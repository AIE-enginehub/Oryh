"""Tests for the optional evaluator sample workspace seeder."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from fnmatch import fnmatchcase

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import (
    ApiKey, AuditLog, BusinessRule, Employee, InventoryItemDetail, Invoice, JournalEntry, Product, Project,
    ProjectMilestone, ProjectTask, PurchaseOrder, SalesOrder, SalesQuotation, Tenant,
)
from conftest import make_stack
from scripts import seed_sample
from scripts.ensure_standalone_tenant import ensure_standalone_tenant
from scripts.seed_sample import EPHEMERAL_KEY_LABEL, SAMPLE_SENTINEL_CODE, seed_sample_workspace


def test_seed_sample_populates_fictional_records_and_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.edition", "standalone")

    with make_stack() as (client, _engine):
        with client.session_factory() as db:
            created = ensure_standalone_tenant(db)
            assert created is not None
            tenant_id = created["tenant_id"]

        with client.session_factory() as db:
            first = seed_sample_workspace(db, tenant_id=tenant_id)
            assert first["already_seeded"] is False
            assert first["tenant_id"] == tenant_id

        with client.session_factory() as db:
            assert db.scalar(
                select(Product).where(Product.tenant_id == tenant_id, Product.product_code == SAMPLE_SENTINEL_CODE)
            ) is not None
            assert len(db.scalars(select(SalesQuotation).where(SalesQuotation.tenant_id == tenant_id)).all()) == 1
            assert len(db.scalars(select(SalesOrder).where(SalesOrder.tenant_id == tenant_id)).all()) == 1
            assert len(db.scalars(select(Invoice).where(Invoice.tenant_id == tenant_id)).all()) == 1
            assert len(db.scalars(select(Project).where(Project.tenant_id == tenant_id)).all()) == 1
            assert len(db.scalars(select(JournalEntry).where(JournalEntry.tenant_id == tenant_id)).all()) == 1
            assert len(
                db.scalars(
                    select(BusinessRule).where(BusinessRule.tenant_id == tenant_id, BusinessRule.status == "published")
                ).all()
            ) == 2
            assert (
                db.scalar(
                    select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.label == EPHEMERAL_KEY_LABEL)
                )
                is None
            )

        with client.session_factory() as db:
            second = seed_sample_workspace(db, tenant_id=tenant_id)
            assert second == {"already_seeded": True, "tenant_id": tenant_id}


@pytest.mark.parametrize("stop_after", [
    "/employees", "/products", "/business-rules", "/invoices", "/invoices/*/submit", "/journal-entries",
])
def test_rerun_recovers_committed_prefix_even_when_a_response_was_lost(monkeypatch, stop_after) -> None:
    monkeypatch.setattr("app.core.config.settings.edition", "standalone")
    original = seed_sample._api_call
    committed = []
    interrupted = False

    async def interrupt_after_commit(client, method, path, payload, **kwargs):
        nonlocal interrupted
        result = await original(client, method, path, payload, **kwargs)
        committed.append((method, path, json.dumps(payload, sort_keys=True)))
        if not interrupted and fnmatchcase(path, stop_after):
            interrupted = True
            raise RuntimeError("response lost after commit")
        return result

    monkeypatch.setattr(seed_sample, "_api_call", interrupt_after_commit)
    with make_stack() as (client, _engine):
        with client.session_factory() as db:
            tenant_id = ensure_standalone_tenant(db)["tenant_id"]
            with pytest.raises(RuntimeError, match="response lost"):
                seed_sample_workspace(db, tenant_id)
        with client.session_factory() as db:
            assert not db.scalar(select(AuditLog.id).filter_by(tenant_id=tenant_id, action=seed_sample.SAMPLE_COMPLETED))
            if stop_after == "/employees":
                # Simulate returning to an import started in a previous year.
                db.scalars(select(Employee).filter_by(tenant_id=tenant_id, employee_code="NW-002")).one().created_at = (
                    datetime(2024, 12, 31, tzinfo=timezone.utc))
                db.add(ApiKey(tenant_id=tenant_id, key_hash="0" * 64, role="service", label=EPHEMERAL_KEY_LABEL))
                db.commit()
            seed_sample_workspace(db, tenant_id)
        with client.session_factory() as db:
            assert seed_sample_workspace(db, tenant_id) == {"already_seeded": True, "tenant_id": tenant_id}
            assert len(committed) == len(set(committed)), "no committed request may be replayed"
            for model, expected in [
                (InventoryItemDetail, 2), (SalesQuotation, 1), (SalesOrder, 1), (Invoice, 1), (PurchaseOrder, 1),
                (ProjectTask, 2), (ProjectMilestone, 1), (JournalEntry, 1),
            ]:
                assert db.scalar(select(func.count()).select_from(model).filter_by(tenant_id=tenant_id)) == expected
            assert db.scalar(select(Invoice.status).filter_by(tenant_id=tenant_id)) == "submitted"
            if stop_after == "/employees":
                assert db.scalar(select(SalesQuotation.quote_date).filter_by(tenant_id=tenant_id)) == date(2024, 12, 31)
                assert db.scalar(select(JournalEntry.posting_date).filter_by(tenant_id=tenant_id)) == date(2024, 12, 31)
            assert db.scalar(select(func.count()).select_from(BusinessRule).filter_by(
                tenant_id=tenant_id, status="published")) == 2
            assert not db.scalar(select(ApiKey.id).filter_by(tenant_id=tenant_id, label=EPHEMERAL_KEY_LABEL))


def test_demo_bootstrap_retries_after_a_partial_seed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "edition", "standalone")
    monkeypatch.setattr(settings, "standalone_company_name", "")
    monkeypatch.setattr(settings, "standalone_seed_sample", True)
    api_call = seed_sample._api_call

    async def fail_after_product(client, method, path, payload=None, **kwargs):
        result = await api_call(client, method, path, payload, **kwargs)
        if path == "/products":
            raise RuntimeError("sample load interrupted")
        return result

    with make_stack() as (client, _engine):
        with monkeypatch.context() as interrupted:
            interrupted.setattr(seed_sample, "_api_call", fail_after_product)
            with client.session_factory() as db, pytest.raises(RuntimeError, match="sample load interrupted"):
                ensure_standalone_tenant(db)

        with client.session_factory() as db:
            for model in (Tenant, Product, ApiKey):
                assert db.scalar(select(func.count()).select_from(model)) == 0
            created = ensure_standalone_tenant(db)
            assert created is not None
            assert created["company_name"] == "Northwind Instruments"

        with client.session_factory() as db:
            assert ensure_standalone_tenant(db) is None
            assert db.scalar(select(func.count()).select_from(Tenant)) == 1
            assert db.scalar(select(func.count()).select_from(SalesQuotation)) == 1
            assert db.scalar(select(func.count()).select_from(ApiKey)) == 1


def test_demo_setting_does_not_seed_an_existing_workspace(monkeypatch) -> None:
    monkeypatch.setattr(settings, "standalone_company_name", "Existing Company")
    monkeypatch.setattr(settings, "standalone_seed_sample", False)
    with make_stack() as (client, _engine):
        with client.session_factory() as db:
            created = ensure_standalone_tenant(db)
            assert created is not None
            assert created["company_name"] == "Existing Company"

        monkeypatch.setattr(settings, "standalone_seed_sample", True)
        with client.session_factory() as db:
            assert ensure_standalone_tenant(db) is None
            assert db.scalar(select(func.count()).select_from(Product)) == 0
            assert db.scalar(select(Tenant.name)) == "Existing Company"
