"""Plotting layer for the MEA-Stim subsystem.

Every figure is a native chart (:mod:`meanap.native.chart`), so the in-app
viewer shows it live; the stimulus-detection checks are drawn by
:mod:`meanap.stim.detection_checks`, which these entry points call.

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
pixel-identical to MATLAB's, but aim to be at least as clear. Every function writes a PNG (default) whose basename matches
the MATLAB output artifact exactly.

Nothing here mutates the numeric modules; all display quantities are recomputed
from the ported detection/psth results passed in.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.colors import ListedColormap

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
    from meanap.native.figure import colormap

    cmap = colormap(cmap)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return _NAN_COLOR
    if vmax == vmin:
        norm = 0.0
    else:
        norm = (value - vmin) / (vmax - vmin)
    norm = float(min(1.0, max(0.0, norm)))
    return cmap(norm)


def _in_patterns(info: StimChannelInfo, pattern_ids) -> bool:
    """Whether the electrode stimulates in any of *pattern_ids*."""
    return any(p in pattern_ids for p in (info.pattern_ids or (info.pattern,)))


# ── plotStimHeatmap.m  (2_StimsHeatmap) ───────────────────────────────────────

def plot_stim_heatmap(stim_info: list[StimChannelInfo], out_path: str | Path) -> Path:
    """Electrode layout: stimulated electrodes black (red edge, pattern label),
    the rest white (port of ``plotStimHeatmap.m``)."""
    from meanap.native.chart_paint import save_chart
    from meanap.stim.detection_checks import StimCheckData, _stims_heatmap

    data = StimCheckData(
        recording="", duration_s=0.0,
        channel_names=np.array([int(i.channel_name) for i in stim_info]),
        coords=np.array([np.asarray(i.coords, float).ravel()[:2] for i in stim_info]),
        stim_times=[np.asarray(i.elec_stim_times, float).ravel() for i in stim_info],
        patterns=[tuple(i.pattern_ids or ((i.pattern,) if i.pattern else ()))
                  for i in stim_info],
        stim_dur_for_plotting=0.0, detection_method="", detection_value=np.nan)
    return save_chart(_stims_heatmap(data), _png(out_path))


# ── plotStimHeatmapWmetric.m  (stimPattern_k_heatmap, spikeLatency_k_heatmap) ──

#: matplotlib's text sizes at its defaults, which these figures were drawn at.
_TEXT = dict(title_size=12, label_size=10, tick_size=9)


def _png(out_path: str | Path) -> Path:
    """``out_path`` with ``.png`` added when it has no suffix (MATLAB names)."""
    out_path = Path(out_path)
    return out_path.with_suffix(".png") if out_path.suffix == "" else out_path


def _circle(xc: float, yc: float, r: float = 0.5, n: int = 48):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return xc + r * np.cos(t), yc + r * np.sin(t)


def _layout_limits(stim_info: list[StimChannelInfo]):
    xs = [float(i.coords[0]) for i in stim_info]
    ys = [float(i.coords[1]) for i in stim_info]
    return (min(xs) - 1, max(xs) + 1), (min(ys) - 1, max(ys) + 1)


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

    The stimulating electrode(s) of ``pattern_id`` are drawn white. A colour bar
    labelled ``cmap_label`` is added over ``vrange``. When ``categorical_legend``
    (a list of ``(rgb, label)``) is given, the colour bar is replaced by a
    legend beneath the array — used for the categorical significance heatmap.
    """
    from meanap.native.chart import (
        Chart, ColourBar, Legend, LegendItem, Panel, Polygon, rgba,
    )
    from meanap.native.chart_paint import save_chart
    from meanap.native.figure import colormap

    table = colormap(cmap)
    node_metric = np.asarray(node_metric, dtype=float).ravel()
    pattern_ids = pattern_id if np.iterable(pattern_id) else [pattern_id]
    lo, hi = (float(v) for v in vrange)
    if not (np.isfinite(lo) and np.isfinite(hi)):
        lo, hi = 0.0, 1.0

    marks, n_nan = [], 0
    for idx, info in enumerate(stim_info):
        xc, yc = float(info.coords[0]), float(info.coords[1])
        is_stim = info.elec_stim_times.size > 0 and _in_patterns(info, pattern_ids)
        value = node_metric[idx] if idx < node_metric.size else np.nan
        if is_stim:
            colour, said = _WHITE, "stimulating electrode"
        elif np.isnan(value):
            # MATLAB's valuesToColormap maps NaN to the darkest colour (its
            # two-argument min/max drop NaN), conflating "no data" with the
            # maximum; grey keeps them apart.
            colour, said, n_nan = _NAN_COLOR, "no data", n_nan + 1
        else:
            colour = values_to_colormap(value, table, lo, hi)
            said = f"{cmap_label}: {value:.4g}"
            if categorical_legend is not None:   # name the category, not the code
                said = next((lbl for c, lbl in categorical_legend
                             if np.allclose(rgba(c)[:3], rgba(colour)[:3])), said)
        px, py = _circle(xc, yc)
        marks.append(Polygon(px, py, fill=rgba(colour), edge=rgba("black"), edge_width=1.0,
                             hover=f"electrode {info.channel_name}\n{said}"))
    xlim, ylim = _layout_limits(stim_info)
    panel = Panel(marks=marks, bare=True, equal=True, xlim=xlim, ylim=ylim,
                  title=title or "", title_size=12)
    legend = None
    if categorical_legend is None:
        panel.colour_bar = ColourBar(table, lo, hi, label=cmap_label, fraction=0.046,
                                     tick_size=9)
        if n_nan:
            panel.legend = Legend([LegendItem(f"no data ({n_nan})", rgba(_NAN_COLOR),
                                              kind="point", edge=rgba("black"), size=9)],
                                  loc="lower right", size=9)
    else:
        legend = Legend([LegendItem(lbl, rgba(c), kind="point", edge=rgba("black"), size=10)
                         for c, lbl in categorical_legend],
                        loc="bottom", columns=len(categorical_legend), size=10)
    return save_chart(Chart([panel], size=(7, 6), legend=legend), _png(out_path))


# ── plotStimTimes.m, plotIdvStimDataAndTrace.m, plotStimDetectionChecks.m ─────
# Drawn by meanap.stim.detection_checks, from what the figures show of the raw
# data, so a bundle can redraw them; these keep the MATLAB-shaped entry points.

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
    from meanap.native.chart_paint import save_chart
    from meanap.stim.detection_checks import _stims_detected, compute_stim_check_data

    data = compute_stim_check_data(raw_data, stim_info, params, "", channels=[])
    return save_chart(_stims_detected(data), _png(out_path))


def plot_idv_stim_data_and_trace(
    raw_data: np.ndarray,
    channel_idx: int,
    stim_info: list[StimChannelInfo],
    params: dict,
    out_path: str | Path,
) -> Path:
    """Raw trace (top) + detected stim pulses (bottom) for one channel
    (port of ``plotIdvStimDataAndTrace.m``)."""
    from meanap.native.chart_paint import save_chart
    from meanap.stim.detection_checks import _electrode_trace, compute_stim_check_data

    data = compute_stim_check_data(raw_data, stim_info, params, "", channels=[channel_idx])
    return save_chart(_electrode_trace(data, channel_idx), _png(out_path))


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
    from meanap.stim.detection_checks import compute_stim_check_data, draw_stim_check_figures

    data = compute_stim_check_data(raw_data, stim_info, params, "", rng,
                                   num_no_stim=num_no_stim_traces)
    return draw_stim_check_figures(data, Path(out_dir))


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
    from meanap.native.chart import NONE, Chart, Line, Panel, Points, rgba
    from meanap.native.chart_paint import save_chart

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
    lo, hi = (np.nanmin(both), np.nanmax(both)) if np.isfinite(both).any() else (0.0, 1.0)
    marks = [Line([lo, hi], [lo, hi], colour=rgba("C1"), dash="--", width=1.5, z=1),
             Points(pre_fr, post_fr, fill=NONE, edge=rgba("C0"), edge_width=1.0, size=6.5,
                    hover=[f"electrode {i.channel_name}\npre {a:.2f}, post {b:.2f} spikes/s"
                           for i, a, b in zip(stim_info, pre_fr, post_fr)])]
    panel = Panel(marks=marks, title=_fn(info), xlabel="Pre-stim firing rate (spikes/s)",
                  ylabel="Post-stim firing rate (spikes/s)", grid="", **_TEXT)
    return save_chart(Chart([panel], size=(4, 4)), _png(out_path))


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
    import warnings

    from meanap.native.chart import Cells, Chart, ColourBar, Line, Panel, Polygon, rgba
    from meanap.native.chart_paint import save_chart

    n_ch = fr_aligned_to_stim.shape[0]
    bins_ms = np.asarray(raster_bins, dtype=float) * 1000.0
    centers_ms = bins_ms[1:]  # MATLAB plots against rasterBins(2:end)

    with warnings.catch_warnings():     # a channel with no trials: an all-NaN mean
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_fr = np.nanmean(fr_aligned_to_stim, axis=(0, 1))          # (n_bins,)
        per_channel = np.nanmean(fr_aligned_to_stim, axis=1)           # (n_ch, n_bins)
    top = float(np.nanmax(mean_fr)) if np.isfinite(mean_fr).any() else 1.0

    blank_ms = float(params.get("blankDurMode") or 0.0) * 1000.0
    artifact_end_ms = blank_ms + float(params.get("postStimWindowDur") or 0.0)
    xlim = (float(bins_ms[0]), float(bins_ms[-1]))

    trace = Panel(
        cell=(0, 0), title=_fn(info), ylabel=ylabel_txt, xlim=xlim, sharex="time", grid="",
        marks=[Polygon([0, artifact_end_ms, artifact_end_ms, 0], [0, 0, top, top],
                       fill=rgba((0.5, 0.5, 0.5), 0.3), z=0.5),
               Line(centers_ms, mean_fr, colour=rgba("C0"), width=1.5,
                    hover=[f"{t:g} ms: {v:.2f}" for t, v in zip(centers_ms, mean_fr)])],
        **_TEXT)
    finite = per_channel[np.isfinite(per_channel)]
    lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)

    def hover(i, j):
        v = per_channel[i, j]
        return (f"channel {i + 1}, {bins_ms[j]:g} to {bins_ms[j + 1]:g} ms\n"
                + (f"{v:.2f} spikes/s" if np.isfinite(v) else "no value"))

    heat = Panel(
        cell=(1, 0), xlabel="Time from stimulation (ms)", ylabel="Channel", xlim=xlim,
        sharex="time", grid="", y_down=True,
        marks=[Cells(per_channel, cmap=parula_map, low=lo, high=hi, x=xlim,
                     y=(0.5, n_ch + 0.5), hover=hover)],
        colour_bar=ColourBar(parula_map, lo, hi, label="Firing rate (spikes/s)",
                             fraction=0.046, tick_size=9),
        **_TEXT)
    return save_chart(Chart([trace, heat], size=(6, 5), grid=(2, 1)), _png(out_path))


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
    from meanap.native.chart import (
        Cells, Chart, ColourBar, ErrorBars, Legend, LegendItem, Panel, Points, rgba,
    )
    from meanap.native.chart_paint import save_chart

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
    names = [str(i.channel_name) for i in stim_info] if len(stim_info) == n_ch else \
        [str(k) for k in x]

    written: list[Path] = []

    # Figure 1: null-dist heatmap (sorted) + observed vs null
    null_sorted = np.sort(null, axis=1)
    finite = null_sorted[np.isfinite(null_sorted)]
    lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    heat = Panel(
        cell=(0, 0), title=f"Null trial proportion distribution – {title_suffix}  |  {_fn(info)}",
        xlabel="Shuffle (sorted)", ylabel="Channel Index", grid="", y_down=True,
        marks=[Cells(null_sorted, cmap=parula_map, low=lo, high=hi, x=(1, n_shuffles),
                     y=(0.5, n_ch + 0.5),
                     hover=lambda i, j: f"channel {i + 1} (electrode {names[i]}), "
                                        f"shuffle rank {j + 1}\n{null_sorted[i, j]:.3f}")],
        colour_bar=ColourBar(parula_map, lo, hi, fraction=0.046, tick_size=9),
        **{**_TEXT, "title_size": 10})

    null_median = np.median(null, axis=1)
    grey, blue, red = rgba((0.6, 0.6, 0.6)), rgba((0.3, 0.3, 0.7)), rgba((0.9, 0.2, 0.2))

    def said(k):
        return (f"channel {x[k]} (electrode {names[k]})\nobserved {obs[k]:.3f}; null median "
                f"{null_median[k]:.3f} [{pctile_lo[k]:.3f}, {pctile_hi[k]:.3f}]")

    marks = [ErrorBars(x, null_median, yerr=np.vstack([null_median - pctile_lo,
                                                       pctile_hi - null_median]),
                       colour=grey, width=1.0),
             Points(x, null_median, fill=grey, size=4, z=2,
                    hover=[said(k) for k in range(n_ch)])]
    for mask, colour, size, label in ((~is_sig, blue, 5.5, "Not significant"),
                                      (is_sig, red, 7.5, "Significant")):
        if mask.any():
            marks.append(Points(x[mask], obs[mask], fill=colour, size=size,
                                hover=[said(k) for k in np.flatnonzero(mask)]))
    scatter = Panel(
        cell=(1, 0), title=f"Observed vs null – {title_suffix}", xlabel="Channel Index",
        ylabel="Proportion of trials (post > pre)", grid="", marks=marks,
        legend=Legend([LegendItem("Not significant", blue, kind="point"),
                       LegendItem("Significant", red, kind="point"),
                       LegendItem("Null median ± CI", grey, kind="tick")], loc="best", size=9),
        **{**_TEXT, "title_size": 10})
    written.append(save_chart(Chart([heat, scatter], size=(8, 5), grid=(2, 1)),
                              out_dir / f"12_shuffle_test_null_dist{name_suffix}.png"))

    # Figure 2: categorical significance heatmap (only per-pattern)
    if pattern_idx is not None:
        sig_red = (0.9, 0.2, 0.2)
        not_sig_grey = (0.85, 0.85, 0.85)
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

    from meanap.native.chart import (
        Chart, Legend, LegendItem, Line, Panel, Points, Text, rgba,
    )
    from meanap.native.chart_paint import save_chart

    red, black, blue, green = rgba("r"), rgba("k"), rgba("b"), rgba("g")
    xs, ys = [], []
    for trial_idx, trial_spikes in enumerate(resp_data.spike_times_by_event, start=1):
        xs.append(np.asarray(trial_spikes, float) * 1000.0)
        ys.append(np.full(len(trial_spikes), trial_idx, float))
    xs = np.concatenate(xs) if xs else np.zeros(0)
    ys = np.concatenate(ys) if ys else np.zeros(0)
    raster = Panel(
        cell=(0, 0), title="Spike Raster (Response)", xlabel="Time from stimulus (ms)",
        ylabel="Trial Number", xlim=tuple(window_ms), ylim=(0, len(stim_times) + 1),
        y_down=True, grid="xy", sharex="time",
        marks=[Points(xs, ys, fill=red, size=3.5,
                      hover=[f"trial {int(y)}: spike at {x:.2f} ms" for x, y in zip(xs, ys)])],
        **_TEXT)

    base_win = data["current_baseline_window_s"]
    base_time_ms = (base.time_vector_s - base_win[0]) * 1000.0 - window_ms[1]
    marks = []
    for i in range(data["num_baseline"]):
        z_ind = (data["all_baseline_psth_smooth"][i] - b_mean) / b_std_safe
        marks.append(Line(base_time_ms, z_ind, colour=rgba((0.8, 0.8, 0.8)), width=0.5, z=1))
    resp_ms = resp.time_vector_s * 1000.0
    marks += [
        Line(resp_ms, zscore_psth, colour=red, width=2, key="Response",
             hover=[f"response at {t:.1f} ms: z = {v:.2f}" for t, v in zip(resp_ms, zscore_psth)]),
        Line(base_time_ms, zscore_baseline_psth, colour=black, width=2, key="Mean Baseline",
             hover=[f"mean baseline at {t:.1f} ms: z = {v:.2f}"
                    for t, v in zip(base_time_ms, zscore_baseline_psth)]),
        Points([peak_t_ms], [peak_val], fill=blue, size=7,
               hover=[f"Z max {peak_val:.2f} at {peak_t_ms:.1f} ms"]),
        Text(peak_t_ms, peak_val, "  Z max", size=10, bold=True, ha="left", va="bottom"),
    ]
    if not np.isnan(hm_t_ms):
        marks += [Points([hm_t_ms], [hm_val], fill=green, size=7,
                         hover=[f"half Z max {hm_val:.2f} at {hm_t_ms:.1f} ms"]),
                  Text(hm_t_ms, hm_val, "  Half Z max", size=10, bold=True, ha="left",
                       va="top")]
    diagnostic = Panel(
        cell=(1, 0), title="Diagnostic: Response vs. Baselines (Z-score)",
        xlabel="Time from stimulus (ms)", ylabel="Z-score", xlim=tuple(window_ms),
        grid="xy", sharex="time", marks=marks,
        legend=Legend([LegendItem("Response", red, key="Response"),
                       LegendItem("Mean Baseline", black, key="Mean Baseline")],
                      loc="best", size=9),
        **_TEXT)
    chart = Chart([raster, diagnostic], size=(12, 8), grid=(2, 1), title_size=12,
                  title=f"Pattern {pattern_idx} | Electrode {int(channel_id)} | "
                        f"Corrected AUC: {data['auc_corrected']:.3f} | d' = {data['d_prime']:.2f}")
    return save_chart(chart, _png(out_path))

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
    only_electrode: int | None = None,
) -> list[Path]:
    """Select and plot the top-AUC electrodes for one pattern (STEP 6 loop).

    Computes corrected AUC per non-stim channel, keeps those ``> auc_threshold``,
    plots the top ``max_channels`` by AUC into
    ``Individual_PSTH_and_Raster_electrode_<id>.png`` — or, given
    ``only_electrode``, just that one of them.
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
        if only_electrode is not None and channel_id != only_electrode:
            continue
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
