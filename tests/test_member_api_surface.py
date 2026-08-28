"""What a zero-capability member can read is a DECISION, pinned here.

Two audiences use this API. Agents acting for members get the business
surface: documents, todos, the naming directory, their own bundle —
tenant-scoped by design, because a workspace's business documents are the
workspace's (payroll being the guarded exception). Administrators get the
machinery underneath: the skill registry, the flow runner's telemetry, the
access topology, attachments by bare id.

Nothing used to enforce that boundary. The raw attachment routes were open to
any credential in the workspace, and so were the skill registry (every role's
instructions and every calibration), the flow runs (operator telemetry,
errors included), and the roles list (every grant set with headcounts). Each
was found by hand, one conversation at a time. This test is that audit made
permanent: it walks every route in the OpenAPI schema with a credential
holding NOTHING and asserts the set that returns data is exactly the list
below — in both directions, so the list can neither grow silently nor go
stale.

Only a 2xx is evidence of reach. A 404 under a fabricated id is tenant scope
holding; a 422 is validation running before the handler's own gate; neither
flows data. Write-route permission gates have their own per-family tests —
this file pins the READ surface, which is where every leak so far has been.

A new route failing here is not wrong — it is undecided. Gate it, or add it
with a reason a powerless member may have it.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import make_client, provision_tenant

MEMBER_READS: dict[tuple[str, str], str] = {
    # --- business documents: tenant-visible by design; payroll filtered inside
    **{("GET", f"/api/v1/{r}"): "business documents are the workspace's"
       for r in (
           "timesheet-headers", "timesheet-entries", "employee-leaves",
           "expense-claims", "expense-items",
           "purchase-requests", "purchase-request-items",
           "purchase-orders", "purchase-order-items", "purchase-order-adjustments",
           "sales-quotations", "sales-quotation-items", "sales-quotation-adjustments",
           "sales-orders", "sales-order-items", "sales-order-adjustments",
           "invoices", "invoice-items", "payments", "payment-applications",
           "billing-accounts", "billing-account-entries",
           "business-objects", "business-object-links",
           "approval-records", "approval-targets", "policies",
           "projects", "resources", "resource-bookings",
           "inventory-items", "inventory-item-details",
           "shipments", "shipment-items",
           "external-document-links",
       )},
    # --- master data: what every document names ------------------------------
    **{("GET", f"/api/v1/{r}"): "master data is what documents point at"
       for r in ("customers", "vendors", "employees", "products", "product-skus",
                 "product-prices", "supplier-products", "external-product-maps",
                 "type-options")},
    # --- coordination, naming, vocabulary ------------------------------------
    ("GET", "/api/v1/todos"): "todos are the coordination fabric",
    ("GET", "/api/v1/object-directory"): "the naming service; payroll filtered inside",
    ("POST", "/api/v1/directory/display-names/resolve"): "the naming service; payroll filtered inside",
    ("GET", "/api/v1/builtin-object-types"): "vocabulary, not data",
    ("GET", "/api/v1/capabilities"): "the capability catalog is documentation",
    ("GET", "/api/v1/object-type-definitions"): "agents read machines to know the states",
    ("GET", "/api/v1/workflow-definitions"): "every submit skill reads the tenant's rules",
    # --- the member's own surface --------------------------------------------
    ("GET", "/api/v1/my/skill-bundle"): "your bundle is yours",
    ("GET", "/api/v1/my/skills/manifest"): "your bundle is yours",
    ("GET", "/api/v1/my/skills/reach"): "your bundle is yours",
    ("GET", "/api/v1/connect-skill"): "the bootstrap skill that teaches connecting",
    ("GET", "/api/v1/tenant"): "workspace name and domain — the room you stand in",
    ("GET", "/api/v1/console/bootstrap"): "who am I: the caller's own identity and grants",
    ("GET", "/api/v1/console/dashboard"): "counts of documents the member can list anyway",
}

# The machinery this audit closed, pinned by name so a revert is loud.
ADMIN_ONLY_READS: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/skills"),
    ("GET", "/api/v1/skills/{skill_ref}"),
    ("GET", "/api/v1/skills/{skill_ref}/files/{file_path}"),
    ("GET", "/api/v1/skills/{skill_ref}/assignments"),
    ("GET", "/api/v1/flow-runs"),
    ("GET", "/api/v1/flow-subscriptions"),
    ("GET", "/api/v1/roles"),
    ("GET", "/api/v1/attachments/{attachment_id}"),
    ("GET", "/api/v1/attachments/{attachment_id}/content"),
    ("GET", "/api/v1/audit-logs"),
)


@pytest.fixture(scope="module")
def surface():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Surface Co", email="admin@surface.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        client.post("/api/v1/roles", json={"name": "nobody", "permissions": []}, headers=admin)
        uid = client.post("/api/v1/auth/invitations",
                          json={"email": "n@surface.example", "role": "nobody"},
                          headers=admin).json()["data"]["id"]
        token = next(l.rsplit("token=", 1)[1].strip()
                     for l in outbox.messages[-1].body.splitlines() if "token=" in l)
        client.post("/api/v1/auth/invitations/accept",
                    json={"token": token, "password": "invitee-pass1"})
        key = client.post("/api/v1/tenant/api-keys",
                          json={"label": "nobody", "user_id": uid},
                          headers=admin).json()["data"]["plain_text_api_key"]

        from app.main import app
        FAKE = "00000000-0000-0000-0000-000000000000"
        reached = {}
        for path, item in app.openapi()["paths"].items():
            if not path.startswith("/api/v1/") or path.startswith("/api/v1/auth/"):
                continue
            for method in item:
                if method == "parameters":
                    continue
                url = re.sub(r"\{[^}]+\}", FAKE, path)
                r = client.request(method.upper(), url, headers={"X-API-Key": key},
                                   json={} if method in ("post", "patch", "put") else None)
                reached[(method.upper(), path)] = r.status_code
        yield reached


def test_the_data_surface_is_exactly_the_decided_list(surface) -> None:
    flowing = {k for k, code in surface.items() if 200 <= code < 300}
    undecided = sorted(f"{m} {p} -> {surface[(m, p)]}" for m, p in flowing - set(MEMBER_READS))
    stale = sorted(f"{m} {p} -> {surface.get((m, p))}" for m, p in set(MEMBER_READS) - flowing)
    assert not undecided, (
        "routes returning data to a ZERO-capability member that nobody decided about "
        "(gate them, or add them to MEMBER_READS with a reason):\n  " + "\n  ".join(undecided)
    )
    assert not stale, (
        "MEMBER_READS entries that no longer return data — a stale claim is how "
        "the list stops being read:\n  " + "\n  ".join(stale)
    )


def test_the_machinery_is_admin_only(surface) -> None:
    for method, path in ADMIN_ONLY_READS:
        assert surface.get((method, path)) == 403, (
            f"{method} {path} must be 403 for a zero-capability member, "
            f"got {surface.get((method, path))}"
        )
