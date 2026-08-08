from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.core.security import hash_token
from app.models import (
    ApiKey,
    BusinessObject,
    Employee,
    Tenant,
    TenantSkill,
    Todo,
    User,
    UserSession,
    hash_api_key,
)

from conftest import make_client


TENANT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"
EMPLOYEE_ID = "44444444-4444-4444-4444-444444444444"
SESSION_TOKEN = "console-session-token"
SERVICE_KEY = "console-service-key"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    now = datetime.now(timezone.utc)
    with make_client(
        [
            Tenant(id=TENANT_ID, name="Acme Corp", email_domain="acme.example"),
            Tenant(id=OTHER_TENANT_ID, name="Other Corp", email_domain="other.example"),
            Employee(id=EMPLOYEE_ID, tenant_id=TENANT_ID, name="Alice Employee"),
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                email="alice@acme.example",
                name="Alice Admin",
                role="admin",
                status="active",
            ),
            User(
                tenant_id=TENANT_ID,
                email="active@acme.example",
                role="member",
                status="active",
            ),
            User(
                tenant_id=TENANT_ID,
                email="disabled@acme.example",
                role="member",
                status="disabled",
            ),
            User(
                tenant_id=OTHER_TENANT_ID,
                email="user@other.example",
                role="admin",
                status="active",
            ),
            UserSession(
                user_id=USER_ID,
                token_hash=hash_token(SESSION_TOKEN),
                expires_at=now + timedelta(hours=1),
            ),
            ApiKey(
                tenant_id=TENANT_ID,
                key_hash=hash_api_key(SERVICE_KEY),
                label="service",
            ),
            BusinessObject(
                tenant_id=TENANT_ID,
                object_type="request",
                title="Active object",
            ),
            BusinessObject(
                tenant_id=TENANT_ID,
                object_type="request",
                title="Deleted object",
                deleted_at=now,
            ),
            BusinessObject(
                tenant_id=OTHER_TENANT_ID,
                object_type="request",
                title="Other tenant object",
            ),
            TenantSkill(
                tenant_id=TENANT_ID,
                name="active-skill",
                files_jsonb={"SKILL.md": "# Active"},
                status="active",
            ),
            TenantSkill(
                tenant_id=TENANT_ID,
                name="archived-skill",
                files_jsonb={"SKILL.md": "# Archived"},
                status="archived",
            ),
            Todo(
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                entity_type="business_object",
                entity_id="55555555-5555-5555-5555-555555555555",
                title="Overdue",
                status="open",
                due_at=now - timedelta(days=1),
            ),
            Todo(
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                entity_type="business_object",
                entity_id="66666666-6666-6666-6666-666666666666",
                title="Due later",
                status="open",
                due_at=now + timedelta(days=1),
            ),
            Todo(
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                entity_type="business_object",
                entity_id="77777777-7777-7777-7777-777777777777",
                title="Already completed",
                status="completed",
                due_at=now - timedelta(days=2),
            ),
        ]
    ) as test_client:
        yield test_client


def user_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SESSION_TOKEN}"}


def test_bootstrap_returns_authenticated_user_and_tenant_context(client: TestClient) -> None:
    response = client.get("/api/v1/console/bootstrap", headers=user_headers())

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "user": {
                "id": USER_ID,
                "email": "alice@acme.example",
                "name": "Alice Admin",
            },
            "tenant": {
                "id": TENANT_ID,
                "name": "Acme Corp",
                "email_domain": "acme.example",
            },
            "role": "admin",
            "permissions": sorted(DEFAULT_ROLE_PERMISSIONS["admin"]),
            "employee_id": EMPLOYEE_ID,
        },
        "meta": {},
    }


def test_dashboard_counts_only_current_tenant_records(client: TestClient) -> None:
    response = client.get("/api/v1/console/dashboard", headers=user_headers())

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "counts": {
                "users": 2,
                "todos_open": 2,
                "todos_overdue": 1,
                "objects": 1,
                "skills": 1,
            }
        },
        "meta": {},
    }


@pytest.mark.parametrize("path", ["bootstrap", "dashboard"])
def test_console_endpoints_require_user_credentials(client: TestClient, path: str) -> None:
    missing = client.get(f"/api/v1/console/{path}")
    service = client.get(
        f"/api/v1/console/{path}",
        headers={"X-API-Key": SERVICE_KEY},
    )

    assert missing.status_code == 401
    assert service.status_code == 403
    assert service.json()["detail"] == "this endpoint requires a user credential, not a service key"
