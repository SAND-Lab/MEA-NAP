"""Test CAT-NAP (suite2p calcium imaging) parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_catnap.py

Ground truth comes from a complete MATLAB CAT-NAP run kept in the gitignored
``local/`` folder (see ``python/CATNAP_PORT_PLAN.md``). Because that data is not
committed, this test **skips gracefully** when the dataset is absent — so it is
a no-op in CI and a real parity check on a dev machine that has the folder.

Both ground-truth ``.mat`` files are MATLAB v7 (not v7.3/HDF5), so they load
with ``scipy.io.loadmat`` — no ``h5py``, no MATLAB needed.

Phase 0 (this file today) validates the *parity contract*: that the dataset is
present, loadable, and carries every field the port will be checked against,
with the expected shapes. Numeric assertions for each port phase are added as
that phase lands:

  - Phase 3 → ``activityStats`` (calTwopActivityStats), exact
  - Phase 2 → ``adjMs`` (suite2pToAdjm), within prob-threshold tolerance;
              ``coords`` / ``activityProperties`` exact
  - Phase 4 → ``NetMet`` end-to-end, within tolerance
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import scipy.io as sio

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# ── Ground-truth dataset (gitignored; may be absent) ──────────────────────────
DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"
SUITE2P_DIR = DATASET_DIR / RECORDING / "suite2p" / "plane0"
CELLTYPE_CSV = DATASET_DIR / RECORDING / (
    f"PutativeCellType_{RECORDING}_PositiveOnly.csv"
)
EXPDATA_MAT = (
    DATASET_DIR / "OutputData22May2026" / "ExperimentMatFiles"
    / f"{RECORDING}_OutputData22May2026.mat"
)
NETMET_MAT = (
    DATASET_DIR / "OutputData22May2026-step-4" / "ExperimentMatFiles"
    / f"{RECORDING}_OutputData22May2026-step-4.mat"
)

# Expected run configuration, from the mat's Params — see CATNAP_PORT_PLAN.md.
EXPECTED_LAGS_MS = [1000, 2500, 5000]
EXPECTED_N_NODES = 253          # after iscell + removeNodesWithNoPeaks filtering
EXPECTED_N_FRAMES = 20000

# activityStats (calTwopActivityStats) — every field the Phase 3 port must produce.
ACTIVITY_STATS_FIELDS = [
    "FR", "FRactive", "FRmean", "FRstd", "FRsem", "FRmedian", "FRiqr",
    "numActiveElec", "ISImean", "ISI",
    "unitHeightMean", "unitPeakDurMean", "unitEventAreaMean", "unitEventAreaSum",
    "recHeightMean", "recPeakDurMean", "recEventAreaMean",
]
ACTIVITY_PROPERTIES_FIELDS = [
    "cellsWithPeaks", "peakDurationFrames", "peakHeights", "eventAreas",
]


def dataset_available() -> bool:
    return EXPDATA_MAT.exists() and NETMET_MAT.exists() and SUITE2P_DIR.exists()


def _load_mat(path: Path):
    return sio.loadmat(path, struct_as_record=False, squeeze_me=True)


def _extract_spike_times(st_array) -> list[np.ndarray]:
    """MATLAB ``spikeTimes{u}.peak`` cell array → list of 1-D float arrays."""
    out = []
    for u in range(np.size(st_array)):
        peak = getattr(st_array[u], "peak", np.array([]))
        out.append(np.atleast_1d(np.asarray(peak, dtype=float)).ravel())
    return out


def _phase3_activity_stats_checks(exp) -> list[tuple[str, bool, str]]:
    """Phase 3 numeric parity: our calc_twop_activity_stats vs MATLAB activityStats."""
    from meanap.catnap.stats import calc_twop_activity_stats

    P = exp["Params"]
    ap = exp["activityProperties"]
    got = calc_twop_activity_stats(
        twop_activity=str(P.twopActivity),
        duration_s=float(exp["Info"].duration_s),
        fs=float(exp["fs"]),
        min_activity_level=float(P.minActivityLevel),
        spike_times=_extract_spike_times(exp["spikeTimes"]),
        peak_heights=np.asarray(ap.peakHeights, dtype=float),
        peak_duration_frames=np.asarray(ap.peakDurationFrames, dtype=float),
        event_areas=np.asarray(ap.eventAreas, dtype=float),
    )

    ref = exp["activityStats"]
    # field → absolute tolerance. Rounded scalars are exact; arrays 1e-6.
    tol = {
        "FR": 1e-6, "FRactive": 1e-6, "ISI": 1e-6,
        "unitHeightMean": 1e-6, "unitPeakDurMean": 1e-6,
        "unitEventAreaMean": 1e-6, "unitEventAreaSum": 1e-6,
        "FRmean": 1e-9, "FRstd": 1e-9, "FRsem": 1e-9,
        "FRmedian": 1e-9, "FRiqr": 1e-9, "numActiveElec": 0.0,
        "ISImean": 1e-6, "recHeightMean": 1e-6,
        "recPeakDurMean": 1e-6, "recEventAreaMean": 1e-6,
    }
    results = []
    for field, atol in tol.items():
        py = np.asarray(got[field], dtype=float)
        ml = np.asarray(getattr(ref, field), dtype=float)
        ok = np.allclose(py, ml, atol=atol, equal_nan=True) and py.shape == ml.shape
        detail = ""
        if not ok:
            if py.shape != ml.shape:
                detail = f"shape py{py.shape} vs ml{ml.shape}"
            else:
                detail = f"max|diff|={np.nanmax(np.abs(py - ml)):.3e}"
        results.append((f"activityStats.{field}", ok, detail))
    return results


def _phase3_cell_type_checks(exp) -> list[tuple[str, bool, str]]:
    """Phase 3: get_cell_type_matrix logic against the PositiveOnly CSV.

    No MATLAB cellTypeMatrix is saved in the mat (Info.CellTypes is an opaque
    MCOS table), so we verify the invariant independently: each cell type's
    column sum must equal the count of its (0-indexed CSV id + 1) values that
    land in ``channels``, and every marked entry sits on the right row.
    """
    import pandas as pd
    from meanap.catnap.stats import get_cell_type_matrix

    df = pd.read_csv(CELLTYPE_CSV)
    cell_type_ids = {c: df[c].to_numpy(dtype=float) for c in df.columns}
    channels = np.asarray(exp["channels"]).ravel().astype(int)
    chan_set = set(channels.tolist())

    matrix, names = get_cell_type_matrix(cell_type_ids, channels)
    results = []

    results.append(("cellTypeMatrix shape (n_chan, n_types)",
                    matrix.shape == (channels.size, len(df.columns)),
                    f"got {matrix.shape}"))
    results.append(("cellTypeMatrix names match CSV columns",
                    names == list(df.columns), f"got {names}"))

    for col, name in enumerate(df.columns):
        ids = df[name].to_numpy(dtype=float)
        ids = (ids[~np.isnan(ids)].astype(int) + 1)  # 0-idx CSV → 1-idx ROI
        expected = len({r for r in ids if r in chan_set})
        got = int(matrix[:, col].sum())
        results.append((f"cellType[{name}] count={expected}",
                        got == expected, f"got {got}"))
    return results


def _phase2_adjm_checks(exp) -> list[tuple[str, bool, str]]:
    """Phase 2 parity: suite2p_to_adjm vs MATLAB suite2pToAdjm.

    Deterministic outputs (coords, channels, spike_times, activity_properties)
    are checked exactly. The peaks adjacency is RNG-thresholded, so we can't
    match MATLAB's stored ``adjMci`` bit-for-bit — but thresholding only ever
    *zeroes* edges, so every **nonzero** entry of MATLAB's matrix must equal the
    deterministic raw STTC. We recompute raw STTC (``get_sttc``) on the recovered
    peak times and check exactly on that surviving-edge mask.
    """
    from meanap.catnap.loader import load_suite2p
    from meanap.catnap.adjacency import suite2p_to_adjm
    from meanap.pipeline.sttc import get_sttc

    P = exp["Params"]
    lags = list(np.ravel(np.asarray(P.FuncConLagval)).astype(int))

    data = load_suite2p(SUITE2P_DIR)
    # rep_num=2 keeps this fast: the deterministic outputs we compare here don't
    # depend on it, and we recompute raw STTC separately below for the adjacency.
    res = suite2p_to_adjm(
        data, "peaks", [lags[0]],
        remove_nodes_with_no_peaks=bool(P.removeNodesWithNoPeaks),
        prob_thresh_tail=float(P.ProbThreshTail),
        prob_thresh_rep_num=2,
        rng=np.random.default_rng(0),
    )
    results = []

    # ── coords / channels (exact) ─────────────────────────────────────────────
    ml_coords = np.asarray(exp["coords"], dtype=float)
    results.append(("coords match (exact)",
                    res.coords.shape == ml_coords.shape
                    and np.allclose(res.coords, ml_coords, atol=1e-6),
                    f"py{res.coords.shape} vs ml{ml_coords.shape}"))
    ml_channels = np.asarray(exp["channels"]).ravel().astype(int)
    results.append(("channels match (exact)",
                    res.channels.shape == ml_channels.shape
                    and np.array_equal(res.channels, ml_channels),
                    f"py{res.channels.shape} vs ml{ml_channels.shape}"))

    # ── activityProperties (exact) ────────────────────────────────────────────
    ap = exp["activityProperties"]
    for pykey, mlkey in [("peakHeights", "peakHeights"),
                         ("peakDurationFrames", "peakDurationFrames"),
                         ("eventAreas", "eventAreas")]:
        py = np.asarray(res.activity_properties[pykey], dtype=float)
        ml = np.asarray(getattr(ap, mlkey), dtype=float)
        ok = py.shape == ml.shape and np.allclose(py, ml, atol=1e-6, equal_nan=True)
        results.append((f"activityProperties.{pykey} (exact)", ok,
                        f"py{py.shape} vs ml{ml.shape}"))
    ml_cwp = np.asarray(getattr(ap, "cellsWithPeaks")).ravel().astype(int)
    results.append(("activityProperties.cellsWithPeaks (exact)",
                    np.array_equal(res.activity_properties["cellsWithPeaks"], ml_cwp),
                    ""))

    # ── spikeTimes (exact) ────────────────────────────────────────────────────
    ml_st = _extract_spike_times(exp["spikeTimes"])
    st_ok = len(res.spike_times) == len(ml_st) and all(
        py.shape == ml.shape and np.allclose(py, ml, atol=1e-6)
        for py, ml in zip(res.spike_times, ml_st)
    )
    results.append((f"spikeTimes match all {len(ml_st)} units (exact)", st_ok, ""))

    # ── adjMs: raw STTC on surviving (nonzero) edges (exact) ───────────────────
    n = len(res.spike_times)
    st_dict = {u: res.spike_times[u] for u in range(n)}
    duration_s = res.F.shape[0] / res.fs
    adjMs = exp["adjMs"]
    for lag in lags:
        ml_adj = np.asarray(getattr(adjMs, f"adjM{lag}mslag"), dtype=float)
        raw = get_sttc(st_dict, n, lag, duration_s)
        mask = np.isfinite(ml_adj) & (ml_adj != 0.0)
        n_edges = int(mask.sum())
        ok = n_edges > 0 and np.allclose(raw[mask], ml_adj[mask], atol=1e-6)
        detail = ""
        if not ok and n_edges:
            detail = f"max|diff|={np.nanmax(np.abs(raw[mask] - ml_adj[mask])):.3e}"
        results.append((f"adjM{lag}mslag STTC on {n_edges} surviving edges (exact)",
                        ok, detail))
    return results


def _phase4_netmet_checks(exp, net) -> list[tuple[str, bool, str]]:
    """Phase 4 parity: shared step-4 compute_network_metrics on the CAT-NAP
    adjacency vs MATLAB's stored NetMet.

    Same isolation strategy as test_pipeline_step4.py: feed the MATLAB stored
    (thresholded) adjMs — not Python's own RNG-thresholded ones — so we test the
    step-4 arithmetic on the CAT-NAP handoff (spike_counts from peak counts,
    duration, active-node inclusion), not the stochastic thresholding. Only
    deterministic NetMet fields are compared (CC/PL are null-model normalized).
    """
    from meanap.pipeline.step4 import compute_network_metrics

    # Everything here must come from the SAME mat as NetMet (the step-4 mat):
    # its adjMs and spikeTimes are that run's own RNG realization, and NetMet was
    # computed from them. (The full-run mat has different RNG-thresholded adjMs.)
    P = net["Params"]
    lags = list(np.ravel(np.asarray(P.FuncConLagval)).astype(int))
    duration_s = float(net["Info"].duration_s)
    min_activity = float(P.minActivityLevel)
    exclude_edges = bool(P.excludeEdgesBelowThreshold)

    spike_counts = np.array([np.size(st) for st in _extract_spike_times(net["spikeTimes"])],
                            dtype=float)
    adjMs = net["adjMs"]
    netmet = net["NetMet"]

    # (field, tolerance) — deterministic metrics only.
    scalar_fields = [("aN", 0.0), ("Dens", 1e-6), ("Eglob", 1e-6),
                     ("NDmean", 1e-4), ("NSmean", 1e-4), ("ElocMean", 1e-5),
                     ("sigEdgesMean", 1e-5)]
    array_fields = [("ND", 1e-6), ("NS", 1e-6), ("MEW", 1e-6),
                    ("Eloc", 1e-5), ("BC", 1e-4)]

    results = []
    for lag in lags:
        ml = getattr(netmet, f"adjM{lag}mslag")
        ml_aN = int(np.ravel(ml.aN)[0])
        adj = np.asarray(getattr(adjMs, f"adjM{lag}mslag"), dtype=float)
        # min_nodes = ml_aN so metrics compute but the slow, stochastic
        # small-worldness block (gated on a_n > min_nodes) is skipped.
        got = compute_network_metrics(
            adj, spike_counts, duration_s, min_activity, ml_aN,
            exclude_edges_below_threshold=exclude_edges, params=None,
        )
        ok_aN = int(got.get("aN", -1)) == ml_aN
        results.append((f"[{lag}ms] aN == {ml_aN}", ok_aN,
                        f"got {got.get('aN')}"))
        if not ok_aN:
            continue  # arrays won't align; other checks meaningless
        for field, atol in scalar_fields:
            if field == "aN":
                continue
            py = float(np.ravel(np.asarray(got.get(field, np.nan)))[0])
            mlv = float(np.ravel(np.asarray(getattr(ml, field)))[0])
            ok = np.allclose(py, mlv, atol=atol, equal_nan=True)
            results.append((f"[{lag}ms] {field}", ok,
                            "" if ok else f"py={py:.6g} ml={mlv:.6g}"))
        for field, atol in array_fields:
            py = np.asarray(got.get(field), dtype=float)
            mlv = np.asarray(getattr(ml, field), dtype=float)
            ok = py.shape == mlv.shape and np.allclose(py, mlv, atol=atol, equal_nan=True)
            results.append((f"[{lag}ms] {field}", ok,
                            "" if ok else (f"shape py{py.shape} ml{mlv.shape}"
                                           if py.shape != mlv.shape
                                           else f"max|diff|={np.nanmax(np.abs(py-mlv)):.2e}")))
    return results


def main() -> int:
    print("=" * 70)
    print("MEA-NAP Python  ▸  CAT-NAP (suite2p) Parity Test")
    print("=" * 70)

    if not dataset_available():
        print("\n  ! CAT-NAP ground-truth dataset not found under")
        print(f"    {DATASET_DIR}")
        print("    (this data is gitignored — see python/CATNAP_PORT_PLAN.md)")
        print("\n  → SKIPPED (no dataset). This is expected in CI.")
        return 0

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    # ── Load ground truth ─────────────────────────────────────────────────────
    exp = _load_mat(EXPDATA_MAT)
    net = _load_mat(NETMET_MAT)

    # ── Config sanity ─────────────────────────────────────────────────────────
    P = exp["Params"]
    check("suite2pMode == 1", int(P.suite2pMode) == 1, f"got {P.suite2pMode}")
    check("twopActivity == 'peaks'", str(P.twopActivity) == "peaks",
          f"got {P.twopActivity!r}")
    lags = list(np.ravel(np.asarray(P.FuncConLagval)).astype(int))
    check(f"FuncConLagval == {EXPECTED_LAGS_MS}", lags == EXPECTED_LAGS_MS,
          f"got {lags}")

    # ── adjMs: Phase 2 target ─────────────────────────────────────────────────
    adjMs = exp["adjMs"]
    for lag in EXPECTED_LAGS_MS:
        field = f"adjM{lag}mslag"
        has = field in adjMs._fieldnames
        check(f"adjMs.{field} present", has)
        if has:
            A = np.asarray(getattr(adjMs, field))
            check(f"adjMs.{field} shape {EXPECTED_N_NODES}²",
                  A.shape == (EXPECTED_N_NODES, EXPECTED_N_NODES),
                  f"got {A.shape}")

    # ── coords / channels / traces: Phase 2 targets ───────────────────────────
    coords = np.asarray(exp["coords"])
    check(f"coords shape ({EXPECTED_N_NODES}, 2)",
          coords.shape == (EXPECTED_N_NODES, 2), f"got {coords.shape}")
    check("coords normalized to [0, 8]",
          coords.min() >= -1e-9 and coords.max() <= 8 + 1e-6,
          f"range [{coords.min():.3f}, {coords.max():.3f}]")
    check(f"channels length {EXPECTED_N_NODES}",
          np.size(exp["channels"]) == EXPECTED_N_NODES)
    for name in ("F", "denoisedF", "spks"):
        arr = np.asarray(exp[name])
        check(f"{name} shape ({EXPECTED_N_FRAMES}, {EXPECTED_N_NODES})",
              arr.shape == (EXPECTED_N_FRAMES, EXPECTED_N_NODES),
              f"got {arr.shape}")

    # ── spikeTimes: cell array of structs with .peak (seconds) ────────────────
    st = exp["spikeTimes"]
    check(f"spikeTimes length {EXPECTED_N_NODES}",
          np.size(st) == EXPECTED_N_NODES, f"got {np.size(st)}")
    check("spikeTimes[0] has .peak field",
          "peak" in getattr(st[0], "_fieldnames", []))

    # ── activityProperties: Phase 2 target ────────────────────────────────────
    ap = exp["activityProperties"]
    for f in ACTIVITY_PROPERTIES_FIELDS:
        check(f"activityProperties.{f} present", f in ap._fieldnames)

    # ── activityStats: Phase 3 target ─────────────────────────────────────────
    stats = exp["activityStats"]
    for f in ACTIVITY_STATS_FIELDS:
        check(f"activityStats.{f} present", f in stats._fieldnames)

    # ── NetMet: Phase 4 target (shared step 4) ────────────────────────────────
    netmet = net["NetMet"]
    for lag in EXPECTED_LAGS_MS:
        check(f"NetMet.adjM{lag}mslag present",
              f"adjM{lag}mslag" in netmet._fieldnames)

    # ── Cell types CSV present (Phase 3 getCellTypeMatrix) ────────────────────
    check("cell-type CSV present", CELLTYPE_CSV.exists(),
          str(CELLTYPE_CSV.relative_to(REPO_ROOT)))

    # ── Report: parity contract ───────────────────────────────────────────────
    print(f"\nDataset: {DATASET_DIR.relative_to(REPO_ROOT)}")
    print(f"Recording: {RECORDING}\n")
    print("Parity contract (dataset fields & shapes):")
    n_pass = sum(ok for _, ok, _ in checks)
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
    print(f"  → {n_pass}/{len(checks)} passed")

    # ── Phase 3: activityStats numeric parity ─────────────────────────────────
    print("\nPhase 3 — calTwopActivityStats numeric parity:")
    phase3 = _phase3_activity_stats_checks(exp)
    p3_pass = sum(ok for _, ok, _ in phase3)
    for name, ok, detail in phase3:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
    print(f"  → {p3_pass}/{len(phase3)} passed")

    # ── Phase 3: getCellTypeMatrix logic ──────────────────────────────────────
    print("\nPhase 3 — getCellTypeMatrix logic:")
    phase3ct = _phase3_cell_type_checks(exp)
    p3ct_pass = sum(ok for _, ok, _ in phase3ct)
    for name, ok, detail in phase3ct:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
    print(f"  → {p3ct_pass}/{len(phase3ct)} passed")

    # ── Phase 2: suite2p_to_adjm parity ───────────────────────────────────────
    print("\nPhase 2 — suite2pToAdjm parity (deterministic outputs + raw STTC):")
    phase2 = _phase2_adjm_checks(exp)
    p2_pass = sum(ok for _, ok, _ in phase2)
    for name, ok, detail in phase2:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
    print(f"  → {p2_pass}/{len(phase2)} passed")

    # ── Phase 4: NetMet parity (shared step 4 on CAT-NAP handoff) ─────────────
    print("\nPhase 4 — NetMet parity (compute_network_metrics on MATLAB adjMs):")
    phase4 = _phase4_netmet_checks(exp, net)
    p4_pass = sum(ok for _, ok, _ in phase4)
    for name, ok, detail in phase4:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
    print(f"  → {p4_pass}/{len(phase4)} passed")

    total_pass = n_pass + p3_pass + p3ct_pass + p2_pass + p4_pass
    total = len(checks) + len(phase3) + len(phase3ct) + len(phase2) + len(phase4)
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    if total_pass == total:
        print("  → CAT-NAP contract + Phase 3 (activityStats) match MATLAB.")
    else:
        print("  → FAILURES above — see details.")
    print("=" * 70)

    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
