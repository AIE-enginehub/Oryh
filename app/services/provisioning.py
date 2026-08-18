from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.audit_trail import catalogue_write

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, SYSTEM_CAPABILITIES
from app.core.type_options import SYSTEM_TYPE_OPTIONS, system_type_sign
from app.models import Capability, ObjectTypeDefinition, Role, TenantSkill, TypeOption
from app.services.flow_subscriptions import provision_flow_subscriptions
from app.services.state_machines import (
    DEFAULT_EXPENSE_MACHINE,
    DEFAULT_INVOICE_MACHINE,
    DEFAULT_LEAVE_MACHINE,
    DEFAULT_PAYMENT_MACHINE,
    DEFAULT_PURCHASE_ORDER_MACHINE,
    DEFAULT_ORDER_MACHINE,
    DEFAULT_PURCHASE_MACHINE,
    DEFAULT_QUOTATION_MACHINE,
    DEFAULT_TIMESHEET_MACHINE,
)

# skills/ ships in the repo and the container image; every directory in it is
# a product skill provisioned into each tenant's registry — except `_common/`,
# which holds shared fragments (no SKILL.md, so seeding skips it) that skills
# pull in with an include marker.
PRODUCT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

# `{{include:_common/<file>}}` alone on its line. Expanded here, at read time,
# so the registry only ever stores finished text: one edit to a fragment bumps
# every including skill's version on the next provision, and nothing
# downstream (files_hash, sync, rendering) knows fragments exist. The fragment
# itself is verbatim — anything tenant- or object-calibrated stays in the
# including skill, and a fragment cannot include further (kept flat on
# purpose; a fragment tree would make "what does this skill say" unreadable).
_INCLUDE_MARKER = re.compile(r"^\{\{include:_common/([A-Za-z0-9_\-./]+)\}\}[ \t]*$", re.MULTILINE)


def _expand_includes(content: str, common_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if ".." in name.split("/"):
            raise ValueError(f"include escapes _common/: {match.group(0)}")
        fragment = common_dir / name
        if not fragment.is_file():
            raise ValueError(f"missing include fragment: _common/{name}")
        text = fragment.read_text(encoding="utf-8")
        if _INCLUDE_MARKER.search(text) or "{{include:" in text:
            raise ValueError(f"fragment _common/{name} must not include further")
        return text.rstrip("\n")

    return _INCLUDE_MARKER.sub(replace, content)


def read_skill_dir(skill_dir: Path) -> dict[str, str]:
    common_dir = skill_dir.parent / "_common"
    files: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            files[str(path.relative_to(skill_dir))] = _expand_includes(content, common_dir)
    return files


def parse_frontmatter(skill_md: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    lines = skill_md.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
    return meta


def insert_unless_raced(db: Session, instance, lookup) -> bool:
    """Insert a default object; return False if another writer got there first.

    Everything provisioned here is a check-then-insert, which is a race the
    moment two API replicas boot together — and a rolling update boots two by
    definition. Both read "missing", both insert, one takes a unique violation.
    Because the whole sync shares a single transaction, that one collision
    discarded 38 tenants' work and exited the container; it restarted and
    succeeded, so the cost was a slower rollout rather than lost data.

    A SAVEPOINT keeps the failure local: the collision rolls back this INSERT
    instead of the transaction, and the re-read finds the row the other replica
    committed — which is the row we wanted to exist. Losing the race is
    therefore success, and returns False only so callers can keep an honest
    changed-count.

    A savepoint rather than `ON CONFLICT DO NOTHING` because deployments run on
    Postgres and the suite runs on SQLite, and this must be the same code on
    both — a concurrency guard that is not exercised by the tests is decoration.
    """
    try:
        with db.begin_nested():
            db.add(instance)
    except IntegrityError:
        if instance in db:
            db.expunge(instance)
        if db.scalar(lookup) is not None:
            return False
        # Nothing there to have collided with, so this was some OTHER
        # constraint. Swallowing it would turn a real defect into a silently
        # skipped default — exactly the kind of quiet the original crash at
        # least did not have.
        raise
    return True


@catalogue_write
def provision_product_skills(db: Session, tenant_id: str) -> int:
    """Upsert the shipped product skill catalog into a tenant's registry.
    Idempotent; file changes bump the skill version. Returns changed count."""
    if not PRODUCT_SKILLS_DIR.is_dir():
        return 0
    changed = 0
    shipped: set[str] = set()
    for skill_dir in sorted(PRODUCT_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        files = read_skill_dir(skill_dir)
        if "SKILL.md" not in files:
            continue
        meta = parse_frontmatter(files["SKILL.md"])
        name = meta.get("name") or skill_dir.name
        shipped.add(name)
        skill = db.scalar(
            select(TenantSkill).where(TenantSkill.tenant_id == tenant_id, TenantSkill.name == name)
        )
        required_capability = meta.get("required_capability") or None
        if skill is None:
            changed += insert_unless_raced(
                db,
                TenantSkill(
                    tenant_id=tenant_id,
                    name=name,
                    kind="product",
                    title=name.replace("-", " ").title(),
                    description=meta.get("description"),
                    required_capability=required_capability,
                    catalog_required_capability=required_capability,
                    files_jsonb=files,
                    created_by="product-catalog",
                ),
                select(TenantSkill).where(
                    TenantSkill.tenant_id == tenant_id, TenantSkill.name == name
                ),
            )
        elif skill.kind == "product":
            # Content follows the catalog; gating and archival belong to the
            # tenant. A required_capability equal to the recorded catalog
            # baseline was never re-gated and keeps tracking the catalog; one
            # that differs is the tenant's decision and is left alone (setting
            # it back to the baseline resumes tracking). status is never
            # touched: an archived product skill stays archived until the
            # tenant revives it — its content still refreshes underneath so a
            # revival comes back current, and description rides the files (it
            # is the SKILL.md frontmatter), not the gate.
            #
            # distribution_mode and the audience rows are the tenant's for the
            # same reason: "this product skill is only for our procurement
            # team" is a distribution decision that touches no content, so it
            # survives every sync and never forks the skill to custom.
            dirty = False
            if files != skill.files_jsonb:
                skill.version += 1
                skill.files_jsonb = files
                skill.description = meta.get("description")
                dirty = True
            if skill.catalog_required_capability != required_capability:
                if skill.required_capability == skill.catalog_required_capability:
                    skill.required_capability = required_capability
                skill.catalog_required_capability = required_capability
                dirty = True
            if dirty:
                changed += 1
        # tenant-authored skill shadowing a product name: leave it alone
    changed += retire_withdrawn_product_skills(db, tenant_id, shipped)
    return changed


def retire_withdrawn_product_skills(db: Session, tenant_id: str, shipped: set[str]) -> int:
    """Archive product skills the catalog no longer ships.

    Without this a withdrawn skill lives on in every existing tenant's
    registry — still active, still gated, still landing in bundles, but frozen
    at its last content and never refreshed again, so it goes on instructing
    agents to call endpoints that may not exist. The catalog stops vouching
    for it, so distribution stops.

    Archived rather than deleted, like everything else here: the row keeps the
    tenant's re-gate and its history, and a tenant who wants to keep the
    content forks it into a `custom` skill — which the catalog never touches.
    A retired skill revived under its product name is archived again on the
    next sync, because nothing upstream stands behind it anymore.
    """
    if not shipped:
        # A catalog that shipped nothing is a broken deploy — an empty or
        # half-copied skills/ directory — not a statement that every skill was
        # withdrawn. Acting on it would silently disarm every tenant's agents.
        return 0
    withdrawn = db.scalars(
        select(TenantSkill).where(
            TenantSkill.tenant_id == tenant_id,
            TenantSkill.kind == "product",
            TenantSkill.status == "active",
            TenantSkill.name.not_in(sorted(shipped)),
        )
    ).all()
    for skill in withdrawn:
        skill.status = "archived"
    return len(withdrawn)


# (object_type, title, description, default machine) for every builtin entity
BUILTIN_DEFINITIONS: tuple[tuple[str, str, str, dict], ...] = (
    (
        "timesheet_header",
        "Timesheet",
        "Lifecycle of timesheet headers; edit to add tenant-specific review steps.",
        DEFAULT_TIMESHEET_MACHINE,
    ),
    (
        "employee_leave",
        "Employee Leave",
        "Lifecycle of 请假 requests; edit to add tenant-specific review steps. "
        "Entitlement rules are NOT here — they live in the tenant's leave policy "
        "and are applied by an agent, because a balance that was stored would "
        "outlive the rule it was computed under.",
        DEFAULT_LEAVE_MACHINE,
    ),
    (
        "expense_claim",
        "Expense Claim",
        "Lifecycle of expense claims; edit to add tenant-specific review or payment steps.",
        DEFAULT_EXPENSE_MACHINE,
    ),
    (
        "purchase_request",
        "Purchase Request",
        "Lifecycle of purchase requests; edit to add tenant-specific review or fulfilment steps.",
        DEFAULT_PURCHASE_MACHINE,
    ),
    (
        "sales_quotation",
        "Sales Quotation",
        "Lifecycle of sales quotations; the back half (sent/accepted/declined/expired) tracks the customer outcome and may be edited away.",
        DEFAULT_QUOTATION_MACHINE,
    ),
    (
        "purchase_order",
        "Purchase Order",
        "Lifecycle of purchase orders to vendors; edit to add tenant-specific confirmation or receiving steps.",
        DEFAULT_PURCHASE_ORDER_MACHINE,
    ),
    (
        "sales_order",
        "Sales Order",
        "Lifecycle of sales orders; the fulfilment half (confirmed/shipped/signed) may be renamed for service delivery (e.g. in_delivery/delivered).",
        DEFAULT_ORDER_MACHINE,
    ),
    (
        "invoice",
        "Invoice",
        "Lifecycle of invoices in both directions (销项/进项); 'paid' is a flow marker only — how much is settled comes from the payment applications, so a partly-paid invoice needs no state.",
        DEFAULT_INVOICE_MACHINE,
    ),
    (
        "payment",
        "Payment",
        "Lifecycle of payments; the approval half serves outbound payments (付款审批), while an inbound receipt is created directly in the terminal state.",
        DEFAULT_PAYMENT_MACHINE,
    ),
)


@catalogue_write
def provision_builtin_definitions(db: Session, tenant_id: str) -> int:
    """Ensure the tenant has editable definition rows for builtin entities.
    Existing rows are respected — tenants own their customizations."""
    created = 0
    for object_type, title, description, machine in BUILTIN_DEFINITIONS:
        existing = db.scalar(
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.tenant_id == tenant_id,
                ObjectTypeDefinition.entity_kind == "builtin",
                ObjectTypeDefinition.object_type == object_type,
            )
        )
        if existing is not None:
            continue
        created += insert_unless_raced(
            db,
            ObjectTypeDefinition(
                tenant_id=tenant_id,
                entity_kind="builtin",
                object_type=object_type,
                title=title,
                description=description,
                json_schema={},
                state_machine=machine,
                created_by="product-catalog",
            ),
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.tenant_id == tenant_id,
                ObjectTypeDefinition.entity_kind == "builtin",
                ObjectTypeDefinition.object_type == object_type,
            ),
        )
    return created


@catalogue_write
def provision_system_capabilities(db: Session, tenant_id: str) -> int:
    """Mirror the product capability catalog into the tenant's capabilities
    table (kind=system). Metadata refreshes on deploy; tenant custom rows are
    untouched."""
    existing = {
        c.name: c
        for c in db.scalars(
            select(Capability).where(Capability.tenant_id == tenant_id, Capability.kind == "system")
        )
    }
    changed = 0
    for name, scopable, title, description in SYSTEM_CAPABILITIES:
        row = existing.get(name)
        if row is None:
            changed += insert_unless_raced(
                db,
                Capability(
                    tenant_id=tenant_id, name=name, kind="system",
                    title=title, description=description, scopable=scopable,
                    created_by="product-catalog",
                ),
                select(Capability).where(
                    Capability.tenant_id == tenant_id, Capability.name == name
                ),
            )
        elif (row.title, row.description, row.scopable) != (title, description, scopable):
            row.title, row.description, row.scopable = title, description, scopable
            changed += 1
    return changed


@catalogue_write
def provision_system_type_options(db: Session, tenant_id: str) -> int:
    """Mirror the shipped type vocabularies into the tenant's type_options
    table (kind=system). Titles/descriptions refresh on deploy; status is the
    tenant's (an archived value stays archived), and custom rows are never
    touched."""
    existing = {
        (row.family, row.name): row
        for row in db.scalars(
            select(TypeOption).where(TypeOption.tenant_id == tenant_id, TypeOption.kind == "system")
        )
    }
    changed = 0
    for family, entries in SYSTEM_TYPE_OPTIONS.items():
        for name, title, description in entries:
            # the sign is part of a shipped value's meaning, so it refreshes
            # with the title and description rather than being seeded once
            sign = system_type_sign(family, name)
            row = existing.get((family, name))
            if row is None:
                changed += insert_unless_raced(
                    db,
                    TypeOption(
                        tenant_id=tenant_id, family=family, name=name, kind="system",
                        title=title, description=description, sign=sign,
                        created_by="product-catalog",
                    ),
                    select(TypeOption).where(
                        TypeOption.tenant_id == tenant_id,
                        TypeOption.family == family,
                        TypeOption.name == name,
                    ),
                )
            elif (row.title, row.description, row.sign) != (title, description, sign):
                row.title, row.description, row.sign = title, description, sign
                changed += 1
    return changed


@catalogue_write
def provision_system_roles(db: Session, tenant_id: str) -> tuple[int, int]:
    """Seed admin/member roles with behavior-preserving defaults, and keep the
    system `admin` role holding every system capability.

    Existing rows were never touched at all, which read as "tenants own their
    tuning" and behaved as something worse: a capability shipped after a tenant
    was created was held by NOBODY there. Three releases' worth of them —
    invoice, payment, billing_account, payroll, policy — were invisible in every
    workspace older than they were, and the symptom was a 403 that looked like
    a permissions decision somebody had made on purpose.

    So `admin` is topped up. It is defined as ALL_PERMISSIONS; a tenant that
    narrowed it narrowed it from a smaller universe, and a workspace wanting a
    restricted administrator should make a role rather than hollow out this
    one. The top-up only ADDS — nothing a tenant granted is ever removed.

    Every OTHER system role follows the catalog through
    `catalog_permissions_jsonb`, which records what we last gave it. "There is
    no defensible way to guess whether a new capability belongs to a role
    somebody else designed" was true only while `permissions_jsonb` was the
    single source: a gap in it could be an omission or a decision, and the two
    look identical. Recording what we gave separates them. A capability in
    neither the live set nor the baseline was never offered here, so offering
    it now is not overriding anybody; one in the baseline but not the live set
    was taken away deliberately, and stays away.

    Custom roles keep the old stance for the old reason, which has not gone
    anywhere: we ship no defaults for a role a tenant invented, so there is
    nothing to follow. Their baseline stays NULL and they are never touched.
    `scripts/reconcile_demo_roles.py` remains the named, reviewed way to widen
    specific ones.
    """
    created = 0
    widened = 0
    for name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        existing = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == name))
        if existing is None:
            created += insert_unless_raced(
                db,
                Role(
                    tenant_id=tenant_id, name=name, title=name,
                    permissions_jsonb=list(permissions),
                    catalog_permissions_jsonb=list(permissions),
                    is_system=True,
                ),
                select(Role).where(Role.tenant_id == tenant_id, Role.name == name),
            )
            continue
        if not existing.is_system:
            continue

        held = set(existing.permissions_jsonb or [])
        if name == "admin":
            grant = [p for p in permissions if p not in held]
        elif existing.catalog_permissions_jsonb is None:
            # No record of what we ever gave this role, so every gap is
            # ambiguous and none of them are ours to close. Start the record;
            # from the next capability onward the comparison works.
            grant = []
        else:
            baseline = set(existing.catalog_permissions_jsonb)
            grant = [p for p in permissions if p not in baseline and p not in held]

        if grant:
            existing.permissions_jsonb = list(existing.permissions_jsonb or []) + grant
            widened += 1
        # Recorded even when nothing was granted: the baseline has to move to
        # what we ship NOW, or a capability the tenant removes tomorrow gets
        # re-granted the day after as "never offered".
        if list(existing.catalog_permissions_jsonb or []) != list(permissions):
            existing.catalog_permissions_jsonb = list(permissions)
    return created, widened


def provision_tenant_defaults(db: Session, tenant_id: str) -> None:
    provision_product_skills(db, tenant_id)
    provision_builtin_definitions(db, tenant_id)
    provision_system_capabilities(db, tenant_id)
    provision_system_type_options(db, tenant_id)
    provision_system_roles(db, tenant_id)
    # Last, and not by accident: it reads the skills and the machines the four
    # calls above just wrote, to derive each subscription's driver and queue.
    provision_flow_subscriptions(db, tenant_id)


def unheld_shipped_capabilities(db: Session, tenant_id: str) -> dict[str, list[str]]:
    """Capabilities that reach NOBODY in this tenant but the administrator.

    Read-only. `provision_system_roles` tops up `admin` and deliberately
    touches nothing else: a capability missing from a role might be an
    omission, or might be a decision, and the two are indistinguishable in the
    data. The sync cannot grant it — but it can say so, and saying so is what
    was missing when settlement, payroll and leave each shipped to a
    workspace where the people who needed them got a 403 instead.

    Getting the QUESTION right took two tries, and both wrong versions are
    worth naming because each fails in the way alarms usually fail.

    "No role holds it" is permanently false: `admin` is defined as every
    capability and is topped up automatically, so the union always contains
    everything and the report is silent forever — an alarm that cannot ring.

    "`member` lacks what our defaults give `member`" is permanently true for
    any workspace that tuned its baseline. Our own demo seed narrows `member`
    on purpose, so that version reported four settled decisions per tenant —
    an alarm that always rings, which is the same as one that never does.

    What is actually actionable is narrower than either: a capability that no
    role a PERSON can hold carries. `quotation.submit_own` sitting only on a
    custom `sales` role is a workspace organising itself; `leave.submit_own`
    sitting nowhere but `admin` means the feature shipped and nobody can use
    it. Only the second is worth a line in a release log.

    Returns {capability: [the non-admin roles our defaults give it to]}.
    """
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS

    roles = list(db.scalars(select(Role).where(Role.tenant_id == tenant_id)))
    # admin excluded from the union — it holds everything by definition, and
    # counting it is what made the first version unable to ever fire
    reachable: set[str] = set()
    for role in roles:
        if role.name == "admin" and role.is_system:
            continue
        reachable.update(role.permissions_jsonb or [])

    report: dict[str, list[str]] = {}
    for role_name, shipped in DEFAULT_ROLE_PERMISSIONS.items():
        if role_name == "admin":
            continue
        for capability in shipped:
            if capability not in reachable:
                report.setdefault(capability, []).append(role_name)
    return report
