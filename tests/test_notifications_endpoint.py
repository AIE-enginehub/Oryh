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

import pytest

from app.services.emails import outbox
from conftest import provision_tenant


@pytest.fixture()
def workspace(client):
    tenant = provision_tenant(client, company_name="Notify Co", email="admin@notify.example")
    headers = {"X-API-Key": tenant["plain_text_api_key"]}
    created = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"name": "许蒙恩", "email": "mengen@notify.example"},
    )
    assert created.status_code == 201, created.text
    silent = client.post("/api/v1/employees", headers=headers, json={"name": "无邮箱同事"})
    assert silent.status_code == 201, silent.text
    outbox.clear()
    return headers, created.json()["data"]["id"], silent.json()["data"]["id"]


def test_a_return_notification_carries_the_comment_verbatim(client, workspace):
    headers, employee_id, _ = workspace
    comment = "每周总时数需达 40 小时；本表 32 小时。任务粒度需到项目号。"
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "returned",
            "title": "许蒙恩 08/03-08/07 周工时",
            "detail": comment,
            "actor_name": "童文戟",
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
    assert "童文戟" in message.body


def test_the_caller_cannot_choose_the_address(client, workspace):
    headers, employee_id, _ = workspace
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "employee_id": employee_id,
            "event": "assigned",
            "title": "审批 许蒙恩 工时",
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
        json={"employee_id": silent_id, "event": "assigned", "title": "审批某单"},
    )
    # Not an error: the agent did its part and a person has to fix the record.
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["delivered"] is False
    assert "no email address" in data["reason"]
    assert data["employee_name"] == "无邮箱同事"
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
        json={"name": "陌生人", "email": "stranger@other.example"},
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
            "title": "许蒙恩 08/03-08/07 周工时",
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
    invited = client.post(
        "/api/v1/auth/invitations",
        headers=headers,
        json={"email": "member@notify.example", "role": "member", "name": "普通成员"},
    )
    assert invited.status_code == 201, invited.text

    from app.services.emails import outbox as mailbox

    token = next(
        line.rsplit("token=", 1)[1].strip()
        for line in mailbox.messages[-1].body.splitlines()
        if "token=" in line
    )
    assert (
        client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": token, "password": "member-pass1"},
        ).status_code
        in (200, 201)
    )
    bundle = client.post(
        f"/api/v1/users/{invited.json()['data']['id']}/skill-bundle", headers=headers
    )
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
                  "title": f"审批 第{n + 1}周工时", "todo_type": "approval"},
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
    assert "3 项" in mail.subject
    for n in (1, 2, 3):
        assert f"- 审批 第{n}周工时" in mail.body
    assert "/console/todos" in mail.body

    trail = client.get(
        "/api/v1/audit-logs", headers=headers, params={"action": "notification.sent"}
    ).json()["data"][0]["detail"]
    assert trail["todo_ids"] == ids and trail["title"] == "3 项工作"


def test_a_single_todo_needs_no_title_and_reads_as_one_item(client, workspace):
    headers, employee_id, _ = workspace
    (todo_id,) = assigned_todos(client, headers, employee_id, 1)
    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"employee_id": employee_id, "event": "assigned", "todo_ids": [todo_id]},
    )
    assert response.status_code == 202, response.text
    assert outbox.messages[0].subject == "有一项工作需要你处理：审批 第1周工时"


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

