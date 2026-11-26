"""Ledger coverage — plan docs/plans/ledger-coverage-2026-11-24.md, phases 1 and 2.

The server finds what happened that the book does not say — documents whose
money counts in a month and that no posted, unreversed entry names — and
entries that name documents which no longer count. It decides nothing about
what must be posted: that is the workspace's posting rule, applied by an
agent. A waiver records a person's decision that a document needs no entry;
a fact is never both waived and in the book.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Cover Co", email="owner@cover-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, who: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=who or admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        ok(call("PUT", "accounting-settings", {"functional_currency": "CNY"}), 200)
        accounts = {code: ok(call("POST", "ledger-accounts", {"account_code": code, "name": code,
                                                              "account_type": kind, **extra}))["id"]
                    for code, kind, extra in (("1002", "asset", {}), ("1122", "asset", {"subledger": "customer"}),
                                              ("6001", "income", {}), ("6602", "expense", {}),
                                              ("2241", "liability", {"subledger": "employee"}))}
        clerk = ok(call("POST", "employees", {"name": "Clerk"}))["id"]
        customer = ok(call("POST", "customers", {"name": "Huaxin"}))["id"]

        def sale(day: str, amount: float = 1000, status: str = "issued") -> dict:
            return ok(call("POST", "invoices", {"direction": "sales", "employee_id": clerk, "customer_id": customer,
                                                "title": "goods", "invoice_date": day, "status": status,
                                                "total_amount": amount}))

        def post(source_type: str, source_id: str, day: str, amount: float, event: str = "issued",
                 party: dict | None = None) -> dict:
            debit = {"ledger_account_id": accounts["1122"], "debit": amount, "customer_id": customer}
            if party is not None:
                debit = {"ledger_account_id": accounts["6602"], "debit": amount}
            credit = {"ledger_account_id": accounts["6001"], "credit": amount}
            if party is not None:
                credit = {"ledger_account_id": accounts["2241"], "credit": amount, **party}
            return ok(call("POST", "journal-entries", {
                "posting_date": day, "description": f"{source_type} {event}", "status": "posted",
                "source_type": source_type, "source_id": source_id, "source_event": event,
                "lines": [debit, credit]}))

        def cover(day: str = "2026-03-01", **params) -> dict:
            return ok(call("GET", "ledger-coverage", period=day, **params), 200)

        yield dict(c=c, admin=admin, call=call, ok=ok, sale=sale, post=post, cover=cover, clerk=clerk,
                   customer=customer, account=accounts.__getitem__)


def test_an_issued_invoice_is_missing_until_an_entry_names_it(shop) -> None:
    s = shop
    first, second = s["sale"]("2026-03-05"), s["sale"]("2026-03-20", 500)
    s["sale"]("2026-03-21", 99, status="draft")
    s["sale"]("2026-04-02")
    report = s["cover"]("2026-03-17")
    assert report["period"] == "2026-03-01" and report["period_end"] == "2026-03-31"
    assert report["families"]["invoice"] == {"counted": 2, "recorded": 0, "waived": 0, "missing": 2,
                                             "by_direction": {"sales": {"counted": 2, "recorded": 0, "waived": 0,
                                                                        "missing": 2}}}
    assert [m["number"] for m in report["missing"]] == [first["invoice_no"], second["invoice_no"]]
    assert report["missing"][0]["party"]["name"] == "Huaxin" and report["missing"][0]["amount"] == 1000.0

    # posted in April for a March invoice: still recorded — the book names it
    s["post"]("invoice", first["id"], "2026-04-03", 1000)
    report = s["cover"]()
    assert (report["families"]["invoice"]["recorded"], report["families"]["invoice"]["missing"]) == (1, 1)
    assert [m["id"] for m in report["missing"]] == [second["id"]]


def test_a_reversed_entry_records_nothing_and_a_voided_invoice_leaves_its_entry_stale(shop) -> None:
    s = shop
    invoice = s["sale"]("2026-03-05")
    entry = s["post"]("invoice", invoice["id"], "2026-03-05", 1000)
    assert s["cover"]()["families"]["invoice"]["missing"] == 0
    s["ok"](s["call"]("POST", f"journal-entries/{entry['id']}/reverse", {"posting_date": "2026-03-06"}))
    assert s["cover"]()["families"]["invoice"]["missing"] == 1, "a reversed entry no longer records the invoice"

    s["post"]("invoice", invoice["id"], "2026-03-07", 1000)
    s["ok"](s["call"]("PATCH", f"invoices/{invoice['id']}", {"status": "void"}), 200)
    report = s["cover"]()
    assert report["families"]["invoice"]["counted"] == 0, "a voided invoice never happened"
    assert [(row["source_id"], row["why"]) for row in report["stale"]] == [(invoice["id"], "the invoice is void")]
    assert s["cover"]("2026-04-01")["stale"] == [], "stale is read in the entry's own month"


def test_payments_and_claims_count_from_their_own_states(shop) -> None:
    s = shop
    paid = s["ok"](s["call"]("POST", "payments", {"direction": "inbound", "employee_id": s["clerk"],
                                                  "customer_id": s["customer"], "amount": 600,
                                                  "payment_date": "2026-03-09", "status": "paid"}))
    s["ok"](s["call"]("POST", "payments", {"direction": "inbound", "employee_id": s["clerk"],
                                           "customer_id": s["customer"], "amount": 50, "payment_date": "2026-03-09"}))
    claim = s["ok"](s["call"]("POST", "expense-claims", {
        "employee_id": s["clerk"], "title": "Taxi to the fair", "claim_date": "2026-03-11", "status": "approved",
        "items": [{"expense_date": "2026-03-10", "amount": 80}, {"expense_date": "2026-03-10", "amount": 20}]}))
    report = s["cover"]()
    assert report["families"]["payment"]["by_direction"] == {"inbound": {"counted": 1, "recorded": 0, "waived": 0,
                                                                                      "missing": 1}}
    claims = [m for m in report["missing"] if m["family"] == "expense_claim"]
    assert (claims[0]["id"], claims[0]["amount"], claims[0]["party"]["name"]) == (claim["id"], 100.0, "Clerk")
    s["post"]("expense_claim", claim["id"], "2026-03-11", 100, event="approved", party={"employee_id": s["clerk"]})
    s["post"]("payment", paid["id"], "2026-03-09", 600, event="received")
    report = s["cover"]()
    assert report["missing"] == [] and report["families"]["expense_claim"] == {"counted": 1, "recorded": 1,
                                                                               "waived": 0, "missing": 0}


def test_families_are_named_and_the_read_is_the_books(shop) -> None:
    s = shop
    s["sale"]("2026-03-05")
    only = s["cover"](families="payment")
    assert set(only["families"]) == {"payment"} and only["missing"] == []
    assert set(s["cover"]()["families"]) == {"invoice", "payment", "expense_claim", "fin_account_transaction"}
    asked = s["cover"](families="invoice_offset,payment_application,billing_account_entry")
    assert set(asked["families"]) == {"invoice_offset", "payment_application", "billing_account_entry"}
    unknown = s["call"]("GET", "ledger-coverage", period="2026-03-01", families="shipments")
    assert unknown.status_code == 422 and "shipments" in unknown.text
    invited = invite_member(s["c"], s["admin"], "member", [], email="m@cover-co.example", employee="Member")
    assert s["call"]("GET", "ledger-coverage", who={"X-API-Key": invited["X-API-Key"]},
                     period="2026-03-01").status_code == 403
    reader = invite_member(s["c"], s["admin"], "book_reader", ["ledger.read"], email="r@cover-co.example",
                           employee="Reader")
    assert s["call"]("GET", "ledger-coverage", who={"X-API-Key": reader["X-API-Key"]},
                     period="2026-03-01").status_code == 200


def test_a_waiver_takes_a_document_off_the_missing_list_and_is_kept(shop) -> None:
    s = shop
    pro_forma, billed = s["sale"]("2026-03-05"), s["sale"]("2026-03-06", 300)
    waiver = s["ok"](s["call"]("POST", "ledger-waivers", {
        "source_type": "invoice", "source_id": pro_forma["id"], "reason": "  pro forma, never billed ",
        "decided_by": "Ms Li (controller)"}))
    assert (waiver["reason"], waiver["decided_by"], waiver["source_event"]) == (
        "pro forma, never billed", "Ms Li (controller)", None)
    report = s["cover"]()
    assert report["families"]["invoice"] == {"counted": 2, "recorded": 0, "waived": 1, "missing": 1,
                                             "by_direction": {"sales": {"counted": 2, "recorded": 0, "waived": 1,
                                                                        "missing": 1}}}
    assert [m["id"] for m in report["missing"]] == [billed["id"]]
    assert [(w["id"], w["waiver_id"], w["reason"]) for w in report["waived"]] == [
        (pro_forma["id"], waiver["id"], "pro forma, never billed")]

    # a waived fact does not post; a second live waiver for it is refused
    refused = s["call"]("POST", "journal-entries", {
        "posting_date": "2026-03-05", "description": "invoice issued", "status": "posted",
        "source_type": "invoice", "source_id": pro_forma["id"], "source_event": "issued",
        "lines": [{"ledger_account_id": s["account"]("1122"), "debit": 1000, "customer_id": s["customer"]},
                  {"ledger_account_id": s["account"]("6001"), "credit": 1000}]})
    assert refused.status_code == 409 and "waived" in refused.text and waiver["id"] in refused.text
    again = s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": pro_forma["id"],
                                                 "reason": "again"})
    assert again.status_code == 409 and waiver["id"] in again.text

    # revoked, never edited: the document is missing again and then posts
    revoked = s["ok"](s["call"]("POST", f"ledger-waivers/{waiver['id']}/revoke", {"reason": "billed after all"}),
                      200)
    assert revoked["revoked_at"] and revoked["revoke_reason"] == "billed after all"
    assert s["call"]("POST", f"ledger-waivers/{waiver['id']}/revoke").status_code == 409
    assert s["cover"]()["families"]["invoice"]["missing"] == 2
    s["post"]("invoice", pro_forma["id"], "2026-03-05", 1000)
    listed = s["ok"](s["call"]("GET", "ledger-waivers", source_id=pro_forma["id"]), 200)
    assert [w["id"] for w in listed] == [waiver["id"]]
    assert s["ok"](s["call"]("GET", "ledger-waivers", revoked="false"), 200) == []


def test_a_fact_in_the_book_cannot_be_waived_and_an_event_waiver_is_narrow(shop) -> None:
    s = shop
    invoice = s["sale"]("2026-03-05")
    entry = s["post"]("invoice", invoice["id"], "2026-03-05", 1000)
    whole = s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                 "reason": "not ours"})
    assert whole.status_code == 409 and entry["entry_no"] in whole.text
    same_event = s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                      "source_event": "issued", "reason": "not ours"})
    assert same_event.status_code == 409
    # another event of it may be waived; the document stays recorded
    other = s["ok"](s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                         "source_event": "received", "reason": "cash sale"}))
    report = s["cover"]()
    assert (report["families"]["invoice"]["recorded"], report["waived"]) == (1, [])
    refused = s["call"]("POST", "journal-entries", {
        "posting_date": "2026-03-06", "description": "invoice received", "status": "posted",
        "source_type": "invoice", "source_id": invoice["id"], "source_event": "received",
        "lines": [{"ledger_account_id": s["account"]("1002"), "debit": 1000},
                  {"ledger_account_id": s["account"]("1122"), "credit": 1000, "customer_id": s["customer"]}]})
    assert refused.status_code == 409 and other["id"] in refused.text
    # a draft may still be written; only posting is refused
    s["ok"](s["call"]("POST", "journal-entries", {
        "posting_date": "2026-03-06", "description": "invoice received (draft)",
        "source_type": "invoice", "source_id": invoice["id"], "source_event": "received",
        "lines": [{"ledger_account_id": s["account"]("1002"), "debit": 1000},
                  {"ledger_account_id": s["account"]("1122"), "credit": 1000, "customer_id": s["customer"]}]}))


def test_waivers_are_validated_gated_and_never_edited(shop) -> None:
    s = shop
    invoice = s["sale"]("2026-03-05")
    blank = s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                 "reason": "   "})
    assert blank.status_code == 422
    unknown = s["call"]("POST", "ledger-waivers", {"source_type": "shipments", "source_id": invoice["id"],
                                                   "reason": "x"})
    assert unknown.status_code == 422 and "not a source" in unknown.text
    reader = invite_member(s["c"], s["admin"], "book_reader", ["ledger.read"], email="r@cover-co.example",
                           employee="Reader")
    who = {"X-API-Key": reader["X-API-Key"]}
    assert s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                "reason": "x"}, who=who).status_code == 403
    waiver = s["ok"](s["call"]("POST", "ledger-waivers", {"source_type": "invoice", "source_id": invoice["id"],
                                                          "reason": "pro forma"}))
    assert waiver["decided_by"] == waiver["waived_by"], "decided_by defaults to the writer"
    assert s["call"]("GET", f"ledger-waivers/{waiver['id']}", who=who).status_code == 200
    assert s["call"]("POST", f"ledger-waivers/{waiver['id']}/revoke", who=who).status_code == 403
    assert s["call"]("PATCH", f"ledger-waivers/{waiver['id']}", {"reason": "y"}).status_code in (404, 405)
    assert s["call"]("DELETE", f"ledger-waivers/{waiver['id']}").status_code in (404, 405)

    # every write path, not only the API: the session refuses the edit
    from fastapi import HTTPException

    from app.db.session import get_db
    from app.main import app
    from app.models import LedgerWaiver

    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.get(LedgerWaiver, waiver["id"])
        row.reason = "edited behind the API"
        with pytest.raises(HTTPException) as edited:
            db.flush()
        assert edited.value.status_code == 409
        db.rollback()
        db.delete(db.get(LedgerWaiver, waiver["id"]))
        with pytest.raises(HTTPException):
            db.flush()
    finally:
        db.rollback()
        db.close()
