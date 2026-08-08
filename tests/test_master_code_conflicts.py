"""A duplicate master-data code is a 409 that names its holder, never a 500.

A live E2E run hit this with a project: `projects_tenant_project_code_uk` has
enforced per-tenant codes on postgres since the baseline migration, but the
model never declared the index — so the sqlite test schema was built without
it and every test stayed green — and no create or update caught
IntegrityError, so re-using an ARCHIVED project's code surfaced to the person
as Internal Server Error.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import provision_tenant as bootstrap_tenant


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Code Co", email="admin@code-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def test_duplicate_project_code_is_409_even_against_an_archived_twin(client: TestClient) -> None:
    headers = provision(client)
    first = client.post(
        "/api/v1/projects",
        json={"project_code": "PW-E2E-0-0", "project_name": "第一期"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    project_id = first.json()["data"]["id"]

    # live twin: refused with the holder named
    duplicate = client.post(
        "/api/v1/projects",
        json={"project_code": "PW-E2E-0-0", "project_name": "撞码"},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text
    assert project_id in duplicate.json()["detail"]

    # that case exactly: the holder is ARCHIVED, so it is invisible in the
    # default list view — "already exists" alone would read as a lie. The
    # message says the twin is archived and keeps its code.
    archived = client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert archived.status_code == 204, archived.text
    again = client.post(
        "/api/v1/projects",
        json={"project_code": "PW-E2E-0-0", "project_name": "归档后再建"},
        headers=headers,
    )
    assert again.status_code == 409, again.text
    detail = again.json()["detail"]
    assert "archived" in detail and project_id in detail

    # a different code sails through
    ok = client.post(
        "/api/v1/projects",
        json={"project_code": "PW-E2E-0-1", "project_name": "换码"},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text


def test_updating_into_a_taken_code_is_409(client: TestClient) -> None:
    headers = provision(client)
    client.post(
        "/api/v1/projects",
        json={"project_code": "P-A", "project_name": "甲"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/projects",
        json={"project_code": "P-B", "project_name": "乙"},
        headers=headers,
    ).json()["data"]

    collided = client.patch(
        f"/api/v1/projects/{second['id']}",
        json={"project_code": "P-A"},
        headers=headers,
    )
    assert collided.status_code == 409, collided.text
    assert "P-A" in collided.json()["detail"]


def test_every_coded_master_family_refuses_duplicates_the_same_way(client: TestClient) -> None:
    """Vendors, customers and products carry the same latent 500 — their
    partial unique indexes were declared but nothing caught the violation."""
    headers = provision(client)
    for path, body in (
        ("/api/v1/vendors", {"vendor_code": "V-01", "name": "供应商"}),
        ("/api/v1/customers", {"customer_code": "C-01", "name": "客户"}),
        ("/api/v1/products", {"product_code": "P-01", "name": "产品"}),
    ):
        first = client.post(path, json=body, headers=headers)
        assert first.status_code == 201, f"{path}: {first.text}"
        duplicate = client.post(path, json=body, headers=headers)
        assert duplicate.status_code == 409, f"{path}: {duplicate.status_code} {duplicate.text}"
        # vendors/customers/products carry an older pre-check with its own
        # wording; the contract asserted here is the status and the code —
        # the IntegrityError path (races, updates) now backs all of them
        code = next(v for k, v in body.items() if k.endswith("_code"))
        assert code in duplicate.json()["detail"]
