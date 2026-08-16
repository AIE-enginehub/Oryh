"""A round transition is several facts. They land together or not at all.

The approval-flow skills describe a return as three calls: record the
`returned` fact, move the document to `returned`, open the submitter's rework
todo. Three calls is three chances to land the first and not the rest, and the
result is HKG-015's shape — a trail saying one thing, a status saying another,
nobody assigned. The same is true of an approval that ends the chain.

So `POST /approval-records` takes the other two as optional fields and commits
all three together. What the server decides is unchanged: the agent still says
which status and whose queue. These tests hold that line — the guards that
protected the separate calls still refuse the same things here — and pin the
retry path, which is the reason the coupling was worth making at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import make_client, provision_tenant


@pytest.fixture()
def flow(client: TestClient):
    ctx = provision_tenant(client, company_name="Round Co", email="admin@round-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    submitter = client.post("/api/v1/employees", json={"name": "提交人"},
                            headers=key).json()["data"]["id"]
    approver = client.post("/api/v1/employees", json={"name": "审批人"},
                           headers=key).json()["data"]["id"]
    header = client.post("/api/v1/timesheet-headers", json={
        "employee_id": submitter, "period_start": "2026-08-03", "period_end": "2026-08-09",
    }, headers=key).json()["data"]["id"]
    assert client.post(f"/api/v1/timesheet-headers/{header}/submit",
                       json={}, headers=key).status_code == 200
    return {"client": client, "key": key, "header": header,
            "submitter": submitter, "approver": approver}


def todos_on(flow, **filters) -> list[dict]:
    rows = flow["client"].get(
        f"/api/v1/todos?entity_type=timesheet_header&entity_id={flow['header']}",
        headers=flow["key"],
    ).json()["data"]
    return [t for t in rows if all(t.get(k) == v for k, v in filters.items())]


def status_of(flow) -> str:
    return flow["client"].get(
        f"/api/v1/timesheet-headers/{flow['header']}", headers=flow["key"]
    ).json()["data"]["status"]


def test_a_return_is_one_call_carrying_all_three_facts(flow) -> None:
    response = flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
        "comment": "项目编号缺失",
        "document_status": "returned",
        "handoff": {"employee_id": flow["submitter"], "title": "修改工时",
                    "description": "项目编号缺失", "todo_type": "rework"},
    }, headers=flow["key"])
    assert response.status_code == 201, response.text

    assert status_of(flow) == "returned"
    rework = todos_on(flow, todo_type="rework", status="open")
    assert len(rework) == 1
    assert rework[0]["employee_id"] == flow["submitter"]
    assert rework[0]["description"] == "项目编号缺失"


def test_the_handoff_survives_the_returned_sweep(flow) -> None:
    """`returned` cancels the round's approval todos. The rework todo opened by
    the same call must not be swept with them — it belongs to the new round."""
    flow["client"].post("/api/v1/todos", json={
        "employee_id": flow["approver"], "entity_type": "timesheet_header",
        "entity_id": flow["header"], "title": "审批工时", "todo_type": "approval",
        "metadata": {"round_no": 1, "sequence_no": 2},
    }, headers=flow["key"])

    flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
        "document_status": "returned",
        "handoff": {"employee_id": flow["submitter"], "title": "修改工时",
                    "todo_type": "rework"},
    }, headers=flow["key"])

    assert todos_on(flow, todo_type="approval", status="open") == []
    assert len(todos_on(flow, todo_type="rework", status="open")) == 1


def test_a_retry_finishes_a_transition_that_stopped_halfway(flow) -> None:
    """The whole reason for the coupling. An agent that recorded the fact and
    then died must be able to repeat the call and end up in the intended state
    — not receive its own fact back while the document stays put."""
    body = {
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
    }
    assert flow["client"].post("/api/v1/approval-records", json=body,
                               headers=flow["key"]).status_code == 201
    assert status_of(flow) == "submitted"

    retried = flow["client"].post("/api/v1/approval-records", json={
        **body,
        "document_status": "returned",
        "handoff": {"employee_id": flow["submitter"], "title": "修改工时",
                    "todo_type": "rework"},
    }, headers=flow["key"])
    assert retried.status_code == 201, retried.text
    assert status_of(flow) == "returned"
    assert len(todos_on(flow, todo_type="rework", status="open")) == 1


def test_repeating_the_whole_call_makes_no_second_todo(flow) -> None:
    body = {
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
        "document_status": "returned",
        "handoff": {"employee_id": flow["submitter"], "title": "修改工时",
                    "todo_type": "rework"},
    }
    assert flow["client"].post("/api/v1/approval-records", json=body,
                               headers=flow["key"]).status_code == 201
    assert flow["client"].post("/api/v1/approval-records", json=body,
                               headers=flow["key"]).status_code == 201
    assert len(todos_on(flow, todo_type="rework", status="open")) == 1


def test_an_illegal_status_is_refused_and_takes_the_fact_with_it(flow) -> None:
    """The machine still rules. And because the three facts share a
    transaction, a refusal on the second must not leave the first behind —
    which is the failure mode the separate calls HAD."""
    response = flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "approved",
        "document_status": "draft",
    }, headers=flow["key"])
    assert response.status_code == 409, response.text

    trail = flow["client"].get(
        f"/api/v1/approval-records?entity_type=timesheet_header&entity_id={flow['header']}",
        headers=flow["key"],
    ).json()["data"]
    assert [r["action"] for r in trail] == ["submitted"]
    assert status_of(flow) == "submitted"


def test_an_unknown_employee_is_refused_and_takes_the_fact_with_it(flow) -> None:
    response = flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
        "document_status": "returned",
        "handoff": {"employee_id": "00000000000000000000000000000000",
                    "title": "修改工时", "todo_type": "rework"},
    }, headers=flow["key"])
    assert response.status_code == 404, response.text

    trail = flow["client"].get(
        f"/api/v1/approval-records?entity_type=timesheet_header&entity_id={flow['header']}",
        headers=flow["key"],
    ).json()["data"]
    assert [r["action"] for r in trail] == ["submitted"]
    assert status_of(flow) == "submitted"


def test_the_three_separate_calls_still_work(flow) -> None:
    """Both new fields are optional. A skill that has not been updated — and
    every bundle already in the field is one — keeps working unchanged."""
    assert flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "returned",
    }, headers=flow["key"]).status_code == 201
    assert flow["client"].patch(f"/api/v1/timesheet-headers/{flow['header']}",
                                json={"status": "returned"},
                                headers=flow["key"]).status_code == 200
    assert flow["client"].post("/api/v1/todos", json={
        "employee_id": flow["submitter"], "entity_type": "timesheet_header",
        "entity_id": flow["header"], "title": "修改工时", "todo_type": "rework",
    }, headers=flow["key"]).status_code == 201

    assert status_of(flow) == "returned"
    assert len(todos_on(flow, todo_type="rework", status="open")) == 1


def test_a_tenant_defined_target_moves_the_same_way() -> None:
    """`approval_target` and `business_object` are the same table, and their
    machines are the tenant's own. The transition still commits as one fact."""
    with make_client() as client:
        ctx = provision_tenant(client, company_name="Proj Co", email="admin@proj-co.example")
        key = {"X-API-Key": ctx["plain_text_api_key"]}
        approver = client.post("/api/v1/employees", json={"name": "审批人"},
                               headers=key).json()["data"]["id"]
        target = client.post("/api/v1/approval-targets", json={
            "target_type": "合同", "title": "年度框架协议",
        }, headers=key)
        assert target.status_code == 201, target.text
        target_id = target.json()["data"]["id"]

        response = client.post("/api/v1/approval-records", json={
            "entity_type": "approval_target", "entity_id": target_id,
            "round_no": 1, "sequence_no": 1, "action": "submitted",
            "document_status": "in_review",
            "handoff": {"employee_id": approver, "title": "审阅合同",
                        "todo_type": "approval"},
        }, headers=key)
        assert response.status_code == 201, response.text

        detail = client.get(f"/api/v1/approval-targets/{target_id}", headers=key).json()["data"]
        assert detail["status"] == "in_review"
        todos = client.get(
            f"/api/v1/todos?entity_type=approval_target&entity_id={target_id}", headers=key
        ).json()["data"]
        assert [t["title"] for t in todos if t["status"] == "open"] == ["审阅合同"]

        # and the machine still rules for these types too
        refused = client.post("/api/v1/approval-records", json={
            "entity_type": "approval_target", "entity_id": target_id,
            "round_no": 1, "sequence_no": 2, "action": "approved",
            "document_status": "不是一个状态",
        }, headers=key)
        assert refused.status_code == 422


def test_every_approval_entity_type_has_a_branch_that_handles_it() -> None:
    """`apply_round_transition` raises for a target that is neither a document
    family nor a business object. That branch is currently unreachable — and
    the day somebody adds an entity type it stops being, `document_status`
    would start returning 422 on a live path.

    So the registry is checked rather than the refusal: every approval entity
    type must map to a model one of the two branches handles.
    """
    from app.api.common import DOCUMENT_FAMILIES
    from app.core.entity_types import APPROVAL_ENTITY_TYPES
    from app.models import BusinessObject

    handled = {family.object_type for family in DOCUMENT_FAMILIES.values()}
    handled |= {"approval_target", "business_object"}  # both are BusinessObject rows
    assert BusinessObject.__tablename__ == "business_objects"

    unhandled = sorted(set(APPROVAL_ENTITY_TYPES) - handled)
    assert unhandled == [], (
        f"{unhandled} can carry approval facts but apply_round_transition has no "
        "branch for them — document_status would 422 on a real path"
    )


def test_a_handoff_onto_a_finished_document_is_refused(flow) -> None:
    """The one contradiction the combined call can express. `rejected` is a
    state the timesheet machine does not leave, so a todo opened there could
    never be acted on — which is the stranded work this change exists to stop,
    now reachable in a single call instead of two. Refused by name, and the
    approval fact goes back with it."""
    response = flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "rejected",
        "document_status": "rejected",
        "handoff": {"employee_id": flow["submitter"], "title": "修改工时",
                    "todo_type": "rework"},
    }, headers=flow["key"])
    assert response.status_code == 409, response.text
    assert "does not leave" in response.json()["detail"]

    trail = flow["client"].get(
        f"/api/v1/approval-records?entity_type=timesheet_header&entity_id={flow['header']}",
        headers=flow["key"],
    ).json()["data"]
    assert [r["action"] for r in trail] == ["submitted"]
    assert status_of(flow) == "submitted"


def test_a_finished_status_without_a_handoff_is_fine(flow) -> None:
    """The other side: finalizing IS the normal use of `document_status`, and
    the guard must not get in its way."""
    response = flow["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": flow["header"],
        "round_no": 1, "sequence_no": 2, "action": "approved",
        "document_status": "approved",
    }, headers=flow["key"])
    assert response.status_code == 201, response.text
    assert status_of(flow) == "approved"
