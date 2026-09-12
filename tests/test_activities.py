"""The record of contact: activities, events with participants, messages.

Pinned: an activity hangs off a customer, a lead or a deal and belongs to
the writer's own employee; its type and outcome are the workspace's
options. An event is planned, its participants are exactly one person each
(ours or the customer's), and logging it writes the activity and moves it
to held in one call. A message names who it was with, may have no employee
of ours, and the same Message-ID is recorded once. Everyone reads; only
the owner writes.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Desk Co", email="admin@desk.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def person(name: str, permissions: list[str]) -> dict:
            emp = client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]
            client.post("/api/v1/roles", json={"name": f"role_{name}", "permissions": permissions}, headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@desk.example", "role": f"role_{name}", "employee_id": emp},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
            key = client.post("/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                              headers=admin).json()["data"]["plain_text_api_key"]
            return {"employee_id": emp, "key": {"X-API-Key": key}}

        customer = client.post("/api/v1/customers", json={"name": "市一医院"}, headers=admin).json()["data"]
        contact = client.post("/api/v1/customer-contacts", headers=admin,
                              json={"customer_id": customer["id"], "name": "王主任", "phone": "13900000001"}).json()["data"]
        yield {"client": client, "admin": admin, "person": person, "customer": customer, "contact": contact}


def test_an_activity_is_a_confirmed_contact_on_a_party_and_belongs_to_its_writer(desk) -> None:
    client = desk["client"]
    zhang = desk["person"]("zhang", ["crm.own"])
    li = desk["person"]("li", ["crm.own"])

    nobody = client.post("/api/v1/activities", headers=zhang["key"], json={
        "activity_type": "call", "occurred_at": "2026-09-10T09:00:00+08:00", "subject": "回访",
    })
    assert nobody.status_code == 422, "an activity hangs off a customer, a lead or a deal"
    bad_type = client.post("/api/v1/activities", headers=zhang["key"], json={
        "customer_id": desk["customer"]["id"], "activity_type": "telepathy",
        "occurred_at": "2026-09-10T09:00:00+08:00", "subject": "回访",
    })
    assert bad_type.status_code == 422
    made = client.post("/api/v1/activities", headers=zhang["key"], json={
        "customer_id": desk["customer"]["id"], "contact_id": desk["contact"]["id"],
        "activity_type": "call", "occurred_at": "2026-09-10T09:00:00+08:00",
        "subject": "回访设备科", "content": "王主任说十月立项，先要报价。", "source_text": "王主任：十月立项，你们先报个价",
        "outcome": "positive", "next_action": "发报价", "next_action_at": "2026-09-12T09:00:00+08:00",
    })
    assert made.status_code == 201, made.text
    activity = made.json()["data"]
    assert activity["employee_id"] == zhang["employee_id"], "the writer's own employee, without being told"

    # someone else's activity is theirs to change, not mine; everyone reads
    assert client.patch(f"/api/v1/activities/{activity['id']}", headers=li["key"], json={"outcome": "neutral"}).status_code == 403
    assert client.get(f"/api/v1/activities/{activity['id']}", headers=li["key"]).status_code == 200
    listed = client.get(f"/api/v1/activities?customer_id={desk['customer']['id']}&occurred_from=2026-09-01T00:00:00Z&order_by=-occurred_at&page=1&size=10",
                        headers=li["key"]).json()
    assert listed["meta"]["total"] == 1 and listed["data"][0]["subject"] == "回访设备科"
    gone = client.delete(f"/api/v1/activities/{activity['id']}", headers=zhang["key"])
    assert gone.status_code == 204
    assert client.get(f"/api/v1/activities?customer_id={desk['customer']['id']}", headers=li["key"]).json()["data"] == []


def test_an_event_is_planned_with_its_people_and_logging_it_writes_the_activity(desk) -> None:
    client = desk["client"]
    zhang = desk["person"]("zhang", ["crm.own"])
    li = desk["person"]("li", ["crm.own"])
    backwards = client.post("/api/v1/events", headers=zhang["key"], json={
        "subject": "现场演示", "starts_at": "2026-09-15T14:00:00+08:00", "ends_at": "2026-09-15T13:00:00+08:00",
    })
    assert backwards.status_code == 422
    made = client.post("/api/v1/events", headers=zhang["key"], json={
        "subject": "现场演示", "event_type": "demo", "customer_id": desk["customer"]["id"],
        "starts_at": "2026-09-15T14:00:00+08:00", "ends_at": "2026-09-15T16:00:00+08:00", "location": "设备科",
    })
    assert made.status_code == 201, made.text
    event = made.json()["data"]
    assert event["event_no"].startswith("EV-") and event["status"] == "planned"

    both = client.post("/api/v1/event-participants", headers=zhang["key"],
                       json={"event_id": event["id"], "employee_id": li["employee_id"], "contact_id": desk["contact"]["id"]})
    assert both.status_code == 422, "one person per row"
    ours = client.post("/api/v1/event-participants", headers=zhang["key"],
                       json={"event_id": event["id"], "employee_id": li["employee_id"], "response": "accepted"})
    assert ours.status_code == 201, ours.text
    theirs = client.post("/api/v1/event-participants", headers=zhang["key"],
                         json={"event_id": event["id"], "contact_id": desk["contact"]["id"], "response": "invited"})
    assert theirs.status_code == 201
    assert client.post("/api/v1/event-participants", headers=zhang["key"],
                       json={"event_id": event["id"], "contact_id": desk["contact"]["id"]}).status_code == 409
    assert client.post("/api/v1/event-participants", headers=li["key"],
                       json={"event_id": event["id"], "employee_id": zhang["employee_id"]}).status_code == 403

    # the machine: planned → held is the log's write; a raw jump to held is legal too but logs nothing
    logged = client.post(f"/api/v1/events/{event['id']}/log", headers=zhang["key"], json={
        "content": "演示顺利，主任要求下周报价。", "outcome": "positive", "next_action": "报价", "next_action_at": "2026-09-22T09:00:00+08:00",
    })
    assert logged.status_code == 201, logged.text
    activity = logged.json()["data"]
    assert activity["event_id"] == event["id"] and activity["activity_type"] == "meeting"
    assert activity["contact_id"] == desk["contact"]["id"] and activity["customer_id"] == desk["customer"]["id"]
    assert activity["subject"] == "现场演示" and activity["occurred_at"].startswith("2026-09-15T")
    held = client.get(f"/api/v1/events/{event['id']}", headers=li["key"]).json()["data"]
    assert held["status"] == "held"
    # held freezes the event's fields; logging twice is refused by the machine
    assert client.patch(f"/api/v1/events/{event['id']}", headers=zhang["key"], json={"location": "别处"}).status_code == 409
    again = client.post(f"/api/v1/events/{event['id']}/log", headers=zhang["key"], json={"content": "x"})
    assert again.status_code == 201, "a second log on a held event is another activity, not a state change"

    internal = client.post("/api/v1/events", headers=zhang["key"],
                           json={"subject": "周会", "starts_at": "2026-09-16T09:00:00+08:00"}).json()["data"]
    assert client.post(f"/api/v1/events/{internal['id']}/log", headers=zhang["key"], json={}).status_code == 422
    window = client.get("/api/v1/events?starts_from=2026-09-15T00:00:00Z&starts_thru=2026-09-15T23:59:59Z&status=held",
                        headers=li["key"]).json()["data"]
    assert [e["id"] for e in window] == [event["id"]]


def test_a_message_is_a_fact_with_a_party_and_one_row_per_message_id(desk) -> None:
    client = desk["client"]
    zhang = desk["person"]("zhang", ["crm.own"])
    nobody = client.post("/api/v1/communication-events", headers=zhang["key"], json={
        "channel": "email", "direction": "inbound", "occurred_at": "2026-09-10T10:00:00+08:00", "subject": "询价",
    })
    assert nobody.status_code == 422, "a message names who it was with"
    bad_channel = client.post("/api/v1/communication-events", headers=zhang["key"], json={
        "channel": "pigeon", "direction": "inbound", "occurred_at": "2026-09-10T10:00:00+08:00",
        "customer_id": desk["customer"]["id"],
    })
    assert bad_channel.status_code == 422
    mail = client.post("/api/v1/communication-events", headers=zhang["key"], json={
        "channel": "email", "direction": "inbound", "occurred_at": "2026-09-10T10:00:00+08:00",
        "subject": "询价：监护仪 20 台", "body": "请报价。", "from_address": "wang@hospital.example",
        "to_addresses": ["sales@desk.example"], "message_id": "<abc123@hospital.example>", "thread_id": "T-1",
        "customer_id": desk["customer"]["id"], "contact_id": desk["contact"]["id"],
    })
    assert mail.status_code == 201, mail.text
    assert mail.json()["data"]["employee_id"] == zhang["employee_id"]
    twice = client.post("/api/v1/communication-events", headers=zhang["key"], json={
        "channel": "email", "direction": "inbound", "occurred_at": "2026-09-10T10:00:00+08:00",
        "message_id": "<abc123@hospital.example>", "customer_id": desk["customer"]["id"],
    })
    assert twice.status_code == 409 and mail.json()["data"]["id"] in twice.json()["detail"]
    reply = client.post("/api/v1/communication-events", headers=zhang["key"], json={
        "channel": "email", "direction": "outbound", "occurred_at": "2026-09-10T11:00:00+08:00",
        "subject": "Re: 询价", "to_addresses": ["wang@hospital.example"], "thread_id": "T-1",
        "customer_id": desk["customer"]["id"],
    })
    assert reply.status_code == 201
    thread = client.get("/api/v1/communication-events?thread_id=T-1&order_by=occurred_at", headers=zhang["key"]).json()["data"]
    assert [m["direction"] for m in thread] == ["inbound", "outbound"]
    # a follow-up activity names the message it came from
    follow = client.post("/api/v1/activities", headers=zhang["key"], json={
        "customer_id": desk["customer"]["id"], "activity_type": "message",
        "occurred_at": "2026-09-10T11:00:00+08:00", "subject": "回复询价",
        "communication_event_id": mail.json()["data"]["id"],
    })
    assert follow.status_code == 201, follow.text
