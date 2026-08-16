"""A real PostgreSQL, for the things SQLite cannot be asked about.

The main suite runs on in-memory SQLite through one connection. That is the
right default — it is fast, it needs nothing installed, and it catches most
things. It cannot catch any of these:

  * a lost update between two transactions, because there is only one
  * `FOR UPDATE`, which SQLite parses and ignores
  * RLS policies and the restricted runtime role
  * `NUMERIC` arithmetic, as opposed to float
  * whether the Alembic chain actually builds the schema the models assume —
    SQLite tests call `Base.metadata.create_all` and never run a migration

The 2026-08-16 architecture review put the financial lost-update at P0 and the
SQLite-only suite at P1. They are one finding: the race survived 1108 passing
tests because no test could express two connections.

These tests skip unless `ORYH_TEST_POSTGRES_URL` names a database this file may
DROP AND RECREATE the schema in. `scripts/run_postgres_tests.sh` starts a
throwaway container and sets it. Nothing here runs against a database anyone
cares about, and the guard below refuses the ones that look like they are.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_URL = os.environ.get("ORYH_TEST_POSTGRES_URL", "")
SCHEMA = "oryh"

needs_postgres = pytest.mark.skipif(
    not TEST_URL,
    reason="set ORYH_TEST_POSTGRES_URL (scripts/run_postgres_tests.sh starts one)",
)


def _refuse_a_database_somebody_needs(url: str) -> None:
    """The schema is dropped and rebuilt here. A URL pointing anywhere real is
    a mistake worth failing loudly on rather than discovering afterwards."""
    lowered = url.lower()
    for marker in ("rds.aliyuncs", "prod", "hkg", "oryh.ai", "banff-tech"):
        if marker in lowered:
            raise RuntimeError(
                f"ORYH_TEST_POSTGRES_URL looks like a real deployment ({marker!r}); "
                "these tests drop and recreate the schema"
            )


@pytest.fixture(scope="session")
def pg_url() -> str:
    if not TEST_URL:
        pytest.skip("no ORYH_TEST_POSTGRES_URL")
    _refuse_a_database_somebody_needs(TEST_URL)
    return TEST_URL


@pytest.fixture(scope="session")
def pg_schema(pg_url: str) -> str:
    """A schema built by the real migration chain, once per session.

    `alembic upgrade head` rather than `create_all`: half the point of having a
    PostgreSQL layer at all is proving the migrations produce the schema the
    models expect, which the SQLite suite structurally cannot ask.
    """
    import alembic.command
    import alembic.config

    engine = create_engine(pg_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(f'drop schema if exists "{SCHEMA}" cascade'))
        conn.execute(text(f'create schema "{SCHEMA}"'))
    engine.dispose()

    config = alembic.config.Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", pg_url)
    alembic.command.upgrade(config, "head")
    return SCHEMA


@pytest.fixture()
def pg_sessionmaker(pg_url: str, pg_schema: str):
    """Sessions on independent connections — the whole reason this file exists.

    NullPool so two sessions never share one connection: with pooling they can,
    and a "concurrency" test on one connection proves nothing.
    """
    from sqlalchemy.pool import NullPool

    engine = create_engine(
        pg_url,
        future=True,
        poolclass=NullPool,
        connect_args={"options": f"-c search_path={pg_schema},public"},
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    engine.dispose()


@pytest.fixture()
def clean_tables(pg_sessionmaker):
    """Truncate between tests. Faster than rebuilding the schema, and it keeps
    the migration chain running exactly once."""
    yield
    with pg_sessionmaker() as db:
        rows = db.execute(
            text(
                "select tablename from pg_tables where schemaname = :s "
                "and tablename <> 'alembic_version'"
            ),
            {"s": SCHEMA},
        ).scalars().all()
        if rows:
            joined = ", ".join(f'"{SCHEMA}"."{name}"' for name in rows)
            db.execute(text(f"truncate {joined} restart identity cascade"))
            db.commit()
