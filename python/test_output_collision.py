"""Test that a run never silently overwrites an earlier one.

Run from the repo root::

    uv run python python/test_output_collision.py

The default output folder name is today's date, so two runs in one day collide
without the user having done anything unusual — and the loss is total: figures,
CSVs and the express bundle, replaced in place. The cases below are the ones
that decide whether the protection is useful or merely annoying:

  - the ``.meanap`` counts even with no folder, since an express user keeps the
    bundle and deletes the folder;
  - resuming *into* a folder must still be allowed, or "start at step 4" would
    rename away the very inputs it is about to read;
  - an empty tree from a crashed run is not a run, and must not force a rename.
"""

from __future__ import annotations

import datetime
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params  # noqa: E402
from meanap.pipeline.output_folders import (  # noqa: E402
    next_free_output_name, output_name_taken, output_paths_for,
)
from meanap.pipeline.runner import (  # noqa: E402
    default_output_folder_name, resolve_output_folder_name, resumes_in_place,
)

Check = tuple[str, bool, str]

NAME = "OutputData07Aug2026"


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _make_run(parent: Path, name: str) -> Path:
    """A folder that looks like a finished run: a tree with files in it."""
    root = parent / name
    (root / "4_NetworkActivity").mkdir(parents=True, exist_ok=True)
    (root / "4_NetworkActivity" / "NetworkActivity_NodeLevel.csv").write_text("x")
    return root


# ── Detection ─────────────────────────────────────────────────────────────────

def _detection_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)

        checks.append(("a name nothing is using is free",
                       not output_name_taken(parent, NAME), ""))

        _make_run(parent, NAME)
        checks.append(("a finished run's folder is detected",
                       output_name_taken(parent, NAME), ""))

        # An express user keeps the .meanap and bins the folder. The next run
        # would then find the name free and overwrite the only thing left.
        folder, bundle = output_paths_for(parent, "ExpressRun")
        bundle.write_bytes(b"PK\x03\x04")
        checks.append(("a bundle counts even with no folder beside it",
                       output_name_taken(parent, "ExpressRun") and not folder.exists(),
                       str(bundle)))

        # A run that died after creating its tree is not a run.
        (parent / "Crashed" / "1_SpikeDetection").mkdir(parents=True)
        checks.append(("an empty tree from a crashed run does not count",
                       not output_name_taken(parent, "Crashed"), ""))

        checks.append(("the bundle name matches what write_bundle actually writes",
                       output_paths_for(parent, NAME)[1].name == f"{NAME}.meanap",
                       output_paths_for(parent, NAME)[1].name))
    return checks


# ── Naming ────────────────────────────────────────────────────────────────────

def _naming_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)

        checks.append(("a free name is returned unchanged",
                       next_free_output_name(parent, NAME) == NAME, ""))

        _make_run(parent, NAME)
        checks.append(("the second run of a day becomes _v2, not _v1",
                       next_free_output_name(parent, NAME) == f"{NAME}_v2",
                       next_free_output_name(parent, NAME)))

        _make_run(parent, f"{NAME}_v2")
        checks.append(("the third becomes _v3",
                       next_free_output_name(parent, NAME) == f"{NAME}_v3",
                       next_free_output_name(parent, NAME)))

        # Re-running from the versioned name itself must count on, not stack.
        checks.append(("an already-versioned name counts on rather than stacking",
                       next_free_output_name(parent, f"{NAME}_v2") == f"{NAME}_v3",
                       next_free_output_name(parent, f"{NAME}_v2")))

        # A bundle alone must push the name along too.
        output_paths_for(parent, f"{NAME}_v3")[1].write_bytes(b"PK\x03\x04")
        checks.append(("a bundle-only run still pushes the next name along",
                       next_free_output_name(parent, NAME) == f"{NAME}_v4",
                       next_free_output_name(parent, NAME)))

        # Past the version ceiling, fall back to a timestamp rather than
        # scanning forever.
        for n in range(2, 101):
            _make_run(parent, f"Busy_v{n}")
        _make_run(parent, "Busy")
        stamped = next_free_output_name(
            parent, "Busy", now=datetime.datetime(2026, 8, 7, 14, 30, 5))
        checks.append(("beyond the version ceiling it falls back to a timestamp",
                       stamped == "Busy_143005", stamped))

        # Custom names get the same treatment as the dated default.
        _make_run(parent, "MyAnalysis")
        checks.append(("a hand-typed name is protected too",
                       next_free_output_name(parent, "MyAnalysis") == "MyAnalysis_v2",
                       next_free_output_name(parent, "MyAnalysis")))
    return checks


# ── What a run decides ────────────────────────────────────────────────────────

def _resolution_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        logs: list[str] = []

        def log(m: str) -> None:
            logs.append(m)

        p = Params(output_data_folder=str(parent), output_data_folder_name=NAME)
        checks.append(("a first run keeps the name it was given",
                       resolve_output_folder_name(p, log) == NAME, ""))
        checks.append(("and says nothing about it",
                       logs == [], str(logs)))

        _make_run(parent, NAME)
        logs.clear()
        chosen = resolve_output_folder_name(p, log)
        checks.append(("a second run moves aside instead of overwriting",
                       chosen == f"{NAME}_v2", chosen))
        checks.append(("and says so, naming both folders",
                       any(NAME in m and f"{NAME}_v2" in m for m in logs), str(logs)))
        checks.append(("and says how to overwrite deliberately",
                       any("overwrite_existing_output" in m for m in logs), str(logs)))

        # Explicitly asked for: land on it.
        logs.clear()
        forced = Params(output_data_folder=str(parent), output_data_folder_name=NAME,
                        overwrite_existing_output=True)
        checks.append(("an explicit overwrite is honoured",
                       resolve_output_folder_name(forced, log) == NAME, ""))
        checks.append(("but still reported, never silent",
                       any("Overwriting" in m for m in logs), str(logs)))

        # Resuming into the folder: renaming would strand the inputs.
        resume = Params(output_data_folder=str(parent), output_data_folder_name=NAME,
                        start_analysis_step=4)
        checks.append(("a run continuing in place is recognised",
                       resumes_in_place(resume), ""))
        checks.append(("and keeps its folder, since it reads what is in it",
                       resolve_output_folder_name(resume, log) == NAME, ""))

        # …but resuming from a *prior* folder writes somewhere new, so it is a
        # genuine collision.
        from_prior = Params(output_data_folder=str(parent),
                            output_data_folder_name=NAME,
                            start_analysis_step=4, prior_analysis=True,
                            prior_analysis_path=str(parent / "Older"))
        checks.append(("resuming from a prior folder is not resuming in place",
                       not resumes_in_place(from_prior), ""))
        checks.append(("so it moves aside like any other new run",
                       resolve_output_folder_name(from_prior, log) == f"{NAME}_v2",
                       resolve_output_folder_name(from_prior, log)))

        # The dated default is what most runs use, and where the bug was.
        blank = Params(output_data_folder=str(parent))
        today = default_output_folder_name()
        _make_run(parent, today)
        checks.append(("the dated default is protected as well",
                       resolve_output_folder_name(blank, log) == f"{today}_v2",
                       resolve_output_folder_name(blank, log)))
    return checks


# ── End to end ────────────────────────────────────────────────────────────────

def _run_checks() -> list[Check]:
    """Two real runs, one after the other, must not tread on each other."""
    from meanap.pipeline.runner import run_pipeline

    checks: list[Check] = []
    import numpy as np
    from meanap.pipeline.io import save_spike_times_npz

    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        sheet = parent / "recordings.csv"
        sheet.write_text("Recording Filename,DIV group,Genotype\nrec_a,14,WT\n")

        # Step 2 off pre-made spike times: enough for a real run through
        # run_pipeline without paying for wavelet spike detection three times.
        spikes = parent / "spikes"
        spikes.mkdir()
        fs = 1000.0
        save_spike_times_npz(
            spikes / "rec_a_spikes.npz",
            {i: {"bior1p5": np.arange(0, 900, 100, dtype=float) + i}
             for i in range(4)},
            np.arange(1, 5), fs, duration_s=1.0,
        )

        p = Params(
            output_data_folder=str(parent),
            output_data_folder_name="Run",
            spreadsheet_file_name=str(sheet),
            spike_detected_data=str(spikes),
            start_analysis_step=2, stop_analysis_step=2,
            prior_analysis=False,
        )

        logs: list[str] = []
        first = run_pipeline(p, log=logs.append)
        checks.append(("the first run writes where it was told",
                       first.name == "Run", first.name))

        second = run_pipeline(p, log=logs.append)
        checks.append(("the second run of the same config lands beside it",
                       second.name == "Run_v2", second.name))
        checks.append(("both runs survive",
                       first.is_dir() and second.is_dir(), ""))
        checks.append(("and the params snapshot of the first is intact",
                       (first / "MEANAP-Params.json").is_file()
                       or any(first.glob("*.json")), str(list(first.glob('*')))))

        third = run_pipeline(p, log=logs.append)
        checks.append(("a third keeps counting", third.name == "Run_v3", third.name))
    return checks


# ── The dialog ────────────────────────────────────────────────────────────────

def _gui_checks(app) -> list[Check]:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QMessageBox
    from meanap.gui.main_window import MainWindow

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        _make_run(parent, NAME)

        w = MainWindow()

        def answer(role: QMessageBox.ButtonRole | None) -> None:
            """Click the button with *role* on whatever dialog is up."""
            def click() -> None:
                for widget in app.topLevelWidgets():
                    if isinstance(widget, QMessageBox) and widget.isVisible():
                        if role is None:
                            widget.reject()
                            return
                        for btn in widget.buttons():
                            if widget.buttonRole(btn) == role:
                                btn.click()
                                return
            QTimer.singleShot(0, click)

        # A fresh one per interaction: accepting the suggestion rewrites the
        # name on the params it is handed (deliberately — the Data tab is
        # updated to match), so reusing one would leave the next case with a
        # name that no longer collides.
        def base() -> Params:
            return Params(output_data_folder=str(parent),
                          output_data_folder_name=NAME)

        # Nothing in the way: no dialog, params come back untouched.
        free = Params(output_data_folder=str(parent), output_data_folder_name="Fresh")
        checks.append(("a free name runs without a dialog",
                       w._confirm_output_folder(free) is free, ""))

        answer(QMessageBox.ButtonRole.AcceptRole)
        chosen = w._confirm_output_folder(base())
        checks.append(("accepting the suggestion renames the run",
                       chosen is not None
                       and chosen.output_data_folder_name == f"{NAME}_v2",
                       str(chosen and chosen.output_data_folder_name)))
        checks.append(("and shows the new name on the Data tab",
                       w._data_panel.output_data_folder_name.text() == f"{NAME}_v2",
                       w._data_panel.output_data_folder_name.text()))

        answer(QMessageBox.ButtonRole.DestructiveRole)
        session = base()
        forced = w._confirm_output_folder(session)
        checks.append(("choosing overwrite keeps the name and sets the flag",
                       forced is not None and forced.overwrite_existing_output
                       and forced.output_data_folder_name == NAME,
                       str(forced)))
        checks.append(("without marking the session's own params to overwrite",
                       # Otherwise "Save params" would carry it into every
                       # future run loaded from that file.
                       not session.overwrite_existing_output, ""))

        answer(None)
        checks.append(("cancelling does not run",
                       w._confirm_output_folder(base()) is None, ""))

        resume = Params(output_data_folder=str(parent), output_data_folder_name=NAME,
                        start_analysis_step=4)
        checks.append(("a resume in place is never questioned",
                       w._confirm_output_folder(resume) is resume, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Output folder collisions")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [("Detection:", _detection_checks),
                         ("Naming:", _naming_checks),
                         ("What a run decides:", _resolution_checks),
                         ("Consecutive runs:", _run_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        app = QApplication.instance() or QApplication([])
        p, n = _report("Run dialog:", _gui_checks(app))
        total_pass += p
        total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
