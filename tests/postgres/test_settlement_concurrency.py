"""Two transactions moving the same money. The balance must survive both.

The 2026-08-16 architecture review's P0-1. Three write paths read a running
total, compute in Python, and write the result back absolutely:

    app/api/billing.py  post_account_entries   account.balance
    app/api/billing.py  apply_payment          payment.applied_amount
    app/api/billing.py  apply_payment          <target>.applied_amount

Two requests can read the same balance, both pass the credit check, both write
their ledger rows, and the second absolute assignment erases the first. The
ledger then disagrees with the running total it is supposed to be the sum of,
both callers were told they succeeded, and `data_integrity_audit.py` finds it
some hours later.

The correct pattern is already in this codebase — `common.py`'s
`resolve_chargeable_account` takes `.with_for_update()` before it reads. Two
paths to the same balance, one locked and one not, is worse than neither being
locked: it reads as a pattern that holds.

Each test comes in two shapes:

  * a DETERMINISTIC one, where a barrier holds both transactions between read
    and write, so the race is not a matter of luck; and
  * a REALISTIC one, N concurrent calls with no barrier, which is what
    production actually looks like.

The deterministic ones characterise the bug. The realistic ones are what would
still be true if somebody replaced the lock with something subtler.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import func, select

from app.api.deps import Actor
from app.models import (
    BillingAccount,
    BillingAccountEntry,
    Customer,
    Tenant,
)
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]


def make_actor(tenant_id: str) -> Actor:
    return Actor(
        tenant_id=tenant_id,
        kind="service",
        role="service",
        credential_id=uuid.uuid4().hex,
    )


@pytest.fixture()
def account(pg_sessionmaker):
    """An account with 100 on it and no credit line: the floor is 0, so an
    overdraw is refusable and a lost update is visible as a negative."""
    with pg_sessionmaker() as db:
        tenant = Tenant(name="PG Co", email_domain="pg-co.example", slug="pg-co")
        db.add(tenant)
        db.flush()
        customer = Customer(tenant_id=tenant.id, name="客户")
        db.add(customer)
        db.flush()
        acct = BillingAccount(
            tenant_id=tenant.id,
            account_code="ACC-1",
            name="客户预存账户",
            customer_id=customer.id,
            unit="CNY",
            unit_type="currency",
            balance=100,
            credit_limit=0,
        )
        db.add(acct)
        db.commit()
        return {"tenant_id": tenant.id, "account_id": acct.id}


def ledger_and_balance(pg_sessionmaker, account_id: str) -> tuple[float, float]:
    with pg_sessionmaker() as db:
        total = db.scalar(
            select(func.coalesce(func.sum(BillingAccountEntry.amount), 0)).where(
                BillingAccountEntry.billing_account_id == account_id
            )
        )
        balance = db.scalar(select(BillingAccount.balance).where(BillingAccount.id == account_id))
        return float(total), float(balance)


def post_in_thread(pg_sessionmaker, account_info, amount, reason, *, barrier=None, errors=None):
    """One deposit, in its own transaction, on its own connection.

    `barrier` releases both threads only once both have read the balance —
    which is the interleaving the guard has to survive, made deterministic
    instead of hoped for.
    """
    from app.api.billing import post_account_entries
    from app.schemas import PostBillingAccountEntryLine

    try:
        with pg_sessionmaker() as db:
            acct = db.get(BillingAccount, account_info["account_id"])
            _ = float(acct.balance or 0)  # the read the race is about
            if barrier is not None:
                barrier.wait(timeout=15)
            post_account_entries(
                db,
                make_actor(account_info["tenant_id"]),
                acct,
                [PostBillingAccountEntryLine(amount=amount, reason=reason)],
                check_permission=False,
            )
            db.commit()
    except Exception as exc:  # recorded, not raised: the thread is not the test
        if errors is not None:
            errors.append(exc)


@needs_postgres
def test_two_deposits_do_not_erase_each_other(pg_sessionmaker, account) -> None:
    """The deterministic reproduction. Both threads read 100; without a lock
    both write 100+their own amount, and whichever commits last wins."""
    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    threads = [
        threading.Thread(target=post_in_thread, args=(pg_sessionmaker, account, 50, "deposit"),
                         kwargs={"barrier": barrier, "errors": errors}),
        threading.Thread(target=post_in_thread, args=(pg_sessionmaker, account, 30, "deposit"),
                         kwargs={"barrier": barrier, "errors": errors}),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"unexpected failures: {errors}"
    ledger, balance = ledger_and_balance(pg_sessionmaker, account["account_id"])
    assert ledger == 80.0, "both entries should be on the ledger"
    assert balance == 180.0, (
        f"balance {balance} is not 100 + the {ledger} on the ledger — one deposit was erased "
        "by the other's absolute write"
    )


@needs_postgres
def test_concurrent_deposits_keep_the_balance_equal_to_the_ledger(pg_sessionmaker, account) -> None:
    """The realistic shape: ten deposits at once, no barrier. Whatever the
    interleaving, the stored balance must equal 100 plus the ledger."""
    errors: list[Exception] = []
    threads = [
        threading.Thread(target=post_in_thread, args=(pg_sessionmaker, account, 10, "deposit"),
                         kwargs={"errors": errors})
        for _ in range(10)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"unexpected failures: {errors}"
    ledger, balance = ledger_and_balance(pg_sessionmaker, account["account_id"])
    assert ledger == 100.0
    assert balance == 200.0, f"balance {balance} != 100 + ledger {ledger}"


@needs_postgres
def test_the_credit_floor_holds_under_concurrency(pg_sessionmaker, account) -> None:
    """The one that costs money. 100 on the account, no credit line, two
    concurrent charges of 80. Exactly one must be refused — unlocked, both read
    100, both pass the floor check, and the account ends up overdrawn on a
    facility that does not exist."""
    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    threads = [
        threading.Thread(target=post_in_thread, args=(pg_sessionmaker, account, -80, "charge"),
                         kwargs={"barrier": barrier, "errors": errors})
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    ledger, balance = ledger_and_balance(pg_sessionmaker, account["account_id"])
    assert balance >= 0, f"balance went to {balance} with no credit limit"
    assert len(errors) == 1, (
        f"exactly one charge should have been refused; {len(errors)} were. "
        f"ledger={ledger} balance={balance}"
    )


# --- the payment side: one payment, two applications, same shape -------------


@pytest.fixture()
def payment_and_invoices(pg_sessionmaker):
    """A 100 payment and two 100 invoices. Applying 100 to each would be
    over-applying the payment by 100 — exactly one must be refused."""
    from datetime import date

    from app.models import Employee, Invoice, Payment

    with pg_sessionmaker() as db:
        tenant = Tenant(name="Pay Co", email_domain="pay-co.example", slug="pay-co")
        db.add(tenant)
        db.flush()
        customer = Customer(tenant_id=tenant.id, name="客户")
        employee = Employee(tenant_id=tenant.id, name="开票人")
        db.add_all([customer, employee])
        db.flush()
        payment = Payment(
            tenant_id=tenant.id, payment_no="PAY-1", direction="inbound",
            customer_id=customer.id, employee_id=employee.id,
            amount=100, currency="CNY", status="draft",
            payment_date=date(2026, 8, 16),
        )
        invoices = [
            Invoice(
                tenant_id=tenant.id, invoice_no=f"INV-{n}", direction="sales",
                customer_id=customer.id, employee_id=employee.id, title=f"发票 {n}",
                total_amount=100, currency="CNY", status="issued",
                invoice_date=date(2026, 8, 16),
            )
            for n in (1, 2)
        ]
        db.add_all([payment, *invoices])
        db.commit()
        return {
            "tenant_id": tenant.id,
            "payment_id": payment.id,
            "invoice_ids": [inv.id for inv in invoices],
        }


def apply_in_thread(pg_sessionmaker, info, invoice_id, amount, *, barrier=None, errors=None):
    from app.api.billing import apply_payment
    from app.schemas import ApplyPaymentLine, ApplyPaymentRequest
    from app.models import Payment

    try:
        with pg_sessionmaker() as db:
            payment = db.get(Payment, info["payment_id"])
            _ = float(payment.applied_amount or 0)  # the read the race is about
            if barrier is not None:
                barrier.wait(timeout=15)
            apply_payment(
                info["payment_id"],
                ApplyPaymentRequest(lines=[ApplyPaymentLine(
                    applied_to_type="invoice", applied_to_id=invoice_id, amount_applied=amount,
                )]),
                make_actor(info["tenant_id"]),
                db,
            )
            db.commit()
    except Exception as exc:
        if errors is not None:
            errors.append(exc)


@needs_postgres
def test_a_payment_cannot_be_applied_twice_over(pg_sessionmaker, payment_and_invoices) -> None:
    """100 of payment, two concurrent applications of 100. Unlocked, both read
    applied=0, both pass the over-apply check, and 200 of a 100 payment is
    settled — money that does not exist, recorded as received."""
    from app.models import Payment, PaymentApplication

    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    threads = [
        threading.Thread(
            target=apply_in_thread,
            args=(pg_sessionmaker, payment_and_invoices, invoice_id, 100),
            kwargs={"barrier": barrier, "errors": errors},
        )
        for invoice_id in payment_and_invoices["invoice_ids"]
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    with pg_sessionmaker() as db:
        applied = float(
            db.scalar(select(Payment.applied_amount).where(
                Payment.id == payment_and_invoices["payment_id"]))
            or 0
        )
        ledger = float(
            db.scalar(select(func.coalesce(func.sum(PaymentApplication.amount_applied), 0)).where(
                PaymentApplication.payment_id == payment_and_invoices["payment_id"]))
        )
    assert applied <= 100.0, f"{applied} of a 100 payment was applied"
    assert ledger <= 100.0, f"the ledger records {ledger} applied from a 100 payment"
    assert applied == ledger, f"stored {applied} != ledger {ledger}"
    assert len(errors) == 1, f"exactly one application should have been refused; {len(errors)} were"
