"""The cost centre a document books against — plan
docs/plans/budgets-2026-10-27.md, phase 3.

A document books against the centre its writer names, and only that one:
which centre a claim, request, order or bill is for — the employee's home
centre, the request's, the payee's — is the agent's judgement, read from
the workspace's rule, not a default the server infers. A centre named on a
write must be this workspace's and active (`_check_cost_centres`, at flush,
whichever endpoint, import or bridge wrote it); one archived later stays on
what already names it.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.models import (
    Budget,
    CostCenter,
    Employee,
    ExpenseClaim,
    Invoice,
    PurchaseOrder,
    PurchaseRequest,
)


def centres_under(db: Session, tenant_id: str, root: str) -> set[str]:
    """A centre and every centre beneath it."""
    children: dict[str | None, list[str]] = {}
    for node, parent in db.execute(select(CostCenter.id, CostCenter.parent_id).where(CostCenter.tenant_id == tenant_id)):
        children.setdefault(parent, []).append(node)
    found, stack = {root}, [root]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


CARRIERS = (Employee, ExpenseClaim, PurchaseRequest, PurchaseOrder, Invoice, Budget)


@event.listens_for(Session, "before_flush")
def _check_cost_centres(session: Session, flush_context, instances) -> None:
    """A centre named on a write must be this workspace's and active. A
    centre archived later stays on what already names it."""
    candidates = [obj for obj in (*session.new, *session.dirty) if isinstance(obj, CARRIERS)]
    if not candidates:
        return
    with session.no_autoflush:
        for document in candidates:
            if document.cost_center_id is None:
                continue
            if document not in session.new and not inspect(document).attrs.cost_center_id.history.has_changes():
                continue
            centre = session.get(CostCenter, document.cost_center_id)
            if centre is None or centre.tenant_id != document.tenant_id:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f"cost_center_id: cost centre {document.cost_center_id} does not exist")
            if centre.status != "active":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f"cost_center_id: cost centre {centre.cost_center_code} is archived")
