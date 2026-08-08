from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    """Invitation emails still carry a token; only the tenant's own creation
    stopped going through the mailbox."""
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token in email body: {body!r}")


def provision_tenant(client: TestClient, slug: str = "master") -> dict:
    data = bootstrap_tenant(
        client,
        company_name=f"{slug.title()} Co",
        email=f"admin@{slug}.example",
        password="admin-pass1",
    )
    return {
        "tenant_id": data["tenant"]["id"],
        "service": {"X-API-Key": data["plain_text_api_key"]},
        "admin": {"Authorization": f"Bearer {data['session_token']}"},
    }


def invite_role_user(
    client: TestClient,
    service: dict[str, str],
    *,
    role: str,
    email: str,
) -> dict:
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "role": role},
        headers=service,
    )
    assert invited.status_code == 201, invited.text
    user_id = invited.json()["data"]["id"]
    token = extract_token(outbox.messages[-1].body)
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "password": "member-pass1"},
    )
    assert accepted.status_code == 200, accepted.text
    session_token = accepted.json()["data"]["session_token"]
    key = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": f"{role}-test", "user_id": user_id},
        headers=service,
    )
    assert key.status_code == 201, key.text
    return {
        "headers": {"X-API-Key": key.json()["data"]["plain_text_api_key"]},
        "session_token": session_token,
    }


def create_master_rows(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    project = client.post(
        "/api/v1/projects", json={"project_name": "Console Project"}, headers=headers
    )
    vendor = client.post(
        "/api/v1/vendors", json={"name": "Console Vendor"}, headers=headers
    )
    product = client.post(
        "/api/v1/products", json={"name": "Console Product"}, headers=headers
    )
    resource = client.post(
        "/api/v1/resources",
        json={"resource_type": "meeting_room", "name": "Console Room"},
        headers=headers,
    )
    for response in (project, vendor, product, resource):
        assert response.status_code == 201, response.text
    sku = client.post(
        "/api/v1/product-skus",
        json={"product_id": product.json()["data"]["id"], "sku_code": "CONSOLE-SKU"},
        headers=headers,
    )
    assert sku.status_code == 201, sku.text
    return {
        "projects": project.json()["data"]["id"],
        "vendors": vendor.json()["data"]["id"],
        "products": product.json()["data"]["id"],
        "product-skus": sku.json()["data"]["id"],
        "resources": resource.json()["data"]["id"],
    }


def test_optional_pagination_preserves_full_lists_and_filters(client: TestClient) -> None:
    service = provision_tenant(client)["service"]

    for index in range(5):
        project = client.post(
            "/api/v1/projects",
            json={
                "project_name": f"Migration {index}",
                "status": "active" if index < 3 else "archived",
            },
            headers=service,
        )
        vendor = client.post(
            "/api/v1/vendors",
            json={
                "name": f"Travel Vendor {index}",
                "tax_id": "MATCH-TAX" if index < 3 else "OTHER-TAX",
                "status": "active" if index < 4 else "archived",
            },
            headers=service,
        )
        resource = client.post(
            "/api/v1/resources",
            json={
                "resource_type": "meeting_room" if index < 4 else "vehicle",
                "name": f"Jade Resource {index}",
                "booking_mode": "shared" if index < 3 else "exclusive",
                "status": "active" if index < 4 else "archived",
            },
            headers=service,
        )
        for response in (project, vendor, resource):
            assert response.status_code == 201, response.text

    # Omitting page retains the old full-list contract, even if size is sent.
    full = client.get("/api/v1/projects?keyword=Migration&size=1", headers=service)
    assert full.status_code == 200
    assert len(full.json()["data"]) == 5
    assert full.json()["meta"] == {"total": 5}

    projects = client.get(
        "/api/v1/projects?keyword=Migration&status=active&page=1&size=2", headers=service
    ).json()
    assert len(projects["data"]) == 2
    assert projects["meta"] == {"total": 3, "page": 1, "page_size": 2, "pages": 2}

    vendors = client.get(
        "/api/v1/vendors?keyword=Travel&tax_id=MATCH-TAX&status=active&page=2&size=2",
        headers=service,
    ).json()
    assert len(vendors["data"]) == 1
    assert vendors["meta"] == {"total": 3, "page": 2, "page_size": 2, "pages": 2}

    resources = client.get(
        "/api/v1/resources?keyword=Jade&resource_type=meeting_room&booking_mode=shared"
        "&status=active&page=1&size=2",
        headers=service,
    ).json()
    assert len(resources["data"]) == 2
    assert resources["meta"] == {"total": 3, "page": 1, "page_size": 2, "pages": 2}

    empty = client.get("/api/v1/resources?keyword=missing&page=1", headers=service).json()
    assert empty["data"] == []
    assert empty["meta"] == {"total": 0, "page": 1, "page_size": 50, "pages": 1}

    for query in ("page=0", "page=1&size=0", "page=1&size=201"):
        assert client.get(f"/api/v1/projects?{query}", headers=service).status_code == 422


def test_member_reads_master_data_but_cannot_write(client: TestClient) -> None:
    ctx = provision_tenant(client)
    rows = create_master_rows(client, ctx["service"])
    member = invite_role_user(
        client, ctx["service"], role="member", email="member@master.example"
    )["headers"]

    for collection in ("projects", "vendors", "products", "product-skus", "resources"):
        response = client.get(f"/api/v1/{collection}", headers=member)
        assert response.status_code == 200, (collection, response.text)
        assert response.json()["data"]

    create_cases = (
        ("projects", {"project_name": "Denied"}),
        ("vendors", {"name": "Denied"}),
        ("products", {"name": "Denied"}),
        ("product-skus", {"product_id": rows["products"], "sku_code": "DENIED"}),
        ("resources", {"resource_type": "meeting_room", "name": "Denied"}),
    )
    for collection, payload in create_cases:
        denied = client.post(f"/api/v1/{collection}", json=payload, headers=member)
        assert denied.status_code == 403, (collection, denied.text)
        assert denied.json()["detail"] == "requires capability master_data.manage"

    patch_payloads = {
        "projects": {"project_name": "Denied"},
        "vendors": {"name": "Denied"},
        "products": {"name": "Denied"},
        "product-skus": {"sku_code": "DENIED"},
        "resources": {"name": "Denied"},
    }
    for collection, entity_id in rows.items():
        denied = client.patch(
            f"/api/v1/{collection}/{entity_id}", json=patch_payloads[collection], headers=member
        )
        assert denied.status_code == 403, (collection, denied.text)
        assert client.delete(f"/api/v1/{collection}/{entity_id}", headers=member).status_code == 403


def test_focused_and_legacy_management_capabilities_both_allow_writes(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    catalog = client.get("/api/v1/capabilities", headers=service).json()["data"]["capabilities"]
    assert "master_data.manage" in {capability["name"] for capability in catalog}

    cases = (
        ("master_manager", ["master_data.manage"], "focused@master.example", "Focused Project"),
        ("legacy_manager", ["users.manage"], "legacy@master.example", "Legacy Project"),
    )
    for role, permissions, email, project_name in cases:
        created_role = client.post(
            "/api/v1/roles",
            json={"name": role, "permissions": permissions},
            headers=service,
        )
        assert created_role.status_code == 201, created_role.text
        actor = invite_role_user(client, service, role=role, email=email)["headers"]
        created = client.post(
            "/api/v1/projects", json={"project_name": project_name}, headers=actor
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["data"]["id"]
        assert client.patch(
            f"/api/v1/projects/{project_id}",
            json={"client": "Updated"},
            headers=actor,
        ).status_code == 200
        assert client.delete(f"/api/v1/projects/{project_id}", headers=actor).status_code == 204


def test_service_key_writes_and_tenant_isolation(client: TestClient) -> None:
    first = provision_tenant(client, "master-one")
    second = provision_tenant(client, "master-two")
    rows = create_master_rows(client, first["service"])

    # Tenant-level service credentials retain full write behavior.
    assert client.patch(
        f"/api/v1/projects/{rows['projects']}",
        json={"client": "Service Updated"},
        headers=first["service"],
    ).status_code == 200

    # Reads and writes never reveal another tenant's records.
    foreign_get = client.get(
        f"/api/v1/projects/{rows['projects']}", headers=second["service"]
    )
    assert foreign_get.status_code == 404
    foreign_list = client.get("/api/v1/projects?page=1&size=50", headers=second["service"]).json()
    assert foreign_list["data"] == []
    assert foreign_list["meta"]["total"] == 0
    foreign_patch = client.patch(
        f"/api/v1/projects/{rows['projects']}",
        json={"client": "Cross Tenant"},
        headers=second["service"],
    )
    assert foreign_patch.status_code == 404


def test_retired_legacy_master_data_writes_return_gone_without_side_effects(
    client: TestClient,
) -> None:
    ctx = provision_tenant(client)
    rows = create_master_rows(client, ctx["service"])
    before = {
        collection: client.get(
            f"/api/v1/{collection}/{entity_id}", headers=ctx["service"]
        ).json()["data"]
        for collection, entity_id in rows.items()
    }

    save_cases = (
        ("/web/projects/save", {"project_name": "Must Not Exist", "status": "active"}),
        ("/web/vendors/save", {"name": "Must Not Exist", "status": "active"}),
        ("/web/products/save", {"name": "Must Not Exist", "status": "active"}),
        (
            f"/web/products/{rows['products']}/skus/save",
            {"dimension": "size", "values": "Must Not Exist"},
        ),
        (
            "/web/resources/save",
            {"name": "Must Not Exist", "resource_type": "meeting_room", "status": "active"},
        ),
    )
    for path, form in save_cases:
        retired = client.post(path, data=form, follow_redirects=False)
        assert retired.status_code == 410, (path, retired.text)

    for collection, entity_id in rows.items():
        path = (
            f"/web/product-skus/{entity_id}/archive"
            if collection == "product-skus"
            else f"/web/{collection}/{entity_id}/archive"
        )
        retired = client.post(path, follow_redirects=False)
        assert retired.status_code == 410, (path, retired.text)

    after = {
        collection: client.get(
            f"/api/v1/{collection}/{entity_id}", headers=ctx["service"]
        ).json()["data"]
        for collection, entity_id in rows.items()
    }
    assert after == before

    for collection in ("projects", "vendors", "products", "resources"):
        rows_after = client.get(
            f"/api/v1/{collection}?keyword=Must Not Exist", headers=ctx["service"]
        ).json()["data"]
        assert rows_after == []
