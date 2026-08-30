"""From lead to cash, one story across every desk that touches it.

The blackbox regression walks this chain with a service key; what THIS file
adds is the capability topology: each step is performed by the credential
that would really perform it — the salesperson (crm.own + quotation/order
submit_own), the admin approving, the warehouse keeper (inventory.manage),
the finance desk (invoice.manage + payment.record + payment.apply) and the
cashier (fin_account.manage) — so a permission that quietly widens or a
desk that can no longer reach its own step fails HERE, in the story where
it matters, not only in a per-family unit test.

The numbers must reconcile at the end: 5 件 × 协议价 88 = 440, zero drift
from quotation to order, stock 10 → 5, invoice settled to 0, bank balance
440 with the register line linked to the payment.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def company():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Fullchain Co", email="admin@fullchain.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def desk(name: str, permissions: list[str], employee: bool = False) -> dict:
            emp = None
            if employee:
                emp = client.post("/api/v1/employees", json={"name": name},
                                  headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": name, "permissions": permissions},
                        headers=admin)
            body = {"email": f"{name}@fullchain.example", "role": name}
            if emp:
                body["employee_id"] = emp
            uid = client.post("/api/v1/auth/invitations", json=body,
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys",
                              json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "key": {"X-API-Key": key}}

        yield {"client": client, "admin": admin, "desk": desk}


def test_from_lead_to_cash_every_desk_plays_itself(company) -> None:
    client, admin = company["client"], company["admin"]
    sales = company["desk"]("sales", ["crm.own", "quotation.submit_own", "order.submit_own"],
                            employee=True)
    keeper = company["desk"]("keeper", ["inventory.manage"])
    finance = company["desk"]("finance", ["invoice.manage", "payment.record", "payment.apply"])
    cashier = company["desk"]("cashier", ["fin_account.manage"])

    # --- the salesperson captures and qualifies a lead -----------------
    lead = client.post("/api/v1/leads", headers=sales["key"], json={
        "employee_id": sales["employee_id"], "company_name": "泵业公司",
        "contact_name": "刘工", "phone": "13800000000", "source": "展会",
    }).json()["data"]
    assert lead["lead_no"].startswith("LD-")
    client.patch(f"/api/v1/leads/{lead['id']}", headers=sales["key"],
                 json={"status": "qualified"})

    # --- the bridge: customer + rolodex + opportunity, no catalog grant
    converted = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=sales["key"],
                            json={"opportunity_title": "泵站改造", "expected_amount": 200000})
    assert converted.status_code == 200, converted.text
    conv = converted.json()["data"]
    customer_id = conv["customer"]["id"]
    opportunity_id = conv["opportunity"]["id"]
    assert conv["contact"]["is_primary"] and conv["contact"]["name"] == "刘工"

    # --- the catalog desk (admin here) readies product, stock, 协议价 --
    product = client.post("/api/v1/products", headers=admin, json={
        "name": "工业阀门DN50", "list_price": 100.0}).json()["data"]["id"]
    position = client.post("/api/v1/inventory-items", headers=keeper["key"], json={
        "product_id": product, "facility": "main", "initial_quantity": 10,
    }).json()["data"]["id"]
    client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": product, "customer_id": customer_id,
        "customer_product_code": "KH-3301", "agreed_price": 88.0})

    # --- quotation at the agreed price, approved, sent, won -----------
    quote = client.post("/api/v1/sales-quotations", headers=sales["key"], json={
        "employee_id": sales["employee_id"], "customer_id": customer_id,
        "title": "泵站改造报价", "contact_name": "刘工", "total_amount": 440.0,
        "items": [{"line_no": 1, "product_id": product, "quantity": 5, "unit_price": 88.0}],
    }).json()["data"]
    assert client.post(f"/api/v1/sales-quotations/{quote['id']}/submit", json={},
                       headers=sales["key"]).status_code == 200
    assert client.patch(f"/api/v1/sales-quotations/{quote['id']}",
                        headers=admin, json={"status": "approved"}).status_code == 200
    assert client.post(f"/api/v1/sales-quotations/{quote['id']}/send", json={},
                       headers=sales["key"]).status_code == 200
    assert client.post(f"/api/v1/sales-quotations/{quote['id']}/close",
                       headers=sales["key"], json={"outcome": "accepted"}).status_code == 200
    won = client.patch(f"/api/v1/opportunities/{opportunity_id}", headers=sales["key"],
                       json={"status": "won"})
    assert won.json()["data"]["closed_at"] is not None

    # --- the order mirrors the won quotation with zero drift ----------
    order = client.post("/api/v1/sales-orders", headers=sales["key"], json={
        "employee_id": sales["employee_id"], "customer_id": customer_id,
        "quotation_id": quote["id"], "title": "泵站改造订单", "total_amount": 440.0,
        "items": [{"line_no": 1, "product_id": product, "quantity": 5, "unit_price": 88.0}],
    }).json()["data"]
    drift = client.get(f"/api/v1/sales-orders/{order['id']}/detail",
                       headers=sales["key"]).json()["data"]["quote_drift"]
    assert drift["amount"] == 0, f"quotation → order must not drift: {drift}"
    assert client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={},
                       headers=sales["key"]).status_code == 200
    assert client.patch(f"/api/v1/sales-orders/{order['id']}",
                        headers=admin, json={"status": "confirmed"}).status_code == 200

    # --- the keeper ships it and posts stock once ---------------------
    refused = client.post("/api/v1/shipments", headers=sales["key"], json={
        "direction": "outbound", "sales_order_id": order["id"], "items": []})
    assert refused.status_code == 403, "freight is warehouse work, not sales work"
    shipment = client.post("/api/v1/shipments", headers=keeper["key"], json={
        "direction": "outbound", "sales_order_id": order["id"], "facility": "main",
        "carrier": "SF", "tracking_no": "SF-1001",
        "items": [{"product_id": product, "quantity": 5, "inventory_item_id": position}],
    }).json()["data"]
    for state in ("packed", "shipped"):
        client.patch(f"/api/v1/shipments/{shipment['id']}", headers=keeper["key"],
                     json={"status": state})
    posted = client.post(f"/api/v1/shipments/{shipment['id']}/post-stock",
                         headers=keeper["key"])
    assert posted.status_code == 200, posted.text
    qoh = float(client.get(f"/api/v1/inventory-items/{position}",
                           headers=keeper["key"]).json()["data"]["quantity_on_hand"])
    assert qoh == 5.0, "outbound decrements exactly what shipped"
    for state in ("shipped", "signed"):
        client.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin,
                     json={"status": state})

    # --- finance invoices and settles the receipt ---------------------
    invoice = client.post("/api/v1/invoices", headers=finance["key"], json={
        "direction": "sales", "employee_id": sales["employee_id"],
        "customer_id": customer_id, "title": "泵站改造货款", "total_amount": 440.0,
    }).json()["data"]
    for state in ("submitted", "issued"):
        client.patch(f"/api/v1/invoices/{invoice['id']}", headers=admin,
                     json={"status": state})
    payment = client.post("/api/v1/payments", headers=finance["key"], json={
        "direction": "inbound", "employee_id": sales["employee_id"],
        "customer_id": customer_id, "amount": 440.0, "status": "paid",
    }).json()["data"]
    applied = client.post(f"/api/v1/payments/{payment['id']}/apply", headers=finance["key"],
                          json={"lines": [{"applied_to_type": "invoice",
                                           "applied_to_id": invoice["id"],
                                           "amount_applied": 440.0}],
                                "idempotency_key": "fullchain-1"})
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["targets"][0]["outstanding_amount"] == 0.0

    # --- the cashier lands the cash and links the line (钱账分离) ------
    blocked = client.post("/api/v1/fin-accounts", headers=finance["key"],
                          json={"name": "招行基本户"})
    assert blocked.status_code == 403, "the accountant never reaches the register"
    account = client.post("/api/v1/fin-accounts", headers=cashier["key"], json={
        "name": "招行基本户", "institution": "招商银行"}).json()["data"]
    line = client.post("/api/v1/fin-account-transactions", headers=cashier["key"], json={
        "fin_account_id": account["id"], "amount": 440.0,
        "counterparty": "泵业公司", "reference_no": "BANK-0001"}).json()["data"]
    linked = client.patch(f"/api/v1/fin-account-transactions/{line['id']}",
                          headers=cashier["key"], json={"payment_id": payment["id"]})
    assert linked.status_code == 200, linked.text
    balance = float(client.get(f"/api/v1/fin-accounts/{account['id']}",
                               headers=cashier["key"]).json()["data"]["current_balance"])
    assert balance == 440.0

    # --- the story reconciles ----------------------------------------
    final = client.get(f"/api/v1/leads/{lead['id']}", headers=sales["key"]).json()["data"]
    assert final["status"] == "converted"
    assert final["converted_customer_id"] == customer_id
