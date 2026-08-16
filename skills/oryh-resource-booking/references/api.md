# Oryh Resource Booking API Reference

Use these templates with:

- header: `X-API-Key: <api_key>`
- base path: `api_base_url`, exactly as given — no version prefix to add

## Common read endpoints

```text
GET /resources?resource_type=&status=&keyword=
GET /resources/{resource_id}
GET /resources/{resource_id}/availability?start_at=&end_at=
GET /resource-bookings?resource_id=&booked_by_employee_id=&status=
GET /resource-bookings/{booking_id}
```

## Create a resource

Needs `master_data.manage` (admin/service credential) — `booking.own` covers bookings only; without it this returns 403.

```json
POST /resources
{
  "resource_type": "meeting_room",
  "name": "Jade Room",
  "code": "JADE-01",
  "location": "Floor 8",
  "capacity": 8,
  "booking_mode": "exclusive",
  "status": "active",
  "metadata": {
    "building": "HQ",
    "has_screen": true
  }
}
```

Example for a shared device pool:

```json
POST /resources
{
  "resource_type": "device",
  "name": "Projector Pool",
  "code": "PROJ-POOL",
  "booking_mode": "shared",
  "max_quantity": 3,
  "status": "active",
  "metadata": {
    "device_kind": "projector"
  }
}
```

## Check resource availability

```text
GET /resources/{resource_id}/availability?start_at=2026-04-03T09:00:00Z&end_at=2026-04-03T10:00:00Z
```

Expected response shape:

```json
{
  "data": {
    "resource_id": "resource-id",
    "start_at": "2026-04-03T09:00:00Z",
    "end_at": "2026-04-03T10:00:00Z",
    "booking_mode": "exclusive",
    "available": true,
    "available_quantity": 1,
    "conflicting_booking_ids": []
  },
  "meta": {}
}
```

For `shared` resources, `available_quantity` tells you what remains in the requested window.

## Create a booking

```json
POST /resource-bookings
{
  "resource_id": "resource-id",
  "booked_by_employee_id": "employee-id",
  "booking_type": "meeting",
  "title": "Weekly sync",
  "start_at": "2026-04-03T09:00:00Z",
  "end_at": "2026-04-03T10:00:00Z",
  "quantity": 1,
  "source_text": "book me the meeting room tomorrow 9 to 10",
  "notes": "Need a screen",
  "metadata": {}
}
```

For a shared resource:

```json
POST /resource-bookings
{
  "resource_id": "resource-id",
  "booked_by_employee_id": "employee-id",
  "booking_type": "device_borrow",
  "title": "Borrow projectors",
  "start_at": "2026-04-04T09:00:00Z",
  "end_at": "2026-04-04T18:00:00Z",
  "quantity": 2,
  "source_text": "lend me two projectors until end of day",
  "metadata": {}
}
```

## Update a booking

```json
PATCH /resource-bookings/{booking_id}
{
  "title": "Weekly sync moved",
  "start_at": "2026-04-03T10:00:00Z",
  "end_at": "2026-04-03T11:00:00Z",
  "notes": "Updated after schedule change",
  "metadata": {}
}
```

Cancelled bookings cannot be updated.

## Cancel a booking

```json
DELETE /resource-bookings/{booking_id}
{
  "cancelled_by": "employee-id",
  "cancel_reason": "meeting moved online"
}
```

This changes the booking status to `cancelled` and preserves history.

## Resource and booking rules

- `resource.status`:
  - `active`
  - `inactive`
  - `archived`

- `resource.booking_mode`:
  - `exclusive`
  - `shared`

- `resource_booking.status`:
  - `confirmed`
  - `cancelled`

- Booking time rule:
  - `end_at` must be greater than `start_at`

- Conflict rule:
  - exclusive: no overlap allowed
  - shared: sum of overlapping quantities must not exceed `max_quantity`
