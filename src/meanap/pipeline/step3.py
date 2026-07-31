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

import numpy as np

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import load_spike_times_npz, resolve_duration_s
from meanap.pipeline.parallel import map_recordings
from meanap.pipeline.probabilistic_threshold import adjm_thr
from meanap.pipeline.resume import build_input_locator
from meanap.pipeline.rng import make_rng
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
    locator = build_input_locator(params, output_root)
    mat_files_dir = output_root / "ExperimentMatFiles"

    method = params.spikes_method
    lag_values = params.func_con_lag_val
    rep_num = params.prob_thresh_rep_num
    tail = params.prob_thresh_tail
    plot_checks = bool(getattr(params, "prob_thresh_plot_checks", False))

    logs: list[str] = []
    npz_file = locator.spike_file(rec.filename)
    if npz_file is None:
        logs.append(f"  [{rec.filename}] SKIP: spike data not found ({rec.filename}_spikes.npz)")
        return rec.filename, logs

    data = np.load(npz_file)
    fs = float(data["fs"][0])
    n_channels = len(data["channels"])

    duration_s, _ = resolve_duration_s(
        data, Path(params.raw_data) / f"{rec.filename}.mat", fs, n_channels,
    )
    if duration_s is None:
        logs.append(f"  [{rec.filename}] SKIP: recording duration unavailable "
                    f"(not in the spike file, and the raw recording could not be read)")
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
    # Derived from the recording name, not from a shared stream, so results
    # don't depend on how many workers the pool decided to use or what order
    # recordings completed in.
    rng = make_rng(params.random_seed, "step3", rec.filename)
    check_dir = output_root / "3_EdgeThresholdingCheck"
    for lag_ms in lag_values:
        logs.append(f"  [{rec.filename}] computing adjacency matrix (lag={lag_ms}ms, "
                    f"{rep_num} shuffles)...")
        if plot_checks:
            adj_m, adj_m_ci, rep_val, dist1 = adjm_thr(
                spike_times_dict, n_channels, lag_ms, tail, fs, duration_s, rep_num,
                rng=rng, collect_check_snapshots=True,
            )
            # Deferred import: plotting pulls in matplotlib, only needed when checks are on
            from meanap.pipeline.plotting_step3 import plot_prob_thresh_check
            check_dir.mkdir(parents=True, exist_ok=True)
            plot_prob_thresh_check(
                dist1, rep_val, adj_m,
                check_dir / f"{rec.filename}{lag_ms}msLagProbThreshCheck.png",
                rng=rng,
            )
        else:
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
