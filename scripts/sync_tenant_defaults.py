"""Provision/refresh product skills and builtin definitions for all tenants.

Runs at container start (after migrations) and can be run manually after a
product-skill update. Idempotent: product skills are upserted by name (file
changes bump the version); tenant-authored skills and tenant-customized
builtin definitions are never touched.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.session import create_ops_sessionmaker
from app.models import Tenant
from app.services.flow_subscriptions import provision_flow_subscriptions
from app.services.provisioning import (
    provision_builtin_definitions,
    provision_product_skills,
    provision_system_capabilities,
    provision_system_roles,
    provision_system_type_options,
)


def main() -> None:
    SessionLocal = create_ops_sessionmaker()
    with SessionLocal() as db:
        tenant_ids = db.scalars(select(Tenant.id)).all()
        skills_changed = 0
        definitions_added = 0
        capabilities_changed = 0
        type_options_changed = 0
        roles_created = 0
        admins_widened = 0
        subscriptions_created = 0
        for tenant_id in tenant_ids:
            skills_changed += provision_product_skills(db, tenant_id)
            definitions_added += provision_builtin_definitions(db, tenant_id)
            capabilities_changed += provision_system_capabilities(db, tenant_id)
            type_options_changed += provision_system_type_options(db, tenant_id)
            created, widened = provision_system_roles(db, tenant_id)
            roles_created += created
            admins_widened += widened
            # After the four above, which it reads. Creates only what is
            # missing — a subscription a tenant switched off stays off, the
            # same rule the admin top-up follows.
            subscriptions_created += provision_flow_subscriptions(db, tenant_id)
        db.commit()
    print(
        f"tenant defaults synced: {len(tenant_ids)} tenants, "
        f"{skills_changed} product skills upserted, {definitions_added} builtin definitions added, "
        f"{capabilities_changed} system capabilities refreshed, "
        f"{type_options_changed} type options refreshed, {roles_created} system roles created, "
        f"{admins_widened} admin roles given newly shipped capabilities, "
        f"{subscriptions_created} flow subscriptions enrolled"
    )


if __name__ == "__main__":
    main()
