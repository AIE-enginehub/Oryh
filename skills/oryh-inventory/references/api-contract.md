<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-inventory: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /external-document-links/{link_id}

Delete External Document Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

## DELETE /inventory-items/{item_id}

Delete Inventory Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /shipment-items/{item_id}

Delete Shipment Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## GET /external-document-links

List External Document Links

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `source` | query | string | no |  |
| `external_kind` | query | string | no |  |
| `external_no` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /inventory-item-details

List Inventory Item Details

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `inventory_item_id` | query | string | no |  |
| `reason` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `sales_order_id` | query | string | no |  |
| `purchase_order_id` | query | string | no |  |
| `include_archived_items` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /inventory-items

List Inventory Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_id` | query | string | no |  |
| `facility` | query | string | no |  |
| `lot_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /inventory-items/{item_id}

Get Inventory Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## GET /picklists

List Picklists

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sales_order_id` | query | string | no |  |
| `facility_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /picklists/{picklist_id}

Get Picklist

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `picklist_id` | path | string | yes |  |

## GET /shipment-items

List Shipment Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `inventory_item_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /shipments

List Shipments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `direction` | query | string | no |  |
| `sales_order_id` | query | string | no |  |
| `purchase_order_id` | query | string | no |  |
| `shipment_no` | query | string | no |  |
| `tracking_no` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /shipments/{shipment_id}

Get Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

## GET /workflow-definitions

List Workflow Definitions

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entity_kind` | query | string | no |  |
| `object_type` | query | string | no |  |
| `name` | query | string | no |  |
| `history` | query | boolean | no |  |
| `status` | query | `active` | `superseded` | `all` | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## PATCH /inventory-items/{item_id}

Update Inventory Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `bin_number` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `expire_date` | date | optional |  |
| `facility` | string (≤100 chars) | optional |  |
| `lot_id` | string (≤64 chars) | optional |  |
| `metadata` | object | optional |  |
| `received_at` | date-time | optional |  |
| `status` | `active` | `archived` | optional |  |
| `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

## PATCH /picklist-items/{item_id}

Update Picklist Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤500 chars) | optional |  |
| `inventory_item_id` | string | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `picked_quantity` | number (≥0.0, ≤9999999.99) | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |

## PATCH /picklists/{picklist_id}

Update Picklist

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `picklist_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `facility_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `status` | string (≤50 chars) | optional |  |

## PATCH /shipments/{shipment_id}

Update Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `address` | string (≤500 chars) | optional |  |
| `carrier` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `expected_date` | date | optional |  |
| `facility` | string (≤100 chars) | optional |  |
| `purchase_order_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `tracking_no` | string (≤100 chars) | optional |  |

## POST /external-document-links

Create External Document Link

Body:

| field | type | | notes |
|---|---|---|---|
| `entity_id` | string | required |  |
| `entity_type` | string (≤100 chars) | required |  |
| `external_kind` | string (≤50 chars) | required |  |
| `external_no` | string (≤128 chars) | required |  |
| `source` | string (≤50 chars) | required |  |
| `metadata` | object | optional |  |

## POST /inventory-item-details

Create Inventory Item Detail

Body:

| field | type | | notes |
|---|---|---|---|
| `inventory_item_id` | string | required |  |
| `quantity_on_hand_diff` | number (≥-9999999.99, ≤9999999.99) | required |  |
| `reason` | `initial` | `import_initial` | `import_override` | `received` | `issued` | `adjustment` | `damaged` | `returned` | `transfer` | `other` | `reserved` | `reservation_released` | required |  |
| `available_to_promise_diff` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `created_by` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `effective_at` | date-time | optional |  |
| `entity_id` | string | optional |  |
| `entity_type` | string (≤50 chars) | optional |  |
| `purchase_order_id` | string | optional |  |
| `sales_order_id` | string | optional |  |
| `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

## POST /inventory-items

Create Inventory Item

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `bin_number` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `expire_date` | date | optional |  |
| `facility` | string (≤100 chars) | optional |  |
| `facility_id` | string | optional |  |
| `initial_description` | string (≤500 chars) | optional |  |
| `initial_quantity` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `initial_reason` | `initial` | `import_initial` | `import_override` | `received` | `issued` | `adjustment` | `damaged` | `returned` | `transfer` | `other` | `reserved` | `reservation_released` | optional |  |
| `lot_id` | string (≤64 chars) | optional |  |
| `metadata` | object | optional |  |
| `received_at` | date-time | optional |  |
| `sku_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |
| `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

## POST /inventory-items/bulk

Bulk Upsert Inventory

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `product_code` | string (≤64 chars) | required |  |
  | `quantity` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `bin_number` | string (≤64 chars) | optional |  |
  | `description` | string (≤500 chars) | optional |  |
  | `expire_date` | date | optional |  |
  | `facility` | string (≤100 chars) | optional |  |
  | `lot_id` | string (≤64 chars) | optional |  |
  | `sku_code` | string (≤64 chars) | optional |  |
  | `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

## POST /picklist-items

Create Picklist Item

Body:

| field | type | | notes |
|---|---|---|---|
| `inventory_item_id` | string | required |  |
| `picklist_id` | string | required |  |
| `product_id` | string | required |  |
| `quantity` | number (≤9999999.99) | required |  |
| `description` | string (≤500 chars) | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `picked_quantity` | number (≥0.0, ≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |

## POST /picklists

Create Picklist

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `facility_id` | string | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `inventory_item_id` | string | required |  |
  | `product_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `picked_quantity` | number (≥0.0, ≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
| `picklist_no` | string (≤64 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /purchase-orders/{po_id}/receive

Receive Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `po_item_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `bin_number` | string (≤64 chars) | optional |  |
  | `expire_date` | date | optional |  |
  | `facility` | string (≤100 chars) | optional |  |
  | `lot_id` | string (≤64 chars) | optional |  |
  | `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

## POST /shipment-items

Create Shipment Item

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `quantity` | number (≤9999999.99) | required |  |
| `shipment_id` | string | required |  |
| `description` | string (≤500 chars) | optional |  |
| `inventory_item_id` | string | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `sku_id` | string | optional |  |

## POST /shipments

Create Shipment

Body:

| field | type | | notes |
|---|---|---|---|
| `direction` | `outbound` | `inbound` | required |  |
| `address` | string (≤500 chars) | optional |  |
| `carrier` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `expected_date` | date | optional |  |
| `facility` | string (≤100 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `product_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `inventory_item_id` | string | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `sku_id` | string | optional |  |
| `picklist_id` | string | optional |  |
| `purchase_order_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `shipment_no` | string (≤64 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `tracking_no` | string (≤100 chars) | optional |  |

## POST /shipments/{shipment_id}/post-stock

Post Shipment Stock

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |
