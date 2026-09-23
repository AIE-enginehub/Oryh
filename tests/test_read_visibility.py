"""A person reads their own documents, what was routed to them, and nothing
else — unless reading everyone's is their job.

The sweep is the point of this file: member A files one document in every
personal family, and member B — same role, same workspace — asks EVERY GET
route the API has, lists and ids alike. Any response that carries one of A's
ids or A's marker text is a leak, whichever endpoint it came from, including
ones written after this test. (app/api/visibility.py)
"""

from __future__ import annotations

import re

import pytest

from conftest import invite_member, make_client, provision_tenant

MEMBER = ["timesheet.submit_own", "leave.submit_own", "expense.submit_own", "purchase.submit_own",
          "quotation.submit_own", "order.submit_own", "approval.record", "todos.complete_own", "crm.own"]
MARK = "ZQX-ALICE-ONLY"


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Private Co", email="admin@private.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def employee(name: str) -> str:
            return client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]

        alice_emp, bob_emp, boss_emp = employee("Alice"), employee("Bob"), employee("Boss")
        alice = invite_member(client, admin, "alice", MEMBER, employee_id=alice_emp)
        bob = invite_member(client, admin, "bob", MEMBER, employee_id=bob_emp)
        boss = invite_member(client, admin, "boss", ["approval.record", "todos.complete_own"], employee_id=boss_emp)
        customer = client.post("/api/v1/customers", json={"name": "Shared Customer"}, headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Shared Product", "product_code": "SP-1"},
                              headers=admin).json()["data"]["id"]
        project = client.post("/api/v1/projects", json={"name": "Shared Project"}, headers=admin)
        project_id = project.json()["data"]["id"] if project.status_code == 201 else None

        def filed(who: dict, emp: str, mark: str) -> dict[str, str]:
            """One document per family, filed by the person as themselves."""
            ids: dict[str, str] = {}

            def post(path: str, body: dict, key: str) -> dict:
                r = client.post(f"/api/v1{path}", json=body, headers=who)
                assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text[:300]}"
                data = r.json()["data"]
                ids[key] = data["id"]
                return data

            sheet = post("/timesheet-headers", {"employee_id": emp, "period_start": "2026-09-14", "period_end": "2026-09-20",
                                                "entries": [{"work_date": "2026-09-15", "hours": 8, "notes": mark}]}, "timesheet")
            if sheet.get("entries"):
                ids["timesheet_entry"] = sheet["entries"][0]["id"]
            post("/employee-leaves", {"employee_id": emp, "leave_type": "annual", "from_date": "2026-10-01",
                                      "thru_date": "2026-10-02", "duration_days": 2, "reason": mark}, "leave")
            claim = post("/expense-claims", {"employee_id": emp, "title": mark,
                                             "items": [{"expense_date": "2026-09-10", "category": "travel", "amount": 120,
                                                        "notes": mark}]}, "expense")
            if claim.get("items"):
                ids["expense_item"] = claim["items"][0]["id"]
            request = post("/purchase-requests", {"employee_id": emp, "title": mark,
                                                  "items": [{"product_name_snapshot": mark, "quantity": 1, "unit_price": 10}]}, "purchase")
            if request.get("items"):
                ids["purchase_item"] = request["items"][0]["id"]
            quote = post("/sales-quotations", {"employee_id": emp, "customer_id": customer, "title": mark,
                                               "items": [{"product_id": product, "quantity": 1, "unit_price": 10}]}, "quotation")
            ids["quotation_item"] = quote["items"][0]["id"]
            order = post("/sales-orders", {"employee_id": emp, "customer_id": customer, "title": mark,
                                           "items": [{"product_id": product, "quantity": 1, "unit_price": 10}]}, "order")
            ids["order_item"] = order["items"][0]["id"]
            post("/leads", {"employee_id": emp, "contact_name": mark, "company_name": mark}, "lead")
            post("/opportunities", {"employee_id": emp, "customer_id": customer, "title": mark}, "opportunity")
            post("/activities", {"employee_id": emp, "activity_type": "call", "subject": mark, "content": mark,
                                 "occurred_at": "2026-09-15T08:00:00Z", "opportunity_id": ids["opportunity"]}, "activity")
            return ids

        yield {"client": client, "admin": admin, "alice": alice, "bob": bob, "boss": boss,
               "alice_emp": alice_emp, "bob_emp": bob_emp, "boss_emp": boss_emp,
               "alice_ids": filed(alice, alice_emp, MARK), "bob_ids": filed(bob, bob_emp, "BOB-OWN")}


def _routes(client) -> list[str]:
    spec = client.get("/openapi.json").json()
    return sorted(path for path, item in spec["paths"].items() if "get" in item and path.startswith("/api/v1/"))


def _leaks(client, who: dict, secret_ids: set[str]) -> list[str]:
    """Ask every GET route; paths with an id are asked once per secret id."""
    leaks = []
    for path in _routes(client):
        params = re.findall(r"{([^}]+)}", path)
        if len(params) > 1:
            continue  # nested ids (attachment content) are reached through their parent, covered by its 404
        targets = [path] if not params else [path.replace("{" + params[0] + "}", sid) for sid in secret_ids]
        for url in targets:
            r = client.get(url, headers=who)
            if r.status_code != 200:
                continue
            text = r.text
            hit = [sid for sid in secret_ids if sid in text]
            if MARK in text or (hit and not params) or (params and hit):
                leaks.append(f"{url.removeprefix('/api/v1')} -> {'marker' if MARK in text else hit[0][:8]}")
    return leaks


def test_a_colleague_cannot_read_my_documents_through_any_get_route(office) -> None:
    secret = set(office["alice_ids"].values())
    leaks = _leaks(office["client"], office["bob"], secret)
    assert not leaks, "Bob can read Alice's documents:\n  " + "\n  ".join(leaks)


def test_the_sweep_can_see_a_leak_when_there_is_one(office) -> None:
    """The same walk with a credential that MAY read everything finds Alice's
    rows all over the API — so an empty result above means hidden, not unasked."""
    found = _leaks(office["client"], office["admin"], set(office["alice_ids"].values()))
    assert len(found) >= 25, found


def test_i_still_read_my_own(office) -> None:
    c, alice, ids = office["client"], office["alice"], office["alice_ids"]
    for path, key in (("/timesheet-headers", "timesheet"), ("/employee-leaves", "leave"), ("/expense-claims", "expense"),
                      ("/purchase-requests", "purchase"), ("/sales-quotations", "quotation"), ("/sales-orders", "order"),
                      ("/leads", "lead"), ("/opportunities", "opportunity"), ("/activities", "activity")):
        listed = c.get(f"/api/v1{path}", headers=alice).json()["data"]
        assert [row["id"] for row in listed] == [ids[key]], f"{path}: mine and only mine"
        assert c.get(f"/api/v1{path}/{ids[key]}", headers=alice).status_code == 200
        assert c.get(f"/api/v1{path}/{ids[key]}", headers=office["bob"]).status_code == 404, \
            f"{path}: a row I may not read does not exist for me"
    lines = c.get("/api/v1/sales-order-items", headers=alice).json()["data"]
    assert [row["id"] for row in lines] == [ids["order_item"]], "lines follow their document"


def test_the_workspace_key_and_the_admin_read_everything(office) -> None:
    c = office["client"]
    assert len(c.get("/api/v1/expense-claims", headers=office["admin"]).json()["data"]) == 2


def test_what_is_routed_to_me_i_can_read_and_only_that(office) -> None:
    c, admin, boss = office["client"], office["admin"], office["boss"]
    claim = office["alice_ids"]["expense"]
    assert c.get(f"/api/v1/expense-claims/{claim}", headers=boss).status_code == 404
    todo = c.post("/api/v1/todos", headers=admin, json={
        "employee_id": office["boss_emp"], "entity_type": "expense_claim", "entity_id": claim, "title": "审批报销"})
    assert todo.status_code == 201, todo.text
    assert c.get(f"/api/v1/expense-claims/{claim}", headers=boss).status_code == 200, "a todo on it is the routing"
    assert [r["id"] for r in c.get("/api/v1/expense-claims", headers=boss).json()["data"]] == [claim]
    assert [r["id"] for r in c.get("/api/v1/expense-items", headers=boss).json()["data"]] == [office["alice_ids"]["expense_item"]]
    assert c.get(f"/api/v1/expense-claims/{office['bob_ids']['expense']}", headers=boss).status_code == 404
    recorded = c.post("/api/v1/approval-records", headers=boss, json={
        "entity_type": "expense_claim", "entity_id": claim, "action": "approved", "comment": "ok", "sequence_no": 2})
    assert recorded.status_code == 201, recorded.text
    c.patch(f"/api/v1/todos/{todo.json()['data']['id']}", headers=boss, json={"status": "done"})
    assert c.get(f"/api/v1/expense-claims/{claim}", headers=boss).status_code == 200, \
        "having decided it, the approver can still look at what they decided"
    # Alice sees the approval on her own claim; Bob sees no approval facts about it
    assert len(c.get("/api/v1/approval-records", headers=office["alice"], params={"entity_id": claim}).json()["data"]) == 1
    assert c.get("/api/v1/approval-records", headers=office["bob"], params={"entity_id": claim}).json()["data"] == []
    # todos: mine, not my colleague's
    assert c.get("/api/v1/todos", headers=office["bob"]).json()["data"] == []
    assert len(c.get("/api/v1/todos", headers=boss).json()["data"]) == 1


@pytest.mark.parametrize("grant,path,key", [
    ("timesheet.read_all", "/timesheet-headers", "timesheet"),
    ("leave.read_all", "/employee-leaves", "leave"),
    ("expense.read_all", "/expense-claims", "expense"),
    ("purchase.read_all", "/purchase-requests", "purchase"),
    ("quotation.read_all", "/sales-quotations", "quotation"),
    ("order.read_all", "/sales-orders", "order"),
    ("crm.read_all", "/opportunities", "opportunity"),
    # a desk that cannot work blind reads the family without being told twice
    ("expense.advance", "/expense-claims", "expense"),
    ("payment.record", "/expense-claims", "expense"),
    ("shipment.manage", "/sales-orders", "order"),
    ("invoice.manage:sales", "/sales-orders", "order"),
    ("purchase_order.manage", "/purchase-requests", "purchase"),
    ("tenant.act_for_any_employee", "/timesheet-headers", "timesheet"),
])
def test_reading_everyones_is_a_grant(office, grant, path, key) -> None:
    c = office["client"]
    emp = c.post("/api/v1/employees", json={"name": "Desk"}, headers=office["admin"]).json()["data"]["id"]
    desk = invite_member(c, office["admin"], "desk" + re.sub(r"[^a-z]", "", grant), [grant], employee_id=emp)
    rows = c.get(f"/api/v1{path}", headers=desk).json()["data"]
    assert {office["alice_ids"][key], office["bob_ids"][key]} <= {row["id"] for row in rows}, grant
    other = "/employee-leaves" if path != "/employee-leaves" else "/timesheet-headers"
    if grant != "tenant.act_for_any_employee" and not (grant == "invoice.manage:sales"):
        assert c.get(f"/api/v1{other}", headers=desk).json()["data"] == [], f"{grant} reads its family, not the others"


def test_the_capabilities_exist_and_member_does_not_hold_them() -> None:
    from app.api.visibility import READ_ALL_CAPABILITIES
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, SYSTEM_CAPABILITY_NAMES

    assert set(READ_ALL_CAPABILITIES) <= SYSTEM_CAPABILITY_NAMES
    assert not set(READ_ALL_CAPABILITIES) & set(DEFAULT_ROLE_PERMISSIONS["member"])
    assert set(READ_ALL_CAPABILITIES) <= set(DEFAULT_ROLE_PERMISSIONS["admin"])


def test_the_trail_of_a_record_follows_the_record(office) -> None:
    """`GET /audit-logs?entity_type=&entity_id=` lets a member read one named
    record's history — no wider than their read of the record itself."""
    c, ids = office["client"], office["alice_ids"]
    for entity_type, key in (("expense_claim", "expense"), ("expense_item", "expense_item"), ("timesheet_header", "timesheet"),
                             ("sales_order", "order"), ("sales_order_item", "order_item"), ("employee_leave", "leave"),
                             ("opportunitie", "opportunity"), ("opportunity", "opportunity"), ("activitie", "activity")):
        q = {"entity_type": entity_type, "entity_id": ids[key]}
        assert c.get("/api/v1/audit-logs", headers=office["bob"], params=q).status_code == 404, entity_type
        mine = c.get("/api/v1/audit-logs", headers=office["alice"], params=q)
        assert mine.status_code == 200, entity_type
        if entity_type != "opportunity":  # the listener spells it `opportunitie`; the alias must still be gated
            assert mine.json()["data"], entity_type
