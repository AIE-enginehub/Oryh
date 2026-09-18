"""A custom object is filed where filing starts; anything further is a move.

`business_object.write` used to create an object in any state its type
declares, so a writer could POST one already `approved` while the same writer
could not PATCH open → approved. Filing states are the machine's `initial`
and the state its `roles.submitted` names (with no machine: `open` and
`in_review`); every other create state takes `business_object.advance`."""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Filing Co", email="admin@filing-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        writer = invite_member(client, admin, "writer", ["business_object.write:*"])
        mover = invite_member(client, admin, "mover", ["business_object.write:*", "business_object.advance:*"])

        def define(object_type: str, machine: dict) -> None:
            created = client.post("/api/v1/object-type-definitions", headers=admin, json={
                "object_type": object_type, "state_machine": machine})
            assert created.status_code == 201, created.text

        yield {"client": client, "admin": admin, "writer": writer, "mover": mover, "define": define}


def _create(desk, who: str, object_type: str, status: str, path: str = "/api/v1/business-objects"):
    type_field = "target_type" if "approval-targets" in path else "object_type"
    return desk["client"].post(path, headers=desk[who], json={
        type_field: object_type, "title": f"{object_type} {status}", "status": status})


def test_a_type_without_a_machine_files_open_or_in_review(desk) -> None:
    assert _create(desk, "writer", "field_note", "open").status_code == 201
    assert _create(desk, "writer", "field_note", "in_review").status_code == 201, \
        "handing an object in for review is how `write` alone submits"
    for decided in ("approved", "rejected", "archived"):
        refused = _create(desk, "writer", "field_note", decided)
        assert refused.status_code == 403 and "business_object.advance" in refused.text, refused.text
        assert _create(desk, "mover", "field_note", decided).status_code == 201


def test_a_machine_files_in_initial_and_its_declared_submitted_state(desk) -> None:
    review = {"initial": "draft", "states": ["draft", "submitted", "approved", "rejected"],
              "transitions": {"draft": ["submitted"], "submitted": ["approved", "rejected"]}}
    desk["define"]("warranty_claim", {**review, "roles": {"submitted": "submitted"}})
    desk["define"]("site_visit", review)

    assert _create(desk, "writer", "warranty_claim", "draft").status_code == 201
    assert _create(desk, "writer", "warranty_claim", "submitted").status_code == 201
    assert _create(desk, "writer", "warranty_claim", "approved").status_code == 403

    assert _create(desk, "writer", "site_visit", "draft").status_code == 201
    assert _create(desk, "writer", "site_visit", "submitted").status_code == 403, \
        "without roles.submitted only initial is filing — a name is not a role"
    assert _create(desk, "mover", "site_visit", "approved").status_code == 201


def test_a_stock_document_files_in_initial_only_even_if_it_names_a_submitted_state(desk) -> None:
    desk["define"]("damage_report", {
        "initial": "draft", "states": ["draft", "approved"], "transitions": {"draft": ["approved"]},
        "roles": {"submitted": "approved"}, "stock_effect": {"reason": "damaged", "state": "approved"}})
    assert _create(desk, "writer", "damage_report", "draft").status_code == 201
    assert _create(desk, "writer", "damage_report", "approved").status_code == 403, \
        "the posting state is never reachable without advance (review N01)"


def test_the_approval_target_door_holds_the_same_wall(desk) -> None:
    path = "/api/v1/approval-targets"
    assert _create(desk, "writer", "field_note", "in_review", path).status_code == 201
    refused = _create(desk, "writer", "field_note", "approved", path)
    assert refused.status_code == 403 and "business_object.advance" in refused.text, refused.text
    assert _create(desk, "mover", "field_note", "approved", path).status_code == 201
