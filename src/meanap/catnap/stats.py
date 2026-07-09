"""CAT-NAP activity statistics.

Ports:
  - ``calTwopActivityStats.m`` → :func:`calc_twop_activity_stats`
  - ``getCellTypeMatrix.m``    → :func:`get_cell_type_matrix`

The stats are the calcium-imaging counterpart of the electrophysiology
``Ephys`` struct (see ``pipeline/step2.py``); they are returned as a dict keyed
by the same MATLAB field names, so downstream CSV writing lines up with the
ephys path. Everything here is deterministic — exact parity with MATLAB is
expected (see ``python/test_pipeline_catnap.py``).
"""

from __future__ import annotations

import warnings

import numpy as np


def _round3(x: float) -> float:
    """MATLAB ``round(x, 3)`` — round half **away from zero** (not banker's).

    numpy's ``round`` uses round-half-to-even, which can disagree with MATLAB
    at exact 0.0005 ties; MATLAB rounds halves away from zero.
    """
    if not np.isfinite(x):
        return float(x)
    factor = 1000.0
    return float(np.sign(x) * np.floor(np.abs(x) * factor + 0.5) / factor)


def _iqr(x: np.ndarray) -> float:
    """MATLAB ``iqr`` = Q3 − Q1 using MATLAB's quantile convention.

    MATLAB's ``quantile`` places the sorted samples at plotting positions
    ``(i - 0.5) / n`` and linearly interpolates (clamping at the extremes) —
    equivalent to numpy's ``method="hazen"``.
    """
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return float("nan")
    q1, q3 = np.quantile(x, [0.25, 0.75], method="hazen")
    return float(q3 - q1)


def _nanmean_over_events(mat: np.ndarray | None) -> np.ndarray | None:
    """``nanmean(mat, 2)`` in MATLAB — mean over the event axis (axis=1 here),
    one value per unit. All-NaN rows yield NaN (no warning)."""
    if mat is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN slice → NaN
        return np.nanmean(np.asarray(mat, dtype=float), axis=1)


def _nansum_over_events(mat: np.ndarray | None) -> np.ndarray | None:
    if mat is None:
        return None
    return np.nansum(np.asarray(mat, dtype=float), axis=1)


def _nanmean_scalar(x: np.ndarray | None) -> float:
    if x is None or np.size(x) == 0:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(np.nanmean(x))


def calc_twop_activity_stats(
    twop_activity: str,
    duration_s: float,
    fs: float,
    min_activity_level: float,
    *,
    spike_times: list[np.ndarray] | None = None,
    activity_matrix: np.ndarray | None = None,
    peak_heights: np.ndarray | None = None,
    peak_duration_frames: np.ndarray | None = None,
    event_areas: np.ndarray | None = None,
) -> dict:
    """Port of ``calTwopActivityStats.m``.

    Parameters mirror the fields MATLAB reads off ``expData``:

    - ``twop_activity`` — ``'peaks'`` | ``'F'`` | ``'spks'`` | ``'denoised F'``.
    - ``spike_times`` — for the ``'peaks'`` path: a list (one per unit) of peak
      times **in seconds** (MATLAB ``spikeTimes{u}.peak``).
    - ``activity_matrix`` — for the other paths: ``(n_frames, n_units)`` array
      (MATLAB ``expData.(twopActivity)``); firing rate is its column sum / duration.
    - ``peak_heights`` / ``peak_duration_frames`` / ``event_areas`` —
      ``(n_units, max_events)`` NaN-padded arrays from ``activityProperties``.

    Returns a dict keyed by the MATLAB ``activityStats`` field names.

    Notes / deviations: the ISI and 2P-specific (height/duration/area) metrics
    are only defined by MATLAB for the ``'peaks'`` path (they read
    ``spikeTimes`` / ``activityProperties``, which only exist then). For the
    other activity types those inputs are ``None`` and the corresponding fields
    come back as NaN rather than erroring.
    """
    stats: dict = {}

    # ── Firing rate (metric shared with ephys) ────────────────────────────────
    if twop_activity == "peaks":
        if spike_times is None:
            raise ValueError("spike_times is required for twop_activity='peaks'")
        n_units = len(spike_times)
        num_peaks = np.array([np.size(st) for st in spike_times], dtype=float)
        peak_isi = np.full(n_units, np.nan)
        for u, st in enumerate(spike_times):
            st = np.asarray(st, dtype=float).ravel()
            if st.size >= 2:
                peak_isi[u] = np.mean(np.diff(st))
        firing_rates = num_peaks / duration_s
    else:
        if activity_matrix is None:
            raise ValueError(
                "activity_matrix is required for twop_activity != 'peaks'"
            )
        # MATLAB sum(expData.(twopActivity), 1): sum over time (rows) → per unit.
        firing_rates = np.asarray(activity_matrix, dtype=float).sum(axis=0) / duration_s
        peak_isi = np.full(firing_rates.shape[0], np.nan)

    active_index = firing_rates >= min_activity_level
    active_fr = firing_rates[active_index]

    stats["FR"] = firing_rates

    # FR with sub-threshold units set to NaN.
    fr_active_full = np.full(firing_rates.shape[0], np.nan)
    fr_active_full[active_index] = active_fr
    stats["FRactive"] = fr_active_full

    # Recording-level FR summaries, computed on active units only, rounded to 3dp.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # empty active set → NaN
        stats["FRmean"] = _round3(float(np.mean(active_fr)) if active_fr.size else float("nan"))
        stats["FRstd"] = _round3(float(np.std(active_fr, ddof=1)) if active_fr.size > 1 else float("nan"))
        sem = (float(np.std(active_fr, ddof=1)) / np.sqrt(active_fr.size)) if active_fr.size > 1 else float("nan")
        stats["FRsem"] = _round3(sem)
        stats["FRmedian"] = _round3(float(np.median(active_fr)) if active_fr.size else float("nan"))
    stats["FRiqr"] = _round3(_iqr(active_fr))
    stats["numActiveElec"] = int(active_fr.size)

    stats["ISImean"] = _nanmean_scalar(peak_isi)
    stats["ISI"] = peak_isi

    # ── Two-photon-specific metrics ───────────────────────────────────────────
    # unit level
    stats["unitHeightMean"] = _nanmean_over_events(peak_heights)
    dur_mean = _nanmean_over_events(peak_duration_frames)
    stats["unitPeakDurMean"] = None if dur_mean is None else dur_mean / fs
    area_mean = _nanmean_over_events(event_areas)
    stats["unitEventAreaMean"] = None if area_mean is None else area_mean / fs
    area_sum = _nansum_over_events(event_areas)
    stats["unitEventAreaSum"] = None if area_sum is None else area_sum / fs

    # recording level
    stats["recHeightMean"] = _nanmean_scalar(stats["unitHeightMean"])
    stats["recPeakDurMean"] = _nanmean_scalar(stats["unitPeakDurMean"])
    stats["recEventAreaMean"] = _nanmean_scalar(stats["unitEventAreaMean"])

    return stats


def get_cell_type_matrix(
    cell_type_ids: dict[str, np.ndarray],
    channels: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """Port of ``getCellTypeMatrix.m``.

    MATLAB reads ``Info.CellTypes`` (a table); here we take a dict mapping each
    cell-type name to an array of **0-indexed** ROI ids (as stored in the
    ``PutativeCellType_*.csv`` files — the ``+1`` in the MATLAB code converts
    those to the 1-indexed ROI numbers held in ``channels``).

    Returns ``(cell_type_matrix, cell_type_names)`` where ``cell_type_matrix``
    is ``(n_channels, n_cell_types)`` with a 1 wherever a channel's ROI id is
    listed under that cell type.
    """
    channels = np.asarray(channels).ravel()
    names = list(cell_type_ids.keys())
    matrix = np.zeros((channels.size, len(names)), dtype=float)

    # channel value → row index (channels are 1-indexed ROI numbers)
    chan_to_row = {int(c): i for i, c in enumerate(channels)}

    for col, name in enumerate(names):
        ids = np.asarray(cell_type_ids[name], dtype=float).ravel()
        ids = ids[~np.isnan(ids)].astype(int) + 1  # 0-indexed CSV → 1-indexed ROI
        for roi in ids:
            row = chan_to_row.get(int(roi))
            if row is not None:
                matrix[row, col] = 1.0

    return matrix, names
