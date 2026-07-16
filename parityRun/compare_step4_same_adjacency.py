"""Level-3 parity check: MATLAB vs Python network metrics on IDENTICAL graphs.

Loads the adjacency matrices + MATLAB-computed metrics produced by
parityRun/gen_step4_parity_reference.m (MATLAB's own BCT functions run on this
parity run's adjacency), feeds the *same* adjMsub to the Python port's
network_metrics functions, and reports the difference.

This isolates the step-4 metric arithmetic: unlike the end-to-end comparison,
neither spike detection nor step 3's probabilistic-thresholding RNG can
contribute any difference here, because both sides start from the same matrix.

    uv run python parityRun/compare_step4_same_adjacency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.network_metrics import (
    average_controllability,
    betweenness_wei,
    charpath,
    clustering_coef_wu,
    density_und,
    distance_wei,
    efficiency_wei_global,
    efficiency_wei_local,
    find_node_deg_edge_weight,
    modal_controllability,
    strengths_und,
    weight_conversion_lengths,
    weight_conversion_normalize,
)

RECS = ["NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"]
LAGS = [10, 25, 50]


def rel(a: float, b: float) -> float:
    d = max(abs(a), abs(b))
    return abs(a - b) / d if d > 0 else 0.0


def main() -> None:
    rows = []
    for rec in RECS:
        ref = loadmat(REPO_ROOT / "parityRun" / f"{rec}_step4_parity_ref.mat",
                      simplify_cells=True)["results"]
        for lag in LAGS:
            r = ref[f"lag{lag}"]
            A = np.asarray(r["adjMsub"], dtype=float)

            # ── Python computes every metric from the SAME matrix ────────────
            ND_py, MEW_py = find_node_deg_edge_weight(A, 0.0001, True)
            NS_py = strengths_und(A)
            Dens_py = density_und(A)
            CCraw_py = clustering_coef_wu(A)
            DistM = distance_wei(weight_conversion_lengths(A))
            PLraw_py = charpath(DistM)[0]
            Eglob_py = efficiency_wei_global(A)
            Eloc_py = efficiency_wei_local(weight_conversion_normalize(A))
            BC_py = betweenness_wei(1.0 / (A + 0.01))
            BC_py = BC_py / ((len(A) - 1) * (len(A) - 2))
            aveC_py = average_controllability(A)
            modC_py = modal_controllability(A)

            checks = {
                "aN": (float(r["aN"]), float(A.shape[0])),
                "Dens": (float(r["Dens"]), float(Dens_py)),
                "ND": (np.asarray(r["ND"]).ravel(), np.asarray(ND_py).ravel()),
                "MEW": (np.asarray(r["MEW"]).ravel(), np.asarray(MEW_py).ravel()),
                "NS": (np.asarray(r["NS"]).ravel(), np.asarray(NS_py).ravel()),
                "CCraw": (np.asarray(r["CCraw"]).ravel(), np.asarray(CCraw_py).ravel()),
                "PLraw": (float(r["PLraw"]), float(PLraw_py)),
                "Eglob": (float(r["Eglob"]), float(Eglob_py)),
                "Eloc": (np.asarray(r["Eloc"]).ravel(), np.asarray(Eloc_py).ravel()),
                "BC": (np.asarray(r["BC"]).ravel(), np.asarray(BC_py).ravel()),
                "aveControl": (np.asarray(r["aveControl"]).ravel(), np.asarray(aveC_py).ravel()),
                "modalControl": (np.asarray(r["modalControl"]).ravel(), np.asarray(modC_py).ravel()),
            }

            for name, (ml, py) in checks.items():
                ml_a, py_a = np.atleast_1d(ml).astype(float), np.atleast_1d(py).astype(float)
                if ml_a.shape != py_a.shape:
                    rows.append((rec, lag, name, np.nan, np.nan, f"SHAPE {ml_a.shape} vs {py_a.shape}"))
                    continue
                abs_d = float(np.max(np.abs(ml_a - py_a)))
                denom = np.maximum(np.abs(ml_a), np.abs(py_a))
                rel_d = float(np.max(np.where(denom > 0, np.abs(ml_a - py_a) / np.where(denom > 0, denom, 1), 0)))
                rows.append((rec, lag, name, abs_d, rel_d, ""))

    print(f"{'recording':28s} {'lag':>4s} {'metric':14s} {'max_abs_diff':>14s} {'max_rel_diff':>14s}  note")
    print("-" * 96)
    worst = 0.0
    for rec, lag, name, abs_d, rel_d, note in rows:
        print(f"{rec:28s} {lag:4d} {name:14s} {abs_d:14.3e} {rel_d:14.3e}  {note}")
        if not np.isnan(abs_d):
            worst = max(worst, abs_d)

    print("-" * 96)
    print(f"Worst absolute difference across every metric/recording/lag: {worst:.3e}")
    print("(1e-12 or below = floating-point noise, i.e. exact parity)")


if __name__ == "__main__":
    main()
