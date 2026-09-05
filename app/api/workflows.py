from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.common import envelope, get_tenant_id, list_rows, requested_pagination
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import BusinessObject, ObjectTypeDefinition, WorkflowDefinition
from app.schemas import (
    CreateWorkflowDefinitionRequest,
    WorkflowDefinitionEnvelope,
    WorkflowDefinitionListEnvelope,
    WorkflowDefinitionRead,
)
from app.services.audit import record_audit
from app.services.flow_subscriptions import unpark_on_new_definition
from app.services.state_machines import BUILTIN_MACHINES

router = APIRouter(prefix="/workflow-definitions")


def workflow_publish_lock_key(
    tenant_id: str,
    entity_kind: str,
    object_type: str,
    name: str,
) -> int:
    """Return a stable signed bigint for one workflow version sequence.

    Length-prefixing keeps different tuples distinct even when user-provided
    names contain separator characters. A hash collision can only serialize
    two unrelated sequences; it cannot let one sequence bypass its lock.
    """
    digest = hashlib.sha256()
    for value in (tenant_id, entity_kind, object_type, name):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)


def lock_workflow_publish_scope(
    db: Session,
    tenant_id: str,
    entity_kind: str,
    object_type: str,
    name: str,
) -> None:
    """Serialize version allocation for one workflow sequence on PostgreSQL.

    Row locks cannot protect the first publish because there is no workflow
    row yet. PostgreSQL transaction-scoped advisory locks cover both the empty
    and non-empty sequence and are released automatically on commit/rollback.
    SQLite has no equivalent and remains a no-op for the unit-test runtime.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("select pg_advisory_xact_lock(cast(:lock_key as bigint))"),
        {
            "lock_key": workflow_publish_lock_key(
                tenant_id,
                entity_kind,
                object_type,
                name,
            )
        },
    )


def validate_workflow_subject(
    db: Session,
    tenant_id: str,
    entity_kind: str,
    object_type: str,
) -> None:
    active_definition = db.scalar(
        select(ObjectTypeDefinition.id).where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == entity_kind,
            ObjectTypeDefinition.object_type == object_type,
            ObjectTypeDefinition.status == "active",
        )
    )
    if entity_kind == "builtin":
        # a workflow routes a LIFECYCLE, so the subject must be a family that
        # has one — browsable-but-machineless collections (resource bookings,
        # billing accounts) are not workflow subjects
        if object_type not in BUILTIN_MACHINES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"unknown builtin object_type {object_type!r} — "
                    f"one of {', '.join(sorted(BUILTIN_MACHINES))}"
                ),
            )
        if active_definition is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"builtin object_type {object_type!r} has no active definition",
            )
        return

    existing_object = db.scalar(
        select(BusinessObject.id)
        .where(
            BusinessObject.tenant_id == tenant_id,
            BusinessObject.object_type == object_type,
        )
        .limit(1)
    )
    if active_definition is None and existing_object is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"business object_type {object_type!r} has neither an active "
                "definition nor existing data"
            ),
        )


@router.get(
    "",
    response_model=WorkflowDefinitionListEnvelope,
    response_model_exclude_unset=True,
)
def list_workflow_definitions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entity_kind: str | None = None,
    object_type: str | None = None,
    name: str | None = None,
    history: Annotated[bool, Query()] = False,
    status_filter: Annotated[
        Literal["active", "superseded", "all"] | None, Query(alias="status")
    ] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """Active versions by default (what the flow agent should follow now);
    history=true returns every published version, newest first."""
    stmt = select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == tenant_id)
    if status_filter and status_filter != "all":
        stmt = stmt.where(WorkflowDefinition.status == status_filter)
    elif not history:
        stmt = stmt.where(WorkflowDefinition.status == "active")
    return list_rows(
        db, stmt,
        filters={
            WorkflowDefinition.entity_kind: entity_kind,
            WorkflowDefinition.object_type: object_type,
            WorkflowDefinition.name: name,
        },
        keyword=keyword,
        keyword_columns=(
            WorkflowDefinition.object_type,
            WorkflowDefinition.name,
            WorkflowDefinition.definition_text,
            WorkflowDefinition.created_by,
        ),
        order_by=(
            WorkflowDefinition.object_type.asc(),
            WorkflowDefinition.name.asc(),
            WorkflowDefinition.version.desc(),
            WorkflowDefinition.id.desc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=WorkflowDefinitionRead, by_alias=False,
    )


@router.get(
    "/{definition_id}",
    response_model=WorkflowDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def get_workflow_definition(
    definition_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Fetch any published version by id — including superseded ones, so past
    routing decisions stay traceable to the definition they were based on."""
    definition = db.get(WorkflowDefinition, definition_id)
    if definition is None or definition.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WorkflowDefinition not found")
    return envelope(WorkflowDefinitionRead.model_validate(definition).model_dump())


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def publish_workflow_definition(
    payload: CreateWorkflowDefinitionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Publishing is append-only: the new text becomes version N+1 and the
    previous active version is marked superseded. Existing versions are never
    modified or deleted."""
    require_permission(actor, "workflows.publish")
    lock_workflow_publish_scope(
        db,
        actor.tenant_id,
        payload.entity_kind,
        payload.object_type,
        payload.name,
    )
    validate_workflow_subject(
        db,
        actor.tenant_id,
        payload.entity_kind,
        payload.object_type,
    )
    current = db.scalars(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.tenant_id == actor.tenant_id,
            WorkflowDefinition.entity_kind == payload.entity_kind,
            WorkflowDefinition.object_type == payload.object_type,
            WorkflowDefinition.name == payload.name,
        )
        .order_by(WorkflowDefinition.version.desc())
    ).all()
    next_version = current[0].version + 1 if current else 1
    for previous in current:
        if previous.status == "active":
            previous.status = "superseded"
    definition = WorkflowDefinition(
        tenant_id=actor.tenant_id,
        entity_kind=payload.entity_kind,
        object_type=payload.object_type,
        name=payload.name,
        version=next_version,
        definition_text=payload.definition_text,
        status="active",
        created_by=attributed(actor, payload.created_by),
    )
    db.add(definition)
    db.flush()
    if payload.entity_kind == "builtin":
        # the family whose routing just changed gets another go at its queue
        unpark_on_new_definition(
            db, actor.tenant_id, payload.object_type, version=next_version, actor=actor.label
        )
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="workflow.published",
        entity_type="workflow_definition",
        entity_id=definition.id,
        actor=actor.label,
        detail={
            "entity_kind": payload.entity_kind,
            "object_type": payload.object_type,
            "name": payload.name,
            "version": next_version,
        },
    )
    db.commit()
    db.refresh(definition)
    return envelope(WorkflowDefinitionRead.model_validate(definition).model_dump())
