"""Reaching an attachment through its document, and the catalog context a line resolves against.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations



from urllib.parse import quote

from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import Session

import hashlib
from app.models import (
    Attachment,
    Product,
    ProductSku,
)
from fastapi import (
    Response,
)
from app.api.common.core import (
    get_scoped_or_404,
)

# --- reaching an attachment's bytes ----------------------------------------
#
# Holding an attachment's id is not authorisation to read it. Attachments are
# standalone blobs by design — `Attachment` carries no back-link, because
# linking is the referencing object's job — and `GET /attachments/{id}/content`
# honoured that literally: tenant scope and nothing else. A credential with no
# payroll capability could read a payslip's PDF, which is the one read
# `tests/test_payroll_visibility.py` opens by calling "the first read in this
# API that belonging to the workspace does not entitle you to".
#
# So the bytes are reached THROUGH the document that carries them. The document
# already knows who may see it — `ensure_invoice_visible`, `ensure_policy_visible`
# and the rest were written for exactly that question — and the caller has to
# name it, which makes the authorisation explicit at every call site instead of
# implicit in an id nobody can trace.
#
# `attachment_id` on the model that actually holds it: header for the three
# single-document families, line items for the five with lines.
ATTACHMENT_SOURCES: dict[type, tuple[type | None, str | None]] = {}


def register_attachment_source(document_model: type, item_model=None, parent_field: str | None = None) -> None:
    """Where this family keeps the attachment ids reachable from one document.

    Declared by each family's own module, so a new family that forgets to
    register is a family whose attachments are unreachable — visibly, on the
    first read — rather than one whose attachments are reachable by anyone.
    """
    ATTACHMENT_SOURCES[document_model] = (item_model, parent_field)


def document_attachment_ids(db: Session, tenant_id: str, document) -> set[str]:
    """Every attachment this one document carries, header and lines."""
    item_model, parent_field = ATTACHMENT_SOURCES[type(document)]
    if item_model is None:
        return {document.attachment_id} - {None}
    rows = db.scalars(
        select(item_model.attachment_id).where(
            item_model.tenant_id == tenant_id,
            getattr(item_model, parent_field) == document.id,
            item_model.attachment_id.is_not(None),
        )
    ).all()
    return set(rows)


def serve_document_attachment(db: Session, tenant_id: str, document, attachment_id: str) -> Response:
    """The bytes, once the caller has proved they may read the document.

    Callers MUST apply the family's own visibility check before calling this —
    it verifies only that the attachment belongs to the document named, which
    is the other half. 404 for an attachment the document does not carry: an
    id that is real but unrelated must not read differently from one that is
    not real, or the endpoint becomes an oracle for what exists.
    """
    if attachment_id not in document_attachment_ids(db, tenant_id, document):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    attachment = get_scoped_or_404(db, Attachment, tenant_id, attachment_id)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}"},
    )


def load_item_catalog_context(db: Session, tenant_id: str, items) -> tuple[dict, dict, set]:
    """(skus_by_id, products_by_id, products_with_skus) for a set of lines —
    the three maps every /detail needs to label its lines, in three reads
    regardless of how many lines the document has."""
    sku_ids = {item.sku_id for item in items if item.sku_id}
    skus = (
        db.scalars(
            select(ProductSku).where(ProductSku.tenant_id == tenant_id, ProductSku.id.in_(sku_ids))
        ).all()
        if sku_ids
        else []
    )
    skus_by_id = {sku.id: sku for sku in skus}
    item_product_ids = {item.product_id for item in items if item.product_id}
    products_with_skus = (
        set(
            db.scalars(
                select(ProductSku.product_id)
                .where(
                    ProductSku.tenant_id == tenant_id,
                    ProductSku.product_id.in_(item_product_ids),
                    ProductSku.status == "active",
                )
                .group_by(ProductSku.product_id)
            ).all()
        )
        if item_product_ids
        else set()
    )
    product_ids = set(item_product_ids)
    product_ids.update(sku.product_id for sku in skus)
    products = (
        db.scalars(
            select(Product).where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
        ).all()
        if product_ids
        else []
    )
    return skus_by_id, {product.id: product for product in products}, products_with_skus


def resolve_item_refs(item, skus_by_id: dict, products_by_id: dict) -> tuple:
    """(product, sku) for one line, from the catalog context maps."""
    sku = skus_by_id.get(item.sku_id) if item.sku_id else None
    if sku is not None and item.product_id is not None and sku.product_id != item.product_id:
        # Defensive against historic/corrupt cross-product references: do
        # not attach a misleading label even though writes now prevent it.
        sku = None
    product_id = item.product_id or (sku.product_id if sku is not None else None)
    return (products_by_id.get(product_id) if product_id else None), sku


def sku_pending_flag(item, products_with_skus: set) -> bool:
    """A variant product quoted/ordered at product level: the SKU decision
    is still open — surfaced so reviewers see 尺码待定 at a glance."""
    return bool(item.product_id and not item.sku_id and item.product_id in products_with_skus)


def normalize_product_context(
    db: Session,
    tenant_id: str,
    product_id: str | None,
    sku_id: str | None,
    product_name_snapshot: str | None,
    unit: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Same contract as `claims.py`'s normalize_project_context: real records
    (404 otherwise) and backfill the free-text name/unit snapshots; without
    them, the free text stands alone. A sku alone derives its product; a sku
    given with a mismatching product is a 400 — the pair must agree."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if product_id and product_id != sku.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to the given product_id",
            )
        product_id = sku.product_id
    if not product_id:
        return None, None, product_name_snapshot, unit
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return product.id, sku_id, product_name_snapshot or product.name, unit or product.unit


def catalog_list_price(
    db: Session, tenant_id: str, product_id: str | None, sku_id: str | None, *, currency: str | None = None,
) -> float | None:
    """The catalog reference price for a line: sku price overrides product
    price; None when the catalog is silent. Captured onto the line as
    list_price_snapshot so the discount stays derivable after catalog edits.
    When the document's `currency` is given and the catalog prices the
    product in another one, the answer is None: a CNY list price beside a
    USD unit price reads as an 87% discount (E-20), and no snapshot is
    better than a wrong one."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        product = get_scoped_or_404(db, Product, tenant_id, sku.product_id)
        if currency and product.currency and product.currency.upper() != currency.upper():
            return None
        if sku.list_price is not None:
            return float(sku.list_price)
        return float(product.list_price) if product.list_price is not None else None
    if product_id:
        product = get_scoped_or_404(db, Product, tenant_id, product_id)
        if currency and product.currency and product.currency.upper() != currency.upper():
            return None
        return float(product.list_price) if product.list_price is not None else None
    return None


def doc_number_lock_key(scope: str, tenant_id: str) -> int:
    digest = hashlib.sha256()
    for value in (scope, tenant_id):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)
