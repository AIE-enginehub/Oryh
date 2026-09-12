"""An account document posts once; a correction is a second document.

The account ledger used to take a direct write with an idempotency key, and
the key's replay had to be compared against the body (review P0-1, item 4).
That write is gone: every row outside the payment, expiry and opening doors
comes from a tenant-defined account document posted from its declared
state, and the document itself is the idempotency — posting it again is a
409, editing it after posting changes nothing on the ledger, and a corrected
amount is a new document.
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
    client.post("/api/v1/object-type-definitions", headers=key, json={
        "object_type": "balance_adjustment", "title": "余额调整单",
        "state_machine": {"initial": "draft", "states": ["draft", "approved"],
                          "transitions": {"draft": ["approved"], "approved": []},
                          "account_effect": {"reason": "adjustment", "state": "approved"}}})
    return {"client": client, "key": key, "id": account.json()["data"]["id"]}


def document(account, lines, status="approved"):
    r = account["client"].post("/api/v1/business-objects", headers=account["key"], json={
        "object_type": "balance_adjustment", "title": "调整", "status": status,
        "payload": {"lines": [{"billing_account_id": account["id"], **line} for line in lines]}})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def post(account, doc_id):
    return account["client"].post(f"/api/v1/business-objects/{doc_id}/post-entries", headers=account["key"])


def balance_of(account) -> float:
    return float(account["client"].get(f"/api/v1/billing-accounts/{account['id']}",
                                       headers=account["key"]).json()["data"]["balance"])


def test_a_document_posts_once(account) -> None:
    doc = document(account, [{"amount": 100.0}])
    assert post(account, doc).status_code == 200
    again = post(account, doc)
    assert again.status_code == 409, again.text
    assert balance_of(account) == 100.0


def test_a_document_posts_only_from_its_declared_state(account) -> None:
    doc = document(account, [{"amount": 100.0}], status="draft")
    early = post(account, doc)
    assert early.status_code == 409 and "approved" in early.json()["detail"]
    assert balance_of(account) == 0.0


def test_editing_a_posted_document_moves_nothing(account) -> None:
    doc = document(account, [{"amount": 100.0}])
    assert post(account, doc).status_code == 200
    edited = account["client"].patch(f"/api/v1/business-objects/{doc}", headers=account["key"], json={
        "payload": {"lines": [{"billing_account_id": account["id"], "amount": 150.0}]}})
    assert edited.status_code == 200, edited.text
    assert post(account, doc).status_code == 409, "the ledger keeps what was posted"
    assert balance_of(account) == 100.0


def test_a_correction_is_a_second_document(account) -> None:
    assert post(account, document(account, [{"amount": 100.0}])).status_code == 200
    assert post(account, document(account, [{"amount": -100.0, "description": "posted in error"},
                                           {"amount": 150.0}])).status_code == 200
    assert balance_of(account) == 150.0


def test_the_floor_holds_for_the_whole_document(account) -> None:
    doc = document(account, [{"amount": 50.0}, {"amount": -80.0}])
    refused = post(account, doc)
    assert refused.status_code == 409, refused.text
    assert balance_of(account) == 0.0, "never half-posted"
