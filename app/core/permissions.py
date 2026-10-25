from __future__ import annotations

from app.locales.zh_CN import messages as zh_messages

from app.locales.zh_CN.permissions import SYSTEM_CAPABILITIES as _SYSTEM_CAPABILITIES_ZH

from app.core.config import settings
from app.core.entity_types import HOSTED_ADVANCE_VERBS, MEMBER_SUBMIT_VERBS

import hashlib

# Permission grammar: "verb" or "verb:scope". A bare grant of a scopable verb
# or an explicit "verb:*" covers every scope; "verb:<object_type>" covers one.
#
# Three enforcement layers (documented boundary):
#   - system verbs guard the core API (code enforcement points below);
#   - custom capabilities (tenant-defined rows) guard skill-bundle
#     distribution and flow-routing eligibility — never the core API;
#   - the scope dimension extends automatically with the tenant's object
#     types: no code change when a tenant defines a new type.

# (name, scopable, title, description)
SYSTEM_CAPABILITIES: tuple[tuple[str, bool, str, str], ...] = _SYSTEM_CAPABILITIES_ZH


# The catalogue's titles and descriptions in English, by capability name;
# `system_capabilities()` picks by locale. Keys must match SYSTEM_CAPABILITIES
# exactly; tests/test_seed_locale.py holds the two together.
CAPABILITY_TEXT_EN: dict[str, tuple[str, str]] = {
    "timesheet.submit_own": ("Submit own timesheet", "Create, fill in, submit and resubmit one's own timesheets"),
    "leave.submit_own": ("Submit own leave", "Create, fill in, submit, withdraw and resubmit one's own leave requests"),
    "leave.advance": ("Advance leave status", "Leave-request status transitions (final decision, return, cancellation): the flow-driving grant"),
    "timesheet.advance": ("Advance timesheet status", "Timesheet status transitions (final decision, return): the flow-driving grant"),
    "expense.submit_own": ("Submit own expense claim", "Create, fill in, submit and resubmit one's own expense claims, receipts included"),
    "expense.advance": ("Advance expense status", "Expense-claim status transitions (final decision, return, mark paid): the flow-driving grant"),
    "purchase.submit_own": ("Submit own purchase request", "Create, fill in, submit and resubmit one's own purchase requests"),
    "purchase.advance": ("Advance purchase request status", "Purchase-request status transitions (final decision, return, mark ordered): the flow-driving grant"),
    "quotation.submit_own": ("Submit own sales quotation", "Create, fill in and submit one's own quotations, including sending, recording the outcome and revising"),
    "quotation.advance": ("Advance quotation status", "Quotation status transitions (final decision, return, expiry sweep): the flow-driving grant"),
    "order.submit_own": ("Submit own sales order", "Create, fill in and submit one's own sales orders, including logistics and delivery facts"),
    "order.advance": ("Advance sales order status", "Sales-order status transitions (confirm, ship, sign-off, cancel): the flow-driving grant"),
    "invoice.manage": ("Issue / record invoices", "Create, edit and submit invoices; scopable by direction (invoice.manage:sales for sales only, :purchase for purchase only, :payroll for payslips only, :reimbursement for employee claims only)"),
    "invoice.advance": ("Advance invoice status", "Invoice status transitions (issue, return, void, write off): the flow-driving grant"),
    "payment.record": ("Record payments", "Create, edit and submit receipts and payments; not settlement"),
    "payment.advance": ("Advance payment status", "Payment status transitions (approve, reject, return, mark paid): the flow-driving grant"),
    "payment.apply": ("Settle", "Apply money to invoices or expense claims, reversals included; separate from payment.record so recording and settlement can be different desks"),
    "payroll.read": ("Read payroll", "Read pay records and payslips; a credential without it sees no payslip at all, while everyone sees their own"),
    "payroll.manage": ("Set pay", "Write pay records (pay changes); separate from issuing payslips (invoice.manage:payroll), because setting pay is a decision at another level"),
    "policy.manage": ("Draft policies", "Create and edit policy drafts and their rules; a draft is visible only to credentials holding this, since a leaked draft is worse than a published one"),
    "policy.publish": ("Publish / repeal policies", "Publish a draft as the version in force (closing the previous one) and repeal published policies; separate from drafting, because publishing is an act of authority, not an edit"),
    "billing_account.manage": ("Manage accounts", "Open account and points balances for customers, suppliers and employees; set credit limits, freeze and close"),
    "billing_account.post": ("Post account entries", "Write account movements (deposit, charge, grant points, redeem, expire); scopable by unit (billing_account.post:currency for money only, :points for points only); granting points is a fraud-prone act, kept apart from opening accounts"),
    "business_object.write": ("Create / edit business objects", "Scopable by object type; includes links and soft delete / restore"),
    "business_object.advance": ("Advance business object status", "Status transitions scoped by object type: the flow-driving grant"),
    "business_object.summarize": ("Summarise business objects", "Scoped by object type; gates the distribution of summary skills (a manager summarising daily reports); holding it also reads that type"),
    "approval.record": ("Record approval facts", "Write approval records (approved / rejected / returned / commented)"),
    "flow_run.record": ("Record flow-agent runs", "Write the flow agent's own run ledger (start, end, outcome): the agent's trail of its own work; advances no document"),
    "timesheet.read_all": ("Read all timesheets", "Read everyone's timesheets; without it a person reads their own and those routed to them"),
    "leave.read_all": ("Read all leave", "Read everyone's leave requests; without it a person reads their own and those routed to them"),
    "expense.read_all": ("Read all expense claims", "Read everyone's expense claims and receipts; without it a person reads their own and those routed to them"),
    "purchase.read_all": ("Read all purchase requests", "Read everyone's purchase requests; without it a person reads their own and those routed to them"),
    "quotation.read_all": ("Read all quotations", "Read every salesperson's quotations; without it a person reads their own and those routed to them"),
    "order.read_all": ("Read all sales orders", "Read every salesperson's orders and returns; without it a person reads their own and those routed to them"),
    "crm.read_all": ("Read all leads and deals", "Read everyone's leads, opportunities and contact records; without it a person reads their own"),
    "invoice.read": ("Read invoices", "Read invoices; scopable by direction (invoice.read:sales for sales only, :purchase for purchase only); payslips stay behind payroll.read; without it a person reads what they handled or were paid by, and what was routed to them"),
    "payment.read": ("Read payments", "Read receipts, payments and settlements; without it a person reads what they handled or were paid by, and what was routed to them"),
    "purchase_order.read": ("Read purchase orders", "Read purchase orders and their lines; without it a person reads what they handled and what was routed to them"),
    "shipment.read": ("Read shipments", "Read shipments and their lines; without it a person reads what was routed to them"),
    "inventory.read": ("Read stock", "Read stock positions, the stock ledger and picklists; without it a person reads the picklists routed to them"),
    "business_object.read": ("Read business objects", "Scopable by object type (business_object.read:warranty_card); writing, advancing or summarising a type implies reading it; without it a person reads what they created and what was routed to them"),
    "billing_account.read": ("Read accounts", "Read account and points balances and their entries; without it a person reads the accounts in their own name"),
    "todos.assign": ("Create todos for others", "Create todos assigned to any employee"),
    "notification.send": ("Send work notifications", "Email the employee concerned about assignments, returns and decisions; the address is resolved from the employee record, never chosen by the caller; no arbitrary content to arbitrary addresses"),
    "todos.complete_own": ("Complete own todos", "Complete todos assigned to oneself"),
    "booking.own": ("Book resources", "Create, change and cancel resource bookings in one's own name"),
    "campaign.manage": ("Run marketing campaigns", "Create, maintain and advance marketing campaigns and record the leads and customers they reached; attribution on leads and deals is written by whoever files them"),
    "crm.own": ("Work own leads and opportunities", "Create, advance and convert one's own leads and drive one's own opportunities to won or lost; the conversion bridge creates the customer record"),
    "master_data.manage": ("Manage master data", "Create, edit and archive projects, vendors, customers, products, SKUs and resources"),
    "project.manage": ("Manage projects", "Create, edit and archive projects and link them to a customer, an opportunity, a contract and an owner; the won-deal bridge (POST /opportunities/{id}/project) needs it too"),
    "inventory.manage": ("Manage stock", "Register stock positions, import counts, post stock documents (damage, transfer, production receipts) and hold stock for orders; ledger rows come only from these acts. Includes shipment.manage"),
    "shipment.manage": ("Ship and receive parcels", "File, advance and post-stock shipments (sales dispatch, return receipt, purchase-return dispatch); no positions, counts or stock documents"),
    "fin_account.manage": ("Fin accounts and bank statements", "Record fin accounts (bank, cash, payment platforms) and their register lines, import statements, link payments for reconciliation; not the payment documents themselves"),
    "contract.manage": ("Manage contracts", "File contracts and originals, locate clauses, advance status, link orders, invoices and payments; scopable by side (contract.manage:purchase, :sales); reading needs it too"),
    "employees.manage": ("Manage employees", "Create and maintain employee records"),
    "users.manage": ("Manage users and roles", "Invite users, assign roles, manage roles and custom capabilities — within the holder's own grants: inviting into admin or building a wider role is the administrator's"),
    "keys.manage": ("Manage access credentials", "Issue, view and disable personal credentials — never for an administrator or for someone holding a users.manage, keys.manage or skills.manage grant the holder lacks; workspace credentials are the administrator's"),
    "object_types.manage": ("Manage object types", "Define object fields and lifecycles"),
    "workflows.publish": ("Publish flow rules", "Draft, publish and repeal the three scoped kinds of business rule: approval flows, data rules and linkages"),
    "skills.manage": ("Manage skills", "Create, revise and archive the workspace's skills"),
    "skills.calibrate": ("Calibrate a skill", "Write one shipped skill's calibration — the workspace's own rules for it, such as product-matching rules — and read that skill; scopable by skill name (skills.calibrate:oryh-product-matching); never its files, audience or status"),
    "purchase_order.manage": ("Place and receive purchase orders", "Create and maintain purchase orders and record receipts; a procurement function, not 'own documents'"),
    "tenant.act_for_any_employee": ("Act for any employee", "Bypass the 'own records only' rule and act on any employee's records"),
}


def system_capabilities() -> tuple[tuple[str, bool, str, str], ...]:
    """The capability catalogue in the deployment's content locale."""

    if settings.resolved_locale != "en":
        return SYSTEM_CAPABILITIES
    return tuple(
        (name, scopable, *CAPABILITY_TEXT_EN[name])
        for name, scopable, _title, _description in SYSTEM_CAPABILITIES
    )

SYSTEM_CAPABILITY_NAMES = frozenset(name for name, *_ in SYSTEM_CAPABILITIES)


# What each capability governs, as the API collections (paths under /api/v1,
# without the prefix) its reads and writes land in. A console that builds its menu from
# a credential's permissions reads this instead of maintaining a table of its
# own; a scopable verb (`business_object.write:warranty_card`) names its object
# type after the colon and is not listed here. Grants with no collection of
# their own (`tenant.act_for_any_employee`, `keys.manage`) map to nothing.
CAPABILITY_COLLECTIONS: dict[str, tuple[str, ...]] = {
    "timesheet.submit_own": ("timesheet-headers", "timesheet-entries"),
    "timesheet.advance": ("timesheet-headers", "timesheet-entries"),
    "timesheet.read_all": ("timesheet-headers", "timesheet-entries"),
    "leave.submit_own": ("employee-leaves",),
    "leave.advance": ("employee-leaves",),
    "leave.read_all": ("employee-leaves",),
    "expense.submit_own": ("expense-claims", "expense-items"),
    "expense.advance": ("expense-claims", "expense-items"),
    "expense.read_all": ("expense-claims", "expense-items"),
    "purchase.submit_own": ("purchase-requests", "purchase-request-items"),
    "purchase.advance": ("purchase-requests", "purchase-request-items"),
    "purchase.read_all": ("purchase-requests", "purchase-request-items"),
    "quotation.submit_own": ("sales-quotations", "sales-quotation-items", "sales-quotation-adjustments"),
    "quotation.advance": ("sales-quotations", "sales-quotation-items", "sales-quotation-adjustments"),
    "quotation.read_all": ("sales-quotations", "sales-quotation-items", "sales-quotation-adjustments"),
    "order.submit_own": ("sales-orders", "sales-order-items", "sales-order-adjustments"),
    "order.advance": ("sales-orders", "sales-order-items", "sales-order-adjustments"),
    "order.read_all": ("sales-orders", "sales-order-items", "sales-order-adjustments"),
    "invoice.manage": ("invoices", "invoice-items"),
    "invoice.advance": ("invoices", "invoice-items"),
    "payment.record": ("payments", "payment-applications"),
    "payment.advance": ("payments", "payment-applications"),
    "payment.apply": ("payments", "payment-applications"),
    "payroll.read": ("pay-histories",),
    "payroll.manage": ("pay-histories",),
    "policy.manage": ("business-rules",),
    "policy.publish": ("business-rules",),
    "billing_account.manage": ("billing-accounts", "billing-account-entries"),
    "billing_account.post": ("billing-account-entries",),
    "business_object.write": (),
    "business_object.advance": (),
    "business_object.summarize": (),
    "approval.record": ("approval-records", "approval-targets"),
    "flow_run.record": ("flow-runs", "flow-subscriptions"),
    "crm.read_all": ("leads", "opportunities", "opportunity-items", "opportunity-contacts", "activities", "communication-events"),
    "crm.own": ("leads", "opportunities", "opportunity-items", "opportunity-contacts", "activities", "communication-events"),
    "invoice.read": ("invoices", "invoice-items"),
    "payment.read": ("payments", "payment-applications"),
    "purchase_order.read": ("purchase-orders", "purchase-order-items", "purchase-order-adjustments"),
    "shipment.read": ("shipments", "shipment-items"),
    "inventory.read": ("inventory-items", "inventory-item-details", "picklists", "picklist-items"),
    "business_object.read": (),
    "billing_account.read": ("billing-accounts", "billing-account-entries"),
    "campaign.manage": ("campaigns", "campaign-members", "events", "event-participants"),
    "todos.assign": ("todos",),
    "todos.complete_own": ("todos",),
    "notification.send": (),
    "booking.own": ("resources", "resource-bookings"),
    "master_data.manage": (
        "customers", "customer-contacts", "customer-products", "vendors", "supplier-products",
        "products", "product-skus", "product-categories", "product-prices", "product-images",
        "bills-of-materials", "bom-items", "facilities", "projects", "sales-channels", "stores",
        "store-facilities", "external-product-maps", "geos", "territories", "type-options",
    ),
    "project.manage": ("projects", "document-parties"),
    "inventory.manage": ("inventory-items", "inventory-item-details", "picklists", "picklist-items"),
    "shipment.manage": ("shipments", "shipment-items", "fulfilment-backlog"),
    "fin_account.manage": ("fin-accounts", "fin-account-transactions"),
    "contract.manage": ("contracts", "contract-items", "contract-terms", "contract-documents"),
    "employees.manage": ("employees",),
    "users.manage": ("auth/users", "roles", "capabilities"),
    "keys.manage": ("tenant/api-keys",),
    "object_types.manage": ("object-type-definitions", "type-options"),
    "workflows.publish": ("business-rules",),
    "skills.manage": ("skills",),
    "skills.calibrate": ("skills",),
    "purchase_order.manage": ("purchase-orders", "purchase-order-items", "purchase-order-adjustments"),
    "tenant.act_for_any_employee": (),
}


def capability_collections(name: str) -> tuple[str, ...]:
    """The collections a capability reaches, its own and those of every verb
    it implies (`inventory.manage` holds the shipment desk too)."""
    own = list(CAPABILITY_COLLECTIONS.get(name, ()))
    for verb, holders in IMPLIED_BY.items():
        if name in holders:
            own.extend(c for c in CAPABILITY_COLLECTIONS.get(verb, ()) if c not in own)
    return tuple(own)


def permissions_fingerprint(permissions) -> str:
    """A short digest of an effective permission set. `GET /auth/me` carries
    it so a client that cached what a credential could see knows, on its next
    call, whether that set moved: a revoked read narrows lists silently (an
    unreadable record does not exist for you), and a version counter would be
    one more thing to bump on every path that changes a grant."""
    return hashlib.sha256("\n".join(sorted(permissions)).encode("utf-8")).hexdigest()[:16]
SCOPABLE_VERBS = frozenset(name for name, scopable, *_ in SYSTEM_CAPABILITIES if scopable)

ALL_PERMISSIONS: tuple[str, ...] = tuple(
    name if not scopable else f"{name}:*" for name, scopable, *_ in SYSTEM_CAPABILITIES
)

# Seeded per tenant; tenants tune from here (e.g. strip approval.record from
# member and grant it via an approver role, or scope a service provider role to specific
# object types). todos.assign is deliberately NOT in member: assigning work to
# someone else is routing — the flow/admin side's write — and it also gates
# flow-side skill distribution (approval-notifier), which must not land in
# every member's bundle. Members complete their own todos; they do not mint
# them for colleagues.
DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": ALL_PERMISSIONS,
    "member": (
        "timesheet.submit_own",
        "leave.submit_own",
        "expense.submit_own",
        "purchase.submit_own",
        "quotation.submit_own",
        "order.submit_own",
        "business_object.write:*",
        "approval.record",
        "todos.complete_own",
        "booking.own",
        "crm.own",
        # the shared families an employee reads by being one; a workspace that
        # lets an outside party in gives that role only the reads it needs
        "invoice.read:*",
        "payment.read",
        "purchase_order.read",
        "shipment.read",
        "inventory.read",
        "business_object.read:*",
        "billing_account.read",
    ),
}
# a member files every hosted family's documents — one table, checked here
assert set(MEMBER_SUBMIT_VERBS) <= set(DEFAULT_ROLE_PERMISSIONS["member"])


# Principal kinds for tenant-level (service) API keys.
#
# `Actor.kind` answers "is there a person behind this credential". Principal
# kind answers "whose machine holds it". A tenant's own service key is the
# tenant's root credential for automation — it issued the key to itself, so
# bypassing the permission layer is not a hole, it is the point. A hosted flow
# agent key is held by ORYH inside someone else's tenant, so it carries an
# enumerable grant set instead, reported on the key itself (`ApiKeyRead
# .permissions`) so the customer's answer to "what can your agent do in my
# company" is a list they can read, not a promise they have to take.
PRINCIPAL_TENANT_SERVICE = "tenant_service"
PRINCIPAL_HOSTED_FLOW_AGENT = "hosted_flow_agent"

# Rendered wherever the hosted agent's writes are attributed. It comes from
# this constant, never from the key's label, so a tenant cannot mint a key that
# reads as ORYH's agent in its own audit trail.
HOSTED_FLOW_AGENT_DISPLAY_NAME = zh_messages.PERMISSIONS_HOSTED_FLOW_AGENT_DISPLAY_NAME

# Advancement, assignment, and a record of its own work — nothing else. The
# hosted agent moves flows and hands out todos. It cannot reshape identity or
# access (users/roles/keys), cannot file documents in someone's name
# (`*.submit_own`), cannot edit business object payloads, and cannot publish the
# tenant's own definitions or skills.
#
# `flow_run.record` is here so the runner needs no second, wider credential: the
# principal that did the work is the one that writes down having done it, in the
# tenant it did it in, signed as itself.
HOSTED_FLOW_AGENT_PERMISSIONS: tuple[str, ...] = (
    "timesheet.advance",
    "leave.advance",
    "expense.advance",
    "purchase.advance",
    "quotation.advance",
    "order.advance",
    "invoice.advance",
    # A payslip is a `direction=payroll` invoice behind the payroll read gate.
    # The hosted agent drives every invoice, payslips included, so it holds the
    # gate — without it the invoice queue silently omitted them (thirteen sat
    # in `submitted` while the run log read "queue 0").
    "payroll.read",
    "payment.advance",
    # the hosted agent runs the points-expiry sweep, which is a ledger write —
    # on POINTS accounts only. A `:*` here once let a hosted key with no
    # subscription at all deposit money on a currency account (review R04).
    "billing_account.post:points",
    "business_object.advance:*",
    "approval.record",
    "todos.assign",
    # The writes a `linkage` rule may ask for once a document reaches a
    # state: a shipment draft raised 1:1 from a confirmed order's lines, and
    # the hold on its stock — derived documents the warehouse completes and
    # posts. Not `invoice.manage`: that verb edits an invoice's words, and the
    # agent moving documents without editing them is a boundary a test holds
    # (an invoicing todo for finance is what sign-off gets). These are the
    # shipped DEFAULT of the tenant's `hosted_flow_agent` role (2026-10-07):
    # the administrator widens or narrows that role like any other, and the
    # key follows it.
    "shipment.manage",
    "inventory.manage",
    # The flow agent is the side that assigns work, so it is the side that
    # tells people work arrived. Its own runtime has no mail transport — the
    # pi child's environment is a six-variable whitelist on purpose — so the
    # server sends on its behalf. See app/api/notifications.py.
    "notification.send",
    "flow_run.record",
)
# the agent's advance verbs are the hosted families' — one table, checked here
assert {v for v in HOSTED_FLOW_AGENT_PERMISSIONS if v.endswith(".advance")} == set(HOSTED_ADVANCE_VERBS.values())

# The hosted agent's grants are a system role the tenant administrator edits,
# seeded with the default above. The role is held by the platform-issued key
# and never by a person; a tenant that runs its own unattended agent instead
# gives it whatever role it likes, and this one is the same decision for the
# hosted one.
HOSTED_FLOW_AGENT_ROLE = "hosted_flow_agent"
DEFAULT_ROLE_PERMISSIONS[HOSTED_FLOW_AGENT_ROLE] = HOSTED_FLOW_AGENT_PERMISSIONS


# A verb the holder of another verb also has. Not an alias: the wider grant
# is a genuine superset — the keeper who holds the shelf also ships from it —
# so a role granted `inventory.manage` before `shipment.manage` existed
# keeps shipping without a data migration, and a role granted only
# `shipment.manage` reaches nothing else.
IMPLIED_BY: dict[str, tuple[str, ...]] = {
    "shipment.manage": ("inventory.manage",),
    "project.manage": ("master_data.manage",),
}


def permissions_cover(permissions: frozenset[str], verb: str, scope: str | None = None) -> bool:
    if verb in permissions or f"{verb}:*" in permissions:
        return True
    if scope is not None and f"{verb}:{scope}" in permissions:
        return True
    return any(permissions_cover(permissions, wider, scope) for wider in IMPLIED_BY.get(verb, ()))


def permissions_cover_any_scope(permissions: frozenset[str], verb: str) -> bool:
    """Does this actor hold `verb` under ANY scope?

    `permissions_cover(perms, "invoice.manage")` is False for someone holding
    only `invoice.manage:sales`, and that is right wherever the caller knows
    which scope it needs — the settlement path always does.

    The attachment gate does not. It asks a different question: "does this
    actor file attachment-backed records at all", and an accounts-receivable accountant scoped to
    sales-side files exactly as many as one scoped to both. Asking the scoped
    question there produced a 403 on the upload for someone fully entitled to
    the record the upload was for.
    """
    if verb in permissions:
        return True
    prefix = verb + ":"
    if any(grant.startswith(prefix) for grant in permissions):
        return True
    return any(permissions_cover_any_scope(permissions, wider) for wider in IMPLIED_BY.get(verb, ()))


GATE_ALTERNATIVE = "|"


def grants_beyond(permissions: frozenset[str], grants) -> list[str]:
    """The grants in `grants` that `permissions` does not cover — what a
    person would be handing out without holding it. `users.manage` lets a
    person invite and shape roles, and a tenant found that an order-and-stock
    administrator given it could invite an administrator (2026-10-14): the
    verb was never meant to be a ladder. A grant is covered by the same
    grant, by `verb:*` for a scoped one, or by the bare verb."""
    return sorted(g for g in grants if not capability_covers(permissions, g))


def capability_covers(permissions: frozenset[str], required: str) -> bool:
    """A skill's required_capability is either a system verb — bare, or
    scoped like `business_object.write:daily_report`, in which case the
    scope must match exactly, via `verb:*`, or via the bare verb — or a
    custom capability (exact grant, scope-less by grammar). Several joined
    by `|` are alternatives: a skill that serves two desks (the policy
    editor and the flow publisher both maintain business rules) reaches
    whoever holds any one of them (review 2026-10-10, R09)."""
    if GATE_ALTERNATIVE in required:
        return any(capability_covers(permissions, part.strip()) for part in required.split(GATE_ALTERNATIVE) if part.strip())
    verb, _, scope = required.partition(":")
    if verb in SYSTEM_CAPABILITY_NAMES:
        if scope:
            return permissions_cover(permissions, verb, scope)
        # a skill gated on the BARE verb teaches the operations the API
        # allows under any scope of it: the purchase-contract desk holding
        # `contract.manage:purchase` must receive oryh-contracts, and the
        # API — not the bundle — is what keeps them to their scope
        # (review R12). Nobody is handed `:*` to make a download work.
        return permissions_cover_any_scope(permissions, verb)
    return required in permissions


def validate_permission_grammar(grant: str, known_custom: frozenset[str]) -> str | None:
    """Return an error string if the grant is not a system verb (optionally
    scoped), not a custom capability, and therefore meaningless."""
    verb, _, scope = grant.partition(":")
    if verb in SYSTEM_CAPABILITY_NAMES:
        if scope and verb not in SCOPABLE_VERBS:
            return f"{verb!r} does not accept a scope"
        return None
    if grant in known_custom:
        return None
    return f"unknown capability {grant!r}"
