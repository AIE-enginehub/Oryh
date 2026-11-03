"""State names are the workspace's vocabulary. Every state the server reads is
found by role or by its place in the machine, so renaming one moves nothing.
"""

from __future__ import annotations

import json

from conftest import make_client, provision_tenant

YEAR = {"period_start": "2026-01-01", "period_end": "2026-12-31"}


def _workspace(c, name: str) -> dict:
    t = provision_tenant(c, company_name=name, email=f"owner@{name.lower()}.example")
    return {"X-API-Key": t["plain_text_api_key"]}


def _rename(c, admin: dict, object_type: str, renames: dict[str, str], roles: dict[str, str] | None = None) -> None:
    rows = c.get("/api/v1/object-type-definitions", headers=admin, params={"object_type": object_type}).json()["data"]
    row = next(r for r in rows if r["object_type"] == object_type)
    text = json.dumps(row["state_machine"])
    for old, new in renames.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    machine = json.loads(text)
    if roles:
        machine["roles"] = {**machine.get("roles", {}), **roles}
    changed = c.patch(f"/api/v1/object-type-definitions/{row['id']}", headers=admin, json={"state_machine": machine})
    assert changed.status_code == 200, changed.text


def test_a_budget_in_the_workspaces_own_words_still_takes_tags_and_closes() -> None:
    with make_client([]) as c:
        admin = _workspace(c, "Budgetwords")
        _rename(c, admin, "budget", {"active": "in_force", "closed": "wound_up"},
                {"active": "in_force", "closed": "wound_up"})
        employee = c.post("/api/v1/employees", headers=admin, json={"name": "E"}).json()["data"]["id"]
        budget = c.post("/api/v1/budgets", headers=admin, json={
            "name": "b", **YEAR, "lines": [{"line_code": "OFF", "name": "office", "category": "office"}]}).json()["data"]
        moved = c.patch(f"/api/v1/budgets/{budget['id']}", headers=admin, json={"status": "in_force"})
        assert moved.status_code == 200, moved.text
        assert moved.json()["data"]["activated_at"], "activation is the role, whatever it is called"

        def claim():
            return c.post("/api/v1/expense-claims", headers=admin, json={
                "employee_id": employee, "title": "x", "items": [{
                    "expense_date": "2026-03-05", "amount": 10, "category": "office",
                    "budget_line_id": budget["lines"][0]["id"]}]})

        assert claim().status_code == 201, claim().text
        closed = c.post(f"/api/v1/budgets/{budget['id']}/close", headers=admin, json={})
        assert closed.status_code == 200, closed.text
        refused = claim()
        assert refused.status_code == 422 and "wound_up" in refused.text


def test_a_renamed_dead_quotation_is_still_dead_and_a_renamed_accepted_one_is_not() -> None:
    with make_client([]) as c:
        admin = _workspace(c, "Quotewords")
        _rename(c, admin, "sales_quotation", {"expired": "lapsed", "accepted": "agreed"}, {"accepted": "agreed"})
        employee = c.post("/api/v1/employees", headers=admin, json={"name": "E"}).json()["data"]["id"]
        customer = c.post("/api/v1/customers", headers=admin, json={"name": "C"}).json()["data"]["id"]

        def order_against(state: str):
            quotation = c.post("/api/v1/sales-quotations", headers=admin, json={
                "employee_id": employee, "customer_id": customer, "title": state, "status": state}).json()["data"]
            return c.post("/api/v1/sales-orders", headers=admin, json={
                "employee_id": employee, "customer_id": customer, "title": "o", "quotation_id": quotation["id"]})

        lapsed = order_against("lapsed")
        assert lapsed.status_code == 409 and "lapsed" in lapsed.text
        agreed = order_against("agreed")
        assert agreed.status_code == 201, agreed.text


def test_a_bank_line_links_the_state_that_leads_to_paid_whatever_it_is_called(monkeypatch) -> None:
    from app.services import treasury

    machine = {"initial": "draft", "states": ["draft", "submitted", "cleared", "paid", "void"],
               "transitions": {"draft": ["submitted"], "submitted": ["cleared"], "cleared": ["paid"], "paid": ["void"]},
               "editable_states": ["draft"]}
    monkeypatch.setattr(treasury, "get_builtin_machine", lambda db, tenant_id, object_type: machine)
    assert treasury.linkable_payment_states(None, "t") == {"cleared", "paid"}
