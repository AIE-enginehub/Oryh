"""The setup report: where a workspace stands, derived on every call.

The wizard for a new administrator is a skill plus this one read — and the
read deliberately has no storage. Every hand-maintained progress record in
this codebase has drifted from the thing it recorded (four lists, one
console, two vocabularies); a derivation cannot, and it makes the wizard
resumable by construction: work done outside it, in any order, shows as
done. `untouched` is a statement about data, never a to-do — whether a
workspace uses a family is the administrator's judgment, held in their
agent's own context, stored nowhere here (the product owner's explicit
call).

What is pinned: the area list follows the FAMILY REGISTRY, so a family
added tomorrow appears in the report without anyone remembering; staffing
excludes the system admin role (it holds everything by definition and
would mark every family ready on day one); and the report is the
administrator's read — it exposes the access topology the member surface
deliberately withholds.
"""

from __future__ import annotations

import pytest

from app.api.common import DOCUMENT_FAMILIES
from app.services.emails import outbox
from app.services.provisioning import PRODUCT_SKILLS_DIR

from conftest import make_client, provision_tenant


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Fresh Co", email="admin@fresh.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def report() -> dict:
            r = client.get("/api/v1/workspace/setup-report", headers=admin)
            assert r.status_code == 200, r.text
            return r.json()["data"]["areas"]

        def invite(role: str, permissions: list[str]) -> dict:
            client.post("/api/v1/roles", json={"name": role, "permissions": permissions},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{role}@fresh.example", "role": role},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys",
                              json={"label": role, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"user_id": uid, "key": {"X-API-Key": key}}

        yield {"client": client, "admin": admin, "report": report, "invite": invite}


def test_the_area_list_follows_the_family_registry(office) -> None:
    areas = office["report"]()
    families = {family.object_type for family in DOCUMENT_FAMILIES.values()}
    fixed = {"organization", "master_data", "flow_driving", "ecommerce", "treasury"}
    assert set(areas) == families | fixed, (
        "a document family added tomorrow must appear in the report the same "
        "day — the list is derived, never maintained"
    )


def test_a_fresh_workspace_reads_as_what_it_is(office) -> None:
    areas = office["report"]()
    assert areas["master_data"]["status"] == "untouched"
    assert areas["ecommerce"]["status"] == "untouched" and areas["ecommerce"]["optional"]
    for family in DOCUMENT_FAMILIES.values():
        area = areas[family.object_type]
        assert area["status"] in ("untouched", "partial"), (
            f"{family.object_type} cannot be ready in an empty workspace — "
            "only the admin exists, and the admin role must not count as staffing"
        )
        assert area["facts"]["staffed_by"]["active_users"] == 0
    # provisioning enrols the drivable families, so flow driving starts live —
    # where the flow skills ship. The open-core tree carries none (they are
    # the hosted product's), derives no driver, and honestly reads untouched.
    if (PRODUCT_SKILLS_DIR / "oryh-expense-approval-flow").is_dir():
        assert areas["flow_driving"]["status"] == "ready"
    else:
        assert areas["flow_driving"]["status"] == "untouched"
    assert areas["organization"]["status"] == "untouched"


def test_staffing_then_defining_walks_a_family_to_ready(office) -> None:
    client, admin = office["client"], office["admin"]
    office["invite"]("clerk", ["expense.submit_own", "expense.advance"])
    area = office["report"]()["expense_claim"]
    # the shipped `member` role also carries the capability — with nobody in
    # it; the roles list is the map, active_users the truth
    assert "clerk" in area["facts"]["staffed_by"]["roles"]
    assert area["facts"]["staffed_by"]["active_users"] == 1
    assert area["status"] == "partial", "staffed but no workflow definition yet"
    assert "workflow definition" in area["next"]

    published = client.post("/api/v1/workflow-definitions", headers=admin, json={
        "entity_kind": "builtin", "object_type": "expense_claim",
        "definition_text": "报销直接主管审批,超5000加财务。"})
    assert published.status_code in (200, 201), published.text
    area = office["report"]()["expense_claim"]
    assert area["status"] == "ready"
    assert area["facts"]["workflow_definitions"]["expense_claim"] is True

    org = office["report"]()["organization"]
    assert org["facts"]["active_non_admin_users"] == 1


def test_a_functional_family_is_ready_without_a_definition(office) -> None:
    """Purchase orders and shipments run on one functional grant with no
    advance verb — no flow to define, so staffing alone is readiness."""
    office["invite"]("keeper", ["inventory.manage", "purchase_order.manage"])
    areas = office["report"]()
    assert areas["shipment"]["status"] == "ready"
    assert areas["purchase_order"]["status"] == "ready"


def test_kind_split_families_report_both_machines_and_both_counts(office) -> None:
    client, admin = office["client"], office["admin"]
    emp = client.post("/api/v1/employees", json={"name": "店长"},
                      headers=admin).json()["data"]["id"]
    so = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "一单"}).json()["data"]
    client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "退一件", "order_kind": "return",
        "original_order_id": so["id"]})
    area = office["report"]()["sales_order"]
    assert area["facts"]["documents"] == 1 and area["facts"]["returns"] == 1, (
        "orders and returns share a table; the report must not count a return "
        "as an order"
    )
    assert set(area["facts"]["workflow_definitions"]) == {"sales_order", "sales_return"}


def test_the_report_is_the_administrators_read(office) -> None:
    nobody = office["invite"]("nobody", [])
    refused = office["client"].get("/api/v1/workspace/setup-report",
                                   headers=nobody["key"])
    assert refused.status_code == 403, (
        "the report exposes the access topology — roles, who holds what, "
        "what reaches nobody — which the member surface deliberately withholds"
    )
