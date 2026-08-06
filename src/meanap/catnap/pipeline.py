"""CAT-NAP pipeline orchestrator (``Params.suite2pMode == 1`` path).

Mirrors the ``suite2pMode`` branches scattered through ``MEApipeline.m``: for
each suite2p recording it denoises (if needed), builds the adjacency matrices +
activity properties (:func:`~meanap.catnap.adjacency.suite2p_to_adjm`), computes
the two-photon activity stats (:func:`~meanap.catnap.stats.calc_twop_activity_stats`),
and then feeds the **shared** step-4 network-metric routine
(:func:`meanap.pipeline.step4.compute_network_metrics`) — the calcium-imaging
counterpart of running steps 1→4 on electrophysiology data.

Per recording it writes the trace and network figures; across the batch it
writes the JSON/CSVs and the group × age comparison figures
(:mod:`meanap.catnap.group_plots`), mirroring the ``2B_``/``4B_GroupComparisons``
folders the ephys path produces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from meanap.params import Params
from meanap.catnap.adjacency import suite2p_to_adjm
from meanap.catnap.group_plots import (
    SUBNET_GRAPH_METRICS, SUBNET_NODE_METRICS, twop_stats_frames,
)
from meanap.catnap.loader import load_suite2p
from meanap.catnap.subnetwork import WHOLE_NETWORK
from meanap.catnap.stats import calc_twop_activity_stats
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.pipeline.step4 import (
    _apply_cartography_boundaries, _batch_metric_bounds, _convert_numpy,
    _NMF_NON_NODE_KEYS, compute_network_metrics,
)

_NEEDS_DENOISING = ("peaks", "denoised F", "spks")


@dataclass
class _RecordingState:
    """What phase 3 needs about a recording, without its activity matrices.

    ``suite2p_to_adjm`` returns the full ``(n_frames, n_units)`` fluorescence,
    denoised-fluorescence and spks matrices — hundreds of MB per recording, so
    holding them for a whole batch across the cartography barrier is not an
    option. Everything here is small (adjacency matrices are ``n_units²``); the
    trace figures re-read the suite2p folder at ``plane0`` instead.
    """

    adjMs: dict[str, np.ndarray]
    coords: np.ndarray
    channels: np.ndarray
    spike_counts: np.ndarray
    duration_s: float
    plane0: Path
    #: User-defined cell-type groups (E/I, per-marker, …) — drives the
    #: subnetwork analysis and the by-cell-type activity comparisons.
    groups: object | None = None
    #: ``(n_channels, n_markers)`` raw marker membership + names, straight from
    #: the spreadsheet. Distinct from ``groups``: this is the cell's full
    #: genetic identity, drawn as concentric rings on the network plots, and it
    #: is not collapsed into whatever grouping the user chose.
    markers: tuple[np.ndarray, list[str]] | None = None
    #: ``(min, max)`` used to normalise the pixel centroids onto ``coords`` —
    #: needed to map the mean projection image into the same frame.
    coord_norm: tuple[float, float] = (0.0, 1.0)


def suite2p_plane0_dir(raw_data: str, filename: str) -> Path:
    """Location of a recording's suite2p output (mirrors MEApipeline.m)."""
    return Path(raw_data) / filename / "suite2p" / "plane0"


def _spike_counts(res, twop_activity: str) -> np.ndarray:
    """Per-node activity count used for the active-node inclusion test.

    Peaks → number of detected peaks per unit (matches MATLAB's peak-count
    firing rate); other activity types → column sum of the activity matrix
    (``sum(expData.(twopActivity), 1)`` in ``calTwopActivityStats.m``).
    """
    if twop_activity == "peaks":
        return np.array([np.size(st) for st in res.spike_times], dtype=float)
    src = {"F": res.F, "spks": res.spks, "denoised F": res.denoised_F}[twop_activity]
    return np.asarray(src, dtype=float).sum(axis=0)


def _activity_stats_for(res, params: Params, duration_s: float) -> dict:
    ap = res.activity_properties
    kw = dict(
        twop_activity=params.twop_activity,
        duration_s=duration_s,
        fs=res.fs,
        min_activity_level=params.min_activity_level,
    )
    if params.twop_activity == "peaks":
        kw.update(
            spike_times=res.spike_times,
            peak_heights=ap.get("peakHeights"),
            peak_duration_frames=ap.get("peakDurationFrames"),
            event_areas=ap.get("eventAreas"),
        )
    else:
        src = {"F": res.F, "spks": res.spks, "denoised F": res.denoised_F}[params.twop_activity]
        kw.update(activity_matrix=src)
    return calc_twop_activity_stats(**kw)


def run_catnap_pipeline(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None] = print,
    should_cancel: CancelCheck = None,
    rng: np.random.Generator | None = None,
) -> None:
    """Run the CAT-NAP path over all recordings, writing NetMet JSON + CSVs.

    Three phases, mirroring ``step4._run_step4_network_metrics``:

    1. **compute** every recording's adjacency, activity stats and network
       metrics;
    2. **reduce** across the batch — pool participation coefficient and
       within-module z-score to place the node-cartography boundaries where
       the data actually clusters (``autoSetCartographyBoundaries``);
    3. **plot** every recording, then the batch comparisons.

    The barrier matters: cartography roles are re-derived in phase 2, so every
    figure and CSV that shows a role has to be produced after it. Phase 1 keeps
    only a small per-recording state (:class:`_RecordingState`) — the raw
    fluorescence matrices are hundreds of MB per recording and are re-read from
    disk in phase 3 for the trace figures.
    """
    from meanap.catnap.denoising import process_suite2p_folder

    if rng is None:
        rng = np.random.default_rng()

    lag_values = params.func_con_lag_val
    min_nodes = params.min_number_of_nodes_to_cal_net_met
    net_dir = output_root / "4_NetworkActivity"
    net_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, dict] = {}
    all_stats: dict[str, dict] = {}
    all_channels: dict[str, np.ndarray] = {}
    states: dict[str, _RecordingState] = {}
    subnetwork_tables: dict[str, list] = {"summary": [], "node": [], "mix": []}

    # ── Phase 1: compute ──────────────────────────────────────────────────────
    for rec in recordings:
        check_cancel(should_cancel)
        plane0 = suite2p_plane0_dir(params.raw_data, rec.filename)
        if not (plane0 / "stat.npy").exists():
            log(f"  [{rec.filename}] SKIP: no suite2p output at {plane0}")
            continue

        log(f"  [{rec.filename}] loading suite2p data…")
        data = load_suite2p(plane0)

        if params.twop_activity in _NEEDS_DENOISING and (
            data.F_denoised is None or params.twop_redo_denoising
        ):
            log(f"  [{rec.filename}] denoising ({data.F.shape[0]} ROIs)…")
            process_suite2p_folder(
                plane0,
                overwrite=params.twop_redo_denoising,
                denoising_threshold=params.twop_denoising_threshold,
                time_before_peak_s=params.twop_denoising_time_before_peak,
                time_after_peak_s=params.twop_denoising_time_after_peak,
            )
            data = load_suite2p(plane0)

        log(f"  [{rec.filename}] building adjacency matrices…")
        res = suite2p_to_adjm(
            data, params.twop_activity, lag_values,
            remove_nodes_with_no_peaks=params.remove_nodes_with_no_peaks,
            prob_thresh_tail=params.prob_thresh_tail,
            prob_thresh_rep_num=params.prob_thresh_rep_num,
            rng=rng,
        )
        duration_s = res.F.shape[0] / res.fs
        spike_counts = _spike_counts(res, params.twop_activity)

        all_stats[rec.filename] = _activity_stats_for(res, params, duration_s)
        all_channels[rec.filename] = res.channels
        groups, markers = _resolve_cell_types(params, rec, res.channels, log)
        states[rec.filename] = _RecordingState(
            adjMs=res.adjMs, coords=res.coords, channels=res.channels,
            spike_counts=spike_counts, duration_s=duration_s, plane0=plane0,
            groups=groups, markers=markers, coord_norm=res.coord_norm,
        )

        rec_results: dict = {}
        for lag_ms in lag_values:
            key = f"adjM{lag_ms}mslag"
            if key not in res.adjMs:
                continue
            log(f"  [{rec.filename}] network metrics (lag={lag_ms}ms)…")
            metrics = compute_network_metrics(
                res.adjMs[key], spike_counts, duration_s,
                params.min_activity_level, min_nodes,
                exclude_edges_below_threshold=params.exclude_edges_below_threshold,
                params=params, rng=rng,
            )
            rec_results[f"{lag_ms}mslag"] = metrics
        all_results[rec.filename] = rec_results

    # ── Phase 2: reduce — data-driven node-cartography boundaries ─────────────
    # Pool PC/Z over the whole batch and re-place the six role boundaries, then
    # re-classify every node (port of MEApipeline.m's autoSetCartographyBoundaries
    # barrier). Without this the roles come from the fixed Params defaults and
    # almost every node lands in role 1.
    if params.auto_set_cartography_boundaries and all_results:
        check_cancel(should_cancel)
        _apply_cartography_boundaries(params, all_results, log, out_dir=net_dir)

    # Pooled node-metric ranges, so the ``_scaled`` network plots of different
    # recordings share an axis.
    batch_bounds = {m: _batch_metric_bounds(all_results, m)
                    for m in ("ND", "NS", "BC", "PC", "Eloc")}

    # ── Phase 3: plot ─────────────────────────────────────────────────────────
    for rec in recordings:
        state = states.get(rec.filename)
        if state is None:
            continue
        check_cancel(should_cancel)
        # Read once here rather than inside each consumer: the mean projection
        # and the trace figures both need the suite2p folder re-opened, and the
        # subnetwork figures want the same backdrop as the whole-network ones.
        data, background = _reload_for_plots(params, rec, state, log)
        _plot_recording(params, rec, state, all_results[rec.filename],
                        batch_bounds, output_root, log, data, background)

        if params.twop_subnetwork_analysis:
            _run_subnetwork_analysis(
                params, rec, state, all_results[rec.filename],
                min_nodes, output_root, subnetwork_tables, log, rng, background,
            )

    _save_catnap_results(recordings, all_results, all_stats, all_channels, net_dir, log)
    _save_subnetwork_results(subnetwork_tables, net_dir, log)
    _plot_group_comparisons(
        params, recordings, all_results, all_stats, all_channels,
        subnetwork_tables, states, output_root, log,
    )
    log("  CAT-NAP pipeline complete.")


def _mean_image_background(mean_img, coord_norm) -> tuple | None:
    """Map suite2p's mean projection into the node coordinate frame.

    ``coords`` are ``stat['med']`` normalised onto ``[0, 8]`` by
    ``(v - min) / (max - min) * 8`` over the *whole* centroid range, so the
    image needs the same affine to line up with the nodes.

    The axis order is the subtle part. suite2p's ``med`` is ``(row, column)`` —
    verified against the ROIs' own ``ypix``/``xpix`` — but ``suite2pToAdjm.m``
    (and this port, for parity) stores it as if it were ``(x, y)``. So the
    plotted x axis is really the pixel *row* and the plotted y axis the pixel
    *column*, and the image has to be transposed to match. Transposing the
    picture rather than fixing ``coords`` keeps exact parity with MATLAB's
    stored coordinates while still putting each node on its own soma.
    """
    if mean_img is None:
        return None
    img = np.asarray(mean_img, dtype=float)
    if img.ndim != 2 or img.size == 0:
        return None
    min_xy, max_xy = coord_norm
    span = float(max_xy) - float(min_xy)
    if not np.isfinite(span) or span <= 0:
        return None

    def to_coord(v: float) -> float:
        return (v - float(min_xy)) / span * 8.0

    n_rows, n_cols = img.shape
    # x axis ← pixel row, y axis ← pixel column (see above).
    extent = (to_coord(0), to_coord(n_rows - 1), to_coord(0), to_coord(n_cols - 1))
    return img.T, extent


def _resolve_cell_types(params, rec, channels, log):
    """Read a recording's cell-type spreadsheet once, for every consumer of it.

    Returns ``(groups, (marker_matrix, marker_names))``, either of which may be
    ``None`` when no usable spreadsheet is found — cell-type features then
    simply don't appear, and the rest of the run is unaffected.

    The two outputs are deliberately different things. ``groups`` is the
    *user's* grouping (excitatory vs inhibitory, or one group per marker) and
    drives the subnetwork analysis and the by-cell-type comparisons.
    ``marker_matrix`` is the raw spreadsheet membership — every marker,
    uncollapsed — and is what the network plots draw as concentric rings, so a
    node shows its full genetic identity regardless of how it was grouped.
    """
    from meanap.catnap import subnetwork as sn

    try:
        path = (Path(params.twop_cell_type_file) if params.twop_cell_type_file
                else sn.find_cell_type_file(params.raw_data, rec.filename))
        if path is None or not Path(path).exists():
            return None, None
        table = sn.load_cell_type_table(path)
        marker_matrix, marker_names = sn.build_marker_matrix(table, channels)
        groups = sn.resolve_groups(table, channels, params.twop_subnetwork_groups)
    except Exception as e:
        log(f"  [{rec.filename}] warning: could not read cell types: {e}")
        return None, None

    counts = ", ".join(f"{k}={v}" for k, v in groups.counts().items())
    log(f"  [{rec.filename}] cell types from {Path(path).name}: "
        f"{len(marker_names)} markers; groups: {counts or 'none'}")
    markers = (marker_matrix, marker_names) if marker_names else None
    return (groups if groups.n_groups else None), markers


def _reload_for_plots(params, rec, state, log):
    """Re-open the recording's suite2p folder for the plotting phase.

    Phase 1 deliberately drops the fluorescence matrices (hundreds of MB each),
    so the trace figures and the mean-projection backdrop both need the folder
    read again — once, here, rather than per figure family.
    """
    if not (params.num_2p_traces or params.twop_network_background):
        return None, None
    try:
        data = load_suite2p(state.plane0)
    except Exception as e:
        log(f"  [{rec.filename}] warning: could not re-read suite2p data: {e}")
        return None, None

    background = None
    if params.twop_network_background:
        background = _mean_image_background(data.mean_img, state.coord_norm)
        if background is None:
            log(f"  [{rec.filename}] note: no mean projection in ops — "
                "network plots drawn without a backdrop")
    return data, background


def _plot_recording(params, rec, state, rec_results, batch_bounds, output_root, log,
                    data=None, background=None) -> None:
    """Per-unit trace figures + the full step-4A figure set for one recording.

    The network figures are the *shared* ``_plot_recording_lag`` — connectivity
    stats, the five spatial network plots (plus their batch-scaled and combined
    variants), node cartography, the two circular plots and graph-metrics-by-node
    — driven through its ``coords_all`` path so node positions come from suite2p
    cell centroids rather than an MEA electrode grid. Nothing here is duplicated
    from the electrophysiology path.

    Runs after the cartography barrier, so the cartography scatter and the
    circular cartography plot show the batch-derived boundaries and the roles
    that the CSVs report.
    """
    from meanap.catnap.plotting import plot_2p_traces
    from meanap.pipeline.step4 import _plot_recording_lag

    if params.num_2p_traces and data is not None:
        try:
            trace_dir = (output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
                         / rec.group / rec.filename)
            log(f"  [{rec.filename}] plotting 2P traces…")
            plot_2p_traces(data, trace_dir, rec.filename,
                           num_traces=params.num_2p_traces)
        except Exception as e:
            log(f"  [{rec.filename}] warning: 2P trace plots failed: {e}")

    for lag_key, metrics in rec_results.items():
        if "adjMsub" not in metrics:
            continue
        lag_ms = int(lag_key.replace("mslag", ""))
        log(f"  [{rec.filename}] network figures (lag={lag_ms}ms)…")
        try:
            _plot_recording_lag(
                rec, lag_ms, metrics, state.channels, params,
                output_root / "4_NetworkActivity", log, batch_bounds,
                coords_all=state.coords, cell_types=state.markers,
                background=background,
                node_size_scale="auto" if params.twop_auto_node_size else 1.0,
            )
        except Exception as e:
            log(f"  [{rec.filename}] warning: network plots (lag={lag_ms}) failed: {e}")


# Node-level metrics compared across cell types (whole-network role of each
# cell), and graph-level metrics compared across induced subgraphs. Both lists
# are filtered against what a given run actually produced. The names (and their
# axis labels) live in ``group_plots`` so the per-recording figures here and the
# batch comparison figures cover exactly the same metrics.
_SUBNET_NODE_METRICS = list(SUBNET_NODE_METRICS)
_SUBNET_GRAPH_METRICS = list(SUBNET_GRAPH_METRICS)


def _run_subnetwork_analysis(
    params, rec, state, rec_results, min_nodes, output_root, tables, log, rng,
    background=None,
) -> None:
    """Cell-type subnetwork analysis for one recording, across all lags.

    Guarded end-to-end: a missing/unparseable cell-type spreadsheet or a
    failing figure logs a warning and leaves the rest of the run intact — the
    core CAT-NAP outputs never depend on this.

    Runs in phase 3, after the cartography barrier, so the whole-network node
    metrics it splits by cell type carry the batch-derived roles.
    """
    from meanap.catnap import subnetwork as sn
    from meanap.catnap import subnetwork_plotting as snp

    groups = state.groups
    if groups is None or groups.n_groups == 0:
        log(f"  [{rec.filename}] subnetworks: no cell-type groups — skipping")
        return

    for lag_key, full_metrics in rec_results.items():
        if "adjMsub" not in full_metrics:
            continue
        lag_ms = int(lag_key.replace("mslag", ""))
        adj_full = state.adjMs[f"adjM{lag_ms}mslag"]
        base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Lag": lag_key}
        out_dir = (output_root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                   / rec.group / rec.filename / f"{lag_ms}mslag" / "cellTypeSubnetworks")

        try:
            log(f"  [{rec.filename}] subnetwork metrics (lag={lag_ms}ms)…")
            results = sn.compute_subnetwork_metrics(
                adj_full, state.spike_counts, state.duration_s, groups, params,
                min_nodes=min_nodes, rng=rng, full_metrics=full_metrics,
            )
            summary = pd.DataFrame(sn.subnetwork_summary_rows(results))
            node_df = sn.split_node_metrics(full_metrics, groups, state.channels,
                                            adj_m=adj_full)

            # Edge mixing is measured on the analysed (active) subgraph, so it
            # describes the same network the whole-network metrics do.
            active = np.asarray(full_metrics["activeChannelIndex"], dtype=int)
            active_groups = groups.subset(active)
            edge_mix = sn.compute_edge_mix(full_metrics["adjMsub"], active_groups)
        except Exception as e:
            log(f"  [{rec.filename}] warning: subnetwork metrics (lag={lag_ms}) failed: {e}")
            continue

        tables["summary"].extend(dict(base, **row) for row in summary.to_dict("records"))
        tables["node"].extend(dict(base, **row) for row in node_df.to_dict("records"))
        tables["mix"].extend(dict(base, **row) for row in edge_mix.to_dict("records"))

        title = f"{rec.filename}  {lag_ms} ms lag"
        coords_active = state.coords[active]
        figures = [
            ("1_CellTypeNetwork.png",
             lambda p: snp.plot_subnetwork_spatial(
                 full_metrics["adjMsub"], coords_active, active_groups, p, title)),
            ("2_SubnetworkGraphs.png",
             lambda p: snp.plot_subnetwork_panels(
                 full_metrics["adjMsub"], coords_active, active_groups, p, title)),
            ("3_NodeMetricsByCellType.png",
             lambda p: snp.plot_node_metrics_by_group(
                 node_df, _SUBNET_NODE_METRICS, p,
                 f"{title} — whole-network node metrics by cell type", rng)),
            ("4_SubnetworkMetrics.png",
             lambda p: snp.plot_subnetwork_metric_bars(
                 summary, _SUBNET_GRAPH_METRICS, p,
                 f"{title} — metrics of each cell-type subnetwork")),
            ("5_EdgeMixing.png",
             lambda p: snp.plot_edge_mix_matrix(
                 edge_mix, active_groups, p, f"{title} — connectivity within/between cell types")),
        ]
        for name, draw in figures:
            try:
                draw(out_dir / name)
            except Exception as e:
                log(f"  [{rec.filename}] warning: subnetwork figure {name} failed: {e}")

        if params.twop_subnetwork_network_plots:
            _plot_subnetwork_figure_set(
                params, rec, state, results, full_metrics, lag_ms,
                output_root / "4_NetworkActivity", log, background,
            )


def _plot_subnetwork_figure_set(
    params, rec, state, results, full_metrics, lag_ms, net_dir, log,
    background=None,
) -> None:
    """Draw the whole step-4A figure set again, once per cell-type subnetwork.

    Same renderer as the whole network (``_plot_recording_lag``), pointed at
    each group's induced subgraph and its own nodes' coordinates — so
    ``cellTypeSubnetworks/Inhibitory/2_MEA_NetworkPlot.png`` can be read
    directly against the whole-network figure of the same name.

    Cartography roles inside a subnetwork are re-classified against the
    **whole-network** boundaries. The subgraph's own pooled PC/Z would put its
    boundaries somewhere else entirely, and then a "connector hub" would mean a
    different thing in each panel; sharing the boundaries keeps the roles
    comparable, which is the point of drawing them side by side.
    """
    from meanap.pipeline import network_metrics as nm
    from meanap.pipeline.step4 import _plot_recording_lag

    bounds = full_metrics.get("cartographyBoundaries")

    for name, metrics in results.items():
        if name == WHOLE_NETWORK or "adjMsub" not in metrics:
            continue
        idx = np.asarray(metrics.get("subnetworkNodeIndex", []), dtype=int)
        if idx.size == 0:
            continue

        metrics = dict(metrics)
        if bounds is not None and "PC" in metrics and "Z" in metrics:
            nd_cart_div, pop_num_nc = nm.classify_node_cartography(
                np.asarray(metrics["PC"], dtype=float),
                np.asarray(metrics["Z"], dtype=float), *bounds,
            )
            metrics["NdCartDiv"] = nd_cart_div
            metrics["cartographyBoundaries"] = bounds
            a_n = max(int(metrics.get("aN", 0)), 1)
            for i in range(6):
                metrics[f"NCpn{i + 1}"] = float(pop_num_nc[i] / a_n)
                metrics[f"NCpn{i + 1}count"] = int(pop_num_nc[i])

        markers = None
        if state.markers is not None:
            marker_matrix, marker_names = state.markers
            markers = (np.asarray(marker_matrix)[idx], marker_names)

        try:
            _plot_recording_lag(
                rec, lag_ms, metrics, state.channels[idx], params,
                net_dir, log, {},
                coords_all=state.coords[idx], cell_types=markers,
                sub_dir=f"cellTypeSubnetworks/{_safe_dir(name)}",
                background=background,
                node_size_scale="auto" if params.twop_auto_node_size else 1.0,
            )
        except Exception as e:
            log(f"  [{rec.filename}] warning: subnetwork figures for {name} "
                f"(lag={lag_ms}) failed: {e}")


def _safe_dir(name: str) -> str:
    """Folder-safe cell-type group name (``NeuN+ & ~GAD+`` → ``NeuN+_GAD+``)."""
    import re
    return re.sub(r"[^\w.+-]+", "_", str(name)).strip("_") or "group"


def _active_channels(df_node: pd.DataFrame) -> dict[str, set]:
    """Channels that cleared the activity threshold, per recording.

    ``FRactive`` is NaN exactly where a cell fell below ``min_activity_level``
    (see ``calc_twop_activity_stats``), so it is already the authoritative
    record of which cells the network analysis kept — no need to re-derive it.
    """
    if df_node.empty or "FRactive" not in df_node.columns:
        return {}
    active = df_node[df_node["FRactive"].notna()]
    return {name: set(sub["Channel"].astype(int))
            for name, sub in active.groupby("FileName")}


def _plot_group_comparisons(
    params, recordings, all_results, all_stats, all_channels, tables, states,
    output_root, log,
) -> None:
    """Batch group × age comparison figures — the CAT-NAP counterpart of the
    ephys ``2B_``/``4B_GroupComparisons`` folders.

    Three families, each guarded independently: a plotting failure costs the
    run nothing, since every metric and CSV is already on disk by this point.

    - **Two-photon activity** — event rate, amplitude, duration and area, the
      calcium equivalent of step 2's firing-rate comparisons.
    - **Network metrics** — the *shared* step-4 comparison plotter, unchanged:
      CAT-NAP's per-recording results dict has the same shape as the ephys one.
    - **Cell-type subnetworks** — only when the subnetwork analysis ran.
    """
    from meanap.catnap import group_plots as gp
    from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons

    order = params.custom_grp_order or None
    log("  Generating group comparison plots…")

    df_node = pd.DataFrame()
    try:
        _, df_node = gp.plot_twop_group_comparisons(
            recordings, all_stats, output_root / "2_NeuronalActivity",
            custom_grp_order=order, channels_by_rec=all_channels,
        )
    except Exception as e:
        log(f"  Warning: two-photon activity group comparison plots failed: {e}")

    # The same activity metrics again, split by cell type, plus how many cells
    # of each type each recording had.
    groups_by_rec = {name: st.groups for name, st in states.items() if st.groups}
    if groups_by_rec:
        try:
            by_type = gp.add_cell_type_column(df_node, groups_by_rec, all_channels)
            composition = gp.composition_frame(
                recordings, groups_by_rec, all_channels,
                active_by_rec=_active_channels(df_node),
            )
            gp.plot_activity_by_cell_type(
                by_type, composition, output_root / "2_NeuronalActivity",
                custom_grp_order=order,
            )
            if not composition.empty:
                composition.to_csv(
                    output_root / "2_NeuronalActivity" / "CellTypeComposition.csv",
                    index=False,
                )
        except Exception as e:
            log(f"  Warning: by-cell-type activity comparisons failed: {e}")

    try:
        plot_step4_group_comparisons(
            recordings, all_results, output_root / "4_NetworkActivity", order,
        )
    except Exception as e:
        log(f"  Warning: network group comparison plots failed: {e}")

    if tables["summary"] or tables["node"]:
        try:
            gp.plot_subnetwork_group_comparisons(
                tables["summary"], tables["node"],
                output_root / "4_NetworkActivity", order,
            )
        except Exception as e:
            log(f"  Warning: cell-type subnetwork group comparison plots failed: {e}")


def _save_subnetwork_results(tables: dict[str, list], net_dir: Path, log) -> None:
    """Write the three batch-level cell-type subnetwork CSVs."""
    outputs = {
        "summary": "Subnetwork_RecordingLevel.csv",
        "node": "Subnetwork_NodeLevel.csv",
        "mix": "Subnetwork_EdgeMix.csv",
    }
    for key, filename in outputs.items():
        if not tables[key]:
            continue
        try:
            pd.DataFrame(tables[key]).to_csv(net_dir / filename, index=False)
        except Exception as e:
            log(f"  Warning: could not save {filename}: {e}")


def _save_catnap_results(
    recordings: list[RecordingInfo],
    all_results: dict[str, dict],
    all_stats: dict[str, dict],
    all_channels: dict[str, np.ndarray],
    net_dir: Path,
    log: Callable[[str], None],
) -> None:
    """Write netmet_results.json + NetworkActivity CSVs (compact port of the
    save block in ``step4._run_step4_network_metrics``)."""
    try:
        json_results = {
            rec_name: {
                lag: {k: v for k, v in metrics.items() if k != "adjMsub"}
                for lag, metrics in rec_results.items()
            }
            for rec_name, rec_results in all_results.items()
        }
        with open(net_dir / "netmet_results.json", "w") as fh:
            json.dump(_convert_numpy(json_results), fh, indent=2)

        rec_rows, node_rows = [], []
        for rec in recordings:
            if rec.filename not in all_results:
                continue
            for lag, metrics in all_results[rec.filename].items():
                base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Lag": lag}
                rec_row = dict(base)
                node_metrics = {}
                for k, v in metrics.items():
                    if k == "adjMsub" or k in _NMF_NON_NODE_KEYS:
                        continue
                    is_array = isinstance(v, (list, np.ndarray))
                    if not is_array or np.size(v) <= 1:
                        rec_row[k] = v[0] if is_array and np.size(v) == 1 else v
                    else:
                        node_metrics[k] = v
                rec_rows.append(rec_row)
                if node_metrics:
                    num_nodes = len(next(iter(node_metrics.values())))
                    for ch in range(num_nodes):
                        node_row = dict(base, Channel=ch + 1)
                        for k, arr in node_metrics.items():
                            if len(arr) == num_nodes:
                                node_row[k] = arr[ch]
                        node_rows.append(node_row)

        if rec_rows:
            pd.DataFrame(rec_rows).to_csv(net_dir / "NetworkActivity_RecordingLevel.csv", index=False)
        if node_rows:
            pd.DataFrame(node_rows).to_csv(net_dir / "NetworkActivity_NodeLevel.csv", index=False)

        # Two-photon activity stats (step-2 equivalent). The recording-level CSV
        # takes every scalar field; the node-level one carries the per-unit
        # arrays (event rate, ISI, amplitude, duration, area), which otherwise
        # only existed in memory — and are what the group comparison figures
        # plot.
        twop_dir = net_dir.parent / "2_NeuronalActivity"
        stats_rows = [dict({"FileName": r.filename, "Grp": r.group, "DIV": r.div},
                           **{k: v for k, v in all_stats[r.filename].items()
                              if np.size(v) <= 1})
                      for r in recordings if r.filename in all_stats]
        if stats_rows:
            pd.DataFrame(stats_rows).to_csv(
                twop_dir / "TwoPhotonActivity_RecordingLevel.csv", index=False)

        _, node_stats = twop_stats_frames(recordings, all_stats, all_channels)
        if not node_stats.empty:
            node_stats.to_csv(twop_dir / "TwoPhotonActivity_NodeLevel.csv", index=False)
    except Exception as e:
        log(f"  Warning: could not save CAT-NAP results: {e}")
