"""Billing accounts — a standing balance, in money or in points.

OFBiz's `BillingAccount` is the money half of this: a customer's credit account
with a limit. What must hold once points share the table:

- the unit type is structural, so money can never land in a points account and
  a points balance is never mistaken for currency;
- the balance is the entry ledger's running sum — never set directly, not even
  at opening;
- the floor is `-credit_limit`, so a points account (limit 0) cannot be
  overdrawn and a credit account can, exactly as far as it was allowed;
- freezing an account refuses movement, which is the entire point of freezing;
- and the server converts nothing — how many points a purchase earns and what
  they are worth are the tenant's rules, not the record layer's.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

from conftest import provision_tenant as bootstrap_tenant

TEST_TENANT = "aaaaaaaa-3333-4333-8333-aaaaaaaaaaaa"
TEST_API_KEY = "billing-account-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Loyalty Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def post(client: TestClient, path: str, body: dict, expect: int = 201) -> dict:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()["data"]


def customer(client: TestClient, name: str = "上海市第一医院") -> dict:
    return post(client, "/api/v1/customers", {"name": name})


def employee(client: TestClient, name: str = "会员小李") -> str:
    return post(client, "/api/v1/employees", {"name": name})["id"]


def money_account(client: TestClient, **overrides) -> dict:
    body = {
        "name": "市一院挂账户",
        "unit_type": "currency",
        "unit": "CNY",
        "customer_id": overrides.pop("customer_id", None) or customer(client)["id"],
    }
    body.update(overrides)
    return post(client, "/api/v1/billing-accounts", body)


def points_account(client: TestClient, **overrides) -> dict:
    body = {
        "name": "会员积分",
        "unit_type": "points",
        "unit": "point",
        "customer_id": overrides.pop("customer_id", None) or customer(client)["id"],
    }
    body.update(overrides)
    return post(client, "/api/v1/billing-accounts", body)


def entries(client: TestClient, account_id: str, lines: list[dict], expect: int = 200, **extra) -> dict:
    response = client.post(
        f"/api/v1/billing-accounts/{account_id}/entries",
        json={"lines": lines, **extra},
        headers=HEADERS,
    )
    assert response.status_code == expect, response.text
    return response.json()["data"] if expect == 200 else response.json()


def test_an_account_starts_empty_and_allocates_its_own_code(client: TestClient) -> None:
    account = money_account(client)

    assert account["account_code"].startswith("BA-")
    assert account["unit_type"] == "currency"
    assert account["balance"] == 0
    assert account["credit_limit"] == 0
    assert account["available_amount"] == 0
    assert account["status"] == "active"
    assert account["owner_name_snapshot"] == "上海市第一医院"


def test_an_opening_balance_is_recorded_as_the_first_entry(client: TestClient) -> None:
    """The balance must be the ledger's sum from the very first row, or the
    invariant that says so is a lie."""
    account = points_account(client, opening_balance=1200.0)

    assert account["balance"] == 1200.0
    detail = client.get(
        f"/api/v1/billing-accounts/{account['id']}/detail", headers=HEADERS
    ).json()["data"]
    assert [entry["reason"] for entry in detail["entries"]] == ["initial"]
    assert detail["entries"][0]["amount"] == 1200.0


def test_points_are_earned_and_redeemed_through_the_ledger(client: TestClient) -> None:
    account = points_account(client)

    earned = entries(
        client, account["id"],
        [{"amount": 500.0, "reason": "earned", "description": "消费 5000 元"}],
    )
    assert earned["balance"] == 500.0

    redeemed = entries(
        client, account["id"],
        [{"amount": -200.0, "reason": "redeemed", "description": "抵扣订单"}],
    )
    assert redeemed["balance"] == 300.0
    assert redeemed["available_amount"] == 300.0


def test_a_points_account_cannot_be_overdrawn(client: TestClient) -> None:
    account = points_account(client, opening_balance=100.0)

    body = entries(
        client, account["id"],
        [{"amount": -150.0, "reason": "redeemed"}],
        expect=409,
    )
    assert "only has 100.00 point available" in body["detail"]
    # nothing was written
    after = client.get(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS).json()["data"]
    assert after["balance"] == 100.0


def test_a_credit_account_may_be_drawn_exactly_as_far_as_allowed(client: TestClient) -> None:
    """挂账: the balance goes negative down to the credit line and no further."""
    account = money_account(client, credit_limit=50000.0)
    assert account["available_amount"] == 50000.0

    charged = entries(
        client, account["id"],
        [{"amount": -48000.0, "reason": "charge", "description": "本月货款挂账"}],
    )
    assert charged["balance"] == -48000.0
    assert charged["available_amount"] == 2000.0

    over = entries(
        client, account["id"], [{"amount": -3000.0, "reason": "charge"}], expect=409
    )
    assert "only has 2000.00 CNY available" in over["detail"]


def test_the_lines_of_one_call_are_judged_together(client: TestClient) -> None:
    account = points_account(client, opening_balance=100.0)

    body = entries(
        client, account["id"],
        [
            {"amount": -80.0, "reason": "redeemed"},
            {"amount": -80.0, "reason": "redeemed"},
        ],
        expect=409,
    )
    assert "available" in body["detail"]
    after = client.get(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS).json()["data"]
    assert after["balance"] == 100.0


def test_a_frozen_account_refuses_movement(client: TestClient) -> None:
    account = points_account(client, opening_balance=100.0)
    assert client.patch(
        f"/api/v1/billing-accounts/{account['id']}", json={"status": "frozen"}, headers=HEADERS
    ).status_code == 200

    body = entries(client, account["id"], [{"amount": 10.0, "reason": "earned"}], expect=409)
    assert "frozen" in body["detail"]

    client.patch(
        f"/api/v1/billing-accounts/{account['id']}", json={"status": "active"}, headers=HEADERS
    )
    assert entries(client, account["id"], [{"amount": 10.0, "reason": "earned"}])["balance"] == 110.0


def test_a_retry_with_the_same_key_posts_once(client: TestClient) -> None:
    account = points_account(client)
    lines = [{"amount": 500.0, "reason": "earned"}]

    first = entries(client, account["id"], lines, idempotency_key="grant-2026-08-02")
    assert first["replayed"] is False
    second = entries(client, account["id"], lines, idempotency_key="grant-2026-08-02")
    assert second["replayed"] is True
    assert second["balance"] == 500.0

    ledger = client.get(
        f"/api/v1/billing-account-entries?billing_account_id={account['id']}", headers=HEADERS
    ).json()["data"]
    assert len(ledger) == 1


def test_a_multi_line_grant_may_carry_an_idempotency_key(client: TestClient) -> None:
    """The key names the CALL. Conflating it with the row made any keyed grant
    of more than one line collide with itself on the unique index."""
    account = points_account(client)
    lines = [
        {"amount": 300.0, "reason": "earned", "expires_at": "2027-12-31T00:00:00Z"},
        {"amount": 200.0, "reason": "earned"},
    ]

    posted = entries(client, account["id"], lines, idempotency_key="grant-batch-1")
    assert posted["replayed"] is False
    assert len(posted["entries"]) == 2
    assert posted["balance"] == 500.0

    replayed = entries(client, account["id"], lines, idempotency_key="grant-batch-1")
    assert replayed["replayed"] is True
    assert len(replayed["entries"]) == 2
    assert replayed["balance"] == 500.0

    ledger = client.get(
        f"/api/v1/billing-account-entries?billing_account_id={account['id']}", headers=HEADERS
    ).json()["data"]
    assert len(ledger) == 2


def test_a_mistake_is_reversed_by_a_counter_entry(client: TestClient) -> None:
    account = points_account(client)
    posted = entries(client, account["id"], [{"amount": 500.0, "reason": "earned"}])
    entry_id = posted["entries"][0]["id"]

    entries(
        client, account["id"],
        [{"amount": -500.0, "reason": "adjustment", "description": "发错人了",
          "entity_type": "billing_account_entry", "entity_id": entry_id}],
    )

    ledger = client.get(
        f"/api/v1/billing-account-entries?billing_account_id={account['id']}", headers=HEADERS
    ).json()["data"]
    assert sorted(row["amount"] for row in ledger) == [-500.0, 500.0]
    assert client.get(
        f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS
    ).json()["data"]["balance"] == 0.0

    # the ledger has no edit and no delete
    assert client.patch(
        f"/api/v1/billing-account-entries/{entry_id}", json={"amount": 1.0}, headers=HEADERS
    ).status_code == 404
    assert client.delete(
        f"/api/v1/billing-account-entries/{entry_id}", headers=HEADERS
    ).status_code == 404


def test_an_account_names_exactly_one_owner(client: TestClient) -> None:
    buyer = customer(client)
    person = employee(client)

    none_named = client.post(
        "/api/v1/billing-accounts",
        json={"name": "无主账户", "unit_type": "points", "unit": "point"},
        headers=HEADERS,
    )
    assert none_named.status_code == 422
    assert "exactly one owner" in none_named.json()["detail"]

    two_named = client.post(
        "/api/v1/billing-accounts",
        json={
            "name": "两个主", "unit_type": "points", "unit": "point",
            "customer_id": buyer["id"], "employee_id": person,
        },
        headers=HEADERS,
    )
    assert two_named.status_code == 422


def test_the_unit_is_checked_against_the_right_vocabulary(client: TestClient) -> None:
    buyer = customer(client)

    bad_currency = client.post(
        "/api/v1/billing-accounts",
        json={"name": "x", "unit_type": "currency", "unit": "point", "customer_id": buyer["id"]},
        headers=HEADERS,
    )
    assert bad_currency.status_code == 422
    assert "3-letter currency code" in bad_currency.json()["detail"]

    bad_points = client.post(
        "/api/v1/billing-accounts",
        json={"name": "x", "unit_type": "points", "unit": "made_up", "customer_id": buyer["id"]},
        headers=HEADERS,
    )
    assert bad_points.status_code == 422
    assert "point" in bad_points.json()["detail"]

    # and the vocabulary is tenant-extensible
    assert client.post(
        "/api/v1/type-options",
        json={"family": "billing_account_unit", "name": "fuel_card", "title": "油卡额度"},
        headers=HEADERS,
    ).status_code == 201
    assert points_account(client, unit="fuel_card", customer_id=buyer["id"])["unit"] == "fuel_card"


def test_the_unit_and_owner_are_immutable(client: TestClient) -> None:
    """Each of them decides what may be posted and to whom, so changing one
    would reinterpret every entry already recorded."""
    account = points_account(client)

    response = client.patch(
        f"/api/v1/billing-accounts/{account['id']}",
        json={"unit_type": "currency", "unit": "CNY", "customer_id": customer(client, "别家")["id"]},
        headers=HEADERS,
    )
    assert response.status_code == 422
    after = client.get(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS).json()["data"]
    assert after["unit_type"] == "points"


def test_an_expires_at_only_means_something_on_a_points_account(client: TestClient) -> None:
    account = money_account(client)
    body = entries(
        client, account["id"],
        [{"amount": 100.0, "reason": "deposit", "expires_at": "2026-12-31T00:00:00Z"}],
        expect=422,
    )
    assert "points account" in body["detail"]


def test_the_reason_vocabulary_is_gated_and_extensible(client: TestClient) -> None:
    account = points_account(client)

    body = entries(client, account["id"], [{"amount": 10.0, "reason": "made_up"}], expect=422)
    assert "earned" in body["detail"]

    assert client.post(
        "/api/v1/type-options",
        json={"family": "billing_account_entry_reason", "name": "birthday", "title": "生日赠送"},
        headers=HEADERS,
    ).status_code == 201
    assert entries(client, account["id"], [{"amount": 88.0, "reason": "birthday"}])["balance"] == 88.0


def test_the_credit_limit_cannot_be_cut_below_what_is_drawn(client: TestClient) -> None:
    account = money_account(client, credit_limit=50000.0)
    entries(client, account["id"], [{"amount": -30000.0, "reason": "charge"}])

    response = client.patch(
        f"/api/v1/billing-accounts/{account['id']}", json={"credit_limit": 10000.0}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "already drawn" in response.json()["detail"]

    # raising it, or lowering it to something still covered, is fine
    assert client.patch(
        f"/api/v1/billing-accounts/{account['id']}", json={"credit_limit": 40000.0}, headers=HEADERS
    ).status_code == 200


def test_an_account_holding_a_balance_cannot_be_deleted(client: TestClient) -> None:
    account = points_account(client, opening_balance=500.0)

    blocked = client.delete(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS)
    assert blocked.status_code == 409
    assert "still holds" in blocked.json()["detail"]

    entries(client, account["id"], [{"amount": -500.0, "reason": "adjustment"}])
    assert client.delete(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS).status_code == 404
    assert client.post(
        f"/api/v1/billing-accounts/{account['id']}/restore", headers=HEADERS
    ).status_code == 200


def test_the_over_limit_queue_finds_accounts_past_their_line(client: TestClient) -> None:
    within = money_account(client, credit_limit=50000.0)
    past = money_account(client, credit_limit=1000.0, customer_id=customer(client, "欠款客户")["id"])
    entries(client, within["id"], [{"amount": -20000.0, "reason": "charge"}])
    entries(client, past["id"], [{"amount": -1000.0, "reason": "charge"}])

    queue = client.get(
        "/api/v1/billing-accounts?unit_type=currency&over_limit=true", headers=HEADERS
    ).json()["data"]
    assert [row["id"] for row in queue] == [past["id"]]


def test_one_owner_may_hold_several_accounts(client: TestClient) -> None:
    """The '各种积分或credit' case: a customer with stored value, loyalty points
    and a coupon quota is three accounts, not three columns."""
    buyer = customer(client)
    money_account(client, customer_id=buyer["id"], name="储值")
    points_account(client, customer_id=buyer["id"], name="积分")
    points_account(client, customer_id=buyer["id"], name="券额", unit="coupon")

    held = client.get(
        f"/api/v1/billing-accounts?customer_id={buyer['id']}", headers=HEADERS
    ).json()["data"]
    assert len(held) == 3
    assert {row["unit"] for row in held} == {"CNY", "point", "coupon"}


def test_the_expiry_queue_shows_batches_nothing_has_expired_yet(client: TestClient) -> None:
    account = points_account(client)
    entries(
        client, account["id"],
        [
            {"amount": 300.0, "reason": "earned", "expires_at": "2025-12-31T00:00:00Z"},
            {"amount": 200.0, "reason": "earned", "expires_at": "2026-06-30T00:00:00Z"},
            {"amount": 100.0, "reason": "earned", "expires_at": "2027-12-31T00:00:00Z"},
            # no expiry at all — never in the queue
            {"amount": 50.0, "reason": "earned"},
        ],
    )

    due = client.get(
        f"/api/v1/billing-accounts/{account['id']}/expiring?before=2026-08-02T00:00:00Z",
        headers=HEADERS,
    ).json()["data"]
    assert due["expiring_amount"] == 500.0
    assert [entry["amount"] for entry in due["entries"]] == [300.0, 200.0]
    assert due["unit"] == "point"


def test_the_expiry_sweep_is_idempotent(client: TestClient) -> None:
    """An expiry names the earn batch it expired, so re-running the sweep sees
    that batch as handled instead of expiring it twice."""
    account = points_account(client)
    posted = entries(
        client, account["id"],
        [{"amount": 300.0, "reason": "earned", "expires_at": "2025-12-31T00:00:00Z"}],
    )
    batch_id = posted["entries"][0]["id"]

    url = f"/api/v1/billing-accounts/{account['id']}/expiring?before=2026-08-02T00:00:00Z"
    first = client.get(url, headers=HEADERS).json()["data"]
    assert first["expiring_amount"] == 300.0

    # the sweep writes the expiry, pointing at the batch it consumed
    entries(
        client, account["id"],
        [{"amount": -300.0, "reason": "expired", "description": "2025 年积分到期",
          "entity_type": "billing_account_entry", "entity_id": batch_id}],
    )

    second = client.get(url, headers=HEADERS).json()["data"]
    assert second["entries"] == []
    assert second["expiring_amount"] == 0.0
    assert client.get(
        f"/api/v1/billing-accounts/{account['id']}", headers=HEADERS
    ).json()["data"]["balance"] == 0.0


def test_the_expiring_amount_is_the_batch_sum_not_a_verdict(client: TestClient) -> None:
    """Whether a batch survived redemption depends on FIFO/LIFO/pool, which is
    tenant policy. The server reports the batches; the agent decides."""
    account = points_account(client)
    entries(
        client, account["id"],
        [{"amount": 300.0, "reason": "earned", "expires_at": "2025-12-31T00:00:00Z"}],
    )
    entries(client, account["id"], [{"amount": -250.0, "reason": "redeemed"}])

    due = client.get(
        f"/api/v1/billing-accounts/{account['id']}/expiring?before=2026-08-02T00:00:00Z",
        headers=HEADERS,
    ).json()["data"]
    # the batch is still reported at its full size; only 50 actually remain
    assert due["expiring_amount"] == 300.0
    assert due["balance"] == 50.0


def test_a_money_account_has_no_expiry_block_in_its_detail(client: TestClient) -> None:
    account = money_account(client, opening_balance=1000.0)
    detail = client.get(
        f"/api/v1/billing-accounts/{account['id']}/detail", headers=HEADERS
    ).json()["data"]
    assert detail["expiring_entry_count"] == 0
    assert detail["expiring_amount"] == 0.0


def test_posting_can_be_scoped_to_one_unit_type(scoped_client) -> None:
    """财务管钱账、会员运营管积分账 — granting points is the fraud-prone action,
    so it is separable from moving money."""
    service, points_only = scoped_client
    buyer = service["client"].post(
        "/api/v1/customers", json={"name": "市一院"}, headers=service["headers"]
    ).json()["data"]
    money = service["client"].post(
        "/api/v1/billing-accounts",
        json={"name": "储值", "unit_type": "currency", "unit": "CNY", "customer_id": buyer["id"]},
        headers=service["headers"],
    ).json()["data"]
    points = service["client"].post(
        "/api/v1/billing-accounts",
        json={"name": "积分", "unit_type": "points", "unit": "point", "customer_id": buyer["id"]},
        headers=service["headers"],
    ).json()["data"]

    allowed = points_only["client"].post(
        f"/api/v1/billing-accounts/{points['id']}/entries",
        json={"lines": [{"amount": 100.0, "reason": "earned"}]},
        headers=points_only["headers"],
    )
    assert allowed.status_code == 200, allowed.text

    refused = points_only["client"].post(
        f"/api/v1/billing-accounts/{money['id']}/entries",
        json={"lines": [{"amount": 100.0, "reason": "deposit"}]},
        headers=points_only["headers"],
    )
    assert refused.status_code == 403
    assert "billing_account.post:currency" in refused.json()["detail"]

    # and opening an account is a different grant again
    assert points_only["client"].post(
        "/api/v1/billing-accounts",
        json={"name": "x", "unit_type": "points", "unit": "point", "customer_id": buyer["id"]},
        headers=points_only["headers"],
    ).status_code == 403


@pytest.fixture()
def scoped_client() -> Generator[tuple[dict, dict], None, None]:
    """A registered tenant plus a user-bound key holding only
    `billing_account.post:points`."""
    from app.services.emails import outbox

    def token_from(body: str) -> str:
        for line in body.splitlines():
            if "token=" in line:
                return line.rsplit("token=", 1)[1].strip()
        raise AssertionError("no token in email")

    with make_client([]) as test_client:
        data = bootstrap_tenant(test_client, company_name="Loyalty Co", email="admin@loyalty-co.com", password="loyal-pass1234")
        service = {"client": test_client, "headers": {"X-API-Key": data["plain_text_api_key"]}}

        assert test_client.post(
            "/api/v1/roles",
            json={"name": "loyalty_ops", "permissions": ["billing_account.post:points"]},
            headers=service["headers"],
        ).status_code == 201
        user_id = test_client.post(
            "/api/v1/auth/invitations",
            json={"email": "ops@loyalty-co.com", "role": "loyalty_ops"},
            headers=service["headers"],
        ).json()["data"]["id"]
        test_client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
        )
        key = test_client.post(
            "/api/v1/tenant/api-keys",
            json={"label": "loyalty-agent", "user_id": user_id},
            headers=service["headers"],
        ).json()["data"]["plain_text_api_key"]
        yield service, {"client": test_client, "headers": {"X-API-Key": key}}


def test_the_ledger_and_the_balance_are_quantised_once(client: TestClient) -> None:
    """Review R09: two lines of 0.015 left the balance at 0.03 and the rows
    summing to 0.04 — the total rounded once, the rows once each. Amounts now
    carry at most two decimals, and the balance is the Decimal sum of exactly
    the figures the rows carry."""
    acct = money_account(client)
    refused = client.post(f"/api/v1/billing-accounts/{acct['id']}/entries", headers=HEADERS,
                          json={"lines": [{"amount": 0.015, "reason": "deposit"}]})
    assert refused.status_code == 422 and "two decimals" in refused.text
    ok = client.post(f"/api/v1/billing-accounts/{acct['id']}/entries", headers=HEADERS,
                     json={"lines": [{"amount": 0.1, "reason": "deposit"}, {"amount": 0.2, "reason": "deposit"},
                                     {"amount": 0.7, "reason": "deposit"}, {"amount": -0.3, "reason": "charge"}]})
    assert ok.status_code == 200, ok.text
    balance = float(client.get(f"/api/v1/billing-accounts/{acct['id']}", headers=HEADERS).json()["data"]["balance"])
    rows = client.get("/api/v1/billing-account-entries", params={"billing_account_id": acct["id"]}, headers=HEADERS).json()["data"]
    assert balance == 0.7 and round(sum(float(r["amount"]) for r in rows), 2) == 0.7, (balance, rows)
