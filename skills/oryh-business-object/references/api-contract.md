<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-business-object: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /business-object-links/{link_id}

Delete Business Object Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

## DELETE /business-objects/{business_object_id}

Delete Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /customers/{customer_id}

Delete Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

## DELETE /object-type-definitions/{definition_id}

Archive Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## DELETE /products/{product_id}

Delete Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## DELETE /timesheet-headers/{header_id}

Delete Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## GET /approval-records

List Approval Records

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `action` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /approval-records/{approval_record_id}

Get Approval Record

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `approval_record_id` | path | string | yes |  |

## GET /audit-logs

List Audit Logs

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `action` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `actor` | query | string | no |  |
| `before` | query | integer | no |  |
| `limit` | query | integer | no |  |

## GET /builtin-object-types

Get Builtin Object Types

## GET /business-object-links

List Business Object Links

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `source_object_id` | query | string | no |  |
| `target_object_id` | query | string | no |  |
| `link_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /business-object-links/{link_id}

Get Business Object Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

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

## GET /customers

List Customers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `phone` | query | string | no |  |
| `customer_kind` | query | string | no |  |
| `customer_type` | query | string | no |  |
| `geo_id` | query | string | no |  |
| `territory_id` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /customers/{customer_id}

Get Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

## GET /customers/{customer_id}/detail

Get Customer Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

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

## GET /products

List Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `category_id` | query | string | no |  |
| `product_type` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /products/{product_id}

Get Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## GET /products/{product_id}/attachments/{attachment_id}/content

Get Product Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /timesheet-headers

List Timesheet Headers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /timesheet-headers/{header_id}

Get Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /timesheet-headers/{header_id}/detail

Get Timesheet Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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

## PATCH /customers/{customer_id}

Update Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `address` | string (≤500 chars) | optional |  |
| `contact` | string (≤200 chars) | optional |  |
| `customer_code` | string (≤64 chars) | optional |  |
| `customer_kind` | `person` | `company` | optional |  |
| `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `payment_terms` | string (≤500 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `territory_id` | string | optional |  |

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

## PATCH /products/{product_id}

Update Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `category_id` | string | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `product_code` | string (≤64 chars) | optional |  |
| `product_type` | `finished_good` | `raw_material` | `semi_finished` | `service` | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `unit` | string (≤50 chars) | optional |  |

## PATCH /timesheet-headers/{header_id}

Update Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

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

## POST /approval-records

Create Approval Record

Body:

| field | type | | notes |
|---|---|---|---|
| `action` | `submitted` | `approved` | `rejected` | `returned` | `commented` | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | required |  |
| `acted_at` | date-time | optional |  |
| `approver_id` | string | optional |  |
| `approver_role` | string (≤100 chars) | optional |  |
| `comment` | string (≤2000 chars) | optional |  |
| `document_status` | string (≤30 chars) | optional |  |
| `handoff` | object | optional |  |
| `metadata` | object | optional |  |
| `round_no` | integer (≥1.0) | optional |  |
| `sequence_no` | integer (≥1.0) | optional |  |
| `source` | `web` | `api` | `ai` | `system` | optional |  |

## POST /business-object-links

Create Business Object Link

Body:

| field | type | | notes |
|---|---|---|---|
| `link_type` | string (≤100 chars) | required |  |
| `source_object_id` | string | required |  |
| `target_object_id` | string | required |  |
| `metadata` | object | optional |  |

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

## POST /customers

Create Customer

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `address` | string (≤500 chars) | optional |  |
| `contact` | string (≤200 chars) | optional |  |
| `customer_code` | string (≤64 chars) | optional |  |
| `customer_kind` | `person` | `company` | optional |  |
| `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
| `metadata` | object | optional |  |
| `owner_employee_id` | string | optional |  |
| `payment_terms` | string (≤500 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `territory_id` | string | optional |  |

## POST /customers/bulk

Bulk Upsert Customers

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `customer_code` | string (≤64 chars) | required |  |
  | `name` | string (≤200 chars) | required |  |
  | `address` | string (≤500 chars) | optional |  |
  | `contact` | string (≤200 chars) | optional |  |
  | `customer_kind` | `person` | `company` | optional |  |
  | `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
  | `email` | string (≤320 chars) | optional |  |
  | `geo_id` | string | optional |  |
  | `metadata` | object | optional |  |
  | `owner_employee_id` | string | optional |  |
  | `payment_terms` | string (≤500 chars) | optional |  |
  | `phone` | string (≤50 chars) | optional |  |
  | `status` | `active` | `archived` | optional |  |
  | `tax_id` | string (≤64 chars) | optional |  |
  | `territory_id` | string | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

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

## POST /products

Create Product

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `category_id` | string | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `product_code` | string (≤64 chars) | optional |  |
| `product_type` | `finished_good` | `raw_material` | `semi_finished` | `service` | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `unit` | string (≤50 chars) | optional |  |

## POST /products/bulk

Bulk Upsert Products

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `name` | string (≤200 chars) | required |  |
  | `product_code` | string (≤64 chars) | required |  |
  | `category_code` | string (≤64 chars) | optional |  |
  | `category_id` | string | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
  | `metadata` | object | optional |  |
  | `prices` | array of objects (fields below) | optional |  |
  | ↳ each `prices[]` item: | | | |
    | `price` | number (≥0.0, ≤9999999.99) | required |  |
    | `price_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
    | `currency` | string (≤3 chars) | optional |  |
    | `tax_in_price` | boolean | optional |  |
    | `tax_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `product_type` | `finished_good` | `raw_material` | `semi_finished` | `service` | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `status` | `active` | `archived` | optional |  |
  | `suppliers` | array of objects (fields below) | optional |  |
  | ↳ each `suppliers[]` item: | | | |
    | `vendor_code` | string (≤64 chars) | required |  |
    | `currency` | string (≤3 chars) | optional |  |
    | `last_price` | number (≥0.0, ≤9999999.99) | optional |  |
    | `lead_time_days` | integer (≥0.0, ≤3650.0) | optional |  |
    | `min_order_quantity` | number (≤9999999.99) | optional |  |
    | `order_increment` | number (≤9999999.99) | optional |  |
    | `preference` | integer (≥1.0, ≤100.0) | optional |  |
    | `supplier_product_code` | string (≤64 chars) | optional |  |
    | `supplier_product_name` | string (≤200 chars) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

## POST /products/{product_id}/skus/batch

Batch Create Product Skus

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `dimension` | string (≤50 chars) | required |  |
| `values` | array of string | required |  |
| `list_price` | number (≥0.0, ≤9999999.99) | string (pattern `^(?!^[-+.]*$)[+-]?0*\d*\.?\d{0,2}0*$`) | optional |  |

## POST /timesheet-headers

Create Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `period_end` | date | required |  |
| `period_start` | date | required |  |
| `custom_fields` | object | optional |  |
| `entries` | array of objects (fields below) | optional |  |
| ↳ each `entries[]` item: | | | |
  | `client` | string (≤200 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `employee_id` | string | optional |  |
  | `header_id` | string | optional |  |
  | `hours` | number (≤24.0) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `project_id` | string | optional |  |
  | `project_name_snapshot` | string (≤200 chars) | optional |  |
  | `task` | string (≤200 chars) | optional |  |
  | `work_date` | date | optional |  |
  | `work_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

## POST /timesheet-headers/{header_id}/restore

Restore Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /timesheet-headers/{header_id}/submit

Submit Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

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
