from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessObject, TenantSkill, Todo, User


def dashboard_counts(
    db: Session,
    tenant_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Build the shared tenant-console summary projection.

    Both the legacy Jinja dashboard and the React console API use this service
    while routes are migrated, so the two surfaces cannot silently drift.
    """

    def count(model, *conditions) -> int:
        return db.scalar(
            select(func.count()).select_from(model).where(
                model.tenant_id == tenant_id,
                *conditions,
            )
        ) or 0

    current_time = now or datetime.now(timezone.utc)
    return {
        "users": count(User, User.status == "active"),
        "todos_open": count(Todo, Todo.status == "open"),
        "todos_overdue": count(
            Todo,
            Todo.status == "open",
            Todo.due_at.is_not(None),
            Todo.due_at < current_time,
        ),
        "objects": count(BusinessObject, BusinessObject.deleted_at.is_(None)),
        "skills": count(TenantSkill, TenantSkill.status == "active"),
    }
