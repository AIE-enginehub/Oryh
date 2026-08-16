# Oryh Access Admin API Reference

{{include:_common/api-auth-principal.md}}

Writes need `users.manage`; reissuing a skill bundle **also** needs
`keys.manage`.

## Reading: see the current state first

```text
GET /capabilities        → {capabilities: [{name, kind, title, description, scopable}], object_types: [...]}
                           kind=system is the fixed vocabulary the server enforces; kind=custom is the tenant's own
                           only scopable=true capabilities may be written verb:scope; object_types are the legal scope values
GET /roles               → [{id, name, title, description, permissions, is_system, user_count}]
GET /auth/users?size=200 → [{id, email, name, role, employee_id, status, invitation_pending}]
GET /tenant/api-keys?status=active   → who holds which credentials (needs keys.manage)
```

`GET /roles` and `GET /capabilities` need only a signed-in caller; writing needs
`users.manage`.

## Roles

```json
POST /roles
{
  "name": "procurement",
  "title": "Procurement officer",
  "description": "Places purchase orders and receives against them",
  "permissions": [
    "timesheet.submit_own", "expense.submit_own", "business_object.write:*",
    "todos.complete_own", "booking.own",
    "purchase_order.manage"
  ]
}
```

- `permissions` **replaces the whole array**, it is not additive: whatever the
  `PATCH` carries is what the role becomes. To add one entry, `GET /roles` for
  the current array, append, and send the whole thing back.
- `name` is unique within the tenant (409); every capability name must exist in
  `GET /capabilities` (a 422 says which one does not).

```json
PATCH /roles/{role_ref}
{"permissions": ["...the existing ones...", "purchase_order.manage"]}
```

`role_ref` accepts either the role id or the role name. `title` and
`description` can be changed on their own, leaving `permissions` untouched.

```text
DELETE /roles/{role_ref}
```

- system role → 409 `system roles cannot be deleted`
- still assigned to users → 409 `role is assigned to users` (move them first)

**Lockout protection** (422, do not retry, explain it to the principal):

```text
the admin role must keep users.manage (lockout guard)
tenant must keep at least one active user with users.manage (lockout guard)
```

The second fires on all three paths: editing role permissions, changing a user's
role, and disabling a user.

## Custom capabilities

```json
POST /capabilities
{"name": "jc.warranty.approve", "title": "May approve warranty cards", "description": "Who can approve a warranty card"}
```

**A custom capability takes effect in exactly two places**: the
`required_capability` gate on skill distribution, and routing decisions in a
workflow definition. **The core server API never checks it** — do not expect it
to gate an endpoint.

- name collides with a system capability → 409
- `DELETE /capabilities/{name}`: system capabilities cannot be deleted (409);
  neither can one that any role grants or any skill uses as its gate (409)

## Users

```json
POST /auth/invitations
{
  "email": "zhangwei.taian@qq.com",
  "name": "Zhang Wei",
  "role": "vendor",
  "employee_id": "employee-id-if-the-record-exists"
}
```

Invitations **deliberately do not validate the company email domain** — an
outside vendor joining with a personal address is exactly this path. The role
must already exist. Email is globally unique and an employee record binds to at
most one user (both 409).

```text
POST /auth/users/{user_id}/resend-invitation      → when a link has expired
POST /auth/users/{user_id}/password-reset-email   → let them reset it themselves; do not do it for them
```

```json
PATCH /auth/users/{user_id}
{"role": "procurement", "status": "active", "employee_id": null}
```

- `role` **overwrites**: they lose everything the old role held. Read the old
  role's `permissions` back to the principal for confirmation first.
- `status`: `active` | `disabled`. Disabling also clears unused invitations and
  reset tokens.
- setting an account that has not accepted its invitation to `active` → 422
  (they have to accept it first).

## Diagnosing "why does he not have that skill"

```text
GET /users/{user_id}/skills     → needs users.manage
GET /roles/{role_ref}/skills    → what someone in this role receives (answerable before hiring)
```

```json
{"data": {"subject_label": "Xie Ting", "role": "member",
  "received": [{"name": "oryh-my-work", "reasons": ["capability"]}],
  "withheld": [
    {"name": "oryh-purchase-submit", "reasons": ["missing_capability"],
     "required_capability": "purchase.submit_own",
     "granted_by_roles": ["procurement", "admin"]},
    {"name": "jc-quote", "reasons": ["missing_capability", "not_in_audience"]}
  ]}}
```

`received` is exactly what their next sync installs — the same decision the
bundle makes, so the two cannot disagree.

`granted_by_roles` answers "who do I copy the grant from". When a capability is
already held by some role, do not invent a new one — that is where a skill's
capability list starts growing without end.

The role view answers about **the role itself**: a skill targeted at an
individual who happens to hold this role shows as `not_in_audience` here,
because the next person to enter the role will not receive it.

## Skill bundles and credentials

```text
POST /users/{user_id}/skill-bundle    → needs users.manage + keys.manage
```

**This rotates that user's key, and every bundle they already have stops working
immediately and must be reinstalled.** The normal move after a role change is
**not** this — it is letting them run `$oryh-skill-sync` once, which leaves the
key alone, affects no other device, and delivers the new skills.

Use this only for a leaked credential or when they genuinely cannot fetch a
bundle, **and tell them before you do**.

## Audit

Creating, changing and deleting roles are all audited (`role.created` /
`role.updated` / `role.deleted`). The detail on `role.updated` carries four
things:

```json
{"name": "member", "permissions": [...],
 "added": ["todos.assign"], "removed": ["booking.own"], "is_system": true}
```

`removed` is the only answer to "what did this change take away" —
`permissions` is a whole-array write, so the result alone cannot distinguish a
deliberate removal from an entry dropped while rebuilding the array. Read it
back with `GET /audit-logs?limit=20` afterwards, particularly for the changes
where `is_system` is true.

A full scan needs `users.manage` — you have it. Someone without that capability
can only query by record or by themselves, and cannot see other people's
credential events. So "he says he cannot find the log" is usually not a fault.
