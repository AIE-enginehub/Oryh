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


# --- phase 2: layouts --------------------------------------------------------------------


def _management_pnl(b, **extra) -> dict:
    a = b["accounts"]
    return {
        "statement": "income_statement", "name": "Management", "confirmed_by": "Lin (finance lead)", **extra,
        "rows": [
            {"row_no": 10, "code": "revenue", "label": "Revenue", "kind": "accounts",
             "accounts": [{"ledger_account_id": a["6001"]}]},
            {"row_no": 20, "code": "cost_of_sales", "label": "Cost of sales", "kind": "accounts",
             "accounts": [{"code_from": "6401", "code_to": "6499"}]},
            {"row_no": 30, "code": "gross_profit", "label": "Gross profit", "kind": "total",
             "formula": [{"code": "revenue"}, {"code": "cost_of_sales", "sign": -1}]},
            {"row_no": 40, "code": "overheads_heading", "label": "Overheads", "kind": "heading"},
            {"row_no": 50, "code": "overheads", "label": "Overheads", "kind": "accounts",
             "accounts": [{"ledger_account_id": a["6601"]}]},
            {"row_no": 60, "code": "operating_profit", "label": "Operating profit", "kind": "total",
             "formula": [{"code": "gross_profit"}, {"code": "overheads", "sign": -1}]},
        ]}


def test_a_layout_says_gross_profit_and_lists_what_it_does_not_place(book) -> None:
    b = book
    b["post"]("2026-02-10", "1002", "6001", 1000)
    b["post"]("2026-03-05", "1002", "6001", 5000, project_id=b["site"])
    b["post"]("2026-03-06", "1002", "6051", 300)               # other income: no row takes it
    b["post"]("2026-03-07", "6401", "1002", 2000)
    b["post"]("2026-03-08", "660101", "2202", 400)             # a sub-account of 6601
    b["post"]("2026-03-09", "660102", "1002", 100)
    layout = b["ok"](b["call"]("POST", "statement-layouts", _management_pnl(b)))
    assert layout["confirmed_by"] == "Lin (finance lead)" and [r["code"] for r in layout["rows"]][2] == "gross_profit"

    plain = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31")
    assert plain["layout"] is None, "no default yet: the default statement"
    s = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31", layout_id=layout["id"])
    lines = {line["code"]: line for line in s["layout"]["lines"]}
    assert (lines["revenue"]["amount"], lines["cost_of_sales"]["amount"], lines["gross_profit"]["amount"]) == (
        5000.0, 2000.0, 3000.0)
    assert lines["overheads"]["amount"] == 500.0, "an account takes its sub-accounts"
    assert [x["account_code"] for x in lines["overheads"]["accounts"]] == ["660101", "660102"]
    assert lines["operating_profit"]["amount"] == 2500.0 and lines["overheads_heading"]["amount"] is None
    assert (lines["revenue"]["compare"], lines["gross_profit"]["compare"]) == (1000.0, 1000.0)
    assert s["layout"]["unplaced"] == [{"ledger_account_id": b["accounts"]["6051"], "account_code": "6051",
                                        "name": "Account 6051", "account_type": "income", "amount": 300.0,
                                        "compare": 0.0}]
    assert s["result"]["amount"] == 2800.0 == lines["operating_profit"]["amount"] + 300.0, \
        "the book's result is whole: a layout never makes money disappear"

    # by: every line splits, and the columns add up
    split = b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31", by="project",
                      layout_id=layout["id"], compare="none")
    revenue = {line["code"]: line for line in split["layout"]["lines"]}["revenue"]
    assert revenue["amounts"] == {b["site"]: 5000.0, "unassigned": 0.0}

    # the default layout applies without layout_id; none reads the plain statement
    b["ok"](b["call"]("PATCH", f"statement-layouts/{layout['id']}", {"is_default": True}), 200)
    assert b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31")["layout"]["id"] == layout["id"]
    assert b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31",
                     layout_id="none")["layout"] is None
    second = b["ok"](b["call"]("POST", "statement-layouts", _management_pnl(b, name="Board", is_default=True)))
    assert b["ok"](b["call"]("GET", f"statement-layouts/{layout['id']}"), 200)["is_default"] is False, \
        "one default per statement"
    archived = b["ok"](b["call"]("PATCH", f"statement-layouts/{second['id']}", {"status": "archived"}), 200)
    assert archived["is_default"] is False
    assert b["read"]("income-statement", date_from="2026-03-01", date_to="2026-03-31")["layout"] is None
    assert len(b["read"]("statement-layouts", statement="income_statement", status="active")) == 1


def test_a_balance_sheet_layout_places_the_unclosed_earnings(book) -> None:
    b = book
    a = b["accounts"]
    b["post"]("2026-03-01", "1002", "4001", 10000)
    b["post"]("2026-03-07", "1122", "6001", 1200)
    b["post"]("2026-03-08", "6401", "2202", 700)
    body = {"statement": "balance_sheet", "name": "Small enterprise", "confirmed_by": "Lin",
            "rows": [
                {"row_no": 1, "code": "assets", "label": "Total assets", "kind": "accounts",
                 "accounts": [{"code_from": "1000", "code_to": "1999"}]},
                {"row_no": 2, "code": "payables", "label": "Payables", "kind": "accounts",
                 "accounts": [{"ledger_account_id": a["2202"]}]},
                {"row_no": 3, "code": "capital", "label": "Paid-in capital", "kind": "accounts",
                 "accounts": [{"ledger_account_id": a["4001"]}]},
                {"row_no": 4, "code": "undistributed", "label": "Undistributed profit", "kind": "accounts",
                 "accounts": [{"ledger_account_id": a["4104"]}, {"earnings_not_yet_closed": True}]},
                {"row_no": 5, "code": "claims", "label": "Liabilities and equity", "kind": "total",
                 "formula": [{"code": "payables"}, {"code": "capital"}, {"code": "undistributed"}]}]}
    layout = b["ok"](b["call"]("POST", "statement-layouts", body))
    sheet = b["read"]("balance-sheet", as_of="2026-03-31", layout_id=layout["id"])
    lines = {line["code"]: line for line in sheet["layout"]["lines"]}
    assert (lines["assets"]["amount"], lines["undistributed"]["amount"], lines["claims"]["amount"]) == (
        11200.0, 500.0, 11200.0)
    assert sheet["layout"]["unplaced"] == [] and sheet["balanced"] is True
    assert lines["claims"]["compare"] == 0.0

    # without the earnings reference, they are unplaced — and said so
    body["rows"][3]["accounts"] = [{"ledger_account_id": a["4104"]}]
    b["ok"](b["call"]("PUT", f"statement-layouts/{layout['id']}/rows",
                      {"rows": body["rows"], "confirmed_by": "Lin"}), 200)
    sheet = b["read"]("balance-sheet", as_of="2026-03-31", layout_id=layout["id"])
    assert sheet["layout"]["unplaced"] == [{"key": "earnings_not_yet_closed", "name": "Earnings not yet closed",
                                            "amount": 500.0}]
    # an income statement read refuses a balance sheet layout
    response = b["call"]("GET", "income-statement", layout_id=layout["id"])
    assert response.status_code == 422 and "balance sheet layout" in response.text


def test_the_write_checks_refuse_a_wrong_statement_naming_the_row(book) -> None:
    b = book
    a = b["accounts"]

    def refused(rows, word, statement="income_statement"):
        response = b["call"]("POST", "statement-layouts", {"statement": statement, "name": "x",
                                                           "confirmed_by": "Lin", "rows": rows})
        assert response.status_code == 422 and word in response.text, response.text

    revenue = {"row_no": 1, "code": "revenue", "label": "Revenue", "kind": "accounts",
               "accounts": [{"ledger_account_id": a["6001"]}]}
    refused([revenue, {"row_no": 2, "code": "gp", "label": "GP", "kind": "total",
                       "formula": [{"code": "cost"}]}], "'cost'")
    refused([{"row_no": 1, "code": "x", "label": "X", "kind": "total", "formula": [{"code": "y"}]},
             {"row_no": 2, "code": "y", "label": "Y", "kind": "total", "formula": [{"code": "x"}]}], "circle")
    refused([revenue, {"row_no": 2, "code": "h", "label": "H", "kind": "heading"},
             {"row_no": 3, "code": "t", "label": "T", "kind": "total", "formula": [{"code": "h"}]}], "heading")
    refused([{"row_no": 1, "code": "cash", "label": "Cash", "kind": "accounts",
              "accounts": [{"ledger_account_id": a["1002"]}]}], "asset")
    refused([{"row_no": 1, "code": "all", "label": "All", "kind": "accounts",
              "accounts": [{"code_from": "1000", "code_to": "6999"}]}], "range")
    refused([revenue, {"row_no": 2, "code": "again", "label": "Again", "kind": "accounts",
                       "accounts": [{"code_from": "6000", "code_to": "6050"}]}], "feeds revenue and again")
    refused([{"row_no": 1, "code": "oh", "label": "OH", "kind": "accounts",
              "accounts": [{"ledger_account_id": a["6601"]}]},
             {"row_no": 2, "code": "rent", "label": "Rent", "kind": "accounts",
              "accounts": [{"ledger_account_id": a["660101"]}]}], "660101 feeds oh and rent")
    refused([{"row_no": 1, "code": "a", "label": "A", "kind": "accounts",
              "accounts": [{"code_from": "6400", "code_to": "6500"}]},
             {"row_no": 2, "code": "b", "label": "B", "kind": "accounts",
              "accounts": [{"code_from": "6450", "code_to": "6700"}]}], "overlap")
    refused([revenue, {"row_no": 1, "code": "other", "label": "Other", "kind": "heading"}], "row_no 1")
    refused([{"row_no": 1, "code": "e", "label": "E", "kind": "accounts",
              "accounts": [{"earnings_not_yet_closed": True}]}], "balance sheet line")
    refused([{"row_no": 1, "code": "e", "label": "E", "kind": "accounts",
              "accounts": [{"ledger_account_id": a["6001"], "code_from": "6001", "code_to": "6001"}]}], "one of")
    response = b["call"]("POST", "statement-layouts", {"statement": "income_statement", "name": "x",
                                                       "confirmed_by": "  ", "rows": [revenue]})
    assert response.status_code == 422 and "confirmed_by" in response.text

    # who may write and read
    layout = b["ok"](b["call"]("POST", "statement-layouts", {"statement": "income_statement", "name": "ok",
                                                             "confirmed_by": "Lin", "rows": [revenue]}))
    reader = invite_member(b["c"], b["admin"], "owner_reader", ["ledger.read"], email="r@statement-co.example",
                           employee="Reader")
    who = {"X-API-Key": reader["X-API-Key"]}
    assert b["call"]("GET", f"statement-layouts/{layout['id']}", who=who).status_code == 200
    assert b["call"]("PATCH", f"statement-layouts/{layout['id']}", {"name": "mine"}, who=who).status_code == 403
    assert b["call"]("POST", "statement-layouts", {"statement": "income_statement", "name": "x",
                                                   "confirmed_by": "Lin", "rows": [revenue]},
                     who=who).status_code == 403


def test_replacing_rows_is_audited_with_before_and_after(book) -> None:
    b = book
    a = b["accounts"]
    layout = b["ok"](b["call"]("POST", "statement-layouts", _management_pnl(b)))
    rows = [{"row_no": 1, "code": "revenue", "label": "Turnover", "kind": "accounts",
             "accounts": [{"code_from": "6001", "code_to": "6099"}]}]
    updated = b["ok"](b["call"]("PUT", f"statement-layouts/{layout['id']}/rows",
                                {"rows": rows, "confirmed_by": "Wu (auditor)"}), 200)
    assert [r["label"] for r in updated["rows"]] == ["Turnover"] and updated["confirmed_by"] == "Wu (auditor)"
    logs = b["read"]("audit-logs", action="ledger.layout_rows_replaced", entity_id=layout["id"])
    detail = logs[0]["detail_jsonb"] if "detail_jsonb" in logs[0] else logs[0]["detail"]
    assert len(detail["before"]) == 6 and detail["after"][0]["label"] == "Turnover"
    assert b["call"]("PUT", f"statement-layouts/{layout['id']}/rows",
                     {"rows": [{**rows[0], "accounts": [{"ledger_account_id": a["1002"]}]}],
                      "confirmed_by": "Wu"}).status_code == 422


# --- phase 3: the cash summary -------------------------------------------------------------


def test_the_cash_summary_follows_the_money_by_the_other_side(book) -> None:
    b = book
    a = b["accounts"]
    assert b["ok"](b["call"]("PATCH", f"ledger-accounts/{a['1002']}", {"is_cash": True}), 200)["is_cash"] is True
    till = b["ok"](b["call"]("POST", "ledger-accounts", {"account_code": "1001", "name": "Cash on hand",
                                                          "account_type": "asset", "is_cash": True}))
    a["1001"] = till["id"]
    b["post"]("2026-02-20", "1002", "4001", 10000)                   # capital, in February
    b["post"]("2026-03-02", "1002", "6001", 5000)                    # a cash sale
    b["post"]("2026-03-03", "1122", "6001", 1200)                    # a credit sale: no cash yet
    b["post"]("2026-03-10", "1002", "1122", 1200)                    # collected
    b["post"]("2026-03-04", "6401", "2202", 700)                     # bought on credit: no cash
    b["post"]("2026-03-15", "2202", "1002", 700)                     # paid
    b["post"]("2026-03-20", "1001", "1002", 300)                     # to the till: a transfer
    b["ok"](b["call"]("POST", "journal-entries", {                   # 100 collected less a 5 fee
        "posting_date": "2026-03-21", "description": "collected net of fee", "status": "posted",
        "lines": [{"ledger_account_id": a["1002"], "debit": 95}, {"ledger_account_id": a["660102"], "debit": 5},
                  {"ledger_account_id": a["1122"], "credit": 100}]}))

    s = b["read"]("cash-summary", date_from="2026-03-01", date_to="2026-03-31")
    assert (s["opening"], s["net_change"], s["closing"], s["reconciled"]) == (10000.0, 5595.0, 15595.0, True)
    assert s["transfers"] == {"count": 1, "amount": 300.0}
    assert [(c["account_code"], c["closing"]) for c in s["cash_accounts"]] == [("1001", 300.0), ("1002", 15295.0)]
    sections = {section["key"]: section for section in s["sections"]}
    assert [r["net"] for r in sections["income"]["rows"]] == [5000.0]
    assert sections["asset"]["rows"][0] == {
        "ledger_account_id": a["1122"], "account_code": "1122", "name": "Account 1122", "received": 1300.0,
        "paid": 0.0, "net": 1300.0, "compare": 0.0, "change": 1300.0, "change_ratio": None}
    assert (sections["liability"]["net"], sections["expense"]["net"]) == (-700.0, -5.0)
    assert sections["equity"]["net"] == 0.0 and sections["equity"]["compare"] == 10000.0, \
        "February's capital shows only as the comparison"
    assert s["net_change_compare"] == 10000.0 and "transfer" in s["basis"]

    # a cash_summary layout: operating and financing lines
    layout = b["ok"](b["call"]("POST", "statement-layouts", {
        "statement": "cash_summary", "name": "Direct method", "confirmed_by": "Lin", "is_default": True,
        "rows": [{"row_no": 1, "code": "operating", "label": "Operating", "kind": "accounts",
                  "accounts": [{"code_from": "1100", "code_to": "3999"}, {"code_from": "6000", "code_to": "6999"}]},
                 {"row_no": 2, "code": "financing", "label": "Financing", "kind": "accounts",
                  "accounts": [{"ledger_account_id": a["4001"]}]},
                 {"row_no": 3, "code": "net", "label": "Net change in cash", "kind": "total",
                  "formula": [{"code": "operating"}, {"code": "financing"}]}]}))
    laid = b["read"]("cash-summary", date_from="2026-03-01", date_to="2026-03-31")
    lines = {line["code"]: line for line in laid["layout"]["lines"]}
    assert laid["layout"]["id"] == layout["id"] and laid["layout"]["unplaced"] == []
    assert (lines["operating"]["amount"], lines["financing"]["amount"], lines["net"]["amount"]) == (
        5595.0, 0.0, 5595.0)
    assert (lines["financing"]["compare"], lines["net"]["compare"]) == (10000.0, 10000.0)

    cash = b["read"]("ledger-accounts", is_cash="true")
    assert sorted(x["account_code"] for x in cash) == ["1001", "1002"]
    assert "1002" not in {x["account_code"] for x in b["read"]("ledger-accounts", is_cash="false")}


def test_only_an_asset_holds_cash_and_no_cash_accounts_is_said(book) -> None:
    b = book
    a = b["accounts"]
    response = b["call"]("PATCH", f"ledger-accounts/{a['6001']}", {"is_cash": True})
    assert response.status_code == 422 and "only an asset" in response.text
    response = b["call"]("POST", "ledger-accounts", {"account_code": "2299", "name": "x",
                                                     "account_type": "liability", "is_cash": True})
    assert response.status_code == 422
    b["post"]("2026-03-02", "1002", "6001", 5000)
    s = b["read"]("cash-summary", date_from="2026-03-01", date_to="2026-03-31", compare="none")
    assert (s["cash_accounts"], s["sections"], s["net_change"], s["reconciled"]) == ([], [], 0.0, True)
    # the sub-account of a cash account is cash too, without its own flag
    banks = b["ok"](b["call"]("POST", "ledger-accounts", {"account_code": "1012", "name": "Banks",
                                                           "account_type": "asset", "is_cash": True}))
    sub = b["ok"](b["call"]("POST", "ledger-accounts", {"account_code": "101201", "name": "Bank USD",
                                                         "account_type": "asset", "parent_id": banks["id"]}))
    assert sub["is_cash"] is False
    b["ok"](b["call"]("POST", "journal-entries", {
        "posting_date": "2026-03-05", "description": "sale into the sub-account", "status": "posted",
        "lines": [{"ledger_account_id": sub["id"], "debit": 40}, {"ledger_account_id": a["6001"], "credit": 40}]}))
    s = b["read"]("cash-summary", date_from="2026-03-01", date_to="2026-03-31", compare="none")
    assert s["net_change"] == 40.0
    assert [(c["account_code"], c["depth"], c["closing"]) for c in s["cash_accounts"]] == [
        ("1012", 0, 40.0), ("101201", 1, 40.0)], "a summary carries its sub-accounts"
    assert s["closing"] == 40.0, "and the total counts them once"
