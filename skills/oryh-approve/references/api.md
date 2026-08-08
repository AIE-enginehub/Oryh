# Oryh Approve API Reference

{{include:_common/api-auth-approver.md}}

## Read Context

One `/detail` per document type; the trail and your own todo are the same two
calls whichever type it is.

```text
GET /timesheet-headers/{header_id}/detail       → entries, hours, period, trail
GET /expense-claims/{claim_id}/detail           → items, totals, attachments, trail
GET /purchase-requests/{request_id}/detail      → items, estimated_total, unpriced_item_count, pending_sku_count, trail
GET /sales-quotations/{quotation_id}/detail     → lines, computed_total vs total_amount, revisions, valid_until, trail
GET /sales-orders/{order_id}/detail             → lines, the linked quotation header, ship_to_address, contract_no, trail

GET /approval-records?entity_type={type}&entity_id={id}   → the trail on its own
GET /todos?employee_id={me}&status=open&entity_type={type}&entity_id={id}   → your open todo
GET /attachments/{attachment_id}/content        → a receipt or quote file
```

`entity_type` is one of `timesheet_header`, `expense_claim`,
`purchase_request`, `sales_quotation`, `sales_order`.

## Record One Approval Fact

```json
POST /approval-records
{
  "entity_type": "expense_claim",
  "entity_id": "claim-id",
  "round_no": 1,
  "sequence_no": 2,
  "action": "approved",
  "approver_role": "manager",
  "comment": "amounts match the receipts",
  "source": "ai",
  "acted_at": "2026-07-11T09:00:00Z"
}
```

Allowed actions: `approved`, `rejected`, `returned`, `commented` (an objection
that does not decide). `submitted` is written by the submitter side.

{{include:_common/approval-record-idempotency.md}}

`approver_id` is server-attributed from the authenticated user; a
self-reported value is ignored for user credentials.

`acted_at` is the decision moment and is required.

## Complete Own Todo

```json
PATCH /todos/{todo_id}
{"status": "completed"}
```

Members can only complete todos assigned to their own employee — completing
someone else's returns 403.

## Explicitly Out Of Scope

- `PATCH /timesheet-headers/{id}`, `/expense-claims/{id}`,
  `/purchase-requests/{id}`, `/sales-quotations/{id}`, `/sales-orders/{id}` —
  status transitions are the workflow admin's write.
- `POST /sales-quotations/{quotation_id}/send`,
  `POST /sales-quotations/{quotation_id}/close` — the rep's writes.
- `POST /todos` (assigning work) — workflow admin only.
