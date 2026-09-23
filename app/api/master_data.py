"""The reference data every document points at: who you trade with, and what.

Split out of `routes.py`: vendors, customers, products, the optional SKU level
under a product, the price book beside a product's own list_price, supplier
products, and inventory items with their append-only detail ledger.

"Master data" is this codebase's own word for the group, not a borrowed one —
`app/services/master_data_import.py` already backs the four `/bulk` endpoints
that live here, and `MASTER_CODE_FIELDS` in `common.py` names the code column
each of these types is unique on.

Nothing here creates a document. That is what makes the cut clean: quotations,
orders and invoices READ this data through `common.py` — `catalog_list_price`,
`resolve_item_refs`, `normalize_product_context` — and never through here.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

import math
import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.registry import KEYWORD, ORDER_BY, PAGE, SIZE, STATUS, GetResource, ListResource, Param, register
from app.api.common import (
    ListFilters,
    list_filters,
    ensure_document_not_deleted,
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    _finish_bulk_import,
    archive_row,
    commit_or_code_conflict,
    commit_or_conflict,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    page_only_pagination,
    register_attachment_source,
    require_active_row,
    require_master_data_manage,
    serve_document_attachment,
    status_scope,
    rows_revision,
    save_rows,
    soft_remove,
)
from app.api.geo import customer_territory
from app.api.deps import Actor, attributed, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import (
    Employee,
    Attachment,
    BillOfMaterials,
    BomItem,
    Customer,
    CustomerContact,
    CustomerProduct,
    ExternalProductMap,
    normalize_external_name,
    Facility,
    InventoryItem,
    InventoryItemDetail,
    PurchaseOrder,
    SalesChannel,
    Store,
    StoreFacility,
    SalesOrder,
    SalesOrderItem,
    Product,
    ProductCategory,
    ProductImage,
    ProductPrice,
    ProductSku,
    SupplierProduct,
    Vendor,
)
from app.schemas import (
    BatchCreateProductSkusEnvelope,
    BatchCreateProductSkusRequest,
    BulkCustomerUpsertRequest,
    BulkInventoryUpsertRequest,
    BulkProductUpsertRequest,
    BulkUpsertEnvelope,
    BulkVendorUpsertRequest,
    CreateCustomerRequest,
    ReleaseStockRequest,
    ReserveStockRequest,
    StockReservationEnvelope,
    StockReservationLineRead,
    StockReservationRead,
    CreateInventoryItemRequest,
    CreateProductPriceRequest,
    CreateFacilityRequest,
    CreateProductCategoryRequest,
    CreateProductRequest,
    CreateExternalProductMapRequest,
    CreateProductSkuRequest,
    CreateSupplierProductRequest,
    CreateVendorRequest,
    ExternalProductMapEnvelope,
    ExternalProductMapListEnvelope,
    FacilityEnvelope,
    FacilityListEnvelope,
    FacilityRead,
    ExternalProductMapRead,
    BillOfMaterialsEnvelope,
    BillOfMaterialsListEnvelope,
    BillOfMaterialsRead,
    BomExplodeEnvelope,
    BomExplodeRead,
    BomExplodedLineRead,
    BomItemEnvelope,
    BomItemListEnvelope,
    BomItemRead,
    BomLeafRequirementRead,
    CreateBillOfMaterialsRequest,
    CreateBomItemRequest,
    CreateProductImageRequest,
    ProductImageEnvelope,
    ProductImageListEnvelope,
    ProductImageRead,
    UpdateProductImageRequest,
    CreateCustomerContactRequest,
    CreateCustomerProductRequest,
    CustomerContactEnvelope,
    CustomerContactListEnvelope,
    CustomerContactRead,
    CustomerDetailEnvelope,
    CustomerEnvelope,
    CustomerProductEnvelope,
    CustomerProductListEnvelope,
    CustomerProductRead,
    CustomerListEnvelope,
    CustomerRead,
    InventoryItemDetailEnvelope,
    InventoryItemDetailListEnvelope,
    InventoryItemDetailRead,
    InventoryItemEnvelope,
    InventoryItemListEnvelope,
    InventoryItemRead,
    ProductCategoryEnvelope,
    ProductCategoryListEnvelope,
    ProductCategoryRead,
    ProductEnvelope,
    ProductListEnvelope,
    ProductPriceEnvelope,
    ProductPriceListEnvelope,
    ProductPriceRead,
    ProductRead,
    ProductSkuEnvelope,
    ProductSkuListEnvelope,
    ProductSkuRead,
    SupplierProductEnvelope,
    SupplierProductListEnvelope,
    SupplierProductRead,
    UpdateBillOfMaterialsRequest,
    UpdateBomItemRequest,
    UpdateCustomerContactRequest,
    UpdateCustomerProductRequest,
    UpdateCustomerRequest,
    ResolveExternalProductsRequest,
    UpdateExternalProductMapRequest,
    UpdateInventoryItemRequest,
    UpdateProductPriceRequest,
    CreateStoreFacilityRequest,
    CreateSalesChannelRequest,
    CreateStoreRequest,
    StoreEnvelope,
    StoreFacilityEnvelope,
    StoreFacilityListEnvelope,
    StoreFacilityRead,
    SalesChannelEnvelope,
    SalesChannelListEnvelope,
    SalesChannelRead,
    StoreListEnvelope,
    StoreRead,
    UpdateFacilityRequest,
    UpdateProductCategoryRequest,
    UpdateStoreFacilityRequest,
    UpdateSalesChannelRequest,
    UpdateStoreRequest,
    UpdateProductRequest,
    UpdateProductSkuRequest,
    UpdateSupplierProductRequest,
    UpdateVendorRequest,
    VendorEnvelope,
    VendorListEnvelope,
    VendorRead,
    SaveBomLinesRequest,
    SavedLinesEnvelope,
    BomItemBase,
)
from app.services.inventory_import import _find_item, bulk_inventory_upsert, post_inventory_detail
from app.services.state_machines import get_builtin_machine, is_terminal_state
from app.services.master_data_import import bulk_upsert
from app.services.type_options import require_type_option

router = APIRouter()


# --- products and their SKUs: the identity race these helpers close --------


def get_locked_product_or_404(db: Session, tenant_id: str, product_id: str) -> Product:
    """Lock the SKU parent row before checking or changing variant identity.

    Product SKU variants are stored as free-form JSON, so a portable database
    uniqueness constraint cannot express their full equality. Serializing all
    identity-changing paths on the parent product closes that race instead.
    """
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def existing_product_sku_variant_attrs(
    db: Session,
    tenant_id: str,
    product_id: str,
    *,
    exclude_sku_id: str | None = None,
) -> list[dict]:
    stmt = select(ProductSku.variant_attrs).where(
        ProductSku.tenant_id == tenant_id,
        ProductSku.product_id == product_id,
    )
    if exclude_sku_id is not None:
        stmt = stmt.where(ProductSku.id != exclude_sku_id)
    return [attrs or {} for attrs in db.scalars(stmt).all()]


def json_value_identity(value):
    """Return a hashable, JSON-type-aware identity for a decoded value.

    Python considers ``True == 1`` and ``False == 0``. JSON does not: booleans
    and numbers are different value types. Tag every JSON type before comparing
    recursively so variant identity follows JSON semantics while retaining
    numeric equivalence such as ``1 == 1.0``.
    """
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(json_value_identity(item) for item in value))
    if isinstance(value, dict):
        return (
            "object",
            tuple(
                sorted(
                    (key, json_value_identity(item))
                    for key, item in value.items()
                )
            ),
        )
    # ``variant_attrs`` comes from JSON request bodies / JSON(B) columns, so
    # reaching this branch indicates corrupt or non-JSON application data.
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def ensure_product_sku_variant_attrs_available(
    db: Session,
    tenant_id: str,
    product_id: str,
    variant_attrs: dict,
    *,
    exclude_sku_id: str | None = None,
) -> None:
    # Empty attributes describe no variant identity and remain valid for legacy
    # and SKU-code-only catalogs. Only a non-empty exact JSON combination is
    # reserved.
    existing_identities = {
        json_value_identity(attrs)
        for attrs in existing_product_sku_variant_attrs(
            db,
            tenant_id,
            product_id,
            exclude_sku_id=exclude_sku_id,
        )
    }
    if variant_attrs and json_value_identity(variant_attrs) in existing_identities:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU with identical variant attributes already exists for this product",
        )


def product_sku_stats(
    db: Session,
    tenant_id: str,
    product_ids: list[str],
) -> dict[str, tuple[int, int]]:
    if not product_ids:
        return {}

    rows = db.execute(
        select(
            ProductSku.product_id,
            func.count(),
            func.sum(case((ProductSku.status == "active", 1), else_=0)),
        )
        .where(ProductSku.tenant_id == tenant_id, ProductSku.product_id.in_(product_ids))
        .group_by(ProductSku.product_id)
    ).all()
    return {product_id: (int(total), int(active or 0)) for product_id, total, active in rows}


def product_reads_with_sku_stats(db: Session, tenant_id: str, products) -> list[dict]:
    """Product reads carrying their variant counts — one stats query however
    many rows the page has."""
    ids = [product.id for product in products]
    stats = product_sku_stats(db, tenant_id, ids)
    primaries: dict[str, str] = {}
    if ids:
        primaries = {
            product_id: image_id
            for product_id, image_id in db.execute(
                select(ProductImage.product_id, ProductImage.id).where(
                    ProductImage.tenant_id == tenant_id,
                    ProductImage.product_id.in_(ids),
                    ProductImage.is_primary.is_(True),
                )
            ).all()
        }
    data = []
    for product in products:
        read = ProductRead.model_validate(product)
        total, active = stats.get(product.id, (0, 0))
        read.sku_count = total
        read.has_skus = active > 0
        read.primary_image_id = primaries.get(product.id)
        data.append(read.model_dump(by_alias=True))
    return data


def product_read_with_skus_flag(db: Session, product: Product) -> dict:
    return product_reads_with_sku_stats(db, product.tenant_id, [product])[0]


# --- vendors and customers: the two sides you trade with -------------------


@router.post(
    "/vendors",
    response_model=VendorEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor(
    payload: CreateVendorRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Vendor, actor.tenant_id, "vendor_code", payload.vendor_code)
    vendor = Vendor(
        tenant_id=actor.tenant_id,
        vendor_code=payload.vendor_code,
        name=payload.name,
        tax_id=payload.tax_id,
        contact=payload.contact,
        email=payload.email,
        phone=payload.phone,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(vendor)
    commit_or_code_conflict(db, vendor)
    db.refresh(vendor)
    return envelope(VendorRead.model_validate(vendor).model_dump(by_alias=True))


@router.patch("/vendors/{vendor_id}", response_model=VendorEnvelope, response_model_exclude_unset=True)
def update_vendor(
    vendor_id: str,
    payload: UpdateVendorRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    vendor = get_scoped_or_404(db, Vendor, actor.tenant_id, vendor_id)
    updates = payload.model_dump(exclude_unset=True)
    if "vendor_code" in updates:
        ensure_code_available(
            db, Vendor, actor.tenant_id, "vendor_code", updates["vendor_code"], exclude_id=vendor.id
        )
    if "metadata" in updates:
        vendor.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(vendor, field, value)
    commit_or_code_conflict(db, vendor)
    db.refresh(vendor)
    return envelope(VendorRead.model_validate(vendor).model_dump(by_alias=True))


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor(
    vendor_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Vendor, vendor_id)


@router.post(
    "/customers",
    response_model=CustomerEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    payload: CreateCustomerRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Customer, actor.tenant_id, "customer_code", payload.customer_code)
    if payload.customer_type is not None:
        require_type_option(db, actor.tenant_id, "customer_type", payload.customer_type)
    if payload.owner_employee_id:
        get_scoped_or_404(db, Employee, actor.tenant_id, payload.owner_employee_id)
    customer = Customer(
        tenant_id=actor.tenant_id,
        customer_code=payload.customer_code,
        name=payload.name,
        customer_kind=payload.customer_kind,
        customer_type=payload.customer_type,
        tax_id=payload.tax_id,
        contact=payload.contact,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        geo_id=payload.geo_id,
        territory_id=customer_territory(db, actor.tenant_id, payload.geo_id, payload.territory_id),
        owner_employee_id=payload.owner_employee_id,
        payment_terms=payload.payment_terms,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(customer)
    commit_or_code_conflict(db, customer)
    db.refresh(customer)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.get("/customers/{customer_id}/detail", response_model=CustomerDetailEnvelope, response_model_exclude_unset=True)
def get_customer_detail(
    customer_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """What a visit brief needs, in one read (F-16): the people, the open
    deals, the last ten contacts, what is scheduled, the last ten messages,
    the recent quotations and orders, and the territory covering it."""
    from app.models import Activity, CommunicationEvent, Event, Opportunity, SalesOrder, SalesQuotation, Territory
    from app.schemas import (
        ActivityRead, CommunicationEventRead, CustomerDetailRead, EventRead, OpportunityRead,
        SalesOrderRead, SalesQuotationRead, TerritoryRead,
    )
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)

    def recent(model, order_column, *, live=True, limit=10):
        stmt = select(model).where(model.tenant_id == tenant_id, model.customer_id == customer.id)
        if live and hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return db.scalars(stmt.order_by(order_column.desc()).limit(limit)).all()

    contacts = db.scalars(select(CustomerContact).where(
        CustomerContact.tenant_id == tenant_id, CustomerContact.customer_id == customer.id,
    ).order_by(CustomerContact.is_primary.desc(), CustomerContact.created_at.asc())).all()
    territory = db.get(Territory, customer.territory_id) if customer.territory_id else None
    detail = CustomerDetailRead(
        customer=CustomerRead.model_validate(customer),
        contacts=[CustomerContactRead.model_validate(c) for c in contacts],
        opportunities=[OpportunityRead.model_validate(o) for o in recent(Opportunity, Opportunity.created_at)],
        activities=[ActivityRead.model_validate(a) for a in recent(Activity, Activity.occurred_at)],
        events=[EventRead.model_validate(e) for e in recent(Event, Event.starts_at)],
        communications=[CommunicationEventRead.model_validate(c) for c in recent(CommunicationEvent, CommunicationEvent.occurred_at)],
        quotations=[SalesQuotationRead.model_validate(q) for q in recent(SalesQuotation, SalesQuotation.created_at, limit=5)],
        orders=[SalesOrderRead.model_validate(o) for o in recent(SalesOrder, SalesOrder.created_at, limit=5)],
        territory=TerritoryRead.model_validate(territory) if territory is not None else None,
    )
    return envelope(detail.model_dump(by_alias=True))


@router.patch("/customers/{customer_id}", response_model=CustomerEnvelope, response_model_exclude_unset=True)
def update_customer(
    customer_id: str,
    payload: UpdateCustomerRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    customer = get_scoped_or_404(db, Customer, actor.tenant_id, customer_id)
    updates = payload.model_dump(exclude_unset=True)
    if "customer_code" in updates:
        ensure_code_available(
            db, Customer, actor.tenant_id, "customer_code", updates["customer_code"],
            exclude_id=customer.id,
        )
    if updates.get("customer_type") is not None:
        require_type_option(db, actor.tenant_id, "customer_type", updates["customer_type"])
    if "geo_id" in updates or "territory_id" in updates or "owner_employee_id" in updates:
        geo_id = updates.get("geo_id", customer.geo_id)
        # a geo change re-resolves the territory unless one was named in the same write
        territory_id = updates["territory_id"] if "territory_id" in updates else (
            None if "geo_id" in updates else customer.territory_id
        )
        updates["territory_id"] = customer_territory(db, actor.tenant_id, geo_id, territory_id)
        if updates.get("owner_employee_id"):
            get_scoped_or_404(db, Employee, actor.tenant_id, updates["owner_employee_id"])
    if "metadata" in updates:
        customer.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(customer, field, value)
    commit_or_code_conflict(db, customer)
    db.refresh(customer)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Customer, customer_id)


# --- stores and facilities: where you sell, and where you ship from ---------


@router.post("/facilities", response_model=FacilityEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_facility(
    payload: CreateFacilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "facility_type", payload.facility_type)
    ensure_code_available(db, Facility, tenant_id, "facility_code", payload.facility_code)
    facility = Facility(
        tenant_id=tenant_id,
        facility_code=payload.facility_code,
        name=payload.name,
        facility_type=payload.facility_type,
        address=payload.address,
        remarks=payload.remarks,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(facility)
    commit_or_conflict(db, (
                        f"an active facility named {payload.name!r} already exists — the "
                        "stock ledger joins on this name, so two live facilities cannot share it"
                    ))
    db.refresh(facility)
    return envelope(FacilityRead.model_validate(facility).model_dump(by_alias=True))


@router.patch("/facilities/{facility_id}", response_model=FacilityEnvelope,
              response_model_exclude_unset=True)
def update_facility(
    facility_id: str,
    payload: UpdateFacilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    facility = get_scoped_or_404(db, Facility, tenant_id, facility_id)
    updates = payload.model_dump(exclude_unset=True)
    if "facility_type" in updates:
        require_type_option(db, tenant_id, "facility_type", updates["facility_type"])
    if "facility_code" in updates:
        ensure_code_available(
            db, Facility, tenant_id, "facility_code", updates["facility_code"],
            exclude_id=facility.id,
        )
    if "metadata" in updates:
        facility.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(facility, field, value)
    commit_or_conflict(db, "an active facility with this name already exists")
    db.refresh(facility)
    return envelope(FacilityRead.model_validate(facility).model_dump(by_alias=True))


@router.delete("/facilities/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(
    facility_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Facility, facility_id)


# --- sales channels: the keys orders arrive under, as master data ----------


def require_sales_channel(db: Session, tenant_id: str, *, source: str | None = None,
                          channel_id: str | None = None) -> SalesChannel | None:
    """The channel a store or a map row names, by id or by its code. An
    unregistered code is the row's error to take back to the person —
    never a channel to invent — and an archived one names its fix."""
    if channel_id is not None:
        return require_active_row(db, SalesChannel, tenant_id, channel_id, "sales channel")
    if source is None:
        return None
    channel = db.scalar(select(SalesChannel).where(
        SalesChannel.tenant_id == tenant_id, SalesChannel.channel_code == source,
    ))
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"no sales channel with code {source!r} — register it first "
                "(POST /sales-channels), never invent one"
            ),
        )
    return require_active_row(db, SalesChannel, tenant_id, channel.id, "sales channel")


def _resolve_store_channel(db: Session, tenant_id: str, fields: dict) -> None:
    """A store names its channel by `sales_channel_id` or by `source`; both
    collapse to the FK before the row is written."""
    source = fields.pop("source", None)
    if "sales_channel_id" in fields or source is not None:
        channel = require_sales_channel(
            db, tenant_id, source=source, channel_id=fields.get("sales_channel_id"),
        )
        fields["sales_channel_id"] = channel.id if channel is not None else None


@router.post("/sales-channels", response_model=SalesChannelEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_sales_channel(
    payload: CreateSalesChannelRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "sales_channel_kind", payload.channel_kind)
    existing = db.scalar(select(SalesChannel).where(
        SalesChannel.tenant_id == tenant_id, SalesChannel.channel_code == payload.channel_code,
    ))
    if existing is not None:
        # the code is the key three tables join on: a lapsed channel and a
        # new one with the same code are the same channel, so it revives
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"sales channel {existing.id} already carries code {payload.channel_code!r} "
                f"({existing.status}) — PATCH it; an archived channel revives by setting status active"
            ),
        )
    channel = SalesChannel(
        tenant_id=tenant_id,
        channel_code=payload.channel_code,
        name=payload.name,
        channel_kind=payload.channel_kind,
        remarks=payload.remarks,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(channel)
    commit_or_conflict(db, f"an active sales channel named {payload.name!r} already exists")
    db.refresh(channel)
    return envelope(SalesChannelRead.model_validate(channel).model_dump(by_alias=True))


@router.patch("/sales-channels/{channel_id}", response_model=SalesChannelEnvelope,
              response_model_exclude_unset=True)
def update_sales_channel(
    channel_id: str,
    payload: UpdateSalesChannelRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    channel = get_scoped_or_404(db, SalesChannel, tenant_id, channel_id)
    updates = payload.model_dump(exclude_unset=True)
    if "channel_kind" in updates:
        require_type_option(db, tenant_id, "sales_channel_kind", updates["channel_kind"])
    if "metadata" in updates:
        channel.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(channel, field, value)
    commit_or_conflict(db, "an active sales channel with this name already exists")
    db.refresh(channel)
    return envelope(SalesChannelRead.model_validate(channel).model_dump(by_alias=True))


@router.delete("/sales-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_channel(
    channel_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, SalesChannel, channel_id)


@router.get("/stores", response_model=StoreListEnvelope, response_model_exclude_unset=True)
def list_stores(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    channel: str | None = None,
    source: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(Store, ranges=('created_at',), equals=('sales_channel_id',)))] = None,
):
    stmt = select(Store).options(selectinload(Store.sales_channel)).where(Store.tenant_id == tenant_id)
    if source:
        stmt = stmt.where(Store.sales_channel.has(SalesChannel.channel_code == source.strip().lower()))

    def with_fulfilment(stores) -> list[dict]:
        # the same standing list the single read carries (E-24: a null here
        # read as "this store has no warehouse") — one grouped query per page
        data = [StoreRead.model_validate(store).model_dump(by_alias=True) for store in stores]
        by_store: dict[str, list[dict]] = {}
        if data:
            for link in db.scalars(
                select(StoreFacility)
                .where(
                    StoreFacility.tenant_id == tenant_id,
                    StoreFacility.store_id.in_([row["id"] for row in data]),
                    StoreFacility.status == "active",
                )
                .order_by(StoreFacility.priority.asc().nulls_last(), StoreFacility.created_at.asc())
            ):
                by_store.setdefault(link.store_id, []).append(
                    StoreFacilityRead.model_validate(link).model_dump(by_alias=True)
                )
        for row in data:
            row["fulfilment_facilities"] = by_store.get(row["id"], [])
        return data

    return list_rows(
        db, stmt,
        filters={Store.channel: channel, Store.status: status_scope(status_filter)},
        keyword=keyword,
        keyword_columns=(Store.name, Store.store_code, Store.address),
        order_by=(Store.name.asc(), Store.id.asc()),
        pagination=page_only_pagination(page, size, default=100),
        sort=order_by,
        render=with_fulfilment,
        extra=extra,
    )


@router.post("/stores", response_model=StoreEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_store(
    payload: CreateStoreRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    ensure_code_available(db, Store, tenant_id, "store_code", payload.store_code)
    channel_fields = {"sales_channel_id": payload.sales_channel_id, "source": payload.source}
    _resolve_store_channel(db, tenant_id, channel_fields)
    store = Store(
        tenant_id=tenant_id,
        store_code=payload.store_code,
        name=payload.name,
        channel=payload.channel,
        sales_channel_id=channel_fields["sales_channel_id"],
        address=payload.address,
        remarks=payload.remarks,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(store)
    commit_or_conflict(db, f"an active store named {payload.name!r} already exists")
    db.refresh(store)
    return envelope(StoreRead.model_validate(store).model_dump(by_alias=True))


@router.patch("/stores/{store_id}", response_model=StoreEnvelope, response_model_exclude_unset=True)
def update_store(
    store_id: str,
    payload: UpdateStoreRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    store = get_scoped_or_404(db, Store, actor.tenant_id, store_id)
    updates = payload.model_dump(exclude_unset=True)
    _resolve_store_channel(db, actor.tenant_id, updates)
    if "store_code" in updates:
        ensure_code_available(
            db, Store, actor.tenant_id, "store_code", updates["store_code"],
            exclude_id=store.id,
        )
    if "metadata" in updates:
        store.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(store, field, value)
    commit_or_conflict(db, "an active store with this name already exists")
    db.refresh(store)
    return envelope(StoreRead.model_validate(store).model_dump(by_alias=True))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(
    store_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Store, store_id)


@router.post("/store-facilities", response_model=StoreFacilityEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_store_facility(
    payload: CreateStoreFacilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    require_active_row(db, Store, tenant_id, payload.store_id, "store")
    require_active_row(db, Facility, tenant_id, payload.facility_id, "facility")
    _require_pair_free(db, StoreFacility, tenant_id,
                       {"store_id": payload.store_id, "facility_id": payload.facility_id}, "link")
    link = StoreFacility(
        tenant_id=tenant_id,
        store_id=payload.store_id,
        facility_id=payload.facility_id,
        priority=payload.priority,
        remarks=payload.remarks,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    commit_or_conflict(db, "a link for this (store, facility) already exists")
    db.refresh(link)
    return envelope(StoreFacilityRead.model_validate(link).model_dump(by_alias=True))


@router.patch("/store-facilities/{link_id}", response_model=StoreFacilityEnvelope,
              response_model_exclude_unset=True)
def update_store_facility(
    link_id: str,
    payload: UpdateStoreFacilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    link = get_scoped_or_404(db, StoreFacility, actor.tenant_id, link_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        link.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(link, field, value)
    db.commit()
    db.refresh(link)
    return envelope(StoreFacilityRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/store-facilities/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store_facility(
    link_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, StoreFacility, link_id)


# --- product images: the catalog's pictures, bytes in the attachment store --


@router.post("/product-images", response_model=ProductImageEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_product_image(
    payload: CreateProductImageRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    require_type_option(db, tenant_id, "product_image_type", payload.image_type)
    attachment = get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    # pictures are image/*; a design draft is often a PDF and belongs in the
    # gallery too. Source files (DWG/AI/PSD) are document management, not a
    # product's pictures, and stay refused
    content_type = attachment.content_type.lower()
    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"attachment {payload.attachment_id} is {attachment.content_type} — a "
                "product picture is image/* (or a PDF design draft); a spreadsheet or a "
                "CAD source belongs in a document, not the gallery"
            ),
        )
    if payload.is_primary:
        _demote_others(db, ProductImage, tenant_id, {"product_id": payload.product_id},
                      (ProductImage.is_primary, True, False))
    image = ProductImage(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        attachment_id=payload.attachment_id,
        is_primary=payload.is_primary,
        image_type=payload.image_type,
        sort_order=payload.sort_order,
        caption=payload.caption,
        metadata_jsonb=payload.metadata,
    )
    db.add(image)
    commit_or_conflict(db, "this picture is already on this product — PATCH that row")
    db.refresh(image)
    return envelope(ProductImageRead.model_validate(image).model_dump(by_alias=True))


@router.patch("/product-images/{image_id}", response_model=ProductImageEnvelope,
              response_model_exclude_unset=True)
def update_product_image(
    image_id: str,
    payload: UpdateProductImageRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    image = get_scoped_or_404(db, ProductImage, tenant_id, image_id)
    updates = payload.model_dump(exclude_unset=True)
    if "image_type" in updates:
        require_type_option(db, tenant_id, "product_image_type", updates["image_type"])
    if updates.get("is_primary") and not image.is_primary:
        _demote_others(db, ProductImage, tenant_id, {"product_id": image.product_id},
                      (ProductImage.is_primary, True, False), keep_id=image.id)
    if "metadata" in updates:
        image.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(image, field, value)
    db.commit()
    db.refresh(image)
    return envelope(ProductImageRead.model_validate(image).model_dump(by_alias=True))


@router.delete("/product-images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_image(
    image_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Removes the LINK. The bytes stay in the attachment store — a blob two
    products share is one blob, and the store deduplicates by sha256."""
    require_master_data_manage(actor)
    image = get_scoped_or_404(db, ProductImage, actor.tenant_id, image_id)
    db.delete(image)
    db.commit()
    return None


# the catalog is one more attachment source: a product's pictures are the
# attachments its product_images rows point at, served through the product
register_attachment_source(Product, ProductImage, "product_id")


@router.get("/products/{product_id}/attachments/{attachment_id}/content")
def get_product_attachment(
    product_id: str,
    attachment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """A picture's bytes, reached through the product that carries it —
    everyone in the workspace reads the catalog, so everyone reads its
    pictures. An attachment that is real but not this product's reads as
    404, the same as one that is not real (the shared rule)."""
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return serve_document_attachment(db, tenant_id, product, attachment_id)


# --- bills of materials: what a good is made of ------------------------------


MAKEABLE_TYPES = ("finished_good", "semi_finished")


def _require_makeable_parent(db: Session, tenant_id: str, product_id: str) -> Product:
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    if product.product_type not in MAKEABLE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"product {product_id} is a {product.product_type} — a bill of "
                "materials is built for a finished or semi-finished good; set "
                "product_type first if this thing is in fact made"
            ),
        )
    return product


def _active_bom_for(db: Session, tenant_id: str, product_id: str) -> BillOfMaterials | None:
    return db.scalar(
        select(BillOfMaterials).where(
            BillOfMaterials.tenant_id == tenant_id,
            BillOfMaterials.product_id == product_id,
            BillOfMaterials.status == "active",
        )
    )


def _bom_lines(db: Session, tenant_id: str, bom_id: str) -> list[BomItem]:
    return list(db.scalars(
        select(BomItem)
        .options(selectinload(BomItem.component))
        .where(BomItem.tenant_id == tenant_id, BomItem.bom_id == bom_id)
        .order_by(BomItem.line_no.asc(), BomItem.created_at.asc())
    ))


def _require_component(
    db: Session, tenant_id: str, parent_product_id: str, component_product_id: str,
    *, recipes: dict[str, list[BomItem]] | None = None,
) -> Product:
    """A component may be anything but a service, the parent itself, or a
    product whose own active recipe (at any depth) contains the parent —
    one walk down the derived tree refuses the loop with its path. A
    caller checking many lines shares `recipes`, so a sub-tree ten lines
    reach is read once, not ten times."""
    if recipes is None:
        recipes = {}
    if component_product_id == parent_product_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a product cannot be a component of itself",
        )
    component = get_scoped_or_404(db, Product, tenant_id, component_product_id)
    if component.product_type == "service":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"product {component_product_id} is a service — a recipe is made of goods",
        )
    seen: set[str] = set()
    stack = [component_product_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if current not in recipes:
            recipe = _active_bom_for(db, tenant_id, current)
            recipes[current] = [] if recipe is None else _bom_lines(db, tenant_id, recipe.id)
        for line in recipes[current]:
            if line.component_product_id == parent_product_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"component {component_product_id} is made (through "
                        f"{current}) from {parent_product_id} itself — a recipe "
                        "cannot contain its own ancestor"
                    ),
                )
            stack.append(line.component_product_id)
    return component


BOM_ROWS = (BomItem, "bom_id", BomItemRead)


def _require_bom_editable(bom: BillOfMaterials) -> None:
    if bom.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"this recipe is {bom.status} — lines change only while draft; "
                "an active recipe is what the floor builds to, so a change is a "
                "NEW version (POST another bill of materials, then activate it)"
            ),
        )


def _bom_read(db: Session, tenant_id: str, bom: BillOfMaterials, *, with_items: bool) -> dict:
    data = BillOfMaterialsRead.model_validate(bom).model_dump(by_alias=True)
    if with_items:
        data["items"] = [
            BomItemRead.model_validate(line).model_dump(by_alias=True)
            for line in _bom_lines(db, tenant_id, bom.id)
        ]
        data["revision"] = rows_revision(db, bom, BillOfMaterialsRead, {"items": BOM_ROWS})
    return data


def build_bom_line(db: Session, tenant_id: str, bom: BillOfMaterials, line, *, index: int | None = None, recipes: dict | None = None, checked: bool = False) -> BomItem:
    """One validated recipe line, inline with the recipe's create or
    standalone — one constructor (gap 4). `checked` = the create already
    judged the component before the recipe row existed (see there)."""
    if not checked:
        _require_component(db, tenant_id, bom.product_id, line.component_product_id, recipes=recipes)
    item = BomItem(
        tenant_id=tenant_id,
        bom_id=bom.id,
        line_no=line.line_no if line.line_no is not None else index,
        component_product_id=line.component_product_id,
        quantity=line.quantity,
        unit=line.unit,
        scrap_rate=line.scrap_rate,
        description=line.description,
    )
    db.add(item)
    return item


@router.post("/bills-of-materials", response_model=BillOfMaterialsEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_bill_of_materials(
    payload: CreateBillOfMaterialsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    validate_only: bool = False,
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    _require_makeable_parent(db, tenant_id, payload.product_id)
    ensure_code_available(db, BillOfMaterials, tenant_id, "bom_code", payload.bom_code)
    recipes: dict[str, list[BomItem]] = {}
    # the lines are judged BEFORE the recipe row is flushed: an active recipe
    # per product is a unique index, so a second active recipe with a bad
    # component must answer 422 for the component, not 409 for the index
    for line in payload.items:
        _require_component(db, tenant_id, payload.product_id, line.component_product_id, recipes=recipes)
    bom = BillOfMaterials(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        bom_code=payload.bom_code,
        version=payload.version,
        output_quantity=payload.output_quantity,
        status=payload.status,
        remarks=payload.remarks,
        metadata_jsonb=payload.metadata,
    )
    db.add(bom)
    try:
        db.flush()
        if payload.status == "active":
            _demote_others(db, BillOfMaterials, tenant_id, {"product_id": payload.product_id},
                          (BillOfMaterials.status, "active", "archived"), keep_id=bom.id)
        items = [
            build_bom_line(db, tenant_id, bom, line, index=index, recipes=recipes, checked=True)
            for index, line in enumerate(payload.items, start=1)
        ]
        if validate_only:
            db.flush()
            data = _bom_read(db, tenant_id, bom, with_items=True)
            db.rollback()
            return {"data": data, "meta": {"validate_only": True, "written": False}}
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this product already has an active recipe, or the bom_code is taken",
        )
    db.refresh(bom)
    return envelope(_bom_read(db, tenant_id, bom, with_items=True))


@router.patch("/bills-of-materials/{bom_id}", response_model=BillOfMaterialsEnvelope,
              response_model_exclude_unset=True)
def update_bill_of_materials(
    bom_id: str,
    payload: UpdateBillOfMaterialsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    bom = get_scoped_or_404(db, BillOfMaterials, tenant_id, bom_id)
    updates = payload.model_dump(exclude_unset=True)
    if "bom_code" in updates:
        ensure_code_available(
            db, BillOfMaterials, tenant_id, "bom_code", updates["bom_code"], exclude_id=bom.id
        )
    if "output_quantity" in updates and updates["output_quantity"] != float(bom.output_quantity):
        _require_bom_editable(bom)
    if updates.get("status") == "active" and bom.status != "active":
        _demote_others(db, BillOfMaterials, tenant_id, {"product_id": bom.product_id},
                      (BillOfMaterials.status, "active", "archived"), keep_id=bom.id)
    if "metadata" in updates:
        bom.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(bom, field, value)
    commit_or_conflict(db, "this product already has an active recipe, or the bom_code is taken")
    db.refresh(bom)
    return envelope(_bom_read(db, tenant_id, bom, with_items=False))


@router.delete("/bills-of-materials/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill_of_materials(
    bom_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, BillOfMaterials, bom_id)


def _atp_by_product(
    db: Session, tenant_id: str, product_ids: set[str], facility_id: str | None = None
) -> dict[str, float]:
    if not product_ids:
        return {}
    stmt = (
        select(InventoryItem.product_id, func.sum(InventoryItem.available_to_promise))
        .where(
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.product_id.in_(product_ids),
            InventoryItem.status == "active",
        )
    )
    if facility_id is not None:
        # "what is at THAT place" — a contract manufacturer's floor, one of
        # several warehouses — rather than the workspace-wide sum
        stmt = stmt.where(InventoryItem.facility_id == facility_id)
    rows = db.execute(stmt.group_by(InventoryItem.product_id)).all()
    return {product_id: float(total or 0) for product_id, total in rows}


@router.get("/bills-of-materials/{bom_id}/explode", response_model=BomExplodeEnvelope,
            response_model_exclude_unset=True)
def explode_bill_of_materials(
    bom_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    quantity: Annotated[float, Query(gt=0, le=99_999_999)] = 1,
    with_stock: bool = False,
    # restrict the stock view to one registered facility (the factory's,
    # a specific warehouse); omitted = every active position
    facility_id: str | None = None,
):
    """The MRP-lite read: walk the recipe (and every sub-assembly's active
    recipe under it), scale each line to the requested quantity of the root
    through its recipe's output quantity, fold in scrap, and sum the leaves
    — what must be bought or already stocked. Derived on every call, stored
    nowhere; comparing it to stock and deciding what to buy is the agent's
    judgment, which is why `with_stock` hands over ATP and a shortage
    instead of a purchase request."""
    root = get_scoped_or_404(db, BillOfMaterials, tenant_id, bom_id)
    lines: list[dict] = []
    leaves: dict[str, dict] = {}

    def walk(bom: BillOfMaterials, needed_of_parent: float, level: int, path: tuple[str, ...]) -> None:
        ratio = needed_of_parent / float(bom.output_quantity)
        for line in _bom_lines(db, tenant_id, bom.id):
            scrap = float(line.scrap_rate) if line.scrap_rate is not None else 0.0
            required = float(line.quantity) * ratio * (1 + scrap / 100)
            component = line.component
            sub = (
                None if line.component_product_id in path
                else _active_bom_for(db, tenant_id, line.component_product_id)
            )
            lines.append({
                "level": level,
                "parent_product_id": bom.product_id,
                "component_product_id": line.component_product_id,
                "component_name": component.name if component else None,
                "component_type": component.product_type if component else "finished_good",
                "unit": line.unit,
                "required_quantity": round(required, 4),
                "scrap_rate": line.scrap_rate,
                "has_bom": sub is not None,
            })
            if sub is not None:
                walk(sub, required, level + 1, path + (line.component_product_id,))
            else:
                leaf = leaves.setdefault(line.component_product_id, {
                    "product_id": line.component_product_id,
                    "product_name": component.name if component else None,
                    "product_type": component.product_type if component else "finished_good",
                    "unit": line.unit,
                    "required_quantity": 0.0,
                })
                leaf["required_quantity"] = round(leaf["required_quantity"] + required, 4)

    walk(root, quantity, 1, (root.product_id,))
    if with_stock:
        if facility_id is not None:
            get_scoped_or_404(db, Facility, tenant_id, facility_id)
        atp = _atp_by_product(
            db, tenant_id,
            {row["component_product_id"] for row in lines} | set(leaves),
            facility_id,
        )
        for row in lines:
            row["available_to_promise"] = atp.get(row["component_product_id"], 0.0)
        for leaf in leaves.values():
            leaf["available_to_promise"] = atp.get(leaf["product_id"], 0.0)
            leaf["shortage"] = round(
                max(0.0, leaf["required_quantity"] - leaf["available_to_promise"]), 4
            )
    return envelope(BomExplodeRead(
        bom_id=root.id, product_id=root.product_id, quantity=quantity,
        lines=[BomExplodedLineRead(**row) for row in lines],
        leaf_requirements=[BomLeafRequirementRead(**leaf) for leaf in leaves.values()],
    ).model_dump(by_alias=True))


@router.post("/bom-items", response_model=BomItemEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_bom_item(
    payload: CreateBomItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    bom = get_scoped_or_404(db, BillOfMaterials, tenant_id, payload.bom_id)
    _require_bom_editable(bom)
    item = build_bom_line(db, tenant_id, bom, payload)
    db.commit()
    db.refresh(item)
    return envelope(BomItemRead.model_validate(item).model_dump(by_alias=True))


@router.post("/bills-of-materials/{bom_id}/save", response_model=SavedLinesEnvelope, response_model_exclude_unset=True)
def save_bom_lines(
    bom_id: str,
    payload: SaveBomLinesRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    validate_only: bool = False,
):
    """A draft recipe's components restated in one act, as a diff under the
    recipe's `revision` — the contract of every `/save`."""
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    bom = get_scoped_or_404(db, BillOfMaterials, tenant_id, bom_id)
    _require_bom_editable(bom)

    def update(item: BomItem, changed: dict) -> None:
        if changed.get("component_product_id"):
            _require_component(db, tenant_id, bom.product_id, changed["component_product_id"])
        for field_name, value in changed.items():
            setattr(item, field_name, value)

    return save_rows(
        db, actor, document=bom, parent_model=BillOfMaterials, header_read=BillOfMaterialsRead, spec=BOM_ROWS,
        payload=payload, build=lambda row: build_bom_line(db, tenant_id, bom, row),
        update=update, remove=db.delete, new_model=BomItemBase, update_model=UpdateBomItemRequest, validate_only=validate_only,
    )


@router.patch("/bom-items/{item_id}", response_model=BomItemEnvelope,
              response_model_exclude_unset=True)
def update_bom_item(
    item_id: str,
    payload: UpdateBomItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    item = get_scoped_or_404(db, BomItem, tenant_id, item_id)
    bom = get_scoped_or_404(db, BillOfMaterials, tenant_id, item.bom_id)
    _require_bom_editable(bom)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("component_product_id"):
        _require_component(db, tenant_id, bom.product_id, updates["component_product_id"])
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(BomItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/bom-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bom_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    item = get_scoped_or_404(db, BomItem, tenant_id, item_id)
    bom = get_scoped_or_404(db, BillOfMaterials, tenant_id, item.bom_id)
    _require_bom_editable(bom)
    db.delete(item)
    db.commit()
    return None


# --- product categories: the catalog's shelving -----------------------------


def _require_usable_parent(
    db: Session, tenant_id: str, parent_id: str | None, *, moving: ProductCategory | None = None
) -> None:
    """A parent must exist, be active, and not sit below the category being
    moved — one walk up the ancestor chain refuses self, cycle and archived
    shelf alike, with the fix in the message."""
    if parent_id is None:
        return
    if moving is not None and parent_id == moving.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a category cannot be its own parent",
        )
    node = get_scoped_or_404(db, ProductCategory, tenant_id, parent_id)
    if node.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"category {node.id} is archived — revive it (PATCH status "
                "active) before shelving anything under it"
            ),
        )
    seen: set[str] = set()
    while node is not None:
        if node.id in seen:
            # a pre-existing loop in the data; refuse to extend it
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="the category tree already contains a cycle at this branch",
            )
        seen.add(node.id)
        if moving is not None and node.parent_id == moving.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"category {parent_id} sits below {moving.id} — moving a "
                    "category under its own descendant would close a loop"
                ),
            )
        node = (
            get_scoped_or_404(db, ProductCategory, tenant_id, node.parent_id)
            if node.parent_id else None
        )


@router.post(
    "/product-categories",
    response_model=ProductCategoryEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product_category(
    payload: CreateProductCategoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    ensure_code_available(
        db, ProductCategory, tenant_id, "category_code", payload.category_code
    )
    _require_usable_parent(db, tenant_id, payload.parent_id)
    category = ProductCategory(
        tenant_id=tenant_id,
        category_code=payload.category_code,
        name=payload.name,
        parent_id=payload.parent_id,
        description=payload.description,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(category)
    commit_or_conflict(db, (
                        f"an active category named {payload.name!r} already exists at "
                        "this level — two live folders with one name is a filing "
                        "error, not a second shelf"
                    ))
    db.refresh(category)
    return envelope(ProductCategoryRead.model_validate(category).model_dump(by_alias=True))


@router.patch("/product-categories/{category_id}", response_model=ProductCategoryEnvelope,
              response_model_exclude_unset=True)
def update_product_category(
    category_id: str,
    payload: UpdateProductCategoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    category = get_scoped_or_404(db, ProductCategory, tenant_id, category_id)
    updates = payload.model_dump(exclude_unset=True)
    if "category_code" in updates:
        ensure_code_available(
            db, ProductCategory, tenant_id, "category_code", updates["category_code"],
            exclude_id=category.id,
        )
    if "parent_id" in updates:
        _require_usable_parent(db, tenant_id, updates["parent_id"], moving=category)
    if "metadata" in updates:
        category.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(category, field, value)
    commit_or_conflict(db, "an active category with this name already exists at the target level")
    db.refresh(category)
    return envelope(ProductCategoryRead.model_validate(category).model_dump(by_alias=True))


@router.delete("/product-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_category(
    category_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ProductCategory, category_id)


# --- products, their SKUs, and the bulk upserts beside them ----------------


def _demote_others(db: Session, model, tenant_id: str, scope: dict, flag, *, keep_id: str | None = None) -> None:
    """One winner per scope: setting the new primary contact, primary
    picture or active recipe DEMOTES the previous one in the same write —
    "which one" is one question with one answer, and a two-step dance
    stops after step one half the time. `flag` is (column, on, off); the
    partial unique index backstops the race this cannot see."""
    column, on_value, off_value = flag
    stmt = (
        update(model)
        .where(model.tenant_id == tenant_id, column == on_value,
               *[getattr(model, key) == value for key, value in scope.items()])
        .values({column.key: off_value})
        .execution_options(synchronize_session=False)
    )
    if keep_id is not None:
        stmt = stmt.where(model.id != keep_id)
    db.execute(stmt)


def _require_pair_free(db: Session, model, tenant_id: str, scope: dict, noun: str, *, revives: str = "link") -> None:
    """A (a, b) pair is one row whose lapse is status: the refusal hands over
    the existing row — PATCH it, revive it, never fork it."""
    existing = db.scalar(select(model).where(
        model.tenant_id == tenant_id,
        *[getattr(model, key) == value for key, value in scope.items()],
    ))
    if existing is not None:
        pair = ", ".join(key.removesuffix("_id") for key in scope)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{noun} {existing.id} already exists for this ({pair}) — "
                f"PATCH it; an archived {revives} revives by setting status active"
            ),
        )


def _match_text(text_value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text_value).casefold().split())


def _match_phrases(title: str, field_text: str) -> set[str]:
    """What a catalog field and a platform title share, as PHRASES: every
    ASCII word/number both contain, and every maximal run of CJK (two or
    more characters) that appears verbatim in both. Bigram counting (the
    first cut) let a long compound shared by half the catalog — 医用胶片打印机 —
    outscore the one word that names the goods (色带), because the compound
    is six bigrams and the word is one. A shared run is one phrase however
    long it is; how much it says is its rarity, weighed by the caller."""
    if not field_text:
        return set()
    phrases: set[str] = set()
    title_words = set(re.findall(r"[a-z0-9][a-z0-9.\-]*", title))
    phrases.update(word for word in re.findall(r"[a-z0-9][a-z0-9.\-]*", field_text) if word in title_words)
    title_runs = re.findall(r"[\u4e00-\u9fff]+", title)
    for run in re.findall(r"[\u4e00-\u9fff]+", field_text):
        for t_run in title_runs:
            # maximal common substrings of length >= 2 (single characters
            # say nothing: 机 is in every machine), longest first so a
            # shorter piece of an already-taken run does not count twice
            found: list[str] = []
            n, m = len(run), len(t_run)
            table = [[0] * (m + 1) for _ in range(n + 1)]
            for i in range(n):
                for j in range(m):
                    if run[i] == t_run[j]:
                        table[i + 1][j + 1] = table[i][j] + 1
            ends = sorted(
                ((table[i][j], i) for i in range(1, n + 1) for j in range(1, m + 1) if table[i][j] >= 2),
                reverse=True,
            )
            taken: list[tuple[int, int]] = []
            for length, i in ends:
                lo, hi = i - length, i
                if any(lo < t_hi and hi > t_lo for t_lo, t_hi in taken):
                    continue
                taken.append((lo, hi))
                found.append(run[lo:hi])
            phrases.update(found)
    return phrases


_MATCH_WORD = re.compile(r"[a-z0-9][a-z0-9.\-]*")
_MATCH_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def _match_keys(text_value: str) -> set[str]:
    """What two texts must have in common to share any phrase at all: an
    ASCII word, or a CJK bigram (a shared run of two or more characters
    contains one). The catalog is indexed by these so a title is compared
    only with the products it could possibly match — the phrase comparison
    itself is a quadratic table per pair of runs, and running it against
    every product for every title was the cost of a long import."""
    keys = set(_MATCH_WORD.findall(text_value))
    for run in _MATCH_CJK_RUN.findall(text_value):
        keys.update(run[i:i + 2] for i in range(len(run) - 1))
    return keys


class _CatalogMatcher:
    """The tenant's active catalog, loaded and indexed ONCE, then asked about
    any number of titles. `GET /product-matches` builds one for its single
    title; the batch resolve builds one for the whole import. Scores are
    exactly what the per-title scan produced — the index only skips products
    that share nothing with the title, and phrase rarity is remembered
    between titles instead of recounted."""

    def __init__(self, db: Session, tenant_id: str) -> None:
        products = db.execute(
            select(Product.id, Product.name, Product.product_code, Product.spec)
            .where(Product.tenant_id == tenant_id, Product.status == "active")
        ).all()
        self.skus_by_product: dict[str, list[tuple[str, str]]] = {}
        for sku_id, product_id, sku_code, variant_attrs in db.execute(
            select(ProductSku.id, ProductSku.product_id, ProductSku.sku_code, ProductSku.variant_attrs)
            .where(ProductSku.tenant_id == tenant_id, ProductSku.status == "active")
        ):
            values = [str(v) for v in (variant_attrs or {}).values() if v not in (None, "")]
            self.skus_by_product.setdefault(product_id, []).append(
                (sku_id, _match_text(" ".join(part for part in [sku_code or "", *values] if part)))
            )
        self.texts = {
            product_id: _match_text(" ".join(part for part in (name, code, spec) if part))
            for product_id, name, code, spec in products
        }
        self.every_text = {
            product_id: text + " " + " ".join(sku_text for _sid, sku_text in self.skus_by_product.get(product_id, ()))
            for product_id, text in self.texts.items()
        }
        self.index: dict[str, set[str]] = {}
        for product_id, text in self.every_text.items():
            for key in _match_keys(text):
                self.index.setdefault(key, set()).add(product_id)
        self._weight: dict[str, float] = {}

    def weight(self, phrase: str) -> float:
        """Rarity across the catalog: a phrase carried by n of N products."""
        known = self._weight.get(phrase)
        if known is None:
            carriers = sum(1 for text in self.every_text.values() if phrase in text)
            known = self._weight[phrase] = math.log(1 + len(self.every_text) / max(carriers, 1))
        return known

    def shortlist(self, title: str, limit: int) -> list[dict]:
        folded = _match_text(title)
        if not folded:
            return []
        possible: set[str] = set()
        for key in _match_keys(folded):
            possible |= self.index.get(key, set())
        shared: dict[str, set[str]] = {}
        sku_hits: dict[str, list[tuple[str, set[str]]]] = {}
        for product_id in possible:
            phrases = _match_phrases(folded, self.texts[product_id])
            for sku_id, sku_text in self.skus_by_product.get(product_id, ()):
                sku_phrases = _match_phrases(folded, sku_text)
                if sku_phrases:
                    sku_hits.setdefault(product_id, []).append((sku_id, sku_phrases))
                    phrases |= sku_phrases
            if phrases:
                shared[product_id] = phrases
        if not shared:
            return []
        title_mass = sum(self.weight(phrase) for phrase in set().union(*shared.values()))
        scored = []
        for product_id, phrases in shared.items():
            mass = sum(self.weight(p) for p in phrases)
            scored.append((mass / title_mass if title_mass else 0.0, mass, product_id))
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        return [
            {
                "product_id": product_id,
                "match_score": round(score, 3),
                "matched_terms": sorted(shared[product_id], key=lambda p: -self.weight(p)),
                "sku_hits": [
                    (sku_id, sorted(phrases, key=lambda p: -self.weight(p)))
                    for sku_id, phrases in sorted(
                        sku_hits.get(product_id, ()), key=lambda hit: -sum(self.weight(p) for p in hit[1])
                    )
                ],
            }
            for score, _mass, product_id in scored[:limit]
        ]


def _hydrate_candidates(db: Session, tenant_id: str, shortlists: list[list[dict]]) -> list[list[dict]]:
    """Product reads and SKU rows for every shortlist in one pass."""
    product_ids = list(dict.fromkeys(hit["product_id"] for hits in shortlists for hit in hits))
    if not product_ids:
        return [[] for _ in shortlists]
    rows = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    reads = {
        read["id"]: read
        for read in product_reads_with_sku_stats(db, tenant_id, [rows[pid] for pid in product_ids if pid in rows])
    }
    sku_ids = list(dict.fromkeys(sku_id for hits in shortlists for hit in hits for sku_id, _p in hit["sku_hits"]))
    sku_rows = {
        sku.id: sku for sku in db.scalars(select(ProductSku).where(ProductSku.id.in_(sku_ids)))
    } if sku_ids else {}
    return [
        [
            {
                **reads[hit["product_id"]],
                "match_score": hit["match_score"],
                "matched_terms": hit["matched_terms"],
                "sku_candidates": [
                    {
                        "id": sku_id,
                        "sku_code": sku_rows[sku_id].sku_code,
                        "variant_attrs": sku_rows[sku_id].variant_attrs or {},
                        "matched_terms": phrases,
                    }
                    for sku_id, phrases in hit["sku_hits"] if sku_id in sku_rows
                ],
            }
            for hit in hits if hit["product_id"] in reads
        ]
        for hits in shortlists
    ]


@router.get("/product-matches", response_model_exclude_unset=True)
def match_products_by_title(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    title: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    """Candidates for a platform title. A READ that hands the agent a
    shortlist with scores; which one (if any) the title means is the
    person's confirmation, and the map row that records it is what makes
    the next import skip this call.

    Scoring: the phrases a product (its name, code, spec — and its SKUs'
    codes and variant values) shares with the title, each weighed by how
    RARE it is in this catalog: a phrase every printer carries says little,
    the one phrase only the ribbon carries says almost everything, and a
    spec token that names one SKU (14x17) is as telling as the product's
    own name. `match_score` is the share of the title's catalog-known mass
    the candidate covers, in [0, 1]; `matched_terms` lists the phrases;
    `sku_candidates` names the variants whose own text the title also
    matches, so a spec in the title resolves to a SKU, not just a product."""
    matcher = _CatalogMatcher(db, tenant_id)
    return envelope(_hydrate_candidates(db, tenant_id, [matcher.shortlist(title, limit)])[0])


@router.post(
    "/products",
    response_model=ProductEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: CreateProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Product, actor.tenant_id, "product_code", payload.product_code)
    require_active_row(db, ProductCategory, actor.tenant_id, payload.category_id, "category")
    product = Product(
        tenant_id=actor.tenant_id,
        product_code=payload.product_code,
        name=payload.name,
        product_type=payload.product_type,
        category_id=payload.category_id,
        spec=payload.spec,
        unit=payload.unit,
        list_price=payload.list_price,
        currency=payload.currency,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(product)
    commit_or_code_conflict(db, product)
    db.refresh(product)
    return envelope(ProductRead.model_validate(product).model_dump(by_alias=True))


@router.post(
    "/products/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_products(
    payload: BulkProductUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert products keyed on `product_code` — the spreadsheet-import path."""
    return _run_bulk_upsert(db=db, actor=actor, family="product", payload=payload)


@router.post(
    "/vendors/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_vendors(
    payload: BulkVendorUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert vendors keyed on `vendor_code`."""
    return _run_bulk_upsert(db=db, actor=actor, family="vendor", payload=payload)


@router.post(
    "/customers/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_customers(
    payload: BulkCustomerUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert customers keyed on `customer_code`."""
    return _run_bulk_upsert(db=db, actor=actor, family="customer", payload=payload)


@router.post(
    "/products/{product_id}/skus/batch",
    response_model=BatchCreateProductSkusEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def batch_create_product_skus(
    product_id: str,
    payload: BatchCreateProductSkusRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a stable, de-duplicated run of one-dimensional SKUs.

    Existing rows in any lifecycle state reserve their complete, non-empty
    variant-attribute combination, so retrying a batch is idempotent without
    conflating a one-dimensional SKU with a richer multi-dimensional variant.
    """
    require_master_data_manage(actor)
    product = get_locked_product_or_404(db, actor.tenant_id, product_id)
    if product.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot create SKU for an archived product",
        )

    existing_identities = {
        json_value_identity(attrs)
        for attrs in existing_product_sku_variant_attrs(db, actor.tenant_id, product_id)
    }

    created: list[ProductSku] = []
    skipped: list[str] = []
    for value in payload.values:
        variant_attrs = {payload.dimension: value}
        variant_identity = json_value_identity(variant_attrs)
        if variant_identity in existing_identities:
            skipped.append(value)
            continue

        generated_code = f"{product.product_code}-{value}" if product.product_code else None
        # sku_code is optional. For unusually long source values, retaining the
        # complete variant attribute is preferable to truncating into a code
        # that could collide with another generated SKU.
        if generated_code is not None and len(generated_code) > 64:
            generated_code = None
        sku = ProductSku(
            tenant_id=actor.tenant_id,
            product_id=product_id,
            sku_code=generated_code,
            variant_attrs=variant_attrs,
            list_price=payload.list_price,
            status="active",
            metadata_jsonb={},
        )
        db.add(sku)
        created.append(sku)
        existing_identities.add(variant_identity)

    created_data: list[dict] = []
    if created:
        # One flush populates generated ids/timestamps for the response; avoid
        # issuing a refresh query per SKU after the batch commit.
        db.flush()
        created_data = [
            ProductSkuRead.model_validate(sku).model_dump(by_alias=True)
            for sku in created
        ]
        db.commit()

    return envelope(
        {
            "created": created_data,
            "skipped": skipped,
        }
    )


@router.patch("/products/{product_id}", response_model=ProductEnvelope, response_model_exclude_unset=True)
def update_product(
    product_id: str,
    payload: UpdateProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    product = get_scoped_or_404(db, Product, actor.tenant_id, product_id)
    updates = payload.model_dump(exclude_unset=True)
    if "category_id" in updates:
        require_active_row(db, ProductCategory, actor.tenant_id, updates["category_id"], "category")
    if "product_code" in updates:
        ensure_code_available(
            db, Product, actor.tenant_id, "product_code", updates["product_code"],
            exclude_id=product.id,
        )
    if "metadata" in updates:
        product.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(product, field, value)
    commit_or_code_conflict(db, product)
    db.refresh(product)
    return envelope(product_read_with_skus_flag(db, product))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Product, product_id)


@router.post(
    "/product-skus",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product_sku(
    payload: CreateProductSkuRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    product = get_locked_product_or_404(db, actor.tenant_id, payload.product_id)
    if product.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot create SKU for an archived product",
        )
    ensure_product_sku_variant_attrs_available(
        db,
        actor.tenant_id,
        payload.product_id,
        payload.variant_attrs,
    )
    sku = ProductSku(
        tenant_id=actor.tenant_id,
        product_id=payload.product_id,
        sku_code=payload.sku_code,
        variant_attrs=payload.variant_attrs,
        list_price=payload.list_price,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(sku)
    db.commit()
    db.refresh(sku)
    return envelope(ProductSkuRead.model_validate(sku).model_dump(by_alias=True))


@router.patch(
    "/product-skus/{sku_id}",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
)
def update_product_sku(
    sku_id: str,
    payload: UpdateProductSkuRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    sku = get_scoped_or_404(db, ProductSku, actor.tenant_id, sku_id)
    updates = payload.model_dump(exclude_unset=True)
    if "variant_attrs" in updates:
        get_locked_product_or_404(db, actor.tenant_id, sku.product_id)
        candidate_attrs = updates["variant_attrs"] or {}
        ensure_product_sku_variant_attrs_available(
            db,
            actor.tenant_id,
            sku.product_id,
            candidate_attrs,
            exclude_sku_id=sku.id,
        )
        updates["variant_attrs"] = candidate_attrs
    if "metadata" in updates:
        sku.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(sku, field, value)
    db.commit()
    db.refresh(sku)
    return envelope(ProductSkuRead.model_validate(sku).model_dump(by_alias=True))


@router.delete("/product-skus/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_sku(
    sku_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ProductSku, sku_id)


# --- product prices: the price book beside the product's own list_price ----


def _find_active_price(
    db: Session, tenant_id: str, product_id: str, sku_id: str | None, price_type: str, currency: str
) -> ProductPrice | None:
    stmt = select(ProductPrice).where(
        ProductPrice.tenant_id == tenant_id,
        ProductPrice.product_id == product_id,
        ProductPrice.price_type == price_type,
        ProductPrice.currency == currency,
        ProductPrice.status == "active",
    )
    stmt = stmt.where(ProductPrice.sku_id == sku_id) if sku_id else stmt.where(ProductPrice.sku_id.is_(None))
    return db.scalar(stmt)


@router.post(
    "/product-prices",
    response_model=ProductPriceEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product_price(
    payload: CreateProductPriceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "product_price_type", payload.price_type)
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    if payload.sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, payload.sku_id)
        if sku.product_id != payload.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to product_id",
            )
    if payload.status == "active":
        existing = _find_active_price(
            db, tenant_id, payload.product_id, payload.sku_id, payload.price_type, payload.currency
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"active {payload.price_type} price {existing.id} already exists for this "
                    "(product, sku, currency) — archive it first, or PATCH it"
                ),
            )
    row = ProductPrice(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        price_type=payload.price_type,
        price=payload.price,
        currency=payload.currency,
        tax_in_price=payload.tax_in_price,
        tax_percentage=payload.tax_percentage,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(row)
    commit_or_conflict(db, "an active price for this (product, sku, type, currency) already exists")
    db.refresh(row)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/product-prices/{price_id}", response_model=ProductPriceEnvelope, response_model_exclude_unset=True)
def update_product_price(
    price_id: str,
    payload: UpdateProductPriceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, ProductPrice, actor.tenant_id, price_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == "active" and row.status != "active":
        clash = _find_active_price(
            db, actor.tenant_id, row.product_id, row.sku_id, row.price_type, row.currency
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"active price {clash.id} already holds this (product, sku, type, currency) slot",
            )
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    commit_or_conflict(db, "an active price for this (product, sku, type, currency) already exists")
    db.refresh(row)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/product-prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_price(
    price_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ProductPrice, price_id)


# --- supplier products: who supplies what, on which terms ------------------


@router.post(
    "/supplier-products",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_product(
    payload: CreateSupplierProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    get_scoped_or_404(db, Vendor, tenant_id, payload.vendor_id)
    _require_pair_free(db, SupplierProduct, tenant_id,
                       {"product_id": payload.product_id, "vendor_id": payload.vendor_id}, "supplier link")
    link = SupplierProduct(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        vendor_id=payload.vendor_id,
        supplier_product_code=payload.supplier_product_code,
        supplier_product_name=payload.supplier_product_name,
        last_price=payload.last_price,
        currency=payload.currency,
        lead_time_days=payload.lead_time_days,
        min_order_quantity=payload.min_order_quantity,
        order_increment=payload.order_increment,
        preference=payload.preference,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    commit_or_conflict(db, "a supplier link for this (product, vendor) already exists")
    db.refresh(link)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.patch(
    "/supplier-products/{supplier_product_id}",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
)
def update_supplier_product(
    supplier_product_id: str,
    payload: UpdateSupplierProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    link = get_scoped_or_404(db, SupplierProduct, actor.tenant_id, supplier_product_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        link.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(link, field, value)
    db.commit()
    db.refresh(link)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/supplier-products/{supplier_product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_product(
    supplier_product_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, SupplierProduct, supplier_product_id)


# --- customer price agreements: SupplierProduct's sell-side mirror ----------


@router.post(
    "/customer-products",
    response_model=CustomerProductEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_product(
    payload: CreateCustomerProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
    _require_pair_free(db, CustomerProduct, tenant_id,
                       {"product_id": payload.product_id, "customer_id": payload.customer_id},
                       "agreement", revives="agreement")
    agreement = CustomerProduct(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        customer_id=payload.customer_id,
        customer_product_code=payload.customer_product_code,
        customer_product_name=payload.customer_product_name,
        agreed_price=payload.agreed_price,
        currency=payload.currency,
        min_order_quantity=payload.min_order_quantity,
        order_increment=payload.order_increment,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(agreement)
    commit_or_conflict(db, "an agreement for this (product, customer) already exists")
    db.refresh(agreement)
    return envelope(CustomerProductRead.model_validate(agreement).model_dump(by_alias=True))


@router.patch(
    "/customer-products/{customer_product_id}",
    response_model=CustomerProductEnvelope,
    response_model_exclude_unset=True,
)
def update_customer_product(
    customer_product_id: str,
    payload: UpdateCustomerProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    agreement = get_scoped_or_404(db, CustomerProduct, actor.tenant_id, customer_product_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        agreement.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(agreement, field, value)
    db.commit()
    db.refresh(agreement)
    return envelope(CustomerProductRead.model_validate(agreement).model_dump(by_alias=True))


@router.delete("/customer-products/{customer_product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_product(
    customer_product_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, CustomerProduct, customer_product_id)


# --- customer contacts: the rolodex behind a B2B account --------------------


def _owns_customer(db: Session, actor: Actor, customer_id: str) -> bool:
    if actor.employee_id is None:
        return False
    customer = db.get(Customer, customer_id)
    return customer is not None and customer.tenant_id == actor.tenant_id and customer.owner_employee_id == actor.employee_id


@router.post("/customer-contacts", response_model=CustomerContactEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_customer_contact(
    payload: CreateCustomerContactRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    # F-09: the salesperson who owns the account adds its people (the deal's
    # cast, the demo's attendees); everyone else's rolodex is the catalog desk's
    if not (has_permission(actor, "crm.own") and _owns_customer(db, actor, payload.customer_id)):
        require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
    if payload.is_primary:
        _demote_others(db, CustomerContact, tenant_id, {"customer_id": payload.customer_id}, (CustomerContact.is_primary, True, False))
    contact = CustomerContact(
        tenant_id=tenant_id,
        customer_id=payload.customer_id,
        name=payload.name,
        title=payload.title,
        phone=payload.phone,
        wechat=payload.wechat,
        email=payload.email,
        is_primary=payload.is_primary,
        status=payload.status,
        remarks=payload.remarks,
        metadata_jsonb=payload.metadata,
    )
    db.add(contact)
    commit_or_conflict(db, (
                        "an active contact with this phone already exists at this "
                        "customer — the same number twice is a duplicate person; "
                        "PATCH that row, or archive it first"
                    ))
    db.refresh(contact)
    return envelope(CustomerContactRead.model_validate(contact).model_dump(by_alias=True))


@router.patch("/customer-contacts/{contact_id}", response_model=CustomerContactEnvelope,
              response_model_exclude_unset=True)
def update_customer_contact(
    contact_id: str,
    payload: UpdateCustomerContactRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    contact = get_scoped_or_404(db, CustomerContact, actor.tenant_id, contact_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_primary") and not contact.is_primary:
        _demote_others(db, CustomerContact, actor.tenant_id, {"customer_id": contact.customer_id},
                      (CustomerContact.is_primary, True, False))
    if "metadata" in updates:
        contact.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(contact, field, value)
    commit_or_conflict(db, "an active contact with this phone already exists at this customer")
    db.refresh(contact)
    return envelope(CustomerContactRead.model_validate(contact).model_dump(by_alias=True))


@router.delete("/customer-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_contact(
    contact_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, CustomerContact, contact_id)


# --- external product maps: what a platform's ids mean in our catalog ------
#
# The channel mirror of supplier-products: that table maps a vendor's code
# for what we buy, this one maps Tmall/JD/Amazon/anything's id for what we
# sell. Many-to-many by rows — a bundle listing is several rows with
# quantities, one product on five channels is five rows. The order-recording
# agent consults this to translate lines; the external ORDER number lands in
# external-document-links, a separate table because a link must be
# hard-unique per tuple while multiple map rows per external id are the point.


def require_map_curation(actor: Actor) -> None:
    """Map rows are written by the catalog desk — and by the desk that
    records channel orders. The person importing a Tmall export is the one
    who confirms "this title is our product"; sending them to the catalog
    desk for every new listing would make the import a two-desk job, and
    the row they write is exactly what a curator would write. Products
    themselves stay catalog work; deleting a map does too."""
    if has_permission(actor, "order.submit_own"):
        return
    require_master_data_manage(actor)


def _require_map_window_authority(actor: Actor, effective_from, effective_to) -> None:
    """A dated window is a swap statement — "this listing meant X until the
    9th" — and that is catalog work: the desk that confirms pairings may not
    date them (E-03)."""
    if (effective_from is not None or effective_to is not None) and not has_permission(actor, "master_data.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "effective_from / effective_to record a listing swap, which is the "
                "catalog desk's write (master_data.manage) — confirm the pairing without a window"
            ),
        )


def _require_map_row_authority(actor: Actor, row: ExternalProductMap) -> None:
    """The desk that may write an undated pairing may also correct or
    withdraw one (E-03: a wrong row it can create but not remove is a trap);
    a row with a window is a swap record and stays with the catalog desk."""
    if (row.effective_from is not None or row.effective_to is not None) and not has_permission(actor, "master_data.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"map {row.id} carries an effective window — a swap record the catalog "
                "desk (master_data.manage) curates"
            ),
        )


@router.get(
    "/external-product-maps",
    response_model=ExternalProductMapListEnvelope,
    response_model_exclude_unset=True,
)
def list_external_product_maps(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    source: str | None = None,
    external_product_id: str | None = None,
    # exact match on the listing title's matching form (NFKC, casefold,
    # whitespace collapsed) — the translation query when the platform
    # export names products by title, not id
    external_name: str | None = None,
    external_sku_id: str | None = None,
    product_id: str | None = None,
    keyword: str | None = None,
    at: Annotated[
        date | None,
        Query(description=(
            "Resolve the map AS OF this date — rows whose [effective_from, "
            "effective_to) window covers it, null bounds open. This is THE "
            "translation query: pass the ORDER's date, because a listing that "
            "swapped products means different things on different days. "
            "Without an explicit status filter, `at` returns live rows only — "
            "an archived (withdrawn) pairing never described the listing."
        )),
    ] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ExternalProductMap, ranges=('created_at', 'effective_from', 'effective_to'), equals=('sku_id',)))] = None,
):
    stmt = select(ExternalProductMap).where(ExternalProductMap.tenant_id == tenant_id)
    if external_product_id and external_name:
        # E-18: an export that carries ids is answered by id-keyed rows AND
        # by the title-keyed rows a desk wrote before anyone recorded the id
        # — the same listing, confirmed under the name it prints
        stmt = stmt.where(or_(
            ExternalProductMap.external_product_id == external_product_id.strip(),
            and_(ExternalProductMap.external_product_id == "",
                 ExternalProductMap.external_name_norm == normalize_external_name(external_name)),
        ))
        external_product_id = None
        external_name = None
    if at is not None:
        stmt = stmt.where(
            or_(ExternalProductMap.effective_from.is_(None),
                ExternalProductMap.effective_from <= at),
            or_(ExternalProductMap.effective_to.is_(None),
                ExternalProductMap.effective_to > at),
        )
        if status_filter is None:
            status_filter = "active"
    return list_rows(
        db, stmt,
        filters={
            ExternalProductMap.source: source.strip().lower() if source else None,
            ExternalProductMap.external_product_id: (
                external_product_id.strip() if external_product_id else None
            ),
            ExternalProductMap.external_name_norm: normalize_external_name(external_name),
            ExternalProductMap.external_sku_id: (
                (normalize_external_name(external_sku_id) or "") if external_sku_id is not None else None
            ),
            ExternalProductMap.product_id: product_id,
            ExternalProductMap.status: status_scope(status_filter),
        },
        keyword=keyword,
        keyword_columns=(ExternalProductMap.external_name, ExternalProductMap.external_product_id),
        order_by=(
            ExternalProductMap.source.asc(),
            ExternalProductMap.external_product_id.asc(),
            ExternalProductMap.created_at.asc(),
            ExternalProductMap.id.asc(),
        ),
        pagination=page_only_pagination(page, size, default=50),
        sort=order_by,
        read_model=ExternalProductMapRead,
        extra=extra,
    )



@router.post("/external-product-maps/resolve", response_model_exclude_unset=True)
def resolve_external_products(
    payload: ResolveExternalProductsRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Translate a whole import's listings in ONE call. A READ — POST only
    because five hundred titles do not fit a query string; it writes
    nothing, and confirming a pairing is still `POST /external-product-maps`
    after a person says so.

    An order file names a hundred listings, and the translation query
    answers one: the agent made a hundred calls, each a turn, and for every
    title nobody had mapped yet `/product-matches` loaded and compared the
    whole catalog again. Here the map is read with one indexed query, and
    with `with_candidates` the catalog is loaded and indexed once for every
    unmapped title together.

    Each listing is answered exactly as `GET /external-product-maps` with
    `at` would answer it: live rows whose window covers the date (the
    listing's own `at`, else the request's; no date = no window test), an
    id AND a title matching id-keyed rows or title-keyed ones. `data[i]`
    answers `listings[i]`."""
    ids = {l.external_product_id for l in payload.listings if l.external_product_id}
    norms = {n for l in payload.listings if (n := normalize_external_name(l.external_name))}
    conditions = []
    if ids:
        conditions.append(ExternalProductMap.external_product_id.in_(ids))
    if norms:
        conditions.append(ExternalProductMap.external_name_norm.in_(norms))
    rows = list(db.scalars(
        select(ExternalProductMap)
        .where(
            ExternalProductMap.tenant_id == tenant_id,
            ExternalProductMap.source == payload.source,
            ExternalProductMap.status == "active",
            or_(*conditions),
        )
        .order_by(ExternalProductMap.external_product_id.asc(), ExternalProductMap.created_at.asc(), ExternalProductMap.id.asc())
    ))
    by_id: dict[str, list[ExternalProductMap]] = {}
    by_norm: dict[str, list[ExternalProductMap]] = {}
    for row in rows:
        if row.external_product_id:
            by_id.setdefault(row.external_product_id, []).append(row)
        if row.external_name_norm:
            by_norm.setdefault(row.external_name_norm, []).append(row)

    def covers(row: ExternalProductMap, when: date | None) -> bool:
        if when is None:
            return True
        return (row.effective_from is None or row.effective_from <= when) and \
               (row.effective_to is None or row.effective_to > when)

    answers: list[dict] = []
    unmapped_titles: list[tuple[int, str]] = []
    for index, listing in enumerate(payload.listings):
        when = listing.at or payload.at
        norm = normalize_external_name(listing.external_name)
        if listing.external_product_id and norm:
            found = list(by_id.get(listing.external_product_id, ())) + [
                row for row in by_norm.get(norm, ()) if row.external_product_id == ""
            ]
        elif listing.external_product_id:
            found = list(by_id.get(listing.external_product_id, ()))
        else:
            found = list(by_norm.get(norm, ()))
        if listing.external_sku_id is not None:
            wanted_sku = normalize_external_name(listing.external_sku_id) or ""
            found = [row for row in found if row.external_sku_id == wanted_sku]
        found = [row for row in found if covers(row, when)]
        answer = {
            "index": index,
            "external_product_id": listing.external_product_id,
            "external_sku_id": listing.external_sku_id,
            "external_name": listing.external_name,
            "at": when,
            "status": "mapped" if found else "unmapped",
            "maps": [ExternalProductMapRead.model_validate(row).model_dump(mode="json", by_alias=True) for row in found],
        }
        if not found and payload.with_candidates and (listing.external_name or "").strip():
            unmapped_titles.append((index, listing.external_name))
        answers.append(answer)
    if unmapped_titles:
        matcher = _CatalogMatcher(db, tenant_id)
        shortlist_by_title: dict[str, list[dict]] = {}
        for _index, title in unmapped_titles:
            if title not in shortlist_by_title:
                shortlist_by_title[title] = matcher.shortlist(title, payload.candidate_limit)
        titles = list(shortlist_by_title)
        hydrated = dict(zip(titles, _hydrate_candidates(db, tenant_id, [shortlist_by_title[t] for t in titles])))
        for index, title in unmapped_titles:
            answers[index]["candidates"] = hydrated[title]
    mapped = sum(1 for a in answers if a["status"] == "mapped")
    return {"data": jsonable_encoder(answers), "meta": {"total": len(answers), "mapped": mapped, "unmapped": len(answers) - mapped}}

@router.post(
    "/external-product-maps",
    response_model=ExternalProductMapEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_external_product_map(
    payload: CreateExternalProductMapRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_map_curation(actor)
    tenant_id = actor.tenant_id
    require_sales_channel(db, tenant_id, source=payload.source)
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    if payload.sku_id is not None:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, payload.sku_id)
        if sku.product_id != payload.product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"sku {payload.sku_id} belongs to product {sku.product_id}, not {payload.product_id}",
            )
    # Only an OPEN live assertion claims the slot: a row with a closed window
    # is history (the listing meant this product until the swap), so a
    # listing may swap BACK to a product it meant before, and closed-window
    # rows for back-dated imports never conflict with the current pairing.
    name_norm = normalize_external_name(payload.external_name)
    # the spec text is matched the way the title is (E-01): "片幅:11X14" and
    # "片幅:11x14" are one spec, and a lookup folds the same way
    payload.external_sku_id = normalize_external_name(payload.external_sku_id) or ""
    _require_map_window_authority(actor, payload.effective_from, payload.effective_to)
    if payload.status == "active" and payload.effective_to is None:
        # the listing's identity is its id, or — when the export carries
        # none — its normalized title; the open slot is claimed per that
        identity = [ExternalProductMap.external_product_id == payload.external_product_id]
        if not payload.external_product_id:
            identity.append(ExternalProductMap.external_name_norm == name_norm)
        existing = db.scalar(
            select(ExternalProductMap).where(
                ExternalProductMap.tenant_id == tenant_id,
                ExternalProductMap.source == payload.source,
                *identity,
                ExternalProductMap.external_sku_id == payload.external_sku_id,
                ExternalProductMap.product_id == payload.product_id,
                ExternalProductMap.status == "active",
                ExternalProductMap.effective_to.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"map {existing.id} already pairs this external listing with this "
                    "product, open-ended — PATCH it, or close its window "
                    "(effective_to) if the listing changed meaning on a date"
                ),
            )
    row = ExternalProductMap(
        tenant_id=tenant_id,
        source=payload.source,
        external_product_id=payload.external_product_id,
        external_sku_id=payload.external_sku_id,
        external_name=payload.external_name,
        external_name_norm=name_norm,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        quantity=payload.quantity,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(row)
    commit_or_conflict(db, "an open-ended map for this (source, external listing, product) already exists")
    db.refresh(row)
    return envelope(ExternalProductMapRead.model_validate(row).model_dump(by_alias=True))


@router.patch(
    "/external-product-maps/{map_id}",
    response_model=ExternalProductMapEnvelope,
    response_model_exclude_unset=True,
)
def update_external_product_map(
    map_id: str,
    payload: UpdateExternalProductMapRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_map_curation(actor)
    row = get_scoped_or_404(db, ExternalProductMap, actor.tenant_id, map_id)
    updates = payload.model_dump(exclude_unset=True)
    _require_map_row_authority(actor, row)
    _require_map_window_authority(actor, updates.get("effective_from"), updates.get("effective_to"))
    if "sku_id" in updates and updates["sku_id"] is not None:
        sku = get_scoped_or_404(db, ProductSku, actor.tenant_id, updates["sku_id"])
        if sku.product_id != row.product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"sku {updates['sku_id']} belongs to product {sku.product_id}, not {row.product_id}",
            )
    if "external_name" in updates:
        if not row.external_product_id:
            # on a name-keyed row the title IS the identity — the same rule
            # that keeps ids uneditable: close the window and add the row
            # the platform now shows, never bend this one
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "this map is keyed by its title (no external_product_id); the "
                    "title is its identity. A renamed listing is a swap: close this "
                    "row's window (effective_to) and create a row for the new title"
                ),
            )
        row.external_name_norm = normalize_external_name(updates["external_name"])
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    # cross-field, so the schema cannot see it: a PATCH may move one bound
    # against the other already on the row
    if (row.effective_from is not None and row.effective_to is not None
            and row.effective_to <= row.effective_from):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "effective_to must be after effective_from — the window is "
                "[from, to), and a zero-length window asserts nothing"
            ),
        )
    commit_or_conflict(db, (
                        "reopening this pairing collides with an open-ended map for the "
                        "same (source, external listing, product) — close that one first"
                    ))
    db.refresh(row)
    return envelope(ExternalProductMapRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/external-product-maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_external_product_map(
    map_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_map_curation(actor)
    _require_map_row_authority(actor, get_scoped_or_404(db, ExternalProductMap, actor.tenant_id, map_id))
    return archive_row(db, actor, ExternalProductMap, map_id, permission="order.submit_own"
                       if not has_permission(actor, "master_data.manage") else None)


# --- inventory: items are running sums of an append-only detail ledger -----


def require_inventory_manage(actor: Actor) -> None:
    """Guard the stock ledger and its positions.

    Strict — no legacy alias. `require_master_data_manage` accepts
    `users.manage` because it shipped before the admin top-up existed and
    needed a bridge; this capability ships after it, so admins hold it on
    deploy, and migration 0063 grants it to every role that held
    `master_data.manage` — the roles that could do this yesterday can do it
    today, and a workspace can now take it away from the ones that should not.
    """
    require_permission(actor, "inventory.manage")


@router.post(
    "/inventory-items",
    response_model=InventoryItemEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(
    payload: CreateInventoryItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_inventory_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    if payload.sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, payload.sku_id)
        if sku.product_id != payload.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to product_id",
            )
    facility, lot_id = payload.facility.strip(), payload.lot_id.strip()
    if payload.facility_id:
        registered = get_scoped_or_404(db, Facility, tenant_id, payload.facility_id)
        if not facility:
            # the registered name backfills the identity string, so the two
            # spellings of "which warehouse" cannot drift apart at birth
            facility = registered.name
        elif facility != registered.name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"facility {facility!r} does not match facility_id's registered "
                    f"name {registered.name!r} — pass one, or make them agree"
                ),
            )
    existing = _find_item(db, tenant_id, payload.product_id, payload.sku_id, facility, lot_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"inventory item {existing.id} already holds this "
                "(product, sku, facility, lot) position — post a detail to move its stock"
            ),
        )
    item = InventoryItem(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        facility=facility,
        facility_id=payload.facility_id,
        lot_id=lot_id,
        bin_number=payload.bin_number,
        expire_date=payload.expire_date,
        received_at=payload.received_at,
        unit_cost=payload.unit_cost,
        currency=payload.currency,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an inventory item for this (product, sku, facility, lot) already exists",
        )
    # the opening balance is a ledger entry like any other movement
    if payload.initial_quantity is not None and payload.initial_quantity != 0:
        post_inventory_detail(
            db,
            item=item,
            quantity_on_hand_diff=payload.initial_quantity,
            reason=payload.initial_reason,
            description=payload.initial_description,
            unit_cost=payload.unit_cost,
            created_by=attributed(actor, None),
        )
    db.commit()
    db.refresh(item)
    return envelope(InventoryItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/inventory-items/{item_id}", response_model=InventoryItemEnvelope, response_model_exclude_unset=True)
def update_inventory_item(
    item_id: str,
    payload: UpdateInventoryItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Identity, dates and cost — never quantities: the request model carries
    no quantity fields, so a client sending one gets a 422 naming it. Stock
    moves only through POST /inventory-item-details."""
    require_inventory_manage(actor)
    item = get_scoped_or_404(db, InventoryItem, actor.tenant_id, item_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        item.metadata_jsonb = updates.pop("metadata")
    if updates.get("facility_id"):
        # the registry pointer beside the free-text name (E-25): positions
        # predate the registry, and a rename of the warehouse must not orphan them
        get_scoped_or_404(db, Facility, actor.tenant_id, updates["facility_id"])
    for field, value in updates.items():
        setattr(item, field, value.strip() if field in ("facility", "lot_id") else value)
    commit_or_conflict(db, "an inventory item for this (product, sku, facility, lot) already exists")
    db.refresh(item)
    return envelope(InventoryItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/inventory-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, InventoryItem, item_id, permission="inventory.manage")


@router.get(
    "/inventory-item-details",
    response_model=InventoryItemDetailListEnvelope,
    response_model_exclude_unset=True,
)
def list_inventory_item_details(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    inventory_item_id: str | None = None,
    reason: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    sales_order_id: str | None = None,
    purchase_order_id: str | None = None,
    include_archived_items: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(InventoryItemDetail, ranges=('created_at', 'effective_at'), equals=()))] = None,
):
    stmt = (
        select(InventoryItemDetail)
        .options(selectinload(InventoryItemDetail.item))
        .where(InventoryItemDetail.tenant_id == tenant_id)
    )
    if inventory_item_id is None and not include_archived_items:
        # an archived position's movements are history — answered when the
        # position is named or history is asked for, never inside "what
        # moved this week"
        stmt = stmt.where(InventoryItemDetail.item.has(InventoryItem.status == "active"))
    return list_rows(
        db, stmt,
        filters={
            InventoryItemDetail.inventory_item_id: inventory_item_id,
            InventoryItemDetail.reason: reason,
            InventoryItemDetail.entity_type: entity_type,
            InventoryItemDetail.entity_id: entity_id,
            InventoryItemDetail.sales_order_id: sales_order_id,
            InventoryItemDetail.purchase_order_id: purchase_order_id,
        },
        order_by=(
            InventoryItemDetail.effective_at.desc(),
            InventoryItemDetail.created_at.desc(),
            InventoryItemDetail.id.desc(),
        ),
        pagination=page_only_pagination(page, size, default=50),
        sort=order_by,
        read_model=InventoryItemDetailRead,
        extra=extra,
    )


def _require_hold_within_bounds(db: Session, item: InventoryItem, reason: str, atp: float, sales_order_id: str) -> None:
    """The two guards the ledger's shape check does not give (E-15): a hold
    that would push available below zero is over-selling, and a release
    larger than what this order still holds at this position invents
    availability. Both are 409s naming the numbers, so the agent's next
    sentence to sales is the right one."""
    available = float(item.available_to_promise or 0)
    if reason == "reserved" and available + atp < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"this hold would push available to promise below zero: {available:g} available "
                f"at this position, {-atp:g} asked — the shortfall is a conversation with "
                "sales, not a negative number"
            ),
        )
    if reason == "reservation_released":
        held = -float(db.scalar(
            select(func.coalesce(func.sum(InventoryItemDetail.available_to_promise_diff), 0)).where(
                InventoryItemDetail.tenant_id == item.tenant_id,
                InventoryItemDetail.inventory_item_id == item.id,
                InventoryItemDetail.sales_order_id == sales_order_id,
                InventoryItemDetail.reason.in_(("reserved", "reservation_released")),
            )
        ) or 0)
        if atp > held + 1e-9:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"this order holds {held:g} at this position, not {atp:g} — a release "
                    "gives back at most what was held (post-stock already released what "
                    "the shipment consumed)"
                ),
            )




def _order_lines_by_goods(db: Session, order: SalesOrder) -> dict[tuple[str, str | None], list[SalesOrderItem]]:
    lines: dict[tuple[str, str | None], list[SalesOrderItem]] = {}
    for line in db.scalars(select(SalesOrderItem).where(
        SalesOrderItem.tenant_id == order.tenant_id, SalesOrderItem.order_id == order.id,
        SalesOrderItem.deleted_at.is_(None), SalesOrderItem.product_id.is_not(None),
    )):
        lines.setdefault((line.product_id, line.sku_id), []).append(line)
    return lines


def _lock_position(db: Session, tenant_id: str, item_id: str) -> InventoryItem:
    """The row lock before any running sum is read (review N02): two holds
    that both read ATP=10 both passed and left -4. `populate_existing` so the
    locked read replaces whatever stale value the session already held."""
    return db.scalar(
        select(InventoryItem)
        .where(InventoryItem.tenant_id == tenant_id, InventoryItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _position_for_order(db: Session, order: SalesOrder, inventory_item_id: str) -> InventoryItem:
    """The position a hold names must hold goods the order sells: a hold
    on a shelf the order never mentions is a typo the ledger would keep."""
    item = require_active_row(
        db, InventoryItem, order.tenant_id, inventory_item_id, "inventory item",
        detail="inventory item is archived — set it active before holding stock there",
    )
    goods = _order_lines_by_goods(db, order)
    if (item.product_id, item.sku_id) not in goods and (item.product_id, None) not in goods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"inventory item {item.id} holds product {item.product_id}"
                + (f" sku {item.sku_id}" if item.sku_id else "")
                + f", which order {order.order_no} has no line for"
            ),
        )
    return item


@router.post(
    "/sales-orders/{order_id}/reserve",
    response_model=StockReservationEnvelope,
    response_model_exclude_unset=True,
)
def reserve_stock_for_order(
    order_id: str,
    payload: ReserveStockRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """占货: hold goods for an order. The ONLY way a `reserved` row enters
    the ledger — an availability fact tied to the order it serves, posted
    by the warehouse from the positions it chooses. Each line names a
    position holding goods the order sells and a quantity; a hold that
    would push available to promise below zero is refused with the
    numbers. Post-stock on the order's shipment consumes the hold itself."""
    require_inventory_manage(actor)
    tenant_id = actor.tenant_id
    order = get_scoped_or_404(db, SalesOrder, tenant_id, order_id)
    ensure_document_not_deleted(order)
    machine = get_builtin_machine(db, tenant_id, "sales_order")
    if is_terminal_state(machine, order.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"order {order.order_no} is {order.status}, a state nothing follows — there is nothing to hold for",
        )
    report = []
    # a stable lock order across requests (by position id), and one lock per
    # position however many lines name it — the bound check then sees the
    # earlier line of the same request already applied
    for line in sorted(payload.lines, key=lambda l: l.inventory_item_id):
        item = _position_for_order(db, order, line.inventory_item_id)
        item = _lock_position(db, tenant_id, item.id)
        _require_hold_within_bounds(db, item, "reserved", -line.quantity, order.id)
        detail = post_inventory_detail(
            db, item=item, quantity_on_hand_diff=0, available_to_promise_diff=-line.quantity,
            reason="reserved",
            description=line.description or payload.description or f"held for order {order.order_no}",
            entity_type="sales_order_item" if line.order_item_id else None,
            entity_id=line.order_item_id,
            sales_order_id=order.id, created_by=attributed(actor, None),
        )
        report.append(StockReservationLineRead(
            inventory_item_id=item.id, detail_id=detail.id, quantity=line.quantity,
            available_to_promise=float(item.available_to_promise),
        ))
    db.commit()
    return envelope(StockReservationRead(order_id=order.id, reason="reserved", lines=report).model_dump(by_alias=True))


@router.post(
    "/sales-orders/{order_id}/release",
    response_model=StockReservationEnvelope,
    response_model_exclude_unset=True,
)
def release_stock_for_order(
    order_id: str,
    payload: ReleaseStockRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Give a hold back by hand — a cancelled order, a line the customer
    dropped. Without `lines`, every outstanding hold of the order is
    released; with them, exactly those quantities, never more than the
    order still holds at that position (post-stock already released what
    the shipment consumed)."""
    require_inventory_manage(actor)
    tenant_id = actor.tenant_id
    order = get_scoped_or_404(db, SalesOrder, tenant_id, order_id)
    ensure_document_not_deleted(order)
    wanted: list[tuple[str, float, str | None]]
    if payload.lines:
        wanted = [(line.inventory_item_id, line.quantity, line.description) for line in payload.lines]
    else:
        held = db.execute(
            select(InventoryItemDetail.inventory_item_id,
                   func.coalesce(func.sum(InventoryItemDetail.available_to_promise_diff), 0))
            .where(
                InventoryItemDetail.tenant_id == tenant_id,
                InventoryItemDetail.sales_order_id == order.id,
                InventoryItemDetail.reason.in_(("reserved", "reservation_released")),
            )
            .group_by(InventoryItemDetail.inventory_item_id)
        ).all()
        wanted = [(position_id, -float(total), None) for position_id, total in held if -float(total) > 1e-9]
    report = []
    for position_id, quantity, words in sorted(wanted, key=lambda w: w[0]):
        item = require_active_row(
            db, InventoryItem, tenant_id, position_id, "inventory item",
            detail="inventory item is archived — set it active before releasing its hold",
        )
        item = _lock_position(db, tenant_id, item.id)
        _require_hold_within_bounds(db, item, "reservation_released", quantity, order.id)
        detail = post_inventory_detail(
            db, item=item, quantity_on_hand_diff=0, available_to_promise_diff=quantity,
            reason="reservation_released",
            description=words or payload.description or f"hold for order {order.order_no} given back",
            sales_order_id=order.id, created_by=attributed(actor, None),
        )
        report.append(StockReservationLineRead(
            inventory_item_id=item.id, detail_id=detail.id, quantity=quantity,
            available_to_promise=float(item.available_to_promise),
        ))
    db.commit()
    return envelope(StockReservationRead(order_id=order.id, reason="reservation_released", lines=report).model_dump(by_alias=True))


@router.post(
    "/inventory-items/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_inventory(
    payload: BulkInventoryUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The stock-take import. Quantities land as ledger details — a counted
    number that differs from the system count becomes an `import_override`
    movement naming both numbers, never an edit of the item."""
    require_inventory_manage(actor)
    result = bulk_inventory_upsert(
        db,
        tenant_id=actor.tenant_id,
        rows=payload.rows,
        dry_run=payload.dry_run,
        on_error=payload.on_error,
        created_by=attributed(actor, None),
    )
    return _finish_bulk_import(
        db, actor, result,
        action="inventory.imported",
        detail={"on_error": payload.on_error},
    )


# --- came back down from common.py: nothing else was using them ------------
#
# Promoted while `routes.py` was being decomposed, on a call graph that had
# master data mixed in with everything else. Once the modules existed, both
# turned out to be reached from here and nowhere else, and `common.py` does
# not use either — which is the whole test for whether a thing is shared.
# `tests/test_shared_core.py` keeps that honest from here on.


def ensure_code_available(
    db: Session,
    model,
    tenant_id: str,
    code_attr: str,
    code: str | None,
    *,
    exclude_id: str | None = None,
) -> None:
    """Reject a master-data code the tenant already uses, as a 409 naming the
    conflict, before the database raises an opaque integrity error.

    The unique index is the real guarantee; this exists so the ordinary case —
    someone re-adds a product that is already in the catalog — comes back as a
    conflict the caller can act on instead of a 500. `exclude_id` lets an
    update keep its own code.
    """
    if not code:
        return
    stmt = select(model.id).where(
        model.tenant_id == tenant_id, getattr(model, code_attr) == code
    )
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{code_attr} '{code}' already exists in this tenant",
        )


def _run_bulk_upsert(
    *,
    db: Session,
    actor: Actor,
    family: str,
    payload,
) -> dict:
    """Shared tail for the three bulk endpoints: capability gate, upsert, one
    audit entry for the whole import, and a single commit-or-rollback.

    The audit records the import as ONE event with its counts, not one entry
    per row: 500 near-identical rows would bury the trail that makes it useful,
    and the interesting fact is "someone replaced the price list on Tuesday"."""
    require_master_data_manage(actor)
    result = bulk_upsert(
        db,
        tenant_id=actor.tenant_id,
        family=family,
        rows=payload.rows,
        dry_run=payload.dry_run,
        on_error=payload.on_error,
    )
    return _finish_bulk_import(
        db, actor, result,
        action="master_data.imported",
        detail={"family": family, "on_error": payload.on_error},
    )


# --- reads declared as data (app/api/registry.py) ---------------------------
# Plain lists and by-id reads: the URL, the filters in contract order, the
# family's ordering. Anything with logic of its own is a handler above.

register(
    router,
    ListResource(
        path="/vendors",
        name="list_vendors",
        model=Vendor,
        read_model=VendorRead,
        response_model=VendorListEnvelope,
        params=(KEYWORD, "tax_id", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(Vendor.created_at.desc(), Vendor.id.desc()),
        keyword_columns=(Vendor.name,),
    ),
    GetResource(
        path="/vendors/{vendor_id}",
        name="get_vendor",
        model=Vendor,
        read_model=VendorRead,
        response_model=VendorEnvelope,
        id_param="vendor_id",
    ),
    # the retail identity key, as tax_id is the B2B one — "这个手机号
    # 是不是老客户" is the question a counter agent actually asks
    ListResource(
        path="/customers",
        name="list_customers",
        model=Customer,
        read_model=CustomerRead,
        response_model=CustomerListEnvelope,
        params=(KEYWORD, "tax_id", "phone", "customer_kind", "customer_type", "geo_id", "territory_id", "owner_employee_id", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(Customer.created_at.desc(), Customer.id.desc()),
        keyword_columns=(Customer.name,),
    ),
    GetResource(
        path="/customers/{customer_id}",
        name="get_customer",
        model=Customer,
        read_model=CustomerRead,
        response_model=CustomerEnvelope,
        id_param="customer_id",
    ),
    ListResource(
        path="/facilities",
        name="list_facilities",
        model=Facility,
        read_model=FacilityRead,
        response_model=FacilityListEnvelope,
        params=("facility_type", STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(Facility.name.asc(), Facility.id.asc()),
        keyword_columns=(Facility.name, Facility.facility_code, Facility.address),
        default_size=100,
    ),
    GetResource(
        path="/facilities/{facility_id}",
        name="get_facility",
        model=Facility,
        read_model=FacilityRead,
        response_model=FacilityEnvelope,
        id_param="facility_id",
    ),
    ListResource(
        path="/sales-channels",
        name="list_sales_channels",
        model=SalesChannel,
        read_model=SalesChannelRead,
        response_model=SalesChannelListEnvelope,
        params=("channel_kind", STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(SalesChannel.channel_code.asc(), SalesChannel.id.asc()),
        keyword_columns=(SalesChannel.channel_code, SalesChannel.name),
        default_size=100,
    ),
    GetResource(
        path="/sales-channels/{channel_id}",
        name="get_sales_channel",
        model=SalesChannel,
        read_model=SalesChannelRead,
        response_model=SalesChannelEnvelope,
        id_param="channel_id",
    ),
    # preferred shippers first; unranked trail in arrival order
    ListResource(
        path="/store-facilities",
        name="list_store_facilities",
        model=StoreFacility,
        read_model=StoreFacilityRead,
        response_model=StoreFacilityListEnvelope,
        params=("store_id", "facility_id", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(StoreFacility.priority.asc().nulls_last(), StoreFacility.created_at.asc(), StoreFacility.id.asc()),
        default_size=100,
    ),
    # the primary first, then the curated order, then arrival
    ListResource(
        path="/product-images",
        name="list_product_images",
        model=ProductImage,
        read_model=ProductImageRead,
        response_model=ProductImageListEnvelope,
        params=("product_id", "image_type", PAGE, SIZE, ORDER_BY),
        order_by=(ProductImage.is_primary.desc(), ProductImage.sort_order.asc().nulls_last(), ProductImage.created_at.asc()),
        equals=("attachment_id",),
        default_size=100,
    ),
    ListResource(
        path="/bills-of-materials",
        name="list_bills_of_materials",
        model=BillOfMaterials,
        read_model=BillOfMaterialsRead,
        response_model=BillOfMaterialsListEnvelope,
        params=("product_id", STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(BillOfMaterials.created_at.desc(), BillOfMaterials.id.desc()),
        keyword_columns=(BillOfMaterials.bom_code, BillOfMaterials.version),
        options=(selectinload(BillOfMaterials.product),),
    ),
    ListResource(
        path="/bom-items",
        name="list_bom_items",
        model=BomItem,
        read_model=BomItemRead,
        response_model=BomItemListEnvelope,
        params=("bom_id", "component_product_id", PAGE, SIZE, ORDER_BY),
        order_by=(BomItem.line_no.asc(), BomItem.created_at.asc()),
        default_size=100,
        options=(selectinload(BomItem.component),),
    ),
    GetResource(
        path="/product-categories/{category_id}",
        name="get_product_category",
        model=ProductCategory,
        read_model=ProductCategoryRead,
        response_model=ProductCategoryEnvelope,
        id_param="category_id",
    ),
    ListResource(
        path="/product-skus",
        name="list_product_skus",
        model=ProductSku,
        read_model=ProductSkuRead,
        response_model=ProductSkuListEnvelope,
        params=("product_id", "sku_code", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(ProductSku.created_at.asc(), ProductSku.sku_code.asc(), ProductSku.id.asc()),
    ),
    GetResource(
        path="/product-skus/{sku_id}",
        name="get_product_sku",
        model=ProductSku,
        read_model=ProductSkuRead,
        response_model=ProductSkuEnvelope,
        id_param="sku_id",
    ),
    # newest first: the live price and its history read top-down
    ListResource(
        path="/product-prices",
        name="list_product_prices",
        model=ProductPrice,
        read_model=ProductPriceRead,
        response_model=ProductPriceListEnvelope,
        params=("product_id", "sku_id", "price_type", "currency", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(ProductPrice.created_at.desc(), ProductPrice.id.desc()),
    ),
    GetResource(
        path="/product-prices/{price_id}",
        name="get_product_price",
        model=ProductPrice,
        read_model=ProductPriceRead,
        response_model=ProductPriceEnvelope,
        id_param="price_id",
    ),
    # preferred sources first; unranked trail in arrival order
    ListResource(
        path="/supplier-products",
        name="list_supplier_products",
        model=SupplierProduct,
        read_model=SupplierProductRead,
        response_model=SupplierProductListEnvelope,
        params=("product_id", "vendor_id", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(SupplierProduct.preference.asc().nulls_last(), SupplierProduct.created_at.asc(), SupplierProduct.id.asc()),
        equals=("currency",),
    ),
    GetResource(
        path="/supplier-products/{supplier_product_id}",
        name="get_supplier_product",
        model=SupplierProduct,
        read_model=SupplierProductRead,
        response_model=SupplierProductEnvelope,
        id_param="supplier_product_id",
    ),
    # the reverse lookup this table exists for: the customer's PO says
    # "货号 KH-3301" and the agent needs to know which product that is
    ListResource(
        path="/customer-products",
        name="list_customer_products",
        model=CustomerProduct,
        read_model=CustomerProductRead,
        response_model=CustomerProductListEnvelope,
        params=("product_id", "customer_id", "customer_product_code", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(CustomerProduct.created_at.asc(), CustomerProduct.id.asc()),
        equals=("currency",),
    ),
    GetResource(
        path="/customer-products/{customer_product_id}",
        name="get_customer_product",
        model=CustomerProduct,
        read_model=CustomerProductRead,
        response_model=CustomerProductEnvelope,
        id_param="customer_product_id",
    ),
    # the primary first, then the rest by arrival — the order a person
    # answering "找谁" actually wants
    ListResource(
        path="/customer-contacts",
        name="list_customer_contacts",
        model=CustomerContact,
        read_model=CustomerContactRead,
        response_model=CustomerContactListEnvelope,
        params=("customer_id", "phone", STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(CustomerContact.is_primary.desc(), CustomerContact.created_at.asc(), CustomerContact.id.asc()),
        keyword_columns=(CustomerContact.name, CustomerContact.title, CustomerContact.wechat, CustomerContact.email, CustomerContact.phone),
    ),
    GetResource(
        path="/customer-contacts/{contact_id}",
        name="get_customer_contact",
        model=CustomerContact,
        read_model=CustomerContactRead,
        response_model=CustomerContactEnvelope,
        id_param="contact_id",
    ),
    GetResource(
        path="/external-product-maps/{map_id}",
        name="get_external_product_map",
        model=ExternalProductMap,
        read_model=ExternalProductMapRead,
        response_model=ExternalProductMapEnvelope,
        id_param="map_id",
    ),
    GetResource(
        path="/inventory-items/{item_id}",
        name="get_inventory_item",
        model=InventoryItem,
        read_model=InventoryItemRead,
        response_model=InventoryItemEnvelope,
        id_param="item_id",
    ),
)


def _store_read(db: Session, tenant_id: str, store: Store) -> dict:
    """A store with the facilities it ships from, in fulfilment priority."""
    data = StoreRead.model_validate(store).model_dump(by_alias=True)
    links = db.scalars(
        select(StoreFacility)
        .where(
            StoreFacility.tenant_id == tenant_id,
            StoreFacility.store_id == store.id,
            StoreFacility.status == "active",
        )
        .order_by(StoreFacility.priority.asc().nulls_last(), StoreFacility.created_at.asc())
    ).all()
    data["fulfilment_facilities"] = [
        StoreFacilityRead.model_validate(link).model_dump(by_alias=True) for link in links
    ]
    return data


def _root_categories_only(stmt, values: dict):
    return stmt.where(ProductCategory.parent_id.is_(None)) if values.get("root_only") else stmt


def _stock_position_filters(stmt, values: dict):
    # `facility` and `lot_id` are compared even when empty: "" is the
    # no-facility / no-lot position, a value, not an absent filter
    if values.get("facility") is not None:
        stmt = stmt.where(InventoryItem.facility == values["facility"])
    if values.get("lot_id") is not None:
        stmt = stmt.where(InventoryItem.lot_id == values["lot_id"])
    return stmt


register(
    router,
    ListResource(
        path="/product-categories",
        name="list_product_categories",
        model=ProductCategory,
        read_model=ProductCategoryRead,
        response_model=ProductCategoryListEnvelope,
        params=("parent_id", Param("root_only", bool, False), STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(ProductCategory.name.asc(), ProductCategory.id.asc()),
        keyword_columns=(ProductCategory.name, ProductCategory.category_code),
        default_size=200,
        where=_root_categories_only,
    ),
    ListResource(
        path="/products",
        name="list_products",
        model=Product,
        read_model=None,
        response_model=ProductListEnvelope,
        params=(KEYWORD, "category_id", "product_type", STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(Product.created_at.desc(), Product.id.desc()),
        keyword_columns=(Product.name, Product.product_code),
        equals=("currency",),
        # one query for every row's SKU statistics, not one per product
        render=lambda db, tenant_id: lambda products: product_reads_with_sku_stats(db, tenant_id, products),
    ),
    GetResource(
        path="/products/{product_id}",
        name="get_product",
        model=Product,
        read_model=ProductRead,
        response_model=ProductEnvelope,
        id_param="product_id",
        read=lambda db, tenant_id, product: product_read_with_skus_flag(db, product),
    ),
    GetResource(
        path="/bills-of-materials/{bom_id}",
        name="get_bill_of_materials",
        model=BillOfMaterials,
        read_model=BillOfMaterialsRead,
        response_model=BillOfMaterialsEnvelope,
        id_param="bom_id",
        read=lambda db, tenant_id, bom: _bom_read(db, tenant_id, bom, with_items=True),
    ),
    GetResource(
        path="/stores/{store_id}",
        name="get_store",
        model=Store,
        read_model=StoreRead,
        response_model=StoreEnvelope,
        id_param="store_id",
        read=_store_read,
    ),
    ListResource(
        path="/inventory-items",
        name="list_inventory_items",
        model=InventoryItem,
        read_model=InventoryItemRead,
        response_model=InventoryItemListEnvelope,
        params=("product_id", "sku_id", Param("facility"), Param("lot_id"), STATUS, PAGE, SIZE, ORDER_BY),
        order_by=(InventoryItem.created_at.desc(), InventoryItem.id.desc()),
        ranges=("created_at", "expire_date", "received_at"),
        equals=("currency", "facility_id"),
        where=_stock_position_filters,
    ),
)
