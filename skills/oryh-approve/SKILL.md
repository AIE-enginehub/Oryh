---
name: oryh-approve
description: Use when an approver's AI agent needs to execute a single approval action on any oryh document — 审批/驳回/退回 a timesheet, expense claim, purchase request, sales quotation, sales order, payment request, or invoice ("审批这张报销单"、"折扣太深，退回去重算"、"这笔款能不能付"、"把审批意见写回系统"). Records exactly one approval fact and completes the approver's own todo, after the review that document type demands: receipts for expenses, derived discounts for quotations, drift from the won quotation for orders, unpriced lines for purchase requests, and the payee account against the vendor's own record for payments. Never changes document status, never decides routing, never creates todos for others — advancing the flow is the workflow admin agent's job.
required_capability: approval.record
---

# Oryh Approve

**One approver, one action, two writes.** Read the document, record the
decision as a fact, close your own todo. That is the whole contract, and it
is the same for every document type — what changes between them is only
*what you must look at before deciding*.

This skill is deliberately small. Everything that moves a process forward —
status transitions, assigning the next approver, rework todos, marking paid,
clearing a rep to send — belongs to the flow skills
(`$oryh-timesheet-approval-flow`, `$oryh-expense-approval-flow`,
`$oryh-purchase-approval-flow`, `$oryh-quotation-approval-flow`,
`$oryh-order-approval-flow`), executed by the workflow admin agent.

## Trigger Examples

- "审批这张工时单 / 报销单 / 采购申请 / 报价单 / 订单"
- "看看这笔报销的发票对不对"
- "折扣给得太深，退回去重新算"
- "合同没签完，这张订单先驳回"
- "把审批意见写回 oryh"

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"          # the approver's own user-bound key
  approval_step:
    entity_type: "expense_claim"  # timesheet_header | expense_claim | purchase_request | sales_quotation | sales_order
    entity_id: "document-id"
    todo_id: "todo-id"            # the approver's own open todo for this document
    action: "approved"            # approved | rejected | returned | commented
    comment: "amounts match the receipts"
    acted_at: "2026-07-11T09:00:00Z"
    round_no: 1                   # copy from the todo's metadata
    sequence_no: 2                # copy from the todo's metadata
    approver_role: "manager"
```

`round_no` / `sequence_no` come from the todo the workflow admin created
(`metadata.round_no` / `metadata.sequence_no`). Reusing them makes retries
idempotent: posting the same action twice returns the already-recorded fact.

## Steps

{{include:_common/fewer-round-trips.md}}

1. **Read context** — the document's own `/detail`, which returns the lines,
   the totals, and the prior approval trail in one call:

   | 单据 | `entity_type` | detail endpoint |
   |---|---|---|
   | 工时表 | `timesheet_header` | `GET /timesheet-headers/{header_id}/detail` |
   | 报销单 | `expense_claim` | `GET /expense-claims/{claim_id}/detail` |
   | 采购申请 | `purchase_request` | `GET /purchase-requests/{request_id}/detail` |
   | 销售报价 | `sales_quotation` | `GET /sales-quotations/{quotation_id}/detail` |
   | 销售订单 | `sales_order` | `GET /sales-orders/{order_id}/detail` |

2. **Review what this document type demands** — see the section below. This
   is the part that is not mechanical, and it is the reason a human approver
   exists in the flow at all.

3. **Record the fact** — exactly one:

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

`approver_id` is filled by the server from the authenticated user — do not
self-report it. Allowed actions: `approved`, `rejected`, `returned`,
`commented` (an objection that does not decide).

4. **Complete the approver's own todo**: `PATCH /todos/{todo_id}` with
   `{"status": "completed"}` — needs `todos.complete_own` (the default member
   role has it); a 403 here is role configuration, not something to retry.

That is all. The document stays `submitted`; once this todo is completed it
re-enters the workflow admin's queue, which reads the new fact and decides
what happens next — next approver, rework todo for the submitter on
`returned`, or the final status.

## What Each Document Type Demands

**工时表 (`timesheet_header`)** — entries, hours, and the period. Nothing is
derived and there is no evidence to fetch; judge the hours against what the
period should hold.

**报销单 (`expense_claim`) — the evidence.** Every line should trace to a
receipt: fetch every item's `attachment_id` **in one batch** —
`GET /attachments/{id}/content` per receipt, all sent together, not one claim
line at a time — and read them. Verify amount, date, and merchant against the item; note items
with no receipt at all. Discrepancies belong in the `comment` and usually mean
`returned`, not `approved`. **Never approve without having looked at the
receipts.**

**采购申请 (`purchase_request`) — the unpriced lines.** Check quantities and
prices against the stated purpose; open quote files via
`GET /attachments/{id}/content` when present; compare priced lines against the
catalog `list_price` (`GET /products/{product_id}`, or the variant's own via
`GET /product-skus/{sku_id}`) when the line is cataloged. The quote files and
the catalog lookups are independent of each other — **send them as one
batch**, once, rather than walking the lines. `unpriced_item_count`
and `pending_sku_count` say what is still open — **decide knowingly**: approve
within a stated budget/配比 expectation, or `returned` for sourcing/细化. Put
what you relied on in the `comment`; never approve unpriced lines silently.

**销售报价 (`sales_quotation`) — the money facts are derived, and the
commitment is outward.** Nothing stores a discount rate: each line carries
`list_price_snapshot` (catalog truth at quoting time) and `unit_price` (what
the rep wants to offer) — the discount is the gap, and only YOU judge whether
it is acceptable. Line by line:
  - Derived discount: `1 − unit_price / list_price_snapshot` per cataloged
    line. Uncataloged lines have no snapshot — the discount is not derivable;
    say so in the comment instead of pretending.
  - Gift lines (`is_gift: true`) are 0-value by design — judge whether the
    giveaway itself is acceptable, not the "discount".
  - Header gap: the declared `total_amount` vs `computed_total`. 抹零 is
    normal; a material gap is an extra discount and must be judged as one.
  - Validity: a `valid_until` far out locks the price in for that long.
  - Terms: payment/delivery terms are commitments too (月结60天 is financing
    the customer).
  - `revisions` with `revision_no > 1` means the customer already negotiated —
    compare against the superseded revision to see what moved.

  Once you approve, the rep sends this document to a customer: a wrong price
  approved here is a price the company has offered.

**销售订单 (`sales_order`) — it should match its won quotation.** `/detail`
returns the linked quotation's **header** beside the order (totals, terms,
quote number); for line-level comparison fetch
`GET /sales-quotations/{quotation_id}/detail`. Price drift, changed terms, a
missing `contract_no` on a contract-required tenant, or a `ship_to_address`
that does not match are exactly what this node exists to catch before goods
move. Drift must be **named in the comment** (合理的补充条款 vs 私自改价).

**付款申请 (`payment`) — the account is the attack surface.** This is the one
node where the standing fraud is aimed directly at you: 改单诈骗 works by
changing the bank account on an otherwise genuine invoice, and everything else
about the request looks right. Before approving:
  - **Compare `counterparty_account` on the payment against the account on the
    vendor's own record** (`GET /vendors/{vendor_id}`). A mismatch is not a
    typo to be tolerated — it is the thing this check exists for. Say so in the
    comment and `returned` it; a changed account is confirmed out of band with
    the supplier, never over the same email thread that carried the invoice.
  - The bills it settles: each `GET /invoices/{invoice_id}/detail` reports
    `outstanding_amount`. Paying more than is outstanding is a 409 later, but a
    payment aimed at the wrong bill will pass the server and only fail here.
  - `order_match` on those bills, when they name a purchase order: the
    `receipt_variance` says the vendor billed more than arrived. Judge it —
    the server states the gap and deliberately does not decide it.
  - The amount against the workspace's tier rules, which the flow agent has
    already put in your todo's description.

**发票/开票申请 (`invoice`) — what leaves the building.** On the sales side you
are approving what the company will bill a customer: check `billed_total`
against the order it names and the terms behind `due_date`. On the purchase
side, the same `order_match` reasoning as above. Note that
`outstanding_amount` is derived from the settlement ledger — never treat a
`paid` status as proof that money arrived.

## What This Skill Never Does

- `PATCH` the document — status transitions are the workflow admin's write.
  That includes `paid` on a claim, `ordered` on a request, and `/send`
  or `/close` on a quotation (those are the rep's).
- `POST /todos` — assigning work to anyone (including rework for the
  submitter, sourcing for procurement, or fulfilment for the warehouse) is
  routing.
- Decide who approves next or whether the flow is complete.
- Contact a customer or touch an outbound document.
- Approve the things listed above without naming them in the `comment`:
  missing receipts, unpriced lines, deep or non-derivable discounts, material
  total gaps, drift from the won quotation.

## Reference

- [references/api.md](references/api.md): request templates, the action
  catalog, and the per-type read endpoints.
