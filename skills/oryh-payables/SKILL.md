---
name: oryh-payables
description: Use when an accounts-payable person needs to book what a supplier billed and pay it — 登记进项发票 against a purchase order, checking it against what was ordered and what actually arrived (三单匹配), filing the 付款申请 that goes through approval, and 核销 matching the payment to the bills it settles. Also settles employee expense claims once approved. Not for the customer side (oryh-receivables), not for placing the purchase order (oryh-purchase-order), and not for routing the approval (oryh-invoice-approval-flow for the bill, oryh-payment-approval-flow for the payment). Also records the vendor's REFUND coming home for a purchase return ("戴尔退款到了"): an inbound payment named to the PR- return.
required_capability: invoice.manage:purchase
---

# Oryh Payables

The AP clerk's whole arc: book the bill → three-way match → payment request → settle.

What makes this side different from receivables:

- **The invoice is someone else's document.** You are recording what the
  supplier sent, including its own tax-invoice code and number. Getting that
  number in matters: it is the workspace's only defence against the same input
  invoice being reimbursed to
  an employee *and* paid again to the supplier.
- **Three-way match is facts, not a verdict.** The server reports ordered vs
  received vs billed per line. Whether a gap is acceptable is read from the
  workspace's workflow definition — never decided here, and never waved through.
- **Paying needs approval; recording does not.** An outbound payment walks
  `draft → submitted → approved → paid`. You file and submit it; someone else
  approves it.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/who-you-are-acting-as.md}}

{{include:_common/leave-no-orphan-work.md}}

## Trigger Examples

- "Dell's invoice arrived, 26,000 — check it against PO-2026-00012"
- "This invoice is two units more than we received, what now?"
- "Turn this batch of supplier bills into a payment request"
- "The money went out, settle it"
- "Li's expense claim is approved — pay it"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs invoice.manage:purchase, payment.record, payment.apply
  employee_id: "{{EMPLOYEE_ID}}"  # the officer recorded on what you file
```

## Booking a Supplier Invoice

1. **Find the order it belongs to.** `GET /purchase-orders?vendor_id={id}` or
   by number. `GET /purchase-orders/{po_id}/detail` gives lines, the agreed
   total, and ordered-vs-received quantities.
2. **Reuse before create.**
   `GET /invoices?direction=purchase&purchase_order_id={id}` — billing in
   instalments is
   normal, so check what is already booked before adding another.
3. **Book the bill WITH its lines, in one call.** `POST /invoices` takes an
   `items` array and files the whole thing in one transaction.
   `direction: "purchase"` with the required `vendor_id`. Record the supplier's
   own `tax_invoice_number` and `tax_invoice_code`, and put the full verification or OCR
   result in `extracted_fields` — the typed columns are only the queryable
   subset. **Keep the file you read those numbers off**: upload the supplier's
   PDF or the scan of the paper invoice and set `attachment_id` on the bill —
   see "Keeping the original" below. Extracting the figures and discarding the
   document leaves the workspace unable to answer what the supplier actually
   billed, which is the question every payment dispute comes down to. Read it
   back with
   `GET /invoices/{invoice_id}/attachments/{attachment_id}/content`. Set `due_date` from the payment terms; that is what the payables
   queue reads. A bill must carry either `items` or a `total_amount` (422
   otherwise).
4. **Pin the lines** to the PO lines they bill (`purchase_order_item_id`). This
   is what makes the three-way match possible; an unpinned line is counted and
   reported as unmatched rather than silently ignored.
5. **Correct a wrong header** with `PATCH /invoices/{invoice_id}` — but the
   money (`total_amount`, `tax_amount`, `currency`) is frozen once the bill
   leaves its editable states, and a bill filed in the wrong direction cannot be
   flipped. Both are void-and-refile, not edits. A bill you have already paid
   against cannot be deleted either; reverse the applications first.

## Three-way match

`GET /invoices/{invoice_id}/detail` returns `order_match` whenever the bill
names its purchase order. Per order line it states:

- `ordered_quantity` / `ordered_amount` — what was committed to the vendor
- `received_quantity` — what the warehouse actually recorded arriving
- `billed_quantity` / `billed_amount` — summed across **every** invoice against
  that order, so a second bill never looks like the first did not happen
- `quantity_variance` (billed − ordered) and `receipt_variance` (billed −
  received); positive means over-billed

Plus `ordered_total` / `billed_total` / `unbilled_total` for the document and
`unmatched_line_count` for lines that bill nothing on the order.

**Read the workspace's rule before judging a gap**:

```text
GET /workflow-definitions?entity_kind=builtin&object_type=invoice
```

Tolerances, who signs off on an over-bill, whether freight may exceed the order —
all of that is the workspace's text, not yours. When the definition is silent
and the numbers disagree, state the three figures plainly to the principal and
ask; do not average them into a decision.

## Paying

### Before paying an expense claim

**Ask which route this workspace takes.** Two are legitimate and the server picks neither:

- **Bill it.** `POST /expense-claims/{claim_id}/invoice` first, then treat
  the invoice as an ordinary bill in every step below. The claim's payable
  lands in AP, in aging, and in whatever a ledger posts from — what a
  company that closes books wants.
- **Pay it.** Skip the invoice and settle the claim itself at the end
  (`"applied_to_type": "expense_claim"`). Fewer documents, same money, same
  guards.

**This workspace's answer is written down — read it, do not choose for
them.** Two places, in order:

- the **"Workspace calibration" section at the bottom of this skill** — the
  admin's own sentence, appended when your bundle was built, so it is
  already here, nothing to fetch ("pay claims directly, no invoice" /
  "always bill first").
- the claim's workflow definition:
  `GET /workflow-definitions?entity_kind=builtin&object_type=expense_claim`
  — what happens after approval is that document's subject.

When neither says, ask the principal once and say which you used. When they
disagree, say so and ask — do not pick.

A single claim may not take both routes: whichever it takes first is the one
it keeps, and the other is refused with a 409 naming what already covers it.
The two documents keep separate running totals, so paying both would pay the
employee twice while each reported itself correctly settled. Reversing the
applications releases the claim to the other route.

On the billing route: the company owes the EMPLOYEE, so the invoice names
them as payee. It arrives `issued`, not `draft`: the
spending was approved on the claim, and a second approval round would ask
someone to re-decide it holding none of the receipts. It bills the claim's
**unbilled lines**, so a claim may carry several invoices — bill what is
agreed now, the disputed lines once they are settled.
`GET /expense-claims/{claim_id}/detail` reports `invoices`,
`invoiced_amount` and `uninvoiced_amount`; read those, never the status.

A supplier bill needs none of this; start at 1.
### The payment

1. **File the payment.** `POST /payments` with `direction: "outbound"` and the
   `vendor_id` (or `payee_employee_id` when paying an expense claim). Leave it at `draft`.
2. **Record `counterparty_account`.** The account the money is about to go to.
   Attach the bank receipt or remittance advice once you have it
   (`attachment_id` on the payment); read it back with
   `GET /payments/{payment_id}/attachments/{attachment_id}/content`.
   This is the single most valuable field on the document: payment-diversion
   fraud works by
   changing the account on an invoice, and an approver comparing this against
   the vendor's own master record is what catches it. Storing it also makes
   that check auditable afterwards instead of only conversational.
3. **Submit it**: `POST /payments/{payment_id}/submit`. Approval routing is the
   flow agent's job; do not advance the status yourself past `submitted`.
4. **After the transfer**, whoever holds `payment.advance` moves it to `paid`.

## A Vendor's Refund for a Purchase Return

Goods went back (`/purchase-orders` row with `order_kind: "return"`, PR-
number) and the vendor's money comes home: record an **inbound** payment,
counterparty `vendor_id`, the return's number in `reference_no` and its row
id in `custom_fields` (`{"return_order_id": "..."}`) — the flow agent reads
that to move the return to `refunded`. A vendor refund settles no invoice
either (a return carries none — the server refuses); if the vendor issues a
credit against FUTURE purchases instead of money, that is a billing-account
entry on our standing account with them ($oryh-billing-account), not a
payment — say which of the two actually happened, never guess.

## Where the Cash Actually Left

The payment's `paid` is the book's claim; the bank's fact is a register
line the cashier links to it ($oryh-treasury). "has it actually left the bank" reads that
link — a paid payment with no bank line is a chase, not a shrug.

## Settlement

```json
POST /payments/{payment_id}/apply
{
  "lines": [
    {"applied_to_type": "invoice", "applied_to_id": "bill-id", "amount_applied": 26000.0}
  ],
  "idempotency_key": "ap-2026-08-02-01"
}
```

- One payment settles several bills — one line each.
- **The payment and the document must name the same party** (409 otherwise).
  The trap is employee reimbursement: the merchant issued the receipt, so
  their bill looks like the thing being reimbursed — but they were already
  paid, by the employee, out of the employee's own money. Settle the
  employee's claim, not the merchant's bill.
- **Always pass an `idempotency_key`**: this writes money, and a retry without
  one applies twice. A repeat with the same key returns `replayed: true`.
- **An expense claim is settled by one route or the other, never both** — see
  step 0 of "Paying". If this workspace bills, apply to the invoice; if it does
  not, apply to the claim with `"applied_to_type": "expense_claim"`. A 409 here
  means the claim already went the other way, and it names what covers it. The
  claim's `paid` status remains the flow's marker either way; the money fact is
  the application.
- A prepayment in transit is an outbound payment whose `unapplied_amount` is still
  positive: `GET /payments?direction=outbound&unapplied=true`. When the supplier
  keeps a **standing prepayment account** with you, apply the payment to it
  instead (`"applied_to_type": "billing_account"`) so the balance is a standing
  fact rather than a floating one — see `$oryh-billing-account`.
- A wrong match is reversed with a negative `amount_applied` and a `note`. Both
  rows stay in the ledger.

{{include:_common/attachment-evidence.md}}

## Validate Before Writing

- `vendor_id` is required on a purchase invoice (422 names it); a `customer_id`
  or a sales order named as the billed order is refused.
- A `tax_invoice_number` already booked — on another bill **or on an expense
  item** — is a 409 naming the other document. That is the duplicate-booking
  control; escalate it, never work around it by blanking the number.
- Unit prices far from the vendor's history
  (`GET /supplier-products?vendor_id=` shows `last_price`) → show both and ask.
- Over-applying, cross-currency, or an outbound payment aimed at a customer
  invoice are all 409s that name the reason. Read them; do not retry the same
  numbers.

## Settling from our account at the vendor

When their invoice is charged to our standing account there and our prepayment
is already deposited, settle in one atomic call on the prepayment: negative
line off the account, positive line onto their (purchase-direction) invoice —
the mirror of the receivables transfer, with our OUTBOUND payment as the deposit.
`GET /billing-accounts/{id}/detail` lists the charged POs and invoices and what
remains drawable. What the deposit does not cover is settled by a fresh
outbound payment applied directly to the invoice.

## Paying Under A Contract

Before an outbound payment to a vendor with a contract, read the clause:
`GET /contract-terms?contract_id=&term_type=payment_terms` (and
`deposit`). A deposit is an outbound payment carrying `contract_id` with
nothing yet to apply it to; later invoices under the same contract carry
it too, so `GET /contracts/{id}/execution` shows paid against invoiced.
Pay what the clause says, on the event it names — never a round number
because the invoice arrived.

## What This Skill Never Does

- Decide that a three-way-match gap is acceptable. It reports the facts and
  applies the workspace's stated rule; silence in the definition means ask.
- Approve its own payment, or move a payment past `submitted`.
- Blank or alter a supplier's invoice number to get past the duplicate check.
- Touch the purchase order's status or its receiving facts (that is
  `$oryh-purchase-order`).
- Edit or delete a settlement row.
- Import history — that is `$oryh-data-migration` (`POST /invoices/bulk`,
  `POST /payments/bulk`).

## Reference

- [references/api.md](references/api.md): every endpoint, the match block's
  fields, and the guards with the exact conditions that raise them.
