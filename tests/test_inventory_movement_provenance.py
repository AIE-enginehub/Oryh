"""A stock movement names the order it fulfils — in the shape the order has.

Three worlds, three shapes. One of OUR orders is a closed document chain, so
it gets a real foreign key — a bare uuid can point at an order that does not
exist, and only the API would ever notice. Any other in-system record keeps
the generic (entity_type, entity_id) pair. And an EXTERNAL order — a workspace
that runs only inventory here, fulfilling Tmall or JD — goes in
`custom_fields`: its number is not a uuid, so the pair cannot even hold it,
and a foreign system's reference is a claim this database cannot check.
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


def movement(shop, **extra):
    body = {"inventory_item_id": shop["item"], "quantity_on_hand_diff": -1,
            "reason": "issued"}
    body.update(extra)
    return shop["client"].post("/api/v1/inventory-item-details", json=body,
                               headers=shop["headers"])


def test_an_external_order_number_cannot_even_enter_the_uuid_pair(shop) -> None:
    """The fact the design rests on, pinned so nobody 'fixes' it by loosening
    the column: entity_id promises resolvability, and a Tmall number is a
    claim this database cannot check."""
    refused = movement(shop, entity_type="tmall_order", entity_id="TM2026082112345")
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert "custom_fields" in str(detail), (
        "the refusal must say where the reference DOES go — before this check "
        "it was a 500 from the ValueError inside the uuid column type"
    )


def test_an_external_order_lives_in_custom_fields(shop) -> None:
    posted = movement(shop, custom_fields={"source": "tmall",
                                           "order_no": "TM2026082112345"})
    assert posted.status_code == 201, posted.text
    row = posted.json()["data"]
    assert row["custom_fields"] == {"source": "tmall", "order_no": "TM2026082112345"}
    assert row["sales_order_id"] is None and row["purchase_order_id"] is None


def test_a_movement_may_name_our_sales_order(shop) -> None:
    customer = shop["post"]("/customers", {"name": "Acme"})["id"]
    order = shop["post"]("/sales-orders", {
        "employee_id": shop["employee"], "customer_id": customer, "title": "one order"})
    posted = movement(shop, sales_order_id=order["id"])
    assert posted.status_code == 201, posted.text
    assert posted.json()["data"]["sales_order_id"] == order["id"]

    listed = shop["client"].get(
        f"/api/v1/inventory-item-details?sales_order_id={order['id']}",
        headers=shop["headers"]).json()["data"]
    assert [r["sales_order_id"] for r in listed] == [order["id"]]


def test_at_most_one_of_our_orders(shop) -> None:
    """Two at once is not a transfer — it is two movements."""
    customer = shop["post"]("/customers", {"name": "Acme"})["id"]
    vendor = shop["post"]("/vendors", {"name": "Dell"})["id"]
    so = shop["post"]("/sales-orders", {
        "employee_id": shop["employee"], "customer_id": customer, "title": "so"})
    po = shop["post"]("/purchase-orders", {
        "employee_id": shop["employee"], "vendor_id": vendor, "title": "po"})
    refused = movement(shop, sales_order_id=so["id"], purchase_order_id=po["id"])
    assert refused.status_code == 422, refused.text
    assert "at most one order" in refused.json()["detail"]


def test_a_named_order_must_exist_in_this_workspace(shop) -> None:
    """The FK's whole argument: a bare uuid can point at an order that does
    not exist, and only the API would ever notice. So the API notices."""
    refused = movement(shop, sales_order_id="00000000-0000-0000-0000-000000000000")
    assert refused.status_code == 404, refused.text


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


def test_reality_is_recordable_without_any_document(shop) -> None:
    """The substrate guarantee the whole warehouse doctrine stands on.

    The messiest part of every ERP is a stock ledger that demands a document
    the world did not produce — so the keeper stops recording, and the count
    becomes fiction. Here a movement needs a reason, a quantity and words,
    never a document. This pins that: a future validation-tightening change
    that makes any provenance field required reintroduces the disease, and
    must fail loudly here rather than quietly in a warehouse.
    """
    bare = movement(
        shop,
        quantity_on_hand_diff=1,
        reason="received",
        description="courier box, one carton, no PO known — sender label says "
                    "Shenzhen; tracking in custom_fields",
        custom_fields={"tracking_no": "SF1234567890"},
    )
    assert bare.status_code == 201, bare.text
    row = bare.json()["data"]
    assert row["sales_order_id"] is None
    assert row["purchase_order_id"] is None
    assert row["entity_type"] is None and row["entity_id"] is None
    assert "no PO known" in row["description"]
