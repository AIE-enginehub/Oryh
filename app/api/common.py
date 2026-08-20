"""Response and pagination plumbing shared by every API module.

One envelope shape for the whole surface: `{"data": …, "meta": …}`, with
pagination meta only when the caller asked for a page. These lived as
verbatim copies in routes.py and workflows.py before being pulled here.
"""

from __future__ import annotations

import uuid as uuid_module

from types import SimpleNamespace
from typing import Annotated

from urllib.parse import quote

from fastapi import Depends, HTTPException, status
from sqlalchemy import Uuid, func, or_, select
from sqlalchemy.orm import Session

import hashlib
import uuid
from app.api.deps import (
    attributed,
    enforce_member_employee,
    has_permission,
    require_permission,
)
from app.models import (
    ApprovalRecord,
    Attachment,
    BillingAccount,
    Customer,
    EmployeeLeave,
    ExpenseClaim,
    ExpenseItem,
    Invoice,
    InvoiceItem,
    Payment,
    Product,
    ProductSku,
    Project,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
    TimesheetHeader,
    Todo,
    Vendor,
)
from app.schemas import (
    EmployeeLeaveRead,
    ExpenseClaimRead,
    InvoiceRead,
    PaymentRead,
    PurchaseOrderAdjustmentRead,
    PurchaseOrderItemRead,
    PurchaseOrderRead,
    PurchaseRequestItemRead,
    PurchaseRequestRead,
    SalesOrderAdjustmentRead,
    SalesOrderItemRead,
    SalesOrderRead,
    SalesQuotationAdjustmentRead,
    SalesQuotationItemRead,
    SalesQuotationRead,
    TimesheetHeaderRead,
)
from app.services import (
    document_import,
)
from app.services.audit import (
    record_audit,
)
from app.services.master_data_import import (
    bulk_upsert,
)
from app.services.state_machines import (
    editable_states,
    get_builtin_machine,
    is_terminal_state,
    state_for_role,
    validate_transition,
)
from app.services.type_options import (
    require_type_option,
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
from sqlalchemy import (
    text,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from app.api.deps import Actor, get_actor


def get_tenant_id(actor: Annotated[Actor, Depends(get_actor)]) -> str:
    return actor.tenant_id


def envelope(data, total: int | None = None) -> dict:
    meta: dict[str, int] = {}
    if total is not None:
        meta["total"] = total
    return {"data": data, "meta": meta}


def paginated_envelope(data, *, total: int, page: int, page_size: int) -> dict:
    return {
        "data": data,
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            # Keep page=1 a valid, stable empty-state location for the
            # console instead of reporting an unusable zero-page result.
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


def requested_pagination(page: int | None, size: int | None) -> tuple[int, int] | None:
    """Keep legacy list semantics unless pagination was explicitly requested.

    Supplying either parameter opts into pagination; the omitted counterpart
    receives the console default. This lets old clients continue to receive the
    complete result set while new clients can use a conventional page/size
    contract.
    """
    if page is None and size is None:
        return None
    return page or 1, size or 50


def page_only_pagination(page: int | None, size: int) -> tuple[int, int] | None:
    """The master-data page contract: only `page` opts into pagination.

    These endpoints shipped `size` with a default before pagination existed,
    so `size` alone cannot opt in — it sizes the page once `page` asks for
    one, and omitting `page` keeps the full-list contract.
    """
    if page is None:
        return None
    return page, size


def list_rows(
    db: Session,
    stmt,
    *,
    filters: dict | None = None,
    keyword: str | None = None,
    keyword_columns: tuple = (),
    order_by: tuple,
    pagination: tuple[int, int] | None,
    read_model: type | None = None,
    by_alias: bool = True,
    render=None,
) -> dict:
    """The one list tail behind every collection endpoint: equality filters,
    a keyword scan across the endpoint's columns, the family's exact ordering,
    and whichever envelope the pagination contract asks for.

    Endpoints keep their explicitly typed query params — they are the OpenAPI
    surface — and pass the pieces here as data. `pagination` arrives computed
    because the opt-in rules differ by family (`requested_pagination` vs
    `page_only_pagination`); `render` is for the few lists whose rows need
    batch enrichment beyond a read model.
    """
    for column, value in (filters or {}).items():
        if value:
            # A non-UUID value against a UUID column is a caller error, not an
            # empty result — postgres refuses the cast and the refusal used to
            # surface as a 500 (a live E2E audit: ?employee_id=gujianguo). Named 422s
            # also answer the agent's actual confusion: these filters take
            # ids, not the natural names skills carry in conversation.
            if isinstance(column.type, Uuid):
                try:
                    uuid_module.UUID(str(value))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"{column.key} must be a UUID, got {str(value)[:80]!r}",
                    )
            stmt = stmt.where(column == value)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(*(column.ilike(pattern) for column in keyword_columns)))
    if render is None:
        def render(rows):
            return [read_model.model_validate(row).model_dump(by_alias=by_alias) for row in rows]
    ordered = stmt.order_by(*order_by)
    if pagination is None:
        data = render(db.scalars(ordered).all())
        return envelope(data, len(data))
    page, size = pagination
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    data = render(db.scalars(ordered.offset((page - 1) * size).limit(size)).all())
    return paginated_envelope(data, total=total, page=page, page_size=size)


# ---------------------------------------------------------------------------
# The shared document core, moved out of routes.py.
#
# These are the helpers three or more domains call: fetch-and-404, the
# archive/delete/restore/submit verbs, the family registries they read. They
# lived in a 13,008-line module beside the 264 endpoints that use them, so
# every domain extraction would have had to import back into routes.py and
# the dependency graph would have knotted on the second one.
#
# Nothing here calls an endpoint, which is what makes the direction one-way:
# domain modules and routes.py import from common, common imports from
# neither.
# ---------------------------------------------------------------------------

def require_master_data_manage(actor: Actor) -> None:
    """Guard tenant master-data writes.

    ``users.manage`` remains an accepted legacy grant so existing tenant
    administrator roles keep working when this more focused capability ships.
    Service credentials continue to pass through ``has_permission``'s normal
    service-actor bypass.
    """
    if not (
        has_permission(actor, "master_data.manage")
        or has_permission(actor, "users.manage")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires capability master_data.manage",
        )


def get_scoped_or_404(
    db: Session,
    model,
    tenant_id: str,
    entity_id: str,
):
    # A path segment that is not a UUID cannot be a row — postgres would
    # refuse the cast and that refusal used to surface as a 500 (a live E2E
    # audit: /employees/principals falling into /employees/{id}). Not-a-valid-id and
    # no-such-id are the same answer to the caller: 404.
    try:
        uuid.UUID(str(entity_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    instance = db.get(model, entity_id)
    if instance is None or instance.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return instance


@dataclass(frozen=True)
class DocumentFamily:
    """Everything the shared plumbing needs to know about one document
    family. The families behave identically by design — same soft delete,
    same machine-gated line editing, same number allocation — so the
    differences live here as data, not as six copies of the same function."""

    object_type: str            # builtin machine key
    items_phrase: str           # subject of the editable 409
    parent_noun: str            # how the 409 names the parent
    permission: str             # the capability that files this family
    read_model: type
    audit_prefix: str           # "quotation" in quotation.submitted / .status_changed
    audit_identity: object      # doc -> the identifying keys every audit carries
    state_noun: str             # how the create-time 422 names the machine
    advance_permission: str | None = None   # None = filing capability covers advancement
    # doc -> the scope its filing capability is checked with, for families whose
    # verb is scopable (invoice.manage:sales). Without it the shared helpers
    # would check the bare verb and refuse an 应收会计 holding only :sales.
    permission_scope: object | None = None
    owner_checked: bool = True  # personal documents enforce the member-own limit
    attributed_delete: bool = True          # deleted_by / delete_reason columns exist
    editable_hint: str = ""     # family-specific tail of the 409
    number_prefix: str | None = None
    number_field: str | None = None
    lock_scope: str | None = None


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


def may_read_payroll(actor: Actor) -> bool:
    """Salaries and payslips are the one thing here that belonging to the
    workspace does not entitle you to read.

    Every other read in this API is tenant-scoped only, which is fine for
    business documents and unacceptable for pay. Writing payroll implies reading
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


def require_machine_state(db: Session, tenant_id: str, model, status_value: str | None) -> str:
    """Create-time gate, returning the state the document starts in.

    A new document may start in ANY state of the tenant's machine (history
    imports arrive mid-flow), but never outside it. `None` — the schema
    default — means the machine's own `initial`: state names are the tenant's
    vocabulary, so the server cannot write `"draft"` into the contract and
    survive a workspace that calls that state something else."""
    family = DOCUMENT_FAMILIES[model]
    machine = get_builtin_machine(db, tenant_id, family.object_type)
    if status_value is None:
        return machine["initial"]
    if status_value not in set(machine.get("states", ())):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status {status_value!r} is not a state of the tenant's {family.state_noun} state machine",
        )
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
        if getattr(row, field_name, None) != expected:
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
    machine = get_builtin_machine(db, document.tenant_id, family.object_type)
    validate_transition(machine, document.status, new_status, subject=family.object_type)
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
        editable=editable_states(machine, family.object_type),
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
    machine = get_builtin_machine(db, actor.tenant_id, family.object_type)
    # "submitted" is a ROLE — the tenant may call the state itself something
    # else, and /submit lands wherever their machine says the role lives
    submitted = state_for_role(machine, family.object_type, "submitted")
    if document.status == submitted:
        # idempotent resubmit
        return envelope(_document_read(family, document))
    validate_transition(machine, document.status, submitted, subject=family.object_type)
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
    machine = get_builtin_machine(db, document.tenant_id, family.object_type)
    editable = editable_states(machine, family.object_type)
    if document.status not in editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{family.items_phrase} can only be changed while the "
                f"{family.parent_noun} is in {sorted(editable)}{family.editable_hint}"
            ),
        )


def allocate_number(db: Session, model, tenant_id: str) -> str:
    family = DOCUMENT_FAMILIES[model]
    return allocate_document_number(
        db, tenant_id,
        model=model, number_column=getattr(model, family.number_field),
        prefix=family.number_prefix, lock_scope=family.lock_scope, field=family.number_field,
    )


def get_live_or_404(db: Session, model, tenant_id: str, row_id: str):
    """Scoped fetch that treats a soft-deleted row as absent."""
    row = get_scoped_or_404(db, model, tenant_id, row_id)
    if row.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return row


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


ITEM_FAMILIES: dict[type, ItemFamily] = {
    SalesQuotationItem: ItemFamily(
        SalesQuotation, "quotation_id", "quotation.submit_own", True, SalesQuotationItemRead,
        ("line_no", "tax_rate", "is_gift", "lead_time"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
    ),
    SalesOrderItem: ItemFamily(
        SalesOrder, "order_id", "order.submit_own", True, SalesOrderItemRead,
        ("line_no", "tax_rate", "is_gift", "promised_date"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
    ),
    PurchaseOrderItem: ItemFamily(
        PurchaseOrder, "po_id", "purchase_order.manage", False, PurchaseOrderItemRead,
        ("line_no", "tax_rate", "promised_date"),
        link_field="purchase_request_item_id", link_validator=_purchase_request_item_for_po_link,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.asc(), m.id.asc()),
    ),
    PurchaseRequestItem: ItemFamily(
        PurchaseRequest, "request_id", "purchase.submit_own", True, PurchaseRequestItemRead,
        (),
        link_field="sales_order_item_id", link_validator=_sales_order_item_for_link,
        list_order=lambda m: (m.created_at.desc(),),
    ),
}


def _item_read(family: ItemFamily, item) -> dict:
    return family.read_model.model_validate(item).model_dump(by_alias=True)


def _item_write_gate(db: Session, actor: Actor, family: ItemFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_items(db: Session, tenant_id: str, model, filters: dict[str, str | None]) -> dict:
    """One list shape for every line family: live lines of live documents,
    equality filters, the family's own ordering."""
    family = ITEM_FAMILIES[model]
    stmt = (
        select(model)
        .join(family.parent_model, getattr(model, family.parent_field) == family.parent_model.id)
        .where(
            model.tenant_id == tenant_id,
            model.deleted_at.is_(None),
            family.parent_model.deleted_at.is_(None),
        )
    )
    return list_rows(
        db, stmt,
        filters={getattr(model, column): value for column, value in filters.items()},
        order_by=family.list_order(model),
        pagination=None,
        render=lambda rows: [_item_read(family, row) for row in rows],
    )


def build_item(db: Session, actor: Actor, model, payload, *, parent=None):
    """One validated line, standalone or inline — the single set of rules for
    both paths; the inline path exists to save turns, not to skip checks.

    `parent` passed = the line rides the document's own create: identity comes
    from the parent, and the editable-state gate does not apply — the person is
    stating the document as a whole, including record-won documents created
    directly in a later state."""
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    if parent is None:
        parent_id = getattr(payload, family.parent_field)
        _item_write_gate(db, actor, family, parent_id)
    else:
        named = getattr(payload, family.parent_field)
        if named and named != parent.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "inline items belong to the document being created; "
                    f"do not name another {family.parent_field}"
                ),
            )
        parent_id = parent.id
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    link_id = getattr(payload, family.link_field) if family.link_field else None
    if link_id:
        family.link_validator(db, tenant_id, link_id)
    product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
        db, tenant_id, payload.product_id, payload.sku_id, payload.product_name_snapshot, payload.unit
    )
    if product_id is None and not product_name_snapshot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="an item needs a product_id (or sku_id) or a free-text product_name_snapshot",
        )
    values = {field: getattr(payload, field) for field in family.extra_fields}
    if family.link_field:
        values[family.link_field] = link_id
    if family.capture_list_price:
        list_price_snapshot = payload.list_price_snapshot
        if list_price_snapshot is None and (product_id or sku_id):
            # capture the catalog truth at writing time; an explicit payload
            # value (e.g. a customer-tier price list) wins
            list_price_snapshot = catalog_list_price(db, tenant_id, product_id, sku_id)
        values["list_price_snapshot"] = list_price_snapshot
    item = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent_id},
        product_id=product_id,
        sku_id=sku_id,
        product_name_snapshot=product_name_snapshot,
        spec=payload.spec,
        quantity=payload.quantity,
        unit=unit,
        unit_price=payload.unit_price,
        amount=payload.amount,
        attachment_id=payload.attachment_id,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
        **values,
    )
    db.add(item)
    db.flush()
    return item


def record_line_audit(
    db: Session,
    actor: Actor,
    parent_model,
    parent_id: str,
    line_id: str,
    verb: str,
    *,
    changed: dict | None = None,
) -> None:
    """Audit a line change against the DOCUMENT it belongs to, not the line.

    An approval is a signature on content, and the trail is what anchors the
    two together. Before this, a document's audit carried its status
    transitions and nothing about the lines — so a timesheet could be approved
    twice, have six entries moved to another project, and be resubmitted, with
    the audit showing three status rows and no trace of the edit at all. That
    is HKG-015, found in production by reading `updated_at`, which is the only
    reason it was reconstructable.

    Written against the parent's id on purpose: an approver, or whoever asks
    later what happened to a document, reads ONE trail. Auditing under the
    line's own id would mean already knowing which lines to ask about, which is
    exactly what the investigation does not know.

    `changed` names the fields, not their values: the audit is a trail, not a
    second copy of the record, and a payslip line's numbers do not belong in a
    log that a wider audience can read than the document itself.
    """
    family = DOCUMENT_FAMILIES.get(parent_model)
    if family is None:                      # a line family whose parent is not a document
        return
    parent = db.get(parent_model, parent_id)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=f"{family.audit_prefix}.{verb}",
        entity_type=family.object_type,
        entity_id=parent_id,
        actor=actor.label,
        detail={
            **(family.audit_identity(parent) if parent is not None else {}),
            "line_id": line_id,
            **({"fields": sorted(changed)} if changed else {}),
        },
    )


def create_item(db: Session, actor: Actor, model, payload) -> dict:
    item = build_item(db, actor, model, payload)
    family = ITEM_FAMILIES[model]
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_added",
    )
    # a new line grows a charged parent's occupation; the guard re-runs here
    # (and only here — deleting a line shrinks, which needs no permission)
    parent = db.get(family.parent_model, getattr(item, family.parent_field))
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(item)
    return envelope(_item_read(family, item))


def get_item(db: Session, tenant_id: str, model, item_id: str) -> dict:
    family = ITEM_FAMILIES[model]
    item = require_live_line(db, tenant_id, model, family.parent_model, family.parent_field, item_id)
    return envelope(_item_read(family, item))


def update_item(db: Session, actor: Actor, model, item_id: str, payload) -> dict:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_live_or_404(db, model, tenant_id, item_id)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    updates = payload.model_dump(exclude_unset=True)
    if "attachment_id" in updates and updates["attachment_id"]:
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if family.link_field and updates.get(family.link_field):
        family.link_validator(db, tenant_id, updates[family.link_field])
    if "product_id" in updates or "sku_id" in updates or "product_name_snapshot" in updates or "unit" in updates:
        # changing the product without naming a sku drops the old sku — a
        # stale variant must never survive a product swap
        product_unchanged = updates.get("product_id", item.product_id) == item.product_id
        sku_default = item.sku_id if product_unchanged else None
        product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
            db,
            tenant_id,
            updates.get("product_id", item.product_id),
            updates.get("sku_id", sku_default),
            updates.get("product_name_snapshot", item.product_name_snapshot),
            updates.get("unit", item.unit),
        )
        refs_changed = (product_id, sku_id) != (item.product_id, item.sku_id)
        item.product_id = product_id
        item.sku_id = sku_id
        item.product_name_snapshot = product_name_snapshot
        item.unit = unit
        if family.capture_list_price and refs_changed and "list_price_snapshot" not in updates:
            # the snapshot follows the new reference (None when uncataloged);
            # an old product's price must never survive a product swap
            item.list_price_snapshot = catalog_list_price(db, tenant_id, product_id, sku_id)
        updates.pop("product_id", None)
        updates.pop("sku_id", None)
        updates.pop("product_name_snapshot", None)
        updates.pop("unit", None)
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    # Every field the caller sent, including the product/sku block popped above
    # — `payload` is the record of what was asked for, `updates` is what is left
    # after this function has consumed parts of it.
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    parent = db.get(family.parent_model, getattr(item, family.parent_field))
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(item)
    return envelope(_item_read(family, item))


def delete_item(db: Session, actor: Actor, model, item_id: str) -> Response:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_scoped_or_404(db, model, tenant_id, item_id)
    if item.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    item.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def archive_row(
    db: Session,
    actor: Actor,
    model,
    row_id: str,
    *,
    permission: str | None = None,
    audit_action: str | None = None,
    audit_entity_type: str | None = None,
    audit_detail=None,
) -> Response:
    """Master data archives, never deletes: existing records keep whatever
    they already reference — archiving only removes the row from what NEW
    records may use, and the history beneath it stays readable.

    `audit_action` is opt-in per family rather than always-on: most families
    here have never written an audit entry for an archive, and turning that on
    for all of them at once is a separate decision from fixing the one family
    whose vocabulary changes silently reinterpret existing records."""
    if permission:
        require_permission(actor, permission)
    else:
        require_master_data_manage(actor)
    row = get_scoped_or_404(db, model, actor.tenant_id, row_id)
    row.status = "archived"
    if audit_action:
        # Stated, not singularized off the table name: `rstrip("s")` is right
        # for `type_options` and wrong the first time a table is not spelled
        # that way, and a wrong entity_type in an audit trail is worse than a
        # missing one — it is a record filed under something that never
        # happened.
        assert audit_entity_type, "audit_action needs audit_entity_type"
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action=audit_action,
            entity_type=audit_entity_type,
            entity_id=row.id,
            actor=actor.label,
            detail=audit_detail(row) if callable(audit_detail) else audit_detail,
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def exclude_rows_with_open_todo(stmt, model, tenant_id: str, entity_type: str):
    """NOT-EXISTS filter for work queues: rows someone already has an open
    todo to act on are hidden, leaving what still needs an assignment
    (e.g. status=submitted&without_open_todo=true)."""
    return stmt.where(
        ~select(Todo.id)
        .where(
            Todo.tenant_id == tenant_id,
            Todo.entity_type == entity_type,
            Todo.entity_id == model.id,
            Todo.status == "open",
        )
        .exists()
    )


def document_approvals(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> list:
    """The approval trail every /detail carries, in workflow order."""
    return db.scalars(
        select(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
        )
        .order_by(ApprovalRecord.round_no.asc(), ApprovalRecord.sequence_no.asc(), ApprovalRecord.acted_at.asc())
    ).all()


def attachments_for_items(db: Session, tenant_id: str, items) -> list:
    attachment_ids = {item.attachment_id for item in items if item.attachment_id}
    if not attachment_ids:
        return []
    return db.scalars(
        select(Attachment).where(Attachment.tenant_id == tenant_id, Attachment.id.in_(attachment_ids))
    ).all()


# --- reaching an attachment's bytes ----------------------------------------
#
# Holding an attachment's id is not authorisation to read it. Attachments are
# standalone blobs by design — `Attachment` carries no back-link, because
# linking is the referencing object's job — and `GET /attachments/{id}/content`
# honoured that literally: tenant scope and nothing else. A credential with no
# payroll capability could read a payslip's PDF, which is the one read
# `tests/test_payroll_visibility.py` opens by calling "the first read in this
# API that belonging to the workspace does not entitle you to".
#
# So the bytes are reached THROUGH the document that carries them. The document
# already knows who may see it — `ensure_invoice_visible`, `ensure_policy_visible`
# and the rest were written for exactly that question — and the caller has to
# name it, which makes the authorisation explicit at every call site instead of
# implicit in an id nobody can trace.
#
# `attachment_id` on the model that actually holds it: header for the three
# single-document families, line items for the five with lines.
ATTACHMENT_SOURCES: dict[type, tuple[type | None, str | None]] = {}


def register_attachment_source(document_model: type, item_model=None, parent_field: str | None = None) -> None:
    """Where this family keeps the attachment ids reachable from one document.

    Declared by each family's own module, so a new family that forgets to
    register is a family whose attachments are unreachable — visibly, on the
    first read — rather than one whose attachments are reachable by anyone.
    """
    ATTACHMENT_SOURCES[document_model] = (item_model, parent_field)


def document_attachment_ids(db: Session, tenant_id: str, document) -> set[str]:
    """Every attachment this one document carries, header and lines."""
    item_model, parent_field = ATTACHMENT_SOURCES[type(document)]
    if item_model is None:
        return {document.attachment_id} - {None}
    rows = db.scalars(
        select(item_model.attachment_id).where(
            item_model.tenant_id == tenant_id,
            getattr(item_model, parent_field) == document.id,
            item_model.attachment_id.is_not(None),
        )
    ).all()
    return set(rows)


def serve_document_attachment(db: Session, tenant_id: str, document, attachment_id: str) -> Response:
    """The bytes, once the caller has proved they may read the document.

    Callers MUST apply the family's own visibility check before calling this —
    it verifies only that the attachment belongs to the document named, which
    is the other half. 404 for an attachment the document does not carry: an
    id that is real but unrelated must not read differently from one that is
    not real, or the endpoint becomes an oracle for what exists.
    """
    if attachment_id not in document_attachment_ids(db, tenant_id, document):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    attachment = get_scoped_or_404(db, Attachment, tenant_id, attachment_id)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}"},
    )


def load_item_catalog_context(db: Session, tenant_id: str, items) -> tuple[dict, dict, set]:
    """(skus_by_id, products_by_id, products_with_skus) for a set of lines —
    the three maps every /detail needs to label its lines, in three reads
    regardless of how many lines the document has."""
    sku_ids = {item.sku_id for item in items if item.sku_id}
    skus = (
        db.scalars(
            select(ProductSku).where(ProductSku.tenant_id == tenant_id, ProductSku.id.in_(sku_ids))
        ).all()
        if sku_ids
        else []
    )
    skus_by_id = {sku.id: sku for sku in skus}
    item_product_ids = {item.product_id for item in items if item.product_id}
    products_with_skus = (
        set(
            db.scalars(
                select(ProductSku.product_id)
                .where(
                    ProductSku.tenant_id == tenant_id,
                    ProductSku.product_id.in_(item_product_ids),
                    ProductSku.status == "active",
                )
                .group_by(ProductSku.product_id)
            ).all()
        )
        if item_product_ids
        else set()
    )
    product_ids = set(item_product_ids)
    product_ids.update(sku.product_id for sku in skus)
    products = (
        db.scalars(
            select(Product).where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
        ).all()
        if product_ids
        else []
    )
    return skus_by_id, {product.id: product for product in products}, products_with_skus


def resolve_item_refs(item, skus_by_id: dict, products_by_id: dict) -> tuple:
    """(product, sku) for one line, from the catalog context maps."""
    sku = skus_by_id.get(item.sku_id) if item.sku_id else None
    if sku is not None and item.product_id is not None and sku.product_id != item.product_id:
        # Defensive against historic/corrupt cross-product references: do
        # not attach a misleading label even though writes now prevent it.
        sku = None
    product_id = item.product_id or (sku.product_id if sku is not None else None)
    return (products_by_id.get(product_id) if product_id else None), sku


def sku_pending_flag(item, products_with_skus: set) -> bool:
    """A variant product quoted/ordered at product level: the SKU decision
    is still open — surfaced so reviewers see 尺码待定 at a glance."""
    return bool(item.product_id and not item.sku_id and item.product_id in products_with_skus)


def normalize_product_context(
    db: Session,
    tenant_id: str,
    product_id: str | None,
    sku_id: str | None,
    product_name_snapshot: str | None,
    unit: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Same contract as `claims.py`'s normalize_project_context: real records
    (404 otherwise) and backfill the free-text name/unit snapshots; without
    them, the free text stands alone. A sku alone derives its product; a sku
    given with a mismatching product is a 400 — the pair must agree."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if product_id and product_id != sku.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to the given product_id",
            )
        product_id = sku.product_id
    if not product_id:
        return None, None, product_name_snapshot, unit
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return product.id, sku_id, product_name_snapshot or product.name, unit or product.unit


def catalog_list_price(db: Session, tenant_id: str, product_id: str | None, sku_id: str | None) -> float | None:
    """The catalog reference price for a line: sku price overrides product
    price; None when the catalog is silent. Captured onto the line as
    list_price_snapshot so the discount stays derivable after catalog edits."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if sku.list_price is not None:
            return float(sku.list_price)
        product = get_scoped_or_404(db, Product, tenant_id, sku.product_id)
        return float(product.list_price) if product.list_price is not None else None
    if product_id:
        product = get_scoped_or_404(db, Product, tenant_id, product_id)
        return float(product.list_price) if product.list_price is not None else None
    return None


def doc_number_lock_key(scope: str, tenant_id: str) -> int:
    digest = hashlib.sha256()
    for value in (scope, tenant_id):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)


def allocate_document_number(
    db: Session, tenant_id: str, *, model, number_column, prefix: str, lock_scope: str, field: str
) -> str:
    """Next {prefix}NNNNNN for the tenant. Serialized with a transaction-scoped
    advisory lock on PostgreSQL (same idiom as workflow version allocation);
    SQLite (unit tests) has no equivalent and is single-writer anyway.
    Numbers are never reused — soft-deleted documents keep theirs, and the
    unique constraint stays the backstop for agent-supplied numbers."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("select pg_advisory_xact_lock(cast(:lock_key as bigint))"),
            {"lock_key": doc_number_lock_key(lock_scope, tenant_id)},
        )
    latest = db.scalar(
        select(func.max(number_column)).where(
            model.tenant_id == tenant_id,
            # fixed-width suffix: lexicographic max == numeric max
            number_column.like(prefix + "______"),
        )
    )
    try:
        seq = int(latest[len(prefix):]) + 1 if latest else 1
    except ValueError:
        # a tenant-supplied number happens to match the width pattern —
        # restart low and let the existence probe walk past collisions
        seq = 1
    for _ in range(100):
        candidate = f"{prefix}{seq:06d}"
        exists = db.scalar(
            select(model.id)
            .where(model.tenant_id == tenant_id, number_column == candidate)
            .limit(1)
        )
        if exists is None:
            return candidate
        seq += 1
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"unable to allocate a number; supply {field} explicitly",
    )


def ensure_content_edit_allowed(actor: Actor, family: str, updates: dict) -> None:
    """A document's own fields are the submitter's write; only `status` is the
    flow's.

    Status is guarded where it is applied, by the family's `advance` verb. The
    rest of the header is what a person reported — their hours, their narrative,
    their claim — so changing it takes the same capability that filed it. This
    changes nothing for the tenant's own credentials: a member editing their own
    header holds `submit_own` and has already passed the own-employee check, and
    admins and tenant service keys hold or bypass everything. It draws the line
    for a principal that may advance a flow while being nobody in the company —
    ORYH's hosted agent can move a timesheet to `approved`, and cannot touch a
    word of what the employee wrote."""
    if any(field != "status" for field in updates):
        require_permission(actor, f"{family}.submit_own")


MASTER_CODE_FIELDS = {
    Project: ("project_code", "project"),
    Vendor: ("vendor_code", "vendor"),
    Customer: ("customer_code", "customer"),
    Product: ("product_code", "product"),
}


def commit_or_code_conflict(db: Session, row) -> None:
    """Commit a master-data write; a duplicate code becomes a 409 that names
    the holder instead of a 500.

    A live E2E run hit this with a project: the unique index has enforced
    per-tenant codes on postgres since the baseline migration, but no create
    or update here caught IntegrityError, so re-using an ARCHIVED project's
    code surfaced as Internal Server Error. The holder's status matters in
    the message for exactly that reason — the person cannot see an archived
    twin in their default list view, so "already exists" alone reads as a
    lie.
    """
    model = type(row)
    code_field, noun = MASTER_CODE_FIELDS[model]
    code_value = getattr(row, code_field)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not code_value:
            raise
        holder = db.scalar(
            select(model).where(
                model.tenant_id == row.tenant_id,
                getattr(model, code_field) == code_value,
            )
        )
        if holder is None:
            raise
        detail = f"{code_field} {code_value!r} already belongs to {noun} {holder.id}"
        status_value = getattr(holder, "status", None)
        if status_value and status_value != "active":
            detail += (
                f" (status: {status_value} — it keeps its code; "
                "restore it or pick another code)"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _finish_bulk_import(db: Session, actor: Actor, result: dict, *, action: str, detail: dict) -> dict:
    """Rollback-or-audit-and-commit tail shared by every bulk import. The
    audit records the import as ONE event with its counts, not one entry per
    row — 500 near-identical rows would bury the trail. An import spans many
    rows, so there is no single entity to anchor to (and `entity_id` is a
    uuid column): it anchors to the tenant whose data changed.
    """
    if not result["applied"]:
        db.rollback()
        return envelope(result)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=action,
        entity_type="tenant",
        entity_id=actor.tenant_id,
        actor=actor.label,
        detail={**detail, **result["summary"]},
    )
    db.commit()
    return envelope(result)


def _run_document_import(*, db: Session, actor: Actor, family: str, payload) -> dict:
    """Shared tail for the historical-document imports. Gated on the family's
    own submit capability — importing history is still writing that family's
    documents — and audited as ONE event with its counts, like master data."""
    spec = document_import.FAMILIES[family]
    if family == "purchase_order":
        # Purchase orders are a FUNCTION, not "my documents" — the same single
        # capability that files one PO files a thousand historical ones, and
        # the own-employee limit never applied to this family to begin with.
        require_permission(actor, "purchase_order.manage")
        machine = get_builtin_machine(db, actor.tenant_id, "purchase_order")
    elif family == "invoice":
        # Invoicing is a function too, but scopable: a 期初 file usually carries
        # both directions, so the import needs the capability for both rather
        # than one side of it.
        for direction in ("sales", "purchase"):
            if any(row.direction == direction for row in payload.rows):
                require_permission(actor, "invoice.manage", direction)
        machine = get_builtin_machine(db, actor.tenant_id, "invoice")
    elif family == "payment":
        require_permission(actor, "payment.record")
        machine = get_builtin_machine(db, actor.tenant_id, "payment")
    else:
        require_permission(actor, "quotation.submit_own" if family == "quotation" else "order.submit_own")
        # A migration writes documents belonging to MANY salespeople, which the
        # single-document endpoints forbid via enforce_member_employee. Rather
        # than checking row by row — every historical document names someone
        # else — the endpoint requires the capability that lifts the own-employee
        # limit outright, so a plain member key cannot backfill history under a
        # colleague's name.
        if actor.kind == "user" and not has_permission(actor, "tenant.act_for_any_employee"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "importing historical documents writes records for other employees — "
                    "requires capability tenant.act_for_any_employee"
                ),
            )
        machine = (
            get_builtin_machine(db, actor.tenant_id, "sales_quotation")
            if family == "quotation"
            else get_builtin_machine(db, actor.tenant_id, "sales_order")
        )
    result = document_import.bulk_import_documents(
        db,
        tenant_id=actor.tenant_id,
        family=family,
        rows=payload.rows,
        machine_states=set(machine.get("states", ())),
        initial_state=machine["initial"],
        dry_run=payload.dry_run,
        on_error=payload.on_error,
        on_missing_reference=payload.on_missing_reference,
    )
    return _finish_bulk_import(
        db, actor, result,
        action=f"{spec['label']}.imported",
        detail={"on_error": payload.on_error, "on_missing_reference": payload.on_missing_reference},
    )


@dataclass(frozen=True)
class AdjustmentFamily:
    """The three adjustment families (quotation / sales order / purchase
    order) behave identically by construction — same fields, same vocabulary,
    same editable-state gate. What differs is data: the models, the two FK
    names, the capability, and whether the parent has an owner to enforce."""

    parent_model: type
    item_model: type
    parent_field: str
    item_field: str
    permission: str
    owner_checked: bool
    read_model: type


ADJUSTMENT_FAMILIES: dict[type, AdjustmentFamily] = {
    SalesQuotationAdjustment: AdjustmentFamily(
        SalesQuotation, SalesQuotationItem, "quotation_id", "quotation_item_id",
        "quotation.submit_own", True, SalesQuotationAdjustmentRead,
    ),
    SalesOrderAdjustment: AdjustmentFamily(
        SalesOrder, SalesOrderItem, "order_id", "order_item_id",
        "order.submit_own", True, SalesOrderAdjustmentRead,
    ),
    PurchaseOrderAdjustment: AdjustmentFamily(
        PurchaseOrder, PurchaseOrderItem, "po_id", "po_item_id",
        # procurement is a function, not "my documents": one capability, no owner
        "purchase_order.manage", False, PurchaseOrderAdjustmentRead,
    ),
}


def _adjustment_read(family: AdjustmentFamily, adjustment) -> dict:
    return family.read_model.model_validate(adjustment).model_dump(by_alias=True)


def _adjustment_write_gate(db: Session, actor: Actor, family: AdjustmentFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_adjustments(
    db: Session, tenant_id: str, model, *,
    parent_id: str | None, item_id: str | None, adjustment_type: str | None,
) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    stmt = select(model).where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            getattr(model, family.parent_field): parent_id,
            getattr(model, family.item_field): item_id,
            model.adjustment_type: adjustment_type,
        },
        order_by=(model.created_at.asc(), model.id.asc()),
        pagination=None,
        render=lambda rows: [_adjustment_read(family, row) for row in rows],
    )


def create_adjustment(db: Session, actor: Actor, model, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    # ONE vocabulary for all three families: an adjustment type is not a
    # direction-specific idea
    require_type_option(db, tenant_id, "sales_adjustment_type", payload.adjustment_type)
    parent_id = getattr(payload, family.parent_field)
    _adjustment_write_gate(db, actor, family, parent_id)
    item_id = getattr(payload, family.item_field)
    if item_id:
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent_id, item_id,
        )
    adjustment = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent_id, family.item_field: item_id},
        adjustment_type=payload.adjustment_type,
        description=payload.description,
        amount=payload.amount,
        source_percentage=payload.source_percentage,
        metadata_jsonb=payload.metadata,
    )
    db.add(adjustment)
    db.flush()
    record_line_audit(
        db, actor, family.parent_model, parent_id, adjustment.id, "adjustment_added",
    )
    parent = db.get(family.parent_model, parent_id)
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def get_adjustment(db: Session, tenant_id: str, model, adjustment_id: str) -> dict:
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    return envelope(_adjustment_read(ADJUSTMENT_FAMILIES[model], adjustment))


def update_adjustment(db: Session, actor: Actor, model, adjustment_id: str, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    parent_id = getattr(adjustment, family.parent_field)
    _adjustment_write_gate(db, actor, family, parent_id)
    updates = payload.model_dump(exclude_unset=True)
    if "adjustment_type" in updates:
        require_type_option(db, tenant_id, "sales_adjustment_type", updates["adjustment_type"])
    if updates.get(family.item_field):
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent_id, updates[family.item_field],
        )
    if "metadata" in updates:
        adjustment.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(adjustment, field, value)
    record_line_audit(
        db, actor, family.parent_model, parent_id, adjustment.id, "adjustment_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    parent = db.get(family.parent_model, parent_id)
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def delete_adjustment(db: Session, actor: Actor, model, adjustment_id: str) -> Response:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_scoped_or_404(db, model, tenant_id, adjustment_id)
    if adjustment.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _adjustment_write_gate(db, actor, family, getattr(adjustment, family.parent_field))
    adjustment.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, family.parent_model, getattr(adjustment, family.parent_field),
        adjustment.id, "adjustment_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- billing-account charging: who carries a document, and what it occupies --
#
# A document charged to an account (`billing_account_id`) says WHO CARRIES the
# obligation, never that it is paid. Settlement stays exclusively the
# payment-applications ledger; the account's own ledger stays exclusively real
# money. What charging changes is one derived number:
#
#     available = balance + credit_limit - exposure
#
# where exposure is the sum of what charged documents still stand to draw: a
# charged ORDER occupies its live total minus what same-account invoices have
# already billed of it (so occupation TRANSFERS to the invoice at billing time
# rather than doubling), and a charged INVOICE occupies its unsettled
# outstanding. Nothing is stored — applied_amount and the ledger balance are
# already materialized, and a fourth running sum would have two directions to
# drift in.
#
# The occupation begins when the document is charged and ends when it is
# settled, uncharged, or deleted — never when a status changes. Status names
# are the tenant's vocabulary; `cancelled` and `completed` are both terminal
# states and mean opposite things for credit, so the release on cancellation
# is the AGENT's explicit write (clear the field), with the reads and the
# integrity audit making a forgotten one visible.
#
# Why this window matters: between order and invoice — an e-commerce wait, a
# walk-in customer's 缺货 two-day gap, a toB delivery months out — the same
# balance must not be spendable twice. That is the double-spend charging
# exists to refuse.

def effective_line_amount(item) -> float:
    """A line's value the way `document_total` reads it: explicit amount wins,
    then unit price × quantity; a gift is 0 by definition; an unpriced line
    contributes 0 — occupation is computed from what is priced, the same
    honesty `estimated_total` keeps."""
    if getattr(item, "amount", None) is not None:
        return float(item.amount)
    if getattr(item, "unit_price", None) is not None:
        return float(item.unit_price) * float(item.quantity or 0)
    if getattr(item, "is_gift", False):
        return 0.0
    return 0.0


def _live_sum(db: Session, model, parent_field: str, parent_id: str, *, lines: bool) -> float:
    rows = db.scalars(
        select(model).where(
            getattr(model, parent_field) == parent_id,
            model.deleted_at.is_(None),
        )
    ).all()
    if lines:
        return sum(effective_line_amount(row) for row in rows)
    return sum(float(row.amount or 0) for row in rows)


def invoice_billed_amount(db: Session, invoice: Invoice) -> float:
    """What this invoice bills: the declared total, else the live line sum —
    the same coalesce the settlement ceiling and the integrity audit use."""
    if invoice.total_amount is not None:
        return float(invoice.total_amount)
    return _live_sum(db, InvoiceItem, "invoice_id", invoice.id, lines=True)


_CHARGEABLE_ORDERS = {
    SalesOrder: SimpleNamespace(
        item_model=SalesOrderItem, item_field="order_id",
        adjustment_model=SalesOrderAdjustment, adjustment_field="order_id",
        invoice_link="sales_order_id", owner_field="customer_id", label="sales order",
    ),
    PurchaseOrder: SimpleNamespace(
        item_model=PurchaseOrderItem, item_field="po_id",
        adjustment_model=PurchaseOrderAdjustment, adjustment_field="po_id",
        invoice_link="purchase_order_id", owner_field="vendor_id", label="purchase order",
    ),
}


def order_live_total(db: Session, order) -> float:
    """The order's agreed total, else live lines plus live adjustments — the
    same contract `document_total` states: null means the line math IS it."""
    if order.total_amount is not None:
        return float(order.total_amount)
    spec = _CHARGEABLE_ORDERS[type(order)]
    return (
        _live_sum(db, spec.item_model, spec.item_field, order.id, lines=True)
        + _live_sum(db, spec.adjustment_model, spec.adjustment_field, order.id, lines=False)
    )


def order_billed_on_account(db: Session, order, account_id: str) -> float:
    """What invoices carrying the SAME account have already billed of this
    order. Only same-account invoices release the order's occupation: an
    invoice issued without the account would otherwise silently release credit
    nothing else guards — refusing too little is a leak, refusing too much is
    a re-read."""
    spec = _CHARGEABLE_ORDERS[type(order)]
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == order.tenant_id,
            getattr(Invoice, spec.invoice_link) == order.id,
            Invoice.billing_account_id == account_id,
            Invoice.deleted_at.is_(None),
        )
    ).all()
    return sum(invoice_billed_amount(db, invoice) for invoice in invoices)


def account_exposure(db: Session, account: BillingAccount) -> float:
    """Everything charged to this account still stands to draw from it."""
    exposure = 0.0
    for order_model in _CHARGEABLE_ORDERS:
        for order in db.scalars(
            select(order_model).where(
                order_model.tenant_id == account.tenant_id,
                order_model.billing_account_id == account.id,
                order_model.deleted_at.is_(None),
            )
        ):
            remainder = order_live_total(db, order) - order_billed_on_account(db, order, account.id)
            exposure += max(remainder, 0.0)
    for invoice in db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == account.tenant_id,
            Invoice.billing_account_id == account.id,
            Invoice.deleted_at.is_(None),
        )
    ):
        outstanding = invoice_billed_amount(db, invoice) - float(invoice.applied_amount or 0)
        exposure += max(outstanding, 0.0)
    return round(exposure, 2)


def account_position(db: Session, account: BillingAccount) -> tuple[float, float, float]:
    """(balance, exposure, available) — the three numbers every charge guard,
    detail read and refusal message speak in."""
    balance = float(account.balance or 0)
    exposure = account_exposure(db, account)
    return balance, exposure, round(balance + float(account.credit_limit or 0) - exposure, 2)


def resolve_chargeable_account(
    db: Session,
    tenant_id: str,
    account_id: str,
    *,
    owner_field: str,
    owner_id: str | None,
    currency: str,
    label: str,
) -> BillingAccount:
    """The account a document may be charged to, LOCKED for the check that
    follows. Row-locked (`FOR UPDATE`) so two agents charging concurrently
    serialize on the account and cannot both pass the same remaining credit —
    the same discipline the SKU parent lock keeps for variant identity."""
    account = db.scalar(
        select(BillingAccount)
        .where(BillingAccount.tenant_id == tenant_id, BillingAccount.id == account_id)
        .with_for_update()
    )
    if account is None or account.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BillingAccount not found")
    if account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"account {account.account_code} is {account.status} and takes no new charges",
        )
    if account.unit_type != "currency":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{account.account_code} counts {account.unit}, not money — a {label} "
                "cannot be charged to a points account"
            ),
        )
    if account.unit != currency:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"currency mismatch: this {label} is in {currency} and account "
                f"{account.account_code} is in {account.unit}"
            ),
        )
    owner = getattr(account, owner_field, None)
    if owner is None or owner_id is None or owner != owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"account {account.account_code} does not belong to this {label}'s "
                "counterparty — a document is charged to its own party's account"
            ),
        )
    return account


def ensure_within_credit(db: Session, account: BillingAccount, *, label: str) -> None:
    """The occupation guard. Call AFTER the charged document is flushed, so the
    exposure it computes already counts the document being charged; a refusal
    raises and the transaction rolls the flush back with it."""
    db.flush()
    balance, exposure, available = account_position(db, account)
    if available < -CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"charging this {label} exceeds the account's credit: balance "
                f"{balance:.2f} + credit limit {float(account.credit_limit or 0):.2f} "
                f"- occupied {exposure:.2f} leaves {available:.2f}. Deposit more, "
                "raise the limit, or shrink the document"
            ),
        )


def recheck_charged_document(db: Session, document, *, label: str) -> None:
    """Re-run the occupation guard after a write that may have GROWN a charged
    document — a new line, a raised amount, a restore. Shrinking needs no
    guard, and a document that carries no account is a no-op."""
    account_id = getattr(document, "billing_account_id", None)
    if not account_id:
        return
    account = db.scalar(
        select(BillingAccount)
        .where(BillingAccount.tenant_id == document.tenant_id, BillingAccount.id == account_id)
        .with_for_update()
    )
    if account is None:
        return
    ensure_within_credit(db, account, label=label)


# --- the last five, promoted so the document families can be split ---------
#
# Step 2a took the helpers three or more domains called. These five are called
# by exactly two — but by two of the four groups routes.py is about to split
# into, which is the same problem one size smaller. A helper two modules need
# has two possible homes: here, or one module importing another. This series
# has spent five commits keeping the second one from happening.
#
#   CENT, ensure_invoice_not_duplicated,
#   ensure_nothing_applied          billing needs them, so do expense claims
#   grouped_linked_lines            purchasing and sales both walk link rows
#   normalize_vendor_context        an expense names a vendor, so does a PR


def ensure_nothing_applied(db: Session, document, *, label: str) -> None:
    """A settled document may not be hidden. The applications against it would
    keep a running total sourced from a row nobody can see, and the ledger would
    point at a document that no longer exists."""
    applied = float(getattr(document, "applied_amount", 0) or 0)
    if abs(applied) > CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{applied:.2f} is applied to this {label} — reverse those "
                "applications before deleting it"
            ),
        )


def grouped_linked_lines(
    db: Session, tenant_id: str, line_model, link_field: str,
    parent_model, parent_field: str, target_ids, build,
) -> dict[str, list]:
    """The reverse side of a cross-document link: for each target line id,
    the live lines pinned to it (with live parents), rendered by `build` —
    two reads for the whole document."""
    grouped: dict[str, list] = {}
    if not target_ids:
        return grouped
    lines = db.scalars(
        select(line_model)
        .where(
            line_model.tenant_id == tenant_id,
            getattr(line_model, link_field).in_(target_ids),
            line_model.deleted_at.is_(None),
        )
        .order_by(line_model.created_at.asc(), line_model.id.asc())
    ).all()
    parent_ids = {getattr(line, parent_field) for line in lines}
    parents_by_id = (
        {
            parent.id: parent
            for parent in db.scalars(
                select(parent_model).where(
                    parent_model.tenant_id == tenant_id, parent_model.id.in_(parent_ids)
                )
            ).all()
        }
        if parent_ids
        else {}
    )
    for line in lines:
        parent = parents_by_id.get(getattr(line, parent_field))
        if parent is None or parent.deleted_at is not None:
            continue
        grouped.setdefault(getattr(line, link_field), []).append(build(line, parent))
    return grouped


def normalize_vendor_context(
    db: Session,
    tenant_id: str,
    vendor_id: str | None,
    merchant: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as `claims.py`'s normalize_project_context: a vendor_id
    must be a real record (404 otherwise) and backfills the free-text merchant
    snapshot; without one, merchant stays whatever the receipt said."""
    if not vendor_id:
        return None, merchant
    vendor = get_scoped_or_404(db, Vendor, tenant_id, vendor_id)
    return vendor.id, merchant or vendor.name


def ensure_invoice_not_duplicated(
    db: Session,
    tenant_id: str,
    invoice_number: str | None,
    exclude_item_id: str | None = None,
    *,
    direction: str = "purchase",
    exclude_invoice_id: str | None = None,
) -> None:
    """The duplicate-booking control: one tax invoice number may only be booked
    once per tenant.

    For 进项 the check spans BOTH places such an invoice can land — an expense
    item and a vendor bill — because the expensive mistake is precisely the one
    a single-table check misses: the same receipt reimbursed to an employee and
    then paid again against the supplier's own invoice. Sales-side numbers are
    ours to issue, so they only have to be unique among our own invoices.

    The agent should catch this in conversation; the server is the hard
    backstop."""
    if not invoice_number:
        return
    if direction == "purchase":
        claimed = (
            select(ExpenseItem)
            .join(ExpenseClaim, ExpenseItem.claim_id == ExpenseClaim.id)
            .where(
                ExpenseItem.tenant_id == tenant_id,
                ExpenseItem.invoice_number == invoice_number,
                ExpenseItem.deleted_at.is_(None),
                ExpenseClaim.deleted_at.is_(None),
            )
        )
        if exclude_item_id:
            claimed = claimed.where(ExpenseItem.id != exclude_item_id)
        existing_item = db.scalars(claimed).first()
        if existing_item is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"invoice {invoice_number!r} is already claimed on expense item "
                    f"{existing_item.id} (claim {existing_item.claim_id})"
                ),
            )
    booked = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.direction == direction,
        Invoice.tax_invoice_number == invoice_number,
        Invoice.deleted_at.is_(None),
    )
    if exclude_invoice_id:
        booked = booked.where(Invoice.id != exclude_invoice_id)
    existing_invoice = db.scalars(booked).first()
    if existing_invoice is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"invoice {invoice_number!r} is already booked on "
                f"{existing_invoice.invoice_no} ({existing_invoice.id})"
            ),
        )


# money comparisons are on values the database stores as numeric(12,2); half a
# cent of slack absorbs float round-tripping without ever admitting a real
# over-application
CENT = 0.005
