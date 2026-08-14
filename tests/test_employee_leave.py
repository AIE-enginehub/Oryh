"""请假, and the balance that is deliberately not stored anywhere.

The design claim under test: a leave balance is not a fact. It is what the
workspace's published rules imply about a person today, and the rules change —
so the server keeps the absences and the policy, and an agent does the
arithmetic. What that buys is the thing a ledger cannot do: revise the policy
and every answer, including about the past, is correct immediately, with no
data to migrate and no correcting entries.

These tests therefore assert two kinds of thing. That the FACTS behave like
every other document family — file, submit, approve, separation of duties. And
that no balance ever gets written down, because the moment one is, the design
is gone and nobody would notice from the endpoints alone.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


def post(client, headers, path, body, expect=(200, 201)):
    response = client.post(f"/api/v1{path}", json=body, headers=headers)
    assert response.status_code in expect, (path, response.status_code, response.text)
    return response.json()["data"] if response.status_code < 400 else response


@pytest.fixture()
def workspace(client: TestClient) -> dict:
    data = provision_tenant(client, company_name="Leave Co", email="admin@leave-co.com",
                            password="leave-pass1234")
    root = {"X-API-Key": data["plain_text_api_key"]}
    staff = post(client, root, "/employees",
                 {"name": "王小明", "hire_date": "2019-03-01"})["id"]
    return {"client": client, "root": root, "staff": staff}


def file_leave(workspace, **overrides):
    body = {
        "employee_id": workspace["staff"], "leave_type": "annual",
        "from_date": "2026-03-02", "thru_date": "2026-03-06", "duration_days": 3,
        "reason": "回老家",
    }
    body.update(overrides)
    return workspace["client"].post("/api/v1/employee-leaves", json=body,
                                    headers=workspace["root"])


def test_a_leave_request_is_filed_submitted_and_approved(workspace: dict) -> None:
    client, root = workspace["client"], workspace["root"]
    filed = file_leave(workspace)
    assert filed.status_code == 201, filed.text
    leave = filed.json()["data"]
    assert leave["status"] == "draft" and leave["duration_days"] == 3.0

    submitted = client.post(f"/api/v1/employee-leaves/{leave['id']}/submit", headers=root)
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "submitted"

    # /submit records the opening fact itself, like every other family
    trail = client.get(
        f"/api/v1/approval-records?entity_type=employee_leave&entity_id={leave['id']}",
        headers=root,
    ).json()["data"]
    assert [r["action"] for r in trail] == ["submitted"]

    approved = client.patch(f"/api/v1/employee-leaves/{leave['id']}",
                            json={"status": "approved"}, headers=root)
    assert approved.status_code == 200, approved.text


def test_half_days_are_the_point_of_the_decimal(workspace: dict) -> None:
    """请假以天为单位，但可以有小数。An 上午请半天 is the ordinary case, not an
    edge one."""
    half = file_leave(workspace, from_date="2026-03-02", thru_date="2026-03-02",
                      duration_days=0.5)
    assert half.status_code == 201, half.text
    assert half.json()["data"]["duration_days"] == 0.5

    zero = file_leave(workspace, duration_days=0)
    assert zero.status_code == 422


def test_the_server_never_derives_the_length_from_the_dates(workspace: dict) -> None:
    """Whether the Saturday inside 周五到周一 counts is the tenant's rule, so
    the agent computes the figure and the server records what was agreed. A
    server that subtracted the dates would be quietly overruling the policy."""
    filed = file_leave(workspace, from_date="2026-03-06", thru_date="2026-03-09",
                       duration_days=2)
    assert filed.status_code == 201, filed.text
    # four calendar days, two working days, and the server keeps the two
    assert filed.json()["data"]["duration_days"] == 2.0


def test_a_backwards_period_is_refused(workspace: dict) -> None:
    backwards = file_leave(workspace, from_date="2026-03-06", thru_date="2026-03-02")
    assert backwards.status_code == 422
    assert "from_date" in backwards.json()["detail"]


def test_the_leave_type_comes_from_the_tenant_vocabulary(workspace: dict) -> None:
    """Which kinds of leave exist is local — 陪产假 and 丧假 vary by workspace
    and their length by province — so it is a type-option family, not a
    constrained column."""
    client, root = workspace["client"], workspace["root"]
    shipped = {row["name"] for row in client.get(
        "/api/v1/type-options?family=leave_type", headers=root).json()["data"]}
    assert {"annual", "sick", "personal", "compensatory"} <= shipped

    assert file_leave(workspace, leave_type="not_a_leave_type").status_code == 422

    client.post("/api/v1/type-options",
                json={"family": "leave_type", "name": "study", "title": "进修假"},
                headers=root)
    assert file_leave(workspace, leave_type="study").status_code == 201


def test_nothing_anywhere_stores_a_balance(workspace: dict) -> None:
    """The load-bearing negative. If an allowance ever appears — on the request,
    on the employee, as an endpoint — the design has quietly become a ledger,
    and every stored number will outlive the rule that produced it."""
    client, root = workspace["client"], workspace["root"]
    leave = file_leave(workspace).json()["data"]
    employee = client.get(f"/api/v1/employees/{workspace['staff']}",
                          headers=root).json()["data"]

    forbidden = ("balance", "entitlement", "allowance", "remaining", "accrual", "quota")
    for field in list(leave) + list(employee):
        assert not any(word in field.lower() for word in forbidden), field

    # …and there is no endpoint offering one
    assert client.get(f"/api/v1/employees/{workspace['staff']}/leave-balance",
                      headers=root).status_code == 404


def test_the_facts_a_balance_is_computed_from_are_all_reachable(workspace: dict) -> None:
    """The other side of that negative: refusing to store it is only defensible
    if the three inputs are each one call away."""
    client, root = workspace["client"], workspace["root"]

    # 1. 工龄 — the employee carries a hire date
    employee = client.get(f"/api/v1/employees/{workspace['staff']}",
                          headers=root).json()["data"]
    assert employee["hire_date"] == "2019-03-01"

    # 2. the rules, as they stood on a chosen date
    policy = post(client, root, "/policies", {
        "code": "HR-002", "category": "hr", "title": "员工请假管理制度",
        "body": "# 年假\n满 5 年 10 天。", "rules_json": {"annual": {"tier_5y": 10}},
    })
    client.post(f"/api/v1/policies/{policy['id']}/publish",
                json={"effective_from": "2026-01-01"}, headers=root)
    in_force = client.get(
        "/api/v1/policies?category=hr&status=published&in_force_on=2026-06-15",
        headers=root).json()["data"]
    assert in_force[0]["rules_json"] == {"annual": {"tier_5y": 10}}

    # 3. the absences, including anything straddling the window's edge
    file_leave(workspace, from_date="2025-12-29", thru_date="2026-01-02",
               duration_days=3)
    file_leave(workspace, from_date="2026-06-01", thru_date="2026-06-01",
               duration_days=1)
    in_2026 = client.get(
        f"/api/v1/employee-leaves?employee_id={workspace['staff']}"
        "&overlapping_from=2026-01-01&overlapping_thru=2026-12-31",
        headers=root).json()["data"]
    # the New Year straddle appears — dropping it would understate the year
    assert len(in_2026) == 2


def test_cancelling_refunds_nothing_because_nothing_was_deducted(workspace: dict) -> None:
    """The quiet payoff of a computed balance. A ledger would need a reversing
    entry here; this needs the row to stop matching the query."""
    client, root = workspace["client"], workspace["root"]
    leave = file_leave(workspace).json()["data"]
    client.post(f"/api/v1/employee-leaves/{leave['id']}/submit", headers=root)

    def counted() -> float:
        rows = client.get(
            f"/api/v1/employee-leaves?employee_id={workspace['staff']}&leave_type=annual"
            "&overlapping_from=2026-01-01&overlapping_thru=2026-12-31",
            headers=root).json()["data"]
        return sum(r["duration_days"] for r in rows
                   if r["status"] in ("submitted", "approved"))

    assert counted() == 3.0
    client.patch(f"/api/v1/employee-leaves/{leave['id']}",
                 json={"status": "cancelled"}, headers=root)
    assert counted() == 0.0
    # the record itself survives: an approver's decision is not erased
    assert client.get(f"/api/v1/employee-leaves/{leave['id']}",
                      headers=root).json()["data"]["status"] == "cancelled"


def test_in_flight_requests_count_so_the_same_days_cannot_be_spent_twice(
    workspace: dict,
) -> None:
    """There is no server-side hold. Counting `submitted` rows IS the
    protection, so the query that finds them has to return them."""
    client, root = workspace["client"], workspace["root"]
    first = file_leave(workspace).json()["data"]
    client.post(f"/api/v1/employee-leaves/{first['id']}/submit", headers=root)
    second = file_leave(workspace, from_date="2026-04-01", thru_date="2026-04-02",
                        duration_days=2).json()["data"]
    client.post(f"/api/v1/employee-leaves/{second['id']}/submit", headers=root)

    rows = client.get(
        f"/api/v1/employee-leaves?employee_id={workspace['staff']}&status=submitted",
        headers=root).json()["data"]
    assert sum(r["duration_days"] for r in rows) == 5.0


def test_a_member_files_their_own_and_cannot_approve_it(workspace: dict) -> None:
    """Same separation every family has: `leave.submit_own` files and submits;
    moving past submitted needs `leave.advance`, which a member does not hold."""
    from app.services.emails import outbox

    client, root = workspace["client"], workspace["root"]
    user_id = client.post("/api/v1/auth/invitations",
                          json={"email": "wang@leave-co.com", "role": "member",
                                "employee_id": workspace["staff"]},
                          headers=root).json()["data"]["id"]
    token = next(line.rsplit("token=", 1)[1].strip()
                 for line in outbox.messages[-1].body.splitlines() if "token=" in line)
    client.post("/api/v1/auth/invitations/accept",
                json={"token": token, "password": "member-pass1"})
    member = {"X-API-Key": client.post(
        "/api/v1/tenant/api-keys", json={"label": "wang", "user_id": user_id},
        headers=root).json()["data"]["plain_text_api_key"]}

    filed = client.post("/api/v1/employee-leaves", json={
        "employee_id": workspace["staff"], "leave_type": "annual",
        "from_date": "2026-05-01", "thru_date": "2026-05-01", "duration_days": 1,
    }, headers=member)
    assert filed.status_code == 201, filed.text
    leave_id = filed.json()["data"]["id"]
    assert client.post(f"/api/v1/employee-leaves/{leave_id}/submit",
                       headers=member).status_code == 200

    self_approved = client.patch(f"/api/v1/employee-leaves/{leave_id}",
                                 json={"status": "approved"}, headers=member)
    assert self_approved.status_code == 403
    assert "leave.advance" in self_approved.json()["detail"]


def test_leave_joins_the_shared_document_plumbing(workspace: dict) -> None:
    """Registering the family rather than hand-rolling a table is what makes
    todos, approval facts, the object console and the workflow definition work
    without a line of leave-specific code."""
    client, root = workspace["client"], workspace["root"]
    leave = file_leave(workspace).json()["data"]

    # the builtin machine was provisioned and is ENFORCED — proving it by the
    # transition it refuses is worth more than reading a definition row back
    illegal = client.patch(f"/api/v1/employee-leaves/{leave['id']}",
                           json={"status": "taken"}, headers=root)
    assert illegal.status_code == 409, illegal.text
    assert "'draft' -> 'taken'" in illegal.json()["detail"]

    todo = client.post("/api/v1/todos", json={
        "employee_id": workspace["staff"], "entity_type": "employee_leave",
        "entity_id": leave["id"], "title": "审批请假", "todo_type": "approval",
    }, headers=root)
    assert todo.status_code == 201, todo.text

    directory = {row["object_type"] for row in client.get(
        "/api/v1/object-directory", headers=root).json()["data"]}
    assert "employee_leave" in directory


@pytest.mark.skipif(
    not (__import__("pathlib").Path(__file__).resolve().parents[1]
         / "scripts" / "seed_demo.py").exists(),
    reason="demo seed is not part of the open-core tree",
)
def test_the_demo_seed_can_actually_answer_how_many_days_are_left() -> None:
    """The seed is the only place the whole claim is demonstrable end to end, so
    it is worth pinning that its parts still fit together.

    A balance needs three things and is unanswerable without any of them: a
    published policy carrying the tiers, a hire date to measure 工龄 from, and
    leave rows in states that distinguish 已批 from 在途. The seed used to
    provide none of them — there were no policies in it at all.

    Read out of the source rather than by seeding: this asserts the demo data
    is coherent, not that Postgres works."""
    import ast
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in
        ("leave_policy", "leave")
    ]
    policies = [c for c in calls if c.func.attr == "leave_policy"]
    leaves = [c for c in calls if c.func.attr == "leave"]

    # both demo tenants, or the balance is unanswerable in one of them
    assert len(policies) == 2, "each demo tenant needs its own published leave policy"
    assert len(leaves) >= 8, len(leaves)

    # the tiers an agent applies must be machine-readable, not only prose
    assert text.count('"statutory"') == 2
    assert '"company_bonus"' in text

    # 已批 and 在途 must BOTH appear, or the in-flight subtraction — the whole
    # protection against spending the same days twice — is never exercised
    stages = {kw.value.value for call in leaves for kw in call.keywords
              if kw.arg == "stage" and isinstance(kw.value, ast.Constant)}
    assert {"approved", "submitted", "returned", "cancelled", "taken"} <= stages, stages

    # everybody gets a hire date, so 工龄 is never a shrug
    assert "hire_date = (NOW - timedelta(days=months * 30)).date()" in text
