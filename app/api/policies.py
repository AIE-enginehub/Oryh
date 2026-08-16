"""规章制度 — the company's own rules, published with a version and a name.

Split out of `routes.py`, unchanged: eight endpoints and the eight helpers that
decide who may read a policy, who may publish one, and when a published one may
still be edited.

There is deliberately no second table holding the figures in a structured form.
That shape exists in traditional systems because their consumer cannot read
prose; ours can. A `policy_rules` table would only have been a second source of
truth for the same rules, free to drift from the body with nothing to notice —
so the structured restatement, when a workspace wants one, is `rules_json` on
this row, versioned and published and frozen with the document it restates.

The server never applies a rule and never parses one. It stores what HR
published and who published it; the agent reads it, computes with it, and
records its working — the same relationship the payroll path has with 五险一金
rates, except the figure now has a publisher and a date instead of living in the
agent's memory. See docs/policies.md.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.common import (
    envelope,
    get_live_or_404,
    get_scoped_or_404,
    list_rows,
    page_only_pagination,
)
from app.api.deps import Actor, attributed, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import Attachment, Employee, Policy
from app.schemas import (
    CreatePolicyRequest,
    PolicyEnvelope,
    PolicyListEnvelope,
    PolicyPublishEnvelope,
    PolicyPublishRead,
    PolicyRead,
    PublishPolicyRequest,
    RepealPolicyRequest,
    RescopePolicyRequest,
    UpdatePolicyRequest,
)
from app.services.audit import record_audit
from app.services.type_options import require_type_option

router = APIRouter()


def may_manage_policies(actor: Actor) -> bool:
    return has_permission(actor, "policy.manage") or has_permission(actor, "policy.publish")


def may_read_policy(actor: Actor, policy: Policy) -> bool:
    """Three gates, in the order they matter.

    A DRAFT is invisible to everyone but its authors — the draft 裁员方案 is
    more dangerous than the published one, and a workspace that could read
    drafts would learn what is coming before it is decided.

    A REPEALED policy is likewise author-only: it is history, and leaving it in
    the handbook is how somebody follows a rule that no longer applies.

    A RESTRICTED policy names the capability it wants and the row is checked
    against it. Everything else published is readable by anyone here, which is
    the point — an employee handbook nobody may read is not a handbook.
    """
    if policy.status in ("draft", "repealed"):
        return may_manage_policies(actor)
    if policy.visibility == "restricted":
        if not policy.required_capability:
            # the CHECK constraint makes this unreachable; if it ever is
            # reached, refusing is the safe direction
            return may_manage_policies(actor)
        verb, _, scope = policy.required_capability.partition(":")
        return has_permission(actor, verb, scope or None)
    return True


def covered_policy_capabilities(db: Session, actor: Actor, tenant_id: str) -> list[str]:
    """Which of the capability strings this tenant's policies ask for are ones
    this actor holds.

    The set is decided in Python — `has_permission` knows about scopes and
    bypasses — but it has to become a SQL predicate, so it is resolved against
    the DISTINCT values actually in use rather than against every string that
    could exist. That is a handful of rows, and it keeps the filter exact.
    """
    declared = db.scalars(
        select(Policy.required_capability)
        .where(Policy.tenant_id == tenant_id, Policy.required_capability.is_not(None))
        .distinct()
    ).all()
    covered = []
    for value in declared:
        verb, _, scope = value.partition(":")
        if has_permission(actor, verb, scope or None):
            covered.append(value)
    return covered


def visible_policy_filter(db: Session, actor: Actor, tenant_id: str):
    """The list-side twin of `may_read_policy`, as SQL rather than a post-filter.

    Filtering rows after the query would make `total` and the page size lie —
    the caller would page through a list whose count includes documents it
    cannot see, which is itself a leak (how many restricted policies exist is
    worth hiding). So the whole gate is expressed as a WHERE clause.
    """
    if may_manage_policies(actor):
        return None
    readable = or_(
        Policy.visibility != "restricted",
        Policy.required_capability.in_(covered_policy_capabilities(db, actor, tenant_id)),
    )
    return and_(Policy.status.in_(("published", "superseded")), readable)


def ensure_policy_visible(actor: Actor, policy: Policy) -> None:
    """404, not 403. That a 薪酬管理办法 exists at all is part of what a
    restricted policy is hiding."""
    if not may_read_policy(actor, policy):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


def ensure_policy_visibility_shape(visibility: str | None, required_capability) -> None:
    if visibility == "restricted" and not required_capability:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a restricted policy must name the capability that may read it "
                "(`required_capability`) — one that names none is readable by "
                "everyone, which is the opposite of what it says"
            ),
        )


def ensure_policy_editable(policy: Policy) -> None:
    if policy.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"policy {policy.code} v{policy.version} is {policy.status} — a published "
                "policy is corrected by publishing a new version, never edited in place, "
                "so that what people were told stays recoverable. To change only who "
                "may READ it, which is not a change to what it says, use "
                "POST /policies/{id}/visibility"
            ),
        )


def next_policy_version(db: Session, tenant_id: str, code: str) -> int:
    highest = db.scalar(
        select(func.max(Policy.version)).where(
            Policy.tenant_id == tenant_id, Policy.code == code
        )
    )
    return (highest or 0) + 1


@router.get("/policies", response_model=PolicyListEnvelope, response_model_exclude_unset=True)
def list_policies(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    code: str | None = None,
    category: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    visibility: str | None = None,
    in_force_on: date | None = None,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """`in_force_on` is the question worth asking — what applied in March, not
    what is on the intranet today."""
    tenant_id = actor.tenant_id
    stmt = select(Policy).where(Policy.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Policy.deleted_at.is_(None))
    narrowing = visible_policy_filter(db, actor, tenant_id)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    if in_force_on is not None:
        stmt = stmt.where(
            Policy.status.in_(("published", "superseded", "repealed")),
            or_(Policy.effective_from.is_(None), Policy.effective_from <= in_force_on),
            or_(Policy.effective_thru.is_(None), Policy.effective_thru >= in_force_on),
        )
    result = list_rows(
        db, stmt,
        filters={
            Policy.code: code,
            Policy.category: category,
            Policy.status: status_filter,
            Policy.visibility: visibility,
        },
        keyword=keyword,
        keyword_columns=(Policy.code, Policy.title, Policy.summary),
        order_by=(Policy.code.asc(), Policy.version.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PolicyRead,
    )
    return result


@router.post(
    "/policies",
    status_code=status.HTTP_201_CREATED,
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def create_policy(
    payload: CreatePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Always a draft. Reusing a `code` opens the next version of that policy —
    the version number is the server's to allocate, so two people cannot both
    be drafting v2."""
    require_permission(actor, "policy.manage")
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "policy_category", payload.category)
    ensure_policy_visibility_shape(payload.visibility, payload.required_capability)
    if payload.effective_thru and payload.effective_from and (
        payload.effective_thru < payload.effective_from
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    if payload.owner_employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.owner_employee_id)

    version = next_policy_version(db, tenant_id, payload.code)
    previous = db.scalars(
        select(Policy).where(
            Policy.tenant_id == tenant_id,
            Policy.code == payload.code,
            Policy.version == version - 1,
        )
    ).first()
    policy = Policy(
        tenant_id=tenant_id,
        code=payload.code,
        version=version,
        category=payload.category,
        title=payload.title,
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
    db.add(policy)
    db.flush()
    record_audit(
        db, tenant_id=tenant_id, action="policy.drafted", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={"code": policy.code, "version": policy.version},
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.get(
    "/policies/{policy_id}", response_model=PolicyEnvelope, response_model_exclude_unset=True
)
def get_policy(
    policy_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    policy = get_live_or_404(db, Policy, actor.tenant_id, policy_id)
    ensure_policy_visible(actor, policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.patch(
    "/policies/{policy_id}", response_model=PolicyEnvelope, response_model_exclude_unset=True
)
def update_policy(
    policy_id: str,
    payload: UpdatePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "policy.manage")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    ensure_policy_editable(policy)
    updates = payload.model_dump(exclude_unset=True)
    if "category" in updates and updates["category"]:
        require_type_option(db, tenant_id, "policy_category", updates["category"])
    ensure_policy_visibility_shape(
        updates.get("visibility", policy.visibility),
        updates.get("required_capability", policy.required_capability),
    )
    if updates.get("attachment_id"):
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if updates.get("owner_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, updates["owner_employee_id"])
    effective_from = updates.get("effective_from", policy.effective_from)
    effective_thru = updates.get("effective_thru", policy.effective_thru)
    if effective_from and effective_thru and effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if "custom_fields" in updates:
        policy.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    reason: Annotated[str | None, Query(max_length=500)] = None,
):
    """Drafts only. A published policy is repealed, not deleted — people acted
    on it, and the record of what they were told has to survive."""
    require_permission(actor, "policy.manage")
    policy = get_live_or_404(db, Policy, actor.tenant_id, policy_id)
    if policy.status != "draft":
        remedy = (
            "repeal it (POST /policies/{id}/repeal) rather than deleting it"
            if policy.status == "published"
            else "it is already closed and stays as the record of what applied then"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"policy {policy.code} v{policy.version} is {policy.status} — "
                f"{remedy}; people acted on it"
            ),
        )
    policy.deleted_at = datetime.now(timezone.utc)
    policy.deleted_by = attributed(actor, None)
    policy.delete_reason = reason
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/policies/{policy_id}/publish",
    response_model=PolicyPublishEnvelope,
    response_model_exclude_unset=True,
)
def publish_policy(
    policy_id: str,
    payload: PublishPolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Publishing closes the previous version and opens this one, in one
    transaction — the same handover `POST /pay-histories` performs, and for the
    same reason: as two calls they eventually drift, and a policy history with
    a gap in it cannot answer what applied in March.

    The previous version's `effective_thru` lands the day before this one
    starts, so the pair reads as a continuous record rather than two documents
    that happen to be numbered.
    """
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    if policy.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"policy {policy.code} v{policy.version} is already {policy.status}",
        )
    effective_from = payload.effective_from or policy.effective_from or date.today()
    if policy.effective_thru and policy.effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="this policy stops applying before the date it would start",
        )

    superseded = db.scalars(
        select(Policy).where(
            Policy.tenant_id == tenant_id,
            Policy.code == policy.code,
            Policy.status == "published",
            Policy.id != policy.id,
            Policy.deleted_at.is_(None),
        )
    ).first()
    if superseded is not None:
        superseded.status = "superseded"
        if superseded.effective_thru is None or superseded.effective_thru >= effective_from:
            superseded.effective_thru = effective_from - timedelta(days=1)
        # flush before promoting this one: the unit of work orders UPDATEs by
        # its own bookkeeping, not by assignment order, so without this the new
        # version can reach 'published' while the old one still is — and the
        # partial unique index refuses, correctly, in the middle of a legal
        # handover
        db.flush()

    policy.status = "published"
    policy.effective_from = effective_from
    policy.published_at = datetime.now(timezone.utc)
    policy.published_by = attributed(actor, None)
    record_audit(
        db, tenant_id=tenant_id, action="policy.published", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "effective_from": effective_from.isoformat(),
            "superseded_id": superseded.id if superseded else None,
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    if superseded is not None:
        db.refresh(superseded)
    return envelope(
        PolicyPublishRead(
            current=PolicyRead.model_validate(policy),
            superseded=PolicyRead.model_validate(superseded) if superseded else None,
        ).model_dump(by_alias=True)
    )


@router.post(
    "/policies/{policy_id}/visibility",
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def rescope_policy(
    policy_id: str,
    payload: RescopePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Change who may read a policy, at any status, without touching a word of
    it.

    Publication freezes what the rule SAYS — that is what lets the handbook
    answer "what were people told in March". It never should have frozen who
    may read it. Those are different kinds of fact: one is a statement made on
    a date, the other is a standing decision that outlives the statement and
    changes when the company does.

    Conflating them left the worst case with no remedy. A policy published to
    a wider audience than intended could not be edited (409), could not be
    deleted (published policies never are), and repealing it would retire a
    rule that is still in force — so the only way to close the reading was to
    stop applying the rule. That is not a choice a workspace should have to
    make about its own handbook.

    Superseded and repealed versions are re-scopable for the same reason, and
    it matters more there: they stay readable to whoever could read them, so a
    version that should never have been broadly visible has to be closable
    after the fact.

    `policy.publish` rather than `policy.manage`, because this is the authority
    act on a published document that drafting is deliberately kept apart from —
    the same line publish and repeal already draw.
    """
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    ensure_policy_visibility_shape(payload.visibility, payload.required_capability)
    before = (policy.visibility, policy.required_capability)
    after = (payload.visibility, payload.required_capability)
    if before == after:
        # nothing to record; a no-op audit row is noise in the one trail that
        # should read as a list of real decisions
        return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))
    policy.visibility = payload.visibility
    policy.required_capability = payload.required_capability
    record_audit(
        db, tenant_id=tenant_id, action="policy.visibility_changed", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "status": policy.status,
            "from": {"visibility": before[0], "required_capability": before[1]},
            "to": {"visibility": after[0], "required_capability": after[1]},
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.post(
    "/policies/{policy_id}/repeal",
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def repeal_policy(
    policy_id: str,
    payload: RepealPolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """废止 — it stops applying, and it stops being visible to people who are
    not its authors, because a repealed rule left in the handbook is how
    somebody follows a rule that no longer exists. It is not deleted: what
    people were told, and until when, stays answerable."""
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    if policy.status != "published":
        # A superseded version is refused for a reason that is easy to miss: it
        # already stopped applying, on the date the handover set, and repealing
        # it would MOVE that date. The result is a hole — publish v2 from
        # 2027-07-01 (closing v1 at 2027-06-30), then repeal v1 as of
        # 2026-12-31, and the first half of 2027 is governed by neither
        # version. Nothing downstream would notice; `in_force_on` would simply
        # return nothing for six months.
        detail = (
            f"only the published version can be repealed — this one is {policy.status}"
        )
        if policy.status == "superseded":
            detail = (
                f"{policy.code} v{policy.version} was already closed on "
                f"{policy.effective_thru} when v{policy.version + 1} took over; "
                "repealing it would move that date and leave a gap in the history. "
                "Repeal the version that is currently published instead"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    effective_thru = payload.effective_thru or date.today()
    if policy.effective_from and effective_thru < policy.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a policy cannot stop applying before it started",
        )
    policy.status = "repealed"
    policy.effective_thru = effective_thru
    record_audit(
        db, tenant_id=tenant_id, action="policy.repealed", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "effective_thru": effective_thru.isoformat(),
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))
