"""Whole-document saves for the documents that did not have one.

Timesheets, quotations, orders, purchase requests and purchase orders could be
restated in one call; an expense claim with twelve receipts was still twelve
PATCHes and DELETEs, each a turn, each a chance to stop half-way. The same
for invoices, contracts, bills of materials, opportunities, shipments and
picklists. One engine (`restate_rows`) and one contract for all of them:
`expected_revision` from the detail, ids kept are changed only in the fields
stated, rows without an id are added, live rows not named are removed,
`?validate_only=true` writes nothing.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Save Co", email="admin@save.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        vendor = client.post("/api/v1/vendors", json={"name": "供应商"}, headers=admin).json()["data"]["id"]
        cup = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP"}, headers=admin).json()["data"]["id"]
        lid = client.post("/api/v1/products", json={"name": "Lid", "product_code": "LID"}, headers=admin).json()["data"]["id"]
        box = client.post("/api/v1/products", json={"name": "Box", "product_code": "BOX"}, headers=admin).json()["data"]["id"]
        yield {"client": client, "admin": admin, "employee": emp, "customer": customer, "vendor": vendor,
               "cup": cup, "lid": lid, "box": box}


def _audit_verbs(c, admin, entity_type, entity_id) -> list[str]:
    rows = c.get("/api/v1/audit-logs", headers=admin, params={"entity_type": entity_type, "entity_id": entity_id}).json()["data"]
    return sorted(r["action"].rsplit(".", 1)[1] for r in rows if r["action"].rsplit(".", 1)[1].startswith("line_"))


def test_an_expense_claim_is_restated_in_one_call(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    claim = c.post("/api/v1/expense-claims", headers=admin, json={
        "employee_id": desk["employee"], "title": "九月差旅",
        "items": [{"expense_date": "2026-09-01", "category": "travel", "amount": 100, "notes": "高铁",
                   "extracted_fields": {"seat": "07A"}},
                  {"expense_date": "2026-09-02", "category": "meal", "amount": 50}]}).json()["data"]
    detail = c.get(f"/api/v1/expense-claims/{claim['id']}/detail", headers=admin).json()["data"]
    revision, (train, meal) = detail["revision"], detail["items"]
    assert len(revision) == 64

    body = {"expected_revision": revision, "title": "九月差旅（改）", "items": [
        {"id": train["id"], "amount": 120},                                   # changed: one field stated
        {"expense_date": "2026-09-03", "category": "lodging", "amount": 300},   # added
    ]}                                                                        # meal: not named → removed
    dry = c.post(f"/api/v1/expense-claims/{claim['id']}/save?validate_only=true", headers=admin, json=body).json()
    assert dry["meta"] == {"validate_only": True, "written": False} and dry["data"]["total_amount"] == 420
    assert c.get(f"/api/v1/expense-claims/{claim['id']}/detail", headers=admin).json()["data"]["revision"] == revision, \
        "a dry run leaves nothing behind"

    saved = c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=admin, json=body)
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["claim"]["title"] == "九月差旅（改）" and data["total_amount"] == 420
    kept = next(i for i in data["items"] if i["id"] == train["id"])
    assert kept["amount"] == 120 and kept["notes"] == "高铁" and kept["extracted_fields"] == {"seat": "07A"}, \
        "a kept line changes only in the fields the row states"
    assert meal["id"] not in [i["id"] for i in data["items"]] and len(data["items"]) == 2
    assert data["revision"] != revision
    assert _audit_verbs(c, admin, "expense_claim", claim["id"]) == ["line_added", "line_changed", "line_removed"]

    stale = c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=admin, json=body)
    assert stale.status_code == 409, "the revision the client read is gone"
    foreign = c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=admin, json={
        "expected_revision": data["revision"], "items": [{"id": meal["id"], "amount": 1}]})
    assert foreign.status_code == 422, "a removed line is no longer a line of this claim"


def test_the_gates_of_the_single_row_paths_hold_on_a_save(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    claim = c.post("/api/v1/expense-claims", headers=admin, json={
        "employee_id": desk["employee"], "title": "c",
        "items": [{"expense_date": "2026-09-01", "category": "travel", "amount": 100}]}).json()["data"]
    revision = c.get(f"/api/v1/expense-claims/{claim['id']}/detail", headers=admin).json()["data"]["revision"]
    other_emp = c.post("/api/v1/employees", json={"name": "别人"}, headers=admin).json()["data"]["id"]
    stranger = invite_member(c, admin, "stranger", ["expense.submit_own"], employee_id=other_emp)
    assert c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=stranger,
                  json={"expected_revision": revision, "items": []}).status_code == 404, "someone else's claim does not exist"
    bad = c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=admin, json={
        "expected_revision": revision, "items": [{"expense_date": "2026-09-01", "category": "no-such-category", "amount": 1}]})
    assert bad.status_code == 422, "an added line goes through the constructor the POST uses"
    assert len(c.get(f"/api/v1/expense-claims/{claim['id']}/detail", headers=admin).json()["data"]["items"]) == 1, "and nothing landed"
    c.post(f"/api/v1/expense-claims/{claim['id']}/submit", headers=admin, json={})
    revision = c.get(f"/api/v1/expense-claims/{claim['id']}/detail", headers=admin).json()["data"]["revision"]
    assert c.post(f"/api/v1/expense-claims/{claim['id']}/save", headers=admin,
                  json={"expected_revision": revision, "items": []}).status_code == 409, "a submitted claim is not editable"


def _restate(c, admin, url: str, revision: str, items: list, expect: int = 200) -> dict:
    r = c.post(url, headers=admin, json={"expected_revision": revision, "items": items})
    assert r.status_code == expect, r.text
    return r.json().get("data", {})


def test_an_invoice_is_restated_and_a_line_cannot_become_another_product_in_place(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    inv = c.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "inv",
        "items": [{"product_id": desk["cup"], "quantity": 2, "unit_price": 10, "amount": 20},
                  {"product_id": desk["lid"], "quantity": 1, "unit_price": 5, "amount": 5}]}).json()["data"]
    detail = c.get(f"/api/v1/invoices/{inv['id']}/detail", headers=admin).json()["data"]
    cup_line = next(i for i in detail["items"] if i["product_id"] == desk["cup"])
    lid_line = next(i for i in detail["items"] if i["product_id"] == desk["lid"])
    url = f"/api/v1/invoices/{inv['id']}/save"
    dry = c.post(url + "?validate_only=true", headers=admin, json={"expected_revision": detail["revision"], "items": []}).json()
    assert dry["meta"]["written"] is False and dry["data"]["items"] == []
    data = _restate(c, admin, url, detail["revision"], [
        {"id": cup_line["id"], "quantity": 3, "amount": 30},
        {"product_id": desk["box"], "quantity": 1, "unit_price": 8, "amount": 8}])
    assert sorted(i["amount"] for i in data["items"]) == [8, 30] and lid_line["id"] not in [i["id"] for i in data["items"]]
    assert _audit_verbs(c, admin, "invoice", inv["id"]) == ["line_added", "line_changed", "line_removed"]
    assert c.get(f"/api/v1/invoices/{inv['id']}/detail", headers=admin).json()["data"]["revision"] == data["revision"]
    _restate(c, admin, url, detail["revision"], [], expect=409)
    c.post(f"/api/v1/invoices/{inv['id']}/submit", headers=admin, json={})
    issued = c.get(f"/api/v1/invoices/{inv['id']}/detail", headers=admin).json()["data"]["revision"]
    _restate(c, admin, url, issued, [], expect=409)


def test_a_draft_recipe_is_restated_and_an_active_one_is_not(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    bom = c.post("/api/v1/bills-of-materials", headers=admin, json={
        "product_id": desk["box"], "bom_code": "B-1", "status": "draft",
        "items": [{"component_product_id": desk["cup"], "quantity": 1}, {"component_product_id": desk["lid"], "quantity": 1}]}).json()["data"]
    read = c.get(f"/api/v1/bills-of-materials/{bom['id']}", headers=admin).json()["data"]
    cup_line = next(i for i in read["items"] if i["component_product_id"] == desk["cup"])
    url = f"/api/v1/bills-of-materials/{bom['id']}/save"
    data = _restate(c, admin, url, read["revision"], [{"id": cup_line["id"], "quantity": 4}])
    assert [(i["component_product_id"], i["quantity"]) for i in data["items"]] == [(desk["cup"], 4)]
    own = c.post(url, headers=admin, json={"expected_revision": data["revision"], "items": [{"component_product_id": desk["box"], "quantity": 1}]})
    assert own.status_code in (409, 422), "a recipe is not its own component — the constructor's rule"
    swapped = c.post(url, headers=admin, json={"expected_revision": data["revision"],
                                               "items": [{"id": cup_line["id"], "component_product_id": desk["lid"]}]})
    assert swapped.status_code == 200, "the component is a field the PATCH takes too"
    revision = swapped.json()["data"]["revision"]
    c.patch(f"/api/v1/bills-of-materials/{bom['id']}", headers=admin, json={"status": "active"})
    live = c.get(f"/api/v1/bills-of-materials/{bom['id']}", headers=admin).json()["data"]["revision"]
    assert live != revision
    _restate(c, admin, url, live, [], expect=409)


def test_contract_lines_are_restated(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    contract = c.post("/api/v1/contracts", headers=admin, json={
        "title": "框架", "contract_type": "oem", "customer_id": desk["customer"], "employee_id": desk["employee"],
        "items": [{"product_id": desk["cup"], "quantity": 100, "unit_price": 9},
                  {"product_id": desk["lid"], "quantity": 100, "unit_price": 1}]}).json()["data"]
    read = c.get(f"/api/v1/contracts/{contract['id']}", headers=admin).json()["data"]
    assert len(read["revision"]) == 64
    cup_line = next(i for i in read["items"] if i["product_id"] == desk["cup"])
    data = _restate(c, admin, f"/api/v1/contracts/{contract['id']}/save", read["revision"], [
        {"id": cup_line["id"], "unit_price": 8.5}, {"product_id": desk["box"], "quantity": 10, "unit_price": 3}])
    assert sorted(i["product_id"] for i in data["items"]) == sorted([desk["cup"], desk["box"]])
    assert next(i for i in data["items"] if i["id"] == cup_line["id"])["unit_price"] == 8.5
    ghost = c.post(f"/api/v1/contracts/{contract['id']}/save", headers=admin, json={
        "expected_revision": data["revision"], "items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]})
    assert ghost.status_code == 404, "a phantom product is refused on the save as on the POST"


def test_warehouse_documents_are_restated_until_they_post(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    position = c.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": desk["cup"], "facility": "main", "initial_quantity": 50}).json()["data"]["id"]
    lid_position = c.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": desk["lid"], "facility": "main", "initial_quantity": 50}).json()["data"]["id"]
    order = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "o",
        "items": [{"product_id": desk["cup"], "quantity": 5}, {"product_id": desk["lid"], "quantity": 5}]}).json()["data"]
    shipment = c.post("/api/v1/shipments", headers=admin, json={
        "direction": "outbound", "sales_order_id": order["id"],
        "items": [{"product_id": desk["cup"], "quantity": 5, "inventory_item_id": position}]})
    assert shipment.status_code == 201, shipment.text
    sid = shipment.json()["data"]["id"]
    read = c.get(f"/api/v1/shipments/{sid}", headers=admin).json()["data"]
    line = read["items"][0]
    data = _restate(c, admin, f"/api/v1/shipments/{sid}/save", read["revision"], [
        {"id": line["id"], "quantity": 3},
        {"product_id": desk["lid"], "quantity": 2, "inventory_item_id": lid_position}])
    assert sorted(i["quantity"] for i in data["items"]) == [2, 3]
    wrong = c.post(f"/api/v1/shipments/{sid}/save", headers=admin, json={"expected_revision": data["revision"], "items": [
        {"product_id": desk["lid"], "quantity": 1, "inventory_item_id": position}]})
    assert wrong.status_code in (409, 422), "a position that holds another product is refused, as on the POST"
    fixed = c.post(f"/api/v1/shipments/{sid}/save", headers=admin, json={"expected_revision": data["revision"], "items": [
        {"id": line["id"], "product_id": desk["lid"]}]})
    assert fixed.status_code == 422 and "cannot change on an existing row" in fixed.json()["detail"]

    picklist = c.post("/api/v1/picklists", headers=admin, json={
        "sales_order_id": order["id"], "facility_id": None,
        "items": [{"product_id": desk["cup"], "quantity": 5, "inventory_item_id": position}]})
    if picklist.status_code == 201:
        pid = picklist.json()["data"]["id"]
        pread = c.get(f"/api/v1/picklists/{pid}", headers=admin).json()["data"]
        pdata = _restate(c, admin, f"/api/v1/picklists/{pid}/save", pread["revision"], [
            {"id": pread["items"][0]["id"], "quantity": 4}])
        assert [i["quantity"] for i in pdata["items"]] == [4]


def test_a_deal_is_restated_by_its_owner(desk) -> None:
    c, admin = desk["client"], desk["admin"]
    deal = c.post("/api/v1/opportunities", headers=admin, json={
        "employee_id": desk["employee"], "customer_id": desk["customer"], "title": "deal"}).json()["data"]
    for product in (desk["cup"], desk["lid"]):
        assert c.post("/api/v1/opportunity-items", headers=admin, json={
            "opportunity_id": deal["id"], "product_id": product, "quantity": 2, "unit_price": 10}).status_code == 201
    detail = c.get(f"/api/v1/opportunities/{deal['id']}/detail", headers=admin).json()["data"]
    cup_line = next(i for i in detail["items"] if i["product_id"] == desk["cup"])
    data = _restate(c, admin, f"/api/v1/opportunities/{deal['id']}/save", detail["revision"], [
        {"id": cup_line["id"], "quantity": 5}, {"product_name_snapshot": "安装培训", "quantity": 1, "unit_price": 3000}])
    kept = next(i for i in data["items"] if i["id"] == cup_line["id"])
    assert kept["quantity"] == 5 and kept["amount"] == 50, "the amount follows quantity × price, as on the PATCH"
    assert len(data["items"]) == 2
    trail = c.get("/api/v1/audit-logs", headers=admin, params={"entity_type": "opportunity", "entity_id": deal["id"]}).json()["data"]
    assert {"opportunity.item_added", "opportunity.item_changed", "opportunity.item_removed"} <= {r["action"] for r in trail}
    nameless = c.post(f"/api/v1/opportunities/{deal['id']}/save", headers=admin, json={
        "expected_revision": data["revision"], "items": [{"quantity": 1}]})
    assert nameless.status_code == 422


def test_every_document_with_lines_has_a_save() -> None:
    """The point of the sweep: a document whose create takes inline lines can
    be restated in one call. Payments are the deliberate exception — applying
    money is `/apply`, with its own idempotency."""
    from app.main import app
    paths = app.openapi()["paths"]
    for collection in ("timesheet-headers", "expense-claims", "invoices", "sales-quotations", "sales-orders",
                       "purchase-requests", "purchase-orders", "contracts", "bills-of-materials", "picklists",
                       "shipments", "opportunities"):
        save = next((p for p in paths if p.startswith(f"/api/v1/{collection}/{{") and p.endswith("/save")), None)
        assert save and "post" in paths[save], collection
        assert any(q["name"] == "validate_only" for q in paths[save]["post"].get("parameters", [])), collection
