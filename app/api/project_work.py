"""Inside a project — plan docs/plans/project-management-2026-11-15.md,
phases 1 and 2.

Tasks (a tree), the dependencies between them, milestones, the issue log,
status reports, and the figures a project is followed by. `project.manage`
plans the work and writes the reports; a member holding `project.contribute`
raises issues and states the actual dates and status of a task assigned to
them. Every member reads a project's work, as they read the project; the
money in the figures needs `project.manage` or the grant that reads the
documents it comes from.

The rules the server holds the work to are in `app/services/project_work.py`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import String, cast, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api.common import ORDER_BY_DOC, PAGE_SIZE_DOC, ListFilters, envelope, get_scoped_or_404, list_filters, list_rows, requested_pagination
from app.api.common.numbering import allocate_document_number
from app.api.deps import Actor, get_actor, has_permission, require_permission
from app.core.business_date import business_today
from app.db.session import get_db
from app.models import (
    Attachment,
    ContractTerm,
    Employee,
    Invoice,
    Project,
    ProjectBaseline,
    ProjectIssue,
    ProjectMilestone,
    ProjectReport,
    ProjectTask,
    ProjectTaskDependency,
    TimesheetEntry,
)
from app.schemas import (
    CreateProjectBaselineRequest,
    CreateProjectIssueRequest,
    CreateProjectMilestoneRequest,
    CreateProjectReportRequest,
    CreateProjectTaskDependencyRequest,
    CreateProjectTaskRequest,
    ProjectBaselineEnvelope,
    ProjectBaselineListEnvelope,
    ProjectBaselineRead,
    ProjectIssueEnvelope,
    ProjectIssueListEnvelope,
    ProjectIssueRead,
    ProjectMilestoneEnvelope,
    ProjectMilestoneListEnvelope,
    ProjectMilestoneRead,
    ProjectReportEnvelope,
    ProjectReportListEnvelope,
    ProjectReportRead,
    ProjectTaskDependencyEnvelope,
    ProjectTaskDependencyListEnvelope,
    ProjectTaskDependencyRead,
    ProjectTaskEnvelope,
    ProjectTaskListEnvelope,
    ProjectTaskRead,
    ReachProjectMilestoneRequest,
    UpdateProjectIssueRequest,
    UpdateProjectMilestoneRequest,
    UpdateProjectReportRequest,
    UpdateProjectTaskRequest,
)
from app.services import project_work as work
from app.services.audit import record_audit
from app.services.state_machines import counted_states
from app.services.type_options import require_type_option

router = APIRouter()

_422 = status.HTTP_422_UNPROCESSABLE_CONTENT
_409 = status.HTTP_409_CONFLICT
# what a member states on a task assigned to them; the plan is the manager's
CONTRIBUTED_FIELDS = frozenset({"actual_start", "actual_end", "status"})


def _task_read(task: ProjectTask) -> dict:
    return ProjectTaskRead.model_validate(task).model_dump(by_alias=True)


def _check_task_fields(db: Session, tenant_id: str, fields: dict) -> None:
    if fields.get("assignee_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, fields["assignee_employee_id"])
    if fields.get("status") is not None:
        require_type_option(db, tenant_id, "project_task_status", fields["status"])


# --- tasks ------------------------------------------------------------------------


@router.post("/project-tasks", response_model=ProjectTaskEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_project_task(payload: CreateProjectTaskRequest, actor: Annotated[Actor, Depends(get_actor)],
                        db: Annotated[Session, Depends(get_db)]):
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    fields = payload.model_dump()
    _check_task_fields(db, tenant_id, fields)
    task = ProjectTask(tenant_id=tenant_id, **fields)
    work.check_parent(db, task)
    db.add(task)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, f"task_code {payload.task_code!r} is taken in this project")
    record_audit(db, tenant_id=tenant_id, action="project.task_added", entity_type="project",
                 entity_id=task.project_id, actor=actor.label, detail={"task_id": task.id, "name": task.name})
    db.commit()
    db.refresh(task)
    return envelope(_task_read(task))


@router.patch("/project-tasks/{task_id}", response_model=ProjectTaskEnvelope, response_model_exclude_unset=True)
def update_project_task(task_id: str, payload: UpdateProjectTaskRequest, actor: Annotated[Actor, Depends(get_actor)],
                        db: Annotated[Session, Depends(get_db)]):
    """Re-plan a task (`project.manage`), or — for the person it is assigned
    to, with `project.contribute` — state its actual dates and status."""
    tenant_id = actor.tenant_id
    task = get_scoped_or_404(db, ProjectTask, tenant_id, task_id)
    updates = payload.model_dump(exclude_unset=True)
    if not has_permission(actor, "project.manage"):
        require_permission(actor, "project.contribute")
        if task.assignee_employee_id is None or task.assignee_employee_id != actor.employee_id:
            work.refuse(status.HTTP_403_FORBIDDEN, "a task is updated by the person it is assigned to, "
                                                   "or by whoever manages the project")
        planned = sorted(set(updates) - CONTRIBUTED_FIELDS)
        if planned:
            work.refuse(status.HTTP_403_FORBIDDEN, f"{', '.join(planned)} are the project's plan — "
                                                   "the project manager changes them")
    _check_task_fields(db, tenant_id, updates)
    for field, value in updates.items():
        setattr(task, field, value)
    if "parent_task_id" in updates:
        work.check_parent(db, task)
    record_audit(db, tenant_id=tenant_id, action="project.task_changed", entity_type="project",
                 entity_id=task.project_id, actor=actor.label,
                 detail={"task_id": task.id, "fields": sorted(updates)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, f"task_code {updates.get('task_code')!r} is taken in this project")
    db.refresh(task)
    return envelope(_task_read(task))


@router.delete("/project-tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_task(task_id: str, actor: Annotated[Actor, Depends(get_actor)],
                        db: Annotated[Session, Depends(get_db)]):
    """Remove a task nothing points at. One with sub-tasks, dependencies or
    recorded hours is history: set its status to `cancelled` instead."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    task = get_scoped_or_404(db, ProjectTask, tenant_id, task_id)
    held = []
    if db.scalar(select(ProjectTask.id).where(ProjectTask.parent_task_id == task.id).limit(1)):
        held.append("sub-tasks")
    if db.scalar(select(ProjectTaskDependency.id).where(or_(
            ProjectTaskDependency.predecessor_task_id == task.id,
            ProjectTaskDependency.successor_task_id == task.id)).limit(1)):
        held.append("dependencies")
    if db.scalar(select(TimesheetEntry.id).where(TimesheetEntry.task_id == task.id).limit(1)):
        held.append("recorded hours")
    if held:
        work.refuse(_409, f"this task has {', '.join(held)} — set its status to cancelled rather than delete it")
    record_audit(db, tenant_id=tenant_id, action="project.task_removed", entity_type="project",
                 entity_id=task.project_id, actor=actor.label, detail={"task_id": task.id, "name": task.name})
    db.delete(task)
    db.commit()


@router.get("/project-tasks", response_model=ProjectTaskListEnvelope, response_model_exclude_unset=True)
def list_project_tasks(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    parent_task_id: str | None = None,
    assignee_employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectTask, ranges=('created_at', 'planned_start', 'planned_end', 'actual_start', 'actual_end')))] = None,
):
    """A project's tasks in plan order; `assignee_employee_id` is one person's."""
    return list_rows(
        db, select(ProjectTask).where(ProjectTask.tenant_id == actor.tenant_id),
        filters={ProjectTask.project_id: project_id, ProjectTask.parent_task_id: parent_task_id,
                 ProjectTask.assignee_employee_id: assignee_employee_id, ProjectTask.status: status_filter},
        keyword=keyword,
        keyword_columns=(cast(ProjectTask.id, String), ProjectTask.task_code, ProjectTask.name),
        order_by=(ProjectTask.sort_order.asc().nulls_last(), ProjectTask.task_code.asc(), ProjectTask.created_at.asc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra, read_model=ProjectTaskRead,
    )


@router.get("/project-tasks/{task_id}", response_model=ProjectTaskEnvelope, response_model_exclude_unset=True)
def get_project_task(task_id: str, actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    return envelope(_task_read(get_scoped_or_404(db, ProjectTask, actor.tenant_id, task_id)))


# --- dependencies -----------------------------------------------------------------


@router.post("/project-task-dependencies", response_model=ProjectTaskDependencyEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_project_task_dependency(payload: CreateProjectTaskDependencyRequest,
                                   actor: Annotated[Actor, Depends(get_actor)],
                                   db: Annotated[Session, Depends(get_db)]):
    """One task waits on another. Nothing reschedules on it: the dates are
    the plan's, and the agent proposes moves."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    if payload.predecessor_task_id == payload.successor_task_id:
        work.refuse(_422, "a task does not wait on itself")
    predecessor = get_scoped_or_404(db, ProjectTask, tenant_id, payload.predecessor_task_id)
    successor = get_scoped_or_404(db, ProjectTask, tenant_id, payload.successor_task_id)
    work.check_dependency(db, predecessor, successor)
    dependency = ProjectTaskDependency(tenant_id=tenant_id, **payload.model_dump())
    db.add(dependency)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, "these two tasks are already joined")
    record_audit(db, tenant_id=tenant_id, action="project.dependency_added", entity_type="project",
                 entity_id=predecessor.project_id, actor=actor.label,
                 detail={"predecessor_task_id": predecessor.id, "successor_task_id": successor.id,
                         "dependency_type": dependency.dependency_type})
    db.commit()
    db.refresh(dependency)
    return envelope(ProjectTaskDependencyRead.model_validate(dependency).model_dump(by_alias=True))


@router.delete("/project-task-dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_task_dependency(dependency_id: str, actor: Annotated[Actor, Depends(get_actor)],
                                   db: Annotated[Session, Depends(get_db)]):
    require_permission(actor, "project.manage")
    dependency = get_scoped_or_404(db, ProjectTaskDependency, actor.tenant_id, dependency_id)
    predecessor = db.get(ProjectTask, dependency.predecessor_task_id)
    record_audit(db, tenant_id=actor.tenant_id, action="project.dependency_removed", entity_type="project",
                 entity_id=predecessor.project_id, actor=actor.label,
                 detail={"predecessor_task_id": dependency.predecessor_task_id,
                         "successor_task_id": dependency.successor_task_id})
    db.delete(dependency)
    db.commit()


@router.get("/project-task-dependencies", response_model=ProjectTaskDependencyListEnvelope,
            response_model_exclude_unset=True)
def list_project_task_dependencies(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    task_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectTaskDependency, ranges=('created_at',)))] = None,
):
    """A project's dependencies, or the ones a task takes part in."""
    stmt = select(ProjectTaskDependency).where(ProjectTaskDependency.tenant_id == actor.tenant_id)
    if project_id:
        before = aliased(ProjectTask)
        stmt = stmt.join(before, before.id == ProjectTaskDependency.predecessor_task_id).where(
            before.project_id == project_id)
    if task_id:
        stmt = stmt.where(or_(ProjectTaskDependency.predecessor_task_id == task_id,
                              ProjectTaskDependency.successor_task_id == task_id))
    return list_rows(db, stmt, order_by=(ProjectTaskDependency.created_at.asc(), ProjectTaskDependency.id.asc()),
                     pagination=requested_pagination(page, size), sort=order_by, extra=extra,
                     read_model=ProjectTaskDependencyRead)


# --- milestones -------------------------------------------------------------------


def _milestone_read(milestone: ProjectMilestone) -> dict:
    return ProjectMilestoneRead.model_validate(milestone).model_dump(by_alias=True)


def _check_links(db: Session, tenant_id: str, project: Project, fields: dict) -> None:
    """The clause that pays on a milestone is one of the project's contract;
    the invoice that billed it names the project."""
    if fields.get("contract_term_id"):
        term = get_scoped_or_404(db, ContractTerm, tenant_id, fields["contract_term_id"])
        if project.contract_id is None or term.contract_id != project.contract_id:
            work.refuse(_422, "contract_term_id is a clause of another contract than the project's")
    if fields.get("invoice_id"):
        invoice = get_scoped_or_404(db, Invoice, tenant_id, fields["invoice_id"])
        if invoice.deleted_at is not None or invoice.project_id != project.id:
            work.refuse(_422, f"invoice {invoice.invoice_no} does not bill this project — name the project on it")


@router.post("/project-milestones", response_model=ProjectMilestoneEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_project_milestone(payload: CreateProjectMilestoneRequest, actor: Annotated[Actor, Depends(get_actor)],
                             db: Annotated[Session, Depends(get_db)]):
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    project = get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    fields = payload.model_dump()
    _check_links(db, tenant_id, project, fields)
    milestone = ProjectMilestone(tenant_id=tenant_id, status="open", **fields)
    db.add(milestone)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="project.milestone_added", entity_type="project",
                 entity_id=project.id, actor=actor.label,
                 detail={"milestone_id": milestone.id, "name": milestone.name, "due_date": str(milestone.due_date)})
    db.commit()
    db.refresh(milestone)
    return envelope(_milestone_read(milestone))


def _billed(db: Session, milestone: ProjectMilestone) -> bool:
    """Linked to an invoice that still stands: what it billed is fixed."""
    if not milestone.invoice_id:
        return False
    invoice = db.get(Invoice, milestone.invoice_id)
    return invoice is not None and invoice.deleted_at is None and \
        invoice.status in counted_states(db, milestone.tenant_id, "invoice")


@router.patch("/project-milestones/{milestone_id}", response_model=ProjectMilestoneEnvelope,
              response_model_exclude_unset=True)
def update_project_milestone(milestone_id: str, payload: UpdateProjectMilestoneRequest,
                             actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    """Rename, re-date, link the clause or the invoice, or cancel. Changing
    the due date is audited like every change; it is the plan's to change."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    milestone = get_scoped_or_404(db, ProjectMilestone, tenant_id, milestone_id)
    project = db.get(Project, milestone.project_id)
    updates = payload.model_dump(exclude_unset=True)
    _check_links(db, tenant_id, project, updates)
    if "invoice_id" in updates and updates["invoice_id"] != milestone.invoice_id and _billed(db, milestone):
        work.refuse(_409, "the invoice that billed this milestone still stands — void it before relinking")
    if updates.get("status") == "cancelled" and milestone.status == "reached":
        work.refuse(_409, "a reached milestone is not cancelled — reopen it first if it was recorded in error")
    for field, value in updates.items():
        setattr(milestone, field, value)
    record_audit(db, tenant_id=tenant_id, action="project.milestone_changed", entity_type="project",
                 entity_id=project.id, actor=actor.label,
                 detail={"milestone_id": milestone.id, "fields": sorted(updates)})
    db.commit()
    db.refresh(milestone)
    return envelope(_milestone_read(milestone))


@router.post("/project-milestones/{milestone_id}/reach", response_model=ProjectMilestoneEnvelope,
             response_model_exclude_unset=True)
def reach_project_milestone(milestone_id: str, payload: ReachProjectMilestoneRequest,
                            actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    """Record that the milestone was met: on which day, confirmed by whom,
    with what evidence. It bills nothing by itself."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    milestone = get_scoped_or_404(db, ProjectMilestone, tenant_id, milestone_id)
    if milestone.status == "cancelled":
        work.refuse(_409, "this milestone was cancelled")
    if _billed(db, milestone):
        work.refuse(_409, "an invoice billed this milestone — what was reached when is fixed while it stands")
    if payload.evidence_attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.evidence_attachment_id)
    milestone.status = "reached"
    milestone.reached_on = payload.reached_on
    milestone.confirmed_by = payload.confirmed_by or actor.label
    milestone.evidence_attachment_id = payload.evidence_attachment_id or milestone.evidence_attachment_id
    record_audit(db, tenant_id=tenant_id, action="project.milestone_reached", entity_type="project",
                 entity_id=milestone.project_id, actor=actor.label,
                 detail={"milestone_id": milestone.id, "reached_on": str(milestone.reached_on),
                         "confirmed_by": milestone.confirmed_by})
    db.commit()
    db.refresh(milestone)
    return envelope(_milestone_read(milestone))


@router.post("/project-milestones/{milestone_id}/reopen", response_model=ProjectMilestoneEnvelope,
             response_model_exclude_unset=True)
def reopen_project_milestone(milestone_id: str, actor: Annotated[Actor, Depends(get_actor)],
                             db: Annotated[Session, Depends(get_db)]):
    """Undo a reached milestone recorded in error. Refused while an invoice
    that billed it stands."""
    require_permission(actor, "project.manage")
    milestone = get_scoped_or_404(db, ProjectMilestone, actor.tenant_id, milestone_id)
    if _billed(db, milestone):
        work.refuse(_409, "an invoice billed this milestone — void it before reopening")
    milestone.status, milestone.reached_on, milestone.confirmed_by = "open", None, None
    record_audit(db, tenant_id=actor.tenant_id, action="project.milestone_reopened", entity_type="project",
                 entity_id=milestone.project_id, actor=actor.label, detail={"milestone_id": milestone.id})
    db.commit()
    db.refresh(milestone)
    return envelope(_milestone_read(milestone))


@router.get("/project-milestones", response_model=ProjectMilestoneListEnvelope, response_model_exclude_unset=True)
def list_project_milestones(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectMilestone, ranges=('created_at', 'due_date', 'reached_on')))] = None,
):
    """Milestones by due date; `due_date_thru=<today>&status=open` is what is overdue."""
    return list_rows(
        db, select(ProjectMilestone).where(ProjectMilestone.tenant_id == actor.tenant_id),
        filters={ProjectMilestone.project_id: project_id, ProjectMilestone.status: status_filter},
        order_by=(ProjectMilestone.due_date.asc(), ProjectMilestone.created_at.asc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra, read_model=ProjectMilestoneRead,
    )


@router.get("/project-milestones/{milestone_id}", response_model=ProjectMilestoneEnvelope,
            response_model_exclude_unset=True)
def get_project_milestone(milestone_id: str, actor: Annotated[Actor, Depends(get_actor)],
                          db: Annotated[Session, Depends(get_db)]):
    return envelope(_milestone_read(get_scoped_or_404(db, ProjectMilestone, actor.tenant_id, milestone_id)))


# --- issues -----------------------------------------------------------------------


def _issue_read(issue: ProjectIssue) -> dict:
    return ProjectIssueRead.model_validate(issue).model_dump(by_alias=True)


def _check_issue_fields(db: Session, tenant_id: str, project_id: str, fields: dict, current: ProjectIssue | None = None) -> None:
    for family, field in (("project_issue_type", "issue_type"), ("project_issue_severity", "severity"),
                          ("project_issue_status", "status")):
        if fields.get(field) is not None:
            require_type_option(db, tenant_id, family, fields[field])
    for field in ("raised_by_employee_id", "owner_employee_id"):
        if fields.get(field):
            get_scoped_or_404(db, Employee, tenant_id, fields[field])
    if fields.get("task_id"):
        task = get_scoped_or_404(db, ProjectTask, tenant_id, fields["task_id"])
        if task.project_id != project_id:
            work.refuse(_422, "task_id is a task of another project")
    resolved_at = fields.get("resolved_at", current.resolved_at if current else None)
    resolution = fields.get("resolution", current.resolution if current else None)
    if resolved_at is not None and not (resolution or "").strip():
        work.refuse(_422, "a resolved issue states its resolution — send resolution with resolved_at")


def _require_contributor(actor: Actor) -> bool:
    """True for whoever manages projects; otherwise `project.contribute`."""
    if has_permission(actor, "project.manage"):
        return True
    require_permission(actor, "project.contribute")
    return False


@router.post("/project-issues", response_model=ProjectIssueEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_project_issue(payload: CreateProjectIssueRequest, actor: Annotated[Actor, Depends(get_actor)],
                         db: Annotated[Session, Depends(get_db)]):
    """Log an issue, a risk, a change request or a defect. Anyone working on
    the project raises one (`project.contribute`); it is recorded as raised
    by them unless a manager names someone else."""
    manager = _require_contributor(actor)
    tenant_id = actor.tenant_id
    project = get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    fields = payload.model_dump(exclude_unset=True)
    if not manager:
        fields["raised_by_employee_id"] = actor.employee_id
    elif not fields.get("raised_by_employee_id"):
        fields["raised_by_employee_id"] = actor.employee_id
    _check_issue_fields(db, tenant_id, project.id, fields)
    if not fields.get("issue_no"):
        fields["issue_no"] = allocate_document_number(
            db, tenant_id, model=ProjectIssue, number_column=ProjectIssue.issue_no, prefix="PI-",
            lock_scope="project_issues", field="issue_no")
    fields.setdefault("issue_type", "issue")
    fields["status"] = fields.get("status") or "open"
    if fields.get("raised_at") is None:
        fields.pop("raised_at", None)
    issue = ProjectIssue(tenant_id=tenant_id, **fields)
    db.add(issue)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, f"issue_no {fields['issue_no']!r} is taken")
    record_audit(db, tenant_id=tenant_id, action="project.issue_raised", entity_type="project",
                 entity_id=project.id, actor=actor.label,
                 detail={"issue_id": issue.id, "issue_no": issue.issue_no, "issue_type": issue.issue_type})
    db.commit()
    db.refresh(issue)
    return envelope(_issue_read(issue))


@router.patch("/project-issues/{issue_id}", response_model=ProjectIssueEnvelope, response_model_exclude_unset=True)
def update_project_issue(issue_id: str, payload: UpdateProjectIssueRequest, actor: Annotated[Actor, Depends(get_actor)],
                         db: Annotated[Session, Depends(get_db)]):
    """Work an issue: its owner, severity, status, and — when resolved —
    how. A contributor changes the issues they raised or own; whoever
    manages projects changes any."""
    manager = _require_contributor(actor)
    tenant_id = actor.tenant_id
    issue = get_scoped_or_404(db, ProjectIssue, tenant_id, issue_id)
    if not manager and actor.employee_id not in {issue.raised_by_employee_id, issue.owner_employee_id} - {None}:
        work.refuse(status.HTTP_403_FORBIDDEN, "an issue is worked by the person who raised it, its owner, "
                                               "or whoever manages the project")
    updates = payload.model_dump(exclude_unset=True)
    if not manager and "raised_by_employee_id" in updates:
        work.refuse(status.HTTP_403_FORBIDDEN, "who raised an issue is recorded, not changed")
    _check_issue_fields(db, tenant_id, issue.project_id, updates, issue)
    for field, value in updates.items():
        setattr(issue, field, value)
    record_audit(db, tenant_id=tenant_id, action="project.issue_changed", entity_type="project",
                 entity_id=issue.project_id, actor=actor.label,
                 detail={"issue_id": issue.id, "issue_no": issue.issue_no, "fields": sorted(updates)})
    db.commit()
    db.refresh(issue)
    return envelope(_issue_read(issue))


@router.get("/project-issues", response_model=ProjectIssueListEnvelope, response_model_exclude_unset=True)
def list_project_issues(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    task_id: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
    owner_employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    unresolved: bool | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectIssue, ranges=('created_at', 'raised_at', 'resolved_at')))] = None,
):
    """A project's issue log, newest first; `unresolved=true` is what is still open."""
    stmt = select(ProjectIssue).where(ProjectIssue.tenant_id == actor.tenant_id)
    if unresolved is not None:
        stmt = stmt.where(ProjectIssue.resolved_at.is_(None) if unresolved else ProjectIssue.resolved_at.is_not(None))
    return list_rows(
        db, stmt,
        filters={ProjectIssue.project_id: project_id, ProjectIssue.task_id: task_id,
                 ProjectIssue.issue_type: issue_type, ProjectIssue.severity: severity,
                 ProjectIssue.owner_employee_id: owner_employee_id, ProjectIssue.status: status_filter},
        keyword=keyword,
        keyword_columns=(cast(ProjectIssue.id, String), ProjectIssue.issue_no, ProjectIssue.title),
        order_by=(ProjectIssue.raised_at.desc(), ProjectIssue.issue_no.desc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra, read_model=ProjectIssueRead,
    )


@router.get("/project-issues/{issue_id}", response_model=ProjectIssueEnvelope, response_model_exclude_unset=True)
def get_project_issue(issue_id: str, actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    return envelope(_issue_read(get_scoped_or_404(db, ProjectIssue, actor.tenant_id, issue_id)))


# --- the figures ------------------------------------------------------------------


def _money_parts(actor: Actor) -> set[str]:
    """The money parts this reader sees: all of them with `project.manage`,
    otherwise each with the grant that reads its documents."""
    if has_permission(actor, "project.manage"):
        return set(work.MONEY_PARTS)
    grants = {
        "expenses": has_permission(actor, "expense.read_all"),
        "purchase_orders": has_permission(actor, "purchase_order.read"),
        "purchase_invoices": has_permission(actor, "invoice.read", "purchase"),
        "billing": has_permission(actor, "invoice.read", "sales"),
        "book": has_permission(actor, "ledger.read"),
    }
    return {part for part, held in grants.items() if held}


@router.get("/projects/{project_id}/execution")
def get_project_execution(project_id: str, actor: Annotated[Actor, Depends(get_actor)],
                          db: Annotated[Session, Depends(get_db)], as_of: date | None = None):
    """Where the project stands, derived on every read: hours planned against
    recorded per task (summaries roll up), hours on no task, each milestone's
    standing — upcoming, overdue, reached on time or late — the issue log's
    counts, and the money per currency: expenses approved, purchase orders
    placed, purchase and sales invoices net of credit notes, the contract's
    value, and the book's lines naming the project. The money parts are
    separate figures, never summed. A part the reader may not see is left
    out and named in `withheld`."""
    project = get_scoped_or_404(db, Project, actor.tenant_id, project_id)
    figures = work.execution(db, project.id, actor.tenant_id, as_of or business_today())
    return envelope(work.visible(figures, _money_parts(actor)))


# --- status reports ---------------------------------------------------------------


def _report_read(actor: Actor, report: ProjectReport) -> dict:
    data = ProjectReportRead.model_validate(report).model_dump(by_alias=True)
    if data.get("figures") is not None:
        data["figures"] = work.visible(data["figures"], _money_parts(actor))
    return data


@router.post("/project-reports", response_model=ProjectReportEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_project_report(payload: CreateProjectReportRequest, actor: Annotated[Actor, Depends(get_actor)],
                          db: Annotated[Session, Depends(get_db)]):
    """Draft the report for a period, in the project manager's words. Any
    period: how often a project reports is the workspace's rule. A period
    already reported takes the next revision; the earlier one stays."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    project = get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    if payload.period_end < payload.period_start:
        work.refuse(_422, "period_end is before period_start")
    revision = work.next_revision(db, tenant_id, project.id, payload.period_start)
    report = ProjectReport(tenant_id=tenant_id, revision=revision, status="draft", **payload.model_dump())
    db.add(report)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, "another report for this period was filed at the same moment — read the list and retry")
    record_audit(db, tenant_id=tenant_id, action="project.report_drafted", entity_type="project",
                 entity_id=project.id, actor=actor.label,
                 detail={"report_id": report.id, "period_start": str(report.period_start), "revision": revision})
    db.commit()
    db.refresh(report)
    return envelope(_report_read(actor, report))


@router.patch("/project-reports/{report_id}", response_model=ProjectReportEnvelope, response_model_exclude_unset=True)
def update_project_report(report_id: str, payload: UpdateProjectReportRequest,
                          actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    """Edit a draft. A published report is refused: file the next revision."""
    require_permission(actor, "project.manage")
    report = get_scoped_or_404(db, ProjectReport, actor.tenant_id, report_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("period_end") is not None and updates["period_end"] < report.period_start:
        work.refuse(_422, "period_end is before period_start")
    for field, value in updates.items():
        setattr(report, field, value)
    record_audit(db, tenant_id=actor.tenant_id, action="project.report_changed", entity_type="project",
                 entity_id=report.project_id, actor=actor.label,
                 detail={"report_id": report.id, "fields": sorted(updates)})
    db.commit()
    db.refresh(report)
    return envelope(_report_read(actor, report))


@router.delete("/project-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_report(report_id: str, actor: Annotated[Actor, Depends(get_actor)],
                          db: Annotated[Session, Depends(get_db)]):
    """Discard a draft. A published report is kept."""
    require_permission(actor, "project.manage")
    report = get_scoped_or_404(db, ProjectReport, actor.tenant_id, report_id)
    record_audit(db, tenant_id=actor.tenant_id, action="project.report_discarded", entity_type="project",
                 entity_id=report.project_id, actor=actor.label,
                 detail={"report_id": report.id, "period_start": str(report.period_start)})
    db.delete(report)
    db.commit()


@router.post("/project-reports/{report_id}/publish", response_model=ProjectReportEnvelope,
             response_model_exclude_unset=True)
def publish_project_report(report_id: str, actor: Annotated[Actor, Depends(get_actor)],
                          db: Annotated[Session, Depends(get_db)]):
    """Publish the report: the project's figures as of the period's end are
    copied into it, and from here it never changes. Sending it to anyone is
    a notification the agent writes."""
    require_permission(actor, "project.manage")
    report = get_scoped_or_404(db, ProjectReport, actor.tenant_id, report_id)
    if report.status == "published":
        work.refuse(_409, "this report was already published")
    figures = work.execution(db, report.project_id, actor.tenant_id, report.period_end)
    report.figures = jsonable_encoder(figures)
    report.status = "published"
    report.published_at = datetime.now(timezone.utc)
    report.published_by = actor.label
    record_audit(db, tenant_id=actor.tenant_id, action="project.report_published", entity_type="project",
                 entity_id=report.project_id, actor=actor.label,
                 detail={"report_id": report.id, "period_start": str(report.period_start),
                         "revision": report.revision, "health": report.health})
    db.commit()
    db.refresh(report)
    return envelope(_report_read(actor, report))


@router.get("/project-reports", response_model=ProjectReportListEnvelope, response_model_exclude_unset=True)
def list_project_reports(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    health: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectReport, ranges=('created_at', 'period_start', 'period_end', 'published_at')))] = None,
):
    """A project's reports, latest period first and the latest revision of a
    period before its earlier ones — the history the agent reads trends from."""
    return list_rows(
        db, select(ProjectReport).where(ProjectReport.tenant_id == actor.tenant_id),
        filters={ProjectReport.project_id: project_id, ProjectReport.health: health,
                 ProjectReport.status: status_filter},
        order_by=(ProjectReport.period_start.desc(), ProjectReport.revision.desc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra,
        render=lambda rows: [_report_read(actor, row) for row in rows],
    )


@router.get("/project-reports/{report_id}", response_model=ProjectReportEnvelope, response_model_exclude_unset=True)
def get_project_report(report_id: str, actor: Annotated[Actor, Depends(get_actor)],
                       db: Annotated[Session, Depends(get_db)]):
    return envelope(_report_read(actor, get_scoped_or_404(db, ProjectReport, actor.tenant_id, report_id)))


# --- baselines --------------------------------------------------------------------


@router.post("/project-baselines", response_model=ProjectBaselineEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_project_baseline(payload: CreateProjectBaselineRequest, actor: Annotated[Actor, Depends(get_actor)],
                            db: Annotated[Session, Depends(get_db)]):
    """Freeze the plan as it stands: every task's planned dates and hours and
    every milestone's due date. It never changes; a re-plan the manager
    accepts is the next baseline."""
    require_permission(actor, "project.manage")
    tenant_id = actor.tenant_id
    project = get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    plan = work.snapshot(db, tenant_id, project.id)
    if not plan["tasks"] and not plan["milestones"]:
        work.refuse(_422, "this project has no tasks or milestones to baseline yet")
    baseline = ProjectBaseline(tenant_id=tenant_id, project_id=project.id, name=payload.name, note=payload.note,
                               baseline_no=work.next_baseline_no(db, tenant_id, project.id), snapshot=plan,
                               captured_by=actor.label)
    db.add(baseline)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        work.refuse(_409, "another baseline was captured at the same moment — read the list and retry")
    record_audit(db, tenant_id=tenant_id, action="project.baseline_captured", entity_type="project",
                 entity_id=project.id, actor=actor.label,
                 detail={"baseline_id": baseline.id, "baseline_no": baseline.baseline_no, "name": baseline.name,
                         "tasks": len(plan["tasks"]), "milestones": len(plan["milestones"])})
    db.commit()
    db.refresh(baseline)
    return envelope(ProjectBaselineRead.model_validate(baseline).model_dump(by_alias=True))


@router.get("/project-baselines", response_model=ProjectBaselineListEnvelope, response_model_exclude_unset=True)
def list_project_baselines(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    project_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ProjectBaseline, ranges=('created_at', 'captured_at')))] = None,
):
    """A project's baselines, latest first."""
    return list_rows(
        db, select(ProjectBaseline).where(ProjectBaseline.tenant_id == actor.tenant_id),
        filters={ProjectBaseline.project_id: project_id},
        order_by=(ProjectBaseline.baseline_no.desc(), ProjectBaseline.created_at.desc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra, read_model=ProjectBaselineRead,
    )


@router.get("/project-baselines/{baseline_id}", response_model=ProjectBaselineEnvelope,
            response_model_exclude_unset=True)
def get_project_baseline(baseline_id: str, actor: Annotated[Actor, Depends(get_actor)],
                         db: Annotated[Session, Depends(get_db)]):
    return envelope(ProjectBaselineRead.model_validate(
        get_scoped_or_404(db, ProjectBaseline, actor.tenant_id, baseline_id)).model_dump(by_alias=True))


@router.get("/project-baselines/{baseline_id}/variance")
def get_project_baseline_variance(baseline_id: str, actor: Annotated[Actor, Depends(get_actor)],
                                  db: Annotated[Session, Depends(get_db)]):
    """How far today's plan has moved from this baseline, derived on read:
    per task, start and end moved by how many days, planned hours changed,
    the actual end against the baselined end, and tasks added or removed
    since; per milestone, the due date moved and the reached date against the
    baselined due date; and the plan's finish then and now. Whether a move
    matters is the manager's call."""
    baseline = get_scoped_or_404(db, ProjectBaseline, actor.tenant_id, baseline_id)
    return envelope(work.variance(db, baseline))
