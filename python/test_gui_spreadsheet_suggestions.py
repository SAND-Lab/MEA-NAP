"""Test suggesting each recording's group and DIV from its name.

Run from the repo root::

    uv run python python/test_gui_spreadsheet_suggestions.py [screenshot-dir]

  A. which part of the names is suggested as the group and DIV, on naming
     schemes taken from real batches (the group a person gave each one is what
     the suggestion has to reproduce, up to the label);
  B. the editor: a sheet built from a folder starts filled in and marked as
     suggested, parts can be picked by hand, suggested groups can be renamed,
     editing or saving confirms, and what is saved is what the pipeline reads;
  C. the simple view offers to build a sheet from the folder's recordings.

GUI settings go to a temporary folder, so this never touches the person's own.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.panels.spreadsheet_editor import SpreadsheetEditor  # noqa: E402
from meanap.pipeline.name_parts import (  # noqa: E402
    div_from_part, name_parts, part_values, suggest_name_parts,
)
from meanap.pipeline.spreadsheet import (  # noqa: E402
    new_recording_table, read_recording_csv,
)

FAILURES: list[str] = []
ERRORS: list[str] = []


def _excepthook(kind, value, tb) -> None:
    ERRORS.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _excepthook


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def same_partition(a: list[str], b: list[str]) -> bool:
    """Whether *a* and *b* group the recordings identically, whatever the labels."""
    pairs = set(zip(a, b))
    return len(pairs) == len(set(a)) == len(set(b))


# ── A. The suggestions ───────────────────────────────────────────────────────

#: (scheme, names, the groups a person gave them)
SCHEMES = [
    ("CAT-NAP Mecp2: batch ids vary too, genotype is the word",
     ["OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21",
      "OPME240517_17_20240602_P1_pup2D_WT_MOI50000_DIV16",
      "OPME240607_6_20240719_P1_pup1B_WT_MOI50000_DIV42",
      "OPME240607_41_20240713_P1_pup3E_KO_MOI50000_DIV36",
      "OPME230825_3_20230915_P1_pup4C_Het_MOI50000_DIV21"],
     ["Mecp2_Het", "Wildtype", "Wildtype", "Mecp2_KO", "Mecp2_Het"]),
    ("MEA batch with genotype and well",
     ["SYN_20260904_WT_DIV14_A1", "SYN_20260904_WT_DIV14_A2",
      "SYN_20260904_KO_DIV14_B1", "SYN_20260904_KO_DIV21_B2"],
     ["WT", "WT", "KO", "KO"]),
    ("one line, wells only: the shared name is the group",
     ["NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"],
     ["NGN2", "NGN2"]),
    ("no genotype word: the repeating part with no digits",
     ["exp-ctrlA-d7-w1", "exp-ctrlA-d7-w2", "exp-lineB-d7-w1", "exp-lineB-d7-w2"],
     ["ctrlA", "ctrlA", "lineB", "lineB"]),
]


def suggestion_section() -> None:
    print("A. Suggesting group and DIV from names")
    check("names split at _ - . and spaces",
          name_parts("a_b-c.d e  f") == ["a", "b", "c", "d", "e", "f"])
    check("DIV read from DIV14, d7, day21 and a bare 35",
          [div_from_part(p) for p in ("DIV14", "d7", "day21", "35", "P1", "20230208")]
          == ["14", "7", "21", "35", "", ""])
    for label, names, truth in SCHEMES:
        s = suggest_name_parts(names)
        got = part_values(names, s.group_part) if s.group_part is not None else []
        check(f"{label}: groups match the person's", bool(got) and same_partition(got, truth),
              f"part={s.group_part} got={got}")
    s = suggest_name_parts(["exp-ctrlA-d7-w1", "exp-lineB-d14-w2"])
    check("a DIV part is found when it is not spelled DIV", s.div_part == 2, str(s))
    s = suggest_name_parts(["HCNT26_DIV58_E2"])
    check("a single recording with no group word: no guess", s.group_part is None, str(s))
    s = suggest_name_parts(["20230101_A1", "20230102_A2"])
    check("dates and wells are never a group", s.group_part is None, str(s))


# ── B. The editor ────────────────────────────────────────────────────────────

def editor_section(tmp: Path, shots: Path | None) -> None:
    print("B. Spreadsheet editor")
    names = ["SYN_20260904_WT_DIV14_A1", "SYN_20260904_WT_DIV14_A2",
             "SYN_20260904_KO_DIV14_B1", "SYN_20260904_KO_DIV21_B2"]
    ed = SpreadsheetEditor(table=new_recording_table(names), suggest=True)
    ed.resize(900, 560)
    ed.show()
    t = ed.table()
    check("a sheet built from a folder starts with group and DIV filled in",
          list(t.iloc[:, 2]) == ["WT", "WT", "KO", "KO"]
          and list(t.iloc[:, 1]) == ["14", "14", "14", "21"], t.to_string())
    check("marked as suggestions", all(ed.is_suggested(r, c) for r in range(4) for c in (1, 2)))
    check("saying what was picked and why",
          "Part 3" in ed.name_parts_note.text() and "KO, WT" in ed.name_parts_note.text(),
          ed.name_parts_note.text())
    check("one chip per part of the name",
          [c.text() for c in ed._chips] == name_parts(names[0]))
    check("with the group and DIV parts highlighted",
          ed._chips[2].property("role") == "group" and ed._chips[3].property("role") == "div",
          str([c.property("role") for c in ed._chips]))
    if shots:
        app.processEvents()
        ed.grab().save(str(shots / "spreadsheet_suggested.png"))

    ed.rename_fields["WT"].setText("Wildtype")
    ed.rename_fields["WT"].textEdited.emit("Wildtype")
    check("renaming a suggested group renames every recording in it",
          list(ed.table().iloc[:, 2]) == ["Wildtype", "Wildtype", "KO", "KO"])

    ed._table.item(3, 2).setText("Het")
    check("an edited cell is no longer a suggestion",
          not ed.is_suggested(3, 2) and ed.is_suggested(2, 2))

    ed.fill_group_from_part(0)
    check("any part can be picked as the group by hand",
          list(ed.table().iloc[:, 2]) == ["SYN"] * 4)
    ed.fill_group_from_part(2)
    path = ed.save_to(tmp / "batch.csv")
    check("saving confirms the suggestions",
          not any(ed.is_suggested(r, c) for r in range(4) for c in (1, 2)))
    recs = read_recording_csv(path, "A2:A100000")
    check("and the pipeline reads back what was suggested",
          [(r.filename, r.div, r.group) for r in recs][:2]
          == [(names[0], 14.0, "WT"), (names[1], 14.0, "WT")], str(recs[:2]))
    ed.close()

    opened = SpreadsheetEditor(path=str(path))
    check("an existing sheet opens as it is, nothing suggested",
          list(opened.table().iloc[:, 2]) == ["WT", "WT", "KO", "KO"]
          and not opened.is_suggested(0, 2) and not opened.name_parts_note.text())
    opened.close()

    blank = SpreadsheetEditor()
    check("an empty sheet hides the name strip", not blank.name_parts_box.isVisibleTo(blank))
    blank.close()


# ── C. The simple view ───────────────────────────────────────────────────────

def simple_view_section(tmp: Path, shots: Path | None) -> None:
    print("C. Simple view offers to build one")
    from meanap.gui.main_window import MainWindow
    import meanap.gui.panels.spreadsheet_editor as editor_module

    raw = tmp / "raw"
    raw.mkdir()
    for name in ("SYN_WT_DIV14_A1", "SYN_KO_DIV14_A2", "SYN_WT_DIV21_A1"):
        (raw / f"{name}.mat").write_bytes(b"")
    w = MainWindow()
    w.resize(1100, 860)
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    w._data_panel.raw_data.line_edit.setText(str(raw))
    sv.evaluate()
    check("with recordings and no sheet, the step offers to build one from them",
          sv._sheet_button.text().startswith("Build one from the 3 recordings"),
          sv._sheet_button.text())
    if shots:
        app.processEvents()
        w.grab().save(str(shots / "simple_build_sheet.png"))

    seen = {}

    def fake_edit(parent, path="", *, table=None, suggested_path="", suggest=False):
        seen.update(table=table, suggest=suggest, suggested_path=suggested_path)
        return ""

    editor_module.edit_spreadsheet = fake_edit
    sv._sheet_button.click()
    check("clicking it opens the editor on those recordings, with suggestions",
          seen.get("suggest") is True and seen["table"] is not None
          and sorted(seen["table"].iloc[:, 0]) == sorted(
              ["SYN_WT_DIV14_A1", "SYN_KO_DIV14_A2", "SYN_WT_DIV21_A1"])
          and seen["suggested_path"] == str(raw / "recordings.csv"), str(seen))

    w._data_panel.spreadsheet.line_edit.setText(str(tmp / "batch.csv"))
    sv.evaluate()
    check("once a sheet is set it goes back to Create or edit",
          sv._sheet_button.text() == "Create or edit…", sv._sheet_button.text())
    w.close()


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    suggestion_section()
    with tempfile.TemporaryDirectory() as tmp:
        editor_section(Path(tmp), shots)
        simple_view_section(Path(tmp), shots)
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
