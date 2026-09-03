"""Who works here: the employee record, their leave, their pay terms, and the
one endpoint that turns an id into a name.

Split out of `routes.py`: employees, employee leave, pay histories, and
`/directory/display-names/resolve`.

Pay histories are the employee's TERMS — salary, the period they hold for, who
approved them — not a payslip. The payslip is an invoice with
`direction="payroll"` and lives with the other documents in `billing.py`; what
this module owns is the agreement a payslip is computed from, which is why
`ensure_pay_history_unused` refuses to edit a term a payslip already used.

The display-name resolver sits here because the identities it maps are these
records plus users and API keys — it returns maps, never rows, so that an
object page can label one page of activity without pulling a tenant-wide
directory.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.common import (
    apply_status_change,
    commit_or_conflict,
    delete_document,
    ensure_content_edit_allowed,
    envelope,
    exclude_rows_with_open_todo,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    may_read_payroll,
    own_employee_id,
    page_only_pagination,
    requested_pagination,
    require_machine_state,
    restore_document,
    submit_document,
)
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, require_permission
from app.core.permissions import (
    HOSTED_FLOW_AGENT_DISPLAY_NAME,
    PRINCIPAL_HOSTED_FLOW_AGENT,
)
from app.db.session import get_db
from app.models import (
    ApiKey,
    Employee,
    EmployeeLeave,
    InvoiceItem,
    PayHistory,
    Todo,
    User,
)
from app.schemas import (
    CreateEmployeeLeaveRequest,
    CreateEmployeeRequest,
    CreatePayHistoryRequest,
    DeleteEmployeeLeaveRequest,
    DisplayNameResolutionEnvelope,
    DisplayNameResolutionRead,
    DisplayNameResolveRequest,
    EmployeeEnvelope,
    EmployeeLeaveEnvelope,
    EmployeeLeaveListEnvelope,
    EmployeeLeaveRead,
    EmployeeListEnvelope,
    EmployeeRead,
    PayHistoryChangeEnvelope,
    PayHistoryChangeRead,
    PayHistoryEnvelope,
    PayHistoryListEnvelope,
    PayHistoryRead,
    TodoListEnvelope,
    TodoRead,
    UpdateEmployeeLeaveRequest,
    UpdateEmployeeRequest,
    UpdatePayHistoryRequest,
)
from app.services.audit import record_audit
from app.services.type_options import require_type_option
from app.services.state_machines import validate_status_filter

router = APIRouter()


# --- the display-name resolver: ids in, labels out, nothing else -----------


def valid_uuid_ids(values: list[str]) -> set[str]:
    valid: set[str] = set()
    for value in values:
        try:
            valid.add(str(UUID(value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return valid


@router.post(
    "/directory/display-names/resolve",
    response_model=DisplayNameResolutionEnvelope,
    response_model_exclude_unset=True,
)
def resolve_display_names(
    payload: DisplayNameResolveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Resolve only the requested tenant-scoped display labels.

    The endpoint deliberately returns maps rather than user/key records so an
    object page can label one bounded page of activity without downloading a
    tenant-wide identity directory or exposing unrelated profile fields.
    """
    employee_ids = valid_uuid_ids(payload.employee_ids)
    requested_user_ids = valid_uuid_ids(
        [label.removeprefix("user:") for label in payload.actor_labels if label.startswith("user:")]
    )
    requested_key_ids = valid_uuid_ids(
        [label.removeprefix("key:") for label in payload.actor_labels if label.startswith("key:")]
    )

    employees = (
        db.scalars(
            select(Employee).where(
                Employee.tenant_id == actor.tenant_id,
                Employee.id.in_(employee_ids),
            )
        ).all()
        if employee_ids
        else []
    )
    users = (
        db.scalars(
            select(User).where(
                User.tenant_id == actor.tenant_id,
                User.id.in_(requested_user_ids),
            )
        ).all()
        if requested_user_ids
        else []
    )
    api_keys = (
        db.scalars(
            select(ApiKey).where(
                ApiKey.tenant_id == actor.tenant_id,
                ApiKey.id.in_(requested_key_ids),
            )
        ).all()
        if requested_key_ids
        else []
    )
    hosted = {
        api_key.id
        for api_key in api_keys
        if api_key.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT
    }
    result = DisplayNameResolutionRead(
        employees={employee.id: employee.name for employee in employees},
        actors={
            **{
                f"user:{user.id}": user.name or user.email
                for user in users
            },
            **{
                # A hosted principal reads as its canonical name, taken from the
                # constant rather than from `label` — the tenant can neither
                # rename it nor mint a key that renders the same way.
                f"key:{api_key.id}": (
                    HOSTED_FLOW_AGENT_DISPLAY_NAME
                    if api_key.id in hosted
                    else f"key:{api_key.label or api_key.id[:8]}"
                )
                for api_key in api_keys
            },
        },
        actor_kinds={f"key:{key_id}": PRINCIPAL_HOSTED_FLOW_AGENT for key_id in hosted},
    )
    return envelope(result.model_dump())


# --- employees: the record, and the todos addressed to one ------------------


@router.get("/employees", response_model=EmployeeListEnvelope, response_model_exclude_unset=True)
def list_employees(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Employee).where(Employee.tenant_id == tenant_id),
        filters={Employee.status: status_filter},
        keyword=keyword,
        keyword_columns=(Employee.name,),
        order_by=(Employee.created_at.desc(), Employee.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=EmployeeRead,
    )


@router.post(
    "/employees",
    response_model=EmployeeEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    payload: CreateEmployeeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "employees.manage")
    employee = Employee(
        tenant_id=actor.tenant_id,
        employee_code=payload.employee_code,
        name=payload.name,
        email=payload.email,
        timezone=payload.timezone,
        hire_date=payload.hire_date,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.get("/employees/{employee_id}", response_model=EmployeeEnvelope, response_model_exclude_unset=True)
def get_employee(
    employee_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    employee = get_scoped_or_404(db, Employee, tenant_id, employee_id)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.patch("/employees/{employee_id}", response_model=EmployeeEnvelope, response_model_exclude_unset=True)
def update_employee(
    employee_id: str,
    payload: UpdateEmployeeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "employees.manage")
    employee = get_scoped_or_404(db, Employee, actor.tenant_id, employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        employee.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(employee, field, value)
    db.commit()
    db.refresh(employee)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.get(
    "/employees/{employee_id}/todos",
    response_model=TodoListEnvelope,
    response_model_exclude_unset=True,
)
def list_employee_todos(
    employee_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    stmt = select(Todo).where(
        Todo.tenant_id == tenant_id,
        Todo.employee_id == employee_id,
    )
    result = list_rows(
        db, stmt,
        filters={
            Todo.status: status_filter,
            Todo.entity_type: entity_type,
            Todo.entity_id: entity_id,
        },
        keyword=keyword,
        keyword_columns=(
            Todo.title,
            Todo.description,
            Todo.todo_type,
            cast(Todo.entity_id, String),
        ),
        order_by=(Todo.created_at.desc(), Todo.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=TodoRead,
    )
    for row in result["data"]:
        row.pop("target", None)
    return result


# --- employee leave: a document, with the submit/restore arc that implies ---


@router.get(
    "/employee-leaves",
    response_model=EmployeeLeaveListEnvelope,
    response_model_exclude_unset=True,
)
def list_employee_leaves(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    leave_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    overlapping_from: date | None = None,
    overlapping_thru: date | None = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """The rows an agent computes a balance FROM.

    `overlapping_from`/`overlapping_thru` is the filter that makes the
    computation one call: leave that overlaps the period at all, which is what
    "how much annual leave has this person used this year" needs — a request
    straddling New Year belongs to both years in part, and the caller decides
    how to split it by the tenant's rule. Filtering on `from_date` alone would
    silently drop it from one side.
    """
    validate_status_filter(db, tenant_id, "employee_leave", status_filter)
    stmt = select(EmployeeLeave).where(EmployeeLeave.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(EmployeeLeave.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, EmployeeLeave, tenant_id, "employee_leave")
    if overlapping_from is not None:
        stmt = stmt.where(EmployeeLeave.thru_date >= overlapping_from)
    if overlapping_thru is not None:
        stmt = stmt.where(EmployeeLeave.from_date <= overlapping_thru)
    return list_rows(
        db, stmt,
        filters={
            EmployeeLeave.employee_id: employee_id,
            EmployeeLeave.leave_type: leave_type,
            EmployeeLeave.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(EmployeeLeave.id, String),
            cast(EmployeeLeave.employee_id, String),
            EmployeeLeave.leave_type,
            EmployeeLeave.reason,
            EmployeeLeave.status,
            EmployeeLeave.source_report_text,
        ),
        order_by=(
            EmployeeLeave.from_date.desc(),
            EmployeeLeave.created_at.desc(),
            EmployeeLeave.id.desc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=EmployeeLeaveRead,
    )


@router.post("/employee-leaves", status_code=status.HTTP_201_CREATED)
def create_employee_leave(
    payload: CreateEmployeeLeaveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """File one absence.

    Deliberately absent: any check that the person has the days. Entitlement is
    computed from the tenant's policy, not stored, so the server has nothing to
    check against and inventing one would be the server deciding a rule that
    belongs in a document somebody can revise. Over-requesting is a legal
    record; the approver — informed by the agent's computation — decides.
    """
    tenant_id = actor.tenant_id
    require_permission(actor, "leave.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_type_option(db, tenant_id, "leave_type", payload.leave_type)
    initial_status = require_machine_state(db, tenant_id, EmployeeLeave, payload.status)
    if payload.thru_date < payload.from_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="thru_date cannot precede from_date",
        )
    leave = EmployeeLeave(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        leave_type=payload.leave_type,
        from_date=payload.from_date,
        thru_date=payload.thru_date,
        duration_days=payload.duration_days,
        reason=payload.reason,
        status=initial_status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.get(
    "/employee-leaves/{leave_id}",
    response_model=EmployeeLeaveEnvelope,
    response_model_exclude_unset=True,
)
def get_employee_leave(
    leave_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    leave = get_scoped_or_404(db, EmployeeLeave, tenant_id, leave_id)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.patch(
    "/employee-leaves/{leave_id}",
    response_model=EmployeeLeaveEnvelope,
    response_model_exclude_unset=True,
)
def update_employee_leave(
    leave_id: str,
    payload: UpdateEmployeeLeaveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    leave = get_active_document_or_404(db, EmployeeLeave, tenant_id, leave_id)
    enforce_member_employee(actor, leave.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "leave", updates)
    if updates.get("leave_type"):
        require_type_option(db, tenant_id, "leave_type", updates["leave_type"])
    from_date = updates.get("from_date", leave.from_date)
    thru_date = updates.get("thru_date", leave.thru_date)
    if thru_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="thru_date cannot precede from_date",
        )
    if "status" in updates and updates["status"] != leave.status:
        apply_status_change(db, actor, leave, updates["status"])
    if "custom_fields" in updates:
        leave.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(leave, field, value)
    db.commit()
    db.refresh(leave)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.delete("/employee-leaves/{leave_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_leave(
    leave_id: str,
    payload: DeleteEmployeeLeaveRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, EmployeeLeave, leave_id, payload)


@router.post("/employee-leaves/{leave_id}/restore")
def restore_employee_leave(
    leave_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, EmployeeLeave, leave_id)


@router.post("/employee-leaves/{leave_id}/submit")
def submit_employee_leave(
    leave_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, EmployeeLeave, leave_id)


# --- pay histories: the salary terms a payslip is computed from -------------
#
# OFBiz's `PayHistory`. The point of the entity is the history: what someone was
# paid last March has to stay answerable, because a payslip issued last March
# has to stay explainable.


def pay_history_or_404(db: Session, tenant_id: str, record_id: str) -> PayHistory:
    return get_scoped_or_404(db, PayHistory, tenant_id, record_id)


def ensure_pay_history_unused(db: Session, record: PayHistory) -> None:
    """A record a payslip has already cited is frozen. Moving it would change
    what an issued document says without touching that document."""
    cited = db.scalar(
        select(func.count())
        .select_from(InvoiceItem)
        .where(
            InvoiceItem.tenant_id == record.tenant_id,
            InvoiceItem.pay_history_id == record.id,
            InvoiceItem.deleted_at.is_(None),
        )
    )
    if cited:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{cited} payslip line(s) were computed from this salary record — "
                "record a new one from a later date instead of editing this"
            ),
        )


def ensure_no_overlapping_pay_period(
    db: Session, tenant_id: str, employee_id: str, component: str, effective_from: date,
    effective_thru: date | None, *, exclude_id: str | None = None,
) -> None:
    """Two salaries in force on the same day is not a fact about anybody — but
    a salary and a commission rate in force on the same day is the ordinary
    case, so the check is per COMPONENT.

    A unique index cannot say this — it is about ranges — so the API says it and
    the integrity audit says it again over the whole table."""
    stmt = select(PayHistory).where(
        PayHistory.tenant_id == tenant_id,
        PayHistory.employee_id == employee_id,
        PayHistory.component == component,
        PayHistory.effective_from <= (effective_thru or date(9999, 12, 31)),
        or_(
            PayHistory.effective_thru.is_(None),
            PayHistory.effective_thru >= effective_from,
        ),
    )
    if exclude_id:
        stmt = stmt.where(PayHistory.id != exclude_id)
    clash = db.scalars(stmt).first()
    if clash is not None:
        stated = (
            f"{float(clash.amount):.2f}"
            if clash.amount is not None
            else (f"{float(clash.rate)} of {clash.basis}" if clash.rate is not None else "a term")
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{clash.component} of {stated} is already in force from "
                f"{clash.effective_from} to {clash.effective_thru or '—'} for this employee"
            ),
        )


def pay_term_in_force_on(on: date):
    """A term is in force on a day if it had started and had not yet ended.
    An open `effective_thru` means "still current", not "ended at null"."""
    return and_(
        PayHistory.effective_from <= on,
        or_(PayHistory.effective_thru.is_(None), PayHistory.effective_thru >= on),
    )


def ensure_pay_term_states_something(payload) -> None:
    """A term has to say what it is. The three shapes cover a scalar (12000 a
    month), a proportion (3% of collections) and everything else in words — but
    a rate with nothing to apply it to is not a rule, it is half of one."""
    if payload.amount is None and payload.rate is None and not payload.formula:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a pay term states an amount, a rate (with the basis it applies to), "
                "or a formula in words — this one states none of them"
            ),
        )
    if payload.rate is not None and not payload.basis:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a rate needs the basis it applies to — 回款额, 毛利, 签约额, "
                "whatever this workspace calls it"
            ),
        )


@router.get("/pay-histories", response_model=PayHistoryListEnvelope, response_model_exclude_unset=True)
def list_pay_histories(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    component: str | None = None,
    in_force_on: date | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Salaries are the one thing in this system a credential does not get to
    read merely by belonging to the workspace. Without `payroll.read` an actor
    sees its own record and nothing else."""
    tenant_id = actor.tenant_id
    stmt = select(PayHistory).where(PayHistory.tenant_id == tenant_id)
    if not may_read_payroll(actor):
        own = own_employee_id(actor)
        if own is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="requires capability payroll.read",
            )
        stmt = stmt.where(PayHistory.employee_id == own)
    if in_force_on is not None:
        stmt = stmt.where(pay_term_in_force_on(in_force_on))
    return list_rows(
        db, stmt,
        filters={PayHistory.employee_id: employee_id, PayHistory.component: component},
        order_by=(PayHistory.effective_from.desc(), PayHistory.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PayHistoryRead,
    )


@router.post(
    "/pay-histories",
    status_code=status.HTTP_201_CREATED,
    response_model=PayHistoryChangeEnvelope,
    response_model_exclude_unset=True,
)
def create_pay_history(
    payload: CreatePayHistoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set or change a salary. A change closes the record in force the day
    before and opens this one — one call, one transaction, because as two calls
    the pair eventually drifts and leaves a hole in someone's history."""
    tenant_id = actor.tenant_id
    require_permission(actor, "payroll.manage")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    require_type_option(db, tenant_id, "pay_component_type", payload.component)
    require_type_option(db, tenant_id, "pay_period_type", payload.period_type)
    ensure_pay_term_states_something(payload)
    if payload.effective_thru is not None and payload.effective_thru < payload.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )

    superseded = db.scalars(
        select(PayHistory)
        .where(
            PayHistory.tenant_id == tenant_id,
            PayHistory.employee_id == payload.employee_id,
            # only the same component is superseded — a pay rise must not
            # silently close somebody's commission arrangement
            PayHistory.component == payload.component,
            PayHistory.effective_from < payload.effective_from,
            PayHistory.effective_thru.is_(None),
        )
        .order_by(PayHistory.effective_from.desc())
    ).first()
    if superseded is not None:
        superseded.effective_thru = payload.effective_from - timedelta(days=1)
        db.flush()

    ensure_no_overlapping_pay_period(
        db, tenant_id, payload.employee_id, payload.component,
        payload.effective_from, payload.effective_thru,
    )
    record = PayHistory(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        component=payload.component,
        effective_from=payload.effective_from,
        effective_thru=payload.effective_thru,
        amount=payload.amount,
        rate=payload.rate,
        basis=payload.basis,
        formula=payload.formula,
        period_type=payload.period_type,
        currency=payload.currency,
        notes=payload.notes,
        created_by=attributed(actor, None),
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(record)
    commit_or_conflict(db, (
                            f"this employee already has a {payload.component} term starting "
                        f"{payload.effective_from}"
                    ))
    db.refresh(record)
    if superseded is not None:
        db.refresh(superseded)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="pay_history.recorded",
        entity_type="pay_history",
        entity_id=record.id,
        actor=actor.label,
        detail={
            "employee_id": record.employee_id,
            "component": record.component,
            "effective_from": record.effective_from.isoformat(),
            "superseded_id": superseded.id if superseded else None,
        },
    )
    db.commit()
    return envelope(
        PayHistoryChangeRead(
            current=PayHistoryRead.model_validate(record),
            superseded=(
                PayHistoryRead.model_validate(superseded) if superseded is not None else None
            ),
        ).model_dump(by_alias=True)
    )


@router.get("/pay-histories/{record_id}", response_model=PayHistoryEnvelope, response_model_exclude_unset=True)
def get_pay_history(
    record_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    record = pay_history_or_404(db, actor.tenant_id, record_id)
    if not may_read_payroll(actor) and own_employee_id(actor) != record.employee_id:
        # 404, not 403: refusing by name would confirm whose record exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PayHistory not found")
    return envelope(PayHistoryRead.model_validate(record).model_dump(by_alias=True))


@router.patch("/pay-histories/{record_id}", response_model=PayHistoryEnvelope, response_model_exclude_unset=True)
def update_pay_history(
    record_id: str,
    payload: UpdatePayHistoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Correcting a typo. A real change in pay is a new record — see POST."""
    tenant_id = actor.tenant_id
    require_permission(actor, "payroll.manage")
    record = pay_history_or_404(db, tenant_id, record_id)
    ensure_pay_history_unused(db, record)
    updates = payload.model_dump(exclude_unset=True)
    if "period_type" in updates and updates["period_type"] is not None:
        require_type_option(db, tenant_id, "pay_period_type", updates["period_type"])
    effective_from = updates.get("effective_from", record.effective_from)
    effective_thru = updates.get("effective_thru", record.effective_thru)
    if effective_thru is not None and effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if "effective_from" in updates or "effective_thru" in updates:
        ensure_no_overlapping_pay_period(
            db, tenant_id, record.employee_id, record.component,
            effective_from, effective_thru, exclude_id=record.id,
        )
    ensure_pay_term_states_something(
        SimpleNamespace(
            amount=updates.get("amount", record.amount),
            rate=updates.get("rate", record.rate),
            basis=updates.get("basis", record.basis),
            formula=updates.get("formula", record.formula),
        )
    )
    if "custom_fields" in updates:
        record.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return envelope(PayHistoryRead.model_validate(record).model_dump(by_alias=True))


@router.get(
    "/employees/{employee_id}/pay-history",
    response_model=PayHistoryListEnvelope,
    response_model_exclude_unset=True,
)
def get_employee_pay_history(
    employee_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    component: str | None = None,
    in_force_on: date | None = None,
):
    """One person's whole compensation trail, newest first.

    `in_force_on` narrows it to what applied on a day, which is the question
    a payslip actually asks — every component in force that month, in one
    call."""
    tenant_id = actor.tenant_id
    if not may_read_payroll(actor) and own_employee_id(actor) != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    stmt = select(PayHistory).where(
        PayHistory.tenant_id == tenant_id, PayHistory.employee_id == employee_id
    )
    if in_force_on is not None:
        stmt = stmt.where(pay_term_in_force_on(in_force_on))
    return list_rows(
        db,
        stmt,
        filters={PayHistory.component: component},
        order_by=(PayHistory.effective_from.desc(), PayHistory.id.desc()),
        pagination=None,
        read_model=PayHistoryRead,
    )
