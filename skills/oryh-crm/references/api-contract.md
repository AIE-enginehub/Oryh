<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-crm: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /activities/{activity_id}

Delete Activity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `activity_id` | path | string | yes |  |

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

## DELETE /communication-events/{row_id}

Delete Communication Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## DELETE /customers/{customer_id}

Delete Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

## DELETE /event-participants/{row_id}

Delete Event Participant

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## DELETE /events/{event_id}

Delete Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | path | string | yes |  |

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

## DELETE /opportunity-contacts/{row_id}

Delete Opportunity Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## DELETE /opportunity-items/{item_id}

Delete Opportunity Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## DELETE /type-options/{type_option_id}

Archive Type Option

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `type_option_id` | path | string | yes |  |

## GET /activities

List Activities

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `contact_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `event_id` | query | string | no |  |
| `activity_type` | query | string | no |  |
| `outcome` | query | string | no |  |
| `occurred_from` | query | date-time | no | Activities at or after this moment |
| `occurred_thru` | query | date-time | no | Activities at or before this moment |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /activities/{activity_id}

Get Activity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `activity_id` | path | string | yes |  |

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

## GET /communication-events

List Communication Events

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `channel` | query | string | no |  |
| `direction` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `contact_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `thread_id` | query | string | no |  |
| `message_id` | query | string | no |  |
| `occurred_from` | query | date-time | no | Messages at or after this moment |
| `occurred_thru` | query | date-time | no | Messages at or before this moment |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /communication-events/{row_id}

Get Communication Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## GET /customers

List Customers

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `tax_id` | query | string | no |  |
| `phone` | query | string | no |  |
| `customer_kind` | query | string | no |  |
| `customer_type` | query | string | no |  |
| `geo_id` | query | string | no |  |
| `territory_id` | query | string | no |  |
| `owner_employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /customers/{customer_id}

Get Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

## GET /customers/{customer_id}/detail

Get Customer Detail

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

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

## GET /employees/{employee_id}/pay-history

Get Employee Pay History

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `component` | query | string | no |  |
| `in_force_on` | query | date | no |  |

## GET /employees/{employee_id}/todos

List Employee Todos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |
| `status` | query | string | no |  |
| `entity_type` | query | string | no |  |
| `entity_id` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /event-participants

List Event Participants

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `contact_id` | query | string | no |  |
| `response` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /event-participants/{row_id}

Get Event Participant

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## GET /events

List Events

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `lead_id` | query | string | no |  |
| `opportunity_id` | query | string | no |  |
| `event_type` | query | string | no |  |
| `status` | query | string | no |  |
| `starts_from` | query | date-time | no | Events starting at or after this moment |
| `starts_thru` | query | date-time | no | Events starting at or before this moment |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /events/{event_id}

Get Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | path | string | yes |  |

## GET /geos

List Geos

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_type` | query | string | no |  |
| `parent_geo_id` | query | string | no |  |
| `geo_code` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /geos/{geo_id}

Get Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

## GET /geos/{geo_id}/path

Get Geo Path

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

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

## GET /opportunity-contacts

List Opportunity Contacts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | query | string | no |  |
| `contact_id` | query | string | no |  |
| `role` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /opportunity-contacts/{row_id}

Get Opportunity Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

## GET /opportunity-items

List Opportunity Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `opportunity_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `sku_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |
| `order_by` | query | string | no | Sort order: a column name, `-` prefix for descending, comma-separated for several (e.g. -created_at,order_no). Any column of the row may be named; an unknown name answers 422 listing the sortable columns. Omit for the collection's own order (newest first for documents). |

## GET /opportunity-items/{item_id}

Get Opportunity Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

## GET /territory-resolution

Resolve

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | query | string | yes | The place to resolve — a customer's geo, or any geo |

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

## PATCH /activities/{activity_id}

Update Activity

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `activity_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `activity_type` | string (≤50 chars) | optional |  |
| `communication_event_id` | string | optional |  |
| `contact_id` | string | optional |  |
| `content` | string (≤10000 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `event_id` | string | optional |  |
| `lead_id` | string | optional |  |
| `next_action` | string (≤500 chars) | optional |  |
| `next_action_at` | date-time | optional |  |
| `occurred_at` | date-time | optional |  |
| `opportunity_id` | string | optional |  |
| `outcome` | string (≤50 chars) | optional |  |
| `source_text` | string (≤20000 chars) | optional |  |
| `subject` | string (≤200 chars) | optional |  |

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

## PATCH /communication-events/{row_id}

Update Communication Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `body` | string (≤100000 chars) | optional |  |
| `contact_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `lead_id` | string | optional |  |
| `opportunity_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `subject` | string (≤500 chars) | optional |  |
| `thread_id` | string (≤255 chars) | optional |  |

## PATCH /customers/{customer_id}

Update Customer

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `customer_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `address` | string (≤500 chars) | optional |  |
| `contact` | string (≤200 chars) | optional |  |
| `customer_code` | string (≤64 chars) | optional |  |
| `customer_kind` | `person` | `company` | optional |  |
| `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `owner_employee_id` | string | optional |  |
| `payment_terms` | string (≤500 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `territory_id` | string | optional |  |

## PATCH /employees/{employee_id}

Update Employee

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `employee_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

## PATCH /event-participants/{row_id}

Update Event Participant

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `response` | string (≤50 chars) | optional |  |

## PATCH /events/{event_id}

Update Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `ends_at` | date-time | optional |  |
| `event_type` | string (≤50 chars) | optional |  |
| `lead_id` | string | optional |  |
| `location` | string (≤300 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `starts_at` | date-time | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `subject` | string (≤200 chars) | optional |  |

## PATCH /geos/{geo_id}

Update Geo

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `geo_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `abbreviation` | string (≤50 chars) | optional |  |
| `geo_type` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `parent_geo_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

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

## PATCH /opportunity-contacts/{row_id}

Update Opportunity Contact

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `row_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `is_primary` | boolean | optional |  |
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `role` | string (≤50 chars) | optional |  |

## PATCH /opportunity-items/{item_id}

Update Opportunity Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `quantity` | number (≤9999999.99) | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999999.99) | optional |  |

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

## POST /activities

Create Activity

Body:

| field | type | | notes |
|---|---|---|---|
| `activity_type` | string (≤50 chars) | required |  |
| `occurred_at` | date-time | required |  |
| `subject` | string (≤200 chars) | required |  |
| `communication_event_id` | string | optional |  |
| `contact_id` | string | optional |  |
| `content` | string (≤10000 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `employee_id` | string | optional |  |
| `event_id` | string | optional |  |
| `lead_id` | string | optional |  |
| `next_action` | string (≤500 chars) | optional |  |
| `next_action_at` | date-time | optional |  |
| `opportunity_id` | string | optional |  |
| `outcome` | string (≤50 chars) | optional |  |
| `source_text` | string (≤20000 chars) | optional |  |

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

## POST /communication-events

Create Communication Event

Body:

| field | type | | notes |
|---|---|---|---|
| `channel` | string (≤50 chars) | required |  |
| `direction` | `inbound` | `outbound` | required |  |
| `occurred_at` | date-time | required |  |
| `body` | string (≤100000 chars) | optional |  |
| `cc_addresses` | array of string | optional |  |
| `contact_id` | string | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `employee_id` | string | optional |  |
| `from_address` | string (≤320 chars) | optional |  |
| `lead_id` | string | optional |  |
| `message_id` | string (≤255 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `subject` | string (≤500 chars) | optional |  |
| `thread_id` | string (≤255 chars) | optional |  |
| `to_addresses` | array of string | optional |  |

## POST /customers

Create Customer

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `address` | string (≤500 chars) | optional |  |
| `contact` | string (≤200 chars) | optional |  |
| `customer_code` | string (≤64 chars) | optional |  |
| `customer_kind` | `person` | `company` | optional |  |
| `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
| `email` | string (≤320 chars) | optional |  |
| `geo_id` | string | optional |  |
| `metadata` | object | optional |  |
| `owner_employee_id` | string | optional |  |
| `payment_terms` | string (≤500 chars) | optional |  |
| `phone` | string (≤50 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
| `tax_id` | string (≤64 chars) | optional |  |
| `territory_id` | string | optional |  |

## POST /customers/bulk

Bulk Upsert Customers

Body:

| field | type | | notes |
|---|---|---|---|
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `customer_code` | string (≤64 chars) | required |  |
  | `name` | string (≤200 chars) | required |  |
  | `address` | string (≤500 chars) | optional |  |
  | `contact` | string (≤200 chars) | optional |  |
  | `customer_kind` | `person` | `company` | optional |  |
  | `customer_type` | string (pattern `^[a-z][a-z0-9_]{0,49}$`) | optional |  |
  | `email` | string (≤320 chars) | optional |  |
  | `geo_id` | string | optional |  |
  | `metadata` | object | optional |  |
  | `owner_employee_id` | string | optional |  |
  | `payment_terms` | string (≤500 chars) | optional |  |
  | `phone` | string (≤50 chars) | optional |  |
  | `status` | `active` | `archived` | optional |  |
  | `tax_id` | string (≤64 chars) | optional |  |
  | `territory_id` | string | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

## POST /employees

Create Employee

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `email` | string (≤320 chars) | optional |  |
| `employee_code` | string (≤64 chars) | optional |  |
| `hire_date` | date | optional |  |
| `metadata` | object | optional |  |
| `status` | `active` | `inactive` | optional |  |
| `timezone` | string (≤100 chars) | optional |  |

## POST /event-participants

Create Event Participant

Body:

| field | type | | notes |
|---|---|---|---|
| `event_id` | string | required |  |
| `contact_id` | string | optional |  |
| `employee_id` | string | optional |  |
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `response` | string (≤50 chars) | optional |  |

## POST /events

Create Event

Body:

| field | type | | notes |
|---|---|---|---|
| `starts_at` | date-time | required |  |
| `subject` | string (≤200 chars) | required |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `description` | string (≤4000 chars) | optional |  |
| `employee_id` | string | optional |  |
| `ends_at` | date-time | optional |  |
| `event_no` | string (≤64 chars) | optional |  |
| `event_type` | string (≤50 chars) | optional |  |
| `lead_id` | string | optional |  |
| `location` | string (≤300 chars) | optional |  |
| `opportunity_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | string (≤50 chars) | optional |  |

## POST /events/{event_id}/log

Log Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `content` | string (≤10000 chars) | optional |  |
| `next_action` | string (≤500 chars) | optional |  |
| `next_action_at` | date-time | optional |  |
| `outcome` | string (≤50 chars) | optional |  |
| `source_text` | string (≤20000 chars) | optional |  |
| `subject` | string (≤200 chars) | optional |  |

## POST /events/{event_id}/restore

Restore Event

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `event_id` | path | string | yes |  |

## POST /geos

Create Geo

Body:

| field | type | | notes |
|---|---|---|---|
| `geo_code` | string (≤64 chars) | required |  |
| `geo_type` | string (≤50 chars) | required |  |
| `name` | string (≤200 chars) | required |  |
| `abbreviation` | string (≤50 chars) | optional |  |
| `metadata` | object | optional |  |
| `parent_geo_id` | string | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /geos/seed-template

Seed Geo Template

Body:

| field | type | | notes |
|---|---|---|---|
| `template` | string | required |  |

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

## POST /opportunity-contacts

Create Opportunity Contact

Body:

| field | type | | notes |
|---|---|---|---|
| `contact_id` | string | required |  |
| `opportunity_id` | string | required |  |
| `is_primary` | boolean | optional |  |
| `metadata_jsonb` | object | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `role` | string (≤50 chars) | optional |  |

## POST /opportunity-items

Create Opportunity Item

Body:

| field | type | | notes |
|---|---|---|---|
| `opportunity_id` | string | required |  |
| `quantity` | number (≤9999999.99) | required |  |
| `amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `custom_fields` | object | optional |  |
| `line_no` | integer (≥1.0) | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `product_id` | string | optional |  |
| `product_name_snapshot` | string (≤200 chars) | optional |  |
| `sku_id` | string | optional |  |
| `spec` | string (≤200 chars) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999999.99) | optional |  |

## POST /todos

Create Todo

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `entity_id` | string | required |  |
| `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
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
  | `entity_type` | `campaign` | `contract` | `employee_leave` | `event` | `expense_claim` | `invoice` | `lead` | `opportunity` | `payment` | `picklist` | `purchase_order` | `purchase_request` | `sales_order` | `sales_quotation` | `shipment` | `timesheet_header` | `approval_target` | `business_object` | `project` | required |  |
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
