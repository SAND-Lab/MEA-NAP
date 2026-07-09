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

from typing import Iterator

import numpy as np


def randmio_und_signed(
    w: np.ndarray, iterations: int, rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Degree-preserving double-edge-swap randomization (Maslov & Sneppen 2002).

    ``iterations`` is a rewiring-attempts-per-edge multiplier, matching
    MATLAB's ``ITER`` input: total swap attempts = ``iterations * n*(n-1)/2``.
    """
    if rng is None:
        rng = np.random.default_rng()

    r = w.astype(float).copy()
    n = r.shape[0]
    total_iter = int(iterations * n * (n - 1) / 2)
    max_attempts = round(n / 2)

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

    n = w.shape[0]
    w = w.astype(float).copy()
    np.fill_diagonal(w, 0.0)
    ap = w > 0
    an = w < 0

    if np.count_nonzero(ap) < n * (n - 1):
        w_r = randmio_und_signed(w, bin_swaps, rng=rng)
        ap_r = w_r > 0
        an_r = w_r < 0
    else:
        ap_r = ap
        an_r = an

    w0 = np.zeros((n, n))
    wei_period = round(1 / wei_freq)

    for sign, a_mask, a_mask_r in ((1, ap, ap_r), (-1, an, an_r)):
        if sign == 1:
            s = (w * a_mask).sum(axis=1)
            wv = np.sort(w[np.triu(a_mask)])
        else:
            s = (-w * a_mask).sum(axis=1)
            wv = np.sort(-w[np.triu(a_mask)])

        iu, ju = np.nonzero(np.triu(a_mask_r))
        i_idx = list(iu)
        j_idx = list(ju)
        lij = [n * j + i for i, j in zip(i_idx, j_idx)]

        p = np.outer(s, s)
        wv = list(wv)

        m = len(wv)
        while m > 0:
            batch = min(m, wei_period)
            p_lij = p.flat[lij]
            oind = np.argsort(p_lij, kind="stable")
            r_idx = rng.choice(m, size=batch, replace=False)
            o = oind[r_idx]

            assigned_i = [i_idx[k] for k in o]
            assigned_j = [j_idx[k] for k in o]
            assigned_w = [wv[k] for k in r_idx]

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
            i_idx = [i_idx[k] for k in range(m) if keep[k]]
            j_idx = [j_idx[k] for k in range(m) if keep[k]]
            lij = [lij[k] for k in range(m) if keep[k]]
            keep_r = np.ones(m, dtype=bool)
            keep_r[r_idx] = False
            wv = [wv[k] for k in range(m) if keep_r[k]]

            m = len(wv)

    return w0 + w0.T


# ── Edge-swap rewiring for small-worldness (randmio_und_v2.m / latmio_und_v2.m) ──
#
# Distinct from randmio_und_signed above: these pick two *existing edges* to
# swap (by index into the nonzero lower-triangle) rather than four random
# node indices, and have no notion of sign (MEA-NAP only calls them on
# already-nonnegative adjacency matrices). Both batch their random draws for
# speed, same trick as ``randmio_und_signed``'s ``next_quad``.

def _valid_quad_stream(
    rng: np.random.Generator, k: int, i_arr: list[int], j_arr: list[int], batch_size: int = 8192,
) -> Iterator[tuple[int, int, int, int, int, int]]:
    """Yields ``(e1, e2, a, b, c, d)``: two distinct edge indices into
    ``i_arr``/``j_arr`` whose four endpoint nodes are all distinct.

    ``i_arr``/``j_arr`` are read fresh on each yield (not snapshotted), so
    callers may mutate them between ``next()`` calls — required, since the
    edge-flip step below does exactly that.
    """
    while True:
        e1_batch = rng.integers(0, k, size=batch_size)
        e2_batch = rng.integers(0, k, size=batch_size)
        for e1, e2 in zip(e1_batch.tolist(), e2_batch.tolist()):
            if e1 == e2:
                continue
            a, b = i_arr[e1], j_arr[e1]
            c, d = i_arr[e2], j_arr[e2]
            if a != c and a != d and b != c and b != d:
                yield e1, e2, a, b, c, d


def _coin_flip_stream(rng: np.random.Generator, batch_size: int = 8192) -> Iterator[bool]:
    while True:
        for v in rng.random(batch_size).tolist():
            yield v > 0.5


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
    i_arr_np, j_arr_np = np.nonzero(np.tril(r))
    i_arr, j_arr = i_arr_np.tolist(), j_arr_np.tolist()
    k = len(i_arr)
    if k < 2:
        return r

    max_attempts = round(n * k / (n * (n - 1)))
    quads = _valid_quad_stream(rng, k, i_arr, j_arr)
    flips = _coin_flip_stream(rng)

    for _ in range(iterations):
        for _attempt in range(max_attempts + 1):
            e1, e2, a, b, c, d = next(quads)
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

    i_arr_np, j_arr_np = np.nonzero(np.tril(r))
    i_arr, j_arr = i_arr_np.tolist(), j_arr_np.tolist()
    k = len(i_arr)
    if k >= 2:
        max_attempts = round(n * k / (n * (n - 1) / 2))
        quads = _valid_quad_stream(rng, k, i_arr, j_arr)
        flips = _coin_flip_stream(rng)

        for _ in range(iterations):
            for _attempt in range(max_attempts + 1):
                e1, e2, a, b, c, dd = next(quads)
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

    ind_rp_reverse = np.argsort(ind_rp)
    return r[np.ix_(ind_rp_reverse, ind_rp_reverse)]
