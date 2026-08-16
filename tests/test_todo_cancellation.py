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


def test_returning_a_document_closes_the_approval_todos_of_that_round(orphan) -> None:
    """HKG-015. An approver returned a timesheet and his own round-1 approval
    todo stayed open. The console then showed one Open approval todo beside two
    completed ones — which reads as a queue still waiting on him — on a document
    whose round had already moved on and which had no assignment at all.

    A returned document goes back to its submitter. Nobody should still be
    holding an open approval todo on it, and that is the same certainty
    `cancel_todos_for` was written for: there the subject was gone, here the
    round is.
    """
    client, key, inv, todo = orphan
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)

    returned = client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "returned", "approver_role": "workflow-admin",
        "comment": "退回修改：项目归属不对",
    }, headers=key)
    assert returned.status_code == 201, returned.text

    row = client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]
    assert row["status"] == "cancelled", "the round is over; the approval work is not pending"
    # cancelled, never completed — the approver did not do this work, he returned it
    assert row["completed_at"] is None
    assert row["completed_by"] is None


def test_a_return_leaves_work_that_is_not_about_deciding(orphan) -> None:
    """The document still exists, so only the approval work ends. A todo like
    "attach the receipt" is exactly what the submitter now has to do."""
    client, key, inv, _todo = orphan
    # A different person: `todos_open_entity_assignee_uk` reserves one OPEN todo
    # per employee per record, so parallel sign-off works — and so does "the
    # approver is deciding while the submitter still owes an attachment".
    submitter = client.post("/api/v1/employees", json={"name": "小李"},
                            headers=key).json()["data"]["id"]
    chore = client.post("/api/v1/todos", json={
        "employee_id": submitter, "entity_type": "invoice", "entity_id": inv,
        "title": "补发票附件", "todo_type": "task"}, headers=key)
    assert chore.status_code == 201, chore.text
    chore = chore.json()["data"]["id"]
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)

    client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "returned", "approver_role": "workflow-admin",
    }, headers=key)

    assert client.get(f"/api/v1/todos/{chore}", headers=key).json()["data"]["status"] == "open"


def test_an_approval_that_decides_leaves_the_other_todos_alone(orphan) -> None:
    """Only `returned` ends the round this way. An `approved` fact is one node
    passing, and the next node's todo may already exist."""
    client, key, inv, todo = orphan
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)

    client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "approved", "approver_role": "manager",
    }, headers=key)

    assert client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]["status"] == "open"


def test_editing_a_line_lands_on_the_document_it_changes(orphan) -> None:
    """HKG-015 step 1, as behaviour rather than as a grep.

    `tests/test_write_audit.py` proves the call is in the code. This proves it
    executes, and — the part that mattered in production — that the row lands on
    the DOCUMENT. Auditing under the line's own id would mean already knowing
    which lines to ask about, which is exactly what an investigation does not
    know: reading the header's trail is how anyone starts.
    """
    client, key, inv, _todo = orphan
    line = client.post("/api/v1/invoice-items", json={
        "invoice_id": inv, "product_name_snapshot": "咨询费",
        "quantity": 1, "unit_price": 100.0,
    }, headers=key)
    assert line.status_code == 201, line.text
    line_id = line.json()["data"]["id"]

    edited = client.patch(f"/api/v1/invoice-items/{line_id}",
                          json={"product_name_snapshot": "咨询费（改）"}, headers=key)
    assert edited.status_code == 200, edited.text

    trail = client.get(
        f"/api/v1/audit-logs?entity_type=invoice&entity_id={inv}", headers=key
    ).json()["data"]
    actions = [row["action"] for row in trail]
    assert "invoice.line_added" in actions, actions
    assert "invoice.line_changed" in actions, actions

    changed = next(row for row in trail if row["action"] == "invoice.line_changed")
    assert changed["detail"]["line_id"] == line_id
    # the FIELDS, not their values: the trail says what moved, and a payslip
    # line's numbers do not belong in a log with a wider audience than the
    # document itself
    assert changed["detail"]["fields"] == ["product_name_snapshot"]
    assert "咨询费（改）" not in str(changed["detail"])


def _approver_key(client, key, employee_id: str, email: str) -> dict:
    """A user-bound key for the person the todo is assigned to.

    `$oryh-approve` runs as "the approver's own agent", so the credential
    resolves to a user and through them to an employee. The bootstrap key the
    fixture carries is a tenant SERVICE key with no employee behind it — it owns
    no todo, and completes none, which is the whole reason these tests need a
    different credential than the ones above.
    """
    invited = client.post("/api/v1/auth/invitations", json={
        "email": email, "role": "admin", "employee_id": employee_id,
    }, headers=key)
    assert invited.status_code == 201, invited.text
    invitation = invited.json()["data"]
    # An invited user is not active, and an inactive user cannot hold a key —
    # `POST /tenant/api-keys` answers 409 "user is not active". The console
    # email backend hands the one-time token back in the response so a test does
    # not need an outbox; SMTP omits it, which is why production never sees it.
    token = invitation["invitation_url"].rsplit("token=", 1)[1]
    accepted = client.post("/api/v1/auth/invitations/accept",
                           json={"token": token, "password": "approver-pass1"})
    assert accepted.status_code == 200, accepted.text
    issued = client.post("/api/v1/tenant/api-keys", json={
        "label": "approver", "user_id": invitation["id"],
    }, headers=key)
    assert issued.status_code == 201, issued.text
    return {"X-API-Key": issued.json()["data"]["plain_text_api_key"]}

def test_deciding_a_node_completes_the_deciders_own_todo(orphan) -> None:
    """Recording the decision and closing the todo that asked for it were two
    calls with no transaction between them. Neither could lose or duplicate the
    decision — the fact goes first and the natural key makes a retry idempotent
    — but the second one going missing stalls the flow: the document only goes
    back to the workflow admin once the todo is done, and nothing said it had
    not been.
    """
    client, key, inv, todo = orphan
    assignee = client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]["employee_id"]
    approver = _approver_key(client, key, assignee, "zhang@cancel-co.example")
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)

    decided = client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "approved", "approver_role": "manager", "comment": "金额与凭证一致",
    }, headers=approver)
    assert decided.status_code == 201, decided.text

    row = client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]
    assert row["status"] == "completed"
    # completed, not cancelled: the work WAS done, and a queue history that
    # cannot tell the two apart cannot answer what a person actually did
    assert row["completed_at"] is not None
    assert row["completed_by"] is not None


def test_the_skills_fourth_step_still_works_against_a_closed_todo(orphan) -> None:
    """`PATCH /todos/{id}` stays in `$oryh-approve` step 4 and stays idempotent,
    so an agent that has not been updated gets a completed todo back rather than
    an error."""
    client, key, inv, todo = orphan
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)
    client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "approved", "approver_role": "manager",
    }, headers=key)

    again = client.patch(f"/api/v1/todos/{todo}", json={"status": "completed"}, headers=key)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["status"] == "completed"


def test_commenting_settles_nothing_and_leaves_the_todo_open(orphan) -> None:
    """An objection that decides nothing may sit beside a decision — so the node
    is still undecided, and the todo asking about it is still work."""
    client, key, inv, todo = orphan
    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)
    client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "commented", "approver_role": "manager", "comment": "第三行的税率存疑",
    }, headers=key)

    assert client.get(f"/api/v1/todos/{todo}", headers=key).json()["data"]["status"] == "open"


def test_a_parallel_signers_todo_is_left_alone(orphan) -> None:
    """`todos_open_entity_assignee_uk` is per EMPLOYEE, which is what makes
    parallel sign-off work — so one person deciding must not close the other's
    seat."""
    client, key, inv, mine = orphan
    assignee = client.get(f"/api/v1/todos/{mine}", headers=key).json()["data"]["employee_id"]
    approver = _approver_key(client, key, assignee, "zhang2@cancel-co.example")
    other = client.post("/api/v1/employees", json={"name": "小王"},
                        headers=key).json()["data"]["id"]
    theirs = client.post("/api/v1/todos", json={
        "employee_id": other, "entity_type": "invoice", "entity_id": inv,
        "title": "会签", "todo_type": "approval"}, headers=key)
    assert theirs.status_code == 201, theirs.text
    theirs = theirs.json()["data"]["id"]

    client.post(f"/api/v1/invoices/{inv}/submit", json={}, headers=key)
    client.post("/api/v1/approval-records", json={
        "entity_type": "invoice", "entity_id": inv, "round_no": 1, "sequence_no": 2,
        "action": "approved", "approver_role": "manager",
    }, headers=approver)

    assert client.get(f"/api/v1/todos/{mine}", headers=key).json()["data"]["status"] == "completed"
    assert client.get(f"/api/v1/todos/{theirs}", headers=key).json()["data"]["status"] == "open"
