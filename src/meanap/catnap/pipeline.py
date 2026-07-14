"""CAT-NAP pipeline orchestrator (``Params.suite2pMode == 1`` path).

Mirrors the ``suite2pMode`` branches scattered through ``MEApipeline.m``: for
each suite2p recording it denoises (if needed), builds the adjacency matrices +
activity properties (:func:`~meanap.catnap.adjacency.suite2p_to_adjm`), computes
the two-photon activity stats (:func:`~meanap.catnap.stats.calc_twop_activity_stats`),
and then feeds the **shared** step-4 network-metric routine
(:func:`meanap.pipeline.step4.compute_network_metrics`) — the calcium-imaging
counterpart of running steps 1→4 on electrophysiology data.

Network-plot generation (which needs the suite2p ``coords`` rather than an MEA
channel layout) is deferred to a later phase; this orchestrator produces the
metrics, JSON, and CSVs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from meanap.params import Params
from meanap.catnap.adjacency import suite2p_to_adjm
from meanap.catnap.loader import load_suite2p
from meanap.catnap.stats import calc_twop_activity_stats
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.pipeline.step4 import compute_network_metrics, _convert_numpy, _NMF_NON_NODE_KEYS

_NEEDS_DENOISING = ("peaks", "denoised F", "spks")


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
    """Run the CAT-NAP path over all recordings, writing NetMet JSON + CSVs."""
    from meanap.catnap.denoising import process_suite2p_folder

    if rng is None:
        rng = np.random.default_rng()

    lag_values = params.func_con_lag_val
    min_nodes = params.min_number_of_nodes_to_cal_net_met
    net_dir = output_root / "4_NetworkActivity"
    net_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, dict] = {}
    all_stats: dict[str, dict] = {}
    all_coords: dict[str, np.ndarray] = {}
    all_channels: dict[str, np.ndarray] = {}

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
        all_coords[rec.filename] = res.coords
        all_channels[rec.filename] = res.channels

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

        _plot_recording(params, rec, data, res, rec_results, output_root, log)

    _save_catnap_results(recordings, all_results, all_stats, net_dir, log)
    log("  CAT-NAP pipeline complete.")


def _plot_recording(params, rec, data, res, rec_results, output_root, log) -> None:
    """Per-unit trace figures + per-lag spatial network plots (Phase 5).

    The network plot reuses the shared step-4 renderer via its
    ``coords_override`` path, feeding suite2p cell centroids
    (``res.coords``) instead of an MEA channel layout.
    """
    from meanap.catnap.plotting import plot_2p_traces
    from meanap.pipeline.plotting_step4 import plot_spatial_network

    try:
        trace_dir = (output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
                     / rec.group / rec.filename)
        log(f"  [{rec.filename}] plotting 2P traces…")
        plot_2p_traces(data, trace_dir, rec.filename, num_traces=params.num_2p_traces)
    except Exception as e:
        log(f"  [{rec.filename}] warning: 2P trace plots failed: {e}")

    for lag_key, metrics in rec_results.items():
        if "adjMsub" not in metrics:
            continue
        lag_ms = int(lag_key.replace("mslag", ""))
        idx = metrics["activeChannelIndex"]
        try:
            plot_spatial_network(
                metrics["adjMsub"], res.channels[idx], params.channel_layout,
                metrics["ND"], None, "None", lag_ms, rec.filename,
                (output_root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                 / rec.group / rec.filename / f"{lag_ms}mslag" / "2_MEA_NetworkPlot.png"),
                z_name="node degree",
                coords_override=res.coords[idx],
            )
        except Exception as e:
            log(f"  [{rec.filename}] warning: network plot (lag={lag_ms}) failed: {e}")


def _save_catnap_results(
    recordings: list[RecordingInfo],
    all_results: dict[str, dict],
    all_stats: dict[str, dict],
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

        # Two-photon activity stats (step-2 equivalent).
        stats_rows = [dict({"FileName": r.filename, "Grp": r.group, "DIV": r.div},
                           **{k: v for k, v in all_stats[r.filename].items()
                              if np.size(v) <= 1})
                      for r in recordings if r.filename in all_stats]
        if stats_rows:
            pd.DataFrame(stats_rows).to_csv(net_dir.parent / "2_NeuronalActivity"
                                            / "TwoPhotonActivity_RecordingLevel.csv", index=False)
    except Exception as e:
        log(f"  Warning: could not save CAT-NAP results: {e}")
