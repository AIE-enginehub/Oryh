<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-product-matching: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /external-product-maps/{map_id}

Delete External Product Map

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `map_id` | path | string | yes |  |

## DELETE /product-skus/{sku_id}

Delete Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

## DELETE /products/{product_id}

Delete Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## DELETE /sales-channels/{channel_id}

Delete Sales Channel

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel_id` | path | string | yes |  |

## DELETE /skills/{skill_ref}

Archive Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## DELETE /skills/{skill_ref}/assignments/{assignment_id}

Remove Skill Assignment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |
| `assignment_id` | path | string | yes |  |

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

## GET /external-product-maps

List External Product Maps

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `source` | query | string | no |  |
| `external_product_id` | query | string | no |  |
| `external_name` | query | string | no |  |
| `external_sku_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `keyword` | query | string | no |  |
| `at` | query | date | no | Resolve the map AS OF this date — rows whose [effective_from, effective_to) window covers it, null bounds open. This is THE translation query: pass the ORDER's date, because a listing that swapped products means different things on different days. Without an explicit status filter, `at` returns live rows only — an archived (withdrawn) pairing never described the listing. |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /external-product-maps/{map_id}

Get External Product Map

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `map_id` | path | string | yes |  |

## GET /product-matches

Match Products By Title

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `title` | query | string (≤300 chars) | yes |  |
| `limit` | query | integer (≥1, ≤20) | no |  |

## GET /product-skus

List Product Skus

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_code` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /product-skus/{sku_id}

Get Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

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

## GET /sales-channels

List Sales Channels

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel_kind` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /sales-channels/{channel_id}

Get Sales Channel

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel_id` | path | string | yes |  |

## GET /skills

List Skills

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `status` | query | `active` | `archived` | `all` | no |  |
| `kind` | query | `product` | `custom` | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /skills/{skill_ref}

Get Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## GET /skills/{skill_ref}/assignments

List Skill Assignments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## GET /skills/{skill_ref}/files/{file_path}

Get Skill File

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |
| `file_path` | path | string | yes |  |

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

## PATCH /external-product-maps/{map_id}

Update External Product Map

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `map_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `external_name` | string (≤200 chars) | optional |  |
| `metadata` | object | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## PATCH /product-skus/{sku_id}

Update Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `sku_code` | string (≤64 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `variant_attrs` | object | optional |  |

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

## PATCH /sales-channels/{channel_id}

Update Sales Channel

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `channel_kind` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

## PATCH /skills/{skill_ref}

Update Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `calibration` | string (≤4000 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `distribution_mode` | `capability` | `targeted` | optional |  |
| `files` | object | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤200 chars) | optional |  |

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

## POST /external-product-maps

Create External Product Map

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `source` | string (≤50 chars) | required |  |
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `external_name` | string (≤200 chars) | optional |  |
| `external_product_id` | string (≤128 chars) | optional |  |
| `external_sku_id` | string (≤128 chars) | optional |  |
| `metadata` | object | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /product-skus

Create Product Sku

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `sku_code` | string (≤64 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `variant_attrs` | object | optional |  |

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

## POST /sales-channels

Create Sales Channel

Body:

| field | type | | notes |
|---|---|---|---|
| `channel_code` | string (≤50 chars) | required |  |
| `channel_kind` | string (≤50 chars) | required |  |
| `name` | string (≤100 chars) | required |  |
| `metadata` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /skills

Create Skill

Body:

| field | type | | notes |
|---|---|---|---|
| `files` | object | required |  |
| `name` | string (≤100 chars, pattern `^[a-z0-9]+(-[a-z0-9]+)*$`) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `distribution_mode` | `capability` | `targeted` | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /skills/{skill_ref}/assignments

Add Skill Assignment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `subject_id` | string (≤100 chars) | required |  |
| `subject_type` | `user` | `role` | required |  |
