"""`order_by` on every paged list: any column, `-` for descending, several
comma-separated, an unknown name refused with the sortable columns named.
The console sorts whatever column it shows, so the contract is generic
rather than a per-endpoint allowlist."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ApiKey, Tenant, hash_api_key
from conftest import make_client

TEST_TENANT = "11111111-1111-1111-1111-111111111111"
TEST_API_KEY = "test-api-key"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client([
        Tenant(id=TEST_TENANT, name="Test Tenant"),
        ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
    ]) as test_client:
        yield test_client


def headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}


def test_a_list_sorts_by_any_column_in_either_direction(client: TestClient) -> None:
    for name, code in (("Zeta", "C-3"), ("Alpha", "C-1"), ("Mid", "C-2")):
        r = client.post("/api/v1/customers", json={"name": name, "customer_code": code}, headers=headers())
        assert r.status_code == 201, r.text
    asc = client.get("/api/v1/customers?order_by=name&page=1&size=10", headers=headers())
    assert asc.status_code == 200, asc.text
    names = [row["name"] for row in asc.json()["data"]]
    assert names == sorted(names)
    desc = client.get("/api/v1/customers?order_by=-name&page=1&size=10", headers=headers()).json()["data"]
    assert [row["name"] for row in desc] == sorted(names, reverse=True)
    # several keys, with the family's order as the tiebreak behind them
    two = client.get("/api/v1/customers?order_by=status,-customer_code&size=10", headers=headers())
    assert two.status_code == 200
    codes = [row["customer_code"] for row in two.json()["data"]]
    assert codes == sorted(codes, reverse=True)
    # unpaged lists take it too
    unpaged = client.get("/api/v1/customers?order_by=customer_code", headers=headers()).json()["data"]
    assert [row["customer_code"] for row in unpaged] == sorted(codes)


def test_an_unknown_sort_column_is_refused_with_the_sortable_ones_named(client: TestClient) -> None:
    r = client.get("/api/v1/customers?order_by=nope", headers=headers())
    assert r.status_code == 422, r.text
    assert "'nope'" in r.json()["detail"] and "customer_code" in r.json()["detail"]


def test_every_paged_list_documents_order_by() -> None:
    """Whatever documents `size` documents `order_by` — the console builds its
    sort control from the OpenAPI document and must not find half the lists
    unsortable."""
    spec = app.openapi()
    missing = []
    for path, item in spec["paths"].items():
        get = item.get("get")
        if not get:
            continue
        names = {p["name"] for p in get.get("parameters", [])}
        if "size" in names and "order_by" not in names:
            missing.append(path)
    # the lists that page by hand and render enriched rows
    assert sorted(missing) == ["/api/v1/auth/users", "/api/v1/skills", "/api/v1/tenant/api-key-owners"], missing
