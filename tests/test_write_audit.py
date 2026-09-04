"""A write that changes a record must leave an audit row, or say why not.

The trail is what anchors an approval to what was approved. HKG-015: a timesheet
was approved twice, six entries were moved to another project, and it was
resubmitted — and the audit carried the three status transitions and nothing
about the edit. The change was only reconstructable because `updated_at`
happened to be there.

`common.py`'s `record_line_audit` closed that for every family's lines and
adjustments in one place. This test is what stops the next one opening: a new
write endpoint either audits, or its silence is written down here with a
reason. An unlisted silent endpoint fails.

The exemptions are NOT a claim that those paths are fine. Most are the same gap
one subject over — master data, projects, API keys — and each says so. They are
listed so the number is a written fact rather than something nobody counted.
Closing one means deleting its line, which is the point.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = ROOT / "app/api"
WRITE_VERBS = {"post", "patch", "put", "delete"}

# endpoint -> why it writes no audit row.
UNAUDITED: dict[str, str] = {
    # Authentication events. A session is not a business record, and the
    # security-relevant half (who holds which key) is audited where keys are
    # issued rather than on every login.
    "auth.py POST /browser/login": "session, not a business record",
    "auth.py POST /browser/logout": "session, not a business record",
    "auth.py POST /login": "session, not a business record",
    "auth.py POST /logout": "session, not a business record",
    "auth.py POST /invitations/accept": "the accepted invitation IS the record",
    "auth.py POST /password-reset-email": "sends mail; the reset itself is audited",
    "auth.py POST /users/{user_id}/password-reset-email": "sends mail; the reset is audited",
    "device.py POST /start": "issues a device code, not a business record",
    "auth.py POST /token/refresh": (
        "the rotation IS audited — by the ORM trail, as api_key.updated with both"
        " hashes redacted, and the replay-revocation branch as is_active"
        " true→false. A record_audit here would claim (api_key, id) and suppress"
        " that richer delta entry; test_token_refresh pins the trail instead."
    ),
    "people.py POST /directory/display-names/resolve": "a read shaped as POST",

    # Document creation. The row's own created_at/created_by carries it, and a
    # create is not a change to something an approver already signed. Worth
    # revisiting if creation ever needs to be answerable on its own.
    "billing.py POST /invoices": "creation; the row carries created_at/created_by",
    "billing.py POST /payments": "creation; the row carries created_at/created_by",
    "claims.py POST /expense-claims": "creation; the row carries created_at/created_by",
    "claims.py POST /timesheet-headers": "creation; the row carries created_at/created_by",
    "people.py POST /employee-leaves": "creation; the row carries created_at/created_by",
    "purchasing.py POST /purchase-orders": "creation; the row carries created_at/created_by",
    "purchasing.py POST /purchase-requests": "creation; the row carries created_at/created_by",
    "sales.py POST /sales-orders": "creation; the row carries created_at/created_by",
    "sales.py POST /sales-quotations": "creation; the row carries created_at/created_by",

    # Restore. The delete that preceded it IS audited, so the trail shows the
    # document left and came back; the restore's own row is missing. Same gap,
    # smaller: HKG-015 step 1 follow-up.
    "billing.py PATCH /billing-accounts/{account_id}": "standing-balance edit unaudited — known gap",
    "billing.py DELETE /billing-accounts/{account_id}": "standing-balance delete unaudited — known gap",
    "billing.py POST /billing-accounts/{account_id}/restore": "restore unaudited — known gap",
    "billing.py POST /invoices/{invoice_id}/restore": "restore unaudited — known gap",
    "billing.py POST /payments/{payment_id}/restore": "restore unaudited — known gap",
    "claims.py POST /expense-claims/{claim_id}/restore": "restore unaudited — known gap",
    "claims.py POST /timesheet-headers/{header_id}/restore": "restore unaudited — known gap",
    "objects.py POST /approval-targets/{approval_target_id}/restore": "restore unaudited — known gap",
    "objects.py POST /business-objects/{business_object_id}/restore": "restore unaudited — known gap",
    "people.py POST /employee-leaves/{leave_id}/restore": "restore unaudited — known gap",
    "purchasing.py POST /purchase-orders/{po_id}/restore": "restore unaudited — known gap",
    "purchasing.py POST /purchase-requests/{request_id}/restore": "restore unaudited — known gap",
    "sales.py POST /sales-orders/{order_id}/restore": "restore unaudited — known gap",
    "sales.py POST /sales-quotations/{quotation_id}/restore": "restore unaudited — known gap",

    # Master data. The same gap as HKG-015 one subject over: a product's price
    # or a vendor's tax id can change under a document that references it, with
    # nothing recording who changed it. DELETE is audited here (archive_row
    # takes an audit action); create and update are not.
    "master_data.py POST /customer-contacts": "master data write unaudited — known gap",
    "master_data.py PATCH /customer-contacts/{contact_id}": "master data write unaudited — known gap",
    "master_data.py POST /customers": "master data write unaudited — known gap",
    "master_data.py PATCH /customers/{customer_id}": "master data write unaudited — known gap",
    "master_data.py POST /vendors": "master data write unaudited — known gap",
    "master_data.py PATCH /vendors/{vendor_id}": "master data write unaudited — known gap",
    "master_data.py POST /products": "master data write unaudited — known gap",
    "master_data.py PATCH /products/{product_id}": "master data write unaudited — known gap",
    "master_data.py POST /product-skus": "master data write unaudited — known gap",
    "master_data.py PATCH /product-skus/{sku_id}": "master data write unaudited — known gap",
    "master_data.py POST /products/{product_id}/skus/batch": "master data write unaudited — known gap",
    "master_data.py POST /product-prices": "master data write unaudited — known gap",
    "master_data.py PATCH /product-prices/{price_id}": "master data write unaudited — known gap",
    "master_data.py POST /product-images": "master data write unaudited — known gap",
    "master_data.py PATCH /product-images/{image_id}": "master data write unaudited — known gap",
    "master_data.py DELETE /product-images/{image_id}": "removes a link; the attachment store keeps the bytes",
    "master_data.py POST /bills-of-materials": "master data write unaudited — known gap",
    "master_data.py PATCH /bills-of-materials/{bom_id}": "master data write unaudited — known gap",
    "master_data.py POST /bom-items": "master data write unaudited — known gap",
    "master_data.py PATCH /bom-items/{item_id}": "master data write unaudited — known gap",
    "master_data.py DELETE /bom-items/{item_id}": "recipe line removal while draft — the recipe is the record",
    "master_data.py POST /facilities": "master data write unaudited — known gap",
    "master_data.py PATCH /facilities/{facility_id}": "master data write unaudited — known gap",
    "master_data.py POST /sales-channels": "master data write unaudited — known gap",
    "master_data.py PATCH /sales-channels/{channel_id}": "master data write unaudited — known gap",
    "master_data.py POST /stores": "master data write unaudited — known gap",
    "master_data.py PATCH /stores/{store_id}": "master data write unaudited — known gap",
    "master_data.py POST /store-facilities": "master data write unaudited — known gap",
    "master_data.py PATCH /store-facilities/{link_id}": "master data write unaudited — known gap",
    "master_data.py POST /product-categories": "master data write unaudited — known gap",
    "master_data.py PATCH /product-categories/{category_id}": "master data write unaudited — known gap",
    "master_data.py POST /supplier-products": "master data write unaudited — known gap",
    "master_data.py PATCH /supplier-products/{supplier_product_id}": "master data write unaudited — known gap",
    "master_data.py POST /customer-products": "master data write unaudited — known gap",
    "master_data.py PATCH /customer-products/{customer_product_id}": "master data write unaudited — known gap",
    "master_data.py POST /external-product-maps": "master data write unaudited — known gap",
    "master_data.py PATCH /external-product-maps/{map_id}": "master data write unaudited — known gap",
    "master_data.py POST /inventory-items": "master data write unaudited — known gap",
    "master_data.py PATCH /inventory-items/{item_id}": "master data write unaudited — known gap",
    "master_data.py POST /inventory-item-details": "append-only ledger; the entry is the record",
    "treasury.py POST /fin-accounts": "master data write unaudited — known gap",
    "treasury.py PATCH /fin-accounts/{account_id}": "master data write unaudited — known gap",
    "treasury.py POST /fin-account-transactions": "append-only register; the entry is the record",
    "treasury.py POST /fin-account-transactions/bulk": "append-only register; the entries are the record",
    "treasury.py PATCH /fin-account-transactions/{trans_id}": "reconciliation link annotation unaudited — known gap",
    "contracts.py POST /contracts": "contract document write unaudited — known gap",
    "contracts.py POST /contracts/{contract_id}/restore": "restore unaudited — known gap",
    "contracts.py POST /contract-items": "contract line write unaudited — known gap",
    "contracts.py PATCH /contract-items/{item_id}": "contract line write unaudited — known gap",
    "contracts.py DELETE /contract-items/{item_id}": "contract line removal while editable — the contract is the record",
    "contracts.py POST /contract-terms": "clause extraction unaudited — the excerpt is the record",
    "contracts.py PATCH /contract-terms/{term_id}": "clause extraction unaudited — the excerpt is the record",
    "contracts.py DELETE /contract-terms/{term_id}": "clause extraction unaudited — the excerpt is the record",
    "contracts.py POST /contract-documents": "links an original to its contract; the attachment store keeps the bytes",
    "contracts.py PATCH /contract-documents/{document_id}": "document link metadata — the bytes are immutable",
    "contracts.py DELETE /contract-documents/{document_id}": "removes a link; the attachment store keeps the bytes",
    "crm.py POST /leads": "pipeline document write unaudited — known gap",
    "crm.py POST /leads/{lead_id}/restore": "restore unaudited — known gap",
    "crm.py POST /opportunities": "pipeline document write unaudited — known gap",
    "crm.py POST /opportunities/{opportunity_id}/restore": "restore unaudited — known gap",
    "shipments.py POST /picklists": "warehouse document write unaudited — known gap",
    "shipments.py POST /picklists/{picklist_id}/restore": "restore unaudited — known gap",
    "shipments.py POST /picklist-items": "warehouse line write unaudited — known gap",
    "shipments.py PATCH /picklist-items/{item_id}": "warehouse line write unaudited — known gap",
    "shipments.py DELETE /picklist-items/{item_id}": "warehouse line write unaudited — known gap",
    "shipments.py POST /shipments": "freight document write unaudited — known gap",
    "shipments.py POST /shipments/{shipment_id}/restore": "restore unaudited — known gap",
    "shipments.py POST /shipments/{shipment_id}/post-stock": "writes append-only ledger entries; the entries are the record, stock_posted_at the receipt",
    "shipments.py POST /shipment-items": "freight line write unaudited — known gap",
    "shipments.py PATCH /shipment-items/{item_id}": "freight line write unaudited — known gap",
    "shipments.py DELETE /shipment-items/{item_id}": "freight line write unaudited — known gap",

    # Workspace and platform configuration.
    "workspace.py POST /projects": "master data write unaudited — known gap",
    "workspace.py PATCH /projects/{project_id}": "master data write unaudited — known gap",
    "workspace.py POST /tenants": "creates the tenant an audit row would belong to",
    "workspace.py POST /tenant/api-keys": "key issuance unaudited — known gap, security-relevant",
    "workspace.py PATCH /tenant/api-keys/{api_key_id}": "key change unaudited — known gap, security-relevant",
    "roles.py POST /capabilities": "tenant capability catalog write unaudited — known gap",
    "roles.py DELETE /capabilities/{name}": "tenant capability catalog write unaudited — known gap",
    "objects.py POST /object-type-definitions": "definition write unaudited — known gap",
    "objects.py PATCH /object-type-definitions/{definition_id}": "definition write unaudited — known gap",
    "objects.py POST /business-object-links": "link write unaudited — known gap",
    "objects.py DELETE /business-object-links/{link_id}": "link write unaudited — known gap",
    "external.py POST /external-document-links": "link write unaudited — known gap; created_by is on the row",
    "external.py DELETE /external-document-links/{link_id}": "link write unaudited — known gap",
    "policies.py PATCH /policies/{policy_id}": "policy edit unaudited — known gap; publish IS audited",
    "policies.py DELETE /policies/{policy_id}": "policy delete unaudited — known gap",
    "people.py POST /employees": "master data write unaudited — known gap",
    "people.py PATCH /employees/{employee_id}": "master data write unaudited — known gap",
    "people.py PATCH /pay-histories/{record_id}": "pay terms edit unaudited — known gap, payroll-relevant",
    "resources.py POST /resources": "master data write unaudited — known gap",
    "resources.py PATCH /resources/{resource_id}": "master data write unaudited — known gap",
    "resources.py PATCH /resource-bookings/{booking_id}": "booking edit unaudited — known gap",
    "skills.py POST ": "tenant skill registry write unaudited — known gap",
    "skills.py PATCH /{skill_ref}": "tenant skill registry write unaudited — known gap",
    "skills.py DELETE /{skill_ref}": "tenant skill registry write unaudited — known gap",
    "flows.py POST /flow-runs": "the FlowRun row IS the record of the run",
    "flows.py PATCH /flow-runs/{run_id}": "the FlowRun row IS the record of the run",
}


def _helpers() -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for path in sorted(API.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found.setdefault(node.name, node)
    return found


def _audits(node: ast.AST, helpers: dict[str, ast.AST], seen: set[str] | None = None) -> bool:
    """Does this endpoint, or anything it calls, reach `record_audit`?"""
    seen = seen if seen is not None else set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if child.id == "record_audit":
                return True
            if child.id in helpers and child.id not in seen:
                seen.add(child.id)
                if _audits(helpers[child.id], helpers, seen):
                    return True
    return False


def _write_endpoints() -> list[tuple[str, bool]]:
    helpers = _helpers()
    found: list[tuple[str, bool]] = []
    for path in sorted(API.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            routes = [
                f"{path.name} {d.func.attr.upper()} {d.args[0].value}"
                for d in node.decorator_list
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr in WRITE_VERBS and d.args
                and isinstance(d.args[0], ast.Constant)
            ]
            if routes:
                audited = _audits(node, helpers)
                found += [(route, audited) for route in routes]
    return found


def test_the_write_endpoints_were_found() -> None:
    """Guard the guard: an analysis that stops seeing endpoints must fail."""
    endpoints = _write_endpoints()
    assert len(endpoints) > 150, f"only {len(endpoints)} write endpoints parsed"
    assert any(audited for _, audited in endpoints)


def test_every_write_either_audits_or_is_listed() -> None:
    silent = sorted(route for route, audited in _write_endpoints() if not audited)
    unlisted = [route for route in silent if route not in UNAUDITED]
    assert not unlisted, (
        "these write endpoints record no audit row and are not in UNAUDITED:\n  "
        + "\n  ".join(unlisted)
        + "\n\nAn approval is a signature on content; a change with no row is a "
        "change nobody can find later (HKG-015). Add record_audit, or add the "
        "endpoint to UNAUDITED with the reason it does not need one."
    )


def test_the_exemption_list_has_no_stale_entries() -> None:
    """An entry that starts auditing must leave the list, or the list stops
    describing the code and starts describing its own history."""
    silent = {route for route, audited in _write_endpoints() if not audited}
    stale = sorted(route for route in UNAUDITED if route not in silent)
    assert not stale, (
        "these are listed as unaudited but now audit — delete their lines:\n  "
        + "\n  ".join(stale)
    )
