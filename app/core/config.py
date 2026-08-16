import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Where the record API lives under the public origin. Stated once because it
# is stated to two different audiences: every router mounts under it, and every
# skill bundle tells an agent to call it. It was a literal in fourteen places,
# and the places that FORGOT it are why an agent's first call 404'd against the
# site root.
API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    app_name: str = "Oryh API"
    # Which assembly this deployment is: "cloud" mounts the SaaS platform
    # layer (app.saas — registration, the operator console, pilots),
    # "standalone" serves the single-tenant product alone. Empty (the
    # default) resolves by CAPABILITY: cloud when app.saas is importable,
    # standalone when the tree does not carry it — so the private repo and
    # the exported open-core repo both run with no configuration, and the
    # variable exists for the case where a tree that HAS the layer must not
    # mount it (a cloud image run as a standalone instance).
    edition: str = ""
    # What this deployment IS, stated rather than inferred. Every default in
    # this file is chosen so a fresh clone runs unconfigured, which makes every
    # one of them a laptop's default; `production` refuses to start on the ones
    # that are unsafe outside a laptop. See core/deployment_profile.py.
    deployment_profile: str = "development"
    database_url: str = "postgresql+psycopg://ofbiz:ofbiz@127.0.0.1:5432/oryh"
    # Owner/DDL connection for alembic and cross-tenant ops scripts (seed,
    # imports, platform bootstrap). Falls back to database_url when unset.
    # In an RLS deployment database_url uses the restricted oryh_app role
    # while this stays on the owning role.
    migration_database_url: str | None = None
    # Password for the oryh_app runtime role created by
    # scripts/bootstrap_db_roles.py.
    app_db_password: str | None = None
    database_schema: str = "oryh"
    # What to call THIS deployment — "acme-test", "production". Handed
    # to agents beside the tenant identity so the two are separate fields
    # rather than one blur: an agent told only a place name read it as
    # a tenant name and refused a legitimate payment as cross-tenant. Empty
    # means the deployment has no name of its own, which is the honest answer
    # for a single-workspace install and reads that way in the manifest.
    environment_id: str = ""
    # Canonical public URL for links in outbound email. Leave empty in
    # dev/test with no fixed domain: links then follow the address the request
    # actually came in on (see app.core.request_context). Set it in production
    # to the real console domain so links are stable behind proxies.
    base_url: str = ""
    # "console" prints to stdout (dev); "smtp" delivers via the SMTP settings
    # below. smtp_security supports implicit TLS ("ssl") and SMTP STARTTLS
    # ("starttls"). Credentials are optional for IP-authenticated relays such
    # as Google Workspace SMTP Relay; when one credential is set, both are
    # required.
    email_backend: str = "console"
    # No default host: a mail relay is a deployment's own choice, and a
    # provider baked in as the fallback is both a wrong guess for most
    # deployments and our vendor's name in everyone else's config.
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: str = "ssl"
    smtp_user: str | None = None
    smtp_password: str | None = None
    # From address; must match the authenticated mailbox for most providers.
    smtp_from: str | None = None
    smtp_from_name: str = "oryh"
    # Exact email addresses exempt from the corporate-domain registration check.
    registration_email_allowlist: list[str] = []
    # Production keeps review enabled: mailbox verification proves access to
    # an address, while platform review establishes authority to create a
    # company tenant. Self-hosted development may explicitly opt out.
    registration_requires_approval: bool = True
    registration_resend_cooldown_seconds: int = 300
    registration_reapply_cooldown_hours: int = 24
    # Reserved TLDs such as .example are useful in automated tests only.
    allow_reserved_registration_domains: bool = False
    registration_token_ttl_hours: int = 48
    # Legacy unauthenticated POST /tenants; disable in production deployments.
    allow_open_tenant_create: bool = True
    # Standalone first boot (scripts/ensure_standalone_tenant.py): the one
    # workspace and its first administrator. Read once, when the database has
    # no tenant at all; afterwards these are inert. An empty password means
    # "generate one and print it to the log once", which is the right default
    # for a compose file that should work before anyone edits an .env.
    standalone_company_name: str = "我的公司"
    standalone_admin_email: str = "admin@oryh.local"
    standalone_admin_password: str = ""
    invitation_token_ttl_hours: int = 168
    password_reset_token_ttl_minutes: int = 60
    password_reset_resend_cooldown_seconds: int = 300
    session_ttl_hours: int = 168
    # The shared secret ORYH's own flow runner presents to bootstrap itself:
    # to learn which tenants have enabled subscriptions, and to be issued that
    # tenant's hosted credential. Empty (the default) turns the two endpoints
    # off entirely, which is what a deployment without a hosted runner wants.
    #
    # This is the fleet's most sensitive secret — holding it means being able
    # to obtain a hosted credential in any enrolled tenant. It buys the thing
    # a per-tenant credentials file could not: a workspace created at 3am is
    # driven at 3am, with nobody editing a file on the runner host. The file
    # it replaces already held every tenant's key in one place, so the
    # isolation given up was notional under the single-container deployment
    # this actually runs in. See docs/hosted-flow-agent.md.
    flow_runner_bootstrap_token: str = ""
    # Browser device flow (oryh-connect): how long a pending authorization
    # stays approvable, and how often the agent should poll for the result.
    device_code_ttl_minutes: int = 15
    device_poll_interval_seconds: int = 5
    # Brand prefix stamped onto OUTBOUND skill bundles only: installed skill
    # names ({brand}-{slug}-…), the install directory ({brand}-skills-{slug}),
    # and the bootstrap connect skill ({brand}-connect). The registry always
    # stores canonical oryh-* names — this changes rendering, never data — so
    # dev/test/prod servers hand out distinguishable skills (e.g. "calwbiz" on
    # a test box) that install side by side on one laptop. Treat it as fixed
    # per environment: changing it live renames every installed bundle, which
    # agents handle as a full reinstall on their next sync.
    skill_brand: str = "oryh"

    @field_validator("edition")
    @classmethod
    def _validate_edition(cls, value: str) -> str:
        if value not in ("", "cloud", "standalone"):
            raise ValueError("edition must be 'cloud', 'standalone', or unset")
        return value

    @property
    def resolved_edition(self) -> str:
        """The edition this process actually runs: the explicit setting, else
        whatever the source tree is capable of. Import-probing is the honest
        default — a tree without app/saas cannot be a cloud, whatever its
        environment says, and failing louder than ModuleNotFoundError at
        request time is the point of resolving it here."""
        if self.edition:
            return self.edition
        import importlib.util

        return "cloud" if importlib.util.find_spec("app.saas") is not None else "standalone"

    @field_validator("skill_brand")
    @classmethod
    def _validate_skill_brand(cls, value: str) -> str:
        if len(value) > 16 or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value):
            raise ValueError(
                "skill_brand must be lowercase kebab-case, start with a letter, max 16 chars"
            )
        return value

    model_config = SettingsConfigDict(
        env_prefix="ORYH_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
