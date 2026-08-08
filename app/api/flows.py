"""Hosted flow driving: which entity types ORYH advances here, and what it did.

Two resources, both deliberately thin. `flow_subscriptions` records the terms of
a service — the platform writes them, the tenant reads them and holds one lever,
`enabled`. `flow_runs` is the envelope around the agent's work: when it ran, what
it found, what it moved. Neither carries routing rules; the tenant's workflow
definition still does, and the driver skill still reads it at use time.

The runner needs no credential beyond the hosted key P0 issued it: it reads its
subscriptions here, and signs its own run records with `flow_run.record`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import envelope, get_tenant_id, list_rows, requested_pagination
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import FlowRun, FlowSubscription
from app.schemas import (
    CloseFlowRunRequest,
    FlowRunEnvelope,
    FlowRunListEnvelope,
    FlowRunRead,
    FlowSubscriptionEnvelope,
    FlowSubscriptionListEnvelope,
    FlowSubscriptionRead,
    OpenFlowRunRequest,
    ReportDriverStateRequest,
    TenantUpdateFlowSubscriptionRequest,
)
from app.services.audit import record_audit

router = APIRouter()


def subscription_or_404(db: Session, tenant_id: str, subscription_id: str) -> FlowSubscription:
    row = db.get(FlowSubscription, subscription_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FlowSubscription not found")
    return row


@router.get(
    "/flow-subscriptions",
    response_model=FlowSubscriptionListEnvelope,
    response_model_exclude_unset=True,
)
def list_flow_subscriptions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = None,
    enabled: bool | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """What the platform drives in this workspace — the tenant's own answer to
    "where has our routing been handed over", and the runner's answer to "what
    am I responsible for here"."""
    stmt = select(FlowSubscription).where(FlowSubscription.tenant_id == tenant_id)
    if enabled is not None:
        stmt = stmt.where(FlowSubscription.enabled.is_(enabled))
    return list_rows(
        db, stmt,
        filters={FlowSubscription.entity_type: entity_type},
        order_by=(FlowSubscription.entity_type,),
        render=lambda rows: subscription_reads_with_last_run(db, tenant_id, rows),
        pagination=requested_pagination(page, size),
    )


def subscription_reads_with_last_run(
    db: Session, tenant_id: str, rows: list[FlowSubscription]
) -> list[dict]:
    """Attach when a runner was last heard from, in one extra query per page.

    Without it, `enabled` is the only signal a reader has — and `enabled` means
    "the tenant has not switched this off", which is not the same as "something
    is driving it". A stopped runner and a working one look identical through
    that field, which is the same confusion the run ledger exists to prevent.
    """
    if not rows:
        return []
    last_runs = dict(
        db.execute(
            select(FlowRun.subscription_id, func.max(FlowRun.started_at))
            .where(
                FlowRun.tenant_id == tenant_id,
                FlowRun.subscription_id.in_([row.id for row in rows]),
            )
            .group_by(FlowRun.subscription_id)
        ).all()
    )
    return [
        FlowSubscriptionRead.model_validate(row)
        .model_copy(update={"last_run_at": last_runs.get(row.id)})
        .model_dump(by_alias=True)
        for row in rows
    ]


@router.patch(
    "/flow-subscriptions/{subscription_id}",
    response_model=FlowSubscriptionEnvelope,
    response_model_exclude_unset=True,
)
def update_flow_subscription(
    subscription_id: str,
    payload: TenantUpdateFlowSubscriptionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The tenant's lever on a service someone else operates: on or off.

    Terms — which skill drives, how often, what the queue query is — are the
    subscription's, and change through the platform. Switching off is immediate
    and needs no one's agreement; switching back on is allowed here because,
    unlike reviving a deactivated credential, it grants no access the tenant has
    not already got a live hosted key for."""
    require_permission(actor, "keys.manage")
    subscription = subscription_or_404(db, actor.tenant_id, subscription_id)
    if subscription.enabled == payload.enabled:
        return envelope(FlowSubscriptionRead.model_validate(subscription).model_dump(by_alias=True))
    subscription.enabled = payload.enabled
    detail = {"entity_type": subscription.entity_type}
    if payload.enabled and subscription.parked_at is not None:
        # Switching a parked subscription back on IS the "I fixed it, try again"
        # gesture — the cause is nearly always on the tenant's side (a definition
        # that routes nowhere, an approver with no employee record), so the
        # person who fixed it is the person who clears the stop. Made explicit
        # here rather than derived from a timestamp, because a rule that says
        # "any edit un-parks" would silently resume spending.
        detail["cleared_park"] = subscription.parked_reason
        subscription.parked_at = None
        subscription.parked_reason = None
        subscription.unmoved_runs = 0
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="flow_subscription.enabled" if payload.enabled else "flow_subscription.disabled",
        entity_type="flow_subscription",
        entity_id=subscription.id,
        actor=actor.label,
        detail=detail,
    )
    db.commit()
    db.refresh(subscription)
    return envelope(FlowSubscriptionRead.model_validate(subscription).model_dump(by_alias=True))


@router.patch(
    "/flow-subscriptions/{subscription_id}/driver-state",
    response_model=FlowSubscriptionEnvelope,
    response_model_exclude_unset=True,
)
def report_driver_state(
    subscription_id: str,
    payload: ReportDriverStateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The runner writing down where it got to with this subscription.

    Separate from the tenant's PATCH because it is a different kind of fact: the
    tenant decides whether a service runs, the runner reports whether it is
    getting anywhere. Gated on `flow_run.record` — the same grant that lets it
    keep its own ledger — so no wider credential appears in the loop.
    """
    require_permission(actor, "flow_run.record")
    subscription = subscription_or_404(db, actor.tenant_id, subscription_id)
    subscription.unmoved_runs = payload.unmoved_runs
    was_parked = subscription.parked_at is not None
    if payload.parked and not was_parked:
        subscription.parked_at = datetime.now(timezone.utc)
        subscription.parked_reason = payload.parked_reason
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="flow_subscription.parked",
            entity_type="flow_subscription",
            entity_id=subscription.id,
            actor=actor.label,
            detail={
                "entity_type": subscription.entity_type,
                "reason": payload.parked_reason,
                "unmoved_runs": payload.unmoved_runs,
            },
        )
    elif not payload.parked and was_parked:
        # The runner never clears its own stop: whatever made the queue stick is
        # still there until a person deals with it. Only the tenant's off→on or
        # an operator lifts it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "a parked subscription is cleared by switching it off and on again, "
                "or by the platform — not by the runner"
            ),
        )
    db.commit()
    db.refresh(subscription)
    return envelope(FlowSubscriptionRead.model_validate(subscription).model_dump(by_alias=True))


@router.get("/flow-runs", response_model=FlowRunListEnvelope, response_model_exclude_unset=True)
def list_flow_runs(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    subscription_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """Newest first: the last run is the question people actually ask."""
    stmt = select(FlowRun).where(FlowRun.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            FlowRun.entity_type: entity_type,
            FlowRun.status: status_filter,
            FlowRun.subscription_id: subscription_id,
        },
        order_by=(FlowRun.started_at.desc(),),
        read_model=FlowRunRead,
        pagination=requested_pagination(page, size),
    )


@router.post(
    "/flow-runs",
    status_code=status.HTTP_201_CREATED,
    response_model=FlowRunEnvelope,
    response_model_exclude_unset=True,
)
def open_flow_run(
    payload: OpenFlowRunRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Opened before the agent starts, so a run that dies without ever reporting
    back still leaves a `running` row with a start time — the only shape in which
    "it hung" is visible at all."""
    require_permission(actor, "flow_run.record")
    if payload.subscription_id is not None:
        subscription_or_404(db, actor.tenant_id, payload.subscription_id)
    run = FlowRun(
        tenant_id=actor.tenant_id,
        subscription_id=payload.subscription_id,
        entity_type=payload.entity_type,
        trigger=payload.trigger,
        status="running",
        started_at=payload.started_at,
        queue_size=payload.queue_size,
        detail_jsonb=payload.detail,
        recorded_by=attributed(actor, None),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return envelope(FlowRunRead.model_validate(run).model_dump(by_alias=True))


@router.patch(
    "/flow-runs/{run_id}",
    response_model=FlowRunEnvelope,
    response_model_exclude_unset=True,
)
def close_flow_run(
    run_id: str,
    payload: CloseFlowRunRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "flow_run.record")
    run = db.get(FlowRun, run_id)
    if run is None or run.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FlowRun not found")
    if run.status != "running":
        # Terminal is terminal: a late retry must not rewrite how a run ended,
        # and the ledger is worth less if the same run can report twice.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"flow run already finished as {run.status!r}",
        )
    run.status = payload.status
    run.finished_at = payload.finished_at
    run.items_advanced = payload.items_advanced
    run.error = payload.error
    if payload.detail is not None:
        run.detail_jsonb = {**(run.detail_jsonb or {}), **payload.detail}
    db.commit()
    db.refresh(run)
    return envelope(FlowRunRead.model_validate(run).model_dump(by_alias=True))


def stale_running_runs(db: Session, tenant_id: str, older_than: datetime) -> list[FlowRun]:
    """Runs that opened and never reported. Not swept automatically — a hung run
    is a fact worth seeing, not a row to tidy away."""
    return list(
        db.scalars(
            select(FlowRun).where(
                FlowRun.tenant_id == tenant_id,
                FlowRun.status == "running",
                FlowRun.started_at < older_than,
            )
        )
    )
