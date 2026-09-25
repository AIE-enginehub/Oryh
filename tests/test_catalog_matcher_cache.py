"""`GET /product-matches` used to load and index the whole active catalog on
every call. The matcher is now kept per tenant and rebuilt only when the
catalog's fingerprint (count and newest change of products and SKUs) moves.
"""
from __future__ import annotations

from app.api import master_data
from conftest import make_client, provision_tenant


def test_the_matcher_is_reused_until_the_catalog_changes(monkeypatch) -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Match Co", email="admin@match.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        assert client.post("/api/v1/products", json={"name": "红丝带 14x17"}, headers=admin).status_code == 201
        master_data._MATCHERS.clear()
        builds = []
        real = master_data._CatalogMatcher

        class Counting(real):
            def __init__(self, db, tenant_id):
                builds.append(tenant_id)
                super().__init__(db, tenant_id)

        monkeypatch.setattr(master_data, "_CatalogMatcher", Counting)
        for _ in range(3):
            r = client.get("/api/v1/product-matches", params={"title": "红丝带"}, headers=admin)
            assert r.status_code == 200, r.text
        assert len(builds) == 1, "three questions, one catalog load"
        assert r.json()["data"][0]["name"].startswith("红丝带")

        assert client.post("/api/v1/products", json={"name": "蓝丝带"}, headers=admin).status_code == 201
        r = client.get("/api/v1/product-matches", params={"title": "蓝丝带"}, headers=admin)
        assert r.status_code == 200 and len(builds) == 2, "a new product is a new catalog"
        assert any(c["name"] == "蓝丝带" for c in r.json()["data"])
        master_data._MATCHERS.clear()
