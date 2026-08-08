"""A value that cannot be a UUID is refused at the door, never a 500.

a live E2E audit: six real-agent 500s in six hours, all one disease —
strings reaching postgres UUID casts. Agents hold natural names
("warranty_card", "principals", a colleague's pinyin); the API held UUID
columns; the gap surfaced as InvalidTextRepresentation instead of an answer.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import provision_tenant as bootstrap_tenant


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Uuid Co", email="admin@uuid-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def test_a_type_name_in_the_definition_slot_resolves_instead_of_500ing(client: TestClient) -> None:
    """Four of the six 500s were GET /object-type-definitions/<type_name> —
    agents hold natural names, so the ref now resolves either an id or an
    object_type, the way role refs already did."""
    headers = provision(client)
    created = client.post(
        "/api/v1/object-type-definitions",
        json={
            "object_type": "warranty_card",
            "title": "保修卡",
            "json_schema": {"type": "object", "additionalProperties": True},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    definition_id = created.json()["data"]["id"]

    by_name = client.get("/api/v1/object-type-definitions/warranty_card", headers=headers)
    assert by_name.status_code == 200, by_name.text
    assert by_name.json()["data"]["id"] == definition_id

    by_id = client.get(f"/api/v1/object-type-definitions/{definition_id}", headers=headers)
    assert by_id.status_code == 200

    assert client.get(
        "/api/v1/object-type-definitions/no_such_type", headers=headers
    ).status_code == 404


def test_a_word_in_a_uuid_path_slot_is_404(client: TestClient) -> None:
    """GET /employees/principals fell into /employees/{employee_id} and the
    cast blew up. Not-a-valid-id and no-such-id are the same answer: 404."""
    headers = provision(client)
    for path in ("/api/v1/employees/principals", "/api/v1/projects/not-a-uuid",
                 "/api/v1/timesheet-headers/工时"):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, f"{path}: {response.status_code} {response.text}"


def test_a_name_in_a_uuid_query_filter_is_422_naming_the_field(client: TestClient) -> None:
    """GET /todos?employee_id=gujianguo — the filter takes an id, the agent
    held a pinyin. The refusal names the field and what it wanted."""
    headers = provision(client)
    response = client.get("/api/v1/todos?employee_id=gujianguo&status=open", headers=headers)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "employee_id" in detail and "UUID" in detail

    # the same guard rides list_rows, so every collection behaves alike
    for path in ("/api/v1/timesheet-headers?employee_id=zhangsan",
                 "/api/v1/sales-orders?customer_id=蓝湾"):
        assert client.get(path, headers=headers).status_code == 422, path


def test_products_are_findable_by_their_own_code(client: TestClient) -> None:
    """a live E2E audit: keyword search matched names only, so pasting the full
    imported code returned zero rows and read as a failed import."""
    headers = provision(client)
    created = client.post(
        "/api/v1/products",
        json={"product_code": "E2E-20260801-001", "name": "验收测试产品"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    found = client.get("/api/v1/products?keyword=E2E-20260801-001", headers=headers)
    assert found.status_code == 200
    assert found.json()["meta"]["total"] == 1
