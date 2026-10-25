from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_purchase.json').read_text(encoding="utf-8"))


from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import Tenant

from conftest import create, seeded_tenants


TEST_TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
TEST_API_KEY = "test-api-key"
OTHER_API_KEY = "other-api-key"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    yield from seeded_tenants((TEST_TENANT, "Test Tenant", TEST_API_KEY), (OTHER_TENANT, "Other Tenant", OTHER_API_KEY))


def api_key_headers(api_key: str = TEST_API_KEY) -> dict[str, str]:
    return {"X-API-Key": api_key}


def headers_for_tenant(tenant_id: str) -> dict[str, str]:
    return api_key_headers(TEST_API_KEY if tenant_id == TEST_TENANT else OTHER_API_KEY)


def create_employee(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {"name": "Alice"}
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "employees", **payload)["id"]


def create_vendor(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": _ZH_TEXT['TEXT_48A8405C94F000EC'], "tax_id": "91110000600000000D"}
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "vendors", **payload)


def create_product(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": _ZH_TEXT['TEXT_3D7C389C9EA4E117'], "spec": "U2723QE 4K", "unit": _ZH_TEXT['TEXT_991363A244F032C7'], "list_price": 3199.0}
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "products", **payload)


def create_request(test_client: TestClient, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "employee_id": employee_id,
        "title": _ZH_TEXT['TEXT_1C6367C09C0B995A'],
        "request_date": "2026-07-11",
    }
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "purchase-requests", **payload)["id"]


def create_item(test_client: TestClient, request_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"request_id": request_id, "product_name_snapshot": _ZH_TEXT['TEXT_B31F6EB420364847'], "quantity": 2}
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "purchase-request-items", **payload)


def test_product_master_data_crud_and_filters(client: TestClient) -> None:
    product = create_product(client, product_code="PRD-001")
    assert product["status"] == "active"
    assert product["list_price"] == 3199.0

    by_keyword = client.get(_ZH_TEXT['TEXT_7C4B386FF7FEC9A9'], headers=api_key_headers()).json()["data"]
    assert [p["id"] for p in by_keyword] == [product["id"]]

    updated = client.patch(
        f"/api/v1/products/{product['id']}", json={"list_price": 2999.0}, headers=api_key_headers()
    )
    assert updated.json()["data"]["list_price"] == 2999.0

    # archive removes from active list; other tenant sees nothing
    assert client.delete(f"/api/v1/products/{product['id']}", headers=api_key_headers()).status_code == 204
    assert client.get("/api/v1/products?status=active", headers=api_key_headers()).json()["data"] == []
    assert client.get(
        f"/api/v1/products/{product['id']}", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404


def test_purchase_flow_with_optional_vendor_product_price(client: TestClient) -> None:
    employee_id = create_employee(client)
    vendor = create_vendor(client)
    product = create_product(client)

    # vendor known up front: id + snapshot backfill
    request_id = create_request(
        client, employee_id, vendor_id=vendor["id"],
        source_report_text=_ZH_TEXT['TEXT_02C91168D85FDA9A'],
        needed_by="2026-07-25",
    )
    header = client.get(f"/api/v1/purchase-requests/{request_id}", headers=api_key_headers()).json()["data"]
    assert header["vendor_id"] == vendor["id"]
    assert header["vendor_name_snapshot"] == _ZH_TEXT['TEXT_48A8405C94F000EC']

    # line 1: cataloged product with unit price — name/unit backfilled
    priced = create_item(
        client, request_id,
        product_id=product["id"], product_name_snapshot=None, quantity=2, unit_price=2999.0,
    )
    assert priced["product_name_snapshot"] == _ZH_TEXT['TEXT_3D7C389C9EA4E117']
    assert priced["unit"] == _ZH_TEXT['TEXT_991363A244F032C7']

    # line 2: free-text item with a lump-sum amount, no unit price
    create_item(client, request_id, product_name_snapshot=_ZH_TEXT['TEXT_604BA56C93A65DD7'], amount=800.0)

    # line 3: free-text item with no price at all — a normal fact
    unpriced = create_item(client, request_id, product_name_snapshot=_ZH_TEXT['TEXT_6E2FB1EF4B2B4A37'], quantity=2)
    assert unpriced["unit_price"] is None and unpriced["amount"] is None

    submit = client.post(
        f"/api/v1/purchase-requests/{request_id}/submit", json={"source": "ai"}, headers=api_key_headers()
    )
    assert submit.status_code == 200
    assert submit.json()["data"]["status"] == "submitted"
    # idempotent resubmit
    assert client.post(
        f"/api/v1/purchase-requests/{request_id}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    approval = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "purchase_request",
            "entity_id": request_id,
            "action": "approved",
            "sequence_no": 2,
            "approver_role": "manager",
            "source": "ai",
        },
        headers=api_key_headers(),
    )
    assert approval.status_code == 201

    detail = client.get(
        f"/api/v1/purchase-requests/{request_id}/detail", headers=api_key_headers()
    ).json()["data"]
    assert len(detail["items"]) == 3
    # estimated total is honest: 2×2999 + 800, with one line unpriced
    assert detail["estimated_total"] == pytest.approx(6798.0)
    assert detail["unpriced_item_count"] == 1
    # two facts now: the submission the server recorded when /submit ran,
    # and the decision on top of it
    assert [r["action"] for r in detail["approval_records"]] == ["submitted", "approved"]

    # finalize: submitted -> approved -> ordered follows the default machine
    for target in ("approved", "ordered"):
        response = client.patch(
            f"/api/v1/purchase-requests/{request_id}", json={"status": target}, headers=api_key_headers()
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == target


def test_purchase_request_without_vendor_and_work_queue(client: TestClient) -> None:
    employee_id = create_employee(client)
    # no vendor at all — free-text hint only
    first = create_request(client, employee_id, title=_ZH_TEXT['TEXT_C72CE83563BABBBD'], vendor_name_snapshot=_ZH_TEXT['TEXT_3AC71949261F2FF0'])
    second = create_request(client, employee_id, title=_ZH_TEXT['TEXT_C8A99CB50C486916'])
    header = client.get(f"/api/v1/purchase-requests/{first}", headers=api_key_headers()).json()["data"]
    assert header["vendor_id"] is None
    assert header["vendor_name_snapshot"] == _ZH_TEXT['TEXT_3AC71949261F2FF0']

    create_item(client, first, product_name_snapshot=_ZH_TEXT['TEXT_3FFB64DD8E70E7FB'], quantity=10, unit=_ZH_TEXT['TEXT_702DFF992262EC17'])
    create_item(client, second, product_name_snapshot=_ZH_TEXT['TEXT_618055B1209620BA'], quantity=1)
    client.post(f"/api/v1/purchase-requests/{first}/submit", json={}, headers=api_key_headers())
    client.post(f"/api/v1/purchase-requests/{second}/submit", json={}, headers=api_key_headers())

    queue = client.get(
        "/api/v1/purchase-requests?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert {r["id"] for r in queue} == {first, second}

    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "purchase_request",
            "entity_id": first,
            "title": _ZH_TEXT['TEXT_A4DF92292C7A54D0'],
            "todo_type": "approval",
        },
        headers=api_key_headers(),
    )
    assert todo.status_code == 201, todo.text
    queue = client.get(
        "/api/v1/purchase-requests?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert {r["id"] for r in queue} == {second}

    # vendor can be attached later (after sourcing prices) while editable… request is
    # submitted now, but header vendor patch is not an item write — allowed
    vendor = create_vendor(client)
    patched = client.patch(
        f"/api/v1/purchase-requests/{first}", json={"vendor_id": vendor["id"]}, headers=api_key_headers()
    )
    assert patched.json()["data"]["vendor_id"] == vendor["id"]


def test_items_locked_after_submit_and_machine_guards(client: TestClient) -> None:
    employee_id = create_employee(client)
    request_id = create_request(client, employee_id)
    item = create_item(client, request_id)

    # draft -> ordered skips the whole flow: illegal
    assert client.patch(
        f"/api/v1/purchase-requests/{request_id}", json={"status": "ordered"}, headers=api_key_headers()
    ).status_code == 409

    client.post(f"/api/v1/purchase-requests/{request_id}/submit", json={}, headers=api_key_headers())

    assert client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "product_name_snapshot": _ZH_TEXT['TEXT_D91017C932B5FC75'], "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 409
    assert client.patch(
        f"/api/v1/purchase-request-items/{item['id']}", json={"quantity": 5}, headers=api_key_headers()
    ).status_code == 409
    assert client.delete(
        f"/api/v1/purchase-request-items/{item['id']}", headers=api_key_headers()
    ).status_code == 409

    # returned reopens editing (sourcing and pricing round), resubmission closes it again
    assert client.patch(
        f"/api/v1/purchase-requests/{request_id}", json={"status": "returned"}, headers=api_key_headers()
    ).status_code == 200
    assert client.patch(
        f"/api/v1/purchase-request-items/{item['id']}",
        json={"unit_price": 450.0}, headers=api_key_headers(),
    ).status_code == 200
    assert client.post(
        f"/api/v1/purchase-requests/{request_id}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # ordered is terminal
    client.patch(f"/api/v1/purchase-requests/{request_id}", json={"status": "approved"}, headers=api_key_headers())
    client.patch(f"/api/v1/purchase-requests/{request_id}", json={"status": "ordered"}, headers=api_key_headers())
    assert client.patch(
        f"/api/v1/purchase-requests/{request_id}", json={"status": "submitted"}, headers=api_key_headers()
    ).status_code == 409


def test_purchase_validation_and_soft_delete(client: TestClient) -> None:
    employee_id = create_employee(client)
    request_id = create_request(client, employee_id)

    # an item needs either a product_id or free text
    nameless = client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "quantity": 1},
        headers=api_key_headers(),
    )
    assert nameless.status_code == 422

    # quantity must be positive; fake product 404
    assert client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "product_name_snapshot": "x", "quantity": 0},
        headers=api_key_headers(),
    ).status_code == 422
    assert client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 404

    # invalid create status
    assert client.post(
        "/api/v1/purchase-requests",
        json={"employee_id": employee_id, "title": "x", "status": "nonsense"},
        headers=api_key_headers(),
    ).status_code == 422

    # soft delete hides, restore brings back
    create_item(client, request_id)
    assert client.delete(f"/api/v1/purchase-requests/{request_id}", headers=api_key_headers()).status_code == 204
    assert client.get(f"/api/v1/purchase-requests/{request_id}", headers=api_key_headers()).status_code == 404
    assert client.get(
        f"/api/v1/purchase-requests/{request_id}?include_deleted=true", headers=api_key_headers()
    ).status_code == 200
    assert client.get("/api/v1/purchase-requests", headers=api_key_headers()).json()["data"] == []
    restored = client.post(
        f"/api/v1/purchase-requests/{request_id}/restore", json={}, headers=api_key_headers()
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "draft"


def create_sku(test_client: TestClient, product_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"product_id": product_id, "variant_attrs": {_ZH_TEXT['TEXT_4060F118DEA05D67']: "M"}}
    payload.update(overrides)
    return create(test_client, headers_for_tenant(tenant_id), "product-skus", **payload)


def test_product_sku_master_data_and_item_refinement(client: TestClient) -> None:
    employee_id = create_employee(client)
    # apparel-style: product = style and color, skus = size
    style = create_product(client, name=_ZH_TEXT['TEXT_2764D350CAF84871'], spec="STYLE-001-NV", unit=_ZH_TEXT['TEXT_7C00255577088EC9'], list_price=89.0)
    sku_m = create_sku(client, style["id"], sku_code="001-NV-M", variant_attrs={_ZH_TEXT['TEXT_4060F118DEA05D67']: "M"})
    sku_xl = create_sku(client, style["id"], sku_code="001-NV-XL",
                        variant_attrs={_ZH_TEXT['TEXT_4060F118DEA05D67']: "XL"}, list_price=95.0)

    # has_skus tells the agent a variant conversation is needed
    read = client.get(f"/api/v1/products/{style['id']}", headers=api_key_headers()).json()["data"]
    assert read["has_skus"] is True
    listed = client.get(_ZH_TEXT['TEXT_D873EB3BA24BEEA4'], headers=api_key_headers()).json()["data"]
    assert listed[0]["has_skus"] is True
    # a flat product (product == sku company) stays has_skus false
    flat = create_product(client, name=_ZH_TEXT['TEXT_D7E32FDFE842E482'])
    assert client.get(
        f"/api/v1/products/{flat['id']}", headers=api_key_headers()
    ).json()["data"]["has_skus"] is False

    variants = client.get(
        f"/api/v1/product-skus?product_id={style['id']}", headers=api_key_headers()
    ).json()["data"]
    assert [v["sku_code"] for v in variants] == ["001-NV-M", "001-NV-XL"]
    assert variants[1]["variant_attrs"] == {_ZH_TEXT['TEXT_4060F118DEA05D67']: "XL"}
    assert variants[1]["list_price"] == 95.0

    request_id = create_request(client, employee_id, title=_ZH_TEXT['TEXT_CDEE0E6D8E129883'])

    # sku alone derives its product; product name/unit backfill from the product
    refined = create_item(client, request_id, product_name_snapshot=None,
                          sku_id=sku_xl["id"], quantity=30, unit_price=95.0)
    assert refined["product_id"] == style["id"]
    assert refined["sku_id"] == sku_xl["id"]
    assert refined["product_name_snapshot"] == _ZH_TEXT['TEXT_2764D350CAF84871']
    assert refined["unit"] == _ZH_TEXT['TEXT_7C00255577088EC9']

    # sku must belong to the product when both are given
    other_product = create_product(client, name=_ZH_TEXT['TEXT_CE45DC5B73419368'])
    mismatch = client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "product_id": other_product["id"],
              "sku_id": sku_m["id"], "quantity": 1},
        headers=api_key_headers(),
    )
    assert mismatch.status_code == 400

    # product-level line with the variant undecided is a legal fact …
    pending = create_item(client, request_id, product_id=style["id"],
                          product_name_snapshot=None, quantity=100)
    assert pending["sku_id"] is None
    archived_only_product = create_product(client, name=_ZH_TEXT['TEXT_91A9C9BCFCA8F00D'])
    archived_only_sku = create_sku(
        client, archived_only_product["id"], sku_code="HISTORY-ONLY", variant_attrs={_ZH_TEXT['TEXT_5F76B2BF82DD2C5D']: _ZH_TEXT['TEXT_4FBC8134F6D04D80']}
    )
    assert client.delete(
        f"/api/v1/product-skus/{archived_only_sku['id']}", headers=api_key_headers()
    ).status_code == 204
    archived_only_line = create_item(
        client,
        request_id,
        product_id=archived_only_product["id"],
        product_name_snapshot=None,
        quantity=1,
        unit_price=10,
    )

    # … and the detail is honest about it
    detail = client.get(
        f"/api/v1/purchase-requests/{request_id}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["pending_sku_count"] == 1
    assert detail["unpriced_item_count"] == 1  # the pending line has no price either
    refined_detail = next(item for item in detail["items"] if item["id"] == refined["id"])
    assert refined_detail["product"] == {
        "id": style["id"],
        "product_code": None,
        "name": _ZH_TEXT['TEXT_2764D350CAF84871'],
        "spec": "STYLE-001-NV",
        "unit": _ZH_TEXT['TEXT_7C00255577088EC9'],
    }
    assert refined_detail["sku"] == {
        "id": sku_xl["id"],
        "product_id": style["id"],
        "sku_code": "001-NV-XL",
        "variant_attrs": {_ZH_TEXT['TEXT_4060F118DEA05D67']: "XL"},
    }
    assert refined_detail["sku_pending"] is False
    pending_detail = next(item for item in detail["items"] if item["id"] == pending["id"])
    assert pending_detail["product"]["name"] == _ZH_TEXT['TEXT_2764D350CAF84871']
    assert pending_detail["sku"] is None
    assert pending_detail["sku_pending"] is True
    archived_only_detail = next(
        item for item in detail["items"] if item["id"] == archived_only_line["id"]
    )
    assert archived_only_detail["sku_pending"] is False

    # refining later: patch the sku on; product stays, pending count drops
    patched = client.patch(
        f"/api/v1/purchase-request-items/{pending['id']}",
        json={"sku_id": sku_m["id"], "unit_price": 89.0},
        headers=api_key_headers(),
    )
    assert patched.json()["data"]["sku_id"] == sku_m["id"]
    detail = client.get(
        f"/api/v1/purchase-requests/{request_id}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["pending_sku_count"] == 0
    assert detail["unpriced_item_count"] == 0

    # swapping the product without naming a sku drops the stale variant
    swapped = client.patch(
        f"/api/v1/purchase-request-items/{pending['id']}",
        json={"product_id": flat["id"], "product_name_snapshot": None},
        headers=api_key_headers(),
    )
    assert swapped.json()["data"]["product_id"] == flat["id"]
    assert swapped.json()["data"]["sku_id"] is None

    # sku tenant isolation: other tenant can neither read nor reference
    assert client.get(
        f"/api/v1/product-skus/{sku_m['id']}", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404
    other_employee = create_employee(client, tenant_id=OTHER_TENANT, name="Bob")
    other_request = create_request(client, other_employee, tenant_id=OTHER_TENANT)
    assert client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": other_request, "sku_id": sku_m["id"], "quantity": 1},
        headers=api_key_headers(OTHER_API_KEY),
    ).status_code == 404

    # archive keeps history intact
    assert client.delete(f"/api/v1/product-skus/{sku_xl['id']}", headers=api_key_headers()).status_code == 204
    active = client.get(
        f"/api/v1/product-skus?product_id={style['id']}&status=active", headers=api_key_headers()
    ).json()["data"]
    assert [v["id"] for v in active] == [sku_m["id"]]
    assert client.get(
        f"/api/v1/purchase-request-items/{refined['id']}", headers=api_key_headers()
    ).json()["data"]["sku_id"] == sku_xl["id"]


def test_purchase_tenant_isolation(client: TestClient) -> None:
    employee_id = create_employee(client)
    product = create_product(client)
    request_id = create_request(client, employee_id)
    item = create_item(client, request_id, product_id=product["id"], product_name_snapshot=None)

    other = api_key_headers(OTHER_API_KEY)
    assert client.get(f"/api/v1/purchase-requests/{request_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/purchase-requests/{request_id}/detail", headers=other).status_code == 404
    assert client.get(f"/api/v1/purchase-request-items/{item['id']}", headers=other).status_code == 404
    assert client.post(f"/api/v1/purchase-requests/{request_id}/submit", json={}, headers=other).status_code == 404
    assert client.get("/api/v1/purchase-requests", headers=other).json()["data"] == []

    # cross-tenant master data cannot be referenced
    other_employee = create_employee(client, tenant_id=OTHER_TENANT, name="Bob")
    other_request = create_request(client, other_employee, tenant_id=OTHER_TENANT)
    assert client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": other_request, "product_id": product["id"], "quantity": 1},
        headers=other,
    ).status_code == 404


def test_procure_to_order_links_purchase_lines_to_sales_order_lines(client: TestClient) -> None:
    """zero-inventory (procure-to-order): a confirmed sales order line drives a
    purchase line. The link is written on the purchase side — the order is
    already locked by then — and both documents' details surface it: the
    purchase reviewer sees which order a line serves, the fulfilment side
    sees the supply status behind each order line."""
    employee_id = create_employee(client, name=_ZH_TEXT['TEXT_4CA168F827DFE777'])
    order = client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": _ZH_TEXT['TEXT_006A0BCECC6C3742'], "order_no": "SO-2026-000123",
              "customer_name_snapshot": _ZH_TEXT['TEXT_B6F9F6281C5CEB6E']},
        headers=api_key_headers(),
    ).json()["data"]
    order_line = client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order["id"], "product_name_snapshot": _ZH_TEXT['TEXT_7FC1374BCA2D346C'], "quantity": 3,
              "unit_price": 8000.0},
        headers=api_key_headers(),
    ).json()["data"]
    # confirm the order — locked for item edits, exactly when procurement starts
    assert client.post(
        f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    request_id = create_request(client, employee_id, title=_ZH_TEXT['TEXT_218B06758AF414CF'])
    linked = create_item(
        client, request_id,
        product_name_snapshot=_ZH_TEXT['TEXT_7FC1374BCA2D346C'], quantity=3, unit_price=6500.0,
        sales_order_item_id=order_line["id"],
    )
    assert linked["sales_order_item_id"] == order_line["id"]
    # a second (split) line against the same order line is legal
    create_item(
        client, request_id,
        product_name_snapshot=_ZH_TEXT['TEXT_D5EB79D741748213'], quantity=1,
        sales_order_item_id=order_line["id"],
    )

    # a nonexistent line is a 404, never a silent null
    missing = client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request_id, "product_name_snapshot": "x", "quantity": 1,
              "sales_order_item_id": "00000000-0000-0000-0000-000000000000"},
        headers=api_key_headers(),
    )
    assert missing.status_code == 404

    # purchase detail: each pinned line carries the order context to review against
    purchase_detail = client.get(
        f"/api/v1/purchase-requests/{request_id}/detail", headers=api_key_headers()
    ).json()["data"]
    pinned = [i for i in purchase_detail["items"] if i["sales_order_item_id"]]
    assert len(pinned) == 2
    assert pinned[0]["sales_order"]["order_no"] == "SO-2026-000123"
    assert pinned[0]["sales_order"]["order_status"] == "submitted"
    assert pinned[0]["sales_order"]["customer_name_snapshot"] == _ZH_TEXT['TEXT_B6F9F6281C5CEB6E']
    assert pinned[0]["sales_order"]["quantity"] == 3.0

    # order detail: the fulfilment side reads the supply behind each line
    order_detail = client.get(
        f"/api/v1/sales-orders/{order['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    supply = order_detail["items"][0]["purchase_items"]
    # set, not order: rows born in the same second tie on created_at
    assert sorted(p["quantity"] for p in supply) == [1.0, 3.0]
    assert all(p["request_status"] == "draft" for p in supply)
    assert supply[0]["request_id"] == request_id

    # PATCH can detach the link (back to a stock purchase)
    detached = client.patch(
        f"/api/v1/purchase-request-items/{linked['id']}",
        json={"sales_order_item_id": None},
        headers=api_key_headers(),
    )
    assert detached.status_code == 200
    assert detached.json()["data"]["sales_order_item_id"] is None
    order_detail = client.get(
        f"/api/v1/sales-orders/{order['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert [p["quantity"] for p in order_detail["items"][0]["purchase_items"]] == [1.0]
