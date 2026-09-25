"""What the 2026-09-24 refactoring review found by reading duplicated code
side by side — each a fact one copy had and the other had lost.

Contract lines, originals and clauses answered every side's rows when no
contract was named; the approval-target alias of a business object could
delete a row already posted to the ledger; a billing account's detail asked
an order for a column that does not exist; a shared customer's brief showed
orders its reader could not list; a stale idempotency claim could be taken
over by a different request; a minted key was kept in plaintext for replay.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest

from app.core import idempotency
from app.models import IdempotencyRecord
from conftest import invite_member, make_client, make_stack, provision_tenant


@pytest.fixture()
def office():
    with make_stack([]) as (client, _engine):
        t = provision_tenant(client, company_name="Findings Co", email="admin@findings.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def make(collection: str, headers=None, **body) -> dict:
            r = client.post(f"/api/v1/{collection}", json=body, headers=headers or admin)
            assert r.status_code == 201, f"{collection}: {r.text}"
            return r.json()["data"]

        yield {"client": client, "admin": admin, "make": make}


def test_contract_children_follow_the_sides_the_reader_holds(office) -> None:
    client, admin, make = office["client"], office["admin"], office["make"]
    vendor = make("vendors", name="代工厂")["id"]
    customer = make("customers", name="市一医院")["id"]
    product = make("products", name="阀门")["id"]
    buying = make("contracts", title="采购合同", contract_type="oem", vendor_id=vendor, total_amount=1000)
    selling = make("contracts", title="销售合同", contract_type="sales", customer_id=customer, total_amount=2000)
    for contract in (buying, selling):
        make("contract-items", contract_id=contract["id"], product_id=product, quantity=1, unit_price=10)
        make("contract-terms", contract_id=contract["id"], term_type="payment_terms", title="付款", content="30 天")
    seller = invite_member(client, admin, "seller", ["contract.manage:sales"])
    for collection in ("contract-items", "contract-terms"):
        rows = client.get(f"/api/v1/{collection}", headers=seller).json()["data"]
        assert {row["contract_id"] for row in rows} == {selling["id"]}, \
            f"{collection}: the sales desk was shown the purchase side's rows"
    assert {c["id"] for c in client.get("/api/v1/contracts", headers=seller).json()["data"]} == {selling["id"]}


def test_the_approval_target_alias_runs_the_business_object_rules(office) -> None:
    client, admin, make = office["client"], office["admin"], office["make"]
    customer = make("customers", name="买家")["id"]
    account = make("billing-accounts", name="积分", unit_type="points", unit="point", customer_id=customer)
    defined = client.post("/api/v1/object-type-definitions", headers=admin, json={
        "object_type": "points_grant", "state_machine": {
            "initial": "approved", "states": ["approved"], "transitions": {"approved": []},
            "account_effect": {"reason": "earned", "state": "approved"}}})
    assert defined.status_code == 201, defined.text
    grant = make("approval-targets", target_type="points_grant", title="送 100 分", status="approved",
                 payload={"lines": [{"billing_account_id": account["id"], "amount": 100.0}]})
    assert grant["target_type"] == "points_grant", "the alias answers in its own vocabulary"
    posted = client.post(f"/api/v1/business-objects/{grant['id']}/post-entries", headers=admin)
    assert posted.status_code == 200, posted.text
    gone = client.delete(f"/api/v1/approval-targets/{grant['id']}", headers=admin)
    assert gone.status_code == 409, "a posted document is the ledger's source: the alias once let it go"
    edited = client.patch(f"/api/v1/approval-targets/{grant['id']}", headers=admin, json={"payload": {"lines": []}})
    assert edited.status_code == 409, edited.text
    retyped = client.patch(f"/api/v1/approval-targets/{grant['id']}", headers=admin, json={"target_type": "memo"})
    assert retyped.status_code == 422 and "target_type" in retyped.json()["detail"]
    # a todo naming the row by its old alias is retired when the row is deleted
    memo = client.post("/api/v1/object-type-definitions", headers=admin, json={"object_type": "memo", "json_schema": {}})
    assert memo.status_code == 201
    note = make("approval-targets", target_type="memo", title="便签")
    emp = make("employees", name="小李")["id"]
    todo = make("todos", employee_id=emp, entity_type="approval_target", entity_id=note["id"], title="看一眼")
    assert client.delete(f"/api/v1/approval-targets/{note['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/v1/todos/{todo['id']}", headers=admin).json()["data"]["status"] == "cancelled"


def test_a_billing_account_detail_names_the_charged_order(office) -> None:
    client, admin, make = office["client"], office["admin"], office["make"]
    customer = make("customers", name="挂账客户")["id"]
    account = make("billing-accounts", name="挂账户", unit_type="currency", unit="CNY",
                   customer_id=customer, credit_limit=10000)
    emp = make("employees", name="销售")["id"]
    order = make("sales-orders", employee_id=emp, customer_id=customer, title="挂账单", order_no="SO-CHARGED-1",
                 billing_account_id=account["id"], items=[{"product_name_snapshot": "货", "quantity": 2, "unit_price": 50}])
    detail = client.get(f"/api/v1/billing-accounts/{account['id']}/detail", headers=admin)
    assert detail.status_code == 200, detail.text
    charged = {row["id"]: row for row in detail.json()["data"]["charged_orders"]}
    assert charged[order["id"]]["number"] == "SO-CHARGED-1", "the copy asked for `order_number`, a column that does not exist"
    assert charged[order["id"]]["occupied"] == 100.0
    assert detail.json()["data"]["exposure_amount"] == 100.0, "one walk serves the figure and the rows"


def test_a_shared_customers_brief_shows_only_what_the_reader_may_list(office) -> None:
    client, admin, make = office["client"], office["admin"], office["make"]
    customer = make("customers", name="共享客户")["id"]
    alice_emp, bob_emp = make("employees", name="Alice")["id"], make("employees", name="Bob")["id"]
    alice = invite_member(client, admin, "alice", ["order.submit_own", "crm.own"], employee_id=alice_emp)
    bob = invite_member(client, admin, "bob", ["order.submit_own", "crm.own"], employee_id=bob_emp)
    make("sales-orders", headers=alice, employee_id=alice_emp, customer_id=customer, title="alice's order")
    make("opportunities", headers=alice, employee_id=alice_emp, customer_id=customer, title="alice's deal")
    brief = client.get(f"/api/v1/customers/{customer}/detail", headers=bob).json()["data"]
    assert brief["orders"] == [] and brief["opportunities"] == [], "the brief leaked what the lists withhold"
    own = client.get(f"/api/v1/customers/{customer}/detail", headers=alice).json()["data"]
    assert len(own["orders"]) == 1 and len(own["opportunities"]) == 1


def test_a_stale_claim_is_taken_over_only_by_the_same_request(office, monkeypatch) -> None:
    client, admin = office["client"], office["admin"]
    scope = hashlib.sha256(("key:" + admin["X-API-Key"]).encode()).hexdigest()
    with client.session_factory() as db:
        db.add(IdempotencyRecord(scope_hash=scope, key="stale", fingerprint="not-this-request",
                                 method="POST", path="/api/v1/customers"))
        db.commit()
    later = idempotency._now() + idempotency.IN_FLIGHT_GRACE + timedelta(minutes=1)
    monkeypatch.setattr(idempotency, "_now", lambda: later)
    hijack = client.post("/api/v1/customers", json={"name": "x"}, headers={**admin, "Idempotency-Key": "stale"})
    assert hijack.status_code == 422 and hijack.json()["detail"][0]["type"] == "idempotency_key_reused", \
        "a key that named one request never runs another"


def test_a_minted_key_is_completed_but_never_replayed(office) -> None:
    client, admin = office["client"], office["admin"]
    key = str(uuid.uuid4())
    minted = client.post("/api/v1/tenant/api-keys", json={"label": "once"}, headers={**admin, "Idempotency-Key": key})
    assert minted.status_code == 201, minted.text
    assert minted.headers.get("Cache-Control") == "no-store" and minted.headers.get("Idempotency-Replayable") == "false"
    secret = minted.json()["data"]["plain_text_api_key"]
    again = client.post("/api/v1/tenant/api-keys", json={"label": "once"}, headers={**admin, "Idempotency-Key": key})
    assert again.status_code == 409 and again.headers.get("Idempotency-Replayed") == "true"
    assert "not kept for replay" in again.json()["detail"]
    with client.session_factory() as db:
        from sqlalchemy import select
        record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        assert secret not in (record.response_body or ""), "the plaintext key was stored for 24 hours"
        assert record.completed_at is not None
    keys = client.get("/api/v1/tenant/api-keys", headers=admin).json()["data"]
    assert sum(1 for k in keys if k["label"] == "once") == 1, "the write itself still happened once"


def test_duplicate_employee_and_resource_codes_are_refused_in_tests_as_in_production(office) -> None:
    client, admin, make = office["client"], office["admin"], office["make"]
    make("employees", name="甲", employee_code="E-001")
    dup = client.post("/api/v1/employees", json={"name": "乙", "employee_code": "E-001"}, headers=admin)
    assert dup.status_code in (409, 422), dup.text
    make("resources", name="会议室 A", code="R-1", resource_type="room")
    dup = client.post("/api/v1/resources", json={"name": "会议室 B", "code": "R-1", "resource_type": "room"}, headers=admin)
    assert dup.status_code in (409, 422), dup.text


def test_the_shipment_desk_deletes_its_own_shipments() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Freight Co", email="admin@freight.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        product = client.post("/api/v1/products", json={"name": "货"}, headers=admin).json()["data"]["id"]
        desk = invite_member(client, admin, "desk", ["shipment.manage"])
        parcel = client.post("/api/v1/shipments", headers=desk, json={
            "direction": "outbound", "items": [{"product_id": product, "quantity": 1}]})
        assert parcel.status_code == 201, parcel.text
        gone = client.delete(f"/api/v1/shipments/{parcel.json()['data']['id']}", headers=desk)
        assert gone.status_code == 204, "the grant that files a shipment could not delete it"
        warehouse = invite_member(client, admin, "warehouse", ["inventory.manage"])
        again = client.post("/api/v1/shipments", headers=warehouse, json={
            "direction": "outbound", "items": [{"product_id": product, "quantity": 1}]})
        assert again.status_code == 201, "the stock ledger's grant still holds every leg"
