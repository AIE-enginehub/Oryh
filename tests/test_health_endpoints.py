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

import pathlib

import pytest
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


# Whichever gateway configs this tree carries. The private tree has two; the
# open-core export renames `nginx.standalone.conf` to `nginx.conf` and ships
# one — so naming both by hand made this test fail in the export, which is the
# very defect it was written next to. Glob, and assert the list is not empty.
NGINX_CONFIGS = sorted(
    (pathlib.Path(__file__).resolve().parent.parent / "nginx").glob("nginx*.conf")
)


def test_there_is_a_gateway_config_to_check() -> None:
    assert NGINX_CONFIGS, "no nginx config found — the check below would pass vacuously"


@pytest.mark.parametrize("config", NGINX_CONFIGS, ids=lambda p: p.name)
def test_the_gateway_proxies_the_health_endpoints(config: pathlib.Path) -> None:
    """An endpoint the gateway does not route is an endpoint nobody outside the
    container can ask.

    `/livez` and `/readyz` were added to the app and the Kubernetes probes were
    repointed at them, but the nginx configs allowlist locations explicitly and
    listed only `healthz` — so a compose operator asking the entrypoint for
    readiness got nginx's own 404, which reads exactly like the app being
    broken. Found by starting a bare clone and asking it.

    Kubernetes was unaffected: those probes reach the pod directly. That is
    precisely why nothing noticed.
    """
    text = config.read_text(encoding="utf-8")
    for endpoint in ("healthz", "livez", "readyz"):
        assert endpoint in text, f"{config.name} does not route /{endpoint}"
