"""A todo can be cancelled, and the shipped schema has to agree.

For the life of the product it could not. `schemas.TodoStatus` listed
`cancelled`, `cancel_todos_for` wrote it, and Postgres carried
`check (status in ('open','completed'))` from the baseline migration. The model
declared no CHECK on the column, so SQLite — which builds from the model — had
no constraint, and the whole suite passed over a value the real database
refused.

The cost was not only that nobody could cancel a todo. Deleting a document
cancels its open todos in the same transaction, so **deleting any document that
had an open todo was a 500**, and the document survived. The fix for orphaned
todos took document deletion down with it, in every real environment, invisibly
to the tests.

These tests exist at two levels because one of them alone would have missed it:
the behaviour, and the agreement between the model and the DDL that ships.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.entity_types import TODO_STATUSES
from app.db.session import Base
from app.models import Todo
from app.schemas import TodoStatus

from conftest import provision_tenant


def _model_constraint() -> str:
    for constraint in Base.metadata.tables[Todo.__tablename__].constraints:
        if constraint.name == "todos_status_chk":
            return str(constraint.sqltext)
    raise AssertionError("the model declares no todos_status_chk")


def test_the_model_declares_the_status_vocabulary() -> None:
    """The missing declaration is the whole bug. Without it SQLite has no
    constraint, and a test database with no constraint cannot disagree with
    anything."""
    text = _model_constraint()
    for value in TODO_STATUSES:
        assert f"'{value}'" in text, f"{value} missing from the model's CHECK"


def test_the_api_vocabulary_and_the_model_are_the_same_list() -> None:
    """They were two lists. `schemas.TodoStatus` said cancelled and the
    database did not, and nothing compared them."""
    assert set(TodoStatus.__args__) == set(TODO_STATUSES)


def test_the_shipped_ddl_allows_every_status_the_api_accepts() -> None:
    """`sql/schema.sql` is what a new environment gets. It carried the narrow
    constraint, so a fresh deployment would have reproduced the bug exactly."""
    snapshot = (pathlib.Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
                ).read_text(encoding="utf-8")
    match = re.search(r"CONSTRAINT todos_status_chk CHECK \(\((.*?)\)\)", snapshot, re.S)
    assert match, "todos_status_chk is absent from the shipped schema"
    for value in TODO_STATUSES:
        assert f"'{value}'" in match.group(1), (
            f"the shipped DDL refuses {value!r}; regenerate sql/schema.sql"
        )


@pytest.fixture()
def orphan(client):
    """An invoice with an open todo on it — the shape that could not be
    deleted."""
    ctx = provision_tenant(client, company_name="Cancel Co", email="admin@cancel-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    emp = client.post("/api/v1/employees", json={"name": "小张"},
                      headers=key).json()["data"]["id"]
    cust = client.post("/api/v1/customers", json={"name": "客户"},
                       headers=key).json()["data"]["id"]
    inv = client.post("/api/v1/invoices", json={
        "direction": "sales", "employee_id": emp, "customer_id": cust,
        "title": "货款", "total_amount": 100.0}, headers=key).json()["data"]["id"]
    todo = client.post("/api/v1/todos", json={
        "employee_id": emp, "entity_type": "invoice", "entity_id": inv,
        "title": "审批发票", "todo_type": "approval"}, headers=key).json()["data"]["id"]
    return client, key, inv, todo


def test_a_todo_can_be_cancelled(orphan) -> None:
    client, key, _inv, todo = orphan
    response = client.patch(f"/api/v1/todos/{todo}", json={"status": "cancelled"},
                            headers=key)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "cancelled"


def test_cancelling_does_not_claim_the_work_was_done(orphan) -> None:
    """`cancelled` leaves the completion columns null on purpose: a queue
    history that cannot tell a cancellation from a completion cannot answer
    what a person actually did."""
    client, key, _inv, todo = orphan
    client.patch(f"/api/v1/todos/{todo}", json={"status": "cancelled"}, headers=key)
    row = client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]
    assert row["completed_at"] is None
    assert row["completed_by"] is None


def test_deleting_a_document_with_an_open_todo_works(orphan) -> None:
    """The regression this actually caused. `delete_document` cancels the open
    todos in the same transaction, so the refused value took the delete with
    it — a 500, and the document still there."""
    client, key, inv, todo = orphan
    deleted = client.delete(f"/api/v1/invoices/{inv}", headers=key)
    assert deleted.status_code == 204, deleted.text

    assert client.get(f"/api/v1/invoices/{inv}", headers=key).status_code == 404
    assert client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]["status"] == (
        "cancelled"
    )
