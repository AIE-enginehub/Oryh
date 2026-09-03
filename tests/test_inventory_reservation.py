"""Reservations: 占货 is an availability fact, not a movement.

When an order lands and the goods must be held, the ledger gains an
ATP-only row — `reserved`, available drops, on-hand stays, and the row
names WHOSE goods are held. When the goods actually leave, post-stock
consumes the hold in the same posting: a `reservation_released` row gives
the availability back and the `issued` row takes both sums down — so ATP
is never deducted twice for stock already promised away, and at rest the
two sums agree again. A cancelled order releases by hand; shipping
without a hold still moves both sums together, because a small shop that
never reserves must not be punished for it.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def stockroom():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Hold Co", email="admin@hold.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "店长"},
                          headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Cup"},
                              headers=admin).json()["data"]["id"]
        position = client.post("/api/v1/inventory-items", headers=admin, json={
            "product_id": product, "facility": "main", "initial_quantity": 10,
        }).json()["data"]["id"]

        def order(title="一单") -> str:
            return client.post("/api/v1/sales-orders", headers=admin, json={
                "employee_id": emp, "title": title}).json()["data"]["id"]

        def sums() -> tuple[float, float]:
            data = client.get(f"/api/v1/inventory-items/{position}",
                              headers=admin).json()["data"]
            return float(data["quantity_on_hand"]), float(data["available_to_promise"])

        def reserve(order_id: str, qty: float, **overrides) -> object:
            body = {"inventory_item_id": position, "quantity_on_hand_diff": 0,
                    "available_to_promise_diff": -qty, "reason": "reserved",
                    "sales_order_id": order_id, **overrides}
            return client.post("/api/v1/inventory-item-details", headers=admin, json=body)

        yield {"client": client, "admin": admin, "product": product,
               "position": position, "order": order, "sums": sums, "reserve": reserve}


def test_a_hold_moves_availability_only_and_names_its_order(stockroom) -> None:
    so = stockroom["order"]()
    ok = stockroom["reserve"](so, 3)
    assert ok.status_code == 201, ok.text
    assert stockroom["sums"]() == (10.0, 7.0), "占货: available drops, on-hand stays"

    moved_goods = stockroom["reserve"](so, 2, quantity_on_hand_diff=-2)
    assert moved_goods.status_code == 422, "goods that actually moved are issued, not reserved"
    backwards = stockroom["reserve"](so, -2)
    assert backwards.status_code == 422
    anonymous = stockroom["reserve"](so, 2, sales_order_id=None)
    assert anonymous.status_code == 422, "a hold must say whose it is, or nothing can consume it"


def test_shipping_a_held_order_consumes_the_hold_not_atp_twice(stockroom) -> None:
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]()
    stockroom["reserve"](so, 3)

    shipment = client.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": so,
        "items": [{"product_id": stockroom["product"], "quantity": 3,
                   "inventory_item_id": stockroom["position"]}]}).json()["data"]
    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=admin)
    assert posted.status_code == 200, posted.text
    assert posted.json()["data"]["lines"][0]["reservation_released"] == 3.0

    assert stockroom["sums"]() == (7.0, 7.0), \
        "release + issue in one posting — ATP is not deducted twice"
    rows = client.get("/api/v1/inventory-item-details",
                      params={"sales_order_id": so},
                      headers=admin).json()["data"]
    reasons = sorted(r["reason"] for r in rows)
    assert reasons == ["issued", "reservation_released", "reserved"], \
        "the ledger tells the whole story: held, consumed, gone"


def test_shipping_without_a_hold_moves_both_sums_together(stockroom) -> None:
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]()
    shipment = client.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": so,
        "items": [{"product_id": stockroom["product"], "quantity": 2,
                   "inventory_item_id": stockroom["position"]}]}).json()["data"]
    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=admin)
    assert posted.json()["data"]["lines"][0]["reservation_released"] is None
    assert stockroom["sums"]() == (8.0, 8.0), \
        "a shop that never reserves is not punished for it"


def test_a_partial_hold_releases_what_it_held_and_no_more(stockroom) -> None:
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]()
    stockroom["reserve"](so, 2)
    shipment = client.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": so,
        "items": [{"product_id": stockroom["product"], "quantity": 5,
                   "inventory_item_id": stockroom["position"]}]}).json()["data"]
    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=admin)
    assert posted.json()["data"]["lines"][0]["reservation_released"] == 2.0
    assert stockroom["sums"]() == (5.0, 5.0), \
        "the unheld three came out of open availability; the held two out of the hold"


def test_a_second_shipment_consumes_only_what_the_hold_still_holds(stockroom) -> None:
    """One hold, two parcels. The outstanding hold is the reserved/released
    PAIR's sum — a derivation that forgot the releases would hand the same
    hold out twice and quietly inflate availability."""
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]()
    stockroom["reserve"](so, 3)

    def ship(qty: float) -> dict:
        shipment = client.post("/api/v1/shipments", headers=admin, json={
            "direction": "outbound", "sales_order_id": so,
            "items": [{"product_id": stockroom["product"], "quantity": qty,
                       "inventory_item_id": stockroom["position"]}]}).json()["data"]
        return client.post(f"/api/v1/shipments/{shipment['id']}/post-stock",
                           headers=admin).json()["data"]["lines"][0]

    assert ship(2)["reservation_released"] == 2.0
    assert stockroom["sums"]() == (8.0, 7.0), "one unit still held after the first parcel"
    assert ship(2)["reservation_released"] == 1.0, \
        "the second parcel consumes the REMAINING one, never the original three"
    assert stockroom["sums"]() == (6.0, 6.0), "at rest the two sums agree again"


def test_a_cancelled_order_gives_its_hold_back_by_hand(stockroom) -> None:
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]("要取消的单")
    stockroom["reserve"](so, 4)
    assert stockroom["sums"]() == (10.0, 6.0)
    released = client.post("/api/v1/inventory-item-details", headers=admin, json={
        "inventory_item_id": stockroom["position"], "quantity_on_hand_diff": 0,
        "available_to_promise_diff": 4, "reason": "reservation_released",
        "sales_order_id": so, "description": "订单取消,释放占货"})
    assert released.status_code == 201, released.text
    assert stockroom["sums"]() == (10.0, 10.0), "the hold came back, nothing moved"


def test_two_lines_on_one_position_split_one_hold_inside_a_posting(stockroom) -> None:
    """One hold, one parcel, two lines from the same shelf. The hold is
    drawn down line by line WITHIN the posting — a derivation that read the
    outstanding hold once per line would hand it out twice."""
    client, admin = stockroom["client"], stockroom["admin"]
    so = stockroom["order"]()
    stockroom["reserve"](so, 8)
    assert stockroom["sums"]() == (10.0, 2.0)
    shipment = client.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": so,
        "items": [{"product_id": stockroom["product"], "quantity": 5,
                   "inventory_item_id": stockroom["position"]},
                  {"product_id": stockroom["product"], "quantity": 5,
                   "inventory_item_id": stockroom["position"]}]}).json()["data"]
    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=admin)
    assert posted.status_code == 200, posted.text
    assert [line["reservation_released"] for line in posted.json()["data"]["lines"]] == [5.0, 3.0], \
        "the second line consumes what the first left, never the whole hold again"
    assert stockroom["sums"]() == (0.0, 0.0), "at rest the two sums agree again"
