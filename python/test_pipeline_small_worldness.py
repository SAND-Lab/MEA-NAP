"""Small-worldness parity + structural tests (``network_metrics
.small_worldness_rl_wu`` and ``null_models.randmio_und_v2``/
``latmio_und_v2``).

Run from the repo root::

    uv run python python/test_pipeline_small_worldness.py

``small_worldness_rl_wu`` is deterministic *given* a real network ``A`` and
two null models ``R``/``L`` — the stochasticity lives entirely in how
``R``/``L`` are generated (``randmio_und_v2``/``latmio_und_v2``, Maslov-
Sneppen edge-swap rewiring, not bit-reproducible against MATLAB's
independent RNG stream — see ``null_models.py``'s docstring). So this test,
like ``test_pipeline_cartography.py``'s fixed-Ci approach, has two parts:

1. Exact parity of ``small_worldness_rl_wu(A, R, L)`` against MATLAB's own
   ``small_worldness_RL_wu.m``, fed the *same* ``A``/``R``/``L`` (generated
   once by MATLAB, saved in ``small_worldness_reference.npz`` — see
   ``gen_small_worldness_reference.m``). This isolates "does the formula
   assembly match" from "do two independent RNG streams agree".
2. Structural invariants on Python's own ``randmio_und_v2``/``latmio_und_v2``
   (exact degree preservation, exact total-weight preservation, symmetry) —
   NOT a MATLAB parity check, same rationale as
   ``test_pipeline_null_models.py``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial.distance import pdist, squareform

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import network_metrics as nm
from meanap.pipeline.null_models import latmio_und_v2, randmio_und_v2

FIXTURE_PATH = REPO_ROOT / "python" / "test_fixtures" / "small_worldness_reference.npz"


def _scalar(x) -> float:
    return float(np.asarray(x).reshape(-1)[0])


def test_formula_parity(fixture) -> bool:
    print("\n[1] small_worldness_rl_wu — exact parity against MATLAB, fixed A/R/L")
    a, r, l = fixture["A"], fixture["R"], fixture["L"]
    sw, sww, cc, pl = nm.small_worldness_rl_wu(a, r, l)

    expected = {
        "SW": (_scalar(fixture["SW"]), sw),
        "SWw": (_scalar(fixture["SWw"]), sww),
        "CC": (_scalar(fixture["CC"]), cc),
        "PL": (_scalar(fixture["PL"]), pl),
    }
    ok = True
    for name, (want, got) in expected.items():
        match = np.isclose(want, got, atol=1e-6, rtol=1e-6)
        ok &= match
        print(f"    {'✓' if match else '✗'} {name}: MATLAB={want:.6f} Python={got:.6f}")
    return ok


def test_null_model_invariants(fixture) -> bool:
    print("\n[2] randmio_und_v2 / latmio_und_v2 — structural invariants")
    a = fixture["A"]
    rng = np.random.default_rng(0)
    deg_before = np.count_nonzero(a, axis=0)
    weight_before = a.sum()

    t0 = time.time()
    r = randmio_und_v2(a, 5000, rng=rng)
    t_rand = time.time() - t0

    d = squareform(pdist(a))
    t0 = time.time()
    l = latmio_und_v2(a, 10000, d, rng=rng)
    t_lat = time.time() - t0

    print(f"    randmio_und_v2 (5000 iter, n={a.shape[0]}): {t_rand:.2f}s")
    print(f"    latmio_und_v2 (10000 iter, n={a.shape[0]}): {t_lat:.2f}s")

    checks = {
        "randmio: degree sequence exactly preserved": np.array_equal(deg_before, np.count_nonzero(r, axis=0)),
        "randmio: total weight exactly preserved": np.isclose(weight_before, r.sum()),
        "randmio: symmetric": np.allclose(r, r.T),
        "randmio: actually changed something": not np.allclose(r, a),
        "latmio: degree sequence exactly preserved": np.array_equal(deg_before, np.count_nonzero(l, axis=0)),
        "latmio: total weight exactly preserved": np.isclose(weight_before, l.sum()),
        "latmio: symmetric": np.allclose(l, l.T),
        "latmio: actually changed something": not np.allclose(l, a),
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def test_end_to_end_smoke(fixture) -> bool:
    print("\n[3] End-to-end smoke test — Python's own R/L fed into small_worldness_rl_wu")
    a = fixture["A"]
    rng = np.random.default_rng(1)
    d = squareform(pdist(a))
    l = latmio_und_v2(a, 10000, d, rng=rng)
    r = randmio_und_v2(a, 5000, rng=rng)
    sw, sww, cc, pl = nm.small_worldness_rl_wu(a, r, l)

    checks = {
        "SW finite": np.isfinite(sw),
        "SWw in [-1, 1] (small-world/random/lattice range)": -1.0 <= sww <= 1.0,
        "CC finite and positive": np.isfinite(cc) and cc > 0,
        "PL finite and positive": np.isfinite(pl) and pl > 0,
    }
    print(f"    SW={sw:.4f} SWw={sww:.4f} CC={cc:.4f} PL={pl:.4f}")
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Small-worldness Parity + Structural Tests")
    print("=" * 70)

    if not FIXTURE_PATH.exists():
        print(f"\n! Missing fixture: {FIXTURE_PATH}")
        print("  Regenerate with:")
        print("    matlab -batch \"run('python/test_fixtures/gen_small_worldness_reference.m')\"")
        print("  then convert to .npz (see the comment at the top of that script).")
        sys.exit(1)

    fixture = np.load(FIXTURE_PATH)

    ok1 = test_formula_parity(fixture)
    ok2 = test_null_model_invariants(fixture)
    ok3 = test_end_to_end_smoke(fixture)

    print(f"\n{'=' * 70}")
    if ok1 and ok2 and ok3:
        print("  → All checks passed")
    else:
        print("  → Some checks FAILED — see above")
        sys.exit(1)
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
