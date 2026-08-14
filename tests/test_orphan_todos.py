"""A work item whose subject no longer exists cannot be done.

HR issued five payslips, the CEO returned them, and five rework todos appeared.
HR then voided all five and issued five fresh ones, which were approved — and
the five todos stayed open forever, pointing at documents that had been
deleted. Nothing misbehaved: "fix the returned document" and "void it and redo
it" are both reasonable ways to answer a rejection, and only the first had
anything that closed the todo.

So the server closes them on the one fact it is certain of — the target is
gone. Everything softer than that (a document *voided by status*, a todo whose
work moved elsewhere) stays with the flow agent, which is the only thing that
reads the workspace's own rules.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


def post(client, headers, path, body):
    response = client.post(f"/api/v1{path}", json=body, headers=headers)
    assert response.status_code in (200, 201), (path, response.status_code, response.text)
    return response.json()["data"]


@pytest.fixture()
def payroll_round(client: TestClient) -> dict:
    """Five payslips, each with a rework todo on HR — the state the CEO's
    rejection leaves behind."""
    data = provision_tenant(client, company_name="Slip Co", email="admin@slip-co.com",
                            password="slip-pass1234")
    headers = {"X-API-Key": data["plain_text_api_key"]}
    hr = post(client, headers, "/employees", {"name": "HR"})["id"]
    slips = []
    for index in range(5):
        payee = post(client, headers, "/employees", {"name": f"员工{index}"})["id"]
        slip = post(client, headers, "/invoices", {
            "direction": "payroll", "employee_id": hr, "payee_employee_id": payee,
            "title": f"2026年6月工资 {index}",
            "period_start": "2026-06-01", "period_end": "2026-06-30",
            "items": [{"invoice_item_type": "payroll_salary",
                       "product_name_snapshot": "基本工资", "amount": 10000.0,
                       "notes": "月薪 10000.00"}],
        })
        todo = post(client, headers, "/todos", {
            "employee_id": hr, "entity_type": "invoice", "entity_id": slip["id"],
            "title": f"修改工资条 {index}", "todo_type": "rework",
        })
        slips.append((slip["id"], todo["id"]))
    return {"client": client, "headers": headers, "hr": hr, "slips": slips}


def open_todos(payroll_round: dict) -> list[dict]:
    return payroll_round["client"].get(
        f"/api/v1/todos?employee_id={payroll_round['hr']}&status=open",
        headers=payroll_round["headers"],
    ).json()["data"]


def test_voiding_the_document_closes_the_work_item_that_pointed_at_it(payroll_round: dict) -> None:
    client, headers = payroll_round["client"], payroll_round["headers"]
    assert len(open_todos(payroll_round)) == 5

    for slip_id, _ in payroll_round["slips"]:
        assert client.delete(f"/api/v1/invoices/{slip_id}", headers=headers).status_code == 204

    assert open_todos(payroll_round) == []


def test_a_cancelled_todo_does_not_claim_it_was_done(payroll_round: dict) -> None:
    """The distinction the whole thing rests on. Nobody did this work, so the
    trail must not say they did — and a report counting `completed_at` must not
    pick it up."""
    client, headers = payroll_round["client"], payroll_round["headers"]
    slip_id, todo_id = payroll_round["slips"][0]
    client.delete(f"/api/v1/invoices/{slip_id}", headers=headers)

    todo = client.get(f"/api/v1/todos/{todo_id}", headers=headers).json()["data"]
    assert todo["status"] == "cancelled"
    assert todo["completed_at"] is None
    assert todo["completed_by"] is None

    trail = client.get(f"/api/v1/audit-logs?action=todo.cancelled&entity_id={todo_id}",
                       headers=headers).json()
    assert trail["meta"]["total"] == 1
    detail = trail["data"][0]["detail"]
    assert detail["target_id"] == slip_id
    assert "deleted" in detail["reason"]


def test_the_replacement_document_is_free_to_raise_its_own_todo(payroll_round: dict) -> None:
    """Why `cancelled` and not something that keeps the row `open`: the partial
    unique index reserves one OPEN todo per person per record, and the redo has
    to be able to raise work of its own."""
    client, headers, hr = payroll_round["client"], payroll_round["headers"], payroll_round["hr"]
    slip_id, _ = payroll_round["slips"][0]
    client.delete(f"/api/v1/invoices/{slip_id}", headers=headers)
    # while it is deleted there is no work to raise, and the server says so
    refused = client.post("/api/v1/todos", json={
        "employee_id": hr, "entity_type": "invoice", "entity_id": slip_id, "title": "x",
    }, headers=headers)
    assert refused.status_code == 404

    client.post(f"/api/v1/invoices/{slip_id}/restore", headers=headers)
    again = client.post("/api/v1/todos", json={
        "employee_id": hr, "entity_type": "invoice", "entity_id": slip_id,
        "title": "同一单据上的新工作", "todo_type": "rework",
    }, headers=headers)
    assert again.status_code == 201, again.text


def test_restoring_the_document_does_not_resurrect_the_todo(payroll_round: dict) -> None:
    """A cancellation is not undone by a restore. The restored document
    re-enters the flow agent's queue — `without_open_todo=true` is what finds
    it — and fresh work is truer than a revived row whose text may no longer be
    what needs doing."""
    client, headers = payroll_round["client"], payroll_round["headers"]
    slip_id, todo_id = payroll_round["slips"][0]
    client.delete(f"/api/v1/invoices/{slip_id}", headers=headers)
    restored = client.post(f"/api/v1/invoices/{slip_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text

    todo = client.get(f"/api/v1/todos/{todo_id}", headers=headers).json()["data"]
    assert todo["status"] == "cancelled"
    # …and the flow agent can see there is work to raise again
    queue = client.get("/api/v1/invoices?direction=payroll&without_open_todo=true",
                       headers=headers).json()["data"]
    assert slip_id in {row["id"] for row in queue}


def test_only_this_document_s_todos_are_touched(payroll_round: dict) -> None:
    """The guard is per record. Voiding one payslip must not clear the queue."""
    client, headers = payroll_round["client"], payroll_round["headers"]
    slip_id, _ = payroll_round["slips"][0]
    client.delete(f"/api/v1/invoices/{slip_id}", headers=headers)
    assert len(open_todos(payroll_round)) == 4


def test_an_agent_may_cancel_work_the_rules_retired(payroll_round: dict) -> None:
    """The other half, and the reason `cancelled` is a first-class status
    rather than a server-only side effect: when a document is voided BY STATUS
    rather than deleted, only the flow agent knows the workspace calls that
    state dead. It needs a word for closing the todo that is not a lie."""
    client, headers = payroll_round["client"], payroll_round["headers"]
    _, todo_id = payroll_round["slips"][0]

    done = client.patch(f"/api/v1/todos/{todo_id}",
                        json={"status": "cancelled"}, headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "cancelled"
    assert done.json()["data"]["completed_at"] is None
    assert client.get(f"/api/v1/audit-logs?action=todo.cancelled&entity_id={todo_id}",
                      headers=headers).json()["meta"]["total"] == 1


def test_completing_a_todo_still_records_that_it_was_done(payroll_round: dict) -> None:
    """The behaviour the new status must not disturb."""
    client, headers = payroll_round["client"], payroll_round["headers"]
    _, todo_id = payroll_round["slips"][0]
    done = client.patch(f"/api/v1/todos/{todo_id}",
                        json={"status": "completed"}, headers=headers).json()["data"]
    assert done["status"] == "completed" and done["completed_at"] is not None
    assert client.get(f"/api/v1/audit-logs?action=todo.completed&entity_id={todo_id}",
                      headers=headers).json()["meta"]["total"] == 1


def test_both_halves_of_the_cleanup_are_taught_where_they_apply() -> None:
    """The server only closes todos on the fact it is certain of — the target
    was deleted. The other two paths are text, and text that is not included is
    not read: the filer needs to know a void is theirs to clean up, and the flow
    agent needs the sweep for documents retired by STATUS, which no server can
    recognize because the state names belong to the tenant."""
    from app.services.provisioning import PRODUCT_SKILLS_DIR

    void = "{{include:_common/leave-no-orphan-work.md}}"
    sweep = "{{include:_common/stale-todo-sweep.md}}"

    files = sorted(PRODUCT_SKILLS_DIR.glob("*/SKILL.md"))
    retires = [p.parent.name for p in files
               if p.parent.name.endswith("-submit")
               or p.parent.name in ("oryh-payroll", "oryh-payables", "oryh-receivables")]
    flows = [p.parent.name for p in files if p.parent.name.endswith("-approval-flow")]
    from app.core.entity_types import HOSTED_DRIVABLE_ENTITY_TYPES

    assert len(retires) >= 8, retires
    # one per hosted-drivable family, or none in the export that withholds them
    assert len(flows) in (0, len(HOSTED_DRIVABLE_ENTITY_TYPES)), flows

    for name in retires:
        assert void in (PRODUCT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8"), name
    for name in flows:
        assert sweep in (PRODUCT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8"), name

    # both must say the word that keeps the queue history honest
    for fragment in ("leave-no-orphan-work.md", "stale-todo-sweep.md"):
        text = (PRODUCT_SKILLS_DIR / "_common" / fragment).read_text(encoding="utf-8")
        assert "cancelled" in text and "completed" in text, fragment

    # and payroll must now teach the path that was missing entirely
    payroll = (PRODUCT_SKILLS_DIR / "oryh-payroll" / "SKILL.md").read_text(encoding="utf-8")
    assert "被退回之后" in payroll and "修原单，不要作废重做" in payroll
