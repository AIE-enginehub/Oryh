"""The server sends the work notification, because the flow agent cannot.

The flow agent decides WHETHER to notify — that is the tenant's workflow
definition's call, read at routing time. It cannot decide WHO the mail goes to
or what it says, and that is the point: the address comes from the employee
record and the body is assembled here, so an agent cannot send to an address it
chose or turn the endpoint into a relay.

Production is why this exists at all. For a live tenant, `approval-notifier`
was invoked in 0 of 60 flow runs; when a customer wrote their own notification
skill to fill the gap it sent through a mail tool their own agent happened to
have, which the flow runner does not — its pi child's environment is a
six-variable whitelist and never carries SMTP credentials.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_notifications_endpoint.json').read_text(encoding="utf-8"))


import pytest

from app.core.config import settings
from app.services.emails import outbox
from conftest import invite_member, provision_tenant


@pytest.fixture()
def workspace(client):
    tenant = provision_tenant(client, company_name="Notify Co", email="admin@notify.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    created = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"name": _ZH_TEXT['TEXT_C981FA16F2EEAB88'], "email": "mengen@notify.example"},
    )
    assert created.status_code == 201, created.text
    silent = client.post("/api/v1/employees", headers=headers, json={"name": _ZH_TEXT['TEXT_611934DF7591B884']})
    assert silent.status_code == 201, silent.text
    outbox.clear()
    return headers, created.json()["data"]["id"], silent.json()["data"]["id"]


def test_a_return_notification_carries_the_comment_verbatim(client, workspace):
    headers, employee_id, _ = workspace
    comment = _ZH_TEXT['TEXT_3389E6BE96C61371']
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "returned",
            "title": _ZH_TEXT['TEXT_B6964FE14B4D32CD'],
            "detail": comment,
            "actor_name": _ZH_TEXT['TEXT_CD485074AA3B075C'],
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["delivered"] is True

    assert len(outbox.messages) == 1
    message = outbox.messages[-1]
    assert message.to == "mengen@notify.example"
    # Verbatim: a paraphrased instruction is a different instruction, and this
    # is the text the person must act on.
    assert comment in message.body
    assert _ZH_TEXT['TEXT_CD485074AA3B075C'] in message.body


def test_the_caller_cannot_choose_the_address(client, workspace):
    headers, employee_id, _ = workspace
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "assigned",
            "title": _ZH_TEXT['TEXT_A3F5B358F0791171'],
            # Not a field. If it ever becomes one, this endpoint is a relay.
            "to": "attacker@elsewhere.example",
        },
    )
    # 422, not a silently-ignored field: RequestModel forbids extras, so an
    # address can neither be honoured nor quietly dropped. Stronger than the
    # assertion this test was first written with.
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "to"]
    assert not outbox.messages


def test_a_missing_address_is_reported_not_guessed(client, workspace):
    headers, _, silent_id = workspace
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": silent_id, "event": "assigned", "title": _ZH_TEXT['TEXT_E04F4395F0582F69']},
    )
    # Not an error: the agent did its part and a person has to fix the record.
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["delivered"] is False
    assert "no email address" in data["reason"]
    assert data["employee_name"] == _ZH_TEXT['TEXT_611934DF7591B884']
    assert not outbox.messages, "nothing may be sent when no address is on file"


def test_an_unknown_event_is_refused(client, workspace):
    headers, employee_id, _ = workspace
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "whatever", "title": "x"},
    )
    assert response.status_code == 422
    assert "event must be one of" in response.json()["detail"]
    assert not outbox.messages


def test_another_tenants_employee_is_not_reachable(client, workspace):
    headers, _, _ = workspace
    other = provision_tenant(client, company_name="Other Co", email="admin@other.example")
    other_headers = {"X-API-Key": other["plain_text_api_key"]}
    stranger = client.post(
        "/api/v1/employees",
        headers=other_headers,
        json={"name": _ZH_TEXT['TEXT_8B5824C4BBC18486'], "email": "stranger@other.example"},
    ).json()["data"]["id"]
    outbox.clear()

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": stranger, "event": "assigned", "title": "x"},
    )
    assert response.status_code == 404
    assert not outbox.messages


def test_a_todo_link_must_belong_to_that_employee(client, workspace):
    headers, employee_id, silent_id = workspace
    # A todo needs a real target; a timesheet for the OTHER employee gives one.
    header = client.post(
        "/api/v1/timesheet-headers",
        headers=headers,
        json={"employee_id": silent_id, "period_start": "2026-08-03", "period_end": "2026-08-07"},
    )
    assert header.status_code == 201, header.text
    todo = client.post(
        "/api/v1/todos",
        headers=headers,
        json={
            "employee_id": silent_id,
            "entity_type": "timesheet_header",
            "entity_id": header.json()["data"]["id"],
            "title": "somebody else's work",
        },
    )
    assert todo.status_code == 201, todo.text
    outbox.clear()

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "assigned",
            "title": "x",
            "todo_id": todo.json()["data"]["id"],
        },
    )
    assert response.status_code == 404
    assert not outbox.messages


def test_sending_leaves_a_trail_without_the_address(client, workspace):
    headers, employee_id, _ = workspace
    client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "approved",
            "title": _ZH_TEXT['TEXT_B6964FE14B4D32CD'],
            "entity_type": "timesheet_header",
            "entity_id": "22222222-2222-2222-2222-222222222222",
        },
    )
    entries = client.get(
        "/api/v1/audit-logs", headers=headers, params={"action": "notification.sent"}
    ).json()["data"]
    assert entries, "a notification must leave a trail"
    detail = entries[0]["detail"]
    assert detail["event"] == "approved"
    assert detail["employee_id"] == employee_id
    # A trail repeating every address becomes its own contact-data export.
    assert "mengen@notify.example" not in str(detail)


def test_the_permission_lists_put_this_on_the_flow_side(client, workspace):
    """Notifying is the flow side's write, like assigning the work itself."""
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, HOSTED_FLOW_AGENT_PERMISSIONS

    assert "notification.send" not in set(DEFAULT_ROLE_PERMISSIONS["member"])
    assert "notification.send" in set(HOSTED_FLOW_AGENT_PERMISSIONS)


def test_a_key_without_the_permission_is_refused(client, workspace):
    """The check itself, not the list it reads.

    The test above asserts the CATALOGUE and passed happily with
    `require_permission` deleted from the endpoint — a mutation run is what
    showed it. A permission nothing enforces is a permission that is not there,
    so this drives a real member-bound key at the real route.
    """
    headers, employee_id, _ = workspace
    member = invite_member(client, headers, "member", role="member", email="member@notify.example",
                           display_name=_ZH_TEXT['TEXT_21DFFBD46E2674C1'], password="member-pass1", key=False)

    from app.services.emails import outbox as mailbox

    bundle = client.post(f"/api/v1/users/{member.user_id}/skill-bundle", headers=headers)
    assert bundle.status_code == 200, bundle.text

    import io
    import re
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    rendered = archive.read(
        next(n for n in archive.namelist() if n.endswith("-my-work/SKILL.md"))
    ).decode()
    member_key = re.search(r"calw_[A-Za-z0-9_-]+", rendered).group(0)
    mailbox.clear()

    response = client.post(
        "/api/v1/notifications",
        headers={"X-API-Key": member_key},
        json={"employee_id": employee_id, "event": "assigned", "title": "x"},
    )
    assert response.status_code == 403, response.text
    assert "notification.send" in response.json()["detail"]
    assert not mailbox.messages, "a refused caller must not have sent anything"


def assigned_todos(client, headers, employee_id, count):
    ids = []
    for n in range(count):
        header = client.post(
            "/api/v1/timesheet-headers",
            headers=headers,
            json={"employee_id": employee_id,
                  "period_start": f"2026-0{n + 1}-05", "period_end": f"2026-0{n + 1}-09"},
        )
        assert header.status_code == 201, header.text
        todo = client.post(
            "/api/v1/todos",
            headers=headers,
            json={"employee_id": employee_id, "entity_type": "timesheet_header",
                  "entity_id": header.json()["data"]["id"],
                  "title": f"{_ZH_TEXT['TEXT_D790C0CBD379D62F']}{n + 1}{_ZH_TEXT['TEXT_B5920BB0B77A0B1D']}", "todo_type": "approval"},
        )
        assert todo.status_code == 201, todo.text
        ids.append(todo.json()["data"]["id"])
    outbox.clear()
    return ids


def test_one_run_one_person_one_mail_listing_every_todo(client, workspace):
    """Enginehub saw both shapes — 8 todos / 8 mails one day, 21 todos / 1 mail
    another, the other twenty squeezed into a title. The rule is now the
    server's: the todos are the message, one message per recipient."""
    headers, employee_id, _ = workspace
    ids = assigned_todos(client, headers, employee_id, 3)

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "assigned", "todo_ids": ids},
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["delivered"] is True
    assert len(outbox.messages) == 1
    mail = outbox.messages[0]
    assert (_ZH_TEXT['TEXT_49EF840EFE6FA1AA'] in mail.subject) if settings.resolved_locale == "zh" else ("3 items" in mail.subject)
    for n in (1, 2, 3):
        assert f"{_ZH_TEXT['TEXT_D57C50A6094DC84A']}{n}{_ZH_TEXT['TEXT_B5920BB0B77A0B1D']}" in mail.body
    assert "/console/todos" in mail.body

    trail = client.get(
        "/api/v1/audit-logs", headers=headers, params={"action": "notification.sent"}
    ).json()["data"][0]["detail"]
    assert trail["todo_ids"] == ids
    assert trail["title"] == (_ZH_TEXT['TEXT_D1A7C08DD3CEDE4B'] if settings.resolved_locale == "zh" else "3 items")


def test_a_single_todo_needs_no_title_and_reads_as_one_item(client, workspace):
    headers, employee_id, _ = workspace
    (todo_id,) = assigned_todos(client, headers, employee_id, 1)
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "assigned", "todo_ids": [todo_id]},
    )
    assert response.status_code == 202, response.text
    expected = _ZH_TEXT['TEXT_A1AD2827629DC71C'] if settings.resolved_locale == "zh" else _ZH_TEXT['TEXT_5C67BDF4F32EAD43']
    assert outbox.messages[0].subject == expected


def test_the_list_is_refused_whole_when_one_item_is_somebody_elses(client, workspace):
    headers, employee_id, silent_id = workspace
    mine = assigned_todos(client, headers, employee_id, 1)
    theirs = assigned_todos(client, headers, silent_id, 1)
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "assigned", "todo_ids": mine + theirs},
    )
    assert response.status_code == 404
    assert not outbox.messages


def test_a_notification_must_name_its_work(client, workspace):
    headers, employee_id, _ = workspace
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "assigned"},
    )
    assert response.status_code == 422
    assert "title is required unless todo_ids" in response.text

