---
name: oryh-resource-booking
description: Use when a user wants to find, book, update, cancel, or check availability for enterprise resources through oryh. This includes meeting rooms, devices, and other shared resources managed with resources and resource_bookings over the oryh API.
required_capability: booking.own
---

# Oryh Resource Booking

Use this skill when the task is to operate bookable enterprise resources in a running `oryh` service.

This skill should trigger for user intents like:

- "帮我订会议室"
- "查一下明天下午有没有空的会议室"
- "帮我借一台投影仪"
- "帮我改一下这个会议室预订时间"
- "取消这个设备预约"
- "看看这个资源现在能不能订"

This skill is for API usage only. It does not do calendar sync, mail notifications, or approval orchestration by itself.

## Required inputs

The caller should provide a parameter block like this:

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
  resource_request:
    resource_type: "meeting_room"
    search:
      keyword: "8人"
      location: "Floor 8"
    booking:
      booked_by_employee_id: "employee-id"
      title: "Weekly sync"
      start_at: "2026-04-03T09:00:00Z"
      end_at: "2026-04-03T10:00:00Z"
      quantity: 1
      source_text: "帮我订明天上午 9 点到 10 点的 8 人会议室"
      notes: "Need a screen"
```

Minimum required values:

- `base_url`
- `api_key`

## Parameter Semantics

- The credential is the identity: with a user-bound key, `booked_by_employee_id` must be the principal's own employee (the server enforces it); cancellation attribution is filled server-side.
- `resource_id` means `resources.id`.
- `booked_by_employee_id` is the principal's `employees.id`, already rendered
  into this file as `{{EMPLOYEE_ID}}` — no call needed to learn it.
- `resource_type` is stored on `resources.resource_type`, such as `meeting_room`, `device`, or `vehicle`.
- `source_text` is stored on `resource_bookings.source_text` to preserve the user's natural-language request.
- `metadata` fields are extension data, not core relational facts.

## HTTP conventions

- Send `X-API-Key: <api_key>` on every authenticated request.
- Use the API base path `/api/v1`.
- Expect responses in `{ "data": ..., "meta": ... }`.
- Do not send `tenant_id`. The server derives tenant scope from `X-API-Key`.

## Core rules

1. Keep the resource model generic.
   Do not build special-case logic only for meeting rooms. Use `resource_type` plus structured fields and metadata.

2. Preserve the original user wording.
   When a user asks in natural language, keep that wording in `resource_bookings.source_text`.

3. Respect booking mode.
   - `exclusive` resources cannot overlap in time
   - `shared` resources can overlap only within available quantity

4. Treat archived or inactive resources as unavailable.
   Do not create new bookings on resources that are not `active`.

5. Prefer availability checks before booking when time matters.
   For meeting rooms and other contested assets, check availability first unless the caller explicitly wants a direct booking attempt.

## Recommended workflow

### 1. Resolve the resource type and constraints

From user input or memory, determine:

- resource type, such as `meeting_room` or `device`
- location preference
- capacity or quantity needs
- booking window
- booking owner employee id

### 2. Find candidate resources

Use `GET /resources` to narrow the search by:

- `resource_type`
- `status`
- `keyword`

Then inspect individual resources if needed.

### 3. Check availability

For a specific resource and time window:

- call `GET /resources/{resource_id}/availability?start_at=...&end_at=...`

Use this to determine:

- whether the resource is available
- available quantity for shared resources
- conflicting booking ids

### 4. Create the booking

Use `POST /resource-bookings` with:

- `resource_id`
- `booked_by_employee_id`
- `title`
- `start_at`
- `end_at`
- `quantity`
- `source_text`
- `notes`

For natural-language requests, `source_text` should preserve the original user request.

### 5. Update or cancel the booking

- Use `PATCH /resource-bookings/{booking_id}` to adjust time, title, quantity, or notes.
- Use `DELETE /resource-bookings/{booking_id}` to cancel the booking while preserving history.

Cancelled bookings should be treated as historical records, not hard deletions.

### 6. Read back the result

Finish by returning:

- the selected resource
- the booking id
- the final booking window
- status

## Resource interpretation

Use this interpretation:

- `resource_type`: business category such as `meeting_room`, `device`, or `vehicle`
- `booking_mode`:
  - `exclusive`: no overlapping bookings
  - `shared`: overlapping bookings allowed within quantity limit
- `max_quantity`: the total shareable quantity for shared resources

Do not invent hidden rules beyond the resource data and availability result.

## When to create a resource

Only create a new resource if:

- the caller is clearly asking to register a new enterprise resource
- or your workflow explicitly includes master-data setup
- and the credential holds `master_data.manage` — resource creation is master data, not booking; `booking.own` alone gets 403 here (a role issue, not a retry)

For normal booking requests, prefer reusing existing resources instead of creating ad hoc ones.

## References

Load [references/api.md](./references/api.md) when you need the endpoint list, payload templates, or the availability/booking examples.
