from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor
from app.db.session import get_db
from app.models import Tenant, User
from app.services.console import dashboard_counts


router = APIRouter(prefix="/console", tags=["console"])


class ConsoleMeta(BaseModel):
    """Reserved for request metadata as the console API evolves."""


class ConsoleUserIdentity(BaseModel):
    id: str
    email: str
    name: str | None = None


class ConsoleTenantIdentity(BaseModel):
    id: str
    name: str
    email_domain: str | None = None


class ConsoleBootstrapData(BaseModel):
    user: ConsoleUserIdentity
    tenant: ConsoleTenantIdentity
    role: str
    permissions: list[str]
    employee_id: str | None = None


class ConsoleBootstrapResponse(BaseModel):
    data: ConsoleBootstrapData
    meta: ConsoleMeta = Field(default_factory=ConsoleMeta)


class ConsoleDashboardCounts(BaseModel):
    users: int
    todos_open: int
    todos_overdue: int
    objects: int
    skills: int


class ConsoleDashboardData(BaseModel):
    counts: ConsoleDashboardCounts


class ConsoleDashboardResponse(BaseModel):
    data: ConsoleDashboardData
    meta: ConsoleMeta = Field(default_factory=ConsoleMeta)


def require_user_actor(actor: Actor) -> None:
    if actor.kind != "user" or actor.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this endpoint requires a user credential, not a service key",
        )


@router.get("/bootstrap", response_model=ConsoleBootstrapResponse)
def bootstrap(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsoleBootstrapResponse:
    require_user_actor(actor)
    user = db.get(User, actor.user_id)
    tenant = db.get(Tenant, actor.tenant_id)
    if user is None or tenant is None:
        # get_actor validates both records. This guard handles a record being
        # removed between authentication and construction of the view model.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authenticated console identity no longer exists",
        )

    return ConsoleBootstrapResponse(
        data=ConsoleBootstrapData(
            user=ConsoleUserIdentity(id=user.id, email=user.email, name=user.name),
            tenant=ConsoleTenantIdentity(
                id=tenant.id,
                name=tenant.name,
                email_domain=tenant.email_domain,
            ),
            role=actor.role,
            permissions=sorted(actor.permissions),
            employee_id=actor.employee_id,
        )
    )


@router.get("/dashboard", response_model=ConsoleDashboardResponse)
def dashboard(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsoleDashboardResponse:
    require_user_actor(actor)
    counts = ConsoleDashboardCounts(**dashboard_counts(db, actor.tenant_id))
    return ConsoleDashboardResponse(data=ConsoleDashboardData(counts=counts))
