"""OAuth 2.1 — the second door's lock.

The device flow (`/auth/device/*`) is already OAuth's device grant in
everything but its endpoint names; what MCP clients (Claude, Codex, …) add
is discovery and the authorization-code grant with PKCE, run in the person's
browser. Both grants mint the SAME interactive key pair the device flow does
— an expiring api key plus a rotating refresh token — so nothing downstream
(capabilities, RLS, audit) learns a new credential shape. Tokens are opaque;
the resource server is this same service, so there is nothing a JWT would
tell it that the row does not.

Deliberately absent: scopes (the token carries the person, permissions are
their role's), third-party clients (every client acts as its own user),
dynamic client registration (retired; the client id is a URL — CIMD — and
the redirect must be that host or loopback).
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api import auth as auth_api
from app.api import device as device_api
from app.core.browser_auth import SESSION_COOKIE
from app.core.request_context import resolved_base_url
from app.core.security import generate_token, hash_token
from app.db.session import bind_tenant_context, get_db
from app.models import ApiKey, OAuthAuthorizationCode, User, generate_api_key, hash_api_key
from app.schemas import DeviceStartRequest, DeviceTokenRequest, TokenRefreshRequest
from app.services import interactive_keys
from app.services.audit import record_audit

router = APIRouter(include_in_schema=False)

CODE_TTL = timedelta(minutes=10)
CONSENT_TTL = timedelta(minutes=10)
CONSENT_PARAMS = ("response_type", "client_id", "redirect_uri", "code_challenge",
                  "code_challenge_method", "state", "scope", "resource")
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def issuer() -> str:
    return resolved_base_url().rstrip("/")


def mcp_resource() -> str:
    return issuer() + "/mcp"


# --- discovery (RFC 8414, RFC 9728) -----------------------------------------


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata():
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "device_authorization_endpoint": f"{base}/oauth/device_authorization",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token", DEVICE_GRANT],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [],
        "service_documentation": f"{base}/docs",
    }


def _protected_resource_document() -> dict:
    return {
        "resource": mcp_resource(),
        "authorization_servers": [issuer()],
        "bearer_methods_supported": ["header"],
        "resource_name": "oryh MCP",
    }


@router.get("/.well-known/oauth-protected-resource")
def protected_resource_metadata():
    return _protected_resource_document()


@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata_for_mcp():
    return _protected_resource_document()


# --- helpers ------------------------------------------------------------------


def _oauth_error(code: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store"},
    )


def _client_host(client_id: str) -> str | None:
    parts = urlsplit(client_id)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        return None
    return parts.hostname.lower() if parts.hostname else None


def _redirect_allowed(client_id: str, redirect_uri: str) -> bool:
    """CIMD-lite: the client is a URL, and it may only be sent back to its
    own host over https — or to a loopback address on any port, which is
    how desktop and CLI agents receive a code."""
    host = _client_host(client_id)
    parts = urlsplit(redirect_uri)
    if host is None or parts.fragment or not parts.hostname:
        return False
    if parts.scheme == "http" and parts.hostname.lower() in LOOPBACK_HOSTS:
        return True
    return parts.scheme == "https" and parts.hostname.lower() == host


def _redirect_with(redirect_uri: str, params: dict[str, str]) -> RedirectResponse:
    joiner = "&" if urlsplit(redirect_uri).query else "?"
    return RedirectResponse(
        f"{redirect_uri}{joiner}{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER
    )


def _same_origin(request: Request) -> bool:
    """A consent POST must come from this site: an Origin (or Referer) that
    names another origin is refused before the cookie is even read."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return True
    parts = urlsplit(origin)
    here = urlsplit(issuer())
    return (parts.scheme, parts.netloc) == (here.scheme, here.netloc)


def _consent_fingerprint(p: dict[str, str]) -> str:
    return "|".join(p.get(key, "") for key in CONSENT_PARAMS)


def _pkce_matches(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii") == challenge


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_response(api_key_plain: str, refresh_plain: str, expires_at: datetime | str | None) -> JSONResponse:
    expires_in = None
    expires_at = _as_utc(expires_at)
    if expires_at is not None:
        expires_in = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    return JSONResponse(
        {
            "access_token": api_key_plain,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_plain,
            "scope": "",
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


# --- authorization endpoint (browser) -----------------------------------------


def _authorize_context(request: Request) -> dict[str, str]:
    q = request.query_params
    return {
        "response_type": q.get("response_type", ""),
        "client_id": q.get("client_id", ""),
        "redirect_uri": q.get("redirect_uri", ""),
        "code_challenge": q.get("code_challenge", ""),
        "code_challenge_method": q.get("code_challenge_method", "S256"),
        "state": q.get("state", ""),
        "scope": q.get("scope", ""),
        "resource": q.get("resource", ""),
    }


def _validate_authorize(p: dict[str, str]):
    """The client and its redirect are checked BEFORE anything is sent back
    to them; every other problem is reported to the redirect, as the spec
    has it. Returns a redirect response for reportable errors, None when
    the request is sound."""
    if not _redirect_allowed(p["client_id"], p["redirect_uri"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id must be an https URL and redirect_uri its own https host or a loopback address",
        )
    if p["response_type"] != "code":
        return _redirect_with(p["redirect_uri"], {"error": "unsupported_response_type", "state": p["state"]})
    if not p["code_challenge"] or p["code_challenge_method"] != "S256":
        return _redirect_with(p["redirect_uri"], {
            "error": "invalid_request", "error_description": "PKCE S256 code_challenge is required",
            "state": p["state"],
        })
    if p["resource"] and p["resource"].rstrip("/") not in {mcp_resource(), issuer()}:
        return _redirect_with(p["redirect_uri"], {
            "error": "invalid_target", "error_description": f"resource must be {mcp_resource()}",
            "state": p["state"],
        })
    return None


@router.get("/oauth/authorize", response_class=HTMLResponse)
def authorize_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    from app.web.routes import get_web_actor, render

    p = _authorize_context(request)
    problem = _validate_authorize(p)
    if problem is not None:
        return problem
    actor = get_web_actor(db, request.cookies.get(SESSION_COOKIE))
    if actor is None:
        target = f"/oauth/authorize?{urlencode(p)}"
        return RedirectResponse(f"/web/login?next={urlencode({'': target})[1:]}", status_code=status.HTTP_303_SEE_OTHER)
    user = db.get(User, actor.user_id)
    nonce = generate_token()
    db.add(OAuthAuthorizationCode(
        code_hash=hash_token(nonce),
        stage="consent",
        session_id=actor.credential_id,
        client_id=p["client_id"],
        redirect_uri=p["redirect_uri"],
        code_challenge=_consent_fingerprint(p),
        resource=p["resource"] or None,
        scope=p["scope"] or None,
        tenant_id=actor.tenant_id,
        user_id=actor.user_id,
        expires_at=datetime.now(timezone.utc) + CONSENT_TTL,
    ))
    db.commit()
    return render(
        "oauth_authorize.html", request, actor, db,
        user=user, params=p, consent=nonce, client_host=_client_host(p["client_id"]),
        redirect_host=urlsplit(p["redirect_uri"]).hostname,
    )


@router.post("/oauth/authorize", response_class=HTMLResponse)
async def authorize_decide(request: Request, db: Annotated[Session, Depends(get_db)]):
    from app.web.routes import get_web_actor

    form = await request.form()
    p = {key: str(form.get(key, "")) for key in (
        "response_type", "client_id", "redirect_uri", "code_challenge",
        "code_challenge_method", "state", "scope", "resource",
    )}
    p["code_challenge_method"] = p["code_challenge_method"] or "S256"
    problem = _validate_authorize(p)
    if problem is not None:
        return problem
    if not _same_origin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="consent must be posted from this site")
    actor = get_web_actor(db, request.cookies.get(SESSION_COOKIE))
    if actor is None:
        return RedirectResponse(f"/web/login?next={urlencode({'': '/oauth/authorize?' + urlencode(p)})[1:]}", status_code=status.HTTP_303_SEE_OTHER)
    # the consent token: minted when THIS session saw THIS request, spent once
    spent = db.execute(
        update(OAuthAuthorizationCode)
        .where(
            OAuthAuthorizationCode.code_hash == hash_token(str(form.get("consent", ""))),
            OAuthAuthorizationCode.stage == "consent",
            OAuthAuthorizationCode.session_id == actor.credential_id,
            OAuthAuthorizationCode.code_challenge == _consent_fingerprint(p),
            OAuthAuthorizationCode.consumed_at.is_(None),
            OAuthAuthorizationCode.expires_at > datetime.now(timezone.utc),
        )
        .values(consumed_at=datetime.now(timezone.utc))
    ).rowcount
    if spent != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this consent was not shown to this session for these parameters, or it expired — open the authorization page again",
        )
    if str(form.get("decision", "")) != "approve":
        db.commit()
        return _redirect_with(p["redirect_uri"], {"error": "access_denied", "state": p["state"]})
    code = generate_token()
    db.add(OAuthAuthorizationCode(
        code_hash=hash_token(code),
        client_id=p["client_id"],
        redirect_uri=p["redirect_uri"],
        code_challenge=p["code_challenge"],
        resource=p["resource"] or None,
        scope=p["scope"] or None,
        tenant_id=actor.tenant_id,
        user_id=actor.user_id,
        stage="code",
        session_id=actor.credential_id,
        expires_at=datetime.now(timezone.utc) + CODE_TTL,
    ))
    db.commit()
    return _redirect_with(p["redirect_uri"], {"code": code, "state": p["state"], "iss": issuer()})


# --- token endpoint ------------------------------------------------------------


async def _grant_params(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        data = await request.form()
    return {key: str(value) for key, value in dict(data).items()}


def _redeem_code(db: Session, p: dict[str, str]) -> JSONResponse:
    code, verifier = p.get("code", ""), p.get("code_verifier", "")
    if not code or not verifier:
        return _oauth_error(400, "invalid_request", "code and code_verifier are required")
    row = db.scalar(select(OAuthAuthorizationCode).where(
        OAuthAuthorizationCode.code_hash == hash_token(code), OAuthAuthorizationCode.stage == "code",
    ))
    if row is None or row.consumed_at is not None or _as_utc(row.expires_at) < datetime.now(timezone.utc):
        return _oauth_error(400, "invalid_grant", "authorization code is unknown, spent or expired")
    if p.get("client_id", "") != row.client_id or p.get("redirect_uri", "") != row.redirect_uri:
        return _oauth_error(400, "invalid_grant", "client_id and redirect_uri must match the authorization request")
    if not _pkce_matches(verifier, row.code_challenge):
        return _oauth_error(400, "invalid_grant", "PKCE verification failed")
    if p.get("resource") and p["resource"].rstrip("/") not in {mcp_resource(), issuer()}:
        return _oauth_error(400, "invalid_target", f"resource must be {mcp_resource()}")
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        return _oauth_error(400, "invalid_grant", "the authorizing user is no longer active")
    # spend the code with a conditional UPDATE: two redemptions that both read
    # "unspent" cannot both mint a key — exactly one wins (review R08)
    spent = db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.id == row.id, OAuthAuthorizationCode.consumed_at.is_(None))
        .values(consumed_at=datetime.now(timezone.utc))
    ).rowcount
    if spent != 1:
        db.rollback()
        return _oauth_error(400, "invalid_grant", "authorization code already redeemed")
    bind_tenant_context(db, row.tenant_id)
    db.info["audit_actor"] = f"user:{user.id}"
    plaintext = generate_api_key()
    api_key = ApiKey(
        tenant_id=row.tenant_id,
        key_hash=hash_api_key(plaintext),
        label=f"oauth:{_client_host(row.client_id)}",
        user_id=user.id,
        role=user.role,
        is_active=True,
    )
    refresh_plain = interactive_keys.make_interactive(api_key)
    db.add(api_key)
    db.flush()
    record_audit(
        db,
        tenant_id=row.tenant_id,
        action="oauth.authorized",
        entity_type="user",
        entity_id=user.id,
        actor=f"user:{user.id}",
        detail={"key_id": api_key.id, "client_id": row.client_id, "resource": row.resource},
    )
    db.commit()
    return _token_response(plaintext, refresh_plain, api_key.expires_at)


def _refresh(db: Session, p: dict[str, str]) -> JSONResponse:
    token = p.get("refresh_token", "")
    if not token:
        return _oauth_error(400, "invalid_request", "refresh_token is required")
    try:
        data = auth_api.refresh_api_key(TokenRefreshRequest(refresh_token=token), db)["data"]
    except HTTPException as exc:
        return _oauth_error(400, "invalid_grant", str(exc.detail))
    return _token_response(data["api_key"], data["refresh_token"], data.get("expires_at"))


def _device(db: Session, p: dict[str, str]) -> JSONResponse:
    device_code = p.get("device_code", "")
    if not device_code:
        return _oauth_error(400, "invalid_request", "device_code is required")
    try:
        data = device_api.poll_device_authorization(DeviceTokenRequest(device_code=device_code), db)["data"]
    except HTTPException as exc:
        return _oauth_error(400, "invalid_grant", str(exc.detail))
    outcome = data.get("status")
    if outcome == "pending":
        return _oauth_error(400, "authorization_pending", "the person has not approved this device yet")
    if outcome == "expired":
        return _oauth_error(400, "expired_token", "the device code expired; start again")
    if outcome == "denied":
        return _oauth_error(400, "access_denied", "the person denied this device")
    return _token_response(data["api_key"], data["refresh_token"], data.get("expires_at"))


@router.post("/oauth/token")
async def token_endpoint(request: Request, db: Annotated[Session, Depends(get_db)]):
    p = await _grant_params(request)
    grant = p.get("grant_type", "")
    if grant == "authorization_code":
        return _redeem_code(db, p)
    if grant == "refresh_token":
        return _refresh(db, p)
    if grant == DEVICE_GRANT:
        return _device(db, p)
    return _oauth_error(400, "unsupported_grant_type", f"grant_type must be one of authorization_code, refresh_token, {DEVICE_GRANT}")


@router.post("/oauth/device_authorization")
async def device_authorization(request: Request, db: Annotated[Session, Depends(get_db)]):
    """RFC 8628's shape over the existing device flow: the client_id (a URL)
    or a client_name labels the device the person approves."""
    p = await _grant_params(request)
    client_name = p.get("client_name") or (_client_host(p.get("client_id", "")) or "agent")
    data = device_api.start_device_authorization(DeviceStartRequest(client_name=client_name), db)["data"]
    return JSONResponse(data, headers={"Cache-Control": "no-store"})
