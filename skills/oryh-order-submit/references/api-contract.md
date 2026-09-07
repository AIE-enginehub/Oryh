<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-order-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /external-document-links/{link_id}

Delete External Document Link

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `link_id` | path | string | yes |  |

## GET /auth/me

Me

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

## GET /product-matches

Match Products By Title

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `title` | query | string (≤300 chars) | yes |  |
| `limit` | query | integer (≥1, ≤20) | no |  |

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
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /sales-orders/{order_id}/detail

Get Sales Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-quotations/{quotation_id}/detail

Get Sales Quotation Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |
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
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

## PATCH /todos/{todo_id}

Update Todo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `todo_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `completed_by` | string (≤100 chars) | optional |  |
| `due_at` | date-time | optional |  |
| `status` | `open` | `completed` | `cancelled` | optional |  |

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

## POST /sales-order-adjustments

Create Sales Order Adjustment

Body:

| field | type | | notes |
|---|---|---|---|
| `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
| `order_id` | string | required |  |
| `description` | string (≤500 chars) | optional |  |
| `metadata` | object | optional |  |
| `order_item_id` | string | optional |  |
| `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

## POST /sales-order-items

Create Sales Order Item

Body:

| field | type | | notes |
|---|---|---|---|
| `order_id` | string | required |  |
| `quantity` | number (≤9999999.99) | required |  |
| `amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `is_gift` | boolean | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `promised_date` | date | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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
