from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import enriched_api_key
from app.models import ApiKey
from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


def provision_tenant(client: TestClient) -> dict:
    """Register a tenant through the real flow so roles/capabilities are
    provisioned; returns service key + admin session."""
    data = bootstrap_tenant(client, company_name="RBAC Co", email="admin@rbac-co.com", password="rbac-pass1")
    return {
        "service": {"X-API-Key": data["plain_text_api_key"]},
        "admin": {"Authorization": f"Bearer {data['session_token']}"},
    }


def invite_with_role(
    client: TestClient,
    headers: dict,
    email: str,
    role: str,
    employee_id: str | None = None,
    name: str | None = None,
) -> dict:
    body = {"email": email, "role": role}
    if employee_id:
        body["employee_id"] = employee_id
    if name:
        body["name"] = name
    response = client.post("/api/v1/auth/invitations", json=body, headers=headers)
    assert response.status_code == 201, response.text
    user_id = response.json()["data"]["id"]
    token = extract_token(outbox.messages[-1].body)
    client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
    key = client.post(
        "/api/v1/tenant/api-keys", json={"label": f"{role}-agent", "user_id": user_id}, headers=headers
    ).json()["data"]["plain_text_api_key"]
    return {"user_id": user_id, "headers": {"X-API-Key": key}}


def test_provisioning_seeds_catalog_and_roles(client: TestClient) -> None:
    ctx = provision_tenant(client)
    roles = client.get("/api/v1/roles", headers=ctx["service"]).json()["data"]
    assert {r["name"] for r in roles if r["is_system"]} == {"admin", "member"}
    admin_role = next(r for r in roles if r["name"] == "admin")
    assert "users.manage" in admin_role["permissions"]

    catalog = client.get("/api/v1/capabilities", headers=ctx["service"]).json()["data"]
    names = {c["name"] for c in catalog["capabilities"]}
    assert "business_object.write" in names and "timesheet.advance" in names
    assert "business_object.summarize" in names
    assert all(c["kind"] == "system" for c in catalog["capabilities"])

    # /auth/me reports the resolved permission set
    me = client.get("/api/v1/auth/me", headers=ctx["admin"]).json()["data"]
    assert "users.manage" in me["permissions"]

    # product skills carry their capability gates
    approve = client.get("/api/v1/skills/oryh-approve", headers=ctx["service"]).json()["data"]
    assert approve["required_capability"] == "approval.record"
    summary = client.get(
        "/api/v1/skills/oryh-business-object-summary", headers=ctx["service"]
    ).json()["data"]
    assert summary["required_capability"] == "business_object.summarize"


def test_scoped_custom_role(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]

    # a custom capability + a vendor role scoped to warranty types only
    assert client.post(
        "/api/v1/capabilities",
        json={"name": "jc.warranty.approve", "title": "保修卡审批资格"},
        headers=service,
    ).status_code == 201
    response = client.post(
        "/api/v1/roles",
        json={
            "name": "vendor",
            "title": "外部服务商",
            "permissions": [
                "business_object.write:warranty_card",
                "business_object.write:warranty_repair",
                "todos.complete_own",
                "jc.warranty.approve",
            ],
        },
        headers=service,
    )
    assert response.status_code == 201, response.text

    # grammar validation
    assert client.post(
        "/api/v1/roles", json={"name": "bad1", "permissions": ["no.such.verb"]}, headers=service
    ).status_code == 422
    assert client.post(
        "/api/v1/roles", json={"name": "bad2", "permissions": ["approval.record:warranty_card"]}, headers=service
    ).status_code == 422

    employee_id = client.post("/api/v1/employees", json={"name": "张伟"}, headers=service).json()["data"]["id"]
    vendor = invite_with_role(client, service, "vendor@partner-co.com", "vendor", employee_id)

    # scoped write: warranty_card allowed, expense_claim denied
    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "warranty_card", "title": "Card"},
        headers=vendor["headers"],
    ).status_code == 201
    denied = client.post(
        "/api/v1/business-objects",
        json={"object_type": "expense_claim", "title": "Claim"},
        headers=vendor["headers"],
    )
    assert denied.status_code == 403
    assert "business_object.write:expense_claim" in denied.json()["detail"]

    # capabilities the role lacks
    assert client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-07-06", "period_end": "2026-07-12"},
        headers=vendor["headers"],
    ).status_code == 403  # no timesheet.submit_own
    assert client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "business_object",
            "entity_id": "00000000-0000-0000-0000-000000000000",
            "action": "approved",
            "sequence_no": 2,
        },
        headers=vendor["headers"],
    ).status_code == 403  # no approval.record

    # inviting with an undefined role is rejected
    assert client.post(
        "/api/v1/auth/invitations",
        json={"email": "x@partner-co.com", "role": "nonexistent"},
        headers=service,
    ).status_code == 422


def test_business_object_link_delete_requires_write_on_both_object_types(
    client: TestClient,
) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    for object_type in ("source_type", "target_type"):
        assert client.post(
            "/api/v1/object-type-definitions",
            json={"object_type": object_type, "json_schema": {}},
            headers=service,
        ).status_code == 201
    role_response = client.post(
        "/api/v1/roles",
        json={
            "name": "source_writer",
            "permissions": ["business_object.write:source_type"],
        },
        headers=service,
    )
    assert role_response.status_code == 201, role_response.text
    scoped = invite_with_role(
        client, service, "source-writer@partner-co.com", "source_writer"
    )

    source = client.post(
        "/api/v1/business-objects",
        json={"object_type": "source_type", "title": "Source"},
        headers=service,
    ).json()["data"]
    target = client.post(
        "/api/v1/business-objects",
        json={"object_type": "target_type", "title": "Target"},
        headers=service,
    ).json()["data"]
    link_payload = {
        "source_object_id": source["id"],
        "target_object_id": target["id"],
        "link_type": "related",
    }
    denied_create = client.post(
        "/api/v1/business-object-links",
        json=link_payload,
        headers=scoped["headers"],
    )
    assert denied_create.status_code == 403
    assert "business_object.write:target_type" in denied_create.json()["detail"]
    link = client.post(
        "/api/v1/business-object-links",
        json=link_payload,
        headers=service,
    ).json()["data"]

    denied = client.delete(
        f"/api/v1/business-object-links/{link['id']}", headers=scoped["headers"]
    )
    assert denied.status_code == 403
    assert "business_object.write:target_type" in denied.json()["detail"]
    assert client.get(
        f"/api/v1/business-object-links/{link['id']}", headers=service
    ).status_code == 200
    assert client.delete(
        f"/api/v1/business-object-links/{link['id']}", headers=service
    ).status_code == 204

    assert client.delete(
        f"/api/v1/business-objects/{target['id']}", headers=scoped["headers"]
    ).status_code == 403
    assert client.delete(
        f"/api/v1/business-objects/{target['id']}", headers=service
    ).status_code == 204
    denied_restore = client.post(
        f"/api/v1/business-objects/{target['id']}/restore",
        json={},
        headers=scoped["headers"],
    )
    assert denied_restore.status_code == 403
    assert "business_object.write:target_type" in denied_restore.json()["detail"]
    assert client.post(
        f"/api/v1/business-objects/{target['id']}/restore", json={}, headers=service
    ).status_code == 200


def test_key_manager_owner_search_and_effective_role(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    for role_name, permissions in (
        ("key_manager", ["keys.manage"]),
        ("auditor", []),
    ):
        response = client.post(
            "/api/v1/roles",
            json={"name": role_name, "permissions": permissions},
            headers=service,
        )
        assert response.status_code == 201, response.text

    manager = invite_with_role(
        client,
        service,
        "key-manager@rbac-co.com",
        "key_manager",
        name="Key Manager",
    )
    alpha = invite_with_role(
        client,
        service,
        "owner-alpha@rbac-co.com",
        "member",
        name="Owner Alpha",
    )
    beta = invite_with_role(
        client,
        service,
        "owner-beta@rbac-co.com",
        "member",
        name="Owner Beta",
    )
    pending = client.post(
        "/api/v1/auth/invitations",
        json={
            "email": "owner-pending@rbac-co.com",
            "name": "Owner Pending",
            "role": "member",
        },
        headers=service,
    )
    assert pending.status_code == 201

    assert client.get("/api/v1/auth/users", headers=manager["headers"]).status_code == 403
    first_page = client.get(
        "/api/v1/tenant/api-key-owners",
        params={"keyword": "Owner", "page": 1, "size": 1},
        headers=manager["headers"],
    ).json()
    second_page = client.get(
        "/api/v1/tenant/api-key-owners",
        params={"keyword": "Owner", "page": 2, "size": 1},
        headers=manager["headers"],
    ).json()
    assert first_page["meta"] == {"total": 2, "page": 1, "page_size": 1, "pages": 2}
    assert second_page["meta"] == {"total": 2, "page": 2, "page_size": 1, "pages": 2}
    assert {
        first_page["data"][0]["id"], second_page["data"][0]["id"]
    } == {alpha["user_id"], beta["user_id"]}
    assert all(
        owner["status"] == "active"
        for owner in first_page["data"] + second_page["data"]
    )

    created = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "owner-extra", "user_id": alpha["user_id"]},
        headers=manager["headers"],
    )
    assert created.status_code == 201, created.text
    key = created.json()["data"]["api_key"]
    assert key["user_name"] == "Owner Alpha"
    assert key["user_email"] == "owner-alpha@rbac-co.com"
    assert key["role"] == "member"
    assert key["effective_role"] == "member"
    assert key["user_status"] == "active"
    assert key["effective_active"] is True

    updated = client.patch(
        f"/api/v1/tenant/api-keys/{key['id']}",
        json={"label": "owner-renamed"},
        headers=manager["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["user_name"] == "Owner Alpha"
    assert updated.json()["data"]["effective_role"] == "member"
    assert updated.json()["data"]["effective_active"] is True

    changed = client.patch(
        f"/api/v1/auth/users/{alpha['user_id']}",
        json={"role": "auditor"},
        headers=service,
    )
    assert changed.status_code == 200, changed.text
    listed = client.get(
        "/api/v1/tenant/api-keys",
        params={"user_id": alpha["user_id"], "page": 1, "size": 20},
        headers=manager["headers"],
    ).json()
    assert listed["meta"]["total"] == 2
    assert {item["role"] for item in listed["data"]} == {"member"}
    assert {item["effective_role"] for item in listed["data"]} == {"auditor"}
    assert {item["effective_active"] for item in listed["data"]} == {True}
    assert {item["user_status"] for item in listed["data"]} == {"active"}
    assert {item["user_email"] for item in listed["data"]} == {
        "owner-alpha@rbac-co.com"
    }
    assert client.get(
        "/api/v1/tenant/api-key-owners", headers=alpha["headers"]
    ).status_code == 403

    disabled = client.patch(
        f"/api/v1/auth/users/{alpha['user_id']}",
        json={"status": "disabled"},
        headers=service,
    )
    assert disabled.status_code == 200, disabled.text
    disabled_keys = client.get(
        "/api/v1/tenant/api-keys",
        params={"user_id": alpha["user_id"], "page": 1, "size": 20},
        headers=manager["headers"],
    ).json()["data"]
    assert {item["is_active"] for item in disabled_keys} == {True}
    assert {item["effective_active"] for item in disabled_keys} == {False}
    assert {item["effective_role"] for item in disabled_keys} == {None}
    assert {item["user_status"] for item in disabled_keys} == {"disabled"}
    assert client.get("/api/v1/auth/me", headers=alpha["headers"]).status_code == 401

    service_key = next(
        item
        for item in client.get(
            "/api/v1/tenant/api-keys", headers=manager["headers"]
        ).json()["data"]
        if item["user_id"] is None
    )
    assert service_key["user_name"] is None
    assert service_key["user_email"] is None
    assert service_key["user_status"] is None
    assert service_key["effective_active"] is True
    assert service_key["effective_role"] == service_key["role"]

    missing_owner_key = ApiKey(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        key_hash="missing-owner-key",
        label="orphaned",
        user_id="00000000-0000-0000-0000-000000000003",
        role="member",
        is_active=True,
        created_at=service_key["created_at"],
    )
    orphaned = enriched_api_key(missing_owner_key).model_dump()
    assert orphaned["user_status"] is None
    assert orphaned["effective_active"] is False
    assert orphaned["effective_role"] is None


def test_role_and_capability_guards(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]

    # lockout guard: admin role must keep users.manage
    assert client.patch(
        "/api/v1/roles/admin", json={"permissions": ["timesheet.submit_own"]}, headers=service
    ).status_code == 422

    # tuning member baseline is allowed (strip approval.record)
    member = client.get("/api/v1/roles", headers=service).json()["data"]
    member_perms = next(r["permissions"] for r in member if r["name"] == "member")
    trimmed = [p for p in member_perms if p != "approval.record"]
    assert client.patch(
        "/api/v1/roles/member", json={"permissions": trimmed}, headers=service
    ).status_code == 200

    # system roles cannot be deleted; roles in use cannot be deleted
    assert client.delete("/api/v1/roles/member", headers=service).status_code == 409
    client.post("/api/v1/roles", json={"name": "temp", "permissions": []}, headers=service)
    invite_with_role(client, service, "temp@rbac-co.com", "temp")
    assert client.delete("/api/v1/roles/temp", headers=service).status_code == 409

    # custom capability referenced by a role cannot be deleted
    client.post("/api/v1/capabilities", json={"name": "x.cap"}, headers=service)
    client.post("/api/v1/roles", json={"name": "capuser", "permissions": ["x.cap"]}, headers=service)
    assert client.delete("/api/v1/capabilities/x.cap", headers=service).status_code == 409
    # system capability cannot be deleted
    assert client.delete("/api/v1/capabilities/users.manage", headers=service).status_code == 409

    # member (no users.manage) cannot manage roles
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    member_user = invite_with_role(client, service, "wang@rbac-co.com", "member", employee_id)
    assert client.post(
        "/api/v1/roles", json={"name": "hax", "permissions": []}, headers=member_user["headers"]
    ).status_code == 403


def test_member_baseline_preserved(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    member = invite_with_role(client, service, "wang2@rbac-co.com", "member", employee_id)

    # member can still: submit own timesheet, write objects, record approvals
    header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-07-06", "period_end": "2026-07-12"},
        headers=member["headers"],
    )
    assert header.status_code == 201
    assert client.post(
        f"/api/v1/timesheet-headers/{header.json()['data']['id']}/submit", json={}, headers=member["headers"]
    ).status_code == 200
    assert client.post(
        "/api/v1/business-objects", json={"object_type": "note", "title": "N"}, headers=member["headers"]
    ).status_code == 201
    # but not: advance status, manage anything
    assert client.patch(
        f"/api/v1/timesheet-headers/{header.json()['data']['id']}",
        json={"status": "approved"}, headers=member["headers"],
    ).status_code == 403
    assert client.get("/api/v1/tenant/api-keys", headers=member["headers"]).status_code == 403


def test_member_expense_baseline(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小李"}, headers=service).json()["data"]["id"]
    member = invite_with_role(client, service, "li@rbac-co.com", "member", employee_id)

    # member can submit their own expense claim with a receipt attachment
    claim = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": employee_id, "title": "打车报销"},
        headers=member["headers"],
    )
    assert claim.status_code == 201
    claim_id = claim.json()["data"]["id"]
    attachment = client.post(
        "/api/v1/attachments",
        json={"filename": "taxi.png", "content_type": "image/png", "content_base64": "aGVsbG8="},
        headers=member["headers"],
    )
    assert attachment.status_code == 201
    assert client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": claim_id,
            "employee_id": employee_id,
            "expense_date": "2026-07-10",
            "category": "transport",
            "amount": 45.0,
            "attachment_id": attachment.json()["data"]["id"],
        },
        headers=member["headers"],
    ).status_code == 201
    assert client.post(
        f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=member["headers"]
    ).status_code == 200

    # but not advance the claim's status (expense.advance) …
    assert client.patch(
        f"/api/v1/expense-claims/{claim_id}", json={"status": "approved"}, headers=member["headers"]
    ).status_code == 403

    # … nor act on someone else's claim
    other_employee = client.post("/api/v1/employees", json={"name": "别人"}, headers=service).json()["data"]["id"]
    other_claim = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": other_employee, "title": "别人的报销"},
        headers=service,
    ).json()["data"]["id"]
    assert client.post(
        f"/api/v1/expense-claims/{other_claim}/submit", json={}, headers=member["headers"]
    ).status_code == 403
    assert client.post(
        "/api/v1/expense-claims",
        json={"employee_id": other_employee, "title": "替别人建"},
        headers=member["headers"],
    ).status_code == 403


def test_member_purchase_baseline(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小周"}, headers=service).json()["data"]["id"]
    member = invite_with_role(client, service, "zhou@rbac-co.com", "member", employee_id)

    # member can file and submit their own purchase request (with a quote attachment)
    request = client.post(
        "/api/v1/purchase-requests",
        json={"employee_id": employee_id, "title": "买一把人体工学椅"},
        headers=member["headers"],
    )
    assert request.status_code == 201
    request_id = request.json()["data"]["id"]
    attachment = client.post(
        "/api/v1/attachments",
        json={"filename": "quote.pdf", "content_type": "application/pdf", "content_base64": "cXVvdGU="},
        headers=member["headers"],
    )
    assert attachment.status_code == 201
    assert client.post(
        "/api/v1/purchase-request-items",
        json={
            "request_id": request_id,
            "product_name_snapshot": "人体工学椅",
            "quantity": 1,
            "unit_price": 1899.0,
            "attachment_id": attachment.json()["data"]["id"],
        },
        headers=member["headers"],
    ).status_code == 201
    assert client.post(
        f"/api/v1/purchase-requests/{request_id}/submit", json={}, headers=member["headers"]
    ).status_code == 200

    # but not advance the status (purchase.advance) …
    assert client.patch(
        f"/api/v1/purchase-requests/{request_id}", json={"status": "approved"}, headers=member["headers"]
    ).status_code == 403

    # … nor file for someone else
    other_employee = client.post("/api/v1/employees", json={"name": "别人"}, headers=service).json()["data"]["id"]
    assert client.post(
        "/api/v1/purchase-requests",
        json={"employee_id": other_employee, "title": "替别人申请"},
        headers=member["headers"],
    ).status_code == 403


def test_member_cannot_assign_todos_but_completes_own(client: TestClient) -> None:
    """todos.assign is not in the member baseline: assigning work is routing,
    the flow/admin side's write. Members still complete their own todos."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post(
        "/api/v1/employees", json={"name": "小李"}, headers=service
    ).json()["data"]["id"]
    colleague_id = client.post(
        "/api/v1/employees", json={"name": "小张"}, headers=service
    ).json()["data"]["id"]
    member = invite_with_role(client, service, "li@rbac-co.com", "member", employee_id)

    header_id = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-07-20", "period_end": "2026-07-26"},
        headers=service,
    ).json()["data"]["id"]

    # a member key cannot mint todos — not for a colleague, not even for itself
    for target in (colleague_id, employee_id):
        denied = client.post(
            "/api/v1/todos",
            json={
                "employee_id": target,
                "entity_type": "timesheet_header",
                "entity_id": header_id,
                "title": "看一下这份工时",
            },
            headers=member["headers"],
        )
        assert denied.status_code == 403, denied.text
        assert "todos.assign" in denied.json()["detail"]

    # the flow side (service credential) assigns; the member completes its own
    todo_id = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "title": "补一下周三的工时",
            "todo_type": "rework",
        },
        headers=service,
    ).json()["data"]["id"]
    completed = client.patch(
        f"/api/v1/todos/{todo_id}", json={"status": "completed"}, headers=member["headers"]
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["status"] == "completed"


def test_role_update_audit_records_what_was_taken_away(client: TestClient) -> None:
    """Regression from the E2E run: an agent read six `role.updated` rows,
    saw `booking.own` in none of them, and told its principal the admin had
    probably dropped it by accident. It was deliberate.

    The agent's reasoning was sound given what it could see. `permissions` is
    a full replacement, so an omitted grant and a removed one produced
    identical rows — and a role changed for the first time has no prior row to
    diff against, making the before-state unrecoverable from the trail.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]

    before = client.get("/api/v1/roles", headers=service).json()["data"]
    member = next(role for role in before if role["name"] == "member")
    kept = [grant for grant in member["permissions"] if grant != "booking.own"]
    assert "booking.own" in member["permissions"], member["permissions"]

    response = client.patch(
        "/api/v1/roles/member", json={"permissions": kept + ["todos.assign"]}, headers=service
    )
    assert response.status_code == 200, response.text

    row = next(
        entry for entry in client.get(
            "/api/v1/audit-logs?action=role.updated", headers=service
        ).json()["data"]
        if entry["detail"]["name"] == "member"
    )
    assert row["detail"]["removed"] == ["booking.own"]
    assert row["detail"]["added"] == ["todos.assign"]
    # the baseline role carries every future hire; the trail says when a
    # change reached that far
    assert row["detail"]["is_system"] is True
    # the resulting set is still there — the delta is in addition, not instead
    assert set(row["detail"]["permissions"]) == set(kept) | {"todos.assign"}


def test_roles_carry_their_headcount(client: TestClient) -> None:
    """`$oryh-access-admin` must state how many people a role change reaches
    before writing. Deriving that needed a second call and `users.manage` —
    a mandated sentence nobody could afford to say correctly.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    for local in ("a", "b", "c"):
        invite_with_role(client, service, f"{local}@rbac-co.com", "member")

    roles = {role["name"]: role for role in client.get("/api/v1/roles", headers=service).json()["data"]}
    assert roles["member"]["user_count"] == 3
    assert roles["admin"]["user_count"] == 1          # the registering admin
    # a role nobody holds says so rather than omitting the field
    created = client.post(
        "/api/v1/roles",
        json={"name": "auditor", "title": "审计", "permissions": ["approval.record"]},
        headers=service,
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["user_count"] == 0


def test_an_undeclared_role_cannot_be_assigned(client: TestClient) -> None:
    """A workspace's roles are the only role names it has.

    A live E2E reported that a new tenant's `dept_manager` could not approve,
    and filed the root cause against provisioning. Provisioning never made that
    role: the product ships `admin` and `member`, and `member` already carries
    `approval.record` and `todos.complete_own`. A fixture had written the
    string straight into `users.role`, producing an account that authenticates
    and can do nothing — the 403 was correct, and the report read it as a
    permissions bug because a permission-less account looks exactly like one.

    What the API must never do is create that state, so this pins both ends:
    an undeclared name is refused on the way in, and a declared one that
    people hold cannot be removed underneath them.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]

    refused = client.post(
        "/api/v1/auth/invitations",
        json={"email": "manager@rbac-co.com", "role": "dept_manager"},
        headers=service,
    )
    assert refused.status_code == 422, refused.text
    assert "not defined for this tenant" in refused.json()["detail"]

    # declare it, and the same invitation is ordinary
    created = client.post(
        "/api/v1/roles",
        json={
            "name": "dept_manager",
            "title": "部门经理",
            "permissions": ["approval.record", "todos.complete_own"],
        },
        headers=service,
    )
    assert created.status_code == 201, created.text
    manager = invite_with_role(client, service, "manager@rbac-co.com", "dept_manager")

    # the capability the report said was missing, exercised end to end
    employee_id = client.post(
        "/api/v1/employees", json={"name": "提交人"}, headers=service
    ).json()["data"]["id"]
    header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": "2026-07-06", "period_end": "2026-07-12"},
        headers=service,
    ).json()["data"]["id"]
    client.post(f"/api/v1/timesheet-headers/{header}/submit", json={}, headers=service)
    recorded = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "timesheet_header",
            "entity_id": header,
            "action": "approved",
            "sequence_no": 2,
            "comment": "ok",
            # required, and required for a reason: an approval fact without
            # the moment it was made cannot be ordered against the submission
        },
        headers=manager["headers"],
    )
    assert recorded.status_code == 201, recorded.text

    # and the role cannot be deleted while it is what makes that possible
    removed = client.delete("/api/v1/roles/dept_manager", headers=service)
    assert removed.status_code == 409, removed.text
    assert "assigned to users" in removed.json()["detail"]


def test_changing_a_user_to_an_undeclared_role_is_refused(client: TestClient) -> None:
    """The second door onto the same state: PATCH rather than invitation."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    member = invite_with_role(client, service, "member@rbac-co.com", "member")

    response = client.patch(
        f"/api/v1/auth/users/{member['user_id']}",
        json={"role": "finance_reviewer"},
        headers=service,
    )
    assert response.status_code == 422, response.text
    assert "not defined for this tenant" in response.json()["detail"]
