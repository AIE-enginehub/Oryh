"""Product categories: the catalog's shelving, and the product's pointer.

A tree with one parent per category. What is pinned: names are unique among
ACTIVE siblings only (same name under two parents is normal shelving,
archiving frees the slot); the tree cannot fold into itself (self-parent
and descendant moves are 422 with the reason); products file onto active
shelves only, and archiving a shelf strands neither its children nor its
products — the pointer is history, not a cascade; the bulk import joins
rows to the tree by category_code and refuses to invent a category, the
vendor doctrine again.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def shelving():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Shelf Co", email="admin@shelf.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        member = invite_member(client, admin, "nobody", [])

        def shelf(name: str, **extra) -> dict:
            r = client.post("/api/v1/product-categories", headers=admin,
                            json={"name": name, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member, "shelf": shelf}


def test_names_are_unique_among_active_siblings_only(shelving) -> None:
    client, admin = shelving["client"], shelving["admin"]
    valves = shelving["shelf"]("阀门", category_code="CAT-VALVE")
    fittings = shelving["shelf"]("管件")

    doubled = client.post("/api/v1/product-categories", headers=admin, json={"name": "阀门"})
    assert doubled.status_code == 409, "two live folders with one name at one level"

    ball_a = shelving["shelf"]("配件", parent_id=valves["id"])
    assert ball_a["parent_name"] == "阀门", "reads say where a shelf sits without a second query"
    ball_b = shelving["shelf"]("配件", parent_id=fittings["id"])
    assert ball_b["id"] != ball_a["id"], "the same name under two parents is normal shelving"

    client.delete(f"/api/v1/product-categories/{ball_a['id']}", headers=admin)
    revived_slot = client.post("/api/v1/product-categories", headers=admin,
                               json={"name": "配件", "parent_id": valves["id"]})
    assert revived_slot.status_code == 201, "archiving frees the name — the old row is history"

    listed = client.get("/api/v1/product-categories", headers=shelving["member"],
                        params={"root_only": True, "status": "active"})
    assert listed.status_code == 200, "the shelving is master data — everyone reads it"
    assert {row["name"] for row in listed.json()["data"]} == {"阀门", "管件"}

    refused = client.post("/api/v1/product-categories", headers=shelving["member"],
                          json={"name": "私货"})
    assert refused.status_code == 403, "shelving is catalog work"


def test_the_tree_cannot_fold_into_itself(shelving) -> None:
    client, admin = shelving["client"], shelving["admin"]
    root = shelving["shelf"]("阀门")
    child = shelving["shelf"]("球阀", parent_id=root["id"])
    grandchild = shelving["shelf"]("不锈钢球阀", parent_id=child["id"])

    own_parent = client.patch(f"/api/v1/product-categories/{root['id']}",
                              headers=admin, json={"parent_id": root["id"]})
    assert own_parent.status_code == 422
    looped = client.patch(f"/api/v1/product-categories/{root['id']}",
                          headers=admin, json={"parent_id": grandchild["id"]})
    assert looped.status_code == 422, "moving a category under its own descendant closes a loop"

    client.delete(f"/api/v1/product-categories/{child['id']}", headers=admin)
    onto_archived = client.post("/api/v1/product-categories", headers=admin,
                                json={"name": "新货架", "parent_id": child["id"]})
    assert onto_archived.status_code == 409, "an archived shelf names its fix: revive first"


def test_products_file_onto_active_shelves_only(shelving) -> None:
    client, admin = shelving["client"], shelving["admin"]
    valves = shelving["shelf"]("阀门")
    retired = shelving["shelf"]("停产线")
    client.delete(f"/api/v1/product-categories/{retired['id']}", headers=admin)

    onto_archived = client.post("/api/v1/products", headers=admin, json={
        "name": "老阀门", "category_id": retired["id"]})
    assert onto_archived.status_code == 409

    made = client.post("/api/v1/products", headers=admin, json={
        "name": "工业阀门DN50", "category_id": valves["id"]})
    assert made.status_code == 201, made.text
    product = made.json()["data"]
    assert product["category_name"] == "阀门"

    filtered = client.get("/api/v1/products", headers=admin,
                          params={"category_id": valves["id"]})
    assert [r["id"] for r in filtered.json()["data"]] == [product["id"]]

    # archiving the shelf strands nothing: the product keeps its pointer
    client.delete(f"/api/v1/product-categories/{valves['id']}", headers=admin)
    still = client.get(f"/api/v1/products/{product['id']}", headers=admin).json()["data"]
    assert still["category_id"] == valves["id"], "the pointer is history, not a cascade"
    moved = client.patch(f"/api/v1/products/{product['id']}", headers=admin,
                         json={"category_id": retired["id"]})
    assert moved.status_code == 409, "…but new filing onto an archived shelf is refused"


def test_the_bulk_import_joins_by_code_and_never_invents_a_shelf(shelving) -> None:
    client, admin = shelving["client"], shelving["admin"]
    shelving["shelf"]("阀门", category_code="CAT-VALVE")

    run = client.post("/api/v1/products/bulk", headers=admin, json={"rows": [
        {"product_code": "P-1", "name": "球阀", "category_code": "CAT-VALVE"},
        {"product_code": "P-2", "name": "野货", "category_code": "CAT-GHOST"},
    ], "on_error": "skip"})
    assert run.status_code == 200, run.text
    results = {r["code"]: r for r in run.json()["data"]["results"]}
    assert results["P-1"]["outcome"] == "created"
    assert results["P-2"]["outcome"] == "error"
    assert "never invent one" in results["P-2"]["error"]

    filed = client.get("/api/v1/products", headers=admin,
                       params={"keyword": "P-1"}).json()["data"][0]
    assert filed["category_name"] == "阀门", "category_code joined the row to the tree"

    cleared = client.post("/api/v1/products/bulk", headers=admin, json={"rows": [
        {"product_code": "P-1", "name": "球阀", "category_code": None},
    ]})
    assert cleared.status_code == 200, cleared.text
    unfiled = client.get("/api/v1/products", headers=admin,
                         params={"keyword": "P-1"}).json()["data"][0]
    assert unfiled["category_id"] is None, "explicit null takes the product off the shelf"
