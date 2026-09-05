---
name: oryh-connect
description: Use when a person's AI agent needs to connect (or reconnect) to a company's oryh — first run on a new machine, "连接 oryh" / "登录 oryh", adding a SECOND employer alongside one that is already installed, or when any oryh skill hits 401 invalid API key. Opens the oryh web page for the person to sign in and approve, then installs that company's personal skill bundle with a fresh device key. Needs no pre-existing credential; this is the only oryh skill that works before login, and the only one shared by every company the person works for.
---

# Oryh Connect

The bootstrap: every other oryh skill needs a personal API key baked into
its files — this one starts from nothing. It runs a browser device flow
(RFC 8628 style, like `gh auth login`): the agent shows a short code, the
person approves it on the oryh web page after signing in, and the agent
receives a device-bound API key it immediately trades for the person's full
skill bundle. The key itself is never stored outside the installed bundle.

This skill is **not** company-specific — it is the one oryh skill installed
once per machine, unprefixed. Every other skill belongs to exactly one
employer and is named after it.

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "Connect me to the company's oryh"
- "I need oryh at my other company too" — a person can work for two companies; each gets
  its own bundle, side by side, and this skill installs both.
- "oryh says my key is invalid" (any oryh skill returning `401 invalid API key`)
- First session on a new machine, before any other oryh skill can work.

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  install_dir: <the agent's skills folder — where the oryh-skills-* directories
               live or should live>
```

**Use `base_url` as it stands; never ask the person for a URL.** This file was
downloaded from the very deployment it points at, and the address was rendered
in at that moment — it is a fact about this copy, not a default to confirm.
Deployments do differ (a company's test server, a private install), which is
exactly why each one hands out its own connect skill carrying its own address;
a person who uses two deployments holds two connect skills, each already
correct. The same goes for `api_base_url`: it arrives complete, so send API
calls straight to it and never append a version prefix or trim one off.

The single exception: if the value still contains the literal `{{...}}`, this
copy was never rendered (someone copied it out of a repo rather than
downloading it). Only then ask for the company's oryh URL.

`base_url` is the website origin, `api_base_url` is the API root, and API
requests go to the latter unchanged. Do not probe the device start or token endpoints with GET
or HEAD: both are POST-only and such a probe returns `405 Method Not Allowed`
even when the deployment is healthy. To check reachability, GET
`<base_url>/healthz`; otherwise proceed directly with the POST below.

## Which Companies Are Already Installed

Take this inventory before connecting — and never turn it into a question. Its
only job is to let you tell a reconnect from a new employer once the login has
named the company in step 5.

```text
1. List `oryh-skills-*/` in the install dir. Each is ONE employer, and each
   holds a `manifest.json` with:
     {"tenant": {"id", "slug", "name"}, "environment_id", "install_dir",
      "site_base_url",
      "api_base_url", "skills": [...]}
   Read them: that is the map from directory → company, and the only reliable
   one, because the company name a person says out loud appears
   nowhere in a directory listing otherwise.

   Match ONLY that exact prefix. A directory carrying a different prefix
   belongs to a DIFFERENT oryh deployment (a company's test server and its
   production server are separate installs, named apart on purpose). Never
   count one as connected here: its companies do not exist on this
   deployment, and its keys are not valid against this `base_url`.

   Then confirm each candidate really is this deployment's: its
   `manifest.json` `base_url` must equal the `base_url` you are connecting
   to. If it differs, it is another deployment's directory — skip it,
   silently. Report "no company is connected yet" when nothing survives both
   checks; do not round a directory you cannot verify up to a connection.

2. Do NOT ask which company this connect is for. You cannot be told anything
   useful: an oryh account belongs to exactly one company, so whoever signs in
   at step 4 settles it, and the approval in step 5 hands you the name, slug
   and install_dir outright. Go straight to the flow.

   Reconcile afterwards, against this inventory:
   - the approved `install_dir` is already here → a RECONNECT (the same person,
     same company, on this machine again, or after the key died). The new
     bundle replaces that directory wholesale.
   - it is not here → a NEW employer. Its bundle lands in a new sibling
     directory. Never overwrite, merge, or "reuse" another company's directory.
```

Do not treat "some oryh directory exists" as "already connected" — that is the
one-employer assumption, and it is wrong for anyone with two jobs, and wrong
again for anyone whose machine also holds another deployment's bundles.

A live installed company is not a reason to stop, and not a reason to ask
either: this connect will either refresh that same company (they sign in with
that account) or add another one (they sign in with the other), and the login
decides which. When the person only wants to know whether their skills are
current, that is the company's own `oryh-<slug>-skill-sync`, not a reconnect —
it needs no login at all.

## The Connect Flow

```text
3. POST `<api_base_url>/auth/device/start` with `Content-Type: application/json`:
   {"client_name": "<agent + machine, e.g. WorkBuddy on Wenji's MacBook>"}
   → {device_code, user_code, verification_uri_complete, expires_in, interval}

   The exact URL is `{{ORYH_API_BASE_URL}}/auth/device/start` — the address
   rendered into this file, used as-is. Do not ask for it or substitute one.

4. Give the person the verification_uri_complete link AND the user_code, and
   ask them to open it: "open <link> in a browser, sign in to oryh, and confirm the code XXXX-XXXX".
   Printing the link is the robust path and the only one that works when you
   run on a different machine, over SSH, in WSL, or in a container — the
   browser must be on the PERSON's machine, not necessarily yours.
   If (and only if) you run on the person's own desktop, you MAY also open it
   for them as a convenience — never depend on it, always show the link too:
     - macOS:   open "<url>"
     - Windows: start "" "<url>"   ·   PowerShell: Start-Process "<url>"
     - Linux:   xdg-open "<url>"
   The code lets them verify it is THIS agent asking.

5. Poll POST `<api_base_url>/auth/device/token` with
   {"device_code": ...} every `interval` seconds until the status leaves
   "pending":
   - approved → {api_key, refresh_token, expires_at, user, tenant, tenant_slug,
     install_dir}: this is the
     answer to "which company" — the server derived it from the account that
     just signed in, which is why you never had to ask. Greet the person by name
     AND by company ("connected to Jingcheng Medical Equipment Co."), so a mistaken login is
     caught here rather than after a timesheet lands in the wrong company. Match
     `install_dir` against the inventory to know whether this is a reconnect or
     a new employer, then continue.
   - denied   → the person rejected it; stop, do not retry.
   - expired  → codes live ~15 minutes; offer to start over from step 3.

   **Save the refresh token now, OUTSIDE every skills directory** — e.g.
   `~/.oryh/<tenant_slug>.refresh-token`, permissions 600, one file per
   employer. The api_key expires (`expires_at` says when) and is renewed
   from that file without a browser round-trip; the skill files themselves
   must never hold it — they are synced and backed up, which is exactly how
   the old never-expiring keys leaked. Never print either value into the
   conversation; confirm where you saved it instead.

6. GET `<api_base_url>/my/skill-bundle` with the new key
   (Accept: application/zip)
   → that company's bundle, every file rendered with this device's key.

7. Install. The zip is self-describing: it contains exactly ONE company
   directory, `oryh-skills-<slug>/`, plus the shared `oryh-connect/`.
   - Whole-directory swap of `oryh-skills-<slug>/` — never file-by-file, so a
     half-updated skill can never run. If that directory already exists (a
     reconnect for the same company), replace it wholesale; the install is
     idempotent, not duplicating.
   - Leave every OTHER `oryh-skills-*/` directory untouched. Those are other
     employers, with other keys.
   - `oryh-connect/` (this skill) may be refreshed at the same level; it is the
     same file for every company.
   - Report which skills arrived AND which company they serve.
```

The device key pair delivered in step 5 is consumed exactly once — if the poll
response is lost, start over from step 3 rather than retrying the token call.
Later, when any oryh skill reports its key **expired** (the 401 says so), renew
without a browser: `POST <api_base_url>/auth/token/refresh` with the saved
refresh token; save the NEW refresh token it returns over the old one. Only
when refresh itself is refused does anyone need this connect flow again.

## If Your Runtime Speaks MCP

Some runtimes (Claude Code, Codex and others that implement the Model
Context Protocol) can connect without any skill files at all: add oryh as
an MCP server at `{{ORYH_BASE_URL}}/mcp`. The runtime discovers the
authorization server from `{{ORYH_BASE_URL}}/.well-known/oauth-authorization-server`,
opens the browser for the person to sign in and approve (authorization
code with PKCE), and holds an expiring access token it refreshes itself —
no key is ever written to disk. Behind that door the same three layers
arrive: tools are the REST contract bound one-to-one, **prompts are these
very skills** (read the desk's prompt before calling tools — the judgement
is there, not in the tool descriptions), and resources are their reference
files. The door is the same door: capabilities, permissions and the audit
trail are exactly what a skills-only agent gets.

Both paths coexist. A runtime without MCP installs the bundle exactly as
above; a runtime with MCP may skip the bundle. Nothing about the company's
side changes either way.

## A Legacy Unprefixed `oryh-skills/` Directory

Bundles used to install into a single `oryh-skills/` with unprefixed skill
names — which is why two employers could not coexist. If you find one:

```text
a. Read the api_key out of any skill in it and GET `<api_base_url>/auth/me`.
   → the tenant block {id, slug, name} tells you which company owns it.
   (401 → it is dead; just delete it.)
b. GET `<api_base_url>/my/skill-bundle` with that key and install it properly,
   as in step 7.
c. Delete the legacy `oryh-skills/` directory only after the new
   `oryh-skills-<slug>/` is fully in place.
```

Leaving both is the worst outcome: two live copies of every skill under two
different names, and no way for the agent to tell which company a request meant.

## Multi-Device

Each connect mints a key for THIS device only (`label: device:<client_name>`);
keys on the person's other machines keep working. The person or an admin can
revoke any device individually under Access credentials in the web console. An
admin-issued bundle (`POST <api_base_url>/users/{id}/skill-bundle`) still
rotates ALL of the person's keys **for that company** — after that, every
device reconnects through this skill. Other employers are unaffected; their
keys live in their own tenant.

## What This Skill Never Does

- Ask the person for their oryh password (the browser page does the
  authenticating; the agent only ever sees the device key).
- Ask which oryh URL to use. The address in this file belongs to the
  deployment that issued it; the only thing worth saying about it is that it
  is unrendered.
- Ask which company to connect. The person signs in, and the server names the
  company — asking first invites a wrong answer about something the login is
  about to settle anyway.
- Store the API key anywhere except inside the installed bundle files.
- Choose who to connect as — the identity comes from whoever approves in the
  browser, never from agent configuration.
- Point one company's skills at another company's oryh, or copy a key between
  directories. The key IS the identity; there is no "switch company" edit.

## Reference

- [references/api.md](references/api.md): exact endpoints and response shapes.
