#!/usr/bin/env python3
"""Prove the image can read a real spreadsheet, at build time.

The agent's first XLSX import raised `ModuleNotFoundError: openpyxl`. It
recovered by unzipping the workbook and reading the XML itself, which works
for a simple sheet and quietly misreads the things that make a real one hard:
a merged header, a formula cell, a second sheet, non-ASCII text, a trailing
total row that is not data.

So the fixture here is built out of exactly those, parsed back, and asserted.
Running it as a build step means a fresh Pod cannot start without the
toolchain — the failure lands on whoever is building, not on an agent halfway
through someone's import.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
except ModuleNotFoundError:  # pragma: no cover - this is the failure being prevented
    print("openpyxl is missing: an agent asked to read an .xlsx would fall back to raw XML", file=sys.stderr)
    raise


def build(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Product list"

    # a merged banner above the header row — the shape that makes a naive
    # reader treat row 1 as the header and lose every column name
    sheet["A1"] = "2026 product catalogue"
    sheet.merge_cells("A1:D1")
    sheet.append([])
    sheet.append(["Part no.", "Name", "Unit price", "Qty"])
    sheet.append(["P-001", "Endoscope lens", 1200.50, 3])
    sheet.append(["P-002", "Light source module", 8600.00, 2])
    # a formula, not a literal
    sheet["E4"] = "=C4*D4"
    # a trailing total row: present in the sheet, never a product
    sheet.append(["Total", None, None, 5])

    second = workbook.create_sheet("Suppliers")
    second.append(["Supplier code", "Name"])
    second.append(["V-001", "East China Medical Devices"])

    workbook.save(path)


def check(path: Path) -> None:
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Product list", "Suppliers"], workbook.sheetnames

    sheet = workbook["Product list"]
    assert {str(r) for r in sheet.merged_cells.ranges} == {"A1:D1"}, sheet.merged_cells.ranges
    header = [cell.value for cell in sheet[3]]
    assert header[:4] == ["Part no.", "Name", "Unit price", "Qty"], header
    assert sheet["B4"].value == "Endoscope lens", sheet["B4"].value
    assert sheet["C4"].value == 1200.50, sheet["C4"].value
    # row 6, not 7: setting E4 directly does not extend max_row, so the total
    # lands right after the last appended product
    assert sheet["A6"].value == "Total", sheet["A6"].value
    assert sheet.max_row == 6, sheet.max_row

    # the formula is readable as a formula; a values-only read gives the cached
    # result, which is None until Excel has computed it — an importer that does
    # not know the difference reports a blank price
    assert sheet["E4"].value == "=C4*D4", sheet["E4"].value
    cached = load_workbook(path, data_only=True)["Product list"]["E4"].value
    assert cached is None, f"expected no cached value in a file openpyxl wrote, got {cached!r}"

    assert workbook["Suppliers"]["B2"].value == "East China Medical Devices"


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "fixture.xlsx"
        build(fixture)
        check(fixture)
    print("XLSX TOOLCHAIN OK")
