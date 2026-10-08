<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-leave-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /business-rules/{rule_id}

Delete Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

## DELETE /employee-leaves/{leave_id}

Delete Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /object-type-definitions/{definition_id}

Archive Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

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

## GET /employee-leaves

List Employee Leaves

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `leave_type` | query | string | no |  |
| `status` | query | string | no |  |
| `overlapping_from` | query | date | no |  |
| `overlapping_thru` | query | date | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `from_date_from` | query | date | no | rows whose from_date is on or after this |
| `from_date_thru` | query | date | no | rows whose from_date is on or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `thru_date_from` | query | date | no | rows whose thru_date is on or after this |
| `thru_date_thru` | query | date | no | rows whose thru_date is on or before this |
| `reason` | query | string | no |  |

## GET /employee-leaves/{leave_id}

Get Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

## GET /object-type-definitions/{definition_id}

Get Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

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

## PATCH /employee-leaves/{leave_id}

Update Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `duration_days` | number | optional |  |
| `from_date` | date | optional |  |
| `leave_type` | string (≤50 chars) | optional |  |
| `reason` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `thru_date` | date | optional |  |

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

## PATCH /object-type-definitions/{definition_id}

Update Object Type Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤2000 chars) | optional |  |
| `json_schema` | object | optional |  |
| `state_machine` | object | optional |  |
| `status` | `active` | `archived` | optional |  |
| `title` | string (≤200 chars) | optional |  |

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

## POST /employee-leaves

Create Employee Leave

Body:

| field | type | | notes |
|---|---|---|---|
| `duration_days` | number | required |  |
| `employee_id` | string | required |  |
| `from_date` | date | required |  |
| `leave_type` | string (≤50 chars) | required |  |
| `thru_date` | date | required |  |
| `custom_fields` | object | optional |  |
| `reason` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |

## POST /employee-leaves/{leave_id}/restore

Restore Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

## POST /employee-leaves/{leave_id}/submit

Submit Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

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

## POST /object-type-definitions

Create Object Type Definition

Body:

| field | type | | notes |
|---|---|---|---|
| `object_type` | string (≤100 chars) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `entity_kind` | `business_object` | `builtin` | optional |  |
| `json_schema` | object | optional |  |
| `state_machine` | object | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
