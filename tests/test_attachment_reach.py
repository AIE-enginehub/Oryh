"""Holding an attachment's id is not permission to read it.

`GET /attachments/{id}/content` was tenant-scoped and nothing else, so any
credential in the workspace could fetch any attachment's bytes. 工资条 is an
invoice and its attachment is the payslip, which makes that the exact read
`test_payroll_visibility.py` opens by calling "the first read in this API that
belonging to the workspace does not entitle you to" — and warns about in the
next breath: "a gate is only worth what its *least* covered path is: one
endpoint left open and the whole thing is decoration." This was that endpoint,
and nothing failed when it was closed, which is what an uncovered path means.

The bytes now travel with the document. The caller names the invoice, the
claim, the policy; the family's own visibility check answers first; only then
is the attachment served, and only if that document actually carries it.
"""

from __future__ import annotations

import base64
from collections.abc import Generator

import pytest

from app.api.common import ATTACHMENT_SOURCES
from app.models import Base
from app.services.emails import outbox

from conftest import make_client
from conftest import provision_tenant as bootstrap_tenant


def token_from(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


@pytest.fixture()
def world() -> Generator[dict, None, None]:
    """One workspace holding a payslip and an expense receipt, plus three
    credentials: the admin, a payroll-blind clerk, and the claimant."""
    with make_client([]) as client:
        data = bootstrap_tenant(
            client, company_name="Reach Co", email="admin@reach-co.com", password="reach-pass1"
        )
        admin = {"X-API-Key": data["plain_text_api_key"]}
        seq = {"n": 0}

        def key_holding(*permissions: str, employee_id: str | None = None) -> dict:
            seq["n"] += 1
            role = f"role{seq['n']}"
            client.post("/api/v1/roles", json={"name": role, "permissions": list(permissions)},
                        headers=admin)
            body = {"email": f"u{seq['n']}@reach-co.com", "role": role}
            if employee_id:
                body["employee_id"] = employee_id
            user_id = client.post("/api/v1/auth/invitations", json=body, headers=admin).json()["data"]["id"]
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"})
            plain = client.post("/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id},
                                headers=admin).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": plain}

        def upload(headers: dict, body: bytes, name: str) -> str:
            r = client.post("/api/v1/attachments", json={
                "filename": name, "content_type": "application/pdf",
                "content_base64": base64.b64encode(body).decode()}, headers=headers)
            assert r.status_code in (200, 201), r.text
            return r.json()["data"]["id"]

        alice = client.post("/api/v1/employees", json={"name": "Alice"},
                            headers=admin).json()["data"]["id"]

        # a payslip, with the payslip PDF attached
        payslip_pdf = upload(admin, b"%PDF net pay 42000", "payslip.pdf")
        payslip = client.post("/api/v1/invoices", json={
            "direction": "payroll", "employee_id": alice, "payee_employee_id": alice,
            "title": "2026-07 工资条", "period_start": "2026-07-01", "period_end": "2026-07-31",
            "attachment_id": payslip_pdf,
            "items": [{"invoice_item_type": "payroll_salary",
                       "product_name_snapshot": "基本工资", "amount": 42000,
                       "notes": "月薪 42000.00"}]}, headers=admin)
        assert payslip.status_code == 201, payslip.text

        # an expense claim with a receipt — the approver's normal case
        receipt_pdf = upload(admin, b"%PDF taxi 88", "receipt.pdf")
        claim = client.post("/api/v1/expense-claims", json={
            "employee_id": alice, "title": "差旅", "items": [
                {"expense_date": "2026-07-02", "amount": 88, "category": "transport",
                 "attachment_id": receipt_pdf}]}, headers=admin).json()["data"]

        # a SECOND claim, whose receipt the first claim must never serve
        other_pdf = upload(admin, b"%PDF hotel 1200", "hotel.pdf")
        other_claim_r = client.post("/api/v1/expense-claims", json={
            "employee_id": alice, "title": "住宿", "items": [
                {"expense_date": "2026-07-03", "amount": 1200, "category": "lodging",
                 "attachment_id": other_pdf}]}, headers=admin)
        assert other_claim_r.status_code == 201, other_claim_r.text
        other_claim = other_claim_r.json()["data"]

        # a payout settling the payslip, carrying its own remittance file
        remittance_pdf = upload(admin, b"%PDF remittance 42000", "remittance.pdf")
        payment = client.post("/api/v1/payments", json={
            "direction": "outbound", "employee_id": alice, "payee_employee_id": alice,
            "amount": 42000,
            "payment_date": "2026-08-05", "attachment_id": remittance_pdf}, headers=admin)
        assert payment.status_code == 201, payment.text

        # a DRAFT policy — visible only to policy.manage, and so is its file
        policy_pdf = upload(admin, b"%PDF draft handbook", "handbook.pdf")
        policy = client.post("/api/v1/policies", json={
            "code": "HR-001", "title": "员工手册", "category": "hr", "body": "draft text",
            "attachment_id": policy_pdf}, headers=admin)
        assert policy.status_code == 201, policy.text

        yield {
            "client": client, "admin": admin, "key_holding": key_holding,
            "payslip_id": payslip.json()["data"]["id"], "payslip_pdf": payslip_pdf,
            "claim_id": claim["id"], "receipt_pdf": receipt_pdf,
            "other_claim_id": other_claim["id"], "other_pdf": other_pdf,
            "payment_id": payment.json()["data"]["id"], "remittance_pdf": remittance_pdf,
            "policy_id": policy.json()["data"]["id"], "policy_pdf": policy_pdf,
        }


# --- the registry stays honest ---------------------------------------------


def test_every_attachment_backed_model_is_reachable_through_a_document() -> None:
    """A family whose attachments no document can serve is a family whose
    evidence is write-only — and the tempting fix for that is to reopen the
    id-based route for everyone."""
    backed = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if mapper.local_table is not None and "attachment_id" in mapper.local_table.c
    }
    reachable = set()
    for document, (item_model, _) in ATTACHMENT_SOURCES.items():
        reachable.add((item_model or document).__name__)
    assert backed == reachable, (
        f"attachment-backed but unreachable: {sorted(backed - reachable)}; "
        f"registered but no longer attachment-backed: {sorted(reachable - backed)}"
    )


def test_each_registered_family_has_a_route() -> None:
    from app.main import app

    # the admin-only id route ends the same way, so match on the nesting
    nested = {
        p for p in app.openapi()["paths"]
        if p.endswith("/attachments/{attachment_id}/content")
        and p != "/api/v1/attachments/{attachment_id}/content"
    }
    assert len(nested) == len(ATTACHMENT_SOURCES), sorted(nested)


# --- the hole that motivated this ------------------------------------------


def test_a_payroll_blind_credential_cannot_read_a_payslip_pdf_by_id(world) -> None:
    """The reported hole, from the caller's side."""
    clerk = world["key_holding"]("invoice.manage:sales")
    got = world["client"].get(
        f"/api/v1/attachments/{world['payslip_pdf']}/content", headers=clerk
    )
    assert got.status_code == 403, got.text


def test_a_payroll_blind_credential_cannot_read_a_payslip_pdf_through_the_invoice(world) -> None:
    """…and from the document side, where it must 404 rather than 403: naming
    it would confirm this person has a payslip for this period, which is most
    of what the gate protects."""
    clerk = world["key_holding"]("invoice.manage:sales")
    got = world["client"].get(
        f"/api/v1/invoices/{world['payslip_id']}/attachments/{world['payslip_pdf']}/content",
        headers=clerk,
    )
    assert got.status_code == 404, got.text


def test_payroll_read_reaches_the_payslip_pdf(world) -> None:
    """The gate must not be a wall: whoever may see the payslip may see its
    file."""
    hr = world["key_holding"]("payroll.read", "invoice.manage:payroll")
    got = world["client"].get(
        f"/api/v1/invoices/{world['payslip_id']}/attachments/{world['payslip_pdf']}/content",
        headers=hr,
    )
    assert got.status_code == 200, got.text
    assert got.content == b"%PDF net pay 42000"


# --- the approver's path, which must keep working --------------------------


def test_an_approver_reads_the_receipt_through_the_claim(world) -> None:
    """`$oryh-approve` tells every approver to open each receipt before
    deciding. Closing the id route without this would have made approving an
    expense claim impossible to do properly."""
    approver = world["key_holding"]("approval.record")
    got = world["client"].get(
        f"/api/v1/expense-claims/{world['claim_id']}/attachments/{world['receipt_pdf']}/content",
        headers=approver,
    )
    assert got.status_code == 200, got.text
    assert got.content == b"%PDF taxi 88"


# --- naming a document you may read does not open the others ---------------


def test_naming_the_wrong_document_does_not_serve_the_attachment(world) -> None:
    """The claim is readable by this approver and the payslip's PDF is not
    part of it — an attachment must belong to the document that vouches for
    it, or the nesting is decoration."""
    approver = world["key_holding"]("approval.record")
    got = world["client"].get(
        f"/api/v1/expense-claims/{world['claim_id']}/attachments/{world['payslip_pdf']}/content",
        headers=approver,
    )
    assert got.status_code == 404, got.text


def test_a_real_id_and_a_bogus_id_read_the_same(world) -> None:
    """Otherwise the endpoint is an oracle for which attachments exist."""
    approver = world["key_holding"]("approval.record")
    unrelated = world["client"].get(
        f"/api/v1/expense-claims/{world['claim_id']}/attachments/{world['payslip_pdf']}/content",
        headers=approver,
    ).status_code
    nonexistent = world["client"].get(
        f"/api/v1/expense-claims/{world['claim_id']}/attachments/"
        "00000000-0000-0000-0000-000000000000/content",
        headers=approver,
    ).status_code
    assert unrelated == nonexistent == 404


# --- the id route is the administrator's ------------------------------------


def test_the_admin_still_reads_by_id(world) -> None:
    got = world["client"].get(
        f"/api/v1/attachments/{world['payslip_pdf']}/content", headers=world["admin"]
    )
    assert got.status_code == 200, got.text


def test_an_ordinary_member_cannot_read_by_id(world) -> None:
    member = world["key_holding"]("expense.submit_own", "approval.record")
    got = world["client"].get(
        f"/api/v1/attachments/{world['receipt_pdf']}/content", headers=member
    )
    assert got.status_code == 403, got.text


def test_one_claim_does_not_serve_another_claims_receipt(world) -> None:
    """The leak the cross-FAMILY case cannot catch.

    Dropping the parent filter makes the lookup return every attachment id in
    the family, so any claim would serve any other's receipts — one employee's
    evidence through another employee's claim. A test that reaches for a
    payslip through a claim never notices: a payslip hangs off an invoice
    header, so it is absent from the expense-item set either way.
    """
    approver = world["key_holding"]("approval.record")
    got = world["client"].get(
        f"/api/v1/expense-claims/{world['claim_id']}/attachments/{world['other_pdf']}/content",
        headers=approver,
    )
    assert got.status_code == 404, got.text
    # …and the claim that DOES carry it still serves it
    own = world["client"].get(
        f"/api/v1/expense-claims/{world['other_claim_id']}/attachments/{world['other_pdf']}/content",
        headers=approver,
    )
    assert own.status_code == 200, own.text


def test_a_payroll_blind_credential_cannot_read_a_payout_file(world) -> None:
    """A payout naming an employee as payee carries their net pay, and its
    attachment is the remittance advice that states it."""
    clerk = world["key_holding"]("invoice.manage:sales")
    got = world["client"].get(
        f"/api/v1/payments/{world['payment_id']}/attachments/{world['remittance_pdf']}/content",
        headers=clerk,
    )
    assert got.status_code == 404, got.text

    cashier = world["key_holding"]("payroll.read", "payment.record")
    assert world["client"].get(
        f"/api/v1/payments/{world['payment_id']}/attachments/{world['remittance_pdf']}/content",
        headers=cashier,
    ).status_code == 200


def test_a_draft_policys_file_follows_the_draft(world) -> None:
    """`policy.manage` widens a read: drafts are visible only to holders. The
    attached handbook is the draft."""
    member = world["key_holding"]("expense.submit_own")
    got = world["client"].get(
        f"/api/v1/policies/{world['policy_id']}/attachments/{world['policy_pdf']}/content",
        headers=member,
    )
    assert got.status_code == 404, got.text

    owner = world["key_holding"]("policy.manage")
    assert world["client"].get(
        f"/api/v1/policies/{world['policy_id']}/attachments/{world['policy_pdf']}/content",
        headers=owner,
    ).status_code == 200


def test_the_console_links_at_routes_the_api_actually_serves() -> None:
    """The console builds these URLs by hand in TypeScript.

    Nothing connected the two before: a renamed collection would leave every
    download button pointing at a 404, and no test on either side would notice
    — the console's own tests assert the string it built, not that anything
    answers there.
    """
    import pathlib
    import re

    from app.main import app

    source = (pathlib.Path(__file__).resolve().parents[1]
              / "frontend/src/api/objects.ts").read_text(encoding="utf-8")
    block = re.search(r"const ATTACHMENT_COLLECTIONS[^=]*=\s*\{(.*?)\n\};", source, re.S)
    assert block, "the console no longer declares ATTACHMENT_COLLECTIONS"
    collections = dict(re.findall(r"(\w+):\s*\"([a-z-]+)\"", block.group(1)))
    assert collections, "no collections parsed — the regex has drifted from the source"

    served = set(app.openapi()["paths"])
    for entity_type, collection in sorted(collections.items()):
        matches = [
            p for p in served
            if p.startswith(f"/api/v1/{collection}/{{")
            and p.endswith("/attachments/{attachment_id}/content")
        ]
        assert matches, (
            f"the console links {entity_type} downloads at /{collection}/…/attachments/…"
            " and the API serves no such route"
        )


def test_the_refusal_names_the_route_not_a_capability(world) -> None:
    """An approver on a pre-release skill bundle calls the old URL and reads
    this message. If it said "requires capability users.manage" they would ask
    their admin for administrator rights and probably get them — a worse
    outcome than the hole this closed.
    """
    member = world["key_holding"]("approval.record")
    got = world["client"].get(
        f"/api/v1/attachments/{world['receipt_pdf']}/content", headers=member
    )
    assert got.status_code == 403
    detail = got.json()["detail"]
    assert "users.manage" not in detail, "the message must not read as a capability to request"
    assert "/attachments/{attachment_id}/content" in detail, "it must name the route to use"
