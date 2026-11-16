"""Inside a project — plan docs/plans/project-management-2026-11-15.md,
phases 1 and 2.

What the server holds a project's work to: tasks form a tree inside one
project, dependencies never loop, a timesheet entry's task belongs to the
entry's project, a purchase names a project that exists, a published status
report never changes. Everything else — the schedule, what moves when a task
slips, whether a milestone is truly met, what an issue's severity means — is
the agent's.

The figures are derived on every read and stored nowhere: hours planned
against hours recorded, per task and rolled up; the milestones' standing;
the issue log's counts; and the money — what was spent, ordered and billed
on the project, per currency, each from its own documents and never summed
across them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import event, func, inspect, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Contract,
    ExpenseClaim,
    ExpenseItem,
    Invoice,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Project,
    ProjectIssue,
    ProjectMilestone,
    ProjectReport,
    ProjectTask,
    ProjectTaskDependency,
    PurchaseOrder,
    PurchaseRequest,
    TimesheetEntry,
    TimesheetHeader,
)
from app.services.state_machines import counted_states

ZERO = Decimal("0")


def refuse(code: int, detail: str):
    raise HTTPException(status_code=code, detail=detail)


def ancestors(db: Session, task: ProjectTask):
    """The chain above a task. Stops at a node already seen: a parent written
    a moment ago may close a loop, and the walk that is meant to find it must
    not run round it forever."""
    seen: set[str] = set()
    node = db.get(ProjectTask, task.parent_task_id) if task.parent_task_id else None
    while node is not None and node.id not in seen:
        seen.add(node.id)
        yield node
        node = db.get(ProjectTask, node.parent_task_id) if node.parent_task_id else None


def check_parent(db: Session, task: ProjectTask) -> None:
    """The parent is a task of the same project, and not the task itself or
    one under it."""
    if not task.parent_task_id:
        return
    parent = db.get(ProjectTask, task.parent_task_id)
    if parent is None or parent.tenant_id != task.tenant_id:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"parent_task_id {task.parent_task_id} names no task")
    if parent.project_id != task.project_id:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "a sub-task belongs to its parent's project")
    if task.id is not None and any(node.id == task.id for node in [parent, *ancestors(db, parent)]):
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "a task cannot sit under itself or under one of its own")


def check_dependency(db: Session, predecessor: ProjectTask, successor: ProjectTask) -> None:
    """Both tasks of one project, and no loop: the successor must not already
    lead, through any chain, back to the predecessor."""
    if predecessor.project_id != successor.project_id:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "a dependency joins two tasks of one project")
    following: dict[str, list[str]] = defaultdict(list)
    for before, after in db.execute(
        select(ProjectTaskDependency.predecessor_task_id, ProjectTaskDependency.successor_task_id)
        .join(ProjectTask, ProjectTask.id == ProjectTaskDependency.predecessor_task_id)
        .where(ProjectTask.project_id == predecessor.project_id)
    ):
        following[before].append(after)
    seen, stack = set(), [successor.id]
    while stack:
        node = stack.pop()
        if node == predecessor.id:
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                   "this dependency closes a loop — the successor already leads back to the predecessor")
        if node not in seen:
            seen.add(node)
            stack.extend(following[node])


@event.listens_for(Session, "before_flush")
def _timesheet_tasks(session: Session, flush_context, instances) -> None:
    """Every timesheet write path — an entry's own POST and PATCH, the whole
    timesheet's save — passes here: a task named on an entry is a task of the
    entry's project."""
    entries = [o for o in (*session.new, *session.dirty) if isinstance(o, TimesheetEntry) and o.task_id]
    with session.no_autoflush:
        for entry in entries:
            if entry not in session.new and not any(
                inspect(entry).attrs[name].history.has_changes() for name in ("task_id", "project_id")
            ):
                continue
            task = session.get(ProjectTask, entry.task_id)
            if task is None or task.tenant_id != entry.tenant_id:
                refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"task_id {entry.task_id} names no task")
            if entry.project_id != task.project_id:
                refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                       f"task {task.task_code or task.name} belongs to another project than this entry — "
                       "name the task's project on the entry")


@event.listens_for(Session, "before_flush")
def _purchase_projects(session: Session, flush_context, instances) -> None:
    """A purchase request or order names a project of this workspace, on
    every write path. The order takes nothing from its request: its writer
    names the project, as cost centres work."""
    documents = [o for o in (*session.new, *session.dirty)
                 if isinstance(o, (PurchaseRequest, PurchaseOrder)) and o.project_id]
    with session.no_autoflush:
        for document in documents:
            if document not in session.new and not inspect(document).attrs.project_id.history.has_changes():
                continue
            project = session.get(Project, document.project_id)
            if project is None or project.tenant_id != document.tenant_id:
                refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"project_id: project {document.project_id} does not exist")


@event.listens_for(Session, "before_flush")
def _published_reports(session: Session, flush_context, instances) -> None:
    """A published report — its words and the figures frozen in it — never
    changes and is never removed. A correction is the next revision."""
    for report in session.deleted:
        if isinstance(report, ProjectReport) and _was_published(report):
            refuse(status.HTTP_409_CONFLICT, "a published report is kept — file the next revision to correct it")
    for report in session.dirty:
        if not isinstance(report, ProjectReport) or not _was_published(report):
            continue
        state = inspect(report)
        changed = [attr.key for attr in state.attrs if attr.key not in ("updated_at",) and attr.history.has_changes()]
        if changed:
            refuse(status.HTTP_409_CONFLICT, f"a published report never changes ({', '.join(sorted(changed))}) — "
                                             "file the next revision to correct it")


def _was_published(report: ProjectReport) -> bool:
    history = inspect(report).attrs.status.history
    before = history.deleted[0] if history.deleted else report.status
    return before == "published"


def next_revision(db: Session, tenant_id: str, project_id: str, period_start: date) -> int:
    """The revision a new report for this period takes. A draft already
    open for the period is the one to edit."""
    rows = db.execute(select(ProjectReport.revision, ProjectReport.status).where(
        ProjectReport.tenant_id == tenant_id, ProjectReport.project_id == project_id,
        ProjectReport.period_start == period_start)).all()
    if any(state == "draft" for _, state in rows):
        refuse(status.HTTP_409_CONFLICT, "a draft report for this period is open — edit it, or delete it first")
    return max((revision for revision, _ in rows), default=0) + 1


# the money parts of the figures, each read with its own documents' grant
MONEY_PARTS = ("expenses", "purchase_orders", "purchase_invoices", "billing", "book")


def _day(*candidates) -> date | None:
    for value in candidates:
        if value is None:
            continue
        return value.date() if hasattr(value, "date") and callable(value.date) else value
    return None


def _add(bucket: dict[str, Decimal], currency: str | None, amount) -> None:
    if amount is not None:
        bucket[currency or "?"] = bucket.get(currency or "?", ZERO) + Decimal(str(amount))


def _plain(bucket: dict[str, Decimal]) -> dict[str, float]:
    return {currency: float(amount) for currency, amount in sorted(bucket.items())}


def _invoices(db: Session, tenant_id: str, project_id: str, direction: str, as_of: date) -> dict:
    """Counted invoices of one direction naming the project, net of notes:
    a credit note counts here when it or the invoice it corrects names the
    project. Lines keep their sign, so notes net by plain addition."""
    counted = counted_states(db, tenant_id, "invoice")
    original = aliased(Invoice)
    rows = db.execute(
        select(Invoice).outerjoin(original, original.id == Invoice.original_invoice_id)
        .where(Invoice.tenant_id == tenant_id, Invoice.direction == direction, Invoice.deleted_at.is_(None),
               Invoice.status.in_(counted),
               or_(Invoice.project_id == project_id, original.project_id == project_id))
    ).scalars().all()
    invoiced: dict[str, Decimal] = {}
    credited: dict[str, Decimal] = {}
    for invoice in rows:
        if (_day(invoice.invoice_date, invoice.issued_at, invoice.created_at) or as_of) > as_of:
            continue
        _add(credited if invoice.invoice_kind == "credit_note" else invoiced, invoice.currency, invoice.total_amount)
    net = dict(invoiced)
    for currency, amount in credited.items():
        net[currency] = net.get(currency, ZERO) + amount
    return {"invoiced": _plain(invoiced), "credited": _plain(credited), "net": _plain(net),
            "count": len(rows)}


def money(db: Session, project: Project, as_of: date) -> dict:
    """What was spent, ordered and billed on the project up to `as_of`, per
    currency. Each part is its own documents' figure and they are not summed:
    an order becomes an invoice, an expense becomes a reimbursement, and only
    the agent knows which of them a question means. Reimbursement invoices
    are left out: they mirror expense claims already counted."""
    tenant_id, project_id = project.tenant_id, project.id
    expenses: dict[str, Decimal] = {}
    claim_states = counted_states(db, tenant_id, "expense_claim")
    for amount, currency in db.execute(
        select(ExpenseItem.amount, ExpenseClaim.currency)
        .join(ExpenseClaim, ExpenseClaim.id == ExpenseItem.claim_id)
        .where(ExpenseItem.tenant_id == tenant_id, ExpenseItem.project_id == project_id,
               ExpenseItem.deleted_at.is_(None), ExpenseClaim.deleted_at.is_(None),
               ExpenseClaim.status.in_(claim_states), ExpenseItem.expense_date <= as_of)
    ):
        _add(expenses, currency, amount)
    ordered: dict[str, Decimal] = {}
    order_states = counted_states(db, tenant_id, "purchase_order")
    orders = 0
    for order in db.scalars(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.project_id == project_id,
        PurchaseOrder.deleted_at.is_(None), PurchaseOrder.order_kind == "order",
        PurchaseOrder.status.in_(order_states),
    )):
        if (_day(order.order_date, order.created_at) or as_of) <= as_of:
            orders += 1
            _add(ordered, order.currency, order.total_amount)
    billing = _invoices(db, tenant_id, project_id, "sales", as_of)
    contract = db.get(Contract, project.contract_id) if project.contract_id else None
    billing["contract_value"] = (
        {contract.currency: float(contract.total_amount)}
        if contract is not None and contract.deleted_at is None and contract.total_amount is not None else {}
    )
    book: dict[str, Decimal] = {}
    for account_type, debit, credit in db.execute(
        select(LedgerAccount.account_type, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(JournalLine.tenant_id == tenant_id, JournalLine.project_id == project_id,
               JournalEntry.status == "posted", JournalEntry.deleted_at.is_(None),
               JournalEntry.posting_date <= as_of)
        .group_by(LedgerAccount.account_type)
    ):
        book[account_type] = Decimal(str(debit or 0)) - Decimal(str(credit or 0))
    return {
        "expenses": {"approved": _plain(expenses)},
        "purchase_orders": {"ordered": _plain(ordered), "count": orders},
        "purchase_invoices": _invoices(db, tenant_id, project_id, "purchase", as_of),
        "billing": billing,
        # posted journal lines naming the project: debit less credit per
        # account type, in the book's currency
        "book": {"net_debit_by_account_type": {k: float(v) for k, v in sorted(book.items())}},
    }


def issues(db: Session, tenant_id: str, project_id: str) -> dict:
    """The log's counts: unresolved ones by type and severity, and every
    issue by status. What is worth escalating is the agent's call."""
    by_status: dict[str, int] = defaultdict(int)
    unresolved: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for issue_type, severity, state, resolved_at in db.execute(
        select(ProjectIssue.issue_type, ProjectIssue.severity, ProjectIssue.status, ProjectIssue.resolved_at)
        .where(ProjectIssue.tenant_id == tenant_id, ProjectIssue.project_id == project_id)
    ):
        by_status[state] += 1
        if resolved_at is None:
            unresolved[issue_type][severity or "unrated"] += 1
    return {"by_status": dict(by_status),
            "unresolved_by_type_and_severity": {k: dict(v) for k, v in unresolved.items()},
            "unresolved": sum(sum(v.values()) for v in unresolved.values())}


def visible(figures: dict, parts: set[str]) -> dict:
    """The figures with the money parts the reader may not see left out,
    and named, so a missing part is never read as zero."""
    out = dict(figures)
    withheld = []
    if "money" in out:
        out["money"] = {k: v for k, v in out["money"].items() if k in parts}
        withheld = [k for k in MONEY_PARTS if k in figures["money"] and k not in parts]
    out["withheld"] = sorted(set(figures.get("withheld", [])) | set(withheld))
    return out


def execution(db: Session, project_id: str, tenant_id: str, as_of: date) -> dict:
    """Hours planned against recorded per task, rolled up the tree; hours on
    no task; where the milestones stand on `as_of`; the issue log's counts;
    and the money. Hours count once their timesheet has left its editable
    start (the states budgets count too). The money is whole here: the API
    leaves out what the reader may not see (`visible`)."""
    tasks = list(db.scalars(select(ProjectTask).where(
        ProjectTask.tenant_id == tenant_id, ProjectTask.project_id == project_id,
    ).order_by(ProjectTask.sort_order.asc().nulls_last(), ProjectTask.task_code, ProjectTask.created_at)))
    counted = counted_states(db, tenant_id, "timesheet_header")
    recorded: dict[str | None, Decimal] = defaultdict(lambda: ZERO)
    for task_id, hours in db.execute(
        select(TimesheetEntry.task_id, func.coalesce(func.sum(TimesheetEntry.hours), 0))
        .join(TimesheetHeader, TimesheetHeader.id == TimesheetEntry.header_id)
        .where(TimesheetEntry.tenant_id == tenant_id, TimesheetEntry.project_id == project_id,
               TimesheetEntry.deleted_at.is_(None), TimesheetHeader.deleted_at.is_(None),
               TimesheetHeader.status.in_(counted), TimesheetEntry.work_date <= as_of)
        .group_by(TimesheetEntry.task_id)
    ):
        recorded[task_id] += Decimal(str(hours))
    parents = {t.id: t.parent_task_id for t in tasks}
    with_children = {t.parent_task_id for t in tasks if t.parent_task_id}
    planned_total: dict[str, Decimal] = defaultdict(lambda: ZERO)
    recorded_total: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for task in tasks:
        own_plan = Decimal(str(task.planned_hours)) if task.planned_hours is not None and task.id not in with_children \
            else ZERO
        node = task.id
        while node is not None:
            planned_total[node] += own_plan
            recorded_total[node] += recorded.get(task.id, ZERO)
            node = parents.get(node)
    rows = [{
        "task_id": t.id, "task_code": t.task_code, "name": t.name, "parent_task_id": t.parent_task_id,
        "summary": t.id in with_children, "status": t.status, "assignee_employee_id": t.assignee_employee_id,
        "planned_start": t.planned_start, "planned_end": t.planned_end,
        "actual_start": t.actual_start, "actual_end": t.actual_end,
        "planned_hours": float(planned_total[t.id]) if t.id in with_children
        else (float(t.planned_hours) if t.planned_hours is not None else None),
        "recorded_hours": float(recorded_total[t.id]),
    } for t in tasks]
    milestones = []
    standing: dict[str, int] = defaultdict(int)
    for m in db.scalars(select(ProjectMilestone).where(
        ProjectMilestone.tenant_id == tenant_id, ProjectMilestone.project_id == project_id,
    ).order_by(ProjectMilestone.due_date, ProjectMilestone.created_at)):
        if m.status == "cancelled":
            where = "cancelled"
        elif m.reached_on is not None:
            where = "reached_on_time" if m.reached_on <= m.due_date else "reached_late"
        else:
            where = "overdue" if m.due_date < as_of else "upcoming"
        standing[where] += 1
        milestones.append({"milestone_id": m.id, "name": m.name, "due_date": m.due_date, "reached_on": m.reached_on,
                           "standing": where, "invoice_id": m.invoice_id})
    return {
        "project_id": project_id, "as_of": as_of,
        "hours": {"planned": float(sum((planned_total[t.id] for t in tasks if not t.parent_task_id), ZERO)),
                  "recorded": float(sum(recorded.values(), ZERO)),
                  "recorded_on_no_task": float(recorded.get(None, ZERO))},
        "tasks": rows, "milestones": milestones, "milestone_standing": dict(standing),
        "issues": issues(db, tenant_id, project_id),
        "money": money(db, db.get(Project, project_id), as_of),
    }
