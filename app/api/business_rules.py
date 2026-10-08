"""Business rules — the workspace's own logic as data: four kinds, one lifecycle.

A workspace's business logic used to live in four places with four lifecycles:
`policies`, `workflow_definitions`, a skill's calibration and the state
machine. The first two were the same kind of thing — versioned tenant prose an
agent reads — told apart by what they are keyed to and who reads them, which
are properties of a row. So they are one table, `business_rules`, and `kind`
says which question a row answers:

| kind            | answers                                              | keyed to        |
|-----------------|------------------------------------------------------|-----------------|
| `policy`        | what the company's rules are                         | nothing         |
| `approval_flow` | who decides a submitted document, on what branches   | an object type  |
| `data_rule`     | what a document must satisfy when it is filed        | an object type  |
| `linkage`       | what happens elsewhere when a document reaches a state | an object type |

The lifecycle is the policy's and is shared by every kind: a draft; a publish
that closes the previous version the day before the new one starts, in one
transaction; effective dates that answer "what applied in March"; repeal; a
visibility and a capability gate; an audit row for every act. The three scoped
kinds get their `code` generated from the scope, so "one published version per
code" and the handover hold for them with no second mechanism.

**The server never applies a rule and never parses one.** It stores what the
workspace published and who published it; the agent reads it, decides, and
records its working. A `data_rule` is the agent's calibration gate, not a
server-side validation — the invariants the server does enforce are code.

Publishing an `approval_flow` for a builtin family lifts a parked hosted
subscription (the next version of the map is nearly always the fix), which is
the one side effect a publish has. See
docs/plans/business-rules-refactor-2026-10-06.zh.md.

`/policies` and `/workflow-definitions` answered one release more as views
over this table and were removed with migration 0098 (2026-10-07).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.api.common import (
    ListFilters,
    list_filters,
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    envelope,
    get_live_or_404,
    get_scoped_or_404,
    list_rows,
    page_only_pagination,
    register_attachment_source,
    serve_document_attachment,
)
from app.api.deps import Actor, attributed, get_actor, has_permission
from app.db.session import get_db
from app.models import Attachment, BusinessObject, BusinessRule, Employee, ObjectTypeDefinition
from app.schemas import (
    SCOPED_RULE_KINDS,
    BusinessRuleEnvelope,
    BusinessRuleListEnvelope,
    BusinessRulePublishEnvelope,
    BusinessRulePublishRead,
    BusinessRuleRead,
    CreateBusinessRuleRequest,
    PublishBusinessRuleRequest,
    PublishNowBusinessRuleRequest,
    RepealBusinessRuleRequest,
    RescopeBusinessRuleRequest,
    UpdateBusinessRuleRequest,
)
from app.services.audit import record_audit
from app.services.flow_subscriptions import unpark_on_new_definition
from app.services.state_machines import BUILTIN_MACHINES
from app.services.type_options import require_type_option

router = APIRouter(prefix="/business-rules")

RULE_KINDS: tuple[str, ...] = ("policy", *SCOPED_RULE_KINDS)

# What each kind is called when the server has to name one.
RULE_KIND_NOUNS: dict[str, str] = {
    "policy": "policy",
    "approval_flow": "approval flow",
    "data_rule": "data rule",
    "linkage": "linkage",
}

# (grants that may draft, grants that may publish / repeal / rescope), per kind.
# The capability names are the ones the catalogue already had: a policy keeps
# its two-step authority (drafting is not publishing); the three scoped kinds
# are the admin's single `workflows.publish`, which drafted nothing before
# because a workflow definition had no draft. Renaming them is a separate
# decision (docs/plans/business-rules-refactor-2026-10-06.zh.md §3.4).
RULE_KIND_GATES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "policy": (("policy.manage", "policy.publish"), ("policy.publish",)),
    "approval_flow": (("workflows.publish",), ("workflows.publish",)),
    "data_rule": (("workflows.publish",), ("workflows.publish",)),
    "linkage": (("workflows.publish",), ("workflows.publish",)),
}


# --- who may do what ---------------------------------------------------------


def may_draft_rules(actor: Actor, kind: str) -> bool:
    return any(has_permission(actor, grant) for grant in RULE_KIND_GATES[kind][0])


def may_publish_rules(actor: Actor, kind: str) -> bool:
    return any(has_permission(actor, grant) for grant in RULE_KIND_GATES[kind][1])


def may_manage_rules(actor: Actor, kind: str) -> bool:
    """The author side of a kind: sees its drafts, reads it unrestricted."""
    return may_draft_rules(actor, kind) or may_publish_rules(actor, kind)


def managed_rule_kinds(actor: Actor) -> frozenset[str]:
    return frozenset(kind for kind in RULE_KINDS if may_manage_rules(actor, kind))


def _require_grant(actor: Actor, grants: tuple[str, ...], act: str, kind: str) -> None:
    if any(has_permission(actor, grant) for grant in grants):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"{act} a {RULE_KIND_NOUNS[kind]} requires capability {' or '.join(grants)}",
    )


def require_rule_drafter(actor: Actor, kind: str) -> None:
    _require_grant(actor, RULE_KIND_GATES[kind][0], "drafting", kind)


def require_rule_publisher(actor: Actor, kind: str) -> None:
    _require_grant(actor, RULE_KIND_GATES[kind][1], "publishing", kind)


def may_read_rule(actor: Actor, rule: BusinessRule) -> bool:
    """Three gates, in the order they matter.

    A DRAFT is invisible to everyone but its authors — the draft 裁员方案 is
    more dangerous than the published one, and a workspace that could read
    drafts would learn what is coming before it is decided.

    A REPEALED or SUPERSEDED rule is history: it leaves the default list, so
    nobody follows a rule that no longer applies, but it stays readable by id
    and by date — "what were the rules in March" has to be answerable by the
    people who could read them in March, not only by HR.

    A RESTRICTED rule names the capability it wants and the row is checked
    against it. Everything else published is readable by anyone here, which is
    the point — an employee handbook nobody may read is not a handbook, and a
    submit skill reads the data rules of what it files with no grant at all.
    """
    if rule.status == "draft":
        return may_manage_rules(actor, rule.kind)
    if rule.visibility == "restricted":
        if not rule.required_capability:
            return may_manage_rules(actor, rule.kind)
        verb, _, scope = rule.required_capability.partition(":")
        return has_permission(actor, verb, scope or None)
    return True


def covered_rule_capabilities(db: Session, actor: Actor, tenant_id: str) -> list[str]:
    """Which of the capability strings this tenant's rules ask for are ones
    this actor holds — resolved against the DISTINCT values actually in use,
    so the SQL predicate stays exact."""
    declared = db.scalars(
        select(BusinessRule.required_capability)
        .where(BusinessRule.tenant_id == tenant_id, BusinessRule.required_capability.is_not(None))
        .distinct()
    ).all()
    covered = []
    for value in declared:
        verb, _, scope = value.partition(":")
        if has_permission(actor, verb, scope or None):
            covered.append(value)
    return covered


def visible_rule_filter(db: Session, actor: Actor, tenant_id: str, *, historical: bool = False):
    """The list-side twin of `may_read_rule`, as a WHERE clause rather than a
    post-filter, so `total` does not count what the caller cannot see.

    `historical` is the `in_force_on` read: a repealed rule that governed the
    date asked about is part of the answer, for everyone who could read it
    then. The default list keeps repealed rows out, so the handbook shows what
    applies now.
    """
    managed = managed_rule_kinds(actor)
    if managed == frozenset(RULE_KINDS):
        return None
    readable = or_(
        BusinessRule.visibility != "restricted",
        BusinessRule.required_capability.in_(covered_rule_capabilities(db, actor, tenant_id)),
    )
    statuses = ("published", "superseded", "repealed") if historical else ("published", "superseded")
    open_to_reader = and_(BusinessRule.status.in_(statuses), readable)
    if managed:
        return or_(BusinessRule.kind.in_(sorted(managed)), open_to_reader)
    return open_to_reader


def ensure_rule_visible(actor: Actor, rule: BusinessRule) -> None:
    """404, not 403. That a 薪酬管理办法 exists at all is part of what a
    restricted rule is hiding."""
    if not may_read_rule(actor, rule):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business rule not found")


def ensure_rule_visibility_shape(visibility: str | None, required_capability) -> None:
    if visibility == "restricted" and not required_capability:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "a restricted rule must name the capability that may read it "
                "(`required_capability`) — one that names none is readable by "
                "everyone, which is the opposite of what it says"
            ),
        )


def ensure_rule_editable(rule: BusinessRule) -> None:
    if rule.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{RULE_KIND_NOUNS[rule.kind]} {rule.code} v{rule.version} is {rule.status} — a "
                "published rule is corrected by publishing a new version, never edited in "
                "place, so that what people were told stays recoverable. To change only who "
                "may READ it, which is not a change to what it says, use "
                "POST /business-rules/{id}/visibility"
            ),
        )


# --- identity: code, scope, version --------------------------------------------


def rule_scope_code(kind: str, entity_kind: str, object_type: str, name: str) -> str:
    """The generated code of a scoped rule: one sequence per (kind, scope, name)."""
    return f"{kind}:{entity_kind}:{object_type}:{name}"


def next_rule_version(db: Session, tenant_id: str, code: str) -> int:
    highest = db.scalar(
        select(func.max(BusinessRule.version)).where(
            BusinessRule.tenant_id == tenant_id, BusinessRule.code == code
        )
    )
    return (highest or 0) + 1


def rule_version_lock_key(tenant_id: str, code: str) -> int:
    """A stable signed bigint for one code's version sequence. Length-prefixed
    so codes containing the separator stay distinct; a collision can only
    serialize two unrelated sequences, never let one bypass its lock."""
    digest = hashlib.sha256()
    for value in (tenant_id, code):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)


def lock_rule_version_scope(db: Session, tenant_id: str, code: str) -> None:
    """Serialize version allocation for one code on PostgreSQL. Row locks
    cannot protect the first version because there is no row yet; a
    transaction-scoped advisory lock covers both cases and releases itself.
    SQLite has no equivalent and stays a no-op for the unit-test runtime."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("select pg_advisory_xact_lock(cast(:lock_key as bigint))"),
        {"lock_key": rule_version_lock_key(tenant_id, code)},
    )


def validate_rule_scope(db: Session, tenant_id: str, entity_kind: str, object_type: str) -> None:
    """A scoped rule is about documents that have a lifecycle: a builtin family
    with a machine and an active definition, or a custom type the workspace
    has defined or has rows of. Browsable-but-machineless collections (resource
    bookings, billing accounts) are not rule subjects."""
    active_definition = db.scalar(
        select(ObjectTypeDefinition.id).where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == entity_kind,
            ObjectTypeDefinition.object_type == object_type,
            ObjectTypeDefinition.status == "active",
        )
    )
    if entity_kind == "builtin":
        if object_type not in BUILTIN_MACHINES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"unknown builtin object_type {object_type!r} — "
                    f"one of {', '.join(sorted(BUILTIN_MACHINES))}"
                ),
            )
        if active_definition is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"builtin object_type {object_type!r} has no active definition",
            )
        return
    existing_object = db.scalar(
        select(BusinessObject.id)
        .where(BusinessObject.tenant_id == tenant_id, BusinessObject.object_type == object_type)
        .limit(1)
    )
    if active_definition is None and existing_object is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"business object_type {object_type!r} has neither an active "
                "definition nor existing data"
            ),
        )


def resolve_rule_identity(db: Session, tenant_id: str, payload: CreateBusinessRuleRequest) -> dict:
    """What a new draft is keyed by, from what the caller said and the kind's
    rules: a policy brings its own code and category; a scoped kind brings an
    object type and gets its code generated."""
    kind = payload.kind
    if kind == "policy":
        if not payload.code:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="a policy needs its own `code` (the workspace's 制度编号)",
            )
        if not payload.category:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="a policy needs a `category` (GET /type-options?family=policy_category)",
            )
        if not payload.title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="a policy needs a `title`",
            )
        require_type_option(db, tenant_id, "policy_category", payload.category)
        scope = {"entity_kind": None, "object_type": None, "name": None}
        if payload.object_type:
            # a policy MAY be about one document family; then the scope is whole
            scope = {
                "entity_kind": payload.entity_kind or "builtin",
                "object_type": payload.object_type,
                "name": payload.name or "default",
            }
            validate_rule_scope(db, tenant_id, scope["entity_kind"], scope["object_type"])
        return {"code": payload.code, "category": payload.category, "title": payload.title, **scope}
    if not payload.object_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"a {RULE_KIND_NOUNS[kind]} is about one object type — `object_type` is required",
        )
    if payload.category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="`category` classifies policies; the other kinds are classified by `kind`",
        )
    entity_kind = payload.entity_kind or "builtin"
    name = payload.name or "default"
    validate_rule_scope(db, tenant_id, entity_kind, payload.object_type)
    return {
        "code": payload.code or rule_scope_code(kind, entity_kind, payload.object_type, name),
        "category": None,
        "title": payload.title or f"{payload.object_type} {RULE_KIND_NOUNS[kind]}",
        "entity_kind": entity_kind,
        "object_type": payload.object_type,
        "name": name,
    }


# --- the acts -----------------------------------------------------------------


def _audit(db: Session, actor: Actor, rule: BusinessRule, event: str, detail: dict) -> None:
    record_audit(
        db, tenant_id=rule.tenant_id, action=f"{rule.kind}.{event}", entity_type="business_rule",
        entity_id=rule.id, actor=attributed(actor, None),
        detail={"kind": rule.kind, "code": rule.code, "version": rule.version, **detail},
    )


def seed_is_untouched(rule: BusinessRule) -> bool:
    """A catalog-seeded draft nobody here has edited: its body still hashes to
    what the catalog shipped."""
    return (
        rule.origin == "catalog"
        and rule.status == "draft"
        and rule.catalog_hash is not None
        and hashlib.sha256(rule.body.strip().encode("utf-8")).hexdigest() == rule.catalog_hash
    )


def draft_rule(
    db: Session, actor: Actor, payload: CreateBusinessRuleRequest, *, adopt_edited_seed: bool = False
) -> BusinessRule:
    """Always a draft. Reusing a code opens the next version of that rule —
    the version number is the server's to allocate, so two people cannot both
    be drafting v2.

    One exception, for the catalog's drafts: a scope that holds a seeded draft
    the workspace has not touched does not get a second draft beside it — what
    is drafted now becomes that row's text, so the seed is the starting point
    it was meant to be and never an orphan sitting at v1 forever. A seed the
    workspace has edited is theirs, and a plain draft leaves it alone;
    publishing in one call adopts it regardless, since a draft was never in
    force and the published text is what the workspace just said.
    """
    require_rule_drafter(actor, payload.kind)
    tenant_id = actor.tenant_id
    identity = resolve_rule_identity(db, tenant_id, payload)
    ensure_rule_visibility_shape(payload.visibility, payload.required_capability)
    if payload.effective_thru and payload.effective_from and payload.effective_thru < payload.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_thru cannot precede effective_from",
        )
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    if payload.owner_employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.owner_employee_id)

    lock_rule_version_scope(db, tenant_id, identity["code"])
    seed = db.scalars(
        select(BusinessRule).where(
            BusinessRule.tenant_id == tenant_id,
            BusinessRule.code == identity["code"],
            BusinessRule.status == "draft",
            BusinessRule.origin == "catalog",
            BusinessRule.deleted_at.is_(None),
        )
    ).first()
    if seed is not None and (adopt_edited_seed or seed_is_untouched(seed)):
        seed.body = payload.body
        seed.summary = payload.summary
        seed.rules_json = payload.rules_json
        seed.visibility = payload.visibility
        seed.required_capability = payload.required_capability
        seed.effective_from = payload.effective_from
        seed.effective_thru = payload.effective_thru
        seed.attachment_id = payload.attachment_id
        seed.owner_employee_id = payload.owner_employee_id
        seed.custom_fields_jsonb = payload.custom_fields
        if payload.title:
            seed.title = payload.title
        db.flush()
        _audit(db, actor, seed, "drafted", {"adopted_seed": True})
        return seed
    version = next_rule_version(db, tenant_id, identity["code"])
    previous = db.scalars(
        select(BusinessRule).where(
            BusinessRule.tenant_id == tenant_id,
            BusinessRule.code == identity["code"],
            BusinessRule.version == version - 1,
        )
    ).first()
    rule = BusinessRule(
        tenant_id=tenant_id,
        kind=payload.kind,
        code=identity["code"],
        version=version,
        entity_kind=identity["entity_kind"],
        object_type=identity["object_type"],
        name=identity["name"],
        category=identity["category"],
        title=identity["title"],
        summary=payload.summary,
        body=payload.body,
        rules_json=payload.rules_json,
        visibility=payload.visibility,
        required_capability=payload.required_capability,
        status="draft",
        effective_from=payload.effective_from,
        effective_thru=payload.effective_thru,
        supersedes_id=previous.id if previous else None,
        attachment_id=payload.attachment_id,
        owner_employee_id=payload.owner_employee_id,
        created_by=attributed(actor, None),
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(rule)
    db.flush()
    _audit(db, actor, rule, "drafted", {})
    return rule


def update_rule_fields(db: Session, actor: Actor, rule: BusinessRule, updates: dict) -> None:
    require_rule_drafter(actor, rule.kind)
    ensure_rule_editable(rule)
    tenant_id = rule.tenant_id
    if updates.get("category"):
        if rule.kind != "policy":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="`category` classifies policies; the other kinds are classified by `kind`",
            )
        require_type_option(db, tenant_id, "policy_category", updates["category"])
    ensure_rule_visibility_shape(
        updates.get("visibility", rule.visibility),
        updates.get("required_capability", rule.required_capability),
    )
    if updates.get("attachment_id"):
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if updates.get("owner_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, updates["owner_employee_id"])
    effective_from = updates.get("effective_from", rule.effective_from)
    effective_thru = updates.get("effective_thru", rule.effective_thru)
    if effective_from and effective_thru and effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_thru cannot precede effective_from",
        )
    changed = sorted(updates)
    if "custom_fields" in updates:
        rule.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(rule, field, value)
    _audit(db, actor, rule, "updated", {"fields": changed})


def delete_rule(db: Session, actor: Actor, rule: BusinessRule, reason: str | None) -> None:
    """Drafts only. A published rule is repealed, not deleted — people acted
    on it, and the record of what they were told has to survive."""
    require_rule_drafter(actor, rule.kind)
    if rule.status != "draft":
        remedy = (
            "repeal it (POST /business-rules/{id}/repeal) rather than deleting it"
            if rule.status == "published"
            else "it is already closed and stays as the record of what applied then"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{RULE_KIND_NOUNS[rule.kind]} {rule.code} v{rule.version} is {rule.status} — "
                f"{remedy}; people acted on it"
            ),
        )
    rule.deleted_at = datetime.now(timezone.utc)
    rule.deleted_by = attributed(actor, None)
    rule.delete_reason = reason
    _audit(db, actor, rule, "deleted", {"reason": reason})


def publish_rule(
    db: Session, actor: Actor, rule: BusinessRule, *, effective_from: date | None, note: str | None
) -> tuple[BusinessRule, BusinessRule | None]:
    """Publishing closes the previous version and opens this one, in one
    transaction — the same handover `POST /pay-histories` performs, and for the
    same reason: as two calls they eventually drift, and a history with a gap
    in it cannot answer what applied in March. The previous version's
    `effective_thru` lands the day before this one starts.

    An `approval_flow` for a builtin family is the hosted runner's map: its
    next version lifts a parked subscription, since the map routing nowhere
    is nearly always what parked it."""
    require_rule_publisher(actor, rule.kind)
    tenant_id = rule.tenant_id
    if rule.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{RULE_KIND_NOUNS[rule.kind]} {rule.code} v{rule.version} is already {rule.status}",
        )
    effective_from = effective_from or rule.effective_from or date.today()
    if rule.effective_thru and rule.effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="this rule stops applying before the date it would start",
        )
    superseded = db.scalars(
        select(BusinessRule).where(
            BusinessRule.tenant_id == tenant_id,
            BusinessRule.code == rule.code,
            BusinessRule.status == "published",
            BusinessRule.id != rule.id,
            BusinessRule.deleted_at.is_(None),
        )
    ).first()
    if superseded is not None:
        superseded.status = "superseded"
        if superseded.effective_thru is None or superseded.effective_thru >= effective_from:
            # the day before this one starts — unless the previous version
            # started that very day (a flow published twice in one afternoon),
            # which closes it on its own first day rather than before it began
            closed_on = effective_from - timedelta(days=1)
            if superseded.effective_from is not None and closed_on < superseded.effective_from:
                closed_on = superseded.effective_from
            superseded.effective_thru = closed_on
        # flush before promoting this one: the unit of work orders UPDATEs by
        # its own bookkeeping, not by assignment order, so without this the new
        # version can reach 'published' while the old one still is — and the
        # partial unique index refuses, correctly, in the middle of a legal
        # handover
        db.flush()
    rule.status = "published"
    rule.effective_from = effective_from
    rule.published_at = datetime.now(timezone.utc)
    rule.published_by = attributed(actor, None)
    _audit(db, actor, rule, "published", {
        "effective_from": effective_from.isoformat(),
        "superseded_id": superseded.id if superseded else None,
        "note": note,
    })
    if rule.kind == "approval_flow" and rule.entity_kind == "builtin":
        db.flush()
        unpark_on_new_definition(
            db, tenant_id, rule.object_type, version=rule.version, actor=actor.label,
        )
    return rule, superseded


def publish_rule_now(
    db: Session, actor: Actor, payload: PublishNowBusinessRuleRequest
) -> tuple[BusinessRule, BusinessRule | None]:
    """Draft and publish in one transaction — the handover a workflow
    definition always had. Needs the publishing grant, which for every kind
    also drafts."""
    require_rule_publisher(actor, payload.kind)
    rule = draft_rule(db, actor, payload, adopt_edited_seed=True)
    return publish_rule(db, actor, rule, effective_from=payload.effective_from, note=payload.note)


def rescope_rule(
    db: Session, actor: Actor, rule: BusinessRule, *, visibility: str, required_capability: str | None,
    note: str | None,
) -> bool:
    """Change who may read a rule, at any status, without touching a word of
    it. What the rule SAYS is frozen once published; who may read it is a
    standing decision that outlives the statement. Returns whether anything
    changed — a no-op leaves no audit row."""
    require_rule_publisher(actor, rule.kind)
    ensure_rule_visibility_shape(visibility, required_capability)
    before = (rule.visibility, rule.required_capability)
    after = (visibility, required_capability)
    if before == after:
        return False
    rule.visibility = visibility
    rule.required_capability = required_capability
    _audit(db, actor, rule, "visibility_changed", {
        "status": rule.status,
        "from": {"visibility": before[0], "required_capability": before[1]},
        "to": {"visibility": after[0], "required_capability": after[1]},
        "note": note,
    })
    return True


def repeal_rule(
    db: Session, actor: Actor, rule: BusinessRule, *, effective_thru: date | None, note: str | None
) -> None:
    """废止 — it stops applying and leaves the default list; it is not
    deleted, and stays readable by id and by date."""
    require_rule_publisher(actor, rule.kind)
    if rule.status != "published":
        # A superseded version already stopped applying, on the date the
        # handover set; repealing it would MOVE that date and leave a hole.
        detail = f"only the published version can be repealed — this one is {rule.status}"
        if rule.status == "superseded":
            detail = (
                f"{rule.code} v{rule.version} was already closed on "
                f"{rule.effective_thru} when v{rule.version + 1} took over; "
                "repealing it would move that date and leave a gap in the history. "
                "Repeal the version that is currently published instead"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    effective_thru = effective_thru or date.today()
    if rule.effective_from and effective_thru < rule.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a rule cannot stop applying before it started",
        )
    rule.status = "repealed"
    rule.effective_thru = effective_thru
    _audit(db, actor, rule, "repealed", {"effective_thru": effective_thru.isoformat(), "note": note})


# --- reads ----------------------------------------------------------------------


def rules_query(
    db: Session, actor: Actor, *, include_deleted: bool = False, in_force_on: date | None = None,
):
    """The statement every rule list starts from: the tenant's rows, the
    reader's gate, and the date question when one is asked."""
    tenant_id = actor.tenant_id
    stmt = select(BusinessRule).where(BusinessRule.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BusinessRule.deleted_at.is_(None))
    narrowing = visible_rule_filter(db, actor, tenant_id, historical=in_force_on is not None)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    if in_force_on is not None:
        stmt = stmt.where(
            BusinessRule.status.in_(("published", "superseded", "repealed")),
            or_(BusinessRule.effective_from.is_(None), BusinessRule.effective_from <= in_force_on),
            or_(BusinessRule.effective_thru.is_(None), BusinessRule.effective_thru >= in_force_on),
        )
    return stmt


def get_rule_or_404(db: Session, actor: Actor, rule_id: str, *, kind: str | None = None) -> BusinessRule:
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    if kind is not None and rule.kind != kind:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business rule not found")
    ensure_rule_visible(actor, rule)
    return rule


def rule_envelope(rule: BusinessRule) -> dict:
    return envelope(BusinessRuleRead.model_validate(rule).model_dump(by_alias=True))


def published_rules_of(
    db: Session, tenant_id: str, *, kind: str | None = None, entity_kind: str, object_type: str,
) -> list[BusinessRule]:
    """Every non-draft rule scoped to one object type, newest version first
    within a sequence — what a document's detail shows beside the document."""
    stmt = select(BusinessRule).where(
        BusinessRule.tenant_id == tenant_id,
        BusinessRule.entity_kind == entity_kind,
        BusinessRule.object_type == object_type,
        BusinessRule.status.in_(("published", "superseded", "repealed")),
        BusinessRule.deleted_at.is_(None),
    )
    if kind is not None:
        stmt = stmt.where(BusinessRule.kind == kind)
    return db.scalars(
        stmt.order_by(
            BusinessRule.kind.asc(), BusinessRule.name.asc(),
            BusinessRule.version.desc(), BusinessRule.id.desc(),
        )
    ).all()


def has_published_approval_flow(db: Session, tenant_id: str, entity_kind: str, object_type: str) -> bool:
    """The existence question the runner, the setup report and the platform
    console ask: is there a map for this family?"""
    return db.scalar(
        select(BusinessRule.id).where(
            BusinessRule.tenant_id == tenant_id,
            BusinessRule.kind == "approval_flow",
            BusinessRule.entity_kind == entity_kind,
            BusinessRule.object_type == object_type,
            BusinessRule.status == "published",
            BusinessRule.deleted_at.is_(None),
        ).limit(1)
    ) is not None


def published_rule_index(
    db: Session, tenant_id: str, entity_kind: str | None = None
) -> dict[tuple[str, str], BusinessRule]:
    """The version in force per (object_type, kind) — what the setup report
    says a family has, and what it checks a flow's text against."""
    stmt = select(BusinessRule).where(
        BusinessRule.tenant_id == tenant_id,
        BusinessRule.kind != "policy",
        BusinessRule.status == "published",
        BusinessRule.deleted_at.is_(None),
    )
    if entity_kind is not None:
        stmt = stmt.where(BusinessRule.entity_kind == entity_kind)
    return {(rule.object_type, rule.kind): rule for rule in db.scalars(stmt)}


REQUIREMENTS_HEADINGS = ("提交要求", "submission requirement", "submission requirements")


def flow_text_carries_requirements(body: str) -> bool:
    """A pre-kinds definition kept its filing conditions inside the routing
    text; until the admin splits it, the submit agents read that section and
    the report says a data rule is still owed."""
    lowered = body.lower()
    return any(heading.lower() in lowered for heading in REQUIREMENTS_HEADINGS)


def families_with_published_approval_flow(db: Session, tenant_id: str, entity_kind: str | None = None) -> set[str]:
    stmt = select(BusinessRule.object_type).where(
        BusinessRule.tenant_id == tenant_id,
        BusinessRule.kind == "approval_flow",
        BusinessRule.status == "published",
        BusinessRule.deleted_at.is_(None),
    )
    if entity_kind is not None:
        stmt = stmt.where(BusinessRule.entity_kind == entity_kind)
    return {object_type for (object_type,) in db.execute(stmt)}


# --- routes -------------------------------------------------------------------------


@router.get("", response_model=BusinessRuleListEnvelope, response_model_exclude_unset=True)
def list_business_rules(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    kind: str | None = None,
    entity_kind: str | None = None,
    object_type: str | None = None,
    name: str | None = None,
    code: str | None = None,
    category: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    visibility: str | None = None,
    in_force_on: date | None = None,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(BusinessRule, ranges=('created_at', 'effective_from', 'effective_thru', 'published_at'), equals=('attachment_id', 'owner_employee_id', 'supersedes_id', 'origin')))] = None,
):
    """`kind` and the scope pick the question; `in_force_on` is the one worth
    asking — what applied in March, not what is on the intranet today. A
    reader with no grant sees published and superseded rules; the authors of
    a kind see its drafts too."""
    stmt = rules_query(db, actor, include_deleted=include_deleted, in_force_on=in_force_on)
    return list_rows(
        db, stmt,
        filters={
            BusinessRule.kind: kind,
            BusinessRule.entity_kind: entity_kind,
            BusinessRule.object_type: object_type,
            BusinessRule.name: name,
            BusinessRule.code: code,
            BusinessRule.category: category,
            BusinessRule.status: status_filter,
            BusinessRule.visibility: visibility,
        },
        keyword=keyword,
        keyword_columns=(BusinessRule.code, BusinessRule.title, BusinessRule.summary, BusinessRule.body, BusinessRule.object_type),
        order_by=(BusinessRule.kind.asc(), BusinessRule.code.asc(), BusinessRule.version.desc()),
        pagination=page_only_pagination(page, size, default=50),
        sort=order_by,
        read_model=BusinessRuleRead,
        extra=extra,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BusinessRuleEnvelope,
             response_model_exclude_unset=True)
def create_business_rule(
    payload: CreateBusinessRuleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Always a draft; publishing is a separate call. Reusing a code — or the
    scope a code is generated from — opens the next version."""
    rule = draft_rule(db, actor, payload)
    db.commit()
    db.refresh(rule)
    return rule_envelope(rule)


@router.post("/publish", status_code=status.HTTP_201_CREATED, response_model=BusinessRulePublishEnvelope,
             response_model_exclude_unset=True)
def publish_business_rule_now(
    payload: PublishNowBusinessRuleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Draft and publish in one transaction: the next version of a rule, in
    force from `effective_from` (today by default), the previous one closed
    the day before — the handover a workflow definition always had."""
    rule, superseded = publish_rule_now(db, actor, payload)
    db.commit()
    db.refresh(rule)
    if superseded is not None:
        db.refresh(superseded)
    return envelope(
        BusinessRulePublishRead(
            current=BusinessRuleRead.model_validate(rule),
            superseded=BusinessRuleRead.model_validate(superseded) if superseded else None,
        ).model_dump(by_alias=True)
    )


@router.get("/{rule_id}", response_model=BusinessRuleEnvelope, response_model_exclude_unset=True)
def get_business_rule(
    rule_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Any version by id, superseded ones included, so a past decision stays
    traceable to the rule it followed."""
    return rule_envelope(get_rule_or_404(db, actor, rule_id))


@router.patch("/{rule_id}", response_model=BusinessRuleEnvelope, response_model_exclude_unset=True)
def update_business_rule(
    rule_id: str,
    payload: UpdateBusinessRuleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    update_rule_fields(db, actor, rule, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(rule)
    return rule_envelope(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_rule(
    rule_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    reason: Annotated[str | None, Query(max_length=500)] = None,
):
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    delete_rule(db, actor, rule, reason)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/publish", response_model=BusinessRulePublishEnvelope,
             response_model_exclude_unset=True)
def publish_business_rule(
    rule_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: PublishBusinessRuleRequest = Body(default=None),
):
    payload = payload or PublishBusinessRuleRequest()
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    rule, superseded = publish_rule(db, actor, rule, effective_from=payload.effective_from, note=payload.note)
    db.commit()
    db.refresh(rule)
    if superseded is not None:
        db.refresh(superseded)
    return envelope(
        BusinessRulePublishRead(
            current=BusinessRuleRead.model_validate(rule),
            superseded=BusinessRuleRead.model_validate(superseded) if superseded else None,
        ).model_dump(by_alias=True)
    )


@router.post("/{rule_id}/visibility", response_model=BusinessRuleEnvelope, response_model_exclude_unset=True)
def rescope_business_rule(
    rule_id: str,
    payload: RescopeBusinessRuleRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    if rescope_rule(db, actor, rule, visibility=payload.visibility,
                    required_capability=payload.required_capability, note=payload.note):
        db.commit()
        db.refresh(rule)
    return rule_envelope(rule)


@router.post("/{rule_id}/repeal", response_model=BusinessRuleEnvelope, response_model_exclude_unset=True)
def repeal_business_rule(
    rule_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: RepealBusinessRuleRequest = Body(default=None),
):
    payload = payload or RepealBusinessRuleRequest()
    rule = get_live_or_404(db, BusinessRule, actor.tenant_id, rule_id)
    repeal_rule(db, actor, rule, effective_thru=payload.effective_thru, note=payload.note)
    db.commit()
    db.refresh(rule)
    return rule_envelope(rule)


# --- the original document, reached through the record that carries it ------
#
# Authorisation is the DOCUMENT's, never the attachment id's. See
# `serve_document_attachment` in common.py for why the standalone
# `/attachments/{id}/content` could not answer this question safely.


register_attachment_source(BusinessRule)


@router.get("/{rule_id}/attachments/{attachment_id}/content")
def get_business_rule_attachment(
    rule_id: str,
    attachment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The rule's own document. Drafts are visible only to the kind's authors,
    and so are their files."""
    document = get_rule_or_404(db, actor, rule_id)
    return serve_document_attachment(db, actor.tenant_id, document, attachment_id)
