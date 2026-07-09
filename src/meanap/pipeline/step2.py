from pathlib import Path
from typing import Callable

import h5py
import numpy as np
import pandas as pd
import json

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.spreadsheet import RecordingInfo, ground_spike_times_dict, parse_ground_electrodes
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.pipeline.plotting_step2 import plot_neuronal_activity_checks


# Recording-level ("whole experiment") and node-level ("single cell/node")
# field whitelists, matching ``saveEphysStats.m``'s ``NetMetricsE``/
# ``NetMetricsC`` for the ``Params.suite2pMode == 0`` (electrophysiology)
# path — the only mode this port supports.
_EPHYS_RECORDING_LEVEL_FIELDS = [
    "numActiveElec", "FRmean", "FRmedian",
    "NBurstRate", "meanNumChansInvolvedInNbursts",
    "meanNBstLengthS", "meanISIWithinNbursts_ms",
    "meanISIoutsideNbursts_ms", "CVofINBI", "fracInNburst",
    "channelAveBurstDur",
    "channelAveISIwithinBurst",
    "channelAveISIoutsideBurst",
    "channelAveFracSpikesInBursts",
]
_EPHYS_NODE_LEVEL_FIELDS = [
    "FR", "FRactive",
    "channelBurstRate",
    "channelWithinBurstFr",
    "channelBurstDur",
    "channelISIwithinBurst",
    "channeISIoutsideBurst",
    "channelFracSpikesInBursts",
]


def _save_ephys_stats_csv(
    recordings: list[RecordingInfo],
    all_ephys: dict[str, dict],
    rec_channels: dict[str, np.ndarray],
    out_dir: Path,
) -> None:
    """Port of ``saveEphysStats.m``: writes ``NeuronalActivity_RecordingLevel.csv``
    and ``NeuronalActivity_NodeLevel.csv``.
    """
    rec_rows = []
    node_rows = []
    for rec in recordings:
        ephys = all_ephys.get(rec.filename)
        if ephys is None:
            continue

        rec_row = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div}
        for field in _EPHYS_RECORDING_LEVEL_FIELDS:
            rec_row[field] = ephys.get(field)
        rec_rows.append(rec_row)

        channels = rec_channels.get(rec.filename, [])
        for i, ch in enumerate(channels):
            node_row = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Channel": ch}
            for field in _EPHYS_NODE_LEVEL_FIELDS:
                arr = ephys.get(field)
                node_row[field] = arr[i] if arr is not None and i < len(arr) else None
            node_rows.append(node_row)

    if rec_rows:
        pd.DataFrame(rec_rows).to_csv(out_dir / "NeuronalActivity_RecordingLevel.csv", index=False)
    if node_rows:
        pd.DataFrame(node_rows).to_csv(out_dir / "NeuronalActivity_NodeLevel.csv", index=False)


def convert_numpy(obj):
    """Helper to serialize numpy types to JSON."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_numpy(v) for v in obj]
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    return obj


def _run_step2_neuronal_activity(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
) -> None:
    """Run Step 2: Neuronal Activity and Burst Detection."""

    log("\n=== Step 2: Neuronal Activity & Burst Detection ===")

    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    out_dir = output_root / "2_NeuronalActivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    # We will save all Ephys results into a single dictionary mapping rec.filename -> ephys
    all_ephys = {}
    rec_channels: dict[str, np.ndarray] = {}
    # Per-recording plotting context, collected in this compute pass and drawn
    # in a second pass once the batch-wide max firing rate is known (needed for
    # the raster's "scaled to entire data batch" panel).
    plot_contexts: list[dict] = []

    for rec in recordings:
        check_cancel(should_cancel)
        npz_file = spike_data_dir / f"{rec.filename}_spikes.npz"
        if not npz_file.exists():
            log(f"  [{rec.filename}] SKIP: Spike data not found at {npz_file.name}")
            continue
            
        log(f"  [{rec.filename}] loading spike data...")
        try:
            data = np.load(npz_file)
            fs = data["fs"][0]
            n_channels = len(data["channels"])
        except Exception as e:
            log(f"  [{rec.filename}] ERROR loading npz: {e}")
            continue
            
        # Get duration_s by peeking at HDF5 raw data shape
        raw_path = Path(params.raw_data) / f"{rec.filename}.mat"
        try:
            with h5py.File(raw_path, "r") as f:
                n_samples = f["dat"].shape[0]
                if n_samples == 64:  # Transposed check
                    n_samples = f["dat"].shape[1]
            duration_s = n_samples / fs
        except Exception:
            # Fallback if raw file not found/readable
            log(f"  [{rec.filename}] Warning: could not read raw file, guessing duration from max spike time")
            duration_s = 0.0
            
        spike_times_full = load_spike_times_npz(npz_file)
        
        # Filter down to the chosen method
        method = params.spikes_method
        spike_times_dict = {}
        for ch in range(n_channels):
            # Keys in spike_times_full might be string or int
            # Our loading code casts to int, so ch should match
            if ch in spike_times_full and method in spike_times_full[ch]:
                times = spike_times_full[ch][method]
                spike_times_dict[ch] = times
                if duration_s == 0.0 and len(times) > 0:
                    duration_s = max(duration_s, np.max(times))
            else:
                spike_times_dict[ch] = np.array([])
                
        if duration_s == 0.0:
            duration_s = 60.0  # safe fallback

        ground_electrodes = parse_ground_electrodes(rec.ground)
        if ground_electrodes:
            spike_times_dict = ground_spike_times_dict(spike_times_dict, data["channels"], ground_electrodes)

        log(f"  [{rec.filename}] calculating firing rates and bursts (method={method})...")
        ephys = firing_rates_bursts(spike_times_dict, n_channels, fs, duration_s, params)
        
        all_ephys[rec.filename] = ephys
        rec_channels[rec.filename] = data["channels"]
        plot_contexts.append({
            "rec": rec,
            "spike_times_dict": spike_times_dict,
            "n_channels": n_channels,
            "chs": data["channels"],
            "fs": fs,
            "duration_s": duration_s,
            "ephys": ephys,
        })

    # Batch-wide max of each per-channel metric (MATLAB's maxValStruct /
    # valsTogetMax): the shared color-scale ceiling for every recording's
    # "scaled to entire dataset" heatmap panel (and, for FR, the raster's
    # "scaled to entire data batch" panel).
    batch_max = {}
    for metric in (
        "FR", "channelBurstRate", "channelBurstDur",
        "channelFracSpikesInBursts", "channelISIwithinBurst", "channeISIoutsideBurst",
    ):
        maxes = [
            float(np.nanmax(ctx["ephys"][metric]))
            for ctx in plot_contexts
            if ctx["ephys"].get(metric) is not None and np.size(ctx["ephys"][metric]) > 0
            and np.any(np.isfinite(ctx["ephys"][metric]))
        ]
        batch_max[metric] = max(maxes) if maxes else None
    spike_freq_max = batch_max.get("FR")

    for ctx in plot_contexts:
        check_cancel(should_cancel)
        log(f"  [{ctx['rec'].filename}] generating neuronal activity plots...")
        plot_neuronal_activity_checks(
            rec=ctx["rec"],
            params=params,
            spike_times_dict=ctx["spike_times_dict"],
            n_channels=ctx["n_channels"],
            chs=ctx["chs"],
            fs=ctx["fs"],
            duration_s=ctx["duration_s"],
            ephys=ctx["ephys"],
            output_root=out_dir / "2A_IndividualNeuronalAnalysis",
            spike_freq_max=spike_freq_max,
            batch_max=batch_max,
        )

    log("  Generating group comparison plots...")
    from meanap.pipeline.plotting_step2 import plot_step2_group_comparisons
    try:
        plot_step2_group_comparisons(
            recordings,
            all_ephys,
            out_dir,
            params.custom_grp_order
        )
    except Exception as e:
        log(f"  Warning: failed to generate group comparison plots: {e}")
        
    try:
        with open(out_dir / "ephys_results.json", "w") as f:
            json.dump(convert_numpy(all_ephys), f, indent=2)
    except Exception as e:
        log(f"  Warning: could not save ephys_results.json: {e}")

    try:
        _save_ephys_stats_csv(recordings, all_ephys, rec_channels, out_dir)
    except Exception as e:
        log(f"  Warning: could not save NeuronalActivity CSVs: {e}")

    log("  Step 2 complete.")
