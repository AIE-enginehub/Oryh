---
name: oryh-inventory
description: Use when a warehouse keeper's AI agent needs to record what actually happened to stock in oryh — 收货 goods arriving (with or without a purchase order), 发货/领用 goods going out, 盘点 a stock count from a sheet, 借用/归还 a borrowed tool, a courier box nobody expected, a return with no return order. Covers posting ledger movements with whatever provenance exists, staging unknown arrivals, pairing loose ends with todos, and importing count sheets. Requires inventory management rights; it does not create products, vendors or customers (that is oryh-master-data) and does not place or receive purchase orders (oryh-purchase-order).
required_capability: inventory.manage
---

# Oryh Inventory

Keep the stock ledger true to the shelf. Stock here is a **ledger**: an
item's `quantity_on_hand` and `available_to_promise` are running sums of its
movement rows, nothing edits them directly, and a movement is never deleted —
a mistake is corrected by a counter-entry. Your job is to get reality into
that ledger at the moment it happens, with whatever is known at that moment.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/stay-current.md}}

{{include:_common/archived-is-history.md}}

## Trigger Examples

- "A carton arrived from SF Express, no idea which order" (record it now)
- "Zhang from engineering borrowed the impact drill, back on Friday"
- "We counted the main warehouse, here is the sheet" (stock-take import)
- "Issue 40 of P-1024 to the Shenzhen site"
- "These three came back from the customer, I don't know which order"
- "Something's off — the system says 120 but the shelf has 97"

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_base_url: "{{ORYH_API_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

- Which item moved: product (or SKU), facility, lot if the workspace tracks
  lots. `GET /inventory-items?product_id=&facility=` finds the position; a
  position that does not exist yet is created with `POST /inventory-items`.
- How much, and which way. A movement is a **difference**, signed: goods
  arriving are positive, goods leaving are negative.
- Why, as one of the ledger's reasons: `received | issued | returned |
  damaged | transfer | adjustment | other` for goods that moved;
  `reserved` and `reservation_released` are the ATP-only pair (see
  Reservation below); `initial`, `import_initial` and `import_override`
  belong to item creation and the count import.
- Everything else is optional — and that is the point. See below.

## Steps

1. **Find the position** before you post: `GET /inventory-items` filtered by
   product/SKU and facility. Read back the current `quantity_on_hand`; if the
   person is issuing more than is on hand, say so before posting, do not post
   and hope.
2. **Say what caused the movement, in the shape the cause has.** At most one
   of the first two:
   - one of this workspace's orders → `sales_order_id` or `purchase_order_id`
     (the server checks it exists here). RETURNS live in the same order
     tables (`order_kind: "return"`), so a return parcel's receipt names the
     RETURN row via the same `sales_order_id` — that is the inspected-into-
     stock step of the return's own lifecycle
   - any other record in the system → (`entity_type`, `entity_id`), a real uuid
   - an external order — Tmall, JD, another system → `custom_fields`, e.g.
     `{"source": "tmall", "order_no": "TM2026082112345"}`. Never `entity_id`:
     that column holds uuids of records this system can resolve, and an
     external number gets a 422 telling you exactly this. When the number is
     concrete, ALSO make it queryable after posting:
     `POST /external-document-links` with the movement as
     `entity_type: "inventory_item_detail"` — then "which movements belong to
     JD return JDR-7788" is one indexed lookup, not a prose search.
   - nothing known → nothing. `description` carries the story.
3. **Post the movement**: `POST /inventory-item-details` with the item, the
   signed `quantity_on_hand_diff`, `reason`, `description`, and whatever step
   2 produced. Posting to an archived item is a 409: reactivate it first if
   the goods are real.
4. **Read back** the item after posting and tell the person the new
   `quantity_on_hand` — that number is the whole reason the ledger exists.
5. **If something needs following up** — a loan to be returned, a source to
   be found, a return to be matched — create a todo for it. The ledger
   records what happened; the coordination fabric records what still has to.

## The Warehouse Records Reality, Not Paperwork

The messiest part of every ERP is the stock ledger, and the mess has one
cause: the system demands a document the world did not produce. Somebody from
the third floor borrows a drill. A courier box arrives that no purchase order
expected. A return shows up and nobody knows which return order it belongs
to. A traditional system rejects all three, so the keeper writes them in a
paper ledger, and within a month the system count is fiction.

Here the rule is the opposite, and it is the point of this system:

**Record what actually happened, with whatever is actually known, at the
moment it happens. A movement needs a reason, a quantity and words — never a
document.**

- **The borrow.** "Zhang from engineering took a drill, says Friday" →
  `POST /inventory-item-details` with `reason: "issued"`, the quantity, the
  whole story in `description`, and
  `custom_fields: {"arrangement": "loan", "holder": "Zhang", "due": "Friday"}`.
  Then create a todo for the return — the follow-up lives in the coordination
  fabric, not in a loan module. When the drill comes back, a `received`
  movement closes the loop and the todo is completed.
- **The mystery box.** Record the receipt NOW: `reason: "received"`, the
  quantity, `description` carrying everything the label says (courier,
  sender, tracking number — `custom_fields` for the structured bits). Book it
  into a staging location if the workspace uses one — `facility` and
  `bin_number` are free text, so a "PENDING" bin is a legal place. Open a todo to find
  the source. Never wait for the source to record the arrival: the box is on
  the shelf whether or not anyone knows why.
- **The orphan return.** `reason: "returned"`, quantity, story. When the
  source is later identified, what to do depends on WHAT was identified —
  and editing the row is never it:
  - it belongs to one of this workspace's own orders or RETURN rows → the
    provenance is a ledger fact, so post a counter-entry reversing the
    anonymous movement and a new one carrying `sales_order_id` — the return
    row's id when a return document exists, else the original order's. The ledger then
    tells the truth twice over: first that goods arrived unexplained, then
    that the explanation was found.
  - it is an EXTERNAL return — a JD refund number, a Tmall aftersale — →
    the row was never wrong, only unnamed. `POST /external-document-links`
    with `external_kind: "return"`, the platform's number, and the existing
    movement as `entity_type: "inventory_item_detail"`. A link, not a
    counter-entry: the frozen row gains a name without being touched.

**Never fabricate a document to satisfy the ledger.** A fake purchase order
"so the receipt has a source" pollutes the document system to decorate the
stock system, and the next person cannot tell your scaffolding from a real
order. Provenance is optional by design; absence of a document is a fact like
any other, and `description` is where it is stated.

**When one informal pattern becomes routine**, stop narrating it and give it a
shape: define a custom business object — a tool-loan record with its own
lifecycle, a sample-out slip, whatever the workspace calls it — and let
movements reference it
through (`entity_type`, `entity_id`). The ledger composes with tenant objects;
nothing about this needs a product change.

## Reservation: A Hold Is An Availability Fact, Not A Movement

When an order lands and its goods must be held, post an ATP-only ledger
row: `POST /inventory-item-details` with `reason: "reserved"`,
`quantity_on_hand_diff: 0`, a negative `available_to_promise_diff`, and
the `sales_order_id` whose goods these are — available drops, on-hand
stays, and the hold says whose it is (the server refuses any other
shape). Whether this workspace reserves at all is the same admin sentence
that governs picking — a small shop that never holds stock is not wrong,
and shipping without a hold simply moves both sums together.

- **Never release what post-stock will.** When the shipment posts, the
  server consumes the hold itself: a `reservation_released` row and the
  `issued` row land in one posting, so ATP is not deducted twice and the
  two sums agree again at rest.
- **A cancelled order releases by hand**: post `reservation_released`
  (ATP-only, positive, same `sales_order_id`) with the why in
  `description`. The ledger then tells the whole story: held, given
  back, nothing moved.
- Over-selling shows itself here: a hold that would push available below
  zero is the conversation to have with sales, not a number to fudge.

## Picking: Whether And How This Workspace Picks

**Whether to pick at all is the admin's call, stated in prose you read —
never a stored switch.** A three-person shop ships straight from the shelf;
a real warehouse walks a list. Before fulfilling a confirmed order, read
the tenant's sales_order workflow definition
(`GET /workflow-definitions?entity_kind=builtin&object_type=sales_order`):
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
   Walk the shipment (`packed → shipped`), **post-stock once**, then close
   the run: `PATCH /picklists/{id} {"status": "completed"}`. The order's
   own `shipped` is the flow agent's write, supported by your shipment.

The picklist is never the stock truth and never a router: stock moves when
the SHIPMENT posts, and which facility a given order ships from is your
call when you create the run.

## Shipments: The Freight Leg Is Yours Too

A parcel or a truck is a `/shipments` document — OFBiz Shipment reduced to
one leg with a `direction`: `outbound` (shipping a sales order, sending a
purchase return back to its vendor) or `inbound` (a customer return's
parcel; purchase-order receiving has its own path, below). The linked order
row must agree with the direction, and the server teaches the matrix on a
mismatch: sales order → outbound, sales return → inbound, purchase order →
inbound, purchase return → outbound. Returns live in the order tables, so a
return's parcel links the RETURN row.

Each line names WHAT moves and, when it touches this warehouse, WHERE:
`inventory_item_id` is the stock position (product@facility@lot) the goods
leave or land in. Omit it for drop-ship legs that never touch stock. The line's
product must match the position's — the server refuses a crossed pair.

**`POST /shipments/{id}/post-stock` is the one bridge to the ledger, and it
runs ONCE.** Direction decides the sign (outbound issues, inbound receives),
every movement carries the shipment line as provenance plus the header's
order link, and `stock_posted_at` makes a second call a 409 — corrections
are counter-entries, like every ledger fix. Lines without a position are
reported `skipped_no_position`, never silently absorbed.

**Never book the same goods twice.** Purchase-order receiving stays
`POST /purchase-orders/{po_id}/receive` ($oryh-purchase-order) — if goods
entered stock there, do not also post-stock a shipment for them; a shipment
for a PO leg is then a freight RECORD (tracking, dates, status), not a stock
mover. One physical movement, one ledger entry, whichever door it came
through.

The shipment's own life (`draft → packed → shipped → received`, editable in
draft/packed, tenant-renamable like every machine) is the freight fact the
flow admin advances order and return statuses FROM.

## Where Returned Goods Land Is The Tenant's Sentence

OFBiz forces a schema-level choice here — every return receipt creates its
own inventory item, and everyone pays the management cost. This system does
not: a "position" is just (product, facility, lot), all free text, and the
LEDGER already carries which units came back from which return (the
movement names the shipment line and the return row). So traceability never
requires segregation — segregation is purely an OPERATIONAL choice about
whether returned goods sit apart until someone inspects them. That choice
belongs to the tenant, stated in words, not in a parameter:

1. **Read the tenant's rule first**:
   `GET /workflow-definitions?entity_kind=builtin&object_type=sales_return`.
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
3. **Segregating tenants have a second leg**: after inspection, moving
   goods quarantine → main is a `transfer` pair in the ledger (one movement
   out, one in), exactly like any internal move. The return document's
   `inspected` state is the flow marker; the transfer is the goods fact.

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

## What This Skill Never Does

- Refuse to record a movement because no document exists. Absence of a
  document is a fact; state it in `description`.
- Fabricate a purchase order, sales order or return order to give a movement
  a source.
- Edit a quantity directly, or edit or delete a movement. Counter-entry, every
  time.
- Put an external order number in `entity_id`. It is not a uuid and the
  column promises resolvability; `custom_fields` is its home.
- Create products, SKUs, vendors or customers — that is `$oryh-master-data`,
  a different capability. A stock sheet naming an unknown product code is a
  per-row error to report, not a product to invent.
- Receive goods against a purchase order by posting movements yourself:
  `POST /purchase-orders/{po_id}/receive` (`$oryh-purchase-order`) does that
  and stamps the order on the ledger. This skill is for everything that
  arrives WITHOUT one.

## Reference

[references/api.md](references/api.md) — movements, picklists, shipments
and the count-import row contract.
