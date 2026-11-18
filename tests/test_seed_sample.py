"""Tests for the standalone demo workspace and manual sample import."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import ApiKey, BusinessRule, Invoice, JournalEntry, Product, Project, SalesOrder, SalesQuotation, Tenant
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
