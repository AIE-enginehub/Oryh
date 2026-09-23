# Oryh Shipping API Reference

<!-- only: bundle -->
Use with:

- header: `X-API-Key: <the principal's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add
<!-- /only -->
Capability: `shipment.manage` (`inventory.manage` includes it); reads are
tenant-visible

{{include:_common/api-conventions.md}}

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
  "direction": "outbound",
  "sales_order_id": "the-order-id",
  "carrier": "SF Express", "tracking_no": "SF123456789", "facility": "Shanghai main warehouse",
  "items": [{"product_id": "…", "sku_id": "…", "quantity": 5, "inventory_item_id": "position-id"}]
}
```

Direction must agree with the linked row (sales order → outbound, sales
return → inbound, purchase order → inbound, purchase return → outbound).
`inventory_item_id` is the stock position a line leaves or lands in — omit
for drop-ship; the position must hold the line's product (and SKU).
`picklist_id` and no items: the server copies the picked lines.

post-stock: outbound `issued`; inbound `received` — except a leg linked to
a RETURN row, which posts `returned`. Provenance `entity_type:
"shipment_item"` + the order FK, once only; the order's outstanding hold is
released in the same posting. Response: `stock_posted_at` and per line
`posted | skipped_no_position` with `reservation_released`.

## What The Order Still Owes

```text
GET /sales-orders/{order_id}/detail    → fulfilment[] per line: ordered / shipped / outstanding
GET /fulfilment-backlog?store_id=&employee_id=&min_days_waiting=
                                       → confirmed orders with lines not fully shipped
GET /stores/{store_id} · GET /stores?source=
                                       → fulfilment_facilities, priority 1 first
GET /inventory-items?product_id=&sku_id=&facility=
                                       → the position a line leaves from (quantity_on_hand, available_to_promise)
GET /inventory-item-details?sales_order_id=&reason=
                                       → what already moved for the order (read only)
GET /picklists?sales_order_id=&status= → a picked run to ship from
GET /todos?employee_id=&status=open    · PATCH /todos/{todo_id} {"status": "completed"}
GET /employees?keyword=
```

The ledger has no write of its own — `/inventory-item-details` is
read-only. Holds are `POST /sales-orders/{id}/reserve` / `/release`, stock
documents are `POST /business-objects/{id}/post-stock`, counts are
`POST /inventory-items/bulk` — all `inventory.manage`, $oryh-inventory.

## Restating The Whole Document

```text
GET  /shipments/{id}                                                          → revision (a hash of the header and the live lines)
POST /shipments/{id}/save?validate_only=true                → the same run, nothing written
POST /shipments/{id}/save
{"expected_revision": "<shipment.revision>", "items": [{"id": "<existing line>", "quantity": 3}, {"product_id": "...", "quantity": 2, "inventory_item_id": "..."}]}
```

A diff, never a delete-and-reinsert: a row naming an `id` keeps its identity
and changes only in the fields it states; a row without an id is added
through the create rules; a live line not listed is removed. A stale
`expected_revision` is a 409 — read again, restate. Only before the shipment is posted to stock. A line's product cannot change in place.
