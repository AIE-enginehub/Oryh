---
name: oryh-shipping
description: Use when goods leave or arrive as a parcel or a truck in oryh — 销售发货/出库, 退货收件, 采购退货发出 — filing the shipment, walking it, posting it to stock once, closing the 发货 todo. Requires shipment.manage. "出库" IS a shipment, never a ledger row; positions, counts, holds and stock documents are oryh-inventory's.
required_capability: shipment.manage
---

# Oryh Shipping

A parcel or a truck is a `/shipments` document, and the shipment is the
ONLY way goods sold, returned or sent back to a vendor reach the stock
ledger: `POST /shipments/{id}/post-stock`, once. There is no other write.
When a person says "ship it" they mean this document — the goods, the carrier,
the tracking number, the posting — and never "subtract from the shelf".
An agent that heard "ship it" and wrote a bare stock row skipped the order, the
parcel and the trace; the server no longer offers that row to anyone.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/stay-current.md}}

## Trigger Examples

- "Ship SO-000012, SF Express, tracking SF123…" (file the leg, post it)
- "Ship these three orders today"
- "The two ribbons the customer returned have arrived" (the return's inbound parcel)
- "The batch going back to the vendor has left"
- "Has this order shipped?" (read: `GET /shipments?sales_order_id=`)

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_base_url: "{{ORYH_API_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

- Which document the goods belong to: a sales order (outbound), a sales
  RETURN row (inbound), a purchase RETURN row (outbound). Purchase-order
  goods arriving is `POST /purchase-orders/{id}/receive`
  ($oryh-purchase-order), not a shipment that posts.
- What moves: product (and SKU), quantity, and the stock POSITION it leaves
  or lands in — `GET /inventory-items?product_id=&sku_id=&facility=`.
- Carrier and tracking number, when known; they can be PATCHed on later.

## "Ship It" Is A Shipment

1. **Find the order and what it still owes**: `GET /sales-orders/{id}/detail`
   — `fulfilment[]` says per line what has shipped and what is
   `outstanding`; an order with nothing outstanding has been shipped
   already, however its status reads. The order must be in the state the
   tenant's definition ships from (usually `confirmed`); an order still
   `draft` or `submitted` is not yours to ship — say so.
2. **Choose the facility**: the store's standing answer (`GET
   /stores/{store_id}`, `fulfilment_facilities`, priority 1 first) or the
   one the person names; then the position holding the goods there.
   Goods only in a warehouse the store does not ship from is a question,
   not a silent cross-ship. Shipping less than ordered is a fact: ship
   what is there as its own leg, the rest stays `outstanding` in
   `GET /fulfilment-backlog` — that IS the shortage record; a remark on
   the leg is for the reader, never the only place it exists.
3. **File the leg**: `POST /shipments` `{direction: "outbound",
   sales_order_id, facility, carrier, tracking_no, items: [{product_id,
   sku_id?, quantity, inventory_item_id}]}`. Where the warehouse picks,
   `picklist_id` and NO items — the server copies the picked lines
   (picked quantities win, zero picks ship nothing) and refuses a picklist
   for another order.
4. **Walk it**: `PATCH /shipments/{id}` `draft → packed → shipped`, or
   `draft → shipped` where nobody packs — the machine allows both
   (tenant-renamable like every machine; lines editable in draft/packed).
   `shipped_at` stamps on the literal name.
5. **Post it, once**: `POST /shipments/{id}/post-stock`. Outbound issues,
   inbound receives (a leg linked to a RETURN row posts `returned`);
   every movement carries the shipment line as provenance plus the order
   link; the order's hold (a hold) is consumed in the same posting so
   availability is never deducted twice. `stock_posted_at` makes a second
   call a 409 — corrections are counter-documents, never re-posts. Lines
   without a position are reported `skipped_no_position`, never silently
   absorbed.
6. **Close your todo** (`PATCH /todos/{id}` `{"status": "completed"}`) in
   the same turn — posting stock does not close it for you — and read
   the order's `/detail` back: the flow agent advances the ORDER's status
   from your leg; you never PATCH the order.

Confirm before step 3 — the parcel's lines, the position, the carrier —
and again before step 5 when the leg was filed in an earlier turn: a
posting cannot be taken back.

## The Direction Matrix

`outbound`: shipping a sales order; sending a purchase RETURN back to its
vendor. `inbound`: a customer return's parcel (linked to the sales RETURN
row); a freight record beside a purchase order whose goods entered stock
through `/receive`. The linked row must agree with the direction, and the
server teaches the matrix on a mismatch.

**Never book the same goods twice.** Purchase-order goods enter stock
through `POST /purchase-orders/{po_id}/receive` — if they did, do not also
post-stock a shipment for them; that shipment is then a freight RECORD
(tracking, dates, status), not a stock mover. One physical movement, one
ledger entry, whichever door it came through.

## Where A Return's Goods Land

The inbound leg's line names the position the goods land in, and which
position is the tenant's own sentence in the sales_return definition
(`GET /workflow-definitions?entity_kind=builtin&object_type=sales_return`
— once per session, with the return's own reads): a quarantine the returns area, a
`RET-` lot, or — the definition silent — the original position, found
from the order's own issue (`GET /inventory-item-details?sales_order_id={original}&reason=issued`).
Creating the stated position on first use is $oryh-inventory's write; ask
that desk (or, holding `inventory.manage`, create it: facility, bin and
lot are free text). Moving goods the returns area → main after inspection is a
stock document (transfer document), not a shipment — $oryh-inventory posts it.

## Who Closes What After The Goods Leave

- **`received` on an outbound shipment** is the customer's sign-off, and
  the person who learns of it records it: the sales desk when the
  customer confirms (`PATCH` the shipment to `received`, `received_at` the
  real date), or you when the carrier's proof of delivery arrives. An
  order can be `signed` with its shipment still `shipped` — that is a
  fact nobody recorded yet, not a state to leave.
- **The "arrange shipment" todo** is yours: complete it after `/post-stock`.
- **A tracking number is recorded once**, on the shipment; the order
  header's `logistics_*` fields are for workspaces that file no shipments.

## What This Skill Never Does

- Write a stock movement by any path but `/post-stock` on a shipment.
  There is no generic ledger write; a shortfall, a damaged unit, a
  transfer are stock documents ($oryh-inventory), not a bigger or smaller
  parcel.
- Create positions, hold stock (`/reserve`), import counts, or post a stock
  document — `inventory.manage`, $oryh-inventory.
- Receive purchase-order goods — `/receive`, $oryh-purchase-order.
- Change an order's status. The flow agent advances it from your leg.
- Post a shipment nobody confirmed, or post one twice.

## Reference

- [references/api.md](references/api.md): request templates and the fields each read returns.
