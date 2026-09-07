<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-expense-submit: API contract

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

## GET /projects

List Projects

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
