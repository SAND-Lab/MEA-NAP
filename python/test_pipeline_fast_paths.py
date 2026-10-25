"""The optimised inner loops must agree with the references they replaced.

Run from the repo root::

    uv run python python/test_pipeline_fast_paths.py

Routines rewritten for speed — first after profiling showed a 270-cell
calcium recording spending ~960s on a single lag (``null_model_und_sign`` and
``efficiency_wei_local`` between them accounting for ~90% of it), then for
spike-sorted recordings with hundreds of units. Each rewrite is supposed to be
*exactly* equivalent, not merely close, so each is checked here against the
slower form it replaced:

1. ``null_models._stable_ranks`` — an ``argpartition`` that reads only the
   ranks the caller asks for, instead of sorting every remaining edge. It
   diverges from a stable sort only on tied values, which is why it carries a
   tie check and an exact fallback. Real calcium networks produce no ties at
   all (their values are products of node strengths), so the tie path is
   unreachable from real data and is only ever exercised here.
2. ``network_metrics.distance_wei`` — a numba-compiled Dijkstra, checked
   against the NumPy implementation it now shadows (which is still the
   fallback when numba is unavailable).
3. ``sttc.get_sttc`` — hoists ``run_T`` out of the pairwise loop and runs
   the whole sweep as one compiled, row-parallel call, so it is checked
   against a direct sweep of the unchanged ``sttc_pair``, at one thread and
   at several.
4. ``null_models.randmio_und_v2`` / ``latmio_und_v2`` — the swap loop is
   compiled and fed random numbers in batches from the caller's generator.
   Checked against the generator-based version it replaced (kept below as
   the reference): same networks *and* the same generator state afterwards,
   so everything drawn later in a run is unchanged too.
5. ``nmf.cal_nmf`` — fits run on threads, each with a seed drawn up front in
   the old order. Checked against the old serial loops at several thread
   counts, and the early-stopping sweep against the full one.
6. ``null_models.map_null_models_und_sign`` — participation_coef_norm's 100
   null models, built on threads from random numbers drawn up front. Checked
   against null models that draw straight from the generator as they go (the
   pre-threading path, still used without numba): same networks, same
   generator state afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import network_metrics as nm  # noqa: E402
from meanap.pipeline import nmf  # noqa: E402
from meanap.pipeline.null_models import (  # noqa: E402
    _null_from_plan, _stable_ranks, latmio_und_v2, map_null_models_und_sign, randmio_und_v2,
)
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
print("[3] get_sttc — compiled parallel sweep vs the per-pair sttc_pair")

import numba  # noqa: E402


def sttc_reference(trains: dict, n: int, lag_ms: float, duration: float) -> np.ndarray:
    want = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(i + 1, n):
            c = sttc_pair(trains[i], trains[j], lag_ms / 1000.0, 0.0, duration)
            want[i, j] = c
            want[j, i] = c
    want[want < 0] = 0.0
    want[np.isnan(want)] = 0.0
    return want


# Odd and even n, since the parallel sweep takes rows in pairs from both ends
# and the middle row of an odd n is the one it must not do twice.
for n, n_spikes, duration in ((30, 40, 120.0), (60, 8, 300.0), (12, 1, 60.0), (31, 60, 90.0)):
    r = np.random.default_rng(n)
    trains = {i: np.sort(r.uniform(0, duration, r.integers(0, n_spikes + 1)))
              for i in range(n)}
    # A couple of empty trains, which is the branch that returns NaN.
    trains[0] = np.array([])
    trains[n - 1] = np.array([])
    # CAT-NAP peak times can arrive unsorted, and run_P is order-dependent.
    trains[2] = r.permutation(r.uniform(0, duration, 25))
    for lag_ms in (10.0, 1000.0):
        want = sttc_reference(trains, n, lag_ms, duration)
        for threads in (1, numba.config.NUMBA_NUM_THREADS):
            numba.set_num_threads(threads)
            got = get_sttc(trains, n, lag_ms, duration)
            check(f"get_sttc n={n} lag={lag_ms:.0f}ms threads={threads}",
                  np.array_equal(got, want),
                  f"max diff {np.max(np.abs(got - want)) if got.shape == want.shape else 'shape'}")
numba.set_num_threads(numba.config.NUMBA_NUM_THREADS)
check("get_sttc n=0", get_sttc({}, 0, 10.0, 60.0).shape == (0, 0))


print()
print("[4] randmio_und_v2 / latmio_und_v2 — compiled vs the generator version")


def _ref_valid_quad_stream(rng, k, i_arr, j_arr, batch_size=8192):
    """The pre-numba ``_valid_quad_stream``, verbatim."""
    budget = min(2_000_000, max(10_000, 200 * k * k))
    rejected = 0
    while True:
        e1_batch = rng.integers(0, k, size=batch_size)
        e2_batch = rng.integers(0, k, size=batch_size)
        for e1, e2 in zip(e1_batch.tolist(), e2_batch.tolist()):
            if e1 != e2:
                a, b = i_arr[e1], j_arr[e1]
                c, d = i_arr[e2], j_arr[e2]
                if a != c and a != d and b != c and b != d:
                    rejected = 0
                    yield e1, e2, a, b, c, d
                    continue
            rejected += 1
            if rejected >= budget:
                yield None
                rejected = 0


def _ref_coin_flip_stream(rng, batch_size=8192):
    while True:
        for v in rng.random(batch_size).tolist():
            yield v > 0.5


def ref_randmio_und_v2(w, iterations, rng):
    """The pre-numba ``randmio_und_v2``, verbatim."""
    r = w.astype(float).copy()
    n = r.shape[0]
    i_arr_np, j_arr_np = np.nonzero(np.tril(r))
    i_arr, j_arr = i_arr_np.tolist(), j_arr_np.tolist()
    k = len(i_arr)
    if k < 2:
        return r
    max_attempts = round(n * k / (n * (n - 1)))
    quads = _ref_valid_quad_stream(rng, k, i_arr, j_arr)
    flips = _ref_coin_flip_stream(rng)
    for _ in range(iterations):
        for _attempt in range(max_attempts + 1):
            quad = next(quads)
            if quad is None:
                return r
            e1, e2, a, b, c, d = quad
            if next(flips):
                i_arr[e2], j_arr[e2] = d, c
                c, d = d, c
            if not (r[a, d] or r[c, b]):
                r[a, d], r[a, b] = r[a, b], 0.0
                r[d, a], r[b, a] = r[b, a], 0.0
                r[c, b], r[c, d] = r[c, d], 0.0
                r[b, c], r[d, c] = r[d, c], 0.0
                j_arr[e1] = d
                j_arr[e2] = b
                break
    return r


def ref_latmio_und_v2(w, iterations, d, rng):
    """The pre-numba ``latmio_und_v2``, verbatim."""
    n = w.shape[0]
    ind_rp = rng.permutation(n)
    r = w[np.ix_(ind_rp, ind_rp)].astype(float).copy()
    i_arr_np, j_arr_np = np.nonzero(np.tril(r))
    i_arr, j_arr = i_arr_np.tolist(), j_arr_np.tolist()
    k = len(i_arr)
    if k >= 2:
        max_attempts = round(n * k / (n * (n - 1) / 2))
        quads = _ref_valid_quad_stream(rng, k, i_arr, j_arr)
        flips = _ref_coin_flip_stream(rng)
        for _ in range(iterations):
            exhausted = False
            for _attempt in range(max_attempts + 1):
                quad = next(quads)
                if quad is None:
                    exhausted = True
                    break
                e1, e2, a, b, c, dd = quad
                if next(flips):
                    i_arr[e2], j_arr[e2] = dd, c
                    c, dd = dd, c
                if not (r[a, dd] or r[c, b]):
                    if (d[a, b] * r[a, b] + d[c, dd] * r[c, dd]) >= (
                        d[a, dd] * r[a, b] + d[c, b] * r[c, dd]
                    ):
                        r[a, dd], r[a, b] = r[a, b], 0.0
                        r[dd, a], r[b, a] = r[b, a], 0.0
                        r[c, b], r[c, dd] = r[c, dd], 0.0
                        r[b, c], r[dd, c] = r[dd, c], 0.0
                        j_arr[e1] = dd
                        j_arr[e2] = b
                        break
            if exhausted:
                break
    ind_rp_reverse = np.argsort(ind_rp)
    return r[np.ix_(ind_rp_reverse, ind_rp_reverse)]


def profile_distance(w: np.ndarray) -> np.ndarray:
    """``squareform(pdist(adjM))``, what step 4 passes latmio as ``d``."""
    diff = w[:, None, :] - w[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=-1))


star = np.zeros((6, 6))
star[0, 1:] = star[1:, 0] = 1.0
with_nan = random_graph(20, 0.4, 7)
with_nan[2, 5] = with_nan[5, 2] = np.nan
one_edge = np.zeros((10, 10))
one_edge[1, 4] = one_edge[4, 1] = 0.5
swap_cases = [(f"n={n} density={dens}", random_graph(n, dens, seed))
              for n, dens, seed in ((5, 0.9, 1), (12, 0.3, 2), (40, 0.05, 3),
                                    (64, 0.1, 4), (64, 1.0, 5), (150, 0.06, 6))]
swap_cases += [("triangle (no valid swap)", np.ones((3, 3)) - np.eye(3)),
               ("star (no valid swap)", star),
               ("a NaN weight", with_nan),
               ("one edge", one_edge)]
for label, w in swap_cases:
    d = np.nan_to_num(profile_distance(np.nan_to_num(w)))
    for name, fast, slow, args in (
        ("randmio_und_v2", randmio_und_v2, ref_randmio_und_v2, (w, 200)),
        ("latmio_und_v2", latmio_und_v2, ref_latmio_und_v2, (w, 400, d)),
    ):
        r_fast = np.random.default_rng(11)
        r_slow = np.random.default_rng(11)
        got = fast(*args, rng=r_fast)
        want = slow(*args, rng=r_slow)
        check(f"{name}: {label}",
              np.array_equal(got, want, equal_nan=True)
              and r_fast.bit_generator.state == r_slow.bit_generator.state,
              "networks or generator state differ")


print()
print("[5] cal_nmf — threaded fits vs the serial loops")


def ref_cal_nmf_curves(trains, counts, duration, rng):
    """The pre-threading search and sweep loops, on the unchanged ``_nnmf``."""
    n_bins = max(int(round(10.0 * duration)), 1)
    x = nmf._bin_spike_times(trains, duration, n_bins)
    rand = nmf._bin_spike_times([nmf.randomise_spike_train(t, duration, rng) for t in trains],
                                duration, n_bins)
    residual, rand_residual, k, per_component = 0.0, 1.0, 1, []
    while residual < rand_residual and k <= x.shape[1]:
        _, _, residual = nmf._nnmf(x, k, rng)
        _, _, rand_residual = nmf._nnmf(rand, k, rng)
        per_component.append(rand_residual)
        k += 1
    active = counts > 1
    xa = x[:, active]
    res, ve = [], []
    for kk in range(1, int(active.sum()) + 1):
        w, h, d = nmf._nnmf(xa, kk, rng)
        res.append(d)
        ve.append(nmf._variance_explained(xa, w, h))
    return k - 1, np.array(per_component), np.array(res), np.array(ve)


def structured_trains(n: int, duration: float, seed: int) -> list[np.ndarray]:
    """Units sharing a few drivers, so the component search goes past rank 1."""
    r = np.random.default_rng(seed)
    drivers = [np.sort(r.uniform(0, duration, 300)) for _ in range(3)]
    out = []
    for ch in range(n):
        if r.random() < 0.15:
            out.append(np.array([]))
            continue
        own = r.uniform(0, duration, int(r.integers(5, 400)))
        shared = drivers[ch % 3] + r.normal(0, 0.01, 300)
        out.append(np.sort(np.clip(np.concatenate([own, shared[r.random(300) < 0.5]]),
                                   0, duration - 1e-6)))
    return out


for seed, n in ((0, 20), (3, 13), (5, 18), (1, 1)):
    trains = structured_trains(n, 120.0, seed)
    counts = np.array([len(t) for t in trains])
    r_ref = np.random.default_rng(seed)
    k_ref, per_ref, res_ref, ve_ref = ref_cal_nmf_curves(trains, counts, 120.0, r_ref)
    for workers in (1, 3, 8):
        r_new = np.random.default_rng(seed)
        got = nmf.cal_nmf(trains, counts, 120.0, 10.0, 25000.0, rng=r_new, max_workers=workers)
        same = (got["num_nnmf_components"] == k_ref
                and np.array_equal(got["randResidualPerComponent"], per_ref)
                and np.array_equal(got["nnmf_residuals"], res_ref)
                and np.array_equal(got["nnmf_var_explained"], ve_ref)
                and r_new.bit_generator.state == r_ref.bit_generator.state)
        check(f"cal_nmf n={n} workers={workers} (k={k_ref})", same,
              "curves, component count or generator state differ")

# The early stop must fit a prefix of the full sweep, rank for rank, then stop
# where _levelled_off first says so, leaving the rest NaN.
trains = structured_trains(60, 120.0, 9)
counts = np.array([len(t) for t in trains])
full = nmf.cal_nmf(trains, counts, 120.0, 10.0, 25000.0, rng=np.random.default_rng(2), max_workers=4)
first_95 = int(np.argmax(full["nnmf_var_explained"] > 0.95)) + 1
stops = []
for gain in (0.002, 0.05, 0.3):
    part = nmf.cal_nmf(trains, counts, 120.0, 10.0, 25000.0, rng=np.random.default_rng(2),
                       max_workers=4, plateau_gain=gain)
    ve = part["nnmf_var_explained"]
    fitted = int(np.sum(~np.isnan(ve)))
    expected = len(ve)
    for r in range(1, len(ve) + 1):
        reached = bool(np.any(full["nnmf_var_explained"][:r] > 0.95))
        if nmf._levelled_off(full["nnmf_var_explained"][:r], gain, reached):
            expected = r
            break
    check(f"plateau_gain={gain}: stops at rank {expected} of {len(ve)}",
          fitted == expected
          and np.array_equal(ve[:fitted], full["nnmf_var_explained"][:fitted])
          and np.all(np.isnan(ve[fitted:]))
          and part["num_nnmf_components"] == full["num_nnmf_components"],
          f"fitted {fitted}, expected {expected}")
    stops.append(fitted)
# The large gain has to stop on a plateau, before the curve reaches 95%, or the
# plateau branch of _levelled_off has gone untested.
check(f"a plateau stop comes before the 95% crossing (rank {first_95})",
      min(stops) < first_95, f"stops {stops}")


print()
print("[6] null_model_und_sign — threaded batches vs drawing as it goes")


def signed_graph(n: int, density: float, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    w = r.random((n, n)) * (r.random((n, n)) < density) * np.where(r.random((n, n)) < 0.3, -1, 1)
    w = np.triu(w, 1)
    return w + w.T


null_cases = [("n=3 (too small to rewire)", random_graph(3, 1.0, 0)),
              ("complete n=20 (not rewired)", random_graph(20, 1.0, 1)),
              ("n=30 signed", signed_graph(30, 0.2, 2)),
              ("n=64 density 0.1", random_graph(64, 0.1, 3)),
              ("n=150 density 0.06", random_graph(150, 0.06, 4))]
for label, w in null_cases:
    r_ref = np.random.default_rng(5)
    want = [_null_from_plan(w, 5, 0.1, None, r_ref) for _ in range(10)]
    for workers in (1, 6):
        r_new = np.random.default_rng(5)
        got = map_null_models_und_sign(w, 10, lambda x: x, rng=r_new, workers=workers)
        check(f"null models {label}, workers={workers}",
              all(np.array_equal(a, b) for a, b in zip(want, got))
              and r_new.bit_generator.state == r_ref.bit_generator.state,
              "networks or generator state differ")

w = random_graph(80, 0.1, 6)
ci = np.random.default_rng(6).integers(1, 5, 80)
_threads = nm.compute_threads
try:
    nm.compute_threads = lambda: 1
    serial = nm.participation_coef_norm(w, ci, 40, rng=np.random.default_rng(7))
    nm.compute_threads = lambda: 8
    threaded = nm.participation_coef_norm(w, ci, 40, rng=np.random.default_rng(7))
finally:
    nm.compute_threads = _threads
check("participation_coef_norm: 1 thread vs 8",
      all(np.array_equal(a, b) for a, b in zip(serial, threaded)))


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All fast-path equivalence checks passed.")
