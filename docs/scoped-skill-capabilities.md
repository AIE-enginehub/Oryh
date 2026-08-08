# Scoped System Capabilities for Self-Authored Skills

How a tenant can define its own object type (e.g. a daily report), write its
own skill for it, and gate that skill on the same `verb:object_type`
permission grammar that already guards the core API — instead of inventing a
custom capability every time. Worked example: `daily_report`.

## The Problem This Closes

Before this, `business_object.write` (and `.advance`, `.summarize`) worked
perfectly at the API layer with an object-type scope — `require_permission(actor,
"business_object.write", "daily_report")` has always respected a role grant
like `business_object.write:daily_report`. But a skill's `required_capability`
could only be a **bare** verb: `capability_covers()` discarded any scope
suffix before checking, so a role scoped to one object type either got the
generic `oryh-business-object` skill (if it also happened to hold
`business_object.write:*`) or got nothing at all — even though its API access
to that one type worked fine. The only way to hand out a type-specific skill
was to invent a **custom capability** (see `jc.warranty.approve` in
`demo/skills/jc-medical/jc-warranty-card-approve`) purely for skill distribution,
duplicating the real permission.

`validate_required_capability` (`app/api/skills.py`) and `capability_covers`
(`app/services/bundles.py`) now both go through the same `verb:scope` grammar
a role's own permission grants use (`validate_permission_grammar` /
`permissions_cover` in `app/core/permissions.py`). A skill can now declare
`required_capability: business_object.write:daily_report` and it will reach
exactly the roles whose grant is `business_object.write:daily_report`,
`business_object.write:*`, or the bare `business_object.write` — the same
three grants that already satisfy the API check for that object type.
Non-scopable verbs (`approval.record`, `timesheet.submit_own`, …) still
reject a scope outright, and custom capabilities remain scope-less exact
strings, same as before.

## Walkthrough: `daily_report`

1. **Define the object type** (self-service, already existed):

   ```text
   POST /object-type-definitions
   {"object_type": "daily_report", "title": "日报", "json_schema": {...}}
   ```

2. **Write the skill** — when one is warranted at all (see the note under
   "What This Doesn't Give You": the generic `oryh-business-object` skill
   already covers any custom type, so a dedicated per-type skill is the
   exception, not the default). The part that matters here is the frontmatter:

   ```yaml
   ---
   name: daily-report-submit
   description: ...
   required_capability: business_object.write:daily_report
   ---
   ```

3. **Get it into the tenant's skill registry**, either way:
   - Raw API: `POST /skills` with `required_capability` as a JSON field
     (this is what the web console's `POST/PATCH /api/v1/skills` note on the
     Skills page points at).
   - `scripts/import_skill.py <dir> --tenant-id <id>` — now reads
     `required_capability` straight from the frontmatter shown above (it
     already read `name`/`description` the same way; this closes the gap so
     copying a template SKILL.md is enough, no follow-up `PATCH` needed).

4. **Grant the scoped permission on a role**:

   ```text
   POST /roles
   {"name": "reporter", "permissions": ["business_object.write:daily_report", "todos.complete_own"]}
   ```

5. **Bundle distribution now matches the API exactly**: a `reporter` gets
   `daily-report-submit` in their bundle; a role scoped to a different type
   (e.g. `business_object.write:weekly_report`) does not; a role with
   `business_object.write:*` gets it along with every other type-gated skill.
   Regression-tested in
   [tests/test_bundles.py](../tests/test_bundles.py) (`test_scoped_system_capability_gates_custom_skill_by_object_type`)
   and [tests/test_skills.py](../tests/test_skills.py) (`test_skill_validation`).

## What This Doesn't Give You

- **Skill content is still hand-written.** Scope matching solves *who gets
  handed the skill*, not *what the skill does*. And note the granularity
  doctrine that has since firmed up (see `oryh-skill-author`'s authoring
  guide): a new object type by itself never justifies a new skill — the
  generic `oryh-business-object` reads the type's definition and workflow
  definition at use time and covers it. Mint a dedicated type-gated skill
  only when the process exceeds those definitions; when you do, this scoped
  grammar is how you distribute it.
- ~~No web-console authoring form yet~~ — since built: the Skills page
  (`/console/skills`) has a React drawer editor with a capability picker that expands
  scopable verbs over the tenant's object types, so step 2–3 can be done
  entirely in the console. The raw API and `import_skill.py` remain the
  scriptable paths.
- **`business_object.advance:<type>` and `.summarize:<type>` follow the same
  rule** but aren't demonstrated here — a reviewer-only or summary skill for
  `daily_report` would be gated the same way, left as an exercise.

## Reference

- [capabilities-skills-api.md](capabilities-skills-api.md): the big picture —
  how capabilities, the API, and skills relate, with the full
  capability→endpoint→skill map. Read this first if the three-way distinction
  is still fuzzy.
- [app/core/permissions.py](../app/core/permissions.py): the `verb:scope`
  grammar (`validate_permission_grammar`, `permissions_cover`) shared by role
  grants and skill gates.
- [app/services/bundles.py](../app/services/bundles.py): `capability_covers`,
  the skill-distribution side of the check.
- [app/api/skills.py](../app/api/skills.py): `validate_required_capability`,
  the save-time validation.
