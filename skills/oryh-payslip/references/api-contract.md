<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-payslip: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

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

## GET /payments/{payment_id}/detail

Get Payment Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `payment_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |
