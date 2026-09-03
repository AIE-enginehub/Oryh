---
name: oryh-quotation-submit
description: Use when a salesperson's AI agent needs to draft, update, query, submit, send, close, or revise that person's own sales quotation in oryh. Covers natural-language quote capture, matching the customer and products against master data (both optional), list-price snapshots and discount facts, gift lines, per-line tax rates and lead times, the negotiated header total (抹零), sending to the customer, recording the outcome (成交/流失/过期), and issuing a new revision when the customer negotiates. It records the salesperson's facts only — internal approval routing belongs to other roles.
required_capability: quotation.submit_own
---

# Oryh Quotation Submit

Record and drive the principal's own sales quotation through its whole life. The credential is the identity: the server only accepts writes for the employee linked to this key, so never ask "for whom" — it is always the principal.

A quotation is an **outbound document**: unlike a requisition, what you write here is what the customer will read. Two consequences shape everything:

- **A sent quotation is immutable.** Fixing a price after it went out is not an edit — it is a new revision (`POST .../revise`), same quote number, `revision_no + 1`. The old revision stays as the fact it was.
- **The discount is derived, never stated.** Each line carries `list_price_snapshot` (the catalog price at quoting time, captured automatically for cataloged products) and `unit_price` (what you actually quote). Approvers and the flow agent judge the gap; you never write a "discount rate" anywhere.

Legitimately uncertain things, and the record is honest about all of them:

- **Customer**: may be in master data, or a brand-new prospect. Match read-only; no match is fine — `customer_id` stays null and the free-text `customer_name_snapshot` stands. Never create customers.
- **Product**: cataloged or free text, same as purchasing. Uncataloged lines have no `list_price_snapshot` — that is a fact, not an error.
- **Header total**: `total_amount` is the negotiated document total (rounding 100,237 down to 100,000, say). Omit it and the line sum IS the total. Never "fix" the gap silently — it is a deliberate commercial fact. Record WHY it differs as adjustments (`POST /sales-quotation-adjustments`: rounding → `rounding`, a whole-document promotion → `promotion`, tax and freight → `tax`/`shipping`) so `adjusted_total` in the detail matches the declared total — an unexplained residual is exactly what calibration bounces back.
- **Gift lines**: "include two samples" → `is_gift: true`, `unit_price: 0`. The flag keeps giveaways from reading as 100% discounts.

**Not for historical migration.** A workbook of past quotations that
already ended belongs to $oryh-data-migration — it keeps their original
numbers, imports terminal states as-is, and handles hundreds of thousands of
rows. This skill files ONE quotation the principal is working on now.

## Trigger Examples

- "Quote this company" / "Draw up a quotation"
- "The quotation is approved — send it to the customer and mark it sent"
- "The customer says it is too expensive; drop the unit price to 95 and issue another version"
- "The customer signed — close the quotation as won"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

Everything else comes from conversation: who the customer is, what to quote, at what price, valid until when.

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=sales_quotation` — the tenant's natural-language rules, current as of this moment. Read what it requires of a submission (discount authority, a maximum validity period, mandatory tax rates or lead times, and the like) and let it shape the conversation from the first question. No definition, or nothing about filing → only the universal checks apply; never invent requirements. Routing rules in the same document belong to other roles — ignore them.
3. **Reuse before create**: `GET /sales-quotations?employee_id={me}&status=draft` — reuse an open draft for the same deal; retries must not duplicate. A `returned` quotation is also reused: fix it, don't recreate — the rework todo's `description` and the latest `returned` approval record's `comment` say exactly what to fix. After a successful resubmit, complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`; needs `todos.complete_own`, in the default member role) — while it stays open, the quotation is invisible to the flow admin's work queue.

4. **In-flight duplicate check**: `GET /sales-quotations?employee_id={me}&status=submitted` and `?status=sent` — an open quotation for the same customer and scope means revise or wait, not a second number. This is a conversation, not a hard stop.

   **Steps 2, 3 and 4 are one batch: the definition read, the draft query
   and both in-flight queries are four independent reads — send them in
   one turn.** They feed nothing into each other; sequencing them
   quadruples the wait for no reason.

5. **Match master data** (read-only, all optional — and ONE batch: the
   customer lookup and every line's product lookup go out together the moment
   the names are known from conversation):
   - Customer: `GET /customers?keyword={name}` or `?tax_id=`. Confident match → `customer_id` (name backfills the snapshot); otherwise the principal's words go in `customer_name_snapshot`. Per-quote contact fields (`contact_name/phone/email`) are THIS deal's buyer — may differ from the master record.
   - Product per line: `GET /products?keyword=`. A confident match auto-captures `list_price_snapshot` — quote your `unit_price` against it knowingly.
   - **A matched customer may have negotiated terms**: `GET /customer-products?customer_id=`
     in the same batch. An `agreed_price` on a quoted product is the price to
     quote — the price book is the rule, the agreement is that customer's
     exception; quote something else only by saying so out loud. Their
     `customer_product_code` is what THEIR paperwork calls the product.
   - SKUs need a product id, so they are the only second wave: for matched
     products with `has_skus: true`, `GET /product-skus?product_id=&status=active`,
     all of them together (same granularity rules as purchasing).
6. **Quotation — one call, lines included**: `POST /sales-quotations` with
   `employee_id`, `title`, customer fields, `valid_until`,
   `payment_terms`/`delivery_terms`, the principal's original words in
   `source_report_text`, **and the complete `items` array**: per line
   `line_no` (the printed order), `quantity`, `unit_price`, and when relevant
   `tax_rate` (mixed quoting, such as 13% on goods and 6% on services),
   `lead_time` (in stock, two weeks),
   `is_gift`. Explicit `list_price_snapshot` only when applying a special
   price list — the catalog capture is automatic, inline or not. Omit
   `quote_number` — the server allocates QT-NNNNNN — unless the tenant has
   its own numbering convention. `project_id` links project-based deals.
   One transaction: a bad line rolls the whole quotation back, so a retry
   never finds a half-built draft. The response echoes the lines as they
   landed — that IS the material for the pre-submit read-back.
   (`POST /sales-quotation-items` still exists for adding a line to an
   existing `draft`/`returned` quotation — a 409 there means revise instead.)
7. **Submit**: `POST /sales-quotations/{id}/submit` — only after the pre-submit read-back below got an explicit yes. Idempotent. Internal approval (if the tenant requires any) runs from here; a tenant with no rules gets it finalized by the flow agent without human nodes.
8. **The submitted approval fact is not yours to write.** `/submit` records it (`round_no` derived, `sequence_no=1`, `source=system`), so the trail opens with it whether or not this credential carries `approval.record`. Posting it anyway is harmless — the recorded fact comes back — but there is nothing to do here.
9. **Send**: once `approved`, render the customer-facing document from `GET /sales-quotations/{id}/detail` (lines in `line_no` order with prices, tax rates, lead times, terms, validity — the principal's own template if they have one), deliver it however the principal does, then `POST /sales-quotations/{id}/send` to record the fact. Idempotent.
10. **Outcome**: when the customer decides — `POST /sales-quotations/{id}/close` with `outcome: accepted|declined|expired` and an `outcome_note` (the agreed amount, or why it was lost). The win rate lives on these facts.
11. **Revision**: customer negotiates → `POST /sales-quotations/{id}/revise` (allowed from `approved`/`sent`). The old revision becomes `superseded`; you get a fresh `draft` with lines copied and catalog snapshots refreshed — adjust prices, then submit again (discount rules apply to the NEW numbers). Read back `GET .../detail` — its `revisions` array is the negotiation trail.

## Validate Before Writing

**Hard rules (the server rejects these; catch them in conversation first):**

- `quantity` > 0; every line needs a `product_id` **or** a free-text `product_name_snapshot`.
- Items only while `draft`/`returned`; sent means revise.
- `customer_id` / `product_id` / `sku_id` / `attachment_id` / `project_id` must be real records here — free text goes in snapshots, never a guessed id.
- Lifecycle is machine-guarded: submit from `draft`/`returned`, send from `approved`, close from `sent`, revise from `approved`/`sent`. A 409 names the legal moves.
- A tenant-supplied `quote_number` that already exists → 409; pick the next or let the server allocate.

**Tenant requirements (the flow agent returns violations; catch them in conversation first):**

- Whatever the step-2 definition requires. Typical shapes: a discount over X% needs a stated reason; validity may not exceed 30 days; the quotation must state whether prices include tax; free gifts need approval. The definition's own wording always wins over these examples.
- The definition is also where the tenant states whether quoted prices are tax-inclusive — put the convention in `remarks` so the printed document says it.

**Reasonableness (pause and ask before writing):**

- `unit_price` far below `list_price_snapshot` → show the derived discount ("list 120, quoted 85 — about 29% off"), confirm intent. The tenant's threshold decides who must approve it — flag, don't block.
- `total_amount` differing from the line sum by more than rounding (rounding is normal; 10% off the sum is a discount pretending to be rounding) → confirm, then record it as an adjustment of the right type rather than only prose in `remarks`.
- `valid_until` in the past or absurdly long → typo or intent? Ask.
- A zero price without `is_gift` → gift or mistake? One question.
- A customer name matching several customer records → list them, ask which.

**Pre-submit read-back:** echo the complete quotation — customer (or "new prospect, no record yet"), each line with quantity, price and derived discount (or "no list price"), tax rates if stated, gift lines, the line sum, the declared total and the gap if any, validity, terms — and get an explicit confirmation.

## What Happens Next (so you can answer the principal)

Submitted quotations sit in the flow agent's queue: calibrated against the step-2 requirements first (non-compliant ones come straight back as rework todos), then routed to whatever approvers the tenant's definition names — discount tiers key on the derived line discounts and the header-total gap. Once `approved`, sending is YOURS (step 9) — no one else touches the customer. `GET /approval-records?entity_type=sales_quotation&entity_id={id}` shows progress any time. Quotations past `valid_until` are swept to `expired` by the flow agent; closing the deal before that is step 10.

## What This Skill Never Does

- Approve its own quotation, decide routing, or PATCH the status raw (`/submit`, `/send`, `/close`, `/revise` are its only transitions).
- Create customers or products as a side effect.
- Edit a sent quotation — revise it.
- Invent a price, discount, or validity the principal didn't state.
- Send to the customer before the quotation is `approved`, or submit without the read-back.

## Reference

- [references/api.md](references/api.md): request templates.
