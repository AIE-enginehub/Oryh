"""The line-item families and everything a line write shares: build, audit, archive.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations




from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    enforce_member_employee,
    require_permission,
)
from app.core.line_math import derive_line_amount
from app.models import (
    ApprovalRecord,
    Attachment,
    Employee,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationItem,
    Todo,
)
from app.schemas import (
    PurchaseOrderItemRead,
    PurchaseRequestItemRead,
    SalesOrderItemRead,
    SalesQuotationItemRead,
)
from app.services.audit import (
    record_audit,
)
from dataclasses import (
    field,
)
from datetime import (
    datetime,
    timezone,
)
from fastapi import (
    Response,
)
from app.api.deps import (
    Actor,
)
from app.api.common.core import (
    ListFilters,
    envelope,
    get_scoped_or_404,
    list_rows,
    require_master_data_manage,
)
from app.api.common.charging import (
    recheck_charged_document,
)
from app.api.common.catalog import (
    catalog_list_price,
    normalize_product_context,
)
from app.api.common.documents import (
    DOCUMENT_FAMILIES,
    ItemFamily,
    _purchase_request_item_for_po_link,
    _sales_order_item_for_link,
    ensure_document_editable,
    get_active_document_or_404,
    get_live_or_404,
    require_live_line,
)

ITEM_FAMILIES: dict[type, ItemFamily] = {
    SalesQuotationItem: ItemFamily(
        SalesQuotation, "quotation_id", "quotation.submit_own", True, SalesQuotationItemRead,
        ("line_no", "tax_rate", "is_gift", "lead_time"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
    ),
    SalesOrderItem: ItemFamily(
        SalesOrder, "order_id", "order.submit_own", True, SalesOrderItemRead,
        ("line_no", "tax_rate", "is_gift", "promised_date"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
        parent_number="order_no",
    ),
    PurchaseOrderItem: ItemFamily(
        PurchaseOrder, "po_id", "purchase_order.manage", False, PurchaseOrderItemRead,
        ("line_no", "tax_rate", "promised_date"),
        link_field="purchase_request_item_id", link_validator=_purchase_request_item_for_po_link,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.asc(), m.id.asc()),
    ),
    PurchaseRequestItem: ItemFamily(
        PurchaseRequest, "request_id", "purchase.submit_own", True, PurchaseRequestItemRead,
        (),
        link_field="sales_order_item_id", link_validator=_sales_order_item_for_link,
        list_order=lambda m: (m.created_at.desc(),),
    ),
}


def employee_names(db: Session, tenant_id: str, ids) -> dict[str, str]:
    """id → name for the employees named, one query."""
    wanted = {value for value in ids if value}
    if not wanted:
        return {}
    return dict(
        db.execute(
            select(Employee.id, Employee.name).where(
                Employee.tenant_id == tenant_id, Employee.id.in_(wanted)
            )
        ).all()
    )


def with_employee_names(db: Session, tenant_id: str, rows: list[dict]) -> list[dict]:
    """`employee_name` beside `employee_id` on rows that carry one — read live,
    never stored, so a renamed person reads under the current name. One query
    per page: an agent confirming who filed a timesheet spent three calls per
    document on this before the name travelled with the record."""
    names = employee_names(db, tenant_id, (row.get("employee_id") for row in rows))
    for row in rows:
        row["employee_name"] = names.get(row.get("employee_id"))
    return rows


def with_employee_name(db: Session, tenant_id: str, row: dict) -> dict:
    return with_employee_names(db, tenant_id, [row])[0]


def reads_with_employee_names(db: Session, tenant_id: str, read_model, rows) -> list[dict]:
    """A list's `render`: the read model's dump, plus the employee's name."""
    return with_employee_names(
        db, tenant_id, [read_model.model_validate(row).model_dump(by_alias=True) for row in rows]
    )


def named_read(db: Session, tenant_id: str, read_model, instance) -> dict:
    """One record's read, plus the employee's name."""
    return with_employee_name(db, tenant_id, read_model.model_validate(instance).model_dump(by_alias=True))


def _item_read(family: ItemFamily, item) -> dict:
    return family.read_model.model_validate(item).model_dump(by_alias=True)


def item_reads(db: Session, family: ItemFamily, rows) -> list[dict]:
    """Lines as dicts, each carrying its document's number when the family
    has one (`order_no` on an order line). A list of lines showed the order
    as a UUID, and a reader asked for it by number fetched every parent."""
    reads = [_item_read(family, row) for row in rows]
    if family.parent_number is None or not reads:
        return reads
    parent = family.parent_model
    ids = {read[family.parent_field] for read in reads}
    numbers = dict(
        db.execute(
            select(parent.id, getattr(parent, family.parent_number)).where(parent.id.in_(ids))
        ).all()
    )
    for read in reads:
        read[family.parent_number] = numbers.get(read[family.parent_field])
    return reads


def _item_write_gate(db: Session, actor: Actor, family: ItemFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_items(
    db: Session, tenant_id: str, model, filters: dict[str, str | None], *, where=(),
    pagination: tuple[int, int] | None = None, sort: str | None = None, extra: ListFilters | None = None,
) -> dict:
    """One list shape for every line family: live lines of live documents,
    equality filters, the family's own ordering. `where` carries the odd
    filter that is not an equality on the line's own column."""
    family = ITEM_FAMILIES[model]
    stmt = (
        select(model)
        .join(family.parent_model, getattr(model, family.parent_field) == family.parent_model.id)
        .where(
            model.tenant_id == tenant_id,
            model.deleted_at.is_(None),
            family.parent_model.deleted_at.is_(None),
            *where,
        )
    )
    return list_rows(
        db, stmt,
        filters={getattr(model, column): value for column, value in filters.items()},
        order_by=family.list_order(model),
        pagination=pagination,
        sort=sort,
        render=lambda rows: item_reads(db, family, rows),
        extra=extra,
    )



def dry_run_readback(db: Session, document, read_model, rows, row_model, key: str, extra: dict | None = None):
    """What a validate-only create would have returned, then nothing written.

    Rendered BEFORE the rollback, while the flushed rows still carry their
    ids and defaults, so the caller sees the exact shape a real write gives
    — minus the ids surviving. The envelope says so in `meta`. One helper
    for every document family: the agent's alternative was write, fail, fix,
    write again, with the person waiting through each round."""
    db.flush()
    data = read_model.model_validate(document).model_dump(by_alias=True)
    data[key] = [row_model.model_validate(row).model_dump(by_alias=True) for row in rows]
    for name, value in (extra or {}).items():
        data[name] = value
    db.rollback()
    return {"data": data, "meta": {"validate_only": True, "written": False}}


def build_item(db: Session, actor: Actor, model, payload, *, parent=None):
    """One validated line, standalone or inline — the single set of rules for
    both paths; the inline path exists to save turns, not to skip checks.

    `parent` passed = the line rides the document's own create: identity comes
    from the parent, and the editable-state gate does not apply — the person is
    stating the document as a whole, including record-won documents created
    directly in a later state."""
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    if parent is None:
        parent_id = getattr(payload, family.parent_field)
        _item_write_gate(db, actor, family, parent_id)
    else:
        named = getattr(payload, family.parent_field)
        if named and named != parent.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "inline items belong to the document being created; "
                    f"do not name another {family.parent_field}"
                ),
            )
        parent_id = parent.id
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    link_id = getattr(payload, family.link_field) if family.link_field else None
    if link_id:
        family.link_validator(db, tenant_id, link_id)
    product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
        db, tenant_id, payload.product_id, payload.sku_id, payload.product_name_snapshot, payload.unit
    )
    if product_id is None and not product_name_snapshot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="an item needs a product_id (or sku_id) or a free-text product_name_snapshot",
        )
    values = {field: getattr(payload, field) for field in family.extra_fields}
    if family.link_field:
        values[family.link_field] = link_id
    if family.capture_list_price:
        list_price_snapshot = payload.list_price_snapshot
        if list_price_snapshot is None and (product_id or sku_id):
            # capture the catalog truth at writing time; an explicit payload
            # value (e.g. a customer-tier price list) wins
            list_price_snapshot = catalog_list_price(
                db, tenant_id, product_id, sku_id, currency=getattr(parent, "currency", None),
            )
        values["list_price_snapshot"] = list_price_snapshot
    item = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent_id},
        product_id=product_id,
        sku_id=sku_id,
        product_name_snapshot=product_name_snapshot,
        spec=payload.spec,
        quantity=payload.quantity,
        unit=unit,
        unit_price=payload.unit_price,
        amount=derive_line_amount(payload.quantity, payload.unit_price, payload.amount,
                                  is_gift=bool(values.get("is_gift"))),
        attachment_id=payload.attachment_id,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
        **values,
    )
    db.add(item)
    db.flush()
    return item


def record_line_audit(
    db: Session,
    actor: Actor,
    parent_model,
    parent_id: str,
    line_id: str,
    verb: str,
    *,
    changed: dict | None = None,
) -> None:
    """Audit a line change against the DOCUMENT it belongs to, not the line.

    An approval is a signature on content, and the trail is what anchors the
    two together. Before this, a document's audit carried its status
    transitions and nothing about the lines — so a timesheet could be approved
    twice, have six entries moved to another project, and be resubmitted, with
    the audit showing three status rows and no trace of the edit at all. That
    is HKG-015, found in production by reading `updated_at`, which is the only
    reason it was reconstructable.

    Written against the parent's id on purpose: an approver, or whoever asks
    later what happened to a document, reads ONE trail. Auditing under the
    line's own id would mean already knowing which lines to ask about, which is
    exactly what the investigation does not know.

    `changed` names the fields, not their values: the audit is a trail, not a
    second copy of the record, and a payslip line's numbers do not belong in a
    log that a wider audience can read than the document itself.
    """
    family = DOCUMENT_FAMILIES.get(parent_model)
    if family is None:                      # a line family whose parent is not a document
        return
    parent = db.get(parent_model, parent_id)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=f"{family.audit_prefix}.{verb}",
        entity_type=family.object_type,
        entity_id=parent_id,
        actor=actor.label,
        detail={
            **(family.audit_identity(parent) if parent is not None else {}),
            "line_id": line_id,
            **({"fields": sorted(changed)} if changed else {}),
        },
    )


def create_item(db: Session, actor: Actor, model, payload) -> dict:
    item = build_item(db, actor, model, payload)
    family = ITEM_FAMILIES[model]
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_added",
    )
    # a new line grows a charged parent's occupation; the guard re-runs here
    # (and only here — deleting a line shrinks, which needs no permission)
    parent = db.get(family.parent_model, getattr(item, family.parent_field))
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(item)
    return envelope(item_reads(db, family, [item])[0])


def get_item(db: Session, tenant_id: str, model, item_id: str) -> dict:
    family = ITEM_FAMILIES[model]
    item = require_live_line(db, tenant_id, model, family.parent_model, family.parent_field, item_id)
    return envelope(item_reads(db, family, [item])[0])


def update_item(db: Session, actor: Actor, model, item_id: str, payload) -> dict:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_live_or_404(db, model, tenant_id, item_id)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    apply_item_updates(db, actor, model, item, payload.model_dump(exclude_unset=True))
    parent = db.get(family.parent_model, getattr(item, family.parent_field))
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(item)
    return envelope(item_reads(db, family, [item])[0])


def apply_item_updates(db: Session, actor: Actor, model, item, updates: dict) -> None:
    """The one set of rules for changing a line — the standalone PATCH and
    the whole-document save both come through here. `updates` is what the
    caller asked for; the audit records those field names."""
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    asked = dict(updates)
    if "attachment_id" in updates and updates["attachment_id"]:
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if family.link_field and updates.get(family.link_field):
        family.link_validator(db, tenant_id, updates[family.link_field])
    if "product_id" in updates or "sku_id" in updates or "product_name_snapshot" in updates or "unit" in updates:
        # changing the product without naming a sku drops the old sku — a
        # stale variant must never survive a product swap
        product_unchanged = updates.get("product_id", item.product_id) == item.product_id
        sku_default = item.sku_id if product_unchanged else None
        product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
            db,
            tenant_id,
            updates.get("product_id", item.product_id),
            updates.get("sku_id", sku_default),
            updates.get("product_name_snapshot", item.product_name_snapshot),
            updates.get("unit", item.unit),
        )
        refs_changed = (product_id, sku_id) != (item.product_id, item.sku_id)
        item.product_id = product_id
        item.sku_id = sku_id
        item.product_name_snapshot = product_name_snapshot
        item.unit = unit
        if family.capture_list_price and refs_changed and "list_price_snapshot" not in updates:
            # the snapshot follows the new reference (None when uncataloged);
            # an old product's price must never survive a product swap
            document = db.get(family.parent_model, getattr(item, family.parent_field))
            item.list_price_snapshot = catalog_list_price(
                db, tenant_id, product_id, sku_id, currency=getattr(document, "currency", None),
            )
        updates.pop("product_id", None)
        updates.pop("sku_id", None)
        updates.pop("product_name_snapshot", None)
        updates.pop("unit", None)
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    # F-28: a stored amount is an override, and an override written for the
    # OLD price is stale the moment the price or quantity changes. Unless this
    # write sets amount itself, drop it so the line reads as price × quantity
    # again (a gift line as 0) — the quotation detail, the flow's tiers and
    # the order's quote_drift all read the effective amount.
    for field, value in updates.items():
        setattr(item, field, value)
    if any(field in updates for field in ("quantity", "unit_price", "is_gift", "amount")):
        # the amount follows the price: a stated one must agree, an unstated
        # one is recomputed (a gift line is 0)
        item.amount = derive_line_amount(
            item.quantity, item.unit_price, updates.get("amount"), is_gift=bool(getattr(item, "is_gift", False)))
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_changed",
        changed=asked,
    )


def delete_item(db: Session, actor: Actor, model, item_id: str) -> Response:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_scoped_or_404(db, model, tenant_id, item_id)
    if item.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    item.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, family.parent_model, getattr(item, family.parent_field),
        item.id, "line_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def archive_row(
    db: Session,
    actor: Actor,
    model,
    row_id: str,
    *,
    permission: str | None = None,
    audit_action: str | None = None,
    audit_entity_type: str | None = None,
    audit_detail=None,
) -> Response:
    """Master data archives, never deletes: existing records keep whatever
    they already reference — archiving only removes the row from what NEW
    records may use, and the history beneath it stays readable.

    `audit_action` is opt-in per family rather than always-on: most families
    here have never written an audit entry for an archive, and turning that on
    for all of them at once is a separate decision from fixing the one family
    whose vocabulary changes silently reinterpret existing records."""
    if permission:
        require_permission(actor, permission)
    else:
        require_master_data_manage(actor)
    row = get_scoped_or_404(db, model, actor.tenant_id, row_id)
    row.status = "archived"
    if audit_action:
        # Stated, not singularized off the table name: `rstrip("s")` is right
        # for `type_options` and wrong the first time a table is not spelled
        # that way, and a wrong entity_type in an audit trail is worse than a
        # missing one — it is a record filed under something that never
        # happened.
        assert audit_entity_type, "audit_action needs audit_entity_type"
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action=audit_action,
            entity_type=audit_entity_type,
            entity_id=row.id,
            actor=actor.label,
            detail=audit_detail(row) if callable(audit_detail) else audit_detail,
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def exclude_rows_with_open_todo(stmt, model, tenant_id: str, entity_type: str):
    """NOT-EXISTS filter for work queues: rows someone already has an open
    todo to act on are hidden, leaving what still needs an assignment
    (e.g. status=submitted&without_open_todo=true)."""
    return stmt.where(
        ~select(Todo.id)
        .where(
            Todo.tenant_id == tenant_id,
            Todo.entity_type == entity_type,
            Todo.entity_id == model.id,
            Todo.status == "open",
        )
        .exists()
    )


def document_approvals(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> list:
    """The approval trail every /detail carries, in workflow order."""
    return db.scalars(
        select(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
        )
        .order_by(ApprovalRecord.round_no.asc(), ApprovalRecord.sequence_no.asc(), ApprovalRecord.acted_at.asc())
    ).all()


def attachments_for_items(db: Session, tenant_id: str, items) -> list:
    attachment_ids = {item.attachment_id for item in items if item.attachment_id}
    if not attachment_ids:
        return []
    return db.scalars(
        select(Attachment).where(Attachment.tenant_id == tenant_id, Attachment.id.in_(attachment_ids))
    ).all()
