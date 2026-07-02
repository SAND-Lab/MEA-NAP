import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

from meanap.pipeline.parula import cm_data as parula_data
# Create 85% parula colormap
parula_85 = LinearSegmentedColormap.from_list('parula_85', parula_data[:int(len(parula_data)*0.85)])

def get_coords_from_chs(chs):
    """Returns a list of (x, y) tuples based on MEA-NAP channel numbering (e.g. 11 to 88)."""
    coords = []
    for ch in chs:
        # e.g., ch = 11 -> x_idx = 0, y_idx = 7
        x_idx = ch // 10 - 1
        y_idx = 8 - (ch % 10)
        
        # Rotate 90 degrees anticlockwise as requested
        x_rot = 7 - y_idx
        y_rot = x_idx
        coords.append((x_rot, y_rot))
    return coords

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

def plot_heatmap(metric: np.ndarray, chs: np.ndarray, title: str, clabel: str, out_path: Path, cmap="viridis"):
    # Note: metric length could be 0 if the caller doesn't pad it.
    if len(metric) == 0:
        return
        
    coords = get_coords_from_chs(chs)
    
    fig, ax = plt.subplots(figsize=(6, 5))
    xs = np.array([c[0] for c in coords])
    ys = np.array([c[1] for c in coords])
    
    valid_mask = ~np.isnan(metric)
    
    # Plot NaN circles as light grey
    if not np.all(valid_mask):
        ax.scatter(xs[~valid_mask], ys[~valid_mask], color='lightgray', s=800, marker='o', edgecolors='white', linewidths=1)
        
    # Plot valid circles with colormap
    if np.any(valid_mask):
        valid_vals = metric[valid_mask]
        vmin = np.min(valid_vals)
        vmax = np.percentile(valid_vals, 99)
        if vmin == vmax:
            vmax = vmin + 1e-5
        
        sc = ax.scatter(xs[valid_mask], ys[valid_mask], c=valid_vals, cmap=cmap, vmin=vmin, vmax=vmax, s=800, marker='o', edgecolors='white', linewidths=1)
        cbar = plt.colorbar(sc, ax=ax)
        cbar.set_label(clabel)
    else:
        # Dummy scatter for colorbar if all are NaN
        sc = ax.scatter([], [], c=[], cmap=cmap, vmin=0, vmax=1, s=800)
        cbar = plt.colorbar(sc, ax=ax)
        cbar.set_label(clabel)
        
    ax.set_title(title)
    ax.axis('off')
    ax.set_aspect('equal', 'box')
    
    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

def plot_raster(spike_times_dict: dict, duration_s: float, out_path: Path):
    fig = plt.figure(figsize=(10, 6))
    gs = fig.add_gridspec(4, 1)
    ax_hist = fig.add_subplot(gs[0])
    ax_raster = fig.add_subplot(gs[1:])
    
    n_channels = len(spike_times_dict)
    n_bins = int(np.ceil(duration_s))
    
    # Create the heatmap matrix: (n_channels, n_bins)
    raster_mat = np.zeros((n_channels, n_bins))
    
    all_spikes = []
    for ch, times in spike_times_dict.items():
        if len(times) > 0:
            all_spikes.extend(times)
            # Bin the spikes for this channel
            counts, _ = np.histogram(times, bins=n_bins, range=(0, n_bins))
            raster_mat[ch, :] = counts
            
    # Calculate vmax based on 99th percentile, with minimum of 1
    vmax_val = max(1, np.percentile(raster_mat, 99))
            
    # Plot as a heatmap (imshow places row 0 at the top by default)
    im = ax_raster.imshow(raster_mat, aspect='auto', cmap=parula_85, vmin=0, vmax=vmax_val, extent=[0, n_bins, n_channels, 0])
    ax_raster.set_xlabel("Time (s)")
    ax_raster.set_ylabel("Electrode (1-64)")
    
    # Add colorbar
    cbar = fig.colorbar(im, ax=ax_raster, fraction=0.05, pad=0.02)
    cbar.set_label("Activity")
    
    if len(all_spikes) > 0:
        bins = np.arange(0, duration_s + 1, 1)
        counts, _ = np.histogram(all_spikes, bins=bins)
        rate = counts / n_channels if n_channels > 0 else counts
            
        ax_hist.plot(bins[:-1], rate, color='black', drawstyle='steps-pre')
        
    ax_hist.set_xlim(0, n_bins)
    ax_hist.set_ylabel("Avg FR (Hz)")
    ax_hist.set_xticks([])
    ax_hist.spines['top'].set_visible(False)
    ax_hist.spines['right'].set_visible(False)
    ax_hist.spines['bottom'].set_visible(False)
    
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
    output_root: Path
):
    out_dir = output_root / rec.group / rec.filename
    out_dir.mkdir(parents=True, exist_ok=True)
    
    plot_firing_rate_distribution(ephys, out_dir / "1_FiringRateByElectrode.png")
    
    if "FR" in ephys:
        plot_heatmap(ephys["FR"], chs, "Firing Rate", "Mean FR (Hz)", out_dir / "2_Heatmap.png")
        
    plot_raster(spike_times_dict, duration_s, out_dir / "3_Raster.png")
    
    if "channelBurstRate" in ephys:
        plot_heatmap(ephys["channelBurstRate"], chs, "Burst Rate", "Burst Rate (bursts/min)", out_dir / "3_BurstRate_heatmap.png", cmap="plasma")
    if "channelBurstDur" in ephys:
        plot_heatmap(ephys["channelBurstDur"], chs, "Burst Duration", "Duration (ms)", out_dir / "4_BurstDur_heatmap.png", cmap="plasma")
    if "channelFracSpikesInBursts" in ephys:
        plot_heatmap(ephys["channelFracSpikesInBursts"], chs, "Fraction Spikes in Bursts", "Fraction", out_dir / "5_FractSpikesInBursts_heatmap.png", cmap="plasma")
    if "channelISIwithinBurst" in ephys:
        plot_heatmap(ephys["channelISIwithinBurst"], chs, "ISI Within Burst", "ISI (ms)", out_dir / "6_ISIwithinBurst_heatmap.png", cmap="plasma")
    if "channeISIoutsideBurst" in ephys:
        plot_heatmap(ephys["channeISIoutsideBurst"], chs, "ISI Outside Burst", "ISI (ms)", out_dir / "7_ISIoutsideBurst_heatmap.png", cmap="plasma")
        
    plot_burst_detection_info(spike_times_dict, ephys, duration_s, fs, out_dir / "8_BurstDetectionInfo.png")
