"""An idempotency key answers for one request, not for whatever comes next.

Both settlement paths used to answer a known key by handing back the rows that
key had already written, without comparing them to what the caller had just
asked for. So an agent that reused a key across a retry it had EDITED — a
corrected amount, one more line — got `replayed: true` and a 200, and none of
its correction happened. Silence exactly where an error was needed.

The 2026-08-16 architecture review's P0-1, item 4. These run on SQLite because
nothing here is about concurrency: the second call happens after the first has
committed. The concurrency half lives in `tests/postgres/`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


@pytest.fixture()
def account(client: TestClient):
    ctx = provision_tenant(client, company_name="Idem Co", email="admin@idem-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    customer = client.post("/api/v1/customers", json={"name": "客户"},
                           headers=key).json()["data"]["id"]
    account = client.post("/api/v1/billing-accounts", json={
        "account_code": "ACC-1", "name": "预存账户", "customer_id": customer,
        "unit": "CNY", "unit_type": "currency", "credit_limit": 0,
    }, headers=key)
    assert account.status_code == 201, account.text
    return {"client": client, "key": key, "id": account.json()["data"]["id"]}


def post_entries(account, lines, idempotency_key):
    return account["client"].post(
        f"/api/v1/billing-accounts/{account['id']}/entries",
        json={"lines": lines, "idempotency_key": idempotency_key},
        headers=account["key"],
    )


def balance_of(account) -> float:
    return account["client"].get(
        f"/api/v1/billing-accounts/{account['id']}", headers=account["key"]
    ).json()["data"]["balance"]


def test_the_same_key_and_the_same_body_runs_once(account) -> None:
    first = post_entries(account, [{"amount": 100, "reason": "deposit"}], "key-1")
    assert first.status_code == 200, first.text
    assert first.json()["data"]["replayed"] is False

    second = post_entries(account, [{"amount": 100, "reason": "deposit"}], "key-1")
    assert second.status_code == 200
    assert second.json()["data"]["replayed"] is True
    assert balance_of(account) == 100.0


def test_the_same_key_with_a_different_amount_is_refused(account) -> None:
    """The case that used to return 200 and do nothing."""
    assert post_entries(account, [{"amount": 100, "reason": "deposit"}], "key-2").status_code == 200

    corrected = post_entries(account, [{"amount": 150, "reason": "deposit"}], "key-2")
    assert corrected.status_code == 409, corrected.text
    assert "different set of account entries" in corrected.json()["detail"]
    assert balance_of(account) == 100.0


def test_the_same_key_with_an_extra_line_is_refused(account) -> None:
    assert post_entries(account, [{"amount": 100, "reason": "deposit"}], "key-3").status_code == 200

    extended = post_entries(account, [
        {"amount": 100, "reason": "deposit"},
        {"amount": 50, "reason": "deposit"},
    ], "key-3")
    assert extended.status_code == 409
    assert balance_of(account) == 100.0


def test_a_new_key_applies_the_corrected_request(account) -> None:
    """The 409 has to leave a way forward, and it is the one the message names."""
    assert post_entries(account, [{"amount": 100, "reason": "deposit"}], "key-4").status_code == 200
    assert post_entries(account, [{"amount": 150, "reason": "deposit"}], "key-5").status_code == 200
    assert balance_of(account) == 250.0


def test_no_key_at_all_still_works(account) -> None:
    """Idempotency is opt-in; two identical unkeyed deposits are two deposits."""
    for _ in range(2):
        response = account["client"].post(
            f"/api/v1/billing-accounts/{account['id']}/entries",
            json={"lines": [{"amount": 25, "reason": "deposit"}]},
            headers=account["key"],
        )
        assert response.status_code == 200, response.text
    assert balance_of(account) == 50.0
