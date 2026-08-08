from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route

from app.core.legacy_usage import (
    LegacyWebUsageMiddleware,
    legacy_tenant_route,
    legacy_tenant_successor,
)
from app.core.security import hash_token
from app.models import Tenant, User, UserSession

from conftest import make_client


SESSION_TOKEN = "legacy-usage-session"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    def seed(db: Session) -> None:
        tenant = Tenant(name="Legacy Usage", email_domain="legacy-usage.example")
        db.add(tenant)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            email="admin@legacy-usage.example",
            name="Legacy Admin",
            role="admin",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_token(SESSION_TOKEN),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )

    with make_client(seed) as test_client:
        yield test_client


def test_legacy_tenant_route_classification_is_bounded() -> None:
    assert legacy_tenant_route("/web/").successor == "/console/dashboard"  # type: ignore[union-attr]
    assert legacy_tenant_route("/web/objects/business_object/private-id").name == "objects"  # type: ignore[union-attr]
    assert legacy_tenant_route("/web/product-skus/private-id/archive").name == "products"  # type: ignore[union-attr]
    assert legacy_tenant_route("/web/register") is None
    assert legacy_tenant_route("/web/invitations/accept") is None
    assert legacy_tenant_route("/web/device") is None
    assert legacy_tenant_route("/web/connect") is None
    assert legacy_tenant_successor("/web/objects/../private-id") == "/console/objects"
    assert legacy_tenant_successor("/web/objects/business_object/..") == "/console/objects"


def test_legacy_tenant_responses_are_marked_and_logged(
    client: TestClient,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="oryh.legacy_web")
    response = client.get("/web/dashboard", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/console/dashboard"
    assert response.headers["deprecation"] == "true"
    assert response.headers["link"] == '</console/dashboard>; rel="successor-version"'
    assert response.headers["x-oryh-legacy-surface"] == "tenant"
    assert (
        "legacy_tenant_web_access route=dashboard method=GET status=308 "
        "outcome=successor_redirect"
    ) in caplog.text

    caplog.clear()
    detail = client.get("/web/objects/business_object/private-record-id", follow_redirects=False)
    assert detail.status_code == 308
    assert detail.headers["location"] == "/console/objects/business_object/private-record-id"
    assert (
        "legacy_tenant_web_access route=objects method=GET status=308 "
        "outcome=successor_redirect successor=/console/objects"
    ) in caplog.text
    assert "private-record-id" not in caplog.text

    caplog.clear()
    client.cookies.set("oryh_session", SESSION_TOKEN, path="/")
    redirected = client.get("/web/dashboard", follow_redirects=False)
    assert redirected.status_code == 308
    assert "route=dashboard method=GET status=308 outcome=successor_redirect" in caplog.text

    caplog.clear()
    retired = client.post(
        "/web/projects/save",
        data={"project_name": "Legacy telemetry project", "status": "active"},
        follow_redirects=False,
    )
    assert retired.status_code == 410
    assert "route=projects method=POST status=410 outcome=retired" in caplog.text

    caplog.clear()
    # A /web page that is still PUBLIC must carry none of the above. The
    # connect page rather than registration: every edition serves it, and it
    # stays public even for a signed-in caller — /web/login would redirect this
    # fixture's session to /console, which FastAPI does not serve at all.
    public_page = client.get("/web/connect")
    assert public_page.status_code == 200
    assert "deprecation" not in public_page.headers
    assert "legacy_tenant_web_access" not in caplog.text


def test_direct_api_root_no_longer_enters_the_legacy_console(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/docs"


def test_legacy_exception_is_logged_without_path_query_or_error_details(caplog) -> None:
    async def raise_unhandled(_request: Request):
        raise RuntimeError("private exception detail")

    crashing_app = Starlette(
        routes=[Route("/web/objects/{record_id}", raise_unhandled)],
    )
    crashing_app.add_middleware(LegacyWebUsageMiddleware)
    caplog.set_level(logging.WARNING, logger="oryh.legacy_web")

    with TestClient(crashing_app) as crashing_client:
        with pytest.raises(RuntimeError, match="private exception detail"):
            crashing_client.get(
                "/web/objects/private-record-id?token=private-query-token",
            )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "oryh.legacy_web"
    ]
    assert messages == [
        "legacy_tenant_web_access route=objects method=GET status=500 "
        "outcome=exception successor=/console/objects"
    ]
    assert "private-record-id" not in messages[0]
    assert "private-query-token" not in messages[0]
    assert "private exception detail" not in messages[0]
