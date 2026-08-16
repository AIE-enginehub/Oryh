"""What an employee says the company owes them: money spent, and hours worked.

Split out of `routes.py`: expense claims with their items, and timesheet
headers with their entries.

Two document families, one module, because they are the same act. An employee
submits an assertion about their own work, someone approves it, and it becomes
money owed to them — which is why both funnel through `common.py`'s
`normalize_project_context` for the cost centre, why both are gated by
`enforce_member_employee` on the way in, and why an expense claim turns into an
invoice by the same path a timesheet does.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    apply_status_change,
    attachments_for_items,
    delete_document,
    document_approvals,
    ensure_content_edit_allowed,
    ensure_document_editable,
    ensure_document_not_deleted,
    ensure_invoice_not_duplicated,
    ensure_nothing_applied,
    envelope,
    exclude_rows_with_open_todo,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    normalize_vendor_context,
    record_line_audit,
    requested_pagination,
    require_machine_state,
    restore_document,
    submit_document,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Attachment,
    Employee,
    ExpenseClaim,
    ExpenseItem,
    Project,
    TimesheetEntry,
    TimesheetHeader,
    Vendor,
)
from app.schemas import (
    ApprovalRecordRead,
    AttachmentRead,
    CreateExpenseClaimRequest,
    CreateExpenseItemRequest,
    CreateTimesheetEntryRequest,
    CreateTimesheetHeaderRequest,
    DeleteExpenseClaimRequest,
    DeleteTimesheetHeaderRequest,
    ExpenseClaimDetailEnvelope,
    ExpenseClaimDetailRead,
    ExpenseClaimListEnvelope,
    ExpenseClaimRead,
    ExpenseItemDetailRead,
    ExpenseItemRead,
    RestoreExpenseClaimRequest,
    RestoreTimesheetHeaderRequest,
    SubmitExpenseClaimRequest,
    SubmitTimesheetRequest,
    TimesheetDetailRead,
    TimesheetEntryRead,
    TimesheetHeaderListEnvelope,
    TimesheetHeaderRead,
    UpdateExpenseClaimRequest,
    UpdateExpenseItemRequest,
    UpdateTimesheetEntryRequest,
    UpdateTimesheetHeaderRequest,
)
from app.services.type_options import require_type_option
from app.services.state_machines import validate_status_filter

router = APIRouter()


def validate_header_entry_link(header: TimesheetHeader, employee_id: str, work_date) -> None:
    if header.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_id must match the header")
    if not (header.period_start <= work_date <= header.period_end):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="work_date must be inside the header period")


def normalize_project_context(
    db: Session,
    tenant_id: str,
    project_id: str | None,
    project_name_snapshot: str | None,
) -> tuple[str | None, str | None]:
    if not project_id:
        return None, project_name_snapshot
    project = get_scoped_or_404(db, Project, tenant_id, project_id)
    return project.id, project_name_snapshot or project.project_name


# --- timesheets: hours worked, asserted by the person who worked them --------


@router.get(
    "/timesheet-headers",
    response_model=TimesheetHeaderListEnvelope,
    response_model_exclude_unset=True,
)
def list_timesheet_headers(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "timesheet_header", status_filter)
    stmt = select(TimesheetHeader).where(TimesheetHeader.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(TimesheetHeader.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, TimesheetHeader, tenant_id, "timesheet_header")
    return list_rows(
        db, stmt,
        filters={
            TimesheetHeader.employee_id: employee_id,
            TimesheetHeader.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(TimesheetHeader.id, String),
            cast(TimesheetHeader.employee_id, String),
            cast(TimesheetHeader.period_start, String),
            cast(TimesheetHeader.period_end, String),
            TimesheetHeader.status,
            TimesheetHeader.source_report_text,
        ),
        order_by=(
            TimesheetHeader.period_start.desc(),
            TimesheetHeader.created_at.desc(),
            TimesheetHeader.id.desc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=TimesheetHeaderRead,
    )


@router.post("/timesheet-headers", status_code=status.HTTP_201_CREATED)
def create_timesheet_header(
    payload: CreateTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_machine_state(db, tenant_id, TimesheetHeader, payload.status)
    header = TimesheetHeader(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(header)
    try:
        db.flush()
        # inline rows ride the same transaction: one bad row rolls back the
        # whole document, so a crash or a validation error can no longer
        # leave a half-filled draft behind
        entries = [
            build_timesheet_entry(db, actor, row, header=header) for row in payload.entries
        ]
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(TimesheetHeader).where(
                TimesheetHeader.tenant_id == tenant_id,
                TimesheetHeader.employee_id == payload.employee_id,
                TimesheetHeader.period_start == payload.period_start,
                TimesheetHeader.period_end == payload.period_end,
            )
        )
        if existing is None:
            raise
        period = f"{existing.period_start.isoformat()}..{existing.period_end.isoformat()}"
        if existing.deleted_at is not None:
            # the unique index intentionally covers soft-deleted rows: a deleted
            # header keeps its period slot so /restore can never collide
            detail = (
                f"deleted timesheet header {existing.id} still holds period {period} "
                f"for employee {payload.employee_id}; restore it instead of recreating"
            )
        else:
            detail = (
                f"timesheet header {existing.id} already covers period {period} "
                f"for employee {payload.employee_id}"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    db.refresh(header)
    data = TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True)
    if entries:
        # the response IS the read-back: what landed, row by row
        data["entries"] = [
            TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True)
            for entry in entries
        ]
    return envelope(data)


@router.get("/timesheet-headers/{header_id}")
def get_timesheet_header(
    header_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    header = get_scoped_or_404(db, TimesheetHeader, tenant_id, header_id)
    if not include_deleted:
        ensure_document_not_deleted(header)
    return envelope(TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True))


@router.patch("/timesheet-headers/{header_id}")
def update_timesheet_header(
    header_id: str,
    payload: UpdateTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, header_id)
    # members only touch their own headers; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, header.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "timesheet", updates)
    if "status" in updates and updates["status"] != header.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, header, updates["status"])
    if "custom_fields" in updates:
        header.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(header, field, value)
    db.commit()
    db.refresh(header)
    return envelope(TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True))


@router.delete("/timesheet-headers/{header_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timesheet_header(
    header_id: str,
    payload: DeleteTimesheetHeaderRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, TimesheetHeader, header_id, payload)


@router.post("/timesheet-headers/{header_id}/restore")
def restore_timesheet_header(
    header_id: str,
    payload: RestoreTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, TimesheetHeader, header_id)


@router.post("/timesheet-headers/{header_id}/submit")
def submit_timesheet_header(
    header_id: str,
    payload: SubmitTimesheetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, TimesheetHeader, header_id)


@router.get("/timesheet-headers/{header_id}/detail")
def get_timesheet_detail(
    header_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    header = get_scoped_or_404(db, TimesheetHeader, tenant_id, header_id)
    if not include_deleted:
        ensure_document_not_deleted(header)
    entries = db.scalars(
        select(TimesheetEntry)
        .where(
            TimesheetEntry.tenant_id == tenant_id,
            TimesheetEntry.header_id == header_id,
            TimesheetEntry.deleted_at.is_(None),
        )
        .order_by(TimesheetEntry.work_date.asc(), TimesheetEntry.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "timesheet_header", header_id)
    detail = TimesheetDetailRead(
        header=TimesheetHeaderRead.model_validate(header),
        entries=[TimesheetEntryRead.model_validate(entry) for entry in entries],
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/timesheet-entries")
def list_timesheet_entries(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    header_id: str | None = None,
    employee_id: str | None = None,
    project_id: str | None = None,
    work_date_from: date | None = None,
    work_date_to: date | None = None,
):
    stmt = (
        select(TimesheetEntry)
        .join(TimesheetHeader, TimesheetEntry.header_id == TimesheetHeader.id)
        .where(
            TimesheetEntry.tenant_id == tenant_id,
            TimesheetEntry.deleted_at.is_(None),
            TimesheetHeader.deleted_at.is_(None),
        )
    )
    if work_date_from:
        stmt = stmt.where(TimesheetEntry.work_date >= work_date_from)
    if work_date_to:
        stmt = stmt.where(TimesheetEntry.work_date <= work_date_to)
    return list_rows(
        db, stmt,
        filters={
            TimesheetEntry.header_id: header_id,
            TimesheetEntry.employee_id: employee_id,
            TimesheetEntry.project_id: project_id,
        },
        order_by=(TimesheetEntry.work_date.desc(),),
        pagination=None,
        read_model=TimesheetEntryRead,
    )


def build_timesheet_entry(
    db: Session, actor: Actor, payload, *, header: TimesheetHeader | None = None
) -> TimesheetEntry:
    """One validated entry, standalone or inline. The single set of rules for
    both paths — the inline path exists to save turns, not to skip checks.

    `header` passed = the row rides the header's own create: parent identity
    comes from the header, and the editable-state gate does not apply — the
    person is stating the document as a whole, including record-won documents
    created directly in a later state."""
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "work_type", payload.work_type)
    if header is None:
        if not payload.header_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="header_id is required")
        header = get_active_document_or_404(db, TimesheetHeader, tenant_id, payload.header_id)
        ensure_document_editable(db, header)
    elif payload.header_id and payload.header_id != header.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="inline entries belong to the header being created; do not name another header_id",
        )
    enforce_member_employee(actor, header.employee_id)
    employee_id = payload.employee_id or header.employee_id
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    if payload.work_date is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="work_date is required")
    validate_header_entry_link(header, employee_id, payload.work_date)
    project_id, project_name_snapshot = normalize_project_context(
        db,
        tenant_id,
        payload.project_id,
        payload.project_name_snapshot,
    )
    entry = TimesheetEntry(
        tenant_id=tenant_id,
        header_id=header.id,
        employee_id=employee_id,
        work_date=payload.work_date,
        project_id=project_id,
        project_name_snapshot=project_name_snapshot,
        client=payload.client,
        task=payload.task,
        hours=payload.hours,
        work_type=payload.work_type,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(entry)
    return entry


@router.post("/timesheet-entries", status_code=status.HTTP_201_CREATED)
def create_timesheet_entry(
    payload: CreateTimesheetEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "timesheet.submit_own")
    entry = build_timesheet_entry(db, actor, payload)
    record_line_audit(
        db, actor, TimesheetHeader, entry.header_id, entry.id, "line_added",
    )
    db.commit()
    db.refresh(entry)
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.get("/timesheet-entries/{entry_id}")
def get_timesheet_entry(
    entry_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TimesheetEntry not found")
    ensure_document_not_deleted(get_scoped_or_404(db, TimesheetHeader, tenant_id, entry.header_id))
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.patch("/timesheet-entries/{entry_id}")
def update_timesheet_entry(
    entry_id: str,
    payload: UpdateTimesheetEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TimesheetEntry not found")
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, entry.header_id)
    ensure_document_editable(db, header)
    enforce_member_employee(actor, header.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "work_type" in updates:
        require_type_option(db, tenant_id, "work_type", updates["work_type"])
    if "project_id" in updates or "project_name_snapshot" in updates:
        project_id, project_name_snapshot = normalize_project_context(
            db,
            tenant_id,
            updates.get("project_id", entry.project_id),
            updates.get("project_name_snapshot", entry.project_name_snapshot),
        )
        entry.project_id = project_id
        entry.project_name_snapshot = project_name_snapshot
        updates.pop("project_id", None)
        updates.pop("project_name_snapshot", None)
    if "hours" in updates:
        entry.hours = updates.pop("hours")
    if "custom_fields" in updates:
        entry.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(entry, field, value)
    record_line_audit(
        db, actor, TimesheetHeader, entry.header_id, entry.id, "line_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(entry)
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.delete("/timesheet-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timesheet_entry(
    entry_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, entry.header_id)
    ensure_document_editable(db, header)
    enforce_member_employee(actor, header.employee_id)
    entry.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, TimesheetHeader, entry.header_id, entry.id, "line_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- expense claims: money spent, asserted by the person who spent it --------


@router.get(
    "/expense-claims",
    response_model=ExpenseClaimListEnvelope,
    response_model_exclude_unset=True,
)
def list_expense_claims(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "expense_claim", status_filter)
    stmt = select(ExpenseClaim).where(ExpenseClaim.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(ExpenseClaim.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, ExpenseClaim, tenant_id, "expense_claim")
    return list_rows(
        db, stmt,
        filters={
            ExpenseClaim.employee_id: employee_id,
            ExpenseClaim.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(ExpenseClaim.id, String),
            cast(ExpenseClaim.employee_id, String),
            ExpenseClaim.title,
            cast(ExpenseClaim.claim_date, String),
            ExpenseClaim.currency,
            ExpenseClaim.status,
            ExpenseClaim.source_report_text,
        ),
        order_by=(ExpenseClaim.created_at.desc(), ExpenseClaim.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ExpenseClaimRead,
    )


@router.post("/expense-claims", status_code=status.HTTP_201_CREATED)
def create_expense_claim(
    payload: CreateExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_machine_state(db, tenant_id, ExpenseClaim, payload.status)
    claim = ExpenseClaim(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        title=payload.title,
        claim_date=payload.claim_date,
        currency=payload.currency,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(claim)
    db.flush()
    items = [build_expense_item(db, actor, row, claim=claim) for row in payload.items]
    db.commit()
    db.refresh(claim)
    data = ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True)
    if items:
        data["items"] = [
            ExpenseItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/expense-claims/{claim_id}")
def get_expense_claim(
    claim_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    claim = get_scoped_or_404(db, ExpenseClaim, tenant_id, claim_id)
    if not include_deleted:
        ensure_document_not_deleted(claim)
    return envelope(ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True))


@router.patch("/expense-claims/{claim_id}")
def update_expense_claim(
    claim_id: str,
    payload: UpdateExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, claim_id)
    # members only touch their own claims; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, claim.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "expense", updates)
    if "status" in updates and updates["status"] != claim.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, claim, updates["status"])
    if "custom_fields" in updates:
        claim.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(claim, field, value)
    db.commit()
    db.refresh(claim)
    return envelope(ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True))


@router.delete("/expense-claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense_claim(
    claim_id: str,
    payload: DeleteExpenseClaimRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """A claim that has been paid out cannot be hidden: the payment applied to
    it would keep pointing at a document nobody can see."""
    claim = get_scoped_or_404(db, ExpenseClaim, actor.tenant_id, claim_id)
    if claim.deleted_at is None:
        ensure_nothing_applied(db, claim, label="expense claim")
    return delete_document(db, actor, ExpenseClaim, claim_id, payload)


@router.post("/expense-claims/{claim_id}/restore")
def restore_expense_claim(
    claim_id: str,
    payload: RestoreExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, ExpenseClaim, claim_id)


@router.post("/expense-claims/{claim_id}/submit")
def submit_expense_claim(
    claim_id: str,
    payload: SubmitExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, ExpenseClaim, claim_id)


@router.get(
    "/expense-claims/{claim_id}/detail",
    response_model=ExpenseClaimDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_expense_claim_detail(
    claim_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    claim = get_scoped_or_404(db, ExpenseClaim, tenant_id, claim_id)
    if not include_deleted:
        ensure_document_not_deleted(claim)
    items = db.scalars(
        select(ExpenseItem)
        .where(
            ExpenseItem.tenant_id == tenant_id,
            ExpenseItem.claim_id == claim_id,
            ExpenseItem.deleted_at.is_(None),
        )
        .order_by(ExpenseItem.expense_date.asc(), ExpenseItem.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "expense_claim", claim_id)
    attachments = attachments_for_items(db, tenant_id, items)
    vendor_ids = {item.vendor_id for item in items if item.vendor_id}
    vendors = (
        db.scalars(
            select(Vendor).where(
                Vendor.tenant_id == tenant_id,
                Vendor.id.in_(vendor_ids),
            )
        ).all()
        if vendor_ids
        else []
    )
    vendor_names = {vendor.id: vendor.name for vendor in vendors}
    detail_items = [
        ExpenseItemDetailRead(
            **ExpenseItemRead.model_validate(item).model_dump(),
            vendor_name=vendor_names.get(item.vendor_id) if item.vendor_id else None,
        )
        for item in items
    ]
    detail = ExpenseClaimDetailRead(
        claim=ExpenseClaimRead.model_validate(claim),
        items=detail_items,
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        attachments=[AttachmentRead.model_validate(attachment) for attachment in attachments],
        total_amount=float(sum(item.amount for item in items)),
        total_tax_amount=float(sum(item.tax_amount or 0 for item in items)),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/expense-items")
def list_expense_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    claim_id: str | None = None,
    employee_id: str | None = None,
    project_id: str | None = None,
    vendor_id: str | None = None,
    invoice_number: str | None = None,
    expense_date_from: date | None = None,
    expense_date_to: date | None = None,
):
    stmt = (
        select(ExpenseItem)
        .join(ExpenseClaim, ExpenseItem.claim_id == ExpenseClaim.id)
        .where(
            ExpenseItem.tenant_id == tenant_id,
            ExpenseItem.deleted_at.is_(None),
            ExpenseClaim.deleted_at.is_(None),
        )
    )
    if expense_date_from:
        stmt = stmt.where(ExpenseItem.expense_date >= expense_date_from)
    if expense_date_to:
        stmt = stmt.where(ExpenseItem.expense_date <= expense_date_to)
    return list_rows(
        db, stmt,
        filters={
            ExpenseItem.claim_id: claim_id,
            ExpenseItem.employee_id: employee_id,
            ExpenseItem.project_id: project_id,
            ExpenseItem.vendor_id: vendor_id,
            ExpenseItem.invoice_number: invoice_number,
        },
        order_by=(ExpenseItem.expense_date.desc(),),
        pagination=None,
        read_model=ExpenseItemRead,
    )


def build_expense_item(
    db: Session, actor: Actor, payload, *, claim: ExpenseClaim | None = None
) -> ExpenseItem:
    """One validated item, standalone or inline — see build_timesheet_entry."""
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "expense_category", payload.category)
    if claim is None:
        if not payload.claim_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="claim_id is required")
        claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, payload.claim_id)
        ensure_document_editable(db, claim)
    elif payload.claim_id and payload.claim_id != claim.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="inline items belong to the claim being created; do not name another claim_id",
        )
    enforce_member_employee(actor, claim.employee_id)
    employee_id = payload.employee_id or claim.employee_id
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    if claim.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_id must match the claim")
    if payload.expense_date is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expense_date is required")
    if payload.amount is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="amount is required")
    ensure_invoice_not_duplicated(db, tenant_id, payload.invoice_number)
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    project_id, project_name_snapshot = normalize_project_context(
        db,
        tenant_id,
        payload.project_id,
        payload.project_name_snapshot,
    )
    vendor_id, merchant = normalize_vendor_context(db, tenant_id, payload.vendor_id, payload.merchant)
    item = ExpenseItem(
        tenant_id=tenant_id,
        claim_id=claim.id,
        employee_id=employee_id,
        expense_date=payload.expense_date,
        category=payload.category,
        amount=payload.amount,
        tax_amount=payload.tax_amount,
        vendor_id=vendor_id,
        merchant=merchant,
        invoice_number=payload.invoice_number,
        invoice_type=payload.invoice_type,
        project_id=project_id,
        project_name_snapshot=project_name_snapshot,
        client=payload.client,
        attachment_id=payload.attachment_id,
        extracted_fields_jsonb=payload.extracted_fields,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(item)
    return item


@router.post("/expense-items", status_code=status.HTTP_201_CREATED)
def create_expense_item(
    payload: CreateExpenseItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "expense.submit_own")
    item = build_expense_item(db, actor, payload)
    record_line_audit(
        db, actor, ExpenseClaim, item.claim_id, item.id, "line_added",
    )
    db.commit()
    db.refresh(item)
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.get("/expense-items/{item_id}")
def get_expense_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExpenseItem not found")
    ensure_document_not_deleted(get_scoped_or_404(db, ExpenseClaim, tenant_id, item.claim_id))
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/expense-items/{item_id}")
def update_expense_item(
    item_id: str,
    payload: UpdateExpenseItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExpenseItem not found")
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, item.claim_id)
    ensure_document_editable(db, claim)
    enforce_member_employee(actor, claim.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "category" in updates:
        require_type_option(db, tenant_id, "expense_category", updates["category"])
    if "invoice_number" in updates and updates["invoice_number"] != item.invoice_number:
        ensure_invoice_not_duplicated(db, tenant_id, updates["invoice_number"], exclude_item_id=item.id)
    if "attachment_id" in updates and updates["attachment_id"]:
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if "vendor_id" in updates or "merchant" in updates:
        vendor_id, merchant = normalize_vendor_context(
            db,
            tenant_id,
            updates.get("vendor_id", item.vendor_id),
            updates.get("merchant", item.merchant),
        )
        item.vendor_id = vendor_id
        item.merchant = merchant
        updates.pop("vendor_id", None)
        updates.pop("merchant", None)
    if "project_id" in updates or "project_name_snapshot" in updates:
        project_id, project_name_snapshot = normalize_project_context(
            db,
            tenant_id,
            updates.get("project_id", item.project_id),
            updates.get("project_name_snapshot", item.project_name_snapshot),
        )
        item.project_id = project_id
        item.project_name_snapshot = project_name_snapshot
        updates.pop("project_id", None)
        updates.pop("project_name_snapshot", None)
    if "extracted_fields" in updates:
        item.extracted_fields_jsonb = updates.pop("extracted_fields")
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    record_line_audit(
        db, actor, ExpenseClaim, item.claim_id, item.id, "line_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(item)
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/expense-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, item.claim_id)
    ensure_document_editable(db, claim)
    enforce_member_employee(actor, claim.employee_id)
    item.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, ExpenseClaim, item.claim_id, item.id, "line_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
