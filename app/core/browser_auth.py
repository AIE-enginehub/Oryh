from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.request_context import resolved_base_url


SESSION_COOKIE = "oryh_session"
CSRF_COOKIE = "oryh_csrf"


def require_same_origin(request: Request) -> None:
    """Reject cross-origin browser authentication attempts when signalled.

    Browsers send Origin and Fetch Metadata headers; non-browser API clients
    may omit them. Login does not yet have a session to protect with a CSRF
    token, so this prevents login-CSRF without changing the legacy JSON login.
    """

    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="browser authentication requires a same-origin request",
        )

    origin = request.headers.get("Origin")
    if not origin:
        return
    supplied = urlsplit(origin)
    expected = urlsplit(resolved_base_url())
    if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="browser authentication requires a same-origin request",
        )


def require_same_origin_on_writes(request: Request) -> None:
    """`require_same_origin`, as a router dependency for every unsafe method.

    Written to be attached to a router rather than called by a handler. It was
    per-handler on the operator console and three of sixteen handlers had it —
    the thirteen without included minting tenant API keys, minting hosted
    flow-agent keys and resetting passwords. A rule repeated at every call site
    holds only where somebody remembered.

    Safe methods are exempt: this defends against a cross-origin form POST, and
    a GET that changes nothing is not one.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    require_same_origin(request)


def _secure_cookie() -> bool:
    return settings.base_url.lower().startswith("https://")


def set_session_cookie(response: Response, token: str) -> None:
    """Set the host-only browser session cookie shared by SSR and the SPA."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set the readable half of the double-submit CSRF token."""
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        secure=_secure_cookie(),
        httponly=False,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )


def clear_browser_auth_cookies(response: Response) -> None:
    clear_session_cookie(response)
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=_secure_cookie(),
        httponly=False,
        samesite="lax",
    )
