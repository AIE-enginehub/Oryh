---
name: oryh-order-submit
description: Use when a salesperson's AI agent needs to record, update, query, or submit that person's own sales order in oryh — typically right after a quotation was accepted ("客户签了，下单吧"), and afterwards to keep fulfilment facts current ("发货了，单号SF…"、"客户签收了"). Also records orders arriving from external channels ("把天猫这单录进来"、"京东订单同步"、"Amazon order came in"): dedup by the platform's order number, translate platform product ids through the external product map, link the external number to the oryh order. Also records customer RETURNS ("买家退货了"、"这单要退两件"、"天猫退款单同步"): a return is an order-table row with order_kind=return linking its original order, running the e-commerce return lifecycle (申请/寄回/收货/验货/退款). Records the order (usually from the won quotation's lines), submits it for confirmation, and maintains logistics/delivery FACTS as fields; status transitions belong to the flow admin. Requires order.submit_own.
required_capability: order.submit_own
---

# Oryh Order Submit

Record and maintain the principal's own sales orders. The credential is the identity: the server only accepts writes for the employee linked to this key. An order is the fulfilment side of a won quotation — **you write facts (lines, tracking numbers, dates); the flow agent moves the status** (`confirmed → shipped → signed` by default; service tenants rename the back half).

**Not for historical migration.** A workbook of past orders belongs to
$oryh-data-migration. This skill records ONE order the principal is placing
now.

## Trigger Examples

- "City First signed — raise the order from the quotation"
- "The order shipped, tracking SF3021…"
- "The customer signed for it" / "when does it arrive?"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=sales_order` — what a valid order must carry (a contract number, a ship-to address, approval before shipping, and the like), current as of this moment. Never invent requirements.
3. **From the won quotation** (the normal path): `GET /sales-quotations/{id}/detail` of the accepted quotation → `POST /sales-orders` with `quotation_id` (the quote number snapshot backfills automatically), the customer fields, `ship_to_address`, `contract_no`, and `title` — the
a channel order names the front it came through: `GET /stores?source=tmall`
(the platform key, lowercase) finds the storefront and its id goes in
`store_id` — an offline sale names the shop the same way. The
customer's people live in `GET /customer-contacts?customer_id=` when you
need who to name in `contact_name` (the snapshot stays free text), and the
customer's negotiated terms in `GET /customer-products?customer_id=` — on a
no-quotation order, a line's price for a customer with an `agreed_price` is
that price unless the principal says otherwise, and an item code on their
paperwork resolves through `customer_product_code` there. Omit `order_no` for the server's `SO-NNNNNN`, or pass the tenant's own convention. Mirror the quotation's lines **in the same create** — the `items` array rides `POST /sales-orders`, one call and one transaction (prices carry over; `promised_date` per line when a delivery date was promised). `POST /sales-order-items` remains for adding a line to an existing draft. An order with no quotation behind it is also legal — snapshots stand alone.
4. **Reuse before create**: `GET /sales-orders?quotation_id={id}` and `?employee_id={me}&status=draft` — one won quote, one order; retries must not duplicate. A `returned` order is also reused: fix what the rework todo's `description` and the latest `returned` record's `comment` name, resubmit, then complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`) — while it stays open, the order is invisible to the flow admin's work queue.
5. **Say the gap out loud before submitting**: `GET /sales-orders/{id}/detail` returns `quote_drift` whenever a quotation is linked — `{quote_total, order_total, amount, percent, quote_basis, order_basis}`, computed by the server against a quotation that can no longer change. **Do not compute it yourself and do not skip it**: if `amount` is not 0, read it to the person in the read-back — "quoted 108,800, this order 120,000, higher by 11,200 (+10.29%)" — and say why, in their words, before `/submit`. The tenant's workflow definition (step 2) is what says whether that gap needs an approval node; the server does not refuse it, so an undisclosed overcharge reaches the customer with nobody having decided it should.
6. **Submit**: `POST /sales-orders/{id}/submit` after an explicit read-back (lines, the drift above, ship-to, promised dates). The flow agent calibrates and confirms — tenants without order ceremony get `confirmed` immediately per their definition.
7. **Fulfilment facts, as they happen** (PATCH fields on your own order — never `status`):
   - Shipping: `logistics_company` + `logistics_tracking_no` on the header
     for the simple one-parcel case; when the warehouse files freight legs,
     `GET /shipments?sales_order_id={id}` shows every parcel with its own
     carrier, tracking and status — read it before telling the customer
     where their goods are
   - Sign-off and delivery: the flow agent stamps the transition; you report the fact in conversation and keep `remarks` honest
   - A change of delivery date: `promised_date` on the header, or on the line
8. **Read back**: `GET /sales-orders/{id}/detail` — items, adjustments, `adjusted_total` vs declared `total_amount`, the linked quotation, Tax, freight, whole-document discounts and rounding record as adjustments (`POST /sales-order-adjustments`, same contract as the quotation side: signed amount, typed, optional `order_item_id`, editable only while the order is) — so the declared total is explained, not asserted.

## Charging the order to a billing account

If the customer pays by their billing account, set `billing_account_id` on the
order at creation. The order OCCUPIES the account's credit from that moment —
that is the point: between order and invoice (two days waiting on a restock, or
months in a B2B deal),
the same balance must not back two orders. One rule, no branches:

> pay from the account → charge the order; invoice from a charged order → the
> same account travels with it; an invoice without the account does not release
> the occupation.

A 409 on the charge is the account refusing, with three numbers (balance +
limit − occupied). Report them to the principal verbatim and offer the three
ways out — deposit more, raise the limit, shrink or split the order. Never pick
one yourself; never retry the same charge hoping.

If the order is later cancelled *but kept on file*, clearing
`billing_account_id` is the release — a plain PATCH, part of the cancellation,
not optional. Line removals and deletion release by themselves.

## Orders That Arrive From Somewhere Else

An order from Tmall, JD, Amazon, a mini-program, or a small vendor's site
carries that system's numbers, and recording it means two translations. Both
are server-backed lookups — never memory, never guesswork:

1. **Dedup by the platform's order number FIRST**:
   `GET /external-document-links?source=tmall&external_kind=order&external_no={their number}`.
   Rows mean this platform order is already recorded — go to the linked
   documents instead of creating a twin. The server's unique constraint
   catches a duplicate LINK; only this check prevents a duplicate ORDER.
2. **Translate the lines through the map — AS OF the order's date**:
   for each external line,
   `GET /external-product-maps?source=tmall&external_product_id={their id}&at={the ORDER's date}`.
   `at` matters because listings swap goods while keeping their platform id
   (a merchant defends a promotion slot), and order sync lags — an order
   placed Tuesday and imported Thursday must translate against what the
   listing meant on TUESDAY. Add `external_sku_id` when the platform
   distinguishes SKUs. Each row contributes `quantity × line qty` of its
   `product_id` — a bundle listing returns several rows, and that IS the
   translation. **No rows means the listing is unmapped on that date: say
   so and stop translating that line.** The map is catalog curation
   ($oryh-master-data); ask the principal whether to wait for the mapping
   or record the line in words (`description`, no `product_id`) with a todo
   for the catalog admin. An order dated exactly ON a swap boundary
   resolves to the newer meaning — when the amounts matter, confirm that
   day's orders with a person.
3. **Create the order as above**, and keep the platform's own facts —
   buyer nickname, platform status, platform line ids — in `custom_fields`,
   where a claim this database cannot check belongs.
4. **Write the link**: `POST /external-document-links` with `source`,
   `external_kind: "order"`, `external_no`, `entity_type: "sales_order"`,
   `entity_id`. Splits and merges are rows, not special cases: one platform
   order fulfilled as two oryh orders is two links; three platform orders
   shipped as one is three links against the same order.
5. **Returns**: record the return as its own row in the SAME orders
   collection — see the next section — and tie the platform's return number
   to that row with `external_kind: "return"`.

`source` is lowercased by the server ("Tmall" and "tmall" are one channel),
but keep your own writes consistent anyway.

## Returns Are Order Rows With Their Own Life

A customer return is a row in `/sales-orders` with `order_kind: "return"`,
pointing at the order it reverses:

```json
POST /sales-orders
{
  "employee_id": "my-employee-id",
  "order_kind": "return",
  "original_order_id": "the-order-being-reversed",
  "customer_id": "customer-id",
  "title": "TM order 101 — buyer returns 2 of 3 cups",
  "items": [{"line_no": 1, "product_id": "cup", "quantity": 2, "unit_price": 39.0}]
}
```

- **One order, many returns**: each partial return is its own row naming the
  same `original_order_id`. "All returns of this order" is
  `GET /sales-orders?original_order_id={id}`; "all returns" is
  `?order_kind=return`. The server allocates `SR-NNNNNN` beside the orders'
  `SO-`.
- **The return runs its own machine** — by default `draft → submitted →
  approved → in_transit → received → inspected → refunded` (rejected /
  cancelled as exits), which is the e-commerce shape: customer applies,
  merchant approves, buyer ships back, warehouse receives, inspected into
  stock, refunded. Refund-before-parcel for cheap
  goods is legal (`approved → refunded`). The ORDER machine's states are not
  legal on a return and vice versa; the tenant reshapes either machine
  independently, one sentence to the admin, like every builtin. A return
  synced from a platform mid-flow is created directly in its current state.
- **The lines are the goods coming back** (positive quantities), the total
  is the refund amount. `original_order_id` may be omitted when nobody knows
  the order yet — record reality first, `PATCH` the linkage when it is
  identified. An original that is itself a return is refused: a return
  reverses an ORDER.
- **The buyer's send-back tracking is YOUR fact to record**: PATCH the
  return row's `logistics_company` / `logistics_tracking_no` when the buyer
  reports shipping it back — that is what the flow admin advances
  `in_transit` from. Facts, never `status`, same as orders.
- **What a return never does**: charge a billing account (the refund is a
  payment document — the finance skills record it), or carry a
  `quotation_id`. The server refuses both.
- **The rest of the loop lives where it always lives**: goods back into
  stock is a `returned` inventory movement naming this return row
  ($oryh-inventory); money back is a payment; the platform's aftersale
  number links this row via `/external-document-links` with
  `external_kind: "return"`, `entity_type: "sales_order"`.
- Order states like paid-but-unshipped are the ORDER machine's business: the
  shipped default is `draft → submitted → confirmed → shipped → signed`, and
  an e-commerce tenant tells the admin agent once — "rename the order
  states to unpaid / paid / shipped / signed" — to rename or extend it.
  Never hard-code state
  names; read `GET /workflow-definitions` and the machine, as step 2 says.

## What This Skill Never Does

- PATCH `status` (flow admin's write — no self-confirmation, no self-sign-off).
- Invent tracking numbers, dates, amounts, or a `contract_no` the principal never stated — a contract number is a legal fact, and an order can be created without one; ask, or leave it empty. Change prices away from the won quotation only by saying so out loud.
- Create orders for anyone else, or touch the warehouse's fulfilment todos.
- Guess a product mapping the map does not hold, or edit the map itself — translation reads it; curation is the catalog admin's.

## Reference

- [references/api.md](references/api.md): request templates.
