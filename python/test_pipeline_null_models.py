"""Structural tests for degree-preserving null models (``null_models.py``)
and the normalized participation coefficient built on top of them
(``network_metrics.participation_coef_norm``).

Run from the repo root::

    uv run python python/test_pipeline_null_models.py

These functions are stochastic (Maslov-Sneppen edge-swap rewiring) and not
bit-reproducible against MATLAB — see ``null_models.py``'s docstring. What
*is* testable without an RNG-matching MATLAB run: the mathematical
invariants the algorithm guarantees by construction (exact degree
preservation, exact total-weight preservation, approximate strength
preservation), plus a smoke test that ``participation_coef_norm`` runs
cleanly on real data and produces bounded, non-NaN output.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import h5py
import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import network_metrics as nm
from meanap.pipeline.modularity import mod_consensus_cluster_iterate
from meanap.pipeline.null_models import null_model_und_sign, randmio_und_signed

EXPERIMENT_MAT_DIR = REPO_ROOT / "OutputData03Mar2026" / "ExperimentMatFiles"
REC_NAME = "NGN2_20230208_P1_DIV14_A2"


def _load_real_adjm(lag_ms: int = 10, n: int = 59) -> np.ndarray:
    mat_path = EXPERIMENT_MAT_DIR / f"{REC_NAME}_OutputData03Mar2026.mat"
    with h5py.File(mat_path, "r") as f:
        adj_m = f["adjMs"][f"adjM{lag_ms}mslag"][()].T
    adj_m = np.nan_to_num(adj_m, nan=0.0)
    adj_m[adj_m < 0] = 0.0
    return adj_m[:n, :n]


def test_randmio_und_signed(sub: np.ndarray) -> bool:
    print("\n[1] randmio_und_signed — degree/weight-preservation invariants")
    rng = np.random.default_rng(0)
    deg_before = np.count_nonzero(sub, axis=0)
    weight_before = sub.sum()

    r = randmio_und_signed(sub, iterations=5, rng=rng)
    deg_after = np.count_nonzero(r, axis=0)

    checks = {
        "degree sequence exactly preserved": np.array_equal(deg_before, deg_after),
        "total weight exactly preserved": np.isclose(weight_before, r.sum()),
        "symmetric": np.allclose(r, r.T),
        "actually changed something": not np.allclose(r, sub),
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def test_null_model_und_sign(sub: np.ndarray) -> bool:
    print("\n[2] null_model_und_sign — degree preservation + approximate strength preservation")
    rng = np.random.default_rng(0)
    deg_before = np.count_nonzero(sub, axis=0)
    strength_before = sub.sum(axis=1)

    w0 = null_model_und_sign(sub, bin_swaps=5, rng=rng)
    deg_after = np.count_nonzero(w0, axis=0)
    strength_after = w0.sum(axis=1)
    corr = np.corrcoef(strength_before, strength_after)[0, 1]

    checks = {
        "degree sequence exactly preserved": np.array_equal(deg_before, deg_after),
        "total weight exactly preserved": np.isclose(sub.sum(), w0.sum()),
        "strength distribution approximately preserved (corr > 0.8)": corr > 0.8,
        "symmetric": np.allclose(w0, w0.T),
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    print(f"    (strength correlation: {corr:.4f})")
    return all(checks.values())


def test_participation_coef_norm(sub: np.ndarray) -> bool:
    print("\n[3] participation_coef_norm — smoke test on real data")
    rng = np.random.default_rng(0)
    ci, _q, _ = mod_consensus_cluster_iterate(sub, rng=rng)

    t0 = time.time()
    pc_norm, pc_residual, pc_raw, between_mod_k = nm.participation_coef_norm(
        sub, ci, n_iter=100, rng=rng,
    )
    elapsed = time.time() - t0
    print(f"    done in {elapsed:.1f}s ({sub.shape[0]} nodes, 100 iterations)")

    checks = {
        "PC_norm bounded in [0, 1]": bool(np.all((pc_norm >= 0) & (pc_norm <= 1))),
        "PC_norm has no NaN": not np.any(np.isnan(pc_norm)),
        "PC_raw bounded in [0, 1]": bool(np.all((pc_raw >= -1e-9) & (pc_raw <= 1))),
        "shapes match node count": len(pc_norm) == sub.shape[0],
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Null Models / Normalized PC Structural Tests")
    print("=" * 70)

    sub = _load_real_adjm()
    print(f"\nUsing real adjacency matrix: {REC_NAME}, lag=10ms, n={sub.shape[0]} nodes")

    ok1 = test_randmio_und_signed(sub)
    ok2 = test_null_model_und_sign(sub)
    ok3 = test_participation_coef_norm(sub)

    print(f"\n{'=' * 70}")
    if ok1 and ok2 and ok3:
        print("  → All structural checks passed")
    else:
        print("  → Some checks FAILED — see above")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
