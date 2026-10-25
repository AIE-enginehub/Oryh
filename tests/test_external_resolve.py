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

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_external_resolve.json').read_text(encoding="utf-8"))


import time

import pytest

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Resolve Co", email="admin@resolve.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        client.post("/api/v1/sales-channels", headers=admin, json={
            "channel_code": "tmall", "name": _ZH_TEXT['TEXT_650D7BCACD9B4DDB'], "channel_kind": "marketplace"})

        def product(name: str, code: str, spec: str | None = None) -> str:
            return client.post("/api/v1/products", headers=admin, json={
                "name": name, "product_code": code, **({"spec": spec} if spec else {})}).json()["data"]["id"]

        cup = product(_ZH_TEXT['TEXT_2FA6B65BF08FB482'], "CUP-500", "500ml")
        box = product(_ZH_TEXT['TEXT_6C1B8DB7C56C8267'], "BOX-01")
        ribbon = product(_ZH_TEXT['TEXT_798868B4C64C7B76'], "RB-100")
        printer = product(_ZH_TEXT['TEXT_A518A8C46A312845'], "PR-900")

        def pair(**body) -> dict:
            r = client.post("/api/v1/external-product-maps", headers=admin, json={"source": "tmall", **body})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        pair(external_product_id="TM-1", external_name=_ZH_TEXT['TEXT_E1A3AFAA8290F395'], product_id=cup)
        # a bundle listing: two rows under one title, no platform id
        pair(external_name=_ZH_TEXT['TEXT_DC8933BFACACE2E9'], product_id=cup)
        pair(external_name=_ZH_TEXT['TEXT_DC8933BFACACE2E9'], product_id=box)
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
        {"external_name": _ZH_TEXT['TEXT_DC8933BFACACE2E9']},
        {"external_name": _ZH_TEXT['TEXT_2F68D3165E1677D8']},      # fullwidth space, other case: the same title
        {"external_name": _ZH_TEXT['TEXT_2C894B3FE6165E09']},
        {"external_product_id": "TM-404", "external_name": _ZH_TEXT['TEXT_E1A3AFAA8290F395']},  # unknown id, known title — but that row is id-keyed
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
        {"external_product_id": "TM-1"}, {"external_name": _ZH_TEXT['TEXT_DC8933BFACACE2E9']}, {"external_product_id": "TM-SWAP"},
        {"external_product_id": "TM-1", "external_name": _ZH_TEXT['TEXT_DC8933BFACACE2E9']}, {"external_name": "nothing"},
    ]
    batch = _resolve(shop, at="2026-08-15", listings=listings)["data"]
    for listing, answer in zip(listings, batch):
        single = c.get("/api/v1/external-product-maps", headers=admin,
                       params={"source": "tmall", "at": "2026-08-15", **listing}).json()["data"]
        assert sorted(m["id"] for m in answer["maps"]) == sorted(m["id"] for m in single), listing


def test_unmapped_titles_come_back_with_the_same_shortlist_product_matches_gives(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    titles = [_ZH_TEXT['TEXT_578068C723E3EBD1'], _ZH_TEXT['TEXT_70DDEF13FBA7A7D4'], _ZH_TEXT['TEXT_9E5FDCE269EA28D3']]
    out = _resolve(shop, with_candidates=True, candidate_limit=3,
                   listings=[{"external_name": t} for t in titles] + [{"external_product_id": "TM-1"}])["data"]
    for title, answer in zip(titles, out):
        single = c.get("/api/v1/product-matches", headers=admin, params={"title": title, "limit": 3}).json()["data"]
        assert [(x["id"], x["match_score"]) for x in answer["candidates"]] == [(x["id"], x["match_score"]) for x in single], title
    assert out[0]["candidates"][0]["id"] == shop["ribbon"], _ZH_TEXT['TEXT_87D3B53CD0E2628D']
    assert out[2]["candidates"] == []
    assert "candidates" not in out[3], "a mapped listing needs no shortlist"


def test_it_is_a_read_bounded_and_strict(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    before = len(c.get("/api/v1/external-product-maps", headers=admin).json()["data"])
    _resolve(shop, with_candidates=True, listings=[{"external_name": _ZH_TEXT['TEXT_70DDEF13FBA7A7D4']}])
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
            families = [_ZH_TEXT['TEXT_2FA6B65BF08FB482'], _ZH_TEXT['TEXT_5386326B9FB0B932'], _ZH_TEXT['TEXT_5C71C5780CCB6032'], _ZH_TEXT['TEXT_3817285CDEA2134F'], _ZH_TEXT['TEXT_E6F6CD8DE54293AE'], _ZH_TEXT['TEXT_6E2FB1EF4B2B4A37'], _ZH_TEXT['TEXT_8D112AC9B899713F'], _ZH_TEXT['TEXT_3B43089648D6A155']]
            products = [Product(tenant_id=tenant_id, name=f"{families[i % 8]}{i:04d}{_ZH_TEXT['TEXT_850E16D958CEA72A']}", product_code=f"P-{i:05d}",
                                spec=f"{100 + i % 50}x{200 + i % 30}", status="active") for i in range(3000)]
            db.add_all(products); db.flush()
            db.add_all([ExternalProductMap(tenant_id=tenant_id, source="tmall", external_product_id=f"TM-{i}",
                                           external_sku_id="", external_name=f"{_ZH_TEXT['TEXT_F79CBD5F2876075F']}{i}",
                                           external_name_norm=normalize_external_name(f"{_ZH_TEXT['TEXT_F79CBD5F2876075F']}{i}"),
                                           product_id=products[i % 3000].id, quantity=1, status="active")
                        for i in range(10000)])
            db.commit()
        listings = [{"external_product_id": f"TM-{i * 20}"} for i in range(400)] + \
                   [{"external_name": f"{families[i % 8]}{i * 7:04d}{_ZH_TEXT['TEXT_B89AD82CD875A727']}"} for i in range(100)]
        started = time.perf_counter()
        out = client.post("/api/v1/external-product-maps/resolve", headers=admin,
                          json={"source": "tmall", "listings": listings, "with_candidates": True}).json()
        elapsed = time.perf_counter() - started
        assert out["meta"] == {"total": 500, "mapped": 400, "unmapped": 100}
        assert all(a["candidates"] for a in out["data"][400:]), "every unmapped title found its family in the catalog"
        assert elapsed < 20, f"500 listings against 10k maps and 3k products took {elapsed:.1f}s"
