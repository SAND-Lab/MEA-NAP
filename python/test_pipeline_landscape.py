"""Tests for data-driven node-cartography boundaries (TrialLandscapeDensity port).

Run from the repo root::

    uv run python python/test_pipeline_landscape.py

Covers ``network_metrics._optimal_1d_split_boundaries`` (deterministic optimal
1-D k-means) and ``network_metrics.trial_landscape_density`` (port of
``TrialLandscapeDensity.m``, ``boundarySelectionMethod='kmeans'`` branch).

The headline behaviour under test is the bug this port fixes: with the *fixed*
default boundaries (``peri_part_coef=0.625`` …) almost every node's PC falls
below the peripheral cutoff, so ~95% of nodes get dumped into cartography
role 1 (NCpn1). Deriving the boundaries from the data spreads nodes across all
six roles instead — matching MATLAB's real output shape. We assert exactly
that regression using the in-repo cartography fixtures (MATLAB-generated PC/Z).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from meanap.pipeline import network_metrics as nm  # noqa: E402

FIX = Path(__file__).resolve().parent / "test_fixtures"
_checks = 0
_fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _checks, _fails
    _checks += 1
    _fails += 0 if ok else 1
    print(f"    {'✓' if ok else '✗'} {name}{'  ' + detail if detail else ''}")


def test_optimal_1d_split() -> None:
    print("[1] _optimal_1d_split_boundaries — synthetic, known answer")
    # three tight clusters around 0, 5, 10 → boundaries near 2.5 and 7.5
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 0.1, 20), rng.normal(5, 0.1, 20), rng.normal(10, 0.1, 20)])
    b = nm._optimal_1d_split_boundaries(x, 3)
    check("returns k-1 boundaries", b is not None and len(b) == 2)
    check("boundaries sorted & between clusters", 2.0 < b[0] < 3.0 and 7.0 < b[1] < 8.0,
          f"got {b}")
    # determinism: identical on repeat (no RNG in the DP)
    b2 = nm._optimal_1d_split_boundaries(x, 3)
    check("deterministic across calls", np.allclose(b, b2))
    # k=2 split of a two-cluster set
    y = np.concatenate([np.zeros(5), np.full(5, 10.0)])
    b3 = nm._optimal_1d_split_boundaries(y, 2)
    check("k=2 midpoint correct", b3 is not None and abs(b3[0] - 5.0) < 1e-9, f"got {b3}")
    # insufficient distinct values → None (caller falls back to defaults)
    check("fewer than k distinct → None", nm._optimal_1d_split_boundaries(np.ones(10), 3) is None)
    check("too few points → None", nm._optimal_1d_split_boundaries(np.array([1.0]), 2) is None)


def test_trial_landscape_density() -> None:
    print("\n[2] trial_landscape_density — fixture PC/Z, boundary ordering")
    defaults = (2.5, 0.625, 0.3, 0.8, 0.75)  # hub, peri, prohub, nonhub, connhub
    for rec in ("NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"):
        f = np.load(FIX / f"{rec}_cartography_reference.npz")
        for lag in (10, 25, 50):
            pc = f[f"lag{lag}_PCnorm"].astype(float)
            z = f[f"lag{lag}_Z"].astype(float)
            b = nm.trial_landscape_density(pc, z, *defaults)
            check(f"{rec[-2:]} lag{lag}: returns 5 boundaries", b is not None and len(b) == 5)
            hub_b, peri, non_hub_conn, pro_hub, conn_hub = b
            check(f"{rec[-2:]} lag{lag}: non-hub PC boundaries ordered", peri <= non_hub_conn,
                  f"peri={peri:.3f} nonHubConn={non_hub_conn:.3f}")
            check(f"{rec[-2:]} lag{lag}: hub PC boundaries ordered", pro_hub <= conn_hub,
                  f"proHub={pro_hub:.3f} connHub={conn_hub:.3f}")
            check(f"{rec[-2:]} lag{lag}: PC boundaries within [0,1]",
                  all(0.0 <= v <= 1.0 for v in (peri, non_hub_conn, pro_hub, conn_hub)))


def test_fixes_role1_pileup() -> None:
    print("\n[3] regression: data-driven boundaries fix the NCpn1 pile-up")
    defaults = (2.5, 0.625, 0.3, 0.8, 0.75)
    for rec in ("NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"):
        f = np.load(FIX / f"{rec}_cartography_reference.npz")
        for lag in (10, 25, 50):
            pc = f[f"lag{lag}_PCnorm"].astype(float)
            z = f[f"lag{lag}_Z"].astype(float)
            n = len(pc)

            _, pop_fixed = nm.classify_node_cartography(
                pc, z, defaults[0], defaults[1], defaults[3], defaults[2], defaults[4])
            frac1_fixed = pop_fixed[0] / n

            hub_b, peri, non_hub_conn, pro_hub, conn_hub = nm.trial_landscape_density(pc, z, *defaults)
            _, pop_auto = nm.classify_node_cartography(pc, z, hub_b, peri, non_hub_conn, pro_hub, conn_hub)
            frac1_auto = pop_auto[0] / n
            roles_used = int(np.sum(pop_auto > 0))

            check(f"{rec[-2:]} lag{lag}: fixed defaults pile into role 1", frac1_fixed >= 0.5,
                  f"NCpn1(fixed)={frac1_fixed:.2f}")
            check(f"{rec[-2:]} lag{lag}: auto boundaries spread the pile out", frac1_auto < frac1_fixed,
                  f"NCpn1 {frac1_fixed:.2f} → {frac1_auto:.2f}, {roles_used}/6 roles used")
            check(f"{rec[-2:]} lag{lag}: all counts conserved", int(np.sum(pop_auto)) == n)


if __name__ == "__main__":
    test_optimal_1d_split()
    test_trial_landscape_density()
    test_fixes_role1_pileup()
    print("\n" + "=" * 70)
    print(f"Total checks: {_checks}   Failures: {_fails}")
    print("=" * 70)
    print("  → All checks passed" if _fails == 0 else f"  → {_fails} FAILED")
    sys.exit(1 if _fails else 0)
