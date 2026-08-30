"""The sales pipeline: leads, opportunities, and the conversion bridge.

Two personal document families under one approval-free grant (`crm.own`
files AND advances your own). What is pinned here: the machine gates the
pipeline like every family (illegal jumps 409, terminal states freeze
fields, a dead lead revives by status); conversion happens ONLY through
the bridge, which creates the Customer, carries the lead's person into
the rolodex and opens the Opportunity in one transaction — a bare status
write to `converted` is refused because it would lose WHICH customer;
`closed_at` stamps on the literal won/lost; and the member-own boundary
holds — my pipeline is mine to work, everyone's to read.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def pipeline():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Pipe Co", email="admin@pipe.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def salesperson(name: str) -> dict:
            emp = client.post("/api/v1/employees", json={"name": name},
                              headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": f"sales_{name}",
                                               "permissions": ["crm.own"]}, headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@pipe.example", "role": f"sales_{name}",
                                    "employee_id": emp},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys",
                              json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "key": {"X-API-Key": key}}

        yield {"client": client, "admin": admin, "salesperson": salesperson}


def test_a_lead_walks_its_machine_and_stays_its_owners(pipeline) -> None:
    client = pipeline["client"]
    zhang = pipeline["salesperson"]("zhang")
    li = pipeline["salesperson"]("li")

    nobody = client.post("/api/v1/leads", headers=zhang["key"],
                         json={"employee_id": zhang["employee_id"], "phone": "13800000000"})
    assert nobody.status_code == 422, "a lead names SOMEBODY — a company or a person"

    made = client.post("/api/v1/leads", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "company_name": "泵业公司",
        "contact_name": "刘工", "phone": "13800000000", "source": "展会"})
    assert made.status_code == 201, made.text
    lead = made.json()["data"]
    assert lead["lead_no"].startswith("LD-") and lead["status"] == "new"

    qualified = client.patch(f"/api/v1/leads/{lead['id']}", headers=zhang["key"],
                             json={"status": "qualified"})
    assert qualified.status_code == 200
    # from qualified the MACHINE would allow converted — the refusal below is
    # the bridge guard itself, not a transition error
    jumped = client.patch(f"/api/v1/leads/{lead['id']}", headers=zhang["key"],
                          json={"status": "converted"})
    assert jumped.status_code == 409, "converted is the bridge's write, never a bare status"
    dropped = client.patch(f"/api/v1/leads/{lead['id']}", headers=zhang["key"],
                           json={"status": "disqualified", "remarks": "没预算"})
    assert dropped.status_code == 200
    revived = client.patch(f"/api/v1/leads/{lead['id']}", headers=zhang["key"],
                           json={"status": "contacted"})
    assert revived.status_code == 200, "a dead lead may come back to life"
    frozen = client.patch(f"/api/v1/leads/{lead['id']}", headers=zhang["key"],
                          json={"status": "new"})
    assert frozen.status_code == 409, "the machine allows no way back to new"

    stolen = client.patch(f"/api/v1/leads/{lead['id']}", headers=li["key"],
                          json={"remarks": "我的了"})
    assert stolen.status_code == 403, "my pipeline is mine to work"
    everyone = client.get("/api/v1/leads", headers=li["key"],
                          params={"employee_id": zhang["employee_id"]})
    assert everyone.status_code == 200 and len(everyone.json()["data"]) == 1, \
        "…and everyone's to read"


def test_the_bridge_converts_in_one_transaction(pipeline) -> None:
    client = pipeline["client"]
    zhang = pipeline["salesperson"]("zhang")
    lead = client.post("/api/v1/leads", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "company_name": "泵业公司",
        "contact_name": "刘工", "phone": "13800000000", "wechat": "liu-gong",
        "status": "qualified"}).json()["data"]

    converted = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=zhang["key"],
                            json={"opportunity_title": "泵站改造",
                                  "expected_amount": 200000})
    assert converted.status_code == 200, converted.text
    data = converted.json()["data"]
    assert data["lead"]["status"] == "converted"
    assert data["customer"]["name"] == "泵业公司"
    assert data["lead"]["converted_customer_id"] == data["customer"]["id"]
    assert data["contact"]["name"] == "刘工" and data["contact"]["is_primary"], \
        "the lead's person lands in the rolodex"
    assert data["contact"]["phone"] == "13800000000"
    opp = data["opportunity"]
    assert opp["opportunity_no"].startswith("OPP-") and opp["status"] == "open"
    assert opp["lead_id"] == lead["id"] and opp["customer_id"] == data["customer"]["id"]

    again = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=zhang["key"], json={})
    assert again.status_code == 409
    assert data["customer"]["id"] in again.json()["detail"], \
        "a second convert points at the customer it already became"


def test_the_bridge_respects_the_machine_and_master_data(pipeline) -> None:
    client, admin = pipeline["client"], pipeline["admin"]
    zhang = pipeline["salesperson"]("zhang")
    fresh = client.post("/api/v1/leads", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "contact_name": "王姐"}).json()["data"]
    early = client.post(f"/api/v1/leads/{fresh['id']}/convert", headers=zhang["key"], json={})
    assert early.status_code == 409, "new → converted is not a legal transition: qualify first"

    existing = client.post("/api/v1/customers", json={"name": "老客户"},
                           headers=admin).json()["data"]["id"]
    client.patch(f"/api/v1/leads/{fresh['id']}", headers=zhang["key"],
                 json={"status": "qualified"})
    attached = client.post(f"/api/v1/leads/{fresh['id']}/convert", headers=zhang["key"],
                           json={"customer_id": existing})
    assert attached.status_code == 200
    body = attached.json()["data"]
    assert body["customer"]["id"] == existing and "contact" not in body, \
        "naming an existing customer attaches — the rolodex is not force-fed"


def test_an_opportunity_closes_with_a_stamp_and_freezes(pipeline) -> None:
    client = pipeline["client"]
    zhang = pipeline["salesperson"]("zhang")
    opp = client.post("/api/v1/opportunities", headers=zhang["key"], json={
        "employee_id": zhang["employee_id"], "title": "泵站改造",
        "customer_name_snapshot": "泵业公司", "expected_amount": 200000}).json()["data"]
    assert opp["closed_at"] is None

    won = client.patch(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"],
                       json={"status": "won"})
    assert won.status_code == 200
    assert won.json()["data"]["closed_at"] is not None, \
        "won stamps closed_at — 'how long do deals take' must answer honestly"

    frozen = client.patch(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"],
                          json={"expected_amount": 999999})
    assert frozen.status_code == 409, "a closed deal's record is history, not a scratchpad"
    reopened = client.patch(f"/api/v1/opportunities/{opp['id']}", headers=zhang["key"],
                            json={"status": "open"})
    assert reopened.status_code == 409, "a lost/won deal that comes back is a NEW opportunity"
