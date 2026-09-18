"""Regressions from the 2026-09-12 architecture review
(docs/system-architecture-review-2026-09-12.md), the parts SQLite can prove.

N01 — the approved-and-posted fact is one fact: an effect-bearing document
born past its initial state needs the advance grant; it posts under the
definition it was filed under; once posted its content is frozen and it
cannot be deleted; a transfer nets to zero and moves one thing.
N02 — the expiry sweep only lapses batches that have lapsed, once per batch
per request (the concurrency half lives in tests/postgres/).
N05 — a CRM row's references agree with each other, whichever call set
them; a line renamed to another product is quoted under that product.
N11 — NaN and Infinity never enter a request body.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Review Co", email="admin@review.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        product = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP-1"}, headers=admin).json()["data"]["id"]
        position = client.post("/api/v1/inventory-items", headers=admin, json={
            "product_id": product, "facility": "main", "initial_quantity": 10}).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]

        def define(object_type: str, effect_key: str, reason: str, version_bump: dict | None = None):
            machine = {"initial": "draft", "states": ["draft", "approved"],
                       "transitions": {"draft": ["approved"], "approved": []},
                       effect_key: {"reason": reason, "state": "approved"}}
            r = client.post("/api/v1/object-type-definitions", headers=admin,
                            json={"object_type": object_type, "state_machine": machine})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "product": product, "position": position,
               "customer": customer, "define": define}


# --- N01 ---------------------------------------------------------------------

def test_an_effect_document_born_approved_is_an_advance(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("damage_report", "stock_effect", "damaged")
    writer = invite_member(c, admin, "writer", ["business_object.write:damage_report"])
    lines = [{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -1}]
    born_ready = c.post("/api/v1/business-objects", headers=writer, json={
        "object_type": "damage_report", "title": "x", "status": "approved", "payload": {"lines": lines}})
    assert born_ready.status_code == 403 and "business_object.advance" in born_ready.json()["detail"], born_ready.text
    draft = c.post("/api/v1/business-objects", headers=writer, json={
        "object_type": "damage_report", "title": "x", "status": "draft", "payload": {"lines": lines}})
    assert draft.status_code == 201, draft.text
    assert draft.json()["data"]["payload"]["definition_version"] == 1
    advancer = invite_member(c, admin, "advancer", ["business_object.advance:damage_report", "inventory.manage"])
    moved = c.patch(f"/api/v1/business-objects/{draft.json()['data']['id']}", headers=advancer, json={"status": "approved"})
    assert moved.status_code == 200, moved.text
    posted = c.post(f"/api/v1/business-objects/{draft.json()['data']['id']}/post-stock", headers=advancer)
    assert posted.status_code == 200, posted.text


def test_a_document_posts_under_the_definition_it_was_filed_under(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    definition = desk["define"]("adjust_slip", "stock_effect", "adjustment")
    doc = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "adjust_slip", "title": "x", "status": "approved",
        "payload": {"lines": [{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -1}]}}).json()["data"]
    changed = c.patch(f"/api/v1/object-type-definitions/{definition['id']}", headers=admin, json={
        "state_machine": {"initial": "draft", "states": ["draft", "approved"],
                          "transitions": {"draft": ["approved"], "approved": []},
                          "stock_effect": {"reason": "damaged", "state": "approved"}}})
    assert changed.status_code == 200, changed.text
    refused = c.post(f"/api/v1/business-objects/{doc['id']}/post-stock", headers=admin)
    assert refused.status_code == 409 and "version" in refused.json()["detail"], refused.text


def test_a_posted_document_is_frozen_and_kept(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("damage_report", "stock_effect", "damaged")
    doc = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "damage_report", "title": "x", "status": "approved",
        "payload": {"lines": [{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -2}]}}).json()["data"]
    assert c.post(f"/api/v1/business-objects/{doc['id']}/post-stock", headers=admin).status_code == 200
    edited = c.patch(f"/api/v1/business-objects/{doc['id']}", headers=admin, json={
        "payload": {"lines": [{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -999}]}})
    assert edited.status_code == 409 and "frozen" in edited.json()["detail"], edited.text
    retitled = c.patch(f"/api/v1/business-objects/{doc['id']}", headers=admin, json={"title": "y"})
    assert retitled.status_code == 409
    gone = c.delete(f"/api/v1/business-objects/{doc['id']}", headers=admin)
    assert gone.status_code == 409 and "counter-document" in gone.json()["detail"]
    read = c.get(f"/api/v1/business-objects/{doc['id']}", headers=admin).json()["data"]
    assert read["payload"]["lines"][0]["quantity_on_hand_diff"] == -2


def test_a_transfer_nets_to_zero_and_moves_one_thing(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("stock_transfer", "stock_effect", "transfer")
    other = c.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": desk["product"], "facility": "annex"}).json()["data"]["id"]
    lid = c.post("/api/v1/products", json={"name": "Lid"}, headers=admin).json()["data"]["id"]
    lid_position = c.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": lid, "facility": "main"}).json()["data"]["id"]

    def transfer(lines):
        doc = c.post("/api/v1/business-objects", headers=admin, json={
            "object_type": "stock_transfer", "title": "t", "status": "approved", "payload": {"lines": lines}}).json()["data"]
        return c.post(f"/api/v1/business-objects/{doc['id']}/post-stock", headers=admin)

    unbalanced = transfer([{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -3},
                           {"inventory_item_id": other, "quantity_on_hand_diff": 2}])
    assert unbalanced.status_code == 422 and "net to zero" in unbalanced.json()["detail"]
    one_sided = transfer([{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -3}])
    assert one_sided.status_code == 422
    crossed = transfer([{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -3},
                        {"inventory_item_id": lid_position, "quantity_on_hand_diff": 3}])
    assert crossed.status_code == 422 and "different goods" in crossed.json()["detail"]
    ok = transfer([{"inventory_item_id": desk["position"], "quantity_on_hand_diff": -3},
                   {"inventory_item_id": other, "quantity_on_hand_diff": 3}])
    assert ok.status_code == 200, ok.text
    stock = c.get(f"/api/v1/inventory-items/{desk['position']}", headers=admin).json()["data"]["quantity_on_hand"]
    assert stock == 7.0


def test_an_account_transfer_nets_to_zero_in_one_unit(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("balance_transfer", "account_effect", "transfer")
    money = c.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "A", "unit_type": "currency", "unit": "CNY", "customer_id": desk["customer"], "opening_balance": 500}).json()["data"]
    points = c.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "P", "unit_type": "points", "unit": "point", "customer_id": desk["customer"]}).json()["data"]

    def transfer(lines):
        doc = c.post("/api/v1/business-objects", headers=admin, json={
            "object_type": "balance_transfer", "title": "t", "status": "approved", "payload": {"lines": lines}}).json()["data"]
        return c.post(f"/api/v1/business-objects/{doc['id']}/post-entries", headers=admin)

    across_units = transfer([{"billing_account_id": money["id"], "amount": -100},
                             {"billing_account_id": points["id"], "amount": 100}])
    assert across_units.status_code == 422 and "different units" in across_units.json()["detail"]
    unbalanced = transfer([{"billing_account_id": money["id"], "amount": -100},
                           {"billing_account_id": money["id"], "amount": 90}])
    assert unbalanced.status_code == 422
    assert c.get(f"/api/v1/billing-accounts/{money['id']}", headers=admin).json()["data"]["balance"] == 500.0


# --- N02 (the request-shaped half) -----------------------------------------------

def test_the_sweep_lapses_only_lapsed_batches_once_per_request(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("points_grant", "account_effect", "earned")
    points = c.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "P", "unit_type": "points", "unit": "point", "customer_id": desk["customer"]}).json()["data"]
    grant = c.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "points_grant", "title": "g", "status": "approved",
        "payload": {"lines": [{"billing_account_id": points["id"], "amount": 100, "expires_at": "2025-12-31T00:00:00Z"},
                              {"billing_account_id": points["id"], "amount": 100, "expires_at": "2099-12-31T00:00:00Z"}]}}).json()["data"]
    rows = c.post(f"/api/v1/business-objects/{grant['id']}/post-entries", headers=admin).json()["data"]["lines"]
    lapsed, future = rows[0]["entry_id"], rows[1]["entry_id"]
    url = f"/api/v1/billing-accounts/{points['id']}/expire"
    early = c.post(url, headers=admin, json={"lines": [{"entry_id": future, "amount": 100}]})
    assert early.status_code == 422 and "not lapsed" in early.json()["detail"], early.text
    twice = c.post(url, headers=admin, json={"lines": [{"entry_id": lapsed, "amount": 60}, {"entry_id": lapsed, "amount": 60}]})
    assert twice.status_code == 422 and "appears twice" in twice.json()["detail"], twice.text
    assert c.get(f"/api/v1/billing-accounts/{points['id']}", headers=admin).json()["data"]["balance"] == 200.0
    assert c.post(url, headers=admin, json={"lines": [{"entry_id": lapsed, "amount": 100}]}).status_code == 200


# --- N05 ---------------------------------------------------------------------

def test_a_crm_row_s_references_agree_with_each_other(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    emp = c.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
    other = c.post("/api/v1/customers", json={"name": "B"}, headers=admin).json()["data"]["id"]
    deal = c.post("/api/v1/opportunities", headers=admin, json={
        "employee_id": emp, "title": "A's deal", "customer_id": desk["customer"]}).json()["data"]
    crossed = c.post("/api/v1/activities", headers=admin, json={
        "employee_id": emp, "activity_type": "call", "subject": "call", "content": "x", "occurred_at": "2026-09-12T08:00:00Z",
        "customer_id": other, "opportunity_id": deal["id"]})
    assert crossed.status_code == 422 and "different customer" in crossed.json()["detail"], crossed.text
    fine = c.post("/api/v1/activities", headers=admin, json={
        "employee_id": emp, "activity_type": "call", "subject": "call", "content": "x", "occurred_at": "2026-09-12T08:00:00Z", "opportunity_id": deal["id"]})
    assert fine.status_code == 201, fine.text
    # the patch is judged against the whole row, not the field it carries
    repointed = c.patch(f"/api/v1/activities/{fine.json()['data']['id']}", headers=admin, json={"customer_id": other})
    assert repointed.status_code == 422, repointed.text
    contact = c.post("/api/v1/customer-contacts", headers=admin, json={"customer_id": other, "name": "B's person"}).json()["data"]["id"]
    wrong_person = c.post("/api/v1/activities", headers=admin, json={
        "employee_id": emp, "activity_type": "call", "subject": "call", "content": "x", "occurred_at": "2026-09-12T08:00:00Z", "opportunity_id": deal["id"], "contact_id": contact})
    assert wrong_person.status_code == 422


def test_a_line_renamed_to_another_product_is_quoted_under_it(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    emp = c.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
    lid = c.post("/api/v1/products", json={"name": "Lid", "product_code": "LID-1", "list_price": 5}, headers=admin).json()["data"]["id"]
    deal = c.post("/api/v1/opportunities", headers=admin, json={
        "employee_id": emp, "title": "deal", "customer_id": desk["customer"]}).json()["data"]
    line = c.post("/api/v1/opportunity-items", headers=admin, json={
        "opportunity_id": deal["id"], "product_id": desk["product"], "quantity": 2, "unit_price": 10}).json()["data"]
    assert line["product_name_snapshot"] == "Cup"
    switched = c.patch(f"/api/v1/opportunity-items/{line['id']}", headers=admin, json={"product_id": lid})
    assert switched.status_code == 200 and switched.json()["data"]["product_name_snapshot"] == "Lid", switched.text
    quote = c.post(f"/api/v1/opportunities/{deal['id']}/quote", headers=admin, json={}).json()["data"]
    assert [(i["product_id"], i["product_name_snapshot"]) for i in quote["items"]] == [(lid, "Lid")]


# --- N11 ---------------------------------------------------------------------

def test_nan_and_infinity_are_refused_at_the_boundary(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    desk["define"]("adjust_slip", "stock_effect", "adjustment")
    for bad in ("NaN", "Infinity"):
        body = '{"object_type": "adjust_slip", "title": "x", "status": "approved", "payload": {"lines": [{"inventory_item_id": "%s", "quantity_on_hand_diff": %s}]}}' % (desk["position"], bad)
        created = c.post("/api/v1/business-objects", headers={**admin, "Content-Type": "application/json"}, content=body)
        if created.status_code == 201:
            posted = c.post(f"/api/v1/business-objects/{created.json()['data']['id']}/post-stock", headers=admin)
            assert posted.status_code == 422, (bad, posted.text)
        else:
            assert created.status_code == 422, (bad, created.text)
    raw = c.post("/api/v1/inventory-items", headers={**admin, "Content-Type": "application/json"},
                 content='{"product_id": "%s", "facility": "x", "initial_quantity": NaN}' % desk["product"])
    assert raw.status_code == 422, raw.text
    stock = c.get(f"/api/v1/inventory-items/{desk['position']}", headers=admin).json()["data"]["quantity_on_hand"]
    assert stock == 10.0
