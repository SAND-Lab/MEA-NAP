"""What the verbose level does, now that it does anything.

Run from the repo root::

    uv run python python/test_verbose_level.py

``Params.verbose_level`` was stored, saved to ``params.json`` and never read:
the GUI offered three levels and every run printed the same thing. It now
selects between three *additive* levels — Verbose adds to Normal, Debug adds to
both — implemented by :mod:`meanap.pipeline.verbosity`.

Three claims are worth holding in place, and the third is the one that matters:

  - **additive** — every line a quieter level prints, a louder one prints too.
    A level that could hide a line would make a Debug log unsafe to reason
    from, and a Normal log unsafe to run with;
  - **it reaches the workers** — steps 3 and 4 compute in separate processes
    that buffer their own log lines. The level travels in ``Params``, so the
    check is that a Verbose run actually shows a line only a worker can write;
  - **it changes nothing else** — the numbers a run produces are identical at
    every level. That is what the GUI tooltip promises, and it is the reason
    someone can turn Debug on to diagnose a run without invalidating it.
"""

from __future__ import annotations

import json
import os
import sys
import re
import tempfile
import time
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.params import Params  # noqa: E402
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.output_folders import create_output_folders  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402
from meanap.pipeline.verbosity import (  # noqa: E402
    VERBOSE_LEVELS, RunLog, as_run_log, format_elapsed, normalise_level,
)

Check = tuple[str, bool, str]

N_REC, N_CH, FS, LAG = 3, 8, 2000.0, 25
RECS = [f"rec{i}" for i in range(N_REC)]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


# ── The log itself ────────────────────────────────────────────────────────────

def _runlog_checks() -> list[Check]:
    checks: list[Check] = []

    checks.append(("the levels are Normal, Verbose, Debug",
                   VERBOSE_LEVELS == ["Normal", "Verbose", "Debug"],
                   str(VERBOSE_LEVELS)))

    # A params file is user-editable and can come from the MATLAB pipeline, so
    # nothing here may raise — an unreadable level logs normally.
    cases = {
        "Normal": "Normal", "verbose": "Verbose", "DEBUG": "Debug",
        "High": "Verbose",              # MATLAB's name for the middle level
        "Silent": "Normal",             # no quieter level exists here
        "": "Normal", None: "Normal", "gibberish": "Normal", 7: "Normal",
    }
    bad = {k: normalise_level(k) for k, want in cases.items()
           if normalise_level(k) != want}
    checks.append(("every stored level resolves to a real one", not bad, str(bad)))

    said: dict[str, list[str]] = {}
    for level in VERBOSE_LEVELS:
        lines: list[str] = []
        log = RunLog(lines.append, level)
        log("always")
        log.detail("detail")
        log.debug("debug")
        said[level] = lines

    checks.append(("Normal prints only the always-lines",
                   said["Normal"] == ["always"], str(said["Normal"])))
    checks.append(("Verbose adds the detail channel",
                   said["Verbose"] == ["always", "detail"], str(said["Verbose"])))
    checks.append(("Debug adds the debug channel on top",
                   said["Debug"] == ["always", "detail", "debug"],
                   str(said["Debug"])))
    checks.append(("so each level is a superset of the one below",
                   set(said["Normal"]) < set(said["Verbose"]) < set(said["Debug"]),
                   ""))

    quiet = RunLog(lambda m: None, "Normal")
    loud = RunLog(lambda m: None, "Debug")
    checks.append(("wants_detail/wants_debug agree with the channels",
                   (not quiet.wants_detail, not quiet.wants_debug,
                    loud.wants_detail, loud.wants_debug) == (True, True, True, True),
                   ""))

    # Timing: silent below its level, one line at or above it.
    for level, want in (("Normal", 0), ("Verbose", 1)):
        lines = []
        with RunLog(lines.append, level).timed("  work"):
            pass
        checks.append((f"timed() says {want} thing(s) at {level}",
                       len(lines) == want, str(lines)))
    checks.append(("and names what it timed", "work took" in lines[0], str(lines)))

    checks.append(("elapsed keeps sub-second precision",
                   (format_elapsed(0.4), format_elapsed(75)) == ("0.40s", "1m 15s"),
                   f"{format_elapsed(0.4)} / {format_elapsed(75)}"))

    # A worker promotes its own line buffer; a nested call must not re-level a
    # log the run already built, or the two would drift apart.
    lines = []
    promoted = as_run_log(lines.append, "Debug")
    checks.append(("a plain callable is promoted", isinstance(promoted, RunLog)
                   and promoted.level == "Debug", promoted.level))
    checks.append(("an existing RunLog is left alone",
                   as_run_log(promoted, "Normal") is promoted
                   and promoted.level == "Debug", promoted.level))
    return checks


# ── A whole run, at each level ────────────────────────────────────────────────

def _seed(root: Path) -> None:
    """Spike times and adjacency: what steps 2-4 read."""
    from meanap.pipeline.atomic import atomic_savez

    for i, rec in enumerate(RECS):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 60 + 3 * ch))}
                  for ch in range(N_CH)}
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            spikes, np.arange(1, N_CH + 1), FS, duration_s=60.0)
        adj = np.abs(rng.normal(0, 0.3, (N_CH, N_CH)))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz",
                     channels=np.arange(1, N_CH + 1),
                     **{f"adjM{LAG}mslag": adj, f"adjM{LAG}mslag_raw": adj})


def _params(tmp: Path, name: str, level: str) -> Params:
    return Params(
        output_data_folder=str(tmp), output_data_folder_name=name,
        spreadsheet_file_name=str(tmp / "recs.csv"), spreadsheet_range="2:100",
        raw_data=str(tmp / "no-raw"),
        start_analysis_step=4, stop_analysis_step=4,
        func_con_lag_val=[LAG], channel_layout="MCS60",
        min_number_of_nodes_to_cal_net_met=2, random_seed=5,
        recording_workers=1, express_mode=True, verbose_level=level,
    )


def _run_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pd.DataFrame([{"Recording Filename": r, "DIV group": 21, "Genotype": "WT"}
                      for r in RECS]).to_csv(tmp / "recs.csv", index=False)

        said: dict[str, list[str]] = {}
        results: dict[str, str] = {}
        for level in VERBOSE_LEVELS:
            root = create_output_folders(tmp, level, ["WT"])
            _seed(root)
            lines: list[str] = []
            started = time.perf_counter()
            out = run_pipeline(_params(tmp, level, level), log=lines.append)
            said[level] = lines
            print(f"    ({level}: {len(lines)} lines in "
                  f"{time.perf_counter() - started:.1f}s)")
            # Express mode, so the three runs cost a second rather than a
            # minute of drawing figures nothing here looks at. It folds the
            # output into a bundle, and the metrics travel inside it.
            with zipfile.ZipFile(out) as bundle:
                results[level] = json.dumps(
                    json.loads(bundle.read("4_NetworkActivity/netmet_results.json")),
                    sort_keys=True)

        # The claim the tooltip makes.
        checks.append(("the numbers are identical at every level",
                       results["Normal"] == results["Verbose"] == results["Debug"]
                       and bool(results["Normal"]),
                       "empty" if not results["Normal"] else "differ"))

        # Additive, on real output rather than a unit fixture. Compared with
        # the run's own name and every number blanked: three runs write to
        # three folders and take three different amounts of time, and neither
        # difference is what "additive" is about.
        def shape(lines: list[str], level: str) -> list[str]:
            return [re.sub(r"\d+(?:\.\d+)?", "#", ln.replace(level, "RUN"))
                    for ln in lines]

        normal, verbose, debug = (set(shape(said[k], k)) for k in VERBOSE_LEVELS)
        missing_v = sorted(normal - verbose)
        missing_d = sorted(verbose - debug)
        checks.append(("Verbose keeps every line Normal printed",
                       not missing_v, str(missing_v[:3])))
        checks.append(("Debug keeps every line Verbose printed",
                       not missing_d, str(missing_d[:3])))
        checks.append(("and each says strictly more",
                       len(said["Normal"]) < len(said["Verbose"]) < len(said["Debug"]),
                       f"{len(said['Normal'])}/{len(said['Verbose'])}/"
                       f"{len(said['Debug'])}"))

        joined = {k: "\n".join(v) for k, v in said.items()}

        # A Normal run is unchanged: none of the new material leaks into it.
        checks.append(("Normal says nothing about the settings or the batch",
                       "Settings changed" not in joined["Normal"]
                       and "Batch:" not in joined["Normal"], ""))

        checks.append(("Verbose says which batch ran",
                       f"{N_REC} recording(s)" in joined["Verbose"], ""))
        checks.append(("and which settings differ from the defaults",
                       "Settings changed from the defaults" in joined["Verbose"]
                       and "random_seed" in joined["Verbose"], ""))
        checks.append(("and reports the level itself, so a pasted log says "
                       "how complete it is",
                       "Log level: Verbose" in joined["Verbose"]
                       and "Log level: Debug" in joined["Debug"], ""))

        # Only ``_step4_compute_one`` can write this, and it runs in a worker
        # process: seeing it proves the level travelled in Params.
        checks.append(("a worker's own detail line comes back",
                       "active nodes" in joined["Verbose"], ""))
        checks.append(("with the timing of the computation it did",
                       "took" in joined["Verbose"] or "in 0." in joined["Verbose"],
                       ""))

        checks.append(("Debug adds the machine and the libraries",
                       "Libraries:" in joined["Debug"]
                       and "CPU(s)" in joined["Debug"], ""))
        checks.append(("and every setting, not only the changed ones",
                       "min_activity_level" in joined["Debug"]
                       and "min_activity_level" not in joined["Verbose"], ""))
    return checks


# ── The GUI offers exactly these levels ───────────────────────────────────────

def _gui_checks() -> list[Check]:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from meanap.gui.panels.pipeline import PipelinePanel

    panel = PipelinePanel()
    offered = [panel.verbose_level.itemText(i)
               for i in range(panel.verbose_level.count())]
    checks = [("the GUI offers the levels the pipeline implements",
               offered == VERBOSE_LEVELS, str(offered))]

    # A level the GUI cannot reach would be a setting nobody can turn on.
    p = Params()
    p.verbose_level = "Debug"
    panel.load(p)
    saved = Params()
    panel.save(saved)
    checks.append(("and round-trips the one that is set",
                   saved.verbose_level == "Debug", saved.verbose_level))
    checks.append(("with a tooltip explaining the difference",
                   "Debug" in panel.verbose_level.toolTip(), ""))
    del app
    return checks


if __name__ == "__main__":
    passed = total = 0
    for title, fn in (
        ("The log and its levels", _runlog_checks),
        ("A run at each level", _run_checks),
        ("The GUI control", _gui_checks),
    ):
        n, m = _report(title, fn())
        passed += n
        total += m

    print(f"\n{passed}/{total} checks passed")
    raise SystemExit(0 if passed == total else 1)
