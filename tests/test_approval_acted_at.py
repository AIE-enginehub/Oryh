"""When an approval happened is the server's answer, not the caller's guess.

`acted_at` was required. A required timestamp is a question an agent cannot
answer — it has no clock — and every skill example showed a literal, so the
template got filled with the most plausible date in view: usually one off the
document being approved. Production ended up holding approvals recorded before
the record they decide existed, which is not a wrong number but a trail that
cannot be true.

These pin the contract that replaced it: omitting it is the normal path, and
the two shapes a guess takes — forward into the future, backward past the
target's own creation — are refused with a message that says what to do
instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import provision_tenant


@pytest.fixture()
def node(client):
    """A submitted timesheet, ready for a decision at round 1 step 2."""
    ctx = provision_tenant(client, company_name="Acted Co", email="admin@acted-co.example")
    key = {"X-API-Key": ctx["plain_text_api_key"]}
    owner = client.post(
        "/api/v1/employees", json={"name": "王小明"}, headers=key
    ).json()["data"]["id"]
    header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": owner, "period_start": "2026-06-01", "period_end": "2026-06-07"},
        headers=key,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/timesheet-entries",
        json={"header_id": header, "employee_id": owner, "work_date": "2026-06-01", "hours": 8},
        headers=key,
    )
    client.post(f"/api/v1/timesheet-headers/{header}/submit", json={}, headers=key)
    return client, key, header


def _decide(client, key, header, **extra):
    body = {
        "entity_type": "timesheet_header", "entity_id": header,
        "action": "approved", "round_no": 1, "sequence_no": 2,
    }
    body.update(extra)
    return client.post("/api/v1/approval-records", json=body, headers=key)


def test_omitting_it_is_the_normal_path(node) -> None:
    client, key, header = node
    created = _decide(client, key, header)
    assert created.status_code == 201, created.text

    stamped = datetime.fromisoformat(created.json()["data"]["acted_at"].replace("Z", "+00:00"))
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - stamped).total_seconds()) < 300, (
        "the server did not stamp the moment of the call"
    )


def test_a_time_before_the_target_existed_is_refused(node) -> None:
    """The production shape. A date lifted off the document being approved is
    almost always earlier than the row, because the row was made today."""
    client, key, header = node
    refused = _decide(client, key, header, acted_at="2026-06-04T10:00:00Z")
    assert refused.status_code == 422, refused.text

    detail = refused.json()["detail"]
    assert "before this record existed" in detail
    # the message has to say what to do instead, or an agent reads a 422 as
    # "try a different value" and guesses again
    assert "Omit acted_at" in detail


def test_a_future_time_is_refused(node) -> None:
    client, key, header = node
    ahead = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    refused = _decide(client, key, header, acted_at=ahead)
    assert refused.status_code == 422, refused.text
    assert "in the future" in refused.json()["detail"]


def test_a_supplied_time_within_the_record_s_life_is_kept(node) -> None:
    """Backfilling stays possible. The one legitimate case in the product —
    a missing `submitted` fact taking the document's own `submitted_at` — is
    this shape: a time the record itself already carries, not an invention."""
    client, key, header = node
    detail = client.get(f"/api/v1/timesheet-headers/{header}", headers=key).json()["data"]
    submitted_at = detail["submitted_at"]

    created = _decide(client, key, header, acted_at=submitted_at)
    assert created.status_code == 201, created.text
    assert created.json()["data"]["acted_at"].startswith(submitted_at[:19])


def test_clock_skew_does_not_trip_the_future_check(node) -> None:
    """An agent stamping an honest `now` on a host a minute or two ahead must
    not be refused; that would push it back to guessing."""
    client, key, header = node
    slightly_ahead = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    created = _decide(client, key, header, acted_at=slightly_ahead)
    assert created.status_code == 201, created.text
