"""The objects a tenant invents, and the todos and approval facts about anything.

Split out of `routes.py`: object type definitions and the business objects that
instantiate them, the links between those objects, approval targets, approval
records, and todos.

They travel together because the call graph makes them one component, not
because they are one subject. A todo or an approval fact may point at ANY
entity type, and resolving that reference — `ensure_referenced_entity_exists`,
`scoped_write_target` — is the same work `business-objects` does for itself.
Splitting them would put one domain module's import inside another, which is
the shape `common.py` exists to prevent.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    DOCUMENT_FAMILIES,
    apply_status_change,
    archive_row,
    cancel_todos_for,
    envelope,
    exclude_rows_with_open_todo,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    requested_pagination,
    require_hosted_write_scope,
    retire_open_work_if_finished,
    visible_payroll_filter,
)
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, require_permission
from app.core.entity_types import (
    APPROVAL_ENTITY_TYPES,
    DECIDED_APPROVAL_ACTIONS,
    OPERATOR_CONFLICT_CLOSURE_KEY,
    TODO_ENTITY_TYPES,
)
from app.db.session import get_db
from app.models import (
    ApprovalRecord,
    AuditLog,
    BillingAccount,
    BusinessObject,
    BusinessObjectLink,
    Employee,
    EmployeeLeave,
    ExpenseClaim,
    ExpenseItem,
    Contract,
    Invoice,
    Lead,
    Picklist,
    Opportunity,
    ObjectTypeDefinition,
    Payment,
    Project,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    ResourceBooking,
    SalesOrder,
    Shipment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationItem,
    TimesheetEntry,
    TimesheetHeader,
    Todo,
    User,
    WorkflowDefinition,
)
from app.schemas import (
    ApprovalRecordEnvelope,
    ApprovalRecordListEnvelope,
    ApprovalRecordRead,
    ApprovalTargetEnvelope,
    ApprovalTargetListEnvelope,
    ApprovalTargetRead,
    AuditLogRead,
    BuiltinObjectTypeEnvelope,
    BulkTodoCreateRequest,
    BulkTodoEnvelope,
    BusinessObjectDetailEnvelope,
    BusinessObjectDetailRead,
    BusinessObjectEnvelope,
    BusinessObjectLinkEnvelope,
    BusinessObjectLinkListEnvelope,
    BusinessObjectLinkRead,
    BusinessObjectListEnvelope,
    BusinessObjectRead,
    CreateApprovalRecordRequest,
    CreateApprovalTargetRequest,
    CreateBusinessObjectLinkRequest,
    CreateBusinessObjectRequest,
    CreateObjectTypeDefinitionRequest,
    CreateTodoRequest,
    DeleteApprovalTargetRequest,
    DeleteBusinessObjectRequest,
    ObjectDirectoryEntryRead,
    ObjectDirectoryEnvelope,
    ObjectTypeDefinitionEnvelope,
    ObjectTypeDefinitionListEnvelope,
    ObjectTypeDefinitionRead,
    RestoreApprovalTargetRequest,
    RestoreBusinessObjectRequest,
    TodoEnvelope,
    TodoLastApproval,
    TodoListEnvelope,
    TodoRead,
    TodoTargetSummary,
    UpdateApprovalTargetRequest,
    UpdateBusinessObjectRequest,
    UpdateObjectTypeDefinitionRequest,
    UpdateTodoRequest,
    WorkflowDefinitionRead,
)
from app.services.audit import record_audit
from app.services.object_types import (
    BUILTIN_OBJECT_TYPES,
    builtin_object_vocabulary,
    ensure_valid_json_schema,
    refuse_shadow_of_shipped,
    validate_business_object_payload,
)
from app.services.state_machines import (
    editable_states,
    ensure_valid_state_machine,
    get_builtin_machine,
    get_business_object_machine,
    is_terminal_state,
    validate_business_object_status,
    validate_business_object_status_filter,
)

router = APIRouter()


# --- what a todo or an approval fact may point at, and when ----------------


def scoped_write_target(db: Session, tenant_id: str, entity_type: str, entity_id: str):
    """The row a todo or approval fact points at, for `require_hosted_write_scope`.
    Builtins resolve through the family registry; anything else is a custom
    business object whose entity_type is its object_type."""
    model = TODO_TARGET_MODELS.get(entity_type)
    if model is not None:
        return db.scalar(
            select(model).where(model.tenant_id == tenant_id, model.id == entity_id)
        )
    return db.scalar(
        select(BusinessObject).where(
            BusinessObject.tenant_id == tenant_id,
            BusinessObject.id == entity_id,
            BusinessObject.object_type == entity_type,
        )
    )


def ensure_no_operator_closure_marker(metadata: dict | None) -> None:
    """A tenant may not mint its own historical-conflict closure.

    The typed column is unwritable through the API, which is the guarantee the
    exemption rests on — but the migration that fills that column promotes this
    metadata key, and metadata IS caller-supplied. Before an environment has
    run that migration, anybody holding `approval.record` could plant the word
    and be exempted from the one-decision rule the moment it does. The key
    ships in the open-core export, so it is public knowledge, not a secret.

    Same shape as `workspace.py`'s `ensure_label_is_not_impersonation`: the real
    guarantee is structural, and this keeps the tenant-supplied side from
    imitating it. A genuine closure is written by the operator script straight
    to the database, which never passes through here.
    """
    if metadata and OPERATOR_CONFLICT_CLOSURE_KEY in metadata:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"metadata key {OPERATOR_CONFLICT_CLOSURE_KEY!r} is reserved for "
                "an authorized operator remediation and cannot be set through "
                "the API"
            ),
        )


def ensure_node_undecided(db: Session, tenant_id: str, payload) -> None:
    """One decision per node — the readable half of a guard the index enforces.

    The natural key includes `action`, which makes a retry idempotent and used
    to let `approved` and `rejected` both stand at the same round and sequence:
    one seat, two contradictory decisions, nothing saying which one counts.

    Nobody has to misbehave to get there. The same approver opens two agent
    sessions, lists the queue in both, decides in one — and the other is now
    holding a list that was true when it was read. That is the ordinary shape
    of the mistake, which is why the server takes it rather than leaving it to
    an agent's memory of what it has already done.

    The 409 names the decision that already stands, because "conflict" alone
    sends an agent looking for its own error when the answer is that a
    colleague — or its other self — got there first.
    """
    if payload.action not in DECIDED_APPROVAL_ACTIONS:
        return
    closed_history = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.historical_conflict_closed.is_(True),
        )
    )
    if closed_history is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"round {payload.round_no} step {payload.sequence_no} is a closed "
                "historical approval conflict. Do not decide it again; retire its "
                "remaining work through the document or Todo workflow."
            ),
        )
    decided = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.action.in_(DECIDED_APPROVAL_ACTIONS),
            ApprovalRecord.historical_conflict_closed.is_(False),
        )
    )
    if decided is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"round {payload.round_no} step {payload.sequence_no} was already "
            f"{decided.action} by {decided.approver_id} at {decided.acted_at} — "
            "a step holds one decision. Re-read the approval trail before acting: "
            "this one is settled, and if it needs revisiting that is a new round, "
            "not a second decision in this one"
        ),
    )


def require_submission_before_decision(payload) -> None:
    """Sequence 1 of a round is the submission; a decision cannot sit there.

    The audit asks that every decided approval have a `submitted` record at a
    LOWER sequence. Nothing enforced it, and `sequence_no` defaults to 1 — so
    an agent recording an approval without passing a sequence put the decision
    at the submission's own place, where no submission can ever precede it. An
    integrity audit found 133 such rows. Cleaning them would not have stopped
    the next one; the default did that.

    The refusal is deliberately about the ARITHMETIC and not about the rest of
    the trail. Whether a decision may be recorded for a document that was
    never submitted is the tenant's flow to define — the server records the
    facts an agent reports and does not adjudicate their order beyond this:
    position 1 is taken, by definition, by the submission. Refusing more than
    that would block a historical import, an auto-approval, or a
    tenant-defined object whose flow has no submission step at all.
    """
    if payload.action in DECIDED_APPROVAL_ACTIONS and payload.sequence_no <= 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"sequence_no 1 is the submission; a {payload.action} record "
                "belongs after it. Use the sequence the workflow admin put on "
                "the todo (metadata.sequence_no), or the next free sequence in "
                "this round."
            ),
        )


def ensure_business_object_not_deleted(business_object: BusinessObject, detail: str = "BusinessObject not found") -> None:
    if business_object.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def get_active_business_object_or_404(db: Session, tenant_id: str, business_object_id: str) -> BusinessObject:
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    ensure_business_object_not_deleted(business_object)
    return business_object


def get_active_approval_target_or_404(db: Session, tenant_id: str, approval_target_id: str) -> BusinessObject:
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, approval_target_id)
    ensure_business_object_not_deleted(business_object, detail="ApprovalTarget not found")
    return business_object


def same_todo_assignment(existing: Todo, payload: CreateTodoRequest) -> bool:
    """Whether a create request is a retry of the open todo it collided with.

    Employee + entity already matched to get here. What separates "the same
    assignment again" from "a new assignment on a stale view" is the flow
    position the assigner wrote down: a second finance review in round 2 is a
    genuinely different todo from the round-1 one, even for the same person on
    the same document. Round/sequence live in metadata because oryh never
    interprets them — it only has to notice when they differ."""
    if (existing.todo_type or None) != (payload.todo_type or None):
        return False
    existing_metadata = existing.metadata_jsonb or {}
    requested_metadata = payload.metadata or {}
    return all(
        existing_metadata.get(field) == requested_metadata.get(field)
        for field in ("round_no", "sequence_no")
    )


# What a todo or an approval fact may point at.
#
# Derived from DOCUMENT_FAMILIES rather than restated, because restating it is
# how this broke: the same list lived in an if-chain here, in a CHECK
# constraint in the migrations, and in DOCUMENT_FAMILIES, and the three drifted.
# Invoices, payments and purchase orders reached the API fine and were refused
# by the database — a 500 on an ordinary approval request, on a path
# `$oryh-payment-approval-flow` tells agents to walk.
#
# `tests/test_entity_reference_types.py` pins these against the live CHECK
# constraint, so the next family added fails the build instead of production.
ALLOWED_APPROVAL_ENTITY_TYPES: frozenset[str] = frozenset(APPROVAL_ENTITY_TYPES)


ALLOWED_TODO_ENTITY_TYPES: frozenset[str] = frozenset(TODO_ENTITY_TYPES)


def ensure_referenced_entity_exists(
    db: Session, tenant_id: str, entity_type: str, entity_id: str, *,
    allowed: frozenset[str], label: str,
):
    """One resolver for both todos and approval facts. Returns the row.

    An unknown type is refused here rather than left to the database. The
    approval path used to fall through an if-chain with no else, so a type it
    did not recognise skipped the existence check entirely and reached the
    CHECK constraint — which answered with a 500 rather than a sentence.

    It returns the row it resolved because it had already fetched it and threw
    it away, and the approval path needs the target's `created_at` to refuse a
    decision recorded before the thing it decides existed.
    """
    if entity_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported {label} entity type {entity_type!r} — "
                f"expected one of: {', '.join(sorted(allowed))}"
            ),
        )
    model = TODO_TARGET_MODELS.get(entity_type)
    if model is not None:
        return get_active_document_or_404(db, model, tenant_id, entity_id)
    if entity_type == "approval_target":
        return get_active_approval_target_or_404(db, tenant_id, entity_id)
    if entity_type == "business_object":
        return get_active_business_object_or_404(db, tenant_id, entity_id)
    return get_scoped_or_404(db, Project, tenant_id, entity_id)


# An agent's host clock is not the server's. Wide enough that an honestly
# stamped "now" never trips the future check, narrow enough that a date pulled
# out of a document never passes it.
ACTED_AT_CLOCK_SKEW = timedelta(minutes=5)


def resolve_acted_at(supplied: datetime | None, target) -> datetime:
    """When the decision happened — the server's answer unless told otherwise.

    This used to be a required field, which meant every caller had to produce a
    timestamp and an agent has no clock. Every skill example showed a literal
    (`"2026-07-11T09:00:00Z"`), so an agent filling the template in took the
    most plausible date in front of it — usually one off the document it was
    approving. Production ended up with approvals recorded before the thing
    they approved existed, which is not a wrong number so much as a trail that
    cannot be true.

    So the server stamps it. Supplying one is now a deliberate act rather than
    a tax on every write, and the two impossible shapes are refused:

    - **the future**, beyond clock skew: nobody decides in advance, and this is
      the shape a guessed date takes when the guess runs forward;
    - **before the target existed**: the shape it takes running backward, and
      the one found in production.

    Backfilling stays possible and one case is already legitimate — the missing
    `submitted` fact takes the document's own `submitted_at`, a stored fact
    rather than an invention, and it satisfies both rules by construction.
    Recording an approval that genuinely predates its record — a historical
    import — is refused: that path does not exist through this API today, and
    when it does it should arrive as a designed feature rather than as the
    absence of a check.
    """
    now = datetime.now(timezone.utc)
    if supplied is None:
        return now

    acted = supplied if supplied.tzinfo else supplied.replace(tzinfo=timezone.utc)
    if acted > now + ACTED_AT_CLOCK_SKEW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"acted_at {acted.isoformat()} is in the future — a decision cannot be "
                "recorded before it is made. Omit acted_at and the server stamps the "
                "moment of the call."
            ),
        )

    created = getattr(target, "created_at", None)
    if created is not None:
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        if acted < created:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"acted_at {acted.isoformat()} is before this record existed "
                    f"({created.isoformat()}) — the trail would say it was decided "
                    "before it was created. Omit acted_at and the server stamps the "
                    "moment of the call; supply one only when the person you are "
                    "acting for told you the decision happened at another time, and "
                    "never infer it from a date on the document."
                ),
            )
    return acted


def ensure_todo_entity_exists(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> None:
    ensure_referenced_entity_exists(
        db, tenant_id, entity_type, entity_id, allowed=ALLOWED_TODO_ENTITY_TYPES, label="todo"
    )


# --- approval targets: something to approve that is not a document ---------


@router.get(
    "/approval-targets",
    response_model=ApprovalTargetListEnvelope,
    response_model_exclude_unset=True,
)
def list_approval_targets(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    target_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    stmt = select(BusinessObject).where(BusinessObject.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BusinessObject.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            BusinessObject.object_type: target_type,
            BusinessObject.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObject.title,
            BusinessObject.summary,
            BusinessObject.source_text,
            cast(BusinessObject.id, String),
        ),
        order_by=(BusinessObject.created_at.desc(), BusinessObject.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ApprovalTargetRead,
    )


@router.post(
    "/approval-targets",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def create_approval_target(
    payload: CreateApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "business_object.write", payload.target_type)
    validate_business_object_payload(db, actor.tenant_id, payload.target_type, payload.payload)
    validate_business_object_status(
        db, actor.tenant_id, payload.target_type, current=None, new=payload.status
    )
    approval_target = BusinessObject(
        tenant_id=actor.tenant_id,
        object_type=payload.target_type,
        title=payload.title,
        summary=payload.summary,
        payload_jsonb=payload.payload,
        source_text=payload.source_text,
        status=payload.status,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(approval_target)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="business_object.created",
        entity_type="business_object",
        entity_id=approval_target.id,
        actor=actor.label,
        detail={"object_type": approval_target.object_type, "title": approval_target.title, "status": approval_target.status},
    )
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.get(
    "/approval-targets/{approval_target_id}",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def get_approval_target(
    approval_target_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    approval_target = get_scoped_or_404(db, BusinessObject, tenant_id, approval_target_id)
    if not include_deleted:
        ensure_business_object_not_deleted(approval_target, detail="ApprovalTarget not found")
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.patch(
    "/approval-targets/{approval_target_id}",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def update_approval_target(
    approval_target_id: str,
    payload: UpdateApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    approval_target = get_active_approval_target_or_404(db, tenant_id, approval_target_id)
    updates = payload.model_dump(exclude_unset=True)
    final_type = updates.get("target_type", approval_target.object_type)
    require_permission(actor, "business_object.write", final_type)
    final_payload = updates.get("payload", approval_target.payload_jsonb)
    validate_business_object_payload(db, tenant_id, final_type, final_payload)
    if "status" in updates and updates["status"] != approval_target.status:
        require_permission(actor, "business_object.advance", final_type)
        validate_business_object_status(
            db, tenant_id, final_type, current=approval_target.status, new=updates["status"]
        )
        record_audit(
            db,
            tenant_id=tenant_id,
            action="business_object.status_changed",
            entity_type="business_object",
            entity_id=approval_target.id,
            actor=actor.label,
            detail={"object_type": final_type, "from": approval_target.status, "to": updates["status"]},
        )
    if "payload" in updates:
        approval_target.payload_jsonb = updates.pop("payload")
    if "target_type" in updates:
        approval_target.object_type = updates.pop("target_type")
    for field, value in updates.items():
        setattr(approval_target, field, value)
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.delete("/approval-targets/{approval_target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_approval_target(
    approval_target_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: DeleteApprovalTargetRequest | None = None,
):
    approval_target = get_scoped_or_404(db, BusinessObject, actor.tenant_id, approval_target_id)
    require_permission(actor, "business_object.write", approval_target.object_type)
    if approval_target.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    approval_target.deleted_at = datetime.now(timezone.utc)
    approval_target.deleted_by = attributed(actor, payload.deleted_by if payload else None)
    approval_target.delete_reason = payload.delete_reason if payload else None
    cancel_todos_for(
        db, actor, "approval_target", approval_target.id,
        reason="approval target deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/approval-targets/{approval_target_id}/restore",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def restore_approval_target(
    approval_target_id: str,
    payload: RestoreApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    approval_target = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, approval_target_id
    )
    require_permission(actor, "business_object.write", approval_target.object_type)
    if approval_target.deleted_at is None:
        return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))
    approval_target.deleted_at = None
    approval_target.deleted_by = None
    approval_target.delete_reason = None
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


# --- object type definitions: the types a tenant invents for itself --------


@router.get(
    "/object-type-definitions",
    response_model=ObjectTypeDefinitionListEnvelope,
    response_model_exclude_unset=True,
)
def list_object_type_definitions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    object_type: str | None = None,
    entity_kind: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db, select(ObjectTypeDefinition).where(ObjectTypeDefinition.tenant_id == tenant_id),
        filters={
            ObjectTypeDefinition.object_type: object_type,
            ObjectTypeDefinition.entity_kind: entity_kind,
            ObjectTypeDefinition.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            ObjectTypeDefinition.object_type,
            ObjectTypeDefinition.title,
            ObjectTypeDefinition.description,
        ),
        order_by=(ObjectTypeDefinition.object_type.asc(), ObjectTypeDefinition.id.asc()),
        pagination=requested_pagination(page, size),
        read_model=ObjectTypeDefinitionRead, by_alias=False,
    )


@router.get("/builtin-object-types", response_model=BuiltinObjectTypeEnvelope)
def get_builtin_object_types(
    actor: Annotated[Actor, Depends(get_actor)],
):
    """What ORYH already ships, so an agent can tell whether a custom object is
    one of these under another name.

    Asked to "建一个 Product 自定义对象", an agent would define one, and the
    workspace would end up with two answers to "有多少产品" — the real catalogue
    and a shadow of it that no order line, price or inventory row can ever point
    at. Once the shadow has data the two cannot be merged back.

    The exact names listed here (the collection, its singular, its synonyms)
    are REFUSED as generic-object names at creation. Whether a company's "product"
    is our product is a reading of THEIR business, and the agent is the one with
    the person in front of it — it can ask, and the server cannot. So there is no
    409 here and none on the create paths: read this first, and if it matches,
    say so rather than defining a second one.

    Ungated, like the skill catalogue and for the same reason: it is a trigger
    index, and it reveals nothing about this workspace's data.
    """
    return envelope(list(builtin_object_vocabulary()))


@router.get(
    "/object-directory",
    response_model=ObjectDirectoryEnvelope,
    response_model_exclude_unset=True,
)
def get_object_directory(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Discover every object collection available in the tenant console.

    Custom types are the union of definitions and actual data, so schema-less
    types created before the definition catalog was introduced remain visible.
    Counts include soft-deleted records because the object console can browse
    them with ``include_deleted=true``.
    """
    tenant_id = actor.tenant_id
    # "how many payslips did this company issue" is itself worth hiding
    payroll_gate = visible_payroll_filter(actor)
    invoice_count_stmt = select(func.count()).select_from(Invoice).where(
        Invoice.tenant_id == tenant_id
    )
    if payroll_gate is not None:
        invoice_count_stmt = invoice_count_stmt.where(payroll_gate)
    builtin_counts = {
        "timesheet_header": db.scalar(
            select(func.count()).select_from(TimesheetHeader).where(
                TimesheetHeader.tenant_id == tenant_id
            )
        )
        or 0,
        "employee_leave": db.scalar(
            select(func.count()).select_from(EmployeeLeave).where(
                EmployeeLeave.tenant_id == tenant_id
            )
        )
        or 0,
        "expense_claim": db.scalar(
            select(func.count()).select_from(ExpenseClaim).where(
                ExpenseClaim.tenant_id == tenant_id
            )
        )
        or 0,
        "purchase_request": db.scalar(
            select(func.count()).select_from(PurchaseRequest).where(
                PurchaseRequest.tenant_id == tenant_id
            )
        )
        or 0,
        "sales_quotation": db.scalar(
            select(func.count()).select_from(SalesQuotation).where(
                SalesQuotation.tenant_id == tenant_id
            )
        )
        or 0,
        # orders and returns share a table; the directory splits them by kind
        # so neither row is counted under two names
        "sales_order": db.scalar(
            select(func.count()).select_from(SalesOrder).where(
                SalesOrder.tenant_id == tenant_id,
                SalesOrder.order_kind == "order",
            )
        )
        or 0,
        "sales_return": db.scalar(
            select(func.count()).select_from(SalesOrder).where(
                SalesOrder.tenant_id == tenant_id,
                SalesOrder.order_kind == "return",
            )
        )
        or 0,
        "purchase_order": db.scalar(
            select(func.count()).select_from(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.order_kind == "order",
            )
        )
        or 0,
        "purchase_return": db.scalar(
            select(func.count()).select_from(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.order_kind == "return",
            )
        )
        or 0,
        "shipment": db.scalar(
            select(func.count()).select_from(Shipment).where(Shipment.tenant_id == tenant_id)
        )
        or 0,
        "contract": db.scalar(
            select(func.count()).select_from(Contract).where(
                Contract.tenant_id == tenant_id
            )
        )
        or 0,
        "picklist": db.scalar(
            select(func.count()).select_from(Picklist).where(
                Picklist.tenant_id == tenant_id
            )
        )
        or 0,
        "lead": db.scalar(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id
            )
        )
        or 0,
        "opportunity": db.scalar(
            select(func.count()).select_from(Opportunity).where(
                Opportunity.tenant_id == tenant_id
            )
        )
        or 0,
        "invoice": db.scalar(invoice_count_stmt) or 0,
        "payment": db.scalar(
            select(func.count()).select_from(Payment).where(Payment.tenant_id == tenant_id)
        )
        or 0,
        "billing_account": db.scalar(
            select(func.count()).select_from(BillingAccount).where(
                BillingAccount.tenant_id == tenant_id
            )
        )
        or 0,
        "resource_booking": db.scalar(
            select(func.count()).select_from(ResourceBooking).where(
                ResourceBooking.tenant_id == tenant_id
            )
        )
        or 0,
    }
    # live rows only: a type whose every row was deleted is not a type the
    # workspace still has — a legacy dump archived out of the way must
    # leave the directory too, or every agent keeps seeing it
    custom_counts = dict(
        db.execute(
            select(BusinessObject.object_type, func.count())
            .where(BusinessObject.tenant_id == tenant_id, BusinessObject.deleted_at.is_(None))
            .group_by(BusinessObject.object_type)
        ).all()
    )
    definitions = db.scalars(
        select(ObjectTypeDefinition).where(ObjectTypeDefinition.tenant_id == tenant_id)
    ).all()
    definition_by_key = {
        (definition.entity_kind, definition.object_type): definition
        for definition in definitions
    }
    defined_custom_types = {
        definition.object_type
        for definition in definitions
        if definition.entity_kind == "business_object"
    }
    entries = [
        ObjectDirectoryEntryRead(
            entity_kind="builtin",
            object_type=object_type,
            count=builtin_counts[object_type],
            title=(
                definition_by_key[("builtin", object_type)].title
                if ("builtin", object_type) in definition_by_key
                else None
            ),
            definition_status=(
                definition_by_key[("builtin", object_type)].status
                if ("builtin", object_type) in definition_by_key
                else None
            ),
        )
        for object_type in BUILTIN_OBJECT_TYPES
    ]
    entries.extend(
        ObjectDirectoryEntryRead(
            entity_kind="business_object",
            object_type=object_type,
            count=custom_counts.get(object_type, 0),
            title=(
                definition_by_key[("business_object", object_type)].title
                if ("business_object", object_type) in definition_by_key
                else None
            ),
            definition_status=(
                definition_by_key[("business_object", object_type)].status
                if ("business_object", object_type) in definition_by_key
                else None
            ),
        )
        for object_type in sorted(defined_custom_types | set(custom_counts))
    )
    return envelope([entry.model_dump() for entry in entries], len(entries))


@router.post(
    "/object-type-definitions",
    status_code=status.HTTP_201_CREATED,
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def create_object_type_definition(
    payload: CreateObjectTypeDefinitionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    if payload.entity_kind == "business_object":
        refuse_shadow_of_shipped(payload.object_type)
    ensure_valid_json_schema(payload.json_schema)
    if payload.state_machine is not None:
        ensure_valid_state_machine(
            payload.state_machine, entity_kind=payload.entity_kind, object_type=payload.object_type
        )
    elif payload.entity_kind == "builtin":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="builtin entity definitions must include a state_machine",
        )
    existing = db.scalar(
        select(ObjectTypeDefinition).where(
            ObjectTypeDefinition.tenant_id == actor.tenant_id,
            ObjectTypeDefinition.entity_kind == payload.entity_kind,
            ObjectTypeDefinition.object_type == payload.object_type,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a definition for this object_type already exists; update it instead",
        )
    definition = ObjectTypeDefinition(
        tenant_id=actor.tenant_id,
        entity_kind=payload.entity_kind,
        object_type=payload.object_type,
        title=payload.title,
        description=payload.description,
        json_schema=payload.json_schema,
        state_machine=payload.state_machine,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.get(
    "/object-type-definitions/{definition_id}",
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def get_object_type_definition(
    definition_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    # Agents hold natural names ("warranty_card"), not definition ids — four
    # of a live E2E audit's six 500s were exactly this call with an object_type in the
    # id slot. The ref resolves either way, like roles do.
    try:
        uuid.UUID(str(definition_id))
    except ValueError:
        definition = db.scalar(
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.tenant_id == tenant_id,
                ObjectTypeDefinition.object_type == definition_id,
            )
        )
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="ObjectTypeDefinition not found"
            )
    else:
        definition = get_scoped_or_404(db, ObjectTypeDefinition, tenant_id, definition_id)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.patch(
    "/object-type-definitions/{definition_id}",
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def update_object_type_definition(
    definition_id: str,
    payload: UpdateObjectTypeDefinitionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    definition = get_scoped_or_404(db, ObjectTypeDefinition, actor.tenant_id, definition_id)
    updates = payload.model_dump(exclude_unset=True)
    version_bumped = False
    if "json_schema" in updates:
        ensure_valid_json_schema(updates["json_schema"])
        if updates["json_schema"] != definition.json_schema:
            definition.version += 1
            version_bumped = True
        definition.json_schema = updates.pop("json_schema")
    if "state_machine" in updates:
        machine = updates.pop("state_machine")
        if machine is None and definition.entity_kind == "builtin":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="builtin entity definitions must keep a state_machine",
            )
        if machine is not None:
            ensure_valid_state_machine(
                machine, entity_kind=definition.entity_kind, object_type=definition.object_type
            )
        if machine != definition.state_machine and not version_bumped:
            definition.version += 1
        definition.state_machine = machine
    for field, value in updates.items():
        setattr(definition, field, value)
    db.commit()
    db.refresh(definition)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.delete("/object-type-definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_object_type_definition(
    definition_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ObjectTypeDefinition, definition_id, permission="object_types.manage")


# --- business objects: rows of those types, and the links between them -----


def parse_payload_match(payload_match: str | None) -> dict:
    if not payload_match:
        return {}
    try:
        parsed = json.loads(payload_match)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="payload_match must be a JSON object"
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(value, (str, int, float, bool)) for value in parsed.values()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload_match must be a flat JSON object of scalar values",
        )
    return parsed


@router.get(
    "/business-objects",
    response_model=BusinessObjectListEnvelope,
    response_model_exclude_unset=True,
)
def list_business_objects(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    object_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    payload_match: str | None = None,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_business_object_status_filter(db, tenant_id, object_type, status_filter)
    stmt = select(BusinessObject).where(BusinessObject.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BusinessObject.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, BusinessObject, tenant_id, "business_object")
    for key, value in parse_payload_match(payload_match).items():
        element = BusinessObject.payload_jsonb[key]
        if isinstance(value, bool):
            stmt = stmt.where(element.as_boolean() == value)
        elif isinstance(value, int):
            stmt = stmt.where(element.as_integer() == value)
        elif isinstance(value, float):
            stmt = stmt.where(element.as_float() == value)
        else:
            stmt = stmt.where(element.as_string() == value)
    return list_rows(
        db, stmt,
        filters={
            BusinessObject.object_type: object_type,
            BusinessObject.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObject.title,
            BusinessObject.summary,
            BusinessObject.source_text,
            BusinessObject.object_type,
            cast(BusinessObject.id, String),
        ),
        order_by=(BusinessObject.created_at.desc(), BusinessObject.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=BusinessObjectRead,
    )


@router.post(
    "/business-objects",
    status_code=status.HTTP_201_CREATED,
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def create_business_object(
    payload: CreateBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "business_object.write", payload.object_type)
    refuse_shadow_of_shipped(payload.object_type)
    validate_business_object_payload(db, actor.tenant_id, payload.object_type, payload.payload)
    validate_business_object_status(
        db, actor.tenant_id, payload.object_type, current=None, new=payload.status
    )
    business_object = BusinessObject(
        tenant_id=actor.tenant_id,
        object_type=payload.object_type,
        title=payload.title,
        summary=payload.summary,
        payload_jsonb=payload.payload,
        source_text=payload.source_text,
        status=payload.status,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(business_object)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="business_object.created",
        entity_type="business_object",
        entity_id=business_object.id,
        actor=actor.label,
        detail={"object_type": business_object.object_type, "title": business_object.title, "status": business_object.status},
    )
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-objects/{business_object_id}",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object(
    business_object_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    if not include_deleted:
        ensure_business_object_not_deleted(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-objects/{business_object_id}/detail",
    response_model=BusinessObjectDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object_detail(
    business_object_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    """Return the related records needed to render an object detail view.

    Approval/todo rows created through the legacy ``approval_target`` alias are
    included alongside canonical ``business_object`` rows so the activity
    timeline remains complete during migration.
    """
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    if not include_deleted:
        ensure_business_object_not_deleted(business_object)

    links = db.scalars(
        select(BusinessObjectLink)
        .where(
            BusinessObjectLink.tenant_id == tenant_id,
            or_(
                BusinessObjectLink.source_object_id == business_object_id,
                BusinessObjectLink.target_object_id == business_object_id,
            ),
        )
        .order_by(BusinessObjectLink.created_at.desc(), BusinessObjectLink.id.desc())
    ).all()
    approval_records = db.scalars(
        select(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type.in_(("business_object", "approval_target")),
            ApprovalRecord.entity_id == business_object_id,
        )
        .order_by(
            ApprovalRecord.round_no.asc(),
            ApprovalRecord.sequence_no.asc(),
            ApprovalRecord.acted_at.asc(),
            ApprovalRecord.id.asc(),
        )
    ).all()
    todos = db.scalars(
        select(Todo)
        .where(
            Todo.tenant_id == tenant_id,
            Todo.entity_type.in_(("business_object", "approval_target")),
            Todo.entity_id == business_object_id,
        )
        .order_by(Todo.created_at.desc(), Todo.id.desc())
    ).all()
    audit_logs = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.entity_type.in_(("business_object", "approval_target")),
            AuditLog.entity_id == business_object_id,
        )
        .order_by(AuditLog.id.desc())
        .limit(200)
    ).all()
    object_type_definition = db.scalar(
        select(ObjectTypeDefinition)
        .where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == "business_object",
            ObjectTypeDefinition.object_type == business_object.object_type,
        )
        .order_by(ObjectTypeDefinition.version.desc(), ObjectTypeDefinition.created_at.desc())
        .limit(1)
    )
    workflow_definitions = db.scalars(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.tenant_id == tenant_id,
            WorkflowDefinition.entity_kind == "business_object",
            WorkflowDefinition.object_type == business_object.object_type,
        )
        .order_by(
            WorkflowDefinition.name.asc(),
            WorkflowDefinition.version.desc(),
            WorkflowDefinition.id.desc(),
        )
    ).all()
    detail = BusinessObjectDetailRead(
        business_object=BusinessObjectRead.model_validate(business_object),
        links=[BusinessObjectLinkRead.model_validate(item) for item in links],
        approval_records=[ApprovalRecordRead.model_validate(item) for item in approval_records],
        todos=[TodoRead.model_validate(item) for item in todos],
        audit_logs=[AuditLogRead.model_validate(item) for item in audit_logs],
        object_type_definition=(
            ObjectTypeDefinitionRead.model_validate(object_type_definition)
            if object_type_definition is not None
            else None
        ),
        workflow_definitions=[
            WorkflowDefinitionRead.model_validate(item) for item in workflow_definitions
        ],
    )
    return envelope(detail.model_dump(by_alias=True))


@router.patch(
    "/business-objects/{business_object_id}",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def update_business_object(
    business_object_id: str,
    payload: UpdateBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    business_object = get_active_business_object_or_404(db, tenant_id, business_object_id)
    updates = payload.model_dump(exclude_unset=True)
    final_type = updates.get("object_type", business_object.object_type)
    require_permission(actor, "business_object.write", final_type)
    # custom-type subscriptions advance through this PATCH, not
    # common.py's apply_status_change — same wall, same pre-write match
    require_hosted_write_scope(actor, business_object.object_type, business_object)
    final_payload = updates.get("payload", business_object.payload_jsonb)
    validate_business_object_payload(db, tenant_id, final_type, final_payload)
    old_status = business_object.status
    if "status" in updates and updates["status"] != old_status:
        require_permission(actor, "business_object.advance", final_type)
        validate_business_object_status(
            db, tenant_id, final_type, current=old_status, new=updates["status"]
        )
        record_audit(
            db,
            tenant_id=tenant_id,
            action="business_object.status_changed",
            entity_type="business_object",
            entity_id=business_object.id,
            actor=actor.label,
            detail={
                "object_type": final_type,
                "title": updates.get("title", business_object.title),
                "from": old_status,
                "to": updates["status"],
            },
        )
        # A tenant-defined type retires the same way a builtin one does: the
        # machine the workspace wrote says nothing follows this state, so the
        # work items asking somebody to move it cannot be done. These machines
        # declare no `editable_states`, so terminal is the whole test.
        machine = get_business_object_machine(db, tenant_id, final_type)
        if machine is not None:
            retire_open_work_if_finished(
                db, actor, machine, "business_object", business_object.id,
                current=old_status, new_status=updates["status"],
            )
    if "payload" in updates:
        business_object.payload_jsonb = updates.pop("payload")
    for field, value in updates.items():
        setattr(business_object, field, value)
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.delete("/business-objects/{business_object_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_object(
    business_object_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: DeleteBusinessObjectRequest | None = None,
):
    business_object = get_scoped_or_404(db, BusinessObject, actor.tenant_id, business_object_id)
    require_permission(actor, "business_object.write", business_object.object_type)
    if business_object.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    business_object.deleted_at = datetime.now(timezone.utc)
    business_object.deleted_by = attributed(actor, payload.deleted_by if payload else None)
    business_object.delete_reason = payload.delete_reason if payload else None
    # todos on a custom object name it by the generic type, not by its
    # object_type — see TODO_ENTITY_TYPES
    cancel_todos_for(
        db, actor, "business_object", business_object.id,
        reason="business object deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/business-objects/{business_object_id}/restore",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def restore_business_object(
    business_object_id: str,
    payload: RestoreBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    business_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, business_object_id
    )
    require_permission(actor, "business_object.write", business_object.object_type)
    if business_object.deleted_at is None:
        return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))
    business_object.deleted_at = None
    business_object.deleted_by = None
    business_object.delete_reason = None
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-object-links",
    response_model=BusinessObjectLinkListEnvelope,
    response_model_exclude_unset=True,
)
def list_business_object_links(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    source_object_id: str | None = None,
    target_object_id: str | None = None,
    link_type: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db, select(BusinessObjectLink).where(BusinessObjectLink.tenant_id == tenant_id),
        filters={
            BusinessObjectLink.source_object_id: source_object_id,
            BusinessObjectLink.target_object_id: target_object_id,
            BusinessObjectLink.link_type: link_type,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObjectLink.link_type,
            cast(BusinessObjectLink.source_object_id, String),
            cast(BusinessObjectLink.target_object_id, String),
        ),
        order_by=(BusinessObjectLink.created_at.desc(), BusinessObjectLink.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=BusinessObjectLinkRead,
    )


@router.post(
    "/business-object-links",
    status_code=status.HTTP_201_CREATED,
    response_model=BusinessObjectLinkEnvelope,
    response_model_exclude_unset=True,
)
def create_business_object_link(
    payload: CreateBusinessObjectLinkRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    source_object = get_active_business_object_or_404(
        db, actor.tenant_id, payload.source_object_id
    )
    target_object = get_active_business_object_or_404(
        db, actor.tenant_id, payload.target_object_id
    )
    require_permission(actor, "business_object.write", source_object.object_type)
    require_permission(actor, "business_object.write", target_object.object_type)
    if source_object.id == target_object.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source and target objects must differ")
    existing = db.scalar(
        select(BusinessObjectLink).where(
            BusinessObjectLink.tenant_id == actor.tenant_id,
            BusinessObjectLink.source_object_id == source_object.id,
            BusinessObjectLink.target_object_id == target_object.id,
            BusinessObjectLink.link_type == payload.link_type,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="business object link already exists")
    link = BusinessObjectLink(
        tenant_id=actor.tenant_id,
        source_object_id=source_object.id,
        target_object_id=target_object.id,
        link_type=payload.link_type,
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return envelope(BusinessObjectLinkRead.model_validate(link).model_dump(by_alias=True))


@router.get(
    "/business-object-links/{link_id}",
    response_model=BusinessObjectLinkEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object_link(
    link_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, BusinessObjectLink, tenant_id, link_id)
    return envelope(BusinessObjectLinkRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/business-object-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_object_link(
    link_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, BusinessObjectLink, actor.tenant_id, link_id)
    source_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, link.source_object_id
    )
    target_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, link.target_object_id
    )
    require_permission(actor, "business_object.write", source_object.object_type)
    require_permission(actor, "business_object.write", target_object.object_type)
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- todos and approval records: the queue, and the facts that close it ----
#
# Interleaved rather than sorted into two blocks, because that is how they sat
# in routes.py and the order carries a claim: reading a todo needs the last
# approval on its target (`attach_todo_targets`), and recording an approval
# fact is what completes the todo. Splitting them would separate a queue from
# the only thing that empties it.


@router.get(
    "/approval-records",
    response_model=ApprovalRecordListEnvelope,
    response_model_exclude_unset=True,
)
def list_approval_records(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = None,
    entity_id: str | None = None,
    action_filter: Annotated[str | None, Query(alias="action")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    pagination = requested_pagination(page, size)
    return list_rows(
        db, select(ApprovalRecord).where(ApprovalRecord.tenant_id == tenant_id),
        filters={
            ApprovalRecord.entity_type: entity_type,
            ApprovalRecord.entity_id: entity_id,
            ApprovalRecord.action: action_filter,
        },
        keyword=keyword,
        keyword_columns=(
            ApprovalRecord.comment,
            ApprovalRecord.approver_id,
            ApprovalRecord.approver_role,
            cast(ApprovalRecord.entity_id, String),
        ),
        # Unpaged keeps the historical workflow-order contract for agent
        # clients. Console pagination is an activity feed, newest first.
        order_by=(
            (
                ApprovalRecord.round_no.asc(),
                ApprovalRecord.sequence_no.asc(),
                ApprovalRecord.acted_at.asc(),
                ApprovalRecord.id.asc(),
            )
            if pagination is None
            else (ApprovalRecord.acted_at.desc(), ApprovalRecord.id.desc())
        ),
        pagination=pagination,
        read_model=ApprovalRecordRead,
    )


TODO_TARGET_MODELS = {family.object_type: model for model, family in DOCUMENT_FAMILIES.items()}


def attach_todo_targets(db: Session, tenant_id: str, rows: list[dict]) -> None:
    """Summarize each todo's target onto the row, in a fixed number of batched
    reads regardless of how many todos there are.

    The check-in used to spend one detail call per todo to learn this much —
    the only part of it that grew with how busy the person was. Eight todos
    was eight extra agent turns at ~12s each. Here it is one grouped query per
    family present, plus one for line sums, approvals, and names.

    The summary shows the same facts the target's own detail endpoint would
    show the same caller — reads are tenant-wide by design — so it widens
    nothing.
    """
    pairs = {(row["entity_type"], row["entity_id"]) for row in rows}
    by_type: dict[str, set[str]] = {}
    for entity_type, entity_id in pairs:
        by_type.setdefault(entity_type, set()).add(entity_id)

    summaries: dict[tuple[str, str], TodoTargetSummary] = {}
    employee_ids: set[str] = set()
    approver_user_ids: set[str] = set()

    for entity_type, ids in by_type.items():
        model = TODO_TARGET_MODELS.get(entity_type)
        if model is not None:
            docs = db.scalars(
                select(model).where(model.tenant_id == tenant_id, model.id.in_(ids))
            ).all()
            for doc in docs:
                summary = TodoTargetSummary(
                    object_type=entity_type,
                    status=doc.status,
                    employee_id=doc.employee_id,
                )
                if entity_type == "timesheet_header":
                    summary.title = f"{doc.period_start} – {doc.period_end}"
                    summary.unit = "hours"
                elif entity_type in ("expense_claim", "purchase_request"):
                    summary.title = doc.title
                    summary.unit = "amount"
                    summary.currency = doc.currency
                elif entity_type == "sales_quotation":
                    summary.title = f"{doc.quote_number} {doc.title or ''}".strip()
                    summary.customer_name = doc.customer_name_snapshot
                    summary.amount = float(doc.total_amount) if doc.total_amount is not None else None
                    summary.unit = "amount"
                    summary.currency = doc.currency
                elif entity_type == "sales_order":
                    summary.title = f"{doc.order_no} {doc.title or ''}".strip()
                    summary.customer_name = doc.customer_name_snapshot
                    summary.amount = float(doc.total_amount) if doc.total_amount is not None else None
                    summary.unit = "amount"
                    summary.currency = doc.currency
                if doc.employee_id:
                    employee_ids.add(doc.employee_id)
                # Deliberately not filtered out of the query above: a todo whose
                # target was deleted still needs describing, and dropping the
                # row here would report it as `missing` — the same word used for
                # an id that names nothing, which is a different problem with a
                # different fix.
                summary.deleted = doc.deleted_at is not None
                summaries[(entity_type, doc.id)] = summary
        elif entity_type in ("business_object", "approval_target"):
            # `approval_target` is a BusinessObject too — the same row reached
            # by a different verb. It was absent from this branch, so every
            # todo pointing at one came back `missing: true` while the row sat
            # there readable. Two of the three non-document types reporting a
            # phantom integrity problem is what made `missing` unusable as the
            # signal a sweep looks for.
            for doc in db.scalars(
                select(BusinessObject).where(
                    BusinessObject.tenant_id == tenant_id, BusinessObject.id.in_(ids)
                )
            ).all():
                summaries[(entity_type, doc.id)] = TodoTargetSummary(
                    object_type=doc.object_type, title=doc.title, status=doc.status,
                    deleted=doc.deleted_at is not None,
                )
        elif entity_type == "project":
            # A project is archived rather than deleted, so `deleted` is never
            # set here; an archived one shows its status and the sweep judges
            # it the same way it judges any dead state.
            for row in db.scalars(
                select(Project).where(Project.tenant_id == tenant_id, Project.id.in_(ids))
            ).all():
                summaries[(entity_type, row.id)] = TodoTargetSummary(
                    object_type="project", title=row.project_name, status=row.status,
                )

    # line-derived amounts, one grouped query per family that stores none
    sum_specs = (
        ("timesheet_header", TimesheetEntry, TimesheetEntry.header_id, func.sum(TimesheetEntry.hours)),
        ("expense_claim", ExpenseItem, ExpenseItem.claim_id, func.sum(ExpenseItem.amount)),
        ("purchase_request", PurchaseRequestItem, PurchaseRequestItem.request_id, func.sum(PurchaseRequestItem.amount)),
        # the sales families store a header total, but nothing forces it to be
        # set — a real quotation shipped with priced lines and a null header
        # total, and the briefing could not put a number on the deal. The
        # header total wins when present; the line sum fills the gap.
        ("sales_quotation", SalesQuotationItem, SalesQuotationItem.quotation_id, func.sum(SalesQuotationItem.amount)),
        ("sales_order", SalesOrderItem, SalesOrderItem.order_id, func.sum(SalesOrderItem.amount)),
    )
    for entity_type, line_model, parent_col, total_col in sum_specs:
        ids = by_type.get(entity_type)
        if not ids:
            continue
        totals = db.execute(
            select(parent_col, total_col)
            .where(
                line_model.tenant_id == tenant_id,
                parent_col.in_(ids),
                line_model.deleted_at.is_(None),
            )
            .group_by(parent_col)
        ).all()
        for parent_id, total in totals:
            summary = summaries.get((entity_type, parent_id))
            if summary is not None and total is not None and summary.amount is None:
                summary.amount = float(total)

    # approval position: newest fact per target, plus how deep the trail is
    for entity_type, ids in by_type.items():
        records = db.scalars(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.tenant_id == tenant_id,
                ApprovalRecord.entity_type == entity_type,
                ApprovalRecord.entity_id.in_(ids),
            )
            .order_by(ApprovalRecord.round_no.asc(), ApprovalRecord.sequence_no.asc())
        ).all()
        for record in records:
            summary = summaries.get((entity_type, record.entity_id))
            if summary is None:
                continue
            summary.approval_count += 1
            summary.last_approval = TodoLastApproval(
                action=record.action,
                round_no=record.round_no,
                sequence_no=record.sequence_no,
                approver_role=record.approver_role,
                comment=record.comment,
                acted_at=record.acted_at,
            )
            if record.approver_id:
                # approver_id is an employee id only when a person acted
                # directly. Real trails also carry actor labels — "user:<id>"
                # from the API layer and service labels like "workflow-admin"
                # from the flow agent — and postgres refuses to cast either to
                # uuid, so each form resolves its own way.
                label = record.approver_id
                summary.last_approval.approver_name = label  # resolved below
                if label.startswith("user:"):
                    approver_user_ids.add(label[5:])
                else:
                    try:
                        uuid.UUID(label)
                    except ValueError:
                        pass  # service label; shown as-is
                    else:
                        employee_ids.add(label)

    names = {
        employee.id: employee.name
        for employee in db.scalars(
            select(Employee).where(Employee.tenant_id == tenant_id, Employee.id.in_(employee_ids))
        ).all()
    } if employee_ids else {}
    if approver_user_ids:
        names.update({
            f"user:{user.id}": user.name or user.email
            for user in db.scalars(
                select(User).where(User.tenant_id == tenant_id, User.id.in_(approver_user_ids))
            ).all()
        })
    for summary in summaries.values():
        if summary.employee_id:
            summary.employee_name = names.get(summary.employee_id)
        if summary.last_approval is not None and summary.last_approval.approver_name:
            # employee ids resolve to names; service labels stay as they are
            summary.last_approval.approver_name = names.get(
                summary.last_approval.approver_name, summary.last_approval.approver_name
            )

    for row in rows:
        key = (row["entity_type"], row["entity_id"])
        summary = summaries.get(key)
        if summary is None:
            summary = TodoTargetSummary(object_type=row["entity_type"], missing=True)
        row["target"] = summary.model_dump()


@router.get(
    "/todos",
    response_model=TodoListEnvelope,
    response_model_exclude_unset=True,
)
def list_todos(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    due_before: datetime | None = None,
    include: Literal["target"] | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    stmt = select(Todo).where(Todo.tenant_id == tenant_id)
    if due_before is not None:
        stmt = stmt.where(Todo.due_at.is_not(None), Todo.due_at <= due_before)
    result = list_rows(
        db, stmt,
        filters={
            Todo.employee_id: employee_id,
            Todo.status: status_filter,
            Todo.entity_type: entity_type,
            Todo.entity_id: entity_id,
        },
        keyword=keyword,
        keyword_columns=(
            Todo.title,
            Todo.description,
            Todo.todo_type,
            cast(Todo.entity_id, String),
        ),
        order_by=(Todo.created_at.desc(), Todo.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=TodoRead,
    )
    if include == "target" and result["data"]:
        attach_todo_targets(db, tenant_id, result["data"])
    else:
        # the read model dumps the field as null even when nobody asked;
        # absent beats null for a shape that predates the feature
        for row in result["data"]:
            row.pop("target", None)
    return result


@router.post(
    "/todos",
    status_code=status.HTTP_201_CREATED,
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def create_todo(
    payload: CreateTodoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "todos.assign")
    todo, created = assign_todo(db, actor, payload)
    db.commit()
    db.refresh(todo)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


def assign_todo(db: Session, actor: Actor, payload: CreateTodoRequest) -> tuple[Todo, bool]:
    """One assignment, every guard it has to pass, in one place.

    Extracted so the bulk endpoint runs the SAME sequence rather than a second
    copy of it. A parallel implementation of a guard list is the defect this
    codebase has now corrected five times over — the copy agrees on the day it
    is written and never again, and here the list includes the hosted agent's
    write boundary, which is not a thing to re-derive.

    Returns (todo, created). `created=False` is the idempotent hit: the same
    assignment is already open and is handed back.

    Does not commit. The caller decides whether one failure ends the batch.
    """
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    ensure_todo_entity_exists(db, tenant_id, payload.entity_type, payload.entity_id)
    if actor.write_scope is not None:
        require_hosted_write_scope(
            actor, payload.entity_type,
            scoped_write_target(db, tenant_id, payload.entity_type, payload.entity_id),
            ignore=("status",),
        )
    existing = db.scalar(
        select(Todo).where(
            Todo.tenant_id == tenant_id,
            Todo.employee_id == payload.employee_id,
            Todo.entity_type == payload.entity_type,
            Todo.entity_id == payload.entity_id,
            Todo.status == "open",
        )
    )
    if existing is not None:
        # Idempotency on the assignment's natural key, matching how approval
        # records answer a retry: a flow agent that crashed after writing —
        # or was fired twice for one signal — gets the assignment it already
        # made back, instead of an error it cannot distinguish from a real one.
        # A DIFFERENT assignment colliding with the open one is still a
        # conflict: the flow moved on and this caller's view is stale.
        if same_todo_assignment(existing, payload):
            return existing, False
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="open todo already exists for this entity")
    todo = Todo(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        title=payload.title,
        description=payload.description,
        todo_type=payload.todo_type,
        status=payload.status,
        due_at=payload.due_at,
        created_by=attributed(actor, payload.created_by),
        metadata_jsonb=payload.metadata,
    )
    if payload.status == "completed":
        todo.completed_at = datetime.now(timezone.utc)
        todo.completed_by = attributed(actor, payload.created_by or payload.employee_id)
    db.add(todo)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="todo.created",
        entity_type="todo",
        entity_id=todo.id,
        actor=actor.label,
        detail={
            "employee_id": todo.employee_id,
            "title": todo.title,
            "todo_type": todo.todo_type,
            "target_entity_type": todo.entity_type,
            "target_entity_id": todo.entity_id,
        },
    )
    return todo, True


@router.post(
    "/todos/bulk",
    response_model=BulkTodoEnvelope,
    response_model_exclude_unset=True,
)
def bulk_create_todos(
    payload: BulkTodoCreateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """One routing decision, many records.

    The flow agent reads its whole queue in one call and every approval trail in
    another, then had to write one todo per record — so three hundred timesheets
    on the same map cost three hundred round-trips and three hundred rounds of
    reasoning about a map that had not changed. This is the leg that stayed
    serial.

    Every item runs `assign_todo`, the same guard sequence the single endpoint
    runs. Nothing here is a second implementation of a check, and the check that
    makes that matter most is the hosted agent's write boundary.

    Audited as ONE event with its counts, like every other bulk import here:
    three hundred near-identical `todo.created` rows would bury the trail the
    assignment audit exists to keep readable. Each todo's own creation is still
    recorded by `assign_todo`; what this adds is that they were one decision.
    """
    require_permission(actor, "todos.assign")
    if payload.on_error == "abort":
        outcome = _assign_all_or_nothing(db, actor, payload.items)
    else:
        outcome = _assign_what_it_can(db, actor, payload.items)
    if not outcome["applied"]:
        return envelope(outcome)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="todo.bulk_assigned",
        entity_type="tenant",
        entity_id=actor.tenant_id,
        actor=actor.label,
        detail={**outcome["summary"], "on_error": payload.on_error},
    )
    db.commit()
    return envelope(outcome)


def _row(index: int, item: CreateTodoRequest, outcome: str, **extra) -> dict:
    return {"index": index, "entity_id": item.entity_id, "outcome": outcome, **extra}


def _summary(items: list, results: list[dict]) -> dict:
    counts = {"created": 0, "unchanged": 0, "error": 0}
    for row in results:
        counts[row["outcome"]] += 1
    return {"total": len(items), "created": counts["created"],
            "unchanged": counts["unchanged"], "failed": counts["error"]}


class _BatchAborted(Exception):
    """Unwinds the one savepoint the whole batch runs in."""

    def __init__(self, results: list[dict]) -> None:
        super().__init__("batch aborted")
        self.results = results


def _assign_all_or_nothing(db: Session, actor: Actor, items: list) -> dict:
    """`abort`: the whole batch in ONE savepoint, unwound on the first failure.

    Deliberately not "write per item, then roll the transaction back" — that
    reads the same and is not the same. A savepoint that has been RELEASED is
    beyond the reach of an outer rollback under pysqlite, which does not emit
    its own BEGIN, so the undo would work on Postgres and silently keep the rows
    on SQLite. One savepoint that is never released until the batch is whole has
    nothing to take back and behaves identically on both.
    """
    results: list[dict] = []
    try:
        with db.begin_nested():
            for index, item in enumerate(items):
                try:
                    todo, created = assign_todo(db, actor, item)
                    db.flush()
                except (HTTPException, IntegrityError) as exc:
                    results.append(_row(index, item, "error", error=_assign_error(exc)))
                    raise _BatchAborted(results) from None
                results.append(_row(
                    index, item, "created" if created else "unchanged", id=todo.id,
                ))
    except _BatchAborted as aborted:
        return {"applied": False, "summary": _summary(items, aborted.results),
                "results": aborted.results}
    return {"applied": True, "summary": _summary(items, results), "results": results}


def _assign_what_it_can(db: Session, actor: Actor, items: list) -> dict:
    """`skip`, the default: one bad item costs that item and nothing else.

    The likely failure is one record having moved on since the agent read the
    queue. Aborting for it would discard the correct assignments and then fail
    identically on the retry; skipping leaves that one in the queue, where the
    next pass rediscovers it — the same self-healing the work queue rests on.

    Each item gets its own savepoint so a failure at the database (rather than
    at one of the look-ahead checks) does not abort the transaction and take
    every later item with it. No outer rollback follows a released savepoint
    here: what succeeded is kept.
    """
    results: list[dict] = []
    for index, item in enumerate(items):
        try:
            with db.begin_nested():
                todo, created = assign_todo(db, actor, item)
                db.flush()
        except (HTTPException, IntegrityError) as exc:
            results.append(_row(index, item, "error", error=_assign_error(exc)))
            continue
        results.append(_row(index, item, "created" if created else "unchanged", id=todo.id))
    summary = _summary(items, results)
    applied = summary["created"] > 0 or summary["unchanged"] > 0
    return {"applied": applied, "summary": summary, "results": results}


def _assign_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    # Named rather than echoed from the driver, which spells the open-todo
    # constraint differently on Postgres and SQLite.
    return "open todo already exists for this entity"


@router.get(
    "/todos/{todo_id}",
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def get_todo(
    todo_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    todo = get_scoped_or_404(db, Todo, tenant_id, todo_id)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


@router.patch(
    "/todos/{todo_id}",
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def update_todo(
    todo_id: str,
    payload: UpdateTodoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    todo = get_scoped_or_404(db, Todo, actor.tenant_id, todo_id)
    require_permission(actor, "todos.complete_own")
    enforce_member_employee(actor, todo.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "due_at" in updates:
        todo.due_at = updates.pop("due_at")
    if "status" in updates:
        was = todo.status
        todo.status = updates["status"]
        if todo.status == "completed":
            todo.completed_at = datetime.now(timezone.utc)
            todo.completed_by = attributed(actor, updates.get("completed_by") or todo.completed_by)
        else:
            # `cancelled` leaves these null on purpose. The columns say
            # COMPLETED, and a report counting `completed_at is not null` must
            # not pick up work that nobody did — who cancelled it and when is
            # in the audit row below, which is where an administrative act
            # belongs anyway.
            todo.completed_at = None
            todo.completed_by = None
        if todo.status != was and todo.status in ("completed", "cancelled"):
            record_audit(
                db,
                tenant_id=actor.tenant_id,
                action=f"todo.{todo.status}",
                entity_type="todo",
                entity_id=todo.id,
                actor=actor.label,
                detail={
                    "employee_id": todo.employee_id,
                    "title": todo.title,
                    "target_entity_type": todo.entity_type,
                    "target_entity_id": todo.entity_id,
                },
            )
    elif "completed_by" in updates:
        todo.completed_by = attributed(actor, updates["completed_by"])
    db.commit()
    db.refresh(todo)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


def complete_own_approval_todo(
    db: Session, actor: Actor, entity_type: str, entity_id: str
) -> str | None:
    """Close the actor's own approval todo, because the actor just decided.

    Recording a decision and completing the todo that asked for it were two
    calls with no transaction between them: `POST /approval-records` then
    `PATCH /todos/{id}`. Both are idempotent and the order is deliberate — the
    fact first, because that is the half that matters — so nothing is ever lost
    or double-counted. What the gap costs is a STALL: the decision stands, the
    approver's todo stays open, and `$oryh-timesheet-approval-flow` only takes
    the document back once that todo is done. The flow stops, and nothing says
    so. HKG-015 is the same shape one case over.

    So the server does both. The todo said "decide this node", the caller just
    did, and that holds whatever the workspace's routing rules say — which is
    what makes it the server's rather than the flow agent's, the same argument
    `common.py`'s `cancel_todos_for` makes for a returned document.

    It lives here rather than in `common.py` because only this module calls it,
    and `tests/test_shared_core.py` is what said so — one commit after that test
    was written, on its author.

    Whose todo is not a guess: `todos_open_entity_assignee_uk` reserves one open
    todo per EMPLOYEE per record, so there is at most one to find, and parallel
    sign-off leaves everybody else's alone. A credential with no linked employee
    — a tenant service key — owns no todo and completes none.

    `PATCH /todos/{id}` remains, and remains idempotent: a skill that still
    sends step 4 gets a completed todo back, not an error.
    """
    if actor.employee_id is None:
        return None
    todo = db.scalar(
        select(Todo).where(
            Todo.tenant_id == actor.tenant_id,
            Todo.employee_id == actor.employee_id,
            Todo.entity_type == entity_type,
            Todo.entity_id == entity_id,
            Todo.todo_type == "approval",
            Todo.status == "open",
        )
    )
    if todo is None:
        return None
    todo.status = "completed"
    todo.completed_at = datetime.now(timezone.utc)
    todo.completed_by = attributed(actor, None)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="todo.completed",
        entity_type="todo",
        entity_id=todo.id,
        actor=actor.label,
        detail={
            "employee_id": todo.employee_id,
            "title": todo.title,
            "target_entity_type": todo.entity_type,
            "target_entity_id": todo.entity_id,
            "closed_by": "the decision this todo asked for",
        },
    )
    return todo.id


def finished_state(db: Session, tenant_id: str, target, state: str) -> bool:
    """Whether this target's own machine allows nothing to follow `state`.

    The same two questions `retire_open_work_if_finished` asks, reachable
    before the write so a contradictory request can be refused rather than
    partly performed.
    """
    family = DOCUMENT_FAMILIES.get(type(target))
    if family is not None:
        machine = get_builtin_machine(db, tenant_id, family.object_type)
        return (
            is_terminal_state(machine, state)
            and state not in editable_states(machine, family.object_type)
        )
    if isinstance(target, BusinessObject):
        machine = get_business_object_machine(db, tenant_id, target.object_type)
        return machine is not None and is_terminal_state(machine, state)
    return False


def apply_round_transition(db: Session, actor: Actor, payload, target) -> None:
    """The rest of the round transition, in the transaction that decided it.

    A `returned` fact is one third of what the approval-flow skills tell an
    agent to do. The other two — move the document to `returned`, open the
    submitter's rework todo — were two more calls, and every one of them could
    be the one that did not happen. HKG-015 is what the leftovers look like
    from a console: a trail saying one thing, a status saying another, nobody
    assigned.

    None of the judgment moves to the server. Which status the document takes
    and whose queue it lands in are the flow agent's, exactly as before, and
    every guard those two calls enforced still runs here — `apply_status_change`
    for the machine and the advance permission, `assign_todo` for the employee,
    the hosted write scope and the open-todo key. What changes is only that the
    three facts share a commit.

    Both halves are idempotent, which is what makes a retry safe: a status
    already at the target is a no-op, and `assign_todo` hands back an identical
    open assignment rather than making a second one.
    """
    if payload.document_status is not None:
        family = DOCUMENT_FAMILIES.get(type(target))
        if family is not None:
            apply_status_change(db, actor, target, payload.document_status)
            target.status = payload.document_status
        elif isinstance(target, BusinessObject):
            require_permission(actor, "business_object.advance", target.object_type)
            validate_business_object_status(
                db, actor.tenant_id, target.object_type,
                current=target.status, new=payload.document_status,
            )
            machine = get_business_object_machine(db, actor.tenant_id, target.object_type)
            if machine is not None:
                retire_open_work_if_finished(
                    db, actor, machine, "business_object", target.id,
                    current=target.status, new_status=payload.document_status,
                )
            target.status = payload.document_status
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{payload.entity_type} has no status the server governs — "
                    "omit document_status"
                ),
            )
    if payload.handoff is not None:
        # A handoff onto a document nothing can move is the stranded todo this
        # whole change exists to stop, expressed in one call instead of two.
        # It reads as a slip rather than an intent — "returned to the submitter"
        # with `rejected` typed into the status — so it is refused by name
        # rather than half-performed.
        if payload.document_status is not None and finished_state(
            db, actor.tenant_id, target, payload.document_status
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{payload.document_status!r} is a state the machine does not leave — "
                    "a handoff there could never be acted on; drop one of the two"
                ),
            )
        assign_todo(
            db, actor,
            CreateTodoRequest(
                employee_id=payload.handoff.employee_id,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                title=payload.handoff.title,
                description=payload.handoff.description,
                todo_type=payload.handoff.todo_type,
                due_at=payload.handoff.due_at,
                metadata=payload.handoff.metadata,
            ),
        )


@router.post(
    "/approval-records",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalRecordEnvelope,
    response_model_exclude_unset=True,
)
def create_approval_record(
    payload: CreateApprovalRecordRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "approval.record")
    if actor.write_scope is not None:
        require_hosted_write_scope(
            actor, payload.entity_type,
            scoped_write_target(db, tenant_id, payload.entity_type, payload.entity_id),
            ignore=("status",),
        )
    target = ensure_referenced_entity_exists(
        db, tenant_id, payload.entity_type, payload.entity_id,
        allowed=ALLOWED_APPROVAL_ENTITY_TYPES, label="approval",
    )
    acted_at = resolve_acted_at(payload.acted_at, target)
    require_submission_before_decision(payload)
    ensure_no_operator_closure_marker(payload.metadata)
    # idempotency on the natural key: an agent retrying the same action gets
    # the already-recorded fact back instead of a duplicate
    existing = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.action == payload.action,
            ApprovalRecord.historical_conflict_closed.is_(False),
        )
    )
    if existing is not None:
        # The retry path still has to finish the transition. An agent that
        # crashed between the fact and the status would otherwise get its own
        # fact handed back forever while the document stayed where it was —
        # a retry that reports success and changes nothing.
        apply_round_transition(db, actor, payload, target)
        db.commit()
        db.refresh(existing)
        return envelope(ApprovalRecordRead.model_validate(existing).model_dump(by_alias=True))
    ensure_node_undecided(db, tenant_id, payload)
    record = ApprovalRecord(
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        round_no=payload.round_no,
        sequence_no=payload.sequence_no,
        action=payload.action,
        approver_id=attributed(actor, payload.approver_id),
        approver_role=payload.approver_role,
        comment=payload.comment,
        source=payload.source,
        metadata_jsonb=payload.metadata,
        acted_at=acted_at,
    )
    db.add(record)
    db.flush()
    if record.action == "returned":
        # The round this approval work belonged to is over: a returned document
        # goes back to its submitter, and nobody should still be holding an open
        # approval todo on it. The same certainty `cancel_todos_for` was written
        # for — there it is "the subject is gone", here it is "the round is".
        #
        # HKG-015: an approver returned a timesheet and his own round-1 approval
        # todo stayed open. The console then showed an Open approval todo beside
        # two completed ones, which reads as an active queue, on a document whose
        # round had moved on and which had no assignment at all.
        #
        # `approval` only. The document still exists, so a todo that is not about
        # deciding it — attach the receipt, fix the hours — is still work.
        cancel_todos_for(
            db, actor, payload.entity_type, payload.entity_id,
            reason=f"round {record.round_no} returned",
            todo_type="approval",
        )
    elif record.action in DECIDED_APPROVAL_ACTIONS:
        # The other half of the same idea. `returned` ends the round for
        # everybody; `approved`/`rejected` ends it for the one seat that just
        # decided, and leaves a parallel signer's todo alone.
        #
        # `commented` is deliberately outside: an objection that settles nothing
        # leaves the node — and the todo asking about it — exactly where it was.
        complete_own_approval_todo(db, actor, payload.entity_type, payload.entity_id)
    # After the sweeps, never before: a handoff opened here must survive
    # `cancel_todos_for`, and the round it belongs to is the new one.
    apply_round_transition(db, actor, payload, target)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="approval.recorded",
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        actor=actor.label,
        detail={
            "action": record.action,
            "round_no": record.round_no,
            "sequence_no": record.sequence_no,
            "approver_id": record.approver_id,
            "approver_role": record.approver_role,
            "comment": record.comment,
        },
    )
    db.commit()
    db.refresh(record)
    return envelope(ApprovalRecordRead.model_validate(record).model_dump(by_alias=True))


@router.get(
    "/approval-records/{approval_record_id}",
    response_model=ApprovalRecordEnvelope,
    response_model_exclude_unset=True,
)
def get_approval_record(
    approval_record_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    record = get_scoped_or_404(db, ApprovalRecord, tenant_id, approval_record_id)
    return envelope(ApprovalRecordRead.model_validate(record).model_dump(by_alias=True))
