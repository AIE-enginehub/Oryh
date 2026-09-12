<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-access-admin: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /capabilities/{name}

Delete Capability

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `name` | path | string | yes |  |

## DELETE /roles/{role_ref}

Delete Role

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `role_ref` | path | string | yes |  |

## DELETE /skills/{skill_ref}

Archive Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

## DELETE /skills/{skill_ref}/assignments/{assignment_id}

Remove Skill Assignment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |
| `assignment_id` | path | string | yes |  |

## GET /audit-logs

List Audit Logs

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `action` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `actor` | query | string | no |  |
| `before` | query | integer | no |  |
| `limit` | query | integer | no |  |

## GET /auth/users

List Users

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `status` | query | `invited` | `active` | `disabled` | no |  |
| `role` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /capabilities

List Capabilities

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

## GET /roles

List Roles

## GET /roles/{role_ref}/skills

Role Skill Reach

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `role_ref` | path | string | yes |  |

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

## GET /tenant/api-keys

List Api Keys

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `user_id` | query | string | no |  |
| `status` | query | `active` | `inactive` | `all` | no |  |
| `is_active` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

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

## GET /users/{user_id}/skills

User Skill Reach

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |

## PATCH /auth/users/{user_id}

Update User

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | optional |  |
| `employee_id` | string | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `role` | string | optional |  |
| `status` | `active` | `disabled` | optional |  |

## PATCH /roles/{role_ref}

Update Role

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `role_ref` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤2000 chars) | optional |  |
| `permissions` | array of string | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /skills/{skill_ref}

Update Skill

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `calibration` | string (≤4000 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `distribution_mode` | `capability` | `targeted` | optional |  |
| `files` | object | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
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

## POST /auth/invitations

Invite User

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | required |  |
| `employee_id` | string | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `role` | string | optional |  |

## POST /auth/users/{user_id}/password-reset-email

Request Password Reset Email

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |

## POST /auth/users/{user_id}/resend-invitation

Resend Invitation

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |

## POST /capabilities

Create Capability

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤100 chars, pattern `^[a-z0-9_.]+$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /roles

Create Role

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤50 chars, pattern `^[a-z0-9_]+$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `permissions` | array of string | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /skills

Create Skill

Body:

| field | type | | notes |
|---|---|---|---|
| `files` | object | required |  |
| `name` | string (≤100 chars, pattern `^[a-z0-9]+(-[a-z0-9]+)*$`) | required |  |
| `created_by` | string (≤100 chars) | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `distribution_mode` | `capability` | `targeted` | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /skills/{skill_ref}/assignments

Add Skill Assignment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `skill_ref` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `subject_id` | string (≤100 chars) | required |  |
| `subject_type` | `user` | `role` | required |  |

## POST /users/{user_id}/skill-bundle

Generate Skill Bundle

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |
