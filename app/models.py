from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.table_constraints import apply_table_constraints
from app.core.entity_types import (
    APPROVAL_ENTITY_TYPES,
    DECIDED_APPROVAL_ACTIONS,
    TODO_ENTITY_TYPES,
    TODO_STATUSES,
)
from app.core.permissions import PRINCIPAL_TENANT_SERVICE
from app.db.session import Base


JsonType = JSON().with_variant(JSONB, "postgresql")


def new_id() -> str:
    return str(uuid4())


def generate_api_key() -> str:
    return f"calw_{secrets.token_urlsafe(24)}"


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IdMixin:
    """The uuid primary key every record shares."""

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=new_id, sort_order=-100
    )


class TenantMixin:
    """Row-level tenancy: every scoped table carries and indexes tenant_id."""

    tenant_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True, sort_order=-90)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=90
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        sort_order=91,
    )


class TenantRecord(IdMixin, TenantMixin, TimestampMixin):
    """id + tenant_id + created_at/updated_at — the spine of nearly every
    tenant-scoped table. sort_order pins the conventional layout (ids first,
    timestamps last) however the mixins compose."""


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, sort_order=92
    )


class SoftDeleteAttributionMixin(SoftDeleteMixin):
    """Soft delete plus who/why — the personal-document families record both."""

    deleted_by: Mapped[str | None] = mapped_column(String(100), nullable=True, sort_order=93)
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True, sort_order=94)


class MetadataJsonbMixin:
    metadata_jsonb: Mapped[dict] = mapped_column("metadata_jsonb", JsonType, default=dict, sort_order=80)


class CustomFieldsJsonbMixin:
    custom_fields_jsonb: Mapped[dict] = mapped_column(
        "custom_fields_jsonb", JsonType, default=dict, sort_order=80
    )


class Employee(TenantRecord, MetadataJsonbMixin, Base):
    __tablename__ = "employees"

    employee_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # When this person's employment started. A real column rather than a custom
    # field because it is universal to employment and because a computation
    # depends on it: 年假 entitlement is a function of 工龄, and an agent that
    # has to guess the start date cannot answer "how many days do I have" at
    # all. Nullable — an imported roster may not carry it, and a null is an
    # honest "nobody said", which an agent can ask about.
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    timesheet_headers: Mapped[list["TimesheetHeader"]] = relationship(back_populates="employee")


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    email_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # The tenant's namespace on an employee's laptop: every skill bundle installs
    # into `{skill_brand}-skills-<slug>/` and every skill in it is named
    # `{skill_brand}-<slug>-…` (brand default "oryh", per-environment via
    # ORYH_SKILL_BRAND), so someone who works for two companies — or one
    # company's test and prod servers — can hold the bundles side by side.
    # Derived once from email_domain at creation (see services/tenants.py) and
    # then IMMUTABLE — it is a directory name on machines we do not control.
    slug: Mapped[str | None] = mapped_column(String(24), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="tenant")


class ApiKey(IdMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # NULL user_id means a tenant-level service key; otherwise the key acts as
    # that user's agent credential and inherits the user's role.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="service")
    # Whose machine holds a tenant-level key: `tenant_service` (the tenant's
    # own, permission-bypassing automation credential) or `hosted_flow_agent`
    # (issued by the platform, held by ORYH, permission-checked). Meaningless
    # on user-bound keys. Platform-set only — never accepted from a tenant
    # request, so the badge it drives cannot be forged. See core/permissions.py.
    principal_kind: Mapped[str] = mapped_column(
        String(30), default=PRINCIPAL_TENANT_SERVICE, server_default=PRINCIPAL_TENANT_SERVICE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("employees.id"), unique=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)

    employee: Mapped[Employee | None] = relationship()

    @property
    def invitation_pending(self) -> bool:
        """The account has no usable login credential yet."""
        return (
            self.email_verified_at is None
            and self.password_hash is None
            and self.oidc_subject is None
        )


class UserSession(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


class DeviceAuthorization(IdMixin, CreatedAtMixin, Base):
    """Pre-auth handshake for a local agent connecting via the browser device
    flow (RFC 8628 style): the agent holds the device_code, the person types
    the short user_code into the web console after signing in. No tenant is
    known before approval, so the table carries no tenant RLS; the plaintext
    key is held only between approval and the agent's next poll."""

    __tablename__ = "device_authorizations"

    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_code: Mapped[str] = mapped_column(String(16), index=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/denied/consumed
    tenant_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    api_key_plaintext: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(TenantRecord, MetadataJsonbMixin, Base):
    __tablename__ = "projects"
    # The baseline migration has enforced this on postgres since day one
    # (projects_tenant_project_code_uk); the model never declared it, so the
    # sqlite test schema was built without it — which is why a duplicate
    # project_code could 500 in production while every test stayed green.
    # Name kept in the migration's spelling so autogenerate stays quiet.
    __table_args__ = (
        Index(
            "projects_tenant_project_code_uk",
            "tenant_id", "project_code",
            unique=True,
            postgresql_where=text("project_code IS NOT NULL"),
            sqlite_where=text("project_code IS NOT NULL"),
        ),
    )

    project_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_name: Mapped[str] = mapped_column(String(200))
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Vendor(TenantRecord, MetadataJsonbMixin, Base):
    """Supplier/vendor master data. Referenced by expense items (and future
    payables); the receipt's 销售方名称/税号 is the agent's matching key."""

    __tablename__ = "vendors"
    # Upsert key for bulk import; partial for the same reason as products.
    __table_args__ = (
        Index(
            "vendors_tenant_code_uq",
            "tenant_id", "vendor_code",
            unique=True,
            postgresql_where=text("vendor_code IS NOT NULL"),
            sqlite_where=text("vendor_code IS NOT NULL"),
        ),
    )

    vendor_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    # 统一社会信用代码 / 纳税人识别号 — exact-match key against invoice seller
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class Customer(TenantRecord, MetadataJsonbMixin, Base):
    """Customer/account master data — 零售 and B2B on ONE table.

    A 会员 and a 集团客户 differ in what their file holds, not in what happens
    to them: both quote, order, get invoiced, pay and may run a standing
    balance, and every one of those mechanics is identical. That is the test
    `Invoice` passes and the orders fail — the orders split because
    counterparty, direction and closure all differ. Splitting customers would
    duplicate the settlement half and, worse, take the counterparty count on
    payments, invoices and billing accounts from three to four, which is how a
    full OFBiz Party layer arrives by the back door without anyone deciding to
    build one.

    So the difference rides two columns on two different axes.

    `customer_kind` is the CLOSED one: a natural person or an organization.
    It is OFBiz's Person/PartyGroup distinction with the Party table not built,
    and it is a constrained column rather than vocabulary because the
    distinction is universal, not the tenant's to extend — no workspace should
    be able to add a third kind or archive one of the two. That closure is what
    keeps it usable by a constraint later (a phone unique per person is the
    obvious candidate; nothing branches on it today), and it is the
    discriminator a Party layer would need, unchanged, if one is ever built.
    Null is the honest default: nobody said, and 个体工商户 is genuinely both.

    `customer_type` is the OPEN one: 零售/批发/经销/电商/政企, the tenant's own
    segmentation of its book, so it is a type option like every other *_type.

    Neither gates anything. What a 经销商 may be sold at, whether a member
    prepays, who gets 账期 — those are judgments, and judgments live in agents
    and workflow definitions.

    Unlike vendors, tax_id is often unknown at quoting time (prospects), so the
    free-text snapshot on the quotation stands alone until the customer is
    promoted into master data — and for a retail person there may never be one.
    """

    __tablename__ = "customers"
    __table_args__ = (
        # Upsert key for bulk import; partial for the same reason as products.
        Index(
            "customers_tenant_code_uq",
            "tenant_id", "customer_code",
            unique=True,
            postgresql_where=text("customer_code IS NOT NULL"),
            sqlite_where=text("customer_code IS NOT NULL"),
        ),
        # The retail lookup is by phone, and the retail case is the one where
        # this table gets long. Deliberately NOT unique: a shared household
        # number is an ordinary fact, and a duplicate member record costs a
        # merge rather than money — the bar every constraint here has to clear.
        Index("customers_tenant_phone_idx", "tenant_id", "phone"),
        CheckConstraint(
            "customer_kind is null or customer_kind in ('person', 'company')",
            name="customers_kind_ck",
        ),
    )

    customer_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    # 'person' = 自然人 (零售/会员), 'company' = 组织 (企业/机构/政府). Null is not
    # a third kind — it is nobody having stated one.
    customer_kind: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # 零售 / 批发 / 经销 / 电商 / 政企 … — tenant vocabulary (customer_type family)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 统一社会信用代码 / 纳税人识别号 — filled in before invoicing, optional while quoting
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # quotes/deliveries need it on the printed document — first-class, unlike vendors
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class Product(TenantRecord, MetadataJsonbMixin, Base):
    """Product/goods master data. Referenced by purchase-request items; a
    requisition line may also carry free text only when the item isn't in
    the catalog yet."""

    __tablename__ = "products"
    # The code is the tenant's own identity for a product, and the key a bulk
    # import upserts on — unique so re-running an import updates rather than
    # duplicates. Partial, because a product may still be created by hand
    # without one; only a stated code has to be unique. Archived rows keep
    # their code deliberately: re-importing it revives that product instead of
    # silently creating a second one alongside the archived original.
    __table_args__ = (
        Index(
            "products_tenant_code_uq",
            "tenant_id", "product_code",
            unique=True,
            postgresql_where=text("product_code IS NOT NULL"),
            sqlite_where=text("product_code IS NOT NULL"),
        ),
    )

    product_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # reference price for the agent's deviation check, not a hard limit
    list_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="active")


class ProductSku(TenantRecord, MetadataJsonbMixin, Base):
    """Transaction-granularity variant of a product (e.g. 款色 → 尺码).
    Companies whose product IS the sku simply never create rows here.
    variant_attrs is free-form JSONB — the agent, not a schema, interprets
    what the dimensions mean per industry."""

    __tablename__ = "product_skus"

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variant_attrs: Mapped[dict] = mapped_column("variant_attrs", JsonType, default=dict)
    # overrides the product-level reference price when set
    list_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    product: Mapped[Product] = relationship()


class ProductPrice(TenantRecord, MetadataJsonbMixin, Base):
    """One price fact of one type for a product (or one of its SKUs) — the
    price book beside the product's own list_price reference column. History
    is status, not date ranges: superseding a price archives the old row and
    creates a new active one, so the invariant is one LIVE price per
    (product-or-sku, price_type, currency) and archived rows are the paper
    trail. Modeled on OFBiz ProductPrice with the store/date-range/price-calc
    machinery removed; the tax flags stay because 含税/不含税 is the first
    question every Chinese price column raises."""

    __tablename__ = "product_prices"
    # one ACTIVE price per key; archiving frees the slot and keeps history
    __table_args__ = (
        Index(
            "product_prices_active_product_uq",
            "tenant_id", "product_id", "price_type", "currency",
            unique=True,
            postgresql_where=text("status = 'active' AND sku_id IS NULL"),
            sqlite_where=text("status = 'active' AND sku_id IS NULL"),
        ),
        Index(
            "product_prices_active_sku_uq",
            "tenant_id", "sku_id", "price_type", "currency",
            unique=True,
            postgresql_where=text("status = 'active' AND sku_id IS NOT NULL"),
            sqlite_where=text("status = 'active' AND sku_id IS NOT NULL"),
        ),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    # prices a specific variant when set; product-level otherwise
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    # list/default/promo/wholesale/competitive/minimum/maximum/cost
    price_type: Mapped[str] = mapped_column(String(20))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    # 含税与否 — the fact as the person stated it, never derived
    tax_in_price: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    product: Mapped[Product] = relationship()
    sku: Mapped[ProductSku | None] = relationship()


class SupplierProduct(TenantRecord, MetadataJsonbMixin, Base):
    """A vendor's supply relationship for a product: their own code and name
    for it, the last agreed price, lead time and order rules. One row per
    (product, vendor) — status archives a lapsed source, and re-importing the
    pair revives it. last_price updates in place (it means "most recent");
    price HISTORY belongs to ProductPrice. Modeled on OFBiz SupplierProduct
    minus agreements, date ranges and drop-ship."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "product_id", "vendor_id",
            name="supplier_products_tenant_product_vendor_uk",
        ),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    # the SUPPLIER's own code/name for this product — the join key against
    # their price lists and order confirmations
    supplier_product_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supplier_product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Numeric, not int: bulk goods order in kg/m as naturally as in units
    min_order_quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    order_increment: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # rank across a product's sources; lower is preferred, null is unranked
    preference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    product: Mapped[Product] = relationship()
    vendor: Mapped[Vendor] = relationship()

    @property
    def vendor_name(self) -> str | None:
        """Denormalized for reads: supplier comparison is the point of this
        table, and an agent should not need a second query per row to say
        which vendor a source is."""
        return self.vendor.name if self.vendor is not None else None


class InventoryItem(TenantRecord, MetadataJsonbMixin, Base):
    """One stock position: a product (or one of its SKUs) at a facility, in a
    lot. Modeled on OFBiz InventoryItem, minus serialized items, owner
    parties and accounting quantities.

    The quantities are DERIVED: nothing may write quantity_on_hand or
    available_to_promise directly — every movement is an InventoryItemDetail,
    and the totals move only through post_inventory_detail(). That is what
    makes the ledger the truth and the item row a running sum of it.

    facility and lot_id are NOT NULL with '' meaning "unspecified", so the
    identity tuple (product-or-sku, facility, lot) is enforceable with the
    same partial-unique-index pattern the price book uses."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        Index(
            "inventory_items_product_tuple_uq",
            "tenant_id", "product_id", "facility", "lot_id",
            unique=True,
            postgresql_where=text("sku_id IS NULL"),
            sqlite_where=text("sku_id IS NULL"),
        ),
        Index(
            "inventory_items_sku_tuple_uq",
            "tenant_id", "sku_id", "facility", "lot_id",
            unique=True,
            postgresql_where=text("sku_id IS NOT NULL"),
            sqlite_where=text("sku_id IS NOT NULL"),
        ),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    # 仓库 and 库位/批号 as the person names them — free text, '' = unspecified
    facility: Mapped[str] = mapped_column(String(100), default="")
    lot_id: Mapped[str] = mapped_column(String(64), default="")
    bin_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # derived sums of the detail ledger — see class docstring
    quantity_on_hand: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    available_to_promise: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="active")

    product: Mapped[Product] = relationship()
    sku: Mapped[ProductSku | None] = relationship()

    @property
    def product_code(self) -> str | None:
        """Denormalized for reads: stock answers are given in the tenant's own
        codes, not in uuids."""
        return self.product.product_code if self.product is not None else None


class InventoryItemDetail(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """One movement of one inventory item — the append-only ledger the item's
    totals are a sum of. Modeled on OFBiz InventoryItemDetail; the many
    per-source id columns collapse into the generic (entity_type, entity_id)
    pair the rest of this codebase already uses for cross-references.

    Rows are immutable: there is no update or delete, a mistake is corrected
    by a counter-entry. `reason` says why stock moved — `import_override` is
    reserved for a bulk import finding the system count different from the
    imported count and recording the difference as a movement rather than
    editing the item."""

    __tablename__ = "inventory_item_details"

    inventory_item_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity_on_hand_diff: Mapped[float] = mapped_column(Numeric(12, 2))
    available_to_promise_diff: Mapped[float] = mapped_column(Numeric(12, 2))
    # initial / import_initial / import_override / received / issued /
    # adjustment / damaged / returned / transfer / other
    reason: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # what caused the movement, when it is a record in the system
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    item: Mapped[InventoryItem] = relationship()


class Resource(TenantRecord, MetadataJsonbMixin, Base):
    __tablename__ = "resources"

    resource_type: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    booking_mode: Mapped[str] = mapped_column(String(20), default="exclusive")
    max_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class ObjectTypeDefinition(TenantRecord, Base):
    """Per-tenant type registry: payload shape (json_schema) and lifecycle
    (state_machine) for both custom business object types and builtin
    entities such as timesheet_header."""

    __tablename__ = "object_type_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "entity_kind", "object_type",
            name="object_type_definitions_tenant_kind_type_uk",
        ),
    )

    entity_kind: Mapped[str] = mapped_column(String(20), default="business_object")
    object_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_schema: Mapped[dict] = mapped_column("json_schema", JsonType, default=dict)
    state_machine: Mapped[dict | None] = mapped_column("state_machine", JsonType, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class TypeOption(TenantRecord, Base):
    """Tenant-visible type vocabulary (price types, adjustment types, expense
    categories, work types — OFBiz-style *_TYPE tables, one table for all
    families). kind=system rows mirror the shipped catalog and get their
    titles/descriptions refreshed on deploy; kind=custom rows are
    tenant-defined. Archiving (either kind) removes a value from what new
    records may use — history keeps whatever it already says. A tenant with
    no rows at all for a family simply has not customized it: the shipped
    catalog applies verbatim."""

    __tablename__ = "type_options"
    __table_args__ = (
        UniqueConstraint("tenant_id", "family", "name", name="type_options_tenant_family_name_uk"),
    )

    # product_price_type / sales_adjustment_type / expense_category / work_type
    family: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20), default="custom")
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which way a value of this kind moves money: +1 adds, -1 deducts, null
    # says nothing. Only families where the sign IS the meaning use it — a
    # payslip's 个税 line recorded as +2000 rather than -2000 pays the person
    # 4000 too much, so the vocabulary declares the direction and the write
    # path checks it. A tenant adding its own deduction type declares its own.
    sign: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Capability(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """Tenant-visible capability catalog. kind=system rows mirror the
    product's enforcement points and are synced on deploy; kind=custom rows
    are tenant-defined and enforce at the skill-distribution and
    flow-routing layers, never the core API."""

    __tablename__ = "capabilities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="capabilities_tenant_name_uk"),
    )

    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="custom")
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Role(TenantRecord, Base):
    """Named bundle of permission grants. System roles (admin/member) are
    seeded per tenant with behavior-preserving defaults; tenants add custom
    roles (approver, finance, 服务商 …) and tune grants."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="roles_tenant_name_uk"),
    )

    name: Mapped[str] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions_jsonb: Mapped[list] = mapped_column("permissions_jsonb", JsonType, default=list)
    # What our shipped defaults last gave this role, recorded at the moment we
    # gave it. Same device as `TenantSkill.catalog_required_capability`, and it
    # answers the question that made new capabilities unreachable for years:
    # a capability absent from `member` is either one we shipped after this
    # workspace was created, or one the workspace removed on purpose, and
    # `permissions_jsonb` alone cannot tell those apart. With a record of what
    # we gave, it can — absent from both means never offered, so grant it;
    # present here and absent there means removed, so leave it removed.
    #
    # NULL means we have no record: roles a tenant invented (we ship no
    # defaults for them and never will), and any role predating the column.
    # A NULL baseline grants nothing — it is filled in on the next sync so the
    # comparison starts working from then on, rather than guessing backwards.
    catalog_permissions_jsonb: Mapped[list | None] = mapped_column(
        "catalog_permissions_jsonb", JsonType, nullable=True, default=None
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class TenantSkill(TenantRecord, Base):
    """Tenant-authored agent skill: the process contract a tenant's agents
    load to run a customer-specific workflow. Stored as data so tenants can
    define workflows without touching the shared codebase."""

    __tablename__ = "tenant_skills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="tenant_skills_tenant_name_uk"),
    )

    name: Mapped[str] = mapped_column(String(100))
    # "product" skills are provisioned from the shipped skills/ catalog and
    # refreshed on deploy; "custom" skills are tenant-authored.
    kind: Mapped[str] = mapped_column(String(20), default="custom")
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # capability gate for skill-bundle distribution: only users whose role
    # covers this capability receive the skill; null = everyone
    required_capability: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # what the shipped catalog last said required_capability is (product
    # skills only; null on custom). The catalog sync compares against this to
    # tell a tenant's re-gate from an untouched default: equal → keep tracking
    # the catalog, different → the tenant owns the gate, leave it alone.
    catalog_required_capability: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # "capability" (default) = whoever passes required_capability;
    # "targeted" = only the audience in tenant_skill_assignments, and an empty
    # audience means nobody. Explicit rather than inferred from row count, so
    # emptying the audience narrows rather than silently re-broadcasting.
    distribution_mode: Mapped[str] = mapped_column(String(20), default="capability")
    # {relative_path: content}; must contain "SKILL.md"
    files_jsonb: Mapped[dict] = mapped_column("files_jsonb", JsonType, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class TenantSkillAssignment(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """Who a skill is for — the audience axis, beside required_capability's
    "what you must be allowed to do".

    The two compose as AND, never OR: a skill in someone's bundle tells their
    agent it may do the thing, so shipping one past the capability gate would
    only produce an agent that 403s on every call. Audience narrows; it never
    grants.
    """

    __tablename__ = "tenant_skill_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "skill_id", "subject_type", "subject_id",
            name="tenant_skill_assignments_uk",
        ),
    )

    skill_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("tenant_skills.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(20))
    # a users.id when subject_type="user"; a role NAME when "role" — roles are
    # referred to by name in User.role and in permission grants alike
    subject_id: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class WorkflowDefinition(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """Tenant-authored workflow definition in natural language — the map the
    admin/flow agent reads to decide the next node after each submission or
    approval. Versions are append-only and immutable: publishing a new
    version supersedes the previous one; history stays queryable so any past
    routing decision can be traced to the definition it was based on."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "entity_kind", "object_type", "name", "version",
            name="workflow_definitions_version_uk",
        ),
    )

    entity_kind: Mapped[str] = mapped_column(String(20), default="business_object")
    object_type: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), default="default")
    version: Mapped[int] = mapped_column(Integer, default=1)
    definition_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Policy(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    """A published rule of the house — 员工手册, 报销制度, 薪酬管理办法, and the
    external standards a workspace has to record because somebody's pay depends
    on them.

    OFBiz models this as `Content` + `DataResource` + `ContentRevision` +
    `ContentApproval`: a general CMS where reading one paragraph costs four
    joins and brings `decoratorContentId` and `childLeafCount` along with it.
    The shape worth keeping is smaller — a versioned document with a publisher,
    an effective range and a visibility (`DataResource.isPublic` is exactly the
    "是否公开" field, only boolean where an HR policy needs three values).

    This is NOT `workflow_definitions`. That says how a KIND OF DOCUMENT routes
    and is keyed to an object type; this says what the company's rules ARE and
    is keyed to nothing. Both are versioned tenant text read by agents; merging
    them would put "谁审批报销" and "报销标准是多少" in one table on the strength
    of both being prose.

    **Status is a marker; the dates are the truth.** `published` means "this is
    the current version of this code", and the partial unique index holds that.
    What actually applied in March is answered by `effective_from`/`_thru`
    across every non-draft version — the same stance settlement takes, where
    `paid` is a flow marker and `outstanding_amount` is the fact.
    """

    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="policies_version_uk"),
        CheckConstraint(
            "visibility in ('internal', 'restricted', 'public')",
            name="policies_visibility_ck",
        ),
        CheckConstraint(
            "status in ('draft', 'published', 'superseded', 'repealed')",
            name="policies_status_ck",
        ),
        # a restricted policy that names no capability is readable by everyone,
        # which is the opposite of what it says
        CheckConstraint(
            "visibility <> 'restricted' or required_capability is not null",
            name="policies_restricted_needs_capability_ck",
        ),
        # who published it and when is the whole point of publishing it
        CheckConstraint(
            "status <> 'published' or (published_at is not null and published_by is not null)",
            name="policies_published_attribution_ck",
        ),
        CheckConstraint(
            "effective_thru is null or effective_from is null "
            "or effective_thru >= effective_from",
            name="policies_effective_period_ck",
        ),
        Index("policies_code_idx", "tenant_id", "code", "version"),
        Index("policies_category_idx", "tenant_id", "category", "status"),
        # one live version per 制度编号 — two documents both claiming to be the
        # current 报销制度 is the failure this table exists to prevent
        Index(
            "policies_current_version_uk",
            "tenant_id", "code",
            unique=True,
            postgresql_where=text("status = 'published' AND deleted_at IS NULL"),
            sqlite_where=text("status = 'published' AND deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Markdown, and the server never parses it — the same standing a workflow
    # definition has
    body: Mapped[str] = mapped_column(Text)
    # The same rules again in whatever structure the workspace finds useful, for
    # an agent that would rather read a figure than a paragraph. Optional, free
    # in shape, and **never interpreted by the server** — it has no more standing
    # here than `body` does. It lives on the policy row rather than in a table of
    # its own for a reason worth keeping: a separate table would be a second
    # source of truth for the same rules, drifting from the prose with nothing
    # to notice. Here it versions, publishes and freezes with the document it
    # restates, because it IS the document.
    rules_json: Mapped[dict | None] = mapped_column("rules_json", JsonType, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="internal")
    # only consulted when visibility = 'restricted'; reuses the scopable
    # `verb:scope` grammar so an HR policy can be pinned to `payroll.read`
    # without inventing a second permission vocabulary
    required_capability: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_thru: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("policies.id"), nullable=True, index=True
    )
    attachment_id: Mapped[str | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True, index=True
    )
    owner_employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class BusinessObject(TenantRecord, SoftDeleteAttributionMixin, Base):
    __tablename__ = "business_objects"

    object_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_jsonb: Mapped[dict] = mapped_column("payload_jsonb", JsonType, default=dict)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class BusinessObjectLink(IdMixin, TenantMixin, CreatedAtMixin, MetadataJsonbMixin, Base):
    __tablename__ = "business_object_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_object_id",
            "target_object_id",
            "link_type",
            name="business_object_links_unique_link",
        ),
    )

    source_object_id: Mapped[str] = mapped_column(ForeignKey("business_objects.id"), index=True)
    target_object_id: Mapped[str] = mapped_column(ForeignKey("business_objects.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(100))

    source_object: Mapped[BusinessObject] = relationship(foreign_keys=[source_object_id])
    target_object: Mapped[BusinessObject] = relationship(foreign_keys=[target_object_id])


class TimesheetHeader(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "timesheet_headers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "period_start",
            "period_end",
            name="timesheet_headers_tenant_employee_period_uk",
        ),
    )

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(back_populates="timesheet_headers")
    entries: Mapped[list["TimesheetEntry"]] = relationship(back_populates="header")


class EmployeeLeave(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    """One person's leave, as a fact: which kind, over which dates, how long,
    and where it got to. OFBiz's `EmplLeave`, with its three compromises undone.

    OFBiz keys this `(partyId, leaveTypeId, fromDate)` and hangs the approval
    off two columns on the row — `approverPartyId` and `leaveStatus`. Both are
    dropped here. The key becomes an id so that changing the dates is a new
    record rather than a delete-and-recreate that loses the history; the
    approval becomes `approval_records` + todos like every other family, so a
    workspace can have two levels, a return with a reason, and a trail.

    **There is no balance anywhere in this model, and that is the design.**
    "How many days do I have left" is not a fact anybody recorded — it follows
    from the tenant's leave policy applied to this person's 工龄 and these
    rows. Storing it would freeze a conclusion drawn under rules that change:
    a company that revises 年假 mid-year, or backdates a 调休 ratio, would have
    a ledger full of entries that were true under the old text. Computed, the
    same revision simply produces different answers, including for the past —
    `GET /policies?in_force_on=…` answers what the rule WAS. This is the same
    stance payroll takes on tax and quotations take on drift: the server keeps
    the facts, the agent applies the rules and shows its working.

    `duration_days` is the exception that proves it. It is a snapshot of the
    length as computed when the request was filed — weekends and holidays
    already taken out per the policy of that day — and it freezes with the
    approval, exactly as a quotation freezes `list_price_snapshot`. What the
    entitlement was is recomputed on demand; what this particular absence cost
    is what the approver agreed to."""

    __tablename__ = "employee_leaves"
    __table_args__ = (
        CheckConstraint("thru_date >= from_date", name="employee_leaves_period_ck"),
        # Half days are the point of the decimal; a request for zero days is a
        # request for nothing, and negative leave is not a thing.
        CheckConstraint("duration_days > 0", name="employee_leaves_duration_ck"),
        Index("employee_leaves_employee_idx", "tenant_id", "employee_id", "from_date"),
        Index("employee_leaves_type_idx", "tenant_id", "leave_type", "from_date"),
    )

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    # `leave_type` type-option family; the server never branches on the value
    leave_type: Mapped[str] = mapped_column(String(50), index=True)
    from_date: Mapped[date] = mapped_column(Date, index=True)
    thru_date: Mapped[date] = mapped_column(Date)
    # Days, with halves. Whether a Saturday inside the range counts is the
    # tenant's rule, applied by the agent before it writes this number — the
    # server stores what was agreed, not a date subtraction of its own.
    duration_days: Mapped[float] = mapped_column(Numeric(6, 2))
    # OFBiz splits this into a second classification table. Free text here: the
    # reason for one absence is prose, and a tree of reason codes is structure
    # nobody queries.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship()


class TimesheetEntry(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "timesheet_entries"

    header_id: Mapped[str] = mapped_column(ForeignKey("timesheet_headers.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    project_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hours: Mapped[float] = mapped_column(Numeric(5, 2))
    work_type: Mapped[str] = mapped_column(String(20), default="regular")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped[TimesheetHeader] = relationship(back_populates="entries")
    project: Mapped[Project | None] = relationship()


class Attachment(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """Tenant-scoped binary evidence (receipts, invoices). Standalone blobs:
    linking is the referencing object's job (e.g. expense_items.attachment_id).
    Uploads are idempotent per (tenant, sha256) — the same file claimed twice
    resolves to the same row, which is also the duplicate-receipt signal."""

    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="attachments_tenant_sha256_uk"),
    )

    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ExpenseClaim(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "expense_claims"

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    claim_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # running sum of the payments applied to this claim. The machine's `paid`
    # state stays as the flow's marker, but the money fact now lives in the
    # payment ledger — so "how much did we actually pay out" is answerable
    # without trusting a status. Historical `paid` claims predate the ledger and
    # are deliberately not backfilled.
    applied_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    employee: Mapped[Employee] = relationship()
    items: Mapped[list["ExpenseItem"]] = relationship(back_populates="claim")


class ExpenseItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "expense_items"

    claim_id: Mapped[str] = mapped_column(ForeignKey("expense_claims.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(50), default="other")
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    invoice_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    project_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    # full structured extraction from the receipt (发票代码, 购买方税号, …);
    # the typed columns above are the queryable subset
    extracted_fields_jsonb: Mapped[dict] = mapped_column("extracted_fields_jsonb", JsonType, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="items")
    project: Mapped[Project | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()


class PurchaseRequest(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "purchase_requests"

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    request_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    # target vendor is an intention, header-level and optional; the free-text
    # snapshot stands alone when master data has no match
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    vendor_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    items: Mapped[list["PurchaseRequestItem"]] = relationship(back_populates="request")


class PurchaseRequestItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "purchase_request_items"

    request_id: Mapped[str] = mapped_column(ForeignKey("purchase_requests.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    # sku refines the product to transaction granularity; null is a legal
    # fact — either the tenant's products ARE skus, or the variant (尺码配比
    # etc.) is genuinely undecided at requisition time
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    # 按单采购 (procure-to-order / 零库存): the sales order line this purchase
    # line exists to fulfil (OFBiz OrderItemAssoc, collapsed to the one
    # direction that matters here). It lives on THIS side because the sales
    # order is already confirmed — and therefore locked — by the time
    # procurement files the request; several purchase lines may point at one
    # sales line (split across vendors or deliveries). Null = stock purchase.
    sales_order_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_order_items.id"), nullable=True, index=True
    )
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # pricing is optional by design: an unpriced requisition is a normal
    # fact (询价 happens later in the flow), never an error
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[PurchaseRequest] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    sku: Mapped[ProductSku | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()


class SalesQuotation(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    """Outbound price quotation sent to a customer. Sent quotations are
    immutable facts — renegotiation creates a new revision row sharing the
    quote_number (append-only, like workflow definition versions)."""

    __tablename__ = "sales_quotations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "quote_number", "revision_no",
            name="sales_quotations_number_rev_uk",
        ),
    )

    # server-allocated when the agent doesn't bring a tenant convention
    quote_number: Mapped[str] = mapped_column(String(64))
    revision_no: Mapped[int] = mapped_column(Integer, default=1)
    revision_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_quotations.id"), nullable=True, index=True
    )
    # the owning sales rep; lifecycle actions are bound to this employee
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # per-quote buyer contact — may differ from the customer master default
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    # the negotiated document total (e.g. rounded 抹零); null means the line
    # sum is the total — /detail reports both facts, agents judge the gap
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship()
    customer: Mapped[Customer | None] = relationship()
    project: Mapped[Project | None] = relationship()
    revision_of: Mapped["SalesQuotation | None"] = relationship(remote_side="SalesQuotation.id")
    items: Mapped[list["SalesQuotationItem"]] = relationship(back_populates="quotation")


class SalesQuotationItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "sales_quotation_items"

    quotation_id: Mapped[str] = mapped_column(ForeignKey("sales_quotations.id"), index=True)
    # line order is a fact of the customer-facing document (unlike internal
    # requisitions), so it is explicit rather than insertion-order
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # catalog price captured at quoting time; the discount is derivable from
    # these two facts — the rate itself is deliberately not stored, policy
    # judgment belongs to the approval-flow agent
    list_price_snapshot: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # 货物13% / 服务6% mixed quoting: the per-line rate is an independent fact
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # keeps zero-priced giveaway lines from reading as 100% discounts
    is_gift: Mapped[bool] = mapped_column(Boolean, default=False)
    # 现货 / 两周 / 30天 — free text, the agent interprets
    lead_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    quotation: Mapped[SalesQuotation] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    sku: Mapped[ProductSku | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()


class PurchaseOrder(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    """The commitment to a VENDOR — what the purchase request (internal
    demand + approval) becomes once procurement actually orders. Split from
    SalesOrder on purpose where OFBiz shares one OrderHeader: the counterparty
    (vendor, required — a PO to nobody is not a document), the direction
    (receiving, not shipping) and the closure (goods into the inventory
    ledger, not a customer sign-off) all differ, and merging them costs both
    sides their clarity."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "po_number", name="purchase_orders_po_number_uk"),
    )

    po_number: Mapped[str] = mapped_column(String(64))
    # the counterparty is the point of the document — required, unlike the
    # sales side's optional customer
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    vendor_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # the procurement officer who placed it
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Charged to OUR standing account at this vendor: the order occupies the
    # account's available credit from the moment it is charged, so the same
    # prepayment cannot back two orders during the wait for delivery. The
    # occupation math and its guards live in `app/api/common.py`.
    billing_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_accounts.id"), nullable=True, index=True
    )
    # the agreed document total; the line sum plus adjustments should equal it
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    vendor: Mapped[Vendor] = relationship()
    employee: Mapped[Employee] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(back_populates="po")


class PurchaseOrderItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    """One ordered line. received_quantity is a running fact stamped by the
    receive endpoint (the same call that appends the inventory ledger when a
    facility is given); partial receiving is simply received < ordered while
    the PO sits in confirmed."""

    __tablename__ = "purchase_order_items"

    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 按单采购, one hop up the chain: the approved request line this PO line
    # orders. Sales traceability runs transitively —
    # SalesOrderItem ← PurchaseRequestItem ← here.
    purchase_request_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_request_items.id"), nullable=True, index=True
    )
    received_quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    po: Mapped[PurchaseOrder] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    sku: Mapped[ProductSku | None] = relationship()
    request_item: Mapped[PurchaseRequestItem | None] = relationship()


class PurchaseOrderAdjustment(TenantRecord, SoftDeleteMixin, MetadataJsonbMixin, Base):
    """The PO twin of the sales-side adjustments: signed amounts beside the
    line math (运费/税/折扣/抹零), optionally pinned to one line. Same
    vocabulary family as the sales documents — an adjustment type is not a
    direction-specific idea."""

    __tablename__ = "purchase_order_adjustments"

    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    po_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_order_items.id"), nullable=True, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    source_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    po: Mapped[PurchaseOrder] = relationship()
    item: Mapped[PurchaseOrderItem | None] = relationship()


class SalesOrder(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    """Fulfilment of a won quotation: the customer's committed purchase,
    tracked from internal confirmation through shipping to sign-off.
    Field design informed by OFBiz OrderHeader/OrderItemShipGroup, reduced
    to the agent-native single-shipment shape: one logistics leg on the
    header, promised dates per line, money as two facts (list snapshot +
    agreed price), no adjustment/payment machinery — those judgments live
    in agents and workflow definitions."""

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_no", name="sales_orders_order_no_uk"),
    )

    # server-allocated when the agent doesn't bring a tenant convention
    order_no: Mapped[str] = mapped_column(String(64))
    # the won quotation this order fulfils — FK + snapshot, like every other
    # master-data reference; free-standing orders (no quote) are legal facts
    quotation_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_quotations.id"), nullable=True, index=True
    )
    source_quote_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # the owning salesperson; lifecycle facts are bound to this employee
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # per-order ship-to — may differ from the customer master address
    ship_to_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    contract_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # the whole-order delivery promise; per-line promises live on the items
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Charged to the customer's standing account: the order occupies the
    # account's available credit from the moment it is charged — the window
    # between order and invoice (an e-commerce wait, a toB delivery gap) is
    # exactly where the same balance must not be spendable twice. The
    # occupation math and its guards live in `app/api/common.py`.
    billing_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_accounts.id"), nullable=True, index=True
    )
    # the agreed document total; null means the line sum is the total —
    # /detail reports both facts, agents judge the gap
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # single-shipment logistics facts (OFBiz ship groups reduced to one leg);
    # multi-shipment tenants split orders or use custom fields
    logistics_company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logistics_tracking_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    quotation: Mapped[SalesQuotation | None] = relationship()
    employee: Mapped[Employee] = relationship()
    customer: Mapped[Customer | None] = relationship()
    project: Mapped[Project | None] = relationship()
    items: Mapped[list["SalesOrderItem"]] = relationship(back_populates="order")


class SalesOrderItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    __tablename__ = "sales_order_items"

    order_id: Mapped[str] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    # line order is a fact of the customer-facing document, same as quotations
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # catalog price captured at ordering time (OFBiz unitListPrice); the
    # discount is derivable from the two facts, never stored
    list_price_snapshot: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_gift: Mapped[bool] = mapped_column(Boolean, default=False)
    # per-line delivery promise (OFBiz estimatedDeliveryDate) — a date here,
    # unlike the quotation's free-text lead_time: an order is a commitment
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[SalesOrder] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    sku: Mapped[ProductSku | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()


class SalesQuotationAdjustment(TenantRecord, SoftDeleteMixin, MetadataJsonbMixin, Base):
    """A signed amount that moves a quotation's total beside the line math —
    促销 discounts, tax, shipping, fees, 抹零. Modeled on OFBiz's
    QuoteAdjustment: many per quotation, each optionally pinned to one line
    (quotation_item_id null = a header-level adjustment). The amount is the
    recorded fact; source_percentage says how it was derived when it was a
    rate. Where the header total used to differ from computed_total
    implicitly, adjustments make the difference explicit and auditable."""

    __tablename__ = "sales_quotation_adjustments"

    quotation_id: Mapped[str] = mapped_column(ForeignKey("sales_quotations.id"), index=True)
    quotation_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_quotation_items.id"), nullable=True, index=True
    )
    # discount/promotion/tax/shipping/fee/surcharge/rounding/other
    adjustment_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # signed: negative reduces the total (discount, 抹零), positive adds
    # (tax, shipping, surcharge)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    source_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    quotation: Mapped[SalesQuotation] = relationship()
    item: Mapped[SalesQuotationItem | None] = relationship()


class SalesOrderAdjustment(TenantRecord, SoftDeleteMixin, MetadataJsonbMixin, Base):
    """The order-side twin of SalesQuotationAdjustment (OFBiz's
    OrderAdjustment): signed total adjustments, optionally pinned to one
    order line."""

    __tablename__ = "sales_order_adjustments"

    order_id: Mapped[str] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    order_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_order_items.id"), nullable=True, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    source_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    order: Mapped[SalesOrder] = relationship()
    item: Mapped[SalesOrderItem | None] = relationship()


class Invoice(TenantRecord, SoftDeleteAttributionMixin, CustomFieldsJsonbMixin, Base):
    """The bill itself, both directions — modeled on OFBiz's `Invoice`, whose
    `invoiceTypeId` likewise carries sales-vs-purchase on ONE entity.

    The orders were split (PurchaseOrder / SalesOrder) because their
    counterparty, direction and closure all differ. An invoice fails that test:
    its closure mechanic is identical on both sides (apply money until nothing
    is outstanding), and a 增值税发票 has one physical shape whether we issued
    it or received it. Splitting would duplicate the settlement machinery,
    which is the expensive half.

    `direction` is a plain constrained column rather than a type option because
    every guard in the settlement path branches on it — a vocabulary the tenant
    could extend would leave those guards undecidable.

    Two different numbers live here on purpose: `invoice_no` is this system's
    document number (allocated, always present), `tax_invoice_number` is the
    tax document's own 发票号码 (absent until the invoice is actually issued or
    the vendor's copy is entered)."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_no", name="invoices_invoice_no_uk"),
        # Counterparty is exactly one side, and the side must agree with the
        # direction. Enforced in the API with a message that names the fix; the
        # constraint is the backstop for imports and direct writes.
        CheckConstraint(
            "(direction = 'sales' and customer_id is not null "
            "and vendor_id is null and payee_employee_id is null) "
            "or (direction = 'purchase' and vendor_id is not null "
            "and customer_id is null and payee_employee_id is null) "
            "or (direction = 'payroll' and payee_employee_id is not null "
            "and customer_id is null and vendor_id is null)",
            name="invoices_direction_counterparty_ck",
        ),
        # 双发工资 is the expensive mistake in this family, so one payslip per
        # person per period is a database fact rather than an agent's care.
        Index(
            "invoices_payroll_period_uk",
            "tenant_id", "payee_employee_id", "period_start",
            unique=True,
            postgresql_where=text("direction = 'payroll' AND deleted_at IS NULL"),
            sqlite_where=text("direction = 'payroll' AND deleted_at IS NULL"),
        ),
    )

    invoice_no: Mapped[str] = mapped_column(String(64))
    # 'sales' = 销项 (we issued it), 'purchase' = 进项 (we received it)
    direction: Mapped[str] = mapped_column(String(10), index=True)
    # 增值税专用发票 / 普通发票 / 电子发票 / 形式发票 / 收据 — tenant vocabulary
    invoice_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # the 经办人 who owns the document, as in every other family
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    # 工资条 (direction='payroll'): the person being paid. Distinct from
    # employee_id above, which is whoever ran payroll.
    payee_employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    counterparty_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    # the pay period a payslip covers; required on payroll, meaningless
    # elsewhere. Real columns rather than custom_fields because the
    # one-per-person-per-period index has to be able to read them.
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # what aging is measured against; null = no agreed term, never overdue
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    # the agreed document total; null means the line sum is the total — the
    # same contract quotations and orders use, and /detail reports both facts
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # running sum of this invoice's payment applications — outstanding is
    # derived from it, never stored, because a partly-settled invoice is not a
    # state (same stance as "partial receiving is not a state")
    applied_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_invoice_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tax_invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # full structured extraction / 查验 result for a received invoice; the typed
    # columns above are the queryable subset (as on expense items)
    extracted_fields_jsonb: Mapped[dict] = mapped_column("extracted_fields_jsonb", JsonType, default=dict)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    # the order being billed — the anchor of the three-way match
    sales_order_id: Mapped[str | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True, index=True)
    purchase_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True, index=True
    )
    # OFBiz's Invoice.billingAccountId — this invoice is charged to a standing
    # account rather than billed for payment on its own. Drawing the account
    # down is an explicit entry, not a side effect of issuing the invoice.
    billing_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_accounts.id"), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
    payee_employee: Mapped[Employee | None] = relationship(foreign_keys=[payee_employee_id])
    customer: Mapped[Customer | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    project: Mapped[Project | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice")


class InvoiceItem(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    """One billed line (OFBiz `InvoiceItem`). `invoice_item_type` is what lets
    this family skip an adjustments table entirely: 运费/折扣/税/抹零 are line
    types here, exactly as OFBiz models them with `invoiceItemTypeId`, so the
    quotation/order pattern of a separate adjustment row buys nothing.

    Quantity and price are both optional — a pure charge line (运费 300) has
    neither, and refusing it would be refusing a normal invoice.

    The order-item links are OFBiz's `OrderItemBilling` collapsed into explicit
    FKs, matching how `PurchaseOrderItem.purchase_request_item_id` records its
    own document chain. They are what makes 已开票数量 answerable per order
    line, and therefore what makes the three-way match possible."""

    __tablename__ = "invoice_items"

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # goods / service / shipping / discount / tax / rounding / other
    invoice_item_type: Mapped[str] = mapped_column(String(30), default="goods")
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    sku_id: Mapped[str | None] = mapped_column(ForeignKey("product_skus.id"), nullable=True, index=True)
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sales_order_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_order_items.id"), nullable=True, index=True
    )
    purchase_order_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_order_items.id"), nullable=True, index=True
    )
    # a payslip's salary line names the pay_histories row it was computed from,
    # which is what keeps an issued payslip explainable a year later
    pay_history_id: Mapped[str | None] = mapped_column(
        ForeignKey("pay_histories.id"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    sku: Mapped[ProductSku | None] = relationship()


class Payment(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    """Money that moved (OFBiz `Payment`, whose `paymentTypeId` carries the
    direction the same way).

    An outbound payment is the single most-approved document in a Chinese SMB,
    so this family keeps the full approval half of the lifecycle. An inbound
    receipt has nothing to approve — the money already arrived — and is simply
    created in the terminal state, which every builtin allows.

    `counterparty_account` is here for one reason: the standing check against
    改单诈骗 is comparing the account a payment is about to go to against the
    account on the vendor's master record. Storing it makes that check auditable
    afterwards rather than only conversational."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payment_no", name="payments_payment_no_uk"),
        CheckConstraint("amount > 0", name="payments_amount_positive_ck"),
        # exactly one counterparty — a payment to nobody cannot be applied, and
        # a payment to two parties cannot be reconciled
        CheckConstraint(
            "(case when customer_id is null then 0 else 1 end) "
            "+ (case when vendor_id is null then 0 else 1 end) "
            "+ (case when payee_employee_id is null then 0 else 1 end) = 1",
            name="payments_single_counterparty_ck",
        ),
    )

    payment_no: Mapped[str] = mapped_column(String(64))
    # 'inbound' = 收款, 'outbound' = 付款
    direction: Mapped[str] = mapped_column(String(10), index=True)
    # 银行转账 / 现金 / 支票 / 银行承兑 / 商业承兑 / 微信 / 支付宝 — tenant vocabulary
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # the 经办人 (cashier) who owns the document
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    # 报销付款: the counterparty is one of our own people, not a master-data party
    payee_employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    counterparty_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    # running sum of this payment's applications; amount - applied_amount is
    # 预收款/预付款 — the unallocated balance IS the advance, so no separate
    # billing-account entity is needed
    applied_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    bank_account: Mapped[str | None] = mapped_column(String(200), nullable=True)
    counterparty_account: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
    payee_employee: Mapped[Employee | None] = relationship(foreign_keys=[payee_employee_id])
    customer: Mapped[Customer | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship()


class PayHistory(TenantRecord, CustomFieldsJsonbMixin, Base):
    """One effective-dated term of an employee's compensation — OFBiz's
    `PayHistory`, widened from the salary alone to every term that is a fact
    about THIS PERSON: the base salary, but also their commission rate, their
    bonus arrangement, their allowances.

    The dividing line is whether the sentence changes when you change the
    person. "13薪 in January" is company policy and belongs in a workflow
    definition; "张三 gets 3% of collections" is a term of 张三's employment and
    belongs here. National policy — 五险一金 rates and the like — belongs in
    neither: it is public knowledge the agent already has, and what it produced
    is recorded on the payslip line itself.

    Terms live here rather than in a tenant-defined business object for a
    reason that is easy to miss: business-object reads are not gated, and
    somebody's commission rate is as confidential as their salary. Everything in
    this table sits behind `payroll.read`.

    The point of the entity is the history. A raise does not overwrite a number:
    it closes the current row for that COMPONENT and opens a new one, in one
    call, because as two calls they eventually drift. What someone was paid last
    March therefore stays answerable, which is what a payslip issued last March
    needs in order to stay explainable.

    Rows a payslip has cited cannot be edited — the payslip's line names the row
    it came from, and a record that moved under an issued document is worse than
    no record."""

    __tablename__ = "pay_histories"
    __table_args__ = (
        CheckConstraint("amount is null or amount >= 0", name="pay_histories_amount_ck"),
        CheckConstraint("rate is null or rate >= 0", name="pay_histories_rate_ck"),
        # a term that states nothing is not a term
        CheckConstraint(
            "amount is not null or rate is not null or formula is not null",
            name="pay_histories_states_something_ck",
        ),
        # a proportion with nothing to apply it to is unusable
        CheckConstraint("rate is null or basis is not null", name="pay_histories_rate_basis_ck"),
        CheckConstraint(
            "effective_thru is null or effective_thru >= effective_from",
            name="pay_histories_period_ck",
        ),
        Index(
            "pay_histories_employee_from_idx",
            "tenant_id", "employee_id", "component", "effective_from",
        ),
        # one row per employee per component per start date — salary and
        # commission legitimately start on the same day. Overlapping RANGES are
        # checked in the API and by the integrity audit, which an index cannot
        # express.
        Index(
            "pay_histories_employee_from_uk",
            "tenant_id", "employee_id", "component", "effective_from",
            unique=True,
        ),
    )

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    # base_salary / commission / bonus / allowance / … — tenant vocabulary
    component: Mapped[str] = mapped_column(String(30), default="base_salary", index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    # null = still in force; a new row for the same component closes it
    effective_thru: Mapped[date | None] = mapped_column(Date, nullable=True)
    # a scalar term: 12000 per month, an 800 monthly allowance
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # a proportional term: 0.03. Meaningless without `basis`.
    rate: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # what the rate applies TO, in the tenant's own words — 回款额 / 毛利 / 签约额
    basis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # the whole arrangement in words when neither shape fits (阶梯提成, 绩效系数).
    # Text for the AGENT to read; the server never parses it, exactly as it
    # never parses a workflow definition.
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    # month / hour / day / year — what a scalar amount is per
    period_type: Mapped[str] = mapped_column(String(20), default="month")
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    employee: Mapped[Employee] = relationship()


class BillingAccount(TenantRecord, SoftDeleteMixin, CustomFieldsJsonbMixin, Base):
    """A party's standing account with us — OFBiz's `BillingAccount`, widened
    past money.

    OFBiz models one thing here: a customer's credit/house account, with
    `accountLimit` as the credit ceiling and the balance derived from the
    invoices charged to it. That shape generalizes exactly: an account is a
    balance in some unit, with a floor, owned by one party. Loyalty points,
    stored value and coupon quotas are the same object with a different unit —
    which is why `unit_type` sits beside the money case rather than in a second
    table.

    `unit_type` is a constrained column and NOT a type option, for the same
    reason `Invoice.direction` is: every guard in the settlement path branches
    on it, and applying money to a points account must be unrepresentable.

    `status` is a small fixed vocabulary that the server DOES gate writes on.
    That is not a contradiction of "state names belong to the tenant" — that
    rule is about documents with tenant-editable machines. An account is master
    data, like a vendor's active/archived, and refusing new movement is the
    entire point of freezing one.

    An unapplied payment and a billing account are different things and both
    exist on purpose: the first is a specific sum in transit, the second is a
    standing account with a limit and a policy. Money moves from the first into
    the second by being applied to it."""

    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_code", name="billing_accounts_code_uk"),
        CheckConstraint("credit_limit >= 0", name="billing_accounts_credit_limit_ck"),
        # exactly one owner, as on payments: an account belonging to nobody
        # cannot be reconciled, and one belonging to two parties cannot either
        CheckConstraint(
            "(case when customer_id is null then 0 else 1 end) "
            "+ (case when vendor_id is null then 0 else 1 end) "
            "+ (case when employee_id is null then 0 else 1 end) = 1",
            name="billing_accounts_single_owner_ck",
        ),
        CheckConstraint("unit_type in ('currency', 'points')", name="billing_accounts_unit_type_ck"),
    )

    account_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    # 'currency' = 钱 (储值/挂账), 'points' = 积分/券额 and anything else counted
    unit_type: Mapped[str] = mapped_column(String(10), index=True)
    # a currency code when unit_type is 'currency'; a tenant vocabulary entry
    # (billing_account_unit) when it is 'points'
    unit: Mapped[str] = mapped_column(String(30))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    owner_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # how far the balance may go NEGATIVE — the credit line. 0 (the default)
    # means no overdraft, which is what a points account wants.
    credit_limit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    # running sum of this account's entries; the entries are the truth
    balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # the card/account number this account had in whatever system it came from
    external_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    employee: Mapped[Employee | None] = relationship()

    @property
    def available_amount(self) -> float:
        """What may still be spent: the balance plus whatever credit remains."""
        return float(self.balance or 0) + float(self.credit_limit or 0)


class BillingAccountEntry(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """One movement on an account — the append-only ledger its balance is a sum
    of, exactly as `InventoryItemDetail` is for stock.

    Rows are immutable: no update, no delete, and a mistake is corrected by a
    counter-entry.

    Provenance uses the generic `(entity_type, entity_id)` pair, deliberately
    UNLIKE `PaymentApplication`'s explicit foreign keys. The difference is what
    the reference means: a payment application names the document it settles —
    a closed set, and money correctness depends on it — while an entry names
    whatever caused it, which is open-ended (a payment application, an invoice,
    an order, a birthday grant, a manual adjustment, or another entry when this
    one expires it).

    `expires_at` only means anything on a points account. Expiry itself is not
    automatic: a flow agent writes a negative `expired` entry pointing at the
    earn entry it expires, which is what makes the sweep idempotent and keeps
    the FIFO question — whose answer is tenant policy — out of the server."""

    __tablename__ = "billing_account_entries"
    __table_args__ = (
        # the key names a CALL; the ordinal is this row's place in it, so a
        # multi-line grant does not collide with itself
        Index(
            "billing_account_entries_idempotency_uk",
            "tenant_id", "billing_account_id", "idempotency_key", "idempotency_seq",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("billing_account_entries_source_idx", "tenant_id", "entity_type", "entity_id"),
        Index("billing_account_entries_expiry_idx", "tenant_id", "billing_account_id", "expires_at"),
    )

    billing_account_id: Mapped[str] = mapped_column(ForeignKey("billing_accounts.id"), index=True)
    # signed: positive adds, negative spends or reverses
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    # deposit / charge / refund / earned / redeemed / expired / adjustment /
    # transfer / initial / import_initial / other — tenant vocabulary
    reason: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # this row's position in the call the key names — see the index above
    idempotency_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    account: Mapped[BillingAccount] = relationship()


class PaymentApplication(IdMixin, TenantMixin, CreatedAtMixin, Base):
    """核销: one act of settling part of a payment against one document —
    OFBiz's `PaymentApplication`, including its ability to point at another
    payment (netting a refund against a receipt).

    Rows are immutable: there is no update or delete, and a mistake is
    corrected by a counter-entry with a negative `amount_applied`. This is the
    same contract `InventoryItemDetail` keeps, for the same reason — a ledger
    that can be edited afterwards cannot be reconciled against anything.

    The target keeps OFBiz's parallel
    invoiceId/billingAccountId/toPaymentId columns rather than this codebase's
    generic `(entity_type, entity_id)` pair: that pair records open-ended ledger
    PROVENANCE (as in `InventoryItemDetail`), while a settlement is a closed
    document chain whose correctness is money — see the column comments below.

    `idempotency_key` exists because this is a money-writing endpoint and agents
    retry: a repeat with the same key returns what was recorded instead of
    applying twice."""

    __tablename__ = "payment_applications"
    __table_args__ = (
        # The key identifies a CALL, which may carry many lines, so the row's
        # position within it is part of the uniqueness. Without the ordinal a
        # multi-line call collides with itself on the second row.
        Index(
            "payment_applications_idempotency_uk",
            "tenant_id", "payment_id", "idempotency_key", "idempotency_seq",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
        # Exactly one target. A row settling nothing is money that vanished; a
        # row settling two documents cannot be reconciled against either.
        CheckConstraint(
            "(case when invoice_id is null then 0 else 1 end) "
            "+ (case when expense_claim_id is null then 0 else 1 end) "
            "+ (case when billing_account_id is null then 0 else 1 end) "
            "+ (case when to_payment_id is null then 0 else 1 end) = 1",
            name="payment_applications_single_target_ck",
        ),
        # An invoice line only means something inside its invoice.
        CheckConstraint(
            "invoice_item_id is null or invoice_id is not null",
            name="payment_applications_item_needs_invoice_ck",
        ),
    )

    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    # The target, as OFBiz's PaymentApplication names it: one nullable column
    # per kind, exactly one set. This family gets real foreign keys rather than
    # the generic (entity_type, entity_id) pair used for ledger provenance
    # elsewhere, because a settlement IS a document chain — the same reason
    # PurchaseOrderItem.purchase_request_item_id is an explicit FK — and
    # because money rows are worth database-level referential integrity: a bare
    # uuid can point at a document that does not exist, and only the API would
    # ever notice.
    invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True, index=True
    )
    # Optional refinement (OFBiz invoiceItemSeqId), and usually absent: in
    # practice money arrives against an invoice, not against one of its lines.
    # The amount guards stay at document level either way.
    invoice_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoice_items.id"), nullable=True, index=True
    )
    expense_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("expense_claims.id"), nullable=True, index=True
    )
    # OFBiz's billingAccountId: money paid INTO a standing account (客户预存) or
    # refunded back out of one. Unlike the other targets this one has no ceiling
    # — a deposit is not a claim — so the settlement guard checks the account's
    # balance floor instead. See SettlementTarget in app/api/billing.py.
    billing_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_accounts.id"), nullable=True, index=True
    )
    # OFBiz's toPaymentId: netting a refund against the receipt that overpaid
    to_payment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True, index=True
    )
    # signed: negative is the counter-entry that reverses an earlier application
    amount_applied: Mapped[float] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # this row's position in the call the key names — see the index above
    idempotency_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    payment: Mapped[Payment] = relationship(foreign_keys=[payment_id])
    to_payment: Mapped[Payment | None] = relationship(foreign_keys=[to_payment_id])

    # The API speaks one uniform way of naming a target — agents say
    # `applied_to_type: "invoice"` — while storage keeps a column per kind.
    # These two derive that shape from whichever column is set, so the request
    # and response contract is unchanged by how the row is stored.
    @property
    def applied_to_type(self) -> str:
        if self.invoice_id is not None:
            return "invoice"
        if self.expense_claim_id is not None:
            return "expense_claim"
        if self.billing_account_id is not None:
            return "billing_account"
        return "payment"

    @property
    def applied_to_id(self) -> str | None:
        return (
            self.invoice_id
            or self.expense_claim_id
            or self.billing_account_id
            or self.to_payment_id
        )


class ApprovalRecord(IdMixin, TenantMixin, CreatedAtMixin, MetadataJsonbMixin, Base):
    __tablename__ = "approval_records"
    __table_args__ = (
        # natural key: agent retries of the same action are idempotent
        UniqueConstraint(
            "tenant_id", "entity_type", "entity_id", "round_no", "sequence_no", "action",
            name="approval_records_action_uk",
        ),
        # ONE decision per node. The key above includes `action`, so it made a
        # retry idempotent and left `approved` and `rejected` at the same
        # round/sequence as two perfectly legal rows — a document carrying both
        # decisions from the same seat, with nothing to say which one stands.
        #
        # It is reachable without anyone doing anything odd: the same approver
        # in two agent sessions, one of them working from a queue it listed
        # before the other acted. A Python check alone would be the same
        # check-then-insert those two sessions are already racing on, so the
        # guard is the index and the readable 409 is the courtesy.
        #
        # `commented` stays outside the predicate — an objection that decides
        # nothing may sit beside the decision, and several may.
        Index(
            "approval_records_one_decision_uk",
            "tenant_id", "entity_type", "entity_id", "round_no", "sequence_no",
            unique=True,
            postgresql_where=text(
                "historical_conflict_closed is false and action in ("
                + ", ".join(f"'{value}'" for value in DECIDED_APPROVAL_ACTIONS)
                + ")"
            ),
            sqlite_where=text(
                "historical_conflict_closed is false and action in ("
                + ", ".join(f"'{value}'" for value in DECIDED_APPROVAL_ACTIONS)
                + ")"
            ),
        ),
        # Declared here, not only in the migration. A constraint that lives only
        # in migrations is absent from every test database — `create_all` builds
        # from this file — which is exactly how invoices and payments went
        # release after release being refused by Postgres and accepted by the
        # suite. The same lesson the open-todo index above already learned.
        CheckConstraint(
            "entity_type in ("
            + ", ".join(f"'{value}'" for value in APPROVAL_ENTITY_TYPES)
            + ")",
            name="approval_records_entity_type_chk",
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(50), default="timesheet_header")
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    round_no: Mapped[int] = mapped_column(default=1)
    sequence_no: Mapped[int] = mapped_column(default=1)
    action: Mapped[str] = mapped_column(String(20))
    # A read-only operator closure for a pre-index contradiction. Both original
    # approval facts stay in the trail; this flag says the *node* has been
    # retired and must not occupy the one-active-decision index. It is not an
    # API input: setting it is a separately approved data-remediation act.
    historical_conflict_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approver_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResourceBooking(TenantRecord, MetadataJsonbMixin, Base):
    __tablename__ = "resource_bookings"

    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    booked_by_employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    booking_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(TenantMixin, CreatedAtMixin, Base):
    """Append-only audit trail: what happened to which record, by whom.
    Read-only accountability and troubleshooting — deliberately NOT a
    delivery/notification mechanism; agent coordination uses todos and
    state queries."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    actor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail_jsonb: Mapped[dict] = mapped_column("detail_jsonb", JsonType, default=dict)


class Todo(TenantRecord, MetadataJsonbMixin, Base):
    __tablename__ = "todos"

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    todo_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        # One open assignment per person per record: POST /todos checks it in
        # Python, and this is what holds when two flow runs both pass that
        # SELECT. It has guarded Postgres since the baseline migration but was
        # never declared here, so test databases built by `create_all` — and
        # anything reading the model for the truth — went without it. The scope
        # is per-EMPLOYEE, not per record, because parallel sign-off means
        # several people legitimately hold an open todo on one document.
        Index(
            "todos_open_entity_assignee_uk",
            "tenant_id", "employee_id", "entity_type", "entity_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
        # …and the same for what a todo may point at, for the same reason.
        CheckConstraint(
            "entity_type in ("
            + ", ".join(f"'{value}'" for value in TODO_ENTITY_TYPES)
            + ")",
            name="todos_entity_type_chk",
        ),
        # The status vocabulary, declared here for the third time and the first
        # one that matters. Postgres has carried
        # `check (status in ('open','completed'))` since the baseline while
        # `schemas.TodoStatus` has said `cancelled` — and because this was not
        # declared, SQLite had no constraint, so the whole suite passed over a
        # value the real database refused. Deleting a document with an open
        # todo was a 500 in production the entire time.
        CheckConstraint(
            "status in (" + ", ".join(f"'{value}'" for value in TODO_STATUSES) + ")",
            name="todos_status_chk",
        ),
    )


class FlowSubscription(TenantRecord, Base):
    """Which entity types ORYH's hosted agent drives for this tenant.

    Enrollment in a service, not a business rule: it records *that* the tenant
    handed one entity type's routing to the platform, never *how* that routing
    goes — the workflow definition still says that, and the driver skill still
    reads it. Per entity type on purpose, so a company can hand over timesheets
    and keep quotations on its own agent.

    `driver_skill` names the skill the run executes. It lives here rather than in
    the runner because otherwise the runner would need a hardcoded
    entity-type → skill table, which is exactly the business knowledge that is
    supposed to stay tenant data — and a tenant-defined object type
    (`warranty_card`) has no skill the platform could have guessed.

    `queue_filter` is the list query that finds unattended records, merged with
    `without_open_todo=true`. It is here for the same reason: "which statuses
    mean in flight" is the tenant's lifecycle talking, and a dispatcher that
    decided it would be interpreting business state.
    """

    __tablename__ = "flow_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", name="flow_subscriptions_entity_uk"),
    )

    entity_type: Mapped[str] = mapped_column(String(100))
    driver_skill: Mapped[str] = mapped_column(String(150))
    queue_filter: Mapped[dict] = mapped_column("queue_filter_jsonb", JsonType, default=dict)
    # How often the dispatcher looks when nothing has signalled. Time-driven
    # nodes (quotation expiry, an overdue promise) have no change to react to,
    # so this tick is the only thing that ever reaches them.
    cadence_seconds: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The hosted principal these runs act as. Deactivating that key stops the
    # work no matter what this row says; the two are meant to be switched
    # together, and the tenant can do either.
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Runs that found work and moved nothing, and the resulting stop. These live
    # here rather than in the runner's memory because forgetting them costs
    # money: a queue that will not drain would resume burning a run every
    # cadence after each restart and each deploy. Keeping them in the record
    # layer also means several runner replicas agree on what is parked without
    # talking to each other.
    unmoved_runs: Mapped[int] = mapped_column(Integer, default=0)
    parked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlowRun(TenantRecord, Base):
    """One pass of the hosted agent over one entity type's work queue.

    The customer-facing answer to "what has your agent been doing in my
    company" — and the operator's, when a tenant's flow stops moving. Business
    writes stay in the audit trail where they belong; this is the envelope
    around them: when it ran, what it found, what it moved, and why it stopped
    if it did.
    """

    __tablename__ = "flow_runs"

    subscription_id: Mapped[str | None] = mapped_column(
        ForeignKey("flow_subscriptions.id"), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(100))
    # what woke this run: "cadence" (the tick), "signal" (a change), "manual"
    trigger: Mapped[str] = mapped_column(String(20), default="cadence")
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # queue_size is what the dispatcher saw before spending a run; the gap
    # between it and items_advanced is where a stuck flow shows itself.
    queue_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_advanced: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_jsonb: Mapped[dict] = mapped_column("detail_jsonb", JsonType, default=dict)
    recorded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


# Every fixed-value column's CHECK, attached from one registry rather than
# restated on thirty classes. Runs after the last class so `Base.metadata`
# already holds every table this module defines.
#
# It has to be here and not only in the migrations: SQLite builds its schema
# from this metadata, so a constraint absent here is absent from every test
# database, and the suite then passes over values the real database refuses.
_attached_constraints = apply_table_constraints(Base.metadata)
