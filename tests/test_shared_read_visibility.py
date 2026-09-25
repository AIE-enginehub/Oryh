"""Shared paper is read by grant, not by membership.

The client team's second end-to-end round (oryh-ai-client docs/50 §1.4,
2026-09-25): a vendor account holding only `business_object.write:
warranty_card` read another vendor's purchase invoice, the employees'
internal order follow-ups and every shipment — because invoices, payments,
purchase orders, freight, stock, business objects and account balances were
"shared business data, visible to the tenant". The personal-family rule now
applies to them (app/api/visibility.py `SHARED_FAMILIES`): an outside
credential reads what names it, what it wrote and what was routed to it;
`member` holds every family's read by default; the desks that write a
family read it without being told twice.

Same sweep as tests/test_read_visibility.py: file one of everything, then
ask EVERY GET route as the outsider and fail on the first row that leaks.
"""

from __future__ import annotations

import re

import pytest

from app.api.deps import Actor
from app.api.visibility import SHARED_FAMILIES, SHARED_READ_CAPABILITIES, visible_clause
from app.core.permissions import (
    CAPABILITY_COLLECTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    HOSTED_FLOW_AGENT_PERMISSIONS,
    PRINCIPAL_HOSTED_FLOW_AGENT,
    SYSTEM_CAPABILITY_NAMES,
)
from conftest import create, invite_member, make_client, provision_tenant

MARK = "ZQX-SHARED-PAPER"
OUTSIDER = ["business_object.write:warranty_card"]


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Shared Co", email="admin@shared.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        clerk_emp = create(client, admin, "employees", name="Clerk")["id"]
        rep_emp = create(client, admin, "employees", name="Vendor Rep")["id"]
        outsider = invite_member(client, admin, "vendor_rep", OUTSIDER, employee_id=rep_emp)
        customer = create(client, admin, "customers", name="Shared Customer")["id"]
        vendor = create(client, admin, "vendors", name="Other Vendor", vendor_code="OV-1")["id"]
        product = create(client, admin, "products", name="Shared Product", product_code="SP-1")["id"]

        ids: dict[str, str] = {}
        ids["sales_invoice"] = create(client, admin, "invoices", direction="sales", employee_id=clerk_emp,
                                      customer_id=customer, title=MARK,
                                      items=[{"product_name_snapshot": MARK, "quantity": 1, "unit_price": 100}])["id"]
        purchase = create(client, admin, "invoices", direction="purchase", employee_id=clerk_emp, vendor_id=vendor,
                          title=MARK, items=[{"product_name_snapshot": MARK, "quantity": 1, "unit_price": 45200}])
        ids["purchase_invoice"] = purchase["id"]
        ids["invoice_item"] = purchase["items"][0]["id"]
        ids["payment"] = create(client, admin, "payments", direction="inbound", employee_id=clerk_emp,
                                customer_id=customer, amount=10, remarks=MARK)["id"]
        po = create(client, admin, "purchase-orders", vendor_id=vendor, employee_id=clerk_emp, title=MARK,
                    items=[{"product_name_snapshot": MARK, "quantity": 1, "unit_price": 5}])
        ids["purchase_order"] = po["id"]
        ids["po_item"] = po["items"][0]["id"]
        ids["shipment"] = create(client, admin, "shipments", direction="inbound", purchase_order_id=po["id"],
                                 title=MARK, items=[])["id"]
        ids["picklist"] = create(client, admin, "picklists", remarks=MARK, items=[])["id"]
        ids["inventory_item"] = create(client, admin, "inventory-items", product_id=product, facility="main",
                                       initial_quantity=5, initial_description=MARK)["id"]
        ids["followup"] = create(client, admin, "business-objects", object_type="order_followup", title=MARK,
                                 summary=MARK)["id"]
        ids["billing_account"] = create(client, admin, "billing-accounts", name=MARK, unit_type="points",
                                        unit="point", customer_id=customer)["id"]
        # warranty cards: one the workspace filed, one the outsider filed
        card = create(client, admin, "business-objects", object_type="warranty_card", title="WC-OURS")["id"]
        own_card = create(client, outsider, "business-objects", object_type="warranty_card", title="WC-THEIRS")["id"]
        yield {"client": client, "admin": admin, "outsider": outsider, "rep_emp": rep_emp, "ids": ids,
               "card": card, "own_card": own_card, "customer": customer, "vendor": vendor}


def _routes(client) -> list[str]:
    spec = client.get("/openapi.json").json()
    return sorted(path for path, item in spec["paths"].items() if "get" in item and path.startswith("/api/v1/"))


def _leaks(client, who: dict, secret_ids: set[str]) -> list[str]:
    leaks = []
    for path in _routes(client):
        params = re.findall(r"{([^}]+)}", path)
        if len(params) > 1:
            continue
        targets = [path] if not params else [path.replace("{" + params[0] + "}", sid) for sid in secret_ids]
        for url in targets:
            r = client.get(url, headers=who)
            if r.status_code != 200:
                continue
            hit = [sid for sid in secret_ids if sid in r.text]
            if MARK in r.text or hit:
                leaks.append(f"{url.removeprefix('/api/v1')} -> {'marker' if MARK in r.text else hit[0][:8]}")
    return leaks


def test_an_outside_account_cannot_read_shared_paper_through_any_get_route(office) -> None:
    """1.4 — the vendor role saw another vendor's 45,200 purchase invoice."""
    leaks = _leaks(office["client"], office["outsider"], set(office["ids"].values()))
    assert not leaks, "the vendor rep reads the workspace's paper:\n  " + "\n  ".join(leaks)


def test_the_sweep_can_see_a_leak_when_there_is_one(office) -> None:
    found = _leaks(office["client"], office["admin"], set(office["ids"].values()))
    assert len(found) >= 20, found


def test_a_member_reads_the_shared_paper_as_before(office) -> None:
    c = office["client"]
    emp = create(c, office["admin"], "employees", name="Colleague")["id"]
    member = invite_member(c, office["admin"], "colleague", role="member", employee_id=emp)
    for path, key in (("/invoices", "purchase_invoice"), ("/payments", "payment"), ("/purchase-orders", "purchase_order"),
                      ("/shipments", "shipment"), ("/picklists", "picklist"), ("/inventory-items", "inventory_item"),
                      ("/business-objects", "followup"), ("/billing-accounts", "billing_account")):
        listed = {row["id"] for row in c.get(f"/api/v1{path}", headers=member).json()["data"]}
        assert office["ids"][key] in listed, f"{path}: a member reads it by being one"


def test_the_outsider_reads_its_own_type_and_what_it_filed(office) -> None:
    c, who = office["client"], office["outsider"]
    cards = {row["id"] for row in c.get("/api/v1/business-objects", headers=who).json()["data"]}
    assert cards == {office["card"], office["own_card"]}, "warranty cards, ours and theirs; nothing else"
    assert c.get(f"/api/v1/business-objects/{office['ids']['followup']}", headers=who).status_code == 404
    directory = {row["object_type"]: row["count"]
                 for row in c.get("/api/v1/object-directory", headers=who).json()["data"]}
    assert directory.get("warranty_card") == 2
    assert not directory.get("order_followup"), "the directory counts what the reader may list"
    assert directory.get("invoice", 0) == 0 and directory.get("shipment", 0) == 0


def test_a_scoped_grant_reads_its_scope_only(office) -> None:
    c, admin = office["client"], office["admin"]

    def desk(name: str, grants: list[str]) -> dict:
        emp = create(c, admin, "employees", name=name)["id"]
        return invite_member(c, admin, name, grants, employee_id=emp)

    sales_reader = desk("ar_reader", ["invoice.read:sales"])
    ap_clerk = desk("ap_clerk", ["invoice.manage:purchase"])
    sales, purchase = office["ids"]["sales_invoice"], office["ids"]["purchase_invoice"]
    assert {r["id"] for r in c.get("/api/v1/invoices", headers=sales_reader).json()["data"]} == {sales}
    assert {r["id"] for r in c.get("/api/v1/invoices", headers=ap_clerk).json()["data"]} == {purchase}, \
        "the desk that files purchase invoices reads them, and only them"
    assert c.get(f"/api/v1/invoices/{sales}", headers=ap_clerk).status_code == 404
    items = {r["id"] for r in c.get("/api/v1/invoice-items", headers=ap_clerk).json()["data"]}
    assert items == {office["ids"]["invoice_item"]}, "lines follow their document"
    # the payments desk reads payments and, having to settle them, invoices of every direction
    cashier = desk("cashier", ["payment.record"])
    assert office["ids"]["payment"] in {r["id"] for r in c.get("/api/v1/payments", headers=cashier).json()["data"]}
    assert {sales, purchase} <= {r["id"] for r in c.get("/api/v1/invoices", headers=cashier).json()["data"]}
    # the shelf reads freight; the freight desk reads the shelf — neither needs a second grant
    keeper = desk("keeper", ["inventory.manage"])
    shipper = desk("shipper", ["shipment.manage"])
    for who in (keeper, shipper):
        assert office["ids"]["shipment"] in {r["id"] for r in c.get("/api/v1/shipments", headers=who).json()["data"]}
        assert office["ids"]["inventory_item"] in {r["id"] for r in c.get("/api/v1/inventory-items", headers=who).json()["data"]}


def test_what_is_routed_to_the_outsider_becomes_readable(office) -> None:
    c, admin, who = office["client"], office["admin"], office["outsider"]
    invoice = office["ids"]["purchase_invoice"]
    assert c.get(f"/api/v1/invoices/{invoice}", headers=who).status_code == 404
    todo = c.post("/api/v1/todos", headers=admin, json={
        "employee_id": office["rep_emp"], "entity_type": "invoice", "entity_id": invoice, "title": "确认对账"})
    assert todo.status_code == 201, todo.text
    assert c.get(f"/api/v1/invoices/{invoice}", headers=who).status_code == 200, "a todo on it is the routing"
    assert [r["id"] for r in c.get("/api/v1/invoices", headers=who).json()["data"]] == [invoice]
    assert [r["id"] for r in c.get("/api/v1/invoice-items", headers=who).json()["data"]] == [office["ids"]["invoice_item"]]
    assert c.get(f"/api/v1/invoices/{office['ids']['sales_invoice']}", headers=who).status_code == 404


def test_the_read_grants_are_catalogued_and_member_holds_them() -> None:
    assert set(SHARED_READ_CAPABILITIES) <= SYSTEM_CAPABILITY_NAMES
    member = set(DEFAULT_ROLE_PERMISSIONS["member"])
    for capability in SHARED_READ_CAPABILITIES:
        assert capability in member or f"{capability}:*" in member, capability
        assert capability in CAPABILITY_COLLECTIONS, capability
    assert len({f.capability for f in SHARED_FAMILIES}) == len(SHARED_READ_CAPABILITIES)


def test_the_hosted_flow_agent_reads_every_family_it_drives() -> None:
    """The agent's grant set gained nothing: the advance verbs it holds imply
    the reads, so its queues did not go dark."""
    agent = Actor(tenant_id="t", kind="service", role="service", credential_id="k",
                  permissions=frozenset(HOSTED_FLOW_AGENT_PERMISSIONS), principal_kind=PRINCIPAL_HOSTED_FLOW_AGENT)
    for family in SHARED_FAMILIES:
        assert visible_clause(agent, family.model) is None, family.name
