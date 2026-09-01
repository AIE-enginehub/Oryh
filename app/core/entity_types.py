"""What a todo or an approval fact may point at — declared once.

This module exists because the list was declared four times: a `Literal` in
`schemas.py`, an if-chain in `routes.py`, a CHECK constraint in the migrations,
and `DOCUMENT_FAMILIES`. All four had drifted. Purchase orders were missing from
the Literal, invoices and payments from the constraint, and the approval
if-chain checked none of the three — so "create the approval todo for this
payment" reached the database and came back a **500**, on a path
`$oryh-payment-approval-flow` tells every finance agent to walk.

It lives in `app/core/` rather than beside either registry because both need it
and they cannot import each other: `state_machines` imports `models`, so
`models` cannot import `state_machines`. This is the leaf both can reach.

`tests/test_entity_reference_types.py` pins it against `BUILTIN_MACHINES`,
`DOCUMENT_FAMILIES` and the live CHECK constraint, so a family added tomorrow
fails the build rather than a month-end.
"""

from __future__ import annotations

# Every builtin document family. Kept in step with `state_machines
# .BUILTIN_MACHINES` and `routes.DOCUMENT_FAMILIES` by test, not by memory.
DOCUMENT_ENTITY_TYPES: tuple[str, ...] = (
    "employee_leave",
    "expense_claim",
    "invoice",
    "lead",
    "opportunity",
    "payment",
    "picklist",
    "purchase_order",
    "purchase_request",
    "sales_order",
    "sales_quotation",
    "shipment",
    "timesheet_header",
)

# Machine types that are NOT document families of their own: their rows live
# inside another family's table, split by that row's `order_kind` column. A
# sales return IS a `sales_orders` row (退单跟订单一张表 — the deciding
# requirement), so a todo or an approval that points at one says
# `sales_order` and resolves through the same table; only the LIFECYCLE
# differs, because an e-commerce return runs 申请→发出→收到→验货入库→退款,
# which is not an order's life. Each entry maps the split-off machine type to
# the family whose table holds its rows.
#
# `tests/test_entity_reference_types.py` pins BUILTIN_MACHINES ==
# DOCUMENT_ENTITY_TYPES ∪ this — a machine added tomorrow must either be a
# real family or say here whose table it lives in.
KIND_SPLIT_MACHINE_TYPES: dict[str, str] = {
    "sales_return": "sales_order",
    "purchase_return": "purchase_order",
}

# Not document families: `approval_target` and `business_object` are
# tenant-defined, and `project` is a standing record a todo may hang off.
APPROVAL_ENTITY_TYPES: tuple[str, ...] = DOCUMENT_ENTITY_TYPES + (
    "approval_target",
    "business_object",
)
TODO_ENTITY_TYPES: tuple[str, ...] = APPROVAL_ENTITY_TYPES + ("project",)

# The builtin families ORYH's hosted flow agent can actually drive: the ones
# whose `.advance` verb is in `HOSTED_FLOW_AGENT_PERMISSIONS`. `purchase_order`
# is deliberately absent — it has no advance permission at all, so nobody
# hosted may move it, and a subscription naming it could never do anything.
#
# It cannot be derived in this module: the verb for a family is not a function
# of its name (`sales_quotation` advances via `quotation.advance`), and the
# mapping lives in `routes.DOCUMENT_FAMILIES`, which this leaf must not import.
# So it is declared, and `tests/test_new_document_family.py` pins it against
# every registry it must agree with.
HOSTED_DRIVABLE_ENTITY_TYPES: tuple[str, ...] = (
    "employee_leave",
    "expense_claim",
    "invoice",
    "payment",
    "purchase_request",
    "sales_order",
    "sales_quotation",
    "timesheet_header",
)

# entity_type -> the REST collection that answers "what here is unattended".
#
# This lived in `flow_runner/queues.py` — a second process, unable to import
# this one, holding its own copy. That copy is exactly what went stale when
# invoices and payments arrived: an unlisted type fell through to
# `/business-objects?object_type=invoice`, which returns nothing, which returns
# as an empty queue. A subscription that could never work was indistinguishable
# from one with nothing to do.
#
# The server now hands the path to the runner with each subscription, so there
# is one copy and it sits beside the list it must agree with.
BUILTIN_QUEUE_PATHS: dict[str, str] = {
    "employee_leave": "/employee-leaves",
    "expense_claim": "/expense-claims",
    "invoice": "/invoices",
    "payment": "/payments",
    "purchase_request": "/purchase-requests",
    "sales_order": "/sales-orders",
    "sales_quotation": "/sales-quotations",
    "timesheet_header": "/timesheet-headers",
}


# The approval actions that DECIDE. `commented` is deliberately outside: an
# objection that does not settle the node can be recorded alongside a decision,
# and more than one of them is ordinary.
#
# Lives here rather than in the API layer because three places need the list
# and must not drift: the write path's refusal, the partial unique index on
# `approval_records` that makes that refusal hold under concurrency, and the
# migration that creates it.
DECIDED_APPROVAL_ACTIONS: tuple[str, ...] = ("approved", "rejected", "returned")


# What a todo's status may be. `cancelled` is not decoration: it is how a work
# item whose subject went away leaves somebody's queue without the trail
# claiming they did the work.
#
# It lives here because it had three homes and one of them disagreed. The
# baseline migration wrote `check (status in ('open','completed'))`, the model
# declared no constraint at all, and `schemas.TodoStatus` listed `cancelled`.
# SQLite builds its schema from the model, so the tests had no constraint and
# stayed green while Postgres refused every cancellation — including the
# server's own `cancel_todos_for`, which meant deleting a document that had an
# open todo was a 500 in every real environment.
TODO_STATUSES: tuple[str, ...] = ("open", "completed", "cancelled")


# The metadata key an authorized operator writes, out-of-band and directly
# against the database, to retire an approval node that carried contradictory
# decisions before the one-decision index existed. Migration `20260810_0049`
# promotes it into a typed, API-unwritable column.
#
# Declared here because two places must agree on the exact string — the
# migration that promotes it and the write path that REFUSES it — and because
# it ships in the open-core export, so it is a known word rather than a secret.
# Reserved the same way ORYH's hosted-agent display name is: a tenant cannot
# mint one, or the exemption would be self-service.
OPERATOR_CONFLICT_CLOSURE_KEY = "oryh_operator_approval_conflict_closure"
