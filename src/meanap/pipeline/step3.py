"""Step 3: functional connectivity (adjacency matrices), port of the
``generateAdjMs.m`` / ``adjM_thr_parallel.m`` portion of ``MEApipeline.m``.

Recordings are independent (each reads its own Step 1 spike ``.npz`` and writes
its own ``_adjM.npz``), so this step is a pure parallel map over recordings —
no cross-recording reduce. The per-recording work is CPU-bound and low-RAM
(spike times + 64x64 matrices), and its hot path (``adjm_thr``'s circular-shift
surrogates) is pure Python, so it runs in separate *processes* (see
``pipeline/parallel.py`` for why threads wouldn't help here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import h5py
import numpy as np

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import load_spike_times_npz
from meanap.pipeline.parallel import map_recordings
from meanap.pipeline.probabilistic_threshold import adjm_thr
from meanap.pipeline.spreadsheet import RecordingInfo, ground_spike_times_dict, parse_ground_electrodes

# Peak per-worker RAM for Step 3: spike times (sparse) + a few 64x64xrep_num
# surrogate stacks (~6 MB at rep_num=200). Tiny — worker count is CPU-limited.
_STEP3_MEM_PER_TASK_GB = 0.3


def _step3_one_recording(task: tuple[Params, RecordingInfo, str]) -> tuple[str, list[str]]:
    """Compute + save one recording's adjacency matrices. Module-level and
    picklable so it can run in a ``spawn``ed worker process. Returns the
    recording name and the log lines it produced (streamed back and printed
    in the parent, in completion order)."""
    params, rec, output_root_str = task
    output_root = Path(output_root_str)
    spike_data_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    mat_files_dir = output_root / "ExperimentMatFiles"

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    rep_num = params.prob_thresh_rep_num
    tail = params.prob_thresh_tail

    logs: list[str] = []
    npz_file = spike_data_dir / f"{rec.filename}_spikes.npz"
    if not npz_file.exists():
        logs.append(f"  [{rec.filename}] SKIP: Spike data not found at {npz_file.name}")
        return rec.filename, logs

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
        logs.append(f"  [{rec.filename}] Warning: could not read raw file for duration")
        return rec.filename, logs

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
        logs.append(f"  [{rec.filename}] computing adjacency matrix (lag={lag_ms}ms, "
                    f"{rep_num} shuffles)...")
        adj_m, adj_m_ci = adjm_thr(
            spike_times_dict, n_channels, lag_ms, tail, fs, duration_s, rep_num, rng=rng,
        )
        out_arrays[f"adjM{lag_ms}mslag"] = adj_m_ci
        out_arrays[f"adjM{lag_ms}mslag_raw"] = adj_m

    out_path = mat_files_dir / f"{rec.filename}_adjM.npz"
    np.savez(out_path, channels=data["channels"], **out_arrays)
    logs.append(f"  [{rec.filename}] saved → {out_path.relative_to(output_root)}")
    return rec.filename, logs


def _run_step3_functional_connectivity(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
) -> None:
    """Run Step 3 over all recordings as a RAM/CPU-aware parallel map.

    Saves one ``<recording>_adjM.npz`` per recording under
    ``ExperimentMatFiles/``, with ``adjM{lag}mslag`` (probabilistically
    thresholded) and ``adjM{lag}mslag_raw`` (unthresholded, deterministic —
    the array with exact MATLAB parity) for each lag in
    ``params.func_con_lag_val``.
    """
    log("\n=== Step 3: Functional Connectivity ===")
    check_cancel(should_cancel)

    (output_root / "ExperimentMatFiles").mkdir(parents=True, exist_ok=True)

    tasks = [(params, rec, str(output_root)) for rec in recordings]

    def _emit(result: tuple[str, list[str]]) -> None:
        for line in result[1]:
            log(line)

    map_recordings(
        _step3_one_recording,
        tasks,
        mem_per_task_gb=_STEP3_MEM_PER_TASK_GB,
        max_workers=params.recording_workers,
        on_result=_emit,
        cancel_check=(lambda: bool(should_cancel())) if should_cancel else None,
    )

    log("  Step 3 complete.")
