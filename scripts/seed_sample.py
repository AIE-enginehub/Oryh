#!/usr/bin/env python3
"""Load a cohesive fictional sample company ('Northwind Instruments') for evaluators.

Unlike `ensure_standalone_tenant.py` (which creates an empty workspace on first
boot), this script is optional and idempotent: operators who want a realistic
starting dataset to test AI agents against can run:

    docker compose exec api python scripts/seed_sample.py

Automatic first boot creates the workspace and sample records in one
transaction. For a manual import, rerun the same command after an interruption. The
import recognizes the already committed prefix (including older imports) and
records completion only after the last journal entry. A finished workspace
is left alone even if an evaluator subsequently edits the sample records.

All records are written through the real FastAPI routes using a short-lived
service API key that is deleted in a `finally` block before returning.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, or_, select, text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.permissions import PRINCIPAL_TENANT_SERVICE
from app.db.session import create_ops_sessionmaker, get_db
from app.main import app
from app.models import (
    AccountingSettings,
    ApiKey,
    AuditLog,
    BusinessRule,
    Customer,
    Employee,
    Facility,
    InventoryItem,
    InventoryItemDetail,
    Invoice,
    JournalEntry,
    LedgerAccount,
    Product,
    Project,
    ProjectMilestone,
    ProjectTask,
    PurchaseOrder,
    SalesOrder,
    SalesQuotation,
    Tenant,
    User,
    Vendor,
    generate_api_key,
    hash_api_key,
)
from app.services.audit import record_audit

SAMPLE_COMPANY_NAME = "Northwind Instruments"
SAMPLE_SENTINEL_CODE = "NW-CAL-100"  # A product identifier, not a completion marker.
EPHEMERAL_KEY_LABEL = "_seed_sample_ephemeral"
SAMPLE_COMPLETED = "sample.northwind_loaded"

# Match only this tenant's committed prefix. For records with generated
# numbers, identify the sample document by its parties and sample title,
# not a date (a retry may run tomorrow) or a freshly allocated number.
_SAMPLE_ROWS = {
    "/employees": (Employee, ("employee_code", "email")),
    "/facilities": (Facility, ("facility_code", "name")),
    "/customers": (Customer, ("customer_code", "name")),
    "/vendors": (Vendor, ("vendor_code", "name")),
    "/products": (Product, ("product_code", "name")),
    "/inventory-items": (InventoryItem, ("product_id", "facility", "lot_id", "sku_id")),
    "/business-rules": (BusinessRule, ("kind", "code", "title", "body")),
    "/business-rules/publish": (BusinessRule, ("kind", "entity_kind", "object_type", "title", "body")),
    "/sales-quotations": (SalesQuotation, ("customer_id", "employee_id", "title")),
    "/sales-orders": (SalesOrder, ("customer_id", "employee_id", "title")),
    "/invoices": (Invoice, ("direction", "customer_id", "employee_id", "title")),
    "/purchase-orders": (PurchaseOrder, ("vendor_id", "employee_id", "title")),
    "/projects": (Project, ("project_code", "project_name")),
    "/project-tasks": (ProjectTask, ("project_id", "task_code", "name")),
    "/project-milestones": (ProjectMilestone, ("project_id", "name")),
    "/accounting-settings": (AccountingSettings, ("functional_currency",)),
    "/ledger-accounts": (LedgerAccount, ("account_code", "name", "account_type")),
    "/journal-entries": (JournalEntry, ("description", "status")),
}


async def _api_call(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    expected: tuple[int, ...] = (200, 201),
) -> dict[str, Any]:
    response = await client.request(method, f"/api/v1{path}", json=payload)
    if response.status_code not in expected:
        raise RuntimeError(f"{method} /api/v1{path} -> {response.status_code}: {response.text}")
    body = response.json() if response.content else {}
    return body.get("data", body)


def _committed_sample(db: Session, tenant_id: str, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    model, fields = _SAMPLE_ROWS[path]
    identity = {field: payload[field] for field in fields}
    try:
        existing = db.scalars(select(model).filter_by(tenant_id=tenant_id, **identity)).one_or_none()
    except MultipleResultsFound as exc:
        raise RuntimeError(f"seed_sample: ambiguous sample records at {path}; review before resuming") from exc
    if existing is None:
        return None
    if getattr(existing, "deleted_at", None) is not None:
        raise RuntimeError(f"seed_sample: archived sample record at {path}; review before resuming")
    if isinstance(existing, (SalesQuotation, SalesOrder, PurchaseOrder, Invoice)):
        amount = payload.get("total_amount")
        actual_amount = existing.total_amount
        if amount is None:
            amount = sum(item["amount"] for item in payload["items"])
        if isinstance(existing, Invoice) and actual_amount is None:
            # A line-item invoice need not repeat its total on the header.
            actual_amount = sum(line.amount or 0 for line in existing.items if line.deleted_at is None)
        if existing.currency != payload["currency"] or actual_amount != amount:
            raise RuntimeError(f"seed_sample: existing document at {path} has a different amount or currency")
    # Similar descriptions are not proof an opening balance was
    # posted. Verify the immutable movement/lines, not the live
    # stock quantity or account balance that could since change.
    if isinstance(existing, InventoryItem) and not db.scalar(select(InventoryItemDetail.id).filter_by(
        tenant_id=tenant_id, inventory_item_id=existing.id, reason="initial",
        description=payload["initial_description"], quantity_on_hand_diff=payload["initial_quantity"],
    )):
        raise RuntimeError("seed_sample: existing stock position has a different opening movement")
    if isinstance(existing, JournalEntry):
        actual = [(line.ledger_account_id, line.debit, line.credit) for line in existing.lines]
        expected_lines = [(line["ledger_account_id"], line.get("debit", 0), line.get("credit", 0))
                          for line in payload["lines"]]
        if sorted(actual) != sorted(expected_lines):
            raise RuntimeError("seed_sample: existing journal entry has different lines")
    return {field: getattr(existing, field) for field in ("id", "name", "product_code", "status")
            if hasattr(existing, field)}


async def _populate_via_api(
    api_key: str,
    admin_employee_id: str,
    db: Session,
    tenant_id: str,
    *,
    resume: bool = True,
) -> dict[str, Any]:
    recovering = resume

    async def write(path: str, payload: dict[str, Any], *, method: str = "POST", expected=(200, 201)):
        nonlocal recovering
        if recovering:
            committed = _committed_sample(db, tenant_id, path, payload)
            if committed is not None:
                return committed
            # The old script committed requests in order. From the first
            # missing write onward, use normal API conflict handling: do not
            # adopt lookalike records later in the workspace.
            recovering = False
        return await _api_call(client, method, path, payload, expected=expected)

    headers = {"X-API-Key": api_key}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://oryh.local",
        headers=headers,
        timeout=30.0,
    ) as client:
        # 1. Colleagues
        priya = await write(
            "/employees",
            {
                "employee_code": "NW-002",
                "name": "Priya Nair",
                "email": "priya@northwind.example",
                "timezone": "UTC",
                "metadata": {"department": "Sales", "title": "Account Lead"},
            },
        )
        # Date the sample, not this invocation: a retry next month (or year)
        # must not move half of the example's documents to a new period.
        sample_date = db.scalars(select(Employee.created_at).filter_by(
            tenant_id=tenant_id, id=priya["id"])).one().date()
        daniel = await write(
            "/employees",
            {
                "employee_code": "NW-003",
                "name": "Daniel Cho",
                "email": "daniel@northwind.example",
                "timezone": "UTC",
                "metadata": {"department": "Operations", "title": "Finance & Ops Manager"},
            },
        )

        # 2. Facility, Customers, Vendors
        await write(
            "/facilities",
            {
                "facility_code": "WH-MAIN",
                "name": "Main Warehouse",
                "facility_type": "warehouse",
                "address": "410 Harbor Way, Seattle, WA",
            },
        )
        meridian = await write(
            "/customers",
            {
                "customer_code": "CUST-MERIDIAN",
                "name": "Meridian Field Services Ltd",
                "customer_kind": "company",
                "contact": "Hannah Cole",
                "email": "procurement@meridian.example",
                "payment_terms": "Net 30",
                "owner_employee_id": priya["id"],
            },
        )
        cascade = await write(
            "/customers",
            {
                "customer_code": "CUST-CASCADE",
                "name": "Cascade Marine Lab",
                "customer_kind": "company",
                "contact": "Marcus Bell",
                "email": "orders@cascade-lab.example",
                "payment_terms": "Net 15",
                "owner_employee_id": priya["id"],
            },
        )
        apex = await write(
            "/vendors",
            {
                "vendor_code": "VEND-APEX",
                "name": "Apex Precision Sensors",
                "contact": "Kenji Sato",
                "email": "supply@apex-sensors.example",
            },
        )
        await write(
            "/vendors",
            {
                "vendor_code": "VEND-PAC",
                "name": "Pacific Packaging Co",
                "contact": "Elena Ortiz",
                "email": "desk@pacific-pack.example",
            },
        )

        # 3. Products & Opening Inventory
        cal_kit = await write(
            "/products",
            {
                "product_code": SAMPLE_SENTINEL_CODE,
                "name": "Portable Calibration Kit",
                "product_type": "finished_good",
                "unit": "unit",
                "list_price": 1250.0,
                "currency": "USD",
                "spec": "Field calibration bench, ISO-17025 traceable",
            },
        )
        probe = await write(
            "/products",
            {
                "product_code": "NW-PRB-220",
                "name": "Pressure Probe Sensor",
                "product_type": "finished_good",
                "unit": "unit",
                "list_price": 240.0,
                "currency": "USD",
                "spec": "0-60 bar digital transducer probe",
            },
        )
        svc_day = await write(
            "/products",
            {
                "product_code": "NW-SVC-DAY",
                "name": "On-Site Commissioning Day",
                "product_type": "service",
                "unit": "day",
                "list_price": 850.0,
                "currency": "USD",
                "spec": "Certified engineer field calibration day",
            },
        )
        await write(
            "/inventory-items",
            {
                "product_id": cal_kit["id"],
                "facility": "Main Warehouse",
                "lot_id": "",
                "sku_id": None,
                "currency": "USD",
                "unit_cost": 740.0,
                "initial_quantity": 45,
                "initial_description": "Opening sample warehouse balance",
            },
        )
        await write(
            "/inventory-items",
            {
                "product_id": probe["id"],
                "facility": "Main Warehouse",
                "lot_id": "",
                "sku_id": None,
                "currency": "USD",
                "unit_cost": 135.0,
                "initial_quantity": 120,
                "initial_description": "Opening sample warehouse balance",
            },
        )

        # 4. Published Natural-Language Business Rules
        discount_draft = await write(
            "/business-rules",
            {
                "kind": "policy",
                "code": "SALES-DISC-01",
                "category": "finance",
                "title": "Commercial Discount Policy",
                "effective_from": f"{sample_date.year}-01-01",
                "body": (
                    "Standard list discounts up to 8% may be offered by the account owner. "
                    "Discounts above 8% up to 15% require operations review; anything above 15% "
                    "requires a signed annual price agreement."
                ),
            },
        )
        if discount_draft["status"] == "draft":
            recovering = False
            await _api_call(
                client, "POST", f"/business-rules/{discount_draft['id']}/publish",
                {"effective_from": f"{sample_date.year}-01-01"}, expected=(200,),
            )
        await write(
            "/business-rules/publish",
            {
                "kind": "approval_flow",
                "entity_kind": "builtin",
                "object_type": "sales_quotation",
                "title": "Sales Quotation Approval Flow",
                "body": (
                    "Quotations within an 8% discount require one manager review by Daniel Cho. "
                    "Quotations above 8% discount require operations and finance review before approval."
                ),
            },
        )

        # 5. Quotations, Sales Orders, Invoices, Purchase Orders
        quotation = await write(
            "/sales-quotations",
            {
                "employee_id": priya["id"],
                "customer_id": meridian["id"],
                "title": "Meridian Annual Calibration Package",
                "quote_date": sample_date.isoformat(),
                "valid_until": (sample_date + timedelta(days=30)).isoformat(),
                "currency": "USD",
                "payment_terms": "Net 30",
                "total_amount": 11200.0,
                "items": [
                    {
                        "line_no": 1,
                        "product_id": cal_kit["id"],
                        "product_name_snapshot": cal_kit["name"],
                        "quantity": 8,
                        "list_price_snapshot": 1250.0,
                        "unit_price": 1187.5,
                        "amount": 9500.0,
                    },
                    {
                        "line_no": 2,
                        "product_id": svc_day["id"],
                        "product_name_snapshot": svc_day["name"],
                        "quantity": 2,
                        "list_price_snapshot": 850.0,
                        "unit_price": 850.0,
                        "amount": 1700.0,
                    },
                ],
            },
        )
        order = await write(
            "/sales-orders",
            {
                "employee_id": priya["id"],
                "customer_id": cascade["id"],
                "title": "Cascade Q4 Calibration Supply",
                "order_date": sample_date.isoformat(),
                "promised_date": (sample_date + timedelta(days=7)).isoformat(),
                "currency": "USD",
                "total_amount": 7400.0,
                "items": [
                    {
                        "line_no": 1,
                        "product_id": cal_kit["id"],
                        "product_name_snapshot": cal_kit["name"],
                        "quantity": 4,
                        "unit_price": 1250.0,
                        "amount": 5000.0,
                    },
                    {
                        "line_no": 2,
                        "product_id": probe["id"],
                        "product_name_snapshot": probe["name"],
                        "quantity": 10,
                        "unit_price": 240.0,
                        "amount": 2400.0,
                    },
                ],
            },
        )
        invoice = await write(
            "/invoices",
            {
                "direction": "sales",
                "employee_id": daniel["id"],
                "customer_id": cascade["id"],
                "title": "Cascade Q4 Calibration Supply",
                "invoice_date": sample_date.isoformat(),
                "due_date": (sample_date + timedelta(days=15)).isoformat(),
                "currency": "USD",
                "items": [
                    {
                        "invoice_item_type": "goods",
                        "product_id": cal_kit["id"],
                        "product_name_snapshot": "Portable Calibration Kits & Pressure Probes",
                        "amount": 7400.0,
                    }
                ],
            },
        )
        if invoice["status"] == "draft":
            recovering = False
            await _api_call(client, "POST", f"/invoices/{invoice['id']}/submit", {}, expected=(200,))

        po = await write(
            "/purchase-orders",
            {
                "employee_id": admin_employee_id,
                "vendor_id": apex["id"],
                "title": "Sensor Batch Replenishment",
                "order_date": sample_date.isoformat(),
                "promised_date": (sample_date + timedelta(days=14)).isoformat(),
                "status": "confirmed",
                "currency": "USD",
                "total_amount": 4800.0,
            },
        )

        # 6. Project Execution
        project = await write(
            "/projects",
            {
                "project_code": "PRJ-MERIDIAN",
                "project_name": "Meridian Calibration Rollout",
            },
        )
        await write(
            "/project-tasks",
            {
                "project_id": project["id"],
                "task_code": "TASK-01",
                "name": "Bench Acceptance & Calibration",
                "assignee_employee_id": daniel["id"],
                "planned_hours": 16.0,
                "status": "in_progress",
            },
        )
        await write(
            "/project-tasks",
            {
                "project_id": project["id"],
                "task_code": "TASK-02",
                "name": "On-Site Commissioning",
                "assignee_employee_id": priya["id"],
                "planned_hours": 16.0,
                "status": "not_started",
            },
        )
        await write(
            "/project-milestones",
            {
                "project_id": project["id"],
                "name": "Customer Sign-Off",
                "due_date": (sample_date + timedelta(days=21)).isoformat(),
            },
        )

        # 7. Accounting Core (Chart + Opening Posted Journal Entry)
        await write(
            "/accounting-settings",
            {"functional_currency": "USD"},
            method="PUT",
            expected=(200,),
        )
        bank_acc = await write(
            "/ledger-accounts",
            {
                "account_code": "1002",
                "name": "Operating Bank",
                "account_type": "asset",
            },
        )
        revenue_acc = await write(
            "/ledger-accounts",
            {
                "account_code": "6001",
                "name": "Product & Service Revenue",
                "account_type": "income",
            },
        )
        await write(
            "/journal-entries",
            {
                "posting_date": sample_date.isoformat(),
                "description": "Opening sample operating receipt",
                "status": "posted",
                "lines": [
                    {"ledger_account_id": bank_acc["id"], "debit": 15000.0},
                    {"ledger_account_id": revenue_acc["id"], "credit": 15000.0},
                ],
            },
        )

        if recovering:
            # A complete installation from before the completion event existed.
            return {"already_seeded": True}
        return {
            "already_seeded": False,
            "company": "Northwind Instruments (sample)",
            "customers": [meridian["name"], cascade["name"]],
            "products": [cal_kit["product_code"], probe["product_code"], svc_day["product_code"]],
            "quotation_id": quotation["id"],
            "sales_order_id": order["id"],
            "invoice_id": invoice["id"],
            "purchase_order_id": po["id"],
            "project_id": project["id"],
        }


def _resolve_tenant(db: Session, tenant_id: str | None) -> Tenant:
    if tenant_id:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise SystemExit(f"seed_sample: workspace {tenant_id} not found")
        return tenant
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.created_at)).all())
    if not tenants:
        raise SystemExit("seed_sample: no workspace exists yet; start the stack first")
    if len(tenants) > 1:
        raise SystemExit("seed_sample: multiple workspaces found; pass --tenant-id")
    return tenants[0]


def _ensure_admin_employee(db: Session, tenant_id: str) -> str:
    admin_user = db.scalar(
        select(User).where(User.tenant_id == tenant_id, User.role == "admin").order_by(User.created_at)
    )
    if admin_user and admin_user.employee_id:
        return str(admin_user.employee_id)

    employee = db.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.employee_code == "NW-001")
    )
    if employee is None:
        employee = Employee(
            tenant_id=tenant_id,
            employee_code="NW-001",
            name="Alex Rivera",
            email=admin_user.email if admin_user else "admin@northwind.example",
            timezone="UTC",
            status="active",
        )
        db.add(employee)
        db.flush()
    if admin_user is not None and admin_user.employee_id is None:
        admin_user.employee_id = employee.id
    return str(employee.id)


def populate_sample_workspace(db: Session, tenant_id: str) -> dict[str, Any]:
    """Load the sample records into the caller's transaction."""
    admin_employee_id = _ensure_admin_employee(db, tenant_id)
    plain_key = generate_api_key()
    temp_key = ApiKey(
        tenant_id=tenant_id,
        key_hash=hash_api_key(plain_key),
        label=EPHEMERAL_KEY_LABEL,
        role="service",
    )
    db.add(temp_key)
    db.flush()

    # Routes commit their own sessions. Savepoints leave those writes in the
    # parent transaction so first boot can roll back the workspace and fixtures
    # together if any request fails.
    request_sessions = sessionmaker(
        bind=db.connection(), autoflush=False, join_transaction_mode="create_savepoint"
    )

    def request_db():
        with request_sessions() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = request_db
    try:
        result = asyncio.run(_populate_via_api(plain_key, admin_employee_id, db, tenant_id, resume=False))
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

    db.delete(temp_key)
    record_audit(db, tenant_id=tenant_id, action=SAMPLE_COMPLETED, entity_type="tenant",
                 entity_id=tenant_id, actor="seed_sample")
    return {**result, "tenant_id": tenant_id}


def seed_sample_workspace(db: Session, tenant_id: str | None = None) -> dict[str, Any]:
    """Populate a clean sample dataset idempotently via the public API routes."""
    tenant = _resolve_tenant(db, tenant_id)
    tenant_id_str = str(tenant.id)

    if db.get_bind().dialect.name == "postgresql":
        # Serialize imports for this workspace only. The HTTP routes commit
        # independently, so keep this transaction open until the final marker.
        db.execute(text("select pg_advisory_xact_lock(hashtextextended(:name, 0))"),
                   {"name": f"sample.northwind:{tenant_id_str}"})
    if db.scalar(select(AuditLog.id).filter_by(tenant_id=tenant_id_str, action=SAMPLE_COMPLETED)):
        db.rollback()
        return {"already_seeded": True, "tenant_id": tenant_id_str}

    plain_key = generate_api_key()
    with Session(bind=db.get_bind()) as setup:
        # The old command could leave a non-expiring key on process death.
        # Reclaim its reserved service keys, never a user's personal key.
        stale_keys = delete(ApiKey).filter_by(tenant_id=tenant_id_str, label=EPHEMERAL_KEY_LABEL,
                                               role="service", user_id=None, principal_kind=PRINCIPAL_TENANT_SERVICE)
        if db.get_bind().dialect.name != "postgresql":
            # Without the workspace advisory lock, do not revoke a live retry.
            stale_keys = stale_keys.where(or_(ApiKey.expires_at.is_(None), ApiKey.expires_at <= datetime.now(timezone.utc)))
        setup.execute(stale_keys)
        admin_employee_id = _ensure_admin_employee(setup, tenant_id_str)
        temp_key = ApiKey(tenant_id=tenant_id_str, key_hash=hash_api_key(plain_key),
                          label=EPHEMERAL_KEY_LABEL, role="service",
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        setup.add(temp_key)
        setup.flush()
        key_id = temp_key.id
        setup.commit()

    override_sqlite = get_db not in app.dependency_overrides and db.get_bind().dialect.name == "sqlite"
    if override_sqlite:
        sqlite_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, future=True)

        def _override_sqlite_db():
            session = sqlite_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_sqlite_db

    try:
        summary = asyncio.run(_populate_via_api(plain_key, admin_employee_id, db, tenant_id_str))
        record_audit(db, tenant_id=tenant_id_str, action=SAMPLE_COMPLETED, entity_type="tenant",
                     entity_id=tenant_id_str, actor="seed_sample")
        summary["tenant_id"] = tenant_id_str
        return summary
    except BaseException:
        db.rollback()
        raise
    finally:
        if override_sqlite:
            app.dependency_overrides.pop(get_db, None)
        # On success, key removal and completion become visible together.
        db.execute(delete(ApiKey).where(ApiKey.tenant_id == tenant_id_str, ApiKey.id == key_id))
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed an optional fictional sample dataset")
    parser.add_argument("--tenant-id", help="Target workspace id (optional when only one exists)")
    args = parser.parse_args()

    SessionLocal = create_ops_sessionmaker()
    with SessionLocal() as db:
        result = seed_sample_workspace(db, tenant_id=args.tenant_id)

    if result.get("already_seeded"):
        print("seed_sample: sample records already present; nothing to do")
        return 0

    print("")
    print("Loaded fictional sample records (Northwind Instruments):")
    print(f"  customers: {', '.join(result['customers'])}")
    print(f"  products:  {', '.join(result['products'])}")
    print("  rules:     SALES-DISC-01 (policy), sales_quotation (approval_flow)")
    print("  records:   1 quotation, 1 sales order, 1 open invoice, 1 PO, 1 project, 1 posted JE")
    print("")
    print("Try asking your connected agent:")
    print('  - "Check our Commercial Discount Policy before quoting Meridian 12% off."')
    print('  - "Reserve inventory from Main Warehouse for the Cascade sales order."')
    print('  - "Which sales invoices are still open and unpaid?"')
    print('  - "Show the Meridian project status and our current trial balance."')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
