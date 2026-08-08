"""How ORYH's own flow runner learns which tenants it serves.

Enrolment became the default, which made a new workspace's subscriptions
automatic — and then nothing happened, because the runner's tenant set came
from a JSON file somebody had to edit on the runner host. A workspace could
have seven enabled subscriptions, an adopted credential, a published workflow
definition and a document sitting in the queue, and never be looked at. The
data said driven; the deployment said not yet.

That file could not be generated: `api_keys` stores a hash, plaintext is shown
exactly once at issuance, and no amount of server-side work recovers it. So the
runner is issued its own instead.

Two endpoints, and deliberately only two: which tenants have enabled
subscriptions, and give me a credential for one. Neither reads a document, a
person, or a money figure. The runner still does all its actual work on the
per-tenant hosted key it is handed here, so `Actor.write_scope`, attribution,
the per-tenant grant set and every audit fact are untouched by this file — the
bootstrap is the only thing that speaks platform.

**What holding this token means.** Anyone with it can obtain a hosted flow
agent credential in any enrolled tenant, and that credential can advance
documents and assign todos there. It cannot read payroll, edit anyone's
document, touch identity, or reach a tenant with no enabled subscription. The
honest summary is that it is the fleet's master key for flow driving, and the
JSON file it replaces was one too — that file listed every tenant's key in one
place on one host.

Off unless `ORYH_FLOW_RUNNER_BOOTSTRAP_TOKEN` is set, so a deployment that does
not host a runner does not carry the surface.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.config import settings
from app.core.permissions import HOSTED_FLOW_AGENT_DISPLAY_NAME, PRINCIPAL_HOSTED_FLOW_AGENT
from app.db.session import bind_platform_admin_context, bind_tenant_context, get_db
from app.models import ApiKey, FlowSubscription, Tenant, generate_api_key, hash_api_key
from app.services.audit import record_audit

router = APIRouter(prefix="/flow-runner", tags=["flow-runner"])

Db = Annotated[Session, Depends(get_db)]


def require_bootstrap(
    db: Db,
    x_flow_runner_bootstrap: Annotated[str | None, Header()] = None,
) -> None:
    """Constant-time, and 404 rather than 401 when the feature is off.

    A deployment with no hosted runner should not advertise that these paths
    exist, and an attacker probing for them should not learn whether the token
    is unset or merely wrong.

    Binds the platform RLS context on success, for the same reason
    `get_platform_admin` does: these two endpoints cross tenants by design, and
    without it every row policy hides the very tenants the runner is asking
    about. Missing it would pass on SQLite and fail on Postgres, which is the
    worst place to find out.
    """
    configured = settings.flow_runner_bootstrap_token
    if not configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not x_flow_runner_bootstrap or not secrets.compare_digest(
        x_flow_runner_bootstrap, configured
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="flow runner bootstrap token required",
        )
    bind_platform_admin_context(db)


Bootstrap = Annotated[None, Depends(require_bootstrap)]


@router.get("/tenants", include_in_schema=False)
def flow_runner_tenants(_: Bootstrap, db: Db):
    """Every tenant with at least one enabled flow subscription.

    Enabled is the whole filter, and it is the tenant's own lever: switching
    the last subscription off removes the workspace from this list and the
    runner stops driving it on the next pass. A tenant that never had a
    subscription — one whose provisioning predates the default and has not been
    synced — is absent rather than silently driven.

    Suspended tenants are excluded here rather than left for the per-request
    check to refuse, so the runner does not spend a pass discovering it.
    """
    rows = db.execute(
        select(Tenant.id, Tenant.name, func.count(FlowSubscription.id))
        .join(FlowSubscription, FlowSubscription.tenant_id == Tenant.id)
        .where(
            FlowSubscription.enabled.is_(True),
            Tenant.status == "active",
        )
        .group_by(Tenant.id, Tenant.name)
        .order_by(Tenant.name)
    ).all()
    return envelope(
        [
            {"tenant_id": tenant_id, "name": name, "enabled_subscriptions": count}
            for tenant_id, name, count in rows
        ],
        total=len(rows),
    )


@router.post("/tenants/{tenant_id}/credential", include_in_schema=False)
def issue_flow_runner_credential(tenant_id: str, _: Bootstrap, db: Db):
    """Issue this tenant's hosted credential to the runner, and make it the one.

    Always mints rather than returning an existing key, because there is
    nothing to return: only the hash is stored. So this also does the two
    things that keep "always mint" from accumulating driftwood:

    - **every other active hosted key for the tenant is deactivated.** The
      fleet has one driver. Leaving the previous key alive is what created the
      rotation window found in testing — a second key that reads every
      subscription, spends agent runs, and is refused on every write because
      `write_scope` only counts rows bound to the key that authenticated.
    - **every subscription is re-pointed at the new key**, not only the
      unbound ones. A subscription still naming yesterday's key is enrolled on
      paper and refused in practice.

    A restart therefore re-mints and supersedes rather than piling up, which is
    what makes the runner's state file an optimisation instead of a
    correctness requirement.
    """
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    subscriptions = db.scalars(
        select(FlowSubscription).where(FlowSubscription.tenant_id == tenant_id)
    ).all()
    if not any(row.enabled for row in subscriptions):
        # Refused rather than issued-and-useless: a credential whose
        # `write_scope` is empty can do nothing, and handing one out would
        # read to the runner as "this tenant is mine to drive".
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this tenant has no enabled flow subscription",
        )

    # The platform flag lets this endpoint SEE across tenants; it does not let
    # it WRITE into one. `api_keys` and `audit_logs` are both tenant-scoped and
    # their INSERT policies key on `app.tenant_id`, so the audit row is refused
    # without this — on Postgres only, which is exactly where it would have
    # been found in production rather than in a test.
    bind_tenant_context(db, tenant_id)

    plain_text_api_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant_id,
        key_hash=hash_api_key(plain_text_api_key),
        label=HOSTED_FLOW_AGENT_DISPLAY_NAME,
        role="service",
        principal_kind=PRINCIPAL_HOSTED_FLOW_AGENT,
        is_active=True,
    )
    db.add(api_key)
    db.flush()

    superseded = 0
    for previous in db.scalars(
        select(ApiKey).where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT,
            ApiKey.is_active.is_(True),
            ApiKey.id != api_key.id,
        )
    ):
        previous.is_active = False
        superseded += 1
    for row in subscriptions:
        row.api_key_id = api_key.id

    record_audit(
        db,
        tenant_id=tenant_id,
        action="flow_agent_key.issued_to_runner",
        entity_type="api_key",
        entity_id=api_key.id,
        actor="platform:flow-runner",
        detail={"superseded_keys": superseded, "subscriptions_repointed": len(subscriptions)},
    )
    db.commit()
    db.refresh(api_key)
    return envelope(
        {
            "tenant_id": tenant_id,
            "api_key_id": api_key.id,
            "plain_text_api_key": plain_text_api_key,
            "superseded_keys": superseded,
        }
    )
