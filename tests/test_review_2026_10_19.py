"""The 2026-10-19 review's reproductions, kept as regressions.

Each test is one of the review's probes (`docs/system-architecture-review-
2026-10-19.zh.md`, F01–F09), now asserting the right answer. Synthetic data,
the test stack's SQLite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from conftest import create, invite_member, make_stack, provision_tenant
from app.api import master_data
from app.core import business_date
from app.core.line_math import derive_line_amount
from app.models import Customer

DESK = ["users.manage", "inventory.manage", "order.submit_own"]


@pytest.fixture()
def shop():
    with make_stack([]) as (client, engine):
        t = provision_tenant(client, company_name="Review Co", email="admin@review19.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        users = client.get("/api/v1/auth/users", headers=admin).json()["data"]
        admin_user = next(u for u in users if u["email"] == "admin@review19.example")
        yield {"client": client, "admin": admin, "admin_user": admin_user}


# --- F01: nobody acts on a person wider than themselves -----------------------


def test_a_users_manage_desk_cannot_demote_disable_or_readdress_the_administrator(shop) -> None:
    c, admin, target = shop["client"], shop["admin"], shop["admin_user"]
    desk = dict(invite_member(c, admin, "stock_desk", DESK, email="desk@review19.example", employee="desk"))
    url = f"/api/v1/auth/users/{target['id']}"
    for change in ({"role": "stock_desk"}, {"status": "disabled"}, {"email": "desk-inbox@review19.example"}):
        r = c.patch(url, headers=desk, json=change)
        assert r.status_code == 403, (change, r.text)
        assert "administrator" in r.text
    assert c.post(f"{url}/password-reset-email", headers=desk).status_code == 403
    after = next(u for u in c.get("/api/v1/auth/users", headers=admin).json()["data"] if u["id"] == target["id"])
    assert (after["role"], after["status"], after["email"]) == ("admin", "active", "admin@review19.example")


def test_the_desk_still_manages_people_within_its_own_reach(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    desk = dict(invite_member(c, admin, "stock_desk", DESK, email="desk@review19.example", employee="desk"))
    invited = c.post("/api/v1/auth/invitations", headers=desk,
                     json={"email": "picker@review19.example", "name": "Picker", "role": "stock_desk"})
    assert invited.status_code == 201, invited.text
    assert c.patch(f"/api/v1/auth/users/{invited.json()['data']['id']}", headers=desk,
                   json={"status": "disabled"}).status_code == 200


def test_a_bundle_or_key_in_an_administrators_name_is_the_administrators(shop) -> None:
    c, admin, target = shop["client"], shop["admin"], shop["admin_user"]
    credential = invite_member(c, admin, "id_desk", ["users.manage", "keys.manage"], email="id@review19.example", employee="id")
    desk = dict(credential)
    bundle = c.post(f"/api/v1/users/{target['id']}/skill-bundle", headers=desk)
    assert bundle.status_code == 403, bundle.text
    user_key = c.post("/api/v1/tenant/api-keys", headers=desk, json={"label": "for admin", "user_id": target["id"]})
    assert user_key.status_code == 403, user_key.text
    service = c.post("/api/v1/tenant/api-keys", headers=desk, json={"label": "workspace"})
    assert service.status_code == 403 and "service key" in service.text
    own = c.post("/api/v1/tenant/api-keys", headers=desk, json={"label": "mine", "user_id": credential.user_id})
    assert own.status_code == 201, own.text
    assert c.post("/api/v1/tenant/api-keys", headers=admin, json={"label": "workspace"}).status_code == 201


def test_a_key_desk_equips_members_but_not_those_who_administer_access(shop) -> None:
    c, admin, target = shop["client"], shop["admin"], shop["admin_user"]
    desk = dict(invite_member(c, admin, "key_desk", ["keys.manage"], email="keys@review19.example", employee="keys"))
    member = invite_member(c, admin, "staff", None, role="member", email="staff@review19.example", employee="staff")
    people = invite_member(c, admin, "people_desk", ["users.manage"], email="people@review19.example", employee="people")
    issue = lambda user_id: c.post("/api/v1/tenant/api-keys", headers=desk, json={"label": "k", "user_id": user_id})
    assert issue(member.user_id).status_code == 201, "equipping staff is the key desk's job"
    assert issue(target["id"]).status_code == 403
    refused = issue(people.user_id)
    assert refused.status_code == 403 and "users.manage" in refused.text


def test_a_key_desk_does_not_mint_a_key_for_whoever_writes_the_skills(shop) -> None:
    """Workspace skills ride in every bundle, the administrator's too: a key
    in a skills.manage holder's name rewrites what the administrator's agent
    reads (review 2026-10-22, N2)."""
    c, admin = shop["client"], shop["admin"]
    desk = dict(invite_member(c, admin, "key_desk", ["keys.manage"], email="keys@review22.example", employee="keys"))
    author = invite_member(c, admin, "skill_desk", ["skills.manage"], email="skills@review22.example", employee="skills")
    refused = c.post("/api/v1/tenant/api-keys", headers=desk, json={"label": "k", "user_id": author.user_id})
    assert refused.status_code == 403 and "skills.manage" in refused.text, refused.text
    both = dict(invite_member(c, admin, "both_desk", ["keys.manage", "skills.manage"], email="both@review22.example", employee="both"))
    assert c.post("/api/v1/tenant/api-keys", headers=both, json={"label": "k", "user_id": author.user_id}).status_code == 201, \
        "a desk that writes skills itself reaches nothing new through the key"


def test_switching_a_wider_key_back_on_is_the_administrators(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    desk = dict(invite_member(c, admin, "id_desk", ["users.manage", "keys.manage"], email="id@review19.example", employee="id"))
    issued = c.post("/api/v1/tenant/api-keys", headers=admin, json={"label": "workspace"}).json()["data"]["api_key"]
    assert c.patch(f"/api/v1/tenant/api-keys/{issued['id']}", headers=desk, json={"is_active": False}).status_code == 200, \
        "switching a key off stays open — it is the safety lever"
    back_on = c.patch(f"/api/v1/tenant/api-keys/{issued['id']}", headers=desk, json={"is_active": True})
    assert back_on.status_code == 403, back_on.text


# --- F02: a contract's parties follow the contract's side ---------------------


def test_a_purchase_desk_does_not_list_a_sales_contracts_parties(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    buyer = create(c, admin, "customers", name="Synthetic buyer")["id"]
    referrer = create(c, admin, "customers", name="Synthetic referrer")["id"]
    vendor = create(c, admin, "vendors", name="Synthetic vendor")["id"]
    sales = c.post("/api/v1/contracts", headers=admin, json={"title": "Sales", "customer_id": buyer}).json()["data"]["id"]
    purchase = c.post("/api/v1/contracts", headers=admin, json={"title": "Purchase", "vendor_id": vendor}).json()["data"]["id"]
    for contract in (sales, purchase):
        r = c.post("/api/v1/document-parties", headers=admin, json={
            "entity_type": "contract", "entity_id": contract, "customer_id": referrer, "party_role": "referrer",
            "terms": {"commission_rate": "8%"}})
        assert r.status_code == 201, r.text
    buy = dict(invite_member(c, admin, "buy_desk", ["contract.manage:purchase"], email="buy@review19.example", employee="buy"))
    sell = dict(invite_member(c, admin, "sell_desk", ["contract.manage:sales"], email="sell@review19.example", employee="sell"))
    none = dict(invite_member(c, admin, "no_desk", [], email="none@review19.example", employee="none"))
    seen = lambda who: {r["entity_id"] for r in c.get("/api/v1/document-parties", headers=who).json()["data"]}
    assert seen(buy) == {purchase}
    assert seen(sell) == {sales}
    assert seen(none) == set()
    assert seen(admin) == {sales, purchase}


# --- F03: a write that committed and then failed is not written again --------


def test_a_failure_after_commit_leaves_the_key_unresolved_not_free(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    keyed = {**admin, "Idempotency-Key": "review19-post-commit"}
    body = {"name": "Synthetic post-commit failure"}
    real, calls = master_data.envelope, {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic failure after commit")
        return real(*args, **kwargs)

    with patch.object(master_data, "envelope", side_effect=flaky):
        with pytest.raises(RuntimeError):
            c.post("/api/v1/customers", headers=keyed, json=body)
        again = c.post("/api/v1/customers", headers=keyed, json=body)
    assert again.status_code == 409, again.text
    assert "never reported its outcome" in again.text
    with c.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Customer).where(Customer.name == body["name"])) == 1


def test_a_failure_before_anything_committed_still_frees_the_key(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    keyed = {**admin, "Idempotency-Key": "review19-pre-commit"}
    body = {"name": "Synthetic pre-commit failure"}
    with patch.object(master_data, "require_master_data_manage", side_effect=RuntimeError("synthetic")):
        with pytest.raises(RuntimeError):
            c.post("/api/v1/customers", headers=keyed, json=body)
    again = c.post("/api/v1/customers", headers=keyed, json=body)
    assert again.status_code == 201, again.text


# --- F05: today is the workspace's date --------------------------------------


def test_the_business_date_is_beijings_while_utc_is_still_yesterday() -> None:
    utc_late = datetime(2026, 10, 19, 17, 30, tzinfo=timezone.utc)  # 01:30 on the 20th in Beijing

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_late.astimezone(tz) if tz else utc_late.replace(tzinfo=None)

    with patch.object(business_date, "datetime", Clock):
        assert business_date.business_today().isoformat() == "2026-10-20"
    assert business_date.resolve_timezone("+08:00").utcoffset(None) == timedelta(hours=8)
    with pytest.raises(ValueError):
        business_date.resolve_timezone("Mars/Olympus")


# --- F06: a deal opens one project --------------------------------------------


def test_a_second_project_cannot_claim_the_same_deal(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    emp = create(c, admin, "employees", name="Rep")["id"]
    customer = create(c, admin, "customers", name="Deal customer")["id"]
    deal = create(c, admin, "opportunities", employee_id=emp, title="Deal", customer_id=customer)["id"]
    first = c.post("/api/v1/projects", headers=admin, json={"project_name": "One", "opportunity_id": deal})
    assert first.status_code == 201, first.text
    second = c.post("/api/v1/projects", headers=admin, json={"project_name": "Two", "opportunity_id": deal})
    assert second.status_code == 409 and "one project" in second.text
    other = c.post("/api/v1/projects", headers=admin, json={"project_name": "Three"}).json()["data"]["id"]
    moved = c.patch(f"/api/v1/projects/{other}", headers=admin, json={"opportunity_id": deal})
    assert moved.status_code == 409
    again = c.patch(f"/api/v1/projects/{first.json()['data']['id']}", headers=admin, json={"opportunity_id": deal})
    assert again.status_code == 200, "restating its own deal is not a second claim"


# --- F07: one relation, one row ------------------------------------------------


def test_an_undated_relation_and_its_mirror_are_recorded_once(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    a = create(c, admin, "customers", name="Parent Co")["id"]
    b = create(c, admin, "customers", name="Child Co")["id"]
    body = {"customer_id": a, "related_customer_id": b, "relation_type": "parent_of"}
    assert c.post("/api/v1/customer-relations", headers=admin, json=body).status_code == 201
    assert c.post("/api/v1/customer-relations", headers=admin, json=body).status_code == 409
    mirror = c.post("/api/v1/customer-relations", headers=admin,
                    json={"customer_id": b, "related_customer_id": a, "relation_type": "subsidiary_of"})
    assert mirror.status_code == 409 and "other side" in mirror.text
    assert c.post("/api/v1/customer-relations", headers=admin,
                  json={"customer_id": a, "related_customer_id": b, "relation_type": "partner_of"}).status_code == 201
    assert c.post("/api/v1/customer-relations", headers=admin,
                  json={"customer_id": b, "related_customer_id": a, "relation_type": "partner_of"}).status_code == 409
    dated = {**body, "effective_from": "2027-01-01"}
    assert c.post("/api/v1/customer-relations", headers=admin, json=dated).status_code == 201, "a new period is a new row"
    assert len(c.get(f"/api/v1/customers/{a}/relations", headers=admin).json()["data"]) == 3


# --- F08: a party's person belongs to the party ---------------------------------


def test_changing_a_partys_customer_does_not_keep_the_old_customers_person(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    buyer = create(c, admin, "customers", name="Buyer")["id"]
    old = create(c, admin, "customers", name="Old referrer")["id"]
    new = create(c, admin, "customers", name="New referrer")["id"]
    old_person = create(c, admin, "customer-contacts", customer_id=old, name="Old person")["id"]
    new_person = create(c, admin, "customer-contacts", customer_id=new, name="New person")["id"]
    contract = c.post("/api/v1/contracts", headers=admin, json={"title": "Deal", "customer_id": buyer}).json()["data"]["id"]
    party = c.post("/api/v1/document-parties", headers=admin, json={
        "entity_type": "contract", "entity_id": contract, "customer_id": old, "party_role": "referrer",
        "contact_id": old_person}).json()["data"]["id"]
    url = f"/api/v1/document-parties/{party}"
    assert c.patch(url, headers=admin, json={"customer_id": new}).status_code == 422
    assert c.patch(url, headers=admin, json={"customer_id": None}).status_code == 422
    moved = c.patch(url, headers=admin, json={"customer_id": new, "contact_id": new_person})
    assert moved.status_code == 200 and moved.json()["data"]["contact_id"] == new_person
    cleared = c.patch(url, headers=admin, json={"customer_id": old, "contact_id": None})
    assert cleared.status_code == 200 and cleared.json()["data"]["contact_id"] is None


# --- F09: the quote bridge computes a line like every other path --------------


def test_the_quote_bridge_rounds_half_up_like_every_line(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    emp = create(c, admin, "employees", name="Rep")["id"]
    customer = create(c, admin, "customers", name="Rounding customer")["id"]
    deal = create(c, admin, "opportunities", employee_id=emp, title="Rounding", customer_id=customer)["id"]
    line = c.post("/api/v1/opportunity-items", headers=admin, json={
        "opportunity_id": deal, "product_name_snapshot": "Screws", "quantity": 1.5, "unit_price": 0.03})
    assert line.status_code == 201 and line.json()["data"]["amount"] == 0.05, line.text
    quoted = c.post(f"/api/v1/opportunities/{deal}/quote", headers=admin, json={})
    assert quoted.status_code == 201, quoted.text
    assert [i["amount"] for i in quoted.json()["data"]["items"]] == [0.05], "binary float rounding gave 0.04"
    assert derive_line_amount(1.5, 0.03, None) == 0.05
