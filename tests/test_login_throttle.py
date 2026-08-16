"""Failed logins get progressively slower. Neither surface had any backoff.

A password could be guessed as fast as the process would answer, on both the
tenant login and — the more privileged of the two — the operator console. The
only thing in front of them was whatever the gateway does, which is an IP token
bucket, and an IP token bucket does not notice one address trying one password
against ten thousand accounts. The 2026-08-16 architecture review's 5.1.

Two keys because the two attacks are different shapes: one account under
sustained guessing from anywhere, and one address working through a list of
accounts. The unit tests below drive the clock rather than sleeping.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.login_throttle import (
    FREE_ATTEMPTS,
    MAX_DELAY_SECONDS,
    WINDOW_SECONDS,
    LoginThrottle,
    login_keys,
)
from app.core.login_throttle import throttle as shared_throttle
from conftest import provision_tenant


@pytest.fixture(autouse=True)
def clean_throttle():
    shared_throttle.clear()
    yield
    shared_throttle.clear()


# --- the counter itself, on a driven clock ---------------------------------


def test_the_first_few_failures_are_free() -> None:
    """A person mistyping their password must notice nothing. That is most of
    what these counters ever see."""
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for n in range(FREE_ATTEMPTS):
        throttle.record_failure(keys, now=float(n))
    assert throttle.retry_after(keys, now=float(FREE_ATTEMPTS)) == 0.0


def test_the_delay_grows_after_that() -> None:
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for n in range(FREE_ATTEMPTS + 3):
        throttle.record_failure(keys, now=0.0)
    wait = throttle.retry_after(keys, now=0.0)
    assert wait > 1.0


def test_the_delay_is_capped() -> None:
    """An uncapped exponential reaches next Tuesday in twenty failures and
    becomes the denial of service it was meant to prevent."""
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for _ in range(60):
        throttle.record_failure(keys, now=0.0)
    assert throttle.retry_after(keys, now=0.0) <= MAX_DELAY_SECONDS


def test_waiting_it_out_works() -> None:
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for _ in range(FREE_ATTEMPTS + 2):
        throttle.record_failure(keys, now=0.0)
    assert throttle.retry_after(keys, now=0.0) > 0
    assert throttle.retry_after(keys, now=MAX_DELAY_SECONDS + 1) == 0.0


def test_success_clears_the_counter() -> None:
    """The delay is a consequence of failures. A legitimate user who finally
    types the right password gets in, and is not still penalised next time."""
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for _ in range(FREE_ATTEMPTS + 3):
        throttle.record_failure(keys, now=0.0)
    throttle.record_success(keys)
    assert throttle.retry_after(keys, now=0.0) == 0.0


def test_switching_accounts_does_not_reset_the_address() -> None:
    """One address working through a list of accounts is the shape an
    account-only counter cannot see."""
    throttle = LoginThrottle()
    for n in range(FREE_ATTEMPTS + 3):
        throttle.record_failure(login_keys(f"victim{n}@example.test", "10.0.0.1"), now=0.0)
    assert throttle.retry_after(login_keys("fresh@example.test", "10.0.0.1"), now=0.0) > 0


def test_switching_addresses_does_not_reset_the_account() -> None:
    """And the mirror: one account under attack from a botnet."""
    throttle = LoginThrottle()
    for n in range(FREE_ATTEMPTS + 3):
        throttle.record_failure(login_keys("victim@example.test", f"10.0.0.{n}"), now=0.0)
    assert throttle.retry_after(login_keys("victim@example.test", "10.9.9.9"), now=0.0) > 0


def test_case_does_not_buy_a_fresh_budget() -> None:
    assert login_keys("A@Example.TEST", None) == login_keys("a@example.test", None)


def test_counters_are_forgotten_after_the_window() -> None:
    throttle = LoginThrottle()
    keys = login_keys("a@example.test", "10.0.0.1")
    for _ in range(FREE_ATTEMPTS + 3):
        throttle.record_failure(keys, now=0.0)
    throttle.record_failure(login_keys("other@example.test", "10.0.0.2"), now=WINDOW_SECONDS + 1)
    assert throttle.retry_after(keys, now=WINDOW_SECONDS + 1) == 0.0
    assert len(throttle._counters) == 2  # the stale pair was pruned


# --- through the API -------------------------------------------------------


def test_the_tenant_login_starts_refusing(client: TestClient) -> None:
    provision_tenant(client, company_name="Throttle Co", email="admin@throttle-co.example")
    body = {"email": "admin@throttle-co.example", "password": "wrong-password"}

    codes = [client.post("/api/v1/auth/login", json=body).status_code
             for _ in range(FREE_ATTEMPTS + 2)]

    assert codes[0] == 401, "the first attempt is an ordinary wrong password"
    assert 429 in codes, f"an unlimited password oracle: {codes}"
    refused = client.post("/api/v1/auth/login", json=body)
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1


def test_the_right_password_still_works_before_the_limit(client: TestClient) -> None:
    ctx = provision_tenant(client, company_name="Ok Co", email="admin@ok-co.example")
    assert ctx["session_token"]
    for _ in range(FREE_ATTEMPTS - 1):
        client.post("/api/v1/auth/login",
                    json={"email": "admin@ok-co.example", "password": "nope"})
    good = client.post("/api/v1/auth/login",
                       json={"email": "admin@ok-co.example", "password": "admin-pass1"})
    assert good.status_code == 200, good.text
