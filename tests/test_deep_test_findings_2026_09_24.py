"""The 2026-09-24 deep-test report: seven ways a permitted call could make the
ledger and its source disagree, one test each, plus the standalone gateway.

Every one of them was a write that happened AFTER a side effect — a
settlement, a stock posting — and rewrote what the side effect had measured.
The regressions here pin the invariants the report named: applied money
fixes the document it was applied against; a posted shipment is the
ledger's source; a unit of stock is allocated once; a hold names a real
line; money is kept to the cent; a register keeps one currency. Two
decisions were taken with them: a draft is never settled, and a
cross-currency register link is refused rather than modelled.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import create, make_client, provision_tenant

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Ledger Co", email="admin@ledger.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = create(client, admin, "employees", name="Clerk")["id"]
        customer_a = create(client, admin, "customers", name="Customer A")["id"]
        customer_b = create(client, admin, "customers", name="Customer B")["id"]
        product = create(client, admin, "products", name="Ribbon", product_code="RB-1")["id"]

        def invoice(customer: str, amount: float = 100.0, submit: bool = True, **fields) -> dict:
            row = create(client, admin, "invoices", direction="sales", employee_id=emp, customer_id=customer,
                         title="发票", items=[{"product_name_snapshot": "Ribbon", "quantity": 1, "unit_price": amount}],
                         **fields)
            if submit:
                r = client.post(f"/api/v1/invoices/{row['id']}/submit", headers=admin)
                assert r.status_code == 200, r.text
                row = r.json()["data"]
            return row

        def payment(customer: str, amount: float = 100.0, **fields) -> dict:
            fields.setdefault("status", "paid")
            return create(client, admin, "payments", direction="inbound", employee_id=emp, customer_id=customer,
                          amount=amount, **fields)

        def apply(payment_id: str, target_type: str, target_id: str, amount: float):
            return client.post(f"/api/v1/payments/{payment_id}/apply", headers=admin, json={
                "lines": [{"applied_to_type": target_type, "applied_to_id": target_id, "amount_applied": amount}]})

        def order(items: list[dict], confirm: bool = True) -> dict:
            row = create(client, admin, "sales-orders", employee_id=emp, customer_id=customer_a, title="订单", items=items)
            if confirm:
                assert client.post(f"/api/v1/sales-orders/{row['id']}/submit", headers=admin).status_code == 200
                r = client.patch(f"/api/v1/sales-orders/{row['id']}", headers=admin, json={"status": "confirmed"})
                assert r.status_code == 200, r.text
                row = r.json()["data"]
            return row

        yield {"client": client, "admin": admin, "emp": emp, "customer_a": customer_a, "customer_b": customer_b,
               "product": product, "invoice": invoice, "payment": payment, "apply": apply, "order": order}


# --- F1 / F2 -----------------------------------------------------------------------------

def test_f1_a_settled_invoice_keeps_its_money(office) -> None:
    c, admin = office["client"], office["admin"]
    inv = office["invoice"](office["customer_a"])
    pay = office["payment"](office["customer_a"])
    assert office["apply"](pay["id"], "invoice", inv["id"], 100).status_code == 200
    changes = ({"total_amount": 1}, {"currency": "USD"}, {"customer_id": office["customer_b"]})
    for change in changes:
        assert c.patch(f"/api/v1/invoices/{inv['id']}", headers=admin, json=change).status_code == 409, change
    # returned to its author it is editable again by state — and still settled
    assert c.patch(f"/api/v1/invoices/{inv['id']}", headers=admin, json={"status": "returned"}).status_code == 200
    for change in changes:
        r = c.patch(f"/api/v1/invoices/{inv['id']}", headers=admin, json=change)
        assert r.status_code == 409, (change, r.text)
        assert "applied" in r.json()["detail"], r.text
    detail = c.get(f"/api/v1/invoices/{inv['id']}/detail", headers=admin).json()["data"]
    assert detail["applied_amount"] == 100 and detail["outstanding_amount"] == 0
    # a note is not money
    assert c.patch(f"/api/v1/invoices/{inv['id']}", headers=admin, json={"remarks": "对账完成"}).status_code == 200


def test_f2_a_settled_payment_keeps_its_party_until_reversed(office) -> None:
    c, admin = office["client"], office["admin"]
    inv = office["invoice"](office["customer_a"])
    pay = office["payment"](office["customer_a"])
    assert office["apply"](pay["id"], "invoice", inv["id"], 100).status_code == 200
    swapped = c.patch(f"/api/v1/payments/{pay['id']}", headers=admin, json={"customer_id": office["customer_b"]})
    assert swapped.status_code == 409, swapped.text
    assert c.patch(f"/api/v1/payments/{pay['id']}", headers=admin, json={"amount": 500}).status_code == 409
    # the reversal still fits, because the party did not move
    assert office["apply"](pay["id"], "invoice", inv["id"], -100).status_code == 200
    corrected = c.patch(f"/api/v1/payments/{pay['id']}", headers=admin, json={"customer_id": office["customer_b"]})
    assert corrected.status_code == 200, "with nothing applied, a party may be corrected"


def test_a_draft_is_never_settled(office) -> None:
    draft = office["invoice"](office["customer_a"], submit=False)
    assert draft["status"] == "draft"
    pay = office["payment"](office["customer_a"])
    refused = office["apply"](pay["id"], "invoice", draft["id"], 100)
    assert refused.status_code == 409 and "submitted" in refused.json()["detail"], refused.text
    submitted = office["invoice"](office["customer_a"])
    unpaid = office["payment"](office["customer_a"], status="draft")
    assert unpaid["status"] == "draft"
    refused = office["apply"](unpaid["id"], "invoice", submitted["id"], 100)
    assert refused.status_code == 409 and "editable" in refused.json()["detail"], refused.text
    assert office["apply"](pay["id"], "invoice", submitted["id"], 100).status_code == 200


# --- F4 ------------------------------------------------------------------------------------

def test_f4_settlement_is_kept_to_the_cent(office) -> None:
    inv = office["invoice"](office["customer_a"])
    pay = office["payment"](office["customer_a"])
    r = office["apply"](pay["id"], "invoice", inv["id"], 0.016)
    assert r.status_code == 422, r.text
    assert "two decimals" in r.text
    assert office["apply"](pay["id"], "invoice", inv["id"], 0.02).status_code == 200
    assert office["apply"](pay["id"], "invoice", inv["id"], 99.98).status_code == 200


# --- F3 / F6 / F7 ---------------------------------------------------------------------------

def _position(office, quantity: int = 10, sku_id: str | None = None) -> str:
    fields = {"product_id": office["product"], "facility": "TA", "initial_quantity": quantity}
    if sku_id:
        fields["sku_id"] = sku_id
    return create(office["client"], office["admin"], "inventory-items", **fields)["id"]


def _shipment(office, order_id: str, position: str, quantity: int, sku_id: str | None = None) -> dict:
    line = {"product_id": office["product"], "quantity": quantity, "inventory_item_id": position}
    if sku_id:
        line["sku_id"] = sku_id
    row = create(office["client"], office["admin"], "shipments", direction="outbound", sales_order_id=order_id,
                 facility="TA", items=[line])
    posted = office["client"].post(f"/api/v1/shipments/{row['id']}/post-stock", headers=office["admin"])
    assert posted.status_code == 200, posted.text
    return row


def test_f3_a_posted_shipment_is_the_ledgers_source(office) -> None:
    c, admin = office["client"], office["admin"]
    position = _position(office)
    order_a = office["order"]([{"product_id": office["product"], "quantity": 3, "unit_price": 10}])
    order_b = office["order"]([{"product_id": office["product"], "quantity": 3, "unit_price": 10}])
    shipment = _shipment(office, order_a["id"], position, 3)
    line = c.get(f"/api/v1/shipment-items?shipment_id={shipment['id']}", headers=admin).json()["data"][0]
    assert c.patch(f"/api/v1/shipment-items/{line['id']}", headers=admin, json={"quantity": 8}).status_code == 409
    assert c.delete(f"/api/v1/shipment-items/{line['id']}", headers=admin).status_code == 409
    assert c.post("/api/v1/shipment-items", headers=admin, json={
        "shipment_id": shipment["id"], "product_id": office["product"], "quantity": 1}).status_code == 409
    moved = c.patch(f"/api/v1/shipments/{shipment['id']}", headers=admin, json={"sales_order_id": order_b["id"]})
    assert moved.status_code == 409 and "posted stock" in moved.json()["detail"], moved.text
    assert c.patch(f"/api/v1/shipments/{shipment['id']}", headers=admin, json={"tracking_no": "SF-1"}).status_code == 200
    kept = c.get(f"/api/v1/shipments/{shipment['id']}", headers=admin).json()["data"]
    assert kept["sales_order_id"] == order_a["id"]
    assert c.get(f"/api/v1/inventory-items/{position}", headers=admin).json()["data"]["quantity_on_hand"] == 7


def test_f6_a_shipped_unit_is_allocated_once(office) -> None:
    c, admin = office["client"], office["admin"]
    sku = create(c, admin, "product-skus", product_id=office["product"], sku_code="RB-1-X")["id"]
    order = office["order"]([
        {"product_id": office["product"], "quantity": 3, "unit_price": 10},
        {"product_id": office["product"], "sku_id": sku, "quantity": 3, "unit_price": 10},
    ])
    _shipment(office, order["id"], _position(office), 3)
    detail = c.get(f"/api/v1/sales-orders/{order['id']}/detail", headers=admin).json()["data"]
    shipped = {(row["sku_id"] is not None): row["shipped"] for row in detail["fulfilment"]}
    assert shipped == {False: 3, True: 0}, detail["fulfilment"]
    assert sum(row["shipped"] for row in detail["fulfilment"]) == 3, "three units left, three are reported"


def test_f7_a_hold_names_a_real_line_of_this_order(office) -> None:
    c, admin = office["client"], office["admin"]
    position = _position(office)
    order = office["order"]([{"product_id": office["product"], "quantity": 2, "unit_price": 10}])
    other = office["order"]([{"product_id": office["product"], "quantity": 2, "unit_price": 10}])
    line = c.get(f"/api/v1/sales-order-items?order_id={order['id']}", headers=admin).json()["data"][0]["id"]
    foreign = c.get(f"/api/v1/sales-order-items?order_id={other['id']}", headers=admin).json()["data"][0]["id"]

    def reserve(order_item_id: str):
        return c.post(f"/api/v1/sales-orders/{order['id']}/reserve", headers=admin, json={
            "lines": [{"inventory_item_id": position, "quantity": 1, "order_item_id": order_item_id}]})

    for bogus in ("11111111-1111-4111-8111-111111111111", foreign, "not-an-id"):
        r = reserve(bogus)
        assert r.status_code == 422, (bogus, r.text)
    assert c.get(f"/api/v1/inventory-items/{position}", headers=admin).json()["data"]["available_to_promise"] == 10, \
        "a refused hold changed nothing"
    assert reserve(line).status_code == 200
    assert c.get(f"/api/v1/inventory-items/{position}", headers=admin).json()["data"]["available_to_promise"] == 9


# --- F5 -------------------------------------------------------------------------------------

def test_f5_a_register_keeps_one_currency(office) -> None:
    c, admin = office["client"], office["admin"]
    account = create(c, admin, "fin-accounts", name="基本户", currency="CNY", opening_balance=100.0,
                     opening_date="2026-09-01")
    usd = office["payment"](office["customer_a"], amount=10, currency="USD")
    cny = office["payment"](office["customer_a"], amount=10)
    crossed = c.post("/api/v1/fin-account-transactions", headers=admin, json={
        "fin_account_id": account["id"], "amount": 10, "payment_id": usd["id"]})
    assert crossed.status_code == 422 and "USD" in crossed.json()["detail"], crossed.text
    assert c.post("/api/v1/fin-account-transactions", headers=admin, json={
        "fin_account_id": account["id"], "amount": 10, "payment_id": cny["id"]}).status_code == 201
    restated = c.patch(f"/api/v1/fin-accounts/{account['id']}", headers=admin, json={"currency": "EUR"})
    assert restated.status_code == 409, restated.text
    assert c.get(f"/api/v1/fin-accounts/{account['id']}", headers=admin).json()["data"]["currency"] == "CNY"
    empty = create(c, admin, "fin-accounts", name="新户")
    assert c.patch(f"/api/v1/fin-accounts/{empty['id']}", headers=admin, json={"currency": "EUR"}).status_code == 200, \
        "an account with no money and no lines may still choose its currency"


# --- S1 -------------------------------------------------------------------------------------

def test_s1_the_standalone_gateway_forwards_oauth_and_mcp() -> None:
    """The hosted gateway forwards /oauth, /mcp and the two well-known paths;
    the standalone one did not, so an open-core install had no MCP or OAuth
    through its own front door."""
    # the open-core export renames nginx.standalone.conf to nginx.conf and ships that one alone
    for conf in [c for c in ("nginx/nginx.conf", "nginx/nginx.standalone.conf") if (ROOT / c).exists()]:
        text = (ROOT / conf).read_text()
        forwarded = re.search(r"location ~ \^/\(\?:([^)]*)\)\(\?:/\|\$\) \{", text)
        assert forwarded, conf
        alternatives = forwarded.group(1)
        for path in ("oauth", "mcp", r"\.well-known/oauth-authorization-server", r"\.well-known/oauth-protected-resource"):
            assert path in alternatives, f"{conf} does not forward {path}"
