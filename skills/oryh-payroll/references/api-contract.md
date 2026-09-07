<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-payroll: API contract

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

## GET /employees/{employee_id}/pay-history

Get Employee Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `component` | query | string | no |  |
| `in_force_on` | query | date | no |  |

## GET /invoices

List Invoices

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `direction` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `payee_employee_id` | query | string | no |  |
| `invoice_no` | query | string | no |  |
| `tax_invoice_number` | query | string | no |  |
| `sales_order_id` | query | string | no |  |
| `purchase_order_id` | query | string | no |  |
| `expense_claim_id` | query | string | no |  |
| `billing_account_id` | query | string | no |  |
| `period_start` | query | date | no |  |
| `status` | query | string | no |  |
| `outstanding` | query | boolean | no |  |
| `due_before` | query | date | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /invoices/{invoice_id}

Get Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

## GET /invoices/{invoice_id}/attachments/{attachment_id}/content

Get Invoice Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /invoices/{invoice_id}/detail

Get Invoice Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /object-directory

Get Object Directory

## GET /pay-histories

List Pay Histories

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `component` | query | string | no |  |
| `in_force_on` | query | date | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /pay-histories/{record_id}

Get Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `record_id` | path | string | yes |  |

## GET /payment-applications

List Payment Applications

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | query | string | no |  |
| `applied_to_type` | query | string | no |  |
| `applied_to_id` | query | string | no |  |
| `invoice_item_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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
| `status` | query | string | no |  |
| `unapplied` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /payments/{payment_id}

Get Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

## GET /policies

List Policies

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `code` | query | string | no |  |
| `category` | query | string | no |  |
| `status` | query | string | no |  |
| `visibility` | query | string | no |  |
| `in_force_on` | query | date | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /type-options

List Type Options

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `family` | query | string | no |  |
| `status` | query | string | no |  |

## PATCH /invoices/{invoice_id}

Update Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `attachment_id` | string | optional |  |
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `due_date` | date | optional |  |
| `extracted_fields` | object | optional |  |
| `invoice_date` | date | optional |  |
| `invoice_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `payee_employee_id` | string | optional |  |
| `period_end` | date | optional |  |
| `period_start` | date | optional |  |
| `project_id` | string | optional |  |
| `purchase_order_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `tax_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `tax_invoice_code` | string (≤32 chars) | optional |  |
| `tax_invoice_number` | string (≤64 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_id` | string | optional |  |

## PATCH /pay-histories/{record_id}

Update Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `record_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `basis` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_thru` | date | optional |  |
| `formula` | string (≤4000 chars) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `period_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `rate` | number (≥0.0, ≤1000.0) | optional |  |

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

## POST /attachments

Create Attachment

Body:

| field | type | | notes |
|---|---|---|---|
| `content_base64` | string | required |  |
| `content_type` | string (≤100 chars) | required |  |
| `filename` | string (≤255 chars) | required |  |

## POST /invoices

Create Invoice

Body:

| field | type | | notes |
|---|---|---|---|
| `direction` | `sales` | `purchase` | `payroll` | `reimbursement` | required |  |
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `attachment_id` | string | optional |  |
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `due_date` | date | optional |  |
| `extracted_fields` | object | optional |  |
| `invoice_date` | date | optional |  |
| `invoice_no` | string (≤64 chars) | optional |  |
| `invoice_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
  | `custom_fields` | object | optional |  |
  | `invoice_id` | string | optional |  |
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
| `payee_employee_id` | string | optional |  |
| `period_end` | date | optional |  |
| `period_start` | date | optional |  |
| `project_id` | string | optional |  |
| `purchase_order_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `sales_order_id` | string | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `tax_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `tax_invoice_code` | string (≤32 chars) | optional |  |
| `tax_invoice_number` | string (≤64 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_id` | string | optional |  |

## POST /pay-histories

Create Pay History

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_from` | date | required |  |
| `employee_id` | string | required |  |
| `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `basis` | string (≤200 chars) | optional |  |
| `component` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_thru` | date | optional |  |
| `formula` | string (≤4000 chars) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `period_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `rate` | number (≥0.0, ≤1000.0) | optional |  |

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

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
