"""A line's amount is quantity × unit_price — the server's arithmetic, never
the person's (`derive_line_amount` in app/core/line_math.py).

Before: `amount` was an optional override. Left empty, a priced line read as
`null` and every total re-derived it; typed by hand, it could disagree with
the price and nothing said so. Now a priced line is stored at
quantity × price, a stated amount must agree, a gift is 0, and only an
unpriced line keeps a lump sum. Every family that carries the three columns
follows the rule, on create, on PATCH, on `/save`, on bulk import.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Amount Co", email="admin@amount.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        vendor = client.post("/api/v1/vendors", json={"name": "卖家"}, headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP"}, headers=admin).json()["data"]["id"]
        yield {"client": client, "admin": admin, "employee": emp, "customer": customer, "vendor": vendor, "product": product}


DOCUMENTS = [
    ("/sales-orders", "/sales-order-items", {"customer_id": True}),
    ("/sales-quotations", "/sales-quotation-items", {"customer_id": True}),
    ("/purchase-orders", "/purchase-order-items", {"vendor_id": True}),
    ("/purchase-requests", "/purchase-request-items", {"vendor_id": False}),
]


def _header(desk, path, party):
    body = {"employee_id": desk["employee"], "title": "t"}
    if party.get("customer_id"):
        body["customer_id"] = desk["customer"]
    if party.get("vendor_id"):
        body["vendor_id"] = desk["vendor"]
    return body


@pytest.mark.parametrize("path,lines,party", DOCUMENTS)
def test_a_priced_line_is_stored_at_quantity_times_price(desk, path, lines, party) -> None:
    c, admin = desk["client"], desk["admin"]
    doc = c.post(f"/api/v1{path}", headers=admin, json={**_header(desk, path, party), "items": [
        {"product_id": desk["product"], "quantity": 3, "unit_price": 12.5},          # computed
        {"product_id": desk["product"], "quantity": 2, "unit_price": 10, "amount": 20},  # stated, agrees
        {"product_id": desk["product"], "quantity": 4},                              # unpriced
    ]})
    assert doc.status_code == 201, doc.text
    items = doc.json()["data"]["items"]
    assert [i["amount"] for i in items] == [37.5, 20, None], path
    wrong = c.post(f"/api/v1{path}", headers=admin, json={**_header(desk, path, party), "items": [
        {"product_id": desk["product"], "quantity": 100, "unit_price": 10, "amount": 900}]})
    assert wrong.status_code == 422 and "100 × 10 = 1000" in wrong.json()["detail"], path

    line = items[0]["id"]
    changed = c.patch(f"/api/v1{lines}/{line}", headers=admin, json={"quantity": 5})
    assert changed.status_code == 200 and changed.json()["data"]["amount"] == 62.5, "PATCHing the quantity recomputes"
    repriced = c.patch(f"/api/v1{lines}/{line}", headers=admin, json={"unit_price": 8})
    assert repriced.json()["data"]["amount"] == 40
    disagree = c.patch(f"/api/v1{lines}/{line}", headers=admin, json={"amount": 41})
    assert disagree.status_code == 422
    detail = c.get(f"/api/v1{path}/{doc.json()['data']['id']}/detail", headers=admin).json()["data"]
    body = {"expected_revision": detail["revision"], "items": [{"id": line, "quantity": 2}]}
    saved = c.post(f"/api/v1{path}/{doc.json()['data']['id']}/save", headers=admin, json=body)
    assert saved.status_code == 200 and saved.json()["data"]["items"][0]["amount"] == 16, "and so does /save"


def test_a_gift_line_is_zero_and_the_lump_sum_survives_without_a_price(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    doc = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "t", "items": [
            {"product_id": desk["product"], "quantity": 1, "unit_price": 99, "is_gift": True},
            {"product_name_snapshot": "安装服务", "quantity": 1, "amount": 500}]}).json()["data"]
    gift, service = doc["items"]
    assert gift["amount"] == 0 and service["amount"] == 500
    ungifted = c.patch(f"/api/v1/sales-order-items/{gift['id']}", headers=admin, json={"is_gift": False})
    assert ungifted.json()["data"]["amount"] == 99, "no longer a gift: back to price × quantity"


def test_invoice_lines_compute_amount_and_leave_tax_as_stated(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    inv = c.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "inv", "items": [
            {"product_id": desk["product"], "quantity": 10, "unit_price": 100, "tax_rate": 13},
            # 含税价: the tax is what the invoice says, not amount × rate
            {"product_id": desk["product"], "quantity": 1, "unit_price": 113, "tax_rate": 13, "tax_amount": 13},
        ]})
    assert inv.status_code == 201, inv.text
    a, b = inv.json()["data"]["items"]
    assert (a["amount"], a["tax_amount"]) == (1000, None) and (b["amount"], b["tax_amount"]) == (113, 13)
    changed = c.patch(f"/api/v1/invoice-items/{a['id']}", headers=admin, json={"quantity": 2})
    assert changed.json()["data"]["amount"] == 200
    assert c.patch(f"/api/v1/invoice-items/{a['id']}", headers=admin, json={"amount": 199}).status_code == 422


def test_deal_lines_follow_the_same_rule(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    deal = c.post("/api/v1/opportunities", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "deal"}).json()["data"]["id"]
    line = c.post("/api/v1/opportunity-items", headers=admin, json={
        "opportunity_id": deal, "product_id": desk["product"], "quantity": 3, "unit_price": 7}).json()["data"]
    assert line["amount"] == 21
    assert c.post("/api/v1/opportunity-items", headers=admin, json={
        "opportunity_id": deal, "product_id": desk["product"], "quantity": 3, "unit_price": 7, "amount": 22}).status_code == 422
    assert c.patch(f"/api/v1/opportunity-items/{line['id']}", headers=admin, json={"quantity": 4}).json()["data"]["amount"] == 28


def test_bulk_import_computes_too(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    r = c.post("/api/v1/sales-orders/bulk", headers=admin, json={"rows": [{
        "order_no": "BULK-1", "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "bulk",
        "items": [{"product_code": "CUP", "quantity": 6, "unit_price": 2.5}]}]})
    assert r.status_code in (200, 201), r.text
    orders = c.get("/api/v1/sales-orders", headers=admin, params={"keyword": "bulk"}).json()["data"]
    lines = c.get("/api/v1/sales-order-items", headers=admin, params={"order_id": orders[0]["id"]}).json()["data"]
    assert [i["amount"] for i in lines] == [15]
    wrong = c.post("/api/v1/sales-orders/bulk", headers=admin, json={"rows": [{
        "order_no": "BULK-2", "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "bulk2",
        "items": [{"product_code": "CUP", "quantity": 6, "unit_price": 2.5, "amount": 99}]}]})
    assert wrong.status_code == 200, wrong.text
    rows = wrong.json()["data"]["results"]
    assert rows[0]["outcome"] == "error" and "6 × 2.5 = 15" in rows[0]["error"], "a bad line is that row's error, not the batch's"
