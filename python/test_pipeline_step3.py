"""Test pipeline Step 3 — functional connectivity (STTC) parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_step3.py

Two things are validated, since MATLAB's own pipeline only ever persists the
*stochastically thresholded* adjacency matrix (never bit-reproducible — see
``probabilistic_threshold.py``'s docstring):

1. **Exact parity** of the deterministic, unthresholded STTC computation
   (``meanap.pipeline.sttc.get_sttc``) against ``get_sttc.m`` reference
   matrices in ``python/test_fixtures/`` (generated once via MATLAB directly
   — see ``python/test_fixtures/gen_sttc_reference.m`` — using the MATLAB
   reference spike times, same isolation strategy as
   ``test_pipeline_step2.py``).
2. **Structural sanity** of the probabilistic thresholding
   (``meanap.pipeline.probabilistic_threshold.adjm_thr``): thresholding only
   ever removes edges (never adds or strengthens one), and the result is
   symmetric with a zero diagonal.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.io import load_spike_times_mat
from meanap.pipeline.probabilistic_threshold import adjm_thr
from meanap.pipeline.sttc import get_sttc


MATLAB_SPIKE_DIR = REPO_ROOT / "OutputData03Mar2026" / "1_SpikeDetection" / "1A_SpikeDetectedData"
FIXTURE_DIR = REPO_ROOT / "python" / "test_fixtures"

RECORDINGS = [
    "NGN2_20230208_P1_DIV14_A2",
    "NGN2_20230208_P1_DIV14_A3",
]

LAGS_MS = [10, 25, 50]
SPIKES_METHOD = "bior1p5"
FS = 12500.0
DURATION_S = 600.0
N_CHANNELS = 64


def test_deterministic_sttc() -> bool:
    print(f"\n{'=' * 70}")
    print("[1] Deterministic STTC parity (vs MATLAB get_sttc.m fixtures)")
    print(f"{'=' * 70}")

    all_ok = True
    for rec_name in RECORDINGS:
        fixture_path = FIXTURE_DIR / f"{rec_name}_sttc_reference.npz"
        if not fixture_path.exists():
            print(f"  ! Fixture not found: {fixture_path} — skipping {rec_name}")
            all_ok = False
            continue

        spike_path = MATLAB_SPIKE_DIR / f"{rec_name}_spikes.mat"
        matlab_spikes = load_spike_times_mat(spike_path)
        spike_times_dict = {
            ch: matlab_spikes.get(ch, {}).get(SPIKES_METHOD, np.array([]))
            for ch in range(N_CHANNELS)
        }

        fixture = np.load(fixture_path)

        print(f"\n  Recording: {rec_name}")
        for lag_ms in LAGS_MS:
            adj_m = get_sttc(spike_times_dict, N_CHANNELS, lag_ms, DURATION_S)
            ref = fixture[f"adjM_{lag_ms}ms"]
            max_diff = np.abs(adj_m - ref).max()
            ok = np.allclose(adj_m, ref, atol=1e-6)
            all_ok &= ok
            flag = "✓" if ok else "✗"
            print(f"    {flag} lag={lag_ms:3d}ms  max|diff|={max_diff:.3e}")

    return all_ok


def test_thresholding_sanity() -> bool:
    print(f"\n{'=' * 70}")
    print("[2] Probabilistic thresholding — structural sanity (not bit-parity)")
    print(f"{'=' * 70}")

    rec_name = RECORDINGS[0]
    spike_path = MATLAB_SPIKE_DIR / f"{rec_name}_spikes.mat"
    matlab_spikes = load_spike_times_mat(spike_path)
    spike_times_dict = {
        ch: matlab_spikes.get(ch, {}).get(SPIKES_METHOD, np.array([]))
        for ch in range(N_CHANNELS)
    }

    print(f"\n  Recording: {rec_name}, lag=10ms, rep_num=50, tail=0.05")
    rng = np.random.default_rng(0)
    t0 = time.time()
    adj_m, adj_m_ci = adjm_thr(
        spike_times_dict, N_CHANNELS, lag_ms=10, tail=0.05,
        fs=FS, duration_s=DURATION_S, rep_num=50, rng=rng,
    )
    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s")

    checks = {
        "symmetric (raw)": np.allclose(adj_m, adj_m.T),
        "symmetric (thresholded)": np.allclose(adj_m_ci, adj_m_ci.T),
        "zero diagonal (raw)": np.allclose(np.diag(adj_m), 0.0),
        "zero diagonal (thresholded)": np.allclose(np.diag(adj_m_ci), 0.0),
        "thresholding only removes edges": np.all(
            (adj_m_ci == adj_m) | (adj_m_ci == 0.0)
        ),
        "thresholded edge count <= raw": int((adj_m_ci > 0).sum()) <= int((adj_m > 0).sum()),
    }

    n_raw = int((adj_m > 0).sum())
    n_thr = int((adj_m_ci > 0).sum())
    print(f"  nonzero edges: raw={n_raw}  thresholded={n_thr}")

    all_ok = True
    for name, ok in checks.items():
        all_ok &= ok
        print(f"    {'✓' if ok else '✗'} {name}")

    return all_ok


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Step 3: Functional Connectivity (STTC) Parity Test")
    print("=" * 70)

    ok1 = test_deterministic_sttc()
    ok2 = test_thresholding_sanity()

    print(f"\n{'=' * 70}")
    if ok1 and ok2:
        print("  → All checks passed")
    else:
        print("  → Some checks FAILED — see above")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
