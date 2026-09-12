"""Fixes from the sales-loop simulation (docs/sales-loop-agent-simulation-2026-09-10.zh.md).

Each test names the finding it closes: a line's amount follows a price
change (F-28); a person may give themselves a todo and a second next step
updates the open one (F-17); a confirmed order's content is closed while its
fulfilment facts stay open (F-05, F-65); conversion into an existing
customer keeps the lead's person and carries the record of contact to the
customer (F-03, F-15, F-23); the bridge names products, keeps notes private
and does not walk a negotiating deal backwards (F-07, F-29, F-04); an order
inherits the quotation's terms (F-48); the account's owner adds its people
(F-09); the queue shows the deal's effective amount (F-60, F-61); the
quotation detail carries the superseded revisions' approval facts (F-38);
the customer's detail is one read (F-16); the template speaks six digits
(F-11); the bundle's connect carries both URLs (F-02).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Loop Co", email="admin@loop.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def person(name: str, permissions: list[str]) -> dict:
            emp = client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": f"role_{name}", "permissions": permissions}, headers=admin)
            uid = client.post("/api/v1/auth/invitations", headers=admin,
                              json={"email": f"{name}@loop.example", "role": f"role_{name}", "employee_id": emp}).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip() for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "user_id": uid, "key": {"X-API-Key": key}}

        product = client.post("/api/v1/products", headers=admin,
                              json={"name": "JC-800", "product_code": "JC-800", "list_price": 128000}).json()["data"]
        yield {"client": client, "admin": admin, "person": person, "product": product}


def test_f28_a_lines_amount_follows_the_price(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["crm.own", "quotation.submit_own"])
    q = client.post("/api/v1/sales-quotations", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "title": "q", "customer_name_snapshot": "c",
        "items": [{"product_id": shop["product"]["id"], "quantity": 2, "unit_price": 128000, "amount": 256000}],
    }).json()["data"]
    item = client.get(f"/api/v1/sales-quotation-items?quotation_id={q['id']}", headers=rep["key"]).json()["data"][0]
    changed = client.patch(f"/api/v1/sales-quotation-items/{item['id']}", headers=rep["key"], json={"unit_price": 121600})
    assert changed.status_code == 200, changed.text
    detail = client.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=rep["key"]).json()["data"]
    assert detail["computed_total"] == 243200.0, "the stored 256000 was stale the moment the price changed"
    gift = client.patch(f"/api/v1/sales-quotation-items/{item['id']}", headers=rep["key"], json={"is_gift": True, "unit_price": 0})
    assert gift.status_code == 200
    detail = client.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=rep["key"]).json()["data"]
    assert detail["computed_total"] == 0.0


def test_f17_a_person_gives_themselves_a_todo_and_two_next_steps_are_two(shop) -> None:
    client = shop["client"]
    rep = shop["person"]("rep", ["crm.own", "todos.complete_own"])
    other = shop["person"]("other", ["crm.own"])
    lead = client.post("/api/v1/leads", headers=rep["key"],
                       json={"employee_id": rep["employee_id"], "company_name": "x"}).json()["data"]
    mine = client.post("/api/v1/todos", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "entity_type": "lead", "entity_id": lead["id"], "title": "发报价"})
    assert mine.status_code == 201, mine.text
    second = client.post("/api/v1/todos", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "entity_type": "lead", "entity_id": lead["id"], "title": "约拜访"})
    assert second.status_code == 409 and mine.json()["data"]["id"] in second.json()["detail"], \
        "one open todo per person per record; the refusal names it so the caller updates it"
    updated = client.patch(f"/api/v1/todos/{mine.json()['data']['id']}", headers=rep["key"], json={"title": "约拜访"})
    assert updated.status_code == 200, updated.text
    same = client.post("/api/v1/todos", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "entity_type": "lead", "entity_id": lead["id"], "title": "约拜访"})
    assert same.status_code in (200, 201) and same.json()["data"]["id"] == mine.json()["data"]["id"], "the same assignment twice is one todo"
    theirs = client.post("/api/v1/todos", headers=rep["key"], json={
        "employee_id": other["employee_id"], "entity_type": "lead", "entity_id": lead["id"], "title": "x"})
    assert theirs.status_code == 403, "assigning to someone else is todos.assign"


def test_f05_f65_a_confirmed_orders_content_is_closed_but_its_facts_stay_open(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["order.submit_own"])
    order = client.post("/api/v1/sales-orders", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "title": "o", "contract_no": "JH-1", "total_amount": 100,
        "items": [{"product_name_snapshot": "x", "quantity": 1, "unit_price": 100}],
    }).json()["data"]
    client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=rep["key"])
    client.patch(f"/api/v1/sales-orders/{order['id']}", json={"status": "confirmed"}, headers=admin)
    closed = client.patch(f"/api/v1/sales-orders/{order['id']}", headers=rep["key"], json={"contract_no": "JH-2"})
    assert closed.status_code == 409, "the content of a confirmed order is closed to the rep"
    assert client.patch(f"/api/v1/sales-orders/{order['id']}", headers=rep["key"], json={"total_amount": 1}).status_code == 409
    facts = client.patch(f"/api/v1/sales-orders/{order['id']}", headers=rep["key"], json={
        "logistics_company": "SF", "logistics_tracking_no": "SF1", "shipped_at": "2026-09-21T02:00:00Z", "remarks": "left"})
    assert facts.status_code == 200, facts.text
    assert facts.json()["data"]["shipped_at"].startswith("2026-09-21")
    shipped = client.patch(f"/api/v1/sales-orders/{order['id']}", json={"status": "shipped"}, headers=admin).json()["data"]
    assert shipped["shipped_at"].startswith("2026-09-21"), "the stamp does not overwrite the stated moment"


def test_f03_f15_f23_conversion_into_an_existing_customer_keeps_the_person_and_the_history(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["crm.own"])
    existing = client.post("/api/v1/customers", json={"name": "回归客户"}, headers=admin).json()["data"]
    lead = client.post("/api/v1/leads", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "company_name": "回归客户", "contact_name": "刘建华",
        "phone": "13800000001", "source": "trade_fair"}).json()["data"]
    client.post("/api/v1/activities", headers=rep["key"], json={
        "lead_id": lead["id"], "activity_type": "call", "occurred_at": "2026-09-05T02:00:00Z", "subject": "展会聊过"})
    client.post("/api/v1/communication-events", headers=rep["key"], json={
        "lead_id": lead["id"], "channel": "wechat", "direction": "inbound", "occurred_at": "2026-09-05T03:00:00Z", "subject": "微信"})
    client.patch(f"/api/v1/leads/{lead['id']}", headers=rep["key"], json={"status": "qualified"})
    converted = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=rep["key"],
                            json={"customer_id": existing["id"], "opportunity_title": "更新"})
    assert converted.status_code in (200, 201), converted.text
    body = converted.json()["data"]
    assert body["contact"]["name"] == "刘建华" and body["contact"]["customer_id"] == existing["id"]
    assert body["opportunity"]["source"] == "trade_fair"
    contacts = client.get(f"/api/v1/customer-contacts?customer_id={existing['id']}", headers=admin).json()["data"]
    assert [c["name"] for c in contacts] == ["刘建华"]
    activities = client.get(f"/api/v1/activities?customer_id={existing['id']}", headers=rep["key"]).json()["data"]
    assert len(activities) == 1 and activities[0]["opportunity_id"] == body["opportunity"]["id"]
    mails = client.get(f"/api/v1/communication-events?customer_id={existing['id']}", headers=rep["key"]).json()["data"]
    assert len(mails) == 1
    # a second conversion of a lead naming the same person does not duplicate them
    again = client.post("/api/v1/leads", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "company_name": "回归客户", "contact_name": "刘建华", "phone": "13800000001"}).json()["data"]
    client.patch(f"/api/v1/leads/{again['id']}", headers=rep["key"], json={"status": "qualified"})
    client.post(f"/api/v1/leads/{again['id']}/convert", headers=rep["key"], json={"customer_id": existing["id"]})
    assert len(client.get(f"/api/v1/customer-contacts?customer_id={existing['id']}", headers=admin).json()["data"]) == 1


def test_f07_f29_f04_f48_the_bridge_names_products_keeps_notes_and_the_order_inherits_terms(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["crm.own", "quotation.submit_own", "order.submit_own"])
    customer = client.post("/api/v1/customers", json={"name": "医院"}, headers=admin).json()["data"]
    deal = client.post("/api/v1/opportunities", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "title": "d", "customer_id": customer["id"]}).json()["data"]
    line = client.post("/api/v1/opportunity-items", headers=rep["key"], json={
        "opportunity_id": deal["id"], "product_id": shop["product"]["id"], "quantity": 2, "notes": "价格未谈"}).json()["data"]
    assert line["product_name_snapshot"] == "JC-800", "F-07: the catalog's name rides the line"
    client.patch(f"/api/v1/opportunities/{deal['id']}", headers=rep["key"], json={"status": "negotiating"})
    quoted = client.post(f"/api/v1/opportunities/{deal['id']}/quote", headers=rep["key"],
                         json={"payment_terms": "月结 30 天", "delivery_terms": "含安装"})
    assert quoted.status_code == 201, "F-04: a negotiating deal still quotes"
    assert client.get(f"/api/v1/opportunities/{deal['id']}", headers=rep["key"]).json()["data"]["status"] == "negotiating"
    q = quoted.json()["data"]
    assert q["items"][0]["product_name_snapshot"] == "JC-800" and not q["items"][0].get("notes"), "F-29: internal notes stay off the quotation"
    order = client.post("/api/v1/sales-orders", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "title": "o", "quotation_id": q["id"], "customer_id": customer["id"]})
    assert order.status_code == 201, order.text
    assert order.json()["data"]["payment_terms"] == "月结 30 天" and order.json()["data"]["delivery_terms"] == "含安装", "F-48"


def test_f09_the_accounts_owner_adds_its_people(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["crm.own"])
    other = shop["person"]("other", ["crm.own"])
    mine = client.post("/api/v1/customers", json={"name": "我的客户", "owner_employee_id": rep["employee_id"]}, headers=admin).json()["data"]
    ok = client.post("/api/v1/customer-contacts", headers=rep["key"], json={"customer_id": mine["id"], "name": "陈卫东"})
    assert ok.status_code == 201, ok.text
    assert client.post("/api/v1/customer-contacts", headers=other["key"], json={"customer_id": mine["id"], "name": "x"}).status_code == 403
    found = client.get("/api/v1/customer-contacts?keyword=0573", headers=admin)
    client.post("/api/v1/customer-contacts", headers=admin, json={"customer_id": mine["id"], "name": "电话人", "phone": "0573-8800 1234"})
    found = client.get("/api/v1/customer-contacts?keyword=0573", headers=admin).json()["data"]
    assert [c["name"] for c in found] == ["电话人"], "F-25: the phone is searchable"


def test_f60_f61_f38_the_queue_shows_the_effective_amount_and_the_detail_keeps_prior_conditions(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["quotation.submit_own", "todos.complete_own"])
    q = client.post("/api/v1/sales-quotations", headers=rep["key"], json={
        "employee_id": rep["employee_id"], "title": "QT-x already numbered", "customer_name_snapshot": "c",
        "items": [{"product_id": shop["product"]["id"], "quantity": 2, "unit_price": 121600}],
    }).json()["data"]
    client.post("/api/v1/sales-quotation-adjustments", headers=rep["key"],
                json={"quotation_id": q["id"], "adjustment_type": "discount", "amount": -3200})
    todo = client.post("/api/v1/todos", headers=admin, json={
        "employee_id": rep["employee_id"], "entity_type": "sales_quotation", "entity_id": q["id"], "title": q["quote_number"] + " 审批"})
    assert todo.status_code == 201
    listed = client.get(f"/api/v1/todos?employee_id={rep['employee_id']}&status=open&include=target", headers=admin).json()["data"]
    target = listed[0]["target"]
    assert target["amount"] == 240000.0, "F-60: lines plus adjustments when the header declares nothing"
    assert target["title"].count(q["quote_number"]) == 1, "F-61"

    client.post(f"/api/v1/sales-quotations/{q['id']}/submit", json={}, headers=rep["key"])
    decided = client.post("/api/v1/approval-records", headers=admin, json={
        "entity_type": "sales_quotation", "entity_id": q["id"], "round_no": 1, "sequence_no": 2,
        "action": "approved", "comment": "售后 4 小时响应要写进合同"})
    assert decided.status_code in (200, 201), decided.text
    client.patch(f"/api/v1/sales-quotations/{q['id']}", json={"status": "approved"}, headers=admin)
    client.post(f"/api/v1/sales-quotations/{q['id']}/send", json={"sent_at": "2026-09-12T01:00:00Z"}, headers=rep["key"])
    assert client.get(f"/api/v1/sales-quotations/{q['id']}", headers=admin).json()["data"]["sent_at"].startswith("2026-09-12"), "F-43"
    v2 = client.post(f"/api/v1/sales-quotations/{q['id']}/revise", json={"reason": "客户要求降价"}, headers=rep["key"]).json()["data"]
    detail = client.get(f"/api/v1/sales-quotations/{v2['id']}/detail", headers=rep["key"]).json()["data"]
    assert [r["comment"] for r in detail["prior_approval_records"] if r["action"] == "approved"] == ["售后 4 小时响应要写进合同"], "F-38"
    assert detail["approval_records"] == [], "the new revision's own trail starts empty"


def test_f16_the_customers_detail_is_one_read(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rep = shop["person"]("rep", ["crm.own"])
    customer = client.post("/api/v1/customers", json={"name": "医院", "owner_employee_id": rep["employee_id"]}, headers=admin).json()["data"]
    client.post("/api/v1/customer-contacts", headers=rep["key"], json={"customer_id": customer["id"], "name": "刘"})
    client.post("/api/v1/opportunities", headers=rep["key"], json={"employee_id": rep["employee_id"], "title": "d", "customer_id": customer["id"]})
    client.post("/api/v1/activities", headers=rep["key"], json={
        "customer_id": customer["id"], "activity_type": "visit", "occurred_at": "2026-09-05T02:00:00Z", "subject": "拜访"})
    detail = client.get(f"/api/v1/customers/{customer['id']}/detail", headers=rep["key"])
    assert detail.status_code == 200, detail.text
    facts = detail.json()["data"]
    assert [c["name"] for c in facts["contacts"]] == ["刘"] and len(facts["opportunities"]) == 1 and len(facts["activities"]) == 1


def test_f11_f02_six_digit_codes_and_a_connect_that_knows_the_api(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    client.post("/api/v1/geos/seed-template", headers=admin, json={"template": "cn_provinces"})
    zhejiang = client.get("/api/v1/geos?geo_code=330000", headers=admin).json()["data"]
    assert len(zhejiang) == 1 and zhejiang[0]["name"] in ("浙江省", "Zhejiang")
    rep = shop["person"]("rep", ["crm.own"])
    bundle = client.post(f"/api/v1/users/{rep['user_id']}/skill-bundle", headers=admin)
    assert bundle.status_code == 200, bundle.text
    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    connect = next(n for n in archive.namelist() if n.endswith("connect/SKILL.md"))
    text = archive.read(connect).decode("utf-8")
    assert "{{ORYH_API_BASE_URL}}" not in text, "F-02"
