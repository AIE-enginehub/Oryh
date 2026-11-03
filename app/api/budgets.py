"""Budgets — plan docs/plans/budgets-2026-10-27.md, phases 1 and 2.

A budget's plan is a ledger (`budget_entries`) that moves only when a
`budget_change` posts; its consumption is derived from the business
documents on every read (`app/services/budgets.py`). The server states the
figures and never refuses spending for being over budget: whether going
over needs somebody's sign-off is the workspace's own approval flow, which
reads `GET /budget-impact`.

Reads of figures sit behind `budget.read_all` (which `budget.manage`
implies); a labour line's figures beyond its plan also need `payroll.read`,
because with two employees a labour total is somebody's salary. Line rows
carry no amounts, so the line list is the directory every member may read
to tag their documents.

Phase 3 scopes a spend budget to a cost centre: it reads that centre's
share of what the company budget collects, beside it.

Phase 2 adds sub-targets under the sales line (by salesperson, territory,
customer or product category) and the combined cash read across an income
and a spend budget. How far each line has gone is a figure on the execution
read (`percent_consumed`, `percent_achieved`); when that warrants telling
someone is the workspace's rule, so the agent raises the todo.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    ListFilters,
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    allocate_number,
    list_filters,
    apply_status_change,
    commit_or_conflict,
    ensure_document_editable,
    envelope,
    get_active_document_or_404,
    get_scoped_or_404,
    list_rows,
    may_read_payroll,
    require_machine_state,
    requested_pagination,
    rows_revision,
    save_rows,
)
from app.api.deps import Actor, attributed, get_actor, has_permission, require_permission
from app.api.family_routes import Verb, register_document_verbs
from app.core.entity_types import HOSTED_ADVANCE_VERBS
from app.db.session import get_db
from app.models import (
    Budget,
    BudgetChange,
    BudgetChangeLine,
    BudgetEntry,
    BudgetLine,
    CostCenter,
    Customer,
    Employee,
    ProductCategory,
    Territory,
)
from app.schemas import (
    BUDGET_DIMENSIONS,
    BudgetChangeEnvelope,
    BudgetChangeLineBase,
    BudgetChangeLineRead,
    BudgetChangeListEnvelope,
    BudgetChangeRead,
    BudgetEntryListEnvelope,
    BudgetEntryRead,
    BudgetEnvelope,
    BudgetImportRequest,
    BudgetLineEnvelope,
    BudgetLineListEnvelope,
    BudgetLineRead,
    BudgetListEnvelope,
    BudgetRead,
    CreateBudgetChangeRequest,
    CreateBudgetLineRequest,
    CreateBudgetRequest,
    SaveBudgetChangeLinesRequest,
    SavedLinesEnvelope,
    UpdateBudgetChangeLineRequest,
    UpdateBudgetChangeRequest,
    UpdateBudgetLineRequest,
    UpdateBudgetRequest,
)
from app.services import budgets as figures
from app.services.audit import record_audit
from app.services.state_machines import get_builtin_machine, state_for_role
from app.services.type_options import require_type_option

router = APIRouter()

CHANGE_ROWS = (BudgetChangeLine, "change_id", BudgetChangeLineRead)
# which ledger entry a signed change line becomes, per change type
ENTRY_TYPES = {
    "original": ("original", None),
    "increase": ("increase", None),
    "decrease": (None, "decrease"),
    "transfer": ("transfer_in", "transfer_out"),
    "carry_forward": ("carry_forward_in", "carry_forward_out"),
}


def _require_read(actor: Actor) -> None:
    require_permission(actor, "budget.read_all")


def _require_manage(actor: Actor) -> None:
    require_permission(actor, "budget.manage")


def _payroll(actor: Actor) -> bool:
    return may_read_payroll(actor)


# --- reads --------------------------------------------------------------------


def _line_read(line: BudgetLine, budget: Budget | None = None) -> dict:
    data = BudgetLineRead.model_validate(line).model_dump(by_alias=True)
    direction = budget.direction if budget is not None else None
    data["collects"] = line.status == "active" and not line.parent_line_id \
        and figures.COLLECTING_CATEGORIES.get(line.category) in ({direction} if direction else {"spend", "income"})
    return data


def _budget_read(db: Session, budget: Budget, *, full: bool) -> dict:
    data = BudgetRead.model_validate(budget).model_dump(by_alias=True)
    if full:
        data["lines"] = [_line_read(line, budget) for line in figures.Scope.of(db, budget).lines]
    else:
        data.pop("lines", None)
    return data


def _change_read(db: Session, change: BudgetChange, *, full: bool) -> dict:
    data = BudgetChangeRead.model_validate(change).model_dump(by_alias=True)
    if full:
        data["revision"] = rows_revision(db, change, BudgetChangeRead, {"items": CHANGE_ROWS})
        data["lines"] = [
            BudgetChangeLineRead.model_validate(row).model_dump(by_alias=True)
            for row in db.scalars(select(BudgetChangeLine).where(
                BudgetChangeLine.tenant_id == change.tenant_id, BudgetChangeLine.change_id == change.id,
            ).order_by(BudgetChangeLine.line_no.asc().nulls_last(), BudgetChangeLine.created_at.asc()))
        ]
    else:
        data.pop("lines", None)
        data.pop("revision", None)
    return data


# --- budgets ----------------------------------------------------------------


def _check_line_fields(db: Session, tenant_id: str, budget: Budget, category: str, owner: str | None) -> None:
    require_type_option(db, tenant_id, "budget_category", category)
    wanted = figures.COLLECTING_CATEGORIES.get(category)
    if wanted is not None and wanted != budget.direction:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"a {category} line collects {wanted}; budget {budget.budget_no} plans {budget.direction}",
        )
    if owner:
        get_scoped_or_404(db, Employee, tenant_id, owner)


def _check_centre(db: Session, tenant_id: str, direction: str, centre: str | None) -> None:
    """A cost-centre budget plans spend: sales are the company's."""
    if not centre:
        return
    if direction != "spend":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a cost centre's budget plans spend; income is planned on the company budget")
    get_scoped_or_404(db, CostCenter, tenant_id, centre)


def _ensure_no_overlap(db: Session, budget: Budget) -> None:
    """Two live budgets of one direction and currency whose periods overlap
    may not both collect the same category — one marketing expense would
    count in both (plan §11 Q10)."""
    mine = {line.category for line in figures.Scope.of(db, budget).top
            if line.status == "active" and line.category in figures.COLLECTING_CATEGORIES}
    if not mine:
        return
    others = db.scalars(select(Budget).where(
        Budget.tenant_id == budget.tenant_id, Budget.id != budget.id, Budget.deleted_at.is_(None),
        Budget.direction == budget.direction, Budget.currency == budget.currency,
        # a cost centre's budget is a breakdown beside the company's: only two
        # budgets of the same scope would count one document twice
        Budget.cost_center_id.is_(None) if budget.cost_center_id is None
        else Budget.cost_center_id == budget.cost_center_id,
        Budget.status.in_(figures.budget_states(db, budget.tenant_id).live),
        Budget.period_start <= budget.period_end, Budget.period_end >= budget.period_start,
    )).all()
    for other in others:
        clash = sorted(mine & {line.category for line in figures.Scope.of(db, other).top
                               if line.status == "active" and line.category in figures.COLLECTING_CATEGORIES})
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"budget {other.budget_no} already collects {', '.join(clash)} for an overlapping period "
                    f"({other.period_start} to {other.period_end}) — one document would count in both; "
                    "close or freeze that budget, or close its line, first"
                ),
            )


@router.get("/budgets", response_model=BudgetListEnvelope, response_model_exclude_unset=True)
def list_budgets(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    direction: str | None = None,
    budget_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(Budget, ranges=('created_at', 'period_start', 'period_end', 'activated_at', 'closed_at'), equals=('currency', 'owner_employee_id')))] = None,
):
    _require_read(actor)
    stmt = select(Budget).where(Budget.tenant_id == actor.tenant_id)
    if not include_deleted:
        stmt = stmt.where(Budget.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={Budget.direction: direction, Budget.budget_type: budget_type, Budget.status: status_filter},
        keyword=keyword,
        keyword_columns=(cast(Budget.id, String), Budget.budget_no, Budget.name, Budget.description),
        order_by=(Budget.period_start.desc(), Budget.created_at.desc(), Budget.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        extra=extra,
        read_model=BudgetRead,
    )


@router.post("/budgets", response_model=BudgetEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: CreateBudgetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_manage(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "budget_type", payload.budget_type)
    if payload.owner_employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.owner_employee_id)
    _check_centre(db, tenant_id, payload.direction, payload.cost_center_id)
    initial = require_machine_state(db, actor, Budget, payload.status)
    active = figures.budget_states(db, tenant_id).active
    budget_no = payload.budget_no or allocate_number(db, Budget, tenant_id)
    budget = Budget(
        tenant_id=tenant_id, budget_no=budget_no, name=payload.name, direction=payload.direction,
        budget_type=payload.budget_type, currency=payload.currency.upper(),
        period_start=payload.period_start, period_end=payload.period_end,
        owner_employee_id=payload.owner_employee_id, status=initial,
        description=payload.description, custom_fields_jsonb=payload.custom_fields,
        cost_center_id=payload.cost_center_id,
    )
    if initial == active:
        budget.activated_at = datetime.now(timezone.utc)
    db.add(budget)
    try:
        db.flush()
        codes = set()
        for index, row in enumerate(payload.lines, start=1):
            if row.line_code in codes:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f"lines[{index - 1}]: line_code {row.line_code!r} appears twice")
            codes.add(row.line_code)
            _check_line_fields(db, tenant_id, budget, row.category, row.owner_employee_id)
            db.add(BudgetLine(
                tenant_id=tenant_id, budget_id=budget.id, line_code=row.line_code, name=row.name,
                category=row.category, owner_employee_id=row.owner_employee_id,
                sort_order=row.sort_order if row.sort_order is not None else index,
                description=row.description, metadata_jsonb=row.metadata,
            ))
        db.flush()
        if initial == active:
            _ensure_no_overlap(db, budget)
        record_audit(db, tenant_id=tenant_id, action="budget.created", entity_type="budget", entity_id=budget.id,
                     actor=actor.label, detail={"budget_no": budget_no, "name": budget.name,
                                                "direction": budget.direction, "lines": len(payload.lines)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"budget_no {budget_no!r} already exists, or two lines collect the same category",
        )
    db.refresh(budget)
    return envelope(_budget_read(db, budget, full=True))


@router.get("/budgets/{budget_id}", response_model=BudgetEnvelope, response_model_exclude_unset=True)
def get_budget(
    budget_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_read(actor)
    budget = get_active_document_or_404(db, Budget, actor.tenant_id, budget_id)
    return envelope(_budget_read(db, budget, full=True))


def _has_entries(db: Session, budget: Budget) -> bool:
    return db.scalar(select(BudgetEntry.id).where(
        BudgetEntry.tenant_id == budget.tenant_id, BudgetEntry.budget_id == budget.id).limit(1)) is not None


@router.patch("/budgets/{budget_id}", response_model=BudgetEnvelope, response_model_exclude_unset=True)
def update_budget(
    budget_id: str,
    payload: UpdateBudgetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_manage(actor)
    tenant_id = actor.tenant_id
    budget = get_active_document_or_404(db, Budget, tenant_id, budget_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    # the name, owner and notes move at any state; what the figures are
    # measured in and over moves only while the budget is a draft with no
    # posted figure
    notes = {"name", "owner_employee_id", "description", "custom_fields"}
    if set(updates) - notes:
        ensure_document_editable(db, budget)
        if _has_entries(db, budget) and {"currency", "period_start", "period_end"} & set(updates):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="changes have posted to this budget — its currency and period are what those figures mean",
            )
    start = updates.get("period_start", budget.period_start)
    end = updates.get("period_end", budget.period_end)
    if end < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="period_end must not precede period_start")
    if updates.get("budget_type"):
        require_type_option(db, tenant_id, "budget_type", updates["budget_type"])
    if updates.get("cost_center_id"):
        _check_centre(db, tenant_id, budget.direction, updates["cost_center_id"])
    if updates.get("owner_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, updates["owner_employee_id"])
    if "custom_fields" in updates:
        budget.custom_fields_jsonb = updates.pop("custom_fields")
    if "currency" in updates and updates["currency"]:
        updates["currency"] = updates["currency"].upper()
    for name, value in updates.items():
        setattr(budget, name, value)
    if status_change is not None and status_change != budget.status:
        apply_status_change(db, actor, budget, status_change)
        budget.status = status_change
        _after_budget_move(db, budget, status_change)
    db.commit()
    db.refresh(budget)
    return envelope(_budget_read(db, budget, full=False))


def _move_budget(db: Session, actor: Actor, budget: Budget, new_status: str) -> None:
    apply_status_change(db, actor, budget, new_status)
    budget.status = new_status
    _after_budget_move(db, budget, new_status)


def _after_budget_move(db: Session, budget: Budget, new_status: str) -> None:
    """Stamps, and the overlap rule an activation must pass."""
    now = datetime.now(timezone.utc)
    states = figures.budget_states(db, budget.tenant_id)
    if new_status == states.active:
        budget.activated_at = budget.activated_at or now
        db.flush()
        _ensure_no_overlap(db, budget)
    if new_status == states.closed:
        budget.closed_at = now


def _before_delete_budget(db: Session, actor: Actor, budget_id: str) -> None:
    _require_manage(actor)
    budget = get_scoped_or_404(db, Budget, actor.tenant_id, budget_id)
    if budget.status != get_builtin_machine(db, actor.tenant_id, "budget")["initial"] or _has_entries(db, budget):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only a draft budget with no posted figures is deleted; close one that has been used",
        )


register_document_verbs(router, Budget, path="/budgets", id_param="budget_id",
                        delete=Verb(before=_before_delete_budget), restore=Verb())


@router.get("/budgets/{budget_id}/execution")
def budget_execution(
    budget_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    by_month: bool = True,
):
    """Every figure per line and month: planned, and for spend requested,
    committed, actual, available, paid and unbudgeted; for income ordered,
    invoiced, gap, received and the pipeline forecast. Labour figures beyond
    their plan need payroll.read."""
    _require_read(actor)
    budget = get_active_document_or_404(db, Budget, actor.tenant_id, budget_id)
    return envelope(figures.execution(db, budget, may_read_payroll=_payroll(actor), by_month=by_month))


@router.post("/budgets/{budget_id}/close")
def close_budget(
    budget_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Close at period end, and read back what each spend line left unspent
    — the figures a carry-forward change into next year's budget starts from.
    Nothing carries forward by itself."""
    _require_manage(actor)
    budget = get_active_document_or_404(db, Budget, actor.tenant_id, budget_id)
    closed = figures.budget_states(db, actor.tenant_id).closed
    if budget.status != closed:
        _move_budget(db, actor, budget, closed)
        db.commit()
        db.refresh(budget)
    result = figures.execution(db, budget, may_read_payroll=_payroll(actor), by_month=False)
    unspent = [
        {"line_id": row["line_id"], "line_code": row["line_code"], "name": row["name"],
         "unspent": row["totals"].get("available")}
        for row in result["lines"] if budget.direction == "spend"
    ]
    return envelope({"budget": _budget_read(db, budget, full=False), "unspent": unspent})


# --- lines ------------------------------------------------------------------


@router.get("/budget-lines", response_model=BudgetLineListEnvelope, response_model_exclude_unset=True)
def list_budget_lines(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    budget_id: str | None = None,
    category: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(BudgetLine, ranges=('created_at',), equals=('owner_employee_id',)))] = None,
):
    """The directory: codes, names and categories, no amounts — readable by
    every member, who tags spend no collection rule reaches."""
    stmt = select(BudgetLine).join(Budget, Budget.id == BudgetLine.budget_id).where(
        BudgetLine.tenant_id == actor.tenant_id, Budget.deleted_at.is_(None),
    )
    return list_rows(
        db, stmt,
        filters={BudgetLine.budget_id: budget_id, BudgetLine.category: category, BudgetLine.status: status_filter},
        keyword=keyword,
        keyword_columns=(BudgetLine.line_code, BudgetLine.name, BudgetLine.description),
        order_by=(BudgetLine.budget_id.asc(), BudgetLine.sort_order.asc().nulls_last(), BudgetLine.line_code.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        extra=extra,
        render=lambda rows: [_line_read(row, db.get(Budget, row.budget_id)) for row in rows],
    )


@router.post("/budget-lines", response_model=BudgetLineEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_budget_line(
    payload: CreateBudgetLineRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_manage(actor)
    tenant_id = actor.tenant_id
    budget = get_active_document_or_404(db, Budget, tenant_id, payload.budget_id)
    if budget.status not in figures.budget_states(db, tenant_id).unclosed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"budget {budget.budget_no} is closed")
    category = payload.category
    if payload.parent_line_id:
        category = _check_sub_target(db, tenant_id, budget, payload)
    _check_line_fields(db, tenant_id, budget, category, payload.owner_employee_id)
    line = BudgetLine(
        tenant_id=tenant_id, budget_id=budget.id, line_code=payload.line_code, name=payload.name,
        category=category, owner_employee_id=payload.owner_employee_id, status=payload.status,
        sort_order=payload.sort_order, description=payload.description, metadata_jsonb=payload.metadata,
        parent_line_id=payload.parent_line_id,
        **{name: getattr(payload, name) for name in BUDGET_DIMENSIONS},
    )
    db.add(line)
    try:
        db.flush()
        if budget.status in figures.budget_states(db, tenant_id).live:
            _ensure_no_overlap(db, budget)
        record_audit(db, tenant_id=tenant_id, action="budget.line_added", entity_type="budget", entity_id=budget.id,
                     actor=actor.label, detail={"budget_no": budget.budget_no, "line_id": line.id,
                                                "line_code": line.line_code, "category": line.category,
                                                "parent_line_id": line.parent_line_id})
        db.commit()
    except IntegrityError:
        db.rollback()
        detail = (f"line_code {payload.line_code!r} is taken in this budget, or a live {category} line "
                  "already collects for it — one collecting line per category")
        if payload.parent_line_id:
            detail = (f"line_code {payload.line_code!r} is taken in this budget, or a live sub-target of that line "
                      "already names this dimension")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    db.refresh(line)
    return envelope(_line_read(line, budget))


# a sub-target's dimension column -> what it names
DIMENSION_MODELS = {
    "employee_id": Employee,
    "territory_id": Territory,
    "customer_id": Customer,
    "product_category_id": ProductCategory,
}


def _check_sub_target(db: Session, tenant_id: str, budget: Budget, payload: CreateBudgetLineRequest) -> str:
    """A sub-target splits the budget's sales line by one dimension; it takes
    its parent's category. Returns that category."""
    parent = get_scoped_or_404(db, BudgetLine, tenant_id, payload.parent_line_id)
    if parent.budget_id != budget.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"parent line {parent.line_code} belongs to another budget")
    if parent.parent_line_id or figures.COLLECTING_CATEGORIES.get(parent.category) != "income":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a sub-target splits an income budget's sales line — "
                                   f"{parent.line_code} is a {parent.category} line")
    if payload.category not in ("other", parent.category):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"a sub-target takes its parent's category ({parent.category})")
    for name, model in DIMENSION_MODELS.items():
        if getattr(payload, name):
            get_scoped_or_404(db, model, tenant_id, getattr(payload, name))
    return parent.category


@router.patch("/budget-lines/{line_id}", response_model=BudgetLineEnvelope, response_model_exclude_unset=True)
def update_budget_line(
    line_id: str,
    payload: UpdateBudgetLineRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_manage(actor)
    line = get_scoped_or_404(db, BudgetLine, actor.tenant_id, line_id)
    budget = db.get(Budget, line.budget_id)
    updates = payload.model_dump(exclude_unset=True)
    if line.parent_line_id and updates.get("category") not in (None, line.category):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"a sub-target takes its parent's category ({line.category})")
    if updates.get("category") or updates.get("owner_employee_id"):
        _check_line_fields(db, actor.tenant_id, budget, updates.get("category", line.category),
                           updates.get("owner_employee_id"))
    if "metadata" in updates:
        line.metadata_jsonb = updates.pop("metadata") or {}
    for name, value in updates.items():
        setattr(line, name, value)
    record_audit(db, tenant_id=actor.tenant_id, action="budget.line_changed", entity_type="budget",
                 entity_id=budget.id, actor=actor.label,
                 detail={"budget_no": budget.budget_no, "line_id": line.id, "fields": sorted(updates)})
    try:
        db.flush()
        if budget.status in figures.budget_states(db, actor.tenant_id).live and ({"category", "status"} & set(updates)):
            _ensure_no_overlap(db, budget)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="a live line of that category already collects for this budget, "
                                   "or a live sub-target already names this dimension")
    db.refresh(line)
    return envelope(_line_read(line, budget))


def _line_and_budget(db: Session, actor: Actor, line_id: str) -> tuple[BudgetLine, Budget]:
    _require_read(actor)
    line = get_scoped_or_404(db, BudgetLine, actor.tenant_id, line_id)
    budget = get_active_document_or_404(db, Budget, actor.tenant_id, line.budget_id)
    if not _payroll(actor):
        scope, found = figures.contributions(db, budget)
        if line.id in figures.payroll_line_ids(scope, found):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="a line carrying labour figures is pay — requires payroll.read")
    return line, budget


@router.get("/budget-lines/{line_id}/documents")
def budget_line_documents(
    line_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    stage: str | None = None,
):
    """The documents behind a line's figures, one row per document and stage."""
    line, budget = _line_and_budget(db, actor, line_id)
    return envelope(figures.line_documents(db, budget, line.id, stage))


@router.get("/budget-lines/{line_id}/availability")
def budget_line_availability(
    line_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    amount: Annotated[float, Query(ge=0)] = 0,
):
    """What an agent asks before filing spend: what the line has left now,
    and after this amount."""
    line, budget = _line_and_budget(db, actor, line_id)
    totals = figures.line_totals(db, budget, line.id)
    left = figures.available(totals)
    after = left - Decimal(str(amount))
    return envelope({
        "line_id": line.id, "line_code": line.line_code, "budget_id": budget.id, "budget_no": budget.budget_no,
        "currency": budget.currency, "planned": figures.cents(totals.get("planned", figures.ZERO)),
        "consumed": figures.cents(totals.get("requested", figures.ZERO) + totals.get("committed", figures.ZERO)
                                  + totals.get("actual", figures.ZERO)),
        "available": figures.cents(left), "amount": amount, "available_after": figures.cents(after),
        "would_go_negative": after < 0,
    })


# --- changes ----------------------------------------------------------------


def _resolve_line(db: Session, tenant_id: str, change_budget: Budget, source: Budget | None, row) -> BudgetLine:
    """A change line names its budget line by id or by code — in the change's
    budget, or for a carry-forward's negative half, in the budget it comes
    from."""
    allowed = {change_budget.id} | ({source.id} if source is not None else set())
    if row.budget_line_id:
        line = get_scoped_or_404(db, BudgetLine, tenant_id, row.budget_line_id)
    else:
        home = source if (source is not None and row.amount < 0) else change_budget
        line = db.scalar(select(BudgetLine).where(
            BudgetLine.tenant_id == tenant_id, BudgetLine.budget_id == home.id, BudgetLine.line_code == row.line_code,
        ))
        if line is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"budget {home.budget_no} has no line {row.line_code!r}")
    if line.budget_id not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"budget line {line.line_code} belongs to another budget")
    home_budget = change_budget if line.budget_id == change_budget.id else source
    if not (home_budget.period_start <= row.period_month <= home_budget.period_end):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{row.period_month} is outside budget {home_budget.budget_no}'s period")
    return line


def _build_change_line(db: Session, change: BudgetChange, row, index: int | None = None) -> BudgetChangeLine:
    budget = db.get(Budget, change.budget_id)
    source = db.get(Budget, change.source_budget_id) if change.source_budget_id else None
    line = _resolve_line(db, change.tenant_id, budget, source, row)
    item = BudgetChangeLine(
        tenant_id=change.tenant_id, change_id=change.id, budget_line_id=line.id,
        line_no=row.line_no if row.line_no is not None else index, period_month=row.period_month,
        amount=row.amount, note=row.note,
    )
    db.add(item)
    return item


def _post(db: Session, actor: Actor, change: BudgetChange) -> None:
    """Write the ledger: one entry per change line, under a lock on the
    budget so two changes never interleave. The sign rules are checked here,
    where they bind, whatever path reached `posted`."""
    budget_ids = {change.budget_id}
    if change.source_budget_id:
        budget_ids.add(change.source_budget_id)
    locked = {row.id: row for row in db.scalars(select(Budget).where(
        Budget.tenant_id == change.tenant_id, Budget.id.in_(budget_ids),
    ).order_by(Budget.id).with_for_update())}
    budget = locked[change.budget_id]
    if change.source_budget_id and locked[change.source_budget_id].currency != budget.currency:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a carry_forward moves one currency between budgets; currency conversion is not supported")
    if budget.status not in figures.budget_states(db, change.tenant_id).unclosed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"budget {budget.budget_no} is {budget.status!r} — its plan no longer moves")
    rows = db.scalars(select(BudgetChangeLine).where(
        BudgetChangeLine.tenant_id == change.tenant_id, BudgetChangeLine.change_id == change.id,
    )).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="a change with no lines moves nothing")
    total = sum((Decimal(str(r.amount)) for r in rows), Decimal(0))
    positive, negative = ENTRY_TYPES.get(change.change_type, ("increase", "decrease"))
    kind = change.change_type
    if kind in ("original", "increase") and any(r.amount < 0 for r in rows):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"an {kind} change gives money — every line is positive; take money with a decrease")
    if kind == "decrease" and any(r.amount > 0 for r in rows):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a decrease takes money — every line is negative")
    if kind in ("transfer", "carry_forward") and total != 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"a {kind} moves money and nets to zero — these lines sum to {total}")
    if kind == "carry_forward" and not change.source_budget_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a carry_forward names the budget it comes from (source_budget_id)")
    lines = {row.id: db.get(BudgetLine, row.budget_line_id) for row in rows}
    levels = {line.parent_line_id for line in lines.values()}
    # money moves between lines of one level: a sub-target's plan is a
    # breakdown of its parent's, never money the parent can hand over
    if kind == "carry_forward" and levels != {None}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a carry_forward moves top-level lines; plan next year's sub-targets afresh")
    if kind == "transfer" and len(levels) > 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="a transfer moves money between top-level lines, or between sub-targets of one "
                                   "line — never between the two")
    for row in rows:
        line = lines[row.id]
        entry_type = positive if row.amount > 0 else negative
        db.add(BudgetEntry(
            tenant_id=change.tenant_id, budget_id=line.budget_id, budget_line_id=line.id, change_id=change.id,
            change_line_id=row.id, entry_type=entry_type, period_month=row.period_month, amount=row.amount,
            created_by=attributed(actor, None),
        ))
    change.posted_at = datetime.now(timezone.utc)
    change.posted_by = actor.label


def _move_change(db: Session, actor: Actor, change: BudgetChange, new_status: str) -> None:
    _check_change_move(db, actor, change, new_status)
    apply_status_change(db, actor, change, new_status)
    change.status = new_status
    _after_change_move(db, actor, change, new_status)


def _check_change_move(db: Session, actor: Actor, change: BudgetChange, new_status: str) -> None:
    """The owner posts a draft directly (budget.manage); a routed change is
    approved, returned, rejected and posted by whoever holds budget.advance."""
    machine = get_builtin_machine(db, actor.tenant_id, "budget_change")
    posted = state_for_role(machine, "budget_change", "posted")
    if new_status == posted and change.status == machine["initial"]:
        _require_manage(actor)
    elif new_status in ("cancelled", state_for_role(machine, "budget_change", "submitted")) \
            and change.status in machine.get("editable_states", ()):
        _require_manage(actor)
    elif not (has_permission(actor, "budget.advance") or (new_status == posted and has_permission(actor, "budget.manage"))):
        require_permission(actor, "budget.advance")


def _after_change_move(db: Session, actor: Actor, change: BudgetChange, new_status: str) -> None:
    """The submitted stamp, and the ledger written when the change posts."""
    machine = get_builtin_machine(db, actor.tenant_id, "budget_change")
    posted = state_for_role(machine, "budget_change", "posted")
    if new_status == state_for_role(machine, "budget_change", "submitted"):
        change.submitted_at = change.submitted_at or datetime.now(timezone.utc)
    if new_status == posted:
        db.flush()
        _post(db, actor, change)


@router.get("/budget-changes", response_model=BudgetChangeListEnvelope, response_model_exclude_unset=True)
def list_budget_changes(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    budget_id: str | None = None,
    change_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(BudgetChange, ranges=('created_at', 'submitted_at', 'posted_at'), equals=('employee_id', 'source_budget_id')))] = None,
):
    if not has_permission(actor, "budget.advance"):
        _require_read(actor)
    stmt = select(BudgetChange).where(BudgetChange.tenant_id == actor.tenant_id)
    if not include_deleted:
        stmt = stmt.where(BudgetChange.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={BudgetChange.budget_id: budget_id, BudgetChange.change_type: change_type,
                 BudgetChange.status: status_filter},
        keyword=keyword,
        keyword_columns=(cast(BudgetChange.id, String), BudgetChange.change_no, BudgetChange.reason),
        order_by=(BudgetChange.created_at.desc(), BudgetChange.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        extra=extra,
        read_model=BudgetChangeRead,
    )


@router.post("/budget-changes", response_model=BudgetChangeEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_budget_change(
    payload: CreateBudgetChangeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_manage(actor)
    tenant_id = actor.tenant_id
    budget = get_active_document_or_404(db, Budget, tenant_id, payload.budget_id)
    require_type_option(db, tenant_id, "budget_change_type", payload.change_type)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    if payload.source_budget_id:
        if payload.change_type != "carry_forward":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="source_budget_id belongs to a carry_forward")
        get_active_document_or_404(db, Budget, tenant_id, payload.source_budget_id)
    machine = get_builtin_machine(db, tenant_id, "budget_change")
    posted = state_for_role(machine, "budget_change", "posted")
    wanted = payload.status or machine["initial"]
    if wanted not in (machine["initial"], posted):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"a change starts as {machine['initial']!r}, or {posted!r} to file and post it in one call",
        )
    change_no = payload.change_no or allocate_number(db, BudgetChange, tenant_id)
    change = BudgetChange(
        tenant_id=tenant_id, change_no=change_no, budget_id=budget.id, change_type=payload.change_type,
        employee_id=payload.employee_id, reason=payload.reason, status=machine["initial"],
        source_budget_id=payload.source_budget_id, custom_fields_jsonb=payload.custom_fields,
    )
    db.add(change)
    try:
        db.flush()
        for index, row in enumerate(payload.lines, start=1):
            _build_change_line(db, change, row, index)
        db.flush()
        if wanted == posted:
            _move_change(db, actor, change, posted)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"change_no {change_no!r} already exists")
    db.refresh(change)
    return envelope(_change_read(db, change, full=True))


@router.get("/budget-changes/{change_id}", response_model=BudgetChangeEnvelope, response_model_exclude_unset=True)
def get_budget_change(
    change_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    if not has_permission(actor, "budget.advance"):
        _require_read(actor)
    change = get_active_document_or_404(db, BudgetChange, actor.tenant_id, change_id)
    return envelope(_change_read(db, change, full=True))


@router.patch("/budget-changes/{change_id}", response_model=BudgetChangeEnvelope, response_model_exclude_unset=True)
def update_budget_change(
    change_id: str,
    payload: UpdateBudgetChangeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    change = get_active_document_or_404(db, BudgetChange, actor.tenant_id, change_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if updates:
        _require_manage(actor)
        ensure_document_editable(db, change)
        if updates.get("change_type"):
            require_type_option(db, actor.tenant_id, "budget_change_type", updates["change_type"])
        if "custom_fields" in updates:
            change.custom_fields_jsonb = updates.pop("custom_fields") or {}
        for name, value in updates.items():
            setattr(change, name, value)
    if status_change is not None and status_change != change.status:
        _check_change_move(db, actor, change, status_change)
        apply_status_change(db, actor, change, status_change)
        change.status = status_change
        _after_change_move(db, actor, change, status_change)
    db.commit()
    db.refresh(change)
    return envelope(_change_read(db, change, full=True))


@router.post("/budget-changes/{change_id}/save", response_model=SavedLinesEnvelope, response_model_exclude_unset=True)
def save_budget_change_lines(
    change_id: str,
    payload: SaveBudgetChangeLinesRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    validate_only: bool = False,
):
    """The change's lines restated in one act, as a diff under its revision."""
    _require_manage(actor)
    change = get_active_document_or_404(db, BudgetChange, actor.tenant_id, change_id)
    ensure_document_editable(db, change)

    def update(row: BudgetChangeLine, changed: dict) -> None:
        if {"budget_line_id", "line_code", "period_month", "amount"} & set(changed):
            merged = BudgetChangeLineBase(
                budget_line_id=changed.get("budget_line_id", row.budget_line_id if "line_code" not in changed else None),
                line_code=changed.get("line_code"),
                period_month=changed.get("period_month", row.period_month),
                amount=changed.get("amount", float(row.amount)),
            )
            budget = db.get(Budget, change.budget_id)
            source = db.get(Budget, change.source_budget_id) if change.source_budget_id else None
            row.budget_line_id = _resolve_line(db, change.tenant_id, budget, source, merged).id
        changed.pop("line_code", None)
        changed.pop("budget_line_id", None)
        for name, value in changed.items():
            setattr(row, name, value)

    return save_rows(
        db, actor, document=change, parent_model=BudgetChange, header_read=BudgetChangeRead, spec=CHANGE_ROWS,
        payload=payload, build=lambda row: _build_change_line(db, change, row), update=update, remove=db.delete,
        new_model=BudgetChangeLineBase, update_model=UpdateBudgetChangeLineRequest, validate_only=validate_only,
    )


def _before_delete_change(db: Session, actor: Actor, change_id: str) -> None:
    _require_manage(actor)
    change = get_scoped_or_404(db, BudgetChange, actor.tenant_id, change_id)
    if change.posted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="a posted change is the plan's history — correct it with another change")


register_document_verbs(router, BudgetChange, path="/budget-changes", id_param="change_id",
                        singular="budget_change", delete=Verb(before=_before_delete_change), restore=Verb(),
                        submit=Verb())


@router.get("/budget-entries", response_model=BudgetEntryListEnvelope, response_model_exclude_unset=True)
def list_budget_entries(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    budget_id: str | None = None,
    budget_line_id: str | None = None,
    change_id: str | None = None,
    period_month: date | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(BudgetEntry, ranges=('created_at', 'period_month'), equals=('entry_type',)))] = None,
):
    """The plan ledger, read-only: every posted figure and the change that
    posted it."""
    _require_read(actor)
    return list_rows(
        db, select(BudgetEntry).where(BudgetEntry.tenant_id == actor.tenant_id),
        filters={BudgetEntry.budget_id: budget_id, BudgetEntry.budget_line_id: budget_line_id,
                 BudgetEntry.change_id: change_id, BudgetEntry.period_month: period_month},
        order_by=(BudgetEntry.period_month.asc(), BudgetEntry.created_at.asc(), BudgetEntry.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        extra=extra,
        read_model=BudgetEntryRead,
    )


# --- plan import (B15) -----------------------------------------------------


@router.post("/budgets/{budget_id}/import")
def import_budget_plan(
    budget_id: str,
    payload: BudgetImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """A plan from a spreadsheet: missing lines are created; every new
    line-month rides one change (original if the budget has no figures yet,
    else increase); a line-month already planned is `unchanged` at the same
    figure and an error at another — a different figure is a change with a
    reason. Posted when asked; a dry run writes nothing."""
    _require_manage(actor)
    tenant_id = actor.tenant_id
    budget = get_active_document_or_404(db, Budget, tenant_id, budget_id)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    plan = figures.planned(db, budget)
    lines = {line.line_code: line for line in figures.Scope.of(db, budget).lines}
    results, new_rows, seen = [], [], set()
    created_lines = 0
    for index, row in enumerate(payload.rows):
        key = (row.line_code, row.period_month)
        if row.period_month.day != 1 or not (budget.period_start <= row.period_month <= budget.period_end):
            results.append({"index": index, "outcome": "error", "error": f"{row.period_month} is not a month of this budget"})
            continue
        if key in seen:
            results.append({"index": index, "outcome": "error", "error": "this line and month appear twice"})
            continue
        seen.add(key)
        line = lines.get(row.line_code)
        if line is None:
            category = row.category or "other"
            _check_line_fields(db, tenant_id, budget, category, None)
            line = BudgetLine(tenant_id=tenant_id, budget_id=budget.id, line_code=row.line_code,
                              name=row.name or row.line_code, category=category, sort_order=len(lines) + 1)
            db.add(line)
            db.flush()
            lines[row.line_code] = line
            created_lines += 1
        current = plan.get((line.id, row.period_month))
        if current is not None and current != 0:
            if current == Decimal(str(row.amount)):
                results.append({"index": index, "outcome": "unchanged"})
            else:
                results.append({"index": index, "outcome": "error",
                                "error": f"{row.line_code} {row.period_month} is already planned at {current} — "
                                         "a different figure is a change with its reason"})
            continue
        new_rows.append((line, row))
        results.append({"index": index, "outcome": "planned"})
    change = None
    if new_rows:
        machine = get_builtin_machine(db, tenant_id, "budget_change")
        change = BudgetChange(
            tenant_id=tenant_id, change_no=allocate_number(db, BudgetChange, tenant_id), budget_id=budget.id,
            change_type="original" if not plan else "increase", employee_id=payload.employee_id,
            reason=payload.reason, status=machine["initial"],
        )
        db.add(change)
        db.flush()
        for index, (line, row) in enumerate(new_rows, start=1):
            db.add(BudgetChangeLine(tenant_id=tenant_id, change_id=change.id, budget_line_id=line.id, line_no=index,
                                    period_month=row.period_month, amount=row.amount))
        db.flush()
        if payload.post:
            _move_change(db, actor, change, state_for_role(machine, "budget_change", "posted"))
    summary = {"rows": len(payload.rows), "lines_created": created_lines,
               "planned": sum(1 for r in results if r["outcome"] == "planned"),
               "unchanged": sum(1 for r in results if r["outcome"] == "unchanged"),
               "errors": sum(1 for r in results if r["outcome"] == "error")}
    data = {"dry_run": payload.dry_run, "summary": summary, "results": results,
            "change": _change_read(db, change, full=False) if change is not None else None}
    if payload.dry_run:
        db.rollback()
    else:
        db.commit()
    return envelope(data)


# --- the combined cash read (phase 2) --------------------------------------


@router.get("/budget-cash")
def budget_cash(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    income_budget_id: str | None = None,
    spend_budget_id: str | None = None,
):
    """The combined cash budget: planned income less planned spend, and cash
    received less cash paid, per month with running totals. Name an income
    budget, a spend budget, or both (one currency)."""
    _require_read(actor)
    if not income_budget_id and not spend_budget_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="name income_budget_id, spend_budget_id, or both")
    income = get_active_document_or_404(db, Budget, actor.tenant_id, income_budget_id) if income_budget_id else None
    spend = get_active_document_or_404(db, Budget, actor.tenant_id, spend_budget_id) if spend_budget_id else None
    for budget, wanted in ((income, "income"), (spend, "spend")):
        if budget is not None and budget.direction != wanted:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"budget {budget.budget_no} plans {budget.direction}, not {wanted}")
    if income is not None and spend is not None and income.currency != spend.currency:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"budget {income.budget_no} is in {income.currency}, {spend.budget_no} in "
                                   f"{spend.currency} — a cash budget nets one currency")
    return envelope(figures.cash_view(db, income, spend, may_read_payroll=_payroll(actor)))


# --- budget impact of a spending document (B11) -----------------------------

# who may read a document's budget impact besides the budget readers: whoever
# advances (approves) that kind of document — the flow agent and approvers
IMPACT_ADVANCE = {
    "expense_claim": HOSTED_ADVANCE_VERBS["expense_claim"],
    "purchase_request": HOSTED_ADVANCE_VERBS["purchase_request"],
    "invoice": HOSTED_ADVANCE_VERBS["invoice"],
    "purchase_order": "purchase_order.manage",
}


@router.get("/budget-impact")
def budget_impact(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str,
    entity_id: str,
):
    """Which budget lines a spending document draws on, and what each has
    left before and after it. Read by whoever approves such documents and by
    the budget readers; never a refusal — the workspace's approval flow
    decides what an overrun means."""
    family = figures.SPENDING_DOCUMENTS.get(entity_type)
    if family is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"entity_type is one of {sorted(figures.SPENDING_DOCUMENTS)}")
    if not (has_permission(actor, "budget.read_all") or has_permission(actor, IMPACT_ADVANCE[entity_type])):
        require_permission(actor, "budget.read_all")
    document = get_active_document_or_404(db, family[0], actor.tenant_id, entity_id)
    return envelope({
        "entity_type": entity_type, "entity_id": document.id,
        "lines": figures.document_impact(db, entity_type, document, may_read_payroll=_payroll(actor)),
    })
