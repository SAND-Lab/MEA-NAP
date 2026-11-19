"""Test the simple view's **Continue a run** page, and what it hands the pipeline.

Run from the repo root::

    uv run python python/test_gui_simple_continue.py

  A. reading a run back: from its folder and from an express run's .meanap,
     and the errors for folders that are not a run;
  B. the spreadsheet copy (``<name>_continued.csv``), the plan the page shows,
     and the settings each answer turns into;
  C. those settings, run for real: removing a recording deletes its figures
     and matches a fresh run of the rest; re-running a later step writes into
     the run, also when only its bundle is left;
  D. the page itself: the questions, the run's settings loaded, removing,
     adding through the spreadsheet editor, re-running, and Run starting a run
     with the right settings.

The runs are step 4 only, on seeded spike times and adjacency (the fixture of
test_continue_interrupted.py), so this takes well under a minute.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.pipeline.continuation import (  # noqa: E402
    continued_sheet_path, plan_lines, read_run, run_overrides, write_continued_sheet,
)
from meanap.pipeline.output_folders import create_output_folders  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402
from test_continue_interrupted import (  # noqa: E402
    _seed_step4_inputs_for, _step4_params,
)

FAILURES: list[str] = []
ERRORS: list[str] = []
sys.excepthook = lambda *exc: ERRORS.append(f"{exc[0].__name__}: {exc[1]}")
SIX = [f"rec{i}" for i in range(6)]


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def pump(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def sheet(path: Path, recs) -> Path:
    pd.DataFrame([{"Recording Filename": r, "DIV group": 21,
                   "Genotype": "WT" if int(r[3:]) % 2 else "KO"}
                  for r in recs]).to_csv(path, index=False)
    return path


def make_run(tmp: Path, name: str, recs, seed=None, **kw) -> Path:
    """A finished step-4 run of *recs*, with data seeded for *seed* (default: recs)."""
    root = create_output_folders(tmp, name, ["WT", "KO"])
    _seed_step4_inputs_for(root, seed or recs)
    p = _step4_params(tmp, name, spreadsheet_file_name=str(sheet(tmp / f"{name}.csv", recs)),
                      **kw)
    return run_pipeline(p, log=lambda m: None)


def table(root: Path) -> pd.DataFrame:
    df = pd.read_csv(root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
    return df.sort_values(df.columns[0]).reset_index(drop=True)


def figures_of(root: Path, rec: str) -> int:
    base = root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
    return len(list(base.rglob(f"*/{rec}/**/*.png")))


# ── A. Reading a run back ────────────────────────────────────────────────────

def reading_section(tmp: Path) -> None:
    print("A. Reading a run back")
    root = make_run(tmp, "Run", SIX[:5])
    run = read_run(root)
    check("a run folder is read back", run.name == "Run" and run.parent == tmp, str(run))
    check("with its recordings, all finished",
          run.recordings == SIX[:5] and run.finished >= set(SIX[:5]), str(run.finished))
    check("its pipeline and version",
          run.mode == "meanap" and run.version.startswith("v"), f"{run.mode} {run.version}")
    check("and a summary for the folded card",
          run.describe().startswith("Run · 5 recordings"), run.describe())
    check("the run is where it is now, whatever params.json says",
          run.params.output_data_folder == str(tmp)
          and run.params.output_data_folder_name == "Run")

    for path, words in ((tmp, "holds several runs"), (tmp / "nope", "doesn't exist"),
                        (root / "ExperimentMatFiles", "no params.json")):
        try:
            read_run(path)
            got = ""
        except ValueError as exc:
            got = str(exc)
        check(f"not a run: says so ({words})", words in got, got)

    old = tmp / "OldRun"
    (old / "4_NetworkActivity").mkdir(parents=True)
    try:
        read_run(old)
        got = ""
    except ValueError as exc:
        got = str(exc)
    check("a MATLAB or pre-params.json run says why, and what to use instead",
          "made by MATLAB" in got and "Continue previous run" in got, got)

    express = make_run(tmp, "Express", SIX[:3], express_mode=True)
    check("an express run leaves only its bundle", express.suffix == ".meanap"
          and not (tmp / "Express").is_dir(), str(express))
    run = read_run(express)
    check("and its bundle is read back too",
          run.bundle_only and run.name == "Express" and run.finished >= set(SIX[:3]),
          f"{run.bundle_only} {run.finished}")


# ── B. Spreadsheet copy, plan, settings ──────────────────────────────────────

def planning_section(tmp: Path) -> None:
    print("B. The spreadsheet copy, the plan, the settings")
    run = read_run(tmp / "Run")
    base = Path(run.sheet)
    before = base.read_text()
    copy = write_continued_sheet(base, keep={"rec0", "rec1", "rec3", "rec4"})
    check("the copy is <name>_continued.csv beside the original",
          copy == base.with_name("Run_continued.csv"), str(copy))
    check("without the removed row", list(pd.read_csv(copy).iloc[:, 0])
          == ["rec0", "rec1", "rec3", "rec4"])
    check("and the original is untouched", base.read_text() == before)
    check("continuing a continued run reuses the copy rather than stacking names",
          continued_sheet_path(copy) == copy, str(continued_sheet_path(copy)))

    kept = ["rec0", "rec1", "rec3", "rec4"]
    lines = plan_lines(run, kept, "remove", prune=True)
    check("the plan for removing says what is kept and what goes",
          any("4 recordings kept" in ln for ln in lines)
          and any("1 recording left out (their figures are deleted" in ln for ln in lines)
          and any("redone over 4 recordings" in ln for ln in lines), str(lines))
    lines = plan_lines(run, SIX, "add")
    check("for adding, the new one is the one to analyse",
          any("1 recording to analyse (1 new)" in ln for ln in lines), str(lines))
    lines = plan_lines(run, SIX[:5], "rerun", from_step=4)
    check("for a re-run, which steps are redone and which are read",
          lines[0].startswith("Step 4 (network activity) is redone for all 5") and "read from the run" in lines[1], str(lines))

    o = run_overrides(run, "remove", prune=True, sheet_names=kept)
    check("removing: continue in place, figures pruned",
          o["continue_interrupted"] and o["prune_removed_recordings"]
          and o["output_data_folder_name"] == "Run", str(o))
    check("starting where the run did, since every recording is done",
          o.get("start_analysis_step", run.params.start_analysis_step) == 4, str(o))
    o = run_overrides(run, "remove", prune=False, sheet_names=kept)
    check("unless told to keep the figures", not o["prune_removed_recordings"])
    o = run_overrides(run, "finish", prune=True)
    check("finishing never prunes", not o["prune_removed_recordings"])
    o = run_overrides(run, "add", sheet_names=SIX)
    check("adding a recording with no spikes starts at step 1",
          o["start_analysis_step"] == 1, str(o))
    run.detected.add("rec5")
    o = run_overrides(run, "add", sheet_names=SIX)
    check("one with spikes but no adjacency at step 2", o["start_analysis_step"] == 2, str(o))
    run.detected.discard("rec5")
    o = run_overrides(run, "rerun", from_step=3)
    check("re-running: from that step, into the run, nothing skipped",
          o["start_analysis_step"] == 3 and not o["continue_interrupted"]
          and o["overwrite_existing_output"] and o["output_data_folder_name"] == "Run",
          str(o))


# ── C. Run for real ──────────────────────────────────────────────────────────

def running_section(tmp: Path) -> None:
    print("C. The settings, run")
    run = read_run(tmp / "Run")
    kept = ["rec0", "rec1", "rec3", "rec4"]
    copy = write_continued_sheet(run.sheet, keep=set(kept))
    check("before: rec2 has figures", figures_of(tmp / "Run", "rec2") > 0)
    params = replace(run.params, spreadsheet_file_name=str(copy),
                     **run_overrides(run, "remove", prune=True, sheet_names=kept))
    out = run_pipeline(params, log=lambda m: None)
    check("removing writes into the same run", out == tmp / "Run", str(out))
    check("its figures are gone", figures_of(out, "rec2") == 0, str(figures_of(out, "rec2")))
    check("its data is kept", (out / "ExperimentMatFiles" / "rec2_adjM.npz").exists())
    ref = make_run(tmp, "Ref", kept)
    check("and the results match a fresh run of what is left",
          table(out).equals(table(ref)), "CSVs differ")
    check("params.json now names the copy, for the next continue",
          read_run(out).sheet == str(copy), read_run(out).sheet)

    run = read_run(tmp / "Run")
    params = replace(run.params, **run_overrides(run, "rerun", from_step=4))
    params.network_metrics_density_threshold = getattr(
        params, "network_metrics_density_threshold", None)
    logs: list[str] = []
    out = run_pipeline(params, log=logs.append)
    check("re-running from step 4 writes into the run, not a _v2",
          out == tmp / "Run" and not (tmp / "Run_v2").exists(), str(out))
    check("and redoes every recording", len(table(out)) == 4, str(len(table(out))))

    bundle = tmp / "Express.meanap"
    run = read_run(bundle)
    params = replace(run.params, **run_overrides(run, "rerun", from_step=4))
    logs = []
    out = run_pipeline(params, log=logs.append)
    check("re-running an express run's step 4 works from its bundle",
          out.name.startswith("Express") and not any("SKIP" in m for m in logs),
          "; ".join(m for m in logs if "SKIP" in m or "Cannot" in m)[:300])


# ── D. The page ──────────────────────────────────────────────────────────────

def page_section(tmp: Path) -> None:
    print("D. The Continue a run page")
    from meanap.gui import main_window as mw
    from meanap.gui.panels import spreadsheet_editor

    root = make_run(tmp, "PageRun", SIX[:5], seed=SIX)
    # rec5 has spike times but no adjacency: adding it starts at step 2.
    (root / "ExperimentMatFiles" / "rec5_adjM.npz").unlink()
    w = mw.MainWindow()
    w.resize(1100, 900)
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    w._data_panel.output_data_folder_name.setText("")
    pump(100)

    def keys():
        return [s.key for s in sv._steps]

    def states():
        return [s.card.state for s in sv._steps]

    sv.show_page("continue")
    pump(100)
    check("a third page, Continue a run", sv.page() == "continue"
          and sv._page_buttons["continue"].isChecked())
    check("it asks for the run first", keys()[:2] == ["run", "action"]
          and states()[0] == "active", f"{keys()} {states()}")
    check("Run on is hidden: one run, on this computer", not sv.run_on_row.isVisibleTo(sv))

    # The two Browse buttons: a folder dialog can't return a .meanap (it hands
    # back the folder it is in), so the file has a button of its own.
    from PyQt6.QtWidgets import QFileDialog, QPushButton
    import meanap.gui.simple_view as simple_view_module
    buttons = {b.text(): b for b in sv._steps[0].card.body.findChildren(QPushButton)}
    check("Browse offers a folder and a .meanap", {"Folder…", ".meanap…"} <= set(buttons),
          str(list(buttons)))
    real_open, real_pick = QFileDialog.getOpenFileName, simple_view_module._pick_folder
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **k: (str(tmp / "Express.meanap"), ""))
    simple_view_module._pick_folder = lambda *a, **k: str(root)
    try:
        buttons[".meanap…"].click()
        pump(50)
        picked_bundle = sv._steps[0].card.body.edit.text()
        buttons["Folder…"].click()
        pump(50)
        picked_folder = sv._steps[0].card.body.edit.text()
    finally:
        QFileDialog.getOpenFileName, simple_view_module._pick_folder = real_open, real_pick
    check(".meanap… puts the file itself in the field",
          picked_bundle == str(tmp / "Express.meanap"), picked_bundle)
    check("Folder… puts the folder", picked_folder == str(root), picked_folder)
    sv._steps[0].card.body.edit.setText(str(root))
    pump(TICK_HOLD_MS_PLUS)
    check("picking the run loads its settings",
          w._data_panel.spreadsheet.value == str(tmp / "PageRun.csv")
          and w._data_panel.output_data_folder_name.text() == "PageRun",
          f"{w._data_panel.spreadsheet.value} {w._data_panel.output_data_folder_name.text()}")
    check("its card folds to the run's summary",
          states()[:2] == ["done", "active"]
          and sv._steps[0].card.summary.text().startswith("PageRun · 5 recordings"),
          f"{states()} {sv._steps[0].card.summary.text()}")

    # Remove
    flow = sv.continue_flow
    flow._radios["remove"].setChecked(True)
    pump(100)
    check("an answer waits for Continue", states()[1] == "active", str(states()))
    flow._confirm_action()
    pump(TICK_HOLD_MS_PLUS)
    check("removing adds a question for which", keys()[-1] == "changes", str(keys()))
    check("the recordings aren't needed: every one has spikes",
          sv._steps[2].card.summary.text() == "Not needed", sv._steps[2].card.summary.text())
    check("and the spreadsheet is the run's",
          sv._steps[3].card.state == "done", str(states()))
    # Recordings that aren't raw files in that folder (spikes imported from a
    # sorter, files in sub-folders, a disk not mounted): a removal reads none
    # of them, so the spreadsheet is not checked against the folder.
    w._data_panel.raw_data.set_value(str(tmp / "raw" / "elsewhere"))
    pump(TICK_HOLD_MS_PLUS)
    check("removing doesn't need the spreadsheet's recordings in the folder",
          sv._steps[3].card.state == "done" and sv._steps[3].card.check.state == "ok",
          f"{states()} {sv._steps[3].card.check}")
    listing = flow._remove_list
    check("which lists the run's recordings, all ticked",
          listing.count() == 5 and all(listing.item(i).checkState() == Qt.CheckState.Checked
                                       for i in range(5)))
    check("and deleting their figures is on", flow._prune_box.isChecked())
    flow.apply_removal()
    pump(200)
    check("Continue with nothing unticked says what to do",
          sv._steps[-1].card.check is not None
          and "Untick" in sv._steps[-1].card.check.message)
    listing.item(2).setCheckState(Qt.CheckState.Unchecked)
    flow.apply_removal()
    pump(TICK_HOLD_MS_PLUS)
    check("unticking one writes the copy and uses it",
          w._data_panel.spreadsheet.value == str(tmp / "PageRun_continued.csv"),
          w._data_panel.spreadsheet.value)
    check("then every question is answered and Run offered",
          all(s == "done" for s in states()) and sv.run_button.isEnabled(), str(states()))
    plan = sv.plan_label.text()
    check("with what the run will do",
          sv.plan_label.isVisible() and "4 recordings kept" in plan and "left out" in plan,
          plan)
    check("Run names the run", sv.run_button.text() == "Continue PageRun",
          sv.run_button.text())

    started: list = []

    class FakeWorker(mw.PipelineWorker):
        def start(self):  # noqa: D102
            started.append(self._params if hasattr(self, "_params") else self.params)

    real = mw.PipelineWorker
    mw.PipelineWorker = FakeWorker
    try:
        sv.run_button.click()
        pump(100)
    finally:
        mw.PipelineWorker = real
    p = started[0] if started else None
    check("Run starts a run that continues this one, pruning",
          p is not None and p.continue_interrupted and p.prune_removed_recordings
          and p.output_data_folder_name == "PageRun"
          and p.spreadsheet_file_name.endswith("PageRun_continued.csv"), str(p and (
              p.continue_interrupted, p.prune_removed_recordings,
              p.output_data_folder_name)))
    check("without asking about the folder being taken", not ERRORS, "; ".join(ERRORS))
    check("and none of it is left in the window's settings",
          not w._collect_params().continue_interrupted)
    sv._on_ended("cancelled", "Run stopped.")
    sv._show_run_state("idle")

    # Add, through the spreadsheet editor
    sv._reopen(1)
    pump(100)
    flow._radios["add"].setChecked(True)
    flow._confirm_action()
    w._data_panel.raw_data.set_value(str(tmp / "raw"))
    pump(TICK_HOLD_MS_PLUS)
    w._data_panel.spreadsheet.set_value(str(tmp / "PageRun.csv"))
    pump(TICK_HOLD_MS_PLUS)
    check("adding needs the recordings folder", sv._steps[2].card.state == "done"
          and sv._steps[2].card.summary.text() != "Not needed",
          f"{states()} {sv._steps[2].card.summary.text()}")
    check("and names the ones the run doesn't have",
          "rec5" in flow._add_label.text(), flow._add_label.text())
    seen: dict = {}

    def fake_editor(parent, path="", *, table=None, suggested_path="", suggest=False):
        seen.update(table=table, suggested=suggested_path)
        table = table.copy()
        table.iloc[-1, 1] = "21"   # what the person fills in
        table.iloc[-1, 2] = "WT"
        table.to_csv(suggested_path, index=False)
        return suggested_path

    real_editor = spreadsheet_editor.edit_spreadsheet
    spreadsheet_editor.edit_spreadsheet = fake_editor
    try:
        flow.open_add_editor()
    finally:
        spreadsheet_editor.edit_spreadsheet = real_editor
    pump(TICK_HOLD_MS_PLUS)
    check("the editor opens on the run's rows plus the new one",
          seen and list(seen["table"].iloc[:, 0]) == SIX, str(seen.get("table")))
    check("suggesting the _continued.csv copy",
          seen.get("suggested") == str(tmp / "PageRun_continued.csv"), str(seen))
    check("saving it answers the question",
          sv._steps[-1].card.summary.text() == "1 added (6 in all)",
          sv._steps[-1].card.summary.text())
    o = sv.run_overrides()
    check("and the run starts at step 2: rec5 has spikes but no adjacency",
          o and o["continue_interrupted"] and o["start_analysis_step"] == 2
          and not o["prune_removed_recordings"], str(o))

    # Re-run
    sv._reopen(1)
    pump(100)
    flow._radios["rerun"].setChecked(True)
    flow._step_combo.setCurrentIndex(flow._step_combo.findData(3))
    flow._confirm_action()
    pump(TICK_HOLD_MS_PLUS)
    check("re-running asks nothing more", "changes" not in keys(), str(keys()))
    check("and goes back to the run's own spreadsheet, not the copy",
          w._data_panel.spreadsheet.value == str(tmp / "PageRun.csv"),
          w._data_panel.spreadsheet.value)
    check("and doesn't need the recordings",
          sv._steps[2].card.summary.text() in ("Not needed", "3 recording files")
          or sv._steps[2].card.state == "done", sv._steps[2].card.summary.text())
    o = sv.run_overrides()
    check("it runs from step 3 into the run",
          o and o["start_analysis_step"] == 3 and not o["continue_interrupted"]
          and o["output_data_folder_name"] == "PageRun", str(o))
    check("Run says so", sv.run_button.text() == "Re-run PageRun from step 3",
          sv.run_button.text())

    # Leaving
    sv.show_page("analyse")
    pump(200)
    check("back on Analyse recordings, a new analysis's questions",
          [s.key for s in sv._steps][0] == "recordings" and sv.run_overrides() is None)
    check("and the run name is put back, so the next run isn't written into it",
          w._data_panel.output_data_folder_name.text() == "",
          w._data_panel.output_data_folder_name.text())
    check("Run on is back", not sv.run_on_row.isHidden())
    hits = [e for e in sv.search_entries() if e.title == "Continue a run"]
    check("search finds the page", bool(hits))
    sv.show_page("continue")
    pump(200)
    check("and coming back finds the run still picked",
          sv._steps[0].card.body.edit.text() == str(root))
    check("no errors along the way", not ERRORS, "; ".join(ERRORS[:3]))
    w.close()


TICK_HOLD_MS_PLUS = 1400


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "raw").mkdir()
        for name in SIX:
            (tmp / "raw" / f"{name}.mat").write_bytes(b"")
        reading_section(tmp)
        planning_section(tmp)
        running_section(tmp)
        page_section(tmp)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
