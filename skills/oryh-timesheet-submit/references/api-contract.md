<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-timesheet-submit: API contract

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

## GET /projects

List Projects

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## GET /timesheet-headers/{header_id}/detail

Get Timesheet Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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

## PATCH /timesheet-entries/{entry_id}

Update Timesheet Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `client` | string (≤200 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `hours` | number (≤24.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `project_name_snapshot` | string (≤200 chars) | optional |  |
| `task` | string (≤200 chars) | optional |  |
| `work_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |

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

## POST /timesheet-entries

Create Timesheet Entry

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `header_id` | string | required |  |
| `hours` | number (≤24.0) | required |  |
| `work_date` | date | required |  |
| `client` | string (≤200 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `project_name_snapshot` | string (≤200 chars) | optional |  |
| `task` | string (≤200 chars) | optional |  |
| `work_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |

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

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
