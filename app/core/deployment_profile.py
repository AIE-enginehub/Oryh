"""What a production deployment must be true of before it serves anything.

Every default in `config.py` is chosen so a fresh clone runs with no
configuration — which is right, and which means every one of them is chosen for
a laptop. `allow_open_tenant_create` defaults to True. `database_url` defaults
to an owner-style account. `base_url` defaults to empty, and an empty
`base_url` makes the app trust the forwarded host it was handed and skip the
Secure flag on its cookies.

None of that is a bug on a laptop and all of it is a bug in production, and
nothing in the system could tell the two apart. The 2026-08-16 architecture
review called this fail-open (5.2), and the fix it asked for is a posture the
operator states rather than one the code infers.

So: `ORYH_DEPLOYMENT_PROFILE=production` refuses to start on any of these
rather than serving with them. The default stays `development`, so a clone, the
test suite and compose are all untouched.

Refusing to start is the point. A warning in a log is a warning nobody reads
until the incident it predicted, and every item here is one an operator can fix
in the minute before the deployment they were already doing.
"""

from __future__ import annotations

from urllib.parse import urlparse

PRODUCTION = "production"
PROFILES = ("development", "test", PRODUCTION)


def _user_of(url: str) -> str | None:
    try:
        return urlparse(url).username
    except ValueError:
        return None


def production_violations(settings) -> list[str]:
    """Everything wrong with this configuration for production, in one pass.

    All of them, not the first: an operator who fixes one and restarts to find
    the next has been made to do the work three times, and the third time is
    the one they do at 2am.
    """
    problems: list[str] = []

    if settings.allow_open_tenant_create:
        problems.append(
            "ORYH_ALLOW_OPEN_TENANT_CREATE is true — the legacy unauthenticated "
            "POST /tenants lets anyone create a workspace"
        )

    if not settings.base_url:
        problems.append(
            "ORYH_BASE_URL is empty — links, origin checks and the cookie Secure flag "
            "would follow whatever Host header a request arrives with"
        )
    elif not settings.base_url.startswith("https://"):
        problems.append(
            f"ORYH_BASE_URL is {settings.base_url!r} — session cookies are only marked "
            "Secure for an https canonical URL"
        )

    migration_url = settings.migration_database_url
    if not migration_url:
        problems.append(
            "ORYH_MIGRATION_DATABASE_URL is unset, so migrations and ops scripts run as "
            "the runtime role — either DDL will fail or the runtime role owns the schema"
        )
    elif migration_url == settings.database_url:
        problems.append(
            "ORYH_DATABASE_URL and ORYH_MIGRATION_DATABASE_URL are the same connection — "
            "the runtime role is the owner, and an owner is not subject to RLS"
        )
    elif _user_of(settings.database_url) == _user_of(migration_url):
        problems.append(
            f"runtime and migration connections are both {_user_of(settings.database_url)!r} — "
            "the restricted runtime role is what makes row-level security apply"
        )

    return problems


def enforce_deployment_profile(settings) -> None:
    """Called once at startup. Raises rather than logs."""
    profile = (settings.deployment_profile or "development").lower()
    if profile not in PROFILES:
        raise RuntimeError(
            f"ORYH_DEPLOYMENT_PROFILE={profile!r} is not one of {PROFILES}"
        )
    if profile != PRODUCTION:
        return
    problems = production_violations(settings)
    if problems:
        listed = "\n  - ".join(problems)
        raise RuntimeError(
            "ORYH_DEPLOYMENT_PROFILE=production, and this configuration is not one:\n  - "
            + listed
        )
