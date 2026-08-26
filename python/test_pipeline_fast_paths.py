"""The optimised inner loops must agree with the references they replaced.

Run from the repo root::

    uv run python python/test_pipeline_fast_paths.py

Three routines were rewritten for speed after profiling showed a 270-cell
calcium recording spending ~960s on a single lag (``null_model_und_sign`` and
``efficiency_wei_local`` between them accounting for ~90% of it). Each rewrite
is supposed to be *exactly* equivalent, not merely close, so each is checked
here against the slower form it replaced:

1. ``null_models._stable_ranks`` — an ``argpartition`` that reads only the
   ranks the caller asks for, instead of sorting every remaining edge. It
   diverges from a stable sort only on tied values, which is why it carries a
   tie check and an exact fallback. Real calcium networks produce no ties at
   all (their values are products of node strengths), so the tie path is
   unreachable from real data and is only ever exercised here.
2. ``network_metrics.distance_wei`` — a numba-compiled Dijkstra, checked
   against the NumPy implementation it now shadows (which is still the
   fallback when numba is unavailable).
3. ``sttc.get_sttc`` — hoists ``run_T`` out of the pairwise loop, so it is
   checked against a direct sweep of the unchanged ``sttc_pair``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import network_metrics as nm  # noqa: E402
from meanap.pipeline.null_models import _stable_ranks  # noqa: E402
from meanap.pipeline.sttc import get_sttc, sttc_pair  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def reference_ranks(values: np.ndarray, ranks: np.ndarray) -> np.ndarray:
    """What the loop did before ``_stable_ranks`` existed."""
    return np.argsort(values, kind="stable")[ranks]


print("[1] _stable_ranks vs a full stable argsort")

rng = np.random.default_rng(0)

# Distinct values: the fast path is taken and must land on the same indices.
for m in (1, 2, 11, 500, 7627, 25964):
    values = rng.random(m)
    n_ranks = min(10, m)
    ranks = rng.choice(m, size=n_ranks, replace=False)
    got = _stable_ranks(values, ranks)
    want = reference_ranks(values, ranks)
    check(f"distinct values, m={m}", np.array_equal(got, want),
          f"{got} != {want}")

# Heavily tied values: this is the path real data never reaches. Ties are
# where argpartition is free to disagree with a stable sort, so the fallback
# has to fire and reproduce the stable answer exactly.
for n_distinct in (1, 2, 5):
    values = rng.integers(0, n_distinct, size=400).astype(float)
    ranks = rng.choice(400, size=10, replace=False)
    got = _stable_ranks(values, ranks)
    want = reference_ranks(values, ranks)
    check(f"tied values, {n_distinct} distinct value(s)", np.array_equal(got, want),
          f"{got} != {want}")

# A single tie among otherwise distinct values still has to be caught: this is
# the case a cheaper check (e.g. only looking at the selected values against
# each other) would silently get wrong.
values = np.arange(300, dtype=float)
values[7] = values[251]  # one duplicated value, far apart
ranks = np.array([0, 6, 7, 8, 250, 251, 252, 297, 298, 299])
check("a single duplicated value still takes the exact path",
      np.array_equal(_stable_ranks(values, ranks), reference_ranks(values, ranks)))

# Zeros are the tie a degenerate network would actually produce.
values = np.zeros(200)
values[50:] = rng.random(150)
ranks = rng.choice(200, size=10, replace=False)
check("many exact zeros", np.array_equal(_stable_ranks(values, ranks),
                                         reference_ranks(values, ranks)))


print()
print("[2] distance_wei — compiled vs NumPy reference")

check("numba is available (otherwise the compiled path is untested here)",
      nm._distance_wei_jit is not None,
      "numba missing: distance_wei is running the NumPy fallback")


def random_graph(n: int, density: float, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    w = r.random((n, n)) * (r.random((n, n)) < density)
    w = np.triu(w, 1)
    return w + w.T


cases = [
    ("complete, n=40", random_graph(40, 1.0, 1)),
    ("dense 0.9, n=40", random_graph(40, 0.9, 2)),
    ("sparse 0.05, n=60 (disconnected)", random_graph(60, 0.05, 3)),
    ("very sparse 0.01, n=80 (mostly isolated)", random_graph(80, 0.01, 4)),
    ("empty, n=15", np.zeros((15, 15))),
    ("n=1", np.zeros((1, 1))),
    ("n=2 connected", np.array([[0.0, 0.5], [0.5, 0.0]])),
]

for label, w in cases:
    length_mat = nm.weight_conversion_lengths(w)
    fast = nm.distance_wei(length_mat)
    slow = nm._distance_wei_numpy(length_mat)
    # Infinities must land in the same places, and finite entries must match
    # bit for bit — this is the same arithmetic in a different loop, not an
    # approximation, so no tolerance is allowed.
    same_inf = np.array_equal(np.isinf(fast), np.isinf(slow))
    finite = np.isfinite(slow)
    same_val = np.array_equal(fast[finite], slow[finite])
    check(f"distance_wei: {label}", same_inf and same_val,
          f"inf layout {same_inf}, values {same_val}")

# And the callers that dominated the runtime, since they feed distance_wei a
# submatrix per node rather than the whole network. Swapping the compiled
# Dijkstra out for the NumPy one is what makes this a comparison rather than a
# restatement of the line above.
_compiled = nm.distance_wei
try:
    for label, w in cases[:4]:
        nm.distance_wei = _compiled
        fast_local = nm.efficiency_wei_local(w)
        fast_global = nm.efficiency_wei_global(w)
        nm.distance_wei = nm._distance_wei_numpy
        slow_local = nm.efficiency_wei_local(w)
        slow_global = nm.efficiency_wei_global(w)
        check(f"efficiency_wei_local: {label}",
              np.array_equal(fast_local, slow_local),
              f"max diff {np.max(np.abs(fast_local - slow_local))}")
        check(f"efficiency_wei_global: {label}",
              fast_global == slow_global, f"{fast_global!r} != {slow_global!r}")
finally:
    nm.distance_wei = _compiled


print()
print("[3] get_sttc — hoisted run_T vs the per-pair sttc_pair")

for n, n_spikes, duration in ((30, 40, 120.0), (60, 8, 300.0), (12, 1, 60.0)):
    r = np.random.default_rng(n)
    trains = {i: np.sort(r.uniform(0, duration, r.integers(0, n_spikes + 1)))
              for i in range(n)}
    # A couple of empty trains, which is the branch that returns NaN.
    trains[0] = np.array([])
    trains[n - 1] = np.array([])
    for lag_ms in (10.0, 1000.0):
        got = get_sttc(trains, n, lag_ms, duration)
        want = np.full((n, n), np.nan)
        for i in range(n):
            for j in range(i + 1, n):
                c = sttc_pair(trains[i], trains[j], lag_ms / 1000.0, 0.0, duration)
                want[i, j] = c
                want[j, i] = c
        want[want < 0] = 0.0
        want[np.isnan(want)] = 0.0
        check(f"get_sttc n={n} lag={lag_ms:.0f}ms", np.array_equal(got, want),
              f"max diff {np.max(np.abs(got - want)) if got.shape == want.shape else 'shape'}")


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All fast-path equivalence checks passed.")
