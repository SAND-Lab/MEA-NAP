"""Synthetic ground truth for spike sorting on a low-density MEA.

Real culture recordings have no ground truth, and on a single electrode two
sorters can split the same spikes differently with nothing to say which is
right (see ``python/SPIKE_SORTING_PLAN.md`` §3.3). This module makes a
recording where the answer is known — neurons placed near the electrodes of
a real MEA layout, firing in the bursty way cultures do — so sorters and
curation settings can be scored against it. It is what chose the default
sorter, and it is the test every change to the presets should be run through
(``python/test_spike_sorting.py``).

What is simulated
-----------------
- The electrode grid of a real layout (``MCS60`` by default) at its real
  pitch, from :mod:`meanap.pipeline.probes`.
- On each of ``n_active_electrodes`` electrodes, 1–``max_units_per_electrode``
  neurons, 10–45 µm from the electrode centre, so each is seen on that
  electrode alone with an amplitude set by its distance.
- Firing: a low tonic Poisson rate per unit plus *network bursts* shared by
  all units — every few seconds, a ~200 ms window in which each unit fires a
  handful of spikes at short intervals. This is the regime that trips up
  Poisson-based contamination metrics and makes overlapping spikes common.
- Gaussian noise at a level typical of an MCS recording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from meanap.pipeline.probes import build_probe


@dataclass
class GroundTruthSpec:
    channel_layout: str = "MCS60"
    duration_s: float = 120.0
    fs: float = 25000.0
    n_active_electrodes: int = 30
    max_units_per_electrode: int = 3
    #: How many units per electrode, as weights for 1, 2, 3, … units.
    units_per_electrode_weights: tuple[float, ...] = (0.5, 0.35, 0.15)
    tonic_rate_hz: tuple[float, float] = (0.2, 2.0)
    burst_interval_s: tuple[float, float] = (1.5, 4.0)
    burst_duration_s: float = 0.2
    spikes_per_burst: tuple[int, int] = (2, 8)
    burst_participation: float = 0.7
    refractory_ms: float = 2.0
    noise_uv: float = 5.0
    #: Peak amplitude range each unit is drawn from (log-uniform), µV.
    amplitude_uv: tuple[float, float] = (15.0, 120.0)
    seed: int = 0
    #: Extra keyword arguments for ``generate_templates``.
    template_kwargs: dict[str, Any] = field(default_factory=dict)


def _bursty_train(rng, spec: GroundTruthSpec, burst_times: np.ndarray, rate: float) -> np.ndarray:
    n_tonic = rng.poisson(rate * spec.duration_s)
    t = list(rng.uniform(0, spec.duration_s, n_tonic))
    for b in burst_times:
        if rng.uniform() > spec.burst_participation:
            continue
        n = rng.integers(spec.spikes_per_burst[0], spec.spikes_per_burst[1] + 1)
        # Spikes crowd the start of the burst, as they do in a culture.
        offsets = np.sort(rng.exponential(spec.burst_duration_s / 3, n))
        t.extend(b + offsets[offsets < spec.burst_duration_s])
    t = np.sort(np.array(t))
    # Enforce the refractory period.
    keep = np.ones(len(t), dtype=bool)
    last = -np.inf
    for i, ti in enumerate(t):
        if ti - last < spec.refractory_ms / 1000:
            keep[i] = False
        else:
            last = ti
    t = t[keep]
    return t[(t > 0.01) & (t < spec.duration_s - 0.01)]


def make_ground_truth(spec: GroundTruthSpec):
    """Returns ``(dat, channels, fs, gt_sorting, info)``.

    ``dat`` is ``(n_samples, n_channels)`` float32 µV, the shape
    ``load_raw_recording`` returns; ``gt_sorting`` is a SpikeInterface sorting
    with a ``gt_channel_index`` property per unit; ``info`` records what was
    simulated.
    """
    import spikeinterface.full as si
    from spikeinterface.core.generate import generate_templates

    from meanap.pipeline.channel_layout import get_coords_from_layout

    rng = np.random.default_rng(spec.seed)
    channels, _ = get_coords_from_layout(spec.channel_layout)
    channels = np.asarray(channels, dtype=int)
    probe, kept = build_probe(spec.channel_layout, channels)
    positions = probe.contact_positions
    n_ch = len(kept)

    # Which electrodes have neurons, and how many each.
    active = rng.choice(n_ch, size=min(spec.n_active_electrodes, n_ch), replace=False)
    weights = np.array(spec.units_per_electrode_weights[:spec.max_units_per_electrode], float)
    weights /= weights.sum()
    counts = rng.choice(np.arange(1, len(weights) + 1), size=len(active), p=weights)

    unit_channel = np.repeat(active, counts)
    n_units = len(unit_channel)
    r = rng.uniform(10, 45, n_units)
    theta = rng.uniform(0, 2 * np.pi, n_units)
    z = rng.uniform(5, 25, n_units)
    unit_locations = np.column_stack([
        positions[unit_channel, 0] + r * np.cos(theta),
        positions[unit_channel, 1] + r * np.sin(theta),
        z,
    ])

    ms_before, ms_after = 1.0, 3.0
    templates = generate_templates(
        positions, unit_locations, spec.fs, ms_before, ms_after,
        seed=spec.seed, dtype="float32", **spec.template_kwargs,
    )
    # The generator's distance model leaves some units far too small to ever
    # be seen; amplitudes are set here instead, log-uniform over a culture's
    # range, keeping each template's shape and (tiny) spread to neighbours.
    peak = np.abs(templates).max(axis=(1, 2))
    target = np.exp(rng.uniform(np.log(spec.amplitude_uv[0]), np.log(spec.amplitude_uv[1]), n_units))
    templates = (templates * (target / peak)[:, None, None]).astype("float32")

    burst_times = []
    t = rng.uniform(*spec.burst_interval_s)
    while t < spec.duration_s - spec.burst_duration_s:
        burst_times.append(t)
        t += rng.uniform(*spec.burst_interval_s)
    burst_times = np.array(burst_times)

    rates = rng.uniform(*spec.tonic_rate_hz, n_units)
    trains = {f"gt{u}": (_bursty_train(rng, spec, burst_times, rates[u]) * spec.fs).astype(np.int64)
              for u in range(n_units)}
    gt_sorting = si.NumpySorting.from_unit_dict(trains, sampling_frequency=spec.fs)
    gt_sorting.set_property("gt_channel_index", unit_channel)
    gt_sorting.set_property("gt_channel_id", channels[kept][unit_channel])
    gt_sorting.set_property("gt_amplitude_uv", np.abs(templates).max(axis=(1, 2)))

    rec, _ = si.generate_ground_truth_recording(
        durations=[spec.duration_s], sampling_frequency=spec.fs,
        num_channels=n_ch, num_units=n_units, sorting=gt_sorting, probe=probe,
        templates=templates, ms_before=ms_before, ms_after=ms_after,
        noise_kwargs={"noise_levels": spec.noise_uv, "strategy": "on_the_fly"},
        seed=spec.seed,
    )
    dat = rec.get_traces().astype(np.float32)
    info = {
        "n_units": n_units, "n_active_electrodes": len(active),
        "units_per_electrode": np.bincount(counts)[1:].tolist(),
        "n_bursts": len(burst_times),
        "amplitudes_uv": np.abs(templates).max(axis=(1, 2)),
        "unit_channel_id": channels[kept][unit_channel],
        "n_spikes": {u: len(tr) for u, tr in trains.items()},
    }
    return dat, channels[kept], spec.fs, gt_sorting, info


def score_against_ground_truth(gt_sorting, sorting, fs: float, delta_ms: float = 0.4) -> dict[str, Any]:
    """Standard sorter-vs-ground-truth scores, plus the counts a network
    analysis cares about: how many true neurons became a node, how many
    nodes are not a neuron."""
    import spikeinterface.full as si

    cmp = si.compare_sorter_to_ground_truth(gt_sorting, sorting, delta_time=delta_ms,
                                            exhaustive_gt=True)
    perf = cmp.get_performance(method="by_unit")
    return {
        "n_gt": len(gt_sorting.unit_ids),
        "n_sorted": len(sorting.unit_ids),
        "accuracy_mean": float(perf["accuracy"].mean()),
        "accuracy_median": float(perf["accuracy"].median()),
        "precision_mean": float(perf["precision"].mean()),
        "recall_mean": float(perf["recall"].mean()),
        "n_well_detected": int(cmp.count_well_detected_units(well_detected_score=0.8)),
        "n_found": int((perf["accuracy"] >= 0.5).sum()),
        "n_false_positive": int(cmp.count_false_positive_units(redundant_score=0.2)),
        "n_redundant": int(cmp.count_redundant_units(redundant_score=0.2)),
        "n_overmerged": int(cmp.count_overmerged_units(overmerged_score=0.2)),
        "per_unit": perf,
        "comparison": cmp,
    }
