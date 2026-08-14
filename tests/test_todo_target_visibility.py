"""`?include=target` has to agree with the target's own detail endpoint.

A production invoice was deleted and its approval todo stayed open. The list
went on describing the target as though nothing had happened — status and all —
while `GET /invoices/{id}` answered 404. An agent following the check-in reads
the list, fetches the target, and gets nothing, with no way to tell a deletion
from an outage; an operator scanning for orphans has no query at all.

`missing` could not carry this. It fired for two of the three non-document
target types whose rows were sitting there perfectly readable, so it was
already crying wolf before a real orphan existed.
"""

from __future__ import annotations

import pytest

from conftest import provision_tenant


@pytest.fixture()
def setup(client):
    ctx = provision_tenant(client)
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    employee = client.post(
        "/api/v1/employees",
        json={"name": "Orphan Owner", "email": "owner@test-co.example"},
        headers=key,
    ).json()["data"]
    customer = client.post(
        "/api/v1/customers", json={"name": "Acme"}, headers=key
    ).json()["data"]
    return client, key, employee, customer


def _todo_target(client, key, todo_id: str) -> dict:
    listed = client.get("/api/v1/todos?status=open&include=target", headers=key)
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["data"] if r["id"] == todo_id]
    assert rows, "the todo vanished from its own list"
    return rows[0]["target"]


def test_a_deleted_target_says_so_instead_of_looking_alive(setup) -> None:
    client, key, employee, customer = setup
    invoice = client.post(
        "/api/v1/invoices",
        json={"direction": "sales", "employee_id": employee["id"],
              "customer_id": customer["id"], "title": "货款",
              "total_amount": 5000.0},
        headers=key,
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["data"]["id"]

    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee["id"], "entity_type": "invoice",
            "entity_id": invoice_id, "title": "审批发票", "todo_type": "approval",
        },
        headers=key,
    )
    assert todo.status_code == 201, todo.text
    todo_id = todo.json()["data"]["id"]

    assert _todo_target(client, key, todo_id)["deleted"] is False

    assert client.delete(f"/api/v1/invoices/{invoice_id}", headers=key).status_code == 204
    # deleting cancels the open todo, which is the behaviour that stops NEW
    # orphans. Reopen it to stand in for the ones that predate that rule —
    # the state this flag exists to make visible.
    reopened = client.patch(
        f"/api/v1/todos/{todo_id}", json={"status": "open"}, headers=key
    )
    assert reopened.status_code == 200, reopened.text

    assert client.get(f"/api/v1/invoices/{invoice_id}", headers=key).status_code == 404

    target = _todo_target(client, key, todo_id)
    assert target["deleted"] is True, "the list still describes a deleted target as live"
    assert target["missing"] is False, "the row exists; `missing` means no row at all"


def test_a_project_target_is_not_reported_as_missing(setup) -> None:
    """It was. `TODO_TARGET_MODELS` covers document families only, so every
    todo on a project came back `missing: true` with the project right there."""
    client, key, employee, customer = setup
    project = client.post(
        "/api/v1/projects", json={"project_name": "Bridge"}, headers=key
    )
    assert project.status_code == 201, project.text

    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee["id"], "entity_type": "project",
            "entity_id": project.json()["data"]["id"], "title": "整理项目资料",
            "todo_type": "task",
        },
        headers=key,
    )
    assert todo.status_code == 201, todo.text

    target = _todo_target(client, key, todo.json()["data"]["id"])
    assert target["missing"] is False
    assert target["title"] == "Bridge"
    assert target["status"] == "active"


def test_an_approval_target_is_not_reported_as_missing(setup) -> None:
    """Same defect, second type: an approval_target is a BusinessObject reached
    by a different verb, and the branch keyed only on `business_object`."""
    client, key, employee, customer = setup
    created = client.post(
        "/api/v1/approval-targets",
        json={"target_type": "contract_review", "title": "年度框架协议",
              "summary": "年度采购框架", "payload": {"no": "C-1"},
              "source_text": "合同正文"},
        headers=key,
    )
    assert created.status_code == 201, created.text

    todo = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee["id"], "entity_type": "approval_target",
            "entity_id": created.json()["data"]["id"], "title": "审阅合同",
            "todo_type": "approval",
        },
        headers=key,
    )
    assert todo.status_code == 201, todo.text

    target = _todo_target(client, key, todo.json()["data"]["id"])
    assert target["missing"] is False
    assert target["title"] == "年度框架协议"


def test_creating_a_todo_on_a_deleted_document_is_still_refused(setup) -> None:
    """The other half of why an orphan cannot be created today. Making the
    read honest must not be mistaken for making the write permissive."""
    client, key, employee, customer = setup
    invoice_id = client.post(
        "/api/v1/invoices",
        json={"direction": "sales", "employee_id": employee["id"],
              "customer_id": customer["id"], "title": "货款",
              "total_amount": 5000.0},
        headers=key,
    ).json()["data"]["id"]
    assert client.delete(f"/api/v1/invoices/{invoice_id}", headers=key).status_code == 204

    refused = client.post(
        "/api/v1/todos",
        json={
            "employee_id": employee["id"], "entity_type": "invoice",
            "entity_id": invoice_id, "title": "审批发票", "todo_type": "approval",
        },
        headers=key,
    )
    assert refused.status_code == 404, refused.text
