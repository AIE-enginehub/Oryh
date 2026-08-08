# Agent Self-Connect: the Browser Device Flow

How an employee's local agent (WorkBuddy / OpenClaw class) gets from zero —
no credential, no skills — to fully provisioned, without an admin issuing
anything. Shipped in PR #14 (2026-07-07).

## The Problem

Every oryh skill needs a personal user-bound API key rendered into its
files. Before this flow, the only mint path was admin issuance
(`POST /users/{id}/skill-bundle`): an admin generated a bundle, delivered the
zip out-of-band, and the user unpacked it into their agent. That has three
costs:

- onboarding requires an admin in the loop for every employee and every new
  machine
- delivering the zip is delivering a credential (IM/email attachments of
  secrets)
- admin issuance rotates the user's key, so provisioning a second device
  silently killed the first

The fix is the pattern used by `gh auth login` and OAuth device authorization
(RFC 8628): the agent shows a short code, the person proves who they are in
their own browser, and the credential travels only over the API channel.

## The Flow

```text
 agent (no credential)                     oryh                        browser
 ─────────────────────                     ───────                        ───────
 POST /auth/device/start ────────────────▶ mint device_code (secret)
   {client_name}                           + user_code "MKQP-W3XZ"
 ◀──────────────────────────────────────── verification_uri_complete
 open browser ────────────────────────────────────────────────────────▶ /web/device?code=…
                                                                        (not signed in →
 POST /auth/device/token  (poll) ────────▶ pending                      /web/login?next=… → back)
                                                                        person reviews:
                                                                        "WorkBuddy on X's MacBook
                                                                         asks to work as you"
                                           approve ◀─────────────────── clicks Authorize
                                           mint per-device API key
 POST /auth/device/token ────────────────▶ approved: {api_key, user, tenant,
                                           tenant_slug, install_dir}
                                           (one-shot: plaintext cleared)
 GET /my/skill-bundle  (X-API-Key) ──────▶ zip of every eligible skill,
                                           rendered with THIS device's key,
                                           in ONE directory: oryh-skills-<slug>/
 whole-directory install → done; oryh-<slug>-skill-sync keeps it current
```

Three parties, three secrets, each staying in its lane:

- `device_code` — high-entropy, held only by the agent, stored hashed
  server-side; the polling credential
- `user_code` — 8 characters typed/verified by a human (alphabet excludes
  lookalikes: no `0/O`, `1/I/L`, `A/4`…); worthless without a signed-in
  session on the approval page
- the person's password — only ever entered on the oryh login page; the
  agent never sees it

**How the link reaches the browser**: the skill's primary instruction is to
*print* `verification_uri_complete` + the code and let the person open it —
the only path that works when the agent runs over SSH, in WSL, or in a
container (the browser is on the person's machine, not necessarily the
agent's; that separation is the whole point of a device flow). Auto-opening
is an optional convenience only when the agent runs on the person's own
desktop, with per-OS commands (macOS `open`, Windows `start` / PowerShell
`Start-Process`, Linux `xdg-open`) — never a hard dependency.

## API Contract

Both endpoints are unauthenticated (they exist to bootstrap a credential) and
live under `/api/v1/auth/device`. See
[skills/oryh-connect/references/api.md](../skills/oryh-connect/references/api.md)
for exact payloads. Summary:

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `POST /auth/device/start` | begin the handshake | returns `device_code`, `user_code`, `verification_uri_complete`, `expires_in` (default 900s), `interval` (default 5s) |
| `POST /auth/device/token` | poll the outcome | `pending` / `denied` / `expired` / `approved` — `approved` carries the key plus user/tenant identity (`tenant`, `tenant_slug`, `install_dir`) and is delivered **exactly once**; replay → `400 already used` |
| `GET /connect-skill` | download the bootstrap skill | public, unauthenticated, identical for every requester; zip rendered with `ORYH_BASE_URL` only |

Settings: `ORYH_DEVICE_CODE_TTL_MINUTES` (15), `ORYH_DEVICE_POLL_INTERVAL_SECONDS` (5).
The verification URL comes from `resolved_base_url()`: an explicitly
configured `ORYH_BASE_URL` wins (pin this in production so links are
stable behind a proxy); otherwise it follows the Host/X-Forwarded-Host of the
request that called `/auth/device/start`, so a dev box with no fixed domain
still produces a URL the person's browser can actually reach — whichever
address the agent used to reach the server is the address the browser gets
told to open.

## The Approval Page

`GET /web/device?code=…` sits behind the normal tenant console session. Not
signed in → bounce through `/web/login?next=…` and back. That login endpoint
accepts only `/web/device` (with an optional query string) as a server-rendered
return target; every other value enters `/console/dashboard`, so a crafted
login link cannot bounce the session to a retired path or another origin.

The page shows **which agent** is asking (`client_name`, chosen by the agent
at start — e.g. "WorkBuddy on Wenji's MacBook"), **who** it would act as, and
the code, with Authorize / Deny. This one click is the deliberate human step:
identity is decided by whoever approves in the browser, never by agent-side
configuration, and an unexpected prompt ("I didn't start this") is the
phishing tell.

## Key Model: Two Mint Paths, Different Semantics

| Path | Who initiates | Effect on existing keys |
|------|---------------|-------------------------|
| Device flow (this doc) | the employee, per device | **additive** — mints `label: device:<client_name>`, other devices untouched, each individually revocable under API Keys |
| Admin issuance `POST /users/{id}/skill-bundle` | an admin | **rotate-all** — every personal key of the user is deactivated; all devices must reconnect (via the device flow, no admin needed for that) |

So admin issuance doubles as the "kill every session of this user" lever,
while day-to-day multi-device life never destroys a sibling credential.
Self-service sync (`GET /my/skill-bundle`) still never mints or rotates
anything — it re-renders with the key presented.

## Security Properties

- **One-shot delivery**: the plaintext key exists server-side only between
  approval and the agent's first successful poll, then the column is nulled
  and the row consumed. A lost poll response means starting over, never
  re-fetching.
- **Hashed polling secret**: `device_code` is stored as a SHA-256 hash, same
  as API keys and session tokens.
- **Short TTL, one-shot codes**: pending authorizations die after 15 minutes;
  a denied or consumed code cannot be approved later.
- **Pre-auth table without tenant RLS**: `device_authorizations` rows exist
  before any tenant is known, so the table deliberately carries no tenant
  policy (same reasoning as the open SELECT on `users`/`api_keys`); all
  lookups go through the hashed device code or the short-lived user code.
- **Audited on both sides**: `device.authorized` when the person approves
  (who, which key, which client, which code), `device.connected` when the
  agent picks the key up.

## Two Employers, One Agent

A contractor or a part-timer works for two companies and files a timesheet in
each. They have two oryh identities — two tenants, two users, two personal keys
— because a tenant is a company and the credential IS the identity. What they do
NOT have is two agents: WorkBuddy is installed once, on one laptop.

So the bundle is namespaced by tenant, and every name a local agent can see
carries the company:

| | |
|---|---|
| install root | `oryh-skills-<slug>/` — one directory per employer, siblings, never merged |
| skill name | `oryh-<slug>-timesheet-submit` — the company sits inside the skill's own name |
| description | opens with `[晶诚医疗设备有限公司]` and says the copy is bound to that company |
| `manifest.json` | carries `tenant: {id, slug, name}`, `install_dir`, `base_url` |

The slug (`Tenant.slug`) is derived once from the tenant's email domain
(`jc-medical.cn` → `jc-medical`) and is then **immutable**: it is a directory
name on machines we do not control. The display name stays freely renameable —
the manifest's tenant block is what carries a rename out to installed copies,
since the per-skill `files_hash` covers templates only and would not move.

**How the agent picks the right company.** It doesn't infer, it reads. The name
and description are all a local agent sees when it selects a skill, so "报一下
晶诚这周的工时" matches `oryh-jc-medical-timesheet-submit` and no other. The key
baked into that skill's files can only write to that company's oryh — there is
no tenant parameter to get wrong, and no "switch company" edit that would make
sense.

**Where the namespacing happens.** Only at render time. The tenant's skill
registry stores canonical, unprefixed names (`oryh-timesheet-submit`) and
pristine templates; `build_bundle_zip` rewrites names, descriptions and every
cross-reference between skills on the way out. Prefixing in the registry instead
would rename rows the agents' `files_hash` comparison depends on, and make every
deploy look like a content change to every installed bundle on earth.

**The one exception** is `oryh-connect`: it must run before any tenant is known,
and it serves every employer the person has. It is machine-level, installs
unprefixed at the bundle root, and is rendered from the product catalog with no
key in it. It is the only skill two companies' bundles both write, and they
write the same bytes.

**Migrating a legacy install.** Bundles used to install into a single
`oryh-skills/` with unprefixed skills. Both `oryh-connect` and `oryh-skill-sync`
now instruct an agent that finds one to identify its owner (`GET /auth/me` with
the key inside it returns the tenant block), reinstall it as
`oryh-skills-<slug>/`, and delete the legacy directory — leaving both is the bad
outcome, since it means two live copies of every skill under two names.

## Distribution: How People Get the Bootstrap Skill

`oryh-connect` ([skills/oryh-connect/SKILL.md](../skills/oryh-connect/SKILL.md))
contains no credentials and no tenant data — one copy serves the whole
company, safe to put on a wiki or IM. Three paths:

1. **Download link**: `GET /web/connect` is a public page (no login
   required) with a "Download oryh-connect.zip" button, backed by
   `GET /api/v1/connect-skill` — also public, same zip for every requester.
   Unlike a bundle, this route renders `ORYH_BASE_URL` (the one placeholder
   the server always knows) but nothing tenant- or user-specific, so it is
   safe to link from a wiki, onboarding doc, or IM without provisioning
   anyone first. `/web/login` and the code-less state of `/web/device` both
   link here for someone who lands on the console without an agent yet.
2. **Hand the directory**: give the employee the `skills/oryh-connect/`
   directory directly (e.g. bundled with other onboarding files). This copy
   has an unrendered `{{ORYH_BASE_URL}}` placeholder, which the skill
   treats as "ask the person for their company's oryh URL".
3. **Already connected**: the skill ships in every rendered bundle — at the zip
   root, beside the tenant's directory rather than inside it, because it is not
   company-specific — so a device whose key was rotated or revoked already has
   the instructions to reconnect, and so does a person adding a second employer.
   skill-sync's 401 handling points at it.
   Signed-in users also see a "连接新设备" shortcut to `/web/connect` on the
   API Keys page for adding another machine.

Trigger phrases the skill matches: "连接 oryh" / "登录 oryh", first use
on a new machine, or any oryh skill hitting `401 invalid API key`.

## After Connecting

The bundle downloaded in the final step is the same capability-derived bundle
admin issuance produces: every skill the user's role covers, rendered with
this device's key, employee id, and name. From then on `oryh-skill-sync`
compares manifests on session start and re-downloads when tenant admins
publish changes or the user's role shifts — login is a one-time event per
device, not a recurring chore.

## Testing

- `tests/test_device_flow.py`: happy path, deny, expiry, code normalization
  (lowercase / missing dash input), multi-device coexistence plus admin
  rotate-all still working, `?next=` open-redirect guard.
- Manual loop against a running stack:
  `curl -X POST …/auth/device/start` → open `verification_uri_complete` →
  sign in, Authorize → `curl -X POST …/auth/device/token` →
  `curl …/my/skill-bundle -H "X-API-Key: …"`.
