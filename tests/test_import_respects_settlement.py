"""The importer follows the rules every other entrance follows.

Review R01: `/payments/bulk` rewrote a fully settled payment's amount to 1
while its 100 of applications stood — the PATCH route refused the same
change with a 409. Review R06: the importer copied an explicit employee_id
into the row without asking whose it was, so tenant A could file a payment
under tenant B's employee. Both are now refused as row errors that name the
reason.
"""

from __future__ import annotations

from conftest import make_client, provision_tenant


def _payment_row(**overrides) -> dict:
    row = {"payment_no": "PAY-H-1", "direction": "inbound", "employee_code": "E-1", "customer_code": "C-1",
           "amount": 100.0, "payment_date": "2025-12-20", "status": "paid"}
    row.update(overrides)
    return row


def test_a_settled_payment_is_not_rewritten_by_reimport() -> None:
    """The review's reproduction, as a regression: 100 paid and fully applied,
    the PATCH says 409, and the bulk path used to say updated=1."""
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Import Co", email="admin@import-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "出纳", "employee_code": "E-1"}, headers=admin).json()["data"]["id"]
        cust = client.post("/api/v1/customers", json={"name": "医院", "customer_code": "C-1"}, headers=admin).json()["data"]["id"]
        first = client.post("/api/v1/payments/bulk", json={"rows": [_payment_row()]}, headers=admin).json()["data"]
        assert first["summary"]["created"] == 1, first
        payment = client.get("/api/v1/payments", headers=admin).json()["data"][0]

        corrected = client.post("/api/v1/payments/bulk", json={"rows": [_payment_row(amount=90.0)]}, headers=admin).json()["data"]
        assert corrected["results"][0]["outcome"] == "updated", "history nothing stands on may still be corrected"

        invoice = client.post("/api/v1/invoices", headers=admin, json={
            "direction": "sales", "employee_id": emp, "customer_id": cust, "title": "货款",
            "total_amount": 90.0, "status": "issued"}).json()["data"]
        applied = client.post(f"/api/v1/payments/{payment['id']}/apply", headers=admin, json={
            "lines": [{"applied_to_type": "invoice", "applied_to_id": invoice["id"], "amount_applied": 90.0}]})
        assert applied.status_code == 200, applied.text

        rewrite = client.post("/api/v1/payments/bulk", json={"rows": [_payment_row(amount=1.0)]}, headers=admin).json()["data"]
        result = rewrite["results"][0]
        assert result["outcome"] == "error" and "applied" in result["error"], result
        listed = client.get("/api/v1/payments", headers=admin).json()["data"]
        assert float(listed[0]["amount"]) == 90.0 and float(listed[0]["applied_amount"]) == 90.0, \
            "the settled payment keeps its amount; the correction is a counter-entry"


def test_the_importer_refuses_another_tenants_ids() -> None:
    with make_client([]) as client:
        a = provision_tenant(client, company_name="Tenant A", email="admin@tenant-a.example")
        b = provision_tenant(client, company_name="Tenant B", email="admin@tenant-b.example")
        admin_a = {"X-API-Key": a["plain_text_api_key"]}
        admin_b = {"X-API-Key": b["plain_text_api_key"]}
        client.post("/api/v1/customers", json={"name": "医院", "customer_code": "C-1"}, headers=admin_a)
        mine = client.post("/api/v1/employees", json={"name": "我们的", "employee_code": "E-A"}, headers=admin_a).json()["data"]["id"]
        theirs = client.post("/api/v1/employees", json={"name": "别人的", "employee_code": "E-B"}, headers=admin_b).json()["data"]["id"]

        rows = [_payment_row(payment_no="PAY-X-1", employee_code=None, employee_id=theirs),
                _payment_row(payment_no="PAY-X-2", employee_code=None, employee_id=mine)]
        result = client.post("/api/v1/payments/bulk", json={"rows": rows, "on_error": "skip"}, headers=admin_a).json()["data"]
        by_no = {r["number"]: r for r in result["results"]}
        assert by_no["PAY-X-1"]["outcome"] == "error" and "not in this workspace" in by_no["PAY-X-1"]["error"]
        assert by_no["PAY-X-2"]["outcome"] == "created", "an id of our own resolves exactly as a code does"
