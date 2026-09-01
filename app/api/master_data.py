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

import uuid

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    _finish_bulk_import,
    archive_row,
    commit_or_code_conflict,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    page_only_pagination,
    require_master_data_manage,
)
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    ExternalProductMap,
    Facility,
    InventoryItem,
    InventoryItemDetail,
    PurchaseOrder,
    Store,
    StoreFacility,
    SalesOrder,
    Product,
    ProductCategory,
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
    CreateInventoryItemDetailRequest,
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
    CreateCustomerContactRequest,
    CreateCustomerProductRequest,
    CustomerContactEnvelope,
    CustomerContactListEnvelope,
    CustomerContactRead,
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
    UpdateCustomerContactRequest,
    UpdateCustomerProductRequest,
    UpdateCustomerRequest,
    UpdateExternalProductMapRequest,
    UpdateInventoryItemRequest,
    UpdateProductPriceRequest,
    CreateStoreFacilityRequest,
    CreateStoreRequest,
    StoreEnvelope,
    StoreFacilityEnvelope,
    StoreFacilityListEnvelope,
    StoreFacilityRead,
    StoreListEnvelope,
    StoreRead,
    UpdateFacilityRequest,
    UpdateProductCategoryRequest,
    UpdateStoreFacilityRequest,
    UpdateStoreRequest,
    UpdateProductRequest,
    UpdateProductSkuRequest,
    UpdateSupplierProductRequest,
    UpdateVendorRequest,
    VendorEnvelope,
    VendorListEnvelope,
    VendorRead,
)
from app.services.inventory_import import _find_item, bulk_inventory_upsert, post_inventory_detail
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
    stats = product_sku_stats(db, tenant_id, [product.id for product in products])
    data = []
    for product in products:
        read = ProductRead.model_validate(product)
        total, active = stats.get(product.id, (0, 0))
        read.sku_count = total
        read.has_skus = active > 0
        data.append(read.model_dump(by_alias=True))
    return data


def product_read_with_skus_flag(db: Session, product: Product) -> dict:
    return product_reads_with_sku_stats(db, product.tenant_id, [product])[0]


# --- vendors and customers: the two sides you trade with -------------------


@router.get("/vendors", response_model=VendorListEnvelope, response_model_exclude_unset=True)
def list_vendors(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    tax_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Vendor).where(Vendor.tenant_id == tenant_id),
        filters={Vendor.tax_id: tax_id, Vendor.status: status_filter},
        keyword=keyword,
        keyword_columns=(Vendor.name,),
        order_by=(Vendor.created_at.desc(), Vendor.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=VendorRead,
    )


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


@router.get("/vendors/{vendor_id}", response_model=VendorEnvelope, response_model_exclude_unset=True)
def get_vendor(
    vendor_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    vendor = get_scoped_or_404(db, Vendor, tenant_id, vendor_id)
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


@router.get("/customers", response_model=CustomerListEnvelope, response_model_exclude_unset=True)
def list_customers(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    tax_id: str | None = None,
    phone: str | None = None,
    customer_kind: str | None = None,
    customer_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Customer).where(Customer.tenant_id == tenant_id),
        filters={
            Customer.tax_id: tax_id,
            # the retail identity key, as tax_id is the B2B one — "这个手机号
            # 是不是老客户" is the question a counter agent actually asks
            Customer.phone: phone,
            Customer.customer_kind: customer_kind,
            Customer.customer_type: customer_type,
            Customer.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(Customer.name,),
        order_by=(Customer.created_at.desc(), Customer.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=CustomerRead,
    )


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
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(customer)
    commit_or_code_conflict(db, customer)
    db.refresh(customer)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.get("/customers/{customer_id}", response_model=CustomerEnvelope, response_model_exclude_unset=True)
def get_customer(
    customer_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


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


def _require_active_row(db: Session, tenant_id: str, model, row_id: str, noun: str):
    row = get_scoped_or_404(db, model, tenant_id, row_id)
    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{noun} {row_id} is archived — revive it (PATCH status active) first",
        )
    return row


@router.get("/facilities", response_model=FacilityListEnvelope, response_model_exclude_unset=True)
def list_facilities(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    facility_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return list_rows(
        db, select(Facility).where(Facility.tenant_id == tenant_id),
        filters={Facility.facility_type: facility_type, Facility.status: status_filter},
        keyword=keyword,
        keyword_columns=(Facility.name, Facility.facility_code, Facility.address),
        order_by=(Facility.name.asc(), Facility.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=FacilityRead,
    )


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"an active facility named {payload.name!r} already exists — the "
                "stock ledger joins on this name, so two live facilities cannot share it"
            ),
        )
    db.refresh(facility)
    return envelope(FacilityRead.model_validate(facility).model_dump(by_alias=True))


@router.get("/facilities/{facility_id}", response_model=FacilityEnvelope,
            response_model_exclude_unset=True)
def get_facility(
    facility_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    facility = get_scoped_or_404(db, Facility, tenant_id, facility_id)
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active facility with this name already exists",
        )
    db.refresh(facility)
    return envelope(FacilityRead.model_validate(facility).model_dump(by_alias=True))


@router.delete("/facilities/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(
    facility_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Facility, facility_id)


@router.get("/stores", response_model=StoreListEnvelope, response_model_exclude_unset=True)
def list_stores(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    channel: str | None = None,
    source: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return list_rows(
        db, select(Store).where(Store.tenant_id == tenant_id),
        filters={
            Store.channel: channel,
            Store.source: source.strip().lower() if source else None,
            Store.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(Store.name, Store.store_code, Store.address),
        order_by=(Store.name.asc(), Store.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=StoreRead,
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
    store = Store(
        tenant_id=tenant_id,
        store_code=payload.store_code,
        name=payload.name,
        channel=payload.channel,
        source=payload.source,
        address=payload.address,
        remarks=payload.remarks,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(store)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"an active store named {payload.name!r} already exists",
        )
    db.refresh(store)
    return envelope(StoreRead.model_validate(store).model_dump(by_alias=True))


@router.get("/stores/{store_id}", response_model=StoreEnvelope, response_model_exclude_unset=True)
def get_store(
    store_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    store = get_scoped_or_404(db, Store, tenant_id, store_id)
    data = StoreRead.model_validate(store).model_dump(by_alias=True)
    # the store's standing answer to "who ships for it", riding the read the
    # agent already makes — preferred first, unranked trailing
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
    return envelope(data)


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
    if "store_code" in updates:
        ensure_code_available(
            db, Store, actor.tenant_id, "store_code", updates["store_code"],
            exclude_id=store.id,
        )
    if "metadata" in updates:
        store.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(store, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active store with this name already exists",
        )
    db.refresh(store)
    return envelope(StoreRead.model_validate(store).model_dump(by_alias=True))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(
    store_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Store, store_id)


@router.get("/store-facilities", response_model=StoreFacilityListEnvelope,
            response_model_exclude_unset=True)
def list_store_facilities(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    store_id: str | None = None,
    facility_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return list_rows(
        db, select(StoreFacility).where(StoreFacility.tenant_id == tenant_id),
        filters={
            StoreFacility.store_id: store_id,
            StoreFacility.facility_id: facility_id,
            StoreFacility.status: status_filter,
        },
        # preferred shippers first; unranked trail in arrival order
        order_by=(
            StoreFacility.priority.asc().nulls_last(),
            StoreFacility.created_at.asc(),
            StoreFacility.id.asc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=StoreFacilityRead,
    )


@router.post("/store-facilities", response_model=StoreFacilityEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_store_facility(
    payload: CreateStoreFacilityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    _require_active_row(db, tenant_id, Store, payload.store_id, "store")
    _require_active_row(db, tenant_id, Facility, payload.facility_id, "facility")
    existing = db.scalar(
        select(StoreFacility).where(
            StoreFacility.tenant_id == tenant_id,
            StoreFacility.store_id == payload.store_id,
            StoreFacility.facility_id == payload.facility_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"link {existing.id} already exists for this (store, facility) — "
                "PATCH it; an archived link revives by setting status active"
            ),
        )
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a link for this (store, facility) already exists",
        )
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


def require_active_category(db: Session, tenant_id: str, category_id: str | None) -> None:
    """Products file onto ACTIVE shelves only; existing products on a shelf
    that later archives keep their pointer — history, not a cascade."""
    if category_id is None:
        return
    category = get_scoped_or_404(db, ProductCategory, tenant_id, category_id)
    if category.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"category {category_id} is archived — revive it or pick a "
                "live one; products already on it keep their pointer"
            ),
        )


@router.get("/product-categories", response_model=ProductCategoryListEnvelope,
            response_model_exclude_unset=True)
def list_product_categories(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    parent_id: str | None = None,
    root_only: bool = False,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 200,
):
    stmt = select(ProductCategory).where(ProductCategory.tenant_id == tenant_id)
    if root_only:
        stmt = stmt.where(ProductCategory.parent_id.is_(None))
    return list_rows(
        db, stmt,
        filters={
            ProductCategory.parent_id: parent_id,
            ProductCategory.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(ProductCategory.name, ProductCategory.category_code),
        order_by=(ProductCategory.name.asc(), ProductCategory.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=ProductCategoryRead,
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"an active category named {payload.name!r} already exists at "
                "this level — two live folders with one name is a filing "
                "error, not a second shelf"
            ),
        )
    db.refresh(category)
    return envelope(ProductCategoryRead.model_validate(category).model_dump(by_alias=True))


@router.get("/product-categories/{category_id}", response_model=ProductCategoryEnvelope,
            response_model_exclude_unset=True)
def get_product_category(
    category_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    category = get_scoped_or_404(db, ProductCategory, tenant_id, category_id)
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active category with this name already exists at the target level",
        )
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


@router.get("/products", response_model=ProductListEnvelope, response_model_exclude_unset=True)
def list_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    category_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Product).where(Product.tenant_id == tenant_id),
        filters={Product.status: status_filter, Product.category_id: category_id},
        keyword=keyword,
        # agents paste full codes ("E2E-20260801-001") into keyword — a
        # search that finds the product by name but not by its own code reads
        # as "the import failed" (observed in a live E2E run)
        keyword_columns=(Product.name, Product.product_code),
        order_by=(Product.created_at.desc(), Product.id.desc()),
        pagination=page_only_pagination(page, size),
        render=lambda products: product_reads_with_sku_stats(db, tenant_id, products),
    )


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
    require_active_category(db, actor.tenant_id, payload.category_id)
    product = Product(
        tenant_id=actor.tenant_id,
        product_code=payload.product_code,
        name=payload.name,
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


@router.get("/products/{product_id}", response_model=ProductEnvelope, response_model_exclude_unset=True)
def get_product(
    product_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return envelope(product_read_with_skus_flag(db, product))


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
        require_active_category(db, actor.tenant_id, updates["category_id"])
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


@router.get("/product-skus", response_model=ProductSkuListEnvelope, response_model_exclude_unset=True)
def list_product_skus(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_code: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(ProductSku).where(ProductSku.tenant_id == tenant_id),
        filters={
            ProductSku.product_id: product_id,
            ProductSku.sku_code: sku_code,
            ProductSku.status: status_filter,
        },
        order_by=(ProductSku.created_at.asc(), ProductSku.sku_code.asc(), ProductSku.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=ProductSkuRead,
    )


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


@router.get(
    "/product-skus/{sku_id}",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
)
def get_product_sku(
    sku_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
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


@router.get("/product-prices", response_model=ProductPriceListEnvelope, response_model_exclude_unset=True)
def list_product_prices(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_id: str | None = None,
    price_type: str | None = None,
    currency: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(ProductPrice).where(ProductPrice.tenant_id == tenant_id),
        filters={
            ProductPrice.product_id: product_id,
            ProductPrice.sku_id: sku_id,
            ProductPrice.price_type: price_type,
            ProductPrice.currency: currency,
            ProductPrice.status: status_filter,
        },
        # newest first: the live price and its history read top-down
        order_by=(ProductPrice.created_at.desc(), ProductPrice.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=ProductPriceRead,
    )


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active price for this (product, sku, type, currency) already exists",
        )
    db.refresh(row)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.get("/product-prices/{price_id}", response_model=ProductPriceEnvelope, response_model_exclude_unset=True)
def get_product_price(
    price_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, ProductPrice, tenant_id, price_id)
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active price for this (product, sku, type, currency) already exists",
        )
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


@router.get("/supplier-products", response_model=SupplierProductListEnvelope, response_model_exclude_unset=True)
def list_supplier_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    vendor_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(SupplierProduct).where(SupplierProduct.tenant_id == tenant_id),
        filters={
            SupplierProduct.product_id: product_id,
            SupplierProduct.vendor_id: vendor_id,
            SupplierProduct.status: status_filter,
        },
        # preferred sources first; unranked trail in arrival order
        order_by=(
            SupplierProduct.preference.asc().nulls_last(),
            SupplierProduct.created_at.asc(),
            SupplierProduct.id.asc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=SupplierProductRead,
    )


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
    existing = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.tenant_id == tenant_id,
            SupplierProduct.product_id == payload.product_id,
            SupplierProduct.vendor_id == payload.vendor_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"supplier link {existing.id} already exists for this (product, vendor) — "
                "PATCH it; an archived link revives by setting status active"
            ),
        )
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a supplier link for this (product, vendor) already exists",
        )
    db.refresh(link)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.get(
    "/supplier-products/{supplier_product_id}",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
)
def get_supplier_product(
    supplier_product_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, SupplierProduct, tenant_id, supplier_product_id)
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


@router.get("/customer-products", response_model=CustomerProductListEnvelope, response_model_exclude_unset=True)
def list_customer_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    customer_id: str | None = None,
    # the reverse lookup this table exists for: the customer's PO says
    # "货号 KH-3301" and the agent needs to know which product that is
    customer_product_code: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(CustomerProduct).where(CustomerProduct.tenant_id == tenant_id),
        filters={
            CustomerProduct.product_id: product_id,
            CustomerProduct.customer_id: customer_id,
            CustomerProduct.customer_product_code: customer_product_code,
            CustomerProduct.status: status_filter,
        },
        order_by=(CustomerProduct.created_at.asc(), CustomerProduct.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=CustomerProductRead,
    )


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
    existing = db.scalar(
        select(CustomerProduct).where(
            CustomerProduct.tenant_id == tenant_id,
            CustomerProduct.product_id == payload.product_id,
            CustomerProduct.customer_id == payload.customer_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"agreement {existing.id} already exists for this (product, customer) — "
                "PATCH it; an archived agreement revives by setting status active"
            ),
        )
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an agreement for this (product, customer) already exists",
        )
    db.refresh(agreement)
    return envelope(CustomerProductRead.model_validate(agreement).model_dump(by_alias=True))


@router.get(
    "/customer-products/{customer_product_id}",
    response_model=CustomerProductEnvelope,
    response_model_exclude_unset=True,
)
def get_customer_product(
    customer_product_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    agreement = get_scoped_or_404(db, CustomerProduct, tenant_id, customer_product_id)
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


def _demote_current_primary(db: Session, tenant_id: str, customer_id: str) -> None:
    """Setting a new primary DEMOTES the old one in the same write — the
    rolodex semantic: "the" contact is one question with one answer, and
    making callers un-set the old primary first would turn every change into
    a two-step dance that half the time stops after step one. The partial
    unique index stays as the backstop for the race this cannot see."""
    db.execute(
        update(CustomerContact)
        .where(
            CustomerContact.tenant_id == tenant_id,
            CustomerContact.customer_id == customer_id,
            CustomerContact.is_primary.is_(True),
        )
        .values(is_primary=False)
        .execution_options(synchronize_session=False)
    )


@router.get("/customer-contacts", response_model=CustomerContactListEnvelope,
            response_model_exclude_unset=True)
def list_customer_contacts(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    customer_id: str | None = None,
    phone: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(CustomerContact).where(CustomerContact.tenant_id == tenant_id),
        filters={
            CustomerContact.customer_id: customer_id,
            CustomerContact.phone: phone,
            CustomerContact.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            CustomerContact.name, CustomerContact.title,
            CustomerContact.wechat, CustomerContact.email,
        ),
        # the primary first, then the rest by arrival — the order a person
        # answering "找谁" actually wants
        order_by=(
            CustomerContact.is_primary.desc(),
            CustomerContact.created_at.asc(),
            CustomerContact.id.asc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=CustomerContactRead,
    )


@router.post("/customer-contacts", response_model=CustomerContactEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_customer_contact(
    payload: CreateCustomerContactRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
    if payload.is_primary:
        _demote_current_primary(db, tenant_id, payload.customer_id)
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "an active contact with this phone already exists at this "
                "customer — the same number twice is a duplicate person; "
                "PATCH that row, or archive it first"
            ),
        )
    db.refresh(contact)
    return envelope(CustomerContactRead.model_validate(contact).model_dump(by_alias=True))


@router.get("/customer-contacts/{contact_id}", response_model=CustomerContactEnvelope,
            response_model_exclude_unset=True)
def get_customer_contact(
    contact_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    contact = get_scoped_or_404(db, CustomerContact, tenant_id, contact_id)
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
        _demote_current_primary(db, actor.tenant_id, contact.customer_id)
    if "metadata" in updates:
        contact.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(contact, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active contact with this phone already exists at this customer",
        )
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
    external_sku_id: str | None = None,
    product_id: str | None = None,
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
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    stmt = select(ExternalProductMap).where(ExternalProductMap.tenant_id == tenant_id)
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
            ExternalProductMap.external_sku_id: (
                external_sku_id.strip() if external_sku_id is not None else None
            ),
            ExternalProductMap.product_id: product_id,
            ExternalProductMap.status: status_filter,
        },
        order_by=(
            ExternalProductMap.source.asc(),
            ExternalProductMap.external_product_id.asc(),
            ExternalProductMap.created_at.asc(),
            ExternalProductMap.id.asc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=ExternalProductMapRead,
    )


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
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
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
    if payload.status == "active" and payload.effective_to is None:
        existing = db.scalar(
            select(ExternalProductMap).where(
                ExternalProductMap.tenant_id == tenant_id,
                ExternalProductMap.source == payload.source,
                ExternalProductMap.external_product_id == payload.external_product_id,
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
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        quantity=payload.quantity,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an open-ended map for this (source, external listing, product) already exists",
        )
    db.refresh(row)
    return envelope(ExternalProductMapRead.model_validate(row).model_dump(by_alias=True))


@router.get(
    "/external-product-maps/{map_id}",
    response_model=ExternalProductMapEnvelope,
    response_model_exclude_unset=True,
)
def get_external_product_map(
    map_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, ExternalProductMap, tenant_id, map_id)
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
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, ExternalProductMap, actor.tenant_id, map_id)
    updates = payload.model_dump(exclude_unset=True)
    if "sku_id" in updates and updates["sku_id"] is not None:
        sku = get_scoped_or_404(db, ProductSku, actor.tenant_id, updates["sku_id"])
        if sku.product_id != row.product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"sku {updates['sku_id']} belongs to product {sku.product_id}, not {row.product_id}",
            )
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "reopening this pairing collides with an open-ended map for the "
                "same (source, external listing, product) — close that one first"
            ),
        )
    db.refresh(row)
    return envelope(ExternalProductMapRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/external-product-maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_external_product_map(
    map_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ExternalProductMap, map_id)


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


@router.get("/inventory-items", response_model=InventoryItemListEnvelope, response_model_exclude_unset=True)
def list_inventory_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_id: str | None = None,
    facility: str | None = None,
    lot_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    stmt = select(InventoryItem).where(InventoryItem.tenant_id == tenant_id)
    # "" is a real position ("" is the default lot, and a facility may be
    # unnamed), so these two filter on presence, not truthiness
    if facility is not None:
        stmt = stmt.where(InventoryItem.facility == facility)
    if lot_id is not None:
        stmt = stmt.where(InventoryItem.lot_id == lot_id)
    return list_rows(
        db, stmt,
        filters={
            InventoryItem.product_id: product_id,
            InventoryItem.sku_id: sku_id,
            InventoryItem.status: status_filter,
        },
        order_by=(InventoryItem.created_at.desc(), InventoryItem.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=InventoryItemRead,
    )


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


@router.get("/inventory-items/{item_id}", response_model=InventoryItemEnvelope, response_model_exclude_unset=True)
def get_inventory_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, InventoryItem, tenant_id, item_id)
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
    for field, value in updates.items():
        setattr(item, field, value.strip() if field in ("facility", "lot_id") else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an inventory item for this (product, sku, facility, lot) already exists",
        )
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
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(InventoryItemDetail).where(InventoryItemDetail.tenant_id == tenant_id),
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
        pagination=page_only_pagination(page, size),
        read_model=InventoryItemDetailRead,
    )


@router.post(
    "/inventory-item-details",
    response_model=InventoryItemDetailEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item_detail(
    payload: CreateInventoryItemDetailRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Append one movement. Details are immutable — there is no PATCH or
    DELETE; a mistake is corrected by a counter-entry. The item's totals move
    here and only here."""
    require_inventory_manage(actor)
    item = get_scoped_or_404(db, InventoryItem, actor.tenant_id, payload.inventory_item_id)
    if item.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="inventory item is archived — set it active before posting movement",
        )
    # `entity_id` promises resolvability — it is uuid-typed, and before this
    # check a Tmall order number here was a 500 from the ValueError inside the
    # column type, not an answer. The refusal has to name where the reference
    # DOES go, because the caller's need is real; only the column is wrong.
    if payload.entity_id is not None:
        try:
            uuid.UUID(payload.entity_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"entity_id must be the uuid of a record in this system — "
                    f"{payload.entity_id!r} is not one. An external order "
                    "(Tmall, JD, another system) goes in `custom_fields`, e.g. "
                    '{"source": "tmall", "order_no": "..."}'
                ),
            )
    # A movement fulfils at most one of OUR orders. Two at once is not a
    # transfer — it is two movements — and an external order (Tmall, JD) is
    # neither: its number is not a uuid this database can vouch for, so it
    # belongs in `custom_fields`, not in a column that promises resolvability.
    if payload.sales_order_id and payload.purchase_order_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a movement fulfils at most one order — record two movements if "
                "stock genuinely moved twice"
            ),
        )
    if payload.sales_order_id:
        get_scoped_or_404(db, SalesOrder, actor.tenant_id, payload.sales_order_id)
    if payload.purchase_order_id:
        get_scoped_or_404(db, PurchaseOrder, actor.tenant_id, payload.purchase_order_id)
    if payload.reason in ("reserved", "reservation_released"):
        # the reservation pair moves AVAILABILITY only: goods held for an
        # order have not moved, they have stopped being promisable. And a
        # hold must say whose it is, or nothing can ever consume it.
        atp = payload.available_to_promise_diff
        wrong_shape = (
            payload.quantity_on_hand_diff != 0
            or atp is None
            or (payload.reason == "reserved" and atp >= 0)
            or (payload.reason == "reservation_released" and atp <= 0)
        )
        if wrong_shape or not payload.sales_order_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "a reservation row moves availability only: quantity_on_hand_diff 0, "
                    "available_to_promise_diff negative for `reserved` (占货) and positive "
                    "for `reservation_released`, and sales_order_id naming whose goods "
                    "are held — goods that actually moved are `issued`/`received`"
                ),
            )
    detail = post_inventory_detail(
        db,
        item=item,
        quantity_on_hand_diff=payload.quantity_on_hand_diff,
        available_to_promise_diff=payload.available_to_promise_diff,
        reason=payload.reason,
        description=payload.description,
        sales_order_id=payload.sales_order_id,
        purchase_order_id=payload.purchase_order_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        unit_cost=payload.unit_cost,
        custom_fields=payload.custom_fields,
        effective_at=payload.effective_at,
        created_by=attributed(actor, payload.created_by),
    )
    db.commit()
    db.refresh(detail)
    return envelope(InventoryItemDetailRead.model_validate(detail).model_dump(by_alias=True))


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
