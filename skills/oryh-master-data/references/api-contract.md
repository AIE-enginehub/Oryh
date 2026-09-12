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

## DELETE /customers/{customer_id}

Delete Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

## DELETE /external-document-links/{link_id}

Delete External Document Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

## DELETE /external-product-maps/{map_id}

Delete External Product Map

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `map_id` | path | string | yes |  |

## DELETE /facilities/{facility_id}

Delete Facility

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `facility_id` | path | string | yes |  |

## DELETE /inventory-items/{item_id}

Delete Inventory Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

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

## DELETE /store-facilities/{link_id}

Delete Store Facility

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

## DELETE /stores/{store_id}

Delete Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## DELETE /supplier-products/{supplier_product_id}

Delete Supplier Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `supplier_product_id` | path | string | yes |  |

## DELETE /territory-geos/{row_id}

Delete Territory Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## DELETE /territory-members/{row_id}

Delete Territory Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

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

## GET /attachments/{attachment_id}

Get Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `attachment_id` | path | string | yes |  |

## GET /attachments/{attachment_id}/content

Get Attachment Content

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `attachment_id` | path | string | yes |  |

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

## GET /bom-items

List Bom Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `bom_id` | query | string | no |  |
| `component_product_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /customer-contacts/{contact_id}

Get Customer Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contact_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /customer-products/{customer_product_id}

Get Customer Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_product_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /external-document-links/{link_id}

Get External Document Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

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

## GET /facilities

List Facilities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `facility_type` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /facilities/{facility_id}

Get Facility

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `facility_id` | path | string | yes |  |

## GET /geos

List Geos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_type` | query | string | no |  |
| `parent_geo_id` | query | string | no |  |
| `geo_code` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /geos/{geo_id}

Get Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

## GET /geos/{geo_id}/path

Get Geo Path

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /product-categories/{category_id}

Get Product Category

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `category_id` | path | string | yes |  |

## GET /product-images

List Product Images

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `image_type` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /product-prices/{price_id}

Get Product Price

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `price_id` | path | string | yes |  |

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

## GET /store-facilities

List Store Facilities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | query | string | no |  |
| `facility_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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

## GET /territories

List Territories

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `parent_territory_id` | query | string | no |  |
| `manager_employee_id` | query | string | no |  |
| `territory_code` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /territories/{territory_id}

Get Territory

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `territory_id` | path | string | yes |  |

## GET /territory-geos

List Territory Geos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `territory_id` | query | string | no |  |
| `geo_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /territory-geos/{row_id}

Get Territory Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## GET /territory-members

List Territory Members

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `territory_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `role` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /territory-members/{row_id}

Get Territory Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## GET /territory-resolution

Resolve

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | query | string | yes | The place to resolve — a customer's geo, or any geo |

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

## PATCH /geos/{geo_id}

Update Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `abbreviation` | string (≤50 chars) | optional |  |
| `geo_type` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_geo_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## PATCH /territories/{territory_id}

Update Territory

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `territory_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤4000 chars) | optional |  |
| `manager_employee_id` | string | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_territory_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## PATCH /territory-members/{row_id}

Update Territory Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `metadata` | object | optional |  |
| `role` | string (≤50 chars) | optional |  |
| `valid_from` | date | optional |  |
| `valid_until` | date | optional |  |

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
| `split` | boolean | optional |  |

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

## POST /geos

Create Geo

Body:

| field | type | | notes |
|---|---|---|---|
| `geo_code` | string (≤64 chars) | required |  |
| `geo_type` | string (≤50 chars) | required |  |
| `name` | string (≤200 chars) | required |  |
| `abbreviation` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `parent_geo_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /geos/seed-template

Seed Geo Template

Body:

| field | type | | notes |
|---|---|---|---|
| `template` | string | required |  |

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

## POST /territories

Create Territory

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `territory_code` | string (≤64 chars) | required |  |
| `description` | string (≤4000 chars) | optional |  |
| `manager_employee_id` | string | optional |  |
| `metadata` | object | optional |  |
| `parent_territory_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /territory-geos

Create Territory Geo

Body:

| field | type | | notes |
|---|---|---|---|
| `geo_id` | string | required |  |
| `territory_id` | string | required |  |
| `metadata` | object | optional |  |

## POST /territory-members

Create Territory Member

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `territory_id` | string | required |  |
| `metadata` | object | optional |  |
| `role` | string (≤50 chars) | optional |  |
| `valid_from` | date | optional |  |
| `valid_until` | date | optional |  |

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
