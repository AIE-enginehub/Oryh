import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.claims import router as claims_router
from app.api.device import router as device_router
from app.api.external import router as external_router
from app.api.flow_runner_bootstrap import router as flow_runner_bootstrap_router
from app.api.flows import router as flows_router
from app.api.master_data import router as master_data_router
from app.api.notifications import router as notifications_router
from app.api.objects import router as objects_router
from app.api.people import router as people_router
from app.api.policies import router as policies_router
from app.api.query_guard import reject_unknown_query_params
from app.api.purchasing import router as purchasing_router
from app.api.resources import router as resources_router
from app.api.contracts import router as contracts_router
from app.api.activities import router as activities_router
from app.api.geo import router as geo_router
from app.api.crm import router as crm_router
from app.api.shipments import router as shipments_router
from app.api.sales import router as sales_router
from app.api.skills import router as skills_router
from app.api.treasury import router as treasury_router
from app.api.workspace import router as workspace_router
from app.api.oauth import router as oauth_router
from app.api.mcp import router as mcp_router
from app.api.bundles import router as bundles_router
from app.api.console import router as console_router
from app.api.roles import router as roles_router
from app.api.workflows import router as workflows_router
from app.core.config import API_PREFIX, settings
from app.core.deployment_profile import enforce_deployment_profile
from app.core.idempotency import IdempotencyMiddleware, openapi_with_idempotency_key
from app.core.legacy_usage import LegacyWebUsageMiddleware
from app.core.request_context import RequestBaseUrlMiddleware
from app.core.responses import JSONCharsetMiddleware
from app.db.session import get_db
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Before the first request, not on the first incident: a production profile
    # that is not a production configuration refuses to serve.
    enforce_deployment_profile(settings)
    yield


# Set on the app before any include_router: every API read refuses query
# parameters its operation does not declare (app/api/query_guard.py).
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(reject_unknown_query_params)],
)


def _json_safe(value):
    """A validation error echoes the offending input; when that input is
    NaN or Infinity (refused at the boundary, review N11) the echo itself
    is not JSON and the 422 became a 500. Non-finite numbers are echoed as
    their names."""
    import math

    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )
app.add_middleware(RequestBaseUrlMiddleware)
app.add_middleware(LegacyWebUsageMiddleware)
# Every write under /api/v1 honours `Idempotency-Key` (app/core/idempotency.py).
# The session comes from the same `get_db` a handler would get — overridden
# in the test stack — resolved per request.
app.add_middleware(
    IdempotencyMiddleware,
    session_resolver=lambda: app.dependency_overrides.get(get_db, get_db),
)
# Added last so it wraps outermost and sees every response, including ones
# synthesized by exception handlers and the middlewares above.
app.add_middleware(JSONCharsetMiddleware)
# The business API, one module per document family or subject. Order is not
# load-bearing: `tests/test_route_table.py` proves no two routes can match one
# URL, so no registration order can change which handler answers.
app.include_router(sales_router, prefix=API_PREFIX)
app.include_router(purchasing_router, prefix=API_PREFIX)
app.include_router(billing_router, prefix=API_PREFIX)
app.include_router(claims_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(objects_router, prefix=API_PREFIX)
app.include_router(master_data_router, prefix=API_PREFIX)
app.include_router(external_router, prefix=API_PREFIX)
app.include_router(people_router, prefix=API_PREFIX)
app.include_router(policies_router, prefix=API_PREFIX)
app.include_router(resources_router, prefix=API_PREFIX)
app.include_router(contracts_router, prefix=API_PREFIX)
app.include_router(crm_router, prefix=API_PREFIX)
app.include_router(activities_router, prefix=API_PREFIX)
app.include_router(geo_router, prefix=API_PREFIX)
app.include_router(shipments_router, prefix=API_PREFIX)
app.include_router(treasury_router, prefix=API_PREFIX)
app.include_router(workspace_router, prefix=API_PREFIX)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(device_router, prefix=API_PREFIX)
app.include_router(skills_router, prefix=API_PREFIX)
app.include_router(workflows_router, prefix=API_PREFIX)
app.include_router(roles_router, prefix=API_PREFIX)
app.include_router(bundles_router, prefix=API_PREFIX)
app.include_router(console_router, prefix=API_PREFIX)
app.include_router(flows_router, prefix=API_PREFIX)
app.include_router(flow_runner_bootstrap_router, prefix=API_PREFIX)

# The SaaS platform layer — registration, the operator console, pilots — is
# attached by NAME, never by a static import: an open-core tree without
# app/saas assembles this exact module and serves the whole single-tenant
# product. `settings.resolved_edition` is "cloud" precisely when app.saas is
# importable (or the operator said so); the boundary test pins both sides.
if settings.resolved_edition == "cloud":
    importlib.import_module("app.saas").mount(app)

# LAST on purpose: this router ends in the retired-tenant catch-all
# (/web/{legacy_path}), and Starlette matches in registration order — every
# other /web contributor, the saas registration pages included, must land
# before the catch-all or it answers 404 for them.
app.include_router(web_router)
app.include_router(oauth_router)
app.include_router(mcp_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    # The public reverse proxy owns the browser root and sends it to React.
    # Direct API-port traffic should land on API documentation rather than a
    # public bootstrap page or retired tenant URL alias.
    return RedirectResponse("/docs")


@app.get("/livez")
def liveness() -> dict[str, str]:
    """The process is up and answering. Deliberately touches nothing else.

    A liveness probe that checks the database restarts every pod at once when
    the database blinks — turning a recoverable blip into an outage, and doing
    it precisely when the database can least afford a reconnect storm.
    """
    return {"status": "ok"}


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """The name every existing probe and compose healthcheck already uses.
    Same answer as `/livez`, kept so this split needs no coordinated change to
    running manifests."""
    return {"status": "ok"}


@app.get("/readyz")
def readiness(response: Response) -> dict:
    """Whether this process can serve a request — which `/healthz` never asked.

    All three Kubernetes probes pointed at an endpoint that returns ok
    unconditionally, so a pod whose database was unreachable was routed traffic
    the moment its port opened, and answered it with 500s. Readiness is the one
    that has to know.

    Readiness turns on one thing: the database answers. That is what separates
    a pod that can serve from one that cannot, and it is the question
    `/healthz` never asked.

    The migration revision is REPORTED, not gated on, for two separate reasons.
    Comparing it to a constant compiled into the image would make healthy pods
    unready during a migration release and turn a rolling deploy into an
    outage. And requiring a stamp at all would fail any schema built by
    `create_all` rather than by Alembic, which is what every test database and
    a standalone first boot are — a readiness probe is the wrong place to
    discover that, and `verify_deployment.sh` is the right one.

    503 rather than an exception: a probe reads the status code, and a stack
    trace in the log every ten seconds while the database is down is noise on
    top of an incident.
    """
    from sqlalchemy import text

    from app.db.session import SessionLocal, get_db

    # the runtime engine and pool, the same path a request takes: an owner
    # connection that answers proves nothing about the role and pool that
    # serve traffic, and building an engine per probe is its own load
    # (review N12)
    checks: dict[str, str] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
            checks["database"] = "ok"
            try:
                revision = db.execute(text("select version_num from alembic_version")).scalar()
                checks["revision"] = revision or "none recorded"
            except Exception:  # noqa: BLE001 — informational; absence is not unreadiness
                checks["revision"] = "not stamped"
    except Exception as exc:  # noqa: BLE001 — the reason belongs in the body
        checks.setdefault("database", f"unreachable: {type(exc).__name__}")

    ready = checks.get("database") == "ok"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "not ready", "checks": checks}


# The OpenAPI document names `Idempotency-Key` on every write operation, so a
# generated client and a skill contract see it beside the body it protects.
_openapi_without_header = app.openapi


def _openapi_with_header() -> dict:
    if app.openapi_schema is None:
        app.openapi_schema = openapi_with_idempotency_key(_openapi_without_header())
    return app.openapi_schema


app.openapi = _openapi_with_header
