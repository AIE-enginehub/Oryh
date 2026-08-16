"""Liveness and readiness answer different questions, and used to answer neither.

All three Kubernetes probes pointed at `/healthz`, which returns ok
unconditionally. So a pod whose database was unreachable was declared ready the
moment its port opened and was sent traffic it could only answer with 500s —
and a wedged process that could still accept a socket was never restarted.

The 2026-08-16 architecture review's 8.3. The split has a direction that
matters in both places: readiness must check the database, liveness must NOT.
A liveness probe that fails on a database blip restarts every pod at once,
which is a reconnect storm aimed at a database that is already struggling.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_livez_says_the_process_is_up(client: TestClient) -> None:
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz_still_answers_for_probes_that_have_not_moved(client: TestClient) -> None:
    """Compose and any manifest still on the old name must keep working — this
    split is not worth a coordinated restart of everything that references it."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_reports_the_database_and_the_revision(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    # reported, never gated on: a create_all schema has no stamp and serves fine
    assert "revision" in body["checks"]


def test_readyz_is_503_when_the_database_is_gone(client: TestClient, monkeypatch) -> None:
    """The case `/healthz` answered ok. 503, not an exception: a probe reads the
    status code, and a traceback every ten seconds during an outage is noise on
    top of an incident."""
    def broken():
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.db.session.create_ops_sessionmaker", lambda: broken)

    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not ready"
    assert "unreachable" in response.json()["checks"]["database"]
