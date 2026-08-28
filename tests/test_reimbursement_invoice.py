"""An approved expense claim becomes a payable to the EMPLOYEE.

The company never owed the merchant who issued the receipt — the employee paid
them, out of their own pocket, at the hotel desk. So a reimbursement is not a
purchase invoice against a vendor, and the counterparty guard refuses that
shape outright: a payout to the employee cannot settle a bill that names the
hotel.

`reimbursement` is therefore a fourth direction whose counterparty is
`payee_employee_id`, the same shape payroll uses. It is not payroll — no
one-per-period rule, no `payroll.read` gate — but it shares the property that
makes settlement trustworthy: the party who gets paid is the party named on
the document.

Raising it is an explicit call, not a side effect of approval. Nothing in this
API invents a document when a status changes, and a flow agent moving a claim
to `approved` holds no capability to file a payable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import provision_tenant


@pytest.fixture()
def shop(client: TestClient):
    t = provision_tenant(client, company_name="Reim Co", email="admin@reim-co.example")
    headers = {"X-API-Key": t["plain_text_api_key"]}

    def post(path, body, expect=(200, 201)):
        r = client.post(f"/api/v1{path}", json=body, headers=headers)
        assert r.status_code in expect, f"{path} -> {r.status_code} {r.text[:300]}"
        return r.json()["data"]

    def approve(claim_id):
        client.post(f"/api/v1/expense-claims/{claim_id}/submit", json={}, headers=headers)
        client.post("/api/v1/approval-records", headers=headers, json={
            "entity_type": "expense_claim", "entity_id": claim_id, "action": "approved",
            "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
        r = client.patch(f"/api/v1/expense-claims/{claim_id}",
                         json={"status": "approved"}, headers=headers)
        assert r.status_code == 200, r.text

    employee = post("/employees", {"name": "Li"})["id"]

    def claim(amount=1300.0, **over):
        body = {"employee_id": employee, "title": "July travel", "claim_date": "2026-07-20",
                "items": [{"expense_date": "2026-07-18", "amount": 480.0, "category": "transport",
                           "merchant": "City Cabs"},
                          {"expense_date": "2026-07-19", "amount": amount - 480.0,
                           "category": "lodging", "merchant": "Hotel Ltd", "tax_amount": 45.28}]}
        body.update(over)
        return post("/expense-claims", body)

    return {"client": client, "headers": headers, "post": post, "approve": approve,
            "employee": employee, "claim": claim}


def raise_invoice(shop, claim_id):
    return shop["client"].post(f"/api/v1/expense-claims/{claim_id}/invoice",
                               headers=shop["headers"])


def test_the_invoice_names_the_employee_not_the_merchant(shop) -> None:
    """The whole point. `Hotel Ltd` appears on the line as the merchant and
    nowhere as a counterparty."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])

    raised = raise_invoice(shop, claim["id"])
    assert raised.status_code == 201, raised.text
    invoice = raised.json()["data"]

    assert invoice["direction"] == "reimbursement"
    # live on arrival: the spending was approved on the claim, and a second
    # approval round would ask someone to re-decide it without the evidence
    assert invoice["status"] == "issued"
    assert invoice["issued_at"] is not None
    assert invoice["payee_employee_id"] == shop["employee"]
    assert invoice["vendor_id"] is None
    assert invoice["customer_id"] is None
    assert invoice["expense_claim_id"] == claim["id"]


def test_the_lines_carry_over_with_their_category_and_tax(shop) -> None:
    """A ledger reaches the expense account through the category, and the tax
    is what makes input VAT recoverable in the markets that allow it."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]

    detail = shop["client"].get(f"/api/v1/invoices/{invoice['id']}/detail",
                                headers=shop["headers"]).json()["data"]
    types = {item["invoice_item_type"] for item in detail["items"]}
    assert types == {"transport", "lodging"}
    assert detail["computed_total"] == 1300.0
    assert detail["computed_tax_total"] == 45.28


def test_a_second_call_bills_nothing_and_says_what_covers_it(shop) -> None:
    """A retry lands here, and so does a second attempt at a fully billed
    claim. Refusing is the safe outcome either way — the alternative is
    reimbursing the same taxi twice — and naming the invoices tells the two
    apart without another call."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])

    first = raise_invoice(shop, claim["id"])
    assert first.status_code == 201
    second = raise_invoice(shop, claim["id"])
    assert second.status_code == 409, second.text
    assert first.json()["data"]["invoice_no"] in second.json()["detail"]


def test_a_claim_may_be_billed_in_instalments(shop) -> None:
    """The rule that replaced one-invoice-per-claim. A line added after the
    first invoice is billed by the second, and the first is untouched."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    first = raise_invoice(shop, claim["id"]).json()["data"]

    # a line appears later — a receipt that surfaced after approval, or a
    # disputed one released once settled
    from app.models import ExpenseItem
    with shop["client"].session_factory() as db:
        db.add(ExpenseItem(
            tenant_id=db.scalar(__import__("sqlalchemy").select(ExpenseItem.tenant_id)
                                .where(ExpenseItem.claim_id == claim["id"]).limit(1)),
            claim_id=claim["id"], employee_id=shop["employee"],
            expense_date=__import__("datetime").date(2026, 7, 20),
            category="meal", amount=90.0))
        db.commit()

    second = raise_invoice(shop, claim["id"])
    assert second.status_code == 201, second.text
    assert second.json()["data"]["id"] != first["id"]

    detail = shop["client"].get(f"/api/v1/invoices/{second.json()['data']['id']}/detail",
                                headers=shop["headers"]).json()["data"]
    assert detail["computed_total"] == 90.0, "the second invoice bills only the new line"

    unchanged = shop["client"].get(f"/api/v1/invoices/{first['id']}/detail",
                                   headers=shop["headers"]).json()["data"]
    assert unchanged["computed_total"] == 1300.0


def test_an_editable_claim_is_a_moving_target(shop) -> None:
    """Its lines are what the invoice bills; billing a document somebody is
    still editing is how the two come to disagree."""
    claim = shop["claim"]()
    refused = raise_invoice(shop, claim["id"])
    assert refused.status_code == 409, refused.text
    assert "still editable" in refused.json()["detail"]


def test_the_payout_settles_it(shop) -> None:
    """End to end: the counterparty guard passes because both sides name the
    same employee — which is exactly what the merchant-invoice design could
    not do."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]

    payout = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "amount": 1300.0,
        "payment_date": "2026-07-25"})
    applied = shop["client"].post(
        f"/api/v1/payments/{payout['id']}/apply", headers=shop["headers"],
        json={"idempotency_key": "reim-1",
              "lines": [{"applied_to_type": "invoice", "applied_to_id": invoice["id"],
                         "amount_applied": 1300.0}]})
    assert applied.status_code in (200, 201), applied.text
    assert applied.json()["data"]["targets"][0]["outstanding_amount"] == 0.0


def test_a_reimbursement_is_not_a_payslip(shop) -> None:
    """It shares payroll's counterparty column and nothing else: no
    one-per-period rule, and no `payroll.read` gate hiding it."""
    for _ in range(2):
        claim = shop["claim"]()
        shop["approve"](claim["id"])
        assert raise_invoice(shop, claim["id"]).status_code == 201

    listed = shop["client"].get("/api/v1/invoices?direction=reimbursement",
                                headers=shop["headers"]).json()["data"]
    assert len(listed) == 2, "two reimbursements for one employee must both stand"


def test_raising_it_takes_the_capability(client: TestClient) -> None:
    """The fixture above drives a service key, which bypasses the permission
    layer by design — so every test there would pass with the gate deleted. A
    mutation run said exactly that.

    `invoice.manage:reimbursement` and not the bare verb: a workspace that
    keeps 应收 and 应付 apart scopes this the same way, and an AR clerk holding
    only `:sales` has no business filing a payable to an employee.
    """
    from app.services.emails import outbox
    from conftest import provision_tenant as bootstrap

    data = bootstrap(client, company_name="Gate Co", email="admin@gate-co.example")
    admin = {"X-API-Key": data["plain_text_api_key"]}

    def key_holding(role: str, *permissions: str) -> dict:
        client.post("/api/v1/roles", json={"name": role, "permissions": list(permissions)},
                    headers=admin)
        uid = client.post("/api/v1/auth/invitations",
                          json={"email": f"{role}@gate-co.example", "role": role},
                          headers=admin).json()["data"]["id"]
        token = next(l.rsplit("token=", 1)[1].strip()
                     for l in outbox.messages[-1].body.splitlines() if "token=" in l)
        client.post("/api/v1/auth/invitations/accept",
                    json={"token": token, "password": "invitee-pass1"})
        plain = client.post("/api/v1/tenant/api-keys", json={"label": role, "user_id": uid},
                            headers=admin).json()["data"]["plain_text_api_key"]
        return {"X-API-Key": plain}

    emp = client.post("/api/v1/employees", json={"name": "Li"}, headers=admin).json()["data"]["id"]
    claim = client.post("/api/v1/expense-claims", headers=admin, json={
        "employee_id": emp, "title": "July travel",
        "items": [{"expense_date": "2026-07-18", "amount": 300.0, "category": "transport"}]},
    ).json()["data"]
    client.post(f"/api/v1/expense-claims/{claim['id']}/submit", json={}, headers=admin)
    client.post("/api/v1/approval-records", headers=admin, json={
        "entity_type": "expense_claim", "entity_id": claim["id"], "action": "approved",
        "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
    client.patch(f"/api/v1/expense-claims/{claim['id']}", json={"status": "approved"},
                 headers=admin)

    ar_only = key_holding("ar_clerk", "invoice.manage:sales")
    refused = client.post(f"/api/v1/expense-claims/{claim['id']}/invoice", headers=ar_only)
    assert refused.status_code == 403, refused.text
    assert "invoice.manage:reimbursement" in refused.json()["detail"]

    ap = key_holding("ap_clerk", "invoice.manage:reimbursement")
    assert client.post(f"/api/v1/expense-claims/{claim['id']}/invoice",
                       headers=ap).status_code == 201


def test_it_is_settleable_the_moment_it_exists(shop) -> None:
    """Why `issued` and not `draft` is more than tidiness.

    Settlement has no status gate — nothing stops a payment being applied to a
    draft. So a reimbursement invoice created as a draft would have been money
    moving against a payable nobody had asserted, and the only thing standing
    between the two was that a draft LOOKS unfinished.
    """
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]
    assert invoice["status"] == "issued"

    payout = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "amount": 1300.0,
        "payment_date": "2026-07-25"})
    settled = shop["client"].post(
        f"/api/v1/payments/{payout['id']}/apply", headers=shop["headers"],
        json={"lines": [{"applied_to_type": "invoice", "applied_to_id": invoice["id"],
                         "amount_applied": 1300.0}]})
    assert settled.status_code in (200, 201), settled.text
    # …and it may go on to `paid`, which `draft` could not have done without
    # first being submitted and approved
    moved = shop["client"].patch(f"/api/v1/invoices/{invoice['id']}",
                                 json={"status": "paid"}, headers=shop["headers"])
    assert moved.status_code == 200, moved.text


def test_a_workspace_without_that_state_is_told_which_one(client: TestClient) -> None:
    """The state names are the tenant's — including the one the reimbursement
    invoice arrives in. A machine that drops `issued` without saying where the
    role went is refused at save time with the exact `roles` entry to add; one
    that declares it gets invoices in its own vocabulary.
    """
    from conftest import provision_tenant as bootstrap

    data = bootstrap(client, company_name="NoIssued Co", email="admin@noissued.example")
    headers = {"X-API-Key": data["plain_text_api_key"]}

    existing = client.get(
        "/api/v1/object-type-definitions?entity_kind=builtin&object_type=invoice",
        headers=headers).json()["data"]
    machine = {
            "initial": "draft",
            "states": ["draft", "submitted", "settled", "void"],
            "transitions": {"draft": ["submitted", "void"], "submitted": ["settled", "void"],
                            "settled": [], "void": []},
    }
    def save(m):
        if existing:
            return client.patch(
                f"/api/v1/object-type-definitions/{existing[0]['id']}",
                json={"state_machine": m}, headers=headers)
        return client.post("/api/v1/object-type-definitions", headers=headers, json={
            "entity_kind": "builtin", "object_type": "invoice", "json_schema": {},
            "state_machine": m})

    # without a roles entry the machine is refused AT SAVE TIME — better than
    # the earlier behavior, which let it save and failed the invoice raise
    refused = save(machine)
    assert refused.status_code == 422, refused.text
    assert '"roles"' in refused.json()["detail"] and "issued" in refused.json()["detail"]

    # the taught fix: this workspace's word for the issued role is `settled`
    machine["roles"] = {"issued": "settled"}
    reshaped = save(machine)
    assert reshaped.status_code in (200, 201), reshaped.text

    emp = client.post("/api/v1/employees", json={"name": "Li"},
                      headers=headers).json()["data"]["id"]
    claim = client.post("/api/v1/expense-claims", headers=headers, json={
        "employee_id": emp, "title": "July travel",
        "items": [{"expense_date": "2026-07-18", "amount": 300.0, "category": "transport"}]},
    ).json()["data"]
    client.post(f"/api/v1/expense-claims/{claim['id']}/submit", json={}, headers=headers)
    client.post("/api/v1/approval-records", headers=headers, json={
        "entity_type": "expense_claim", "entity_id": claim["id"], "action": "approved",
        "approver_id": "mgr", "approver_role": "manager", "source": "ai", "sequence_no": 2})
    client.patch(f"/api/v1/expense-claims/{claim['id']}", json={"status": "approved"},
                 headers=headers)

    raised = client.post(f"/api/v1/expense-claims/{claim['id']}/invoice", headers=headers)
    assert raised.status_code == 201, raised.text
    assert raised.json()["data"]["status"] == "settled", (
        "the reimbursement invoice arrives in the WORKSPACE's word for issued"
    )


def test_the_claim_reports_its_invoices_and_what_is_unbilled(shop) -> None:
    """The two-way link, from the claim's side.

    Nothing is stored on the claim: a stored list drifts the moment an invoice
    is voided and a stored total drifts the moment a line is added. And the
    claim's own `applied_amount` stays zero forever now that money reaches it
    through the invoices — so these are the numbers to route on, never the
    status.
    """
    claim = shop["claim"]()
    shop["approve"](claim["id"])

    before = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}/detail",
                                headers=shop["headers"]).json()["data"]
    assert before["invoices"] == []
    assert before["invoiced_amount"] == 0.0
    assert before["uninvoiced_amount"] == 1300.0

    invoice = raise_invoice(shop, claim["id"]).json()["data"]
    after = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}/detail",
                               headers=shop["headers"]).json()["data"]
    assert [i["invoice_no"] for i in after["invoices"]] == [invoice["invoice_no"]]
    assert after["invoiced_amount"] == 1300.0
    assert after["uninvoiced_amount"] == 0.0
    assert after["invoices"][0]["outstanding_amount"] == 1300.0

    payout = shop["post"]("/payments", {
        "direction": "outbound", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "amount": 1300.0,
        "payment_date": "2026-07-25"})
    shop["client"].post(f"/api/v1/payments/{payout['id']}/apply", headers=shop["headers"],
                        json={"lines": [{"applied_to_type": "invoice",
                                         "applied_to_id": invoice["id"],
                                         "amount_applied": 1300.0}]})
    settled = shop["client"].get(f"/api/v1/expense-claims/{claim['id']}/detail",
                                 headers=shop["headers"]).json()["data"]
    assert settled["invoices"][0]["outstanding_amount"] == 0.0
    # the claim's own applied_amount never moved, which is why the invoice
    # figures are the ones worth reading
    assert float(settled["claim"].get("applied_amount") or 0) == 0.0


def test_the_invoice_names_the_claim_it_came_from(shop) -> None:
    """And from the invoice's side — one field, so the chain is followable in
    either direction without a join table."""
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]
    assert invoice["expense_claim_id"] == claim["id"]

    listed = shop["client"].get(f"/api/v1/invoices?expense_claim_id={claim['id']}",
                                headers=shop["headers"])
    assert listed.status_code == 200, listed.text
    assert [i["id"] for i in listed.json()["data"]] == [invoice["id"]]


def test_the_database_refuses_a_line_billed_twice(shop) -> None:
    """The backstop under the API filter.

    `raise_reimbursement_invoice` skips lines already billed, so the unique
    index never fires through the endpoint — which is exactly why a mutation
    that disabled the index changed nothing. It is there for what the filter
    cannot see: two calls racing, an import, a direct write. Same reason
    `invoices_payroll_period_uk` exists rather than trusting the agent not to
    issue two payslips.
    """
    import sqlalchemy
    from sqlalchemy.exc import IntegrityError

    from app.models import ExpenseItem, InvoiceItem

    claim = shop["claim"]()
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]

    with shop["client"].session_factory() as db:
        billed = db.scalar(
            sqlalchemy.select(InvoiceItem).where(InvoiceItem.invoice_id == invoice["id"]).limit(1)
        )
        assert billed.expense_item_id is not None
        item = db.get(ExpenseItem, billed.expense_item_id)
        db.add(InvoiceItem(
            tenant_id=item.tenant_id,
            invoice_id=invoice["id"],
            line_no=99,
            invoice_item_type=item.category,
            expense_item_id=item.id,        # the same expense line, a second time
            amount=item.amount,
        ))
        with pytest.raises(IntegrityError):
            db.commit()


def test_the_invoice_states_its_total_rather_than_leaving_it_derived(shop) -> None:
    """`null` means "the line sum is the total" — a real contract, honoured by
    settlement, so the money was never wrong. The reader was: an invoice list
    renders the header total, and a reimbursement showed a dash where every
    other invoice shows an amount.

    Payroll refuses a declared total on purpose (net pay must be derived,
    because +2000 and -2000 are the same number until you read the sign).
    Reimbursement is the opposite: every line is a positive expense and the
    figure was agreed when the claim was approved.
    """
    claim = shop["claim"]()          # 480 transport + 820 lodging, tax 45.28
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]

    assert invoice["total_amount"] == 1300.0, "the header carries no amount to render"
    assert invoice["tax_amount"] == 45.28, "recoverable input tax must survive the hop"

    # …and what it states agrees with what it bills
    detail = shop["client"].get(f"/api/v1/invoices/{invoice['id']}/detail",
                                headers=shop["headers"]).json()["data"]
    assert detail["computed_total"] == detail["billed_total"] == 1300.0
    assert detail["computed_tax_total"] == 45.28


def test_a_claim_with_no_tax_states_no_tax(shop) -> None:
    """`0.0` and "no tax was recorded" are different facts. Summing to zero and
    storing it would claim the receipts were examined and found tax-free."""
    claim = shop["post"]("/expense-claims", {
        "employee_id": shop["employee"], "title": "no tax anywhere",
        "items": [{"expense_date": "2026-07-18", "amount": 60.0, "category": "meal"}]})
    shop["approve"](claim["id"])
    invoice = raise_invoice(shop, claim["id"]).json()["data"]

    assert invoice["total_amount"] == 60.0
    assert invoice["tax_amount"] is None, "no tax on any line must not become a stated zero"


def test_an_employee_facing_invoice_states_what_kind_it_is(shop) -> None:
    """A document with no type reads as an unfinished one.

    Neither a payslip nor a reimbursement is a tax instrument, so none of the
    发票 values fit — and `other` would be a different lie: it means "a
    document nobody classified", which would put these in the same bucket as
    genuinely unclassified receipts the next time somebody totals input tax.
    Each gets a seeded value of its own.
    """
    claim = shop["claim"]()
    shop["approve"](claim["id"])
    raised = raise_invoice(shop, claim["id"]).json()["data"]
    assert raised["invoice_type"] == "reimbursement"

    # …and the same default reaches a payslip filed through the ordinary route
    payslip = shop["post"]("/invoices", {
        "direction": "payroll", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "title": "July salary",
        "period_start": "2026-07-01", "period_end": "2026-07-31",
        "items": [{"invoice_item_type": "payroll_salary",
                   "product_name_snapshot": "Base salary", "amount": 15000.0,
                   "notes": "15000.00 a month"}]})
    assert payslip["invoice_type"] == "payslip"


def test_a_stated_type_is_never_overwritten(shop) -> None:
    """The default fills a silence; it does not correct the caller. A workspace
    that classifies its own reimbursements keeps its answer."""
    stated = shop["post"]("/invoices", {
        "direction": "reimbursement", "employee_id": shop["employee"],
        "payee_employee_id": shop["employee"], "title": "stated",
        "invoice_type": "receipt", "total_amount": 100.0})
    assert stated["invoice_type"] == "receipt"


def test_supplier_and_customer_invoices_are_left_open(shop) -> None:
    """Which 发票 a supplier issued is a fact about the paper. The server has
    no business guessing it, so those directions get no default — filling them
    in would be inventing evidence."""
    vendor = shop["post"]("/vendors", {"name": "Dell"})["id"]
    bill = shop["post"]("/invoices", {
        "direction": "purchase", "employee_id": shop["employee"], "vendor_id": vendor,
        "title": "a bill", "total_amount": 500.0})
    assert bill["invoice_type"] is None


def test_every_default_type_is_a_value_the_vocabulary_actually_ships() -> None:
    """A default naming a value no workspace has is worse than none.

    `require_type_option` runs on what the CALLER states, not on what the
    server fills in — so a default pointing at an unseeded value would write a
    type nothing can resolve, and a mutation removing the seeded entry left
    every other test here green. The two must be checked against each other
    directly.
    """
    from app.api.billing import DEFAULT_INVOICE_TYPE_BY_DIRECTION
    from app.core.type_options import SYSTEM_TYPE_OPTIONS

    shipped = {name for name, _, _ in SYSTEM_TYPE_OPTIONS["invoice_type"]}
    missing = {
        direction: value
        for direction, value in DEFAULT_INVOICE_TYPE_BY_DIRECTION.items()
        if value not in shipped
    }
    assert not missing, (
        f"these directions default to invoice types no workspace is seeded with: {missing}"
    )
