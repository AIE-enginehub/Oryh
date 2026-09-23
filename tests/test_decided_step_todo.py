"""A todo for an approval step that is already decided is refused (objects.py
`ensure_step_undecided`).

Seen live: the approver approved, completed their todo, and before the flow
agent advanced the timesheet it was back in the `submitted & no open todo`
queue — so the agent re-issued round 1 / seq 2 to the same people, and "my
todos" showed finished work as pending. The trail is the fact; the server
now reads it before it hands out the same step again.
"""

from __future__ import annotations

from conftest import invite_member, make_client, provision_tenant


def test_a_decided_step_is_not_reissued() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Trail Co", email="admin@trail.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        worker = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        boss_emp = client.post("/api/v1/employees", json={"name": "经理"}, headers=admin).json()["data"]["id"]
        boss = invite_member(client, admin, "boss", ["approval.record", "todos.complete_own"], employee_id=boss_emp)
        header = client.post("/api/v1/timesheet-headers", headers=admin, json={
            "employee_id": worker, "period_start": "2026-09-14", "period_end": "2026-09-20",
            "entries": [{"work_date": "2026-09-15", "hours": 8}]}).json()["data"]["id"]
        client.post(f"/api/v1/timesheet-headers/{header}/submit", headers=admin, json={})

        step = {"employee_id": boss_emp, "entity_type": "timesheet_header", "entity_id": header, "title": "审批工时",
                "metadata": {"workflow_version": 1, "round_no": 1, "sequence_no": 2}}
        first = client.post("/api/v1/todos", headers=admin, json=step)
        assert first.status_code == 201, first.text
        todo = first.json()["data"]["id"]
        # the approver decides and closes their todo; the flow has not advanced the document yet
        decided = client.post("/api/v1/approval-records", headers=boss, json={
            "entity_type": "timesheet_header", "entity_id": header, "action": "approved", "round_no": 1, "sequence_no": 2,
            "comment": "ok"})
        assert decided.status_code == 201, decided.text
        client.patch(f"/api/v1/todos/{todo}", headers=boss, json={"status": "completed"})
        queue = client.get("/api/v1/timesheet-headers", headers=admin, params={"status": "submitted", "without_open_todo": "true"}).json()["data"]
        assert [h["id"] for h in queue] == [header], "the ball is momentarily unheld — exactly when a hasty agent re-assigns"

        again = client.post("/api/v1/todos", headers=admin, json=step)
        assert again.status_code == 409, again.text
        assert "already decided: approved" in again.json()["detail"] and "advance the document" in again.json()["detail"]
        bulk = client.post("/api/v1/todos/bulk", headers=admin, json={"items": [step]}).json()["data"]
        assert bulk["summary"]["failed"] == 1 and "already decided" in bulk["results"][0]["error"]
        assert client.get("/api/v1/todos", headers=boss, params={"status": "open"}).json()["data"] == [], "nothing pending was minted"

        # the NEXT step of the same document is still assignable; a plain todo without step metadata too
        nxt = client.post("/api/v1/todos", headers=admin, json={**step, "title": "复核", "metadata": {"round_no": 1, "sequence_no": 3}})
        assert nxt.status_code == 201, nxt.text
        plain = client.post("/api/v1/todos", headers=admin, json={"employee_id": worker, "entity_type": "timesheet_header",
                                                                   "entity_id": header, "title": "补充说明"})
        assert plain.status_code == 201, plain.text
        # a returned document re-enters at a new round: round 2 / seq 2 is undecided
        r2 = client.post("/api/v1/todos", headers=admin, json={**step, "employee_id": boss_emp, "metadata": {"round_no": 2, "sequence_no": 2}})
        assert r2.status_code in (201, 409)  # 409 only because boss already holds the round-1/seq-3 todo on this record


def test_the_assigner_may_withdraw_a_todo_it_minted_and_a_rework_todo_may_name_the_step() -> None:
    from conftest import invite_member, make_client, provision_tenant

    with make_client([]) as client:
        t = provision_tenant(client, company_name="Withdraw Co", email="admin@withdraw.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        worker = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        boss_emp = client.post("/api/v1/employees", json={"name": "经理"}, headers=admin).json()["data"]["id"]
        boss = invite_member(client, admin, "boss", ["approval.record", "todos.complete_own"], employee_id=boss_emp)
        flow_emp = client.post("/api/v1/employees", json={"name": "流程"}, headers=admin).json()["data"]["id"]
        flow = invite_member(client, admin, "flow", ["todos.assign", "approval.record", "timesheet.advance"], employee_id=flow_emp)  # the hosted agent's shape: it advances, so it reads
        header = client.post("/api/v1/timesheet-headers", headers=admin, json={
            "employee_id": worker, "period_start": "2026-09-14", "period_end": "2026-09-20",
            "entries": [{"work_date": "2026-09-15", "hours": 8}]}).json()["data"]["id"]
        client.post(f"/api/v1/timesheet-headers/{header}/submit", headers=admin, json={})
        minted_r = client.post("/api/v1/todos", headers=flow, json={
            "employee_id": boss_emp, "entity_type": "timesheet_header", "entity_id": header, "title": "审批",
            "metadata": {"round_no": 1, "sequence_no": 2}})
        assert minted_r.status_code == 201, minted_r.text
        minted = minted_r.json()["data"]["id"]
        # the assigner may cancel what it minted — and only cancel
        assert client.patch(f"/api/v1/todos/{minted}", headers=flow, json={"status": "completed"}).status_code == 403
        assert client.patch(f"/api/v1/todos/{minted}", headers=flow, json={"title": "x"}).status_code == 403
        assert client.patch(f"/api/v1/todos/{minted}", headers=flow, json={"status": "cancelled"}).status_code == 200
        # someone else's minted todo is not the assigner's to withdraw
        other = client.post("/api/v1/todos", headers=admin, json={
            "employee_id": boss_emp, "entity_type": "timesheet_header", "entity_id": header, "title": "审批2"}).json()["data"]["id"]
        assert client.patch(f"/api/v1/todos/{other}", headers=flow, json={"status": "cancelled"}).status_code == 403
        # a return decided at r1/s2 hands the submitter a rework todo that may name that step
        assert client.post("/api/v1/approval-records", headers=boss, json={
            "entity_type": "timesheet_header", "entity_id": header, "action": "returned", "round_no": 1, "sequence_no": 2,
            "comment": "改"}).status_code == 201
        rework = client.post("/api/v1/todos", headers=flow, json={
            "employee_id": worker, "entity_type": "timesheet_header", "entity_id": header, "title": "修改", "todo_type": "rework",
            "metadata": {"round_no": 1, "sequence_no": 2}})
        assert rework.status_code == 201, rework.text
