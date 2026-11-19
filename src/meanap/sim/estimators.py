"""Pairwise measures from other papers, as networks MEA-Sim can score.

STTC is MEA-NAP's measure; these are the others MEA studies use, so the same
simulations can ask whether they do better. Each takes the spike trains and
returns a symmetric ``(n, n)`` matrix (signed where the measure has a sign;
the edge method sets negatives to 0, as the pipeline does for STTC, before
step 4 sees it). None is thresholded: they are weighted networks, scored by
how well their weights rank the truth.

Timescales follow the STTC lag (``lag_ms``), so a comparison at one lag is a
comparison at one timescale: counts are binned ``lag_ms`` wide (Cutts &
Eglen's choice for the spike count correlation), and smoothing kernels and
cross-correlation windows are ``lag_ms`` wide.

==============  ===============================================================
``pearson``     Pearson correlation of spike counts in bins ``lag_ms`` wide —
                the spike count correlation (Cohen & Kohn 2011).
``schreiber``   Schreiber et al. (2003) similarity: the cosine between the two
                trains convolved with a Gaussian of SD ``lag_ms``.
``cch``         Peak of the cross-correlogram within ±``lag_ms`` (1 ms bins),
                normalised by √(N_A·N_B) — the normalised cross-correlation
                used on MEAs by Pasquale et al. (2008).
``partial``     Partial correlation of the binned counts: each pair's
                correlation with every other recorded electrode held fixed
                (Eichler et al. 2003; on MEAs, Poli et al. 2016). Covariance
                shrunk (Ledoit–Wolf) before inverting.
``popreg``      Correlation of the binned counts of i and j with the summed
                count of every *other* electrode (neither i nor j) held fixed
                — what is left once the population rate is accounted for
                (after Okun et al.'s 2015 population coupling).
``xcov_within`` After Schroeter et al. (2015): inside each network burst,
                spikes in 1 ms bins, the normalised cross-covariance of each
                pair, peak over lags 1–15 ms either way (zero lag left out),
                averaged over bursts.
``te``          Delayed transfer entropy (Ito et al. 2011; Nigam et al. 2016):
                1 ms binary bins, one bin of history, the largest over delays
                1–``lag_ms`` ms, in bits; made undirected by taking the larger
                of the two directions.
==============  ===============================================================
"""

from __future__ import annotations

import numpy as np

__all__ = ["ESTIMATORS", "estimate", "binned"]

ESTIMATORS = ("pearson", "schreiber", "cch", "partial", "popreg", "xcov_within", "te")


def binned(trains: list[np.ndarray], T: float, bin_s: float) -> np.ndarray:
    """``(n, n_bins)`` spike counts."""
    nb = max(int(np.floor(T / bin_s)), 1)
    out = np.zeros((len(trains), nb))
    for i, t in enumerate(trains):
        k = (np.asarray(t) / bin_s).astype(int)
        k = k[(k >= 0) & (k < nb)]
        np.add.at(out[i], k, 1)
    return out


def _corr_rows(X: np.ndarray) -> np.ndarray:
    Z = X - X.mean(axis=1, keepdims=True)
    sd = np.sqrt((Z * Z).mean(axis=1))
    live = sd > 0
    out = np.full((len(X), len(X)), np.nan)
    Zl = Z[live] / sd[live, None]
    out[np.ix_(live, live)] = Zl @ Zl.T / X.shape[1]
    return out


def _pearson(trains, T, lag_s):
    return _corr_rows(binned(trains, T, lag_s))


def close_deltas(a: np.ndarray, b: np.ndarray, w: float) -> np.ndarray:
    """Every ``b − a`` within ±*w* (both sorted), without a Python loop."""
    if a.size == 0 or b.size == 0:
        return np.empty(0)
    lo = np.searchsorted(b, a - w, "left")
    hi = np.searchsorted(b, a + w, "right")
    counts = hi - lo
    total = int(counts.sum())
    if total == 0:
        return np.empty(0)
    rep = np.repeat(np.arange(a.size), counts)
    offs = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    return b[lo[rep] + offs] - a[rep]


def _gauss_overlap(a, b, sigma):
    """⟨a∗g, b∗g⟩ for a Gaussian g of SD σ: Σ exp(−Δ²/4σ²) over spike pairs."""
    d = close_deltas(a, b, 6 * sigma)
    return float(np.exp(-(d * d) / (4 * sigma * sigma)).sum())


def _schreiber(trains, T, lag_s):
    n = len(trains)
    norm = np.array([np.sqrt(_gauss_overlap(t, t, lag_s)) for t in trains])
    out = np.full((n, n), np.nan)
    for i in range(n):
        if norm[i] == 0:
            continue
        out[i, i] = 1.0
        for j in range(i + 1, n):
            if norm[j] > 0:
                out[i, j] = out[j, i] = _gauss_overlap(trains[i], trains[j], lag_s) / (
                    norm[i] * norm[j])
    return out


def _cch(trains, T, lag_s):
    n = len(trains)
    w = max(int(round(lag_s / 0.001)), 1)
    out = np.full((n, n), np.nan)
    for i in range(n):
        a = trains[i]
        if a.size == 0:
            continue
        for j in range(i + 1, n):
            b = trains[j]
            if b.size == 0:
                continue
            # Counts of b-spikes at each 1 ms lag from each a-spike, within ±w ms.
            d = close_deltas(a, b, (w + 0.5) * 0.001)
            hist = np.bincount(np.clip(np.round(d / 0.001).astype(int) + w, 0, 2 * w),
                               minlength=2 * w + 1)
            out[i, j] = out[j, i] = hist.max() / np.sqrt(a.size * b.size)
    return out


def _partial(trains, T, lag_s):
    from sklearn.covariance import LedoitWolf

    X = binned(trains, T, lag_s)
    n = len(X)
    live = X.std(axis=1) > 0
    out = np.full((n, n), np.nan)
    if live.sum() < 3:
        return out
    P = np.linalg.pinv(LedoitWolf().fit(X[live].T).covariance_)
    d = np.sqrt(np.diag(P))
    pc = -P / np.outer(d, d)
    out[np.ix_(live, live)] = pc
    return out


def _popreg(trains, T, lag_s):
    """Partial correlation of i and j given P = the summed counts of every other
    electrode (neither i nor j), from the covariance matrix alone."""
    X = binned(trains, T, lag_s)
    C = np.cov(X)
    s = C.sum(axis=1)                       # cov(i, total)
    S = C.sum()                             # var(total)
    d = np.diag(C)
    # P = total − x_i − x_j
    cov_iP = s[:, None] - d[:, None] - C    # cov(x_i, P_ij)
    cov_jP = cov_iP.T
    var_P = S - 2 * (s[:, None] + s[None, :]) + d[:, None] + d[None, :] + 2 * C
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = var_P > 0
        r_ij = C - np.where(ok, cov_iP * cov_jP / var_P, 0.0)
        r_ii = d[:, None] - np.where(ok, cov_iP ** 2 / var_P, 0.0)
        r_jj = d[None, :] - np.where(ok, cov_jP ** 2 / var_P, 0.0)
        out = r_ij / np.sqrt(r_ii * r_jj)
    out[~np.isfinite(out)] = np.nan
    return out


def _xcov_within(trains, T, lag_s, bin_s=0.001, max_lag=15):
    from meanap.sim.fit import detect_bursts

    n = len(trains)
    bursts = detect_bursts(trains, T)
    acc, cnt = np.zeros((n, n)), np.zeros((n, n))
    for a, b in bursts:
        nb = int(np.ceil((b - a) / bin_s))
        if nb <= 2 * max_lag:
            continue
        X = np.zeros((n, nb))
        for c in range(n):
            t = trains[c][(trains[c] >= a) & (trains[c] < b)]
            if len(t):
                np.add.at(X[c], np.minimum(((t - a) / bin_s).astype(int), nb - 1), 1)
        sd = X.std(axis=1)
        live = sd > 0
        if live.sum() < 2:
            continue
        Z = np.zeros_like(X)
        Z[live] = (X[live] - X[live].mean(1, keepdims=True)) / sd[live, None]
        best = np.full((n, n), -np.inf)
        for L in range(1, max_lag + 1):
            c = Z[:, :-L] @ Z[:, L:].T / nb
            best = np.maximum(best, np.maximum(c, c.T))
        both = live[:, None] & live[None, :]
        acc[both] += best[both]
        cnt[both] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)


def _te(trains, T, lag_s, bin_s=0.001):
    """Delayed transfer entropy i → j, max over delays, from 1 ms binary bins."""
    n = len(trains)
    nb = int(np.floor(T / bin_s))
    spikes = []
    X = np.zeros((n, nb + 1), bool)
    for i, t in enumerate(trains):
        k = np.unique((np.asarray(t) / bin_s).astype(int))
        k = k[(k >= 0) & (k < nb)]
        X[i, k] = True
        spikes.append(k)
    max_d = max(int(round(lag_s / bin_s)), 1)
    owner = np.concatenate([np.full(s.size, i) for i, s in enumerate(spikes)]) \
        if spikes else np.empty(0, int)
    allk = np.concatenate(spikes) if spikes else np.empty(0, int)
    te = np.zeros((n, n))
    for j in range(n):
        nxt, cur = X[j, 1:nb], X[j, :nb - 1]          # j(t+1), j(t) for t = 0 … nb-2
        masks = {(a, b): (nxt == a) & (cur == b) for a in (0, 1) for b in (0, 1)}
        tot = {ab: m.sum() for ab, m in masks.items()}
        best = np.zeros(n)
        for d in range(1, max_d + 1):
            t = allk + d - 1                             # i at t+1-d  ⇔  t = k + d - 1
            ok = (t >= 0) & (t < nb - 1)
            c1 = {ab: np.bincount(owner[ok], weights=m[t[ok]], minlength=n)
                  for ab, m in masks.items()}           # i spiked
            val = np.zeros(n)
            N = nb - 1
            for (a, b), m in masks.items():
                for c, cnt in ((1, c1[(a, b)]), (0, tot[(a, b)] - c1[(a, b)])):
                    n_bc = (c1[(0, b)] + c1[(1, b)]) if c == 1 else \
                        (tot[(0, b)] + tot[(1, b)] - c1[(0, b)] - c1[(1, b)])
                    n_ab = tot[(a, b)]
                    n_b = tot[(0, b)] + tot[(1, b)]
                    with np.errstate(divide="ignore", invalid="ignore"):
                        term = cnt / N * np.log2((cnt * n_b) / (n_bc * n_ab))
                    val += np.where(cnt > 0, term, 0.0)
            best = np.maximum(best, val)
        te[:, j] = best
    np.fill_diagonal(te, 0.0)
    return np.maximum(te, te.T)


_FUNCS = {"pearson": _pearson, "schreiber": _schreiber, "cch": _cch, "partial": _partial,
          "popreg": _popreg, "xcov_within": _xcov_within, "te": _te}


def estimate(name: str, trains: list[np.ndarray], T: float, lag_ms: float) -> np.ndarray:
    """The ``(n, n)`` matrix of estimator *name* (diagonal NaN)."""
    if name not in _FUNCS:
        raise ValueError(f"Unknown estimator {name!r}; expected one of {ESTIMATORS}")
    trains = [np.sort(np.asarray(t, float)) for t in trains]
    m = np.array(_FUNCS[name](trains, float(T), lag_ms / 1000.0), float)
    np.fill_diagonal(m, np.nan)
    return m
