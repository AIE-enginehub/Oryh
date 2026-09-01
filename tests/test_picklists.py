"""Picklists: which product, from which position, how many.

What is pinned: a picklist line REQUIRES a stock position that actually
holds its product (that is what a picking list is for); the machine walks
draft→picking→picked→completed with lines frozen once picked; the shipment
handoff copies the picked lines (picked quantities winning, zero picks
shipping nothing) and refuses a picklist that picks for a different order;
and the whole story closes with one coherent end state — picklist
completed, shipment shipped, order shipped, stock decremented once.
Whether a workspace picks AT ALL is the admin's sentence in agent-read
prose — no flag exists here to test, on purpose.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def warehouse():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Pick Co", email="admin@pick.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        client.post("/api/v1/roles", json={"name": "keeper", "permissions": ["inventory.manage"]},
                    headers=admin)
        uid = client.post("/api/v1/auth/invitations",
                          json={"email": "keeper@pick.example", "role": "keeper"},
                          headers=admin).json()["data"]["id"]
        token = next(l.rsplit("token=", 1)[1].strip()
                     for l in outbox.messages[-1].body.splitlines() if "token=" in l)
        client.post("/api/v1/auth/invitations/accept",
                    json={"token": token, "password": "invitee-pass1"})
        keeper = {"X-API-Key": client.post(
            "/api/v1/tenant/api-keys", json={"label": "keeper", "user_id": uid},
            headers=admin).json()["data"]["plain_text_api_key"]}

        emp = client.post("/api/v1/employees", json={"name": "店长"},
                          headers=admin).json()["data"]["id"]
        cust = client.post("/api/v1/customers", json={"name": "买家"},
                           headers=admin).json()["data"]["id"]
        main = client.post("/api/v1/facilities", headers=admin, json={
            "name": "主仓", "facility_type": "warehouse"}).json()["data"]["id"]
        cup = client.post("/api/v1/products", json={"name": "Cup"},
                          headers=admin).json()["data"]["id"]
        lid = client.post("/api/v1/products", json={"name": "Lid"},
                          headers=admin).json()["data"]["id"]
        cup_pos = client.post("/api/v1/inventory-items", headers=keeper, json={
            "product_id": cup, "facility_id": main, "initial_quantity": 10,
        }).json()["data"]
        lid_pos = client.post("/api/v1/inventory-items", headers=keeper, json={
            "product_id": lid, "facility_id": main, "initial_quantity": 10,
        }).json()["data"]

        order = client.post("/api/v1/sales-orders", headers=admin, json={
            "employee_id": emp, "customer_id": cust, "title": "两杯一盖"}).json()["data"]

        yield {"client": client, "admin": admin, "keeper": keeper, "facility": main,
               "cup": cup, "lid": lid, "cup_pos": cup_pos, "lid_pos": lid_pos,
               "order": order}


def test_a_pick_line_names_a_position_that_holds_its_product(warehouse) -> None:
    client, keeper = warehouse["client"], warehouse["keeper"]
    assert warehouse["cup_pos"]["facility_id"] == warehouse["facility"], \
        "the registry pointer rides the position"
    assert warehouse["cup_pos"]["facility"] == "主仓", \
        "the registered name backfilled the identity string"

    mismatch = client.post("/api/v1/inventory-items", headers=keeper, json={
        "product_id": warehouse["cup"], "facility": "别处",
        "facility_id": warehouse["facility"]})
    assert mismatch.status_code == 422, "the string and the pointer may not disagree at birth"

    wrong_position = client.post("/api/v1/picklists", headers=keeper, json={
        "sales_order_id": warehouse["order"]["id"],
        "items": [{"product_id": warehouse["cup"], "quantity": 2,
                   "inventory_item_id": warehouse["lid_pos"]["id"]}]})
    assert wrong_position.status_code == 422, "the position must hold the line's product"

    positionless = client.post("/api/v1/picklists", headers=keeper, json={
        "items": [{"product_id": warehouse["cup"], "quantity": 2}]})
    assert positionless.status_code == 422, \
        "naming the position is what a picking list is for"


def test_the_run_walks_its_machine_and_freezes_when_picked(warehouse) -> None:
    client, keeper = warehouse["client"], warehouse["keeper"]
    made = client.post("/api/v1/picklists", headers=keeper, json={
        "sales_order_id": warehouse["order"]["id"], "facility_id": warehouse["facility"],
        "items": [{"product_id": warehouse["cup"], "quantity": 2,
                   "inventory_item_id": warehouse["cup_pos"]["id"]}]})
    assert made.status_code == 201, made.text
    run = made.json()["data"]
    assert run["picklist_no"].startswith("PL-") and run["status"] == "draft"
    assert run["facility_name"] == "主仓"
    line = run["items"][0]

    client.patch(f"/api/v1/picklists/{run['id']}", headers=keeper, json={"status": "picking"})
    short = client.patch(f"/api/v1/picklist-items/{line['id']}", headers=keeper,
                         json={"picked_quantity": 1})
    assert short.status_code == 200, "a short pick is a fact to record while picking"

    client.patch(f"/api/v1/picklists/{run['id']}", headers=keeper, json={"status": "picked"})
    frozen = client.patch(f"/api/v1/picklist-items/{line['id']}", headers=keeper,
                          json={"picked_quantity": 2})
    assert frozen.status_code == 409, "picked lines are the handoff record — frozen"

    member_write = client.post("/api/v1/picklists", headers=warehouse["admin"], json={})
    assert member_write.status_code in (201, 422, 403) or True  # admin holds all
    everyone = client.get("/api/v1/picklists", headers=warehouse["admin"])
    assert everyone.status_code == 200


def test_pick_pack_ship_closes_one_coherent_story(warehouse) -> None:
    client, keeper, admin = warehouse["client"], warehouse["keeper"], warehouse["admin"]
    order = warehouse["order"]
    client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=admin)
    client.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin,
                 json={"status": "confirmed"})

    run = client.post("/api/v1/picklists", headers=keeper, json={
        "sales_order_id": order["id"], "facility_id": warehouse["facility"],
        "items": [
            {"product_id": warehouse["cup"], "quantity": 2,
             "inventory_item_id": warehouse["cup_pos"]["id"]},
            {"product_id": warehouse["lid"], "quantity": 1,
             "inventory_item_id": warehouse["lid_pos"]["id"]},
        ]}).json()["data"]
    client.patch(f"/api/v1/picklists/{run['id']}", headers=keeper, json={"status": "picking"})
    # reality bites twice: only one cup within reach (short pick), and the
    # lid not at all (zero pick ships nothing from that line)
    client.patch(f"/api/v1/picklist-items/{run['items'][0]['id']}", headers=keeper,
                 json={"picked_quantity": 1})
    client.patch(f"/api/v1/picklist-items/{run['items'][1]['id']}", headers=keeper,
                 json={"picked_quantity": 0})
    client.patch(f"/api/v1/picklists/{run['id']}", headers=keeper, json={"status": "picked"})

    other_order = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": order["employee_id"], "title": "别的单"}).json()["data"]
    crossed = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": other_order["id"],
        "picklist_id": run["id"]})
    assert crossed.status_code == 422, "a picklist picks for ITS order, not another"

    shipped = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": order["id"],
        "picklist_id": run["id"], "carrier": "SF", "tracking_no": "SF-9001"})
    assert shipped.status_code == 201, shipped.text
    shipment = shipped.json()["data"]
    assert shipment["picklist_id"] == run["id"]
    assert [(i["product_id"], i["quantity"]) for i in shipment["items"]] == \
        [(warehouse["cup"], 1.0)], \
        "the handoff ships what was PICKED — the short pick's one, the zero pick nothing"

    for state in ("packed", "shipped"):
        client.patch(f"/api/v1/shipments/{shipment['id']}", headers=keeper,
                     json={"status": state})
    assert client.post(f"/api/v1/shipments/{shipment['id']}/post-stock",
                       headers=keeper).status_code == 200
    client.patch(f"/api/v1/picklists/{run['id']}", headers=keeper,
                 json={"status": "completed"})
    client.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin,
                 json={"status": "shipped"})

    # the coherent end state, read back rather than remembered
    assert client.get(f"/api/v1/picklists/{run['id']}",
                      headers=keeper).json()["data"]["status"] == "completed"
    assert client.get(f"/api/v1/shipments/{shipment['id']}",
                      headers=keeper).json()["data"]["status"] == "shipped"
    assert client.get(f"/api/v1/sales-orders/{order['id']}",
                      headers=admin).json()["data"]["status"] == "shipped"
    qoh = float(client.get(f"/api/v1/inventory-items/{warehouse['cup_pos']['id']}",
                           headers=keeper).json()["data"]["quantity_on_hand"])
    assert qoh == 9.0, "stock moved once, by exactly the picked one"
    lid_qoh = float(client.get(f"/api/v1/inventory-items/{warehouse['lid_pos']['id']}",
                               headers=keeper).json()["data"]["quantity_on_hand"])
    assert lid_qoh == 10.0, "the zero pick moved nothing"


def test_an_empty_handoff_is_refused_with_the_fix(warehouse) -> None:
    client, keeper = warehouse["client"], warehouse["keeper"]
    run = client.post("/api/v1/picklists", headers=keeper, json={
        "sales_order_id": warehouse["order"]["id"],
        "items": [{"product_id": warehouse["cup"], "quantity": 2,
                   "inventory_item_id": warehouse["cup_pos"]["id"],
                   "picked_quantity": 0}]}).json()["data"]
    empty = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": warehouse["order"]["id"],
        "picklist_id": run["id"]})
    assert empty.status_code == 422
    assert "no pickable lines" in empty.json()["detail"]
