"""A tier table we ship must have exactly one answer per person.

A seeded leave policy wrote its seniority bonus as two open-ended floors —
满 3 年 +2, 满 5 年 +5 — and said nothing about somebody who has passed both.
For an employee with eight years' tenure, taking the highest leaves 0 days and
adding them up leaves 2. Both readings can quote the policy.

That is worse than a wording nit, because a leave balance here is not stored:
an agent computes it from this document. The text is an executable
specification, so an ambiguity in it is two different answers to one person's
question about her own leave.

The server cannot fix this in general — `rules_json` is the tenant's prose and
the server deliberately does not parse a word of it. What we can hold is the
policies WE ship, which are the worked examples every demo and every reader
starts from. So: any tier list in `seed_demo.py` must be a set of disjoint
intervals, and a tier without an upper bound must be the last one.

Parsed out of the source rather than seeded into a database, because the point
is a property of the text we publish.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SEED = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"

# The demo seed is not part of the open-core distribution, and this file pins a
# property of the policies WE publish rather than anything the product enforces
# — so where the seed is absent there is nothing here to check.
pytestmark = pytest.mark.skipif(
    not SEED.exists(), reason="seed_demo.py is not part of this distribution"
)


def _tier_lists() -> list[tuple[int, str, list[dict]]]:
    if not SEED.exists():
        return []
    """Every list-of-dicts in the seed where the dicts carry a `*_min` bound.

    Returns (line number, the bound's field name, the tiers) so a failure names
    the place rather than the shape.
    """
    found: list[tuple[int, str, list[dict]]] = []
    tree = ast.parse(SEED.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.List) or not node.elts:
            continue
        try:
            items = [ast.literal_eval(element) for element in node.elts]
        except ValueError:
            continue
        if not all(isinstance(item, dict) for item in items):
            continue
        bounds = {key for item in items for key in item if key.endswith("_min")}
        if len(bounds) != 1:
            continue
        found.append((node.lineno, bounds.pop(), items))
    return found


def test_the_seed_ships_tier_tables() -> None:
    """If the parse stops finding them, the rest of this file silently passes."""
    assert _tier_lists(), "no tier tables found in seed_demo.py — has it moved?"


@pytest.mark.parametrize("line,field,tiers", _tier_lists(),
                         ids=lambda value: str(value) if isinstance(value, int) else "")
def test_a_shipped_tier_table_has_one_answer_per_person(line, field, tiers) -> None:
    prefix = field[: -len("_min")]
    upper = f"{prefix}_max"
    spans = []
    for tier in tiers:
        low = tier[field]
        high = tier.get(upper, float("inf"))
        assert low < high, f"{SEED.name}:{line}: tier {tier} covers nothing"
        spans.append((low, high, tier))

    spans.sort()
    for (low_a, high_a, tier_a), (low_b, high_b, tier_b) in zip(spans, spans[1:]):
        assert high_a <= low_b, (
            f"{SEED.name}:{line}: {tier_a} and {tier_b} both match anyone with "
            f"{prefix} in [{low_b}, {min(high_a, high_b)}) — the document does not "
            "say whether to take the highest or add them, so two agents reading "
            "it get different answers. Give the earlier tier a "
            f"`{upper}`, and fold the intended total into the later one."
        )


def test_the_starbridge_bonus_is_the_cumulative_reading() -> None:
    """The values, not just the shape. The seed's own comment predicts
    `应得 12（法定 5 + 司龄 7）`, so the 5-year tier has to carry 7 — the total —
    now that tiers no longer stack."""
    source = SEED.read_text(encoding="utf-8")
    assert '{"tenure_years_min": 3, "tenure_years_max": 5, "extra_days": 2}' in source
    assert '{"tenure_years_min": 5, "extra_days": 7}' in source
    assert "应得 12（法定 5 + 司龄 7）" in source
