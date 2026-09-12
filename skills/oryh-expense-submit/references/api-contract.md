<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-expense-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /expense-claims/{claim_id}

Delete Expense Claim

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /expense-items/{item_id}

Delete Expense Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /projects/{project_id}

Delete Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

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

## GET /auth/me

Me

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

## GET /expense-items

List Expense Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `claim_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `project_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `invoice_number` | query | string | no |  |
| `expense_date_from` | query | date | no |  |
| `expense_date_to` | query | date | no |  |

## GET /expense-items/{item_id}

Get Expense Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## GET /projects

List Projects

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /projects/{project_id}

Get Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /workflow-definitions/{definition_id}

Get Workflow Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

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

## PATCH /expense-items/{item_id}

Update Expense Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≤9999999.99) | optional |  |
| `attachment_id` | string | optional |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `client` | string (≤200 chars) | optional |  |
| `custom_fields` | object | optional |  |
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

## PATCH /projects/{project_id}

Update Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `client` | string (≤200 chars) | optional |  |
| `end_date` | date | optional |  |
| `metadata` | object | optional |  |
| `project_code` | string (≤64 chars) | optional |  |
| `project_name` | string (≤200 chars) | optional |  |
| `start_date` | date | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## POST /expense-items

Create Expense Item

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≤9999999.99) | required |  |
| `claim_id` | string | required |  |
| `employee_id` | string | required |  |
| `expense_date` | date | required |  |
| `attachment_id` | string | optional |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `client` | string (≤200 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `extracted_fields` | object | optional |  |
| `invoice_number` | string (≤100 chars) | optional |  |
| `invoice_type` | `vat_special` | `vat_general` | `vat_electronic` | `receipt` | `other` | optional |  |
| `merchant` | string (≤200 chars) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `project_name_snapshot` | string (≤200 chars) | optional |  |
| `tax_amount` | number (≥0.0, ≤9999999.99) | optional |  |
| `vendor_id` | string | optional |  |

## POST /projects

Create Project

Body:

| field | type | | notes |
|---|---|---|---|
| `project_name` | string (≤200 chars) | required |  |
| `client` | string (≤200 chars) | optional |  |
| `end_date` | date | optional |  |
| `metadata` | object | optional |  |
| `project_code` | string (≤64 chars) | optional |  |
| `start_date` | date | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## POST /workflow-definitions

Publish Workflow Definition

Body:

| field | type | | notes |
|---|---|---|---|
| `definition_text` | string (≤20000 chars) | required |  |
| `object_type` | string (≤100 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `name` | string (≤100 chars) | optional |  |
