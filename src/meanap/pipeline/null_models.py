"""Degree/strength-preserving network randomization, ports of
``randmio_und_signed.m``, ``null_model_und_sign.m``, ``randmio_und_v2.m``
and ``latmio_und_v2.m`` (BCT / ``Functions/CC_PL_SW/``). The signed variants
are used by ``participation_coef_norm`` to normalize the participation
coefficient; ``randmio_und_v2``/``latmio_und_v2`` build the random and
lattice-like null models that ``network_metrics.small_worldness_rl_wu``
normalizes small-worldness against.

**Not bit-reproducible against MATLAB** — all four functions consume random
numbers from MATLAB's RNG, a different stream than Python's. Same situation
as Step 3's thresholding and Step 4's modularity: the *algorithm* is ported
faithfully and validated via structural invariants (e.g. degree sequence is
exactly preserved by construction), not by diffing against a specific
MATLAB run's specific random outcome.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

T = TypeVar("T")

# ``randmio_und_signed`` is the pipeline's single hottest Step-4 function
# (profiled at ~46% of Step 4 — 159M inner iterations of a sequential swap
# loop that can't be vectorized, since each accepted swap mutates the matrix
# the next one reads). That's the textbook case for a JIT. We compile the
# inner loop with numba when it's importable and fall back to an equivalent
# pure-NumPy implementation otherwise, so the module has no hard numba
# dependency — it just runs ~10-30x faster when numba is present.
try:
    from numba import njit

    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - numba optional / version-gated
    _HAVE_NUMBA = False


if _HAVE_NUMBA:

    @njit(cache=True, nogil=True)
    def _randmio_signed_core(r, sgn, total_iter, max_attempts, seed):  # pragma: no cover - jitted
        """In-place degree-preserving signed swaps on ``r`` (and its sign
        matrix ``sgn``). Compiled; uses numba's own RNG (seeded per call).
        ``sgn`` is kept consistent with ``r`` so sign comparisons are integer
        lookups rather than repeated ``np.sign`` calls.

        Releases the GIL, so several null models can rewire on threads at
        once. numba keeps one RNG state per thread and this seeds it before
        drawing, so a call's result does not depend on what else is running."""
        np.random.seed(seed)
        n = r.shape[0]
        for _ in range(total_iter):
            for _attempt in range(max_attempts + 1):
                # Draw 4 distinct nodes (retry distinctness without consuming
                # an attempt — matches the reference ``next_quad`` semantics).
                while True:
                    a = np.random.randint(0, n)
                    b = np.random.randint(0, n)
                    c = np.random.randint(0, n)
                    d = np.random.randint(0, n)
                    if a != b and a != c and a != d and b != c and b != d and c != d:
                        break

                s_ab = sgn[a, b]
                s_cd = sgn[c, d]
                s_ad = sgn[a, d]
                s_cb = sgn[c, b]

                if s_ab == s_cd and s_ad == s_cb and s_ab != s_ad:
                    r_ab = r[a, b]
                    r_cd = r[c, d]
                    r_ad = r[a, d]
                    r_cb = r[c, b]
                    r[a, d] = r_ab; r[a, b] = r_ad; r[d, a] = r_ab; r[b, a] = r_ad
                    r[c, b] = r_cd; r[c, d] = r_cb; r[b, c] = r_cd; r[d, c] = r_cb
                    sgn[a, d] = s_ab; sgn[a, b] = s_ad; sgn[d, a] = s_ab; sgn[b, a] = s_ad
                    sgn[c, b] = s_cd; sgn[c, d] = s_cb; sgn[b, c] = s_cd; sgn[d, c] = s_cb
                    break


def _randmio_signed_seeded(r: np.ndarray, iterations: int, seed: int) -> np.ndarray:
    """The numba path of :func:`randmio_und_signed`, on a float copy ``r``
    (rewired in place and returned) with its seed already drawn."""
    n = r.shape[0]
    total_iter = int(iterations * n * (n - 1) / 2)
    max_attempts = round(n / 2)
    sgn = np.sign(r).astype(np.int64)
    _randmio_signed_core(r, sgn, total_iter, max_attempts, seed)
    return r


def randmio_und_signed(
    w: np.ndarray, iterations: int, rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Degree-preserving double-edge-swap randomization (Maslov & Sneppen 2002).

    ``iterations`` is a rewiring-attempts-per-edge multiplier, matching
    MATLAB's ``ITER`` input: total swap attempts = ``iterations * n*(n-1)/2``.

    Uses a numba-compiled inner loop when available (see module note); the
    pure-NumPy fallback below is behaviourally equivalent (same swap rule,
    same distinct-quad sampling), just slower. Both preserve the degree
    sequence exactly by construction — the invariant the port is validated on.
    """
    if rng is None:
        rng = np.random.default_rng()

    r = w.astype(float).copy()
    n = r.shape[0]
    if n < 4:
        # A double-edge swap needs four distinct nodes. MATLAB's
        # randmio_und_signed.m draws them in a bare `while 1`, which spins
        # forever below n=4; MEA arrays are never that small, but a cell-type
        # subnetwork can be. Nothing is rewirable, so return the input.
        return r
    total_iter = int(iterations * n * (n - 1) / 2)
    max_attempts = round(n / 2)

    if _HAVE_NUMBA:
        return _randmio_signed_seeded(r, iterations, int(rng.integers(0, 2**31 - 1)))

    # ── Pure-NumPy fallback ──────────────────────────────────────────────────
    # rng.choice(n, size=4, replace=False) has surprisingly high per-call
    # overhead (array-machinery setup dominates for such a tiny sample) —
    # profiled at >85% of this function's runtime for realistic network
    # sizes. Draw big batches of candidate quads instead and filter for
    # distinctness, refilling as exhausted; net effect is the same
    # distribution (uniform random distinct 4-tuples), just far fewer
    # numpy-level calls.
    quad_buffer = np.empty((0, 4), dtype=np.int64)
    buffer_pos = 0

    def next_quad() -> tuple[int, int, int, int]:
        nonlocal quad_buffer, buffer_pos
        while True:
            if buffer_pos >= len(quad_buffer):
                quad_buffer = rng.integers(0, n, size=(4096, 4))
                buffer_pos = 0
            row = quad_buffer[buffer_pos]
            buffer_pos += 1
            if len(set(row.tolist())) == 4:
                return int(row[0]), int(row[1]), int(row[2]), int(row[3])

    for _ in range(total_iter):
        for _attempt in range(max_attempts + 1):
            a, b, c, d = next_quad()

            r0_ab = r[a, b]
            r0_cd = r[c, d]
            r0_ad = r[a, d]
            r0_cb = r[c, b]

            if (
                np.sign(r0_ab) == np.sign(r0_cd)
                and np.sign(r0_ad) == np.sign(r0_cb)
                and np.sign(r0_ab) != np.sign(r0_ad)
            ):
                r[a, d] = r0_ab
                r[a, b] = r0_ad
                r[d, a] = r0_ab
                r[b, a] = r0_ad
                r[c, b] = r0_cd
                r[c, d] = r0_cb
                r[b, c] = r0_cd
                r[d, c] = r0_cb
                break

    return r


def _stable_ranks(values: np.ndarray, ranks: np.ndarray) -> np.ndarray:
    """Indices of *values* at the given *ranks*, exactly as
    ``np.argsort(values, kind="stable")[ranks]`` would give them.

    The caller reads only a handful of ranks out of an ordering of every
    remaining edge, so sorting the whole array is nearly all wasted work.
    ``argpartition`` places just the requested ranks correctly in O(m) rather
    than O(m log m), and is 3-9x faster at the edge counts a dense calcium
    network reaches.

    It differs from a *stable* sort in one case: where the value at a
    requested rank is tied with another element, the two orderings may pick
    different members of the tied group. So the selected values are checked
    for duplicates, and a tie sends the call down the exact sorted path. The
    check costs one O(m) comparison per selected rank — a few percent of what
    it saves. (In practice ties do not arise here: the values are products of
    node strengths, and a run over a real 270-cell network saw none in 2597
    iterations. The fallback is for the networks that aren't that one.)
    """
    picked = np.argpartition(values, ranks)[ranks]
    selected = values[picked]
    tied = sum(np.count_nonzero(values == v) for v in selected.tolist())
    if tied != selected.shape[0]:
        return np.argsort(values, kind="stable")[ranks]
    return picked


@dataclass
class _NullPlan:
    """Every random number one :func:`null_model_und_sign` call uses.

    ``seed`` is the rewiring's (None when the network is not rewired, or
    numba is missing and the rewiring draws for itself), and ``choices``
    holds, per sign, the ``rng.choice`` draw of each weight-assignment pass.
    """

    rewire: bool
    seed: int | None
    choices: tuple[list[np.ndarray], list[np.ndarray]]


def _draw_null_plan(w: np.ndarray, bin_swaps: int, wei_freq: float,
                    rng: np.random.Generator) -> _NullPlan:
    """Draw a null model's random numbers in the order the model uses them.

    Possible because none of the draws depends on the rewired network: the
    rewiring takes one seed, and each weight-assignment pass draws a choice
    whose size depends only on how many edges of that sign the *original*
    network has (rewiring preserves the count). So the draws can be taken
    first, in order, and the expensive rewiring run afterwards, on any
    thread, with the result and the generator's final state unchanged.
    """
    n = w.shape[0]
    w = w.astype(float).copy()
    np.fill_diagonal(w, 0.0)
    ap = w > 0
    an = w < 0
    rewire = bool(np.count_nonzero(ap) < n * (n - 1))
    seed = None
    if rewire and _HAVE_NUMBA and n >= 4:
        seed = int(rng.integers(0, 2**31 - 1))
    elif rewire and n >= 4:
        raise RuntimeError("_draw_null_plan needs numba for the rewiring")

    wei_period = round(1 / wei_freq)
    choices: tuple[list[np.ndarray], list[np.ndarray]] = ([], [])
    for draws, a_mask in zip(choices, (ap, an)):
        m = int(np.count_nonzero(np.triu(a_mask)))
        while m > 0:
            batch = min(m, wei_period)
            draws.append(rng.choice(m, size=batch, replace=False))
            m -= batch
    return _NullPlan(rewire, seed, choices)


def _null_from_plan(w: np.ndarray, bin_swaps: int, wei_freq: float,
                    plan: _NullPlan | None, rng: np.random.Generator | None = None) -> np.ndarray:
    """Build the null model, taking random numbers from ``plan`` or, with no
    plan, straight from ``rng`` (the path without numba)."""
    n = w.shape[0]
    w = w.astype(float).copy()
    np.fill_diagonal(w, 0.0)
    ap = w > 0
    an = w < 0

    if np.count_nonzero(ap) < n * (n - 1):
        if plan is None:
            w_r = randmio_und_signed(w, bin_swaps, rng=rng)
        elif plan.seed is None:
            w_r = w.copy()  # n < 4: nothing is rewirable (see randmio_und_signed)
        else:
            w_r = _randmio_signed_seeded(w.copy(), bin_swaps, plan.seed)
        ap_r = w_r > 0
        an_r = w_r < 0
    else:
        ap_r = ap
        an_r = an

    w0 = np.zeros((n, n))
    wei_period = round(1 / wei_freq)

    for sign, a_mask, a_mask_r, planned in ((1, ap, ap_r, 0), (-1, an, an_r, 1)):
        if sign == 1:
            s = (w * a_mask).sum(axis=1)
            wv = np.sort(w[np.triu(a_mask)])
        else:
            s = (-w * a_mask).sum(axis=1)
            wv = np.sort(-w[np.triu(a_mask)])

        iu, ju = np.nonzero(np.triu(a_mask_r))
        i_idx = iu
        j_idx = ju
        lij = n * j_idx + i_idx

        p = np.outer(s, s)
        draws = iter(plan.choices[planned]) if plan is not None else None

        # ``i_idx``/``j_idx``/``lij``/``wv`` are kept as arrays rather than
        # lists: each pass drops only ``wei_period`` entries, so the loop runs
        # ~m/10 times and every list rebuild below would be O(m) *in Python*.
        # On a 64-electrode ephys network that is invisible; on a 270-cell
        # calcium recording (m ~ 7600) it was three quarters of CAT-NAP's
        # entire runtime. Masking the arrays is the same filter in C.
        m = wv.shape[0]
        while m > 0:
            batch = min(m, wei_period)
            p_lij = p.flat[lij]
            r_idx = next(draws) if draws is not None else rng.choice(m, size=batch, replace=False)
            o = _stable_ranks(p_lij, r_idx)

            # These three stay Python-level: they are ``batch`` (<=10) items,
            # so vectorising buys nothing, and the accumulation below has to
            # stay in this exact order to sum identically in floating point.
            assigned_i = i_idx[o].tolist()
            assigned_j = j_idx[o].tolist()
            assigned_w = wv[r_idx]

            for i_a, j_a, wa in zip(assigned_i, assigned_j, assigned_w):
                w0[i_a, j_a] = sign * wa

            wa_accum = np.zeros(n)
            for i_a, j_a, wa in zip(assigned_i, assigned_j, assigned_w):
                wa_accum[i_a] += wa
                wa_accum[j_a] += wa
            iju = wa_accum != 0
            if np.any(iju):
                f = 1.0 - np.divide(
                    wa_accum[iju], s[iju], out=np.ones_like(wa_accum[iju]), where=s[iju] != 0,
                )
                p[iju, :] *= f[:, None]
                p[:, iju] *= f[None, :]
                s[iju] -= wa_accum[iju]

            keep = np.ones(m, dtype=bool)
            keep[o] = False
            i_idx = i_idx[keep]
            j_idx = j_idx[keep]
            lij = lij[keep]
            keep_r = np.ones(m, dtype=bool)
            keep_r[r_idx] = False
            wv = wv[keep_r]

            m = wv.shape[0]

    return w0 + w0.T


def null_model_und_sign(
    w: np.ndarray,
    bin_swaps: int = 5,
    wei_freq: float = 0.1,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Randomize an undirected network, preserving degree and (approximately)
    strength distributions.

    Direct port of ``null_model_und_sign.m``'s ``wei_freq < 1`` (periodic
    re-sort) branch — the default in modern MATLAB (``nargin('randperm')~=1``
    always true in any MATLAB version this codebase targets), so the
    ``wei_freq==1`` exact-resort branch isn't ported.
    """
    if rng is None:
        rng = np.random.default_rng()
    plan = _draw_null_plan(w, bin_swaps, wei_freq, rng) if _HAVE_NUMBA else None
    return _null_from_plan(w, bin_swaps, wei_freq, plan, rng)


def map_null_models_und_sign(
    w: np.ndarray,
    count: int,
    fn: Callable[[np.ndarray], T],
    bin_swaps: int = 5,
    wei_freq: float = 0.1,
    rng: np.random.Generator | None = None,
    workers: int = 1,
) -> list[T]:
    """``[fn(null_model_und_sign(w, ...)) for _ in range(count)]``, on threads.

    Same null models, in the same order, and the same generator state
    afterwards, as ``count`` sequential calls: every model's random numbers are
    drawn first, in sequence (:func:`_draw_null_plan`), and only then are the
    models built, up to ``workers`` at a time. The rewiring that dominates the
    cost releases the GIL. ``fn`` reduces each model as soon as it is built,
    so ``count`` full matrices are never held at once.
    """
    if rng is None:
        rng = np.random.default_rng()
    if not _HAVE_NUMBA or workers <= 1 or count <= 1:
        return [fn(null_model_und_sign(w, bin_swaps, wei_freq, rng)) for _ in range(count)]
    plans = [_draw_null_plan(w, bin_swaps, wei_freq, rng) for _ in range(count)]
    with ThreadPoolExecutor(max_workers=min(workers, count)) as ex:
        return list(ex.map(lambda plan: fn(_null_from_plan(w, bin_swaps, wei_freq, plan)), plans))


# ── Edge-swap rewiring for small-worldness (randmio_und_v2.m / latmio_und_v2.m) ──
#
# Distinct from randmio_und_signed above: these pick two *existing edges* to
# swap (by index into the nonzero lower-triangle) rather than four random
# node indices, and have no notion of sign (MEA-NAP only calls them on
# already-nonnegative adjacency matrices).
#
# The swap loop is sequential (each accepted swap changes the edge list the
# next draw reads), so it is compiled with numba like randmio_und_signed. Unlike
# that function, it does not switch to numba's own RNG: the random numbers are
# still drawn from the caller's Generator, in batches of _DRAW_BATCH, by the
# Python wrapper. When the compiled loop runs out of a batch it returns, the
# wrapper draws the next one, and the loop resumes where it stopped. That
# keeps the draws in exactly the order the earlier pure-Python version made
# them, so seeded runs give the same null models, and so the same SW/SWw/CC/PL,
# as before the loop was compiled.

# Consecutive rejected draws after which the swap loop concludes the graph has
# no valid quad at all. See the deviation note in _rewire's docstring.
_QUAD_SEARCH_BUDGET = 2_000_000

# Random numbers drawn per refill: one batch of edge indices for e1, one for
# e2, or one batch of coin flips.
_DRAW_BATCH = 8192

# Why _edge_swap_core returned.
_SWAPS_DONE = 0
_NEED_EDGE_DRAWS = 1
_NEED_FLIP_DRAWS = 2
_NO_VALID_QUAD = 3

# Slots of the core's ``state`` array, which carries its loop position across
# a return-and-refill: the outer iteration, the attempt within it, the read
# position in each batch, the consecutive-rejection count, and a quad found
# just before the flip batch ran out (pending flag + its two edge indices).
_ITER, _ATTEMPT, _POS_E, _POS_F, _REJECTED, _PENDING, _E1, _E2 = range(8)


def _edge_swap_core(r, i_arr, j_arr, d, lattice, iterations, max_attempts, budget,
                    e1_batch, e2_batch, flips, state):  # pragma: no cover - jitted
    """The rewiring loop shared by ``randmio_und_v2`` and ``latmio_und_v2``.

    Mutates ``r``, ``i_arr``, ``j_arr`` and ``state`` in place and returns one
    of the ``_SWAPS_DONE``/``_NEED_*``/``_NO_VALID_QUAD`` codes. ``lattice``
    adds latmio's condition that a swap must not move edge weight onto more
    distant pairs (``d``); with it off, ``d`` is never read.
    """
    n_e = e1_batch.shape[0]
    n_f = flips.shape[0]
    it = state[_ITER]
    attempt = state[_ATTEMPT]
    pos_e = state[_POS_E]
    pos_f = state[_POS_F]
    rejected = state[_REJECTED]
    status = _SWAPS_DONE

    while it < iterations:
        swapped = False
        while attempt <= max_attempts:
            if state[_PENDING] == 0:
                # Draw edge pairs until both edges' four endpoints are distinct.
                found = False
                while not found:
                    if pos_e >= n_e:
                        status = _NEED_EDGE_DRAWS
                        break
                    e1 = e1_batch[pos_e]
                    e2 = e2_batch[pos_e]
                    pos_e += 1
                    if e1 != e2:
                        a = i_arr[e1]
                        b = j_arr[e1]
                        c = i_arr[e2]
                        dd = j_arr[e2]
                        if a != c and a != dd and b != c and b != dd:
                            rejected = 0
                            found = True
                            continue
                    rejected += 1
                    if rejected >= budget:
                        status = _NO_VALID_QUAD
                        break
                if not found:
                    break
                state[_PENDING] = 1
                state[_E1] = e1
                state[_E2] = e2
            if pos_f >= n_f:
                status = _NEED_FLIP_DRAWS
                break
            flip = flips[pos_f] > 0.5
            pos_f += 1
            state[_PENDING] = 0

            e1 = state[_E1]
            e2 = state[_E2]
            a = i_arr[e1]
            b = j_arr[e1]
            c = i_arr[e2]
            dd = j_arr[e2]
            if flip:
                i_arr[e2] = dd
                j_arr[e2] = c
                c, dd = dd, c
            # ``not (r[a, dd] or r[c, b])`` in the reference; a NaN counts as
            # an edge there, and ``== 0`` is False for NaN, so they agree.
            if r[a, dd] == 0 and r[c, b] == 0:
                if not lattice or (d[a, b] * r[a, b] + d[c, dd] * r[c, dd]
                                   >= d[a, dd] * r[a, b] + d[c, b] * r[c, dd]):
                    r_ab = r[a, b]
                    r_ba = r[b, a]
                    r_cd = r[c, dd]
                    r_dc = r[dd, c]
                    r[a, dd] = r_ab
                    r[a, b] = 0.0
                    r[dd, a] = r_ba
                    r[b, a] = 0.0
                    r[c, b] = r_cd
                    r[c, dd] = 0.0
                    r[b, c] = r_dc
                    r[dd, c] = 0.0
                    j_arr[e1] = dd
                    j_arr[e2] = b
                    swapped = True
                    break
            attempt += 1
        if status != _SWAPS_DONE:
            break
        it += 1
        attempt = 0

    state[_ITER] = it
    state[_ATTEMPT] = attempt
    state[_POS_E] = pos_e
    state[_POS_F] = pos_f
    state[_REJECTED] = rejected
    return status


if _HAVE_NUMBA:
    _edge_swap_core = njit(cache=True)(_edge_swap_core)


def _rewire(r: np.ndarray, d: np.ndarray, lattice: bool, iterations: int,
            max_attempts: int, rng: np.random.Generator) -> None:
    """Run the edge-swap loop on ``r`` in place, feeding it batches from ``rng``.

    **Deviation from MATLAB.** ``latmio_und_v2.m`` / ``randmio_und_v2.m`` search
    for a swappable edge pair in a bare ``while 1``, which never terminates on
    a graph where no two edges have four distinct endpoints — a triangle, a
    star, any small or degenerate component. MEA-NAP's ephys networks are
    large enough that MATLAB never hit it, but a cell-type subnetwork can
    easily be three or four cells, so the search is bounded here: after
    ``budget`` consecutive rejected draws, rewiring stops and the graph is
    left as it is. The budget is far beyond what any graph that *does* admit a
    swap would need, so this only changes behaviour where MATLAB would hang.
    """
    i_np, j_np = np.nonzero(np.tril(r))
    i_arr = np.ascontiguousarray(i_np, dtype=np.int64)
    j_arr = np.ascontiguousarray(j_np, dtype=np.int64)
    k = i_arr.shape[0]
    # A graph with any valid quad at all has at least ~2/k² of its draws
    # succeed, so scaling the budget with k² keeps the false-give-up
    # probability negligible while staying instant for the tiny graphs where
    # giving up is the correct answer.
    budget = min(_QUAD_SEARCH_BUDGET, max(10_000, 200 * k * k))

    # Both batches start "used up", so nothing is drawn before the loop asks:
    # the same lazy order the generator-based version drew in.
    e1_batch = np.zeros(_DRAW_BATCH, dtype=np.int64)
    e2_batch = np.zeros(_DRAW_BATCH, dtype=np.int64)
    flips = np.zeros(_DRAW_BATCH)
    state = np.zeros(8, dtype=np.int64)
    state[_POS_E] = _DRAW_BATCH
    state[_POS_F] = _DRAW_BATCH
    while True:
        status = _edge_swap_core(r, i_arr, j_arr, d, lattice, iterations, max_attempts,
                                 budget, e1_batch, e2_batch, flips, state)
        if status == _NEED_EDGE_DRAWS:
            e1_batch = rng.integers(0, k, size=_DRAW_BATCH)
            e2_batch = rng.integers(0, k, size=_DRAW_BATCH)
            state[_POS_E] = 0
        elif status == _NEED_FLIP_DRAWS:
            flips = rng.random(_DRAW_BATCH)
            state[_POS_F] = 0
        else:
            return


def randmio_und_v2(
    w: np.ndarray, iterations: int, rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Degree-preserving edge-swap null model, port of ``randmio_und_v2.m``.

    Used to build the random null model that ``network_metrics
    .small_worldness_rl_wu`` normalizes clustering coefficient and path
    length against. ``iterations`` is a rewiring-attempts-per-edge
    multiplier, matching MATLAB's ``ITER`` input.
    """
    if rng is None:
        rng = np.random.default_rng()

    r = w.astype(float).copy()
    n = r.shape[0]
    k = int(np.count_nonzero(np.tril(r)))
    if k < 2:
        return r

    max_attempts = round(n * k / (n * (n - 1)))
    _rewire(r, np.zeros((1, 1)), False, iterations, max_attempts, rng)
    return r


def latmio_und_v2(
    w: np.ndarray, iterations: int, d: np.ndarray, rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Lattice-like degree-preserving null model, port of ``latmio_und_v2.m``.

    ``d`` is the externally supplied "distance" matrix that biases which
    swaps count as more lattice-like — MEA-NAP passes
    ``squareform(pdist(adjM))`` (Euclidean distance between each node's
    *connectivity profile*, not spatial electrode distance; see
    ``ExtractNetMet.m``'s call site). Returns the latticized network in the
    original node ordering.
    """
    if rng is None:
        rng = np.random.default_rng()

    n = w.shape[0]
    ind_rp = rng.permutation(n)
    r = w[np.ix_(ind_rp, ind_rp)].astype(float).copy()

    k = int(np.count_nonzero(np.tril(r)))
    if k >= 2:
        max_attempts = round(n * k / (n * (n - 1) / 2))
        _rewire(r, np.ascontiguousarray(d, dtype=float), True, iterations, max_attempts, rng)

    ind_rp_reverse = np.argsort(ind_rp)
    return r[np.ix_(ind_rp_reverse, ind_rp_reverse)]
