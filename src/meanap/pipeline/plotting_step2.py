import math
from pathlib import Path

import numpy as np
from meanap.pipeline.figure_output import savefig
from meanap.pipeline.rng import derive_seed_int
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.spreadsheet import parse_ground_electrodes
from meanap.pipeline.parula import cm_data as parula_data
from meanap.pipeline.plotting_step4 import comparison_figure_stem, plot_half_violin_by_x
# Create 85% parula colormap
parula_85 = LinearSegmentedColormap.from_list('parula_85', parula_data[:int(len(parula_data)*0.85)])

def _fnt(rec_name: str) -> str:
    """MATLAB's ``FNt``: the recording name with its underscores removed."""
    return rec_name.replace("_", "")


def _div_text(div) -> str:
    """A DIV as MATLAB's ``num2str`` prints it: ``14``, not ``14.0``."""
    try:
        f = float(div)
    except (TypeError, ValueError):
        return str(div)
    return str(int(f)) if f.is_integer() else str(div)


def plot_firing_rate_distribution(ephys: dict, out_path: Path, seed: int | None = None,
                                  rec_name: str = "", div=None, kde_height: float = 0.3):
    """Half-violin of per-electrode firing rate, port of ``firingRateElectrodeDistribution.m``.

    Drawn as MATLAB draws it, with ``HalfViolinPlot`` (:func:`_half_violin`):
    grey KDE to the right, jittered electrodes to the left, black mean dot and
    SEM bar; x from 0.5 to 1.5 without ticks, ``age<DIV>`` under it, the
    recording's ``FNt`` as the title, and y from 0 to 15 % above the fastest
    electrode (at least 0.1 Hz). ``kde_height`` is ``Params.kdeHeight``.

    ``seed`` fixes the jitter, so two identically-seeded runs — or the
    pipeline's copy and one redrawn from a bundle — give the same figure.
    """
    from meanap.pipeline.metric_limits import metric_limits
    from meanap.pipeline.plotting_step4 import _half_violin

    fr = np.asarray(ephys.get("FR", []), dtype=float)
    if len(fr) == 0:
        return

    fig, ax = plt.subplots(figsize=(5.0, 6.0))   # MATLAB: [50 50 500 600] px
    _half_violin(ax, fr, pos=1.0, colour=(0.5, 0.5, 0.5), width=kde_height,
                 rng=np.random.default_rng(seed), limits=metric_limits("FR"))
    ax.set_xlim(0.5, 1.5)
    ax.set_xticks([])
    if div is not None:
        ax.set_xlabel(f"age{_div_text(div)}")
    ax.set_ylabel("mean firing rate per electrode (Hz)")
    ax.set_title(_fnt(rec_name), fontsize=8)   # TitleFontSizeMultiplier 0.7
    # MATLAB's ``aesthetics``: no box, ticks out.
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out")
    finite = fr[np.isfinite(fr)]
    top = max(float(finite.max()) if finite.size else 0.0, 0.1)
    ax.set_ylim(0, top * 1.15)
    plt.tight_layout()
    savefig(fig, out_path, default_dpi=300)
    plt.close(fig)

#: Marker area (pt²) of an electrode on the built-in 8×8 layouts, whose
#: neighbours sit 8/7 plot units apart.
_HEATMAP_MARKER_AREA = 800
_HEATMAP_GRID_SPACING = 8 / 7


def _heatmap_marker_area(xs: np.ndarray, ys: np.ndarray) -> float:
    """Marker area for electrodes as densely packed as these.

    Scaled from the 8×8 grids' size by the median nearest-neighbour distance,
    so neighbouring electrodes of an HD-MEA do not paint over each other.
    """
    from scipy.spatial import cKDTree

    xy = np.unique(np.column_stack([xs, ys]), axis=0)
    if len(xy) < 2:
        return _HEATMAP_MARKER_AREA
    d, _ = cKDTree(xy).query(xy, k=2)
    ratio = float(np.median(d[:, 1])) / _HEATMAP_GRID_SPACING
    return float(np.clip(_HEATMAP_MARKER_AREA * ratio ** 2, 2.0, _HEATMAP_MARKER_AREA))


def _draw_heatmap_panel(ax, xs, ys, metric, valid_mask, vmin, vmax, cmap, clabel, panel_title,
                        marker_area: float = _HEATMAP_MARKER_AREA):
    """Draw one electrode heatmap panel (colored circles at electrode coords)."""
    s = marker_area
    lw = 1 if s >= 100 else 0
    if not np.all(valid_mask):
        ax.scatter(xs[~valid_mask], ys[~valid_mask], color="lightgray", s=s,
                   marker="o", edgecolors="white", linewidths=lw)
    # No electrode with a value (no bursts detected, say) leaves nothing for a
    # colour bar to describe: it would only show the placeholder range, or the
    # batch's maximum on the dataset-scaled panel.
    if np.any(valid_mask):
        sc = ax.scatter(xs[valid_mask], ys[valid_mask], c=metric[valid_mask], cmap=cmap,
                        vmin=vmin, vmax=vmax, s=s, marker="o", edgecolors="white", linewidths=lw)
        cbar = plt.colorbar(sc, ax=ax)
        cbar.set_label(clabel)
    ax.set_title(panel_title)
    ax.axis("off")
    ax.set_aspect("equal", "box")


def _pool_units_by_electrode(chs: np.ndarray, metric: np.ndarray, aggregate: str):
    """One value per electrode from the values of the units on it."""
    electrodes = np.unique(chs)
    pooled = np.full(len(electrodes), np.nan)
    for i, e in enumerate(electrodes):
        vals = metric[chs == e]
        vals = vals[np.isfinite(vals)]
        if len(vals):
            pooled[i] = vals.sum() if aggregate == "sum" else vals.mean()
    return electrodes, pooled


def plot_heatmap(
    metric: np.ndarray, chs: np.ndarray, title: str, clabel: str, out_path: Path,
    cmap="viridis", channel_layout: str = "Axion64",
    batch_max: float | None = None,
    aggregate: str = "mean",
    layout: tuple[np.ndarray, np.ndarray] | None = None,
    grounded: set[int] | None = None,
):
    """Electrode heatmap, port of ``electrodeHeatMaps.m`` / ``plotNodeHeatmap.m``.

    ``grounded`` is the recording's grounded electrode IDs. They are drawn
    grey, as ``electrodeHeatMaps.m`` draws them, and kept out of the colour
    range: grounding empties their spike trains, so left in they would read as
    silent electrodes and set the bottom of the scale. (MATLAB's burst heatmaps,
    ``plotNodeHeatmap.m``, are never passed the list; here every heatmap is.)

    ``layout`` is the recording's own ``(channels, coords)`` when the array
    has no fixed layout (see :func:`~meanap.pipeline.channel_layout.recording_layout`);
    ``channel_layout`` is used otherwise.

    ``aggregate`` (``"sum"`` or ``"mean"``) only matters when several nodes
    share an electrode — a spike-sorted run — and says how they pool.

    When ``batch_max`` is given, produce a two-panel figure (like MATLAB's
    ``tiledlayout(1,2)``): left scaled to this recording (color axis = 99th
    percentile of its own values), right scaled to the entire dataset (color
    axis = ``batch_max``, the batch-wide max of this metric = MATLAB's
    ``maxValStruct.(metric)``), so levels are comparable across recordings.
    When ``batch_max`` is None, fall back to the original single panel.

    ``title`` is the recording's ``FNt``; as in MATLAB the panels read
    "<FNt> scaled to recording" and "<FNt> scaled to entire dataset", and the
    metric is named by the colour bar alone.
    """
    # Note: metric length could be 0 if the caller doesn't pad it.
    if len(metric) == 0:
        return

    layout_channels, layout_coords = (layout if layout is not None
                                      else get_coords_from_layout(channel_layout))
    coord_by_channel = dict(zip(layout_channels.tolist(), map(tuple, layout_coords)))
    chs = np.asarray(chs).ravel()
    metric = np.asarray(metric, dtype=float)
    # A spike-sorted run has several nodes per electrode (its units), listed
    # under the same electrode ID. An electrode heatmap has one cell per
    # electrode, so units are pooled onto theirs: summed for rates and
    # fractions of spikes — what the electrode as a whole did — averaged for
    # everything else. A detected run has no repeats and is left as it is.
    if len(np.unique(chs)) < len(chs):
        chs, metric = _pool_units_by_electrode(chs, metric, aggregate)
    keep = np.array([int(c) in coord_by_channel for c in chs])
    if not np.any(keep):
        return
    coords = np.array([coord_by_channel[int(c)] for c in chs[keep]])
    metric = metric[keep]
    if grounded:
        metric = np.where(np.isin(chs[keep].astype(int), list(grounded)), np.nan, metric)
    xs = coords[:, 0]
    ys = coords[:, 1]
    valid_mask = ~np.isnan(metric)
    marker_area = (_heatmap_marker_area(xs, ys) if layout is not None
                   else _HEATMAP_MARKER_AREA)

    if np.any(valid_mask):
        valid_vals = metric[valid_mask]
        vmin = float(np.min(valid_vals))
        recording_vmax = float(np.percentile(valid_vals, 99))
    else:
        vmin, recording_vmax = 0.0, 1.0
    if vmin == recording_vmax:
        recording_vmax = vmin + 1e-5

    if batch_max is None:
        fig, ax = plt.subplots(figsize=(6, 5))
        _draw_heatmap_panel(ax, xs, ys, metric, valid_mask, vmin, recording_vmax, cmap, clabel, title,
                            marker_area)
        plt.tight_layout()
        savefig(fig, out_path, default_dpi=300)
        plt.close(fig)
        return

    batch_vmax = float(batch_max)
    if batch_vmax <= vmin or np.isnan(batch_vmax):
        batch_vmax = vmin + 1e-5

    fig, (ax_rec, ax_batch) = plt.subplots(1, 2, figsize=(12, 5))
    _draw_heatmap_panel(ax_rec, xs, ys, metric, valid_mask, vmin, recording_vmax, cmap,
                        clabel, f"{title} scaled to recording", marker_area)
    _draw_heatmap_panel(ax_batch, xs, ys, metric, valid_mask, vmin, batch_vmax, cmap,
                        clabel, f"{title} scaled to entire dataset", marker_area)
    plt.tight_layout()
    savefig(fig, out_path, default_dpi=300)
    plt.close(fig)

def plot_raster(
    spike_times_dict: dict,
    duration_s: float,
    out_path: Path,
    spike_freq_max: float | None = None,
    raster_upper_percentile: float = 99.0,
    rec_name: str = "",
):
    """Two-panel raster, port of ``rasterPlot.m``.

    The time axis is in minutes, as MATLAB's is. Only the axis is rescaled:
    the bins stay one second wide, so each cell is still a count per second
    (Hz) and the colour bar keeps its meaning.

    Top panel is scaled to this recording (color axis = the
    ``raster_upper_percentile`` of its own 1-second spike counts); bottom panel
    is scaled to the entire data batch (color axis = ``spike_freq_max``, the
    batch-wide max firing rate). Sharing the bottom scale across every
    recording makes activity levels visually comparable between them — this is
    what MATLAB's ``spikeFreqMax`` (``maxValStruct.FR``) does. When
    ``spike_freq_max`` is None (e.g. a single recording plotted in isolation)
    the batch panel falls back to this recording's own percentile scale.
    """
    n_channels = len(spike_times_dict)
    n_bins = max(1, int(np.ceil(duration_s)))

    # Downsample to 1-second bins: each cell is that channel's spike count in
    # that second, i.e. its instantaneous firing rate in Hz.
    raster_mat = np.zeros((n_channels, n_bins))
    for ch, times in spike_times_dict.items():
        if len(times) > 0:
            counts, _ = np.histogram(times, bins=n_bins, range=(0, n_bins))
            raster_mat[ch, :] = counts

    recording_vmax = max(1.0, np.percentile(raster_mat, raster_upper_percentile))
    batch_vmax = max(1.0, spike_freq_max) if spike_freq_max is not None else recording_vmax

    fig, (ax_rec, ax_batch) = plt.subplots(2, 1, figsize=(10, 8))
    fnt = _fnt(rec_name)

    for ax, vmax, title in (
        (ax_rec, recording_vmax, f"{fnt} raster scaled to recording"),
        (ax_batch, batch_vmax, f"{fnt} raster scaled to entire data batch"),
    ):
        im = ax.imshow(
            raster_mat, aspect="auto", cmap=parula_85, vmin=0, vmax=vmax,
            extent=[0, duration_s / 60.0, n_channels, 0],
        )
        ax.set_ylabel("Electrode")
        ax.set_xlabel("Time (min)")
        ax.set_title(title, fontsize=10)
        cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
        cbar.set_label("Firing Rate (Hz)")

    plt.tight_layout()
    savefig(fig, out_path, default_dpi=300)
    plt.close(fig)

def plot_burst_detection_info(spike_times_dict: dict, ephys: dict, duration_s: float, fs: float, out_path: Path):
    fig, axes = plt.subplots(3, 1, figsize=(10, 10))
    
    ax_raster_full = axes[0]
    ax_raster_burst = axes[1]
    ax_isi = axes[2]
    
    n_channels = len(spike_times_dict)
    # Downsample to 10 Hz (0.1s bins) for raster plotting
    n_bins = int(np.ceil(duration_s * 10))
    
    raster_full = np.zeros((n_channels, n_bins))
    raster_burst = np.zeros((n_channels, n_bins))
    burst_times = ephys.get("burstTimes", [])
    
    all_spikes = []
    
    for ch, times in spike_times_dict.items():
        if len(times) > 0:
            all_spikes.extend(times)
            
            # Full raster
            counts, _ = np.histogram(times, bins=n_bins, range=(0, duration_s))
            raster_full[ch, :] = counts
            
            # Burst raster
            in_burst_times = []
            for t in times:
                for (t0, t1) in burst_times:
                    if t0 <= t <= t1:
                        in_burst_times.append(t)
                        break
            if len(in_burst_times) > 0:
                counts_burst, _ = np.histogram(in_burst_times, bins=n_bins, range=(0, duration_s))
                raster_burst[ch, :] = counts_burst
                
    ax_raster_full.imshow(raster_full, aspect='auto', cmap=parula_85, extent=[0, duration_s, n_channels, 0])
    ax_raster_full.set_xlim(0, duration_s)
    ax_raster_full.set_title("Downsampled raster")
    ax_raster_full.set_ylabel("Electrodes")
    
    ax_raster_burst.imshow(raster_burst, aspect='auto', cmap=parula_85, extent=[0, duration_s, n_channels, 0])
    ax_raster_burst.set_xlim(0, duration_s)
    ax_raster_burst.set_title("Raster with only bursts")
    ax_raster_burst.set_ylabel("Electrodes")
    ax_raster_burst.set_xlabel("Time (s)")
    
    if len(all_spikes) > 0:
        all_spikes = np.sort(all_spikes)
        isi = np.diff(all_spikes)
        
        isi_within = []
        isi_outside = []
        
        for i in range(len(isi)):
            t_mid = all_spikes[i] + isi[i]/2.0
            in_burst = False
            for (t0, t1) in burst_times:
                if t0 <= t_mid <= t1:
                    in_burst = True
                    break
            if in_burst:
                isi_within.append(isi[i])
            else:
                isi_outside.append(isi[i])
                
        if len(isi) > 0:
            min_val = max(1e-5, np.min(isi))
            max_val = np.max(isi)
            if max_val > min_val:
                bins = np.logspace(np.log10(min_val), np.log10(max_val), 100)
                if len(isi_outside) > 0:
                    ax_isi.hist(isi_outside, bins=bins, density=True, histtype='step', label='Outside Bursts', color='blue')
                if len(isi_within) > 0:
                    ax_isi.hist(isi_within, bins=bins, density=True, histtype='step', label='Within Bursts', color='red')
                ax_isi.set_xscale('log')
                ax_isi.set_xlabel("Inter-Spike Interval (s)")
                ax_isi.set_ylabel("Probability")
                ax_isi.legend()
                ax_isi.set_title("ISI Distribution: Within vs. Outside Bursts")
    
    plt.tight_layout()
    savefig(fig, out_path, default_dpi=300)
    plt.close(fig)

#: The per-channel heatmaps, as ``(figure name, ephys key, colour-bar label,
#: colormap)``. One list rather than six near-identical call sites, so the
#: pipeline and the bundle renderer cannot disagree about which figures exist
#: or what they are called. Names and colour-bar labels are MATLAB's
#: (``electrodeHeatMaps.m``, ``plotNodeHeatmap.m``); the burst heatmaps are
#: numbered 4-8, after ``3_Raster``.
#: How the units of one electrode pool onto it in a sorted run (see
#: :func:`plot_heatmap`). Rates and burst rates add up; the rest are per-unit
#: properties and average.
_POOL_BY_SUM = {"FR": "sum", "channelBurstRate": "sum"}

ACTIVITY_HEATMAPS = (
    ("2_Heatmap.png", "FR", "mean firing rate (Hz)", "viridis"),
    ("4_BurstRate_heatmap.png", "channelBurstRate",
     "Mean burst rate (per minute)", "plasma"),
    ("5_BurstDur_heatmap.png", "channelBurstDur",
     "Mean burst duration (ms)", "plasma"),
    ("6_FractSpikesInBursts_heatmap.png", "channelFracSpikesInBursts",
     "Fraction spikes in bursts", "plasma"),
    ("7_ISIwithinBurst_heatmap.png", "channelISIwithinBurst",
     "ISI within bursts (ms)", "plasma"),
    ("8_ISIoutsideBurst_heatmap.png", "channeISIoutsideBurst",
     "ISI outside bursts (ms)", "plasma"),
)


def plot_neuronal_activity_checks(
    rec,
    params,
    spike_times_dict: dict,
    n_channels: int,
    chs: np.ndarray,
    fs: float,
    duration_s: float,
    ephys: dict,
    output_root: Path,
    spike_freq_max: float | None = None,
    batch_max: dict | None = None,
    fmt: str = "png",
    only: str | None = None,
    layout: tuple[np.ndarray, np.ndarray] | None = None,
) -> list[Path]:
    """Draw one recording's step-2 activity figures.

    ``fmt`` selects the image format (``svg``/``pdf`` give vector output) and
    ``only`` restricts the call to the single figure with that base name — the
    two hooks the bundle viewer needs to render one plot per request. Both
    default to the pipeline's behaviour: every figure, as PNG.

    Returns the paths actually written.
    """
    out_dir = output_root / rec.group / rec.filename
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    def want(name: str) -> Path | None:
        stem = Path(name).stem
        if only is not None and stem != only:
            return None
        path = out_dir / f"{stem}.{fmt}"
        written.append(path)
        return path

    channel_layout = getattr(params, "channel_layout", "Axion64")
    bmax = batch_max or {}

    if (p := want("1_FiringRateByElectrode.png")) is not None:
        plot_firing_rate_distribution(
            ephys, p,
            seed=derive_seed_int(params.random_seed, "step2-plots", rec.filename),
            rec_name=rec.filename, div=rec.div,
            kde_height=getattr(params, "kde_height", 0.3))

    for name, key, cbar, cmap in ACTIVITY_HEATMAPS:
        if key not in ephys:
            continue
        if (p := want(name)) is not None:
            plot_heatmap(ephys[key], chs, _fnt(rec.filename), cbar, p, cmap=cmap,
                         channel_layout=channel_layout, batch_max=bmax.get(key), layout=layout,
                         aggregate=_POOL_BY_SUM.get(key, "mean"),
                         grounded=parse_ground_electrodes(rec.ground))

    if (p := want("3_Raster.png")) is not None:
        plot_raster(
            spike_times_dict, duration_s, p,
            spike_freq_max=spike_freq_max,
            raster_upper_percentile=getattr(params, "raster_plot_upper_percentile", 99.0),
            rec_name=rec.filename,
        )

    if (p := want("8_BurstDetectionInfo.png")) is not None:
        plot_burst_detection_info(spike_times_dict, ephys, duration_s, fs, p)

    return [p for p in written if p.exists()]


import pandas as pd

#: Recording-level activity metrics and their labels, in ``PlotEphysStats.m``'s
#: order and wording (``eMetl``). The label is the y label and the file name;
#: the position is the file's ``<n>``.
EPHYS_REC_METRICS = {
    "numActiveElec": "number of active electrodes",
    "FRmean": "mean firing rate (Hz)",
    "FRmedian": "median firing rate (Hz)",
    "NBurstRate": "network burst rate (per minute)",
    "meanNumChansInvolvedInNbursts": "mean number of channels involved in network bursts",
    "meanNBstLengthS": "mean network burst length (s)",
    "meanISIWithinNbursts_ms": "mean ISI within network burst (ms)",
    "meanISIoutsideNbursts_ms": "mean ISI outside network bursts (ms)",
    "CVofINBI": "coefficient of variation of inter network burst intervals",
    "fracInNburst": "fraction of bursts in network bursts",
    "channelAveBurstRate": "Single-electrode burst rate (per minute)",
    "channelAveBurstDur": "Single-electrode average burst duration (ms)",
    "channelAveISIwithinBurst": "Single-electrode average ISI within burst (ms)",
    "channelAveISIoutsideBurst": "Single-electrode average ISI outside burst (ms)",
    "channelAveFracSpikesInBursts": "Mean fraction of spikes in bursts per electrode",
}

#: Node-level activity metrics (``cMetl``). MATLAB stores the first two with
#: underscores and swaps them for spaces before using them.
EPHYS_NODE_METRICS = {
    "FR": "mean firing rate node",
    "FRactive": "mean firing rate active node",
    "channelBurstRate": "Unit burst rate (per minute)",
    "channelWithinBurstFr": "Unit within-burst firing rate (Hz)",
    "channelBurstDur": "Unit burst duration (ms)",
    "channelISIwithinBurst": "Unit ISI within burst (ms)",
    "channeISIoutsideBurst": "Unit ISI outside burst (ms)",
    "channelFracSpikesInBursts": "Unit fraction of spikes in bursts",
}

# ── Feasible y-axis ranges for the comparison violins ────────────────────────
#
# Port of ``eMetCustomBounds`` in ``PlotEphysStats.m``: a count, rate or
# duration is drawn from zero, a fraction on [0, 1]. ``None`` is MATLAB's
# ``nan`` — that end is left to the data. MATLAB's table only names the
# recording-level metrics; the same rule is applied to the node level here,
# since a unit's burst rate is no more able to go negative than an array's.
EPHYS_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    # Recording level
    "numActiveElec": (0, None),
    "FRmean": (0, None),
    "FRmedian": (0, None),
    "NBurstRate": (0, None),
    "meanNumChansInvolvedInNbursts": (0, None),
    "meanNBstLengthS": (0, None),
    "meanISIWithinNbursts_ms": (0, None),
    "meanISIoutsideNbursts_ms": (0, None),
    "CVofINBI": (0, None),
    "fracInNburst": (0, 1),
    "channelAveBurstRate": (0, None),
    "channelAveBurstDur": (0, None),
    "channelAveISIwithinBurst": (0, None),
    "channelAveISIoutsideBurst": (0, None),
    "channelAveFracSpikesInBursts": (0, 1),
    # Node level
    "FR": (0, None),
    "FRactive": (0, None),
    "channelBurstRate": (0, None),
    "channelWithinBurstFr": (0, None),
    "channelBurstDur": (0, None),
    "channelISIwithinBurst": (0, None),
    "channeISIoutsideBurst": (0, None),
    "channelFracSpikesInBursts": (0, 1),
}


def ephys_bounds(metric: str) -> tuple[float | None, float | None] | None:
    """The y-range *metric*'s comparison violins are drawn on, or ``None``."""
    return EPHYS_BOUNDS.get(metric)

def _plot_violin(df: pd.DataFrame, metric: str, group_col: str, out_path: Path, ylabel: str) -> None:
    if df.empty or metric not in df.columns or df[metric].dropna().empty:
        return
        
    df_plot = df.dropna(subset=[metric])
    if df_plot.empty:
        return
        
    fig, ax = plt.subplots(figsize=(max(4, len(df_plot[group_col].unique()) * 1.5), 6))
    
    sns.violinplot(
        data=df_plot, x=group_col, y=metric,
        ax=ax, color="lightgray", inner=None, linewidth=1
    )
    sns.stripplot(
        data=df_plot, x=group_col, y=metric,
        ax=ax, color="black", size=4, jitter=True, alpha=0.6
    )
    
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.set_title(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    savefig(fig, out_path, default_dpi=300, bbox_inches="tight")
    plt.close(fig)

def ephys_comparison_frames(
    recordings: list,
    all_ephys: dict,
    custom_grp_order: list[str] | None = None,
) -> tuple["pd.DataFrame", "pd.DataFrame"]:
    """The recording- and node-level tables every 2B comparison plot is drawn from.

    The step-2 counterpart of
    :func:`~meanap.pipeline.plotting_step4.netmet_comparison_frames`, and split
    out for the same reason: so one figure can be drawn on its own by the same
    code that draws the folder. There is no ``Lag`` column here — step-2
    activity metrics do not depend on the STTC lag.

    Returns empty frames when nothing matched, rather than raising.
    """
    from meanap.pipeline.plotting_step4 import _apply_group_order

    rec_rows = []
    node_rows = []

    for rec in recordings:
        if rec.filename not in all_ephys:
            continue

        ephys = all_ephys[rec.filename]
        base = {"FileName": rec.filename, "Grp": rec.group, "DIV": str(rec.div)}

        # Recording-level
        rec_row = dict(base)
        for k in EPHYS_REC_METRICS:
            if k in ephys:
                val = ephys[k]
                if isinstance(val, (list, np.ndarray)) and np.size(val) == 1:
                    val = val[0]
                rec_row[k] = val
        rec_rows.append(rec_row)

        # Node-level
        num_nodes = len(ephys.get("FR", []))
        if num_nodes > 0:
            for ch in range(num_nodes):
                node_row = dict(base)
                node_row["Channel"] = ch + 1
                for k in EPHYS_NODE_METRICS:
                    if k in ephys and len(ephys[k]) > ch:
                        node_row[k] = ephys[k][ch]
                node_rows.append(node_row)

    df_rec = pd.DataFrame(rec_rows)
    df_node = pd.DataFrame(node_rows)
    _apply_group_order(df_rec, df_node, custom_grp_order)
    return df_rec, df_node


def plot_step2_group_comparisons(
    recordings: list,
    all_ephys: dict,
    out_dir: Path,
    custom_grp_order: list[str] | None = None,
    fmt: str = "png",
    colors=None,
    n_electrodes: int | None = None,
) -> None:
    """Generate group comparison plots for step 2.

    ``colors`` is a :class:`~meanap.pipeline.palette.ColorScheme` for the age
    and group palettes; omitting it keeps the historical ones. ``n_electrodes``
    (the array's electrode count, when fixed) caps the active-electrode violins.
    """
    df_rec, df_node = ephys_comparison_frames(recordings, all_ephys, custom_grp_order)
    if df_rec.empty:
        return

    # File names follow PlotEphysStats.m: "<n>_<label>_byGroup" and
    # "<n>_<label>_byAge", except node-by-age, which it writes as plain
    # "<n>_<label>". Its by-age panels are titled "Age<DIV>", with no space.

    # 3_RecordingsByGroup
    grp_dir = out_dir / "2B_GroupComparisons" / "3_RecordingsByGroup" / "HalfViolinPlots"
    grp_dir.mkdir(parents=True, exist_ok=True)

    for n, (k, name) in enumerate(EPHYS_REC_METRICS.items(), start=1):
        plot_half_violin_by_x(df_rec, k, name, "group",
                              grp_dir / f"{comparison_figure_stem(n, name, 'byGroup')}.{fmt}",
                              group_order=custom_grp_order,
                              colors=colors,
                              ylim=ephys_bounds(k), max_nodes=n_electrodes)

    # 1_NodeByGroup
    node_grp_dir = out_dir / "2B_GroupComparisons" / "1_NodeByGroup"
    node_grp_dir.mkdir(parents=True, exist_ok=True)

    for n, (k, name) in enumerate(EPHYS_NODE_METRICS.items(), start=1):
        plot_half_violin_by_x(df_node, k, name, "group",
                              node_grp_dir / f"{comparison_figure_stem(n, name, 'byGroup')}.{fmt}",
                              group_order=custom_grp_order, colors=colors,
                              ylim=ephys_bounds(k), max_nodes=n_electrodes)

    # 4_RecordingsByAge
    age_dir = out_dir / "2B_GroupComparisons" / "4_RecordingsByAge" / "HalfViolinPlots"
    age_dir.mkdir(parents=True, exist_ok=True)

    for n, (k, name) in enumerate(EPHYS_REC_METRICS.items(), start=1):
        plot_half_violin_by_x(df_rec, k, name, "DIV",
                              age_dir / f"{comparison_figure_stem(n, name, 'byAge')}.{fmt}",
                              group_order=custom_grp_order,
                              colors=colors,
                              ylim=ephys_bounds(k), max_nodes=n_electrodes, age_title_sep="")

    # 2_NodeByAge
    node_age_dir = out_dir / "2B_GroupComparisons" / "2_NodeByAge"
    node_age_dir.mkdir(parents=True, exist_ok=True)

    for n, (k, name) in enumerate(EPHYS_NODE_METRICS.items(), start=1):
        plot_half_violin_by_x(df_node, k, name, "DIV",
                              node_age_dir / f"{comparison_figure_stem(n, name)}.{fmt}",
                              group_order=custom_grp_order, colors=colors,
                              ylim=ephys_bounds(k), max_nodes=n_electrodes, age_title_sep="")
