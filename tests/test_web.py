from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token link found in email body: {body!r}")


def register_via_web(client: TestClient) -> str:
    """A workspace with a service key. It used to be created by driving the
    registration pages; these tests are about what happens AFTER a workspace
    exists, and a standalone deployment has one without ever serving those
    pages."""
    return bootstrap_tenant(
        client,
        company_name="Acme Corp",
        email="alice@acme-corp.com",
        password="s3cret-pass",
    )["plain_text_api_key"]


def invite_and_read_link(client: TestClient, service_key: str, email: str) -> str:
    """Send an invitation and return the link the mail carried. Any outbound
    mail would do; an invitation is the one every deployment sends."""
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "role": "member"},
        headers={"X-API-Key": service_key},
    )
    assert response.status_code == 201, response.text
    body = outbox.messages[-1].body
    return next(line.strip() for line in body.splitlines() if "token=" in line)

def test_public_web_login_and_logout_remain_available(client: TestClient) -> None:
    register_via_web(client)
    client.cookies.clear()

    login_page = client.get("/web/login")
    assert 'href="/console/login?mode=reset"' in login_page.text

    response = client.post(
        "/web/login",
        data={"email": "alice@acme-corp.com", "password": "wrong"},
    )
    assert "invalid email or password" in response.text

    response = client.post(
        "/web/login",
        data={"email": "alice@acme-corp.com", "password": "s3cret-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/console/dashboard"
    assert client.cookies.get("oryh_session")

    # The retired dashboard is a compatibility redirect, even while signed in.
    dashboard = client.get("/web/dashboard", follow_redirects=False)
    assert dashboard.status_code == 308
    assert dashboard.headers["location"] == "/console/dashboard"

    response = client.post("/web/logout", follow_redirects=False)
    assert response.status_code == 303
    assert client.cookies.get("oryh_session") is None


def test_password_reset_link_uses_reset_specific_copy(client: TestClient) -> None:
    response = client.get("/web/invitations/accept?mode=reset&token=one-time-token")
    assert response.status_code == 200
    assert "Reset your password" in response.text
    assert "Set new password" in response.text
    assert 'name="mode" value="reset"' in response.text
    assert 'name="name"' not in response.text


def test_public_web_invitation_acceptance_remains_available(client: TestClient) -> None:
    service_key = register_via_web(client)
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "bob@gmail.com", "role": "member", "name": "Bob"},
        headers={"X-API-Key": service_key},
    )
    assert invited.status_code == 201, invited.text
    invite_token = extract_token(outbox.messages[-1].body)

    bob = TestClient(app)
    page = bob.get(f"/web/invitations/accept?token={invite_token}")
    assert page.status_code == 200
    assert "Accept invitation" in page.text
    assert 'name="name"' not in page.text
    assert 'name="password_confirmation"' in page.text
    accepted = bob.post(
        "/web/invitations/accept",
        data={"token": invite_token, "password": "bob-s3cret", "password_confirmation": "bob-s3cret"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/console/dashboard"
    assert bob.cookies.get("oryh_session")


def test_web_invitation_accept_requires_matching_passwords(client: TestClient) -> None:
    service_key = register_via_web(client)
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "bob@gmail.com", "role": "member", "name": "Bob"},
        headers={"X-API-Key": service_key},
    )
    assert invited.status_code == 201, invited.text
    invite_token = extract_token(outbox.messages[-1].body)

    bob = TestClient(app)
    response = bob.post(
        "/web/invitations/accept",
        data={"token": invite_token, "password": "bob-s3cret", "password_confirmation": "different-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "passwords do not match" in response.text
    assert bob.cookies.get("oryh_session") is None


@pytest.mark.parametrize(
    ("legacy_path", "successor"),
    (
        ("/web", "/console/dashboard"),
        ("/web/", "/console/dashboard"),
        ("/web/dashboard", "/console/dashboard"),
        ("/web/users", "/console/users"),
        ("/web/employees", "/console/employees"),
        ("/web/projects", "/console/projects"),
        ("/web/vendors", "/console/vendors"),
        ("/web/products", "/console/products"),
        ("/web/resources", "/console/resources"),
        ("/web/skills", "/console/skills"),
        ("/web/skills/sample-skill", "/console/skills"),
        ("/web/api-keys", "/console/api-keys"),
        ("/web/todos", "/console/todos"),
        ("/web/approvals", "/console/approvals"),
        ("/web/roles", "/console/roles"),
        ("/web/object-types", "/console/object-types"),
        ("/web/objects", "/console/objects"),
        ("/web/attachments/attachment-123/content", "/console/objects"),
        (
            "/web/objects/business_object/record-123",
            "/console/objects/business_object/record-123",
        ),
    ),
)
def test_retired_tenant_get_routes_permanently_redirect_to_react(
    client: TestClient,
    legacy_path: str,
    successor: str,
) -> None:
    response = client.get(legacy_path, follow_redirects=False)
    assert response.status_code == 308, (legacy_path, response.text)
    assert response.headers["location"] == successor
    assert response.headers["deprecation"] == "true"
    assert response.headers["x-oryh-legacy-surface"] == "tenant"


def test_retired_tenant_head_route_uses_the_same_successor(client: TestClient) -> None:
    response = client.head("/web/projects", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/console/projects"
    assert response.headers["link"] == '</console/projects>; rel="successor-version"'
    assert response.content == b""


@pytest.mark.parametrize(
    "legacy_path",
    (
        "/web/users/invite",
        "/web/users/user-123/skill-bundle",
        "/web/users/user-123/update",
        "/web/users/user-123/resend-invite",
        "/web/employees/create",
        "/web/employees/employee-123/status",
        "/web/projects/save",
        "/web/projects/project-123/archive",
        "/web/vendors/save",
        "/web/vendors/vendor-123/archive",
        "/web/products/product-123/skus/save",
        "/web/product-skus/sku-123/archive",
        "/web/products/save",
        "/web/products/product-123/archive",
        "/web/resources/save",
        "/web/resources/resource-123/archive",
        "/web/skills/save",
        "/web/skills/skill-123/status",
        "/web/api-keys/create",
        "/web/api-keys/key-123/deactivate",
        "/web/todos/todo-123/complete",
        "/web/roles/save",
        "/web/roles/role-123/delete",
        "/web/capabilities/create",
        "/web/capabilities/capability-123/delete",
        "/web/workflows/publish",
        "/web/object-types/create",
        "/web/object-types/definition-123/status",
    ),
)
def test_retired_tenant_unsafe_routes_are_gone(client: TestClient, legacy_path: str) -> None:
    response = client.post(legacy_path, follow_redirects=False)
    assert response.status_code == 410, (legacy_path, response.text)
    assert response.headers["deprecation"] == "true"
    assert response.headers["x-oryh-legacy-surface"] == "tenant"


def test_retired_tenant_write_has_no_side_effect(client: TestClient) -> None:
    service_key = register_via_web(client)
    headers = {"X-API-Key": service_key}
    before = client.get("/api/v1/projects", headers=headers).json()["data"]
    email_count = len(outbox.messages)

    response = client.post(
        "/web/projects/save",
        data={"project_name": "Must Not Exist", "status": "active"},
        follow_redirects=False,
    )

    assert response.status_code == 410
    assert client.get("/api/v1/projects", headers=headers).json()["data"] == before
    assert len(outbox.messages) == email_count


def _verify_link(body: str) -> str:
    return next(line.strip() for line in body.splitlines() if "verify-email" in line)


def test_email_link_follows_request_host_when_base_url_unset(client: TestClient) -> None:
    """With no canonical URL configured, a link must point back at the host the
    request actually arrived on — which is what makes a deployment reachable at
    an address nobody told the server about."""
    service_key = register_via_web(client)
    console = TestClient(app, base_url="http://console.example.com")
    link = invite_and_read_link(console, service_key, "dana@acme-corp.com")

    assert link.startswith("http://console.example.com/")


def test_email_link_prefers_explicit_base_url(client: TestClient, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "base_url", "https://canonical.example.com")
    service_key = register_via_web(client)
    console = TestClient(app, base_url="http://internal-host:8000")
    link = invite_and_read_link(console, service_key, "erin@acme-corp.com")

    assert link.startswith("https://canonical.example.com/")
