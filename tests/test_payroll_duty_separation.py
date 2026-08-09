"""The payroll arc as a real workspace runs it: HR sets pay, issues payslips
and files the payout; somebody else approves it; somebody else again matches
the money to the documents.

`test_payroll_visibility.py` proves who may READ pay. This file proves the
duties are separable — that the capability set a demo tenant actually grants
carries one person through their part and stops them at the edge of the next.
That is a different claim, and it failed in a live environment while every
visibility test passed: HR could set pay and issue every payslip, then got a
403 on the payout that pays them, because filing a payment needs
`payment.record` and the HR role held none of the payment capabilities. The arc
was complete on paper and dead-ended in practice.

The role sets below mirror `scripts/seed_demo.py`. When that file grants a role
something new, this one should be the test that notices.
"""

from __future__ import annotations

import pathlib
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Tenant
from app.services.emails import outbox
from app.services.provisioning import PRODUCT_SKILLS_DIR

from conftest import make_client
from conftest import provision_tenant as bootstrap_tenant

# The demo seed and its reconcile are operations material: the open-core export
# ships the product, not our two fabricated companies. The arc tests below build
# their own workspace and run everywhere; only the two that read `seed_demo.py`
# as a source file need it present, so they skip rather than drag the whole file
# out of the export.
SEED_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
needs_demo_seed = pytest.mark.skipif(
    not SEED_SOURCE.exists(), reason="demo seed is not part of the open-core tree"
)

MEMBER_BASE = [
    "timesheet.submit_own", "expense.submit_own", "business_object.write:*",
    "todos.complete_own", "booking.own",
]

# Verbatim from seed_demo.seed_starbridge. A drift here is a drift in what the
# demo tenant can actually do.
SEEDED_ROLES: dict[str, list[str]] = {
    "hr_admin": MEMBER_BASE + [
        "approval.record", "employees.manage",
        "payroll.read", "payroll.manage", "invoice.manage:payroll",
        "payment.record",
        "policy.manage", "policy.publish",
    ],
    "finance_reviewer": MEMBER_BASE + [
        "approval.record", "invoice.manage:sales", "invoice.manage:purchase",
        "invoice.advance", "payment.record", "payment.apply",
        "billing_account.manage", "billing_account.post:currency",
    ],
    "cashier_lead": MEMBER_BASE + ["approval.record", "payment.record", "payment.advance"],
    # the person being paid: an ordinary member, no payroll grant of any kind
    "plain": list(MEMBER_BASE),
}


def token_from(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


@pytest.fixture()
def workspace() -> Generator[dict, None, None]:
    """One tenant carrying the seeded role set, one linked person per role."""
    with make_client([]) as client:
        data = bootstrap_tenant(
            client, company_name="Xingqiao", email="admin@xingqiao-co.com", password="xq-pass1234"
        )
        root = {"X-API-Key": data["plain_text_api_key"]}
        keys: dict[str, dict] = {}
        employees: dict[str, str] = {}
        for role, permissions in SEEDED_ROLES.items():
            client.post(
                "/api/v1/roles", json={"name": role, "permissions": permissions}, headers=root
            )
            employees[role] = client.post(
                "/api/v1/employees", json={"name": role}, headers=root
            ).json()["data"]["id"]
            user_id = client.post(
                "/api/v1/auth/invitations",
                json={"email": f"{role}@xingqiao-co.com", "role": role,
                      "employee_id": employees[role]},
                headers=root,
            ).json()["data"]["id"]
            client.post(
                "/api/v1/auth/invitations/accept",
                json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
            )
            keys[role] = {"X-API-Key": client.post(
                "/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id}, headers=root
            ).json()["data"]["plain_text_api_key"]}
        yield {"client": client, "root": root, "keys": keys, "employees": employees}


def set_pay(client, hr, employee_id: str, amount: float) -> object:
    return client.post(
        "/api/v1/pay-histories",
        json={"employee_id": employee_id, "component": "base_salary",
              "effective_from": "2026-07-01", "amount": amount,
              "period_type": "month", "notes": "入职定薪"},
        headers=hr,
    )


def issue_payslip(client, hr, officer: str, payee: str, amount: float) -> object:
    return client.post(
        "/api/v1/invoices",
        json={"direction": "payroll", "employee_id": officer, "payee_employee_id": payee,
              "title": "2026年7月工资", "period_start": "2026-07-01", "period_end": "2026-07-31",
              "items": [{"invoice_item_type": "payroll_salary",
                         "product_name_snapshot": "基本工资", "amount": amount,
                         "notes": f"月薪 {amount:.2f}"}]},
        headers=hr,
    )


def file_payout(client, headers, officer: str, payee: str, amount: float) -> object:
    return client.post(
        "/api/v1/payments",
        json={"direction": "outbound", "employee_id": officer, "payee_employee_id": payee,
              "amount": amount, "reference_no": "PAYROLL-2026-07"},
        headers=headers,
    )


def test_hr_files_and_submits_the_payout_but_cannot_approve_it(workspace: dict) -> None:
    """The whole point of giving HR `payment.record`: it is the submit half of
    the payment family, and advancement is a separate capability. Grant one
    without the other and 提交 and 自批 stay different acts — which is what a
    workspace means when it says HR may not pay themselves."""
    client, keys, employees = workspace["client"], workspace["keys"], workspace["employees"]
    hr, payee = keys["hr_admin"], employees["plain"]

    assert set_pay(client, hr, payee, 15000.0).status_code == 201
    assert issue_payslip(client, hr, employees["hr_admin"], payee, 15000.0).status_code == 201

    payout = file_payout(client, hr, employees["hr_admin"], payee, 15000.0)
    assert payout.status_code == 201, payout.text
    payout_id = payout.json()["data"]["id"]

    submitted = client.post(f"/api/v1/payments/{payout_id}/submit", headers=hr)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "submitted"

    # the edge: filing it is HR's job, approving it is not
    self_approved = client.patch(
        f"/api/v1/payments/{payout_id}", json={"status": "approved"}, headers=hr
    )
    assert self_approved.status_code == 403
    assert "payment.advance" in self_approved.json()["detail"]


def test_the_arc_completes_with_no_temporary_grant(workspace: dict) -> None:
    """End to end on the seeded roles alone. The live run that surfaced this
    only got through by adding capabilities to a throwaway role and removing
    them afterwards, which proves the API works and says nothing about whether
    the workspace does."""
    client, keys, employees = workspace["client"], workspace["keys"], workspace["employees"]
    hr, cashier, finance, plain = (
        keys["hr_admin"], keys["cashier_lead"], keys["finance_reviewer"], keys["plain"]
    )
    payee = employees["plain"]

    set_pay(client, hr, payee, 15000.0)
    slip_id = issue_payslip(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]
    payout_id = file_payout(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]
    client.post(f"/api/v1/payments/{payout_id}/submit", headers=hr)

    # 出纳 approves and pays — payment.advance, and no payroll grant needed to
    # move money it is the workspace's job to move
    approved = client.patch(f"/api/v1/payments/{payout_id}", json={"status": "approved"}, headers=cashier)
    assert approved.status_code == 200, approved.text
    paid = client.patch(f"/api/v1/payments/{payout_id}", json={"status": "paid"}, headers=cashier)
    assert paid.status_code == 200, paid.text

    # 会计 matches the money to the payslip — a separate capability from
    # recording it, so 出纳记账 and 会计核销 can be different people
    applied = client.post(
        f"/api/v1/payments/{payout_id}/apply",
        json={"lines": [{"applied_to_type": "invoice", "applied_to_id": slip_id,
                         "amount_applied": 15000.0}],
              "idempotency_key": "payroll-2026-07-plain"},
        headers=finance,
    )
    assert applied.status_code == 200, applied.text

    # idempotent: the same key writes nothing the second time
    replay = client.post(
        f"/api/v1/payments/{payout_id}/apply",
        json={"lines": [{"applied_to_type": "invoice", "applied_to_id": slip_id,
                         "amount_applied": 15000.0}],
              "idempotency_key": "payroll-2026-07-plain"},
        headers=finance,
    )
    assert replay.status_code == 200, replay.text
    detail = client.get(f"/api/v1/invoices/{slip_id}/detail", headers=hr).json()["data"]
    assert float(detail["outstanding_amount"]) == 0.0

    # and the person paid can read their own payslip throughout, holding nothing
    own = client.get(f"/api/v1/invoices/{slip_id}/detail", headers=plain)
    assert own.status_code == 200
    assert float(own.json()["data"]["billed_total"]) == 15000.0


def test_an_approver_reads_what_it_approves_without_reaching_the_salary_record(
    workspace: dict,
) -> None:
    """`payroll.read` and `payroll.manage` are different grants, and the
    approval path needs only the first. A reviewer given both to 'make it work'
    can rewrite the salary they were asked to check."""
    client, keys, employees = workspace["client"], workspace["keys"], workspace["employees"]
    hr, payee = keys["hr_admin"], employees["plain"]
    set_pay(client, hr, payee, 15000.0)
    slip_id = issue_payslip(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]

    reviewer = {"name": "payroll_reviewer",
                "permissions": MEMBER_BASE + ["approval.record", "payment.advance", "payroll.read"]}
    client.post("/api/v1/roles", json=reviewer, headers=workspace["root"])
    user_id = client.post(
        "/api/v1/auth/invitations",
        json={"email": "reviewer@xingqiao-co.com", "role": "payroll_reviewer"},
        headers=workspace["root"],
    ).json()["data"]["id"]
    client.post("/api/v1/auth/invitations/accept",
                json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"})
    key = {"X-API-Key": client.post(
        "/api/v1/tenant/api-keys", json={"label": "reviewer", "user_id": user_id},
        headers=workspace["root"],
    ).json()["data"]["plain_text_api_key"]}

    # reads the payslip it is being asked to approve against
    assert client.get(f"/api/v1/invoices/{slip_id}/detail", headers=key).status_code == 200
    # …and cannot restate what the person earns
    rewrite = client.post(
        "/api/v1/pay-histories",
        json={"employee_id": payee, "component": "base_salary", "effective_from": "2026-08-01",
              "amount": 1.0, "period_type": "month"},
        headers=key,
    )
    assert rewrite.status_code == 403
    assert "payroll.manage" in rewrite.json()["detail"]


def reach(client, headers) -> dict[str, set[str]]:
    body = client.get("/api/v1/my/skills/reach", headers=headers).json()["data"]
    return {
        "received": {entry["name"] for entry in body["received"]},
        "withheld": {entry["name"] for entry in body["withheld"]},
    }


def test_reading_your_own_pay_needs_no_capability_and_so_neither_does_its_skill(
    workspace: dict,
) -> None:
    """The distribution half. `oryh-payroll` is gated on `payroll.manage`, so
    everyone below HR received no payroll skill at all — including the person
    whose own payslip the API would have handed them. An agent asked 我的工资条
    then found no payroll tool and fell back to `business_object.write:*`,
    writing salary figures into a custom object with no read gate on it. The
    read skill is ungated because the read is."""
    client, keys = workspace["client"], workspace["keys"]

    for role in ("plain", "cashier_lead", "finance_reviewer", "hr_admin"):
        assert "oryh-payslip" in reach(client, keys[role])["received"], role

    # the write arc stays gated, and the person it is withheld from is told why
    plain = reach(client, keys["plain"])
    assert "oryh-payroll" in plain["withheld"]
    assert "oryh-payroll" in reach(client, keys["hr_admin"])["received"]


def test_the_read_only_payslip_skill_hands_out_no_write_path() -> None:
    """A read skill that quotes a write endpoint is a write skill with a
    misleading name — an ungated one, here, since this skill reaches everybody."""
    skill = PRODUCT_SKILLS_DIR / "oryh-payslip"
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(skill.rglob("*.md"))
    )
    for verb in ("POST /", "PATCH /", "PUT /", "DELETE /"):
        assert verb not in text, f"the read-only payslip skill quotes {verb}"
    # and it must say what to do when a read is refused, because the observed
    # failure was an agent inventing somewhere else to put the numbers
    assert "business_object" in text


def seeded_role_permissions(function_name: str) -> dict[str, list[str]]:
    """The role grants `scripts/seed_demo.py` actually writes, read out of its
    source. Parsed rather than executed because seeding wants a database, and
    the question here is only what the file says."""
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    base: list[str] = []
    roles: dict[str, list[str]] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "member_base":
            base = [element.value for element in node.value.elts]
        call = node.value if isinstance(node, ast.Expr) else node
        if not isinstance(call, ast.Call) or getattr(call.func, "attr", "") != "add_role":
            continue
        name = call.args[0].value
        grants = call.args[2]
        # the seed writes `member_base + [...]`; either half may be absent
        extra = grants.right if isinstance(grants, ast.BinOp) else grants
        roles[name] = base + [element.value for element in extra.elts]
    return roles


@needs_demo_seed
def test_the_roles_tested_here_are_the_roles_the_demo_tenant_gets() -> None:
    """These tests build their own workspace, so they would happily keep
    passing while `seed_demo.py` drifted out from under them — and the demo
    tenant, not this fixture, is where the 403 was found."""
    seeded = seeded_role_permissions("seed_starbridge")
    for role, expected in SEEDED_ROLES.items():
        if role == "plain":
            continue  # the ordinary member baseline, not a named seed role
        assert role in seeded, f"seed_demo no longer defines {role}"
        assert sorted(seeded[role]) == sorted(expected), (
            f"{role} drifted: seed has {sorted(set(seeded[role]) ^ set(expected))} on one side only"
        )


@needs_demo_seed
def test_reconcile_tops_up_an_existing_tenant_without_a_reseed(workspace: dict) -> None:
    """A shared test environment cannot be `seed_demo.py --reset`: the people
    signed in there have sessions, keys and documents from earlier rounds. So
    the capability gap has to be closable in place, idempotently, and without
    quietly reversing anything an operator removed on purpose."""
    import scripts.reconcile_demo_roles as reconcile
    from scripts.reconcile_demo_roles import REASONS, REQUIRED, plan, unknown_capabilities

    assert unknown_capabilities() == []
    assert set(REASONS) >= {
        capability for roles in REQUIRED.values() for caps in roles.values() for capability in caps
    }
    # every slug it names is one the seed actually creates — a mistyped slug
    # reports "nothing to do", which reads exactly like success
    seed_slugs = set(SEED_SOURCE.read_text(encoding="utf-8").split('slug="')[1:])
    for slug in REQUIRED:
        assert any(rest.startswith(f'{slug}"') for rest in seed_slugs), f"{slug} is in no seed"

    client, root = workspace["client"], workspace["root"]
    # a tenant seeded before the grant existed
    stale = [p for p in SEEDED_ROLES["hr_admin"] if p != "payment.record"]
    client.patch("/api/v1/roles/hr_admin", json={"permissions": stale}, headers=root)

    # the fixture tenant stands in for 星桥; REQUIRED is keyed by real slug
    with client.session_factory() as db:
        slug = db.scalars(select(Tenant.slug)).one()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(reconcile, "REQUIRED", {slug: REQUIRED["starbridge-consulting"]})

    with client.session_factory() as db:
        assert reconcile.unknown_tenants(db) == []
        pending = plan(db, None)
        assert [(role.name, missing) for _, role, missing in pending] == [
            ("hr_admin", ["payment.record"])
        ]
        for _, role, missing in pending:
            role.permissions_jsonb = list(role.permissions_jsonb or []) + missing
        db.commit()
        # idempotent: a second pass finds nothing left to do
        assert plan(db, None) == []

    payee, hr = workspace["employees"]["plain"], workspace["keys"]["hr_admin"]
    assert file_payout(client, hr, workspace["employees"]["hr_admin"], payee, 15000.0).status_code == 201


def test_an_approver_sees_the_payout_it_must_decide_on_but_not_the_payslip(
    workspace: dict,
) -> None:
    """`payment.advance` counts as handling money. Approving a payout you
    cannot see is not a weaker version of the job, it is none of it — the queue
    came back empty, so a workflow definition routing 工资发放 through payment
    approval had a step nobody could reach.

    The widening stops at the payout. The payslip behind it, with its
    line-by-line 社保/个税 breakdown, still needs `payroll.read`."""
    client, keys, employees = workspace["client"], workspace["keys"], workspace["employees"]
    hr, payee = keys["hr_admin"], employees["plain"]
    set_pay(client, hr, payee, 15000.0)
    slip_id = issue_payslip(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]
    payout_id = file_payout(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]
    client.post(f"/api/v1/payments/{payout_id}/submit", headers=hr)

    # an approver holding advancement and no payroll grant whatsoever
    approver = MEMBER_BASE + ["approval.record", "payment.advance"]
    client.post("/api/v1/roles", json={"name": "payout_approver", "permissions": approver},
                headers=workspace["root"])
    user_id = client.post(
        "/api/v1/auth/invitations",
        json={"email": "approver@xingqiao-co.com", "role": "payout_approver"},
        headers=workspace["root"],
    ).json()["data"]["id"]
    client.post("/api/v1/auth/invitations/accept",
                json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"})
    key = {"X-API-Key": client.post(
        "/api/v1/tenant/api-keys", json={"label": "approver", "user_id": user_id},
        headers=workspace["root"],
    ).json()["data"]["plain_text_api_key"]}

    queue = client.get("/api/v1/payments?direction=outbound&status=submitted", headers=key)
    assert payout_id in {row["id"] for row in queue.json()["data"]}
    assert client.get(f"/api/v1/payments/{payout_id}/detail", headers=key).status_code == 200
    # …and the payslip stays shut
    assert client.get(f"/api/v1/invoices/{slip_id}/detail", headers=key).status_code == 404

    assert client.patch(
        f"/api/v1/payments/{payout_id}", json={"status": "approved"}, headers=key
    ).status_code == 200


def test_a_settled_payout_closes_again_even_to_a_money_handler(workspace: dict) -> None:
    """The bound on the widening. Once a payout has been applied to a payslip
    its amount IS that person's net pay, and the first clause of the gate keeps
    its full strength — money handlers included. Approval happens before
    settlement, so the flow never needed this window open."""
    client, keys, employees = workspace["client"], workspace["keys"], workspace["employees"]
    hr, finance, payee = keys["hr_admin"], keys["finance_reviewer"], employees["plain"]
    set_pay(client, hr, payee, 15000.0)
    slip_id = issue_payslip(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]
    payout_id = file_payout(client, hr, employees["hr_admin"], payee, 15000.0).json()["data"]["id"]

    # finance holds payment.record + payment.apply and no payroll grant
    assert client.get(f"/api/v1/payments/{payout_id}", headers=finance).status_code == 200
    client.post(
        f"/api/v1/payments/{payout_id}/apply",
        json={"lines": [{"applied_to_type": "invoice", "applied_to_id": slip_id,
                         "amount_applied": 15000.0}], "idempotency_key": "k1"},
        headers=finance,
    )
    assert client.get(f"/api/v1/payments/{payout_id}", headers=finance).status_code == 404
    assert payout_id not in {
        row["id"] for row in client.get("/api/v1/payments", headers=finance).json()["data"]
    }
