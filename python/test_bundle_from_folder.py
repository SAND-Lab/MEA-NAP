"""Packing a finished output folder into a bundle, after the run.

A bundle used to be reachable only through express mode, which is a decision
made *before* the analysis starts. So a full run that turned out to be worth
emailing — 111 MB of PNGs against the ~3 MB they were drawn from — had no route
to the shareable file except running everything again, even though every byte
the bundle needs was already sitting on disk.

``bundle_output_folder`` closes that gap, and these checks are about the two
things it must not get wrong. It has to reconstruct the manifest the runner
used to build from live pipeline state — which recordings, which pipeline,
which lags — from the folder alone; and it must leave the folder exactly as it
found it, because unlike an express run the user still wants it.

Run: ``uv run python python/test_bundle_from_folder.py``
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from meanap.params import Params, save_params  # noqa: E402
from meanap.pipeline.bundle import MANIFEST_NAME, open_bundle  # noqa: E402
from meanap.pipeline.pack import (  # noqa: E402
    bundle_output_folder, default_bundle_dest, unbundlable_reason,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


RECS = [("MPT_A1", "WT", 14.0), ("MPT_A2", "KO", 21.0)]
LAGS = (10, 25)


def make_output_folder(root: Path, *, params: Params | None = None,
                       step4: bool = True) -> Path:
    """A stand-in for what a full ephys run leaves behind.

    Small, but with one file of every kind the packer reads or decides about:
    the settings, the recording table, the metrics, per-recording arrays, and
    figures from both a family that is redrawn and a family that is carried.
    """
    root.mkdir(parents=True, exist_ok=True)
    save_params(params or Params(func_con_lag_val=list(LAGS)), root)

    (root / "ExperimentMatFiles").mkdir(exist_ok=True)
    for name, _grp, _div in RECS:
        np.savez(root / "ExperimentMatFiles" / f"{name}_adjM.npz",
                 **{f"adjM{lag}mslag": np.zeros((4, 4)) for lag in LAGS})

    net = root / "4_NetworkActivity"
    net.mkdir(exist_ok=True)
    if step4:
        (net / "NetworkActivity_RecordingLevel.csv").write_text(
            "FileName,Grp,DIV,ND\n"
            + "".join(f"{n},{g},{d:g},1.0\n" for n, g, d in RECS))
        with open(net / "netmet_results.json", "w") as fh:
            json.dump({n: {f"{lag}mslag": {"ND": [1.0]} for lag in LAGS}
                       for n, _g, _d in RECS}, fh)

    # A redrawn family (4A) and a carried one (2A): the first must be left out
    # of the zip, the second must travel.
    for name, grp, _div in RECS:
        redrawn = net / "4A_IndividualNetworkAnalysis" / grp / name
        redrawn.mkdir(parents=True, exist_ok=True)
        (redrawn / "1_NetworkPlot.png").write_bytes(b"\x89PNG" + b"x" * 4096)
        carried = root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / grp / name
        carried.mkdir(parents=True, exist_ok=True)
        (carried / "unit1_trace.png").write_bytes(b"\x89PNG" + b"y" * 64)
    (root / "2_NeuronalActivity" / "ephys_results.json").write_text("{}")
    return root


# ── What the manifest says about a folder it had to read for itself ───────────

print("\nReconstructing the manifest from the folder")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    run = make_output_folder(tmp / "OutputData01Jan2026")
    before = sorted(p.relative_to(run).as_posix() for p in run.rglob("*")
                    if p.is_file())

    result = bundle_output_folder(run, log=lambda _m: None)

    check("it lands beside the folder under the folder's name",
          result.dest == tmp / "OutputData01Jan2026.meanap"
          and result.dest.is_file(), str(result.dest))
    check("nothing to warn about for a complete run",
          result.warnings == [], str(result.warnings))

    with open_bundle(result.dest) as bundle:
        names = {r["filename"] for r in bundle.recordings}
        check("both recordings are named, from the recording-level CSV",
              names == {n for n, _g, _d in RECS}, str(sorted(names)))
        check("with the groups and DIVs beside them",
              {(r["filename"], r["group"], r["div"]) for r in bundle.recordings}
              == {(n, g, d) for n, g, d in RECS}, str(bundle.recordings))
        check("the pipeline is read from the settings", bundle.mode == "ephys",
              bundle.mode)
        # From netmet_results.json rather than func_con_lag_val: a manifest that
        # claims a lag the run has no metrics for gives the viewer a control
        # that selects an empty figure list.
        check("the lags are the ones the run actually produced",
              bundle.lags == list(LAGS), str(bundle.lags))
        check("the count reported matches the manifest",
              result.recordings == len(RECS), str(result.recordings))

    with zipfile.ZipFile(result.dest) as zf:
        packed = set(zf.namelist())
    check("the manifest is in it", MANIFEST_NAME in packed, "")
    check("redrawable figures are left out — that is the whole saving",
          not any(p.startswith("4_NetworkActivity/4A_") for p in packed),
          str(sorted(p for p in packed if "4A_" in p)))
    check("the data those figures come from travels",
          "4_NetworkActivity/netmet_results.json" in packed
          and any(p.endswith("_adjM.npz") for p in packed), str(sorted(packed)))
    check("figures that cannot be redrawn travel as pictures",
          any(p.startswith("2_NeuronalActivity/2A_") and p.endswith(".png")
              for p in packed), str(sorted(packed)))

    # The one thing that separates this from an express run, which deletes the
    # folder it packed. Here the folder is the reason the user has a bundle to
    # make at all.
    after = sorted(p.relative_to(run).as_posix() for p in run.rglob("*")
                   if p.is_file())
    check("the output folder keeps every file it had",
          set(before) <= set(after), str(sorted(set(before) - set(after))))
    check("...and gains only the manifest",
          set(after) - set(before) == {MANIFEST_NAME},
          str(sorted(set(after) - set(before))))


# ── Not overwriting a bundle whose run may be gone ────────────────────────────

print("\nWhere a second bundle goes")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    run = make_output_folder(tmp / "Run")
    first = bundle_output_folder(run, log=lambda _m: None).dest
    check("the default name is free the first time",
          first.name == "Run.meanap", first.name)

    # An express run leaves a bundle and deletes its folder, so the file sitting
    # at the default name can be the only surviving copy of a different run.
    second = default_bundle_dest(run)
    check("a second pack steps aside rather than overwriting",
          second.name == "Run_v2.meanap" and first.is_file(), second.name)


# ── Folders that cannot, or only partly, be packed ────────────────────────────

print("\nFolders that are not a Python run")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    empty = tmp / "NotARun"
    empty.mkdir()
    try:
        bundle_output_folder(empty, log=lambda _m: None)
        check("an unrelated folder is refused", False, "no error raised")
    except ValueError as e:
        check("an unrelated folder is refused, saying what to pick instead",
              "does not look like a MEA-NAP output folder" in str(e)
              and "1_SpikeDetection" in str(e), str(e))

    # A MATLAB run is a perfectly good analysis in a format this cannot pack,
    # which is a different thing from a folder that is not a run at all.
    matlab = tmp / "OutputData28Aug2025"
    matlab.mkdir()
    (matlab / "Parameters_OutputData28Aug2025.mat").write_bytes(b"MATLAB")
    (matlab / "4_NetworkActivity").mkdir()
    try:
        bundle_output_folder(matlab, log=lambda _m: None)
        check("a MATLAB folder is refused", False, "no error raised")
    except ValueError as e:
        check("a MATLAB run is told it is one, not that it looks broken",
              "MATLAB" in str(e) and "does not look like" not in str(e), str(e))

    try:
        bundle_output_folder(tmp / "NoSuchFolder", log=lambda _m: None)
        check("a missing folder is refused", False, "no error raised")
    except ValueError as e:
        check("a missing folder is refused", "Not an output folder" in str(e),
              str(e))

    # The GUI asks this before it asks where to save, so it has to give the
    # same answers as the pack itself rather than a second opinion.
    check("the reason is available without attempting the pack",
          unbundlable_reason(empty) is not None
          and unbundlable_reason(matlab) is not None
          and unbundlable_reason(tmp / "NoSuchFolder") is not None, "")

    # Stopping before step 4 is not a reason to refuse: the bundle is still a
    # valid thing to resume from, it just has nothing to look at.
    partial = make_output_folder(tmp / "StoppedEarly", step4=False)
    result = bundle_output_folder(partial, log=lambda _m: None)
    check("...and a packable folder gives no reason at all",
          unbundlable_reason(partial) is None, str(unbundlable_reason(partial)))
    check("a run that never reached step 4 still packs",
          result.dest.is_file(), str(result.dest))
    check("...and says why the viewer will not open it",
          any("netmet_results.json" in w for w in result.warnings)
          and any("recordings" in w for w in result.warnings),
          str(result.warnings))


# ── A bundle that will not open is not left to be sent ────────────────────────

print("\nVerification")

with tempfile.TemporaryDirectory() as tmp:
    from meanap.pipeline.pack import _verify

    broken = Path(tmp) / "Broken.meanap"
    broken.write_bytes(b"not a zip at all")
    try:
        _verify(broken)
        check("a bundle that will not reopen is rejected", False, "no error")
    except ValueError as e:
        check("a bundle that will not reopen is rejected", "read back" in str(e),
              str(e))
    check("...and removed, rather than left with the right name and size",
          not broken.exists(), "")


# ── The GUI can reach it ──────────────────────────────────────────────────────

print("\nThe Results tab")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from meanap.gui.main_window import MainWindow  # noqa: E402

window = MainWindow()
window.show()
app.processEvents()
panel = window._results_panel

check("there is a Make bundle button", hasattr(panel, "make_bundle_btn"), "")
check("it says what it makes", "bundle" in panel.make_bundle_btn.text().lower(),
      panel.make_bundle_btn.text())
check("pressing it reaches the window",
      callable(getattr(window, "_on_make_bundle", None)), "")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # The reason the button exists is a run that finished weeks ago and now
    # needs sending. That session has no run in it and no reason to have set
    # the Data tab — so the button has to stay live and ask, the way Open
    # bundle… does. Disabling it here refuses exactly the case it was for.
    window._last_output_root = None
    window._last_bundle = None
    window._data_panel.output_data_folder.set_value("")
    window._refresh_results_target()
    check("with no run in the session the button is still live — it asks",
          panel.make_bundle_btn.isEnabled(), "")
    check("...and the label says so, since View report beside it is dead",
          "Make bundle" in panel.target_label.text(), panel.target_label.text())

    run = make_output_folder(tmp / "OutputData02Jan2026")
    window._last_output_root = run
    window._refresh_results_target()
    check("an existing output folder leaves it live",
          panel.make_bundle_btn.isEnabled(), "")

    # An express run's folder is removed once its bundle reads back, so
    # _last_output_root is the bundle itself. There is nothing to pack, but the
    # button still asks rather than going dead.
    window._last_output_root = tmp / "GoneExpressRun.meanap"
    window._refresh_results_target()
    check("a run whose folder is gone still leaves the button live",
          panel.make_bundle_btn.isEnabled(), "")

    # Packing is the one thing that turns it off, and only while it runs.
    window._last_output_root = run
    window._refresh_results_target()
    panel.set_bundling(True)
    check("while packing, the button says so and refuses a second press",
          not panel.make_bundle_btn.isEnabled()
          and "Packing" in panel.make_bundle_btn.text(),
          panel.make_bundle_btn.text())
    panel.set_bundling(False)
    check("and comes back afterwards",
          panel.make_bundle_btn.isEnabled()
          and "Make bundle" in panel.make_bundle_btn.text(),
          panel.make_bundle_btn.text())


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All folder-to-bundle checks passed.")
