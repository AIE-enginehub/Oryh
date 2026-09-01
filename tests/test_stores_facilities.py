"""Stores and facilities: where the company sells, and where it ships from.

What is pinned: a facility's type comes from the tenant's `facility_type`
vocabulary (unknown values are refused with the options, never bent); the
facility NAME is unique among active rows because the stock ledger joins
on that string; a store's channel is the closed offline/online pair and
its `source` lowercases into the external channels' own join key; the
(store, facility) fulfilment link is one row per pair that revives rather
than forks, listed preferred-first; and a sales order names the front it
came through — nullable, refused onto an archived store, kept by orders
already there.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def town():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Town Co", email="admin@town.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        client.post("/api/v1/roles", json={"name": "nobody", "permissions": []}, headers=admin)
        uid = client.post("/api/v1/auth/invitations",
                          json={"email": "n@town.example", "role": "nobody"},
                          headers=admin).json()["data"]["id"]
        token = next(l.rsplit("token=", 1)[1].strip()
                     for l in outbox.messages[-1].body.splitlines() if "token=" in l)
        client.post("/api/v1/auth/invitations/accept",
                    json={"token": token, "password": "invitee-pass1"})
        member = {"X-API-Key": client.post(
            "/api/v1/tenant/api-keys", json={"label": "nobody", "user_id": uid},
            headers=admin).json()["data"]["plain_text_api_key"]}

        yield {"client": client, "admin": admin, "member": member}


def test_a_facility_is_typed_by_the_vocabulary_and_named_once(town) -> None:
    client, admin = town["client"], town["admin"]
    bent = client.post("/api/v1/facilities", headers=admin, json={
        "name": "主仓", "facility_type": "spaceship"})
    assert bent.status_code == 422
    assert "warehouse" in bent.json()["detail"], "the refusal hands over the options"

    made = client.post("/api/v1/facilities", headers=admin, json={
        "name": "主仓", "facility_type": "warehouse", "facility_code": "FAC-MAIN"})
    assert made.status_code == 201, made.text

    doubled = client.post("/api/v1/facilities", headers=admin, json={
        "name": "主仓", "facility_type": "office"})
    assert doubled.status_code == 409, "the stock ledger joins on the name — one live 主仓"
    client.delete(f"/api/v1/facilities/{made.json()['data']['id']}", headers=admin)
    freed = client.post("/api/v1/facilities", headers=admin, json={
        "name": "主仓", "facility_type": "warehouse"})
    assert freed.status_code == 201, "archiving frees the name — the old row is history"

    listed = client.get("/api/v1/facilities", headers=town["member"],
                        params={"facility_type": "warehouse", "status": "active"})
    assert listed.status_code == 200, "facilities are master data — everyone reads them"
    assert [r["name"] for r in listed.json()["data"]] == ["主仓"]
    refused = client.post("/api/v1/facilities", headers=town["member"],
                          json={"name": "私仓", "facility_type": "warehouse"})
    assert refused.status_code == 403


def test_a_store_names_its_channel_and_its_source_key(town) -> None:
    client, admin = town["client"], town["admin"]
    sideways = client.post("/api/v1/stores", headers=admin, json={
        "name": "天猫旗舰店", "channel": "wechat"})
    assert sideways.status_code == 422, "offline/online is a closed pair"

    online = client.post("/api/v1/stores", headers=admin, json={
        "name": "天猫旗舰店", "channel": "online", "source": "  TMALL "})
    assert online.status_code == 201, online.text
    assert online.json()["data"]["source"] == "tmall", \
        "source lowercases into the external channels' own join key"
    shop = client.post("/api/v1/stores", headers=admin, json={
        "name": "南京西路店", "channel": "offline", "address": "南京西路100号"})
    assert shop.status_code == 201

    by_source = client.get("/api/v1/stores", headers=town["member"],
                           params={"source": "Tmall"})
    assert [r["name"] for r in by_source.json()["data"]] == ["天猫旗舰店"]


def test_the_fulfilment_link_is_the_stores_standing_answer(town) -> None:
    client, admin = town["client"], town["admin"]
    store = client.post("/api/v1/stores", headers=admin, json={
        "name": "天猫旗舰店", "channel": "online", "source": "tmall"}).json()["data"]
    main = client.post("/api/v1/facilities", headers=admin, json={
        "name": "主仓", "facility_type": "warehouse"}).json()["data"]
    backup = client.post("/api/v1/facilities", headers=admin, json={
        "name": "华南仓", "facility_type": "warehouse"}).json()["data"]

    first = client.post("/api/v1/store-facilities", headers=admin, json={
        "store_id": store["id"], "facility_id": backup["id"], "priority": 2})
    assert first.status_code == 201, first.text
    client.post("/api/v1/store-facilities", headers=admin, json={
        "store_id": store["id"], "facility_id": main["id"], "priority": 1})

    doubled = client.post("/api/v1/store-facilities", headers=admin, json={
        "store_id": store["id"], "facility_id": main["id"]})
    assert doubled.status_code == 409, "one row per pair — PATCH it, archived revives"
    assert "PATCH it" in doubled.json()["detail"], \
        "the refusal hands over the existing row, not a bare constraint"

    detail = client.get(f"/api/v1/stores/{store['id']}", headers=town["member"]).json()["data"]
    names = [row["facility_name"] for row in detail["fulfilment_facilities"]]
    assert names == ["主仓", "华南仓"], \
        "the store's read answers who ships for it, preferred first"

    ghost = client.post("/api/v1/store-facilities", headers=admin, json={
        "store_id": store["id"], "facility_id": "00000000-0000-0000-0000-000000000000"})
    assert ghost.status_code == 404


def test_a_sales_order_names_the_front_it_came_through(town) -> None:
    client, admin = town["client"], town["admin"]
    store = client.post("/api/v1/stores", headers=admin, json={
        "name": "天猫旗舰店", "channel": "online", "source": "tmall"}).json()["data"]
    retired = client.post("/api/v1/stores", headers=admin, json={
        "name": "老店", "channel": "offline"}).json()["data"]
    client.delete(f"/api/v1/stores/{retired['id']}", headers=admin)
    emp = client.post("/api/v1/employees", json={"name": "店长"},
                      headers=admin).json()["data"]["id"]

    onto_archived = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "一单", "store_id": retired["id"]})
    assert onto_archived.status_code == 409

    made = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "天猫一单", "store_id": store["id"]})
    assert made.status_code == 201, made.text
    order = made.json()["data"]
    assert order["store_id"] == store["id"] and order["store_name"] == "天猫旗舰店"

    bare = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "无店订单"})
    assert bare.status_code == 201, "an order with no store is a legal fact"

    filtered = client.get("/api/v1/sales-orders", headers=admin,
                          params={"store_id": store["id"]}).json()["data"]
    assert [r["id"] for r in filtered] == [order["id"]]

    # archiving the store strands nothing: the order keeps its pointer
    client.delete(f"/api/v1/stores/{store['id']}", headers=admin)
    kept = client.get(f"/api/v1/sales-orders/{order['id']}", headers=admin).json()["data"]
    assert kept["store_id"] == store["id"]
