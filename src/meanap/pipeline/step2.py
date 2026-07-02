from pathlib import Path
from typing import Callable

import h5py
import numpy as np
import json

from meanap.params import Params
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.pipeline.plotting_step2 import plot_neuronal_activity_checks


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
) -> None:
    """Run Step 2: Neuronal Activity and Burst Detection."""
    
    log("\n=== Step 2: Neuronal Activity & Burst Detection ===")
    
    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    out_dir = output_root / "2_NeuronalActivity"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # We will save all Ephys results into a single dictionary mapping rec.filename -> ephys
    all_ephys = {}
    
    for rec in recordings:
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
            
        log(f"  [{rec.filename}] calculating firing rates and bursts (method={method})...")
        ephys = firing_rates_bursts(spike_times_dict, n_channels, fs, duration_s, params)
        
        all_ephys[rec.filename] = ephys
        
        # Generate Step 2 plots
        log(f"  [{rec.filename}] generating neuronal activity plots...")
        plot_neuronal_activity_checks(
            rec=rec,
            params=params,
            spike_times_dict=spike_times_dict,
            n_channels=n_channels,
            chs=data["channels"],
            fs=fs,
            duration_s=duration_s,
            ephys=ephys,
            output_root=out_dir / "2A_IndividualNeuronalAnalysis"
        )
        
    log("  Step 2 complete.")
    
    try:
        with open(out_dir / "ephys_results.json", "w") as f:
            json.dump(convert_numpy(all_ephys), f, indent=2)
    except Exception as e:
        log(f"  Warning: could not save ephys_results.json: {e}")
