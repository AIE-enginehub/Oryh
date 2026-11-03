"""Budgets, phase 1 — plan docs/plans/budgets-2026-10-27.md.

A small business plans three things for the year: a marketing pot, labour
cost (gross pay plus the employer's social insurance and housing fund) and a
sales target. The plan is a ledger moved only by posted changes; what was
consumed is derived from the documents and stored nowhere; and a line
collects its documents without anybody tagging them.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant

YEAR = {"period_start": "2026-01-01", "period_end": "2026-12-31"}
MARCH = "2026-03-01"


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Budget Shop", email="owner@budget-shop.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def post(path: str, body: dict, who: dict | None = None):
            return c.post(f"/api/v1/{path}", headers=who or admin, json=body)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"]

        owner = ok(post("employees", {"name": "Owner"}))["id"]
        staff = ok(post("employees", {"name": "Staff"}))["id"]
        vendor = ok(post("vendors", {"name": "Ad Agency"}))["id"]
        bureau = ok(post("vendors", {"name": "Tax Bureau"}))["id"]
        customer = ok(post("customers", {"name": "Big Client"}))["id"]
        yield dict(c=c, admin=admin, post=post, ok=ok, owner=owner, staff=staff, vendor=vendor,
                   bureau=bureau, customer=customer)


def _spend_budget(s, **extra) -> dict:
    budget = s["ok"](s["post"]("budgets", {
        "name": "2026 operating", **YEAR, "lines": [
            {"line_code": "LAB", "name": "Labour", "category": "labour"},
            {"line_code": "MKT", "name": "Marketing pot", "category": "marketing"},
            {"line_code": "OFF", "name": "Office", "category": "office"},
        ], **extra}))
    lines = {line["line_code"]: line for line in budget["lines"]}
    s["ok"](s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "reason": "the 2026 plan", "status": "posted",
        "lines": [
            {"line_code": "LAB", "period_month": MARCH, "amount": 20000},
            {"line_code": "MKT", "period_month": MARCH, "amount": 5000},
            {"line_code": "OFF", "period_month": MARCH, "amount": 1000},
        ]}))
    s["ok"](s["c"].patch(f"/api/v1/budgets/{budget['id']}", headers=s["admin"], json={"status": "active"}), 200)
    return {**budget, "lines": lines}


def _execution(s, budget_id: str, who: dict | None = None) -> dict:
    return s["ok"](s["c"].get(f"/api/v1/budgets/{budget_id}/execution", headers=who or s["admin"]), 200)


def _line(execution: dict, code: str) -> dict:
    return next(row for row in execution["lines"] if row["line_code"] == code)


def _purchase_invoice(s, lines: list[dict], **extra) -> dict:
    return s["ok"](s["post"]("invoices", {
        "direction": "purchase", "employee_id": s["owner"], "vendor_id": extra.pop("vendor", s["vendor"]),
        "title": "invoice", "invoice_date": "2026-03-10", "status": "issued", "items": lines, **extra}))


# --- B1-B5: the plan is a ledger moved by changes ----------------------------


def test_the_plan_is_what_posted_changes_say(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    marketing = _line(_execution(s, budget["id"]), "MKT")
    assert marketing["collects"] and marketing["totals"]["planned"] == 5000.0
    entries = s["ok"](s["c"].get("/api/v1/budget-entries", headers=s["admin"],
                                 params={"budget_line_id": budget["lines"]["MKT"]["id"]}), 200)
    assert [(e["entry_type"], e["amount"]) for e in entries] == [("original", 5000.0)]

    moved = s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "transfer",
        "reason": "more ads, less paper", "status": "posted", "lines": [
            {"line_code": "OFF", "period_month": MARCH, "amount": -400},
            {"line_code": "MKT", "period_month": MARCH, "amount": 400}]})
    assert moved.status_code == 201, moved.text
    execution = _execution(s, budget["id"])
    assert (_line(execution, "MKT")["totals"]["planned"], _line(execution, "OFF")["totals"]["planned"]) == (5400.0, 600.0)

    unbalanced = s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "transfer",
        "reason": "x", "status": "posted", "lines": [{"line_code": "OFF", "period_month": MARCH, "amount": -100}]})
    assert unbalanced.status_code == 422 and "nets to zero" in unbalanced.text
    backwards = s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "increase",
        "reason": "x", "status": "posted", "lines": [{"line_code": "OFF", "period_month": MARCH, "amount": -100}]})
    assert backwards.status_code == 422 and "every line is positive" in backwards.text


def test_a_posted_change_is_history(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    change = s["ok"](s["c"].get("/api/v1/budget-changes", headers=s["admin"],
                                params={"budget_id": budget["id"]}), 200)[0]
    assert change["status"] == "posted" and change["posted_at"]
    assert s["c"].delete(f"/api/v1/budget-changes/{change['id']}", headers=s["admin"]).status_code == 409
    refused = s["c"].patch(f"/api/v1/budgets/{budget['id']}", headers=s["admin"], json={"currency": "USD"})
    assert refused.status_code == 409


def test_a_workspace_may_route_changes_for_approval(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    desk = dict(invite_member(s["c"], s["admin"], "budget_desk", ["budget.manage"],
                              email="desk@budget-shop.example", employee="Desk"))
    approver = dict(invite_member(s["c"], s["admin"], "approver", ["budget.advance"],
                                  email="cfo@budget-shop.example", employee="CFO"))
    change = s["ok"](s["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": s["owner"], "change_type": "increase", "reason": "trade fair",
        "lines": [{"line_code": "MKT", "period_month": MARCH, "amount": 1000}]}, desk))
    assert change["status"] == "draft"
    assert s["post"](f"budget-changes/{change['id']}/submit", {}, desk).status_code == 200
    assert s["c"].patch(f"/api/v1/budget-changes/{change['id']}", headers=desk,
                        json={"status": "approved"}).status_code == 403, "the desk does not approve its own change"
    for state in ("approved", "posted"):
        moved = s["c"].patch(f"/api/v1/budget-changes/{change['id']}", headers=approver, json={"status": state})
        assert moved.status_code == 200, moved.text
    assert _line(_execution(s, budget["id"]), "MKT")["totals"]["planned"] == 6000.0


# --- B2, B6-B7: collection and the four stages --------------------------------


def test_marketing_is_collected_from_expenses_and_invoice_lines_without_tags(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    s["ok"](s["post"]("expense-claims", {
        "employee_id": s["staff"], "title": "trade fair", "status": "approved", "items": [
            {"expense_date": "2026-03-05", "amount": 300, "category": "marketing"},
            {"expense_date": "2026-03-05", "amount": 50, "category": "transport"}]}))
    _purchase_invoice(s, [{"invoice_item_type": "marketing", "product_name_snapshot": "search ads", "amount": 1200},
                          {"invoice_item_type": "tax", "product_name_snapshot": "VAT", "amount": 72}])
    execution = _execution(s, budget["id"])
    marketing = _line(execution, "MKT")["totals"]
    assert marketing["actual"] == 1500.0 and marketing["available"] == 3500.0
    assert execution["unbudgeted"]["actual"] == 50.0, "the taxi no line collects is shown, not lost"


def test_labour_is_gross_pay_plus_the_employer_share_never_net_or_withholdings(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    s["ok"](s["post"]("invoices", {
        "direction": "payroll", "employee_id": s["owner"], "payee_employee_id": s["staff"], "title": "March pay",
        "period_start": "2026-03-01", "period_end": "2026-03-31", "status": "issued", "items": [
            {"invoice_item_type": "payroll_salary", "product_name_snapshot": "salary", "amount": 10000,
             "notes": "monthly salary 10000.00"},
            {"invoice_item_type": "payroll_pension_ee", "product_name_snapshot": "pension", "amount": -800,
             "notes": "base 10000.00 x 8% = 800.00"},
            {"invoice_item_type": "payroll_iit", "product_name_snapshot": "income tax", "amount": -200,
             "notes": "cumulative withholding 200.00"}]}))
    _purchase_invoice(s, [
        {"invoice_item_type": "employer_social_insurance", "product_name_snapshot": "employer SI", "amount": 1600},
        {"invoice_item_type": "employer_housing_fund", "product_name_snapshot": "employer HF", "amount": 700},
        {"invoice_item_type": "withheld_remittance", "product_name_snapshot": "withheld", "amount": 1000}],
        vendor=s["bureau"])
    labour = _line(_execution(s, budget["id"]), "LAB")["totals"]
    assert labour["actual"] == 12300.0, "10,000 gross + 1,600 + 700; never the 9,000 net, never the 1,000 again"


def test_labour_figures_are_pay_and_stay_behind_payroll_read(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    reader = dict(invite_member(s["c"], s["admin"], "controller", ["budget.read_all"],
                                email="controller@budget-shop.example", employee="Controller"))
    execution = _execution(s, budget["id"], reader)
    labour = _line(execution, "LAB")
    assert labour["redacted"] and labour["totals"]["planned"] == 20000.0 and labour["totals"]["actual"] is None
    assert execution["totals_exclude_labour"] is True
    assert s["c"].get(f"/api/v1/budget-lines/{budget['lines']['LAB']['id']}/documents",
                      headers=reader).status_code == 403
    assert not _line(execution, "MKT")["redacted"]


def test_requested_becomes_committed_becomes_actual_and_counts_once(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    office = budget["lines"]["OFF"]["id"]
    request = s["ok"](s["post"]("purchase-requests", {
        "employee_id": s["staff"], "title": "chairs", "request_date": "2026-03-02", "status": "approved",
        "items": [{"product_name_snapshot": "chair", "quantity": 4, "unit_price": 100, "budget_line_id": office}]}))
    assert _line(_execution(s, budget["id"]), "OFF")["totals"]["requested"] == 400.0

    order = s["ok"](s["post"]("purchase-orders", {
        "employee_id": s["owner"], "vendor_id": s["vendor"], "title": "chairs", "order_date": "2026-03-03",
        "status": "confirmed", "items": [{"product_name_snapshot": "chair", "quantity": 3, "unit_price": 100,
                                          "purchase_request_item_id": request["items"][0]["id"]}]}))
    assert order["items"][0]["budget_line_id"] == office, "the order line inherits the request line's tag"
    office_now = _line(_execution(s, budget["id"]), "OFF")["totals"]
    assert (office_now["requested"], office_now["committed"]) == (100.0, 300.0)

    _purchase_invoice(s, [{"product_name_snapshot": "chair", "amount": 200, "invoice_item_type": "goods",
                           "purchase_order_item_id": order["items"][0]["id"]}], purchase_order_id=order["id"])
    office_now = _line(_execution(s, budget["id"]), "OFF")["totals"]
    assert (office_now["requested"], office_now["committed"], office_now["actual"]) == (100.0, 100.0, 200.0)
    assert office_now["available"] == 1000 - 400


def test_paid_is_the_cash_against_actual(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    invoice = _purchase_invoice(s, [{"invoice_item_type": "marketing", "product_name_snapshot": "ads", "amount": 1000}])
    payment = s["ok"](s["post"]("payments", {
        "direction": "outbound", "employee_id": s["owner"], "vendor_id": s["vendor"], "amount": 600, "status": "paid"}))
    s["ok"](s["post"](f"payments/{payment['id']}/apply", {"lines": [
        {"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 600}]}), 200)
    marketing = _line(_execution(s, budget["id"]), "MKT")["totals"]
    assert (marketing["actual"], marketing["paid"]) == (1000.0, 600.0)


# --- B6, B12: tagging -----------------------------------------------------------


def test_a_tag_must_fit_and_is_never_refused_for_being_over_budget(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    office = budget["lines"]["OFF"]["id"]
    over = _purchase_invoice(s, [{"invoice_item_type": "goods", "product_name_snapshot": "desk", "amount": 5000,
                                  "budget_line_id": office}])
    assert over["id"], "5,000 against a 1,000 line is recorded; the workspace's approval flow judges it"
    office_now = _line(_execution(s, budget["id"]), "OFF")["totals"]
    assert office_now["available"] == -4000.0

    usd = s["post"]("invoices", {
        "direction": "purchase", "employee_id": s["owner"], "vendor_id": s["vendor"], "title": "usd",
        "currency": "USD", "invoice_date": "2026-03-10", "items": [
            {"invoice_item_type": "goods", "product_name_snapshot": "x", "amount": 10, "budget_line_id": office}]})
    assert usd.status_code == 422 and "USD" in usd.text
    late = s["post"]("invoices", {
        "direction": "purchase", "employee_id": s["owner"], "vendor_id": s["vendor"], "title": "2027",
        "invoice_date": "2027-01-10", "items": [
            {"invoice_item_type": "goods", "product_name_snapshot": "x", "amount": 10, "budget_line_id": office}]})
    assert late.status_code == 422 and "outside" in late.text


def test_spend_is_never_tagged_to_an_income_line(shop) -> None:
    s = shop
    income = s["ok"](s["post"]("budgets", {"name": "2026 sales", "direction": "income", **YEAR,
                                          "lines": [{"line_code": "SAL", "name": "Sales", "category": "sales"}]}))
    response = s["post"]("invoices", {
        "direction": "purchase", "employee_id": s["owner"], "vendor_id": s["vendor"], "title": "x",
        "invoice_date": "2026-03-10", "items": [{"invoice_item_type": "goods", "product_name_snapshot": "x",
                                                 "amount": 10, "budget_line_id": income["lines"][0]["id"]}]})
    assert response.status_code == 422 and "income" in response.text


# --- Q10: one collector per category per period ---------------------------------


def test_two_overlapping_budgets_do_not_both_collect_marketing(shop) -> None:
    s = shop
    _spend_budget(s)
    second = s["ok"](s["post"]("budgets", {"name": "Q2 push", "period_start": "2026-04-01", "period_end": "2026-06-30",
                                          "lines": [{"line_code": "M2", "name": "More marketing", "category": "marketing"}]}))
    clash = s["c"].patch(f"/api/v1/budgets/{second['id']}", headers=s["admin"], json={"status": "active"})
    assert clash.status_code == 409 and "marketing" in clash.text
    twice = s["post"]("budget-lines", {"budget_id": second["id"], "line_code": "M3", "name": "again",
                                       "category": "marketing"})
    assert twice.status_code == 409, "one collecting line per category per budget"


# --- B8: income ----------------------------------------------------------------


def test_sales_income_is_invoiced_ordered_and_a_pipeline_beside_it(shop) -> None:
    s = shop
    income = s["ok"](s["post"]("budgets", {"name": "2026 sales", "direction": "income", **YEAR,
                                          "lines": [{"line_code": "SAL", "name": "Sales", "category": "sales"}]}))
    s["ok"](s["post"]("budget-changes", {
        "budget_id": income["id"], "employee_id": s["owner"], "reason": "the target", "status": "posted",
        "lines": [{"line_code": "SAL", "period_month": MARCH, "amount": 50000}]}))
    s["ok"](s["post"]("invoices", {
        "direction": "sales", "employee_id": s["owner"], "customer_id": s["customer"], "title": "March sale",
        "invoice_date": "2026-03-15", "status": "issued", "items": [
            {"invoice_item_type": "goods", "product_name_snapshot": "widgets", "amount": 20000},
            {"invoice_item_type": "tax", "product_name_snapshot": "VAT", "amount": 2600}]}))
    s["ok"](s["post"]("opportunities", {
        "employee_id": s["owner"], "customer_id": s["customer"], "title": "big deal", "expected_amount": 30000,
        "probability": 50, "expected_close_date": "2026-03-28"}))
    sales = _line(_execution(s, income["id"]), "SAL")["totals"]
    assert (sales["invoiced"], sales["gap"]) == (20000.0, 30000.0), "tax is not income"
    assert (sales["pipeline"], sales["pipeline_weighted"]) == (30000.0, 15000.0)
    assert sales["percent_achieved"] == 40.0


# --- B11: impact, B15: import ------------------------------------------------------


def test_an_approver_reads_what_a_request_does_to_its_line(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    request = s["ok"](s["post"]("purchase-requests", {
        "employee_id": s["staff"], "title": "printer", "request_date": "2026-03-02", "items": [
            {"product_name_snapshot": "printer", "quantity": 1, "unit_price": 700,
             "budget_line_id": budget["lines"]["OFF"]["id"]}]}))
    approver = dict(invite_member(s["c"], s["admin"], "purchasing_approver", ["purchase.advance"],
                                  email="approver@budget-shop.example", employee="Approver"))
    impact = s["ok"](s["c"].get("/api/v1/budget-impact", headers=approver,
                                params={"entity_type": "purchase_request", "entity_id": request["id"]}), 200)
    row = impact["lines"][0]
    assert (row["line_code"], row["how"], row["counted"]) == ("OFF", "tagged", False)
    assert (row["available_before"], row["available_after"], row["would_go_negative"]) == (1000.0, 300.0, False)
    nobody = dict(invite_member(s["c"], s["admin"], "nobody", [], email="nobody@budget-shop.example", employee="N"))
    assert s["c"].get("/api/v1/budget-impact", headers=nobody,
                      params={"entity_type": "purchase_request", "entity_id": request["id"]}).status_code == 403


def test_a_plan_imports_once_and_a_different_figure_is_a_change(shop) -> None:
    s = shop
    budget = s["ok"](s["post"]("budgets", {"name": "imported", **YEAR}))
    rows = [{"line_code": "MKT", "name": "Marketing", "category": "marketing", "period_month": MARCH, "amount": 900},
            {"line_code": "MKT", "period_month": "2026-04-01", "amount": 900}]
    first = s["ok"](s["post"](f"budgets/{budget['id']}/import", {
        "employee_id": s["owner"], "reason": "from the spreadsheet", "rows": rows, "post": True}), 200)
    assert first["summary"] == {"rows": 2, "lines_created": 1, "planned": 2, "unchanged": 0, "errors": 0}
    again = s["ok"](s["post"](f"budgets/{budget['id']}/import", {
        "employee_id": s["owner"], "reason": "again", "rows": rows, "post": True}), 200)
    assert again["summary"]["unchanged"] == 2 and again["change"] is None
    other = s["ok"](s["post"](f"budgets/{budget['id']}/import", {
        "employee_id": s["owner"], "reason": "edited", "post": True,
        "rows": [{"line_code": "MKT", "period_month": MARCH, "amount": 950}]}), 200)
    assert other["summary"]["errors"] == 1 and "a change with its reason" in other["results"][0]["error"]


def test_the_line_directory_has_no_amounts_and_figures_need_a_grant(shop) -> None:
    s = shop
    budget = _spend_budget(s)
    member = dict(invite_member(s["c"], s["admin"], "member_like", [], email="m@budget-shop.example", employee="M"))
    directory = s["c"].get("/api/v1/budget-lines", headers=member, params={"budget_id": budget["id"]})
    assert directory.status_code == 200 and {row["line_code"] for row in directory.json()["data"]} == {"LAB", "MKT", "OFF"}
    assert not any("amount" in key or "planned" in key for row in directory.json()["data"] for key in row)
    assert s["c"].get(f"/api/v1/budgets/{budget['id']}/execution", headers=member).status_code == 403


@pytest.mark.parametrize("invoice_status", ["draft", "issued"])
def test_labour_tagged_to_an_ordinary_line_stays_private(shop, invoice_status):
    s = shop
    budget = _spend_budget(s)
    office = budget["lines"]["OFF"]["id"]
    invoice = _purchase_invoice(s, [{"invoice_item_type": "employer_social_insurance",
        "product_name_snapshot": "Employer contribution", "amount": 4321, "budget_line_id": office}],
        status=invoice_status)
    reader = dict(invite_member(s["c"], s["admin"], "budget_reader", ["budget.read_all", "invoice.read"],
                                email="reader@budget-shop.example", employee="Reader"))
    impact = s["ok"](s["c"].get("/api/v1/budget-impact", headers=reader,
                    params={"entity_type": "invoice", "entity_id": invoice["id"]}), 200)["lines"][0]
    assert impact["redacted"]
    assert all(impact[key] is None for key in ("amount", "available_before", "available_after", "would_go_negative"))
    if invoice_status == "draft":
        return
    result = _execution(s, budget["id"], reader)
    row = _line(result, "OFF")
    assert row["redacted"] and row["totals"]["planned"] == 1000
    assert all(value is None for key, value in row["totals"].items() if key != "planned")
    assert all(month["actual"] is None for month in row["by_month"])
    assert result["totals"]["actual"] == 0 and result["totals_exclude_labour"]
    for resource in ("documents", "availability"):
        assert s["c"].get(f"/api/v1/budget-lines/{office}/{resource}", headers=reader).status_code == 403
        assert s["c"].get(f"/api/v1/budget-lines/{office}/{resource}", headers=s["admin"]).status_code == 200
    assert _line(_execution(s, budget["id"]), "OFF")["totals"]["actual"] == 4321


def _office_request(s, budget, amount=400):
    return s["ok"](s["post"]("purchase-requests", {
        "employee_id": s["staff"], "title": "Chairs", "request_date": "2026-03-02", "status": "approved",
        "items": [{"product_name_snapshot": "Chair", "quantity": 1, "unit_price": amount,
                   "budget_line_id": budget["lines"]["OFF"]["id"]}]}))


def _linked_order(s, request, amount=400, status="draft"):
    return s["ok"](s["post"]("purchase-orders", {
        "employee_id": s["owner"], "vendor_id": s["vendor"], "title": "Chairs",
        "order_date": "2026-03-03", "status": status,
        "items": [{"product_name_snapshot": "Chair", "quantity": 1, "unit_price": amount,
                   "purchase_request_item_id": request["items"][0]["id"]}]}))


def _move(s, collection, document, status):
    return s["ok"](s["c"].patch(f"/api/v1/{collection}/{document['id']}", headers=s["admin"],
                                json={"status": status}), 200)


def _impact(s, entity_type, document):
    return s["ok"](s["c"].get("/api/v1/budget-impact", headers=s["admin"],
        params={"entity_type": entity_type, "entity_id": document["id"]}), 200)["lines"]


def test_request_occupation_survives_draft_and_submitted_orders(shop):
    s = shop
    budget = _spend_budget(s)
    request = _office_request(s, budget)
    order = _linked_order(s, request, amount=300)
    for state in ("draft", "submitted", "confirmed", "cancelled"):
        if state != "draft":
            _move(s, "purchase-orders", order, state)
        totals = _line(_execution(s, budget["id"]), "OFF")["totals"]
        assert (totals["requested"], totals["committed"]) == ((100, 300) if state == "confirmed" else (400, 0))
        assert totals["available"] == 600


@pytest.mark.parametrize("line_application", [False, True])
def test_reimbursement_cash_follows_expense_lines_and_reversals(shop, line_application):
    s = shop
    budget = _spend_budget(s)
    claim = s["ok"](s["post"]("expense-claims", {
        "employee_id": s["staff"], "title": "Expenses", "status": "approved", "items": [
            {"expense_date": "2026-03-05", "amount": 600, "category": "marketing"},
            {"expense_date": "2026-03-06", "amount": 400, "category": "office",
             "budget_line_id": budget["lines"]["OFF"]["id"]}]}))
    invoice = s["ok"](s["post"](f"expense-claims/{claim['id']}/invoice", {}))
    pay = s["ok"](s["post"]("payments", {"direction": "outbound", "employee_id": s["owner"],
        "payee_employee_id": s["staff"], "amount": 1000, "status": "paid"}))
    application = {"applied_to_type": "invoice", "applied_to_id": invoice["id"]}
    if line_application:
        invoice_lines = s["ok"](s["c"].get("/api/v1/invoice-items", headers=s["admin"],
                                          params={"invoice_id": invoice["id"]}), 200)
        application["invoice_item_id"] = next(i["id"] for i in invoice_lines
            if i["amount"] == 600)
    for amount, expected_total in ((500, 500), (-200, 300)):
        s["ok"](s["post"](f"payments/{pay['id']}/apply", {
            "lines": [{**application, "amount_applied": amount}]}), 200)
        result = _execution(s, budget["id"])
        assert _line(result, "MKT")["totals"]["actual"] == 600
        assert _line(result, "MKT")["totals"]["paid"] == (expected_total if line_application else expected_total * 0.6)
        assert _line(result, "OFF")["totals"]["paid"] == (0 if line_application else expected_total * 0.4)
        cash = s["ok"](s["c"].get("/api/v1/budget-cash", headers=s["admin"],
                                 params={"spend_budget_id": budget["id"]}), 200)
        assert cash["totals"]["paid"] == expected_total
        assert cash["totals"]["net_actual"] == -expected_total


def test_unpaid_credit_notes_do_not_invent_refunds(shop):
    s = shop
    budget = _spend_budget(s)
    _purchase_invoice(s, [{"invoice_item_type": "marketing", "product_name_snapshot": "Credit", "amount": -100}])
    totals = _line(_execution(s, budget["id"]), "MKT")["totals"]
    assert totals["actual"] == -100 and totals["paid"] == 0
    invoice = _purchase_invoice(s, [
        {"invoice_item_type": "marketing", "product_name_snapshot": "Ads", "amount": 1000},
        {"invoice_item_type": "marketing", "product_name_snapshot": "Discount", "amount": -100}])
    pay = s["ok"](s["post"]("payments", {"direction": "outbound", "employee_id": s["owner"],
        "vendor_id": s["vendor"], "amount": 900, "status": "paid"}))
    for amount, expected in ((450, 450), (-180, 270)):
        s["ok"](s["post"](f"payments/{pay['id']}/apply", {"lines": [
            {"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": amount}]}), 200)
        assert _line(_execution(s, budget["id"]), "MKT")["totals"]["paid"] == expected


@pytest.mark.parametrize("invoice_amount", [200, 400, 700])
def test_impact_predicts_only_the_net_change_in_occupation(shop, invoice_amount):
    s = shop
    budget = _spend_budget(s)
    request = _office_request(s, budget)
    order = _linked_order(s, request)
    impact = _impact(s, "purchase_order", order)[0]
    assert (impact["available_before"], impact["available_after"]) == (600, 600)
    _move(s, "purchase-orders", order, "submitted")
    _move(s, "purchase-orders", order, "confirmed")
    # An existing invoice takes part of the order before this draft arrives.
    _purchase_invoice(s, [{"invoice_item_type": "goods", "product_name_snapshot": "Chair", "amount": 100,
        "purchase_order_item_id": order["items"][0]["id"]}], purchase_order_id=order["id"])
    invoice = _purchase_invoice(s, [{"invoice_item_type": "goods", "product_name_snapshot": "Chair",
        "amount": invoice_amount, "purchase_order_item_id": order["items"][0]["id"]}],
        purchase_order_id=order["id"], status="draft")
    impact = _impact(s, "invoice", invoice)[0]
    expected_after = 1000 - max(400, invoice_amount + 100)
    assert (impact["available_before"], impact["available_after"]) == (600, expected_after)
    # Preview is read-only; it neither changes status nor spends the budget.
    assert _line(_execution(s, budget["id"]), "OFF")["totals"]["available"] == 600
    _move(s, "invoices", invoice, "submitted")
    _move(s, "invoices", invoice, "issued")
    assert _line(_execution(s, budget["id"]), "OFF")["totals"]["available"] == expected_after
    posted = _impact(s, "invoice", invoice)[0]
    assert posted["counted"] and posted["available_before"] == 600 and posted["available_after"] == expected_after


@pytest.mark.parametrize("currency", ["CNY", "USD"])
@pytest.mark.parametrize("post_later", [False, True])
def test_carry_forward_preserves_currency_at_posting(shop, currency, post_later):
    s = shop
    source = _spend_budget(s)
    target = s["ok"](s["post"]("budgets", {"name": "Next year", "currency": currency,
        "period_start": "2027-01-01", "period_end": "2027-12-31",
        "lines": [{"line_code": "OFF", "name": "Office", "category": "office"}]}))
    body = {"budget_id": target["id"], "source_budget_id": source["id"], "employee_id": s["owner"],
        "change_type": "carry_forward", "reason": "Year end", "status": "draft" if post_later else "posted",
        "lines": [{"line_code": "OFF", "period_month": MARCH, "amount": -1000},
                  {"line_code": "OFF", "period_month": "2027-03-01", "amount": 1000}]}
    response = s["post"]("budget-changes", body)
    if post_later:
        change = s["ok"](response)
        response = s["c"].patch(f"/api/v1/budget-changes/{change['id']}", headers=s["admin"], json={"status": "posted"})
    if currency == "USD":
        assert response.status_code == 422 and "currency" in response.text
    else:
        assert response.status_code == (200 if post_later else 201), response.text
    moved = currency == "CNY"
    assert _line(_execution(s, source["id"]), "OFF")["totals"]["planned"] == (0 if moved else 1000)
    assert _line(_execution(s, target["id"]), "OFF")["totals"]["planned"] == (1000 if moved else 0)
