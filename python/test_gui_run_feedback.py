"""Test what a running pipeline shows: moving times, the settings tick, the log.

Run from the repo root::

    uv run python python/test_gui_run_feedback.py

  A. RunClock: elapsed time counts up and time left counts down between
     progress reports, on a fake clock (no real waiting);
  B. the classic Run tab and the simple view keep their times moving;
  C. the simple view's Other settings card gets a tick once every question
     is answered;
  D. Show log opens the live status log in the simple view's panel.

Nothing here starts a pipeline or touches the person's own settings.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QObject, QSettings, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.main_window import MainWindow, save_simple_view_preference  # noqa: E402
from meanap.gui.modes import TAB_RUN  # noqa: E402
from meanap.gui.run_clock import RunClock, timing_text  # noqa: E402
from meanap.gui.simple_checks import Check  # noqa: E402
from meanap.pipeline.progress import Progress  # noqa: E402

FAILURES: list[str] = []
ERRORS: list[str] = []


def _excepthook(kind, value, tb) -> None:
    ERRORS.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


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


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def snapshot(elapsed: float, eta: float | None, detail: str = "rec_A1") -> Progress:
    return Progress(fraction=0.3, phase="Spike detection", detail=detail,
                    elapsed_s=elapsed, eta_s=eta)


class FakeWorker(QObject):
    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)


# ── A. The clock ──────────────────────────────────────────────────────────────

def clock_section() -> None:
    print("A. RunClock")
    now = FakeTime()
    clock = RunClock(now=now)
    clock.start()
    now.t += 7
    check("from the start, elapsed counts up with no report yet",
          round(clock.elapsed()) == 7 and clock.eta() is None, f"{clock.elapsed()}")
    check("and says it is estimating", clock.text() == "7s elapsed  ·  estimating time left…",
          clock.text())
    clock.report(60.0, 300.0)
    now.t += 5
    check("after a report, elapsed counts on from the report's figure",
          round(clock.elapsed()) == 65, f"{clock.elapsed()}")
    check("and time left counts down", round(clock.eta()) == 295, f"{clock.eta()}")
    check("as one line", clock.text() == "1m 05s elapsed  ·  about 4m 55s left", clock.text())
    now.t += 400
    check("an estimate that runs out says so, rather than sitting on 0s",
          clock.text().endswith("should be done shortly"), clock.text())
    clock.report(470.0, 30.0)
    check("a new report replaces the count", round(clock.elapsed()) == 470
          and round(clock.eta()) == 30)
    clock.stop()
    now.t += 100
    check("stopped, it stands still", round(clock.elapsed()) == 470 and not clock.running())
    check("the text both views use", timing_text(125, None)
          == "2m 05s elapsed  ·  estimating time left…")

    ticks = []
    real = RunClock()
    real.ticked.connect(lambda: ticks.append(1))
    real.start()
    pump(2300)
    real.stop()
    check("it ticks about once a second on its own", 3 <= len(ticks) <= 4, str(len(ticks)))


# ── B. Both views ─────────────────────────────────────────────────────────────

def views_section(window: MainWindow) -> None:
    print("\nB. The times keep moving")
    panel = window._run_panel
    now = FakeTime()
    panel.clock._now = now
    panel.start_progress()
    panel.show_progress(snapshot(10.0, 120.0))
    first = panel.progress_eta.text()
    now.t += 4
    panel.clock.ticked.emit()  # what the timer does each second
    check("Run tab: between reports, elapsed and time left move",
          first == "10s elapsed  ·  about 2m 00s left"
          and panel.progress_eta.text() == "14s elapsed  ·  about 1m 56s left",
          f"{first!r} → {panel.progress_eta.text()!r}")
    check("on a timer, not only when told", panel.clock.running())
    panel.show_queue_progress(0, 3, "first.json", snapshot(20.0, 60.0))
    now.t += 2
    panel.clock.ticked.emit()
    check("a queue's run keeps its 'in this run'",
          panel.progress_eta.text() == "22s elapsed  ·  about 58s left in this run",
          panel.progress_eta.text())
    now.t += 8
    panel.finish_progress("Finished.")
    check("finished: the total is up to the end, and the clock stops",
          panel.progress_eta.text() == "30s total" and not panel.clock.running(),
          panel.progress_eta.text())

    view = window._simple_view
    vnow = FakeTime()
    view.clock._now = vnow
    worker = FakeWorker()
    view.track_run(worker)
    worker.progress.emit(snapshot(30.0, 90.0, detail="well B2"))
    first = view.run_detail.text()
    vnow.t += 3
    view.clock.ticked.emit()
    check("simple view: the same, with the recording first",
          first == "well B2  ·  30s elapsed  ·  about 1m 30s left"
          and view.run_detail.text() == "well B2  ·  33s elapsed  ·  about 1m 27s left",
          f"{first!r} → {view.run_detail.text()!r}")
    check("the settings card can't be changed mid-run", not view.settings_card.isEnabled())
    worker.finished_ok.emit("")
    check("finished: its clock stops and the card is back",
          not view.clock.running() and view.settings_card.isEnabled())
    view._show_run_state("idle")


# ── C. The tick ───────────────────────────────────────────────────────────────

def tick_section(window: MainWindow) -> None:
    print("\nC. Other settings gets a tick")
    view = window._simple_view
    badge = view.settings_card.badge
    view.evaluate()
    check("while questions are open, the card shows its number",
          badge.text() == str(len(view._steps) + 1) and badge.property("state") != "ok",
          badge.text())
    real_checks = [step.check for step in view._steps]
    for step in view._steps:
        step.check = lambda: Check("ok", "", "fine")
    view.evaluate()
    check("once every question is answered, a green tick",
          badge.text() == "✓" and badge.property("state") == "ok", badge.text())
    window._spike_panel.thresholds.setText("3.0")
    view.refresh_settings()
    check("settings changed from the defaults keep it", badge.text() == "✓")
    window._spike_panel.thresholds.setText("4.0, 5.0")
    for step, real in zip(view._steps, real_checks):
        step.check = real
    view.evaluate()
    check("and it goes when a question is open again", badge.text() != "✓")


# ── D. The log ────────────────────────────────────────────────────────────────

def log_section(window: MainWindow) -> None:
    print("\nD. Show log, in the simple view")
    view = window._simple_view
    drawer = view.drawer
    panel = window._run_panel
    log_box = panel.log.parentWidget()
    view._show_run_state("running", "Running")
    view.log_button.click()
    pump(300)
    check("opens in the panel, on the same page",
          window.is_simple_view() and drawer.is_open() and drawer.section() is log_box
          and drawer.title_label.text() == "Status log"
          and drawer.note.text() == "Updates as the run goes.", drawer.title_label.text())
    check("filling the panel's height",
          log_box.height() > drawer.panel.height() * 0.6,
          f"{log_box.height()} of {drawer.panel.height()}")
    panel.append_log("Recording 3 of 12 done")
    check("and live: new lines appear while it is open",
          "Recording 3 of 12 done" in panel.log.toPlainText() and panel.log.isVisible())
    drawer.close_section()
    check("closing puts the log back on the Run tab", panel.isAncestorOf(log_box))
    view._show_run_state("idle")

    window._set_simple_view(False, remember=False)
    window._on_show_run_log()
    check("from the classic view it is the Run tab, as before",
          window._tabs.currentIndex() == window._tab_index(TAB_RUN))


# ── E. Run on ─────────────────────────────────────────────────────────────────

class FakeQueueWorker(QObject):
    progress = pyqtSignal(int, str, object)
    finished_all = pyqtSignal(str)
    failed = pyqtSignal(str)


def run_on_section(window: MainWindow, tmp: Path) -> None:
    print("\nE. Run on")
    from meanap.gui.main_window import _QueueFeed
    from meanap.gui.panels.run import QUEUE, SHARED, THIS_RUN

    view = window._simple_view
    panel = window._run_panel
    drawer = view.drawer
    window._set_simple_view(True, remember=False)
    real_checks = [step.check for step in view._steps]
    for step in view._steps:
        step.check = lambda: Check("ok", "", "fine")
    view.evaluate()
    pump(50)
    check("three choices, starting on this computer",
          [view.run_on.itemData(i) for i in range(view.run_on.count())]
          == [THIS_RUN, QUEUE, SHARED] and view.run_on.currentData() == THIS_RUN)
    check("which runs once, named for the pipeline",
          view.run_button.text() == "Run MEA-NAP" and view.run_button.isEnabled()
          and not view.run_on_setup.isVisible())

    view.run_on.setCurrentIndex(view.run_on.findData(QUEUE))
    pump(300)
    check("choosing a queue switches the Run tab too", panel.mode() == QUEUE)
    check("and opens the queue in the panel to set it up",
          drawer.is_open() and drawer.section() is panel.queue
          and drawer.title_label.text() == "Queue of saved runs")
    check("an empty queue has nothing to run",
          view.run_button.text() == "Run queue" and not view.run_button.isEnabled(),
          f"{view.run_button.text()!r} {view.run_button.isEnabled()}")
    saved = tmp / "saved.json"
    saved.write_text("{}")
    panel.queue.add_paths([saved])
    panel.refresh()
    check("with a run in it, Run says how many and can start",
          view.run_button.text() == "Run queue (1)" and view.run_button.isEnabled(),
          view.run_button.text())
    drawer.close_section()
    stack = panel._stack
    check("closing puts the queue page back in its place",
          stack.indexOf(panel.queue) == 1 and stack.currentWidget() is panel.queue)
    check("and 'Set up…' reopens it", view.run_on_setup.isVisible())

    started = []
    window._on_run_queue = lambda: started.append(QUEUE)
    view.run_button.click()
    check("Run starts the queue, not a single run", started == [QUEUE])

    panel.shared_radio.setChecked(True)
    pump(30)
    label, enabled, _tip = panel.shared.run_button_state()
    check("switching on the Run tab moves this choice too",
          view.run_on.currentData() == SHARED
          and view.run_button.text() == label.replace("▶", "").strip()
          and view.run_button.isEnabled() == enabled, view.run_button.text())
    view.open_run_setup()
    pump(250)
    check("the shared page opens in the panel", drawer.section() is panel.shared)
    drawer.close_section()
    check("and goes back", stack.indexOf(panel.shared) == 2)

    view.run_on.setCurrentIndex(view.run_on.findData(THIS_RUN))
    pump(30)
    check("back on this computer", panel.mode() == THIS_RUN
          and view.run_button.text() == "Run MEA-NAP" and not drawer.is_open())

    worker = FakeQueueWorker()
    view.track_run(_QueueFeed(worker, 3))
    worker.progress.emit(1, "second.json", snapshot(5.0, 50.0, detail="well A2"))
    check("a queue's progress is the whole queue's",
          view.progress.value() == 433  # (1 run done + 0.3 of the second) of 3
          and view.run_headline.text() == "43%  ·  Run 2 of 3  ·  Spike detection"
          and view.run_detail.text().startswith("second.json  ·  well A2"),
          f"{view.progress.value()} {view.run_headline.text()!r} {view.run_detail.text()!r}")
    check("the choice can't change mid-run", not view.run_on.isEnabled())
    worker.finished_all.emit("3 runs: 3 finished")
    check("it ends with the queue's summary, and no single folder to open",
          view._run_state == "done" and view.run_detail.text() == "3 runs: 3 finished"
          and not view.results_button.isVisible() and not view.folder_button.isVisible(),
          view.run_detail.text())
    view._show_run_state("idle")
    for step, real in zip(view._steps, real_checks):
        step.check = real
    view.evaluate()


def main() -> int:
    sys.excepthook = _excepthook
    clock_section()
    save_simple_view_preference(False)
    window = MainWindow()
    sys.excepthook = _excepthook
    if window._tutorial is not None:
        window._tutorial.hide()
    window._set_simple_view(True, remember=False)
    window.resize(1200, 800)
    window.show()
    pump(100)
    views_section(window)
    tick_section(window)
    log_section(window)
    with tempfile.TemporaryDirectory() as tmp:
        run_on_section(window, Path(tmp))
    window.close()
    pump(50)
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
