from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client


TEST_TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
TEST_API_KEY = "test-api-key"
OTHER_API_KEY = "other-api-key"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Test Tenant"),
            Tenant(id=OTHER_TENANT, name="Other Tenant"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
            ApiKey(tenant_id=OTHER_TENANT, key_hash=hash_api_key(OTHER_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def api_key_headers(api_key: str = TEST_API_KEY) -> dict[str, str]:
    return {"X-API-Key": api_key}


def headers_for_tenant(tenant_id: str) -> dict[str, str]:
    return api_key_headers(TEST_API_KEY if tenant_id == TEST_TENANT else OTHER_API_KEY)


def create_employee(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {"name": "Alice"}
    payload.update(overrides)
    response = test_client.post("/api/v1/employees", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_vendor(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "戴尔（中国）有限公司", "tax_id": "91110000600000000D"}
    payload.update(overrides)
    response = test_client.post("/api/v1/vendors", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_product(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "27寸显示器", "spec": "U2723QE 4K", "unit": "台", "list_price": 3199.0}
    payload.update(overrides)
    response = test_client.post("/api/v1/products", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_request(test_client: TestClient, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "employee_id": employee_id,
        "title": "研发部显示器采购",
        "request_date": "2026-07-11",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/purchase-requests", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_item(test_client: TestClient, request_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"request_id": request_id, "product_name_snapshot": "人体工学椅", "quantity": 2}
    payload.update(overrides)
    response = test_client.post(
        "/api/v1/purchase-request-items", json=payload, headers=headers_for_tenant(tenant_id)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_product_master_data_crud_and_filters(client: TestClient) -> None:
    product = create_product(client, product_code="PRD-001")
    assert product["status"] == "active"
    assert product["list_price"] == 3199.0

    by_keyword = client.get("/api/v1/products?keyword=显示器", headers=api_key_headers()).json()["data"]
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
        source_report_text="要给研发买两台4K显示器和一批线材，显示器找戴尔，线材还没定。",
        needed_by="2026-07-25",
    )
    header = client.get(f"/api/v1/purchase-requests/{request_id}", headers=api_key_headers()).json()["data"]
    assert header["vendor_id"] == vendor["id"]
    assert header["vendor_name_snapshot"] == "戴尔（中国）有限公司"

    # line 1: cataloged product with unit price — name/unit backfilled
    priced = create_item(
        client, request_id,
        product_id=product["id"], product_name_snapshot=None, quantity=2, unit_price=2999.0,
    )
    assert priced["product_name_snapshot"] == "27寸显示器"
    assert priced["unit"] == "台"

    # line 2: free-text item with a lump-sum amount, no unit price
    create_item(client, request_id, product_name_snapshot="各类线材一批", amount=800.0)

    # line 3: free-text item with no price at all — a normal fact
    unpriced = create_item(client, request_id, product_name_snapshot="显示器支架", quantity=2)
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
            "approver_role": "manager",
            "source": "ai",
            "acted_at": "2026-07-12T10:00:00Z",
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
    assert len(detail["approval_records"]) == 1

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
    first = create_request(client, employee_id, title="办公用品补货", vendor_name_snapshot="随便哪家文具店")
    second = create_request(client, employee_id, title="服务器扩容")
    header = client.get(f"/api/v1/purchase-requests/{first}", headers=api_key_headers()).json()["data"]
    assert header["vendor_id"] is None
    assert header["vendor_name_snapshot"] == "随便哪家文具店"

    create_item(client, first, product_name_snapshot="A4纸", quantity=10, unit="箱")
    create_item(client, second, product_name_snapshot="2U服务器", quantity=1)
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
            "title": "审批采购申请",
            "todo_type": "approval",
        },
        headers=api_key_headers(),
    )
    assert todo.status_code == 201, todo.text
    queue = client.get(
        "/api/v1/purchase-requests?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert {r["id"] for r in queue} == {second}

    # vendor can be attached later (询价后) while editable… request is
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
        json={"request_id": request_id, "product_name_snapshot": "追加", "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 409
    assert client.patch(
        f"/api/v1/purchase-request-items/{item['id']}", json={"quantity": 5}, headers=api_key_headers()
    ).status_code == 409
    assert client.delete(
        f"/api/v1/purchase-request-items/{item['id']}", headers=api_key_headers()
    ).status_code == 409

    # returned reopens editing (询价补价环), resubmission closes it again
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
    payload = {"product_id": product_id, "variant_attrs": {"尺码": "M"}}
    payload.update(overrides)
    response = test_client.post(
        "/api/v1/product-skus", json=payload, headers=headers_for_tenant(tenant_id)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_product_sku_master_data_and_item_refinement(client: TestClient) -> None:
    employee_id = create_employee(client)
    # apparel-style: product = 款色, skus = 尺码
    style = create_product(client, name="圆领T恤·藏青", spec="STYLE-001-NV", unit="件", list_price=89.0)
    sku_m = create_sku(client, style["id"], sku_code="001-NV-M", variant_attrs={"尺码": "M"})
    sku_xl = create_sku(client, style["id"], sku_code="001-NV-XL",
                        variant_attrs={"尺码": "XL"}, list_price=95.0)

    # has_skus tells the agent a variant conversation is needed
    read = client.get(f"/api/v1/products/{style['id']}", headers=api_key_headers()).json()["data"]
    assert read["has_skus"] is True
    listed = client.get("/api/v1/products?keyword=T恤", headers=api_key_headers()).json()["data"]
    assert listed[0]["has_skus"] is True
    # a flat product (product == sku company) stays has_skus false
    flat = create_product(client, name="27寸显示器无变体")
    assert client.get(
        f"/api/v1/products/{flat['id']}", headers=api_key_headers()
    ).json()["data"]["has_skus"] is False

    variants = client.get(
        f"/api/v1/product-skus?product_id={style['id']}", headers=api_key_headers()
    ).json()["data"]
    assert [v["sku_code"] for v in variants] == ["001-NV-M", "001-NV-XL"]
    assert variants[1]["variant_attrs"] == {"尺码": "XL"}
    assert variants[1]["list_price"] == 95.0

    request_id = create_request(client, employee_id, title="文化衫采购")

    # sku alone derives its product; product name/unit backfill from the product
    refined = create_item(client, request_id, product_name_snapshot=None,
                          sku_id=sku_xl["id"], quantity=30, unit_price=95.0)
    assert refined["product_id"] == style["id"]
    assert refined["sku_id"] == sku_xl["id"]
    assert refined["product_name_snapshot"] == "圆领T恤·藏青"
    assert refined["unit"] == "件"

    # sku must belong to the product when both are given
    other_product = create_product(client, name="别的款")
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
    archived_only_product = create_product(client, name="历史变体产品")
    archived_only_sku = create_sku(
        client, archived_only_product["id"], sku_code="HISTORY-ONLY", variant_attrs={"版本": "旧"}
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
        "name": "圆领T恤·藏青",
        "spec": "STYLE-001-NV",
        "unit": "件",
    }
    assert refined_detail["sku"] == {
        "id": sku_xl["id"],
        "product_id": style["id"],
        "sku_code": "001-NV-XL",
        "variant_attrs": {"尺码": "XL"},
    }
    assert refined_detail["sku_pending"] is False
    pending_detail = next(item for item in detail["items"] if item["id"] == pending["id"])
    assert pending_detail["product"]["name"] == "圆领T恤·藏青"
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
    """零库存 (procure-to-order): a confirmed sales order line drives a
    purchase line. The link is written on the purchase side — the order is
    already locked by then — and both documents' details surface it: the
    purchase reviewer sees which order a line serves, the fulfilment side
    sees the supply status behind each order line."""
    employee_id = create_employee(client, name="赵采购")
    order = client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": "市一医院 JC-800", "order_no": "SO-2026-000123",
              "customer_name_snapshot": "市第一医院"},
        headers=api_key_headers(),
    ).json()["data"]
    order_line = client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order["id"], "product_name_snapshot": "JC-800 打印机", "quantity": 3,
              "unit_price": 8000.0},
        headers=api_key_headers(),
    ).json()["data"]
    # confirm the order — locked for item edits, exactly when procurement starts
    assert client.post(
        f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    request_id = create_request(client, employee_id, title="按单采购 JC-800")
    linked = create_item(
        client, request_id,
        product_name_snapshot="JC-800 打印机", quantity=3, unit_price=6500.0,
        sales_order_item_id=order_line["id"],
    )
    assert linked["sales_order_item_id"] == order_line["id"]
    # a second (split) line against the same order line is legal
    create_item(
        client, request_id,
        product_name_snapshot="JC-800 打印机 备用机", quantity=1,
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
    assert pinned[0]["sales_order"]["customer_name_snapshot"] == "市第一医院"
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
