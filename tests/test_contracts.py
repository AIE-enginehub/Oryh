"""Contracts: a file, and the clauses located inside it.

What is pinned: the counterparty is one side and the side follows from it
(scope-checked on `contract.manage:purchase` / `:sales`, reads gated by
the same grant); originals of ANY format link into the attachment store
and carry the text an agent extracted, read back through the contract;
terms are the contract's own words tagged by a tenant-extensible type and
anchored to a file and page, so "payment schedule" is one lookup by type; signing
stamps signed_at and freezes the agreement's own fields while the desk's
notes stay writable; a supplement points at its parent; orders, invoices
and payments name the contract on their side (a crossed pointer is 422)
and the execution read derives what happened under it — only what did
happen, per currency.

A contract filed with only a counterparty's name states its side, and the
vendor or customer is linked later without re-filing it (review
2026-10-24, findings 1 and 2).
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_contracts.json').read_text(encoding="utf-8"))


import base64

import pytest


from conftest import invite_member, make_client, provision_tenant

PDF = b"%PDF-1.4\n% signed contract\n"
PAYMENT_CLAUSE = _ZH_TEXT['TEXT_4FE8F0C83458D8DD']


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Deal Co", email="admin@deal.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def holder(name: str, permissions: list[str]) -> dict:
            return dict(invite_member(client, admin, name, permissions))

        buyer = holder("buyer", ["contract.manage:purchase", "purchase_order.manage"])
        seller = holder("seller", ["contract.manage:sales"])
        nobody = holder("nobody", [])
        factory = client.post("/api/v1/vendors", json={"name": _ZH_TEXT['TEXT_7774DE82E2DD089E']},
                              headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_85DED9E803B8D55E']},
                               headers=admin).json()["data"]["id"]
        valve = client.post("/api/v1/products", json={"name": _ZH_TEXT['TEXT_31B509285FE3285B']},
                            headers=admin).json()["data"]["id"]

        def contract(**extra) -> dict:
            r = client.post("/api/v1/contracts", headers=buyer, json={
                "title": _ZH_TEXT['TEXT_C46CFE24BD5D8BCD'], "contract_type": "oem", "vendor_id": factory,
                "total_amount": 100000, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "buyer": buyer, "seller": seller,
               "nobody": nobody, "factory": factory, "customer": customer, "valve": valve,
               "contract": contract}


def test_one_counterparty_and_the_side_is_the_scope(desk) -> None:
    client, buyer, seller = desk["client"], desk["buyer"], desk["seller"]
    both = client.post("/api/v1/contracts", headers=buyer, json={
        "title": _ZH_TEXT['TEXT_C1B1DDEED6F1401E'], "contract_type": "oem",
        "vendor_id": desk["factory"], "customer_id": desk["customer"]})
    assert both.status_code == 422, "one counterparty"
    made = desk["contract"]()
    assert made["contract_no"].startswith("CT-") and made["side"] == "purchase"
    assert made["counterparty_name"] == _ZH_TEXT['TEXT_7774DE82E2DD089E']

    crossed = client.post("/api/v1/contracts", headers=buyer, json={
        "title": _ZH_TEXT['TEXT_8CC974544F87D34D'], "contract_type": "sales", "customer_id": desk["customer"]})
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
        "extracted_text": "……" + PAYMENT_CLAUSE + _ZH_TEXT['TEXT_C578992CB944778D']})
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
        "content": PAYMENT_CLAUSE, "summary": _ZH_TEXT['TEXT_8397FC9E046ECAEB'],
        "document_id": document["id"], "page_no": 1})
    assert term.status_code == 201, term.text

    # THE question, answered by one lookup: the words, the reading, the page
    asked = client.get("/api/v1/contract-terms", headers=buyer,
                       params={"contract_id": made["id"], "term_type": "payment_terms"})
    rows = asked.json()["data"]
    assert len(rows) == 1 and rows[0]["content"] == PAYMENT_CLAUSE
    assert rows[0]["summary"].startswith(_ZH_TEXT['TEXT_025BCB13E220841D']) and rows[0]["page_no"] == 1
    grouped = client.get(f"/api/v1/contracts/{made['id']}", headers=buyer).json()["data"]
    assert list(grouped["terms_by_type"]) == ["payment_terms"]
    assert grouped["documents"][0]["has_text"] and "extracted_text" not in grouped["documents"][0]
    found = client.get("/api/v1/contract-documents", headers=buyer,
                       params={"contract_id": made["id"], "keyword": _ZH_TEXT['TEXT_3D02E802F717C533']}).json()["data"]
    assert [d["id"] for d in found] == [document["id"]] and _ZH_TEXT['TEXT_3D02E802F717C533'] in found[0]["extracted_text"], \
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
                         json={"summary": _ZH_TEXT['TEXT_25AD5337E25A89B9'], "remarks": _ZH_TEXT['TEXT_82395D423099A07A']})
    assert noted.status_code == 200, "the desk's notes stay writable"
    line = client.post("/api/v1/contract-items", headers=buyer, json={
        "contract_id": made["id"], "description": _ZH_TEXT['TEXT_2601F0D9696E3362']})
    assert line.status_code == 409, "lines are part of the agreement"

    supplement = desk["contract"](title=_ZH_TEXT['TEXT_CAD27FEE52812E55'], parent_contract_id=made["id"])
    assert supplement["parent_contract_id"] == made["id"]
    selfish = client.patch(f"/api/v1/contracts/{supplement['id']}", headers=buyer,
                           json={"parent_contract_id": supplement["id"]})
    assert selfish.status_code == 422


def test_orders_invoices_and_payments_execute_the_contract_on_its_side(desk) -> None:
    client, admin, buyer = desk["client"], desk["admin"], desk["buyer"]
    made = desk["contract"](items=[{"product_id": desk["valve"], "quantity": 1000,
                                    "unit_price": 100}])
    emp = client.post("/api/v1/employees", json={"name": _ZH_TEXT['TEXT_6E098153A5860B46']},
                      headers=admin).json()["data"]["id"]
    crossed = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": _ZH_TEXT['TEXT_BA2E6455CF830BC0'], "contract_id": made["id"]})
    assert crossed.status_code == 422, "a sales order cannot execute a purchase contract"

    po = client.post("/api/v1/purchase-orders", headers=buyer, json={
        "employee_id": emp,
        "vendor_id": desk["factory"], "title": _ZH_TEXT['TEXT_1DD14751E44CD530'], "contract_id": made["id"],
        "total_amount": 40000, "status": "confirmed",
        "items": [{"product_id": desk["valve"], "quantity": 400, "unit_price": 100}]})
    assert po.status_code == 201, po.text
    invoice = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "purchase", "employee_id": emp, "vendor_id": desk["factory"], "title": _ZH_TEXT['TEXT_66AEE2F21B8F7A1C'],
        "total_amount": 40000, "contract_id": made["id"], "status": "issued"})
    assert invoice.status_code == 201, invoice.text
    payroll = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "payroll", "employee_id": emp, "title": _ZH_TEXT['TEXT_0480B1210B0C2344'], "total_amount": 1,
        "contract_id": made["id"]})
    assert payroll.status_code == 422, "a payroll invoice executes no contract"
    deposit = client.post("/api/v1/payments", headers=admin, json={
        "direction": "outbound", "employee_id": emp, "vendor_id": desk["factory"], "amount": 30000,
        "status": "paid", "contract_id": made["id"], "remarks": _ZH_TEXT['TEXT_6E2277A69007E1D4']})
    assert deposit.status_code == 201, deposit.text

    execution = client.get(f"/api/v1/contracts/{made['id']}/execution", headers=buyer)
    assert execution.status_code == 200, execution.text
    data = execution.json()["data"]
    assert (data["orders"], data["ordered_amount"]) == (1, 40000.0)
    assert (data["invoices"], data["invoiced_amount"]) == (1, 40000.0)
    assert (data["payments"], data["paid_amount"]) == (1, 30000.0)
    assert data["lines"] == [{"product_id": desk["valve"], "product_name": _ZH_TEXT['TEXT_31B509285FE3285B'],
                              "contracted_quantity": 1000.0, "ordered_quantity": 400.0}], \
        "contracted vs ordered, by product, derived"


def test_a_factory_not_yet_in_master_data_is_still_a_purchase(desk) -> None:
    client, admin, buyer, seller = desk["client"], desk["admin"], desk["buyer"], desk["seller"]
    snapshot = {"title": "New factory trial-run contract", "contract_type": "oem", "counterparty_name_snapshot": "New Factory (not yet in master data)"}
    unstated = client.post("/api/v1/contracts", headers=buyer, json=snapshot)
    assert unstated.status_code == 422 and "states its side" in unstated.text, \
        "with no vendor and no customer the side is not guessed"
    crossed = client.post("/api/v1/contracts", headers=buyer, json={**snapshot, "side": "sales", "vendor_id": desk["factory"]})
    assert crossed.status_code == 422, "a vendor is the purchase side"
    made = client.post("/api/v1/contracts", headers=buyer, json={**snapshot, "side": "purchase"})
    assert made.status_code == 201, made.text
    contract = made.json()["data"]
    assert contract["side"] == "purchase" and contract["vendor_id"] is None
    assert client.get(f"/api/v1/contracts/{contract['id']}", headers=seller).status_code == 403, \
        "the sales desk does not read a purchase"
    assert client.post("/api/v1/contracts", headers=seller, json={**snapshot, "side": "purchase"}).status_code == 403

    # signed before the factory was entered — the vendor is linked later, not re-filed
    assert client.patch(f"/api/v1/contracts/{contract['id']}", headers=buyer, json={"status": "signed"}).status_code == 200
    wrong = client.patch(f"/api/v1/contracts/{contract['id']}", headers=buyer, json={"customer_id": desk["customer"]})
    assert wrong.status_code == 403, "a customer would move it to the sales desk, which this buyer is not"
    linked = client.patch(f"/api/v1/contracts/{contract['id']}", headers=buyer, json={"vendor_id": desk["factory"]})
    assert linked.status_code == 200, linked.text
    read = client.get(f"/api/v1/contracts/{contract['id']}", headers=buyer).json()["data"]
    assert read["vendor_id"] == desk["factory"] and read["side"] == "purchase"
    assert read["counterparty_name_snapshot"] == "New Factory (not yet in master data)", "what the paper said is kept"
    again = client.patch(f"/api/v1/contracts/{contract['id']}", headers=admin, json={"vendor_id": None, "side": "sales"})
    assert again.status_code == 409, "once linked, a contract for another party is another contract"


def test_a_snapshot_contract_filed_on_the_wrong_side_is_moved_by_a_desk_holding_both(desk) -> None:
    client, admin, seller = desk["client"], desk["admin"], desk["seller"]
    filed = client.post("/api/v1/contracts", headers=seller, json={
        "title": "OEM contract filed on the sales side by mistake", "counterparty_name_snapshot": "New Factory", "side": "sales"}).json()["data"]
    assert client.patch(f"/api/v1/contracts/{filed['id']}", headers=seller, json={"side": "purchase"}).status_code == 403, \
        "moving it hands it to the purchase desk; the sales desk alone may not"
    moved = client.patch(f"/api/v1/contracts/{filed['id']}", headers=admin, json={"side": "purchase"})
    assert moved.status_code == 200 and moved.json()["data"]["side"] == "purchase", moved.text

    emp = client.post("/api/v1/employees", json={"name": "Sales"}, headers=admin).json()["data"]["id"]
    other = client.post("/api/v1/contracts", headers=seller, json={
        "title": "Another one", "counterparty_name_snapshot": "Some customer", "side": "sales"}).json()["data"]
    order = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": _ZH_TEXT['TEXT_BA2E6455CF830BC0'], "contract_id": other["id"]})
    assert order.status_code == 201, order.text
    blocked = client.patch(f"/api/v1/contracts/{other['id']}", headers=admin, json={"side": "purchase"})
    assert blocked.status_code == 409 and "sales_orders" in blocked.text, \
        "a sales order already executes it; moving it would cross the pointer"


def test_execution_counts_only_what_happened_and_never_adds_currencies(desk) -> None:
    client, admin, buyer = desk["client"], desk["admin"], desk["buyer"]
    made = desk["contract"](items=[
        {"product_id": desk["valve"], "quantity": 600, "unit_price": 100},
        {"product_id": desk["valve"], "quantity": 400, "unit_price": 100, "description": "Second batch"}])
    emp = client.post("/api/v1/employees", json={"name": _ZH_TEXT['TEXT_6E098153A5860B46']}, headers=admin).json()["data"]["id"]

    def order(status: str, quantity: int) -> None:
        r = client.post("/api/v1/purchase-orders", headers=buyer, json={
            "employee_id": emp, "vendor_id": desk["factory"], "title": status, "contract_id": made["id"],
            "total_amount": quantity * 100, "status": status,
            "items": [{"product_id": desk["valve"], "quantity": quantity, "unit_price": 100}]})
        assert r.status_code == 201, r.text

    def invoice(status: str, amount: float, currency: str = "CNY") -> None:
        r = client.post("/api/v1/invoices", headers=admin, json={
            "direction": "purchase", "employee_id": emp, "vendor_id": desk["factory"], "title": status,
            "total_amount": amount, "currency": currency, "contract_id": made["id"], "status": status})
        assert r.status_code == 201, r.text

    def payment(status: str, amount: float) -> None:
        r = client.post("/api/v1/payments", headers=admin, json={
            "direction": "outbound", "employee_id": emp, "vendor_id": desk["factory"], "amount": amount,
            "status": status, "contract_id": made["id"]})
        assert r.status_code == 201, r.text

    order("confirmed", 300)
    order("received", 100)
    order("draft", 50)          # not yet ordered
    order("submitted", 50)      # still in approval
    order("cancelled", 200)     # never happened
    invoice("issued", 30000)
    invoice("paid", 10000.10)
    invoice("draft", 5000)
    invoice("cancelled", 5000)
    invoice("issued", 1000, "USD")
    payment("paid", 30000.05)
    payment("draft", 9999)
    payment("approved", 9999)   # approved, not yet moved
    payment("void", 9999)

    data = client.get(f"/api/v1/contracts/{made['id']}/execution", headers=buyer).json()["data"]
    assert data["currency"] == "CNY"
    assert (data["orders"], data["ordered_amount"]) == (2, 40000.0)
    assert (data["invoices"], data["invoiced_amount"]) == (2, 40000.1)
    assert (data["payments"], data["paid_amount"]) == (1, 30000.05), "a draft, approved or voided payment paid nothing"
    assert data["other_currencies"] == [{"currency": "USD", "orders": 0, "ordered_amount": 0.0, "invoices": 1,
                                         "invoiced_amount": 1000.0, "payments": 0, "paid_amount": 0.0}]
    assert data["lines"] == [{"product_id": desk["valve"], "product_name": _ZH_TEXT['TEXT_31B509285FE3285B'],
                              "contracted_quantity": 1000.0, "ordered_quantity": 400.0}], \
        "one row per product, from the orders that count"


def test_after_signing_the_quoted_words_and_the_originals_stay_as_signed(desk) -> None:
    client, buyer = desk["client"], desk["buyer"]
    made = desk["contract"]()

    def upload(name: str) -> str:
        return client.post("/api/v1/attachments", headers=buyer, json={
            "filename": name, "content_type": "application/pdf",
            "content_base64": base64.b64encode(PDF + name.encode()).decode()}).json()["data"]["id"]

    signed_doc = client.post("/api/v1/contract-documents", headers=buyer, json={
        "contract_id": made["id"], "attachment_id": upload("signed.pdf"), "document_type": "signed"}).json()["data"]
    draft_doc = client.post("/api/v1/contract-documents", headers=buyer, json={
        "contract_id": made["id"], "attachment_id": upload("draft.pdf"), "document_type": "draft"}).json()["data"]
    term = client.post("/api/v1/contract-terms", headers=buyer, json={
        "contract_id": made["id"], "term_type": "payment_terms", "content": PAYMENT_CLAUSE,
        "document_id": signed_doc["id"]}).json()["data"]
    assert client.patch(f"/api/v1/contract-terms/{term['id']}", headers=buyer,
                        json={"content": PAYMENT_CLAUSE + " "}).status_code == 200, "before signing the quote is a draft"
    assert client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer, json={"status": "signed"}).status_code == 200

    rewrite = client.patch(f"/api/v1/contract-terms/{term['id']}", headers=buyer, json={"content": "No deposit"})
    assert rewrite.status_code == 409 and "signed words" in rewrite.text
    reread = client.patch(f"/api/v1/contract-terms/{term['id']}", headers=buyer,
                          json={"summary": _ZH_TEXT['TEXT_025BCB13E220841D'], "clause_ref": "5", "page_no": 2})
    assert reread.status_code == 200, "the reading, the reference and the place stay writable"
    assert client.delete(f"/api/v1/contract-terms/{term['id']}", headers=buyer).status_code == 204, \
        "a wrong quote is removed and the right one filed — two acts in the trail"

    unlink = client.delete(f"/api/v1/contract-documents/{signed_doc['id']}", headers=buyer)
    assert unlink.status_code == 409 and "originals stay linked" in unlink.text
    assert client.delete(f"/api/v1/contract-documents/{draft_doc['id']}", headers=buyer).status_code == 204, \
        "a negotiation draft may still be unlinked"
    later = client.post("/api/v1/contract-documents", headers=buyer, json={
        "contract_id": made["id"], "attachment_id": upload("scan-2.pdf"), "document_type": "scan_page"})
    assert later.status_code == 201, "a scan filed after signing is still filed"


def test_a_deleted_contract_answers_no_list_and_no_search(desk) -> None:
    client, buyer = desk["client"], desk["buyer"]
    kept, gone = desk["contract"](title="Kept"), desk["contract"](title="Deleted",
        items=[{"description": "Confidential part", "quantity": 1}])
    for made in (kept, gone):
        client.post("/api/v1/contract-terms", headers=buyer, json={
            "contract_id": made["id"], "term_type": "payment_terms", "content": f"SECRET clause {made['title']}"})
    scan = client.post("/api/v1/attachments", headers=buyer, json={
        "filename": "x.pdf", "content_type": "application/pdf",
        "content_base64": base64.b64encode(PDF).decode()}).json()["data"]["id"]
    client.post("/api/v1/contract-documents", headers=buyer, json={
        "contract_id": gone["id"], "attachment_id": scan, "extracted_text": "SECRET full text"})
    party = client.post("/api/v1/document-parties", headers=desk["admin"], json={
        "entity_type": "contract", "entity_id": gone["id"], "customer_id": desk["customer"],
        "party_role": "referrer", "terms": {"commission_rate": "8%"}})
    assert party.status_code == 201, party.text
    assert client.delete(f"/api/v1/contracts/{gone['id']}", headers=buyer).status_code == 204

    terms = client.get("/api/v1/contract-terms", headers=buyer, params={"keyword": "SECRET"}).json()["data"]
    assert [t["contract_id"] for t in terms] == [kept["id"]]
    assert client.get("/api/v1/contract-items", headers=buyer).json()["data"] == []
    assert client.get("/api/v1/contract-documents", headers=buyer, params={"keyword": "SECRET"}).json()["data"] == []
    for who in (buyer, desk["admin"]):
        parties = client.get("/api/v1/document-parties", headers=who).json()["data"]
        assert gone["id"] not in {p["entity_id"] for p in parties}, "nor its parties, for either side"


def test_contract_dates_are_judged_on_the_merged_row(desk) -> None:
    client, buyer = desk["client"], desk["buyer"]
    made = desk["contract"](effective_from="2026-06-01")
    backwards = client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer, json={"effective_to": "2026-01-01"})
    assert backwards.status_code == 422 and "must not precede" in backwards.text
    assert client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer,
                        json={"effective_to": "2027-05-31"}).status_code == 200
    late_start = client.patch(f"/api/v1/contracts/{made['id']}", headers=buyer, json={"effective_from": "2027-06-01"})
    assert late_start.status_code == 422, "the other end, against the stored end"


def test_a_supplement_points_at_a_live_contract_on_its_side_and_never_round_in_a_loop(desk) -> None:
    client, buyer, seller = desk["client"], desk["buyer"], desk["seller"]
    a = desk["contract"](title="A")
    b = desk["contract"](title="B", parent_contract_id=a["id"])
    c = desk["contract"](title="C", parent_contract_id=b["id"])
    for target, parent in ((a, c), (a, b), (b, c)):
        loop = client.patch(f"/api/v1/contracts/{target['id']}", headers=buyer, json={"parent_contract_id": parent["id"]})
        assert loop.status_code == 422 and "supplement itself" in loop.text, (target["title"], parent["title"])
    assert client.patch(f"/api/v1/contracts/{a['id']}", headers=buyer,
                        json={"parent_contract_id": a["id"]}).status_code == 422

    crossed = client.post("/api/v1/contracts", headers=seller, json={
        "title": "Sales supplement", "customer_id": desk["customer"], "parent_contract_id": a["id"]})
    assert crossed.status_code == 422 and "its own side" in crossed.text
    stray = desk["contract"](title="To delete")
    assert client.delete(f"/api/v1/contracts/{stray['id']}", headers=buyer).status_code == 204
    orphan = client.post("/api/v1/contracts", headers=buyer, json={
        "title": "Supplement to a deleted contract", "contract_type": "oem", "vendor_id": desk["factory"], "parent_contract_id": stray["id"]})
    assert orphan.status_code == 404, "a deleted contract is supplemented by nothing"

    snapshot = client.post("/api/v1/contracts", headers=desk["admin"], json={
        "title": "Name-only contract", "counterparty_name_snapshot": "Some party", "side": "purchase",
        "parent_contract_id": a["id"]}).json()["data"]
    moved = client.patch(f"/api/v1/contracts/{snapshot['id']}", headers=desk["admin"], json={"side": "sales"})
    assert moved.status_code == 409 and "supplement links" in moved.text, "moving it would cross the parent link"
