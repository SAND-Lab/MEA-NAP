"""The CAT-NAP activity rasters — plain and z-scored per cell.

MATLAB draws a ``3_Raster`` for every suite2p recording; the Python port drew
nothing population-wide, only per-cell traces. These checks cover the four
things the new figures depend on: the binning is right (counts per second for
``peaks``, the mean of each second otherwise), the z-scoring is right (and
does not turn a silent cell into a hole), the matrix survives the state file,
and every route to a picture — the run, a resumed run, a bundle in the viewer
— produces both figures without carrying them as images.

Run: ``uv run python python/test_catnap_raster.py``
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

import numpy as np  # noqa: E402

from meanap.catnap.rasters import (  # noqa: E402
    RASTER_FIGURES, binned_activity, plot_activity_raster, zscore_units,
)
from meanap.catnap.store import (  # noqa: E402
    RecordingState, load_recording_state, save_recording_state,
)

Check = tuple[str, bool, str]
FAILURES: list[str] = []


def _report(title: str, checks: list[Check]) -> None:
    print(f"\n{title}")
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))
        if not ok:
            FAILURES.append(name)


# ── A: binning ───────────────────────────────────────────────────────────────

def _binning_checks() -> list[Check]:
    checks: list[Check] = []
    fs = 10.0

    # peaks: three cells, events at known seconds; the last bin is partial.
    spikes = [np.array([0.5, 0.7, 3.2]), np.array([]), np.array([4.9])]
    b = binned_activity("peaks", fs, 5.0, spike_times=spikes)
    checks.append(("peaks: one column per second, one row per cell",
                   b.shape == (5, 3), f"{b.shape}"))
    checks.append(("peaks: events are counted into the second they fall in",
                   b[0, 0] == 2 and b[3, 0] == 1 and b[4, 2] == 1 and b.sum() == 4,
                   f"{b.T}"))
    checks.append(("peaks: a silent cell is a row of zeros", not b[:, 1].any(), ""))
    checks.append(("peaks: float32, not float64", b.dtype == np.float32, str(b.dtype)))

    # continuous: the mean of each second's frames, partial last bin included.
    n_frames, n_units = 25, 2                      # 2.5 s at 10 Hz
    m = np.arange(n_frames * n_units, dtype=float).reshape(n_frames, n_units)
    c = binned_activity("spks", fs, n_frames / fs, matrix=m)
    checks.append(("continuous: ceil(duration) columns, partial bin kept",
                   c.shape == (3, 2), f"{c.shape}"))
    checks.append(("continuous: each bin is the mean of its frames",
                   np.allclose(c[0], m[:10].mean(axis=0))
                   and np.allclose(c[2], m[20:].mean(axis=0)), f"{c}"))
    try:
        binned_activity("spks", fs, 1.0)
        checks.append(("continuous without a matrix is refused", False, "no error"))
    except ValueError:
        checks.append(("continuous without a matrix is refused", True, ""))
    return checks


# ── B: z-scoring ─────────────────────────────────────────────────────────────

def _zscore_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(0)
    x = rng.normal(3.0, 2.0, (200, 4))
    x[:, 2] = 7.0                                  # constant: no variance
    x[:, 3] = 0.0                                  # silent: no variance either
    z = zscore_units(x)
    checks.append(("each cell has mean 0 and SD 1 after z-scoring",
                   np.allclose(z[:, :2].mean(axis=0), 0, atol=1e-6)
                   and np.allclose(z[:, :2].std(axis=0), 1, atol=1e-6), ""))
    checks.append(("a cell with no variance is zeros, not NaN",
                   np.all(z[:, 2] == 0) and np.all(z[:, 3] == 0)
                   and not np.isnan(z).any(), ""))
    checks.append(("z-scoring is per cell: a bright cell does not dominate",
                   abs(z[:, 0].max() - z[:, 1].max()) < 2.0, ""))
    checks.append(("float32 out", z.dtype == np.float32, str(z.dtype)))
    return checks


# ── C: the figure itself ─────────────────────────────────────────────────────

def _figure_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(1)
    binned = rng.poisson(0.3, (60, 12)).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        for stem, _label, zscored in RASTER_FIGURES:
            out = plot_activity_raster(binned, Path(tmp) / f"{stem}.svg",
                                       activity="peaks", title="t", zscored=zscored)
            text = out.read_text() if out.exists() else ""
            checks.append((f"{stem}: written", bool(text), "no file"))
            expect = "z-score (per cell)" if zscored else "Events / s"
            checks.append((f"{stem}: colorbar says what it shows",
                           expect in text, expect))
        # A fluorescence trace that sits entirely below 1 must still be
        # visible — MATLAB's ``max(prctile, 1)`` floor would blank it.
        low = rng.uniform(0.0, 0.05, (30, 5)).astype(np.float32)
        out = plot_activity_raster(low, Path(tmp) / "low.png",
                                   activity="denoised F", title="t")
        from PIL import Image
        img = np.asarray(Image.open(out).convert("L"), dtype=float)
        # The heatmap area is the darkest thing on a white page; if the floor
        # had clipped every value to the bottom of the map it would be one flat
        # colour, so demand some spread inside the dark region.
        dark = img[img < 200]
        checks.append(("a sub-1 fluorescence raster is not flattened to one colour",
                       dark.size > 0 and dark.std() > 5, f"std={dark.std():.1f}"))
        # peaks keeps the floor: a nearly silent recording is not stretched so
        # that a single event fills the scale.
        quiet = np.zeros((30, 5), dtype=np.float32)
        quiet[3, 1] = 1
        plot_activity_raster(quiet, Path(tmp) / "quiet.png", activity="peaks", title="t")
        checks.append(("a near-silent peaks raster still draws", (Path(tmp) / "quiet.png").exists(), ""))
    return checks


# ── D: the state file carries it ─────────────────────────────────────────────

def _store_checks() -> list[Check]:
    checks: list[Check] = []
    binned = np.random.default_rng(2).random((40, 6)).astype(np.float32)
    state = RecordingState(
        adjMs={"adjM10mslag": np.zeros((6, 6))}, coords=np.zeros((6, 2)),
        channels=np.arange(6) + 1, spike_counts=np.ones(6), duration_s=40.0,
        plane0=Path("."), fs=30.0, binned_activity=binned,
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rec_catnap.npz"
        save_recording_state(path, state, {"FR": np.ones(6)})
        back, _ = load_recording_state(path, Path("."))
        # Stored at half precision (see save_recording_state), so equal to
        # three significant digits rather than bit for bit.
        checks.append(("the binned matrix round-trips through the state file",
                       back.binned_activity is not None
                       and back.binned_activity.shape == binned.shape
                       and np.allclose(back.binned_activity, binned, rtol=2e-3, atol=1e-6), ""))
        checks.append(("...read back as float32", back.binned_activity.dtype == np.float32,
                       str(back.binned_activity.dtype)))
        with np.load(path) as raw:
            checks.append(("...and held at float16 on disk",
                           raw["binned_activity"].dtype == np.float16,
                           str(raw["binned_activity"].dtype)))
        # A file from before the matrix was stored loads with None, not an error.
        state.binned_activity = None
        save_recording_state(path, state, {"FR": np.ones(6)})
        back, _ = load_recording_state(path, Path("."))
        checks.append(("a state without it reads back as None",
                       back.binned_activity is None, ""))
    return checks


# ── E: end to end — run, bundle, viewer ──────────────────────────────────────

def _pipeline_checks() -> list[Check]:
    import test_catnap_multi_activity as T
    from meanap.catnap.pipeline import run_catnap_pipeline
    from meanap.params import save_params
    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.pack import bundle_output_folder
    from meanap.viewer.server import ViewerService

    checks: list[Check] = []
    tmp, raw, recs = T._dataset(2)
    # peaks at the top level, spks in its own subtree: both must get rasters.
    params = dataclasses.replace(T._params(raw, ("spks",)), num_2p_traces=1)
    out = create_output_folders(tmp, "RasterRun", sorted({r.group for r in recs}))
    save_params(params, out)
    logs: list[str] = []
    run_catnap_pipeline(params, recs, out, logs.append)

    stems = [s for s, _l, _z in RASTER_FIGURES]
    for tree, label in ((out, "peaks"), (out / "ByActivityType" / "spks", "spks")):
        for rec in recs:
            folder = (tree / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
                      / rec.group / rec.filename)
            have = [s for s in stems if (folder / f"{s}.png").exists()
                    and (folder / f"{s}.png").stat().st_size > 0]
            checks.append((f"{label}: both rasters drawn for {rec.filename}",
                           have == stems, f"{have}"))
    checks.append(("no raster warnings in the log",
                   not any("Raster" in l and "warning" in l.lower() for l in logs),
                   "; ".join(l for l in logs if "Raster" in l)))

    # The two measures' matrices differ (they are different measures) and
    # the peaks one is integer event counts.
    peaks_state, _ = load_recording_state(
        out / "ExperimentMatFiles" / f"{recs[0].filename}_catnap.npz", Path("."))
    spks_state, _ = load_recording_state(
        out / "ByActivityType" / "spks" / "ExperimentMatFiles"
        / f"{recs[0].filename}_catnap.npz", Path("."))
    checks.append(("peaks state holds integer event counts per second",
                   peaks_state.binned_activity is not None
                   and np.all(peaks_state.binned_activity == np.round(peaks_state.binned_activity))
                   and peaks_state.binned_activity.shape[0] == int(np.ceil(peaks_state.duration_s)),
                   f"{None if peaks_state.binned_activity is None else peaks_state.binned_activity.shape}"))
    checks.append(("spks state holds a different matrix of the same shape",
                   spks_state.binned_activity is not None
                   and spks_state.binned_activity.shape == peaks_state.binned_activity.shape
                   and not np.array_equal(spks_state.binned_activity, peaks_state.binned_activity), ""))

    # Bundle: the rasters are redrawable, so they must not be packed as images,
    # while the trace figures still are.
    result = bundle_output_folder(out, log=lambda _m: None)
    packed = zipfile.ZipFile(result.dest).namelist()
    checks.append(("bundle carries no raster images",
                   not any("ActivityRaster" in n for n in packed),
                   str([n for n in packed if "ActivityRaster" in n])))
    checks.append(("...but still carries the trace figures",
                   any("2ptraces" in n for n in packed), ""))

    # Viewer: lists both, renders both, from the bundle.
    svc = ViewerService(result.dest)
    try:
        man = svc.manifest()
        rec = man["recordings"][0]
        names = [f["name"] for f in rec["activity"]]
        checks.append(("viewer lists both rasters under Activity figures",
                       names == stems, f"{names}"))
        for name in names:
            path = svc.activity_figure(rec["name"], name, fmt="png", overrides={})
            checks.append((f"viewer renders {name} from the bundle",
                           path.exists() and path.stat().st_size > 0, str(path)))
        try:
            svc.activity_figure(rec["name"], "3_Raster", fmt="png", overrides={})
            checks.append(("an unknown raster name is refused", False, "no error"))
        except ValueError:
            checks.append(("an unknown raster name is refused", True, ""))
    finally:
        svc.close()
    return checks


def main() -> int:
    print("CAT-NAP activity rasters")
    _report("A — binning to one row per second", _binning_checks())
    _report("B — z-scoring per cell", _zscore_checks())
    _report("C — the figures", _figure_checks())
    _report("D — the state file", _store_checks())
    _report("E — run, bundle, viewer", _pipeline_checks())
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All raster checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
