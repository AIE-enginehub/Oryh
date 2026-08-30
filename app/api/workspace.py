"""The workspace itself: its record, its keys, its vocabularies, its trail.

Split out of `routes.py`: tenant creation and read, API keys and their owners,
projects, type options, attachments, and the audit log.

What holds this together is that none of it is a business record. These are the
things a workspace has to have BEFORE the first document exists — a tenant row,
a credential to write with, a cost centre to book against, a vocabulary for the
`*_type` fields, somewhere to put a file, and a trail of who did what.

Two of them are read far more widely than they are written. `require_type_option`
lives in `common.py`, because every document write validates its `*_type` fields
against the vocabulary defined here; `attachments_for_items` likewise. Only the
CRUD is here.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.common import (
    archive_row,
    commit_or_code_conflict,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    page_only_pagination,
    requested_pagination,
    require_master_data_manage,
)
from app.api.deps import (
    Actor,
    attributed,
    get_actor,
    has_permission,
    has_permission_any_scope,
    require_permission,
)
from app.core.config import settings
from app.core.permissions import (
    HOSTED_FLOW_AGENT_DISPLAY_NAME,
    PRINCIPAL_HOSTED_FLOW_AGENT,
    PRINCIPAL_TENANT_SERVICE,
)
from app.db.session import get_db
from app.models import (
    ApiKey,
    Attachment,
    AuditLog,
    Project,
    Tenant,
    TypeOption,
    User,
    generate_api_key,
    hash_api_key,
)
from app.schemas import (
    ApiKeyEnvelope,
    ApiKeyListEnvelope,
    ApiKeyOwnerListEnvelope,
    ApiKeyOwnerRead,
    ApiKeyRead,
    AttachmentRead,
    AuditLogRead,
    CreateApiKeyEnvelope,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateAttachmentRequest,
    CreateProjectRequest,
    CreateTenantRequest,
    CreateTenantResponse,
    CreateTypeOptionRequest,
    ProjectEnvelope,
    ProjectListEnvelope,
    ProjectRead,
    TenantRead,
    TypeOptionEnvelope,
    TypeOptionListEnvelope,
    TypeOptionRead,
    UpdateApiKeyRequest,
    UpdateProjectRequest,
    UpdateTypeOptionRequest,
)
from app.services.audit import record_audit
from app.core.type_options import (
    TYPE_FAMILIES,
    system_type_names,
)
from app.services.provisioning import (
    provision_system_type_options,
    provision_tenant_defaults,
)
from app.services.tenants import create_tenant_with_api_key

router = APIRouter()


# --- the tenant record, and the credentials that write to it ----------------


def get_current_tenant(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="tenant not found for API key")
    return tenant


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: CreateTenantRequest,
    db: Annotated[Session, Depends(get_db)],
):
    # Legacy internal bootstrap path; self-service signup goes through
    # /auth/register with email verification.
    if not settings.allow_open_tenant_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="open tenant creation is disabled; register via /auth/register",
        )
    tenant, api_key, plain_text_api_key = create_tenant_with_api_key(
        db,
        tenant_name=payload.name,
        tenant_status=payload.status,
        api_key_label=payload.initial_api_key_label,
    )
    provision_tenant_defaults(db, tenant.id)
    db.commit()
    data = CreateTenantResponse(
        tenant=TenantRead.model_validate(tenant),
        api_key=ApiKeyRead.model_validate(api_key),
        plain_text_api_key=plain_text_api_key,
    )
    return envelope(data.model_dump())


@router.get("/tenant")
def get_tenant(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    return envelope(TenantRead.model_validate(tenant).model_dump())


@router.get(
    "/tenant/api-keys",
    response_model=ApiKeyListEnvelope,
    response_model_exclude_unset=True,
)
def list_api_keys(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    user_id: str | None = None,
    status_filter: Annotated[Literal["active", "inactive", "all"] | None, Query(alias="status")] = None,
    is_active: bool | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    require_permission(actor, "keys.manage")
    stmt = select(ApiKey).where(ApiKey.tenant_id == actor.tenant_id)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        matching_user_ids = select(User.id).where(
            User.tenant_id == actor.tenant_id,
            or_(User.name.ilike(pattern), User.email.ilike(pattern)),
        )
        stmt = stmt.where(
            or_(
                ApiKey.label.ilike(pattern),
                cast(ApiKey.id, String).ilike(pattern),
                ApiKey.user_id.in_(matching_user_ids),
            )
        )
    if is_active is not None:
        stmt = stmt.where(ApiKey.is_active.is_(is_active))
    elif status_filter and status_filter != "all":
        stmt = stmt.where(ApiKey.is_active.is_(status_filter == "active"))

    def render(api_keys):
        users = api_key_users(db, actor.tenant_id, api_keys)
        return [
            enriched_api_key(api_key, users.get(api_key.user_id)).model_dump()
            for api_key in api_keys
        ]

    return list_rows(
        db, stmt,
        filters={ApiKey.user_id: user_id},
        order_by=(ApiKey.created_at.desc(), ApiKey.id.desc()),
        pagination=requested_pagination(page, size),
        render=render,
    )


def api_key_users(db: Session, tenant_id: str, api_keys: list[ApiKey]) -> dict[str, User]:
    user_ids = {api_key.user_id for api_key in api_keys if api_key.user_id is not None}
    if not user_ids:
        return {}
    users = db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.id.in_(user_ids))
    ).all()
    return {user.id: user for user in users}


def ensure_label_is_not_impersonation(label: str | None) -> None:
    """Keep the hosted agent's name out of tenant-chosen labels.

    The badge itself is structural (`principal_kind`), so a look-alike label
    cannot actually forge anything. This is the cheap second line: an audit
    reader scanning a column should never have to notice a `key:` prefix to
    tell ORYH's principal from a key the tenant named after it."""
    if label and HOSTED_FLOW_AGENT_DISPLAY_NAME in label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"名称 {HOSTED_FLOW_AGENT_DISPLAY_NAME!r} 由平台保留，不能用于工作空间凭证",
        )


def enriched_api_key(api_key: ApiKey, user: User | None = None) -> ApiKeyRead:
    owner_is_active = user is not None and user.status == "active"
    effective_active = api_key.is_active and (
        api_key.user_id is None or owner_is_active
    )
    effective_role = None
    if effective_active:
        effective_role = api_key.role if api_key.user_id is None else user.role
    return ApiKeyRead.model_validate(api_key).model_copy(
        update={
            "user_name": user.name if user is not None else None,
            "user_email": user.email if user is not None else None,
            "user_status": user.status if user is not None else None,
            "effective_active": effective_active,
            "effective_role": effective_role,
        }
    )


@router.get(
    "/tenant/api-key-owners",
    response_model=ApiKeyOwnerListEnvelope,
    response_model_exclude_unset=True,
)
def list_api_key_owners(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Search active users eligible to own a user-bound API key.

    This intentionally requires ``keys.manage`` rather than ``users.manage``
    and exposes only the identity fields needed by the key-management UI.
    """
    require_permission(actor, "keys.manage")
    stmt = select(User).where(
        User.tenant_id == actor.tenant_id,
        User.status == "active",
    )
    return list_rows(
        db, stmt,
        keyword=keyword,
        keyword_columns=(User.name, User.email),
        order_by=(User.name.asc(), User.email.asc(), User.id.asc()),
        pagination=(page, size),
        read_model=ApiKeyOwnerRead, by_alias=False,
    )


@router.post(
    "/tenant/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateApiKeyEnvelope,
    response_model_exclude_unset=True,
)
def create_api_key(
    payload: CreateApiKeyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "keys.manage")
    ensure_label_is_not_impersonation(payload.label)
    key_role = "service"
    user: User | None = None
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
        if user is None or user.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is not active")
        key_role = user.role
    plain_text_api_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=actor.tenant_id,
        key_hash=hash_api_key(plain_text_api_key),
        label=payload.label,
        user_id=payload.user_id,
        role=key_role,
        # Tenants issue tenant-service keys and nothing else. The hosted
        # principal is minted by the platform (POST /admin/tenants/{id}/
        # hosted-flow-agent-key) so that "ORYH holds a key here" is always the
        # record of a platform action, never something a tenant can assert.
        principal_kind=PRINCIPAL_TENANT_SERVICE,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    data = CreateApiKeyResponse(
        api_key=enriched_api_key(api_key, user),
        plain_text_api_key=plain_text_api_key,
    )
    return envelope(data.model_dump())


@router.patch(
    "/tenant/api-keys/{api_key_id}",
    response_model=ApiKeyEnvelope,
    response_model_exclude_unset=True,
)
def update_api_key(
    api_key_id: str,
    payload: UpdateApiKeyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "keys.manage")
    api_key = get_scoped_or_404(db, ApiKey, actor.tenant_id, api_key_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_label_is_not_impersonation(updates.get("label"))
    if api_key.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT:
        # The tenant's control over ORYH's principal is exactly one lever:
        # switch it off. Renaming it would break the identity its audit entries
        # are read under, and switching it back on would restore a supplier's
        # access without the supplier — or the subscription — knowing.
        if "label" in updates:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{HOSTED_FLOW_AGENT_DISPLAY_NAME} 的名称由平台固定，不可修改",
            )
        if updates.get("is_active") is True and not api_key.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"{HOSTED_FLOW_AGENT_DISPLAY_NAME} 一经停用即为退订，"
                    "重新启用需要平台重新签发"
                ),
            )
    for field, value in updates.items():
        setattr(api_key, field, value)
    db.commit()
    db.refresh(api_key)
    user = db.get(User, api_key.user_id) if api_key.user_id is not None else None
    return envelope(enriched_api_key(api_key, user).model_dump())


# --- projects: the cost centre a timesheet or an expense books against ------


@router.get("/projects", response_model=ProjectListEnvelope, response_model_exclude_unset=True)
def list_projects(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Project).where(Project.tenant_id == tenant_id),
        filters={Project.status: status_filter},
        keyword=keyword,
        keyword_columns=(Project.project_name,),
        order_by=(Project.created_at.desc(), Project.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=ProjectRead,
    )


@router.post(
    "/projects",
    response_model=ProjectEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: CreateProjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    project = Project(
        tenant_id=actor.tenant_id,
        project_code=payload.project_code,
        project_name=payload.project_name,
        client=payload.client,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        metadata_jsonb=payload.metadata,
    )
    db.add(project)
    commit_or_code_conflict(db, project)
    db.refresh(project)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.get("/projects/{project_id}", response_model=ProjectEnvelope, response_model_exclude_unset=True)
def get_project(
    project_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    project = get_scoped_or_404(db, Project, tenant_id, project_id)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.patch("/projects/{project_id}", response_model=ProjectEnvelope, response_model_exclude_unset=True)
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    project = get_scoped_or_404(db, Project, actor.tenant_id, project_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        project.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(project, field, value)
    commit_or_code_conflict(db, project)
    db.refresh(project)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Project, project_id)


# --- type options: the tenant's vocabularies for *_type fields --------------


@router.get("/type-options", response_model=TypeOptionListEnvelope, response_model_exclude_unset=True)
def list_type_options(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    family: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
):
    if family is not None and family not in TYPE_FAMILIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown family — one of: {', '.join(sorted(TYPE_FAMILIES))}",
        )
    return list_rows(
        db, select(TypeOption).where(TypeOption.tenant_id == tenant_id),
        filters={TypeOption.family: family, TypeOption.status: status_filter},
        order_by=(TypeOption.family.asc(), TypeOption.created_at.asc(), TypeOption.id.asc()),
        pagination=None,
        read_model=TypeOptionRead,
    )


@router.post(
    "/type-options",
    status_code=status.HTTP_201_CREATED,
    response_model=TypeOptionEnvelope,
    response_model_exclude_unset=True,
)
def create_type_option(
    payload: CreateTypeOptionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Tenant-defined vocabulary entry (经销价、开票服务费…). The first
    customization materializes the shipped catalog as system rows, so the
    vocabulary the tenant now owns is complete and editable."""
    require_permission(actor, "object_types.manage")
    tenant_id = actor.tenant_id
    if payload.family not in TYPE_FAMILIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown family — one of: {', '.join(sorted(TYPE_FAMILIES))}",
        )
    if payload.name in system_type_names(payload.family):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name collides with a system value")
    provision_system_type_options(db, tenant_id)
    existing = db.scalar(
        select(TypeOption).where(
            TypeOption.tenant_id == tenant_id,
            TypeOption.family == payload.family,
            TypeOption.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="type option already exists")
    row = TypeOption(
        tenant_id=tenant_id,
        family=payload.family,
        name=payload.name,
        kind="custom",
        title=payload.title,
        description=payload.description,
        created_by=attributed(actor, None),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="type_option.created",
        entity_type="type_option",
        entity_id=row.id,
        actor=actor.label,
        detail={"family": row.family, "name": row.name, "title": row.title},
    )
    db.commit()
    db.refresh(row)
    return envelope(TypeOptionRead.model_validate(row).model_dump(by_alias=True))


@router.patch(
    "/type-options/{type_option_id}",
    response_model=TypeOptionEnvelope,
    response_model_exclude_unset=True,
)
def update_type_option(
    type_option_id: str,
    payload: UpdateTypeOptionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    row = get_scoped_or_404(db, TypeOption, actor.tenant_id, type_option_id)
    updates = payload.model_dump(exclude_unset=True)
    if row.kind == "system" and ("title" in updates or "description" in updates):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a system value's wording follows the catalog; only its status is the tenant's",
        )
    # Recorded BEFORE the writes, and only what actually moves: a business
    # vocabulary silently changing its meaning is exactly the thing nobody can
    # reconstruct later. "渠道价" being redefined is a different price in every
    # report that reads it, and until now the row's `updated_at` was the only
    # trace — no actor, no old value, no reason.
    changed = {
        field: {"from": getattr(row, field), "to": value}
        for field, value in updates.items()
        if getattr(row, field) != value
    }
    for field, value in updates.items():
        setattr(row, field, value)
    if changed:
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="type_option.updated",
            entity_type="type_option",
            entity_id=row.id,
            actor=actor.label,
            detail={"family": row.family, "name": row.name, "changed": changed},
        )
    db.commit()
    db.refresh(row)
    return envelope(TypeOptionRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/type-options/{type_option_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_type_option(
    type_option_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Archive, never delete: existing records keep whatever value they
    already carry; archiving only removes it from what NEW records may use."""
    return archive_row(
        db,
        actor,
        TypeOption,
        type_option_id,
        permission="object_types.manage",
        audit_action="type_option.archived",
        audit_entity_type="type_option",
        audit_detail=lambda row: {"family": row.family, "name": row.name},
    )


# --- the audit trail: who may sweep it, and who must name a target ----------


def require_audit_scope(
    caller: Actor, *, entity_type: str | None, entity_id: str | None, actor: str | None
) -> None:
    """Who may sweep the whole trail, and who must name what they are asking about.

    The log carries every actor's activity, including `skill_bundle.*` rows and
    the `key_id` in their detail. Ungated, a plain member could read the lot —
    while `GET /auth/users` correctly refused them the directory of the very
    people whose actions they were reading.

    Holders of `users.manage` (and service actors, which act for the company)
    keep the full sweep; it is their troubleshooting tool. Everyone else must
    scope the query, to one of:

    - their own activity (`actor=user:<self>`)
    - their own account (`entity_type=user&entity_id=<self>`)
    - one named record of any other type

    That last clause is deliberate. "What happened to this record" is the
    console's object-detail trail and the documented use in
    `$oryh-business-object`; it is the record's history, not another person's,
    and it is no wider than the read access they already have to the record.

    Refused rather than silently narrowed: a quietly filtered log reads as
    "nothing happened", which is the failure this codebase just spent a fix
    removing from status filters.
    """
    if has_permission(caller, "users.manage"):
        return
    if actor is not None and actor != caller.label:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you may only filter this log by your own actor",
        )
    own_account = entity_type == "user" and entity_id == caller.user_id
    if entity_type == "user" and not own_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you may only read your own user's audit trail",
        )
    scoped = (
        actor == caller.label
        or own_account
        or (entity_id is not None and entity_type != "user")
    )
    if not scoped:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "reading the whole audit trail requires users.manage; "
                "otherwise name what you are asking about — entity_id=<record>, "
                f"entity_type=user&entity_id=<you>, or actor={caller.label}"
            ),
        )


@router.get("/audit-logs")
def list_audit_logs(
    caller: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    before: int | None = None,
    limit: int = 100,
):
    """Read-only audit trail, newest first. For troubleshooting and
    accountability — agent coordination uses todos and state queries, not
    this endpoint. Page backwards with `before=<smallest id seen>`.

    `users.manage` reads the whole trail; everyone else names what they are
    asking about — see `require_audit_scope`."""
    require_audit_scope(caller, entity_type=entity_type, entity_id=entity_id, actor=actor)
    tenant_id = caller.tenant_id
    limit = max(1, min(limit, 500))
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if before is not None:
        stmt = stmt.where(AuditLog.id < before)
    entries = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()
    data = [AuditLogRead.model_validate(item).model_dump(by_alias=True) for item in entries]
    return envelope(data, len(data))


# --- attachments: bytes in the row, not a bucket ----------------------------


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Every capability that files an attachment-backed record. The gate below said
# "any capability that files attachment-backed records grants upload" and then
# named two of them, while EIGHT models carry `attachment_id`. So an 应收会计
# holding only `invoice.manage:sales` could raise the invoice and could set its
# `attachment_id`, but got 403 producing the id — the 发票原件 (a customer's
# PDF, a 增值税发票扫描件) had nowhere to go, on the one document family whose
# whole point is that the original is the evidence.
#
# It hid because every seeded role builds on `member_base`, which carries
# `expense.submit_own`: in a demo tenant everyone is also an expense claimant,
# so the gate passed for reasons unrelated to what they were filing. A service
# key scoped to invoice entry alone is where it bites.
#
# `test_attachment_upload_gate.py` walks the mappers and fails when a model
# grows `attachment_id` without a capability named here — the list is a fact
# about the schema, not a list anyone should have to remember to update.
ATTACHMENT_FILING_CAPABILITIES = (
    "expense.submit_own",      # ExpenseItem
    "purchase.submit_own",     # PurchaseRequestItem
    "purchase_order.manage",   # PurchaseOrderItem
    "quotation.submit_own",    # SalesQuotationItem
    "order.submit_own",        # SalesOrderItem
    "invoice.manage",          # Invoice
    "payment.record",          # Payment
    "policy.manage",           # Policy
)


@router.post("/attachments", status_code=status.HTTP_201_CREATED)
def create_attachment(
    payload: CreateAttachmentRequest,
    response: Response,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    # any capability that files attachment-backed records grants upload.
    # `_any_scope` because `invoice.manage` is scopable and the question here
    # is not which direction they bill — it is whether they file at all.
    if not any(has_permission_any_scope(actor, verb) for verb in ATTACHMENT_FILING_CAPABILITIES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "requires a capability that files attachment-backed records: "
                + ", ".join(ATTACHMENT_FILING_CAPABILITIES)
            ),
        )
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_base64 is not valid base64",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="attachment content is empty")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"attachment exceeds {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB",
        )
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(Attachment).where(Attachment.tenant_id == tenant_id, Attachment.sha256 == digest)
    )
    if existing is not None:
        # Idempotent per (tenant, sha256): the same bytes resolve to the same
        # row. **200 says reused, 201 says newly stored** — that distinction is
        # the duplicate-evidence signal, and the server is the only thing that
        # can state it honestly. Callers previously had to guess from
        # created_at, which is wrong for anything uploaded in the last few
        # minutes — exactly when a claim's receipts arrive together.
        response.status_code = status.HTTP_200_OK
        return envelope(AttachmentRead.model_validate(existing).model_dump(by_alias=True))
    attachment = Attachment(
        tenant_id=tenant_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=len(content),
        sha256=digest,
        content=content,
        uploaded_by=attributed(actor, None),
    )
    db.add(attachment)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="attachment.uploaded",
        entity_type="attachment",
        entity_id=attachment.id,
        actor=actor.label,
        detail={"filename": attachment.filename, "size_bytes": attachment.size_bytes, "sha256": digest},
    )
    db.commit()
    db.refresh(attachment)
    return envelope(AttachmentRead.model_validate(attachment).model_dump(by_alias=True))


@router.get("/attachments/{attachment_id}")
def get_attachment(
    attachment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Metadata by bare id — the administrator's route, exactly like /content.

    A filename is content in miniature ("2026-07-payslip-li.pdf"), and the
    sha256 answers "does this workspace hold these exact bytes" — neither is a
    thing holding an id entitles you to. Everyone else reads attachment
    metadata where it already rides: on the document's own /detail."""
    if not has_permission(actor, "users.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "reading an attachment by id alone is the workspace administrator's "
                "route. Attachment metadata rides the owning document's /detail — "
                "this is the wrong URL, not a missing capability"
            ),
        )
    attachment = get_scoped_or_404(db, Attachment, actor.tenant_id, attachment_id)
    return envelope(AttachmentRead.model_validate(attachment).model_dump(by_alias=True))


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(
    attachment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The bytes by id alone — the workspace administrator's route only.

    Everyone else reaches an attachment through the document that carries it:
    `GET /invoices/{id}/attachments/{attachment_id}/content` and its eight
    siblings, where the document's own visibility answers the question first.
    An attachment is never a thing you are entitled to because you hold its id.

    This route used to be tenant-scoped and nothing else, so any credential in
    the workspace could read a payslip's PDF — 工资条 is an invoice, and its
    attachment is the payslip. `tests/test_payroll_visibility.py` calls payroll
    "the first read in this API that belonging to the workspace does not
    entitle you to", and warns that a gate is only worth its least covered
    path. This was that path.

    It stays open to `users.manage` because an administrator already reads the
    whole audit trail and manages every credential — the id-based route buys
    them nothing they lack, and taking it away would leave no way to inspect an
    attachment whose referencing document was deleted.
    """
    # NOT `require_permission`, whose "requires capability users.manage" would
    # send an approver to their admin asking for administrator rights — the
    # worst possible outcome of this change, and a likelier one than it looks:
    # an approver running a skill bundle from before this release calls the old
    # URL, reads the 403, and does what it says. The message has to name the
    # route instead, because that is the actual fix.
    if not has_permission(actor, "users.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "reading an attachment by id alone is the workspace administrator's "
                "route. Fetch it through the document that carries it instead, e.g. "
                "GET /expense-claims/{claim_id}/attachments/{attachment_id}/content "
                "or /invoices/{invoice_id}/attachments/{attachment_id}/content — "
                "this is the wrong URL, not a missing capability"
            ),
        )
    tenant_id = actor.tenant_id
    attachment = get_scoped_or_404(db, Attachment, tenant_id, attachment_id)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}",
        },
    )


# --- the setup report: where this workspace stands, derived, never stored ---


@router.get("/workspace/setup-report")
def workspace_setup_report(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Everything a new administrator's agent needs to know about where this
    workspace stands — computed from live data on every call, stored nowhere.

    The report deliberately has no memory: the workspace IS the state. Every
    hand-maintained progress record in this codebase has drifted from the
    thing it recorded; a derivation cannot. That also makes the wizard built
    on it resumable by construction — steps done outside it, in any order,
    by anybody, show as done.

    Statuses are a rough shorthand; the FACTS beside them are the answer. An
    `untouched` area is a statement about data, never a to-do: whether a
    workspace uses inventory is the administrator's judgment, held in their
    agent's own context — this server does not record such decisions
    (deliberate, per the product owner: no module switches, no declared-off
    registry).

    A document family is `ready` when it is STAFFED (a person-holdable role
    with at least one active person carries its filing capability — the
    system admin role is excluded, since it holds everything by definition
    and would mark every family staffed on day one) and, where a flow
    exists to drive, DEFINED (an active workflow definition). Usage counts
    ride along as facts. Admin-gated: the report exposes the access
    topology, which the member surface deliberately does not."""
    from app.api.common import DOCUMENT_FAMILIES
    from app.core.entity_types import KIND_SPLIT_MACHINE_TYPES
    from app.core.permissions import permissions_cover_any_scope
    from app.models import (
        Customer,
        CustomerContact,
        CustomerProduct,
        Employee,
        ExternalDocumentLink,
        ExternalProductMap,
        FinAccount,
        FinAccountTrans,
        FlowSubscription,
        Product,
        Role,
        TypeOption,
        User,
        Vendor,
        WorkflowDefinition,
    )
    from app.services.provisioning import unheld_shipped_capabilities

    require_permission(actor, "users.manage")
    tenant_id = actor.tenant_id

    def count(model, *conditions) -> int:
        stmt = select(func.count()).select_from(model).where(
            model.tenant_id == tenant_id, *conditions
        )
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return db.scalar(stmt) or 0

    # --- who can act: roles, their people, and the capabilities they carry --
    roles = list(db.scalars(select(Role).where(Role.tenant_id == tenant_id)))
    users_by_role: dict[str, int] = dict(
        db.execute(
            select(User.role, func.count())
            .where(User.tenant_id == tenant_id, User.status == "active")
            .group_by(User.role)
        ).all()
    )
    person_roles = [
        r for r in roles if not (r.name == "admin" and r.is_system)
    ]

    def staffing(capability: str) -> dict:
        holder_roles = [
            r.name for r in person_roles
            if permissions_cover_any_scope(frozenset(r.permissions_jsonb or []), capability)
        ]
        holder_users = sum(users_by_role.get(name, 0) for name in holder_roles)
        return {"roles": sorted(holder_roles), "active_users": holder_users}

    definitions_by_type: dict[str, int] = dict(
        db.execute(
            select(WorkflowDefinition.object_type, func.count())
            .where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.entity_kind == "builtin",
                WorkflowDefinition.status == "active",
            )
            .group_by(WorkflowDefinition.object_type)
        ).all()
    )

    areas: dict[str, dict] = {}

    # --- organization ------------------------------------------------------
    employees = count(Employee)
    non_admin_users = sum(
        n for role, n in users_by_role.items() if role != "admin"
    )
    linked_users = db.scalar(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant_id,
            User.status == "active",
            User.employee_id.is_not(None),
        )
    ) or 0
    unheld = unheld_shipped_capabilities(db, tenant_id)
    org_facts = {
        "employees": employees,
        "active_non_admin_users": non_admin_users,
        "users_linked_to_employees": linked_users,
        "custom_roles": sum(1 for r in roles if not r.is_system),
        "capabilities_reaching_nobody": sorted(unheld),
    }
    areas["organization"] = {
        "status": (
            "ready" if employees and non_admin_users
            else "partial" if employees or non_admin_users
            else "untouched"
        ),
        "facts": org_facts,
        "next": (
            "invite people, create employees and link them, shape roles — "
            "$oryh-access-admin"
        ),
    }

    # --- master data -------------------------------------------------------
    md_facts = {
        "products": count(Product),
        "customers": count(Customer),
        "customer_contacts": count(CustomerContact),
        "customer_products": count(CustomerProduct),
        "vendors": count(Vendor),
        "custom_type_options": count(TypeOption, TypeOption.kind == "custom"),
    }
    areas["master_data"] = {
        "status": "ready" if any(
            md_facts[k] for k in ("products", "customers", "vendors")
        ) else "untouched",
        "facts": md_facts,
        "next": "import the catalog from spreadsheets — $oryh-master-data",
    }

    # --- one area per document family, derived from the registry -----------
    split_by_family: dict[str, list[str]] = {}
    for machine_type, home in KIND_SPLIT_MACHINE_TYPES.items():
        split_by_family.setdefault(home, []).append(machine_type)

    for model, family in DOCUMENT_FAMILIES.items():
        staffed = staffing(family.permission)
        machine_types = [family.object_type] + sorted(
            split_by_family.get(family.object_type, [])
        )
        defined = {
            machine_type: definitions_by_type.get(machine_type, 0) > 0
            for machine_type in machine_types
        }
        facts: dict = {
            "filing_capability": family.permission,
            "staffed_by": staffed,
            "workflow_definitions": defined,
            "documents": count(model),
        }
        if family.object_type in split_by_family:
            facts["documents"] = count(model, model.order_kind == "order")
            facts["returns"] = count(model, model.order_kind == "return")
        is_staffed = staffed["active_users"] > 0
        # a family with no advance permission (purchase orders, shipments) is
        # driven by its one functional grant; a definition is optional there
        needs_definition = family.advance_permission is not None
        if is_staffed and (defined[family.object_type] or not needs_definition):
            status_word = "ready"
        elif is_staffed or facts["documents"] or any(defined.values()):
            status_word = "partial"
        else:
            status_word = "untouched"
        areas[family.object_type] = {
            "status": status_word,
            "facts": facts,
            "next": (
                f"grant {family.permission} to a role with people in it"
                if not is_staffed
                else f"publish a workflow definition for {family.object_type}"
                if needs_definition and not defined[family.object_type]
                else "in use — nothing missing"
            ),
        }

    # --- flow driving ------------------------------------------------------
    subscriptions = list(db.scalars(
        select(FlowSubscription).where(FlowSubscription.tenant_id == tenant_id)
    ))
    areas["flow_driving"] = {
        "status": "ready" if any(s.enabled for s in subscriptions) else "untouched",
        "facts": {
            "enabled": sorted(s.entity_type for s in subscriptions if s.enabled),
            "disabled": sorted(s.entity_type for s in subscriptions if not s.enabled),
        },
        "next": "subscriptions provision automatically; switch off what your own agents drive",
    }

    # --- treasury: the cash side, split from the accounting desk ------------
    treasury_staffed = staffing("fin_account.manage")
    treasury_accounts = count(FinAccount)
    areas["treasury"] = {
        "status": (
            "ready" if treasury_staffed["active_users"] and treasury_accounts
            else "partial" if treasury_staffed["active_users"] or treasury_accounts
            else "untouched"
        ),
        "facts": {
            "filing_capability": "fin_account.manage",
            "staffed_by": treasury_staffed,
            "fin_accounts": treasury_accounts,
            "register_rows": count(FinAccountTrans),
        },
        "next": (
            "grant fin_account.manage to the cashier (钱账分离 — deliberately "
            "no shipped role carries it), then open accounts and import "
            "statements — $oryh-treasury"
        ),
    }

    # --- e-commerce (optional — only relevant when selling through platforms)
    areas["ecommerce"] = {
        "status": "ready" if (
            count(ExternalProductMap) or count(ExternalDocumentLink)
        ) else "untouched",
        "optional": True,
        "facts": {
            "channel_product_maps": count(ExternalProductMap),
            "external_document_links": count(ExternalDocumentLink),
        },
        "next": (
            "only if you sell through Tmall/JD/Amazon/mini-programs: curate "
            "the product map ($oryh-master-data), record channel orders "
            "($oryh-order-submit)"
        ),
    }

    return envelope({"areas": areas})
