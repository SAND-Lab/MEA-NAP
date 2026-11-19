"""MEA-NAP's own edge methods and network metrics, run on a simulation.

Nothing here reimplements the pipeline. STTC is
:func:`meanap.pipeline.sttc.get_sttc`, the nulls are
:func:`meanap.pipeline.probabilistic_threshold.adjm_thr` and the metrics are
step 4's :func:`meanap.pipeline.step4.compute_network_metrics`, so what a
sweep finds about a metric holds for the numbers a real run reports.

Edge methods
------------
``raw``       STTC between every pair, no threshold (a fully connected,
              weighted network).
``circular``  STTC, keeping edges above the circular-shift null (step 3's
              default).
``jitter``    STTC, keeping edges above the interval-jitter null.
``top``       STTC, keeping the strongest ``keep_frac`` of pairs: the same
              number of edges whatever the data (a proportional threshold).
``excess``    STTC minus its mean under the interval-jitter null, no
              threshold: how much more synchronous than the pair's own rate
              profiles (bursts included) predict.
``outside``   STTC on the spikes outside network bursts, with the burst
              periods cut out of the recording.
``within``    STTC inside network bursts only, the burst periods laid end to
              end — the within-burst view of Schroeter et al. (2015,
              *J Neurosci* 35:5459).

Measures from other papers (Pearson, Schreiber, cross-correlation, partial
correlation, population-regressed correlation, within-burst cross-covariance,
transfer entropy) are in :mod:`meanap.sim.estimators`; like STTC, their
negative values are set to 0 before step 4.

``outside`` and ``within`` find the bursts from the spikes
(:func:`meanap.sim.fit.detect_bursts`), as they would have to on a recording;
they are not told where the simulator put them.

Two views of what counts as correlation
---------------------------------------
``coactivation``  Being active together, for whatever reason, network bursts
                  included. The truth is how often a pair co-activates — in
                  the bursts they took part in together, and through their
                  coupling
                  (:func:`coactivation_truth`) — scored as the rank
                  correlation with each method's weights (``coactRho``).
``coupling``      Correlation beyond the bursts: the truth is the planted
                  graph alone, scored by ``edgeAUC``/``recall``/
                  ``falsePosRate`` on each method's weights.

Edge recovery is scored against the planted graph: the AUC of the raw STTC
(how well edge weight ranks true edges above non-edges, 0.5 = chance), and for
each method the share of true edges kept (recall) and of non-edges kept
(false-positive rate). These count excitatory edges only.

Inhibitory edges are scored apart, on the *signed* STTC — the values the
pipeline zeroes when negative (``get_sttc(..., clip=False)``): how well a low
STTC picks out inhibitory pairs from unconnected ones (``inhibAUC``), their mean
STTC (``inhibSTTC``), and the share of them any method kept as an edge
(``inhibKept`` — they can only be kept with a positive weight, which is the
wrong sign).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from meanap.sim.model import SimResult

__all__ = [
    "EDGE_METHODS", "VIEWS", "VIEW_METHODS", "DEFAULT_METHODS", "coactivation_truth", "splice", "EdgeSettings", "Measured", "edge_matrix", "measure",
    "planted_metrics", "METRICS", "DEFAULT_METRICS", "metric_label",
]

EDGE_METHODS = {
    "raw": "STTC, no threshold",
    "circular": "STTC + circular-shift null",
    "top": "STTC, strongest pairs only",
    "jitter": "STTC + jitter null",
    "excess": "STTC above jitter expectation",
    "outside": "STTC outside bursts",
    "within": "STTC within bursts",
    # from other papers (meanap.sim.estimators)
    "pearson": "Pearson correlation of counts",
    "schreiber": "Schreiber similarity",
    "cch": "Cross-correlation peak (Pasquale)",
    "partial": "Partial correlation",
    "popreg": "Correlation beyond population rate",
    "xcov_within": "Within-burst cross-covariance (Schroeter)",
    "te": "Transfer entropy",
}

#: Methods that decide which pairs are edges. The others weight every pair,
#: so "edges found" and "false positives" do not apply to them (see edgeAUC).
THRESHOLDED = ("circular", "jitter", "top")

#: What counts as correlation (see the module docstring).
VIEWS = {
    "coactivation": "Co-activation, including bursts",
    "coupling": "Beyond bursts — coupling only",
}

#: The methods built for each view, checked by default when it is chosen.
VIEW_METHODS = {
    "coactivation": ("raw", "circular", "top", "pearson", "schreiber", "cch"),
    "coupling": ("jitter", "excess", "outside", "within", "partial", "popreg", "xcov_within",
                 "te"),
}

#: Checked when a view is chosen: a few that answer it, and quick to run.
DEFAULT_METHODS = {
    "coactivation": ("raw", "circular", "pearson"),
    "coupling": ("jitter", "excess", "partial", "popreg"),
}

#: Metrics a sweep can follow: step 4's scalars plus edge recovery and mean STTC.
METRICS = {
    "meanSTTC": "Mean STTC (all pairs)",
    "coactRho": "Co-activation recovered (rank r)",
    "edgeAUC": "Planted edges recovered (AUC)",
    "recall": "True (excitatory) edges found",
    "falsePosRate": "False-positive edge rate",
    "inhibKept": "Inhibitory pairs kept as edges",
    "inhibAUC": "Inhibitory edges found (AUC, signed STTC)",
    "inhibSTTC": "Mean signed STTC of inhibitory pairs",
    "fracNegative": "Pairs with negative STTC",
    "Dens": "Density",
    "NDmean": "Mean node degree",
    "NSmean": "Mean node strength",
    "sigEdgesMean": "Mean edge weight",
    "Q": "Modularity (Q)",
    "nMod": "Number of modules",
    "PCmean": "Mean participation coefficient",
    "Eglob": "Global efficiency",
    "ElocMean": "Mean local efficiency",
    "CC": "Clustering (normalised)",
    "PL": "Path length (normalised)",
    "SW": "Small-worldness",
    "aveControlMean": "Mean average controllability",
    "modalControlMean": "Mean modal controllability",
}

DEFAULT_METRICS = ("meanSTTC", "coactRho", "edgeAUC", "recall", "falsePosRate", "inhibAUC",
                   "Dens", "NDmean", "sigEdgesMean", "Q", "PCmean", "Eglob", "SW",
                   "modalControlMean")


def metric_label(key: str) -> str:
    return METRICS.get(key, key)


@dataclass
class EdgeSettings:
    """How edges are estimated, as in the Connectivity tab."""

    lag_ms: float = 10.0
    rep_num: int = 100
    tail: float = 0.05
    #: Jitter window as a multiple of the lag, as ``Params.prob_thresh_jitter_lags``.
    jitter_lags: float = 5.0
    keep_frac: float = 0.10
    #: Margin cut around each detected burst by ``outside`` (and added by ``within``).
    burst_pad_ms: float = 100.0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def jitter_ms(self) -> float:
        return self.jitter_lags * self.lag_ms


@dataclass
class Measured:
    """One edge method's network and its metrics."""

    method: str
    adjacency: np.ndarray        # weighted, as step 4 receives it
    metrics: dict[str, float]
    #: The signed STTC the weights came from (the same for every method).
    signed: np.ndarray | None = None


def _keep_top(raw: np.ndarray, frac: float) -> np.ndarray:
    n = len(raw)
    iu = np.triu_indices(n, 1)
    vals = raw[iu]
    k = int(round(np.clip(frac, 0.0, 1.0) * vals.size))
    out = np.zeros_like(raw)
    if k > 0:
        keep = np.argsort(-vals, kind="stable")[:k]
        keep = keep[vals[keep] > 0]
        out[iu[0][keep], iu[1][keep]] = vals[keep]
        out += out.T
    return out


def edge_matrix(sim: SimResult, method: str, settings: EdgeSettings,
                rng: np.random.Generator, raw: np.ndarray | None = None) -> np.ndarray:
    """The weighted network *method* gives for *sim*."""
    from meanap.pipeline.probabilistic_threshold import adjm_thr
    from meanap.pipeline.sttc import get_sttc

    d, n, T = sim.spike_dict(), sim.n, sim.duration_s
    if method in ("circular", "jitter"):
        _, thr = adjm_thr(d, n, settings.lag_ms, settings.tail, 25000.0, T,
                          int(settings.rep_num), rng=rng, null=method,
                          jitter_ms=settings.jitter_ms)
        return thr
    if raw is None:
        raw = get_sttc(d, n, settings.lag_ms, T)
    if method == "raw":
        return raw
    if method == "top":
        return _keep_top(raw, settings.keep_frac)
    if method == "excess":
        return _excess(sim, settings, rng)
    from meanap.sim.estimators import ESTIMATORS, estimate

    if method in ESTIMATORS:
        m = np.nan_to_num(estimate(method, sim.trains, T, settings.lag_ms))
        m[m < 0] = 0.0          # as the pipeline does for STTC: weights are ≥ 0
        np.fill_diagonal(m, 0.0)
        return m
    if method in ("outside", "within"):
        return _burst_split(sim, settings, inside=method == "within")
    raise ValueError(f"Unknown edge method {method!r}; expected one of {list(EDGE_METHODS)}")


def _excess(sim: SimResult, settings: EdgeSettings, rng) -> np.ndarray:
    """STTC minus its mean over interval-jitter surrogates, negatives set to 0."""
    from meanap.pipeline.probabilistic_threshold import surrogate_spikes
    from meanap.pipeline.sttc import get_sttc

    d, n, T = sim.spike_dict(), sim.n, sim.duration_s
    real = np.nan_to_num(get_sttc(d, n, settings.lag_ms, T, clip=False))
    reps = int(np.clip(settings.rep_num, 5, 40))   # a mean needs far fewer than a tail
    null = np.zeros((n, n))
    for _ in range(reps):
        synth = surrogate_spikes(d, n, 25000.0, T, rng, null="jitter",
                                 jitter_ms=settings.jitter_ms)
        null += np.nan_to_num(get_sttc(synth, n, settings.lag_ms, T, clip=False))
    out = real - null / reps
    out[out < 0] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def _merge(intervals: np.ndarray) -> np.ndarray:
    out: list[list[float]] = []
    for a, b in intervals[np.argsort(intervals[:, 0])]:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return np.array(out).reshape(-1, 2)


def splice(trains: list[np.ndarray], keep: np.ndarray) -> tuple[list[np.ndarray], float]:
    """Keep only the spikes inside *keep* intervals and close the gaps, as if
    those stretches had been recorded back to back. Returns the new trains and
    their total length."""
    if keep.size == 0:
        return [np.empty(0) for _ in trains], 0.0
    lengths = keep[:, 1] - keep[:, 0]
    offset = np.concatenate([[0.0], np.cumsum(lengths)[:-1]])
    out = []
    for t in trains:
        k = np.searchsorted(keep[:, 0], t, "right") - 1
        ok = (k >= 0)
        ok[ok] &= t[ok] < keep[k[ok], 1]
        out.append(t[ok] - keep[k[ok], 0] + offset[k[ok]])
    return out, float(lengths.sum())


def _burst_split(sim: SimResult, settings: EdgeSettings, inside: bool) -> np.ndarray:
    """STTC outside (or inside) the network bursts found in *sim*'s spikes."""
    from meanap.pipeline.sttc import get_sttc
    from meanap.sim.fit import detect_bursts

    T, n = sim.duration_s, sim.n
    bursts = detect_bursts(sim.trains, T)
    pad = settings.burst_pad_ms / 1000.0
    if bursts.size:
        bursts = _merge(np.clip(np.column_stack([bursts[:, 0] - pad, bursts[:, 1] + pad]), 0, T))
    if inside:
        keep = bursts
    else:
        edges = np.concatenate([[0.0], bursts.ravel(), [T]]).reshape(-1, 2)
        keep = edges[edges[:, 1] > edges[:, 0]]
    trains, length = splice(sim.trains, keep)
    if length <= 4 * settings.lag_ms / 1000.0:
        return np.zeros((n, n))
    return get_sttc(dict(enumerate(trains)), n, settings.lag_ms, length)


def coactivation_truth(sim: SimResult) -> np.ndarray:
    """How strongly each pair co-activates, by construction: the bursts both
    joined (as a share of all bursts), plus their coupling (minus it if they
    inhibit). For bursts that spread, each shared burst counts by how close
    the two joined it in time (``exp(−|Δonset| / spread)``, the spread being a
    quarter of the burst width): joining the same burst 60 ms apart is less
    "together" than 5 ms apart. A ranking target, not an STTC value."""
    n = sim.n
    shared = np.zeros((n, n))
    joins = sim.burst_joins
    if joins is not None and joins.shape[1]:
        nb = joins.shape[1]
        if sim.burst_onsets is not None:
            on = sim.burst_onsets
            tau = max(sim.spec.burst_width_ms / 4000.0, 1e-3)
            for b in range(nb):
                o = on[:, b]
                ok = np.isfinite(o)
                w = np.zeros((n, n))
                w[np.ix_(ok, ok)] = np.exp(-np.abs(o[ok, None] - o[None, ok]) / tau)
                shared += w
            shared /= nb
        else:
            j = joins.astype(float)
            shared = (j @ j.T) / nb
    c = sim.spec.coupling
    out = shared + c * sim.excitatory - c * sim.inhibitory
    np.fill_diagonal(out, 0.0)
    return out


def _rank_r(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import spearmanr

    if a.size < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return np.nan
    return float(spearmanr(a, b).statistic)


def _auc(scores: np.ndarray, truth: np.ndarray) -> float:
    """Mann–Whitney AUC: P(a true edge outscores a non-edge), ties half."""
    pos, neg = scores[truth], scores[~truth]
    if pos.size == 0 or neg.size == 0:
        return np.nan
    from scipy.stats import rankdata

    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def _scalars(metrics: dict) -> dict[str, float]:
    return {k: float(v) for k, v in metrics.items()
            if np.isscalar(v) and isinstance(v, (int, float, np.integer, np.floating))}


def network_metrics(adj: np.ndarray, counts: np.ndarray, duration_s: float,
                    rng: np.random.Generator) -> dict[str, float]:
    """Step 4's scalar metrics for one weighted network."""
    from meanap.params import Params
    from meanap.pipeline.step4 import compute_network_metrics

    return _scalars(compute_network_metrics(adj, counts, duration_s, 0.0, 3,
                                            params=Params(), rng=rng))


def measure(sim: SimResult, methods=("raw", "circular", "jitter"),
            settings: EdgeSettings | None = None, seed: int = 1,
            with_metrics: bool = True) -> dict[str, Measured]:
    """Every edge method's network and metrics for *sim*."""

    settings = settings or EdgeSettings()
    rng = np.random.default_rng([int(seed), 0xED6E])
    signed = signed_sttc(sim, settings.lag_ms)
    raw = np.nan_to_num(np.where(signed < 0, 0.0, signed))   # what get_sttc returns
    np.fill_diagonal(raw, 0.0)
    iu = np.triu_indices(sim.n, 1)
    exc, inh = sim.excitatory[iu], sim.inhibitory[iu]
    none = ~sim.adjacency[iu]
    s_up = signed[iu]
    pool = exc | none
    truth1 = coactivation_truth(sim)[iu]
    common = {
        "meanSTTC": float(np.mean(raw[iu])) if iu[0].size else np.nan,
        "inhibAUC": _auc(-np.nan_to_num(s_up[inh | none]), inh[inh | none]),
        "inhibSTTC": float(np.nanmean(s_up[inh])) if inh.any() else np.nan,
        "fracNegative": float(np.mean(s_up[np.isfinite(s_up)] < 0)) if iu[0].size else np.nan,
    }
    counts = sim.spike_counts()
    out = {}
    for m in methods:
        adj = edge_matrix(sim, m, settings, rng, raw=raw)
        w = adj[iu]
        kept = w > 0
        binary = m in THRESHOLDED
        rec = {
            "edgeAUC": _auc(w[pool], exc[pool]),
            "coactRho": _rank_r(w, truth1),
            "recall": float(kept[exc].mean()) if exc.any() and binary else np.nan,
            "falsePosRate": float(kept[none].mean()) if none.any() and binary else np.nan,
            "inhibKept": float(kept[inh].mean()) if inh.any() and binary else np.nan,
            "nEdges": float(kept.sum()),
        }
        metrics = network_metrics(adj, counts, sim.duration_s, rng) if with_metrics else {}
        out[m] = Measured(m, adj, {**common, **rec, **metrics}, signed)
    return out


def signed_sttc(sim: SimResult, lag_ms: float) -> np.ndarray:
    """STTC with its sign kept (NaN for empty trains and on the diagonal)."""
    from meanap.pipeline.sttc import get_sttc

    return get_sttc(sim.spike_dict(), sim.n, lag_ms, sim.duration_s, clip=False)


def planted_metrics(sim: SimResult, seed: int = 1) -> dict[str, float]:
    """Step 4's metrics on the planted graph itself (edge weight = coupling).

    The reference for the shape metrics (density, modularity, participation):
    what an edge method would report if it recovered the graph exactly.
    """
    adj = sim.excitatory.astype(float) * max(sim.spec.coupling, 1e-6)
    rng = np.random.default_rng([int(seed), 0x7AB1E])
    m = network_metrics(adj, np.maximum(sim.spike_counts(), 1.0), sim.duration_s, rng)
    m.update(recall=1.0, falsePosRate=0.0, edgeAUC=1.0, coactRho=np.nan,
             inhibAUC=1.0 if sim.inhibitory.any() else np.nan)
    return m
