from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import settings
import app.models  # noqa: F401
from app.db.session import Base


config = context.config
# Migrations run with the owning role; the runtime URL may be the restricted
# oryh_app role which cannot run DDL.
config.set_main_option(
    "sqlalchemy.url", settings.migration_database_url or settings.database_url
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def resolve_version_table_schema(connection) -> str | None:
    if connection.dialect.name != "postgresql":
        return None
    target_schema = settings.database_schema
    target_exists = connection.execute(
        text("select to_regclass(:relation_name)"),
        {"relation_name": f"{target_schema}.alembic_version"},
    ).scalar()
    if target_exists:
        return target_schema
    public_exists = connection.execute(
        text("select to_regclass('public.alembic_version')"),
    ).scalar()
    if public_exists:
        return "public"
    return target_schema


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=settings.database_schema if url.startswith("postgresql") else None,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        version_table_schema = resolve_version_table_schema(connection)
        if connection.dialect.name == "postgresql":
            connection.execute(text(f'create schema if not exists "{settings.database_schema}"'))
            connection.execute(text(f'SET search_path TO "{settings.database_schema}", public'))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            version_table_schema=version_table_schema,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
