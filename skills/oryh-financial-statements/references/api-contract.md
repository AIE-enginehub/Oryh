<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-financial-statements: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## GET /accounting-settings

Get Accounting Settings

## GET /balance-sheet

Get Balance Sheet

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `as_of` | query | date | no | default: today |
| `compare` | query | string | no | previous_period (default: the end of the month before), previous_year or none |

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

## GET /income-statement

Get Income Statement

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `date_from` | query | string | no | YYYY-MM-DD, or year_start for the start of the financial year date_to falls in; default: the first of date_to's month, or of this month |
| `date_to` | query | date | no | default: the end of date_from's month, or of this month |
| `compare` | query | string | no | previous_period (default), previous_year or none |
| `by` | query | string | no | split every figure by one of project, cost_center, customer, vendor, employee, month; lines without it fall under `unassigned` |

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

## GET /ledger-coverage

Get Ledger Coverage

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `period` | query | date | yes | any day of the month to read |
| `families` | query | string | no | comma-separated; default invoice,payment,expense_claim,fin_account_transaction. Also payment_application, invoice_offset, billing_account_entry |

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
