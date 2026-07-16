"""Probabilistic edge thresholding, port of ``adjM_thr_parallel.m``.

Generates synthetic spike trains by circularly shifting each channel's real
spike times by a random offset, recomputes STTC on the shuffled data, and
zeroes out any edge whose real STTC value doesn't clear the ``tail``
significance cutoff across ``rep_num`` repetitions.

**Not bit-reproducible against MATLAB.** The shuffling is driven by a random
number generator and MATLAB's ``adjM_thr_parallel.m`` never seeds one
explicitly, so even two MATLAB runs of the same recording can produce
different ``adjMci`` matrices. Only the deterministic, unthresholded STTC
matrix (:func:`meanap.pipeline.sttc.get_sttc`) has exact parity coverage —
see ``python/test_pipeline_step3.py``. This module is validated structurally
(shuffled spike counts are conserved, thresholding only ever removes edges,
etc.), not against a specific MATLAB run's random outcome.
"""

from __future__ import annotations

import math

import numpy as np

from meanap.pipeline.sttc import get_sttc


def circular_shift_spikes(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    fs: float,
    duration_s: float,
    rng: np.random.Generator,
) -> dict[int, np.ndarray]:
    """Circularly shift each channel's spike times by an independent random offset.

    Port of the per-repetition synthetic-spike-train loop in
    ``adjM_thr_parallel.m`` (operates in frames, matching MATLAB's
    ``spk_vec = times*fs + k; overhang wraps around num_frames``).
    """
    num_frames = round(duration_s * fs)
    shifted: dict[int, np.ndarray] = {}
    for ch in range(n_channels):
        times = np.asarray(spike_times_dict.get(ch, np.array([])))
        if len(times) == 0:
            shifted[ch] = times
            continue
        k = rng.integers(1, num_frames, endpoint=True)
        spk_vec = times * fs + k
        overhang = spk_vec > num_frames
        spk_vec[overhang] -= num_frames
        shifted[ch] = np.sort(spk_vec) / fs
    return shifted


def threshold_snapshots(
    surrogate: np.ndarray, tail: float, rep_num: int
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Threshold matrices at increasing repetition counts (MATLAB ``dist1``).

    Port of the incremental ``dist1`` construction in ``adjM_thr_checkreps.m``:
    ``a = 0:10:rep_num; a(1)=1`` gives the checkpoint repetition counts, and at
    each ``i`` the threshold matrix is the ``ceil((1-tail)*i)``-th smallest
    surrogate value per edge. Used only to draw the probabilistic-thresholding
    stability check figure.
    """
    a = list(range(0, rep_num + 1, 10))
    if a:
        a[0] = 1
    else:
        a = [1]
    a = [i for i in a if 1 <= i <= rep_num]
    dist1: list[np.ndarray] = []
    for i in a:
        sub_sorted = np.sort(surrogate[:, :, :i], axis=2)
        cp = math.ceil((1 - tail) * i) - 1
        cp = min(max(cp, 0), i - 1)
        dist1.append(sub_sorted[:, :, cp])
    return np.array(a), dist1


def adjm_thr(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    lag_ms: float,
    tail: float,
    fs: float,
    duration_s: float,
    rep_num: int,
    rng: np.random.Generator | None = None,
    collect_check_snapshots: bool = False,
):
    """Compute the raw and probabilistically-thresholded STTC adjacency matrices.

    Returns
    -------
    adj_m : (n, n) raw STTC matrix (deterministic, exact MATLAB parity)
    adj_m_ci : (n, n) thresholded matrix — edges not significant at ``tail``
               (one-sided, upper-tail) across ``rep_num`` circular-shift
               surrogates are zeroed.

    If ``collect_check_snapshots`` is set, also returns ``(rep_val, dist1)`` from
    :func:`threshold_snapshots` for the stability check plot (port of
    ``adjM_thr_checkreps.m``).
    """
    if rng is None:
        rng = np.random.default_rng()

    adj_m = get_sttc(spike_times_dict, n_channels, lag_ms, duration_s)

    surrogate = np.empty((n_channels, n_channels, rep_num))
    for r in range(rep_num):
        synth = circular_shift_spikes(spike_times_dict, n_channels, fs, duration_s, rng)
        adj_synth = get_sttc(synth, n_channels, lag_ms, duration_s)
        np.fill_diagonal(adj_synth, 0.0)
        surrogate[:, :, r] = adj_synth

    cutoff_point = math.ceil((1 - tail) * rep_num) - 1  # MATLAB is 1-indexed
    cutoff_point = min(max(cutoff_point, 0), rep_num - 1)

    surrogate_sorted = np.sort(surrogate, axis=2)
    threshold = surrogate_sorted[:, :, cutoff_point]

    adj_m_ci = adj_m.copy()
    adj_m_ci[threshold > adj_m] = 0.0

    if collect_check_snapshots:
        rep_val, dist1 = threshold_snapshots(surrogate, tail, rep_num)
        return adj_m, adj_m_ci, rep_val, dist1

    return adj_m, adj_m_ci
