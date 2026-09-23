"""Who may READ a person's documents: the person, whoever the document was
routed to, and whoever holds the family's read-all grant.

Until now every read was tenant-scoped only — belonging to the workspace
meant reading everyone's timesheets, expense claims, leave, requests,
quotations, orders and pipeline. Payroll was the one exception, gated by
hand in each query. That was tolerable while a workspace was five people
around one table and is wrong everywhere else: "my timesheets" and "all
timesheets" are different entitlements, and the second one is somebody's job.

The rule, for every family a person files "as themselves" (the `*.submit_own`
families, and the personal sales pipeline):

  * **mine** — the document's `employee_id` is the employee this credential
    is;
  * **routed to me** — I hold (or held) a todo on it, or I recorded an
    approval fact on it. A line manager with no finance role reads exactly
    the documents that reached their desk, nothing else;
  * **read-all** — I hold `<family>.read_all`, directly or through a grant
    that cannot be exercised blind: the family's `advance`, and the desks
    downstream of it (whoever ships an order reads orders; whoever pays a
    claim reads claims). `tenant.act_for_any_employee` reads everything it
    may act on. A tenant's own service key bypasses, as it always has.

Lines, adjustments, approval facts, todos and attachments follow their
document. A row you may not read does not exist for you: lists omit it and a
direct read is 404, not 403 — the API does not confirm what it will not show.

Enforcement is at the two choke points every handler already uses —
`list_rows` and `get_scoped_or_404` — reading the actor `get_actor` leaves on
the request's session, so a new endpoint is scoped by being written the
ordinary way. `tests/test_read_visibility.py` walks every GET route as a
stranger and fails on the first row that leaks.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Actor
from app.core.permissions import permissions_cover, permissions_cover_any_scope
from app.models import (
    Activity,
    ApprovalRecord,
    CommunicationEvent,
    Customer,
    EmployeeLeave,
    ExpenseClaim,
    ExpenseItem,
    Lead,
    Opportunity,
    OpportunityContact,
    OpportunityItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
    TimesheetEntry,
    TimesheetHeader,
    Todo,
)


@dataclass(frozen=True)
class PersonalFamily:
    name: str
    capability: str
    model: type
    entity_types: tuple[str, ...]
    # grants that cannot be exercised without reading the whole family
    implied_by: tuple[str, ...]


FAMILIES: tuple[PersonalFamily, ...] = (
    PersonalFamily("timesheet", "timesheet.read_all", TimesheetHeader, ("timesheet_header",),
                   ("timesheet.advance", "invoice.manage", "payroll.manage")),
    PersonalFamily("leave", "leave.read_all", EmployeeLeave, ("employee_leave",),
                   ("leave.advance", "payroll.manage", "employees.manage")),
    PersonalFamily("expense", "expense.read_all", ExpenseClaim, ("expense_claim",),
                   ("expense.advance", "invoice.manage", "payment.record", "payment.advance", "payment.apply")),
    PersonalFamily("purchase", "purchase.read_all", PurchaseRequest, ("purchase_request",),
                   ("purchase.advance", "purchase_order.manage")),
    PersonalFamily("quotation", "quotation.read_all", SalesQuotation, ("sales_quotation",),
                   ("quotation.advance", "order.advance", "contract.manage", "invoice.manage")),
    PersonalFamily("order", "order.read_all", SalesOrder, ("sales_order", "sales_return"),
                   ("order.advance", "shipment.manage", "inventory.manage", "invoice.manage", "payment.record",
                    "payment.advance", "payment.apply", "purchase_order.manage", "contract.manage")),
    PersonalFamily("lead", "crm.read_all", Lead, ("lead",), ("campaign.manage",)),
    PersonalFamily("opportunity", "crm.read_all", Opportunity, ("opportunity",),
                   ("campaign.manage", "quotation.advance", "order.advance")),
)
FAMILY_BY_MODEL: dict[type, PersonalFamily] = {f.model: f for f in FAMILIES}
READ_ALL_CAPABILITIES: tuple[str, ...] = tuple(dict.fromkeys(f.capability for f in FAMILIES))

# rows that follow a document: (parent model, the column that names it)
CHILDREN: dict[type, tuple[type, str]] = {
    TimesheetEntry: (TimesheetHeader, "header_id"),
    ExpenseItem: (ExpenseClaim, "claim_id"),
    PurchaseRequestItem: (PurchaseRequest, "request_id"),
    SalesQuotationItem: (SalesQuotation, "quotation_id"),
    SalesQuotationAdjustment: (SalesQuotation, "quotation_id"),
    SalesOrderItem: (SalesOrder, "order_id"),
    SalesOrderAdjustment: (SalesOrder, "order_id"),
    OpportunityItem: (Opportunity, "opportunity_id"),
    OpportunityContact: (Opportunity, "opportunity_id"),
}
# the record of contact: the author's, and everyone's who may read the deal or lead it is about
CONTACT_RECORDS: tuple[type, ...] = (Activity, CommunicationEvent)


def request_actor(db: Session) -> Actor | None:
    """The authenticated actor of the request this session serves — stamped by
    `get_actor`. None outside a request (scripts, maintenance), where nothing
    is being shown to anybody."""
    return db.info.get("actor")


def can_read_all(actor: Actor, family: PersonalFamily) -> bool:
    if actor.bypasses_permissions:
        return True
    if permissions_cover(actor.permissions, family.capability) or \
            permissions_cover(actor.permissions, "tenant.act_for_any_employee"):
        return True
    return any(permissions_cover_any_scope(actor.permissions, grant) for grant in family.implied_by)


def _own(actor: Actor) -> str | None:
    return actor.employee_id if actor.kind == "user" else None


def _family_clause(actor: Actor, family: PersonalFamily):
    """SQL condition on the family's document table, or None when unrestricted."""
    if can_read_all(actor, family):
        return None
    model = family.model
    parts = []
    own = _own(actor)
    if own is not None:
        parts.append(model.employee_id == own)
        parts.append(model.id.in_(
            select(Todo.entity_id).where(
                Todo.tenant_id == actor.tenant_id, Todo.employee_id == own, Todo.entity_type.in_(family.entity_types))
        ))
    parts.append(model.id.in_(
        select(ApprovalRecord.entity_id).where(
            ApprovalRecord.tenant_id == actor.tenant_id, ApprovalRecord.approver_id == actor.label,
            ApprovalRecord.entity_type.in_(family.entity_types))
    ))
    return or_(*parts)


def visible_clause(actor: Actor | None, model):
    """The condition a SELECT of `model` must carry for this actor, or None."""
    if actor is None:
        return None
    family = FAMILY_BY_MODEL.get(model)
    if family is not None:
        return _family_clause(actor, family)
    if model in CHILDREN:
        parent, column = CHILDREN[model]
        clause = _family_clause(actor, FAMILY_BY_MODEL[parent])
        return None if clause is None else getattr(model, column).in_(select(parent.id).where(clause))
    if model in CONTACT_RECORDS:
        lead_clause = _family_clause(actor, FAMILY_BY_MODEL[Lead])
        deal_clause = _family_clause(actor, FAMILY_BY_MODEL[Opportunity])
        if lead_clause is None and deal_clause is None:
            return None
        parts = []
        own = _own(actor)
        if own is not None:
            parts.append(model.employee_id == own)
        parts.append(model.lead_id.in_(select(Lead.id).where(lead_clause)) if lead_clause is not None else model.lead_id.is_not(None))
        parts.append(model.opportunity_id.in_(select(Opportunity.id).where(deal_clause)) if deal_clause is not None
                     else model.opportunity_id.is_not(None))
        if own is not None:
            # the account owner reads what anyone said to their customer
            parts.append(model.customer_id.in_(
                select(Customer.id).where(Customer.tenant_id == actor.tenant_id, Customer.owner_employee_id == own)))
        return or_(*parts)
    if model is Todo:
        if actor.bypasses_permissions or permissions_cover(actor.permissions, "todos.assign") or \
                permissions_cover(actor.permissions, "tenant.act_for_any_employee"):
            return None
        parts = [Todo.created_by == actor.label]
        if _own(actor) is not None:
            parts.append(Todo.employee_id == _own(actor))
        return or_(*parts)
    if model is ApprovalRecord:
        restricted = [(f, _family_clause(actor, f)) for f in FAMILIES]
        restricted = [(f, c) for f, c in restricted if c is not None]
        if not restricted:
            return None
        hidden_types = tuple(t for f, _c in restricted for t in f.entity_types)
        parts = [ApprovalRecord.approver_id == actor.label, ApprovalRecord.entity_type.not_in(hidden_types)]
        for family, clause in restricted:
            parts.append(and_(
                ApprovalRecord.entity_type.in_(family.entity_types),
                ApprovalRecord.entity_id.in_(select(family.model.id).where(clause)),
            ))
        return or_(*parts)
    return None


def scoped(db: Session, stmt, model=None):
    """`stmt` narrowed to what the request's actor may read. `model` defaults
    to the statement's first entity — the row being listed."""
    actor = request_actor(db)
    if actor is None:
        return stmt
    if model is None:
        descriptions = getattr(stmt, "column_descriptions", None) or []
        model = descriptions[0].get("entity") if descriptions else None
    if model is None:
        return stmt
    clause = visible_clause(actor, model)
    return stmt if clause is None else stmt.where(clause)


def is_visible(db: Session, instance) -> bool:
    """Whether the request's actor may read this already-loaded row."""
    actor = request_actor(db)
    if actor is None:
        return True
    model = type(instance)
    clause = visible_clause(actor, model)
    if clause is None:
        return True
    return db.scalar(select(model.id).where(model.id == instance.id, clause)) is not None


def _singular(table: str) -> str:
    return table[:-3] + "y" if table.endswith("ies") else table[:-1] if table.endswith("s") else table


def scoped_models() -> dict[str, type]:
    """Every scoped model by the name audit rows, links and todos use for it
    (the table's singular), plus the entity-type aliases families declare."""
    models: dict[str, type] = {}
    for model in [f.model for f in FAMILIES] + list(CHILDREN) + list(CONTACT_RECORDS) + [Todo, ApprovalRecord]:
        models[_singular(model.__tablename__)] = model
        # the audit listener's own spelling (`opportunities` → `opportunitie`)
        models[model.__tablename__[:-1]] = model
        models[model.__tablename__] = model
    for family in FAMILIES:
        for alias in family.entity_types:
            models[alias] = family.model
    return models


def entity_visible(db: Session, entity_type: str, entity_id: str) -> bool:
    """Whether the actor may read the document an attachment, link or fact
    points at — for rows that carry (entity_type, entity_id) instead of a
    foreign key."""
    actor = request_actor(db)
    if actor is None:
        return True
    model = scoped_models().get(entity_type)
    if model is None:
        return True
    clause = visible_clause(actor, model)
    if clause is None:
        return True
    return db.scalar(select(model.id).where(model.id == entity_id, clause)) is not None


__all__ = [
    "FAMILIES", "READ_ALL_CAPABILITIES", "can_read_all", "entity_visible", "is_visible", "request_actor",
    "scoped", "visible_clause",
]
