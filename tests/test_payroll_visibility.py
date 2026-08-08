"""Payroll confidentiality — the first read in this API that belonging to the
workspace does not entitle you to.

Every other read here is tenant-scoped only, which is right for business
documents and unacceptable for pay. This file is the gate's proof, and it is a
separate file because a gate is only worth what its *least* covered path is:
one endpoint left open and the whole thing is decoration.

So each path is tested from both sides — the holder sees it, the non-holder does
not — and the non-holder always sees their own payslip, because an employee who
cannot check what they were paid has no recourse.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import make_client

from conftest import provision_tenant as bootstrap_tenant


def token_from(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


@pytest.fixture()
def workspace() -> Generator[dict, None, None]:
    """A tenant with three credentials and one payslip each for two people:

    - `hr`      holds payroll.read + invoice.manage:* (the service key)
    - `viewer`  holds payroll.read only
    - `outsider` holds neither, and IS one of the paid employees
    """
    with make_client([]) as client:
        data = bootstrap_tenant(client, company_name="Pay Co", email="admin@pay-co.com", password="pay-pass1234")
        hr = {"X-API-Key": data["plain_text_api_key"]}

        def make(name: str) -> str:
            return client.post("/api/v1/employees", json={"name": name}, headers=hr).json()["data"]["id"]

        alice, bob, officer = make("Alice"), make("Bob"), make("HR专员")

        def invite(email: str, role: str, permissions: list[str], employee_id: str | None) -> dict:
            client.post(
                "/api/v1/roles", json={"name": role, "permissions": permissions}, headers=hr
            )
            body = {"email": email, "role": role}
            if employee_id:
                body["employee_id"] = employee_id
            user_id = client.post("/api/v1/auth/invitations", json=body, headers=hr).json()["data"]["id"]
            client.post(
                "/api/v1/auth/invitations/accept",
                json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
            )
            key = client.post(
                "/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id}, headers=hr
            ).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": key}

        viewer = invite("viewer@pay-co.com", "payroll_viewer", ["payroll.read"], None)
        # Alice is an ordinary member with no payroll grant at all
        outsider = invite(
            "alice@pay-co.com", "plain_member",
            ["timesheet.submit_own", "todos.complete_own"], alice,
        )

        slips = {}
        for person, name, net in ((alice, "Alice", 9000.0), (bob, "Bob", 12000.0)):
            slips[name] = client.post(
                "/api/v1/invoices",
                json={
                    "direction": "payroll", "employee_id": officer, "payee_employee_id": person,
                    "title": f"{name} 2026年7月工资",
                    "period_start": "2026-07-01", "period_end": "2026-07-31",
                    "items": [
                        {"invoice_item_type": "payroll_salary",
                         "product_name_snapshot": "基本工资", "amount": net,
                         "notes": f"月薪 {net:.2f}"},
                    ],
                },
                headers=hr,
            ).json()["data"]
            payout = client.post(
                "/api/v1/payments",
                json={"direction": "outbound", "employee_id": officer, "payee_employee_id": person,
                      "amount": net, "status": "paid", "reference_no": "PAYROLL-2026-07"},
                headers=hr,
            ).json()["data"]
            client.post(
                f"/api/v1/payments/{payout['id']}/apply",
                json={"lines": [{"applied_to_type": "invoice",
                                 "applied_to_id": slips[name]["id"], "amount_applied": net}]},
                headers=hr,
            )
            slips[name]["payment_id"] = payout["id"]

        # an ordinary sales invoice, to prove the gate hides payroll and nothing else
        buyer = client.post("/api/v1/customers", json={"name": "客户"}, headers=hr).json()["data"]
        sales = client.post(
            "/api/v1/invoices",
            json={"direction": "sales", "employee_id": officer, "customer_id": buyer["id"],
                  "title": "货款", "total_amount": 5000.0},
            headers=hr,
        ).json()["data"]

        yield {
            "client": client, "hr": hr, "viewer": viewer, "outsider": outsider,
            "slips": slips, "sales": sales, "alice": alice, "bob": bob,
        }


def invite_role(client, hr: dict, email: str, role: str, permissions: list[str]) -> dict:
    client.post("/api/v1/roles", json={"name": role, "permissions": permissions}, headers=hr)
    user_id = client.post(
        "/api/v1/auth/invitations", json={"email": email, "role": role}, headers=hr
    ).json()["data"]["id"]
    client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
    )
    key = client.post(
        "/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id}, headers=hr
    ).json()["data"]["plain_text_api_key"]
    return {"X-API-Key": key}


def ids(response) -> set[str]:
    return {row["id"] for row in response.json()["data"]}


def test_the_holder_sees_every_payslip(workspace: dict) -> None:
    client, slips = workspace["client"], workspace["slips"]
    for headers in (workspace["hr"], workspace["viewer"]):
        listed = ids(client.get("/api/v1/invoices?direction=payroll", headers=headers))
        assert listed == {slips["Alice"]["id"], slips["Bob"]["id"]}


def test_a_credential_without_the_grant_sees_only_its_own(workspace: dict) -> None:
    """Alice is an ordinary member linked to her own employee record."""
    client, slips, outsider = workspace["client"], workspace["slips"], workspace["outsider"]

    listed = ids(client.get("/api/v1/invoices", headers=outsider))
    assert slips["Alice"]["id"] in listed, "an employee must be able to check their own pay"
    assert slips["Bob"]["id"] not in listed
    # and the gate hides payroll only — ordinary documents are unaffected
    assert workspace["sales"]["id"] in listed


def test_fetching_someone_elses_payslip_is_404_not_403(workspace: dict) -> None:
    """403 would confirm that Bob has a payslip for this period, which is most
    of what the gate protects."""
    client, slips, outsider = workspace["client"], workspace["slips"], workspace["outsider"]

    for path in ("", "/detail"):
        response = client.get(f"/api/v1/invoices/{slips['Bob']['id']}{path}", headers=outsider)
        assert response.status_code == 404, path
    # ...while her own is fully readable, breakdown included
    own = client.get(f"/api/v1/invoices/{slips['Alice']['id']}/detail", headers=outsider)
    assert own.status_code == 200
    assert own.json()["data"]["billed_total"] == 9000.0


def test_the_payment_that_paid_someone_else_is_hidden_too(workspace: dict) -> None:
    """Its amount IS their net pay, so gating the invoice alone would be
    pointless."""
    client, slips, outsider = workspace["client"], workspace["slips"], workspace["outsider"]

    listed = ids(client.get("/api/v1/payments", headers=outsider))
    assert slips["Bob"]["payment_id"] not in listed
    assert slips["Alice"]["payment_id"] in listed

    assert client.get(
        f"/api/v1/payments/{slips['Bob']['payment_id']}", headers=outsider
    ).status_code == 404
    assert client.get(
        f"/api/v1/payments/{slips['Bob']['payment_id']}/detail", headers=outsider
    ).status_code == 404
    assert client.get(
        f"/api/v1/payments/{slips['Alice']['payment_id']}", headers=outsider
    ).status_code == 200


def test_an_unsettled_payout_is_hidden_too(workspace: dict) -> None:
    """Found in a live test environment, not here.

    The gate keyed on settlement, but a payout exists long before it is
    settled — created, submitted, approved, paid, and only then applied. For
    that whole stretch it carried the payee's name and their net pay in plain
    view of every colleague, and only became confidential once the money had
    already moved.
    """
    client, hr, outsider = workspace["client"], workspace["hr"], workspace["outsider"]
    officer = client.post(
        "/api/v1/employees", json={"name": "出纳"}, headers=hr
    ).json()["data"]["id"]

    pending = client.post(
        "/api/v1/payments",
        json={"direction": "outbound", "employee_id": officer,
              "payee_employee_id": workspace["bob"], "amount": 12000.0},
        headers=hr,
    ).json()["data"]
    assert pending["applied_amount"] == 0.0, "the point of this test is that it is unsettled"

    listed = ids(client.get("/api/v1/payments", headers=outsider))
    assert pending["id"] not in listed
    assert client.get(
        f"/api/v1/payments/{pending['id']}", headers=outsider
    ).status_code == 404

    # …and the employee's own unsettled payout is still theirs to see
    own = client.post(
        "/api/v1/payments",
        json={"direction": "outbound", "employee_id": officer,
              "payee_employee_id": workspace["alice"], "amount": 9000.0},
        headers=hr,
    ).json()["data"]
    assert own["id"] in ids(client.get("/api/v1/payments", headers=outsider))


def test_a_money_handler_sees_payouts_it_has_to_process(workspace: dict) -> None:
    """The exemption is the job: a 出纳 recording 报销付款 and 工资代发 has to
    see what they are paying. What stays hidden from them is a payout already
    applied to somebody's payslip — at that point its amount IS the net pay."""
    client, hr = workspace["client"], workspace["hr"]
    cashier = invite_role(client, hr, "cashier@pay-co.com", "cashier",
                          ["payment.record", "payment.apply"])
    officer = client.post(
        "/api/v1/employees", json={"name": "出纳2"}, headers=hr
    ).json()["data"]["id"]

    pending = client.post(
        "/api/v1/payments",
        json={"direction": "outbound", "employee_id": officer,
              "payee_employee_id": workspace["bob"], "amount": 12000.0},
        headers=hr,
    ).json()["data"]

    assert pending["id"] in ids(client.get("/api/v1/payments", headers=cashier))
    # the already-settled payslip payout stays out of reach
    assert workspace["slips"]["Bob"]["payment_id"] not in ids(
        client.get("/api/v1/payments", headers=cashier)
    )


def test_the_settlement_ledger_is_filtered(workspace: dict) -> None:
    client, slips, outsider = workspace["client"], workspace["slips"], workspace["outsider"]

    rows = client.get("/api/v1/payment-applications", headers=outsider).json()["data"]
    targets = {row["applied_to_id"] for row in rows}
    assert slips["Bob"]["id"] not in targets
    assert slips["Alice"]["id"] in targets

    # naming it directly does not get around the filter either
    direct = client.get(
        f"/api/v1/payment-applications?applied_to_type=invoice&applied_to_id={slips['Bob']['id']}",
        headers=outsider,
    ).json()["data"]
    assert direct == []


def test_even_the_count_is_hidden(workspace: dict) -> None:
    """"How many payslips did this company issue" is worth hiding on its own."""
    client = workspace["client"]

    def invoice_count(headers: dict) -> int:
        directory = client.get("/api/v1/object-directory", headers=headers).json()["data"]
        return next(row["count"] for row in directory if row["object_type"] == "invoice")

    # hr sees 2 payslips + 1 sales invoice; Alice sees her own + the sales one
    assert invoice_count(workspace["hr"]) == 3
    assert invoice_count(workspace["outsider"]) == 2


def test_salary_records_are_gated_the_same_way(workspace: dict) -> None:
    client, hr, outsider = workspace["client"], workspace["hr"], workspace["outsider"]
    for person, amount in ((workspace["alice"], 12000.0), (workspace["bob"], 20000.0)):
        client.post(
            "/api/v1/pay-histories",
            json={"employee_id": person, "amount": amount, "effective_from": "2026-01-01"},
            headers=hr,
        )

    assert len(client.get("/api/v1/pay-histories", headers=hr).json()["data"]) == 2

    own_only = client.get("/api/v1/pay-histories", headers=outsider).json()["data"]
    assert [row["amount"] for row in own_only] == [12000.0]

    bobs = client.get(
        f"/api/v1/employees/{workspace['bob']}/pay-history", headers=outsider
    )
    assert bobs.status_code == 404
    assert client.get(
        f"/api/v1/employees/{workspace['alice']}/pay-history", headers=outsider
    ).status_code == 200


def test_a_tenant_service_key_reads_payroll_by_design(workspace: dict) -> None:
    """Worth stating rather than discovering: a tenant service key bypasses the
    permission layer entirely (`Actor.bypasses_permissions`), so it reads pay.

    That is the documented meaning of that credential — the company issued it to
    itself — and it is not something this gate overrides. The consequence for
    payroll is real though: any standing agent holding the tenant key can read
    every salary, so a workspace that cares should run payroll agents on
    user-bound keys with `payroll.read` instead.
    """
    client, hr, slips = workspace["client"], workspace["hr"], workspace["slips"]

    # `hr` here IS the tenant service key from registration
    listed = ids(client.get("/api/v1/invoices?direction=payroll", headers=hr))
    assert listed == {slips["Alice"]["id"], slips["Bob"]["id"]}

    # and a user-bound key without the grant does not, which is the gate working
    outsider = ids(client.get("/api/v1/invoices?direction=payroll", headers=workspace["outsider"]))
    assert outsider == {slips["Alice"]["id"]}
