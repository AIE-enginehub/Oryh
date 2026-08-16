"""A materialized sum has exactly one writer, and it is not an endpoint.

The other half of the coupled-fact problem. `quantity_on_hand` is a running sum
of the inventory detail ledger; `applied_amount` of the payment applications;
`balance` of the billing account entries. Each is a number stored beside the
rows it is a sum of, which is a lie waiting to happen the moment two places can
move it — and the way it happens is a second write path added months later that
updates the row and forgets the ledger, or the ledger and forgets the row.

This is what keeps that from being a matter of remembering. Every such column is
listed with the one function allowed to write it, and the AST is checked. An
endpoint that starts assigning `item.quantity_on_hand` fails here rather than in
a stock count.

It is deliberately a different mechanism from the recompute in
`scripts/data_integrity_audit.py`. That one asks whether the numbers currently
agree, in a live database, after the fact. This one asks whether they still
CAN diverge, in the source, before anything ships.

`total_amount` is not in the list and must not be. On a quotation, order, or
invoice it is the AGREED document total — a negotiated fact that legitimately
differs from the line sum (抹零, a discount granted verbally), which is why
`/detail` reports both and lets an agent judge the gap. Materializing it would
destroy the distinction the design is built on.
"""

from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# column -> the single function permitted to move it in the database.
SINGLE_WRITER: dict[str, str] = {
    "quantity_on_hand": "post_inventory_detail",
    "available_to_promise": "post_inventory_detail",
    "applied_amount": "apply_payment",
    "balance": "post_account_entries",
}


def writers_of(column: str) -> set[tuple[str, str]]:
    """Every (file, enclosing function) that can move `column` in the database.

    Two shapes, because the codebase uses both and a checker that knows only
    one is worse than no checker. `item.quantity_on_hand = x` is the obvious
    one. `update(Model).values(quantity_on_hand=...)` is how the inventory
    ledger actually writes — deliberately, so the database computes the sum
    relative to its own row rather than to a value Python read earlier — and a
    first draft of this file scanned only for attribute assignment, found
    nothing, and passed. A guard that reports full coverage of a column no
    mechanism is watching is exactly the failure this suite keeps finding.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for scope in ast.walk(tree):
            if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            here = (str(path.relative_to(APP.parent)), scope.name)
            for node in ast.walk(scope):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr == column:
                        found.add(here)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("values", "update")
                    and any(kw.arg == column for kw in node.keywords)
                ):
                    found.add(here)
    return found


def test_every_materialized_sum_has_one_writer() -> None:
    offenders = {}
    for column, permitted in SINGLE_WRITER.items():
        writers = writers_of(column)
        unexpected = sorted(f"{f}:{fn}" for f, fn in writers if fn != permitted)
        if unexpected:
            offenders[column] = unexpected
    assert offenders == {}, (
        f"{offenders} — a materialized sum with a second writer drifts from its "
        "ledger the first time one path is updated and the other is not. Move the "
        "write into the permitted function, or state here why this one is different"
    )


def test_the_permitted_writers_still_exist() -> None:
    """The list above is only a guard while the names in it are real. A renamed
    helper would leave every column with zero permitted writers and this file
    passing on a technicality."""
    missing = {}
    for column, permitted in SINGLE_WRITER.items():
        writers = writers_of(column)
        if not any(fn == permitted for _f, fn in writers):
            missing[column] = permitted
    assert missing == {}, (
        f"{missing} name functions that no longer assign these columns — either the "
        "writer was renamed (update the map) or the column stopped being materialized"
    )


def test_the_agreed_total_is_not_treated_as_a_sum() -> None:
    """A regression guard on the DESIGN, not the code. If `total_amount` ever
    joins the map above, someone has decided the agreed total is a derived
    number — which contradicts every `/detail` in the sales and billing modules
    and makes 抹零 unrepresentable. That is a decision to argue, not to slip in
    with a dict entry."""
    assert "total_amount" not in SINGLE_WRITER
    assert "billed_total" not in SINGLE_WRITER
