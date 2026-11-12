"""Is the response to a stimulus the same on every trial, and is its network?

Two questions the evoked-vs-baseline networks of :mod:`meanap.stim.evoked_network`
cannot answer, because they pool every trial:

**Drift over trials.** A culture stimulated sixty times may answer the first
stimulus differently from the last: it adapts, potentiates, or the electrode
drifts. Per node, the evoked-minus-baseline spike count on each trial is
tested for a monotonic trend (Spearman ρ against trial number). The *pattern*
of the response (which nodes answer, and how strongly) is compared between
every pair of trials. If it drifts, trials close together look more alike than
trials far apart, so similarity falls with trial separation. That fall is
tested against trials shuffled into a random order, which keeps every trial's
response but removes any order in them.

**Split-half networks.** A network is only worth interpreting if another set of
trials gives the same one. The trials are split two ways, and each half gets
its own epoch network:

* *odd vs even*: interleaved halves, so both span the whole recording. Their
  agreement is the network's reliability.
* *first vs second half*: agreement lower than odd vs even means the network
  changed over the recording, not just that it is noisy.

Agreement is the correlation of edge weights between the two halves. Edges of
one matrix are not independent (each node sits in n − 1 of them), so its
p-value is a Mantel test, which permutes the node labels of one half.

Inputs are spike trains and event times only, like :mod:`~meanap.stim.evoked_network`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from meanap.stim.evoked_network import baseline_window, trial_counts

#: The two ways trials are split: name → (description of half A, of half B).
SPLITS = {"odd_even": ("odd trials", "even trials"),
          "first_second": ("first half", "second half")}


# ── Drift over trials ─────────────────────────────────────────────────────────

@dataclass
class TrialConsistency:
    condition: str
    window_s: tuple[float, float]
    evoked: np.ndarray          # (n_trials, n) spike counts in the evoked window
    baseline: np.ndarray        # (n_trials, n) counts in the equally long window before
    latency_s: np.ndarray       # (n_trials, n) first spike after window start; NaN if none
    node_rho: np.ndarray        # (n,) Spearman ρ of response vs trial number
    node_p: np.ndarray          # (n,)
    evoked_drift: "PatternDrift"    # pattern of evoked counts across trials
    baseline_drift: "PatternDrift"  # the same before each event: the recording's own drift
    summary: dict

    @property
    def response(self) -> np.ndarray:
        return self.evoked - self.baseline


def first_spike_latency(trains: list[np.ndarray], events: np.ndarray,
                        window: tuple[float, float]) -> np.ndarray:
    """``(n_trials, n)`` time from each event to a node's first spike in
    ``[event + w0, event + w1)``; NaN when it does not fire there."""
    events = np.sort(np.asarray(events, float))
    out = np.full((len(events), len(trains)), np.nan)
    for j, t in enumerate(trains):
        t = np.asarray(t, float)
        if not t.size:
            continue
        i = np.searchsorted(t, events + window[0], side="left")
        ok = i < t.size
        first = np.where(ok, t[np.minimum(i, t.size - 1)], np.inf)
        hit = first < events + window[1]
        out[hit, j] = first[hit] - events[hit]
    return out


def pattern_similarity(counts: np.ndarray) -> np.ndarray:
    """Pearson correlation, over nodes, of every pair of trials' count vectors.

    A trial in which no node fires has no pattern; its row and column are NaN.
    """
    x = counts - counts.mean(axis=1, keepdims=True)
    norm = np.sqrt((x ** 2).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return (x @ x.T) / np.outer(norm, norm)


def similarity_by_lag(sim: np.ndarray) -> np.ndarray:
    """Mean of the *k*-th off-diagonal of *sim*, for k = 1 … n_trials − 1."""
    n = sim.shape[0]
    out = np.full(n - 1, np.nan)
    for k in range(1, n):
        d = np.diagonal(sim, offset=k)
        d = d[np.isfinite(d)]
        if d.size:
            out[k - 1] = d.mean()
    return out


def _lag_slope(lag_sim: np.ndarray, max_lag: int) -> float:
    """Least-squares slope of similarity on separation over lags 1 … *max_lag*.

    Only the first half of the lags is used: beyond that each lag rests on
    fewer pairs than it has trials to spare, and the last few on one or two.
    """
    k = np.arange(1, max_lag + 1, dtype=float)
    y = lag_sim[:max_lag]
    ok = np.isfinite(y)
    if ok.sum() < 3:
        return np.nan
    return float(np.polyfit(k[ok], y[ok], 1)[0])


@dataclass
class PatternDrift:
    """Does the pattern of counts across nodes change with trial order?"""

    similarity: np.ndarray      # (n_trials, n_trials) correlation of count patterns
    lag_similarity: np.ndarray  # (n_trials - 1,) mean similarity at trial separation k
    lag_null: np.ndarray        # (n_shuffles, n_trials - 1) the same, trial order shuffled
    slope: float                # similarity per trial of separation, lags 1 … n_trials // 2
    slope_p: float              # one-sided: falls faster than in shuffled orders

    @property
    def mean_similarity(self) -> float:
        ok = np.isfinite(self.lag_similarity)
        return float(self.lag_similarity[ok].mean()) if ok.any() else np.nan


def pattern_drift(counts: np.ndarray, n_shuffles: int,
                  rng: np.random.Generator) -> PatternDrift:
    """Similarity of every pair of trials' count patterns, and whether it
    falls with their separation more steeply than in a random trial order."""
    n_trials = counts.shape[0]
    sim = pattern_similarity(counts)
    lag_sim = similarity_by_lag(sim)
    lag_null = np.empty((n_shuffles, max(n_trials - 1, 0)))
    for s in range(n_shuffles):
        order = rng.permutation(n_trials)
        lag_null[s] = similarity_by_lag(sim[np.ix_(order, order)])
    max_lag = max(n_trials // 2, 1)
    slope = _lag_slope(lag_sim, max_lag)
    null_slopes = np.array([_lag_slope(row, max_lag) for row in lag_null])
    null_slopes = null_slopes[np.isfinite(null_slopes)]
    slope_p = (float((1 + np.sum(null_slopes <= slope)) / (1 + null_slopes.size))
               if np.isfinite(slope) and null_slopes.size else np.nan)
    return PatternDrift(similarity=sim, lag_similarity=lag_sim, lag_null=lag_null,
                        slope=slope, slope_p=slope_p)


def _spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    from scipy.stats import spearmanr

    if np.ptp(y) == 0 or len(y) < 4:
        return np.nan, np.nan
    res = spearmanr(x, y)
    return float(res.statistic), float(res.pvalue)


def trial_consistency(trains: list[np.ndarray], events: np.ndarray,
                      window: tuple[float, float], *, condition: str = "stim",
                      n_shuffles: int = 1000, alpha: float = 0.05,
                      rng: np.random.Generator | None = None) -> TrialConsistency:
    """Per-trial responses, their trend over trials, and the stability of their pattern.

    The drift test on the response pattern compares the slope of similarity
    against trial separation with *n_shuffles* random trial orders: a
    one-sided p-value for similarity falling faster with separation than chance.
    """
    rng = rng or np.random.default_rng()
    events = np.sort(np.asarray(events, float))
    evoked = trial_counts(trains, events, window)
    baseline = trial_counts(trains, events, baseline_window(window))
    response = evoked - baseline
    n_trials, n = evoked.shape
    trial_no = np.arange(1, n_trials + 1)

    rho, p = np.full(n, np.nan), np.full(n, np.nan)
    for j in range(n):
        rho[j], p[j] = _spearman(trial_no, response[:, j])

    ev_drift = pattern_drift(evoked, n_shuffles, rng)
    bl_drift = pattern_drift(baseline, n_shuffles, rng)

    pop = response.sum(axis=1)
    pop_rho, pop_p = _spearman(trial_no, pop)
    half = n_trials // 2
    tested = np.isfinite(p)
    latency = first_spike_latency(trains, events, window)
    with np.errstate(invalid="ignore"):
        lat_trial = np.nanmedian(latency, axis=1) if n else np.full(n_trials, np.nan)
    lat_ok = np.isfinite(lat_trial)
    lat_rho, lat_p = (_spearman(trial_no[lat_ok], lat_trial[lat_ok])
                      if lat_ok.sum() >= 4 else (np.nan, np.nan))
    summary = {
        "n_trials": n_trials,
        "meanPopResponse": float(pop.mean()) if n_trials else np.nan,
        "popResponseRho": pop_rho, "popResponseP": pop_p,
        "popResponseFirstHalf": float(pop[:half].mean()) if half else np.nan,
        "popResponseSecondHalf": float(pop[half:].mean()) if half else np.nan,
        "nNodesTested": int(tested.sum()),
        "fracNodesDrifting": float(np.mean(p[tested] < alpha)) if tested.any() else np.nan,
        "fracNodesDriftingUp": (float(np.mean((p[tested] < alpha) & (rho[tested] > 0)))
                                if tested.any() else np.nan),
        "meanPatternSimilarity": ev_drift.mean_similarity,
        "similarityLagSlope": ev_drift.slope, "similarityLagSlopeP": ev_drift.slope_p,
        "baselineSimilarityLagSlope": bl_drift.slope,
        "baselineSimilarityLagSlopeP": bl_drift.slope_p,
        "medianLatency_ms": float(np.nanmedian(lat_trial) * 1000) if lat_ok.any() else np.nan,
        "latencyRho": lat_rho, "latencyP": lat_p,
    }
    return TrialConsistency(
        condition=condition, window_s=tuple(window), evoked=evoked, baseline=baseline,
        latency_s=latency, node_rho=rho, node_p=p, evoked_drift=ev_drift,
        baseline_drift=bl_drift, summary=summary)


# ── Split-half networks ───────────────────────────────────────────────────────

def split_trials(n_trials: int, split: str) -> tuple[np.ndarray, np.ndarray]:
    """Indices of the two halves of ``range(n_trials)`` for *split* (:data:`SPLITS`)."""
    idx = np.arange(n_trials)
    if split == "odd_even":       # trial 1, 3, 5 … vs 2, 4, 6 … (1-based)
        return idx[0::2], idx[1::2]
    if split == "first_second":
        half = n_trials // 2
        return idx[:half], idx[half:]
    raise ValueError(f"Unknown split {split!r} ({', '.join(SPLITS)})")


def _upper(m: np.ndarray) -> np.ndarray:
    return m[np.triu_indices_from(m, k=1)]


def edge_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson r of the upper-triangle edge weights of *a* and *b*."""
    x, y = _upper(a), _upper(b)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def mantel(a: np.ndarray, b: np.ndarray, n_perm: int = 1000,
           rng: np.random.Generator | None = None) -> tuple[float, float]:
    """Edge-weight correlation of two symmetric matrices and its Mantel p-value.

    The null relabels the nodes of *b* at random (rows and columns together),
    which keeps each matrix's structure and breaks only the correspondence
    between them. One-sided: agreement greater than chance.
    """
    rng = rng or np.random.default_rng()
    r = edge_correlation(a, b)
    if not np.isfinite(r):
        return r, np.nan
    n = b.shape[0]
    null = np.empty(n_perm)
    for i in range(n_perm):
        o = rng.permutation(n)
        null[i] = edge_correlation(a, b[np.ix_(o, o)])
    null = null[np.isfinite(null)]
    return r, float((1 + np.sum(null >= r)) / (1 + null.size))


def edge_overlap(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Jaccard index of the nonzero edges of *a* and *b*, and its chance level.

    Chance is the Jaccard expected if each half's edges fell at random with
    the same densities: ``pa·pb / (pa + pb − pa·pb)``.
    """
    x, y = _upper(np.nan_to_num(a)) != 0, _upper(np.nan_to_num(b)) != 0
    union = np.sum(x | y)
    jac = float(np.sum(x & y) / union) if union else np.nan
    pa, pb = x.mean() if x.size else 0.0, y.mean() if y.size else 0.0
    denom = pa + pb - pa * pb
    return jac, float(pa * pb / denom) if denom else np.nan
