<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-skill-sync: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

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

## GET /connect-skill

Download Connect Skill

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

## GET /my/skill-bundle

My Skill Bundle

## GET /my/skills/manifest

My Skills Manifest

## GET /my/skills/reach

My Skill Reach

## GET /skills

List Skills

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `status` | query | `active` | `archived` | `all` | no |  |
| `kind` | query | `product` | `custom` | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /skills/{skill_ref}

Get Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## GET /skills/{skill_ref}/assignments

List Skill Assignments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## GET /skills/{skill_ref}/files/{file_path}

Get Skill File

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |
| `file_path` | path | string | yes |  |

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
