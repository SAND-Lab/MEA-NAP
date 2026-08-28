"""Test scanning a share link for recordings, and building a batch spreadsheet.

Run from the repo root::

    uv run python python/test_gui_spreadsheet_builder.py

No network: the remote half runs against a stub store that implements the same
three-method protocol :mod:`meanap.remote.base` defines, so the walk is
exercised without depending on Dropbox being up (or on it not having changed
its undocumented endpoints, which is what ``test_remote_dropbox.py`` is for).

What it checks:
  - the scanner finds the same recordings through a store as it does on disk,
    and marks the ones with no local path as remote rather than handing back a
    ``Path`` that stringifies to ``"None"``;
  - a URL routes to the Dropbox store instead of being stat-ed as a path — the
    bug this all started from, where a link scanned as "0 recordings found";
  - a spreadsheet built from a scan carries the exact folder names, DIVs read
    out of them, and blank groups (never guessed);
  - the editor round-trips a file, validates while editing, and saves what the
    pipeline's reader then reads back;
  - the scan can list only the recordings the batch spreadsheet names over its
    set range, and falls back to showing everything when there is no
    spreadsheet to filter against.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.scanner import (  # noqa: E402
    find_suite2p_recordings, scan_store,
)
from meanap.pipeline.spreadsheet import (  # noqa: E402
    fill_from_table, infer_div, match_recording_name, new_recording_table,
    read_recording_csv, read_recording_table, validate_recording_table,
    write_recording_table,
)
from meanap.remote.base import RemoteEntry  # noqa: E402

Check = tuple[str, bool, str]

LINK = ("https://www.dropbox.com/scl/fo/49tlfzlqtps5bx056jhb6/AM0tD"
        "?rlkey=udtwfveup1rmql07cslj2xhgj&dl=0")


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── A store with no local path, standing in for a share link ──────────────────

TREE = {
    "": [("slice1_DIV14", True), ("slice2_DIV21", True),
         ("notes", True), ("batch.csv", False)],
    "slice1_DIV14/suite2p/plane0": [
        ("stat.npy", False), ("F.npy", False), ("iscell.npy", False),
        ("ops.npy", False), ("Fdenoised.npy", False)],
    "slice2_DIV21/suite2p/plane0": [
        ("stat.npy", False), ("F.npy", False), ("iscell.npy", False),
        ("ops.npy", False)],
    # "notes" has no suite2p output at all — the listing comes back empty.
}


class StubStore:
    """The three operations :class:`~meanap.remote.base.RemoteStore` needs."""

    copies = True
    store_id = "stub"

    def __init__(self) -> None:
        self.listed: list[str] = []

    def list(self, path: str = "") -> list[RemoteEntry]:
        self.listed.append(path)
        prefix = f"{path.strip('/')}/" if path.strip("/") else ""
        return [RemoteEntry(path=f"{prefix}{name}", is_dir=is_dir,
                            size=None if is_dir else 10)
                for name, is_dir in TREE.get(path.strip("/"), [])]

    def stat(self, path: str):
        return None

    def fetch(self, path: str, dest: Path, progress=None) -> Path:
        raise AssertionError("a scan must not fetch anything")


def _make_local_dataset(root: Path) -> None:
    """Two suite2p recordings and one folder that isn't one."""
    for name, denoised in [("slice1_DIV14", True), ("slice2_DIV21", False)]:
        plane0 = root / name / "suite2p" / "plane0"
        plane0.mkdir(parents=True)
        for f in ("stat.npy", "F.npy", "iscell.npy", "ops.npy"):
            (plane0 / f).write_bytes(b"")
        if denoised:
            (plane0 / "Fdenoised.npy").write_bytes(b"")
    (root / "notes").mkdir()


# ── Scanner ───────────────────────────────────────────────────────────────────

def _scanner_checks() -> list[Check]:
    from meanap.remote import store_for
    from meanap.remote.dropbox_link import DropboxLinkStore
    from meanap.remote.local import LocalStore

    checks: list[Check] = []

    # Remote: found, named, and flagged as having nothing local to read.
    store = StubStore()
    seen: list[tuple[int, int]] = []
    remote = scan_store(store, progress=lambda d, t: seen.append((d, t)))
    checks.append(("a store's recordings are found by their suite2p output",
                   [r.name for r in remote] == ["slice1_DIV14", "slice2_DIV21"],
                   str([r.name for r in remote])))
    checks.append(("a folder with no suite2p output is not a recording",
                   all(r.name != "notes" for r in remote),
                   str([r.name for r in remote])))
    checks.append(("denoised output is reported per recording",
                   [r.has_denoised for r in remote] == [True, False],
                   str([r.has_denoised for r in remote])))
    checks.append(("recordings with no local path are marked remote",
                   all(r.is_remote and r.suite2p_dir is None for r in remote),
                   str([r.suite2p_dir for r in remote])))
    checks.append(("rel_path points at the store's plane0",
                   remote[0].rel_path == "slice1_DIV14/suite2p/plane0",
                   remote[0].rel_path))
    checks.append(("progress is reported to the end",
                   seen and seen[-1] == (3, 3), str(seen)))
    checks.append(("scanning transfers nothing (listings only)",
                   len(store.listed) == 4, str(store.listed)))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_local_dataset(root)

        local = find_suite2p_recordings(str(root))
        checks.append(("a local folder finds the same recordings",
                       [r.name for r in local] == ["slice1_DIV14", "slice2_DIV21"],
                       str([r.name for r in local])))
        checks.append(("local recordings keep a usable plane0 path",
                       all(not r.is_remote and r.suite2p_dir.is_dir() for r in local),
                       str([str(r.suite2p_dir) for r in local])))

        # The same walk through LocalStore must agree with the filesystem one —
        # two code paths that disagree would be worse than one that is slow.
        through_store = scan_store(LocalStore(root))
        checks.append(("scanning a LocalStore agrees with the direct walk",
                       [(r.name, r.suite2p_dir, r.has_denoised) for r in through_store]
                       == [(r.name, r.suite2p_dir, r.has_denoised) for r in local],
                       str([r.name for r in through_store])))

    checks.append(("a missing folder yields no recordings, not an error",
                   find_suite2p_recordings("/nonexistent/path/xyz") == [], ""))

    # The original bug: a URL was Path()-ed, was not a directory, and the scan
    # reported "0 recordings" as though the folder were empty.
    checks.append(("a share link routes to the Dropbox store, not the filesystem",
                   isinstance(store_for(LINK), DropboxLinkStore),
                   type(store_for(LINK)).__name__))
    checks.append(("a plain path still routes to the local store",
                   isinstance(store_for("/tmp"), LocalStore),
                   type(store_for("/tmp")).__name__))
    return checks


# ── Spreadsheet building ──────────────────────────────────────────────────────

def _spreadsheet_checks() -> list[Check]:
    checks: list[Check] = []

    checks.append(("DIV is read out of a recording name",
                   infer_div("OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21") == 21,
                   str(infer_div("OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"))))
    checks.append(("DIV separators are tolerated",
                   [infer_div("a_DIV_7"), infer_div("b div 14"), infer_div("c-DIV-21")]
                   == [7.0, 14.0, 21.0], ""))
    checks.append(("a name with no DIV gets no DIV",
                   infer_div("NGN2_20230208_P1_A2") is None, ""))
    checks.append(("a bare number is not mistaken for a DIV",
                   infer_div("plate_20230208_A2") is None, ""))

    names = ["slice1_DIV14", "slice2_DIV21", "slice3"]
    table = new_recording_table(names)
    checks.append(("names come through exactly as scanned",
                   list(table.iloc[:, 0]) == names, str(list(table.iloc[:, 0]))))
    checks.append(("DIVs are whole days, blank when the name doesn't say",
                   list(table.iloc[:, 1]) == ["14", "21", ""],
                   str(list(table.iloc[:, 1]))))
    checks.append(("the group column is left blank, never guessed",
                   list(table.iloc[:, 2]) == ["", "", ""],
                   str(list(table.iloc[:, 2]))))
    checks.append(("the Ground column is opt-in",
                   list(table.columns) == ["Recording Filename", "DIV group", "Genotype"]
                   and list(new_recording_table(names, ground=True).columns)[-1] == "Ground",
                   str(list(table.columns))))

    problems = validate_recording_table(table)
    checks.append(("a half-filled sheet reports its missing DIV and groups",
                   len(problems) == 2 and "DIV" in problems[0] and "genotype" in problems[1],
                   str(problems)))

    table.iloc[:, 1] = ["14", "21", "28"]
    table.iloc[:, 2] = ["WT", "WT", "KO"]
    checks.append(("a complete sheet has nothing to report",
                   validate_recording_table(table) == [],
                   str(validate_recording_table(table))))

    dupes = table.copy()
    dupes.iloc[2, 0] = "slice1_DIV14"
    checks.append(("a duplicated recording name is caught",
                   any("Duplicate" in p for p in validate_recording_table(dupes)),
                   str(validate_recording_table(dupes))))

    blank = table.copy()
    blank.iloc[1, 0] = ""
    checks.append(("a blank recording name is caught",
                   any("no recording name" in p for p in validate_recording_table(blank)),
                   str(validate_recording_table(blank))))

    # Filling from a master sheet whose names differ by a trailing word — the
    # shape of the real dataset this was built against, where 12 of 13 folders
    # carry a "… David Oluigbo" suffix the lab's spreadsheet doesn't.
    import pandas as pd
    master = pd.DataFrame({
        "Recording Filename": ["slice1_DIV14", "slice2_DIV21", "unrelated"],
        "DIV group": ["14", "21", "7"],
        "Genotype": ["WT", "KO", "WT"],
    }, dtype=str)
    scanned = new_recording_table(
        ["slice1_DIV14 David Oluigbo", "slice2_DIV21", "slice9_DIV30"])
    filled, matched = fill_from_table(scanned, master)

    checks.append(("a suffixed folder name still matches its row",
                   matched == 2, str(matched)))
    checks.append(("the scanned names are kept, not overwritten by the sheet's",
                   list(filled.iloc[:, 0]) == ["slice1_DIV14 David Oluigbo",
                                               "slice2_DIV21", "slice9_DIV30"],
                   str(list(filled.iloc[:, 0]))))
    checks.append(("DIV and group come from the sheet, including a binned DIV",
                   list(filled.iloc[:, 1]) == ["14", "21", "30"]
                   and list(filled.iloc[:, 2]) == ["WT", "KO", ""],
                   str(filled.to_dict("list"))))
    checks.append(("an unmatched recording keeps what the scan inferred",
                   filled.iloc[2, 1] == "30" and filled.iloc[2, 2] == "",
                   str(list(filled.iloc[2]))))
    checks.append(("a row in the sheet with no recording is ignored",
                   "unrelated" not in list(filled.iloc[:, 0]), ""))
    checks.append(("matching never pairs two different recordings",
                   match_recording_name("slice1_DIV14",
                                        ["slice1_DIV140", "slice1_DIV14x"]) is None,
                   str(match_recording_name("slice1_DIV14",
                                            ["slice1_DIV140", "slice1_DIV14x"]))))
    checks.append(("an exact match wins over a suffixed one",
                   match_recording_name("slice1", ["slice1 extra", "slice1"]) == "slice1",
                   str(match_recording_name("slice1", ["slice1 extra", "slice1"]))))

    # What is written must be what the pipeline's own reader reads back —
    # otherwise the editor is producing a file that only it understands.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "recordings.csv"
        write_recording_table(path, table)
        back = read_recording_table(path)
        checks.append(("a saved sheet round-trips through the editor's reader",
                       back.equals(table.reset_index(drop=True)),
                       f"{list(back.iloc[:, 1])} vs {list(table.iloc[:, 1])}"))

        infos = read_recording_csv(path, "A2:A100")
        checks.append(("the pipeline reader gets the rows it expects",
                       [(i.filename, i.div, i.group) for i in infos]
                       == [("slice1_DIV14", 14.0, "WT"), ("slice2_DIV21", 21.0, "WT"),
                           ("slice3", 28.0, "KO")],
                       str([(i.filename, i.div, i.group) for i in infos])))
    return checks


# ── Editor dialog ─────────────────────────────────────────────────────────────

def _editor_checks(app) -> list[Check]:
    from meanap.gui.panels.spreadsheet_editor import SpreadsheetEditor

    checks: list[Check] = []
    editor = SpreadsheetEditor()
    editor.set_recordings(["slice1_DIV14", "slice2_DIV21"])

    checks.append(("the editor shows a row per scanned recording",
                   editor._table.rowCount() == 2, str(editor._table.rowCount())))
    checks.append(("blanks to fill in are flagged before saving",
                   "⚠" in editor._status.text(), editor._status.text()))

    # Fill the group column the way the toolbar button does.
    for row in range(editor._table.rowCount()):
        editor._table.item(row, 2).setText("WT")
    checks.append(("filling the last blank column clears the warning",
                   "⚠" not in editor._status.text(), editor._status.text()))

    editor._on_add_row()
    checks.append(("an added row is empty and immediately flagged",
                   editor._table.rowCount() == 3 and "⚠" in editor._status.text(),
                   editor._status.text()))

    editor._table.setCurrentCell(2, 0)
    editor._on_remove_rows()
    checks.append(("removing the selected row leaves a valid sheet",
                   editor._table.rowCount() == 2 and "⚠" not in editor._status.text(),
                   editor._status.text()))

    editor.ground_check.setChecked(True)
    checks.append(("the Ground column can be added without losing edits",
                   list(editor.table().columns)[-1] == "Ground"
                   and list(editor.table().iloc[:, 0]) == ["slice1_DIV14", "slice2_DIV21"]
                   and list(editor.table().iloc[:, 2]) == ["WT", "WT"],
                   str(editor.table().to_dict("list"))))
    editor.ground_check.setChecked(False)
    checks.append(("and removed again",
                   list(editor.table().columns) == ["Recording Filename", "DIV group",
                                                    "Genotype"],
                   str(list(editor.table().columns))))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sheet.csv"
        emitted: list[str] = []
        editor.saved.connect(emitted.append)
        editor.save_to(path)
        checks.append(("saving emits the path so the Data tab can follow it",
                       emitted == [str(path)], str(emitted)))

        infos = read_recording_csv(path, "A2:A100")
        checks.append(("what the editor saved is what a run would read",
                       [(i.filename, i.div, i.group) for i in infos]
                       == [("slice1_DIV14", 14.0, "WT"), ("slice2_DIV21", 21.0, "WT")],
                       str([(i.filename, i.div, i.group) for i in infos])))

        reopened = SpreadsheetEditor(path=str(path))
        checks.append(("reopening a saved sheet shows what was saved",
                       reopened.table().equals(editor.table()),
                       str(reopened.table().to_dict("list"))))
    return checks


# ── The panel end to end ──────────────────────────────────────────────────────

def _filter_checks(app) -> list[Check]:
    """The scan listing only the recordings the batch spreadsheet names."""
    from PyQt6.QtCore import QSettings
    from meanap.gui.panels.catnap import CatNapPanel, _FILTER_PREF_KEY

    settings = QSettings("SAND Lab", "MEA-NAP")
    saved_pref = settings.value(_FILTER_PREF_KEY, False)

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_local_dataset(root)
        # A third folder the spreadsheet doesn't list, and one it lists under a
        # shorter name than the folder carries — the real dataset's shape.
        (root / "slice3_DIV28" / "suite2p" / "plane0").mkdir(parents=True)
        (root / "slice3_DIV28" / "suite2p" / "plane0" / "stat.npy").touch()

        sheet = root / "recordings.csv"
        sheet.write_text("Recording Filename,DIV group,Genotype\n"
                         "slice1_DIV14,14,WT\n"
                         "slice3_DIV28,28,KO\n"
                         "ghost_DIV7,7,WT\n")

        panel = CatNapPanel()
        panel.spreadsheet_source = lambda: (str(sheet), "A2:A100000")
        panel._folder_edit.setText(str(root))

        panel._sheet_filter.setChecked(False)
        panel._on_scan()
        panel._scan_worker.wait(10_000)
        app.processEvents()
        checks.append(("unfiltered, every suite2p folder is listed",
                       panel._recording_list.count() == 3,
                       str([r.name for r in panel._recordings])))

        panel._sheet_filter.setChecked(True)
        app.processEvents()
        listed = [r.name for r in panel._recordings]
        checks.append(("filtered, only the spreadsheet's recordings are listed",
                       listed == ["slice1_DIV14", "slice3_DIV28"], str(listed)))
        checks.append(("the list widget shows exactly those",
                       panel._recording_list.count() == 2,
                       str(panel._recording_list.count())))
        checks.append(("the log says how many were hidden",
                       "showing 2, hiding 1" in panel._log.toPlainText(),
                       panel._log.toPlainText()[-200:]))
        checks.append(("a spreadsheet row with no folder is called out",
                       "ghost_DIV7" in panel._log.toPlainText(),
                       panel._log.toPlainText()[-200:]))

        # The range is the *set* range, not the whole file.
        panel.spreadsheet_source = lambda: (str(sheet), "A2:A2")
        panel._apply_sheet_filter()
        checks.append(("the set range limits which rows count",
                       [r.name for r in panel._recordings] == ["slice1_DIV14"],
                       str([r.name for r in panel._recordings])))

        # A folder that gained a trailing word still matches its row.
        (root / "slice1_DIV14").rename(root / "slice1_DIV14 David Oluigbo")
        panel.spreadsheet_source = lambda: (str(sheet), "A2:A100000")
        panel._on_scan()
        panel._scan_worker.wait(10_000)
        app.processEvents()
        checks.append(("a suffixed folder name still matches its row",
                       [r.name for r in panel._recordings]
                       == ["slice1_DIV14 David Oluigbo", "slice3_DIV28"],
                       str([r.name for r in panel._recordings])))

        # Nothing to filter against must not empty the list — that would look
        # exactly like a scan that found nothing.
        panel.spreadsheet_source = lambda: ("", "A2:A100000")
        panel._apply_sheet_filter()
        checks.append(("no spreadsheet set shows everything, and says so",
                       panel._recording_list.count() == 3
                       and "No spreadsheet set" in panel._log.toPlainText(),
                       str(panel._recording_list.count())))

        panel.spreadsheet_source = lambda: (str(root / "nope.csv"), "A2:A100000")
        panel._apply_sheet_filter()
        checks.append(("an unreadable spreadsheet shows everything, and says so",
                       panel._recording_list.count() == 3
                       and "Can't read the spreadsheet" in panel._log.toPlainText(),
                       str(panel._recording_list.count())))

        panel.spreadsheet_source = lambda: (str(sheet), "not-a-range")
        panel._apply_sheet_filter()
        checks.append(("a malformed range shows everything rather than failing",
                       panel._recording_list.count() == 3, ""))

        # The choice is a view preference, remembered across sessions.
        checks.append(("the choice is remembered outside the run's params",
                       bool(settings.value(_FILTER_PREF_KEY)) is True,
                       str(settings.value(_FILTER_PREF_KEY))))

    settings.setValue(_FILTER_PREF_KEY, saved_pref)
    return checks


def _panel_checks(app) -> list[Check]:
    from meanap.catnap.scanner import Suite2pRecording
    from meanap.gui.panels.catnap import CatNapPanel

    checks: list[Check] = []
    panel = CatNapPanel()

    checks.append(("the spreadsheet button is off until something is found",
                   not panel._make_sheet_btn.isEnabled(), ""))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_local_dataset(root)
        panel._folder_edit.setText(str(root))
        panel._on_scan()
        panel._scan_worker.wait(10_000)
        app.processEvents()

        checks.append(("scanning a folder lists its recordings",
                       panel._recording_list.count() == 2,
                       str(panel._recording_list.count())))
        checks.append(("and enables the spreadsheet button",
                       panel._make_sheet_btn.isEnabled(), ""))

    # A remote result must not be loaded as a path, and must say why.
    panel._recordings = [Suite2pRecording(name="slice1_DIV14", suite2p_dir=None,
                                          has_denoised=False,
                                          rel_path="slice1_DIV14/suite2p/plane0")]
    panel._recording_list.clear()
    panel._recording_list.addItem("○  slice1_DIV14")
    panel._recording_list.setCurrentRow(0)
    app.processEvents()
    checks.append(("selecting a remote recording explains itself instead of failing",
                   "behind the share link" in panel._log.toPlainText()
                   and not panel._denoise_btn.isEnabled(),
                   panel._log.toPlainText()[-160:]))
    checks.append(("a remote recording is never loaded from a path",
                   panel._current_plane0 == "", panel._current_plane0))

    # The cell-type auto-detect walks recording folders; a remote one has none.
    panel._celltype_file.setText("")
    panel._load_markers()
    checks.append(("cell-type auto-detection skips remote recordings safely",
                   True, ""))

    # A bad link fails loudly rather than reporting an empty folder.
    panel._folder_edit.setText("https://www.dropbox.com/scl/fo/nope/hash?dl=0")
    panel._on_scan()
    panel._scan_worker.wait(10_000)
    app.processEvents()
    checks.append(("a malformed share link reports the reason, not '0 found'",
                   "Scan failed" in panel._log.toPlainText()
                   and "rlkey" in panel._log.toPlainText(),
                   panel._log.toPlainText()[-200:]))
    return checks


def main() -> int:
    print("=" * 70)
    print("Share-link scanning and spreadsheet building")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [("Scanner:", _scanner_checks),
                         ("Spreadsheet:", _spreadsheet_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        app = QApplication.instance() or QApplication([])
        for title, build in [("Spreadsheet editor:", _editor_checks),
                             ("CAT-NAP panel:", _panel_checks),
                             ("Spreadsheet filter:", _filter_checks)]:
            p, n = _report(title, build(app))
            total_pass += p
            total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
