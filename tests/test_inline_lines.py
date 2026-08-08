"""Create a document WITH its lines in one request.

The submit skills used to spend one turn (~12s) per line: header, then five
entry POSTs, then submit. The rows now ride the header's own transaction —
which is also an integrity fix: a crash or a bad row mid-entries can no
longer leave a half-filled draft behind.

The inline path reuses the standalone line builders verbatim, so both paths
enforce the same rules by construction.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import provision_tenant as bootstrap_tenant


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Inline Co", email="admin@inline-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def employee(client: TestClient, headers: dict, name: str = "小林") -> str:
    response = client.post("/api/v1/employees", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_timesheet_created_whole_and_submitted_in_two_calls(client: TestClient) -> None:
    headers = provision(client)
    emp = employee(client, headers)

    created = client.post("/api/v1/timesheet-headers", json={
        "employee_id": emp,
        "period_start": "2026-06-01",
        "period_end": "2026-06-07",
        "entries": [
            {"work_date": "2026-06-01", "hours": 8, "task": "需求梳理"},
            {"work_date": "2026-06-02", "hours": 6.5, "task": "方案评审"},
        ],
    }, headers=headers)
    assert created.status_code == 201, created.text
    data = created.json()["data"]

    # the response is the read-back: every row, as stored
    assert [entry["hours"] for entry in data["entries"]] == [8.0, 6.5]
    assert all(entry["header_id"] == data["id"] for entry in data["entries"])
    # employee_id defaulted from the header — inline rows need not repeat it
    assert all(entry["employee_id"] == emp for entry in data["entries"])

    submitted = client.post(
        f"/api/v1/timesheet-headers/{data['id']}/submit", json={}, headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "submitted"


def test_one_bad_row_rolls_back_the_whole_document(client: TestClient) -> None:
    """The point of riding one transaction. The old flow committed the header
    first, so a bad third entry left a half-filled draft nobody asked for."""
    headers = provision(client)
    emp = employee(client, headers)

    created = client.post("/api/v1/timesheet-headers", json={
        "employee_id": emp,
        "period_start": "2026-06-01",
        "period_end": "2026-06-07",
        "entries": [
            {"work_date": "2026-06-01", "hours": 8},
            {"work_date": "2026-07-15", "hours": 8},   # outside the period
        ],
    }, headers=headers)
    assert created.status_code == 400, created.text

    # nothing landed — not the header either
    listed = client.get(f"/api/v1/timesheet-headers?employee_id={emp}", headers=headers)
    assert listed.json()["meta"]["total"] == 0


def test_inline_rows_may_not_name_another_parent(client: TestClient) -> None:
    headers = provision(client)
    emp = employee(client, headers)
    other = client.post("/api/v1/timesheet-headers", json={
        "employee_id": emp, "period_start": "2026-05-01", "period_end": "2026-05-07",
    }, headers=headers).json()["data"]["id"]

    hijack = client.post("/api/v1/timesheet-headers", json={
        "employee_id": emp,
        "period_start": "2026-06-01",
        "period_end": "2026-06-07",
        "entries": [{"header_id": other, "work_date": "2026-06-01", "hours": 8}],
    }, headers=headers)
    assert hijack.status_code == 422, hijack.text
    assert "do not name another header_id" in hijack.json()["detail"]


def test_expense_claim_with_items_and_batch_invoice_dedup(client: TestClient) -> None:
    headers = provision(client)
    emp = employee(client, headers)

    created = client.post("/api/v1/expense-claims", json={
        "employee_id": emp,
        "title": "出差报销",
        "items": [
            {"expense_date": "2026-06-03", "amount": 120, "invoice_number": "INV-001"},
            {"expense_date": "2026-06-04", "amount": 80.5},
        ],
    }, headers=headers)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert [item["amount"] for item in data["items"]] == [120.0, 80.5]

    # the standalone dedup rule holds inside a batch too: a second claim
    # reusing the invoice number is refused, and the claim does not land
    duplicate = client.post("/api/v1/expense-claims", json={
        "employee_id": emp,
        "title": "重复发票",
        "items": [{"expense_date": "2026-06-05", "amount": 50, "invoice_number": "INV-001"}],
    }, headers=headers)
    assert duplicate.status_code == 409, duplicate.text
    listed = client.get(f"/api/v1/expense-claims?employee_id={emp}", headers=headers)
    assert listed.json()["meta"]["total"] == 1


def test_plain_create_without_lines_is_unchanged(client: TestClient) -> None:
    headers = provision(client)
    emp = employee(client, headers)
    created = client.post("/api/v1/timesheet-headers", json={
        "employee_id": emp, "period_start": "2026-06-01", "period_end": "2026-06-07",
    }, headers=headers)
    assert created.status_code == 201
    assert "entries" not in created.json()["data"]


def test_quotation_created_whole_with_catalog_snapshot(client: TestClient) -> None:
    """The named pain: a three-line quote was header + three item POSTs. Now
    one call — and the inline path must still capture the catalog list price,
    because that snapshot is what discount review keys on."""
    headers = provision(client)
    emp = employee(client, headers)
    product = client.post("/api/v1/products", json={
        "product_code": "P-LENS", "name": "内窥镜镜头", "list_price": 1200,
    }, headers=headers)
    assert product.status_code == 201, product.text
    product_id = product.json()["data"]["id"]

    created = client.post("/api/v1/sales-quotations", json={
        "employee_id": emp,
        "title": "医院设备报价",
        "valid_until": "2026-08-31",
        "items": [
            {"line_no": 1, "product_id": product_id, "quantity": 2, "unit_price": 1000, "amount": 2000},
            {"line_no": 2, "product_name_snapshot": "安装调试", "quantity": 1, "unit_price": 500, "amount": 500},
        ],
    }, headers=headers)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["quote_number"].startswith("QT-")
    lines = {row["line_no"]: row for row in data["items"]}
    # the catalog snapshot rode the inline path — discount review depends on it
    assert lines[1]["list_price_snapshot"] == 1200.0
    assert lines[1]["product_name_snapshot"] == "内窥镜镜头"
    assert lines[2]["list_price_snapshot"] is None

    # submit straight away: the whole quote was two calls
    submitted = client.post(f"/api/v1/sales-quotations/{data['id']}/submit", json={}, headers=headers)
    assert submitted.status_code == 200, submitted.text


def test_purchase_request_and_order_lines_ride_the_create(client: TestClient) -> None:
    headers = provision(client)
    emp = employee(client, headers)

    request = client.post("/api/v1/purchase-requests", json={
        "employee_id": emp, "title": "办公用品",
        "items": [{"product_name_snapshot": "人体工学椅", "quantity": 3, "unit_price": 800, "amount": 2400}],
    }, headers=headers)
    assert request.status_code == 201, request.text
    assert request.json()["data"]["items"][0]["amount"] == 2400.0

    order = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "title": "服务订单",
        "items": [{"product_name_snapshot": "驻场顾问", "quantity": 2, "unit_price": 1500, "amount": 3000}],
    }, headers=headers)
    assert order.status_code == 201, order.text
    assert order.json()["data"]["items"][0]["amount"] == 3000.0

    # a bad row still rolls back the whole document, generic path included
    bad = client.post("/api/v1/sales-orders", json={
        "employee_id": emp, "title": "坏行",
        "items": [{"quantity": 1, "unit_price": 10}],  # no product, no snapshot
    }, headers=headers)
    assert bad.status_code == 422, bad.text
    listed = client.get(f"/api/v1/sales-orders?employee_id={emp}", headers=headers)
    assert listed.json()["meta"]["total"] == 1

    # and an inline row may not point at a different parent
    other = client.post("/api/v1/sales-quotations", json={
        "employee_id": emp, "title": "另一张",
    }, headers=headers).json()["data"]
    conflict = client.post("/api/v1/sales-quotations", json={
        "employee_id": emp, "title": "冲突",
        "items": [{"quotation_id": other["id"], "product_name_snapshot": "x", "quantity": 1}],
    }, headers=headers)
    assert conflict.status_code == 422, conflict.text
    assert "do not name another" in conflict.json()["detail"]
