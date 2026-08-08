from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
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


def create_project(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {"project_name": "ERP Upgrade", "client": "Acme Corp"}
    payload.update(overrides)
    response = test_client.post("/api/v1/projects", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_resource(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "resource_type": "meeting_room",
        "name": "Room A",
        "code": "ROOM-A",
        "location": "Floor 3",
        "booking_mode": "exclusive",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/resources", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_approval_target(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "target_type": "meeting_resolution",
        "title": "Approve Q2 steering committee resolution",
        "summary": "Review the proposed vendor consolidation decision.",
        "payload": {"meeting_code": "M-2026-04-01", "resolution_no": "R-7"},
        "source_text": "会议决议：同意在 Q2 完成供应商整合。",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/approval-targets", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_business_object(test_client: TestClient, tenant_id: str = TEST_TENANT, **overrides) -> str:
    payload = {
        "object_type": "warranty_card",
        "title": "JC printer warranty card WC-1001",
        "summary": "Warranty card submitted by a service provider.",
        "payload": {"printer_serial_no": "PRN-1001", "customer": "City Hospital"},
        "source_text": "服务商提交 JC 打印机保修卡申请。",
        "created_by": "agent-test",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/business-objects", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_header(
    test_client: TestClient,
    employee_id: str,
    tenant_id: str = TEST_TENANT,
    **overrides,
) -> str:
    payload = {
        "employee_id": employee_id,
        "period_start": "2026-03-09",
        "period_end": "2026-03-15",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/timesheet-headers", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_entry(
    test_client: TestClient,
    header_id: str,
    employee_id: str,
    tenant_id: str = TEST_TENANT,
    **overrides,
) -> str:
    payload = {
        "header_id": header_id,
        "employee_id": employee_id,
        "work_date": "2026-03-10",
        "hours": 4.5,
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/timesheet-entries", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_todo(
    test_client: TestClient,
    employee_id: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str = TEST_TENANT,
    **overrides,
) -> str:
    payload = {
        "employee_id": employee_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": "Review pending item",
        "description": "Please review this item.",
        "todo_type": "approval",
        "created_by": "agent-test",
    }
    payload.update(overrides)
    response = test_client.post("/api/v1/todos", json=payload, headers=headers_for_tenant(tenant_id))
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_json_responses_declare_utf8_charset(client: TestClient) -> None:
    # Bare "application/json" makes non-spec clients guess the encoding and
    # garble CJK text; both normal routes and exception-handler responses must
    # declare the charset.
    ok = client.get("/healthz")
    assert ok.headers["content-type"] == "application/json; charset=utf-8"

    error = client.get("/api/v1/employees")
    assert error.status_code == 401
    assert error.headers["content-type"] == "application/json; charset=utf-8"


def test_reject_missing_or_invalid_api_key(client: TestClient) -> None:
    missing_key_response = client.get("/api/v1/employees")
    assert missing_key_response.status_code == 401
    assert "X-API-Key" in missing_key_response.json()["detail"]

    invalid_key_response = client.get("/api/v1/employees", headers=api_key_headers("bad-key"))
    assert invalid_key_response.status_code == 401
    assert invalid_key_response.json()["detail"] == "invalid API key"


def test_tenant_bootstrap_and_api_key_management(client: TestClient) -> None:
    tenant_response = client.post(
        "/api/v1/tenants",
        json={"name": "Bootstrap Tenant", "initial_api_key_label": "bootstrap"},
    )
    assert tenant_response.status_code == 201
    tenant_payload = tenant_response.json()["data"]
    assert tenant_payload["tenant"]["name"] == "Bootstrap Tenant"
    assert tenant_payload["api_key"]["label"] == "bootstrap"
    assert tenant_payload["plain_text_api_key"].startswith("calw_")

    bootstrap_key = tenant_payload["plain_text_api_key"]

    get_tenant_response = client.get("/api/v1/tenant", headers=api_key_headers(bootstrap_key))
    assert get_tenant_response.status_code == 200
    assert get_tenant_response.json()["data"]["name"] == "Bootstrap Tenant"

    create_key_response = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "secondary"},
        headers=api_key_headers(bootstrap_key),
    )
    assert create_key_response.status_code == 201
    secondary_key_payload = create_key_response.json()["data"]
    secondary_key_id = secondary_key_payload["api_key"]["id"]
    secondary_plain_text_key = secondary_key_payload["plain_text_api_key"]
    assert secondary_plain_text_key.startswith("calw_")

    list_keys_response = client.get("/api/v1/tenant/api-keys", headers=api_key_headers(bootstrap_key))
    assert list_keys_response.status_code == 200
    assert list_keys_response.json()["meta"]["total"] == 2

    update_key_response = client.patch(
        f"/api/v1/tenant/api-keys/{secondary_key_id}",
        json={"is_active": False, "label": "revoked"},
        headers=api_key_headers(bootstrap_key),
    )
    assert update_key_response.status_code == 200
    assert update_key_response.json()["data"]["is_active"] is False
    assert update_key_response.json()["data"]["label"] == "revoked"

    inactive_keys = client.get(
        "/api/v1/tenant/api-keys",
        params={"page": 1, "size": 10, "status": "inactive", "keyword": "revoked"},
        headers=api_key_headers(bootstrap_key),
    ).json()
    assert inactive_keys["meta"] == {"total": 1, "page": 1, "page_size": 10, "pages": 1}
    assert [key["id"] for key in inactive_keys["data"]] == [secondary_key_id]

    invalidated_key_response = client.get("/api/v1/tenant", headers=api_key_headers(secondary_plain_text_key))
    assert invalidated_key_response.status_code == 401


def test_timesheet_flow(client: TestClient) -> None:
    employee_id = create_employee(client, email="alice@example.com")
    project_id = create_project(client)
    header_id = create_header(
        client,
        employee_id,
        source_report_text="这周我在 ERP Upgrade 上做了 API 设计，还实现了一部分后端接口。",
    )

    entry_response = client.post(
        "/api/v1/timesheet-entries",
        json={
            "header_id": header_id,
            "employee_id": employee_id,
            "work_date": "2026-03-10",
            "project_id": project_id,
            "client": "Acme Corp",
            "task": "API design",
            "hours": 4.5,
            "custom_fields": {"ticket_no": "JIRA-123"},
        },
        headers=api_key_headers(),
    )
    assert entry_response.status_code == 201
    assert entry_response.json()["data"]["project_name_snapshot"] == "ERP Upgrade"

    submit_response = client.post(
        f"/api/v1/timesheet-headers/{header_id}/submit",
        json={"source": "ai"},
        headers=api_key_headers(),
    )
    assert submit_response.status_code == 200
    assert submit_response.json()["data"]["status"] == "submitted"

    approval_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "action": "approved",
            "approver_id": "mgr-1",
            "approver_role": "manager",
            "source": "ai",
            "acted_at": "2026-03-11T10:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approval_response.status_code == 201

    detail_response = client.get(f"/api/v1/timesheet-headers/{header_id}/detail", headers=api_key_headers())
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["header"]["status"] == "submitted"
    assert "ERP Upgrade" in detail["header"]["source_report_text"]
    assert len(detail["entries"]) == 1
    assert len(detail["approval_records"]) == 1


def test_project_crud_and_filters(client: TestClient) -> None:
    project_id = create_project(client, project_name="Alpha Build", metadata={"region": "CN"})

    list_response = client.get("/api/v1/projects?keyword=Alpha&status=active", headers=api_key_headers())
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(f"/api/v1/projects/{project_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["metadata"]["region"] == "CN"

    patch_response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"client": "Globex", "metadata": {"region": "US"}},
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["client"] == "Globex"
    assert patch_response.json()["data"]["metadata"]["region"] == "US"

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=api_key_headers())
    assert delete_response.status_code == 204

    archived_response = client.get("/api/v1/projects?status=archived", headers=api_key_headers())
    assert archived_response.status_code == 200
    assert archived_response.json()["meta"]["total"] == 1


def test_resource_crud_filters_and_archive(client: TestClient) -> None:
    resource_id = create_resource(
        client,
        resource_type="meeting_room",
        name="Jade Room",
        code="JADE-01",
        location="Floor 8",
        capacity=8,
        metadata={"building": "HQ"},
    )

    list_response = client.get(
        "/api/v1/resources?resource_type=meeting_room&status=active&keyword=Jade",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert resource_id in {item["id"] for item in list_response.json()["data"]}

    get_response = client.get(f"/api/v1/resources/{resource_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["metadata"]["building"] == "HQ"

    patch_response = client.patch(
        f"/api/v1/resources/{resource_id}",
        json={"location": "Floor 9", "metadata": {"building": "Annex"}},
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["location"] == "Floor 9"
    assert patch_response.json()["data"]["metadata"]["building"] == "Annex"

    availability_response = client.get(
        f"/api/v1/resources/{resource_id}/availability?start_at=2026-04-03T09:00:00Z&end_at=2026-04-03T10:00:00Z",
        headers=api_key_headers(),
    )
    assert availability_response.status_code == 200
    assert availability_response.json()["data"]["available"] is True
    assert availability_response.json()["data"]["available_quantity"] == 1

    delete_response = client.delete(f"/api/v1/resources/{resource_id}", headers=api_key_headers())
    assert delete_response.status_code == 204

    archived_response = client.get("/api/v1/resources?status=archived", headers=api_key_headers())
    assert archived_response.status_code == 200
    assert resource_id in {item["id"] for item in archived_response.json()["data"]}


def test_employee_crud_and_filters(client: TestClient) -> None:
    employee_id = create_employee(
        client,
        employee_code="E1001",
        name="Carol",
        metadata={"department": "Engineering"},
    )

    list_response = client.get("/api/v1/employees?keyword=Car&status=active", headers=api_key_headers())
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(f"/api/v1/employees/{employee_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["metadata"]["department"] == "Engineering"

    patch_response = client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"timezone": "Asia/Shanghai", "metadata": {"department": "Product"}},
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["timezone"] == "Asia/Shanghai"
    assert patch_response.json()["data"]["metadata"]["department"] == "Product"


def test_approval_target_crud_and_filters(client: TestClient) -> None:
    approval_target_id = create_approval_target(
        client,
        title="Approve sourcing exception",
        payload={"request_no": "SRC-9"},
    )

    list_response = client.get(
        "/api/v1/approval-targets?target_type=meeting_resolution&status=open",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert approval_target_id in {item["id"] for item in list_response.json()["data"]}

    get_response = client.get(f"/api/v1/approval-targets/{approval_target_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["payload"]["request_no"] == "SRC-9"

    patch_response = client.patch(
        f"/api/v1/approval-targets/{approval_target_id}",
        json={
            "summary": "Review the exception and confirm vendor risk treatment.",
            "status": "in_review",
            "payload": {"request_no": "SRC-9", "risk_level": "high"},
        },
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["status"] == "in_review"
    assert patch_response.json()["data"]["payload"]["risk_level"] == "high"


def test_approval_target_status_is_constrained(client: TestClient) -> None:
    response = client.post(
        "/api/v1/approval-targets",
        json={
            "target_type": "meeting_resolution",
            "title": "Bad status target",
            "status": "pending_review",
        },
        headers=api_key_headers(),
    )
    assert response.status_code == 422


def test_approval_target_soft_delete_include_deleted_and_restore(client: TestClient) -> None:
    approval_target_id = create_approval_target(client)

    delete_response = client.request(
        "DELETE",
        f"/api/v1/approval-targets/{approval_target_id}",
        json={"deleted_by": "admin-approval", "delete_reason": "duplicate request"},
        headers=api_key_headers(),
    )
    assert delete_response.status_code == 204

    hidden_get_response = client.get(f"/api/v1/approval-targets/{approval_target_id}", headers=api_key_headers())
    assert hidden_get_response.status_code == 404

    include_deleted_get_response = client.get(
        f"/api/v1/approval-targets/{approval_target_id}?include_deleted=true",
        headers=api_key_headers(),
    )
    assert include_deleted_get_response.status_code == 200
    assert include_deleted_get_response.json()["data"]["deleted_by"] == "admin-approval"

    include_deleted_list_response = client.get(
        "/api/v1/approval-targets?include_deleted=true",
        headers=api_key_headers(),
    )
    assert include_deleted_list_response.status_code == 200
    assert approval_target_id in {item["id"] for item in include_deleted_list_response.json()["data"]}

    approval_record_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "approval_target",
            "entity_id": approval_target_id,
            "action": "submitted",
            "acted_at": "2026-04-02T13:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approval_record_response.status_code == 404

    restore_response = client.post(
        f"/api/v1/approval-targets/{approval_target_id}/restore",
        json={"restored_by": "admin-approval"},
        headers=api_key_headers(),
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["data"]["deleted_at"] is None

    restored_get_response = client.get(f"/api/v1/approval-targets/{approval_target_id}", headers=api_key_headers())
    assert restored_get_response.status_code == 200


def test_business_object_crud_links_approval_and_todo(client: TestClient) -> None:
    warranty_card_id = create_business_object(
        client,
        object_type="warranty_card",
        title="JC warranty card for Hospital Printer",
        payload={"printer_serial_no": "JC-P-001", "customer": "City Hospital"},
    )
    repair_id = create_business_object(
        client,
        object_type="warranty_repair",
        title="Replace toner sensor",
        payload={"service_provider": "SP-A", "service_fee": 180},
    )

    list_response = client.get(
        "/api/v1/business-objects?object_type=warranty_card&status=open",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert warranty_card_id in {item["id"] for item in list_response.json()["data"]}

    link_response = client.post(
        "/api/v1/business-object-links",
        json={
            "source_object_id": repair_id,
            "target_object_id": warranty_card_id,
            "link_type": "repair_of",
            "metadata": {"relationship_source": "agent"},
        },
        headers=api_key_headers(),
    )
    assert link_response.status_code == 201
    assert link_response.json()["data"]["metadata"]["relationship_source"] == "agent"

    duplicate_link_response = client.post(
        "/api/v1/business-object-links",
        json={
            "source_object_id": repair_id,
            "target_object_id": warranty_card_id,
            "link_type": "repair_of",
        },
        headers=api_key_headers(),
    )
    assert duplicate_link_response.status_code == 409

    links_response = client.get(
        f"/api/v1/business-object-links?target_object_id={warranty_card_id}&link_type=repair_of",
        headers=api_key_headers(),
    )
    assert links_response.status_code == 200
    assert [item["source_object_id"] for item in links_response.json()["data"]] == [repair_id]

    approver_employee_id = create_employee(client, name="JC Reviewer")
    approval_record_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "business_object",
            "entity_id": warranty_card_id,
            "action": "submitted",
            "approver_id": approver_employee_id,
            "source": "ai",
            "acted_at": "2026-04-22T09:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approval_record_response.status_code == 201

    todo_id = create_todo(client, approver_employee_id, "business_object", warranty_card_id)
    complete_response = client.patch(
        f"/api/v1/todos/{todo_id}",
        json={"status": "completed", "completed_by": approver_employee_id},
        headers=api_key_headers(),
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["entity_type"] == "business_object"


def test_business_object_soft_delete_blocks_links_and_approval(client: TestClient) -> None:
    warranty_card_id = create_business_object(client)
    repair_id = create_business_object(client, object_type="warranty_repair", title="Repair service")

    delete_response = client.request(
        "DELETE",
        f"/api/v1/business-objects/{warranty_card_id}",
        json={"deleted_by": "agent-test", "delete_reason": "duplicate"},
        headers=api_key_headers(),
    )
    assert delete_response.status_code == 204

    approval_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "business_object",
            "entity_id": warranty_card_id,
            "action": "submitted",
            "acted_at": "2026-04-22T09:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approval_response.status_code == 404

    link_response = client.post(
        "/api/v1/business-object-links",
        json={
            "source_object_id": repair_id,
            "target_object_id": warranty_card_id,
            "link_type": "repair_of",
        },
        headers=api_key_headers(),
    )
    assert link_response.status_code == 404

    restore_response = client.post(
        f"/api/v1/business-objects/{warranty_card_id}/restore",
        json={"restored_by": "agent-test"},
        headers=api_key_headers(),
    )
    assert restore_response.status_code == 200


def test_exclusive_resource_booking_conflict_and_cancellation(client: TestClient) -> None:
    employee_id = create_employee(client, name="Booker")
    resource_id = create_resource(client, resource_type="meeting_room", name="Amber Room", code="AMBER-01")

    first_booking_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": employee_id,
            "title": "Weekly sync",
            "start_at": "2026-04-03T09:00:00Z",
            "end_at": "2026-04-03T10:00:00Z",
            "quantity": 1,
            "source_text": "订一个周会会议室",
        },
        headers=api_key_headers(),
    )
    assert first_booking_response.status_code == 201
    booking_id = first_booking_response.json()["data"]["id"]

    conflict_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": employee_id,
            "title": "Conflicting booking",
            "start_at": "2026-04-03T09:30:00Z",
            "end_at": "2026-04-03T10:30:00Z",
        },
        headers=api_key_headers(),
    )
    assert conflict_response.status_code == 409

    availability_conflict_response = client.get(
        f"/api/v1/resources/{resource_id}/availability?start_at=2026-04-03T09:30:00Z&end_at=2026-04-03T10:30:00Z",
        headers=api_key_headers(),
    )
    assert availability_conflict_response.status_code == 200
    assert availability_conflict_response.json()["data"]["available"] is False
    assert booking_id in availability_conflict_response.json()["data"]["conflicting_booking_ids"]

    cancel_response = client.request(
        "DELETE",
        f"/api/v1/resource-bookings/{booking_id}",
        json={"cancelled_by": employee_id, "cancel_reason": "meeting moved online"},
        headers=api_key_headers(),
    )
    assert cancel_response.status_code == 204

    replacement_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": employee_id,
            "title": "Replacement booking",
            "start_at": "2026-04-03T09:30:00Z",
            "end_at": "2026-04-03T10:30:00Z",
        },
        headers=api_key_headers(),
    )
    assert replacement_response.status_code == 201


def test_shared_resource_booking_quantity_limit(client: TestClient) -> None:
    employee_id = create_employee(client, name="Device Booker")
    other_employee_id = create_employee(client, name="Second Booker")
    resource_id = create_resource(
        client,
        resource_type="device",
        name="Projector Pool",
        code="PROJ-POOL",
        booking_mode="shared",
        max_quantity=3,
    )

    first_booking_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": employee_id,
            "title": "Borrow 2 projectors",
            "start_at": "2026-04-04T09:00:00Z",
            "end_at": "2026-04-04T18:00:00Z",
            "quantity": 2,
        },
        headers=api_key_headers(),
    )
    assert first_booking_response.status_code == 201

    second_booking_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": other_employee_id,
            "title": "Borrow 1 projector",
            "start_at": "2026-04-04T10:00:00Z",
            "end_at": "2026-04-04T12:00:00Z",
            "quantity": 1,
        },
        headers=api_key_headers(),
    )
    assert second_booking_response.status_code == 201

    limit_response = client.post(
        "/api/v1/resource-bookings",
        json={
            "resource_id": resource_id,
            "booked_by_employee_id": employee_id,
            "title": "Exceed quantity",
            "start_at": "2026-04-04T11:00:00Z",
            "end_at": "2026-04-04T13:00:00Z",
            "quantity": 1,
        },
        headers=api_key_headers(),
    )
    assert limit_response.status_code == 409

    availability_response = client.get(
        f"/api/v1/resources/{resource_id}/availability?start_at=2026-04-04T11:00:00Z&end_at=2026-04-04T13:00:00Z",
        headers=api_key_headers(),
    )
    assert availability_response.status_code == 200
    assert availability_response.json()["data"]["available"] is False
    assert availability_response.json()["data"]["available_quantity"] == 0


def test_timesheet_header_crud_and_filters(client: TestClient) -> None:
    employee_id = create_employee(client, name="Dora")
    header_id = create_header(
        client,
        employee_id,
        source_report_text="上周我主要做 Dora 项目的需求梳理和评审。",
        custom_fields={"source_batch": "batch-1"},
    )

    list_response = client.get(
        f"/api/v1/timesheet-headers?employee_id={employee_id}&status=draft",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert "需求梳理" in get_response.json()["data"]["source_report_text"]
    assert get_response.json()["data"]["custom_fields"]["source_batch"] == "batch-1"

    # draft -> returned is not a legal transition of the default state machine
    illegal_patch = client.patch(
        f"/api/v1/timesheet-headers/{header_id}",
        json={"status": "returned"},
        headers=api_key_headers(),
    )
    assert illegal_patch.status_code == 409

    submit_response = client.post(
        f"/api/v1/timesheet-headers/{header_id}/submit",
        json={},
        headers=api_key_headers(),
    )
    assert submit_response.status_code == 200

    patch_response = client.patch(
        f"/api/v1/timesheet-headers/{header_id}",
        json={
            "status": "returned",
            "source_report_text": "更正：上周主要做 Dora 项目评审和 API 对齐。",
            "custom_fields": {"source_batch": "batch-2"},
        },
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["status"] == "returned"
    assert "API 对齐" in patch_response.json()["data"]["source_report_text"]
    assert patch_response.json()["data"]["custom_fields"]["source_batch"] == "batch-2"


def test_patch_entry_rejects_unknown_fields_instead_of_ignoring_them(client: TestClient) -> None:
    """The audit's concrete case: PATCHing work_date used to 200 and change
    nothing — the worst outcome for an agent, which then reports the date as
    fixed. Unknown fields must 422 and name themselves."""
    employee_id = create_employee(client, name="Strict")
    header_id = create_header(client, employee_id)
    entry_id = create_entry(client, header_id, employee_id)

    response = client.patch(
        f"/api/v1/timesheet-entries/{entry_id}",
        json={"work_date": "2026-03-11"},
        headers=api_key_headers(),
    )
    assert response.status_code == 422
    assert "work_date" in response.text

    # declared fields still update fine
    response = client.patch(
        f"/api/v1/timesheet-entries/{entry_id}",
        json={"hours": 6.0},
        headers=api_key_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["hours"] == 6.0


def test_create_timesheet_header_duplicate_period_returns_conflict(client: TestClient) -> None:
    employee_id = create_employee(client, name="Dupe")
    header_id = create_header(client, employee_id)

    duplicate = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-03-09", "period_end": "2026-03-15"},
        headers=api_key_headers(),
    )
    assert duplicate.status_code == 409
    assert header_id in duplicate.json()["detail"]
    assert "2026-03-09..2026-03-15" in duplicate.json()["detail"]

    # an adjacent period is not a duplicate
    create_header(client, employee_id, period_start="2026-03-16", period_end="2026-03-22")

    # a soft-deleted header keeps its period slot (restore must stay collision-free)
    delete_response = client.delete(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert delete_response.status_code == 204
    recreate = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-03-09", "period_end": "2026-03-15"},
        headers=api_key_headers(),
    )
    assert recreate.status_code == 409
    assert "restore" in recreate.json()["detail"]


def test_timesheet_header_soft_delete_hides_header_and_blocks_follow_up_operations(client: TestClient) -> None:
    employee_id = create_employee(client, name="Helen")
    project_id = create_project(client, project_name="Deletion Flow")
    header_id = create_header(client, employee_id)
    entry_id = create_entry(client, header_id, employee_id, project_id=project_id, task="Cleanup")

    delete_response = client.request(
        "DELETE",
        f"/api/v1/timesheet-headers/{header_id}",
        json={"deleted_by": "admin-1", "delete_reason": "duplicate timesheet"},
        headers=api_key_headers(),
    )
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert get_response.status_code == 404

    detail_response = client.get(f"/api/v1/timesheet-headers/{header_id}/detail", headers=api_key_headers())
    assert detail_response.status_code == 404

    list_response = client.get("/api/v1/timesheet-headers?status=draft", headers=api_key_headers())
    assert list_response.status_code == 200
    assert header_id not in {item["id"] for item in list_response.json()["data"]}

    entry_get_response = client.get(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert entry_get_response.status_code == 404

    entry_list_response = client.get(f"/api/v1/timesheet-entries?header_id={header_id}", headers=api_key_headers())
    assert entry_list_response.status_code == 200
    assert entry_list_response.json()["meta"]["total"] == 0

    entry_update_response = client.patch(
        f"/api/v1/timesheet-entries/{entry_id}",
        json={"hours": 5},
        headers=api_key_headers(),
    )
    assert entry_update_response.status_code == 404

    submit_response = client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=api_key_headers())
    assert submit_response.status_code == 404

    delete_again_response = client.delete(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert delete_again_response.status_code == 204


def test_timesheet_header_include_deleted_and_restore(client: TestClient) -> None:
    employee_id = create_employee(client, name="Ivy")
    project_id = create_project(client, project_name="Restore Flow")
    header_id = create_header(client, employee_id)
    entry_id = create_entry(client, header_id, employee_id, project_id=project_id, task="Restore me")

    delete_response = client.request(
        "DELETE",
        f"/api/v1/timesheet-headers/{header_id}",
        json={"deleted_by": "admin-2", "delete_reason": "operator mistake"},
        headers=api_key_headers(),
    )
    assert delete_response.status_code == 204

    hidden_get_response = client.get(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert hidden_get_response.status_code == 404

    include_deleted_get_response = client.get(
        f"/api/v1/timesheet-headers/{header_id}?include_deleted=true",
        headers=api_key_headers(),
    )
    assert include_deleted_get_response.status_code == 200
    assert include_deleted_get_response.json()["data"]["id"] == header_id

    include_deleted_list_response = client.get(
        "/api/v1/timesheet-headers?include_deleted=true",
        headers=api_key_headers(),
    )
    assert include_deleted_list_response.status_code == 200
    assert header_id in {item["id"] for item in include_deleted_list_response.json()["data"]}

    include_deleted_detail_response = client.get(
        f"/api/v1/timesheet-headers/{header_id}/detail?include_deleted=true",
        headers=api_key_headers(),
    )
    assert include_deleted_detail_response.status_code == 200
    assert len(include_deleted_detail_response.json()["data"]["entries"]) == 1

    restore_response = client.post(
        f"/api/v1/timesheet-headers/{header_id}/restore",
        json={"restored_by": "admin-2"},
        headers=api_key_headers(),
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["data"]["id"] == header_id

    restored_get_response = client.get(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers())
    assert restored_get_response.status_code == 200

    restored_entry_get_response = client.get(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert restored_entry_get_response.status_code == 200


def test_timesheet_entry_crud_filters_and_soft_delete(client: TestClient) -> None:
    employee_id = create_employee(client, name="Eve")
    project_id = create_project(client, project_name="Platform")
    header_id = create_header(client, employee_id)
    entry_id = create_entry(
        client,
        header_id,
        employee_id,
        project_id=project_id,
        work_date="2026-03-11",
        task="Backend",
        client="Acme Corp",
        custom_fields={"ticket_no": "OPS-7"},
    )

    list_response = client.get(
        f"/api/v1/timesheet-entries?header_id={header_id}&employee_id={employee_id}&project_id={project_id}&work_date_from=2026-03-11&work_date_to=2026-03-11",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["task"] == "Backend"

    patch_response = client.patch(
        f"/api/v1/timesheet-entries/{entry_id}",
        json={"hours": 6, "notes": "Expanded scope", "custom_fields": {"ticket_no": "OPS-8"}},
        headers=api_key_headers(),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["hours"] == 6
    assert patch_response.json()["data"]["custom_fields"]["ticket_no"] == "OPS-8"

    delete_response = client.delete(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert delete_response.status_code == 204

    not_found_response = client.get(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert not_found_response.status_code == 404

    empty_list_response = client.get(f"/api/v1/timesheet-entries?header_id={header_id}", headers=api_key_headers())
    assert empty_list_response.status_code == 200
    assert empty_list_response.json()["meta"]["total"] == 0


def test_approval_record_listing_and_detail(client: TestClient) -> None:
    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)

    first_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "round_no": 1,
            "sequence_no": 2,
            "action": "commented",
            "comment": "Needs clarification",
            "acted_at": "2026-03-10T09:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "round_no": 1,
            "sequence_no": 3,
            "action": "approved",
            "approver_id": "mgr-2",
            "acted_at": "2026-03-10T10:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert second_response.status_code == 201
    approval_id = second_response.json()["data"]["id"]

    list_response = client.get(
        f"/api/v1/approval-records?entity_type=timesheet_header&entity_id={header_id}",
        headers=api_key_headers(),
    )
    assert list_response.status_code == 200
    assert [record["sequence_no"] for record in list_response.json()["data"]] == [2, 3]

    get_response = client.get(f"/api/v1/approval-records/{approval_id}", headers=api_key_headers())
    assert get_response.status_code == 200
    assert get_response.json()["data"]["action"] == "approved"


def test_approval_target_approval_records_do_not_generate_or_complete_employee_todos(client: TestClient) -> None:
    approver_employee_id = create_employee(client, name="Manager Mike")
    approval_target_id = create_approval_target(client)

    submitted_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "approval_target",
            "entity_id": approval_target_id,
            "round_no": 1,
            "sequence_no": 1,
            "action": "submitted",
            "approver_id": approver_employee_id,
            "approver_role": "manager",
            "source": "ai",
            "acted_at": "2026-04-02T09:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert submitted_response.status_code == 201

    open_todos_response = client.get(
        f"/api/v1/employees/{approver_employee_id}/todos?status=open&entity_type=approval_target&entity_id={approval_target_id}",
        headers=api_key_headers(),
    )
    assert open_todos_response.status_code == 200
    assert open_todos_response.json()["meta"]["total"] == 0

    approved_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "approval_target",
            "entity_id": approval_target_id,
            "round_no": 1,
            "sequence_no": 2,
            "action": "approved",
            "approver_id": approver_employee_id,
            "source": "ai",
            "acted_at": "2026-04-02T10:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approved_response.status_code == 201

    completed_todos_response = client.get(
        f"/api/v1/employees/{approver_employee_id}/todos?status=completed&entity_type=approval_target&entity_id={approval_target_id}",
        headers=api_key_headers(),
    )
    assert completed_todos_response.status_code == 200
    assert completed_todos_response.json()["meta"]["total"] == 0

def test_approval_todo_is_created_and_completed_explicitly(client: TestClient) -> None:
    employee_id = create_employee(client, name="Todo Owner")
    header_id = create_header(client, employee_id)
    approver_employee_id = create_employee(client, name="Manager Mike")

    todo_response = client.post(
        "/api/v1/todos",
        json={
            "employee_id": approver_employee_id,
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "title": "Review timesheet for Todo Owner",
            "description": "Please review this timesheet.",
            "todo_type": "approval",
            "created_by": "agent-approval-01",
            "metadata": {"round_no": 1, "sequence_no": 1},
        },
        headers=api_key_headers(),
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["data"]["id"]

    todo_list_response = client.get(
        f"/api/v1/todos?employee_id={approver_employee_id}&status=open",
        headers=api_key_headers(),
    )
    assert todo_list_response.status_code == 200
    assert todo_list_response.json()["meta"]["total"] == 1
    todo = todo_list_response.json()["data"][0]
    assert todo["id"] == todo_id
    assert todo["entity_id"] == header_id
    assert todo["employee_id"] == approver_employee_id
    assert todo["status"] == "open"
    assert todo["title"] == "Review timesheet for Todo Owner"
    assert todo["todo_type"] == "approval"
    assert todo["created_by"] == "agent-approval-01"

    employee_todo_list_response = client.get(
        f"/api/v1/employees/{approver_employee_id}/todos?status=open",
        headers=api_key_headers(),
    )
    assert employee_todo_list_response.status_code == 200
    assert employee_todo_list_response.json()["meta"]["total"] == 1
    assert employee_todo_list_response.json()["data"][0]["entity_id"] == header_id

    approve_response = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "round_no": 1,
            "sequence_no": 2,
            "action": "approved",
            "approver_id": approver_employee_id,
            "approver_role": "manager",
            "acted_at": "2026-03-10T10:00:00Z",
        },
        headers=api_key_headers(),
    )
    assert approve_response.status_code == 201

    complete_todo_response = client.patch(
        f"/api/v1/todos/{todo_id}",
        json={"status": "completed", "completed_by": approver_employee_id},
        headers=api_key_headers(),
    )
    assert complete_todo_response.status_code == 200
    assert complete_todo_response.json()["data"]["completed_by"] == approver_employee_id

    completed_todo_response = client.get(
        f"/api/v1/todos?employee_id={approver_employee_id}&status=completed&entity_type=timesheet_header&entity_id={header_id}",
        headers=api_key_headers(),
    )
    assert completed_todo_response.status_code == 200
    assert completed_todo_response.json()["meta"]["total"] == 1
    assert completed_todo_response.json()["data"][0]["entity_id"] == header_id
    assert completed_todo_response.json()["data"][0]["employee_id"] == approver_employee_id
    assert completed_todo_response.json()["data"][0]["completed_by"] == approver_employee_id

    todo_names_response = client.post(
        "/api/v1/directory/display-names/resolve",
        json={
            "employee_ids": [
                approver_employee_id,
                completed_todo_response.json()["data"][0]["completed_by"],
            ],
            "actor_labels": [todo["created_by"]],
        },
        headers=api_key_headers(),
    )
    assert todo_names_response.status_code == 200
    assert todo_names_response.json()["data"] == {
        "employees": {approver_employee_id: "Manager Mike"},
        # Arbitrary legacy agent labels remain a deliberate UI fallback.
        "actors": {},
        # Only principals that are more than a tenant-issued key are typed here.
        "actor_kinds": {},
    }

    employee_completed_todo_response = client.get(
        f"/api/v1/employees/{approver_employee_id}/todos?status=completed",
        headers=api_key_headers(),
    )
    assert employee_completed_todo_response.status_code == 200
    assert employee_completed_todo_response.json()["meta"]["total"] == 1
    assert employee_completed_todo_response.json()["data"][0]["entity_id"] == header_id


def test_create_todo_rejects_duplicate_open_todo_for_same_entity(client: TestClient) -> None:
    employee_id = create_employee(client, name="Todo Duplicate Owner")
    header_id = create_header(client, employee_id)

    first_todo_id = create_todo(client, employee_id, "timesheet_header", header_id)
    assert first_todo_id

    duplicate_response = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "title": "Duplicate review task",
        },
        headers=api_key_headers(),
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "open todo already exists for this entity"


def test_recreating_the_same_open_assignment_returns_it_instead_of_failing(
    client: TestClient,
) -> None:
    """A flow agent that crashed mid-write, or ran twice for one signal, must be
    able to tell "I already did this" from a real error. Approval records have
    always answered a retry with the recorded fact; assignments now do too."""
    employee_id = create_employee(client, name="Retry Owner")
    header_id = create_header(client, employee_id)
    assignment = {
        "employee_id": employee_id,
        "entity_type": "timesheet_header",
        "entity_id": header_id,
        "title": "Review timesheet",
        "todo_type": "approval",
        "metadata": {"round_no": 1, "sequence_no": 2, "workflow_version": 3},
    }

    first = client.post("/api/v1/todos", json=assignment, headers=api_key_headers())
    assert first.status_code == 201
    retry = client.post("/api/v1/todos", json=assignment, headers=api_key_headers())
    assert retry.status_code == 201
    assert retry.json()["data"]["id"] == first.json()["data"]["id"]

    # a different position in the flow is a different assignment, and the open
    # one says this caller's view of where the ball is has gone stale
    next_round = client.post(
        "/api/v1/todos",
        json={**assignment, "metadata": {"round_no": 2, "sequence_no": 1}},
        headers=api_key_headers(),
    )
    assert next_round.status_code == 409

    todos = client.get(
        f"/api/v1/todos?entity_id={header_id}", headers=api_key_headers()
    ).json()
    assert todos["meta"]["total"] == 1


def test_tenant_isolation_across_resources(client: TestClient) -> None:
    employee_id = create_employee(client, tenant_id=TEST_TENANT)
    project_id = create_project(client, tenant_id=TEST_TENANT)
    header_id = create_header(client, employee_id, tenant_id=TEST_TENANT)
    entry_id = create_entry(client, header_id, employee_id, tenant_id=TEST_TENANT, project_id=project_id)
    approval_id = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "action": "approved",
            "acted_at": "2026-03-12T10:00:00Z",
        },
        headers=api_key_headers(TEST_API_KEY),
    ).json()["data"]["id"]

    assert client.get(f"/api/v1/employees/{employee_id}", headers=api_key_headers(OTHER_API_KEY)).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}", headers=api_key_headers(OTHER_API_KEY)).status_code == 404
    assert client.get(f"/api/v1/timesheet-headers/{header_id}", headers=api_key_headers(OTHER_API_KEY)).status_code == 404
    assert client.get(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers(OTHER_API_KEY)).status_code == 404
    assert client.get(
        f"/api/v1/approval-records/{approval_id}",
        headers=api_key_headers(OTHER_API_KEY),
    ).status_code == 404


def test_entry_validation_rejects_mismatched_employee_and_out_of_period_date(client: TestClient) -> None:
    employee_id = create_employee(client, name="Frank")
    other_employee_id = create_employee(client, name="Grace")
    header_id = create_header(client, employee_id)

    mismatched_response = client.post(
        "/api/v1/timesheet-entries",
        json={
            "header_id": header_id,
            "employee_id": other_employee_id,
            "work_date": "2026-03-10",
            "hours": 8,
        },
        headers=api_key_headers(),
    )
    assert mismatched_response.status_code == 400
    assert "employee_id must match the header" in mismatched_response.json()["detail"]

    out_of_period_response = client.post(
        "/api/v1/timesheet-entries",
        json={
            "header_id": header_id,
            "employee_id": employee_id,
            "work_date": "2026-03-20",
            "hours": 8,
        },
        headers=api_key_headers(),
    )
    assert out_of_period_response.status_code == 400
    assert "work_date must be inside the header period" in out_of_period_response.json()["detail"]


def test_entry_update_blocked_after_submit(client: TestClient) -> None:
    employee_id = create_employee(client, name="Bob")
    header_id = create_header(client, employee_id)
    entry_id = create_entry(client, header_id, employee_id, hours=8)

    client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=api_key_headers())

    update_response = client.patch(
        f"/api/v1/timesheet-entries/{entry_id}",
        json={"hours": 6},
        headers=api_key_headers(),
    )
    assert update_response.status_code == 409

    delete_response = client.delete(f"/api/v1/timesheet-entries/{entry_id}", headers=api_key_headers())
    assert delete_response.status_code == 409


def test_todo_optional_pagination_and_keyword_contract(client: TestClient) -> None:
    employee_id = create_employee(client)
    project_ids = [
        create_project(client, project_name=f"Project {index}") for index in range(3)
    ]
    create_todo(
        client,
        employee_id,
        "project",
        project_ids[0],
        title="Needle review",
        description="check the milestone",
    )
    create_todo(
        client,
        employee_id,
        "project",
        project_ids[1],
        title="Other review",
        todo_type="needle-kind",
    )
    create_todo(
        client,
        employee_id,
        "project",
        project_ids[2],
        title="Completed review",
        status="completed",
    )

    legacy = client.get("/api/v1/todos", headers=api_key_headers()).json()
    assert len(legacy["data"]) == 3
    assert legacy["meta"] == {"total": 3}

    paged = client.get(
        "/api/v1/todos",
        params={"page": 1, "size": 1, "keyword": "needle", "status": "open"},
        headers=api_key_headers(),
    ).json()
    assert paged["meta"] == {"total": 2, "page": 1, "page_size": 1, "pages": 2}
    assert len(paged["data"]) == 1
    assert paged["data"][0]["status"] == "open"
    assert "metadata" in paged["data"][0]


def test_approval_optional_pagination_action_and_keyword_contract(client: TestClient) -> None:
    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)
    for sequence_no, action, comment, acted_at in (
        (1, "commented", "Needle clarification", "2026-03-10T09:00:00Z"),
        (2, "approved", "Needle resolved", "2026-03-10T10:00:00Z"),
        (3, "commented", "Unrelated", "2026-03-10T11:00:00Z"),
    ):
        response = client.post(
            "/api/v1/approval-records",
            json={
                "entity_type": "timesheet_header",
                "entity_id": header_id,
                "sequence_no": sequence_no,
                "action": action,
                "comment": comment,
                "acted_at": acted_at,
            },
            headers=api_key_headers(),
        )
        assert response.status_code == 201

    legacy = client.get(
        "/api/v1/approval-records",
        params={"entity_type": "timesheet_header", "entity_id": header_id},
        headers=api_key_headers(),
    ).json()
    assert [record["sequence_no"] for record in legacy["data"]] == [1, 2, 3]
    assert legacy["meta"] == {"total": 3}

    paged = client.get(
        "/api/v1/approval-records",
        params={"page": 1, "size": 20, "keyword": "needle", "action": "commented"},
        headers=api_key_headers(),
    ).json()
    assert paged["meta"] == {"total": 1, "page": 1, "page_size": 20, "pages": 1}
    assert [record["sequence_no"] for record in paged["data"]] == [1]


def test_builtin_object_lists_support_compatible_server_pagination(client: TestClient) -> None:
    employee_id = create_employee(client)
    resource_id = create_resource(client)

    for index, marker in enumerate(("Needle", "Other"), start=1):
        timesheet = client.post(
            "/api/v1/timesheet-headers",
            json={
                "employee_id": employee_id,
                "period_start": f"2026-04-{index * 7 - 6:02d}",
                "period_end": f"2026-04-{index * 7:02d}",
                "source_report_text": f"{marker} timesheet",
            },
            headers=api_key_headers(),
        )
        assert timesheet.status_code == 201
        expense = client.post(
            "/api/v1/expense-claims",
            json={"employee_id": employee_id, "title": f"{marker} expense"},
            headers=api_key_headers(),
        )
        assert expense.status_code == 201
        purchase = client.post(
            "/api/v1/purchase-requests",
            json={"employee_id": employee_id, "title": f"{marker} purchase"},
            headers=api_key_headers(),
        )
        assert purchase.status_code == 201
        booking = client.post(
            "/api/v1/resource-bookings",
            json={
                "resource_id": resource_id,
                "booked_by_employee_id": employee_id,
                "title": f"{marker} booking",
                "start_at": f"2026-04-{20 + index:02d}T09:00:00Z",
                "end_at": f"2026-04-{20 + index:02d}T10:00:00Z",
            },
            headers=api_key_headers(),
        )
        assert booking.status_code == 201

    for path in (
        "/api/v1/timesheet-headers",
        "/api/v1/expense-claims",
        "/api/v1/purchase-requests",
        "/api/v1/resource-bookings",
    ):
        legacy = client.get(path, headers=api_key_headers()).json()
        assert len(legacy["data"]) == 2
        assert legacy["meta"] == {"total": 2}

        paged = client.get(
            path,
            params={"page": 1, "size": 1, "keyword": "needle"},
            headers=api_key_headers(),
        ).json()
        assert paged["meta"] == {"total": 1, "page": 1, "page_size": 1, "pages": 1}
        assert len(paged["data"]) == 1


def test_console_lists_export_typed_openapi_contracts() -> None:
    expected = {
        "/api/v1/todos": "ListEnvelope_TodoRead_",
        "/api/v1/approval-records": "ListEnvelope_ApprovalRecordRead_",
        "/api/v1/business-objects": "ListEnvelope_BusinessObjectRead_",
        "/api/v1/business-objects/{business_object_id}/detail": "Envelope_BusinessObjectDetailRead_",
        "/api/v1/business-object-links": "ListEnvelope_BusinessObjectLinkRead_",
        "/api/v1/object-directory": "ListEnvelope_ObjectDirectoryEntryRead_",
        "/api/v1/object-type-definitions": "ListEnvelope_ObjectTypeDefinitionRead_",
        "/api/v1/workflow-definitions": "ListEnvelope_WorkflowDefinitionRead_",
        "/api/v1/skills": "ListEnvelope_TenantSkillSummary_",
        "/api/v1/tenant/api-keys": "ListEnvelope_ApiKeyRead_",
        "/api/v1/tenant/api-key-owners": "ListEnvelope_ApiKeyOwnerRead_",
        "/api/v1/timesheet-headers": "ListEnvelope_TimesheetHeaderRead_",
        "/api/v1/expense-claims": "ListEnvelope_ExpenseClaimRead_",
        "/api/v1/purchase-requests": "ListEnvelope_PurchaseRequestRead_",
        "/api/v1/resource-bookings": "ListEnvelope_ResourceBookingRead_",
    }
    contract = app.openapi()
    for path, schema_name in expected.items():
        response_schema = contract["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"] == f"#/components/schemas/{schema_name}"

    display_name_schema = contract["paths"]["/api/v1/directory/display-names/resolve"][
        "post"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    assert display_name_schema["$ref"] == (
        "#/components/schemas/Envelope_DisplayNameResolutionRead_"
    )
