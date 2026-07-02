"""Top-level pipeline runner, orchestrating steps to mirror ``MEApipeline.m``."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable

from meanap.params import Params
from meanap.pipeline.io import load_raw_recording, save_spike_times_npz
from meanap.pipeline.step2 import _run_step2_neuronal_activity
from meanap.pipeline.step3 import _run_step3_functional_connectivity
from meanap.pipeline.step4 import _run_step4_network_metrics
from meanap.pipeline.output_folders import create_output_folders
from meanap.pipeline.spike_detection import SpikeDetectionParams, detect_spikes_recording
from meanap.pipeline.spreadsheet import RecordingInfo, read_recording_csv


def default_output_folder_name() -> str:
    """Default output folder name, matching MATLAB's ``'OutputData' + ddmmmyyyy``."""
    return "OutputData" + datetime.date.today().strftime("%d%b%Y")


def run_pipeline(params: Params, log: Callable[[str], None] = print) -> Path:
    """Run the pipeline steps in ``[start_analysis_step, stop_analysis_step]``.

    Creates the same output folder tree as the MATLAB pipeline
    (``CreateOutputFolders.m``) up front, then runs each requested step.
    Steps 1-4 are all implemented (see ``python/PIPELINE_PORT_STATUS.md`` for
    which parts of each step have exact MATLAB parity vs. are deterministic
    approximations / not yet ported).
    """
    if not params.spreadsheet_file_name:
        raise ValueError("Spreadsheet file must be set")
    if not params.output_data_folder:
        raise ValueError("Output data folder must be set")

    recordings = read_recording_csv(params.spreadsheet_file_name, params.spreadsheet_range)
    if not recordings:
        raise ValueError("No recordings found in the given spreadsheet range")
    group_names = sorted({r.group for r in recordings})

    folder_name = params.output_data_folder_name or default_output_folder_name()
    output_root = create_output_folders(
        Path(params.output_data_folder), folder_name, group_names,
        include_not_box_plots=params.include_not_box_plots,
    )
    log(f"Output folder ready: {output_root}")

    start = params.start_analysis_step
    stop = params.stop_analysis_step

    if start <= 1 <= stop:
        _run_step1_spike_detection(params, recordings, output_root, log)
    else:
        log("Skipping step 1 (spike detection) — outside the selected step range.")

    if start <= 2 <= stop:
        _run_step2_neuronal_activity(params, recordings, output_root, log)
    else:
        log("Skipping step 2 (neuronal activity) — outside the selected step range.")

    if start <= 3 <= stop:
        _run_step3_functional_connectivity(params, recordings, output_root, log)
    else:
        log("Skipping step 3 (functional connectivity) — outside the selected step range.")

    if start <= 4 <= stop:
        _run_step4_network_metrics(params, recordings, output_root, log)
    else:
        log("Skipping step 4 (network activity) — outside the selected step range.")

    return output_root


def _run_step1_spike_detection(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
) -> None:
    if not params.raw_data:
        raise ValueError("Raw data folder must be set to run step 1 (spike detection)")

    spike_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    raw_dir = Path(params.raw_data)
    cost_list = params.cost_list if isinstance(params.cost_list, list) else [params.cost_list]

    for rec in recordings:
        raw_path = raw_dir / f"{rec.filename}.mat"
        if not raw_path.exists():
            log(f"  ! raw file not found, skipping: {raw_path.name}")
            continue

        log(f"  [{rec.filename}] loading raw data…")
        dat, channels, fs = load_raw_recording(raw_path)

        detect_params = SpikeDetectionParams(
            fs=fs,
            thresholds=params.thresholds,
            wname_list=params.wname_list,
            cost_list=cost_list,
            filter_low_pass=params.filter_low_pass,
            filter_high_pass=params.filter_high_pass,
            ref_period_ms=params.ref_period,
            min_peak_thr_mult=params.min_peak_thr_multiplier,
            max_peak_thr_mult=params.max_peak_thr_multiplier,
            pos_peak_thr_mult=params.pos_peak_thr_multiplier,
            remove_artifacts=params.remove_artifacts,
        )

        log(f"  [{rec.filename}] detecting spikes ({len(channels)} channels)…")
        result = detect_spikes_recording(dat, channels, fs, detect_params)

        out_path = spike_dir / f"{rec.filename}_spikes.npz"
        save_spike_times_npz(out_path, result.spike_times, channels, fs)
        log(f"  [{rec.filename}] saved → {out_path.relative_to(output_root)}")

        # Mirrors MEApipeline.m creating a per-recording checks folder here;
        # the check plots themselves aren't ported yet.
        check_dir = output_root / "1_SpikeDetection" / "1B_SpikeDetectionChecks" / rec.group / rec.filename
        check_dir.mkdir(parents=True, exist_ok=True)
        
        from meanap.pipeline.plotting import plot_spike_detection_checks
        log(f"  [{rec.filename}] generating spike detection check plots…")
        plot_spike_detection_checks(dat, result, params, rec.filename, check_dir)
