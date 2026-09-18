"""Every paged list can be cut by its dates and its references.

The stock ledger could not be read for a week; an invoice list could not
be cut by due date; a contract list could not be cut by who signed it.
Lists now declare their filters once (`list_filters`) under one naming
rule — `<column>_from` / `<column>_thru` for a range, the column's own name
for an equality — and OpenAPI documents every one, which is what the
skills' contracts are generated from.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from conftest import make_client, provision_tenant

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREFIX = "/api/v1"


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Filter Co", email="admin@filter.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP-1"}, headers=admin).json()["data"]["id"]
        yield {"client": client, "admin": admin, "employee": emp, "customer": customer, "product": product}


def test_every_paged_list_documents_a_created_at_range() -> None:
    spec = json.loads((ROOT / "frontend/openapi.json").read_text(encoding="utf-8"))
    exempt = {"/auth/users", "/skills", "/workflow-definitions", "/tenant/api-key-owners"}
    missing = []
    for path, item in spec["paths"].items():
        get = item.get("get")
        if not get or not path.startswith(PREFIX) or "{" in path:
            continue
        names = {p["name"] for p in get.get("parameters", [])}
        if "size" not in names or path.removeprefix(PREFIX) in exempt:
            continue
        if "created_at_from" not in names or "created_at_thru" not in names:
            missing.append(path)
    assert not missing, f"paged lists without a created_at range: {missing}"


def test_the_ledger_reads_by_effective_date(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    position = c.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": shop["product"], "facility": "main", "initial_quantity": 10}).json()["data"]["id"]
    order = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"], "title": "o",
        "items": [{"product_id": shop["product"], "quantity": 2}]}).json()["data"]
    c.post(f"/api/v1/sales-orders/{order['id']}/reserve", headers=admin, json={
        "lines": [{"inventory_item_id": position, "quantity": 2}]})
    rows = c.get("/api/v1/inventory-item-details", headers=admin, params={
        "inventory_item_id": position, "effective_at_from": "2000-01-01T00:00:00Z", "effective_at_thru": "2099-01-01T00:00:00Z"}).json()["data"]
    assert sorted(r["reason"] for r in rows) == ["initial", "reserved"]
    none = c.get("/api/v1/inventory-item-details", headers=admin, params={
        "inventory_item_id": position, "effective_at_thru": "2000-01-01T00:00:00Z"}).json()["data"]
    assert none == []
    future_only = c.get("/api/v1/inventory-item-details", headers=admin, params={
        "inventory_item_id": position, "effective_at_from": "2099-01-01T00:00:00Z"}).json()["data"]
    assert future_only == []


def test_documents_cut_by_their_own_dates_and_references(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    early = c.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": shop["employee"], "customer_id": shop["customer"], "title": "早",
        "invoice_date": "2026-01-10", "due_date": "2026-02-10", "total_amount": 100}).json()["data"]
    late = c.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": shop["employee"], "customer_id": shop["customer"], "title": "晚",
        "invoice_date": "2026-06-10", "due_date": "2026-07-10", "total_amount": 100, "currency": "USD"}).json()["data"]
    by_due = c.get("/api/v1/invoices", headers=admin, params={"due_date_from": "2026-03-01", "due_date_thru": "2026-12-31"}).json()["data"]
    assert [i["id"] for i in by_due] == [late["id"]]
    by_invoice_date = c.get("/api/v1/invoices", headers=admin, params={"invoice_date_thru": "2026-03-01"}).json()["data"]
    assert [i["id"] for i in by_invoice_date] == [early["id"]]
    by_currency = c.get("/api/v1/invoices", headers=admin, params={"currency": "USD"}).json()["data"]
    assert [i["id"] for i in by_currency] == [late["id"]]

    contract = c.post("/api/v1/contracts", headers=admin, json={
        "title": "c", "contract_type": "oem", "customer_id": shop["customer"], "employee_id": shop["employee"],
        "effective_from": "2026-01-01", "effective_to": "2026-12-31"}).json()["data"]
    assert [x["id"] for x in c.get("/api/v1/contracts", headers=admin, params={"employee_id": shop["employee"]}).json()["data"]] == [contract["id"]]
    assert c.get("/api/v1/contracts", headers=admin, params={"effective_to_thru": "2026-06-30"}).json()["data"] == []
    assert len(c.get("/api/v1/contracts", headers=admin, params={"effective_from_thru": "2026-06-30"}).json()["data"]) == 1

    order = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"], "title": "o", "order_date": "2026-09-01",
        "promised_date": "2026-09-20", "items": [{"product_id": shop["product"], "quantity": 2}]}).json()["data"]
    assert len(c.get("/api/v1/sales-orders", headers=admin, params={"order_date_from": "2026-09-01", "promised_date_thru": "2026-09-30"}).json()["data"]) == 1
    assert c.get("/api/v1/sales-orders", headers=admin, params={"promised_date_from": "2026-10-01"}).json()["data"] == []
    line = c.get("/api/v1/sales-order-items", headers=admin, params={"order_id": order["id"], "created_at_from": "2000-01-01T00:00:00Z"}).json()["data"]
    assert len(line) == 1


def test_a_reference_filter_still_names_ids_not_names(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    refused = c.get("/api/v1/contracts", headers=admin, params={"employee_id": "xiao-li"})
    assert refused.status_code == 422 and "UUID" in refused.json()["detail"]
    bad_date = c.get("/api/v1/invoices", headers=admin, params={"due_date_from": "not-a-date"})
    assert bad_date.status_code == 422
