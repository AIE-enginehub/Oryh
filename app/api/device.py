from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import resolved_base_url
from app.core.security import generate_token, hash_token
from app.db.session import bind_tenant_context, get_db
from app.models import DeviceAuthorization, Tenant, User
from app.schemas import DeviceStartRequest, DeviceTokenRequest
from app.services.audit import record_audit
from app.services.bundles import install_dir, tenant_slug

router = APIRouter(prefix="/auth/device")

# user_code alphabet without lookalikes (0/O, 1/I/L, A/4 …): typed by hand
# from another screen.
USER_CODE_ALPHABET = "BCDFGHJKMNPQRSTVWXZ23456789"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def generate_user_code() -> str:
    chars = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{chars[:4]}-{chars[4:]}"


def normalize_user_code(value: str) -> str:
    chars = "".join(c for c in value.upper() if c.isalnum())
    return f"{chars[:4]}-{chars[4:]}" if len(chars) == 8 else value.strip().upper()


def find_pending_by_user_code(db: Session, user_code: str) -> DeviceAuthorization | None:
    row = db.scalar(
        select(DeviceAuthorization)
        .where(
            DeviceAuthorization.user_code == normalize_user_code(user_code),
            DeviceAuthorization.status == "pending",
        )
        .order_by(DeviceAuthorization.created_at.desc())
    )
    if row is None or as_utc(row.expires_at) < utc_now():
        return None
    return row


@router.post("/start", status_code=status.HTTP_201_CREATED)
def start_device_authorization(
    payload: DeviceStartRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Begin the browser device flow for an agent that has no credential yet:
    returns the device_code the agent keeps and polls with, and the short
    user_code the person confirms in the web console after signing in."""
    device_code = generate_token()
    user_code = generate_user_code()
    while db.scalar(
        select(DeviceAuthorization).where(
            DeviceAuthorization.user_code == user_code,
            DeviceAuthorization.status == "pending",
        )
    ) is not None:
        user_code = generate_user_code()
    row = DeviceAuthorization(
        device_code_hash=hash_token(device_code),
        user_code=user_code,
        client_name=payload.client_name,
        expires_at=utc_now() + timedelta(minutes=settings.device_code_ttl_minutes),
    )
    db.add(row)
    db.commit()
    return {
        "data": {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": f"{resolved_base_url()}/web/device",
            "verification_uri_complete": f"{resolved_base_url()}/web/device?code={user_code}",
            "expires_in": settings.device_code_ttl_minutes * 60,
            "interval": settings.device_poll_interval_seconds,
        },
        "meta": {},
    }


@router.post("/token")
def poll_device_authorization(
    payload: DeviceTokenRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Poll the outcome. The minted key is delivered exactly once: the row is
    consumed and its plaintext cleared on the first successful poll."""
    row = db.scalar(
        select(DeviceAuthorization).where(
            DeviceAuthorization.device_code_hash == hash_token(payload.device_code)
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid device code")
    if row.status == "pending":
        if as_utc(row.expires_at) < utc_now():
            return {"data": {"status": "expired"}, "meta": {}}
        return {
            "data": {"status": "pending", "interval": settings.device_poll_interval_seconds},
            "meta": {},
        }
    if row.status == "denied":
        return {"data": {"status": "denied"}, "meta": {}}
    if row.status == "consumed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device code already used; start a new authorization",
        )

    # approved: hand over the key and burn the row
    plaintext = row.api_key_plaintext
    user = db.get(User, row.user_id)
    tenant = db.get(Tenant, row.tenant_id)
    row.status = "consumed"
    row.api_key_plaintext = None
    row.consumed_at = utc_now()
    bind_tenant_context(db, row.tenant_id)
    record_audit(
        db,
        tenant_id=row.tenant_id,
        action="device.connected",
        entity_type="user",
        entity_id=row.user_id,
        actor=f"user:{row.user_id}",
        detail={"key_id": row.api_key_id, "client_name": row.client_name},
    )
    db.commit()
    return {
        "data": {
            "status": "approved",
            "api_key": plaintext,
            "user": {
                "email": user.email if user else None,
                "name": user.name if user else None,
                "role": user.role if user else None,
                "employee_id": user.employee_id if user else None,
            },
            "tenant": tenant.name if tenant else None,
            # Which company the agent just connected to, in the form its skills
            # and install directory carry — so it can greet the person with the
            # right employer before it has downloaded anything.
            "tenant_slug": tenant_slug(tenant) if tenant else None,
            "install_dir": install_dir(tenant_slug(tenant)) if tenant else None,
        },
        "meta": {},
    }
