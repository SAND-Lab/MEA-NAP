"""Electrical stimulation detection + pattern grouping.

Port of MEA-NAP's ``Functions/stimAnalysis/detectStimTimes.m``,
``getStimPatterns.m`` and ``checkStimPattern.m`` (identical on
``feat/plot-parity`` and ``origin/main``).

Detects electrical-stimulation onset times from a raw voltage recording, then
groups the stimulated electrodes into repeated stimulation *patterns*.

The six detection methods mirror the MATLAB exactly:

``absPosThreshold`` / ``absNegThreshold``
    Samples above / below a fixed voltage threshold.
``stdNeg``
    Samples below ``mean - std * stimDetectionVal`` (per channel).
``blanking``
    Median-z-score threshold, snapped to a per-recording template of "blank"
    (constant-value) onset times.
``longblank``
    The production method for blanked stimulation data: each stimulus leaves a
    long run of identical samples (the amplifier blanking); the run *start* is
    the stim time. Runs are found by run-length encoding of ``diff == 0``.
``axionStimEvents``
    Handled elsewhere (event times come from the Axion CSV, not the trace);
    :func:`detect_stim_times` returns empty stim times for these channels.

**1-based indexing gotcha** (see PIPELINE_PORT_STATUS.md for the analogous
spike-time case): MATLAB reports a run starting at sample index ``i`` as
``i / fs`` with ``i`` *1-based*, so a run starting at the very first sample maps
to ``1/fs``, not ``0``. This port adds ``+1`` to every 0-based start position
before dividing by ``fs`` to reproduce MATLAB's times bit-for-bit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ── Run-length helpers ────────────────────────────────────────────────────────

def _runs(channel_dat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Run-length-encode constant-value runs of a 1-D trace.

    Reproduces MATLAB's ``change_points = [1; diff(x) ~= 0]`` /
    ``group_id = cumsum(change_points)`` scheme.

    Returns
    -------
    start_pos : (n_runs,) int — 0-based start sample of each run
    run_len : (n_runs,) int — length (in samples) of each run
    """
    change = np.ones(channel_dat.shape[0], dtype=bool)
    np.not_equal(channel_dat[1:], channel_dat[:-1], out=change[1:])
    start_pos = np.flatnonzero(change)
    run_len = np.diff(np.append(start_pos, channel_dat.shape[0]))
    return start_pos, run_len


def _refractory_prune(stim_times: np.ndarray, ref_period: float) -> np.ndarray:
    """Greedy forward prune: drop any stim within ``ref_period`` of the last kept.

    Literal port of the "V2 fast" loop in ``detectStimTimes.m`` — assumes
    ``stim_times`` is sorted ascending (start positions always are).
    """
    if stim_times.size == 0:
        return stim_times
    keep = np.ones(stim_times.shape[0], dtype=bool)
    last_valid = 0
    for i in range(1, stim_times.shape[0]):
        if stim_times[i] <= stim_times[last_valid] + ref_period:
            keep[i] = False
        else:
            last_valid = i
    return stim_times[keep]


# ── Per-channel detection result ──────────────────────────────────────────────

@dataclass
class StimChannelInfo:
    """Per-channel stim-detection result — mirrors MATLAB's ``stimInfo{i}`` struct."""

    elec_stim_times: np.ndarray            # onset times (s)
    elec_stim_dur: np.ndarray              # per-stim duration (s)
    channel_name: int
    coords: np.ndarray
    pattern: int = 0                       # filled in by get_stim_patterns
    # longblank extras
    blank_starts: np.ndarray | None = None
    blank_ends: np.ndarray | None = None
    non_stim_blank_starts: np.ndarray | None = None
    non_stim_blank_ends: np.ndarray | None = None
    blank_durations: np.ndarray | None = None
    all_stim_times_template: np.ndarray | None = None
    all_blank_starts_template: np.ndarray | None = None
    all_blank_ends_template: np.ndarray | None = None


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_stim_times(
    raw_data: np.ndarray,
    params: dict,
    channel_names: np.ndarray,
    coords: np.ndarray,
) -> list[StimChannelInfo]:
    """Detect electrical stimulation times per channel.

    Parameters
    ----------
    raw_data : (n_samples, n_channels) float — raw voltage traces
    params : dict with keys ``stimDetectionMethod``, ``stimRefractoryPeriod``,
        ``stimDuration``, ``fs``, and method-specific keys
        (``minBlankingDuration``, ``stimDetectionVal``).
    channel_names : (n_channels,) — electrode IDs
    coords : (n_channels, 2) — electrode coordinates (stored, not used in detection)

    Returns
    -------
    list[StimChannelInfo], one per channel.
    """
    method = params["stimDetectionMethod"]
    ref_period = float(params["stimRefractoryPeriod"])
    stim_dur = float(params["stimDuration"])
    fs = float(params["fs"])
    n_channels = raw_data.shape[1]

    # --- 'blanking' template pre-pass -----------------------------------------
    all_stim_times_template = None
    median_zscore = None
    if method == "blanking":
        min_duration = round(float(params["minBlankingDuration"]) * fs)
        num_blanks = np.zeros(n_channels, dtype=int)
        electrode_blank_times: list[np.ndarray] = []
        for c in range(n_channels):
            start_pos, run_len = _runs(raw_data[:, c])
            valid = run_len >= min_duration
            starts = (start_pos[valid] + 1) / fs
            num_blanks[c] = starts.size
            electrode_blank_times.append(starts)
        mode_count = _matlab_mode(num_blanks)
        sel = np.flatnonzero(num_blanks == mode_count)
        if sel.size:
            stacked = np.column_stack([electrode_blank_times[i] for i in sel])
            all_stim_times_template = np.median(stacked, axis=1)
        else:
            all_stim_times_template = np.array([])
        # median z-score used for approximate stim detection
        mad = np.median(np.abs(raw_data - raw_data.mean(axis=0)), axis=0)
        median_zscore = np.abs(raw_data - np.median(raw_data, axis=0)) / mad

    # --- 'longblank' blank pre-pass -------------------------------------------
    lb = None
    if method == "longblank":
        lb = _longblank_prepass(raw_data, fs, float(params["minBlankingDuration"]))

    # --- per-channel detection loop -------------------------------------------
    stim_info: list[StimChannelInfo] = []
    for c in range(n_channels):
        trace = raw_data[:, c]

        if method == "absPosThreshold":
            thr = float(params["stimDetectionVal"])
            stim_times = (np.flatnonzero(trace > thr) + 1) / fs
        elif method == "absNegThreshold":
            thr = float(params["stimDetectionVal"])
            stim_times = (np.flatnonzero(trace < thr) + 1) / fs
        elif method == "stdNeg":
            thr = trace.mean() - trace.std(ddof=1) * float(params["stimDetectionVal"])
            stim_times = (np.flatnonzero(trace < thr) + 1) / fs
        elif method == "blanking":
            stim_times = _detect_blanking(
                median_zscore[:, c], all_stim_times_template,
                float(params["stimDetectionVal"]), ref_period, fs,
            )
        elif method == "longblank":
            start_pos, run_len = _runs(trace)
            valid = run_len >= lb["min_duration"]
            stim_times = (start_pos[valid] + 1) / fs
        elif method == "axionStimEvents":
            stim_times = np.array([])
        else:
            raise ValueError(f"No valid stimulus detection method: {method!r}")

        stim_times = _refractory_prune(np.asarray(stim_times, dtype=float), ref_period)

        info = StimChannelInfo(
            elec_stim_times=stim_times,
            elec_stim_dur=np.full(stim_times.shape[0], stim_dur),
            channel_name=int(channel_names[c]),
            coords=np.asarray(coords[c], dtype=float),
        )
        if method == "blanking":
            info.all_stim_times_template = all_stim_times_template
        if method == "longblank":
            info.blank_starts = lb["blank_starts"][c]
            info.blank_ends = lb["blank_ends"][c]
            info.non_stim_blank_starts = lb["non_stim_starts"][c]
            info.non_stim_blank_ends = lb["non_stim_ends"][c]
            info.blank_durations = lb["blank_ends"][c] - lb["blank_starts"][c] \
                if lb["blank_starts"][c].size == lb["blank_ends"][c].size else np.array([])
            info.all_blank_starts_template = lb["starts_template"]
            info.all_blank_ends_template = lb["ends_template"]
        stim_info.append(info)

    return stim_info


def _longblank_prepass(raw_data: np.ndarray, fs: float, min_blank_dur: float) -> dict:
    """Pre-compute per-channel blank/non-stim-blank runs for the longblank method."""
    n_channels = raw_data.shape[1]
    min_duration = round(min_blank_dur * fs)
    non_stim_min_dur = round(0.001 * fs)

    blank_starts, blank_ends = [], []
    non_stim_starts, non_stim_ends = [], []
    num_blanks = np.zeros(n_channels, dtype=int)

    for c in range(n_channels):
        start_pos, run_len = _runs(raw_data[:, c])
        end_1based = start_pos + run_len           # MATLAB 1-based last-sample index
        start_1based = start_pos + 1

        valid = run_len >= min_duration
        bs = start_1based[valid] / fs
        be = end_1based[valid] / fs
        # filter out long blanks (> 0.05 s)
        if bs.size == be.size:
            keep = (be - bs) <= 0.05
            bs, be = bs[keep], be[keep]
        blank_starts.append(bs)
        blank_ends.append(be)

        ns = (run_len >= non_stim_min_dur) & (run_len < min_duration)
        non_stim_starts.append(start_1based[ns] / fs)
        non_stim_ends.append(end_1based[ns] / fs)

        num_blanks[c] = bs.size

    # blank templates (mode of times within ±1 s windows) — stored, not used for
    # detection, but faithfully reproduced.
    mode_count = _matlab_mode(num_blanks)
    valid_ch = np.flatnonzero(num_blanks == mode_count)
    cons_starts = np.sort(np.concatenate([blank_starts[i] for i in valid_ch])) if valid_ch.size else np.array([])
    cons_ends = np.sort(np.concatenate([blank_ends[i] for i in valid_ch])) if valid_ch.size else np.array([])
    starts_template = _blank_template(cons_starts)
    ends_template = _blank_template(cons_ends)

    return {
        "min_duration": min_duration,
        "blank_starts": blank_starts,
        "blank_ends": blank_ends,
        "non_stim_starts": non_stim_starts,
        "non_stim_ends": non_stim_ends,
        "starts_template": starts_template,
        "ends_template": ends_template,
    }


def _blank_template(consolidated: np.ndarray) -> np.ndarray:
    """Mode of times within a ±1 s sliding window, then unique (port of the loop)."""
    if consolidated.size == 0:
        return np.array([])
    out = np.zeros(consolidated.shape[0])
    for i, t in enumerate(consolidated):
        window = consolidated[(consolidated >= t - 1) & (consolidated <= t + 1)]
        out[i] = _matlab_mode(window)
    return np.unique(out)


def _detect_blanking(
    median_zscore_ch: np.ndarray,
    template: np.ndarray,
    thr: float,
    ref_period: float,
    fs: float,
) -> np.ndarray:
    """'blanking' detection: threshold median-z-score, prune, snap to template."""
    approx = (np.flatnonzero(median_zscore_ch > thr) + 1) / fs
    approx = _refractory_prune(approx, ref_period)
    out = []
    for t in approx:
        before = template[template < t]
        if before.size:
            out.append(before[np.argmin(np.abs(t - before))])
    return np.asarray(out, dtype=float)


def _matlab_mode(x: np.ndarray) -> float:
    """MATLAB ``mode``: most frequent value, ties broken by smallest."""
    if x.size == 0:
        return np.nan
    vals, counts = np.unique(x, return_counts=True)
    return float(vals[np.argmax(counts)])   # np.unique sorts ascending → smallest on ties


# ── Pattern grouping ──────────────────────────────────────────────────────────

def check_stim_pattern(
    candidate: np.ndarray,
    stim_patterns: list[np.ndarray],
    time_diff_threshold: float,
) -> tuple[int, list[np.ndarray]]:
    """Assign ``candidate`` to an existing pattern or create a new one.

    Port of ``checkStimPattern.m``. Returns a **1-based** pattern id and the
    (possibly extended) list of patterns. Only equal-length patterns are
    compared; the last equal-length match within threshold wins (matching
    MATLAB, which overwrites ``matchPattern`` without breaking the loop).
    """
    if not stim_patterns:
        stim_patterns.append(candidate)
        return 1, stim_patterns

    lengths = [p.shape[0] for p in stim_patterns]
    if candidate.shape[0] not in lengths:
        stim_patterns.append(candidate)
        return len(stim_patterns), stim_patterns

    match = None
    for idx, patt in enumerate(stim_patterns):
        if candidate.shape[0] == patt.shape[0]:
            if np.mean(np.abs(candidate - patt)) < time_diff_threshold:
                match = idx
    if match is None:
        stim_patterns.append(candidate)
        return len(stim_patterns), stim_patterns
    return match + 1, stim_patterns


def get_stim_patterns(
    stim_info: list[StimChannelInfo],
    params: dict,
) -> tuple[list[StimChannelInfo], list[np.ndarray]]:
    """Group electrodes into stimulation patterns (port of ``getStimPatterns.m``).

    Iterates electrodes in ascending order of stim count. Electrodes with no
    stimulation get pattern 0; the rest are matched via :func:`check_stim_pattern`
    using ``params['stimTimeDiffThreshold']``. Mutates and returns ``stim_info``.
    """
    threshold = float(params["stimTimeDiffThreshold"])
    num_stim = np.array([info.elec_stim_times.shape[0] for info in stim_info])
    # MATLAB sort is stable ascending; np.argsort with kind='stable' matches.
    order = np.argsort(num_stim, kind="stable")

    stim_patterns: list[np.ndarray] = []
    for elec_idx in order:
        info = stim_info[elec_idx]
        if info.elec_stim_times.shape[0] == 0:
            info.pattern = 0
        else:
            pid, stim_patterns = check_stim_pattern(
                info.elec_stim_times, stim_patterns, threshold
            )
            info.pattern = pid
    return stim_info, stim_patterns
