# Oryh Business Object API Reference

Use these templates with:

- header: `X-API-Key: <api_key>`
- base path: `<base_url>/api/v1`

## Common Endpoints

```text
GET /business-objects?object_type=&status=&include_deleted=&payload_match=
POST /business-objects
GET /business-objects/{business_object_id}
PATCH /business-objects/{business_object_id}
DELETE /business-objects/{business_object_id}
POST /business-objects/{business_object_id}/restore
GET /object-type-definitions?object_type=&status=
POST /object-type-definitions
GET /object-type-definitions/{definition_id}
PATCH /object-type-definitions/{definition_id}
DELETE /object-type-definitions/{definition_id}
GET /business-object-links?source_object_id=&target_object_id=&link_type=
POST /business-object-links
GET /approval-records?entity_type=business_object&entity_id={business_object_id}
POST /approval-records
GET /todos?employee_id=&status=&entity_type=business_object&entity_id=
POST /todos
PATCH /todos/{todo_id}
```

## Create Business Object

```json
POST /business-objects
{
  "object_type": "warranty_card",
  "title": "Warranty card application for SN-JC-2026-0422",
  "summary": "Service provider submitted a warranty card application.",
  "payload": {
    "application_no": "WC-APP-0422",
    "customer": "City Hospital",
    "printer_serial_no": "SN-JC-2026-0422"
  },
  "source_text": "服务商提交医院打印机保修卡申请。",
  "status": "in_review",
  "created_by": "agent-id"   // service keys only; user keys are attributed server-side
}
```

Allowed statuses:

- `open`
- `in_review`
- `approved`
- `rejected`
- `archived`

## Update Business Object

`payload` is a full replacement on update. Read the current object first, merge changes in the agent, then send the complete payload. Do NOT include `status` in an ordinary update: changing it requires the separate `business_object.advance` capability (403 otherwise) — status advancement is the flow admin's write, per rule 4.

```json
PATCH /business-objects/{business_object_id}
{
  "payload": {
    "application_no": "WC-APP-0422",
    "customer": "City Hospital",
    "printer_serial_no": "SN-JC-2026-0422",
    "registered_warranty_card_no": "WC-REG-0422"
  }
}
```

## Object Type Definitions

A tenant may attach a JSON Schema to an `object_type`. When an active definition exists, `payload` is validated on every business object create and update; violations return `422` with the failing JSON path. Types without a definition stay free-form. Creating and updating definitions requires an admin or service credential.

```json
POST /object-type-definitions
{
  "object_type": "warranty_card",
  "title": "Warranty Card",
  "json_schema": {
    "type": "object",
    "required": ["application_no", "printer_serial_no"],
    "properties": {
      "application_no": {"type": "string"},
      "customer": {"type": "string"},
      "printer_serial_no": {"type": "string"}
    }
  }
}
```

- One definition per `object_type` per tenant; duplicates return `409`, update the existing one instead.
- Changing `json_schema` bumps `version`.
- `DELETE` archives the definition (validation stops); `PATCH {"status": "active"}` reactivates it.
- Before writing objects of a defined type, read the definition and make the payload conform.

## State Machines And Status Transitions

If the tenant's type definition carries a `state_machine`, status changes are validated: an illegal transition returns `409` listing the allowed targets. Creating an object in any declared state is allowed (recording an already-mid-flow fact). Types without a machine accept the default statuses only.

States are the **coarse lifecycle** (open/approved/paid …), never workflow nodes. While an approval flow runs, the object's status does not move; the flow's position is derived from approval records (nodes passed) and open todos (current holder).

## Workflow Definitions (natural language, versioned)

The flow agent's map lives in `/workflow-definitions` — plain natural language per tenant per type:

```text
GET  /workflow-definitions?entity_kind=&object_type=&name=      → active version
GET  /workflow-definitions?...&history=true                     → every version
GET  /workflow-definitions/{id}                                  → any version, incl. superseded
POST /workflow-definitions                                       → publish (admin/service): appends
                                                                   version N+1, supersedes N
```

When making a routing decision, record the version you followed in the todo's `metadata.workflow_version` so the trail stays traceable.

## Agent Coordination: Todos And State Queries, Not Streams

Coordination is level-triggered — query current state; never rely on having "seen" a message:

- **"What should I (or my principal) do now?"** → `GET /todos?employee_id=<me>&status=open`. Completion is a first-class fact: finish work by `PATCH /todos/{id}` with `status=completed`. Unfinished work stays visible and can be escalated (`due_at`, filter `due_before=`).
- **Flow-agent work queue** — records nobody has been assigned to act on yet:

{{include:_common/tenant-state-names.md}}

```text
GET /timesheet-headers?status=submitted&without_open_todo=true
GET /business-objects?object_type=expense_claim&status=in_review&without_open_todo=true
```

These queries are idempotent and self-healing: if your run crashes, the item is still in the queue next time.

## Audit Trail (read-only)

`GET /audit-logs?entity_type=&entity_id=&action=&actor=&before=&limit=` returns what happened to a record, newest first (`business_object.created`, `business_object.status_changed`, `approval.recorded`, `todo.created`, `todo.completed`, `timesheet.submitted`, …). Use it for troubleshooting and accountability. It is NOT a delivery mechanism — do not build workflows that depend on consuming it.

**Name what you are asking about.** Sweeping the whole trail needs
`users.manage`; without it, pass `entity_id` for the record in question (or
`actor=user:<yourself>` for your own activity). An unscoped call is **403**,
not an empty list — the error says what you may ask for instead.

## Query By Payload Fields

`payload_match` filters business objects by top-level scalar payload fields (JSON object, string/number/boolean values only):

```text
GET /business-objects?object_type=warranty_card&payload_match={"printer_serial_no":"SN-JC-2026-0422"}
```

## Link Business Objects

```json
POST /business-object-links
{
  "source_object_id": "repair-object-id",
  "target_object_id": "warranty-card-object-id",
  "link_type": "repair_of",
  "metadata": {
    "linked_by": "agent-id"
  }
}
```

Duplicate links return `409`. Self-links return `400`.

## Query Relationships

List child objects under a parent:

```text
GET /business-object-links?target_object_id=warranty-card-object-id&link_type=repair_of
```

Find the parent object from a child:

```text
GET /business-object-links?source_object_id=repair-object-id&link_type=repair_of
```

## Create Approval Record (requires approval.record — approver or flow-admin credential)

```json
POST /approval-records
{
  "entity_type": "business_object",
  "entity_id": "business-object-id",
  "round_no": 1,
  "sequence_no": 1,
  "action": "approved",
  "approver_id": "employee-id",   // service keys only; user keys are attributed server-side
  "approver_role": "manager",
  "comment": "approved",
  "source": "ai",
  "acted_at": "2026-04-22T09:00:00Z",
  "metadata": {
    "workflow_id": "customer-specific-flow"
  }
}
```

Allowed actions:

- `submitted`
- `approved`
- `rejected`
- `returned`
- `commented`

## Create Approval Todo (requires todos.assign — normally the flow admin)

Unlike the approval-record POST above, this is NOT retry-idempotent: an open todo already standing for the same (employee, entity) returns 409 "open todo already exists for this entity" — treat that as already-assigned, not an error.

```json
POST /todos
{
  "employee_id": "approver-employee-id",
  "entity_type": "business_object",
  "entity_id": "business-object-id",
  "title": "Review warranty card application",
  "description": "Review the submitted warranty card application.",
  "todo_type": "approval",
  "created_by": "agent-id",
  "metadata": {
    "round_no": 1,
    "sequence_no": 1
  }
}
```

## Complete Todo (own todos only for members)

```json
PATCH /todos/{todo_id}
{
  "status": "completed",
  "completed_by": "approver-employee-id"
}
```
