"""The bank register's `reference_no` idempotence, on an index SQLite cannot build.

`fin_account_trans_reference_uq` (0068) is a PARTIAL unique index —
`(tenant_id, fin_account_id, reference_no) where reference_no is not null`.
SQLite has no such thing, so `Base.metadata.create_all` never makes it and the
entire SQLite suite is structurally unable to ask what happens when it fires.

It fired on a live deployment instead. Two things made that a 500:

  * the violation surfaces on the FLUSH inside `post_fin_account_trans`, not on
    the commit, and
  * only the commit was wrapped in `try/except IntegrityError`, so the 409 the
    endpoint plainly means to give was dead code.

What is pinned here is the timing, not just the status: a re-imported statement
line is a 409 that names the reference, the register does not grow, and the
balance does not move. The per-account and NULL scopes of the index are pinned
alongside, because widening the catch must not turn a legitimate second write
into a false conflict.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.postgres.conftest import needs_postgres


@pytest.fixture()
def cashier_desk(pg_sessionmaker, pg_schema):
    """The real app on owner-role sessions. RLS is not the subject here — the
    partial index is, and it applies to the owner exactly as it does to
    anybody else."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        db = pg_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            tenant = client.post(
                "/api/v1/tenants", json={"name": "Register Co"}
            ).json()["data"]
            headers = {"X-API-Key": tenant["plain_text_api_key"]}
            account = client.post(
                "/api/v1/fin-accounts",
                headers=headers,
                json={"name": "招行基本户", "opening_balance": 1000.0},
            ).json()["data"]
            yield {"client": client, "headers": headers, "account": account}
    finally:
        app.dependency_overrides.pop(get_db, None)


def _line(desk, **overrides) -> dict:
    body = {
        "fin_account_id": desk["account"]["id"],
        "amount": 300.0,
        "trans_type": "deposit",
        "reference_no": "B-001",
    }
    body.update(overrides)
    return body


def _balance(desk) -> float:
    return float(
        desk["client"]
        .get(f"/api/v1/fin-accounts/{desk['account']['id']}", headers=desk["headers"])
        .json()["data"]["current_balance"]
    )


@needs_postgres
def test_the_index_exists_at_all(pg_sessionmaker, pg_schema, clean_tables):
    """If the migration ever stops creating it, every assertion below would
    pass for the wrong reason — a conflict that cannot happen is not a
    conflict handled."""
    with pg_sessionmaker() as db:
        definition = db.execute(
            text(
                "select indexdef from pg_indexes "
                "where schemaname = :s and indexname = 'fin_account_trans_reference_uq'"
            ),
            {"s": pg_schema},
        ).scalar()
    assert definition, "0068's partial unique index is missing"
    assert "UNIQUE" in definition.upper()
    assert "reference_no IS NOT NULL" in definition


@needs_postgres
def test_a_re_imported_statement_line_is_409_not_500(cashier_desk, clean_tables):
    """The live incident itself: the second POST used to reach the client as
    `Internal Server Error` — plain text, no JSON — because the IntegrityError
    escaped from the flush before the guarded commit."""
    desk = cashier_desk
    first = desk["client"].post(
        "/api/v1/fin-account-transactions", headers=desk["headers"], json=_line(desk)
    )
    assert first.status_code == 201, first.text
    assert _balance(desk) == 1300.0

    again = desk["client"].post(
        "/api/v1/fin-account-transactions", headers=desk["headers"], json=_line(desk)
    )
    assert again.status_code == 409, again.text
    assert "B-001" in again.json()["detail"]

    # the refusal is complete: no orphan register row, no moved money
    assert _balance(desk) == 1300.0
    rows = desk["client"].get(
        f"/api/v1/fin-account-transactions?fin_account_id={desk['account']['id']}",
        headers=desk["headers"],
    ).json()["data"]
    assert sum(1 for r in rows if r.get("reference_no") == "B-001") == 1


@needs_postgres
def test_the_session_still_works_after_the_refusal(cashier_desk, clean_tables):
    """The rollback has to leave a usable session — a 409 that poisons the
    transaction would turn one duplicate line into a broken import run."""
    desk = cashier_desk
    desk["client"].post("/api/v1/fin-account-transactions",
                        headers=desk["headers"], json=_line(desk))
    desk["client"].post("/api/v1/fin-account-transactions",
                        headers=desk["headers"], json=_line(desk))

    ok = desk["client"].post(
        "/api/v1/fin-account-transactions",
        headers=desk["headers"],
        json=_line(desk, reference_no="B-002", amount=-80.0, trans_type="withdrawal"),
    )
    assert ok.status_code == 201, ok.text
    assert _balance(desk) == 1220.0


@needs_postgres
def test_null_references_repeat_and_other_accounts_keep_their_own(
    cashier_desk, clean_tables
):
    """The index is partial and per-account. Widening the except must not
    invent a conflict where the database sees none."""
    desk = cashier_desk
    for _ in range(3):
        bare = desk["client"].post(
            "/api/v1/fin-account-transactions",
            headers=desk["headers"],
            json=_line(desk, reference_no=None, amount=5.0),
        )
        assert bare.status_code == 201, bare.text

    desk["client"].post("/api/v1/fin-account-transactions",
                        headers=desk["headers"], json=_line(desk))
    other = desk["client"].post(
        "/api/v1/fin-accounts", headers=desk["headers"], json={"name": "工行户"}
    ).json()["data"]
    elsewhere = desk["client"].post(
        "/api/v1/fin-account-transactions",
        headers=desk["headers"],
        json=_line(desk, fin_account_id=other["id"]),
    )
    assert elsewhere.status_code == 201, elsewhere.text
