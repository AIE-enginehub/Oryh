from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    actor: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append an audit log entry in the caller's transaction: committed if and
    only if the business write commits. This is a read-only trail for
    troubleshooting and accountability — NOT a delivery mechanism. Agent
    coordination goes through todos and state queries."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            detail_jsonb=detail or {},
        )
    )
