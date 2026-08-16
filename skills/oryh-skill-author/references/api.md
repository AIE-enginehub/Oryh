# Oryh Skill Author API Reference

Use with:

- header: `X-API-Key: <the admin's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add

## Read The Tenant's Reality (step 3)

```text
GET /auth/me                                   → permissions (need skills.manage; workflows.publish for policy)
GET /object-type-definitions                   → builtin + custom objects, schemas, state machines
GET /workflow-definitions?entity_kind=&object_type=  → current policy text (active version)
GET /skills?status=all                         → existing registry (product + custom)
GET /skills/{name}                             → full files of one skill (house style / revision base)
GET /capabilities                              → system + custom gates
GET /roles                                     → who holds what (distribution preview)
```

## Publish A New Skill

`files`: `SKILL.md` required; at most 32 files, 512 KB total; relative paths only (422 otherwise).

```json
POST /skills
{
  "name": "jc-quote",
  "title": "Jingcheng quoting",
  "description": "Use when ... (the full trigger contract — see authoring-guide)",
  "required_capability": "quotation.submit_own",
  "files": {
    "SKILL.md": "---\nname: jc-quote\n...",
    "references/intake.md": "...",
    "references/follow-up.md": "..."
  }
}
```

- 409 on duplicate name → revise instead.
- `required_capability` is validated: must be a system verb (optionally scoped, e.g. `business_object.write:sales_order`) or an existing custom capability.

## Revise

```json
PATCH /skills/{name}
{"files": {"SKILL.md": "...complete replacement...", "references/intake.md": "...",
    "references/follow-up.md": "..."}}
```

Full-map replacement; server bumps `version` when content changed. Editing a `kind=product` skill's `files` forks it to `custom` — warn first. Metadata-only PATCHes do not fork: a changed `required_capability` and an archived `status` are the tenant's and survive catalog syncs, while content (and the description inside it) keeps following the catalog. `catalog_required_capability` in the response is the shipped default; setting the gate back to it resumes tracking.

## Archive

```text
DELETE /skills/{name}    → status=archived (bundle stops shipping it)
```

## Audience — who it is for

```text
GET /skills/{name}/assignments
```

```json
{"data": {
  "assignments": [
    {"id": "…", "subject_type": "role", "subject_id": "procurement",
     "subject_label": "procurement", "blocked_members": []}
  ],
  "impact": {
    "distribution_mode": "capability",
    "reaches_now": ["…"], "would_reach": ["…"],
    "gaining": ["…"], "losing": ["…"], "blocked": ["…"]
  }
}}
```

Read `impact` **before** changing anything. `losing` names the people a switch
to `targeted` would take the skill away from — say that number out loud.
`blocked` names people in the audience whose role cannot run the skill; they
never receive it, and the fix is a capability grant, not an audience edit.

```json
POST /skills/{name}/assignments
{"subject_type": "role", "subject_id": "procurement"}
```

`subject_type` is `role` (subject_id = role **name**) or `user` (subject_id =
user id). 404 if the subject does not exist in this tenant. Naming the same
subject twice returns **200** with the existing row instead of 201 — already
done, not an error.

```text
DELETE /skills/{name}/assignments/{assignment_id}
```

One subject at a time in both directions — there is no whole-list replace, so
"add one person" can never turn into "keep only that person".

```json
PATCH /skills/{name}
{"distribution_mode": "targeted"}
```

`capability` (default) = whoever passes `required_capability`. `targeted` =
only the audience, **and an empty audience means nobody** — emptying it
narrows rather than falling back to everyone.

## Adjacent (only when the requirement lands there)

```json
POST /workflow-definitions        // policy — needs workflows.publish; publish-only, no PATCH
{
  "entity_kind": "builtin",
  "object_type": "sales_quotation",
  "definition_text": "## Submission requirements\nA quotation must state its validity period……\n[every existing clause from the step-3 GET, carried over verbatim]\n## Routing rules\n……\n[+ the admin's new/changed clause, woven in where it belongs]"
}
```

`definition_text` is the tenant's ENTIRE policy for this object after this
call, not the delta — see "Amending A Workflow Definition" in SKILL.md. A
`definition_text` shorter than what step 3's `GET` just returned is almost
always a bug, not an intentional simplification; confirm with the admin
before publishing one.

```json
POST /capabilities                // custom gate — needs users.manage
{"name": "acme.intake.submit", "title": "May submit parsed quotations"}
// name: lowercase [a-z0-9_.] only — hyphens are rejected (422)

POST /object-type-definitions     // new custom object — needs object_types.manage
{"object_type": "sales_order", "title": "Sales order", "json_schema": {...}, "state_machine": {...}}

POST /type-options                // custom type vocabulary entry — needs object_types.manage
{"family": "product_price_type", "name": "dealer_tier2", "title": "Tier-2 dealer price"}
// families: product_price_type / sales_adjustment_type / expense_category / work_type
// name: lowercase [a-z0-9_], no hyphens; DELETE archives (history keeps its values)
```

## Distribution (after publish)

```text
POST /users/{id}/skill-bundle     → admin-issued bundle (rotates ALL that user's keys; needs users.manage + keys.manage)
GET  /my/skills/manifest          → what each agent's own sync compares against
```

Eligibility is evaluated per request from the user's role grants vs `required_capability` — publishing to the right gate IS the distribution act.
