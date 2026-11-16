#!/usr/bin/env python3
"""Load a cohesive fictional sample company ('Northwind Instruments') for evaluators.

Unlike `ensure_standalone_tenant.py` (which creates an empty workspace on first
boot), this script is optional and idempotent: operators who want a realistic
starting dataset to test AI agents against can run:

    docker compose exec api python scripts/seed_sample.py

All records are written through the real FastAPI routes using a short-lived
service API key that is deleted in a `finally` block before returning.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import create_ops_sessionmaker, get_db
from app.main import app
from app.models import (
    ApiKey,
    Employee,
    Product,
    Tenant,
    User,
    generate_api_key,
    hash_api_key,
)

SAMPLE_SENTINEL_CODE = "NW-CAL-100"
EPHEMERAL_KEY_LABEL = "_seed_sample_ephemeral"


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


async def _populate_via_api(
    api_key: str,
    admin_employee_id: str,
) -> dict[str, Any]:
    today = date.today()
    headers = {"X-API-Key": api_key}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://oryh.local",
        headers=headers,
        timeout=30.0,
    ) as client:
        # 1. Colleagues
        priya = await _api_call(
            client,
            "POST",
            "/employees",
            {
                "employee_code": "NW-002",
                "name": "Priya Nair",
                "email": "priya@northwind.example",
                "timezone": "UTC",
                "metadata": {"department": "Sales", "title": "Account Lead"},
            },
        )
        daniel = await _api_call(
            client,
            "POST",
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
        await _api_call(
            client,
            "POST",
            "/facilities",
            {
                "facility_code": "WH-MAIN",
                "name": "Main Warehouse",
                "facility_type": "warehouse",
                "address": "410 Harbor Way, Seattle, WA",
            },
        )
        meridian = await _api_call(
            client,
            "POST",
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
        cascade = await _api_call(
            client,
            "POST",
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
        apex = await _api_call(
            client,
            "POST",
            "/vendors",
            {
                "vendor_code": "VEND-APEX",
                "name": "Apex Precision Sensors",
                "contact": "Kenji Sato",
                "email": "supply@apex-sensors.example",
            },
        )
        await _api_call(
            client,
            "POST",
            "/vendors",
            {
                "vendor_code": "VEND-PAC",
                "name": "Pacific Packaging Co",
                "contact": "Elena Ortiz",
                "email": "desk@pacific-pack.example",
            },
        )

        # 3. Products & Opening Inventory
        cal_kit = await _api_call(
            client,
            "POST",
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
        probe = await _api_call(
            client,
            "POST",
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
        svc_day = await _api_call(
            client,
            "POST",
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
        await _api_call(
            client,
            "POST",
            "/inventory-items",
            {
                "product_id": cal_kit["id"],
                "facility": "Main Warehouse",
                "currency": "USD",
                "unit_cost": 740.0,
                "initial_quantity": 45,
                "initial_description": "Opening sample warehouse balance",
            },
        )
        await _api_call(
            client,
            "POST",
            "/inventory-items",
            {
                "product_id": probe["id"],
                "facility": "Main Warehouse",
                "currency": "USD",
                "unit_cost": 135.0,
                "initial_quantity": 120,
                "initial_description": "Opening sample warehouse balance",
            },
        )

        # 4. Published Natural-Language Business Rules
        discount_draft = await _api_call(
            client,
            "POST",
            "/business-rules",
            {
                "kind": "policy",
                "code": "SALES-DISC-01",
                "category": "finance",
                "title": "Commercial Discount Policy",
                "effective_from": f"{today.year}-01-01",
                "body": (
                    "Standard list discounts up to 8% may be offered by the account owner. "
                    "Discounts above 8% up to 15% require operations review; anything above 15% "
                    "requires a signed annual price agreement."
                ),
            },
        )
        await _api_call(
            client,
            "POST",
            f"/business-rules/{discount_draft['id']}/publish",
            {"effective_from": f"{today.year}-01-01"},
            expected=(200,),
        )
        await _api_call(
            client,
            "POST",
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
        quotation = await _api_call(
            client,
            "POST",
            "/sales-quotations",
            {
                "employee_id": priya["id"],
                "customer_id": meridian["id"],
                "title": "Meridian Annual Calibration Package",
                "quote_date": today.isoformat(),
                "valid_until": (today + timedelta(days=30)).isoformat(),
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
        order = await _api_call(
            client,
            "POST",
            "/sales-orders",
            {
                "employee_id": priya["id"],
                "customer_id": cascade["id"],
                "title": "Cascade Q4 Calibration Supply",
                "order_date": today.isoformat(),
                "promised_date": (today + timedelta(days=7)).isoformat(),
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
        invoice = await _api_call(
            client,
            "POST",
            "/invoices",
            {
                "direction": "sales",
                "employee_id": daniel["id"],
                "customer_id": cascade["id"],
                "title": "Cascade Q4 Calibration Supply",
                "invoice_date": today.isoformat(),
                "due_date": (today + timedelta(days=15)).isoformat(),
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
        await _api_call(client, "POST", f"/invoices/{invoice['id']}/submit", {}, expected=(200,))

        po = await _api_call(
            client,
            "POST",
            "/purchase-orders",
            {
                "employee_id": admin_employee_id,
                "vendor_id": apex["id"],
                "title": "Sensor Batch Replenishment",
                "order_date": today.isoformat(),
                "promised_date": (today + timedelta(days=14)).isoformat(),
                "status": "confirmed",
                "currency": "USD",
                "total_amount": 4800.0,
            },
        )

        # 6. Project Execution
        project = await _api_call(
            client,
            "POST",
            "/projects",
            {
                "project_code": "PRJ-MERIDIAN",
                "project_name": "Meridian Calibration Rollout",
            },
        )
        await _api_call(
            client,
            "POST",
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
        await _api_call(
            client,
            "POST",
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
        await _api_call(
            client,
            "POST",
            "/project-milestones",
            {
                "project_id": project["id"],
                "name": "Customer Sign-Off",
                "due_date": (today + timedelta(days=21)).isoformat(),
            },
        )

        # 7. Accounting Core (Chart + Opening Posted Journal Entry)
        await _api_call(
            client,
            "PUT",
            "/accounting-settings",
            {"functional_currency": "USD"},
            expected=(200,),
        )
        bank_acc = await _api_call(
            client,
            "POST",
            "/ledger-accounts",
            {
                "account_code": "1002",
                "name": "Operating Bank",
                "account_type": "asset",
            },
        )
        revenue_acc = await _api_call(
            client,
            "POST",
            "/ledger-accounts",
            {
                "account_code": "6001",
                "name": "Product & Service Revenue",
                "account_type": "income",
            },
        )
        await _api_call(
            client,
            "POST",
            "/journal-entries",
            {
                "posting_date": today.isoformat(),
                "description": "Opening sample operating receipt",
                "status": "posted",
                "lines": [
                    {"ledger_account_id": bank_acc["id"], "debit": 15000.0},
                    {"ledger_account_id": revenue_acc["id"], "credit": 15000.0},
                ],
            },
        )

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


def seed_sample_workspace(db: Session, tenant_id: str | None = None) -> dict[str, Any]:
    """Populate a clean sample dataset idempotently via the public API routes."""
    tenant = _resolve_tenant(db, tenant_id)
    tenant_id_str = str(tenant.id)

    if db.scalar(
        select(Product.id).where(
            Product.tenant_id == tenant_id_str,
            Product.product_code == SAMPLE_SENTINEL_CODE,
        )
    ):
        return {"already_seeded": True, "tenant_id": tenant_id_str}

    admin_employee_id = _ensure_admin_employee(db, tenant_id_str)
    plain_key = generate_api_key()
    temp_key = ApiKey(
        tenant_id=tenant_id_str,
        key_hash=hash_api_key(plain_key),
        label=EPHEMERAL_KEY_LABEL,
        role="service",
    )
    db.add(temp_key)
    db.commit()

    had_override = get_db in app.dependency_overrides
    if not had_override and db.get_bind().dialect.name == "sqlite":
        sqlite_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, future=True)

        def _override_sqlite_db():
            session = sqlite_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_sqlite_db

    try:
        summary = asyncio.run(_populate_via_api(plain_key, admin_employee_id))
        summary["tenant_id"] = tenant_id_str
        return summary
    finally:
        if not had_override and get_db in app.dependency_overrides:
            app.dependency_overrides.pop(get_db, None)
        db.execute(
            delete(ApiKey).where(
                ApiKey.tenant_id == tenant_id_str,
                ApiKey.label == EPHEMERAL_KEY_LABEL,
            )
        )
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
