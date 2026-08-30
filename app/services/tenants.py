from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email_domains import registrable_domain
from app.db.session import bind_tenant_context
from app.models import ApiKey, Tenant, generate_api_key, hash_api_key

# Long enough to stay recognizable ("starbridge-consulting"), short enough that
# the longest prefixed skill name (oryh-<slug>-timesheet-approval-flow) stays
# under the 64-character name limit local agent runtimes impose.
SLUG_MAX_LENGTH = 24


def find_tenant_by_company_domain(db: Session, domain: str) -> Tenant | None:
    """Match both canonical domains and legacy tenants stored with a subdomain."""
    exact = db.scalar(select(Tenant).where(Tenant.email_domain == domain))
    if exact is not None:
        return exact
    tenants = db.scalars(select(Tenant).where(Tenant.email_domain.is_not(None))).all()
    for tenant in tenants:
        try:
            if registrable_domain(tenant.email_domain or "") == domain:
                return tenant
        except ValueError:
            continue
    return None


def slugify_domain(email_domain: str | None) -> str:
    """The company's directory name, from the one tenant field that is unique,
    ASCII by construction and immutable: its email domain. `jc-medical.cn` →
    `jc-medical`. The display name cannot serve — it is free-form, mutable and
    routinely CJK."""
    label = (email_domain or "").strip().lower().split(".")[0]
    label = re.sub(r"[^a-z0-9]+", "-", label).strip("-")[:SLUG_MAX_LENGTH].strip("-")
    return label


def derive_tenant_slug(db: Session, email_domain: str | None) -> str:
    """Pick a slug no live tenant holds. Domain uniqueness does not imply slug
    uniqueness (`acme.com` and `acme.cn` both want `acme`, and the first label
    drops the TLD), so collisions get a counter; a domain-less tenant — the
    bootstrap script, older fixtures — falls back to a random one.

    The check-then-insert can still race two SIMULTANEOUS registrations whose
    distinct domains share a base onto the same slug; the unique index then
    rejects the second commit. That is the same benign race the `email_domain`
    unique column already has — the loser gets a 500 and retries into a free
    slug on the next attempt; no duplicate is ever written."""
    base = slugify_domain(email_domain) or f"t-{uuid.uuid4().hex[:8]}"
    candidate = base
    suffix = 2
    while db.scalar(select(Tenant.id).where(Tenant.slug == candidate)) is not None:
        tail = f"-{suffix}"
        candidate = f"{base[: SLUG_MAX_LENGTH - len(tail)].strip('-')}{tail}"
        suffix += 1
    return candidate


def create_tenant_with_api_key(
    db: Session,
    *,
    tenant_name: str,
    tenant_status: str = "active",
    api_key_label: str | None = "default",
) -> tuple[Tenant, ApiKey, str]:
    plain_text_api_key = generate_api_key()
    tenant = Tenant(name=tenant_name, status=tenant_status, slug=derive_tenant_slug(db, None))
    db.add(tenant)
    db.flush()
    # The open-create path runs with no RLS context at all — no caller, no
    # platform flag — so the bootstrap key's insert must carry the new
    # tenant's GUC or a non-owner role is refused by tenant_insert.
    bind_tenant_context(db, tenant.id)
    api_key = ApiKey(
        tenant=tenant,
        key_hash=hash_api_key(plain_text_api_key),
        label=api_key_label,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(tenant)
    db.refresh(api_key)
    return tenant, api_key, plain_text_api_key
