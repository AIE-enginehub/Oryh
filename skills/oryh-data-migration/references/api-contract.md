<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-data-migration: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /customers/{customer_id}

Delete Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

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

## DELETE /products/{product_id}

Delete Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## DELETE /purchase-orders/{po_id}

Delete Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## DELETE /sales-orders/{order_id}

Delete Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /sales-quotations/{quotation_id}

Delete Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

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

## GET /employees/{employee_id}/pay-history

Get Employee Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `component` | query | string | no |  |
| `in_force_on` | query | date | no |  |

## GET /employees/{employee_id}/todos

List Employee Todos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `status` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /purchase-orders/{po_id}

Get Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

## GET /purchase-orders/{po_id}/attachments/{attachment_id}/content

Get Purchase Order Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /purchase-orders/{po_id}/detail

Get Purchase Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

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
| `supersedes_order_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /sales-orders/{order_id}

Get Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-orders/{order_id}/attachments/{attachment_id}/content

Get Sales Order Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /sales-orders/{order_id}/detail

Get Sales Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-quotations

List Sales Quotations

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `quote_number` | query | string | no |  |
| `valid_before` | query | date | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /sales-quotations/{quotation_id}

Get Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-quotations/{quotation_id}/attachments/{attachment_id}/content

Get Sales Quotation Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /sales-quotations/{quotation_id}/detail

Get Sales Quotation Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |
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

## PATCH /employees/{employee_id}

Update Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

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

## PATCH /purchase-orders/{po_id}

Update Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `order_date` | date | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `promised_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_id` | string | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

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
| `shipped_at` | date-time | optional |  |
| `signed_at` | date-time | optional |  |
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

## PATCH /sales-quotations/{quotation_id}

Update Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contact_email` | string (≤320 chars) | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `outcome_note` | string (≤2000 chars) | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `quote_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
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

## POST /employees

Create Employee

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

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

## POST /purchase-orders

Create Purchase Order

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `vendor_id` | string | required |  |
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `po_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `purchase_request_item_id` | string | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `order_date` | date | optional |  |
| `order_kind` | `order` | `return` | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `po_number` | string (≤64 chars) | optional |  |
| `promised_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |

## POST /purchase-orders/bulk

Bulk Import Purchase Orders

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `po_number` | string (≤64 chars) | required |  |
  | `adjustments` | array of objects (fields below) | optional |  |
  | ↳ each `adjustments[]` item: | | | |
    | `adjustment_type` | string (≤20 chars) | required |  |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
    | `description` | string (≤500 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `metadata` | object | optional |  |
    | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `contract_no` | string (≤64 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
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
  | `promised_date` | date | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
  | `vendor_code` | string (≤64 chars) | optional |  |
  | `vendor_id` | string | optional |  |
  | `vendor_name_snapshot` | string (≤200 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /purchase-orders/{po_id}/receive

Receive Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `po_item_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `bin_number` | string (≤64 chars) | optional |  |
  | `expire_date` | date | optional |  |
  | `facility` | string (≤100 chars) | optional |  |
  | `lot_id` | string (≤64 chars) | optional |  |
  | `unit_cost` | number (≥0.0, ≤9999999.99) | optional |  |

## POST /purchase-orders/{po_id}/restore

Restore Purchase Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `po_id` | path | string | yes |  |

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
| `opportunity_id` | string | optional |  |
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

## POST /sales-orders/{order_id}/release

Release Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤500 chars) | optional |  |
| `lines` | array of objects (fields below) | optional |  |

## POST /sales-orders/{order_id}/reserve

Reserve Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `inventory_item_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `order_item_id` | string | optional |  |
| `description` | string (≤500 chars) | optional |  |

## POST /sales-orders/{order_id}/restore

Restore Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /sales-orders/{order_id}/revise

Revise Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `reason` | string (≤2000 chars) | optional |  |

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

## POST /sales-quotations

Create Sales Quotation

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `contact_email` | string (≤320 chars) | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
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
  | `lead_time` | string (≤100 chars) | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `quotation_id` | string | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `opportunity_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `quote_date` | date | optional |  |
| `quote_number` | string (≤64 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `valid_until` | date | optional |  |

## POST /sales-quotations/bulk

Bulk Import Sales Quotations

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `quote_number` | string (≤64 chars) | required |  |
  | `adjustments` | array of objects (fields below) | optional |  |
  | ↳ each `adjustments[]` item: | | | |
    | `adjustment_type` | string (≤20 chars) | required |  |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
    | `description` | string (≤500 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `metadata` | object | optional |  |
    | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `contact_email` | string (≤320 chars) | optional |  |
  | `contact_name` | string (≤200 chars) | optional |  |
  | `contact_phone` | string (≤50 chars) | optional |  |
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
  | `outcome_note` | string (≤2000 chars) | optional |  |
  | `payment_terms` | string (≤2000 chars) | optional |  |
  | `project_code` | string (≤64 chars) | optional |  |
  | `quote_date` | date | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
  | `valid_until` | date | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /sales-quotations/{quotation_id}/close

Close Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `outcome` | `accepted` | `declined` | `expired` | required |  |
| `closed_by` | string | optional |  |
| `outcome_note` | string (≤2000 chars) | optional |  |
| `source` | `web` | `api` | `ai` | `system` | optional |  |

## POST /sales-quotations/{quotation_id}/restore

Restore Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /sales-quotations/{quotation_id}/revise

Revise Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `reason` | string (≤2000 chars) | optional |  |
| `revised_by` | string | optional |  |
| `source` | `web` | `api` | `ai` | `system` | optional |  |

## POST /sales-quotations/{quotation_id}/send

Send Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `sent_at` | date-time | optional |  |
| `sent_by` | string | optional |  |
| `source` | `web` | `api` | `ai` | `system` | optional |  |

## POST /sales-quotations/{quotation_id}/submit

Submit Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |
