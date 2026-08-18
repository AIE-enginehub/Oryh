"""Every content change to a tenant's records leaves a trail, automatically.

The trail used to be written by hand, one `record_audit` call at a time, and it
covered the FLOW: submissions, approvals, status changes, todos. What it did not
cover was the CONTENT — 115 of 195 write endpoints recorded nothing at all, so a
customer created by an agent, a price edited, an order line changed, or an
employee added left the database changed and the log silent. "Who changed this
price, and from what" had no answer.

Doing that by hand means 115 edits and a 116th endpoint that is silent again the
day someone adds it. So this listens at the ORM instead: any INSERT, UPDATE or
DELETE on a tenant-scoped table appends its own audit row inside the SAME flush,
which means the trail commits if and only if the business write commits.

Two deliberate boundaries:

  * It records the DELTA, not the result. Finding F25 settled that on the roles
    endpoint — a log carrying only post-change state answers "what does this say
    now", never "what did they take away". Every entry here carries `before` and
    `after` per changed field.
  * It never copies a secret. `password_hash`, `key_hash` and their kin are
    recorded as changed, with their values replaced — the trail says an API key
    was rotated without becoming a second place the hash lives.

The hand-written `record_audit` calls stay exactly as they are. They carry
meaning this cannot infer — `quotation.status_changed`, `approval.recorded` —
and sit above the mechanical layer rather than being replaced by it.
"""

from __future__ import annotations

import contextlib
import datetime
import functools
import decimal
import enum
import re
import uuid
from typing import Any

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models import AuditLog

# Columns whose VALUE must never reach the trail. The change is still recorded —
# a rotated credential is exactly the kind of event a trail exists for — but the
# value is replaced, so audit_logs never becomes a second home for a hash.
SECRET_COLUMN = re.compile(r"password|token|secret|hash|salt|private", re.I)
REDACTED = "«redacted»"

# Noise and recursion. `audit_logs` would audit its own inserts; sessions and
# device authorizations are short-lived machinery that turns over constantly and
# says nothing about the business records anyone is trying to trace.
NEVER_AUDITED = {"audit_logs", "user_sessions", "device_authorizations"}

# Bookkeeping the ORM touches on nearly every write; recording them would bury
# the fields a reader actually came for.
IGNORED_COLUMNS = {"updated_at", "created_at"}


def _jsonable(value: Any) -> Any:
    """audit_logs.detail_jsonb is JSON; ORM values are not always."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        # str, not float: a price is exactly what it was, not the nearest double.
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return _jsonable(value.value)
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _entity_name(table: str) -> str:
    """`sales_quotation_items` → `sales_quotation_item`, to sit beside the
    hand-written entries, which name a thing rather than a table."""
    return table[:-1] if table.endswith("s") and not table.endswith("ss") else table


def _auditable(instance: object) -> bool:
    table = getattr(instance, "__tablename__", None)
    if table is None or table in NEVER_AUDITED:
        return False
    if not hasattr(instance, "tenant_id") or not hasattr(instance, "id"):
        return False
    return getattr(instance, "tenant_id", None) is not None


def _ensure_id(instance: object) -> str | None:
    """The id of a row being INSERTed, resolved before the INSERT.

    Ids come from a Python-side column default, which SQLAlchemy applies while
    emitting the statement — after this listener has run. So a new row's `id`
    is still None here, and an entry built from it fails the NOT NULL on
    `audit_logs.entity_id`, taking the business write down with it. Resolving
    the default now assigns the same id the INSERT will carry, so the trail
    points at the row rather than at nothing.
    """
    current = getattr(instance, "id", None)
    if current is not None:
        return current
    column = sa_inspect(type(instance)).columns.get("id")
    default = getattr(column, "default", None) if column is not None else None
    if default is None or not getattr(default, "is_callable", False):
        return None
    generated = default.arg({})
    instance.id = generated
    return generated


def _attribute_names(instance: object) -> list[str]:
    """Mapped ATTRIBUTE names, not column names.

    They differ more often than they look: `queue_filter` is stored in
    `queue_filter_jsonb`, `metadata` in `metadata_jsonb`. Reading the column
    name and then asking `state.attrs[...]` for it raises KeyError — it crashed
    every write to those models — and `getattr` would quietly return nothing,
    dropping the field from the trail without a word. The attribute name is
    also what the API exposes, so the trail reads the way the record does.
    """
    return [attribute.key for attribute in sa_inspect(type(instance)).mapper.column_attrs]


def _created_detail(instance: object) -> dict:
    fields = {}
    for name in _attribute_names(instance):
        if name in IGNORED_COLUMNS or name in ("id", "tenant_id"):
            continue
        value = getattr(instance, name, None)
        if value is None:
            continue
        fields[name] = REDACTED if SECRET_COLUMN.search(name) else _jsonable(value)
    return {"fields": fields}


def _changed_detail(instance: object) -> dict | None:
    """before/after per changed field, or None when nothing meaningful moved."""
    state = sa_inspect(instance)
    changes: dict[str, dict] = {}
    for name in _attribute_names(instance):
        if name in IGNORED_COLUMNS:
            continue
        history = state.attrs[name].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        if before == after:
            continue
        if SECRET_COLUMN.search(name):
            changes[name] = {"before": REDACTED, "after": REDACTED}
        else:
            before, after = _matched(before, after)
            changes[name] = {"before": _jsonable(before), "after": _jsonable(after)}
    return {"changes": changes} if changes else None


def _matched(before: Any, after: Any) -> tuple[Any, Any]:
    """Put both sides of a money change in the same units.

    `before` is what the database held — a Decimal with the column's scale.
    `after` is what the request assigned, and has not been near the database
    yet, so a JSON `96.50` arrives as the float `96.5`. Recorded as they come,
    the entry reads `88.00 → 96.5`, which invites the reader to wonder whether
    a digit was lost. It was not; only the two sides were measured differently.
    """
    if isinstance(before, decimal.Decimal) and isinstance(after, (int, float)):
        return before, decimal.Decimal(str(after)).quantize(before)
    if isinstance(after, decimal.Decimal) and isinstance(before, (int, float)):
        return decimal.Decimal(str(before)).quantize(after), after
    return before, after


def _deleted_detail(instance: object) -> dict:
    fields = {}
    for name in _attribute_names(instance):
        if name in IGNORED_COLUMNS or name in ("id", "tenant_id"):
            continue
        value = getattr(instance, name, None)
        if value is None:
            continue
        fields[name] = REDACTED if SECRET_COLUMN.search(name) else _jsonable(value)
    return {"fields": fields}


def _pending(instance: object, verb: str, detail: dict, actor: str | None) -> dict | None:
    """The values for an entry, held until commit decides whether to write it."""
    entity_id = _ensure_id(instance)
    if entity_id is None:
        # Nothing to point at. Better a missing entry than a failed business
        # write: this listener must never be the reason a customer is not saved.
        return None
    entity = _entity_name(instance.__tablename__)
    return {
        "tenant_id": instance.tenant_id,
        "action": f"{entity}.{verb}",
        "entity_type": entity,
        "entity_id": entity_id,
        "actor": actor,
        "detail_jsonb": {"source": "orm", **detail},
    }


def catalogue_write(function):
    """Marks a function that writes the SHIPPED catalogue, not a tenant's work.

    The catalogue is 111 type options, the capabilities, the system roles, the
    product skills — none of it anyone's decision about their business. Trailed,
    a new workspace opens with several hundred entries and the tenant's first
    real change is buried under them.

    Applied per function rather than to the aggregate that calls them, because
    the aggregate is not the only caller: `scripts/sync_tenant_defaults.py`
    invokes them directly, which is how a live workspace ended up holding 200
    entries for work nobody in it had done. What a tenant later does TO the
    catalogue is their decision, and is recorded normally.

    Lives here rather than in `provisioning`, which cannot host it: it imports
    `flow_subscriptions`, and that module needs the decorator too.
    """

    @functools.wraps(function)
    def wrapper(session: Session, *args, **kwargs):
        with suppressed(session):
            return function(session, *args, **kwargs)

    return wrapper


def _append(pending: list, values: dict | None) -> None:
    if values is not None:
        pending.append(values)


@contextlib.contextmanager
def suppressed(session: Session):
    """Don't trail these writes.

    For provisioning a workspace, which inserts the shipped catalogue —
    111 type options, the capabilities, the system roles, the product skills.
    None of it is anyone's decision about their business, and recording it
    buries the first real change under a hundred rows nobody asked for.
    """
    previous = session.info.get("audit_suppressed", False)
    session.info["audit_suppressed"] = True
    try:
        yield
    finally:
        session.info["audit_suppressed"] = previous


def _gather(session: Session, *_: object) -> None:
    """Collect what changed, while the ORM still remembers what it was.

    Deltas have to be read HERE — after the flush, attribute history is gone.
    But whether an entry survives cannot be decided here, because the common
    endpoint shape is `db.add(...)`, `db.flush()`, then `record_audit(...)`:
    the hand-written entry does not exist yet at the moment this runs, and
    writing now produces two rows for one act. So this only gathers; the
    decision is made at commit, once every `record_audit` call has been made.
    """
    if session.info.get("audit_suppressed"):
        return
    actor = session.info.get("audit_actor")
    pending = session.info.setdefault("audit_pending", [])
    claimed = session.info.setdefault("audit_semantic", set())

    for entry in session.new:
        if isinstance(entry, AuditLog):
            claimed.add((entry.entity_type, entry.entity_id))

    for instance in session.new:
        if _auditable(instance):
            _append(pending, _pending(instance, "created", _created_detail(instance), actor))

    for instance in session.dirty:
        if not _auditable(instance) or not session.is_modified(instance):
            continue
        detail = _changed_detail(instance)
        if detail is not None:
            _append(pending, _pending(instance, "updated", detail, actor))

    for instance in session.deleted:
        if _auditable(instance):
            _append(pending, _pending(instance, "deleted", _deleted_detail(instance), actor))


def _emit(session: Session) -> None:
    """Write the gathered entries, minus whatever the semantic layer claimed.

    Where a `record_audit` call exists it carries meaning this cannot infer —
    `quotation.status_changed`, `timesheet.submitted`, `approval.recorded` — so
    the ORM layer fills the GAP rather than covering the whole surface. It steps
    aside for any entity the semantic layer named, and steps back in by itself
    if that call is ever removed.
    """
    pending = session.info.get("audit_pending")
    if not pending:
        return
    claimed = set(session.info.get("audit_semantic", set()))
    for entry in session.new:
        if isinstance(entry, AuditLog):
            claimed.add((entry.entity_type, entry.entity_id))

    session.info["audit_pending"] = []
    fresh = [
        AuditLog(**values)
        for values in pending
        if (values["entity_type"], values["entity_id"]) not in claimed
    ]
    if fresh:
        session.add_all(fresh)
        # These are not auditable themselves (`audit_logs` is in NEVER_AUDITED),
        # so the flush they trigger cannot recurse.
        session.flush()


def _on_commit(session: Session) -> None:
    # `before_commit` fires BEFORE the commit's own flush, so without this the
    # last writes of the transaction have not been gathered yet and the trail
    # comes out empty — which is exactly what the first version of this did.
    # Flushing here runs `_gather` over them; then the decision can be made
    # with every `record_audit` call already in hand.
    session.flush()
    _emit(session)


def _forget(session: Session, *_: object) -> None:
    session.info.pop("audit_pending", None)
    session.info.pop("audit_semantic", None)


def install() -> None:
    """Register the listeners for every Session, once."""
    if not event.contains(Session, "before_flush", _gather):
        event.listen(Session, "before_flush", _gather)
    if not event.contains(Session, "before_commit", _on_commit):
        event.listen(Session, "before_commit", _on_commit)
    if not event.contains(Session, "after_commit", _forget):
        event.listen(Session, "after_commit", _forget)
    if not event.contains(Session, "after_soft_rollback", _forget):
        event.listen(Session, "after_soft_rollback", _forget)
