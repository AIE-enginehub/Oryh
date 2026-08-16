# Oryh Connect API Reference

Website origin: `<base_url>` — the address rendered into this bundle by the
deployment that issued it. Use it as-is; it is never a question for the person.
API root: `<api_base_url>` — rendered in the same way and already complete.
Send every API request to it as given; the two device endpoints are
unauthenticated, and they are how an agent gets its first credential.

Both device endpoints are POST-only. A GET or HEAD request to the correct URL
returns `405 Method Not Allowed` with `Allow: POST`; that does not mean the
deployment is down. A POST to `<base_url>/auth/device/start` (the website
origin, not the API root) reaches the website instead and also returns 405. If a
reachability check is needed, use `GET <base_url>/healthz`.

## Start

```text
POST <api_base_url>/auth/device/start
Content-Type: application/json
{"client_name": "WorkBuddy on Wenji's MacBook"}
```

```json
{
  "data": {
    "device_code": "…long secret, keep private, never display…",
    "user_code": "MKQP-W3XZ",
    "verification_uri": "https://oryh.ai/web/device",
    "verification_uri_complete": "https://oryh.ai/web/device?code=MKQP-W3XZ",
    "expires_in": 900,
    "interval": 5
  },
  "meta": {}
}
```

Show the person only the `user_code` and open `verification_uri_complete`.
The `device_code` is the polling secret — treat it like a password.

## Poll

```text
POST <api_base_url>/auth/device/token
Content-Type: application/json
{"device_code": "…"}
```

One of:

```json
{"data": {"status": "pending", "interval": 5}, "meta": {}}
{"data": {"status": "denied"}, "meta": {}}
{"data": {"status": "expired"}, "meta": {}}
{"data": {
  "status": "approved",
  "api_key": "calw_…",
  "user": {"email": "wang@corp.com", "name": "Wang", "role": "member", "employee_id": "…"},
  "tenant": "Acme Consulting",
  "tenant_slug": "acme",
  "install_dir": "oryh-skills-acme"
}, "meta": {}}
```

`approved` is delivered exactly once; the next poll of the same device_code
returns `400 device code already used`. `400 invalid device code` means the
code was mistyped or the server was reset — start over.

`tenant` / `tenant_slug` / `install_dir` say which company was just connected —
the server derives them from the account that signed in, and an oryh account
belongs to exactly one company. This is why the agent never asks which company
to connect: the question is answered here, definitively. Name the company back
to the person, and match `install_dir` against the installed directories to
tell a new employer from a reconnect of one already there.

## Fetch the Bundle

```text
GET <api_base_url>/my/skill-bundle
X-API-Key: <the api_key from the approved poll>
Accept: application/zip
```

The zip contains exactly ONE company directory — `oryh-skills-<slug>/` with
`README.md`, `manifest.json`, and one directory per skill, each named
`oryh-<slug>-…` and rendered with this device's key — plus the shared,
company-agnostic `oryh-connect/`.

Install by whole-directory swap of that one company directory. Any other
`oryh-skills-*/` on the machine belongs to another employer: leave it alone.
Afterwards that company's `oryh-<slug>-skill-sync` keeps it current.

## Whose Directory Is This?

```text
GET <api_base_url>/auth/me
X-API-Key: <a key found in an installed bundle>
```

Returns the user plus the identity block
`{"tenant": {"id", "slug", "name"}, "environment_id", "install_dir",
"site_base_url",
"api_base_url", "base_url"}` (`base_url` is the older alias of
`site_base_url`) — how to find
out which company a legacy or unlabelled install belongs to.
