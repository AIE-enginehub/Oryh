import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.responses import RedirectResponse

from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.claims import router as claims_router
from app.api.device import router as device_router
from app.api.flow_runner_bootstrap import router as flow_runner_bootstrap_router
from app.api.flows import router as flows_router
from app.api.master_data import router as master_data_router
from app.api.objects import router as objects_router
from app.api.people import router as people_router
from app.api.policies import router as policies_router
from app.api.purchasing import router as purchasing_router
from app.api.resources import router as resources_router
from app.api.sales import router as sales_router
from app.api.skills import router as skills_router
from app.api.workspace import router as workspace_router
from app.api.bundles import router as bundles_router
from app.api.console import router as console_router
from app.api.roles import router as roles_router
from app.api.workflows import router as workflows_router
from app.core.config import API_PREFIX, settings
from app.core.deployment_profile import enforce_deployment_profile
from app.core.legacy_usage import LegacyWebUsageMiddleware
from app.core.request_context import RequestBaseUrlMiddleware
from app.core.responses import JSONCharsetMiddleware
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Before the first request, not on the first incident: a production profile
    # that is not a production configuration refuses to serve.
    enforce_deployment_profile(settings)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestBaseUrlMiddleware)
app.add_middleware(LegacyWebUsageMiddleware)
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
app.include_router(objects_router, prefix=API_PREFIX)
app.include_router(master_data_router, prefix=API_PREFIX)
app.include_router(people_router, prefix=API_PREFIX)
app.include_router(policies_router, prefix=API_PREFIX)
app.include_router(resources_router, prefix=API_PREFIX)
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

    from app.db.session import create_ops_sessionmaker

    checks: dict[str, str] = {}
    try:
        with create_ops_sessionmaker()() as db:
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
