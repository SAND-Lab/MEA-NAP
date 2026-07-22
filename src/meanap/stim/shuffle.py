"""Circular-shift shuffle test for stim-response significance.

Port of ``stimShuffleTest.m`` + ``computeTrialProportion.m`` /
``computeTrialProportionForEachChannel.m`` (origin/main).

The per-electrode metric is the proportion of trials where the post-stim spike
count exceeds the pre-stim (baseline) count. Significance is a one-tailed upper
test against a null built by circularly shifting each electrode's spike train.

**Determinism**: ``trialProp_obs`` is deterministic and reproduces MATLAB
exactly. The null distribution (``trialProp_null``, ``pctile_*``,
``isSignificant``) is **not** bit-reproducible — MATLAB's ``stimShuffleTest``
never seeds the RNG (same situation as Step 3's probabilistic thresholding), so
those are validated structurally, not against MATLAB's specific null.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .psth import get_stim_artifact_duration


def compute_trial_proportion(
    spike_times_s: np.ndarray,
    stim_times_s: np.ndarray,
    poststim_window_s: tuple[float, float],
    baseline_window_s: tuple[float, float],
) -> float:
    """Proportion of trials with more post-stim than pre-stim spikes (one electrode).

    Windows use ``[start, end)`` (>= start & < end), matching MATLAB. Returns 0
    for no spikes / no trials.
    """
    spike_times_s = np.asarray(spike_times_s, dtype=float).ravel()
    stim_times_s = np.asarray(stim_times_s, dtype=float).ravel()
    if spike_times_s.size == 0 or stim_times_s.size == 0:
        return 0.0
    pb0, pb1 = baseline_window_s
    pp0, pp1 = poststim_window_s
    greater = 0
    for st in stim_times_s:
        n_pre = np.sum((spike_times_s >= st + pb0) & (spike_times_s < st + pb1))
        n_post = np.sum((spike_times_s >= st + pp0) & (spike_times_s < st + pp1))
        if n_post > n_pre:
            greater += 1
    return greater / stim_times_s.size


def _trial_prop_all_channels(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_times_s: np.ndarray,
    poststim_window_s: tuple[float, float],
    baseline_window_s: tuple[float, float],
    n_channels: int,
    method: str,
) -> np.ndarray:
    out = np.zeros(n_channels)
    for c in range(n_channels):
        if c not in spike_times or method not in spike_times[c]:
            continue
        sp = spike_times[c][method]
        if np.asarray(sp).size == 0:
            continue
        out[c] = compute_trial_proportion(sp, stim_times_s, poststim_window_s, baseline_window_s)
    return out


@dataclass
class ShuffleResults:
    trial_prop_obs: np.ndarray
    trial_prop_null: np.ndarray
    pctile_lo: np.ndarray
    pctile_hi: np.ndarray
    is_sig_lo: np.ndarray
    is_sig_hi: np.ndarray
    is_significant: np.ndarray
    n_shuffles: int
    alpha: float
    poststim_window: tuple[float, float]
    baseline_window: tuple[float, float]
    artifact_duration: float


def stim_shuffle_test(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_times_s: np.ndarray,
    params: dict,
    info: dict,
    n_channels: int,
    rng: np.random.Generator | None = None,
) -> ShuffleResults:
    """Port of ``stimShuffleTest.m``.

    Only ``trial_prop_obs`` is deterministic (parity-checkable); the null is
    RNG-dependent. ``params`` needs ``SpikesMethod``, ``stimAnalysisWindow`` and
    an artifact-duration source; ``info`` needs ``duration_s``.
    """
    method = params["SpikesMethod"]
    n_shuffles = int(params.get("Nshuffles") or 500)
    alpha = float(params.get("shuffleAlpha") or 0.05)
    if rng is None:
        rng = np.random.default_rng()

    window = params["stimAnalysisWindow"]
    artifact_dur = get_stim_artifact_duration(params)
    poststim = (artifact_dur, float(window[1]))
    poststim_dur = poststim[1] - poststim[0]
    baseline = (-poststim_dur, 0.0)
    if poststim_dur <= 0:
        raise ValueError("artifact window >= post-stim window; nothing to test")

    duration_s = float(info["duration_s"])
    stim_times_s = np.asarray(stim_times_s, dtype=float).ravel()

    obs = _trial_prop_all_channels(spike_times, stim_times_s, poststim, baseline, n_channels, method)

    null = np.zeros((n_channels, n_shuffles))
    for s in range(n_shuffles):
        shifted: dict[int, dict[str, np.ndarray]] = {}
        for c in range(n_channels):
            if c in spike_times and method in spike_times[c]:
                sp = np.asarray(spike_times[c][method], dtype=float).ravel()
                if sp.size:
                    d = rng.random() * duration_s
                    sh = sp + d
                    sh[sh > duration_s] -= duration_s
                    sh = np.sort(sh)
                else:
                    sh = sp
                shifted[c] = {method: sh}
        null[:, s] = _trial_prop_all_channels(shifted, stim_times_s, poststim, baseline, n_channels, method)

    # numpy percentile default (linear) matches MATLAB prctile only approximately;
    # the null itself is already RNG-divergent, so this is structural anyway.
    pctile_lo = np.percentile(null, alpha * 100, axis=1)
    pctile_hi = np.percentile(null, (1 - alpha) * 100, axis=1)
    is_sig_hi = obs > pctile_hi
    is_sig_lo = np.zeros(n_channels, dtype=bool)

    return ShuffleResults(obs, null, pctile_lo, pctile_hi, is_sig_lo, is_sig_hi,
                          is_sig_hi.copy(), n_shuffles, alpha, poststim, baseline, artifact_dur)
