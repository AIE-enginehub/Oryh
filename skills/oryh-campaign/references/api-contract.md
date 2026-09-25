<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-campaign: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths are relative to the API root. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /campaign-members/{member_id}

Delete Campaign Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `member_id` | path | string | yes |  |

## DELETE /campaigns/{campaign_id}

Delete Campaign

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | path | string | yes |  |

## DELETE /leads/{lead_id}

Delete Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

## DELETE /opportunities/{opportunity_id}

Delete Opportunity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

## DELETE /sales-orders/{order_id}

Delete Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delete_reason` | string (≤2000 chars) | optional |  |
| `deleted_by` | string (≤100 chars) | optional |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

## GET /campaign-members

List Campaign Members

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `contact_id` | query | string | no |  |
| `member_status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `responded_at_from` | query | date-time | no | rows whose responded_at is at or after this |
| `responded_at_thru` | query | date-time | no | rows whose responded_at is at or before this |

## GET /campaign-members/{member_id}

Get Campaign Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `member_id` | path | string | yes |  |

## GET /campaigns

List Campaigns

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `campaign_type` | query | string | no |  |
| `parent_campaign_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `end_date_from` | query | date | no | rows whose end_date is on or after this |
| `end_date_thru` | query | date | no | rows whose end_date is on or before this |
| `start_date_from` | query | date | no | rows whose start_date is on or after this |
| `start_date_thru` | query | date | no | rows whose start_date is on or before this |
| `currency` | query | string | no |  |

## GET /campaigns/{campaign_id}

Get Campaign

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | path | string | yes |  |

## GET /campaigns/{campaign_id}/detail

Get Campaign Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | path | string | yes |  |

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

## GET /leads

List Leads

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `source` | query | string | no |  |
| `campaign_id` | query | string | no |  |
| `geo_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `converted_customer_id` | query | string | no |  |

## GET /leads/{lead_id}

Get Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

## GET /opportunities

List Opportunities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `campaign_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `closed_at_from` | query | date-time | no | rows whose closed_at is at or after this |
| `closed_at_thru` | query | date-time | no | rows whose closed_at is at or before this |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `expected_close_date_from` | query | date | no | rows whose expected_close_date is on or after this |
| `expected_close_date_thru` | query | date | no | rows whose expected_close_date is on or before this |
| `currency` | query | string | no |  |
| `source` | query | string | no |  |

## GET /opportunities/{opportunity_id}

Get Opportunity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

## GET /opportunities/{opportunity_id}/detail

Get Opportunity Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

## GET /sales-orders

List Sales Orders

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `store_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `billing_account_id` | query | string | no |  |
| `quotation_id` | query | string | no |  |
| `order_no` | query | string | no |  |
| `order_kind` | query | string | no |  |
| `original_order_id` | query | string | no |  |
| `supersedes_order_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |
| `created_at_from` | query | date-time | no | rows whose created_at is at or after this |
| `created_at_thru` | query | date-time | no | rows whose created_at is at or before this |
| `order_date_from` | query | date | no | rows whose order_date is on or after this |
| `order_date_thru` | query | date | no | rows whose order_date is on or before this |
| `promised_date_from` | query | date | no | rows whose promised_date is on or after this |
| `promised_date_thru` | query | date | no | rows whose promised_date is on or before this |
| `shipped_at_from` | query | date-time | no | rows whose shipped_at is at or after this |
| `shipped_at_thru` | query | date-time | no | rows whose shipped_at is at or before this |
| `signed_at_from` | query | date-time | no | rows whose signed_at is at or after this |
| `signed_at_thru` | query | date-time | no | rows whose signed_at is at or before this |
| `submitted_at_from` | query | date-time | no | rows whose submitted_at is at or after this |
| `submitted_at_thru` | query | date-time | no | rows whose submitted_at is at or before this |
| `contract_id` | query | string | no |  |
| `currency` | query | string | no |  |
| `project_id` | query | string | no |  |

## GET /sales-orders/{order_id}

Get Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

## GET /sales-orders/{order_id}/attachments/{attachment_id}/content

Get Sales Order Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /sales-orders/{order_id}/detail

Get Sales Order Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `include_deleted` | query | boolean | no |  |

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
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /workflow-definitions/{definition_id}

Get Workflow Definition

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `definition_id` | path | string | yes |  |

## PATCH /campaign-members/{member_id}

Update Campaign Member

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `member_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contact_id` | string | optional |  |
| `member_status` | string (≤50 chars) | optional |  |
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `responded_at` | date-time | optional |  |

## PATCH /campaigns/{campaign_id}

Update Campaign

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `actual_cost` | number (≥0.0, ≤999999999999.99) | optional |  |
| `budget` | number (≥0.0, ≤999999999999.99) | optional |  |
| `campaign_type` | string (≤50 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `employee_id` | string | optional |  |
| `end_date` | date | optional |  |
| `expected_revenue` | number (≥0.0, ≤999999999999.99) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_campaign_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `start_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |

## PATCH /leads/{lead_id}

Update Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `campaign_id` | string | optional |  |
| `company_name` | string (≤200 chars) | optional |  |
| `contact_name` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
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
| `campaign_id` | string | optional |  |
| `competitor` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `expected_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `expected_close_date` | date | optional |  |
| `lead_id` | string | optional |  |
| `lost_reason` | string (≤50 chars) | optional |  |
| `probability` | integer (≥0.0, ≤100.0) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source` | string (≤100 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /sales-orders/{order_id}

Update Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `billing_account_id` | string | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `logistics_company` | string (≤100 chars) | optional |  |
| `logistics_tracking_no` | string (≤100 chars) | optional |  |
| `order_date` | date | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `promised_date` | date | optional |  |
| `quotation_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `ship_to_address` | string (≤500 chars) | optional |  |
| `shipped_at` | date-time | optional |  |
| `signed_at` | date-time | optional |  |
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

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

## POST /campaign-members

Create Campaign Member

Body:

| field | type | | notes |
|---|---|---|---|
| `campaign_id` | string | required |  |
| `contact_id` | string | optional |  |
| `customer_id` | string | optional |  |
| `lead_id` | string | optional |  |
| `member_status` | string (≤50 chars) | optional |  |
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `responded_at` | date-time | optional |  |

## POST /campaigns

Create Campaign

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `name` | string (≤200 chars) | required |  |
| `actual_cost` | number (≥0.0, ≤999999999999.99) | optional |  |
| `budget` | number (≥0.0, ≤999999999999.99) | optional |  |
| `campaign_no` | string (≤64 chars) | optional |  |
| `campaign_type` | string (≤50 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `end_date` | date | optional |  |
| `expected_revenue` | number (≥0.0, ≤999999999999.99) | optional |  |
| `parent_campaign_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `start_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /campaigns/{campaign_id}/restore

Restore Campaign

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `campaign_id` | path | string | yes |  |

## POST /leads

Create Lead

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `campaign_id` | string | optional |  |
| `company_name` | string (≤200 chars) | optional |  |
| `contact_name` | string (≤100 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
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

## POST /leads/{lead_id}/restore

Restore Lead

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `lead_id` | path | string | yes |  |

## POST /opportunities

Create Opportunity

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `campaign_id` | string | optional |  |
| `competitor` | string (≤200 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `expected_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `expected_close_date` | date | optional |  |
| `lead_id` | string | optional |  |
| `lost_reason` | string (≤50 chars) | optional |  |
| `opportunity_no` | string (≤64 chars) | optional |  |
| `probability` | integer (≥0.0, ≤100.0) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source` | string (≤100 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /opportunities/{opportunity_id}/quote

Quote Opportunity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `quote_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `valid_until` | date | optional |  |

## POST /opportunities/{opportunity_id}/restore

Restore Opportunity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |

## POST /opportunities/{opportunity_id}/save

Save Opportunity Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional | a live row to keep; absent = a new row |
  | `line_no` | integer | optional |  |
  | `notes` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string | optional |  |
  | `quantity` | number | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string | optional |  |
  | `unit` | string | optional |  |
  | `unit_price` | number | optional |  |

## POST /sales-orders

Create Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `title` | string (≤200 chars) | required |  |
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
| `billing_account_id` | string | optional |  |
| `contact_name` | string (≤200 chars) | optional |  |
| `contact_phone` | string (≤50 chars) | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `customer_name_snapshot` | string (≤200 chars) | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `is_gift` | boolean | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `order_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `logistics_company` | string (≤100 chars) | optional |  |
| `logistics_tracking_no` | string (≤100 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `order_date` | date | optional |  |
| `order_kind` | `order` | `return` | optional |  |
| `order_no` | string (≤64 chars) | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `project_id` | string | optional |  |
| `promised_date` | date | optional |  |
| `quotation_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `ship_to_address` | string (≤500 chars) | optional |  |
| `source_quote_number` | string (≤64 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string | optional |  |
| `store_id` | string | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |

## POST /sales-orders/bulk

Bulk Import Sales Orders

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `order_no` | string (≤64 chars) | required |  |
  | `adjustments` | array of objects (fields below) | optional |  |
  | ↳ each `adjustments[]` item: | | | |
    | `adjustment_type` | string (≤20 chars) | required |  |
    | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
    | `description` | string (≤500 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `metadata` | object | optional |  |
    | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |
  | `contact_name` | string (≤200 chars) | optional |  |
  | `contact_phone` | string (≤50 chars) | optional |  |
  | `contract_no` | string (≤64 chars) | optional |  |
  | `currency` | string (≤3 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `customer_code` | string (≤64 chars) | optional |  |
  | `customer_id` | string | optional |  |
  | `customer_name_snapshot` | string (≤200 chars) | optional |  |
  | `delivery_terms` | string (≤2000 chars) | optional |  |
  | `employee_code` | string (≤64 chars) | optional |  |
  | `employee_id` | string | optional |  |
  | `items` | array of objects (fields below) | optional |  |
  | ↳ each `items[]` item: | | | |
    | `quantity` | number (≤9999999.99) | required |  |
    | `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
    | `custom_fields` | object | optional |  |
    | `is_gift` | boolean | optional |  |
    | `lead_time` | string (≤100 chars) | optional |  |
    | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
    | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
    | `notes` | string (≤2000 chars) | optional |  |
    | `product_code` | string (≤64 chars) | optional |  |
    | `product_name_snapshot` | string (≤200 chars) | optional |  |
    | `promised_date` | date | optional |  |
    | `sku_code` | string (≤64 chars) | optional |  |
    | `spec` | string (≤200 chars) | optional |  |
    | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
    | `unit` | string (≤50 chars) | optional |  |
    | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
  | `order_date` | date | optional |  |
  | `payment_terms` | string (≤2000 chars) | optional |  |
  | `project_code` | string (≤64 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `remarks` | string (≤2000 chars) | optional |  |
  | `ship_to_address` | string (≤500 chars) | optional |  |
  | `source_quote_number` | string (≤64 chars) | optional |  |
  | `status` | string (≤30 chars) | optional |  |
  | `title` | string (≤200 chars) | optional |  |
  | `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |
| `on_missing_reference` | `error` | `snapshot` | optional |  |

## POST /sales-orders/{order_id}/release

Release Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `description` | string (≤500 chars) | optional |  |
| `lines` | array of objects (fields below) | optional |  |

## POST /sales-orders/{order_id}/reserve

Reserve Stock For Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `lines` | array of objects (fields below) | required |  |
| ↳ each `lines[]` item: | | | |
  | `inventory_item_id` | string | required |  |
  | `quantity` | number (≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `order_item_id` | string | optional |  |
| `description` | string (≤500 chars) | optional |  |

## POST /sales-orders/{order_id}/restore

Restore Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `restored_by` | string (≤100 chars) | optional |  |

## POST /sales-orders/{order_id}/revise

Revise Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `reason` | string (≤2000 chars) | optional |  |

## POST /sales-orders/{order_id}/save

Save Sales Order Lines

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |
| `validate_only` | query | boolean | no |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `expected_revision` | string (≤64 chars) | required |  |
| `items` | array of objects (fields below) | required |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `id` | string | optional |  |
  | `is_gift` | boolean | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `list_price_snapshot` | number (≥0.0, ≤9999999.99) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `order_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `adjustments` | array of objects (fields below) | optional |  |
| ↳ each `adjustments[]` item: | | | |
  | `adjustment_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
  | `amount` | number (≥-9999999.99, ≤9999999.99) | required |  |
  | `description` | string (≤500 chars) | optional |  |
  | `id` | string | optional |  |
  | `item_index` | integer (≥0.0, ≤199.0) | optional |  |
  | `metadata` | object | optional |  |
  | `source_percentage` | number (≥0.0, ≤100.0) | optional |  |

## POST /sales-orders/{order_id}/submit

Submit Sales Order

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `order_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `source` | `web` | `api` | `ai` | `system` | optional |  |
| `submitted_by` | string | optional |  |

## POST /type-options

Create Type Option

Body:

| field | type | | notes |
|---|---|---|---|
| `family` | string | required |  |
| `name` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | required |  |
| `description` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

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
