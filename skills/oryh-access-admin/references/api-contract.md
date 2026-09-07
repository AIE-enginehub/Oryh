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

## GET /roles

List Roles

## GET /roles/{role_ref}/skills

Role Skill Reach

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `role_ref` | path | string | yes |  |

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

## POST /users/{user_id}/skill-bundle

Generate Skill Bundle

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |
