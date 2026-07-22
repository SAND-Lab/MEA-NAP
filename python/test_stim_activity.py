"""Parity test: Python stim activity analysis vs MATLAB StimActivity_NodeLevel.csv.

Isolates the stim *analysis* arithmetic from spike detection by feeding MATLAB's
own spikeTimes (from ExperimentMatFiles), exactly as the step-2/3/4 ports do.
Pipeline: detect stim (on raw) -> patterns -> clean spikes -> activity metrics,
then diff every metric column against the reference CSV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.pipeline.io import load_raw_recording, load_spike_times_mat  # noqa: E402
from meanap.stim.detection import detect_stim_times, get_stim_patterns  # noqa: E402
from meanap.stim.cleaning import clean_spikes_from_stim  # noqa: E402
from meanap.stim.activity import stim_activity_analysis  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "local" / "testMEAstim"
OUT = REPO / "local" / "testMEAstim" / "OutputData20Jul2026"

RECORDINGS = ["OWT220207_1H_DIV57_HUB45_3UA", "OWT220207_1H_DIV57_PER72_3UA"]

PARAMS = {
    "stimDetectionMethod": "longblank", "stimDetectionVal": 150,
    "stimRefractoryPeriod": 2.9, "stimDuration": 0.00012, "fs": 25000,
    "minBlankingDuration": 0.004, "stimTimeDiffThreshold": 0.005,
    "postStimWindowDur": 0.5, "SpikesMethod": "bior1p5",
    "stimAnalysisWindow": [-0.03, 0.03],
}

METRIC_COLS = [
    "auc_poststim", "auc_baseline_mean", "auc_corrected",
    "peak_firing_rate_hz", "peak_time_ms", "halfRmax_time_ms",
    "d_prime", "zscore", "median_latency_ms",
]

RTOL, ATOL = 1e-6, 1e-6


def main() -> int:
    ref = pd.read_csv(OUT / "StimActivity_NodeLevel.csv")
    total, worst = 0, {}
    n_fail = 0

    for name in RECORDINGS:
        dat, channels, fs = load_raw_recording(RAW_DIR / f"{name}.mat")
        dat = dat.astype(np.float64)
        coords = np.zeros((dat.shape[1], 2))
        info = detect_stim_times(dat, {**PARAMS, "fs": fs}, channels, coords)
        info, patterns = get_stim_patterns(info, PARAMS)

        mat = OUT / "ExperimentMatFiles" / f"{name}_OutputData20Jul2026.mat"
        spikes = load_spike_times_mat(mat)
        spikes = clean_spikes_from_stim(spikes, info, PARAMS)

        rows = stim_activity_analysis(
            spikes, info, patterns, PARAMS,
            {"FileName": name, "Grp": "WT", "DIV": 57},
        )
        py = pd.DataFrame(rows)
        rf = ref[ref.FileName == name].copy()

        print(f"\n[{name}] python rows={len(py)}  matlab rows={len(rf)}")
        if len(py) != len(rf):
            print("  ROW COUNT MISMATCH")
            py_ch, ml_ch = set(py.channel_id), set(rf.channel_id)
            print("   only-python channels:", sorted(py_ch - ml_ch))
            print("   only-matlab channels:", sorted(ml_ch - py_ch))

        merged = rf.merge(py, on=["channel_id", "pattern_id"], suffixes=("_ml", "_py"))
        for col in METRIC_COLS:
            a = merged[f"{col}_py"].to_numpy(float)
            b = merged[f"{col}_ml"].to_numpy(float)
            both_nan = np.isnan(a) & np.isnan(b)
            ok = both_nan | np.isclose(a, b, rtol=RTOL, atol=ATOL)
            diff = np.abs(a - b)
            diff[both_nan] = 0
            md = float(np.nanmax(diff)) if diff.size else 0.0
            worst[col] = max(worst.get(col, 0.0), md)
            total += len(ok)
            fails = int((~ok).sum())
            n_fail += fails
            flag = "OK" if fails == 0 else f"FAIL({fails})"
            print(f"   {col:22s} {flag:10s} max|Δ|={md:.3e}")
            if fails and fails <= 5:
                idx = np.flatnonzero(~ok)
                for j in idx[:5]:
                    print(f"        ch{int(merged.channel_id.iloc[j])}: py={a[j]:.6g} ml={b[j]:.6g}")

    print(f"\nTOTAL: {total - n_fail}/{total} metric checks passed")
    print("worst |Δ| per column:", {k: f"{v:.2e}" for k, v in worst.items()})
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
