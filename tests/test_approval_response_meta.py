"""A decision's response says what it did, so nothing has to be re-read.

An approver's agent, told by its person to "verify after approving", re-read
the todo list and the trail after every decision — three calls for a fact
the transaction already guaranteed. The 201 now carries `meta` with the todo
it closed and the document's status; the skill says that is the check.
"""

from __future__ import annotations

from conftest import make_client, provision_tenant


def test_the_decision_response_names_the_todo_it_closed_and_the_status() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Meta Co", email="admin@meta.example")
        key = {"X-API-Key": t["plain_text_api_key"]}
        owner = client.post("/api/v1/employees", json={"name": "提交人"}, headers=key).json()["data"]["id"]
        header = client.post(
            "/api/v1/timesheet-headers", headers=key,
            json={"employee_id": owner, "period_start": "2026-06-01", "period_end": "2026-06-07",
                  "entries": [{"work_date": "2026-06-01", "hours": 8, "task": "x"}]},
        ).json()["data"]["id"]
        assert client.post(f"/api/v1/timesheet-headers/{header}/submit", json={}, headers=key).status_code == 200

        # the service key owns no employee, so it owns no todo to close
        decided = client.post("/api/v1/approval-records", headers=key, json={
            "entity_type": "timesheet_header", "entity_id": header,
            "round_no": 1, "sequence_no": 2, "action": "approved",
        })
        assert decided.status_code == 201, decided.text
        assert decided.json()["meta"] == {"completed_todo_ids": [], "document_status": "submitted"}

        # a returned decision with the transition inline reports the new status
        returned = client.post("/api/v1/approval-records", headers=key, json={
            "entity_type": "timesheet_header", "entity_id": header,
            "round_no": 1, "sequence_no": 3, "action": "returned", "comment": "fix the task text",
            "document_status": "returned",
        })
        assert returned.status_code == 201, returned.text
        assert returned.json()["meta"]["document_status"] == "returned"
