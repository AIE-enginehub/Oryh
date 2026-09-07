<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-purchase-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

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

## GET /auth/me

Me

## GET /billing-accounts

List Billing Accounts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `unit_type` | query | string | no |  |
| `unit` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `account_code` | query | string | no |  |
| `external_account_id` | query | string | no |  |
| `status` | query | string | no |  |
| `over_limit` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /product-skus

List Product Skus

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_code` | query | string | no |  |
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

## GET /purchase-requests/{request_id}/detail

Get Purchase Request Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-orders/{order_id}/detail

Get Sales Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /vendors

List Vendors

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `status` | query | string | no |  |
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

## PATCH /purchase-request-items/{item_id}

Update Purchase Request Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sales_order_item_id` | string | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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

## POST /approval-records

Create Approval Record

Body:

| field | type | | notes |
|---|---|---|---|
| `action` | `submitted` | `approved` | `rejected` | `returned` | `commented` | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `contract` | `employee_leave` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | required |  |
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

## POST /attachments

Create Attachment

Body:

| field | type | | notes |
|---|---|---|---|
| `content_base64` | string | required |  |
| `content_type` | string (≤100 chars) | required |  |
| `filename` | string (≤255 chars) | required |  |

## POST /purchase-request-items

Create Purchase Request Item

Body:

| field | type | | notes |
|---|---|---|---|
| `quantity` | number (≤9999999.99) | required |  |
| `request_id` | string | required |  |
| `amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `sales_order_item_id` | string | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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
