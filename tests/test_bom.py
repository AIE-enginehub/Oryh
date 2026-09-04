"""Materials and bills of materials: one products table, one closed axis.

What is pinned: `product_type` is the closed manufacturing role (an unknown
value is refused; existing rows read as finished goods); a recipe is built
for a finished or semi-finished good only and is made of goods only (never
a service, never the parent, never anything upstream of it — one walk down
the derived tree refuses the loop); ONE active recipe per product, with
activation archiving the old in the same write; lines change only while
draft, because an active recipe is what the floor builds to; and the
explode read derives multi-level requirements — output ratio and scrap
folded in, leaves summed — with ATP and shortage when asked, so the agent
decides what to buy and the server stores no plan.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def workshop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Make Co", email="admin@make.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        member = invite_member(client, admin, "nobody", [])

        def product(name: str, kind: str = "finished_good") -> str:
            r = client.post("/api/v1/products", headers=admin,
                            json={"name": name, "product_type": kind})
            assert r.status_code == 201, r.text
            return r.json()["data"]["id"]

        def bom(product_id: str, items: list[dict], **extra) -> dict:
            r = client.post("/api/v1/bills-of-materials", headers=admin,
                            json={"product_id": product_id, "items": items, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member,
               "product": product, "bom": bom}


def test_the_manufacturing_role_is_a_closed_axis(workshop) -> None:
    client, admin = workshop["client"], workshop["admin"]
    plain = client.post("/api/v1/products", headers=admin, json={"name": "杯子"}).json()["data"]
    assert plain["product_type"] == "finished_good", "what a catalog held before it knew the word"
    bent = client.post("/api/v1/products", headers=admin,
                       json={"name": "怪物", "product_type": "widget"})
    assert bent.status_code == 422
    steel = workshop["product"]("钢板", "raw_material")
    listed = client.get("/api/v1/products", headers=workshop["member"],
                        params={"product_type": "raw_material"}).json()["data"]
    assert [r["id"] for r in listed] == [steel]


def test_a_recipe_is_for_a_made_good_and_made_of_goods(workshop) -> None:
    client, admin = workshop["client"], workshop["admin"]
    steel = workshop["product"]("钢板", "raw_material")
    polish = workshop["product"]("抛光服务", "service")
    valve = workshop["product"]("阀门")

    for_a_material = client.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": steel, "items": []})
    assert for_a_material.status_code == 422, "a raw material is not made"
    of_a_service = client.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": valve,
        "items": [{"component_product_id": polish, "quantity": 1}]})
    assert of_a_service.status_code == 422, "a recipe is made of goods"
    of_itself = client.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": valve,
        "items": [{"component_product_id": valve, "quantity": 1}]})
    assert of_itself.status_code == 422

    refused = client.post("/api/v1/bills-of-materials", headers=workshop["member"], json={
        "product_id": valve, "items": []})
    assert refused.status_code == 403, "recipes are catalog work"


def test_one_active_recipe_and_lines_frozen_once_active(workshop) -> None:
    client, admin = workshop["client"], workshop["admin"]
    steel = workshop["product"]("钢板", "raw_material")
    valve = workshop["product"]("阀门")
    v1 = workshop["bom"](valve, [{"component_product_id": steel, "quantity": 2}],
                         version="v1", status="active")
    frozen = client.post("/api/v1/bom-items", headers=admin, json={
        "bom_id": v1["id"], "component_product_id": steel, "quantity": 1})
    assert frozen.status_code == 409, "an active recipe is what the floor builds to"

    v2 = workshop["bom"](valve, [{"component_product_id": steel, "quantity": 1.5}], version="v2")
    assert v2["status"] == "draft"
    added = client.post("/api/v1/bom-items", headers=admin, json={
        "bom_id": v2["id"], "component_product_id": steel, "quantity": 0.5,
        "description": "垫片料"})
    assert added.status_code == 201, "draft lines are open"

    activated = client.patch(f"/api/v1/bills-of-materials/{v2['id']}", headers=admin,
                             json={"status": "active"})
    assert activated.status_code == 200, activated.text
    statuses = {r["version"]: r["status"] for r in client.get(
        "/api/v1/bills-of-materials", headers=admin,
        params={"product_id": valve, "status": "all"}).json()["data"]}
    assert statuses == {"v1": "archived", "v2": "active"}, \
        "activating the new version archives the old in the same write"


def test_a_recipe_cannot_contain_its_own_ancestor(workshop) -> None:
    client, admin = workshop["client"], workshop["admin"]
    bolt = workshop["product"]("螺栓", "semi_finished")
    body = workshop["product"]("阀体", "semi_finished")
    valve = workshop["product"]("阀门")
    workshop["bom"](valve, [{"component_product_id": body, "quantity": 1}], status="active")
    workshop["bom"](body, [{"component_product_id": bolt, "quantity": 4}], status="active")
    looped = client.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": bolt, "status": "active",
        "items": [{"component_product_id": valve, "quantity": 1}]})
    assert looped.status_code == 422, looped.text
    assert "ancestor" in looped.json()["detail"]


def test_explode_derives_the_multilevel_requirement_and_the_shortage(workshop) -> None:
    client, admin = workshop["client"], workshop["admin"]
    steel = workshop["product"]("钢板", "raw_material")
    rubber = workshop["product"]("橡胶", "raw_material")
    body = workshop["product"]("阀体", "semi_finished")
    valve = workshop["product"]("阀门")
    # per 10 bodies: 25 kg steel with 4% scrap
    workshop["bom"](body, [{"component_product_id": steel, "quantity": 25, "unit": "kg",
                            "scrap_rate": 4}], output_quantity=10, status="active")
    # per valve: 1 body + 0.2 kg rubber
    recipe = workshop["bom"](valve, [
        {"component_product_id": body, "quantity": 1},
        {"component_product_id": rubber, "quantity": 0.2, "unit": "kg"},
    ], status="active")
    client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": steel, "facility": "main", "initial_quantity": 100})

    exploded = client.get(f"/api/v1/bills-of-materials/{recipe['id']}/explode",
                          headers=workshop["member"],
                          params={"quantity": 40, "with_stock": True})
    assert exploded.status_code == 200, exploded.text
    data = exploded.json()["data"]
    by_level = {(row["level"], row["component_product_id"]): row for row in data["lines"]}
    assert by_level[(1, body)]["required_quantity"] == 40.0 and by_level[(1, body)]["has_bom"]
    # 40 bodies / output 10 = ratio 4 → 25 kg × 4 × 1.04 = 104 kg steel
    assert by_level[(2, steel)]["required_quantity"] == 104.0, \
        "output ratio and scrap folded in, one level down"
    leaves = {leaf["product_id"]: leaf for leaf in data["leaf_requirements"]}
    assert set(leaves) == {steel, rubber}, "a sub-assembly is not a leaf — its materials are"
    assert leaves[rubber]["required_quantity"] == 8.0
    assert leaves[steel]["available_to_promise"] == 100.0 and leaves[steel]["shortage"] == 4.0, \
        "the server hands over the gap; buying is the agent's decision"
    assert leaves[rubber]["shortage"] == 8.0
