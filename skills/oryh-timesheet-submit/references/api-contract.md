<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-timesheet-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /projects/{project_id}

Delete Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

## DELETE /timesheet-entries/{entry_id}

Delete Timesheet Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

## DELETE /timesheet-headers/{header_id}

Delete Timesheet Header

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

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

## GET /timesheet-entries

List Timesheet Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `header_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `project_id` | query | string | no |  |
| `work_date_from` | query | date | no |  |
| `work_date_to` | query | date | no |  |

## GET /timesheet-entries/{entry_id}

Get Timesheet Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

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
