"""Inventory: items are running sums of an append-only detail ledger.

The behaviours worth pinning: totals never move except through a detail; the
stock-take import records a differing count as an `import_override` movement
naming both numbers instead of editing the item; re-running the same count is
a no-op; details are immutable.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_inventory.json').read_text(encoding="utf-8"))


from fastapi.testclient import TestClient

from conftest import admin_headers, create


def provision(client: TestClient) -> dict[str, str]:
    return admin_headers(client, company_name="Stock Co", email="admin@stock-co.example", password="admin-pass1")


def create_product(client: TestClient, headers, code: str, name: str = _ZH_TEXT['TEXT_C7005F6AFFA067C1']) -> str:
    return create(client, headers, "products", product_code=code, name=name)["id"]


def bulk(client: TestClient, headers, rows, **options) -> dict:
    response = client.post(
        "/api/v1/inventory-items/bulk", json={"rows": rows, **options}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def details_of(client: TestClient, headers, item_id: str) -> list[dict]:
    return client.get(
        f"/api/v1/inventory-item-details?inventory_item_id={item_id}", headers=headers
    ).json()["data"]


# --- ledger discipline ------------------------------------------------------


def test_item_totals_move_only_through_details(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers, "P-001")

    created = client.post(
        "/api/v1/inventory-items",
        json={"product_id": product_id, "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "initial_quantity": 100,
              "initial_description": _ZH_TEXT['TEXT_3773B5A1DDD160D7']},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["quantity_on_hand"] == 100 and item["available_to_promise"] == 100
    assert item["product_code"] == "P-001"

    ledger = details_of(client, headers, item["id"])
    assert len(ledger) == 1 and ledger[0]["reason"] == "initial"

    # movement: an outbound leg issues 30 when it posts; atp follows qoh
    leg = client.post(
        "/api/v1/shipments",
        json={"direction": "outbound", "items": [
            {"product_id": product_id, "quantity": 30, "inventory_item_id": item["id"]}]},
        headers=headers,
    )
    assert leg.status_code == 201, leg.text
    issued = client.post(f"/api/v1/shipments/{leg.json()['data']['id']}/post-stock", headers=headers)
    assert issued.status_code == 200, issued.text
    after = client.get(f"/api/v1/inventory-items/{item['id']}", headers=headers).json()["data"]
    assert after["quantity_on_hand"] == 70 and after["available_to_promise"] == 70

    # the item's totals always equal the ledger sum
    ledger = details_of(client, headers, item["id"])
    assert sum(d["quantity_on_hand_diff"] for d in ledger) == after["quantity_on_hand"]

    # PATCHing a quantity is rejected by name — no back door into the totals
    poked = client.patch(
        f"/api/v1/inventory-items/{item['id']}",
        json={"quantity_on_hand": 999},
        headers=headers,
    )
    assert poked.status_code == 422
    assert "quantity_on_hand" in poked.text


def test_details_are_immutable(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers, "P-002")
    item = client.post(
        "/api/v1/inventory-items",
        json={"product_id": product_id, "initial_quantity": 10},
        headers=headers,
    ).json()["data"]
    detail_id = details_of(client, headers, item["id"])[0]["id"]

    # the ledger has no per-row path at all — no GET-one, no PATCH, no DELETE
    assert client.patch(
        f"/api/v1/inventory-item-details/{detail_id}", json={"description": "x"}, headers=headers
    ).status_code == 404
    assert client.delete(
        f"/api/v1/inventory-item-details/{detail_id}", headers=headers
    ).status_code == 404


def test_archived_item_rejects_movement(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers, "P-003")
    item = client.post(
        "/api/v1/inventory-items", json={"product_id": product_id, "initial_quantity": 5}, headers=headers
    ).json()["data"]
    leg = client.post(
        "/api/v1/shipments",
        json={"direction": "inbound", "items": [
            {"product_id": product_id, "quantity": 1, "inventory_item_id": item["id"]}]},
        headers=headers,
    ).json()["data"]
    assert client.delete(f"/api/v1/inventory-items/{item['id']}", headers=headers).status_code == 204
    blocked = client.post(f"/api/v1/shipments/{leg['id']}/post-stock", headers=headers)
    assert blocked.status_code == 409


def test_one_item_per_stock_position(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers, "P-004")
    first = client.post(
        "/api/v1/inventory-items", json={"product_id": product_id, "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F']}, headers=headers
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/v1/inventory-items", json={"product_id": product_id, "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F']}, headers=headers
    )
    assert duplicate.status_code == 409
    assert first.json()["data"]["id"] in duplicate.json()["detail"]
    # a different facility is a different position
    other = client.post(
        "/api/v1/inventory-items", json={"product_id": product_id, "facility": _ZH_TEXT['TEXT_AE9893B10D866BB8']}, headers=headers
    )
    assert other.status_code == 201


# --- the stock-take import --------------------------------------------------


def test_bulk_import_creates_then_overrides_via_ledger(client: TestClient) -> None:
    headers = provision(client)
    create_product(client, headers, "P-100", _ZH_TEXT['TEXT_ADFBE6F133AD4366'])
    create_product(client, headers, "P-101", _ZH_TEXT['TEXT_1B1AABCF1272E356'])

    rows = [
        {"product_code": "P-100", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "quantity": 120.5},
        {"product_code": "P-101", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "lot_id": "B2026-07", "quantity": 19.9},
    ]
    first = bulk(client, headers, rows)
    assert first["summary"]["created"] == 2

    items = {i["product_code"]: i for i in client.get("/api/v1/inventory-items", headers=headers).json()["data"]}
    assert items["P-100"]["quantity_on_hand"] == 120.5
    opening = details_of(client, headers, items["P-100"]["id"])
    assert [d["reason"] for d in opening] == ["import_initial"]

    # identical re-count → nothing moves, no ledger noise (float traps included)
    second = bulk(client, headers, rows)
    assert second["summary"] == {"total": 2, "created": 0, "updated": 0, "unchanged": 2, "failed": 0}, (
        second["results"]
    )
    assert len(details_of(client, headers, items["P-100"]["id"])) == 1

    # a differing count NEVER edits the item — it appends an import_override
    # detail carrying exactly (counted - system), naming both numbers
    rows[0]["quantity"] = 97
    third = bulk(client, headers, rows)
    moved = [r for r in third["results"] if r["outcome"] == "updated"][0]
    assert moved["changed"] == ["quantity_on_hand"]

    item = client.get(f"/api/v1/inventory-items/{items['P-100']['id']}", headers=headers).json()["data"]
    assert item["quantity_on_hand"] == 97
    ledger = details_of(client, headers, item["id"])
    assert len(ledger) == 2
    override = [d for d in ledger if d["reason"] == "import_override"][0]
    assert override["quantity_on_hand_diff"] == -23.5
    assert "120.5" in override["description"] and "97" in override["description"]
    assert _ZH_TEXT['TEXT_CB6E8FBE3F900093'] in override["description"]
    # ledger sum still IS the item total
    assert sum(d["quantity_on_hand_diff"] for d in ledger) == item["quantity_on_hand"]


def test_bulk_unknown_product_or_sku_is_a_row_error(client: TestClient) -> None:
    headers = provision(client)
    create_product(client, headers, "P-200", _ZH_TEXT['TEXT_F2BCFBB4C9DCE340'])
    report = bulk(client, headers, [
        {"product_code": "P-404", "quantity": 10},
        {"product_code": "P-200", "sku_code": "NO-SUCH", "quantity": 5},
        {"product_code": "P-200", "quantity": 5},
    ])
    assert report["applied"] is False and report["summary"]["failed"] == 2
    errors = {r["index"]: r["error"] for r in report["results"] if r["outcome"] == "error"}
    assert "P-404" in errors[0] and "NO-SUCH" in errors[1]
    # abort semantics: the good row did not land either
    assert client.get("/api/v1/inventory-items", headers=headers).json()["data"] == []


def test_bulk_duplicate_position_in_one_batch_is_an_error(client: TestClient) -> None:
    headers = provision(client)
    create_product(client, headers, "P-300", _ZH_TEXT['TEXT_88949D0EF051214C'])
    report = bulk(client, headers, [
        {"product_code": "P-300", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "quantity": 3},
        {"product_code": "P-300", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "quantity": 4},
    ])
    assert report["summary"]["failed"] == 1
    error = [r for r in report["results"] if r["outcome"] == "error"][0]
    assert error["index"] == 1 and "also row 0" in error["error"]


def test_bulk_dry_run_writes_nothing(client: TestClient) -> None:
    headers = provision(client)
    create_product(client, headers, "P-400", _ZH_TEXT['TEXT_03D1F94FF456E4BA'])
    preview = bulk(client, headers, [{"product_code": "P-400", "quantity": 50}], dry_run=True)
    assert preview["applied"] is False and preview["summary"]["created"] == 1
    assert client.get("/api/v1/inventory-items", headers=headers).json()["data"] == []
    assert client.get("/api/v1/inventory-item-details", headers=headers).json()["data"] == []


def test_bulk_sku_level_positions(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers, "P-500", _ZH_TEXT['TEXT_1B49AB0CB89BCCED'])
    sku = client.post(
        "/api/v1/product-skus",
        json={"product_id": product_id, "sku_code": "P-500-XL", "variant_attrs": {_ZH_TEXT['TEXT_4060F118DEA05D67']: "XL"}},
        headers=headers,
    ).json()["data"]

    report = bulk(client, headers, [
        {"product_code": "P-500", "sku_code": "P-500-XL", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "quantity": 40},
        {"product_code": "P-500", "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "quantity": 15},  # Product-level remainder
    ])
    assert report["summary"]["created"] == 2
    items = client.get(f"/api/v1/inventory-items?product_id={product_id}", headers=headers).json()["data"]
    by_sku = {i["sku_id"]: i["quantity_on_hand"] for i in items}
    assert by_sku[sku["id"]] == 40 and by_sku[None] == 15


def test_concurrent_movements_do_not_lose_one_another(stack) -> None:
    """The totals must move by a relative update the database computes, never
    by a number Python worked out from a value it read earlier.

    Two postings against one item both read the same starting total — under
    READ COMMITTED that is ordinary, not a race gone wrong. With an absolute
    write the second silently overwrites the first: both ledger rows survive,
    one movement vanishes from the total, and nothing errors. Receiving,
    issuing and stock-takes all hit the same item row, so this is where it
    would happen.
    """
    from sqlalchemy.orm import Session

    from app.models import InventoryItem
    from app.services.inventory_import import post_inventory_detail

    client, engine = stack
    headers = provision(client)
    product_id = create_product(client, headers, "P-RACE")
    item_id = client.post(
        "/api/v1/inventory-items",
        json={"product_id": product_id, "facility": _ZH_TEXT['TEXT_864B9E5CE5752E2F'], "initial_quantity": 10},
        headers=headers,
    ).json()["data"]["id"]

    # both sessions load the item BEFORE either writes — each now holds its own
    # copy saying 10, which is the whole setup for a lost update
    with Session(engine) as first, Session(engine) as second:
        item_a = first.get(InventoryItem, item_id)
        item_b = second.get(InventoryItem, item_id)
        assert float(item_a.quantity_on_hand) == float(item_b.quantity_on_hand) == 10

        post_inventory_detail(first, item=item_a, quantity_on_hand_diff=5, reason="received")
        first.commit()
        # `second` still believes 10. An absolute write would store 10 + 2 = 12
        # and the +5 would be gone.
        post_inventory_detail(second, item=item_b, quantity_on_hand_diff=2, reason="received")
        second.commit()

    ledger = details_of(client, headers, item_id)
    moved = sum(float(row["quantity_on_hand_diff"]) for row in ledger)
    item = client.get(f"/api/v1/inventory-items/{item_id}", headers=headers).json()["data"]

    assert moved == 17, [row["quantity_on_hand_diff"] for row in ledger]
    # the invariant the whole design rests on: the item is the sum of its ledger
    assert float(item["quantity_on_hand"]) == moved
    assert float(item["available_to_promise"]) == moved
