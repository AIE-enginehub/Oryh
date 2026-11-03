"""Treasury review, 2026-10-26: a register line and the payment it carries.

1. A payment lands once: its lines together carry no more than its amount,
   and a payment its batch line settles takes no line of its own.
2. A line links a payment that is approved or paid, and not deleted.
3. A batch counts only its live members.
4. The payment's detail shows the lines that carry it.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Treasury Review Co", email="admin@treasury-review.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        cashier = dict(invite_member(c, admin, "cashier", ["fin_account.manage"],
                                     email="cash@treasury-review.example", employee="Cashier"))
        emp = c.post("/api/v1/employees", headers=admin, json={"name": "Payer"}).json()["data"]["id"]
        vendor = c.post("/api/v1/vendors", headers=admin, json={"name": "Supplier"}).json()["data"]["id"]
        customer = c.post("/api/v1/customers", headers=admin, json={"name": "Buyer"}).json()["data"]["id"]
        account = c.post("/api/v1/fin-accounts", headers=cashier, json={
            "name": "Main bank", "account_type": "bank", "currency": "CNY",
            "opening_balance": 100000}).json()["data"]

        def payment(amount=100, status="paid", reference_no=None, direction="outbound"):
            party = {"vendor_id": vendor} if direction == "outbound" else {"customer_id": customer}
            r = c.post("/api/v1/payments", headers=admin, json={
                "direction": direction, "employee_id": emp, "amount": amount, "status": status, **party,
                **({"reference_no": reference_no} if reference_no else {})})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        def line(amount, **extra):
            return c.post("/api/v1/fin-account-transactions", headers=cashier,
                          json={"fin_account_id": account["id"], "amount": amount, **extra})

        def link(line_id, **body):
            return c.patch(f"/api/v1/fin-account-transactions/{line_id}", headers=cashier, json=body)

        def detail(payment_id):
            return c.get(f"/api/v1/payments/{payment_id}/detail", headers=admin).json()["data"]

        yield dict(c=c, admin=admin, payment=payment, line=line, link=link, detail=detail)


# --- 1. one landing per payment ---------------------------------------------


def test_a_payment_does_not_land_twice(desk) -> None:
    p = desk["payment"](100)
    assert desk["line"](-100, payment_id=p["id"]).status_code == 201
    twice = desk["line"](-100, payment_id=p["id"])
    assert twice.status_code == 422 and "lands once" in twice.text


def test_partial_legs_land_up_to_the_amount_and_not_past_it(desk) -> None:
    p = desk["payment"](100)
    assert desk["line"](-60, payment_id=p["id"]).status_code == 201
    assert desk["line"](-41, payment_id=p["id"]).status_code == 422, "60 + 41 is more than 100"
    assert desk["line"](-40, payment_id=p["id"]).status_code == 201
    over = desk["line"](-99999, payment_id=desk["payment"](100)["id"])
    assert over.status_code == 422, "a 100 payment is not a 99,999 debit"


def test_a_netted_fee_lands_the_gross(desk) -> None:
    receipt = desk["payment"](100, direction="inbound")
    netted = desk["line"](99.4, gross_amount=100, fee_amount=0.6, payment_id=receipt["id"])
    assert netted.status_code == 201, netted.text
    landed = desk["detail"](receipt["id"])
    assert (landed["landed_amount"], landed["unlanded_amount"]) == (100.0, 0.0)


def test_relinking_a_line_does_not_count_against_itself(desk) -> None:
    p = desk["payment"](100)
    row = desk["line"](-100).json()["data"]
    assert desk["link"](row["id"], payment_id=p["id"]).status_code == 200
    assert desk["link"](row["id"], payment_id=p["id"]).status_code == 200


def test_a_payment_in_a_settled_batch_takes_no_line_of_its_own(desk) -> None:
    a, b = desk["payment"](100, reference_no="RUN-A"), desk["payment"](50, reference_no="RUN-A")
    batch = desk["line"](-150).json()["data"]
    assert desk["link"](batch["id"], payment_reference_no="RUN-A").status_code == 200
    alone = desk["line"](-100, payment_id=a["id"])
    assert alone.status_code == 409 and "batch line" in alone.text
    again = desk["line"](-150).json()["data"]
    twice = desk["link"](again["id"], payment_reference_no="RUN-A")
    assert twice.status_code == 409 and "one batch, one landing" in twice.text
    assert desk["detail"](b["id"])["landed_amount"] == 50.0


def test_a_batch_whose_member_already_landed_alone_is_refused(desk) -> None:
    a = desk["payment"](100, reference_no="RUN-B")
    desk["payment"](50, reference_no="RUN-B")
    assert desk["line"](-100, payment_id=a["id"]).status_code == 201
    batch = desk["line"](-150).json()["data"]
    refused = desk["link"](batch["id"], payment_reference_no="RUN-B")
    assert refused.status_code == 409 and a["payment_no"] in refused.text


# --- 2. only a live payment --------------------------------------------------


@pytest.mark.parametrize("state", ["draft", "submitted", "returned", "rejected", "cancelled", "void"])
def test_a_line_does_not_link_a_payment_that_moved_nothing(desk, state) -> None:
    refused = desk["line"](-100, payment_id=desk["payment"](status=state)["id"])
    assert refused.status_code == 409 and state in refused.text


@pytest.mark.parametrize("state", ["approved", "paid"])
def test_a_line_links_an_approved_or_paid_payment(desk, state) -> None:
    assert desk["line"](-100, payment_id=desk["payment"](status=state)["id"]).status_code == 201


def test_a_line_does_not_link_a_deleted_payment(desk) -> None:
    p = desk["payment"](status="draft")
    assert desk["c"].delete(f"/api/v1/payments/{p['id']}", headers=desk["admin"]).status_code == 204
    assert desk["line"](-100, payment_id=p["id"]).status_code in (404, 409)


# --- 3. a batch counts its live members --------------------------------------


def test_a_voided_member_is_not_part_of_the_batch(desk) -> None:
    desk["payment"](100, reference_no="RUN-C")
    desk["payment"](50, status="void", reference_no="RUN-C")
    desk["payment"](25, status="draft", reference_no="RUN-C")
    wrong = desk["line"](-175).json()["data"]
    assert desk["link"](wrong["id"], payment_reference_no="RUN-C").status_code == 422, "only 100 of it is live"
    right = desk["line"](-100).json()["data"]
    settled = desk["link"](right["id"], payment_reference_no="RUN-C")
    assert settled.status_code == 200, settled.text
    assert (settled.json()["data"]["payments_settled"], settled.json()["data"]["payments_total"]) == (1, 100.0)


# --- 4. the payment shows where it landed ------------------------------------


def test_the_payment_detail_shows_its_landings(desk) -> None:
    p = desk["payment"](100)
    empty = desk["detail"](p["id"])
    assert (empty["cash_landings"], empty["landed_amount"], empty["unlanded_amount"]) == ([], 0.0, 100.0)
    first = desk["line"](-60, payment_id=p["id"], reference_no="BANK-1").json()["data"]
    seen = desk["detail"](p["id"])
    assert [(row["trans_id"], row["via"], row["amount"], row["fin_account_name"]) for row in seen["cash_landings"]] == [
        (first["id"], "direct", -60.0, "Main bank")]
    assert (seen["landed_amount"], seen["unlanded_amount"]) == (60.0, 40.0)

    member = desk["payment"](30, reference_no="RUN-D")
    batch = desk["line"](-30).json()["data"]
    assert desk["link"](batch["id"], payment_reference_no="RUN-D").status_code == 200
    via_batch = desk["detail"](member["id"])
    assert [(row["trans_id"], row["via"]) for row in via_batch["cash_landings"]] == [(batch["id"], "batch")]
    assert via_batch["unlanded_amount"] == 0.0
