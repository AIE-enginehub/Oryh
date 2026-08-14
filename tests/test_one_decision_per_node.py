"""One step of an approval holds one decision.

The natural key on `approval_records` includes `action`, which is what makes an
agent's retry idempotent — and what let `approved` and `rejected` stand together
at the same round and sequence. One seat, two contradictory decisions, nothing
in the data saying which counts.

The route that produces it is ordinary: one approver, two agent sessions, a
queue listed in both and acted on in one. So the guard has to survive the
concurrency it exists for, which is why it is an index and not only a check.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import ApprovalRecord, Base, Tenant
from conftest import provision_tenant


def post(client, headers, path, body):
    response = client.post(f"/api/v1{path}", json=body, headers=headers)
    assert response.status_code in (200, 201), (path, response.status_code, response.text)
    return response.json()["data"]


@pytest.fixture()
def queue(client: TestClient) -> dict:
    """A submitted timesheet with an approver's todo on it."""
    data = provision_tenant(client, company_name="Node Co", email="admin@node-co.com",
                            password="node-pass1234")
    headers = {"X-API-Key": data["plain_text_api_key"]}
    approver = post(client, headers, "/employees", {"name": "审批人"})["id"]
    owner = post(client, headers, "/employees", {"name": "王小明"})["id"]
    header_id = post(client, headers, "/timesheet-headers", {
        "employee_id": owner, "period_start": "2026-06-01", "period_end": "2026-06-07",
    })["id"]
    post(client, headers, "/timesheet-entries", {
        "header_id": header_id, "employee_id": owner, "work_date": "2026-06-01", "hours": 8,
    })
    post(client, headers, f"/timesheet-headers/{header_id}/submit", {})
    return {"client": client, "headers": headers, "approver": approver, "header_id": header_id}


def decide(queue: dict, action: str, comment: str = ""):
    return queue["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": queue["header_id"], "action": action,
        "round_no": 1, "sequence_no": 2, "approver_id": queue["approver"], "comment": comment,
    }, headers=queue["headers"])


def test_a_second_different_decision_on_one_step_is_refused(queue: dict) -> None:
    assert decide(queue, "rejected", "工时不实").status_code == 201
    clash = decide(queue, "approved", "看错了")
    assert clash.status_code == 409
    detail = clash.json()["detail"]
    # the message has to name what already stands, or an agent reads "conflict"
    # as its own error and retries instead of re-reading the trail
    assert "rejected" in detail and queue["approver"] in detail


def test_repeating_the_same_decision_is_still_idempotent(queue: dict) -> None:
    """The behaviour the guard must not break. A retry — a dropped response, a
    stale session replaying its list — gets the recorded fact back, not a 409
    and not a duplicate."""
    first = decide(queue, "approved", "同意")
    assert first.status_code == 201
    again = decide(queue, "approved", "同意")
    assert again.status_code == 201
    assert again.json()["data"]["id"] == first.json()["data"]["id"]

    rows = queue["client"].get(
        f"/api/v1/approval-records?entity_type=timesheet_header&entity_id={queue['header_id']}",
        headers=queue["headers"],
    ).json()["data"]
    assert [r["action"] for r in rows if r["sequence_no"] == 2] == ["approved"]


def test_a_comment_may_sit_beside_the_decision(queue: dict) -> None:
    """`commented` decides nothing, so it is outside the guard — an approver
    who objects and then approves anyway has said two true things."""
    assert decide(queue, "commented", "下次提前报").status_code == 201
    assert decide(queue, "approved", "这次放行").status_code == 201


def test_the_next_round_gets_its_own_decision(queue: dict) -> None:
    """Returned-and-resubmitted is a NEW round, and the guard is per step, not
    per document — otherwise a rework could never be decided."""
    assert decide(queue, "returned", "补齐再交").status_code == 201
    second = queue["client"].post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": queue["header_id"],
        "action": "approved", "round_no": 2, "sequence_no": 2,
        "approver_id": queue["approver"],
    }, headers=queue["headers"])
    assert second.status_code == 201, second.text


def test_two_concurrent_sessions_cannot_both_decide(tmp_path) -> None:
    """The case the guard is FOR, and the reason it is an index.

    Both sessions read an undecided step — which is what a Python check reads —
    and both then insert. Only the database sees the second one, so a
    check-then-insert would have let this through exactly when it mattered.

    File-backed SQLite: the suite's in-memory database is a single shared
    connection, where two sessions are one transaction and cannot race at all.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'node.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        tenant = Tenant(name="Node", slug="node", email_domain="node.com")
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id

    def fact(action: str, *, closed: bool = False) -> ApprovalRecord:
        return ApprovalRecord(
            tenant_id=tenant_id, entity_type="timesheet_header",
            entity_id="00000000-0000-0000-0000-0000000000aa",
            round_no=1, sequence_no=2, action=action, approver_id="emp-1",
            historical_conflict_closed=closed,
            acted_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )

    with factory() as a, factory() as b:
        undecided = select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.action.in_(("approved", "rejected", "returned")),
        )
        assert a.scalar(undecided) is None and b.scalar(undecided) is None

        b.add(fact("approved"))
        b.commit()

        a.add(fact("rejected"))
        with pytest.raises(IntegrityError) as raised:
            a.commit()

    # Which constraint fired, not merely that one did — a NOT NULL slip in this
    # fixture would otherwise read as the guard working. Postgres names the
    # index; SQLite lists the columns, so assert on the distinguishing shape:
    # this key stops at `sequence_no`, where the older natural key carries
    # `action` and would have let these two rows coexist.
    message = str(raised.value)
    assert "sequence_no" in message
    assert "approval_records.action" not in message

    with factory() as db:
        actions = list(db.scalars(select(ApprovalRecord.action)))
        assert actions == ["approved"], actions
    engine.dispose()


def test_an_operator_closed_historical_conflict_keeps_both_facts(tmp_path) -> None:
    """The exceptional closure retires a node without rewriting its trail.

    The database still holds the original contradictory approvals. They are
    excluded from the active-decision guard only after a separate operator
    remediation set the typed, API-unwritable flag.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'closed-node.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        tenant = Tenant(name="History", slug="history", email_domain="history.com")
        db.add(tenant)
        db.commit()
        db.add_all([
            ApprovalRecord(
                tenant_id=tenant.id, entity_type="timesheet_header",
                entity_id="00000000-0000-0000-0000-0000000000bb",
                round_no=1, sequence_no=2, action="returned", approver_id="emp-1",
                historical_conflict_closed=True,
                acted_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            ),
            ApprovalRecord(
                tenant_id=tenant.id, entity_type="timesheet_header",
                entity_id="00000000-0000-0000-0000-0000000000bb",
                round_no=1, sequence_no=2, action="approved", approver_id="emp-1",
                historical_conflict_closed=True,
                acted_at=datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc),
            ),
        ])
        db.commit()
        facts = list(db.scalars(select(ApprovalRecord).order_by(ApprovalRecord.acted_at)))
        assert [fact.action for fact in facts] == ["returned", "approved"]
        assert all(fact.historical_conflict_closed for fact in facts)
        from app.api.routes import ensure_node_undecided

        with pytest.raises(HTTPException, match="closed historical approval conflict"):
            ensure_node_undecided(
                db,
                tenant.id,
                SimpleNamespace(
                    action="rejected", entity_type="timesheet_header",
                    entity_id="00000000-0000-0000-0000-0000000000bb",
                    round_no=1, sequence_no=2,
                ),
            )
    engine.dispose()


def test_a_tenant_cannot_mint_its_own_historical_closure(queue: dict) -> None:
    """The exemption's whole guarantee is that only an operator can grant it,
    and the typed column is indeed unwritable through the API. But the
    migration that FILLS that column promotes a metadata key, and metadata is
    caller-supplied — so before an environment runs the migration, anyone
    holding `approval.record` could plant the word and be exempted the moment
    it does. The key ships in the open-core export; it is public, not secret.

    Reserved the way ORYH's hosted-agent display name is. A real closure is
    written by the operator script straight to the database and never passes
    through this path."""
    from app.core.entity_types import OPERATOR_CONFLICT_CLOSURE_KEY

    client, headers = queue["client"], queue["headers"]

    # the typed field is not an input at all
    typed = client.post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": queue["header_id"],
        "action": "approved", "round_no": 1, "sequence_no": 2,
        "approver_id": queue["approver"],
        "historical_conflict_closed": True,
    }, headers=headers)
    assert typed.status_code == 422

    # …and neither is the metadata key the migration promotes
    planted = client.post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": queue["header_id"],
        "action": "approved", "round_no": 1, "sequence_no": 2,
        "approver_id": queue["approver"],
        "metadata": {OPERATOR_CONFLICT_CLOSURE_KEY: "closed_historical_conflict"},
    }, headers=headers)
    assert planted.status_code == 400
    assert OPERATOR_CONFLICT_CLOSURE_KEY in planted.json()["detail"]

    # ordinary metadata is untouched by the guard
    ordinary = client.post("/api/v1/approval-records", json={
        "entity_type": "timesheet_header", "entity_id": queue["header_id"],
        "action": "approved", "round_no": 1, "sequence_no": 2,
        "approver_id": queue["approver"],
        "metadata": {"workflow_version": 3},
    }, headers=headers)
    assert ordinary.status_code == 201, ordinary.text


def test_the_key_the_migration_promotes_is_the_key_the_api_refuses() -> None:
    """Three copies of one string — the guard, the migration that promotes it,
    and the operator script that writes it. Drift in any direction is silent:
    a guard on the wrong word blocks nothing, and a migration on the wrong word
    promotes nothing while the operator believes the node is closed."""
    import pathlib

    from app.core.entity_types import OPERATOR_CONFLICT_CLOSURE_KEY

    root = pathlib.Path(__file__).resolve().parents[1]
    migration = (root / "alembic" / "versions"
                 / "20260812_0051_backfill_historical_conflict_column.py"
                 ).read_text(encoding="utf-8")
    assert "OPERATOR_CONFLICT_CLOSURE_KEY" in migration
    assert f"'{OPERATOR_CONFLICT_CLOSURE_KEY}'" not in migration, (
        "the migration restates the key instead of importing it"
    )

    # Found by glob rather than by path: which environment needed a closure is
    # operations material and does not belong in shipped test code. The whole
    # ops tree is absent from the open-core export, so this simply finds
    # nothing there.
    scripts = list(root.glob("ops/**/close-historical-approval-conflicts.sh"))
    for script in scripts:
        assert OPERATOR_CONFLICT_CLOSURE_KEY in script.read_text(encoding="utf-8"), script


def test_the_retirement_column_is_not_back_in_the_published_migration() -> None:
    """The exemption was written into 0049 first, and it cannot live there.

    0049 had already shipped and already run. The release guard compares the
    checksum of every migration in the live release's tree against the target's,
    so an edited 0049 refuses every future release into an environment that
    already applied it — which is how this was found, by a release stopping at
    `applied Alembic history was modified or removed`.

    Nothing about that is visible while writing the edit: the tests pass, the
    schema comes out identical, and a fresh database reaches the same place.
    Only an environment carrying the old copy disagrees, and it says so at
    deploy time. So the rule gets a test rather than a memory — 0049 predates
    the column and must keep predating it, and anything the column needs goes
    in a revision that has not shipped.
    """
    import importlib.util
    import pathlib

    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"

    def load(stem: str):
        spec = importlib.util.spec_from_file_location(stem, versions / f"{stem}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    published = load("20260810_0049_one_decision_per_node")
    retirement = load("20260812_0051_backfill_historical_conflict_column")

    assert "historical_conflict_closed" not in published._decided_predicate(), (
        "0049 has shipped and been applied; teaching it about the retirement "
        "column edits history and blocks every release into an environment "
        "that already ran it. Put it in a new revision."
    )
    source = (versions / "20260810_0049_one_decision_per_node.py").read_text(encoding="utf-8")
    assert "historical_conflict_closed" not in source, (
        "same reason: 0049 must not mention the retirement column at all"
    )

    assert retirement.down_revision == "20260810_0050", (
        "the retirement revision must sit after the leave migration, not beside it"
    )
    assert "historical_conflict_closed" in retirement._decided_predicate(), (
        "the retirement revision must narrow the index, or a retired node still "
        "collides with the decision that replaced it"
    )
