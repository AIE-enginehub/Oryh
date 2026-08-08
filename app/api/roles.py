from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Actor, attributed, get_actor, require_permission
from app.core.permissions import SYSTEM_CAPABILITY_NAMES, validate_permission_grammar
from app.db.session import get_db
from app.models import Capability, ObjectTypeDefinition, Role, TenantSkill, User
from app.schemas import (
    CapabilityCatalogEnvelope,
    CapabilityEnvelope,
    CapabilityRead,
    CreateCapabilityRequest,
    CreateRoleRequest,
    RoleEnvelope,
    RoleListEnvelope,
    RoleRead,
    UpdateRoleRequest,
)
from app.services.access_guards import lock_tenant_identity, tenant_has_active_user_manager
from app.services.audit import record_audit

router = APIRouter()


def envelope(data, total: int | None = None) -> dict:
    meta: dict[str, int] = {}
    if total is not None:
        meta["total"] = total
    return {"data": data, "meta": meta}


def custom_capability_names(db: Session, tenant_id: str) -> frozenset[str]:
    return frozenset(
        db.scalars(
            select(Capability.name).where(
                Capability.tenant_id == tenant_id, Capability.kind == "custom"
            )
        )
    )


def validate_permissions(db: Session, tenant_id: str, permissions: list[str]) -> None:
    known_custom = custom_capability_names(db, tenant_id)
    for grant in permissions:
        error = validate_permission_grammar(grant, known_custom)
        if error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)


def get_role_or_404(db: Session, tenant_id: str, role_ref: str) -> Role:
    role = db.get(Role, role_ref) if len(role_ref) == 36 else None
    if role is None or role.tenant_id != tenant_id:
        role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_ref))
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


# --------------------------------------------------------------------------
# roles
# --------------------------------------------------------------------------

def role_headcounts(db: Session, tenant_id: str) -> dict[str, int]:
    """{role name: active holders} in one read, so listing roles never fans
    out — the whole point is that the number is cheap enough to always say."""
    rows = db.execute(
        select(User.role, func.count())
        .where(User.tenant_id == tenant_id, User.status == "active")
        .group_by(User.role)
    ).all()
    return {name: count for name, count in rows}


def role_read(role: Role, headcounts: dict[str, int]) -> dict:
    data = RoleRead.model_validate(role)
    data.user_count = headcounts.get(role.name, 0)
    return data.model_dump(by_alias=True)


@router.get("/roles", response_model=RoleListEnvelope, response_model_exclude_unset=True)
def list_roles(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    roles = db.scalars(
        select(Role).where(Role.tenant_id == actor.tenant_id).order_by(Role.is_system.desc(), Role.name.asc())
    ).all()
    headcounts = role_headcounts(db, actor.tenant_id)
    data = [role_read(role, headcounts) for role in roles]
    return envelope(data, len(data))


@router.post(
    "/roles",
    response_model=RoleEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_role(
    payload: CreateRoleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "users.manage")
    validate_permissions(db, actor.tenant_id, payload.permissions)
    existing = db.scalar(
        select(Role).where(Role.tenant_id == actor.tenant_id, Role.name == payload.name)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role name already exists")
    role = Role(
        tenant_id=actor.tenant_id,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        permissions_jsonb=payload.permissions,
    )
    db.add(role)
    db.flush()
    record_audit(
        db, tenant_id=actor.tenant_id, action="role.created", entity_type="role",
        entity_id=role.id, actor=actor.label, detail={"name": role.name, "permissions": payload.permissions},
    )
    db.commit()
    db.refresh(role)
    return envelope(role_read(role, role_headcounts(db, actor.tenant_id)))


@router.patch("/roles/{role_ref}", response_model=RoleEnvelope, response_model_exclude_unset=True)
def update_role(
    role_ref: str,
    payload: UpdateRoleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "users.manage")
    lock_tenant_identity(db, actor.tenant_id)
    role = get_role_or_404(db, actor.tenant_id, role_ref)
    updates = payload.model_dump(exclude_unset=True)
    if "permissions" in updates:
        permissions = updates.pop("permissions")
        validate_permissions(db, actor.tenant_id, permissions)
        if role.is_system and role.name == "admin" and "users.manage" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="the admin role must keep users.manage (lockout guard)",
            )
        if not tenant_has_active_user_manager(
            db,
            actor.tenant_id,
            role_permission_overrides={role.name: permissions},
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tenant must keep at least one active user with users.manage (lockout guard)",
            )
        # The delta, not just the result. `permissions` is a full replacement,
        # so an omitted grant and a deliberately removed one produce identical
        # rows — an agent reading the trail diagnosed a real revocation as a
        # slip and told its principal to report it as a bug. `removed` is also
        # the only way to answer "what did this change take away" for a role
        # changed for the first time, which has no prior row to diff against.
        before = frozenset(role.permissions_jsonb or ())
        after = frozenset(permissions)
        role.permissions_jsonb = permissions
        record_audit(
            db, tenant_id=actor.tenant_id, action="role.updated", entity_type="role",
            entity_id=role.id, actor=actor.label,
            detail={
                "name": role.name,
                "permissions": permissions,
                "added": sorted(after - before),
                "removed": sorted(before - after),
                # 29 of 41 people sit on the baseline role, plus every future
                # hire; the trail should say when a change reached that far
                "is_system": role.is_system,
            },
        )
    for field, value in updates.items():
        setattr(role, field, value)
    db.commit()
    db.refresh(role)
    return envelope(role_read(role, role_headcounts(db, actor.tenant_id)))


@router.delete("/roles/{role_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_ref: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "users.manage")
    role = get_role_or_404(db, actor.tenant_id, role_ref)
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="system roles cannot be deleted")
    in_use = db.scalar(
        select(User).where(User.tenant_id == actor.tenant_id, User.role == role.name)
    )
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role is assigned to users")
    db.delete(role)
    record_audit(
        db, tenant_id=actor.tenant_id, action="role.deleted", entity_type="role",
        entity_id=role.id, actor=actor.label, detail={"name": role.name},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# capabilities
# --------------------------------------------------------------------------

@router.get(
    "/capabilities",
    response_model=CapabilityCatalogEnvelope,
    response_model_exclude_unset=True,
)
def list_capabilities(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Catalog for the console matrix: system + custom rows, plus the
    tenant's object types so scopable verbs can be expanded per type."""
    capabilities = db.scalars(
        select(Capability)
        .where(Capability.tenant_id == actor.tenant_id)
        .order_by(Capability.kind.desc(), Capability.name.asc())
    ).all()
    object_types = list(
        db.scalars(
            select(ObjectTypeDefinition.object_type).where(
                ObjectTypeDefinition.tenant_id == actor.tenant_id,
                ObjectTypeDefinition.entity_kind == "business_object",
                ObjectTypeDefinition.status == "active",
            )
        )
    )
    data = {
        "capabilities": [CapabilityRead.model_validate(c).model_dump() for c in capabilities],
        "object_types": sorted(object_types),
    }
    return envelope(data)


@router.post(
    "/capabilities",
    response_model=CapabilityEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_capability(
    payload: CreateCapabilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Tenant-defined capability. Enforced at the skill-distribution and
    flow-routing layers, never at the core API — see docs."""
    require_permission(actor, "users.manage")
    if payload.name in SYSTEM_CAPABILITY_NAMES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name collides with a system capability")
    existing = db.scalar(
        select(Capability).where(Capability.tenant_id == actor.tenant_id, Capability.name == payload.name)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="capability already exists")
    capability = Capability(
        tenant_id=actor.tenant_id,
        name=payload.name,
        kind="custom",
        title=payload.title,
        description=payload.description,
        created_by=attributed(actor, None),
    )
    db.add(capability)
    db.commit()
    db.refresh(capability)
    return envelope(CapabilityRead.model_validate(capability).model_dump())


@router.delete("/capabilities/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capability(
    name: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "users.manage")
    capability = db.scalar(
        select(Capability).where(Capability.tenant_id == actor.tenant_id, Capability.name == name)
    )
    if capability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    if capability.kind == "system":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="system capabilities cannot be deleted")
    referencing_role = db.scalars(select(Role).where(Role.tenant_id == actor.tenant_id)).all()
    if any(name in role.permissions_jsonb for role in referencing_role):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="capability is granted by a role")
    referencing_skill = db.scalar(
        select(TenantSkill).where(
            TenantSkill.tenant_id == actor.tenant_id, TenantSkill.required_capability == name
        )
    )
    if referencing_skill is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="capability is required by a skill")
    db.delete(capability)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
