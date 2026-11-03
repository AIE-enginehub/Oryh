"""Budgets, phase 2 — plan docs/plans/budgets-2026-10-27.md §12.

The sales target split by salesperson, territory, customer or product
category, each split a sub-target read beside the sales line and never added
to it; how far each line's plan is spoken for, a figure the agent alerts on
by the workspace's rule; and the combined cash read across an income and a
spend budget.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant

YEAR = {"period_start": "2026-01-01", "period_end": "2026-12-31"}
MARCH = "2026-03-01"


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Reach Shop", email="owner@reach-shop.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def post(path: str, body: dict, who: dict | None = None):
            return c.post(f"/api/v1/{path}", headers=who or admin, json=body)

        def patch(path: str, body: dict, who: dict | None = None):
            return c.patch(f"/api/v1/{path}", headers=who or admin, json=body)

        def get(path: str, who: dict | None = None, **params):
            return c.get(f"/api/v1/{path}", headers=who or admin, params=params)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"]

        owner = ok(post("employees", {"name": "Owner"}))["id"]
        yield dict(c=c, admin=admin, post=post, patch=patch, get=get, ok=ok, owner=owner)


def _line(execution: dict, code: str) -> dict:
    return next(row for row in execution["lines"] if row["line_code"] == code)


def _sub(row: dict, code: str) -> dict:
    return next(sub for sub in row["sub_targets"] if sub["line_code"] == code)


def _income_budget(s, target: float = 50000) -> dict:
    budget = s["ok"](s["post"]("budgets", {"name": "2026 sales", "direction": "income", **YEAR,
                                          "lines": [{"line_code": "SAL", "name": "Sales", "category": "sales"}]}))
    s["ok"](s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "reason": "the target", "status": "posted",
        "lines": [{"line_code": "SAL", "period_month": MARCH, "amount": target}]}))
    return {**budget, "sales": budget["lines"][0]["id"]}


def _sub_target(s, budget: dict, code: str, amount: float, **dimension) -> dict:
    line = s["ok"](s["post"]("budget-lines", {"budget_id": budget["id"], "line_code": code, "name": code,
                                              "parent_line_id": budget["sales"], **dimension}))
    s["ok"](s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "reason": f"{code}'s share", "status": "posted",
        "lines": [{"budget_line_id": line["id"], "period_month": MARCH, "amount": amount}]}))
    return line


def _sales_invoice(s, customer: str, items: list[dict]) -> dict:
    return s["ok"](s["post"]("invoices", {
        "direction": "sales", "employee_id": s["owner"], "customer_id": customer, "title": "sale",
        "invoice_date": "2026-03-15", "status": "issued", "items": items}))


# --- sub-targets -----------------------------------------------------------------


def test_a_sales_target_splits_by_salesperson_territory_and_product_beside_the_total(shop) -> None:
    s = shop
    ok, post = s["ok"], s["post"]
    ana = ok(post("employees", {"name": "Ana"}))["id"]
    ben = ok(post("employees", {"name": "Ben"}))["id"]
    east = ok(post("territories", {"territory_code": "EAST", "name": "East"}))["id"]
    zhejiang = ok(post("territories", {"territory_code": "ZJ", "name": "Zhejiang", "parent_territory_id": east}))["id"]
    tools = ok(post("product-categories", {"name": "Tools", "category_code": "TOOLS"}))["id"]
    drills = ok(post("product-categories", {"name": "Drills", "category_code": "DRILLS", "parent_id": tools}))["id"]
    drill = ok(post("products", {"name": "Drill", "product_code": "DRILL-1", "category_id": drills}))["id"]
    cup = ok(post("products", {"name": "Cup", "product_code": "CUP-1"}))["id"]
    north = ok(post("customers", {"name": "North Co", "owner_employee_id": ana, "territory_id": zhejiang}))["id"]
    south = ok(post("customers", {"name": "South Co", "owner_employee_id": ben}))["id"]

    budget = _income_budget(s)
    _sub_target(s, budget, "ANA", 30000, employee_id=ana)
    _sub_target(s, budget, "BEN", 20000, employee_id=ben)
    east_target = _sub_target(s, budget, "EAST", 25000, territory_id=east)
    _sub_target(s, budget, "TOOLS", 10000, product_category_id=tools)

    _sales_invoice(s, north, [
        {"invoice_item_type": "goods", "product_id": drill, "product_name_snapshot": "drill", "amount": 8000},
        {"invoice_item_type": "goods", "product_id": cup, "product_name_snapshot": "cup", "amount": 2000},
        {"invoice_item_type": "tax", "product_name_snapshot": "VAT", "amount": 1300}])
    _sales_invoice(s, south, [
        {"invoice_item_type": "goods", "product_id": cup, "product_name_snapshot": "cup", "amount": 5000}])
    ok(post("opportunities", {"employee_id": ben, "customer_id": south, "title": "refill", "expected_amount": 4000,
                              "probability": 50, "expected_close_date": "2026-03-28"}))

    execution = ok(s["get"](f"budgets/{budget['id']}/execution"), 200)
    sales = _line(execution, "SAL")
    assert sales["totals"]["invoiced"] == 15000.0
    assert execution["totals"]["planned"] == 50000.0, "a sub-target's plan is a breakdown, never added to the total"
    figures = {sub["line_code"]: sub["totals"] for sub in sales["sub_targets"]}
    assert figures["ANA"]["invoiced"] == 10000.0, "the account owner sold North's invoice"
    assert (figures["BEN"]["invoiced"], figures["BEN"]["pipeline"]) == (5000.0, 4000.0)
    assert figures["EAST"]["invoiced"] == 10000.0, "Zhejiang lies under East"
    assert figures["TOOLS"]["invoiced"] == 8000.0, "a drill is on a shelf under Tools; tax and cups are not"
    assert _sub(sales, "EAST")["dimension"] == "territory" and _sub(sales, "EAST")["collects"] is False

    splits = sales["splits"]
    assert splits["salesperson"] == {"planned": 50000.0, "line_planned": 50000.0, "unplanned": 0.0,
                                     "outside_invoiced": 0.0}
    assert (splits["territory"]["unplanned"], splits["territory"]["outside_invoiced"]) == (25000.0, 5000.0)

    documents = ok(s["get"](f"budget-lines/{east_target['id']}/documents", stage="invoiced"), 200)
    assert [(d["entity_type"], d["amount"]) for d in documents] == [("invoice", 10000.0)]


def test_a_sub_target_names_one_dimension_once_under_a_sales_line(shop) -> None:
    s = shop
    ok, post = s["ok"], s["post"]
    ana = ok(post("employees", {"name": "Ana"}))["id"]
    region = ok(post("territories", {"territory_code": "W", "name": "West"}))["id"]
    budget = _income_budget(s)
    base = {"budget_id": budget["id"], "name": "x", "parent_line_id": budget["sales"]}

    assert post("budget-lines", {**base, "line_code": "NONE"}).status_code == 422
    assert post("budget-lines", {**base, "line_code": "TWO", "employee_id": ana,
                                 "territory_id": region}).status_code == 422
    assert post("budget-lines", {"budget_id": budget["id"], "line_code": "LOOSE", "name": "x",
                                 "employee_id": ana}).status_code == 422, "a dimension needs a parent"
    ok(post("budget-lines", {**base, "line_code": "ANA", "employee_id": ana}))
    twice = post("budget-lines", {**base, "line_code": "ANA2", "employee_id": ana})
    assert twice.status_code == 409 and "dimension" in twice.text

    spend = ok(post("budgets", {"name": "costs", **YEAR,
                                "lines": [{"line_code": "MKT", "name": "Marketing", "category": "marketing"}]}))
    under_marketing = post("budget-lines", {"budget_id": spend["id"], "line_code": "M-ANA", "name": "x",
                                            "parent_line_id": spend["lines"][0]["id"], "employee_id": ana})
    assert under_marketing.status_code == 422 and "sales" in under_marketing.text


def test_money_moves_between_lines_of_one_level(shop) -> None:
    s = shop
    ok, post = s["ok"], s["post"]
    ana = ok(post("employees", {"name": "Ana"}))["id"]
    ben = ok(post("employees", {"name": "Ben"}))["id"]
    budget = _income_budget(s)
    ok(post("budget-lines", {"budget_id": budget["id"], "line_code": "OTHER", "name": "Other income",
                             "category": "other"}))
    ok(post("budget-changes", {"budget_id": budget["id"], "employee_id": s["owner"], "reason": "x", "status": "posted",
                               "lines": [{"line_code": "OTHER", "period_month": MARCH, "amount": 1000}]}))
    _sub_target(s, budget, "ANA", 30000, employee_id=ana)
    _sub_target(s, budget, "BEN", 20000, employee_id=ben)

    across = post("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "transfer", "reason": "x",
        "status": "posted", "lines": [{"line_code": "ANA", "period_month": MARCH, "amount": -500},
                                      {"line_code": "OTHER", "period_month": MARCH, "amount": 500}]})
    assert across.status_code == 422 and "sub-targets" in across.text
    within = post("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "transfer", "reason": "Ben's new account",
        "status": "posted", "lines": [{"line_code": "ANA", "period_month": MARCH, "amount": -5000},
                                      {"line_code": "BEN", "period_month": MARCH, "amount": 5000}]})
    assert within.status_code == 201, within.text
    sales = _line(ok(s["get"](f"budgets/{budget['id']}/execution"), 200), "SAL")
    assert (_sub(sales, "ANA")["totals"]["planned"], _sub(sales, "BEN")["totals"]["planned"]) == (25000.0, 25000.0)


# --- how far a line has gone: a fact the agent alerts on --------------------------------


def _marketing_budget(s, manager: str, **extra) -> dict:
    budget = s["ok"](s["post"]("budgets", {
        "name": "2026 marketing", **YEAR, **extra,
        "lines": [{"line_code": "MKT", "name": "Marketing pot", "category": "marketing", "owner_employee_id": manager}]}))
    s["ok"](s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "reason": "the pot", "status": "posted",
        "lines": [{"line_code": "MKT", "period_month": MARCH, "amount": 5000}]}))
    s["ok"](s["patch"](f"budgets/{budget['id']}", {"status": "active"}), 200)
    return budget


def test_execution_reports_how_far_the_plan_is_spoken_for_and_raises_nothing(shop) -> None:
    """When a percent warrants telling someone, and whom, is the workspace's
    rule: the server reports the figure, the agent raises the todo."""
    s = shop
    ok, post = s["ok"], s["post"]
    manager = ok(post("employees", {"name": "Marketing manager"}))["id"]
    vendor = ok(post("vendors", {"name": "Agency"}))["id"]
    budget = _marketing_budget(s, manager)
    ok(post("purchase-requests", {
        "employee_id": manager, "title": "banners", "request_date": "2026-03-02", "status": "approved",
        "items": [{"product_name_snapshot": "banner", "quantity": 1, "unit_price": 1000,
                   "budget_line_id": budget["lines"][0]["id"]}]}))
    ok(post("invoices", {
        "direction": "purchase", "employee_id": s["owner"], "vendor_id": vendor, "title": "ads",
        "invoice_date": "2026-03-10", "status": "issued",
        "items": [{"invoice_item_type": "marketing", "product_name_snapshot": "ads", "amount": 3200}]}))
    totals = _line(ok(s["get"](f"budgets/{budget['id']}/execution"), 200), "MKT")["totals"]
    assert (totals["percent_used"], totals["percent_consumed"]) == (64.0, 84.0), "actual alone, and with requests"
    todos = ok(s["get"]("todos", employee_id=manager), 200)
    assert todos == [], "nothing is raised by the record"
    assert post("budget-alerts/sweep", {}).status_code in (404, 405)
    assert "alert_percents" not in ok(s["get"](f"budgets/{budget['id']}"), 200)


# --- the combined cash read ---------------------------------------------------------


def test_the_cash_budget_nets_receipts_against_payments_month_by_month(shop) -> None:
    s = shop
    ok, post = s["ok"], s["post"]
    vendor = ok(post("vendors", {"name": "Agency"}))["id"]
    customer = ok(post("customers", {"name": "Client"}))["id"]
    income = _income_budget(s)
    spend = _marketing_budget(s, s["owner"])

    sale = _sales_invoice(s, customer, [
        {"invoice_item_type": "goods", "product_name_snapshot": "widgets", "amount": 20000}])
    receipt = ok(post("payments", {"direction": "inbound", "employee_id": s["owner"], "customer_id": customer,
                                   "amount": 15000, "status": "paid", "payment_date": "2026-03-20"}))
    ok(post(f"payments/{receipt['id']}/apply", {"lines": [
        {"applied_to_type": "invoice", "applied_to_id": sale["id"], "amount_applied": 15000}]}), 200)
    for kind, amount, paid in (("marketing", 1000, 600), ("goods", 300, 300)):
        bill = ok(post("invoices", {
            "direction": "purchase", "employee_id": s["owner"], "vendor_id": vendor, "title": kind,
            "invoice_date": "2026-03-10", "status": "issued",
            "items": [{"invoice_item_type": kind, "product_name_snapshot": kind, "amount": amount}]}))
        payment = ok(post("payments", {"direction": "outbound", "employee_id": s["owner"], "vendor_id": vendor,
                                       "amount": paid, "status": "paid"}))
        ok(post(f"payments/{payment['id']}/apply", {"lines": [
            {"applied_to_type": "invoice", "applied_to_id": bill["id"], "amount_applied": paid}]}), 200)

    cash = ok(s["get"]("budget-cash", income_budget_id=income["id"], spend_budget_id=spend["id"]), 200)
    march = next(row for row in cash["months"] if row["month"] == MARCH)
    assert (march["income_planned"], march["received"]) == (50000.0, 15000.0)
    assert (march["spend_planned"], march["paid"], march["unbudgeted_paid"]) == (5000.0, 600.0, 300.0)
    assert (march["net_planned"], march["net_actual"]) == (45000.0, 14100.0)
    december = cash["months"][-1]
    assert december["cumulative_net_actual"] == 14100.0 and cash["paid_excludes_labour"] is False

    backwards = s["get"]("budget-cash", income_budget_id=spend["id"])
    assert backwards.status_code == 422 and "plans spend" in backwards.text
    assert s["get"]("budget-cash").status_code == 422
