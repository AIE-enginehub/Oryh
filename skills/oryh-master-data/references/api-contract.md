<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-master-data: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /bills-of-materials/{bom_id}

Delete Bill Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | path | string | yes |  |

## DELETE /bom-items/{item_id}

Delete Bom Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /customer-contacts/{contact_id}

Delete Customer Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contact_id` | path | string | yes |  |

## DELETE /customer-products/{customer_product_id}

Delete Customer Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_product_id` | path | string | yes |  |

## DELETE /external-product-maps/{map_id}

Delete External Product Map

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `map_id` | path | string | yes |  |

## DELETE /product-categories/{category_id}

Delete Product Category

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `category_id` | path | string | yes |  |

## DELETE /product-images/{image_id}

Delete Product Image

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `image_id` | path | string | yes |  |

## DELETE /product-prices/{price_id}

Delete Product Price

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `price_id` | path | string | yes |  |

## DELETE /products/{product_id}

Delete Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## DELETE /supplier-products/{supplier_product_id}

Delete Supplier Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `supplier_product_id` | path | string | yes |  |

## GET /auth/me

Me

## GET /bills-of-materials

List Bills Of Materials

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## GET /customer-contacts

List Customer Contacts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | query | string | no |  |
| `phone` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /customer-products

List Customer Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `customer_product_code` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /customers

List Customers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `phone` | query | string | no |  |
| `customer_kind` | query | string | no |  |
| `customer_type` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## GET /facilities

List Facilities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `facility_type` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /product-categories

List Product Categories

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `parent_id` | query | string | no |  |
| `root_only` | query | boolean | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /product-images

List Product Images

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `image_type` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /product-matches

Match Products By Title

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `title` | query | string (≤300 chars) | yes |  |
| `limit` | query | integer (≥1, ≤20) | no |  |

## GET /product-prices

List Product Prices

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_id` | query | string | no |  |
| `price_type` | query | string | no |  |
| `currency` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## GET /store-facilities

List Store Facilities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | query | string | no |  |
| `facility_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## GET /stores/{store_id}

Get Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## GET /supplier-products

List Supplier Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## PATCH /bom-items/{item_id}

Update Bom Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `component_product_id` | string | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `quantity` | number (≤99999999.9999) | optional |  |
| `scrap_rate` | number (≥0.0, ≤99.99) | optional |  |
| `unit` | string (≤50 chars) | optional |  |

## PATCH /customer-contacts/{contact_id}

Update Customer Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contact_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | optional |  |
| `is_primary` | boolean | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤100 chars) | optional |  |
| `wechat` | string (≤100 chars) | optional |  |

## PATCH /customer-products/{customer_product_id}

Update Customer Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_product_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `agreed_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `customer_product_code` | string (≤64 chars) | optional |  |
| `customer_product_name` | string (≤200 chars) | optional |  |
| `metadata` | object | optional |  |
| `min_order_quantity` | number (≤9999999.99) | optional |  |
| `order_increment` | number (≤9999999.99) | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## PATCH /facilities/{facility_id}

Update Facility

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `facility_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `address` | string (≤500 chars) | optional |  |
| `facility_code` | string (≤64 chars) | optional |  |
| `facility_type` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

## PATCH /product-categories/{category_id}

Update Product Category

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `category_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `category_code` | string (≤64 chars) | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `parent_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## PATCH /product-images/{image_id}

Update Product Image

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `image_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `caption` | string (≤200 chars) | optional |  |
| `image_type` | string (≤50 chars) | optional |  |
| `is_primary` | boolean | optional |  |
| `metadata` | object | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |

## PATCH /product-prices/{price_id}

Update Product Price

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `price_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `metadata` | object | optional |  |
| `price` | number (≥0.0, ≤9999999.99) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_in_price` | boolean | optional |  |
| `tax_percentage` | number (≥0.0, ≤100.0) | optional |  |

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

## PATCH /store-facilities/{link_id}

Update Store Facility

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `metadata` | object | optional |  |
| `priority` | integer (≥1.0, ≤100.0) | optional |  |
| `remarks` | string (≤500 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## POST /attachments

Create Attachment

Body:

| field | type | | notes |
|---|---|---|---|
| `content_base64` | string | required |  |
| `content_type` | string (≤100 chars) | required |  |
| `filename` | string (≤255 chars) | required |  |

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

## POST /bom-items

Create Bom Item

Body:

| field | type | | notes |
|---|---|---|---|
| `bom_id` | string | required |  |
| `component_product_id` | string | required |  |
| `quantity` | number (≤99999999.9999) | required |  |
| `description` | string (≤500 chars) | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `scrap_rate` | number (≥0.0, ≤99.99) | optional |  |
| `unit` | string (≤50 chars) | optional |  |

## POST /customer-contacts

Create Customer Contact

Body:

| field | type | | notes |
|---|---|---|---|
| `customer_id` | string | required |  |
| `name` | string (≤100 chars) | required |  |
| `email` | string (≤320 chars) | optional |  |
| `is_primary` | boolean | optional |  |
| `metadata` | object | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤100 chars) | optional |  |
| `wechat` | string (≤100 chars) | optional |  |

## POST /customer-products

Create Customer Product

Body:

| field | type | | notes |
|---|---|---|---|
| `customer_id` | string | required |  |
| `product_id` | string | required |  |
| `agreed_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `customer_product_code` | string (≤64 chars) | optional |  |
| `customer_product_name` | string (≤200 chars) | optional |  |
| `metadata` | object | optional |  |
| `min_order_quantity` | number (≤9999999.99) | optional |  |
| `order_increment` | number (≤9999999.99) | optional |  |
| `status` | `active` | `archived` | optional |  |

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
  | `metadata` | object | optional |  |
  | `phone` | string (≤50 chars) | optional |  |
  | `status` | `active` | `archived` | optional |  |
  | `tax_id` | string (≤64 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

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

## POST /facilities

Create Facility

Body:

| field | type | | notes |
|---|---|---|---|
| `facility_type` | string (≤50 chars) | required |  |
| `name` | string (≤100 chars) | required |  |
| `address` | string (≤500 chars) | optional |  |
| `facility_code` | string (≤64 chars) | optional |  |
| `metadata` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## POST /product-categories

Create Product Category

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤100 chars) | required |  |
| `category_code` | string (≤64 chars) | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `parent_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /product-images

Create Product Image

Body:

| field | type | | notes |
|---|---|---|---|
| `attachment_id` | string | required |  |
| `product_id` | string | required |  |
| `caption` | string (≤200 chars) | optional |  |
| `image_type` | string (≤50 chars) | optional |  |
| `is_primary` | boolean | optional |  |
| `metadata` | object | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |

## POST /product-prices

Create Product Price

Body:

| field | type | | notes |
|---|---|---|---|
| `price` | number (≥0.0, ≤9999999.99) | required |  |
| `price_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `product_id` | string | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `metadata` | object | optional |  |
| `sku_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_in_price` | boolean | optional |  |
| `tax_percentage` | number (≥0.0, ≤100.0) | optional |  |

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

## POST /store-facilities

Create Store Facility

Body:

| field | type | | notes |
|---|---|---|---|
| `facility_id` | string | required |  |
| `store_id` | string | required |  |
| `metadata` | object | optional |  |
| `priority` | integer (≥1.0, ≤100.0) | optional |  |
| `remarks` | string (≤500 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

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
