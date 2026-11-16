"""Inside a project — plan docs/plans/project-management-2026-11-15.md, phase 1.

The server holds a project's work to its shape: tasks form a tree inside one
project, dependencies never loop, a timesheet entry's task is one of its
project's, a milestone is reached with a confirmer and stays put while the
invoice that billed it stands. It schedules nothing. The figures — hours
against plan, milestones on time or late — are derived on every read.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def project():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Build Co", email="owner@build-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, who: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=who or admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        site = ok(call("POST", "projects", {"project_name": "Warehouse fit-out", "project_code": "WH-1"}))["id"]
        other = ok(call("POST", "projects", {"project_name": "Office move", "project_code": "OF-1"}))["id"]

        def task(name: str, **extra) -> dict:
            return ok(call("POST", "project-tasks", {"project_id": extra.pop("project_id", site), "name": name,
                                                      **extra}))

        yield dict(c=c, admin=admin, call=call, ok=ok, site=site, other=other, task=task)


def test_tasks_form_a_tree_inside_one_project(project) -> None:
    p = project
    phase = p["task"]("Fit-out", task_code="1")
    racking = p["task"]("Racking", task_code="1.1", parent_task_id=phase["id"], planned_hours=40)
    taken = p["call"]("POST", "project-tasks", {"project_id": p["site"], "name": "x", "task_code": "1.1"})
    assert taken.status_code == 409, "a task code is unique within its project"
    elsewhere = p["call"]("POST", "project-tasks", {"project_id": p["other"], "name": "x", "parent_task_id": phase["id"]})
    assert elsewhere.status_code == 422 and "parent's project" in elsewhere.text
    loop = p["call"]("PATCH", f"project-tasks/{phase['id']}", {"parent_task_id": racking["id"]})
    assert loop.status_code == 422 and "under itself" in loop.text
    unknown = p["call"]("POST", "project-tasks", {"project_id": p["site"], "name": "x", "status": "half_done"})
    assert unknown.status_code == 422 and "project_task_status" in unknown.text


def test_dependencies_are_facts_that_never_loop(project) -> None:
    p = project
    design, build, test = (p["task"](name) for name in ("Design", "Build", "Test"))
    p["ok"](p["call"]("POST", "project-task-dependencies",
                      {"predecessor_task_id": design["id"], "successor_task_id": build["id"]}))
    p["ok"](p["call"]("POST", "project-task-dependencies",
                      {"predecessor_task_id": build["id"], "successor_task_id": test["id"], "lag_days": 2}))
    loop = p["call"]("POST", "project-task-dependencies",
                     {"predecessor_task_id": test["id"], "successor_task_id": design["id"]})
    assert loop.status_code == 422 and "loop" in loop.text
    across = p["call"]("POST", "project-task-dependencies", {
        "predecessor_task_id": design["id"], "successor_task_id": p["task"]("x", project_id=p["other"])["id"]})
    assert across.status_code == 422
    listed = p["ok"](p["call"]("GET", "project-task-dependencies", project_id=p["site"]), 200)
    assert len(listed) == 2
    held = p["call"]("DELETE", f"project-tasks/{build['id']}")
    assert held.status_code == 409 and "cancelled" in held.text


def test_the_person_assigned_states_how_their_task_stands_and_nothing_else(project) -> None:
    p = project
    invited = invite_member(p["c"], p["admin"], "member", [], email="w@build-co.example", employee="Worker")
    me = invited.employee_id
    worker = {"X-API-Key": invited["X-API-Key"]}
    mine = p["task"]("Racking", assignee_employee_id=me, planned_end="2026-03-31")
    theirs = p["task"]("Lighting")
    started = p["ok"](p["call"]("PATCH", f"project-tasks/{mine['id']}",
                                {"actual_start": "2026-03-02", "status": "in_progress"}, who=worker), 200)
    assert (started["actual_start"], started["status"]) == ("2026-03-02", "in_progress")
    replanned = p["call"]("PATCH", f"project-tasks/{mine['id']}", {"planned_end": "2026-04-30"}, who=worker)
    assert replanned.status_code == 403 and "planned_end" in replanned.text
    assert p["call"]("PATCH", f"project-tasks/{theirs['id']}", {"status": "done"}, who=worker).status_code == 403
    assert p["call"]("POST", "project-tasks", {"project_id": p["site"], "name": "x"}, who=worker).status_code == 403
    assert len(p["ok"](p["call"]("GET", "project-tasks", who=worker, project_id=p["site"]), 200)) == 2


def test_hours_are_counted_per_task_and_roll_up(project) -> None:
    p = project
    phase = p["task"]("Fit-out")
    racking = p["task"]("Racking", parent_task_id=phase["id"], planned_hours=40)
    p["task"]("Lighting", parent_task_id=phase["id"], planned_hours=10)
    foreign = p["task"]("Packing", project_id=p["other"])
    employee = p["ok"](p["call"]("POST", "employees", {"name": "Fitter"}))["id"]

    def timesheet(week: tuple[str, str], entries: list[dict], submit: bool = True) -> None:
        header = p["ok"](p["call"]("POST", "timesheet-headers", {"employee_id": employee, "period_start": week[0],
                                                                "period_end": week[1]}))["id"]
        for entry in entries:
            p["ok"](p["call"]("POST", "timesheet-entries", {"header_id": header, "employee_id": employee,
                                                            "work_date": week[0], **entry}))
        if submit:
            p["ok"](p["call"]("POST", f"timesheet-headers/{header}/submit", {}), 200)

    wrong = p["call"]("POST", "timesheet-headers", {"employee_id": employee, "period_start": "2026-03-09",
                                                    "period_end": "2026-03-15"})
    header = p["ok"](wrong)["id"]
    crossed = p["call"]("POST", "timesheet-entries", {"header_id": header, "employee_id": employee, "hours": 1,
                                                      "work_date": "2026-03-10", "project_id": p["site"],
                                                      "task_id": foreign["id"]})
    assert crossed.status_code == 422 and "another project" in crossed.text
    timesheet(("2026-03-02", "2026-03-08"), [{"hours": 8, "project_id": p["site"], "task_id": racking["id"]},
                                             {"hours": 2, "project_id": p["site"]}])
    timesheet(("2026-03-16", "2026-03-22"), [{"hours": 5, "project_id": p["site"], "task_id": racking["id"]}],
              submit=False)
    figures = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", as_of="2026-03-31"), 200)
    rows = {row["name"]: row for row in figures["tasks"]}
    assert (rows["Racking"]["planned_hours"], rows["Racking"]["recorded_hours"]) == (40.0, 8.0), "a draft is not counted"
    assert (rows["Fit-out"]["summary"], rows["Fit-out"]["planned_hours"], rows["Fit-out"]["recorded_hours"]) == \
        (True, 50.0, 8.0)
    assert figures["hours"] == {"planned": 50.0, "recorded": 10.0, "recorded_on_no_task": 2.0}


def test_a_milestone_is_reached_with_a_confirmer_and_stays_put_once_billed(project) -> None:
    p = project
    first = p["ok"](p["call"]("POST", "project-milestones", {"project_id": p["site"], "name": "Racking accepted",
                                                            "due_date": "2026-03-31"}))
    p["ok"](p["call"]("POST", "project-milestones", {"project_id": p["site"], "name": "Handover",
                                                     "due_date": "2026-04-30"}))
    reached = p["ok"](p["call"]("POST", f"project-milestones/{first['id']}/reach",
                                {"reached_on": "2026-04-03", "confirmed_by": "Li Wei (customer)"}), 200)
    assert (reached["status"], reached["confirmed_by"]) == ("reached", "Li Wei (customer)")

    clerk = p["ok"](p["call"]("POST", "employees", {"name": "Clerk"}))["id"]
    customer = p["ok"](p["call"]("POST", "customers", {"name": "Huaxin"}))["id"]

    def invoice(project_id: str | None) -> dict:
        row = p["ok"](p["call"]("POST", "invoices", {"direction": "sales", "employee_id": clerk, "customer_id": customer,
                                                     "title": "Milestone 1", "total_amount": 50000,
                                                     "project_id": project_id}))
        p["ok"](p["call"]("POST", f"invoices/{row['id']}/submit", {}), 200)
        return row

    stray = p["call"]("PATCH", f"project-milestones/{first['id']}", {"invoice_id": invoice(None)["id"]})
    assert stray.status_code == 422 and "does not bill this project" in stray.text
    billed = invoice(p["site"])
    issued = p["call"]("PATCH", f"invoices/{billed['id']}", {"status": "issued"})
    assert issued.status_code == 200, issued.text
    p["ok"](p["call"]("PATCH", f"project-milestones/{first['id']}", {"invoice_id": billed["id"]}), 200)
    moved = p["call"]("POST", f"project-milestones/{first['id']}/reach", {"reached_on": "2026-03-30"})
    assert moved.status_code == 409 and "fixed" in moved.text
    assert p["call"]("POST", f"project-milestones/{first['id']}/reopen").status_code == 409

    figures = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", as_of="2026-05-05"), 200)
    assert figures["milestone_standing"] == {"reached_late": 1, "overdue": 1}


def test_a_milestones_clause_is_one_of_its_projects_contract(project) -> None:
    p = project
    customer = p["ok"](p["call"]("POST", "customers", {"name": "Huaxin"}))["id"]
    contract = p["ok"](p["call"]("POST", "contracts", {"title": "Fit-out", "side": "sales", "customer_id": customer}))
    term = p["ok"](p["call"]("POST", "contract-terms", {"contract_id": contract["id"], "term_type": "payment_terms",
                                                        "content": "30% on acceptance of the racking"}))["id"]
    orphan = p["call"]("POST", "project-milestones", {"project_id": p["site"], "name": "x", "due_date": "2026-03-31",
                                                      "contract_term_id": term})
    assert orphan.status_code == 422 and "another contract" in orphan.text
    p["ok"](p["call"]("PATCH", f"projects/{p['site']}", {"contract_id": contract["id"]}), 200)
    p["ok"](p["call"]("POST", "project-milestones", {"project_id": p["site"], "name": "Racking", "due_date": "2026-03-31",
                                                     "contract_term_id": term}))


def test_the_integrity_audit_finds_a_projects_work_whole(project) -> None:
    import pathlib

    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    p = project
    p["task"]("Racking", parent_task_id=p["task"]("Fit-out")["id"])
    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    checks = dict(namespace["STRUCTURAL_CHECKS"])
    names = ("project tasks under a parent of another project",
             "timesheet entries counted against a task of another project",
             "project issues about a task of another project")
    db = next(app.dependency_overrides[get_db]())
    try:
        assert {name: db.execute(sql_text(checks[name])).scalar() for name in names} == dict.fromkeys(names, 0)
    finally:
        db.close()


# --- phase 2: issues, status reports, the money -----------------------------------


def test_anyone_on_the_project_raises_an_issue_and_a_resolved_one_says_how(project) -> None:
    p = project
    invited = invite_member(p["c"], p["admin"], "member", [], email="i@build-co.example", employee="Inspector")
    worker = {"X-API-Key": invited["X-API-Key"]}
    racking = p["task"]("Racking")
    raised = p["ok"](p["call"]("POST", "project-issues", {
        "project_id": p["site"], "task_id": racking["id"], "issue_type": "risk", "severity": "high",
        "title": "Anchor bolts late"}, who=worker))
    assert raised["issue_no"].startswith("PI-") and raised["raised_by_employee_id"] == invited.employee_id
    assert raised["status"] == "open"
    unknown = p["call"]("POST", "project-issues", {"project_id": p["site"], "title": "x", "severity": "dire"})
    assert unknown.status_code == 422 and "project_issue_severity" in unknown.text
    elsewhere = p["call"]("POST", "project-issues", {"project_id": p["other"], "title": "x", "task_id": racking["id"]})
    assert elsewhere.status_code == 422 and "another project" in elsewhere.text
    silent = p["call"]("PATCH", f"project-issues/{raised['id']}", {"resolved_at": "2026-03-20T10:00:00Z"}, who=worker)
    assert silent.status_code == 422 and "resolution" in silent.text
    resolved = p["ok"](p["call"]("PATCH", f"project-issues/{raised['id']}", {
        "resolved_at": "2026-03-20T10:00:00Z", "resolution": "Second supplier delivered", "status": "resolved"},
        who=worker), 200)
    assert resolved["status"] == "resolved"
    someone_elses = p["ok"](p["call"]("POST", "project-issues", {"project_id": p["site"], "title": "Dust"}))
    assert p["call"]("PATCH", f"project-issues/{someone_elses['id']}", {"severity": "low"},
                     who=worker).status_code == 403
    figures = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution"), 200)
    assert figures["issues"]["unresolved"] == 1
    assert figures["issues"]["by_status"] == {"resolved": 1, "open": 1}
    assert len(p["ok"](p["call"]("GET", "project-issues", who=worker, project_id=p["site"], unresolved="true"),
                       200)) == 1


def test_a_published_report_keeps_its_words_and_figures_and_a_correction_is_a_revision(project) -> None:
    p = project
    p["ok"](p["call"]("POST", "project-milestones", {"project_id": p["site"], "name": "Racking accepted",
                                                     "due_date": "2026-03-04"}))
    week = {"project_id": p["site"], "period_start": "2026-03-02", "period_end": "2026-03-08"}
    draft = p["ok"](p["call"]("POST", "project-reports", {**week, "health": "amber", "summary": "Bolts late"}))
    assert (draft["revision"], draft["status"]) == (1, "draft")
    assert p["call"]("POST", "project-reports", {**week, "health": "green", "summary": "x"}).status_code == 409
    p["ok"](p["call"]("PATCH", f"project-reports/{draft['id']}", {"blockers": "Anchor bolts"}), 200)
    sent = p["ok"](p["call"]("POST", f"project-reports/{draft['id']}/publish"), 200)
    assert sent["status"] == "published" and sent["figures"]["milestone_standing"] == {"overdue": 1}
    assert p["call"]("PATCH", f"project-reports/{draft['id']}", {"health": "green"}).status_code == 409
    assert p["call"]("DELETE", f"project-reports/{draft['id']}").status_code == 409

    milestone = p["ok"](p["call"]("GET", "project-milestones", project_id=p["site"]), 200)[0]
    p["ok"](p["call"]("POST", f"project-milestones/{milestone['id']}/reach", {"reached_on": "2026-03-06"}), 200)
    kept = p["ok"](p["call"]("GET", f"project-reports/{draft['id']}"), 200)
    assert kept["figures"]["milestone_standing"] == {"overdue": 1}, "the figures are what stood at publication"

    corrected = p["ok"](p["call"]("POST", "project-reports", {**week, "health": "red", "summary": "Worse"}))
    assert corrected["revision"] == 2
    history = p["ok"](p["call"]("GET", "project-reports", project_id=p["site"]), 200)
    assert [r["revision"] for r in history] == [2, 1]


def test_the_money_is_each_documents_own_figure_and_withheld_without_the_grant(project) -> None:
    p = project
    staff = p["ok"](p["call"]("POST", "employees", {"name": "Buyer"}))["id"]
    vendor = p["ok"](p["call"]("POST", "vendors", {"name": "Steel Co"}))["id"]
    customer = p["ok"](p["call"]("POST", "customers", {"name": "Huaxin"}))["id"]
    contract = p["ok"](p["call"]("POST", "contracts", {"title": "Fit-out", "side": "sales", "customer_id": customer,
                                                       "total_amount": 100000}))
    p["ok"](p["call"]("PATCH", f"projects/{p['site']}", {"contract_id": contract["id"]}), 200)
    p["ok"](p["call"]("POST", "expense-claims", {
        "employee_id": staff, "title": "site visit", "status": "approved", "items": [
            {"expense_date": "2026-03-05", "amount": 300, "project_id": p["site"]},
            {"expense_date": "2026-03-05", "amount": 50}]}))
    stray = p["call"]("POST", "purchase-orders", {"employee_id": staff, "vendor_id": vendor, "title": "x",
                                                  "project_id": "00000000-0000-0000-0000-000000000000"})
    assert stray.status_code == 422 and "project_id" in stray.text
    order = p["ok"](p["call"]("POST", "purchase-orders", {
        "employee_id": staff, "vendor_id": vendor, "title": "racking", "order_date": "2026-03-03",
        "status": "confirmed", "project_id": p["site"], "total_amount": 8000}))
    assert order["project_id"] == p["site"]
    request = p["ok"](p["call"]("POST", "purchase-requests", {"employee_id": staff, "title": "bolts",
                                                              "project_id": p["site"]}))
    assert request["project_id"] == p["site"]
    p["ok"](p["call"]("POST", "invoices", {"direction": "purchase", "employee_id": staff, "vendor_id": vendor,
                                           "title": "racking", "invoice_date": "2026-03-10", "status": "issued",
                                           "total_amount": 6000, "project_id": p["site"]}))
    billed = p["ok"](p["call"]("POST", "invoices", {"direction": "sales", "employee_id": staff,
                                                    "customer_id": customer, "title": "stage 1",
                                                    "invoice_date": "2026-03-12", "status": "issued",
                                                    "total_amount": 30000, "project_id": p["site"]}))
    p["ok"](p["call"]("POST", "invoices", {"direction": "sales", "invoice_kind": "credit_note",
                                           "original_invoice_id": billed["id"], "employee_id": staff,
                                           "customer_id": customer, "title": "discount",
                                           "invoice_date": "2026-03-14", "status": "issued",
                                           "total_amount": -2000}))
    money = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", as_of="2026-03-31"), 200)["money"]
    assert money["expenses"] == {"approved": {"CNY": 300.0}}
    assert money["purchase_orders"] == {"ordered": {"CNY": 8000.0}, "count": 1}
    assert money["purchase_invoices"]["net"] == {"CNY": 6000.0}
    assert money["billing"]["net"] == {"CNY": 28000.0}, "the credit note nets though it names only the invoice"
    assert money["billing"]["contract_value"] == {"CNY": 100000.0}
    before = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", as_of="2026-03-11"), 200)["money"]
    assert before["billing"]["net"] == {}

    invited = invite_member(p["c"], p["admin"], "member", [], email="m@build-co.example", employee="Fitter")
    member = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", who={"X-API-Key": invited["X-API-Key"]}), 200)
    # a member reads invoices and purchase orders by default, so sees what
    # they total; everyone's expenses and the book stay behind their grants
    assert set(member["withheld"]) == {"expenses", "book"} and "expenses" not in member["money"]
    seller = invite_member(p["c"], p["admin"], "sales_reader", ["invoice.read:sales"], email="s@build-co.example",
                           employee="Seller")
    partial = p["ok"](p["call"]("GET", f"projects/{p['site']}/execution", who={"X-API-Key": seller["X-API-Key"]}), 200)
    assert set(partial["money"]) == {"billing"} and "billing" not in partial["withheld"]
