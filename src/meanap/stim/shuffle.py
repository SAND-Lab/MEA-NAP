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


def run_pattern_shuffle_tests(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_patterns: list,
    params: dict,
    artifact_duration_s: float,
    info: dict,
    n_channels: int,
    rng: np.random.Generator,
) -> dict[int, ShuffleResults]:
    """Every pattern's shuffle test, keyed by 1-based pattern number.

    One RNG stream, used in pattern order: each test continues it where the
    last left off, so the results are only reproducible when all patterns run
    together, in this order. The stim step, the figures and the rebuild script
    all go through here so they get the same null from the same seed.
    """
    p = {**params, "artifactDuration_s": artifact_duration_s}
    return {pidx: stim_shuffle_test(spike_times, st, p, info, n_channels, rng=rng)
            for pidx, st in enumerate(stim_patterns, 1)}


#: Columns the shuffle test adds to ``StimActivity_NodeLevel.csv``.
SHUFFLE_CSV_COLUMNS = ("trial_prop_obs", "is_sig_hi")


def add_shuffle_columns(rows: list[dict], shuffles: dict[int, ShuffleResults]) -> None:
    """Give each ``StimActivity_NodeLevel.csv`` row its electrode's shuffle result.

    Rows are matched by ``pattern_id`` and ``file_index`` (1-based electrode
    position). A row whose pattern has no result gets blanks, so the columns
    are always there and a failed test shows up as missing, not as "not
    significant".
    """
    for r in rows:
        sr = shuffles.get(r["pattern_id"])
        c = int(r["file_index"]) - 1
        if sr is None or not 0 <= c < len(sr.trial_prop_obs):
            r["trial_prop_obs"], r["is_sig_hi"] = np.nan, None
        else:
            r["trial_prop_obs"] = float(sr.trial_prop_obs[c])
            r["is_sig_hi"] = bool(sr.is_sig_hi[c])


#: MATLAB's per-pattern file name (``stimActivityAnalysis.m``).
SHUFFLE_MAT_NAME = "shuffleResults_pattern_{}.mat"


def save_shuffle_results_mat(dest, shuffles: dict[int, ShuffleResults],
                             stim_patterns: list) -> list:
    """Write ``shuffleResults_pattern_{k}.mat`` into the recording folder *dest*.

    Same file name, variable (``patternShuffleResults``) and field names as
    MATLAB's ``stimShuffleTest``, so scripts written for MATLAB's output read
    these unchanged. Per-electrode fields are ``[numChannels x 1]`` columns in
    electrode order, and the ``isSig*`` fields are MATLAB logicals. Like
    MATLAB, a pattern with no stimulus times gets no file.
    """
    from pathlib import Path

    import scipy.io as sio

    from meanap.pipeline.atomic import atomic_path

    dest = Path(dest)
    written = []
    for pidx, sr in sorted(shuffles.items()):
        if np.asarray(stim_patterns[pidx - 1]).size == 0:
            continue
        struct = {
            "trialProp_obs": np.asarray(sr.trial_prop_obs, float),
            "trialProp_null": np.asarray(sr.trial_prop_null, float),
            "pctile_lo": np.asarray(sr.pctile_lo, float),
            "pctile_hi": np.asarray(sr.pctile_hi, float),
            "isSigLo": np.asarray(sr.is_sig_lo, bool),
            "isSigHi": np.asarray(sr.is_sig_hi, bool),
            "isSignificant": np.asarray(sr.is_significant, bool),
            "Nshuffles": float(sr.n_shuffles),
            "alpha": float(sr.alpha),
            "postStimWindow": np.asarray(sr.poststim_window, float).reshape(1, 2),
            "baselineWindow": np.asarray(sr.baseline_window, float).reshape(1, 2),
            "artifactDuration": float(sr.artifact_duration),
        }
        path = dest / SHUFFLE_MAT_NAME.format(pidx)
        with atomic_path(path, suffix=".mat") as tmp:
            sio.savemat(tmp, {"patternShuffleResults": struct}, oned_as="column")
        written.append(path)
    return written
