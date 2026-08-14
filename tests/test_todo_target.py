"""`GET /todos?include=target` — the todo list carries its own context.

The my-work check-in used to spend one detail call per todo to learn who a
document belongs to, what it is worth, and where its approval stands — the
only part of the briefing that grew with how busy the person was, at one
agent turn (~12s) per todo. The summary answers the same questions in the
list response, from a fixed number of batched reads.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import provision_tenant as bootstrap_tenant


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Todo Co", email="admin@todo-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(f"/api/v1{path}", json=body, headers=headers)
    assert response.status_code in (200, 201), f"{path}: {response.text}"
    return response.json()["data"]


def todo_for(client: TestClient, headers: dict, employee_id: str, entity_type: str, entity_id: str) -> str:
    return post(client, headers, "/todos", {
        "employee_id": employee_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": f"处理 {entity_type}",
    })["id"]


def targets_by_type(client: TestClient, headers: dict, employee_id: str) -> dict[str, dict]:
    response = client.get(
        f"/api/v1/todos?employee_id={employee_id}&status=open&include=target", headers=headers
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert all("target" in row for row in rows), rows
    return {row["entity_type"]: row["target"] for row in rows}


def test_todo_targets_answer_what_the_detail_calls_used_to(client: TestClient) -> None:
    headers = provision(client)
    approver = post(client, headers, "/employees", {"name": "审批人"})["id"]
    owner = post(client, headers, "/employees", {"name": "王小明"})["id"]

    header_id = post(client, headers, "/timesheet-headers", {
        "employee_id": owner, "period_start": "2026-06-01", "period_end": "2026-06-07",
    })["id"]
    for day, hours in (("2026-06-01", 8), ("2026-06-02", 6.5)):
        post(client, headers, "/timesheet-entries", {
            "header_id": header_id, "employee_id": owner, "work_date": day, "hours": hours,
        })

    claim_id = post(client, headers, "/expense-claims", {
        "employee_id": owner, "title": "出差报销",
    })["id"]
    for amount in (120, 80.5):
        post(client, headers, "/expense-items", {
            "claim_id": claim_id, "employee_id": owner,
            "expense_date": "2026-06-03", "amount": amount,
        })
    post(client, headers, f"/expense-claims/{claim_id}/submit", {})
    post(client, headers, "/approval-records", {
        "entity_type": "expense_claim", "entity_id": claim_id,
        "action": "approved", "sequence_no": 2, "approver_id": approver, "comment": "票据齐全",
    })

    object_id = post(client, headers, "/business-objects", {
        "object_type": "daily_report", "title": "周一日报", "payload": {},
    })["id"]

    for entity_type, entity_id in (
        ("timesheet_header", header_id),
        ("expense_claim", claim_id),
        ("business_object", object_id),
    ):
        todo_for(client, headers, approver, entity_type, entity_id)

    targets = targets_by_type(client, headers, approver)

    # timesheet: whose week, how many hours — summed from entries
    sheet = targets["timesheet_header"]
    assert sheet["employee_name"] == "王小明"
    assert sheet["amount"] == 14.5 and sheet["unit"] == "hours"
    assert "2026-06-01" in sheet["title"]

    # expense claim: whose, how much, and where the approval stands
    claim = targets["expense_claim"]
    assert claim["employee_name"] == "王小明"
    assert claim["amount"] == 200.5 and claim["unit"] == "amount"
    assert claim["status"] == "submitted"
    assert claim["approval_count"] >= 1
    last = claim["last_approval"]
    assert last["action"] == "approved"
    assert last["approver_name"] == "审批人"
    assert last["comment"] == "票据齐全"

    # a flow agent's approval carries a service label, not an employee id —
    # postgres refuses to cast it to uuid, so it must never reach the
    # employee lookup (this passed on sqlite and 500ed on the real stack)
    post(client, headers, "/approval-records", {
        "entity_type": "expense_claim", "entity_id": claim_id,
        "action": "commented", "approver_id": "workflow-admin", "sequence_no": 2,
    })
    refreshed = targets_by_type(client, headers, approver)["expense_claim"]
    assert refreshed["last_approval"]["approver_name"] == "workflow-admin"

    # a quotation whose header total was never set still gets a number — the
    # real briefing could not price a deal because the total lived on the
    # lines (found by the measurement run, on live data)
    customer = post(client, headers, "/customers", {"name": "蓝湾零售"})["id"]
    quotation = post(client, headers, "/sales-quotations", {
        "employee_id": owner, "customer_id": customer, "title": "驻场报价",
    })
    post(client, headers, "/sales-quotation-items", {
        "quotation_id": quotation["id"], "product_name_snapshot": "顾问",
        "quantity": 2, "unit_price": 1500, "amount": 3000,
    })
    todo_for(client, headers, approver, "sales_quotation", quotation["id"])
    quote_target = targets_by_type(client, headers, approver)["sales_quotation"]
    assert quote_target["amount"] == 3000.0, quote_target

    # business objects report their own object_type, not the todo's word for it
    report = targets["business_object"]
    assert report["object_type"] == "daily_report"
    assert report["title"] == "周一日报"


def test_dangling_and_unrequested_targets(stack) -> None:
    """A todo cannot be created pointing at nothing (the server 404s), so a
    dangling target only arises when the document goes away afterwards. The
    summary says `missing` instead of erroring the whole list."""
    from sqlalchemy.orm import Session

    from app.models import ExpenseClaim

    client, engine = stack
    headers = provision(client)
    someone = post(client, headers, "/employees", {"name": "小李"})["id"]
    claim_id = post(client, headers, "/expense-claims", {
        "employee_id": someone, "title": "会消失的报销",
    })["id"]
    todo_for(client, headers, someone, "expense_claim", claim_id)

    # hard-delete underneath the todo — the API only soft-deletes, so this is
    # the only way a target can truly vanish. Through the ORM, because the Uuid
    # column stores dashless on sqlite and raw SQL with dashes matches nothing.
    with Session(engine) as session:
        session.delete(session.get(ExpenseClaim, claim_id))
        session.commit()

    targets = targets_by_type(client, headers, someone)
    assert targets["expense_claim"]["missing"] is True

    # without include=target the shape is exactly what it was before
    plain = client.get(f"/api/v1/todos?employee_id={someone}&status=open", headers=headers)
    assert plain.status_code == 200
    assert all("target" not in row for row in plain.json()["data"])

    # an unknown include value is refused, not ignored
    assert client.get(
        f"/api/v1/todos?employee_id={someone}&include=everything", headers=headers
    ).status_code == 422
