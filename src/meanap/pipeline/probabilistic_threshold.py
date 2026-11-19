"""Probabilistic edge thresholding, port of ``adjM_thr_parallel.m``.

Generates synthetic spike trains, recomputes STTC on them, and zeroes out any
edge whose real STTC value doesn't clear the ``tail`` significance cutoff
across ``rep_num`` repetitions. Two nulls make the synthetic trains:

``"circular"`` (MATLAB's, the default)
    Each channel's whole train is shifted by its own random offset. It keeps
    each train's own pattern and breaks all timing between channels, slow
    included — so two channels that only share network bursts, or a rise in
    rate across the recording, pass as connected.
``"jitter"`` (interval jitter, Amarasingham et al. 2012, *J Neurophysiol*)
    Time is cut into windows ``jitter_ms`` long and each spike moved to a
    uniformly random time within its own window. Every channel keeps its
    spike count in every window, so shared bursts and slow co-modulation are
    in the null too; only coincidences finer than the window are tested. An
    edge then means "more synchronous than the two channels' rate profiles
    explain", which is less tied to how much either fires.

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


def interval_jitter_spikes(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    window_s: float,
    duration_s: float,
    rng: np.random.Generator,
) -> dict[int, np.ndarray]:
    """Move each spike to a uniform time within its own ``window_s`` window.

    The windows are fixed (``[0, w), [w, 2w), …``), not centred on each
    spike, which is what makes the null exact: given each train's count in
    each window, every placement within the windows is equally likely
    (Amarasingham et al. 2012). Spikes stay inside the recording.
    """
    if window_s <= 0:
        raise ValueError(f"The jitter window must be positive, not {window_s * 1000:g} ms.")
    jittered: dict[int, np.ndarray] = {}
    for ch in range(n_channels):
        times = np.asarray(spike_times_dict.get(ch, np.array([])), dtype=float)
        if len(times) == 0:
            jittered[ch] = times
            continue
        start = np.floor(times / window_s) * window_s
        end = np.minimum(start + window_s, duration_s)
        moved = start + rng.random(len(times)) * (end - start)
        jittered[ch] = np.sort(moved)
    return jittered


#: The surrogate nulls :func:`adjm_thr` offers, as ``Params.prob_thresh_null`` names them.
NULLS = ("circular", "jitter")


def surrogate_spikes(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    fs: float,
    duration_s: float,
    rng: np.random.Generator,
    *,
    null: str = "circular",
    jitter_ms: float = 50.0,
) -> dict[int, np.ndarray]:
    """One surrogate dataset under *null* (see the module docstring)."""
    if null == "circular":
        return circular_shift_spikes(spike_times_dict, n_channels, fs, duration_s, rng)
    if null == "jitter":
        return interval_jitter_spikes(spike_times_dict, n_channels, jitter_ms / 1000.0,
                                      duration_s, rng)
    raise ValueError(f"Unknown surrogate null {null!r}; expected one of {NULLS}.")


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
    *,
    null: str = "circular",
    jitter_ms: float = 50.0,
):
    """Compute the raw and probabilistically-thresholded STTC adjacency matrices.

    Returns
    -------
    adj_m : (n, n) raw STTC matrix (deterministic, exact MATLAB parity)
    adj_m_ci : (n, n) thresholded matrix — edges not significant at ``tail``
               (one-sided, upper-tail) across ``rep_num`` surrogates under
               *null* (``"circular"`` or ``"jitter"`` with windows
               ``jitter_ms`` long) are zeroed.

    If ``collect_check_snapshots`` is set, also returns ``(rep_val, dist1)`` from
    :func:`threshold_snapshots` for the stability check plot (port of
    ``adjM_thr_checkreps.m``).
    """
    if rng is None:
        rng = np.random.default_rng()

    adj_m = get_sttc(spike_times_dict, n_channels, lag_ms, duration_s)

    surrogate = np.empty((n_channels, n_channels, rep_num))
    for r in range(rep_num):
        synth = surrogate_spikes(spike_times_dict, n_channels, fs, duration_s, rng,
                                 null=null, jitter_ms=jitter_ms)
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
