"""The models must know every CHECK the database has.

SQLite builds its schema from `Base.metadata`, so a constraint the model does
not declare does not exist in any test database. The schema has eighty-one and
the models declared twenty-two, which is why the suite ran green over
`cancelled` on `todos.status` for the life of the product — and, because
deleting a document cancels its todos, over document deletion being a 500 in
production.

`app.core.table_constraints` now holds them once and attaches them to the metadata.
These tests keep that registry honest in both directions, and pin the one place
where a fixed list is the WRONG answer.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.type_options import TYPE_FAMILIES
from app.core.table_constraints import (
    COLUMN_VOCABULARIES,
    TABLE_INVARIANTS,
    apply_table_constraints,
    constraint_name,
)
from app.db.session import Base
import app.models  # noqa: F401  (registers the tables and applies the registry)

SNAPSHOT = pathlib.Path(__file__).resolve().parents[1] / "sql" / "schema.sql"

_CREATE = re.compile(r"CREATE TABLE (?:\w+\.)?(\w+) \((.*?)^\);", re.S | re.M)
_CHECK = re.compile(r"CONSTRAINT (\w+) CHECK \((.*)\)$")
# A pure vocabulary: `col = ANY (ARRAY[...])` and nothing else. The five
# conditional CHECKs that merely mention literals — "a restricted policy must
# name a capability" — are logic, and flattening them into a value list would
# lose the logic.
_PURE = re.compile(
    r"^\(\(?(\w+)\)?(?:::text)? = ANY \(\(?ARRAY\[(.*?)\]\)?(?:::text\[\])?\)\)$"
)
_VALUE = re.compile(r"'([^']*)'::(?:text|character varying)")


def _shipped() -> dict[tuple[str, str], tuple[str, ...]]:
    found: dict[tuple[str, str], tuple[str, ...]] = {}
    for table, body in _CREATE.findall(SNAPSHOT.read_text(encoding="utf-8")):
        for line in body.splitlines():
            match = _CHECK.search(line.strip().rstrip(","))
            if not match:
                continue
            pure = _PURE.match(match.group(2))
            if pure:
                found[(table, pure.group(1))] = tuple(
                    sorted(set(_VALUE.findall(pure.group(2))))
                )
    return found


def test_the_snapshot_still_parses() -> None:
    """Everything below is vacuous if the shape of the dump changes."""
    assert len(_shipped()) >= 25, "hardly any vocabulary CHECKs found — did the DDL move?"


def test_every_shipped_vocabulary_is_registered() -> None:
    """The direction that was broken: the database knew things the model did
    not, so SQLite was more permissive than production."""
    missing = sorted(set(_shipped()) - set(COLUMN_VOCABULARIES))
    assert not missing, (
        "these columns carry a fixed-value CHECK in sql/schema.sql that "
        f"app/core/table_constraints.py does not register: {missing}. Until they are "
        "registered, no test database has them."
    )


def test_no_registered_vocabulary_is_absent_from_the_schema() -> None:
    """The other direction: a registry entry with no constraint behind it
    enforces something in tests that production does not enforce, which is its
    own kind of lie."""
    extra = sorted(set(COLUMN_VOCABULARIES) - set(_shipped()))
    assert not extra, (
        f"registered but absent from sql/schema.sql: {extra}. Either add a "
        "migration, or drop the entry."
    )


@pytest.mark.parametrize("key", sorted(COLUMN_VOCABULARIES), ids=lambda k: f"{k[0]}.{k[1]}")
def test_the_registered_values_match_the_shipped_ones(key) -> None:
    shipped = _shipped().get(key)
    assert shipped is not None
    assert tuple(sorted(COLUMN_VOCABULARIES[key])) == shipped, (
        f"{key[0]}.{key[1]}: the registry and the shipped DDL disagree about "
        "which values are allowed"
    )


def _shipped_names() -> set[str]:
    names: set[str] = set()
    for _table, body in _CREATE.findall(SNAPSHOT.read_text(encoding="utf-8")):
        for line in body.splitlines():
            match = _CHECK.search(line.strip().rstrip(","))
            if match:
                names.add(match.group(1))
    return names


def test_every_shipped_check_is_declared_somewhere() -> None:
    """The whole gap, in one assertion: eighty-one constraints in the schema,
    twenty-two on the models. The rest existed only in production."""
    registered = {constraint_name(t, c) for (t, c) in COLUMN_VOCABULARIES}
    registered |= set(TABLE_INVARIANTS)
    hand_declared = {
        c.name
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if getattr(c, "name", None)
    }
    missing = sorted(_shipped_names() - registered - hand_declared)
    assert not missing, (
        f"CHECK constraints in sql/schema.sql that no test database will have: "
        f"{missing}"
    )


def test_no_invariant_is_absent_from_the_schema() -> None:
    extra = sorted(set(TABLE_INVARIANTS) - _shipped_names())
    assert not extra, (
        f"registered but absent from sql/schema.sql: {extra}. Either add a "
        "migration, or drop the entry."
    )


def test_invariant_expressions_are_dialect_portable() -> None:
    """SQLite builds from these too, and `= ANY (ARRAY[...])` is Postgres-only.
    Getting this wrong does not fail one test — it fails `create_all`, so every
    test errors at once and the cause is buried."""
    postgres_only = sorted(
        name for name, (_table, expression) in TABLE_INVARIANTS.items()
        if "ANY (ARRAY" in expression or "::" in expression
    )
    assert not postgres_only, (
        f"{postgres_only} use Postgres-only syntax; write `x in (...)` and drop "
        "the casts"
    )


def test_the_constraints_reach_the_metadata() -> None:
    """The registry is inert unless something attaches it. Re-running the
    applier must find nothing left to do."""
    assert apply_table_constraints(Base.metadata) == 0, (
        "constraints were still unattached — app/models.py should apply the "
        "registry after its last class"
    )
    for (table_name, column) in COLUMN_VOCABULARIES:
        table = Base.metadata.tables.get(table_name)
        if table is None:  # platform tables, absent from the standalone edition
            continue
        names = {getattr(c, "name", None) for c in table.constraints}
        assert constraint_name(table_name, column) in names, (
            f"{table_name}.{column} is registered but not on the table"
        )


def test_a_tenant_extensible_vocabulary_has_no_fixed_list() -> None:
    """The one place a fixed CHECK is the wrong answer.

    `TypeOption` exists so a workspace names its own values, and the write path
    validates against the tenant's active options. A fixed list on the same
    column is not a stricter version of that rule — it contradicts it, and the
    product then accepts the definition and rejects the use.

    `timesheet_entries.work_type` did exactly that: `POST /type-options`
    returned 201 and logging hours against the new type returned 500, from
    before type options existed until `20260813_0054` dropped the constraint.
    """
    clashes = sorted(
        f"{table}.{column}"
        for (table, column) in COLUMN_VOCABULARIES
        if column in TYPE_FAMILIES
    )
    assert not clashes, (
        f"{clashes} are tenant-extensible vocabularies with a fixed CHECK. "
        "Defining a value will succeed and using it will fail. Drop the "
        "constraint — the tenant's option list is the vocabulary."
    )
