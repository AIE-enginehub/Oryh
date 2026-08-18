from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor, require_permission
from app.core.browser_auth import (
    clear_browser_auth_cookies,
    require_same_origin,
    set_csrf_cookie,
    set_session_cookie,
)
from app.core.config import settings
from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.core.request_context import resolved_base_url
from app.core.login_throttle import login_keys, throttle
from app.core.security import generate_token, hash_password, hash_token, verify_password
from app.db.session import bind_tenant_context, get_db
from app.services import interactive_keys
from app.models import (
    ApiKey,
    Employee,
    Role,
    Tenant,
    User,
    UserSession,
    hash_api_key,
)
from app.schemas import (
    TokenRefreshRequest,
    AcceptInvitationRequest,
    InvitationUserEnvelope,
    InviteUserRequest,
    LoginRequest,
    PasswordResetEmailEnvelope,
    PasswordResetRequest,
    PasswordResetRequestEnvelope,
    SessionResponse,
    UpdateUserRequest,
    UserEnvelope,
    UserListEnvelope,
    UserRead,
    UserStatus,
)
from app.services.access_guards import lock_tenant_identity, tenant_has_active_user_manager
from app.services.audit import record_audit

logger = logging.getLogger("oryh.auth")

router = APIRouter(prefix="/auth")


class BrowserLoginData(BaseModel):
    user: UserRead
    expires_at: datetime


class BrowserEnvelopeMeta(BaseModel):
    pass


class BrowserLoginEnvelope(BaseModel):
    data: BrowserLoginData
    meta: BrowserEnvelopeMeta = Field(default_factory=BrowserEnvelopeMeta)


class BrowserCsrfData(BaseModel):
    csrf_token: str


class BrowserCsrfEnvelope(BaseModel):
    data: BrowserCsrfData
    meta: BrowserEnvelopeMeta = Field(default_factory=BrowserEnvelopeMeta)


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


def invitation_user_data(user: User, token: str, *, email_sent: bool = True) -> dict:
    """Keep the historical flat User response and add the one-time URL only
    for the non-delivering console backend.

    `email_sent` is the same contract `password_reset_email_data` already
    keeps. The invitation was committed before delivery was attempted, so an
    SMTP outage used to surface as a 500 on a request that had in fact created
    the user and the token — the caller could not tell whether to retry, and
    retrying created nothing. Now the business fact is reported and delivery is
    a field: a caller that sees `email_sent: false` knows the invitation exists
    and the person did not hear about it.
    """
    data = UserRead.model_validate(user).model_dump()
    data["email_sent"] = email_sent
    if settings.email_backend == "console":
        data["invitation_url"] = f"{resolved_base_url()}/web/invitations/accept?token={token}"
    return data


def password_reset_email_data(user: User, *, email_sent: bool) -> dict:
    return {
        "user": UserRead.model_validate(user).model_dump(),
        "email_sent": email_sent,
    }


PASSWORD_RESET_REQUEST_MESSAGE = (
    "if an active account exists for this email, a password reset link has been sent"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def start_session(db: Session, user: User) -> tuple[str, UserSession]:
    token = generate_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utc_now() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    return token, session


def authenticate_user(db: Session, payload: LoginRequest, request: Request | None = None) -> User:
    """One password attempt, rate-limited per account and per source address.

    Neither login surface had any backoff: a password could be guessed as fast
    as the process would answer. `request` is optional so every existing caller
    keeps working, but a caller that omits it throttles by account only — the
    address half needs the request.
    """
    keys = login_keys(payload.email, request.client.host if request and request.client else None)
    wait = throttle.retry_after(keys)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed sign-in attempts; try again shortly",
            headers={"Retry-After": str(max(1, int(wait + 0.999)))},
        )
    user = db.scalar(select(User).where(User.email == payload.email))
    if (
        user is None
        or user.status != "active"
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        throttle.record_failure(keys)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    throttle.record_success(keys)
    return user


def ensure_role_exists(db: Session, tenant_id: str, role_name: str) -> None:
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name))
    if role is None and role_name not in DEFAULT_ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role {role_name!r} is not defined for this tenant",
        )


def get_current_user(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if actor.kind != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this endpoint requires a user credential, not a service key",
        )
    return db.get(User, actor.user_id)


@router.post("/token/refresh")
def refresh_api_key(
    payload: TokenRefreshRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Exchange a refresh token for a fresh interactive key pair.

    Unauthenticated by design — the caller's key has usually just expired; the
    refresh token IS the credential here, matched by exact hash against a
    256-bit space, which is why no throttle is needed. Rotation is in place:
    the old key stops working the moment this returns, and any bundle rendered
    with it goes stale until the agent re-syncs.
    """
    presented = hash_api_key(payload.refresh_token)
    api_key = db.scalar(
        select(ApiKey).where(ApiKey.refresh_token_hash == presented, ApiKey.is_active.is_(True))
    )
    if api_key is None:
        api_key = db.scalar(
            select(ApiKey).where(
                ApiKey.prior_refresh_token_hash == presented, ApiKey.is_active.is_(True)
            )
        )
        if api_key is not None and not interactive_keys.within_retry_grace(api_key):
            # A spent token outside the retry window means a second party holds
            # a copy. Revoke rather than guess which one is legitimate; the
            # real device reconnects through the browser, in front of a person.
            bind_tenant_context(db, api_key.tenant_id)
            db.info["audit_actor"] = f"key:{api_key.id}"
            api_key.is_active = False
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "refresh token already used — this device's key has been "
                    "revoked as a precaution; reconnect with the oryh-connect skill"
                ),
            )
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
            )
        # Within the grace window: a lost-response retry. Rotate again — the
        # pair from the response that never arrived dies with this rotation.

    tenant = db.get(Tenant, api_key.tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant is suspended")
    if api_key.user_id is not None:
        user = db.get(User, api_key.user_id)
        if user is None or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API key owner is not active"
            )

    bind_tenant_context(db, api_key.tenant_id)
    db.info["audit_actor"] = f"key:{api_key.id}"
    key_plain, refresh_plain = interactive_keys.rotate(api_key)
    db.commit()
    return envelope(
        {
            "api_key": key_plain,
            "refresh_token": refresh_plain,
            "expires_at": api_key.expires_at,
        }
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    user = authenticate_user(db, payload, request)
    session_token, session = start_session(db, user)
    db.commit()
    db.refresh(session)
    db.refresh(user)
    data = SessionResponse(
        session_token=session_token,
        expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )
    return envelope(data.model_dump())


@router.post(
    "/password-reset-email",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PasswordResetRequestEnvelope,
)
def request_self_service_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    """Send an anonymous, one-time password-reset link when eligible.

    The response is deliberately identical for unknown, disabled, and active
    accounts so the login surface cannot be used to enumerate users.
    """
    from app.services.emails import EmailDeliveryError, send_password_reset_link_email

    require_same_origin(request)
    response.headers["Cache-Control"] = "no-store"
    result = envelope({"message": PASSWORD_RESET_REQUEST_MESSAGE})

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        return result

    user_id = user.id
    tenant_id = user.tenant_id
    bind_tenant_context(db, tenant_id)
    lock_tenant_identity(db, tenant_id)
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.status != "active" or user.invitation_pending:
        return result

    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "active":
        return result

    now = utc_now()
    reset_ttl = timedelta(minutes=settings.password_reset_token_ttl_minutes)
    if user.invite_token_hash is not None and user.invite_expires_at is not None:
        last_sent_at = as_utc(user.invite_expires_at) - reset_ttl
        if now - last_sent_at < timedelta(
            seconds=settings.password_reset_resend_cooldown_seconds
        ):
            return result

    token = generate_token()
    token_hash = hash_token(token)
    to_email = user.email
    tenant_name = tenant.name
    user.invite_token_hash = token_hash
    user.invite_expires_at = now + reset_ttl
    db.commit()

    try:
        send_password_reset_link_email(
            to=to_email,
            tenant_name=tenant_name,
            token=token,
        )
    except EmailDeliveryError:
        # Keep the public response generic, but do not make an SMTP outage
        # consume the resend cooldown. The token predicate avoids invalidating
        # a newer request that may have raced with this delivery attempt.
        db.execute(
            update(User)
            .where(User.id == user_id, User.invite_token_hash == token_hash)
            .values(invite_token_hash=None, invite_expires_at=None)
        )
        db.commit()

    return result


@router.post("/browser/login", response_model=BrowserLoginEnvelope)
def browser_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    require_same_origin(request)
    user = authenticate_user(db, payload, request)
    session_token, session = start_session(db, user)
    csrf_token = generate_token()
    db.commit()
    db.refresh(session)
    db.refresh(user)
    set_session_cookie(response, session_token)
    set_csrf_cookie(response, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return envelope(
        {
            "expires_at": session.expires_at,
            "user": UserRead.model_validate(user).model_dump(),
        }
    )


@router.get("/browser/csrf", response_model=BrowserCsrfEnvelope)
def browser_csrf(
    response: Response,
    _: Annotated[Actor, Depends(get_actor)],
):
    csrf_token = generate_token()
    set_csrf_cookie(response, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return envelope({"csrf_token": csrf_token})


@router.post("/browser/logout", status_code=status.HTTP_204_NO_CONTENT)
def browser_logout(
    response: Response,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    if actor.kind == "user" and actor.credential_id is not None:
        session = db.get(UserSession, actor.credential_id)
        if session is not None and session.revoked_at is None:
            session.revoked_at = utc_now()
            db.commit()
    clear_browser_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    if actor.kind == "user" and actor.credential_id is not None:
        session = db.get(UserSession, actor.credential_id)
        if session is not None and session.revoked_at is None:
            session.revoked_at = utc_now()
            db.commit()


@router.get("/me")
def me(
    user: Annotated[User, Depends(get_current_user)],
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Who this credential is, what it may do — and which company it belongs to.
    The tenant block is what an agent serving two employers uses to tell one
    installed bundle from the other: the key is the identity, so the only honest
    way to ask "whose skill is this?" is to ask the server."""
    from app.services.bundles import bundle_identity

    data = UserRead.model_validate(user).model_dump()
    data["permissions"] = sorted(actor.permissions)
    data.update(bundle_identity(db.get(Tenant, actor.tenant_id)))
    return envelope(data)


@router.post(
    "/invitations",
    response_model=InvitationUserEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def invite_user(
    payload: InviteUserRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    from app.services.emails import EmailDeliveryError, send_invitation_email

    require_permission(actor, "users.manage")
    ensure_role_exists(db, actor.tenant_id, payload.role)
    # Invitations are deliberately exempt from the corporate-domain check:
    # external collaborators (service providers, auditors) join this way.
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email cannot be used for this invitation",
        )
    if payload.employee_id is not None:
        employee = db.get(Employee, payload.employee_id)
        if employee is None or employee.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        if db.scalar(select(User).where(User.employee_id == payload.employee_id)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="employee is already linked to a user",
            )

    token = generate_token()
    tenant = db.get(Tenant, actor.tenant_id)
    user = User(
        tenant_id=actor.tenant_id,
        email=payload.email,
        name=payload.name,
        role=payload.role,
        employee_id=payload.employee_id,
        status="invited",
        invite_token_hash=hash_token(token),
        invite_expires_at=utc_now() + timedelta(hours=settings.invitation_token_ttl_hours),
        invited_by=actor.user_id,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="user.invited",
        entity_type="user",
        entity_id=user.id,
        actor=actor.label,
        detail={"email": user.email, "role": user.role, "employee_id": user.employee_id},
    )
    db.commit()
    db.refresh(user)
    try:
        send_invitation_email(to=payload.email, tenant_name=tenant.name, token=token)
        email_sent = True
    except EmailDeliveryError:
        # The user and the token are committed. Reporting a 500 would tell the
        # caller nothing about which half happened.
        logger.warning("invitation email not delivered to=%s", payload.email)
        email_sent = False
    return envelope(invitation_user_data(user, token, email_sent=email_sent))


@router.post("/invitations/accept")
def accept_invitation(
    payload: AcceptInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
):
    # The token is either an invitation (status=invited) or an admin-issued
    # password reset for an existing active user.
    token_hash = hash_token(payload.token)
    candidate = db.execute(
        select(User.id, User.tenant_id).where(
            User.invite_token_hash == token_hash,
            User.status.in_(("invited", "active")),
        )
    ).one_or_none()
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired invitation token")

    # Bind RLS before asking PostgreSQL for an UPDATE row lock. Re-querying the
    # token under that lock closes the race with resend/reset token rotation.
    bind_tenant_context(db, candidate.tenant_id)
    user = db.scalar(
        select(User)
        .where(
            User.id == candidate.id,
            User.invite_token_hash == token_hash,
            User.status.in_(("invited", "active")),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.invite_expires_at is None or as_utc(user.invite_expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired invitation token")
    user.password_hash = hash_password(payload.password)
    if user.status == "invited" and payload.name is not None:
        user.name = payload.name
    user.status = "active"
    user.email_verified_at = utc_now()
    user.invite_token_hash = None
    user.invite_expires_at = None
    old_sessions = db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ).all()
    for old_session in old_sessions:
        old_session.revoked_at = utc_now()
    session_token, session = start_session(db, user)
    db.commit()
    db.refresh(session)
    db.refresh(user)
    data = SessionResponse(
        session_token=session_token,
        expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )
    return envelope(data.model_dump())


@router.get("/users", response_model=UserListEnvelope, response_model_exclude_unset=True)
def list_users(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
    role: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    require_permission(actor, "users.manage")
    stmt = select(User).where(User.tenant_id == actor.tenant_id)
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    if role:
        stmt = stmt.where(User.role == role)
    if page is None:
        users = db.scalars(stmt.order_by(User.created_at.desc(), User.id.desc())).all()
        data = [UserRead.model_validate(user).model_dump() for user in users]
        return envelope(data, len(data))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = db.scalars(
        stmt.order_by(User.created_at.desc(), User.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    data = [UserRead.model_validate(user).model_dump() for user in users]
    return paginated_envelope(data, total=total, page=page, page_size=size)


@router.patch("/users/{user_id}", response_model=UserEnvelope, response_model_exclude_unset=True)
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "users.manage")
    lock_tenant_identity(db, actor.tenant_id)
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.tenant_id == actor.tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    # what this person could do BEFORE the change — an access trail is only
    # useful if it says what moved, not merely that something did
    was = {"role": user.role, "status": user.status, "email": user.email,
           "employee_id": user.employee_id}
    email_changed = "email" in updates and updates["email"] != user.email
    if email_changed:
        if db.scalar(select(User).where(User.email == updates["email"])) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email cannot be used for this user",
            )
    if "role" in updates:
        ensure_role_exists(db, actor.tenant_id, updates["role"])
    if updates.get("status") == "active" and user.invitation_pending:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="an unverified user must accept an invitation before activation",
        )
    if "employee_id" in updates and updates["employee_id"] is not None:
        employee = db.get(Employee, updates["employee_id"])
        if employee is None or employee.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        other = db.scalar(select(User).where(User.employee_id == updates["employee_id"]))
        if other is not None and other.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="employee is already linked to a user",
            )
    if "role" in updates or "status" in updates:
        proposed_status = updates.get("status", user.status)
        proposed_role = updates.get("role", user.role)
        if not tenant_has_active_user_manager(
            db,
            actor.tenant_id,
            user_overrides={user.id: (proposed_status, proposed_role)},
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tenant must keep at least one active user with users.manage (lockout guard)",
            )
    for field, value in updates.items():
        setattr(user, field, value)
    if email_changed or updates.get("status") == "disabled":
        # A disabled account must not retain an invitation or password-reset
        # token that could become usable again after a later re-enable. An
        # email change likewise invalidates links delivered to the old owner.
        user.invite_token_hash = None
        user.invite_expires_at = None
    if updates.get("status") == "disabled":
        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
        ).all()
        for session in sessions:
            session.revoked_at = utc_now()
    changed = {
        field: {"from": was[field], "to": getattr(user, field)}
        for field in was
        if getattr(user, field) != was[field]
    }
    if changed:
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            actor=actor.label,
            detail={"email": user.email, **changed},
        )
    db.commit()
    db.refresh(user)
    return envelope(UserRead.model_validate(user).model_dump())


@router.post(
    "/users/{user_id}/password-reset-email",
    response_model=PasswordResetEmailEnvelope,
    response_model_exclude_unset=True,
)
def request_password_reset_email(
    user_id: str,
    response: Response,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Email an active tenant user a one-time link for choosing a new password.

    Sending does not change the current password or sessions. Accepting the
    link performs the reset and revokes existing sessions atomically.
    """
    from app.services.emails import EmailDeliveryError, send_password_reset_link_email

    require_permission(actor, "users.manage")
    lock_tenant_identity(db, actor.tenant_id)
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.tenant_id == actor.tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.status != "active" or user.invitation_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only active users with a usable login can reset their password",
        )

    token = generate_token()
    user.invite_token_hash = hash_token(token)
    user.invite_expires_at = utc_now() + timedelta(
        minutes=settings.password_reset_token_ttl_minutes
    )
    db.commit()
    db.refresh(user)

    tenant = db.get(Tenant, actor.tenant_id)
    email_sent = True
    try:
        send_password_reset_link_email(
            to=user.email,
            tenant_name=tenant.name if tenant else "oryh",
            token=token,
        )
    except EmailDeliveryError:
        email_sent = False

    response.headers["Cache-Control"] = "no-store"
    return envelope(password_reset_email_data(user, email_sent=email_sent))


@router.post(
    "/users/{user_id}/resend-invitation",
    response_model=InvitationUserEnvelope,
    response_model_exclude_unset=True,
)
def resend_invitation(
    user_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Re-issue an invitation for an unverified user.

    A fresh token replaces the previous one. A disabled, never-verified user
    returns to ``invited`` so a revoked or expired invitation can be recovered
    without ever activating a passwordless account.
    """
    from app.services.emails import EmailDeliveryError, send_invitation_email

    require_permission(actor, "users.manage")
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.tenant_id == actor.tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    recoverable_disabled_invite = user.status == "disabled" and user.invitation_pending
    if user.status != "invited" and not recoverable_disabled_invite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only unverified users can be re-invited",
        )
    token = generate_token()
    user.status = "invited"
    user.invite_token_hash = hash_token(token)
    user.invite_expires_at = utc_now() + timedelta(hours=settings.invitation_token_ttl_hours)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="user.reinvited",
        entity_type="user",
        entity_id=user.id,
        actor=actor.label,
        detail={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)
    tenant = db.get(Tenant, actor.tenant_id)
    try:
        send_invitation_email(to=user.email, tenant_name=tenant.name, token=token)
        email_sent = True
    except EmailDeliveryError:
        # The user and the token are committed. Reporting a 500 would tell the
        # caller nothing about which half happened.
        logger.warning("invitation email not delivered to=%s", user.email)
        email_sent = False
    return envelope(invitation_user_data(user, token, email_sent=email_sent))
