<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-ledger: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /business-rules/{rule_id}

Delete Business Rule

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `rule_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

## DELETE /journal-entries/{entry_id}

Delete Journal Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

## GET /accounting-periods

List Accounting Periods

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `period_start_from` | query | date | no | rows whose period_start is on or after this |
| `period_start_thru` | query | date | no | rows whose period_start is on or before this |
| `closed_at_from` | query | date-time | no | rows whose closed_at is at or after this |
| `closed_at_thru` | query | date-time | no | rows whose closed_at is at or before this |

## GET /accounting-settings

Get Accounting Settings

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

## GET /journal-entries

List Journal Entries

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `status` | query | string | no |  |
| `source_type` | query | string | no |  |
| `source_id` | query | string | no |  |
| `source_event` | query | string | no |  |
| `ledger_account_id` | query | string | no |  |
| `reverses_entry_id` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `posting_date_from` | query | date | no | rows whose posting_date is on or after this |
| `posting_date_thru` | query | date | no | rows whose posting_date is on or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `posted_at_from` | query | date-time | no | rows whose posted_at is at or after this |
| `posted_at_thru` | query | date-time | no | rows whose posted_at is at or before this |

## GET /journal-entries/{entry_id}

Get Journal Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

## GET /ledger-accounts

List Ledger Accounts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_type` | query | string | no |  |
| `parent_id` | query | string | no |  |
| `subledger` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `currency` | query | string | no |  |

## GET /ledger-accounts/{account_id}

Get Ledger Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

## GET /ledger-accounts/{account_id}/ledger

Get Account Ledger

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |
| `date_from` | query | date | no |  |
| `date_to` | query | date | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1, ≤1000) | no |  |

## GET /ledger-accounts/{account_id}/parties

Get Account Parties

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |
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

## GET /trial-balance

Get Trial Balance

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `date_from` | query | date | no |  |
| `date_to` | query | date | no |  |

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

## PATCH /journal-entries/{entry_id}

Update Journal Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤4000 chars) | optional |  |
| `lines` | array of objects (fields below) | optional |  |
| `posting_date` | date | optional |  |

## PATCH /ledger-accounts/{account_id}

Update Ledger Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `account_code` | string (≤32 chars) | optional |  |
| `account_type` | `asset` | `liability` | `equity` | `income` | `expense` | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |
| `subledger` | `customer` | `vendor` | `employee` | optional |  |

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

## POST /accounting-periods/close

Close Accounting Period

Body:

| field | type | | notes |
|---|---|---|---|
| `period` | date | required |  |
| `reason` | string (≤2000 chars) | optional |  |

## POST /accounting-periods/reopen

Reopen Accounting Period

Body:

| field | type | | notes |
|---|---|---|---|
| `period` | date | required |  |
| `reason` | string (≤2000 chars) | optional |  |

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

## POST /journal-entries

Create Journal Entry

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤4000 chars) | required |  |
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `ledger_account_id` | string | required |  |
  | `cost_center_id` | string | optional |  |
  | `credit` | number (≥0.0, ≤999999999999.99) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `customer_id` | string | optional |  |
  | `debit` | number (≥0.0, ≤999999999999.99) | optional |  |
  | `description` | string (≤2000 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `exchange_rate` | number | optional |  |
  | `foreign_amount` | number (≤999999999999.99) | optional |  |
  | `project_id` | string | optional |  |
  | `vendor_id` | string | optional |  |
| `posting_date` | date | required |  |
| `entry_no` | string (≤64 chars) | optional |  |
| `source_event` | string (≤60 chars) | optional |  |
| `source_id` | string | optional |  |
| `source_type` | string (≤40 chars) | optional |  |
| `status` | `draft` | `posted` | optional |  |

## POST /journal-entries/{entry_id}/post

Post Journal Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

## POST /journal-entries/{entry_id}/reverse

Reverse Journal Entry

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `entry_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## POST /ledger-accounts

Create Ledger Account

Body:

| field | type | | notes |
|---|---|---|---|
| `account_code` | string (≤32 chars) | required |  |
| `account_type` | `asset` | `liability` | `equity` | `income` | `expense` | required |  |
| `name` | string (≤200 chars) | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `parent_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |
| `subledger` | `customer` | `vendor` | `employee` | optional |  |

## PUT /accounting-settings

Put Accounting Settings

Body:

| field | type | | notes |
|---|---|---|---|
| `functional_currency` | string (≤3 chars) | required |  |
| `retained_earnings_account_id` | string | optional |  |
