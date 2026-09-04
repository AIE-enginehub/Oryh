"""Archived is history, not a quieter kind of live.

An account entered by mistake, with a mistaken statement imported into it,
was archived — and the agent kept reading its lines as this month's cash.
What is pinned: master-data lists answer with active rows unless asked
(`status=archived` / `status=all`); an archived account's register lines
and an archived position's movements leave the default lists with their
parent, come back only when the parent is named or history is asked for,
and then say `archived` on every row; the reconciliation queue never shows
them.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def books():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="History Co", email="admin@history.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        cashier = invite_member(client, admin, "cashier", ["fin_account.manage"])

        def account(name: str) -> dict:
            return client.post("/api/v1/fin-accounts", headers=cashier, json={
                "name": name, "institution": "招商银行", "opening_balance": 100.0,
                "opening_date": "2026-08-01"}).json()["data"]

        def line(account_id: str, amount: float, **extra) -> dict:
            return client.post("/api/v1/fin-account-transactions", headers=cashier,
                               json={"fin_account_id": account_id, "amount": amount, **extra}).json()["data"]

        yield {"client": client, "admin": admin, "cashier": cashier, "account": account, "line": line}


def test_master_data_lists_answer_with_active_rows_unless_asked(books) -> None:
    client, admin = books["client"], books["admin"]
    live = client.post("/api/v1/customers", json={"name": "在营客户"}, headers=admin).json()["data"]
    gone = client.post("/api/v1/customers", json={"name": "误录客户"}, headers=admin).json()["data"]
    assert client.delete(f"/api/v1/customers/{gone['id']}", headers=admin).status_code == 204

    names = lambda **params: {r["name"] for r in client.get(  # noqa: E731
        "/api/v1/customers", headers=admin, params=params).json()["data"]}
    assert names() == {"在营客户"}, "the everyday answer is the live rows"
    assert names(status="archived") == {"误录客户"}
    assert names(status="all") == {"在营客户", "误录客户"}
    assert client.get(f"/api/v1/customers/{gone['id']}", headers=admin).json()["data"]["status"] == "archived", \
        "a direct read still answers — history is kept, not hidden"
    assert live["status"] == "active"


def test_an_archived_accounts_register_is_history(books) -> None:
    client, cashier = books["client"], books["cashier"]
    right = books["account"]("招行基本户")
    wrong = books["account"]("误录的户")
    kept = books["line"](right["id"], 50.0, description="real receipt")
    mistaken = books["line"](wrong["id"], 999.0, description="imported by mistake")
    assert client.delete(f"/api/v1/fin-accounts/{wrong['id']}", headers=cashier).status_code == 204

    listed = {r["id"] for r in client.get("/api/v1/fin-account-transactions",
                                          headers=cashier).json()["data"]}
    assert kept["id"] in listed and mistaken["id"] not in listed, \
        "an archived account's lines leave the everyday list with their account"
    accounts = {r["name"] for r in client.get("/api/v1/fin-accounts", headers=cashier).json()["data"]}
    assert accounts == {"招行基本户"}, "the archived account leaves the account list too"

    queue = {r["id"] for r in client.get("/api/v1/fin-account-transactions",
                                         params={"unlinked": True}, headers=cashier).json()["data"]}
    assert mistaken["id"] not in queue, "history never waits in the reconciliation queue"

    named = client.get("/api/v1/fin-account-transactions",
                       params={"fin_account_id": wrong["id"]}, headers=cashier).json()["data"]
    assert mistaken["id"] in {r["id"] for r in named}, "naming the account answers with its history"
    assert all(r["account_status"] == "archived" for r in named), "when history is shown, every row says so"
    widened = {r["id"] for r in client.get("/api/v1/fin-account-transactions",
                                           params={"include_archived_accounts": True},
                                           headers=cashier).json()["data"]}
    assert {kept["id"], mistaken["id"]} <= widened

    revived = client.patch(f"/api/v1/fin-accounts/{wrong['id']}", headers=cashier,
                           json={"status": "active"})
    assert revived.status_code == 200
    assert mistaken["id"] in {r["id"] for r in client.get(
        "/api/v1/fin-account-transactions", headers=cashier).json()["data"]}, \
        "reviving the account brings its history back — nothing was lost"


def test_an_archived_positions_movements_are_history(books) -> None:
    client, admin = books["client"], books["admin"]
    product = client.post("/api/v1/products", json={"name": "Cup"}, headers=admin).json()["data"]["id"]
    live = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": product, "facility": "main", "initial_quantity": 5}).json()["data"]
    wrong = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": product, "facility": "ghost", "initial_quantity": 7}).json()["data"]
    assert client.delete(f"/api/v1/inventory-items/{wrong['id']}", headers=admin).status_code == 204

    rows = client.get("/api/v1/inventory-item-details", headers=admin).json()["data"]
    assert {r["inventory_item_id"] for r in rows} == {live["id"]}, \
        "the archived position's movements leave the everyday list"
    named = client.get("/api/v1/inventory-item-details",
                       params={"inventory_item_id": wrong["id"]}, headers=admin).json()["data"]
    assert named and all(r["item_status"] == "archived" for r in named)
    positions = {r["id"] for r in client.get("/api/v1/inventory-items", headers=admin).json()["data"]}
    assert positions == {live["id"]}
