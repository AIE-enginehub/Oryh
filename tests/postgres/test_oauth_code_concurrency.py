"""One authorization code, two redemptions at once. One key.

Review R08 (2026-09-05): `_redeem_code` read `consumed_at`, then set it, so
two concurrent exchanges of one code both minted a key. The code is now
spent with a conditional UPDATE in the transaction that mints the key:
exactly one caller wins, the other gets invalid_grant.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password, hash_token
from app.models import ApiKey, OAuthAuthorizationCode, Tenant, User
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]

CLIENT_ID = "https://agent.example.com/client"
REDIRECT = "http://127.0.0.1:53421/callback"


@pytest.fixture()
def grant(pg_sessionmaker):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    code = secrets.token_urlsafe(32)
    with pg_sessionmaker() as db:
        tenant = Tenant(name="OAuth PG", email_domain="oauth-pg.example", slug="oauth-pg")
        db.add(tenant)
        db.flush()
        user = User(tenant_id=tenant.id, email="admin@oauth-pg.example", name="Admin", role="admin",
                    status="active", password_hash=hash_password("pw-12345678"))
        db.add(user)
        db.flush()
        db.add(OAuthAuthorizationCode(
            code_hash=hash_token(code), stage="code", client_id=CLIENT_ID, redirect_uri=REDIRECT,
            code_challenge=challenge, tenant_id=tenant.id, user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        db.commit()
        return {"tenant_id": tenant.id, "code": code, "verifier": verifier}


def redeem_in_thread(pg_sessionmaker, grant, statuses, *, barrier=None):
    from app.api import oauth as oauth_api

    original = oauth_api._pkce_matches

    def gated(verifier, challenge):
        if barrier is not None:
            barrier.wait(timeout=15)  # both have read the unspent row
        return original(verifier, challenge)

    try:
        with pg_sessionmaker() as db:
            oauth_api._pkce_matches = gated
            try:
                response = oauth_api._redeem_code(db, {
                    "code": grant["code"], "code_verifier": grant["verifier"],
                    "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
                })
            finally:
                oauth_api._pkce_matches = original
        statuses.append(response.status_code)
    except Exception as exc:  # noqa: BLE001
        statuses.append(repr(exc))


def test_one_code_mints_one_key_under_concurrent_redemption(pg_sessionmaker, grant) -> None:
    barrier = threading.Barrier(2)
    statuses: list = []
    threads = [threading.Thread(target=redeem_in_thread, args=(pg_sessionmaker, grant, statuses), kwargs={"barrier": barrier})
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(map(str, statuses)) == ["200", "400"], statuses
    with pg_sessionmaker() as db:
        keys = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == grant["tenant_id"]))
        assert keys == 1, "exactly one key for one code"
