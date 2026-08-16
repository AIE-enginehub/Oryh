"""No two API routes can answer the same URL.

Starlette matches in registration order, so wherever two routes CAN match one
URL, the order they were registered in silently decides which wins — and moving
a function between modules changes that order. `app/main.py` already carries a
warning about this for the `/web` catch-all.

Today no such pair exists across the 315 API routes: for every pair with the
same method and the same segment count, some position holds two different
literals, which no single URL can satisfy. That is what makes `routes.py` safe
to split by domain — the decomposition cannot change which handler answers.

This test exists to keep that true. The moment someone adds `POST
/invoices/bulk` beside a `POST /invoices/{invoice_id}`, order starts deciding,
and the next person to move a function will change behaviour without touching
one line of logic.
"""

from __future__ import annotations

import ast
import pathlib
import re
from itertools import combinations

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = ROOT / "app/api"

_VERBS = {"get", "post", "patch", "put", "delete"}


def _routes() -> list[tuple[str, str, str]]:
    """(method, full path, module) for every API route, prefixes applied."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(API.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r'APIRouter\(\s*prefix="([^"]*)"', text)
        prefix = match.group(1) if match else ""
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr in _VERBS
                        and decorator.args
                        and isinstance(decorator.args[0], ast.Constant)):
                    found.append((decorator.func.attr.upper(),
                                  prefix + decorator.args[0].value, path.stem))
    return found


def _can_match_the_same_url(a: str, b: str) -> bool:
    left, right = a.strip("/").split("/"), b.strip("/").split("/")
    if len(left) != len(right):
        return False
    overlapping = False
    for x, y in zip(left, right):
        x_param, y_param = x.startswith("{"), y.startswith("{")
        if x_param and y_param:
            continue
        if x_param != y_param:
            overlapping = True      # a literal against a parameter: one URL fits both
            continue
        if x != y:
            return False            # two different literals: nothing fits both
    return overlapping


def test_the_route_table_was_found() -> None:
    routes = _routes()
    assert len(routes) > 250, f"only {len(routes)} routes parsed — has app/api moved?"


def test_no_two_routes_can_answer_the_same_url() -> None:
    by_method: dict[str, list[tuple[str, str]]] = {}
    for method, path, module in _routes():
        by_method.setdefault(method, []).append((path, module))

    ambiguous = [
        f"{method} {a} [{ma}] vs {b} [{mb}]"
        for method, entries in by_method.items()
        for (a, ma), (b, mb) in combinations(entries, 2)
        if _can_match_the_same_url(a, b)
    ]
    assert not ambiguous, (
        "these routes can both match one URL, so registration order decides "
        "which answers — and any file reorganisation may change it:\n  "
        + "\n  ".join(sorted(ambiguous))
        + "\n\nGive the literal path a distinct shape, or register it "
        "deliberately and delete this test's claim that none exist."
    )
