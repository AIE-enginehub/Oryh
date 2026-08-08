from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger("oryh.legacy_web")


@dataclass(frozen=True)
class LegacyTenantRoute:
    name: str
    successor: str


_LEGACY_TENANT_PREFIXES: tuple[tuple[str, LegacyTenantRoute], ...] = (
    ("/web/product-skus", LegacyTenantRoute("products", "/console/products")),
    ("/web/capabilities", LegacyTenantRoute("roles", "/console/roles")),
    ("/web/workflows", LegacyTenantRoute("object-types", "/console/object-types")),
    ("/web/attachments", LegacyTenantRoute("attachments", "/console/objects")),
    ("/web/object-types", LegacyTenantRoute("object-types", "/console/object-types")),
    ("/web/api-keys", LegacyTenantRoute("api-keys", "/console/api-keys")),
    ("/web/dashboard", LegacyTenantRoute("dashboard", "/console/dashboard")),
    ("/web/employees", LegacyTenantRoute("employees", "/console/employees")),
    ("/web/projects", LegacyTenantRoute("projects", "/console/projects")),
    ("/web/vendors", LegacyTenantRoute("vendors", "/console/vendors")),
    ("/web/products", LegacyTenantRoute("products", "/console/products")),
    ("/web/resources", LegacyTenantRoute("resources", "/console/resources")),
    ("/web/skills", LegacyTenantRoute("skills", "/console/skills")),
    ("/web/todos", LegacyTenantRoute("todos", "/console/todos")),
    ("/web/approvals", LegacyTenantRoute("approvals", "/console/approvals")),
    ("/web/roles", LegacyTenantRoute("roles", "/console/roles")),
    ("/web/objects", LegacyTenantRoute("objects", "/console/objects")),
    ("/web/users", LegacyTenantRoute("users", "/console/users")),
)


def legacy_tenant_route(path: str) -> LegacyTenantRoute | None:
    """Classify deprecated tenant-management routes without logging IDs.

    Public account, invitation, device and connect routes are still active and
    therefore intentionally remain outside this retired-route list.
    """
    if path in {"/web", "/web/"}:
        return LegacyTenantRoute("root", "/console/dashboard")
    for prefix, route in _LEGACY_TENANT_PREFIXES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return route
    return None


def legacy_tenant_successor(path: str) -> str | None:
    """Resolve the React destination for one retired tenant-console URL.

    Most legacy pages map to a workspace root. Object detail URLs are the one
    safe deep-link shape whose two path segments can be carried forward.
    Values are quoted so the result always remains below ``/console/objects``.
    """
    route = legacy_tenant_route(path)
    if route is None:
        return None
    parts = path.split("/")
    if len(parts) == 5 and parts[1:3] == ["web", "objects"]:
        raw_entity_type, raw_record_id = parts[3], parts[4]
        entity_type = quote(raw_entity_type, safe="")
        record_id = quote(raw_record_id, safe="")
        if (
            entity_type
            and record_id
            and raw_entity_type not in {".", ".."}
            and raw_record_id not in {".", ".."}
        ):
            return f"/console/objects/{entity_type}/{record_id}"
    return route.successor


def legacy_request_outcome(request: Request, response: Response) -> str:
    """Return an aggregation-safe outcome without inspecting credentials."""
    location = response.headers.get("location", "")
    if 300 <= response.status_code < 400 and (
        location == "/web/login" or location.startswith("/web/login?")
    ):
        return "login_redirect"
    if response.status_code in {401, 403}:
        return "denied"
    if response.status_code == 410:
        return "retired"
    if response.status_code >= 400:
        return "error"
    if request.method in {"GET", "HEAD"}:
        return "successor_redirect" if location.startswith("/console/") else "served"
    return "handled"


def log_legacy_request(
    *,
    route: LegacyTenantRoute,
    method: str,
    status_code: int,
    outcome: str,
) -> None:
    """Emit one bounded-cardinality event without paths or error details."""
    # WARNING is deliberate: Uvicorn's default configuration does not emit
    # INFO records from arbitrary application loggers, while these events must
    # be visible in ordinary container logs during cutover.
    logger.warning(
        "legacy_tenant_web_access route=%s method=%s status=%s outcome=%s successor=%s",
        route.name,
        method,
        status_code,
        outcome,
        route.successor,
    )


class LegacyWebUsageMiddleware(BaseHTTPMiddleware):
    """Mark and log traffic that reaches the retired tenant route surface.

    The normalized route name keeps log cardinality bounded and avoids leaking
    tenant record identifiers. Operators can aggregate
    ``legacy_tenant_web_access`` events while redirects and write tombstones
    remain available for old bookmarks and stale forms.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        route = legacy_tenant_route(request.url.path)
        successor = legacy_tenant_successor(request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            if route is not None:
                log_legacy_request(
                    route=route,
                    method=request.method,
                    status_code=500,
                    outcome="exception",
                )
            raise
        if route is None:
            return response

        response.headers["Deprecation"] = "true"
        response.headers["Link"] = (
            f'<{successor or route.successor}>; rel="successor-version"'
        )
        response.headers["X-Oryh-Legacy-Surface"] = "tenant"
        outcome = legacy_request_outcome(request, response)
        log_legacy_request(
            route=route,
            method=request.method,
            status_code=response.status_code,
            outcome=outcome,
        )
        return response
