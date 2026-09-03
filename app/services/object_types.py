from __future__ import annotations

import re
from functools import lru_cache

from fastapi import HTTPException, status
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import validator_for
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ObjectTypeDefinition


# Every builtin collection the object console can browse. Not the same list as
# the machine-backed families in BUILTIN_MACHINES: resource bookings and billing
# accounts are browsable but have no tenant-editable lifecycle, so they are not
# workflow subjects. `tests/test_object_types.py` pins both lists against their
# sources — this one silently lagged four releases behind, which is how invoices
# and payments came to be invisible in the console after they shipped.
BUILTIN_OBJECT_TYPES: tuple[str, ...] = (
    "timesheet_header",
    "employee_leave",
    "expense_claim",
    "purchase_request",
    "sales_quotation",
    "sales_order",
    "sales_return",
    "purchase_order",
    "purchase_return",
    "shipment",
    "picklist",
    "contract",
    "lead",
    "opportunity",
    "invoice",
    "payment",
    "billing_account",
    "resource_booking",
)


# What ORYH already ships, stated so an agent can judge — never enforced here.
#
# Asked to "建一个 Product 自定义对象", an agent would define one, and the
# workspace would then have two answers to "有多少产品": the real catalogue, and
# a shadow of it that no order line, price row or inventory item can ever point
# at. Nothing stopped a custom `invoice` beside the invoice document family
# either.
#
# The server does not refuse it. Whether a company's "product" is our product is
# a reading of their business, and a records layer that decides that is deciding
# what their words mean. What the server owes is the FACT — here is what already
# exists, in the words people would reach for — and the agent, which has the
# person in front of it, does the rest. It can ask; this cannot.
#
# DERIVED from the REST surface, never listed. A collection a tenant can already
# GET is a thing ORYH ships, so a concept added next month appears here the day
# its endpoint does, with nobody remembering to come back. Five separate defects
# in this codebase have been a hand-maintained list drifting from the registry it
# shadowed; a sixth was not worth writing.
_COLLECTION_PATH = re.compile(r"^/api/v1/([a-z][a-z0-9-]*)$")

_IRREGULAR_ALIASES: dict[str, str] = {
    # Words people reach for that are not our collection names. Short on
    # purpose: this is a hint an agent weighs, so a wrong entry costs a
    # conversation rather than a refusal — but a long list of guesses is still
    # noise dressed as knowledge. Genuinely ambiguous words ("account": a
    # customer, or a billing account?) are left out; the agent can see both and
    # ask which was meant.
    "client": "customers",
    "supplier": "vendors",
    "staff": "employees",
    "goods": "products",
}


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("ses", "xes", "ches", "shes")):
        return name[:-2]
    if name.endswith("s"):
        return name[:-1]
    return name


@lru_cache(maxsize=1)
def builtin_object_vocabulary() -> tuple[dict, ...]:
    """Every shipped collection and the words that mean it.

    Cached: the REST surface cannot change while the process runs, and the
    OpenAPI document is expensive to build the first time.
    """
    from app.main import app  # deferred: app imports the routes that import this

    by_collection: dict[str, set[str]] = {}
    for path, operations in app.openapi()["paths"].items():
        match = _COLLECTION_PATH.match(path)
        if match is None or "get" not in operations:
            continue
        collection = match.group(1).replace("-", "_")
        names = by_collection.setdefault(collection, {collection})
        names.add(_singular(collection))
    for alias, collection in _IRREGULAR_ALIASES.items():
        by_collection.setdefault(collection, {collection}).add(alias)
    return tuple(
        {
            "object_type": collection,
            "path": "/" + collection.replace("_", "-"),
            "also_called": sorted(names - {collection}),
        }
        for collection, names in sorted(by_collection.items())
    )


def builtin_object_names() -> dict[str, str]:
    """word → the collection it means. For a caller that wants a lookup."""
    return {
        name: entry["object_type"]
        for entry in builtin_object_vocabulary()
        for name in (entry["object_type"], *entry["also_called"])
    }


def ensure_valid_json_schema(schema: dict) -> None:
    """Reject definitions whose json_schema is not itself a valid JSON Schema."""
    validator_cls = validator_for(schema, default=Draft202012Validator)
    try:
        validator_cls.check_schema(schema)
    except Exception as exc:  # jsonschema raises SchemaError (a ValidationError subclass)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"field rules are not valid: {exc}",
        ) from exc


def get_active_definition(db: Session, tenant_id: str, object_type: str) -> ObjectTypeDefinition | None:
    return db.scalar(
        select(ObjectTypeDefinition).where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == "business_object",
            ObjectTypeDefinition.object_type == object_type,
            ObjectTypeDefinition.status == "active",
        )
    )


def validate_business_object_payload(
    db: Session,
    tenant_id: str,
    object_type: str,
    payload: dict,
) -> None:
    """Validate payload against the tenant's active definition for this
    object_type. Types without a definition stay schema-less by design."""
    definition = get_active_definition(db, tenant_id, object_type)
    if definition is None or not definition.json_schema:
        return
    validator_cls = validator_for(definition.json_schema, default=Draft202012Validator)
    try:
        validator_cls(definition.json_schema).validate(payload)
    except ValidationError as exc:
        path = "$" + "".join(f".{p}" if isinstance(p, str) else f"[{p}]" for p in exc.absolute_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"payload does not match the '{object_type}' definition "
                f"(version {definition.version}) at {path}: {exc.message}"
            ),
        ) from exc
