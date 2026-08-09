# Oryh Skill Sync API Reference

Use with:

- header: `X-API-Key: <the principal's user-bound key — this company's>`
- base path: `api_base_url`, exactly as given — no version prefix to add

Both endpoints reject web sessions and tenant-level service keys — only a personal bundle key works. The key decides the company: there is no tenant parameter, and none is needed.

## Am I Current?

```text
GET /my/skills/manifest
```

```json
{
  "data": [
    {
      "name": "oryh-my-work",
      "installed_as": "oryh-jc-medical-my-work",
      "title": "Oryh My Work",
      "version": 3,
      "files_hash": "9f2c…"
    }
  ],
  "meta": {
    "total": 1,
    "tenant": {"id": "…", "slug": "jc-medical", "name": "晶诚医疗设备有限公司"},
    "install_dir": "oryh-skills-jc-medical",
    "base_url": "https://oryh.ai"
  }
}
```

Compare against the installed `oryh-skills-<slug>/manifest.json`:

```json
{
  "generated_at": "2026-07-14T12:00:00+00:00",
  "tenant": {"id": "…", "slug": "jc-medical", "name": "晶诚医疗设备有限公司"},
  "install_dir": "oryh-skills-jc-medical",
  "base_url": "https://oryh.ai",
  "skills": [
    {
      "name": "oryh-my-work",
      "installed_as": "oryh-jc-medical-my-work",
      "title": "Oryh My Work",
      "version": 3,
      "files_hash": "9f2c…"
    }
  ]
}
```

`name` is the registry name — the stable key both sides compare on, identical for every tenant. `installed_as` is what the skill is called on this machine, where it must carry the company so that two employers' skills never collide.

Out of date when any of: a name present on one side only, a differing `version`, a differing `files_hash`, or a differing `tenant.name` (the company renamed itself — the per-skill hashes cover templates only, so nothing else would move).

`meta.tenant.id` different from the installed `tenant.id` is not staleness — it means this key belongs to a different company than this directory. Stop and report; do not install.

## Refresh

```text
GET /my/skill-bundle          → application/zip
```

The zip contains exactly one company directory — `oryh-skills-<slug>/` with `README.md`, `manifest.json`, and one directory per skill, each named `oryh-<slug>-…` — plus the shared, company-agnostic `oryh-connect/`. It is rendered with the SAME key used to call the endpoint — no rotation, no admin involvement. Each successful download is recorded in the tenant audit log as `skill_bundle.synced`.

Swap that one company directory. Sibling `oryh-skills-*/` directories belong to the person's other employers; leave them alone.

## Why A Skill Is Missing

```text
GET /my/skills/reach
```

```json
{"data": {
  "subject_type": "user", "subject_id": "…", "subject_label": "谢婷", "role": "member",
  "received": [
    {"name": "oryh-my-work", "reasons": ["capability"]},
    {"name": "jc-quote", "reasons": ["targeted_role"], "named_via": ["role:project_manager"]}
  ],
  "withheld": [
    {"name": "oryh-purchase-submit", "reasons": ["missing_capability"],
     "required_capability": "purchase.submit_own",
     "granted_by_roles": ["procurement", "admin"]},
    {"name": "jc-warranty-card-approve",
     "reasons": ["missing_capability", "not_in_audience"]}
  ]
}}
```

Needs only this person's own key — it says nothing about anyone else.

`reasons` carries **every** blocker, not the first. A skill can fail both
axes, and then both must be fixed: granting the capability alone leaves it
exactly as unreachable as before, and so does an audience edit alone. Relay
all of them.

`not_in_audience` means the skill is aimed elsewhere — an audience change,
not a permission change. Do not tell the person to ask for a capability there.

`granted_by_roles` is who holds the capability today. It is a fact for an
admin looking for a precedent, **not** a suggestion that the person ask to be
made one of those roles — that is usually an escalation, and the real fix is
almost always a grant to the role they already have.

## Errors

```text
401 invalid API key                    → key rotated/revoked; reconnect via oryh-connect
403 a user-bound API key is required   → configured credential is a service key, not a personal one
```
