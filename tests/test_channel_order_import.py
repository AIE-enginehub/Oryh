"""Importing a Tmall order, the whole loop, with the credential that does it.

The person importing an export holds order.submit_own — not the catalog
desk's grant — and the loop is theirs end to end: dedup by the platform
order number, translate each line through the map (by title, because the
export carries titles), and when the map is silent, ask the catalog for
CANDIDATES ranked by the title's vocabulary, get the person's
confirmation, and record it as a title-keyed map row so the next import
skips the question. The order lands on its storefront and is linked to
the platform number; a second import of the same export finds the link
and the map and writes nothing new. What the import desk still cannot do
is create a product — the map is the boundary, not the catalog.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Tmall Co", email="admin@tmall-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        emp = client.post("/api/v1/employees", json={"name": "运营小李"},
                          headers=admin).json()["data"]["id"]
        ops = invite_member(client, admin, "channel_ops", ["order.submit_own"], employee_id=emp)

        store = client.post("/api/v1/stores", headers=admin, json={
            "name": "天猫旗舰店", "channel": "online", "source": "tmall"}).json()["data"]["id"]
        cup = client.post("/api/v1/products", headers=admin, json={
            "name": "保温杯 500ml", "product_code": "CUP-500", "spec": "樱花粉"}).json()["data"]["id"]
        client.post("/api/v1/products", headers=admin, json={
            "name": "保温杯 350ml", "product_code": "CUP-350"})
        client.post("/api/v1/products", headers=admin, json={
            "name": "登山杖", "product_code": "POLE-1"})
        # named with the words in the other order and no spaces: only a
        # vocabulary match (CJK bigrams) can see it inside a platform title
        thermos = client.post("/api/v1/products", headers=admin, json={
            "name": "樱花粉保温杯", "product_code": "CUP-PINK"}).json()["data"]["id"]

        nobody = invite_member(client, admin, "nobody", [])

        yield {"client": client, "admin": admin, "ops": ops, "nobody": nobody,
               "employee": emp, "store": store, "cup": cup, "thermos": thermos}


TITLE = "【官方旗舰】保温杯500ml樱花粉 便携随行杯"
ORDER_NO = "2039487651234"


def test_the_first_import_asks_the_catalog_and_records_the_answer(shop) -> None:
    client, ops = shop["client"], shop["ops"]

    # 1. dedup by the platform number — nothing yet
    seen = client.get("/api/v1/external-document-links", headers=ops,
                      params={"source": "tmall", "external_no": ORDER_NO}).json()["data"]
    assert seen == []

    # 2. the map is silent for this title
    mapped = client.get("/api/v1/external-product-maps", headers=ops,
                        params={"source": "tmall", "external_name": TITLE,
                                "at": "2026-09-01"}).json()["data"]
    assert mapped == []

    # 3. candidates, ranked — the 500ml cup first, the 350ml close behind,
    #    the walking pole nowhere
    candidates = client.get("/api/v1/product-matches", headers=ops,
                            params={"title": TITLE, "limit": 5})
    assert candidates.status_code == 200, candidates.text
    ranked = candidates.json()["data"]
    assert ranked[0]["id"] == shop["cup"] and ranked[0]["match_score"] > ranked[1]["match_score"]
    assert "登山杖" not in {r["name"] for r in ranked}
    assert shop["thermos"] in {r["id"] for r in ranked}, \
        "樱花粉保温杯 shares the title's vocabulary even with the words reordered and unspaced"

    # 4. the person confirms → the import desk records the title-keyed map
    recorded = client.post("/api/v1/external-product-maps", headers=ops, json={
        "source": "tmall", "external_name": TITLE, "product_id": shop["cup"], "quantity": 1})
    assert recorded.status_code == 201, "confirming a listing is the import desk's own act"

    # 5. the order lands on its storefront, linked to the platform number
    order = client.post("/api/v1/sales-orders", headers=ops, json={
        "employee_id": shop["employee"], "customer_name_snapshot": "淘宝买家",
        "store_id": shop["store"], "title": "天猫订单",
        "items": [{"line_no": 1, "product_id": shop["cup"], "quantity": 2, "unit_price": 99}],
    })
    assert order.status_code == 201, order.text
    linked = client.post("/api/v1/external-document-links", headers=ops, json={
        "source": "tmall", "external_kind": "order", "external_no": ORDER_NO,
        "entity_type": "sales_order", "entity_id": order.json()["data"]["id"]})
    assert linked.status_code == 201, linked.text

    # the boundary: the import desk curates the MAP, never the catalog —
    # and a credential that records nothing curates nothing
    forbidden = client.post("/api/v1/products", headers=ops, json={"name": "野货"})
    assert forbidden.status_code == 403
    whiteboard = client.post("/api/v1/external-product-maps", headers=shop["nobody"], json={
        "source": "tmall", "external_name": "乱写", "product_id": shop["cup"]})
    assert whiteboard.status_code == 403


def test_the_second_import_finds_the_map_and_the_link(shop) -> None:
    client, ops = shop["client"], shop["ops"]
    client.post("/api/v1/external-product-maps", headers=ops, json={
        "source": "tmall", "external_name": TITLE, "product_id": shop["cup"]})
    order = client.post("/api/v1/sales-orders", headers=ops, json={
        "employee_id": shop["employee"], "store_id": shop["store"], "title": "天猫订单",
        "items": [{"line_no": 1, "product_id": shop["cup"], "quantity": 2, "unit_price": 99}],
    }).json()["data"]
    client.post("/api/v1/external-document-links", headers=ops, json={
        "source": "tmall", "external_kind": "order", "external_no": ORDER_NO,
        "entity_type": "sales_order", "entity_id": order["id"]})

    # the export arrives again, its title re-spaced by a spreadsheet
    mapped = client.get("/api/v1/external-product-maps", headers=ops,
                        params={"source": "tmall",
                                "external_name": "【官方旗舰】保温杯500ml樱花粉　便携随行杯",
                                "at": "2026-09-02"}).json()["data"]
    assert [r["product_id"] for r in mapped] == [shop["cup"]], \
        "the confirmed answer is remembered; no question this time"
    seen = client.get("/api/v1/external-document-links", headers=ops,
                      params={"source": "tmall", "external_no": ORDER_NO}).json()["data"]
    assert [r["entity_id"] for r in seen] == [order["id"]], "the number is already ours"
    duplicate = client.post("/api/v1/external-document-links", headers=ops, json={
        "source": "tmall", "external_kind": "order", "external_no": ORDER_NO,
        "entity_type": "sales_order", "entity_id": order["id"]})
    assert duplicate.status_code == 409, "the server backs the agent's dedup"


def test_candidates_are_ranked_by_score_not_by_age(shop) -> None:
    """The shortlist's order is the score: a product filed later that
    matches the title better comes FIRST, or the person reads the wrong
    name at the top of every list."""
    client, admin, ops = shop["client"], shop["admin"], shop["ops"]
    exact = client.post("/api/v1/products", headers=admin, json={
        "name": "保温杯500ml樱花粉 便携随行杯", "product_code": "CUP-EXACT"}).json()["data"]["id"]
    ranked = client.get("/api/v1/product-matches", headers=ops,
                        params={"title": TITLE, "limit": 3}).json()["data"]
    assert ranked[0]["id"] == exact, "the newest product outranks the older partial matches"
    scores = [r["match_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
