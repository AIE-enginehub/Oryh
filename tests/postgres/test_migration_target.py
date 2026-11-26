"""Schema reset and Alembic upgrade must share the disposable test target."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from app.core.config import settings
from tests.postgres.conftest import _refuse_a_database_somebody_needs


@pytest.mark.parametrize("setting,value", [
    ("migration_database_url", "postgresql+psycopg://localhost/another_database"),
    ("database_schema", "another_schema"),
])
def test_conflicting_test_target_is_refused_before_connecting(monkeypatch, setting, value):
    url = "postgresql+psycopg://localhost/disposable"
    monkeypatch.setattr(settings, "database_schema", "oryh")
    monkeypatch.setattr(settings, "migration_database_url", url)
    monkeypatch.setattr(settings, setting, value)
    with pytest.raises(RuntimeError, match="test target"):
        _refuse_a_database_somebody_needs(url)


def test_upgrade_uses_the_callers_transaction(pg_url, pg_schema, monkeypatch):
    # With an already migrated test DB this upgrade has nothing to apply.
    # A second connection must never be opened, even when app settings say otherwise.
    monkeypatch.setattr(settings, "migration_database_url", "sqlite:///:memory:")
    monkeypatch.setattr("sqlalchemy.engine_from_config",
                        lambda *a, **kw: pytest.fail("Alembic opened a second engine"))
    engine = create_engine(pg_url)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert connection.in_transaction()
    finally:
        engine.dispose()
