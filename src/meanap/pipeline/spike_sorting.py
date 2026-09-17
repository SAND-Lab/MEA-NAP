"""Step 1 by spike *sorting*: units, not electrodes, as the pipeline's nodes.

The detectors in :mod:`meanap.pipeline.spike_detection` give one spike train
per electrode. On a dense culture an electrode often hears several neurons,
and every later step then treats their pooled activity as one node. Sorting
clusters the spikes on each electrode by waveform so each neuron becomes its
own train — and, in this pipeline, its own node.

Everything here runs through `SpikeInterface <https://spikeinterface.readthedocs.io>`_,
which wraps the sorters behind one call and supplies the waveform, template
and quality-metric machinery used to curate what they return. It is an
optional dependency (``pip install meanap[sorting]``) and is imported lazily,
so a pipeline that only detects never pays for it.

Why the presets look the way they do
------------------------------------
MEA-NAP's arrays are low-density (200–350 µm pitch). A spike reaches ~100 µm,
so it is seen on one electrode and there is no spatial footprint to sort on:
the problem is per-electrode waveform clustering, the one tetrode-era sorters
were built for. The presets therefore keep every sorter's spatial radii
*below* the pitch (so neighbouring electrodes are independent) and switch off
drift correction, which needs a footprint to track. See
``python/SPIKE_SORTING_PLAN.md`` for the survey and feasibility numbers.

What comes back
---------------
:class:`SpikeSortingResult` has the same ``spike_times`` shape as detection's
result — ``{node: {method: times_s}}`` — under the method name
:data:`~meanap.params.SORTED_METHOD`, plus the per-unit arrays the file format
stores under ``unit_*`` (see :func:`~meanap.pipeline.io.save_spike_times_npz`).
``channels`` holds each unit's *parent electrode ID*, repeated when several
units share one, which is what lets grounding, the electrode heatmaps and the
node-level CSVs work without knowing the nodes are units.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, NamedTuple

import numpy as np

from meanap.params import SORTED_METHOD
from meanap.pipeline.probes import build_probe, electrode_pitch_um, layout_grid_step

#: The sorters MEA-NAP knows how to configure for a low-density array, in the
#: order the GUI offers them. Anything else SpikeInterface installs still runs,
#: with its own defaults.
SUPPORTED_SORTERS = ("tridesclous2", "mountainsort5", "spykingcircus2", "lupin", "kilosort4")

#: How many of a unit's spikes are kept as example waveforms in the spike file.
#: They exist to be drawn (the viewer's waveform panel), not analysed.
_N_EXAMPLE_WAVEFORMS = 200

#: How far from its electrode a unit is drawn, in electrode steps. Units on
#: one electrode are spread on a ring of this radius so they can be told
#: apart in the spatial network plots; small enough that the ring stays
#: nearer its own electrode than any neighbour.
_UNIT_RING_RADIUS_STEPS = 0.22


class SortingUnavailable(ImportError):
    """SpikeInterface (or the chosen sorter) is not installed."""


def sorting_available() -> bool:
    """Whether the ``sorting`` extra is importable."""
    try:
        import probeinterface  # noqa: F401
        import spikeinterface  # noqa: F401
    except ImportError:
        return False
    return True


def installed_sorters() -> list[str]:
    """The sorters that can run here, in :data:`SUPPORTED_SORTERS` order first."""
    if not sorting_available():
        return []
    import spikeinterface.sorters as ss
    have = set(ss.installed_sorters())
    ordered = [s for s in SUPPORTED_SORTERS if s in have]
    return ordered + sorted(have - set(ordered))


def _require_spikeinterface():
    try:
        import spikeinterface.full as si
    except ImportError as e:
        raise SortingUnavailable(
            "Spike sorting needs SpikeInterface: install the 'sorting' extra "
            "(pip install 'meanap[sorting]' or uv sync --extra sorting)."
        ) from e
    return si


# ── Parameters ────────────────────────────────────────────────────────────────

@dataclass
class SpikeSortingParams:
    """Everything :func:`sort_spikes_recording` needs, mirroring the
    ``sort_*`` / ``curation_*`` fields of :class:`meanap.params.Params`."""
    channel_layout: str = "MCS60"
    sorter_name: str = "tridesclous2"
    sorter_params: dict[str, Any] = field(default_factory=dict)
    freq_min: float = 300.0
    freq_max: float = 6000.0
    common_reference: str = "global_median"
    electrode_pitch_um: float | None = None
    auto_merge: bool = False
    curation_min_snr: float = 4.0
    censor_ms: float = 0.3
    curation_refractory_ms: float = 1.5
    curation_max_rp_violation_frac: float = 0.05
    curation_min_firing_rate: float = 0.05
    curation_keep_labels: tuple[str, ...] = ("good", "mua")
    n_jobs: int | None = None
    seed: int | None = None
    keep_sorter_output: bool = False


class SpikeSortingResult(NamedTuple):
    """One recording's sorted units, shaped like a detection result.

    ``spike_times`` / ``waveforms`` are keyed by *unit index* (0-based node
    number), then by method — always :data:`SORTED_METHOD`. ``channels`` is
    the parent electrode ID per unit. ``units`` holds the ``unit_*`` arrays as
    the file stores them; ``all_units`` is the pre-curation table (one row per
    unit the sorter returned, kept or not), for the checks folder.
    """
    spike_times: dict[int, dict[str, np.ndarray]]
    waveforms: dict[int, dict[str, np.ndarray]]
    channels: np.ndarray
    fs: float
    units: dict[str, np.ndarray]
    all_units: list[dict[str, Any]]
    sorter_name: str
    sorter_version: str
    sorter_params: dict[str, Any]
    templates: np.ndarray  # (n_units, n_pts) on each unit's own electrode, µV
    template_times_ms: np.ndarray  # (n_pts,) relative to the trough


# ── Sorter presets ────────────────────────────────────────────────────────────

def sorter_presets(sorter_name: str, pitch_um: float, n_channels: int) -> dict[str, Any]:
    """MEA-NAP's settings for *sorter_name* on an array of this pitch.

    The principle throughout: no spatial radius may reach a neighbouring
    electrode (so each electrode is sorted on its own waveforms), and nothing
    that needs a spatial footprint — drift correction, position-based
    clustering — is left on. Values are in the sorter's own vocabulary.
    """
    near = 0.4 * pitch_um  # comfortably inside one electrode's reach
    if sorter_name == "mountainsort5":
        return {
            "scheme": "2",
            # We filter and reference before handing the recording over;
            # whitening stays on, it is per-channel noise scaling here.
            "filter": False,
            "whiten": True,
            "scheme1_detect_channel_radius": near,
            "scheme2_phase1_detect_channel_radius": near,
            "scheme2_detect_channel_radius": near,
            "snippet_mask_radius": near,
            "progress_bar": False,
        }
    if sorter_name == "tridesclous2":
        return {
            "apply_motion_correction": False,
            "detection_radius_um": near,
            "features_radius_um": near,
            "split_radius_um": near,
            "template_radius_um": near,
        }
    if sorter_name == "lupin":
        return {
            "apply_motion_correction": False,
            "whitening_radius_um": near,
            "detection_radius_um": near,
            "features_radius_um": near,
            "split_radius_um": near,
            "template_radius_um": near,
        }
    if sorter_name == "spykingcircus2":
        return {
            "apply_motion_correction": False,
            "general": {"ms_before": 0.5, "ms_after": 1.5, "radius_um": near},
            "merging": {"max_distance_um": near},
        }
    if sorter_name == "kilosort4":
        # Kilosort's own guidance for sparse / ≤64-channel arrays: no drift
        # blocks, neighbourhoods no larger than the array, template centres
        # one per electrode column.
        return {
            "nblocks": 0,
            "nearest_chans": min(10, n_channels),
            "nearest_templates": min(100, n_channels),
            "dmin": pitch_um,
            "dminx": pitch_um,
            "max_channel_distance": near,
            "whitening_range": min(32, n_channels),
            "do_CAR": False,  # done here already
            "progress_bar": False,
        }
    return {}


def _merge_params(preset: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """User values over presets, one level deep for the dict-valued groups
    SpyKING CIRCUS 2 uses, so overriding ``general.radius_um`` keeps
    ``general.ms_before``."""
    merged = dict(preset)
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


# ── Recording wrap + preprocessing ────────────────────────────────────────────

def _job_kwargs(n_jobs: int | None) -> dict[str, Any]:
    from meanap.pipeline.parallel import spawn_usable, suggest_process_count
    if n_jobs is None:
        # SpikeInterface workers each hold a 1 s chunk of every channel plus
        # the sorter's own state — small; cores are the bound.
        n_jobs = suggest_process_count(64, 0.5)
    n_jobs = max(1, int(n_jobs))
    # Workers are started fresh rather than forked: a fork copies the whole
    # pipeline process — its open recording stream, its Qt state when run
    # from the GUI — and the copies complain on exit. Spawn is what the
    # pipeline's own pools use (pipeline/parallel.py), with the same caveat
    # about unguarded scripts; where it cannot be used, sorting runs on one
    # worker rather than forking.
    if n_jobs > 1 and not spawn_usable():
        n_jobs = 1
    return {"n_jobs": n_jobs, "chunk_duration": "1s", "progress_bar": False,
            "mp_context": "spawn"}


def build_recording(
    dat: np.ndarray,
    channels: np.ndarray,
    fs: float,
    params: SpikeSortingParams,
):
    """A SpikeInterface recording over the array the pipeline already holds.

    Returns ``(recording, kept)``: the recording carries only the channels the
    layout places (``kept`` is their 0-based index into ``dat``'s columns),
    with the probe attached and gains set so traces read in µV, which is what
    ``load_raw_recording`` hands over.
    """
    si = _require_spikeinterface()
    probe, kept = build_probe(params.channel_layout, channels, params.electrode_pitch_um)
    traces = dat if len(kept) == dat.shape[1] else dat[:, kept]
    rec = si.NumpyRecording(traces, sampling_frequency=float(fs),
                            channel_ids=[str(int(channels[i])) for i in kept])
    rec = rec.set_probe(probe)
    rec.set_channel_gains(1.0)
    rec.set_channel_offsets(0.0)
    return rec, kept


def preprocess(recording, params: SpikeSortingParams, folder: Path, n_jobs: int | None):
    """Bandpass, reference, and write the result to *folder* as float32.

    Written out rather than kept lazy because every sorter reads the traces
    many times over, in parallel workers; a lazy filter would be recomputed
    on each read. float32 halves what a float64 source would cost on disk.
    """
    si = _require_spikeinterface()
    rec = si.bandpass_filter(recording, freq_min=params.freq_min, freq_max=params.freq_max)
    if params.common_reference == "global_median":
        rec = si.common_reference(rec, reference="global", operator="median")
    elif params.common_reference not in ("none", "", None):
        raise ValueError(f"Unknown sort_common_reference {params.common_reference!r}")
    rec = si.astype(rec, "float32")
    if folder.exists():
        shutil.rmtree(folder)
    # Written by this process, not a pool: the source is an in-memory array,
    # and a spawned worker would receive its own pickled copy of it — with
    # eight workers on a ten-minute 60-channel recording, eight copies of
    # 3.6 GB. Filtering 60 channels in one process is a minute or so; the
    # sorter then reads the on-disk copy, which workers can share.
    jobs = _job_kwargs(n_jobs)
    jobs["n_jobs"] = 1
    return rec.save(folder=folder, format="binary", **jobs)


# ── Curation ──────────────────────────────────────────────────────────────────

def rp_violation_fraction(spike_train_s: np.ndarray, refractory_ms: float) -> float:
    """Fraction of a unit's inter-spike intervals shorter than the refractory
    period — the contamination measure that stays meaningful for bursting
    neurons (a Poisson-normalised ratio does not)."""
    if len(spike_train_s) < 2:
        return 0.0
    isi_ms = np.diff(np.sort(spike_train_s)) * 1000.0
    return float(np.mean(isi_ms < refractory_ms))


def label_unit(snr: float, rp_frac: float, firing_rate: float, params: SpikeSortingParams) -> str:
    """``good`` / ``mua`` / ``noise`` for one unit — see the ``curation_*``
    fields of :class:`meanap.params.Params` for what each means."""
    if not np.isfinite(snr) or snr < params.curation_min_snr:
        return "noise"
    if firing_rate < params.curation_min_firing_rate:
        return "noise"
    if rp_frac > params.curation_max_rp_violation_frac:
        return "mua"
    return "good"


def unit_ring_coords(electrode_xy: np.ndarray, electrode_index: np.ndarray, step: float) -> np.ndarray:
    """Layout coordinates for units: their electrode's, spread on a small ring
    when an electrode carries more than one. Deterministic — order of units on
    an electrode fixes their angle — so a re-render draws the same picture."""
    coords = np.array(electrode_xy, dtype=float, copy=True)
    for e in np.unique(electrode_index):
        idx = np.flatnonzero(electrode_index == e)
        if len(idx) < 2:
            continue
        angles = 2 * np.pi * np.arange(len(idx)) / len(idx)
        coords[idx, 0] += _UNIT_RING_RADIUS_STEPS * step * np.cos(angles)
        coords[idx, 1] += _UNIT_RING_RADIUS_STEPS * step * np.sin(angles)
    return coords


# ── The whole thing ───────────────────────────────────────────────────────────

def run_sorter_on(
    rec_pre,
    n_channels: int,
    params: SpikeSortingParams,
    work_dir: Path,
    log: Callable[[str], None] = lambda m: None,
):
    """Run the chosen sorter over a preprocessed recording.

    Returns ``(sorting, sorter_version, sorter_params)`` — the sorter's raw
    output before any curation, which is what a ground-truth benchmark scores.
    """
    si = _require_spikeinterface()
    import spikeinterface.sorters as ss

    if params.sorter_name not in ss.installed_sorters():
        raise SortingUnavailable(
            f"Sorter {params.sorter_name!r} is not installed "
            f"(installed: {', '.join(ss.installed_sorters()) or 'none'})")

    jobs = _job_kwargs(params.n_jobs)
    pitch = electrode_pitch_um(params.channel_layout, params.electrode_pitch_um)
    sorter_params = _merge_params(
        sorter_presets(params.sorter_name, pitch, n_channels), params.sorter_params)
    if params.seed is not None and params.sorter_name in ("tridesclous2", "lupin", "spykingcircus2"):
        sorter_params.setdefault("seed", int(params.seed))
    # The internal sorters and MountainSort5 each take their worker count in
    # their own field; hand it to whichever this one reads.
    if params.sorter_name == "mountainsort5":
        sorter_params.setdefault("n_jobs", jobs["n_jobs"])
        sorter_params.setdefault("mp_context", jobs["mp_context"])
    elif params.sorter_name in ("tridesclous2", "lupin", "spykingcircus2"):
        sorter_params.setdefault("job_kwargs", dict(jobs))
    sorter_version = str(ss.sorter_dict[params.sorter_name].get_sorter_version())

    log(f"      running {params.sorter_name} {sorter_version}…")
    # MountainSort5 narrates every phase to stdout whatever ``verbose`` says;
    # the pipeline's log is the place for progress, so that chatter is dropped.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        sorting = si.run_sorter(
            params.sorter_name, rec_pre, folder=Path(work_dir) / "sorter_output",
            remove_existing_folder=True, verbose=False, **sorter_params)
    log(f"      {len(sorting.unit_ids)} unit(s) returned")
    return sorting, sorter_version, sorter_params


def curate_sorting(
    sorting,
    rec_pre,
    channels: np.ndarray,
    kept: np.ndarray,
    fs: float,
    params: SpikeSortingParams,
    sorter_version: str,
    sorter_params: dict[str, Any],
    log: Callable[[str], None] = lambda m: None,
) -> SpikeSortingResult:
    """Measure a sorter's units, label them, and keep the ones that become
    nodes. ``kept`` maps the recording's channel order back to columns of the
    original array (see :func:`build_recording`)."""
    si = _require_spikeinterface()
    jobs = _job_kwargs(params.n_jobs)
    n_raw = len(sorting.unit_ids)

    # Empty units break the analyzer's template estimate; they would be
    # dropped by the firing-rate floor anyway.
    counts = sorting.count_num_spikes_per_unit()
    sorting = sorting.select_units([u for u in sorting.unit_ids if counts[u] > 0])
    if len(sorting.unit_ids) == 0:
        return _empty_result(channels, fs, params, sorter_version, sorter_params)

    # Two spikes of one unit closer than a spike is wide are one spike
    # counted twice — a template matcher resolving a burst can do that — so
    # the second is dropped. On a dense culture recording this was a tenth of
    # a busy unit's spikes, all at intervals under 0.25 ms. Kilosort censors
    # at 0.25 ms for the same reason.
    if params.censor_ms > 0:
        from spikeinterface.curation import remove_duplicated_spikes
        before = sum(sorting.count_num_spikes_per_unit().values())
        sorting = remove_duplicated_spikes(sorting, censored_period_ms=params.censor_ms,
                                           method="keep_first")
        after = sum(sorting.count_num_spikes_per_unit().values())
        if before != after:
            log(f"      {before - after} duplicate spike(s) within "
                f"{params.censor_ms:g} ms removed")

    log("      measuring units (waveforms, templates, quality metrics)…")
    analyzer = si.create_sorting_analyzer(sorting, rec_pre, sparse=False)
    analyzer.compute({
        "random_spikes": {"max_spikes_per_unit": _N_EXAMPLE_WAVEFORMS,
                          "seed": params.seed},
        "waveforms": {"ms_before": 1.0, "ms_after": 2.0},
        "templates": {"operators": ["average"]},
        "noise_levels": {},
    }, **jobs)

    if params.auto_merge:
        from spikeinterface.curation import auto_merge_units
        # The merge test looks at cross-correlograms and template similarity;
        # neither is needed otherwise, so they are computed only here.
        analyzer.compute({"correlograms": {}, "template_similarity": {}}, **jobs)
        before = len(analyzer.unit_ids)
        analyzer = auto_merge_units(analyzer, recursive=True, **jobs)
        log(f"      auto-merge: {before} → {len(analyzer.unit_ids)} unit(s)")

    analyzer.compute({"spike_amplitudes": {}}, **jobs)
    metrics = analyzer.compute("quality_metrics",
                               metric_names=["snr", "firing_rate", "presence_ratio"],
                               ).get_data()

    extremum = si.get_template_extremum_channel(analyzer, peak_sign="neg", outputs="index")
    templates_ext = analyzer.get_extension("templates")
    waveforms_ext = analyzer.get_extension("waveforms")
    nbefore = templates_ext.nbefore
    n_pts = templates_ext.nbefore + templates_ext.nafter
    template_times_ms = (np.arange(n_pts) - nbefore) / fs * 1000.0

    # Layout coordinates of every electrode, in the recording's channel order.
    from meanap.pipeline.probes import layout_coords_for_channels
    layout_xy, _ = layout_coords_for_channels(params.channel_layout, channels)
    step = layout_grid_step(params.channel_layout)

    # One row per unit the sorter returned, curated or not.
    rows: list[dict[str, Any]] = []
    for unit_id in analyzer.unit_ids:
        train = analyzer.sorting.get_unit_spike_train(unit_id) / fs
        probe_ch = int(extremum[unit_id])
        col = int(kept[probe_ch])  # column of the original array, index into `channels`
        snr = float(metrics.loc[unit_id, "snr"])
        fr = float(metrics.loc[unit_id, "firing_rate"])
        rp = rp_violation_fraction(train, params.curation_refractory_ms)
        rows.append({
            "sorter_unit_id": str(unit_id),
            "channel_index": col,
            "channel_id": int(channels[col]),
            "n_spikes": int(len(train)),
            "firing_rate": fr,
            "snr": snr,
            "rp_violation_frac": rp,
            "presence_ratio": float(metrics.loc[unit_id, "presence_ratio"]),
            "amplitude_uv": float(templates_ext.get_unit_template(unit_id)[nbefore, probe_ch]),
            "label": label_unit(snr, rp, fr, params),
            "_train": train,
            "_template": templates_ext.get_unit_template(unit_id)[:, probe_ch]
            .astype(np.float32),
            "_waveforms": waveforms_ext.get_waveforms_one_unit(unit_id)[:, :, probe_ch]
            .astype(np.float32),
        })

    # Nodes are numbered by electrode, then by amplitude within it, so unit 1
    # of electrode 25 is its biggest neuron and the order is stable across
    # sorters and reruns.
    rows.sort(key=lambda r: (r["channel_index"], r["amplitude_uv"], r["sorter_unit_id"]))
    kept_rows = [r for r in rows if r["label"] in params.curation_keep_labels]
    n_by_label = {lab: sum(r["label"] == lab for r in rows) for lab in ("good", "mua", "noise")}
    log(f"      curation: {n_by_label['good']} good, {n_by_label['mua']} multi-unit, "
        f"{n_by_label['noise']} noise → {len(kept_rows)} node(s) kept "
        f"({', '.join(params.curation_keep_labels)})")

    if not kept_rows:
        result = _empty_result(channels, fs, params, sorter_version, sorter_params)
        return result._replace(all_units=[_public(r) for r in rows])

    # Unit IDs read "<electrode>-<rank>", e.g. 25-1, 25-2.
    unit_ids: list[str] = []
    rank_on: dict[int, int] = {}
    for r in kept_rows:
        rank_on[r["channel_index"]] = rank_on.get(r["channel_index"], 0) + 1
        unit_ids.append(f"{r['channel_id']}-{rank_on[r['channel_index']]}")

    ch_index = np.array([r["channel_index"] for r in kept_rows], dtype=int)
    coords = unit_ring_coords(layout_xy[ch_index], ch_index, step)

    spike_times = {i: {SORTED_METHOD: r["_train"].astype(float)} for i, r in enumerate(kept_rows)}
    waveforms = {i: {SORTED_METHOD: r["_waveforms"]} for i, r in enumerate(kept_rows)}
    units = {
        "id": np.array(unit_ids),
        "sorter_unit_id": np.array([r["sorter_unit_id"] for r in kept_rows]),
        "channel_index": ch_index,
        "coords": coords,
        "label": np.array([r["label"] for r in kept_rows]),
        "n_spikes": np.array([r["n_spikes"] for r in kept_rows], dtype=int),
        "firing_rate": np.array([r["firing_rate"] for r in kept_rows], dtype=float),
        "snr": np.array([r["snr"] for r in kept_rows], dtype=float),
        "rp_violation_frac": np.array([r["rp_violation_frac"] for r in kept_rows], dtype=float),
        "presence_ratio": np.array([r["presence_ratio"] for r in kept_rows], dtype=float),
        "amplitude_uv": np.array([r["amplitude_uv"] for r in kept_rows], dtype=float),
        "template": np.stack([r["_template"] for r in kept_rows]),
        "template_times_ms": template_times_ms.astype(np.float32),
        "sorter_name": np.array(params.sorter_name),
        "sorter_version": np.array(sorter_version),
        "sorter_params_json": np.array(json.dumps(sorter_params, default=str)),
        "n_units_returned": np.array(n_raw),
    }
    return SpikeSortingResult(
        spike_times=spike_times, waveforms=waveforms,
        channels=np.array([r["channel_id"] for r in kept_rows], dtype=int),
        fs=float(fs), units=units,
        all_units=[_public(r) for r in rows],
        sorter_name=params.sorter_name, sorter_version=sorter_version,
        sorter_params=sorter_params,
        templates=units["template"], template_times_ms=template_times_ms,
    )


def sort_spikes_recording(
    dat: np.ndarray,
    channels: np.ndarray,
    fs: float,
    params: SpikeSortingParams,
    work_dir: Path | str,
    log: Callable[[str], None] = lambda m: None,
    duration_s: float | None = None,
) -> SpikeSortingResult:
    """Sort one recording and curate the units into pipeline nodes.

    ``dat`` is ``(n_samples, n_channels)`` in µV, as ``load_raw_recording``
    returns it. ``work_dir`` receives the preprocessed copy and the sorter's
    own output; both are removed afterwards unless ``params.keep_sorter_output``.
    """
    si = _require_spikeinterface()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    jobs = _job_kwargs(params.n_jobs)
    # The sorters' internal stages do not all take job kwargs; the global
    # setting is what reaches them, and it is what makes them spawn rather
    # than fork (see _job_kwargs). Restored afterwards.
    previous = si.get_global_job_kwargs()
    si.set_global_job_kwargs(**jobs)
    try:
        return _sort_spikes_recording(dat, channels, fs, params, work_dir, log, jobs)
    finally:
        si.set_global_job_kwargs(**previous)


def _sort_spikes_recording(dat, channels, fs, params, work_dir, log, jobs) -> SpikeSortingResult:
    recording, kept = build_recording(dat, channels, fs, params)
    dropped = len(channels) - len(kept)
    if dropped:
        log(f"      {dropped} channel(s) not in layout {params.channel_layout} "
            f"left out of sorting")

    log(f"      preprocessing ({params.freq_min:g}–{params.freq_max:g} Hz, "
        f"reference {params.common_reference}, {jobs['n_jobs']} workers)…")
    rec_pre = preprocess(recording, params, work_dir / "preprocessed", params.n_jobs)

    sorting, sorter_version, sorter_params = run_sorter_on(
        rec_pre, len(kept), params, work_dir, log)
    result = curate_sorting(sorting, rec_pre, channels, kept, fs, params,
                            sorter_version, sorter_params, log)
    _cleanup(work_dir, params)
    return result


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _empty_result(channels, fs, params, sorter_version, sorter_params) -> SpikeSortingResult:
    return SpikeSortingResult(
        spike_times={}, waveforms={}, channels=np.zeros(0, dtype=int), fs=float(fs),
        units={
            "id": np.zeros(0, dtype=str), "channel_index": np.zeros(0, dtype=int),
            "coords": np.zeros((0, 2)), "label": np.zeros(0, dtype=str),
            "sorter_name": np.array(params.sorter_name),
            "sorter_version": np.array(sorter_version),
            "sorter_params_json": np.array(json.dumps(sorter_params, default=str)),
            "n_units_returned": np.array(0),
        },
        all_units=[], sorter_name=params.sorter_name, sorter_version=sorter_version,
        sorter_params=sorter_params, templates=np.zeros((0, 0), dtype=np.float32),
        template_times_ms=np.zeros(0),
    )


def _cleanup(work_dir: Path, params: SpikeSortingParams) -> None:
    if params.keep_sorter_output:
        return
    shutil.rmtree(work_dir, ignore_errors=True)


def params_from_pipeline(params, fs: float | None = None) -> SpikeSortingParams:
    """The sorting settings out of a :class:`meanap.params.Params`."""
    return SpikeSortingParams(
        channel_layout=params.channel_layout,
        sorter_name=params.sorter_name,
        sorter_params=dict(params.sorter_params or {}),
        freq_min=params.sort_freq_min,
        freq_max=params.sort_freq_max,
        common_reference=params.sort_common_reference,
        electrode_pitch_um=params.electrode_pitch_um,
        auto_merge=params.sort_auto_merge,
        curation_min_snr=params.curation_min_snr,
        censor_ms=params.sort_censor_ms,
        curation_refractory_ms=params.curation_refractory_ms,
        curation_max_rp_violation_frac=params.curation_max_rp_violation_frac,
        curation_min_firing_rate=params.curation_min_firing_rate,
        curation_keep_labels=tuple(params.curation_keep_labels),
        n_jobs=params.spike_detection_channel_workers,
        seed=params.random_seed,
        keep_sorter_output=params.keep_sorter_output,
    )
