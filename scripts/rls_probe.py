"""Prove RLS isolation by talking to Postgres directly with the runtime role,
bypassing the application entirely.

Usage:
    python scripts/rls_probe.py

Uses ORYH_DATABASE_URL (the restricted oryh_app connection) for the
probes and the owning connection to discover two tenant ids. Exits non-zero
on any breach.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.db.session import ops_engine_url

PROBE_TABLES = ("business_objects", "employees", "todos", "tenant_skills", "timesheet_headers")


def main() -> int:
    if not settings.database_url.startswith("postgresql"):
        raise SystemExit("rls probe requires a postgres ORYH_DATABASE_URL")

    owner = create_engine(ops_engine_url(), future=True)
    with owner.connect() as conn:
        conn.execute(text(f'set search_path to "{settings.database_schema}", public'))
        tenants = conn.execute(
            text("select id::text, name from tenants order by created_at limit 2")
        ).all()
    if len(tenants) < 2:
        raise SystemExit("need at least two tenants (seed demo data first)")
    (tenant_a, name_a), (tenant_b, name_b) = tenants

    app_engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"options": f"-c search_path={settings.database_schema},public"},
    )
    failures: list[str] = []

    with app_engine.connect() as conn:
        role = conn.execute(text("select current_user")).scalar()
        print(f"probing as role: {role}")
        if role != "oryh_app":
            failures.append(f"expected to connect as oryh_app, got {role} (RLS may not apply)")

        # 1. no GUC bound -> default deny on every strict table
        for table in PROBE_TABLES:
            count = conn.execute(text(f"select count(*) from {table}")).scalar()
            print(f"  no-context {table}: {count} rows")
            if count != 0:
                failures.append(f"{table}: visible without tenant context ({count} rows)")
        conn.rollback()  # close the autobegun transaction before explicit begin()

        # 2. bound to tenant A -> only A's rows
        with conn.begin():
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
            for table in PROBE_TABLES:
                leaked = conn.execute(
                    text(f"select count(*) from {table} where tenant_id::text <> :t"), {"t": tenant_a}
                ).scalar()
                visible = conn.execute(text(f"select count(*) from {table}")).scalar()
                print(f"  tenant-A {table}: visible={visible} cross-tenant={leaked}")
                if leaked != 0:
                    failures.append(f"{table}: {leaked} rows of other tenants visible under tenant A")

        # 3. cross-tenant INSERT rejected by WITH CHECK
        try:
            with conn.begin():
                conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
                conn.execute(
                    text(
                        "insert into business_objects (tenant_id, object_type, title) "
                        "values (cast(:other as uuid), 'rls_probe', 'should be rejected')"
                    ),
                    {"other": tenant_b},
                )
            failures.append("cross-tenant INSERT into business_objects was accepted")
        except Exception as exc:
            print(f"  cross-tenant insert rejected: {type(exc).__name__}")

        # 4. platform-admin GUC grants read across tenants
        with conn.begin():
            conn.execute(text("select set_config('app.is_platform_admin', 'on', true)"))
            count = conn.execute(text("select count(distinct tenant_id) from business_objects")).scalar()
            print(f"  platform-admin business_objects tenants visible: {count}")
            if count < 2:
                failures.append("platform-admin context should see all tenants")

    if failures:
        print("\nRLS PROBE FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nRLS PROBE OK (tenants checked: {name_a!r}, {name_b!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
