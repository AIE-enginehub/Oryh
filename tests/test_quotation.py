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
    payload = {"name": "李雷"}
    payload.update(overrides)
    response = test_client.post("/api/v1/employees", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_customer(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "华欣机械有限公司", "contact": "王工", "address": "苏州市工业园区"}
    payload.update(overrides)
    response = test_client.post("/api/v1/customers", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_product(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "四刃立铣刀", "spec": "D10 硬质合金", "unit": "支", "list_price": 120.0}
    payload.update(overrides)
    response = test_client.post("/api/v1/products", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_persists_every_accepted_header_field(client: TestClient) -> None:
    """A field the request schema accepts must survive the create.

    `remarks` was silently dropped here since the family shipped: agents that
    put the tenant's mandatory discount justification in it at create time
    lost it, and only noticed if they read the document back. RequestModel's
    extra="forbid" guards the other direction (unknown fields rejected) —
    nothing guarded this one.
    """
    employee_id = create_employee(client)
    quotation = create_quotation(
        client, employee_id,
        remarks="折扣理由：战略客户，年内第三次采购",
        payment_terms="到货验收后 30 天付款",
        delivery_terms="含 13% 增值税的到货价",
        source_report_text="客户压价，按八八折报出",
    )
    for field, expected in (
        ("remarks", "折扣理由：战略客户，年内第三次采购"),
        ("payment_terms", "到货验收后 30 天付款"),
        ("delivery_terms", "含 13% 增值税的到货价"),
        ("source_report_text", "客户压价，按八八折报出"),
    ):
        assert quotation.get(field) == expected, f"{field} lost at create: {quotation.get(field)!r}"

    read_back = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}", headers=api_key_headers()
    ).json()["data"]
    assert read_back["remarks"] == "折扣理由：战略客户，年内第三次采购"


def create_quotation(test_client: TestClient, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {
        "employee_id": employee_id,
        "title": "华欣机械 刀具年度报价",
        "quote_date": "2026-07-21",
        "valid_until": "2026-08-20",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/sales-quotations", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_item(test_client: TestClient, quotation_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"quotation_id": quotation_id, "product_name_snapshot": "定制夹具", "quantity": 2}
    payload.update(overrides)
    response = test_client.post(
        "/api/v1/sales-quotation-items", json=payload, headers=headers_for_tenant(tenant_id)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_customer_master_data_crud_and_filters(client: TestClient) -> None:
    customer = create_customer(client, customer_code="CUS-001", tax_id="91320500MA1WCACX3F")
    assert customer["status"] == "active"
    assert customer["address"] == "苏州市工业园区"

    by_keyword = client.get("/api/v1/customers?keyword=华欣", headers=api_key_headers()).json()["data"]
    assert [c["id"] for c in by_keyword] == [customer["id"]]
    by_tax = client.get(
        "/api/v1/customers?tax_id=91320500MA1WCACX3F", headers=api_key_headers()
    ).json()["data"]
    assert [c["id"] for c in by_tax] == [customer["id"]]

    updated = client.patch(
        f"/api/v1/customers/{customer['id']}", json={"contact": "赵工"}, headers=api_key_headers()
    )
    assert updated.json()["data"]["contact"] == "赵工"

    # archive removes from active list; other tenant sees nothing
    assert client.delete(f"/api/v1/customers/{customer['id']}", headers=api_key_headers()).status_code == 204
    assert client.get("/api/v1/customers?status=active", headers=api_key_headers()).json()["data"] == []
    assert client.get(
        f"/api/v1/customers/{customer['id']}", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404


def test_quotation_full_lifecycle_with_derived_pricing_facts(client: TestClient) -> None:
    employee_id = create_employee(client)
    customer = create_customer(client)
    product = create_product(client)

    quotation = create_quotation(client, employee_id, customer_id=customer["id"])
    # server-allocated number, customer snapshot backfilled from master data
    assert quotation["quote_number"] == "QT-000001"
    assert quotation["revision_no"] == 1
    assert quotation["customer_name_snapshot"] == "华欣机械有限公司"
    assert quotation["status"] == "draft"

    # cataloged line captures the list-price snapshot automatically
    priced = create_item(
        client,
        quotation["id"],
        product_id=product["id"],
        product_name_snapshot=None,
        quantity=200,
        unit_price=108.0,
        tax_rate=13,
        line_no=1,
    )
    assert priced["list_price_snapshot"] == 120.0
    assert priced["product_name_snapshot"] == "四刃立铣刀"
    # gift line: zero-priced by design, never "unpriced"
    create_item(
        client,
        quotation["id"],
        product_name_snapshot="样品一盒",
        quantity=1,
        unit_price=0,
        is_gift=True,
        line_no=2,
    )
    # free-text line without price: an honest unpriced fact
    create_item(client, quotation["id"], line_no=3)

    detail = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["computed_total"] == 200 * 108.0
    assert detail["unpriced_item_count"] == 1
    assert [item["line_no"] for item in detail["items"]] == [1, 2, 3]
    assert detail["items"][0]["product"]["list_price"] == 120.0
    assert [r["revision_no"] for r in detail["revisions"]] == [1]

    # negotiated document total (抹零) is a declared fact beside the line sum
    assert client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}",
        json={"total_amount": 21000.0},
        headers=api_key_headers(),
    ).status_code == 200

    # submit → approve → send → close accepted
    submitted = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers()
    ).json()["data"]
    assert submitted["status"] == "submitted"
    assert submitted["submitted_at"] is not None
    # idempotent resubmit
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # approval fact + todo entity dispatch accept sales_quotation
    record = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "sales_quotation",
            "entity_id": quotation["id"],
            "round_no": 1,
            "sequence_no": 1,
            "action": "submitted",
        },
        headers=api_key_headers(),
    )
    assert record.status_code == 201
    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "sales_quotation",
            "entity_id": quotation["id"],
            "title": "审批报价 QT-000001",
        },
        headers=api_key_headers(),
    )
    assert todo.status_code == 201

    assert client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "approved"}, headers=api_key_headers()
    ).status_code == 200

    sent = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/send", json={}, headers=api_key_headers()
    ).json()["data"]
    assert sent["status"] == "sent"
    assert sent["sent_at"] is not None

    closed = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/close",
        json={"outcome": "accepted", "outcome_note": "按报价签约"},
        headers=api_key_headers(),
    ).json()["data"]
    assert closed["status"] == "accepted"
    assert closed["closed_at"] is not None
    assert closed["outcome_note"] == "按报价签约"

    detail = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert [r["action"] for r in detail["approval_records"]] == ["submitted"]


def test_quote_number_allocation_and_custom_numbers(client: TestClient) -> None:
    employee_id = create_employee(client)
    first = create_quotation(client, employee_id)
    second = create_quotation(client, employee_id)
    assert [first["quote_number"], second["quote_number"]] == ["QT-000001", "QT-000002"]

    custom = create_quotation(client, employee_id, quote_number="HX-2026-001")
    assert custom["quote_number"] == "HX-2026-001"
    # duplicate custom number is a conflict, not a silent overwrite
    duplicate = client.post(
        "/api/v1/sales-quotations",
        json={"employee_id": employee_id, "title": "dup", "quote_number": "HX-2026-001"},
        headers=api_key_headers(),
    )
    assert duplicate.status_code == 409

    # allocation continues past custom numbers
    third = create_quotation(client, employee_id)
    assert third["quote_number"] == "QT-000003"


def test_revision_flow(client: TestClient) -> None:
    employee_id = create_employee(client)
    product = create_product(client, list_price=120.0)
    quotation = create_quotation(client, employee_id)
    create_item(
        client,
        quotation["id"],
        product_id=product["id"],
        product_name_snapshot=None,
        quantity=200,
        unit_price=108.0,
        line_no=1,
    )

    # revising a draft is illegal — drafts are edited, not revised
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/revise", json={}, headers=api_key_headers()
    ).status_code == 409

    client.post(f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers())
    client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "approved"}, headers=api_key_headers()
    )
    client.post(f"/api/v1/sales-quotations/{quotation['id']}/send", json={}, headers=api_key_headers())

    # the catalog moved between revisions: the new revision re-snapshots it
    client.patch(f"/api/v1/products/{product['id']}", json={"list_price": 110.0}, headers=api_key_headers())

    revised = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/revise",
        json={"reason": "客户要求降价"},
        headers=api_key_headers(),
    )
    assert revised.status_code == 201
    revision = revised.json()["data"]
    assert revision["quote_number"] == quotation["quote_number"]
    assert revision["revision_no"] == 2
    assert revision["revision_of_id"] == quotation["id"]
    assert revision["status"] == "draft"

    superseded = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}", headers=api_key_headers()
    ).json()["data"]
    assert superseded["status"] == "superseded"

    # lines copied; snapshot refreshed to today's catalog truth
    items = client.get(
        f"/api/v1/sales-quotation-items?quotation_id={revision['id']}", headers=api_key_headers()
    ).json()["data"]
    assert len(items) == 1
    assert items[0]["unit_price"] == 108.0
    assert items[0]["list_price_snapshot"] == 110.0

    # the superseded revision cannot be revised again
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/revise", json={}, headers=api_key_headers()
    ).status_code == 409

    # both revisions visible under one number; detail lists the trail
    revisions = client.get(
        f"/api/v1/sales-quotations?quote_number={quotation['quote_number']}", headers=api_key_headers()
    ).json()["data"]
    assert {r["revision_no"] for r in revisions} == {1, 2}
    detail = client.get(
        f"/api/v1/sales-quotations/{revision['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert [r["revision_no"] for r in detail["revisions"]] == [1, 2]


def test_items_locked_after_submit_and_machine_guards(client: TestClient) -> None:
    employee_id = create_employee(client)
    quotation = create_quotation(client, employee_id)
    item = create_item(client, quotation["id"])

    # draft -> sent skips the whole flow: illegal
    assert client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "sent"}, headers=api_key_headers()
    ).status_code == 409
    # lifecycle endpoints are machine-guarded too
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/send", json={}, headers=api_key_headers()
    ).status_code == 409
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/close",
        json={"outcome": "accepted"},
        headers=api_key_headers(),
    ).status_code == 409

    client.post(f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers())

    assert client.post(
        "/api/v1/sales-quotation-items",
        json={"quotation_id": quotation["id"], "product_name_snapshot": "追加", "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 409
    assert client.patch(
        f"/api/v1/sales-quotation-items/{item['id']}", json={"quantity": 5}, headers=api_key_headers()
    ).status_code == 409
    assert client.delete(
        f"/api/v1/sales-quotation-items/{item['id']}", headers=api_key_headers()
    ).status_code == 409

    # returned reopens editing, resubmission closes it again
    assert client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "returned"}, headers=api_key_headers()
    ).status_code == 200
    assert client.patch(
        f"/api/v1/sales-quotation-items/{item['id']}", json={"unit_price": 95.0}, headers=api_key_headers()
    ).status_code == 200
    assert client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # the expiry sweep path: approved → sent → expired stamps closed_at
    client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "approved"}, headers=api_key_headers()
    )
    client.post(f"/api/v1/sales-quotations/{quotation['id']}/send", json={}, headers=api_key_headers())
    swept = client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "expired"}, headers=api_key_headers()
    ).json()["data"]
    assert swept["status"] == "expired"
    assert swept["closed_at"] is not None

    # expired is terminal
    assert client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}", json={"status": "submitted"}, headers=api_key_headers()
    ).status_code == 409


def test_pricing_fact_overrides_and_product_swap(client: TestClient) -> None:
    employee_id = create_employee(client)
    cheap = create_product(client, name="国产立铣刀", list_price=60.0)
    dear = create_product(client, name="进口立铣刀", list_price=200.0)
    quotation = create_quotation(client, employee_id)

    # explicit snapshot (special price list) beats the catalog capture
    item = create_item(
        client,
        quotation["id"],
        product_id=cheap["id"],
        product_name_snapshot=None,
        quantity=10,
        unit_price=50.0,
        list_price_snapshot=55.0,
    )
    assert item["list_price_snapshot"] == 55.0

    # swapping the product refreshes the price snapshot to the new product's
    # catalog truth; the name snapshot keeps the principal's words (family
    # semantics, same as purchase items)
    swapped = client.patch(
        f"/api/v1/sales-quotation-items/{item['id']}",
        json={"product_id": dear["id"]},
        headers=api_key_headers(),
    ).json()["data"]
    assert swapped["product_id"] == dear["id"]
    assert swapped["product_name_snapshot"] == "国产立铣刀"
    assert swapped["list_price_snapshot"] == 200.0

    # tax_rate is bounded
    assert client.post(
        "/api/v1/sales-quotation-items",
        json={"quotation_id": quotation["id"], "product_name_snapshot": "x", "quantity": 1, "tax_rate": 130},
        headers=api_key_headers(),
    ).status_code == 422


def test_quotation_validation_and_soft_delete(client: TestClient) -> None:
    employee_id = create_employee(client)
    quotation = create_quotation(client, employee_id)

    # an item needs either a product_id or free text
    assert client.post(
        "/api/v1/sales-quotation-items",
        json={"quotation_id": quotation["id"], "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 422
    # quantity must be positive; fake refs 404
    assert client.post(
        "/api/v1/sales-quotation-items",
        json={"quotation_id": quotation["id"], "product_name_snapshot": "x", "quantity": 0},
        headers=api_key_headers(),
    ).status_code == 422
    assert client.post(
        "/api/v1/sales-quotation-items",
        json={"quotation_id": quotation["id"], "product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1},
        headers=api_key_headers(),
    ).status_code == 404
    assert client.post(
        "/api/v1/sales-quotations",
        json={"employee_id": employee_id, "title": "x", "customer_id": "00000000-0000-0000-0000-000000000000"},
        headers=api_key_headers(),
    ).status_code == 404

    # invalid create status
    assert client.post(
        "/api/v1/sales-quotations",
        json={"employee_id": employee_id, "title": "x", "status": "nonsense"},
        headers=api_key_headers(),
    ).status_code == 422

    # soft delete hides, restore brings back
    create_item(client, quotation["id"])
    assert client.delete(
        f"/api/v1/sales-quotations/{quotation['id']}", headers=api_key_headers()
    ).status_code == 204
    assert client.get(
        f"/api/v1/sales-quotations/{quotation['id']}", headers=api_key_headers()
    ).status_code == 404
    assert client.get(
        f"/api/v1/sales-quotations/{quotation['id']}?include_deleted=true", headers=api_key_headers()
    ).status_code == 200
    assert client.get("/api/v1/sales-quotations", headers=api_key_headers()).json()["data"] == []
    restored = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/restore", json={}, headers=api_key_headers()
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "draft"


def test_quotation_work_queue_filter(client: TestClient) -> None:
    employee_id = create_employee(client)
    quotation = create_quotation(client, employee_id)
    client.post(f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers())

    queue = client.get(
        "/api/v1/sales-quotations?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert [q["id"] for q in queue] == [quotation["id"]]

    client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "sales_quotation",
            "entity_id": quotation["id"],
            "title": "审批报价",
        },
        headers=api_key_headers(),
    )
    queue = client.get(
        "/api/v1/sales-quotations?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert queue == []


def test_quotation_tenant_isolation(client: TestClient) -> None:
    employee_id = create_employee(client)
    customer = create_customer(client)
    quotation = create_quotation(client, employee_id, customer_id=customer["id"])
    item = create_item(client, quotation["id"])

    other = api_key_headers(OTHER_API_KEY)
    assert client.get(f"/api/v1/sales-quotations/{quotation['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/sales-quotations/{quotation['id']}/detail", headers=other).status_code == 404
    assert client.get(f"/api/v1/sales-quotation-items/{item['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/sales-quotations", headers=other).json()["data"] == []
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=other).status_code == 404
    # cross-tenant references are 404s, not leaks
    other_employee = create_employee(client, tenant_id=OTHER_TENANT, name="外部员工")
    assert client.post(
        "/api/v1/sales-quotations",
        json={"employee_id": other_employee, "title": "跨租户", "customer_id": customer["id"]},
        headers=other,
    ).status_code == 404


def test_adjustments_shape_the_total_and_ride_revisions(client: TestClient) -> None:
    """OFBiz-style QuoteAdjustment: signed amounts beside the line math,
    header- or line-level, visible in the detail as adjustments_total and
    adjusted_total — the number the declared total_amount should match."""
    employee_id = create_employee(client)
    quotation = create_quotation(client, employee_id)
    line = create_item(client, quotation["id"], quantity=10, unit_price=100.0)
    other_quotation = create_quotation(client, employee_id, title="另一单")
    foreign_line = create_item(client, other_quotation["id"])

    def add(payload, expect=201):
        response = client.post(
            "/api/v1/sales-quotation-adjustments",
            json={"quotation_id": quotation["id"], **payload},
            headers=api_key_headers(),
        )
        assert response.status_code == expect, response.text
        return response.json()["data"] if expect == 201 else response.json()

    # header-level: tax on, rounding off; line-level: a promo discount
    add({"adjustment_type": "tax", "amount": 130.0, "source_percentage": 13, "description": "增值税 13%"})
    add({"adjustment_type": "rounding", "amount": -0.5, "description": "抹零"})
    promo = add({
        "adjustment_type": "promotion", "amount": -50.0,
        "quotation_item_id": line["id"], "description": "开业促销减50",
        "metadata": {"活动": "开业季"},
    })
    assert promo["quotation_item_id"] == line["id"]
    assert promo["metadata"] == {"活动": "开业季"}

    # a line from another quotation is a 400, not a silent cross-link
    wrong = add({"adjustment_type": "discount", "amount": -1, "quotation_item_id": foreign_line["id"]}, expect=400)
    assert "does not belong" in wrong["detail"]

    detail = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert detail["computed_total"] == 1000.0
    assert detail["adjustments_total"] == 79.5  # +130 − 0.5 − 50
    assert detail["adjusted_total"] == 1079.5
    # set, not order: rows born in the same second tie on created_at
    assert {a["adjustment_type"] for a in detail["adjustments"]} == {"tax", "rounding", "promotion"}

    # revise copies adjustments and remaps the line-pinned one to the copied line
    submit = client.post(f"/api/v1/sales-quotations/{quotation['id']}/submit", json={}, headers=api_key_headers())
    assert submit.status_code == 200, submit.text
    advance = client.patch(
        f"/api/v1/sales-quotations/{quotation['id']}",
        json={"status": "approved"},
        headers=api_key_headers(),
    )
    assert advance.status_code == 200, advance.text
    revised = client.post(
        f"/api/v1/sales-quotations/{quotation['id']}/revise",
        json={"reason": "客户要求再让一点"},
        headers=api_key_headers(),
    )
    assert revised.status_code == 201, revised.text
    revision = revised.json()["data"]

    revision_detail = client.get(
        f"/api/v1/sales-quotations/{revision['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert revision_detail["adjustments_total"] == 79.5
    copied_promo = [a for a in revision_detail["adjustments"] if a["adjustment_type"] == "promotion"][0]
    copied_line_ids = {item["id"] for item in revision_detail["items"]}
    assert copied_promo["quotation_item_id"] in copied_line_ids
    assert copied_promo["quotation_item_id"] != line["id"]

    # the superseded original is no longer editable: adjustments are locked
    locked = client.post(
        "/api/v1/sales-quotation-adjustments",
        json={"quotation_id": quotation["id"], "adjustment_type": "fee", "amount": 1},
        headers=api_key_headers(),
    )
    assert locked.status_code == 409

    # editing on the live draft revision still works, and delete is soft
    fee = client.post(
        "/api/v1/sales-quotation-adjustments",
        json={"quotation_id": revision["id"], "adjustment_type": "fee", "amount": 20.0},
        headers=api_key_headers(),
    ).json()["data"]
    patched = client.patch(
        f"/api/v1/sales-quotation-adjustments/{fee['id']}",
        json={"amount": 25.0, "description": "加急服务费"},
        headers=api_key_headers(),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["amount"] == 25.0
    assert client.delete(
        f"/api/v1/sales-quotation-adjustments/{fee['id']}", headers=api_key_headers()
    ).status_code == 204
    assert client.get(
        f"/api/v1/sales-quotation-adjustments/{fee['id']}", headers=api_key_headers()
    ).status_code == 404
    final = client.get(
        f"/api/v1/sales-quotations/{revision['id']}/detail", headers=api_key_headers()
    ).json()["data"]
    assert final["adjustments_total"] == 79.5
