"""Spike Time Tiling Coefficient (STTC), port of ``get_sttc.m`` / ``sttc_m.m``.

Reference: Cutts & Eglen (2014), "Detecting Pairwise Correlations in Spike
Trains: An Objective Comparison of Methods and Application to the Study of
Retinal Waves", https://www.ncbi.nlm.nih.gov/pubmed/25339742
"""

from __future__ import annotations

import numpy as np


def _run_t(dt: float, t_start: float, t_end: float, times: np.ndarray) -> float:
    """Fraction-of-recording (unnormalised) tiled by ``times`` +/- ``dt``.

    Direct port of ``run_T`` in ``sttc_m.m`` — vectorised over consecutive
    spike gaps but preserves MATLAB's exact edge-case branching (the n==1
    case uses if/elseif; the n>1 case uses two independent ifs).
    """
    n = len(times)
    if n == 0:
        return 0.0

    time_a = 2 * n * dt

    if n == 1:
        t = times[0]
        if t - t_start < dt:
            time_a = time_a - t_start + t - dt
        elif t + dt > t_end:
            time_a = time_a - t - dt + t_end
        return time_a

    diffs = np.diff(times)
    overlap = diffs[diffs < 2 * dt]
    time_a -= np.sum(2 * dt - overlap)

    if times[0] - t_start < dt:
        time_a = time_a - t_start + times[0] - dt
    if t_end - times[-1] < dt:
        time_a = time_a - times[-1] - dt + t_end

    return time_a


def _run_p(t1: np.ndarray, t2: np.ndarray, dt: float) -> int:
    """Count of spikes in ``t1`` with >=1 coincident spike in ``t2`` within ``dt``.

    Vectorised equivalent of the monotonic two-pointer ``run_P`` in
    ``sttc_m.m``: for each spike in ``t1`` only its immediate neighbours in
    the sorted ``t2`` array can be within ``dt`` (both arrays are sorted
    ascending), so a single ``searchsorted`` call suffices.
    """
    if len(t1) == 0 or len(t2) == 0:
        return 0
    idx = np.searchsorted(t2, t1)
    idx_hi = np.clip(idx, 0, len(t2) - 1)
    idx_lo = np.clip(idx - 1, 0, len(t2) - 1)
    coincident = (np.abs(t2[idx_hi] - t1) <= dt) | (np.abs(t2[idx_lo] - t1) <= dt)
    return int(np.sum(coincident))


def sttc_pair(spike_times_1: np.ndarray, spike_times_2: np.ndarray, dt: float,
              t_start: float, t_end: float) -> float:
    """Spike time tiling coefficient between two spike trains (in seconds)."""
    n1 = len(spike_times_1)
    n2 = len(spike_times_2)
    if n1 == 0 or n2 == 0:
        return np.nan

    t = t_end - t_start
    ta = _run_t(dt, t_start, t_end, spike_times_1) / t
    tb = _run_t(dt, t_start, t_end, spike_times_2) / t
    pa = _run_p(spike_times_1, spike_times_2, dt) / n1
    pb = _run_p(spike_times_2, spike_times_1, dt) / n2

    return 0.5 * (pa - tb) / (1 - tb * pa) + 0.5 * (pb - ta) / (1 - ta * pb)


def get_sttc(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    lag_ms: float,
    duration_s: float,
) -> np.ndarray:
    """Pairwise STTC adjacency matrix, port of ``get_sttc.m``.

    Negative values and NaNs (including the diagonal, which is never
    computed) are zeroed, matching MATLAB's
    ``adjM(adjM<0)=0; adjM(isnan(adjM))=0;``.
    """
    dt = lag_ms / 1000.0
    adj_m = np.full((n_channels, n_channels), np.nan)

    times = [np.asarray(spike_times_dict.get(ch, np.array([]))) for ch in range(n_channels)]

    for i in range(n_channels):
        for j in range(i + 1, n_channels):
            coef = sttc_pair(times[i], times[j], dt, 0.0, duration_s)
            adj_m[i, j] = coef
            adj_m[j, i] = coef

    adj_m[adj_m < 0] = 0.0
    adj_m[np.isnan(adj_m)] = 0.0
    return adj_m
