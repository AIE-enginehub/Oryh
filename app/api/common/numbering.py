"""Document numbers under a lock, master-data code conflicts, and the bulk-import tail.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations




from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    has_permission,
    require_permission,
)
from app.models import (
    Customer,
    Employee,
    Product,
    Project,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    Resource,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
    Vendor,
)
from app.schemas import (
    PurchaseOrderAdjustmentRead,
    SalesOrderAdjustmentRead,
    SalesQuotationAdjustmentRead,
)
from app.services import (
    document_import,
)
from app.services.audit import (
    record_audit,
)
from app.services.state_machines import (
    get_builtin_machine,
)
from dataclasses import (
    dataclass,
    field,
)
from sqlalchemy import (
    text,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from app.api.deps import (
    Actor,
)
from app.api.common.core import (
    envelope,
)
from app.api.common.catalog import (
    doc_number_lock_key,
)

def allocate_document_number(
    db: Session, tenant_id: str, *, model, number_column, prefix: str, lock_scope: str, field: str
) -> str:
    """Next {prefix}NNNNNN for the tenant. Serialized with a transaction-scoped
    advisory lock on PostgreSQL (same idiom as workflow version allocation);
    SQLite (unit tests) has no equivalent and is single-writer anyway.
    Numbers are never reused — soft-deleted documents keep theirs, and the
    unique constraint stays the backstop for agent-supplied numbers."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("select pg_advisory_xact_lock(cast(:lock_key as bigint))"),
            {"lock_key": doc_number_lock_key(lock_scope, tenant_id)},
        )
    latest = db.scalar(
        select(func.max(number_column)).where(
            model.tenant_id == tenant_id,
            # fixed-width suffix: lexicographic max == numeric max
            number_column.like(prefix + "______"),
        )
    )
    try:
        seq = int(latest[len(prefix):]) + 1 if latest else 1
    except ValueError:
        # a tenant-supplied number happens to match the width pattern —
        # restart low and let the existence probe walk past collisions
        seq = 1
    for _ in range(100):
        candidate = f"{prefix}{seq:06d}"
        exists = db.scalar(
            select(model.id)
            .where(model.tenant_id == tenant_id, number_column == candidate)
            .limit(1)
        )
        if exists is None:
            return candidate
        seq += 1
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"unable to allocate a number; supply {field} explicitly",
    )


def ensure_content_edit_allowed(actor: Actor, family: str, updates: dict) -> None:
    """A document's own fields are the submitter's write; only `status` is the
    flow's.

    Status is guarded where it is applied, by the family's `advance` verb. The
    rest of the header is what a person reported — their hours, their narrative,
    their claim — so changing it takes the same capability that filed it. This
    changes nothing for the tenant's own credentials: a member editing their own
    header holds `submit_own` and has already passed the own-employee check, and
    admins and tenant service keys hold or bypass everything. It draws the line
    for a principal that may advance a flow while being nobody in the company —
    ORYH's hosted agent can move a timesheet to `approved`, and cannot touch a
    word of what the employee wrote."""
    if any(field != "status" for field in updates):
        require_permission(actor, f"{family}.submit_own")


MASTER_CODE_FIELDS = {
    Project: ("project_code", "project"),
    Vendor: ("vendor_code", "vendor"),
    Customer: ("customer_code", "customer"),
    Product: ("product_code", "product"),
    Employee: ("employee_code", "employee"),
    Resource: ("code", "resource"),
}


def commit_or_conflict(db: Session, detail: str) -> None:
    """Commit, or turn the unique index's refusal into a 409 that says what
    collided. The index is the invariant; this is its sentence — every
    family that owns a "one live X per scope" rule ends its write here."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def commit_or_code_conflict(db: Session, row) -> None:
    """Commit a master-data write; a duplicate code becomes a 409 that names
    the holder instead of a 500.

    A live E2E run hit this with a project: the unique index has enforced
    per-tenant codes on postgres since the baseline migration, but no create
    or update here caught IntegrityError, so re-using an ARCHIVED project's
    code surfaced as Internal Server Error. The holder's status matters in
    the message for exactly that reason — the person cannot see an archived
    twin in their default list view, so "already exists" alone reads as a
    lie.
    """
    model = type(row)
    code_field, noun = MASTER_CODE_FIELDS[model]
    code_value = getattr(row, code_field)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not code_value:
            raise
        holder = db.scalar(
            select(model).where(
                model.tenant_id == row.tenant_id,
                getattr(model, code_field) == code_value,
            )
        )
        if holder is None:
            raise
        detail = f"{code_field} {code_value!r} already belongs to {noun} {holder.id}"
        status_value = getattr(holder, "status", None)
        if status_value and status_value != "active":
            detail += (
                f" (status: {status_value} — it keeps its code; "
                "restore it or pick another code)"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _finish_bulk_import(db: Session, actor: Actor, result: dict, *, action: str, detail: dict) -> dict:
    """Rollback-or-audit-and-commit tail shared by every bulk import. The
    audit records the import as ONE event with its counts, not one entry per
    row — 500 near-identical rows would bury the trail. An import spans many
    rows, so there is no single entity to anchor to (and `entity_id` is a
    uuid column): it anchors to the tenant whose data changed.
    """
    if not result["applied"]:
        db.rollback()
        return envelope(result)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=action,
        entity_type="tenant",
        entity_id=actor.tenant_id,
        actor=actor.label,
        detail={**detail, **result["summary"]},
    )
    db.commit()
    return envelope(result)


def _run_document_import(*, db: Session, actor: Actor, family: str, payload) -> dict:
    """Shared tail for the historical-document imports. Gated on the family's
    own submit capability — importing history is still writing that family's
    documents — and audited as ONE event with its counts, like master data."""
    spec = document_import.FAMILIES[family]
    if spec.get("scope_by_direction"):
        # Invoicing is a function, but scopable: a 期初 file usually carries
        # both directions, so the import needs the capability for both rather
        # than one side of it.
        for direction in ("sales", "purchase"):
            if any(row.direction == direction for row in payload.rows):
                require_permission(actor, spec["permission"], direction)
    else:
        # purchase orders and payments are FUNCTIONS, not "my documents": the
        # single capability that files one files a thousand historical ones
        require_permission(actor, spec["permission"])
    if spec.get("acts_for_others") and actor.kind == "user" and not has_permission(actor, "tenant.act_for_any_employee"):
        # A migration writes documents belonging to MANY salespeople, which the
        # single-document endpoints forbid via enforce_member_employee. Rather
        # than checking row by row — every historical document names someone
        # else — the endpoint requires the capability that lifts the own-employee
        # limit outright, so a plain member key cannot backfill history under a
        # colleague's name.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "importing historical documents writes records for other employees — "
                "requires capability tenant.act_for_any_employee"
            ),
        )
    machine = get_builtin_machine(db, actor.tenant_id, spec["label"])
    result = document_import.bulk_import_documents(
        db,
        tenant_id=actor.tenant_id,
        family=family,
        rows=payload.rows,
        machine_states=set(machine.get("states", ())),
        initial_state=machine["initial"],
        dry_run=payload.dry_run,
        on_error=payload.on_error,
        on_missing_reference=payload.on_missing_reference,
    )
    return _finish_bulk_import(
        db, actor, result,
        action=f"{spec['label']}.imported",
        detail={"on_error": payload.on_error, "on_missing_reference": payload.on_missing_reference},
    )


@dataclass(frozen=True)
class AdjustmentFamily:
    """The three adjustment families (quotation / sales order / purchase
    order) behave identically by construction — same fields, same vocabulary,
    same editable-state gate. What differs is data: the models, the two FK
    names, the capability, and whether the parent has an owner to enforce."""

    parent_model: type
    item_model: type
    parent_field: str
    item_field: str
    permission: str
    owner_checked: bool
    read_model: type


ADJUSTMENT_FAMILIES: dict[type, AdjustmentFamily] = {
    SalesQuotationAdjustment: AdjustmentFamily(
        SalesQuotation, SalesQuotationItem, "quotation_id", "quotation_item_id",
        "quotation.submit_own", True, SalesQuotationAdjustmentRead,
    ),
    SalesOrderAdjustment: AdjustmentFamily(
        SalesOrder, SalesOrderItem, "order_id", "order_item_id",
        "order.submit_own", True, SalesOrderAdjustmentRead,
    ),
    PurchaseOrderAdjustment: AdjustmentFamily(
        PurchaseOrder, PurchaseOrderItem, "po_id", "po_item_id",
        # procurement is a function, not "my documents": one capability, no owner
        "purchase_order.manage", False, PurchaseOrderAdjustmentRead,
    ),
}
