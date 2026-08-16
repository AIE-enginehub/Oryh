# Invoices, payments and settlement

How the order-to-cash tail is modeled, and why each decision went the way it
did. The short version: **the server guards the money, the agent decides the
process**, and settlement progress is derived rather than stored as a state.

## Why one invoice table and two order tables

`PurchaseOrder` and `SalesOrder` were split even though OFBiz shares one
`OrderHeader`, because their counterparty, direction and closure all differ.

An invoice fails that same test, so it follows OFBiz's `Invoice` instead: one
table, direction on a column. The closure mechanic is *identical* on both sides
— apply money until nothing is outstanding — and a VAT invoice has one physical
shape whether we issued it or received it. Splitting would have duplicated the
settlement machinery, which is the expensive half.

`direction` is a constrained column rather than a `type_options` vocabulary
because every guard in the settlement path branches on it. A value a tenant
could add would leave those guards undecidable.

It is also immutable after filing. Flipping it would silently reinterpret the
counterparty, the capability scope, the billable order and what a payment may
settle; an invoice filed the wrong way round is voided and refiled.

## What OFBiz gave, and what was folded away

| OFBiz | here | why |
|---|---|---|
| `Invoice.invoiceTypeId` | `invoices.direction` + `invoice_type` | direction is structural; the tax-document kind is tenant vocabulary |
| `Invoice(invoiceTypeId = PAYROL_INVOICE)` | `invoices.direction = 'payroll'` | a payslip is an invoice payable to an employee, so the whole settlement path is reused unchanged — see [payroll.md](payroll.md) |
| `InvoiceItem.invoiceItemTypeId` | `invoice_items.invoice_item_type` | freight, discount and tax are line types, so this family needs no adjustments table (unlike quotations and orders, which have one) |
| `OrderItemBilling` | `invoice_items.sales_order_item_id` / `purchase_order_item_id` | explicit FKs, matching how `PurchaseOrderItem.purchase_request_item_id` records its own chain |
| `Payment.paymentTypeId` | `payments.direction` | same reasoning as the invoice |
| `PaymentApplication` | `payment_applications` | kept whole, including `toPaymentId` |
| `PaymentApplication.invoiceId` / `invoiceItemSeqId` / `toPaymentId` | `invoice_id` / `invoice_item_id` / `to_payment_id`, plus `expense_claim_id` | kept as OFBiz has them: one nullable FK per kind, exactly one set (see below) |
| `InvoiceStatus` / `PaymentStatus` | `audit_logs` | same-transaction audit already records every status move |
| `BillingAccount` | `billing_accounts` (+ `billing_account_entries`) | a standing account with a limit, widened past money — see [billing-accounts.md](billing-accounts.md). An unapplied payment is still a *sum in transit*; an account is a *standing balance*, and the two coexist |
| `AcctgTrans` / `AcctgTransEntry` | — | general ledger and period close are a separate question |

## The ledger's target: explicit foreign keys, not a generic pair

`payment_applications` names what it settles with one nullable FK per kind —
`invoice_id`, `expense_claim_id`, `to_payment_id` — and a CHECK that exactly
one is set. A second CHECK keeps `invoice_item_id` meaningless without its
invoice.

This deliberately does **not** use the `(entity_type, entity_id)` pair that
`InventoryItemDetail` uses, and the difference is the point:

- that pair records **provenance** — "what caused this stock movement" — over an
  open-ended set of causes, where a foreign key per kind would never close;
- a settlement is a **document chain**, the same thing
  `PurchaseOrderItem.purchase_request_item_id` and `SalesOrder.quotation_id`
  record, and this codebase already uses explicit FKs for those;
- and these are money rows. A bare uuid can point at a document that does not
  exist, or at one that was deleted afterwards, and only the API would ever
  notice. A foreign key makes that unrepresentable.

In practice the item level is usually empty: money arrives against an invoice,
not against one of its lines. `invoice_item_id` exists for the cases that do
refine that far, and the amount guards stay at document level regardless.

The **API contract is unchanged** by any of this. Agents still name a target
the one uniform way — `applied_to_type` + `applied_to_id` — on both the apply
request and the read model; the model derives those two from whichever column
is set. Storage got integrity; the skills did not get a third spelling of the
same idea.

## A document and its lines are one act

An invoice is raised WITH what it bills. `POST /invoices` takes its `items` in
the same call and the same transaction, so a bad line rolls the whole document
back instead of leaving a half-raised shell behind — the shape five other
document families already had, and which invoices and purchase orders have now
been brought into line with.

The rule that makes it stick: **an invoice must bill something.** Neither lines
nor a declared `total_amount` is a 422, because such a document is not a draft
awaiting detail — its `billed_total` is 0, nothing can ever be settled against
it, and it says nothing. A header-only invoice with a stated total remains
perfectly legal; that is how most summary invoices arrive.

`POST /invoice-items` still exists, for adding a line to an invoice that already
has some. It is not how an invoice is raised.

## What may be restated, and when

The settlement guard refuses to over-apply — but a guard on the write path is
worth nothing if the amount it measured against can be moved afterwards.
Shrinking an issued invoice's total used to leave it settled beyond what it
bills: a state this codebase's own integrity audit reports as corruption,
reachable with one ordinary PATCH.

So the states that freeze a document's LINES also freeze the money on its
header:

| document | frozen outside its editable states |
|---|---|
| invoice | `total_amount`, `tax_amount`, `currency` |
| payment | `amount`, `currency` |

Everything that is not the money — remarks, contacts, due dates — stays
editable, because correcting a remark is not a reason to void a tax document.
Restating what an issued invoice bills is a void-and-reissue or a credit note.
Which states count as editable remains the tenant's choice, as everywhere else.

The same reasoning closes the deletion path: a document that payments have
settled cannot be soft-deleted, on either side of the ledger. The applications
against it would otherwise keep a running total sourced from a row nobody can
see. Reverse them first — which is a counter-entry, and stays visible.

## Settlement is not a status

`applied_amount` on an invoice, an expense claim and a payment is a **running
sum of the append-only application ledger** — the same relationship
`inventory_items.quantity_on_hand` has to `inventory_item_details`.

Everything follows from that:

- `outstanding_amount = billed_total − applied_amount`, reported on `/detail`
  and computed in SQL for the `outstanding=true` work queue. A partly-paid
  invoice therefore needs no state of its own, exactly as a partly-received
  purchase order needs none.
- `billed_total` is the declared `total_amount` when the tenant stated one,
  else the live line sum. This is what makes a header-only invoice — no lines
  at all, which is how most summary invoices arrive — a complete, settleable document.
- `paid` survives in the shipped machine as the **flow's marker**, and the
  integrity audit reports disagreement between marker and ledger as *advisory*.
  It legitimately lags: an invoice is set `paid` moments before the receipt is
  applied, and failing on that would be crying wolf.
- The ledger is immutable. A correction is a counter-entry with a negative
  `amount_applied`; both rows stand as the audit trail.

## Where the line between server and agent falls

The settlement endpoint is modeled on `POST /purchase-orders/{id}/receive`, and
draws the same line:

**The server guarantees (409/422 at the door):**

- nothing is over-applied on either side — not the payment, not the document;
- nothing is reversed beyond what was applied;
- the direction agrees (an inbound payment settles a sales invoice; an outbound
  one settles a vendor bill or an expense claim);
- the currencies agree — cross-currency settlement needs a rate nobody has
  stated, so it is refused with that reason rather than silently converted;
- the target is live and in the same tenant;
- a retry carrying the same `idempotency_key` applies once;
- a tax invoice number is booked once per tenant, **across vendor bills and
  expense items alike**;
- a payment cannot be soft-deleted, nor its amount reduced, below what is
  already applied.

**The agent decides (reading the tenant's workflow definition):**

- when to issue an invoice and what goes on it;
- which customer a bank line belongs to;
- whether a three-way-match gap is acceptable;
- collection and payment-term policy, and whether to write something off;
- whether a payment needs a human approver.

The status of either document is deliberately **not** a gate. State names are
tenant-editable, so the server cannot know which of them mean "collectable" or
"payable" — that judgment sits with the agent, which is the same reason
receiving is not status-gated.

## Three-way match

`GET /invoices/{id}/detail` returns an `order_match` block whenever the invoice
names its order. Per order line: ordered, received (purchase side only), billed,
and the two variances; per document: ordered/billed/unbilled totals and a count
of lines that pin no order line.

`billed_*` sums **every** invoice pinned to that order line, not just the one
being read — otherwise a second invoice for the same delivery would look like
the first never happened.

No tolerance is applied. A threshold here would be business policy living in
the record layer; the agent reads the tenant's definition and judges.

## Capabilities

| capability | holder |
|---|---|
| `invoice.manage` (scopable `:sales` / `:purchase`) | the AR and AP clerks — the scope is what lets them be different people |
| `invoice.advance` | whoever finalizes an invoicing request; also the hosted flow agent |
| `payment.record` | the cashier — files and submits payments |
| `payment.advance` | approves and marks paid; also the hosted flow agent |
| `payment.apply` | the accountant — settlement |

`payment.record` and `payment.apply` are separate on purpose: recording money
and matching it are incompatible duties in Chinese practice, and the split makes that
separation expressible rather than merely intended. None of the five is in the
`member` default — they are finance functions, granted through a role.

`invoice.manage` reuses the existing scope grammar (`verb:scope`), which until
now carried object types. Nothing in `permissions_cover` needed to change: a
scope is an opaque string to the permission layer, and the routes pass the
document's own direction.

## Opening balances

Opening balances are two imports and a matching pass, never a column:

1. `POST /invoices/bulk` — historical invoices at their **full** original
   amount, keyed on their own numbers, arriving fully outstanding;
2. `POST /payments/bulk` — historical money, arriving fully unapplied;
3. `POST /payments/{id}/apply` — the match, through the same guarded call
   everyday finance uses.

There is deliberately no "already settled" field on either import row. Writing
settlement straight into the ledger would bypass the over-application,
direction and currency guards that are the only reason the ledger can be
trusted — and a wrong opening balance is the migration error nobody catches for
months.

## Deliberately still out of scope

- **General ledger and period close.** Journal entries, a chart of accounts and
  a closing lock are the next question, not this one. Nothing here fabricates
  accounting entries.
- **Foreign exchange.** Cross-currency settlement is refused with a message
  saying why, rather than converted at a rate nobody agreed.
- **Aging buckets.** A real need, but it belongs with the aggregation/reporting
  layer rather than beside the ledger. (Credit limits do now exist — they live
  on the billing account, not on the customer, and orders/invoices charged to
  an account occupy its credit from order time; the charging model, the
  transfer-and-settle pattern and the release paths are in
  [billing-accounts.md](billing-accounts.md).)
- **Credit notes as their own entity.** A refund is an outbound payment netted
  against the receipt (OFBiz's `toPaymentId`); a corrected invoice is a voided
  one and a new one.
