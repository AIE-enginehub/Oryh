from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.browser_auth import CSRF_COOKIE, SESSION_COOKIE
from app.core.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    HOSTED_FLOW_AGENT_PERMISSIONS,
    PRINCIPAL_HOSTED_FLOW_AGENT,
    PRINCIPAL_TENANT_SERVICE,
    permissions_cover,
)
from app.core.security import hash_token
from app.db.session import bind_tenant_context, get_db
from app.models import ApiKey, FlowSubscription, Role, Tenant, User, UserSession, hash_api_key


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    kind: str  # "user" (session or user-bound key) or "service" (tenant-level key)
    role: str  # tenant role name (system: admin/member) or "service"
    user_id: str | None = None
    employee_id: str | None = None
    credential_id: str | None = None
    # permission grants of the role; a tenant's own service key bypasses checks
    permissions: frozenset[str] = frozenset()
    # Hosted flow agents only: {entity_type: queue_filter} of the enabled
    # subscriptions this key serves. None = unconstrained (people, tenant
    # service keys). The server holds business writes to this boundary —
    # the prompt-level statement of it (flow_runner) is UX, this is the wall.
    write_scope: dict | None = None
    # service actors only: whose machine holds the key (core/permissions.py)
    principal_kind: str = PRINCIPAL_TENANT_SERVICE

    @property
    def label(self) -> str:
        if self.kind == "user":
            return f"user:{self.user_id}"
        return f"key:{self.credential_id}"

    @property
    def bypasses_permissions(self) -> bool:
        """A tenant's own service key has never been permission-checked: the
        tenant issued it to itself, and it is the recovery credential of last
        resort. A principal held by anyone else — today ORYH's hosted flow
        agent — carries grants like every other actor, so what it may do is
        enumerable rather than a matter of trust."""
        return self.kind == "service" and self.principal_kind == PRINCIPAL_TENANT_SERVICE


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes for DateTime(timezone=True) columns.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _ensure_tenant_active(db: Session, tenant_id: str) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant is suspended")


def _load_role_permissions(db: Session, tenant_id: str, role_name: str) -> frozenset[str]:
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name))
    if role is not None:
        return frozenset(role.permissions_jsonb)
    # legacy tenants before role provisioning: shipped defaults
    return frozenset(DEFAULT_ROLE_PERMISSIONS.get(role_name, ()))


def _actor_from_user(db: Session, user: User, credential_id: str) -> Actor:
    return Actor(
        tenant_id=user.tenant_id,
        kind="user",
        role=user.role,
        user_id=user.id,
        employee_id=user.employee_id,
        credential_id=credential_id,
        permissions=_load_role_permissions(db, user.tenant_id, user.role),
    )


def _resolve_session_actor(db: Session, token: str) -> Actor:
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )
    if session is None or _as_utc(session.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session")
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is not active")
    _ensure_tenant_active(db, user.tenant_id)
    bind_tenant_context(db, user.tenant_id)
    return _actor_from_user(db, user, session.id)


def _resolve_api_key_actor(db: Session, api_key_value: str) -> Actor:
    api_key = db.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key_value), ApiKey.is_active.is_(True))
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    _ensure_tenant_active(db, api_key.tenant_id)
    bind_tenant_context(db, api_key.tenant_id)
    if api_key.user_id is None:
        principal_kind = api_key.principal_kind or PRINCIPAL_TENANT_SERVICE
        write_scope = None
        if principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT:
            # the boundary the tenant actually enrolled in: writes outside it
            # are refused even if the model talks itself into them
            write_scope = {
                row.entity_type: dict(row.queue_filter or {})
                for row in db.scalars(
                    select(FlowSubscription).where(
                        FlowSubscription.tenant_id == api_key.tenant_id,
                        FlowSubscription.api_key_id == api_key.id,
                        FlowSubscription.enabled.is_(True),
                    )
                )
            }
        return Actor(
            tenant_id=api_key.tenant_id,
            kind="service",
            role=api_key.role or "service",
            credential_id=api_key.id,
            principal_kind=principal_kind,
            # A hosted principal's grants are fixed by the platform, not read
            # from a tenant Role row: it is the contract between ORYH and the
            # customer, not one of the tenant's own tuning knobs.
            permissions=(
                frozenset(HOSTED_FLOW_AGENT_PERMISSIONS)
                if principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT
                else frozenset()
            ),
            write_scope=write_scope,
        )
    user = db.get(User, api_key.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key owner is not active")
    return _actor_from_user(db, user, api_key.id)


def get_actor(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Actor:
    if authorization and authorization.lower().startswith("bearer "):
        return _resolve_session_actor(db, authorization[7:].strip())
    if x_api_key:
        return _resolve_api_key_actor(db, x_api_key)
    if session_token:
        actor = _resolve_session_actor(db, session_token)
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            if csrf_cookie is None or csrf_header is None or not hmac.compare_digest(
                csrf_cookie.encode("utf-8"), csrf_header.encode("utf-8")
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="missing or invalid CSRF token",
                )
        return actor
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="X-API-Key header, Authorization bearer token, or browser session cookie is required",
    )


def get_user_key_actor(
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Actor:
    """Self-service endpoints for a person's local agent: only a user-bound
    API key (the credential embedded in skill bundles) is accepted — a browser
    session must not mint a long-lived credential file."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )
    actor = _resolve_api_key_actor(db, x_api_key)
    if actor.kind != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="a user-bound API key is required",
        )
    return actor


def get_api_key_actor(
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Actor:
    """Any API key — user-bound or the tenant service key — but never a
    browser session.

    The flow agent runs on the tenant service key by design: it acts for the
    company, not a person, so its audit label must stay `key:<id>` rather than
    borrowing some admin who did not do the work. That agent needs its own
    skills, and a service key holds no less than it could already read —
    `GET /skills/{ref}/files/{path}` serves full skill content to any
    authenticated actor — so refusing it a rendered bundle protected nothing
    and only broke the documented deployment."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )
    return _resolve_api_key_actor(db, x_api_key)


def has_permission(actor: Actor, verb: str, scope: str | None = None) -> bool:
    if actor.bypasses_permissions:
        return True
    return permissions_cover(actor.permissions, verb, scope)


def require_permission(actor: Actor, verb: str, scope: str | None = None) -> None:
    if not has_permission(actor, verb, scope):
        target = f"{verb}:{scope}" if scope else verb
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"requires capability {target}",
        )


def require_roles(actor: Actor, *roles: str) -> None:
    # legacy shim: admin/service gates now mean the management capability set
    if actor.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"requires one of roles: {', '.join(roles)}",
        )


def attributed(actor: Actor, provided: str | None) -> str | None:
    """Server-side actor attribution for *_by fields: user-kind actors are
    always recorded as themselves; a tenant's own service key may attribute
    explicitly (backward-compatible multi-principal agent behavior) and falls
    back to its key label.

    A hosted principal may never attribute: ORYH operates it inside a customer's
    tenant, and a supplier that can sign a write as one of the customer's people
    is not auditable. Its writes are always `key:<id>`, which resolves to the
    hosted display name."""
    if actor.kind == "user" or actor.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT:
        return actor.label
    return provided if provided is not None else actor.label


def enforce_member_employee(actor: Actor, employee_id: str | None) -> None:
    """Actors without tenant.act_for_any_employee may only act on records
    belonging to their own linked employee."""
    if actor.kind == "user" and not has_permission(actor, "tenant.act_for_any_employee"):
        if actor.employee_id is None or actor.employee_id != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="this credential can only act on its own employee records",
            )
