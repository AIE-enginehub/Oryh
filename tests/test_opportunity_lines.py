"""A deal's lines, its cast, its close details, and the quote bridge.

Pinned: lines and cast belong to the deal's owner; a line names a product;
the cast is the customer's own people with one primary; close details are
the salesperson's facts (probability, lost_reason from the options,
competitor); the bridge turns the lines into a quotation draft priced with a
stated basis per line, moves the deal to quoting, and the order raised from
that quotation inherits the deal — so the detail shows where the money went.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def deal():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Deal Co", email="admin@deal.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def person(name: str, permissions: list[str]) -> dict:
            emp = client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": f"role_{name}", "permissions": permissions}, headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@deal.example", "role": f"role_{name}", "employee_id": emp},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "key": {"X-API-Key": key}}

        customer = client.post("/api/v1/customers", json={"name": "市一医院"}, headers=admin).json()["data"]
        contact = client.post("/api/v1/customer-contacts", headers=admin,
                              json={"customer_id": customer["id"], "name": "王主任", "phone": "13900000001", "title": "设备科主任"}).json()["data"]
        product = client.post("/api/v1/products", headers=admin,
                              json={"name": "监护仪", "product_code": "MON-1", "list_price": 12000}).json()["data"]
        client.post("/api/v1/customer-products", headers=admin,
                    json={"customer_id": customer["id"], "product_id": product["id"], "agreed_price": 11000})
        yield {"client": client, "admin": admin, "person": person, "customer": customer, "contact": contact, "product": product}


def test_lines_and_cast_are_the_owners_and_the_close_details_are_facts(deal) -> None:
    client = deal["client"]
    zhang = deal["person"]("zhang", ["crm.own", "quotation.submit_own"])
    li = deal["person"]("li", ["crm.own"])
    opp = client.post("/api/v1/opportunities", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "title": "监护仪 20 台", "customer_id": deal["customer"]["id"],
        "expected_amount": 240000, "probability": 40, "source": "referral",
    }).json()["data"]
    assert opp["probability"] == 40 and opp["source"] == "referral"

    nameless = client.post("/api/v1/opportunity-items", headers=zhang["key"],
                           json={"opportunity_id": opp["id"], "quantity": 20})
    assert nameless.status_code == 422, "a line names a product"
    line = client.post("/api/v1/opportunity-items", headers=zhang["key"],
                       json={"opportunity_id": opp["id"], "product_id": deal["product"]["id"], "quantity": 20})
    assert line.status_code == 201, line.text
    assert line.json()["data"]["amount"] is None, "no price stated, no amount invented"
    free = client.post("/api/v1/opportunity-items", headers=zhang["key"],
                       json={"opportunity_id": opp["id"], "product_name_snapshot": "安装培训", "quantity": 1, "unit_price": 3000})
    assert free.status_code == 201 and free.json()["data"]["amount"] == 3000.0
    stranger = client.post("/api/v1/opportunity-items", headers=li["key"],
                           json={"opportunity_id": opp["id"], "product_name_snapshot": "x", "quantity": 1})
    assert stranger.status_code == 403, "my deal's lines are mine"

    # the cast: the customer's own people, one primary
    other_customer = client.post("/api/v1/customers", json={"name": "别家"}, headers=deal["admin"]).json()["data"]
    outsider = client.post("/api/v1/customer-contacts", headers=deal["admin"],
                           json={"customer_id": other_customer["id"], "name": "路人"}).json()["data"]
    wrong = client.post("/api/v1/opportunity-contacts", headers=zhang["key"],
                        json={"opportunity_id": opp["id"], "contact_id": outsider["id"], "role": "decision_maker"})
    assert wrong.status_code == 422
    bad_role = client.post("/api/v1/opportunity-contacts", headers=zhang["key"],
                           json={"opportunity_id": opp["id"], "contact_id": deal["contact"]["id"], "role": "mascot"})
    assert bad_role.status_code == 422
    cast = client.post("/api/v1/opportunity-contacts", headers=zhang["key"],
                       json={"opportunity_id": opp["id"], "contact_id": deal["contact"]["id"], "role": "decision_maker", "is_primary": True})
    assert cast.status_code == 201, cast.text
    twice = client.post("/api/v1/opportunity-contacts", headers=zhang["key"],
                        json={"opportunity_id": opp["id"], "contact_id": deal["contact"]["id"], "role": "champion"})
    assert twice.status_code == 409

    # close details: lost_reason from the options; a reason on a live deal is still the person's fact
    assert client.patch(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"],
                        json={"lost_reason": "vibes"}).status_code == 422
    lost = client.patch(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"],
                        json={"status": "lost", "lost_reason": "competitor", "competitor": "迈瑞", "probability": 0})
    assert lost.status_code == 200, lost.text
    assert lost.json()["data"]["lost_reason"] == "competitor" and lost.json()["data"]["closed_at"]
    # lost freezes the lines, not the cast
    assert client.post("/api/v1/opportunity-items", headers=zhang["key"],
                       json={"opportunity_id": opp["id"], "product_name_snapshot": "late", "quantity": 1}).status_code == 409
    assert client.patch(f"/api/v1/opportunity-contacts/{cast.json()['data']['id']}", headers=zhang["key"],
                        json={"role": "influencer"}).status_code == 200


def test_the_quote_bridge_prices_each_line_with_a_basis_and_the_order_inherits_the_deal(deal) -> None:
    client = deal["client"]
    zhang = deal["person"]("zhang", ["crm.own", "quotation.submit_own", "order.submit_own"])
    opp = client.post("/api/v1/opportunities", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "title": "监护仪 20 台", "customer_id": deal["customer"]["id"],
    }).json()["data"]
    empty = client.post(f"/api/v1/opportunities/{opp['id']}/quote", headers=zhang["key"], json={})
    assert empty.status_code == 422, "nothing to quote yet"

    client.post("/api/v1/opportunity-items", headers=zhang["key"],
                json={"opportunity_id": opp["id"], "product_id": deal["product"]["id"], "quantity": 20})
    client.post("/api/v1/opportunity-items", headers=zhang["key"],
                json={"opportunity_id": opp["id"], "product_name_snapshot": "安装培训", "quantity": 1, "unit_price": 3000})
    client.post("/api/v1/opportunity-items", headers=zhang["key"],
                json={"opportunity_id": opp["id"], "product_name_snapshot": "未定价的服务", "quantity": 2})
    client.post("/api/v1/opportunity-contacts", headers=zhang["key"],
                json={"opportunity_id": opp["id"], "contact_id": deal["contact"]["id"], "role": "decision_maker", "is_primary": True})

    quoted = client.post(f"/api/v1/opportunities/{opp['id']}/quote", headers=zhang["key"],
                         json={"valid_until": "2026-12-31"})
    assert quoted.status_code == 201, quoted.text
    quotation = quoted.json()["data"]
    assert quotation["opportunity_id"] == opp["id"] and quotation["status"] == "draft"
    assert quotation["contact_name"] == "王主任" and quotation["contact_phone"] == "13900000001"
    bases = {i["product_name_snapshot"] or i["product_id"]: (i["unit_price"], i["price_basis"]) for i in quotation["items"]}
    assert bases["安装培训"] == (3000.0, "opportunity_line")
    assert bases["未定价的服务"] == (None, "unpriced")
    priced = next(v for k, v in bases.items() if k == deal["product"]["id"] or k == "监护仪")
    assert priced == (11000.0, "customer_agreement"), "the customer's agreed price beats the catalog's 12000"
    catalog = next(i for i in quotation["items"] if i["product_id"] == deal["product"]["id"])
    assert catalog["list_price_snapshot"] == 12000.0

    moved = client.get(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"]).json()["data"]
    assert moved["status"] == "quoting"

    # an order raised from that quotation carries the deal without being told
    order = client.post("/api/v1/sales-orders", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "title": "监护仪订单", "quotation_id": quotation["id"],
        "customer_id": deal["customer"]["id"],
    })
    assert order.status_code == 201, order.text
    assert order.json()["data"]["opportunity_id"] == opp["id"]

    detail = client.get(f"/api/v1/opportunities/{opp['id']}/detail", headers=zhang["key"]).json()["data"]
    assert len(detail["items"]) == 3
    assert detail["contacts"][0]["contact_name"] == "王主任" and detail["contacts"][0]["is_primary"] is True
    assert [q["id"] for q in detail["quotations"]] == [quotation["id"]]
    assert [o["id"] for o in detail["orders"]] == [order.json()["data"]["id"]]
    listed = client.get(f"/api/v1/sales-orders?opportunity_id={opp['id']}", headers=zhang["key"]).json()["data"]
    assert len(listed) == 1
