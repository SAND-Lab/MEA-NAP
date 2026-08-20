"""CAT-NAP adjacency-matrix construction.

Port of ``Functions/twoPhoton/suite2pToAdjm.m`` (everything after the denoising
call — the loading/denoising itself lives in ``loader.py`` / ``denoising.py``).

Takes a loaded :class:`~meanap.catnap.loader.Suite2pData` and produces the
functional-connectivity adjacency matrices plus the node coordinates, channel
list, per-unit activity matrices, peak spike times, and event properties that
the rest of the pipeline consumes.

Determinism: ``coords``, ``channels``, ``activity_properties``, ``spike_times``
and the ``corr``-based adjacency (``F`` / ``spks`` / ``denoised F``) are exact
— though the correlation paths now bin first, which MATLAB does not do (see
``suite2p_to_adjm``), so they match MATLAB only at a one-frame bin.
The ``peaks`` adjacency reuses :func:`meanap.pipeline.probabilistic_threshold.adjm_thr`
(STTC + circular-shift thresholding), whose thresholding step is RNG-driven and
therefore only reproducible against MATLAB within tolerance — see that module
and ``python/test_pipeline_catnap.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    #: ``(min, max)`` of the raw pixel centroids, the normalisation that mapped
    #: them onto ``coords``. Kept so anything else in pixel space — the mean
    #: projection image, most usefully — can be mapped into the same frame.
    coord_norm: tuple[float, float] = (0.0, 1.0)
    #: ``{requested bin ms: frames actually averaged}`` for the correlation
    #: paths, empty on the STTC path. Lets the caller say what a requested bin
    #: rounded to, which matters most when it rounded to 1 (no binning at all).
    bin_frames: dict[int, int] = field(default_factory=dict)


def _corr_columns(x: np.ndarray) -> np.ndarray:
    """MATLAB ``corr(X)`` — Pearson correlation between the columns (units) of X."""
    if x.shape[1] == 0:
        return np.zeros((0, 0))
    return np.corrcoef(x, rowvar=False)


def frames_per_bin(bin_ms: float, fs: float) -> int:
    """How many frames make up a *bin_ms* bin at *fs* Hz, at least one.

    A bin shorter than a single frame cannot be built, so it collapses to one
    frame — which is the un-binned correlation, i.e. exactly what this path did
    before bin lengths were settable. That continuity is deliberate: an old
    parameter file with ephys-scale lags still reproduces its old result.
    """
    # floor(x + 0.5), not round(): Python rounds halves to even, so a bin that
    # works out to exactly 166.5 frames would land on 166 — defensible, but not
    # what anyone checking the arithmetic by hand would get.
    return max(1, math.floor(float(bin_ms) * float(fs) / 1000.0 + 0.5))


def _bin_columns(x: np.ndarray, n_frames: int) -> np.ndarray:
    """Average each column of *x* over consecutive blocks of *n_frames* rows.

    The trailing partial bin is dropped rather than averaged over fewer frames:
    a short final bin is noisier than the rest, and it would be the one bin
    whose value depended on where the recording happened to stop.

    Mean and sum give the same correlation here (Pearson is scale-invariant and
    every kept bin holds the same number of frames), so this is equally the
    "sum the spikes in each bin" reading — no need to branch on activity type.
    """
    if n_frames <= 1:
        return x
    n_bins = x.shape[0] // n_frames
    return x[: n_bins * n_frames].reshape(n_bins, n_frames, x.shape[1]).mean(axis=1)


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
        The timescales to build adjacency at, one matrix each. On the
        ``'peaks'`` path these are STTC lags (the coincidence window); on the
        correlation paths they are *bin* lengths — the traces are averaged into
        bins that long and correlated between bins. Empty falls back to one bin
        of ``round(1000 / fs)`` ms, i.e. a single frame, which is the un-binned
        correlation this path used to be fixed at.
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
    bin_frames: dict[int, int] = {}

    if twop_activity in ("F", "spks", "denoised F"):
        # Pearson correlation between binned traces — one adjacency per bin
        # length, mirroring one per lag on the STTC path. The number in the key
        # is the *requested* bin, not the realised one: it has to match what
        # the user typed for the output folders to be predictable, and the
        # rounding to whole frames is reported through ``bin_frames`` instead.
        used_lags = list(func_con_lag_val) or [round(1000.0 / fs)]
        src = {"F": F_isc, "spks": spks_isc, "denoised F": denoised_isc}[twop_activity]
        # Correlating needs at least two bins to correlate *across*; one bin
        # spanning the recording has zero variance and gives an all-NaN matrix,
        # which would carry a whole run's downstream work into nothing. A bin
        # too long for the recording is clamped to half its length instead, and
        # ``bin_frames`` records what it became so the caller can say so.
        max_frames = max(1, src.shape[0] // 2)
        for bin_ms in used_lags:
            n_frames = min(frames_per_bin(bin_ms, fs), max_frames)
            bin_frames[int(bin_ms)] = n_frames
            adjMs[f"adjM{int(bin_ms)}mslag"] = _corr_columns(
                _bin_columns(src, n_frames))

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
        coord_norm=(min_xy, max_xy),
        bin_frames=bin_frames,
    )
