"""A role's grants, one way.

A person's capability set is entirely their role's. Five places used to read
it — the API's own authentication, the bundle renderer, the reach report, the
identity guard, the key issuer — and they disagreed on one thing: whether a
tenant provisioned before roles were rows (the shipped defaults answer for
those) got the defaults or nothing. Authentication fell back; the bundle did
not, so a legacy member could call the API and receive an empty bundle.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.models import Role


def role_permissions(db: Session, tenant_id: str) -> dict[str, frozenset[str]]:
    """{role name: its grants} for the tenant's own role rows."""
    return {
        role.name: frozenset(role.permissions_jsonb or ())
        for role in db.scalars(select(Role).where(Role.tenant_id == tenant_id)).all()
    }


def role_grants(roles: Mapping[str, frozenset[str]], role_name: str) -> frozenset[str]:
    """One role's grants from a tenant's role map — the shipped defaults when
    the tenant has no row for it (legacy tenants before role provisioning). A
    row with no grants is exactly that: no grants, not the defaults."""
    if role_name in roles:
        return roles[role_name]
    return frozenset(DEFAULT_ROLE_PERMISSIONS.get(role_name, ()))


def permissions_of_role(db: Session, tenant_id: str, role_name: str) -> frozenset[str]:
    """One role's grants, with the same fallback."""
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name))
    if role is not None:
        return frozenset(role.permissions_jsonb or ())
    return frozenset(DEFAULT_ROLE_PERMISSIONS.get(role_name, ()))
