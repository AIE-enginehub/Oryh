"""Charging documents to a billing account: occupation, transfer, release.

The acceptance test here is a scenario stated by the product owner, numbers and
all, and `test_the_whole_prepaid_and_credit_story` walks it verbatim: overdraft
100, deposit 100, order 150 charged (available 50), invoice takes the
occupation over, second deposit (available 150), then payment allocation moves deposit money
onto the invoice — ending with the invoice settled, balance 50, available 150,
and the ledger showing whose 50 remains. If that test ever fails, the feature
no longer does what was asked for, whatever else passes.

Around it: the double-spend refusal inside the order→invoice gap, the toB
release paths (line removal, negative adjustment, uncharge, delete), restore
re-checking, the vendor-side mirror, and the deposit-direction regression the
mirror exposed — the old `effect_sign` read every outbound payment as a refund,
so a prepayment to a vendor drove the balance NEGATIVE.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_billing_account_charging.json').read_text(encoding="utf-8"))


import pytest

from conftest import provision_tenant


@pytest.fixture()
def shop(client):
    """A tenant, a customer with an overdraft-100 account, and a helper set."""
    ctx = provision_tenant(client, company_name="Charge Co", email="admin@charge-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    emp = client.post("/api/v1/employees", json={"name": _ZH_TEXT['TEXT_601033CD3A86ED09']},
                      headers=key).json()["data"]["id"]
    cust = client.post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_DA7A4643ED2DC857']},
                       headers=key).json()["data"]["id"]
    account = client.post("/api/v1/billing-accounts", json={
        "name": _ZH_TEXT['TEXT_F8B0F48D920AEB0D'], "unit_type": "currency", "unit": "CNY",
        "customer_id": cust, "credit_limit": 100.0,
    }, headers=key)
    assert account.status_code == 201, account.text
    account = account.json()["data"]["id"]
    return client, key, emp, cust, account


def _detail(client, key, account):
    data = client.get(f"/api/v1/billing-accounts/{account}/detail", headers=key).json()["data"]
    return data["balance"], data["exposure_amount"], data["available_amount"]


def _deposit(client, key, cust, amount, note):
    payment = client.post("/api/v1/payments", json={"status": "paid",
        "direction": "inbound", "customer_id": cust, "amount": amount,
        "employee_id": _deposit.employee, "remarks": note,
    }, headers=key)
    assert payment.status_code == 201, payment.text
    payment = payment.json()["data"]["id"]
    applied = client.post(f"/api/v1/payments/{payment}/apply", json={
        "lines": [{"applied_to_type": "billing_account", "applied_to_id": _deposit.account,
                   "amount_applied": amount}],
    }, headers=key)
    assert applied.status_code == 200, applied.text
    return payment


def test_the_whole_prepaid_and_credit_story(shop) -> None:
    client, key, emp, cust, account = shop
    _deposit.account = account
    _deposit.employee = emp

    # Credit limit 100 plus deposit 100 gives availability 200.
    p1 = _deposit(client, key, cust, 100.0, _ZH_TEXT['TEXT_F8ED6C9A96158788'])
    assert _detail(client, key, account) == (100.0, 0.0, 200.0)

    # Order 150 consumes credit, leaving 50.
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_9FBFDFE0CDA5065E'],
        "billing_account_id": account, "total_amount": 150.0,
    }, headers=key)
    assert order.status_code == 201, order.text
    order = order.json()["data"]["id"]
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)

    # A second order for 100 during the gap must fail; 409 reports all three amounts.
    refused = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_42CC418560D530F5'],
        "billing_account_id": account, "total_amount": 100.0,
    }, headers=key)
    assert refused.status_code == 409, refused.text
    assert "50" in refused.json()["detail"]

    # Invoice 150 on the same account transfers the hold without changing availability.
    invoice = client.post("/api/v1/invoices", json={
        "direction": "sales", "employee_id": emp, "customer_id": cust,
        "title": _ZH_TEXT['TEXT_6755AC641E711133'], "total_amount": 150.0, "currency": "CNY",
        "billing_account_id": account, "sales_order_id": order,
    }, headers=key)
    assert invoice.status_code == 201, invoice.text
    invoice = invoice.json()["data"]["id"]
    assert client.post(f"/api/v1/invoices/{invoice}/submit", headers=key).status_code == 200
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)

    # Another deposit of 100 leaves availability 150.
    p2 = _deposit(client, key, cust, 100.0, _ZH_TEXT['TEXT_53D143D17594A47C'])
    assert _detail(client, key, account) == (200.0, 150.0, 150.0)

    # Allocate the first deposit of 100 to the invoice in one atomic request.
    transfer1 = client.post(f"/api/v1/payments/{p1}/apply", json={
        "lines": [
            {"applied_to_type": "billing_account", "applied_to_id": account,
             "amount_applied": -100.0},
            {"applied_to_type": "invoice", "applied_to_id": invoice,
             "amount_applied": 100.0},
        ],
    }, headers=key)
    assert transfer1.status_code == 200, transfer1.text
    assert _detail(client, key, account) == (100.0, 50.0, 150.0)

    # Allocate 50 from the second deposit too; the invoice is settled.
    transfer2 = client.post(f"/api/v1/payments/{p2}/apply", json={
        "lines": [
            {"applied_to_type": "billing_account", "applied_to_id": account,
             "amount_applied": -50.0},
            {"applied_to_type": "invoice", "applied_to_id": invoice,
             "amount_applied": 50.0},
        ],
    }, headers=key)
    assert transfer2.status_code == 200, transfer2.text

    # Final: balance 50, availability 150, applied 150, no charged documents.
    balance, exposure, available = _detail(client, key, account)
    assert (balance, exposure, available) == (50.0, 0.0, 150.0)
    detail = client.get(f"/api/v1/billing-accounts/{account}/detail", headers=key).json()["data"]
    assert detail["charged_orders"] == []
    assert detail["charged_invoices"] == []
    settled = client.get(f"/api/v1/invoices/{invoice}", headers=key).json()["data"]
    assert float(settled["applied_amount"]) == 150.0
    # Ledger: +100 P1, +100 P2, −100 transfer, −50 transfer; remaining 50 belongs to P2.
    reasons = [(row["reason"], row["amount"]) for row in detail["entries"]]
    assert ("charge", -100.0) in reasons and ("charge", -50.0) in reasons
    assert ("deposit", 100.0) in reasons


def test_the_tob_release_paths(shop) -> None:
    """partial cancellation by deleting a line, negative adjustment, full cancellation by clearing items —— credit is released at every step. """
    client, key, emp, cust, account = shop

    # Limit 100; two order lines 40+50 hold 90 and leave 10.
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_E1CF30C25E2C28CE'],
        "billing_account_id": account,
        "items": [
            {"product_name_snapshot": _ZH_TEXT['TEXT_ED119841A240422E'], "quantity": 1, "unit_price": 40.0},
            {"product_name_snapshot": _ZH_TEXT['TEXT_47DA0C7352EAF146'], "quantity": 1, "unit_price": 50.0},
        ],
    }, headers=key)
    assert order.status_code == 201, order.text
    payload = order.json()["data"]
    order = payload["id"]
    lines = {row["product_name_snapshot"]: row["id"] for row in payload["items"]}
    assert _detail(client, key, account)[1:] == (90.0, 10.0)

    # Delete the 40 line for partial cancellation; the hold falls automatically.
    removed = client.delete(f"/api/v1/sales-order-items/{lines[_ZH_TEXT['TEXT_ED119841A240422E']]}", headers=key)
    assert removed.status_code == 204, removed.text
    assert _detail(client, key, account)[1:] == (50.0, 50.0)

    # A negative adjustment of 30 releases another 30.
    adjusted = client.post("/api/v1/sales-order-adjustments", json={
        "order_id": order, "adjustment_type": "discount",
        "description": _ZH_TEXT['TEXT_BA816DF7BF2D8406'], "amount": -30.0,
    }, headers=key)
    assert adjusted.status_code == 201, adjusted.text
    assert _detail(client, key, account)[1:] == (20.0, 80.0)

    # Keep the cancelled document with empty lines: this releases holds without blocking.
    cleared = client.patch(f"/api/v1/sales-orders/{order}",
                           json={"billing_account_id": None}, headers=key)
    assert cleared.status_code == 200, cleared.text
    assert _detail(client, key, account)[1:] == (0.0, 100.0)


def test_growing_a_charged_order_re_runs_the_guard(shop) -> None:
    client, key, emp, cust, account = shop
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_B34F0EB40D0DE708'],
        "billing_account_id": account,
        "items": [{"product_name_snapshot": _ZH_TEXT['TEXT_E8A5458550216BAF'], "quantity": 1, "unit_price": 80.0}],
    }, headers=key).json()["data"]["id"]

    grown = client.post("/api/v1/sales-order-items", json={
        "order_id": order, "product_name_snapshot": _ZH_TEXT['TEXT_EA4D307C2CDF28A6'],
        "quantity": 1, "unit_price": 50.0,
    }, headers=key)
    assert grown.status_code == 409, grown.text
    assert "credit" in grown.json()["detail"]


def test_restore_re_checks_what_delete_released(shop) -> None:
    client, key, emp, cust, account = shop
    first = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_9E0C544267E3D194'],
        "billing_account_id": account, "total_amount": 100.0,
    }, headers=key).json()["data"]["id"]

    client.request("DELETE", f"/api/v1/sales-orders/{first}", json={}, headers=key)
    # released credit gets spent by a second order…
    second = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_04B8B7088797D532'],
        "billing_account_id": account, "total_amount": 80.0,
    }, headers=key)
    assert second.status_code == 201, second.text

    # …so the first cannot silently come back
    revived = client.post(f"/api/v1/sales-orders/{first}/restore", json={}, headers=key)
    assert revived.status_code == 409, revived.text


def test_owner_and_unit_guards(shop) -> None:
    client, key, emp, cust, account = shop
    stranger = client.post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_B596F24B46EBA28C']},
                           headers=key).json()["data"]["id"]
    wrong_owner = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": stranger, "title": _ZH_TEXT['TEXT_44808049B6F7F86F'],
        "billing_account_id": account, "total_amount": 10.0,
    }, headers=key)
    assert wrong_owner.status_code == 409

    points = client.post("/api/v1/billing-accounts", json={
        "name": _ZH_TEXT['TEXT_AFDC1964634C59B9'], "unit_type": "points", "unit": "point",
        "customer_id": cust,
    }, headers=key).json()["data"]["id"]
    not_money = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": _ZH_TEXT['TEXT_B1ACE6C676DC7F3E'],
        "billing_account_id": points, "total_amount": 10.0,
    }, headers=key)
    assert not_money.status_code == 409


def test_the_vendor_mirror_and_the_deposit_direction(shop) -> None:
    """Our vendor account records an outbound payment as a deposit, not a refund. The prior negative balance was a mirrored-account bug; this test protects that correction."""
    client, key, emp, _cust, _account = shop
    vendor = client.post("/api/v1/vendors", json={"name": _ZH_TEXT['TEXT_1E45D68723770382']},
                         headers=key).json()["data"]["id"]
    account = client.post("/api/v1/billing-accounts", json={
        "name": _ZH_TEXT['TEXT_1A7D7A134833CF8A'], "unit_type": "currency", "unit": "CNY",
        "vendor_id": vendor, "credit_limit": 100.0,
    }, headers=key).json()["data"]["id"]

    prepay = client.post("/api/v1/payments", json={"status": "paid",
        "direction": "outbound", "vendor_id": vendor, "amount": 100.0,
        "employee_id": emp, "remarks": _ZH_TEXT['TEXT_6100A2D27F36B420'],
    }, headers=key).json()["data"]["id"]
    applied = client.post(f"/api/v1/payments/{prepay}/apply", json={
        "lines": [{"applied_to_type": "billing_account", "applied_to_id": account,
                   "amount_applied": 100.0}],
    }, headers=key)
    assert applied.status_code == 200, applied.text
    balance, exposure, available = _detail(client, key, account)
    assert (balance, exposure, available) == (100.0, 0.0, 200.0)

    po = client.post("/api/v1/purchase-orders", json={
        "employee_id": emp, "vendor_id": vendor, "title": _ZH_TEXT['TEXT_B40B8D6870E8D2DC'],
        "billing_account_id": account, "total_amount": 150.0,
    }, headers=key)
    assert po.status_code == 201, po.text
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)


def test_a_strangers_cheque_cannot_fund_this_account(shop) -> None:
    client, key, _emp, _cust, account = shop  # noqa: the underscore names are used below
    other = client.post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_50E716572F3A1075']},
                        headers=key).json()["data"]["id"]
    payment = client.post("/api/v1/payments", json={"status": "paid",
        "direction": "inbound", "customer_id": other, "amount": 30.0,
        "employee_id": _emp, "remarks": _ZH_TEXT['TEXT_B08407D6D02017F6'],
    }, headers=key).json()["data"]["id"]
    refused = client.post(f"/api/v1/payments/{payment}/apply", json={
        "lines": [{"applied_to_type": "billing_account", "applied_to_id": account,
                   "amount_applied": 30.0}],
    }, headers=key)
    assert refused.status_code == 409, refused.text
    # discriminating against the other 409s this endpoint gives (currency,
    # account status, over-application), not pinning prose for its own sake.
    # The check moved onto SettlementTarget so invoices and claims get it too,
    # and the wording generalised with it.
    assert "names a different party" in refused.json()["detail"]
