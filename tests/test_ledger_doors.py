"""The second round of "no row typed by hand" (docs/ledger-writes-are-business-acts-2026-09-11.zh.md).

The account ledger has the same doors the stock ledger got: money through
payments, expiry through the sweep's own write, opening balances through the
account's creation, everything else through a tenant-defined account document
posted once — and no direct `/entries` write. Two smaller doors closed with
it: an order that ships by shipments takes its freight facts from the
shipment, not from header fields beside it; and the `submitted` approval fact
is the server's, a person's credential records decisions only.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Doors Co", email="admin@doors.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        points = client.post("/api/v1/billing-accounts", headers=admin, json={
            "name": "积分", "unit_type": "points", "unit": "point", "customer_id": customer}).json()["data"]
        money = client.post("/api/v1/billing-accounts", headers=admin, json={
            "name": "储值", "unit_type": "currency", "unit": "CNY", "customer_id": customer,
            "opening_balance": 1000.0}).json()["data"]

        def define(object_type: str, reason: str, states=("approved",)) -> object:
            return client.post("/api/v1/object-type-definitions", headers=admin, json={
                "object_type": object_type, "state_machine": {
                    "initial": states[0], "states": list(states),
                    "transitions": {s: ([states[i + 1]] if i + 1 < len(states) else []) for i, s in enumerate(states)},
                    "account_effect": {"reason": reason, "state": states[-1]}}})

        yield {"client": client, "admin": admin, "customer": customer, "employee": emp,
               "points": points, "money": money, "define": define}


def test_there_is_no_direct_account_write(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    gone = c.post(f"/api/v1/billing-accounts/{desk['points']['id']}/entries", headers=admin,
                  json={"lines": [{"amount": 100.0, "reason": "earned"}]})
    assert gone.status_code in (404, 405), gone.text


def test_reserved_reasons_keep_their_own_doors(desk) -> None:
    for reason in ("deposit", "charge", "refund", "expired", "initial", "import_initial"):
        refused = desk["define"](f"acct_{reason}", reason)
        assert refused.status_code == 422, (reason, refused.text)
        assert "own door" in refused.json()["detail"]
    assert desk["define"]("points_grant", "earned").status_code == 201
    no_effect = desk["client"].post("/api/v1/object-type-definitions", headers=desk["admin"], json={
        "object_type": "memo", "json_schema": {}})
    assert no_effect.status_code == 201


def test_a_transfer_is_one_document_on_two_accounts(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    other = c.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "储值 B", "unit_type": "currency", "unit": "CNY", "customer_id": desk["customer"]}).json()["data"]
    assert desk["define"]("balance_transfer", "transfer").status_code == 201
    doc = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "balance_transfer", "title": "划转 300", "status": "approved",
        "payload": {"lines": [{"billing_account_id": desk["money"]["id"], "amount": -300.0},
                              {"billing_account_id": other["id"], "amount": 300.0}]}}).json()["data"]
    posted = c.post(f"/api/v1/business-objects/{doc['id']}/post-entries", headers=admin)
    assert posted.status_code == 200, posted.text
    balances = {row["billing_account_id"]: row["balance"] for row in posted.json()["data"]["lines"]}
    assert balances == {desk["money"]["id"]: 700.0, other["id"]: 300.0}
    assert posted.json()["data"]["reason"] == "transfer"


def test_a_memo_posts_nothing_and_a_frozen_account_takes_nothing(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    c.post("/api/v1/object-type-definitions", headers=admin, json={"object_type": "memo", "json_schema": {}})
    memo = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "memo", "title": "note",
        "payload": {"lines": [{"billing_account_id": desk["points"]["id"], "amount": 5}]}}).json()["data"]
    refused = c.post(f"/api/v1/business-objects/{memo['id']}/post-entries", headers=admin)
    assert refused.status_code == 422 and "account_effect" in refused.json()["detail"]
    desk["define"]("points_grant", "earned")
    c.patch(f"/api/v1/billing-accounts/{desk['points']['id']}", headers=admin, json={"status": "frozen"})
    grant = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "points_grant", "title": "grant", "status": "approved",
        "payload": {"lines": [{"billing_account_id": desk["points"]["id"], "amount": 50}]}}).json()["data"]
    frozen = c.post(f"/api/v1/business-objects/{grant['id']}/post-entries", headers=admin)
    assert frozen.status_code == 409 and "frozen" in frozen.json()["detail"]


def test_the_expiry_door_holds_the_sweep_to_its_facts(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("points_grant", "earned")
    grant = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "points_grant", "title": "grant", "status": "approved",
        "payload": {"lines": [{"billing_account_id": desk["points"]["id"], "amount": 300.0,
                               "expires_at": "2025-12-31T00:00:00Z"},
                              {"billing_account_id": desk["points"]["id"], "amount": 50.0}]}}).json()["data"]
    rows = c.post(f"/api/v1/business-objects/{grant['id']}/post-entries", headers=admin).json()["data"]["lines"]
    batch, evergreen = rows[0]["entry_id"], rows[1]["entry_id"]
    url = f"/api/v1/billing-accounts/{desk['points']['id']}/expire"
    too_much = c.post(url, headers=admin, json={"lines": [{"entry_id": batch, "amount": 301.0}]})
    assert too_much.status_code == 422 and "holds 300.00" in too_much.json()["detail"]
    not_a_batch = c.post(url, headers=admin, json={"lines": [{"entry_id": evergreen, "amount": 10.0}]})
    assert not_a_batch.status_code == 422
    partial = c.post(url, headers=admin, json={"lines": [{"entry_id": batch, "amount": 250.0,
                                                          "description": "50 were redeemed FIFO"}]})
    assert partial.status_code == 200, partial.text
    assert partial.json()["data"]["balance"] == 100.0
    again = c.post(url, headers=admin, json={"lines": [{"entry_id": batch, "amount": 50.0}]})
    assert again.status_code == 409, "a batch expires once, whatever amount"


def test_an_order_that_ships_by_shipments_takes_freight_facts_from_the_shipment(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    product = c.post("/api/v1/products", json={"name": "Cup"}, headers=admin).json()["data"]["id"]
    order = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "一单",
        "items": [{"product_id": product, "quantity": 1, "unit_price": 10}]}).json()["data"]
    # no shipment yet: the header is the only place, and it is open
    ok = c.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin, json={"logistics_tracking_no": "SF-1"})
    assert ok.status_code == 200, ok.text
    leg = c.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": order["id"], "carrier": "SF", "tracking_no": "SF-2"})
    assert leg.status_code == 201, leg.text
    for field, value in (("logistics_tracking_no", "SF-3"), ("logistics_company", "YTO"),
                         ("shipped_at", "2026-09-11T00:00:00Z"), ("signed_at", "2026-09-12T00:00:00Z")):
        refused = c.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin, json={field: value})
        assert refused.status_code == 409, (field, refused.text)
        assert leg.json()["data"]["shipment_no"] in refused.json()["detail"]
    remarks = c.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin, json={"remarks": "留言"})
    assert remarks.status_code == 200, "the other fulfilment facts stay open"


def test_the_submitted_fact_is_the_servers(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    approver_emp = c.post("/api/v1/employees", json={"name": "审批人"}, headers=admin).json()["data"]["id"]
    approver = invite_member(c, admin, "approver", ["approval.record"], employee_id=approver_emp)
    product = c.post("/api/v1/products", json={"name": "Cup"}, headers=admin).json()["data"]["id"]
    order = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "一单",
        "items": [{"product_id": product, "quantity": 1, "unit_price": 10}]}).json()["data"]
    forged = c.post("/api/v1/approval-records", headers=approver, json={
        "entity_type": "sales_order", "entity_id": order["id"], "action": "submitted"})
    assert forged.status_code == 403 and "server's fact" in forged.json()["detail"], forged.text
    backfilled = c.post("/api/v1/approval-records", headers=admin, json={
        "entity_type": "sales_order", "entity_id": order["id"], "action": "submitted"})
    assert backfilled.status_code == 201, "the workspace service key may backfill"
