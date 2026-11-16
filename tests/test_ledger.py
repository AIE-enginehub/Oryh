"""The book — plan docs/plans/accounting-core-2026-11-08.md, phase 1.

The server holds the book to its shape and nothing else: an entry balances,
posts to accounts that take lines, names the party its account keeps a
subledger for, converts at the rate it states, records a source fact once,
is never edited once posted, and never lands in a closed month. Which
account a document posts to is the workspace's rule, applied by an agent.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant

MARCH = "2026-03-10"


@pytest.fixture()
def books():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Book Co", email="owner@book-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, who: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=who or admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        def account(code: str, account_type: str, **extra) -> str:
            return ok(call("POST", "ledger-accounts", {"account_code": code, "name": code,
                                                       "account_type": account_type, **extra}))["id"]

        customer = ok(call("POST", "customers", {"name": "Huaxin"}))["id"]
        invoice = ok(call("POST", "invoices", {
            "direction": "sales", "employee_id": ok(call("POST", "employees", {"name": "Clerk"}))["id"],
            "customer_id": customer, "title": "March goods",
            "items": [{"invoice_item_type": "goods", "product_name_snapshot": "tea", "amount": 1130}]}))["id"]
        yield dict(c=c, admin=admin, call=call, ok=ok, account=account, customer=customer, invoice=invoice)


def _set_up(b) -> dict:
    b["ok"](b["call"]("PUT", "accounting-settings", {"functional_currency": "CNY"}), 200)
    return {
        "bank": b["account"]("1002", "asset"),
        "receivable": b["account"]("1122", "asset", subledger="customer"),
        "revenue": b["account"]("6001", "income"),
        "vat": b["account"]("2221", "liability"),
    }


def _sale(b, a, *, status="posted", day=MARCH, **extra) -> dict:
    return {
        "posting_date": day, "description": "March goods issued", "status": status,
        "source_type": "invoice", "source_id": b["invoice"], "source_event": "issued", **extra,
        "lines": [
            {"ledger_account_id": a["receivable"], "debit": 1130, "customer_id": b["customer"]},
            {"ledger_account_id": a["revenue"], "credit": 1000},
            {"ledger_account_id": a["vat"], "credit": 130},
        ],
    }


def test_nothing_posts_before_the_books_have_a_currency(books) -> None:
    b = books
    bank, revenue = b["account"]("1002", "asset"), b["account"]("6001", "income")
    early = b["call"]("POST", "journal-entries", {"posting_date": MARCH, "description": "x", "lines": [
        {"ledger_account_id": bank, "debit": 10}, {"ledger_account_id": revenue, "credit": 10}]})
    assert early.status_code == 409 and "accounting-settings" in early.text
    assert b["ok"](b["call"]("GET", "accounting-settings"), 200) is None


def test_an_entry_balances_and_names_the_party_its_account_keeps(books) -> None:
    b = books
    a = _set_up(b)
    lopsided = _sale(b, a)
    lopsided["lines"][1]["credit"] = 999
    refused = b["call"]("POST", "journal-entries", lopsided)
    assert refused.status_code == 422 and "does not balance" in refused.text
    nameless = _sale(b, a)
    del nameless["lines"][0]["customer_id"]
    refused = b["call"]("POST", "journal-entries", nameless)
    assert refused.status_code == 422 and "customer subledger" in refused.text
    both = _sale(b, a)
    both["lines"][1]["debit"] = 1
    assert b["call"]("POST", "journal-entries", both).status_code == 422, "a line is a debit or a credit"
    entry = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a)))
    assert (entry["status"], entry["total"], len(entry["lines"])) == ("posted", 1130.0, 3)
    assert entry["entry_no"].startswith("JE-") and entry["posted_at"]


def test_a_summary_account_takes_no_lines_and_an_account_with_lines_keeps_its_identity(books) -> None:
    b = books
    a = _set_up(b)
    expenses = b["account"]("6600", "expense")
    office = b["account"]("6602", "expense", parent_id=expenses)
    wrong_type = b["call"]("POST", "ledger-accounts", {"account_code": "6603", "name": "x",
                                                       "account_type": "asset", "parent_id": expenses})
    assert wrong_type.status_code == 422 and "shares its type" in wrong_type.text
    summary = b["call"]("POST", "journal-entries", {"posting_date": MARCH, "description": "x", "status": "posted",
                                                    "lines": [{"ledger_account_id": expenses, "debit": 10},
                                                              {"ledger_account_id": a["bank"], "credit": 10}]})
    assert summary.status_code == 422 and "sub-accounts" in summary.text
    b["ok"](b["call"]("POST", "journal-entries", {"posting_date": MARCH, "description": "paper", "status": "posted",
                                                  "lines": [{"ledger_account_id": office, "debit": 10},
                                                            {"ledger_account_id": a["bank"], "credit": 10}]}))
    under = b["call"]("POST", "ledger-accounts", {"account_code": "6602.1", "name": "x", "account_type": "expense",
                                                  "parent_id": office})
    assert under.status_code == 409 and "carries lines" in under.text
    recoded = b["call"]("PATCH", f"ledger-accounts/{office}", {"account_type": "asset"})
    assert recoded.status_code == 409 and "account_type" in recoded.text
    b["ok"](b["call"]("PATCH", f"ledger-accounts/{office}", {"name": "Office supplies", "status": "archived"}), 200)
    archived = b["call"]("POST", "journal-entries", {"posting_date": MARCH, "description": "x", "lines": [
        {"ledger_account_id": office, "debit": 1}, {"ledger_account_id": a["bank"], "credit": 1}]})
    assert archived.status_code == 422 and "archived" in archived.text
    currency = b["call"]("PUT", "accounting-settings", {"functional_currency": "USD"})
    assert currency.status_code == 409 and "no longer changes" in currency.text


def test_a_source_fact_posts_once_and_a_correction_is_a_reversal(books) -> None:
    b = books
    a = _set_up(b)
    first = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a)))
    again = b["call"]("POST", "journal-entries", _sale(b, a))
    assert again.status_code == 409 and first["entry_no"] in again.text
    assert b["call"]("PATCH", f"journal-entries/{first['id']}", {"description": "x"}).status_code == 409
    assert b["call"]("DELETE", f"journal-entries/{first['id']}").status_code == 409

    reversal = b["ok"](b["call"]("POST", f"journal-entries/{first['id']}/reverse", {"posting_date": "2026-03-20"}))
    assert reversal["reverses_entry_id"] == first["id"]
    assert [(l["debit"], l["credit"]) for l in reversal["lines"]] == [(0.0, 1130.0), (1000.0, 0.0), (130.0, 0.0)]
    assert b["call"]("POST", f"journal-entries/{first['id']}/reverse", {}).status_code == 409
    assert b["call"]("POST", f"journal-entries/{reversal['id']}/reverse", {}).status_code == 409
    b["ok"](b["call"]("POST", "journal-entries", _sale(b, a, day="2026-03-21")))
    listed = b["ok"](b["call"]("GET", "journal-entries", source_type="invoice", source_id=b["invoice"]), 200)
    assert len(listed) == 2, "what this invoice put in the book: the reversed posting and the one that stands"


def test_a_draft_is_checked_by_a_person_then_posted(books) -> None:
    b = books
    a = _set_up(b)
    draft = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a, status="draft")))
    assert draft["status"] == "draft" and draft["posted_at"] is None
    changed = _sale(b, a)["lines"]
    changed[1]["credit"], changed[2]["credit"] = 1001, 129
    b["ok"](b["call"]("PATCH", f"journal-entries/{draft['id']}", {"lines": changed}), 200)
    posted = b["ok"](b["call"]("POST", f"journal-entries/{draft['id']}/post"), 200)
    assert posted["status"] == "posted" and [l["credit"] for l in posted["lines"]][1:] == [1001.0, 129.0]
    discard = b["ok"](b["call"]("POST", "journal-entries", {**_sale(b, a, status="draft"), "source_event": "x"}))
    assert b["call"]("DELETE", f"journal-entries/{discard['id']}").status_code == 204


def test_a_closed_month_takes_nothing_until_it_is_reopened_with_a_reason(books) -> None:
    b = books
    a = _set_up(b)
    draft = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a, status="draft")))
    blocked = b["call"]("POST", "accounting-periods/close", {"period": "2026-03-31"})
    assert blocked.status_code == 409 and draft["entry_no"] in blocked.text, "a draft there could never post"
    b["ok"](b["call"]("POST", f"journal-entries/{draft['id']}/post"), 200)
    closed = b["ok"](b["call"]("POST", "accounting-periods/close", {"period": "2026-03-31"}), 200)
    assert (closed["period_start"], closed["status"]) == ("2026-03-01", "closed")
    late = b["call"]("POST", f"journal-entries/{draft['id']}/reverse", {"posting_date": "2026-03-25"})
    assert late.status_code == 409 and "2026-03 is closed" in late.text
    assert b["call"]("POST", f"journal-entries/{draft['id']}/reverse", {"posting_date": "2026-04-02"}).status_code == 201
    assert b["call"]("POST", "accounting-periods/reopen", {"period": "2026-03-01"}).status_code == 422
    reopened = b["ok"](b["call"]("POST", "accounting-periods/reopen",
                                 {"period": "2026-03-01", "reason": "late supplier bill"}), 200)
    assert reopened["status"] == "open"


def test_the_trial_balance_balances_and_summaries_carry_their_sub_accounts(books) -> None:
    b = books
    a = _set_up(b)
    cash = b["account"]("1001", "asset")
    petty = b["account"]("1001.01", "asset", parent_id=cash)
    b["ok"](b["call"]("POST", "journal-entries", _sale(b, a, day="2026-02-10")))
    b["ok"](b["call"]("POST", "journal-entries", {
        "posting_date": MARCH, "description": "Huaxin paid", "status": "posted",
        "lines": [{"ledger_account_id": petty, "debit": 1130},
                  {"ledger_account_id": a["receivable"], "credit": 1130, "customer_id": b["customer"]}]}))
    tb = b["ok"](b["call"]("GET", "trial-balance", date_from="2026-03-01", date_to="2026-03-31"), 200)
    rows = {row["account_code"]: row for row in tb["rows"]}
    assert tb["totals"]["debit"] == tb["totals"]["credit"] == 1130.0
    assert (rows["1122"]["opening"], rows["1122"]["credit"], rows["1122"]["closing"]) == (1130.0, 1130.0, 0.0)
    assert rows["1001"]["summary"] and rows["1001"]["closing"] == rows["1001.01"]["closing"] == 1130.0
    assert rows["6001"]["natural_closing"] == 1000.0, "income reads positive on its own side"

    ledger = b["ok"](b["call"]("GET", f"ledger-accounts/{a['receivable']}/ledger", date_from="2026-03-01",
                               date_to="2026-03-31"), 200)
    assert (ledger["opening"], [l["balance"] for l in ledger["lines"]], ledger["closing"]) == (1130.0, [0.0], 0.0)
    owed = b["ok"](b["call"]("GET", f"ledger-accounts/{a['receivable']}/parties", as_of="2026-02-28"), 200)
    assert owed == [{"customer_id": b["customer"], "debit": 1130.0, "credit": 0.0, "balance": 1130.0}]


def test_a_converted_line_carries_its_rate_and_the_arithmetic_holds(books) -> None:
    b = books
    a = _set_up(b)
    usd = b["account"]("1002.02", "asset", currency="USD")
    def entry(amount):
        return {"posting_date": MARCH, "description": "USD receipt", "status": "posted", "lines": [
            {"ledger_account_id": usd, "debit": amount, "currency": "USD", "foreign_amount": 100, "exchange_rate": 7.1},
            {"ledger_account_id": a["revenue"], "credit": amount}]}
    wrong = b["call"]("POST", "journal-entries", entry(700))
    assert wrong.status_code == 422 and "710.00" in wrong.text
    bare = b["call"]("POST", "journal-entries", {**entry(710), "lines": [
        {"ledger_account_id": usd, "debit": 710}, {"ledger_account_id": a["revenue"], "credit": 710}]})
    assert bare.status_code == 422 and "kept in USD" in bare.text
    b["ok"](b["call"]("POST", "journal-entries", entry(710)))


def test_the_book_is_read_and_written_only_with_its_grants(books) -> None:
    b = books
    a = _set_up(b)
    stranger = dict(invite_member(b["c"], b["admin"], "member_like", [], email="m@book-co.example", employee="M"))
    assert b["call"]("GET", "ledger-accounts", who=stranger).status_code == 403
    assert b["call"]("GET", "trial-balance", who=stranger).status_code == 403
    reader = dict(invite_member(b["c"], b["admin"], "auditor", ["ledger.read"], email="r@book-co.example",
                                employee="R"))
    assert b["call"]("GET", "trial-balance", who=reader).status_code == 200
    assert b["call"]("POST", "journal-entries", _sale(b, a), who=reader).status_code == 403
    bookkeeper = dict(invite_member(b["c"], b["admin"], "bookkeeper", ["ledger.post"], email="k@book-co.example",
                                    employee="K"))
    assert b["call"]("GET", "journal-entries", who=bookkeeper).status_code == 200, "posting implies reading"
    assert b["call"]("POST", "accounting-periods/close", {"period": MARCH}, who=bookkeeper).status_code == 403


def _audit(names: tuple[str, ...]) -> dict[str, int]:
    import pathlib

    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    checks = dict(namespace["STRUCTURAL_CHECKS"])
    db = next(app.dependency_overrides[get_db]())
    try:
        return {name: db.execute(sql_text(checks[name])).scalar() for name in names}
    finally:
        db.close()


def test_the_integrity_audit_finds_the_book_whole(books) -> None:
    b = books
    a = _set_up(b)
    entry = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a)))
    b["ok"](b["call"]("POST", f"journal-entries/{entry['id']}/reverse", {"posting_date": MARCH}))
    names = ("posted journal entries that do not balance", "posted journal entries with fewer than two lines",
             "reversals that do not mirror the entry they reverse")
    assert _audit(names) == dict.fromkeys(names, 0)


def test_no_draft_is_written_into_or_moved_into_a_closed_month(books) -> None:
    """Review 2026-11-12, finding 6: closing refused while drafts were dated in
    the month, but a draft could be created or moved there afterwards and sit
    stranded, never able to post."""
    b = books
    a = _set_up(b)
    b["ok"](b["call"]("POST", "accounting-periods/close", {"period": "2026-01-01"}), 200)
    created = b["call"]("POST", "journal-entries", _sale(b, a, status="draft", day="2026-01-15"))
    assert created.status_code == 409 and "2026-01 is closed" in created.text
    draft = b["ok"](b["call"]("POST", "journal-entries", _sale(b, a, status="draft")))
    moved = b["call"]("PATCH", f"journal-entries/{draft['id']}", {"posting_date": "2026-01-20"})
    assert moved.status_code == 409 and "could never post" in moved.text


def test_an_accounts_ledger_pages_and_carries_its_running_balance(books) -> None:
    b = books
    a = _set_up(b)
    for n in range(5):
        b["ok"](b["call"]("POST", "journal-entries", {
            "posting_date": f"2026-03-{10 + n}", "description": f"cash sale {n}", "status": "posted",
            "lines": [{"ledger_account_id": a["bank"], "debit": 10 * (n + 1)},
                      {"ledger_account_id": a["revenue"], "credit": 10 * (n + 1)}]}))
    whole = b["ok"](b["call"]("GET", f"ledger-accounts/{a['bank']}/ledger", date_from="2026-03-11",
                              date_to="2026-03-31"), 200)
    assert (whole["opening"], whole["total_lines"], whole["closing"]) == (10.0, 4, 150.0)
    second = b["ok"](b["call"]("GET", f"ledger-accounts/{a['bank']}/ledger", date_from="2026-03-11",
                               date_to="2026-03-31", page=2, size=2), 200)
    assert [line["balance"] for line in second["lines"]] == [100.0, 150.0], "page 1's 20 + 30 carried over"
    assert [line["balance"] for line in whole["lines"]][2:] == [100.0, 150.0]
