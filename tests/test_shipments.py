"""Shipments: the freight leg, and the one bridge it has to stock.

OFBiz Shipment/ShipmentItem in agent-native shape: one leg, one direction,
lines that name the stock POSITION they leave or land in
(`inventory_item_id` — ItemIssuance/ShipmentReceipt collapsed to the useful
core). The shipment is the freight document; the inventory ledger stays the
only stock truth, and /post-stock is the single, once-only bridge between
them — direction decides the sign, the shipment line rides as provenance,
and the header's order FK (returns included, since returns are order rows)
is carried onto every movement.

The matrix pinned here is what keeps agents from shipping backwards: sales
order → outbound, sales return → inbound, purchase order → inbound,
purchase return → outbound. Freight is warehouse work — inventory.manage
files and advances, the purchase-order pattern.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def dock():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Dock Co", email="admin@dock.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        keeper = invite_member(client, admin, "keeper", ["inventory.manage"])

        emp = client.post("/api/v1/employees", json={"name": "店长"},
                          headers=admin).json()["data"]["id"]
        cust = client.post("/api/v1/customers", json={"name": "买家"},
                           headers=admin).json()["data"]["id"]
        vendor = client.post("/api/v1/vendors", json={"name": "供应商"},
                             headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP-1"},
                              headers=admin).json()["data"]["id"]
        position = client.post("/api/v1/inventory-items", headers=admin, json={
            "product_id": product, "facility": "main", "initial_quantity": 10,
        }).json()["data"]["id"]

        def order(**extra) -> dict:
            body = {"employee_id": emp, "customer_id": cust, "title": "一单", **extra}
            r = client.post("/api/v1/sales-orders", json=body, headers=admin)
            assert r.status_code == 201, r.text
            return r.json()["data"]

        def qoh() -> float:
            return float(client.get(f"/api/v1/inventory-items/{position}",
                                    headers=admin).json()["data"]["quantity_on_hand"])

        yield {"client": client, "admin": admin, "keeper": keeper, "employee": emp,
               "customer": cust, "vendor": vendor, "product": product,
               "position": position, "order": order, "qoh": qoh}


def test_the_keeper_ships_and_the_machine_walks(dock) -> None:
    client, keeper = dock["client"], dock["keeper"]
    so = dock["order"]()
    created = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": so["id"], "facility": "main",
        "carrier": "SF Express", "tracking_no": "SF-1001",
        "items": [{"product_id": dock["product"], "quantity": 3,
                   "inventory_item_id": dock["position"]}],
    })
    assert created.status_code == 201, created.text
    shipment = created.json()["data"]
    assert shipment["shipment_no"].startswith("SH-")
    assert shipment["items"][0]["inventory_item_id"] == dock["position"], \
        "the line names its stock position — the ShipmentItem↔InventoryItem tie"

    for state in ("packed", "shipped", "received"):
        moved = client.patch(f"/api/v1/shipments/{shipment['id']}", headers=keeper,
                             json={"status": state})
        assert moved.status_code == 200, f"{state}: {moved.text}"
    read = client.get(f"/api/v1/shipments/{shipment['id']}", headers=keeper).json()["data"]
    assert read["shipped_at"] and read["received_at"], "literal transitions stamp their facts"

    stuck = client.patch(f"/api/v1/shipments/{shipment['id']}", headers=keeper,
                         json={"status": "packed"})
    assert stuck.status_code == 409, "received is terminal"

    late_line = client.post("/api/v1/shipment-items", headers=keeper, json={
        "shipment_id": shipment["id"], "product_id": dock["product"], "quantity": 1})
    assert late_line.status_code == 409, "lines are editable in draft/packed only"


def test_freight_is_warehouse_work(dock) -> None:
    """inventory.manage suffices — the desk that holds the stock ledger holds
    the legs that feed it, no second capability. The zero-capability refusal
    rides the member-surface audit; what this pins is the POSITIVE grant."""
    ok = dock["client"].post("/api/v1/shipments", headers=dock["keeper"], json={
        "direction": "inbound", "facility": "main"})
    assert ok.status_code == 201, ok.text


def test_the_direction_matrix_holds(dock) -> None:
    client, keeper = dock["client"], dock["keeper"]
    so = dock["order"]()
    ret = dock["order"](order_kind="return", original_order_id=so["id"])

    backwards = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "inbound", "sales_order_id": so["id"]})
    assert backwards.status_code == 422 and "matrix" in backwards.json()["detail"]

    return_parcel = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "inbound", "sales_order_id": ret["id"]})
    assert return_parcel.status_code == 201, \
        "a customer return's parcel comes IN, linked to the RETURN row"

    po = client.post("/api/v1/purchase-orders", headers=dock["admin"], json={
        "vendor_id": dock["vendor"], "employee_id": dock["employee"],
        "title": "进货"}).json()["data"]
    wrong_way = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "purchase_order_id": po["id"]})
    assert wrong_way.status_code == 422

    both = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": so["id"], "purchase_order_id": po["id"]})
    assert both.status_code == 422


def test_a_line_names_a_position_that_holds_its_product(dock) -> None:
    client, keeper, admin = dock["client"], dock["keeper"], dock["admin"]
    other = client.post("/api/v1/products", json={"name": "Lid", "product_code": "LID-1"},
                        headers=admin).json()["data"]["id"]
    crossed = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound",
        "items": [{"product_id": other, "quantity": 1,
                   "inventory_item_id": dock["position"]}]})
    assert crossed.status_code == 422, crossed.text
    assert dock["product"] in crossed.json()["detail"]


def test_post_stock_bridges_once_with_provenance(dock) -> None:
    client, keeper = dock["client"], dock["keeper"]
    so = dock["order"]()
    before = dock["qoh"]()
    shipment = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": so["id"],
        "items": [
            {"product_id": dock["product"], "quantity": 3,
             "inventory_item_id": dock["position"]},
            {"product_id": dock["product"], "quantity": 2},  # 直发 — no position
        ]}).json()["data"]

    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=keeper)
    assert posted.status_code == 200, posted.text
    outcomes = {line["outcome"] for line in posted.json()["data"]["lines"]}
    assert outcomes == {"posted", "skipped_no_position"}, \
        "a 直发 line is skipped and SAID to be, never silently absorbed"
    assert dock["qoh"]() == before - 3, "outbound decrements exactly the positioned line"

    movements = client.get("/api/v1/inventory-item-details",
                           params={"sales_order_id": so["id"]},
                           headers=keeper).json()["data"]
    assert len(movements) == 1
    assert movements[0]["reason"] == "issued"
    assert movements[0]["entity_type"] == "shipment_item", \
        "the ledger names the shipment line as provenance"

    again = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=keeper)
    assert again.status_code == 409, "the ledger is append-only — posting twice doubles goods"
    assert "counter-entries" in again.json()["detail"]


def test_the_return_loop_closes_through_a_shipment(dock) -> None:
    """退单收货 end to end: the customer return's parcel is an inbound
    shipment linked to the RETURN row; posting it lands the goods back in
    stock with the return row on the movement — the 验货入库 fact the flow
    admin advances the return on."""
    client, keeper = dock["client"], dock["keeper"]
    so = dock["order"](status="signed")
    ret = dock["order"](order_kind="return", original_order_id=so["id"], status="approved")
    before = dock["qoh"]()

    parcel = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "inbound", "sales_order_id": ret["id"],
        "carrier": "YTO", "tracking_no": "YT-889",
        "items": [{"product_id": dock["product"], "quantity": 2,
                   "inventory_item_id": dock["position"]}]}).json()["data"]
    posted = client.post(f"/api/v1/shipments/{parcel['id']}/post-stock", headers=keeper)
    assert posted.status_code == 200, posted.text
    assert dock["qoh"]() == before + 2, "inbound increments"

    movements = client.get("/api/v1/inventory-item-details",
                           params={"sales_order_id": ret["id"]},
                           headers=keeper).json()["data"]
    assert [m["reason"] for m in movements] == ["returned"], \
        "a customer return coming back is `returned` whichever door it enters — " \
        "the direct movement path already says so, and one event must not get " \
        "two ledger words"


def test_the_segregation_policy_is_a_position_not_a_schema(dock) -> None:
    """The OFBiz fork, dissolved: whether returned goods sit apart is WHICH
    position the inbound line names — free-text facility, created on first
    use — while the ledger's provenance keeps returned-unit traceability
    either way. Both tenant policies run through the same public API with
    zero configuration: this test is the segregated one, original-position
    receiving is the return-loop test above."""
    client, keeper, admin = dock["client"], dock["keeper"], dock["admin"]
    so = dock["order"](status="signed")
    ret = dock["order"](order_kind="return", original_order_id=so["id"], status="approved")

    quarantine = client.post("/api/v1/inventory-items", headers=keeper, json={
        "product_id": dock["product"], "facility": "退货区"}).json()["data"]["id"]
    parcel = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "inbound", "sales_order_id": ret["id"],
        "items": [{"product_id": dock["product"], "quantity": 2,
                   "inventory_item_id": quarantine}]}).json()["data"]
    assert client.post(f"/api/v1/shipments/{parcel['id']}/post-stock",
                       headers=keeper).status_code == 200

    def qty(item_id: str) -> float:
        return float(client.get(f"/api/v1/inventory-items/{item_id}",
                                headers=keeper).json()["data"]["quantity_on_hand"])

    assert qty(quarantine) == 2, "segregated: the goods sit in 退货区, not the main position"

    traced = client.get("/api/v1/inventory-item-details",
                        params={"sales_order_id": ret["id"]},
                        headers=keeper).json()["data"]
    assert [m["reason"] for m in traced] == ["returned"], \
        "traceability rides the ledger, not the segregation"

    # inspection passed: the transfer pair moves goods 退货区 → main
    main_before = dock["qoh"]()
    for item_id, diff in ((quarantine, -2.0), (dock["position"], 2.0)):
        moved = client.post("/api/v1/inventory-item-details", headers=keeper, json={
            "inventory_item_id": item_id, "quantity_on_hand_diff": diff,
            "reason": "transfer", "description": "验收合格,退货区转主仓",
            "entity_type": "sales_order", "entity_id": ret["id"]})
        assert moved.status_code == 201, moved.text
    assert qty(quarantine) == 0 and dock["qoh"]() == main_before + 2


def test_a_todo_may_point_at_a_shipment(dock) -> None:
    client, admin = dock["client"], dock["admin"]
    shipment = client.post("/api/v1/shipments", headers=dock["keeper"], json={
        "direction": "outbound"}).json()["data"]
    todo = client.post("/api/v1/todos", headers=admin, json={
        "entity_type": "shipment", "entity_id": shipment["id"],
        "employee_id": dock["employee"], "title": "打包发货"})
    assert todo.status_code == 201, todo.text


def test_post_stock_refuses_an_archived_position(dock) -> None:
    """An archived shelf takes no goods: the posting names the position and
    its fix instead of writing a movement nobody can read back."""
    client, keeper, admin = dock["client"], dock["keeper"], dock["admin"]
    so = dock["order"]()
    shipment = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": so["id"],
        "items": [{"product_id": dock["product"], "quantity": 1,
                   "inventory_item_id": dock["position"]}]}).json()["data"]
    assert client.delete(f"/api/v1/inventory-items/{dock['position']}",
                         headers=admin).status_code == 204
    refused = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=keeper)
    assert refused.status_code == 409, refused.text
    assert "archived" in refused.json()["detail"]
    assert dock["qoh"]() == 10, "nothing moved"
