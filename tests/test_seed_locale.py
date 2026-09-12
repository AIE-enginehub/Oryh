"""What a fresh workspace is seeded with, in the deployment's language.

The vocabularies, the capability catalogue and the system emails were Chinese
everywhere, so the open-core repository seeded an English-speaking company
with 店铺 and 提交自己的工时. One content locale now decides: explicit
ORYH_LOCALE, else English on a standalone deployment and Chinese on the
hosted service. The Chinese tables are the product for its market and stay
exactly as they were; the English ones must mirror them name for name.
"""

from __future__ import annotations

import re

import pytest

from app.core import permissions, type_options
from app.core.config import settings
from app.services.emails import outbox, send_work_notification

CJK = re.compile(r"[一-鿿]")


def test_the_english_vocabulary_mirrors_the_chinese_one_name_for_name() -> None:
    zh, en = type_options.SYSTEM_TYPE_OPTIONS, type_options.SYSTEM_TYPE_OPTIONS_EN
    assert list(zh) == list(en), "same families in the same order"
    for family in zh:
        assert [n for n, _, _ in zh[family]] == [n for n, _, _ in en[family]], family
        for name, title, description in en[family]:
            assert title and description, (family, name)
            assert not CJK.search(title + description), (family, name, title, description)


def test_the_english_catalogue_names_every_capability_once() -> None:
    names = [name for name, *_ in permissions.SYSTEM_CAPABILITIES]
    assert names == list(permissions.CAPABILITY_TEXT_EN), "same capabilities, same order"
    for name, (title, description) in permissions.CAPABILITY_TEXT_EN.items():
        assert title and description and not CJK.search(title + description), name


def test_the_locale_follows_the_edition_unless_stated(monkeypatch) -> None:
    monkeypatch.setattr(settings, "locale", "")
    monkeypatch.setattr(settings, "edition", "standalone")
    assert settings.resolved_locale == "en"
    monkeypatch.setattr(settings, "edition", "cloud")
    assert settings.resolved_locale == "zh"
    monkeypatch.setattr(settings, "locale", "en")
    assert settings.resolved_locale == "en", "a stated locale wins over the edition"
    with pytest.raises(ValueError):
        settings.__class__.model_validate({**settings.model_dump(), "locale": "fr"})


def test_seeding_picks_the_locale(monkeypatch) -> None:
    monkeypatch.setattr(settings, "locale", "en")
    assert type_options.system_type_options()["facility_type"][0] == ("store", "Store", "A shop open to customers")
    catalogue = {name: title for name, _, title, _ in permissions.system_capabilities()}
    assert catalogue["timesheet.submit_own"] == "Submit own timesheet"
    monkeypatch.setattr(settings, "locale", "zh")
    assert type_options.system_type_options()["facility_type"][0][1] == "店铺"
    assert permissions.system_capabilities() == permissions.SYSTEM_CAPABILITIES


def test_a_fresh_workspace_on_a_standalone_deployment_reads_english(monkeypatch) -> None:
    from conftest import make_client, provision_tenant

    monkeypatch.setattr(settings, "locale", "en")
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Acme", email="admin@acme.example")
        key = {"X-API-Key": t["plain_text_api_key"]}
        data = client.get("/api/v1/capabilities", headers=key).json()["data"]
        rows = [c for group in data.values() for c in group] if isinstance(data, dict) else data
        caps = {c["name"]: c for c in rows if isinstance(c, dict) and "name" in c}
        assert "timesheet.submit_own" in caps, str(data)[:200]
        assert caps["timesheet.submit_own"]["title"] == "Submit own timesheet"
        assert not any(CJK.search((c.get("title") or "") + (c.get("description") or "")) for c in caps.values())
        options = client.get("/api/v1/type-options?family=leave_type", headers=key).json()["data"]
        titles = {o["name"]: o["title"] for o in options}
        assert titles["annual"] == "Annual leave" and not any(CJK.search(v) for v in titles.values())


def test_work_notifications_are_written_in_the_locale(monkeypatch) -> None:
    outbox.clear()
    monkeypatch.setattr(settings, "locale", "en")
    send_work_notification(to="a@x.example", recipient_name="Ann", event="returned", title="Timesheet 08/03",
                           detail="hours do not add up", actor_name="Bob", link="https://x/console/todos")
    mail = outbox.messages[-1]
    assert mail.subject == "Returned for rework: Timesheet 08/03"
    assert "Handled by: Bob" in mail.body and "hours do not add up" in mail.body and not CJK.search(mail.body)
    monkeypatch.setattr(settings, "locale", "zh")
    send_work_notification(to="a@x.example", recipient_name="安", event="approved", title="工时", detail=None,
                           actor_name=None, link="https://x/console/todos")
    assert outbox.messages[-1].subject == "你的单据已通过：工时"
