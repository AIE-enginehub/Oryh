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
    payload = {"name": "王强"}
    payload.update(overrides)
    response = test_client.post("/api/v1/employees", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_customer(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "市第一人民医院", "contact": "设备科 周敏", "address": "北京西路 100 号"}
    payload.update(overrides)
    response = test_client.post("/api/v1/customers", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_product(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "JC-800 医用胶片打印机", "spec": "干式激光", "unit": "台", "list_price": 128000.0}
    payload.update(overrides)
    response = test_client.post("/api/v1/products", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_quotation(test_client: TestClient, employee_id: str, **overrides) -> dict:
    payload = {"employee_id": employee_id, "title": "市一 JC-800 报价"}
    payload.update(overrides)
    response = test_client.post("/api/v1/sales-quotations", json=payload, headers=api_key_headers())
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_order(test_client: TestClient, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"employee_id": employee_id, "title": "市一 JC-800 订单"}
    payload.update(overrides)
    response = test_client.post("/api/v1/sales-orders", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_item(test_client: TestClient, order_id: str, **overrides) -> dict:
    payload = {"order_id": order_id, "product_name_snapshot": "配件一批", "quantity": 1}
    payload.update(overrides)
    response = test_client.post("/api/v1/sales-order-items", json=payload, headers=api_key_headers())
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_order_full_lifecycle_with_stamps(client: TestClient) -> None:
    employee_id = create_employee(client)
    customer = create_customer(client)
    product = create_product(client)

    order = create_order(
        client, employee_id, customer_id=customer["id"],
        ship_to_address="北京西路 100 号", contract_no="HT-2026-001",
    )
    assert order["order_no"] == "SO-000001"
    assert order["customer_name_snapshot"] == "市第一人民医院"
    assert order["status"] == "draft"

    item = create_item(
        client, order["id"], product_id=product["id"], product_name_snapshot=None,
        quantity=1, unit_price=121600.0, tax_rate=13, line_no=1, promised_date="2026-08-05",
    )
    assert item["list_price_snapshot"] == 128000.0
    assert item["product_name_snapshot"] == "JC-800 医用胶片打印机"

    submitted = client.post(
        f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers()
    ).json()["data"]
    assert submitted["status"] == "submitted" and submitted["submitted_at"] is not None
    # idempotent resubmit
    assert client.post(
        f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # approval fact + todo dispatch accept sales_order
    assert client.post(
        "/api/v1/approval-records",
        json={"entity_type": "sales_order", "entity_id": order["id"], "round_no": 1,
              "sequence_no": 1, "action": "submitted", "acted_at": "2026-07-22T09:00:00Z"},
        headers=api_key_headers(),
    ).status_code == 201
    assert client.post(
        "/api/v1/todos",
        json={"employee_id": employee_id, "entity_type": "sales_order",
              "entity_id": order["id"], "title": "确认订单"},
        headers=api_key_headers(),
    ).status_code == 201

    # confirm → shipped stamps shipped_at; → signed stamps signed_at
    assert client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "confirmed"}, headers=api_key_headers()
    ).status_code == 200
    client.patch(
        f"/api/v1/sales-orders/{order['id']}",
        json={"logistics_company": "顺丰速运", "logistics_tracking_no": "SF123"},
        headers=api_key_headers(),
    )
    shipped = client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "shipped"}, headers=api_key_headers()
    ).json()["data"]
    assert shipped["shipped_at"] is not None
    signed = client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "signed"}, headers=api_key_headers()
    ).json()["data"]
    assert signed["signed_at"] is not None

    detail = client.get(
        f"/api/v1/sales-orders/{order['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["computed_total"] == 121600.0
    assert detail["unpriced_item_count"] == 0
    assert [r["action"] for r in detail["approval_records"]] == ["submitted"]


def test_order_number_allocation_and_custom(client: TestClient) -> None:
    employee_id = create_employee(client)
    first = create_order(client, employee_id)
    second = create_order(client, employee_id)
    assert [first["order_no"], second["order_no"]] == ["SO-000001", "SO-000002"]

    custom = create_order(client, employee_id, order_no="SO202607001")
    assert custom["order_no"] == "SO202607001"
    duplicate = client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": "dup", "order_no": "SO202607001"},
        headers=api_key_headers(),
    )
    assert duplicate.status_code == 409
    third = create_order(client, employee_id)
    assert third["order_no"] == "SO-000003"


def test_order_links_won_quotation(client: TestClient) -> None:
    employee_id = create_employee(client)
    quotation = create_quotation(client, employee_id)

    order = create_order(client, employee_id, quotation_id=quotation["id"])
    # snapshot backfills from the quotation
    assert order["source_quote_number"] == quotation["quote_number"]

    detail = client.get(
        f"/api/v1/sales-orders/{order['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["quotation"]["id"] == quotation["id"]

    # filter by quotation
    linked = client.get(
        f"/api/v1/sales-orders?quotation_id={quotation['id']}", headers=api_key_headers()
    ).json()["data"]
    assert [o["id"] for o in linked] == [order["id"]]

    # a fake quotation reference is a 404, not a silent null
    assert client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": "x",
              "quotation_id": "00000000-0000-0000-0000-000000000000"},
        headers=api_key_headers(),
    ).status_code == 404


def test_order_machine_guards_and_item_locking(client: TestClient) -> None:
    employee_id = create_employee(client)
    order = create_order(client, employee_id)
    item = create_item(client, order["id"])

    # draft -> shipped skips the whole flow: illegal
    assert client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "shipped"}, headers=api_key_headers()
    ).status_code == 409

    client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers())
    assert client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order["id"], "product_name_snapshot": "追加", "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 409
    assert client.patch(
        f"/api/v1/sales-order-items/{item['id']}", json={"quantity": 5}, headers=api_key_headers()
    ).status_code == 409

    # returned reopens editing, resubmission closes it again
    assert client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "returned"}, headers=api_key_headers()
    ).status_code == 200
    assert client.patch(
        f"/api/v1/sales-order-items/{item['id']}", json={"unit_price": 450.0}, headers=api_key_headers()
    ).status_code == 200
    assert client.post(
        f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # signed is terminal
    client.patch(f"/api/v1/sales-orders/{order['id']}", json={"status": "confirmed"}, headers=api_key_headers())
    client.patch(f"/api/v1/sales-orders/{order['id']}", json={"status": "shipped"}, headers=api_key_headers())
    client.patch(f"/api/v1/sales-orders/{order['id']}", json={"status": "signed"}, headers=api_key_headers())
    assert client.patch(
        f"/api/v1/sales-orders/{order['id']}", json={"status": "submitted"}, headers=api_key_headers()
    ).status_code == 409

    # create may record an already-agreed fact directly at confirmed
    direct = create_order(client, employee_id, status="confirmed")
    assert direct["status"] == "confirmed"


def test_order_validation_and_soft_delete(client: TestClient) -> None:
    employee_id = create_employee(client)
    order = create_order(client, employee_id)

    assert client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order["id"], "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 422
    assert client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order["id"], "product_name_snapshot": "x", "quantity": 0},
        headers=api_key_headers(),
    ).status_code == 422
    assert client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": "x", "status": "nonsense"},
        headers=api_key_headers(),
    ).status_code == 422

    create_item(client, order["id"])
    assert client.delete(f"/api/v1/sales-orders/{order['id']}", headers=api_key_headers()).status_code == 204
    assert client.get(f"/api/v1/sales-orders/{order['id']}", headers=api_key_headers()).status_code == 404
    assert client.get(
        f"/api/v1/sales-orders/{order['id']}?include_deleted=true", headers=api_key_headers()
    ).status_code == 200
    restored = client.post(
        f"/api/v1/sales-orders/{order['id']}/restore", json={}, headers=api_key_headers()
    )
    assert restored.status_code == 200 and restored.json()["data"]["status"] == "draft"


def test_order_work_queue_and_tenant_isolation(client: TestClient) -> None:
    employee_id = create_employee(client)
    order = create_order(client, employee_id)
    client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers())

    queue = client.get(
        "/api/v1/sales-orders?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert [o["id"] for o in queue] == [order["id"]]
    client.post(
        "/api/v1/todos",
        json={"employee_id": employee_id, "entity_type": "sales_order",
              "entity_id": order["id"], "title": "确认订单"},
        headers=api_key_headers(),
    )
    assert client.get(
        "/api/v1/sales-orders?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"] == []

    other = api_key_headers(OTHER_API_KEY)
    assert client.get(f"/api/v1/sales-orders/{order['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/sales-orders/{order['id']}/detail", headers=other).status_code == 404
    assert client.get("/api/v1/sales-orders", headers=other).json()["data"] == []


def test_order_adjustments_shape_the_total(client: TestClient) -> None:
    """OFBiz-style OrderAdjustment: signed amounts beside the line math,
    header- or line-level, locked with the document's editable states."""
    employee_id = create_employee(client)
    order = create_order(client, employee_id)
    line = create_item(client, order["id"], quantity=4, unit_price=250.0)

    def add(payload, expect=201):
        response = client.post(
            "/api/v1/sales-order-adjustments",
            json={"order_id": order["id"], **payload},
            headers=api_key_headers(),
        )
        assert response.status_code == expect, response.text
        return response.json()["data"] if expect == 201 else response.json()

    add({"adjustment_type": "shipping", "amount": 80.0, "description": "运费"})
    add({"adjustment_type": "discount", "amount": -100.0, "quotation_item_id": None,
         "order_item_id": line["id"], "description": "年度返利折扣"}, expect=422)  # unknown field rejected
    add({"adjustment_type": "discount", "amount": -100.0, "order_item_id": line["id"],
         "description": "年度返利折扣"})

    detail = client.get(
        f"/api/v1/sales-orders/{order['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["computed_total"] == 1000.0
    assert detail["adjustments_total"] == -20.0
    assert detail["adjusted_total"] == 980.0
    assert {a["adjustment_type"] for a in detail["adjustments"]} == {"shipping", "discount"}

    # submitted → adjustments lock with the document
    submit = client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={}, headers=api_key_headers())
    assert submit.status_code == 200, submit.text
    locked = client.post(
        "/api/v1/sales-order-adjustments",
        json={"order_id": order["id"], "adjustment_type": "fee", "amount": 5},
        headers=api_key_headers(),
    )
    assert locked.status_code == 409
