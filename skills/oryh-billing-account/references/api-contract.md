<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-billing-account: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /billing-accounts/{account_id}

Delete Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

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

## POST /billing-accounts/{account_id}/entries

Post Billing Account Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `amount` | number (≥-9999999999.99, ≤9999999999.99) | required |  |
  | `reason` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `effective_at` | date-time | optional |  |
  | `entity_id` | string | optional |  |
  | `entity_type` | string (≤50 chars) | optional |  |
  | `expires_at` | date-time | optional |  |
| `idempotency_key` | string (≤64 chars) | optional |  |

## POST /billing-accounts/{account_id}/restore

Restore Billing Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

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
