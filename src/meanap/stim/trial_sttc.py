"""STTC computed within each trial and averaged, with its trial-shuffle null.

:func:`~meanap.stim.evoked_network.epoch_network` normally lays a node's
windows end to end and computes one STTC over the joined train. STTC corrects
for firing rate through the fraction of time each train "tiles" (``T_A``),
but over the joined train that is one fraction for all trials. When the
culture is busier on some trials than others, two nodes that are both busier
on the same trials coincide more than a single ``T_A`` predicts, and the edge
reflects shared slow state rather than timing. Joining also lets spikes at
the end of one trial and the start of the next count as coincident.

Here each pair's STTC is computed within every trial's window alone (edges of
the window clipped, as for a recording's start and end) and averaged over the
trials in which both nodes fired; STTC is undefined when either is silent.
The rate correction then holds trial by trial, and no coincidence crosses a
trial boundary.

**Null.** The same trial shuffle: node A's trial *i* paired with node B's
trial *j*. For each pair, the STTC of every trial of A against every trial of
B is computed once (an ``n_trials × n_trials`` table); a surrogate is the
mean over one random pairing of rows with columns, read off the table.
Observed is the mean of its diagonal.
"""

from __future__ import annotations

import numpy as np

from meanap.pipeline.sttc import _HAVE_NUMBA, _run_p_jit, _run_t

#: A pair needs this many trials in which both nodes fired; fewer and its
#: STTC is left undefined (0, no edge) rather than resting on one or two trials.
MIN_VALID_TRIALS = 5


def _pair_impl(flat, starts, tiled, n_trials, dt, a, b, perms, min_valid, out_obs,
               out_null, out_ge, out_valid):
    """Observed and surrogate trial-mean STTC of nodes *a* and *b*."""
    table = np.full((n_trials, n_trials), np.nan)
    for i in range(n_trials):
        sa, ea = starts[a * n_trials + i], starts[a * n_trials + i + 1]
        n1 = ea - sa
        if n1 == 0:
            continue
        t1 = flat[sa:ea]
        ta = tiled[a * n_trials + i]
        for j in range(n_trials):
            sb, eb = starts[b * n_trials + j], starts[b * n_trials + j + 1]
            n2 = eb - sb
            if n2 == 0:
                continue
            t2 = flat[sb:eb]
            tb = tiled[b * n_trials + j]
            pa = _run_p_jit(t1, t2, dt) / n1
            pb = _run_p_jit(t2, t1, dt) / n2
            table[i, j] = 0.5 * (pa - tb) / (1 - tb * pa) + 0.5 * (pb - ta) / (1 - ta * pb)

    total, count = 0.0, 0
    for k in range(n_trials):
        v = table[k, k]
        if np.isfinite(v):
            total += v
            count += 1
    out_valid[a, b] = count
    if count < min_valid:
        out_obs[a, b] = np.nan
        return
    obs = total / count
    out_obs[a, b] = obs

    reps = perms.shape[0]
    null_total, ge = 0.0, 0
    for r in range(reps):
        s, c = 0.0, 0
        for k in range(n_trials):
            v = table[perms[r, a, k], perms[r, b, k]]
            if np.isfinite(v):
                s += v
                c += 1
        if c == 0:
            ge += 1               # no surrogate value: count against the edge
            continue
        s /= c
        null_total += s
        if s >= obs:
            ge += 1
    out_null[a, b] = null_total / reps
    out_ge[a, b] = ge


def _all_pairs_impl(flat, starts, tiled, n_nodes, n_trials, dt, perms, min_valid,
                    out_obs, out_null, out_ge, out_valid):
    for a in _prange(n_nodes):
        for b in range(a + 1, n_nodes):
            _pair(flat, starts, tiled, n_trials, dt, a, b, perms, min_valid,
                  out_obs, out_null, out_ge, out_valid)


if _HAVE_NUMBA:
    from numba import njit, prange as _prange

    _pair = njit(cache=True, error_model="numpy")(_pair_impl)
    _all_pairs = njit(cache=True, error_model="numpy", parallel=True)(_all_pairs_impl)
else:  # pragma: no cover - numba optional
    _prange = range
    _pair = _pair_impl
    _all_pairs = _all_pairs_impl


def trial_mean_sttc(segments: list[list[np.ndarray]], length: float, lag_ms: float,
                    rep_num: int, rng: np.random.Generator,
                    min_valid: int = MIN_VALID_TRIALS):
    """Trial-averaged STTC of every pair, and its trial-shuffle surrogates.

    *segments* is ``[node][trial]`` spike times relative to the window start,
    each window *length* s long. Returns ``(sttc, null_mean, p, n_valid)``,
    all ``(n, n)`` and symmetric: ``sttc`` NaN where fewer than *min_valid*
    trials had both nodes firing; ``p`` the permutation p-value
    ``(1 + #{surrogate ≥ observed}) / (1 + rep_num)``, 1 where undefined.
    """
    n = len(segments)
    n_trials = len(segments[0]) if n else 0
    dt = lag_ms / 1000.0
    parts = [np.sort(np.asarray(s, float)) for node in segments for s in node]
    starts = np.r_[0, np.cumsum([p.size for p in parts])].astype(np.int64)
    flat = np.concatenate(parts) if parts else np.zeros(0)
    tiled = np.array([_run_t(dt, 0.0, length, p) / length for p in parts], float)
    perms = np.empty((rep_num, n, n_trials), np.int64)
    for r in range(rep_num):
        for a in range(n):
            perms[r, a] = rng.permutation(n_trials)

    obs = np.full((n, n), np.nan)
    null = np.zeros((n, n))
    ge = np.zeros((n, n), np.int64)
    valid = np.zeros((n, n), np.int64)
    _all_pairs(flat, starts, tiled, n, n_trials, dt, perms, int(min_valid),
               obs, null, ge, valid)
    iu = np.triu_indices(n, 1)
    for m in (obs, null, ge, valid):
        m[(iu[1], iu[0])] = m[iu]
    p = (1 + ge) / (1 + rep_num)
    p[~np.isfinite(obs)] = 1.0
    np.fill_diagonal(p, 1.0)
    np.fill_diagonal(obs, 0.0)
    return obs, null, p, valid
