"""Compare MATLAB vs Python spike detection on the parity run.

Reports per-recording spike counts and the match rate within +/-1 ms, plus the
exact per-spike time offset once counts agree.

Note the known, deliberate 2-sample offset: MATLAB's spike times sit 2 samples
after the true negative peak (1-based frames + alignPeaks' off-by-one), the
port's sit on it. See align_peaks()'s docstring / PIPELINE_PORT_STATUS.md.
The +/-1 ms tolerance absorbs it; SHIFT_SAMPLES below removes it exactly.

    uv run python parityRun/compare_spike_detection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.io import load_spike_times_mat, load_spike_times_npz

RECS = ["NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"]
METHODS = ["bior1p5", "thr4", "thr5"]
TOL_S = 0.001  # +/-1 ms
# Known deliberate offset: MATLAB's times = true peak + 2 samples.
SHIFT_SAMPLES = 2


def match_count(py: np.ndarray, ml: np.ndarray, tol: float = TOL_S) -> int:
    """Number of Python spikes with a MATLAB spike within +/-tol."""
    a, b = np.sort(np.asarray(py).ravel()), np.sort(np.asarray(ml).ravel())
    tp, j = 0, 0
    for t in a:
        while j < len(b) and b[j] < t - tol:
            j += 1
        if j < len(b) and abs(b[j] - t) <= tol:
            tp += 1
    return tp


def main() -> None:
    print(f"Spike detection: MATLAB vs Python (tolerance=+/-{TOL_S*1000:g} ms)\n")
    for rec in RECS:
        ml = load_spike_times_mat(
            REPO_ROOT / "parityRun" / "OutputData_MATLAB_parity" / "1_SpikeDetection"
            / "1A_SpikeDetectedData" / f"{rec}_spikes.mat")
        py_path = (REPO_ROOT / "parityRun" / "OutputData_Python_parity"
                   / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz")
        py = load_spike_times_npz(py_path)
        fs = float(np.load(py_path)["fs"].ravel()[0])

        print(rec)
        for method in METHODS:
            n_ml = sum(len(ml[c][method]) for c in ml)
            n_py = sum(len(py[c][method]) for c in py)
            tp = sum(match_count(py[c][method], ml[c][method]) for c in ml)

            precision = tp / n_py if n_py else 0.0
            recall = tp / n_ml if n_ml else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

            # Exact residual after removing the known 2-sample offset — only
            # meaningful where the per-channel counts already agree.
            resid = []
            for c in sorted(ml):
                a = np.sort(np.asarray(py[c][method]).ravel()) + SHIFT_SAMPLES / fs
                b = np.sort(np.asarray(ml[c][method]).ravel())
                if a.shape == b.shape and len(a):
                    resid.append(np.abs(a - b))
            worst = float(np.max(np.concatenate(resid))) if resid else float("nan")

            print(f"  {method:8s} MATLAB={n_ml:6d} Python={n_py:6d} matched={tp:6d}  "
                  f"P={precision:.4f} R={recall:.4f} F1={f1:.4f}  "
                  f"max|Δt| after +{SHIFT_SAMPLES}-sample shift = {worst:.2e} s")
        print()


if __name__ == "__main__":
    main()
