# Oryh My Work API Reference

{{include:_common/api-auth-principal.md}}

## Identity

```text
GET /auth/me            → user + linked employee_id
```

## My Inbox

```text
GET /todos?employee_id={me}&status=open&include=target
GET /todos?employee_id={me}&status=open&due_before=<now, ISO-8601>&include=target   # overdue check
```

Todo fields worth reporting: `title`, `todo_type` (approval / rework / follow_up), `due_at`, `entity_type` + `entity_id` (what it points at), `metadata.round_no` / `metadata.sequence_no` (for approval todos — pass them to the approve skill).

With `include=target` each row also carries `target` — the context that used
to cost one detail call per todo:

```text
target: {object_type, title, status, employee_id, employee_name,
         amount, unit ("amount"|"hours"), currency, customer_name,
         approval_count, last_approval: {action, round_no, sequence_no,
                                         approver_name, approver_role,
                                         comment, acted_at},
         missing}
```

`amount` is the document's total (summed from its lines where the family
stores none); `last_approval` is the newest fact on its trail. `missing:
true` means the target row is gone — report it, do not re-fetch. The full
`/detail` endpoints remain the answer when the person drills into ONE item;
never walk the whole inbox through them again.

## Context For A Todo

```text
GET /timesheet-headers/{entity_id}/detail      # when entity_type=timesheet_header
GET /expense-claims/{entity_id}/detail         # when entity_type=expense_claim
GET /purchase-requests/{entity_id}/detail      # when entity_type=purchase_request
GET /sales-quotations/{entity_id}/detail       # when entity_type=sales_quotation
GET /sales-orders/{entity_id}/detail           # when entity_type=sales_order
GET /business-objects/{entity_id}              # when entity_type=business_object
```

## My In-flight Submissions

```text
GET /timesheet-headers?employee_id={me}&status=submitted
GET /expense-claims?employee_id={me}&status=submitted
GET /purchase-requests?employee_id={me}&status=submitted
GET /sales-quotations?employee_id={me}&status=submitted
GET /sales-orders?employee_id={me}&status=submitted
GET /approval-records?entity_type={timesheet_header|expense_claim|purchase_request|sales_quotation|sales_order}&entity_id={id}
```

## My Deals Awaiting The Other Side

{{include:_common/tenant-state-names.md}}

```text
GET /sales-quotations?employee_id={me}&status=approved   # cleared to send, not yet sent
GET /sales-quotations?employee_id={me}&status=sent       # with the customer; check valid_until
GET /sales-orders?employee_id={me}&status=confirmed      # awaiting shipment; chase the tracking no
GET /sales-orders?employee_id={me}&status=shipped        # in transit; follow to sign-off
```

Each of these four is a stage, not a name: "cleared but not sent", "with the
customer", "sold but not shipped", "in transit". A workspace that renamed the
stage still has it — find it in `state_machine.states` and ask for that one.

The trail is the position: the latest records tell whether the manager has acted, whether finance is reviewing, and so on. Do not infer progress from the status field — it stays `submitted` for the whole flow.

## Completing A Confirmed Item

```json
PATCH /todos/{todo_id}
{"status": "completed"}
```

Members can only complete their own todos (403 otherwise). Completion is attributed and timestamped by the server.
