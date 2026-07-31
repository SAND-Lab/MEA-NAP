"""Test the CAT-NAP cell-type subnetwork GUI controls.

Run from the repo root::

    uv run python python/test_gui_cell_type_groups.py

Drives the real PyQt6 widgets offscreen (``QT_QPA_PLATFORM=offscreen``, set
below) — no display needed, so this runs anywhere the GUI dependencies are
installed and skips cleanly when they are not.

What it checks:
  - the group grid compiles marker include/exclude choices into the same
    expressions :mod:`meanap.catnap.subnetwork` consumes, for any number of
    groups (not just two);
  - selections survive loading a different spreadsheet's marker set;
  - ``Params`` round-trips through ``load()``/``save()`` in every grouping mode,
    including the free-text fallback for expressions the grid cannot represent;
  - the panel auto-detects the example dataset's spreadsheet and validates
    against its markers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        print(f"  {flag} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _editor_checks(app) -> list[Check]:
    from meanap.gui.panels.cell_type_groups import (
        CellTypeGroupEditor, EXCLUDE, IGNORE, INCLUDE, _CELL_STATES, _N_LEAD,
    )

    checks: list[Check] = []
    ed = CellTypeGroupEditor()
    markers = ["NeuN+", "Mecp2+", "PV+", "SST+", "GAD+"]
    ed.set_markers(markers)

    checks.append(("starts with 2 group rows", ed._table.rowCount() == 2,
                   str(ed._table.rowCount())))
    checks.append(("marker columns match the spreadsheet", ed.markers() == markers,
                   str(ed.markers())))

    def set_cell(row: int, marker: str, state: str) -> None:
        col = _N_LEAD + markers.index(marker)
        ed._table.cellWidget(row, col).setCurrentIndex(_CELL_STATES.index(state))

    def set_name(row: int, name: str) -> None:
        ed._table.item(row, 0).setText(name)

    def set_match(row: int, match: str) -> None:
        ed._table.cellWidget(row, 1).setCurrentIndex(1 if match == "all" else 0)

    # Row 0: Excitatory = NeuN+ and none of the inhibitory markers.
    set_name(0, "Excitatory")
    set_match(0, "all")
    set_cell(0, "NeuN+", INCLUDE)
    for m in ("GAD+", "PV+", "SST+"):
        set_cell(0, m, EXCLUDE)

    # Row 1: Inhibitory = any inhibitory marker.
    set_name(1, "Inhibitory")
    set_match(1, "any")
    for m in ("GAD+", "PV+", "SST+"):
        set_cell(1, m, INCLUDE)

    # Markers appear in *column* order, which is the spreadsheet's order — not
    # the order they happen to be written in EXCITATORY_INHIBITORY_PRESET. The
    # expressions are equivalent; assert the deterministic one the grid emits.
    groups = ed.groups()
    checks.append(("Excitatory compiles to the expected expression",
                   groups.get("Excitatory") == "NeuN+ & ~PV+ & ~SST+ & ~GAD+",
                   str(groups.get("Excitatory"))))
    checks.append(("Inhibitory compiles to the expected expression",
                   groups.get("Inhibitory") == "PV+ | SST+ | GAD+",
                   str(groups.get("Inhibitory"))))

    # …and it must select the same cells as the shipped preset does.
    from meanap.catnap.subnetwork import (
        EXCITATORY_INHIBITORY_PRESET, eval_group_expression,
    )
    import numpy as np
    combos = np.array([[bool(i >> b & 1) for b in range(len(markers))]
                       for i in range(2 ** len(markers))])
    same = all(
        np.array_equal(eval_group_expression(groups[name], combos, markers),
                       eval_group_expression(EXCITATORY_INHIBITORY_PRESET[name],
                                             combos, markers))
        for name in ("Excitatory", "Inhibitory")
    )
    checks.append(("grid output is equivalent to the shipped E/I preset "
                   "on every marker combination", same, ""))

    # More than two groups — the point of the Add group button.
    for i, (name, marker) in enumerate([("Mecp2 positive", "Mecp2+"),
                                        ("PV interneurons", "PV+"),
                                        ("SST interneurons", "SST+")]):
        ed._add_btn.click()
        row = ed._table.rowCount() - 1
        set_name(row, name)
        set_cell(row, marker, INCLUDE)
    groups = ed.groups()
    checks.append(("supports 5 groups, not just 2", len(groups) == 5, str(list(groups))))
    checks.append(("extra groups compile correctly",
                   groups.get("PV interneurons") == "PV+"
                   and groups.get("SST interneurons") == "SST+", str(groups)))

    # Combined include + exclude with 'any'.
    ed._add_btn.click()
    row = ed._table.rowCount() - 1
    set_name(row, "Mixed")
    set_match(row, "any")
    set_cell(row, "PV+", INCLUDE)
    set_cell(row, "SST+", INCLUDE)
    set_cell(row, "NeuN+", EXCLUDE)
    checks.append(("'any of' with exclusions parenthesises correctly",
                   ed.groups().get("Mixed") == "(PV+ | SST+) & ~NeuN+",
                   str(ed.groups().get("Mixed"))))

    # Rows with nothing selected are dropped rather than emitting "".
    ed._add_btn.click()
    set_name(ed._table.rowCount() - 1, "Empty")
    checks.append(("rows with no markers selected are skipped",
                   "Empty" not in ed.groups(), str(list(ed.groups()))))

    # Every expression the grid produces must be valid to the analysis code.
    from meanap.catnap.subnetwork import GroupExpressionError, eval_group_expression
    import numpy as np
    identity = np.eye(len(markers), dtype=bool)
    ok, detail = True, ""
    for name, expr in ed.groups().items():
        try:
            eval_group_expression(expr, identity, markers)
        except GroupExpressionError as e:
            ok, detail = False, f"{name}: {e}"
    checks.append(("every emitted expression parses in the analysis code", ok, detail))

    # Reloading a narrower spreadsheet keeps what still applies.
    before = ed.groups()
    ed.set_markers(["NeuN+", "GAD+"])
    after = ed.groups()
    checks.append(("selections survive a marker-set change",
                   after.get("Excitatory") == "NeuN+ & ~GAD+"
                   and after.get("Inhibitory") == "GAD+", str(after)))
    checks.append(("groups whose markers all vanished are dropped",
                   "PV interneurons" not in after and "Excitatory" in before,
                   str(list(after))))

    # Round-trip through set_groups.
    ed2 = CellTypeGroupEditor()
    ed2.set_markers(markers)
    ok = ed2.set_groups(before)
    checks.append(("set_groups round-trips the grid's own output",
                   ok and ed2.groups() == before, f"{ok} {ed2.groups()}"))
    checks.append(("set_groups reports failure on an expression it cannot show",
                   ed2.set_groups({"Weird": "(NeuN+ | GAD+) & (PV+ | SST+)"}) is False,
                   ""))

    # No markers loaded yet: columns are adopted from the expressions.
    ed3 = CellTypeGroupEditor()
    ok = ed3.set_groups({"Inhibitory": "GAD+ | PV+"})
    checks.append(("set_groups works before any spreadsheet is loaded",
                   ok and ed3.markers() == ["GAD+", "PV+"]
                   and ed3.groups() == {"Inhibitory": "GAD+ | PV+"},
                   f"{ok} {ed3.markers()} {ed3.groups()}"))

    ed._remove_btn.click()
    checks.append(("Remove drops a row", ed._table.rowCount() == 6,
                   str(ed._table.rowCount())))
    return checks


def _panel_checks(app) -> list[Check]:
    from meanap.gui.panels.catnap import (
        CatNapPanel, MODE_CUSTOM, MODE_EI, MODE_EXPRESSIONS, MODE_PER_MARKER,
    )
    from meanap.params import Params

    checks: list[Check] = []
    panel = CatNapPanel()

    # ── Mode round-trips through Params ───────────────────────────────────────
    for mode, expected in [
        (MODE_PER_MARKER, None),
        (MODE_EI, "E/I"),
    ]:
        panel._subnetwork_enabled.setChecked(True)
        panel._group_mode.setCurrentText(mode)
        p = Params()
        panel.save(p)
        checks.append((f"{mode!r} saves as {expected!r}",
                       p.twop_subnetwork_groups == expected
                       and p.twop_subnetwork_analysis is True,
                       str(p.twop_subnetwork_groups)))
        panel.load(p)
        checks.append((f"{mode!r} reloads into the same mode",
                       panel._group_mode.currentText() == mode,
                       panel._group_mode.currentText()))

    # Custom grid mode.
    panel._group_mode.setCurrentText(MODE_CUSTOM)
    panel._group_editor.set_markers(["NeuN+", "GAD+", "PV+"])
    panel._group_editor.set_groups({"Excitatory": "NeuN+ & ~GAD+",
                                    "Inhibitory": "GAD+ | PV+",
                                    "PV cells": "PV+"})
    p = Params()
    panel.save(p)
    checks.append(("custom grid saves 3 groups as expressions",
                   p.twop_subnetwork_groups == {"Excitatory": "NeuN+ & ~GAD+",
                                                "Inhibitory": "GAD+ | PV+",
                                                "PV cells": "PV+"},
                   str(p.twop_subnetwork_groups)))
    panel.load(p)
    checks.append(("custom grid reloads into the grid, not free text",
                   panel._group_mode.currentText() == MODE_CUSTOM,
                   panel._group_mode.currentText()))

    # An expression the grid cannot represent must land in free-text mode.
    p2 = Params(twop_subnetwork_analysis=True,
                twop_subnetwork_groups={"Weird": "(NeuN+ | GAD+) & (PV+ | SST+)"})
    panel.load(p2)
    checks.append(("grid-inexpressible group falls back to free text",
                   panel._group_mode.currentText() == MODE_EXPRESSIONS,
                   panel._group_mode.currentText()))
    p3 = Params()
    panel.save(p3)
    checks.append(("free-text fallback preserves the expression verbatim",
                   p3.twop_subnetwork_groups == p2.twop_subnetwork_groups,
                   str(p3.twop_subnetwork_groups)))

    # Free-text parsing tolerates blanks/comments.
    panel._group_mode.setCurrentText(MODE_EXPRESSIONS)
    panel._group_text.setPlainText(
        "# a comment\n\nInhibitory = GAD+ | PV+\nExcitatory=NeuN+ & ~GAD+\nnonsense line\n"
    )
    p4 = Params()
    panel.save(p4)
    checks.append(("free text skips comments and malformed lines",
                   p4.twop_subnetwork_groups == {"Inhibitory": "GAD+ | PV+",
                                                 "Excitatory": "NeuN+ & ~GAD+"},
                   str(p4.twop_subnetwork_groups)))

    # Disabling the analysis must not lose the group definitions.
    panel._subnetwork_enabled.setChecked(False)
    p5 = Params()
    panel.save(p5)
    checks.append(("unticking the checkbox keeps the groups but disables the run",
                   p5.twop_subnetwork_analysis is False and bool(p5.twop_subnetwork_groups),
                   str(p5.twop_subnetwork_analysis)))
    return checks


def _dataset_checks(app) -> list[Check]:
    from meanap.gui.panels.catnap import CatNapPanel, MODE_EI

    checks: list[Check] = []
    panel = CatNapPanel()
    panel._subnetwork_enabled.setChecked(True)
    panel._celltype_file.setText(
        str(DATASET_DIR / RECORDING / f"PutativeCellType_{RECORDING}_PositiveOnly.csv")
    )
    panel._load_markers(verbose=True)
    checks.append(("panel loads the example spreadsheet's markers",
                   panel._group_editor.markers()
                   == ["NeuN+", "Mecp2+", "PV+", "SST+", "GAD+"],
                   str(panel._group_editor.markers())))

    panel._group_mode.setCurrentText(MODE_EI)
    panel._validate_groups()
    status = panel._group_status.text()
    checks.append(("E/I mode validates against the real markers",
                   "Excitatory" in status and "Inhibitory" in status and "⚠" not in status,
                   status))

    # Auto-detection: no explicit path, discovered from the scanned recordings.
    panel._celltype_file.setText("")
    panel._group_editor.set_markers([])
    from meanap.catnap.scanner import find_suite2p_recordings
    panel._recordings = find_suite2p_recordings(str(DATASET_DIR))
    panel._load_markers()
    checks.append((f"auto-detects the spreadsheet from {len(panel._recordings)} scanned "
                   "recording(s)",
                   panel._group_editor.markers()
                   == ["NeuN+", "Mecp2+", "PV+", "SST+", "GAD+"],
                   str(panel._group_editor.markers())))

    # A bad marker name must surface as a warning, not a silent skip.
    from meanap.gui.panels.catnap import MODE_EXPRESSIONS
    panel._group_mode.setCurrentText(MODE_EXPRESSIONS)
    panel._group_text.setPlainText("Typo = GAB+ | PV+")
    panel._validate_groups()
    checks.append(("a mistyped marker is flagged while editing",
                   "⚠" in panel._group_status.text(), panel._group_status.text()))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP cell-type subnetwork GUI")
    print("=" * 70)

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print(f"\nSKIPPED — PyQt6 not available ({e})")
        return 0

    app = QApplication.instance() or QApplication([])

    total_pass = total = 0
    for title, build in [
        ("Group grid editor:", _editor_checks),
        ("CAT-NAP panel ↔ Params:", _panel_checks),
    ]:
        p, n = _report(title, build(app))
        total_pass += p
        total += n

    if (DATASET_DIR / RECORDING).is_dir():
        p, n = _report("Real example dataset:", _dataset_checks(app))
        total_pass += p
        total += n
    else:
        print(f"\nReal example dataset — SKIPPED (not found at {DATASET_DIR})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
