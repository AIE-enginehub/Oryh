"""`GET /product-matches` used to load and index the whole active catalog on
every call. The matcher is now kept per tenant and rebuilt only when the
catalog's fingerprint (count and newest change of products and SKUs) moves.
"""
from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_catalog_matcher_cache.json').read_text(encoding="utf-8"))


from app.api import master_data
from conftest import make_client, provision_tenant


def test_the_matcher_is_reused_until_the_catalog_changes(monkeypatch) -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Match Co", email="admin@match.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        assert client.post("/api/v1/products", json={"name": _ZH_TEXT['TEXT_E26ACF32120269E9']}, headers=admin).status_code == 201
        master_data._MATCHERS.clear()
        builds = []
        real = master_data._CatalogMatcher

        class Counting(real):
            def __init__(self, db, tenant_id):
                builds.append(tenant_id)
                super().__init__(db, tenant_id)

        monkeypatch.setattr(master_data, "_CatalogMatcher", Counting)
        for _ in range(3):
            r = client.get("/api/v1/product-matches", params={"title": _ZH_TEXT['TEXT_A7F9703D0D8435D2']}, headers=admin)
            assert r.status_code == 200, r.text
        assert len(builds) == 1, "three questions, one catalog load"
        assert r.json()["data"][0]["name"].startswith(_ZH_TEXT['TEXT_A7F9703D0D8435D2'])

        assert client.post("/api/v1/products", json={"name": _ZH_TEXT['TEXT_7F92DD71CAA6052D']}, headers=admin).status_code == 201
        r = client.get("/api/v1/product-matches", params={"title": _ZH_TEXT['TEXT_7F92DD71CAA6052D']}, headers=admin)
        assert r.status_code == 200 and len(builds) == 2, "a new product is a new catalog"
        assert any(c["name"] == _ZH_TEXT['TEXT_7F92DD71CAA6052D'] for c in r.json()["data"])
        master_data._MATCHERS.clear()
