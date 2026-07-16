import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.parula import cm_data as parula_data
from meanap.pipeline.plotting_step4 import plot_half_violin_by_x
# Create 85% parula colormap
parula_85 = LinearSegmentedColormap.from_list('parula_85', parula_data[:int(len(parula_data)*0.85)])

def plot_firing_rate_distribution(ephys: dict, out_path: Path):
    fr = ephys.get("FR", [])
    if len(fr) == 0:
        return
        
    fig, ax = plt.subplots(figsize=(4, 6))
    sns.violinplot(y=fr, ax=ax, inner=None, color="lightgray")
    sns.stripplot(y=fr, ax=ax, color="black", size=4, jitter=True)
    
    ax.set_ylabel("Mean firing rate per electrode (Hz)")
    ax.set_title("Firing Rate by Electrode")
    
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

def _draw_heatmap_panel(ax, xs, ys, metric, valid_mask, vmin, vmax, cmap, clabel, panel_title):
    """Draw one electrode heatmap panel (colored circles at electrode coords)."""
    if not np.all(valid_mask):
        ax.scatter(xs[~valid_mask], ys[~valid_mask], color="lightgray", s=800,
                   marker="o", edgecolors="white", linewidths=1)
    if np.any(valid_mask):
        sc = ax.scatter(xs[valid_mask], ys[valid_mask], c=metric[valid_mask], cmap=cmap,
                        vmin=vmin, vmax=vmax, s=800, marker="o", edgecolors="white", linewidths=1)
    else:
        sc = ax.scatter([], [], c=[], cmap=cmap, vmin=vmin, vmax=vmax, s=800)
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label(clabel)
    ax.set_title(panel_title)
    ax.axis("off")
    ax.set_aspect("equal", "box")


def plot_heatmap(
    metric: np.ndarray, chs: np.ndarray, title: str, clabel: str, out_path: Path,
    cmap="viridis", channel_layout: str = "Axion64",
    batch_max: float | None = None,
):
    """Electrode heatmap, port of ``electrodeHeatMaps.m`` / ``plotNodeHeatmap.m``.

    When ``batch_max`` is given, produce a two-panel figure (like MATLAB's
    ``tiledlayout(1,2)``): left scaled to this recording (color axis = 99th
    percentile of its own values), right scaled to the entire dataset (color
    axis = ``batch_max``, the batch-wide max of this metric = MATLAB's
    ``maxValStruct.(metric)``), so levels are comparable across recordings.
    When ``batch_max`` is None, fall back to the original single panel.
    """
    # Note: metric length could be 0 if the caller doesn't pad it.
    if len(metric) == 0:
        return

    layout_channels, layout_coords = get_coords_from_layout(channel_layout)
    coord_by_channel = dict(zip(layout_channels.tolist(), map(tuple, layout_coords)))
    keep = np.array([int(c) in coord_by_channel for c in chs])
    if not np.any(keep):
        return
    coords = np.array([coord_by_channel[int(c)] for c in chs[keep]])
    metric = metric[keep]
    xs = coords[:, 0]
    ys = coords[:, 1]
    valid_mask = ~np.isnan(metric)

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
        _draw_heatmap_panel(ax, xs, ys, metric, valid_mask, vmin, recording_vmax, cmap, clabel, title)
        plt.tight_layout()
        fig.savefig(out_path, dpi=300)
        plt.close(fig)
        return

    batch_vmax = float(batch_max)
    if batch_vmax <= vmin or np.isnan(batch_vmax):
        batch_vmax = vmin + 1e-5

    fig, (ax_rec, ax_batch) = plt.subplots(1, 2, figsize=(12, 5))
    _draw_heatmap_panel(ax_rec, xs, ys, metric, valid_mask, vmin, recording_vmax, cmap,
                        clabel, f"{title}\nscaled to recording")
    _draw_heatmap_panel(ax_batch, xs, ys, metric, valid_mask, vmin, batch_vmax, cmap,
                        clabel, f"{title}\nscaled to entire dataset")
    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

def plot_raster(
    spike_times_dict: dict,
    duration_s: float,
    out_path: Path,
    spike_freq_max: float | None = None,
    raster_upper_percentile: float = 99.0,
):
    """Two-panel raster, port of ``rasterPlot.m``.

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

    for ax, vmax, title in (
        (ax_rec, recording_vmax, "raster scaled to recording"),
        (ax_batch, batch_vmax, "raster scaled to entire data batch"),
    ):
        im = ax.imshow(
            raster_mat, aspect="auto", cmap=parula_85, vmin=0, vmax=vmax,
            extent=[0, duration_s, n_channels, 0],
        )
        ax.set_ylabel("Electrode")
        ax.set_title(title, fontsize=10)
        cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
        cbar.set_label("Firing Rate (Hz)")
    ax_batch.set_xlabel("Time (s)")

    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
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
    ax_raster_full.set_title("Raster (All spikes)")
    ax_raster_full.set_ylabel("Electrode")
    
    ax_raster_burst.imshow(raster_burst, aspect='auto', cmap=parula_85, extent=[0, duration_s, n_channels, 0])
    ax_raster_burst.set_xlim(0, duration_s)
    ax_raster_burst.set_title("Raster (Only network bursts)")
    ax_raster_burst.set_ylabel("Electrode")
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
                ax_isi.set_title("ISI Distribution")
    
    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

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
):
    out_dir = output_root / rec.group / rec.filename
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_firing_rate_distribution(ephys, out_dir / "1_FiringRateByElectrode.png")

    channel_layout = getattr(params, "channel_layout", "Axion64")
    bmax = batch_max or {}

    if "FR" in ephys:
        plot_heatmap(ephys["FR"], chs, "Firing Rate", "Mean FR (Hz)", out_dir / "2_Heatmap.png", channel_layout=channel_layout, batch_max=bmax.get("FR"))

    plot_raster(
        spike_times_dict, duration_s, out_dir / "3_Raster.png",
        spike_freq_max=spike_freq_max,
        raster_upper_percentile=getattr(params, "raster_plot_upper_percentile", 99.0),
    )

    if "channelBurstRate" in ephys:
        plot_heatmap(ephys["channelBurstRate"], chs, "Burst Rate", "Burst Rate (bursts/min)", out_dir / "3_BurstRate_heatmap.png", cmap="plasma", channel_layout=channel_layout, batch_max=bmax.get("channelBurstRate"))
    if "channelBurstDur" in ephys:
        plot_heatmap(ephys["channelBurstDur"], chs, "Burst Duration", "Duration (ms)", out_dir / "4_BurstDur_heatmap.png", cmap="plasma", channel_layout=channel_layout, batch_max=bmax.get("channelBurstDur"))
    if "channelFracSpikesInBursts" in ephys:
        plot_heatmap(ephys["channelFracSpikesInBursts"], chs, "Fraction Spikes in Bursts", "Fraction", out_dir / "5_FractSpikesInBursts_heatmap.png", cmap="plasma", channel_layout=channel_layout, batch_max=bmax.get("channelFracSpikesInBursts"))
    if "channelISIwithinBurst" in ephys:
        plot_heatmap(ephys["channelISIwithinBurst"], chs, "ISI Within Burst", "ISI (ms)", out_dir / "6_ISIwithinBurst_heatmap.png", cmap="plasma", channel_layout=channel_layout, batch_max=bmax.get("channelISIwithinBurst"))
    if "channeISIoutsideBurst" in ephys:
        plot_heatmap(ephys["channeISIoutsideBurst"], chs, "ISI Outside Burst", "ISI (ms)", out_dir / "7_ISIoutsideBurst_heatmap.png", cmap="plasma", channel_layout=channel_layout, batch_max=bmax.get("channeISIoutsideBurst"))
        
    plot_burst_detection_info(spike_times_dict, ephys, duration_s, fs, out_dir / "8_BurstDetectionInfo.png")

import pandas as pd

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
    "channelAveBurstRate": "Single-electrode burst rate (per min)",
    "channelAveBurstDur": "Single-electrode avg burst dur (ms)",
    "channelAveISIwithinBurst": "Single-electrode avg ISI within burst (ms)",
    "channelAveISIoutsideBurst": "Single-electrode avg ISI outside burst (ms)",
    "channelAveFracSpikesInBursts": "Mean fraction of spikes in bursts per electrode",
}

EPHYS_NODE_METRICS = {
    "FR": "mean_firing_rate_node",
    "FRactive": "mean_firing_rate_active_node",
    "channelBurstRate": "Unit burst rate (per minute)",
    "channelWithinBurstFr": "Unit within-burst firing rate (Hz)",
    "channelBurstDur": "Unit burst duration (ms)",
    "channelISIwithinBurst": "Unit ISI within burst (ms)",
    "channeISIoutsideBurst": "Unit ISI outside burst (ms)",
    "channelFracSpikesInBursts": "Unit fraction of spikes in bursts",
}

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
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

def plot_step2_group_comparisons(
    recordings: list,
    all_ephys: dict,
    out_dir: Path,
    custom_grp_order: list[str] | None = None
) -> None:
    """Generate group comparison plots for step 2."""
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
                
    if not rec_rows:
        return
        
    df_rec = pd.DataFrame(rec_rows)
    df_node = pd.DataFrame(node_rows)
    
    if custom_grp_order:
        df_rec["Grp"] = pd.Categorical(df_rec["Grp"], categories=custom_grp_order, ordered=True)
        df_node["Grp"] = pd.Categorical(df_node["Grp"], categories=custom_grp_order, ordered=True)
    
    # 3_RecordingsByGroup
    grp_dir = out_dir / "2B_GroupComparisons" / "3_RecordingsByGroup" / "HalfViolinPlots"
    grp_dir.mkdir(parents=True, exist_ok=True)
    
    for k, name in EPHYS_REC_METRICS.items():
        plot_half_violin_by_x(df_rec, k, name, "group",
                              grp_dir / f"{k}_byGroup.png", group_order=custom_grp_order)

    # 1_NodeByGroup
    node_grp_dir = out_dir / "2B_GroupComparisons" / "1_NodeByGroup"
    node_grp_dir.mkdir(parents=True, exist_ok=True)

    for k, name in EPHYS_NODE_METRICS.items():
        plot_half_violin_by_x(df_node, k, name, "group",
                              node_grp_dir / f"{k}_byGroup_node.png", group_order=custom_grp_order)

    # 4_RecordingsByAge
    age_dir = out_dir / "2B_GroupComparisons" / "4_RecordingsByAge" / "HalfViolinPlots"
    age_dir.mkdir(parents=True, exist_ok=True)

    for k, name in EPHYS_REC_METRICS.items():
        plot_half_violin_by_x(df_rec, k, name, "DIV",
                              age_dir / f"{k}_byDIV.png", group_order=custom_grp_order)

    # 2_NodeByAge
    node_age_dir = out_dir / "2B_GroupComparisons" / "2_NodeByAge"
    node_age_dir.mkdir(parents=True, exist_ok=True)

    for k, name in EPHYS_NODE_METRICS.items():
        plot_half_violin_by_x(df_node, k, name, "DIV",
                              node_age_dir / f"{k}_byDIV_node.png", group_order=custom_grp_order)
