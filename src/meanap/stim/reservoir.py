"""Reservoir-computing export matrices from stim-aligned spikes.

Port of STEP 5.1d / STEP 7 / STEP 8 of ``stimActivityAnalysis.m`` (origin/main):
``FiringRateMatrix``, ``latencyMatrix`` and ``ExactSpikeTimes``, each
``[numTrialsTotal x numChannels]`` over the consolidated (all-pattern,
chronological) stim times.

All three exclude stimulated channels (kept NaN / empty). ``FiringRateMatrix``
additionally only fills channels that pass the individual-electrode PSTH gate
(spikes present in the ±window across pattern-1 trials) — faithfully mirroring
that the MATLAB fills it inside the analysis loop, after that gate.
"""

from __future__ import annotations

import numpy as np

from .detection import StimChannelInfo, _matlab_mode
from .psth import get_stim_artifact_duration


def _consolidated_stim_times(stim_patterns: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    times, labels = [], []
    for pidx, st in enumerate(stim_patterns, start=1):
        st = np.asarray(st, dtype=float).ravel()
        if st.size:
            times.append(st)
            labels.append(np.full(st.size, pidx))
    if not times:
        return np.array([]), np.array([])
    t = np.concatenate(times)
    lbl = np.concatenate(labels)
    order = np.argsort(t, kind="stable")   # MATLAB sort is stable
    return t[order], lbl[order]


def compute_reservoir_matrices(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_info: list[StimChannelInfo],
    stim_patterns: list[np.ndarray],
    params: dict,
) -> dict:
    """Return ``FiringRateMatrix``/``latencyMatrix``/``ExactSpikeTimes`` (+ meta)."""
    method = params["SpikesMethod"]
    window = tuple(float(x) for x in params["stimAnalysisWindow"])
    n_channels = len(stim_info)

    blank_dur_mode = 0.0
    if params.get("stimDetectionMethod") == "longblank":
        durs = [np.asarray(si.non_stim_blank_ends, float).ravel()
                - np.asarray(si.non_stim_blank_starts, float).ravel()
                for si in stim_info if si.non_stim_blank_starts is not None]
        durs = np.concatenate(durs) if durs else np.array([])
        blank_dur_mode = _matlab_mode(durs) if durs.size else 0.0
    artifact_dur = get_stim_artifact_duration({**params, "blankDurMode": blank_dur_mode})

    stimulated = {c for c in range(n_channels)
                  if stim_info[c].pattern is not None and stim_info[c].pattern > 0}

    consolidated, labels = _consolidated_stim_times(stim_patterns)
    n_trials = consolidated.shape[0]

    fr = np.full((n_trials, n_channels), np.nan)
    latency = np.full((n_trials, n_channels), np.nan)
    exact: list[list[np.ndarray]] = [[np.array([]) for _ in range(n_channels)]
                                     for _ in range(n_trials)]

    post_start_off = artifact_dur
    post_end_off = window[1]
    win_dur = post_end_off - post_start_off

    # PSTH gate uses pattern-1 stim times (matches the analysis loop)
    pattern1 = np.asarray(stim_patterns[0], dtype=float).ravel() if stim_patterns else np.array([])

    for c in range(n_channels):
        if c in stimulated:
            continue
        if c not in spike_times or method not in spike_times[c]:
            continue
        sp = np.asarray(spike_times[c][method], dtype=float).ravel()
        if sp.size == 0:
            continue

        # FiringRateMatrix — gated on non-empty ±window psth samples (pattern 1)
        has_psth = any(np.any((sp >= t + window[0]) & (sp <= t + window[1])) for t in pattern1)
        if has_psth:
            for ti, st in enumerate(consolidated):
                inwin = sp[(sp >= st + post_start_off) & (sp <= st + post_end_off)]
                fr[ti, c] = inwin.size / win_dur

        # latencyMatrix — not psth-gated, first spike in [artifact, w2], ms, >0
        for ti, st in enumerate(consolidated):
            valid = sp[(sp >= st + post_start_off) & (sp <= st + post_end_off)]
            if valid.size:
                lat_ms = (valid.min() - st) * 1000.0
                if lat_ms > 0:
                    latency[ti, c] = lat_ms

        # ExactSpikeTimes — spikes in [artifact, w2], ms post-stim
        for ti, st in enumerate(consolidated):
            inwin = sp[(sp >= st + post_start_off) & (sp <= st + post_end_off)]
            exact[ti][c] = (inwin - st) * 1000.0 if inwin.size else np.array([])

    return {
        "FiringRateMatrix": fr,
        "latencyMatrix": latency,
        "ExactSpikeTimes": exact,
        "allStimTimesConsolidated": consolidated,
        "stimPatternLabels": labels,
        "numTrialsTotal": n_trials,
        "analysis_window_s": (artifact_dur, window[1]),
        "stimulated_channels_excluded": sorted(c + 1 for c in stimulated),
    }
