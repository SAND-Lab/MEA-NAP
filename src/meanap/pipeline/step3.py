"""Step 3: functional connectivity (adjacency matrices), port of the
``generateAdjMs.m`` / ``adjM_thr_parallel.m`` portion of ``MEApipeline.m``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import h5py
import numpy as np

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.probabilistic_threshold import adjm_thr
from meanap.pipeline.spreadsheet import RecordingInfo, ground_spike_times_dict, parse_ground_electrodes


def _run_step3_functional_connectivity(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
) -> None:
    """Run Step 3: compute STTC adjacency matrices for each recording/lag.

    Saves one ``<recording>_adjM.npz`` per recording under
    ``ExperimentMatFiles/``, with ``adjM{lag}mslag`` (probabilistically
    thresholded) and ``adjM{lag}mslag_raw`` (unthresholded, deterministic —
    the array with exact MATLAB parity) for each lag in
    ``params.func_con_lag_val``.
    """
    log("\n=== Step 3: Functional Connectivity ===")

    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    mat_files_dir = output_root / "ExperimentMatFiles"
    mat_files_dir.mkdir(parents=True, exist_ok=True)

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    rep_num = params.prob_thresh_rep_num
    tail = params.prob_thresh_tail

    for rec in recordings:
        check_cancel(should_cancel)
        npz_file = spike_data_dir / f"{rec.filename}_spikes.npz"
        if not npz_file.exists():
            log(f"  [{rec.filename}] SKIP: Spike data not found at {npz_file.name}")
            continue

        log(f"  [{rec.filename}] loading spike data...")
        data = np.load(npz_file)
        fs = float(data["fs"][0])
        n_channels = len(data["channels"])

        raw_path = Path(params.raw_data) / f"{rec.filename}.mat"
        try:
            with h5py.File(raw_path, "r") as f:
                n_samples = f["dat"].shape[0]
                if n_samples == n_channels:
                    n_samples = f["dat"].shape[1]
            duration_s = n_samples / fs
        except Exception:
            log(f"  [{rec.filename}] Warning: could not read raw file for duration")
            continue

        spike_times_full = load_spike_times_npz(npz_file)
        spike_times_dict = {
            ch: spike_times_full.get(ch, {}).get(method, np.array([]))
            for ch in range(n_channels)
        }
        ground_electrodes = parse_ground_electrodes(rec.ground)
        if ground_electrodes:
            spike_times_dict = ground_spike_times_dict(spike_times_dict, data["channels"], ground_electrodes)

        out_arrays: dict[str, np.ndarray] = {}
        rng = np.random.default_rng()
        for lag_ms in lag_values:
            check_cancel(should_cancel)
            log(f"  [{rec.filename}] computing adjacency matrix (lag={lag_ms}ms, "
                f"{rep_num} shuffles)...")
            adj_m, adj_m_ci = adjm_thr(
                spike_times_dict, n_channels, lag_ms, tail, fs, duration_s, rep_num, rng=rng,
            )
            out_arrays[f"adjM{lag_ms}mslag"] = adj_m_ci
            out_arrays[f"adjM{lag_ms}mslag_raw"] = adj_m

        out_path = mat_files_dir / f"{rec.filename}_adjM.npz"
        np.savez(out_path, channels=data["channels"], **out_arrays)
        log(f"  [{rec.filename}] saved → {out_path.relative_to(output_root)}")

    log("  Step 3 complete.")
