<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-approve: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /business-rules/{rule_id}

Delete Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

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

## DELETE /expense-claims/{claim_id}

Delete Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /invoices/{invoice_id}

Delete Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /product-skus/{sku_id}

Delete Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

## DELETE /products/{product_id}

Delete Product

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | path | string | yes |  |

## DELETE /purchase-requests/{request_id}

Delete Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /sales-orders/{order_id}

Delete Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /sales-quotations/{quotation_id}

Delete Sales Quotation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /stores/{store_id}

Delete Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## DELETE /timesheet-headers/{header_id}

Delete Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /vendors/{vendor_id}

Delete Vendor

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `acted_at_from` | query | date-time | no | rows whose acted_at is at or after this |
| `acted_at_thru` | query | date-time | no | rows whose acted_at is at or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `approver_id` | query | string | no |  |
| `source` | query | string | no |  |

## GET /approval-records/{approval_record_id}

Get Approval Record

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `approval_record_id` | path | string | yes |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `currency` | query | string | no |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

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

## GET /customers/{customer_id}/relations

List Customer Relations Of

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `hire_date_from` | query | date | no | rows whose hire_date is on or after this |
| `hire_date_thru` | query | date | no | rows whose hire_date is on or before this |

## GET /employees/{employee_id}

Get Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

## GET /expense-claims

List Expense Claims

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `claim_date_from` | query | date | no | rows whose claim_date is on or after this |
| `claim_date_thru` | query | date | no | rows whose claim_date is on or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `currency` | query | string | no |  |

## GET /expense-claims/{claim_id}

Get Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /expense-claims/{claim_id}/attachments/{attachment_id}/content

Get Expense Claim Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /expense-claims/{claim_id}/detail

Get Expense Claim Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `due_date_from` | query | date | no | rows whose due_date is on or after this |
| `due_date_thru` | query | date | no | rows whose due_date is on or before this |
| `invoice_date_from` | query | date | no | rows whose invoice_date is on or after this |
| `invoice_date_thru` | query | date | no | rows whose invoice_date is on or before this |
| `issued_at_from` | query | date-time | no | rows whose issued_at is at or after this |
| `issued_at_thru` | query | date-time | no | rows whose issued_at is at or before this |
| `period_end_from` | query | date | no | rows whose period_end is on or after this |
| `period_end_thru` | query | date | no | rows whose period_end is on or before this |
| `period_start_from` | query | date | no | rows whose period_start is on or after this |
| `period_start_thru` | query | date | no | rows whose period_start is on or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `attachment_id` | query | string | no |  |
| `contract_id` | query | string | no |  |
| `currency` | query | string | no |  |
| `invoice_type` | query | string | no |  |
| `project_id` | query | string | no |  |

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

## GET /product-skus

List Product Skus

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_code` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

## GET /product-skus/{sku_id}

Get Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `currency` | query | string | no |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `needed_by_from` | query | date | no | rows whose needed_by is on or after this |
| `needed_by_thru` | query | date | no | rows whose needed_by is on or before this |
| `request_date_from` | query | date | no | rows whose request_date is on or after this |
| `request_date_thru` | query | date | no | rows whose request_date is on or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `currency` | query | string | no |  |

## GET /purchase-requests/{request_id}

Get Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /purchase-requests/{request_id}/attachments/{attachment_id}/content

Get Purchase Request Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /purchase-requests/{request_id}/detail

Get Purchase Request Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `order_date_from` | query | date | no | rows whose order_date is on or after this |
| `order_date_thru` | query | date | no | rows whose order_date is on or before this |
| `promised_date_from` | query | date | no | rows whose promised_date is on or after this |
| `promised_date_thru` | query | date | no | rows whose promised_date is on or before this |
| `shipped_at_from` | query | date-time | no | rows whose shipped_at is at or after this |
| `shipped_at_thru` | query | date-time | no | rows whose shipped_at is at or before this |
| `signed_at_from` | query | date-time | no | rows whose signed_at is at or after this |
| `signed_at_thru` | query | date-time | no | rows whose signed_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `contract_id` | query | string | no |  |
| `currency` | query | string | no |  |
| `project_id` | query | string | no |  |

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
| `closed_at_from` | query | date-time | no | rows whose closed_at is at or after this |
| `closed_at_thru` | query | date-time | no | rows whose closed_at is at or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `quote_date_from` | query | date | no | rows whose quote_date is on or after this |
| `quote_date_thru` | query | date | no | rows whose quote_date is on or before this |
| `sent_at_from` | query | date-time | no | rows whose sent_at is at or after this |
| `sent_at_thru` | query | date-time | no | rows whose sent_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `valid_until_from` | query | date | no | rows whose valid_until is on or after this |
| `valid_until_thru` | query | date | no | rows whose valid_until is on or before this |
| `currency` | query | string | no |  |
| `project_id` | query | string | no |  |
| `revision_of_id` | query | string | no |  |

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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `sales_channel_id` | query | string | no |  |

## GET /stores/{store_id}

Get Store

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | path | string | yes |  |

## GET /timesheet-headers

List Timesheet Headers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `period_end_from` | query | date | no | rows whose period_end is on or after this |
| `period_end_thru` | query | date | no | rows whose period_end is on or before this |
| `period_start_from` | query | date | no | rows whose period_start is on or after this |
| `period_start_thru` | query | date | no | rows whose period_start is on or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |

## GET /timesheet-headers/{header_id}

Get Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /timesheet-headers/{header_id}/detail

Get Timesheet Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
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
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

## GET /vendors/{vendor_id}

Get Vendor

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `vendor_id` | path | string | yes |  |

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

## PATCH /expense-claims/{claim_id}

Update Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `claim_date` | date | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |

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

## PATCH /product-skus/{sku_id}

Update Product Sku

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `sku_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `sku_code` | string (≤64 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `variant_attrs` | object | optional |  |

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

## PATCH /timesheet-headers/{header_id}

Update Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

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

## POST /approval-records

Create Approval Record

Body:

| field | type | | notes |
|---|---|---|---|
| `action` | `submitted` | `approved` | `rejected` | `returned` | `commented` | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | required |  |
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

## POST /expense-claims

Create Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `claim_date` | date | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
  | `claim_id` | string | optional |  |
  | `client` | string (≤200 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `employee_id` | string | optional |  |
  | `expense_date` | date | optional |  |
  | `extracted_fields` | object | optional |  |
  | `invoice_number` | string (≤100 chars) | optional |  |
  | `invoice_type` | `vat_special` | `vat_general` | `vat_electronic` | `receipt` | `other` | optional |  |
  | `merchant` | string (≤200 chars) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `project_id` | string | optional |  |
  | `project_name_snapshot` | string (≤200 chars) | optional |  |
  | `tax_amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `vendor_id` | string | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

## POST /expense-claims/{claim_id}/invoice

Raise Reimbursement Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

## POST /expense-claims/{claim_id}/restore

Restore Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /expense-claims/{claim_id}/save

Save Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number | optional |  |
  | `attachment_id` | string | optional |  |
  | `category` | string | optional |  |
  | `claim_id` | string | optional |  |
  | `client` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `employee_id` | string | optional |  |
  | `expense_date` | date | optional |  |
  | `extracted_fields` | object | optional |  |
  | `id` | string | optional | a live row to keep; absent = a new row |
  | `invoice_number` | string | optional |  |
  | `invoice_type` | `vat_special` | `vat_general` | `vat_electronic` | `receipt` | `other` | optional |  |
  | `merchant` | string | optional |  |
  | `notes` | string | optional |  |
  | `project_id` | string | optional |  |
  | `project_name_snapshot` | string | optional |  |
  | `tax_amount` | number | optional |  |
  | `vendor_id` | string | optional |  |
| `claim_date` | date | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /expense-claims/{claim_id}/submit

Submit Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

## POST /invoices

Create Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

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

## POST /invoices/{invoice_id}/save

Save Invoice Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional | a live row to keep; absent = a new row |
  | `invoice_id` | string | optional |  |
  | `invoice_item_type` | string | optional |  |
  | `line_no` | integer | optional |  |
  | `notes` | string | optional |  |
  | `pay_history_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string | optional |  |
  | `purchase_order_item_id` | string | optional |  |
  | `quantity` | number | optional |  |
  | `sales_order_item_id` | string | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string | optional |  |
  | `tax_amount` | number | optional |  |
  | `tax_rate` | number | optional |  |
  | `unit` | string | optional |  |
  | `unit_price` | number | optional |  |

## POST /invoices/{invoice_id}/submit

Submit Invoice

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `invoice_id` | path | string | yes |  |

## POST /product-skus

Create Product Sku

Body:

| field | type | | notes |
|---|---|---|---|
| `product_id` | string | required |  |
| `list_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `metadata` | object | optional |  |
| `sku_code` | string (≤64 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `variant_attrs` | object | optional |  |

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

## POST /purchase-requests

Create Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

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

## POST /purchase-requests/{request_id}/restore

Restore Purchase Request

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /purchase-requests/{request_id}/save

Save Purchase Request Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `request_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional |  |
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

## POST /sales-orders

Create Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
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

## POST /sales-orders/{order_id}/save

Save Sales Order Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional |  |
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
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `id` | string | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

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

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
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

## POST /sales-quotations/{quotation_id}/save

Save Sales Quotation Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `quotation_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional |  |
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
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `id` | string | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

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

## POST /timesheet-headers

Create Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `period_end` | date | required |  |
| `period_start` | date | required |  |
| `custom_fields` | object | optional |  |
| `entries` | array of objects (fields below) | optional |  |
| ↳ each `entries[]` item: | | | |
  | `client` | string (≤200 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `employee_id` | string | optional |  |
  | `header_id` | string | optional |  |
  | `hours` | number (≤24.0) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `project_id` | string | optional |  |
  | `project_name_snapshot` | string (≤200 chars) | optional |  |
  | `task` | string (≤200 chars) | optional |  |
  | `work_date` | date | optional |  |
  | `work_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

## POST /timesheet-headers/{header_id}/restore

Restore Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /timesheet-headers/{header_id}/save

Save Timesheet Document

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `entries` | array of objects (fields below) | required |  |
| ↳ each `entries[]` item: | | | |
  | `hours` | number (≤24.0) | required |  |
  | `work_date` | date | required |  |
  | `id` | string | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `project_id` | string | optional |  |
  | `task` | string (≤200 chars) | optional |  |
  | `work_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `expected_revision` | string (≤64 chars) | required |  |
| `intent_id` | string (≤100 chars) | required |  |
| `period_end` | date | required |  |
| `period_start` | date | required |  |
| `source_report_text` | string (≤10000 chars) | optional |  |

## POST /timesheet-headers/{header_id}/submit

Submit Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

## POST /todos

Create Todo

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
| `title` | string (≤200 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `due_at` | date-time | optional |  |
| `metadata` | object | optional |  |
| `status` | `open` | `completed` | `cancelled` | optional |  |
| `todo_type` | string (≤50 chars) | optional |  |

## POST /todos/bulk

Bulk Create Todos

Body:

| field | type | | notes |
|---|---|---|---|
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `employee_id` | string | required |  |
  | `entity_id` | string | required |  |
  | `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
  | `title` | string (≤200 chars) | required |  |
  | `created_by` | string (≤100 chars) | optional |  |
  | `description` | string (≤2000 chars) | optional |  |
  | `due_at` | date-time | optional |  |
  | `metadata` | object | optional |  |
  | `status` | `open` | `completed` | `cancelled` | optional |  |
  | `todo_type` | string (≤50 chars) | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

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
