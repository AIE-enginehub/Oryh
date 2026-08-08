from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token link found in email body: {body!r}")


def register_and_verify(client: TestClient) -> dict:
    response = bootstrap_tenant(client, company_name="Acme Corp", email="alice@acme-corp.com", password="s3cret-pass")
    return response


def browser_login(client: TestClient):
    return client.post(
        "/api/v1/auth/browser/login",
        json={"email": "alice@acme-corp.com", "password": "s3cret-pass"},
    )


def test_browser_login_sets_host_only_cookies_without_exposing_session_token(client: TestClient) -> None:
    data = register_and_verify(client)
    client.cookies.clear()

    response = browser_login(client)

    assert response.json()["data"]["user"]["id"] == data["user"]["id"]
    assert response.json()["data"]["expires_at"]
    assert "session_token" not in response.json()["data"]
    assert response.json()["meta"] == {}
    assert response.headers["cache-control"] == "no-store"

    cookie_headers = response.headers.get_list("set-cookie")
    session_header = next(value for value in cookie_headers if value.startswith("oryh_session="))
    csrf_header = next(value for value in cookie_headers if value.startswith("oryh_csrf="))
    assert "HttpOnly" in session_header
    assert "HttpOnly" not in csrf_header
    for cookie_header in (session_header, csrf_header):
        assert "Path=/" in cookie_header
        assert "SameSite=lax" in cookie_header
        assert "Domain=" not in cookie_header
    assert client.cookies.get("oryh_session")
    assert client.cookies.get("oryh_csrf")


def test_browser_login_rejects_cross_origin_requests(client: TestClient) -> None:
    register_and_verify(client)
    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/browser/login",
        json={"email": "alice@acme-corp.com", "password": "s3cret-pass"},
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
    )

    assert "same-origin" in response.json()["detail"]
    assert client.cookies.get("oryh_session") is None


def test_login_password_reset_is_private_throttled_and_single_use(client: TestClient) -> None:
    register_and_verify(client)
    outbox.clear()

    requested = client.post(
        "/api/v1/auth/password-reset-email",
        json={"email": " Alice@Acme-Corp.com "},
    )

    assert requested.status_code == 202, requested.text
    assert requested.headers["cache-control"] == "no-store"
    generic_response = requested.json()
    assert "active account exists" in generic_response["data"]["message"]
    assert len(outbox.messages) == 1
    reset_token = extract_token(outbox.messages[-1].body)
    assert "mode=reset" in outbox.messages[-1].body

    # Repeated and unknown-address requests have the same response while the
    # cooldown prevents mailbox flooding and the body prevents enumeration.
    repeated = client.post(
        "/api/v1/auth/password-reset-email",
        json={"email": "alice@acme-corp.com"},
    )
    unknown = client.post(
        "/api/v1/auth/password-reset-email",
        json={"email": "unknown@acme-corp.com"},
    )
    assert repeated.status_code == unknown.status_code == 202
    assert repeated.json() == unknown.json() == generic_response
    assert len(outbox.messages) == 1

    # Requesting the link does not revoke the current password. Accepting it
    # rotates the credential, and the one-time token cannot be reused.
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "alice@acme-corp.com", "password": "s3cret-pass"},
    ).status_code == 200
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": reset_token, "password": "new-s3cret-pass"},
    )
    assert accepted.status_code == 200, accepted.text
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "alice@acme-corp.com", "password": "s3cret-pass"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "alice@acme-corp.com", "password": "new-s3cret-pass"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": reset_token, "password": "must-not-win"},
    ).status_code == 400


def test_login_password_reset_rejects_cross_origin_requests(client: TestClient) -> None:
    register_and_verify(client)
    outbox.clear()

    response = client.post(
        "/api/v1/auth/password-reset-email",
        json={"email": "alice@acme-corp.com"},
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
    )

    assert "same-origin" in response.json()["detail"]
    assert not outbox.messages


def test_cookie_auth_allows_safe_requests_and_requires_csrf_for_writes(client: TestClient) -> None:
    register_and_verify(client)
    client.cookies.clear()
    assert browser_login(client).status_code == 200

    assert client.get("/api/v1/auth/me").status_code == 200
    missing = client.post("/api/v1/employees", json={"name": "Bob"})
    assert missing.status_code == 403
    assert "CSRF" in missing.json()["detail"]
    wrong = client.post(
        "/api/v1/employees",
        json={"name": "Bob"},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert wrong.status_code == 403

    csrf_token = client.cookies.get("oryh_csrf")
    created = client.post(
        "/api/v1/employees",
        json={"name": "Bob"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert created.status_code == 201, created.text


def test_explicit_credentials_take_precedence_and_do_not_require_csrf(client: TestClient) -> None:
    data = register_and_verify(client)
    client.cookies.clear()
    assert browser_login(client).status_code == 200

    created = client.post(
        "/api/v1/employees",
        json={"name": "Agent Created"},
        headers={"X-API-Key": data["plain_text_api_key"]},
    )
    assert created.status_code == 201, created.text

    bearer_wins = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid",
            "X-API-Key": data["plain_text_api_key"],
        },
    )
    assert bearer_wins.status_code == 401


def test_legacy_session_can_issue_and_rotate_csrf_token(client: TestClient) -> None:
    data = register_and_verify(client)
    client.cookies.clear()
    client.cookies.set("oryh_session", data["session_token"], path="/")

    first = client.get("/api/v1/auth/browser/csrf")
    assert first.status_code == 200, first.text
    first_token = first.json()["data"]["csrf_token"]
    assert client.cookies.get("oryh_csrf") == first_token

    second = client.get("/api/v1/auth/browser/csrf")
    second_token = second.json()["data"]["csrf_token"]
    assert second.status_code == 200
    assert second_token != first_token
    assert client.cookies.get("oryh_csrf") == second_token


def test_browser_logout_requires_csrf_revokes_session_and_clears_cookies(client: TestClient) -> None:
    register_and_verify(client)
    client.cookies.clear()
    assert browser_login(client).status_code == 200
    session_token = client.cookies.get("oryh_session")
    csrf_token = client.cookies.get("oryh_csrf")

    assert client.post("/api/v1/auth/browser/logout").status_code == 403
    response = client.post(
        "/api/v1/auth/browser/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert client.cookies.get("oryh_session") is None
    assert client.cookies.get("oryh_csrf") is None
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"},
    ).status_code == 401


def test_https_base_url_marks_both_browser_cookies_secure(client: TestClient, monkeypatch) -> None:
    register_and_verify(client)
    client.cookies.clear()
    monkeypatch.setattr(settings, "base_url", "https://console.example.com")

    response = browser_login(client)

    cookie_headers = response.headers.get_list("set-cookie")
    browser_cookies = [
        value
        for value in cookie_headers
        if value.startswith("oryh_session=") or value.startswith("oryh_csrf=")
    ]
    assert len(browser_cookies) == 2
    assert all("Secure" in value for value in browser_cookies)


def test_browser_auth_openapi_has_concrete_response_contracts(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    login_schema = paths["/api/v1/auth/browser/login"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    csrf_schema = paths["/api/v1/auth/browser/csrf"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert login_schema["$ref"].endswith("/BrowserLoginEnvelope")
    assert csrf_schema["$ref"].endswith("/BrowserCsrfEnvelope")
