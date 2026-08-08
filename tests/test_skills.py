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
HEADERS = {"X-API-Key": TEST_API_KEY}
OTHER_HEADERS = {"X-API-Key": OTHER_API_KEY}

SKILL_FILES = {
    "SKILL.md": "---\nname: jc-warranty-card-apply\ndescription: capture warranty cards\n---\n\n# Apply\n",
    "references/api.md": "# API\n",
    "agents/openai.yaml": "model: gpt\n",
}


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


def create_skill(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "jc-warranty-card-apply",
        "title": "JC Warranty Card Apply",
        "description": "capture warranty cards",
        "files": SKILL_FILES,
    }
    payload.update(overrides)
    response = client.post("/api/v1/skills", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_skill_crud_and_versioning(client: TestClient) -> None:
    skill = create_skill(client)
    assert skill["version"] == 1
    assert set(skill["files"]) == set(SKILL_FILES)

    # duplicate name rejected
    response = client.post(
        "/api/v1/skills",
        json={"name": "jc-warranty-card-apply", "files": SKILL_FILES},
        headers=HEADERS,
    )
    assert response.status_code == 409

    # lookup by name and by id both work
    assert client.get("/api/v1/skills/jc-warranty-card-apply", headers=HEADERS).status_code == 200
    assert client.get(f"/api/v1/skills/{skill['id']}", headers=HEADERS).status_code == 200

    # file content served as plain text
    response = client.get("/api/v1/skills/jc-warranty-card-apply/files/references/api.md", headers=HEADERS)
    assert response.status_code == 200
    assert response.text == "# API\n"

    # changing files bumps version; metadata-only change does not
    new_files = dict(SKILL_FILES, **{"references/api.md": "# API v2\n"})
    response = client.patch(
        "/api/v1/skills/jc-warranty-card-apply", json={"files": new_files}, headers=HEADERS
    )
    assert response.json()["data"]["version"] == 2
    response = client.patch(
        "/api/v1/skills/jc-warranty-card-apply", json={"title": "Renamed"}, headers=HEADERS
    )
    assert response.json()["data"]["version"] == 2

    # archive hides from the default agent index
    assert client.delete("/api/v1/skills/jc-warranty-card-apply", headers=HEADERS).status_code == 204
    assert client.get("/api/v1/skills", headers=HEADERS).json()["meta"]["total"] == 0
    assert client.get("/api/v1/skills?status=all", headers=HEADERS).json()["meta"]["total"] == 1


def test_skill_validation(client: TestClient) -> None:
    # SKILL.md required
    response = client.post(
        "/api/v1/skills",
        json={"name": "broken", "files": {"README.md": "x"}},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "SKILL.md" in response.json()["detail"]

    # path traversal rejected
    response = client.post(
        "/api/v1/skills",
        json={"name": "broken", "files": {"SKILL.md": "x", "../evil": "x"}},
        headers=HEADERS,
    )
    assert response.status_code == 422

    # name must be kebab-case
    response = client.post(
        "/api/v1/skills",
        json={"name": "Not Valid!", "files": {"SKILL.md": "x"}},
        headers=HEADERS,
    )
    assert response.status_code == 422

    # required_capability follows the same grammar as a role's permission
    # grants: unknown string, or a scope on a non-scopable verb, both 422
    response = client.post(
        "/api/v1/skills",
        json={
            "name": "unknown-cap",
            "required_capability": "no.such.capability",
            "files": {"SKILL.md": "x"},
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/skills",
        json={
            "name": "bad-scope",
            "required_capability": "approval.record:daily_report",
            "files": {"SKILL.md": "x"},
        },
        headers=HEADERS,
    )
    assert response.status_code == 422

    # a scoped system verb on a scopable capability is valid
    response = client.post(
        "/api/v1/skills",
        json={
            "name": "daily-report-submit",
            "required_capability": "business_object.write:daily_report",
            "files": {"SKILL.md": "x"},
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text


def test_skill_tenant_isolation(client: TestClient) -> None:
    create_skill(client)
    # other tenant sees nothing and cannot fetch by name
    assert client.get("/api/v1/skills", headers=OTHER_HEADERS).json()["meta"]["total"] == 0
    assert client.get("/api/v1/skills/jc-warranty-card-apply", headers=OTHER_HEADERS).status_code == 404
    # same name can exist independently in the other tenant
    response = client.post(
        "/api/v1/skills",
        json={"name": "jc-warranty-card-apply", "files": {"SKILL.md": "different tenant\n"}},
        headers=OTHER_HEADERS,
    )
    assert response.status_code == 201


def test_skill_index_is_summary_only(client: TestClient) -> None:
    create_skill(client)
    entry = client.get("/api/v1/skills", headers=HEADERS).json()["data"][0]
    assert "files" not in entry
    assert entry["description"] == "capture warranty cards"


def test_skill_optional_pagination_and_keyword_contract(client: TestClient) -> None:
    create_skill(client)
    create_skill(
        client,
        name="expense-helper",
        title="Expense Helper",
        description="prepare expense claims",
    )

    legacy = client.get("/api/v1/skills", headers=HEADERS).json()
    assert len(legacy["data"]) == 2
    assert legacy["meta"] == {"total": 2}

    paged = client.get(
        "/api/v1/skills",
        params={"page": 1, "size": 1, "keyword": "expense", "status": "active"},
        headers=HEADERS,
    ).json()
    assert paged["meta"] == {"total": 1, "page": 1, "page_size": 1, "pages": 1}
    assert paged["data"][0]["name"] == "expense-helper"
    assert "files" not in paged["data"][0]
