<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-resource-booking: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /resource-bookings/{booking_id}

Delete Resource Booking

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `booking_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|

## GET /resource-bookings

List Resource Bookings

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `resource_id` | query | string | no |  |
| `booked_by_employee_id` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /resource-bookings/{booking_id}

Get Resource Booking

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `booking_id` | path | string | yes |  |

## GET /resources

List Resources

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `keyword` | query | string | no |  |
| `resource_type` | query | string | no |  |
| `booking_mode` | query | string | no |  |
| `status` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /resources/{resource_id}

Get Resource

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `resource_id` | path | string | yes |  |

## GET /resources/{resource_id}/availability

Get Resource Availability

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `resource_id` | path | string | yes |  |
| `start_at` | query | date-time | yes |  |
| `end_at` | query | date-time | yes |  |

## PATCH /resource-bookings/{booking_id}

Update Resource Booking

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `booking_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `booking_type` | string (≤100 chars) | optional |  |
| `end_at` | date-time | optional |  |
| `metadata` | object | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `quantity` | integer (≥1.0) | optional |  |
| `source_text` | string (≤10000 chars) | optional |  |
| `start_at` | date-time | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /resource-bookings

Create Resource Booking

Body:

| field | type | | notes |
|---|---|---|---|
| `booked_by_employee_id` | string | required |  |
| `end_at` | date-time | required |  |
| `resource_id` | string | required |  |
| `start_at` | date-time | required |  |
| `title` | string (≤200 chars) | required |  |
| `booking_type` | string (≤100 chars) | optional |  |
| `metadata` | object | optional |  |
| `notes` | string (≤2000 chars) | optional |  |
| `quantity` | integer (≥1.0) | optional |  |
| `source_text` | string (≤10000 chars) | optional |  |
| `status` | `confirmed` | `cancelled` | optional |  |

## POST /resources

Create Resource

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `resource_type` | string (≤100 chars) | required |  |
| `booking_mode` | `exclusive` | `shared` | optional |  |
| `capacity` | integer (≥1.0) | optional |  |
| `code` | string (≤64 chars) | optional |  |
| `location` | string (≤200 chars) | optional |  |
| `max_quantity` | integer (≥1.0) | optional |  |
| `metadata` | object | optional |  |
| `status` | `active` | `inactive` | `archived` | optional |  |
