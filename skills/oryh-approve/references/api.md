# Oryh Approve API Reference

{{include:_common/api-auth-principal.md}}

{{include:_common/api-conventions.md}}

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
GET /expense-claims/{claim_id}/attachments/{attachment_id}/content       → a receipt
GET /purchase-requests/{request_id}/attachments/{attachment_id}/content  → a quote file
```

`entity_type` is one of `timesheet_header`, `employee_leave`, `expense_claim`,
`purchase_request`, `sales_quotation`, `sales_order`, `invoice`, `payment`.

An attachment is reached through the document that carries it, never by its id
alone: the server answers "may this person see this document" first, and only
then serves the bytes. `GET /attachments/{id}/content` still exists and is the
workspace administrator's route — an approver calling it gets 403, which is
not a missing capability to request but the wrong URL. Quotations and orders
follow the same shape
(`GET /sales-orders/{order_id}/attachments/{attachment_id}/content`).

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
  "source": "ai"
}
```

Allowed actions: `approved`, `rejected`, `returned`, `commented` (an objection
that does not decide). `submitted` is written by `/submit` itself.

Idempotent on (entity, round_no, sequence_no, action): retries return the
recorded fact. `approver_id` is server-attributed from the authenticated
user; a self-reported value is ignored for user credentials.

{{include:_common/when-the-decision-happened.md}}

## Completing A Todo By Hand

Recording the fact closes your own todo in the same transaction; this call
is for a todo the fact did not close (a note-to-self, a task somebody
assigned you outside an approval).

```json
PATCH /todos/{todo_id}
{"status": "completed"}
```

Members can only complete todos assigned to their own employee — completing
someone else's is refused: 403 when you may read it, 404 when you may not.

## Explicitly Out Of Scope

- `PATCH /timesheet-headers/{id}`, `/expense-claims/{id}`,
  `/purchase-requests/{id}`, `/sales-quotations/{id}`, `/sales-orders/{id}` —
  status transitions are the workflow admin's write.
- `POST /sales-quotations/{quotation_id}/send`,
  `POST /sales-quotations/{quotation_id}/close` — the rep's writes.
- `POST /todos` (assigning work) — workflow admin only.
