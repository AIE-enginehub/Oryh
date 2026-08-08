from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token link found in email body: {body!r}")


def register_and_verify(
    test_client: TestClient,
    email: str = "alice@acme-corp.com",
    company_name: str = "Acme Corp",
    password: str = "s3cret-pass",
) -> dict:
    """A tenant with an admin, however it came to exist. What these tests
    are about — invitations, sessions, attribution, user management — is the
    same whether the workspace arrived through cloud registration or a
    standalone first boot, so they no longer insist on the former."""
    return bootstrap_tenant(
        test_client, company_name=company_name, email=email, password=password
    )


def session_headers(session_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {session_token}"}


def api_key_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_invitation_flow_and_member_restrictions(client: TestClient) -> None:
    data = register_and_verify(client)
    admin_headers = session_headers(data["session_token"])
    service_headers = api_key_headers(data["plain_text_api_key"])

    # admin creates two employees
    response = client.post("/api/v1/employees", json={"name": "Bob"}, headers=admin_headers)
    assert response.status_code == 201
    bob_employee_id = response.json()["data"]["id"]
    response = client.post("/api/v1/employees", json={"name": "Carol"}, headers=admin_headers)
    carol_employee_id = response.json()["data"]["id"]

    # invite Bob as member linked to his employee record; personal email allowed for invites
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": "bob@gmail.com", "role": "member", "employee_id": bob_employee_id},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    invite_token = extract_token(outbox.messages[-1].body)
    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": invite_token, "password": "bob-s3cret", "name": "Bob"},
    )
    assert response.status_code == 200, response.text
    bob_session = response.json()["data"]["session_token"]
    bob_user_id = response.json()["data"]["user"]["id"]

    # member cannot manage users or api keys
    assert client.get("/api/v1/auth/users", headers=session_headers(bob_session)).status_code == 403
    assert client.get("/api/v1/tenant/api-keys", headers=session_headers(bob_session)).status_code == 403
    assert client.post("/api/v1/employees", json={"name": "Eve"}, headers=session_headers(bob_session)).status_code == 403

    # admin issues a user-bound agent key for Bob
    response = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "bob-agent", "user_id": bob_user_id},
        headers=service_headers,
    )
    assert response.status_code == 201, response.text
    bob_key = response.json()["data"]["plain_text_api_key"]
    assert response.json()["data"]["api_key"]["role"] == "member"

    # Bob's agent can create his own timesheet header
    response = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": bob_employee_id, "period_start": "2026-06-01", "period_end": "2026-06-07"},
        headers=api_key_headers(bob_key),
    )
    assert response.status_code == 201, response.text
    bob_header_id = response.json()["data"]["id"]

    # ...but not Carol's
    response = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": carol_employee_id, "period_start": "2026-06-01", "period_end": "2026-06-07"},
        headers=api_key_headers(bob_key),
    )
    assert response.status_code == 403

    # PATCH is member-restricted too: Bob may edit his own header but not
    # Carol's — approvers never patch status; the flow admin (service) does
    response = client.patch(
        f"/api/v1/timesheet-headers/{bob_header_id}",
        json={"source_report_text": "本周主要做回归测试"},
        headers=api_key_headers(bob_key),
    )
    assert response.status_code == 200
    carol_header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": carol_employee_id, "period_start": "2026-06-01", "period_end": "2026-06-07"},
        headers=service_headers,
    ).json()["data"]["id"]
    response = client.patch(
        f"/api/v1/timesheet-headers/{carol_header}",
        json={"source_report_text": "tamper"},
        headers=api_key_headers(bob_key),
    )
    assert response.status_code == 403

    # no self-approval: members cannot patch status, not even on their own
    # header — flow advancement needs the admin/service credential
    client.post(f"/api/v1/timesheet-headers/{bob_header_id}/submit", json={}, headers=api_key_headers(bob_key))
    response = client.patch(
        f"/api/v1/timesheet-headers/{bob_header_id}",
        json={"status": "approved"},
        headers=api_key_headers(bob_key),
    )
    assert response.status_code == 403

    # same for business objects: members may edit fields but not advance status
    claim_id = client.post(
        "/api/v1/business-objects",
        json={"object_type": "claim", "title": "Bob's claim"},
        headers=api_key_headers(bob_key),
    ).json()["data"]["id"]
    assert client.patch(
        f"/api/v1/business-objects/{claim_id}", json={"title": "Bob's claim v2"},
        headers=api_key_headers(bob_key),
    ).status_code == 200
    assert client.patch(
        f"/api/v1/business-objects/{claim_id}", json={"status": "approved"},
        headers=api_key_headers(bob_key),
    ).status_code == 403


def test_actor_attribution_overrides_self_reported_ids(client: TestClient) -> None:
    data = register_and_verify(client)
    admin_headers = session_headers(data["session_token"])
    service_headers = api_key_headers(data["plain_text_api_key"])
    admin_user_id = data["user"]["id"]

    # user-kind actor: created_by is forced to the authenticated user
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "warranty_card", "title": "Card A", "created_by": "someone-else"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["created_by"] == f"user:{admin_user_id}"

    # service key keeps explicit attribution (agent behavior)
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "warranty_card", "title": "Card B", "created_by": "agent-01"},
        headers=service_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["created_by"] == "agent-01"


def test_logout_revokes_session(client: TestClient) -> None:
    data = register_and_verify(client)
    headers = session_headers(data["session_token"])
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_user_management(client: TestClient) -> None:
    data = register_and_verify(client)
    admin_headers = session_headers(data["session_token"])
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": "dave@acme-corp.com", "role": "member"},
        headers=admin_headers,
    )
    dave_id = response.json()["data"]["id"]

    response = client.get("/api/v1/auth/users", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 2

    # promote and disable
    response = client.patch(f"/api/v1/auth/users/{dave_id}", json={"role": "admin"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"
    response = client.patch(f"/api/v1/auth/users/{dave_id}", json={"status": "disabled"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "disabled"


def test_admin_changes_email_and_resends_invitation(client: TestClient) -> None:
    data = register_and_verify(client)
    admin_headers = session_headers(data["session_token"])
    admin_email = data["user"]["email"]

    # invite with a typo'd address
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": "typo@wrong-domain.com", "role": "member", "name": "Dave"},
        headers=admin_headers,
    )
    dave_id = response.json()["data"]["id"]
    first_token = extract_token(outbox.messages[-1].body)

    # email cannot collide with an existing user
    response = client.patch(
        f"/api/v1/auth/users/{dave_id}", json={"email": admin_email}, headers=admin_headers
    )
    assert response.status_code == 409

    # fix the address (normalized to lowercase) and resend the invitation
    response = client.patch(
        f"/api/v1/auth/users/{dave_id}", json={"email": "Dave@Acme-Corp.com"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "dave@acme-corp.com"

    response = client.post(f"/api/v1/auth/users/{dave_id}/resend-invitation", headers=admin_headers)
    assert response.status_code == 200
    assert outbox.messages[-1].to == "dave@acme-corp.com"
    second_token = extract_token(outbox.messages[-1].body)
    assert second_token != first_token

    # the old token is dead; the fresh one works
    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": first_token, "password": "dave-s3cret"},
    )
    assert response.status_code == 400
    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": second_token, "password": "dave-s3cret"},
    )
    assert response.status_code == 200, response.text

    # an accepted (active) user cannot be re-invited
    response = client.post(f"/api/v1/auth/users/{dave_id}/resend-invitation", headers=admin_headers)
    assert response.status_code == 409

    # changing an active user's email changes their login identifier
    response = client.patch(
        f"/api/v1/auth/users/{dave_id}", json={"email": "david@acme-corp.com"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert client.post(
        "/api/v1/auth/login", json={"email": "dave@acme-corp.com", "password": "dave-s3cret"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": "david@acme-corp.com", "password": "dave-s3cret"}
    ).status_code == 200
