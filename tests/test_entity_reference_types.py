"""What a todo or an approval fact may point at, pinned in one place.

This file exists because the same list lived in three: an if-chain in
`routes.py`, a CHECK constraint in the migrations, and `DOCUMENT_FAMILIES`. The
three drifted, and the drift surfaced as a **500** on an ordinary request —
"create the approval todo for this payment", which `$oryh-payment-approval-flow`
tells every finance agent to make. The API resolved the payment fine and the
database refused it, and the IntegrityError reached the client as a server
error.

Nothing in the suite had ever created a todo against a payment, so nothing
noticed. These tests are the thing that would have.

They also cover the fall-through: the approval path's if-chain had no `else`, so
an entity type it did not recognise skipped the existence check entirely and
reached the constraint. A typo now gets a sentence.
"""

from __future__ import annotations

import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.common import DOCUMENT_FAMILIES
from app.core.entity_types import (
    APPROVAL_ENTITY_TYPES,
    DOCUMENT_ENTITY_TYPES,
    TODO_ENTITY_TYPES,
)
from app.services.state_machines import BUILTIN_MACHINES
from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

TEST_TENANT = "dddddddd-9999-4999-8999-dddddddddddd"
TEST_API_KEY = "entity-types-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Reference Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def constraint_values(client: TestClient, table: str) -> set[str]:
    """The entity types the live CHECK constraint actually admits."""
    from app.db.session import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
        # SQLite keeps the CREATE TABLE text; Postgres has pg_get_constraintdef.
        # Both end up as a quoted IN-list, which is all this needs.
        if db.get_bind().dialect.name == "postgresql":
            ddl = db.execute(
                text(
                    "select pg_get_constraintdef(con.oid) from pg_constraint con"
                    " join pg_class rel on rel.oid = con.conrelid"
                    " where rel.relname = :t and con.conname = :c"
                ),
                {"t": table, "c": f"{table}_entity_type_chk"},
            ).scalar()
        else:
            ddl = db.execute(
                text("select sql from sqlite_master where type='table' and name=:t"),
                {"t": table},
            ).scalar()
            match = re.search(r"entity_type\s+IN\s*\(([^)]*)\)", ddl or "", re.I)
            ddl = match.group(0) if match else ""
        return set(re.findall(r"'([a-z_]+)'", ddl or ""))
    finally:
        db.close()


def test_the_one_declaration_matches_both_registries() -> None:
    """`app/core/entity_types.py` is the single declaration; these are the two
    registries it must not drift from. Adding a document family without
    updating it fails here — which is the whole reason it is one file and not
    four scattered lists."""
    families = {family.object_type for family in DOCUMENT_FAMILIES.values()}
    assert families == set(DOCUMENT_ENTITY_TYPES), (
        "DOCUMENT_FAMILIES and app/core/entity_types.py disagree"
    )
    assert set(BUILTIN_MACHINES) == set(DOCUMENT_ENTITY_TYPES), (
        "BUILTIN_MACHINES and app/core/entity_types.py disagree"
    )
    assert families <= set(TODO_ENTITY_TYPES)
    assert families <= set(APPROVAL_ENTITY_TYPES)

    # the ones that were missing, named so the regression is unmistakable
    for late_arrival in ("invoice", "payment", "purchase_order"):
        assert late_arrival in TODO_ENTITY_TYPES, late_arrival
        assert late_arrival in APPROVAL_ENTITY_TYPES, late_arrival


def test_a_payment_can_carry_an_approval_todo(client: TestClient) -> None:
    """The exact request that answered 500 in the test environment."""
    person = client.post(
        "/api/v1/employees", json={"name": "出纳"}, headers=HEADERS
    ).json()["data"]["id"]
    payee = client.post(
        "/api/v1/employees", json={"name": "员工"}, headers=HEADERS
    ).json()["data"]["id"]
    payment = client.post(
        "/api/v1/payments",
        json={"direction": "outbound", "employee_id": person, "payee_employee_id": payee,
              "amount": 14050.0},
        headers=HEADERS,
    ).json()["data"]

    todo = client.post(
        "/api/v1/todos",
        json={"entity_type": "payment", "entity_id": payment["id"],
              "employee_id": person, "title": "审批工资发放"},
        headers=HEADERS,
    )
    assert todo.status_code == 201, todo.text

    record = client.post(
        "/api/v1/approval-records",
        json={"entity_type": "payment", "entity_id": payment["id"],
              "round_no": 1, "sequence_no": 2, "action": "approved",
              "approver_id": person},
        headers=HEADERS,
    )
    assert record.status_code == 201, record.text


def test_an_invoice_can_too(client: TestClient) -> None:
    person = client.post(
        "/api/v1/employees", json={"name": "会计"}, headers=HEADERS
    ).json()["data"]["id"]
    customer = client.post(
        "/api/v1/customers", json={"name": "客户"}, headers=HEADERS
    ).json()["data"]["id"]
    invoice = client.post(
        "/api/v1/invoices",
        json={"direction": "sales", "employee_id": person, "customer_id": customer,
              "title": "货款", "total_amount": 5000.0},
        headers=HEADERS,
    ).json()["data"]

    assert client.post(
        "/api/v1/todos",
        json={"entity_type": "invoice", "entity_id": invoice["id"],
              "employee_id": person, "title": "开票复核"},
        headers=HEADERS,
    ).status_code == 201
    assert client.post(
        "/api/v1/approval-records",
        json={"entity_type": "invoice", "entity_id": invoice["id"],
              "round_no": 1, "sequence_no": 2, "action": "approved",
              "approver_id": person},
        headers=HEADERS,
    ).status_code == 201


def test_an_unknown_entity_type_is_a_sentence_not_a_500(client: TestClient) -> None:
    """The approval if-chain had no `else`: a type it did not recognise skipped
    validation and hit the constraint, which answers in SQL."""
    person = client.post(
        "/api/v1/employees", json={"name": "某人"}, headers=HEADERS
    ).json()["data"]["id"]

    for path, body in (
        ("/api/v1/todos",
         {"entity_type": "invoicce", "entity_id": person, "employee_id": person,
          "title": "打错了"}),
        ("/api/v1/approval-records",
         {"entity_type": "invoicce", "entity_id": person, "round_no": 1,
          "sequence_no": 2, "action": "approved", "approver_id": person}),
    ):
        response = client.post(path, json=body, headers=HEADERS)
        # the Literal refuses it at the door and names the real ones; the
        # resolver behind it is the backstop for anything that gets past
        assert response.status_code == 422, (path, response.text)
        assert "invoice" in response.text


def test_the_database_constraint_admits_exactly_what_the_api_does(client: TestClient) -> None:
    """The pin. A family added to the registry without a migration fails here,
    which is the whole point — the alternative is a 500 in somebody's month-end.
    """
    for table, expected in (
        ("todos", TODO_ENTITY_TYPES),
        ("approval_records", APPROVAL_ENTITY_TYPES),
    ):
        allowed = constraint_values(client, table)
        assert allowed, f"could not read {table}'s entity_type constraint"
        missing = sorted(set(expected) - allowed)
        assert not missing, (
            f"{table}'s CHECK constraint refuses {missing}, which the API accepts — "
            "add a migration rebuilding it from the registry"
        )


def test_an_existing_admin_role_is_topped_up_with_new_capabilities() -> None:
    """The third finding from a live deployment: no role in that workspace held any
    of `payroll.*`, `payment.*`, `invoice.*` or `policy.*` — not even `admin`.

    `provision_system_roles` only ever CREATED missing roles, so a capability
    shipped after a tenant was created was held by nobody there, and the
    symptom was a 403 that looked like somebody's deliberate decision.
    """
    from sqlalchemy import select

    from app.core.permissions import ALL_PERMISSIONS
    from app.db.session import get_db
    from app.main import app
    from app.models import Role
    from app.services.provisioning import provision_system_roles

    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Old Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="k"),
        ]
    ):
        db = next(app.dependency_overrides[get_db]())
        try:
            # an admin from before the settlement releases existed
            db.add(Role(
                tenant_id=TEST_TENANT, name="admin", title="admin", is_system=True,
                permissions_jsonb=["timesheet.submit_own", "approval.record"],
            ))
            db.add(Role(
                tenant_id=TEST_TENANT, name="member", title="member", is_system=True,
                permissions_jsonb=["timesheet.submit_own"],
            ))
            custom = Role(
                tenant_id=TEST_TENANT, name="finance_reviewer", title="reviewer",
                is_system=False, permissions_jsonb=["approval.record"],
            )
            db.add(custom)
            db.commit()

            created, widened = provision_system_roles(db, TEST_TENANT)
            db.commit()
            assert created == 0 and widened == 1

            admin = db.scalar(select(Role).where(
                Role.tenant_id == TEST_TENANT, Role.name == "admin"))
            held = set(admin.permissions_jsonb)
            assert set(ALL_PERMISSIONS) <= held
            # scopable verbs are held in their wildcard form
            for late_arrival in ("payroll.read", "payroll.manage", "payment.record",
                                 "payment.apply", "invoice.manage:*", "policy.manage",
                                 "policy.publish", "billing_account.manage"):
                assert late_arrival in held, late_arrival
            # nothing the tenant granted was taken away
            assert {"timesheet.submit_own", "approval.record"} <= held

            # …and no other role is touched, because there is no defensible way
            # to guess whether a new capability belongs to somebody else's role
            member = db.scalar(select(Role).where(
                Role.tenant_id == TEST_TENANT, Role.name == "member"))
            assert member.permissions_jsonb == ["timesheet.submit_own"]
            reviewer = db.scalar(select(Role).where(
                Role.tenant_id == TEST_TENANT, Role.name == "finance_reviewer"))
            assert reviewer.permissions_jsonb == ["approval.record"]

            # idempotent: running it again changes nothing
            assert provision_system_roles(db, TEST_TENANT) == (0, 0)
        finally:
            db.close()
