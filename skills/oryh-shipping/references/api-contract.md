<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-shipping: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /business-objects/{business_object_id}

Delete Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /inventory-items/{item_id}

Delete Inventory Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /picklists/{picklist_id}

Delete Picklist

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `picklist_id` | path | string | yes |  |

## DELETE /purchase-orders/{po_id}

Delete Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## DELETE /sales-orders/{order_id}

Delete Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /shipment-items/{item_id}

Delete Shipment Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /shipments/{shipment_id}

Delete Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

## DELETE /stores/{store_id}

Delete Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## GET /business-objects

List Business Objects

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `object_type` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `payload_match` | query | string | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /business-objects/{business_object_id}

Get Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /business-objects/{business_object_id}/detail

Get Business Object Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /employees

List Employees

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /employees/{employee_id}

Get Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

## GET /employees/{employee_id}/pay-history

Get Employee Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `component` | query | string | no |  |
| `in_force_on` | query | date | no |  |

## GET /employees/{employee_id}/todos

List Employee Todos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `status` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /fulfilment-backlog

List Fulfilment Backlog

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `min_days_waiting` | query | integer (≥0) | no |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /picklists/{picklist_id}

Get Picklist

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `picklist_id` | path | string | yes |  |

## GET /purchase-orders

List Purchase Orders

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | query | string | no |  |
| `billing_account_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `po_number` | query | string | no |  |
| `order_kind` | query | string | no |  |
| `original_order_id` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /purchase-orders/{po_id}

Get Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## GET /purchase-orders/{po_id}/attachments/{attachment_id}/content

Get Purchase Order Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /purchase-orders/{po_id}/detail

Get Purchase Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## GET /sales-orders

List Sales Orders

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `billing_account_id` | query | string | no |  |
| `quotation_id` | query | string | no |  |
| `order_no` | query | string | no |  |
| `order_kind` | query | string | no |  |
| `original_order_id` | query | string | no |  |
| `supersedes_order_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /sales-orders/{order_id}

Get Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-orders/{order_id}/attachments/{attachment_id}/content

Get Sales Order Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /sales-orders/{order_id}/detail

Get Sales Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /shipment-items

List Shipment Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `inventory_item_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /shipments/{shipment_id}

Get Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

## GET /stores

List Stores

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel` | query | string | no |  |
| `source` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /stores/{store_id}

Get Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## GET /todos

List Todos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `due_before` | query | date-time | no |  |
| `include` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /todos/{todo_id}

Get Todo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `todo_id` | path | string | yes |  |

## GET /type-options

List Type Options

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `family` | query | string | no |  |
| `status` | query | string | no |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /workflow-definitions/{definition_id}

Get Workflow Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## PATCH /business-objects/{business_object_id}

Update Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `created_by` | string (≤100 chars) | optional |  |
| `object_type` | string (≤100 chars) | optional |  |
| `payload` | object | optional |  |
| `source_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /employees/{employee_id}

Update Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

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
| `facility_id` | string | optional |  |
| `lot_id` | string (≤64 chars) | optional |  |
| `metadata` | object | optional |  |
| `received_at` | date-time | optional |  |
| `status` | `active` | `archived` | optional |  |
| `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

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

## PATCH /purchase-orders/{po_id}

Update Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `order_date` | date | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `promised_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_id` | string | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

## PATCH /sales-orders/{order_id}

Update Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `billing_account_id` | string | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `logistics_company` | string (≤100 chars) | optional |  |
| `logistics_tracking_no` | string (≤100 chars) | optional |  |
| `order_date` | date | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `promised_date` | date | optional |  |
| `quotation_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `ship_to_address` | string (≤500 chars) | optional |  |
| `shipped_at` | date-time | optional |  |
| `signed_at` | date-time | optional |  |
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

## PATCH /shipment-items/{item_id}

Update Shipment Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤500 chars) | optional |  |
| `inventory_item_id` | string | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |

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

## PATCH /stores/{store_id}

Update Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `address` | string (≤500 chars) | optional |  |
| `channel` | `offline` | `online` | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_channel_id` | string | optional |  |
| `source` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `store_code` | string (≤64 chars) | optional |  |

## PATCH /todos/{todo_id}

Update Todo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `todo_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `completed_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `due_at` | date-time | optional |  |
| `status` | `open` | `completed` | `cancelled` | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /business-objects

Create Business Object

Body:

| field | type | | notes |
|---|---|---|---|
| `object_type` | string (≤100 chars) | required |  |
| `title` | string (≤200 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `payload` | object | optional |  |
| `source_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `summary` | string (≤2000 chars) | optional |  |

## POST /business-objects/{object_id}/post-entries

Post Business Object Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `object_id` | path | string | yes |  |

## POST /business-objects/{object_id}/post-stock

Post Business Object Stock

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `object_id` | path | string | yes |  |

## POST /business-objects/{business_object_id}/restore

Restore Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /employees

Create Employee

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

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
| `initial_reason` | `initial` | `import_initial` | `import_override` | `received` | `issued` | `adjustment` | `damaged` | `returned` | `transfer` | `other` | `reserved` | `reservation_released` | `production` | optional |  |
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

## POST /picklists/{picklist_id}/restore

Restore Picklist

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `picklist_id` | path | string | yes |  |

## POST /purchase-orders

Create Purchase Order

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `vendor_id` | string | required |  |
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `po_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `purchase_request_item_id` | string | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `order_date` | date | optional |  |
| `order_kind` | `order` | `return` | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `po_number` | string (≤64 chars) | optional |  |
| `promised_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

## POST /purchase-orders/bulk

Bulk Import Purchase Orders

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `po_number` | string (≤64 chars) | required |  |
  | `adjustments` | array of objects (fields below) | optional |  |
  | ↳ each `adjustments[]` item: | | | |
    | `adjustment_type` | string (≤20 chars) | required |  |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
    | `description` | string (≤500 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `metadata` | object | optional |  |
    | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `contract_no` | string (≤64 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `delivery_terms` | string (≤2000 chars) | optional |  |
  | `employee_code` | string (≤64 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `items` | array of objects (fields below) | optional |  |
  | ↳ each `items[]` item: | | | |
    | `quantity` | number (≤9999999.99) | required |  |
    | `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
    | `custom_fields` | object | optional |  |
    | `is_gift` | boolean | optional |  |
    | `lead_time` | string (≤100 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
    | `notes` | string (≤2000 chars) | optional |  |
    | `product_code` | string (≤64 chars) | optional |  |
    | `product_name_snapshot` | string (≤200 chars) | optional |  |
    | `promised_date` | date | optional |  |
    | `sku_code` | string (≤64 chars) | optional |  |
    | `spec` | string (≤200 chars) | optional |  |
    | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
    | `unit` | string (≤50 chars) | optional |  |
    | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
  | `order_date` | date | optional |  |
  | `payment_terms` | string (≤2000 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
  | `vendor_code` | string (≤64 chars) | optional |  |
  | `vendor_id` | string | optional |  |
  | `vendor_name_snapshot` | string (≤200 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

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

## POST /purchase-orders/{po_id}/restore

Restore Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## POST /sales-orders

Create Sales Order

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `billing_account_id` | string | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `is_gift` | boolean | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `order_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `logistics_company` | string (≤100 chars) | optional |  |
| `logistics_tracking_no` | string (≤100 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `order_date` | date | optional |  |
| `order_kind` | `order` | `return` | optional |  |
| `order_no` | string (≤64 chars) | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `promised_date` | date | optional |  |
| `quotation_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `ship_to_address` | string (≤500 chars) | optional |  |
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

## POST /sales-orders/bulk

Bulk Import Sales Orders

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `order_no` | string (≤64 chars) | required |  |
  | `adjustments` | array of objects (fields below) | optional |  |
  | ↳ each `adjustments[]` item: | | | |
    | `adjustment_type` | string (≤20 chars) | required |  |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
    | `description` | string (≤500 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `metadata` | object | optional |  |
    | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `contact_name` | string (≤200 chars) | optional |  |
  | `contact_phone` | string (≤50 chars) | optional |  |
  | `contract_no` | string (≤64 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `customer_code` | string (≤64 chars) | optional |  |
  | `customer_id` | string | optional |  |
  | `customer_name_snapshot` | string (≤200 chars) | optional |  |
  | `delivery_terms` | string (≤2000 chars) | optional |  |
  | `employee_code` | string (≤64 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `items` | array of objects (fields below) | optional |  |
  | ↳ each `items[]` item: | | | |
    | `quantity` | number (≤9999999.99) | required |  |
    | `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
    | `custom_fields` | object | optional |  |
    | `is_gift` | boolean | optional |  |
    | `lead_time` | string (≤100 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
    | `notes` | string (≤2000 chars) | optional |  |
    | `product_code` | string (≤64 chars) | optional |  |
    | `product_name_snapshot` | string (≤200 chars) | optional |  |
    | `promised_date` | date | optional |  |
    | `sku_code` | string (≤64 chars) | optional |  |
    | `spec` | string (≤200 chars) | optional |  |
    | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
    | `unit` | string (≤50 chars) | optional |  |
    | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
  | `order_date` | date | optional |  |
  | `payment_terms` | string (≤2000 chars) | optional |  |
  | `project_code` | string (≤64 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `ship_to_address` | string (≤500 chars) | optional |  |
  | `source_quote_number` | string (≤64 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /sales-orders/{order_id}/release

Release Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤500 chars) | optional |  |
| `lines` | array of objects (fields below) | optional |  |

## POST /sales-orders/{order_id}/reserve

Reserve Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `inventory_item_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `order_item_id` | string | optional |  |
| `description` | string (≤500 chars) | optional |  |

## POST /sales-orders/{order_id}/restore

Restore Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /sales-orders/{order_id}/revise

Revise Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `reason` | string (≤2000 chars) | optional |  |

## POST /sales-orders/{order_id}/submit

Submit Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

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

## POST /shipments/{shipment_id}/restore

Restore Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

## POST /stores

Create Store

Body:

| field | type | | notes |
|---|---|---|---|
| `channel` | `offline` | `online` | required |  |
| `name` | string (≤100 chars) | required |  |
| `address` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_channel_id` | string | optional |  |
| `source` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `store_code` | string (≤64 chars) | optional |  |

## POST /todos

Create Todo

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
| `title` | string (≤200 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `due_at` | date-time | optional |  |
| `metadata` | object | optional |  |
| `status` | `open` | `completed` | `cancelled` | optional |  |
| `todo_type` | string (≤50 chars) | optional |  |

## POST /todos/bulk

Bulk Create Todos

Body:

| field | type | | notes |
|---|---|---|---|
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `employee_id` | string | required |  |
  | `entity_id` | string | required |  |
  | `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
  | `title` | string (≤200 chars) | required |  |
  | `created_by` | string (≤100 chars) | optional |  |
  | `description` | string (≤2000 chars) | optional |  |
  | `due_at` | date-time | optional |  |
  | `metadata` | object | optional |  |
  | `status` | `open` | `completed` | `cancelled` | optional |  |
  | `todo_type` | string (≤50 chars) | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

## POST /workflow-definitions

Publish Workflow Definition

Body:

| field | type | | notes |
|---|---|---|---|
| `definition_text` | string (≤20000 chars) | required |  |
| `object_type` | string (≤100 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `name` | string (≤100 chars) | optional |  |
