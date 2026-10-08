<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-billing-account: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /billing-accounts/{account_id}

Delete Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /business-objects/{business_object_id}

Delete Business Object

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `business_object_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /business-rules/{rule_id}

Delete Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

## DELETE /invoice-items/{item_id}

Delete Invoice Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /object-type-definitions/{definition_id}

Archive Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## DELETE /payments/{payment_id}

Delete Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

## GET /billing-account-entries

List Billing Account Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `billing_account_id` | query | string | no |  |
| `reason` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `effective_at_from` | query | date-time | no | rows whose effective_at is at or after this |
| `effective_at_thru` | query | date-time | no | rows whose effective_at is at or before this |
| `expires_at_from` | query | date-time | no | rows whose expires_at is at or after this |
| `expires_at_thru` | query | date-time | no | rows whose expires_at is at or before this |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `valid_from_from` | query | date | no | rows whose valid_from is on or after this |
| `valid_from_thru` | query | date | no | rows whose valid_from is on or before this |
| `valid_until_from` | query | date | no | rows whose valid_until is on or after this |
| `valid_until_thru` | query | date | no | rows whose valid_until is on or before this |

## GET /billing-accounts/{account_id}

Get Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

## GET /billing-accounts/{account_id}/detail

Get Billing Account Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |
| `entry_limit` | query | integer (≥1, ≤200) | no |  |
| `include_deleted` | query | boolean | no |  |

## GET /billing-accounts/{account_id}/expiring

Get Expiring Billing Account Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |
| `before` | query | date-time | no |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

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

## GET /business-rules

List Business Rules

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `kind` | query | string | no |  |
| `entity_kind` | query | string | no |  |
| `object_type` | query | string | no |  |
| `name` | query | string | no |  |
| `code` | query | string | no |  |
| `category` | query | string | no |  |
| `status` | query | string | no |  |
| `visibility` | query | string | no |  |
| `in_force_on` | query | date | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `effective_from_from` | query | date | no | rows whose effective_from is on or after this |
| `effective_from_thru` | query | date | no | rows whose effective_from is on or before this |
| `effective_thru_from` | query | date | no | rows whose effective_thru is on or after this |
| `effective_thru_thru` | query | date | no | rows whose effective_thru is on or before this |
| `published_at_from` | query | date-time | no | rows whose published_at is at or after this |
| `published_at_thru` | query | date-time | no | rows whose published_at is at or before this |
| `attachment_id` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |
| `supersedes_id` | query | string | no |  |
| `origin` | query | string | no |  |

## GET /business-rules/{rule_id}

Get Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |

## GET /business-rules/{rule_id}/attachments/{attachment_id}/content

Get Business Rule Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /employees

List Employees

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `hire_date_from` | query | date | no | rows whose hire_date is on or after this |
| `hire_date_thru` | query | date | no | rows whose hire_date is on or before this |

## GET /employees/{employee_id}

Get Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

## GET /invoice-items

List Invoice Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `sales_order_item_id` | query | string | no |  |
| `purchase_order_item_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `sku_id` | query | string | no |  |

## GET /invoice-items/{item_id}

Get Invoice Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

## GET /object-type-definitions/{definition_id}

Get Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## GET /payments

List Payments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `direction` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `payee_employee_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `payment_no` | query | string | no |  |
| `reference_no` | query | string | no |  |
| `payment_date_from` | query | date | no |  |
| `payment_date_thru` | query | date | no |  |
| `status` | query | string | no |  |
| `unapplied` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `paid_at_from` | query | date-time | no | rows whose paid_at is at or after this |
| `paid_at_thru` | query | date-time | no | rows whose paid_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `attachment_id` | query | string | no |  |
| `contract_id` | query | string | no |  |
| `currency` | query | string | no |  |

## GET /payments/{payment_id}

Get Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

## GET /payments/{payment_id}/attachments/{attachment_id}/content

Get Payment Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /payments/{payment_id}/detail

Get Payment Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |
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
| `completed_at_from` | query | date-time | no | rows whose completed_at is at or after this |
| `completed_at_thru` | query | date-time | no | rows whose completed_at is at or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `due_at_from` | query | date-time | no | rows whose due_at is at or after this |
| `due_at_thru` | query | date-time | no | rows whose due_at is at or before this |
| `todo_type` | query | string | no |  |

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

## PATCH /billing-accounts/{account_id}

Update Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `credit_limit` | number (≥0.0, ≤9999999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `external_account_id` | string (≤64 chars) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `owner_name_snapshot` | string (≤200 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `frozen` | `closed` | optional |  |
| `valid_from` | date | optional |  |
| `valid_until` | date | optional |  |

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

## PATCH /business-rules/{rule_id}

Update Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `attachment_id` | string | optional |  |
| `body` | string | optional |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_thru` | date | optional |  |
| `owner_employee_id` | string | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `rules_json` | object | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `visibility` | `internal` | `restricted` | `public` | optional |  |

## PATCH /invoice-items/{item_id}

Update Invoice Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `invoice_item_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `pay_history_id` | string | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `purchase_order_item_id` | string | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sales_order_item_id` | string | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `tax_amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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

## PATCH /payments/{payment_id}

Update Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≤9999999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `bank_account` | string (≤200 chars) | optional |  |
| `contract_id` | string | optional |  |
| `counterparty_account` | string (≤200 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `payee_employee_id` | string | optional |  |
| `payment_date` | date | optional |  |
| `payment_method` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `reference_no` | string (≤100 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `vendor_id` | string | optional |  |

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

## POST /billing-accounts

Create Billing Account

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `unit` | string (≤30 chars) | required |  |
| `unit_type` | `currency` | `points` | required |  |
| `account_code` | string (≤64 chars) | optional |  |
| `credit_limit` | number (≥0.0, ≤9999999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `employee_id` | string | optional |  |
| `external_account_id` | string (≤64 chars) | optional |  |
| `opening_balance` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
| `owner_name_snapshot` | string (≤200 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | `active` | `frozen` | `closed` | optional |  |
| `valid_from` | date | optional |  |
| `valid_until` | date | optional |  |
| `vendor_id` | string | optional |  |

## POST /billing-accounts/{account_id}/expire

Expire Billing Account Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `amount` | number (≤9999999999.99) | required |  |
  | `entry_id` | string | required |  |
  | `description` | string (≤500 chars) | optional |  |

## POST /billing-accounts/{account_id}/restore

Restore Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

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

## POST /business-rules

Create Business Rule

Body:

| field | type | | notes |
|---|---|---|---|
| `body` | string | required |  |
| `attachment_id` | string | optional |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `code` | string (≤50 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_thru` | date | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `kind` | `policy` | `approval_flow` | `data_rule` | `linkage` | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `object_type` | string (≤100 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `rules_json` | object | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `visibility` | `internal` | `restricted` | `public` | optional |  |

## POST /business-rules/publish

Publish Business Rule Now

Body:

| field | type | | notes |
|---|---|---|---|
| `body` | string | required |  |
| `attachment_id` | string | optional |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `code` | string (≤50 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_thru` | date | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `kind` | `policy` | `approval_flow` | `data_rule` | `linkage` | optional |  |
| `name` | string (≤100 chars) | optional |  |
| `note` | string (≤2000 chars) | optional |  |
| `object_type` | string (≤100 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `rules_json` | object | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `visibility` | `internal` | `restricted` | `public` | optional |  |

## POST /business-rules/{rule_id}/publish

Publish Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_from` | date | optional |  |
| `note` | string (≤2000 chars) | optional |  |

## POST /business-rules/{rule_id}/repeal

Repeal Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_thru` | date | optional |  |
| `note` | string (≤2000 chars) | optional |  |

## POST /business-rules/{rule_id}/visibility

Rescope Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `visibility` | `internal` | `restricted` | `public` | required |  |
| `note` | string (≤2000 chars) | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |

## POST /invoice-items

Create Invoice Item

Body:

| field | type | | notes |
|---|---|---|---|
| `invoice_id` | string | required |  |
| `amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `invoice_item_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `pay_history_id` | string | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `purchase_order_item_id` | string | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sales_order_item_id` | string | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `tax_amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
| `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

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

## POST /payments

Create Payment

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≤9999999999.99) | required |  |
| `direction` | `inbound` | `outbound` | required |  |
| `employee_id` | string | required |  |
| `attachment_id` | string | optional |  |
| `bank_account` | string (≤200 chars) | optional |  |
| `contract_id` | string | optional |  |
| `counterparty_account` | string (≤200 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `payee_employee_id` | string | optional |  |
| `payment_date` | date | optional |  |
| `payment_method` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `payment_no` | string (≤64 chars) | optional |  |
| `reference_no` | string (≤100 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `vendor_id` | string | optional |  |

## POST /payments/bulk

Bulk Import Payments

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `amount` | number (≤9999999999.99) | required |  |
  | `direction` | `inbound` | `outbound` | required |  |
  | `payment_no` | string (≤64 chars) | required |  |
  | `bank_account` | string (≤200 chars) | optional |  |
  | `counterparty_account` | string (≤200 chars) | optional |  |
  | `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `customer_code` | string (≤64 chars) | optional |  |
  | `customer_id` | string | optional |  |
  | `employee_code` | string (≤64 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `payee_employee_code` | string (≤64 chars) | optional |  |
  | `payee_employee_id` | string | optional |  |
  | `payment_date` | date | optional |  |
  | `payment_method` | string (≤30 chars) | optional |  |
  | `reference_no` | string (≤100 chars) | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `vendor_code` | string (≤64 chars) | optional |  |
  | `vendor_id` | string | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /payments/{payment_id}/apply

Apply Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `amount_applied` | number (≥-9999999999.99, ≤9999999999.99) | required |  |
  | `applied_to_id` | string | required |  |
  | `applied_to_type` | `invoice` | `expense_claim` | `billing_account` | `payment` | required |  |
  | `invoice_item_id` | string | optional |  |
  | `note` | string (≤500 chars) | optional |  |
| `idempotency_key` | string (≤64 chars) | optional |  |

## POST /payments/{payment_id}/restore

Restore Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

## POST /payments/{payment_id}/submit

Submit Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
