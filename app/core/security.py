from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

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
