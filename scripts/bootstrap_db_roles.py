"""Create/refresh the restricted oryh_app runtime role.

Runs with the owning connection (ORYH_MIGRATION_DATABASE_URL or
ORYH_DATABASE_URL) before migrations. Idempotent. The role password comes
from ORYH_APP_DB_PASSWORD; if unset the script is a no-op so plain
single-role deployments keep working.

The role gets DML on all tables in the oryh schema but does not own them,
so row-level security policies apply to it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.db.session import ops_engine_url

APP_ROLE = "oryh_app"


def main() -> None:
    password = settings.app_db_password
    if not password:
        print("ORYH_APP_DB_PASSWORD not set; skipping app role bootstrap")
        return
    url = ops_engine_url()
    if not url.startswith("postgresql"):
        print("not a postgres deployment; skipping app role bootstrap")
        return

    schema = settings.database_schema.replace('"', '""')
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text(f'create schema if not exists "{schema}"'))
        role_exists = conn.execute(
            text("select 1 from pg_roles where rolname = :name"), {"name": APP_ROLE}
        ).scalar()
        quoted_password = password.replace("'", "''")
        if role_exists:
            conn.execute(text(f"alter role {APP_ROLE} with login password '{quoted_password}' nobypassrls"))
        else:
            conn.execute(text(f"create role {APP_ROLE} with login password '{quoted_password}' nobypassrls"))
        conn.execute(text(f'grant usage on schema "{schema}" to {APP_ROLE}'))
        conn.execute(
            text(f'grant select, insert, update, delete on all tables in schema "{schema}" to {APP_ROLE}')
        )
        conn.execute(text(f'grant usage on all sequences in schema "{schema}" to {APP_ROLE}'))
        conn.execute(
            text(
                f'alter default privileges in schema "{schema}" '
                f"grant select, insert, update, delete on tables to {APP_ROLE}"
            )
        )
        conn.execute(
            text(f'alter default privileges in schema "{schema}" grant usage on sequences to {APP_ROLE}')
        )
    print(f"app role {APP_ROLE!r} ready (login, nobypassrls, DML on schema {settings.database_schema})")


if __name__ == "__main__":
    main()
