"""Product price book and supplier links — the OFBiz-shaped pair.

History is status, not date ranges: superseding a price archives the old row
and creates the new active one, so "one live price per (product-or-sku, type,
currency)" is the invariant and archived rows are the paper trail. A supplier
link is one row per (product, vendor) whose last_price updates in place. The
bulk product import writes both when its rows carry them.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_product_prices_suppliers.json').read_text(encoding="utf-8"))


from fastapi.testclient import TestClient


from conftest import admin_headers, create, invite_member


def provision(client: TestClient) -> dict[str, str]:
    return admin_headers(client, company_name="Price Co", email="admin@price-co.example", password="admin-pass1")


def create_product(client: TestClient, headers, code: str = "P-001", name: str = _ZH_TEXT['TEXT_C7005F6AFFA067C1']) -> str:
    return create(client, headers, "products", product_code=code, name=name)["id"]


def create_vendor(client: TestClient, headers, code: str = "V-001", name: str = _ZH_TEXT['TEXT_B61BD2B509D29104']) -> str:
    return create(client, headers, "vendors", vendor_code=code, name=name)["id"]


def bulk(client: TestClient, headers, rows, **options) -> dict:
    response = client.post(
        "/api/v1/products/bulk", json={"rows": rows, **options}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- CRUD ------------------------------------------------------------------


def test_price_crud_and_one_active_slot_per_key(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)

    created = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "wholesale", "price": 15.5, "tax_percentage": 13},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    price_id = created.json()["data"]["id"]
    assert created.json()["data"]["tax_in_price"] is True

    # the active slot for (product, type, currency) is taken
    duplicate = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "wholesale", "price": 16.0},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert price_id in duplicate.json()["detail"]

    # a different currency is a different slot
    usd = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "wholesale", "price": 2.2, "currency": "USD"},
        headers=headers,
    )
    assert usd.status_code == 201, usd.text

    # archiving frees the slot; reactivating while it is taken is a 409
    assert client.delete(f"/api/v1/product-prices/{price_id}", headers=headers).status_code == 204
    replacement = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "wholesale", "price": 16.0},
        headers=headers,
    )
    assert replacement.status_code == 201, replacement.text
    revive = client.patch(
        f"/api/v1/product-prices/{price_id}", json={"status": "active"}, headers=headers
    )
    assert revive.status_code == 409

    listed = client.get(
        f"/api/v1/product-prices?product_id={product_id}&price_type=wholesale&currency=CNY&status=all",
        headers=headers,
    ).json()["data"]
    # live slot holds the replacement; the archived original is the history
    assert {(row["status"], row["price"]) for row in listed} == {("active", 16.0), ("archived", 15.5)}


def test_price_sku_must_belong_to_product(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)
    other_id = create_product(client, headers, code="P-002", name=_ZH_TEXT['TEXT_0A307701BE8A1769'])
    sku = client.post(
        "/api/v1/product-skus",
        json={"product_id": other_id, "variant_attrs": {_ZH_TEXT['TEXT_4060F118DEA05D67']: "XL"}},
        headers=headers,
    ).json()["data"]["id"]

    response = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "sku_id": sku, "price_type": "promo", "price": 9.9},
        headers=headers,
    )
    assert response.status_code == 400
    assert "sku_id" in response.json()["detail"]


def test_supplier_link_crud_one_row_per_pair(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)
    vendor_id = create_vendor(client, headers)

    created = client.post(
        "/api/v1/supplier-products",
        json={
            "product_id": product_id,
            "vendor_id": vendor_id,
            "supplier_product_code": "HD-XX-01",
            "last_price": 12.8,
            "lead_time_days": 7,
            "min_order_quantity": 100,
            "preference": 1,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    link = created.json()["data"]
    assert link["vendor_name"] == _ZH_TEXT['TEXT_B61BD2B509D29104']

    duplicate = client.post(
        "/api/v1/supplier-products",
        json={"product_id": product_id, "vendor_id": vendor_id},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert link["id"] in duplicate.json()["detail"]

    patched = client.patch(
        f"/api/v1/supplier-products/{link['id']}", json={"last_price": 12.5}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["last_price"] == 12.5

    assert client.delete(f"/api/v1/supplier-products/{link['id']}", headers=headers).status_code == 204
    archived = client.get(f"/api/v1/supplier-products/{link['id']}", headers=headers).json()["data"]
    assert archived["status"] == "archived"


def test_price_writes_need_master_data_manage(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)
    # a user-bound member key can read the price book but not write it
    member = dict(invite_member(client, headers, "wang", role="member", email="wang@price-co.example", employee=_ZH_TEXT['TEXT_F5C982AE4094EF29']))

    assert client.get("/api/v1/product-prices", headers=member).status_code == 200
    denied = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "promo", "price": 9.9},
        headers=member,
    )
    assert denied.status_code == 403
    assert "master_data.manage" in denied.json()["detail"]


# --- bulk import writes both tables ----------------------------------------


def test_bulk_rows_carry_prices_and_suppliers(client: TestClient) -> None:
    headers = provision(client)
    create_vendor(client, headers)

    rows = [
        {
            "product_code": "P-100",
            "name": _ZH_TEXT['TEXT_ADFBE6F133AD4366'],
            "list_price": 19.9,
            "prices": [
                {"price_type": "wholesale", "price": 15.5, "tax_percentage": 13},
                {"price_type": "cost", "price": 11.2, "tax_in_price": False},
            ],
            "suppliers": [
                {"vendor_code": "V-001", "supplier_product_code": "HD-XX-01", "last_price": 11.2, "lead_time_days": 7}
            ],
        }
    ]
    first = bulk(client, headers, rows)
    assert first["summary"]["created"] == 1

    product_id = client.get(_ZH_TEXT['TEXT_5D3DAB28A731BD1F'], headers=headers).json()["data"][0]["id"]
    prices = client.get(f"/api/v1/product-prices?product_id={product_id}", headers=headers).json()["data"]
    assert {(p["price_type"], p["price"]) for p in prices} == {("wholesale", 15.5), ("cost", 11.2)}
    links = client.get(f"/api/v1/supplier-products?product_id={product_id}", headers=headers).json()["data"]
    assert len(links) == 1 and links[0]["supplier_product_code"] == "HD-XX-01"

    # the same file again is a full no-op — nested floats included
    second = bulk(client, headers, rows)
    assert second["summary"] == {"total": 1, "created": 0, "updated": 0, "unchanged": 1, "failed": 0}, (
        second["results"]
    )

    # a moved wholesale price archives the old row and creates the new: history
    rows[0]["prices"][0]["price"] = 14.8
    third = bulk(client, headers, rows)
    moved = third["results"][0]
    assert moved["outcome"] == "updated" and moved["changed"] == ["prices"]
    wholesale = client.get(
        f"/api/v1/product-prices?product_id={product_id}&price_type=wholesale&status=all", headers=headers
    ).json()["data"]
    # set, not order: rows born in the same second tie on created_at
    assert {(p["price"], p["status"]) for p in wholesale} == {(14.8, "active"), (15.5, "archived")}

    # a supplier price move updates in place — no history row for the pair
    rows[0]["suppliers"][0]["last_price"] = 10.9
    fourth = bulk(client, headers, rows)
    assert fourth["results"][0]["changed"] == ["suppliers"]
    links = client.get(f"/api/v1/supplier-products?product_id={product_id}", headers=headers).json()["data"]
    assert len(links) == 1 and links[0]["last_price"] == 10.9


def test_bulk_unknown_vendor_code_is_a_row_error_and_aborts(client: TestClient) -> None:
    headers = provision(client)
    rows = [
        {"product_code": "P-200", "name": _ZH_TEXT['TEXT_34141C98D7F98B1A'], "suppliers": [{"vendor_code": "V-404", "last_price": 3.3}]},
        {"product_code": "P-201", "name": _ZH_TEXT['TEXT_F2BCFBB4C9DCE340']},
    ]
    report = bulk(client, headers, rows)
    assert report["applied"] is False
    assert report["summary"]["failed"] == 1
    error = [r for r in report["results"] if r["outcome"] == "error"][0]
    assert error["index"] == 0 and "V-404" in error["error"]
    # abort semantics: the good row was not written either
    assert client.get(_ZH_TEXT['TEXT_7D8857B30A98B836'], headers=headers).json()["data"] == []

    # skip mode imports the good row and reports the rest
    skipped = bulk(client, headers, rows, on_error="skip")
    assert skipped["summary"]["created"] == 1 and skipped["summary"]["failed"] == 1


def test_bulk_duplicate_nested_keys_are_row_errors(client: TestClient) -> None:
    headers = provision(client)
    create_vendor(client, headers)
    report = bulk(
        client,
        headers,
        [
            {
                "product_code": "P-300",
                "name": _ZH_TEXT['TEXT_1B1AABCF1272E356'],
                "prices": [
                    {"price_type": "promo", "price": 8.8},
                    {"price_type": "promo", "price": 7.7},
                ],
            }
        ],
    )
    assert report["summary"]["failed"] == 1
    assert "price_type" in report["results"][0]["error"]


def test_bulk_dry_run_writes_no_nested_rows(client: TestClient) -> None:
    headers = provision(client)
    create_vendor(client, headers)
    rows = [
        {
            "product_code": "P-400",
            "name": _ZH_TEXT['TEXT_03D1F94FF456E4BA'],
            "prices": [{"price_type": "wholesale", "price": 21.9}],
            "suppliers": [{"vendor_code": "V-001", "last_price": 18.0}],
        }
    ]
    preview = bulk(client, headers, rows, dry_run=True)
    assert preview["applied"] is False and preview["summary"]["created"] == 1
    assert client.get(_ZH_TEXT['TEXT_C0C4E45486872DEE'], headers=headers).json()["data"] == []
    assert client.get("/api/v1/product-prices", headers=headers).json()["data"] == []
    assert client.get("/api/v1/supplier-products", headers=headers).json()["data"] == []


def test_bulk_reimport_revives_archived_supplier_link(client: TestClient) -> None:
    headers = provision(client)
    vendor_id = create_vendor(client, headers)
    rows = [
        {"product_code": "P-500", "name": _ZH_TEXT['TEXT_88949D0EF051214C'], "suppliers": [{"vendor_code": "V-001", "last_price": 500.0}]}
    ]
    bulk(client, headers, rows)
    product_id = client.get(_ZH_TEXT['TEXT_CED0574BF4F285F5'], headers=headers).json()["data"][0]["id"]
    link_id = client.get(
        f"/api/v1/supplier-products?product_id={product_id}&vendor_id={vendor_id}", headers=headers
    ).json()["data"][0]["id"]
    client.delete(f"/api/v1/supplier-products/{link_id}", headers=headers)

    revived = bulk(client, headers, rows)
    assert revived["results"][0]["changed"] == ["suppliers"]
    link = client.get(f"/api/v1/supplier-products/{link_id}", headers=headers).json()["data"]
    assert link["status"] == "active"
