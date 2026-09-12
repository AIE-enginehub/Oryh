# Oryh Inventory API Reference

Use with:

- header: `X-API-Key: <the principal's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add
- capability: `inventory.manage` (the bundle only carries this skill when the
  principal's role has it; it includes `shipment.manage`); reads are
  tenant-visible

{{include:_common/api-conventions.md}}

## Positions

```text
GET    /inventory-items?product_id=&sku_id=&facility=&lot_id=&status=
GET    /inventory-items/{item_id}
POST   /inventory-items             → optional initial_quantity lands as the first detail; 409 if the position exists
PATCH  /inventory-items/{item_id}   → identity/dates/cost, and facility_id (the registry pointer, fillable after the fact) — NO quantity fields; sending one is a 422
DELETE /inventory-items/{item_id}   → archive (the ledger beneath stays)
```

A position is (product-or-SKU, `facility`, `lot_id`). `facility`,
`bin_number` and `lot_id` are free text: a "PENDING" bin for unexplained
arrivals needs no configuration.

## The Ledger (read only)

```text
GET    /inventory-item-details?inventory_item_id=&reason=&entity_type=&entity_id=&sales_order_id=&purchase_order_id=
```

There is no `POST`: every row is written by one of the doors below and
carries it — `entity_type` `shipment_item` / `purchase_order_item` /
`sales_order_item` / `business_object`, plus the order FK. Details are
immutable — no update, no delete, no per-row path; a mistake is corrected
by a counter-document. `reason` vocabulary as read: `received | issued |
returned | adjustment | damaged | transfer | production | other` for goods
that moved; `reserved | reservation_released` for the ATP-only hold pair;
`initial | import_initial | import_override` for item creation and the
count import. Movements of ACTIVE positions are listed unless
`inventory_item_id` names one or `include_archived_items=true` is passed;
every row carries `item_status`.

## Holds: Through The Order

```text
POST /sales-orders/{order_id}/reserve   {"lines": [{"inventory_item_id": "…", "quantity": 5, "order_item_id"?: "…"}], "description"?: "…"}
POST /sales-orders/{order_id}/release   {"lines"?: [...same...], "description"?: "…"}   — no lines: every outstanding hold of the order
```

`reserve` writes `reserved` rows (available drops, on-hand stays, the row
names the order); 422 when the position holds goods the order has no line
for, 409 when the hold would push available below zero (the numbers are in
the detail), 409 when the order is in a state nothing follows. `release`
writes `reservation_released` rows; 409 when more than the order still
holds at that position is asked for. Post-stock on the order's shipment
releases the hold itself. Response: `{order_id, reason, lines: [{inventory_item_id,
detail_id, quantity, available_to_promise}]}`.

## Stock Documents: A Business Object That Posts

```text
GET  /object-type-definitions?entity_kind=business_object      → types; a stock document's state_machine carries stock_effect {reason, state}
POST /object-type-definitions   {object_type, title?, json_schema?, state_machine: {..., "stock_effect": {"reason": "damaged", "state": "approved"}}}
POST /business-objects          {object_type, title, status, payload: {"lines": [{"inventory_item_id": "…", "quantity_on_hand_diff": -2, "unit_cost"?: 12.5, "description"?: "…"}], ...}}
PATCH /business-objects/{id}    {"status": "approved"}                     → along the type's machine
POST /business-objects/{id}/post-stock                                  → once; 409 on a second call
```

`stock_effect.reason` ∈ `received | issued | returned | adjustment | damaged
| transfer | production | other`; `state` is the state the document posts
from. Lines are signed — a transfer document is a minus line and a plus line. The
posting refuses a type without `stock_effect` (422), a document not in the
declared state (409), an empty or unsigned line (422), an archived position
(409); it writes every line under the reason with `entity_type:
"business_object"`, stamps `payload.stock_posted_at`, and audits
`business_object.stock_posted`. Response: `{object_id, reason,
stock_posted_at, lines: [{inventory_item_id, detail_id, quantity_on_hand_diff,
quantity_on_hand}]}`.

## Naming A Frozen Row Later

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
lookup. A link, not a counter-entry: the frozen row gains a name without
being touched. Exact duplicate → 409 (a retry, not a new fact); `DELETE
/external-document-links/{id}` undoes a mislink.

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
                            refuses a picklist that picks for a different order — $oryh-shipping
```

## Shipments

The parcel, its walk and `POST /shipments/{id}/post-stock` are
$oryh-shipping's (`shipment.manage`, included in `inventory.manage`); this
skill only READS them: `GET /shipments?sales_order_id=&status=`,
`GET /shipments/{shipment_id}`.

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

## Where To Ship From, What Is Still Owed

```text
GET /stores?source=&keyword=           → each store with fulfilment_facilities (priority 1 first)
GET /stores/{store_id}                 → the same, one store
GET /store-facilities?store_id=        → the raw pairs
GET /facilities?keyword=               → the registry the pointer names
GET /fulfilment-backlog?store_id=&employee_id=&min_days_waiting=
                                       → confirmed orders with lines not fully shipped:
                                         lines[].ordered/shipped/outstanding, days_waiting,
                                         shipments_posted, open_todo_count, promised_date
GET /sales-orders/{order_id}/detail    → fulfilment[] per line — the same arithmetic for one order
GET /employees?keyword=                → who a todo goes to
```

## Finding The Product

```text
GET /products?keyword=              → by name or code; `?product_code=` exact
GET /product-skus?product_id=       → the product's SKUs; `?sku_code=` exact
GET /product-matches?title=&limit=5 → candidates for a platform title
```
