"""Interactive personal keys expire and refresh; exempt principals never change.

Phase 1 of docs/mcp-adoption-plan-2026-08.md: until now every API key lived
forever, and the device flow rendered a permanent plaintext key into markdown
on personal machines. These tests pin the whole new lifecycle — expiry is
enforced, the device flow hands out a pair, refresh rotates in place, a
lost-response retry survives, replay revokes — and, just as deliberately, that
nothing changed for the principals the plan exempts: tenant service keys and
hosted flow-agent keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ApiKey, hash_api_key
from conftest import make_stack, provision_tenant


@pytest.fixture()
def stack():
    with make_stack() as (client, engine):
        yield client, engine


def _session(engine) -> Session:
    return sessionmaker(bind=engine, future=True)()


def _invitation_token() -> str:
    from app.services.emails import outbox

    for line in outbox.messages[-1].body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in the invitation email")


def _mint_member_pair(client, admin_headers, suffix: str = "1") -> tuple[str, str, str]:
    """Invite → accept → admin issues the bundle; returns (user_id, api_key, refresh_token)."""
    invited = client.post(
        "/api/v1/auth/invitations",
        headers=admin_headers,
        json={"email": f"member{suffix}@refresh.example", "role": "member", "name": f"Member {suffix}"},
    )
    assert invited.status_code == 201, invited.text
    user_id = invited.json()["data"]["id"]
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": _invitation_token(), "password": f"member{suffix}-pass1"},
    )
    assert accepted.status_code in (200, 201), accepted.text

    bundle = client.post(f"/api/v1/users/{user_id}/skill-bundle", headers=admin_headers)
    assert bundle.status_code == 200, bundle.text
    refresh_token = bundle.headers["X-Oryh-Refresh-Token"]
    import io
    import re
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    rendered = archive.read(
        next(n for n in archive.namelist() if n.endswith("-my-work/SKILL.md"))
    ).decode()
    api_key = re.search(r"calw_[A-Za-z0-9_-]+", rendered).group(0)
    return user_id, api_key, refresh_token


def test_a_bundle_key_expires_and_the_refresh_header_is_present(stack):
    client, engine = stack
    tenant = provision_tenant(client, company_name="Refresh Co", email="admin@refresh.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, api_key, refresh_token = _mint_member_pair(client, headers)

    assert refresh_token.startswith("calwr_"), "refresh token must be unmistakable for a key"
    me = client.get("/api/v1/auth/me", headers={"X-API-Key": api_key})
    assert me.status_code == 200, me.text

    with _session(engine) as db:
        row = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key)))
        assert row.expires_at is not None, "an interactive personal key must expire"
        assert row.refresh_token_hash == hash_api_key(refresh_token)


def test_an_expired_key_is_401_with_the_refresh_hint(stack):
    client, engine = stack
    tenant = provision_tenant(client, company_name="Expired Co", email="admin@expired.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, api_key, _ = _mint_member_pair(client, headers)

    with _session(engine) as db:
        row = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key)))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    response = client.get("/api/v1/auth/me", headers={"X-API-Key": api_key})
    assert response.status_code == 401
    # "expired", not "invalid": the skills key their refresh procedure to this
    # exact distinction.
    assert "expired" in response.json()["detail"]
    assert "token/refresh" in response.json()["detail"]


def test_refresh_rotates_in_place(stack):
    client, engine = stack
    tenant = provision_tenant(client, company_name="Rotate Co", email="admin@rotate.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, old_key, old_refresh = _mint_member_pair(client, headers)

    refreshed = client.post("/api/v1/auth/token/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200, refreshed.text
    pair = refreshed.json()["data"]
    assert pair["api_key"].startswith("calw_") and pair["refresh_token"].startswith("calwr_")
    assert pair["expires_at"] is not None

    # the new key authenticates; the one rendered into the old bundle is dead
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": pair["api_key"]}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": old_key}).status_code == 401

    # one row, rotated — not a second credential
    with _session(engine) as db:
        rows = db.scalars(select(ApiKey).where(ApiKey.user_id == user_id)).all()
        assert len(rows) == 1
        assert rows[0].key_hash == hash_api_key(pair["api_key"])


def test_a_lost_response_retry_within_grace_succeeds(stack):
    client, _ = stack
    tenant = provision_tenant(client, company_name="Retry Co", email="admin@retry.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, _, refresh_token = _mint_member_pair(client, headers)

    first = client.post("/api/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    # The response was "lost": retry with the token just spent, immediately.
    second = client.post("/api/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 200, (
        "a client whose refresh response vanished must not be locked out"
    )
    # The newest pair wins; the lost response's key died with the second rotation.
    newest = second.json()["data"]
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": newest["api_key"]}).status_code == 200
    lost = first.json()["data"]
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": lost["api_key"]}).status_code == 401


def test_replay_outside_grace_revokes_the_device(stack):
    client, engine = stack
    tenant = provision_tenant(client, company_name="Replay Co", email="admin@replay.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, _, refresh_token = _mint_member_pair(client, headers)

    first = client.post("/api/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    live = first.json()["data"]

    # Age the rotation past the grace window: what arrives now is replay.
    with _session(engine) as db:
        row = db.scalar(select(ApiKey).where(ApiKey.user_id == user_id))
        row.refresh_rotated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

    replay = client.post("/api/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401
    assert "already used" in replay.json()["detail"]

    # Revocation is total: the live pair dies too, because the server cannot
    # know which holder was the thief.
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": live["api_key"]}).status_code == 401
    again = client.post("/api/v1/auth/token/refresh", json={"refresh_token": live["refresh_token"]})
    assert again.status_code == 401


def test_garbage_refresh_tokens_are_401_without_side_effects(stack):
    client, _ = stack
    tenant = provision_tenant(client, company_name="Garbage Co", email="admin@garbage.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, api_key, _ = _mint_member_pair(client, headers)

    response = client.post(
        "/api/v1/auth/token/refresh", json={"refresh_token": "calwr_not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid refresh token"
    # and nobody was punished for someone else's guess
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": api_key}).status_code == 200


def test_service_keys_never_expire(stack):
    """The exemption is the other half of the design: a workload's durable
    secret lives in a secret store, not in synced markdown, and gets no TTL."""
    client, engine = stack
    tenant = provision_tenant(client, company_name="Service Co", email="admin@service.example")
    service_key = tenant["plain_text_api_key"]

    with _session(engine) as db:
        row = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(service_key)))
        assert row.expires_at is None, "a tenant service key must not expire"
        assert row.refresh_token_hash is None
        # even a very old service key still authenticates
        row.created_at = datetime.now(timezone.utc) - timedelta(days=365)
        db.commit()

    assert client.get("/api/v1/tenant", headers={"X-API-Key": service_key}).status_code == 200


def test_the_refresh_rotation_is_audited_with_redacted_hashes(stack):
    client, _ = stack
    tenant = provision_tenant(client, company_name="Audited Co", email="admin@audited.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    user_id, _, refresh_token = _mint_member_pair(client, headers)

    assert (
        client.post("/api/v1/auth/token/refresh", json={"refresh_token": refresh_token}).status_code
        == 200
    )

    entries = client.get(
        "/api/v1/audit-logs", headers=headers, params={"entity_type": "api_key"}
    ).json()["data"]
    rotations = [
        entry
        for entry in entries
        if entry["action"] == "api_key.updated"
        and "key_hash" in entry["detail"].get("changes", {})
    ]
    assert rotations, "a rotation must leave a trail"
    serialized = str(rotations[0]["detail"])
    assert "«redacted»" in serialized
    assert "calw_" not in serialized and "calwr_" not in serialized
    assert rotations[0]["actor"].startswith("key:")
