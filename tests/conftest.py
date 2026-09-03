"""Test-suite guards and the shared app-client factory.

Guards run before any app module is imported.  The developer's .env may
select the smtp email backend with real credentials; tests must never
deliver real mail, so force the console backend here (os.environ has
priority over the env file in pydantic-settings)."""

import os

os.environ["ORYH_EMAIL_BACKEND"] = "console"
# Most legacy behavior tests exercise tenant APIs after self-service signup.
# Dedicated registration-review tests enable the production approval posture.
os.environ["ORYH_REGISTRATION_REQUIRES_APPROVAL"] = "false"
os.environ["ORYH_ALLOW_RESERVED_REGISTRATION_DOMAINS"] = "true"
os.environ.pop("ORYH_SMTP_USER", None)
os.environ.pop("ORYH_SMTP_PASSWORD", None)
# app.db.session binds its engine to this URL at import time; tests run on
# per-test in-memory sqlite, never on whatever .env points at.
os.environ["ORYH_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, bind_tenant_context, get_db
from app.main import app
from app.services.emails import outbox

# Rows to insert before the app first sees the database: model instances,
# or a callable receiving the session when inserts need flush ordering.
Seed = Iterable[object] | Callable[[Session], None]


def _fresh_db(seed: Seed | None) -> tuple[Engine, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    if seed is not None:
        with factory() as db:
            if callable(seed):
                seed(db)
            else:
                db.add_all(list(seed))
            db.commit()
    return engine, factory


@contextmanager
def make_stack(seed: Seed | None = None) -> Generator[tuple[TestClient, Engine], None, None]:
    """The app client plus its engine, on a fresh seeded schema."""
    engine, factory = _fresh_db(seed)

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    outbox.clear()
    try:
        with TestClient(app) as client:
            # `provision_tenant` needs a session of its own, and reaching for
            # the override's generator from a helper is worse than saying so.
            client.session_factory = factory
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        outbox.clear()
        Base.metadata.drop_all(bind=engine)


@contextmanager
def make_client(seed: Seed | None = None) -> Generator[TestClient, None, None]:
    """The plain app client — the shape almost every test file wants."""
    with make_stack(seed) as (client, _engine):
        yield client


@contextmanager
def make_session(seed: Seed | None = None) -> Generator[Session, None, None]:
    """A bare ORM session on a fresh seeded schema — no HTTP app involved."""
    engine, factory = _fresh_db(seed)
    try:
        with factory() as session:
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)


def provision_tenant(
    client: TestClient,
    *,
    company_name: str = "Test Co",
    email: str = "admin@test-co.example",
    password: str = "admin-pass1",
) -> dict:
    """Create a tenant with an active admin and a bootstrap service key.

    Tests used to reach for `POST /auth/register` + `/auth/verify-email`,
    which made the whole suite depend on the SaaS registration surface — the
    one thing an open-core tree deliberately does not carry, so the exported
    suite could not run at all. Nothing here is about registration: a test
    that needs A tenant is not testing how strangers get one.

    This is the same act `provision_registration` and
    `ensure_standalone_tenant` perform, and it returns the shape
    `/auth/verify-email` returned, so call sites kept their assertions.
    Registration itself is still tested — from `tests/saas/`, against the
    endpoints, where it belongs.
    """
    from app.api.auth import start_session
    from app.core.security import hash_password
    from app.models import ApiKey, Tenant, User, generate_api_key, hash_api_key
    from app.schemas import ApiKeyRead, TenantRead, UserRead
    from app.services.provisioning import provision_tenant_defaults
    from app.services.tenants import derive_tenant_slug

    domain = email.rsplit("@", 1)[1]
    with client.session_factory() as db:
        tenant = Tenant(
            name=company_name,
            email_domain=domain,
            slug=derive_tenant_slug(db, domain),
        )
        db.add(tenant)
        db.flush()
        bind_tenant_context(db, tenant.id)
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
        )
        plain_text_api_key = generate_api_key()
        api_key = ApiKey(
            tenant_id=tenant.id,
            key_hash=hash_api_key(plain_text_api_key),
            label="bootstrap",
            role="service",
        )
        db.add_all([user, api_key])
        provision_tenant_defaults(db, tenant.id)
        session_token, _ = start_session(db, user)
        db.commit()
        db.refresh(tenant)
        db.refresh(user)
        db.refresh(api_key)
        return {
            "tenant": TenantRead.model_validate(tenant).model_dump(),
            "user": UserRead.model_validate(user).model_dump(),
            "api_key": ApiKeyRead.model_validate(api_key).model_dump(),
            "plain_text_api_key": plain_text_api_key,
            "session_token": session_token,
        }


def invite_member(
    client: TestClient,
    admin: dict,
    name: str,
    permissions: list[str],
    *,
    employee_id: str | None = None,
    domain: str = "example.test",
) -> dict:
    """A credential holding exactly these capabilities, the way a real
    member gets one: a role, an invitation (optionally bound to an
    employee), acceptance, a user-bound key. Returns the auth header.

    Forty test files used to carry this dance inline, twelve lines each,
    and every one of them differed in something that did not matter."""
    client.post("/api/v1/roles", json={"name": name, "permissions": permissions},
                headers=admin)
    body = {"email": f"{name}@{domain}", "role": name}
    if employee_id:
        body["employee_id"] = employee_id
    invited = client.post("/api/v1/auth/invitations", json=body, headers=admin)
    assert invited.status_code == 201, invited.text
    user_id = invited.json()["data"]["id"]
    token = next(line.rsplit("token=", 1)[1].strip()
                 for line in outbox.messages[-1].body.splitlines() if "token=" in line)
    client.post("/api/v1/auth/invitations/accept",
                json={"token": token, "password": "invitee-pass1"})
    key = client.post("/api/v1/tenant/api-keys", json={"label": name, "user_id": user_id},
                      headers=admin).json()["data"]["plain_text_api_key"]
    return {"X-API-Key": key}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """App client on an empty database.  A file that needs rows pre-seeded
    overrides this fixture with `with make_client(<seed>) as c: yield c`."""
    with make_client() as test_client:
        yield test_client


@pytest.fixture()
def stack() -> Generator[tuple[TestClient, Engine], None, None]:
    """(client, engine) for tests that also instrument the engine."""
    with make_stack() as pair:
        yield pair
