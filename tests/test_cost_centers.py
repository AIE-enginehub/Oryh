"""Cost centres and budgets scoped to one — plan
docs/plans/budgets-2026-10-27.md §13.

A cost centre is master data, a tree. An employee has a home centre — a
fact the agent reads — and a spending document books against the centre its
writer names, never one the server infers. A spend budget scoped to
a centre reads that centre's share (its subtree's) of what the company
budget collects, beside it and never added to it.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant

YEAR = {"period_start": "2026-01-01", "period_end": "2026-12-31"}
MARCH = "2026-03-01"


@pytest.fixture()
def org():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Centre Co", email="owner@centre-co.example")
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

        ops = ok(post("cost-centers", {"cost_center_code": "OPS", "name": "Operations"}))["id"]
        warehouse = ok(post("cost-centers", {"cost_center_code": "WH", "name": "Warehouse", "parent_id": ops}))["id"]
        sales = ok(post("cost-centers", {"cost_center_code": "SALES", "name": "Sales"}))["id"]
        owner = ok(post("employees", {"name": "Owner"}))["id"]
        picker = ok(post("employees", {"name": "Picker", "cost_center_id": warehouse}))["id"]
        vendor = ok(post("vendors", {"name": "Supplier"}))["id"]
        yield dict(c=c, admin=admin, post=post, patch=patch, get=get, ok=ok, ops=ops, warehouse=warehouse,
                   sales=sales, owner=owner, picker=picker, vendor=vendor)


def _claim(o, employee: str, amount: float, category: str = "marketing", **extra) -> dict:
    return o["ok"](o["post"]("expense-claims", {
        "employee_id": employee, "title": "spend", "status": "approved", **extra,
        "items": [{"expense_date": "2026-03-05", "amount": amount, "category": category}]}))


def _invoice(o, items: list[dict], **extra) -> dict:
    return o["ok"](o["post"]("invoices", {
        "direction": "purchase", "employee_id": o["owner"], "vendor_id": o["vendor"], "title": "bill",
        "invoice_date": "2026-03-10", "status": "issued", "items": items, **extra}))


def _budget(o, name: str, lines: list[tuple[str, str, float]], **extra) -> dict:
    budget = o["ok"](o["post"]("budgets", {
        "name": name, **YEAR, **extra,
        "lines": [{"line_code": code, "name": code, "category": category} for code, category, _ in lines]}))
    o["ok"](o["post"]("budget-changes", {
        "budget_id": budget["id"], "employee_id": o["owner"], "reason": "plan", "status": "posted",
        "lines": [{"line_code": code, "period_month": MARCH, "amount": amount} for code, _, amount in lines]}))
    o["ok"](o["patch"](f"budgets/{budget['id']}", {"status": "active"}), 200)
    return {**budget, "lines": {line["line_code"]: line for line in budget["lines"]}}


def _totals(o, budget: dict, code: str) -> dict:
    execution = o["ok"](o["get"](f"budgets/{budget['id']}/execution"), 200)
    return next(row for row in execution["lines"] if row["line_code"] == code)["totals"]


# --- master data -------------------------------------------------------------------


def test_cost_centres_are_a_tree_every_member_reads(org) -> None:
    o = org
    duplicate = o["post"]("cost-centers", {"cost_center_code": "OPS", "name": "again"})
    assert duplicate.status_code == 409
    loop = o["patch"](f"cost-centers/{o['ops']}", {"parent_id": o["warehouse"]})
    assert loop.status_code == 422 and "under itself" in loop.text
    member = dict(invite_member(o["c"], o["admin"], "member_like", [], email="m@centre-co.example", employee="M"))
    listed = o["ok"](o["get"]("cost-centers", member), 200)
    assert {row["cost_center_code"] for row in listed} == {"OPS", "WH", "SALES"}
    assert o["post"]("cost-centers", {"cost_center_code": "X", "name": "x"}, member).status_code == 403


def test_a_document_books_against_the_centre_its_writer_names_and_no_other(org) -> None:
    o = org
    assert _claim(o, o["picker"], 50)["cost_center_id"] is None, \
        "the picker's home centre is a fact for the agent, not a default the server fills in"
    assert _claim(o, o["picker"], 50, cost_center_id=o["sales"])["cost_center_id"] == o["sales"]

    request = o["ok"](o["post"]("purchase-requests", {
        "employee_id": o["picker"], "title": "pallets", "request_date": "2026-03-02", "status": "approved",
        "cost_center_id": o["warehouse"],
        "items": [{"product_name_snapshot": "pallet", "quantity": 10, "unit_price": 20}]}))
    order = o["ok"](o["post"]("purchase-orders", {
        "employee_id": o["owner"], "vendor_id": o["vendor"], "title": "pallets", "order_date": "2026-03-03",
        "status": "confirmed", "items": [{"product_name_snapshot": "pallet", "quantity": 10, "unit_price": 20,
                                          "purchase_request_item_id": request["items"][0]["id"]}]}))
    header = o["ok"](o["get"](f"purchase-orders/{order['id']}"), 200)
    assert header["cost_center_id"] is None, "ordering a warehouse request does not book the order there by itself"
    bill = _invoice(o, [{"invoice_item_type": "goods", "product_name_snapshot": "pallet", "amount": 200,
                         "purchase_order_item_id": order["items"][0]["id"]}], purchase_order_id=order["id"])
    assert bill["cost_center_id"] is None


def test_a_centre_named_on_a_write_exists_and_is_active(org) -> None:
    o = org
    o["ok"](o["patch"](f"cost-centers/{o['sales']}", {"status": "archived"}), 200)
    archived = o["post"]("expense-claims", {"employee_id": o["owner"], "title": "x", "cost_center_id": o["sales"],
                                            "items": []})
    assert archived.status_code == 422 and "archived" in archived.text
    unknown = o["patch"](f"employees/{o['owner']}", {"cost_center_id": "00000000-0000-0000-0000-000000000000"})
    assert unknown.status_code == 422 and "does not exist" in unknown.text


# --- budgets scoped to a centre ----------------------------------------------------------


def test_a_centres_budget_reads_its_share_beside_the_company_budget(org) -> None:
    o = org
    company = _budget(o, "company", [("MKT", "marketing", 5000)])
    operations = _budget(o, "operations", [("MKT", "marketing", 2000), ("OFF", "office", 1000)],
                         cost_center_id=o["ops"])
    assert operations["cost_center_id"] == o["ops"], "activating it beside the company budget is no clash"

    _claim(o, o["picker"], 300, cost_center_id=o["warehouse"])    # under operations
    _invoice(o, [{"invoice_item_type": "marketing", "product_name_snapshot": "ads", "amount": 1200}])  # no centre
    assert _totals(o, company, "MKT")["actual"] == 1500.0, "the company budget still reads every document"
    assert _totals(o, operations, "MKT")["actual"] == 300.0, "operations reads the warehouse's share"

    _invoice(o, [{"invoice_item_type": "goods", "product_name_snapshot": "shelving", "amount": 400,
                  "budget_line_id": operations["lines"]["OFF"]["id"]}], cost_center_id=o["ops"])
    assert _totals(o, operations, "OFF")["actual"] == 400.0
    company_now = o["ok"](o["get"](f"budgets/{company['id']}/execution"), 200)
    assert company_now["unbudgeted"]["actual"] == 400.0, \
        "a centre's tag does not hide the spend from the company budget; it has no office line, so it says so"

    untagged_home = o["post"]("invoices", {
        "direction": "purchase", "employee_id": o["owner"], "vendor_id": o["vendor"], "title": "x",
        "invoice_date": "2026-03-10", "items": [{"invoice_item_type": "goods", "product_name_snapshot": "x",
                                                 "amount": 10, "budget_line_id": operations["lines"]["OFF"]["id"]}]})
    assert untagged_home.status_code == 422 and "cost centre" in untagged_home.text

    impact = o["ok"](o["get"]("budget-impact", entity_type="expense_claim",
                              entity_id=_claim(o, o["picker"], 100, status="submitted",
                                                        cost_center_id=o["warehouse"])["id"]), 200)
    assert {row["budget_id"] for row in impact["lines"]} == {company["id"], operations["id"]}


def test_one_budget_per_scope_and_period_collects_a_category(org) -> None:
    o = org
    _budget(o, "operations", [("MKT", "marketing", 2000)], cost_center_id=o["ops"])
    again = o["ok"](o["post"]("budgets", {"name": "ops again", **YEAR, "cost_center_id": o["ops"],
                                          "lines": [{"line_code": "M", "name": "M", "category": "marketing"}]}))
    clash = o["patch"](f"budgets/{again['id']}", {"status": "active"})
    assert clash.status_code == 409 and "marketing" in clash.text
    income = o["post"]("budgets", {"name": "ops sales", "direction": "income", **YEAR, "cost_center_id": o["ops"]})
    assert income.status_code == 422 and "spend" in income.text
