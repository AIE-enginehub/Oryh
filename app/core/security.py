from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

# scrypt parameters chosen for interactive login latency (~100ms).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    derived_b64 = base64.b64encode(derived).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${derived_b64}"


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def verify_password_or_decoy(password: str, stored: str | None) -> bool:
    """`verify_password` that costs the same when there is nothing to verify.

    A sign-in for an unknown, disabled or password-less account used to skip
    the hash and answer in about 1 ms against about 100 ms for a wrong
    password, which tells a caller which emails have accounts — the very
    thing the password-reset endpoint is careful not to say (review
    2026-11-12, finding 5). With no stored hash, a decoy is checked and the
    answer is always False."""
    if stored is None:
        verify_password(password, _decoy_hash())
        return False
    return verify_password(password, stored)


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n_str, r_str, p_str, salt_b64, derived_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(derived_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_str),
            r=int(r_str),
            p=int(p_str),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
