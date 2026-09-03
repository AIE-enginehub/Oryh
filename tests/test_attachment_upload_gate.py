"""Who may put an attachment into the system.

The gate said "any capability that files attachment-backed records grants
upload" and then named two of them. Eight models carry `attachment_id`, so six
families were filed by people who could not produce the id their own record
wanted — most visibly 发票, where the original IS the evidence: an 应收会计
holding only `invoice.manage:sales` could raise the invoice, could set its
`attachment_id`, and got 403 on the upload that would have created one.

It stayed hidden because every seeded role builds on `member_base`, which
carries `expense.submit_own`. In a demo tenant everyone is also an expense
claimant, so the gate passed for a reason unrelated to what they were filing.

Two things are guarded here, and the first is why this file exists rather than
one more assertion in the invoice suite: the capability list is a fact about
the SCHEMA. A model that grows `attachment_id` tomorrow reopens exactly this
hole, silently, and no one reviewing that migration would think to look at an
upload endpoint in `workspace.py`.
"""

from __future__ import annotations

import base64
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.workspace import ATTACHMENT_FILING_CAPABILITIES
from app.core.permissions import SYSTEM_CAPABILITY_NAMES
from app.models import Base
from app.services.emails import outbox

from conftest import make_client
from conftest import provision_tenant as bootstrap_tenant

# What files each attachment-backed record. Declared rather than derived: the
# link from a table to the capability that writes it is a product decision, and
# the point of the test below is to force that decision to be made ONCE per
# attachment-backed family, in the open.
FILES_THE_RECORD = {
    "expense_items": "expense.submit_own",
    "purchase_request_items": "purchase.submit_own",
    "purchase_order_items": "purchase_order.manage",
    "sales_quotation_items": "quotation.submit_own",
    "sales_order_items": "order.submit_own",
    "invoices": "invoice.manage",
    "payments": "payment.record",
    "policies": "policy.manage",
    "product_images": "master_data.manage",
    "contract_documents": "contract.manage",
}


def attachment_backed_tables() -> set[str]:
    return {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.local_table is not None and "attachment_id" in mapper.local_table.c
    }


def test_every_attachment_backed_record_has_a_capability_that_can_upload() -> None:
    """The guard that survives the next migration.

    A new `attachment_id` column fails here, naming the table, instead of
    shipping a family whose filer cannot attach anything.
    """
    missing = attachment_backed_tables() - set(FILES_THE_RECORD)
    assert not missing, (
        f"these tables carry attachment_id but no capability files them: {sorted(missing)}. "
        "Name the capability in FILES_THE_RECORD and in ATTACHMENT_FILING_CAPABILITIES."
    )


def test_the_declared_map_describes_tables_that_still_exist() -> None:
    """The other direction: a family that loses its attachment column should
    not leave a capability behind widening the gate for nothing."""
    stale = set(FILES_THE_RECORD) - attachment_backed_tables()
    assert not stale, f"no longer attachment-backed: {sorted(stale)}"


def test_the_gate_lists_exactly_the_filing_capabilities() -> None:
    assert set(ATTACHMENT_FILING_CAPABILITIES) == set(FILES_THE_RECORD.values())


def test_every_listed_capability_is_a_real_one() -> None:
    """A typo here fails open in the most expensive direction: the gate quietly
    stops recognising a capability nobody holds under that spelling."""
    unknown = [v for v in ATTACHMENT_FILING_CAPABILITIES if v not in SYSTEM_CAPABILITY_NAMES]
    assert not unknown, f"not system capabilities: {unknown}"


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


@pytest.fixture()
def tenant() -> Generator[dict, None, None]:
    """A tenant plus a factory for user-bound keys holding named capabilities
    and nothing else — no `member_base`, which is what hid this."""
    with make_client([]) as client:
        data = bootstrap_tenant(
            client, company_name="Attach Co", email="admin@attach-co.com", password="attach-pass1"
        )
        service = {"X-API-Key": data["plain_text_api_key"]}
        seq = {"n": 0}

        def key_holding(*permissions: str) -> dict:
            seq["n"] += 1
            role = f"role{seq['n']}"
            assert client.post(
                "/api/v1/roles", json={"name": role, "permissions": list(permissions)},
                headers=service,
            ).status_code == 201
            email = f"user{seq['n']}@attach-co.com"
            user_id = client.post(
                "/api/v1/auth/invitations", json={"email": email, "role": role}, headers=service
            ).json()["data"]["id"]
            client.post(
                "/api/v1/auth/invitations/accept",
                json={"token": extract_token(outbox.messages[-1].body), "password": "invitee-pass1"},
            )
            plain = client.post(
                "/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id}, headers=service
            ).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": plain}

        yield {"client": client, "service": service, "key_holding": key_holding}


def upload(client: TestClient, headers: dict, body: bytes = b"%PDF-1.4 fapiao") -> int:
    return client.post(
        "/api/v1/attachments",
        json={
            "filename": "fapiao.pdf",
            "content_type": "application/pdf",
            "content_base64": base64.b64encode(body).decode(),
        },
        headers=headers,
    ).status_code


def test_an_ar_clerk_can_attach_the_original_invoice(tenant) -> None:
    """The reported case. `invoice.manage:sales` is SCOPED, so the gate has to
    ask "holds it under any scope" — asking the unscoped question refuses the
    person the record belongs to."""
    clerk = tenant["key_holding"]("invoice.manage:sales")
    assert upload(tenant["client"], clerk) == 201


@pytest.mark.parametrize("capability", sorted(set(FILES_THE_RECORD.values())))
def test_each_filing_capability_can_upload(tenant, capability: str) -> None:
    """Every family, not just the one that was reported."""
    holder = tenant["key_holding"](capability)
    assert upload(tenant["client"], holder, body=f"%PDF {capability}".encode()) == 201


def test_a_credential_that_files_nothing_still_cannot_upload(tenant) -> None:
    """The gate is not decoration: widening it to eight capabilities must not
    widen it to everyone. Without this, deleting the gate passes every test
    above."""
    bystander = tenant["key_holding"]("todos.complete_own")
    assert upload(tenant["client"], bystander) == 403


def test_the_capability_doc_names_every_filing_capability() -> None:
    """The doc is hand-maintained and nothing pinned it, which is how it came
    to list two capabilities for an endpoint eight of them now grant. A reader
    deciding what to request from their admin reads THAT table, so a partial
    truth there costs the same 403 this file exists to prevent.
    """
    import pathlib
    import re

    doc = pathlib.Path(__file__).resolve().parents[1] / "docs/capabilities-skills-api.md"
    row = next(
        (line for line in doc.read_text(encoding="utf-8").splitlines()
         if "`POST /attachments`" in line),
        None,
    )
    assert row is not None, "the capability map no longer documents POST /attachments"
    named = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", row))
    assert set(ATTACHMENT_FILING_CAPABILITIES) <= named, (
        "the doc's attachment row omits: "
        f"{sorted(set(ATTACHMENT_FILING_CAPABILITIES) - named)}"
    )
