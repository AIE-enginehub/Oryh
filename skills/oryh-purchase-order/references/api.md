# Oryh Purchase Order API Reference

{{include:_common/api-auth-principal.md}}

The credential needs `purchase_order.manage` — held by admin roles by
default, grantable to procurement staff, **not** in the member default (403
names the capability).

## Reads

{{include:_common/tenant-state-names.md}}

```text
GET /purchase-orders?vendor_id=&employee_id=&status=&po_number=&keyword=&page=&size=
                                             → keyword matches po_number/title/vendor snapshot/contract_no
GET /purchase-orders/{po_id}                 → header only
GET /purchase-orders/{po_id}/detail          → header + items (with product/sku/request context) + adjustments
                                               + computed_total/adjustments_total/adjusted_total
                                               + ordered_quantity/received_quantity + approval trail
GET /purchase-order-items?po_id=             → lines of one order
GET /purchase-order-items?purchase_request_item_id=  → which PO lines order a given requisition line
GET /object-type-definitions?entity_kind=builtin&object_type=purchase_order → the tenant's state machine (names are tenant-editable)
GET /purchase-requests?status=approved       → the requisitions waiting to be ordered
GET /vendors?keyword=&status=active          → the counterparty (REQUIRED on the PO)
GET /supplier-products?vendor_id=&product_id=  → the vendor's catalog + last_price history
GET /type-options?family=sales_adjustment_type → legal adjustment types (extend via POST /type-options)
```

## Create Order

```json
POST /purchase-orders
{
  "vendor_id": "vendor-id",
  "employee_id": "buyer-employee-id",
  "title": "研发部显示器采购",
  "order_date": "2026-07-26",
  "promised_date": "2026-08-05",
  "currency": "CNY",
  "payment_terms": "月结30天",
  "contract_no": "HT-2026-102"
}
```

- `vendor_id` and `employee_id` are **required** and must exist (404).
  `vendor_name_snapshot` fills from the vendor when omitted.
- Omit `po_number` → server allocates the next `PO-NNNNNN`. Pass your own to keep a
  tenant's numbering; a duplicate is 409.
- `status` defaults to the machine's initial (`draft`); any other value must
  be a state of the tenant's machine (422).

`PATCH /purchase-orders/{po_id}` updates header fields any time; a `status`
change must be a legal transition of the tenant's machine (409 otherwise) and
is audited. `DELETE` soft-deletes.

## Items — editable only while the order is in an editable state (default: draft)

```json
POST /purchase-order-items
{
  "po_id": "po-id",
  "line_no": 1,
  "product_id": "product-id-if-cataloged",
  "sku_id": "sku-id-when-the-variant-matters",
  "product_name_snapshot": "27寸显示器",
  "spec": "4K IPS",
  "quantity": 10,
  "unit": "台",
  "unit_price": 2750.00,
  "promised_date": "2026-08-05",
  "purchase_request_item_id": "approved-request-line-id",
  "notes": "optional"
}
```

- Identity: `product_id` (or `sku_id`, which derives the product) **or**
  free-text `product_name_snapshot` (422 with neither). Catalog matches
  backfill name/unit.
- 按单采购: `purchase_request_item_id` pins the requisition line this PO line
  fulfils (404 if nonexistent/cross-tenant; several PO lines may pin one
  request line). `PATCH` with `null` detaches. The chain is visible from both
  ends — see below.
- `PATCH /purchase-order-items/{item_id}` / `DELETE` while editable (409
  otherwise). `received_quantity` is server-maintained via `/receive` — not
  writable here.

## Adjustments (运费/税/折扣 on top of the line sum)

```json
POST /purchase-order-adjustments
{
  "po_id": "po-id",
  "po_item_id": null,
  "adjustment_type": "shipping",
  "description": "到付运费",
  "amount": 80.00
}
```

Signed `amount` (negative = discount); `po_item_id` null = header-level.
`adjustment_type` must be an active `sales_adjustment_type` option — the one
vocabulary shared by quotation/order/PO adjustments (422 lists the active
options; extend with `POST /type-options`). PATCH/DELETE gated on the same
editable states as items. `/detail` sums them:
`adjusted_total = computed_total + adjustments_total`.

## Receive — record arrival facts; never moves status

```json
POST /purchase-orders/{po_id}/receive
{
  "lines": [
    {"po_item_id": "line-id", "quantity": 6, "facility": "上海仓", "lot_id": "L-2026-07", "unit_cost": 2750.00},
    {"po_item_id": "other-line-id", "quantity": 3}
  ]
}
```

- Each line accumulates its item's `received_quantity`. Partial deliveries =
  多次调用; over-receipt (超收) is recorded as stated — flag it in
  conversation, the server does not block it.
- **With `facility`**: the goods land in inventory — the (product/sku,
  facility, lot) position is found or created, and an `InventoryItemDetail`
  is appended with `reason: "received"`, pinned to the PO line
  (`entity_type: purchase_order_item`). `unit_cost` defaults to the line's
  `unit_price`. Requires a cataloged product on the line — a free-text line
  with a facility is 422.
- **Without `facility`**: a 直发/零库存 receipt — the PO records arrival,
  stock is never touched.
- When a `SupplierProduct` link already exists for (line's product, PO's
  vendor), its `last_price` learns the line's `unit_price`; a link is never
  created here.
- Response per line: `{po_item_id, received_quantity, inventory_item_id}`
  (null when no facility). One audit event records the whole receipt.
- Not status-gated: state names are tenant-editable, so "receivable" is your
  judgment — don't receive against a draft that was never sent.

## The 按单采购 Chain

```text
sales_order_item  ←  purchase_request_item (sales_order_item_id)
                  ←  purchase_order_item  (purchase_request_item_id)
                  →  inventory_item_detail (entity_type=purchase_order_item)
```

- PO `/detail` items resolve a `purchase_request` block:
  `{purchase_request_item_id, request_id, request_status, quantity}` — the
  requisition-side quantity beside the ordered one.
- Purchase-request `/detail` items list `purchase_order_items`:
  `[{id, po_id, po_number, po_status, quantity, received_quantity, unit_price}]`
  — so 请购了5台/已下单5台/已到货3台 reads in one call, and through the
  request line's `sales_order` block the chain reaches the customer order.

## Historical Import

`POST /purchase-orders/bulk` upserts history keyed on `po_number` — same
contract as the sales imports, vendor always required. That workflow (order,
dry runs, chunking, problem reporting) is `$oryh-data-migration`.
