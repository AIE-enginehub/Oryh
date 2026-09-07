<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-payables: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /invoice-items/{item_id}

Delete Invoice Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /invoices/{invoice_id}

Delete Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /payments/{payment_id}

Delete Payment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## GET /billing-accounts/{account_id}/detail

Get Billing Account Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |
| `entry_limit` | query | integer (≥1, ≤200) | no |  |
| `include_deleted` | query | boolean | no |  |

## GET /contract-terms

List Contract Terms

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `term_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /contracts/{contract_id}/execution

Contract Execution

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## GET /expense-claims/{claim_id}/detail

Get Expense Claim Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /invoice-items

List Invoice Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `sales_order_item_id` | query | string | no |  |
| `purchase_order_item_id` | query | string | no |  |

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

## GET /purchase-orders/{po_id}/detail

Get Purchase Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## GET /supplier-products

List Supplier Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
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

## POST /expense-claims/{claim_id}/invoice

Raise Reimbursement Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

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

## POST /invoices/bulk

Bulk Import Invoices

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `direction` | `sales` | `purchase` | `payroll` | `reimbursement` | required |  |
  | `invoice_no` | string (≤64 chars) | required |  |
  | `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `customer_code` | string (≤64 chars) | optional |  |
  | `customer_id` | string | optional |  |
  | `due_date` | date | optional |  |
  | `employee_code` | string (≤64 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `invoice_date` | date | optional |  |
  | `invoice_type` | string (≤30 chars) | optional |  |
  | `items` | array of objects (fields below) | optional |  |
  | ↳ each `items[]` item: | | | |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
    | `custom_fields` | object | optional |  |
    | `invoice_item_type` | string (≤30 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `notes` | string (≤2000 chars) | optional |  |
    | `product_code` | string (≤64 chars) | optional |  |
    | `product_name_snapshot` | string (≤200 chars) | optional |  |
    | `quantity` | number (≤9999999.99) | optional |  |
    | `sku_code` | string (≤64 chars) | optional |  |
    | `spec` | string (≤200 chars) | optional |  |
    | `tax_amount` | number (≥-9999999.99, ≤9999999.99) | optional |  |
    | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
    | `unit` | string (≤50 chars) | optional |  |
    | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
  | `project_code` | string (≤64 chars) | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `tax_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
  | `tax_invoice_code` | string (≤32 chars) | optional |  |
  | `tax_invoice_number` | string (≤64 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
  | `vendor_code` | string (≤64 chars) | optional |  |
  | `vendor_id` | string | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /invoices/{invoice_id}/restore

Restore Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

## POST /invoices/{invoice_id}/submit

Submit Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

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
