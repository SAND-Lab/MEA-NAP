"""CAT-NAP adjacency-matrix construction.

Port of ``Functions/twoPhoton/suite2pToAdjm.m`` (everything after the denoising
call — the loading/denoising itself lives in ``loader.py`` / ``denoising.py``).

Takes a loaded :class:`~meanap.catnap.loader.Suite2pData` and produces the
functional-connectivity adjacency matrices plus the node coordinates, channel
list, per-unit activity matrices, peak spike times, and event properties that
the rest of the pipeline consumes.

Determinism: ``coords``, ``channels``, ``activity_properties``, ``spike_times``
and the ``corr``-based adjacency (``F`` / ``spks`` / ``denoised F``) are exact.
The ``peaks`` adjacency reuses :func:`meanap.pipeline.probabilistic_threshold.adjm_thr`
(STTC + circular-shift thresholding), whose thresholding step is RNG-driven and
therefore only reproducible against MATLAB within tolerance — see that module
and ``python/test_pipeline_catnap.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from meanap.catnap.loader import Suite2pData
from meanap.pipeline.probabilistic_threshold import adjm_thr


@dataclass
class Suite2pAdjmResult:
    """Outputs of :func:`suite2p_to_adjm`, mirroring ``suite2pToAdjm.m``'s returns."""

    adjMs: dict[str, np.ndarray]          # {'adjM{lag}mslag': (n, n)}
    coords: np.ndarray                    # (n, 2), normalized to [0, 8]
    channels: np.ndarray                  # (n,) 1-indexed ROI ids
    F: np.ndarray                         # (n_frames, n) raw fluorescence
    denoised_F: np.ndarray | None         # (n_frames, n) or None
    spks: np.ndarray                      # (n_frames, n) suite2p spike prob
    spike_times: list[np.ndarray] | None  # per-unit peak times (s); None unless 'peaks'
    fs: float
    activity_properties: dict             # peakDurationFrames/peakHeights/eventAreas/cellsWithPeaks
    func_con_lag_val: list[int]           # lags actually used (single deriv. lag for corr paths)


def _corr_columns(x: np.ndarray) -> np.ndarray:
    """MATLAB ``corr(X)`` — Pearson correlation between the columns (units) of X."""
    if x.shape[1] == 0:
        return np.zeros((0, 0))
    return np.corrcoef(x, rowvar=False)


def suite2p_to_adjm(
    data: Suite2pData,
    twop_activity: str,
    func_con_lag_val: list[int],
    *,
    remove_nodes_with_no_peaks: bool = False,
    prob_thresh_tail: float = 0.05,
    prob_thresh_rep_num: int = 200,
    rng: np.random.Generator | None = None,
) -> Suite2pAdjmResult:
    """Port of ``suite2pToAdjm.m``.

    Parameters
    ----------
    data
        Loaded suite2p recording. For ``twop_activity`` in
        ``{'peaks', 'denoised F', 'spks'}`` the denoising outputs
        (``F_denoised``, ``peak_start_frames`` …) must already be present
        (the runner ensures this by denoising first).
    twop_activity
        ``'peaks'`` | ``'F'`` | ``'spks'`` | ``'denoised F'``.
    func_con_lag_val
        STTC lags (ms) for the ``'peaks'`` path. Ignored by the ``corr`` paths,
        which derive a single lag ``round(1000 / fs)`` from the frame rate.
    """
    fs = float(data.fs)
    cell_mask = data.cell_mask  # iscell[:, 0] as bool, shape (n_rois,)

    # ── iscell subset (MATLAB `... (iscell(:,1), :)'`) ────────────────────────
    # Activity matrices are (n_frames, n_cells) to match MATLAB's transpose.
    F_isc = data.F[cell_mask].T
    spks_isc = data.spks[cell_mask].T

    # 1-indexed ROI ids among the iscell units (MATLAB `channels(iscell)`).
    channels = (np.arange(data.F.shape[0]) + 1)[cell_mask]

    # Node coordinates from stat centroids (2, n_rois) → (n_cells, 2).
    coords = data.xy_loc[:, cell_mask].T.astype(float)

    denoised_isc: np.ndarray | None = None
    peak_start_isc = peak_dur_isc = peak_height_isc = event_area_isc = None
    needs_peaks = twop_activity in ("peaks", "denoised F", "spks")
    if needs_peaks:
        if data.F_denoised is None or data.peak_start_frames is None:
            raise ValueError(
                f"twop_activity={twop_activity!r} needs denoising outputs "
                "(F_denoised / peak_start_frames …) — run denoising first."
            )
        denoised_isc = data.F_denoised[cell_mask].T
        peak_start_isc = data.peak_start_frames[cell_mask]
        peak_dur_isc = (data.peak_end_frames - data.peak_start_frames)[cell_mask]
        peak_height_isc = data.peak_heights[cell_mask]
        event_area_isc = data.event_areas[cell_mask]

    # ── removeNodesWithNoPeaks: keep only cells with ≥1 detected peak ──────────
    cells_with_peaks = None
    if remove_nodes_with_no_peaks:
        if peak_start_isc is None:
            raise ValueError(
                "remove_nodes_with_no_peaks requires the peaks/denoising outputs."
            )
        keep = ~np.all(np.isnan(peak_start_isc), axis=1)
        cells_with_peaks = np.where(keep)[0] + 1  # MATLAB 1-indexed find()

        F_isc = F_isc[:, keep]
        spks_isc = spks_isc[:, keep]
        if denoised_isc is not None:
            denoised_isc = denoised_isc[:, keep]
        peak_start_isc = peak_start_isc[keep]
        peak_dur_isc = peak_dur_isc[keep]
        peak_height_isc = peak_height_isc[keep]
        event_area_isc = event_area_isc[keep]
        channels = channels[keep]
        coords = coords[keep]

    activity_properties: dict = {
        "peakDurationFrames": peak_dur_isc,
        "peakHeights": peak_height_isc,
        "eventAreas": event_area_isc,
    }
    if cells_with_peaks is not None:
        activity_properties["cellsWithPeaks"] = cells_with_peaks

    # ── Normalize coords to [0, 8] using the *full* XYloc range ────────────────
    # (MATLAB uses max/min over all ROIs' XYloc, not just the kept subset.)
    xy_all = data.xy_loc.astype(float)
    min_xy, max_xy = float(xy_all.min()), float(xy_all.max())
    coords = (coords - min_xy) / (max_xy - min_xy) * 8.0

    # ── Adjacency ─────────────────────────────────────────────────────────────
    adjMs: dict[str, np.ndarray] = {}
    spike_times: list[np.ndarray] | None = None

    if twop_activity in ("F", "spks", "denoised F"):
        lag_val = round(1000.0 / fs)  # single derived lag
        used_lags = [lag_val]
        src = {"F": F_isc, "spks": spks_isc, "denoised F": denoised_isc}[twop_activity]
        adjMs[f"adjM{lag_val}mslag"] = _corr_columns(src)

    elif twop_activity == "peaks":
        used_lags = list(func_con_lag_val)
        time_points = (data.time_points if data.time_points is not None
                       else np.arange(F_isc.shape[0]) / fs)
        n_units = peak_start_isc.shape[0]

        # Per-unit peak times (s): frame indices (0-indexed) → timePoints.
        spike_times = []
        for u in range(n_units):
            frames = peak_start_isc[u]
            frames = frames[~np.isnan(frames)].astype(int)
            spike_times.append(time_points[frames] if frames.size else np.array([]))

        spike_times_dict = {u: spike_times[u] for u in range(n_units)}
        duration_s = F_isc.shape[0] / fs

        if rng is None:
            rng = np.random.default_rng()
        for lag in used_lags:
            if n_units >= 2:
                _adj_raw, adj_ci = adjm_thr(
                    spike_times_dict, n_units, lag, prob_thresh_tail, fs,
                    duration_s, prob_thresh_rep_num, rng=rng,
                )
            else:
                adj_ci = np.zeros((n_units, n_units))
            adjMs[f"adjM{lag}mslag"] = adj_ci

    else:
        raise ValueError(f"Unknown twop_activity: {twop_activity!r}")

    return Suite2pAdjmResult(
        adjMs=adjMs,
        coords=coords,
        channels=channels,
        F=F_isc,
        denoised_F=denoised_isc,
        spks=spks_isc,
        spike_times=spike_times,
        fs=fs,
        activity_properties=activity_properties,
        func_con_lag_val=used_lags,
    )
