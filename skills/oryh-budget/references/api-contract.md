<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-budget: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /budget-changes/{change_id}

Delete Budget Change

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |

## DELETE /budgets/{budget_id}

Delete Budget

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

## DELETE /business-rules/{rule_id}

Delete Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

## GET /budget-cash

Budget Cash

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `income_budget_id` | query | string | no |  |
| `spend_budget_id` | query | string | no |  |

## GET /budget-changes

List Budget Changes

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | query | string | no |  |
| `change_type` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `posted_at_from` | query | date-time | no | rows whose posted_at is at or after this |
| `posted_at_thru` | query | date-time | no | rows whose posted_at is at or before this |
| `employee_id` | query | string | no |  |
| `source_budget_id` | query | string | no |  |

## GET /budget-changes/{change_id}

Get Budget Change

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |

## GET /budget-entries

List Budget Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | query | string | no |  |
| `budget_line_id` | query | string | no |  |
| `change_id` | query | string | no |  |
| `period_month` | query | date | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `period_month_from` | query | date | no | rows whose period_month is on or after this |
| `period_month_thru` | query | date | no | rows whose period_month is on or before this |
| `entry_type` | query | string | no |  |

## GET /budget-impact

Budget Impact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entity_type` | query | string | yes |  |
| `entity_id` | query | string | yes |  |

## GET /budget-lines

List Budget Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | query | string | no |  |
| `category` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `owner_employee_id` | query | string | no |  |

## GET /budget-lines/{line_id}/availability

Budget Line Availability

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `line_id` | path | string | yes |  |
| `amount` | query | number (≥0) | no |  |

## GET /budget-lines/{line_id}/documents

Budget Line Documents

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `line_id` | path | string | yes |  |
| `stage` | query | string | no |  |

## GET /budgets

List Budgets

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `direction` | query | string | no |  |
| `budget_type` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `period_start_from` | query | date | no | rows whose period_start is on or after this |
| `period_start_thru` | query | date | no | rows whose period_start is on or before this |
| `period_end_from` | query | date | no | rows whose period_end is on or after this |
| `period_end_thru` | query | date | no | rows whose period_end is on or before this |
| `activated_at_from` | query | date-time | no | rows whose activated_at is at or after this |
| `activated_at_thru` | query | date-time | no | rows whose activated_at is at or before this |
| `closed_at_from` | query | date-time | no | rows whose closed_at is at or after this |
| `closed_at_thru` | query | date-time | no | rows whose closed_at is at or before this |
| `currency` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |

## GET /budgets/{budget_id}

Get Budget

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

## GET /budgets/{budget_id}/execution

Budget Execution

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |
| `by_month` | query | boolean | no |  |

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

## PATCH /budget-changes/{change_id}

Update Budget Change

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `change_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `custom_fields` | object | optional |  |
| `reason` | string (≤4000 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |

## PATCH /budget-lines/{line_id}

Update Budget Line

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `line_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `status` | `active` | `closed` | optional |  |

## PATCH /budgets/{budget_id}

Update Budget

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `budget_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `cost_center_id` | string | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `period_end` | date | optional |  |
| `period_start` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |

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

## POST /budget-changes

Create Budget Change

Body:

| field | type | | notes |
|---|---|---|---|
| `budget_id` | string | required |  |
| `employee_id` | string | required |  |
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `amount` | number (≥-999999999999.99, ≤999999999999.99) | required |  |
  | `period_month` | date | required |  |
  | `budget_line_id` | string | optional |  |
  | `line_code` | string (≤64 chars) | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `note` | string (≤2000 chars) | optional |  |
| `reason` | string (≤4000 chars) | required |  |
| `change_no` | string (≤64 chars) | optional |  |
| `change_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `custom_fields` | object | optional |  |
| `source_budget_id` | string | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /budget-changes/{change_id}/restore

Restore Budget Change

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |

## POST /budget-changes/{change_id}/save

Save Budget Change Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number | optional |  |
  | `budget_line_id` | string | optional |  |
  | `id` | string | optional | a live row to keep; absent = a new row |
  | `line_code` | string | optional |  |
  | `line_no` | integer | optional |  |
  | `note` | string | optional |  |
  | `period_month` | date | optional |  |

## POST /budget-changes/{change_id}/submit

Submit Budget Change

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `change_id` | path | string | yes |  |

## POST /budget-lines

Create Budget Line

Body:

| field | type | | notes |
|---|---|---|---|
| `budget_id` | string | required |  |
| `line_code` | string (≤64 chars) | required |  |
| `name` | string (≤200 chars) | required |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `customer_id` | string | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `employee_id` | string | optional |  |
| `metadata` | object | optional |  |
| `owner_employee_id` | string | optional |  |
| `parent_line_id` | string | optional |  |
| `product_category_id` | string | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `status` | `active` | `closed` | optional |  |
| `territory_id` | string | optional |  |

## POST /budgets

Create Budget

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `period_end` | date | required |  |
| `period_start` | date | required |  |
| `budget_no` | string (≤64 chars) | optional |  |
| `budget_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `cost_center_id` | string | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `direction` | `spend` | `income` | optional |  |
| `lines` | array of objects (fields below) | optional |  |
| ↳ each `lines[]` item: | | | |
  | `line_code` | string (≤64 chars) | required |  |
  | `name` | string (≤200 chars) | required |  |
  | `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
  | `description` | string (≤2000 chars) | optional |  |
  | `metadata` | object | optional |  |
  | `owner_employee_id` | string | optional |  |
  | `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `owner_employee_id` | string | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /budgets/{budget_id}/close

Close Budget

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

## POST /budgets/{budget_id}/import

Import Budget Plan

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `reason` | string (≤4000 chars) | required |  |
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `amount` | number (≤999999999999.99) | required |  |
  | `line_code` | string (≤64 chars) | required |  |
  | `period_month` | date | required |  |
  | `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
  | `name` | string (≤200 chars) | optional |  |
| `dry_run` | boolean | optional |  |
| `post` | boolean | optional |  |

## POST /budgets/{budget_id}/restore

Restore Budget

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `budget_id` | path | string | yes |  |

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

## POST /todos

Create Todo

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `budget` | `budget_change` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
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
  | `entity_type` | `budget` | `budget_change` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
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
