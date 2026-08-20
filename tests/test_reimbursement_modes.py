"""How much ceremony a reimbursement gets is the workspace's decision.

Three ways a company pays an approved claim, all legitimate:

1. **Bill it.** Raise the claim's reimbursement invoice, pay that. An AP
   sub-ledger, aging, one posting rule per document — what a company with a
   general ledger wants.
2. **Pay it.** Apply the payout to the claim itself. Fewer documents, same
   money, same guards.
3. **Neither.** ORYH holds the approval; the payout happens in a bank portal
   or another system entirely.

The server picks none of these. What it enforces is that ONE claim does not
take both of the first two, because the claim and its invoice keep separate
running totals: 1300 against each and the employee has 2600, with both
documents reporting themselves correctly settled. Neither the over-application
guard nor the counterparty guard can see it — each looks at one document.

The exclusion is decided by whichever route the claim takes first, and each
refusal names the other route rather than the rule.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


@pytest.fixture()
def shop(client: TestClient):
    t = provision_tenant(client, company_name="Modes Co", email="admin@modes.example")
    headers = {"X-API-Key": t["plain_text_api_key"]}

    def post(path, body, expect=(200, 201)):
        r = client.post(f"/api/v1{path}", json=body, headers=headers)
        assert r.status_code in expect, f"{path} -> {r.status_code} {r.text[:300]}"
        return r.json()["data"]

    employee = post("/employees", {"name": "Li"})["id"]

    def approved_claim(amount=800.0):
        claim = post("/expense-claims", {
            "employee_id": employee, "title": "July travel",
            "items": [{"expense_date": "2026-07-18", "amount": amount,
                       "category": "transport"}]})
        client.post(f"/api/v1/expense-claims/{claim['id']}/submit", json={}, headers=headers)
        client.post("/api/v1/approval-records", headers=headers, json={
            "entity_type": "expense_claim", "entity_id": claim["id"], "action": "approved",
            "approver_id": "mgr", "approver_role": "manager", "source": "ai",
            "sequence_no": 2})
        client.patch(f"/api/v1/expense-claims/{claim['id']}", json={"status": "approved"},
                     headers=headers)
        return claim

    def payout(amount=800.0):
        return post("/payments", {
            "direction": "outbound", "employee_id": employee, "payee_employee_id": employee,
            "amount": amount, "payment_date": "2026-07-25"})

    def apply_to(payment_id, target_type, target_id, amount):
        return client.post(f"/api/v1/payments/{payment_id}/apply", headers=headers,
                           json={"lines": [{"applied_to_type": target_type,
                                            "applied_to_id": target_id,
                                            "amount_applied": amount}]})

    return {"client": client, "headers": headers, "post": post, "employee": employee,
            "approved_claim": approved_claim, "payout": payout, "apply_to": apply_to,
            "raise_invoice": lambda cid: client.post(
                f"/api/v1/expense-claims/{cid}/invoice", headers=headers)}


# --- mode 1: bill it --------------------------------------------------------


def test_a_workspace_that_bills_pays_the_invoice(shop) -> None:
    claim = shop["approved_claim"]()
    invoice = shop["raise_invoice"](claim["id"])
    assert invoice.status_code == 201, invoice.text

    settled = shop["apply_to"](shop["payout"]()["id"], "invoice",
                               invoice.json()["data"]["id"], 800.0)
    assert settled.status_code in (200, 201), settled.text
    assert settled.json()["data"]["targets"][0]["outstanding_amount"] == 0.0


# --- mode 2: pay it ---------------------------------------------------------


def test_a_workspace_that_does_not_bill_pays_the_claim(shop) -> None:
    """No invoice anywhere. This is the route the previous release removed,
    and removing it decided a question that belongs to the tenant."""
    claim = shop["approved_claim"]()
    settled = shop["apply_to"](shop["payout"]()["id"], "expense_claim", claim["id"], 800.0)
    assert settled.status_code in (200, 201), settled.text
    assert settled.json()["data"]["targets"][0]["outstanding_amount"] == 0.0

    listed = shop["client"].get(f"/api/v1/invoices?expense_claim_id={claim['id']}",
                                headers=shop["headers"]).json()["data"]
    assert listed == [], "paying directly must not conjure an invoice"


# --- mode 3: neither --------------------------------------------------------


def test_a_workspace_that_pays_elsewhere_leaves_both_alone(shop) -> None:
    """ORYH holds the approval; the money moves in a bank portal. Nothing here
    should require a payment to exist for the claim to be complete."""
    claim = shop["approved_claim"]()
    detail = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}/detail",
                                headers=shop["headers"]).json()["data"]
    assert detail["invoices"] == []
    assert detail["uninvoiced_amount"] == 800.0

    moved = shop["client"].patch(f"/api/v1/expense-claims/{claim['id']}",
                                 json={"status": "paid"}, headers=shop["headers"])
    assert moved.status_code == 200, moved.text


# --- the one thing the server does enforce ---------------------------------


def test_a_billed_claim_is_not_also_paid_directly(shop) -> None:
    claim = shop["approved_claim"]()
    invoice = shop["raise_invoice"](claim["id"]).json()["data"]

    refused = shop["apply_to"](shop["payout"]()["id"], "expense_claim", claim["id"], 800.0)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert invoice["invoice_no"] in detail, detail
    assert "apply the payment to that invoice instead" in detail


def test_a_directly_paid_claim_is_not_also_billed(shop) -> None:
    """The reverse, and the half that is easy to forget: without it a workspace
    could pay the claim, then bill it, then pay the bill."""
    claim = shop["approved_claim"]()
    shop["apply_to"](shop["payout"]()["id"], "expense_claim", claim["id"], 800.0)

    refused = shop["raise_invoice"](claim["id"])
    assert refused.status_code == 409, refused.text
    assert "already been paid against this claim directly" in refused.json()["detail"]


def test_reversing_the_direct_payment_reopens_the_billed_route(shop) -> None:
    """The exclusion is about live money, not a one-way door. A workspace that
    settled the wrong way can reverse and switch."""
    claim = shop["approved_claim"]()
    payment = shop["payout"]()
    shop["apply_to"](payment["id"], "expense_claim", claim["id"], 800.0)
    assert shop["raise_invoice"](claim["id"]).status_code == 409

    shop["apply_to"](payment["id"], "expense_claim", claim["id"], -800.0)
    assert shop["raise_invoice"](claim["id"]).status_code == 201


def test_deleting_the_invoice_reopens_the_direct_route(shop) -> None:
    """A workspace that billed by mistake deletes the invoice and pays
    directly. The precondition looks at LIVE invoices — a mutation that
    dropped `deleted_at IS NULL` left this claim permanently unpayable by
    either route, and nothing said so."""
    claim = shop["approved_claim"]()
    invoice = shop["raise_invoice"](claim["id"]).json()["data"]
    assert shop["apply_to"](shop["payout"]()["id"], "expense_claim",
                            claim["id"], 800.0).status_code == 409

    gone = shop["client"].delete(f"/api/v1/invoices/{invoice['id']}", headers=shop["headers"])
    assert gone.status_code == 204, gone.text

    settled = shop["apply_to"](shop["payout"]()["id"], "expense_claim", claim["id"], 800.0)
    assert settled.status_code in (200, 201), settled.text


def test_the_admin_switches_the_mode_in_one_sentence(shop) -> None:
    """The acceptance criterion for this whole family: a tenant admin says a
    few words to their agent, and the workspace's settlement route changes.
    No configuration surface, no deploy.

    Their agent's move (rule 5a of $oryh-skill-author) is one PATCH to the
    calibration on $oryh-payables. The payables agent's move (step 0) is to
    read the "Workspace calibration" section of its own bundle. This test is
    the wire between those two sentences.
    """
    import io
    import zipfile

    client, headers = shop["client"], shop["headers"]

    def payables_text() -> str:
        bundle = client.get("/api/v1/my/skill-bundle", headers=headers)
        assert bundle.status_code == 200, bundle.text
        archive = zipfile.ZipFile(io.BytesIO(bundle.content))
        path = next(n for n in archive.namelist() if n.endswith("-payables/SKILL.md"))
        return archive.read(path).decode("utf-8")

    def set_mode(sentence: str) -> dict:
        r = client.patch("/api/v1/skills/oryh-payables",
                         json={"calibration": sentence}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["data"]

    # the admin's first ruling: the light route
    direct = "报销审批通过后直接核销报销单，不开 reimbursement 发票。"
    first = set_mode(direct)
    assert first["kind"] == "product", "one sentence must not fork the skill"

    rendered = payables_text()
    assert direct in rendered
    # the refinement reads AFTER the rule it refines: step 0 sends the agent
    # to this section, so the section must exist below that instruction
    assert rendered.index(direct) > rendered.index("Ask which route this workspace takes")
    # …and step 0 must keep SAYING so. The calibration section is inert if the
    # skill stops pointing the agent at it.
    assert '"Workspace calibration" section at the bottom of this skill' in rendered

    # the company grows a ledger; the admin changes their mind in one sentence
    billed = "报销一律先开 reimbursement 发票，付款核销发票。"
    second = set_mode(billed)
    assert second["version"] == first["version"] + 1, (
        "the version bump is the stale signal — without it every installed "
        "copy keeps paying the old way"
    )
    rendered = payables_text()
    assert billed in rendered
    assert direct not in rendered, "the old ruling must not linger beside the new one"
