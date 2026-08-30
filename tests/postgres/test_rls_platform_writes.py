"""Platform-side write paths under a role RLS actually applies to.

The bug class this pins: a write path that works on deployments whose database
role OWNS the tables and therefore skips RLS entirely — and 500s anywhere the
runtime role is not the owner. Two shipped that way:

  * POST /api/v1/tenants (the open bootstrap create) inserted the tenant's
    first api_keys row with no RLS context bound at all — no caller, no
    platform flag — and `tenant_insert` refused it.
  * POST /api/v1/admin/tenants/{id}/api-keys wrote the key fine (api_keys'
    WITH CHECK carries the platform branch on purpose) and then died on the
    audit_logs row the trail listener generates, whose policy did not.

Every SQLite test and every owner-role Postgres test is structurally blind to
this, so these tests run the real endpoints through a session that has
`SET ROLE` to a plain granted role — the same standing oryh_app has in a
deployment that follows scripts/bootstrap_db_roles.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, text

from tests.postgres.conftest import needs_postgres

ROLE = "oryh_rls_probe"


@pytest.fixture(scope="session")
def restricted_grants(pg_url: str, pg_schema: str) -> None:
    """A non-owner role with full table privileges — privileges are not the
    question here, policies are. Re-granted per session because the schema is
    dropped and rebuilt, which drops the grants with it."""
    engine = create_engine(pg_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                do $$ begin
                  create role {ROLE} nologin;
                exception when duplicate_object then null;
                end $$
                """
            )
        )
        conn.execute(
            text(
                f"""
                do $$ begin
                  execute format('grant {ROLE} to %I', current_user);
                exception when others then null;  -- superusers SET ROLE freely
                end $$
                """
            )
        )
        conn.execute(text(f'grant usage on schema "{pg_schema}" to {ROLE}'))
        conn.execute(text(f'grant all privileges on all tables in schema "{pg_schema}" to {ROLE}'))
        conn.execute(text(f'grant usage, select on all sequences in schema "{pg_schema}" to {ROLE}'))
    engine.dispose()


@pytest.fixture()
def restricted_factory(pg_url: str, pg_schema: str, restricted_grants):
    """App-shaped sessions whose connections run as the granted role, so every
    statement — including the audit rows a commit generates — faces the
    policies instead of owner exemption."""
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    engine = create_engine(
        pg_url,
        future=True,
        poolclass=NullPool,
        connect_args={"options": f"-c search_path={pg_schema},public"},
    )

    @event.listens_for(engine, "connect")
    def _assume_restricted_role(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"set role {ROLE}")
        finally:
            cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # The test is void if RLS quietly does not apply — assert the standing.
    with factory() as probe:
        assert probe.execute(text("select current_user")).scalar() == ROLE
    yield factory
    engine.dispose()


@pytest.fixture()
def restricted_client(restricted_factory):
    """The real app, its DB dependency handed restricted-role sessions."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        db = restricted_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@needs_postgres
def test_open_tenant_create_bootstraps_key_under_rls(restricted_client, clean_tables):
    """The bootstrap api_keys insert must ride the new tenant's own GUC —
    there is no authenticated context on this path to borrow one from."""
    response = restricted_client.post("/api/v1/tenants", json={"name": "RLS Probe Co"})
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["plain_text_api_key"]
    assert body["api_key"]["tenant_id"] == body["tenant"]["id"]


@needs_postgres
def test_platform_admin_key_issue_survives_its_audit_row(
    restricted_client, pg_sessionmaker, clean_tables
):
    """The admin write itself passes api_keys' platform branch; what used to
    die was the audit_logs row the commit generates. The endpoint must land
    both, and the trail row must actually be there."""
    from app.core.security import generate_token, hash_token
    from app.models import Tenant
    from app.saas.models import PlatformAdmin, PlatformSession

    token = generate_token()
    with pg_sessionmaker() as db:
        tenant = Tenant(name="Audited Co", slug="audited-co")
        admin = PlatformAdmin(email="op@oryh.example", password_hash="x", status="active")
        db.add_all([tenant, admin])
        db.flush()
        db.add(
            PlatformSession(
                platform_admin_id=admin.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        db.commit()
        tenant_id = tenant.id

    response = restricted_client.post(
        f"/api/v1/admin/tenants/{tenant_id}/api-keys",
        json={"label": "support reset"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["plain_text_api_key"]

    with pg_sessionmaker() as db:
        trail = db.execute(
            text("select count(*) from audit_logs where tenant_id = :t"),
            {"t": tenant_id},
        ).scalar()
    assert trail and trail >= 1
