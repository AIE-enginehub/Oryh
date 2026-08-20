"""核销 — payments, and which documents they settle.

This is the money-correctness file. What must hold:

- nothing may be over-applied, on EITHER side (a payment cannot pay out more
  than it holds; a document cannot be settled beyond what it bills);
- direction and currency must agree, because a wrong-side or wrong-currency
  application is a silently wrong balance rather than a loud failure;
- the ledger is append-only — a correction is a counter-entry, never an edit;
- a retry with the same idempotency key applies once;
- settlement progress is never a status: it is derived from the ledger, so a
  partly-paid invoice needs no state of its own.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

TEST_TENANT = "99999999-2222-4222-8222-999999999999"
TEST_API_KEY = "settlement-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Settlement Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def post(client: TestClient, path: str, body: dict, expect: int = 201) -> dict:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()["data"]


def employee(client: TestClient, name: str = "财务小陈") -> str:
    return post(client, "/api/v1/employees", {"name": name})["id"]


def customer(client: TestClient) -> dict:
    return post(client, "/api/v1/customers", {"name": "上海市第一医院"})


def vendor(client: TestClient) -> dict:
    return post(client, "/api/v1/vendors", {"name": "戴尔（中国）有限公司"})


def sales_invoice(client: TestClient, total: float = 10000.0, **overrides) -> dict:
    body = {
        "direction": "sales",
        "employee_id": overrides.pop("employee_id", None) or employee(client),
        "customer_id": overrides.pop("customer_id", None) or customer(client)["id"],
        "title": "货款",
        "total_amount": total,
    }
    body.update(overrides)
    return post(client, "/api/v1/invoices", body)


def receipt(client: TestClient, amount: float = 10000.0, **overrides) -> dict:
    body = {
        "direction": "inbound",
        "employee_id": overrides.pop("employee_id", None) or employee(client),
        "customer_id": overrides.pop("customer_id", None) or customer(client)["id"],
        "amount": amount,
        # money that already arrived is created in its terminal state
        "status": "paid",
    }
    body.update(overrides)
    return post(client, "/api/v1/payments", body)


def apply(client: TestClient, payment_id: str, lines: list[dict], expect: int = 200, **extra) -> dict:
    response = client.post(
        f"/api/v1/payments/{payment_id}/apply",
        json={"lines": lines, **extra},
        headers=HEADERS,
    )
    assert response.status_code == expect, response.text
    return response.json()["data"] if expect == 200 else response.json()


def outstanding(client: TestClient, invoice_id: str) -> float:
    detail = client.get(f"/api/v1/invoices/{invoice_id}/detail", headers=HEADERS).json()["data"]
    return detail["outstanding_amount"]


def test_a_partial_receipt_settles_part_of_an_invoice(client: TestClient) -> None:
    """The headline case: 客户先付一半. Nothing about the invoice's STATUS
    changes — the outstanding balance is derived from the ledger."""
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 4000.0, employee_id=person, customer_id=buyer["id"])

    result = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 4000.0}],
    )
    assert result["applied_amount"] == 4000.0
    assert result["unapplied_amount"] == 0.0
    assert result["targets"][0]["outstanding_amount"] == 6000.0

    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["applied_amount"] == 4000.0
    assert detail["outstanding_amount"] == 6000.0
    # still issued/draft — partial settlement is not a state
    assert detail["invoice"]["status"] == "draft"
    assert len(detail["applications"]) == 1


def test_a_document_cannot_be_settled_beyond_what_it_bills(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 15000.0, employee_id=person, customer_id=buyer["id"])

    body = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 12000.0}],
        expect=409,
    )
    assert "over-applying" in body["detail"]
    assert "10000.00" in body["detail"]
    # nothing was written
    assert outstanding(client, invoice["id"]) == 10000.0


def test_a_payment_cannot_pay_out_more_than_it_holds(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    first = sales_invoice(client, 6000.0, employee_id=person, customer_id=buyer["id"])
    second = sales_invoice(client, 6000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])

    # both lines individually fit; together they overflow the payment
    body = apply(
        client, money["id"],
        [
            {"applied_to_type": "invoice", "applied_to_id": first["id"], "amount_applied": 6000.0},
            {"applied_to_type": "invoice", "applied_to_id": second["id"], "amount_applied": 6000.0},
        ],
        expect=409,
    )
    assert "over-applying" in body["detail"]
    # refused whole, not half-applied
    assert outstanding(client, first["id"]) == 6000.0
    assert outstanding(client, second["id"]) == 6000.0


def test_one_receipt_settles_several_invoices(client: TestClient) -> None:
    """客户一笔钱付几张票 — the ordinary case that makes 核销 a many-to-many."""
    person = employee(client)
    buyer = customer(client)
    first = sales_invoice(client, 6000.0, employee_id=person, customer_id=buyer["id"])
    second = sales_invoice(client, 3000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])

    result = apply(
        client, money["id"],
        [
            {"applied_to_type": "invoice", "applied_to_id": first["id"], "amount_applied": 6000.0},
            {"applied_to_type": "invoice", "applied_to_id": second["id"], "amount_applied": 3000.0},
        ],
    )
    assert result["applied_amount"] == 9000.0
    # what is left is 预收款 — an advance looking for a document
    assert result["unapplied_amount"] == 1000.0
    assert outstanding(client, first["id"]) == 0.0
    assert outstanding(client, second["id"]) == 0.0


def test_an_unapplied_balance_is_the_advance(client: TestClient) -> None:
    """预收/预付 needs no entity of its own: it is what a payment still holds."""
    money = receipt(client, 5000.0)
    detail = client.get(f"/api/v1/payments/{money['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["applied_amount"] == 0.0
    assert detail["unapplied_amount"] == 5000.0


def test_a_mistake_is_reversed_by_a_counter_entry(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 10000.0}],
    )

    reversed_result = apply(
        client, money["id"],
        [
            {
                "applied_to_type": "invoice",
                "applied_to_id": invoice["id"],
                "amount_applied": -10000.0,
                "note": "认错客户了",
            }
        ],
    )
    assert reversed_result["applied_amount"] == 0.0
    assert outstanding(client, invoice["id"]) == 10000.0

    # both rows stand as history — the ledger is append-only
    ledger = client.get(
        f"/api/v1/payment-applications?payment_id={money['id']}", headers=HEADERS
    ).json()["data"]
    assert sorted(row["amount_applied"] for row in ledger) == [-10000.0, 10000.0]


def test_reversing_more_than_was_applied_is_refused(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 3000.0}],
    )

    body = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": -5000.0}],
        expect=409,
    )
    assert "reversing more than was applied" in body["detail"]


def test_the_ledger_has_no_edit_or_delete(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    result = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 1000.0}],
    )
    application_id = result["applications"][0]["id"]

    # there is no such route at all — the ledger is written only through /apply
    assert client.patch(
        f"/api/v1/payment-applications/{application_id}", json={"amount_applied": 1.0}, headers=HEADERS
    ).status_code == 404
    assert client.delete(
        f"/api/v1/payment-applications/{application_id}", headers=HEADERS
    ).status_code == 404


def test_an_inbound_payment_cannot_settle_a_vendor_bill(client: TestClient) -> None:
    person = employee(client)
    supplier = vendor(client)
    bill = post(
        client, "/api/v1/invoices",
        {
            "direction": "purchase",
            "employee_id": person,
            "vendor_id": supplier["id"],
            "title": "服务器",
            "total_amount": 8000.0,
        },
    )
    money = receipt(client, 8000.0, employee_id=person)

    body = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": bill["id"], "amount_applied": 8000.0}],
        expect=409,
    )
    assert "'outbound' payment" in body["detail"]


def test_cross_currency_settlement_is_refused_with_a_reason(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(
        client, 10000.0, employee_id=person, customer_id=buyer["id"], currency="USD"
    )
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])  # CNY

    body = apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 10000.0}],
        expect=409,
    )
    assert "currency mismatch" in body["detail"]
    assert "explicit rate" in body["detail"]


def test_a_retry_with_the_same_key_but_a_corrected_amount_is_refused(client: TestClient) -> None:
    """The other half of `test_a_retry_with_the_same_key_applies_once`.

    A key that has already written rows used to answer for any later request
    carrying it — so an agent retrying with a CORRECTED amount was told
    `replayed: true`, 200, and its correction was silently dropped. The money
    the caller believed it had settled sat unapplied.
    """
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])

    apply(client, money["id"], [{"applied_to_type": "invoice", "applied_to_id": invoice["id"],
                                 "amount_applied": 4000.0}], idempotency_key="agent-run-43")
    refused = client.post(
        f"/api/v1/payments/{money['id']}/apply",
        json={"lines": [{"applied_to_type": "invoice", "applied_to_id": invoice["id"],
                         "amount_applied": 6000.0}],
              "idempotency_key": "agent-run-43"},
        headers=HEADERS,
    )
    assert refused.status_code == 409, refused.text
    assert "different set of applications" in refused.json()["detail"]
    assert outstanding(client, invoice["id"]) == 6000.0

    # and the way forward the message names actually works
    apply(client, money["id"], [{"applied_to_type": "invoice", "applied_to_id": invoice["id"],
                                 "amount_applied": 6000.0}], idempotency_key="agent-run-44")
    assert outstanding(client, invoice["id"]) == 0.0


def test_a_retry_with_the_same_key_applies_once(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    lines = [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 4000.0}]

    first = apply(client, money["id"], lines, idempotency_key="agent-run-42")
    assert first["replayed"] is False
    second = apply(client, money["id"], lines, idempotency_key="agent-run-42")
    assert second["replayed"] is True

    assert second["applied_amount"] == 4000.0
    assert outstanding(client, invoice["id"]) == 6000.0
    ledger = client.get(
        f"/api/v1/payment-applications?payment_id={money['id']}", headers=HEADERS
    ).json()["data"]
    assert len(ledger) == 1


def test_a_multi_line_call_may_carry_an_idempotency_key(client: TestClient) -> None:
    """An idempotency key names the CALL, not a row. When both were conflated
    the partial unique index made any keyed call of more than one line collide
    with itself — a 500 on the second row."""
    person = employee(client)
    buyer = customer(client)
    first = sales_invoice(client, 4000.0, employee_id=person, customer_id=buyer["id"])
    second = sales_invoice(client, 3000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 7000.0, employee_id=person, customer_id=buyer["id"])
    lines = [
        {"applied_to_type": "invoice", "applied_to_id": first["id"], "amount_applied": 4000.0},
        {"applied_to_type": "invoice", "applied_to_id": second["id"], "amount_applied": 3000.0},
    ]

    posted = apply(client, money["id"], lines, idempotency_key="ar-batch-7")
    assert posted["replayed"] is False
    assert len(posted["applications"]) == 2
    assert posted["applied_amount"] == 7000.0

    replayed = apply(client, money["id"], lines, idempotency_key="ar-batch-7")
    assert replayed["replayed"] is True
    assert len(replayed["applications"]) == 2
    assert replayed["applied_amount"] == 7000.0
    assert outstanding(client, first["id"]) == 0.0
    assert outstanding(client, second["id"]) == 0.0

    ledger = client.get(
        f"/api/v1/payment-applications?payment_id={money['id']}", headers=HEADERS
    ).json()["data"]
    assert len(ledger) == 2



def reimbursement_invoice(client: TestClient, claim_id: str) -> dict:
    """Approve the claim and raise its reimbursement invoice — the route money
    takes now that the claim itself takes none."""
    client.post(f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=HEADERS)
    client.post("/api/v1/approval-records", headers=HEADERS, json={
        "entity_type": "expense_claim", "entity_id": claim_id, "action": "approved",
        "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
    moved = client.patch(f"/api/v1/expense-claims/{claim_id}",
                         json={"status": "approved"}, headers=HEADERS)
    assert moved.status_code == 200, moved.text
    raised = client.post(f"/api/v1/expense-claims/{claim_id}/invoice", headers=HEADERS)
    assert raised.status_code == 201, raised.text
    return raised.json()["data"]


def test_a_payment_settles_an_expense_claim(client: TestClient) -> None:
    """报销付款, paid straight against the claim.

    The lighter of the two routes a workspace may take: no invoice, fewer
    documents, same money. `tests/test_reimbursement_modes.py` covers the
    other route and the rule that a single claim may not take both.
    """
    person = employee(client, "出差的小李")
    cashier = employee(client, "出纳")
    claim = post(client, "/api/v1/expense-claims", {"employee_id": person, "title": "7月差旅"})
    post(
        client, "/api/v1/expense-items",
        {"claim_id": claim["id"], "employee_id": person, "expense_date": "2026-07-11", "amount": 480.0},
    )
    post(
        client, "/api/v1/expense-items",
        {"claim_id": claim["id"], "employee_id": person, "expense_date": "2026-07-12", "amount": 320.0},
    )
    # deliberately larger than the claim, so the guard that fires below is the
    # CLAIM's limit and not the payment's
    payout = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound",
            "employee_id": cashier,
            "payee_employee_id": person,
            "amount": 2000.0,
            "status": "paid",
        },
    )

    result = apply(
        client, payout["id"],
        [{"applied_to_type": "expense_claim", "applied_to_id": claim["id"], "amount_applied": 800.0}],
    )
    # the claim has no total column — the sum of its live items is the claim
    assert result["targets"][0]["settleable_total"] == 800.0
    assert result["targets"][0]["outstanding_amount"] == 0.0

    over = apply(
        client, payout["id"],
        [{"applied_to_type": "expense_claim", "applied_to_id": claim["id"], "amount_applied": 300.0}],
        expect=409,
    )
    assert "over-applying this expense claim" in over["detail"]


def test_a_refund_nets_against_the_receipt_that_overpaid(client: TestClient) -> None:
    """OFBiz's toPaymentId: money going back out settles part of the money that
    came in, without inventing a credit-note entity."""
    person = employee(client)
    buyer = customer(client)
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    refund = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound",
            "employee_id": person,
            "customer_id": buyer["id"],
            "amount": 2000.0,
            "status": "paid",
        },
    )

    result = apply(
        client, refund["id"],
        [{"applied_to_type": "payment", "applied_to_id": money["id"], "amount_applied": 2000.0}],
    )
    assert result["applied_amount"] == 2000.0
    assert result["targets"][0]["outstanding_amount"] == 8000.0

    receipt_detail = client.get(f"/api/v1/payments/{money['id']}/detail", headers=HEADERS).json()["data"]
    assert receipt_detail["applied_amount"] == 2000.0
    assert receipt_detail["unapplied_amount"] == 8000.0


def test_a_payment_cannot_settle_itself(client: TestClient) -> None:
    money = receipt(client, 1000.0)
    body = apply(
        client, money["id"],
        [{"applied_to_type": "payment", "applied_to_id": money["id"], "amount_applied": 500.0}],
        expect=422,
    )
    assert "cannot settle itself" in body["detail"]


def test_settling_a_deleted_document_is_refused(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    assert client.delete(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS).status_code == 204

    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 1000.0}],
        expect=404,
    )


def test_a_payment_with_applications_cannot_be_deleted(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 1000.0}],
    )

    blocked = client.delete(f"/api/v1/payments/{money['id']}", headers=HEADERS)
    assert blocked.status_code == 409
    assert "reverse those applications" in blocked.json()["detail"]

    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": -1000.0}],
    )
    assert client.delete(f"/api/v1/payments/{money['id']}", headers=HEADERS).status_code == 204


def test_a_paid_payments_amount_is_frozen(client: TestClient) -> None:
    """The amount is what an approver approved and what the ledger measured
    against. Restating it afterwards is a different payment — and if it were
    allowed, the over-application guard could be walked around with a PATCH."""
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 5000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 5000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 5000.0}],
    )

    for amount in (2000.0, 999999.0):
        response = client.patch(
            f"/api/v1/payments/{money['id']}", json={"amount": amount}, headers=HEADERS
        )
        assert response.status_code == 409, amount
        assert "cannot be restated" in response.json()["detail"]
    assert client.get(
        f"/api/v1/payments/{money['id']}", headers=HEADERS
    ).json()["data"]["amount"] == 5000.0


def test_a_draft_payments_amount_cannot_drop_below_what_is_applied(client: TestClient) -> None:
    """The editable-state gate is the outer fence; this is the inner one, for a
    payment still in draft that money has already been applied from."""
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 5000.0, employee_id=person, customer_id=buyer["id"])
    money = post(
        client, "/api/v1/payments",
        {
            "direction": "inbound", "employee_id": person, "customer_id": buyer["id"],
            "amount": 5000.0,
        },
    )
    assert money["status"] == "draft"
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 5000.0}],
    )

    response = client.patch(
        f"/api/v1/payments/{money['id']}", json={"amount": 2000.0}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "already applied" in response.json()["detail"]
    # raising it while still editable is fine
    assert client.patch(
        f"/api/v1/payments/{money['id']}", json={"amount": 8000.0}, headers=HEADERS
    ).status_code == 200


def test_a_payment_names_exactly_one_counterparty(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    supplier = vendor(client)

    none_named = client.post(
        "/api/v1/payments",
        json={"direction": "inbound", "employee_id": person, "amount": 100.0},
        headers=HEADERS,
    )
    assert none_named.status_code == 422
    assert "exactly one counterparty" in none_named.json()["detail"]

    two_named = client.post(
        "/api/v1/payments",
        json={
            "direction": "inbound",
            "employee_id": person,
            "amount": 100.0,
            "customer_id": buyer["id"],
            "vendor_id": supplier["id"],
        },
        headers=HEADERS,
    )
    assert two_named.status_code == 422


def test_an_outbound_payment_walks_the_approval_half(client: TestClient) -> None:
    """付款审批 is the most-approved document there is, so the payment family
    keeps the full draft → submitted → approved → paid lifecycle."""
    person = employee(client)
    supplier = vendor(client)
    payment = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound",
            "employee_id": person,
            "vendor_id": supplier["id"],
            "amount": 26000.0,
            "counterparty_account": "6222 0000 1111 2222",
        },
    )
    assert payment["status"] == "draft"

    submitted = client.post(f"/api/v1/payments/{payment['id']}/submit", headers=HEADERS)
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "submitted"

    # a submitted payment cannot jump straight to paid
    jump = client.patch(f"/api/v1/payments/{payment['id']}", json={"status": "paid"}, headers=HEADERS)
    assert jump.status_code == 409

    approved = client.patch(
        f"/api/v1/payments/{payment['id']}", json={"status": "approved"}, headers=HEADERS
    )
    assert approved.status_code == 200
    paid = client.patch(f"/api/v1/payments/{payment['id']}", json={"status": "paid"}, headers=HEADERS)
    assert paid.status_code == 200
    assert paid.json()["data"]["paid_at"] is not None


def test_the_receivables_queue_is_derived_from_the_ledger(client: TestClient) -> None:
    """`outstanding=true` measures against the applications, not a status —
    which is what lets a partly-paid invoice stay in the queue without needing
    a state to say so."""
    person = employee(client)
    buyer = customer(client)
    settled = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    partly = sales_invoice(client, 5000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 3000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [
            {"applied_to_type": "invoice", "applied_to_id": settled["id"], "amount_applied": 1000.0},
            {"applied_to_type": "invoice", "applied_to_id": partly["id"], "amount_applied": 2000.0},
        ],
    )

    queue = client.get(
        "/api/v1/invoices?direction=sales&outstanding=true", headers=HEADERS
    ).json()["data"]
    ids = {row["id"] for row in queue}
    assert partly["id"] in ids
    # fully settled, so it has left the queue without any status change
    assert settled["id"] not in ids
    assert client.get(f"/api/v1/invoices/{settled['id']}", headers=HEADERS).json()["data"]["status"] == "draft"


def test_the_overdue_queue_combines_direction_outstanding_and_due_date(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    overdue = sales_invoice(
        client, 1000.0, employee_id=person, customer_id=buyer["id"], due_date="2026-01-31"
    )
    sales_invoice(
        client, 1000.0, employee_id=person, customer_id=buyer["id"], due_date="2026-12-31"
    )
    # no due date at all: no agreed term, so never overdue
    sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])

    queue = client.get(
        "/api/v1/invoices?direction=sales&outstanding=true&due_before=2026-08-02", headers=HEADERS
    ).json()["data"]
    assert [row["id"] for row in queue] == [overdue["id"]]


def test_unapplied_payments_are_the_claim_queue(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    matched = receipt(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    floating = receipt(client, 700.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, matched["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 1000.0}],
    )

    queue = client.get("/api/v1/payments?unapplied=true", headers=HEADERS).json()["data"]
    assert [row["id"] for row in queue] == [floating["id"]]


def test_the_flow_queue_hides_documents_someone_is_already_on(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    chased = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    unchased = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    post(
        client, "/api/v1/todos",
        {
            "employee_id": person,
            "entity_type": "invoice",
            "entity_id": chased["id"],
            "title": "催收",
        },
    )

    queue = client.get(
        "/api/v1/invoices?outstanding=true&without_open_todo=true", headers=HEADERS
    ).json()["data"]
    assert [row["id"] for row in queue] == [unchased["id"]]


def test_the_three_way_match_reports_ordered_received_and_billed(client: TestClient) -> None:
    """采购三单匹配: the server states the three numbers and their gaps; whether
    a gap is acceptable is the agent's call against the workflow definition."""
    person = employee(client)
    supplier = vendor(client)
    po = post(
        client, "/api/v1/purchase-orders",
        {"vendor_id": supplier["id"], "employee_id": person, "title": "服务器采购"},
    )
    po_line = post(
        client, "/api/v1/purchase-order-items",
        {
            "po_id": po["id"],
            "line_no": 1,
            "product_name_snapshot": "服务器",
            "quantity": 10,
            "unit_price": 2600.0,
            "amount": 26000.0,
        },
    )
    # only 8 of 10 arrived
    received = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"lines": [{"po_item_id": po_line["id"], "quantity": 8}]},
        headers=HEADERS,
    )
    assert received.status_code == 200, received.text

    # ...but the vendor billed all 10
    bill = post(
        client, "/api/v1/invoices",
        {
            "direction": "purchase",
            "employee_id": person,
            "vendor_id": supplier["id"],
            "title": "服务器货款",
            "purchase_order_id": po["id"],
            "items": [
                {
                    "product_name_snapshot": "服务器",
                    "quantity": 10,
                    "unit_price": 2600.0,
                    "amount": 26000.0,
                    "purchase_order_item_id": po_line["id"],
                }
            ],
        },
    )

    match = client.get(f"/api/v1/invoices/{bill['id']}/detail", headers=HEADERS).json()["data"]["order_match"]
    assert match["order_type"] == "purchase_order"
    assert match["order_no"] == po["po_number"]
    line = match["lines"][0]
    assert line["ordered_quantity"] == 10.0
    assert line["received_quantity"] == 8.0
    assert line["billed_quantity"] == 10.0
    assert line["quantity_variance"] == 0.0
    # billed two more than arrived — the fact the approver needs
    assert line["receipt_variance"] == 2.0
    assert match["ordered_total"] == 26000.0
    assert match["billed_total"] == 26000.0
    assert match["unbilled_total"] == 0.0
    assert match["unmatched_line_count"] == 0


def test_the_match_sums_billing_across_every_invoice_on_the_order(client: TestClient) -> None:
    """A second invoice for the same order must not look like the first never
    happened."""
    person = employee(client)
    supplier = vendor(client)
    po = post(
        client, "/api/v1/purchase-orders",
        {"vendor_id": supplier["id"], "employee_id": person, "title": "分批开票"},
    )
    po_line = post(
        client, "/api/v1/purchase-order-items",
        {"po_id": po["id"], "product_name_snapshot": "服务器", "quantity": 10, "unit_price": 2600.0, "amount": 26000.0},
    )

    for quantity, amount in ((6, 15600.0), (4, 10400.0)):
        bill = post(
            client, "/api/v1/invoices",
            {
                "direction": "purchase",
                "employee_id": person,
                "vendor_id": supplier["id"],
                "title": "分批",
                "purchase_order_id": po["id"],
                "items": [
                    {
                        "product_name_snapshot": "服务器",
                        "quantity": quantity,
                        "amount": amount,
                        "purchase_order_item_id": po_line["id"],
                    }
                ],
            },
        )

    match = client.get(f"/api/v1/invoices/{bill['id']}/detail", headers=HEADERS).json()["data"]["order_match"]
    assert match["lines"][0]["billed_quantity"] == 10.0
    assert match["billed_total"] == 26000.0
    assert match["unbilled_total"] == 0.0


def test_lines_that_match_no_order_line_are_counted_not_hidden(client: TestClient) -> None:
    person = employee(client)
    supplier = vendor(client)
    po = post(
        client, "/api/v1/purchase-orders",
        {"vendor_id": supplier["id"], "employee_id": person, "title": "PO"},
    )
    bill = post(
        client, "/api/v1/invoices",
        {
            "direction": "purchase",
            "employee_id": person,
            "vendor_id": supplier["id"],
            "title": "含计划外运费",
            "purchase_order_id": po["id"],
            "items": [
                {
                    "invoice_item_type": "shipping",
                    "product_name_snapshot": "运费",
                    "amount": 300.0,
                }
            ],
        },
    )

    match = client.get(f"/api/v1/invoices/{bill['id']}/detail", headers=HEADERS).json()["data"]["order_match"]
    assert match["unmatched_line_count"] == 1


def test_an_invoice_without_an_order_has_no_match_block(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 1000.0, employee_id=person, customer_id=buyer["id"])
    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail.get("order_match") is None


def test_historical_payments_import_unapplied(client: TestClient) -> None:
    """期初: the money facts import, but what each one settled goes through the
    guarded apply endpoint — a bulk path into the ledger would be a bulk path
    around the checks that make it trustworthy."""
    post(client, "/api/v1/employees", {"name": "出纳", "employee_code": "E-CASH"})
    post(client, "/api/v1/customers", {"name": "上海市第一医院", "customer_code": "C-SH1"})
    rows = [
        {
            "payment_no": "2025-REC-0001",
            "direction": "inbound",
            "employee_code": "E-CASH",
            "customer_code": "C-SH1",
            "amount": 4000.0,
            "payment_date": "2025-12-20",
            "status": "paid",
            "reference_no": "BANK-99887766",
        }
    ]
    result = post(client, "/api/v1/payments/bulk", {"rows": rows}, expect=200)
    assert result["summary"]["created"] == 1

    imported = client.get("/api/v1/payments", headers=HEADERS).json()["data"][0]
    assert imported["payment_no"] == "2025-REC-0001"
    assert imported["counterparty_name_snapshot"] == "上海市第一医院"
    assert imported["applied_amount"] == 0.0

    rerun = post(client, "/api/v1/payments/bulk", {"rows": rows}, expect=200)
    assert rerun["summary"]["unchanged"] == 1


def test_a_payment_carries_approval_facts_and_todos(client: TestClient) -> None:
    """付款审批 needs both: an approver records a fact against the payment, and
    the flow agent assigns the todo that got them there."""
    person = employee(client)
    supplier = vendor(client)
    payment = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound",
            "employee_id": person,
            "vendor_id": supplier["id"],
            "amount": 26000.0,
        },
    )
    client.post(f"/api/v1/payments/{payment['id']}/submit", headers=HEADERS)

    post(
        client, "/api/v1/todos",
        {
            "employee_id": person,
            "entity_type": "payment",
            "entity_id": payment["id"],
            "title": "复核收款账号与供应商档案是否一致",
        },
    )
    post(
        client, "/api/v1/approval-records",
        {
            "entity_type": "payment",
            "entity_id": payment["id"],
            "action": "approved",
            "sequence_no": 2,
            "approver_id": person,
            "comment": "账号与档案一致",
        },
    )

    detail = client.get(f"/api/v1/payments/{payment['id']}/detail", headers=HEADERS).json()["data"]
    # the submission is a fact the server records when /submit runs, so the
    # trail opens with it rather than with the decision
    assert [record["action"] for record in detail["approval_records"]] == ["submitted", "approved"]


def test_the_ledgers_target_is_constrained_in_the_database() -> None:
    """The API refuses a bad target, but money rows are worth a backstop the
    API cannot bypass: one nullable FK per kind, exactly one set, and an
    invoice line only inside its own invoice."""
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.models import PaymentApplication

    from conftest import make_stack

    with make_stack(
        [
            Tenant(id=TEST_TENANT, name="Settlement Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as (test_client, engine):
        person = employee(test_client)
        buyer = customer(test_client)
        invoice = sales_invoice(test_client, 1000.0, employee_id=person, customer_id=buyer["id"])
        money = receipt(test_client, 1000.0, employee_id=person, customer_id=buyer["id"])

        def accepted(**columns) -> bool:
            with Session(bind=engine) as db:
                db.add(
                    PaymentApplication(
                        tenant_id=TEST_TENANT,
                        payment_id=money["id"],
                        amount_applied=1.0,
                        **columns,
                    )
                )
                try:
                    db.flush()
                except IntegrityError:
                    return False
                finally:
                    db.rollback()
                return True

        # settling nothing at all is money that vanished
        assert not accepted()
        # settling two documents cannot be reconciled against either
        assert not accepted(invoice_id=invoice["id"], to_payment_id=money["id"])
        # an invoice line without its invoice names nothing
        assert not accepted(
            expense_claim_id=None,
            invoice_item_id=client_invoice_line(test_client, invoice["id"]),
        )
        # and the ordinary shape stands
        assert accepted(invoice_id=invoice["id"])


def client_invoice_line(client: TestClient, invoice_id: str) -> str:
    return post(
        client,
        "/api/v1/invoice-items",
        {"invoice_id": invoice_id, "product_name_snapshot": "货物", "amount": 100.0},
    )["id"]


def _audit_money_checks() -> list[tuple[str, str]]:
    """The settlement invariants out of scripts/data_integrity_audit.py, loaded
    textually because scripts/ is not an importable package."""
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    # everything above main(), so the helpers the check SQL is built from come
    # along with it — slicing at STRUCTURAL_CHECKS would leave them undefined
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    return [
        (name, sql)
        for name, sql in namespace["STRUCTURAL_CHECKS"]
        if any(
            marker in sql
            for marker in ("payment_applications", "applied_amount", "billing_account")
        )
    ]


def test_the_integrity_audits_money_invariants_hold_on_real_settlements(client: TestClient) -> None:
    """The audit is a script, so nothing else would notice it drifting from the
    schema — and its checks are exactly the ones that would let a wrong balance
    sit unnoticed. Build a database that exercises every settlement shape,
    including a netted refund, then run the audit's own SQL over it.

    The netting case earns its place: an earlier version of the payment check
    summed only the rows where a payment was the SOURCE, so any netted receipt
    would have been reported as drifted forever.
    """
    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    person = employee(client)
    cashier = employee(client, "出纳")
    buyer = customer(client)

    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 6000.0}],
    )
    # a reversal, so counter-entries are in the data too
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": -1000.0}],
    )
    # a refund netted against that receipt — the case the old check missed
    refund = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": person, "customer_id": buyer["id"],
            "amount": 2000.0, "status": "paid",
        },
    )
    apply(
        client, refund["id"],
        [{"applied_to_type": "payment", "applied_to_id": money["id"], "amount_applied": 2000.0}],
    )
    # and an expense claim settled by its own payout
    claim = post(client, "/api/v1/expense-claims", {"employee_id": person, "title": "差旅"})
    post(
        client, "/api/v1/expense-items",
        {"claim_id": claim["id"], "employee_id": person, "expense_date": "2026-07-11", "amount": 800.0},
    )
    payout = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": cashier, "payee_employee_id": person,
            "amount": 800.0, "status": "paid",
        },
    )
    apply(
        client, payout["id"],
        [{"applied_to_type": "invoice", "applied_to_id": reimbursement_invoice(client, claim["id"])["id"],
          "amount_applied": 800.0}],
    )
    # a prepaid account, drawn down and partly refunded, plus a points account
    # with an expired batch — so the account invariants meet real rows too
    account = billing_account(client, customer_id=buyer["id"])
    deposit = receipt(client, 20000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, deposit["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 20000.0}],
    )
    post(
        client, f"/api/v1/billing-accounts/{account['id']}/entries",
        {"lines": [{"amount": -5000.0, "reason": "charge"}]}, expect=200,
    )
    loyalty = post(
        client, "/api/v1/billing-accounts",
        {"name": "会员积分", "unit_type": "points", "unit": "point", "customer_id": buyer["id"]},
    )
    granted = post(
        client, f"/api/v1/billing-accounts/{loyalty['id']}/entries",
        {"lines": [{"amount": 300.0, "reason": "earned", "expires_at": "2025-12-31T00:00:00Z"}]},
        expect=200,
    )
    post(
        client, f"/api/v1/billing-accounts/{loyalty['id']}/entries",
        {"lines": [{"amount": -300.0, "reason": "expired",
                    "entity_type": "billing_account_entry",
                    "entity_id": granted["entries"][0]["id"]}]},
        expect=200,
    )

    checks = _audit_money_checks()
    assert len(checks) >= 15, "the audit lost its settlement or account checks"
    db = next(app.dependency_overrides[get_db]())
    try:
        for name, sql in checks:
            offending = db.execute(sql_text(sql)).scalar()
            assert offending == 0, f"{name}: {offending} offending rows"
    finally:
        db.close()


def billing_account(client: TestClient, **overrides) -> dict:
    body = {
        "name": "预存款",
        "unit_type": "currency",
        "unit": "CNY",
        "customer_id": overrides.pop("customer_id", None) or customer(client)["id"],
    }
    body.update(overrides)
    return post(client, "/api/v1/billing-accounts", body)


def test_a_customer_prepayment_lands_in_their_account(client: TestClient) -> None:
    """预存: money paid into a standing account rather than against a claim.
    Unlike every other target this one has no ceiling — a deposit is not
    something you can over-settle."""
    person = employee(client)
    buyer = customer(client)
    account = billing_account(client, customer_id=buyer["id"])
    money = receipt(client, 100000.0, employee_id=person, customer_id=buyer["id"])

    result = apply(
        client, money["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 100000.0}],
    )
    assert result["applied_amount"] == 100000.0
    target = result["targets"][0]
    assert target["balance"] == 100000.0
    assert target["available_amount"] == 100000.0
    # a deposit has no claim to settle, so these do not apply
    assert target.get("settleable_total") is None
    assert target.get("outstanding_amount") is None

    # and the balance moved through the account's own ledger, so the two agree
    detail = client.get(
        f"/api/v1/billing-accounts/{account['id']}/detail", headers=HEADERS
    ).json()["data"]
    assert detail["balance"] == 100000.0
    assert [entry["reason"] for entry in detail["entries"]] == ["deposit"]
    assert detail["entries"][0]["entity_type"] == "payment"
    assert detail["entries"][0]["entity_id"] == money["id"]


def test_a_refund_out_of_an_account_reduces_its_balance(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    account = billing_account(client, customer_id=buyer["id"])
    deposit = receipt(client, 100000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, deposit["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 100000.0}],
    )

    refund = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": person, "customer_id": buyer["id"],
            "amount": 30000.0, "status": "paid",
        },
    )
    result = apply(
        client, refund["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 30000.0}],
    )
    # an outbound payment applied here REDUCES the balance
    assert result["targets"][0]["balance"] == 70000.0


def test_an_account_cannot_be_refunded_past_its_credit_line(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    account = billing_account(client, customer_id=buyer["id"])
    refund = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": person, "customer_id": buyer["id"],
            "amount": 5000.0, "status": "paid",
        },
    )

    body = apply(
        client, refund["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 5000.0}],
        expect=409,
    )
    assert "only has 0.00 available" in body["detail"]


def test_money_can_never_be_applied_to_a_points_account(client: TestClient) -> None:
    """The reason unit_type is a constrained column and not a vocabulary."""
    person = employee(client)
    buyer = customer(client)
    points = post(
        client, "/api/v1/billing-accounts",
        {"name": "会员积分", "unit_type": "points", "unit": "point", "customer_id": buyer["id"]},
    )
    money = receipt(client, 500.0, employee_id=person, customer_id=buyer["id"])

    body = apply(
        client, money["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": points["id"],
          "amount_applied": 500.0}],
        expect=409,
    )
    assert "counts point, not money" in body["detail"]


def test_a_deposit_can_be_reversed_by_a_counter_entry(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    account = billing_account(client, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 10000.0}],
    )

    reversed_result = apply(
        client, money["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": -10000.0, "note": "记错账户了"}],
    )
    assert reversed_result["applied_amount"] == 0.0
    assert reversed_result["targets"][0]["balance"] == 0.0
    # both movements stand in the account's ledger
    ledger = client.get(
        f"/api/v1/billing-account-entries?billing_account_id={account['id']}", headers=HEADERS
    ).json()["data"]
    assert sorted(row["amount"] for row in ledger) == [-10000.0, 10000.0]


def test_a_frozen_account_refuses_settlement_too(client: TestClient) -> None:
    person = employee(client)
    buyer = customer(client)
    account = billing_account(client, customer_id=buyer["id"])
    client.patch(
        f"/api/v1/billing-accounts/{account['id']}", json={"status": "frozen"}, headers=HEADERS
    )
    money = receipt(client, 1000.0, employee_id=person, customer_id=buyer["id"])

    body = apply(
        client, money["id"],
        [{"applied_to_type": "billing_account", "applied_to_id": account["id"],
          "amount_applied": 1000.0}],
        expect=409,
    )
    assert "frozen" in body["detail"]


def test_a_settled_invoices_total_cannot_be_moved_under_the_ledger(client: TestClient) -> None:
    """The hole this closes: /apply refuses to over-apply, but that guard is
    worth nothing if the amount it measured against can be shrunk afterwards.
    A plain PATCH used to leave an invoice settled beyond what it bills — a
    state the integrity audit reports as corruption."""
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 10000.0}],
    )
    client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=HEADERS)
    client.patch(f"/api/v1/invoices/{invoice['id']}", json={"status": "issued"}, headers=HEADERS)

    for field, value in (("total_amount", 100.0), ("tax_amount", 5.0), ("currency", "USD")):
        response = client.patch(
            f"/api/v1/invoices/{invoice['id']}", json={field: value}, headers=HEADERS
        )
        assert response.status_code == 409, field
        assert "cannot be restated" in response.json()["detail"]

    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["billed_total"] == 10000.0
    assert detail["outstanding_amount"] == 0.0

    # fields that are not the money stay editable — a wrong remark is not a
    # reason to void a tax document
    assert client.patch(
        f"/api/v1/invoices/{invoice['id']}", json={"remarks": "客户要求补充说明"}, headers=HEADERS
    ).status_code == 200


def test_a_settled_invoice_cannot_be_deleted(client: TestClient) -> None:
    """Same rule the payment side keeps: the ledger must not point at a
    document nobody can see."""
    person = employee(client)
    buyer = customer(client)
    invoice = sales_invoice(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    money = receipt(client, 10000.0, employee_id=person, customer_id=buyer["id"])
    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 10000.0}],
    )

    blocked = client.delete(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS)
    assert blocked.status_code == 409
    assert "reverse those applications" in blocked.json()["detail"]

    apply(
        client, money["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": -10000.0}],
    )
    assert client.delete(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS).status_code == 204


def test_a_paid_out_expense_claim_cannot_be_deleted(client: TestClient) -> None:
    """`ensure_nothing_applied` reads the claim's OWN applied_amount, which
    stays zero forever now that money reaches it through the reimbursement
    invoice. That check became decorative the moment settlement moved: a fully
    paid claim would have deleted cleanly and left a payable whose origin was
    gone. The invoice's existence is what blocks it, settled or not."""
    person = employee(client)
    cashier = employee(client, "出纳")
    claim = post(client, "/api/v1/expense-claims", {"employee_id": person, "title": "差旅"})
    post(
        client, "/api/v1/expense-items",
        {"claim_id": claim["id"], "employee_id": person, "expense_date": "2026-07-11", "amount": 800.0},
    )
    invoice = reimbursement_invoice(client, claim["id"])

    # blocked already, before a single cent has moved
    blocked = client.delete(f"/api/v1/expense-claims/{claim['id']}", headers=HEADERS)
    assert blocked.status_code == 409
    assert invoice["invoice_no"] in blocked.json()["detail"]

    payout = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": cashier, "payee_employee_id": person,
            "amount": 800.0, "status": "paid",
        },
    )
    apply(
        client, payout["id"],
        [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 800.0}],
    )
    assert client.delete(f"/api/v1/expense-claims/{claim['id']}",
                         headers=HEADERS).status_code == 409

    # …and the claim's own applied_amount never moved, which is the point
    fresh = client.get(f"/api/v1/expense-claims/{claim['id']}", headers=HEADERS).json()["data"]
    assert float(fresh.get("applied_amount") or 0) == 0.0


def test_recording_and_applying_are_separable_duties(client: TestClient) -> None:
    """出纳记账 and 会计核销 are different capabilities on purpose."""
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, SYSTEM_CAPABILITY_NAMES

    assert "payment.record" in SYSTEM_CAPABILITY_NAMES
    assert "payment.apply" in SYSTEM_CAPABILITY_NAMES
    # neither is a member default — these are finance functions
    assert "payment.record" not in DEFAULT_ROLE_PERMISSIONS["member"]
    assert "payment.apply" not in DEFAULT_ROLE_PERMISSIONS["member"]
