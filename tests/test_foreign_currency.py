"""Foreign currency — plan docs/plans/foreign-currency-2026-11-27.md, phase 1.

Rates are facts the workspace states; a line may cite the one it used, and a
cited rate never changes. Foreign-currency accounts read in their own
currency beside the book's. The revaluation read says what each foreign
balance is worth at a day's rate against the book; the agent posts.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def book():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Harbour Trading", email="owner@harbour.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, who: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=who or admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        ok(call("PUT", "accounting-settings", {"functional_currency": "HKD"}), 200)
        customer = ok(call("POST", "customers", {"name": "Pacific Imports"}))["id"]
        other = ok(call("POST", "customers", {"name": "Lantau Retail"}))["id"]
        accounts: dict[str, str] = {}
        for code, kind, extra in (("1002", "asset", {}), ("1012", "asset", {"currency": "USD"}),
                                  ("1122", "asset", {"currency": "USD", "subledger": "customer"}),
                                  ("6001", "income", {}), ("6061", "income", {})):
            accounts[code] = ok(call("POST", "ledger-accounts", {"account_code": code, "name": f"Account {code}",
                                                                 "account_type": kind, **extra}))["id"]

        def rate(pair: str, day: str, value: float, kind: str = "spot", source: str = "HKMA") -> dict:
            a, b = pair.split("/")
            return ok(call("POST", "exchange-rates", {"from_currency": a, "to_currency": b, "rate": value,
                                                      "rate_date": day, "rate_type": kind, "source": source}))

        def entry(day: str, lines: list[dict], **extra) -> dict:
            return ok(call("POST", "journal-entries", {"posting_date": day, "description": "x", "status": "posted",
                                                       "lines": lines, **extra}))

        def read(path: str, **params):
            return ok(call("GET", path, **params), 200)

        yield dict(c=c, admin=admin, call=call, ok=ok, rate=rate, entry=entry, read=read, accounts=accounts,
                   customer=customer, other=other)


def _sale(b, day: str, usd: float, at: float, customer: str | None = None, rate_id: str | None = None) -> dict:
    """A USD invoice to the customer, booked in HKD at `at`."""
    hkd = round(usd * at, 2)
    line = {"ledger_account_id": b["accounts"]["1122"], "debit": hkd, "currency": "USD", "foreign_amount": usd,
            "exchange_rate": at, "customer_id": customer or b["customer"]}
    if rate_id:
        line["exchange_rate_id"] = rate_id
    return b["entry"](day, [line, {"ledger_account_id": b["accounts"]["6001"], "credit": hkd}])


def test_rates_are_facts_and_lookup_never_guesses(book) -> None:
    b = book
    b["rate"]("USD/HKD", "2026-03-31", 7.8)
    b["rate"]("USD/HKD", "2026-06-30", 7.82, kind="month_end")
    b["rate"]("HKD/CNY", "2026-06-30", 0.92, source="PBOC")
    found = b["read"]("exchange-rates/lookup", from_currency="USD", to_currency="HKD", rate_type="spot",
                      on="2026-06-15")
    assert (found["rate"], found["rate_date"], found["inverted"]) == (7.8, "2026-03-31", False), \
        "the latest of that type on or before the day — never the month_end rate"
    inverted = b["read"]("exchange-rates/lookup", from_currency="CNY", to_currency="HKD", rate_type="spot",
                         on="2026-07-01")
    assert inverted["inverted"] is True and inverted["rate"] == 1.08695652
    assert inverted["stated"] == {"from_currency": "HKD", "to_currency": "CNY", "rate": 0.92}
    missing = b["call"]("GET", "exchange-rates/lookup", from_currency="USD", to_currency="HKD", rate_type="spot",
                        on="2026-03-30")
    assert missing.status_code == 404 and "import it" in missing.text

    clash = b["call"]("POST", "exchange-rates", {"from_currency": "USD", "to_currency": "HKD", "rate": 7.81,
                                                 "rate_date": "2026-03-31", "rate_type": "spot", "source": "x"})
    assert clash.status_code == 409 and "already stated as 7.8" in clash.text
    for body, word in (({"rate_type": "guess"}, "exchange_rate_type"), ({"to_currency": "USD"}, "another"),
                       ({"source": "  "}, "source")):
        response = b["call"]("POST", "exchange-rates", {"from_currency": "USD", "to_currency": "HKD", "rate": 7.8,
                                                        "rate_date": "2026-04-01", "rate_type": "spot",
                                                        "source": "HKMA", **body})
        assert response.status_code == 422 and word in response.text, response.text

    imported = b["ok"](b["call"]("POST", "exchange-rates/import", {"rates": [
        {"from_currency": "USD", "to_currency": "HKD", "rate": 7.8, "rate_date": "2026-03-31",
         "rate_type": "spot", "source": "HKMA"},
        {"from_currency": "USD", "to_currency": "HKD", "rate": 7.79, "rate_date": "2026-07-15",
         "rate_type": "spot", "source": "HKMA"}]}))
    assert (imported["created"], imported["skipped"]) == (1, 1), "an import can be re-run"
    refused = b["call"]("POST", "exchange-rates/import", {"rates": [
        {"from_currency": "USD", "to_currency": "HKD", "rate": 7.0, "rate_date": "2026-08-01",
         "rate_type": "spot", "source": "HKMA"},
        {"from_currency": "USD", "to_currency": "HKD", "rate": 7.5, "rate_date": "2026-03-31",
         "rate_type": "spot", "source": "HKMA"}]})
    assert refused.status_code == 409 and "rates[1]" in refused.text
    assert len(b["read"]("exchange-rates", from_currency="usd", rate_type="spot")) == 2, "all or nothing"


def test_a_cited_rate_agrees_with_its_line_and_never_changes(book) -> None:
    b = book
    spot = b["rate"]("USD/HKD", "2026-03-31", 7.8)
    reverse = b["rate"]("HKD/USD", "2026-04-30", 0.128)
    wrong = b["call"]("POST", "journal-entries", {"posting_date": "2026-04-01", "description": "x",
                                                  "status": "posted", "lines": [
        {"ledger_account_id": b["accounts"]["1122"], "debit": 7810, "currency": "USD", "foreign_amount": 1000,
         "exchange_rate": 7.81, "customer_id": b["customer"], "exchange_rate_id": spot["id"]},
        {"ledger_account_id": b["accounts"]["6001"], "credit": 7810}]})
    assert wrong.status_code == 422 and "gives 7.80000000" in wrong.text
    posted = _sale(b, "2026-04-01", 1000, 7.8, rate_id=spot["id"])
    assert posted["lines"][0]["exchange_rate_id"] == spot["id"]
    _sale(b, "2026-05-02", 1000, 7.8125, rate_id=reverse["id"])            # the reverse pair, inverted

    response = b["call"]("PATCH", f"exchange-rates/{spot['id']}", {"rate": 7.9})
    assert response.status_code == 409 and "cited" in response.text
    assert b["call"]("DELETE", f"exchange-rates/{spot['id']}").status_code == 409
    unused = b["rate"]("USD/HKD", "2026-09-30", 7.7)
    assert b["ok"](b["call"]("PATCH", f"exchange-rates/{unused['id']}", {"rate": 7.75}), 200)["rate"] == 7.75
    assert b["call"]("DELETE", f"exchange-rates/{unused['id']}").status_code == 204

    # a reversal cites the same fact
    reversal = b["ok"](b["call"]("POST", f"journal-entries/{posted['id']}/reverse", {"posting_date": "2026-04-02"}))
    assert reversal["lines"][0]["exchange_rate_id"] == spot["id"]


def test_foreign_accounts_read_in_their_own_currency(book) -> None:
    b = book
    a = b["accounts"]
    _sale(b, "2026-03-05", 1000, 7.8)
    _sale(b, "2026-03-06", 500, 7.8, customer=b["other"])
    b["entry"]("2026-03-20", [                                               # Pacific pays USD 400 into the USD bank
        {"ledger_account_id": a["1012"], "debit": 3124, "currency": "USD", "foreign_amount": 400,
         "exchange_rate": 7.81},
        {"ledger_account_id": a["1122"], "credit": 3124, "currency": "USD", "foreign_amount": 400,
         "exchange_rate": 7.81, "customer_id": b["customer"]}])
    trial = {r["account_code"]: r for r in b["read"]("trial-balance", date_from="2026-03-01",
                                                      date_to="2026-03-31")["rows"]}
    assert trial["1122"]["foreign"] == {"currency": "USD", "opening": 0.0, "debit": 1500.0, "credit": 400.0,
                                        "closing": 1100.0}
    assert trial["1122"]["closing"] == 8576.0 and "foreign" not in trial["6001"]

    ledger = b["read"](f"ledger-accounts/{a['1122']}/ledger", date_from="2026-03-01", date_to="2026-03-31")
    assert (ledger["currency"], ledger["foreign_closing"]) == ("USD", 1100.0)
    assert [line["foreign_balance"] for line in ledger["lines"]] == [1000.0, 1500.0, 1100.0]
    paged = b["read"](f"ledger-accounts/{a['1122']}/ledger", date_from="2026-03-01", date_to="2026-03-31",
                      page=2, size=2)
    assert [line["foreign_balance"] for line in paged["lines"]] == [1100.0], "the running balance carries over"

    parties = {p["customer_id"]: p for p in b["read"](f"ledger-accounts/{a['1122']}/parties", as_of="2026-03-31")}
    assert (parties[b["customer"]]["foreign_balance"], parties[b["customer"]]["balance"]) == (600.0, 4676.0)
    assert parties[b["other"]]["foreign_balance"] == 500.0


def test_revaluation_proposes_the_difference_and_only_the_remainder(book) -> None:
    b = book
    a = b["accounts"]
    _sale(b, "2026-05-10", 1000, 7.8)
    b["entry"]("2026-05-11", [{"ledger_account_id": a["1012"], "debit": 1560, "currency": "USD",
                               "foreign_amount": 200, "exchange_rate": 7.8},
                              {"ledger_account_id": a["1002"], "credit": 1560}])
    missing = b["read"]("fx-revaluation", as_of="2026-05-31", rate_type="month_end")
    assert missing["rows"] == [] and missing["missing_rates"] == [{"currency": "USD",
                                                                   "account_codes": ["1012", "1122"]}]
    month_end = b["rate"]("USD/HKD", "2026-05-31", 7.82, kind="month_end")
    s = b["read"]("fx-revaluation", as_of="2026-05-31", rate_type="month_end")
    rows = {r["account_code"]: r for r in s["rows"]}
    assert rows["1122"]["customer_id"] == b["customer"]
    assert (rows["1122"]["foreign_balance"], rows["1122"]["book_balance"], rows["1122"]["rate"]) == (
        1000.0, 7800.0, 7.82)
    assert (rows["1122"]["revalued"], rows["1122"]["difference"], rows["1122"]["effect"]) == (7820.0, 20.0, "gain")
    assert rows["1012"]["difference"] == 4.0 and s["totals"] == {"gains": 24.0, "losses": 0.0, "net": 24.0}
    assert s["rates"]["USD"]["exchange_rate_id"] == month_end["id"] and s["rates"]["USD"]["rate_date"] == "2026-05-31"

    # the agent posts by the rule, against the account itself, once a month
    body = {"source_type": "ledger_account", "source_id": a["1122"], "source_event": s["source_event"]}
    difference = {"ledger_account_id": a["1122"], "debit": 20, "customer_id": b["customer"], "currency": "USD",
                  "foreign_amount": 0, "exchange_rate": 7.82, "exchange_rate_id": month_end["id"]}
    gain = {"ledger_account_id": a["6061"], "credit": 20}
    not_an_exchange = b["call"]("POST", "journal-entries", {"posting_date": "2026-05-31", "description": "x",
                                                            "status": "posted", "lines": [difference, gain]})
    assert not_an_exchange.status_code == 422 and "exchange difference" in not_an_exchange.text
    other_account = b["call"]("POST", "journal-entries", {"posting_date": "2026-05-31", "description": "x",
                                                          "status": "posted", **body, "lines": [
        {**difference, "ledger_account_id": a["1012"], "customer_id": None}, gain]})
    assert other_account.status_code == 422 and "its own entry" in other_account.text
    b["entry"]("2026-05-31", [difference, gain], **body)
    twice = b["call"]("POST", "journal-entries", {"posting_date": "2026-05-31", "description": "again",
                                                  "status": "posted", **body, "lines": [difference, gain]})
    assert twice.status_code == 409, "one live revaluation per account and month"
    after = {r["account_code"]: r for r in b["read"]("fx-revaluation", as_of="2026-05-31",
                                                     rate_type="month_end")["rows"]}
    assert after["1122"]["difference"] == 0.0 and after["1122"]["revaluation_entry_no"]

    # a month later the rate falls: only the remainder from the revalued figure
    b["rate"]("USD/HKD", "2026-06-30", 7.79, kind="month_end")
    june = {r["account_code"]: r for r in b["read"]("fx-revaluation", as_of="2026-06-30",
                                                    rate_type="month_end")["rows"]}
    assert (june["1122"]["book_balance"], june["1122"]["difference"], june["1122"]["effect"]) == (
        7820.0, -30.0, "loss")
    stated = b["read"]("fx-revaluation", as_of="2026-06-30", rates="USD:7.9")
    assert stated["rates"]["USD"]["source"] == "stated for this read"
    assert b["call"]("GET", "fx-revaluation", as_of="2026-06-30").status_code == 422
    assert b["call"]("GET", "fx-revaluation", rates="USD7.9").status_code == 422


def test_settled_foreign_side_leaves_the_exchange_and_who_may_read(book) -> None:
    b = book
    a = b["accounts"]
    _sale(b, "2026-05-10", 1000, 7.8)
    b["entry"]("2026-05-20", [{"ledger_account_id": a["1012"], "debit": 7790, "currency": "USD",
                               "foreign_amount": 1000, "exchange_rate": 7.79},
                              {"ledger_account_id": a["1122"], "credit": 7790, "currency": "USD",
                               "foreign_amount": 1000, "exchange_rate": 7.79, "customer_id": b["customer"]}])
    s = b["read"]("fx-revaluation", as_of="2026-05-31", rates="USD:7.79")
    receivable = next(r for r in s["rows"] if r["account_code"] == "1122")
    assert (receivable["foreign_balance"], receivable["book_balance"], receivable["settled"]) == (0.0, 10.0, True)
    assert (receivable["difference"], receivable["effect"]) == (-10.0, "loss")

    reader = invite_member(b["c"], b["admin"], "fx_reader", ["ledger.read"], email="r@harbour.example",
                           employee="Reader")
    who = {"X-API-Key": reader["X-API-Key"]}
    assert b["call"]("GET", "fx-revaluation", who=who, rates="USD:7.8").status_code == 200
    assert b["call"]("GET", "exchange-rates", who=who).status_code == 200
    assert b["call"]("POST", "exchange-rates", {"from_currency": "USD", "to_currency": "HKD", "rate": 7.8,
                                                "rate_date": "2026-01-01", "rate_type": "spot", "source": "x"},
                     who=who).status_code == 403
    member = invite_member(b["c"], b["admin"], "member", [], email="m@harbour.example", employee="Member")
    assert b["call"]("GET", "exchange-rates", who={"X-API-Key": member["X-API-Key"]}).status_code == 403
