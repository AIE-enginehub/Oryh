---
name: oryh-business-object
description: Use when an AI agent needs to record, update, query, or relate ANY tenant-defined business object in oryh through business_objects and business_object_links — warranty cards, sales orders, daily reports, contract reviews, service requests, whatever the tenant has defined. This one skill covers every custom object type by reading the tenant's object-type definition (fields, lifecycle) and workflow definition (submission requirements) at use time; tenants do not need a separate skill per object type. Recording facts only; routing and approval belong to the flow admin and approver skills.
required_capability: business_object.write
---

# Oryh Business Object

Store tenant-specific business facts when the object is not a built-in module (timesheets, bookings). oryh records objects, links, and facts; workflow definitions and the flow admin own the process around them.

**One skill, every custom type.** What makes a `daily_report` different from a `warranty_card` is tenant data — the object-type definition (fields + lifecycle) and the workflow definition (what a valid submission contains) — both read fresh at use time (rules 1 and 2). A tenant writes a dedicated customer skill for an object type only when the *process* exceeds what reading those definitions can express (e.g. a correction-confirm gate over dirty input, fixed customer-facing 话术); the mere existence of a new object type never justifies a new skill.

## Trigger Examples

- "记录一个保修卡申请"
- "把这条维修记录挂到那张保修卡下面"
- "更新这个业务对象的字段"
- "查询某张保修卡下的维修记录"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"
```

The rest is business context from the conversation or the calling customer skill.

## Rules That Prevent Data Damage

0. **Is this already a built-in? Decide before you define.** Custom objects are
   for what ORYH does not ship. `GET /builtin-object-types` lists every shipped
   collection with the words that mean it, so "帮我建个产品对象" is recognisable
   as `products` before anything is written.

   **The server will not stop you.** It states the fact and leaves the reading
   to you, because whether this company's "产品" is our `products` is a question
   about their business, and you are the one who can ask them. A 409 could not.

   So the judgement is yours, and it is not only exact matches: `货品`,
   `merchandise`, `商品目录` are the same thing under another name, and the
   endpoint will not say so. When it matches — exactly or in meaning — **say so
   and stop**: name the real collection, say what is already in it, and ask
   whether that is what they meant. Fields it lacks belong in `custom_fields` on
   the real record.

   **Never resolve a collision by renaming** to `product_2` or `产品_new`. That
   is the same two-sources-of-truth with a worse name, and once the shadow has
   rows nothing merges them back. If they confirm it genuinely means something
   else in this company, name it after what makes it different.
1. **Check the type definition first**: `GET /object-type-definitions?object_type=<type>` — if it exists, the payload must conform to its JSON Schema (422 with the failing path otherwise) and status changes obey its state machine. Types without a definition are free-form with the default status set.
2. **Read the tenant's submission requirements**: `GET /workflow-definitions?entity_kind=business_object&object_type=<type>` — the active definition's 提交要求 (required evidence, numbering conventions, who reviews) shapes the conversation before you write; the flow admin calibrates against the same text, so a requirement skipped here is a guaranteed rework round. No definition → only the schema applies; never invent requirements.
3. **Payload is a full replacement on PATCH**: read the object, merge changes in the agent, send the complete payload. Sending only changed keys deletes the rest.
4. **Statuses are the coarse lifecycle, not workflow position.** Do not advance `status` from this skill — that requires `business_object.advance` (flow admin / admin credential). While an approval flow runs, the object's status does not move; progress lives in approval records and todos.
5. **Scoped permissions**: the credential may be limited to specific object types (`business_object.write:<type>`); a 403 names the missing capability — do not retry with another type to "work around" it.
6. **Dedupe on retries**: list candidates by `object_type` + `payload_match` before creating again.
7. **Preserve raw language** in `source_text`; attribution (`created_by`) is filled server-side for user credentials.

## Core Operations

- Create: `POST /business-objects` (`object_type`, `title`, `summary`, `payload`, `source_text`, `status`)
- Update fields: `GET` → merge → `PATCH /business-objects/{id}` (full payload)
- Relate: `POST /business-object-links` — child as `source_object_id`, parent as `target_object_id`, e.g. `warranty_repair --repair_of--> warranty_card`; duplicates 409, self-links 400
- Query: `GET /business-objects?object_type=&status=&payload_match={"field":"value"}`; children via `GET /business-object-links?target_object_id=&link_type=`
- Soft delete / restore: `DELETE` + `POST .../restore`; deleted objects hidden unless `include_deleted=true`

## Approval Around An Object (who does what)

This skill only creates the record. Then:

- the **flow admin** discovers it (work queue: `status=in_review&without_open_todo=true`), reads the tenant's workflow definition for this `object_type`, and assigns approver todos
- an **approver's agent** records one fact (`POST /approval-records`, needs `approval.record`) and completes its own todo
- the **flow admin** finalizes the status

If your credential happens to hold `approval.record` and the calling skill instructs it, you may record the initial `submitted` fact (round 1, seq 1); otherwise the flow admin backfills it.

## Reference

- [references/api.md](references/api.md): endpoints, templates, definitions/state-machine/workflow contracts, coordination queries.
