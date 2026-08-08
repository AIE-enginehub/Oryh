import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.auth import router as auth_router
from app.api.device import router as device_router
from app.api.flow_runner_bootstrap import router as flow_runner_bootstrap_router
from app.api.flows import router as flows_router
from app.api.routes import router
from app.api.skills import router as skills_router
from app.api.bundles import router as bundles_router
from app.api.console import router as console_router
from app.api.roles import router as roles_router
from app.api.workflows import router as workflows_router
from app.core.config import settings
from app.core.legacy_usage import LegacyWebUsageMiddleware
from app.core.request_context import RequestBaseUrlMiddleware
from app.core.responses import JSONCharsetMiddleware
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestBaseUrlMiddleware)
app.add_middleware(LegacyWebUsageMiddleware)
# Added last so it wraps outermost and sees every response, including ones
# synthesized by exception handlers and the middlewares above.
app.add_middleware(JSONCharsetMiddleware)
app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(device_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(roles_router, prefix="/api/v1")
app.include_router(bundles_router, prefix="/api/v1")
app.include_router(console_router, prefix="/api/v1")
app.include_router(flows_router, prefix="/api/v1")
app.include_router(flow_runner_bootstrap_router, prefix="/api/v1")

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


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
