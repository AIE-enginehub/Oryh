"""A production profile that is not a production configuration must not serve.

Every default in `config.py` is chosen so a fresh clone runs unconfigured —
`allow_open_tenant_create` true, an owner-style database account, an empty
`base_url` that makes the app trust whatever Host header arrives and drop the
Secure flag from its cookies. All correct on a laptop, all wrong in production,
and nothing in the system could tell the two apart. The 2026-08-16 architecture
review's 5.2.

The posture is now stated rather than inferred, and stating it is checked.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.core.deployment_profile import (
    PROFILES,
    enforce_deployment_profile,
    production_violations,
)


@dataclasses.dataclass
class FakeSettings:
    """A production-ready configuration. Each test breaks exactly one thing."""

    deployment_profile: str = "production"
    allow_open_tenant_create: bool = False
    base_url: str = "https://calwbiz.example"
    database_url: str = "postgresql+psycopg://oryh_app:secret@db:5432/oryh"
    migration_database_url: str | None = "postgresql+psycopg://owner:secret@db:5432/oryh"


def test_a_correct_production_configuration_starts() -> None:
    assert production_violations(FakeSettings()) == []
    enforce_deployment_profile(FakeSettings())


def test_open_tenant_creation_is_refused() -> None:
    problems = production_violations(FakeSettings(allow_open_tenant_create=True))
    assert len(problems) == 1
    assert "POST /tenants" in problems[0]


def test_an_empty_base_url_is_refused() -> None:
    problems = production_violations(FakeSettings(base_url=""))
    assert len(problems) == 1
    assert "Host header" in problems[0]


def test_a_plain_http_base_url_is_refused() -> None:
    """The cookie Secure flag follows the canonical URL, so http here means
    session cookies travel in the clear."""
    problems = production_violations(FakeSettings(base_url="http://calwbiz.example"))
    assert len(problems) == 1
    assert "Secure" in problems[0]


def test_one_connection_for_runtime_and_migrations_is_refused() -> None:
    shared = "postgresql+psycopg://owner:secret@db:5432/oryh"
    problems = production_violations(
        FakeSettings(database_url=shared, migration_database_url=shared)
    )
    assert len(problems) == 1
    assert "not subject to RLS" in problems[0]


def test_the_same_role_on_two_urls_is_refused() -> None:
    """Different URLs, same account — RLS applies to neither."""
    problems = production_violations(FakeSettings(
        database_url="postgresql+psycopg://owner:secret@db-a:5432/oryh",
        migration_database_url="postgresql+psycopg://owner:secret@db-b:5432/oryh",
    ))
    assert len(problems) == 1
    assert "row-level security" in problems[0]


def test_a_missing_migration_url_is_refused() -> None:
    problems = production_violations(FakeSettings(migration_database_url=None))
    assert len(problems) == 1
    assert "ORYH_MIGRATION_DATABASE_URL is unset" in problems[0]


def test_every_violation_is_reported_at_once() -> None:
    """Not the first one. An operator who fixes one, restarts, and finds the
    next has been made to do the work three times — and the third time is the
    one they do at 2am."""
    problems = production_violations(FakeSettings(
        allow_open_tenant_create=True, base_url="", migration_database_url=None,
    ))
    assert len(problems) == 3


def test_the_development_default_is_unaffected() -> None:
    """The whole point of the defaults is that a clone runs unconfigured."""
    enforce_deployment_profile(FakeSettings(
        deployment_profile="development",
        allow_open_tenant_create=True, base_url="", migration_database_url=None,
    ))


def test_an_unknown_profile_is_refused() -> None:
    with pytest.raises(RuntimeError, match="not one of"):
        enforce_deployment_profile(FakeSettings(deployment_profile="staging"))
    assert "production" in PROFILES


def test_enforcement_names_every_problem_in_the_message() -> None:
    with pytest.raises(RuntimeError) as raised:
        enforce_deployment_profile(FakeSettings(
            allow_open_tenant_create=True, base_url="http://x.example",
        ))
    message = str(raised.value)
    assert "POST /tenants" in message and "Secure" in message


def test_the_real_settings_object_carries_the_field() -> None:
    """The tests above use a stand-in; this is what pins them to the thing that
    actually starts the app."""
    from app.core.config import settings

    assert hasattr(settings, "deployment_profile")
    assert settings.deployment_profile in PROFILES
    assert production_violations(settings) is not None
