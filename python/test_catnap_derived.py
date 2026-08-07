"""Test CAT-NAP against raw data it may not own: read-only, shared, or remote.

Run from the repo root::

    uv run python python/test_catnap_derived.py

Three changes, all aimed at making a suite2p folder something the pipeline only
ever *reads*, and reads once:

  A. **Derived files leave the raw folder.** Denoising wrote six ``.npy`` files
     into the suite2p directory. Against read-only data that fails; against a
     remote mount it silently uploads ~48 MB per recording back to the source.
  B. **``ops.npy`` is not re-read.** It is a pickle — 493 MB in the example
     dataset, the largest file in a suite2p folder — and must be read whole to
     reach the two fields the pipeline wants. Now cached in a small sidecar.
  C. **The raw folder is opened once per recording.** Phase 3 used to re-open it
     purely for the mean-projection backdrop; phase 1 now captures that.

(C) is the one that decides whether a batch can stream through bounded local
storage, so it is checked by counting reads, not by inspection.

Everything runs on a synthetic suite2p folder; no example dataset needed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.derived import (  # noqa: E402
    DENOISING_OUTPUTS, OPS_CACHE_NAME, derived_dir, resolve_read,
)
from meanap.catnap.loader import load_suite2p  # noqa: E402

Check = tuple[str, bool, str]

N_CELLS, N_FRAMES = 6, 400


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        print(f"  {flag} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _make_suite2p(root: Path, *, mean_img: bool = True) -> Path:
    """A minimal but valid plane0 folder."""
    d = root / "rec1" / "suite2p" / "plane0"
    d.mkdir(parents=True)
    rng = np.random.default_rng(0)
    np.save(d / "F.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32) + 1.0)
    np.save(d / "spks.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32))
    np.save(d / "iscell.npy", np.column_stack(
        [np.ones(N_CELLS), np.ones(N_CELLS)]))
    stat = np.array([{"med": [int(rng.integers(0, 64)), int(rng.integers(0, 64))]}
                     for _ in range(N_CELLS)], dtype=object)
    np.save(d / "stat.npy", stat, allow_pickle=True)
    ops = {"fs": 30.0}
    if mean_img:
        ops["meanImgE"] = rng.random((64, 64))
    np.save(d / "ops.npy", np.array(ops, dtype=object), allow_pickle=True)
    return d


# ── A: derived files leave the raw folder ─────────────────────────────────────


def _derived_location_checks() -> list[Check]:
    from meanap.catnap.denoising import process_suite2p_folder

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp)
        derived = tmp / "derived"

        out = process_suite2p_folder(plane0, derived_root=derived, recording="rec1")
        checks.append(("denoising writes under the derived root",
                       out == derived_dir(derived, "rec1"), f"{out}"))
        written = {p.name for p in out.glob("*.npy")}
        checks.append(("all six outputs land there",
                       set(DENOISING_OUTPUTS) <= written,
                       f"{sorted(set(DENOISING_OUTPUTS) - written)}"))
        stray = [p.name for p in plane0.glob("*.npy")
                 if p.name in DENOISING_OUTPUTS]
        checks.append(("the raw folder is left untouched", not stray, f"{stray}"))

        data = load_suite2p(plane0, derived, "rec1")
        checks.append(("the loader finds them in the derived root",
                       data.F_denoised is not None
                       and data.peak_start_frames is not None, ""))

        # A second call must not redo the work.
        again = process_suite2p_folder(plane0, derived_root=derived, recording="rec1")
        checks.append(("already-denoised is not redone", again == out, f"{again}"))

    with tempfile.TemporaryDirectory() as tmp:
        # No derived root: the historical behaviour, unchanged.
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp)
        process_suite2p_folder(plane0)
        in_place = {p.name for p in plane0.glob("*.npy")}
        checks.append(("without a derived root, outputs stay in place",
                       set(DENOISING_OUTPUTS) <= in_place, ""))
        checks.append(("…and load without one too",
                       load_suite2p(plane0).F_denoised is not None, ""))

    with tempfile.TemporaryDirectory() as tmp:
        # A dataset that already carries denoising output must not be redone
        # just because a derived root is now configured.
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp)
        process_suite2p_folder(plane0)
        derived = tmp / "derived"
        where = process_suite2p_folder(plane0, derived_root=derived, recording="rec1")
        checks.append(("pre-existing in-folder outputs are reused, not redone",
                       where == plane0, f"{where}"))
        checks.append(("…and are still what the loader reads",
                       load_suite2p(plane0, derived, "rec1").F_denoised is not None, ""))
    return checks


# ── B: ops.npy is read once ───────────────────────────────────────────────────


def _ops_cache_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp)
        derived = tmp / "derived"

        first = load_suite2p(plane0, derived, "rec1")
        cache = resolve_read(plane0, derived, "rec1", OPS_CACHE_NAME)
        checks.append(("a sidecar is written on first read",
                       cache is not None and cache.parent == derived_dir(derived, "rec1"),
                       f"{cache}"))
        checks.append(("the sidecar is far smaller than ops.npy",
                       cache.stat().st_size < (plane0 / "ops.npy").stat().st_size,
                       f"{cache.stat().st_size} vs {(plane0/'ops.npy').stat().st_size}"))

        # Delete ops.npy: a second load must succeed purely from the cache.
        (plane0 / "ops.npy").unlink()
        second = load_suite2p(plane0, derived, "rec1")
        checks.append(("a second load does not need ops.npy", True, ""))
        checks.append(("fs is identical", second.fs == first.fs,
                       f"{second.fs} vs {first.fs}"))
        checks.append(("the mean image is identical",
                       np.array_equal(np.asarray(second.mean_img, dtype=np.float32),
                                      np.asarray(first.mean_img, dtype=np.float32)), ""))

    with tempfile.TemporaryDirectory() as tmp:
        # A stale cache must lose to a newer ops.npy (suite2p was re-run).
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp)
        derived = tmp / "derived"
        load_suite2p(plane0, derived, "rec1")
        cache = resolve_read(plane0, derived, "rec1", OPS_CACHE_NAME)
        import os
        old = cache.stat().st_mtime
        os.utime(cache, (old - 100, old - 100))
        np.save(plane0 / "ops.npy",
                np.array({"fs": 99.0, "meanImgE": np.zeros((8, 8))}, dtype=object),
                allow_pickle=True)
        checks.append(("a stale cache is ignored for a newer ops.npy",
                       load_suite2p(plane0, derived, "rec1").fs == 99.0, ""))

    with tempfile.TemporaryDirectory() as tmp:
        # No mean image in ops: must not crash, and must cache the absence.
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp, mean_img=False)
        derived = tmp / "derived"
        a = load_suite2p(plane0, derived, "rec1")
        (plane0 / "ops.npy").unlink()
        b = load_suite2p(plane0, derived, "rec1")
        checks.append(("an ops without a mean image round-trips",
                       a.mean_img is None and b.mean_img is None and b.fs == a.fs, ""))
    return checks


# ── C: the raw folder is opened once per recording ────────────────────────────


def _single_pass_checks() -> list[Check]:
    """Count reads of the raw folder across a whole run.

    This is the property the remote-streaming work depends on: if a recording's
    raw data is needed twice, separated by the batch-wide cartography barrier, a
    bounded cache has to evict and re-fetch it.
    """
    import pandas as pd

    from meanap.catnap import pipeline as cp
    from meanap.params import Params
    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.spreadsheet import RecordingInfo

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _make_suite2p(tmp)
        pd.DataFrame([{"Recording filename": "rec1", "DIV": 21, "Group": "WT"}]
                     ).to_csv(tmp / "batch.csv", index=False)

        calls: list[str] = []
        real = cp.load_suite2p

        def counting(plane0, *a, **kw):
            calls.append(str(plane0))
            return real(plane0, *a, **kw)

        cp.load_suite2p = counting
        try:
            for traces, label in ((0, "no traces"), (2, "with traces")):
                calls.clear()
                out = create_output_folders(tmp, f"Out{traces}", ["WT"])
                params = Params(
                    suite2p_mode=True, raw_data=str(tmp),
                    derived_data_folder=str(tmp / "derived"),
                    twop_activity="F", func_con_lag_val=[25],
                    min_activity_level=0.0, min_number_of_nodes_to_cal_net_met=2,
                    twop_subnetwork_analysis=False, num_2p_traces=traces,
                    twop_network_background=True,
                    auto_set_cartography_boundaries=False, random_seed=1,
                    output_data_folder=str(tmp), output_data_folder_name=f"Out{traces}",
                )
                cp.run_catnap_pipeline(
                    params, [RecordingInfo(filename="rec1", div=21.0, group="WT")],
                    out, lambda m: None)
                expected = 1 if traces == 0 else 2
                checks.append((f"raw folder opened {expected}x ({label})",
                               len(calls) == expected, f"got {len(calls)}"))
                if traces == 0:
                    bg = (out / "ExperimentMatFiles" / "rec1_background.npz")
                    checks.append(("…and the backdrop was still captured",
                                   bg.exists(), ""))
        finally:
            cp.load_suite2p = real

        stray = [p.name for p in (tmp / "rec1" / "suite2p" / "plane0").glob("*.npy")
                 if p.name in DENOISING_OUTPUTS or p.name == OPS_CACHE_NAME]
        checks.append(("a full run writes nothing into the raw folder",
                       not stray, f"{stray}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP against read-only / remote raw data")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — derived files leave the raw folder:", _derived_location_checks),
        ("B — ops.npy is read once, then cached:", _ops_cache_checks),
        ("C — the raw folder is opened once per recording:", _single_pass_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
