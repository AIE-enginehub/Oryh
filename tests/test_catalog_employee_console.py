from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.browser_auth import SESSION_COOKIE
from app.main import app

from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    """Invitation emails still carry a token; only the tenant's own creation
    stopped going through the mailbox."""
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token in email body: {body!r}")


def provision_tenant(client: TestClient, slug: str = "catalog") -> dict:
    data = bootstrap_tenant(
        client,
        company_name=f"{slug.title()} Co",
        email=f"admin@{slug}.example",
        password="admin-pass1",
    )
    return {
        "tenant_id": data["tenant"]["id"],
        "service": {"X-API-Key": data["plain_text_api_key"]},
        "session_token": data["session_token"],
    }


def role_user(
    client: TestClient,
    service: dict[str, str],
    *,
    role: str,
    permissions: list[str] | None,
    email: str,
) -> dict[str, str]:
    if permissions is not None:
        response = client.post(
            "/api/v1/roles",
            json={"name": role, "permissions": permissions},
            headers=service,
        )
        assert response.status_code == 201, response.text
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "role": role},
        headers=service,
    )
    assert invited.status_code == 201, invited.text
    user_id = invited.json()["data"]["id"]
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": extract_token(outbox.messages[-1].body), "password": "invitee-pass1"},
    )
    assert accepted.status_code == 200, accepted.text
    key = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": role, "user_id": user_id},
        headers=service,
    )
    assert key.status_code == 201, key.text
    return {"X-API-Key": key.json()["data"]["plain_text_api_key"]}


def create_product(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    payload = {"name": "Catalog Product"}
    payload.update(overrides)
    # product_code is unique per tenant, so a single hardcoded default would
    # collide between two fixtures in the same tenant. Derive it from the name
    # instead; callers that care still pass their own.
    payload.setdefault("product_code", "CAT-" + payload["name"].replace(" ", "-").upper())
    response = client.post("/api/v1/products", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_sku(
    client: TestClient,
    headers: dict[str, str],
    product_id: str,
    **overrides,
) -> dict:
    payload = {"product_id": product_id, "sku_code": "CAT-SKU", "variant_attrs": {"size": "M"}}
    payload.update(overrides)
    response = client.post("/api/v1/product-skus", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_employee(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    payload = {"name": "Console Employee"}
    payload.update(overrides)
    response = client.post("/api/v1/employees", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_product_pagination_filters_sku_counts_and_query_shape(
    stack: tuple[TestClient, Engine],
) -> None:
    client, engine = stack
    service = provision_tenant(client)["service"]
    products = [
        create_product(
            client,
            service,
            name=f"Summer Catalog {index}",
            product_code=f"SUM-{index}",
            status="active" if index < 3 else "archived",
        )
        for index in range(4)
    ]
    create_sku(client, service, products[0]["id"], sku_code="SUM-0-A")
    create_sku(
        client,
        service,
        products[0]["id"],
        sku_code="SUM-0-B",
        variant_attrs={"size": "L"},
        status="archived",
    )
    create_sku(client, service, products[1]["id"], sku_code="SUM-1-A")
    create_sku(client, service, products[2]["id"], sku_code="SUM-2-OLD", status="archived")

    sku_queries: list[str] = []

    def capture_sku_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "from product_skus" in statement.lower():
            sku_queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sku_queries)
    try:
        response = client.get(
            "/api/v1/products?keyword=Summer&status=active&page=1&size=2",
            headers=service,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sku_queries)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"total": 3, "page": 1, "page_size": 2, "pages": 2}
    assert len(body["data"]) == 2
    # One grouped query for every product on the page; never one query per row.
    assert len(sku_queries) == 1
    expected_counts = {products[0]["id"]: 2, products[1]["id"]: 1, products[2]["id"]: 1}
    for row in body["data"]:
        assert row["sku_count"] == expected_counts[row["id"]]
        assert row["has_skus"] is (row["id"] != products[2]["id"])

    second = client.get(
        "/api/v1/products?keyword=Summer&status=active&page=2&size=2",
        headers=service,
    ).json()
    assert len(second["data"]) == 1
    assert second["meta"] == {"total": 3, "page": 2, "page_size": 2, "pages": 2}
    assert {row["id"] for row in body["data"] + second["data"]} == {
        product["id"] for product in products[:3]
    }

    # Archived SKUs remain part of sku_count, matching the pre-pagination catalog semantics.
    updated = client.patch(
        f"/api/v1/products/{products[0]['id']}",
        json={"spec": "updated"},
        headers=service,
    ).json()["data"]
    assert updated["sku_count"] == 2
    assert updated["has_skus"] is True
    archived_only = client.get(
        f"/api/v1/products/{products[2]['id']}", headers=service
    ).json()["data"]
    assert archived_only["sku_count"] == 1
    assert archived_only["has_skus"] is False

    full = client.get("/api/v1/products?keyword=Summer&size=1", headers=service).json()
    assert len(full["data"]) == 4
    assert full["meta"] == {"total": 4}

    empty = client.get("/api/v1/products?keyword=missing&page=1", headers=service).json()
    assert empty["data"] == []
    assert empty["meta"] == {"total": 0, "page": 1, "page_size": 50, "pages": 1}


def test_product_sku_pagination_counts_after_all_filters(stack: tuple[TestClient, Engine]) -> None:
    client, _ = stack
    service = provision_tenant(client)["service"]
    first = create_product(client, service, name="First Style", product_code="FIRST")
    second = create_product(client, service, name="Second Style", product_code="SECOND")
    first_skus = [
        create_sku(
            client,
            service,
            first["id"],
            sku_code=f"FIRST-{index}",
            status="active" if index < 3 else "archived",
            variant_attrs={"size": str(index)},
        )
        for index in range(5)
    ]
    create_sku(client, service, second["id"], sku_code="SECOND-0")

    first_page = client.get(
        f"/api/v1/product-skus?product_id={first['id']}&status=active&page=1&size=2",
        headers=service,
    ).json()
    assert first_page["meta"] == {"total": 3, "page": 1, "page_size": 2, "pages": 2}
    assert len(first_page["data"]) == 2
    assert all(row["product_id"] == first["id"] and row["status"] == "active" for row in first_page["data"])

    second_page = client.get(
        f"/api/v1/product-skus?product_id={first['id']}&status=active&page=2&size=2",
        headers=service,
    ).json()
    assert len(second_page["data"]) == 1
    assert {row["id"] for row in first_page["data"] + second_page["data"]} == {
        sku["id"] for sku in first_skus[:3]
    }

    exact = client.get(
        f"/api/v1/product-skus?product_id={first['id']}&sku_code=FIRST-2&page=1&size=1",
        headers=service,
    ).json()
    assert [row["sku_code"] for row in exact["data"]] == ["FIRST-2"]
    assert exact["meta"] == {"total": 1, "page": 1, "page_size": 1, "pages": 1}

    full = client.get(
        f"/api/v1/product-skus?product_id={first['id']}&size=1", headers=service
    ).json()
    assert len(full["data"]) == 5
    assert full["meta"] == {"total": 5}

    for query in ("page=0", "page=1&size=0", "page=1&size=201"):
        assert client.get(f"/api/v1/product-skus?{query}", headers=service).status_code == 422

    assert client.delete(f"/api/v1/products/{second['id']}", headers=service).status_code == 204
    denied = client.post(
        "/api/v1/product-skus",
        json={"product_id": second["id"], "sku_code": "SECOND-LATE"},
        headers=service,
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "cannot create SKU for an archived product"
    batch_denied = client.post(
        f"/api/v1/products/{second['id']}/skus/batch",
        json={"dimension": "size", "values": ["late"]},
        headers=service,
    )
    assert batch_denied.status_code == 409
    assert batch_denied.json()["detail"] == "cannot create SKU for an archived product"


def test_batch_product_skus_are_ordered_idempotent_and_validated(
    stack: tuple[TestClient, Engine],
) -> None:
    client, _ = stack
    service = provision_tenant(client, "batch-skus")["service"]
    product = create_product(
        client,
        service,
        name="Batch Style",
        product_code="STYLE",
    )
    create_sku(
        client,
        service,
        product["id"],
        sku_code="STYLE-M-OLD",
        variant_attrs={"size": "M", "fit": "regular"},
        status="archived",
    )

    response = client.post(
        f"/api/v1/products/{product['id']}/skus/batch",
        json={
            "dimension": " size ",
            "values": [" M ", "L", "M", "XL", " L "],
            "list_price": 88.5,
        },
        headers=service,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    # The archived multi-dimensional SKU does not reserve the distinct
    # one-dimensional {size: M} combination.
    assert data["skipped"] == []
    assert [row["variant_attrs"] for row in data["created"]] == [
        {"size": "M"},
        {"size": "L"},
        {"size": "XL"},
    ]
    assert [row["sku_code"] for row in data["created"]] == [
        "STYLE-M",
        "STYLE-L",
        "STYLE-XL",
    ]
    assert [row["list_price"] for row in data["created"]] == [88.5, 88.5, 88.5]

    persisted = client.get(
        f"/api/v1/product-skus?product_id={product['id']}", headers=service
    ).json()["data"]
    persisted_by_id = {row["id"]: row for row in persisted}
    assert [persisted_by_id[row["id"]]["list_price"] for row in data["created"]] == [
        row["list_price"] for row in data["created"]
    ]

    # Archived exact combinations remain reserved, preventing a second active
    # SKU from being created with the same non-empty identity.
    assert client.delete(
        f"/api/v1/product-skus/{data['created'][0]['id']}", headers=service
    ).status_code == 204
    duplicate = client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "variant_attrs": {"size": "M"}},
        headers=service,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == (
        "SKU with identical variant attributes already exists for this product"
    )

    retry = client.post(
        f"/api/v1/products/{product['id']}/skus/batch",
        json={"dimension": "size", "values": ["XL", "M", "L"]},
        headers=service,
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["data"] == {"created": [], "skipped": ["XL", "M", "L"]}

    update_duplicate = client.patch(
        f"/api/v1/product-skus/{data['created'][1]['id']}",
        json={"variant_attrs": {"size": "XL"}},
        headers=service,
    )
    assert update_duplicate.status_code == 409
    assert update_duplicate.json()["detail"] == (
        "SKU with identical variant attributes already exists for this product"
    )

    # Empty variant attributes carry no combination identity, so code-only
    # catalogs may continue to contain more than one such SKU.
    for sku_code in ("EMPTY-A", "EMPTY-B"):
        empty = client.post(
            "/api/v1/product-skus",
            json={
                "product_id": product["id"],
                "sku_code": sku_code,
                "variant_attrs": {},
            },
            headers=service,
        )
        assert empty.status_code == 201, empty.text

    rows = client.get(
        f"/api/v1/product-skus?product_id={product['id']}", headers=service
    ).json()["data"]
    attrs = [row["variant_attrs"] for row in rows]
    assert {"size": "M", "fit": "regular"} in attrs
    assert {"size": "M"} in attrs
    assert {"size": "L"} in attrs
    assert {"size": "XL"} in attrs

    invalid_payloads = (
        {"dimension": " ", "values": ["M"]},
        {"dimension": "size", "values": []},
        {"dimension": "size", "values": ["M", " "]},
        {"dimension": "size", "values": ["M"], "list_price": -1},
        {"dimension": "size", "values": ["M"], "list_price": 1.239},
        {"dimension": "size", "values": [str(index) for index in range(201)]},
    )
    for payload in invalid_payloads:
        invalid = client.post(
            f"/api/v1/products/{product['id']}/skus/batch",
            json=payload,
            headers=service,
        )
        assert invalid.status_code == 422, (payload, invalid.text)


def test_sku_variant_identity_preserves_json_value_types(
    stack: tuple[TestClient, Engine],
) -> None:
    client, _ = stack
    service = provision_tenant(client, "sku-json-types")["service"]
    product = create_product(client, service, name="Typed Variants")

    boolean = client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "variant_attrs": {"flag": True}},
        headers=service,
    )
    assert boolean.status_code == 201, boolean.text

    numeric = client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "variant_attrs": {"flag": 1}},
        headers=service,
    )
    assert numeric.status_code == 201, numeric.text

    equivalent_numeric = client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "variant_attrs": {"flag": 1.0}},
        headers=service,
    )
    assert equivalent_numeric.status_code == 409

    duplicate_boolean = client.patch(
        f"/api/v1/product-skus/{numeric.json()['data']['id']}",
        json={"variant_attrs": {"flag": True}},
        headers=service,
    )
    assert duplicate_boolean.status_code == 409


def test_sku_identity_writes_share_the_product_parent_lock(
    stack: tuple[TestClient, Engine], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import routes as routes_api

    client, _ = stack
    ctx = provision_tenant(client, "sku-locks")
    service = ctx["service"]
    product = create_product(client, service, name="Locked Style", product_code="LOCK")

    calls: list[tuple[str, str]] = []
    original = routes_api.get_locked_product_or_404

    def track_lock(db: Session, tenant_id: str, product_id: str):
        calls.append((tenant_id, product_id))
        return original(db, tenant_id, product_id)

    monkeypatch.setattr(routes_api, "get_locked_product_or_404", track_lock)

    batch = client.post(
        f"/api/v1/products/{product['id']}/skus/batch",
        json={"dimension": "size", "values": ["M"]},
        headers=service,
    )
    assert batch.status_code == 201, batch.text
    single = client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "variant_attrs": {"size": "L"}},
        headers=service,
    )
    assert single.status_code == 201, single.text
    sku_id = single.json()["data"]["id"]
    changed_identity = client.patch(
        f"/api/v1/product-skus/{sku_id}",
        json={"variant_attrs": {"size": "XL"}},
        headers=service,
    )
    assert changed_identity.status_code == 200, changed_identity.text
    changed_label_only = client.patch(
        f"/api/v1/product-skus/{sku_id}",
        json={"sku_code": "LOCK-XL"},
        headers=service,
    )
    assert changed_label_only.status_code == 200, changed_label_only.text

    assert calls == [(ctx["tenant_id"], product["id"])] * 3


def test_employee_pagination_permissions_and_no_delete(stack: tuple[TestClient, Engine]) -> None:
    client, _ = stack
    ctx = provision_tenant(client)
    service = ctx["service"]
    employees = [
        create_employee(
            client,
            service,
            name=f"Console Employee {index}",
            employee_code=f"E-{index}",
            status="active" if index < 3 else "inactive",
        )
        for index in range(5)
    ]

    full = client.get("/api/v1/employees?keyword=Console&size=1", headers=service).json()
    assert len(full["data"]) == 5
    assert full["meta"] == {"total": 5}

    page = client.get(
        "/api/v1/employees?keyword=Console&status=active&page=1&size=2", headers=service
    ).json()
    assert len(page["data"]) == 2
    assert page["meta"] == {"total": 3, "page": 1, "page_size": 2, "pages": 2}

    member = role_user(
        client,
        service,
        role="member",
        permissions=None,
        email="employee-reader@catalog.example",
    )
    assert client.get("/api/v1/employees?page=1", headers=member).status_code == 200
    denied = client.post("/api/v1/employees", json={"name": "Denied"}, headers=member)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "requires capability employees.manage"
    assert client.patch(
        f"/api/v1/employees/{employees[0]['id']}", json={"name": "Denied"}, headers=member
    ).status_code == 403

    manager = role_user(
        client,
        service,
        role="employee_manager",
        permissions=["employees.manage"],
        email="employee-manager@catalog.example",
    )
    managed = create_employee(client, manager, name="Managed Employee")
    changed = client.patch(
        f"/api/v1/employees/{managed['id']}",
        json={"status": "inactive"},
        headers=manager,
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["status"] == "inactive"
    assert client.delete(f"/api/v1/employees/{managed['id']}", headers=service).status_code == 405


def test_catalog_permissions_reads_and_tenant_isolation(stack: tuple[TestClient, Engine]) -> None:
    client, _ = stack
    first = provision_tenant(client, "catalog-one")
    second = provision_tenant(client, "catalog-two")
    product = create_product(client, first["service"], name="Private Product")
    sku = create_sku(client, first["service"], product["id"], sku_code="PRIVATE-SKU")
    employee = create_employee(client, first["service"], name="Private Employee")

    member = role_user(
        client,
        first["service"],
        role="member",
        permissions=None,
        email="catalog-reader@catalog-one.example",
    )
    for path in (
        "/api/v1/products?page=1",
        f"/api/v1/products/{product['id']}",
        "/api/v1/product-skus?page=1",
        f"/api/v1/product-skus/{sku['id']}",
    ):
        assert client.get(path, headers=member).status_code == 200, path
    assert client.post("/api/v1/products", json={"name": "Denied"}, headers=member).status_code == 403
    assert client.post(
        "/api/v1/product-skus",
        json={"product_id": product["id"], "sku_code": "DENIED"},
        headers=member,
    ).status_code == 403
    assert client.post(
        f"/api/v1/products/{product['id']}/skus/batch",
        json={"dimension": "size", "values": ["L"]},
        headers=member,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/products/{product['id']}", json={"name": "Denied"}, headers=member
    ).status_code == 403
    assert client.delete(f"/api/v1/product-skus/{sku['id']}", headers=member).status_code == 403

    manager = role_user(
        client,
        first["service"],
        role="catalog_manager",
        permissions=["master_data.manage"],
        email="catalog-manager@catalog-one.example",
    )
    managed_product = create_product(client, manager, name="Managed Product")
    create_sku(client, manager, managed_product["id"], sku_code="MANAGED-SKU")
    assert client.post(
        f"/api/v1/products/{managed_product['id']}/skus/batch",
        json={"dimension": "size", "values": ["L"]},
        headers=manager,
    ).status_code == 201

    legacy = role_user(
        client,
        first["service"],
        role="legacy_catalog_manager",
        permissions=["users.manage"],
        email="legacy-manager@catalog-one.example",
    )
    assert client.post("/api/v1/products", json={"name": "Legacy Product"}, headers=legacy).status_code == 201

    for path in (
        f"/api/v1/products/{product['id']}",
        f"/api/v1/product-skus/{sku['id']}",
        f"/api/v1/employees/{employee['id']}",
    ):
        assert client.get(path, headers=second["service"]).status_code == 404
    assert client.get(
        f"/api/v1/product-skus?product_id={product['id']}&page=1", headers=second["service"]
    ).json()["meta"]["total"] == 0
    assert client.post(
        f"/api/v1/products/{product['id']}/skus/batch",
        json={"dimension": "size", "values": ["L"]},
        headers=second["service"],
    ).status_code == 404
    assert client.get("/api/v1/employees?page=1", headers=second["service"]).json()["data"] == []


def test_retired_legacy_catalog_handlers_redirect_or_return_gone_without_writes(
    stack: tuple[TestClient, Engine],
) -> None:
    client, _ = stack
    ctx = provision_tenant(client, "legacy-console")
    client.cookies.set(SESSION_COOKIE, ctx["session_token"])

    writes = (
        (
            "/web/products/save",
            {"name": "Web Product", "product_code": "WEB-1", "status": "active"},
        ),
        (
            "/web/products/product-id/skus/save",
            {"dimension": "size", "values": "M XL"},
        ),
        (
            "/web/employees/create",
            {"name": "Web Employee", "employee_code": "WEB-E1"},
        ),
    )
    for path, form in writes:
        response = client.post(path, data=form, follow_redirects=False)
        assert response.status_code == 410, (path, response.text)

    assert client.get(
        "/api/v1/products?keyword=Web Product", headers=ctx["service"]
    ).json()["data"] == []
    assert client.get(
        "/api/v1/employees?keyword=Web Employee", headers=ctx["service"]
    ).json()["data"] == []

    for path, successor in (
        ("/web/products", "/console/products"),
        ("/web/employees", "/console/employees"),
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == successor


def test_phase_three_openapi_uses_typed_envelopes(stack: tuple[TestClient, Engine]) -> None:
    _client, _ = stack
    schema = app.openapi()
    expected = {
        "/api/v1/products": "ListEnvelope_ProductRead_",
        "/api/v1/product-skus": "ListEnvelope_ProductSkuRead_",
        "/api/v1/employees": "ListEnvelope_EmployeeRead_",
    }
    for path, model in expected.items():
        response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{model}"}

    batch_response = schema["paths"]["/api/v1/products/{product_id}/skus/batch"]["post"][
        "responses"
    ]["201"]["content"]["application/json"]["schema"]
    assert batch_response == {"$ref": "#/components/schemas/Envelope_BatchCreateProductSkusRead_"}
