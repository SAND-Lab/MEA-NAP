"""Test continuing an interrupted run, and changing which recordings it covers.

Run from the repo root::

    uv run python python/test_continue_interrupted.py

A batch cut off at recording 5 of 10 used to mean redoing all ten. Continuing
skips the ones whose result for that step is already on disk.

The load-bearing claim is not "it skips things" but **a continued run produces
what an uninterrupted one would**. Two things have to hold for that:

  - *completeness* — writes are atomic, so a file existing means it is whole.
    Without that, a truncated ``.npz`` from the interrupt would be skipped and
    then fail to load a step later, far from the cause;
  - *the batch reduce still sees the batch* — step 4 pools participation
    coefficient and within-module z-score across every recording to place the
    node-cartography boundaries. A continued run that only saw the recordings it
    recomputed would put those boundaries somewhere the original never would, so
    the finished ones are loaded back in rather than merely skipped.

The last sections check that end to end: interrupt, continue, and compare the
recording-level CSV against a run that was never interrupted.

The same machinery covers changing the batch. **Adding** a recording is just
continuing with a longer spreadsheet — the new one is computed, the rest are
loaded back, and every pooled statistic is redone over all of them.
**Removing** one is a shorter spreadsheet; the numbers follow it on their own,
but its *figures* do not, so those are reported and optionally pruned.
**Combining** separate runs is several prior-analysis folders and one
spreadsheet naming recordings from all of them. Each is checked against the
run you would have got by analysing that set together from the start, because
"cheaper" is only worth anything if the answer is the same.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.params import Params  # noqa: E402
from meanap.pipeline.atomic import (  # noqa: E402
    atomic_path, atomic_savez, guard_readable, is_readable_npz,
)
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.output_folders import create_output_folders  # noqa: E402
from meanap.pipeline.resume import already_done  # noqa: E402
from meanap.pipeline.runner import (  # noqa: E402
    resolve_output_folder_name, run_pipeline,
)

Check = tuple[str, bool, str]

N_REC, N_CH, FS, LAG = 6, 12, 2000.0, 25
RECS = [f"rec{i}" for i in range(N_REC)]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


# ── Atomic writes ─────────────────────────────────────────────────────────────

def _atomic_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        path = atomic_savez(tmp / "a.npz", x=np.arange(5))
        checks.append(("a normal write lands and reads back",
                       is_readable_npz(path), ""))
        checks.append(("leaving no scratch file behind",
                       not [q for q in tmp.iterdir() if q.name.startswith(".")],
                       str([q.name for q in tmp.iterdir()])))

        # The case this exists for: interrupted mid-write.
        atomic_savez(tmp / "b.npz", x=np.arange(3))
        before = (tmp / "b.npz").read_bytes()
        try:
            with atomic_path(tmp / "b.npz", suffix=".npz") as scratch:
                scratch.write_bytes(b"half a file")
                raise KeyboardInterrupt("simulated Ctrl-C")
        except KeyboardInterrupt:
            pass
        checks.append(("an interrupted write leaves the previous file intact",
                       (tmp / "b.npz").read_bytes() == before, ""))
        checks.append(("and cleans up after itself",
                       not [q for q in tmp.iterdir() if q.name.startswith(".")],
                       str([q.name for q in tmp.iterdir()])))

        # A truncated file from before atomic writes existed.
        (tmp / "c.npz").write_bytes(b"PK\x03\x04truncated")
        checks.append(("a corrupt artefact is not mistaken for a finished one",
                       not is_readable_npz(tmp / "c.npz"), ""))
        said: list[str] = []
        checks.append(("the guard rejects it",
                       guard_readable(tmp / "c.npz", said.append) is False, ""))
        checks.append(("deletes it, so it is not re-tripped every run",
                       not (tmp / "c.npz").exists(), ""))
        checks.append(("and explains why it is redoing the work",
                       said and "interrupted" in said[0], str(said)))
    return checks


# ── already_done ──────────────────────────────────────────────────────────────

def _already_done_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good = atomic_savez(tmp / "good.npz", x=np.arange(3))

        off = Params(continue_interrupted=False)
        on = Params(continue_interrupted=True)
        checks.append(("a normal run never skips, however complete the file",
                       not already_done(off, tmp, good), ""))
        checks.append(("a continued run skips a complete artefact",
                       already_done(on, tmp, good), ""))
        checks.append(("and does not skip one that isn't there",
                       not already_done(on, tmp, tmp / "absent.npz"), ""))

        (tmp / "bad.npz").write_bytes(b"PK\x03\x04nope")
        said: list[str] = []
        checks.append(("nor one that will not open",
                       not already_done(on, tmp, tmp / "bad.npz", said.append), ""))
        checks.append(("having removed it so the work is actually redone",
                       not (tmp / "bad.npz").exists(), ""))
    return checks


# ── Where a continued run writes ──────────────────────────────────────────────

def _destination_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "Run" / "4_NetworkActivity").mkdir(parents=True)
        (tmp / "Run" / "4_NetworkActivity" / "x.csv").write_text("x")

        base = dict(output_data_folder=str(tmp), output_data_folder_name="Run")
        logs: list[str] = []
        checks.append(("a normal run steps aside from an existing folder",
                       resolve_output_folder_name(Params(**base), logs.append)
                       == "Run_v2", ""))

        logs.clear()
        chosen = resolve_output_folder_name(
            Params(**base, continue_interrupted=True), logs.append)
        checks.append(("a continued run goes into the folder it is continuing",
                       chosen == "Run", chosen))
        checks.append(("and says what it will do with it",
                       any("Continuing" in m and "skipped" in m for m in logs),
                       str(logs)))

        logs.clear()
        fresh = resolve_output_folder_name(
            Params(output_data_folder=str(tmp), output_data_folder_name="New",
                   continue_interrupted=True), logs.append)
        checks.append(("continuing something that isn't there just runs",
                       fresh == "New"
                       and any("Nothing to continue" in m for m in logs),
                       str(logs)))
    return checks


# ── Step 4, end to end ────────────────────────────────────────────────────────

def _seed_step4_inputs(root: Path) -> None:
    """Spike times and adjacency — the two things step 4 reads."""
    for i, rec in enumerate(RECS):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 80 + ch))}
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


def _step4_params(tmp: Path, name: str, **kw) -> Params:
    p = Params(output_data_folder=str(tmp), output_data_folder_name=name,
               spreadsheet_file_name=str(tmp / "recs.csv"),
               spreadsheet_range="2:100", raw_data=str(tmp / "no-raw"),
               start_analysis_step=4, stop_analysis_step=4,
               func_con_lag_val=[LAG], channel_layout="MCS60",
               min_number_of_nodes_to_cal_net_met=2, random_seed=5,
               recording_workers=1)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _step4_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pd.DataFrame([{"Recording Filename": r, "DIV group": 21, "Genotype": "WT"}
                      for r in RECS]).to_csv(tmp / "recs.csv", index=False)

        ref_root = create_output_folders(tmp, "Ref", ["WT"])
        _seed_step4_inputs(ref_root)
        ref = run_pipeline(_step4_params(tmp, "Ref"), log=lambda m: None)
        ref_json = json.load(open(ref / "4_NetworkActivity" / "netmet_results.json"))
        checks.append(("an uninterrupted run writes every recording",
                       sorted(ref_json) == sorted(RECS), str(sorted(ref_json))))

        # What an interrupted run leaves: the checkpoint holds the recordings
        # that finished, because it is rewritten after each one.
        part = create_output_folders(tmp, "Run", ["WT"])
        _seed_step4_inputs(part)
        ckpt = part / "4_NetworkActivity" / "netmet_results.json"
        ckpt.write_text(json.dumps({k: ref_json[k] for k in RECS[:3]}))

        logs: list[str] = []
        root = run_pipeline(
            _step4_params(tmp, "Run", continue_interrupted=True), log=logs.append)
        checks.append(("continuing writes into the same folder",
                       root.name == "Run", root.name))
        checks.append(("it says how many it is skipping",
                       any("3 recording(s) already have network metrics" in m
                           for m in logs), ""))

        final = json.load(open(ckpt))
        checks.append(("and ends with every recording",
                       sorted(final) == sorted(RECS), str(sorted(final))))

        def table(root: Path) -> pd.DataFrame:
            df = pd.read_csv(root / "4_NetworkActivity"
                             / "NetworkActivity_RecordingLevel.csv")
            return df.sort_values(df.columns[0]).reset_index(drop=True)

        # The claim the whole feature rests on.
        checks.append(("the result is identical to never being interrupted",
                       table(root).equals(table(ref)), "CSVs differ"))

        # Phase C needs adjMsub, which the checkpoint does not store — it is
        # rebuilt from the adjacency. If that failed, the skipped recordings
        # would silently have no figures.
        def n_figs(r: Path) -> int:
            return len(list((r / "4_NetworkActivity"
                             / "4A_IndividualNetworkAnalysis").rglob("*.png")))
        checks.append(("figures are drawn for the skipped recordings too",
                       n_figs(root) == n_figs(ref),
                       f"{n_figs(root)} vs {n_figs(ref)}"))

        # A checkpoint naming a recording whose adjacency is gone must not be
        # trusted: that recording is recomputed instead.
        part2 = create_output_folders(tmp, "Run2", ["WT"])
        _seed_step4_inputs(part2)
        (part2 / "4_NetworkActivity" / "netmet_results.json").write_text(
            json.dumps({k: ref_json[k] for k in RECS[:2]}))
        (part2 / "ExperimentMatFiles" / f"{RECS[0]}_adjM.npz").unlink()
        logs2: list[str] = []
        root2 = run_pipeline(
            _step4_params(tmp, "Run2", continue_interrupted=True), log=logs2.append)
        final2 = json.load(open(root2 / "4_NetworkActivity" / "netmet_results.json"))
        checks.append(("a checkpoint entry with no adjacency is not trusted",
                       any("1 recording(s) already have" in m for m in logs2),
                       str([m for m in logs2 if "already have" in m])))
        checks.append(("and that recording is simply redone or skipped cleanly",
                       RECS[0] not in final2 or final2[RECS[0]],
                       "left in a half state"))
    return checks


# ── The GUI offers it ─────────────────────────────────────────────────────────

# ── Changing which recordings a run covers ────────────────────────────────────

def _batch_change_checks() -> list[Check]:
    """Add one, remove one, and combine two runs — each against a fresh run."""
    checks: list[Check] = []

    def sheet(tmp: Path, recs, name: str) -> Path:
        path = tmp / name
        pd.DataFrame([{"Recording Filename": r, "DIV group": 21,
                       "Genotype": "WT" if int(r[3:]) % 2 else "KO"}
                      for r in recs]).to_csv(path, index=False)
        return path

    def table(root: Path) -> pd.DataFrame:
        df = pd.read_csv(root / "4_NetworkActivity"
                         / "NetworkActivity_RecordingLevel.csv")
        return df.sort_values(df.columns[0]).reset_index(drop=True)

    six = [f"rec{i}" for i in range(6)]

    # ── Adding ───────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = create_output_folders(tmp, "Run", ["WT", "KO"])
        _seed_step4_inputs_for(root, six)
        run_pipeline(_batch_params(tmp, "Run", sheet(tmp, six[:5], "five.csv")),
                     log=lambda m: None)
        run_pipeline(_batch_params(tmp, "Run", sheet(tmp, six, "six.csv"),
                                   continue_interrupted=True), log=lambda m: None)

        ref = create_output_folders(tmp, "Ref", ["WT", "KO"])
        _seed_step4_inputs_for(ref, six)
        ref = run_pipeline(_batch_params(tmp, "Ref", sheet(tmp, six, "six.csv")),
                           log=lambda m: None)
        checks.append(("adding a recording gives what a fresh run would",
                       table(root).equals(table(ref)), "CSVs differ"))
        checks.append(("including the pooled statistics over all of them",
                       len(table(root)) == 6, str(len(table(root)))))

    # ── Removing ─────────────────────────────────────────────────────────────
    for prune in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = create_output_folders(tmp, "Run", ["WT", "KO"])
            _seed_step4_inputs_for(root, six)
            run_pipeline(_batch_params(tmp, "Run", sheet(tmp, six, "six.csv")),
                         log=lambda m: None)
            kept = [r for r in six if r != "rec2"]
            logs: list[str] = []
            run_pipeline(_batch_params(tmp, "Run", sheet(tmp, kept, "five.csv"),
                                       continue_interrupted=True,
                                       prune_removed_recordings=prune),
                         log=logs.append)

            def rec2_figs() -> int:
                base = root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                return len(list(base.rglob("*/rec2/**/*.png")))

            if not prune:
                checks.append(("removing a recording drops it from the results",
                               "rec2" not in table(root).iloc[:, 0].values, ""))
                checks.append(("it is named in the log as no longer listed",
                               any("no longer in the spreadsheet" in m and "rec2" in m
                                   for m in logs), ""))
                checks.append(("its figures are reported rather than left silent",
                               any("still on disk" in m for m in logs), ""))
                checks.append(("and kept, since deleting results is opt-in",
                               rec2_figs() > 0, str(rec2_figs())))
            else:
                checks.append(("pruning removes its figures",
                               rec2_figs() == 0, str(rec2_figs())))
                checks.append(("but keeps its data, so adding it back is cheap",
                               (root / "ExperimentMatFiles" / "rec2_adjM.npz").exists(),
                               ""))
                ref = create_output_folders(tmp, "Ref", ["WT", "KO"])
                _seed_step4_inputs_for(ref, kept)
                ref = run_pipeline(
                    _batch_params(tmp, "Ref", sheet(tmp, kept, "five.csv")),
                    log=lambda m: None)
                checks.append(("and the result matches a fresh run of what is left",
                               table(root).equals(table(ref)), "CSVs differ"))

    # ── Combining ────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, recs in [("RunA", six[:3]), ("RunB", six[3:])]:
            root = create_output_folders(tmp, name, ["WT", "KO"])
            _seed_step4_inputs_for(root, recs)
            run_pipeline(_batch_params(tmp, name, sheet(tmp, recs, f"{name}.csv")),
                         log=lambda m: None)

        logs = []
        combined = run_pipeline(
            _batch_params(tmp, "Combined", sheet(tmp, six, "both.csv"),
                          prior_analysis=True,
                          prior_analysis_path=str(tmp / "RunA"),
                          prior_analysis_paths=[str(tmp / "RunB")]),
            log=logs.append)
        checks.append(("combining two runs covers every recording",
                       len(table(combined)) == 6, str(len(table(combined)))))
        checks.append(("both prior folders are named in the log",
                       sum("RunA" in m or "RunB" in m for m in logs) >= 2,
                       str([m for m in logs if "Run" in m][:3])))

        ref = create_output_folders(tmp, "Ref", ["WT", "KO"])
        _seed_step4_inputs_for(ref, six)
        ref = run_pipeline(_batch_params(tmp, "Ref", sheet(tmp, six, "both.csv")),
                           log=lambda m: None)
        checks.append(("and gives what one analysis of all six would",
                       table(combined).equals(table(ref)), "CSVs differ"))
    return checks


def _seed_step4_inputs_for(root: Path, recs) -> None:
    """As _seed_step4_inputs, for an explicit recording list."""
    for rec in recs:
        i = int(rec[3:])
        rng = np.random.default_rng(i)
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 80 + ch))}
             for ch in range(N_CH)},
            np.arange(1, N_CH + 1), FS, duration_s=60.0)
        adj = np.abs(rng.normal(0, 0.3, (N_CH, N_CH)))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz",
                     channels=np.arange(1, N_CH + 1),
                     **{f"adjM{LAG}mslag": adj, f"adjM{LAG}mslag_raw": adj})


def _batch_params(tmp: Path, name: str, sheet_path: Path, **kw) -> Params:
    p = _step4_params(tmp, name)
    p.spreadsheet_file_name = str(sheet_path)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _gui_checks() -> list[Check]:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from meanap.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "Run" / "4_NetworkActivity").mkdir(parents=True)
        (tmp / "Run" / "4_NetworkActivity" / "x.csv").write_text("x")
        window = MainWindow()

        def click(role) -> None:
            def go() -> None:
                for widget in app.topLevelWidgets():
                    if isinstance(widget, QMessageBox) and widget.isVisible():
                        for btn in widget.buttons():
                            if widget.buttonRole(btn) == role:
                                btn.click()
                                return
            QTimer.singleShot(0, go)

        def base() -> Params:
            return Params(output_data_folder=str(tmp),
                          output_data_folder_name="Run")

        click(QMessageBox.ButtonRole.ActionRole)
        chosen = window._confirm_output_folder(base())
        checks.append(("the dialog offers continuing the existing run",
                       chosen is not None and chosen.continue_interrupted,
                       str(chosen and chosen.continue_interrupted)))
        checks.append(("keeping its folder name",
                       chosen is not None
                       and chosen.output_data_folder_name == "Run",
                       str(chosen and chosen.output_data_folder_name)))

        session = base()
        click(QMessageBox.ButtonRole.ActionRole)
        window._confirm_output_folder(session)
        checks.append(("without marking the session's own params to continue",
                       # Otherwise "Save params" would carry it into every run.
                       not session.continue_interrupted, ""))

        already = Params(output_data_folder=str(tmp),
                         output_data_folder_name="Run",
                         continue_interrupted=True)
        checks.append(("a run already set to continue is not questioned",
                       window._confirm_output_folder(already) is already, ""))
    return checks


def _gui_controls_checks() -> list[Check]:
    """The three things that make this reachable without editing Python."""
    from PyQt6.QtWidgets import QApplication
    from meanap.gui.panels.pipeline import PipelinePanel
    from meanap.gui.panels.spreadsheet_editor import SpreadsheetEditor
    from meanap.pipeline.spreadsheet import (
        new_recording_table, write_recording_table,
    )

    QApplication.instance() or QApplication([])
    checks: list[Check] = []

    # ── Run tab ──────────────────────────────────────────────────────────────
    panel = PipelinePanel()
    checks.append(("the Run tab offers continuing a run",
                   hasattr(panel, "continue_interrupted"), ""))
    checks.append(("pruning is offered but disabled until it applies",
                   hasattr(panel, "prune_removed")
                   and not panel.prune_removed.isEnabled(), ""))
    panel.continue_interrupted.setChecked(True)
    checks.append(("and enabled once continuing is on",
                   panel.prune_removed.isEnabled(), ""))

    panel.prune_removed.setChecked(True)
    out = Params()
    panel.save(out)
    checks.append(("both reach Params",
                   out.continue_interrupted and out.prune_removed_recordings, ""))

    panel.continue_interrupted.setChecked(False)
    out2 = Params()
    panel.save(out2)
    checks.append(("pruning cannot leak into a run that is not continuing",
                   not out2.prune_removed_recordings, ""))

    panel.load(Params(continue_interrupted=True, prune_removed_recordings=True))
    checks.append(("and they round-trip back into the panel",
                   panel.continue_interrupted.isChecked()
                   and panel.prune_removed.isChecked(), ""))

    # ── Prior analysis, which now sits with the switch that enables it ───────
    paths = panel.prior
    checks.append(("the folders are disabled until 'Use prior analysis' is on",
                   not paths.isEnabled(), ""))
    panel.prior_analysis.setChecked(True)
    checks.append(("and enabled once it is",
                   paths.isEnabled(), ""))
    paths.load(Params(prior_analysis_path="/a/RunA",
                      prior_analysis_paths=["/a/RunB", "/a/RunC"]))
    checks.append(("several previous analyses can be listed",
                   paths.extra_prior_paths() == ["/a/RunB", "/a/RunC"],
                   str(paths.extra_prior_paths())))
    merged = Params()
    panel.save(merged)
    checks.append(("the first stays prior_analysis_path, the rest the list",
                   merged.prior_analysis_path == "/a/RunA"
                   and merged.prior_analysis_paths == ["/a/RunB", "/a/RunC"],
                   str(merged.prior_analysis_paths)))
    checks.append(("a folder already named is not added twice",
                   paths._prior_listed("/a/RunB") and paths._prior_listed("/a/RunA")
                   and not paths._prior_listed("/a/New"), ""))

    # ── Spreadsheet editor ───────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        sheet = Path(tmp) / "r.csv"
        table = new_recording_table(["a_DIV21", "b_DIV21", "c_DIV21"])
        table.iloc[:, 2] = "WT"
        write_recording_table(sheet, table)

        editor = SpreadsheetEditor(path=str(sheet))
        checks.append(("an unedited sheet says nothing about continuing",
                       "Continue previous run" not in editor._status.text(),
                       editor._status.text()))

        editor._on_add_row()
        for col, value in ((0, "d_DIV21"), (1, "21"), (2, "WT")):
            editor._table.item(3, col).setText(value)
        checks.append(("adding a recording points at the Continue option",
                       "1 added" in editor._status.text()
                       and "Continue previous run" in editor._status.text(),
                       editor._status.text()))

        editor._table.setCurrentCell(0, 0)
        editor._on_remove_rows()
        text = editor._status.text()
        checks.append(("removing one is reported too",
                       "1 added and 1 removed" in text, text))
        checks.append(("with the figures caveat, which only applies to removals",
                       "figures stay in the output folder" in text, text))

        fresh = SpreadsheetEditor()
        fresh.set_recordings(["x_DIV21"])
        checks.append(("a brand-new sheet has nothing to have changed from",
                       "Continue previous run" not in fresh._status.text(),
                       fresh._status.text()))
    return checks


def main() -> int:
    print("=" * 70)
    print("Continuing an interrupted run")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [("Atomic writes:", _atomic_checks),
                         ("Deciding what is done:", _already_done_checks),
                         ("Where it writes:", _destination_checks),
                         ("Step 4, end to end:", _step4_checks),
                         ("Adding, removing, combining:", _batch_change_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        import PyQt6  # noqa: F401
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        for title, build in [("In the GUI:", _gui_checks),
                             ("GUI controls:", _gui_controls_checks)]:
            p, n = _report(title, build())
            total_pass += p
            total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
