"""Tests for the optional evaluator sample workspace seeder."""

from __future__ import annotations

from sqlalchemy import select

from app.models import ApiKey, BusinessRule, Invoice, JournalEntry, Product, Project, SalesOrder, SalesQuotation
from conftest import make_stack
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
