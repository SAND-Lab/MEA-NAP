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
7. ``io._read_deflate_parallel`` — MATLAB v7.3 ``dat`` inflated chunk by
   chunk on threads. Checked against h5py's own read, including edge chunks,
   integer data, and the layouts it must decline (shuffle, no compression,
   unwritten chunks).
8. ``plotting._frequency_curves`` — per-bin spike counts by ``bincount``
   rather than a full-length 0/1 vector per channel.
9. ``spike_detection.detect_spikes_wavelet`` — the thresholding keeps
   ``c > DTh`` instead of building the matrix of kept coefficients. Checked
   against the matrix version on the same coefficients. (The CWT itself moved
   from FFT to direct convolution, which agrees to rounding, not exactly;
   that is checked to a tolerance.)
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



# ── 7. Parallel inflate of MATLAB v7.3 chunks ─────────────────────────────────

import tempfile  # noqa: E402

import h5py  # noqa: E402

from meanap.pipeline import io as mio  # noqa: E402
from meanap.pipeline import parallel as mpar  # noqa: E402

_compute_threads = mpar.compute_threads
with tempfile.TemporaryDirectory() as tmp:
    rng = np.random.default_rng(8)
    cases = [
        # (label, data, create_dataset kwargs, should take the parallel path)
        ("64 x 127 chunks, edge chunk", rng.standard_normal((64, 1000)),
         dict(chunks=(64, 127), compression="gzip", compression_opts=3), True),
        ("row and column edge chunks", rng.standard_normal((13, 1000)),
         dict(chunks=(5, 127), compression="gzip"), True),
        ("int16 data", rng.integers(-3000, 3000, (8, 999)).astype(np.int16),
         dict(chunks=(8, 100), compression="gzip"), True),
        ("shuffle + gzip", rng.standard_normal((8, 500)),
         dict(chunks=(8, 64), compression="gzip", shuffle=True), False),
        ("chunked, uncompressed", rng.standard_normal((8, 500)),
         dict(chunks=(8, 64)), False),
        ("contiguous", rng.standard_normal((8, 500)), dict(), False),
    ]
    try:
        mpar.compute_threads = lambda: 8
        for label, data, kwargs, parallel in cases:
            path = Path(tmp) / f"{len(list(Path(tmp).iterdir()))}.mat"
            with h5py.File(path, "w") as f:
                f.create_dataset("dat", data=data, **kwargs)
            with h5py.File(path, "r") as f:
                got = mio._read_deflate_parallel(f["dat"], path)
                want = f["dat"][()].astype(np.float32)
            if parallel:
                check(f"parallel inflate: {label}",
                      got is not None and got.dtype == np.float32
                      and np.array_equal(got, want), "differs from h5py")
            else:
                check(f"parallel inflate declines: {label}", got is None)

        # Chunks never written read as the fill value; that is h5py's to do.
        path = Path(tmp) / "sparse.mat"
        with h5py.File(path, "w") as f:
            d = f.create_dataset("dat", shape=(8, 1000), dtype="f8",
                                 chunks=(8, 100), compression="gzip")
            d[:, :300] = 1.0
        with h5py.File(path, "r") as f:
            check("parallel inflate declines: unwritten chunks",
                  mio._read_deflate_parallel(f["dat"], path) is None)

        # End to end through load_raw_recording, as MATLAB lays out a v7.3
        # recording, against the plain read it replaced, at 1 and 8 threads.
        path = Path(tmp) / "recording.mat"
        dat = rng.standard_normal((16, 2000))
        with h5py.File(path, "w") as f:
            f.create_dataset("dat", data=dat, chunks=(16, 127),
                             compression="gzip", compression_opts=3)
            f.create_dataset("channels", data=np.arange(16)[None, :] + 11.0)
            f.create_dataset("fs", data=np.array([[12500.0]]))
        want = dat.T.astype(np.float32)
        for threads in (1, 8):
            mpar.compute_threads = lambda t=threads: t
            got, channels, fs = mio.load_raw_recording(path)
            check(f"load_raw_recording v7.3, threads={threads}",
                  np.array_equal(got, want) and got.dtype == want.dtype
                  and got.flags["F_CONTIGUOUS"] == want.flags["F_CONTIGUOUS"]
                  and np.array_equal(channels, np.arange(16) + 11) and fs == 12500.0)
    finally:
        mpar.compute_threads = _compute_threads


# ── 8. Spike-check frequency curves ───────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402

from meanap.pipeline.plotting import _frequency_curves  # noqa: E402
from meanap.pipeline.spike_detection import SpikeDetectionResult  # noqa: E402


def ref_frequency_curves(result, methods, d_samp_f, n_samples, n_channels):
    n_bins = int(np.ceil(n_samples / d_samp_f))
    curves = np.zeros((len(methods), n_bins))
    for i, method in enumerate(methods):
        spk_matrix = np.zeros((n_channels, n_bins))
        for ch_idx in result.spike_times:
            frames = np.round(result.spike_times[ch_idx].get(method, np.array([]))
                              * result.fs).astype(int)
            frames = frames[frames < n_samples]
            spk_vec = np.zeros(n_samples)
            spk_vec[frames] = 1
            pad_len = (d_samp_f - (n_samples % d_samp_f)) % d_samp_f
            if pad_len > 0:
                spk_vec = np.pad(spk_vec, (0, pad_len), constant_values=np.nan)
            spk_matrix[ch_idx, :] = np.nansum(spk_vec.reshape(-1, d_samp_f), axis=1)
        if result.spike_times:
            curves[i] = np.mean(spk_matrix[list(result.spike_times), :], axis=0)
    return curves


rng = np.random.default_rng(9)
fs = 1000.0
for n_samples, d_samp_f in ((10_000, 1000), (10_007, 1000), (999, 1000)):
    times = {}
    for ch in (0, 2, 3, 5):
        t = np.sort(rng.integers(0, n_samples + 50, 300)) / fs   # some past the end
        t = np.concatenate([t, t[:20]])                            # duplicate frames
        times[ch] = {"thr4": t, "bior1p5": t[::3], "empty": np.array([])}
    result = SpikeDetectionResult(times, {}, {}, np.arange(6), fs)
    methods = ["bior1p5", "empty", "thr4"]
    got = _frequency_curves(result, methods, SimpleNamespace(d_samp_f=d_samp_f),
                            n_samples, 6)
    want = ref_frequency_curves(result, methods, d_samp_f, n_samples, 6)
    check(f"frequency curves n={n_samples} bin={d_samp_f}", np.array_equal(got, want))


# ── 9. Wavelet thresholding ───────────────────────────────────────────────────

from meanap.pipeline import spike_detection as sd  # noqa: E402


def ref_detect_spikes_wavelet(signal, fs_hz, wid_ms=(0.4, 0.8), ns=5, option="l",
                              L=-0.12, wname="bior1.5"):
    """The thresholding as it was, building the kept-coefficient matrix."""
    signal = signal - signal.mean()
    Nt = len(signal)
    W = sd._determine_scales(wname, wid_ms, fs_hz, ns)
    c = sd._cwt_bior15(signal, W.astype(float))
    L_scaled = L * 36.7368
    Io = np.zeros(Nt, dtype=bool)
    ct = np.zeros((ns, Nt), dtype=float)
    for i in range(ns):
        stride = max(1, int(round(W[i])))
        Sigmaj = np.median(np.abs(c[i, ::stride] - c[i, :].mean())) / 0.6745
        if Sigmaj == 0:
            continue
        Thj = Sigmaj * np.sqrt(2 * np.log(Nt))
        index = np.where(np.abs(c[i, :]) > Thj)[0]
        if len(index) == 0:
            if option == "c":
                pass
            else:
                Mj = Thj
                PS = 1.0 / Nt
                PN = 1.0 - PS
                DTh = Mj / 2 + Sigmaj**2 / Mj * (L_scaled + np.log(PN / PS))
                DTh = abs(DTh) * (DTh >= 0)
                ind = np.where(np.abs(c[i, :]) > DTh)[0]
                if len(ind) > 0:
                    ct[i, ind] = c[i, ind]
        else:
            Mj = np.mean(np.abs(c[i, index]))
            PS = len(index) / Nt
            PN = 1.0 - PS
            DTh = Mj / 2 + Sigmaj**2 / Mj * (L_scaled + np.log(PN / PS))
            DTh = abs(DTh) * (DTh >= 0)
            ind = np.where(np.abs(c[i, :]) > DTh)[0]
            if len(ind) > 0:
                ct[i, ind] = c[i, ind]
        ct[i, ct[i, :] < 0] = 0
        Io = Io | (ct[i, :] != 0)
    return sd._parse_spike_index(Io.astype(int), fs_hz, wid_ms)


rng = np.random.default_rng(10)
fs = 12500.0
noise = rng.standard_normal(200_000)
spiky = noise.copy()
for t in rng.integers(100, 199_900, 400):
    spiky[t:t + 8] -= np.hanning(8) * 12
signals = {
    "noise (nothing above Thj at any scale)": noise,
    "noise + spikes": spiky,
    "slow sine (a few edge coefficients only)": np.sin(np.arange(200_000) / 2000.0),
    "constant (Sigmaj = 0)": np.ones(50_000),
}
for label, x in signals.items():
    for option, L in (("l", -0.12), ("c", -0.12), ("l", 0.5), ("l", -2.0)):
        got = sd.detect_spikes_wavelet(x, fs, option=option, L=L)
        want = ref_detect_spikes_wavelet(x, fs, option=option, L=L)
        check(f"wavelet {label}, option={option} L={L}", np.array_equal(got, want),
              f"{len(got)} vs {len(want)} spikes")

# Direct convolution against the FFT convolution it replaced: rounding only.
from scipy.signal import oaconvolve  # noqa: E402

W = sd._determine_scales("bior1.5", (0.4, 0.8), fs, 5).astype(float)
got = sd._cwt_bior15(spiky, W)
int_psi, xval = sd._get_bior15_intwave()
for i, a in enumerate(W):
    k = np.arange(0, np.floor(a * (xval[-1] - xval[0])) + 1)
    f = int_psi[np.floor(k / (a * (xval[1] - xval[0]))).astype(np.intp)][::-1]
    want = -np.sqrt(a) * sd._wkeep1_centre(np.diff(oaconvolve(spiky, f, mode="full")),
                                           len(spiky))
    err = np.max(np.abs(got[i] - want)) / np.max(np.abs(want))
    check(f"CWT scale {a:g}: direct vs FFT convolution within 1e-12", err < 1e-12,
          f"max relative difference {err:.1e}")


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All fast-path equivalence checks passed.")
