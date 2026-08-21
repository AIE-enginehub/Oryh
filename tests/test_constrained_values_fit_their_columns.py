"""Every value a CHECK constraint permits must fit the column that stores it.

`invoices.direction` was `varchar(10)`, sized for `sales`, `purchase` and
`payroll`. Adding `reimbursement` — 13 characters — extended the constraint and
never looked at the width, so Postgres refused every insert and a finance user
in production found it: the one direction that could not be created.

**The suite could not have caught it, and that is the point of this file.**
Tests run on in-memory SQLite, which does not enforce VARCHAR length at all —
the same insert succeeds there and the column quietly holds 13 characters. So
1409 passing tests said nothing about a rule only the production engine
applies.

This checks the DECLARED types instead of the running database: the CHECK
expression names the legal values, the SQLAlchemy column declares the width,
and the comparison is arithmetic that needs no engine at all. A constraint the
test database ignores is exactly the kind worth deriving rather than
exercising.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import String

from app.core.table_constraints import COLUMN_VOCABULARIES, TABLE_INVARIANTS
from app.models import Base

# A CHECK expression states its legal values as quoted literals compared
# against a column. Pull both out, so the pairing is read from the constraint
# rather than restated here — a list restated in a test drifts from the one
# the database enforces, which is the failure mode this exists to prevent.
LITERAL = re.compile(r"\(?(\w+)\)?(?:::text)?\s*=\s*'([^']+)'(?:::text)?")


def column_literals() -> dict[tuple[str, str], set[str]]:
    """Both registries, because they hold different halves of the same rule.

    `COLUMN_VOCABULARIES` is the single-column CHECKs — the bulk of them.
    `TABLE_INVARIANTS` carries the compound ones, where a value appears
    alongside conditions on other columns; `invoices.direction` lives there,
    because the direction has to agree with the counterparty. Reading only one
    would have missed the column this test was written for.
    """
    found: dict[tuple[str, str], set[str]] = {
        key: set(values) for key, values in COLUMN_VOCABULARIES.items()
    }
    for table, expression in TABLE_INVARIANTS.values():
        for column, value in LITERAL.findall(expression):
            found.setdefault((table, column), set()).add(value)
    return found


def declared_widths() -> dict[tuple[str, str], int]:
    widths: dict[tuple[str, str], int] = {}
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        if table is None:
            continue
        for column in table.c:
            if isinstance(column.type, String) and column.type.length:
                widths[(table.name, column.name)] = column.type.length
    return widths


def oversized(values: set[str], width: int) -> dict[str, int]:
    """The whole comparison, in one place a self-test can reach.

    Inline, a mutation could disable it and every parametrised case stayed
    green — with all real values fitting, `> width` and `> 9999` are
    indistinguishable. A test that re-implemented the arithmetic did not help:
    it exercised its own copy. Naming it is what makes the check checkable.
    """
    return {value: len(value) for value in values if len(value) > width}


def test_the_pairing_finds_something() -> None:
    """Guard the guard: a regex that matches nothing passes every assertion
    below while checking no constraint at all."""
    pairs = column_literals()
    assert len(pairs) >= 25, (
        f"only {len(pairs)} constrained column(s) parsed — a registry moved or the "
        "regex drifted, and this test would then check almost nothing"
    )
    assert ("invoices", "direction") in pairs, "the column this test was written for is not being read"


@pytest.mark.parametrize("table,column", sorted(column_literals()))
def test_every_permitted_value_fits(table: str, column: str) -> None:
    width = declared_widths().get((table, column))
    if width is None:
        pytest.skip(f"{table}.{column} is not a bounded string column")
    too_long = oversized(column_literals()[(table, column)], width)
    assert not too_long, (
        f"{table}.{column} is String({width}) and its CHECK permits values that do not fit: "
        f"{too_long}. Postgres refuses the insert; SQLite — which this suite runs on — does "
        "not, so nothing else here would notice."
    )


def test_the_comparison_actually_rejects_something_too_long() -> None:
    """The other guard-the-guard, and the one a mutation run demanded.

    With every real value fitting, `len(value) > width` and `len(value) > 9999`
    behave identically — so the arithmetic could be inverted or disabled and
    the parametrised tests above would stay green while checking nothing. This
    feeds the comparison a value that must fail.
    """
    too_long = oversized({"sales", "reimbursement"}, 10)
    assert too_long == {"reimbursement": 13}, (
        "the width comparison no longer rejects an oversized value — every "
        "assertion in this file is vacuous"
    )


def test_the_column_this_was_reported_on_now_fits() -> None:
    """Named explicitly, so a revert is loud rather than merely parametrised.

    A finance user could raise sales, purchase and payroll invoices and not
    reimbursement ones. The value was 13 characters; the column held 10.
    """
    width = declared_widths()[("invoices", "direction")]
    assert width >= len("reimbursement"), (
        f"invoices.direction is String({width}) and cannot hold 'reimbursement'"
    )
