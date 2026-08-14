"""A capability we ship later reaches the role we ship it for — unless the
workspace took it away.

Three features shipped to a 403: settlement, payroll, leave. Each time the
capability existed, the role that should have carried it did not, and the sync
could not act because a gap in `permissions_jsonb` is ambiguous — omission or
decision, indistinguishable. `Role.catalog_permissions_jsonb` records what we
gave, which is the missing half of the comparison.

These tests pin the four cases that ambiguity collapses into, because each one
is a separate decision and three of them are ways to get it wrong.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.models import Role, Tenant
from app.services.provisioning import provision_system_roles, unheld_shipped_capabilities

from conftest import make_session

TENANT = "44444444-4444-4444-4444-444444444444"


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with make_session([Tenant(id=TENANT, name="Roles Co")]) as session:
        yield session


@pytest.fixture()
def tenant_id() -> str:
    return TENANT


@pytest.fixture()
def member(db_session, tenant_id):
    provision_system_roles(db_session, tenant_id)
    db_session.flush()
    return db_session.scalar(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == "member")
    )


def _sync(db_session, tenant_id, shipped, monkeypatch):
    """Re-run the sync as if `member` shipped `shipped` this release."""
    monkeypatch.setitem(DEFAULT_ROLE_PERMISSIONS, "member", tuple(shipped))
    provision_system_roles(db_session, tenant_id)
    db_session.flush()


def test_a_fresh_role_records_what_it_was_given(member) -> None:
    assert set(member.permissions_jsonb) == set(DEFAULT_ROLE_PERMISSIONS["member"])
    assert set(member.catalog_permissions_jsonb) == set(DEFAULT_ROLE_PERMISSIONS["member"])


def test_a_capability_shipped_later_reaches_the_role(db_session, tenant_id, member,
                                                     monkeypatch) -> None:
    """The whole point. This is 请假 the day it shipped."""
    shipped = list(DEFAULT_ROLE_PERMISSIONS["member"]) + ["sabbatical.submit_own"]
    _sync(db_session, tenant_id, shipped, monkeypatch)

    assert "sabbatical.submit_own" in member.permissions_jsonb
    assert "sabbatical.submit_own" in member.catalog_permissions_jsonb


def test_a_capability_the_workspace_removed_stays_removed(db_session, tenant_id, member,
                                                          monkeypatch) -> None:
    """The reason the sync used to do nothing. Re-granting this is worse than
    never granting anything: a permission a customer took away comes back and
    nobody is told."""
    member.permissions_jsonb = [
        p for p in member.permissions_jsonb if p != "expense.submit_own"
    ]
    db_session.flush()

    _sync(db_session, tenant_id, list(DEFAULT_ROLE_PERMISSIONS["member"]), monkeypatch)

    assert "expense.submit_own" not in member.permissions_jsonb


def test_removal_survives_an_unrelated_capability_shipping(db_session, tenant_id, member,
                                                           monkeypatch) -> None:
    """The two above must hold at the same time, which is the case a single
    `shipped - held` diff cannot express."""
    member.permissions_jsonb = [
        p for p in member.permissions_jsonb if p != "expense.submit_own"
    ]
    db_session.flush()

    shipped = list(DEFAULT_ROLE_PERMISSIONS["member"]) + ["sabbatical.submit_own"]
    _sync(db_session, tenant_id, shipped, monkeypatch)

    assert "sabbatical.submit_own" in member.permissions_jsonb
    assert "expense.submit_own" not in member.permissions_jsonb


def test_a_role_with_no_record_is_not_widened_by_guessing(db_session, tenant_id, member,
                                                          monkeypatch) -> None:
    """A pre-column role, or one created outside provisioning. Every gap in it
    is ambiguous, so none of them are ours to close — we start the record and
    grant nothing. Guessing backwards is what migration 0052 declines to do."""
    member.permissions_jsonb = ["approval.record"]
    member.catalog_permissions_jsonb = None
    db_session.flush()

    _sync(db_session, tenant_id, list(DEFAULT_ROLE_PERMISSIONS["member"]), monkeypatch)

    assert member.permissions_jsonb == ["approval.record"]
    assert set(member.catalog_permissions_jsonb) == set(DEFAULT_ROLE_PERMISSIONS["member"])


def test_the_baseline_moves_even_when_nothing_is_granted(db_session, tenant_id, member,
                                                         monkeypatch) -> None:
    """Without this the next release re-grants what the tenant just removed:
    a stale baseline makes a deliberate removal look like "never offered"."""
    _sync(db_session, tenant_id, list(DEFAULT_ROLE_PERMISSIONS["member"]), monkeypatch)
    member.permissions_jsonb = [
        p for p in member.permissions_jsonb if p != "booking.own"
    ]
    db_session.flush()

    _sync(db_session, tenant_id, list(DEFAULT_ROLE_PERMISSIONS["member"]), monkeypatch)
    _sync(db_session, tenant_id, list(DEFAULT_ROLE_PERMISSIONS["member"]), monkeypatch)

    assert "booking.own" not in member.permissions_jsonb


def test_a_custom_role_is_never_touched(db_session, tenant_id, member, monkeypatch) -> None:
    """We ship no defaults for a role a tenant invented, so there is nothing to
    follow. `scripts/reconcile_demo_roles.py` stays the named way to widen one."""
    db_session.add(Role(
        tenant_id=tenant_id, name="dept_manager", title="Dept Manager",
        permissions_jsonb=["approval.record"], is_system=False,
    ))
    db_session.flush()

    shipped = list(DEFAULT_ROLE_PERMISSIONS["member"]) + ["sabbatical.submit_own"]
    _sync(db_session, tenant_id, shipped, monkeypatch)

    custom = db_session.scalar(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == "dept_manager")
    )
    assert custom.permissions_jsonb == ["approval.record"]
    assert custom.catalog_permissions_jsonb is None


def test_admin_still_gets_everything_regardless_of_its_record(db_session, tenant_id,
                                                              monkeypatch) -> None:
    """admin is defined as ALL_PERMISSIONS and is topped up on that definition,
    not on the baseline. A stale or absent record must not narrow it."""
    provision_system_roles(db_session, tenant_id)
    db_session.flush()
    admin = db_session.scalar(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == "admin")
    )
    admin.permissions_jsonb = ["approval.record"]
    admin.catalog_permissions_jsonb = ["approval.record"]
    db_session.flush()

    provision_system_roles(db_session, tenant_id)
    db_session.flush()

    assert set(admin.permissions_jsonb) == set(ALL_PERMISSIONS)


def test_the_alarm_goes_quiet_once_the_capability_lands(db_session, tenant_id, member,
                                                        monkeypatch) -> None:
    """The startup report and this mechanism have to agree: a capability the
    sync can now place should stop being reported as unreachable."""
    shipped = list(DEFAULT_ROLE_PERMISSIONS["member"]) + ["sabbatical.submit_own"]
    monkeypatch.setitem(DEFAULT_ROLE_PERMISSIONS, "member", tuple(shipped))

    member.catalog_permissions_jsonb = [
        p for p in member.catalog_permissions_jsonb if p != "sabbatical.submit_own"
    ]
    member.permissions_jsonb = [
        p for p in member.permissions_jsonb if p != "sabbatical.submit_own"
    ]
    db_session.flush()
    assert "sabbatical.submit_own" in unheld_shipped_capabilities(db_session, tenant_id)

    provision_system_roles(db_session, tenant_id)
    db_session.flush()

    assert "sabbatical.submit_own" not in unheld_shipped_capabilities(db_session, tenant_id)
