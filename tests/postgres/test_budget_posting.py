"""Two budget changes posting at once — plan docs/plans/budgets-2026-10-27.md.

Posting writes the plan ledger under `FOR UPDATE` on the budget, so two
changes never interleave, and a change line posts once
(`budget_entries_change_line_uk`). SQLite has one connection and ignores the
lock; only here can two transactions meet.
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
def budget_with_changes(pg_sessionmaker):
    """A budget with one line and three draft changes of 100 each."""
    from app.models import Budget, BudgetChange, BudgetChangeLine, BudgetLine, Employee, Tenant

    with pg_sessionmaker() as db:
        tenant = Tenant(name="Plan Co", email_domain="plan-co.example", slug=f"plan-{uuid.uuid4().hex[:6]}")
        db.add(tenant)
        db.flush()
        owner = Employee(tenant_id=tenant.id, name="Owner")
        db.add(owner)
        db.flush()
        budget = Budget(tenant_id=tenant.id, budget_no="BG-1", name="2026", direction="spend",
                        budget_type="operating", currency="CNY", period_start=date(2026, 1, 1),
                        period_end=date(2026, 12, 31), status="active")
        db.add(budget)
        db.flush()
        line = BudgetLine(tenant_id=tenant.id, budget_id=budget.id, line_code="MKT", name="Marketing",
                          category="marketing")
        db.add(line)
        db.flush()
        changes = []
        for n in range(3):
            change = BudgetChange(tenant_id=tenant.id, change_no=f"BC-{n}", budget_id=budget.id,
                                  change_type="increase", employee_id=owner.id, reason="more", status="draft")
            db.add(change)
            db.flush()
            db.add(BudgetChangeLine(tenant_id=tenant.id, change_id=change.id, budget_line_id=line.id, line_no=1,
                                    period_month=date(2026, 3, 1), amount=100))
            changes.append(change.id)
        db.commit()
        return {"tenant_id": tenant.id, "budget_id": budget.id, "line_id": line.id, "changes": changes}


def post_in_thread(pg_sessionmaker, info, change_id, *, barrier, errors):
    from app.api.budgets import update_budget_change
    from app.schemas import UpdateBudgetChangeRequest

    try:
        with pg_sessionmaker() as db:
            barrier.wait(timeout=15)
            update_budget_change(change_id, UpdateBudgetChangeRequest(status="posted"),
                                 make_actor(info["tenant_id"]), db)
    except Exception as exc:  # the refused one is the point of the second test
        errors.append(exc)


def _run(pg_sessionmaker, info, change_ids):
    barrier = threading.Barrier(len(change_ids))
    errors: list[Exception] = []
    threads = [threading.Thread(target=post_in_thread, args=(pg_sessionmaker, info, cid),
                                kwargs={"barrier": barrier, "errors": errors}) for cid in change_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


def _planned(pg_sessionmaker, info) -> tuple[int, float]:
    from app.models import BudgetEntry

    with pg_sessionmaker() as db:
        count, total = db.execute(select(func.count(), func.coalesce(func.sum(BudgetEntry.amount), 0)).where(
            BudgetEntry.budget_line_id == info["line_id"])).one()
    return int(count), float(total)


@needs_postgres
def test_three_changes_posting_at_once_all_land(pg_sessionmaker, budget_with_changes) -> None:
    errors = _run(pg_sessionmaker, budget_with_changes, budget_with_changes["changes"])
    assert errors == []
    assert _planned(pg_sessionmaker, budget_with_changes) == (3, 300.0)


@needs_postgres
def test_one_change_posted_twice_at_once_posts_once(pg_sessionmaker, budget_with_changes) -> None:
    """Two people press post on the same draft. One posts; the other finds it
    posted already (the machine has no posted -> posted) or meets the unique
    change line — either way the plan moves by 100, not 200."""
    one = budget_with_changes["changes"][0]
    errors = _run(pg_sessionmaker, budget_with_changes, [one, one])
    assert len(errors) == 1, errors
    assert _planned(pg_sessionmaker, budget_with_changes) == (1, 100.0)
