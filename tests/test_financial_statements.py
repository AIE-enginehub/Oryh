"""Financial statements — plan docs/plans/financial-statements-2026-11-25.md, phase 1.

The income statement and the balance sheet are sums of posted journal lines,
grouped by account type and the chart's tree, derived on every read. The
server adds up and checks; the layout of a statutory format and the reasons
behind a movement are the agent's.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def book():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Statement Co", email="owner@statement-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, who: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=who or admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        ok(call("PUT", "accounting-settings", {"functional_currency": "CNY"}), 200)
        accounts: dict[str, str] = {}
        for code, kind, parent in (("1002", "asset", None), ("1122", "asset", None), ("2202", "liability", None),
                                   ("4001", "equity", None), ("4104", "equity", None), ("6001", "income", None),
                                   ("6051", "income", None), ("6401", "expense", None), ("6601", "expense", None),
                                   ("660101", "expense", "6601"), ("660102", "expense", "6601")):
            body = {"account_code": code, "name": f"Account {code}", "account_type": kind}
            if parent:
                body["parent_id"] = accounts[parent]
            accounts[code] = ok(call("POST", "ledger-accounts", body))["id"]
        site = ok(call("POST", "projects", {"project_name": "Warehouse fit-out", "project_code": "P-7"}))["id"]

        def post(day: str, debit: str, credit: str, amount: float, status: str = "posted", **dims) -> dict:
            return ok(call("POST", "journal-entries", {
                "posting_date": day, "description": f"{debit}/{credit}", "status": status,
                "lines": [{"ledger_account_id": accounts[debit], "debit": amount, **dims},
                          {"ledger_account_id": accounts[credit], "credit": amount, **dims}]}))

        def read(path: str, **params) -> dict:
            return ok(call("GET", path, **params), 200)

        yield dict(c=c, admin=admin, call=call, ok=ok, post=post, read=read, accounts=accounts, site=site)


def _rows(section: dict) -> dict[str, dict]:
    return {row["account_code"]: row for row in section["rows"]}


def test_the_income_statement_sums_the_book_on_each_side(book) -> None:
    b = book
    b["post"]("2026-02-10", "1002", "6001", 1000)              # February sales
    b["post"]("2026-03-05", "1002", "6001", 5000)              # March sales
    b["post"]("2026-03-06", "1002", "6051", 300)               # other income
    b["post"]("2026-03-07", "6401", "1002", 2000)              # cost of sales
    b["post"]("2026-03-08", "660101", "2202", 400)             # rent
    b["post"]("2026-03-09", "660102", "1002", 100)             # fees
    b["post"]("2026-03-20", "660102", "1002", 999, status="draft")
    s = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31")
    income, expense = s["sections"]
    assert (income["key"], income["total"], expense["total"]) == ("income", 5300.0, 2500.0)
    assert s["result"] == {"amount": 2800.0, "compare": 1000.0, "change": 1800.0, "change_ratio": 1.8}
    assert s["compare"] == {"date_from": "2026-02-01", "date_to": "2026-02-28"}, "whole months shift by months"
    rows = _rows(expense)
    assert rows["6601"]["summary"] and rows["6601"]["amount"] == 500.0 and rows["660101"]["depth"] == 1
    assert [r["account_code"] for r in expense["rows"]] == ["6401", "6601", "660101", "660102"]
    assert (_rows(income)["6001"]["compare"], _rows(income)["6001"]["change"]) == (1000.0, 4000.0)
    assert _rows(income)["6051"]["change_ratio"] is None, "nothing to compare with is not an infinite change"
    assert s["drafts"] == 1 and s["currency"] == "CNY"
    assert s["period_status"]["open_months"] == ["2026-03-01"]
    assert s["coverage"] == [{"period": "2026-03-01", "missing": 0, "stale": 0}]


def test_a_reversed_pair_nets_to_nothing_and_the_sheet_balances(book) -> None:
    b = book
    b["post"]("2026-03-01", "1002", "4001", 10000)              # capital paid in
    wrong = b["post"]("2026-03-05", "1122", "6001", 800)
    b["ok"](b["call"]("POST", f"journal-entries/{wrong['id']}/reverse", {"posting_date": "2026-03-06"}))
    b["post"]("2026-03-07", "1122", "6001", 1200)
    b["post"]("2026-03-08", "6401", "2202", 700)
    s = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31", compare="none")
    assert s["result"] == {"amount": 500.0} and s["compare"] is None
    sheet = b["read"]("balance-sheet", as_of="2026-03-31")
    assets, liabilities, equity = sheet["sections"]
    assert (assets["total"], liabilities["total"]) == (11200.0, 700.0)
    assert equity["earnings_not_yet_closed"]["amount"] == 500.0, "the income result is the unclosed earnings"
    assert equity["total"] == 10500.0 and sheet["balanced"] is True
    assert sheet["totals"] == {"assets": 11200.0, "liabilities_and_equity": 11200.0}
    assert sheet["compare"] == {"as_of": "2026-02-28"} and assets["compare"] == 0.0

    # the agent closes the year into retained earnings: the line moves, the sheet still balances
    b["ok"](b["call"]("POST", "journal-entries", {
        "posting_date": "2026-03-31", "description": "close the year", "status": "posted",
        "lines": [{"ledger_account_id": b["accounts"]["6001"], "debit": 1200},
                  {"ledger_account_id": b["accounts"]["6401"], "credit": 700},
                  {"ledger_account_id": b["accounts"]["4104"], "credit": 500}]}))
    closed = b["read"]("balance-sheet", as_of="2026-03-31", compare="none")
    equity = closed["sections"][2]
    assert equity["earnings_not_yet_closed"]["amount"] == 0.0 and _rows(equity)["4104"]["amount"] == 500.0
    assert closed["balanced"] is True and equity["total"] == 10500.0


def test_by_splits_every_figure_and_the_columns_add_up(book) -> None:
    b = book
    b["post"]("2026-03-05", "1122", "6001", 900, project_id=b["site"])
    b["post"]("2026-03-06", "1122", "6001", 100)
    b["post"]("2026-04-02", "6401", "2202", 250, project_id=b["site"])
    s = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-04-30", by="project")
    assert [(c["key"], c["label"], c["code"]) for c in s["columns"]] == [
        (b["site"], "Warehouse fit-out", "P-7"), ("unassigned", "Unassigned", None)]
    sales = _rows(s["sections"][0])["6001"]
    assert sales["amounts"] == {b["site"]: 900.0, "unassigned": 100.0} and sales["amount"] == 1000.0
    assert s["result"]["amounts"] == {b["site"]: 650.0, "unassigned": 100.0}
    assert s["result"]["amount"] == sum(s["result"]["amounts"].values())
    months = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-05-31", by="month", compare="none")
    assert [c["key"] for c in months["columns"]] == ["2026-03-01", "2026-04-01", "2026-05-01"]
    assert months["result"]["amounts"] == {"2026-03-01": 1000.0, "2026-04-01": -250.0, "2026-05-01": 0.0}
    assert len(months["coverage"]) == 3


def test_spans_year_start_and_previous_year(book) -> None:
    b = book
    b["ok"](b["call"]("PUT", "accounting-settings", {"functional_currency": "CNY", "fiscal_year_start_month": 4}),
            200)
    assert b["read"]("accounting-settings")["fiscal_year_start_month"] == 4
    b["post"]("2025-03-15", "1002", "6001", 70)
    b["post"]("2026-03-15", "1002", "6001", 100)
    b["post"]("2025-04-15", "1002", "6001", 40)
    s = b["read"]("income-statement", date_from="year_start", date_to="2026-03-31", compare="previous_year")
    assert (s["date_from"], s["date_to"]) == ("2025-04-01", "2026-03-31")
    assert s["compare"] == {"date_from": "2024-04-01", "date_to": "2025-03-31"}
    assert (s["result"]["amount"], s["result"]["compare"]) == (140.0, 70.0)
    days = b["read"]("income-statement", date_from="2026-03-10", date_to="2026-03-19")
    assert days["compare"] == {"date_from": "2026-02-28", "date_to": "2026-03-09"}, "a span of days shifts by days"
    one_month = b["read"]("income-statement", date_to="2026-03-31")
    assert (one_month["date_from"], one_month["result"]["amount"]) == ("2026-03-01", 100.0)
    leap = b["read"]("balance-sheet", as_of="2028-02-29", compare="previous_year")
    assert leap["compare"] == {"as_of": "2027-02-28"}
    # unchanged when omitted
    b["ok"](b["call"]("PUT", "accounting-settings", {"functional_currency": "CNY"}), 200)
    assert b["read"]("accounting-settings")["fiscal_year_start_month"] == 4


def test_bad_parameters_and_who_may_read(book) -> None:
    b = book
    for params, word in (({"compare": "last_week"}, "compare"), ({"by": "project,month"}, "by"),
                         ({"date_from": "March"}, "date_from"),
                         ({"date_from": "2026-03-31", "date_to": "2026-03-01"}, "before")):
        response = b["call"]("GET", "income-statement", **params)
        assert response.status_code == 422 and word in response.text, response.text
    assert b["call"]("PUT", "accounting-settings", {"functional_currency": "CNY",
                                                     "fiscal_year_start_month": 13}).status_code == 422
    member = invite_member(b["c"], b["admin"], "member", [], email="m@statement-co.example", employee="Member")
    for path in ("income-statement", "balance-sheet"):
        assert b["call"]("GET", path, who={"X-API-Key": member["X-API-Key"]}).status_code == 403
    reader = invite_member(b["c"], b["admin"], "owner_reader", ["ledger.read"], email="r@statement-co.example",
                           employee="Reader")
    for path in ("income-statement", "balance-sheet"):
        assert b["call"]("GET", path, who={"X-API-Key": reader["X-API-Key"]}).status_code == 200
