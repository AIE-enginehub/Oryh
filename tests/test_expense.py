from __future__ import annotations

import base64
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client


TEST_TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
TEST_API_KEY = "test-api-key"
OTHER_API_KEY = "other-api-key"

RECEIPT_BYTES = b"%PDF-1.4 fake receipt for tests"
RECEIPT_BASE64 = base64.b64encode(RECEIPT_BYTES).decode("ascii")


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


def create_claim(test_client: TestClient, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "employee_id": employee_id,
        "title": "上海出差报销",
        "claim_date": "2026-07-10",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/expense-claims", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def upload_receipt(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {
        "filename": "receipt.pdf",
        "content_type": "application/pdf",
        "content_base64": RECEIPT_BASE64,
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/attachments", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


def create_item(test_client: TestClient, claim_id: str, employee_id: str, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {
        "claim_id": claim_id,
        "employee_id": employee_id,
        "expense_date": "2026-07-08",
        "category": "meal",
        "amount": 186.5,
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/expense-items", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_expense_flow_with_receipt_and_approval(client: TestClient) -> None:
    employee_id = create_employee(client, email="alice@example.com")
    vendor_response = client.post(
        "/api/v1/vendors",
        json={"name": "上海餐饮供应商", "vendor_code": "SUP-001"},
        headers=api_key_headers(),
    )
    assert vendor_response.status_code == 201, vendor_response.text
    vendor = vendor_response.json()["data"]
    claim_id = create_claim(
        client,
        employee_id,
        source_report_text="7月8日出差上海，餐费186.5元，高铁票553元，附发票。",
    )

    attachment = upload_receipt(client)
    assert attachment["size_bytes"] == len(RECEIPT_BYTES)

    create_item(
        client,
        claim_id,
        employee_id,
        amount=186.5,
        tax_amount=11.06,
        vendor_id=vendor["id"],
        merchant="上海某餐饮有限公司",
        invoice_number="032001900311",
        invoice_type="vat_electronic",
        attachment_id=attachment["id"],
        extracted_fields={"发票代码": "032001900311", "购买方名称": "Test Tenant"},
    )
    create_item(
        client,
        claim_id,
        employee_id,
        expense_date="2026-07-08",
        category="travel",
        amount=553.0,
        invoice_number="G12345678",
        invoice_type="receipt",
    )

    submit = client.post(f"/api/v1/expense-claims/{claim_id}/submit", json={"source": "ai"}, headers=api_key_headers())
    assert submit.status_code == 200
    assert submit.json()["data"]["status"] == "submitted"
    assert submit.json()["data"]["submitted_at"] is not None

    # idempotent resubmit
    assert client.post(
        f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    approval = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "expense_claim",
            "entity_id": claim_id,
            "action": "approved",
            "approver_id": "mgr-1",
            "approver_role": "manager",
            "source": "ai",
            "acted_at": "2026-07-11T10:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approval.status_code == 201

    detail = client.get(f"/api/v1/expense-claims/{claim_id}/detail", headers=api_key_headers()).json()["data"]
    assert detail["claim"]["status"] == "submitted"
    assert len(detail["items"]) == 2
    assert detail["total_amount"] == pytest.approx(739.5)
    assert detail["total_tax_amount"] == pytest.approx(11.06)
    assert len(detail["approval_records"]) == 1
    assert [a["id"] for a in detail["attachments"]] == [attachment["id"]]
    assert detail["items"][0]["extracted_fields"]["购买方名称"] == "Test Tenant"
    assert detail["items"][0]["vendor_name"] == "上海餐饮供应商"

    # finalize: submitted -> approved -> paid follows the default machine
    for target in ("approved", "paid"):
        response = client.patch(
            f"/api/v1/expense-claims/{claim_id}", json={"status": target}, headers=api_key_headers()
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == target


def test_expense_claim_filters_and_work_queue(client: TestClient) -> None:
    employee_id = create_employee(client)
    first = create_claim(client, employee_id, title="报销一")
    second = create_claim(client, employee_id, title="报销二")
    client.post(f"/api/v1/expense-claims/{first}/submit", json={}, headers=api_key_headers())
    client.post(f"/api/v1/expense-claims/{second}/submit", json={}, headers=api_key_headers())

    submitted = client.get("/api/v1/expense-claims?status=submitted", headers=api_key_headers()).json()["data"]
    assert {c["id"] for c in submitted} == {first, second}

    # assigning a todo takes the claim out of the flow agent's work queue
    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "expense_claim",
            "entity_id": first,
            "title": "审批 Alice 的报销",
            "todo_type": "approval",
        },
        headers=api_key_headers(),
    )
    assert todo.status_code == 201, todo.text

    queue = client.get(
        "/api/v1/expense-claims?status=submitted&without_open_todo=true", headers=api_key_headers()
    ).json()["data"]
    assert {c["id"] for c in queue} == {second}


def test_duplicate_invoice_number_is_rejected_within_tenant(client: TestClient) -> None:
    employee_id = create_employee(client)
    first_claim = create_claim(client, employee_id, title="第一张")
    second_claim = create_claim(client, employee_id, title="第二张")
    item = create_item(client, first_claim, employee_id, invoice_number="INV-001")

    duplicate = client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": second_claim,
            "employee_id": employee_id,
            "expense_date": "2026-07-09",
            "amount": 99.0,
            "invoice_number": "INV-001",
        },
        headers=api_key_headers(),
    )
    assert duplicate.status_code == 409
    assert "INV-001" in duplicate.json()["detail"]

    # updating another item onto a taken invoice number is also rejected
    other = create_item(client, second_claim, employee_id, invoice_number="INV-002")
    conflict = client.patch(
        f"/api/v1/expense-items/{other['id']}", json={"invoice_number": "INV-001"}, headers=api_key_headers()
    )
    assert conflict.status_code == 409

    # soft-deleting the original item frees the invoice number
    assert client.delete(f"/api/v1/expense-items/{item['id']}", headers=api_key_headers()).status_code == 204
    retry = client.patch(
        f"/api/v1/expense-items/{other['id']}", json={"invoice_number": "INV-001"}, headers=api_key_headers()
    )
    assert retry.status_code == 200

    # same invoice in the other tenant is fine — isolation, not global uniqueness
    other_employee = create_employee(client, tenant_id=OTHER_TENANT, name="Bob")
    other_claim = create_claim(client, other_employee, tenant_id=OTHER_TENANT)
    create_item(client, other_claim, other_employee, tenant_id=OTHER_TENANT, invoice_number="INV-001")


def test_attachment_idempotent_upload_download_and_isolation(client: TestClient) -> None:
    # 201 stored these bytes; 200 says the server already held them. That
    # distinction IS the duplicate-evidence signal an expense agent relies on:
    # it used to be guessed from created_at, which reports "new" for anything
    # re-uploaded within minutes — exactly when a claim's receipts arrive.
    fresh = client.post(
        "/api/v1/attachments",
        json={"filename": "receipt.pdf", "content_type": "application/pdf",
              "content_base64": RECEIPT_BASE64},
        headers=api_key_headers(),
    )
    assert fresh.status_code == 201, fresh.text
    first = fresh.json()["data"]

    reused = client.post(
        "/api/v1/attachments",
        json={"filename": "renamed.pdf", "content_type": "application/pdf",
              "content_base64": RECEIPT_BASE64},
        headers=api_key_headers(),
    )
    assert reused.status_code == 200, "re-uploading the same bytes must report reuse, not creation"
    second = reused.json()["data"]
    assert second["id"] == first["id"]  # same bytes, same tenant → same row

    content = client.get(f"/api/v1/attachments/{first['id']}/content", headers=api_key_headers())
    assert content.status_code == 200
    assert content.content == RECEIPT_BYTES
    assert content.headers["content-type"].startswith("application/pdf")

    # other tenant can neither read metadata nor content
    assert client.get(
        f"/api/v1/attachments/{first['id']}", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404
    assert client.get(
        f"/api/v1/attachments/{first['id']}/content", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404

    # same bytes uploaded by the other tenant is a separate row — and a
    # genuine creation there, never reported as someone else's duplicate
    other_upload = client.post(
        "/api/v1/attachments",
        json={"filename": "receipt.pdf", "content_type": "application/pdf",
              "content_base64": RECEIPT_BASE64},
        headers=api_key_headers(OTHER_API_KEY),
    )
    assert other_upload.status_code == 201
    assert other_upload.json()["data"]["id"] != first["id"]

    invalid = client.post(
        "/api/v1/attachments",
        json={"filename": "x.pdf", "content_type": "application/pdf", "content_base64": "not-base64!!"},
        headers=api_key_headers(),
    )
    assert invalid.status_code == 422

    # attachment_id on an item must exist in the same tenant
    employee_id = create_employee(client)
    claim_id = create_claim(client, employee_id)
    cross = client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": claim_id,
            "employee_id": employee_id,
            "expense_date": "2026-07-08",
            "amount": 10,
            "attachment_id": other_upload.json()["data"]["id"],
        },
        headers=api_key_headers(),
    )
    assert cross.status_code == 404


def test_items_locked_after_submit_and_machine_guards_transitions(client: TestClient) -> None:
    employee_id = create_employee(client)
    claim_id = create_claim(client, employee_id)
    item = create_item(client, claim_id, employee_id)

    # draft -> approved skips submitted: illegal
    assert client.patch(
        f"/api/v1/expense-claims/{claim_id}", json={"status": "approved"}, headers=api_key_headers()
    ).status_code == 409

    client.post(f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=api_key_headers())

    locked_create = client.post(
        "/api/v1/expense-items",
        json={"claim_id": claim_id, "employee_id": employee_id, "expense_date": "2026-07-08", "amount": 5},
        headers=api_key_headers(),
    )
    assert locked_create.status_code == 409
    assert client.patch(
        f"/api/v1/expense-items/{item['id']}", json={"amount": 1.0}, headers=api_key_headers()
    ).status_code == 409
    assert client.delete(f"/api/v1/expense-items/{item['id']}", headers=api_key_headers()).status_code == 409

    # returned reopens editing, resubmission closes it again
    assert client.patch(
        f"/api/v1/expense-claims/{claim_id}", json={"status": "returned"}, headers=api_key_headers()
    ).status_code == 200
    assert client.patch(
        f"/api/v1/expense-items/{item['id']}", json={"amount": 20.0}, headers=api_key_headers()
    ).status_code == 200
    assert client.post(
        f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=api_key_headers()
    ).status_code == 200

    # paid is terminal
    client.patch(f"/api/v1/expense-claims/{claim_id}", json={"status": "approved"}, headers=api_key_headers())
    client.patch(f"/api/v1/expense-claims/{claim_id}", json={"status": "paid"}, headers=api_key_headers())
    assert client.patch(
        f"/api/v1/expense-claims/{claim_id}", json={"status": "submitted"}, headers=api_key_headers()
    ).status_code == 409


def test_claim_soft_delete_restore_and_validation(client: TestClient) -> None:
    employee_id = create_employee(client)
    claim_id = create_claim(client, employee_id)
    create_item(client, claim_id, employee_id, invoice_number="INV-D1")

    assert client.delete(f"/api/v1/expense-claims/{claim_id}", headers=api_key_headers()).status_code == 204
    assert client.get(f"/api/v1/expense-claims/{claim_id}", headers=api_key_headers()).status_code == 404
    assert client.get(
        f"/api/v1/expense-claims/{claim_id}?include_deleted=true", headers=api_key_headers()
    ).status_code == 200
    listed = client.get("/api/v1/expense-claims", headers=api_key_headers()).json()["data"]
    assert listed == []

    # items on a deleted claim stop blocking the invoice number
    other_claim = create_claim(client, employee_id, title="新报销")
    create_item(client, other_claim, employee_id, invoice_number="INV-D1")

    restored = client.post(
        f"/api/v1/expense-claims/{claim_id}/restore", json={}, headers=api_key_headers()
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "draft"

    # employee mismatch between item and claim
    stranger = create_employee(client, name="Someone Else")
    mismatch = client.post(
        "/api/v1/expense-items",
        json={"claim_id": other_claim, "employee_id": stranger, "expense_date": "2026-07-08", "amount": 5},
        headers=api_key_headers(),
    )
    assert mismatch.status_code == 400

    # invalid create status and non-positive amount are rejected up front
    bad_status = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": employee_id, "title": "x", "status": "nonsense"},
        headers=api_key_headers(),
    )
    assert bad_status.status_code == 422
    bad_amount = client.post(
        "/api/v1/expense-items",
        json={"claim_id": other_claim, "employee_id": employee_id, "expense_date": "2026-07-08", "amount": 0},
        headers=api_key_headers(),
    )
    assert bad_amount.status_code == 422


def create_vendor(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> dict:
    payload = {"name": "上海某餐饮有限公司", "tax_id": "91310000MA1FL0000X"}
    payload.update(overrides)
    response = test_client.post("/api/v1/vendors", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_vendor_master_data_and_item_association(client: TestClient) -> None:
    vendor = create_vendor(client, vendor_code="V-001", contact="王经理", phone="021-12345678")
    assert vendor["status"] == "active"

    # filters: keyword and exact tax_id
    by_keyword = client.get("/api/v1/vendors?keyword=餐饮", headers=api_key_headers()).json()["data"]
    assert [v["id"] for v in by_keyword] == [vendor["id"]]
    by_tax = client.get(
        "/api/v1/vendors?tax_id=91310000MA1FL0000X", headers=api_key_headers()
    ).json()["data"]
    assert [v["id"] for v in by_tax] == [vendor["id"]]
    assert client.get("/api/v1/vendors?tax_id=nope", headers=api_key_headers()).json()["data"] == []

    # item association: vendor_id backfills the merchant snapshot
    employee_id = create_employee(client)
    claim_id = create_claim(client, employee_id)
    item = create_item(client, claim_id, employee_id, vendor_id=vendor["id"], merchant=None)
    assert item["vendor_id"] == vendor["id"]
    assert item["merchant"] == "上海某餐饮有限公司"

    # explicit merchant text wins over the backfill; vendor stays linked
    item2 = create_item(
        client, claim_id, employee_id, vendor_id=vendor["id"], merchant="发票抬头原文", invoice_number="INV-V1"
    )
    assert item2["merchant"] == "发票抬头原文"

    # vendor is optional: null vendor_id with free-text merchant only
    item3 = create_item(client, claim_id, employee_id, merchant="无主数据商户", invoice_number="INV-V2")
    assert item3["vendor_id"] is None

    # filter items by vendor
    by_vendor = client.get(
        f"/api/v1/expense-items?vendor_id={vendor['id']}", headers=api_key_headers()
    ).json()["data"]
    assert {i["id"] for i in by_vendor} == {item["id"], item2["id"]}

    # patch can attach and detach the vendor
    detached = client.patch(
        f"/api/v1/expense-items/{item3['id']}", json={"vendor_id": vendor["id"]}, headers=api_key_headers()
    )
    assert detached.json()["data"]["vendor_id"] == vendor["id"]
    detached = client.patch(
        f"/api/v1/expense-items/{item3['id']}", json={"vendor_id": None}, headers=api_key_headers()
    )
    assert detached.json()["data"]["vendor_id"] is None
    assert detached.json()["data"]["merchant"] == "无主数据商户"

    # archive removes it from active lists but history stands
    assert client.delete(f"/api/v1/vendors/{vendor['id']}", headers=api_key_headers()).status_code == 204
    active = client.get("/api/v1/vendors?status=active", headers=api_key_headers()).json()["data"]
    assert active == []
    assert client.get(
        f"/api/v1/expense-items/{item['id']}", headers=api_key_headers()
    ).json()["data"]["vendor_id"] == vendor["id"]

    # tenant isolation: other tenant sees nothing and cannot reference it
    assert client.get(
        f"/api/v1/vendors/{vendor['id']}", headers=api_key_headers(OTHER_API_KEY)
    ).status_code == 404
    other_employee = create_employee(client, tenant_id=OTHER_TENANT, name="Bob")
    other_claim = create_claim(client, other_employee, tenant_id=OTHER_TENANT)
    cross = client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": other_claim,
            "employee_id": other_employee,
            "expense_date": "2026-07-08",
            "amount": 10,
            "vendor_id": vendor["id"],
        },
        headers=api_key_headers(OTHER_API_KEY),
    )
    assert cross.status_code == 404


def test_expense_tenant_isolation(client: TestClient) -> None:
    employee_id = create_employee(client)
    claim_id = create_claim(client, employee_id)
    item = create_item(client, claim_id, employee_id)

    other = api_key_headers(OTHER_API_KEY)
    assert client.get(f"/api/v1/expense-claims/{claim_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/expense-claims/{claim_id}/detail", headers=other).status_code == 404
    assert client.get(f"/api/v1/expense-items/{item['id']}", headers=other).status_code == 404
    assert client.post(f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=other).status_code == 404
    assert client.get("/api/v1/expense-claims", headers=other).json()["data"] == []
