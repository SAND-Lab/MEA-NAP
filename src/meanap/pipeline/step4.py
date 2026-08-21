"""Step 4: network activity metrics, port of ``ExtractNetMet.m`` (see
``network_metrics.py`` for exactly which metrics are and aren't in scope,
and which are deterministic vs. dependent on a stochastic null model).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from meanap.network_plot import NetworkStyle

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform

from meanap.timescale import timescale_folder, timescale_kind
from meanap.params import Params
from meanap.pipeline import network_metrics as nm
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import find_raw_file, load_spike_times_npz, resolve_duration_s
from meanap.pipeline.modularity import mod_consensus_cluster_iterate
from meanap.pipeline.nmf import cal_nmf
from meanap.pipeline.null_models import latmio_und_v2, randmio_und_v2
from meanap.pipeline.parallel import map_recordings
from meanap.pipeline.progress import RunProgress
from meanap.pipeline.plotting_step4 import (
    plot_circular_cartography_network, plot_circular_module_network,
    plot_connectivity_stats, plot_graph_metrics_by_node,
    plot_network_beside_field, plot_node_cartography, plot_spatial_network,
    plot_spatial_network_combined,
)
from meanap.pipeline.resume import ADJM_SUFFIX, build_input_locator
from meanap.pipeline.rng import make_rng
from meanap.pipeline.spreadsheet import RecordingInfo, ground_spike_times_dict, parse_ground_electrodes


def _convert_numpy(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def compute_network_metrics(
    adj_m: np.ndarray,
    spike_counts: np.ndarray,
    duration_s: float,
    min_activity_level: float,
    min_nodes: int,
    exclude_edges_below_threshold: bool = True,
    params: Params | None = None,
    rng: np.random.Generator | None = None,
) -> dict:
    """Compute deterministic network metrics for one (recording, lag) adjacency matrix.

    Mirrors the active-node subsetting + metric calls in ``ExtractNetMet.m``
    (weighted adjM path).
    """
    adj_m = adj_m.copy()
    adj_m[adj_m < 0] = 0.0
    adj_m = np.nan_to_num(adj_m, nan=0.0)

    node_strength_full = adj_m.sum(axis=0)
    activity_level = spike_counts / duration_s
    inclusion_index = np.nonzero((node_strength_full != 0) & (activity_level >= min_activity_level))[0]
    a_n = len(inclusion_index)

    result: dict = {"aN": a_n, "activeChannelIndex": inclusion_index}

    if a_n < min_nodes:
        return result

    sub = adj_m[np.ix_(inclusion_index, inclusion_index)]
    result["adjMsub"] = sub  # not JSON-serialized — see _run_step4_network_metrics

    nd, mew = nm.find_node_deg_edge_weight(
        sub, edge_thresh=0.0001, exclude_zeros=exclude_edges_below_threshold,
    )
    result["ND"] = nd
    result["MEW"] = mew
    result["NS"] = nm.strengths_und(sub)
    result["Dens"] = nm.density_und(sub)

    # a_n >= min_nodes is already guaranteed by the early return above, so
    # unlike ExtractNetMet.m (which nan-guards this block with an explicit
    # "aN >= minNumberOfNodesToCalNetMet" check) it's unconditional here.
    result["NDmean"] = float(np.nanmean(nd))
    nd_p75 = np.percentile(nd, 75)
    result["NDtop25"] = float(np.mean(nd[nd >= nd_p75]))
    result["NSmean"] = float(np.nanmean(result["NS"]))

    # Mean of the significant (nonzero) edges — every matrix entry, not just
    # the upper triangle, matching ExtractNetMet.m's `adjM(abs(adjM) > 0)`.
    sig_edges = sub[np.abs(sub) > 0]
    if sig_edges.size:
        result["sigEdgesMean"] = float(np.mean(sig_edges))
        sig_edges_p90 = np.percentile(sig_edges, 90)
        result["sigEdgesTop10"] = float(np.mean(sig_edges[sig_edges >= sig_edges_p90]))

    # Raw (unnormalized) clustering coefficient / path length — independently
    # useful/testable deterministic quantities, but NOT what MATLAB saves as
    # NetMet.CC/NetMet.PL (see the small-worldness block below for those).
    result["CC_raw"] = nm.clustering_coef_wu(sub)
    result["CC_rawMean"] = float(np.mean(result["CC_raw"]))

    length_mat = nm.weight_conversion_lengths(sub)
    dist = nm.distance_wei(length_mat)
    pl_raw, _ = nm.charpath(dist)
    result["PL_raw"] = pl_raw

    result["Eglob"] = nm.efficiency_wei_global(sub)

    # ── Small-worldness (SW/SWw + the saved, null-model-normalized CC/PL) ──
    # MATLAB's own gate here is strictly "> minNumberOfNodesToCalNetMet"
    # (ExtractNetMet.m), unlike every other block's "aN >= ..." — faithfully
    # replicated, not a typo.
    if a_n > min_nodes:
        if rng is None:
            rng = np.random.default_rng()
        dist_profile = squareform(pdist(sub))
        lattice_net = latmio_und_v2(sub, 10000, dist_profile, rng=rng)
        random_net = randmio_und_v2(sub, 5000, rng=rng)
        sw, sww, cc, pl = nm.small_worldness_rl_wu(sub, random_net, lattice_net)
        result["SW"] = sw
        result["SWw"] = sww
        result["CC"] = cc
        result["PL"] = pl

    sub_nrm = nm.weight_conversion_normalize(sub)
    eloc = nm.efficiency_wei_local(sub_nrm)
    result["Eloc"] = eloc
    result["ElocMean"] = float(np.mean(eloc))

    path_len_net = 1.0 / (sub + 0.01)
    bc = nm.betweenness_wei(path_len_net)
    n = sub.shape[0]
    result["BC"] = bc / ((n - 1) * (n - 2)) if n > 2 else np.full(n, np.nan)

    with np.errstate(divide="ignore"):
        mean_dist = dist.mean(axis=0)
        result["NE"] = 1.0 / mean_dist

    # ── Modularity-dependent metrics (stochastic Ci — see modularity.py) ──
    if params is not None and a_n > 1:
        ci, q, _num_repeats = mod_consensus_cluster_iterate(sub, threshold=0.4, rep_num=50, rng=rng)
        result["Ci"] = ci
        result["Q"] = q
        result["nMod"] = int(ci.max())

        # PC = normalized participation coefficient — matches what MATLAB
        # actually saves as NetMet.PC (participation_coef_norm.m's 1st
        # output) and feeds into node cartography / hub classification /
        # the "4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png"
        # plot. PC_raw is the deterministic (given Ci) 3rd output, kept
        # separately since it's independently testable/useful.
        pc_norm, pc_residual, pc_raw, _between_mod_k = nm.participation_coef_norm(sub, ci, n_iter=100, rng=rng)
        z = nm.module_degree_zscore(sub, ci)
        result["PC"] = pc_norm
        result["PC_raw"] = pc_raw
        result["PC_residual"] = pc_residual
        result["Z"] = z

        result["PCmean"] = float(np.mean(pc_norm))
        pc_p90 = np.percentile(pc_norm, 90)
        pc_p10 = np.percentile(pc_norm, 10)
        result["PCmeanTop10"] = float(np.mean(pc_norm[pc_norm >= pc_p90]))
        result["PCmeanBottom10"] = float(np.mean(pc_norm[pc_norm <= pc_p10]))
        result["percentZscoreGreaterThanZero"] = float(np.sum(z > 0) / len(z) * 100)
        result["percentZscoreLessThanZero"] = float(np.sum(z < 0) / len(z) * 100)

        result["RC"] = nm.rich_club_wu(sub)

        nd_cart_div, pop_num_nc = nm.classify_node_cartography(
            pc_norm, z,
            params.hub_boundary_wm_d_deg, params.peri_part_coef,
            params.non_hub_connector_part_coef, params.pro_hub_part_coef,
            params.connector_hub_part_coef,
        )
        result["NdCartDiv"] = nd_cart_div
        for i in range(6):
            result[f"NCpn{i + 1}"] = float(pop_num_nc[i] / a_n)
            result[f"NCpn{i + 1}count"] = int(pop_num_nc[i])

        hub3, hub4 = nm.hub_classification(result["ND"], pc_norm, result["BC"], result["NE"])
        result["Hub3"] = hub3
        result["Hub4"] = hub4

    # ── Controllability ────────────────────────────────────────────────────────
    ave_control = nm.average_controllability(adj_m)
    if len(ave_control) > 0:
        ave_control_sub = ave_control[inclusion_index]
        result["aveControl"] = ave_control_sub
        result["aveControlMean"] = float(np.mean(ave_control_sub))
        p75 = np.percentile(ave_control_sub, 75)
        result["aveControlTop25"] = float(np.mean(ave_control_sub[ave_control_sub >= p75]))

    modal_control = nm.modal_controllability(adj_m)
    if len(modal_control) > 0:
        modal_control_sub = modal_control[inclusion_index]
        result["modalControl"] = modal_control_sub
        result["modalControlMean"] = float(np.mean(modal_control_sub))
        result["modalControlPrctLessThanThreshold"] = float(np.mean(modal_control_sub < 0.975))

    return result


# NMF-related arrays that are NOT indexed by node/channel (rank-k sweeps,
# factor matrices) — must be excluded from the generic "any array => spread
# across NodeLevel.csv rows by channel index" logic below, since their
# length can coincidentally match the active-node count and get silently
# (and wrongly) treated as per-channel data.
_NMF_NON_NODE_KEYS = frozenset({
    "nnmf_residuals", "nnmf_var_explained", "randResidualPerComponent",
    "downSampleSpikeMatrix", "nmfFactors", "nmfWeights",
    "nmfFactorsVarThreshold", "nmfWeightsVarThreshold",
})

# Edge-weight bounds for the "scaled to entire data batch" network plots.
# MATLAB hardcodes ``minMax.EW = [0.1, 1]`` (MEApipeline.m) rather than deriving
# it from the data, so the scaled variants share a fixed edge scale.
_EDGE_BATCH_BOUNDS = (0.1, 1.0)


def _batch_metric_bounds(all_results: dict, metric: str) -> tuple[float, float] | None:
    """Pool a node-level metric across every recording/lag and return its
    ``(min, max)``, or ``None`` if the metric is absent everywhere.

    Mirrors ``findMinMaxNetMetTable.m``, which reads the whole
    ``NetworkActivity_NodeLevel.csv`` column (all recordings and all lags
    pooled together) to get the shared bounds for the batch-scaled plots.
    """
    chunks = []
    for rec_results in all_results.values():
        for metrics in rec_results.values():
            arr = metrics.get(metric)
            if arr is None:
                continue
            a = np.asarray(arr, dtype=float).ravel()
            a = a[np.isfinite(a)]
            if a.size:
                chunks.append(a)
    if not chunks:
        return None
    pooled = np.concatenate(chunks)
    return float(pooled.min()), float(pooled.max())


#: The spatial network plots: ``(filename, colour metric, colour legend name,
#: size metric, size legend name)``. At module level because the bundle renderer
#: has to be able to *name* a variant without re-deriving the rule — see
#: :func:`variant_stem`. The batch maximum each scaled variant needs is just
#: ``batch_bounds[size metric][1]`` and is looked up where it is used.
#:
#: Controllability plots are only produced when those (optional) metrics are
#: present; the drawing loop's ``color_key not in metrics`` guard skips them.
#: No batch bound is pooled for those two, so their scaled variant shares only
#: the node-size and edge scale, not the colour scale.
SPATIAL_PLOTS = (
    ("2_MEA_NetworkPlot.png", None, "None", "ND", "node degree"),
    ("3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png", "BC",
     "Betweenness centrality", "ND", "node degree"),
    ("4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png", "PC",
     "Participation coefficient", "ND", "node degree"),
    ("5_MEA_NetworkPlotNodestrengthLocalefficiency.png", "Eloc",
     "Local efficiency", "NS", "node strength"),
    ("10_MEA_NetworkPlotNodedegreeAveragecontrollability.png", "aveControl",
     "Average controllability", "ND", "node degree"),
    ("11_MEA_NetworkPlotNodedegreeModalcontrollability.png", "modalControl",
     "Modal controllability", "ND", "node degree"),
)

#: How each spatial network plot is drawn: to this recording's own range, to the
#: batch's, or the two side by side.
FIGURE_VARIANTS = ("plain", "scaled", "combined")


def variant_stem(base: str, variant: str) -> str | None:
    """The filename stem *variant* of the plot *base* is written under.

    ``None`` when there is no such variant: only the spatial network plots come
    in scaled and combined versions, and ``plain`` is the base itself.
    """
    if variant == "plain":
        return Path(base).stem
    spec = next((s for s in SPATIAL_PLOTS if Path(s[0]).stem == Path(base).stem),
                None)
    if spec is None:
        return None
    fname, color_key, color_name = spec[0], spec[1], spec[2]
    if variant == "scaled":
        return Path(fname.replace("_MEA_NetworkPlot", "_scaled_MEA_NetworkPlot",
                                  1)).stem
    if variant == "combined":
        # MATLAB names this "<n>_combined_MEA_NetworkPlot" plus the colour
        # legend name, rather than the concatenated size+colour suffix the
        # single plots use.
        stem = f"{fname.split('_', 1)[0]}_combined_MEA_NetworkPlot"
        return stem + (f"_{color_name}" if color_key is not None else "")
    return None


def _plot_recording_lag(
    rec: RecordingInfo,
    lag_ms,
    metrics: dict,
    channels_arr: np.ndarray,
    params: Params,
    out_dir: Path,
    log: Callable[[str], None],
    batch_bounds: dict[str, tuple[float, float] | None],
    coords_all: np.ndarray | None = None,
    cell_types: tuple[np.ndarray, list[str]] | None = None,
    sub_dir: str | None = None,
    background: tuple | None = None,
    node_size_scale: float | str = 1.0,
    fmt: str = "png",
    only: str | None = None,
    style: "NetworkStyle | None" = None,
) -> list[Path]:
    """Draw every step-4A plot for one recording/lag.

    Produces both the individual-scaled plots (each colored/sized to this
    recording's own range) and, for the spatial network plots, ``_scaled``
    variants whose node-size / node-color / edge scales come from
    ``batch_bounds`` (the whole batch's pooled range) so they can be compared
    across recordings — matching MATLAB's ``useMinMaxBoundsForPlots`` pass in
    ``PlotIndvNetMet.m``.

    ``coords_all`` supplies node positions directly (one row per channel in
    ``channels_arr``) instead of looking them up in the MEA channel layout —
    the CAT-NAP path passes suite2p cell centroids, so the whole figure set is
    shared between electrophysiology and calcium imaging rather than
    duplicated.

    ``cell_types`` is an ``(n_channels, n_markers)`` membership matrix and its
    marker names, aligned with ``channels_arr``. When given, every spatial
    network plot draws each node's full genetic identity as concentric marker
    rings — CAT-NAP's use for the immunohistochemistry panel.

    ``sub_dir`` nests the output under the recording's lag folder, so the same
    figure set can be drawn more than once per lag — CAT-NAP uses it to redraw
    everything per cell-type subnetwork alongside the whole-network version.

    ``background`` is an ``(image, extent)`` pair — CAT-NAP passes suite2p's
    mean projection — used for **one** extra side-by-side figure showing the
    field of view next to the network. It is deliberately not drawn under the
    ordinary spatial plots: with a few hundred nodes and a dense edge set the
    image is completely covered, so it adds clutter without adding information.
    ``node_size_scale`` is forwarded to ``plot_network``; ``"auto"`` sizes nodes
    from how densely they are packed, which two-photon fields need and MEA
    layouts are unaffected by.
    ``fmt`` is the image format — the suffix drives matplotlib, so ``"svg"`` (or
    ``"pdf"``) yields editable vector output for figures headed to a paper.
    ``only`` restricts the call to the single figure with that base name, which
    is how the viewer renders one plot per request instead of the whole set.
    Returns the paths actually written.
    """
    if "adjMsub" not in metrics:
        return []

    rec_out_dir = out_dir / "4A_IndividualNetworkAnalysis" / rec.group / rec.filename
    # "1000mslag" for STTC, "1000msbin" for a CAT-NAP correlation run — the
    # number means a different thing in each, so the folder says which.
    lag_dir = rec_out_dir / timescale_folder(lag_ms, params)
    if sub_dir:
        lag_dir = lag_dir.joinpath(*str(sub_dir).split("/"))

    written: list[Path] = []

    def want(name: str) -> Path | None:
        """Path for one figure, or ``None`` when this render skips it.

        Centralising the naming here is what lets the same call sites serve
        both the pipeline (every figure, PNG) and the viewer (one figure, any
        format) without a second copy of the figure list.
        """
        stem = Path(name).stem
        if only is not None and stem != only:
            return None
        path = lag_dir / f"{stem}.{fmt}"
        written.append(path)
        return path

    if (p := want(f"1_adjM{lag_ms}msConnectivityStats.png")) is not None:
        plot_connectivity_stats(
            metrics["adjMsub"], metrics["ND"], metrics["NS"], lag_ms,
            rec.filename, p,
            exclude_edges_below_threshold=params.exclude_edges_below_threshold,
        )

    try:
        channels_active = channels_arr[metrics["activeChannelIndex"]]
        coords_active = (None if coords_all is None
                         else np.asarray(coords_all)[metrics["activeChannelIndex"]])
        ct_active = None
        if cell_types is not None:
            ct_matrix, ct_names = cell_types
            ct_active = (np.asarray(ct_matrix)[metrics["activeChannelIndex"]], ct_names)
        for fname, color_key, color_name, size_key, size_name in SPATIAL_PLOTS:
            if size_key not in metrics:
                continue
            # The batch maximum for the size metric is the whole of what the
            # scaled variant needs from the pooled bounds.
            size_max = (batch_bounds[size_key][1]
                        if batch_bounds.get(size_key) else None)
            if color_key is not None and color_key not in metrics:
                continue
            z = metrics[size_key]
            z2 = metrics[color_key] if color_key is not None else None

            # Individual-scaled (this recording's own range).
            if (p := want(fname)) is not None:
                plot_spatial_network(
                    metrics["adjMsub"], channels_active, params.channel_layout,
                    z, z2, color_name, lag_ms, rec.filename,
                    p, z_name=size_name,
                    coords_override=coords_active, cell_types=ct_active,
                    node_size_scale=node_size_scale, style=style,
                )

            # Batch-scaled variant + side-by-side combined figure, if we have a
            # batch max for the size metric.
            if size_max is not None:
                color_bounds = batch_bounds.get(color_key) if color_key is not None else None
                scaled_name = fname.replace("_MEA_NetworkPlot", "_scaled_MEA_NetworkPlot", 1)
                if (p := want(scaled_name)) is not None:
                    plot_spatial_network(
                        metrics["adjMsub"], channels_active, params.channel_layout,
                        z, z2, color_name, lag_ms, rec.filename,
                        p, z_name=size_name,
                        z_scale_override=size_max,
                        z2_bounds_override=color_bounds,
                        edge_bounds_override=_EDGE_BATCH_BOUNDS,
                        coords_override=coords_active, cell_types=ct_active,
                        node_size_scale=node_size_scale, style=style,
                    )
                # MATLAB names the combined figure "<n>_combined_MEA_NetworkPlot"
                # plus "_<color legend name>" when there's a colour metric (e.g.
                # "10_combined_MEA_NetworkPlot_Average controllability"), rather
                # than the concatenated size+colour suffix of the single plots.
                num_prefix = fname.split("_", 1)[0]
                combined_name = f"{num_prefix}_combined_MEA_NetworkPlot"
                if color_key is not None:
                    combined_name += f"_{color_name}"
                combined_name += ".png"
                if (p := want(combined_name)) is not None:
                    plot_spatial_network_combined(
                        metrics["adjMsub"], channels_active, params.channel_layout,
                        z, z2, color_name, lag_ms, rec.filename,
                        p, z_name=size_name,
                        z_scale_override=size_max,
                        z2_bounds_override=color_bounds,
                        edge_bounds_override=_EDGE_BATCH_BOUNDS,
                        coords_override=coords_active, cell_types=ct_active,
                        node_size_scale=node_size_scale, style=style,
                    )
    except ValueError as e:
        log(f"  [{rec.filename}] skipped spatial network plot: {e}")

    if background is not None:
        try:
            if (p := want("12_MeanImageAndNetwork.png")) is not None:
                plot_network_beside_field(
                    metrics["adjMsub"], channels_active, params.channel_layout,
                    metrics["ND"], lag_ms, rec.filename, p,
                    background=background,
                    coords_override=coords_active,
                    node_size_scale=node_size_scale,
                )
        except Exception as e:
            log(f"  [{rec.filename}] skipped field-of-view figure: {e}")

    if "PC" in metrics:
        if (p := want(f"9_adjM{lag_ms}msNodeCartography.png")) is not None:
            plot_node_cartography(
                metrics["PC"], metrics["Z"], params, lag_ms, rec.filename, p,
                boundaries=metrics.get("cartographyBoundaries"),
                nd_cart_div=metrics.get("NdCartDiv"),
            )

    if "NdCartDiv" in metrics:
        if (p := want("9_circular_NetworkPlotNodeCartography.png")) is not None:
            plot_circular_cartography_network(
                metrics["adjMsub"], metrics["NdCartDiv"],
                lag_ms, rec.filename, p,
                edge_thresh=params.exclude_edges_below_threshold * 0.0001,
            )

    if "Ci" in metrics:
        if (p := want("6_circular_NetworkPlotNodedegreeModule.png")) is not None:
            plot_circular_module_network(
                metrics["adjMsub"], metrics["Ci"], metrics["ND"],
                lag_ms, rec.filename, p,
            )

    try:
        if (p := want(f"7_adjM{lag_ms}msGraphMetricsByNode.png")) is not None:
            plot_graph_metrics_by_node(
                nd=metrics["ND"],
                mew=metrics["MEW"],
                ns=metrics["NS"],
                z=metrics.get("Z"),
                eloc=metrics.get("Eloc"),
                pc=metrics.get("PC"),
                bc=metrics.get("BC"),
                lag_ms=lag_ms,
                recording_name=rec.filename,
                out_path=p,
                # The half-violin jitter is the only randomness in the 4A set.
                # Left unseeded it made this one figure differ between two
                # otherwise-identical seeded runs — and between the pipeline's
                # copy and a viewer's. Derived per recording+lag like every
                # other stochastic stage (see pipeline/rng.py).
                rng=make_rng(params.random_seed, "step4-plots", rec.filename, lag_ms),
            )
    except Exception as e:
        log(f"  [{rec.filename}] skipped graph-metrics-by-node plot: {e}")

    # ``want`` records intent; a plot guarded by a try/except may not have
    # produced its file, so report what is actually on disk.
    return [p for p in written if p.exists()]


# Peak per-worker RAM for Step 4: NMF's downsampled spike matrix + sklearn NMF
# working set + (in the plot phase) a matplotlib figure or two. All modest;
# ~0.6 GB is a safe cap so a 16 GB box still gets several workers.
_STEP4_MEM_PER_TASK_GB = 0.6


def _step4_compute_one(
    task: tuple[Params, RecordingInfo, str],
) -> tuple[str, dict | None, np.ndarray | None, list[str]]:
    """Phase A worker: compute one recording's network metrics (effRank, NMF,
    per-lag metrics). Module-level/picklable for ``spawn``. Returns the metrics
    keyed by lag (or ``None`` if skipped), the channel array (needed by the
    plot phase), and the log lines it produced."""
    params, rec, output_root_str = task
    output_root = Path(output_root_str)
    locator = build_input_locator(params, output_root)

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    min_nodes = params.min_number_of_nodes_to_cal_net_met
    logs: list[str] = []

    adj_path = locator.adjm_file(rec.filename)
    spike_path = locator.spike_file(rec.filename)
    if adj_path is None:
        logs.append(f"  [{rec.filename}] SKIP: adjacency matrices not found "
                    f"({rec.filename}_adjM.npz)")
        return rec.filename, None, None, logs
    if spike_path is None:
        logs.append(f"  [{rec.filename}] SKIP: spike data not found ({rec.filename}_spikes.npz)")
        return rec.filename, None, None, logs

    # Derived from the recording name, not from a shared stream, so the
    # stochastic metrics (Ci/Q/PC-norm/SW/NMF) don't depend on how many
    # workers the pool used or what order recordings completed in.
    rng = make_rng(params.random_seed, "step4", rec.filename)

    logs.append(f"  [{rec.filename}] loading adjacency matrices...")
    adj_data = np.load(adj_path)
    spike_data = np.load(spike_path)
    fs = float(spike_data["fs"][0])
    channels_arr = spike_data["channels"]
    n_channels = len(channels_arr)

    duration_s, _ = resolve_duration_s(
        spike_data, find_raw_file(params.raw_data, rec.filename), fs, n_channels,
    )
    if duration_s is None:
        logs.append(f"  [{rec.filename}] SKIP: recording duration unavailable "
                    f"(not in the spike file, and the raw recording could not be read)")
        return rec.filename, None, None, logs

    spike_times_full = load_spike_times_npz(spike_path)
    spike_times_dict = {
        ch: spike_times_full.get(ch, {}).get(method, np.array([]))
        for ch in range(n_channels)
    }
    ground_electrodes = parse_ground_electrodes(rec.ground)
    if ground_electrodes:
        spike_times_dict = ground_spike_times_dict(spike_times_dict, channels_arr, ground_electrodes)

    spike_counts = np.array([len(spike_times_dict[ch]) for ch in range(n_channels)])
    spike_times_list = [spike_times_dict[ch] for ch in range(n_channels)]

    try:
        eff_rank = nm.effective_rank(
            spike_times_list, fs, duration_s,
            params.eff_rank_downsample_freq, params.eff_rank_cal_method
        )
    except Exception as e:
        logs.append(f"  [{rec.filename}] WARNING: could not compute effective rank: {e}")
        eff_rank = float('nan')

    try:
        logs.append(f"  [{rec.filename}] computing NMF components...")
        nmf_result = cal_nmf(
            spike_times_list, spike_counts, duration_s,
            params.nmf_downsample_freq, fs,
            include_nmf_components=params.include_nmf_components, rng=rng,
        )
    except Exception as e:
        logs.append(f"  [{rec.filename}] WARNING: could not compute NMF components: {e}")
        nmf_result = {}

    rec_results: dict = {}
    for lag_ms in lag_values:
        key = f"adjM{lag_ms}mslag"
        if key not in adj_data:
            continue
        logs.append(f"  [{rec.filename}] computing network metrics (lag={lag_ms}ms)...")
        metrics = compute_network_metrics(
            adj_data[key], spike_counts, duration_s,
            params.min_activity_level, min_nodes,
            exclude_edges_below_threshold=params.exclude_edges_below_threshold,
            params=params, rng=rng,
        )
        metrics["effRank"] = eff_rank
        metrics.update(nmf_result)
        rec_results[f"{lag_ms}mslag"] = metrics

    return rec.filename, rec_results, channels_arr, logs


def _step4_plot_one(
    task: tuple[Params, RecordingInfo, dict, np.ndarray, str, dict],
) -> tuple[str, list[str]]:
    """Phase C worker: draw one recording's plots (individual- and
    batch-scaled) now that ``batch_bounds`` are known. Module-level/picklable
    for ``spawn``; writes its own PNGs and returns its log lines."""
    params, rec, rec_results, channels_arr, output_root_str, batch_bounds = task
    out_dir = Path(output_root_str) / "4_NetworkActivity"
    logs: list[str] = []

    def _log(msg: str) -> None:
        logs.append(msg)

    # Every 4A figure is a function of `metrics` + the stored adjacency, both of
    # which the bundle carries, so express mode skips them and the viewer
    # redraws on demand.
    if params.express_mode:
        return rec.filename, logs

    for lag_key, metrics in rec_results.items():
        lag_ms = int(lag_key.replace("mslag", ""))
        _log(f"  [{rec.filename}] plotting network metrics (lag={lag_ms}ms)...")
        _plot_recording_lag(
            rec, lag_ms, metrics, channels_arr, params, out_dir, _log, batch_bounds,
        )
    return rec.filename, logs


def _apply_cartography_boundaries(
    params: Params,
    all_results: dict[str, dict],
    log: Callable[[str], None],
    out_dir: Path | None = None,
) -> None:
    """Re-derive node-cartography boundaries from pooled PC/Z and re-classify.

    Port of MEApipeline.m's ``autoSetCartographyBoundaries`` step: after every
    recording's metrics are computed, pool the participation coefficient (PC)
    and within-module z-score (Z) across recordings and run
    :func:`nm.trial_landscape_density` to place the six cartography boundaries
    where the data actually clusters, rather than at the fixed
    ``params.peri_part_coef`` etc. Then overwrite ``NdCartDiv`` / ``NCpn*`` for
    every recording at each affected lag. Mutates ``all_results`` in place.

    With ``auto_set_cartography_boundaries_per_lag`` each lag gets its own
    boundaries from that lag's pooled PC/Z (MEApipeline default); otherwise a
    single set from ``cartography_lag_val[0]`` is applied to all lags.
    """
    lag_keys = sorted(
        {lag for rec in all_results.values() for lag in rec},
        key=lambda k: int(k.replace("mslag", "")),
    )
    if not lag_keys:
        return

    if params.auto_set_cartography_boundaries_per_lag:
        # each lag: derive from its own pooled PC/Z, apply to itself
        plans = [(lk, [lk]) for lk in lag_keys]
    else:
        ref = f"{params.cartography_lag_val[0]}mslag"
        source = ref if ref in lag_keys else lag_keys[0]
        plans = [(source, lag_keys)]  # one boundary set → all lags

    for source_lag, target_lags in plans:
        pc_pool, z_pool = [], []
        for rec in all_results.values():
            m = rec.get(source_lag)
            if m and "PC" in m and "Z" in m:
                pc_pool.append(np.asarray(m["PC"], dtype=float))
                z_pool.append(np.asarray(m["Z"], dtype=float))
        if not pc_pool:
            continue

        bounds = nm.trial_landscape_density(
            np.concatenate(pc_pool), np.concatenate(z_pool),
            params.hub_boundary_wm_d_deg, params.peri_part_coef,
            params.pro_hub_part_coef, params.non_hub_connector_part_coef,
            params.connector_hub_part_coef,
        )
        if bounds is None:
            log(f"  Cartography: too few PC/Z values at {source_lag}; "
                "keeping fixed boundaries.")
            continue
        hub_b, peri, non_hub_conn, pro_hub, conn_hub = bounds
        log(f"  Cartography boundaries from {source_lag} pooled PC/Z: "
            f"Zhub={hub_b:.3f} peri={peri:.3f} nonHubConn={non_hub_conn:.3f} "
            f"proHub={pro_hub:.3f} connHub={conn_hub:.3f}")

        # Pooled PC/Z landscape scatter with the derived boundaries
        # (TrialLandscapeDensity.m's ZandPC_scatter). MATLAB overwrites a single
        # file per lag, so in per-lag mode the last lag's version is what remains.
        if out_dir is not None:
            from meanap.pipeline.plotting_step4 import plot_density_landscape
            dl_dir = out_dir / "4B_GroupComparisons" / "7_DensityLandscape"
            plot_density_landscape(
                np.concatenate(pc_pool), np.concatenate(z_pool), bounds,
                dl_dir / "ZandPC_scatter_with_kmeans_boundaries_.png",
            )

        for lag_key in target_lags:
            for rec in all_results.values():
                m = rec.get(lag_key)
                if not m or "PC" not in m or "Z" not in m:
                    continue
                pc = np.asarray(m["PC"], dtype=float)
                z = np.asarray(m["Z"], dtype=float)
                a_n = len(pc)
                if a_n == 0:
                    continue
                nd_cart_div, pop_num_nc = nm.classify_node_cartography(
                    pc, z, hub_b, peri, non_hub_conn, pro_hub, conn_hub,
                )
                m["NdCartDiv"] = nd_cart_div
                # Store the data-driven boundaries so the per-recording
                # cartography scatter plot draws these (and colours by this
                # NdCartDiv) rather than re-deriving from the fixed params
                # defaults — keeping the plot consistent with the CSVs and the
                # circular cartography plot.
                m["cartographyBoundaries"] = (hub_b, peri, non_hub_conn, pro_hub, conn_hub)
                for i in range(6):
                    m[f"NCpn{i + 1}"] = float(pop_num_nc[i] / a_n)
                    m[f"NCpn{i + 1}count"] = int(pop_num_nc[i])


#: Where phase A's running results are kept. The final artefact *is* the
#: checkpoint — no separate journal to write, clean up, or get out of step with
#: the thing it shadows. Rewritten after each recording rather than appended to,
#: because a JSON object cannot be appended to; the cost is one serialisation
#: per recording, and the benefit is that an interrupted run leaves a valid,
#: readable results file holding everything that finished.
NETMET_FILENAME = "netmet_results.json"


def _netmet_json(all_results: dict) -> dict:
    """The JSON form of the metrics: everything except the adjacency subgraph.

    ``adjMsub`` is dropped because it is a pure function of the stored adjacency
    and ``activeChannelIndex`` — see :func:`_restore_adjm_sub`, which puts it
    back — and it is the largest thing in the dict.
    """
    return {
        rec_name: {
            lag: {k: v for k, v in metrics.items() if k != "adjMsub"}
            for lag, metrics in rec_results.items()
        }
        for rec_name, rec_results in all_results.items()
    }


def _write_netmet(out_dir: Path, all_results: dict) -> None:
    """Checkpoint phase A's results so far. Atomic; safe to call repeatedly."""
    from meanap.pipeline.atomic import atomic_write_json

    atomic_write_json(out_dir / NETMET_FILENAME,
                      _convert_numpy(_netmet_json(all_results)), indent=2)


def _restore_adjm_sub(output_root: Path, recording: str, rec_results: dict) -> bool:
    """Put ``adjMsub`` back for a recording loaded from the checkpoint.

    Phase C draws from it and the JSON does not carry it. Rebuilt from the
    adjacency this run already wrote plus ``activeChannelIndex``, exactly as
    ``compute_network_metrics`` derived it in the first place. ``False`` when the
    adjacency is missing, which makes the recording recompute rather than plot
    from a half-restored state.
    """
    path = output_root / "ExperimentMatFiles" / f"{recording}{ADJM_SUFFIX}"
    if not path.is_file():
        return False
    try:
        with np.load(path) as data:
            for lag_key, metrics in rec_results.items():
                lag = lag_key.replace("mslag", "")
                key = next((k for k in (f"adjM{lag}mslag_raw", f"adjM{lag}mslag")
                            if k in data.files), None)
                active = metrics.get("activeChannelIndex")
                if key is None or active is None:
                    return False
                adj = np.asarray(data[key], dtype=float).copy()
                adj[adj < 0] = 0.0
                adj = np.nan_to_num(adj, nan=0.0)
                idx = np.asarray(active, dtype=int)
                metrics["adjMsub"] = adj[np.ix_(idx, idx)]
    except Exception:                                    # noqa: BLE001
        return False
    return True


def _load_netmet_checkpoint(
    params: Params, output_root: Path, recordings, log,
) -> tuple[dict, dict]:
    """Recordings already finished by an interrupted run: metrics and channels.

    Returns ``({name: results}, {name: channels})``, both empty unless the run
    was asked to continue. A recording is only accepted when its adjacency is
    also present, so what is skipped is genuinely complete.
    """
    if not params.continue_interrupted:
        return {}, {}

    path = output_root / "4_NetworkActivity" / NETMET_FILENAME
    if not path.is_file():
        return {}, {}
    try:
        with open(path) as fh:
            stored = json.load(fh)
    except (OSError, ValueError) as e:
        log(f"  Ignoring an unreadable {NETMET_FILENAME} ({e}) — recomputing.")
        return {}, {}

    wanted = {rec.filename for rec in recordings}
    results: dict = {}
    channels: dict = {}
    for name, rec_results in stored.items():
        if name not in wanted or not rec_results:
            continue
        restored = _to_arrays(rec_results)
        if not _restore_adjm_sub(output_root, name, restored):
            continue
        adjm = output_root / "ExperimentMatFiles" / f"{name}{ADJM_SUFFIX}"
        try:
            with np.load(adjm) as data:
                channels[name] = np.asarray(data["channels"])
        except Exception:                                # noqa: BLE001
            continue
        results[name] = restored
    if results:
        log(f"  Continuing: {len(results)} recording(s) already have network "
            f"metrics — skipping them.")
    return results, channels


def _to_arrays(obj):
    """Undo the array-to-list flattening ``_convert_numpy`` applies for JSON."""
    if isinstance(obj, dict):
        return {k: _to_arrays(v) for k, v in obj.items()}
    if isinstance(obj, list):
        arr = np.asarray(obj)
        return arr if arr.dtype != object else [_to_arrays(v) for v in obj]
    return obj


def _run_step4_network_metrics(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
    progress: "RunProgress | None" = None,
) -> None:
    log("\n=== Step 4: Network Activity ===")

    out_dir = output_root / "4_NetworkActivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    progress = progress or RunProgress()
    progress.begin("step4.compute", items=len(recordings))

    _cancel = (lambda: bool(should_cancel())) if should_cancel else None

    # What an interrupted run already finished. Seeding from it — rather than
    # only skipping — matters for phase B: the cartography boundaries are pooled
    # across the whole batch, so a continued run that saw half of it would place
    # them somewhere the original never would.
    all_results, channels_by_rec = _load_netmet_checkpoint(
        params, output_root, recordings, log)
    todo = [rec for rec in recordings if rec.filename not in all_results]
    for rec in recordings:
        if rec.filename in all_results:
            progress.item_done(rec.filename)

    def _emit(result) -> None:
        """Phase C's callback: log lines, and one step of the bar.

        Deliberately shape-agnostic — the two phases return different tuples,
        and this only needs the ends of them.
        """
        for line in result[-1]:  # log lines are always the last element
            log(line)
        progress.item_done(result[0])

    def _emit_computed(result) -> None:
        """Phase A's callback. Runs in the parent, in completion order, which is
        the only place it is safe to touch the shared dicts or the checkpoint."""
        filename, rec_results, channels_arr, logs = result
        for line in logs:
            log(line)
        if rec_results:
            all_results[filename] = rec_results
            channels_by_rec[filename] = channels_arr
            # Written after every recording so an interrupt costs the one in
            # flight, not the batch. Atomic, so a reader never sees it partial.
            try:
                _write_netmet(out_dir, all_results)
            except OSError as e:
                log(f"  Warning: could not checkpoint {NETMET_FILENAME}: {e}")
        progress.item_done(filename)

    # ── Phase A: parallel compute over recordings (map) ──────────────────────
    check_cancel(should_cancel)
    map_recordings(
        _step4_compute_one,
        [(params, rec, str(output_root)) for rec in todo],
        mem_per_task_gb=_STEP4_MEM_PER_TASK_GB,
        max_workers=params.recording_workers,
        on_result=_emit_computed,
        cancel_check=_cancel,
    )

    # ── Phase B: reduce (serial) ─────────────────────────────────────────────
    # Data-driven node-cartography boundaries: pool PC/Z across every recording
    # and re-derive the cartography boundaries (TrialLandscapeDensity), then
    # re-classify every node. Mirrors MEApipeline.m's autoSetCartographyBoundaries
    # barrier between per-recording ExtractNetMet and calNodeCartography.
    if params.auto_set_cartography_boundaries:
        # out_dir=None suppresses the pooled PC/Z landscape scatter — a figure,
        # and one the bundle's metrics can redraw.
        _apply_cartography_boundaries(
            params, all_results, log,
            out_dir=None if params.express_mode else out_dir)

    # Pool node-level metrics across every recording for the batch-scaled plot
    # bounds.
    batch_bounds = {
        m: _batch_metric_bounds(all_results, m)
        for m in ("ND", "NS", "BC", "PC", "Eloc")
    }

    # ── Phase C: parallel plot over recordings (map) ─────────────────────────
    check_cancel(should_cancel)
    progress.phase_done()
    progress.begin("step4.plot", items=len(recordings))
    plot_tasks = [
        (params, rec, all_results[rec.filename], channels_by_rec[rec.filename],
         str(output_root), batch_bounds)
        for rec in recordings
        if rec.filename in all_results
    ]
    map_recordings(
        _step4_plot_one,
        plot_tasks,
        mem_per_task_gb=_STEP4_MEM_PER_TASK_GB,
        max_workers=params.recording_workers,
        on_result=_emit,
        cancel_check=_cancel,
    )

    try:
        # Already checkpointed after each recording; written once more so a run
        # that skipped every recording still leaves the file in a known state.
        _write_netmet(out_dir, all_results)

        # Export CSVs like MATLAB's saveNetMet.m
        rec_rows = []
        node_rows = []
        for rec in recordings:
            if rec.filename not in all_results:
                continue
            rec_results = all_results[rec.filename]
            channels_arr = channels_by_rec.get(rec.filename)
            for lag, metrics in rec_results.items():
                base_info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Lag": lag}
                
                rec_row = dict(base_info)
                node_metrics = {}
                
                for k, v in metrics.items():
                    if k == "adjMsub" or k in _NMF_NON_NODE_KEYS:
                        continue
                    is_array = isinstance(v, (list, np.ndarray))
                    if not is_array or (is_array and np.size(v) <= 1):
                        val = v[0] if is_array and np.size(v) == 1 else v
                        rec_row[k] = val
                    else:
                        node_metrics[k] = v
                        
                rec_rows.append(rec_row)
                
                if node_metrics:
                    # Determine number of nodes from one of the arrays
                    num_nodes = len(next(iter(node_metrics.values())))

                    # ``Channel`` must be the real electrode ID, matching
                    # saveNetMet.m's ``Info.channels(activeNodeIndices)`` — not
                    # the node's position among the active nodes. Only the
                    # active nodes get a row, so index the recording's channel
                    # list through activeChannelIndex (0-based, as set by
                    # compute_network_metrics).
                    active_idx = metrics.get("activeChannelIndex")
                    if channels_arr is not None and active_idx is not None:
                        channel_ids = np.asarray(channels_arr).ravel()[
                            np.asarray(active_idx, dtype=int)
                        ]
                    else:
                        channel_ids = None

                    for ch in range(num_nodes):
                        node_row = dict(base_info)
                        node_row["Channel"] = (
                            channel_ids[ch] if channel_ids is not None else ch + 1
                        )
                        for k, v_arr in node_metrics.items():
                            if len(v_arr) == num_nodes:
                                node_row[k] = v_arr[ch]
                        node_rows.append(node_row)
                        
        if rec_rows:
            pd.DataFrame(rec_rows).to_csv(out_dir / "NetworkActivity_RecordingLevel.csv", index=False)
        if node_rows:
            pd.DataFrame(node_rows).to_csv(out_dir / "NetworkActivity_NodeLevel.csv", index=False)
            
    except Exception as e:
        log(f"  Warning: could not save network metrics results: {e}")

    progress.phase_done()
    progress.begin("batch", items=1)

    if not params.express_mode:
        log("  Generating group comparison plots...")
        from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons
        try:
            plot_step4_group_comparisons(
                recordings,
                all_results,
                out_dir,
                params.custom_grp_order,
                timescale=timescale_kind(params),
            )
        except Exception as e:
            log(f"  Warning: failed to generate group comparison plots: {e}")

    progress.phase_done()
    log("  Step 4 complete.")
