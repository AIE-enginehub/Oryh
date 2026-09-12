"""Geography and territories.

A GEO is a place in a hierarchy — OFBiz's Geo: country, province, city,
district, postal code, or a region the workspace draws itself — each naming
its parent. A TERRITORY is a named set of geos (coverage is by containment)
with the people who work it. Both are master data (`master_data.manage`),
read by everyone.

Where a customer is (`geo_id`) and who covers it (`territory_id`) are two
facts. The server does the deterministic half — walk the geo's chain, list
every territory covering any geo in it, most specific first — and fills
the customer's territory when exactly one covers the most specific level.
When several do, the choice is a person's by the workspace's own rule; the
resolver says so rather than picking.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    commit_or_conflict,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    requested_pagination,
    require_master_data_manage,
    require_type_option,
    status_scope,
)
from app.api.deps import Actor, get_actor
from app.core.config import settings
from app.core.geo_templates import GEO_TEMPLATES
from app.db.session import get_db
from app.models import Employee, Geo, Territory, TerritoryGeo, TerritoryMember
from app.schemas import (
    CreateGeoRequest,
    CreateTerritoryGeoRequest,
    CreateTerritoryMemberRequest,
    CreateTerritoryRequest,
    GeoEnvelope,
    GeoListEnvelope,
    GeoRead,
    SeedGeoTemplateRead,
    SeedGeoTemplateRequest,
    TerritoryEnvelope,
    TerritoryGeoEnvelope,
    TerritoryGeoListEnvelope,
    TerritoryGeoRead,
    TerritoryListEnvelope,
    TerritoryMatchRead,
    TerritoryMemberEnvelope,
    TerritoryMemberListEnvelope,
    TerritoryMemberRead,
    TerritoryRead,
    TerritoryResolutionEnvelope,
    TerritoryResolutionRead,
    UpdateGeoRequest,
    UpdateTerritoryMemberRequest,
    UpdateTerritoryRequest,
)
from app.services.audit import record_audit

router = APIRouter()

MAX_DEPTH = 32


def geo_path(db: Session, tenant_id: str, geo_id: str) -> list[Geo]:
    """The geo and its ancestors, the geo first. A cycle (a parent that is
    its own descendant) is a curation error, cut at MAX_DEPTH rather than
    looped forever."""
    chain: list[Geo] = []
    seen: set[str] = set()
    current: str | None = geo_id
    while current and current not in seen and len(chain) < MAX_DEPTH:
        geo = db.scalar(select(Geo).where(Geo.tenant_id == tenant_id, Geo.id == current))
        if geo is None:
            break
        chain.append(geo)
        seen.add(geo.id)
        current = geo.parent_geo_id
    return chain


def resolve_territory(db: Session, tenant_id: str, geo_id: str) -> TerritoryResolutionRead:
    chain = geo_path(db, tenant_id, geo_id)
    matches: list[TerritoryMatchRead] = []
    for depth, geo in enumerate(chain):
        rows = db.execute(
            select(Territory, TerritoryGeo)
            .join(TerritoryGeo, TerritoryGeo.territory_id == Territory.id)
            .where(
                TerritoryGeo.tenant_id == tenant_id,
                TerritoryGeo.geo_id == geo.id,
                Territory.status == "active",
            )
            .order_by(Territory.territory_code.asc())
        ).all()
        for territory, _cover in rows:
            matches.append(TerritoryMatchRead(
                territory=TerritoryRead.model_validate(territory),
                covered_geo=GeoRead.model_validate(geo),
                depth=depth,
            ))
    answer = None
    ambiguous = False
    if matches:
        top = [m for m in matches if m.depth == matches[0].depth]
        if len(top) == 1:
            answer = top[0].territory
        else:
            ambiguous = True
    return TerritoryResolutionRead(
        geo_path=[GeoRead.model_validate(g) for g in chain],
        matches=matches,
        territory=answer,
        ambiguous=ambiguous,
    )


def customer_territory(db: Session, tenant_id: str, geo_id: str | None, territory_id: str | None) -> str | None:
    """The territory to store on a customer: the one named (checked to
    exist), else the one the geo resolves to unambiguously, else none."""
    if territory_id:
        get_scoped_or_404(db, Territory, tenant_id, territory_id)
        return territory_id
    if not geo_id:
        return None
    get_scoped_or_404(db, Geo, tenant_id, geo_id)
    resolved = resolve_territory(db, tenant_id, geo_id)
    return resolved.territory.id if resolved.territory is not None else None


# --- geos ---------------------------------------------------------------------


@router.get("/geos", response_model=GeoListEnvelope, response_model_exclude_unset=True)
def list_geos(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    geo_type: str | None = None,
    parent_geo_id: str | None = None,
    geo_code: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(Geo).where(Geo.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            Geo.geo_type: geo_type,
            Geo.parent_geo_id: parent_geo_id,
            Geo.geo_code: geo_code,
            Geo.status: status_scope(status_filter),
        },
        keyword=keyword,
        keyword_columns=(cast(Geo.id, String), Geo.geo_code, Geo.name, Geo.abbreviation),
        order_by=(Geo.geo_code.asc(), Geo.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=GeoRead,
    )


def _geo_parent(db: Session, tenant_id: str, parent_geo_id: str | None, current: Geo | None = None) -> None:
    if not parent_geo_id:
        return
    if current is not None and parent_geo_id == current.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="a geo cannot be its own parent")
    get_scoped_or_404(db, Geo, tenant_id, parent_geo_id)
    if current is not None and any(g.id == current.id for g in geo_path(db, tenant_id, parent_geo_id)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="that parent is below this geo — the hierarchy would loop")


@router.post("/geos", response_model=GeoEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_geo(
    payload: CreateGeoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    require_type_option(db, tenant_id, "geo_type", payload.geo_type)
    _geo_parent(db, tenant_id, payload.parent_geo_id)
    geo = Geo(
        tenant_id=tenant_id, geo_code=payload.geo_code.strip(), name=payload.name, geo_type=payload.geo_type,
        parent_geo_id=payload.parent_geo_id, abbreviation=payload.abbreviation, status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(geo)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"geo_code {payload.geo_code!r} already exists")
    record_audit(db, tenant_id=tenant_id, action="geo.created", entity_type="geo", entity_id=geo.id,
                 actor=actor.label, detail={"geo_code": geo.geo_code, "name": geo.name, "geo_type": geo.geo_type})
    commit_or_conflict(db, f"geo_code {payload.geo_code!r} already exists")
    db.refresh(geo)
    return envelope(GeoRead.model_validate(geo).model_dump(by_alias=True))


@router.post("/geos/seed-template", response_model=SeedGeoTemplateRead, status_code=status.HTTP_201_CREATED)
def seed_geo_template(
    payload: SeedGeoTemplateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Load a shipped table of places once. Rows whose code already exists
    are left alone, so re-running is harmless."""
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    rows = GEO_TEMPLATES[payload.template]
    existing = {
        g.geo_code: g for g in db.scalars(select(Geo).where(Geo.tenant_id == tenant_id))
    }
    english = settings.resolved_locale == "en"
    created = 0
    for code, zh, en, geo_type, parent_code in rows:
        if code in existing:
            continue
        parent = existing.get(parent_code) if parent_code else None
        geo = Geo(
            tenant_id=tenant_id, geo_code=code, name=en if english else zh, geo_type=geo_type,
            parent_geo_id=parent.id if parent is not None else None,
            abbreviation=None, status="active",
            metadata_jsonb={"template": payload.template, "name_zh": zh, "name_en": en},
        )
        db.add(geo)
        db.flush()
        existing[code] = geo
        created += 1
    record_audit(db, tenant_id=tenant_id, action="geo.template_seeded", entity_type="geo",
                 entity_id=existing["CN"].id if "CN" in existing else "",
                 actor=actor.label, detail={"template": payload.template, "created": created})
    db.commit()
    return SeedGeoTemplateRead(template=payload.template, created=created, existing=len(rows) - created)


@router.get("/geos/{geo_id}", response_model=GeoEnvelope, response_model_exclude_unset=True)
def get_geo(
    geo_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    geo = get_scoped_or_404(db, Geo, tenant_id, geo_id)
    return envelope(GeoRead.model_validate(geo).model_dump(by_alias=True))


@router.get("/geos/{geo_id}/path", response_model=GeoListEnvelope, response_model_exclude_unset=True)
def get_geo_path(
    geo_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """The geo and its ancestors, root first — 中国 / 浙江省 / 杭州市."""
    get_scoped_or_404(db, Geo, tenant_id, geo_id)
    chain = list(reversed(geo_path(db, tenant_id, geo_id)))
    return envelope([GeoRead.model_validate(g).model_dump(by_alias=True) for g in chain], len(chain))


@router.patch("/geos/{geo_id}", response_model=GeoEnvelope, response_model_exclude_unset=True)
def update_geo(
    geo_id: str,
    payload: UpdateGeoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    geo = get_scoped_or_404(db, Geo, tenant_id, geo_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("geo_type"):
        require_type_option(db, tenant_id, "geo_type", updates["geo_type"])
    if "parent_geo_id" in updates:
        _geo_parent(db, tenant_id, updates["parent_geo_id"], current=geo)
    if "metadata" in updates:
        geo.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(geo, field, value)
    record_audit(db, tenant_id=tenant_id, action="geo.updated", entity_type="geo", entity_id=geo.id,
                 actor=actor.label, detail={"geo_code": geo.geo_code, "fields": sorted(updates)})
    db.commit()
    db.refresh(geo)
    return envelope(GeoRead.model_validate(geo).model_dump(by_alias=True))


# --- territories -------------------------------------------------------------------


@router.get("/territories", response_model=TerritoryListEnvelope, response_model_exclude_unset=True)
def list_territories(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    parent_territory_id: str | None = None,
    manager_employee_id: str | None = None,
    territory_code: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(Territory).where(Territory.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            Territory.parent_territory_id: parent_territory_id,
            Territory.manager_employee_id: manager_employee_id,
            Territory.territory_code: territory_code,
            Territory.status: status_scope(status_filter),
        },
        keyword=keyword,
        keyword_columns=(cast(Territory.id, String), Territory.territory_code, Territory.name, Territory.description),
        order_by=(Territory.territory_code.asc(), Territory.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=TerritoryRead,
    )


@router.get("/territory-resolution", response_model=TerritoryResolutionEnvelope, response_model_exclude_unset=True)
def resolve(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    geo_id: Annotated[str, Query(description="The place to resolve — a customer's geo, or any geo")],
):
    get_scoped_or_404(db, Geo, tenant_id, geo_id)
    return envelope(resolve_territory(db, tenant_id, geo_id).model_dump(by_alias=True))


def _territory_fields(db: Session, tenant_id: str, fields: dict, current: Territory | None = None) -> None:
    if fields.get("parent_territory_id"):
        if current is not None and fields["parent_territory_id"] == current.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="a territory cannot be its own parent")
        get_scoped_or_404(db, Territory, tenant_id, fields["parent_territory_id"])
    if fields.get("manager_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, fields["manager_employee_id"])


@router.post("/territories", response_model=TerritoryEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_territory(
    payload: CreateTerritoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    _territory_fields(db, tenant_id, payload.model_dump(exclude_unset=True))
    territory = Territory(
        tenant_id=tenant_id, territory_code=payload.territory_code.strip(), name=payload.name,
        parent_territory_id=payload.parent_territory_id, manager_employee_id=payload.manager_employee_id,
        description=payload.description, status=payload.status, metadata_jsonb=payload.metadata,
    )
    db.add(territory)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"territory_code {payload.territory_code!r} already exists")
    record_audit(db, tenant_id=tenant_id, action="territory.created", entity_type="territory",
                 entity_id=territory.id, actor=actor.label,
                 detail={"territory_code": territory.territory_code, "name": territory.name})
    commit_or_conflict(db, f"territory_code {payload.territory_code!r} already exists")
    db.refresh(territory)
    return envelope(TerritoryRead.model_validate(territory).model_dump(by_alias=True))


@router.get("/territories/{territory_id}", response_model=TerritoryEnvelope, response_model_exclude_unset=True)
def get_territory(
    territory_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    territory = get_scoped_or_404(db, Territory, tenant_id, territory_id)
    return envelope(TerritoryRead.model_validate(territory).model_dump(by_alias=True))


@router.patch("/territories/{territory_id}", response_model=TerritoryEnvelope, response_model_exclude_unset=True)
def update_territory(
    territory_id: str,
    payload: UpdateTerritoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    territory = get_scoped_or_404(db, Territory, tenant_id, territory_id)
    updates = payload.model_dump(exclude_unset=True)
    _territory_fields(db, tenant_id, updates, current=territory)
    if "metadata" in updates:
        territory.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(territory, field, value)
    record_audit(db, tenant_id=tenant_id, action="territory.updated", entity_type="territory",
                 entity_id=territory.id, actor=actor.label,
                 detail={"territory_code": territory.territory_code, "fields": sorted(updates)})
    db.commit()
    db.refresh(territory)
    return envelope(TerritoryRead.model_validate(territory).model_dump(by_alias=True))


# --- coverage --------------------------------------------------------------------------


@router.get("/territory-geos", response_model=TerritoryGeoListEnvelope, response_model_exclude_unset=True)
def list_territory_geos(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    territory_id: str | None = None,
    geo_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(TerritoryGeo).where(TerritoryGeo.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={TerritoryGeo.territory_id: territory_id, TerritoryGeo.geo_id: geo_id},
        order_by=(TerritoryGeo.created_at.asc(), TerritoryGeo.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=TerritoryGeoRead,
    )


@router.post("/territory-geos", response_model=TerritoryGeoEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_territory_geo(
    payload: CreateTerritoryGeoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    territory = get_scoped_or_404(db, Territory, tenant_id, payload.territory_id)
    geo = get_scoped_or_404(db, Geo, tenant_id, payload.geo_id)
    row = TerritoryGeo(tenant_id=tenant_id, territory_id=territory.id, geo_id=geo.id, metadata_jsonb=payload.metadata)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="the territory already covers that geo")
    record_audit(db, tenant_id=tenant_id, action="territory.coverage_added", entity_type="territory",
                 entity_id=territory.id, actor=actor.label,
                 detail={"territory_code": territory.territory_code, "geo_code": geo.geo_code})
    db.commit()
    db.refresh(row)
    return envelope(TerritoryGeoRead.model_validate(row).model_dump(by_alias=True))


@router.get("/territory-geos/{row_id}", response_model=TerritoryGeoEnvelope, response_model_exclude_unset=True)
def get_territory_geo(
    row_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, TerritoryGeo, tenant_id, row_id)
    return envelope(TerritoryGeoRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/territory-geos/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_territory_geo(
    row_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, TerritoryGeo, actor.tenant_id, row_id)
    record_audit(db, tenant_id=actor.tenant_id, action="territory.coverage_removed", entity_type="territory",
                 entity_id=row.territory_id, actor=actor.label, detail={"geo_id": row.geo_id})
    db.delete(row)
    db.commit()


# --- members ---------------------------------------------------------------------------


@router.get("/territory-members", response_model=TerritoryMemberListEnvelope, response_model_exclude_unset=True)
def list_territory_members(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    territory_id: str | None = None,
    employee_id: str | None = None,
    role: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(TerritoryMember).where(TerritoryMember.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            TerritoryMember.territory_id: territory_id,
            TerritoryMember.employee_id: employee_id,
            TerritoryMember.role: role,
        },
        order_by=(TerritoryMember.created_at.asc(), TerritoryMember.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=TerritoryMemberRead,
    )


@router.post("/territory-members", response_model=TerritoryMemberEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_territory_member(
    payload: CreateTerritoryMemberRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    territory = get_scoped_or_404(db, Territory, tenant_id, payload.territory_id)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    if payload.role:
        require_type_option(db, tenant_id, "territory_member_role", payload.role)
    if payload.valid_from and payload.valid_until and payload.valid_until < payload.valid_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="valid_until is before valid_from")
    row = TerritoryMember(
        tenant_id=tenant_id, territory_id=territory.id, employee_id=payload.employee_id, role=payload.role,
        valid_from=payload.valid_from, valid_until=payload.valid_until, metadata_jsonb=payload.metadata,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that person is already in the territory")
    record_audit(db, tenant_id=tenant_id, action="territory.member_added", entity_type="territory",
                 entity_id=territory.id, actor=actor.label,
                 detail={"territory_code": territory.territory_code, "employee_id": payload.employee_id, "role": payload.role})
    db.commit()
    db.refresh(row)
    return envelope(TerritoryMemberRead.model_validate(row).model_dump(by_alias=True))


@router.get("/territory-members/{row_id}", response_model=TerritoryMemberEnvelope, response_model_exclude_unset=True)
def get_territory_member(
    row_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, TerritoryMember, tenant_id, row_id)
    return envelope(TerritoryMemberRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/territory-members/{row_id}", response_model=TerritoryMemberEnvelope, response_model_exclude_unset=True)
def update_territory_member(
    row_id: str,
    payload: UpdateTerritoryMemberRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, TerritoryMember, tenant_id, row_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("role"):
        require_type_option(db, tenant_id, "territory_member_role", updates["role"])
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    if row.valid_from and row.valid_until and row.valid_until < row.valid_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="valid_until is before valid_from")
    record_audit(db, tenant_id=tenant_id, action="territory.member_changed", entity_type="territory",
                 entity_id=row.territory_id, actor=actor.label,
                 detail={"employee_id": row.employee_id, "fields": sorted(updates)})
    db.commit()
    db.refresh(row)
    return envelope(TerritoryMemberRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/territory-members/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_territory_member(
    row_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, TerritoryMember, actor.tenant_id, row_id)
    record_audit(db, tenant_id=actor.tenant_id, action="territory.member_removed", entity_type="territory",
                 entity_id=row.territory_id, actor=actor.label, detail={"employee_id": row.employee_id})
    db.delete(row)
    db.commit()
