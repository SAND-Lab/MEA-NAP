"""Stimulus-triggered functional networks: evoked vs baseline, and noise correlations.

Steps 3–4 build one network over a whole recording. With a stimulus that
drives many nodes at once — a full-field flash — that network mixes two
things: nodes that interact, and nodes that merely answer the same stimulus.
This module separates them, per stimulus condition:

**Epoch networks.** Every node's spikes are cut to a window after each event
(*evoked*) and to an equally long window before it (*baseline*), the windows
are laid end to end, and the pipeline's own STTC
(:func:`~meanap.pipeline.sttc.get_sttc`) and network metrics
(:func:`~meanap.pipeline.step4.compute_network_metrics`) run on the result.

The significance test is the point. Step 3's circular-shift surrogates slide
each train against the others, which breaks every node's alignment to the
stimulus — so any shared response would pass as an edge. The default here is a
**trial shuffle** (the shift predictor): each node's windows are reordered
across trials independently. Each node keeps its stimulus-locked response
exactly; only which trial its spikes came from is scrambled. An edge that
survives is co-variation *beyond* what the stimulus explains. ``null =
"circular"`` gives step 3's test instead, for total co-activity.

**Noise correlations.** Per condition, the trial-by-trial spike counts of
every pair, correlated after each node's mean response is removed (Pearson
on counts — the classic measure of shared trial-to-trial variability). Same
trial shuffle for the p-values.

Inputs are spike trains and event times only, so this works for any event
source (:mod:`meanap.stim.events`) and for detected or sorted nodes alike.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from meanap.pipeline.sttc import get_sttc

NULLS = ("trial_shuffle", "circular")


@dataclass
class EpochNetwork:
    """One condition × epoch: the STTC matrix and its thresholded version."""

    condition: str
    epoch: str                     # "evoked" | "baseline"
    window_s: tuple[float, float]  # relative to each event
    lag_ms: float
    null: str
    n_trials: int
    duration_s: float              # total length of the concatenated windows
    sttc: np.ndarray               # (n, n) raw
    sttc_thr: np.ndarray           # (n, n) edges not beating the null zeroed
    null_mean: np.ndarray          # (n, n) mean surrogate STTC (shift predictor)
    p: np.ndarray                  # (n, n) permutation p-value of each edge
    spike_counts: np.ndarray       # (n,) spikes inside the windows


def baseline_window(window: tuple[float, float]) -> tuple[float, float]:
    """The pre-event window as long as *window* that ends at the event."""
    length = window[1] - window[0]
    return (-length, 0.0)


def separated_events(events: np.ndarray, window: tuple[float, float]) -> np.ndarray:
    """Which events have both windows clear of their neighbours' windows.

    An event's baseline must not reach back into the previous event's evoked
    window, nor its evoked window run into the next event's baseline — each
    spike has to belong to one trial. Returns a boolean mask over *events*
    (sorted); an event too close to a neighbour is dropped rather than the
    whole recording refused.
    """
    events = np.sort(np.asarray(events, float))
    need = window[1] - baseline_window(window)[0]
    gaps = np.diff(events)
    ok_prev = np.r_[True, gaps >= need]
    ok_next = np.r_[gaps >= need, True]
    return ok_prev & ok_next


def check_windows_fit(events: np.ndarray, window: tuple[float, float]) -> float:
    """Shortest gap between events, raising if evoked and baseline windows of
    consecutive events would overlap (each spike must belong to one trial)."""
    events = np.sort(np.asarray(events, float))
    if len(events) < 2:
        return np.inf
    gap = float(np.min(np.diff(events)))
    need = window[1] - baseline_window(window)[0]
    if gap < need:
        raise ValueError(
            f"events {gap:.3f} s apart, but the evoked window {window} and its "
            f"baseline need {need:.3f} s — shorten the window")
    return gap


def trial_segments(train: np.ndarray, events: np.ndarray,
                   window: tuple[float, float]) -> list[np.ndarray]:
    """A node's spikes in ``[event + w0, event + w1)``, per event, relative
    to the window start."""
    train = np.asarray(train, float)
    w0, w1 = window
    lo = np.searchsorted(train, events + w0, side="left")
    hi = np.searchsorted(train, events + w1, side="left")
    return [train[a:b] - (e + w0) for a, b, e in zip(lo, hi, events)]


def concatenate(segments: list[np.ndarray], length: float,
                order: np.ndarray | None = None) -> np.ndarray:
    """Trials laid end to end, in *order* (default: as recorded)."""
    order = np.arange(len(segments)) if order is None else order
    parts = [segments[k] + i * length for i, k in enumerate(order)]
    return np.concatenate(parts) if parts else np.zeros(0)


def epoch_network(trains: list[np.ndarray], events: np.ndarray,
                  window: tuple[float, float], lag_ms: float, *,
                  condition: str = "stim", epoch: str = "evoked",
                  null: str = "trial_shuffle", rep_num: int = 200,
                  tail: float = 0.05, fs: float = 25000.0,
                  rng: np.random.Generator | None = None) -> EpochNetwork:
    """STTC network of the concatenated *window*-after-event epochs.

    An edge is kept when its permutation p-value, ``(1 + #{surrogate ≥
    observed}) / (1 + rep_num)``, is below *tail*. This deliberately differs
    from step 3's :func:`~meanap.pipeline.probabilistic_threshold.adjm_thr`
    (kept when STTC ≥ the ``1 - tail`` quantile — MATLAB's rule), which counts
    ties with the surrogates as wins: with the few spikes of short windows
    ties are common, and that rule's false-positive rate was measured at ~9 %
    for a nominal 5 % on ``python/test_evoked_network.py``'s data.
    """
    if null not in NULLS:
        raise ValueError(f"Unknown null {null!r} ({', '.join(NULLS)})")
    rng = rng or np.random.default_rng()
    events = np.sort(np.asarray(events, float))
    n, n_trials = len(trains), len(events)
    length = window[1] - window[0]
    duration = n_trials * length
    segs = [trial_segments(t, events, window) for t in trains]
    observed = {i: concatenate(s, length) for i, s in enumerate(segs)}
    sttc = get_sttc(observed, n, lag_ms, duration)
    np.fill_diagonal(sttc, 0.0)

    surrogate = np.empty((n, n, rep_num))
    for r in range(rep_num):
        if null == "trial_shuffle":
            synth = {i: concatenate(s, length, rng.permutation(n_trials))
                     for i, s in enumerate(segs)}
        else:
            from meanap.pipeline.probabilistic_threshold import circular_shift_spikes
            synth = circular_shift_spikes(observed, n, fs, duration, rng)
        adj = get_sttc(synth, n, lag_ms, duration)
        np.fill_diagonal(adj, 0.0)
        surrogate[:, :, r] = adj

    p = (1 + np.sum(surrogate >= sttc[:, :, None], axis=2)) / (1 + rep_num)
    sttc_thr = sttc.copy()
    sttc_thr[p >= tail] = 0.0
    sttc_thr[sttc_thr < 0] = 0.0
    return EpochNetwork(
        condition=condition, epoch=epoch, window_s=tuple(window), lag_ms=lag_ms,
        null=null, n_trials=n_trials, duration_s=duration, sttc=sttc,
        sttc_thr=sttc_thr, null_mean=surrogate.mean(axis=2), p=p,
        spike_counts=np.array([len(v) for v in observed.values()], dtype=float),
    )


# ── Noise correlations ────────────────────────────────────────────────────────

@dataclass
class NoiseCorrelation:
    condition: str
    window_s: tuple[float, float]
    n_trials: int
    r: np.ndarray        # (n, n) Pearson r of trial counts; NaN for a silent node
    p: np.ndarray        # (n, n) two-sided trial-shuffle p-value
    counts: np.ndarray   # (n_trials, n)


def trial_counts(trains: list[np.ndarray], events: np.ndarray,
                 window: tuple[float, float]) -> np.ndarray:
    """``(n_trials, n_nodes)`` spike counts in ``[event + w0, event + w1)``."""
    events = np.sort(np.asarray(events, float))
    out = np.empty((len(events), len(trains)))
    for j, t in enumerate(trains):
        t = np.asarray(t, float)
        out[:, j] = (np.searchsorted(t, events + window[1], side="left")
                     - np.searchsorted(t, events + window[0], side="left"))
    return out


def _corr(counts: np.ndarray) -> np.ndarray:
    x = counts - counts.mean(axis=0)
    norm = np.sqrt((x ** 2).sum(axis=0))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (x.T @ x) / np.outer(norm, norm)
    np.fill_diagonal(r, np.nan)
    return r


def noise_correlations(trains: list[np.ndarray], events: np.ndarray,
                       window: tuple[float, float], *, condition: str = "stim",
                       rep_num: int = 200,
                       rng: np.random.Generator | None = None) -> NoiseCorrelation:
    """Correlation of trial-to-trial count fluctuations for every node pair.

    Within one condition the stimulus is the same on every trial, so the mean
    response is common to all of them and drops out of a correlation over
    trials; what remains is shared variability. The p-value compares |r| with
    pairs whose trials were shuffled independently per node.
    """
    rng = rng or np.random.default_rng()
    counts = trial_counts(trains, events, window)
    r = _corr(counts)
    exceed = np.zeros_like(r)
    n_trials = counts.shape[0]
    for _ in range(rep_num):
        shuffled = np.column_stack([counts[rng.permutation(n_trials), j]
                                    for j in range(counts.shape[1])])
        exceed += np.abs(_corr(shuffled)) >= np.abs(r)
    p = (exceed + 1) / (rep_num + 1)
    p[np.isnan(r)] = np.nan
    return NoiseCorrelation(condition=condition, window_s=tuple(window),
                            n_trials=n_trials, r=r, p=p, counts=counts)


# ── Summaries ─────────────────────────────────────────────────────────────────

def network_summary(net: EpochNetwork, params, min_activity_hz: float = 0.0,
                    min_nodes: int = 3, rng: np.random.Generator | None = None) -> dict:
    """Scalar network metrics of the thresholded epoch network, as step 4
    computes them for a whole recording (only the scalar ones)."""
    from meanap.pipeline.step4 import compute_network_metrics

    metrics = compute_network_metrics(
        net.sttc_thr, net.spike_counts, net.duration_s, min_activity_hz, min_nodes,
        params=params, rng=rng)
    out = {k: float(v) for k, v in metrics.items()
           if np.isscalar(v) and isinstance(v, (int, float, np.integer, np.floating))}
    upper = np.triu_indices_from(net.sttc, k=1)
    out["meanSTTC"] = float(np.nanmean(net.sttc[upper])) if upper[0].size else np.nan
    out["meanSTTCminusNull"] = (float(np.nanmean((net.sttc - net.null_mean)[upper]))
                                if upper[0].size else np.nan)
    out["nSigEdges"] = int(np.count_nonzero(net.sttc_thr[upper]))
    return out


def noise_summary(nc: NoiseCorrelation, alpha: float = 0.05) -> dict:
    upper = np.triu_indices_from(nc.r, k=1)
    r, p = nc.r[upper], nc.p[upper]
    ok = np.isfinite(r)
    return {
        "aN": int(np.sum(nc.counts.sum(axis=0) > 0)),
        "meanNoiseCorr": float(np.mean(r[ok])) if ok.any() else np.nan,
        "fracSigNoiseCorr": float(np.mean(p[ok] < alpha)) if ok.any() else np.nan,
        "fracSigPositive": float(np.mean((p[ok] < alpha) & (r[ok] > 0))) if ok.any() else np.nan,
        "nPairs": int(ok.sum()),
    }
