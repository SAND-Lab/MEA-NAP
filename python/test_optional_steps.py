"""The optional steps: a checkbox each, and each one actually does something.

Run from the repo root::

    uv run python python/test_optional_steps.py

``Params.optional_steps_to_run`` used to be a multi-select list box holding one
inert entry — ``generateCSV`` was written into the parameter file and read by
nothing. Both halves are checked here:

  - the widgets: a checkbox per step, each with a tooltip, round-tripping
    through ``Params`` in both directions;
  - ``generateCSV``: the spreadsheet is built from the raw data folder before
    step 1, names come from the files, DIV comes from the names, and — unlike
    MATLAB's version, which overwrites — anything already filled in by hand is
    carried across rather than lost;
  - ``Stats``: a finished run carries on into step 5, and a failure there is
    reported as the statistics failing rather than as a failed run.

The pipeline run is steps 3-4 from fabricated spike times, the same cheap
fixture ``test_shared_run.py`` uses: enough of a run to reach the spreadsheet
and finish, without spike detection.
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
from PyQt6.QtWidgets import QApplication, QCheckBox  # noqa: E402

from meanap.params import (  # noqa: E402
    GENERATE_CSV_STEP, STATS_STEP, Params,
)
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402
from meanap.pipeline.spreadsheet import (  # noqa: E402
    generate_spreadsheet, read_recording_table,
)

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


N_CH, FS, LAG = 12, 2000.0, 25
RECS = [f"rec{i}_DIV{d}" for i, d in enumerate([14, 14, 21, 21, 28, 28])]
GROUPS = ["WT", "KO", "WT", "KO", "WT", "KO"]


def seed_raw(folder: Path, recs=RECS) -> Path:
    """Empty files standing in for recordings: only their names are read here."""
    folder.mkdir(parents=True, exist_ok=True)
    for rec in recs:
        (folder / f"{rec}.mat").write_bytes(b"")
    return folder


def seed_spikes(folder: Path, recs=RECS) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(recs):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 80 + ch))}
                  for ch in range(N_CH)}
        save_spike_times_npz(folder / f"{rec}_spikes.npz", spikes,
                             np.arange(1, N_CH + 1), FS, duration_s=60.0)
    return folder


def write_sheet(path: Path, recs=RECS) -> Path:
    pd.DataFrame([{"Recording Filename": r, "DIV group": int(r.split("DIV")[1]),
                   "Genotype": g} for r, g in zip(recs, GROUPS)]
                 ).to_csv(path, index=False)
    return path


def params_for(tmp: Path, sheet: Path, spikes: Path, name: str,
               raw: Path, optional: list[str]) -> Params:
    return Params(
        raw_data=str(raw), spreadsheet_file_name=str(sheet),
        spreadsheet_range="2:100", spike_detected_data=str(spikes),
        output_data_folder=str(tmp / "out"), output_data_folder_name=name,
        start_analysis_step=3, stop_analysis_step=4,
        func_con_lag_val=[LAG], prob_thresh_rep_num=20, channel_layout="MCS60",
        min_number_of_nodes_to_cal_net_met=2, random_seed=5,
        recording_workers=1, optional_steps_to_run=optional,
    )


# ── A. The widgets ────────────────────────────────────────────────────────────

print("\nSection A — a checkbox per optional step")

from meanap.gui.panels.pipeline import PipelinePanel  # noqa: E402

panel = PipelinePanel()
check("every step is a checkbox",
      bool(panel.optional_steps)
      and all(isinstance(b, QCheckBox) for b in panel.optional_steps.values()))
check("both steps are offered",
      set(panel.optional_steps) == {GENERATE_CSV_STEP, STATS_STEP},
      str(set(panel.optional_steps)))
check("each says what it does", all(b.toolTip() for b in panel.optional_steps.values()))

panel.load(Params(optional_steps_to_run=[STATS_STEP]))
check("load ticks exactly what the params name",
      panel.optional_steps[STATS_STEP].isChecked()
      and not panel.optional_steps[GENERATE_CSV_STEP].isChecked())

out = Params()
panel.save(out)
check("and save gives it back", out.optional_steps_to_run == [STATS_STEP],
      str(out.optional_steps_to_run))

panel.optional_steps[GENERATE_CSV_STEP].setChecked(True)
panel.save(out)
check("both ticked round-trips",
      set(out.optional_steps_to_run) == {GENERATE_CSV_STEP, STATS_STEP},
      str(out.optional_steps_to_run))

panel.load(Params(optional_steps_to_run=[]))
panel.save(out)
check("none ticked means an empty list", out.optional_steps_to_run == [],
      str(out.optional_steps_to_run))


# ── B. generateCSV ────────────────────────────────────────────────────────────

print("\nSection B — generateCSV builds the sheet from the raw data")

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    raw = seed_raw(tmp / "raw")
    (raw / "notes.txt").write_bytes(b"")
    (raw / "sub").mkdir()
    (raw / "sub" / "buried.mat").write_bytes(b"")

    sheet = tmp / "recordings.csv"
    generate_spreadsheet(raw, sheet, log=lambda s: None)
    table = read_recording_table(sheet)

    check("one row per raw recording", list(table.iloc[:, 0]) == RECS,
          str(list(table.iloc[:, 0])))
    check("files that are not recordings are left out",
          "notes" not in list(table.iloc[:, 0]))
    check("a sub-folder is not walked into",
          "buried" not in list(table.iloc[:, 0]))
    check("DIV comes from the name",
          list(table.iloc[:, 1]) == ["14", "14", "21", "21", "28", "28"],
          str(list(table.iloc[:, 1])))
    check("genotype is left blank, not guessed",
          set(table.iloc[:, 2]) == {""}, str(set(table.iloc[:, 2])))

    # The expensive column, filled in by hand, then the step run again.
    table.iloc[:, 2] = GROUPS
    table.to_csv(sheet, index=False)
    (raw / "rec6_DIV35.mat").write_bytes(b"")
    generate_spreadsheet(raw, sheet, log=lambda s: None)
    again = read_recording_table(sheet)

    check("a recording added since is picked up", len(again) == 7, str(len(again)))
    carried = dict(zip(again.iloc[:, 0], again.iloc[:, 2]))
    check("hand-filled genotypes survive regenerating",
          [carried[r] for r in RECS] == GROUPS, str(carried))
    check("the new row is blank rather than invented",
          carried["rec6_DIV35"] == "", str(carried))

    try:
        generate_spreadsheet(tmp / "nothing-here", tmp / "x.csv", log=lambda s: None)
        check("a missing raw folder is refused", False, "no error raised")
    except ValueError as exc:
        check("a missing raw folder is refused", "not found" in str(exc), str(exc))


# ── C. generateCSV inside a real run ──────────────────────────────────────────

print("\nSection C — the step runs, and before the sheet is read")

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    raw = seed_raw(tmp / "raw")
    spikes = seed_spikes(tmp / "spikes")

    # A sheet that already matches the data: regenerating it must leave the
    # run's answer alone, which is what makes the option safe to leave on.
    plain_sheet = write_sheet(tmp / "plain.csv")
    plain = run_pipeline(params_for(tmp, plain_sheet, spikes, "plain", raw, []),
                         log=lambda s: None)

    gen_sheet = write_sheet(tmp / "generated.csv")
    generated = run_pipeline(
        params_for(tmp, gen_sheet, spikes, "generated", raw, [GENERATE_CSV_STEP]),
        log=lambda s: None)

    rel = Path("4_NetworkActivity") / "NetworkActivity_RecordingLevel.csv"
    # Both runs read the same spreadsheet in the same order, so the rows line
    # up without sorting — which is itself part of the claim.
    a = pd.read_csv(plain / rel)
    b = pd.read_csv(generated / rel)
    check("the run still analyses every recording", len(b) == len(RECS), str(len(b)))
    check("and gets the same answer as without the step",
          a.equals(b), "recording-level metrics differ")

    # A sheet that is missing entirely: the step has to write one early enough
    # for the run to read it.
    missing = tmp / "does-not-exist-yet.csv"
    check("the sheet really is absent to begin with", not missing.exists())
    p = params_for(tmp, missing, spikes, "from-scratch", raw, [GENERATE_CSV_STEP])
    p.spreadsheet_file_name = str(missing)
    run_pipeline(p, log=lambda s: None)
    check("a run with no spreadsheet writes one and carries on", missing.exists())
    check("and it names the recordings that are there",
          list(read_recording_table(missing).iloc[:, 0]) == RECS)


# ── D. Stats as an optional step ──────────────────────────────────────────────

print("\nSection D — a finished run carries on into step 5")

from meanap.gui.main_window import MainWindow  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)

    window = MainWindow()
    window.show()

    # Not asked for: nothing starts, and the usual closing line is still said.
    window._params = Params(optional_steps_to_run=[])
    started = window._start_optional_stats(tmp)
    check("it stays out of the way when the step is not ticked", started is False)
    check("no stats worker was created", window._stats_worker is None)

    # Asked for: it starts, against the folder the run just produced.
    finished = tmp / "OutputDataTest"
    finished.mkdir()
    window._params = Params(optional_steps_to_run=[STATS_STEP])
    started = window._start_optional_stats(finished)
    check("ticking it starts the step", started is True)
    check("against the run that just finished",
          window._stats_panel.source() == finished,
          str(window._stats_panel.source()))
    check("and the Run log says so",
          "statistics and machine learning" in window._run_panel.log.toPlainText())

    if window._stats_worker is not None:
        window._stats_worker.wait(60_000)
    app.processEvents()

    # That folder holds no run, so the step fails — and the *run* must not be
    # reported as having failed, because it did not.
    log = window._run_panel.log.toPlainText()
    check("a failing stats step is reported as the stats step failing",
          "the statistics step failed" in log, log[-300:])
    check("and says the run itself was fine",
          "The run itself finished" in log, log[-300:])
    window.close()


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All optional-step checks passed.")
