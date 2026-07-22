"""End-to-end MEA-Stim orchestration.

Ties together the ported stages in the order ``MEApipeline.m`` runs them for
``Params.stimulationMode``:

    detect stim (raw voltage)  ->  group patterns  ->  clean spikes
        ->  per-electrode activity metrics  ->  reservoir matrices
        ->  circular-shift shuffle test  ->  aggregate CSV

Spike times are loaded from the recording's ``ExperimentMatFiles`` `.mat`
(method ``params['SpikesMethod']``); grounding/cleaning is reapplied here, as
this port loads spikes fresh rather than threading one chained `.mat` like
MATLAB. Plots (``plotting.py``) and pattern decoding are separate opt-in steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..pipeline.io import load_raw_recording, load_spike_times_mat
from .detection import detect_stim_times, get_stim_patterns
from .cleaning import clean_spikes_from_stim
from .activity import stim_activity_analysis, write_stim_activity_csv
from .reservoir import compute_reservoir_matrices
from .shuffle import stim_shuffle_test


def write_stim_figures(
    dest,
    stim_info: list,
    stim_patterns: list,
    spike_times: dict,
    params: dict,
    raw_data: np.ndarray,
    artifact_duration_s: float,
    info: dict,
    rng: np.random.Generator | None = None,
) -> list:
    """Write every ported per-recording stim figure into ``dest``.

    Shared by the pipeline runner and ``python/gen_stim_plots.py`` so both draw
    the same set. Population-raster plots use MATLAB's internal
    ``rasterBinWidth = 0.01`` override, independent of ``params['rasterBinWidth']``.
    """
    from pathlib import Path as _Path

    from .psth import get_fr_aligned_to_stim
    from .shuffle import stim_shuffle_test
    from .decoding import build_stim_activity_store
    from . import plotting as PL

    dest = _Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    method = params["SpikesMethod"]
    n_ch = len(stim_info)
    fr_params = {**params, "rasterBinWidth": 0.01}
    spk = [np.asarray(spike_times.get(c, {}).get(method, []), float).ravel() for c in range(n_ch)]
    all_stim = np.concatenate([s.elec_stim_times for s in stim_info]) if n_ch else np.array([])
    written: list = []

    # 9_FR_before_after_stimulation [+ per pattern]
    written.append(PL.plot_pre_post_stim_fr(spike_times, stim_info, all_stim, params,
                                            dest / "9_FR_before_after_stimulation.png", info))
    for pidx, st in enumerate(stim_patterns, 1):
        written.append(PL.plot_pre_post_stim_fr(spike_times, stim_info, st, params,
                       dest / f"9_FR_before_after_stimulation_pattern_{pidx}.png", info))

    # 10_stimulation_raster_and_psth [+ per pattern]
    fr, rbins = get_fr_aligned_to_stim(spk, all_stim, fr_params)
    written.append(PL.plot_metric_aligned_to_stim(fr, rbins, info, params,
                   "Mean firing rate (spikes/s)", dest / "10_stimulation_raster_and_psth.png"))
    for pidx, st in enumerate(stim_patterns, 1):
        frp, rbp = get_fr_aligned_to_stim(spk, st, fr_params)
        written.append(PL.plot_metric_aligned_to_stim(frp, rbp, info, params,
                       "Mean firing rate (spikes/s)",
                       dest / f"10_stimulation_raster_and_psth_pattern_{pidx}.png"))

    # stimPattern_k_heatmap (firing rate) + spikeLatency_k_heatmap
    _, mean_store = build_stim_activity_store(spike_times, stim_info, stim_patterns, params)
    store_max = max([1e-4] + [float(np.nanmax(m)) for m in mean_store if m.size])
    for pidx, st in enumerate(stim_patterns, 1):
        lat = PL.compute_median_spike_latency(spike_times, stim_info, st, params)
        written.append(PL.plot_stim_heatmap_w_metric(
            lat, (np.nanmin(lat), np.nanmax(lat)), "viridis_r", "Median spike latency (ms)",
            stim_info, pidx, dest / f"spikeLatency_pattern_{pidx}_heatmap.png",
            title=f"Pattern {pidx}"))
        written.append(PL.plot_stim_heatmap_w_metric(
            mean_store[pidx - 1][:n_ch], (0.0, store_max), "viridis",
            "Firing rate (spikes/s)", stim_info, pidx,
            dest / f"stimPattern_{pidx}_heatmap.png", title=f"Pattern {pidx}"))

    # Individual PSTH & raster (top-5 by corrected AUC)
    for pidx, st in enumerate(stim_patterns, 1):
        written += PL.plot_individual_psth_and_raster_for_pattern(
            spike_times, stim_info, st, params,
            dest / f"Individual_PSTH_and_Raster_Pattern_{pidx}", pidx, artifact_duration_s)

    # 12_shuffle_test_* (seeded for reproducibility; null is RNG-divergent)
    shuffle_rng = rng if rng is not None else np.random.default_rng(1)
    for pidx, st in enumerate(stim_patterns, 1):
        sr = stim_shuffle_test(spike_times, st,
                               {**params, "artifactDuration_s": artifact_duration_s},
                               info, n_ch, rng=shuffle_rng)
        written += PL.plot_stim_shuffle_results(sr, stim_info, info, params, dest, pidx)

    return [p for p in written if p is not None]


@dataclass
class StimRecordingResult:
    name: str
    stim_info: list
    stim_patterns: list
    spike_times: dict
    rows: list[dict]
    reservoir: dict
    shuffle: dict = field(default_factory=dict)


def run_stim_analysis_for_recording(
    raw_path: str | Path,
    spike_mat_path: str | Path,
    params: dict,
    info: dict,
    run_shuffle: bool = True,
    rng: np.random.Generator | None = None,
) -> StimRecordingResult:
    """Run the full stim analysis for one recording.

    Parameters
    ----------
    raw_path : the raw voltage `.mat` (for stim detection).
    spike_mat_path : `.mat` holding ``spikeTimes`` (e.g. ExperimentMatFiles).
    params : stim params (see ``MEASTIM_PORT_PLAN.md``).
    info : recording metadata (``FileName``/``Grp``/``DIV``/``duration_s``).
    """
    dat, channels, fs = load_raw_recording(raw_path)
    dat = dat.astype(np.float64)
    coords = np.zeros((dat.shape[1], 2))

    stim_info = detect_stim_times(dat, {**params, "fs": fs}, channels, coords)
    stim_info, stim_patterns = get_stim_patterns(stim_info, params)

    spikes = load_spike_times_mat(spike_mat_path)
    spikes = clean_spikes_from_stim(spikes, stim_info, params)

    rows = stim_activity_analysis(spikes, stim_info, stim_patterns, params, info)
    reservoir = compute_reservoir_matrices(spikes, stim_info, stim_patterns, params)

    shuffle: dict = {}
    if run_shuffle:
        artifact_dur = reservoir["analysis_window_s"][0]
        for pidx, st in enumerate(stim_patterns, start=1):
            st = np.asarray(st).ravel()
            if st.size == 0:
                continue
            shuffle[pidx] = stim_shuffle_test(
                spikes, st,
                {**params, "artifactDuration_s": artifact_dur},
                info, len(stim_info), rng=rng,
            )

    return StimRecordingResult(
        name=info.get("FileName", Path(raw_path).stem),
        stim_info=stim_info, stim_patterns=stim_patterns, spike_times=spikes,
        rows=rows, reservoir=reservoir, shuffle=shuffle,
    )


def run_stim_analysis(
    recordings: list[dict],
    params: dict,
    output_csv: str | Path | None = None,
    run_shuffle: bool = True,
    rng: np.random.Generator | None = None,
) -> list[StimRecordingResult]:
    """Run stim analysis over several recordings and (optionally) write the CSV.

    ``recordings`` : list of dicts with ``raw_path``, ``spike_mat_path`` and an
    ``info`` sub-dict. Aggregates every recording's rows into one
    ``StimActivity_NodeLevel.csv`` (port of ``saveEphysStatsStim.m``).
    """
    results = []
    all_rows: list[dict] = []
    for rec in recordings:
        res = run_stim_analysis_for_recording(
            rec["raw_path"], rec["spike_mat_path"], params, rec["info"],
            run_shuffle=run_shuffle, rng=rng,
        )
        results.append(res)
        all_rows.extend(res.rows)
    if output_csv is not None:
        write_stim_activity_csv(all_rows, output_csv)
    return results
