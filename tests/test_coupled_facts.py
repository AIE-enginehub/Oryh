"""Facts that must land together, checked by driving them rather than reading.

The recurring defect this file exists for: writing fact A logically requires
fact B, A and B are separate API calls, and one of them does not happen. The
approval record and the approver's todo was the case that reached production —
`POST /approval-records` succeeded, `PATCH /todos/{id}` did not, and a timesheet
sat in a queue that read as active for three weeks.

Reviewing for it does not work. It is invisible in any one endpoint: each call
is correct, and the coupling lives between them, in a skill document. So each
pair is driven here through the API, and the invariant asserted on the result.

Two shapes, both covered:

  a coupled WRITE — one call must produce both facts
  a coupled RETIREMENT — a document that stops being movable takes its
                         outstanding work with it

The derived-sum shape is not here. Those columns (`quantity_on_hand`,
`applied_amount`, `balance`) have one writer each and never leave the
transaction that moves their ledger; `tests/test_single_writer_columns.py`
holds that property, and `scripts/data_integrity_audit.py` recomputes each sum
against its ledger in a live database.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.core.entity_types import BUILTIN_QUEUE_PATHS, DOCUMENT_ENTITY_TYPES
from app.services.state_machines import BUILTIN_MACHINES
from conftest import provision_tenant

API = pathlib.Path(__file__).resolve().parent.parent / "app" / "api"

# One family per shape the coupling has to hold for, not all nine: the code
# under test is `common.py`'s two funnels, which every family shares. A tenth
# family added tomorrow gets the behaviour for free, and would show up in
# `test_every_family_shares_the_funnel` if it did not.
FAMILY = "timesheet_header"


@pytest.fixture()
def workspace(client: TestClient):
    ctx = provision_tenant(client, company_name="Coupled Co", email="admin@coupled-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    submitter = client.post("/api/v1/employees", json={"name": "提交人"},
                            headers=key).json()["data"]["id"]
    approver = client.post("/api/v1/employees", json={"name": "审批人"},
                           headers=key).json()["data"]["id"]
    return {"client": client, "key": key, "submitter": submitter, "approver": approver}


def new_header(workspace, *, start="2026-08-03", end="2026-08-09") -> str:
    return workspace["client"].post("/api/v1/timesheet-headers", json={
        "employee_id": workspace["submitter"], "period_start": start, "period_end": end,
    }, headers=workspace["key"]).json()["data"]["id"]


def open_todos(workspace, header: str) -> list[dict]:
    rows = workspace["client"].get(
        f"/api/v1/todos?entity_type=timesheet_header&entity_id={header}",
        headers=workspace["key"],
    ).json()["data"]
    return [t for t in rows if t["status"] == "open"]


def add_todo(workspace, header: str, *, todo_type: str | None, employee: str) -> str:
    response = workspace["client"].post("/api/v1/todos", json={
        "employee_id": employee, "entity_type": "timesheet_header", "entity_id": header,
        "title": f"{todo_type or 'ad hoc'} 工作", "todo_type": todo_type,
    }, headers=workspace["key"])
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


# --- coupled retirement: a document that cannot move takes its work with it --


def test_a_terminal_status_retires_the_open_work(workspace) -> None:
    """`leave-no-orphan-work.md` used to tell agents to do this by hand, on a
    path where the status change had already succeeded. Five payslips were
    voided that way and five todos stayed open for months."""
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])
    add_todo(workspace, header, todo_type="approval", employee=workspace["approver"])

    assert workspace["client"].patch(
        f"/api/v1/timesheet-headers/{header}", json={"status": "approved"},
        headers=workspace["key"],
    ).status_code == 200

    assert open_todos(workspace, header) == []


def test_a_non_terminal_status_leaves_the_work_alone(workspace) -> None:
    """The other half. `submitted` is a state work is done IN — a sweep that
    could not tell the two apart would empty every queue in the workspace."""
    header = new_header(workspace)
    add_todo(workspace, header, todo_type="approval", employee=workspace["approver"])

    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])

    assert len(open_todos(workspace, header)) == 1


def test_the_retirement_is_cancelled_not_completed(workspace) -> None:
    """Nobody did the work. A queue history that records it as done cannot
    answer what a person actually did, which is the whole reason both statuses
    exist."""
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])
    todo_id = add_todo(workspace, header, todo_type="approval", employee=workspace["approver"])

    workspace["client"].patch(f"/api/v1/timesheet-headers/{header}",
                              json={"status": "rejected"}, headers=workspace["key"])

    todo = workspace["client"].get(f"/api/v1/todos/{todo_id}",
                                   headers=workspace["key"]).json()["data"]
    assert todo["status"] == "cancelled"


def test_every_builtin_family_retires_work_at_every_terminal_state() -> None:
    """The funnel is shared, so this is really a check on the machines: a
    family whose terminal states are also editable would silently opt out of
    the sweep, and that is a decision worth failing a build over rather than
    discovering in a queue."""
    overlapping = {
        name: sorted(
            set(state for state, moves in machine.get("transitions", {}).items() if not moves)
            & set(machine.get("editable_states", ()))
        )
        for name, machine in BUILTIN_MACHINES.items()
    }
    offenders = {name: states for name, states in overlapping.items() if states}
    assert offenders == {}, (
        f"{offenders} declare terminal states that are also editable — documents there "
        "keep their open todos, which may be right, but say so on purpose"
    )


# --- coupled write: a resubmission completes the rework it answers -----------


def test_resubmitting_completes_the_rework_todo(workspace) -> None:
    """Two skills told the agent to `PATCH /todos/{id}` after the resubmit, and
    `leave-no-orphan-work.md` claimed the server already did it. Now it does."""
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])
    workspace["client"].post("/api/v1/approval-records", json={
        "entity_type": FAMILY, "entity_id": header, "round_no": 1, "sequence_no": 2,
        "action": "returned", "document_status": "returned",
        "handoff": {"employee_id": workspace["submitter"], "title": "修改工时",
                    "todo_type": "rework"},
    }, headers=workspace["key"])
    rework = open_todos(workspace, header)
    assert [t["todo_type"] for t in rework] == ["rework"]

    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])

    todo = workspace["client"].get(f"/api/v1/todos/{rework[0]['id']}",
                                   headers=workspace["key"]).json()["data"]
    assert todo["status"] == "completed"
    assert todo["completed_at"] is not None


def test_resubmitting_leaves_other_work_open(workspace) -> None:
    """Only the rework. "attach the receipt" is still worth doing on a document
    that has just been sent back up."""
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])
    workspace["client"].post("/api/v1/approval-records", json={
        "entity_type": FAMILY, "entity_id": header, "round_no": 1, "sequence_no": 2,
        "action": "returned", "document_status": "returned",
    }, headers=workspace["key"])
    add_todo(workspace, header, todo_type=None, employee=workspace["submitter"])

    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])

    assert [t["todo_type"] for t in open_todos(workspace, header)] == [None]


# --- the pairs that are deliberately NOT coupled ---------------------------


def routed_endpoints() -> list[tuple[str, str, set[str]]]:
    """(verb+path, function name, names it calls) for every mutating route."""
    found = []
    for path in sorted(API.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for deco in fn.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                if deco.func.attr not in ("post", "patch"):
                    continue
                if not deco.args or not isinstance(deco.args[0], ast.Constant):
                    continue
                calls = {
                    node.func.id
                    for node in ast.walk(fn)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                found.append((f"{deco.func.attr.upper()} {deco.args[0].value}", fn.name, calls))
    return found


def test_every_family_shares_the_funnel() -> None:
    """The two fixes above live in `submit_document` and `apply_status_change`,
    which is only worth anything while every family goes through them.

    A family whose PATCH sets `status` itself would keep its open todos on a
    terminal state, and one whose `/submit` writes the status itself would
    leave the rework todo open — and both would look completely ordinary in
    review. The quotation's `/close` and `/revise` are the two that genuinely
    do their own transition, so they call the shared retirement directly and
    are named here rather than discovered later.
    """
    endpoints = routed_endpoints()
    # `BUILTIN_QUEUE_PATHS` answers "what here is unattended" and deliberately
    # omits purchase orders and shipments — nobody hosted may advance either
    # (one functional grant drives each, and neither has a /submit). Their
    # PATCHes still set a status, so they belong in this check even though
    # they never appear in a flow queue; leaving them out is how they would
    # go unwatched.
    collections = {path.strip("/") for path in BUILTIN_QUEUE_PATHS.values()} | {
        "purchase-orders", "shipments",
    }
    assert len(collections) == len(DOCUMENT_ENTITY_TYPES), (
        f"{len(collections)} collections for {len(DOCUMENT_ENTITY_TYPES)} document families — "
        "a family was added and this test cannot see its endpoints"
    )

    submits = [(route, fn, calls) for route, fn, calls in endpoints if route.endswith("/submit")]
    assert len(submits) == len(BUILTIN_QUEUE_PATHS), (
        f"{len(submits)} submit endpoints for {len(BUILTIN_QUEUE_PATHS)} submittable families — "
        "one of them is not where this test can see it"
    )
    detached = sorted(route for route, _fn, calls in submits if "submit_document" not in calls)
    assert detached == [], (
        f"{detached} do not go through `submit_document`, so a resubmission there "
        "leaves the rework todo open"
    )

    # every PATCH on a family collection, and the two bespoke transitions
    own_transition = {
        "POST /sales-quotations/{quotation_id}/close",
        "POST /sales-quotations/{quotation_id}/revise",
    }
    for route, _fn, calls in endpoints:
        if not route.startswith("PATCH /"):
            continue
        collection = route.split("/")[1].split("{")[0].strip("/")
        if collection not in collections:
            continue
        assert "apply_status_change" in calls, (
            f"{route} does not go through `apply_status_change` — a terminal status "
            "set there would leave the document's open todos behind"
        )
    for route, _fn, calls in endpoints:
        if route in own_transition:
            assert "retire_open_work_if_finished" in calls, (
                f"{route} performs its own transition and must retire the work itself"
            )


def test_a_decision_does_not_move_the_document_on_its_own(workspace) -> None:
    """Not an oversight, and worth a test so it is not "fixed" by accident.
    An approver records a fact; whether the document is now approved is the
    workflow admin's call, in another session, reading the whole trail. The
    coupling on offer is `document_status` in the same call — taken when the
    caller knows the answer, and that caller is not the approver.
    """
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])

    workspace["client"].post("/api/v1/approval-records", json={
        "entity_type": FAMILY, "entity_id": header, "round_no": 1, "sequence_no": 2,
        "action": "approved",
    }, headers=workspace["key"])

    detail = workspace["client"].get(f"/api/v1/timesheet-headers/{header}",
                                     headers=workspace["key"]).json()["data"]
    assert detail["status"] == "submitted"


def test_submitting_does_not_invent_an_approver(workspace) -> None:
    """A submitted document with no todo is transient by design, not stranded:
    the flow agent polls `without_open_todo=true` and assigns. Nobody but that
    agent knows who the approver is, so the server does not guess — and
    `data_integrity_audit.py` reports the ones that sit that way for an hour.
    """
    header = new_header(workspace)
    workspace["client"].post(f"/api/v1/timesheet-headers/{header}/submit",
                             json={}, headers=workspace["key"])

    assert open_todos(workspace, header) == []
    unassigned = workspace["client"].get(
        "/api/v1/timesheet-headers?without_open_todo=true", headers=workspace["key"]
    ).json()["data"]
    assert header in [row["id"] for row in unassigned]
