from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ObjectTypeDefinition

# Shipped default for the builtin timesheet lifecycle. Every tenant gets a
# copy as an editable definition row at provisioning time; this constant is
# only the fallback when that row is missing.
DEFAULT_TIMESHEET_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "submitted", "approved", "rejected", "returned"],
    "transitions": {
        "draft": ["submitted"],
        "submitted": ["approved", "rejected", "returned"],
        "returned": ["submitted"],
        "approved": [],
        "rejected": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin 请假 lifecycle. Two states the other
# families do not have, and both are about time passing after approval:
#
# `cancelled` — approved leave the person did not take. It cannot be deleted:
# an approver said yes, and the record of what was approved has to survive the
# plan changing. Since the balance is COMPUTED, cancelling is the whole of the
# refund — nothing is credited back because nothing was ever debited.
# `taken` — the leave actually happened. Optional in the sense that a workspace
# that never records it just leaves rows at `approved`; for one that does, it
# is what separates "was allowed to" from "did", which payroll may care about.
DEFAULT_LEAVE_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "submitted", "approved", "rejected", "returned", "cancelled", "taken"],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["approved", "rejected", "returned", "cancelled"],
        "returned": ["submitted", "cancelled"],
        "approved": ["taken", "cancelled"],
        "taken": [],
        "rejected": [],
        "cancelled": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin expense-claim lifecycle. Same contract as
# the timesheet machine; "paid" models the finance payout step and tenants
# may edit it away.
DEFAULT_EXPENSE_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "submitted", "approved", "rejected", "returned", "paid"],
    "transitions": {
        "draft": ["submitted"],
        "submitted": ["approved", "rejected", "returned"],
        "returned": ["submitted"],
        "approved": ["paid"],
        "rejected": [],
        "paid": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin purchase-request lifecycle. "ordered"
# models the procurement execution step (order placed); receiving/PO life
# beyond that is out of scope for a requisition — tenants may add states.
DEFAULT_PURCHASE_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "submitted", "approved", "rejected", "returned", "ordered"],
    "transitions": {
        "draft": ["submitted"],
        "submitted": ["approved", "rejected", "returned"],
        "returned": ["submitted"],
        "approved": ["ordered"],
        "rejected": [],
        "ordered": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin sales-quotation lifecycle. The front half
# (draft→submitted→approved) is the internal approval segment shared with the
# other builtins; the back half is the customer-facing outcome. "superseded"
# is the revision hinge: a sent/approved quotation is an immutable fact, and
# renegotiation issues a new revision while this one steps aside. Tenants who
# don't track customer outcomes may prune the back half.
DEFAULT_QUOTATION_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "approved", "rejected", "returned",
        "sent", "accepted", "declined", "expired", "superseded",
    ],
    "transitions": {
        "draft": ["submitted"],
        "submitted": ["approved", "rejected", "returned"],
        "returned": ["submitted"],
        "approved": ["sent", "superseded"],
        "sent": ["accepted", "declined", "expired", "superseded"],
        "rejected": [],
        "accepted": [],
        "declined": [],
        "expired": [],
        "superseded": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin sales-order lifecycle (OFBiz status flow
# CREATED→APPROVED→SENT→COMPLETED mapped onto the family idiom). The front
# half is the shared approval segment — "confirmed" is this family's
# "approved" — and the back half is fulfilment: shipped → signed. Service
# tenants typically rename the back half (e.g. in_delivery → delivered);
# anchors only pin draft/submitted. Record-won agents may create directly
# at "confirmed" — create accepts any declared state, like every builtin.
DEFAULT_ORDER_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "confirmed", "rejected", "returned",
        "shipped", "signed", "cancelled",
    ],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["confirmed", "rejected", "returned"],
        "returned": ["submitted", "cancelled"],
        "confirmed": ["shipped", "cancelled"],
        "shipped": ["signed"],
        "signed": [],
        "rejected": [],
        "cancelled": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the purchase-order lifecycle. One procurement role
# drives the whole thing, so there is no returned/rejected half: a PO the
# vendor cannot honour is cancelled and re-issued. Partial receiving is not a
# state — it is confirmed with received_quantity < quantity on the lines.
DEFAULT_PURCHASE_ORDER_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "submitted", "confirmed", "received", "closed", "cancelled"],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["confirmed", "cancelled"],
        "confirmed": ["received", "cancelled"],
        "received": ["closed"],
        "closed": [],
        "cancelled": [],
    },
    "editable_states": ["draft"],
}


# Shipped default for the builtin invoice lifecycle, shared by both directions
# (OFBiz keeps one status vocabulary across sales and purchase invoices too).
# `submitted` is 开票申请 on the sales side and 待核对 on the purchase side.
#
# `paid` is a FLOW MARKER, not the settlement truth: how much is actually
# settled is `applied_amount` against the payment-application ledger, and a
# partly-paid invoice deliberately has no state of its own — the same stance
# that keeps partial receiving out of the purchase-order machine. Tenants who
# never chase payment status can prune it.
DEFAULT_INVOICE_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "returned", "issued",
        "paid", "written_off", "void", "cancelled",
    ],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["issued", "returned", "cancelled"],
        "returned": ["submitted", "cancelled"],
        "issued": ["paid", "written_off", "void"],
        "paid": [],
        "written_off": [],
        "void": [],
        "cancelled": [],
    },
    "editable_states": ["draft", "returned"],
}

# Shipped default for the builtin payment lifecycle. The approval half is here
# for outbound payments — 付款审批 is the most-approved document there is — and
# an inbound receipt simply gets created at `paid`, since create accepts any
# declared state in every family. `void` after `paid` covers a bounced or
# recalled transfer; the applications it carried are reversed by counter-entry,
# never by deleting the ledger rows.
DEFAULT_PAYMENT_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "approved", "rejected", "returned",
        "paid", "cancelled", "void",
    ],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["approved", "rejected", "returned", "cancelled"],
        "returned": ["submitted", "cancelled"],
        "approved": ["paid", "cancelled"],
        "paid": ["void"],
        "rejected": [],
        "cancelled": [],
        "void": [],
    },
    "editable_states": ["draft", "returned"],
}


# Fallback statuses for custom business object types without a machine —
# the pre-existing free mode.
DEFAULT_BUSINESS_OBJECT_STATES = {"open", "in_review", "approved", "rejected", "archived"}

# One row per builtin lifecycle: the shipped default machine, and the anchor
# states its endpoints rely on (POST .../submit targets "submitted", new
# documents start at "draft"). The purchase order has no submit endpoint but
# keeps the same anchors — its machine still starts at draft and the console
# and skills lean on those two names existing.
BUILTIN_MACHINES: dict[str, dict] = {
    "timesheet_header": DEFAULT_TIMESHEET_MACHINE,
    "employee_leave": DEFAULT_LEAVE_MACHINE,
    "expense_claim": DEFAULT_EXPENSE_MACHINE,
    "purchase_request": DEFAULT_PURCHASE_MACHINE,
    "sales_quotation": DEFAULT_QUOTATION_MACHINE,
    "sales_order": DEFAULT_ORDER_MACHINE,
    "purchase_order": DEFAULT_PURCHASE_ORDER_MACHINE,
    "invoice": DEFAULT_INVOICE_MACHINE,
    "payment": DEFAULT_PAYMENT_MACHINE,
}
BUILTIN_ANCHORS: dict[str, dict] = {
    object_type: {"initial": "draft", "required_states": {"draft", "submitted"}}
    for object_type in BUILTIN_MACHINES
}


def ensure_valid_state_machine(machine: dict, *, entity_kind: str, object_type: str) -> None:
    def fail(detail: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid state_machine: {detail}",
        )

    states = machine.get("states")
    if not isinstance(states, list) or not states or not all(isinstance(s, str) and s for s in states):
        fail("states must be a non-empty list of strings")
    state_set = set(states)
    if len(state_set) != len(states):
        fail("states contains duplicates")
    initial = machine.get("initial")
    if initial not in state_set:
        fail("initial must be one of states")
    transitions = machine.get("transitions")
    if not isinstance(transitions, dict):
        fail("transitions must be an object mapping state -> [states]")
    for from_state, to_states in transitions.items():
        if from_state not in state_set:
            fail(f"transition source {from_state!r} is not a declared state")
        if not isinstance(to_states, list) or not all(t in state_set for t in to_states):
            fail(f"transition targets of {from_state!r} must be declared states")
    editable = machine.get("editable_states", [])
    if not isinstance(editable, list) or not all(e in state_set for e in editable):
        fail("editable_states must be a list of declared states")
    if entity_kind == "builtin":
        anchors = BUILTIN_ANCHORS.get(object_type)
        if anchors is None:
            fail(f"unknown builtin entity {object_type!r}")
        missing = anchors["required_states"] - state_set
        if missing:
            fail(f"builtin {object_type} machine must keep anchor states {sorted(missing)}")
        if initial != anchors["initial"]:
            fail(f"builtin {object_type} machine must start at {anchors['initial']!r}")


def get_definition(
    db: Session, tenant_id: str, entity_kind: str, object_type: str
) -> ObjectTypeDefinition | None:
    return db.scalar(
        select(ObjectTypeDefinition).where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == entity_kind,
            ObjectTypeDefinition.object_type == object_type,
            ObjectTypeDefinition.status == "active",
        )
    )


def get_builtin_machine(db: Session, tenant_id: str, object_type: str) -> dict:
    """The tenant's edited machine for a builtin lifecycle, else the shipped
    default. One function for every builtin — the object_type string is the
    whole difference between the families."""
    definition = get_definition(db, tenant_id, "builtin", object_type)
    if definition is not None and definition.state_machine:
        return definition.state_machine
    return BUILTIN_MACHINES[object_type]


def get_business_object_machine(db: Session, tenant_id: str, object_type: str) -> dict | None:
    definition = get_definition(db, tenant_id, "business_object", object_type)
    if definition is not None and definition.state_machine:
        return definition.state_machine
    return None


def validate_transition(machine: dict, current: str, new: str, *, subject: str) -> None:
    """409 on illegal transitions. A current state unknown to the machine
    (definition changed under live objects) may move to any declared state so
    records never get stuck."""
    if new == current:
        return
    states = set(machine.get("states", ()))
    if new not in states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{subject}: {new!r} is not a state of the configured state machine",
        )
    if current not in states:
        return
    allowed = machine.get("transitions", {}).get(current, [])
    if new not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{subject}: illegal transition {current!r} -> {new!r} (allowed: {sorted(allowed)})",
        )


def is_terminal_state(machine: dict, state: str) -> bool:
    """True when the machine allows nothing to follow this state.

    The server is not allowed an opinion about what a workspace's state NAMES
    mean — 作废, 已取消, 已废弃 and 已完成 are the tenant's vocabulary, and
    `leave-no-orphan-work.md` says so in as many words. It does not need one.
    A state with no outgoing transitions is a statement the tenant's own
    machine makes: nothing further happens to a document here. That is enough
    to know the open work items pointing at it cannot be done.

    A state the machine has never heard of is NOT terminal — `validate_transition`
    deliberately lets such a document move anywhere so it never gets stuck, and
    a state that can still move is not an ending.
    """
    transitions = machine.get("transitions", {})
    if state not in transitions:
        return False
    return not transitions[state]


def validate_business_object_status(
    db: Session, tenant_id: str, object_type: str, *, current: str | None, new: str
) -> None:
    """Create (current=None): any declared state is acceptable — agents may
    record facts that are already mid-flow. Update: transition must be legal."""
    machine = get_business_object_machine(db, tenant_id, object_type)
    if machine is None:
        if new not in DEFAULT_BUSINESS_OBJECT_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status must be one of {sorted(DEFAULT_BUSINESS_OBJECT_STATES)} for types without a state machine",
            )
        return
    if current is None:
        if new not in set(machine.get("states", ())):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status {new!r} is not a state of the '{object_type}' state machine",
            )
        return
    validate_transition(machine, current, new, subject=f"business_object '{object_type}'")


def validate_status_filter(
    db: Session, tenant_id: str, object_type: str, status_filter: str | None
) -> None:
    """Reject a `?status=` this tenant's machine does not declare.

    Only `draft` and `submitted` are anchored (BUILTIN_ANCHORS); every other
    name is the shipped default and the tenant may rename it. Filtering on a
    name that no longer exists used to return 200 with zero rows — which reads
    as "nothing to do", not "you asked the wrong question". An agent then tells
    its principal there are no orders in transit while three sit in
    `in_delivery`.

    A status outside the machine can never match a row, so refusing it loses
    no legitimate query and turns a silent wrong answer into a loud one that
    names the states this tenant actually uses.
    """
    if status_filter is None:
        return
    machine = get_builtin_machine(db, tenant_id, object_type)
    states = machine.get("states", ())
    if status_filter not in states:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"unknown status {status_filter!r} for {object_type}; "
                f"this workspace uses: {', '.join(sorted(states))}"
            ),
        )


def validate_business_object_status_filter(
    db: Session, tenant_id: str, object_type: str | None, status_filter: str | None
) -> None:
    """Same guard for custom objects. Without an `object_type` the query spans
    types with different machines, so there is nothing to check it against."""
    if status_filter is None or object_type is None:
        return
    machine = get_business_object_machine(db, tenant_id, object_type)
    states = set(machine["states"]) if machine else DEFAULT_BUSINESS_OBJECT_STATES
    if status_filter not in states:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"unknown status {status_filter!r} for {object_type}; "
                f"this workspace uses: {', '.join(sorted(states))}"
            ),
        )


def editable_states(machine: dict, object_type: str) -> set[str]:
    """Which states allow editing the document's lines. A tenant machine
    that omits editable_states falls back to the shipped default machine's
    own list — one source of truth per family (the purchase order's default
    has no returned half, so its fallback is just draft)."""
    fallback = BUILTIN_MACHINES[object_type]["editable_states"]
    return set(machine.get("editable_states", fallback))
