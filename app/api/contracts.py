"""Contracts: a natural-language file, and the clauses located inside it.

Deliberately not OFBiz's Agreement/AgreementItem/AgreementTerm. The
originals (PDF, scans, Word — any format) live in the attachment store
through ContractDocument links, each carrying the text an agent extracted
from that file with its own tools; ContractTerm rows point at the small
passages that answer the questions people actually ask, tagged by a
tenant-extensible term type and anchored to the file and page they came
from. "付款节奏怎样?" is one lookup by term type — the contract's own words,
verbatim, with the agent's reading beside them — never a re-read.

One functional grant, `contract.manage`, files, curates and advances (the
purchase-order shape: signing is a fact the desk records; review before
signing is the tenant's own todos and approval facts). It is scopable on
the SIDE derived from the counterparty (`:purchase` / `:sales`), and it
gates READS too: a contract carries the prices negotiated with a factory,
and belonging to the workspace does not entitle a credential to them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.common import (
    allocate_number,
    apply_status_change,
    commit_or_conflict,
    delete_document,
    DOCUMENT_FAMILIES,
    ensure_document_editable,
    envelope,
    get_active_document_or_404,
    get_scoped_or_404,
    list_rows,
    normalize_customer_context,
    normalize_vendor_context,
    register_attachment_source,
    requested_pagination,
    require_family_permission,
    require_machine_state,
    restore_document,
    serve_document_attachment,
)
from app.api.deps import Actor, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import (
    Attachment,
    Contract,
    ContractDocument,
    ContractItem,
    ContractTerm,
    Employee,
    Invoice,
    Payment,
    Product,
    PurchaseOrder,
    SalesOrder,
)
from app.schemas import (
    ContractDocumentEnvelope,
    ContractDocumentListEnvelope,
    ContractDocumentRead,
    ContractEnvelope,
    ContractExecutionEnvelope,
    ContractExecutionRead,
    ContractItemEnvelope,
    ContractItemListEnvelope,
    ContractItemRead,
    ContractListEnvelope,
    ContractRead,
    ContractTermEnvelope,
    ContractTermListEnvelope,
    ContractTermRead,
    CreateContractDocumentRequest,
    CreateContractItemRequest,
    CreateContractRequest,
    CreateContractTermRequest,
    UpdateContractDocumentRequest,
    UpdateContractItemRequest,
    UpdateContractRequest,
    UpdateContractTermRequest,
)
from app.services.state_machines import validate_status_filter
from app.services.type_options import require_type_option

router = APIRouter()

# the contract's originals are its attachments, reachable through it
register_attachment_source(Contract, ContractDocument, "contract_id")

SIDES = ("purchase", "sales")


def _require_reader(actor: Actor) -> list[str]:
    """Reads are gated by the filing capability in ANY scope — the list
    itself then shows only the side(s) the credential holds."""
    visible = [side for side in SIDES if has_permission(actor, "contract.manage", side)]
    if not visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "contracts are read by the desk that files them — requires "
                "contract.manage (any scope); ask that desk for the clause you need"
            ),
        )
    return visible


def _side_clause(side: str):
    """Which rows are a side's: purchase contracts name a vendor, sales ones do not."""
    return Contract.vendor_id.is_not(None) if side == "purchase" else Contract.vendor_id.is_(None)


def _require_contract_access(db: Session, actor: Actor, contract_id: str) -> Contract:
    """Reads and writes are gated alike — by the contract's own side."""
    contract = get_active_document_or_404(db, Contract, actor.tenant_id, contract_id)
    require_family_permission(actor, DOCUMENT_FAMILIES[Contract], contract)
    return contract


def _contract_read(db: Session, tenant_id: str, contract: Contract, *, full: bool) -> dict:
    data = ContractRead.model_validate(contract).model_dump(by_alias=True)
    if not full:
        return data
    data["items"] = [
        ContractItemRead.model_validate(row).model_dump(by_alias=True)
        for row in db.scalars(
            select(ContractItem)
            .options(selectinload(ContractItem.product))
            .where(ContractItem.tenant_id == tenant_id, ContractItem.contract_id == contract.id)
            .order_by(ContractItem.line_no.asc(), ContractItem.created_at.asc())
        )
    ]
    data["documents"] = [
        _contract_document_read(row, with_text=False)
        for row in db.scalars(
            select(ContractDocument)
            .where(ContractDocument.tenant_id == tenant_id, ContractDocument.contract_id == contract.id)
            .order_by(
                ContractDocument.sort_order.asc().nulls_last(),
                ContractDocument.page_no.asc().nulls_last(),
                ContractDocument.created_at.asc(),
            )
        )
    ]
    grouped: dict[str, list[dict]] = {}
    for row in db.scalars(
        select(ContractTerm)
        .where(ContractTerm.tenant_id == tenant_id, ContractTerm.contract_id == contract.id)
        .order_by(ContractTerm.sort_order.asc().nulls_last(), ContractTerm.created_at.asc())
    ):
        grouped.setdefault(row.term_type, []).append(
            ContractTermRead.model_validate(row).model_dump(by_alias=True)
        )
    data["terms_by_type"] = grouped
    return data


def _contract_document_read(row: ContractDocument, *, with_text: bool) -> dict:
    data = ContractDocumentRead.model_validate(row).model_dump(by_alias=True)
    data["has_text"] = bool(row.extracted_text)
    if not with_text:
        data.pop("extracted_text", None)
    return data


# --- contracts ----------------------------------------------------------------


@router.get("/contracts", response_model=ContractListEnvelope, response_model_exclude_unset=True)
def list_contracts(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    side: str | None = None,
    contract_type: str | None = None,
    vendor_id: str | None = None,
    customer_id: str | None = None,
    parent_contract_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    visible = _require_reader(actor)
    tenant_id = actor.tenant_id
    validate_status_filter(db, tenant_id, "contract", status_filter)
    stmt = select(Contract).where(Contract.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Contract.deleted_at.is_(None))
    for hidden in SIDES:
        if hidden not in visible:
            stmt = stmt.where(_side_clause(next(s for s in SIDES if s != hidden)))
    if side in SIDES:
        stmt = stmt.where(_side_clause(side))
    return list_rows(
        db, stmt,
        filters={
            Contract.contract_type: contract_type,
            Contract.vendor_id: vendor_id,
            Contract.customer_id: customer_id,
            Contract.parent_contract_id: parent_contract_id,
            Contract.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(Contract.id, String), Contract.contract_no, Contract.title,
            Contract.counterparty_name_snapshot, Contract.summary, Contract.remarks,
        ),
        order_by=(Contract.created_at.desc(), Contract.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ContractRead,
    )


def _resolve_counterparty(db: Session, tenant_id: str, payload) -> tuple[str | None, str | None, str | None]:
    """The side's master-data pointer, checked and backfilling the snapshot."""
    snapshot = payload.counterparty_name_snapshot
    if payload.vendor_id:
        vendor_id, snapshot = normalize_vendor_context(db, tenant_id, payload.vendor_id, snapshot)
        return vendor_id, None, snapshot
    customer_id, snapshot = normalize_customer_context(db, tenant_id, payload.customer_id, snapshot)
    return None, customer_id, snapshot


@router.post("/contracts", response_model=ContractEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: CreateContractRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    side = "purchase" if payload.vendor_id else "sales"
    require_permission(actor, "contract.manage", side)
    require_type_option(db, tenant_id, "contract_type", payload.contract_type)
    vendor_id, customer_id, snapshot = _resolve_counterparty(db, tenant_id, payload)
    if payload.employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    if payload.parent_contract_id:
        get_scoped_or_404(db, Contract, tenant_id, payload.parent_contract_id)
    for line in payload.items:
        if line.product_id:
            get_scoped_or_404(db, Product, tenant_id, line.product_id)
    initial_status = require_machine_state(db, tenant_id, Contract, payload.status)
    contract_no = payload.contract_no or allocate_number(db, Contract, tenant_id)
    contract = Contract(
        tenant_id=tenant_id,
        contract_no=contract_no,
        title=payload.title,
        contract_type=payload.contract_type,
        vendor_id=vendor_id,
        customer_id=customer_id,
        counterparty_name_snapshot=snapshot,
        total_amount=payload.total_amount,
        currency=payload.currency,
        signed_date=payload.signed_date,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        our_signatory=payload.our_signatory,
        counterparty_signatory=payload.counterparty_signatory,
        employee_id=payload.employee_id,
        parent_contract_id=payload.parent_contract_id,
        summary=payload.summary,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    if initial_status == "signed":
        contract.signed_at = datetime.now(timezone.utc)
    db.add(contract)
    try:
        db.flush()
        db.add_all([
            ContractItem(
                tenant_id=tenant_id, contract_id=contract.id,
                line_no=line.line_no if line.line_no is not None else index,
                product_id=line.product_id, description=line.description,
                quantity=line.quantity, unit=line.unit, unit_price=line.unit_price,
                currency=line.currency, delivery_note=line.delivery_note,
                metadata_jsonb=line.metadata,
            )
            for index, line in enumerate(payload.items, start=1)
        ])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"contract_no {contract_no!r} already exists",
        )
    db.refresh(contract)
    return envelope(_contract_read(db, tenant_id, contract, full=True))


@router.get("/contracts/{contract_id}", response_model=ContractEnvelope,
            response_model_exclude_unset=True)
def get_contract(
    contract_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    contract = _require_contract_access(db, actor, contract_id)
    return envelope(_contract_read(db, actor.tenant_id, contract, full=True))


@router.patch("/contracts/{contract_id}", response_model=ContractEnvelope,
              response_model_exclude_unset=True)
def update_contract(
    contract_id: str,
    payload: UpdateContractRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    contract = _require_contract_access(db, actor, contract_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if "contract_type" in updates:
        require_type_option(db, tenant_id, "contract_type", updates["contract_type"])
    if updates.get("employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, updates["employee_id"])
    if updates.get("parent_contract_id"):
        if updates["parent_contract_id"] == contract.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="a contract cannot supplement itself")
        get_scoped_or_404(db, Contract, tenant_id, updates["parent_contract_id"])
    # summary/remarks/custom_fields are the desk's notes and move at any
    # state; the AGREEMENT's own fields obey the machine's editable states
    notes = {"summary", "remarks", "custom_fields", "employee_id"}
    if any(field not in notes for field in updates):
        ensure_document_editable(db, contract)
    if status_change is not None and status_change != contract.status:
        apply_status_change(db, actor, contract, status_change)
        contract.status = status_change
        if status_change == "signed" and contract.signed_at is None:
            contract.signed_at = datetime.now(timezone.utc)
    if "custom_fields" in updates:
        contract.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(contract, field, value)
    db.commit()
    db.refresh(contract)
    return envelope(_contract_read(db, tenant_id, contract, full=False))


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, Contract, contract_id)


@router.post("/contracts/{contract_id}/restore")
def restore_contract(
    contract_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Contract, contract_id)


@router.get("/contracts/{contract_id}/attachments/{attachment_id}/content")
def get_contract_attachment(
    contract_id: str,
    attachment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """An original's bytes, reached through the contract that carries it,
    by the desk that may read the contract."""
    contract = _require_contract_access(db, actor, contract_id)
    return serve_document_attachment(db, actor.tenant_id, contract, attachment_id)


@router.get("/contracts/{contract_id}/execution", response_model=ContractExecutionEnvelope,
            response_model_exclude_unset=True)
def contract_execution(
    contract_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """What has happened under the contract — orders placed, invoices
    billed, payments moved, contracted vs ordered quantity by product —
    derived from the documents that point at it, stored nowhere."""
    tenant_id = actor.tenant_id
    contract = _require_contract_access(db, actor, contract_id)
    order_model = PurchaseOrder if contract.side == "purchase" else SalesOrder
    orders = list(db.scalars(
        select(order_model).where(
            order_model.tenant_id == tenant_id,
            order_model.contract_id == contract.id,
            order_model.deleted_at.is_(None),
        )
    ))
    invoices = list(db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.contract_id == contract.id,
            Invoice.deleted_at.is_(None),
        )
    ))
    payments = list(db.scalars(
        select(Payment).where(
            Payment.tenant_id == tenant_id, Payment.contract_id == contract.id,
            Payment.deleted_at.is_(None),
        )
    ))
    ordered_by_product: dict[str, float] = {}
    if orders:
        # the lines table and its parent column, taken from the family's
        # own relationship so a renamed FK cannot strand this read
        relationship = order_model.__mapper__.relationships["items"]
        item_model = relationship.mapper.class_
        parent_col = next(iter(relationship.remote_side))
        for product_id, total in db.execute(
            select(item_model.product_id, func.sum(item_model.quantity)).where(
                item_model.tenant_id == tenant_id,
                parent_col.in_([o.id for o in orders]),
                item_model.deleted_at.is_(None),
                item_model.product_id.is_not(None),
            ).group_by(item_model.product_id)
        ).all():
            ordered_by_product[product_id] = float(total or 0)
    lines = []
    for item in db.scalars(
        select(ContractItem).options(selectinload(ContractItem.product)).where(
            ContractItem.tenant_id == tenant_id, ContractItem.contract_id == contract.id,
            ContractItem.product_id.is_not(None),
        )
    ):
        lines.append({
            "product_id": item.product_id,
            "product_name": item.product_name,
            "contracted_quantity": float(item.quantity) if item.quantity is not None else None,
            "ordered_quantity": ordered_by_product.get(item.product_id, 0.0),
        })
    return envelope(ContractExecutionRead(
        contract_id=contract.id,
        side=contract.side,
        contracted_amount=float(contract.total_amount) if contract.total_amount is not None else None,
        orders=len(orders),
        ordered_amount=round(sum(float(o.total_amount or 0) for o in orders), 2),
        invoices=len(invoices),
        invoiced_amount=round(sum(float(i.total_amount or 0) for i in invoices), 2),
        payments=len(payments),
        paid_amount=round(sum(float(p.amount or 0) for p in payments), 2),
        lines=lines,
    ).model_dump(by_alias=True))


# --- lines --------------------------------------------------------------------


@router.get("/contract-items", response_model=ContractItemListEnvelope,
            response_model_exclude_unset=True)
def list_contract_items(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    contract_id: str | None = None,
    product_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    _require_reader(actor)
    if contract_id:
        _require_contract_access(db, actor, contract_id)
    stmt = select(ContractItem).options(selectinload(ContractItem.product)).where(ContractItem.tenant_id == actor.tenant_id)
    return list_rows(
        db, stmt,
        filters={ContractItem.contract_id: contract_id, ContractItem.product_id: product_id},
        order_by=(ContractItem.line_no.asc(), ContractItem.created_at.asc()),
        pagination=requested_pagination(page, size),
        read_model=ContractItemRead,
    )


@router.post("/contract-items", response_model=ContractItemEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_contract_item(
    payload: CreateContractItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    contract = _require_contract_access(db, actor, payload.contract_id)
    ensure_document_editable(db, contract)
    if payload.product_id:
        get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    item = ContractItem(
        tenant_id=tenant_id, contract_id=contract.id, line_no=payload.line_no,
        product_id=payload.product_id, description=payload.description,
        quantity=payload.quantity, unit=payload.unit, unit_price=payload.unit_price,
        currency=payload.currency, delivery_note=payload.delivery_note,
        metadata_jsonb=payload.metadata,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return envelope(ContractItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/contract-items/{item_id}", response_model=ContractItemEnvelope,
              response_model_exclude_unset=True)
def update_contract_item(
    item_id: str,
    payload: UpdateContractItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    item = get_scoped_or_404(db, ContractItem, tenant_id, item_id)
    contract = _require_contract_access(db, actor, item.contract_id)
    ensure_document_editable(db, contract)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("product_id"):
        get_scoped_or_404(db, Product, tenant_id, updates["product_id"])
    if "metadata" in updates:
        item.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(ContractItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/contract-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, ContractItem, actor.tenant_id, item_id)
    contract = _require_contract_access(db, actor, item.contract_id)
    ensure_document_editable(db, contract)
    db.delete(item)
    db.commit()
    return None


# --- originals ----------------------------------------------------------------


@router.get("/contract-documents", response_model=ContractDocumentListEnvelope,
            response_model_exclude_unset=True)
def list_contract_documents(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    contract_id: str | None = None,
    document_type: str | None = None,
    # searches the extracted text — "翻卷宗", as opposed to the terms'
    # "翻到那一条"; rows come back with their text when a keyword is given
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    _require_reader(actor)
    if contract_id:
        _require_contract_access(db, actor, contract_id)
    stmt = select(ContractDocument).where(ContractDocument.tenant_id == actor.tenant_id)
    with_text = bool(keyword)
    return list_rows(
        db, stmt,
        filters={ContractDocument.contract_id: contract_id, ContractDocument.document_type: document_type},
        keyword=keyword,
        keyword_columns=(ContractDocument.extracted_text, ContractDocument.caption),
        order_by=(
            ContractDocument.contract_id.asc(),
            ContractDocument.sort_order.asc().nulls_last(),
            ContractDocument.page_no.asc().nulls_last(),
            ContractDocument.created_at.asc(),
        ),
        pagination=requested_pagination(page, size),
        render=lambda rows: [_contract_document_read(row, with_text=with_text) for row in rows],
    )


@router.post("/contract-documents", response_model=ContractDocumentEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_contract_document(
    payload: CreateContractDocumentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    contract = _require_contract_access(db, actor, payload.contract_id)
    require_type_option(db, tenant_id, "contract_document_type", payload.document_type)
    # any format: the store neither reads nor judges bytes, and a contract
    # arrives as a PDF, a folder of scanned pages, a Word file alike
    get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    row = ContractDocument(
        tenant_id=tenant_id, contract_id=contract.id, attachment_id=payload.attachment_id,
        document_type=payload.document_type, sort_order=payload.sort_order,
        page_no=payload.page_no, caption=payload.caption,
        extracted_text=payload.extracted_text, metadata_jsonb=payload.metadata,
    )
    db.add(row)
    commit_or_conflict(db, "this file is already on this contract — PATCH that row")
    db.refresh(row)
    return envelope(_contract_document_read(row, with_text=True))


@router.get("/contract-documents/{document_id}", response_model=ContractDocumentEnvelope,
            response_model_exclude_unset=True)
def get_contract_document(
    document_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, ContractDocument, actor.tenant_id, document_id)
    _require_contract_access(db, actor, row.contract_id)
    return envelope(_contract_document_read(row, with_text=True))


@router.patch("/contract-documents/{document_id}", response_model=ContractDocumentEnvelope,
              response_model_exclude_unset=True)
def update_contract_document(
    document_id: str,
    payload: UpdateContractDocumentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = get_scoped_or_404(db, ContractDocument, tenant_id, document_id)
    _require_contract_access(db, actor, row.contract_id)
    updates = payload.model_dump(exclude_unset=True)
    if "document_type" in updates:
        require_type_option(db, tenant_id, "contract_document_type", updates["document_type"])
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return envelope(_contract_document_read(row, with_text=True))


@router.delete("/contract-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract_document(
    document_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Removes the LINK; the attachment store keeps the bytes. Terms that
    pointed at this file keep their words and lose only their page."""
    row = get_scoped_or_404(db, ContractDocument, actor.tenant_id, document_id)
    _require_contract_access(db, actor, row.contract_id)
    for term in db.scalars(
        select(ContractTerm).where(
            ContractTerm.tenant_id == actor.tenant_id, ContractTerm.document_id == row.id
        )
    ):
        term.document_id = None
    db.delete(row)
    db.commit()
    return None


# --- located clauses ---------------------------------------------------------


@router.get("/contract-terms", response_model=ContractTermListEnvelope,
            response_model_exclude_unset=True)
def list_contract_terms(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    contract_id: str | None = None,
    # THE question: "付款节奏怎样?" is term_type=payment_terms on one contract
    term_type: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    _require_reader(actor)
    if contract_id:
        _require_contract_access(db, actor, contract_id)
    stmt = select(ContractTerm).where(ContractTerm.tenant_id == actor.tenant_id)
    return list_rows(
        db, stmt,
        filters={ContractTerm.contract_id: contract_id, ContractTerm.term_type: term_type},
        keyword=keyword,
        keyword_columns=(ContractTerm.content, ContractTerm.summary, ContractTerm.title,
                         ContractTerm.clause_ref),
        order_by=(
            ContractTerm.contract_id.asc(),
            ContractTerm.sort_order.asc().nulls_last(),
            ContractTerm.created_at.asc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=ContractTermRead,
    )


def _require_term_document(db: Session, tenant_id: str, contract_id: str, document_id: str | None) -> None:
    if document_id is None:
        return
    document = get_scoped_or_404(db, ContractDocument, tenant_id, document_id)
    if document.contract_id != contract_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"document {document_id} belongs to contract {document.contract_id}, not this one",
        )


@router.post("/contract-terms", response_model=ContractTermEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_contract_term(
    payload: CreateContractTermRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    contract = _require_contract_access(db, actor, payload.contract_id)
    require_type_option(db, tenant_id, "contract_term_type", payload.term_type)
    _require_term_document(db, tenant_id, contract.id, payload.document_id)
    term = ContractTerm(
        tenant_id=tenant_id, contract_id=contract.id, term_type=payload.term_type,
        clause_ref=payload.clause_ref, title=payload.title, content=payload.content,
        summary=payload.summary, document_id=payload.document_id, page_no=payload.page_no,
        sort_order=payload.sort_order, metadata_jsonb=payload.metadata,
    )
    db.add(term)
    db.commit()
    db.refresh(term)
    return envelope(ContractTermRead.model_validate(term).model_dump(by_alias=True))


@router.patch("/contract-terms/{term_id}", response_model=ContractTermEnvelope,
              response_model_exclude_unset=True)
def update_contract_term(
    term_id: str,
    payload: UpdateContractTermRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    term = get_scoped_or_404(db, ContractTerm, tenant_id, term_id)
    _require_contract_access(db, actor, term.contract_id)
    updates = payload.model_dump(exclude_unset=True)
    if "term_type" in updates:
        require_type_option(db, tenant_id, "contract_term_type", updates["term_type"])
    if "document_id" in updates:
        _require_term_document(db, tenant_id, term.contract_id, updates["document_id"])
    if "metadata" in updates:
        term.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(term, field, value)
    db.commit()
    db.refresh(term)
    return envelope(ContractTermRead.model_validate(term).model_dump(by_alias=True))


@router.delete("/contract-terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract_term(
    term_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    term = get_scoped_or_404(db, ContractTerm, actor.tenant_id, term_id)
    _require_contract_access(db, actor, term.contract_id)
    db.delete(term)
    db.commit()
    return None
