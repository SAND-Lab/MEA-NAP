"""CAT-NAP adjacency-matrix construction.

Port of ``Functions/twoPhoton/suite2pToAdjm.m`` (everything after the denoising
call — the loading/denoising itself lives in ``loader.py`` / ``denoising.py``).

Takes a loaded :class:`~meanap.catnap.loader.Suite2pData` and produces the
functional-connectivity adjacency matrices plus the node coordinates, channel
list, per-unit activity matrices, peak spike times, and event properties that
the rest of the pipeline consumes.

Determinism: ``coords``, ``channels``, ``activity_properties``, ``spike_times``
and the unthresholded ``corr``-based adjacency (``F`` / ``spks`` /
``denoised F``) are exact — though the correlation paths now bin first, which
MATLAB does not do (see ``suite2p_to_adjm``), so they match MATLAB only at a
one-frame bin, and only with ``corr_prob_threshold`` off: the circular-shift
threshold on those paths (:func:`threshold_correlation`) is Python-only and,
like the STTC one, RNG-driven.
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
    """Pearson correlation between the columns (units) of X, without self-edges.

    **Deliberate divergence from MATLAB.** ``suite2pToAdjm.m`` (lines 133-141)
    stores ``double(corr(...))`` as the adjacency and nothing downstream clears
    it, so every node carries a self-loop of weight 1 — the largest weight in
    the matrix. The STTC/ETTC path has always returned a zero diagonal, so the
    two connectivity measures were not producing comparable graphs.

    What that corrupts, for anyone reading old correlation-mode results:

    * ``Dens`` counts ``triu(adjM)`` *including* the diagonal against a
      denominator that excludes it, so density is inflated by ``2/(n-1)`` and
      can exceed 1 — which is how this was found.
    * ``NS`` (``strengths_und``) gains exactly 1.0 per node.
    * ``sigEdgesMean`` / ``sigEdgesTop10`` pool ``adjM[abs(adjM) > 0]``, so n
      maximum-weight self-edges enter the distribution; the top-10% mean is
      hit hardest.

    ``ND`` and ``MEW`` are unaffected: ``find_node_deg_edge_weight`` subtracts
    ``eye(n)`` before thresholding.

    A run that needs the old behaviour bit-for-bit can compare against a
    pre-fix bundle; nothing else in the pipeline depends on the diagonal.
    """
    if x.shape[1] == 0:
        return np.zeros((0, 0))
    c = np.corrcoef(x, rowvar=False)
    # corrcoef of a constant column is NaN throughout; that is a separate
    # concern, handled downstream. Only the self-edges are cleared here.
    np.fill_diagonal(c, 0.0)
    return c


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


def threshold_correlation(
    x: np.ndarray,
    tail: float,
    rep_num: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Pearson adjacency of the columns of *x*, keeping only significant edges.

    The correlation counterpart of
    :func:`~meanap.pipeline.probabilistic_threshold.adjm_thr`: each repetition
    circularly shifts every unit's trace by its own random offset, which keeps
    each trace's own statistics (its values, and its autocorrelation apart
    from the one wrap-around point) while breaking the timing between units.
    An edge survives only if its real correlation is at least the
    ``ceil((1 - tail) * rep_num)``-th smallest of its ``rep_num`` surrogate
    correlations — the same one-sided, upper-tail cutoff the STTC path uses,
    so ``prob_thresh_tail`` means the same thing on both. Being one-sided, it
    zeroes every negative correlation along with the weak positive ones.

    *x* is the already-binned ``(n_bins, n_units)`` activity: it is the binned
    series that gets correlated, so it is the binned series that is shifted.
    Offsets are drawn from ``1 .. n_bins - 1``, so no surrogate is the real
    data unshifted.

    Rather than holding every surrogate matrix (``n² × rep_num`` floats — over
    a gigabyte for a thousand cells at 200 repetitions), this counts per edge
    how many surrogates fall at or below the real value. The edge's cutoff
    surrogate is at or below the real value exactly when at least
    ``cutoff + 1`` of them are, so the result is the one sorting would give.

    NaN edges (a unit whose binned trace is constant) are left NaN, as the
    unthresholded path leaves them: that is handled downstream.
    """
    real = _corr_columns(x)
    n_bins, n_units = x.shape
    if n_units < 2 or n_bins < 2:
        return real

    # Correlation is a dot product of z-scores, and a circular shift permutes
    # a column without changing its mean or spread — so standardise once and
    # each repetition is a single matrix product. A constant column (std 0)
    # contributes zeros; its real edges are NaN and stay NaN.
    sd = x.std(axis=0)
    z = np.divide(x - x.mean(axis=0), sd, out=np.zeros(x.shape), where=sd > 0)

    cutoff = math.ceil((1 - tail) * rep_num) - 1  # 0-indexed, as adjm_thr
    cutoff = min(max(cutoff, 0), rep_num - 1)

    rows = np.arange(n_bins)[:, None]
    cols = np.arange(n_units)[None, :]
    at_or_below = np.zeros((n_units, n_units), dtype=np.int32)
    for _ in range(rep_num):
        k = rng.integers(1, n_bins, size=n_units)  # 1 .. n_bins-1
        shifted = z[(rows - k[None, :]) % n_bins, cols]
        at_or_below += (shifted.T @ shifted / n_bins) <= real

    # Decide each edge once, from the upper triangle, and mirror it. The two
    # halves are compared separately against floating-point surrogates, so on
    # a near-tie (highly correlated cells) they could otherwise disagree — and
    # an asymmetric matrix breaks the undirected metrics downstream.
    drop = np.triu(at_or_below <= cutoff, k=1)
    drop |= drop.T
    out = real.copy()
    out[drop & ~np.isnan(real)] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def suite2p_to_adjm(
    data: Suite2pData,
    twop_activity: str,
    func_con_lag_val: list[int],
    *,
    remove_nodes_with_no_peaks: bool = False,
    prob_thresh_tail: float = 0.05,
    prob_thresh_rep_num: int = 200,
    corr_prob_threshold: bool = False,
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
    corr_prob_threshold
        On the correlation paths, keep only edges that beat circular-shift
        surrogates of the binned traces (:func:`threshold_correlation`, using
        ``prob_thresh_tail`` / ``prob_thresh_rep_num``). Off here so a direct
        call returns the plain correlation matrix; a pipeline run takes it
        from ``Params.twop_corr_prob_thresh``, which is on by default. The
        ``peaks`` path is always thresholded and ignores this.
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
        if corr_prob_threshold and rng is None:
            rng = np.random.default_rng()
        for bin_ms in used_lags:
            n_frames = min(frames_per_bin(bin_ms, fs), max_frames)
            bin_frames[int(bin_ms)] = n_frames
            binned = _bin_columns(src, n_frames)
            adjMs[f"adjM{int(bin_ms)}mslag"] = (
                threshold_correlation(binned, prob_thresh_tail,
                                      prob_thresh_rep_num, rng)
                if corr_prob_threshold else _corr_columns(binned))

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
