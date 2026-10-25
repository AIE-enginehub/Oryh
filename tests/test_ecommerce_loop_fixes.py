"""Fixes from the e-commerce order loop simulation
(docs/ecommerce-order-loop-agent-simulation-2026-09-11.zh.md).

Each test names the finding it closes: the candidate list ranks the goods
over the machine that shares its marketing words, names the SKU a spec
token points at, and tells the truth about has_skus (E-06, E-05, E-17);
the spec text folds the way the title does (E-01); an export that carries
ids still finds the title-keyed rows a desk wrote (E-18); a platform number
becomes one order unless the caller declares a split (E-02); a seller links
only its own orders (E-30); a hold cannot promise stock that is not there
and a release cannot give back more than was held (E-15); the store list
says who ships for each store (E-24); a position registers its facility
after the fact (E-25); the desk that confirms pairings may withdraw an
undated one but never date a swap (E-03); a USD order carries no CNY list
price (E-20); the backlog read is the structured shortage (E-22, E-27) and
the order detail says what shipped per line (E-28).
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_ecommerce_loop_fixes.json').read_text(encoding="utf-8"))


import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Ecom Co", email="admin@ecom.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        for code, name in (("tmall", _ZH_TEXT['TEXT_650D7BCACD9B4DDB']), ("jd", _ZH_TEXT['TEXT_81BAF57E05F11276'])):
            client.post("/api/v1/sales-channels", headers=admin,
                        json={"channel_code": code, "name": name, "channel_kind": "marketplace"})

        def product(name: str, code: str, **extra) -> str:
            return client.post("/api/v1/products", headers=admin,
                               json={"name": name, "product_code": code, **extra}).json()["data"]["id"]

        printers = {code: product(f"{code} {tier}{_ZH_TEXT['TEXT_A518A8C46A312845']}", code, list_price=price)
                    for code, tier, price in (("JC-600", _ZH_TEXT['TEXT_9F4D8636B82415C3'], 88000), ("JC-700", _ZH_TEXT['TEXT_A7F82FEA1AF99270'], 128000), ("JC-800", _ZH_TEXT['TEXT_F964E258A17BCF37'], 198000))}
        ribbon = product(_ZH_TEXT['TEXT_60D863633FFEE6BA'], "PT-RIBBON", list_price=380)
        skus = {}
        for size in ("8x10", "11x14", "14x17"):
            skus[size] = client.post("/api/v1/product-skus", headers=admin, json={
                "product_id": ribbon, "sku_code": f"RB-{size}", "variant_attrs": {_ZH_TEXT['TEXT_3E3C1381E289C43F']: size},
            }).json()["data"]["id"]
        head = product(_ZH_TEXT['TEXT_AB24582AF2B2BB11'], "PT-HEAD", list_price=8600)
        motor = product(_ZH_TEXT['TEXT_EABF2BBB6A1D463F'], "PT-MOTOR", list_price=1200)

        seller_emp = client.post("/api/v1/employees", json={"name": _ZH_TEXT['TEXT_FA6D97D001FB87DC']}, headers=admin).json()["data"]["id"]
        other_emp = client.post("/api/v1/employees", json={"name": _ZH_TEXT['TEXT_EEB0BE5265CA353A']}, headers=admin).json()["data"]["id"]
        seller = invite_member(client, admin, "maxue", ["order.submit_own"], employee_id=seller_emp)
        keeper = invite_member(client, admin, "keeper", ["inventory.manage"])

        def order(employee_id: str = seller_emp, **extra) -> dict:
            body = {"employee_id": employee_id, "customer_name_snapshot": _ZH_TEXT['TEXT_6D6A63F93C43899E'], "title": _ZH_TEXT['TEXT_E5FC40746BB3834E'], **extra}
            r = client.post("/api/v1/sales-orders", json=body, headers=admin)
            assert r.status_code == 201, r.text
            return r.json()["data"]

        def walk(order_id: str, *states: str) -> None:
            for state in states:
                r = client.patch(f"/api/v1/sales-orders/{order_id}", json={"status": state}, headers=admin)
                assert r.status_code == 200, f"{state}: {r.text}"

        yield {
            "client": client, "admin": admin, "seller": seller, "seller_emp": seller_emp,
            "other_emp": other_emp, "keeper": keeper, "printers": printers, "ribbon": ribbon,
            "skus": skus, "head": head, "motor": motor, "order": order, "walk": walk,
        }


# --- E-06 / E-05 / E-17: candidates ----------------------------------------

def test_e06_the_goods_outrank_the_machine_that_shares_its_words(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    rows = client.get("/api/v1/product-matches", headers=admin,
                      params={"title": _ZH_TEXT['TEXT_5896C5D384BE2BE4'], "limit": 5}).json()["data"]
    assert rows[0]["id"] == shop["ribbon"], [(r["product_code"], r["match_score"]) for r in rows]
    assert rows[0]["match_score"] > rows[1]["match_score"]
    assert _ZH_TEXT['TEXT_3276FDB7927C16A4'] in rows[0]["matched_terms"] and "14x17" in rows[0]["matched_terms"]
    # E-17: the flag is the truth the /products list tells
    assert rows[0]["has_skus"] is True and rows[0]["sku_count"] == 3
    # E-05: the spec token resolves to the variant, not just the product
    assert [sku["sku_code"] for sku in rows[0]["sku_candidates"]] == ["RB-14x17"]

    five_rolls = client.get("/api/v1/product-matches", headers=admin,
                            params={"title": _ZH_TEXT['TEXT_37A83F63E4B7F2F2']}).json()["data"]
    assert five_rolls[0]["id"] == shop["ribbon"]
    assert five_rolls[0]["sku_candidates"] == [], "no spec in the title, no variant named"

    part = client.get("/api/v1/product-matches", headers=admin,
                      params={"title": _ZH_TEXT['TEXT_7AF7A0D7CBCFB78D']}).json()["data"]
    assert part[0]["id"] == shop["motor"]


# --- E-01 / E-18 / E-03: the map -----------------------------------------------

def test_e01_the_spec_text_folds_like_the_title(shop) -> None:
    client, seller = shop["client"], shop["seller"]
    written = client.post("/api/v1/external-product-maps", headers=seller, json={
        "source": "tmall", "external_name": _ZH_TEXT['TEXT_38C67418CFA5CA9D'], "external_sku_id": _ZH_TEXT['TEXT_C85E9E3D4A34670A'],
        "product_id": shop["ribbon"], "sku_id": shop["skus"]["11x14"], "quantity": 1,
    })
    assert written.status_code == 201, written.text
    assert written.json()["data"]["external_sku_id"] == _ZH_TEXT['TEXT_6FCC8FD6F67C4996']
    hit = client.get("/api/v1/external-product-maps", headers=seller, params={
        "source": "tmall", "external_name": _ZH_TEXT['TEXT_EFF3AEB28D41D262'], "external_sku_id": _ZH_TEXT['TEXT_6FCC8FD6F67C4996'],
        "at": "2026-09-10",
    }).json()["data"]
    assert [row["sku_id"] for row in hit] == [shop["skus"]["11x14"]]


def test_e18_an_id_carrying_export_still_finds_the_title_keyed_row(shop) -> None:
    client, seller = shop["client"], shop["seller"]
    client.post("/api/v1/external-product-maps", headers=seller, json={
        "source": "jd", "external_name": _ZH_TEXT['TEXT_0D2F1C18990EF495'], "product_id": shop["motor"],
    })
    by_both = client.get("/api/v1/external-product-maps", headers=seller, params={
        "source": "jd", "external_product_id": "100045678999", "external_name": _ZH_TEXT['TEXT_0D2F1C18990EF495'],
        "at": "2026-09-10",
    }).json()["data"]
    assert [row["product_id"] for row in by_both] == [shop["motor"]]
    by_id_alone = client.get("/api/v1/external-product-maps", headers=seller, params={
        "source": "jd", "external_product_id": "100045678999", "at": "2026-09-10",
    }).json()["data"]
    assert by_id_alone == [], "the id alone names nothing yet — the title did"


def test_e03_the_order_desk_withdraws_its_own_mistake_but_never_dates_a_swap(shop) -> None:
    client, seller, admin = shop["client"], shop["seller"], shop["admin"]
    wrong = client.post("/api/v1/external-product-maps", headers=seller, json={
        "source": "tmall", "external_name": _ZH_TEXT['TEXT_ACC98A9FF875B42E'], "product_id": shop["head"],
    }).json()["data"]
    gone = client.delete(f"/api/v1/external-product-maps/{wrong['id']}", headers=seller)
    assert gone.status_code == 204, gone.text
    dated = client.post("/api/v1/external-product-maps", headers=seller, json={
        "source": "tmall", "external_name": _ZH_TEXT['TEXT_ACC98A9FF875B42E'], "product_id": shop["ribbon"],
        "effective_from": "2026-09-01",
    })
    assert dated.status_code == 403 and "master_data.manage" in dated.json()["detail"]
    swap = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "tmall", "external_name": _ZH_TEXT['TEXT_ACC98A9FF875B42E'], "product_id": shop["ribbon"],
        "effective_from": "2026-09-01",
    }).json()["data"]
    kept = client.delete(f"/api/v1/external-product-maps/{swap['id']}", headers=seller)
    assert kept.status_code == 403, "a windowed row is a swap record — catalog work"


# --- E-02 / E-30: platform numbers -----------------------------------------------

def test_e02_a_platform_number_becomes_one_order_unless_split(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    first, second = shop["order"](), shop["order"]()
    link = {"source": "tmall", "external_kind": "order", "external_no": "TM202609100001",
            "entity_type": "sales_order"}
    assert client.post("/api/v1/external-document-links", headers=admin,
                       json={**link, "entity_id": first["id"]}).status_code == 201
    again = client.post("/api/v1/external-document-links", headers=admin,
                        json={**link, "entity_id": second["id"]})
    assert again.status_code == 409, again.text
    assert first["id"] in again.json()["detail"] and "split" in again.json()["detail"]
    declared = client.post("/api/v1/external-document-links", headers=admin,
                           json={**link, "entity_id": second["id"], "split": True})
    assert declared.status_code == 201, declared.text


def test_e30_a_seller_links_only_its_own_orders(shop) -> None:
    client, seller = shop["client"], shop["seller"]
    mine, theirs = shop["order"](), shop["order"](employee_id=shop["other_emp"])
    link = {"source": "jd", "external_kind": "order", "entity_type": "sales_order"}
    ok = client.post("/api/v1/external-document-links", headers=seller,
                     json={**link, "external_no": "JD1", "entity_id": mine["id"]})
    assert ok.status_code == 201, ok.text
    refused = client.post("/api/v1/external-document-links", headers=seller,
                          json={**link, "external_no": "JD2", "entity_id": theirs["id"]})
    assert refused.status_code in (403, 404), refused.text  # another seller's order does not exist for this one


# --- E-15: holds ------------------------------------------------------------------

def test_e15_a_hold_and_a_release_stay_within_what_is_there(shop) -> None:
    client, keeper, admin = shop["client"], shop["keeper"], shop["admin"]
    position = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": shop["head"], "facility": "SH-MAIN", "initial_quantity": 3,
    }).json()["data"]["id"]
    so = shop["order"](items=[{"product_id": shop["head"], "quantity": 3, "unit_price": 8600}])

    def move(verb: str, qty: float):
        return client.post(f"/api/v1/sales-orders/{so['id']}/{verb}", headers=keeper, json={
            "lines": [{"inventory_item_id": position, "quantity": qty}]})

    over = move("reserve", 4)
    assert over.status_code == 409 and "below zero" in over.json()["detail"], over.text
    assert move("reserve", 3).status_code == 200
    too_much = move("release", 4)
    assert too_much.status_code == 409 and "holds 3" in too_much.json()["detail"], too_much.text
    assert move("release", 3).status_code == 200
    nothing_left = move("release", 1)
    assert nothing_left.status_code == 409


# --- E-24 / E-25: stores and positions ------------------------------------------

def test_e24_e25_the_store_list_names_its_warehouses_and_a_position_registers_one(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    facility = client.post("/api/v1/facilities", headers=admin, json={"name": _ZH_TEXT['TEXT_596F588B4DF0BE65'], "facility_type": "warehouse"}).json()["data"]["id"]
    store = client.post("/api/v1/stores", headers=admin, json={
        "name": _ZH_TEXT['TEXT_6C8F1124A20827A4'], "channel": "online", "source": "tmall"}).json()["data"]["id"]
    client.post("/api/v1/store-facilities", headers=admin,
                json={"store_id": store, "facility_id": facility, "priority": 1})
    listed = client.get("/api/v1/stores", headers=admin, params={"source": "tmall"}).json()["data"]
    assert [f["facility_id"] for f in listed[0]["fulfilment_facilities"]] == [facility]

    position = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": shop["motor"], "facility": _ZH_TEXT['TEXT_596F588B4DF0BE65'], "initial_quantity": 4,
    }).json()["data"]
    assert position["facility_id"] is None
    filled = client.patch(f"/api/v1/inventory-items/{position['id']}", headers=admin,
                          json={"facility_id": facility})
    assert filled.status_code == 200, filled.text
    assert filled.json()["data"]["facility_id"] == facility
    unknown = client.patch(f"/api/v1/inventory-items/{position['id']}", headers=admin,
                           json={"facility_id": "00000000-0000-0000-0000-000000000000"})
    assert unknown.status_code == 404


# --- E-20: currency ---------------------------------------------------------------

def test_e20_a_usd_order_carries_no_cny_list_price(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    usd = shop["order"](currency="USD", items=[{"product_id": shop["ribbon"], "sku_id": shop["skus"]["11x14"],
                                              "quantity": 5, "unit_price": 47.8}])
    line = client.get(f"/api/v1/sales-order-items?order_id={usd['id']}", headers=admin).json()["data"][0]
    assert line["list_price_snapshot"] is None, line
    cny = shop["order"](items=[{"product_id": shop["ribbon"], "quantity": 1, "unit_price": 300}])
    line = client.get(f"/api/v1/sales-order-items?order_id={cny['id']}", headers=admin).json()["data"][0]
    assert line["list_price_snapshot"] == 380.0


# --- E-22 / E-27 / E-28: the backlog ------------------------------------------------

def test_e22_the_backlog_is_the_shortage_as_a_fact(shop) -> None:
    client, admin, keeper = shop["client"], shop["admin"], shop["keeper"]
    position = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": shop["ribbon"], "sku_id": shop["skus"]["14x17"], "facility": "TA", "initial_quantity": 40,
    }).json()["data"]["id"]
    partial = shop["order"](items=[
        {"product_id": shop["ribbon"], "sku_id": shop["skus"]["14x17"], "quantity": 3, "unit_price": 380},
        {"product_id": shop["ribbon"], "sku_id": shop["skus"]["8x10"], "quantity": 2, "unit_price": 300},
    ])
    nothing = shop["order"](items=[{"product_id": shop["ribbon"], "sku_id": shop["skus"]["8x10"], "quantity": 4, "unit_price": 300}])
    still_draft = shop["order"](items=[{"product_id": shop["head"], "quantity": 1, "unit_price": 8600}])
    shop["walk"](partial["id"], "submitted", "confirmed")
    shop["walk"](nothing["id"], "submitted", "confirmed")

    shipment = client.post("/api/v1/shipments", headers=keeper, json={
        "direction": "outbound", "sales_order_id": partial["id"], "facility": "TA",
        "items": [{"product_id": shop["ribbon"], "sku_id": shop["skus"]["14x17"], "quantity": 3,
                   "inventory_item_id": position}],
    }).json()["data"]
    before = client.get("/api/v1/fulfilment-backlog", headers=admin).json()["data"]
    assert [row["order_id"] for row in before] == [partial["id"], nothing["id"]]
    assert all(line["shipped"] == 0 for line in before[0]["lines"]), "a draft leg has shipped nothing"
    assert client.post(f"/api/v1/shipments/{shipment['id']}/post-stock", headers=keeper).status_code == 200

    backlog = client.get("/api/v1/fulfilment-backlog", headers=admin).json()
    assert backlog["meta"]["total"] == 2
    rows = {row["order_id"]: row for row in backlog["data"]}
    assert still_draft["id"] not in rows
    lines = {line["sku_id"]: line for line in rows[partial["id"]]["lines"]}
    assert lines[shop["skus"]["14x17"]]["outstanding"] == 0 and lines[shop["skus"]["14x17"]]["shipped"] == 3
    assert lines[shop["skus"]["8x10"]]["outstanding"] == 2
    assert rows[partial["id"]]["shipments_posted"] == 1
    assert rows[nothing["id"]]["shipments_posted"] == 0 and rows[nothing["id"]]["lines"][0]["outstanding"] == 4

    detail = client.get(f"/api/v1/sales-orders/{partial['id']}/detail", headers=admin).json()["data"]
    assert sorted((line["shipped"], line["outstanding"]) for line in detail["fulfilment"]) == [(0.0, 2.0), (3.0, 0.0)]
    only_store = client.get("/api/v1/fulfilment-backlog", headers=admin,
                            params={"employee_id": shop["other_emp"]}).json()["data"]
    assert only_store == []
