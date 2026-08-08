from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Actor, attributed, get_actor, require_permission
from app.api.roles import custom_capability_names
from app.db.session import get_db
from app.core.permissions import validate_permission_grammar
from app.models import Role, TenantSkill, TenantSkillAssignment, User
from app.schemas import (
    CreateSkillAssignmentRequest,
    CreateTenantSkillRequest,
    SkillAssignmentEnvelope,
    SkillAssignmentRead,
    SkillAudienceEnvelope,
    SkillAudienceImpact,
    SkillAudienceRead,
    SkillAudienceSummary,
    TenantSkillEnvelope,
    TenantSkillListEnvelope,
    TenantSkillRead,
    TenantSkillSummary,
    UpdateTenantSkillRequest,
)
from app.services.audit import record_audit
from app.services.bundles import can_run, role_permissions

router = APIRouter(prefix="/skills")

MAX_TOTAL_FILE_BYTES = 512 * 1024
MAX_FILE_COUNT = 32


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
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


def requested_pagination(page: int | None, size: int | None) -> tuple[int, int] | None:
    if page is None and size is None:
        return None
    return page or 1, size or 50


def validate_files(files: dict[str, str]) -> None:
    if "SKILL.md" not in files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="files must include SKILL.md",
        )
    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"a skill may contain at most {MAX_FILE_COUNT} files",
        )
    total = 0
    for path, content in files.items():
        if path.startswith("/") or ".." in path or "\\" in path or not path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid file path: {path!r} (relative paths only, no '..')",
            )
        total += len(content.encode("utf-8"))
    if total > MAX_TOTAL_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"skill files exceed {MAX_TOTAL_FILE_BYTES // 1024} KB total",
        )


def validate_required_capability(db: Session, tenant_id: str, name: str | None) -> None:
    """Same grammar as a role's permission grants: a bare or `verb:*`/`verb:type`
    system capability, or an exact tenant-defined custom capability. Sharing
    validate_permission_grammar keeps the two in lockstep — a skill gated on
    `business_object.write:daily_report` and a role granted the same string
    are validated (and, in capability_covers, matched) the same way."""
    if name is None:
        return
    known_custom = custom_capability_names(db, tenant_id)
    error = validate_permission_grammar(name, known_custom)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"required_capability: {error}")


def get_skill_or_404(db: Session, tenant_id: str, skill_ref: str) -> TenantSkill:
    """Look up by id first, then by name, so agents can use the stable name."""
    skill = db.get(TenantSkill, skill_ref) if len(skill_ref) == 36 else None
    if skill is None or skill.tenant_id != tenant_id:
        skill = db.scalar(
            select(TenantSkill).where(
                TenantSkill.tenant_id == tenant_id, TenantSkill.name == skill_ref
            )
        )
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TenantSkill not found")
    return skill


@router.get(
    "",
    response_model=TenantSkillListEnvelope,
    response_model_exclude_unset=True,
)
def list_skills(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[
        Literal["active", "archived", "all"] | None, Query(alias="status")
    ] = "active",
    kind: Literal["product", "custom"] | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """Skill index for agents: name + description are the trigger contract;
    fetch the full skill by name when it matches. status=all lists everything."""
    stmt = select(TenantSkill).where(TenantSkill.tenant_id == tenant_id)
    if status_filter and status_filter != "all":
        stmt = stmt.where(TenantSkill.status == status_filter)
    if kind:
        stmt = stmt.where(TenantSkill.kind == kind)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                TenantSkill.name.ilike(pattern),
                TenantSkill.title.ilike(pattern),
                TenantSkill.description.ilike(pattern),
                TenantSkill.required_capability.ilike(pattern),
            )
        )
    ordered = stmt.order_by(TenantSkill.name.asc(), TenantSkill.id.asc())

    def rendered(rows) -> list[dict]:
        # one audience read for the whole page, never one per row
        summaries = audience_summaries(db, tenant_id, [skill.id for skill in rows])
        out = []
        for skill in rows:
            summary = TenantSkillSummary.model_validate(skill)
            summary.audience = summaries.get(skill.id)
            out.append(summary.model_dump())
        return out

    pagination = requested_pagination(page, size)
    if pagination is None:
        data = rendered(db.scalars(ordered).all())
        return envelope(data, len(data))
    page_number, page_size = pagination
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    data = rendered(db.scalars(ordered.offset((page_number - 1) * page_size).limit(page_size)).all())
    return paginated_envelope(data, total=total, page=page_number, page_size=page_size)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TenantSkillEnvelope,
    response_model_exclude_unset=True,
)
def create_skill(
    payload: CreateTenantSkillRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "skills.manage")
    validate_files(payload.files)
    existing = db.scalar(
        select(TenantSkill).where(
            TenantSkill.tenant_id == actor.tenant_id, TenantSkill.name == payload.name
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a skill with this name already exists; update it instead",
        )
    validate_required_capability(db, actor.tenant_id, payload.required_capability)
    skill = TenantSkill(
        tenant_id=actor.tenant_id,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        required_capability=payload.required_capability,
        distribution_mode=payload.distribution_mode,
        files_jsonb=payload.files,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return envelope(TenantSkillRead.model_validate(skill).model_dump(by_alias=True))


@router.get(
    "/{skill_ref}",
    response_model=TenantSkillEnvelope,
    response_model_exclude_unset=True,
)
def get_skill(
    skill_ref: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    skill = get_skill_or_404(db, tenant_id, skill_ref)
    data = TenantSkillRead.model_validate(skill)
    data.audience = audience_summaries(db, tenant_id, [skill.id]).get(skill.id)
    return envelope(data.model_dump(by_alias=True))


@router.get("/{skill_ref}/files/{file_path:path}", response_class=PlainTextResponse)
def get_skill_file(
    skill_ref: str,
    file_path: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    skill = get_skill_or_404(db, tenant_id, skill_ref)
    content = skill.files_jsonb.get(file_path)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found in skill")
    return PlainTextResponse(content)


@router.patch(
    "/{skill_ref}",
    response_model=TenantSkillEnvelope,
    response_model_exclude_unset=True,
)
def update_skill(
    skill_ref: str,
    payload: UpdateTenantSkillRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "skills.manage")
    skill = get_skill_or_404(db, actor.tenant_id, skill_ref)
    updates = payload.model_dump(exclude_unset=True)
    if "required_capability" in updates:
        validate_required_capability(db, actor.tenant_id, updates["required_capability"])
    if "files" in updates:
        files = updates.pop("files")
        validate_files(files)
        if files != skill.files_jsonb:
            skill.version += 1
            if skill.kind == "product":
                # tenant edited a product skill: fork it so product-catalog
                # syncs stop overwriting the tenant's customization; a custom
                # skill has no catalog baseline to track
                skill.kind = "custom"
                skill.catalog_required_capability = None
        skill.files_jsonb = files
    for field, value in updates.items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return envelope(TenantSkillRead.model_validate(skill).model_dump(by_alias=True))


@router.delete("/{skill_ref}", status_code=status.HTTP_204_NO_CONTENT)
def archive_skill(
    skill_ref: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "skills.manage")
    skill = get_skill_or_404(db, actor.tenant_id, skill_ref)
    skill.status = "archived"
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- audience: who a skill is for -------------------------------------------


def skill_assignments(db: Session, tenant_id: str, skill_id: str) -> list[TenantSkillAssignment]:
    return list(db.scalars(
        select(TenantSkillAssignment)
        .where(
            TenantSkillAssignment.tenant_id == tenant_id,
            TenantSkillAssignment.skill_id == skill_id,
        )
        .order_by(TenantSkillAssignment.subject_type.asc(), TenantSkillAssignment.created_at.asc())
    ).all())


def audience_summaries(db: Session, tenant_id: str, skill_ids: list[str]) -> dict[str, SkillAudienceSummary]:
    """One read for a whole page of skills, so the list view never fans out."""
    if not skill_ids:
        return {}
    rows = db.scalars(
        select(TenantSkillAssignment).where(
            TenantSkillAssignment.tenant_id == tenant_id,
            TenantSkillAssignment.skill_id.in_(skill_ids),
        )
    ).all()
    summaries: dict[str, SkillAudienceSummary] = {}
    for row in rows:
        summary = summaries.setdefault(row.skill_id, SkillAudienceSummary())
        if row.subject_type == "role":
            summary.roles.append(row.subject_id)
        else:
            summary.user_count += 1
    for summary in summaries.values():
        summary.roles.sort()
    return summaries


def _tenant_people(db: Session, tenant_id: str) -> list[User]:
    return list(db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.status == "active")
    ).all())


def _label(user: User) -> str:
    return user.name or user.email


def audience_impact(
    db: Session,
    tenant_id: str,
    skill: TenantSkill,
    assignments: list[TenantSkillAssignment],
) -> SkillAudienceImpact:
    """Who reaches this skill today, who would under the current audience, and
    — the one that gets missed — who would stop receiving it.

    Nobody reports a skill they silently stopped getting, so narrowing has to
    be stated before it happens, not discovered afterwards.
    """
    people = _tenant_people(db, tenant_id)
    permissions = role_permissions(db, tenant_id)
    named_users = {a.subject_id for a in assignments if a.subject_type == "user"}
    named_roles = {a.subject_id for a in assignments if a.subject_type == "role"}

    reaches_now: list[str] = []
    would_reach: list[str] = []
    blocked: list[str] = []
    for user in people:
        grants = permissions.get(user.role, frozenset())
        runnable = can_run(skill, grants)
        named = user.id in named_users or user.role in named_roles
        # today: audience applies only if the skill is already targeted
        if runnable and (skill.distribution_mode != "targeted" or named):
            reaches_now.append(_label(user))
        if runnable and named:
            would_reach.append(_label(user))
        if named and not runnable:
            blocked.append(_label(user))

    now, later = set(reaches_now), set(would_reach)
    return SkillAudienceImpact(
        distribution_mode=skill.distribution_mode,
        reaches_now=sorted(reaches_now),
        would_reach=sorted(would_reach),
        gaining=sorted(later - now),
        losing=sorted(now - later),
        blocked=sorted(set(blocked)),
    )


def assignment_read(
    db: Session, tenant_id: str, skill: TenantSkill, row: TenantSkillAssignment
) -> SkillAssignmentRead:
    permissions = role_permissions(db, tenant_id)
    label: str | None = None
    blocked: list[str] = []
    if row.subject_type == "user":
        user = db.get(User, row.subject_id)
        if user is not None:
            label = _label(user)
            if not can_run(skill, permissions.get(user.role, frozenset())):
                blocked.append(label)
    else:
        label = row.subject_id
        for user in _tenant_people(db, tenant_id):
            if user.role == row.subject_id and not can_run(skill, permissions.get(user.role, frozenset())):
                blocked.append(_label(user))
    return SkillAssignmentRead(
        id=row.id,
        skill_id=row.skill_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        subject_label=label,
        blocked_members=sorted(set(blocked)),
        created_by=row.created_by,
        created_at=row.created_at,
    )


@router.get(
    "/{skill_ref}/assignments",
    response_model=SkillAudienceEnvelope,
    response_model_exclude_unset=True,
)
def list_skill_assignments(
    skill_ref: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """The audience, plus what it would do — read this before changing it."""
    skill = get_skill_or_404(db, tenant_id, skill_ref)
    rows = skill_assignments(db, tenant_id, skill.id)
    data = SkillAudienceRead(
        assignments=[assignment_read(db, tenant_id, skill, row) for row in rows],
        impact=audience_impact(db, tenant_id, skill, rows),
    )
    return envelope(data.model_dump())


@router.post(
    "/{skill_ref}/assignments",
    status_code=status.HTTP_201_CREATED,
    response_model=SkillAssignmentEnvelope,
    response_model_exclude_unset=True,
)
def add_skill_assignment(
    skill_ref: str,
    payload: CreateSkillAssignmentRequest,
    response: Response,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Name one more subject. Deliberately one at a time rather than a
    whole-list replace: a replace lets an agent asked to "add one person"
    send only that person and drop everyone else — the same shape as the
    workflow-definition overwrite this codebase already learned from."""
    require_permission(actor, "skills.manage")
    skill = get_skill_or_404(db, actor.tenant_id, skill_ref)
    if payload.subject_type == "user":
        subject = db.get(User, payload.subject_id)
        if subject is None or subject.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    else:
        role = db.scalar(
            select(Role).where(Role.tenant_id == actor.tenant_id, Role.name == payload.subject_id)
        )
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    existing = db.scalar(
        select(TenantSkillAssignment).where(
            TenantSkillAssignment.tenant_id == actor.tenant_id,
            TenantSkillAssignment.skill_id == skill.id,
            TenantSkillAssignment.subject_type == payload.subject_type,
            TenantSkillAssignment.subject_id == payload.subject_id,
        )
    )
    if existing is not None:
        # naming the same subject twice is the caller's intent already met
        response.status_code = status.HTTP_200_OK
        return envelope(assignment_read(db, actor.tenant_id, skill, existing).model_dump())

    row = TenantSkillAssignment(
        tenant_id=actor.tenant_id,
        skill_id=skill.id,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        created_by=attributed(actor, None),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="skill.assigned",
        entity_type="tenant_skill",
        entity_id=skill.id,
        actor=actor.label,
        detail={
            "skill": skill.name,
            "subject_type": payload.subject_type,
            "subject_id": payload.subject_id,
        },
    )
    db.commit()
    db.refresh(row)
    return envelope(assignment_read(db, actor.tenant_id, skill, row).model_dump())


@router.delete(
    "/{skill_ref}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_skill_assignment(
    skill_ref: str,
    assignment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "skills.manage")
    skill = get_skill_or_404(db, actor.tenant_id, skill_ref)
    row = db.scalar(
        select(TenantSkillAssignment).where(
            TenantSkillAssignment.tenant_id == actor.tenant_id,
            TenantSkillAssignment.skill_id == skill.id,
            TenantSkillAssignment.id == assignment_id,
        )
    )
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    detail = {
        "skill": skill.name,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
    }
    db.delete(row)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="skill.unassigned",
        entity_type="tenant_skill",
        entity_id=skill.id,
        actor=actor.label,
        detail=detail,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
