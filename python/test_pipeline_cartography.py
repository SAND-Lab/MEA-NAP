"""Test node cartography / modularity-dependent metrics parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_cartography.py

Modularity (community detection via Louvain + consensus clustering,
``modularity.py``) is inherently stochastic — MATLAB's own runs aren't
bit-reproducible across each other, let alone against Python (different RNG
streams). So this test does what the rest of the deterministic-metric tests
in this repo do: feed the *deterministic* downstream computations
(raw participation coefficient, within-module z-score, rich club
coefficient) a **fixed, MATLAB-generated community assignment (Ci)** — see
``python/test_fixtures/gen_cartography_reference.m`` — and diff against
MATLAB's own output for those same functions given that same Ci. This
isolates "does the deterministic math match" from "does the same community
assignment get found," which is a different (and inherently unanswerable,
bit-for-bit) question.

Node cartography classification and hub counting are additionally fed a
**fixed, MATLAB-generated *normalized* PC** (``participation_coef_norm``'s
1st output — what MATLAB's real pipeline actually feeds these two
functions, confirmed by tracing ``ExtractNetMet.m`` → ``PlotIndvNetMet.m``;
see ``network_metrics.py``'s docstring). That normalization is itself
stochastic (100 degree-preserving network randomizations per node), so this
is the same isolation trick applied one level deeper — not a claim that
Python's own ``participation_coef_norm`` reproduces MATLAB's specific
random outcome.

Louvain itself (``louvain.py``) is separately sanity-checked against known
theoretical values (e.g. Q=0.5 for two disconnected triangles) rather than
against MATLAB directly.
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

HUB_BOUNDARY_WM_D_DEG = 2.5
PERI_PART_COEF = 0.625
PRO_HUB_PART_COEF = 0.3
NON_HUB_CONNECTOR_PART_COEF = 0.8
CONNECTOR_HUB_PART_COEF = 0.75


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Node Cartography / Modularity-dependent Metrics Parity Test")
    print("=" * 70)

    total_checks = 0
    total_matches = 0
    mismatches: list[str] = []

    for rec_name in RECORDINGS:
        fixture_path = FIXTURE_DIR / f"{rec_name}_cartography_reference.npz"
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

                incl = fixture[f"lag{lag_ms}_inclusionIndex"].astype(int) - 1
                sub = adj_m_full[np.ix_(incl, incl)]
                ci = fixture[f"lag{lag_ms}_Ci"].astype(int)

                pc = nm.participation_coef(sub, ci)
                z = nm.module_degree_zscore(sub, ci)
                rw = nm.rich_club_wu(sub)

                # Node cartography / hub classification in MATLAB's real
                # pipeline run on the *normalized* PC (participation_coef_
                # norm.m's 1st output — see network_metrics.py's docstring),
                # not the raw formula. Since that normalization is itself
                # stochastic (100 degree-preserving randomizations), we feed
                # classify_node_cartography/hub_classification the same
                # fixed, MATLAB-generated PCnorm the fixture captured —
                # same isolation pattern as Ci: validate the deterministic
                # classification logic given a fixed (if unreproducible)
                # upstream value.
                pc_norm_fixed = fixture[f"lag{lag_ms}_PCnorm"]
                nd_cart_div, pop_num_nc = nm.classify_node_cartography(
                    pc_norm_fixed, z, HUB_BOUNDARY_WM_D_DEG, PERI_PART_COEF,
                    NON_HUB_CONNECTOR_PART_COEF, PRO_HUB_PART_COEF, CONNECTOR_HUB_PART_COEF,
                )

                nd, _ = nm.find_node_deg_edge_weight(sub, 0.0001, True)
                bc = nm.betweenness_wei(1.0 / (sub + 0.01))
                n = sub.shape[0]
                bc = bc / ((n - 1) * (n - 2))
                length_mat = nm.weight_conversion_lengths(sub)
                dist = nm.distance_wei(length_mat)
                with np.errstate(divide="ignore"):
                    ne = 1.0 / dist.mean(axis=0)
                hub3, hub4 = nm.hub_classification(nd, pc_norm_fixed, bc, ne)

                ref_rw = fixture[f"lag{lag_ms}_Rw"]
                # MATLAB's Rw length = max node degree in the subset; Python's
                # default k_level matches (same node_degree.max()) so shapes
                # should already agree — pad/truncate defensively either way.
                n_common = min(len(rw), len(ref_rw))

                checks = [
                    ("PC", pc, fixture[f"lag{lag_ms}_PC"], 1e-6),
                    ("Z", z, fixture[f"lag{lag_ms}_Z"], 1e-6),
                    ("Rw", rw[:n_common], ref_rw[:n_common], 1e-6),
                    ("NdCartDiv", nd_cart_div, fixture[f"lag{lag_ms}_NdCartDiv"], 0),
                    ("PopNumNC", pop_num_nc, fixture[f"lag{lag_ms}_PopNumNC"], 0),
                    ("Hub3", hub3, fixture[f"lag{lag_ms}_Hub3"], 1e-6),
                    ("Hub4", hub4, fixture[f"lag{lag_ms}_Hub4"], 1e-6),
                ]

                print(f"\n  lag={lag_ms}ms (aN={len(incl)}, nMod={ci.max()}):")
                for name, py_val, ml_val, atol in checks:
                    ok = np.allclose(py_val, ml_val, atol=atol, equal_nan=True)
                    total_checks += 1
                    total_matches += ok
                    flag = "✓" if ok else "✗"
                    print(f"    {flag} {name}")
                    if not ok:
                        py_arr, ml_arr = np.asarray(py_val, dtype=float), np.asarray(ml_val, dtype=float)
                        max_diff = np.nanmax(np.abs(py_arr - ml_arr))
                        mismatches.append(f"{rec_name} / lag={lag_ms} / {name}: max|diff|={max_diff}")

    print(f"\n{'=' * 70}")
    print("Summary")
    print(f"{'─' * 70}")
    if total_checks:
        print(f"Total checks: {total_checks}   Matches: {total_matches}   "
              f"({100 * total_matches / total_checks:.1f}%)")
    else:
        print("No checks ran")

    if mismatches:
        print("\nMismatches:")
        for m in mismatches:
            print(f"  ✗ {m}")

    print(f"\n{'=' * 70}")
    if total_checks and total_matches == total_checks:
        print("  → Perfect parity with MATLAB (deterministic metrics, given a fixed Ci)")
    else:
        print("  → Some checks FAILED — see above")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
