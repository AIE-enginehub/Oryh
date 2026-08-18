"""The skills a person opens a session with must check they are current.

`oryh-skill-sync`'s own description says it runs "on session start" — but
nothing tells an agent a session started. An agent reaches a skill because the
person's words matched it, and nobody says "session start"; they say "我有什么
要办的" or "帮我提交工时". So the check has to hang off the skills people
actually reach, or it never runs: reported from production, where installed
skills stayed stale until someone thought to ask for an update by name.

Every reference to skill-sync in the corpus before this was an ADMIN being told
that users would sync — never a user's own skill telling it to look.
"""

from __future__ import annotations

import pathlib

import pytest

from app.services.provisioning import PRODUCT_SKILLS_DIR, read_skill_dir

MARKER = "{{include:_common/stay-current.md}}"
FRAGMENT = PRODUCT_SKILLS_DIR / "_common" / "stay-current.md"

# What a person's first sentence of the day plausibly reaches. Not every skill:
# a session that starts at `oryh-payroll` is an admin doing a specific job, and
# a manifest check there is noise.
ENTRY_SKILLS = (
    "oryh-my-work",
    "oryh-timesheet-submit",
    "oryh-expense-submit",
    "oryh-leave-submit",
    "oryh-approve",
)


def test_the_entry_skills_all_exist() -> None:
    # Guard the guard: a renamed skill would silently drop out of the sweep.
    missing = [n for n in ENTRY_SKILLS if not (PRODUCT_SKILLS_DIR / n / "SKILL.md").exists()]
    assert not missing, f"entry skills missing from the corpus: {missing}"


@pytest.mark.parametrize("name", ENTRY_SKILLS)
def test_an_entry_skill_checks_it_is_current(name) -> None:
    text = (PRODUCT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    assert MARKER in text, (
        f"{name} is a skill people start sessions with but never checks whether "
        "its instructions are stale — include _common/stay-current.md"
    )


@pytest.mark.parametrize("name", ENTRY_SKILLS)
def test_the_check_reaches_the_rendered_skill(name) -> None:
    rendered = read_skill_dir(PRODUCT_SKILLS_DIR / name)["SKILL.md"]
    assert "{{include:" not in rendered, f"{name} has an unexpanded include"
    assert "/my/skills/manifest" in rendered, f"{name} renders without the check"


def test_the_fragment_keeps_its_three_rules() -> None:
    text = FRAGMENT.read_text(encoding="utf-8")
    # Each was a deliberate decision, and losing any one changes the behaviour:
    # batching keeps it free, consent keeps instructions from changing under
    # someone mid-session, and the session rule is what makes it safe to put
    # this in five skills at once.
    assert "/my/skills/manifest" in text, "the call itself is missing"
    assert "Do NOT refresh silently" in text, "the consent rule is missing"
    assert "Once per session" in text, "the de-duplication rule is missing"


def test_the_endpoint_the_fragment_names_is_real() -> None:
    from app.main import app

    paths = set()

    def walk(routes, prefix=""):
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                context = getattr(route, "include_context", None)
                walk(nested.routes, prefix + getattr(context, "prefix", ""))
                continue
            path = getattr(route, "path", None)
            if path:
                paths.add(prefix + path)

    walk(app.routes)
    assert "/api/v1/my/skills/manifest" in paths, (
        "the fragment sends agents to an endpoint this API does not serve"
    )
