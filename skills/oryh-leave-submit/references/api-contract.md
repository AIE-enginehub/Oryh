<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-leave-submit: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /employee-leaves/{leave_id}

Delete Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

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

## GET /employee-leaves/{leave_id}

Get Employee Leave

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `leave_id` | path | string | yes |  |

## GET /employees/{employee_id}

Get Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

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
