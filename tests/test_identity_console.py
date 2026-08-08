from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import emails
from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token in email body: {body!r}")


def provision_tenant(client: TestClient, slug: str = "identity") -> dict:
    data = bootstrap_tenant(client, company_name=f"{slug.title()} Co", email=f"admin@{slug}.example", password="admin-pass1")
    return {
        "tenant_id": data["tenant"]["id"],
        "service": {"X-API-Key": data["plain_text_api_key"]},
        "admin": {"Authorization": f"Bearer {data['session_token']}"},
    }


def invite(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    name: str | None = None,
    role: str = "member",
    extra_headers: dict[str, str] | None = None,
):
    request_headers = {**headers, **(extra_headers or {})}
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "name": name, "role": role},
        headers=request_headers,
    )
    assert response.status_code == 201, response.text
    return response


def accept_and_issue_key(
    client: TestClient,
    service: dict[str, str],
    invitation_response,
) -> dict[str, str]:
    user_id = invitation_response.json()["data"]["id"]
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": extract_token(outbox.messages[-1].body), "password": "invitee-pass1"},
    )
    assert accepted.status_code == 200, accepted.text
    key = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "identity-test", "user_id": user_id},
        headers=service,
    )
    assert key.status_code == 201, key.text
    return {"X-API-Key": key.json()["data"]["plain_text_api_key"]}


def test_display_name_resolver_is_bounded_authorized_and_tenant_scoped(
    client: TestClient,
) -> None:
    first = provision_tenant(client, "names-first")
    second = provision_tenant(client, "names-second")
    first_employee = client.post(
        "/api/v1/employees", json={"name": "First Employee"}, headers=first["service"]
    ).json()["data"]
    second_employee = client.post(
        "/api/v1/employees", json={"name": "Second Employee"}, headers=second["service"]
    ).json()["data"]

    invitation = invite(
        client,
        first["service"],
        email="member@names-first.example",
        name="First Member",
    )
    first_user_id = invitation.json()["data"]["id"]
    member_headers = accept_and_issue_key(client, first["service"], invitation)

    second_user = client.get(
        "/api/v1/auth/users", headers=second["service"]
    ).json()["data"][0]
    first_keys = client.get(
        "/api/v1/tenant/api-keys", headers=first["service"]
    ).json()["data"]
    second_key = client.get(
        "/api/v1/tenant/api-keys", headers=second["service"]
    ).json()["data"][0]
    first_service_key = next(key for key in first_keys if key["user_id"] is None)

    response = client.post(
        "/api/v1/directory/display-names/resolve",
        json={
            "employee_ids": [
                first_employee["id"],
                first_employee["id"],
                second_employee["id"],
            ],
            "actor_labels": [
                f"user:{first_user_id}",
                f"user:{first_user_id}",
                f"user:{second_user['id']}",
                f"key:{first_service_key['id']}",
                f"key:{second_key['id']}",
                "system:unresolved",
            ],
        },
        headers=first["service"],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["employees"] == {first_employee["id"]: "First Employee"}
    assert data["actors"] == {
        f"user:{first_user_id}": "First Member",
        f"key:{first_service_key['id']}": (
            f"key:{first_service_key['label'] or first_service_key['id'][:8]}"
        ),
    }
    member_response = client.post(
        "/api/v1/directory/display-names/resolve",
        json={"employee_ids": [first_employee["id"]], "actor_labels": []},
        headers=member_headers,
    )
    assert member_response.status_code == 200
    assert member_response.json()["data"]["employees"] == {
        first_employee["id"]: "First Employee"
    }

    too_many = client.post(
        "/api/v1/directory/display-names/resolve",
        json={"employee_ids": [str(uuid4()) for _ in range(201)], "actor_labels": []},
        headers=first["service"],
    )
    assert too_many.status_code == 422
    oversized_duplicates = client.post(
        "/api/v1/directory/display-names/resolve",
        json={"employee_ids": [first_employee["id"]] * 201, "actor_labels": []},
        headers=first["service"],
    )
    assert oversized_duplicates.status_code == 422


def test_access_changes_leave_an_audit_trail(client: TestClient) -> None:
    """Who can do what must be answerable after the fact.

    Changing a ROLE's permissions was always audited; changing which role a
    PERSON holds — the more consequential of the two — was not, so a granted
    capability or a disabled account had no trail at all. Found in the
    multi-agent e2e run when an admin agent was asked to record who may place
    purchase orders and correctly refused to invent a write path.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]

    invited = invite(client, service, email="newhire@identity.example", name="New Hire")
    user_id = invited.json()["data"]["id"]

    def actions() -> list[dict]:
        rows = client.get("/api/v1/audit-logs?limit=50", headers=service).json()["data"]
        return [r for r in rows if r["entity_type"] == "user"]

    invited_events = [r for r in actions() if r["action"] == "user.invited"]
    assert invited_events, "inviting a user must be audited"
    assert invited_events[0]["detail"]["email"] == "newhire@identity.example"

    # a role change records what moved, not merely that something did
    assert client.patch(
        f"/api/v1/auth/users/{user_id}", json={"role": "admin"}, headers=service
    ).status_code == 200
    updated = [r for r in actions() if r["action"] == "user.updated"]
    assert updated, "changing which role a person holds must be audited"
    assert updated[0]["detail"]["role"] == {"from": "member", "to": "admin"}

    # disabling an account is an access change too
    assert client.patch(
        f"/api/v1/auth/users/{user_id}", json={"status": "disabled"}, headers=service
    ).status_code == 200
    statuses = [
        r for r in actions()
        if r["action"] == "user.updated" and "status" in r["detail"]
    ]
    assert statuses[0]["detail"]["status"] == {"from": "invited", "to": "disabled"}

    # a no-op PATCH writes no trail — the log should carry decisions, not noise
    before = len(actions())
    assert client.patch(
        f"/api/v1/auth/users/{user_id}", json={"status": "disabled"}, headers=service
    ).status_code == 200
    assert len(actions()) == before


def test_user_list_optional_pagination_and_filters(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    invited = [
        invite(client, service, email="lead@identity.example", name="Ops Lead"),
        invite(client, service, email="ops-mail@identity.example", name="Finance"),
        invite(client, service, email="hr@identity.example", name="HR"),
        invite(client, service, email="delegate@identity.example", name="Admin Delegate", role="admin"),
        invite(client, service, email="other@identity.example", name="Other Admin", role="admin"),
    ]
    disabled_id = invited[2].json()["data"]["id"]
    assert client.patch(
        f"/api/v1/auth/users/{disabled_id}",
        json={"status": "disabled"},
        headers=service,
    ).status_code == 200

    # Supplying size without page keeps the historical full-list response.
    full = client.get("/api/v1/auth/users?size=1", headers=service).json()
    assert len(full["data"]) == 6  # tenant admin + five invitees
    assert full["meta"] == {"total": 6}
    assert all("invitation_url" not in row for row in full["data"])

    keyword = client.get("/api/v1/auth/users?keyword=ops&page=1&size=10", headers=service).json()
    assert {row["email"] for row in keyword["data"]} == {
        "lead@identity.example",
        "ops-mail@identity.example",
    }
    assert keyword["meta"] == {"total": 2, "page": 1, "page_size": 10, "pages": 1}

    first = client.get(
        "/api/v1/auth/users?status=invited&role=member&page=1&size=1",
        headers=service,
    ).json()
    second = client.get(
        "/api/v1/auth/users?status=invited&role=member&page=2&size=1",
        headers=service,
    ).json()
    assert first["meta"] == {"total": 2, "page": 1, "page_size": 1, "pages": 2}
    assert second["meta"] == {"total": 2, "page": 2, "page_size": 1, "pages": 2}
    assert first["data"][0]["id"] != second["data"][0]["id"]
    # Stable ordering gives the same page on a repeated request.
    repeated = client.get(
        "/api/v1/auth/users?status=invited&role=member&page=1&size=1",
        headers=service,
    ).json()
    assert repeated["data"][0]["id"] == first["data"][0]["id"]

    empty = client.get(
        "/api/v1/auth/users?keyword=missing&page=1", headers=service
    ).json()
    assert empty["data"] == []
    assert empty["meta"] == {"total": 0, "page": 1, "page_size": 50, "pages": 1}

    for query in ("page=0", "page=1&size=0", "page=1&size=201", "status=unknown&page=1"):
        assert client.get(f"/api/v1/auth/users?{query}", headers=service).status_code == 422


def test_console_invitation_urls_are_additive_and_smtp_hides_them(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    monkeypatch.setattr(settings, "base_url", "")
    forwarded = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "console.oryh.test",
    }
    first = invite(
        client,
        service,
        email="console-invite@identity.example",
        name="Console Invite",
        extra_headers=forwarded,
    )
    first_data = first.json()["data"]
    first_token = extract_token(outbox.messages[-1].body)
    assert first_data["id"] and first_data["email"] == "console-invite@identity.example"
    assert first_data["invitation_pending"] is True
    assert first_data["invitation_url"] == (
        f"https://console.oryh.test/web/invitations/accept?token={first_token}"
    )
    duplicate = client.post(
        "/api/v1/auth/invitations",
        json={"email": "console-invite@identity.example", "role": "member"},
        headers=service,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "email cannot be used for this invitation"

    resent = client.post(
        f"/api/v1/auth/users/{first_data['id']}/resend-invitation",
        headers={**service, **forwarded},
    )
    assert resent.status_code == 200, resent.text
    second_token = extract_token(outbox.messages[-1].body)
    assert second_token != first_token
    assert resent.json()["data"]["id"] == first_data["id"]
    assert resent.json()["data"]["invitation_url"] == (
        f"https://console.oryh.test/web/invitations/accept?token={second_token}"
    )
    # Resending replaced the token rather than leaving two usable links.
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": first_token, "password": "invitee-pass1"},
    ).status_code == 400

    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "base_url", "https://app.oryh.test")
    monkeypatch.setattr(emails, "_send_smtp", lambda _message: None)
    smtp = invite(
        client,
        service,
        email="smtp-invite@identity.example",
        name="SMTP Invite",
        extra_headers=forwarded,
    )
    assert smtp.json()["data"]["id"]
    assert "invitation_url" not in smtp.json()["data"]
    assert "https://app.oryh.test/web/invitations/accept?token=" in outbox.messages[-1].body


def test_tenant_password_reset_email_keeps_access_until_the_link_is_accepted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = provision_tenant(client, "password-reset")
    invitation = invite(
        client,
        ctx["service"],
        email="member@password-reset.example",
        name="Reset Target",
    )
    user_id = invitation.json()["data"]["id"]
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": extract_token(outbox.messages[-1].body), "password": "member-old-pass"},
    )
    assert accepted.status_code == 200, accepted.text
    old_session = accepted.json()["data"]["session_token"]
    member_headers = {"Authorization": f"Bearer {old_session}"}

    # Ordinary members cannot send reset emails, including to themselves.
    assert client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=member_headers,
    ).status_code == 403

    monkeypatch.setattr(settings, "base_url", "")
    forwarded = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "console.oryh.test",
    }
    first = client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers={**ctx["service"], **forwarded},
    )
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    first_data = first.json()["data"]
    first_token = extract_token(outbox.messages[-1].body)
    assert first_data["user"]["id"] == user_id
    assert first_data["email_sent"] is True
    assert "reset_url" not in first_data
    assert "重置" in outbox.messages[-1].subject
    assert (
        f"https://console.oryh.test/web/invitations/accept?mode=reset&token={first_token}"
        in outbox.messages[-1].body
    )
    assert "60 分钟" in outbox.messages[-1].body
    assert "member-old-pass" not in outbox.messages[-1].body

    # Re-sending rotates the token. Neither send changes the current password
    # or revokes a live session before the recipient accepts the link.
    second = client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers={**ctx["service"], **forwarded},
    )
    assert second.status_code == 200, second.text
    second_token = extract_token(outbox.messages[-1].body)
    assert second_token != first_token
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": first_token, "password": "must-not-win"},
    ).status_code == 400
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "member@password-reset.example", "password": "member-old-pass"},
    ).status_code == 200
    assert client.get("/api/v1/auth/me", headers=member_headers).status_code == 200

    completed = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": second_token,
            "password": "member-new-pass",
            "name": "Must Not Rename Active User",
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["user"]["name"] == "Reset Target"
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "member@password-reset.example", "password": "member-old-pass"},
    ).status_code == 401
    assert client.get("/api/v1/auth/me", headers=member_headers).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "member@password-reset.example", "password": "member-new-pass"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": second_token, "password": "single-use-only"},
    ).status_code == 400


def test_password_reset_email_guards_isolation_and_delivery_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = provision_tenant(client, "reset-guards")
    second = provision_tenant(client, "reset-foreign")
    pending = invite(
        client,
        first["service"],
        email="pending@reset-guards.example",
        name="Pending User",
    )
    user_id = pending.json()["data"]["id"]
    invite_token = extract_token(outbox.messages[-1].body)

    assert client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=first["service"],
    ).status_code == 409
    assert client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=second["service"],
    ).status_code == 404

    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": invite_token, "password": "pending-pass1"},
    )
    assert accepted.status_code == 200, accepted.text
    active_session = accepted.json()["data"]["session_token"]
    issued = client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=first["service"],
    )
    assert issued.status_code == 200, issued.text
    old_email_token = extract_token(outbox.messages[-1].body)
    assert client.patch(
        f"/api/v1/auth/users/{user_id}",
        json={"email": "renamed@reset-guards.example"},
        headers=first["service"],
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": old_email_token, "password": "old-email-must-not-win"},
    ).status_code == 400

    issued_after_rename = client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=first["service"],
    )
    assert issued_after_rename.status_code == 200, issued_after_rename.text
    reset_token = extract_token(outbox.messages[-1].body)
    assert client.patch(
        f"/api/v1/auth/users/{user_id}",
        json={"status": "disabled"},
        headers=first["service"],
    ).status_code == 200
    assert client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=first["service"],
    ).status_code == 409
    assert client.patch(
        f"/api/v1/auth/users/{user_id}",
        json={"status": "active"},
        headers=first["service"],
    ).status_code == 200
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {active_session}"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": reset_token, "password": "stale-link-pass"},
    ).status_code == 400

    monkeypatch.setattr(settings, "password_reset_token_ttl_minutes", 0)
    expired = client.post(
        f"/api/v1/auth/users/{user_id}/password-reset-email",
        headers=first["service"],
    )
    assert expired.status_code == 200, expired.text
    expired_token = extract_token(outbox.messages[-1].body)
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": expired_token, "password": "expired-link-pass"},
    ).status_code == 400
    monkeypatch.setattr(settings, "password_reset_token_ttl_minutes", 60)

    admin_user = next(
        user
        for user in client.get("/api/v1/auth/users", headers=first["service"]).json()["data"]
        if user["role"] == "admin"
    )

    smtp_attempts = []

    def record_delivery(message) -> None:
        smtp_attempts.append(message)

    # SMTP reset links must use the configured canonical application origin;
    # never derive a security-sensitive link from request forwarding headers.
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "base_url", "")
    monkeypatch.setattr(emails, "_send_smtp", record_delivery)
    missing_origin = client.post(
        f"/api/v1/auth/users/{admin_user['id']}/password-reset-email",
        headers={**first["service"], "X-Forwarded-Host": "attacker.example"},
    )
    assert missing_origin.status_code == 200, missing_origin.text
    assert missing_origin.json()["data"]["email_sent"] is False
    assert smtp_attempts == []

    def fail_delivery(_message) -> None:
        raise emails.EmailDeliveryError("smtp unavailable")

    monkeypatch.setattr(settings, "base_url", "https://app.oryh.test")
    monkeypatch.setattr(emails, "_send_smtp", fail_delivery)
    failed = client.post(
        f"/api/v1/auth/users/{admin_user['id']}/password-reset-email",
        headers=first["service"],
    )
    assert failed.status_code == 200, failed.text
    assert failed.headers["cache-control"] == "no-store"
    assert failed.json()["data"]["email_sent"] is False
    assert "reset_url" not in failed.json()["data"]
    assert client.get("/api/v1/auth/me", headers=first["admin"]).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@reset-guards.example", "password": "admin-pass1"},
    ).status_code == 200


def test_users_manage_and_tenant_isolation(client: TestClient) -> None:
    first = provision_tenant(client, "identity-one")
    second = provision_tenant(client, "identity-two")
    pending = invite(
        client,
        first["service"],
        email="member@identity-one.example",
        name="Member",
    )
    pending_id = pending.json()["data"]["id"]
    member = accept_and_issue_key(client, first["service"], pending)

    assert client.get("/api/v1/auth/users", headers=member).status_code == 403
    assert client.post(
        "/api/v1/auth/invitations",
        json={"email": "blocked@identity-one.example", "role": "member"},
        headers=member,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/auth/users/{pending_id}", json={"name": "Blocked"}, headers=member
    ).status_code == 403
    assert client.post(
        f"/api/v1/auth/users/{pending_id}/resend-invitation", headers=member
    ).status_code == 403

    # Tenant-scoped management credentials neither list nor mutate foreign users.
    second_list = client.get("/api/v1/auth/users?page=1", headers=second["service"]).json()
    assert {row["tenant_id"] for row in second_list["data"]} == {second["tenant_id"]}
    assert pending_id not in {row["id"] for row in second_list["data"]}
    assert client.patch(
        f"/api/v1/auth/users/{pending_id}", json={"name": "Cross Tenant"}, headers=second["service"]
    ).status_code == 404
    assert client.post(
        f"/api/v1/auth/users/{pending_id}/resend-invitation", headers=second["service"]
    ).status_code == 404


def test_identity_mutations_keep_an_active_users_manager(client: TestClient) -> None:
    ctx = provision_tenant(client, "lockout")
    users = client.get("/api/v1/auth/users", headers=ctx["service"]).json()["data"]
    original_admin_id = next(user["id"] for user in users if user["role"] == "admin")

    # The only human manager cannot demote or disable themselves, regardless
    # of whether the request uses their session or the tenant recovery key.
    assert client.patch(
        f"/api/v1/auth/users/{original_admin_id}",
        json={"role": "member"},
        headers=ctx["admin"],
    ).status_code == 422
    assert client.patch(
        f"/api/v1/auth/users/{original_admin_id}",
        json={"status": "disabled"},
        headers=ctx["service"],
    ).status_code == 422

    custom_role = client.post(
        "/api/v1/roles",
        json={"name": "access_owner", "permissions": ["users.manage"]},
        headers=ctx["service"],
    )
    assert custom_role.status_code == 201, custom_role.text
    owner_invite = invite(
        client,
        ctx["service"],
        email="owner@lockout.example",
        role="access_owner",
    )
    owner_id = owner_invite.json()["data"]["id"]
    accept_and_issue_key(client, ctx["service"], owner_invite)

    # Once a second active manager exists, the original admin may be demoted.
    demoted = client.patch(
        f"/api/v1/auth/users/{original_admin_id}",
        json={"role": "member"},
        headers=ctx["service"],
    )
    assert demoted.status_code == 200, demoted.text

    # The custom role is now the final management path, so neither its grant
    # nor its final active assignee can be removed.
    assert client.patch(
        "/api/v1/roles/access_owner",
        json={"permissions": []},
        headers=ctx["service"],
    ).status_code == 422
    assert client.patch(
        f"/api/v1/auth/users/{owner_id}",
        json={"status": "disabled"},
        headers=ctx["service"],
    ).status_code == 422

    assert client.patch(
        f"/api/v1/auth/users/{original_admin_id}",
        json={"role": "admin"},
        headers=ctx["service"],
    ).status_code == 200
    assert client.patch(
        "/api/v1/roles/access_owner",
        json={"permissions": []},
        headers=ctx["service"],
    ).status_code == 200


def test_disabled_unverified_user_can_recover_only_through_invitation(client: TestClient) -> None:
    ctx = provision_tenant(client, "invite-recovery")
    pending = invite(
        client,
        ctx["service"],
        email="pending@invite-recovery.example",
    )
    pending_id = pending.json()["data"]["id"]

    activation = client.patch(
        f"/api/v1/auth/users/{pending_id}",
        json={"status": "active"},
        headers=ctx["service"],
    )
    assert activation.status_code == 422
    assert "accept an invitation" in activation.json()["detail"]

    assert client.patch(
        f"/api/v1/auth/users/{pending_id}",
        json={"status": "disabled"},
        headers=ctx["service"],
    ).status_code == 200
    recovered = client.post(
        f"/api/v1/auth/users/{pending_id}/resend-invitation",
        headers=ctx["service"],
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["data"]["status"] == "invited"
    fresh_token = extract_token(outbox.messages[-1].body)
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": fresh_token, "password": "recovered-pass1"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["user"]["invitation_pending"] is False

    # A verified account uses the normal active/disabled lifecycle and cannot
    # be converted back into an invitation.
    assert client.patch(
        f"/api/v1/auth/users/{pending_id}",
        json={"status": "disabled"},
        headers=ctx["service"],
    ).status_code == 200
    assert client.post(
        f"/api/v1/auth/users/{pending_id}/resend-invitation",
        headers=ctx["service"],
    ).status_code == 409


def test_role_capability_typed_crud_guards_and_isolation(client: TestClient) -> None:
    first = provision_tenant(client, "rbac-one")
    second = provision_tenant(client, "rbac-two")
    service = first["service"]

    capability = client.post(
        "/api/v1/capabilities",
        json={"name": "console.review", "title": "Console Review"},
        headers=service,
    )
    assert capability.status_code == 201, capability.text
    assert capability.json()["data"]["kind"] == "custom"

    role = client.post(
        "/api/v1/roles",
        json={
            "name": "console_reviewer",
            "title": "Console Reviewer",
            "permissions": ["console.review"],
        },
        headers=service,
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["data"]["id"]
    assert role.json()["data"]["permissions"] == ["console.review"]

    changed = client.patch(
        f"/api/v1/roles/{role_id}",
        json={"title": "Reviewer v2", "permissions": ["console.review", "todos.complete_own"]},
        headers=service,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["title"] == "Reviewer v2"
    assert "todos.complete_own" in changed.json()["data"]["permissions"]

    listed_roles = client.get("/api/v1/roles", headers=service).json()
    assert listed_roles["meta"]["total"] >= 3
    assert role_id in {row["id"] for row in listed_roles["data"]}
    catalog = client.get("/api/v1/capabilities", headers=service).json()
    assert set(catalog["data"]) == {"capabilities", "object_types"}
    assert "console.review" in {row["name"] for row in catalog["data"]["capabilities"]}

    # Read access remains open to an ordinary member; all writes remain users.manage-gated.
    member_invite = invite(
        client,
        service,
        email="reader@rbac-one.example",
        name="Reader",
    )
    member = accept_and_issue_key(client, service, member_invite)
    assert client.get("/api/v1/roles", headers=member).status_code == 200
    assert client.get("/api/v1/capabilities", headers=member).status_code == 200
    assert client.post(
        "/api/v1/roles", json={"name": "blocked", "permissions": []}, headers=member
    ).status_code == 403
    assert client.patch(
        f"/api/v1/roles/{role_id}", json={"title": "Blocked"}, headers=member
    ).status_code == 403
    assert client.post(
        "/api/v1/capabilities", json={"name": "blocked.cap"}, headers=member
    ).status_code == 403
    assert client.delete("/api/v1/capabilities/console.review", headers=member).status_code == 403

    # Existing lockout and reference protection stays intact.
    assert client.patch(
        "/api/v1/roles/admin",
        json={"permissions": ["timesheet.submit_own"]},
        headers=service,
    ).status_code == 422
    assert client.delete("/api/v1/roles/member", headers=service).status_code == 409
    assert client.delete("/api/v1/capabilities/users.manage", headers=service).status_code == 409
    assert client.delete("/api/v1/capabilities/console.review", headers=service).status_code == 409

    # Removing the custom role releases its custom capability for deletion.
    assert client.delete(f"/api/v1/roles/{role_id}", headers=service).status_code == 204
    assert client.delete("/api/v1/capabilities/console.review", headers=service).status_code == 204

    # Catalog and role identifiers are tenant-scoped.
    second_roles = client.get("/api/v1/roles", headers=second["service"]).json()["data"]
    assert role_id not in {row["id"] for row in second_roles}
    assert client.patch(
        f"/api/v1/roles/{role_id}", json={"title": "Foreign"}, headers=second["service"]
    ).status_code == 404
    second_caps = client.get("/api/v1/capabilities", headers=second["service"]).json()["data"]
    assert "console.review" not in {row["name"] for row in second_caps["capabilities"]}
    assert client.delete("/api/v1/capabilities/console.review", headers=second["service"]).status_code == 404


def test_identity_openapi_contracts_are_typed(client: TestClient) -> None:
    schema = app.openapi()
    refs = {
        ("/api/v1/auth/users", "get", "200"): "ListEnvelope_UserRead_",
        ("/api/v1/auth/invitations", "post", "201"): "Envelope_InvitationUserRead_",
        ("/api/v1/auth/users/{user_id}", "patch", "200"): "Envelope_UserRead_",
        ("/api/v1/auth/users/{user_id}/password-reset-email", "post", "200"): "Envelope_PasswordResetEmailRead_",
        ("/api/v1/auth/users/{user_id}/resend-invitation", "post", "200"): "Envelope_InvitationUserRead_",
        ("/api/v1/roles", "get", "200"): "ListEnvelope_RoleRead_",
        ("/api/v1/roles", "post", "201"): "Envelope_RoleRead_",
        ("/api/v1/roles/{role_ref}", "patch", "200"): "Envelope_RoleRead_",
        ("/api/v1/capabilities", "get", "200"): "Envelope_CapabilityCatalog_",
        ("/api/v1/capabilities", "post", "201"): "Envelope_CapabilityRead_",
    }
    for (path, method, code), model in refs.items():
        response_schema = schema["paths"][path][method]["responses"][code]["content"][
            "application/json"
        ]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{model}"}
