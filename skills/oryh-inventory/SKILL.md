---
name: oryh-inventory
description: Use when a warehouse keeper's agent keeps the stock ledger true in oryh — 库位登记, 盘点导入, 占货/释放, and the stock documents that move goods for reasons no order carries (报损, 调拨, 借用/归还, 生产入库, 杂收). Every ledger row is written by a business act; there is no direct movement write. Requires inventory.manage (which includes shipment.manage — parcels are oryh-shipping). Never creates products (oryh-master-data) or places POs (oryh-purchase-order).
required_capability: inventory.manage
---

# Oryh Inventory

Keep the stock ledger true to the shelf. Stock here is a **ledger**: an
item's `quantity_on_hand` and `available_to_promise` are running sums of its
movement rows, nothing edits them directly, and a movement is never deleted —
a mistake is corrected by a counter-document.
**No movement row is typed by hand.** Every row is written by the business act that caused it — a
shipment posting, a purchase receipt, a count import, an order's hold, or a
stock document the tenant defined — and the row carries that act as its
provenance. An agent once heard "ship it", skipped the order and the parcel,
and wrote a bare ledger row; the write that allowed it is gone —
`/inventory-item-details` is read-only.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/stay-current.md}}

{{include:_common/archived-is-history.md}}

## Trigger Examples

- "We counted the main warehouse, here is the sheet" (stock-take import)
- "Something's off — the system says 120 but the shelf has 97" (a count, or a damage report)
- "Zhang from engineering borrowed the impact drill, back on Friday" (a loan slip)
- "Move the two returned rolls from the returns area to the main shelf" (a transfer document)
- "Hold five 14x17 rolls for SO-000012" (a hold)
- "A carton arrived from SF Express, no idea which order" (a unexplained-receipt document — record it now)
- "Register a position for PT-HEAD in the Taian transit warehouse"

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_base_url: "{{ORYH_API_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

- Which position: product (or SKU), facility, lot if the workspace tracks
  lots. `GET /inventory-items?product_id=&facility=` finds it; a position
  that does not exist yet is created with `POST /inventory-items`.
- What happened, in the shape of the act that makes it true — the table
  below. The act names the ledger reason; you never pick one.

## Every Movement Has A Door

| What happened | The act that writes the row | Whose |
|---|---|---|
| Goods left for a customer, a return parcel arrived, a purchase return went back | `POST /shipments/{id}/post-stock` | $oryh-shipping (`shipment.manage`, included in yours) |
| Purchase-order goods arrived | `POST /purchase-orders/{id}/receive` | $oryh-purchase-order |
| A count differs from the system | `POST /inventory-items/bulk` (`import_override`) | you |
| Goods held for an order / given back | `POST /sales-orders/{id}/reserve` · `/release` | you |
| Anything else — damage, transfer, loan and return, production receipt, a parcel nobody ordered | a **stock document** the tenant defined, posted once: `POST /business-objects/{id}/post-stock` | you |

`/inventory-item-details` is read-only. A movement you cannot place
in this table is a question for the person — which door did the goods go
through? — never a row to type.

## The Warehouse Records Reality, Not Paperwork

The messiest part of every ERP is the stock ledger, and the mess has one
cause: the system demands a document the world did not produce, so the
keeper stops recording and the count becomes fiction. Here the door for
the undocumented case is a document the TENANT defines in its own words
— a loan slip, a unexplained-receipt document, a damage report — one sentence in a definition, and from
then on a two-minute record. The rule stays:

**Record what actually happened, at the moment it happens, through the
stock document that names it. A stock document needs a reason, the lines
and words — never a purchase order, sales order or return invented to
give it a source.**

- **The borrow.** "Zhang from engineering took a drill, says Friday" → a
  `tool_loan` document (`stock_effect: {reason: "issued", state: "open"}`
  in its definition) with one line, the whole story in `title` and
  `payload`, posted at once; a todo for the return. When the drill comes
  back, a `tool_return` document (`received`) closes the loop — or the
  tenant defines the loan with a `returned` state that a second document
  is not needed for. The follow-up lives in the coordination fabric.
- **The mystery box.** Record the receipt NOW through the workspace's
  unexplained-receipt document (`received`), the courier's label in the payload, into a staging
  position if the workspace uses one (`facility` and `bin_number` are free
  text, so a "PENDING" bin is a legal place). Open a todo to find the
  source. Never wait for the source to record the arrival.
- **The orphan return.** A parcel back from a customer is an inbound
  shipment ($oryh-shipping) — linked to the RETURN row when it is known,
  filed without one when it is not; when the source is later identified,
  what to do depends on WHAT was identified — and editing a row is never
  it: an external return number becomes a link (`POST
  /external-document-links` with `external_kind: "return"` on the
  movement, `entity_type: "inventory_item_detail"`), and one of this
  workspace's own return rows means a counter-document reversing the
  anonymous receipt and a new leg naming the row.

**Never fabricate a document of another kind to satisfy the ledger.** A
fake purchase order "so the receipt has a source" pollutes the document
system to decorate the stock system. The stock document IS the source, and
the definition that shaped it says so.

## Stock Documents: The Tenant's Own Doors

A stock document is a business object whose type definition carries a
`stock_effect`. Reading one:

```text
GET /object-type-definitions?entity_kind=business_object   → which types post stock, under which reason, from which state
GET /workflow-definitions?entity_kind=business_object&object_type=damage_report  → the tenant's words on when one is filed and who approves
```

Filing and posting one, in that order:

1. `POST /business-objects` `{object_type, title, status, payload: {lines:
   [{inventory_item_id, quantity_on_hand_diff, unit_cost?, description?}],
   …}}` — lines are SIGNED: a damage report is minus lines, a transfer document is one minus
   and one plus line on two positions, a production receipt document is plus lines. Whatever
   else the tenant's schema asks for goes in the payload beside them.
2. Walk it to the state the definition posts from (`PATCH
   /business-objects/{id}` `{"status": …}`) — the tenant's approval, in
   their words; a document created straight in that state is legal when
   nobody approves.
3. `POST /business-objects/{id}/post-stock` — **once**. The server posts
   every line under the definition's reason with the document as
   provenance (`entity_type: "business_object"`), stamps
   `payload.stock_posted_at`, and answers a second call with a 409. A
   wrong posting is a counter-document, never an edit.

Defining a new one is a sentence the admin (or you, holding
`workflows.publish`) writes in the object-type definition's state machine:

```json
{"initial": "draft", "states": ["draft", "approved", "rejected"],
 "transitions": {"draft": ["approved", "rejected"], "approved": [], "rejected": []},
 "stock_effect": {"reason": "damaged", "state": "approved"}}
```

`reason` is one of `received | issued | returned | adjustment | damaged |
transfer | production | other`; the reservation pair and the opening/count
reasons belong to the bridges that own them and are refused here.
**When one informal pattern becomes routine**, this is where it gets its
shape — a tool-loan slip, a sample-out record — and nothing about it needs
a product change.

## Reservation: A Hold Is An Availability Fact, Not A Movement

When an order lands and its goods must be held, post the hold through the
order: `POST /sales-orders/{order_id}/reserve` `{"lines": [{"inventory_item_id",
"quantity", "order_item_id"?}]}` — the server writes the `reserved` row
itself (available drops, on-hand stays, the row names the order), refuses a
position that holds goods the order has no line for, and refuses a hold
that would push available below zero with the numbers (409): that refusal
is the conversation to have with sales, not a number to fudge. Whether this
workspace reserves at all is the same admin sentence that governs picking
— a small shop that never holds stock is not wrong.

- **Never release what post-stock will.** When the shipment posts, the
  server consumes the hold itself: a `reservation_released` row and the
  `issued` row land in one posting, so ATP is not deducted twice and the
  two sums agree again at rest.
- **A cancelled order releases by hand**: `POST /sales-orders/{order_id}/release`
  with no lines gives back every outstanding hold of the order; with lines,
  exactly those quantities. A release larger than what the order still
  holds at that position is refused (409) — after post-stock there is
  nothing left to give back.

## Positions

- **A position is (product-or-SKU, facility, lot)**, free text, created on
  first use (`POST /inventory-items`; a 409 means it exists — reuse it). An
  `initial_quantity` on creation is the position's opening count and lands
  as its first ledger row; a position already on file only moves through
  the doors above.
- **A position names its facility twice**: the free-text `facility` is its
  identity, `facility_id` the registry pointer. Positions created before
  the warehouse was registered carry no pointer — `PATCH
  /inventory-items/{id}` `{"facility_id": …}` fills it in, and a renamed
  warehouse then breaks nothing.
- **Archiving a position** (`DELETE`) keeps its ledger; nothing posts to
  an archived one until it is set active again.

## Picking: Whether And How This Workspace Picks

**Whether to pick at all is the admin's call, stated in prose you read —
never a stored switch.** A three-person shop ships straight from the shelf;
a real warehouse walks a list. Before fulfilling a confirmed order, read
the tenant's sales_order workflow definition
(`GET /workflow-definitions?entity_kind=builtin&object_type=sales_order` —
once per session, sent with the order's own reads, not before them):
if it says picking is required ("pick before shipping" — one sentence is enough),
create a picklist; if it says nothing about picking, ship directly. The
admin changes the practice by editing that sentence (or this skill's
calibration), not a config flag.

Where picking IS the practice:

1. **Create the run**: `POST /picklists` with `sales_order_id`, the
   `facility_id` being walked, and lines — each line REQUIRES the stock
   position (`inventory_item_id`): naming where to take from is what a
   picking list is for, and the position must hold the line's product. A
   drop-ship line that touches no stock has no business on the list.
2. **Walk it**: `PATCH /picklists/{id}` `draft → picking`; record reality
   per line as you go — `PATCH /picklist-items/{id}
   {"picked_quantity": …}` — a short pick (or a zero) is a fact, not an
   error. Then `→ picked`: lines freeze; the list is now the handoff
   record.
3. **Pack and ship**: `POST /shipments` with `picklist_id` and NO items —
   the server copies the picked lines (picked quantities win; zero picks
   ship nothing), and refuses a picklist that picks for a different order.
   The leg, its walk and post-stock once are $oryh-shipping's — your
   grant includes them. Then close the run: `PATCH /picklists/{id}
   {"status": "completed"}`. The order's own `shipped` is the flow agent's
   write, supported by the shipment.

The picklist is never the stock truth and never a router: stock moves when
the SHIPMENT posts, and which facility a given order ships from is your
call when you create the run.

## Where Returned Goods Land Is The Tenant's Sentence

OFBiz forces a schema-level choice here — every return receipt creates its
own inventory item, and everyone pays the management cost. This system does
not: a "position" is just (product, facility, lot), all free text, and the
LEDGER already carries which units came back from which return (the
movement names the shipment line and the RETURN row). So traceability never
requires segregation — segregation is purely an OPERATIONAL choice about
whether returned goods sit apart until someone inspects them. That choice
belongs to the tenant, stated in words, not in a parameter:

1. **Read the tenant's rule** — once per session, in the same wave as the
   return's own reads: `GET /workflow-definitions?entity_kind=builtin&object_type=sales_return`.
   If the definition states a receiving policy — "returns land in the
   quarantine area, transfer to main after inspection", "returns go
   straight back to the original position",
   a quarantine bin, a `RET-` lot — follow its words exactly. Creating the
   stated position on first use is normal (`POST /inventory-items`,
   facility/bin/lot are free text; a 409 means it exists — reuse it).
2. **Definition silent → the original position.** The SME default: goods
   return to where they left from. Find it from the original order's own
   issue: `GET /inventory-item-details?sales_order_id={original_order_id}&reason=issued`
   → that movement's `inventory_item_id`. No issue movement on record (the
   order predates stock tracking, or shipped drop-ship) → the product's position
   at the facility the person names, and ask when nothing names one.
3. **The parcel itself is the inbound shipment** ($oryh-shipping) whose
   line names that position. **Segregating tenants have a second step**:
   after inspection, moving goods quarantine → main is a transfer document — a stock
   document with `stock_effect.reason: "transfer"`, one minus line and one
   plus line, posted once. The return document's `inspected` state is the
   flow marker; the transfer is the goods fact.

The tenant admin changes this rule by SAYING it — their agent publishes a
new `sales_return` workflow definition version carrying the sentence
(`workflows.publish`), and every later receipt follows the new words. Never
invent a policy the definition does not state, and never park the decision
in this skill's own text: the definition is where the tenant's words live,
versioned, so past receipts stay traceable to the rule they followed.

## Stock-Take Import

A count sheet is `POST /inventory-items/bulk` (`dry_run` first). Stock
lives on a ledger, so a counted quantity that differs from the system count
appends an `import_override` movement naming both numbers rather than
editing the item; a position not yet on file is created with an
`import_initial` opening; `product_code` (and `sku_code`) must already
exist. The full row contract is in [references/api.md](references/api.md).

**The server takes at most 500 rows per call** (a 422 above that). Do not
discover this by trying: write the normalised rows to a JSON file and run the
bundled script from this skill's directory —

```text
python3 scripts/bulk_import.py --kind inventory rows.json --expected-rows N
python3 scripts/bulk_import.py --kind inventory rows.json --expected-rows N --apply
```

It chunks at the cap, sends in order, dry-runs by default, stops at the
first bad chunk, and reports cumulatively with every row index global to
your file.

**`--expected-rows N` is the sheet's own count, and it is not optional.**
Read N off the sheet's last row number before extracting anything; never
count the rows you extracted and hand that number back. A file reader that
stops at 1,000 lines gives you 999 rows and says nothing — a stock take of
999 positions out of 1,000 then imports cleanly and reports success, and the
missing position surfaces weeks later as a shortage. With N given, the script
refuses to send when fewer rows reached it and tells you to re-read the sheet
in parts.

**One row per position** — (product-or-sku, facility, lot). Before the dry
run, look for two rows on the same position in the file; the server reports
the second as a per-row error, and under `abort` that error stops the chunk.
Two counts of one shelf is a question for the person, not a row to drop.

**Report the whole chain, every time**: *"sheet 1,000 rows → 1,000 sent in 2
chunks → 998 created, 2 unchanged, 0 failed."* Every number from the
responses, none from memory. A person who reads "999 imported" cannot tell a
999-row sheet from a lost row; the chain can.

## What This Skill Never Does

- Type a ledger row. There is no endpoint for it; every movement is a
  shipment posting, a purchase receipt, a count, a hold, or a stock
  document posted once.
- Refuse to record what happened because no order exists. The tenant's
  stock documents are the door for exactly that; absence of an order is a
  fact the document states.
- Fabricate a purchase order, sales order or return order to give a movement
  a source.
- Edit a quantity directly, or edit or delete a movement. Counter-document,
  every time.
- Ship. The parcel, its walk and `/post-stock` are $oryh-shipping's —
  included in your grant, taught there.
- Create products, SKUs, vendors or customers — that is `$oryh-master-data`,
  a different capability. A stock sheet naming an unknown product code is a
  per-row error to report, not a product to invent.
- Receive goods against a purchase order: `POST /purchase-orders/{po_id}/receive`
  (`$oryh-purchase-order`) does that and stamps the order on the ledger.

## Reference

- [references/api.md](references/api.md): request templates and the fields each read returns.
