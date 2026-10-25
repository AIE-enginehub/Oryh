"""Protect backend locale boundaries and the bilingual catalog contract."""
import copy
import json
import re

from scripts.export_console_catalog import _bilingual_catalog, catalog_artifacts


def test_catalog_artifacts_restore_every_original_bilingual_label():
    english, labels = catalog_artifacts()
    expected = _bilingual_catalog()
    restored = copy.deepcopy(english)
    assert not inspect_text(english)
    for group in restored["groups"]:
        group["label"][0] = labels["groups"][group["key"]]
    for resource in restored["resources"]:
        locale = labels["resources"][resource["key"]]
        resource["label"][0] = locale["label"]
        for related in resource["related"]:
            related["label"][0] = locale["related"][f"{related['resource']}:{related['param']}"]
    assert restored == expected
    # Neither splitting the artifacts nor restoring them may mutate API state
    # or module-level vocabulary used by the next export.
    assert catalog_artifacts() == (english, labels)


def inspect_text(value):
    return re.search(r"[\u3400-\u9fff]", json.dumps(value, ensure_ascii=False))


def test_server_rendered_navigation_and_connection_examples_keep_both_languages():
    from types import SimpleNamespace
    from app.locales.zh_CN.web import MESSAGES
    from app.web.routes import templates

    for language in ("en", "zh"):
        html = templates.get_template("connect.html").render(
            request=SimpleNamespace(url=SimpleNamespace(path="/web/connect")),
            actor=SimpleNamespace(role="member"), locale=language, edition="cloud",
        )
        assert MESSAGES["connect_request"] in html
        assert (MESSAGES["open_console"] if language == "zh" else "Open the console") in html
        assert (MESSAGES["sign_out"] if language == "zh" else "Sign out") in html
