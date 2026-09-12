---
name: oryh-order-submit
description: Use when a salesperson's agent records, updates or submits their OWN sales order in oryh — after a won quotation ("客户签了，下单吧"), fulfilment facts ("发货了，单号SF…"), channel orders ("把天猫这单录进来") and customer returns ("买家退货了"). Facts only; status transitions belong to the flow. Requires order.submit_own.
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
- "The customer signed for it"
- "Sync the JD order"
- "Two pieces of this order are coming back"
- "Sync the Tmall refund order"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/fail-fast-on-master-data.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=sales_order` — what a valid order must carry (a contract number, a ship-to address, approval before shipping, and the like), current as of this moment. Never invent requirements.
3. **From the won quotation** (the normal path) — **after step 4's reuse check, which goes out in the same wave as step 2**: `GET /sales-quotations/{id}/detail` of the accepted quotation → `POST /sales-orders` with `quotation_id` (the quote number snapshot backfills automatically), the customer fields, `ship_to_address`, `contract_no`, and `title`. Omit `order_no` for the server's `SO-NNNNNN`, or pass the tenant's own convention. Mirror the quotation's lines **in the same create** — the `items` array rides `POST /sales-orders`, one call and one transaction (prices carry over; `promised_date` per line when a delivery date was promised). `POST /sales-order-items` remains for adding a line to an existing draft. An order with no quotation behind it is also legal — snapshots stand alone.
   - **The storefront**: a channel order names the front it came through —
     `GET /stores?source=tmall` (the channel's code, lowercase) lists the
     stores under that channel and the right one's id goes in `store_id`.
     Two stores under one channel is normal (two Amazon storefronts): the
     export's shop name or account says which; when it does not, ask —
     never pick the first. An offline sale names the shop the same way.
   - **The lines**: a channel line names its product by whatever the export
     carried — `GET /external-product-maps?source=tmall&external_product_id=…&at={order date}`
     when it has an id, `…&external_name={title as printed}&at=` when it has
     only the title (the common case — pass the title verbatim; matching
     forgives spacing and case, and `external_sku_id` carries the spec
     text). No row → the line is unmapped: say so and run the import loop
     below, never guess a product from a look-alike name.
   - **The terms travel**: an order created with `quotation_id` inherits the quotation's `payment_terms` and `delivery_terms` unless you restate them — say them in the read-back either way. Read the quotation's `/detail` → `approval_records` and `prior_approval_records` for conditions an approver attached ("put the 4-hour after-sales response in the contract") and carry them into `delivery_terms` / `contract_no`'s contract; a condition is part of what was won.
   - **The customer's people and terms**: `GET /customer-contacts?customer_id=`
     when you need who to name in `contact_name` (the snapshot stays free
     text); `GET /customer-products?customer_id=` for negotiated terms — on
     a no-quotation order, a line's price for a customer with an
     `agreed_price` is that price unless the principal says otherwise, and
     an item code on their paperwork resolves through
     `customer_product_code` there.
4. **Reuse before create** (send with step 2, before any create): `GET /sales-orders?quotation_id={id}` and `?employee_id={me}&status=draft` — one won quote, one order; retries must not duplicate. An existing order for the quotation means update it, never a second create. A `returned` order is also reused: fix what the rework todo's `description` and the latest `returned` record's `comment` name, resubmit, then complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`) — while it stays open, the order is invisible to the flow admin's work queue.
5. **Say the gap out loud before submitting**: `GET /sales-orders/{id}/detail` returns `quote_drift` whenever a quotation is linked — `{quote_total, order_total, amount, percent, quote_basis, order_basis}`, computed by the server against a quotation that can no longer change. **Do not compute it yourself and do not skip it**: if `amount` is not 0, read it to the person in the read-back — "quoted 108,800, this order 120,000, higher by 11,200 (+10.29%)" — and say why, in their words, before `/submit`. The tenant's workflow definition (step 2) is what says whether that gap needs an approval node; the server does not refuse it, so an undisclosed overcharge reaches the customer with nobody having decided it should.
6. **Submit**: `POST /sales-orders/{id}/submit` after an explicit read-back (lines, the drift above, ship-to, promised dates). The flow agent calibrates and confirms — tenants without order ceremony get `confirmed` immediately per their definition.
7. **Fulfilment facts, as they happen** (PATCH fields on your own order — never `status`):
   - Shipping: **one place for a tracking number.** When the warehouse files
     shipments (`GET /shipments?sales_order_id={id}` answers), the number
     lives on the shipment and you do not copy it onto the header; only when
     nobody files shipments does `logistics_company` + `logistics_tracking_no`
     go on the header. Read the shipments before telling the customer where
     their goods are
   - Sign-off and delivery: the flow agent stamps the transition; you report the fact in conversation and keep `remarks` honest. When the business moment differs from the PATCH's own — goods left on the 21st, signed on the 23rd — write `shipped_at` / `signed_at` explicitly; the stamp only fills them when they are empty
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

## Importing A Channel Order: The Loop

An export from Tmall (JD, Amazon, a mini-program, a small vendor's site) is
a spreadsheet of platform order numbers and product TITLES, and recording
it means two translations — both server-backed lookups, never memory, never
guesswork. The loop, per order, in this order — reads first, the person in
the middle, writes last:

1. **Dedup by the platform number FIRST**:
   `GET /external-document-links?source=tmall&external_kind=order&external_no={theirs}`.
   A hit means this order is already ours — go to the linked documents and
   skip it; never record it twice because the export came twice. The
   server also refuses to link a number that already names another order
   of ours (409 naming it) — but by then the duplicate order exists, so
   this read comes first.
2. **Translate each line through the map first — AS OF the order's date**:
   `GET /external-product-maps?source=tmall&external_name={title verbatim}&at={the ORDER's date}`
   (spec text in `external_sku_id` as the export prints it — the server
   folds case and width, not the platform's label; when the export carries
   listing ids, pass `external_product_id=` AND the title, and the server
   answers with both the id-keyed rows and the title-keyed ones a desk
   wrote earlier). A hit is the answer, confirmed once by a person on an
   earlier import; use it without asking again. Rows that differ only in
   `external_sku_id` are spec variants, not a bundle — look up with the
   spec. `at` matters because listings swap goods while
   keeping their id or title (a merchant defends a promotion slot) and
   order sync lags — an order placed Tuesday and imported Thursday must
   translate against what the listing meant on TUESDAY; an order dated
   exactly ON a swap boundary resolves to the newer meaning, so when the
   amounts matter, confirm that day's orders with a person. Each row
   contributes `quantity × line qty` of its `product_id` — a bundle
   listing returns several rows, and that IS the translation.
3. **Only when the map is silent, ask the catalog for candidates**:
   `GET /product-matches?title={title}&limit=5` ranks active products by
   how much of the title's vocabulary they share. It is a shortlist, not
   a decision. **This workspace's own matching rules** (how its titles
   are built, which words mean nothing, what a bundle looks like) live in
   $oryh-product-matching's calibration — when that skill is in your
   bundle, hand the unmapped lines to it and take its translation back;
   the loop below is the same procedure without the rules. Collect the unmapped lines of the whole batch and ask the
   person ONCE, showing each title with its top candidates (code, name,
   spec, score): "Insulated cup 500ml sakura pink → CUP-500 Insulated cup
   500ml (0.83)? or CUP-350?" Never pick a look-alike yourself,
   and treat "none of these" as an answer — that listing waits for the
   catalog desk; meanwhile the line may be recorded in words
   (`product_name_snapshot` as printed, no `product_id`; the order stays a
   draft) if the principal prefers that to waiting. Your grant cannot
   hand the catalog desk a todo: name the unmapped listings in your
   read-back so the person can. When the person confirms later, `PATCH
   /sales-order-items/{id}` with `product_id` (and `sku_id`) fills the line
   in.
4. **Record what the person confirmed** so the next import skips step 3:
   `POST /external-product-maps {"source": "tmall", "external_name":
   {title verbatim — never tidied}, "external_sku_id": {spec as printed or ""},
   "external_product_id": {listing id when the export has one},
   "product_id": …, "sku_id": {when the pairing is a variant}, "quantity": …}`.
   Your grant writes undated map rows for exactly this reason, and may
   correct or withdraw one; a bundle is one row per component with its
   quantity, written together. Effective-date swaps stay with
   $oryh-master-data. The one thing this step must never do:
   Writing a map without the person's confirmation.
5. **Create the order** with the translated lines, `store_id` from
   `GET /stores?source=tmall` (several stores under one channel → the
   export says which, or you ask; each store row lists its
   `fulfilment_facilities`, priority 1 first — the warehouse's standing
   answer, not yours to override), the buyer in `customer_name_snapshot`
   (a buyer who is a known account: `GET /customers?keyword=` and set
   `customer_id` too), the platform's `currency` with unit prices in it
   (the server snapshots no list price when the catalog prices the goods
   in another currency — a CNY list price beside a USD unit price is not
   a discount), and the platform's own facts — buyer nickname, platform
   status, platform line ids, the platform's own timestamp with its time
   zone — in `custom_fields`, where a claim this database cannot check
   belongs. A line's SKU shows as `sku_id`; to print its code in your
   read-back, `GET /product-skus?product_id=`. Then **link the platform
   number**: `POST /external-document-links` with `source`, `external_kind:
   "order"`, `external_no`, `entity_type: "sales_order"`, `entity_id`. The
   server refuses the same number against a second order (409 naming the
   first) — a duplicate import stops here — unless you send `split: true`,
   which is how a deliberate split is recorded: one platform order
   fulfilled as two oryh orders is two links, the second declared a split;
   three platform orders shipped as one is three links against the same
   order. A seller's credential links its own orders only.
6. **Returns**: record the return as its own row in the SAME orders
   collection — see the next section — and tie the platform's return
   number to that row with `external_kind: "return"`.

Read back the batch at the end: orders created, lines translated from
the map versus confirmed today, listings still unmapped — in that order.
`source` is lowercased by the server ("Tmall" and "tmall" are one channel),
but keep your own writes consistent anyway.

## When The Warehouse Cannot Ship What Was Confirmed

A confirmed order is past its machine's editable states (the shipped
default closes the lines after `draft` / `returned`; read the machine, the
workspace may have moved that line). When the warehouse then finds it cannot
ship the order as written — short stock, a spec the buyer changed on the
phone, an address the courier refuses — nothing on it can be edited, and
the honest record is: **that order is cancelled, and a new one replaces
it.** The server does both in one call so the link is a fact, not a remark:

```text
POST /sales-orders/{order_id}/revise
{"reason": "warehouse short; the customer now wants 2"}
```

- The 201 is a fresh **draft** copied from the source — header, lines,
  adjustments, `custom_fields`, the platform numbers it was imported under
  — with `supersedes_order_id` naming the source. The source is moved to
  the machine's `cancelled` in the same transaction, its open todos closed,
  the credit it occupied released for the draft to occupy.
- **Edit the draft, then submit it** exactly as a new order: change the
  lines, the address, the promised date; read back; `/submit`. The flow
  agent confirms it under the tenant's definition like any other order.
- **Decide by the state, not by habit.** An order still in an editable
  state is edited in place — `/revise` refuses it (409) and says so. A
  return is reversed, never revised (422). An order a shipment already
  names is partly on its way: that is a return or a further shipment
  ($oryh-shipping), and `/revise` refuses it (409).
- **Follow the link both ways**: the source's `/detail` carries
  `superseded_by`; `GET /sales-orders?supersedes_order_id={source}` lists
  what replaced it. When a person asks about the platform number, the
  external-document link now names both rows — the live one is the draft
  or whatever it became.
- Never do this by hand — a raw `cancelled` PATCH is the flow admin's write,
  and a separate `POST /sales-orders` has no column to say what it replaces.

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
  stock is the return parcel's inbound shipment posting against this
  return row ($oryh-shipping); money back is a payment; the platform's aftersale
  number links this row via `/external-document-links` with
  `external_kind: "return"`, `entity_type: "sales_order"`.
- Order states like paid-but-unshipped are the ORDER machine's business: the
  shipped default is `draft → submitted → confirmed → shipped → signed`, and
  an e-commerce tenant tells the admin agent once — "rename the order
  states to unpaid / paid / shipped / signed" — to rename or extend it.
  Never hard-code state
  names; read `GET /workflow-definitions` and the machine, as step 2 says.

## What This Skill Never Does

- **Move stock.** "ship it" is a SHIPMENT — the parcel filed against the order,
  walked and posted once (`$oryh-shipping`, `shipment.manage`) — never a
  ledger row, and this skill files neither. When your bundle carries
  `$oryh-shipping`, hand the order over to it; when it does not, the
  person's role does not ship, and the shipping todo the flow assigns goes to
  whoever's does. The order's `logistics_*` fields are for workspaces that
  file no shipments and record only the tracking fact.
- PATCH `status` (flow admin's write — no self-confirmation, no self-sign-off).
- Invent tracking numbers, dates, amounts, or a `contract_no` the principal never stated — a contract number is a legal fact, and an order can be created without one; ask, or leave it empty. Change prices away from the won quotation only by saying so out loud.
- Create orders for anyone else, or touch the warehouse's fulfilment todos.
- Guess a product mapping the map does not hold, or write a map row nobody confirmed. Order desks may POST title-keyed map rows after a person confirms the candidate; id-keyed rows, edits, effective-date swaps and deletion stay with $oryh-master-data.

## Reference

- [references/api.md](references/api.md): request templates.
