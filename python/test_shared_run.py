"""Test sharing one analysis across several computers through a common folder.

Run from the repo root::

    uv run python python/test_shared_run.py

The claim is that a batch split across machines and pooled on one of them
gives **what a single machine analysing the whole batch would** — the same
per-recording numbers, the same pooled statistics — while every machine only
ever writes its own corner of the shared folder.

Checked here:

  - the split: proportional to benchmark score, adds up, contiguous;
  - the workspace: create, join (including a second computer wanting the
    same name), start, per-machine part spreadsheets, progress records, and
    finding the raw data on another machine by its workspace-relative path;
  - the merge: per-recording files and figure folders unioned, step 4's
    results JSON unioned by key, group-level files left for the pooled run;
  - end to end, with a helper in a *separate process* driven through the
    ``meanap-shared`` command: main + helper → pooled folder, compared
    recording by recording against one uninterrupted run of the same batch;
  - "finish now": a helper that joined but never got going, and the main
    computer doing its share itself — same answer again;
  - the GUI page: what the Run button says in each state, and the table's
    editable split.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.params import Params  # noqa: E402
from meanap.pipeline.atomic import atomic_savez  # noqa: E402
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402
from meanap.shared.merge import merge_outputs, recordings_in  # noqa: E402
from meanap.shared.roles import machine_views, run_main  # noqa: E402
from meanap.shared.workspace import (  # noqa: E402
    DONE, FINISHED, RUNNING, WAITING, WORKING, MachineRecord, ProgressRecord,
    create_workspace, open_workspace, split_by_score, split_recordings,
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_sheet(path: Path, recs=RECS) -> Path:
    pd.DataFrame([{"Recording Filename": r, "DIV group": 21,
                   "Genotype": "WT" if i % 2 else "KO"}
                  for i, r in enumerate(recs)]).to_csv(path, index=False)
    return path


def _seed_spikes(folder: Path, recs=RECS) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(recs):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 80 + ch))}
                  for ch in range(N_CH)}
        save_spike_times_npz(folder / f"{rec}_spikes.npz", spikes,
                             np.arange(1, N_CH + 1), FS, duration_s=60.0)


def _params(tmp: Path, sheet: Path, spikes: Path, name: str) -> Params:
    """Steps 3–4 from pre-detected spikes: the cheapest run that still has
    per-recording work on two steps and pooled work after."""
    return Params(
        raw_data="", spreadsheet_file_name=str(sheet), spreadsheet_range="2:100",
        spike_detected_data=str(spikes),
        output_data_folder=str(tmp / "out"), output_data_folder_name=name,
        start_analysis_step=3, stop_analysis_step=4,
        func_con_lag_val=[LAG], prob_thresh_rep_num=20, channel_layout="MCS60",
        min_number_of_nodes_to_cal_net_met=2, random_seed=5,
        recording_workers=1, express_mode=True,
    )


def _table(root: Path) -> pd.DataFrame:
    """The recording-level step-4 CSV, whether the run left a folder or a bundle."""
    from meanap.pipeline.bundle import is_bundle, open_bundle

    rel = Path("4_NetworkActivity") / "NetworkActivity_RecordingLevel.csv"
    if is_bundle(root):
        with open_bundle(root) as b:
            df = pd.read_csv(b.root / rel)
    else:
        df = pd.read_csv(root / rel)
    return df.sort_values(df.columns[0]).reset_index(drop=True)


def _machine(name: str, role: str = "helper", score: float | None = None,
             host: str | None = None) -> MachineRecord:
    m = MachineRecord.for_this_machine(name, role)
    m.score = score
    if host is not None:
        m.hostname = host
    return m


# ── Splitting ─────────────────────────────────────────────────────────────────

def _split_checks() -> list[Check]:
    checks: list[Check] = []
    recs = [f"r{i}" for i in range(10)]

    s = split_recordings(recs, {"desktop": 3.0, "laptop": 1.0})
    checks.append(("proportional to weight", (len(s["desktop"]), len(s["laptop"])) == (8, 2),
                   str({k: len(v) for k, v in s.items()})))
    checks.append(("contiguous, in spreadsheet order",
                   s["desktop"] == recs[:8] and s["laptop"] == recs[8:], str(s)))

    s = split_recordings(recs, {"a": 1.0, "b": 1.0, "c": 1.0})
    checks.append(("remainders go to the machines listed first",
                   [len(s[m]) for m in "abc"] == [4, 3, 3], str([len(s[m]) for m in "abc"])))
    checks.append(("every recording exactly once",
                   sorted(r for v in s.values() for r in v) == sorted(recs), ""))

    s = split_recordings(recs, {"a": 0.0, "b": 0.0})
    checks.append(("no scores at all → even split", [len(s["a"]), len(s["b"])] == [5, 5], str(s)))

    s = split_recordings(recs[:1], {"a": 1.0, "b": 5.0})
    checks.append(("one recording goes to one machine, nobody gets a negative share",
                   sorted(len(v) for v in s.values()) == [0, 1], str(s)))

    machines = [_machine("laptop", score=1.0), _machine("desktop", "main", score=3.0),
                _machine("old", score=None)]
    s = split_by_score(recs, machines, "desktop")
    checks.append(("split_by_score puts the main computer first",
                   list(s) == ["desktop", "laptop", "old"], str(list(s))))
    checks.append(("an un-benchmarked machine counts as average",
                   len(s["old"]) == 3 and len(s["desktop"]) == 5, str({k: len(v) for k, v in s.items()})))
    return checks


# ── The workspace ─────────────────────────────────────────────────────────────

def _workspace_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shared = tmp / "Dropbox"
        raw = shared / "Data" / "raw"
        raw.mkdir(parents=True)
        # Raw files exist by name only: create_workspace never opens them.
        for rec in RECS:
            (raw / f"{rec}.mat").write_bytes(b"")
        sheet = _write_sheet(tmp / "recs.csv")
        params = Params(raw_data=str(raw), spreadsheet_file_name=str(sheet),
                        spreadsheet_range="2:4", output_data_folder=str(tmp / "out"),
                        output_data_folder_name="Mine", continue_interrupted=True)

        logs: list[str] = []
        (shared / "Runs").mkdir()
        ws = create_workspace(shared / "Runs", "My Run", params,
                              _machine("desktop", "main", score=2.0), log=logs.append)
        run = ws.read()
        checks.append(("the workspace is named for the run, filesystem-safe",
                       ws.path.name == "My-Run.meanap-shared", ws.path.name))
        checks.append(("only the rows in the spreadsheet range are in the batch",
                       run.recordings == RECS[:3], str(run.recordings)))
        checks.append(("per-run output settings are not carried into the manifest",
                       run.params["output_data_folder_name"] == ""
                       and run.params["continue_interrupted"] is False
                       and run.params["spreadsheet_file_name"] == "", ""))
        checks.append(("the raw data is recorded relative to the workspace",
                       run.raw_data["relative"].replace("\\", "/") == "../../Data/raw",
                       str(run.raw_data)))
        checks.append(("the main computer is registered",
                       [m.name for m in ws.machines()] == ["desktop"]
                       and ws.machines()[0].role == "main", str(ws.machines())))

        # Another computer, then a third asking for the same name.
        laptop = ws.join(_machine("laptop", score=1.0, host="laptop.local"))
        other = ws.join(_machine("laptop", score=0.5, host="other.local"))
        checks.append(("a second computer with the same name gets a suffix",
                       (laptop.name, other.name) == ("laptop", "laptop-2"),
                       f"{laptop.name}, {other.name}"))
        rejoined = ws.join(_machine("laptop", score=1.5, host="laptop.local"))
        checks.append(("the same computer joining again keeps its name",
                       rejoined.name == "laptop", rejoined.name))
        checks.append(("everyone starts out waiting",
                       all(ws.read_progress(m.name).status == WAITING for m in ws.machines()), ""))
        checks.append(("machines list the main computer first",
                       [m.name for m in ws.machines()] == ["desktop", "laptop", "laptop-2"],
                       str([m.name for m in ws.machines()])))

        # Finding the data from "another machine": move the whole synced folder.
        moved = tmp / "elsewhere" / "Dropbox"
        (tmp / "elsewhere").mkdir()
        shared.rename(moved)
        ws2 = open_workspace(moved / "Runs" / "My-Run.meanap-shared")
        found = ws2.resolve_raw_data()
        checks.append(("the raw data is found by its workspace-relative path",
                       found is not None and Path(found) == (moved / "Data" / "raw").resolve(),
                       str(found)))
        # And not when the folder is there but the recordings are not.
        for rec in RECS:
            (moved / "Data" / "raw" / f"{rec}.mat").unlink()
        checks.append(("…but a folder without the recordings does not count",
                       ws2.resolve_raw_data() is None, str(ws2.resolve_raw_data())))

        # Starting.
        try:
            ws2.start({"desktop": RECS[:2]})
            bad = False
        except ValueError:
            bad = True
        checks.append(("a split that misses a recording is refused", bad, ""))
        run = ws2.start({"desktop": RECS[:2], "laptop": RECS[2:3], "laptop-2": []})
        checks.append(("starting records the split and flips the status",
                       run.status == RUNNING and run.assigned_to("laptop") == ["rec2"], ""))
        part = pd.read_csv(ws2.part_spreadsheet("desktop"))
        checks.append(("each machine gets a spreadsheet with just its rows, same columns",
                       list(part["Recording Filename"]) == RECS[:2]
                       and list(part.columns) == ["Recording Filename", "DIV group", "Genotype"],
                       str(part)))
        wp = ws2.worker_params("desktop", raw_data="/data/here")
        checks.append(("worker params: own part, own output, continuing",
                       wp.spreadsheet_file_name.endswith("desktop/recordings.csv")
                       and wp.output_data_folder_name == "output"
                       and wp.continue_interrupted and wp.raw_data == "/data/here", ""))
        fp = ws2.final_params(tmp / "out", "Pooled", raw_data="")
        checks.append(("final params: whole batch, chosen folder, continuing",
                       fp.spreadsheet_file_name == str(ws2.spreadsheet_path)
                       and fp.output_data_folder_name == "Pooled" and fp.continue_interrupted, ""))
        remote = ws2.worker_params("desktop", raw_data="https://www.dropbox.com/scl/fo/x")
        checks.append(("a remote source caches outside the shared folder",
                       remote.cache_dir and "meanap-shared" not in remote.cache_dir.lower()
                       and not remote.cache_dir.startswith(str(ws2.path)), remote.cache_dir))

        # Progress.
        ws2.write_progress("laptop", ProgressRecord(status=WORKING, fraction=0.4, detail="rec2"))
        p = ws2.read_progress("laptop")
        checks.append(("progress round-trips with a timestamp",
                       p.status == WORKING and p.fraction == 0.4 and p.age_s() is not None
                       and p.age_s() < 5, str(p)))
        views = machine_views(ws2)
        checks.append(("machine views pair each machine with its progress and share",
                       [(v.machine.name, v.assigned, v.status) for v in views]
                       == [("desktop", 2, WAITING), ("laptop", 1, WORKING), ("laptop-2", 0, WAITING)],
                       str([(v.machine.name, v.assigned, v.status) for v in views])))
        lines = ws2.describe()
        checks.append(("describe() is readable", len(lines) == 4 and "40%" in lines[2], str(lines)))
    return checks


# ── Merging ───────────────────────────────────────────────────────────────────

def _merge_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def part(name: str, recs: list[str]) -> Path:
            root = tmp / name
            spikes = root / "1_SpikeDetection" / "1A_SpikeDetectedData"
            adjm = root / "ExperimentMatFiles"
            spikes.mkdir(parents=True)
            adjm.mkdir(parents=True)
            netmet = {}
            for rec in recs:
                atomic_savez(spikes / f"{rec}_spikes.npz", x=np.arange(3))
                atomic_savez(adjm / f"{rec}_adjM.npz", channels=np.arange(3))
                for fam in ("4_NetworkActivity/4A_IndividualNetworkAnalysis",
                            "3_EdgeThresholdingCheck"):
                    d = root / fam / "WT" / rec
                    d.mkdir(parents=True)
                    (d / "fig.png").write_bytes(b"png")
                netmet[rec] = {"25mslag": {"ND": [1, 2, 3], "source": name}}
            (root / "4_NetworkActivity").mkdir(exist_ok=True)
            (root / "4_NetworkActivity" / "netmet_results.json").write_text(json.dumps(netmet))
            # Group-level things that must *not* travel.
            (root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv").write_text("x")
            (root / "4_NetworkActivity" / "4B_GroupComparisons").mkdir()
            (root / "4_NetworkActivity" / "4B_GroupComparisons" / "g.png").write_bytes(b"")
            return root

        a = part("A", ["rec0", "rec1"])
        b = part("B", ["rec1", "rec2"])      # rec1 in both: first writer wins
        checks.append(("recordings_in reads the names off the data files",
                       recordings_in(a) == {"rec0", "rec1"}, str(recordings_in(a))))

        dest = tmp / "Pooled"
        logs: list[str] = []
        report = merge_outputs([a, b], dest, log=logs.append)
        checks.append(("every recording's data files are in the pooled folder",
                       all((dest / "ExperimentMatFiles" / f"{r}_adjM.npz").is_file()
                           and (dest / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{r}_spikes.npz").is_file()
                           for r in ("rec0", "rec1", "rec2")), ""))
        checks.append(("and their figure folders, from every family",
                       all((dest / fam / "WT" / r / "fig.png").is_file()
                           for r in ("rec0", "rec1", "rec2")
                           for fam in ("4_NetworkActivity/4A_IndividualNetworkAnalysis",
                                       "3_EdgeThresholdingCheck")), ""))
        pooled = json.loads((dest / "4_NetworkActivity" / "netmet_results.json").read_text())
        checks.append(("netmet_results.json is unioned by recording",
                       sorted(pooled) == ["rec0", "rec1", "rec2"], str(sorted(pooled))))
        checks.append(("a recording present in two parts is taken once, first part first",
                       pooled["rec1"]["25mslag"]["source"] == "A", str(pooled["rec1"])))
        checks.append(("group-level files are not carried over",
                       not (dest / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv").exists()
                       and not (dest / "4_NetworkActivity" / "4B_GroupComparisons").exists(), ""))
        checks.append(("the report counts what happened",
                       report.sources == 2 and report.recordings == {"rec0", "rec1", "rec2"}
                       and report.netmet_entries == 3 and report.already_present > 0,
                       str(report)))

        # A part that is a bundle rather than a folder.
        from meanap.pipeline.bundle import build_manifest, write_bundle
        from meanap.pipeline.spreadsheet import RecordingInfo
        c = part("C", ["rec3"])
        manifest = build_manifest(
            Params(func_con_lag_val=[25]),
            [RecordingInfo(filename="rec3", div=21, group="WT")], mode="ephys")
        bundle = write_bundle(c, manifest)
        report2 = merge_outputs([bundle], dest)
        checks.append(("a bundle part is merged like a folder",
                       (dest / "ExperimentMatFiles" / "rec3_adjM.npz").is_file()
                       and "rec3" in json.loads(
                           (dest / "4_NetworkActivity" / "netmet_results.json").read_text()),
                       str(report2)))

        # Merging into a folder that is itself one of the sources is a no-op for it.
        report3 = merge_outputs([a], a)
        checks.append(("a part merged into itself is left alone",
                       report3.files_copied == 0 and report3.recordings == {"rec0", "rec1"},
                       str(report3)))
    return checks


# ── The benchmark ─────────────────────────────────────────────────────────────

def _benchmark_checks() -> list[Check]:
    from meanap.shared.benchmark import run_benchmark

    checks: list[Check] = []
    logs: list[str] = []
    t0 = time.perf_counter()
    result = run_benchmark(scale=0.1, log=logs.append, max_processes=2)
    wall = time.perf_counter() - t0
    checks.append(("a scaled benchmark runs and scores",
                   result.score > 0 and result.seconds > 0, str(result)))
    checks.append(("its parts add up", abs(result.detection_s + result.network_s
                                          - result.seconds * 0.1) < 1e-6, str(result)))
    checks.append(("it reports the machine", result.cores >= 1 and result.ram_gb > 0, ""))
    checks.append(("and explains itself", any("relative speed" in m for m in logs), str(logs)))
    print(f"    (scaled benchmark took {wall:.1f} s)")
    return checks


# ── End to end ────────────────────────────────────────────────────────────────

def _helper_process(ws_path: Path, name: str) -> subprocess.Popen:
    """A helper computer: the CLI, in its own process, joining and waiting."""
    return subprocess.Popen(
        [sys.executable, "-m", "meanap.shared.cli", "join", str(ws_path),
         "--name", name, "--no-benchmark"],
        cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )


def _wait_for(predicate, timeout_s: float, every: float = 0.5) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(every)
    return predicate()


def _end_to_end_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shared = tmp / "Dropbox"
        spikes = shared / "spikes"
        _seed_spikes(spikes)
        sheet = _write_sheet(tmp / "recs.csv")
        params = _params(tmp, sheet, spikes, "Ref")

        # The answer: one machine, the whole batch.
        ref = run_pipeline(params, log=lambda m: None)
        ref_table = _table(ref)
        checks.append(("the reference run covers the batch", len(ref_table) == N_REC, str(len(ref_table))))

        # ── Main + a helper in another process ───────────────────────────────
        logs: list[str] = []
        ws = create_workspace(shared, "Shared", params,
                              _machine("desktop", "main", score=1.0), log=logs.append)
        helper = _helper_process(ws.path, "laptop")
        joined = _wait_for(lambda: ws.machine("laptop") is not None, 60)
        checks.append(("the helper joins from its own process", joined, ""))
        if joined:
            assignment = split_by_score(ws.read().recordings, ws.machines(), "desktop")
            ws.start(assignment)
            checks.append(("the split gives both computers work",
                           all(assignment.values()) and sorted(assignment) == ["desktop", "laptop"],
                           str({k: len(v) for k, v in assignment.items()})))
            root = run_main(ws, "desktop", output_data_folder=tmp / "out",
                            output_data_folder_name="Pooled", log=logs.append, poll_s=1.0)
            helper_out, _ = helper.communicate(timeout=300)
            checks.append(("the helper process ends cleanly",
                           helper.returncode == 0, helper_out[-800:]))
            checks.append(("the helper says it is done",
                           ws.read_progress("laptop").status == FINISHED,
                           str(ws.read_progress("laptop"))))
            checks.append(("the main computer waited for it",
                           any("laptop: done" in m for m in logs), ""))
            checks.append(("the run is marked done", ws.read().status == DONE, ws.read().status))
            pooled = _table(root)
            checks.append(("the pooled result has every recording",
                           sorted(pooled[pooled.columns[0]]) == sorted(ref_table[ref_table.columns[0]]),
                           str(list(pooled[pooled.columns[0]]))))
            checks.append(("and it is identical to one machine doing the whole batch",
                           pooled.equals(ref_table), "CSVs differ"))
            # Each machine only ever wrote its own corner.
            own = recordings_in(ws.part_results("desktop")) if ws.part_results("desktop") \
                and ws.part_results("desktop").is_dir() else set()
            checks.append(("each part holds only its share",
                           (not own or own == set(assignment["desktop"])), str(own)))
        else:
            helper.kill()

        # ── "Finish now": a helper that never gets going ─────────────────────
        logs2: list[str] = []
        ws2 = create_workspace(shared, "Alone", params,
                               _machine("desktop", "main", score=1.0), log=logs2.append)
        ws2.join(_machine("ghost", score=1.0, host="ghost.local"))
        ws2.start(split_by_score(ws2.read().recordings, ws2.machines(), "desktop"))
        polls = {"n": 0}

        def finish_now() -> bool:
            polls["n"] += 1
            return polls["n"] >= 2

        root2 = run_main(ws2, "desktop", output_data_folder=tmp / "out",
                         output_data_folder_name="Pooled2", log=logs2.append,
                         poll_s=0.2, finish_now=finish_now)
        checks.append(("finish-now stops the wait",
                       any("Finishing now" in m for m in logs2), ""))
        checks.append(("and says which recordings it will do itself",
                       any("no results yet and will be analysed here" in m for m in logs2), ""))
        checks.append(("the ghost's recordings are done on the main computer, same answer",
                       _table(root2).equals(ref_table), "CSVs differ"))
    return checks


# ── The GUI page ──────────────────────────────────────────────────────────────

def _gui_checks() -> list[Check]:
    from PyQt6.QtWidgets import QApplication, QSpinBox

    app = QApplication.instance() or QApplication([])
    from meanap.gui.main_window import MainWindow
    from meanap.gui.panels.run import SHARED
    from meanap.gui.panels.shared import ROLE_MAIN, SetupWizard, _describe_data_reach

    checks: list[Check] = []
    window = MainWindow()
    window.show()
    app.processEvents()
    run_panel, panel = window._run_panel, window._shared_panel

    run_panel.set_mode(SHARED)
    app.processEvents()
    checks.append(("the Run tab has a third page", run_panel.mode() == SHARED
                   and run_panel._stack.currentWidget() is panel, ""))
    checks.append(("before anything is set up, Start is off and says why",
                   not run_panel.run_btn.isEnabled()
                   and "Start shared run" in run_panel.run_btn.text()
                   and run_panel.run_btn.toolTip(), run_panel.run_btn.text()))
    checks.append(("the test-pipeline button does not apply here",
                   not run_panel.test_btn.isVisibleTo(run_panel), ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shared = tmp / "Dropbox"
        (shared / "raw").mkdir(parents=True)
        for rec in RECS:
            (shared / "raw" / f"{rec}.mat").write_bytes(b"")
        sheet = _write_sheet(tmp / "recs.csv")
        params = Params(raw_data=str(shared / "raw"), spreadsheet_file_name=str(sheet),
                        spreadsheet_range="2:100", output_data_folder=str(tmp / "out"),
                        output_data_folder_name="Run")

        # The setup wizard's checks, without showing it.
        wiz = SetupWizard(params)
        page = wiz.folder_page
        page._revalidate()
        checks.append(("the folder page wants a folder first",
                       not page.isComplete() and "Choose" in page.status.text(), page.status.text()))
        page.folder.set_value(str(shared))
        checks.append(("…and is happy with one", page.isComplete(), page.status.text()))
        checks.append(("it says the data will be found from the other computers",
                       page.data_note.text().startswith("✓"), page.data_note.text()))
        checks.append(("and says when it will not",
                       _describe_data_reach(Params(raw_data="/elsewhere/raw"), str(shared)).startswith("!"), ""))
        (tmp / "out" / "Run" / "4_NetworkActivity").mkdir(parents=True)
        (tmp / "out" / "Run" / "4_NetworkActivity" / "x.csv").write_text("x")
        wiz.output_page.initializePage()
        checks.append(("the output page steps aside from an existing run",
                       wiz.output_page.name.text() == "Run_v2" and wiz.output_page.isComplete(),
                       wiz.output_page.name.text()))

        # The page with a run in it, as the main computer.
        ws = create_workspace(shared, "Run", params, _machine("desktop", "main", score=3.0))
        panel.workspace, panel.role, panel.machine_name = ws, ROLE_MAIN, "desktop"
        panel.params = params
        panel.output_folder, panel.output_name = str(tmp / "out"), "Pooled"
        panel._show_state(True)
        panel.refresh()
        app.processEvents()
        checks.append(("alone, Start waits for company",
                       not run_panel.run_btn.isEnabled() and "other computer" in run_panel.run_btn.toolTip(),
                       run_panel.run_btn.toolTip()))
        ws.join(_machine("laptop", score=1.0, host="laptop.local"))
        panel.refresh()
        app.processEvents()
        checks.append(("with a helper, Start is on and counts the computers",
                       run_panel.run_btn.isEnabled() and "2 computers" in run_panel.run_btn.text(),
                       run_panel.run_btn.text()))
        checks.append(("the table lists both", panel.table.rowCount() == 2
                       and "desktop" in panel.table.item(0, 0).text()
                       and "this computer" in panel.table.item(0, 0).text(), ""))
        # Speeds 3.0 : 1.0 over six recordings → 4.5 : 1.5, rounded to 5 : 1
        # (the tie on the remainder goes to the main computer).
        spin = panel.table.cellWidget(1, 3)
        checks.append(("the helper's count is editable, the main computer's is the remainder",
                       isinstance(spin, QSpinBox) and spin.value() == 1
                       and panel.table.item(0, 3).text() == "5",
                       f"{spin and spin.value()} / {panel.table.item(0, 3).text()}"))
        spin.setValue(4)
        app.processEvents()
        checks.append(("editing a count moves the remainder",
                       panel.table.item(0, 3).text() == "2", panel.table.item(0, 3).text()))
        assignment = panel.assignment()
        checks.append(("the assignment follows the table, main first, contiguous",
                       list(assignment) == ["desktop", "laptop"]
                       and assignment["desktop"] == RECS[:2] and assignment["laptop"] == RECS[2:],
                       str(assignment)))
        panel._reset_split()
        app.processEvents()
        checks.append(("'Split by speed' restores the proportional split",
                       panel.table.cellWidget(1, 3).value() == 1,
                       str(panel.table.cellWidget(1, 3).value())))

        panel.set_running(True)
        app.processEvents()
        checks.append(("while running, Start is off and the finish-now button is not yet shown",
                       not run_panel.run_btn.isEnabled() and not panel.finish_btn.isVisibleTo(panel), ""))
        ws.start(panel.assignment())
        panel.refresh()
        app.processEvents()
        checks.append(("once started, finish-now is offered",
                       panel.finish_btn.isVisibleTo(panel), ""))
        panel.set_running(False)
        panel.mark_finished("Finished.")
        app.processEvents()
        checks.append(("finished text shows", panel.status_label.text() == "Finished.", ""))
        panel.reset()
        app.processEvents()
        checks.append(("leaving returns the page to its two choices",
                       panel.workspace is None and panel.setup_btn.isVisibleTo(panel), ""))
    window.close()
    return checks


def main() -> int:
    passed = total = 0
    sections = [
        ("Splitting the batch", _split_checks),
        ("The workspace", _workspace_checks),
        ("Merging parts", _merge_checks),
        ("The benchmark", _benchmark_checks),
        ("The GUI page", _gui_checks),
        ("End to end: main + helper process, and finish-now", _end_to_end_checks),
    ]
    for title, fn in sections:
        p, t = _report(title, fn())
        passed += p
        total += t
    print(f"\n{'ALL PASSED' if passed == total else 'FAILURES'}: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
