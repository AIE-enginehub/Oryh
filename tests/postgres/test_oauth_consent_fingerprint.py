"""The consent stage stores its whole request, and a real request is long.

`GET /oauth/authorize` records a consent row whose `code_challenge` column
holds `_consent_fingerprint(p)` — all eight authorization parameters joined by
"|" — so the POST can prove the page it answers is the one this session saw.
The column was `varchar(128)`. The S256 challenge alone is 43 characters; add
a client-id URL, a redirect URI, the resource URL and the client's `state`,
and every real client passed 128: the authorize page answered 500
(StringDataRightTruncation) on PostgreSQL from v2026.9.5, found by the
2026-09-14 live probe. SQLite ignores VARCHAR lengths, so the main suite
passed throughout. `client_id` alone may be 500 characters and `state` has no
bound at all, so the column is `text`.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.api.oauth import _consent_fingerprint
from app.core.security import hash_password, hash_token
from app.models import OAuthAuthorizationCode, Tenant, User
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]


def test_a_long_real_world_consent_request_is_stored(pg_sessionmaker) -> None:
    verifier = secrets.token_urlsafe(48)
    params = {
        "response_type": "code",
        # a client-id metadata document URL at the column's own 500-character bound
        "client_id": "https://agents.example.com/.well-known/oauth-client/" + "c" * 447,
        "redirect_uri": "https://agents.example.com/oauth/callback/" + "r" * 300,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
        "code_challenge_method": "S256",
        # clients pack encoded session data into state; nothing bounds it
        "state": secrets.token_urlsafe(1500),
        "scope": "oryh",
        "resource": "https://oryh.example.com/mcp",
    }
    fingerprint = _consent_fingerprint(params)
    assert len(fingerprint) > 2000

    with pg_sessionmaker() as db:
        tenant = Tenant(name="Consent PG", email_domain="consent-pg.example", slug="consent-pg")
        db.add(tenant)
        db.flush()
        user = User(tenant_id=tenant.id, email="admin@consent-pg.example", name="Admin", role="admin",
                    status="active", password_hash=hash_password("pw-12345678"))
        db.add(user)
        db.flush()
        nonce = secrets.token_urlsafe(32)
        db.add(OAuthAuthorizationCode(
            code_hash=hash_token(nonce), stage="consent", session_id=None,
            client_id=params["client_id"], redirect_uri=params["redirect_uri"],
            code_challenge=fingerprint, resource=params["resource"], scope=params["scope"],
            tenant_id=tenant.id, user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        db.commit()

        stored = db.query(OAuthAuthorizationCode).filter_by(code_hash=hash_token(nonce)).one()
        assert stored.code_challenge == fingerprint, "stored whole — the POST compares it for equality"
