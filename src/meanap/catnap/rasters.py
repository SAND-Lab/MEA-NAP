"""The per-recording activity raster for CAT-NAP — plain and z-scored.

``MEApipeline.m`` draws a ``3_Raster`` for every suite2p recording: the
activity matrix the network was built from, cells down the side and time
along the bottom (``rasterPlot.m`` with ``get2pActivityMatrix``). The Python
port had no equivalent — a CAT-NAP run's ``2A_IndividualNeuronalAnalysis``
folder held only the per-cell trace figures, so nothing showed the whole
population at once, and nothing showed what the measure of activity the run
was configured with actually looks like.

Two figures per recording and measure:

* ``3_ActivityRaster`` — the measure as it is: event counts per second under
  ``peaks``, the trace averaged into one-second bins otherwise. The colour
  ceiling is a percentile of the recording (``raster_plot_upper_percentile``),
  as in MATLAB, so a few very bright cells do not wash out the rest.
* ``4_ActivityRaster_zscored`` — the same matrix with every cell standardised
  over time. A raw raster is dominated by whichever cells are brightest or
  most active; z-scoring puts every cell on the same footing so the *timing*
  of activity — population events, cells that fire together — is what stands
  out. Diverging colours centred on zero, symmetric ceiling.

Both are drawn from :func:`binned_activity`, a ``(n_seconds, n_units)``
float32 matrix that the pipeline stores in each recording's state file. That
is what lets the viewer redraw them from a bundle: the full activity matrices
are hundreds of MB per recording and are deliberately not carried, but at one
row per second the population is a few hundred kB, and one second is the
resolution MATLAB's raster shows anyway.

**Deviation from MATLAB.** ``rasterPlot.m`` reduces a continuous trace to one
sample per second with ``interp1`` — it *samples* one frame out of every
``fs``, discarding the rest. Here the bin is the mean of its frames, which is
what downsampling should mean and is what the ephys path does with its spike
counts (``downSampleSum``). The two agree in what they show; the binned
version is just less noisy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = [
    "RASTER_BIN_S",
    "RASTER_FIGURES",
    "binned_activity",
    "zscore_units",
    "plot_activity_raster",
    "activity_colorbar_label",
]

#: Width of one raster column, in seconds. One second, like MATLAB's.
RASTER_BIN_S = 1.0

#: ``(file stem, viewer label, z-scored?)`` for the two figures, in the order
#: they are listed. The stems are distinct from the ephys ``3_Raster`` so the
#: report's per-figure descriptions can tell them apart.
RASTER_FIGURES: tuple[tuple[str, str, bool], ...] = (
    ("3_ActivityRaster", "Activity raster", False),
    ("4_ActivityRaster_zscored", "Activity raster (z-scored per cell)", True),
)

#: Colorbar text per measure. Only ``peaks`` counts anything; the rest are
#: the trace's own units, averaged.
_COLORBAR_LABELS = {
    "peaks": "Events / s",
    "spks": "Deconvolved activity (a.u.)",
    "denoised F": "Denoised fluorescence (a.u.)",
    "F": "Fluorescence (a.u.)",
}


def activity_colorbar_label(activity: str) -> str:
    return _COLORBAR_LABELS.get(str(activity), f"{activity} (a.u.)")


def binned_activity(
    activity: str,
    fs: float,
    duration_s: float,
    *,
    spike_times: list[np.ndarray] | None = None,
    matrix: np.ndarray | None = None,
    bin_s: float = RASTER_BIN_S,
) -> np.ndarray:
    """The ``(n_bins, n_units)`` raster matrix for one recording and measure.

    ``peaks`` counts each unit's events per bin from *spike_times* (seconds);
    every other measure averages *matrix* (``(n_frames, n_units)``) over the
    frames of each bin. A trailing partial bin is kept — averaged over the
    frames it has — so a 61.5 s recording is 62 columns, not 61.

    float32: it is a picture's worth of data, stored per recording per measure,
    and float64 would double the bundle cost for precision no colour map shows.
    """
    n_bins = max(1, int(np.ceil(duration_s / bin_s - 1e-9)))
    if activity == "peaks":
        if spike_times is None:
            raise ValueError("spike_times is required to bin 'peaks'")
        out = np.zeros((n_bins, len(spike_times)), dtype=np.float32)
        edges = np.arange(n_bins + 1) * bin_s
        for u, times in enumerate(spike_times):
            times = np.asarray(times, dtype=float).ravel()
            if times.size:
                out[:, u], _ = np.histogram(times, bins=edges)
        return out

    if matrix is None:
        raise ValueError(f"matrix is required to bin {activity!r}")
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2:
        raise ValueError(f"activity matrix must be 2-D, got shape {m.shape}")
    frames_per_bin = max(1, int(round(fs * bin_s)))
    n_frames, n_units = m.shape
    n_bins = max(n_bins, int(np.ceil(n_frames / frames_per_bin)))
    out = np.full((n_bins, n_units), np.nan, dtype=np.float32)
    for b in range(n_bins):
        chunk = m[b * frames_per_bin:(b + 1) * frames_per_bin]
        if chunk.shape[0]:
            out[b] = chunk.mean(axis=0)
    return out


def zscore_units(binned: np.ndarray) -> np.ndarray:
    """Standardise each unit (column) over time.

    A unit with no variance — silent throughout, or a constant trace — has no
    z-score; it comes back as a row of zeros rather than NaN so it draws as
    "at its own mean" instead of as a hole in the picture. NaN bins (there are
    none from :func:`binned_activity`, but a stored matrix could carry them)
    are ignored in the mean and SD and stay NaN.
    """
    x = np.asarray(binned, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nanmean(x, axis=0, keepdims=True)
        sd = np.nanstd(x, axis=0, keepdims=True)
        z = (x - mean) / sd
    flat = np.broadcast_to(~(sd > 0), z.shape)
    z = np.where(flat & ~np.isnan(x), 0.0, z)
    return z.astype(np.float32)


def plot_activity_raster(
    binned: np.ndarray,
    out_path: Path | str,
    *,
    activity: str,
    title: str,
    zscored: bool = False,
    bin_s: float = RASTER_BIN_S,
    upper_percentile: float = 99.0,
    colormap: str = "parula",
) -> Path:
    """Draw one raster — plain, or per-cell z-scored — and save it.

    *binned* is ``(n_bins, n_units)`` from :func:`binned_activity`; it is
    transposed for display so cells run down the y axis in stored order (the
    order of ``channels``), the first cell at the top.

    The plain raster's colour ceiling is the *upper_percentile* of the matrix,
    floored at 1 event/s for ``peaks`` (MATLAB's ``max(prctile, 1)``) and at
    the matrix maximum otherwise — a fluorescence trace can sit entirely below
    1, and MATLAB's floor would blank it. The z-scored raster uses a diverging
    map centred on zero with a symmetric ceiling at the same percentile of
    ``|z|``, floored at 1 SD.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from meanap.pipeline.figure_output import savefig
    from meanap.pipeline.plotting_step2 import parula_85

    out_path = Path(out_path)
    mat = np.asarray(binned, dtype=float)
    if zscored:
        mat = zscore_units(mat)
    n_bins, n_units = mat.shape
    duration_s = n_bins * bin_s
    finite = mat[np.isfinite(mat)]

    if zscored:
        ceiling = float(np.percentile(np.abs(finite), upper_percentile)) if finite.size else 1.0
        vmax = max(ceiling, 1.0)
        vmin = -vmax
        cmap = "RdBu_r"
        cbar_label = "z-score (per cell)"
    else:
        ceiling = float(np.percentile(finite, upper_percentile)) if finite.size else 0.0
        floor = 1.0 if activity == "peaks" else (float(finite.max()) if finite.size else 0.0)
        vmax = max(ceiling, floor)
        if not vmax > 0:
            vmax = 1.0
        vmin = 0.0
        cmap = "gray_r" if str(colormap).lower() == "gray" else parula_85
        cbar_label = activity_colorbar_label(activity)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    im = ax.imshow(
        mat.T, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax,
        extent=[0, duration_s, n_units, 0], interpolation="nearest",
    )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cell")
    ax.set_title(title, fontsize=10)
    ax.tick_params(direction="out")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label(cbar_label)
    cbar.outline.set_visible(False)
    fig.tight_layout()
    savefig(fig, out_path, default_dpi=150)
    plt.close(fig)
    return out_path
