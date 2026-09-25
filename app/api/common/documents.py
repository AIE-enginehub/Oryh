"""The document families: status scope, submit/delete/restore, todos on documents, editability.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations




from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    attributed,
    enforce_member_employee,
    has_permission,
    require_permission,
)
from app.models import (
    ApprovalRecord,
    Campaign,
    Contract,
    EmployeeLeave,
    Event,
    ExpenseClaim,
    Invoice,
    Lead,
    Opportunity,
    Payment,
    Picklist,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderItem,
    SalesQuotation,
    Shipment,
    TimesheetHeader,
    Todo,
)
from app.schemas import (
    EmployeeLeaveRead,
    ExpenseClaimRead,
    ContractRead,
    InvoiceRead,
    CampaignRead,
    EventRead,
    LeadRead,
    PicklistRead,
    OpportunityRead,
    PaymentRead,
    PurchaseOrderRead,
    PurchaseRequestRead,
    SalesOrderRead,
    SalesQuotationRead,
    ShipmentRead,
    TimesheetHeaderRead,
)
from app.services.audit import (
    record_audit,
)
from app.core.entity_types import DOCUMENT_ENTITY_TYPES
from app.services.state_machines import (
    editable_states,
    get_builtin_machine,
    is_terminal_state,
    state_for_role,
    validate_transition,
)
from dataclasses import (
    dataclass,
)
from datetime import (
    datetime,
    timezone,
)
from fastapi import (
    Response,
)
from app.api.deps import (
    Actor,
)
from app.api.common.core import (
    DocumentFamily,
    envelope,
    get_scoped_or_404,
)
from app.api.common.charging import (
    recheck_charged_document,
)
from app.api.common.numbering import (
    allocate_document_number,
)

DOCUMENT_FAMILIES: dict[type, DocumentFamily] = {
    TimesheetHeader: DocumentFamily(
        "timesheet_header", "timesheet entries", "header",
        "timesheet.submit_own", TimesheetHeaderRead, "timesheet",
        lambda d: {
            "employee_id": d.employee_id,
            "period_start": d.period_start.isoformat(),
            "period_end": d.period_end.isoformat(),
        },
        "timesheet", advance_permission="timesheet.advance",
    ),
    EmployeeLeave: DocumentFamily(
        # No line items: a leave request is one absence, so the items_phrase /
        # parent_noun pair only ever surfaces in the editable-state 409, where
        # it reads correctly because that gate also guards header edits.
        "employee_leave", "leave details", "request",
        "leave.submit_own", EmployeeLeaveRead, "leave",
        lambda d: {
            "employee_id": d.employee_id,
            "leave_type": d.leave_type,
            "from_date": d.from_date.isoformat(),
            "thru_date": d.thru_date.isoformat(),
            "duration_days": float(d.duration_days),
        },
        "leave", advance_permission="leave.advance",
    ),
    ExpenseClaim: DocumentFamily(
        "expense_claim", "expense items", "claim",
        "expense.submit_own", ExpenseClaimRead, "expense",
        lambda d: {"employee_id": d.employee_id, "title": d.title},
        "expense", advance_permission="expense.advance",
    ),
    PurchaseRequest: DocumentFamily(
        "purchase_request", "purchase request items", "request",
        "purchase.submit_own", PurchaseRequestRead, "purchase",
        lambda d: {"employee_id": d.employee_id, "title": d.title},
        "purchase", advance_permission="purchase.advance",
    ),
    SalesQuotation: DocumentFamily(
        "sales_quotation", "quotation items", "quotation",
        "quotation.submit_own", SalesQuotationRead, "quotation",
        lambda d: {
            "employee_id": d.employee_id,
            "quote_number": d.quote_number,
            "revision_no": d.revision_no,
            "title": d.title,
        },
        "quotation", advance_permission="quotation.advance",
        editable_hint="; a sent quotation is revised, not edited",
        number_prefix="QT-", number_field="quote_number", lock_scope="sales_quotation_number",
    ),
    SalesOrder: DocumentFamily(
        "sales_order", "sales order items", "order",
        "order.submit_own", SalesOrderRead, "order",
        lambda d: {"employee_id": d.employee_id, "order_no": d.order_no, "title": d.title},
        "order", advance_permission="order.advance",
        number_prefix="SO-", number_field="order_no", lock_scope="sales_order_number",
        machine_type_for=lambda d: "sales_return" if d.order_kind == "return" else "sales_order",
    ),
    PurchaseOrder: DocumentFamily(
        # procurement is a function, not "my documents": one capability files
        # AND advances, no owner to enforce, and (for now) no delete attribution
        "purchase_order", "purchase order items", "order",
        "purchase_order.manage", PurchaseOrderRead, "purchase_order",
        lambda d: {"po_number": d.po_number},
        "purchase order", advance_permission=None,
        owner_checked=False, attributed_delete=False,
        number_prefix="PO-", number_field="po_number", lock_scope="purchase_order_number",
        machine_type_for=lambda d: "purchase_return" if d.order_kind == "return" else "purchase_order",
    ),
    Contract: DocumentFamily(
        # a file and its located clauses: one functional grant files and
        # advances (signing is a recorded fact; review is the tenant's own
        # todos), scoped on the side derived from the counterparty
        "contract", "contract lines", "contract",
        "contract.manage", ContractRead, "contract",
        lambda d: {"contract_no": d.contract_no, "title": d.title, "side": d.side},
        "contract", advance_permission=None,
        permission_scope=lambda d: d.side,
        owner_checked=False, attributed_delete=False,
        number_prefix="CT-", number_field="contract_no", lock_scope="contract_number",
    ),
    Picklist: DocumentFamily(
        # warehouse work like the shipment: one functional grant files AND
        # advances, no owner, everyone reads
        "picklist", "picklist lines", "picklist",
        "inventory.manage", PicklistRead, "picklist",
        lambda d: {"picklist_no": d.picklist_no, "sales_order_id": d.sales_order_id},
        "picklist", advance_permission=None,
        owner_checked=False, attributed_delete=False,
        number_prefix="PL-", number_field="picklist_no", lock_scope="picklist_number",
    ),
    Shipment: DocumentFamily(
        # freight is the shipment desk's: one grant files AND advances, like
        # the purchase order, and everyone in the workspace reads. The stock
        # ledger's grant (`inventory.manage`) implies it — see IMPLIED_BY —
        # so the warehouse keeps every leg; delete and restore once checked
        # `inventory.manage` alone while every other write checked this one
        "shipment", "shipment items", "shipment",
        "shipment.manage", ShipmentRead, "shipment",
        lambda d: {"shipment_no": d.shipment_no, "direction": d.direction},
        "shipment", advance_permission=None,
        owner_checked=False, attributed_delete=False,
        number_prefix="SH-", number_field="shipment_no", lock_scope="shipment_number",
    ),
    Campaign: DocumentFamily(
        # marketing's, run for everyone: no owner-own limit, no approval half,
        # no lines. What it earned is read from the leads and deals naming it.
        "campaign", "campaign details", "campaign",
        "campaign.manage", CampaignRead, "campaign",
        lambda d: {"campaign_no": d.campaign_no, "name": d.name},
        "campaign", advance_permission=None,
        owner_checked=False, attributed_delete=False,
        number_prefix="CMP-", number_field="campaign_no", lock_scope="campaign_number",
    ),
    Event: DocumentFamily(
        # a scheduled contact: personal like the lead, approval-free; planned,
        # then held or cancelled. No lines — participants are their own rows.
        "event", "event details", "event",
        "crm.own", EventRead, "event",
        lambda d: {"event_no": d.event_no, "subject": d.subject},
        "event", advance_permission=None,
        attributed_delete=False,
        number_prefix="EV-", number_field="event_no", lock_scope="event_number",
    ),
    Lead: DocumentFamily(
        # the pipeline's front door: personal like a quotation (my leads are
        # mine to work), approval-free like a shipment — one grant files AND
        # advances, and the same grant drives the conversion bridge. No
        # lines: items_phrase only ever surfaces in the editable-state 409
        "lead", "lead details", "lead",
        "crm.own", LeadRead, "lead",
        lambda d: {
            "lead_no": d.lead_no,
            "company_name": d.company_name,
            "contact_name": d.contact_name,
        },
        "lead", advance_permission=None,
        attributed_delete=False,
        number_prefix="LD-", number_field="lead_no", lock_scope="lead_number",
    ),
    Opportunity: DocumentFamily(
        # the deal a lead became: the same personal, approval-free shape as
        # the lead, and no lines either
        "opportunity", "opportunity details", "opportunity",
        "crm.own", OpportunityRead, "opportunity",
        lambda d: {"opportunity_no": d.opportunity_no, "title": d.title},
        "opportunity", advance_permission=None,
        attributed_delete=False,
        number_prefix="OPP-", number_field="opportunity_no",
        lock_scope="opportunity_number",
    ),
    Invoice: DocumentFamily(
        # invoicing is a finance function like procurement — no owner-own limit
        # — but unlike the PO it keeps an approval half (开票申请), so filing and
        # advancing are separate grants. The filing capability is checked with
        # the direction as its scope, which is why the routes pass one.
        "invoice", "invoice lines", "invoice",
        "invoice.manage", InvoiceRead, "invoice",
        lambda d: {
            "invoice_no": d.invoice_no,
            "direction": d.direction,
            "title": d.title,
        },
        "invoice", advance_permission="invoice.advance",
        permission_scope=lambda d: d.direction,
        owner_checked=False,
        number_prefix="INV-", number_field="invoice_no", lock_scope="invoice_number",
    ),
    Payment: DocumentFamily(
        # a payment has no lines, so the items_phrase/parent_noun pair only ever
        # shows up in the editable-state 409 the shared plumbing raises; it reads
        # correctly there because that gate also guards edits to the header.
        "payment", "payment details", "payment",
        "payment.record", PaymentRead, "payment",
        lambda d: {
            "payment_no": d.payment_no,
            "direction": d.direction,
            "amount": float(d.amount),
        },
        "payment", advance_permission="payment.advance",
        owner_checked=False, attributed_delete=False,
        number_prefix="PAY-", number_field="payment_no", lock_scope="payment_number",
    ),
}
# one family per document entity type — the list is app/core/entity_types.py's
assert {f.object_type for f in DOCUMENT_FAMILIES.values()} == set(DOCUMENT_ENTITY_TYPES), (
    {f.object_type for f in DOCUMENT_FAMILIES.values()} ^ set(DOCUMENT_ENTITY_TYPES)
)


def status_scope(status_filter: str | None) -> str | None:
    """What a master-data list answers by default: the ACTIVE rows. An
    archived row is history — a bank account entered by mistake, a product
    nobody sells — and history mixed into the everyday answer is how an
    agent sums a dead account into the cash position. `status=archived`
    asks for the history, `status=all` for both; the equality filter
    treats None as "no clause"."""
    if status_filter == "all":
        return None
    return status_filter or "active"


def require_active_row(
    db: Session, model, tenant_id: str, row_id: str | None, noun: str, *, detail: str | None = None
):
    """A pointer at master data must land on a LIVE row: an archived shelf,
    store, account or category names its fix instead of accepting a new
    document; rows already pointing at it keep their pointer — history,
    not a cascade. None passes through, for the nullable pointers. A caller
    that is posting INTO the row (a ledger, a register) passes its own
    `detail`, since "pointing anything new at it" is not what it is doing."""
    if row_id is None:
        return None
    row = get_scoped_or_404(db, model, tenant_id, row_id)
    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail or (
                f"{noun} {row_id} is archived — set it active (PATCH status active) "
                "before pointing anything new at it; existing rows keep their pointer"
            ),
        )
    return row



def require_contract_for(db: Session, tenant_id: str, contract_id: str | None, side: str):
    """A document that names a contract must sit on the contract's SIDE:
    a purchase order executes a purchase contract, a sales order a sales
    one, a sales invoice or an inbound payment a sales one, and so on — a
    crossed pointer is a wrong answer the execution read would repeat."""
    if contract_id is None:
        return None
    contract = get_scoped_or_404(db, Contract, tenant_id, contract_id)
    if contract.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.side != side:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"contract {contract_id} is a {contract.side} contract — this document "
                f"executes the {side} side; a crossed pointer is a wrong answer"
            ),
        )
    return contract


def may_read_payroll(actor: Actor) -> bool:
    """Salaries and payslips are the one thing here that belonging to the
    workspace does not entitle you to read.

    Shared business data is tenant-scoped; a person's own documents are read
    by them, by whoever they were routed to, or with `<family>.read_all`
    (app/api/visibility.py). Pay is stricter than either: hidden from everyone
    without the grant, not just from colleagues. Writing payroll implies reading
    it; `payroll.read` exists separately so a workspace can let someone see the
    numbers without being able to change them."""
    return has_permission(actor, "payroll.read") or has_permission(
        actor, "invoice.manage", "payroll"
    )


def own_employee_id(actor: Actor) -> str | None:
    """The employee this credential IS, when it is a person's. Service keys are
    nobody, so they see their own payslip never — and their whole workspace's
    only with the capability."""
    return actor.employee_id if actor.kind == "user" else None


def visible_payroll_filter(actor: Actor):
    """The payroll visibility rule, as a SQL condition on `invoices`.

    Returned as a clause rather than applied here because it has to be threaded
    into several queries — and the whole value of this gate is that no path
    around it exists. Every read that could surface a payslip, or a payment that
    settles one, goes through this or `billing.py`'s `hide_payroll_payments`.

    Everyone sees their own payslip. That is not a concession: an employee who
    cannot see what they were paid has no way to check it."""
    if may_read_payroll(actor):
        return None
    own = own_employee_id(actor)
    if own is None:
        return Invoice.direction != "payroll"
    return or_(Invoice.direction != "payroll", Invoice.payee_employee_id == own)


def require_family_permission(actor: Actor, family: DocumentFamily, document) -> None:
    """The filing check for a document that already exists. Scopable families
    are checked against the document's own scope (an invoice's direction), so
    a role granted only `invoice.manage:sales` reaches its own documents and
    no others."""
    scope = family.permission_scope(document) if family.permission_scope else None
    require_permission(actor, family.permission, scope)


def _document_read(family: DocumentFamily, document) -> dict:
    return family.read_model.model_validate(document).model_dump(by_alias=True)


def require_machine_state(
    db: Session, actor: Actor, model, status_value: str | None,
    *, object_type: str | None = None, advance_exempt: bool = False,
) -> str:
    """Create-time gate, returning the state the document starts in.

    A new document may start in ANY state of the tenant's machine (history
    imports arrive mid-flow), but never outside it. `None` — the schema
    default — means the machine's own `initial`: state names are the tenant's
    vocabulary, so the server cannot write `"draft"` into the contract and
    survive a workspace that calls that state something else.

    Starting anywhere but `initial` is a status move with no PATCH behind it,
    so it takes the same grant the PATCH would: a family whose advancement is
    a separate capability requires it here too. Without this a member filed
    `{"status": "approved"}` on their own leave, and a 出纳 holding only
    `payment.record` created an outbound payment already `paid` — the whole
    approval half skipped at the door. `advance_exempt` is for a document with
    nothing to approve (an inbound receipt: the money already arrived).

    `object_type` overrides the family's machine key for kind-split tables:
    a sales_orders row being created as a RETURN starts in the return
    machine's vocabulary, and there is no document yet to derive that from."""
    family = DOCUMENT_FAMILIES[model]
    machine = get_builtin_machine(db, actor.tenant_id, object_type or family.object_type)
    if status_value is None:
        return machine["initial"]
    if status_value not in set(machine.get("states", ())):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"status {status_value!r} is not a state of the tenant's {family.state_noun} state machine",
        )
    if status_value != machine["initial"] and family.advance_permission and not advance_exempt:
        require_permission(actor, family.advance_permission)
    return status_value


def require_hosted_write_scope(
    actor: Actor, entity_type: str, row, *, ignore: tuple[str, ...] = ()
) -> None:
    """Hold a hosted flow agent's business writes to its subscriptions.

    A live E2E run: a subscription filtered to one employee's timesheets, and the
    agent returned two other people's. The prompt now states the boundary
    (flow_runner); this makes it mechanical — a model that talks itself into a
    record outside the filter is refused, not trusted.

    Matching is equality on the filter's keys against the row's CURRENT
    (pre-write) attributes. `ignore=("status",)` at the todo/approval sites,
    because status is the queue's ENTRY condition, not the record's identity:
    the agent legitimately returns an in-scope record and must then be able to
    create its rework todo, by which time the status no longer matches. The
    identity keys — employee_id and friends — are what the incident violated,
    and they always apply. A filter key the row lacks counts as a mismatch:
    refusing too much is recoverable, a leaked write is not.
    """
    scope = actor.write_scope
    if scope is None:
        return
    queue_filter = scope.get(entity_type)
    if queue_filter is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"the hosted principal has no enabled subscription for {entity_type}",
        )
    for field_name, expected in queue_filter.items():
        if field_name in ignore:
            continue
        actual = getattr(row, field_name, None)
        # the derived queue filter says `status: [a, b]` when a family has
        # several landing states; the boundary reads it as membership, the
        # same way the queue query does (review R10)
        matches = actual in expected if isinstance(expected, (list, tuple, set, frozenset)) else actual == expected
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"outside this subscription's boundary: {entity_type} record's "
                    f"{field_name} does not match the subscription filter"
                ),
            )


def apply_status_change(db: Session, actor: Actor, document, new_status: str) -> dict:
    """Machine-guarded, audited status move — the PATCH half of every
    lifecycle. Validates the transition and records the audit fact; the
    caller's setattr loop performs the actual write.

    It also closes the open work items when the document is entering a state
    its machine allows no exit from. `leave-no-orphan-work.md` used to tell
    every agent to do this by hand — "retiring it BY STATUS is not handled,
    close your own todos yourself" — which is a second call, on a path where
    the first one has already succeeded. Five payslips is what that costs:
    returned, voided, replaced, approved, and five rework todos still open in
    somebody's queue months later.

    The server needs no opinion about what 作废 or 已完成 mean to decide this.
    Two statements the tenant's own machine makes are enough: no transition
    leaves the state, and the state is not editable. Nothing can be done to
    the document — not its status, not its content — so nothing anyone was
    asked to do to it can be done either. Same certainty as "the subject is
    gone", one step weaker in form and identical in consequence.

    Both halves are load-bearing. Every shipped machine keeps its terminal
    states out of `editable_states`, but a workspace edits its machines, and a
    terminal-but-editable state is a real place to still have work — an
    invoice parked in 已作废 whose lines someone is still correcting for the
    record. So the guard asks the machine rather than assuming the shape.
    """
    family = DOCUMENT_FAMILIES[type(document)]
    if family.advance_permission:
        require_permission(actor, family.advance_permission)
    require_hosted_write_scope(actor, family.object_type, document)
    # the MACHINE follows the row's kind (a return runs a return's life);
    # todo retirement below stays on family.object_type, because todos point
    # at the table's entity type — the same row either way
    machine_type = family.machine_type(document)
    machine = get_builtin_machine(db, document.tenant_id, machine_type)
    validate_transition(machine, document.status, new_status, subject=machine_type)
    record_audit(
        db,
        tenant_id=document.tenant_id,
        action=f"{family.audit_prefix}.status_changed",
        entity_type=family.object_type,
        entity_id=document.id,
        actor=actor.label,
        detail={**family.audit_identity(document), "from": document.status, "to": new_status},
    )
    retire_open_work_if_finished(
        db, actor, machine, family.object_type, document.id,
        current=document.status, new_status=new_status,
        editable=editable_states(machine, machine_type),
    )
    return machine


def record_submission_fact(
    db: Session,
    actor: Actor,
    entity_type: str,
    entity_id: str,
    acted_at: datetime,
) -> None:
    """Write the `submitted` approval fact for a submission the server just made.

    The approval trail is supposed to open with it — `round_no=1,
    sequence_no=1` — and every later decision is ordered against it. It used to
    be the SUBMITTER's job: post the fact if your role carries
    `approval.record`, and if it does not, skip it and let the workflow admin
    backfill from `submitted_at`. Two agents had to remember, one of them
    conditionally, for a fact the server itself performs and already stores.
    They did not always remember, and the integrity audit found 133 decided
    approvals with nothing in front of them.

    So the server writes it. The round is derived rather than passed: a
    submission opens round 1, and each `returned` sends the document back for
    another one, which is exactly the rule the submit skills stated in prose.
    The natural key makes this idempotent against an agent that posts the same
    fact anyway — the create endpoint hands back the existing row — so nothing
    breaks for a skill that has not been updated.
    """
    returns = db.scalar(
        select(func.count())
        .select_from(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == actor.tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
            ApprovalRecord.action == "returned",
        )
    )
    round_no = (returns or 0) + 1
    already = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == actor.tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
            ApprovalRecord.round_no == round_no,
            ApprovalRecord.sequence_no == 1,
            ApprovalRecord.action == "submitted",
        )
    )
    if already is not None:
        return
    db.add(
        ApprovalRecord(
            tenant_id=actor.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            round_no=round_no,
            sequence_no=1,
            action="submitted",
            approver_id=actor.label,
            approver_role="submitter",
            source="system",
            acted_at=acted_at,
        )
    )


def submit_document(db: Session, actor: Actor, model, document_id: str) -> dict:
    """POST .../submit — the one transition a member may drive themselves."""
    family = DOCUMENT_FAMILIES[model]
    document = get_active_document_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    require_hosted_write_scope(actor, family.object_type, document)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    machine_type = family.machine_type(document)
    machine = get_builtin_machine(db, actor.tenant_id, machine_type)
    # "submitted" is a ROLE — the tenant may call the state itself something
    # else, and /submit lands wherever their machine says the role lives
    submitted = state_for_role(machine, machine_type, "submitted")
    if document.status == submitted:
        # idempotent resubmit
        return envelope(_document_read(family, document))
    validate_transition(machine, document.status, submitted, subject=machine_type)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=f"{family.audit_prefix}.submitted",
        entity_type=family.object_type,
        entity_id=document.id,
        actor=actor.label,
        detail={**family.audit_identity(document), "from": document.status},
    )
    document.status = submitted
    document.submitted_at = datetime.now(timezone.utc)
    record_submission_fact(
        db, actor, family.object_type, document.id, document.submitted_at
    )
    complete_rework_todos_for(db, actor, family.object_type, document.id)
    db.commit()
    db.refresh(document)
    return envelope(_document_read(family, document))


def cancel_todos_for(
    db: Session,
    actor: Actor,
    entity_type: str,
    entity_id: str,
    *,
    reason: str,
    todo_type: str | None = None,
) -> int:
    """Close the open todos pointing at a record that has just been deleted.

    HR issued five payslips, the CEO returned them, and five rework todos
    appeared. HR then voided all five and issued five fresh ones, which were
    approved — and the five todos stayed open forever, attached to documents
    that no longer exist. Nothing was wrong with the flow: "fix the returned
    document" and "void it and redo it" are both reasonable, and only the first
    one had anything that closed the todo.

    So the server closes them, and only on the fact it is certain of: the thing
    this work item points at is gone, therefore the work item cannot be done.
    That is not a judgment about the flow — a todo whose subject was deleted is
    unactionable whatever the workspace's rules say.

    `cancelled`, never `completed`. The work was not done, and recording that it
    was would make the trail lie about a person's queue. The partial unique
    index only reserves `open`, so a replacement todo on the same record is free
    to exist the moment this one leaves that state.

    Restoring the document does NOT resurrect these rows. The restored record
    re-enters the flow agent's queue (`without_open_todo=true` is what finds
    it), and letting the agent raise fresh work is both simpler and truer than
    reviving a cancellation — the old todo's text may no longer be what needs
    doing.

    `todo_type` narrows the sweep. A deleted document takes ALL of its work with
    it; a RETURNED one takes only the approval work, because the document still
    exists and a todo like "attach the receipt" is still worth doing.
    """
    conditions = [
        Todo.tenant_id == actor.tenant_id,
        Todo.entity_type == entity_type,
        Todo.entity_id == entity_id,
        Todo.status == "open",
    ]
    if todo_type is not None:
        conditions.append(Todo.todo_type == todo_type)
    open_todos = list(db.scalars(select(Todo).where(*conditions)))
    for todo in open_todos:
        todo.status = "cancelled"
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="todo.cancelled",
            entity_type="todo",
            entity_id=todo.id,
            actor=attributed(actor, None),
            detail={
                "employee_id": todo.employee_id,
                "title": todo.title,
                "target_type": entity_type,
                "target_id": entity_id,
                "reason": reason,
            },
        )
    return len(open_todos)


def retire_open_work_if_finished(
    db: Session,
    actor: Actor,
    machine: dict,
    entity_type: str,
    entity_id: str,
    *,
    current: str,
    new_status: str,
    editable: set[str] | None = None,
) -> int:
    """Close the open todos on a document that has just stopped being movable.

    One function rather than the condition written at each status funnel,
    because there are four of them — `apply_status_change` for the nine
    document families, the quotation's `/close` and `/revise`, and the
    business-object PATCH — and a rule copied four times is a rule that will
    hold in three places.

    `editable` is passed when the caller's machine names editability under a
    different contract than the builtin families do; business-object machines
    have no `editable_states` at all, so their terminal states are simply
    terminal.
    """
    if new_status == current:
        return 0
    if not is_terminal_state(machine, new_status):
        return 0
    if editable is not None and new_status in editable:
        return 0
    return cancel_todos_for(
        db, actor, entity_type, entity_id,
        reason=f"{entity_type} reached {new_status}, which its machine does not leave",
    )


def complete_rework_todos_for(db: Session, actor: Actor, entity_type: str, entity_id: str) -> int:
    """A resubmission completes the rework it answers.

    `_common/leave-no-orphan-work.md` has been telling agents for months that
    "fixing the original closes the rework todo as part of resubmitting". It
    did not. Two skills carried the missing half in prose instead —
    "resubmit, then complete that rework todo (`PATCH /todos/{id}`)" — with the
    consequence spelled out beside it: while it stays open, the document is
    invisible to the flow admin's work queue. So a submit that landed and a
    PATCH that did not left the document in exactly the state the rework was
    supposed to end.

    The server is certain here in a way it is not about most things. A rework
    todo asks the filer to fix this document and send it back; the filer just
    sent it back. Nothing about which approver comes next, or what the
    workspace's rules are, is being decided — only that the thing this work
    item asked for has happened.

    `completed`, not `cancelled`: somebody did the work. That distinction is
    the whole reason both statuses exist, and getting it backwards here would
    make the queue history lie in the more flattering direction.
    """
    open_rework = list(
        db.scalars(
            select(Todo).where(
                Todo.tenant_id == actor.tenant_id,
                Todo.entity_type == entity_type,
                Todo.entity_id == entity_id,
                Todo.status == "open",
                Todo.todo_type == "rework",
            )
        )
    )
    for todo in open_rework:
        todo.status = "completed"
        todo.completed_at = datetime.now(timezone.utc)
        # The docstring above already argues for this line —
        # "`completed`, not `cancelled`: somebody did the work" — and then the
        # row did not say who, so every resubmission left a todo that claimed
        # to be done by nobody. The sibling auto-completion in objects.py
        # (the approval todo the server closes) has always written it; this
        # one was the odd path out.
        todo.completed_by = attributed(actor, None)
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="todo.completed",
            entity_type="todo",
            entity_id=todo.id,
            actor=attributed(actor, None),
            detail={
                "employee_id": todo.employee_id,
                "title": todo.title,
                "target_type": entity_type,
                "target_id": entity_id,
                "reason": "the document it asked to be fixed was resubmitted",
            },
        )
    return len(open_rework)


def delete_document(db: Session, actor: Actor, model, document_id: str, payload=None) -> Response:
    family = DOCUMENT_FAMILIES[model]
    document = get_scoped_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    if document.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    document.deleted_at = datetime.now(timezone.utc)
    if family.attributed_delete:
        document.deleted_by = attributed(actor, payload.deleted_by if payload else None)
        document.delete_reason = payload.delete_reason if payload else None
    cancel_todos_for(
        db, actor, family.object_type, document.id,
        reason=f"{family.object_type} deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def restore_document(db: Session, actor: Actor, model, document_id: str) -> dict:
    family = DOCUMENT_FAMILIES[model]
    document = get_scoped_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    if document.deleted_at is None:
        return envelope(_document_read(family, document))
    document.deleted_at = None
    if family.attributed_delete:
        document.deleted_by = None
        document.delete_reason = None
    # deleting a charged document released its occupation and somebody may have
    # spent that credit since; coming back has to fit what is left
    recheck_charged_document(db, document, label=family.object_type)
    db.commit()
    db.refresh(document)
    return envelope(_document_read(family, document))


def ensure_document_not_deleted(document) -> None:
    if document.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{type(document).__name__} not found"
        )


def get_active_document_or_404(db: Session, model, tenant_id: str, document_id: str):
    document = get_scoped_or_404(db, model, tenant_id, document_id)
    ensure_document_not_deleted(document)
    return document


def ensure_not_consumed_by_an_order(db: Session, document) -> None:
    """A quotation an order was written from is history, not a draft.

    The states a document may be edited in are the tenant's to choose, and a
    workspace that keeps `accepted` editable is making a legitimate choice —
    right up to the moment an order quotes it. From then on the quotation is
    the BASELINE that order is measured against: what was agreed, against what
    was ordered. Move it afterwards and every later answer about the gap is
    computed from a number nobody agreed to.

    This is the same argument `billing.py`'s `ensure_money_fields_editable`
    already makes one level down — a settlement guard is worth nothing if the
    amount it measured can be moved afterwards — applied to the quote→order
    pair.

    Note what it does NOT depend on: any status, any threshold, any reading of
    the tenant's vocabulary. "An order references this quotation" is a fact
    about rows, which is why the server may hold it.
    """
    if not isinstance(document, SalesQuotation):
        return
    order = db.scalar(
        select(SalesOrder.order_no).where(
            SalesOrder.tenant_id == document.tenant_id,
            SalesOrder.quotation_id == document.id,
            SalesOrder.deleted_at.is_(None),
        )
    )
    if order is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"sales order {order} was written from this quotation, so it is "
            "now the agreed baseline and cannot be changed. Revise it into a "
            "new version (POST /sales-quotations/{id}/revise) if the customer "
            "renegotiated, or record the difference on the order itself"
        ),
    )


def ensure_document_editable(db: Session, document) -> None:
    """409 unless the document sits in one of its machine's editable states —
    the single write-gate for lines and adjustments across every family."""
    ensure_not_consumed_by_an_order(db, document)
    family = DOCUMENT_FAMILIES[type(document)]
    machine_type = family.machine_type(document)
    machine = get_builtin_machine(db, document.tenant_id, machine_type)
    editable = editable_states(machine, machine_type)
    if document.status not in editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{family.items_phrase} can only be changed while the "
                f"{family.parent_noun} is in {sorted(editable)}{family.editable_hint}"
            ),
        )


def require_original_order(db: Session, tenant_id: str, model, original_order_id: str | None):
    """A return's linkage to the order it reverses — used by both order
    tables at create and update. The original must exist in this tenant, in
    the SAME table, and be an ORDER: a return pointing at another return
    chains nothing anyone can settle, and one order carrying many returns is
    simply many rows naming the same original."""
    if original_order_id is None:
        return None
    original = get_scoped_or_404(db, model, tenant_id, original_order_id)
    if original.order_kind != "order":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"original_order_id names {original_order_id}, which is itself a "
                "return — a return reverses an ORDER"
            ),
        )
    return original


def allocate_number(db: Session, model, tenant_id: str, *, prefix: str | None = None) -> str:
    """`prefix` overrides the family's series for kind-split rows — a sales
    return allocates SR- beside the orders' SO- so a human tells them apart
    at a glance; uniqueness is still the one (tenant, number) constraint."""
    family = DOCUMENT_FAMILIES[model]
    return allocate_document_number(
        db, tenant_id,
        model=model, number_column=getattr(model, family.number_field),
        prefix=prefix or family.number_prefix,
        lock_scope=family.lock_scope, field=family.number_field,
    )


# the same fetch under the name the line-item paths use
get_live_or_404 = get_active_document_or_404


def require_line_on_document(
    db: Session, tenant_id: str, item_model, parent_field: str, item_field: str,
    parent_id: str, item_id: str,
):
    """The line a write pins to must be a live line of the SAME document."""
    item = get_live_or_404(db, item_model, tenant_id, item_id)
    if getattr(item, parent_field) != parent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{item_field} does not belong to {parent_field}",
        )
    return item


def require_live_line(db: Session, tenant_id: str, item_model, parent_model, parent_field: str, line_id: str):
    """A live line whose document is also live — the shape of every
    cross-document link check and of reading a single line."""
    line = get_live_or_404(db, item_model, tenant_id, line_id)
    ensure_document_not_deleted(get_scoped_or_404(db, parent_model, tenant_id, getattr(line, parent_field)))
    return line


def _sales_order_item_for_link(db: Session, tenant_id: str, sales_order_item_id: str) -> SalesOrderItem:
    """The confirmed sales order line a procure-to-order purchase line pins
    to. Existence and tenant scope only: the ORDER may be in any live state —
    that is the point, procurement happens after confirmation locks it."""
    return require_live_line(db, tenant_id, SalesOrderItem, SalesOrder, "order_id", sales_order_item_id)


def _purchase_request_item_for_po_link(db: Session, tenant_id: str, purchase_request_item_id: str) -> PurchaseRequestItem:
    """The approved request line a PO line orders. Existence and tenant scope
    only — the REQUEST may be in any live state; ordering happens after its
    approval locks it, which is the same reason the sales link works this way."""
    return require_live_line(
        db, tenant_id, PurchaseRequestItem, PurchaseRequest, "request_id", purchase_request_item_id
    )


@dataclass(frozen=True)
class ItemFamily:
    """The four line-item families differ only in data: which document they
    hang off, which capability writes them, whether the parent has an owner,
    which extra columns exist, whether the catalog list price is snapshotted,
    and which cross-document link (if any) a line may pin to."""

    parent_model: type
    parent_field: str
    permission: str
    owner_checked: bool
    read_model: type
    extra_fields: tuple[str, ...]        # payload attrs copied verbatim
    capture_list_price: bool = False     # sales lines snapshot the catalog price
    link_field: str | None = None
    link_validator: object | None = None
    list_order: object | None = None     # model -> order_by columns
    parent_number: str | None = None     # the document's number, carried on its lines
