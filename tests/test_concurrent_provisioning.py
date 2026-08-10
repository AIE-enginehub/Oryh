"""Two API replicas syncing tenant defaults at the same moment.

A rolling update starts the new Pod before the old one leaves, so two processes
run the startup sync concurrently — by design, on every release. Both read
"this default is missing", both insert it, and one takes a unique violation.
Because the whole sync shares a single transaction, that one collision rolled
back every tenant's work and exited the container.

These tests use a FILE-backed SQLite so two sessions hold genuinely separate
connections and transactions. The suite's usual in-memory database is a single
shared connection (StaticPool), where two "sessions" cannot race because they
are the same transaction — it would report a pass that proves nothing.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Capability, Role, Tenant, TenantSkill
from app.services.provisioning import (
    insert_unless_raced,
    provision_system_capabilities,
    provision_system_roles,
    provision_tenant_defaults,
)


@pytest.fixture()
def replicas(tmp_path) -> Generator[tuple[sessionmaker, str], None, None]:
    """A shared database and a factory two independent 'replicas' can open."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'race.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        tenant = Tenant(name="Race Co", slug="race-co", email_domain="race-co.com")
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id
    try:
        yield factory, tenant_id
    finally:
        engine.dispose()


def test_two_replicas_provisioning_at_once_both_succeed(replicas) -> None:
    """The whole failure in one test: replica B commits first, replica A
    then commits into a database that already has everything it planned to
    insert. Before the fix A raised on the shared unique key and lost the work
    it had done for every other default too."""
    factory, tenant_id = replicas
    with factory() as a, factory() as b:
        # both start from the same empty state — the stale read is the race
        assert a.scalar(select(TenantSkill).where(TenantSkill.tenant_id == tenant_id)) is None
        assert b.scalar(select(TenantSkill).where(TenantSkill.tenant_id == tenant_id)) is None

        provision_tenant_defaults(b, tenant_id)
        b.commit()

        provision_tenant_defaults(a, tenant_id)
        a.commit()  # this is the call that used to raise IntegrityError

    with factory() as db:
        names = list(db.scalars(select(TenantSkill.name).where(TenantSkill.tenant_id == tenant_id)))
        assert names, "no product skills provisioned at all"
        assert len(names) == len(set(names)), f"duplicate skills after the race: {names}"
        # the loser's pass must not have doubled anything else either
        caps = list(db.scalars(select(Capability.name).where(Capability.tenant_id == tenant_id)))
        assert len(caps) == len(set(caps))
        roles = list(db.scalars(select(Role.name).where(Role.tenant_id == tenant_id)))
        assert len(roles) == len(set(roles))


def test_the_loser_reports_nothing_changed(replicas) -> None:
    """The changed-count is what the sync prints and what an operator reads to
    decide whether a release did anything. A replica that inserted nothing
    because it lost every race must say so rather than claim the catalog."""
    factory, tenant_id = replicas
    with factory() as b:
        first = provision_system_capabilities(b, tenant_id)
        b.commit()
    assert first > 0

    with factory() as a:
        # a stale reader: it sees an empty tenant and plans the full insert
        second = provision_system_capabilities(a, tenant_id)
        a.commit()
    assert second == 0, f"the losing replica claimed {second} capabilities it did not write"


def test_a_lost_race_does_not_discard_the_rest_of_the_transaction(replicas) -> None:
    """Why a SAVEPOINT and not a try/except around the whole sync: the point is
    that work done BEFORE the collision survives it. A transaction-level
    rollback is what turned one duplicate skill into 38 tenants of lost work."""
    factory, tenant_id = replicas
    with factory() as b:
        provision_system_roles(b, tenant_id)
        b.commit()

    with factory() as a:
        a.add(TenantSkill(
            tenant_id=tenant_id, name="written-before-the-collision", kind="custom",
            title="t", files_jsonb={}, created_by="test",
        ))
        provision_system_roles(a, tenant_id)  # every insert here loses
        a.commit()

    with factory() as db:
        survived = db.scalar(
            select(TenantSkill).where(TenantSkill.name == "written-before-the-collision")
        )
        assert survived is not None, "the earlier write was rolled back with the collision"


def test_an_unrelated_constraint_violation_still_raises(replicas) -> None:
    """The guard must stay narrow. Catching IntegrityError and shrugging would
    turn any future modelling mistake into a default that silently never gets
    provisioned — quieter than the crash it replaced, and worse."""
    factory, tenant_id = replicas
    with factory() as db:
        # a NOT NULL breach, not a duplicate: the lookup finds nothing, so
        # there was no race to lose and the error is the caller's to see
        malformed = TenantSkill(
            tenant_id=tenant_id, name=None, kind="product",
            title="t", files_jsonb={}, created_by="test",
        )
        lookup = select(TenantSkill).where(TenantSkill.name == "malformed")
        with pytest.raises(IntegrityError):
            insert_unless_raced(db, malformed, lookup)


def test_the_race_is_real_without_the_fix(replicas) -> None:
    """Guard the guard. If the plain check-then-insert stopped colliding — a
    dropped unique constraint, say — every test above would pass while proving
    nothing, so pin that the unprotected shape still fails."""
    factory, tenant_id = replicas
    with factory() as b:
        b.add(Capability(
            tenant_id=tenant_id, name="race.probe", kind="system",
            title="t", description="d", scopable=False, created_by="test",
        ))
        b.commit()

    with factory() as a:
        a.add(Capability(
            tenant_id=tenant_id, name="race.probe", kind="system",
            title="t", description="d", scopable=False, created_by="test",
        ))
        with pytest.raises(IntegrityError):
            a.commit()
