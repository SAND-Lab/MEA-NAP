"""Test the simple view: its checks, its step-by-step flow, and the toggle.

Run from the repo root::

    uv run python python/test_gui_simple_view.py

The simple view asks one question at a time and shows a tick when an answer
checks out. These checks hold four things in place:

  A. the checks behind the ticks, on folders and spreadsheets built here;
  B. the simple view is the default, and the choice is remembered;
  C. the flow: each answer folds once it checks out, the settings it writes
     are the ones a run reads, and switching pipeline rebuilds the questions
     without leaving stale connections behind;
  D. a run's progress and its end are shown on the page.

GUI settings go to a temporary folder, so running this never touches the
person's own preferences.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QToolBar  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.main_window import MainWindow, SIMPLE_VIEW_KEY  # noqa: E402
from meanap.gui.simple_checks import (  # noqa: E402
    check_output_folder, check_recordings_folder, check_spreadsheet,
)
from meanap.gui.simple_view import TICK_HOLD_MS, _pick_folder  # noqa: E402
from meanap.pipeline.progress import Progress  # noqa: E402

FAILURES: list[str] = []
ERRORS: list[str] = []
sys.excepthook = lambda *exc: ERRORS.append(f"{exc[0].__name__}: {exc[1]}")


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


def make_data(root: Path) -> dict[str, Path]:
    raw = root / "raw"
    raw.mkdir()
    for name in ("rec_DIV14_A", "rec_DIV14_B", "rec_DIV21_A"):
        (raw / f"{name}.mat").write_bytes(b"")
    sheets = {
        "good": "Recording,DIV,Group\nrec_DIV14_A,14,WT\nrec_DIV14_B,14,KO\nrec_DIV21_A,21,WT\n",
        "partial": "Recording,DIV,Group\nrec_DIV14_A,14,WT\nrec_DIV99_Z,99,KO\n",
        "none": "Recording,DIV,Group\nother_1,14,WT\nother_2,14,KO\n",
        "no_group": "Recording,DIV,Group\nrec_DIV14_A,14,\nrec_DIV14_B,14,KO\n",
        "bad_div": "Recording,DIV,Group\nrec_DIV14_A,fourteen,WT\n",
        "empty": "Recording,DIV,Group\n",
    }
    paths = {"raw": raw, "empty_dir": root / "empty"}
    (root / "empty").mkdir()
    for key, text in sheets.items():
        path = root / f"{key}.csv"
        path.write_text(text)
        paths[key] = path
    suite2p = root / "s2p"
    for name in ("cultureA", "cultureB"):
        plane = suite2p / name / "suite2p" / "plane0"
        plane.mkdir(parents=True)
        (plane / "stat.npy").write_bytes(b"")
    paths["suite2p"] = suite2p
    return paths


# ── A. Checks ────────────────────────────────────────────────────────────────

def checks_section(d: dict[str, Path]) -> None:
    print("A. The checks behind the ticks")
    check("empty folder field says nothing", check_recordings_folder("", "meanap") is None)
    c = check_recordings_folder(str(d["raw"]), "meanap")
    check("recordings folder: ok, counts the files",
          c.state == "ok" and "3 recording files" in c.message, repr(c))
    c = check_recordings_folder(str(d["raw"] / "missing"), "meanap")
    check("missing folder is an error", c.state == "error", repr(c))
    c = check_recordings_folder(str(d["empty_dir"]), "meanap")
    check("folder with no recordings is an error", c.state == "error", repr(c))
    c = check_recordings_folder("https://www.dropbox.com/scl/fo/abc/xyz?dl=0", "meanap")
    check("Dropbox link accepted without a network check", c.state == "ok", repr(c))
    c = check_recordings_folder(str(d["suite2p"]), "catnap")
    check("suite2p folder: ok in CAT-NAP", c.state == "ok" and "2 suite2p" in c.message, repr(c))
    c = check_recordings_folder(str(d["raw"]), "catnap")
    check("ephys folder is an error in CAT-NAP", c.state == "error", repr(c))

    def sheet(key):
        return check_spreadsheet(str(d[key]), str(d["raw"]), "meanap")

    c = sheet("good")
    check("matching spreadsheet: ok", c.state == "ok" and c.summary == "3 recordings", repr(c))
    c = sheet("partial")
    check("some recordings missing: warning naming the first",
          c.state == "warn" and "rec_DIV99_Z" in c.message, repr(c))
    check("no recordings found: error", sheet("none").state == "error")
    c = sheet("no_group")
    check("blank group: warning, still usable", c.state == "warn" and c.complete, repr(c))
    check("non-numeric DIV: error", sheet("bad_div").state == "error")
    check("no rows: error", sheet("empty").state == "error")
    c = check_spreadsheet(str(d["raw"] / "nope.csv"), str(d["raw"]), "meanap")
    check("missing spreadsheet: error", c.state == "error", repr(c))
    c = check_spreadsheet(str(d["good"]), "", "meanap")
    check("no recordings folder yet: spreadsheet checked on its own", c.state == "ok", repr(c))

    c = check_output_folder(str(d["empty_dir"]))
    check("existing output folder: ok", c.state == "ok", repr(c))
    c = check_output_folder(str(d["empty_dir"] / "new_results"))
    check("new output folder inside an existing one: ok", c.state == "ok", repr(c))
    c = check_output_folder(str(d["empty_dir"] / "a" / "b"))
    check("output folder two levels deep in nothing: error", c.state == "error", repr(c))


# ── B. The toggle ────────────────────────────────────────────────────────────

def toggle_section() -> None:
    print("B. Simple by default, choice remembered")
    settings = QSettings("SAND Lab", "MEA-NAP")
    settings.setValue("tutorial/seen", True)
    settings.remove(SIMPLE_VIEW_KEY)
    w = MainWindow()
    check("the simple view opens by default", w.is_simple_view())
    toolbars = w.findChildren(QToolBar)
    check("with no toolbar", not any(tb.isVisibleTo(w) for tb in toolbars))
    check("and nothing saved until someone chooses", settings.value(SIMPLE_VIEW_KEY) is None)
    w._simple_view.classic_requested.emit()
    check("Classic view switches to the tabs", not w.is_simple_view())
    check("and shows the toolbar", all(tb.isVisibleTo(w) for tb in toolbars))
    w.close()
    w2 = MainWindow()
    check("someone who chose the classic view keeps it", not w2.is_simple_view())
    w2._set_simple_view(True)
    w2.close()
    check("and switching back is remembered too", MainWindow().is_simple_view())

    # A first launch in the classic view still offers the tutorial (it walks
    # the tabs); in the simple view it waits, since there is nothing to point at.
    settings.remove("tutorial/seen")
    w4 = MainWindow()
    check("the tutorial does not open over the simple view",
          w4._tutorial is None or not w4._tutorial.isVisible())
    w4.close()
    settings.setValue("tutorial/seen", True)

    # MEA-Sim from the pipeline menu under the logo. QMenu.exec is swapped for
    # a stand-in that records the menu and returns, so nothing blocks.
    from PyQt6.QtWidgets import QMenu
    w3 = MainWindow()
    w3._set_simple_view(True)
    shown: list[QMenu] = []
    real_exec = QMenu.exec
    QMenu.exec = lambda self, *a, **k: shown.append(self)
    try:
        w3._simple_view.mode_caption.click()
    finally:
        QMenu.exec = real_exec
    actions = [a for a in shown[0].actions() if a.text().startswith("MEA-Sim")] if shown else []
    check("the pipeline menu offers MEA-Sim, apart from the pipelines",
          len(actions) == 1 and not actions[0].isCheckable(), str([a.text() for a in
                                                                   shown[0].actions()] if shown else shown))
    if actions:
        actions[0].trigger()
    sim = getattr(w3, "_sim_window", None)
    check("choosing it opens the MEA-Sim window", sim is not None and sim.isVisible())
    hits = [e for e in w3._search_entries() if e.title == "Open MEA-Sim"]
    check("searching 'simulate' finds it", bool(hits))
    if sim is not None:
        sim.close()
    w3._set_simple_view(False)
    w3.close()


# ── C. The flow ──────────────────────────────────────────────────────────────

def flow_section(d: dict[str, Path], shots: Path | None) -> None:
    print("C. One question at a time")
    w = MainWindow()
    w.resize(1100, 820)
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    pump(100)

    def states():
        return [s.card.state for s in sv._steps]

    check("starts on the recordings folder alone", states()[0] == "active"
          and all(s == "hidden" for s in states()[1:]), str(states()))
    check("Run is not offered yet", not sv.run_area.isVisible())
    check("nor Other settings", not sv.settings_card.isVisible())
    check("and no Simulate button in the top bar: MEA-Sim is on the pipeline menu",
          not hasattr(sv, "simulate_button"))

    folder = sv._steps[0].card.body.edit
    folder.setText(str(d["raw"] / "missing"))
    pump(500)
    check("a wrong folder keeps the question open with an error",
          states()[0] == "active" and sv._steps[0].card.status.property("state") == "error",
          str(states()))

    folder.setText(str(d["raw"]))
    pump(450)  # past the debounce, inside the tick's hold
    card = sv._steps[0].card
    check("tick shown on the field before it folds",
          card.badge.text() == "✓" and card._details.isVisible(),
          f"{card.badge.text()!r} {card._details.isVisible()}")
    if shots:
        w.grab().save(str(shots / "simple_tick.png"))
    pump(TICK_HOLD_MS + 500)
    check("then it folds to a summary and the next question opens",
          states()[:2] == ["done", "active"] and not card._details.isVisible()
          and card.summary.text() == "3 recording files", str(states()))
    check("the folder is written to the Data tab",
          w._data_panel.raw_data.value == str(d["raw"]))

    sv._steps[1].card.body.edit.setText(str(d["partial"]))
    pump(1300)
    check("a spreadsheet with a warning still moves on, flagged",
          states()[1] == "done" and sv._steps[1].card.badge.text() == "!", str(states()))
    sv._steps[1].card.reopen_requested.emit()
    pump(100)
    check("clicking a done question reopens it", states()[1] == "active", str(states()))
    sv._steps[1].card.body.edit.setText(str(d["good"]))
    pump(1300)
    check("a changed answer that checks out closes it again",
          states()[1] == "done" and sv._steps[1].card.badge.text() == "✓", str(states()))

    check("recording settings wait for Continue", states()[2] == "active", str(states()))
    sv._confirm_current()
    pump(1300)
    out = d["empty_dir"] / "results"
    sv._steps[3].card.body.edit.setText(str(out))
    pump(1300)
    check("all answered: every question folded and Run offered",
          states() == ["done"] * 4 and sv.run_area.isVisible() and sv.run_button.isEnabled(),
          str(states()))
    check("and Other settings with it", sv.settings_card.isVisible())
    if shots:
        w.grab().save(str(shots / "simple_ready.png"))

    sv._steps[2].card.reopen_requested.emit()
    pump(600)
    check("looking back at an answered question hides nothing after it",
          states() == ["done", "done", "active", "done"] and sv.run_area.isVisible()
          and sv.run_button.isEnabled(), str(states()))
    sv._confirm_current()
    pump(1300)
    check("and Continue folds it again", states() == ["done"] * 4, str(states()))

    sv._steps[0].card.reopen_requested.emit()
    pump(600)
    check("the first question too: the rest stay folded",
          states() == ["active", "done", "done", "done"] and sv.run_area.isVisible(),
          str(states()))
    folder.setText(str(d["raw"] / "missing"))
    pump(500)
    check("but an answer that stops checking out hides what follows it",
          states() == ["active", "hidden", "hidden", "hidden"]
          and not sv.run_area.isVisible(), str(states()))
    folder.setText(str(d["raw"]))
    pump(TICK_HOLD_MS + 1300)
    check("and putting it right brings them back, the question still open",
          states() == ["active", "done", "done", "done"] and sv.run_area.isVisible(),
          str(states()))
    sv._confirm_current()
    pump(1300)
    check("until it is confirmed", states() == ["done"] * 4, str(states()))

    params = w._collect_params()
    check("a run reads the answers given here",
          params.raw_data == str(d["raw"]) and params.spreadsheet_file_name == str(d["good"])
          and params.output_data_folder == str(out),
          f"{params.raw_data} {params.spreadsheet_file_name} {params.output_data_folder}")

    w._data_panel.channel_layout.setCurrentText("Axion16")
    pump(500)
    check("a change on the Data tab reaches the simple view",
          "Axion16" in sv._steps[2].card.summary.text(), sv._steps[2].card.summary.text())

    for mode in ("catnap", "meastim", "meanap", "catnap"):
        w._on_mode_requested(mode)
        pump(200)
    check("CAT-NAP asks for suite2p recordings and an activity measure",
          [s.key for s in sv._steps] == ["recordings", "spreadsheet", "activity", "output"],
          str([s.key for s in sv._steps]))
    check("the ephys folder is rejected in CAT-NAP", states()[0] == "active", str(states()))
    w._data_panel.raw_data.set_value(str(d["suite2p"]))
    w._data_panel.output_data_folder.set_value(str(d["empty_dir"]))
    pump(1500)
    check("after several pipeline switches, edits still flow without errors", not ERRORS,
          "; ".join(ERRORS[:3]))
    w._on_mode_requested("meastim")
    pump(200)
    check("MEA-Stim adds a stimulation question",
          "stimulation" in [s.key for s in sv._steps], str([s.key for s in sv._steps]))
    w.close()


# ── D. The run ───────────────────────────────────────────────────────────────

class _FakeWorker(QObject):
    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)


def run_section(shots: Path | None) -> None:
    print("D. Progress and the end of a run")
    w = MainWindow()
    w.resize(1100, 820)
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    worker = _FakeWorker()
    sv.track_run(worker)
    worker.progress.emit(Progress(fraction=0.42, phase="Spike detection",
                                  detail="rec_DIV14_A", elapsed_s=75.0, eta_s=110.0))
    pump(100)
    check("progress shown with phase, recording and time left",
          sv.progress.isVisible() and sv.progress.value() == 420
          and "Spike detection" in sv.run_headline.text()
          and "rec_DIV14_A" in sv.run_detail.text() and "left" in sv.run_detail.text(),
          f"{sv.run_headline.text()} | {sv.run_detail.text()}")
    check("Stop offered while running", sv.stop_button.isVisible())
    if shots:
        w.grab().save(str(shots / "simple_running.png"))
    worker.finished_ok.emit(Path(_SETTINGS_DIR))
    pump(100)
    check("finished: View results and Open folder offered",
          sv.results_button.isVisible() and sv.folder_button.isVisible()
          and not sv.progress.isVisible())
    worker2 = _FakeWorker()
    sv.track_run(worker2)
    worker2.failed.emit("Traceback ...\nValueError: bad file")
    pump(100)
    check("failed: says so, gives the last line, offers the log and Run again",
          "failed" in sv.run_headline.text() and "bad file" in sv.run_detail.text()
          and sv.log_button.isVisible() and sv.run_button.isVisible())
    w.close()


# ── E. The version under the logo ────────────────────────────────────────────

def version_section(shots: Path | None) -> None:
    print("E. Version, and whether it is current, under the logo")
    from meanap import updates
    from meanap.version import pipeline_version

    w = MainWindow()
    w.resize(1100, 820)
    w.show()
    w._set_simple_view(True)
    pump(50)
    sv = w._simple_view
    button = sv.version_button
    own = f"v{pipeline_version(w._mode)}"
    check("the running version shows under the logo",
          button.isVisible() and button.text() == own, button.text())
    check("it sits below the pipeline's name",
          button.geometry().top() >= sv.mode_caption.geometry().bottom(), "")
    check("plain while nothing newer is known", button.property("state") == "", "")

    w._on_mode_requested("catnap")
    pump(50)
    check("switching pipeline shows that pipeline's version",
          button.text() == f"v{pipeline_version('catnap')}", button.text())
    w._on_mode_requested("meanap")
    pump(50)

    w._on_update_status(updates.AppStatus(running="v1.0.0", latest_release="v99.0.0"))
    pump(50)
    check("an out-of-date copy says which version is newer",
          button.text() == f"{own}  ·  v99.0.0 available ⬆", button.text())
    check("and is highlighted, since it asks for a click",
          button.property("state") == "update", str(button.property("state")))
    check("the whole line fits",
          button.width() >= button.fontMetrics().horizontalAdvance(button.text()),
          f"{button.width()} < text")
    check("its tooltip says what the check found", "v99.0.0" in button.toolTip(),
          button.toolTip())
    if shots:
        w.grab().save(str(shots / "simple_update_available.png"))

    check("the main window listens for it",
          sv.receivers(sv.versions_requested) >= 1, "")
    # The dialog itself would ask GitHub, so only the request is checked here.
    sv.versions_requested.disconnect()
    asked: list[bool] = []
    sv.versions_requested.connect(lambda: asked.append(True))
    button.click()
    check("clicking it asks for the versions dialog", asked == [True], str(asked))

    w._on_update_status(updates.AppStatus(running="v99.0.0", latest_release="v99.0.0"))
    pump(50)
    check("an up-to-date copy goes back to the plain version",
          button.text() == own and button.property("state") == "", button.text())
    hits = [e for e in w._search_entries() if e.title == "Versions and updates"]
    check("searching finds it under the logo, without leaving the simple view",
          hits and hits[0].target is button, str(hits[:1]))
    w.close()


# ── C2. Choosing the recordings folder ──────────────────────────────────────

def picker_section(d: dict[str, Path]) -> None:
    print("C2. Choosing the recordings folder")
    seen: dict[str, object] = {}

    def answer(select: str | None) -> None:
        dialog = next(w for w in QApplication.topLevelWidgets()
                      if isinstance(w, QFileDialog) and w.isVisible())
        seen["native"] = dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        seen["dirs_only"] = dialog.testOption(QFileDialog.Option.ShowDirsOnly)
        seen["filters"] = dialog.nameFilters()
        if select:
            dialog.selectFile(select)
        dialog.accept()

    def pick(select: str | None) -> str:
        QTimer.singleShot(300, lambda: answer(select))
        return _pick_folder(None, "Select folder", str(d["raw"]),
                            "Recordings (*.mat *.h5 *.raw)")

    chosen = pick(None)
    check("it is Qt's own dialog, showing files as well as folders",
          seen.get("native") is True and seen.get("dirs_only") is False, str(seen))
    check("the recordings filter first, all files a choice away",
          seen.get("filters") == ["Recordings (*.mat *.h5 *.raw)", "All files (*)"],
          str(seen.get("filters")))
    check("accepting returns the folder it is in", Path(chosen) == d["raw"], chosen)
    chosen = pick(str(d["raw"] / "rec_DIV14_A.mat"))
    check("a recording picked by mistake stands for its folder",
          Path(chosen) == d["raw"], chosen)

    w = MainWindow()
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    pump(100)
    check("Other settings wait for the questions", not sv.settings_card.isVisible())
    sv.open_section(sv.settings_card.areas()[0].key, 0)
    pump(100)
    check("but a setting looked up early shows them", sv.settings_card.isVisible())
    sv.evaluate()
    check("and they stay shown", sv.settings_card.isVisible())
    w.close()


def example_section() -> None:
    print("F. Try it on the example data")
    from meanap.gui import main_window as mw

    example = Path(__file__).resolve().parents[1] / "ExampleData"
    fetched: list = []
    real = mw.download_example_data
    mw.download_example_data = lambda dest, log=None: fetched.append(dest) or example
    try:
        w = MainWindow()
        w._set_simple_view(True)
        w._data_panel.output_data_folder.set_value("")
        w._data_panel.raw_data.set_value("")
        w._data_panel.spreadsheet.set_value("")
        sv = w._simple_view
        pump(100)
        link = getattr(sv, "_example_link", None)
        check("MEA-NAP's first question offers the example data",
              link is not None and link.text() == "Or try it on the example data")
        check("its tooltip says how big the download is", "1.8 GB" in link.toolTip())
        started: list = []
        real_run = w._on_run
        w._on_run = lambda: started.append(True)
        link.click()
        pump(1500)
        check("it is fetched into a results folder of its own",
              fetched and str(fetched[0]).endswith("MEA-NAP"), str(fetched))
        check("and fills in the recordings and the spreadsheet",
              w._data_panel.raw_data.value == str(example)
              and w._data_panel.spreadsheet.value.endswith("exampleData.csv"))
        check("without starting a run: Run is the person's to press", not started)
        w._on_run = real_run
        w._on_mode_requested("catnap")
        pump(200)
        check("CAT-NAP has no example data link",
              not any(b.text() == "Or try it on the example data"
                      for b in sv._steps[0].card.findChildren(type(link))))
        w.close()
    finally:
        mw.download_example_data = real


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        data = make_data(Path(tmp))
        checks_section(data)
        toggle_section()
        flow_section(data, shots)
        picker_section(data)
        run_section(shots)
        version_section(shots)
        example_section()
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
