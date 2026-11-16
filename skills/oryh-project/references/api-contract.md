<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-project: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /contract-terms/{term_id}

Delete Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

## DELETE /project-reports/{report_id}

Delete Project Report

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `report_id` | path | string | yes |  |

## DELETE /project-task-dependencies/{dependency_id}

Delete Project Task Dependency

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `dependency_id` | path | string | yes |  |

## DELETE /project-tasks/{task_id}

Delete Project Task

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `task_id` | path | string | yes |  |

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

## GET /contract-terms

List Contract Terms

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `term_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `document_id` | query | string | no |  |

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

## GET /project-issues

List Project Issues

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | query | string | no |  |
| `task_id` | query | string | no |  |
| `issue_type` | query | string | no |  |
| `severity` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `unresolved` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `raised_at_from` | query | date-time | no | rows whose raised_at is at or after this |
| `raised_at_thru` | query | date-time | no | rows whose raised_at is at or before this |
| `resolved_at_from` | query | date-time | no | rows whose resolved_at is at or after this |
| `resolved_at_thru` | query | date-time | no | rows whose resolved_at is at or before this |

## GET /project-issues/{issue_id}

Get Project Issue

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `issue_id` | path | string | yes |  |

## GET /project-milestones

List Project Milestones

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `due_date_from` | query | date | no | rows whose due_date is on or after this |
| `due_date_thru` | query | date | no | rows whose due_date is on or before this |
| `reached_on_from` | query | date | no | rows whose reached_on is on or after this |
| `reached_on_thru` | query | date | no | rows whose reached_on is on or before this |

## GET /project-milestones/{milestone_id}

Get Project Milestone

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `milestone_id` | path | string | yes |  |

## GET /project-reports

List Project Reports

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | query | string | no |  |
| `health` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `period_start_from` | query | date | no | rows whose period_start is on or after this |
| `period_start_thru` | query | date | no | rows whose period_start is on or before this |
| `period_end_from` | query | date | no | rows whose period_end is on or after this |
| `period_end_thru` | query | date | no | rows whose period_end is on or before this |
| `published_at_from` | query | date-time | no | rows whose published_at is at or after this |
| `published_at_thru` | query | date-time | no | rows whose published_at is at or before this |

## GET /project-reports/{report_id}

Get Project Report

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `report_id` | path | string | yes |  |

## GET /project-task-dependencies

List Project Task Dependencies

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | query | string | no |  |
| `task_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |

## GET /project-tasks

List Project Tasks

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | query | string | no |  |
| `parent_task_id` | query | string | no |  |
| `assignee_employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `planned_start_from` | query | date | no | rows whose planned_start is on or after this |
| `planned_start_thru` | query | date | no | rows whose planned_start is on or before this |
| `planned_end_from` | query | date | no | rows whose planned_end is on or after this |
| `planned_end_thru` | query | date | no | rows whose planned_end is on or before this |
| `actual_start_from` | query | date | no | rows whose actual_start is on or after this |
| `actual_start_thru` | query | date | no | rows whose actual_start is on or before this |
| `actual_end_from` | query | date | no | rows whose actual_end is on or after this |
| `actual_end_thru` | query | date | no | rows whose actual_end is on or before this |

## GET /project-tasks/{task_id}

Get Project Task

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `task_id` | path | string | yes |  |

## GET /projects

List Projects

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `contract_id` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `end_date_from` | query | date | no | rows whose end_date is on or after this |
| `end_date_thru` | query | date | no | rows whose end_date is on or before this |
| `start_date_from` | query | date | no | rows whose start_date is on or after this |
| `start_date_thru` | query | date | no | rows whose start_date is on or before this |

## GET /projects/{project_id}

Get Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

## GET /projects/{project_id}/detail

Get Project Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

## GET /projects/{project_id}/execution

Get Project Execution

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |
| `as_of` | query | date | no |  |

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

## PATCH /contract-terms/{term_id}

Update Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `clause_ref` | string (≤50 chars) | optional |  |
| `content` | string (≤20000 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `term_type` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /project-issues/{issue_id}

Update Project Issue

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `issue_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤10000 chars) | optional |  |
| `issue_type` | string (≤30 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `raised_by_employee_id` | string | optional |  |
| `resolution` | string (≤10000 chars) | optional |  |
| `resolved_at` | date-time | optional |  |
| `severity` | string (≤30 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `task_id` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /project-milestones/{milestone_id}

Update Project Milestone

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `milestone_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contract_term_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `due_date` | date | optional |  |
| `invoice_id` | string | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `status` | `open` | `cancelled` | optional |  |

## PATCH /project-reports/{report_id}

Update Project Report

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `report_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `blockers` | string (≤20000 chars) | optional |  |
| `done` | string (≤20000 chars) | optional |  |
| `health` | `green` | `amber` | `red` | optional |  |
| `next_steps` | string (≤20000 chars) | optional |  |
| `period_end` | date | optional |  |
| `summary` | string (≤20000 chars) | optional |  |

## PATCH /project-tasks/{task_id}

Update Project Task

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `task_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `actual_end` | date | optional |  |
| `actual_start` | date | optional |  |
| `assignee_employee_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_task_id` | string | optional |  |
| `planned_end` | date | optional |  |
| `planned_hours` | number (≥0.0, ≤999999.99) | optional |  |
| `planned_start` | date | optional |  |
| `sort_order` | integer | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `task_code` | string (≤64 chars) | optional |  |

## PATCH /projects/{project_id}

Update Project

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `project_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `client` | string (≤200 chars) | optional |  |
| `contract_id` | string | optional |  |
| `customer_id` | string | optional |  |
| `end_date` | date | optional |  |
| `metadata` | object | optional |  |
| `opportunity_id` | string | optional |  |
| `owner_employee_id` | string | optional |  |
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

## POST /contract-terms

Create Contract Term

Body:

| field | type | | notes |
|---|---|---|---|
| `content` | string (≤20000 chars) | required |  |
| `contract_id` | string | required |  |
| `term_type` | string (≤50 chars) | required |  |
| `clause_ref` | string (≤50 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /notifications

Send Notification

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `event` | string (≤20 chars) | required |  |
| `actor_name` | string (≤200 chars) | optional |  |
| `detail` | string (≤4000 chars) | optional |  |
| `entity_id` | string | optional |  |
| `entity_type` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `todo_id` | string | optional |  |
| `todo_ids` | array of string | optional |  |

## POST /project-issues

Create Project Issue

Body:

| field | type | | notes |
|---|---|---|---|
| `project_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `description` | string (≤10000 chars) | optional |  |
| `issue_no` | string (≤64 chars) | optional |  |
| `issue_type` | string (≤30 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `raised_at` | date-time | optional |  |
| `raised_by_employee_id` | string | optional |  |
| `resolution` | string (≤10000 chars) | optional |  |
| `resolved_at` | date-time | optional |  |
| `severity` | string (≤30 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `task_id` | string | optional |  |

## POST /project-milestones

Create Project Milestone

Body:

| field | type | | notes |
|---|---|---|---|
| `due_date` | date | required |  |
| `name` | string (≤200 chars) | required |  |
| `project_id` | string | required |  |
| `contract_term_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `invoice_id` | string | optional |  |

## POST /project-milestones/{milestone_id}/reach

Reach Project Milestone

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `milestone_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `reached_on` | date | required |  |
| `confirmed_by` | string (≤200 chars) | optional |  |
| `evidence_attachment_id` | string | optional |  |

## POST /project-milestones/{milestone_id}/reopen

Reopen Project Milestone

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `milestone_id` | path | string | yes |  |

## POST /project-reports

Create Project Report

Body:

| field | type | | notes |
|---|---|---|---|
| `health` | `green` | `amber` | `red` | required |  |
| `period_end` | date | required |  |
| `period_start` | date | required |  |
| `project_id` | string | required |  |
| `summary` | string (≤20000 chars) | required |  |
| `blockers` | string (≤20000 chars) | optional |  |
| `done` | string (≤20000 chars) | optional |  |
| `next_steps` | string (≤20000 chars) | optional |  |

## POST /project-reports/{report_id}/publish

Publish Project Report

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `report_id` | path | string | yes |  |

## POST /project-task-dependencies

Create Project Task Dependency

Body:

| field | type | | notes |
|---|---|---|---|
| `predecessor_task_id` | string | required |  |
| `successor_task_id` | string | required |  |
| `dependency_type` | `FS` | `SS` | `FF` | `SF` | optional |  |
| `lag_days` | integer (≥-3650.0, ≤3650.0) | optional |  |

## POST /project-tasks

Create Project Task

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `project_id` | string | required |  |
| `actual_end` | date | optional |  |
| `actual_start` | date | optional |  |
| `assignee_employee_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `parent_task_id` | string | optional |  |
| `planned_end` | date | optional |  |
| `planned_hours` | number (≥0.0, ≤999999.99) | optional |  |
| `planned_start` | date | optional |  |
| `sort_order` | integer | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `task_code` | string (≤64 chars) | optional |  |

## POST /projects

Create Project

Body:

| field | type | | notes |
|---|---|---|---|
| `project_name` | string (≤200 chars) | required |  |
| `client` | string (≤200 chars) | optional |  |
| `contract_id` | string | optional |  |
| `customer_id` | string | optional |  |
| `end_date` | date | optional |  |
| `metadata` | object | optional |  |
| `opportunity_id` | string | optional |  |
| `owner_employee_id` | string | optional |  |
| `project_code` | string (≤64 chars) | optional |  |
| `start_date` | date | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
