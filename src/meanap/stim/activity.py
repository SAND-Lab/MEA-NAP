"""Stimulation activity analysis — electrode-level response metrics.

Ports the ``StimActivity_NodeLevel.csv``-producing core of
``stimActivityAnalysis.m`` (origin/main) plus ``saveEphysStatsStim.m``.

Only the deterministic, CSV-producing path is here (gaussian-smoothed
individual-electrode PSTH, d′, z-score, AUC correction, first-spike latency).
Population plots (``ssvkernel``), the shuffle test and pattern decoding live in
sibling modules. Feeding MATLAB's own ``spikeTimes`` isolates this arithmetic
from spike detection, exactly like the step-2/3/4 ports.
"""

from __future__ import annotations

import numpy as np

from .detection import StimChannelInfo, _matlab_mode
from .psth import (
    calculate_psth_metrics,
    get_spike_latency_rel_stim,
    get_stim_artifact_duration,
)

# CSV column order (port of saveEphysStatsStim.m; psth_window_s expands to _1/_2)
CSV_COLUMNS = [
    "FileName", "Grp", "DIV", "channel_id", "file_index", "pattern_id",
    "auc_poststim", "auc_baseline_mean", "auc_corrected",
    "peak_firing_rate_hz", "peak_time_ms", "halfRmax_time_ms",
    "d_prime", "zscore", "psth_window_s_1", "psth_window_s_2",
    "median_latency_ms",
]

_PSTH_BIN_WIDTH_S = 0.001
_NUM_BASELINE_PSTHS = 30
_GAUSSIAN_WIDTH_MS = 1.0


def stim_activity_analysis(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_info: list[StimChannelInfo],
    stim_patterns: list[np.ndarray],
    params: dict,
    info: dict,
) -> list[dict]:
    """Compute per-electrode stim-response metrics (one dict per CSV row).

    Parameters
    ----------
    spike_times : ``{channel_index: {method: times_s}}`` (already cleaned).
    stim_info : per-channel detection results (pattern assignment used here).
    stim_patterns : representative stim-time vectors per pattern.
    params : needs ``SpikesMethod``, ``stimAnalysisWindow``, ``postStimWindowDur``,
        ``stimDetectionMethod`` and (for longblank) blank info via ``stim_info``.
    info : recording metadata dict with ``FileName``/``Grp``/``DIV``.
    """
    method = params["SpikesMethod"]
    window = tuple(float(x) for x in params["stimAnalysisWindow"])
    n_channels = len(stim_info)

    # blankDurMode / artifactDuration (as at the top of stimActivityAnalysis.m)
    blank_dur_mode = 0.0
    if params.get("stimDetectionMethod") == "longblank":
        durs = [
            np.asarray(si.non_stim_blank_ends, float).ravel()
            - np.asarray(si.non_stim_blank_starts, float).ravel()
            for si in stim_info
            if si.non_stim_blank_starts is not None
        ]
        durs = np.concatenate(durs) if durs else np.array([])
        blank_dur_mode = _matlab_mode(durs) if durs.size else 0.0
    artifact_duration_s = get_stim_artifact_duration(
        {**params, "blankDurMode": blank_dur_mode}
    )

    stimulated = {c for c in range(n_channels)
                  if stim_info[c].pattern is not None and stim_info[c].pattern > 0}

    # consolidated trials (all patterns, sorted) — used by d′ window bookkeeping
    poststim_window = (artifact_duration_s, window[1])
    poststim_dur = poststim_window[1] - poststim_window[0]
    baseline_window = (-poststim_dur, 0.0)
    baseline_duration_s = window[1]

    rows: list[dict] = []
    for pattern_idx, stim_times in enumerate(stim_patterns, start=1):
        stim_times = np.asarray(stim_times, dtype=float).ravel()
        if stim_times.size == 0:
            continue

        for c in range(n_channels):
            if c in stimulated:
                continue
            if c not in spike_times or method not in spike_times[c]:
                continue
            sp = np.asarray(spike_times[c][method], dtype=float).ravel()
            if sp.size == 0:
                continue

            _, resp = calculate_psth_metrics(
                sp, stim_times, window, _PSTH_BIN_WIDTH_S,
                smoothing_method="gaussian", gaussian_width_ms=_GAUSSIAN_WIDTH_MS,
                auc_start_s=0.0,
            )
            # skip channels with no spikes in the analysis window
            samples = _spikes_in_window(sp, stim_times, window)
            if samples.size == 0:
                continue

            # d′ / z-score: trial-by-trial pre/post firing rates
            base_fr = np.empty(stim_times.size)
            post_fr = np.empty(stim_times.size)
            for i, st in enumerate(stim_times):
                nb = np.sum((sp >= st + baseline_window[0]) & (sp < st + baseline_window[1]))
                npost = np.sum((sp >= st + poststim_window[0]) & (sp < st + poststim_window[1]))
                base_fr[i] = nb / poststim_dur
                post_fr[i] = npost / poststim_dur
            b_mean, b_std = base_fr.mean(), _std1(base_fr)
            p_mean, p_std = post_fr.mean(), _std1(post_fr)
            if b_std == 0 and p_std == 0:
                d_prime = abs(p_mean - b_mean)
            else:
                d_prime = (p_mean - b_mean) / np.sqrt((b_std**2 + p_std**2) / 2)
            b_std_safe = b_std if b_std != 0 else np.finfo(float).eps
            zscore = (p_mean - b_mean) / b_std_safe

            # baseline-AUC distribution → auc_corrected
            baseline_aucs = np.empty(_NUM_BASELINE_PSTHS)
            for i in range(1, _NUM_BASELINE_PSTHS + 1):
                bw = (window[0] - i * baseline_duration_s,
                      window[0] - (i - 1) * baseline_duration_s)
                _, bm = calculate_psth_metrics(
                    sp, stim_times, bw, _PSTH_BIN_WIDTH_S,
                    smoothing_method="gaussian", gaussian_width_ms=_GAUSSIAN_WIDTH_MS,
                    artifact_exclusion_duration_s=artifact_duration_s,
                )
                baseline_aucs[i - 1] = bm.auc
            mean_baseline_auc = float(baseline_aucs.mean())
            auc_corrected = resp.auc - mean_baseline_auc

            # half-Rmax decay time (uses the FULL-window smoothed PSTH)
            half_rmax_time_s = _half_rmax_time(resp.psth_smooth, resp.time_vector_s)

            # median first-spike latency for this channel/pattern
            lat = get_spike_latency_rel_stim(stim_times, sp, window[1])
            median_latency_ms = float(np.nanmedian(lat)) if np.any(~np.isnan(lat)) else np.nan

            channel_id = stim_info[c].channel_name
            rows.append({
                "FileName": info.get("FileName", ""),
                "Grp": info.get("Grp", ""),
                "DIV": info.get("DIV", ""),
                "channel_id": int(channel_id),
                "file_index": c + 1,                 # 1-based electrode position
                "pattern_id": pattern_idx,
                "auc_poststim": resp.auc,
                "auc_baseline_mean": mean_baseline_auc,
                "auc_corrected": auc_corrected,
                "peak_firing_rate_hz": resp.peak_firing_rate,
                "peak_time_ms": resp.peak_time_s * 1000.0,
                "halfRmax_time_ms": half_rmax_time_s * 1000.0,
                "d_prime": float(d_prime),
                "zscore": float(zscore),
                "psth_window_s_1": window[0],
                "psth_window_s_2": window[1],
                "median_latency_ms": median_latency_ms,
            })

    return rows


def _spikes_in_window(sp, stim_times, window):
    w0, w1 = window
    parts = [sp[(sp >= st + w0) & (sp <= st + w1)] - st for st in stim_times]
    return np.concatenate(parts) if parts else np.array([])


def _std1(x: np.ndarray) -> float:
    """MATLAB ``std`` (N-1 normalization)."""
    return float(np.std(x, ddof=1)) if x.size > 1 else 0.0


def _half_rmax_time(psth_smooth: np.ndarray, time_vector_s: np.ndarray) -> float:
    """Time of first drop to <= Rmax/2 after the global peak (port of STEP 5.1g)."""
    rmax_idx = int(np.argmax(psth_smooth))
    half = psth_smooth[rmax_idx] / 2.0
    tail = psth_smooth[rmax_idx:]
    hits = np.flatnonzero(tail <= half)
    if hits.size == 0:
        return np.nan
    return float(time_vector_s[rmax_idx + hits[0]])


def write_stim_activity_csv(rows: list[dict], path) -> None:
    """Write ``StimActivity_NodeLevel.csv`` (port of ``saveEphysStatsStim.m``)."""
    import pandas as pd
    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    df.to_csv(path, index=False)
