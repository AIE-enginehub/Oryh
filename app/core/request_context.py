from __future__ import annotations

from contextvars import ContextVar

from app.core.config import settings

# Final fallback when neither ORYH_BASE_URL nor a request context is set
# (e.g. links built from an offline script).
_DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# The base URL (scheme://host[:port], no trailing slash) of the HTTP request
# currently being served, captured per request. Email links fall back to this
# when ORYH_BASE_URL is not explicitly configured, so a dev/test deployment
# with no fixed domain produces links pointing at whatever address the admin
# actually reached the console on — instead of a hardcoded 127.0.0.1.
_request_base_url: ContextVar[str | None] = ContextVar("request_base_url", default=None)


def set_request_base_url(url: str | None) -> object:
    return _request_base_url.set(url)


def reset_request_base_url(token: object) -> None:
    _request_base_url.reset(token)  # type: ignore[arg-type]


def get_request_base_url() -> str | None:
    return _request_base_url.get()


def resolved_base_url() -> str:
    """Base URL for links in outbound email and rendered skill bundles. An
    explicitly configured ORYH_BASE_URL (the canonical production domain)
    always wins; otherwise fall back to the current request's address so a
    dev/test deployment with no fixed domain still produces reachable links."""
    if settings.base_url:
        return settings.base_url.rstrip("/")
    request_base = get_request_base_url()
    if request_base:
        return request_base.rstrip("/")
    return _DEFAULT_BASE_URL


class RequestBaseUrlMiddleware:
    """Pure-ASGI middleware that records each HTTP request's base URL in a
    context variable. Implemented as raw ASGI (not BaseHTTPMiddleware) so the
    value set here propagates into the endpoint — including sync endpoints run
    in the threadpool — which BaseHTTPMiddleware's separate task would break.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        token = set_request_base_url(_base_url_from_scope(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_base_url(token)


def _base_url_from_scope(scope) -> str | None:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    # Honor a reverse proxy's forwarded scheme/host when present, so links use
    # the externally visible address rather than the internal one.
    scheme = headers.get("x-forwarded-proto", scope.get("scheme", "http")).split(",")[0].strip()
    host = headers.get("x-forwarded-host", headers.get("host", "")).split(",")[0].strip()
    if not host:
        server = scope.get("server")
        if not server:
            return None
        name, port = server
        host = name if not port or port in (80, 443) else f"{name}:{port}"
    return f"{scheme}://{host}"
