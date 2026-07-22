"""Matplotlib plotting layer for the MEA-Stim subsystem.

Port of the figure-producing functions in ``Functions/stimAnalysis/`` on
``origin/main``:

- ``plotStimTimes.m``              -> :func:`plot_stim_times`  (1_StimsDetected)
- ``plotStimHeatmap.m``            -> :func:`plot_stim_heatmap` (2_StimsHeatmap)
- ``plotIdvStimDataAndTrace.m``    -> :func:`plot_idv_stim_data_and_trace`
- ``plotStimDetectionChecks.m``    -> :func:`plot_stim_detection_checks`
- ``valuesToColormap.m``           -> :func:`values_to_colormap`
- ``plotStimHeatmapWmetric.m``     -> :func:`plot_stim_heatmap_w_metric`
- ``plotPrePostStimFR.m``          -> :func:`plot_pre_post_stim_fr` (9_...)
- ``plotMetricAlignedToStim.m``    -> :func:`plot_metric_aligned_to_stim` (10_...)
- ``plotStimShuffleResults.m``     -> :func:`plot_stim_shuffle_results` (12_...)
- the individual-electrode PSTH+raster figure built inline in STEP 6 of
  ``stimActivityAnalysis.m`` -> :func:`plot_individual_psth_and_raster`
  (+ :func:`plot_individual_psth_and_raster_for_pattern` mirroring the
  top-AUC channel selection loop).

These reproduce the MATLAB figures in *content* and layout (titles, axis
labels, colorbars, artifact-window shading, colours). They are not
pixel-identical — matplotlib defaults differ from MATLAB — but aim to be at
least as clear. Every function writes a PNG (default) whose basename matches
the MATLAB output artifact exactly.

Nothing here mutates the numeric modules; all display quantities are recomputed
from the ported detection/psth results passed in.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")  # headless: never needs a display
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, ListedColormap

from ..pipeline.parula import parula_map
from .detection import StimChannelInfo, _matlab_mode
from .psth import (
    calculate_psth_metrics,
    get_fr_aligned_to_stim,
    get_spike_latency_rel_stim,
    get_stim_artifact_duration,
)

_WHITE = (1.0, 1.0, 1.0)
_NAN_COLOR = (0.9, 0.9, 0.9)


# ── shared save helper ────────────────────────────────────────────────────────

def _save(fig, out_path: str | Path, dpi: int = 150) -> Path:
    """Save ``fig`` to ``out_path`` (``.png`` appended if no suffix) and close it."""
    out_path = Path(out_path)
    if out_path.suffix == "":
        out_path = out_path.with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def _method_spikes(spike_times: dict, channel_idx: int, method: str) -> np.ndarray:
    """Spike-time vector (s) for a channel/method from the ``{ch:{method:...}}`` dict."""
    if channel_idx not in spike_times or method not in spike_times[channel_idx]:
        return np.array([])
    return np.asarray(spike_times[channel_idx][method], dtype=float).ravel()


# ── valuesToColormap.m ────────────────────────────────────────────────────────

def values_to_colormap(value: float, cmap, vmin: float, vmax: float):
    """Map a scalar to an RGBA colour (port of ``valuesToColormap.m``).

    Normalises to ``[vmin, vmax]`` (clipped), quantises to the colormap and
    returns the RGBA tuple. NaN -> light grey (MATLAB would error; here NaN
    channels are simply drawn neutral, matching the reference figures where
    missing metrics read as background).
    """
    cmap = plt.get_cmap(cmap) if isinstance(cmap, str) else cmap
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return _NAN_COLOR
    if vmax == vmin:
        norm = 0.0
    else:
        norm = (value - vmin) / (vmax - vmin)
    norm = float(min(1.0, max(0.0, norm)))
    return cmap(norm)


# ── plotStimHeatmap.m  (2_StimsHeatmap) ───────────────────────────────────────

def plot_stim_heatmap(stim_info: list[StimChannelInfo], out_path: str | Path) -> Path:
    """Electrode layout: stimulated electrodes black (red edge, pattern label),
    the rest white (port of ``plotStimHeatmap.m``)."""
    fig, ax = plt.subplots(figsize=(6, 6))
    for info in stim_info:
        xc, yc = float(info.coords[0]), float(info.coords[1])
        if info.elec_stim_times.size == 0:
            ax.add_patch(Circle((xc, yc), 0.5, facecolor="white",
                                edgecolor="black", linewidth=1.0, zorder=2))
        else:
            ax.add_patch(Circle((xc, yc), 0.5, facecolor="black",
                                edgecolor="red", linewidth=1.5, zorder=3))
            ax.text(xc, yc, str(info.pattern), color="white", fontsize=12,
                    ha="center", va="center", zorder=4)
    _finalize_layout_axes(ax, stim_info)
    return _save(fig, out_path)


def _finalize_layout_axes(ax, stim_info: list[StimChannelInfo]) -> None:
    """Common electrode-layout axis styling (equal aspect, no ticks, padding)."""
    xs = [float(i.coords[0]) for i in stim_info]
    ys = [float(i.coords[1]) for i in stim_info]
    ax.set_xlim(min(xs) - 1, max(xs) + 1)
    ax.set_ylim(min(ys) - 1, max(ys) + 1)
    ax.set_aspect("equal")
    ax.axis("off")


# ── plotStimHeatmapWmetric.m  (stimPattern_k_heatmap, spikeLatency_k_heatmap) ──

def plot_stim_heatmap_w_metric(
    node_metric: np.ndarray,
    vrange: tuple[float, float],
    cmap,
    cmap_label: str,
    stim_info: list[StimChannelInfo],
    pattern_id,
    out_path: str | Path,
    title: str | None = None,
    categorical_legend: list[tuple] | None = None,
) -> Path:
    """Electrode circles coloured by ``node_metric`` (port of ``plotStimHeatmapWmetric.m``).

    The stimulating electrode(s) of ``pattern_id`` are drawn white. A colorbar
    labelled ``cmap_label`` is added over ``vrange``. When ``categorical_legend``
    (a list of ``(rgb, label)``) is given, the colorbar is replaced by a
    horizontal legend beneath the axes — used for the categorical significance
    heatmap.
    """
    cmap = plt.get_cmap(cmap) if isinstance(cmap, str) else cmap
    node_metric = np.asarray(node_metric, dtype=float).ravel()
    pattern_ids = pattern_id if np.iterable(pattern_id) else [pattern_id]

    fig, ax = plt.subplots(figsize=(7, 6))
    for idx, info in enumerate(stim_info):
        xc, yc = float(info.coords[0]), float(info.coords[1])
        is_stim = info.elec_stim_times.size > 0 and info.pattern in pattern_ids
        color = _WHITE if is_stim else values_to_colormap(
            node_metric[idx], cmap, vrange[0], vrange[1])
        ax.add_patch(Circle((xc, yc), 0.5, facecolor=color,
                            edgecolor="black", linewidth=1.0, zorder=2))
    _finalize_layout_axes(ax, stim_info)

    if categorical_legend is None:
        sm = ScalarMappable(norm=Normalize(vrange[0], vrange[1]), cmap=cmap)
        cb = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label(cmap_label, fontsize=12)
        # Note grey = missing metric. MATLAB's valuesToColormap maps NaN to the
        # darkest colour (its two-arg min/max drop NaN → norm 1), conflating
        # "no data" with the maximum; this port keeps it visually distinct.
        n_nan = int(np.sum([np.isnan(node_metric[i]) and info.pattern not in pattern_ids
                            for i, info in enumerate(stim_info)]))
        if n_nan:
            ax.plot([], [], marker="o", linestyle="", markersize=10,
                    markerfacecolor=_NAN_COLOR, markeredgecolor="black",
                    label=f"no data ({n_nan})")
            ax.legend(loc="lower right", frameon=False, fontsize=9,
                      handletextpad=0.3, borderpad=0.2)
    else:
        handles = [plt.Line2D([0], [0], marker="o", linestyle="", markersize=11,
                              markerfacecolor=c, markeredgecolor="black", label=lbl)
                   for c, lbl in categorical_legend]
        ax.legend(handles=handles, loc="upper center",
                  bbox_to_anchor=(0.5, -0.02), ncol=len(handles),
                  frameon=False, fontsize=11)
    if title:
        ax.set_title(title, fontweight="bold")
    return _save(fig, out_path)


# ── plotStimTimes.m  (1_StimsDetected) ────────────────────────────────────────

def plot_stim_times(
    raw_data: np.ndarray,
    stim_info: list[StimChannelInfo],
    params: dict,
    out_path: str | Path,
) -> Path:
    """Stacked per-electrode stim raster (port of ``plotStimTimes.m``).

    Each electrode's detected pulses are drawn as a 0/1 step trace offset
    vertically, ordered by electrode ID (top = smallest). Electrode IDs label
    the left, channel indices the right.
    """
    fs = float(params["fs"])
    stim_dur = float(params["stimDurationForPlotting"])
    n_time = raw_data.shape[0]
    dur_s = n_time / fs
    resample_n = round(dur_s * 1000.0)  # 1000 Hz
    resample_t = np.linspace(0, dur_s, resample_n)

    electrodes = np.array([info.channel_name for info in stim_info])
    sorted_elecs = np.sort(electrodes)
    n_ch = len(stim_info)

    fig, ax = plt.subplots(figsize=(6, 15))
    channels = n_ch
    for curr_elec in sorted_elecs:
        chan = int(np.flatnonzero(electrodes == curr_elec)[0])
        stim_vec = np.zeros(resample_n)
        for st in stim_info[chan].elec_stim_times:
            loc = (resample_t >= st) & (resample_t <= st + stim_dur)
            stim_vec[loc] = 1.0
        vert = channels * 1.2
        ax.plot(resample_t, stim_vec + vert, linewidth=0.8)
        ax.text(-1, vert + 0.5, str(int(curr_elec)), ha="right", va="center", fontsize=7)
        ax.text(dur_s + 1, vert + 0.5, str(chan + 1), ha="left", va="center", fontsize=7)
        channels -= 1

    ax.set_yticks([])
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.set_xlabel("Time (s)")
    ax.tick_params(direction="out")
    y_mid = n_ch * 1.2 / 2
    ax.text(-dur_s * 0.06, y_mid, "Electrode ID", rotation=90, va="center",
            ha="center", fontsize=10)
    ax.text(dur_s * 1.06, y_mid, "Channel Index", rotation=270, va="center",
            ha="center", fontsize=10)
    return _save(fig, out_path)


# ── plotIdvStimDataAndTrace.m  (3_*Electrode_<id>) ────────────────────────────

def plot_idv_stim_data_and_trace(
    raw_data: np.ndarray,
    channel_idx: int,
    stim_info: list[StimChannelInfo],
    params: dict,
    out_path: str | Path,
) -> Path:
    """Raw trace (top) + detected stim pulses (bottom) for one channel
    (port of ``plotIdvStimDataAndTrace.m``)."""
    fs = float(params["fs"])
    stim_dur = float(params["stimDurationForPlotting"])
    n_time = raw_data.shape[0]
    dur_s = n_time / fs
    resample_n = round(dur_s * 1000.0)
    resample_t = np.linspace(0, dur_s, resample_n)
    rec_t = np.linspace(0, dur_s, n_time)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    if params.get("stimDetectionMethod") == "absPosThreshold":
        ax1.axhline(float(params["stimDetectionVal"]), linestyle="--", color="k")
    ax1.plot(rec_t, raw_data[:, channel_idx], linewidth=0.5)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Filtered signal")
    ax1.set_title(f"Electrode {int(stim_info[channel_idx].channel_name)} "
                  f"(Channel {channel_idx + 1})")

    stim_vec = np.zeros(resample_n)
    for st in stim_info[channel_idx].elec_stim_times:
        stim_vec[(resample_t >= st) & (resample_t <= st + stim_dur)] = 1.0
    ax2.plot(resample_t, stim_vec, linewidth=0.8)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("Stim Pulses Detected")
    ax2.set_xlabel("Time (s)")
    ax2.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig, out_path)


# ── plotStimDetectionChecks.m ─────────────────────────────────────────────────

def plot_stim_detection_checks(
    raw_data: np.ndarray,
    stim_info: list[StimChannelInfo],
    params: dict,
    out_dir: str | Path,
    num_no_stim_traces: int = 5,
    rng: np.random.Generator | None = None,
) -> list[Path]:
    """Write the detection-check figure set (port of ``plotStimDetectionChecks.m``).

    Produces ``1_StimsDetected``, ``2_StimsHeatmap``, five random
    ``3_NoStimsElectrode_<id>`` (electrode 15, the reference, excluded) and one
    ``3_StimsElectrode_<id>`` per stimulated channel. ``rng`` seeds the random
    non-stim electrode picks for reproducibility.
    """
    out_dir = Path(out_dir)
    if rng is None:
        rng = np.random.default_rng()
    written: list[Path] = []

    written.append(plot_stim_times(raw_data, stim_info, params, out_dir / "1_StimsDetected"))
    written.append(plot_stim_heatmap(stim_info, out_dir / "2_StimsHeatmap"))

    channel_names = np.array([info.channel_name for info in stim_info])
    stim_channels = [i for i, info in enumerate(stim_info) if info.elec_stim_times.size > 0]
    # electrode index 15 (1-based) is the reference electrode, excluded from picks
    non_stim_channels = [i for i, info in enumerate(stim_info)
                         if info.elec_stim_times.size == 0 and i != 14]

    picks = list(non_stim_channels)
    for _ in range(min(num_no_stim_traces, len(picks))):
        j = int(rng.integers(len(picks)))
        ch = picks.pop(j)
        name = int(channel_names[ch])
        written.append(plot_idv_stim_data_and_trace(
            raw_data, ch, stim_info, params, out_dir / f"3_NoStimsElectrode_{name}"))

    for ch in stim_channels:
        name = int(channel_names[ch])
        written.append(plot_idv_stim_data_and_trace(
            raw_data, ch, stim_info, params, out_dir / f"3_StimsElectrode_{name}"))
    return written


# ── plotPrePostStimFR.m  (9_FR_before_after_stimulation) ──────────────────────

def plot_pre_post_stim_fr(
    spike_times: dict,
    stim_info: list[StimChannelInfo],
    all_stim_times: np.ndarray,
    params: dict,
    out_path: str | Path,
    info: dict,
) -> Path:
    """Pre- vs post-stim firing-rate scatter with unity line (port of
    ``plotPrePostStimFR.m``).

    Post-stim window starts after the blanked artifact; the pre-stim window is
    matched to the same effective duration.
    """
    method = params["SpikesMethod"]
    all_stim_times = np.asarray(all_stim_times, dtype=float).ravel()
    n_ch = len(stim_info)

    artifact_dur = get_stim_artifact_duration(params)
    post_win = (artifact_dur, float(params["stimAnalysisWindow"][1]))
    eff_dur = post_win[1] - post_win[0]
    if eff_dur <= 0:
        raise ValueError("artifact window >= post-stim analysis window; nothing to plot")
    pre_win = (-eff_dur, 0.0)

    pre_fr = np.full(n_ch, np.nan)
    post_fr = np.full(n_ch, np.nan)
    for c in range(n_ch):
        sp = _method_spikes(spike_times, c, method)
        n_pre = np.empty(all_stim_times.size)
        n_post = np.empty(all_stim_times.size)
        for k, st in enumerate(all_stim_times):
            n_pre[k] = np.sum((sp >= st + pre_win[0]) & (sp <= st + pre_win[1]))
            n_post[k] = np.sum((sp >= st + post_win[0]) & (sp <= st + post_win[1]))
        pre_fr[c] = n_pre.mean() / (pre_win[1] - pre_win[0]) if all_stim_times.size else np.nan
        post_fr[c] = n_post.mean() / (post_win[1] - post_win[0]) if all_stim_times.size else np.nan

    both = np.concatenate([pre_fr, post_fr])
    lo, hi = np.nanmin(both), np.nanmax(both)
    unity = np.linspace(lo, hi, 100)

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.scatter(pre_fr, post_fr, facecolors="none", edgecolors="C0")
    ax.plot(unity, unity, linestyle="--", color="C1")
    ax.set_xlabel("Pre-stim firing rate (spikes/s)")
    ax.set_ylabel("Post-stim firing rate (spikes/s)")
    ax.tick_params(direction="out")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(_fn(info), fontweight="bold")
    return _save(fig, out_path)


def _fn(info: dict) -> str:
    """Recording name from an info dict (``FN``/``FileName``)."""
    fn = info.get("FN", info.get("FileName", ""))
    if isinstance(fn, (list, tuple, np.ndarray)) and len(fn):
        return str(fn[0])
    return str(fn)


# ── plotMetricAlignedToStim.m  (10_stimulation_raster_and_psth) ───────────────

def plot_metric_aligned_to_stim(
    fr_aligned_to_stim: np.ndarray,
    raster_bins: np.ndarray,
    info: dict,
    params: dict,
    ylabel_txt: str,
    out_path: str | Path,
) -> Path:
    """Two-tile mean-trace + channel x time heatmap aligned to stim
    (port of ``plotMetricAlignedToStim.m``).

    ``params`` supplies ``blankDurMode`` (s) and ``postStimWindowDur`` (ms) for
    the grey artifact-window shading. ``fr_aligned_to_stim`` is
    ``[n_ch, n_stim, n_bins]``.
    """
    n_ch = fr_aligned_to_stim.shape[0]
    bins_ms = np.asarray(raster_bins, dtype=float) * 1000.0
    centers_ms = bins_ms[1:]  # MATLAB plots against rasterBins(2:end)

    mean_fr = np.nanmean(fr_aligned_to_stim, axis=(0, 1))          # (n_bins,)
    per_channel = np.nanmean(fr_aligned_to_stim, axis=1)           # (n_ch, n_bins)

    blank_ms = float(params.get("blankDurMode") or 0.0) * 1000.0
    artifact_end_ms = blank_ms + float(params.get("postStimWindowDur") or 0.0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 5),
                                   gridspec_kw={"height_ratios": [1, 1]})
    ax1.plot(centers_ms, mean_fr, color="C0")
    ax1.fill([0, artifact_end_ms, artifact_end_ms, 0],
             [0, 0, np.nanmax(mean_fr), np.nanmax(mean_fr)],
             color=(0.5, 0.5, 0.5), alpha=0.3, linewidth=0)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.tick_params(direction="out")
    ax1.set_ylabel(ylabel_txt)
    ax1.set_xlim(bins_ms[0], bins_ms[-1])
    ax1.set_title(_fn(info), fontweight="bold")

    # pcolormesh over true bin edges keeps each column in its time interval
    im = ax2.pcolormesh(bins_ms, np.arange(0.5, n_ch + 1), per_channel,
                        cmap=parula_map, shading="flat")
    ax2.set_xlim(bins_ms[0], bins_ms[-1])
    ax2.set_ylim(n_ch + 0.5, 0.5)  # channel 1 at top
    ax2.set_ylabel("Channel")
    ax2.set_xlabel("Time from stimulation (ms)")
    ax2.tick_params(direction="out")
    ax2.spines[["top", "right"]].set_visible(False)
    cb = fig.colorbar(im, ax=ax2, location="right", fraction=0.046, pad=0.04)
    cb.set_label("Firing rate (spikes/s)", fontsize=12)
    fig.tight_layout()
    return _save(fig, out_path)


# ── plotStimShuffleResults.m  (12_...) ────────────────────────────────────────

def plot_stim_shuffle_results(
    shuffle_results,
    stim_info: list[StimChannelInfo],
    info: dict,
    params: dict,
    out_dir: str | Path,
    pattern_idx=None,
) -> list[Path]:
    """Shuffle-test figures (port of ``plotStimShuffleResults.m``).

    Writes ``12_shuffle_test_null_dist[_pattern_k]`` (sorted null-distribution
    heatmap + observed-vs-null errorbar) and, per pattern,
    ``12_shuffle_test_sig_heatmap[_pattern_k]`` (electrode layout coloured by
    significance). ``shuffle_results`` is a :class:`~meanap.stim.shuffle.ShuffleResults`.
    """
    out_dir = Path(out_dir)
    if pattern_idx is None:
        name_suffix, title_suffix = "_allStim", "all stim"
    else:
        name_suffix, title_suffix = f"_pattern_{pattern_idx:.0f}", f"pattern {pattern_idx:.0f}"

    obs = np.asarray(shuffle_results.trial_prop_obs, dtype=float).ravel()
    null = np.asarray(shuffle_results.trial_prop_null, dtype=float)
    pctile_lo = np.asarray(shuffle_results.pctile_lo, dtype=float).ravel()
    pctile_hi = np.asarray(shuffle_results.pctile_hi, dtype=float).ravel()
    is_sig = np.asarray(shuffle_results.is_significant, dtype=bool).ravel()
    n_ch = obs.size
    n_shuffles = shuffle_results.n_shuffles
    x = np.arange(1, n_ch + 1)

    written: list[Path] = []

    # Figure 1: null-dist heatmap (sorted) + observed vs null
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5))
    null_sorted = np.sort(null, axis=1)
    im = ax1.imshow(null_sorted, aspect="auto", cmap=parula_map, origin="upper",
                    extent=[1, n_shuffles, n_ch + 0.5, 0.5])
    fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.02)
    ax1.set_ylabel("Channel Index")
    ax1.set_xlabel("Shuffle (sorted)")
    ax1.set_title(f"Null trial proportion distribution – {title_suffix}  |  {_fn(info)}")
    ax1.tick_params(direction="out")

    null_median = np.median(null, axis=1)
    ax2.errorbar(x, null_median, yerr=[null_median - pctile_lo, pctile_hi - null_median],
                 fmt=".", color=(0.6, 0.6, 0.6), linewidth=1,
                 label=r"Null median $\pm$ CI")
    ax2.scatter(x[~is_sig], obs[~is_sig], s=25, color=(0.3, 0.3, 0.7),
                label="Not significant")
    ax2.scatter(x[is_sig], obs[is_sig], s=40, color=(0.9, 0.2, 0.2),
                label="Significant")
    ax2.set_xlabel("Channel Index")
    ax2.set_ylabel("Proportion of trials (post > pre)")
    ax2.legend(loc="best")
    ax2.set_title(f"Observed vs null – {title_suffix}")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.tick_params(direction="out")
    fig.tight_layout()
    written.append(_save(fig, out_dir / f"12_shuffle_test_null_dist{name_suffix}"))

    # Figure 2: categorical significance heatmap (only per-pattern)
    if pattern_idx is not None:
        sig_red = (0.9, 0.2, 0.2)
        not_sig_grey = (0.85, 0.85, 0.85)
        node_colors = [sig_red if s else not_sig_grey for s in is_sig]
        legend = [(sig_red, "Significant"),
                  (not_sig_grey, "Not significant"),
                  (_WHITE, "Stimulated electrode")]
        cmap2 = ListedColormap([not_sig_grey, sig_red])
        p = plot_stim_heatmap_w_metric(
            is_sig.astype(float), (0.0, 1.0), cmap2, "Significant",
            stim_info, pattern_idx, out_dir / f"12_shuffle_test_sig_heatmap{name_suffix}",
            title=f"Significant electrodes – {title_suffix}",
            categorical_legend=legend,
        )
        written.append(p)
    return written


# ── individual-electrode PSTH + raster (STEP 6 of stimActivityAnalysis.m) ──────

def _individual_electrode_display_data(
    spike_times_s: np.ndarray,
    stim_times: np.ndarray,
    window: tuple[float, float],
    artifact_duration_s: float,
) -> dict | None:
    """Recompute the per-channel quantities STEP 5 stores in ``temp_data``.

    Mirrors ``stimActivityAnalysis.m`` STEP 5.1b/e/f/g for one electrode using
    the gaussian PSTH path. Returns ``None`` for channels with no spikes in the
    analysis window (the MATLAB ``continue``).
    """
    bin_w = 0.001
    gauss_ms = 1.0
    num_baseline = 30
    baseline_dur = window[1] - 0.0

    resp_data, resp = calculate_psth_metrics(
        spike_times_s, stim_times, window, bin_w,
        smoothing_method="gaussian", gaussian_width_ms=gauss_ms, auc_start_s=0.0)
    if resp_data.psth_samples.size == 0:
        return None

    # d'/z-score trial firing rates (post-artifact window, matched baseline)
    post_win = (artifact_duration_s, window[1])
    post_dur = post_win[1] - post_win[0]
    base_win = (-post_dur, 0.0)
    base_fr = np.empty(stim_times.size)
    post_fr = np.empty(stim_times.size)
    for i, st in enumerate(stim_times):
        base_fr[i] = np.sum((spike_times_s >= st + base_win[0])
                            & (spike_times_s < st + base_win[1])) / post_dur
        post_fr[i] = np.sum((spike_times_s >= st + post_win[0])
                            & (spike_times_s < st + post_win[1])) / post_dur
    b_mean = base_fr.mean()
    b_std = np.std(base_fr, ddof=1) if base_fr.size > 1 else 0.0
    p_mean = post_fr.mean()
    p_std = np.std(post_fr, ddof=1) if post_fr.size > 1 else 0.0
    if b_std == 0 and p_std == 0:
        d_prime = abs(p_mean - b_mean)
    else:
        d_prime = (p_mean - b_mean) / np.sqrt((b_std**2 + p_std**2) / 2)
    b_std_safe = b_std if b_std != 0 else np.finfo(float).eps

    # baseline PSTH ensemble for the diagnostic panel
    all_baseline = None
    baseline_aucs = np.empty(num_baseline)
    last_base = None
    last_win = None
    for i in range(1, num_baseline + 1):
        bw = (window[0] - i * baseline_dur, window[0] - (i - 1) * baseline_dur)
        _, bm = calculate_psth_metrics(
            spike_times_s, stim_times, bw, bin_w, smoothing_method="gaussian",
            gaussian_width_ms=gauss_ms, artifact_exclusion_duration_s=artifact_duration_s)
        baseline_aucs[i - 1] = bm.auc
        if all_baseline is None:
            all_baseline = np.zeros((num_baseline, bm.psth_smooth.size))
        all_baseline[i - 1] = bm.psth_smooth
        last_base = bm
        last_win = bw
    mean_baseline_auc = float(baseline_aucs.mean())
    mean_baseline_psth = all_baseline.mean(axis=0)

    return {
        "response": resp_data,
        "resp_metrics": resp,
        "base_metrics": last_base,
        "current_baseline_window_s": last_win,
        "all_baseline_psth_smooth": all_baseline,
        "mean_baseline_psth": mean_baseline_psth,
        "auc_corrected": resp.auc - mean_baseline_auc,
        "d_prime": float(d_prime),
        "baseline_mean_hz": b_mean,
        "baseline_std_safe": b_std_safe,
        "num_baseline": num_baseline,
    }


def plot_individual_psth_and_raster(
    spike_times_s: np.ndarray,
    stim_times: np.ndarray,
    params: dict,
    out_path: str | Path,
    channel_id: int,
    pattern_idx: int,
    artifact_duration_s: float,
    data: dict | None = None,
) -> Path | None:
    """Two-panel per-electrode figure: spike raster + z-scored PSTH-vs-baseline.

    Port of the figure built inline in STEP 6 of ``stimActivityAnalysis.m``.
    Recomputes display quantities via the gaussian PSTH path unless ``data``
    (from :func:`_individual_electrode_display_data`) is supplied. Returns the
    written path, or ``None`` if the electrode has no spikes in the window.
    """
    window = tuple(float(x) for x in params["stimAnalysisWindow"])
    spike_times_s = np.asarray(spike_times_s, dtype=float).ravel()
    stim_times = np.asarray(stim_times, dtype=float).ravel()

    if data is None:
        data = _individual_electrode_display_data(
            spike_times_s, stim_times, window, artifact_duration_s)
    if data is None:
        return None

    resp = data["resp_metrics"]
    resp_data = data["response"]
    base = data["base_metrics"]
    b_mean = data["baseline_mean_hz"]
    b_std_safe = data["baseline_std_safe"]
    window_ms = np.array(window) * 1000.0

    zscore_psth = (resp.psth_smooth - b_mean) / b_std_safe
    zscore_baseline_psth = (data["mean_baseline_psth"] - b_mean) / b_std_safe

    # peak / half-max searched in the second half of the window (t >= 0)
    half = zscore_psth.size // 2
    tail = zscore_psth[half:]
    peak_rel = int(np.argmax(tail))
    peak_idx = peak_rel + half
    peak_val = float(zscore_psth[peak_idx])
    peak_t_ms = float(resp.time_vector_s[peak_idx] * 1000.0)
    halfmax = peak_val / 2.0
    hits = np.flatnonzero(zscore_psth[peak_idx:] <= halfmax)
    if hits.size:
        hm_idx = peak_idx + hits[0]
        hm_t_ms = float(resp.time_vector_s[hm_idx] * 1000.0)
        hm_val = float(zscore_psth[hm_idx])
    else:
        hm_t_ms = hm_val = np.nan

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle(
        f"Pattern {pattern_idx} | Electrode {int(channel_id)} | "
        f"Corrected AUC: {data['auc_corrected']:.3f} | d' = {data['d_prime']:.2f}",
        fontweight="bold")

    # panel 1: spike raster (trials reversed on y)
    for trial_idx, trial_spikes in enumerate(resp_data.spike_times_by_event, start=1):
        if trial_spikes.size:
            ax1.plot(trial_spikes * 1000.0, np.full(trial_spikes.size, trial_idx),
                     "r.", markersize=5)
    ax1.set_ylim(len(stim_times) + 1, 0)  # reversed, trial 1 at top
    ax1.set_xlim(window_ms)
    ax1.set_ylabel("Trial Number")
    ax1.set_xlabel("Time from stimulus (ms)")
    ax1.set_title("Spike Raster (Response)")
    ax1.grid(True, alpha=0.3)

    # panel 2: z-scored response vs baselines
    base_win = data["current_baseline_window_s"]
    base_time_ms = (base.time_vector_s - base_win[0]) * 1000.0
    for i in range(data["num_baseline"]):
        z_ind = (data["all_baseline_psth_smooth"][i] - b_mean) / b_std_safe
        ax2.plot(base_time_ms - window_ms[1], z_ind, color=(0.8, 0.8, 0.8), linewidth=0.5)
    ax2.plot(resp.time_vector_s * 1000.0, zscore_psth, "r-", linewidth=2, label="Response")
    ax2.plot(base_time_ms - window_ms[1], zscore_baseline_psth, "k-", linewidth=2,
             label="Mean Baseline")
    ax2.plot(peak_t_ms, peak_val, "bo", markerfacecolor="b", markersize=7)
    ax2.annotate(r" $Z_{max}$", (peak_t_ms, peak_val), va="bottom", ha="left",
                 fontweight="bold")
    if not np.isnan(hm_t_ms):
        ax2.plot(hm_t_ms, hm_val, "go", markerfacecolor="g", markersize=7)
        ax2.annotate(r" Half $Z_{max}$", (hm_t_ms, hm_val), va="top", ha="left",
                     fontweight="bold")
    ax2.set_title("Diagnostic: Response vs. Baselines (Z-score)")
    ax2.set_ylabel("Z-score")
    ax2.set_xlabel("Time from stimulus (ms)")
    ax2.set_xlim(window_ms)
    ax2.legend(loc="best")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return _save(fig, out_path)


def plot_individual_psth_and_raster_for_pattern(
    spike_times: dict,
    stim_info: list[StimChannelInfo],
    stim_times: np.ndarray,
    params: dict,
    out_dir: str | Path,
    pattern_idx: int,
    artifact_duration_s: float,
    max_channels: int = 5,
    auc_threshold: float = 0.5,
) -> list[Path]:
    """Select and plot the top-AUC electrodes for one pattern (STEP 6 loop).

    Computes corrected AUC per non-stim channel, keeps those ``> auc_threshold``,
    plots the top ``max_channels`` by AUC into
    ``Individual_PSTH_and_Raster_electrode_<id>.png``.
    """
    out_dir = Path(out_dir)
    method = params["SpikesMethod"]
    window = tuple(float(x) for x in params["stimAnalysisWindow"])
    stim_times = np.asarray(stim_times, dtype=float).ravel()

    stimulated = {c for c, info in enumerate(stim_info)
                  if info.pattern is not None and info.pattern > 0}

    candidates: list[tuple[float, int, dict]] = []
    for c in range(len(stim_info)):
        if c in stimulated:
            continue
        sp = _method_spikes(spike_times, c, method)
        if sp.size == 0:
            continue
        d = _individual_electrode_display_data(sp, stim_times, window, artifact_duration_s)
        if d is None:
            continue
        if d["auc_corrected"] > auc_threshold:
            candidates.append((d["auc_corrected"], c, d))

    candidates.sort(key=lambda t: t[0], reverse=True)
    written: list[Path] = []
    for _, c, d in candidates[:max_channels]:
        channel_id = int(stim_info[c].channel_name)
        sp = _method_spikes(spike_times, c, method)
        p = plot_individual_psth_and_raster(
            sp, stim_times, params,
            out_dir / f"Individual_PSTH_and_Raster_electrode_{channel_id}",
            channel_id, pattern_idx, artifact_duration_s, data=d)
        if p is not None:
            written.append(p)
    return written


# ── convenience: spike-latency / firing-rate metric heatmaps ──────────────────

def compute_median_spike_latency(
    spike_times: dict,
    stim_info: list[StimChannelInfo],
    stim_times: np.ndarray,
    params: dict,
) -> np.ndarray:
    """Per-channel median first-spike latency (ms) for one pattern.

    Mirrors STEP 7's ``channelMedianSpikeLatency_ms`` column, used to colour the
    ``spikeLatency_pattern_k_heatmap`` figure.
    """
    method = params["SpikesMethod"]
    search_end = float(params["stimAnalysisWindow"][1])
    stim_times = np.asarray(stim_times, dtype=float).ravel()
    out = np.full(len(stim_info), np.nan)
    for c in range(len(stim_info)):
        sp = _method_spikes(spike_times, c, method)
        if sp.size == 0:
            continue
        lat = get_spike_latency_rel_stim(stim_times, sp, search_end)
        if np.any(~np.isnan(lat)):
            out[c] = np.nanmedian(lat)
    return out
