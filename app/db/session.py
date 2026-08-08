from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {"options": "-c search_path=oryh,public"}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)

if settings.database_url.startswith("postgresql"):
    @event.listens_for(engine, "connect")
    def set_postgres_search_path(dbapi_connection, _connection_record) -> None:
        autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f'SET search_path TO "{settings.database_schema}", public')
        finally:
            cursor.close()
            dbapi_connection.autocommit = autocommit

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# --- Row-Level Security context -------------------------------------------
# Policies key on the app.tenant_id / app.is_platform_admin GUCs. SET LOCAL
# only lives for one transaction and handlers commit mid-request, so the
# authenticated context is kept on session.info and re-applied at the start
# of every transaction.

RLS_TENANT_KEY = "rls_tenant_id"
RLS_PLATFORM_KEY = "rls_platform_admin"


def apply_rls_context(connection, tenant_id: str | None, platform_admin: bool) -> None:
    if connection.dialect.name != "postgresql":
        return
    if tenant_id:
        connection.exec_driver_sql(
            "select set_config('app.tenant_id', %s, true)", (tenant_id,)
        )
    if platform_admin:
        connection.exec_driver_sql(
            "select set_config('app.is_platform_admin', 'on', true)"
        )


@event.listens_for(Session, "after_begin")
def _reapply_rls_context(session: Session, _transaction, connection) -> None:
    apply_rls_context(
        connection,
        session.info.get(RLS_TENANT_KEY),
        bool(session.info.get(RLS_PLATFORM_KEY)),
    )


def bind_tenant_context(db: Session, tenant_id: str) -> None:
    """Bind the session to a tenant for RLS: future transactions get the GUC
    via the after_begin hook; the current one gets it immediately."""
    db.info[RLS_TENANT_KEY] = tenant_id
    apply_rls_context(db.connection(), tenant_id, bool(db.info.get(RLS_PLATFORM_KEY)))


def bind_platform_admin_context(db: Session) -> None:
    db.info[RLS_PLATFORM_KEY] = True
    apply_rls_context(db.connection(), db.info.get(RLS_TENANT_KEY), True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ops_engine_url() -> str:
    """Connection URL for cross-tenant operational scripts (seeding, imports,
    platform bootstrap): the owning role, which is exempt from RLS."""
    return settings.migration_database_url or settings.database_url


def create_ops_sessionmaker() -> sessionmaker:
    url = ops_engine_url()
    args = (
        {"check_same_thread": False}
        if url.startswith("sqlite")
        else {"options": f"-c search_path={settings.database_schema},public"}
    )
    return sessionmaker(
        bind=create_engine(url, future=True, connect_args=args),
        autoflush=False,
        autocommit=False,
        future=True,
    )
