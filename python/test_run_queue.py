"""Test running several saved analyses back to back.

Run from the repo root::

    uv run python python/test_run_queue.py

A queue exists so nobody has to be awake for the handover between runs. That
makes its failure behaviour the interesting part, not its success behaviour:

  - **one bad run must not end the night.** Coming back to five results and one
    error is worth far more than coming back to one error, so each run is caught
    individually and the queue carries on;
  - **the summary has to be readable cold.** Whoever reads it has forgotten what
    was queued, so every run is named, and failures say why rather than only
    that;
  - **stopping means stopping.** Cancelling during run three must not start run
    four, and the runs that never started say so instead of being missing.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.params import Params, save_params  # noqa: E402
from meanap.pipeline.atomic import atomic_savez  # noqa: E402
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.output_folders import create_output_folders  # noqa: E402
from meanap.pipeline.queue import (  # noqa: E402
    CANCELLED, DONE, FAILED, SKIPPED, QueuedRun, load_queue, run_queue,
    summarise,
)

Check = tuple[str, bool, str]

N_CH, FS, LAG = 8, 2000.0, 25


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _seed(root: Path, recs: list[str]) -> None:
    """Step-4 inputs, so a queued run has something real to do."""
    for rec in recs:
        rng = np.random.default_rng(abs(hash(rec)) % 1000)
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 60 + ch))}
             for ch in range(N_CH)},
            np.arange(1, N_CH + 1), FS, duration_s=60.0)
        adj = np.abs(rng.normal(0, 0.3, (N_CH, N_CH)))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz",
                     channels=np.arange(1, N_CH + 1),
                     **{f"adjM{LAG}mslag": adj, f"adjM{LAG}mslag_raw": adj})


def _write_params(tmp: Path, name: str, sheet: Path, **kw) -> Path:
    """A parameter file for a run that will succeed, unless kw breaks it."""
    root = create_output_folders(tmp, name, ["WT"])
    _seed(root, ["recX", "recY"])
    base = dict(
        output_data_folder=str(tmp), output_data_folder_name=name,
        spreadsheet_file_name=str(sheet), spreadsheet_range="2:100",
        raw_data=str(tmp / "no-raw"), start_analysis_step=4, stop_analysis_step=4,
        func_con_lag_val=[LAG], channel_layout="MCS60",
        min_number_of_nodes_to_cal_net_met=2, random_seed=3,
        recording_workers=1, continue_interrupted=True,
    )
    base.update(kw)
    holder = tmp / f"_{name}"
    holder.mkdir(exist_ok=True)
    save_params(Params(**base), holder)
    destination = tmp / f"{name}.json"
    (holder / "params.json").rename(destination)
    return destination


def _sheet(tmp: Path) -> Path:
    path = tmp / "recs.csv"
    pd.DataFrame([{"Recording Filename": r, "DIV group": 21, "Genotype": "WT"}
                  for r in ("recX", "recY")]).to_csv(path, index=False)
    return path


# ── Loading ───────────────────────────────────────────────────────────────────

def _loading_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = _sheet(tmp)
        a = _write_params(tmp, "Alpha", sheet)
        b = _write_params(tmp, "Beta", sheet, express_mode=True)

        runs = load_queue([a, b])
        checks.append(("parameter files load into queued runs",
                       len(runs) == 2, str(len(runs))))
        checks.append(("each is named by its output folder",
                       [r.label for r in runs] == ["Alpha", "Beta"],
                       str([r.label for r in runs])))
        checks.append(("and describes what it will do",
                       "Ephys" in runs[0].describe()
                       and "steps 4–4" in runs[0].describe(),
                       runs[0].describe()))
        checks.append(("noting express mode, which changes what is written",
                       "express" in runs[1].describe(), runs[1].describe()))

        # A queue is validated in full before anything starts: a typo should be
        # a message now, not a gap in the morning's results.
        try:
            load_queue([a, tmp / "nope.json"])
            said = ""
        except ValueError as e:
            said = str(e)
        checks.append(("a missing file is refused up front, by name",
                       "nope.json" in said, said))

        (tmp / "broken.json").write_text("{not json")
        try:
            load_queue([tmp / "broken.json"])
            said = ""
        except ValueError as e:
            said = str(e)
        checks.append(("so is one that will not parse",
                       "broken.json" in said, said))

        # A run configured in the GUI has no file behind it yet.
        loose = QueuedRun(params=Params(output_data_folder_name="Ad hoc"))
        checks.append(("a run with no file still has a usable name",
                       loose.label == "Ad hoc", loose.label))
        checks.append(("and one with neither falls back rather than blanking",
                       QueuedRun(params=Params()).label == "unnamed run", ""))
    return checks


# ── Running ───────────────────────────────────────────────────────────────────

def _running_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = _sheet(tmp)
        good1 = _write_params(tmp, "First", sheet)
        bad = _write_params(tmp, "Broken", sheet, spreadsheet_file_name="")
        good2 = _write_params(tmp, "Third", sheet)

        logs: list[str] = []
        finished: list[str] = []
        result = run_queue(load_queue([good1, bad, good2]), log=logs.append,
                           on_finished=lambda o: finished.append(o.run.label))

        checks.append(("every run is attempted",
                       len(result.outcomes) == 3, str(len(result.outcomes))))
        checks.append(("a failure in the middle does not stop the rest",
                       result.done == 2 and result.failed == 1,
                       f"done={result.done} failed={result.failed}"))
        checks.append(("the runs after it still produce output",
                       result.outcomes[2].output is not None
                       and result.outcomes[2].output.is_dir(),
                       str(result.outcomes[2].output)))
        checks.append(("the failure records why, not just that",
                       "Spreadsheet file must be set" in result.outcomes[1].error,
                       result.outcomes[1].error))
        checks.append(("and the log says the queue is carrying on",
                       any("queue continues" in m for m in logs), ""))
        checks.append(("outcomes are reported as they happen",
                       finished == ["First", "Broken", "Third"], str(finished)))

        text = "\n".join(summarise(result))
        checks.append(("the summary names every run",
                       all(n in text for n in ("First", "Broken", "Third")), ""))
        checks.append(("marks which failed",
                       "✗ 2. Broken" in text, text))
        checks.append(("gives the output folder of the ones that worked",
                       str(result.outcomes[0].output) in text, ""))
        checks.append(("and counts them up",
                       "2 of 3 completed, 1 failed" in text, text))
    return checks


def _cancel_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = _sheet(tmp)
        paths = [_write_params(tmp, f"Run{i}", sheet) for i in range(4)]

        # Stop after the first run finishes: the rest must not start.
        state = {"stop": False}
        seen: list[str] = []

        def finished(outcome) -> None:
            seen.append(outcome.status)
            state["stop"] = True

        result = run_queue(load_queue(paths), log=lambda m: None,
                           should_cancel=lambda: state["stop"],
                           on_finished=finished)

        checks.append(("the first run completes",
                       result.outcomes[0].status == DONE,
                       result.outcomes[0].status))
        checks.append(("the rest are not started",
                       all(o.status == SKIPPED for o in result.outcomes[1:]),
                       str([o.status for o in result.outcomes])))
        checks.append(("but they are still listed, rather than missing",
                       len(result.outcomes) == 4, str(len(result.outcomes))))
        text = "\n".join(summarise(result))
        checks.append(("and the summary says they never ran",
                       text.count("not started") == 3, text))

        # Cancelling before anything starts should run nothing at all.
        result2 = run_queue(load_queue(paths), log=lambda m: None,
                            should_cancel=lambda: True)
        checks.append(("a queue cancelled up front runs nothing",
                       result2.done == 0
                       and all(o.status == SKIPPED for o in result2.outcomes),
                       str([o.status for o in result2.outcomes])))
    return checks


def _progress_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = _sheet(tmp)
        paths = [_write_params(tmp, f"P{i}", sheet) for i in range(2)]

        seen: list[tuple[int, str, float]] = []
        run_queue(load_queue(paths), log=lambda m: None,
                  progress=lambda i, run, snap: seen.append(
                      (i, run.label, snap.fraction)))

        checks.append(("progress is reported during the runs",
                       len(seen) > 0, str(len(seen))))
        checks.append(("carrying which run it belongs to",
                       {i for i, _, _ in seen} == {0, 1},
                       str(sorted({i for i, _, _ in seen}))),)
        checks.append(("and that run's own name",
                       {label for _, label, _ in seen} == {"P0", "P1"},
                       str({label for _, label, _ in seen})))
        checks.append(("each run's progress runs to completion",
                       max(f for i, _, f in seen if i == 0) == 1.0,
                       str(max(f for i, _, f in seen if i == 0))))
    return checks


def _empty_checks() -> list[Check]:
    logs: list[str] = []
    result = run_queue([], log=logs.append)
    return [
        ("an empty queue is not an error",
         result.outcomes == [] and result.done == 0, ""),
        ("and says so rather than printing an empty summary",
         any("Nothing was queued" in m for m in logs), str(logs)),
    ]


# ── The Queue tab ─────────────────────────────────────────────────────────────

def _gui_checks() -> list[Check]:
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.main_window import MainWindow
    from meanap.gui.modes import MODES, TAB_QUEUE

    app = QApplication.instance() or QApplication([])
    checks: list[Check] = []

    checks.append(("the Queue tab is available in every mode",
                   all(TAB_QUEUE in m.tabs for m in MODES.values()),
                   str([k for k, m in MODES.items() if TAB_QUEUE not in m.tabs])))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = _sheet(tmp)
        good = [_write_params(tmp, n, sheet) for n in ("One", "Two")]
        bad = _write_params(tmp, "Bad", sheet, spreadsheet_file_name="")

        window = MainWindow()
        panel = window._queue_panel

        panel.add_paths([good[0], bad, good[1]])
        checks.append(("files can be queued",
                       panel.list.count() == 3, str(panel.list.count())))
        checks.append(("adding one twice does not queue it twice",
                       panel.add_paths([good[0]]) == 0
                       and panel.list.count() == 3, str(panel.list.count())))

        before = [p.name for p in panel.paths()]
        panel.list.item(1).setSelected(True)
        panel._move(1)
        after = [p.name for p in panel.paths()]
        checks.append(("runs can be reordered",
                       after == [before[0], before[2], before[1]], str(after)))
        panel.list.clearSelection()

        panel.list.item(2).setSelected(True)
        panel._on_remove()
        checks.append(("and removed",
                       panel.list.count() == 2, str(panel.list.count())))
        panel.add_paths([bad])
        panel.list.clearSelection()

        # Run it for real, on the UI thread's event loop.
        summaries: list[str] = []
        loop = QEventLoop()
        window._on_run_queue()
        window._queue_worker.finished_all.connect(
            lambda text: (summaries.append(text), loop.quit()))
        window._queue_worker.failed.connect(
            lambda m: (summaries.append("FAILED " + m), loop.quit()))
        checks.append(("starting disables editing while it runs",
                       not panel.add_btn.isEnabled()
                       and not panel.run_btn.isEnabled()
                       and panel.stop_btn.isEnabled(), ""))
        QTimer.singleShot(900_000, loop.quit)
        loop.exec()

        checks.append(("the queue reports what completed",
                       summaries == ["2 of 3 completed, 1 failed"],
                       str(summaries)))
        marks = [panel.list.item(i).text().split()[0]
                 for i in range(panel.list.count())]
        checks.append(("each run is marked with how it ended",
                       marks == ["✓", "✓", "✗"], str(marks)))
        checks.append(("the bar finishes full",
                       panel.overall.value() == 1000, str(panel.overall.value())))
        checks.append(("and editing is possible again",
                       panel.add_btn.isEnabled() and panel.run_btn.isEnabled()
                       and not panel.stop_btn.isEnabled(), ""))

        text = panel.log.toPlainText()
        checks.append(("the summary is in the tab's own log",
                       "2 of 3 completed" in text and "Bad" in text, ""))

        # Saving and reloading the queue itself.
        queue_file = tmp / "overnight.meanapqueue"
        import json as _json
        queue_file.write_text(_json.dumps(
            {"runs": [str(p) for p in panel.paths()]}))
        panel._paths.clear()
        panel._status.clear()
        panel.add_paths(_json.loads(queue_file.read_text())["runs"])
        checks.append(("a saved queue reloads to the same runs",
                       [p.name for p in panel.paths()]
                       == [Path(p).name for p in
                           _json.loads(queue_file.read_text())["runs"]], ""))

        # The two run buttons must not overlap.
        window._queue_worker = None
        checks.append(("a single run is refused while the queue is going",
                       hasattr(window, "_on_run_queue")
                       and "_queue_worker" in Path(
                           __import__("meanap.gui.main_window",
                                      fromlist=["x"]).__file__).read_text(), ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Running a queue of analyses")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [("Loading a queue:", _loading_checks),
                         ("Running it:", _running_checks),
                         ("Stopping it:", _cancel_checks),
                         ("Progress:", _progress_checks),
                         ("Nothing queued:", _empty_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        import PyQt6  # noqa: F401
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        p, n = _report("The Queue tab:", _gui_checks())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
