from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, permissions_cover
from app.models import Role, Tenant, User


def lock_tenant_identity(db: Session, tenant_id: str) -> None:
    """Serialize identity mutations on one stable tenant row.

    PostgreSQL's row lock prevents concurrent user/role updates from each
    observing the other's old state and jointly removing the final manager.
    SQLite ignores ``FOR UPDATE``, which is sufficient for unit tests.
    """
    db.scalar(
        select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
    )


def tenant_has_active_user_manager(
    db: Session,
    tenant_id: str,
    *,
    user_overrides: Mapping[str, tuple[str, str]] | None = None,
    role_permission_overrides: Mapping[str, Iterable[str]] | None = None,
) -> bool:
    """Return whether the simulated tenant state keeps a human manager.

    Tenant-level service keys remain an operational recovery credential, but
    identity-management mutations must not leave a SaaS tenant without any
    active user whose role covers ``users.manage``.
    """
    lock_tenant_identity(db, tenant_id)
    roles = {
        role.name: frozenset(role.permissions_jsonb)
        for role in db.scalars(select(Role).where(Role.tenant_id == tenant_id))
    }
    for role_name, permissions in (role_permission_overrides or {}).items():
        roles[role_name] = frozenset(permissions)

    overrides = user_overrides or {}
    seen_users: set[str] = set()
    active_users = db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.status == "active")
    )
    for user in active_users:
        seen_users.add(user.id)
        status, role_name = overrides.get(user.id, (user.status, user.role))
        if status != "active":
            continue
        permissions = roles.get(
            role_name,
            frozenset(DEFAULT_ROLE_PERMISSIONS.get(role_name, ())),
        )
        if permissions_cover(permissions, "users.manage"):
            return True

    # A verified disabled user may be activated by this mutation and therefore
    # will not have appeared in the active-user query above.
    for user_id, (status, role_name) in overrides.items():
        if user_id in seen_users or status != "active":
            continue
        permissions = roles.get(
            role_name,
            frozenset(DEFAULT_ROLE_PERMISSIONS.get(role_name, ())),
        )
        if permissions_cover(permissions, "users.manage"):
            return True
    return False
