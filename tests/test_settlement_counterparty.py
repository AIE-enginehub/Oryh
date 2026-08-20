"""Money owed to one party is not discharged by paying another.

An application says: the money that moved is the money this document was
waiting for. That is a lie unless the same party stands on both sides.

Only the billing account checked it — "without this, one customer's cheque
could quietly fund another's account". The identical hole was open on invoices,
and it is not theoretical: it is exactly what a plausible expense-reimbursement
design produces. Raise a purchase invoice against the merchant who issued the
receipt, pay the employee who advanced the money, apply one to the other, and
the API answered 200 — clearing a payable to a supplier who was never paid,
in a workspace that may also buy from that supplier directly.

The pairs now live on `SettlementTarget`, so the check is a property of being a
settlement target rather than something each call site remembers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.billing import SETTLEMENT_TARGETS

from conftest import provision_tenant


@pytest.fixture()
def shop(client: TestClient):
    t = provision_tenant(client, company_name="CP Co", email="admin@cp-co.example")
    headers = {"X-API-Key": t["plain_text_api_key"]}

    def post(path, body, expect=(200, 201)):
        r = client.post(f"/api/v1{path}", json=body, headers=headers)
        assert r.status_code in expect, f"{path} -> {r.status_code} {r.text[:300]}"
        return r.json()["data"]

    return {"client": client, "headers": headers, "post": post,
            "employee": post("/employees", {"name": "李工"})["id"],
            "other_employee": post("/employees", {"name": "王工"})["id"],
            "vendor": post("/vendors", {"name": "Hotel Ltd"})["id"],
            "customer": post("/customers", {"name": "Acme"})["id"]}


def apply_to(shop, payment_id: str, target_type: str, target_id: str, amount: float):
    return shop["client"].post(
        f"/api/v1/payments/{payment_id}/apply",
        json={"lines": [{"applied_to_type": target_type, "applied_to_id": target_id,
                         "amount_applied": amount}]},
        headers=shop["headers"],
    )


def test_every_settlement_target_declares_its_counterparty() -> None:
    """The registry guard. A new target that forgets the pairs ships with the
    hole this file exists to close, and nothing else would say so."""
    missing = [name for name, spec in SETTLEMENT_TARGETS.items() if not spec.counterparty_fields]
    assert not missing, f"settlement targets with no counterparty check: {missing}"


def test_paying_an_employee_does_not_settle_a_vendors_bill(shop) -> None:
    """The reported shape, and the one that reads as reasonable.

    The merchant issued the receipt, so their bill looks like the thing being
    reimbursed — but the merchant was already paid, by the employee, out of the
    employee's own pocket. The company never owed them anything.
    """
    bill = shop["post"]("/invoices", {
        "direction": "purchase", "employee_id": shop["employee"], "vendor_id": shop["vendor"],
        "title": "Hotel, 18 July", "total_amount": 820.0})
    payout = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "amount": 820.0, "payment_date": "2026-07-25"})

    refused = apply_to(shop, payout["id"], "invoice", bill["id"], 820.0)
    assert refused.status_code == 409, refused.text
    assert "names a different party" in refused.json()["detail"]


def test_the_right_vendor_still_settles_its_own_bill(shop) -> None:
    """The guard must not be a wall — this is the ordinary payables path."""
    bill = shop["post"]("/invoices", {
        "direction": "purchase", "employee_id": shop["employee"], "vendor_id": shop["vendor"],
        "title": "Hotel, 18 July", "total_amount": 820.0})
    payout = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"], "vendor_id": shop["vendor"],
        "amount": 820.0, "payment_date": "2026-07-25"})

    ok = apply_to(shop, payout["id"], "invoice", bill["id"], 820.0)
    assert ok.status_code in (200, 201), ok.text
    assert ok.json()["data"]["targets"][0]["outstanding_amount"] == 0.0


def test_one_customers_payment_does_not_settle_anothers_invoice(shop) -> None:
    """The receivable side of the same error."""
    other = shop["post"]("/customers", {"name": "Beta Corp"})["id"]
    bill = shop["post"]("/invoices", {
        "direction": "sales", "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "June services", "total_amount": 5000.0})
    receipt = shop["post"]("/payments", {
        "direction": "inbound", "employee_id": shop["employee"], "customer_id": other,
        "amount": 5000.0, "payment_date": "2026-07-25"})

    refused = apply_to(shop, receipt["id"], "invoice", bill["id"], 5000.0)
    assert refused.status_code == 409, refused.text


def test_a_payout_to_one_employee_does_not_settle_anothers_reimbursement(shop) -> None:
    """The same rule where the counterparty column is named differently: an
    invoice carries `payee_employee_id`, and so does the payment — but they
    have to be the same person."""
    claim = shop["post"]("/expense-claims", {
        "employee_id": shop["employee"], "title": "July travel",
        "items": [{"expense_date": "2026-07-18", "amount": 300.0, "category": "transport"}]})
    client, headers = shop["client"], shop["headers"]
    client.post(f"/api/v1/expense-claims/{claim['id']}/submit", json={}, headers=headers)
    client.post("/api/v1/approval-records", headers=headers, json={
        "entity_type": "expense_claim", "entity_id": claim["id"], "action": "approved",
        "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
    client.patch(f"/api/v1/expense-claims/{claim['id']}", json={"status": "approved"},
                 headers=headers)
    invoice = client.post(f"/api/v1/expense-claims/{claim['id']}/invoice",
                          headers=headers).json()["data"]

    wrong = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["other_employee"], "amount": 300.0,
        "payment_date": "2026-07-25"})
    assert apply_to(shop, wrong["id"], "invoice", invoice["id"], 300.0).status_code == 409

    right = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "amount": 300.0, "payment_date": "2026-07-25"})
    assert apply_to(shop, right["id"], "invoice", invoice["id"], 300.0).status_code in (200, 201)
