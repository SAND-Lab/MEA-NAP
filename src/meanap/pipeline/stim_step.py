"""Stimulation-analysis step of the pipeline (MEA-Stim).

Runs right after spike detection (step 1) when ``params.stimulation_mode`` is
set, mirroring MATLAB's ``MEApipeline.m`` — where ``batchDetectStim`` +
``batchProcessSpikesFromStim`` run at the end of step 1 and
``stimActivityAnalysis`` + ``saveEphysStatsStim`` at the end of step 2 (never
after step 4). This port folds all of it into one step. For each recording it
detects stimulation on the raw voltage, groups patterns, cleans the Python
step-1 spike times, computes the electrode-level response metrics + reservoir
matrices + shuffle test, writes the per-recording figures, and finally
aggregates every recording's rows into ``StimActivity_NodeLevel.csv``.

See ``src/meanap/stim/`` and ``python/MEASTIM_PORT_PLAN.md``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import load_raw_recording, load_spike_times_npz
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.stim.detection import detect_stim_times, get_stim_patterns, _matlab_mode
from meanap.stim.cleaning import clean_spikes_from_stim
from meanap.stim.psth import get_stim_artifact_duration
from meanap.stim.activity import stim_activity_analysis, write_stim_activity_csv


def _coords_for_channels(layout: str, channels: np.ndarray) -> np.ndarray:
    """Electrode coords ordered to match ``channels`` (unknown IDs → NaN)."""
    try:
        ids, xy = get_coords_from_layout(layout)
        by_id = {int(c): p for c, p in zip(ids, xy)}
    except Exception:
        by_id = {}
    return np.array([by_id.get(int(c), (np.nan, np.nan)) for c in channels], dtype=float)


def _blank_dur_mode(stim_info: list) -> float:
    durs = [np.asarray(si.non_stim_blank_ends, float).ravel()
            - np.asarray(si.non_stim_blank_starts, float).ravel()
            for si in stim_info if si.non_stim_blank_starts is not None]
    durs = np.concatenate(durs) if durs else np.array([])
    return _matlab_mode(durs) if durs.size else 0.0


def run_stim_analysis(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log=print,
    should_cancel: CancelCheck = None,
) -> None:
    """Run the stim analysis over all recordings and write the aggregate CSV."""
    log("\n=== Stimulation analysis (MEA-Stim) ===")
    if not params.raw_data:
        log("  ! Raw data folder not set — stim detection needs the raw voltage. Skipping.")
        return

    raw_dir = Path(params.raw_data)
    spike_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    indiv_dir = output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
    method = params.spikes_method
    base = params.to_stim_params_dict()

    all_rows: list[dict] = []
    n_done = 0
    for rec in recordings:
        check_cancel(should_cancel)
        raw_path = raw_dir / f"{rec.filename}.mat"
        npz_path = spike_dir / f"{rec.filename}_spikes.npz"
        if not raw_path.exists():
            log(f"  ! [{rec.filename}] raw file not found, skipping: {raw_path.name}")
            continue
        if not npz_path.exists():
            log(f"  ! [{rec.filename}] spike times not found ({npz_path.name}); run step 1 first. Skipping.")
            continue

        log(f"  [{rec.filename}] detecting stimulation…")
        dat, channels, fs = load_raw_recording(raw_path)
        dat = dat.astype(np.float64)
        coords = _coords_for_channels(params.channel_layout, channels)
        sp_params = {**base, "fs": fs}

        stim_info = detect_stim_times(dat, sp_params, channels, coords)
        stim_info, patterns = get_stim_patterns(stim_info, sp_params)
        n_stim_elec = sum(1 for s in stim_info if s.pattern and s.pattern > 0)
        log(f"    {len(patterns)} pattern(s), {n_stim_elec} stimulating electrode(s)")
        if not patterns:
            log(f"    no stimulation detected on [{rec.filename}] — skipping analysis.")
            continue

        # Python step-1 spikes for this recording, filtered to the analysis method
        spikes_full = load_spike_times_npz(npz_path)
        spikes = {c: {method: m[method]} for c, m in spikes_full.items() if method in m}
        spikes = clean_spikes_from_stim(spikes, stim_info, sp_params)

        info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div,
                "FN": [rec.filename], "duration_s": dat.shape[0] / fs}

        log(f"  [{rec.filename}] computing stim response metrics…")
        rows = stim_activity_analysis(spikes, stim_info, patterns, sp_params, info)
        all_rows.extend(rows)
        log(f"    {len(rows)} electrode rows")

        # per-recording figures
        check_cancel(should_cancel)
        try:
            from meanap.stim.pipeline import write_stim_figures
            blank_dur_mode = _blank_dur_mode(stim_info)
            artifact_dur = get_stim_artifact_duration({**sp_params, "blankDurMode": blank_dur_mode})
            dest = indiv_dir / rec.group / rec.filename
            figs = write_stim_figures(dest, stim_info, patterns, spikes, sp_params,
                                      dat, artifact_dur, info,
                                      rng=np.random.default_rng(1))
            log(f"  [{rec.filename}] wrote {len(figs)} stim figures")
        except Exception as e:   # plotting must never sink the numeric results
            log(f"  [{rec.filename}] Warning: stim plotting failed: {e}")
        n_done += 1

    if all_rows:
        csv_path = output_root / "StimActivity_NodeLevel.csv"
        write_stim_activity_csv(all_rows, csv_path)
        log(f"  Wrote {csv_path.name} ({len(all_rows)} rows across {n_done} recording(s))")
    else:
        log("  No stim rows produced (no stimulation detected in any recording).")
