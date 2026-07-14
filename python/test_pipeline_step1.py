"""Test pipeline Step 1 — spike detection parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_step1.py

Downloads example data if not already present (same files the MATLAB test
pipeline uses), runs Python spike detection with the same parameters as the
``OutputData03Mar2026`` MATLAB run, and reports per-channel overlap with the
MATLAB spike times.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.io import load_raw_recording, load_spike_times_mat, save_spike_times_npz
from meanap.pipeline.spike_detection import SpikeDetectionParams, detect_spikes_recording


# ── Example data ──────────────────────────────────────────────────────────────

EXAMPLE_DIR = REPO_ROOT / "ExampleData"
MATLAB_OUTPUT_DIR = REPO_ROOT / "OutputData03Mar2026" / "1_SpikeDetection" / "1A_SpikeDetectedData"
PYTHON_OUTPUT_DIR = REPO_ROOT / "OutputData_Python" / "1_SpikeDetection" / "1A_SpikeDetectedData"

RECORDINGS = [
    "NGN2_20230208_P1_DIV14_A2",
    "NGN2_20230208_P1_DIV14_A3",
]


# ── Overlap metrics ───────────────────────────────────────────────────────────

def spike_overlap(times_a: np.ndarray, times_b: np.ndarray, tol_ms: float = 1.0) -> dict:
    """Compute overlap between two spike-time arrays.

    A Python spike is "matched" if a MATLAB spike falls within ±tol_ms of it.

    Returns dict with precision, recall, F1, n_python, n_matlab.
    """
    tol_s = tol_ms / 1000.0
    if len(times_a) == 0 and len(times_b) == 0:
        return dict(precision=1.0, recall=1.0, f1=1.0, n_python=0, n_matlab=0)
    if len(times_a) == 0 or len(times_b) == 0:
        return dict(precision=0.0, recall=0.0, f1=0.0, n_python=len(times_a), n_matlab=len(times_b))

    a_sorted = np.sort(times_a)
    b_sorted = np.sort(times_b)

    # True positives: for each python spike, is there a matlab spike within tol?
    tp = 0
    j = 0
    for t in a_sorted:
        while j < len(b_sorted) and b_sorted[j] < t - tol_s:
            j += 1
        if j < len(b_sorted) and abs(b_sorted[j] - t) <= tol_s:
            tp += 1

    precision = tp / len(a_sorted) if len(a_sorted) > 0 else 0.0
    recall = tp / len(b_sorted) if len(b_sorted) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return dict(precision=precision, recall=recall, f1=f1,
                n_python=len(a_sorted), n_matlab=len(b_sorted))


# ── Parameters matching the MATLAB OutputData03Mar2026 run ───────────────────

def build_params(fs: float) -> SpikeDetectionParams:
    """Return detection params matching the MATLAB example data run.

    Source: OutputData03Mar2026/Parameters_OutputData03Mar2026.csv
    """
    return SpikeDetectionParams(
        fs=fs,
        thresholds=[4.0, 5.0],
        wname_list=["bior1.5"],
        cost_list=[-0.12],
        spikes_method="bior1p5",
        wid_ms=(0.4, 0.8),
        n_scales=5,
        filter_low_pass=600.0,
        filter_high_pass=6150.0,
        ref_period_ms=1.0,
        min_peak_thr_mult=-5.0,
        max_peak_thr_mult=-100.0,
        pos_peak_thr_mult=15.0,
        remove_artifacts=False,
        unit="s",
        grd=[],
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Step 1: Spike Detection Parity Test")
    print("=" * 70)

    # Step 0: ensure example data is present
    print("\n[0] Checking example data …")
    download_example_data(REPO_ROOT, log=print)

    PYTHON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []

    for rec_name in RECORDINGS:
        print(f"\n{'─' * 60}")
        print(f"Recording: {rec_name}")
        print(f"{'─' * 60}")

        # Load raw data
        raw_path = EXAMPLE_DIR / f"{rec_name}.mat"
        print(f"  Loading raw data from {raw_path.name} …", end=" ", flush=True)
        dat, channels, fs = load_raw_recording(raw_path)
        duration_s = dat.shape[0] / fs
        print(f"done  [{dat.shape[0]} samples × {dat.shape[1]} channels, fs={fs:.0f} Hz, {duration_s:.1f} s]")

        # Run Python spike detection
        params = build_params(fs)
        print(f"  Running spike detection ({len(channels)} channels) …", end=" ", flush=True)
        result = detect_spikes_recording(dat, channels, fs, params)
        n_methods = len(next(iter(result.spike_times.values())))
        print(f"done  [{n_methods} methods × {len(channels)} channels]")

        # Save Python outputs
        out_path = PYTHON_OUTPUT_DIR / f"{rec_name}_spikes.npz"
        save_spike_times_npz(out_path, result.spike_times, channels, fs)
        print(f"  Saved Python outputs → {out_path.relative_to(REPO_ROOT)}")

        # Compare with MATLAB if available
        matlab_path = MATLAB_OUTPUT_DIR / f"{rec_name}_spikes.mat"
        if not matlab_path.exists():
            print(f"  MATLAB output not found at {matlab_path} — skipping comparison.")
            continue

        print(f"  Comparing with MATLAB output …")
        matlab_spikes = load_spike_times_mat(matlab_path)

        for method in ["bior1p5", "thr4", "thr5"]:
            py_times_by_ch = []
            ml_times_by_ch = []
            metrics_by_ch = []

            for ch_idx in sorted(result.spike_times.keys()):
                py_t = result.spike_times[ch_idx].get(method, np.array([]))
                ml_t = matlab_spikes.get(ch_idx, {}).get(method, np.array([]))
                m = spike_overlap(py_t, ml_t, tol_ms=1.0)
                metrics_by_ch.append(m)
                py_times_by_ch.append(py_t)
                ml_times_by_ch.append(ml_t)

            # Aggregate
            n_ch = len(metrics_by_ch)
            avg_f1 = np.mean([m["f1"] for m in metrics_by_ch])
            avg_prec = np.mean([m["precision"] for m in metrics_by_ch])
            avg_recall = np.mean([m["recall"] for m in metrics_by_ch])
            total_py = sum(len(t) for t in py_times_by_ch)
            total_ml = sum(len(t) for t in ml_times_by_ch)

            all_results.append({
                "recording": rec_name,
                "method": method,
                "avg_f1": avg_f1,
                "avg_precision": avg_prec,
                "avg_recall": avg_recall,
                "total_python": total_py,
                "total_matlab": total_ml,
            })

            flag = "✓" if avg_f1 > 0.8 else ("~" if avg_f1 > 0.5 else "✗")
            print(f"    {flag} [{method:10s}]  F1={avg_f1:.3f}  "
                  f"prec={avg_prec:.3f}  recall={avg_recall:.3f}  "
                  f"py={total_py:6d}  ml={total_ml:6d}")

    # Summary table
    if all_results:
        print(f"\n{'=' * 70}")
        print("Summary")
        print(f"{'─' * 70}")
        print(f"{'Recording':<40} {'Method':<12} {'F1':>6} {'Prec':>6} {'Recall':>7}")
        print(f"{'─' * 70}")
        for r in all_results:
            print(f"{r['recording']:<40} {r['method']:<12} "
                  f"{r['avg_f1']:6.3f} {r['avg_precision']:6.3f} {r['avg_recall']:7.3f}")
        print(f"{'=' * 70}")

        overall_f1 = np.mean([r["avg_f1"] for r in all_results])
        print(f"\nOverall mean F1 across all recordings × methods: {overall_f1:.3f}")
        if overall_f1 > 0.8:
            print("  → Good parity with MATLAB")
        elif overall_f1 > 0.5:
            print("  → Moderate parity — wavelet scale differences likely")
        else:
            print("  → Low parity — implementation differences need investigation")

    print(f"\nPython outputs saved to: {PYTHON_OUTPUT_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
