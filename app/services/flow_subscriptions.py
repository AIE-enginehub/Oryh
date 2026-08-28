"""Which of a tenant's object types the hosted agent drives, by default.

Enrolment used to be opt-in per type, and running it for a while showed the
default was backwards: workspaces published a routing map for five document
families and enrolled one, because enrolling was a separate act somebody had to
remember. A map published and never followed is the same silent nothing as a
subscription pointing at a type the runner cannot poll.

So the default flips. Every builtin family the hosted agent may advance gets a
subscription row, enabled, with everything derivable derived. Turning one off is
an explicit `enabled=false`, and **sync never turns it back on** — the same rule
the admin-role top-up follows, for the same reason: a tenant's decision to
narrow something must survive every deploy.

Rows rather than a computed list, deliberately. A synthesized entry has no id,
and `flow_runs.subscription_id`, the park state and `Actor.write_scope` all hang
off one. Provisioning keeps every downstream contract exactly as it was — the
write boundary in particular is still read from rows, and this change does not
touch it.

What is NOT defaulted: tenant-defined object types. Their driver is a skill the
tenant wrote, and nothing here can guess its name. Those stay opt-in.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.entity_types import HOSTED_DRIVABLE_ENTITY_TYPES, KIND_SPLIT_MACHINE_TYPES
from app.core.permissions import HOSTED_FLOW_AGENT_PERMISSIONS, PRINCIPAL_HOSTED_FLOW_AGENT
from app.models import ApiKey, FlowSubscription, TenantSkill
from app.services.audit_trail import catalogue_write
from app.services.state_machines import editable_states, get_builtin_machine

DEFAULT_CADENCE_SECONDS = 300


def derived_queue_filter(db: Session, tenant_id: str, entity_type: str) -> dict:
    """The states a document sits in while it waits to be routed.

    Read from the tenant's OWN machine, not from a constant, so a workspace that
    renamed `submitted` gets its own word and keeps getting it. Every shipped
    machine lands on exactly one such state today; the derivation handles more
    because a tenant may add one.

    The definition is structural: a state an editable state transitions INTO,
    minus the terminal ones. `draft` and `returned` are the filer's to fix, and
    `paid` / `void` are over — what is left is in flight. Post-approval states
    like `issued` or `received` are excluded because they are waiting on money
    or goods, not on a person to route them.

    This matters twice over: the filter is also the hosted agent's write
    boundary, so deriving it narrow is deriving the boundary narrow.

    A kind-split family's queue path serves BOTH kinds — `/sales-orders` holds
    orders and returns — so the landing states union over the family's machine
    and its split machines. Without the union, a tenant renaming the ORDER
    machine's submitted would silently drop every submitted RETURN out of the
    hosted queue: both machines happen to say `submitted` today, and deriving
    from one of them is correct only as long as that coincidence holds.
    """
    machine_types = [entity_type] + sorted(
        split for split, home in KIND_SPLIT_MACHINE_TYPES.items() if home == entity_type
    )
    landing: set[str] = set()
    for machine_type in machine_types:
        machine = get_builtin_machine(db, tenant_id, machine_type)
        transitions = machine.get("transitions") or {}
        editable = editable_states(machine, machine_type)
        # A state absent from `transitions` has no way out, same as one mapped
        # to an empty list. `cancelled` reaches this branch from every machine.
        landing |= {
            state
            for source in editable
            for state in transitions.get(source, [])
            if transitions.get(state) and state not in editable
        }
    if not landing:
        # A machine with no route out of its editable states cannot be driven at
        # all. An empty filter would hand the agent every record of the type —
        # and every record as its write boundary — so refuse to guess.
        return {}
    if len(landing) == 1:
        return {"status": next(iter(landing))}
    return {"status": sorted(landing)}


def derived_driver_skill(db: Session, tenant_id: str, entity_type: str) -> str | None:
    """The skill that gates on this family's advance verb.

    One-to-one across the shipped catalog since the invoice flow was split out
    of the payment one, and `tests/test_new_document_family.py` keeps it that
    way. But the catalog is not the whole registry: a tenant may author a skill
    gating on the same verb, and one really did — 晶诚's `jc-warranty-card-flow`
    holds `timesheet.advance` and sorts before `oryh-timesheet-approval-flow`,
    so picking by name alone made a customer's own skill the platform's driver
    for a builtin family. Nobody asked for that and nobody would have seen it.

    So the catalog wins for a builtin family. A workspace that genuinely wants
    its own skill driving timesheets says so by editing the subscription, which
    is a decision on the record rather than a side effect of a name.

    Returns None rather than guessing if the shipped driver has been archived or
    re-gated. An enrolment without a driver is still worth recording, and the
    console shows it as needing attention.
    """
    verb = HOSTED_ADVANCE_VERBS.get(entity_type)
    if verb is None:
        return None
    skill = db.scalars(
        select(TenantSkill)
        .where(
            TenantSkill.tenant_id == tenant_id,
            TenantSkill.status == "active",
            TenantSkill.required_capability == verb,
        )
        .order_by(
            (TenantSkill.kind != "product"),  # ours first, then anyone else's
            TenantSkill.name.asc(),
        )
    ).first()
    return skill.name if skill is not None else None


# entity_type -> the advance verb its driver skill gates on. Declared here
# rather than imported from `routes.DOCUMENT_FAMILIES` because that module
# imports this layer; `tests/test_new_document_family.py` pins the two together.
HOSTED_ADVANCE_VERBS: dict[str, str] = {
    "employee_leave": "leave.advance",
    "expense_claim": "expense.advance",
    "invoice": "invoice.advance",
    "payment": "payment.advance",
    "purchase_request": "purchase.advance",
    "sales_order": "order.advance",
    "sales_quotation": "quotation.advance",
    "timesheet_header": "timesheet.advance",
}


def active_hosted_key_id(db: Session, tenant_id: str) -> str | None:
    """The credential a provisioned subscription runs as.

    `Actor.write_scope` is built from the rows belonging to the authenticating
    key, so a row with no `api_key_id` is enrolled on paper and refused on every
    write. During a rotation window two keys are active; the oldest is chosen so
    that provisioning does not silently move existing work onto a key the
    operator has not cut over to yet.
    """
    key = db.scalars(
        select(ApiKey)
        .where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT,
            ApiKey.is_active.is_(True),
        )
        .order_by(ApiKey.created_at.asc())
    ).first()
    return key.id if key is not None else None


@catalogue_write
def provision_flow_subscriptions(db: Session, tenant_id: str) -> int:
    """Give the tenant a subscription row for every drivable builtin family.

    Creates what is missing and touches nothing that exists — a row switched off
    stays off, a hand-tuned `queue_filter` stays as typed. Returns the number
    created.

    Nothing starts running as a side effect of this: a subscription whose
    workflow definition is unpublished spends no agent turn and says
    `workflow_definition_missing`. Publishing the map is what starts the work,
    which is the point — the map IS the statement that this is how the document
    should route.
    """
    # Sessions here run `autoflush=False`, and on a new tenant the skills and
    # definitions this reads were added by the calls just above and are still
    # pending. Without the flush every derivation silently comes back empty —
    # a subscription with no driver, which is the failure this whole change is
    # meant to stop shipping.
    db.flush()
    existing = {
        row.entity_type
        for row in db.scalars(
            select(FlowSubscription).where(FlowSubscription.tenant_id == tenant_id)
        )
    }
    api_key_id = active_hosted_key_id(db, tenant_id)
    created = 0
    for entity_type in HOSTED_DRIVABLE_ENTITY_TYPES:
        if entity_type in existing:
            continue
        driver_skill = derived_driver_skill(db, tenant_id, entity_type)
        if not driver_skill:
            # No installed skill can drive this family, so a row here could
            # never run — it would only sit on the flow card looking enabled,
            # which is the #119 confusion in provisioned form. The cloud
            # catalog always carries the flow skills, so there this branch is
            # dead; a standalone deployment without them simply gets no
            # default enrolment, and authoring a flow skill later is what
            # creates the subscription (via the console, deliberately).
            continue
        db.add(
            FlowSubscription(
                tenant_id=tenant_id,
                entity_type=entity_type,
                driver_skill=driver_skill,
                queue_filter=derived_queue_filter(db, tenant_id, entity_type),
                cadence_seconds=DEFAULT_CADENCE_SECONDS,
                api_key_id=api_key_id,
                enabled=True,
                created_by="platform:default",
            )
        )
        created += 1
    return created


def attach_hosted_key(db: Session, tenant_id: str, api_key_id: str) -> int:
    """Bind subscriptions that have no credential to a freshly issued one.

    Rows are provisioned before a tenant has a hosted key — enrolment is a
    default, issuing the credential is a platform act, and they happen in
    whichever order operations reaches them. Without this the rows sit enabled
    and outside every `write_scope`, which is enrolled-on-paper and refused in
    practice.
    """
    orphans = db.scalars(
        select(FlowSubscription).where(
            FlowSubscription.tenant_id == tenant_id,
            FlowSubscription.api_key_id.is_(None),
        )
    ).all()
    for row in orphans:
        row.api_key_id = api_key_id
    return len(orphans)


__all__ = [
    "DEFAULT_CADENCE_SECONDS",
    "HOSTED_ADVANCE_VERBS",
    "active_hosted_key_id",
    "attach_hosted_key",
    "derived_driver_skill",
    "derived_queue_filter",
    "provision_flow_subscriptions",
]

assert set(HOSTED_ADVANCE_VERBS) == set(HOSTED_DRIVABLE_ENTITY_TYPES)
assert set(HOSTED_ADVANCE_VERBS.values()) <= set(HOSTED_FLOW_AGENT_PERMISSIONS)
