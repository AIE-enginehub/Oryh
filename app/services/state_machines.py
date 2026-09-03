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


# Shipped default for the SALES RETURN lifecycle — rows in `sales_orders`
# with order_kind='return', shaped by the e-commerce reality that decided
# the model: 客户申请(submitted) → 商家同意(approved) → 退单已发出
# (in_transit) → 已收到(received) → 已验货入库(inspected) → 已退款(refunded).
# The graph is permissive where reality is: seller-arranged pickup skips
# in_transit, cheap goods are refunded without waiting for the parcel
# (approved → refunded), and a received parcel may be refunded before formal
# inspection. Money and goods are still separate FACTS — the refund itself
# is a payment document, the restock an inventory movement naming this row;
# `refunded` here is the flow marker, the same stance as invoice `paid`.
DEFAULT_SALES_RETURN_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "approved", "rejected",
        "in_transit", "received", "inspected", "refunded", "cancelled",
    ],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["approved", "rejected", "cancelled"],
        "approved": ["in_transit", "received", "refunded", "cancelled"],
        "in_transit": ["received", "cancelled"],
        "received": ["inspected", "refunded"],
        "inspected": ["refunded"],
        "refunded": [],
        "rejected": [],
        "cancelled": [],
    },
    "editable_states": ["draft"],
}

# Shipped default for the PURCHASE RETURN lifecycle — rows in
# `purchase_orders` with order_kind='return': goods going BACK to a vendor.
# Mirror-image of the sales return with the transit leg outbound; the
# vendor's money coming back is a payment document, `refunded` the marker.
DEFAULT_PURCHASE_RETURN_MACHINE: dict = {
    "initial": "draft",
    "states": [
        "draft", "submitted", "approved", "rejected",
        "shipped", "refunded", "cancelled",
    ],
    "transitions": {
        "draft": ["submitted", "cancelled"],
        "submitted": ["approved", "rejected", "cancelled"],
        "approved": ["shipped", "refunded", "cancelled"],
        "shipped": ["refunded"],
        "refunded": [],
        "rejected": [],
        "cancelled": [],
    },
    "editable_states": ["draft"],
}


# Shipped default for the shipment lifecycle — one freight leg, one machine
# for BOTH directions (the invoice precedent): draft → packed → shipped →
# received, where `received` means "arrived at the destination" — the
# customer's hands outbound, our dock inbound. OFBiz keeps two status sets
# (SHIPMENT_/PURCH_SHIP_); we keep one vocabulary and let the tenant rename
# or extend (in_transit, delivered, 揽收…) in a sentence. The stock effect
# is NOT a state: /post-stock bridges to the inventory ledger exactly once,
# whatever the status says — the same money/goods-as-facts stance as
# invoice `paid`.
DEFAULT_SHIPMENT_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "packed", "shipped", "received", "cancelled"],
    "transitions": {
        "draft": ["packed", "shipped", "cancelled"],
        "packed": ["shipped", "cancelled"],
        "shipped": ["received"],
        "received": [],
        "cancelled": [],
    },
    "editable_states": ["draft", "packed"],
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


# Shipped defaults for the sales pipeline. No approval half in either: a
# lead is qualified by the salesperson's judgment and an opportunity is won
# by the customer's signature, neither of which is a review step. States are
# the tenant's vocabulary as everywhere — rename or extend freely; the one
# server-written state is the lead's `converted` (the conversion bridge
# lands there), anchored by ROLE so renaming it keeps the bridge working.
DEFAULT_LEAD_MACHINE: dict = {
    "initial": "new",
    "states": ["new", "contacted", "qualified", "converted", "disqualified"],
    "transitions": {
        "new": ["contacted", "qualified", "disqualified"],
        "contacted": ["qualified", "disqualified"],
        "qualified": ["converted", "disqualified"],
        # a dead lead may come back to life — 半年后又有预算了
        "disqualified": ["contacted"],
        "converted": [],
    },
    "editable_states": ["new", "contacted", "qualified"],
}

DEFAULT_OPPORTUNITY_MACHINE: dict = {
    "initial": "open",
    "states": ["open", "quoting", "negotiating", "won", "lost"],
    "transitions": {
        "open": ["quoting", "negotiating", "won", "lost"],
        "quoting": ["negotiating", "won", "lost"],
        "negotiating": ["won", "lost"],
        "won": [],
        "lost": [],
    },
    "editable_states": ["open", "quoting", "negotiating"],
}

# Shipped default for the picking run. Warehouse work like the shipment:
# no approval half, one functional grant files and advances. `picked` is
# the handoff point — the shipment copies the lines and the stock posts
# there; `completed` closes the run after the goods left.
DEFAULT_PICKLIST_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "picking", "picked", "completed", "cancelled"],
    "transitions": {
        "draft": ["picking", "cancelled"],
        "picking": ["picked", "cancelled"],
        "picked": ["completed", "cancelled"],
        "completed": [],
        "cancelled": [],
    },
    # picked_quantity is recorded WHILE picking, so lines stay editable there
    "editable_states": ["draft", "picking"],
}

# Shipped default for contracts. Signing is a fact the desk records, not a
# review step the server owns: one functional grant files and advances,
# and a tenant that wants review before signing says so in its workflow
# definition and works it as todos and approval facts against the
# contract. `signed` is a literal-name stamp (signed_at), the shipment
# convention; `active` is when it governs, `expired`/`terminated` how it
# ends.
DEFAULT_CONTRACT_MACHINE: dict = {
    "initial": "draft",
    "states": ["draft", "negotiating", "signed", "active", "expired", "terminated", "cancelled"],
    "transitions": {
        "draft": ["negotiating", "signed", "cancelled"],
        "negotiating": ["draft", "signed", "cancelled"],
        "signed": ["active", "terminated"],
        "active": ["expired", "terminated"],
        "expired": [],
        "terminated": [],
        "cancelled": [],
    },
    "editable_states": ["draft", "negotiating"],
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
    # kind-split types: rows live in the order tables under order_kind
    # ='return', with their own lifecycle — see KIND_SPLIT_MACHINE_TYPES
    "sales_return": DEFAULT_SALES_RETURN_MACHINE,
    "purchase_return": DEFAULT_PURCHASE_RETURN_MACHINE,
    "shipment": DEFAULT_SHIPMENT_MACHINE,
    "picklist": DEFAULT_PICKLIST_MACHINE,
    "contract": DEFAULT_CONTRACT_MACHINE,
    "lead": DEFAULT_LEAD_MACHINE,
    "opportunity": DEFAULT_OPPORTUNITY_MACHINE,
    "invoice": DEFAULT_INVOICE_MACHINE,
    "payment": DEFAULT_PAYMENT_MACHINE,
}
# What the SERVER needs from a machine, named by ROLE rather than by state
# name. State names are the tenant's vocabulary — a workspace may call the
# post-approval invoice state `approved` instead of `issued`, start claims at
# `open` instead of `draft` — and the server has no business freezing their
# words. What it does need is to find its own anchor points inside whatever
# vocabulary the tenant chose:
#
#   submitted — where POST /{family}/submit lands a document (every family)
#   issued    — an invoice that is live and settleable, past any approval:
#               issued_at stamps on entering it, reimbursement invoices
#               arrive in it
#   paid      — a payment that has actually moved: paid_at stamps on it
#
# A machine says nothing → each role resolves to its own name (the shipped
# machines all use role names as state names, so every existing tenant
# machine keeps working untouched). A machine that renames a state carries a
# `roles` map pointing the role at the new name:
#
#   {"states": ["draft", "submitted", "approved", ...],
#    "roles": {"issued": "approved"}, ...}
#
# The previous anchor ({"required_states": {"draft", "submitted"}, initial ==
# "draft"}) enforced the NAMES, which made renaming impossible by validation
# — and left `issued` unanchored, so renaming IT passed validation and then
# broke the reimbursement route at runtime.
STATE_ROLES: dict[str, tuple[str, ...]] = {
    object_type: ("submitted",) for object_type in BUILTIN_MACHINES
}
STATE_ROLES["invoice"] = ("submitted", "issued")
# revising a quotation steps the source aside, and /send marks it delivered —
# the server writes both states
STATE_ROLES["sales_quotation"] = ("submitted", "superseded", "sent")
STATE_ROLES["payment"] = ("submitted", "paid")
# a shipment is never submitted-for-approval: the warehouse records it and
# moves it; the server writes none of its states by role
STATE_ROLES["shipment"] = ()
# picking is warehouse work too: recorded and advanced, never submitted
STATE_ROLES["picklist"] = ()
# a contract is never submitted-for-approval by the server: signing is
# recorded, review is the tenant's own todos and approval facts
STATE_ROLES["contract"] = ()
# the pipeline has no submit: the salesperson records and advances their own.
# The lead keeps one anchor — the conversion bridge writes `converted` — and
# the opportunity none: won/lost are the salesperson's PATCH, and closed_at
# stamps on the literal names (the shipment convention: renamed states move
# without stamping, and the fact is PATCHed by whoever knows it)
STATE_ROLES["lead"] = ("converted",)
STATE_ROLES["opportunity"] = ()


def state_for_role(machine: dict, object_type: str, role: str) -> str:
    """The tenant's name for one of the server's anchor states.

    Raises with the exact fix when the machine cannot answer, because the
    caller is mid-request and "the machine is wrong" without saying HOW is a
    dead end for the admin reading the error.
    """
    name = (machine.get("roles") or {}).get(role, role)
    if name not in set(machine.get("states", ())):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"this workspace's {object_type} machine has no state for the "
                f"{role!r} role: neither a state named {role!r} nor a "
                f'`"roles": {{"{role}": "<your name for it>"}}` entry. '
                "Add the role mapping to the machine to use your own state name"
            ),
        )
    return name


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
    roles = machine.get("roles", {})
    if not isinstance(roles, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in roles.items()
    ):
        fail("roles must map role names to state names")
    for role, target in roles.items():
        if target not in state_set:
            fail(f"roles[{role!r}] names {target!r}, which is not a declared state")
    if entity_kind == "builtin":
        required = STATE_ROLES.get(object_type)
        if required is None:
            fail(f"unknown builtin entity {object_type!r}")
        unknown = set(roles) - set(required)
        if unknown:
            fail(
                f"builtin {object_type} has no {sorted(unknown)} role — "
                f"it anchors {sorted(required)}"
            )
        # every role must RESOLVE — to its own name or through the map. This
        # is what replaced requiring the names themselves: rename freely, but
        # tell the server where its anchors went.
        for role in required:
            if roles.get(role, role) not in state_set:
                fail(
                    f"the {role!r} role resolves to no state: rename it with "
                    f'`"roles": {{"{role}": "<state>"}}` or keep a state named {role!r}'
                )


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
    # a kind-split listing (orders AND returns in one table) may span two
    # machines: pass the tuple, and the vocabulary is their union
    types = (object_type,) if isinstance(object_type, str) else tuple(object_type)
    states: set[str] = set()
    for machine_type in types:
        states |= set(get_builtin_machine(db, tenant_id, machine_type).get("states", ()))
    if status_filter not in states:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"unknown status {status_filter!r} for {' / '.join(types)}; "
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
