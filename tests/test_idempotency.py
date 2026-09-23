"""A retried write answers what the first attempt answered.

`Idempotency-Key` on any write under /api/v1 (app/core/idempotency.py):
same key + same request replays; same key + different request is a 422;
the key is scoped to the credential; a 5xx is forgotten so the retry runs.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import make_stack, provision_tenant
from app.core import idempotency
from app.models import IdempotencyRecord


@pytest.fixture()
def shop():
    with make_stack([]) as (client, engine):
        t = provision_tenant(client, company_name="Retry Co", email="admin@retry.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=admin).json()["data"]["id"]
        customer = client.post("/api/v1/customers", json={"name": "买家"}, headers=admin).json()["data"]["id"]
        yield {"client": client, "admin": admin, "employee": emp, "customer": customer,
               "order": {"employee_id": emp, "customer_id": customer, "title": "一单"}}


def test_a_retry_with_the_same_key_replays_and_writes_nothing(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    key = str(uuid.uuid4())
    first = c.post("/api/v1/sales-orders", json=shop["order"], headers={**admin, "Idempotency-Key": key})
    assert first.status_code == 201, first.text
    again = c.post("/api/v1/sales-orders", json=shop["order"], headers={**admin, "Idempotency-Key": key})
    assert again.status_code == 201 and again.headers.get("Idempotency-Replayed") == "true"
    assert again.json() == first.json(), "the replay is the first answer, byte for byte"
    assert "Idempotency-Replayed" not in first.headers
    orders = c.get("/api/v1/sales-orders", headers=admin).json()["data"]
    assert len(orders) == 1, "one document, however many times the request arrived"
    with c.session_factory() as db:
        record = db.scalar(select(IdempotencyRecord))
        assert record.status_code == 201 and record.path == "/api/v1/sales-orders" and record.completed_at is not None


def test_the_same_key_with_a_different_request_is_a_client_bug(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    key = "order-2026-09-15-001"
    assert c.post("/api/v1/sales-orders", json=shop["order"], headers={**admin, "Idempotency-Key": key}).status_code == 201
    other = c.post("/api/v1/sales-orders", json={**shop["order"], "title": "另一单"}, headers={**admin, "Idempotency-Key": key})
    assert other.status_code == 422 and other.json()["detail"][0]["type"] == "idempotency_key_reused"
    assert len(c.get("/api/v1/sales-orders", headers=admin).json()["data"]) == 1
    # same key, same body, different path: a different request too
    elsewhere = c.post("/api/v1/customers", json={"name": "x"}, headers={**admin, "Idempotency-Key": key})
    assert elsewhere.status_code == 422


def test_the_key_is_scoped_to_the_credential(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    key = "shared-key"
    assert c.post("/api/v1/customers", json={"name": "甲"}, headers={**admin, "Idempotency-Key": key}).status_code == 201
    other_tenant = provision_tenant(c, company_name="Other Co", email="admin@other.example")
    other = {"X-API-Key": other_tenant["plain_text_api_key"]}
    r = c.post("/api/v1/customers", json={"name": "乙"}, headers={**other, "Idempotency-Key": key})
    assert r.status_code == 201 and "Idempotency-Replayed" not in r.headers, "another credential's key is another key"
    assert [x["name"] for x in c.get("/api/v1/customers", headers=other).json()["data"]] == ["乙"]


def test_errors_are_replayed_too_but_a_server_error_is_not_remembered(shop, monkeypatch) -> None:
    c, admin = shop["client"], shop["admin"]
    key = "bad-order"
    bad = {**shop["order"], "customer_id": str(uuid.uuid4())}
    first = c.post("/api/v1/sales-orders", json=bad, headers={**admin, "Idempotency-Key": key})
    assert 400 <= first.status_code < 500
    again = c.post("/api/v1/sales-orders", json=bad, headers={**admin, "Idempotency-Key": key})
    assert again.status_code == first.status_code and again.headers.get("Idempotency-Replayed") == "true", \
        "a 4xx is the answer to that request; asking again gets it again without re-running"

    from app.api import sales as sales_api
    real = sales_api.require_machine_state
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(sales_api, "require_machine_state", flaky)
    try:
        failed = c.post("/api/v1/sales-orders", json=shop["order"], headers={**admin, "Idempotency-Key": "retry-me"})
        assert failed.status_code >= 500
    except RuntimeError:
        pass  # the stack may surface the exception instead of a 500; either way the claim must be gone
    with c.session_factory() as db:
        assert db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == "retry-me")) is None, \
            "a failed attempt leaves no claim: the retry must run"
    retried = c.post("/api/v1/sales-orders", json=shop["order"], headers={**admin, "Idempotency-Key": "retry-me"})
    assert retried.status_code == 201 and "Idempotency-Replayed" not in retried.headers


def test_an_in_flight_key_is_refused_and_an_expired_one_is_forgotten(shop, monkeypatch) -> None:
    c, admin = shop["client"], shop["admin"]
    with c.session_factory() as db:
        import hashlib
        scope = hashlib.sha256(("key:" + admin["X-API-Key"]).encode()).hexdigest()
        db.add(IdempotencyRecord(scope_hash=scope, key="busy", fingerprint="x", method="POST", path="/api/v1/customers"))
        db.commit()
    busy = c.post("/api/v1/customers", json={"name": "x"}, headers={**admin, "Idempotency-Key": "busy"})
    assert busy.status_code == 409

    later = idempotency._now() + idempotency.RETENTION + timedelta(minutes=1)
    monkeypatch.setattr(idempotency, "_now", lambda: later)
    fresh = c.post("/api/v1/customers", json={"name": "x"}, headers={**admin, "Idempotency-Key": "busy"})
    assert fresh.status_code == 201 and "Idempotency-Replayed" not in fresh.headers, \
        "after the retention window the key is free again"


def test_reads_anonymous_writes_and_bad_keys(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    listed = c.get("/api/v1/customers", headers={**admin, "Idempotency-Key": "ignored-on-reads"})
    assert listed.status_code == 200 and "Idempotency-Replayed" not in listed.headers
    with c.session_factory() as db:
        assert db.scalar(select(IdempotencyRecord)) is None, "reads claim nothing"
    anonymous = c.post("/api/v1/customers", json={"name": "x"}, headers={"Idempotency-Key": "no-credential"})
    assert anonymous.status_code == 401
    too_long = c.post("/api/v1/customers", json={"name": "x"}, headers={**admin, "Idempotency-Key": "k" * 201})
    assert too_long.status_code == 422 and too_long.json()["detail"][0]["type"] == "idempotency_key_invalid"


def test_the_openapi_document_names_the_header_on_every_write() -> None:
    from app.main import app
    schema = app.openapi()
    missing = []
    for path, item in schema["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method, op in item.items():
            if method.upper() in idempotency.WRITE_METHODS and not any(
                p.get("in") == "header" and p.get("name") == "Idempotency-Key" for p in op.get("parameters", [])
            ):
                missing.append(f"{method.upper()} {path}")
    assert not missing, missing
    assert not any(p.get("name") == "Idempotency-Key" for p in schema["paths"]["/api/v1/customers"]["get"].get("parameters", []))


def test_the_answer_is_stored_before_its_first_byte_leaves(shop) -> None:
    """A client that retries the instant it has the response must find the
    answer, not an in-flight claim (the live probe's 409 on v2026.9.18)."""
    import asyncio
    import json as jsonlib

    from app.db.session import get_db
    from app.main import app

    c, admin = shop["client"], shop["admin"]
    seen = {}

    async def downstream(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 201, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"data": {"ok": true}}'})

    async def send(message):
        if message["type"] == "http.response.start":
            with c.session_factory() as db:
                record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == "early-bird"))
                seen["completed"] = record is not None and record.completed_at is not None
                seen["body"] = record.response_body if record else None

    async def receive():
        return {"type": "http.request", "body": jsonlib.dumps({"name": "x"}).encode(), "more_body": False}

    middleware = idempotency.IdempotencyMiddleware(downstream, session_resolver=lambda: app.dependency_overrides.get(get_db, get_db))
    scope = {"type": "http", "method": "POST", "path": "/api/v1/customers", "query_string": b"",
             "headers": [(b"x-api-key", admin["X-API-Key"].encode()), (b"idempotency-key", b"early-bird")]}
    asyncio.run(middleware(scope, receive, send))
    assert seen == {"completed": True, "body": '{"data": {"ok": true}}'}
