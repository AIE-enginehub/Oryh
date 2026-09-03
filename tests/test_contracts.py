"""Contracts: a file, and the clauses located inside it.

What is pinned: the counterparty is one side and the side is derived
(scope-checked on `contract.manage:purchase` / `:sales`, reads gated by
the same grant); originals of ANY format link into the attachment store
and carry the text an agent extracted, read back through the contract;
terms are the contract's own words tagged by a tenant-extensible type and
anchored to a file and page, so "付款节奏" is one lookup by type; signing
stamps signed_at and freezes the agreement's own fields while the desk's
notes stay writable; a supplement points at its parent; orders, invoices
and payments name the contract on their side (a crossed pointer is 422)
and the execution read derives what happened under it.
"""

from __future__ import annotations

import base64

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant

PDF = b"%PDF-1.4\n% signed contract\n"
PAYMENT_CLAUSE = "第五条 付款方式:合同签订后三个工作日内支付合同总价的30%作为预付款;首批货物发出前支付60%;验收合格后支付余款10%。"


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Deal Co", email="admin@deal.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def holder(name: str, permissions: list[str]) -> dict:
            client.post("/api/v1/roles", json={"name": name, "permissions": permissions},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@deal.example", "role": name},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            return {"X-API-Key": client.post(
                "/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                headers=admin).json()["data"]["plain_text_api_key"]}

        buyer = holder("buyer", ["contract.manage:purchase", "purchase_order.manage"])
        seller = holder("seller", ["contract.manage:sales"])
        nobody = holder("nobody", [])
        factory = client.post("/api/v1/vendors", json={"name": "东莞代工厂"},
                              headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "市一医院"},
                               headers=admin).json()["data"]["id"]
        valve = client.post("/api/v1/products", json={"name": "工业阀门"},
                            headers=admin).json()["data"]["id"]

        def contract(**extra) -> dict:
            r = client.post("/api/v1/contracts", headers=buyer, json={
                "title": "阀门委托加工合同", "contract_type": "oem", "vendor_id": factory,
                "total_amount": 100000, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "buyer": buyer, "seller": seller,
               "nobody": nobody, "factory": factory, "customer": customer, "valve": valve,
               "contract": contract}


def test_one_counterparty_and_the_side_is_the_scope(desk) -> None:
    client, buyer, seller = desk["client"], desk["buyer"], desk["seller"]
    both = client.post("/api/v1/contracts", headers=buyer, json={
        "title": "两头都签", "contract_type": "oem",
        "vendor_id": desk["factory"], "customer_id": desk["customer"]})
    assert both.status_code == 422, "one counterparty"
    made = desk["contract"]()
    assert made["contract_no"].startswith("CT-") and made["side"] == "purchase"
    assert made["counterparty_name"] == "东莞代工厂"

    crossed = client.post("/api/v1/contracts", headers=buyer, json={
        "title": "卖给医院", "contract_type": "sales", "customer_id": desk["customer"]})
    assert crossed.status_code == 403, "a buyer's scope does not file sales contracts"
    peeked = client.get(f"/api/v1/contracts/{made['id']}", headers=seller)
    assert peeked.status_code == 403, "nor does the seller read purchase contracts"
    blind = client.get("/api/v1/contracts", headers=desk["nobody"])
    assert blind.status_code == 403, "reads are the filing desk's"
    own = client.get("/api/v1/contracts", headers=buyer).json()["data"]
    assert [r["id"] for r in own] == [made["id"]]


def test_originals_of_any_format_with_their_text_and_a_located_clause(desk) -> None:
    client, buyer = desk["client"], desk["buyer"]
    made = desk["contract"]()
    scan = client.post("/api/v1/attachments", headers=buyer, json={
        "filename": "signed.pdf", "content_type": "application/pdf",
        "content_base64": base64.b64encode(PDF).decode()})
    assert scan.status_code == 201, "the contract desk uploads originals"
    doc = client.post("/api/v1/contract-documents", headers=buyer, json={
        "contract_id": made["id"], "attachment_id": scan.json()["data"]["id"],
        "document_type": "signed", "page_no": 1,
        "extracted_text": "……" + PAYMENT_CLAUSE + "……第六条 交货……"})
    assert doc.status_code == 201, doc.text
    document = doc.json()["data"]
    assert document["has_text"] and document["content_type"] == "application/pdf"

    read = client.get(f"/api/v1/contracts/{made['id']}/attachments/"
                      f"{scan.json()['data']['id']}/content", headers=buyer)
    assert read.status_code == 200 and read.content == PDF
    stranger = client.get(f"/api/v1/contracts/{made['id']}/attachments/"
                          f"{scan.json()['data']['id']}/content", headers=desk["seller"])
    assert stranger.status_code == 403

    bent = client.post("/api/v1/contract-terms", headers=buyer, json={
        "contract_id": made["id"], "term_type": "vibes", "content": "x"})
    assert bent.status_code == 422, "the term type is the vocabulary"
    term = client.post("/api/v1/contract-terms", headers=buyer, json={
        "contract_id": made["id"], "term_type": "payment_terms", "clause_ref": "5",
        "content": PAYMENT_CLAUSE, "summary": "首付30%,发货前60%,验收后10%",
        "document_id": document["id"], "page_no": 1})
    assert term.status_code == 201, term.text

    # THE question, answered by one lookup: the words, the reading, the page
    asked = client.get("/api/v1/contract-terms", headers=buyer,
                       params={"contract_id": made["id"], "term_type": "payment_terms"})
    rows = asked.json()["data"]
    assert len(rows) == 1 and rows[0]["content"] == PAYMENT_CLAUSE
    assert rows[0]["summary"].startswith("首付30%") and rows[0]["page_no"] == 1
    grouped = client.get(f"/api/v1/contracts/{made['id']}", headers=buyer).json()["data"]
    assert list(grouped["terms_by_type"]) == ["payment_terms"]
    assert grouped["documents"][0]["has_text"] and "extracted_text" not in grouped["documents"][0]
    found = client.get("/api/v1/contract-documents", headers=buyer,
                       params={"contract_id": made["id"], "keyword": "预付款"}).json()["data"]
    assert [d["id"] for d in found] == [document["id"]] and "预付款" in found[0]["extracted_text"], \
        "the full text is searchable when the terms are silent"


def test_signing_stamps_and_freezes_the_agreement_but_not_the_notes(desk) -> None:
    client, buyer = desk["client"], desk["buyer"]
    made = desk["contract"](items=[{"product_id": desk["valve"], "quantity": 1000,
                                    "unit_price": 100}])
    signed = client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer,
                          json={"status": "signed"})
    assert signed.status_code == 200 and signed.json()["data"]["signed_at"] is not None
    frozen = client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer,
                          json={"total_amount": 90000})
    assert frozen.status_code == 409, "a signed agreement's own fields are history"
    noted = client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer,
                         json={"summary": "代工阀门1000件,分三批交付", "remarks": "已归档"})
    assert noted.status_code == 200, "the desk's notes stay writable"
    line = client.post("/api/v1/contract-items", headers=buyer, json={
        "contract_id": made["id"], "description": "追加一行"})
    assert line.status_code == 409, "lines are part of the agreement"

    supplement = desk["contract"](title="补充协议一", parent_contract_id=made["id"])
    assert supplement["parent_contract_id"] == made["id"]
    selfish = client.patch(f"/api/v1/contracts/{supplement['id']}", headers=buyer,
                           json={"parent_contract_id": supplement["id"]})
    assert selfish.status_code == 422


def test_orders_invoices_and_payments_execute_the_contract_on_its_side(desk) -> None:
    client, admin, buyer = desk["client"], desk["admin"], desk["buyer"]
    made = desk["contract"](items=[{"product_id": desk["valve"], "quantity": 1000,
                                    "unit_price": 100}])
    emp = client.post("/api/v1/employees", json={"name": "采购"},
                      headers=admin).json()["data"]["id"]
    crossed = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "卖单", "contract_id": made["id"]})
    assert crossed.status_code == 422, "a sales order cannot execute a purchase contract"

    po = client.post("/api/v1/purchase-orders", headers=buyer, json={
        "employee_id": emp,
        "vendor_id": desk["factory"], "title": "第一批", "contract_id": made["id"],
        "total_amount": 40000,
        "items": [{"product_id": desk["valve"], "quantity": 400, "unit_price": 100}]})
    assert po.status_code == 201, po.text
    invoice = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "purchase", "employee_id": emp, "vendor_id": desk["factory"], "title": "首批发票",
        "total_amount": 40000, "contract_id": made["id"]})
    assert invoice.status_code == 201, invoice.text
    payroll = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "payroll", "employee_id": emp, "title": "工资条", "total_amount": 1,
        "contract_id": made["id"]})
    assert payroll.status_code == 422, "a payroll invoice executes no contract"
    deposit = client.post("/api/v1/payments", headers=admin, json={
        "direction": "outbound", "employee_id": emp, "vendor_id": desk["factory"], "amount": 30000,
        "status": "paid", "contract_id": made["id"], "remarks": "预付款30%"})
    assert deposit.status_code == 201, deposit.text

    execution = client.get(f"/api/v1/contracts/{made['id']}/execution", headers=buyer)
    assert execution.status_code == 200, execution.text
    data = execution.json()["data"]
    assert (data["orders"], data["ordered_amount"]) == (1, 40000.0)
    assert (data["invoices"], data["invoiced_amount"]) == (1, 40000.0)
    assert (data["payments"], data["paid_amount"]) == (1, 30000.0)
    assert data["lines"] == [{"product_id": desk["valve"], "product_name": "工业阀门",
                              "contracted_quantity": 1000.0, "ordered_quantity": 400.0}], \
        "contracted vs ordered, by product, derived"
