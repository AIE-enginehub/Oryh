from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Invoice, JournalEntry, PurchaseOrder
from scripts import seed_sample
from scripts.ensure_standalone_tenant import ensure_standalone_tenant


def test_two_retries_finish_one_interrupted_workspace(pg_sessionmaker, clean_tables, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.edition", "standalone")

    def route_session():
        with pg_sessionmaker() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, route_session)
    with pg_sessionmaker() as db:
        tenant_id = ensure_standalone_tenant(db)["tenant_id"]

    original = seed_sample._api_call

    async def abort_after_invoice(client, method, path, payload, **kwargs):
        result = await original(client, method, path, payload, **kwargs)
        if path == "/invoices":
            raise InterruptedError("invoice committed")
        return result

    with monkeypatch.context() as patch, pg_sessionmaker() as db:
        patch.setattr(seed_sample, "_api_call", abort_after_invoice)
        with pytest.raises(InterruptedError, match="invoice committed"):
            seed_sample.seed_sample_workspace(db, tenant_id)

    start = Barrier(2)

    def retry():
        with pg_sessionmaker() as db:
            start.wait(timeout=10)
            return seed_sample.seed_sample_workspace(db, tenant_id)["already_seeded"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(retry) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [False, True]

    with pg_sessionmaker() as db:
        for model in (Invoice, PurchaseOrder, JournalEntry):
            assert db.scalar(select(func.count()).select_from(model).filter_by(tenant_id=tenant_id)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).filter_by(
            tenant_id=tenant_id, action=seed_sample.SAMPLE_COMPLETED)) == 1
