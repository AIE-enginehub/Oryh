"""Rename the legacy brand schema for existing PostgreSQL deployments.

Revision ID: 20260713_0018
Revises: 20260711_0017
Create Date: 2026-07-13 10:00:00

Fresh installations already create the ``oryh`` schema through the earlier
migrations.  Installations upgraded from the previous product name have their
tables in the legacy schema; this revision moves that schema without copying
or rewriting tenant data.
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0018"
down_revision = "20260711_0017"
branch_labels = None
depends_on = None

LEGACY_SCHEMA = "calwbiz"
CURRENT_SCHEMA = "oryh"


def _schema_exists(schema: str) -> bool:
    return bool(
        op.get_bind()
        .exec_driver_sql("select exists(select 1 from information_schema.schemata where schema_name = %s)", (schema,))
        .scalar()
    )


def _schema_has_tables(schema: str) -> bool:
    return bool(
        op.get_bind()
        .exec_driver_sql(
            "select exists(select 1 from information_schema.tables where table_schema = %s)",
            (schema,),
        )
        .scalar()
    )


def upgrade() -> None:
    if not _schema_exists(LEGACY_SCHEMA):
        return
    if _schema_exists(CURRENT_SCHEMA):
        if _schema_has_tables(CURRENT_SCHEMA):
            raise RuntimeError(
                "both the legacy and Oryh schemas contain tables; run the brand migration before Alembic"
            )
        op.execute(f'drop schema "{CURRENT_SCHEMA}"')
    op.execute(f'alter schema "{LEGACY_SCHEMA}" rename to "{CURRENT_SCHEMA}"')


def downgrade() -> None:
    if _schema_exists(CURRENT_SCHEMA) and not _schema_exists(LEGACY_SCHEMA):
        op.execute(f'alter schema "{CURRENT_SCHEMA}" rename to "{LEGACY_SCHEMA}"')
