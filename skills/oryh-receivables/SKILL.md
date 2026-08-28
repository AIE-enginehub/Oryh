---
name: oryh-receivables
description: Use when an accounts-receivable person needs to bill a customer and collect — 给客户开票 from a sales order or free-standing, 登记收款 when money lands in the bank, 核销 matching that money to the invoices it settles (including reversing a wrong match), and chasing what is overdue. Covers the whole AR arc for one role. Not for filing the sales order (that is oryh-order-submit), not for the supplier side (oryh-payables), and not for approving or routing anything (oryh-invoice-approval-flow / oryh-payment-approval-flow). Also records customer REFUNDS for sales returns ("给买家退款"、"退货款退回去"): an outbound payment named to the SR- return, settling no invoice.
required_capability: invoice.manage:sales
---

# Oryh Receivables

The AR clerk's whole arc: invoice → receive → settle → chase.

Three facts shape everything here:

- **An invoice's settlement is never a status.** How much is still owed is
  `outstanding_amount`, derived from the settlement ledger. A half-paid invoice does
  not get a special state, and you must never invent one.
- **The server guards the money, not the process.** It refuses to let anything
  be over-applied, to settle across currencies, or to apply an inbound payment
  to a supplier's bill. It does NOT gate settlement on either document's status —
  state names belong to the workspace, so which of them mean "collectable" is
  your judgment, read from the workflow definition.
- **Corrections are counter-entries.** The ledger has no edit and no delete.
  Matched the wrong invoice? Apply a negative amount and then apply it right.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/who-you-are-acting-as.md}}

{{include:_common/leave-no-orphan-work.md}}

## Trigger Examples

- "Invoice City First Hospital for the amount on SO-2026-0031"
- "60,000 came in from East China Hospital — settle it"
- "That money was matched to the wrong invoice, reverse it"
- "Which customers are overdue?"
- "The customer says they never got this invoice — void it and reissue"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs invoice.manage:sales, payment.record, payment.apply
  employee_id: "{{EMPLOYEE_ID}}"  # the officer recorded on what you file
```

Whether a workspace separates recording a receipt (`payment.record`) from
matching it (`payment.apply`) is its own choice — segregation of incompatible
duties. If your key holds only one
of them, do that half and say plainly which step someone else must take.

## Issuing an Invoice

1. **Find what to bill.** Usually a delivered order:
   `GET /sales-orders?status=signed`, or the order the person named. Read
   `GET /sales-orders/{order_id}/detail` for lines, quantities and the agreed
   total.
2. **Reuse before create.** `GET /invoices?direction=sales&sales_order_id={id}`
   — an existing draft for the same order takes more lines; a retry must not
   mint a second invoice.
3. **Raise the invoice WITH its lines, in one call.** `POST /invoices` takes an
   `items` array; the whole thing is one transaction, so a bad line rolls the
   invoice back rather than leaving a half-raised document. `direction: "sales"`
   and `customer_id` are the document (a sales invoice pointed at a vendor is
   refused, not re-filed). Omit `invoice_no` for a server-allocated `INV-`
   number. Set `due_date` from the order's payment terms — **this is what the
   overdue queue reads**, so an invoice without one is never chased.
4. **An invoice must bill something** (422 otherwise): either `items`, or a
   `total_amount` when the amount is agreed as one figure — a summary invoice with only
   a header total is a complete, settleable invoice, so do not fabricate lines
   to look tidy. Lines pinned to order lines (`sales_order_item_id`) make
   billing progress answerable per line and are worth the effort on partial billing.
   Charges and allowances are line TYPES (`shipping`, `discount`), not separate
   documents. `POST /invoice-items` adds a line to an invoice that already
   exists; it is not how an invoice is raised.
5. **Read back, then issue.** `GET /invoices/{invoice_id}/detail` reports
   `computed_total` (the line sum) beside `billed_total` (what settlement
   measures). When they differ, say so and confirm before moving on — rounding the total is
   normal, a typo is not.
6. Correct a wrong header with `PATCH /invoices/{invoice_id}`; the direction is
   not correctable by design, so a wrongly-directed invoice is voided and
   refiled. Once the tax invoice actually exists, record its own number in
   `tax_invoice_number` (+ `tax_invoice_code`), and attach the issued document
   itself — the PDF or OFD the tax system produced — via `attachment_id`; see
   "Keeping the original" below. The customer will ask for it again, and a
   number without the document behind it is not a copy anyone can send. Read it
   back with `GET /invoices/{invoice_id}/attachments/{attachment_id}/content`.
   That number may only be booked
   once in the workspace, and a 409 naming the other document is the
   duplicate-booking backstop doing its job.

## Recording Money In

`POST /payments` with `direction: "inbound"` and the `customer_id` it came
from. Money that already landed is created directly in the terminal state
(`status: "paid"`) — an inbound receipt has nothing to approve.

Record `reference_no` (the bank reference) whenever the person has it: it is how the
same transfer is recognised if it turns up twice.

**Identifying who paid is yours, not the server's.** A bank line saying
"60,000 from that hospital" is a person's judgment against open invoices, and getting it
wrong is a wrong balance for two customers. When it is not obvious, list the
candidates and ask rather than guessing.

## Settlement — matching money to invoices

```json
POST /payments/{payment_id}/apply
{
  "lines": [
    {"applied_to_type": "invoice", "applied_to_id": "invoice-id", "amount_applied": 60000.0}
  ],
  "idempotency_key": "ar-2026-08-02-lin-01"
}
```

- **The receipt and the invoice must name the same customer** (409 otherwise) —
  one customer's money never clears another's invoice, however alike the
  amounts look on a bank statement.
- One payment settles several invoices — that is the ordinary case, one line
  each.
- **Always pass an `idempotency_key`** on a fresh match: this endpoint writes
  money, and a retry without one applies twice. A repeat with the same key
  returns `replayed: true` and writes nothing.
- What is left over is money still in transit — `unapplied_amount` on the
  payment. Find it later with
  `GET /payments?direction=inbound&unapplied=true`.
- If the customer keeps a **standing account** with you (a prepayment or a
  charge account), apply the
  payment to that instead of leaving it floating:
  `{"applied_to_type": "billing_account", "applied_to_id": "..."}`. Unlike an
  invoice, an account has no ceiling — a deposit is not a claim — so the
  response reports its `balance` and `available_amount`. Opening and drawing on
  such accounts is `$oryh-billing-account`.
- Over-applying is a 409 that names the remaining amount on whichever side ran
  out. Read it and re-plan; never retry the same numbers.

**Settling a charged invoice from the account (a transfer)**: when the invoice is
carried on the customer's account and their money is already deposited there,
move it in ONE call on the deposit payment — negative line off the account,
positive line onto the invoice, atomic:

```json
POST /payments/{deposit_payment_id}/apply
{"lines": [
  {"applied_to_type": "billing_account", "applied_to_id": "...", "amount_applied": -100.0},
  {"applied_to_type": "invoice", "applied_to_id": "...", "amount_applied": 100.0}
]}
```

Read `GET /billing-accounts/{id}/detail` first: `charged_invoices` is your
worklist, `entries` shows which deposits are drawable, and which deposit funds
which invoice is the workspace's rule — suggest FIFO if nobody states one, and
name the payments you drew from in your report. A credit-carried invoice with
no deposit behind it needs no transfer: the customer's remittance applies
directly to the invoice, and the account's available recovers by itself.

**Reversing a wrong match**: the same endpoint with a negative
`amount_applied` and a `note` saying why. Both rows stand in the ledger — that
is the audit trail, and hiding the mistake is not an option the API offers.

## Refunding a Customer Return

A sales return that reached its refund step (inspected, refund approved) is THIS
desk's work — the customer money relationship is yours in both directions.
The return is a row in `/sales-orders` with `order_kind: "return"`; the todo
or the flow agent hands you its id.

- Record an **outbound** payment, counterparty `customer_id`, amount = what
  the return refunds (the return row's `total_amount`, or the person's
  words when they differ — say the difference out loud). Put the return's
  number in `reference_no` ("SR-000012") and the row id in `custom_fields`
  (`{"return_order_id": "..."}`), because that is how the flow agent finds
  the refund fact to move the return to `refunded`.
- **A refund settles no invoice.** Returns carry none — the server refuses
  an invoice against a return (422) and refuses charging one to a billing
  account. Do not create a credit note to "have something to apply against";
  the payment standing alone, named to the return, IS the record.
- The payment walks the ordinary payment approval flow (the hosted workflow admin agent);
  nothing about a refund exempts it. Once it is `paid`, the flow agent — not
  you — moves the RETURN to its refunded state.
- Platform-fronted refunds (the platform refunded the buyer directly and settles with
  you later): still record the outbound payment when the settlement says the
  money left, with the platform's aftersale number linked to the return row
  via `/external-document-links` (`external_kind: "return"`).

## Collecting

The overdue queue:

```text
GET /invoices?direction=sales&outstanding=true&due_before=2026-08-02
```

`outstanding=true` means the ledger says money is still owed, regardless of
status. Pair it with `without_open_todo=true` when a flow agent is assigning
chase-ups, so you only see what nobody is already on.

Per customer: `GET /invoices?direction=sales&customer_id={id}&outstanding=true`
gives their open items; each `/detail` carries `outstanding_amount` and the
applications so far. Summarize; do not dump the ledger at the person.

Uncollectable, and the workspace's definition allows writing it off →
`PATCH /invoices/{invoice_id}` with `{"status": "written_off"}`. That is a
policy decision: confirm with the principal, never take it on your own reading.

{{include:_common/attachment-evidence.md}}

## Validate Before Writing

- `customer_id` must exist here (404 otherwise); a sales invoice with a
  `vendor_id`, or a purchase order named as the billed order, is a 422 that
  says which field belongs.
- A tax invoice number already booked — on another invoice **or on an expense
  item** — is a 409. That is the same receipt being reimbursed and billed
  twice; surface it, do not work around it.
- Lines **and the money on the header** are editable only while the invoice is
  in the machine's editable states
  (`GET /object-type-definitions?entity_kind=builtin&object_type=invoice` for
  this workspace's names). `total_amount`, `tax_amount` and `currency` are
  frozen once it leaves them — a 409 there means the invoice has been issued,
  and restating what it bills is a void-and-reissue or a credit note, never a
  PATCH. Everything that is not the money (remarks, contact, due date) stays
  editable.
- An invoice payments have settled cannot be deleted (409). Reverse the
  applications first.
- Currency must match between a payment and what it settles. A 409 here is real:
  cross-currency settlement needs a rate nobody has stated yet.

## What This Skill Never Does

- Invent a settlement status, or read "paid" as truth — `outstanding_amount` is
  the answer, and `paid` is only the flow's marker.
- Delete or edit a settlement row, or delete a payment that still has applications.
- Apply money to a supplier's bill or an expense claim (that is
  `$oryh-payables`), or settle across currencies.
- Decide payment terms or write-off policy on its own — those live in the workspace's
  workflow definition.
- Approve anything. Routing and approval are `the hosted workflow admin agent` for
  the bill and `the hosted workflow admin agent` for the money.
- Import history — that is `$oryh-data-migration` (`POST /invoices/bulk`).
- Open, draw on, or grant points to a customer's standing account — that is
  `$oryh-billing-account`. Applying a receipt INTO one is yours; everything
  else about the account is not.

## Reference

- [references/api.md](references/api.md): every endpoint, the settlement contract, and
  the guards with the exact conditions that raise them.
