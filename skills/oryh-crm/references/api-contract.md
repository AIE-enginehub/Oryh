<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-crm: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /leads/{lead_id}

Delete Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

## GET /customers

List Customers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `phone` | query | string | no |  |
| `customer_kind` | query | string | no |  |
| `customer_type` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /leads

List Leads

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `source` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /opportunities

List Opportunities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

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

## PATCH /leads/{lead_id}

Update Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `company_name` | string (≤200 chars) | optional |  |
| `contact_name` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source` | string (≤100 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `wechat` | string (≤100 chars) | optional |  |

## PATCH /opportunities/{opportunity_id}

Update Opportunity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `expected_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `expected_close_date` | date | optional |  |
| `lead_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /leads

Create Lead

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `company_name` | string (≤200 chars) | optional |  |
| `contact_name` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `lead_no` | string (≤64 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source` | string (≤100 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `wechat` | string (≤100 chars) | optional |  |

## POST /leads/{lead_id}/convert

Convert Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `customer_id` | string | optional |  |
| `customer_name` | string (≤200 chars) | optional |  |
| `expected_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `expected_close_date` | date | optional |  |
| `opportunity_title` | string (≤200 chars) | optional |  |

## POST /opportunities

Create Opportunity

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `expected_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `expected_close_date` | date | optional |  |
| `lead_id` | string | optional |  |
| `opportunity_no` | string (≤64 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |
