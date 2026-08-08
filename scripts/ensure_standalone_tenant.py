"""Standalone first boot: give the deployment its one workspace.

The cloud grows tenants through registration and review — a SaaS surface a
standalone deployment does not mount. What replaces it is not a smaller
registration flow but a fact: a standalone deployment has exactly one tenant,
so the startup chain can create it the first time and never again. Runs after
`sync_tenant_defaults.py` in the standalone compose command, mirroring what
`provision_registration` does for an approved cloud registration: the tenant,
its first admin user, a bootstrap service key, and the provisioned defaults —
minus the parts that are about strangers (email verification, review).

Idempotent on the bluntest possible fact: ANY existing tenant means this
already happened (or the operator made tenants some other way), so the script
prints nothing sensitive and exits. It never edits an existing workspace —
a bootstrap that "fixes" a live tenant on every restart is a config-drift
engine, and the console owns day-two changes.

Credentials print exactly once, on the boot that created them. The password is
echoed only when it was GENERATED here; one supplied via
ORYH_STANDALONE_ADMIN_PASSWORD is presumed already known to whoever set it.
"""

from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import ApiKey, Tenant, User, generate_api_key, hash_api_key
from app.services.provisioning import provision_tenant_defaults
from app.services.tenants import derive_tenant_slug


def ensure_standalone_tenant(db: Session) -> dict | None:
    """Create the single workspace if none exists. Returns the created facts
    (with plaintext credentials) exactly once, None on every later call."""
    if db.scalar(select(Tenant).limit(1)) is not None:
        return None

    password = settings.standalone_admin_password
    generated_password = not password
    if generated_password:
        password = secrets.token_urlsafe(12)

    tenant = Tenant(
        name=settings.standalone_company_name,
        status="active",
        slug=derive_tenant_slug(db, None),
    )
    db.add(tenant)
    db.flush()

    admin = User(
        tenant_id=tenant.id,
        email=settings.standalone_admin_email,
        password_hash=hash_password(password),
        role="admin",
        status="active",
    )
    plain_text_api_key = generate_api_key()
    bootstrap_key = ApiKey(
        tenant_id=tenant.id,
        key_hash=hash_api_key(plain_text_api_key),
        label="bootstrap",
        role="service",
    )
    db.add_all([admin, bootstrap_key])
    provision_tenant_defaults(db, tenant.id)
    db.commit()

    return {
        "tenant_id": tenant.id,
        "company_name": tenant.name,
        "admin_email": admin.email,
        "admin_password": password if generated_password else None,
        "bootstrap_api_key": plain_text_api_key,
    }


def main() -> int:
    if settings.resolved_edition != "standalone":
        print("ensure_standalone_tenant: cloud edition grows tenants through registration; skipped")
        return 0

    from app.db.session import create_ops_sessionmaker

    SessionLocal = create_ops_sessionmaker()
    with SessionLocal() as db:
        created = ensure_standalone_tenant(db)

    if created is None:
        print("ensure_standalone_tenant: workspace already exists; nothing to do")
        return 0

    lines = [
        "",
        "=" * 64,
        "  oryh standalone workspace created",
        f"  company:   {created['company_name']}",
        f"  console:   sign in as {created['admin_email']}",
    ]
    if created["admin_password"] is not None:
        lines.append(f"  password:  {created['admin_password']}   (generated — change it after first sign-in)")
    lines += [
        f"  agent key: {created['bootstrap_api_key']}   (service key for connecting agents)",
        "  This is printed ONCE. Store it now.",
        "=" * 64,
        "",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
