from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client


TEST_TENANT = "11111111-1111-1111-1111-111111111111"
TEST_API_KEY = "test-api-key"
HEADERS = {"X-API-Key": TEST_API_KEY}

WARRANTY_SCHEMA = {
    "type": "object",
    "required": ["serial_number", "product"],
    "properties": {
        "serial_number": {"type": "string", "minLength": 3},
        "product": {"type": "string"},
        "purchase_year": {"type": "integer", "minimum": 2000},
    },
    "additionalProperties": True,
}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Test Tenant"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def create_definition(client: TestClient, **overrides) -> dict:
    payload = {"object_type": "warranty_card", "title": "Warranty Card", "json_schema": WARRANTY_SCHEMA}
    payload.update(overrides)
    response = client.post("/api/v1/object-type-definitions", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_definition_crud(client: TestClient) -> None:
    definition = create_definition(client)
    assert definition["version"] == 1
    assert definition["status"] == "active"

    # duplicate type rejected
    response = client.post(
        "/api/v1/object-type-definitions",
        json={"object_type": "warranty_card", "json_schema": {}},
        headers=HEADERS,
    )
    assert response.status_code == 409

    # schema change bumps version
    new_schema = dict(WARRANTY_SCHEMA, required=["serial_number"])
    response = client.patch(
        f"/api/v1/object-type-definitions/{definition['id']}",
        json={"json_schema": new_schema},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["data"]["version"] == 2

    # list and archive
    response = client.get("/api/v1/object-type-definitions", headers=HEADERS)
    assert response.json()["meta"]["total"] == 1
    response = client.delete(f"/api/v1/object-type-definitions/{definition['id']}", headers=HEADERS)
    assert response.status_code == 204
    response = client.get(f"/api/v1/object-type-definitions/{definition['id']}", headers=HEADERS)
    assert response.json()["data"]["status"] == "archived"


def test_invalid_json_schema_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/object-type-definitions",
        json={"object_type": "broken", "json_schema": {"type": "not-a-type"}},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "field rules are not valid" in response.json()["detail"]


def test_payload_validated_on_create_and_update(client: TestClient) -> None:
    create_definition(client)

    # conforming payload accepted
    response = client.post(
        "/api/v1/business-objects",
        json={
            "object_type": "warranty_card",
            "title": "Card A",
            "payload": {"serial_number": "SN-001", "product": "Pump X", "purchase_year": 2026},
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    object_id = response.json()["data"]["id"]

    # missing required field rejected with a pointer
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "warranty_card", "title": "Card B", "payload": {"product": "Pump X"}},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "warranty_card" in response.json()["detail"]

    # update to violating payload rejected
    response = client.patch(
        f"/api/v1/business-objects/{object_id}",
        json={"payload": {"serial_number": "SN-001", "product": "Pump X", "purchase_year": 1999}},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "purchase_year" in response.json()["detail"]

    # other object types stay free-form
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "misc_note", "title": "Note", "payload": {"anything": ["goes"]}},
        headers=HEADERS,
    )
    assert response.status_code == 201


def test_archived_definition_stops_validating(client: TestClient) -> None:
    definition = create_definition(client)
    client.delete(f"/api/v1/object-type-definitions/{definition['id']}", headers=HEADERS)
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "warranty_card", "title": "Card", "payload": {}},
        headers=HEADERS,
    )
    assert response.status_code == 201


def test_payload_match_filter(client: TestClient) -> None:
    create_definition(client)
    for serial, year in (("SN-001", 2025), ("SN-002", 2026)):
        response = client.post(
            "/api/v1/business-objects",
            json={
                "object_type": "warranty_card",
                "title": serial,
                "payload": {"serial_number": serial, "product": "Pump X", "purchase_year": year},
            },
            headers=HEADERS,
        )
        assert response.status_code == 201

    response = client.get(
        "/api/v1/business-objects",
        params={"payload_match": '{"serial_number": "SN-002"}'},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["title"] == "SN-002"

    # numeric scalar match
    response = client.get(
        "/api/v1/business-objects",
        params={"payload_match": '{"purchase_year": 2025}'},
        headers=HEADERS,
    )
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["title"] == "SN-001"

    # malformed filter rejected
    response = client.get(
        "/api/v1/business-objects",
        params={"payload_match": "not-json"},
        headers=HEADERS,
    )
    assert response.status_code == 400


def test_object_type_optional_pagination_and_keyword_contract(client: TestClient) -> None:
    create_definition(client)
    create_definition(
        client,
        object_type="inspection_note",
        title="Inspection Note",
        json_schema={},
    )

    legacy = client.get("/api/v1/object-type-definitions", headers=HEADERS).json()
    assert len(legacy["data"]) == 2
    assert legacy["meta"] == {"total": 2}

    paged = client.get(
        "/api/v1/object-type-definitions",
        params={"page": 1, "size": 1, "keyword": "inspection", "status": "active"},
        headers=HEADERS,
    ).json()
    assert paged["meta"] == {"total": 1, "page": 1, "page_size": 1, "pages": 1}
    assert paged["data"][0]["object_type"] == "inspection_note"


def test_business_object_detail_contract(client: TestClient) -> None:
    definition = create_definition(client)
    object_ids: list[str] = []
    for serial in ("SN-DETAIL-1", "SN-DETAIL-2"):
        response = client.post(
            "/api/v1/business-objects",
            json={
                "object_type": "warranty_card",
                "title": serial,
                "payload": {"serial_number": serial, "product": "Pump X"},
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        object_ids.append(response.json()["data"]["id"])

    link = client.post(
        "/api/v1/business-object-links",
        json={
            "source_object_id": object_ids[0],
            "target_object_id": object_ids[1],
            "link_type": "supersedes",
        },
        headers=HEADERS,
    )
    assert link.status_code == 201

    employee = client.post(
        "/api/v1/employees", json={"name": "Approver"}, headers=HEADERS
    ).json()["data"]
    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee["id"],
            "entity_type": "business_object",
            "entity_id": object_ids[0],
            "title": "Review warranty",
        },
        headers=HEADERS,
    )
    assert todo.status_code == 201
    approval = client.post(
        "/api/v1/approval-records",
        json={
            "entity_type": "business_object",
            "entity_id": object_ids[0],
            "action": "commented",
            "comment": "Looks good",
        },
        headers=HEADERS,
    )
    assert approval.status_code == 201
    workflow = client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "business_object",
            "object_type": "warranty_card",
            "name": "default",
            "definition_text": "steps: [review]",
        },
        headers=HEADERS,
    )
    assert workflow.status_code == 201

    detail = client.get(
        f"/api/v1/business-objects/{object_ids[0]}/detail", headers=HEADERS
    ).json()["data"]
    assert detail["business_object"]["id"] == object_ids[0]
    assert [item["id"] for item in detail["links"]] == [link.json()["data"]["id"]]
    assert [item["id"] for item in detail["todos"]] == [todo.json()["data"]["id"]]
    assert [item["id"] for item in detail["approval_records"]] == [approval.json()["data"]["id"]]
    assert detail["object_type_definition"]["id"] == definition["id"]
    assert [item["id"] for item in detail["workflow_definitions"]] == [workflow.json()["data"]["id"]]


def test_object_directory_includes_defined_and_data_only_custom_types(
    client: TestClient,
) -> None:
    create_definition(client)
    archived = create_definition(
        client,
        object_type="archived_type",
        title="Archived Type",
        json_schema={},
    )
    assert client.delete(
        f"/api/v1/object-type-definitions/{archived['id']}", headers=HEADERS
    ).status_code == 204

    for serial in ("SN-DIR-1", "SN-DIR-2"):
        assert client.post(
            "/api/v1/business-objects",
            json={
                "object_type": "warranty_card",
                "title": serial,
                "payload": {"serial_number": serial, "product": "Pump X"},
            },
            headers=HEADERS,
        ).status_code == 201
    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "legacy_note", "title": "Schema-less legacy record"},
        headers=HEADERS,
    ).status_code == 201

    response = client.get("/api/v1/object-directory", headers=HEADERS)
    assert response.status_code == 200
    payload = response.json()
    by_key = {
        (entry["entity_kind"], entry["object_type"]): entry
        for entry in payload["data"]
    }
    # Derived from the source of truth rather than restated here. Spelling the
    # list out is what let it rot: this assertion passed for four releases while
    # purchase orders, invoices, payments and billing accounts were missing from
    # the console entirely.
    from app.services.object_types import BUILTIN_OBJECT_TYPES

    assert {key for key in by_key if key[0] == "builtin"} == {
        ("builtin", object_type) for object_type in BUILTIN_OBJECT_TYPES
    }
    assert payload["meta"]["total"] == len(BUILTIN_OBJECT_TYPES) + 3
    assert by_key[("business_object", "warranty_card")] == {
        "entity_kind": "business_object",
        "object_type": "warranty_card",
        "count": 2,
        "title": "Warranty Card",
        "definition_status": "active",
    }
    assert by_key[("business_object", "legacy_note")] == {
        "entity_kind": "business_object",
        "object_type": "legacy_note",
        "count": 1,
        "title": None,
        "definition_status": None,
    }
    assert by_key[("business_object", "archived_type")]["count"] == 0
    assert by_key[("business_object", "archived_type")]["definition_status"] == "archived"


def test_the_browsable_and_workflow_lists_stay_pinned_to_their_sources() -> None:
    """These two lists drifted silently for four releases: purchase orders,
    invoices, payments and billing accounts all shipped without ever appearing
    in the object console, and a workflow definition could not be published for
    an invoice or a payment even though the flow skill instructs agents to read
    one.

    Nothing else would have noticed, so this is the thing that notices.
    """
    from app.services.object_types import BUILTIN_OBJECT_TYPES
    from app.services.provisioning import BUILTIN_DEFINITIONS
    from app.services.state_machines import BUILTIN_MACHINES

    # every family with a lifecycle is a workflow subject and gets a definition
    machine_types = set(BUILTIN_MACHINES)
    assert machine_types == {object_type for object_type, *_ in BUILTIN_DEFINITIONS}, (
        "a machine without a provisioned definition can never be a workflow subject"
    )

    # and every one of them is browsable, plus the machineless collections
    assert machine_types <= set(BUILTIN_OBJECT_TYPES), (
        f"not browsable in the object console: {sorted(machine_types - set(BUILTIN_OBJECT_TYPES))}"
    )
    assert set(BUILTIN_OBJECT_TYPES) - machine_types == {"resource_booking", "billing_account"}


def test_every_shipped_machine_passes_the_validation_tenant_edits_face() -> None:
    """The seed data every new tenant starts from, held to the rule tenants
    are held to. `ensure_valid_state_machine` runs on the EDIT path only, so
    a defect typed into a shipped default — a transition target that is not a
    state, an anchor role that no longer resolves — would sail into every
    fresh workspace and surface as a runtime 422 in whatever endpoint needed
    the anchor. That is not hypothetical: renaming `issued` once passed the
    old validation and broke the reimbursement route in production, which is
    why STATE_ROLES exists. The builtin branch of the validator checks
    exactly that resolution, so running it over the seed list makes "the
    initialization data is correct" a build-time fact instead of a claim.

    Title and description ride along: they are what the console shows an
    admin deciding which machine to edit, and an empty one ships blind.
    """
    from app.services.provisioning import BUILTIN_DEFINITIONS
    from app.services.state_machines import ensure_valid_state_machine

    for object_type, title, description, machine in BUILTIN_DEFINITIONS:
        ensure_valid_state_machine(
            machine, entity_kind="builtin", object_type=object_type
        )
        assert title and title.strip(), f"{object_type} ships without a title"
        assert description and description.strip(), f"{object_type} ships without a description"


# --- ORYH states what it ships; the agent decides ---------------------------


def test_the_server_refuses_the_exact_word_and_leaves_the_reading_to_the_agent(client: TestClient) -> None:
    """The doctrine used to let `product` through, on the argument that whether
    a company's product is our product is a reading of THEIR business. Then a
    production tenant's admin agent wrote 150,000 legacy customers, products,
    quotes and sales orders into generic objects named exactly that, beside
    empty builtin tables — judgement never fired once. So the EXACT shipped
    words are now the server's to refuse; the reading beyond them ("merchandise",
    "货品") is still the agent's, and still allowed through here."""
    for object_type in ("product", "invoice", "customer"):
        response = client.post(
            "/api/v1/object-type-definitions",
            json={"object_type": object_type, "json_schema": {}},
            headers=HEADERS,
        )
        assert response.status_code == 422, f"{object_type}: {response.text}"
    near_miss = client.post(
        "/api/v1/object-type-definitions",
        json={"object_type": "merchandise", "json_schema": {}},
        headers=HEADERS,
    )
    assert near_miss.status_code == 201, "the semantic call stays where the person is"


def test_what_the_agent_needs_to_judge_with(client: TestClient) -> None:
    """The fact has to be available, or "let the agent decide" is a way of
    deciding nothing. The object directory does not carry it: it lists the
    browsable document families, and `products` is not one of them."""
    response = client.get("/api/v1/builtin-object-types", headers=HEADERS)
    assert response.status_code == 200, response.text
    by_type = {row["object_type"]: row for row in response.json()["data"]}

    assert "products" in by_type
    assert by_type["products"]["path"] == "/products"
    # the words a person actually writes, so an agent asked for "Product" or
    # "goods" recognises the collision without inventing a synonym list
    assert "product" in by_type["products"]["also_called"]
    assert "goods" in by_type["products"]["also_called"]

    # the collections the object directory does NOT carry — which is why this
    # endpoint exists rather than a note in a skill
    directory = client.get("/api/v1/object-directory", headers=HEADERS).json()["data"]
    assert "products" not in {row["object_type"] for row in directory}


def test_the_vocabulary_is_derived_from_the_rest_surface(client: TestClient) -> None:
    """Not a written list. A collection a tenant can already GET is a thing ORYH
    ships, so a concept added next month appears the day its endpoint does —
    which is the property five separate defects in this codebase were missing.
    """
    from app.main import app
    from app.services.object_types import builtin_object_vocabulary

    paths = app.openapi()["paths"]
    entries = builtin_object_vocabulary()

    # Every word it claims points at a collection that really answers GET.
    # Asserted this way round rather than by re-deriving the set here: a test
    # that reimplements the rule it is checking agrees with it by construction
    # and catches nothing.
    for entry in entries:
        assert f"/api/v1{entry['path']}" in paths, entry
        assert "get" in paths[f"/api/v1{entry['path']}"], entry

    listed = {entry["object_type"] for entry in entries}
    assert len(listed) > 40, "too few to have come from anywhere but a list"
    for expected in ("products", "customers", "vendors", "employees", "invoices",
                     "policies", "projects"):
        assert expected in listed


def test_the_alias_list_stays_a_hint_not_a_policy() -> None:
    """These are words people reach for, not a claim to have thought of
    everything. Now that the exact words are REFUSED, a wrong entry costs a
    legitimate custom type its name, so the list stays short, and the
    ambiguous ones belong to the agent — "account" could be a customer or a
    billing account, and only the person knows which."""
    from app.services.object_types import _IRREGULAR_ALIASES, builtin_object_names

    assert len(_IRREGULAR_ALIASES) <= 8, "the alias map is growing into a policy"
    assert "account" not in builtin_object_names()


def test_a_genuine_custom_object_is_untouched(client: TestClient) -> None:
    for object_type in ("warranty_card", "contract_review", "grant_application"):
        response = client.post(
            "/api/v1/object-type-definitions",
            json={"object_type": object_type, "json_schema": {}},
            headers=HEADERS,
        )
        assert response.status_code == 201, f"{object_type}: {response.text}"


def test_a_deleted_legacy_dump_leaves_the_directory(client: TestClient) -> None:
    """A workspace that once dumped its legacy customers into generic rows
    and then archived them must not keep a ghost 'customer' type in the
    directory with a five-digit count: live rows only, and a type with no
    live rows and no definition is gone."""
    made = [
        client.post("/api/v1/business-objects",
                    json={"object_type": "legacy_customer", "title": f"客户 {n}"},
                    headers=HEADERS).json()["data"]["id"]
        for n in range(3)
    ]
    keys = lambda: {  # noqa: E731
        (e["entity_kind"], e["object_type"]): e["count"]
        for e in client.get("/api/v1/object-directory", headers=HEADERS).json()["data"]
    }
    assert keys()[("business_object", "legacy_customer")] == 3
    for object_id in made[:2]:
        assert client.delete(f"/api/v1/business-objects/{object_id}", headers=HEADERS).status_code == 204
    assert keys()[("business_object", "legacy_customer")] == 1, "the directory counts live rows"
    assert client.delete(f"/api/v1/business-objects/{made[2]}", headers=HEADERS).status_code == 204
    assert ("business_object", "legacy_customer") not in keys(), \
        "no live rows and no definition — the type is gone from the directory"


def test_a_generic_object_may_not_shadow_a_shipped_collection(client: TestClient) -> None:
    """The exact names ORYH ships — the collection, its singular, its listed
    synonyms — are refused as generic-object names, for rows and for type
    definitions alike, and the refusal names the real route. Anything else
    stays free: the judgement beyond exact words is the agent's."""
    for shadow, real in (("customer", "/customers"), ("product", "/products"),
                         ("quote", "/sales-quotations"), ("sales_order", "/sales-orders"),
                         ("supplier", "/vendors"), ("Client", "/customers")):
        refused = client.post("/api/v1/business-objects", headers=HEADERS,
                              json={"object_type": shadow, "title": "legacy row"})
        assert refused.status_code == 422, (shadow, refused.text)
        assert real in refused.json()["detail"] and "bulk" in refused.json()["detail"]
    definition = client.post("/api/v1/object-type-definitions", headers=HEADERS, json={
        "entity_kind": "business_object", "object_type": "product", "title": "Product",
        "json_schema": {"type": "object"}})
    assert definition.status_code == 422 and "/products" in definition.json()["detail"]
    allowed = client.post("/api/v1/business-objects", headers=HEADERS,
                          json={"object_type": "product_recall", "title": "召回 2026-09"})
    assert allowed.status_code == 201, "a name that is not a shipped word stays free"


def test_a_record_cannot_change_type_to_borrow_another_types_write_grant(client: TestClient) -> None:
    """Review R07: `business_object.write:review_allowed` could not edit a
    `review_record` — until the PATCH also changed its object_type, after
    which the same person edited it under the type they may write. A record's
    type is its identity now: changing it is refused, for anyone."""
    from conftest import invite_member, provision_tenant

    t = provision_tenant(client, company_name="Retype Co", email="admin@retype.example")
    admin = {"X-API-Key": t["plain_text_api_key"]}
    scoped = invite_member(client, admin, "reviewer", ["business_object.write:review_allowed"])
    record = client.post("/api/v1/business-objects", headers=admin,
                         json={"object_type": "review_record", "title": "评审记录"}).json()["data"]
    assert client.patch(f"/api/v1/business-objects/{record['id']}", headers=scoped,
                        json={"title": "改标题"}).status_code == 403
    retyped = client.patch(f"/api/v1/business-objects/{record['id']}", headers=scoped,
                           json={"object_type": "review_allowed", "title": "改标题"})
    assert retyped.status_code in (403, 422), retyped.text
    as_admin = client.patch(f"/api/v1/business-objects/{record['id']}", headers=admin,
                            json={"object_type": "review_allowed"})
    assert as_admin.status_code == 422 and "identity" in as_admin.json()["detail"], "not even an admin re-types a record"
    still = client.get(f"/api/v1/business-objects/{record['id']}", headers=admin).json()["data"]
    assert still["object_type"] == "review_record" and still["title"] == "评审记录"
