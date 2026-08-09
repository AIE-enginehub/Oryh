# Receivables API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

## Invoices (sales side)

| Call | Purpose |
|---|---|
| `GET /invoices?direction=sales&status=draft` | this workspace's sales invoices; `status` must be a state of the tenant's machine (422 names the real ones) |
| `GET /invoices?direction=sales&customer_id={id}&outstanding=true` | one customer's open items |
| `GET /invoices?direction=sales&outstanding=true&due_before=2026-08-02` | 逾期应收 |
| `GET /invoices?direction=sales&outstanding=true&without_open_todo=true` | open items nobody is chasing yet |
| `GET /invoices?tax_invoice_number=24312000000098765432` | find by the tax document's own number |
| `GET /invoices?sales_order_id={id}` | what has already been billed for an order |
| `POST /invoices` | file one |
| `GET /invoices/{invoice_id}` | the header |
| `GET /invoices/{invoice_id}/detail` | lines, applications, totals, and the order match |
| `PATCH /invoices/{invoice_id}` | correct the header, or move the status |
| `DELETE /invoices/{invoice_id}` | soft delete — refused while payments are applied |
| `POST /invoices/{invoice_id}/restore` | undo that |
| `POST /invoices/{invoice_id}/submit` | draft → submitted (开票申请) |

`keyword=` also matches title, invoice_no, tax_invoice_number and the
counterparty snapshot. Lists accept `page`/`size`.

### Create

```json
POST /invoices
{
  "direction": "sales",
  "employee_id": "{{EMPLOYEE_ID}}",
  "customer_id": "customer-uuid",
  "title": "2026年7月货款",
  "invoice_date": "2026-07-31",
  "due_date": "2026-08-30",
  "currency": "CNY",
  "tax_amount": 5522.12,
  "invoice_type": "vat_special",
  "sales_order_id": "order-uuid",
  "items": [
    {"line_no": 1, "product_id": "product-uuid", "quantity": 4,
     "unit_price": 12000.0, "amount": 48000.0, "tax_rate": 13.0,
     "sales_order_item_id": "order-line-uuid"}
  ]
}
```

- `items` ride the create in one transaction: a bad line rolls the whole
  invoice back, so a validation error never leaves a half-raised document.
  The response reads the lines back under `items`.
- **An invoice must bill something**: send `items`, or a `total_amount` when the
  amount is agreed as one figure (汇总开票). Neither is a 422.

- `direction` and `customer_id` are the document. A `vendor_id` here is a 422.
- `invoice_no` is server-allocated (`INV-`) unless you bring the workspace's
  own; a duplicate is a 409.
- `due_date` is what the overdue queue reads. Without it the invoice is never
  chased.
- `total_amount` may be omitted when there are lines — then the line sum is
  what settlement measures. `/detail` reports both.
- `total_amount`, `tax_amount` and `currency` are frozen once the invoice
  leaves its editable states (409). Restating what an issued invoice bills is a
  void-and-reissue or a credit note, never a PATCH.
- `invoice_type` must be an active option:
  `GET /type-options?family=invoice_type` (`POST /type-options` extends it).

### Lines

| Call | Purpose |
|---|---|
| `GET /invoice-items?invoice_id={id}` | this invoice's lines |
| `POST /invoice-items` | add a line to an invoice that already exists (raising one is `POST /invoices` with `items`) |
| `GET /invoice-items/{item_id}` | one line |
| `PATCH /invoice-items/{item_id}` | correct it |
| `DELETE /invoice-items/{item_id}` | drop it |

```json
POST /invoice-items
{
  "invoice_id": "invoice-uuid",
  "line_no": 1,
  "invoice_item_type": "goods",
  "product_id": "product-uuid",
  "quantity": 4,
  "unit_price": 12000.0,
  "amount": 48000.0,
  "tax_rate": 13.0,
  "sales_order_item_id": "order-line-uuid"
}
```

- `invoice_item_type` carries charges and allowances: `goods`, `service`,
  `shipping`, `discount` (negative amount), `tax`, `rounding`, `other` —
  `GET /type-options?family=invoice_item_type`.
- Quantity and price are both optional: a 运费 line has only an `amount`.
- `sales_order_item_id` may only point at a line of the order this invoice
  bills; pin the invoice with `sales_order_id` first or it is a 422.
- Lines are writable only in the machine's editable states (409 otherwise).

## Payments in

| Call | Purpose |
|---|---|
| `GET /payments?direction=inbound&unapplied=true` | money not yet matched to anything |
| `GET /payments?customer_id={id}` | one customer's payments |
| `GET /payments?reference_no=BANK-99887766` | find a bank line already recorded |
| `POST /payments` | record one |
| `GET /payments/{payment_id}/detail` | its applications and what is left |
| `PATCH /payments/{payment_id}` | correct it |

```json
POST /payments
{
  "direction": "inbound",
  "employee_id": "{{EMPLOYEE_ID}}",
  "customer_id": "customer-uuid",
  "amount": 60000.0,
  "currency": "CNY",
  "payment_date": "2026-08-01",
  "payment_method": "bank_transfer",
  "reference_no": "BANK-99887766",
  "status": "paid"
}
```

Exactly one counterparty (`customer_id` here); naming none or two is a 422.
`payment_method` comes from `GET /type-options?family=payment_method`.

## 核销

```json
POST /payments/{payment_id}/apply
{
  "lines": [
    {"applied_to_type": "invoice", "applied_to_id": "invoice-a", "amount_applied": 40000.0},
    {"applied_to_type": "invoice", "applied_to_id": "invoice-b", "amount_applied": 20000.0,
     "note": "尾款"}
  ],
  "idempotency_key": "ar-2026-08-02-01"
}
```

Returns the written rows, the payment's `applied_amount` / `unapplied_amount`,
and a `targets` entry per document with its `settleable_total`,
`applied_amount` and `outstanding_amount`.

- A repeat with the same `idempotency_key` returns `replayed: true` and writes
  nothing.
- A negative `amount_applied` reverses an earlier match. Both rows stay.
- `GET /payment-applications?payment_id={id}` or
  `?applied_to_type=invoice&applied_to_id={id}` reads the ledger. There is no
  PATCH and no DELETE on it.

### The guards, and exactly when they fire

| Condition | Answer |
|---|---|
| more applied than the payment holds | 409 naming what is still unapplied |
| more applied than the document bills | 409 naming what is still outstanding |
| reversing more than was applied (either side) | 409 |
| inbound payment against a purchase invoice | 409 — that one is settled by an outbound payment |
| payment and document in different currencies | 409 — needs an explicit rate, unsupported |
| target soft-deleted | 404 |
| `amount_applied: 0` | 422 |
| a payment applied to itself | 422 |
| deleting a payment that still has applications | 409 — reverse them first |
| reducing `amount` below what is applied | 409 |
| restating an issued invoice's `total_amount`/`tax_amount`/`currency` | 409 — void and reissue, or raise a credit note |
| deleting an invoice that payments are applied to | 409 — reverse them first |

Not guarded on purpose: the status of either document. State names belong to
the workspace, so "is this collectable yet" is read from the workflow
definition, not from the server.

## Lifecycle

```text
GET /object-type-definitions?entity_kind=builtin&object_type=invoice
```

Shipped default: `draft → submitted → issued`, then `paid`, `written_off` or
`void`; `cancelled` from draft/submitted/returned; `returned` sends a rejected
开票申请 back. Tenants rename and rewire — read the machine rather than assuming.

`paid` is a flow marker only. The truth is `outstanding_amount` on `/detail`.

## Related

- `GET /workflow-definitions?entity_kind=builtin&object_type=invoice` — the
  workspace's own billing and collection policy, in its own words.
- `POST /todos` with `entity_type: "invoice"` — a chase-up assignment.
- `POST /approval-records` with `entity_type: "invoice"` — an approval fact on
  an 开票申请.
