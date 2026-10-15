"""A deal's parties, a project's provenance, relations between customers
(plan docs/plans/deal-parties-and-project-links-2026-10-14.zh.md).

The case: a friend in the US introduces a bus company's driver-dispatch
project, signs with them, and subcontracts to us. The friend is the
customer; the bus company is a party; the friend is also the referrer with a
share; the won deal becomes a project that knows all of it; the contract
references the friend's own agreement with the bus company without being it.
"""

from __future__ import annotations

import pytest

from conftest import create, invite_member, make_stack, provision_tenant


@pytest.fixture()
def deal():
    with make_stack([]) as (client, engine):
        t = provision_tenant(client, company_name="Referral Co", email="admin@referral.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        sales = invite_member(client, admin, "sales", ["crm.own", "quotation.submit_own", "project.manage"], employee="zhang")
        friend = create(client, admin, "customers", name="X (friend)", customer_kind="person", customer_type="affiliate")
        friend_contact = create(client, admin, "customer-contacts", customer_id=friend["id"], name="X", is_primary=True)
        bus = create(client, admin, "customers", name="Metro Bus Co", customer_kind="company", customer_type="enterprise")
        bus_contact = create(client, admin, "customer-contacts", customer_id=bus["id"], name="Ops director", is_primary=True)
        yield {
            "client": client, "admin": admin, "sales": dict(sales), "sales_employee": sales.employee_id,
            "friend": friend, "friend_contact": friend_contact, "bus": bus, "bus_contact": bus_contact,
        }


def _opportunity(d, **extra):
    c, s = d["client"], d["sales"]
    return create(c, s, "opportunities", employee_id=d["sales_employee"], title="Driver dispatch system (US, via X)",
                  customer_id=d["friend"]["id"], expected_amount=80000, currency="USD", **extra)


def test_the_parties_to_a_deal_beyond_its_customer(deal) -> None:
    c, s, admin = deal["client"], deal["sales"], deal["admin"]
    opp = _opportunity(deal)
    end_client = c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["bus"]["id"],
        "party_role": "end_client", "contact_id": deal["bus_contact"]["id"]})
    assert end_client.status_code == 201, end_client.text
    referrer = c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["friend"]["id"],
        "party_role": "referrer", "terms": {"commission_pct": 10, "trigger": "on_receipt"}})
    assert referrer.status_code == 201, referrer.text
    # the contracting party is the deal's customer, derived — never a row
    filed = c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["friend"]["id"], "party_role": "contracting"})
    assert filed.status_code == 422 and "carrier's customer_id" in filed.text
    wrong_person = c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["bus"]["id"],
        "party_role": "consultant", "contact_id": deal["friend_contact"]["id"]})
    assert wrong_person.status_code == 422, "a party's contact belongs to that party"
    twice = c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["bus"]["id"], "party_role": "end_client"})
    assert twice.status_code == 409
    detail = c.get(f"/api/v1/opportunities/{opp['id']}/detail", headers=s).json()["data"]
    roles = [(p["party_role"], p["customer_name"], p["derived"]) for p in detail["parties"]]
    assert roles == [("contracting", "X (friend)", True), ("end_client", "Metro Bus Co", False), ("referrer", "X (friend)", False)]
    assert detail["parties"][2]["terms"] == {"commission_pct": 10, "trigger": "on_receipt"}
    # the cast may now include the bus company's buyer
    cast = c.post("/api/v1/opportunity-contacts", headers=s, json={
        "opportunity_id": opp["id"], "contact_id": deal["bus_contact"]["id"], "role": "end_user"})
    assert cast.status_code == 201, cast.text
    # a stranger's person still cannot be cast
    stranger = create(c, admin, "customers", name="Nobody Inc")
    nobody = create(c, admin, "customer-contacts", customer_id=stranger["id"], name="N")
    assert c.post("/api/v1/opportunity-contacts", headers=s, json={"opportunity_id": opp["id"], "contact_id": nobody["id"]}).status_code == 422


def test_a_won_deal_opens_one_project_that_knows_where_it_came_from(deal) -> None:
    c, s, admin = deal["client"], deal["sales"], deal["admin"]
    opp = _opportunity(deal)
    c.post("/api/v1/document-parties", headers=s, json={
        "entity_type": "opportunity", "entity_id": opp["id"], "customer_id": deal["bus"]["id"], "party_role": "end_client"})
    early = c.post(f"/api/v1/opportunities/{opp['id']}/project", headers=s, json={})
    assert early.status_code == 409 and "won" in early.text
    assert c.patch(f"/api/v1/opportunities/{opp['id']}", headers=s, json={"status": "won"}).status_code == 200
    contract = create(c, admin, "contracts", title="Subcontract with X", contract_type="service", customer_id=deal["friend"]["id"],
                      opportunity_id=opp["id"], currency="USD", total_amount=80000,
                      upstream={"contract_no": "MB-2026-07", "parties": ["Metro Bus Co", "X"], "summary": "development agreement"})
    opened = c.post(f"/api/v1/opportunities/{opp['id']}/project", headers=s, json={"project_code": "BUS-01"})
    assert opened.status_code == 201, opened.text
    project = opened.json()["data"]
    assert project["customer_id"] == deal["friend"]["id"] and project["client"] == "X (friend)"
    assert project["opportunity_id"] == opp["id"] and project["contract_id"] == contract["id"]
    assert project["owner_employee_id"] == deal["sales_employee"]
    again = c.post(f"/api/v1/opportunities/{opp['id']}/project", headers=s, json={})
    assert again.status_code == 200 and again.json()["data"]["id"] == project["id"], "one deal, one project"
    detail = c.get(f"/api/v1/projects/{project['id']}/detail", headers=admin).json()["data"]
    assert detail["customer"]["name"] == "X (friend)" and detail["opportunity"]["id"] == opp["id"]
    assert detail["contract"]["upstream"]["contract_no"] == "MB-2026-07"
    assert [p["party_role"] for p in detail["parties"]] == ["contracting", "end_client"], "the parties rode along"
    # the contract carried them too, and the upstream reference is not a contract of ours
    contract_read = c.get(f"/api/v1/contracts/{contract['id']}", headers=admin).json()["data"]
    assert [p["party_role"] for p in contract_read["parties"]] == ["contracting", "end_client"]
    assert c.get("/api/v1/contracts", headers=admin, params={"opportunity_id": opp["id"]}).json()["meta"]["total"] == 1
    # a reader without the contract grant sees the project but not the contract
    without = c.get(f"/api/v1/projects/{project['id']}/detail", headers=s).json()["data"]
    assert without["contract"] is None and without["customer"]["name"] == "X (friend)"


def test_project_links_are_checked_and_the_gate_is_project_manage(deal) -> None:
    c, admin = deal["client"], deal["admin"]
    desk = dict(invite_member(c, admin, "pm", ["project.manage"], employee="pm"))
    made = c.post("/api/v1/projects", headers=desk, json={"project_name": "Dispatch build", "customer_id": deal["friend"]["id"]})
    assert made.status_code == 201, made.text
    assert made.json()["data"]["client"] == "X (friend)", "the customer's name is the snapshot"
    bad = c.post("/api/v1/projects", headers=desk, json={"project_name": "x", "contract_id": "00000000-0000-0000-0000-000000000000"})
    assert bad.status_code == 404
    nobody = dict(invite_member(c, admin, "clerk", ["timesheet.submit_own"], employee="clerk"))
    assert c.post("/api/v1/projects", headers=nobody, json={"project_name": "x"}).status_code == 403
    listed = c.get("/api/v1/projects", headers=admin, params={"customer_id": deal["friend"]["id"]}).json()
    assert listed["meta"]["total"] == 1
    assert c.get("/api/v1/capabilities", headers=admin).status_code == 200


def test_relations_between_customers_read_from_either_side(deal) -> None:
    c, admin, s = deal["client"], deal["admin"], deal["sales"]
    made = c.post("/api/v1/customer-relations", headers=admin, json={
        "customer_id": deal["friend"]["id"], "related_customer_id": deal["bus"]["id"], "relation_type": "referrer_of",
        "effective_from": "2026-10-01", "remarks": "single line of contact; we never talk to the bus company"})
    assert made.status_code == 201, made.text
    assert c.post("/api/v1/customer-relations", headers=admin, json={
        "customer_id": deal["friend"]["id"], "related_customer_id": deal["friend"]["id"], "relation_type": "partner_of"}).status_code == 422
    assert c.post("/api/v1/customer-relations", headers=s, json={
        "customer_id": deal["friend"]["id"], "related_customer_id": deal["bus"]["id"], "relation_type": "partner_of"}).status_code == 403
    from_friend = c.get(f"/api/v1/customers/{deal['friend']['id']}/relations", headers=s).json()["data"]
    assert [(r["relation_type_here"], r["other_customer_name"], r["direction"]) for r in from_friend] == [("referrer_of", "Metro Bus Co", "subject")]
    from_bus = c.get(f"/api/v1/customers/{deal['bus']['id']}/relations", headers=s).json()["data"]
    assert [(r["relation_type_here"], r["other_customer_name"], r["direction"]) for r in from_bus] == [("referred_by", "X (friend)", "object")]
    brief = c.get(f"/api/v1/customers/{deal['bus']['id']}/detail", headers=admin).json()["data"]
    assert brief["relations"][0]["relation_type_here"] == "referred_by"


def test_a_leads_referrer_becomes_the_deals_referrer_party(deal) -> None:
    c, s = deal["client"], deal["sales"]
    lead = c.post("/api/v1/leads", headers=s, json={
        "employee_id": deal["sales_employee"], "company_name": "Metro Bus Co", "contact_name": "via X", "source": "referral",
        "referrer_contact_id": deal["friend_contact"]["id"]})
    assert lead.status_code == 201, lead.text
    assert lead.json()["data"]["referrer_customer_id"] == deal["friend"]["id"], "the person names the customer"
    mismatched = c.post("/api/v1/leads", headers=s, json={
        "employee_id": deal["sales_employee"], "company_name": "x", "referrer_customer_id": deal["bus"]["id"],
        "referrer_contact_id": deal["friend_contact"]["id"]})
    assert mismatched.status_code == 422
    assert c.patch(f"/api/v1/leads/{lead.json()['data']['id']}", headers=s, json={"status": "qualified"}).status_code == 200
    converted = c.post(f"/api/v1/leads/{lead.json()['data']['id']}/convert", headers=s, json={
        "customer_id": deal["friend"]["id"], "opportunity_title": "Driver dispatch (via X)"})
    assert converted.status_code == 200, converted.text
    opp = converted.json()["data"]["opportunity"]
    parties = c.get(f"/api/v1/opportunities/{opp['id']}/detail", headers=s).json()["data"]["parties"]
    assert [(p["party_role"], p["customer_name"]) for p in parties] == [("contracting", "X (friend)"), ("referrer", "X (friend)")]
    assert parties[1]["contact_name"] == "X"
