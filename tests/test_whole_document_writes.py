"""Whole-document writes (docs/whole-document-writes-2026-09-13.zh.md).

A document and its lines are one act on creation; this pins the rest of
that promise: every inline create can be tried first (`validate_only`),
adjustments ride the create beside the lines, the four families with a
shared line constructor can be restated as a whole (`/save`) as a DIFF
guarded by a revision, and the four hand-built line families go through
one constructor on both paths.
"""

from __future__ import annotations

import base64

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Whole Co", email="admin@whole.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        vendor = client.post("/api/v1/vendors", json={"name": "供应商"}, headers=admin).json()["data"]["id"]
        cup = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP-1", "list_price": 10}, headers=admin).json()["data"]["id"]
        lid = client.post("/api/v1/products", json={"name": "Lid", "product_code": "LID-1", "list_price": 2}, headers=admin).json()["data"]["id"]
        shelf = client.post("/api/v1/inventory-items", headers=admin, json={"product_id": cup, "facility": "main", "initial_quantity": 5}).json()["data"]["id"]
        yield {"client": client, "admin": admin, "employee": emp, "customer": customer, "vendor": vendor, "cup": cup, "lid": lid, "shelf": shelf}


def _count(client, headers, path, **params) -> int:
    return len(client.get(path, headers=headers, params=params).json()["data"])


# --- gap 1: a dry run everywhere ---------------------------------------------------

def test_every_inline_create_can_be_tried_first(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    lines = [{"product_id": desk["cup"], "quantity": 2, "unit_price": 10}]
    cases = [
        ("/api/v1/sales-quotations", {"employee_id": desk["employee"], "title": "q", "customer_id": desk["customer"], "items": lines}),
        ("/api/v1/sales-orders", {"employee_id": desk["employee"], "title": "o", "customer_id": desk["customer"], "items": lines}),
        ("/api/v1/purchase-requests", {"employee_id": desk["employee"], "title": "r", "items": lines}),
        ("/api/v1/purchase-orders", {"employee_id": desk["employee"], "vendor_id": desk["vendor"], "title": "p", "items": lines}),
        ("/api/v1/invoices", {"direction": "sales", "employee_id": desk["employee"], "customer_id": desk["customer"],
                              "title": "i", "items": [{"product_name_snapshot": "cups", "quantity": 2, "unit_price": 10}]}),
        ("/api/v1/contracts", {"title": "c", "contract_type": "oem", "customer_id": desk["customer"],
                               "items": [{"product_id": desk["cup"], "quantity": 1}]}),
        ("/api/v1/bills-of-materials", {"product_id": desk["cup"], "items": [{"component_product_id": desk["lid"], "quantity": 1}]}),
        ("/api/v1/picklists", {"items": [{"product_id": desk["cup"], "quantity": 1, "inventory_item_id": desk["shelf"]}]}),
        ("/api/v1/shipments", {"direction": "outbound", "items": [{"product_id": desk["cup"], "quantity": 1}]}),
    ]
    for path, body in cases:
        tried = c.post(path, headers=admin, json=body, params={"validate_only": "true"})
        assert tried.status_code in (200, 201), (path, tried.text)
        assert tried.json()["meta"] == {"validate_only": True, "written": False}, path
        assert tried.json()["data"].get("items"), path
        assert _count(c, admin, path) == 0, f"{path}: a dry run wrote"
    # and a dry run that fails, fails the way the real write would
    bad = c.post("/api/v1/sales-orders", headers=admin, params={"validate_only": "true"}, json={
        "employee_id": desk["employee"], "title": "o", "customer_id": desk["customer"],
        "items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]})
    assert bad.status_code == 404, bad.text
    assert _count(c, admin, "/api/v1/sales-orders") == 0


# --- gap 6: adjustments ride the create ---------------------------------------------

def test_adjustments_are_stated_with_the_document(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    created = c.post("/api/v1/sales-quotations", headers=admin, json={
        "employee_id": desk["employee"], "title": "q", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 10, "unit_price": 10},
                  {"product_id": desk["lid"], "quantity": 10, "unit_price": 2}],
        "adjustments": [{"adjustment_type": "discount", "amount": -10, "item_index": 0, "description": "10 off the cups"},
                        {"adjustment_type": "discount", "amount": -5, "description": "header"}]})
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert [a["quotation_item_id"] for a in data["adjustments"]] == [data["items"][0]["id"], None]
    detail = c.get(f"/api/v1/sales-quotations/{data['id']}/detail", headers=admin).json()["data"]
    assert detail["adjusted_total"] == 105.0
    out_of_range = c.post("/api/v1/sales-quotations", headers=admin, json={
        "employee_id": desk["employee"], "title": "q", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 1, "unit_price": 10}],
        "adjustments": [{"adjustment_type": "discount", "amount": -1, "item_index": 3}]})
    assert out_of_range.status_code == 422 and "item_index" in out_of_range.json()["detail"]


# --- gap 3: the whole document restated, as a diff, under a revision -------------------

def test_a_quotation_is_restated_as_a_diff_under_its_revision(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    q = c.post("/api/v1/sales-quotations", headers=admin, json={
        "employee_id": desk["employee"], "title": "q", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 10, "unit_price": 10},
                  {"product_id": desk["lid"], "quantity": 10, "unit_price": 2}],
        "adjustments": [{"adjustment_type": "discount", "amount": -5}]}).json()["data"]
    cup_line, lid_line = q["items"]
    detail = c.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=admin).json()["data"]
    revision = detail["revision"]
    assert revision and len(revision) == 64
    url = f"/api/v1/sales-quotations/{q['id']}/save"
    body = {"expected_revision": revision, "items": [
        {"id": cup_line["id"], "product_id": desk["cup"], "quantity": 12, "unit_price": 9},   # changed
        {"product_id": desk["lid"], "quantity": 1, "unit_price": 3},                          # added
        # the lid line of 10 is not listed: removed
    ], "adjustments": [
        {"id": q["adjustments"][0]["id"], "adjustment_type": "discount", "amount": -8},       # changed
        {"adjustment_type": "discount", "amount": -1, "item_index": 1},                       # added, on the new line
    ]}
    tried = c.post(url, headers=admin, json=body, params={"validate_only": "true"})
    assert tried.status_code == 200 and tried.json()["meta"]["written"] is False, tried.text
    still = c.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=admin).json()["data"]
    assert still["revision"] == revision, "a dry run leaves the document as it was"

    saved = c.post(url, headers=admin, json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()["data"]
    assert out["items"][0]["id"] == cup_line["id"], "a kept line keeps its identity"
    assert out["items"][0]["quantity"] == 12.0 and out["items"][0]["unit_price"] == 9.0
    assert out["items"][0]["amount"] is None, "a stored amount is dropped when the price moves (F-28)"
    assert lid_line["id"] not in {i["id"] for i in out["items"]}
    assert len(out["items"]) == 2 and len(out["adjustments"]) == 2
    assert out["adjustments"][1]["quotation_item_id"] == out["items"][1]["id"]
    assert out["revision"] != revision

    stale = c.post(url, headers=admin, json=body)
    assert stale.status_code == 409 and "revision" in stale.json()["detail"], "the old revision is refused"
    after = c.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=admin).json()["data"]
    assert after["revision"] == out["revision"]
    assert sorted(i["quantity"] for i in after["items"]) == [1.0, 12.0]
    trail = [r["action"] for r in c.get("/api/v1/audit-logs", headers=admin,
                                        params={"entity_type": "sales_quotation", "entity_id": q["id"], "limit": 50}).json()["data"]]
    for verb in ("line_changed", "line_added", "line_removed", "adjustment_changed", "adjustment_added"):
        assert any(a.endswith(verb) for a in trail), (verb, trail)
    foreign = c.post(url, headers=admin, json={"expected_revision": out["revision"], "items": [
        {"id": lid_line["id"], "product_id": desk["lid"], "quantity": 1}]})
    assert foreign.status_code == 422, "a removed line's id is not a live line"


def test_a_confirmed_order_cannot_be_restated_and_a_draft_can(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    o = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": desk["employee"], "title": "o", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 1, "unit_price": 10}]}).json()["data"]
    detail = c.get(f"/api/v1/sales-orders/{o['id']}/detail", headers=admin).json()["data"]
    body = {"expected_revision": detail["revision"], "items": [
        {"id": o["items"][0]["id"], "product_id": desk["cup"], "quantity": 3, "unit_price": 10}]}
    ok = c.post(f"/api/v1/sales-orders/{o['id']}/save", headers=admin, json=body)
    assert ok.status_code == 200, ok.text
    for state in ("submitted", "confirmed"):
        assert c.patch(f"/api/v1/sales-orders/{o['id']}", headers=admin, json={"status": state}).status_code == 200
    detail = c.get(f"/api/v1/sales-orders/{o['id']}/detail", headers=admin).json()["data"]
    closed = c.post(f"/api/v1/sales-orders/{o['id']}/save", headers=admin, json={**body, "expected_revision": detail["revision"]})
    assert closed.status_code == 409, closed.text


def test_the_owner_gate_holds_on_a_save(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    other_emp = c.post("/api/v1/employees", json={"name": "别人"}, headers=admin).json()["data"]["id"]
    rep = invite_member(c, admin, "rep", ["quotation.submit_own"], employee_id=other_emp)
    q = c.post("/api/v1/sales-quotations", headers=admin, json={
        "employee_id": desk["employee"], "title": "q", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 1, "unit_price": 10}]}).json()["data"]
    revision = c.get(f"/api/v1/sales-quotations/{q['id']}/detail", headers=admin).json()["data"]["revision"]
    refused = c.post(f"/api/v1/sales-quotations/{q['id']}/save", headers=rep, json={
        "expected_revision": revision, "items": [{"product_id": desk["cup"], "quantity": 1}]})
    assert refused.status_code == 403, refused.text


def test_purchase_documents_save_too(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    po = c.post("/api/v1/purchase-orders", headers=admin, json={
        "employee_id": desk["employee"], "vendor_id": desk["vendor"], "title": "p",
        "items": [{"product_id": desk["cup"], "quantity": 5, "unit_price": 8}],
        "adjustments": [{"adjustment_type": "discount", "amount": -4, "item_index": 0}]}).json()["data"]
    assert po["adjustments"][0]["po_item_id"] == po["items"][0]["id"]
    revision = c.get(f"/api/v1/purchase-orders/{po['id']}/detail", headers=admin).json()["data"]["revision"]
    saved = c.post(f"/api/v1/purchase-orders/{po['id']}/save", headers=admin, json={
        "expected_revision": revision,
        "items": [{"id": po["items"][0]["id"], "product_id": desk["cup"], "quantity": 6, "unit_price": 8}],
        "adjustments": []})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["adjustments"] == [], "an adjustment not restated is removed"
    pr = c.post("/api/v1/purchase-requests", headers=admin, json={
        "employee_id": desk["employee"], "title": "r", "items": [{"product_id": desk["cup"], "quantity": 1}]}).json()["data"]
    revision = c.get(f"/api/v1/purchase-requests/{pr['id']}/detail", headers=admin).json()["data"]["revision"]
    saved = c.post(f"/api/v1/purchase-requests/{pr['id']}/save", headers=admin, json={
        "expected_revision": revision, "items": [{"product_id": desk["lid"], "quantity": 4}]})
    assert saved.status_code == 200, saved.text
    assert [i["product_id"] for i in saved.json()["data"]["items"]] == [desk["lid"]]


# --- gap 4 + 7: one constructor per line family; contract documents and terms inline -----

def test_inline_and_standalone_lines_share_one_rulebook(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    lid_position = c.post("/api/v1/inventory-items", headers=admin, json={"product_id": desk["lid"], "facility": "main"}).json()["data"]["id"]
    crossed = {"product_id": desk["cup"], "quantity": 1, "inventory_item_id": lid_position}
    assert c.post("/api/v1/picklists", headers=admin, json={"items": [crossed]}).status_code == 422
    run = c.post("/api/v1/picklists", headers=admin, json={}).json()["data"]
    assert c.post("/api/v1/picklist-items", headers=admin, json={"picklist_id": run["id"], **crossed}).status_code == 422
    assert c.post("/api/v1/shipments", headers=admin, json={"direction": "outbound", "items": [crossed]}).status_code == 422
    leg = c.post("/api/v1/shipments", headers=admin, json={"direction": "outbound"}).json()["data"]
    assert c.post("/api/v1/shipment-items", headers=admin, json={"shipment_id": leg["id"], **crossed}).status_code == 422
    ghost = "00000000-0000-0000-0000-000000000000"
    assert c.post("/api/v1/contracts", headers=admin, json={
        "title": "c", "contract_type": "oem", "customer_id": desk["customer"], "items": [{"product_id": ghost, "quantity": 1}]}).status_code == 404
    assert c.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": desk["cup"], "items": [{"component_product_id": desk["cup"], "quantity": 1}]}).status_code == 422, "a product is not its own component"
    # the component is judged before the recipe row exists: a second active
    # recipe with a bad component is a 422 for the component, not a 409 for
    # the one-active-recipe index (the blackbox caught this on v2026.9.13)
    assert c.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": desk["cup"], "items": [{"component_product_id": desk["lid"], "quantity": 1}]}).status_code == 201
    again = c.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": desk["cup"], "items": [{"component_product_id": desk["cup"], "quantity": 1}]})
    assert again.status_code == 422, again.text


def test_a_contract_is_filed_with_its_documents_and_clauses(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    upload = c.post("/api/v1/attachments", headers=admin, json={
        "filename": "contract.pdf", "content_type": "application/pdf",
        "content_base64": base64.b64encode(b"%PDF-1.4 stub").decode()})
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["data"]["id"]
    created = c.post("/api/v1/contracts", headers=admin, json={
        "title": "OEM 2026", "contract_type": "oem", "customer_id": desk["customer"],
        "items": [{"product_id": desk["cup"], "quantity": 100, "unit_price": 9}],
        "documents": [{"attachment_id": attachment, "document_type": "signed", "caption": "signed scan"}],
        "terms": [{"term_type": "payment_terms", "content": "30% deposit, balance on delivery", "document_index": 0, "page_no": 3}]})
    assert created.status_code == 201, created.text
    full = c.get(f"/api/v1/contracts/{created.json()['data']['id']}", headers=admin).json()["data"]
    terms = [term for group in full["terms_by_type"].values() for term in group]
    assert len(full["documents"]) == 1 and terms[0]["document_id"] == full["documents"][0]["id"]
    assert terms[0]["page_no"] == 3
    dangling = c.post("/api/v1/contracts", headers=admin, json={
        "title": "x", "contract_type": "oem", "customer_id": desk["customer"],
        "terms": [{"term_type": "payment_terms", "content": "x", "document_index": 2}]})
    assert dangling.status_code == 422 and "document_index" in dangling.json()["detail"]
    assert _count(c, admin, "/api/v1/contracts") == 1, "the refused contract left nothing behind"
