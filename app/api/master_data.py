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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
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
from app.api.deps import Actor, attributed, get_actor
from app.db.session import get_db
from app.models import (
    Customer,
    InventoryItem,
    InventoryItemDetail,
    Product,
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
    CreateProductRequest,
    CreateProductSkuRequest,
    CreateSupplierProductRequest,
    CreateVendorRequest,
    CustomerEnvelope,
    CustomerListEnvelope,
    CustomerRead,
    InventoryItemDetailEnvelope,
    InventoryItemDetailListEnvelope,
    InventoryItemDetailRead,
    InventoryItemEnvelope,
    InventoryItemListEnvelope,
    InventoryItemRead,
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
    UpdateCustomerRequest,
    UpdateInventoryItemRequest,
    UpdateProductPriceRequest,
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


# --- products, their SKUs, and the bulk upserts beside them ----------------


@router.get("/products", response_model=ProductListEnvelope, response_model_exclude_unset=True)
def list_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Product).where(Product.tenant_id == tenant_id),
        filters={Product.status: status_filter},
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
    product = Product(
        tenant_id=actor.tenant_id,
        product_code=payload.product_code,
        name=payload.name,
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


# --- inventory: items are running sums of an append-only detail ledger -----


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
    require_master_data_manage(actor)
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
    require_master_data_manage(actor)
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
    return archive_row(db, actor, InventoryItem, item_id)


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
    require_master_data_manage(actor)
    item = get_scoped_or_404(db, InventoryItem, actor.tenant_id, payload.inventory_item_id)
    if item.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="inventory item is archived — set it active before posting movement",
        )
    detail = post_inventory_detail(
        db,
        item=item,
        quantity_on_hand_diff=payload.quantity_on_hand_diff,
        available_to_promise_diff=payload.available_to_promise_diff,
        reason=payload.reason,
        description=payload.description,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        unit_cost=payload.unit_cost,
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
    require_master_data_manage(actor)
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
