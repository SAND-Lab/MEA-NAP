import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from meanap.params import Params
from meanap.pipeline.spike_detection import SpikeDetectionResult, bandpass_filter


def plot_spike_detection_checks(
    dat: np.ndarray,
    result: SpikeDetectionResult,
    params: Params,
    rec_name: str,
    out_dir: Path,
) -> None:
    """Generate diagnostic plots for step 1 (spike detection)."""
    # Use non-interactive backend
    plt.switch_backend("Agg")

    fs = result.fs
    n_samples, n_channels = dat.shape
    duration_s = n_samples / fs
    
    scale_factor = 1.0
    if params.potential_difference_unit == "V":
        scale_factor = 1e6
    elif params.potential_difference_unit == "mV":
        scale_factor = 1e3

    methods = list(next(iter(result.spike_times.values())).keys())
    methods = sorted(methods)
    
    # We assign standard colors for methods
    colors = plt.cm.tab10.colors

    # ── 1. Spike Frequencies ──
    fig, ax = plt.subplots(figsize=(12, 6))
    
    d_samp_f = int(params.d_samp_f)
    n_bins = int(np.ceil(n_samples / d_samp_f))
    
    for i, method in enumerate(methods):
        spk_matrix = np.zeros((n_channels, n_bins))
        for ch_idx in list(result.spike_times.keys()):
            
            # spike_times are in the requested unit, in runner.py default is 's', wait, 
            # runner.py uses SpikeDetectionParams default 's'. So times are in seconds.
            times_s = result.spike_times[ch_idx].get(method, np.array([]))
            frames = np.round(times_s * fs).astype(int)
            frames = frames[frames < n_samples]
            
            spk_vec = np.zeros(n_samples)
            spk_vec[frames] = 1
            
            # Pad to multiple of d_samp_f
            pad_len = (d_samp_f - (n_samples % d_samp_f)) % d_samp_f
            if pad_len > 0:
                spk_vec = np.pad(spk_vec, (0, pad_len), constant_values=np.nan)
            
            spk_matrix[ch_idx, :] = np.nansum(spk_vec.reshape(-1, d_samp_f), axis=1)
            
        # Average across channels
        active_channels = list(result.spike_times.keys())
        if active_channels:
            down_spk_matrix_all = np.mean(spk_matrix[active_channels, :], axis=0)
        else:
            down_spk_matrix_all = np.zeros(n_bins)
        # MATLAB plots the raw counts per bin, not converted to Hz
        rate_hz = down_spk_matrix_all
        
        # MATLAB plots against bin indices, not time!
        time_bins = np.arange(1, n_bins + 1)
        ax.plot(time_bins, rate_hz, lw=2, color=colors[i % len(colors)], label=method.replace("p", "."))

    ax.set_xlim(0, duration_s)
    
    # MATLAB xtick logic: ticks every 60 "units" mapped to 1, 2, 3... minutes
    tick_step = 60
    ticks = np.arange(tick_step, duration_s + tick_step, tick_step)
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(int(i+1)) for i in range(len(ticks))])
    
    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Spiking frequency (Hz)")  # Note: Actually raw spikes/bin due to MATLAB port
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.set_title(rec_name)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    fig.savefig(out_dir / "2_SpikeFrequencies.png", dpi=150)
    plt.close(fig)

    # ── 2. Example Traces ──
    fig, axes = plt.subplots(5, 2, figsize=(14, 8), constrained_layout=True)
    fig.suptitle(rec_name)
    axes = axes.flatten()
    
    window_width_s = 30 / 1000
    window_width_frames = int(round(window_width_s * fs))
    
    active_channels = list(result.spike_times.keys())
    if not active_channels:
        return
        
    last_channel = active_channels[0]
    
    # We plot 9 example traces, leaving the 10th axis empty or turning it off
    for i in range(9):
        ax = axes[i]
        ch = np.random.choice(active_channels)
        last_channel = ch
        
        # We need the filtered trace
        raw_trace = dat[:, ch].astype(float)
        trace = bandpass_filter(raw_trace, fs, params.filter_low_pass, params.filter_high_pass)
        trace = trace * scale_factor
        
        ax.plot(trace, color="black", lw=0.5)
        
        std_trace = np.std(trace)
        
        # Pick a random spike from the first available method to center the window
        times_s = result.spike_times[ch].get(methods[0], np.array([]))
        if len(times_s) > 0:
            st = int(round(np.random.choice(times_s) * fs))
        else:
            st = n_samples // 2
            
        start_f = max(0, st - window_width_frames)
        end_f = min(n_samples, st + window_width_frames)
        
        ax.set_xlim(start_f, end_f)
        ax.set_ylim(-6 * std_trace, 5 * std_trace)
        
        for m_idx, method in enumerate(methods):
            m_times_s = result.spike_times[ch].get(method, np.array([]))
            m_frames = np.round(m_times_s * fs).astype(int)
            # Filter to just the ones in window
            m_frames = m_frames[(m_frames >= start_f) & (m_frames <= end_f)]
            
            y_val = 5 * std_trace - (m_idx + 1) * (0.5 * std_trace)
            ax.scatter(m_frames, np.full_like(m_frames, y_val, dtype=float), 
                       s=15, marker="v", color=colors[m_idx % len(colors)])
                       
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_xticks([])
        ax.set_ylabel("Amplitude ($\\mu$V)")
        ax.set_title(f"Electrode {ch} | {start_f/fs:.3f} - {end_f/fs:.3f} s")
        
    axes[9].axis("off")
    fig.savefig(out_dir / "1_ExampleTraces.png", dpi=150)
    plt.close(fig)

    # ── 3. Waveforms ──
    n_methods = len(methods)
    n_cols = int(np.ceil(n_methods / 2))
    n_rows = 2
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 3, 6), squeeze=False, constrained_layout=True)
    fig.suptitle(f"{rec_name}\nUnique spikes by method from electrode {last_channel}")
    
    # We need the filtered trace std for y limits
    raw_trace = dat[:, last_channel].astype(float)
    trace = bandpass_filter(raw_trace, fs, params.filter_low_pass, params.filter_high_pass)
    trace = trace * scale_factor
    std_trace = np.std(trace)
    
    ymin, ymax = -6 * std_trace, 5 * std_trace
    if ymin == ymax:
        ymin, ymax = -1, 1

    # Waveform length (samples) — determines the time axis. Take it from the
    # first method that has waveforms.
    wave_len = 0
    for method in methods:
        w = result.spike_waveforms.get(last_channel, {}).get(method, np.zeros((0, 0)))
        if w.shape[0] > 0:
            wave_len = w.shape[1]
            break

    # Pick a "nice" scale-bar duration ~ a quarter of the window.
    scale_bar_ms = None
    if wave_len > 0 and fs > 0:
        window_ms = wave_len / fs * 1000.0
        for cand in (2.0, 1.0, 0.5, 0.2, 0.1):
            if cand <= window_ms * 0.6:
                scale_bar_ms = cand
                break

    for i, method in enumerate(methods):
        r = i // n_cols
        c = i % n_cols
        ax = axes[r, c]

        waves = result.spike_waveforms.get(last_channel, {}).get(method, np.zeros((0, 0)))

        if waves.shape[0] > 1000:
            indices = np.linspace(0, waves.shape[0] - 1, 1000).astype(int)
            waves = waves[indices]

        # MATLAB BUG REPLICATION:
        # In MATLAB, 'trace' is scaled by 10^6, and then 'spk_waves_method' is extracted from it.
        # Then, 'spk_waves_method' is MULTIPLIED BY 10^6 AGAIN.
        # We replicate this double-scaling here so the plots look visually identical to the MATLAB reference.
        waves = waves * scale_factor

        if waves.shape[0] > 0:
            ax.plot(waves.T, color=[0.7, 0.7, 0.7], lw=0.1)
            ax.plot(np.mean(waves, axis=0), color="black", lw=1.5)

        if wave_len > 0:
            ax.set_xlim(0, wave_len - 1)  # axis tight, like MATLAB

        # Time scale bar (bottom-left) — MATLAB hides the x-axis entirely, so
        # give the viewer an explicit time reference instead.
        if scale_bar_ms is not None and wave_len > 0:
            bar_samples = scale_bar_ms / 1000.0 * fs
            x0 = wave_len * 0.05
            y0 = ymin + 0.06 * (ymax - ymin)
            ax.plot([x0, x0 + bar_samples], [y0, y0], color="black", lw=2,
                    solid_capstyle="butt", clip_on=False)
            label = (f"{scale_bar_ms:g} ms" if scale_bar_ms >= 1
                     else f"{scale_bar_ms * 1000:g} µs")
            ax.text(x0 + bar_samples / 2, y0 - 0.03 * (ymax - ymin), label,
                    ha="center", va="top", fontsize=8)

        ax.set_title(method.replace("p", "."))
        ax.set_ylim(ymin, ymax)
        ax.set_ylabel("Voltage ($\\mu$V)")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_xticks([])

    # Turn off unused axes
    for i in range(n_methods, n_rows * n_cols):
        r = i // n_cols
        c = i % n_cols
        axes[r, c].axis("off")
        
    fig.savefig(out_dir / "3_Waveforms.png", dpi=150)
    plt.close(fig)
