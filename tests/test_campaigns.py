"""Campaigns: where leads come from, as facts.

Pinned here: a campaign is marketing's (campaign.manage files and advances,
no owner-own limit) and walks its machine like every family; a member is
exactly one party and cannot be listed twice; a salesperson may put their
own lead on a campaign but not somebody else's; attribution rides the lead
into the opportunity the bridge opens; and the detail counts what the
campaign produced live — leads, conversions, deals, wins — without storing
any of it.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def crm():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Fair Co", email="admin@fair.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def person(name: str, permissions: list[str]) -> dict:
            emp = client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": f"role_{name}", "permissions": permissions}, headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@fair.example", "role": f"role_{name}", "employee_id": emp},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "key": {"X-API-Key": key}}

        yield {"client": client, "admin": admin, "person": person}


def test_a_campaign_is_marketings_and_walks_its_machine(crm) -> None:
    client = crm["client"]
    marketing = crm["person"]("mkt", ["campaign.manage"])
    sales = crm["person"]("zhang", ["crm.own"])

    refused = client.post("/api/v1/campaigns", headers=sales["key"],
                          json={"name": "Shanghai fair", "employee_id": sales["employee_id"]})
    assert refused.status_code == 403, "crm.own does not run campaigns"

    made = client.post("/api/v1/campaigns", headers=marketing["key"], json={
        "name": "Shanghai fair 2026", "employee_id": marketing["employee_id"],
        "campaign_type": "trade_fair", "start_date": "2026-10-12", "end_date": "2026-10-14",
        "budget": 80000,
    })
    assert made.status_code == 201, made.text
    campaign = made.json()["data"]
    assert campaign["campaign_no"].startswith("CMP-") and campaign["status"] == "planned"

    bad_type = client.post("/api/v1/campaigns", headers=marketing["key"],
                           json={"name": "x", "employee_id": marketing["employee_id"], "campaign_type": "carrier_pigeon"})
    assert bad_type.status_code == 422, "campaign_type is one of the workspace's options"
    bad_dates = client.post("/api/v1/campaigns", headers=marketing["key"],
                            json={"name": "x", "employee_id": marketing["employee_id"],
                                  "start_date": "2026-10-14", "end_date": "2026-10-12"})
    assert bad_dates.status_code == 422

    # the machine gates like every family: planned → completed is not a step
    jump = client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=marketing["key"], json={"status": "completed"})
    assert jump.status_code == 409
    live = client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=marketing["key"], json={"status": "active"})
    assert live.status_code == 200 and live.json()["data"]["status"] == "active"
    # marketing is not owner-checked: another campaign.manage holder edits it too
    other = crm["person"]("mkt2", ["campaign.manage"])
    edited = client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=other["key"], json={"actual_cost": 61000})
    assert edited.status_code == 200 and edited.json()["data"]["actual_cost"] == 61000.0
    # everyone reads
    assert client.get(f"/api/v1/campaigns/{campaign['id']}", headers=sales["key"]).status_code == 200
    listed = client.get("/api/v1/campaigns?status=active&campaign_type=trade_fair", headers=sales["key"]).json()["data"]
    assert [c["id"] for c in listed] == [campaign["id"]]


def test_members_are_one_party_each_and_never_twice(crm) -> None:
    client = crm["client"]
    marketing = crm["person"]("mkt", ["campaign.manage"])
    zhang = crm["person"]("zhang", ["crm.own"])
    li = crm["person"]("li", ["crm.own"])
    campaign = client.post("/api/v1/campaigns", headers=marketing["key"],
                           json={"name": "Webinar", "employee_id": marketing["employee_id"]}).json()["data"]
    lead = client.post("/api/v1/leads", headers=zhang["key"],
                       json={"employee_id": zhang["employee_id"], "company_name": "泵业公司"}).json()["data"]
    customer = client.post("/api/v1/customers", headers=crm["admin"], json={"name": "老客户"}).json()["data"]
    contact = client.post("/api/v1/customer-contacts", headers=crm["admin"],
                          json={"customer_id": customer["id"], "name": "王工"}).json()["data"]

    both = client.post("/api/v1/campaign-members", headers=marketing["key"],
                       json={"campaign_id": campaign["id"], "lead_id": lead["id"], "customer_id": customer["id"]})
    assert both.status_code == 422, "a member is a lead OR a customer"
    neither = client.post("/api/v1/campaign-members", headers=marketing["key"], json={"campaign_id": campaign["id"]})
    assert neither.status_code == 422

    # the salesperson may list their own lead; the other salesperson may not
    own = client.post("/api/v1/campaign-members", headers=zhang["key"],
                      json={"campaign_id": campaign["id"], "lead_id": lead["id"], "member_status": "attended"})
    assert own.status_code == 201, own.text
    not_theirs = client.post("/api/v1/campaign-members", headers=li["key"],
                             json={"campaign_id": campaign["id"], "lead_id": lead["id"]})
    assert not_theirs.status_code in (403, 409)
    again = client.post("/api/v1/campaign-members", headers=marketing["key"],
                        json={"campaign_id": campaign["id"], "lead_id": lead["id"]})
    assert again.status_code == 409, "a party is listed once"

    # a customer, then one of its people — two rows, both legal; a stranger's contact is not
    by_customer = client.post("/api/v1/campaign-members", headers=marketing["key"],
                              json={"campaign_id": campaign["id"], "customer_id": customer["id"]})
    assert by_customer.status_code == 201
    by_contact = client.post("/api/v1/campaign-members", headers=marketing["key"],
                             json={"campaign_id": campaign["id"], "customer_id": customer["id"], "contact_id": contact["id"]})
    assert by_contact.status_code == 201
    other_customer = client.post("/api/v1/customers", headers=crm["admin"], json={"name": "别家"}).json()["data"]
    wrong = client.post("/api/v1/campaign-members", headers=marketing["key"],
                        json={"campaign_id": campaign["id"], "customer_id": other_customer["id"], "contact_id": contact["id"]})
    assert wrong.status_code == 422

    bad_status = client.patch(f"/api/v1/campaign-members/{own.json()['data']['id']}", headers=marketing["key"],
                              json={"member_status": "ghosted"})
    assert bad_status.status_code == 422
    members = client.get(f"/api/v1/campaign-members?campaign_id={campaign['id']}&page=1&size=10",
                         headers=zhang["key"]).json()
    assert members["meta"]["total"] == 3


def test_attribution_rides_the_lead_into_the_deal_and_the_detail_counts_live(crm) -> None:
    client = crm["client"]
    marketing = crm["person"]("mkt", ["campaign.manage"])
    zhang = crm["person"]("zhang", ["crm.own"])
    campaign = client.post("/api/v1/campaigns", headers=marketing["key"],
                           json={"name": "Fair", "employee_id": marketing["employee_id"]}).json()["data"]

    ghost = client.post("/api/v1/leads", headers=zhang["key"],
                        json={"employee_id": zhang["employee_id"], "company_name": "x",
                              "campaign_id": "00000000-0000-0000-0000-000000000000"})
    assert ghost.status_code == 404, "attribution names a real campaign"

    leads = []
    for name in ("甲", "乙", "丙"):
        made = client.post("/api/v1/leads", headers=zhang["key"],
                           json={"employee_id": zhang["employee_id"], "company_name": name,
                                 "source": "trade-fair", "campaign_id": campaign["id"]})
        assert made.status_code == 201, made.text
        leads.append(made.json()["data"])
    assert all(l["campaign_id"] == campaign["id"] for l in leads)
    assert client.get(f"/api/v1/leads?campaign_id={campaign['id']}", headers=zhang["key"]).json()["meta"]["total"] == 3 or \
        len(client.get(f"/api/v1/leads?campaign_id={campaign['id']}", headers=zhang["key"]).json()["data"]) == 3

    # qualify and convert one: the deal inherits the campaign
    client.patch(f"/api/v1/leads/{leads[0]['id']}", headers=zhang["key"], json={"status": "qualified"})
    converted = client.post(f"/api/v1/leads/{leads[0]['id']}/convert", headers=zhang["key"],
                            json={"opportunity_title": "甲的项目", "expected_amount": 120000})
    assert converted.status_code in (200, 201), converted.text
    deal = client.get(f"/api/v1/opportunities?lead_id={leads[0]['id']}", headers=zhang["key"]).json()["data"][0]
    assert deal["campaign_id"] == campaign["id"]
    won = client.patch(f"/api/v1/opportunities/{deal['id']}", headers=zhang["key"], json={"status": "won"})
    assert won.status_code == 200

    # a deal with no lead names the campaign directly
    direct = client.post("/api/v1/opportunities", headers=zhang["key"],
                         json={"employee_id": zhang["employee_id"], "title": "路过的", "campaign_id": campaign["id"],
                               "customer_name_snapshot": "丁", "expected_amount": 5000})
    assert direct.status_code == 201, direct.text

    detail = client.get(f"/api/v1/campaigns/{campaign['id']}/detail", headers=zhang["key"])
    assert detail.status_code == 200, detail.text
    facts = detail.json()["data"]
    assert facts["leads_total"] == 3 and facts["leads_converted"] == 1
    assert facts["opportunities_total"] == 2 and facts["opportunities_won"] == 1
    assert facts["won_expected_amount"] == 120000.0
    assert facts["members_total"] == 0 and facts["members_by_status"] == {}
