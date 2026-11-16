"""Posting into the book at once — plan docs/plans/accounting-core-2026-11-08.md.

Two agents posting the same source fact must leave one entry in the book
(`journal_entries_source_uk`), and a month closing while an entry posts into
it must not let the entry slip in: both paths take the period row's lock.
SQLite has one connection and ignores locks; only here can two transactions
meet.
"""

from __future__ import annotations

import threading
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.api.deps import Actor
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]


def make_actor(tenant_id: str) -> Actor:
    return Actor(tenant_id=tenant_id, kind="service", role="service", credential_id=uuid.uuid4().hex)


@pytest.fixture()
def book(pg_sessionmaker):
    from app.models import AccountingSettings, Customer, Employee, Invoice, LedgerAccount, Tenant

    with pg_sessionmaker() as db:
        tenant = Tenant(name="Book Co", email_domain="book-co.example", slug=f"book-{uuid.uuid4().hex[:6]}")
        db.add(tenant)
        db.flush()
        db.add(AccountingSettings(tenant_id=tenant.id, functional_currency="CNY"))
        clerk = Employee(tenant_id=tenant.id, name="Clerk")
        customer = Customer(tenant_id=tenant.id, name="Huaxin")
        db.add_all([clerk, customer])
        db.flush()
        invoice = Invoice(tenant_id=tenant.id, invoice_no="INV-1", direction="sales", employee_id=clerk.id,
                          customer_id=customer.id, title="goods", currency="CNY", status="issued")
        receivable = LedgerAccount(tenant_id=tenant.id, account_code="1122", name="AR", account_type="asset")
        revenue = LedgerAccount(tenant_id=tenant.id, account_code="6001", name="Sales", account_type="income")
        db.add_all([invoice, receivable, revenue])
        db.commit()
        return {"tenant_id": tenant.id, "invoice_id": invoice.id, "receivable": receivable.id, "revenue": revenue.id}


def _entry(info, day: date):
    from app.schemas import CreateJournalEntryRequest

    return CreateJournalEntryRequest(
        posting_date=day, description="goods issued", status="posted", source_type="invoice",
        source_id=info["invoice_id"], source_event="issued",
        lines=[{"ledger_account_id": info["receivable"], "debit": 100},
               {"ledger_account_id": info["revenue"], "credit": 100}])


def _together(pg_sessionmaker, calls) -> list[Exception]:
    barrier = threading.Barrier(len(calls))
    errors: list[Exception] = []

    def run(call):
        try:
            with pg_sessionmaker() as db:
                barrier.wait(timeout=15)
                call(db)
        except Exception as exc:  # the refused one is the point
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


def _posted(pg_sessionmaker, tenant_id: str) -> int:
    from app.models import JournalEntry

    with pg_sessionmaker() as db:
        return db.scalar(select(func.count()).select_from(JournalEntry).where(
            JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted"))


@needs_postgres
def test_one_source_fact_posted_twice_at_once_posts_once(pg_sessionmaker, book) -> None:
    from app.api.ledger import create_journal_entry

    actor = make_actor(book["tenant_id"])
    errors = _together(pg_sessionmaker, [
        lambda db: create_journal_entry(_entry(book, date(2026, 3, 10)), actor, db),
        lambda db: create_journal_entry(_entry(book, date(2026, 3, 10)), actor, db),
    ])
    assert len(errors) == 1 and getattr(errors[0], "status_code", None) == 409, errors
    assert _posted(pg_sessionmaker, book["tenant_id"]) == 1


@needs_postgres
def test_an_entry_and_its_months_close_at_once_never_leave_it_inside_a_closed_month(pg_sessionmaker, book) -> None:
    from app.api.ledger import close_accounting_period, create_journal_entry
    from app.models import AccountingPeriod, JournalEntry
    from app.schemas import PeriodActionRequest

    actor = make_actor(book["tenant_id"])
    _together(pg_sessionmaker, [
        lambda db: create_journal_entry(_entry(book, date(2026, 3, 10)), actor, db),
        lambda db: close_accounting_period(PeriodActionRequest(period=date(2026, 3, 1)), actor, db),
    ])
    with pg_sessionmaker() as db:
        period = db.scalar(select(AccountingPeriod).where(AccountingPeriod.tenant_id == book["tenant_id"]))
        posted = db.scalar(select(JournalEntry).where(JournalEntry.tenant_id == book["tenant_id"],
                                                      JournalEntry.status == "posted"))
        assert period is not None
        if posted is not None and period.status == "closed":
            assert posted.posted_at <= period.closed_at, "an entry landed in the month after it closed"
