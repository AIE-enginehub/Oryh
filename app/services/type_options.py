"""Validation against the tenant's type vocabularies.

The write path for every *_type/*_category field: the schema pins the name
shape, this layer decides whether the value exists for THIS tenant — shipped
catalog plus custom entries, minus archived ones. A tenant with no rows for
a family has not customized it, so the shipped catalog applies verbatim
(also what keeps a freshly migrated deployment working before the per-tenant
seed runs).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.type_options import (
    SIGNED_TYPE_FAMILIES,
    SYSTEM_TYPE_OPTIONS,
    system_type_names,
    system_type_sign,
)
from app.models import TypeOption


def allowed_type_options(db: Session, tenant_id: str, family: str) -> frozenset[str]:
    """Values new records may use for this family, tenant vocabulary applied."""
    rows = db.execute(
        select(TypeOption.name, TypeOption.status).where(
            TypeOption.tenant_id == tenant_id, TypeOption.family == family
        )
    ).all()
    if not rows:
        return system_type_names(family)
    return frozenset(name for name, row_status in rows if row_status == "active")


def require_type_option(db: Session, tenant_id: str, family: str, value: str) -> None:
    allowed = allowed_type_options(db, tenant_id, family)
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"unknown {family} '{value}' — active options: {', '.join(sorted(allowed))}. "
                "Custom values are defined via POST /type-options."
            ),
        )


def type_option_error(db: Session, tenant_id: str, family: str, values: set[str]) -> str | None:
    """Bulk-friendly variant: one message naming every bad value, or None."""
    allowed = allowed_type_options(db, tenant_id, family)
    unknown = sorted(values - allowed)
    if not unknown:
        return None
    return (
        f"unknown {family} {', '.join(unknown)} — active options: {', '.join(sorted(allowed))}"
    )


def type_option_sign(db: Session, tenant_id: str, family: str, name: str) -> int | None:
    """Which way this kind of value moves money, as the tenant's own catalog
    declares it — falling back to the shipped sign for a family the tenant has
    never customized (the same fallback `allowed_type_options` keeps)."""
    stored = db.execute(
        select(TypeOption.sign).where(
            TypeOption.tenant_id == tenant_id,
            TypeOption.family == family,
            TypeOption.name == name,
        )
    ).scalar_one_or_none()
    if stored is not None:
        return stored
    return system_type_sign(family, name)


__all__ = [
    "SIGNED_TYPE_FAMILIES",
    "SYSTEM_TYPE_OPTIONS",
    "allowed_type_options",
    "require_type_option",
    "type_option_error",
    "type_option_sign",
]
