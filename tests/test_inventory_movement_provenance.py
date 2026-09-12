"""Every ledger row is written by a business act, and carries that act.

The generic `POST /inventory-item-details` is gone: an agent that heard
"出库" once wrote a bare `issued` row past the order and the shipment, and
the row it wrote could not say why. Now a movement's provenance is not a
field the caller fills in — it is the bridge that wrote it: a shipment
line, a purchase-order line, the count import, an order's hold, or a
tenant-defined stock document in its approved state.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


@pytest.fixture()
def shop(client: TestClient):
    t = provision_tenant(client, company_name="Stock Co", email="admin@stock-co.example")
    headers = {"X-API-Key": t["plain_text_api_key"]}

    def post(path, body, expect=(200, 201)):
        r = client.post(f"/api/v1{path}", json=body, headers=headers)
        assert r.status_code in expect, f"{path} -> {r.status_code} {r.text[:300]}"
        return r.json()["data"]

    employee = post("/employees", {"name": "Li"})["id"]
    product = post("/products", {"name": "Widget", "product_code": "W-1"})["id"]
    item = post("/inventory-items", {"product_id": product, "facility": "main",
                                     "initial_quantity": 100})["id"]
    return {"client": client, "headers": headers, "post": post,
            "employee": employee, "product": product, "item": item}


def test_there_is_no_generic_ledger_write(shop) -> None:
    bare = shop["client"].post("/api/v1/inventory-item-details", headers=shop["headers"], json={
        "inventory_item_id": shop["item"], "quantity_on_hand_diff": -1, "reason": "issued"})
    assert bare.status_code in (404, 405), bare.text
    rows = shop["client"].get("/api/v1/inventory-item-details",
                              params={"inventory_item_id": shop["item"]},
                              headers=shop["headers"]).json()["data"]
    assert [r["reason"] for r in rows] == ["initial"], "the ledger is still readable"


def test_a_shipment_line_is_the_movement_s_provenance(shop) -> None:
    customer = shop["post"]("/customers", {"name": "Acme"})["id"]
    order = shop["post"]("/sales-orders", {
        "employee_id": shop["employee"], "customer_id": customer, "title": "one order"})
    leg = shop["post"]("/shipments", {
        "direction": "outbound", "sales_order_id": order["id"],
        "items": [{"product_id": shop["product"], "quantity": 1, "inventory_item_id": shop["item"]}]})
    shop["post"](f"/shipments/{leg['id']}/post-stock", {})
    listed = shop["client"].get(
        f"/api/v1/inventory-item-details?sales_order_id={order['id']}",
        headers=shop["headers"]).json()["data"]
    assert [(r["reason"], r["entity_type"], r["sales_order_id"]) for r in listed] == \
        [("issued", "shipment_item", order["id"])]


def test_a_stock_document_posts_under_its_definition_s_reason(shop) -> None:
    """报损单, 借用单, 调拨单: the tenant defines the type, names the ledger
    reason and the state that posts, and the bridge does the rest — once."""
    shop["post"]("/object-type-definitions", {
        "object_type": "damage_report", "title": "报损单",
        "state_machine": {
            "initial": "draft", "states": ["draft", "approved", "rejected"],
            "transitions": {"draft": ["approved", "rejected"], "approved": [], "rejected": []},
            "stock_effect": {"reason": "damaged", "state": "approved"},
        }})
    report = shop["post"]("/business-objects", {
        "object_type": "damage_report", "title": "两件摔坏", "status": "draft",
        "payload": {"lines": [{"inventory_item_id": shop["item"], "quantity_on_hand_diff": -2,
                               "description": "叉车碰倒"}]}})
    early = shop["client"].post(f"/api/v1/business-objects/{report['id']}/post-stock", headers=shop["headers"])
    assert early.status_code == 409 and "approved" in early.json()["detail"], early.text

    shop["client"].patch(f"/api/v1/business-objects/{report['id']}", headers=shop["headers"],
                         json={"status": "approved"})
    posted = shop["post"](f"/business-objects/{report['id']}/post-stock", {})
    assert posted["reason"] == "damaged" and posted["lines"][0]["quantity_on_hand"] == 98.0
    rows = shop["client"].get("/api/v1/inventory-item-details",
                              params={"entity_type": "business_object", "entity_id": report["id"]},
                              headers=shop["headers"]).json()["data"]
    assert [(r["reason"], r["quantity_on_hand_diff"], r["description"]) for r in rows] == \
        [("damaged", -2.0, "叉车碰倒")]
    twice = shop["client"].post(f"/api/v1/business-objects/{report['id']}/post-stock", headers=shop["headers"])
    assert twice.status_code == 409, "once — a correction is a counter-document"
    read = shop["client"].get(f"/api/v1/business-objects/{report['id']}", headers=shop["headers"]).json()["data"]
    assert read["payload"]["stock_posted_at"]


def test_a_type_without_a_stock_effect_posts_nothing(shop) -> None:
    shop["post"]("/object-type-definitions", {"object_type": "memo", "json_schema": {}})
    memo = shop["post"]("/business-objects", {"object_type": "memo", "title": "note",
                                              "payload": {"lines": [{"inventory_item_id": shop["item"],
                                                                     "quantity_on_hand_diff": -1}]}})
    refused = shop["client"].post(f"/api/v1/business-objects/{memo['id']}/post-stock", headers=shop["headers"])
    assert refused.status_code == 422 and "stock_effect" in refused.json()["detail"]
    bad = shop["client"].post("/api/v1/object-type-definitions", headers=shop["headers"], json={
        "object_type": "hold_slip", "state_machine": {
            "initial": "open", "states": ["open"], "transitions": {"open": []},
            "stock_effect": {"reason": "reserved", "state": "open"}}})
    assert bad.status_code == 422, "the reservation pair belongs to the order bridge"


def test_receiving_stamps_the_purchase_order_header(shop) -> None:
    """The line stays in the pair — it is the precise cause — and the header
    FK is what makes "every movement this order caused" one indexed query."""
    vendor = shop["post"]("/vendors", {"name": "Dell"})["id"]
    po = shop["post"]("/purchase-orders", {
        "employee_id": shop["employee"], "vendor_id": vendor, "title": "stock po",
        "items": [{"product_id": shop["product"], "quantity": 5, "unit_price": 10.0}]})
    po_item = shop["client"].get(
        f"/api/v1/purchase-order-items?po_id={po['id']}",
        headers=shop["headers"]).json()["data"][0]

    received = shop["client"].post(
        f"/api/v1/purchase-orders/{po['id']}/receive", headers=shop["headers"],
        json={"lines": [{"po_item_id": po_item["id"], "quantity": 5,
                         "facility": "main"}]})
    assert received.status_code in (200, 201), received.text

    rows = shop["client"].get(
        f"/api/v1/inventory-item-details?purchase_order_id={po['id']}",
        headers=shop["headers"]).json()["data"]
    assert len(rows) == 1, "the receiving movement must carry the header FK"
    assert rows[0]["entity_type"] == "purchase_order_item"
    assert rows[0]["entity_id"] == po_item["id"]
