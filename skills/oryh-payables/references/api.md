# Payables API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

## Supplier invoices (purchase side)

| Call | Purpose |
|---|---|
| `GET /invoices?direction=purchase&outstanding=true` | what is still owed to suppliers |
| `GET /invoices?direction=purchase&outstanding=true&due_before=2026-08-02` | due or overdue for payment |
| `GET /invoices?direction=purchase&vendor_id={id}` | one supplier's bills |
| `GET /invoices?direction=purchase&purchase_order_id={id}` | what is already booked against an order |
| `GET /invoices?tax_invoice_number=24312000000098765432` | find a bill by the supplier's own number |
| `POST /invoices` | book one |
| `GET /invoices/{invoice_id}/detail` | lines, applications, totals and `order_match` |
| `PATCH /invoices/{invoice_id}` | correct the header, or move the status |
| `DELETE /invoices/{invoice_id}` | soft delete — refused while payments are applied |
| `POST /invoices/{invoice_id}/restore` | undo that |
| `POST /invoices/{invoice_id}/submit` | draft → submitted (awaiting check) |

```json
POST /invoices
{
  "direction": "purchase",
  "employee_id": "{{EMPLOYEE_ID}}",
  "vendor_id": "vendor-uuid",
  "title": "Server purchase",
  "invoice_date": "2026-07-28",
  "due_date": "2026-08-27",
  "total_amount": 26000.0,
  "tax_amount": 2991.15,
  "invoice_type": "vat_special",
  "tax_invoice_code": "3100253130",
  "tax_invoice_number": "24312000000098765432",
  "purchase_order_id": "po-uuid",
  "extracted_fields": {"seller_tax_id": "91310000MA1FL1234X", "total_with_tax": "26000.00"},
  "items": [
    {"line_no": 1, "product_id": "product-uuid", "quantity": 10,
     "unit_price": 2600.0, "amount": 26000.0, "tax_rate": 13.0,
     "purchase_order_item_id": "po-line-uuid"}
  ]
}
```

`items` ride the create in one transaction — a bad line rolls the whole bill
back. A bill must carry either `items` or a `total_amount` (422 otherwise), and
once it leaves its editable states `total_amount`/`tax_amount`/`currency` are
frozen (409): restating what a booked bill owes is a void-and-refile.

`vendor_id` is required; a `customer_id` or a `sales_order_id` on a purchase
invoice is a 422. A `tax_invoice_number` already booked anywhere in the
workspace — including on an expense item — is a 409 naming the other document.

### Lines

| Call | Purpose |
|---|---|
| `GET /invoice-items?invoice_id={id}` | this bill's lines |
| `GET /invoice-items?purchase_order_item_id={id}` | everything billed for one order line |
| `POST /invoice-items` | add one |
| `PATCH /invoice-items/{item_id}` | correct it |
| `DELETE /invoice-items/{item_id}` | drop it |

```json
POST /invoice-items
{
  "invoice_id": "invoice-uuid",
  "line_no": 1,
  "invoice_item_type": "goods",
  "product_id": "product-uuid",
  "quantity": 10,
  "unit_price": 2600.0,
  "amount": 26000.0,
  "tax_rate": 13.0,
  "purchase_order_item_id": "po-line-uuid"
}
```

`purchase_order_item_id` may only point at a line of the order this invoice
bills — pin the invoice with `purchase_order_id` first, or it is a 422.

## Three-way match

`GET /invoices/{invoice_id}/detail` → `order_match`, present when the bill names
its order:

```json
{
  "order_type": "purchase_order",
  "order_id": "po-uuid",
  "order_no": "PO-2026-00012",
  "order_status": "received",
  "lines": [
    {
      "order_item_id": "po-line-uuid",
      "line_no": 1,
      "product_name": "Server",
      "ordered_quantity": 10.0,
      "ordered_amount": 26000.0,
      "received_quantity": 8.0,
      "billed_quantity": 10.0,
      "billed_amount": 26000.0,
      "quantity_variance": 0.0,
      "receipt_variance": 2.0
    }
  ],
  "ordered_total": 26000.0,
  "billed_total": 26000.0,
  "unbilled_total": 0.0,
  "unmatched_line_count": 0
}
```

- `billed_*` sums **every** invoice pinned to that order line, not just this
  one — billing in instalments stays honest.
- `receipt_variance` positive = billed more than arrived. That is the number an
  approver needs; the server states it and stops there.
- `unmatched_line_count` counts this bill's lines that pin no order line (a
  freight line the order never carried, for example).

The sales side gets the same block from `sales_order_id`, without
`received_quantity` — there is no receiving fact on that side.

## Payments out

| Call | Purpose |
|---|---|
| `GET /payments?direction=outbound&status=submitted` | awaiting approval |
| `GET /payments?direction=outbound&unapplied=true` | paid but not matched (a prepayment) |
| `GET /payments?vendor_id={id}` | one supplier's payments |
| `POST /payments` | file one |
| `GET /payments/{payment_id}/detail` | its applications and what is left |
| `PATCH /payments/{payment_id}` | correct it, or (with `payment.advance`) move the status |
| `POST /payments/{payment_id}/submit` | draft → submitted, into approval |
| `DELETE /payments/{payment_id}` | soft delete — refused while applications stand |
| `POST /payments/{payment_id}/restore` | undo that |

```json
POST /payments
{
  "direction": "outbound",
  "employee_id": "{{EMPLOYEE_ID}}",
  "vendor_id": "vendor-uuid",
  "amount": 26000.0,
  "currency": "CNY",
  "payment_method": "bank_transfer",
  "bank_account": "ICBC ****1234",
  "counterparty_account": "6222 0000 1111 2222",
  "remarks": "PO-2026-00012 final payment"
}
```

Exactly one counterparty: `vendor_id`, or `payee_employee_id` when paying an expense claim.
`counterparty_account` is what the approver compares against the vendor's
master record — the standing check against payment-diversion fraud.

Lifecycle: `draft → submitted → approved → paid`, with `rejected`/`returned`
off `submitted` and `void` after `paid`.
`GET /object-type-definitions?entity_kind=builtin&object_type=payment` for this
workspace's names.

## Settlement

```json
POST /payments/{payment_id}/apply
{
  "lines": [
    {"applied_to_type": "invoice", "applied_to_id": "bill-a", "amount_applied": 26000.0},
    {"applied_to_type": "expense_claim", "applied_to_id": "claim-b", "amount_applied": 800.0}
  ],
  "idempotency_key": "ap-2026-08-02-01"
}
```

Returns the written rows, the payment's `applied_amount` / `unapplied_amount`,
and a `targets` entry per document with `settleable_total`, `applied_amount`
and `outstanding_amount`.

`GET /payment-applications?applied_to_type=invoice&applied_to_id={id}` reads one
document's ledger. There is no PATCH and no DELETE — a correction is a line
with a negative `amount_applied`.

### The guards, and exactly when they fire

| Condition | Answer |
|---|---|
| more applied than the payment holds | 409 naming what is still unapplied |
| more applied than the document owes | 409 naming what is still outstanding |
| reversing more than was applied (either side) | 409 |
| outbound payment against a sales invoice | 409 — that one is settled by an inbound payment |
| payment and document in different currencies | 409 — needs an explicit rate, unsupported |
| target soft-deleted | 404 |
| `amount_applied: 0`, or a payment applied to itself | 422 |
| deleting a payment that still has applications | 409 — reverse them first |
| reducing `amount` below what is applied | 409 |
| restating a booked bill's `total_amount`/`tax_amount`/`currency` | 409 — void and refile |
| deleting a bill you have already paid against | 409 — reverse them first |

Not guarded on purpose: the status of either document — which states mean
"payable" is the workspace's wording, read from the workflow definition.

## Related

- `GET /purchase-orders/{po_id}/detail` — ordered vs received, from the order's
  own side.
- `GET /supplier-products?vendor_id={id}` — `last_price`, for the price sanity
  check.
- `GET /expense-claims/{claim_id}/detail` — what a claim actually totals before
  paying it.
- `POST /approval-records` with `entity_type: "payment"` — the approval fact on
  a payment request.

## When the decision happened

{{include:_common/when-the-decision-happened.md}}
