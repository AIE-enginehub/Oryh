from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api import auth as auth_api
from app.api.deps import Actor, _resolve_session_actor
from app.core.browser_auth import SESSION_COOKIE, clear_browser_auth_cookies, set_session_cookie
from app.core.legacy_usage import legacy_tenant_successor
from app.core.security import hash_token
from app.db.session import get_db
from app.models import Tenant, User, UserSession
from app.schemas import (
    AcceptInvitationRequest,
    LoginRequest,
)

router = APIRouter(prefix="/web")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def get_web_actor(
    db: Annotated[Session, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Actor | None:
    if not session_token:
        return None
    try:
        return _resolve_session_actor(db, session_token)
    except HTTPException:
        return None


WebActor = Annotated[Actor | None, Depends(get_web_actor)]
Db = Annotated[Session, Depends(get_db)]


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/web/login", status_code=status.HTTP_303_SEE_OTHER)


def error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return str(exc)


def render(
    template: str, request: Request, actor: Actor | None = None, db: Session | None = None, **context
):
    nav = {}
    # Sidebar identity: resolve the actor's display name and tenant once, when a
    # session is available. Cheap point lookups; skipped on error fallbacks that
    # pass no db.
    if db is not None and actor is not None:
        tenant = db.get(Tenant, actor.tenant_id)
        nav["nav_tenant"] = tenant.name if tenant else None
        nav["nav_sub"] = tenant.name if tenant else None
        if actor.user_id:
            user = db.get(User, actor.user_id)
            if user is not None:
                nav["nav_name"] = user.name or user.email
    return templates.TemplateResponse(
        request, template, {"actor": actor, **nav, **context}
    )


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def web_root():
    return RedirectResponse(
        "/console/dashboard", status_code=status.HTTP_308_PERMANENT_REDIRECT
    )


@router.get("/connect", response_class=HTMLResponse)
def connect_page(request: Request, actor: WebActor):
    # public even when signed in: this is what you hand to a *new* agent or
    # device, not a per-user download
    return render("connect.html", request, actor)


def safe_next_url(next_url: str) -> str:
    # The only server-rendered authenticated flow that still needs a return
    # target is device approval. Everything else enters the React console, and
    # crafted external or legacy-management targets cannot bounce the session.
    if next_url == "/web/device" or next_url.startswith("/web/device?"):
        return next_url
    return "/console/dashboard"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, actor: WebActor, next: str = ""):
    if actor is not None:
        return RedirectResponse(safe_next_url(next), status_code=status.HTTP_303_SEE_OTHER)
    return render("login.html", request, next=next)


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "",
):
    try:
        data = auth_api.login(LoginRequest(email=email, password=password), db)["data"]
    except (HTTPException, ValidationError) as exc:
        return render("login.html", request, error=error_text(exc), email=email, next=next)
    response = RedirectResponse(safe_next_url(next), status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, data["session_token"])
    return response


@router.post("/logout")
def logout(
    db: Db,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    if session_token:
        from sqlalchemy import select

        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(session_token)))
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response = login_redirect()
    clear_browser_auth_cookies(response)
    return response


@router.get("/invitations/accept", response_class=HTMLResponse)
def accept_invite_page(request: Request, token: str = "", mode: str = "invite"):
    return render("accept_invite.html", request, token=token, reset_mode=mode == "reset")


@router.post("/invitations/accept", response_class=HTMLResponse)
def accept_invite_submit(
    request: Request,
    db: Db,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirmation: Annotated[str, Form()],
    mode: Annotated[str, Form()] = "invite",
):
    if password != password_confirmation:
        return render(
            "accept_invite.html",
            request,
            error="passwords do not match",
            token=token,
            reset_mode=mode == "reset",
        )
    try:
        payload = AcceptInvitationRequest(token=token, password=password)
        data = auth_api.accept_invitation(payload, db)["data"]
    except (HTTPException, ValidationError) as exc:
        return render(
            "accept_invite.html",
            request,
            error=error_text(exc),
            token=token,
            reset_mode=mode == "reset",
        )
    response = RedirectResponse("/console/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, data["session_token"])
    return response


def device_login_redirect(code: str) -> RedirectResponse:
    from urllib.parse import quote

    target = f"/web/device?code={quote(code)}" if code else "/web/device"
    return RedirectResponse(
        f"/web/login?next={quote(target)}", status_code=status.HTTP_303_SEE_OTHER
    )


def render_device(request: Request, actor: Actor, db: Session, **context):
    user = db.get(User, actor.user_id)
    return render("device.html", request, actor, user=user, **context)


@router.get("/device", response_class=HTMLResponse)
def device_page(request: Request, actor: WebActor, db: Db, code: str = ""):
    from app.api import device as device_api

    if actor is None:
        return device_login_redirect(code)
    auth = device_api.find_pending_by_user_code(db, code) if code else None
    error = "No pending connection found for this code — it may have expired. Ask your agent to start again." if code and auth is None else None
    return render_device(request, actor, db, code=code, auth=auth, error=error)


@router.post("/device/approve", response_class=HTMLResponse)
def device_approve(request: Request, actor: WebActor, db: Db, code: Annotated[str, Form()]):
    from app.api import device as device_api
    from app.models import ApiKey, generate_api_key, hash_api_key
    from app.services.audit import record_audit

    if actor is None:
        return device_login_redirect(code)
    auth = device_api.find_pending_by_user_code(db, code)
    if auth is None:
        return render_device(
            request, actor, db, code=code, auth=None,
            error="This code is no longer pending — it may have expired or already been used.",
        )
    user = db.get(User, actor.user_id)
    # one key per connected device; other devices' keys stay untouched
    plaintext = generate_api_key()
    api_key = ApiKey(
        tenant_id=actor.tenant_id,
        key_hash=hash_api_key(plaintext),
        label=f"device:{auth.client_name or 'agent'}",
        user_id=user.id,
        role=user.role,
        is_active=True,
    )
    db.add(api_key)
    db.flush()
    auth.status = "approved"
    auth.tenant_id = actor.tenant_id
    auth.user_id = user.id
    auth.api_key_id = api_key.id
    auth.api_key_plaintext = plaintext
    auth.approved_at = datetime.now(timezone.utc)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="device.authorized",
        entity_type="user",
        entity_id=user.id,
        actor=actor.label,
        detail={"key_id": api_key.id, "client_name": auth.client_name, "user_code": auth.user_code},
    )
    db.commit()
    return render_device(request, actor, db, code="", auth=None, result="approved", client_name=auth.client_name)


@router.post("/device/deny", response_class=HTMLResponse)
def device_deny(request: Request, actor: WebActor, db: Db, code: Annotated[str, Form()]):
    from app.api import device as device_api

    if actor is None:
        return device_login_redirect(code)
    auth = device_api.find_pending_by_user_code(db, code)
    if auth is not None:
        auth.status = "denied"
        db.commit()
    return render_device(request, actor, db, code="", auth=None, result="denied")


# All authenticated tenant-management pages now live in React. Keep one thin
# compatibility boundary so old bookmarks land on their successor while stale
# forms cannot replay writes against the removed handlers.
@router.api_route(
    "/{legacy_path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def retired_tenant_console(request: Request, legacy_path: str):
    del legacy_path
    successor = legacy_tenant_successor(request.url.path)
    if successor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if request.method in {"GET", "HEAD"}:
        return RedirectResponse(successor, status_code=status.HTTP_308_PERMANENT_REDIRECT)
    return Response(
        "This page has moved. Use the current console.",
        status_code=status.HTTP_410_GONE,
        media_type="text/plain",
    )
