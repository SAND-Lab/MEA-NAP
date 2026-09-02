"""Redraw a run's figures from a bundle, on demand.

Express mode ships the data and drops the pictures; this module puts the
pictures back. It is deliberately thin: every figure is produced by calling
:func:`meanap.pipeline.step4._plot_recording_lag` — *the same function the
pipeline calls* — with state reassembled from the bundle. No plotting code is
duplicated here, so a reconstructed figure cannot drift from the one the
pipeline would have drawn. :func:`python/test_bundle_render.py` pins that down
by rendering both ways and comparing pixels.

Three things have to be rebuilt from what the bundle stores:

``adjMsub``
    The active-node subgraph every network figure draws. Not stored, because it
    is a pure function of the full adjacency (in the state ``.npz``) and
    ``activeChannelIndex`` (in the metrics JSON) — see
    :func:`meanap.pipeline.step4.compute_network_metrics`, which this mirrors.
``batch_bounds``
    Pooled node-metric ranges for the ``_scaled`` figure variants. Recomputed
    across every recording in the bundle, exactly as the pipeline's phase 2
    does, so the batch-scaled plots keep their shared axes.
numpy arrays
    JSON round-trips arrays to lists; the plotters want arrays back.

Two capabilities the pipeline itself doesn't need fall out for free. Any figure
can be emitted as **SVG or PDF** — vector, editable, publication-ready —
because matplotlib picks the format from the suffix. And ``overrides`` re-renders
with different styling (node size, edge threshold, colour map) without touching
the stored results, which is what makes an interactive viewer possible.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from meanap.params import Params
from meanap.timescale import timescale_kind
from meanap.pipeline.bundle import RunBundle
from meanap.pipeline.palette import ColorScheme
from meanap.pipeline.resume import ADJM_SUFFIX, CATNAP_SUFFIX
from meanap.pipeline.spreadsheet import RecordingInfo

__all__ = [
    "FIGURES",
    "GROUP_FAMILIES",
    "VECTOR_FORMATS",
    "FigureSpec",
    "RenderContext",
    "available_figures",
    "available_activity_figures",
    "ACTIVITY_FIGURES",
    "SPIKE_CHECK_FIGURES",
    "available_spike_check_figures",
    "render_spike_check_figure",
    "available_edge_check_lags",
    "render_edge_check_figure",
    "figure_variants",
    "SUBNETWORK_FIGURES",
    "available_subnetwork_figures",
    "render_subnetwork_figure",
    "render_subnetwork_figure_set",
    "available_group_families",
    "load_context",
    "render_figure",
    "render_activity_figure",
    "render_group_family",
    "gallery",
    "cached_figure",
    "style_from_overrides",
    "COMPARISON_FAMILIES",
    "COMPARISON_LEVELS",
    "COMPARISON_SPLITS",
    "Choice",
    "ComparisonAxes",
    "ComparisonFamily",
    "LAG_SERIES",
    "LagSeries",
    "LevelAxis",
    "available_comparison_families",
    "available_lag_series",
    "cached_lag_series_figure",
    "lag_series",
    "render_lag_series_figure",
    "cached_comparison_figure",
    "comparison_axes",
    "comparison_family",
    "comparison_lags",
    "comparison_metrics",
    "render_comparison_figure",
]

#: Formats that produce editable vector output rather than pixels.
VECTOR_FORMATS = ("svg", "pdf")


@dataclass(frozen=True)
class FigureSpec:
    """One redrawable figure: its file stem and a human-readable label."""

    name: str
    label: str
    #: Metrics key that must be present for this figure to exist.
    requires: str | None = None


#: The 4A figure set, keyed by the base filename ``_plot_recording_lag`` writes.
#: ``requires`` mirrors that function's own guards so a viewer can list only
#: what a given recording actually has, rather than offering a button that
#: silently produces nothing.
FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec("1_adjM{lag}msConnectivityStats", "Connectivity statistics"),
    FigureSpec("2_MEA_NetworkPlot", "Network — node degree", "ND"),
    FigureSpec("3_MEA_NetworkPlotNodedegreeBetweennesscentrality",
               "Network — betweenness centrality", "BC"),
    FigureSpec("4_MEA_NetworkPlotNodedegreeParticipationcoefficient",
               "Network — participation coefficient", "PC"),
    FigureSpec("5_MEA_NetworkPlotNodestrengthLocalefficiency",
               "Network — local efficiency", "Eloc"),
    FigureSpec("6_circular_NetworkPlotNodedegreeModule", "Circular — modules", "Ci"),
    FigureSpec("7_adjM{lag}msGraphMetricsByNode", "Graph metrics by node", "ND"),
    FigureSpec("9_adjM{lag}msNodeCartography", "Node cartography", "PC"),
    FigureSpec("9_circular_NetworkPlotNodeCartography",
               "Circular — cartography", "NdCartDiv"),
    FigureSpec("10_MEA_NetworkPlotNodedegreeAveragecontrollability",
               "Network — average controllability", "aveControl"),
    FigureSpec("11_MEA_NetworkPlotNodedegreeModalcontrollability",
               "Network — modal controllability", "modalControl"),
    FigureSpec("12_MeanImageAndNetwork", "Field of view beside network"),
)


#: The step-2 per-recording activity figures, in the order the pipeline writes
#: them. ``requires`` is the ``ephys`` key each needs; the two with ``None``
#: are always available because they are drawn from the spike times.
ACTIVITY_FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec("1_FiringRateByElectrode", "Firing rate by electrode"),
    FigureSpec("2_Heatmap", "Firing rate heatmap", "FR"),
    FigureSpec("3_Raster", "Raster"),
    FigureSpec("3_BurstRate_heatmap", "Burst rate heatmap", "channelBurstRate"),
    FigureSpec("4_BurstDur_heatmap", "Burst duration heatmap", "channelBurstDur"),
    FigureSpec("5_FractSpikesInBursts_heatmap", "Fraction of spikes in bursts",
               "channelFracSpikesInBursts"),
    FigureSpec("6_ISIwithinBurst_heatmap", "ISI within burst",
               "channelISIwithinBurst"),
    FigureSpec("7_ISIoutsideBurst_heatmap", "ISI outside bursts",
               "channeISIoutsideBurst"),
    FigureSpec("8_BurstDetectionInfo", "Burst detection detail"),
)

#: The step-1 spike-detection check figures. Rebuilt from the payload step 1
#: saves beside the spike times, so all three stand or fall together — there is
#: no per-figure ``requires`` to test.
SPIKE_CHECK_FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec("1_ExampleTraces", "Example traces with detected spikes"),
    FigureSpec("2_SpikeFrequencies", "Spike frequency over time"),
    FigureSpec("3_Waveforms", "Spike waveforms by method"),
)

#: Per-channel metrics whose heatmap colour ceiling is pooled across the batch
#: (MATLAB's ``maxValStruct``). Must match step 2's own list, or a rebuilt
#: heatmap would use a different colour scale from the pipeline's.
_ACTIVITY_BATCH_METRICS = (
    "FR", "channelBurstRate", "channelBurstDur",
    "channelFracSpikesInBursts", "channelISIwithinBurst", "channeISIoutsideBurst",
)


@dataclass
class RenderContext:
    """Everything needed to redraw one bundle's figures, loaded once.

    Loading is not free (metrics JSON plus one ``.npz`` per recording), and a
    viewer answers many requests against the same bundle, so callers should
    build this once and reuse it.
    """

    params: Params
    recordings: dict[str, RecordingInfo]
    results: dict[str, dict]
    batch_bounds: dict[str, tuple[float, float] | None]
    root: Path
    mode: str = "catnap"
    #: ``{recording: frame rate in Hz}`` for CAT-NAP runs. Not on
    #: :class:`RecordingInfo` because that is the spreadsheet roster, known
    #: before any recording is opened, whereas the rate is read out of each
    #: recording's ``ops.npy`` during the run. Empty for ephys runs, and for
    #: folders written before the rate was recorded.
    sampling_rates: dict[str, float] = dataclasses.field(default_factory=dict)

    def lags(self, recording: str) -> list[int]:
        return sorted(int(k.replace("mslag", ""))
                      for k in self.results.get(recording, {}))


def _to_arrays(obj):
    """Undo the array→list flattening ``_convert_numpy`` applies for JSON."""
    if isinstance(obj, dict):
        return {k: _to_arrays(v) for k, v in obj.items()}
    if isinstance(obj, list):
        # Only numeric lists become arrays; a list of strings (marker names,
        # say) must stay a list or the plotters' string handling breaks.
        flat = np.asarray(obj)
        return flat if flat.dtype.kind in "fiub" else obj
    return obj


def load_context(bundle: RunBundle | Path | str) -> RenderContext:
    """Assemble a :class:`RenderContext` from an opened bundle or a folder.

    Accepts a plain output folder too, so the renderer works against a run that
    was never bundled — useful for regenerating one figure as SVG after a
    normal run.
    """
    if isinstance(bundle, RunBundle):
        root, params, mode = bundle.root, bundle.params, bundle.mode
        rec_rows = bundle.recordings
    else:
        from meanap.params import PARAMS_FILENAME, load_params
        root = Path(bundle)
        params = (load_params(root / PARAMS_FILENAME)[0]
                  if (root / PARAMS_FILENAME).exists() else Params())
        mode = "catnap" if params.suite2p_mode else "ephys"
        rec_rows = _recordings_from_csv(root)

    recordings = {
        r["filename"]: RecordingInfo(
            filename=r["filename"], div=float(r.get("div") or 0), group=r.get("group", ""),
        )
        for r in rec_rows
    }

    from meanap.catnap.rates import read_sampling_rates

    sampling_rates = read_sampling_rates(root)

    metrics_path = root / "4_NetworkActivity" / "netmet_results.json"
    if not metrics_path.exists():
        raise ValueError(
            f"No network metrics in {root} — expected "
            "4_NetworkActivity/netmet_results.json. This run may predate express "
            "mode, or may not have reached step 4."
        )
    with open(metrics_path) as fh:
        results = _to_arrays(json.load(fh))

    # adjMsub is derived, not stored — see the module docstring.
    for rec_name, per_lag in results.items():
        state_path = _state_file(root, rec_name)
        if state_path is None:
            continue
        with np.load(state_path) as data:
            adj_keys = _adjacency_keys(data)
            for lag_key, metrics in per_lag.items():
                full_key = f"adjM{lag_key.replace('mslag', '')}mslag"
                if full_key not in adj_keys or "activeChannelIndex" not in metrics:
                    continue
                metrics["adjMsub"] = _active_subgraph(
                    data[adj_keys[full_key]], metrics["activeChannelIndex"])

    from meanap.pipeline.step4 import _batch_metric_bounds
    batch_bounds = {m: _batch_metric_bounds(results, m)
                    for m in ("ND", "NS", "BC", "PC", "Eloc")}

    return RenderContext(params=params, recordings=recordings, results=results,
                         batch_bounds=batch_bounds, root=root, mode=mode,
                         sampling_rates=sampling_rates)


def _state_file(root: Path, recording: str) -> Path | None:
    """The per-recording array file, whichever pipeline produced it.

    CAT-NAP writes ``<rec>_catnap.npz`` (adjacency, coords, cell types); the
    electrophysiology path writes ``<rec>_adjM.npz`` (adjacency + channels).
    Both hold what the 4A figures need — for ephys, node positions come from
    the channel layout rather than being stored — so the renderer takes
    whichever is present instead of having two code paths.
    """
    for suffix in (CATNAP_SUFFIX, ADJM_SUFFIX):
        path = root / "ExperimentMatFiles" / f"{recording}{suffix}"
        if path.exists():
            return path
    return None


def _adjacency_keys(data) -> dict[str, str]:
    """Map ``adjM{lag}mslag`` → the key holding it in *data*.

    CAT-NAP prefixes its adjacency entries (``adj__``) to keep them apart from
    the stats in the same file; step 3 stores them bare, alongside a ``_raw``
    (pre-thresholding) copy that the metrics were *not* computed from.
    """
    prefixed = {k[len("adj__"):]: k for k in data.files if k.startswith("adj__")}
    if prefixed:
        return prefixed
    return {k: k for k in data.files
            if k.startswith("adjM") and k.endswith("mslag")}


def _active_subgraph(adj_m: np.ndarray, active_index) -> np.ndarray:
    """Rebuild ``adjMsub`` exactly as ``compute_network_metrics`` does.

    The clip-and-fill must match that function or reconstructed figures would
    differ from the pipeline's on any matrix with negatives or NaNs.
    """
    adj = np.asarray(adj_m, dtype=float).copy()
    adj[adj < 0] = 0.0
    adj = np.nan_to_num(adj, nan=0.0)
    idx = np.asarray(active_index, dtype=int)
    return adj[np.ix_(idx, idx)]


def _recordings_from_csv(root: Path) -> list[dict]:
    """Recover the recordings table from the recording-level CSV."""
    import pandas as pd

    path = root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path).drop_duplicates("FileName")
    return [{"filename": r.FileName, "group": r.Grp, "div": r.DIV}
            for r in df.itertuples()]


def available_figures(ctx: RenderContext, recording: str, lag: int) -> list[FigureSpec]:
    """Which figures this recording/lag can actually produce."""
    metrics = ctx.results.get(recording, {}).get(f"{lag}mslag", {})
    if "adjMsub" not in metrics:
        return []
    out = []
    for spec in FIGURES:
        if spec.requires is not None and spec.requires not in metrics:
            continue
        if spec.name == "12_MeanImageAndNetwork" and _background_path(ctx, recording) is None:
            continue
        out.append(dataclasses.replace(spec, name=spec.name.format(lag=lag)))
    return out


def _background_path(ctx: RenderContext, recording: str) -> Path | None:
    from meanap.catnap.store import BACKGROUND_SUFFIX

    path = ctx.root / "ExperimentMatFiles" / f"{recording}{BACKGROUND_SUFFIX}"
    return path if path.exists() else None


def render_figure(
    ctx: RenderContext,
    recording: str,
    lag: int,
    figure: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
    variant: str = "plain",
) -> Path:
    """Redraw one figure and return the file written.

    ``fmt`` may be any format matplotlib writes; ``svg`` and ``pdf`` give
    editable vector output. ``overrides`` is a mapping of ``Params`` field names
    to values, applied to a *copy* — so a viewer can restyle a plot (node size,
    edge threshold, colour map) without disturbing the bundle or any other
    request.

    Raises :class:`ValueError` when the figure isn't available for this
    recording/lag, rather than silently writing nothing.
    """
    from meanap.catnap.store import load_background
    from meanap.network_plot import NetworkStyle
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.step4 import _plot_recording_lag, variant_stem

    lag_key = f"{lag}mslag"
    metrics = ctx.results.get(recording, {}).get(lag_key)
    if not metrics:
        raise ValueError(f"No results for {recording} at {lag} ms lag")
    if "adjMsub" not in metrics:
        raise ValueError(
            f"{recording} at {lag} ms lag has no adjacency subgraph — the run "
            "excluded it (too few active nodes) or its state file is missing."
        )

    rec = ctx.recordings.get(recording) or RecordingInfo(
        filename=recording, div=0.0, group="")

    params, style = _apply_overrides(ctx.params, overrides)

    channels, coords, markers = _recording_arrays(ctx, recording)
    background = None
    bg_path = _background_path(ctx, recording)
    if bg_path is not None:
        background = load_background(bg_path)

    # The scaled/combined versions are drawn by the same call, under their own
    # names — so asking for one is just asking for a different stem.
    wanted = variant_stem(figure, variant)
    if wanted is None:
        raise ValueError(
            f"'{figure}' has no '{variant}' version — only the spatial network "
            f"plots do. Use figure_variants() to list what a figure offers.")

    with figure_dpi(dpi):
        written = _plot_recording_lag(
            rec, lag, metrics, channels, params, Path(out_dir), lambda m: None,
            ctx.batch_bounds, coords_all=coords, cell_types=markers,
            background=background,
            # NetworkStyle.for_run, not `twop_auto_node_size` read directly:
            # that flag defaults to True and applies only to suite2p runs, so
            # reading it here sized an *ephys* re-render "auto" when the
            # pipeline had drawn it at 1.0.
            node_size_scale=NetworkStyle.for_run(params).node_size_scale,
            fmt=fmt, only=wanted, style=style,
        )
    if not written:
        raise ValueError(
            f"'{figure}' ({variant}) is not one of the figures available for "
            f"{recording} at {lag} ms lag. Use available_figures() to list them."
        )
    return written[0]


def figure_variants(ctx: RenderContext, recording: str, lag: int,
                    figure: str) -> list[str]:
    """Which scalings of *figure* exist for this recording and lag.

    Always at least ``["plain"]``. The batch-scaled and side-by-side versions
    need a pooled bound for the figure's size metric, which a single-recording
    bundle may not have — so this is asked per bundle rather than assumed.
    """
    # Imported here, not at module scope: step4 pulls in matplotlib, and this
    # module is careful to stay cheap to import.
    from meanap.pipeline.step4 import FIGURE_VARIANTS, SPATIAL_PLOTS

    spec = next((sp for sp in SPATIAL_PLOTS
                 if Path(sp[0]).stem == Path(figure).stem), None)
    if spec is None:
        return ["plain"]
    size_key = spec[3]
    if not ctx.batch_bounds.get(size_key):
        return ["plain"]
    return list(FIGURE_VARIANTS)


#: Styling knobs the viewer exposes, forwarded to
#: :class:`~meanap.network_plot.NetworkStyle` rather than to ``Params``. These
#: are the Network Viewer tab's controls; keeping them separate is what lets a
#: request restyle a figure without pretending the run used those settings.
STYLE_KEYS = frozenset({
    "max_edges", "edge_threshold_method", "edge_threshold", "layout",
    "node_size_scale", "node_scaling_method", "node_scaling_power",
    "min_node_size", "min_edge_width", "max_edge_width", "colormap",
})


def style_from_overrides(overrides: dict | None, params: Params | None = None):
    """Split a request's overrides into the styling half.

    The overrides are applied *on top of the styling this run drew with*
    (:meth:`NetworkStyle.for_run`), not on top of a fresh ``NetworkStyle``.
    A request only carries the controls that were changed, so building from
    class defaults meant changing any one of them silently reset the rest —
    most visibly node sizing, which CAT-NAP runs leave on ``"auto"`` and a
    fresh ``NetworkStyle`` puts at ``1.0``.

    Returns ``None`` when nothing styling-related was asked for, which keeps
    the pipeline's own styling — and therefore pixel parity — in force.
    """
    from meanap.network_plot import NetworkStyle

    picked = {k: v for k, v in (overrides or {}).items() if k in STYLE_KEYS}
    if not picked:
        return None
    base = (NetworkStyle.for_run(params) if params is not None
            else NetworkStyle())
    return dataclasses.replace(base, **picked)


def _apply_overrides(params: Params, overrides: dict | None):
    """Split overrides into ``(Params, NetworkStyle | None)``.

    Both are applied to copies, so a request never mutates the loaded context.
    An unrecognised key is an error rather than a silent no-op: a viewer
    control that quietly does nothing is worse than one that reports itself.
    """
    style = style_from_overrides(overrides, params)
    param_names = {f.name for f in dataclasses.fields(Params)}
    rest = {k: v for k, v in (overrides or {}).items() if k not in STYLE_KEYS}
    unknown = set(rest) - param_names
    if unknown:
        raise ValueError(f"Unknown parameter override(s): {sorted(unknown)}")
    return (dataclasses.replace(params, **rest) if rest else params), style


# ── Batch (2B / 4B) comparison figures ────────────────────────────────────────


@dataclass(frozen=True)
class GroupFamily:
    """One batch-comparison figure family and where it lands."""

    key: str
    label: str
    #: Output subfolder, relative to the run root.
    out_subdir: str


GROUP_FAMILIES: tuple[GroupFamily, ...] = (
    GroupFamily("network", "Network metrics by group and age", "4_NetworkActivity"),
    GroupFamily("activity", "Two-photon activity by group and age", "2_NeuronalActivity"),
    GroupFamily("cell_type", "Activity by cell type", "2_NeuronalActivity"),
    GroupFamily("subnetwork", "Cell-type subnetworks by group and age", "4_NetworkActivity"),
    GroupFamily("ephys_activity", "Neuronal activity by group and age",
                "2_NeuronalActivity"),
)


def _ephys_stats(ctx: RenderContext) -> dict:
    """Step-2 ``Ephys`` dicts, read back from ``ephys_results.json``.

    The electrophysiology counterpart of the CAT-NAP activity stats; a
    different file and a different plotter, but the same idea — the numbers the
    2B comparison figures are drawn from.
    """
    path = ctx.root / "2_NeuronalActivity" / "ephys_results.json"
    if not path.exists():
        return {}
    with open(path) as fh:
        return _to_arrays(json.load(fh))


def available_group_families(ctx: RenderContext) -> list[GroupFamily]:
    """Which batch families this bundle has the inputs for.

    Each depends on something optional — activity stats, a cell-type grouping,
    the subnetwork analysis having been switched on — so a viewer should ask
    rather than assume.
    """
    out = []
    for fam in GROUP_FAMILIES:
        if fam.key == "network" and ctx.results:
            out.append(fam)
        elif fam.key == "activity" and _all_stats(ctx):
            out.append(fam)
        elif fam.key == "cell_type" and _groups_by_rec(ctx):
            out.append(fam)
        elif fam.key == "subnetwork" and _subnetwork_rows(ctx)[0]:
            out.append(fam)
        elif fam.key == "ephys_activity" and _ephys_stats(ctx):
            out.append(fam)
    return out


def _states(ctx: RenderContext) -> dict:
    """Per-recording stored state, loaded once and cached on the context."""
    cached = getattr(ctx, "_states_cache", None)
    if cached is not None:
        return cached
    from meanap.catnap.store import load_recording_state

    states: dict = {}
    for name in ctx.recordings:
        path = ctx.root / "ExperimentMatFiles" / f"{name}{CATNAP_SUFFIX}"
        if path.exists():
            states[name] = load_recording_state(path, Path("."))
    object.__setattr__(ctx, "_states_cache", states)
    return states


def _all_stats(ctx: RenderContext) -> dict:
    return {name: stats for name, (_, stats) in _states(ctx).items() if stats}


def _channels_by_rec(ctx: RenderContext) -> dict:
    return {name: state.channels for name, (state, _) in _states(ctx).items()}


def _groups_by_rec(ctx: RenderContext) -> dict:
    return {name: state.groups for name, (state, _) in _states(ctx).items()
            if state.groups is not None and state.groups.n_groups}


def _subnetwork_rows(ctx: RenderContext) -> tuple[list, list]:
    """The cell-type subnetwork tables, read back from the bundle's CSVs."""
    import pandas as pd

    def read(name: str) -> list:
        path = ctx.root / "4_NetworkActivity" / name
        return (pd.read_csv(path).to_dict("records") if path.exists() else [])

    return read("Subnetwork_RecordingLevel.csv"), read("Subnetwork_NodeLevel.csv")


def render_group_family(
    ctx: RenderContext,
    family: str,
    out_root: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> list[Path]:
    """Redraw one batch-comparison family, returning the files written.

    These are whole folders of small multiples rather than single figures, so
    unlike :func:`render_figure` this renders a family at a time — which is
    also how the pipeline produces them.

    ``dpi`` overrides each plot's authored resolution; pass
    :data:`~meanap.pipeline.figure_output.DEFAULT_THUMBNAIL_DPI` for a gallery.
    Leave it ``None`` for figures meant to be looked at closely.
    """
    from meanap.catnap import group_plots as gp
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons

    fam = next((f for f in GROUP_FAMILIES if f.key == family), None)
    if fam is None:
        raise ValueError(
            f"Unknown figure family {family!r}; expected one of "
            f"{[f.key for f in GROUP_FAMILIES]}")

    params, _ = _apply_overrides(ctx.params, overrides)
    order = params.custom_grp_order or None
    scheme = ColorScheme.from_params(params)
    out_root = Path(out_root)
    out_dir = out_root / fam.out_subdir
    recordings = list(ctx.recordings.values())
    before = set(out_dir.rglob("*")) if out_dir.exists() else set()

    with figure_dpi(dpi):
        if fam.key == "network":
            plot_step4_group_comparisons(recordings, ctx.results, out_dir, order,
                                         fmt=fmt, colors=scheme,
                                         timescale=timescale_kind(params))
        elif fam.key == "activity":
            gp.plot_twop_group_comparisons(
                recordings, _all_stats(ctx), out_dir, custom_grp_order=order,
                channels_by_rec=_channels_by_rec(ctx), fmt=fmt)
        elif fam.key == "cell_type":
            _, df_node = gp.twop_stats_frames(
                recordings, _all_stats(ctx), _channels_by_rec(ctx))
            groups_by_rec = _groups_by_rec(ctx)
            by_type = gp.add_cell_type_column(
                df_node, groups_by_rec, _channels_by_rec(ctx))
            composition = gp.composition_frame(
                recordings, groups_by_rec, _channels_by_rec(ctx),
                # Without this the "active cells" columns are omitted, and the
                # four 5_CellTypeComposition figures that read them are simply
                # never drawn — which is how they went missing from bundles.
                active_by_rec=gp.active_channels(df_node))
            gp.plot_activity_by_cell_type(
                by_type, composition, out_dir, custom_grp_order=order, fmt=fmt)
        elif fam.key == "ephys_activity":
            from meanap.pipeline.plotting_step2 import plot_step2_group_comparisons
            plot_step2_group_comparisons(
                recordings, _ephys_stats(ctx), out_dir, order, fmt=fmt, colors=scheme)
        else:  # subnetwork
            summary, node = _subnetwork_rows(ctx)
            gp.plot_subnetwork_group_comparisons(
                summary, node, out_dir, order, fmt=fmt,
                timescale=timescale_kind(params))

    return sorted(p for p in out_dir.rglob(f"*.{fmt}")
                  if p.is_file() and p not in before)


# ── One comparison figure at a time ───────────────────────────────────────────
#
# The half-violin families (4B network metrics, 2B neuronal activity) are the
# ones that hurt as galleries: on a three-lag run the network family alone is
# 274 small multiples in a single scroll. But every one of them is one metric
# at one lag, so each has an address — (level, split, lag, metric) — and can be
# drawn on its own, exactly as a 4A figure can. That is what makes the viewer's
# comparison tab selectable rather than a wall.
#
# The families below draw *nothing new*: same function, same arguments, same
# filenames as the folder-at-a-time path. Only the reaching is different.


@dataclass(frozen=True)
class ComparisonFamily:
    """A family whose figures are one metric each, and so individually addressable."""

    key: str
    #: Output subfolder for the whole step, relative to the run root.
    out_subdir: str
    #: The comparisons folder inside it, as the pipeline names it.
    comparisons_dir: str
    #: Whether its figures are per-STTC-lag. Step-2 activity metrics are not.
    has_lag: bool


COMPARISON_FAMILIES: tuple[ComparisonFamily, ...] = (
    ComparisonFamily("network", "4_NetworkActivity", "4B_GroupComparisons", True),
    ComparisonFamily("ephys_activity", "2_NeuronalActivity", "2B_GroupComparisons", False),
)

#: ``split`` → the ``x_kind`` passed to ``plot_half_violin_by_x`` and the
#: filename stem the pipeline uses. ``group`` gives one panel per group with age
#: along x; ``age`` gives one panel per age with group along x.
COMPARISON_SPLITS: dict[str, tuple[str, str]] = {
    "group": ("group", "byGroup"),
    "age": ("DIV", "byDIV"),
}

COMPARISON_LEVELS = ("recording", "node")

#: ``(level, split)`` → the folder the pipeline writes that combination to.
_COMPARISON_DIRS: dict[tuple[str, str], str] = {
    ("recording", "group"): "3_RecordingsByGroup/HalfViolinPlots",
    ("node", "group"): "1_NodeByGroup",
    ("recording", "age"): "4_RecordingsByAge/HalfViolinPlots",
    ("node", "age"): "2_NodeByAge",
}


def comparison_family(key: str) -> ComparisonFamily:
    """Look up a comparison family, or say which ones exist."""
    fam = next((f for f in COMPARISON_FAMILIES if f.key == key), None)
    if fam is None:
        raise ValueError(
            f"Unknown comparison family {key!r}; expected one of "
            f"{[f.key for f in COMPARISON_FAMILIES]}")
    return fam


def comparison_metrics(family: str, level: str) -> dict[str, str]:
    """Metric key → axis label, for one family and level.

    These are the same maps the pipeline plots from, so the list a viewer offers
    and the figures it can actually draw are one thing.
    """
    from meanap.pipeline.plotting_step2 import EPHYS_NODE_METRICS, EPHYS_REC_METRICS
    from meanap.pipeline.plotting_step4 import NETMET_NODE_METRICS, NETMET_REC_METRICS

    comparison_family(family)
    if level not in COMPARISON_LEVELS:
        raise ValueError(f"Unknown level {level!r}; expected one of {list(COMPARISON_LEVELS)}")
    by_level = {
        ("network", "recording"): NETMET_REC_METRICS,
        ("network", "node"): NETMET_NODE_METRICS,
        ("ephys_activity", "recording"): EPHYS_REC_METRICS,
        ("ephys_activity", "node"): EPHYS_NODE_METRICS,
    }
    return dict(by_level[(family, level)])


def _comparison_frames(ctx: RenderContext, family: str, order: list | None):
    """``(df_rec, df_node)`` for a family, built once and cached on the context.

    Rebuilding these means walking every recording's metrics again, which is
    most of the cost of drawing a single comparison figure — and a viewer draws
    a great many of them against the same bundle.
    """
    cache = getattr(ctx, "_comparison_frames_cache", None)
    if cache is None:
        cache = {}
        object.__setattr__(ctx, "_comparison_frames_cache", cache)
    key = (family, tuple(order) if order else None)
    if key in cache:
        return cache[key]

    if family == "network":
        from meanap.pipeline.plotting_step4 import netmet_comparison_frames
        frames = netmet_comparison_frames(
            list(ctx.recordings.values()), ctx.results, order)
    else:
        from meanap.pipeline.plotting_step2 import ephys_comparison_frames
        frames = ephys_comparison_frames(
            list(ctx.recordings.values()), _ephys_stats(ctx), order)
    cache[key] = frames
    return frames


@dataclass(frozen=True)
class Choice:
    """One selectable value on a facet, and how to name it in a UI."""

    key: str
    label: str


@dataclass(frozen=True)
class LevelAxis(Choice):
    """A level (recording or node) and the metrics it can plot."""

    metrics: tuple[Choice, ...] = ()


@dataclass(frozen=True)
class ComparisonAxes:
    """Everything selectable for one comparison family.

    This is what turns a wall of small multiples into a set of controls: the
    facets are the address :func:`render_comparison_figure` takes, enumerated
    for the run in hand rather than assumed.
    """

    family: str
    label: str
    #: Empty for a family whose figures don't depend on the STTC lag.
    lags: tuple[int, ...]
    levels: tuple[LevelAxis, ...]
    splits: tuple[Choice, ...]


_LEVEL_LABELS = {"recording": "Recording level", "node": "Node level"}
_SPLIT_LABELS = {"group": "By group", "age": "By age"}


def available_comparison_families(ctx: RenderContext) -> list[ComparisonFamily]:
    """Which comparison families this run has the numbers for.

    The same availability test :func:`available_group_families` applies — a
    family with no data behind it must not be offered as a tab that renders
    nothing.
    """
    out = []
    for fam in COMPARISON_FAMILIES:
        if fam.key == "network" and ctx.results:
            out.append(fam)
        elif fam.key == "ephys_activity" and _ephys_stats(ctx):
            out.append(fam)
    return out


def comparison_axes(ctx: RenderContext, family: str) -> ComparisonAxes:
    """The facets a viewer should offer for *family*, for this run.

    Every metric the family defines is listed, present in the data or not,
    because the pipeline writes a figure for each either way — an absent metric
    gets the same "no data" placeholder here that it gets in the output folder.
    A *level* with no rows at all is dropped, since nothing there can be drawn.
    """
    fam = comparison_family(family)
    label = next((f.label for f in GROUP_FAMILIES if f.key == family), family)
    frames = dict(zip(COMPARISON_LEVELS, _comparison_frames(
        ctx, family, ctx.params.custom_grp_order or None)))

    levels = tuple(
        LevelAxis(
            key=level, label=_LEVEL_LABELS[level],
            metrics=tuple(Choice(key=k, label=v)
                          for k, v in comparison_metrics(family, level).items()),
        )
        for level in COMPARISON_LEVELS if not frames[level].empty
    )
    return ComparisonAxes(
        family=family, label=label,
        lags=tuple(comparison_lags(ctx, family)),
        levels=levels,
        splits=tuple(Choice(key=k, label=_SPLIT_LABELS[k]) for k in COMPARISON_SPLITS),
    )


def comparison_lags(ctx: RenderContext, family: str = "network") -> list[int]:
    """The lags this family's figures exist at, in ms. Empty for a lagless family."""
    from meanap.pipeline.plotting_step4 import _lag_num

    fam = comparison_family(family)
    if not fam.has_lag:
        return []
    df_rec, _ = _comparison_frames(ctx, family, None)
    if df_rec.empty or "Lag" not in df_rec.columns:
        return []
    return sorted({_lag_num(v) for v in df_rec["Lag"].unique()})


def render_comparison_figure(
    ctx: RenderContext,
    family: str,
    level: str,
    split: str,
    metric: str,
    out_dir: Path | str,
    *,
    lag: int | None = None,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> Path:
    """Redraw one comparison figure and return the file written.

    The address is ``(family, level, split, lag, metric)``: which comparison set
    (4B network metrics or 2B neuronal activity), whether the points are
    recordings or nodes, whether groups or ages are the panels, which STTC lag,
    and which metric.

    The file is written to the same relative path, under the same name, that
    :func:`render_group_family` would have written it to — so the two paths are
    directly comparable, and the pixel-parity test can hold them to it.

    Raises :class:`ValueError` on any address the bundle cannot draw, naming
    what is available instead.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.plotting_step4 import _lag_num, plot_half_violin_by_x

    fam = comparison_family(family)
    if split not in COMPARISON_SPLITS:
        raise ValueError(
            f"Unknown split {split!r}; expected one of {list(COMPARISON_SPLITS)}")
    metrics = comparison_metrics(family, level)  # also validates level
    if metric not in metrics:
        raise ValueError(
            f"Unknown {level}-level metric {metric!r} for the {family} family. "
            f"Use comparison_metrics() to list them.")

    # Everything decidable from the address alone is settled before any data is
    # touched, so a malformed request gets the error about the request rather
    # than one about the bundle being empty.
    if not fam.has_lag and lag is not None:
        raise ValueError(
            f"The {family} comparison figures do not depend on the STTC lag, so "
            f"lag={lag} has no meaning here; omit it.")

    params, _ = _apply_overrides(ctx.params, overrides)
    order = params.custom_grp_order or None
    df_rec, df_node = _comparison_frames(ctx, family, order)
    df = df_rec if level == "recording" else df_node
    if df.empty:
        raise ValueError(
            f"This bundle has no {level}-level data for the {family} comparison "
            f"family, so there is nothing to draw.")

    x_kind, stem = COMPARISON_SPLITS[split]
    dest_dir = Path(out_dir) / fam.out_subdir / fam.comparisons_dir / _COMPARISON_DIRS[
        (level, split)]

    if fam.has_lag:
        available = sorted({_lag_num(v) for v in df["Lag"].unique()})
        if lag is None:
            raise ValueError(
                f"The {family} comparison figures are per-lag; pass one of "
                f"{available} ms.")
        if lag not in available:
            raise ValueError(
                f"No {family} results at {lag} ms lag; this run has {available} ms.")
        df = df[df["Lag"].map(_lag_num) == lag]
        dest_dir = dest_dir / f"Lag{lag}ms"

    suffix = "_node" if level == "node" else ""
    dest = dest_dir / f"{metric}_{stem}{suffix}.{fmt}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with figure_dpi(dpi):
        plot_half_violin_by_x(df, metric, metrics[metric], x_kind, dest,
                              group_order=order, colors=ColorScheme.from_params(params))

    if not dest.is_file():
        raise ValueError(
            f"Nothing was drawn for {metric} ({level}, by {split}) — the "
            f"selection matched no recordings.")
    return dest


# ── Across-lag figures ────────────────────────────────────────────────────────
#
# Two sets whose subject is the lag itself rather than a slice at one lag, so
# neither belongs under the comparison facets: graph metrics *against* lag (one
# figure per metric), and cartography role proportions per lag (one per lag).


@dataclass(frozen=True)
class LagSeries:
    """An across-lag figure set: what it is keyed by, and where it lands."""

    key: str
    label: str
    out_subdir: str
    #: What one figure is addressed by — a metric name, or a lag in ms.
    keyed_by: str


LAG_SERIES: tuple[LagSeries, ...] = (
    LagSeries("graph_metrics", "Graph metrics by lag",
              "4_NetworkActivity/4B_GroupComparisons/5_GraphMetricsByLag", "metric"),
    LagSeries("cartography", "Node cartography by lag",
              "4_NetworkActivity/4B_GroupComparisons/6_NodeCartographyByLag", "lag"),
)


def lag_series(key: str) -> LagSeries:
    """Look up an across-lag set, or say which ones exist."""
    series = next((s for s in LAG_SERIES if s.key == key), None)
    if series is None:
        raise ValueError(
            f"Unknown across-lag set {key!r}; expected one of "
            f"{[s.key for s in LAG_SERIES]}")
    return series


def available_lag_series(ctx: RenderContext) -> list[tuple[LagSeries, tuple[Choice, ...]]]:
    """The across-lag sets this run can draw, each with its selectable keys.

    Both need more than one lag to say anything, and cartography additionally
    needs the ``NCpn1``-``NCpn6`` role proportions, which a run without node
    cartography does not have. Offering either without its inputs would be a
    control that renders an empty page.
    """
    lags = comparison_lags(ctx, "network")
    if len(lags) < 2:
        return []
    df_rec, _ = _comparison_frames(ctx, "network", ctx.params.custom_grp_order or None)
    out = []
    for series in LAG_SERIES:
        if series.keyed_by == "metric":
            present = [Choice(key=k, label=v)
                       for k, v in comparison_metrics("network", "recording").items()
                       if k in df_rec.columns and df_rec[k].notna().any()]
        else:
            has_roles = all(f"NCpn{i}" in df_rec.columns for i in range(1, 7))
            present = ([Choice(key=str(lag), label=f"{lag} ms") for lag in lags]
                       if has_roles else [])
        if present:
            out.append((series, tuple(present)))
    return out


def render_lag_series_figure(
    ctx: RenderContext,
    series: str,
    key: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> Path:
    """Redraw one across-lag figure — a metric's lag curve, or one lag's roles.

    Written to the same relative path and name the pipeline uses, as
    :func:`render_comparison_figure` is.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.plotting_step4 import (
        plot_graph_metrics_by_lag, plot_node_cartography_by_lag,
    )

    spec = lag_series(series)
    params, _ = _apply_overrides(ctx.params, overrides)
    order = params.custom_grp_order or None
    scheme = ColorScheme.from_params(params)
    df_rec, _ = _comparison_frames(ctx, "network", order)
    if df_rec.empty:
        raise ValueError("This bundle has no network metrics, so there is nothing "
                         "to plot against lag.")

    dest_dir = Path(out_dir) / spec.out_subdir
    with figure_dpi(dpi):
        if spec.keyed_by == "metric":
            if key not in comparison_metrics("network", "recording"):
                raise ValueError(
                    f"Unknown recording-level metric {key!r}. Use "
                    f"available_lag_series() to list what this run can plot.")
            written = plot_graph_metrics_by_lag(
                df_rec, dest_dir, group_order=order, only=key, fmt=fmt,
                colors=scheme, timescale=timescale_kind(params))
        else:
            try:
                lag = int(key)
            except (TypeError, ValueError):
                raise ValueError(
                    f"The {series} set is keyed by lag in ms; {key!r} is not a "
                    f"number.") from None
            available = comparison_lags(ctx, "network")
            if lag not in available:
                raise ValueError(
                    f"No results at {lag} ms lag; this run has {available} ms.")
            written = plot_node_cartography_by_lag(
                df_rec, dest_dir, group_order=order, only=lag, fmt=fmt)

    if not written:
        raise ValueError(
            f"Nothing was drawn for {key!r} in the {series} set — this run has no "
            f"finite values for it.")
    return written[0]


def cached_lag_series_figure(
    ctx: RenderContext,
    cache,
    series: str,
    key: str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> tuple[Path, bool]:
    """One across-lag figure, rendered once per address and cached."""
    from meanap.pipeline.render_cache import bundle_identity, cache_key

    cache_id = cache_key(bundle_identity(ctx.root), f"lag:{series}:{key}",
                         fmt=fmt, dpi=dpi, overrides=overrides)
    files, was_cached = cache.get_or_render(
        cache_id,
        lambda dest: [render_lag_series_figure(
            ctx, series, key, dest, fmt=fmt, dpi=dpi, overrides=overrides)],
    )
    return files[0], was_cached


def cached_comparison_figure(
    ctx: RenderContext,
    cache,
    family: str,
    level: str,
    split: str,
    metric: str,
    *,
    lag: int | None = None,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> tuple[Path, bool]:
    """One comparison figure, rendered once per address and cached.

    Returns ``(path, was_cached)``, like :func:`cached_figure`.
    """
    from meanap.pipeline.render_cache import bundle_identity, cache_key

    key = cache_key(bundle_identity(ctx.root),
                    f"cmp:{family}:{level}:{split}:{lag}:{metric}",
                    fmt=fmt, dpi=dpi, overrides=overrides)
    files, was_cached = cache.get_or_render(
        key,
        lambda dest: [render_comparison_figure(
            ctx, family, level, split, metric, dest,
            lag=lag, fmt=fmt, dpi=dpi, overrides=overrides)],
    )
    return files[0], was_cached


def cached_figure(
    ctx: RenderContext,
    cache,
    recording: str,
    lag: int,
    figure: str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
    variant: str = "plain",
) -> tuple[Path, bool]:
    """One figure, rendered once per (figure, variant, style, format) and cached.

    Returns ``(path, was_cached)``. Single figures are ~0.1 s so the cache
    matters less than it does for a family, but flicking back and forth between
    two plots is the commonest thing a reader does, and it should be instant.
    """
    from meanap.pipeline.render_cache import bundle_identity, cache_key

    # The variant is part of the key, or switching the scaling toggle would
    # serve back whichever version was rendered first.
    key = cache_key(bundle_identity(ctx.root),
                    f"fig:{recording}:{lag}:{figure}:{variant}",
                    fmt=fmt, dpi=dpi, overrides=overrides)
    files, was_cached = cache.get_or_render(
        key,
        lambda dest: [render_figure(ctx, recording, lag, figure, dest,
                                    fmt=fmt, dpi=dpi, overrides=overrides,
                                    variant=variant)],
    )
    return files[0], was_cached


def gallery(
    ctx: RenderContext,
    family: str,
    cache,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> tuple[list[Path], bool]:
    """A family's figures, rendered once and served from *cache* thereafter.

    Returns ``(files, was_cached)``. This is what a viewer should call to show
    a family: the first request pays the render (about six seconds for the
    109-figure network family at thumbnail resolution), every later one is a
    directory listing.

    ``dpi`` defaults to :data:`~meanap.pipeline.figure_output.DEFAULT_THUMBNAIL_DPI`
    because the caller is a gallery; pass ``dpi=None`` explicitly via
    :func:`render_group_family` when you want the authored resolution.
    """
    from meanap.pipeline.figure_output import DEFAULT_THUMBNAIL_DPI
    from meanap.pipeline.render_cache import bundle_identity, cache_key

    if dpi is None:
        dpi = DEFAULT_THUMBNAIL_DPI
    key = cache_key(bundle_identity(ctx.root), family,
                    fmt=fmt, dpi=dpi, overrides=overrides)
    return cache.get_or_render(
        key,
        lambda dest: render_group_family(
            ctx, family, dest, fmt=fmt, dpi=dpi, overrides=overrides),
    )


def available_activity_figures(ctx: RenderContext, recording: str) -> list[FigureSpec]:
    """Which step-2 activity figures this recording can produce.

    Empty when the bundle has no spike times for it — the raster and the
    burst-detection detail are drawn from spike times, not from the summary
    metrics, so without them there is nothing to redraw.
    """
    ephys = _ephys_stats(ctx).get(recording)
    if not ephys or _spike_file(ctx, recording) is None:
        return []
    return [spec for spec in ACTIVITY_FIGURES
            if spec.requires is None or spec.requires in ephys]


def _spike_file(ctx: RenderContext, recording: str) -> Path | None:
    from meanap.pipeline.resume import SPIKE_SUBDIR

    path = ctx.root / SPIKE_SUBDIR / f"{recording}_spikes.npz"
    return path if path.exists() else None


def _spike_check_file(ctx: RenderContext, recording: str) -> Path | None:
    from meanap.pipeline.plotting import CHECKS_SUFFIX
    from meanap.pipeline.resume import SPIKE_SUBDIR

    path = ctx.root / SPIKE_SUBDIR / f"{recording}{CHECKS_SUFFIX}"
    return path if path.exists() else None


def available_spike_check_figures(
    ctx: RenderContext, recording: str,
) -> list[FigureSpec]:
    """Which step-1 check figures this recording can produce.

    Empty for a run that predates the stored payload, or one whose step 1 was
    skipped — in both cases there is nothing to draw from, and offering a button
    that produces nothing is worse than offering none.
    """
    if _spike_check_file(ctx, recording) is None:
        return []
    return list(SPIKE_CHECK_FIGURES)


#: The per-recording cell-type subnetwork figures, per lag. Everything they
#: need was already in the bundle — the adjacency subgraph, the coordinates and
#: the resolved groups in the state file, the three tables as CSVs — so unlike
#: the step-1 and step-3 checks this needed no new payload, only wiring.
SUBNETWORK_FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec("1_CellTypeNetwork", "Network coloured by cell type"),
    FigureSpec("2_SubnetworkGraphs", "Each cell type's subnetwork"),
    FigureSpec("3_NodeMetricsByCellType", "Node metrics by cell type"),
    FigureSpec("4_SubnetworkMetrics", "Metrics of each subnetwork"),
    FigureSpec("5_EdgeMixing", "Connectivity within and between cell types"),
)


def _subnetwork_tables(ctx: RenderContext) -> dict[str, "object"]:
    """The three subnetwork CSVs as DataFrames, loaded once and cached."""
    import pandas as pd

    cached = getattr(ctx, "_subnet_tables_cache", None)
    if cached is not None:
        return cached
    out = {}
    for key, name in (("summary", "Subnetwork_RecordingLevel.csv"),
                      ("node", "Subnetwork_NodeLevel.csv"),
                      ("mix", "Subnetwork_EdgeMix.csv")):
        path = ctx.root / "4_NetworkActivity" / name
        out[key] = pd.read_csv(path) if path.exists() else pd.DataFrame()
    object.__setattr__(ctx, "_subnet_tables_cache", out)
    return out


def _subnetwork_slice(ctx: RenderContext, recording: str, lag: int) -> dict:
    """Each table cut down to one recording and lag, as the plotters expect.

    The pipeline hands the plotters exactly this slice; the CSVs are the same
    rows with ``FileName``/``Lag`` columns added, so cutting on those puts them
    back the way they were.
    """
    lag_key = f"{lag}mslag"
    out = {}
    for key, table in _subnetwork_tables(ctx).items():
        if table.empty:
            out[key] = table
            continue
        rows = table[(table["FileName"] == recording) & (table["Lag"] == lag_key)]
        out[key] = rows.drop(columns=[c for c in ("FileName", "Grp", "DIV", "Lag")
                                      if c in rows.columns]).reset_index(drop=True)
    return out


#: Where a CAT-NAP run writes its per-unit trace figures. Unlike every other
#: family the viewer serves, these are *carried* in the bundle rather than
#: redrawn from it: they need the full fluorescence matrices, which are
#: hundreds of MB per recording and deliberately not stored. So the viewer's
#: job here is to find the packed images, not to render anything.
TRACE_DIR = "2_NeuronalActivity/2A_IndividualNeuronalAnalysis"


def available_trace_figures(ctx: RenderContext, recording: str) -> list[FigureSpec]:
    """The per-unit peak-detection figures packed for this recording.

    A CAT-NAP run with ``num_2p_traces > 0`` saves a three-panel figure per
    unit — raw F, scaled F over the denoised trace, and the denoised trace with
    detected event starts — and ``write_bundle`` packs them verbatim. Nothing
    listed them, so a bundle could carry the only record of what peak detection
    did and show the reader no sign of it.

    Sorted by the unit number in the filename rather than lexically, so unit 9
    precedes unit 10.
    """
    base = ctx.root / TRACE_DIR
    if not base.is_dir():
        return []
    # group/recording/, matching what _plot_recording writes.
    hits = sorted(base.glob(f"*/{recording}/*.png"))
    if not hits:
        return []

    def unit_of(path: Path) -> tuple[int, str]:
        digits = "".join(c if c.isdigit() else " " for c in path.stem).split()
        return (int(digits[0]) if digits else 1 << 30, path.stem)

    return [FigureSpec(h.stem, f"Unit {unit_of(h)[0]}" if unit_of(h)[0] < (1 << 30)
                       else h.stem)
            for h in sorted(hits, key=unit_of)]


def trace_figure_path(ctx: RenderContext, recording: str, name: str) -> Path:
    """Locate one packed trace figure, refusing anything outside the bundle.

    ``name`` arrives from a URL, so it is matched against the discovered set
    rather than joined onto a path — a traversal here would read arbitrary
    files off the machine running the viewer.
    """
    base = (ctx.root / TRACE_DIR).resolve()
    for hit in base.glob(f"*/{recording}/*.png"):
        if hit.stem == name:
            resolved = hit.resolve()
            if not resolved.is_relative_to(base):
                break
            return resolved
    raise FileNotFoundError(f"no trace figure {name!r} for {recording}")


def available_subnetwork_figures(
    ctx: RenderContext, recording: str, lag: int,
) -> list[FigureSpec]:
    """Which cell-type subnetwork figures this recording/lag can produce.

    Empty unless the run did the subnetwork analysis *and* the recording ended
    up with groups — a spreadsheet that labelled none of its cells produces
    tables with no rows for it, and there is nothing to draw.
    """
    metrics = ctx.results.get(recording, {}).get(f"{lag}mslag")
    if not metrics or "adjMsub" not in metrics:
        return []
    # _states holds (state, stats) pairs.
    stored = _states(ctx).get(recording)
    if stored is None or getattr(stored[0].groups, "n_groups", 0) == 0:
        return []

    tables = _subnetwork_slice(ctx, recording, lag)
    available = []
    for spec in SUBNETWORK_FIGURES:
        needs = {"3_NodeMetricsByCellType": "node",
                 "4_SubnetworkMetrics": "summary",
                 "5_EdgeMixing": "mix"}.get(spec.name)
        if needs is None or not tables[needs].empty:
            available.append(spec)
    return available


def render_subnetwork_figure(
    ctx: RenderContext,
    recording: str,
    lag: int,
    figure: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
) -> Path:
    """Redraw one per-recording cell-type subnetwork figure from the bundle."""
    from meanap.catnap import subnetwork_plotting as snp
    from meanap.catnap.pipeline import _SUBNET_GRAPH_METRICS, _SUBNET_NODE_METRICS
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.rng import make_rng

    if figure not in {spec.name for spec in
                      available_subnetwork_figures(ctx, recording, lag)}:
        raise ValueError(
            f"'{figure}' is not one of the cell-type subnetwork figures for "
            f"{recording} at {lag} ms lag. These exist only for runs with the "
            "subnetwork analysis enabled; use available_subnetwork_figures() "
            "to list what is here.")

    metrics = ctx.results[recording][f"{lag}mslag"]
    state, _stats = _states(ctx)[recording]
    active = np.asarray(metrics["activeChannelIndex"], dtype=int)
    active_groups = state.groups.subset(active)
    coords_active = np.asarray(state.coords)[active]
    adj_sub = metrics["adjMsub"]
    tables = _subnetwork_slice(ctx, recording, lag)

    rec = ctx.recordings.get(recording) or RecordingInfo(
        filename=recording, div=0.0, group="")
    title = f"{recording}  {lag} ms lag"
    out_path = Path(out_dir) / f"{figure}.{fmt}"

    draw = {
        "1_CellTypeNetwork": lambda: snp.plot_subnetwork_spatial(
            adj_sub, coords_active, active_groups, out_path, title),
        "2_SubnetworkGraphs": lambda: snp.plot_subnetwork_panels(
            adj_sub, coords_active, active_groups, out_path, title),
        "3_NodeMetricsByCellType": lambda: snp.plot_node_metrics_by_group(
            tables["node"], _SUBNET_NODE_METRICS, out_path,
            f"{title} — whole-network node metrics by cell type",
            # The same dedicated stream the pipeline draws with, so the
            # jittered points land where they landed in the run's own figure.
            make_rng(ctx.params.random_seed, "catnap_subnetwork_plot",
                     recording, f"{lag}mslag")),
        "4_SubnetworkMetrics": lambda: snp.plot_subnetwork_metric_bars(
            tables["summary"], _SUBNET_GRAPH_METRICS, out_path,
            f"{title} — metrics of each cell-type subnetwork"),
        "5_EdgeMixing": lambda: snp.plot_edge_mix_matrix(
            tables["mix"], active_groups, out_path,
            f"{title} — connectivity within/between cell types"),
    }[figure]

    with figure_dpi(dpi):
        draw()
    if not out_path.exists():
        raise ValueError(
            f"'{figure}' produced nothing for {recording} at {lag} ms lag — "
            "its table is present but empty of anything plottable.")
    return out_path


def render_subnetwork_figure_set(
    ctx: RenderContext,
    recording: str,
    lag: int,
    out_root: Path | str,
    *,
    fmt: str = "png",
) -> list[Path]:
    """Redraw the whole 4A figure set once per cell-type subnetwork.

    The one family here that has to *recompute* rather than reassemble: the
    per-subnetwork metrics are not stored (only their summary rows are), so
    :func:`~meanap.catnap.subnetwork.compute_subnetwork_metrics` is re-run from
    the adjacency, spike counts and groups the state file carries. That is
    stochastic, so it reproduces the run's own figures only for a seeded run —
    with ``random_seed=None`` the numbers will be close but not identical, which
    is true of re-running the pipeline itself.

    *out_root* is the run's ``4_NetworkActivity`` folder, as the pipeline passes.
    """
    from meanap.catnap.pipeline import _plot_subnetwork_figure_set
    from meanap.catnap.store import load_background
    from meanap.catnap.subnetwork import compute_subnetwork_metrics
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.rng import make_rng

    lag_key = f"{lag}mslag"
    metrics = ctx.results.get(recording, {}).get(lag_key)
    stored = _states(ctx).get(recording)
    if not metrics or stored is None or getattr(stored[0].groups, "n_groups", 0) == 0:
        return []
    state = stored[0]

    adj_full = state.adjMs.get(f"adjM{lag}mslag")
    if adj_full is None:
        return []

    rec = ctx.recordings.get(recording) or RecordingInfo(
        filename=recording, div=0.0, group="")
    results = compute_subnetwork_metrics(
        adj_full, state.spike_counts, state.duration_s, state.groups, ctx.params,
        min_nodes=ctx.params.min_number_of_nodes_to_cal_net_met,
        rng=make_rng(ctx.params.random_seed, "catnap_subnetwork", recording),
        full_metrics=metrics,
    )

    background = None
    bg_path = _background_path(ctx, recording)
    if bg_path is not None:
        background = load_background(bg_path)

    out_root = Path(out_root)
    before = set(out_root.rglob(f"*.{fmt}")) if out_root.exists() else set()
    with figure_dpi(None):
        _plot_subnetwork_figure_set(
            ctx.params, rec, state, results, metrics, lag, out_root,
            lambda m: None, background)
    return sorted(p for p in out_root.rglob(f"*.{fmt}") if p not in before)


def _edge_check_file(ctx: RenderContext, recording: str) -> Path | None:
    from meanap.pipeline.plotting_step3 import EDGE_CHECK_SUFFIX

    path = ctx.root / "ExperimentMatFiles" / f"{recording}{EDGE_CHECK_SUFFIX}"
    return path if path.exists() else None


def available_edge_check_lags(ctx: RenderContext, recording: str) -> list[int]:
    """Lags whose edge-threshold stability check this bundle can redraw.

    Empty unless the run had ``prob_thresh_plot_checks`` on — the snapshots this
    is built from cost a full extra pass over the surrogates, so they are only
    collected when asked for.
    """
    from meanap.pipeline.plotting_step3 import stored_lags

    path = _edge_check_file(ctx, recording)
    return stored_lags(path) if path is not None else []


def render_edge_check_figure(
    ctx: RenderContext,
    recording: str,
    lag: int,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
) -> Path:
    """Redraw one edge-threshold stability check from the bundle.

    No style overrides: the figure is a record of how the thresholding settled,
    and none of the network styling controls apply to it.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.plotting_step3 import (
        draw_edge_threshold_check, load_edge_threshold_check,
    )

    path = _edge_check_file(ctx, recording)
    data = load_edge_threshold_check(path, lag) if path is not None else None
    if data is None:
        raise ValueError(
            f"No edge-threshold check for {recording} at {lag}ms in this bundle. "
            "These are only produced when the run had 'plot thresholding checks' "
            "enabled; use available_edge_check_lags() to list what is here.")

    out_path = Path(out_dir) / f"{recording}{lag}msLagProbThreshCheck.{fmt}"
    with figure_dpi(dpi):
        draw_edge_threshold_check(data, out_path)
    return out_path


def render_spike_check_figure(
    ctx: RenderContext,
    recording: str,
    figure: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
) -> Path:
    """Redraw one step-1 check figure from the bundle.

    Takes no style overrides: these are a record of what spike detection did,
    and their axes are fixed to the recording's own noise level rather than to
    anything a viewer should be re-scaling.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.plotting import (
        draw_spike_check_figures, load_spike_check_data,
    )

    path = _spike_check_file(ctx, recording)
    if path is None:
        raise ValueError(
            f"No spike-detection check data for {recording} in this bundle — it "
            "comes from step 1, which this run either skipped or predates.")

    with figure_dpi(dpi):
        written = draw_spike_check_figures(
            load_spike_check_data(path), Path(out_dir), fmt=fmt, only=figure)
    if not written:
        raise ValueError(
            f"'{figure}' is not one of the spike-detection check figures for "
            f"{recording}. Use available_spike_check_figures() to list them.")
    return written[0]


def _activity_batch_max(ctx: RenderContext) -> dict:
    """Pooled per-channel maxima, recomputed exactly as step 2 does.

    These set the shared colour ceiling for the batch-scaled heatmap panels, so
    getting them from the whole batch rather than one recording is what keeps a
    rebuilt heatmap identical to the pipeline's.
    """
    stats = _ephys_stats(ctx)
    out: dict = {}
    for metric in _ACTIVITY_BATCH_METRICS:
        maxes = [
            float(np.nanmax(e[metric]))
            for e in stats.values()
            if e.get(metric) is not None and np.size(e[metric]) > 0
            and np.any(np.isfinite(e[metric]))
        ]
        out[metric] = max(maxes) if maxes else None
    return out


def render_activity_figure(
    ctx: RenderContext,
    recording: str,
    figure: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> Path:
    """Redraw one step-2 activity figure from the bundle.

    Same contract as :func:`render_figure`, for the other per-recording family:
    it calls ``plot_neuronal_activity_checks`` — the function the pipeline
    calls — with the spike times and metrics reassembled from the bundle.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.pipeline.io import load_spike_times_npz
    from meanap.pipeline.plotting_step2 import plot_neuronal_activity_checks
    from meanap.pipeline.spreadsheet import ground_spike_times_dict, parse_ground_electrodes

    ephys = _ephys_stats(ctx).get(recording)
    spike_path = _spike_file(ctx, recording)
    if not ephys or spike_path is None:
        raise ValueError(
            f"No step-2 activity data for {recording} in this bundle — it needs "
            "both ephys_results.json and the spike times.")

    params, _ = _apply_overrides(ctx.params, overrides)
    rec = ctx.recordings.get(recording) or RecordingInfo(
        filename=recording, div=0.0, group="")

    data = np.load(spike_path)
    fs = float(data["fs"][0])
    channels = data["channels"]
    n_channels = len(channels)
    duration_s = float(data["duration_s"][0]) if "duration_s" in data else None
    if duration_s is None:
        raise ValueError(
            f"{spike_path.name} has no stored duration; it predates express mode "
            "and the raster cannot be scaled without it.")

    # Same spike-time selection step 2 makes, including grounding — a grounded
    # electrode must stay empty in the raster.
    full = load_spike_times_npz(spike_path)
    spike_times_dict = {
        ch: full.get(ch, {}).get(params.spikes_method, np.array([]))
        for ch in range(n_channels)
    }
    ground = parse_ground_electrodes(rec.ground)
    if ground:
        spike_times_dict = ground_spike_times_dict(spike_times_dict, channels, ground)

    batch_max = _activity_batch_max(ctx)
    with figure_dpi(dpi):
        written = plot_neuronal_activity_checks(
            rec=rec, params=params, spike_times_dict=spike_times_dict,
            n_channels=n_channels, chs=channels, fs=fs, duration_s=duration_s,
            ephys=ephys, output_root=Path(out_dir),
            spike_freq_max=batch_max.get("FR"), batch_max=batch_max,
            fmt=fmt, only=figure,
        )
    if not written:
        raise ValueError(
            f"'{figure}' is not one of the activity figures available for "
            f"{recording}. Use available_activity_figures() to list them.")
    return written[0]


def _recording_arrays(ctx: RenderContext, recording: str):
    """``(channels, coords, markers)`` for one recording, from its state file.

    ``coords`` is ``None`` on the electrophysiology path: node positions there
    come from the MEA channel layout, which the plotters derive from
    ``params.channel_layout`` and the channel list, so storing them would be
    redundant.
    """
    path = _state_file(ctx.root, recording)
    if path is None:
        raise ValueError(f"No stored state for {recording} in {ctx.root}")
    with np.load(path) as data:
        channels = np.asarray(data["channels"])
        coords = np.asarray(data["coords"]) if "coords" in data.files else None
        markers = None
        if "marker_matrix" in data.files:
            markers = (np.asarray(data["marker_matrix"]),
                       [str(n) for n in data["marker_names"]])
    return channels, coords, markers


# ── Step 5: statistics and machine learning ──────────────────────────────────
#
# Unlike every other family here, these figures are not redrawn from the
# pipeline's own state files. They are redrawn from the tables the statistics
# step wrote beside them, which a bundle carries in full while dropping the
# pictures (see meanap.pipeline.bundle's _DATA_ONLY_DIRS). Every figure is a
# pure function of those tables, verified byte-for-byte in test_stats_report.py,
# so a viewer can offer the whole set without re-running a decoder.

STATS_DIRNAME = "5_StatsAndML"


def _stats_root(ctx: RenderContext) -> Path:
    return Path(ctx.root) / STATS_DIRNAME


def available_stats_lags(ctx: RenderContext) -> list[str]:
    """Lag folders the statistics step wrote, or ``[]`` if it was never run.

    Names rather than integers: the step's folders are named after the run's
    own lag labels (``1000mslag``, or ``all`` for a run with no lag axis), and
    a correlation-binned CAT-NAP run has labels that are not lags at all.
    """
    from meanap.stats.figures import available_lags

    return available_lags(_stats_root(ctx))


def stats_results(ctx: RenderContext, lag: str):
    """The stored statistics results for one lag, loaded once per context.

    Cached on the context like :func:`_states`: a viewer answers a figure
    request at a time, and re-reading a run's comparison table for each one
    would dominate the cost of drawing.
    """
    from meanap.stats.dataset import load_dataset
    from meanap.stats.figures import load_results

    cache = getattr(ctx, "_stats_cache", None)
    if cache is None:
        cache = {}
        object.__setattr__(ctx, "_stats_cache", cache)
    if lag in cache:
        return cache[lag]

    folder = _stats_root(ctx) / lag
    if not folder.is_dir():
        cache[lag] = None
        return None
    dataset = load_dataset(ctx.root)
    # "all" is the folder a run with no lag axis writes to; there is nothing to
    # subset by in that case.
    cache[lag] = load_results(
        folder, dataset if lag == "all" else dataset.for_lag(_stats_lag_value(dataset, lag)),
        lag=lag)
    return cache[lag]


def _stats_lag_value(dataset, lag: str):
    """The run's own Lag value matching a statistics folder name.

    The step names its folders after the value verbatim, so this is normally
    the identity; it is a lookup rather than a cast because a folder name has
    had path-unsafe characters replaced and may no longer match exactly.
    """
    for value in dataset.lags:
        if str(value).replace("/", "-").replace(" ", "") == lag:
            return value
    return lag


def available_stats_figures(ctx: RenderContext, lag: str) -> list:
    """The catalogued figures this run's stored results can produce."""
    from meanap.stats.figures import stats_figures

    results = stats_results(ctx, lag)
    return stats_figures(results) if results is not None else []


def render_stats_figure(
    ctx: RenderContext,
    lag: str,
    key: str,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> Path:
    """Redraw one statistics figure into *out_dir*, returning the file written.

    Honours the viewer's group and age colour overrides, so a genotype keeps
    the colour the rest of the session gave it.
    """
    from meanap.pipeline.figure_output import figure_dpi
    from meanap.stats.figures import draw_stats_figure, stats_figures

    results = stats_results(ctx, lag)
    if results is None:
        raise ValueError(
            f"This run has no statistics results for {lag!r}. Run the "
            f"statistics step (meanap-stats, or the Stats & ML tab) over it first.")

    figure = next((f for f in stats_figures(results) if f.key == key), None)
    if figure is None:
        raise ValueError(
            f"Unknown statistics figure {key!r}; expected one of "
            f"{[f.key for f in stats_figures(results)]}")

    params, _ = _apply_overrides(ctx.params, overrides)
    scheme = ColorScheme.from_params(params)
    out_path = Path(out_dir) / f"{figure.filename}.{fmt}"
    with figure_dpi(dpi):
        drawn = draw_stats_figure(results, key, out_path, scheme=scheme)
    if drawn is None:
        raise ValueError(f"Statistics figure {key!r} has no data to draw.")
    return drawn


def cached_stats_figure(
    ctx: RenderContext,
    cache,
    lag: str,
    key: str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> tuple[Path, bool]:
    """One statistics figure, rendered once per address and cached.

    Returns ``(path, was_cached)``, like :func:`cached_figure`.
    """
    from meanap.pipeline.render_cache import bundle_identity, cache_key

    identity = cache_key(bundle_identity(ctx.root), f"stats:{lag}:{key}",
                         fmt=fmt, dpi=dpi, overrides=overrides)
    files, was_cached = cache.get_or_render(
        identity,
        lambda dest: [render_stats_figure(
            ctx, lag, key, dest, fmt=fmt, dpi=dpi, overrides=overrides)],
    )
    return files[0], was_cached
