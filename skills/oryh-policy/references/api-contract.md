<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-policy: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /policies/{policy_id}

Delete Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |
| `reason` | query | string (≤500 chars) | no |  |

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

## GET /policies/{policy_id}

Get Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |

## GET /type-options

List Type Options

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `family` | query | string | no |  |
| `status` | query | string | no |  |

## PATCH /policies/{policy_id}

Update Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |

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

## POST /policies

Create Policy

Body:

| field | type | | notes |
|---|---|---|---|
| `body` | string | required |  |
| `category` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `code` | string (≤50 chars) | required |  |
| `title` | string (≤200 chars) | required |  |
| `attachment_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_thru` | date | optional |  |
| `owner_employee_id` | string | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |
| `rules_json` | object | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `visibility` | `internal` | `restricted` | `public` | optional |  |

## POST /policies/{policy_id}/publish

Publish Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_from` | date | optional |  |
| `note` | string (≤2000 chars) | optional |  |

## POST /policies/{policy_id}/repeal

Repeal Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `effective_thru` | date | optional |  |
| `note` | string (≤2000 chars) | optional |  |

## POST /policies/{policy_id}/visibility

Rescope Policy

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `policy_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `visibility` | `internal` | `restricted` | `public` | required |  |
| `note` | string (≤2000 chars) | optional |  |
| `required_capability` | string (≤100 chars) | optional |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
