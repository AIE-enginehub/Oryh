"""Line-family and document-verb routes are declared, not hand-written
(app/api/family_routes.py). What keeps that true: every declaration is on
the contract under the name and method it says, and the modules that moved
to declarations do not quietly grow a copy-pasted line or verb handler again.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
# modules whose line families and document verbs are declared
MIGRATED = ("sales.py", "purchasing.py", "claims.py", "billing.py", "people.py", "crm.py",
            "activities.py", "shipments.py", "contracts.py")
LINE_HELPERS = {"create_item", "get_item", "update_item", "delete_item", "list_items",
                "create_adjustment", "get_adjustment", "update_adjustment", "delete_adjustment", "list_adjustments"}
VERB_HELPERS = {"delete_document", "restore_document", "submit_document"}


def test_every_declaration_is_on_the_contract() -> None:
    from app.api.family_routes import DECLARED
    from app.main import app

    assert len(DECLARED) >= 70, len(DECLARED)
    paths = app.openapi()["paths"]
    for name, method, path in DECLARED:
        op = paths["/api/v1" + path][method]
        assert op["operationId"].startswith(name + "_"), (name, method, path)


def test_a_migrated_module_keeps_no_hand_written_line_or_verb_handler() -> None:
    """The shape a declaration replaces: a routed function whose whole body is
    one call into the family machinery."""
    offenders = []
    for name in MIGRATED:
        tree = ast.parse((ROOT / "app/api" / name).read_text())
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            if not any(isinstance(d, ast.Call) and ast.unparse(d.func).startswith("router.") for d in fn.decorator_list):
                continue
            body = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))]
            if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
                continue
            callee = ast.unparse(body[0].value.func)
            if callee in LINE_HELPERS | VERB_HELPERS:
                offenders.append(f"{name}:{fn.lineno} {fn.name} -> {callee}")
    assert not offenders, "declare these instead (app/api/family_routes.py):\n  " + "\n  ".join(offenders)
