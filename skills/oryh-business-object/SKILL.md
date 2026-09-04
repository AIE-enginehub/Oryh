---
name: oryh-business-object
description: Use when an AI agent needs to record, update, query, or relate ANY tenant-defined business object in oryh through business_objects and business_object_links — warranty cards, sales orders, daily reports, contract reviews, service requests, whatever the tenant has defined. This one skill covers every custom object type by reading the tenant's object-type definition (fields, lifecycle) and workflow definition (submission requirements) at use time; tenants do not need a separate skill per object type. Recording facts only; routing and approval belong to the flow admin and approver skills.
required_capability: business_object.write
---

# Oryh Business Object

Store tenant-specific business facts when the object is not a built-in module (timesheets, bookings). oryh records objects, links, and facts; workflow definitions and the flow admin own the process around them.

**One skill, every custom type.** What makes a `daily_report` different from a `warranty_card` is tenant data — the object-type definition (fields + lifecycle) and the workflow definition (what a valid submission contains) — both read fresh at use time (rules 1 and 2). A tenant writes a dedicated customer skill for an object type only when the *process* exceeds what reading those definitions can express (e.g. a correction-confirm gate over dirty input, fixed customer-facing wording); the mere existence of a new object type never justifies a new skill.

{{include:_common/answer-the-question.md}}

{{include:_common/custom-object-is-never-silent.md}}

## Trigger Examples

- "Record a warranty-card application"
- "Attach this repair record to that warranty card"
- "Update this business object's fields"
- "List the repair records under a given warranty card"

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
   collection with the words that mean it, so "create a product object for me" is recognisable
   as `products` before anything is written.

   **The server stops the exact names.** A generic object — a row or a type
   definition — named `customer`, `product`, `quote`, `sales_order`, `supplier`
   or any other word in that list is refused (422) and the refusal names the
   real collection and its import route. That guard exists because a
   workspace once loaded 150,000 legacy customers, products and quotes into
   generic objects named exactly that, beside empty builtin tables.

   The judgement beyond exact words is still yours: `merchandise`,
   `product catalog`, `stock items` are the same thing under another name, and the
   server will not say so. When it matches — exactly or in meaning — **say so
   and stop**: name the real collection, say what is already in it, and ask
   whether that is what they meant. Fields it lacks belong in `custom_fields` on
   the real record. A legacy sheet of customers, products or past documents is
   never generic objects: it is $oryh-master-data (`/customers/bulk`,
   `/products/bulk`) and $oryh-data-migration.

   **Never resolve a collision by renaming** to `product_2` or `product_new`. That
   is the same two-sources-of-truth with a worse name, and once the shadow has
   rows nothing merges them back. If they confirm it genuinely means something
   else in this company, name it after what makes it different.
1. **Check the type definition first**: `GET /object-type-definitions?object_type=<type>` — if it exists, the payload must conform to its JSON Schema (422 with the failing path otherwise) and status changes obey its state machine. Types without a definition are free-form with the default status set.
2. **Read the tenant's submission requirements**: `GET /workflow-definitions?entity_kind=business_object&object_type=<type>` — the active definition's submission requirements (required evidence, numbering conventions, who reviews) shapes the conversation before you write; the flow admin calibrates against the same text, so a requirement skipped here is a guaranteed rework round. No definition → only the schema applies; never invent requirements.
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
