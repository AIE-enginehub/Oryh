from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


def provision_member(client: TestClient) -> dict:
    """Tenant with one linked member; returns service headers + member login."""
    data = bootstrap_tenant(client, company_name="Device Co", email="admin@device-co.com", password="device-pass1")
    service = {"X-API-Key": data["plain_text_api_key"]}
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = client.post(
        "/api/v1/auth/invitations",
        json={"email": "wang@device-co.com", "role": "member", "employee_id": employee_id},
        headers=service,
    ).json()["data"]["id"]
    invite_token = extract_token(outbox.messages[-1].body)
    client.post("/api/v1/auth/invitations/accept", json={"token": invite_token, "password": "member-pass1"})
    client.cookies.clear()
    return {
        "service": service,
        "user_id": user_id,
        "email": "wang@device-co.com",
        "password": "member-pass1",
    }


def start_flow(client: TestClient, client_name: str = "WorkBuddy on test") -> dict:
    response = client.post("/api/v1/auth/device/start", json={"client_name": client_name})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def poll(client: TestClient, device_code: str):
    return client.post("/api/v1/auth/device/token", json={"device_code": device_code})


def web_login(client: TestClient, email: str, password: str, next_url: str = "") -> None:
    data = {"email": email, "password": password}
    if next_url:
        data["next"] = next_url
    response = client.post("/web/login", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text


def test_device_flow_happy_path(client: TestClient) -> None:
    ctx = provision_member(client)
    grant = start_flow(client)
    assert grant["verification_uri_complete"].endswith(f"/web/device?code={grant['user_code']}")
    assert "-" in grant["user_code"]

    # before approval: pending
    assert poll(client, grant["device_code"]).json()["data"]["status"] == "pending"

    # unauthenticated approval page bounces through login and back
    response = client.get(f"/web/device?code={grant['user_code']}", follow_redirects=False)
    assert response.status_code == 303
    assert "/web/login?next=" in response.headers["location"]

    web_login(client, ctx["email"], ctx["password"], next_url=f"/web/device?code={grant['user_code']}")
    page = client.get(f"/web/device?code={grant['user_code']}")
    assert "WorkBuddy on test" in page.text and grant["user_code"] in page.text
    assert "进入控制台" in page.text
    assert "进入 React 控制台" not in page.text

    approved = client.post("/web/device/approve", data={"code": grant["user_code"]})
    assert approved.status_code == 200 and "Device connected" in approved.text
    assert "Access credentials" in approved.text
    assert "API Keys" not in approved.text

    result = poll(client, grant["device_code"]).json()["data"]
    assert result["status"] == "approved"
    assert result["user"]["email"] == ctx["email"]
    assert result["tenant"] == "Device Co"
    # the agent is told which company it just connected to, in the form its
    # skills and install directory carry
    assert result["tenant_slug"] == "device-co"
    assert result["install_dir"] == "oryh-skills-device-co"
    key = result["api_key"]
    # The handover is a PAIR now: the key expires, the refresh token renews it
    # without another browser round-trip. Prefixes differ on purpose, so one
    # pasted where the other belongs fails loudly.
    assert result["refresh_token"].startswith("calwr_")
    assert result["expires_at"] is not None

    # the key is user-bound and pulls the personal bundle
    me = client.get("/api/v1/auth/me", headers={"X-API-Key": key}).json()["data"]
    assert me["email"] == ctx["email"]
    assert me["tenant"]["slug"] == "device-co"
    bundle = client.get("/api/v1/my/skill-bundle", headers={"X-API-Key": key})
    assert bundle.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    roots = {name.split("/")[0] for name in archive.namelist()}
    # the company's own directory, plus the shared bootstrap skill that belongs
    # to the machine rather than to any one employer
    assert roots == {"oryh-skills-device-co", "oryh-connect"}
    assert "oryh-connect/SKILL.md" in archive.namelist()
    tenant_skills = {
        name[len("oryh-skills-device-co/") :].split("/")[0]
        for name in archive.namelist()
        if name.startswith("oryh-skills-device-co/") and name.count("/") >= 2
    }
    assert "oryh-device-co-skill-sync" in tenant_skills
    rendered = archive.read("oryh-skills-device-co/oryh-device-co-my-work/SKILL.md").decode()
    assert key in rendered
    # the shared copy is the same file for every employer, so it must never
    # carry this company's credential
    shared_connect = archive.read("oryh-connect/SKILL.md").decode()
    assert key not in shared_connect and "calw_" not in shared_connect

    # one-shot delivery: the same device_code cannot be polled again
    replay = poll(client, grant["device_code"])
    assert replay.status_code == 400
    assert "already used" in replay.json()["detail"]

    # both sides of the handshake are audited
    audit = client.get("/api/v1/audit-logs?action=device.authorized", headers=ctx["service"]).json()
    assert audit["meta"]["total"] == 1
    assert audit["data"][0]["detail"]["client_name"] == "WorkBuddy on test"
    audit = client.get("/api/v1/audit-logs?action=device.connected", headers=ctx["service"]).json()
    assert audit["meta"]["total"] == 1


def test_device_flow_deny(client: TestClient) -> None:
    ctx = provision_member(client)
    grant = start_flow(client)
    web_login(client, ctx["email"], ctx["password"])
    denied = client.post("/web/device/deny", data={"code": grant["user_code"]})
    assert denied.status_code == 200 and "denied" in denied.text.lower()
    assert poll(client, grant["device_code"]).json()["data"]["status"] == "denied"
    # a denied code can no longer be approved
    retry = client.post("/web/device/approve", data={"code": grant["user_code"]})
    assert "no longer pending" in retry.text


def test_device_flow_expiry(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = provision_member(client)
    monkeypatch.setattr(settings, "device_code_ttl_minutes", 0)
    grant = start_flow(client)
    assert poll(client, grant["device_code"]).json()["data"]["status"] == "expired"
    web_login(client, ctx["email"], ctx["password"])
    page = client.get(f"/web/device?code={grant['user_code']}")
    assert "No pending connection" in page.text


def test_device_flow_bad_codes(client: TestClient) -> None:
    ctx = provision_member(client)
    assert poll(client, "not-a-real-code").status_code == 400
    web_login(client, ctx["email"], ctx["password"])
    page = client.get("/web/device?code=ZZZZ-ZZZZ")
    assert "No pending connection" in page.text
    # user_code entry is normalized: lowercase and missing dash still match
    grant = start_flow(client)
    lowered = grant["user_code"].replace("-", "").lower()
    page = client.get(f"/web/device?code={lowered}")
    assert grant["user_code"] in page.text


def test_device_key_is_per_device_no_rotation(client: TestClient) -> None:
    import re

    ctx = provision_member(client)
    # device A connects
    grant_a = start_flow(client, client_name="laptop")
    web_login(client, ctx["email"], ctx["password"])
    client.post("/web/device/approve", data={"code": grant_a["user_code"]})
    key_a = poll(client, grant_a["device_code"]).json()["data"]["api_key"]

    # device B connects: A keeps working
    grant_b = start_flow(client, client_name="desktop")
    client.post("/web/device/approve", data={"code": grant_b["user_code"]})
    key_b = poll(client, grant_b["device_code"]).json()["data"]["api_key"]
    assert key_a != key_b
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": key_a}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": key_b}).status_code == 200

    # keys are labelled per device for individual revocation
    keys = client.get("/api/v1/tenant/api-keys", headers=ctx["service"]).json()["data"]
    labels = {k["label"] for k in keys}
    assert "device:laptop" in labels and "device:desktop" in labels

    # admin issuance still rotates ALL personal keys (both devices die)
    response = client.post(f"/api/v1/users/{ctx['user_id']}/skill-bundle", headers=ctx["service"])
    assert response.status_code == 200
    fresh = re.search(r"calw_[A-Za-z0-9_-]+", zipfile.ZipFile(io.BytesIO(response.content)).read(
        "oryh-skills-device-co/oryh-device-co-my-work/SKILL.md").decode()).group(0)
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": key_a}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": key_b}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": fresh}).status_code == 200


def test_connect_skill_download_is_public_and_rendered(client: TestClient) -> None:
    # no auth needed, no tenant provisioned yet
    response = client.get("/api/v1/connect-skill")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="oryh-connect.zip"' in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert "oryh-connect/SKILL.md" in names
    assert "oryh-connect/references/api.md" in names
    skill_md = archive.read("oryh-connect/SKILL.md").decode()
    api_reference = archive.read("oryh-connect/references/api.md").decode()
    assert "{{ORYH_BASE_URL}}" not in skill_md
    assert "http://testserver" in skill_md
    assert 'api_base_url: "http://testserver/api/v1"' in skill_md
    assert "POST `<api_base_url>/auth/device/start`" in skill_md
    assert "POST /auth/device/start" not in skill_md
    assert "POST <api_base_url>/auth/device/start" in api_reference
    # The reference used to spell endpoints as `<base_url>/api/v1/…`,
    # which reads as an instruction to assemble the address. Endpoint lines now
    # hang off the rendered API root; the only surviving mention of the prefix
    # is the 405 explanation, which is describing the mistake, not teaching it.
    assert "<base_url>/api/v1" not in api_reference
    assert "405 Method Not Allowed" in api_reference

    # the connect page itself is public too, before and after login
    page = client.get("/web/connect")
    assert page.status_code == 200 and "oryh-connect" in page.text
    ctx = provision_member(client)
    web_login(client, ctx["email"], ctx["password"])
    signed_in_page = client.get("/web/connect")
    assert signed_in_page.status_code == 200 and "Access credentials" in signed_in_page.text


def test_login_next_is_console_only(client: TestClient) -> None:
    ctx = provision_member(client)
    response = client.post(
        "/web/login",
        data={"email": ctx["email"], "password": ctx["password"], "next": "https://evil.example/phish"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/console/dashboard"

    legacy_target = client.post(
        "/web/login",
        data={"email": ctx["email"], "password": ctx["password"], "next": "/web/users"},
        follow_redirects=False,
    )
    assert legacy_target.status_code == 303
    assert legacy_target.headers["location"] == "/console/dashboard"
