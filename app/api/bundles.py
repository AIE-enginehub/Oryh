from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor, get_api_key_actor, get_user_key_actor, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import ApiKey, Role, Tenant, User, generate_api_key, hash_api_key
from app.services.audit import record_audit
from app.api.roles import get_role_or_404
from app.schemas import SkillReachEntry, SkillReachEnvelope, SkillReachRead
from app.services.bundles import (
    BundleFor,
    SkillReach,
    service_permissions,
    build_bundle_zip,
    build_connect_skill_zip,
    bundle_identity,
    eligible_skills,
    install_dir,
    role_permissions,
    skill_name_map,
    skill_reach,
    skills_manifest,
    tenant_slug,
)

router = APIRouter()


def skill_bundle_user_for_update(tenant_id: str, user_id: str):
    """Build the row-locking lookup used to serialize credential rotation."""
    return (
        select(User)
        .where(User.id == user_id, User.tenant_id == tenant_id)
        .with_for_update()
    )


@router.get("/connect-skill")
def download_connect_skill():
    """Public, credential-free download of the connect bootstrap skill — the
    only skill that needs no prior key, so anyone can fetch it and hand it to
    their local agent to start the device flow. Identical for every requester;
    no auth, no tenant context. Named for the environment's skill brand."""
    zip_bytes = build_connect_skill_zip()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{settings.skill_brand}-connect.zip"'
        },
    )


@router.get("/my/skills/manifest")
def my_skills_manifest(
    actor: Annotated[Actor, Depends(get_user_key_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """What the calling agent's principal is currently entitled to: name,
    version, and content hash per eligible skill. A local agent compares this
    against its installed manifest.json to decide whether to re-sync — also
    surfaces skills gained/lost through role changes.

    `meta` carries the same identity block the installed manifest holds, so an
    agent serving two employers knows which directory this answer is about, and
    a company that renamed itself still reaches the copies on people's laptops
    (the per-skill hashes cover templates only, and would not move)."""
    tenant = db.get(Tenant, actor.tenant_id)
    skills = eligible_skills(
        db, actor.tenant_id, actor.permissions, user_id=actor.user_id, role=actor.role
    )
    # the same name_map the zip lays out under, so installed_as here matches the
    # directory the agent installed and sync compares cleanly
    name_map = skill_name_map(db, actor.tenant_id, tenant_slug(tenant))
    data = skills_manifest(skills, name_map)
    return {"data": data, "meta": {"total": len(data), **bundle_identity(tenant)}}


@router.get("/my/skill-bundle")
def my_skill_bundle(
    actor: Annotated[Actor, Depends(get_api_key_actor)],
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
):
    """Self-service bundle refresh for a local agent: re-render the caller's
    eligible skills using the key it presented — the caller already holds the
    plaintext, so nothing is rotated and other devices keep working. Admin
    issuance (POST /users/{id}/skill-bundle) remains the way to mint or
    revoke credentials.

    A tenant service key gets the tenant's bundle. That is how the workflow
    admin agent is deployed — it acts for the company, not a person, so its
    writes must stay attributable to `key:<id>` rather than borrowing an
    admin who did not do the work."""
    if actor.kind == "user":
        holder = db.get(User, actor.user_id)
        filename_stem = holder.email.split("@")[0]
        tenant_id = holder.tenant_id
    else:
        key = db.get(ApiKey, actor.credential_id)
        holder = BundleFor.tenant_service(actor.tenant_id, (key.label if key else None) or "service")
        filename_stem = "service"
        tenant_id = actor.tenant_id
    # Only a bypassing principal gets the "everything" stand-in: a hosted flow
    # agent carries real grants, so its bundle is filtered by them and it never
    # receives, say, the access-admin skill it could not execute anyway.
    permissions = service_permissions() if actor.bypasses_permissions else actor.permissions
    zip_bytes, skill_names = build_bundle_zip(
        db, user=holder, permissions=permissions, api_key_plaintext=x_api_key
    )
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="skill_bundle.synced",
        entity_type="user" if actor.kind == "user" else "tenant",
        entity_id=actor.user_id or actor.tenant_id,
        actor=actor.label,
        detail={"skills": skill_names, "key_id": actor.credential_id},
    )
    db.commit()

    filename = f"{install_dir(tenant_slug(db.get(Tenant, tenant_id)))}-{filename_stem}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


def reach_read(
    reaches: list[SkillReach],
    *,
    subject_type: str,
    subject_id: str,
    subject_label: str,
    role: str | None,
) -> SkillReachRead:
    entries = [
        SkillReachEntry(
            name=item.skill.name,
            title=item.skill.title,
            description=item.skill.description,
            kind=item.skill.kind,
            required_capability=item.skill.required_capability,
            distribution_mode=item.skill.distribution_mode,
            received=item.received,
            reasons=list(item.reasons),
            named_via=list(item.named_via),
            granted_by_roles=list(item.granted_by_roles),
        )
        for item in reaches
    ]
    return SkillReachRead(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_label=subject_label,
        role=role,
        received=[entry for entry in entries if entry.received],
        withheld=[entry for entry in entries if not entry.received],
    )


def user_reach(db: Session, tenant_id: str, user: User) -> SkillReachRead:
    roles = role_permissions(db, tenant_id)
    reaches = skill_reach(
        db,
        tenant_id,
        roles.get(user.role, frozenset()),
        user_id=user.id,
        role=user.role,
        roles=roles,
    )
    return reach_read(
        reaches,
        subject_type="user",
        subject_id=user.id,
        subject_label=user.name or user.email,
        role=user.role,
    )


@router.get(
    "/my/skills/reach",
    response_model=SkillReachEnvelope,
    response_model_exclude_unset=True,
)
def my_skill_reach(
    actor: Annotated[Actor, Depends(get_user_key_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Why the calling agent has the skills it has — and, the half that matters,
    why it does not have the others.

    The manifest answers "what do I have". When a person asks their agent "why
    don't you have the purchase skill", the agent had no way to answer beyond
    guessing; this endpoint names every reason that applies, so the person can
    ask their admin for the whole fix rather than half of it.

    `granted_by_roles` is context, not a recommendation — those roles are
    frequently more privileged than the caller, and "ask to be made one of
    them" is an escalation, not a fix. No permission gate: it reveals nothing
    about anyone else, and the
    skill catalog is already readable tenant-wide as the agent's trigger index.
    """
    user = db.get(User, actor.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"data": user_reach(db, actor.tenant_id, user).model_dump(), "meta": {}}


@router.get(
    "/users/{user_id}/skills",
    response_model=SkillReachEnvelope,
    response_model_exclude_unset=True,
)
def user_skill_reach(
    user_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """What this person's next sync would install, and what it would not."""
    require_permission(actor, "users.manage")
    user = db.scalar(select(User).where(User.id == user_id, User.tenant_id == actor.tenant_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"data": user_reach(db, actor.tenant_id, user).model_dump(), "meta": {}}


@router.get(
    "/roles/{role_ref}/skills",
    response_model=SkillReachEnvelope,
    response_model_exclude_unset=True,
)
def role_skill_reach(
    role_ref: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """What everyone holding this role receives, before anyone is hired into it.

    Answered for the role itself, so a skill targeted at named individuals who
    happen to hold this role reads as `not_in_audience` here — correct, because
    the next person given this role would not get it. Their personal view is
    where that individual grant shows up.
    """
    require_permission(actor, "users.manage")
    role = get_role_or_404(db, actor.tenant_id, role_ref)
    roles = role_permissions(db, actor.tenant_id)
    reaches = skill_reach(
        db,
        actor.tenant_id,
        roles.get(role.name, frozenset()),
        role=role.name,
        roles=roles,
    )
    data = reach_read(
        reaches,
        subject_type="role",
        subject_id=role.name,
        subject_label=role.title or role.name,
        role=role.name,
    )
    return {"data": data.model_dump(), "meta": {}}


@router.post("/users/{user_id}/skill-bundle")
def generate_skill_bundle(
    user_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Generate the user's personal skill bundle: rotate their user-bound API
    key (previous keys are deactivated — old bundles die immediately), render
    every skill their role's capabilities cover, and stream a zip. Nothing
    rendered is stored server-side."""
    require_permission(actor, "users.manage")
    require_permission(actor, "keys.manage")
    # Serialize the complete read-disable-create rotation for this principal.
    # PostgreSQL row locks also cover the first bundle issuance because the
    # user row already exists; SQLite accepts the clause as a test-compatible
    # no-op. A second concurrent issuance waits, then revokes the first one's
    # newly-created key before minting its own.
    user = db.scalar(skill_bundle_user_for_update(actor.tenant_id, user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is not active")

    role = db.scalar(select(Role).where(Role.tenant_id == actor.tenant_id, Role.name == user.role))
    permissions = frozenset(role.permissions_jsonb) if role else frozenset()

    # rotation: one live personal key per user
    old_keys = db.scalars(
        select(ApiKey).where(
            ApiKey.tenant_id == actor.tenant_id,
            ApiKey.user_id == user.id,
            ApiKey.is_active.is_(True),
        )
    ).all()
    for old in old_keys:
        old.is_active = False
    plaintext = generate_api_key()
    new_key = ApiKey(
        tenant_id=actor.tenant_id,
        key_hash=hash_api_key(plaintext),
        label="skill-bundle",
        user_id=user.id,
        role=user.role,
        is_active=True,
    )
    db.add(new_key)
    db.flush()

    zip_bytes, skill_names = build_bundle_zip(
        db, user=user, permissions=permissions, api_key_plaintext=plaintext
    )
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="skill_bundle.issued",
        entity_type="user",
        entity_id=user.id,
        actor=actor.label,
        detail={
            "skills": skill_names,
            "new_key_id": new_key.id,
            "rotated_key_ids": [k.id for k in old_keys],
        },
    )
    db.commit()

    filename = f"{install_dir(tenant_slug(db.get(Tenant, user.tenant_id)))}-{user.email.split('@')[0]}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )
