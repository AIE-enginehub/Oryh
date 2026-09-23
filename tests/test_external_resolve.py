"""A whole import's listings are translated in one call.

An order file names a hundred listings and the translation query answered
one: a hundred turns for the agent, and for every unmapped title
`/product-matches` loaded and compared the entire catalog again.
`POST /external-product-maps/resolve` reads the map with one indexed query
and, with `with_candidates`, loads and indexes the catalog once for every
unmapped title together. It must answer each listing exactly as the
single-listing reads would.
"""

from __future__ import annotations

import time

import pytest

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Resolve Co", email="admin@resolve.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        client.post("/api/v1/sales-channels", headers=admin, json={
            "channel_code": "tmall", "name": "天猫", "channel_kind": "marketplace"})

        def product(name: str, code: str, spec: str | None = None) -> str:
            return client.post("/api/v1/products", headers=admin, json={
                "name": name, "product_code": code, **({"spec": spec} if spec else {})}).json()["data"]["id"]

        cup = product("保温杯", "CUP-500", "500ml")
        box = product("礼盒", "BOX-01")
        ribbon = product("医用胶片打印机色带", "RB-100")
        printer = product("医用胶片打印机", "PR-900")

        def pair(**body) -> dict:
            r = client.post("/api/v1/external-product-maps", headers=admin, json={"source": "tmall", **body})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        pair(external_product_id="TM-1", external_name="保温杯 500ML 官方正品", product_id=cup)
        # a bundle listing: two rows under one title, no platform id
        pair(external_name="保温杯礼盒装", product_id=cup)
        pair(external_name="保温杯礼盒装", product_id=box)
        # a listing that swapped products on 2026-07-01
        pair(external_product_id="TM-SWAP", product_id=printer, effective_to="2026-07-01")
        pair(external_product_id="TM-SWAP", product_id=ribbon, effective_from="2026-07-01")
        yield {"client": client, "admin": admin, "cup": cup, "box": box, "ribbon": ribbon, "printer": printer}


def _resolve(shop, **body):
    r = shop["client"].post("/api/v1/external-product-maps/resolve", headers=shop["admin"], json={"source": "Tmall", **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_one_call_answers_every_listing_in_order(shop) -> None:
    out = _resolve(shop, at="2026-09-01", listings=[
        {"external_product_id": "TM-1"},
        {"external_name": "保温杯礼盒装"},
        {"external_name": "保温杯　500ml 官方正品"},      # fullwidth space, other case: the same title
        {"external_name": "没人见过的商品"},
        {"external_product_id": "TM-404", "external_name": "保温杯 500ML 官方正品"},  # unknown id, known title — but that row is id-keyed
    ])
    data = out["data"]
    assert [d["index"] for d in data] == [0, 1, 2, 3, 4]
    assert [d["status"] for d in data] == ["mapped", "mapped", "mapped", "unmapped", "unmapped"]
    assert [m["product_id"] for m in data[0]["maps"]] == [shop["cup"]]
    assert sorted(m["product_id"] for m in data[1]["maps"]) == sorted([shop["cup"], shop["box"]]), "a bundle is several rows"
    assert out["meta"] == {"total": 5, "mapped": 3, "unmapped": 2}
    assert "candidates" not in data[3], "candidates are asked for, not volunteered"


def test_each_listing_is_answered_as_of_its_own_date(shop) -> None:
    data = _resolve(shop, at="2026-09-01", listings=[
        {"external_product_id": "TM-SWAP"},
        {"external_product_id": "TM-SWAP", "at": "2026-06-30"},
        {"external_product_id": "TM-SWAP", "at": "2026-07-01"},
    ])["data"]
    assert [[m["product_id"] for m in d["maps"]] for d in data] == [[shop["ribbon"]], [shop["printer"]], [shop["ribbon"]]], \
        "a file that spans a listing swap resolves each line on its own day; the boundary day is the newer meaning"
    undated = _resolve(shop, listings=[{"external_product_id": "TM-SWAP"}])["data"][0]
    assert len(undated["maps"]) == 2, "no date, no window test — the same as the list without `at`"


def test_the_batch_agrees_with_the_single_listing_read(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    listings = [
        {"external_product_id": "TM-1"}, {"external_name": "保温杯礼盒装"}, {"external_product_id": "TM-SWAP"},
        {"external_product_id": "TM-1", "external_name": "保温杯礼盒装"}, {"external_name": "nothing"},
    ]
    batch = _resolve(shop, at="2026-08-15", listings=listings)["data"]
    for listing, answer in zip(listings, batch):
        single = c.get("/api/v1/external-product-maps", headers=admin,
                       params={"source": "tmall", "at": "2026-08-15", **listing}).json()["data"]
        assert sorted(m["id"] for m in answer["maps"]) == sorted(m["id"] for m in single), listing


def test_unmapped_titles_come_back_with_the_same_shortlist_product_matches_gives(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    titles = ["医用胶片打印机色带 原装正品", "保温杯 新款", "zzz 完全无关"]
    out = _resolve(shop, with_candidates=True, candidate_limit=3,
                   listings=[{"external_name": t} for t in titles] + [{"external_product_id": "TM-1"}])["data"]
    for title, answer in zip(titles, out):
        single = c.get("/api/v1/product-matches", headers=admin, params={"title": title, "limit": 3}).json()["data"]
        assert [(x["id"], x["match_score"]) for x in answer["candidates"]] == [(x["id"], x["match_score"]) for x in single], title
    assert out[0]["candidates"][0]["id"] == shop["ribbon"], "the rare phrase decides: 色带 names the ribbon, not the printer"
    assert out[2]["candidates"] == []
    assert "candidates" not in out[3], "a mapped listing needs no shortlist"


def test_it_is_a_read_bounded_and_strict(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    before = len(c.get("/api/v1/external-product-maps", headers=admin).json()["data"])
    _resolve(shop, with_candidates=True, listings=[{"external_name": "保温杯 新款"}])
    assert len(c.get("/api/v1/external-product-maps", headers=admin).json()["data"]) == before, "resolving confirms nothing"
    url = "/api/v1/external-product-maps/resolve"
    assert c.post(url, headers=admin, json={"source": "tmall", "listings": []}).status_code == 422
    assert c.post(url, headers=admin, json={"source": "tmall", "listings": [{}]}).status_code == 422, "a listing names an id or a title"
    assert c.post(url, headers=admin, json={"source": "tmall", "listings": [{"external_name": "x"}] * 501}).status_code == 422
    assert c.post(url, headers=admin, json={"source": "tmall", "listings": [{"external_name": "x", "title": "y"}]}).status_code == 422
    assert c.post(url, json={"source": "tmall", "listings": [{"external_name": "x"}]}).status_code == 401
    other = provision_tenant(c, company_name="Other Co", email="admin@other-resolve.example")
    theirs = c.post(url, headers={"X-API-Key": other["plain_text_api_key"]},
                    json={"source": "tmall", "listings": [{"external_product_id": "TM-1"}]}).json()["data"][0]
    assert theirs["status"] == "unmapped", "another tenant's map is not this tenant's answer"


def test_a_large_catalog_and_a_large_file_stay_one_fast_call() -> None:
    from app.models import ExternalProductMap, Product, normalize_external_name

    with make_client([]) as client:
        t = provision_tenant(client, company_name="Big Co", email="admin@big.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        tenant_id = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t['session_token']}"}).json()["data"]["tenant"]["id"] \
            if t.get("session_token") else None
        with client.session_factory() as db:
            if tenant_id is None:
                from app.models import Tenant
                tenant_id = db.query(Tenant).filter(Tenant.name == "Big Co").one().id
            from app.db.session import bind_tenant_context
            bind_tenant_context(db, tenant_id)
            families = ["保温杯", "打印机色带", "医用胶片", "蓝牙耳机", "办公椅", "显示器支架", "数据线", "机械键盘"]
            products = [Product(tenant_id=tenant_id, name=f"{families[i % 8]}{i:04d}型", product_code=f"P-{i:05d}",
                                spec=f"{100 + i % 50}x{200 + i % 30}", status="active") for i in range(3000)]
            db.add_all(products); db.flush()
            db.add_all([ExternalProductMap(tenant_id=tenant_id, source="tmall", external_product_id=f"TM-{i}",
                                           external_sku_id="", external_name=f"店铺标题 {i}",
                                           external_name_norm=normalize_external_name(f"店铺标题 {i}"),
                                           product_id=products[i % 3000].id, quantity=1, status="active")
                        for i in range(10000)])
            db.commit()
        listings = [{"external_product_id": f"TM-{i * 20}"} for i in range(400)] + \
                   [{"external_name": f"{families[i % 8]}{i * 7:04d}型 官方旗舰店 包邮"} for i in range(100)]
        started = time.perf_counter()
        out = client.post("/api/v1/external-product-maps/resolve", headers=admin,
                          json={"source": "tmall", "listings": listings, "with_candidates": True}).json()
        elapsed = time.perf_counter() - started
        assert out["meta"] == {"total": 500, "mapped": 400, "unmapped": 100}
        assert all(a["candidates"] for a in out["data"][400:]), "every unmapped title found its family in the catalog"
        assert elapsed < 20, f"500 listings against 10k maps and 3k products took {elapsed:.1f}s"
