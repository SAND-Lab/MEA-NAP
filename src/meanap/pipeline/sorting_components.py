"""Tridesclous2 rebuilt from its components, with the stages MEA-NAP wants
to vary exposed.

Stock TDC2 (:mod:`spikeinterface.sorters.internal.tridesclous2`) is a fixed
chain: 5 σ threshold detection → subsample → per-channel ISO-SPLIT clustering
→ templates → the *peeler* (template matching over the whole recording) →
merge/censor. Its ``detect_threshold`` parameter only governs the peaks that
feed clustering; the peeler re-detects with its own threshold, hard-wired to
5 σ, and the peeler's spikes are what comes out. So "lower the threshold"
on stock TDC2 does not lower the final detection floor, and a different
candidate detector cannot be plugged in at all.

This module runs the same chain — same components, same defaults — but lets
the caller choose:

- **where candidate peaks come from**: TDC2's own threshold detection at any
  ``detect_threshold``, or an externally detected set (MEA-NAP's bior1.5
  wavelet spikes, via :func:`peaks_from_spike_times`);
- **the peeler's threshold** (``peeler_threshold``);
- **whether the peeler runs at all** (``assign="peeler"``) or every candidate
  peak is kept and simply labelled by the clustering (``assign="peaks"``) —
  the literal "wavelet decides what is a spike, the sorter decides which
  neuron" arrangement.

It exists to answer, on ground truth, whether wavelet candidates find
smaller spikes than a lowered threshold does. See
``python/benchmark_hybrid_sorting.py`` and ``python/SPIKE_SORTING_PLAN.md``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import numpy as np


def peaks_from_spike_times(
    spike_times_by_column: dict[int, np.ndarray],
    fs: float,
    kept: np.ndarray,
    recording_w=None,
) -> np.ndarray:
    """Candidate peaks in SpikeInterface's ``base_peak_dtype`` from spike
    times detected outside SpikeInterface.

    ``spike_times_by_column`` maps a column of the *original* array (as
    MEA-NAP's detectors key their results) to spike times in seconds;
    ``kept`` is the probe's column order (see
    :func:`~meanap.pipeline.spike_sorting.build_recording`), so channels the
    probe left off are dropped here. ``amplitude`` is filled from the
    whitened trace when a recording is given, since the clustering's
    pre-labelling and sparsity estimate read the channel, not the amplitude,
    but downstream diagnostics show it.
    """
    from spikeinterface.core.base import base_peak_dtype

    col_to_probe = {int(c): i for i, c in enumerate(kept)}
    rows = []
    for col, times in spike_times_by_column.items():
        probe_ch = col_to_probe.get(int(col))
        if probe_ch is None or len(times) == 0:
            continue
        frames = np.round(np.asarray(times, dtype=float) * fs).astype(np.int64)
        rows.append(np.column_stack([frames, np.full(len(frames), probe_ch)]))
    if not rows:
        return np.zeros(0, dtype=base_peak_dtype)
    arr = np.concatenate(rows)
    order = np.lexsort((arr[:, 1], arr[:, 0]))
    arr = arr[order]
    peaks = np.zeros(len(arr), dtype=base_peak_dtype)
    peaks["sample_index"] = arr[:, 0]
    peaks["channel_index"] = arr[:, 1]
    peaks["segment_index"] = 0
    if recording_w is not None:
        n = recording_w.get_num_samples()
        peaks = peaks[(peaks["sample_index"] >= 0) & (peaks["sample_index"] < n)]
        # Amplitude at the peak, read in chunks so a long recording is not
        # pulled into memory whole.
        amp = np.zeros(len(peaks))
        step = int(60 * fs)
        for start in range(0, n, step):
            m = (peaks["sample_index"] >= start) & (peaks["sample_index"] < start + step)
            if not m.any():
                continue
            traces = recording_w.get_traces(start_frame=start, end_frame=min(start + step, n))
            amp[m] = traces[peaks["sample_index"][m] - start, peaks["channel_index"][m]]
        peaks["amplitude"] = amp
    return peaks


def run_tdc2_components(
    rec_pre,
    *,
    peaks: np.ndarray | None = None,
    detect_threshold: float = 5.0,
    peeler_threshold: float = 5.0,
    assign: str = "peeler",
    sorter_params: dict[str, Any] | None = None,
    job_kwargs: dict[str, Any] | None = None,
    seed: int | None = None,
    log: Callable[[str], None] = lambda m: None,
):
    """Tridesclous2's chain over an already bandpassed/referenced recording.

    ``rec_pre`` is what :func:`~meanap.pipeline.spike_sorting.preprocess`
    returns. Whitening is applied here as TDC2 does (local, 100 µm — on a
    low-density array that is per-channel noise scaling). ``sorter_params``
    are TDC2's own names and override its defaults (the MEA-NAP presets from
    :func:`~meanap.pipeline.spike_sorting.sorter_presets` belong here).

    Returns ``(sorting, info)``: a SpikeInterface sorting and a dict with the
    counts at each stage.
    """
    import spikeinterface.full as si
    from spikeinterface.core import NumpySorting, Templates, get_noise_levels
    from spikeinterface.core.base import minimum_spike_dtype
    from spikeinterface.core.template_tools import get_template_extremum_channel  # noqa: F401
    from spikeinterface.core.job_tools import fix_job_kwargs
    from spikeinterface.core.waveform_tools import estimate_templates_with_accumulator
    from spikeinterface.sorters.internal.tridesclous2 import Tridesclous2Sorter
    from spikeinterface.sortingcomponents.clustering.main import (
        clustering_methods, find_clusters_from_peaks,
    )
    from spikeinterface.sortingcomponents.matching import find_spikes_from_templates
    from spikeinterface.sortingcomponents.peak_detection import detect_peaks
    from spikeinterface.sortingcomponents.peak_selection import select_peaks
    from spikeinterface.sortingcomponents.tools import (
        clean_templates, compute_sparsity_from_peaks_and_label,
    )

    params = deepcopy(Tridesclous2Sorter.default_params())
    params.update(sorter_params or {})
    params["detect_threshold"] = detect_threshold
    jobs = fix_job_kwargs(dict(job_kwargs or {}))
    jobs["progress_bar"] = False
    fs = rec_pre.get_sampling_frequency()
    num_chans = rec_pre.get_num_channels()
    info: dict[str, Any] = {}

    recording = si.whiten(rec_pre, dtype="float32", mode="local", radius_um=100.0)
    noise_levels = get_noise_levels(recording, return_in_uV=False,
                                    random_slices_kwargs=dict(seed=seed), **jobs)

    # ── candidates ──────────────────────────────────────────────────────────
    if peaks is None:
        all_peaks = detect_peaks(
            recording, method="locally_exclusive",
            method_kwargs=dict(noise_levels=noise_levels, peak_sign=params["peak_sign"],
                               detect_threshold=detect_threshold, exclude_sweep_ms=1.5,
                               radius_um=params["detection_radius_um"]),
            job_kwargs=jobs)
        info["candidate_source"] = f"threshold {detect_threshold:g} sigma"
    else:
        all_peaks = peaks
        info["candidate_source"] = "given"
    info["n_candidates"] = int(len(all_peaks))
    log(f"      {len(all_peaks)} candidate peaks ({info['candidate_source']})")

    # With assign="peaks" every candidate must be labelled, so nothing is
    # subsampled; the clustering is per channel and copes with it.
    if assign == "peaks":
        sel = all_peaks
    else:
        n_peaks = max(params["n_peaks_per_channel"] * num_chans, 20_000)
        sel = select_peaks(all_peaks, method="uniform", n_peaks=n_peaks, seed=seed)
    info["n_clustered"] = int(len(sel))

    # ── clustering (verbatim from TDC2) ─────────────────────────────────────
    num_shifts = int(fs * params["merge_similarity_lag_ms"] / 1000.0)
    ck = deepcopy(clustering_methods["iterative-isosplit"]._default_params)
    ck["peaks_svd"]["ms_before"] = params["clustering_ms_before"]
    ck["peaks_svd"]["ms_after"] = params["clustering_ms_after"]
    ck["peaks_svd"]["radius_um"] = params["features_radius_um"]
    ck["peaks_svd"]["n_components"] = params["n_svd_components_per_channel"]
    ck["split"]["split_radius_um"] = params["split_radius_um"]
    ck["split"]["recursive_depth"] = params["clustering_recursive_depth"]
    ck["split"]["method_kwargs"]["n_pca_features"] = params["n_pca_features"]
    ck["clean_templates"]["sparsify_threshold"] = params["template_sparsify_threshold"]
    ck["clean_templates"]["min_snr"] = params["template_min_snr_ptp"]
    ck["clean_templates"]["max_jitter_ms"] = params["template_max_jitter_ms"]
    ck["merge_from_templates"]["num_shifts"] = num_shifts
    ck["noise_levels"] = noise_levels
    ck["clean_low_firing"]["min_firing_rate"] = params["min_firing_rate"]
    ck["clean_low_firing"]["subsampling_factor"] = all_peaks.size / max(1, sel.size)
    ck["seed"] = seed

    unit_ids, labels, _ = find_clusters_from_peaks(
        recording, sel, method="iterative-isosplit", method_kwargs=ck,
        extra_outputs=True, job_kwargs=jobs)
    mask = labels >= 0
    kept_peaks, kept_labels = sel[mask], labels[mask]
    info["n_clusters"] = int(unit_ids.size)
    info["n_labelled"] = int(mask.sum())
    log(f"      {unit_ids.size} cluster(s); {mask.sum()} of {len(sel)} clustered peaks labelled")
    if unit_ids.size == 0:
        return NumpySorting.from_unit_dict({}, fs), info

    sorting_pre = NumpySorting.from_samples_and_labels(
        kept_peaks["sample_index"], kept_labels, fs, unit_ids=unit_ids)

    if assign == "peaks":
        # The wavelet said what is a spike; the clustering said which unit.
        return sorting_pre, info

    # ── templates + peeler (verbatim from TDC2, threshold exposed) ──────────
    spike_vector = sorting_pre.to_spike_vector(concatenated=True)
    sparsity, _ = compute_sparsity_from_peaks_and_label(
        kept_peaks, spike_vector["unit_index"], sorting_pre.unit_ids, recording,
        params["template_radius_um"])
    nbefore = int(params["ms_before"] * fs / 1000.0)
    nafter = int(params["ms_after"] * fs / 1000.0)
    templates_array = estimate_templates_with_accumulator(
        recording, sorting_pre.to_spike_vector(), sorting_pre.unit_ids, nbefore, nafter,
        return_in_uV=False, sparsity_mask=sparsity.mask, **jobs)
    templates = Templates(
        templates_array=templates_array, sampling_frequency=fs, nbefore=nbefore,
        channel_ids=recording.channel_ids, unit_ids=sorting_pre.unit_ids,
        sparsity_mask=sparsity.mask, probe=recording.get_probe(), is_in_uV=False)
    templates = clean_templates(
        templates, sparsify_threshold=params["template_sparsify_threshold"],
        noise_levels=noise_levels, min_snr=params["template_min_snr_ptp"],
        max_jitter_ms=params["template_max_jitter_ms"], remove_empty=True)
    info["n_templates"] = int(len(templates.unit_ids))
    if len(templates.unit_ids) == 0:
        return NumpySorting.from_unit_dict({}, fs), info

    spikes = find_spikes_from_templates(
        recording, templates, method="tdc-peeler",
        method_kwargs=dict(noise_levels=noise_levels, detect_threshold=peeler_threshold),
        pipeline_kwargs=dict(gather_mode="memory"), job_kwargs=jobs)
    final = np.zeros(spikes.size, dtype=minimum_spike_dtype)
    final["sample_index"] = spikes["sample_index"]
    final["unit_index"] = spikes["cluster_index"]
    final["segment_index"] = spikes["segment_index"]
    sorting = NumpySorting(final, fs, templates.unit_ids)
    info["n_peeled"] = int(spikes.size)
    log(f"      peeler at {peeler_threshold:g} sigma: {spikes.size} spikes on "
        f"{len(templates.unit_ids)} template(s)")

    from spikeinterface.sorters.internal.spyking_circus2 import final_cleaning_circus
    analyzer = final_cleaning_circus(
        recording, sorting, templates, amplitude_scalings=spikes["amplitude"],
        noise_levels=noise_levels,
        similarity_kwargs={"method": "l1", "support": "union",
                           "max_lag_ms": params["merge_similarity_lag_ms"]},
        sparsity_overlap=0.5, censor_ms=3.0, max_distance_um=50,
        template_diff_thresh=np.arange(0.05, 0.4, 0.05), debug_folder=None,
        job_kwargs=jobs)
    sorting = NumpySorting.from_sorting(analyzer.sorting)
    info["n_units"] = int(len(sorting.unit_ids))
    return sorting, info
