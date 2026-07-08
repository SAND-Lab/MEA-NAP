"""Step 4: network activity metrics, port of the deterministic portion of
``ExtractNetMet.m`` (see ``network_metrics.py`` for exactly which metrics
are and aren't in scope).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import h5py
import numpy as np
import pandas as pd

from meanap.params import Params
from meanap.pipeline import network_metrics as nm
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.modularity import mod_consensus_cluster_iterate
from meanap.pipeline.plotting_step4 import (
    plot_circular_cartography_network, plot_circular_module_network,
    plot_connectivity_stats, plot_graph_metrics_by_node,
    plot_node_cartography, plot_spatial_network, plot_spatial_network_combined,
)
from meanap.pipeline.spreadsheet import RecordingInfo


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
    result["CC"] = nm.clustering_coef_wu(sub)
    result["CCmean"] = float(np.mean(result["CC"]))

    length_mat = nm.weight_conversion_lengths(sub)
    dist = nm.distance_wei(length_mat)
    pl, _ = nm.charpath(dist)
    result["PL"] = pl

    result["Eglob"] = nm.efficiency_wei_global(sub)

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


def _plot_recording_lag(
    rec: RecordingInfo,
    lag_ms,
    metrics: dict,
    channels_arr: np.ndarray,
    params: Params,
    out_dir: Path,
    log: Callable[[str], None],
    batch_bounds: dict[str, tuple[float, float] | None],
) -> None:
    """Draw every step-4A plot for one recording/lag.

    Produces both the individual-scaled plots (each colored/sized to this
    recording's own range) and, for the spatial network plots, ``_scaled``
    variants whose node-size / node-color / edge scales come from
    ``batch_bounds`` (the whole batch's pooled range) so they can be compared
    across recordings — matching MATLAB's ``useMinMaxBoundsForPlots`` pass in
    ``PlotIndvNetMet.m``.
    """
    if "adjMsub" not in metrics:
        return

    rec_out_dir = out_dir / "4A_IndividualNetworkAnalysis" / rec.group / rec.filename
    lag_dir = rec_out_dir / f"{lag_ms}mslag"

    plot_connectivity_stats(
        metrics["adjMsub"], metrics["ND"], metrics["NS"], lag_ms,
        rec.filename, lag_dir / f"1_adjM{lag_ms}msConnectivityStats.png",
        exclude_edges_below_threshold=params.exclude_edges_below_threshold,
    )

    nd_max = batch_bounds["ND"][1] if batch_bounds.get("ND") else None
    ns_max = batch_bounds["NS"][1] if batch_bounds.get("NS") else None

    # (filename, color metric key, color legend name, size metric key,
    #  size legend name, size batch-max) for each spatial network plot; the
    #  ``_scaled`` filename is derived by inserting "_scaled" after the number.
    spatial_specs = [
        ("2_MEA_NetworkPlot.png", None, "None", "ND", "node degree", nd_max),
        ("3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png", "BC",
         "Betweenness centrality", "ND", "node degree", nd_max),
        ("4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png", "PC",
         "Participation coefficient", "ND", "node degree", nd_max),
        ("5_MEA_NetworkPlotNodestrengthLocalefficiency.png", "Eloc",
         "Local efficiency", "NS", "node strength", ns_max),
        # Controllability plots are only produced when those (optional) metrics
        # are present; the loop's ``color_key not in metrics`` guard skips them
        # otherwise. No batch bound is pooled for these, so their scaled
        # variant shares only the node-size and edge scale, not the color scale.
        ("10_MEA_NetworkPlotNodedegreeAveragecontrollability.png", "aveControl",
         "Average controllability", "ND", "node degree", nd_max),
        ("11_MEA_NetworkPlotNodedegreeModalcontrollability.png", "modalControl",
         "Modal controllability", "ND", "node degree", nd_max),
    ]

    try:
        channels_active = channels_arr[metrics["activeChannelIndex"]]
        for fname, color_key, color_name, size_key, size_name, size_max in spatial_specs:
            if size_key not in metrics:
                continue
            if color_key is not None and color_key not in metrics:
                continue
            z = metrics[size_key]
            z2 = metrics[color_key] if color_key is not None else None

            # Individual-scaled (this recording's own range).
            plot_spatial_network(
                metrics["adjMsub"], channels_active, params.channel_layout,
                z, z2, color_name, lag_ms, rec.filename,
                lag_dir / fname, z_name=size_name,
            )

            # Batch-scaled variant + side-by-side combined figure, if we have a
            # batch max for the size metric.
            if size_max is not None:
                color_bounds = batch_bounds.get(color_key) if color_key is not None else None
                scaled_name = fname.replace("_MEA_NetworkPlot", "_scaled_MEA_NetworkPlot", 1)
                plot_spatial_network(
                    metrics["adjMsub"], channels_active, params.channel_layout,
                    z, z2, color_name, lag_ms, rec.filename,
                    lag_dir / scaled_name, z_name=size_name,
                    z_scale_override=size_max,
                    z2_bounds_override=color_bounds,
                    edge_bounds_override=_EDGE_BATCH_BOUNDS,
                )
                combined_name = fname.replace("_MEA_NetworkPlot", "_combined_MEA_NetworkPlot", 1)
                plot_spatial_network_combined(
                    metrics["adjMsub"], channels_active, params.channel_layout,
                    z, z2, color_name, lag_ms, rec.filename,
                    lag_dir / combined_name, z_name=size_name,
                    z_scale_override=size_max,
                    z2_bounds_override=color_bounds,
                    edge_bounds_override=_EDGE_BATCH_BOUNDS,
                )
    except ValueError as e:
        log(f"  [{rec.filename}] skipped spatial network plot: {e}")

    if "PC" in metrics:
        plot_node_cartography(
            metrics["PC"], metrics["Z"], params, lag_ms, rec.filename,
            lag_dir / f"9_adjM{lag_ms}msNodeCartography.png",
        )

    if "NdCartDiv" in metrics:
        plot_circular_cartography_network(
            metrics["adjMsub"], metrics["NdCartDiv"],
            lag_ms, rec.filename,
            lag_dir / "9_circular_NetworkPlotNodeCartography.png",
            edge_thresh=params.exclude_edges_below_threshold * 0.0001,
        )

    if "Ci" in metrics:
        plot_circular_module_network(
            metrics["adjMsub"], metrics["Ci"], metrics["ND"],
            lag_ms, rec.filename,
            lag_dir / "6_circular_NetworkPlotNodedegreeModule.png",
        )

    try:
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
            out_path=lag_dir / f"7_adjM{lag_ms}msGraphMetricsByNode.png",
        )
    except Exception as e:
        log(f"  [{rec.filename}] skipped graph-metrics-by-node plot: {e}")


def _run_step4_network_metrics(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
) -> None:
    log("\n=== Step 4: Network Activity ===")

    mat_files_dir = output_root / "ExperimentMatFiles"
    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    out_dir = output_root / "4_NetworkActivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    min_nodes = params.min_number_of_nodes_to_cal_net_met
    rng = np.random.default_rng()

    all_results: dict[str, dict] = {}
    # (rec, lag_ms, metrics, channels_arr) tuples collected in the compute pass
    # and drawn in a second pass once batch-wide metric bounds are known.
    plot_jobs: list[tuple] = []

    for rec in recordings:
        check_cancel(should_cancel)
        adj_path = mat_files_dir / f"{rec.filename}_adjM.npz"
        spike_path = spike_data_dir / f"{rec.filename}_spikes.npz"
        if not adj_path.exists():
            log(f"  [{rec.filename}] SKIP: adjacency matrices not found at {adj_path.name}")
            continue
        if not spike_path.exists():
            log(f"  [{rec.filename}] SKIP: spike data not found at {spike_path.name}")
            continue

        log(f"  [{rec.filename}] loading adjacency matrices...")
        adj_data = np.load(adj_path)
        spike_data = np.load(spike_path)
        fs = float(spike_data["fs"][0])
        channels_arr = spike_data["channels"]
        n_channels = len(channels_arr)

        raw_path = Path(params.raw_data) / f"{rec.filename}.mat"
        try:
            with h5py.File(raw_path, "r") as f:
                n_samples = f["dat"].shape[0]
                if n_samples == n_channels:
                    n_samples = f["dat"].shape[1]
            duration_s = n_samples / fs
        except Exception:
            log(f"  [{rec.filename}] SKIP: could not read raw file for duration")
            continue

        spike_times_full = load_spike_times_npz(spike_path)
        spike_counts = np.array([
            len(spike_times_full.get(ch, {}).get(method, ())) for ch in range(n_channels)
        ])
        
        spike_times_list = [
            spike_times_full.get(ch, {}).get(method, np.array([])) for ch in range(n_channels)
        ]
        
        try:
            eff_rank = nm.effective_rank(
                spike_times_list, fs, duration_s, 
                params.eff_rank_downsample_freq, params.eff_rank_cal_method
            )
        except Exception as e:
            log(f"  [{rec.filename}] WARNING: could not compute effective rank: {e}")
            eff_rank = float('nan')

        rec_results = {}
        for lag_ms in lag_values:
            check_cancel(should_cancel)
            key = f"adjM{lag_ms}mslag"
            if key not in adj_data:
                continue
            log(f"  [{rec.filename}] computing network metrics (lag={lag_ms}ms)...")
            metrics = compute_network_metrics(
                adj_data[key], spike_counts, duration_s,
                params.min_activity_level, min_nodes,
                exclude_edges_below_threshold=params.exclude_edges_below_threshold,
                params=params, rng=rng,
            )
            metrics["effRank"] = eff_rank
            rec_results[f"{lag_ms}mslag"] = metrics
            # Defer plotting to a second pass: the "scaled to entire data batch"
            # variants need batch-wide metric bounds, which aren't known until
            # every recording has been computed (see below).
            plot_jobs.append((rec, lag_ms, metrics, channels_arr))

        all_results[rec.filename] = rec_results

    # Second pass: now that all recordings are computed, pool the node-level
    # metrics to get batch-wide bounds, then draw every recording's plots
    # (individual-scaled + the batch-scaled ``_scaled`` variants).
    batch_bounds = {
        m: _batch_metric_bounds(all_results, m)
        for m in ("ND", "NS", "BC", "PC", "Eloc")
    }
    for rec, lag_ms, metrics, channels_arr in plot_jobs:
        check_cancel(should_cancel)
        log(f"  [{rec.filename}] plotting network metrics (lag={lag_ms}ms)...")
        _plot_recording_lag(
            rec, lag_ms, metrics, channels_arr, params, out_dir, log, batch_bounds,
        )

    try:
        json_results = {
            rec_name: {
                lag: {k: v for k, v in metrics.items() if k != "adjMsub"}
                for lag, metrics in rec_results.items()
            }
            for rec_name, rec_results in all_results.items()
        }
        with open(out_dir / "netmet_results.json", "w") as fh:
            json.dump(_convert_numpy(json_results), fh, indent=2)

        # Export CSVs like MATLAB's saveNetMet.m
        rec_rows = []
        node_rows = []
        for rec in recordings:
            if rec.filename not in all_results:
                continue
            rec_results = all_results[rec.filename]
            for lag, metrics in rec_results.items():
                base_info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Lag": lag}
                
                rec_row = dict(base_info)
                node_metrics = {}
                
                for k, v in metrics.items():
                    if k == "adjMsub":
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
                    for ch in range(num_nodes):
                        node_row = dict(base_info)
                        node_row["Channel"] = ch + 1
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

    log("  Generating group comparison plots...")
    from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons
    try:
        plot_step4_group_comparisons(
            recordings,
            all_results,
            out_dir,
            params.custom_grp_order
        )
    except Exception as e:
        log(f"  Warning: failed to generate group comparison plots: {e}")

    log("  Step 4 complete.")
