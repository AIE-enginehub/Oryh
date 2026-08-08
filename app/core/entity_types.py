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
    "expense_claim",
    "invoice",
    "payment",
    "purchase_order",
    "purchase_request",
    "sales_order",
    "sales_quotation",
    "timesheet_header",
)

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
    "expense_claim": "/expense-claims",
    "invoice": "/invoices",
    "payment": "/payments",
    "purchase_request": "/purchase-requests",
    "sales_order": "/sales-orders",
    "sales_quotation": "/sales-quotations",
    "timesheet_header": "/timesheet-headers",
}
