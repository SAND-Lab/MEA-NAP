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

from meanap.params import Params
from meanap.pipeline import network_metrics as nm
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.plotting_step4 import plot_connectivity_stats, plot_spatial_network
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

    return result


def _run_step4_network_metrics(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
) -> None:
    log("\n=== Step 4: Network Activity ===")

    mat_files_dir = output_root / "ExperimentMatFiles"
    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    out_dir = output_root / "4_NetworkActivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    min_nodes = params.min_number_of_nodes_to_cal_net_met

    all_results: dict[str, dict] = {}

    for rec in recordings:
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

        rec_out_dir = out_dir / "4A_IndividualNetworkAnalysis" / rec.group / rec.filename

        rec_results = {}
        for lag_ms in lag_values:
            key = f"adjM{lag_ms}mslag"
            if key not in adj_data:
                continue
            log(f"  [{rec.filename}] computing network metrics (lag={lag_ms}ms)...")
            metrics = compute_network_metrics(
                adj_data[key], spike_counts, duration_s,
                params.min_activity_level, min_nodes,
                exclude_edges_below_threshold=params.exclude_edges_below_threshold,
            )
            rec_results[f"{lag_ms}mslag"] = metrics

            if "adjMsub" in metrics:
                lag_dir = rec_out_dir / f"{lag_ms}mslag"
                plot_connectivity_stats(
                    metrics["adjMsub"], metrics["ND"], metrics["NS"], lag_ms,
                    rec.filename, lag_dir / f"1_adjM{lag_ms}msConnectivityStats.png",
                    exclude_edges_below_threshold=params.exclude_edges_below_threshold,
                )
                try:
                    channels_active = channels_arr[metrics["activeChannelIndex"]]
                    plot_spatial_network(
                        metrics["adjMsub"], channels_active, params.channel_layout,
                        metrics["ND"], None, "None", lag_ms, rec.filename,
                        lag_dir / "2_MEA_NetworkPlot.png",
                    )
                    plot_spatial_network(
                        metrics["adjMsub"], channels_active, params.channel_layout,
                        metrics["ND"], metrics["BC"], "Betweenness centrality",
                        lag_ms, rec.filename,
                        lag_dir / "3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png",
                    )
                except ValueError as e:
                    log(f"  [{rec.filename}] skipped spatial network plot: {e}")

        all_results[rec.filename] = rec_results

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
    except Exception as e:
        log(f"  Warning: could not save netmet_results.json: {e}")

    log("  Step 4 complete.")
