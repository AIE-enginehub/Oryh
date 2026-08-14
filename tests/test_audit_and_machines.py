from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.workflows import lock_workflow_publish_scope, workflow_publish_lock_key
from app.models import ApiKey, Tenant, hash_api_key
from app.services.state_machines import DEFAULT_TIMESHEET_MACHINE

from conftest import make_client


TEST_TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
TEST_API_KEY = "test-api-key"
OTHER_API_KEY = "other-api-key"
HEADERS = {"X-API-Key": TEST_API_KEY}
OTHER_HEADERS = {"X-API-Key": OTHER_API_KEY}


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


def create_employee(client: TestClient, name: str = "Alice") -> str:
    response = client.post("/api/v1/employees", json={"name": name}, headers=HEADERS)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def create_header(client: TestClient, employee_id: str, start="2026-06-01", end="2026-06-07") -> str:
    response = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee_id, "period_start": start, "period_end": end},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


# ---------------------------------------------------------------------------
# state machines
# ---------------------------------------------------------------------------

def test_default_timesheet_machine_guards_transitions(client: TestClient) -> None:
    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)

    # draft -> approved is illegal
    response = client.patch(
        f"/api/v1/timesheet-headers/{header_id}", json={"status": "approved"}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "illegal transition" in response.json()["detail"]

    # legal path: submit, then approve
    assert client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=HEADERS).status_code == 200
    response = client.patch(
        f"/api/v1/timesheet-headers/{header_id}", json={"status": "approved"}, headers=HEADERS
    )
    assert response.status_code == 200

    # approved is terminal
    response = client.patch(
        f"/api/v1/timesheet-headers/{header_id}", json={"status": "draft"}, headers=HEADERS
    )
    assert response.status_code == 409

    # submitting an approved header is illegal too
    header2 = create_header(client, employee_id, start="2026-06-08", end="2026-06-14")
    client.post(f"/api/v1/timesheet-headers/{header2}/submit", json={}, headers=HEADERS)
    client.patch(f"/api/v1/timesheet-headers/{header2}", json={"status": "approved"}, headers=HEADERS)
    response = client.post(f"/api/v1/timesheet-headers/{header2}/submit", json={}, headers=HEADERS)
    assert response.status_code == 409


def test_tenant_custom_timesheet_machine(client: TestClient) -> None:
    # Lifecycle customization only — workflow nodes never become states.
    # This tenant forbids returning: submitted timesheets can only be
    # approved or rejected.
    machine = {
        "initial": "draft",
        "states": ["draft", "submitted", "approved", "rejected"],
        "transitions": {
            "draft": ["submitted"],
            "submitted": ["approved", "rejected"],
            "approved": [],
            "rejected": [],
        },
        "editable_states": ["draft"],
    }
    response = client.post(
        "/api/v1/object-type-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "timesheet_header",
            "title": "Timesheet without returns",
            "state_machine": machine,
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text

    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)
    client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=HEADERS)

    # returning is illegal for this tenant
    response = client.patch(
        f"/api/v1/timesheet-headers/{header_id}", json={"status": "returned"}, headers=HEADERS
    )
    assert response.status_code == 409
    assert client.patch(
        f"/api/v1/timesheet-headers/{header_id}", json={"status": "approved"}, headers=HEADERS
    ).status_code == 200

    # the other tenant still runs the default machine and may return
    other_employee = client.post("/api/v1/employees", json={"name": "Bob"}, headers=OTHER_HEADERS).json()["data"]["id"]
    other_header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": other_employee, "period_start": "2026-06-01", "period_end": "2026-06-07"},
        headers=OTHER_HEADERS,
    ).json()["data"]["id"]
    client.post(f"/api/v1/timesheet-headers/{other_header}/submit", json={}, headers=OTHER_HEADERS)
    assert client.patch(
        f"/api/v1/timesheet-headers/{other_header}", json={"status": "returned"}, headers=OTHER_HEADERS
    ).status_code == 200


def test_builtin_machine_requires_anchors(client: TestClient) -> None:
    response = client.post(
        "/api/v1/object-type-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "timesheet_header",
            "state_machine": {
                "initial": "open",
                "states": ["open", "done"],
                "transitions": {"open": ["done"], "done": []},
            },
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "anchor" in response.json()["detail"] or "must start" in response.json()["detail"]

    # builtin definitions must carry a machine
    response = client.post(
        "/api/v1/object-type-definitions",
        json={"entity_kind": "builtin", "object_type": "timesheet_header"},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_business_object_state_machine(client: TestClient) -> None:
    # `grant_application` rather than a builtin's name: a custom object may not
    # claim a word ORYH already ships, and the machine under test here never
    # depended on which word it was.
    response = client.post(
        "/api/v1/object-type-definitions",
        json={
            "object_type": "grant_application",
            "json_schema": {},
            "state_machine": {
                "initial": "open",
                "states": ["open", "approved", "rejected", "paid"],
                "transitions": {"open": ["approved", "rejected"], "approved": ["paid"], "rejected": [], "paid": []},
            },
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text

    # create mid-flow is allowed (recording an existing fact), unknown state is not
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "grant_application", "title": "A", "status": "approved"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    object_id = response.json()["data"]["id"]
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "grant_application", "title": "B", "status": "nonsense"},
        headers=HEADERS,
    )
    assert response.status_code == 422

    # transition guard
    response = client.patch(
        f"/api/v1/business-objects/{object_id}", json={"status": "open"}, headers=HEADERS
    )
    assert response.status_code == 409
    assert client.patch(
        f"/api/v1/business-objects/{object_id}", json={"status": "paid"}, headers=HEADERS
    ).status_code == 200

    # types without a machine keep the default status set
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "free_note", "title": "C", "status": "weird_state"},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "free_note", "title": "C", "status": "in_review"},
        headers=HEADERS,
    ).status_code == 201


# ---------------------------------------------------------------------------
# approval idempotency
# ---------------------------------------------------------------------------

def test_approval_record_idempotency(client: TestClient) -> None:
    response = client.post(
        "/api/v1/business-objects",
        json={"object_type": "claim", "title": "Claim"},
        headers=HEADERS,
    )
    object_id = response.json()["data"]["id"]
    body = {
        "entity_type": "business_object",
        "entity_id": object_id,
        "round_no": 1,
        "sequence_no": 1,
        "action": "submitted",
    }
    first = client.post("/api/v1/approval-records", json=body, headers=HEADERS)
    retry = client.post("/api/v1/approval-records", json=body, headers=HEADERS)
    assert first.json()["data"]["id"] == retry.json()["data"]["id"]

    records = client.get(
        f"/api/v1/approval-records?entity_type=business_object&entity_id={object_id}",
        headers=HEADERS,
    ).json()
    assert records["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# audit trail
# ---------------------------------------------------------------------------

def test_audit_trail_records_actions(client: TestClient) -> None:
    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)
    client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=HEADERS)
    client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "title": "Review timesheet",
        },
        headers=HEADERS,
    )
    client.patch(f"/api/v1/timesheet-headers/{header_id}", json={"status": "approved"}, headers=HEADERS)

    # newest first; every business change left a trail entry
    response = client.get("/api/v1/audit-logs", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    actions = [e["action"] for e in body["data"]]
    assert actions == ["timesheet.status_changed", "todo.created", "timesheet.submitted"]
    submitted = body["data"][-1]
    assert submitted["detail"]["employee_id"] == employee_id
    assert submitted["actor"].startswith("key:")

    # filters: entity, action, paging with before
    response = client.get(
        f"/api/v1/audit-logs?entity_type=timesheet_header&entity_id={header_id}", headers=HEADERS
    )
    assert response.json()["meta"]["total"] == 2
    response = client.get("/api/v1/audit-logs?action=todo.created", headers=HEADERS)
    assert response.json()["meta"]["total"] == 1
    newest_id = body["data"][0]["id"]
    response = client.get(f"/api/v1/audit-logs?before={newest_id}", headers=HEADERS)
    assert response.json()["meta"]["total"] == 2

    # tenant isolation
    response = client.get("/api/v1/audit-logs", headers=OTHER_HEADERS)
    assert response.json()["meta"]["total"] == 0


def test_todo_work_queue_and_due_dates(client: TestClient) -> None:
    employee_id = create_employee(client)
    header_id = create_header(client, employee_id)
    client.post(f"/api/v1/timesheet-headers/{header_id}/submit", json={}, headers=HEADERS)

    # flow-agent work queue: submitted headers nobody is assigned to yet
    queue = client.get(
        "/api/v1/timesheet-headers?status=submitted&without_open_todo=true", headers=HEADERS
    ).json()
    assert queue["meta"]["total"] == 1

    # assign an approval todo with a due date -> header leaves the queue
    response = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee_id,
            "entity_type": "timesheet_header",
            "entity_id": header_id,
            "title": "Approve timesheet",
            "due_at": "2026-07-04T09:00:00Z",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["data"]["due_at"] is not None
    queue = client.get(
        "/api/v1/timesheet-headers?status=submitted&without_open_todo=true", headers=HEADERS
    ).json()
    assert queue["meta"]["total"] == 0

    # escalation query: open todos due before a deadline
    overdue = client.get(
        "/api/v1/todos?status=open&due_before=2026-07-05T00:00:00Z", headers=HEADERS
    ).json()
    assert overdue["meta"]["total"] == 1
    none_due = client.get(
        "/api/v1/todos?status=open&due_before=2026-07-03T00:00:00Z", headers=HEADERS
    ).json()
    assert none_due["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# product skill provisioning
# ---------------------------------------------------------------------------

def test_new_tenant_gets_product_skills_and_builtin_machine(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tenants",
        json={"name": "Provisioned Co"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    key = response.json()["data"]["plain_text_api_key"]
    headers = {"X-API-Key": key}

    skills = client.get("/api/v1/skills", headers=headers).json()["data"]
    names = {s["name"] for s in skills}
    assert "oryh-timesheet-submit" in names
    assert "oryh-approve" in names
    assert all(s["kind"] == "product" for s in skills)

    definitions = client.get(
        "/api/v1/object-type-definitions?entity_kind=builtin", headers=headers
    ).json()["data"]
    by_type = {d["object_type"]: d for d in definitions}
    # Derived from the registry rather than restated: this list was a literal
    # and the eighth family (请假) made it wrong without saying anything about
    # the behaviour under test, which is that EVERY builtin machine provisions.
    from app.services.state_machines import BUILTIN_MACHINES

    assert set(by_type) == set(BUILTIN_MACHINES)
    assert by_type["timesheet_header"]["state_machine"]["initial"] == "draft"
    assert by_type["expense_claim"]["state_machine"]["initial"] == "draft"
    assert "paid" in by_type["expense_claim"]["state_machine"]["states"]
    assert by_type["purchase_request"]["state_machine"]["initial"] == "draft"
    assert "ordered" in by_type["purchase_request"]["state_machine"]["states"]
    assert by_type["sales_quotation"]["state_machine"]["initial"] == "draft"
    assert "superseded" in by_type["sales_quotation"]["state_machine"]["states"]
    assert by_type["sales_order"]["state_machine"]["initial"] == "draft"
    assert "shipped" in by_type["sales_order"]["state_machine"]["states"]

    # editing a product skill forks it to custom so catalog syncs keep hands off
    skill_name = "oryh-timesheet-submit"
    full = client.get(f"/api/v1/skills/{skill_name}", headers=headers).json()["data"]
    assert full["catalog_required_capability"] == full["required_capability"]  # untouched default
    new_files = dict(full["files"], **{"SKILL.md": full["files"]["SKILL.md"] + "\n<!-- tenant note -->\n"})
    response = client.patch(f"/api/v1/skills/{skill_name}", json={"files": new_files}, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["kind"] == "custom"
    assert response.json()["data"]["version"] == 2
    # a custom skill has no catalog baseline to track
    assert response.json()["data"]["catalog_required_capability"] is None


# ---------------------------------------------------------------------------
# workflow definitions (natural language, append-only versions)
# ---------------------------------------------------------------------------

def test_workflow_publish_lock_uses_stable_postgres_transaction_lock() -> None:
    postgres_db = Mock(spec=Session)
    postgres_db.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    lock_workflow_publish_scope(
        postgres_db,
        TEST_TENANT,
        "builtin",
        "timesheet_header",
        "default",
    )

    postgres_db.execute.assert_called_once()
    statement, params = postgres_db.execute.call_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {
        "lock_key": workflow_publish_lock_key(
            TEST_TENANT,
            "builtin",
            "timesheet_header",
            "default",
        )
    }
    assert params["lock_key"] != workflow_publish_lock_key(
        TEST_TENANT,
        "builtin",
        "timesheet_header",
        "alternate",
    )


def test_workflow_publish_lock_is_sqlite_compatible() -> None:
    sqlite_db = Mock(spec=Session)
    sqlite_db.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite")
    )

    lock_workflow_publish_scope(
        sqlite_db,
        TEST_TENANT,
        "builtin",
        "timesheet_header",
        "default",
    )

    sqlite_db.execute.assert_not_called()


def test_workflow_definition_versioning(client: TestClient) -> None:
    definition = client.post(
        "/api/v1/object-type-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "timesheet_header",
            "json_schema": {},
            "state_machine": DEFAULT_TIMESHEET_MACHINE,
        },
        headers=HEADERS,
    )
    assert definition.status_code == 201, definition.text
    v1_text = "工时提交后由直属经理审批，通过即 approved。"
    response = client.post(
        "/api/v1/workflow-definitions",
        json={"entity_kind": "builtin", "object_type": "timesheet_header", "definition_text": v1_text},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    v1 = response.json()["data"]
    assert v1["version"] == 1 and v1["status"] == "active"

    v2_text = "工时提交后由直属经理审批；超过40小时需财务复核；财务复核可能在改判后再次进行。"
    response = client.post(
        "/api/v1/workflow-definitions",
        json={"entity_kind": "builtin", "object_type": "timesheet_header", "definition_text": v2_text},
        headers=HEADERS,
    )
    v2 = response.json()["data"]
    assert v2["version"] == 2 and v2["status"] == "active"

    # default listing returns only the active version
    listing = client.get(
        "/api/v1/workflow-definitions?entity_kind=builtin&object_type=timesheet_header",
        headers=HEADERS,
    ).json()
    assert listing["meta"]["total"] == 1
    assert listing["data"][0]["version"] == 2
    assert listing["data"][0]["definition_text"] == v2_text

    # history keeps every version; superseded v1 is still fetchable by id
    history = client.get(
        "/api/v1/workflow-definitions?object_type=timesheet_header&history=true",
        headers=HEADERS,
    ).json()
    assert history["meta"]["total"] == 2
    old = client.get(f"/api/v1/workflow-definitions/{v1['id']}", headers=HEADERS).json()["data"]
    assert old["status"] == "superseded"
    assert old["definition_text"] == v1_text

    paged = client.get(
        "/api/v1/workflow-definitions",
        params={
            "history": True,
            "status": "active",
            "keyword": "40小时",
            "page": 1,
            "size": 1,
        },
        headers=HEADERS,
    ).json()
    assert paged["meta"] == {"total": 1, "page": 1, "page_size": 1, "pages": 1}
    assert paged["data"][0]["id"] == v2["id"]

    # publishing left an audit entry
    audit = client.get("/api/v1/audit-logs?action=workflow.published", headers=HEADERS).json()
    assert audit["meta"]["total"] == 2

    # tenant isolation
    other = client.get("/api/v1/workflow-definitions", headers=OTHER_HEADERS).json()
    assert other["meta"]["total"] == 0
    assert client.get(
        f"/api/v1/workflow-definitions/{v1['id']}", headers=OTHER_HEADERS
    ).status_code == 404


def test_workflow_publish_rejects_typos_and_accepts_known_custom_types(
    client: TestClient,
) -> None:
    unknown_builtin = client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "timeshet_header",
            "definition_text": "typo",
        },
        headers=HEADERS,
    )
    assert unknown_builtin.status_code == 422
    assert "unknown builtin" in unknown_builtin.json()["detail"]

    # a browsable collection with no lifecycle is not a workflow subject at
    # all: there is no state machine for a definition to route
    machineless = client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "resource_booking",
            "definition_text": "not configured",
        },
        headers=HEADERS,
    )
    assert machineless.status_code == 422
    assert "unknown builtin" in machineless.json()["detail"]

    # ...while a real workflow subject this tenant has not had provisioned yet
    # is refused for the other reason
    missing_builtin_definition = client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "invoice",
            "definition_text": "not configured",
        },
        headers=HEADERS,
    )
    assert missing_builtin_definition.status_code == 422
    assert "no active definition" in missing_builtin_definition.json()["detail"]

    typo_custom = client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "business_object",
            "object_type": "waranty_card",
            "definition_text": "typo",
        },
        headers=HEADERS,
    )
    assert typo_custom.status_code == 422
    assert "neither an active definition nor existing data" in typo_custom.json()["detail"]

    definition = client.post(
        "/api/v1/object-type-definitions",
        json={"object_type": "defined_type", "json_schema": {}},
        headers=HEADERS,
    )
    assert definition.status_code == 201
    assert client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "business_object",
            "object_type": "defined_type",
            "definition_text": "definition-backed",
        },
        headers=HEADERS,
    ).status_code == 201

    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "data_only_type", "title": "Existing object"},
        headers=HEADERS,
    ).status_code == 201
    assert client.post(
        "/api/v1/workflow-definitions",
        json={
            "entity_kind": "business_object",
            "object_type": "data_only_type",
            "definition_text": "data-backed",
        },
        headers=HEADERS,
    ).status_code == 201


def test_filtering_on_a_renamed_state_fails_loudly_instead_of_returning_nothing(
    client: TestClient,
) -> None:
    """The silent wrong answer, pinned.

    Only `draft` and `submitted` are anchored; a tenant may rename every other
    state. Filtering on a name it no longer uses returned 200 with zero rows,
    which reads as "nothing to do" rather than "you asked the wrong question" —
    an agent following a product skill's `?status=returned` told its principal
    there was nothing waiting while work sat in the tenant's own state.

    A status outside the machine can never match a row, so refusing it loses no
    legitimate query.
    """
    client.post(
        "/api/v1/object-type-definitions",
        json={
            "entity_kind": "builtin",
            "object_type": "timesheet_header",
            "title": "Timesheet without returns",
            "state_machine": {
                "initial": "draft",
                "states": ["draft", "submitted", "approved", "rejected"],
                "transitions": {
                    "draft": ["submitted"],
                    "submitted": ["approved", "rejected"],
                    "approved": [],
                    "rejected": [],
                },
                "editable_states": ["draft"],
            },
        },
        headers=HEADERS,
    )

    response = client.get("/api/v1/timesheet-headers?status=returned", headers=HEADERS)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    # names what this workspace actually uses, so the agent can retry correctly
    assert "returned" in detail
    assert "approved" in detail and "draft" in detail

    # states this tenant does use still answer normally, empty or not
    for state in ("draft", "submitted", "approved"):
        assert client.get(f"/api/v1/timesheet-headers?status={state}", headers=HEADERS).status_code == 200

    # and the guard is per tenant: the default machine still has `returned`
    assert client.get(
        "/api/v1/timesheet-headers?status=returned", headers=OTHER_HEADERS
    ).status_code == 200


def test_status_filter_guard_covers_every_builtin_document(client: TestClient) -> None:
    """One family fixed and the rest left silent would be the worst outcome —
    the skills hardcode default names across all of them."""
    for path in (
        "timesheet-headers",
        "expense-claims",
        "purchase-requests",
        "sales-quotations",
        "sales-orders",
        "purchase-orders",
    ):
        response = client.get(f"/api/v1/{path}?status=no_such_state", headers=HEADERS)
        assert response.status_code == 422, f"{path}: {response.status_code} {response.text}"

    # custom objects too, when the query names the type whose machine to check
    assert client.get(
        "/api/v1/business-objects?object_type=contract_review&status=no_such_state", headers=HEADERS
    ).status_code == 422
    # ...and not when it does not — the query spans types with different machines
    assert client.get(
        "/api/v1/business-objects?status=no_such_state", headers=HEADERS
    ).status_code == 200


def test_a_capability_that_reaches_nobody_is_reported() -> None:
    """Three releases shipped a capability that reached nobody who needed it —
    结算, 工资, 请假 — and each was found days later by a 403 in somebody's
    flow. `provision_system_roles` cannot fix it (a capability missing from a
    role the tenant designed might be a decision, not an omission), but the
    deploy log can say so.

    The condition has to be exactly right or the alarm is useless, and the two
    obvious versions both are. Asking "does any role hold it" can never fire —
    `admin` is topped up with everything. Asking "does `member` hold what our
    defaults give `member`" always fires on any workspace that tuned its
    baseline, which our own demo seed does on purpose. Both are pinned here."""
    from sqlalchemy import select

    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
    from app.models import Role
    from app.services.provisioning import unheld_shipped_capabilities
    from conftest import provision_tenant

    with make_client([]) as client:
        data = provision_tenant(client, company_name="Gap Co",
                                email="admin@gap-co.com", password="gap-pass1234")
        root = {"X-API-Key": data["plain_text_api_key"]}
        with client.session_factory() as db:
            tenant_id = db.scalar(select(Tenant.id))
            # a fresh tenant is complete: every shipped capability reaches someone
            assert unheld_shipped_capabilities(db, tenant_id) == {}

        # take it off `member`, the way a tenant older than the capability looks
        stripped = [p for p in DEFAULT_ROLE_PERMISSIONS["member"] if p != "leave.submit_own"]
        client.patch("/api/v1/roles/member", json={"permissions": stripped}, headers=root)

        with client.session_factory() as db:
            report = unheld_shipped_capabilities(db, tenant_id)
            assert report.get("leave.submit_own") == ["member"]
            # `admin` still holding it must NOT silence the report — that is the
            # bug which made the first version permanently quiet
            admin = db.scalar(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == "admin")
            )
            assert "leave.submit_own" in (admin.permissions_jsonb or [])

        # a capability a CUSTOM role carries is a workspace organising itself,
        # not a gap — the noise that made the second version permanently loud
        client.post("/api/v1/roles",
                    json={"name": "leave_desk", "permissions": ["leave.submit_own"]},
                    headers=root)
        with client.session_factory() as db:
            assert "leave.submit_own" not in unheld_shipped_capabilities(db, tenant_id)
