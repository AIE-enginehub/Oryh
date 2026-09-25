"""Every write takes an `Idempotency-Key`; a retry answers what the first
attempt answered.

An agent whose POST timed out after the server committed has one safe move
without this: read back and guess whether the order it meant to create is
the one it sees. With the header, it sends the same request with the same
key and receives the same response — status, body, `Idempotency-Replayed:
true` — and nothing is written twice. Money-moving endpoints already carry
a body-level `idempotency_key` bound to their business rows; this is the
general rule for the rest, at the edge of the API, one place.

The contract (the shape Stripe made conventional):

* Scope: the credential the request presents — API key, bearer, or browser
  session — so two tenants, or two people, can use the same key text
  without meeting. A request with no credential is passed through; its
  write will be refused by auth anyway.
* Same key, same request (method, path, query, body): the stored response
  is replayed, for 24 hours.
* Same key, a different request: 422 `idempotency_key_reused` — the client
  has a bug, and silently answering the first request's result would hide
  it.
* Same key while the first attempt is still running: 409 — wait and retry
  with the same key.
* A 5xx is not remembered: the retry runs again, which is the point of
  retrying.

Pure ASGI (like the other middlewares here), so it sees the raw body and
the raw response, and needs no cooperation from any handler — except one:
an answer that must not be kept (a minted key) says `Idempotency-Replayable:
false`, and the retry is told the first attempt completed, not the secret.

The claim and the settle are three short statements each and run on the
event loop on purpose. Moved to a worker thread, they overlapped with the
request's own session being closed on another thread — harmless on a pooled
database, but on the test stack's single shared connection a rollback from
one thread swallowed the settle's UPDATE from the other, one run in two.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.browser_auth import SESSION_COOKIE
from app.core.config import API_PREFIX
from app.models import IdempotencyRecord

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotency-Replayed"
# A handler whose answer must not be kept (a minted key, a bundle with a key
# inside) says so with this response header; the client sees it too.
REPLAYABLE_HEADER = "Idempotency-Replayable"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
KEY_MAX_LENGTH = 200
RETENTION = timedelta(hours=24)
# An attempt that never reported back (process killed mid-request) must not
# hold its key forever; after this long a retry takes the key over.
IN_FLIGHT_GRACE = timedelta(minutes=5)
# expired rows are swept on a claim, at most this often — not on every one
PURGE_INTERVAL = timedelta(minutes=1)
_KEPT_RESPONSE_HEADERS = (b"content-type", b"location")
# An answer marked `Idempotency-Replayable: false` (a minted key, a bundle
# with a key inside) or one that is not text is completed but not kept: the
# retry learns that the first attempt finished, never the secret it carried.
NOT_REPLAYABLE = (
    "the first attempt with this Idempotency-Key completed, but its answer is not kept for replay — "
    "it carried a credential shown once, or bytes that are not text. If you did not receive it, "
    "revoke what it issued and send a new request with a new key"
)
log = logging.getLogger(__name__)
_last_purge: datetime | None = None


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def _credential(headers: dict[str, str]) -> str | None:
    """What the request authenticates with — never stored, only hashed into
    the scope. Precedence mirrors app.api.deps: key, bearer, session."""
    if headers.get("x-api-key"):
        return "key:" + headers["x-api-key"].strip()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return "bearer:" + auth[7:].strip()
    cookie = headers.get("cookie", "")
    for part in cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE and value:
            return "session:" + value
    return None


def _json_response(status: int, detail) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    return status, [(b"content-type", b"application/json"), (b"cache-control", b"no-store")], body


class IdempotencyMiddleware:
    def __init__(self, app, session_resolver: Callable[[], Callable[[], Iterator[Session]]]):
        self.app = app
        # Resolved per request so the test stack's `get_db` override is what
        # the middleware writes through, the same as every handler.
        self.session_resolver = session_resolver

    @contextmanager
    def _session(self) -> Iterator[Session]:
        gen = self.session_resolver()()
        db = next(gen)
        try:
            yield db
        finally:
            gen.close()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in WRITE_METHODS \
                or not scope.get("path", "").startswith(f"{API_PREFIX}/"):
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        key = headers.get(HEADER.lower())
        if key is None:
            await self.app(scope, receive, send)
            return
        key = key.strip()
        if not key or len(key) > KEY_MAX_LENGTH or not key.isprintable():
            await self._reply(send, *_json_response(422, [{
                "type": "idempotency_key_invalid", "loc": ["header", HEADER],
                "msg": f"{HEADER} must be 1–{KEY_MAX_LENGTH} printable characters", "input": key[:KEY_MAX_LENGTH]}]))
            return
        credential = _credential(headers)
        if credential is None:
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        scope_hash = hashlib.sha256(credential.encode("utf-8")).hexdigest()
        fingerprint = hashlib.sha256(b"\x00".join([
            scope["method"].encode(), scope["path"].encode(), scope.get("query_string", b""), body,
        ])).hexdigest()

        verdict = self._claim_in_session(scope_hash, key, fingerprint, scope["method"], scope["path"])
        if verdict[0] == "replay":
            record = verdict[1]
            stored = json.loads(record.response_headers or "[]")
            response_headers = [(n.encode("latin-1"), v.encode("latin-1")) for n, v in stored]
            response_headers.append((REPLAYED_HEADER.lower().encode(), b"true"))
            await self._reply(send, record.status_code, response_headers, (record.response_body or "").encode("utf-8"))
            return
        if verdict[0] == "refuse":
            await self._reply(send, *verdict[1])
            return
        record_id = verdict[1]

        replay_receive = _replay(body)
        held: list[dict] = []
        state = {"status": None, "headers": [], "chunks": [], "settled": False, "no_store": False}

        async def capture(message):
            # The answer is stored BEFORE its first byte leaves. Stored after
            # (the first cut), a client that retried the instant it had the
            # response could arrive while the claim still read "in flight" and
            # be told 409 — found by the live probe on v2026.9.18, where the
            # retry follows the response within a millisecond.
            if state["settled"]:
                await send(message)
                return
            held.append(message)
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                headers = message.get("headers") or []
                state["headers"] = [(n, v) for n, v in headers if n.lower() in _KEPT_RESPONSE_HEADERS]
                state["no_store"] = any(
                    n.lower() == REPLAYABLE_HEADER.lower().encode() and v.strip().lower() == b"false" for n, v in headers
                )
                return
            if message["type"] == "http.response.body":
                state["chunks"].append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                try:
                    self._settle(record_id, state)
                except Exception:
                    # the write below may already be committed: the claim
                    # stays in flight rather than being forgotten, so a retry
                    # is told to wait instead of running the write again
                    log.exception("idempotency: the answer for claim %s could not be stored", record_id)
                state["settled"] = True
                for queued in held:
                    await send(queued)
                held.clear()

        try:
            await self.app(scope, replay_receive, capture)
        except BaseException:
            if not state["settled"]:
                self._forget(record_id)
            raise
        if not state["settled"]:
            # the app ended without a final body chunk: nothing to remember
            self._forget(record_id)
            for queued in held:
                await send(queued)

    def _settle(self, record_id: str, state: dict) -> None:
        status = state["status"]
        if status is None or status >= 500:
            self._forget(record_id)
            return
        headers, body = state["headers"], b"".join(state["chunks"])
        try:
            text = body.decode("utf-8") if not state["no_store"] else None
        except UnicodeDecodeError:
            text = None
        if text is None:
            status, headers, body = _json_response(409, NOT_REPLAYABLE)
            text = body.decode("utf-8")
        with self._session() as db:
            record = db.get(IdempotencyRecord, record_id)
            if record is not None:
                record.status_code = status
                record.response_headers = json.dumps([(n.decode("latin-1"), v.decode("latin-1")) for n, v in headers])
                record.response_body = text
                record.completed_at = _now()
                db.commit()

    def _claim_in_session(self, *args):
        with self._session() as db:
            return self._claim(db, *args)

    def _claim(self, db: Session, scope_hash: str, key: str, fingerprint: str, method: str, path: str):
        global _last_purge
        now = _now()
        if _last_purge is None or now - _last_purge >= PURGE_INTERVAL:
            db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < now - RETENTION))
            db.commit()
            _last_purge = now
        existing = db.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.scope_hash == scope_hash, IdempotencyRecord.key == key))
        if existing is not None and _utc(existing.created_at) < now - RETENTION:
            # past retention but not yet swept: the key is free again
            db.delete(existing)
            db.commit()
            existing = None
        if existing is None:
            record = IdempotencyRecord(scope_hash=scope_hash, key=key, fingerprint=fingerprint, method=method, path=path)
            db.add(record)
            try:
                db.commit()
                return ("run", record.id)
            except IntegrityError:
                db.rollback()
                existing = db.scalar(select(IdempotencyRecord).where(
                    IdempotencyRecord.scope_hash == scope_hash, IdempotencyRecord.key == key))
        if existing.completed_at is None:
            if _utc(existing.created_at) > now - IN_FLIGHT_GRACE:
                return ("refuse", _json_response(409, f"a request with this {HEADER} is still being processed; retry with the same key"))
            if existing.fingerprint != fingerprint:
                # a stale claim is taken over only by the same request: the
                # key never becomes a way to run a different one
                return ("refuse", _json_response(422, [{
                    "type": "idempotency_key_reused", "loc": ["header", HEADER],
                    "msg": f"{HEADER} was already used for a different request; a new request takes a new key", "input": key}]))
            existing.created_at = now
            db.commit()
            return ("run", existing.id)
        if existing.fingerprint != fingerprint:
            return ("refuse", _json_response(422, [{
                "type": "idempotency_key_reused", "loc": ["header", HEADER],
                "msg": f"{HEADER} was already used for a different request; a new request takes a new key", "input": key}]))
        return ("replay", existing)

    def _forget(self, record_id: str) -> None:
        with self._session() as db:
            db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.id == record_id))
            db.commit()

    @staticmethod
    async def _reply(send, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
        headers = list(headers) + [(b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def openapi_with_idempotency_key(schema: dict) -> dict:
    """Every write operation under the API prefix documents the header, so a
    generated client and a skill contract see it where they see the body."""
    parameter = {
        "name": HEADER, "in": "header", "required": False,
        "schema": {"type": "string", "minLength": 1, "maxLength": KEY_MAX_LENGTH},
        "description": (
            "A client-chosen token for this write (a UUID will do). Retrying with the same key "
            "replays the first attempt's response instead of writing again; the same key with a "
            "different request is refused (422). Scoped to the credential, kept 24 hours."
        ),
    }
    for path, item in schema.get("paths", {}).items():
        if not path.startswith(f"{API_PREFIX}/"):
            continue
        for method, op in item.items():
            if method.upper() not in WRITE_METHODS or not isinstance(op, dict):
                continue
            params = op.setdefault("parameters", [])
            if not any(p.get("name") == HEADER and p.get("in") == "header" for p in params):
                params.append(parameter)
    return schema
