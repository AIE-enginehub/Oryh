"""Fin accounts and the bank register: the cash truth, held honest.

The account balance is a running sum of an append-only register with one
write path; the register row is the bank's fact — no lifecycle, no edits,
corrections are counter-entries. What this file pins is the money honesty
around that: sign rules the database itself enforces (deposits positive,
withdrawals negative — CHECKs SQLite-backed tests witness), the PSP
gross/fee/net identity, statement re-imports made idempotent by the bank's
own line id, the reconciliation link that may point a line only at a
payment moving money the SAME way, and the desk split — 钱账分离 —
that keeps the accountant's payment.record out of the cashier's register.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Cash Co", email="admin@cash.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def invite(role: str, permissions: list[str]) -> dict:
            client.post("/api/v1/roles", json={"name": role, "permissions": permissions},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{role}@cash.example", "role": role},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys",
                              json={"label": role, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": key}

        cashier = invite("cashier", ["fin_account.manage"])
        account = client.post("/api/v1/fin-accounts", headers=cashier, json={
            "name": "招行基本户", "institution": "招商银行", "account_number": "1109",
            "opening_balance": 1000.0, "opening_date": "2026-08-01",
        }).json()["data"]

        def balance() -> float:
            return float(client.get(f"/api/v1/fin-accounts/{account['id']}",
                                    headers=cashier).json()["data"]["current_balance"])

        yield {"client": client, "admin": admin, "cashier": cashier, "invite": invite,
               "account": account, "balance": balance}


def test_the_opening_balance_is_the_registers_first_row(desk) -> None:
    assert float(desk["account"]["current_balance"]) == 1000.0
    rows = desk["client"].get("/api/v1/fin-account-transactions",
                              params={"fin_account_id": desk["account"]["id"]},
                              headers=desk["cashier"]).json()["data"]
    assert [r["trans_type"] for r in rows] == ["opening"]
    later = desk["client"].post("/api/v1/fin-account-transactions", headers=desk["cashier"],
                                json={"fin_account_id": desk["account"]["id"],
                                      "trans_type": "opening", "amount": 50.0})
    assert later.status_code == 422, "a second opening would rewrite history"


def test_the_balance_is_a_running_sum_and_only_the_register_moves_it(desk) -> None:
    client, cashier = desk["client"], desk["cashier"]
    for amount, ttype in ((500.0, None), (-120.5, None), (-3.0, "fee")):
        posted = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
            "fin_account_id": desk["account"]["id"], "amount": amount,
            **({"trans_type": ttype} if ttype else {})})
        assert posted.status_code == 201, posted.text
    assert desk["balance"]() == 1000.0 + 500.0 - 120.5 - 3.0

    sneaky = client.patch(f"/api/v1/fin-accounts/{desk['account']['id']}",
                          headers=cashier, json={"current_balance": 9999})
    assert sneaky.status_code == 422, "no balance field exists to edit — the register is the way"

    frozen = client.patch(
        "/api/v1/fin-account-transactions/"
        + client.get("/api/v1/fin-account-transactions",
                     params={"fin_account_id": desk["account"]["id"]},
                     headers=cashier).json()["data"][0]["id"],
        headers=cashier, json={"amount": 1.0})
    assert frozen.status_code == 422, \
        "bank facts are frozen — only the reconciliation links are ours to set"


def test_the_balance_moves_by_a_relative_update() -> None:
    """The one property the suite cannot exercise: two concurrent postings
    against one account. An absolute write (`balance = <python number>`) lets
    the second silently swallow the first — both register rows survive, the
    balance loses one, nothing errors — and SQLite's single writer can never
    reproduce it. So the pin reads the source: the service must hand the
    arithmetic to the database, the same stance post_inventory_detail took
    and for the same reason."""
    import pathlib
    source = (pathlib.Path(__file__).resolve().parents[1]
              / "app/services/treasury.py").read_text(encoding="utf-8")
    assert "FinAccount.current_balance + amount" in source, \
        "the balance update must be relative — computed by the database, never Python"


def test_the_database_itself_holds_the_sign_rules(desk) -> None:
    client, cashier = desk["client"], desk["cashier"]
    backwards = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "trans_type": "deposit", "amount": -5.0})
    assert backwards.status_code >= 400, "a negative deposit must not land"
    zero = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "amount": 0})
    assert zero.status_code == 422


def test_psp_lines_carry_gross_fee_net_and_the_identity_holds(desk) -> None:
    client, cashier = desk["client"], desk["cashier"]
    wallet = client.post("/api/v1/fin-accounts", headers=cashier, json={
        "name": "微信商户", "institution": "微信支付", "account_type": "wallet",
    }).json()["data"]
    ok = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": wallet["id"], "amount": 99.4,
        "gross_amount": 100.0, "fee_amount": 0.6,
        "counterparty": "买家A", "reference_no": "WX-1001"})
    assert ok.status_code == 201, ok.text
    crooked = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": wallet["id"], "amount": 99.0,
        "gross_amount": 100.0, "fee_amount": 0.6})
    assert crooked.status_code == 422, "net must equal gross - fee — taught before the CHECK fires"


def test_statement_import_is_idempotent_by_the_banks_own_line_id(desk) -> None:
    client, cashier = desk["client"], desk["cashier"]
    rows = [
        {"trans_date": "2026-08-25", "amount": 300.0, "reference_no": "B-001",
         "counterparty": "客户甲"},
        {"trans_date": "2026-08-25", "amount": -80.0, "reference_no": "B-002",
         "counterparty": "房东"},
        {"trans_date": "2026-08-26", "amount": -1.5, "trans_type": "fee",
         "reference_no": "B-003"},
    ]
    body = {"fin_account_id": desk["account"]["id"], "rows": rows}
    first = client.post("/api/v1/fin-account-transactions/bulk", headers=cashier,
                        json={**body, "dry_run": True}).json()["data"]
    assert first["summary"]["created"] == 3 and not first["applied"]
    assert desk["balance"]() == 1000.0, "a dry run moves no money"

    applied = client.post("/api/v1/fin-account-transactions/bulk", headers=cashier,
                          json=body).json()["data"]
    assert applied["summary"]["created"] == 3 and applied["applied"]
    assert desk["balance"]() == 1000.0 + 300.0 - 80.0 - 1.5

    again = client.post("/api/v1/fin-account-transactions/bulk", headers=cashier,
                        json=body).json()["data"]
    assert again["summary"]["unchanged"] == 3 and again["summary"]["created"] == 0, \
        "re-importing the same statement is a no-op, which is how a half-run resumes"
    assert desk["balance"]() == 1000.0 + 300.0 - 80.0 - 1.5

    mutated = client.post("/api/v1/fin-account-transactions/bulk", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "on_error": "skip",
        "rows": [{"trans_date": "2026-08-25", "amount": 999.0, "reference_no": "B-001"}],
    }).json()["data"]
    assert mutated["summary"]["failed"] == 1, \
        "the same line id with a different amount is a person's question, never an overwrite"


def test_the_reconciliation_link_moves_money_the_same_way(desk) -> None:
    client, admin, cashier = desk["client"], desk["admin"], desk["cashier"]
    emp = client.post("/api/v1/employees", json={"name": "出纳"},
                      headers=admin).json()["data"]["id"]
    vendor = client.post("/api/v1/vendors", json={"name": "房东公司"},
                         headers=admin).json()["data"]["id"]
    payment = client.post("/api/v1/payments", headers=admin, json={
        "direction": "outbound", "employee_id": emp, "vendor_id": vendor,
        "amount": 80.0}).json()["data"]

    line = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "amount": -80.0,
        "counterparty": "房东公司"}).json()["data"]
    linked = client.patch(f"/api/v1/fin-account-transactions/{line['id']}",
                          headers=cashier, json={"payment_id": payment["id"]})
    assert linked.status_code == 200, linked.text

    inflow = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "amount": 80.0}).json()["data"]
    backwards = client.patch(f"/api/v1/fin-account-transactions/{inflow['id']}",
                             headers=cashier, json={"payment_id": payment["id"]})
    assert backwards.status_code == 422, \
        "an outbound payment cannot land as a positive line — a backwards link lies"

    queue = client.get("/api/v1/fin-account-transactions",
                       params={"unlinked": True, "fin_account_id": desk["account"]["id"]},
                       headers=cashier).json()["data"]
    assert line["id"] not in {r["id"] for r in queue}, "linked rows leave the queue"
    assert inflow["id"] in {r["id"] for r in queue}


def test_one_debit_settles_a_batch_of_payments(desk) -> None:
    """Payroll leaves the bank as one debit for many payments. The line links
    to the BATCH — the reference_no the payments share — and only when the
    members sum to it exactly; the refusal names the difference, the batch
    line leaves the queue, and a line never settles a payment and a batch
    at once."""
    client, admin, cashier = desk["client"], desk["admin"], desk["cashier"]
    account = desk["account"]["id"]
    officer = client.post("/api/v1/employees", json={"name": "出纳"},
                          headers=admin).json()["data"]["id"]
    for name, net in (("周", 300.0), ("吴", 200.0), ("郑", 150.0)):
        person = client.post("/api/v1/employees", json={"name": name},
                             headers=admin).json()["data"]["id"]
        r = client.post("/api/v1/payments", headers=admin, json={
            "direction": "outbound", "employee_id": officer, "payee_employee_id": person,
            "amount": net, "reference_no": "PAYROLL-2026-08"})
        assert r.status_code == 201, r.text

    short = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account, "amount": -640.0, "description": "代发工资"}).json()["data"]
    refused = client.patch(f"/api/v1/fin-account-transactions/{short['id']}",
                           headers=cashier, json={"payment_reference_no": "PAYROLL-2026-08"})
    assert refused.status_code == 422 and "difference of -10.0" in refused.json()["detail"], \
        "a batch settles exactly — the refusal names the gap for a person"

    debit = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account, "amount": -650.0, "description": "代发工资"}).json()["data"]
    unknown = client.patch(f"/api/v1/fin-account-transactions/{debit['id']}",
                           headers=cashier, json={"payment_reference_no": "PAYROLL-2026-09"})
    assert unknown.status_code == 422, "a batch link names a batch that exists"
    linked = client.patch(f"/api/v1/fin-account-transactions/{debit['id']}",
                          headers=cashier, json={"payment_reference_no": "PAYROLL-2026-08"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["data"]["payments_settled"] == 3
    assert float(linked.json()["data"]["payments_total"]) == 650.0

    queue = {r["id"] for r in client.get(
        "/api/v1/fin-account-transactions", params={"unlinked": True, "fin_account_id": account},
        headers=cashier).json()["data"]}
    assert debit["id"] not in queue and short["id"] in queue, "the batch line is explained"

    credit = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account, "amount": 650.0}).json()["data"]
    backwards = client.patch(f"/api/v1/fin-account-transactions/{credit['id']}",
                             headers=cashier, json={"payment_reference_no": "PAYROLL-2026-08"})
    assert backwards.status_code == 422, "an outbound batch cannot land as a credit"

    one = client.get("/api/v1/payments", params={"reference_no": "PAYROLL-2026-08"},
                     headers=admin).json()["data"][0]["id"]
    both = client.patch(f"/api/v1/fin-account-transactions/{debit['id']}",
                        headers=cashier, json={"payment_id": one})
    assert both.status_code == 422, "one payment or one batch, never both"


def test_bank_fees_are_register_facts_not_payments(desk) -> None:
    """A bank charge needs no payment and no vendor: a standalone fee is a
    `fee` row that explains itself and never sits in the reconciliation
    queue; a fee the bank nets out of a receipt rides the receipt's own
    line as gross/fee/net, and that line links to the full payment."""
    client, admin, cashier = desk["client"], desk["admin"], desk["cashier"]
    account = desk["account"]["id"]
    for body in ({"amount": -1.5, "trans_type": "fee", "description": "monthly account fee"},
                 {"amount": 0.8, "trans_type": "interest"},
                 {"amount": -50.0, "trans_type": "transfer_out", "description": "to the cash box"}):
        r = client.post("/api/v1/fin-account-transactions", headers=cashier,
                        json={"fin_account_id": account, **body})
        assert r.status_code == 201, r.text
    queue = client.get("/api/v1/fin-account-transactions",
                       params={"unlinked": True, "fin_account_id": account},
                       headers=cashier).json()["data"]
    assert queue == [], "rows whose type is the explanation never wait for a document"
    assert desk["balance"]() == 1000.0 - 1.5 + 0.8 - 50.0, "they still move the balance"

    emp = client.post("/api/v1/employees", json={"name": "会计"},
                      headers=admin).json()["data"]["id"]
    customer = client.post("/api/v1/customers", json={"name": "大客户"},
                           headers=admin).json()["data"]["id"]
    payment = client.post("/api/v1/payments", headers=admin, json={
        "direction": "inbound", "employee_id": emp, "customer_id": customer,
        "amount": 10000.0}).json()["data"]
    netted = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account, "gross_amount": 10000.0, "fee_amount": 15.0,
        "amount": 9985.0, "counterparty": "大客户"})
    assert netted.status_code == 201, netted.text
    row = netted.json()["data"]
    assert row["id"] in {r["id"] for r in client.get(
        "/api/v1/fin-account-transactions", params={"unlinked": True, "fin_account_id": account},
        headers=cashier).json()["data"]}, "a receipt still waits for its payment"
    linked = client.patch(f"/api/v1/fin-account-transactions/{row['id']}",
                          headers=cashier, json={"payment_id": payment["id"]})
    assert linked.status_code == 200, linked.text
    assert float(linked.json()["data"]["fee_amount"]) == 15.0, \
        "the netted charge stays on the receipt's line — no second row, no vendor"


def test_a_retail_refund_line_names_the_return_row(desk) -> None:
    client, admin, cashier = desk["client"], desk["admin"], desk["cashier"]
    emp = client.post("/api/v1/employees", json={"name": "店长"},
                      headers=admin).json()["data"]["id"]
    so = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "一单"}).json()["data"]
    ret = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "退一件", "order_kind": "return",
        "original_order_id": so["id"]}).json()["data"]
    refund = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "amount": -39.0,
        "trans_type": "refund", "entity_type": "sales_order", "entity_id": ret["id"]})
    assert refund.status_code == 201, refund.text

    external = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": desk["account"]["id"], "amount": -1.0,
        "entity_type": "sales_order", "entity_id": "TM-NOT-A-UUID"})
    assert external.status_code == 422
    assert "custom_fields" in external.json()["detail"]


def test_the_desks_stay_split(desk) -> None:
    """钱账分离: the accountant's payment.record reaches payment documents and
    never the register; the register's capability reaches nothing else."""
    accountant = desk["invite"]("accountant", ["payment.record", "payment.apply"])
    for method, path, body in (
        ("GET", "/api/v1/fin-accounts", None),
        ("GET", "/api/v1/fin-account-transactions", None),
        ("POST", "/api/v1/fin-account-transactions",
         {"fin_account_id": desk["account"]["id"], "amount": 1.0}),
    ):
        r = desk["client"].request(method, path, headers=accountant,
                                   json=body)
        assert r.status_code == 403, f"{method} {path}: {r.status_code}"

    emp = desk["client"].post("/api/v1/employees", json={"name": "会计"},
                              headers=desk["admin"]).json()["data"]["id"]
    vendor = desk["client"].post("/api/v1/vendors", json={"name": "供应商乙"},
                                 headers=desk["admin"]).json()["data"]["id"]
    payment_write = desk["client"].post("/api/v1/payments", headers=desk["cashier"], json={
        "direction": "outbound", "employee_id": emp, "vendor_id": vendor, "amount": 5.0})
    assert payment_write.status_code == 403, \
        "the cashier's fin_account.manage must not write payment documents"


def test_an_archived_account_refuses_postings(desk) -> None:
    client, cashier = desk["client"], desk["cashier"]
    box = client.post("/api/v1/fin-accounts", headers=cashier,
                      json={"name": "旧现金柜"}).json()["data"]
    assert client.delete(f"/api/v1/fin-accounts/{box['id']}",
                         headers=cashier).status_code == 204
    refused = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": box["id"], "amount": 10.0})
    assert refused.status_code == 409


def test_an_earlier_start_is_restated_not_rebuilt(desk) -> None:
    """The live lesson: an account opened at 8/1 with August's statement at
    hand, then January through July had to come in. The skill's recipe —
    import the older lines, then two adjustments (the balance at the new
    start date, and the reversal of the original opening, dated where it
    sat) — must leave current_balance exactly where it was and be accepted
    by the sign rules, or the recipe is a story rather than a fix."""
    client, cashier, account = desk["client"], desk["cashier"], desk["account"]
    # August, as it happened
    august = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account["id"], "trans_date": "2026-08-15",
        "amount": 250.0, "reference_no": "AUG-1"})
    assert august.status_code == 201
    before = desk["balance"]()
    assert before == 1250.0

    # the older months' net is 1000 - 400 = 600, which the 8/1 opening
    # already contained: balance at 1/1 was 400
    older = client.post("/api/v1/fin-account-transactions/bulk", headers=cashier, json={
        "fin_account_id": account["id"], "rows": [
            {"trans_date": "2026-03-10", "amount": 900.0, "reference_no": "MAR-1"},
            {"trans_date": "2026-05-02", "amount": -300.0, "reference_no": "MAY-1"},
        ]})
    assert older.status_code == 200, older.text
    assert desk["balance"]() == before + 600.0, "importing alone double-counts — the restatement is what fixes it"

    at_start = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account["id"], "trans_type": "adjustment",
        "trans_date": "2026-01-01", "amount": 400.0,
        "description": "opening restated: balance at 2026-01-01"})
    reversal = client.post("/api/v1/fin-account-transactions", headers=cashier, json={
        "fin_account_id": account["id"], "trans_type": "adjustment",
        "trans_date": "2026-08-01", "amount": -1000.0,
        "description": "opening restated: reverses the 2026-08-01 opening"})
    assert at_start.status_code == 201, at_start.text
    assert reversal.status_code == 201, reversal.text
    assert desk["balance"]() == before, "restated: same total, full history, nothing rebuilt"

    rows = client.get("/api/v1/fin-account-transactions",
                      params={"fin_account_id": account["id"], "date_to": "2026-07-31"},
                      headers=cashier).json()["data"]
    assert sum(float(r["amount"]) for r in rows) == 1000.0, \
        "the balance as of any date inside the back-filled span now reads right"
    types = [r["trans_type"] for r in client.get(
        "/api/v1/fin-account-transactions", params={"fin_account_id": account["id"]},
        headers=cashier).json()["data"]]
    assert types.count("opening") == 1, "the original opening stays as the history it is"
