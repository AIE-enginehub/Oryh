<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-purchase-order: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /bills-of-materials/{bom_id}

Delete Bill Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | path | string | yes |  |

## DELETE /contract-terms/{term_id}

Delete Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

## DELETE /contracts/{contract_id}

Delete Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## DELETE /object-type-definitions/{definition_id}

Archive Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## DELETE /purchase-order-adjustments/{adjustment_id}

Delete Purchase Order Adjustment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `adjustment_id` | path | string | yes |  |

## DELETE /purchase-order-items/{item_id}

Delete Purchase Order Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /purchase-orders/{po_id}

Delete Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## DELETE /purchase-requests/{request_id}

Delete Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /shipments/{shipment_id}

Delete Shipment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `shipment_id` | path | string | yes |  |

## DELETE /supplier-products/{supplier_product_id}

Delete Supplier Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `supplier_product_id` | path | string | yes |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

## DELETE /vendors/{vendor_id}

Delete Vendor

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | path | string | yes |  |

## GET /bills-of-materials

List Bills Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /bills-of-materials/{bom_id}

Get Bill Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | path | string | yes |  |

## GET /bills-of-materials/{bom_id}/explode

Explode Bill Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | path | string | yes |  |
| `quantity` | query | number (≤99999999) | no |  |
| `with_stock` | query | boolean | no |  |
| `facility_id` | query | string | no |  |

## GET /contract-terms

List Contract Terms

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `term_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /contracts

List Contracts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `side` | query | string | no |  |
| `contract_type` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `parent_contract_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /contracts/{contract_id}

Get Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## GET /contracts/{contract_id}/attachments/{attachment_id}/content

Get Contract Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /contracts/{contract_id}/execution

Contract Execution

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

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

## GET /object-type-definitions

List Object Type Definitions

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `object_type` | query | string | no |  |
| `entity_kind` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /object-type-definitions/{definition_id}

Get Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## GET /purchase-order-adjustments

List Purchase Order Adjustments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | query | string | no |  |
| `po_item_id` | query | string | no |  |
| `adjustment_type` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /purchase-order-adjustments/{adjustment_id}

Get Purchase Order Adjustment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `adjustment_id` | path | string | yes |  |

## GET /purchase-order-items

List Purchase Order Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | query | string | no |  |
| `purchase_request_item_id` | query | string | no |  |
| `sales_order_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /purchase-order-items/{item_id}

Get Purchase Order Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

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

## GET /purchase-requests

List Purchase Requests

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /purchase-requests/{request_id}

Get Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /purchase-requests/{request_id}/attachments/{attachment_id}/content

Get Purchase Request Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /purchase-requests/{request_id}/detail

Get Purchase Request Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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

## GET /supplier-products

List Supplier Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /supplier-products/{supplier_product_id}

Get Supplier Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `supplier_product_id` | path | string | yes |  |

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

## GET /vendors

List Vendors

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /vendors/{vendor_id}

Get Vendor

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | path | string | yes |  |

## PATCH /bills-of-materials/{bom_id}

Update Bill Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `bom_code` | string (≤64 chars) | optional |  |
| `metadata` | object | optional |  |
| `output_quantity` | number (≤99999999.9999) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | `draft` | optional |  |
| `version` | string (≤50 chars) | optional |  |

## PATCH /contract-terms/{term_id}

Update Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `clause_ref` | string (≤50 chars) | optional |  |
| `content` | string (≤20000 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `term_type` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /contracts/{contract_id}

Update Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contract_type` | string (≤50 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `counterparty_signatory` | string (≤100 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `employee_id` | string | optional |  |
| `our_signatory` | string (≤100 chars) | optional |  |
| `parent_contract_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `signed_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `summary` | string (≤10000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤999999999999.99) | optional |  |

## PATCH /object-type-definitions/{definition_id}

Update Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤2000 chars) | optional |  |
| `json_schema` | object | optional |  |
| `state_machine` | object | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /purchase-order-adjustments/{adjustment_id}

Update Purchase Order Adjustment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `adjustment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `po_item_id` | string | optional |  |
| `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

## PATCH /purchase-order-items/{item_id}

Update Purchase Order Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
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

## PATCH /purchase-requests/{request_id}

Update Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `needed_by` | date | optional |  |
| `request_date` | date | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `vendor_id` | string | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

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

## PATCH /supplier-products/{supplier_product_id}

Update Supplier Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `supplier_product_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `currency` | string (≤3 chars) | optional |  |
| `last_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `lead_time_days` | integer (≥0.0, ≤3650.0) | optional |  |
| `metadata` | object | optional |  |
| `min_order_quantity` | number (≤9999999.99) | optional |  |
| `order_increment` | number (≤9999999.99) | optional |  |
| `preference` | integer (≥1.0, ≤100.0) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `supplier_product_code` | string (≤64 chars) | optional |  |
| `supplier_product_name` | string (≤200 chars) | optional |  |

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

## PATCH /type-options/{type_option_id}

Update Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /vendors/{vendor_id}

Update Vendor

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contact` | string (≤200 chars) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `vendor_code` | string (≤64 chars) | optional |  |

## POST /bills-of-materials

Create Bill Of Materials

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `bom_code` | string (≤64 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `component_product_id` | string | required |  |
  | `quantity` | number (≤99999999.9999) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `scrap_rate` | number (≥0.0, ≤99.99) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `output_quantity` | number (≤99999999.9999) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | `draft` | optional |  |
| `version` | string (≤50 chars) | optional |  |

## POST /contract-terms

Create Contract Term

Body:

| field | type | | notes |
|---|---|---|---|
| `content` | string (≤20000 chars) | required |  |
| `contract_id` | string | required |  |
| `term_type` | string (≤50 chars) | required |  |
| `clause_ref` | string (≤50 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /contracts

Create Contract

Body:

| field | type | | notes |
|---|---|---|---|
| `title` | string (≤200 chars) | required |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `contract_type` | string (≤50 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `counterparty_signatory` | string (≤100 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `employee_id` | string | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `currency` | string (≤3 chars) | optional |  |
  | `delivery_note` | string (≤500 chars) | optional |  |
  | `description` | string (≤500 chars) | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `metadata` | object | optional |  |
  | `product_id` | string | optional |  |
  | `quantity` | number (≤99999999.9999) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `our_signatory` | string (≤100 chars) | optional |  |
| `parent_contract_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `signed_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `summary` | string (≤10000 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `vendor_id` | string | optional |  |

## POST /contracts/{contract_id}/restore

Restore Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## POST /object-type-definitions

Create Object Type Definition

Body:

| field | type | | notes |
|---|---|---|---|
| `object_type` | string (≤100 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `json_schema` | object | optional |  |
| `state_machine` | object | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /purchase-order-adjustments

Create Purchase Order Adjustment

Body:

| field | type | | notes |
|---|---|---|---|
| `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
| `po_id` | string | required |  |
| `description` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `po_item_id` | string | optional |  |
| `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

## POST /purchase-order-items

Create Purchase Order Item

Body:

| field | type | | notes |
|---|---|---|---|
| `po_id` | string | required |  |
| `quantity` | number (≤9999999.99) | required |  |
| `amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `promised_date` | date | optional |  |
| `purchase_request_item_id` | string | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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

## POST /purchase-requests

Create Purchase Request

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `request_id` | string | optional |  |
  | `sales_order_item_id` | string | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `needed_by` | date | optional |  |
| `request_date` | date | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `vendor_id` | string | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

## POST /purchase-requests/{request_id}/restore

Restore Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /purchase-requests/{request_id}/submit

Submit Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

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

## POST /supplier-products

Create Supplier Product

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `vendor_id` | string | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `last_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `lead_time_days` | integer (≥0.0, ≤3650.0) | optional |  |
| `metadata` | object | optional |  |
| `min_order_quantity` | number (≤9999999.99) | optional |  |
| `order_increment` | number (≤9999999.99) | optional |  |
| `preference` | integer (≥1.0, ≤100.0) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `supplier_product_code` | string (≤64 chars) | optional |  |
| `supplier_product_name` | string (≤200 chars) | optional |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /vendors

Create Vendor

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `contact` | string (≤200 chars) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `metadata` | object | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `vendor_code` | string (≤64 chars) | optional |  |

## POST /vendors/bulk

Bulk Upsert Vendors

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `name` | string (≤200 chars) | required |  |
  | `vendor_code` | string (≤64 chars) | required |  |
  | `contact` | string (≤200 chars) | optional |  |
  | `email` | string (≤320 chars) | optional |  |
  | `metadata` | object | optional |  |
  | `phone` | string (≤50 chars) | optional |  |
  | `status` | `active` | `archived` | optional |  |
  | `tax_id` | string (≤64 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
