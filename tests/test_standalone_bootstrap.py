"""First boot of a standalone deployment: one workspace, created once.

What these tests pin is the replacement contract for registration: everything
`provision_registration` gives an approved cloud signup — tenant, first admin,
bootstrap service key, provisioned defaults — arrives on first boot, minus the
parts that are about strangers. And the bluntest idempotency rule there is:
ANY existing tenant means the script must not touch the database again, ever,
because a bootstrap that "fixes" a live workspace on restart is config drift
with root access.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.models import ApiKey, Role, Tenant, TenantSkill, TypeOption, User

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ensure_standalone_tenant import ensure_standalone_tenant  # noqa: E402

from conftest import make_stack  # noqa: E402


def test_first_boot_creates_the_workspace_and_second_boot_creates_nothing() -> None:
    with make_stack() as (client, engine):
        from sqlalchemy.orm import Session

        with Session(engine) as db:
            created = ensure_standalone_tenant(db)
            assert created is not None
            # generated password is reported for the one-time printout
            assert created["admin_password"]
            assert created["bootstrap_api_key"].startswith("calw_")

            # the workspace is provisioned like any other tenant: vocabulary,
            # roles and product skills are all there, not a bare row
            tenant_id = created["tenant_id"]
            assert db.scalar(select(Tenant).where(Tenant.id == tenant_id)) is not None
            assert db.scalars(select(TypeOption).where(TypeOption.tenant_id == tenant_id)).first() is not None
            assert db.scalars(select(Role).where(Role.tenant_id == tenant_id)).first() is not None
            assert db.scalars(select(TenantSkill).where(TenantSkill.tenant_id == tenant_id)).first() is not None

        with Session(engine) as db:
            assert ensure_standalone_tenant(db) is None, "a second boot must be a no-op"
            assert db.scalar(select(Tenant)) is not None

        # the printed credentials actually work, against the real app:
        # console sign-in for the person...
        login = client.post(
            "/api/v1/auth/login",
            json={"email": created["admin_email"], "password": created["admin_password"]},
        )
        assert login.status_code == 200, login.text

        # ...and the service key for their agents (/auth/me is user-only by
        # design, so prove it on a business surface instead).
        listed = client.get("/api/v1/customers", headers={"X-API-Key": created["bootstrap_api_key"]})
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"] == []


def test_supplied_password_is_used_and_never_echoed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "standalone_admin_password", "operator-chose-this1")
    monkeypatch.setattr(settings, "standalone_admin_email", "boss@internal.example")
    monkeypatch.setattr(settings, "standalone_company_name", "内部部署公司")

    with make_stack() as (client, engine):
        from sqlalchemy.orm import Session

        with Session(engine) as db:
            created = ensure_standalone_tenant(db)
            assert created is not None
            assert created["company_name"] == "内部部署公司"
            # a password the operator supplied is presumed known — the one-time
            # printout must not repeat it
            assert created["admin_password"] is None

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "boss@internal.example", "password": "operator-chose-this1"},
        )
        assert login.status_code == 200, login.text


def test_standalone_defaults_enroll_no_flow_subscriptions() -> None:
    """Default enrolment derives each subscription's driver from installed
    skills. The private tree ships the flow skills, so this asserts the
    tightened rule indirectly: whatever was enrolled names a real driver —
    a subscription with an empty driver_skill can never run and must not be
    provisioned (the #119 lesson, applied to provisioning)."""
    with make_stack() as (_client, engine):
        from sqlalchemy.orm import Session

        from app.models import FlowSubscription

        with Session(engine) as db:
            created = ensure_standalone_tenant(db)
            assert created is not None
            empty_drivers = db.scalars(
                select(FlowSubscription).where(
                    FlowSubscription.tenant_id == created["tenant_id"],
                    FlowSubscription.driver_skill == "",
                )
            ).all()
            assert empty_drivers == []
