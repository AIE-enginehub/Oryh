"""State names are the tenant's vocabulary, end to end.

The acceptance case: an admin says "invoice 审批完成后的状态改叫 approved" —
one PATCH to the builtin machine, with a `roles` entry telling the server
where its anchor went. Everything the server does with that state follows the
role: /submit lands on the tenant's word, issued_at stamps on the tenant's
word, reimbursement invoices arrive in it, documents are created in the
machine's own initial.

What made this impossible before was an anchor on the NAMES: every builtin
machine had to keep literal `draft` and `submitted` and start at `draft` — so
renaming was refused at validation. And `issued` was not anchored at all, so
renaming IT saved fine and then broke the reimbursement route at runtime.
Roles replace both failure modes: rename freely, declare where the roles
live, and a machine that cannot answer is refused at save time with the exact
entry to add.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


@pytest.fixture()
def shop(client: TestClient):
    t = provision_tenant(client, company_name="Vocab Co", email="admin@vocab.example")
    headers = {"X-API-Key": t["plain_text_api_key"]}

    def post(path, body, expect=(200, 201)):
        r = client.post(f"/api/v1{path}", json=body, headers=headers)
        assert r.status_code in expect, f"{path} -> {r.status_code} {r.text[:300]}"
        return r.json()["data"]

    def save_machine(object_type: str, machine: dict):
        existing = client.get(
            f"/api/v1/object-type-definitions?entity_kind=builtin&object_type={object_type}",
            headers=headers).json()["data"]
        if existing:
            return client.patch(f"/api/v1/object-type-definitions/{existing[0]['id']}",
                                json={"state_machine": machine}, headers=headers)
        return client.post("/api/v1/object-type-definitions", headers=headers, json={
            "entity_kind": "builtin", "object_type": object_type, "json_schema": {},
            "state_machine": machine})

    return {"client": client, "headers": headers, "post": post,
            "save_machine": save_machine,
            "employee": post("/employees", {"name": "Li"})["id"]}


def test_the_admins_one_sentence_renames_issued_to_approved(shop) -> None:
    """The user-stated acceptance case, verbatim."""
    saved = shop["save_machine"]("invoice", {
        "initial": "draft",
        "states": ["draft", "submitted", "returned", "approved", "paid",
                   "written_off", "void", "cancelled"],
        "transitions": {
            "draft": ["submitted", "cancelled"],
            "submitted": ["approved", "returned", "cancelled"],
            "returned": ["submitted", "cancelled"],
            "approved": ["paid", "written_off", "void"],
            "paid": [], "written_off": [], "void": [], "cancelled": [],
        },
        "editable_states": ["draft", "returned"],
        "roles": {"issued": "approved"},
    })
    assert saved.status_code in (200, 201), saved.text

    vendor = shop["post"]("/vendors", {"name": "Dell"})["id"]
    invoice = shop["post"]("/invoices", {
        "direction": "purchase", "employee_id": shop["employee"], "vendor_id": vendor,
        "title": "one bill", "total_amount": 500.0})
    shop["client"].post(f"/api/v1/invoices/{invoice['id']}/submit", json={},
                        headers=shop["headers"])

    # the flow agent finalizes in the TENANT's word…
    moved = shop["client"].patch(f"/api/v1/invoices/{invoice['id']}",
                                 json={"status": "approved"}, headers=shop["headers"])
    assert moved.status_code == 200, moved.text
    fresh = shop["client"].get(f"/api/v1/invoices/{invoice['id']}",
                               headers=shop["headers"]).json()["data"]
    assert fresh["status"] == "approved"
    # …and issued_at follows the ROLE, not the shipped name
    assert fresh["issued_at"] is not None, (
        "the timestamp coupling must follow the role — an invoice approved "
        "under the tenant's vocabulary is still an issued invoice"
    )

    # the shipped word is gone: the machine is the tenant's, entirely
    refused = shop["client"].patch(f"/api/v1/invoices/{invoice['id']}",
                                   json={"status": "issued"}, headers=shop["headers"])
    assert refused.status_code == 409, refused.text


def test_reimbursement_invoices_arrive_in_the_tenants_word(shop) -> None:
    saved = shop["save_machine"]("invoice", {
        "initial": "draft",
        "states": ["draft", "submitted", "returned", "approved", "paid",
                   "written_off", "void", "cancelled"],
        "transitions": {
            "draft": ["submitted", "cancelled"],
            "submitted": ["approved", "returned", "cancelled"],
            "returned": ["submitted", "cancelled"],
            "approved": ["paid", "written_off", "void"],
            "paid": [], "written_off": [], "void": [], "cancelled": [],
        },
        "editable_states": ["draft", "returned"],
        "roles": {"issued": "approved"},
    })
    assert saved.status_code in (200, 201)

    claim = shop["post"]("/expense-claims", {
        "employee_id": shop["employee"], "title": "July travel",
        "items": [{"expense_date": "2026-07-18", "amount": 300.0, "category": "transport"}]})
    shop["client"].post(f"/api/v1/expense-claims/{claim['id']}/submit", json={},
                        headers=shop["headers"])
    shop["client"].post("/api/v1/approval-records", headers=shop["headers"], json={
        "entity_type": "expense_claim", "entity_id": claim["id"], "action": "approved",
        "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
    shop["client"].patch(f"/api/v1/expense-claims/{claim['id']}",
                         json={"status": "approved"}, headers=shop["headers"])

    raised = shop["client"].post(f"/api/v1/expense-claims/{claim['id']}/invoice",
                                 headers=shop["headers"])
    assert raised.status_code == 201, raised.text
    assert raised.json()["data"]["status"] == "approved"
    assert raised.json()["data"]["issued_at"] is not None


def test_documents_are_created_in_the_machines_own_initial(shop) -> None:
    """"创建时什么状态" — the initial is the machine's, not the schema's."""
    saved = shop["save_machine"]("expense_claim", {
        "initial": "open",
        "states": ["open", "filed", "returned", "approved", "rejected", "paid"],
        "transitions": {
            "open": ["filed"], "filed": ["approved", "returned", "rejected"],
            "returned": ["filed"], "approved": ["paid"], "rejected": [], "paid": [],
        },
        "editable_states": ["open", "returned"],
        "roles": {"submitted": "filed"},
    })
    assert saved.status_code in (200, 201), saved.text

    claim = shop["post"]("/expense-claims", {
        "employee_id": shop["employee"], "title": "no status stated",
        "items": [{"expense_date": "2026-07-18", "amount": 90.0, "category": "meal"}]})
    assert claim["status"] == "open", (
        "a create that states no status starts at the TENANT machine's initial"
    )

    # …and /submit lands on the tenant's word for the submitted role
    submitted = shop["client"].post(f"/api/v1/expense-claims/{claim['id']}/submit",
                                    json={}, headers=shop["headers"])
    assert submitted.status_code == 200, submitted.text
    fresh = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}",
                               headers=shop["headers"]).json()["data"]
    assert fresh["status"] == "filed"
    assert fresh["submitted_at"] is not None

    # a second submit is the idempotent no-op it always was, under the new name
    again = shop["client"].post(f"/api/v1/expense-claims/{claim['id']}/submit",
                                json={}, headers=shop["headers"])
    assert again.status_code == 200


def test_a_machine_that_loses_a_role_is_refused_with_the_recipe(shop) -> None:
    refused = shop["save_machine"]("payment", {
        "initial": "draft",
        "states": ["draft", "submitted", "settled"],
        "transitions": {"draft": ["submitted"], "submitted": ["settled"], "settled": []},
        "editable_states": ["draft"],
    })
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert '"roles"' in detail and "paid" in detail, detail


def test_untouched_workspaces_notice_nothing(shop) -> None:
    """Every existing tenant machine resolves roles by identity. The shipped
    vocabulary keeps working with no roles entry anywhere."""
    claim = shop["post"]("/expense-claims", {
        "employee_id": shop["employee"], "title": "plain",
        "items": [{"expense_date": "2026-07-18", "amount": 10.0, "category": "meal"}]})
    assert claim["status"] == "draft"
    shop["client"].post(f"/api/v1/expense-claims/{claim['id']}/submit", json={},
                        headers=shop["headers"])
    fresh = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}",
                               headers=shop["headers"]).json()["data"]
    assert fresh["status"] == "submitted"
