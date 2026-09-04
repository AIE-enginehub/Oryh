# Oryh Inventory API Reference

Use with:

- header: `X-API-Key: <the principal's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add
- capability: `inventory.manage` (the bundle only carries this skill when the
  principal's role has it); reads are tenant-visible

## Positions

```text
GET    /inventory-items?product_id=&sku_id=&facility=&lot_id=&status=
GET    /inventory-items/{item_id}
POST   /inventory-items             → optional initial_quantity lands as the first detail; 409 if the position exists
PATCH  /inventory-items/{item_id}   → identity/dates/cost only — it has NO quantity fields; sending one is a 422
DELETE /inventory-items/{item_id}   → archive (the ledger beneath stays)
```

A position is (product-or-SKU, `facility`, `lot_id`). `facility`,
`bin_number` and `lot_id` are free text: a "PENDING" bin for unexplained
arrivals needs no configuration.

## Movements

```text
GET    /inventory-item-details?inventory_item_id=&reason=&entity_type=&entity_id=&sales_order_id=&purchase_order_id=
POST   /inventory-item-details      → append one movement; the ONLY way totals move
```

```json
POST /inventory-item-details
{
  "inventory_item_id": "…",
  "quantity_on_hand_diff": -1,
  "reason": "issued",
  "description": "impact drill borrowed by Zhang (engineering), due back Friday",
  "custom_fields": {"arrangement": "loan", "holder": "Zhang", "due": "2026-08-22"}
}
```

Details are immutable — no update, no delete, no per-row path; a mistake is
corrected by a counter-entry. `reason` catalog: `received | issued |
adjustment | damaged | returned | transfer | other` for goods that moved;
`reserved | reservation_released` for the ATP-only hold pair
(`quantity_on_hand_diff` 0, `available_to_promise_diff` negative then
positive, `sales_order_id` required — 422 otherwise); `initial |
import_initial | import_override` for item creation and the count import.
Posting to an archived item is a 409.

**Provenance, in the shape the cause has** — one movement carries at most one
of the first two:

- **One of this workspace's orders** → `sales_order_id` or
  `purchase_order_id` (at most one; the server checks the order exists
  here). Receiving through `POST /purchase-orders/{po_id}/receive` stamps
  `purchase_order_id` for you, so "every movement this order caused" is one
  filtered GET.
- **Any other record in the system** → (`entity_type`, `entity_id`) —
  `entity_id` must be a real uuid.
- **An external order — Tmall, JD, another system** → `custom_fields`.
  Never `entity_id`: that column holds uuids of records this system can
  resolve, and an external number is a 422 telling you exactly this.

**A concrete external number also gets a LINK** (after posting, or later
when a mystery parcel is finally identified — the frozen row gains a name
without a counter-entry):

```json
POST /external-document-links
{
  "source": "jd",
  "external_kind": "return",
  "external_no": "JDR-202608-7788",
  "entity_type": "inventory_item_detail",
  "entity_id": "the movement's id"
}
```

`GET /external-document-links?source=jd&external_no=JDR-202608-7788` then
answers "which movements belong to this platform return" as one indexed
lookup. Same capability as the movement itself; exact duplicate → 409 (a
retry, not a new fact); `DELETE /external-document-links/{id}` undoes a
mislink.

## Shipments

```text
GET  /shipments?direction=&sales_order_id=&purchase_order_id=&status=&tracking_no=
GET  /shipments/{shipment_id}                    → header + items
POST /shipments                                  → SH-NNNNNN; items ride the create
PATCH /shipments/{shipment_id}                   → facts + machine-gated status
POST /shipments/{shipment_id}/post-stock         → the ONE bridge to the ledger; 409 on a second call
GET  /shipment-items?shipment_id=&inventory_item_id=
POST /shipment-items · PATCH/DELETE /shipment-items/{item_id}   → editable while draft/packed
```

```json
POST /shipments
{
  "direction": "inbound",
  "sales_order_id": "the-RETURN-row-id",
  "carrier": "YTO", "tracking_no": "YT-889", "facility": "main",
  "items": [{"product_id": "cup", "quantity": 2, "inventory_item_id": "position-id"}]
}
```

Direction must agree with the linked row (sales order → outbound, sales
return → inbound, purchase order → inbound, purchase return → outbound).
`inventory_item_id` is the stock position a line leaves or lands in — omit
for drop-ship. post-stock: outbound `issued`; inbound `received` — except a leg
linked to a RETURN row, which posts `returned`, so one ledger word answers
"how much came back" whichever door it entered. Provenance
`entity_type: "shipment_item"` + the order FK, once only.

## Picklists

```text
GET    /picklists?sales_order_id=&facility_id=&status=&keyword=
POST   /picklists        → {sales_order_id, facility_id?, items: [{product_id, sku_id?,
                            inventory_item_id, quantity, picked_quantity?, description?}]}
                            every line names its stock position, and the position must
                            hold the line's product (422 otherwise)
GET    /picklists/{id}   → header + live lines
PATCH  /picklists/{id}   → fields, or status along the tenant's machine
                            (default draft → picking → picked → completed; cancelled)
POST   /picklist-items   → add a line to an editable run;  PATCH /picklist-items/{id}
                            {picked_quantity} records reality;  DELETE removes the line
POST   /shipments        → {picklist_id, ...} and NO items: the server copies the picked
                            lines (picked quantities win, zero picks ship nothing) and
                            refuses a picklist that picks for a different order
```

`GET /inventory-item-details` answers with movements of ACTIVE positions
unless `inventory_item_id` names one or `include_archived_items=true` is
passed; every row carries `item_status`. `GET /inventory-items` lists active
positions by default (`status=archived` / `status=all` to widen).

## Stock-Take Import

Stock lives on a LEDGER. An inventory item's `quantity_on_hand` /
`available_to_promise` are running sums of its detail rows — nothing edits
them directly, and the import obeys the same rule:

```text
POST /inventory-items/bulk
{"rows": [
  {"product_code": "P-001", "facility": "Main warehouse", "lot_id": "B2026-07",
   "quantity": 120.5, "expire_date": "2027-06-30"}
 ], "dry_run": true, "on_error": "abort"}
```

- The stock position is (product-or-sku, `facility`, `lot_id`); `sku_code`
  names a variant, empty facility/lot mean "unspecified". One row per
  position per file — a duplicate is a per-row error.
- No item at that position yet → created, opening balance recorded as a
  ledger detail with reason `import_initial`.
- Counted `quantity` equals the system count → `unchanged`, no ledger noise.
- Counted `quantity` DIFFERS → the item is NOT edited: a detail is appended
  with `quantity_on_hand_diff` = (counted − system), reason
  `import_override`, its description naming both numbers (import override:
  system quantity X → imported quantity Y). The row result reports
  `changed: ["quantity_on_hand"]`.
- `product_code` (and `sku_code`) must already exist — unknown codes are
  per-row errors, never invented records.

