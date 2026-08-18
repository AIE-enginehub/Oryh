"""Lifecycle of an interactive personal key: expiry, refresh, rotation.

An interactive personal key is the one that lands on a person's machine,
rendered into their skill bundle — the device flow and the bundle endpoints
mint them. Those keys expire (`settings.interactive_key_ttl_hours`) and carry a
refresh token; everything else — tenant service keys, hosted flow-agent keys,
keys minted before expiry existed — has `expires_at` NULL and never changes
behaviour.

Refresh ROTATES IN PLACE: the same `ApiKey` row gets a new key hash, a new
refresh-token hash, and a fresh expiry. One row stays one device, revocation
stays one `is_active` flip, and the ORM audit trail records each rotation as an
`api_key.updated` with both hashes «redacted».

The retry problem is handled with a grace window. A client whose refresh
response was lost still holds only the token it just spent; retrying with it
within `refresh_retry_grace_seconds` is honest and rotates again. The same
token outside the window means a second party holds a copy — the key is
revoked, and the legitimate device reconnects through the browser, which is
exactly the moment a person should be looking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models import ApiKey, generate_api_key, generate_refresh_token, hash_api_key


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres hands back aware ones."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def interactive_expiry() -> datetime:
    return utc_now() + timedelta(hours=settings.interactive_key_ttl_hours)


def is_expired(api_key: ApiKey) -> bool:
    return api_key.expires_at is not None and as_utc(api_key.expires_at) < utc_now()


def make_interactive(api_key: ApiKey) -> str:
    """Give a freshly minted key its expiry and refresh token.

    Returns the refresh token PLAINTEXT — the caller's one chance to deliver
    it; only the hash is stored.
    """
    refresh_plain = generate_refresh_token()
    api_key.expires_at = interactive_expiry()
    api_key.refresh_token_hash = hash_api_key(refresh_plain)
    api_key.prior_refresh_token_hash = None
    api_key.refresh_rotated_at = utc_now()
    return refresh_plain


def rotate(api_key: ApiKey) -> tuple[str, str]:
    """Rotate both secrets in place; returns (api_key_plaintext, refresh_plaintext).

    The key rendered into any previously downloaded bundle stops working here —
    that is the point. The agent keeps the new pair in memory and may re-sync
    its bundle, which re-renders the files with the key it presents.
    """
    key_plain = generate_api_key()
    refresh_plain = generate_refresh_token()
    api_key.prior_refresh_token_hash = api_key.refresh_token_hash
    api_key.key_hash = hash_api_key(key_plain)
    api_key.refresh_token_hash = hash_api_key(refresh_plain)
    api_key.expires_at = interactive_expiry()
    api_key.refresh_rotated_at = utc_now()
    return key_plain, refresh_plain


def within_retry_grace(api_key: ApiKey) -> bool:
    if api_key.refresh_rotated_at is None:
        return False
    deadline = as_utc(api_key.refresh_rotated_at) + timedelta(
        seconds=settings.refresh_retry_grace_seconds
    )
    return utc_now() <= deadline
