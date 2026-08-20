"""A direction the server accepts must have a name in the console.

`reimbursement` was added to the API and the console was not told. Its label
came from a ternary chain that fell through to 工资条 for anything it did not
name, so a payable owed to an employee appeared in the invoice list as that
employee's **payslip** — the one mislabel in this family that reads as a
different kind of money entirely.

The chain is a lookup now, and this pins both halves: the TypeScript union that
types the field, and the label function that renders it. Neither is derived
from the server at build time, so nothing else connects them.

`direction` is deliberately a constrained column rather than a tenant
vocabulary — every guard in the settlement path branches on it, and a value a
tenant could invent would leave those guards undecidable. That is exactly why
this test can exist: the set is closed and knowable, so drift is checkable.
"""

from __future__ import annotations

import pathlib
import re

from app.core.table_constraints import TABLE_INVARIANTS

CONSOLE = pathlib.Path(__file__).resolve().parents[1] / "frontend/src"
TABLE = CONSOLE / "components/objects/ObjectRecordTable.tsx"
TYPES = CONSOLE / "api/objects.ts"


def server_directions() -> set[str]:
    """Read them from the CHECK constraint — the thing the database actually
    enforces — rather than from a list somewhere that could drift with the
    console instead of against it."""
    _, expression = TABLE_INVARIANTS["invoices_direction_counterparty_ck"]
    found = set(re.findall(r"direction\)?::text = '([a-z_]+)'::text", expression))
    if not found:
        found = set(re.findall(r"direction = '([a-z_]+)'", expression))
    assert found, "no directions parsed from the CHECK constraint"
    return found


def test_the_console_types_every_direction_the_server_accepts() -> None:
    union = re.search(r"\n  direction: ((?:\"[a-z_]+\"(?: \| )?)+);", TYPES.read_text(encoding="utf-8"))
    assert union, "the invoice direction union is no longer where this test looks"
    typed = set(re.findall(r'"([a-z_]+)"', union.group(1)))
    missing = server_directions() - typed
    assert not missing, f"the console cannot type these directions: {sorted(missing)}"


def test_the_console_names_every_direction_the_server_accepts() -> None:
    """A type is not a label. The union could carry `reimbursement` while the
    renderer still fell through to somebody else's word."""
    body = TABLE.read_text(encoding="utf-8")
    labelled = set(re.findall(r'case "([a-z_]+)":', body))
    missing = server_directions() - labelled
    assert not missing, (
        f"these directions have no console label and would render as another "
        f"kind of document: {sorted(missing)}"
    )


def test_an_unknown_direction_does_not_borrow_a_meaning() -> None:
    """The defect was not the missing case — it was the fallback. A default
    that names a real document type turns every future gap into a silent
    mislabel instead of a visible one."""
    body = TABLE.read_text(encoding="utf-8")
    default = re.search(r"default:\s*\n\s*return ([^;]+);", body)
    assert default, "the label function has no default branch"
    assert "text(" not in default.group(1), (
        "the fallback returns a translated document name — an unknown direction "
        "must show its own key, not borrow another's meaning"
    )
