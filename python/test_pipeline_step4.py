"""Test pipeline Step 4 — network metrics parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_step4.py

Only the deterministic metrics in ``meanap.pipeline.network_metrics`` are
checked here (see that module's docstring for what's out of scope — anything
depending on randomized null models or community detection).

To isolate Step 4's arithmetic from Step 3's inherent stochasticity (its
significance thresholding is not bit-reproducible against MATLAB — see
``probabilistic_threshold.py``), this test feeds Step 4 the *actual MATLAB
adjacency matrices* from a real MATLAB run (``OutputData03Mar2026/
ExperimentMatFiles/*_OutputData03Mar2026.mat``, field ``adjMs.adjM{lag}mslag``)
rather than Python's own Step 3 output. Ground truth metric values were
computed by calling MATLAB's own BCT functions directly on those same
matrices — see ``python/test_fixtures/gen_step4_reference.m``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import network_metrics as nm

EXPERIMENT_MAT_DIR = REPO_ROOT / "OutputData03Mar2026" / "ExperimentMatFiles"
FIXTURE_DIR = REPO_ROOT / "python" / "test_fixtures"

RECORDINGS = [
    "NGN2_20230208_P1_DIV14_A2",
    "NGN2_20230208_P1_DIV14_A3",
]
LAGS_MS = [10, 25, 50]


def _scalar(x) -> float:
    return float(np.asarray(x).reshape(-1)[0])


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Step 4: Network Metrics Parity Test")
    print("=" * 70)

    total_checks = 0
    total_matches = 0
    mismatches: list[str] = []

    for rec_name in RECORDINGS:
        fixture_path = FIXTURE_DIR / f"{rec_name}_step4_reference.npz"
        mat_path = EXPERIMENT_MAT_DIR / f"{rec_name}_OutputData03Mar2026.mat"
        if not fixture_path.exists() or not mat_path.exists():
            print(f"  ! Missing fixture or MATLAB .mat for {rec_name}, skipping.")
            continue

        fixture = np.load(fixture_path)

        print(f"\n{'─' * 60}")
        print(f"Recording: {rec_name}")
        print(f"{'─' * 60}")

        with h5py.File(mat_path, "r") as f:
            for lag_ms in LAGS_MS:
                adj_m_full = f["adjMs"][f"adjM{lag_ms}mslag"][()].T
                adj_m_full = np.nan_to_num(adj_m_full, nan=0.0)
                adj_m_full[adj_m_full < 0] = 0.0

                incl = fixture[f"lag{lag_ms}_inclusionIndex"].astype(int) - 1  # MATLAB 1-based
                sub = adj_m_full[np.ix_(incl, incl)]

                nd, mew = nm.find_node_deg_edge_weight(sub, 0.0001, True)
                ns = nm.strengths_und(sub)
                dens = nm.density_und(sub)
                cc = nm.clustering_coef_wu(sub)

                length_mat = nm.weight_conversion_lengths(sub)
                dist = nm.distance_wei(length_mat)
                pl, _ = nm.charpath(dist)

                eglob = nm.efficiency_wei_global(sub)
                eloc = nm.efficiency_wei_local(nm.weight_conversion_normalize(sub))

                n = sub.shape[0]
                bc = nm.betweenness_wei(1.0 / (sub + 0.01)) / ((n - 1) * (n - 2))

                with np.errstate(divide="ignore"):
                    ne = 1.0 / dist.mean(axis=0)

                checks = [
                    ("ND", nd, fixture[f"lag{lag_ms}_ND"], 1e-6),
                    ("MEW", mew, fixture[f"lag{lag_ms}_MEW"], 1e-6),
                    ("NS", ns, fixture[f"lag{lag_ms}_NS"], 1e-6),
                    ("Dens", dens, _scalar(fixture[f"lag{lag_ms}_Dens"]), 1e-6),
                    ("CC", cc, fixture[f"lag{lag_ms}_CCraw"], 1e-6),
                    ("PL", pl, _scalar(fixture[f"lag{lag_ms}_PLraw"]), 1e-3),
                    ("Eglob", eglob, _scalar(fixture[f"lag{lag_ms}_Eglob"]), 1e-6),
                    ("Eloc", eloc, fixture[f"lag{lag_ms}_Eloc"], 1e-5),
                    ("BC", bc, fixture[f"lag{lag_ms}_BC"], 1e-4),
                    ("NE", ne, fixture[f"lag{lag_ms}_NE"], 1e-6),
                ]

                print(f"\n  lag={lag_ms}ms (aN={n}):")
                for name, py_val, ml_val, atol in checks:
                    ok = np.allclose(py_val, ml_val, atol=atol, equal_nan=True)
                    total_checks += 1
                    total_matches += ok
                    flag = "✓" if ok else "✗"
                    print(f"    {flag} {name}")
                    if not ok:
                        max_diff = np.nanmax(np.abs(np.asarray(py_val) - np.asarray(ml_val)))
                        mismatches.append(f"{rec_name} / lag={lag_ms} / {name}: max|diff|={max_diff}")

    print(f"\n{'=' * 70}")
    print("Summary")
    print(f"{'─' * 70}")
    print(f"Total checks: {total_checks}   Matches: {total_matches}   "
          f"({100 * total_matches / total_checks:.1f}%)" if total_checks else "No checks ran")

    if mismatches:
        print("\nMismatches:")
        for m in mismatches:
            print(f"  ✗ {m}")

    print(f"\n{'=' * 70}")
    if total_checks and total_matches == total_checks:
        print("  → Perfect parity with MATLAB (deterministic metrics)")
    else:
        print("  → Some checks FAILED — see above")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
