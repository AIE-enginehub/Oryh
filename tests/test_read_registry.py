"""Plain reads are declared, not hand-written (app/api/registry.py).

The migration's invariant was that the OpenAPI document did not change by a
byte; what keeps it true afterwards is here: every declaration's contract is
exactly what it says, in the order it says it, the hooks do what the handlers
they replaced did, and a migrated module does not quietly grow a copy-pasted
list handler again.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from conftest import make_client, provision_tenant

ROOT = pathlib.Path(__file__).resolve().parents[1]
# modules whose plain reads have been moved into declarations
MIGRATED = ("master_data.py",)


def _spec() -> dict:
    from app.main import app
    return app.openapi()


def test_every_declaration_is_the_contract_it_describes() -> None:
    import app.main  # noqa: F401  (registers the routes)
    from app.api.registry import REGISTRY, Filter, GetResource, ListResource, Param

    assert len(REGISTRY) >= 31
    paths = _spec()["paths"]
    for resource in REGISTRY:
        op = paths["/api/v1" + resource.path]["get"]
        assert op["operationId"].startswith(resource.name + "_"), resource.path
        query = [p["name"] for p in op.get("parameters", []) if p["in"] == "query"]
        if isinstance(resource, GetResource):
            assert query == [], resource.path
            assert [p["name"] for p in op["parameters"] if p["in"] == "path"] == [resource.id_param]
            continue
        assert isinstance(resource, ListResource)
        declared = [p.name if isinstance(p, (Filter, Param)) else p for p in resource.params]
        assert query[:len(declared)] == declared, f"{resource.path}: parameters in contract order"
        trailing = query[len(declared):]
        expected = [f"{c}_{edge}" for c in sorted(resource.ranges) for edge in ("from", "thru")] + sorted(resource.equals)
        assert sorted(trailing) == sorted(expected), f"{resource.path}: ranges and reference filters"


def test_a_migrated_module_keeps_no_plain_list_or_by_id_handler() -> None:
    """The shape the registry replaces: a GET whose whole body is
    `return list_rows(select(M).where(M.tenant_id == tenant_id), …)` or
    `get_scoped_or_404` + `envelope(Read.model_validate(row)…)`. Written by
    hand again, it is a second copy of a declaration."""
    offenders = []
    for name in MIGRATED:
        tree = ast.parse((ROOT / "app/api" / name).read_text())
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            if not any(isinstance(d, ast.Call) and ast.unparse(d.func) == "router.get" for d in fn.decorator_list):
                continue
            body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
            if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Call) \
                    and ast.unparse(body[0].value.func) == "list_rows" \
                    and ast.unparse(body[0].value.args[1]).endswith(".tenant_id == tenant_id)") \
                    and "render" not in {k.arg for k in body[0].value.keywords}:
                offenders.append(f"{name}: {fn.name}")
            if len(body) == 2 and isinstance(body[0], ast.Assign) and isinstance(body[1], ast.Return) \
                    and ast.unparse(body[0].value).startswith("get_scoped_or_404(db, ") \
                    and ".model_validate(" in ast.unparse(body[1].value) and ast.unparse(body[1].value).startswith("envelope("):
                offenders.append(f"{name}: {fn.name}")
    assert not offenders, "declare these in the module's register(...) block instead: " + ", ".join(offenders)


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Registry Co", email="admin@registry.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        yield client, admin


def test_a_declared_list_filters_searches_pages_and_hides_the_archived(shop) -> None:
    c, admin = shop
    ids = [c.post("/api/v1/vendors", headers=admin, json={"name": n, "tax_id": t}).json()["data"]["id"]
           for n, t in (("华东纸业", "T-1"), ("华南纸业", "T-2"), ("北方钢材", "T-3"))]
    c.patch(f"/api/v1/vendors/{ids[2]}", headers=admin, json={"status": "archived"})
    assert {v["id"] for v in c.get("/api/v1/vendors", headers=admin).json()["data"]} == set(ids[:2]), "active by default"
    assert len(c.get("/api/v1/vendors", headers=admin, params={"status": "all"}).json()["data"]) == 3
    assert [v["id"] for v in c.get("/api/v1/vendors", headers=admin, params={"keyword": "华东"}).json()["data"]] == [ids[0]]
    assert [v["id"] for v in c.get("/api/v1/vendors", headers=admin, params={"tax_id": "T-2"}).json()["data"]] == [ids[1]]
    paged = c.get("/api/v1/vendors", headers=admin, params={"page": 1, "size": 1, "order_by": "name"}).json()
    assert paged["meta"]["total"] == 2 and len(paged["data"]) == 1
    assert c.get("/api/v1/vendors", headers=admin, params={"created_at_from": "2099-01-01T00:00:00Z"}).json()["data"] == []
    assert c.get("/api/v1/vendors", headers=admin, params={"nonsense": "x"}).status_code == 422
    assert c.get(f"/api/v1/vendors/{ids[0]}", headers=admin).json()["data"]["name"] == "华东纸业"
    assert c.get("/api/v1/vendors/not-a-uuid", headers=admin).status_code == 404


def test_the_hooks_do_what_the_handlers_did(shop) -> None:
    c, admin = shop
    root = c.post("/api/v1/product-categories", headers=admin, json={"name": "耗材", "category_code": "C1"}).json()["data"]["id"]
    c.post("/api/v1/product-categories", headers=admin, json={"name": "色带", "category_code": "C2", "parent_id": root})
    assert len(c.get("/api/v1/product-categories", headers=admin).json()["data"]) == 2
    only_roots = c.get("/api/v1/product-categories", headers=admin, params={"root_only": "true"}).json()["data"]
    assert [x["id"] for x in only_roots] == [root], "a flag parameter reaches the where hook"

    product = c.post("/api/v1/products", headers=admin, json={"name": "色带", "product_code": "RB-1"}).json()["data"]["id"]
    c.post("/api/v1/product-skus", headers=admin, json={"product_id": product, "sku_code": "RB-1-A"})
    listed = c.get("/api/v1/products", headers=admin).json()["data"][0]
    assert listed["has_skus"] is True, "the batch render still enriches list rows"
    assert c.get(f"/api/v1/products/{product}", headers=admin).json()["data"]["has_skus"] is True, "and the by-id read hook too"

    c.post("/api/v1/inventory-items", headers=admin, json={"product_id": product, "facility": "main", "initial_quantity": 1})
    c.post("/api/v1/inventory-items", headers=admin, json={"product_id": product, "facility": "", "initial_quantity": 1})
    assert len(c.get("/api/v1/inventory-items", headers=admin).json()["data"]) == 2
    nowhere = c.get("/api/v1/inventory-items", headers=admin, params={"facility": ""}).json()["data"]
    assert [x["facility"] for x in nowhere] == [""], 'facility="" is a position, not an absent filter'
