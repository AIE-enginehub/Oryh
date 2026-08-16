"""Charging documents to a billing account: occupation, transfer, release.

The acceptance test here is a scenario stated by the product owner, numbers and
all, and `test_the_whole_prepaid_and_credit_story` walks it verbatim: overdraft
100, deposit 100, order 150 charged (available 50), invoice takes the
occupation over, second deposit (available 150), then 核销 moves deposit money
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

import pytest

from conftest import provision_tenant


@pytest.fixture()
def shop(client):
    """A tenant, a customer with an overdraft-100 account, and a helper set."""
    ctx = provision_tenant(client, company_name="Charge Co", email="admin@charge-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    emp = client.post("/api/v1/employees", json={"name": "小销"},
                      headers=key).json()["data"]["id"]
    cust = client.post("/api/v1/customers", json={"name": "大客户"},
                       headers=key).json()["data"]["id"]
    account = client.post("/api/v1/billing-accounts", json={
        "name": "大客户往来户", "unit_type": "currency", "unit": "CNY",
        "customer_id": cust, "credit_limit": 100.0,
    }, headers=key)
    assert account.status_code == 201, account.text
    account = account.json()["data"]["id"]
    return client, key, emp, cust, account


def _detail(client, key, account):
    data = client.get(f"/api/v1/billing-accounts/{account}/detail", headers=key).json()["data"]
    return data["balance"], data["exposure_amount"], data["available_amount"]


def _deposit(client, key, cust, amount, note):
    payment = client.post("/api/v1/payments", json={
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

    # 可透支 100,预存 100 —— 总 credit 200
    p1 = _deposit(client, key, cust, 100.0, "第一笔预存")
    assert _detail(client, key, account) == (100.0, 0.0, 200.0)

    # 下单 150 挂账 —— 还剩 credit 50
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "一批货",
        "billing_account_id": account, "total_amount": 150.0,
    }, headers=key)
    assert order.status_code == 201, order.text
    order = order.json()["data"]["id"]
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)

    # gap 期间的双花:再下 100 的单必须被拒,409 报三个数
    refused = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "还想再订",
        "billing_account_id": account, "total_amount": 100.0,
    }, headers=key)
    assert refused.status_code == 409, refused.text
    assert "50" in refused.json()["detail"]

    # 交付开票 150,带同一账户 —— 占用平移,可用不变
    invoice = client.post("/api/v1/invoices", json={
        "direction": "sales", "employee_id": emp, "customer_id": cust,
        "title": "货款发票", "total_amount": 150.0, "currency": "CNY",
        "billing_account_id": account, "sales_order_id": order,
    }, headers=key)
    assert invoice.status_code == 201, invoice.text
    invoice = invoice.json()["data"]["id"]
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)

    # 又存 100 —— 剩余 credit 150
    p2 = _deposit(client, key, cust, 100.0, "第二笔预存")
    assert _detail(client, key, account) == (200.0, 150.0, 150.0)

    # 核销:第一笔预存 100 划拨到发票(一次请求,原子)
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

    # 第二笔的 50 也划拨过去 —— 发票结清
    transfer2 = client.post(f"/api/v1/payments/{p2}/apply", json={
        "lines": [
            {"applied_to_type": "billing_account", "applied_to_id": account,
             "amount_applied": -50.0},
            {"applied_to_type": "invoice", "applied_to_id": invoice,
             "amount_applied": 50.0},
        ],
    }, headers=key)
    assert transfer2.status_code == 200, transfer2.text

    # 终态:balance 50,总 credit 150,发票 applied 150,挂账清单已空
    balance, exposure, available = _detail(client, key, account)
    assert (balance, exposure, available) == (50.0, 0.0, 150.0)
    detail = client.get(f"/api/v1/billing-accounts/{account}/detail", headers=key).json()["data"]
    assert detail["charged_orders"] == []
    assert detail["charged_invoices"] == []
    settled = client.get(f"/api/v1/invoices/{invoice}", headers=key).json()["data"]
    assert float(settled["applied_amount"]) == 150.0
    # 台账讲完整个故事:+100 P1、+100 P2、-100 划拨、-50 划拨,剩下的 50 是 P2 的
    reasons = [(row["reason"], row["amount"]) for row in detail["entries"]]
    assert ("charge", -100.0) in reasons and ("charge", -50.0) in reasons
    assert ("deposit", 100.0) in reasons


def test_the_tob_release_paths(shop) -> None:
    """部分取消删行、负向调整、整单取消置空 —— credit 每一步自动回来。"""
    client, key, emp, cust, account = shop

    # 额度 100,订两行 40+50 —— 占用 90,可用 10
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "toB 大单",
        "billing_account_id": account,
        "items": [
            {"product_name_snapshot": "甲件", "quantity": 1, "unit_price": 40.0},
            {"product_name_snapshot": "乙件", "quantity": 1, "unit_price": 50.0},
        ],
    }, headers=key)
    assert order.status_code == 201, order.text
    payload = order.json()["data"]
    order = payload["id"]
    lines = {row["product_name_snapshot"]: row["id"] for row in payload["items"]}
    assert _detail(client, key, account)[1:] == (90.0, 10.0)

    # 部分取消:删掉 40 的那行 → 占用自动回落
    removed = client.delete(f"/api/v1/sales-order-items/{lines['甲件']}", headers=key)
    assert removed.status_code == 204, removed.text
    assert _detail(client, key, account)[1:] == (50.0, 50.0)

    # 再让一步:负向调整 30 → 占用再回 30
    adjusted = client.post("/api/v1/sales-order-adjustments", json={
        "order_id": order, "adjustment_type": "discount",
        "description": "部分取消折让", "amount": -30.0,
    }, headers=key)
    assert adjusted.status_code == 201, adjusted.text
    assert _detail(client, key, account)[1:] == (20.0, 80.0)

    # 整单取消留档:置空即释放,永远不被守卫拦
    cleared = client.patch(f"/api/v1/sales-orders/{order}",
                           json={"billing_account_id": None}, headers=key)
    assert cleared.status_code == 200, cleared.text
    assert _detail(client, key, account)[1:] == (0.0, 100.0)


def test_growing_a_charged_order_re_runs_the_guard(shop) -> None:
    client, key, emp, cust, account = shop
    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "先小后大",
        "billing_account_id": account,
        "items": [{"product_name_snapshot": "首件", "quantity": 1, "unit_price": 80.0}],
    }, headers=key).json()["data"]["id"]

    grown = client.post("/api/v1/sales-order-items", json={
        "order_id": order, "product_name_snapshot": "追加件",
        "quantity": 1, "unit_price": 50.0,
    }, headers=key)
    assert grown.status_code == 409, grown.text
    assert "credit" in grown.json()["detail"]


def test_restore_re_checks_what_delete_released(shop) -> None:
    client, key, emp, cust, account = shop
    first = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "先占着",
        "billing_account_id": account, "total_amount": 100.0,
    }, headers=key).json()["data"]["id"]

    client.request("DELETE", f"/api/v1/sales-orders/{first}", json={}, headers=key)
    # released credit gets spent by a second order…
    second = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "抢走额度",
        "billing_account_id": account, "total_amount": 80.0,
    }, headers=key)
    assert second.status_code == 201, second.text

    # …so the first cannot silently come back
    revived = client.post(f"/api/v1/sales-orders/{first}/restore", json={}, headers=key)
    assert revived.status_code == 409, revived.text


def test_owner_and_unit_guards(shop) -> None:
    client, key, emp, cust, account = shop
    stranger = client.post("/api/v1/customers", json={"name": "别人家"},
                           headers=key).json()["data"]["id"]
    wrong_owner = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": stranger, "title": "拿别人的账户",
        "billing_account_id": account, "total_amount": 10.0,
    }, headers=key)
    assert wrong_owner.status_code == 409

    points = client.post("/api/v1/billing-accounts", json={
        "name": "积分户", "unit_type": "points", "unit": "point",
        "customer_id": cust,
    }, headers=key).json()["data"]["id"]
    not_money = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "customer_id": cust, "title": "拿积分挂账",
        "billing_account_id": points, "total_amount": 10.0,
    }, headers=key)
    assert not_money.status_code == 409


def test_the_vendor_mirror_and_the_deposit_direction(shop) -> None:
    """我们在 vendor 的账户:打款是 outbound 且必须记为存入 —— 修正前它被记成
    refund,余额直接为负。这是镜像暴露的真 bug 的回归测试。"""
    client, key, emp, _cust, _account = shop
    vendor = client.post("/api/v1/vendors", json={"name": "老供应商"},
                         headers=key).json()["data"]["id"]
    account = client.post("/api/v1/billing-accounts", json={
        "name": "供应商往来户", "unit_type": "currency", "unit": "CNY",
        "vendor_id": vendor, "credit_limit": 100.0,
    }, headers=key).json()["data"]["id"]

    prepay = client.post("/api/v1/payments", json={
        "direction": "outbound", "vendor_id": vendor, "amount": 100.0,
        "employee_id": emp, "remarks": "给供应商的预付",
    }, headers=key).json()["data"]["id"]
    applied = client.post(f"/api/v1/payments/{prepay}/apply", json={
        "lines": [{"applied_to_type": "billing_account", "applied_to_id": account,
                   "amount_applied": 100.0}],
    }, headers=key)
    assert applied.status_code == 200, applied.text
    balance, exposure, available = _detail(client, key, account)
    assert (balance, exposure, available) == (100.0, 0.0, 200.0)

    po = client.post("/api/v1/purchase-orders", json={
        "employee_id": emp, "vendor_id": vendor, "title": "补货",
        "billing_account_id": account, "total_amount": 150.0,
    }, headers=key)
    assert po.status_code == 201, po.text
    assert _detail(client, key, account) == (100.0, 150.0, 50.0)


def test_a_strangers_cheque_cannot_fund_this_account(shop) -> None:
    client, key, _emp, _cust, account = shop  # noqa: the underscore names are used below
    other = client.post("/api/v1/customers", json={"name": "路人"},
                        headers=key).json()["data"]["id"]
    payment = client.post("/api/v1/payments", json={
        "direction": "inbound", "customer_id": other, "amount": 30.0,
        "employee_id": _emp, "remarks": "别人的钱",
    }, headers=key).json()["data"]["id"]
    refused = client.post(f"/api/v1/payments/{payment}/apply", json={
        "lines": [{"applied_to_type": "billing_account", "applied_to_id": account,
                   "amount_applied": 30.0}],
    }, headers=key)
    assert refused.status_code == 409, refused.text
    assert "belongs to a different party" in refused.json()["detail"]
