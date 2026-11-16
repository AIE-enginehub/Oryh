"""Signing in costs the same whether or not the email has an account.

Review 2026-11-12, finding 5: an unknown, disabled or password-less account
skipped the password hash and answered in about 1 ms against about 100 ms for
a wrong password, which told any caller which emails have accounts. A decoy
hash is now checked instead. Timing itself is too noisy to assert on, so this
counts the hash checks.
"""

from __future__ import annotations

import pytest

from app.core import security
from conftest import make_client, provision_tenant


@pytest.fixture()
def counted(monkeypatch):
    calls = []
    real = security.verify_password

    def counting(password, stored):
        calls.append(stored)
        return real(password, stored)

    monkeypatch.setattr(security, "verify_password", counting)
    return calls


def test_an_unknown_email_pays_for_a_password_check_too(counted) -> None:
    with make_client([]) as c:
        provision_tenant(c, company_name="Timing Co", email="owner@timing-co.example")
        counted.clear()
        unknown = c.post("/api/v1/auth/login", json={"email": "nobody@timing-co.example", "password": "guess-1234"})
        assert unknown.status_code == 401
        assert len(counted) == 1, "the decoy hash was checked"
        wrong = c.post("/api/v1/auth/login", json={"email": "owner@timing-co.example", "password": "guess-1234"})
        assert wrong.status_code == 401
        assert len(counted) == 2, "one check either way"
