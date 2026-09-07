<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-skill-author: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

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

## GET /auth/me

Me

## GET /builtin-object-types

Get Builtin Object Types

## GET /capabilities

List Capabilities

## GET /my/skills/manifest

My Skills Manifest

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

## GET /product-skus

List Product Skus

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `product_id` | query | string | no |  |
| `sku_code` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /products

List Products

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `category_id` | query | string | no |  |
| `product_type` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## POST /capabilities

Create Capability

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤100 chars, pattern `^[a-z0-9_.]+$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

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

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /users/{user_id}/skill-bundle

Generate Skill Bundle

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `user_id` | path | string | yes |  |

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
