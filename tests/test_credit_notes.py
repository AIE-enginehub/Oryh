"""Credit and debit notes — plan docs/plans/accounting-core-2026-11-08.md, phase 2.

A note is an invoice of another kind that names the invoice it corrects. The
server holds the arithmetic: a credit note never takes back more than was
billed, line by line or in total; it is settled by a refund running the
other way, or set against an open invoice of the same party. Whether to
credit, how much, and whether to refund or offset is the agent's call.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import text as sql_text

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Note Co", email="owner@note-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        clerk = ok(call("POST", "employees", {"name": "Clerk"}))["id"]
        buyer = ok(call("POST", "customers", {"name": "Huaxin"}))["id"]
        other = ok(call("POST", "customers", {"name": "Someone else"}))["id"]

        def invoice(customer: str | None = None, submit: bool = True, **extra) -> dict:
            row = ok(call("POST", "invoices", {
                "direction": "sales", "employee_id": clerk, "customer_id": customer or buyer, "title": "March goods",
                "items": [{"invoice_item_type": "goods", "product_name_snapshot": "tea", "amount": 1000},
                          {"invoice_item_type": "discount", "product_name_snapshot": "discount", "amount": -50},
                          {"invoice_item_type": "shipping", "product_name_snapshot": "freight", "amount": 100}],
                **extra}))
            if submit:
                ok(call("POST", f"invoices/{row['id']}/submit", {}), 200)
            return row

        def note(original: dict, lines: list[tuple[int, float]], kind: str = "credit_note", **extra):
            return call("POST", "invoices", {
                "direction": "sales", "employee_id": clerk, "customer_id": extra.pop("customer_id", buyer),
                "title": "Return", "invoice_kind": kind, "original_invoice_id": original["id"], **extra,
                "items": [{"invoice_item_type": "goods", "product_name_snapshot": "return", "amount": amount,
                           "original_invoice_item_id": original["items"][index]["id"]}
                          for index, amount in lines]})

        def outstanding(invoice_id: str) -> float:
            return ok(call("GET", f"invoices/{invoice_id}/detail"), 200)["outstanding_amount"]

        yield dict(c=c, call=call, ok=ok, clerk=clerk, buyer=buyer, other=other, invoice=invoice, note=note,
                   outstanding=outstanding)


def test_a_credit_note_names_its_invoice_and_takes_its_own_series(shop) -> None:
    s = shop
    original = s["invoice"]()
    credit = s["ok"](s["note"](original, [(0, -300)]))
    assert (credit["invoice_kind"], credit["original_invoice_id"]) == ("credit_note", original["id"])
    assert credit["invoice_no"].startswith("CN-")
    assert credit["items"][0]["original_invoice_item_id"] == original["items"][0]["id"]
    listed = s["ok"](s["call"]("GET", "invoices", original_invoice_id=original["id"]), 200)
    assert [row["id"] for row in listed] == [credit["id"]]
    debit = s["ok"](s["note"](original, [(2, 40)], kind="debit_note"))
    assert debit["invoice_no"].startswith("DN-")


def test_a_note_corrects_an_invoice_that_was_stood_behind_for_the_same_party(shop) -> None:
    s = shop
    draft = s["invoice"](submit=False)
    early = s["note"](draft, [(0, -100)])
    assert early.status_code == 409 and "still editable" in early.text
    original = s["invoice"]()
    stranger = s["note"](original, [(0, -100)], customer_id=s["other"])
    assert stranger.status_code == 422 and "customer_id" in stranger.text
    credit = s["ok"](s["note"](original, [(0, -100)]))
    of_a_note = s["note"](credit, [(0, -1)])
    assert of_a_note.status_code == 422 and "corrects the invoice" in of_a_note.text
    elsewhere = s["call"]("POST", "invoices", {
        "direction": "sales", "employee_id": s["clerk"], "customer_id": s["buyer"], "title": "x",
        "invoice_kind": "credit_note", "original_invoice_id": original["id"],
        "items": [{"invoice_item_type": "goods", "product_name_snapshot": "x", "amount": -1,
                   "original_invoice_item_id": s["invoice"]()["items"][0]["id"]}]})
    assert elsewhere.status_code == 422 and "not a line of the invoice" in elsewhere.text
    unnamed = s["call"]("POST", "invoices", {"direction": "sales", "employee_id": s["clerk"],
                                             "customer_id": s["buyer"], "title": "x", "invoice_kind": "credit_note",
                                             "total_amount": -5})
    assert unnamed.status_code == 422 and "original_invoice_id" in unnamed.text
    positive = s["note"](original, [(0, -10)], total_amount=10)
    assert positive.status_code == 422 and "0 or less" in positive.text


def test_a_credit_moves_a_line_toward_zero_and_never_past_it(shop) -> None:
    s = shop
    original = s["invoice"]()
    beyond = s["note"](original, [(0, -1001)])
    assert beyond.status_code == 409 and "never past it" in beyond.text
    s["ok"](s["note"](original, [(0, -600)]))
    again = s["note"](original, [(0, -500)])
    assert again.status_code == 409, "600 already credited of 1000"
    s["ok"](s["note"](original, [(0, 200)], kind="debit_note"))
    s["ok"](s["note"](original, [(0, -500)])), "a debit note raised the line to 1200"
    # a returned discount is given back as a positive line: toward zero for a negative line
    s["ok"](s["note"](original, [(1, 20), (2, -60)]))
    past = s["note"](original, [(1, 40), (2, -40)])
    assert past.status_code == 409, "the discount was -50; 20 already given back, 40 more passes zero"


def test_credit_notes_never_give_back_more_than_was_billed(shop) -> None:
    s = shop
    original = s["invoice"]()
    whole = {"direction": "sales", "employee_id": s["clerk"], "customer_id": s["buyer"], "title": "goodwill",
             "invoice_kind": "credit_note", "original_invoice_id": original["id"]}
    s["ok"](s["call"]("POST", "invoices", {**whole, "total_amount": -1000}))
    over = s["call"]("POST", "invoices", {**whole, "total_amount": -51})
    assert over.status_code == 409 and "more than was billed" in over.text, "1050 billed, 1000 already given"
    s["ok"](s["call"]("POST", "invoices", {**whole, "total_amount": -50}))
    deleted = s["call"]("DELETE", f"invoices/{original['id']}", {"delete_reason": "x"})
    assert deleted.status_code == 409 and "correct" in deleted.text


def test_a_credit_note_is_refunded_by_money_going_the_other_way(shop) -> None:
    s = shop
    original = s["invoice"]()
    credit = s["ok"](s["note"](original, [(0, -300)]))
    s["ok"](s["call"]("POST", f"invoices/{credit['id']}/submit", {}), 200)
    assert s["outstanding"](credit["id"]) == -300.0
    open_notes = s["ok"](s["call"]("GET", "invoices", invoice_kind="credit_note", outstanding="true"), 200)
    assert [row["id"] for row in open_notes] == [credit["id"]], "an unrefunded credit is still open"

    def payment(direction: str, amount: float) -> str:
        return s["ok"](s["call"]("POST", "payments", {"direction": direction, "employee_id": s["clerk"],
                                                      "customer_id": s["buyer"], "amount": amount,
                                                      "status": "paid"}))["id"]

    def apply(payment_id: str, amount: float):
        return s["call"]("POST", f"payments/{payment_id}/apply", {"lines": [
            {"applied_to_type": "invoice", "applied_to_id": credit["id"], "amount_applied": amount}]})

    wrong_way = apply(payment("inbound", 300), 300)
    assert wrong_way.status_code == 409 and "outbound" in wrong_way.text
    refund = payment("outbound", 400)
    over = apply(refund, 301)
    assert over.status_code == 409 and "over-refunding" in over.text
    s["ok"](apply(refund, 300), 200)
    assert s["outstanding"](credit["id"]) == 0.0
    assert s["ok"](s["call"]("GET", "invoices", invoice_kind="credit_note", outstanding="true"), 200) == []
    back = apply(refund, -400)
    assert back.status_code == 409


def test_a_credit_note_is_set_against_an_open_invoice_of_the_same_party(shop) -> None:
    s = shop
    original = s["invoice"]()
    credit = s["ok"](s["note"](original, [(0, -300)]))
    s["ok"](s["call"]("POST", f"invoices/{credit['id']}/submit", {}), 200)
    offset = s["ok"](s["call"]("POST", f"invoices/{credit['id']}/offsets",
                               {"invoice_id": original["id"], "amount": 200}))
    assert offset["amount"] == 200.0
    assert (s["outstanding"](original["id"]), s["outstanding"](credit["id"])) == (850.0, -100.0)
    beyond = s["call"]("POST", f"invoices/{credit['id']}/offsets", {"invoice_id": original["id"], "amount": 101})
    assert beyond.status_code == 409 and "left to give" in beyond.text
    theirs = s["invoice"](customer=s["other"])
    crossed = s["call"]("POST", f"invoices/{credit['id']}/offsets", {"invoice_id": theirs["id"], "amount": 10})
    assert crossed.status_code == 409 and "customer_id" in crossed.text
    s["ok"](s["call"]("POST", f"invoices/{credit['id']}/offsets", {"invoice_id": original["id"], "amount": -50}))
    assert s["outstanding"](original["id"]) == 900.0, "a negative offset takes part of one back"
    rows = s["ok"](s["call"]("GET", f"invoices/{original['id']}/offsets"), 200)
    assert sorted(row["amount"] for row in rows) == [-50.0, 200.0]
    assert _audit() == {name: 0 for name in AUDITED}


def test_an_offset_is_taken_back_only_from_the_pair_it_was_set_between(shop) -> None:
    """Review 2026-11-12, finding 1: each document's running total stayed on
    the right side of zero, so a credit set against invoice A could be "taken
    back" from invoice B that cash had settled — and then used again."""
    s = shop
    first, second = s["invoice"](), s["invoice"]()
    credit = s["ok"](s["note"](first, [(0, -300)]))
    s["ok"](s["call"]("POST", f"invoices/{credit['id']}/submit", {}), 200)
    s["ok"](s["call"]("POST", f"invoices/{credit['id']}/offsets", {"invoice_id": first["id"], "amount": 300}))
    cash = s["ok"](s["call"]("POST", "payments", {"direction": "inbound", "employee_id": s["clerk"],
                                                  "customer_id": s["buyer"], "amount": 500, "status": "paid"}))
    s["ok"](s["call"]("POST", f"payments/{cash['id']}/apply", {"lines": [
        {"applied_to_type": "invoice", "applied_to_id": second["id"], "amount_applied": 500}]}), 200)
    stolen = s["call"]("POST", f"invoices/{credit['id']}/offsets", {"invoice_id": second["id"], "amount": -300})
    assert stolen.status_code == 409 and "more than was offset between these two" in stolen.text
    assert (s["outstanding"](second["id"]), s["outstanding"](credit["id"])) == (550.0, 0.0)
    assert _audit() == {name: 0 for name in AUDITED}


AUDITED = ("invoice applied_amount equals the sum of its applications and offsets",
           "offsets taken back beyond what was set between the pair",
           "credit notes giving back more than their invoice and its debit notes billed",
           "notes that disagree with their original's party, direction or currency")


def _audit() -> dict[str, int]:
    from app.db.session import get_db
    from app.main import app

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    checks = dict(namespace["STRUCTURAL_CHECKS"])
    db = next(app.dependency_overrides[get_db]())
    try:
        return {name: db.execute(sql_text(checks[name])).scalar() for name in AUDITED}
    finally:
        db.close()
