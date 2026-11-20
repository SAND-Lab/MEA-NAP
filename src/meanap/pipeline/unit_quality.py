"""Quality metrics for sorted units, in the manner of Bombcell.

A spike sorter returns units whatever the recording holds, and its own labels
(or none) are the only say on which are neurons. This module scores every unit
on the criteria Bombcell uses (Fabre, van Beest, Peters, Carandini & Harris
2023, *Bombcell: automated curation and cell classification of spike-sorted
electrophysiology data*, Zenodo, https://doi.org/10.5281/zenodo.8172821) and
labels it the way Bombcell does:

1. **noise**: the template is not a spike. Too many peaks or troughs, a
   trough-to-peak duration outside 0.1–1.15 ms, a baseline that is not flat,
   or a second peak too large for the trough before it.
2. **mua**: a spike, but not one isolated neuron. Too many refractory-period
   violations, too many spikes missing below the detection threshold, too few
   spikes, present for too little of the recording, or (when the amplitudes
   are in µV) too small or too low in SNR.
3. **good**: everything else.

Each unit also says *which* criteria it failed, and whether its waveform looks
**non-somatic** (axonal: a positive peak larger than the trough, or a narrow
trough between two peaks), which Bombcell reports without splitting by default.

It reads whatever a sorting provides: spike times always; per-spike amplitudes
for the missing-spike estimate; multi-channel templates and channel noise
levels for the waveform, amplitude and SNR criteria. A criterion the inputs
cannot support is left as NaN and does not count against a unit.

This is an independent implementation of the published methods, not
Bombcell's code. Two sets of thresholds (:data:`PRESETS`):

- ``"bombcell"``: Bombcell's defaults (``bombcell/default_parameters.py``,
  checked 2026-11-18), tuned on Neuropixels recordings sorted with Kilosort.
- ``"mea"`` (MEA-NAP's default): the same, except where a planar MEA's spikes
  or recording lengths break an assumption. There is no baseline-flatness
  test on a sparse array, because an MEA spike's template rises in a broad
  positive phase from about 1 ms before its trough, and that alone marked
  textbook spikes as noise. The floor is 50 spikes and 0.05 Hz, not 300
  spikes, because recordings are minutes long, not hours. There is no
  absolute amplitude floor: SNR ≥ 5 already sets one relative to each
  electrode's noise, and µV levels differ between MEA types.

Where the method differs from Bombcell's:

- **Refractory violations** use the sliding refractory-period test (the IBL
  "slidingRP" metric, Bombcell's current default) by default: for refractory
  periods of 1–10 ms, how confident can we be (90 %) that contamination is
  under each level, given the violations seen? A unit passes when, for some
  refractory period, it is confidently under 10 %, and fails when it is
  confidently over at every one. With too few spikes to tell, it fails under
  ``"bombcell"`` (as Bombcell does by default) and passes under ``"mea"``
  (Bombcell's ``keepUncertainRPVUnits``): a few minutes at under 1 Hz cannot
  confirm a 10 % contamination limit even with no violations at all. Hill et al. (2011)'s
  closed-form estimate at 2 ms (Bombcell's legacy method) is the
  ``refractory_method="hill"`` alternative.
- **SNR** is the template's largest absolute value over the peak channel's
  noise level, as SpikeInterface defines it, because an import seldom carries
  the raw voltage that Bombcell's own SNR is measured on.
- **Spatial decay** is only scored on dense probes (electrodes ≤ 40 µm apart).
  On a 60-electrode MEA or a sparse MaxWell routing, a unit is seen on one
  electrode, and a decay "slope" over electrodes 80–200 µm apart would mark
  every real neuron as noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np

__all__ = [
    "QualityThresholds", "UnitQualityInputs", "compute_unit_quality", "classify_units",
    "hill_contamination", "percent_spikes_missing", "presence_ratio", "waveform_metrics",
    "inputs_from_analyzer", "plot_unit_quality", "LABELS",
]

LABELS = ("good", "mua", "noise")
#: Electrode spacing at and below which a unit spans several electrodes and its
#: spatial decay means something.
DENSE_PROBE_UM = 40.0


@dataclass(frozen=True)
class QualityThresholds:
    """Bombcell's default classification thresholds."""

    # noise: waveform shape
    max_n_peaks: int = 2
    max_n_troughs: int = 1
    min_duration_us: float = 100.0
    max_duration_us: float = 1150.0
    max_baseline_fraction: float = 0.3
    max_second_peak_to_trough: float = 0.8
    #: exponential decay constant of amplitude with distance, per µm
    min_spatial_decay: float = 0.01
    max_spatial_decay: float = 0.1
    #: Raw-voltage test (:mod:`meanap.pipeline.unit_noise`): at or above this,
    #: the electrode's own noise makes at least half as many events as large
    #: as the unit's typical spike as the unit has — the unit cannot be told
    #: from noise. Not one of Bombcell's; scored only when the raw file is read.
    max_noise_fraction: float = 0.5
    # non-somatic
    max_main_peak_to_trough_nonsomatic: float = 0.8
    min_trough_to_peak2_nonsomatic: float = 5.0
    min_width_first_peak_nonsomatic: float = 4.0       # samples
    min_width_main_trough_nonsomatic: float = 5.0      # samples
    max_peak1_to_peak2_nonsomatic: float = 3.0
    # mua
    max_rpv_contamination: float = 0.1
    max_percent_missing: float = 20.0
    min_n_spikes: int = 300
    min_presence_ratio: float = 0.7
    min_amplitude_uv: float = 40.0
    min_snr: float = 5.0
    #: Below this firing rate a unit is mua; 0 for no floor (Bombcell has none).
    min_firing_rate: float = 0.0
    #: Whether the waveform's baseline is tested at all.
    test_baseline: bool = True
    # how the metrics are measured
    #: "sliding" (refractory periods swept, a confidence test) or "hill".
    refractory_method: str = "sliding"
    refractory_s: float = 0.002            # "hill" only
    censored_s: float = 0.0001
    sliding_refractory_s: tuple = tuple(np.arange(4, 41) * 0.25e-3)   # 1–10 ms
    sliding_confidence: float = 0.9
    #: A unit the sliding test can neither clear nor convict (too few spikes)
    #: passes. Bombcell's ``keepUncertainRPVUnits``; off there by default.
    keep_uncertain_refractory: bool = False
    presence_bin_s: float = 60.0
    peak_prominence: float = 0.2      # of the waveform's largest absolute value
    baseline_samples: int = 10        # template samples before the spike, for flatness


#: The threshold sets, by name. "mea" is what MEA-NAP uses unless told otherwise.
PRESETS = {
    "bombcell": QualityThresholds(),
    "mea": QualityThresholds(min_n_spikes=50, min_firing_rate=0.05, test_baseline=False,
                             min_amplitude_uv=0.0, keep_uncertain_refractory=True),
}
DEFAULT_PRESET = "mea"


def thresholds_for(preset: str | QualityThresholds | None) -> QualityThresholds:
    """A preset's thresholds (by name), or the thresholds given."""
    if isinstance(preset, QualityThresholds):
        return preset
    name = preset or DEFAULT_PRESET
    if name not in PRESETS:
        raise ValueError(f"Unknown unit-quality preset {name!r}: one of {sorted(PRESETS)}")
    return PRESETS[name]


@dataclass
class UnitQualityInputs:
    """What a sorting offers to score its units with."""

    unit_ids: list
    spike_trains: list            # seconds, one array per unit
    duration_s: float
    fs: float
    #: Per-spike amplitudes, one array per unit (any units; sign ignored).
    amplitudes: list | None = None
    #: (n_units, n_samples, n_channels) mean waveforms.
    templates: np.ndarray | None = None
    #: Templates and noise levels are in µV, so the amplitude floor applies.
    in_uv: bool = False
    #: (n_channels,) noise level per channel, the templates' units.
    noise_levels: np.ndarray | None = None
    #: (n_channels, 2) channel positions, µm.
    channel_xy_um: np.ndarray | None = None
    sorter: str = ""
    labels: np.ndarray | None = None     # the sorter's own, for comparison


# ── single metrics ────────────────────────────────────────────────────────────


def presence_ratio(train: np.ndarray, duration_s: float, bin_s: float = 60.0) -> float:
    """Fraction of time bins in which the unit fires, Bombcell's way: a bin
    counts when it holds at least 5 % of the 90th-percentile bin's spikes."""
    if duration_s <= 0:
        return float("nan")
    edges = np.arange(0.0, duration_s, bin_s)
    if len(edges) < 2:
        edges = np.array([0.0, duration_s])
    else:
        edges = np.append(edges, duration_s) if edges[-1] < duration_s - 1e-9 else edges
    counts, _ = np.histogram(train, bins=edges)
    if not len(counts):
        return float("nan")
    floor = 0.05 * np.percentile(counts, 90)
    return float(np.mean((counts >= floor) & (counts > 0)))


def hill_contamination(train: np.ndarray, duration_s: float, refractory_s: float = 0.002,
                       censored_s: float = 0.0001) -> float:
    """Estimated fraction of a unit's spikes that are another neuron's.

    Hill, Mehta & Kleinfeld (2011): if a fraction *c* of *N* spikes come from
    a contaminating Poisson source, spike pairs closer than the refractory
    period τR (and further apart than the censored period τC) arrive at
    ``2 (τR − τC) N² c (1 − c) / T``. Solved for *c* from the observed count
    of such pairs; 1 when more violations are seen than any *c* ≤ ½ explains.
    """
    st = np.sort(np.asarray(train, dtype=float))
    n = len(st)
    if n < 2 or duration_s <= 0:
        return float("nan")
    violations = _pair_violations(st, censored_s, refractory_s)
    if violations == 0:
        return 0.0
    k = 2.0 * (refractory_s - censored_s) * n * n
    disc = 1.0 - 4.0 * violations * duration_s / k     # of c² − c + v·T/k = 0
    if disc < 0:
        return 1.0
    return float(min((1.0 - np.sqrt(disc)) / 2.0, 1.0))


def _pair_violations(st: np.ndarray, censored_s: float, refractory_s: float) -> int:
    """Spike pairs (any two, not only neighbours) between τC and τR apart."""
    n = len(st)
    lo = np.searchsorted(st, st + censored_s, side="left" if censored_s > 0 else "right")
    hi = np.searchsorted(st, st + refractory_s, side="right")
    lo = np.maximum(lo, np.arange(1, n + 1))
    return int(np.maximum(hi - lo, 0).sum())


def sliding_rp_contamination(train: np.ndarray, duration_s: float,
                             refractory_s=tuple(np.arange(4, 41) * 0.25e-3),
                             censored_s: float = 0.0001, confidence: float = 0.9,
                             levels=tuple(np.arange(1, 71) * 0.005)) -> float:
    """The lowest contamination a unit is confidently below, swept over
    refractory periods (the sliding refractory-period test).

    A contaminating Poisson source making a fraction *c* of a unit's *N*
    spikes, at rate ``r = N / T``, lands about ``2 c r (τR − τC) N`` spikes
    within ``τR`` of another spike. If the unit had contamination *c*, seeing
    no more than the observed number of such pairs would have probability
    ``P = PoissonCDF(observed; expected)``. When ``P ≤ 1 − confidence``, the
    unit is confidently below *c*. The result is the smallest *c* (of
    *levels*, 0.5–35 %) that holds for some τR; ``inf`` when none does: too
    contaminated, or too few spikes to tell.
    """
    from scipy.stats import poisson

    st = np.sort(np.asarray(train, dtype=float))
    n = len(st)
    if n < 2 or duration_s <= 0:
        return float("nan")
    rate = n / duration_s
    taus = np.asarray(refractory_s, dtype=float)
    observed = np.array([_pair_violations(st, censored_s, tau) for tau in taus])
    levels = np.asarray(levels, dtype=float)
    expected = 2.0 * levels[:, None] * rate * (taus[None, :] - censored_s) * n
    p = poisson.cdf(observed[None, :], expected)          # (levels, taus)
    confident = (p <= 1.0 - confidence).any(axis=1)
    return float(levels[np.argmax(confident)]) if confident.any() else float("inf")


def sliding_rp_status(train: np.ndarray, duration_s: float, max_contamination: float = 0.1,
                      refractory_s=tuple(np.arange(4, 41) * 0.25e-3),
                      censored_s: float = 0.0001, confidence: float = 0.9) -> int:
    """Whether a unit's refractory period says it is clean (``1``),
    contaminated (``-1``), or cannot say (``0``).

    Clean: for some τR, confidently below *max_contamination*. Contaminated:
    for every τR, confidently above it (more pairs than that contamination
    would give, ``P(≥ observed) ≤ 1 − confidence``). Otherwise uncertain: too
    few spikes to tell, which on a short or slow recording is most units.
    """
    from scipy.stats import poisson

    st = np.sort(np.asarray(train, dtype=float))
    n = len(st)
    if n < 2 or duration_s <= 0:
        return 0
    rate = n / duration_s
    taus = np.asarray(refractory_s, dtype=float)
    observed = np.array([_pair_violations(st, censored_s, tau) for tau in taus])
    expected = 2.0 * max_contamination * rate * (taus - censored_s) * n
    if (poisson.cdf(observed, expected) <= 1.0 - confidence).any():
        return 1
    if (poisson.sf(observed - 1, expected) <= 1.0 - confidence).all():
        return -1
    return 0


def percent_spikes_missing(amplitudes: np.ndarray, n_bins: int = 50) -> float:
    """Percentage of a unit's spikes estimated to fall below detection.

    The amplitude distribution of a well-detected unit is roughly Gaussian;
    detection cuts off its lower tail. A Gaussian fitted to the histogram,
    zero below the smallest amplitude seen, says how much of the tail is
    missing (Hill et al. 2011; Bombcell's ``percentageSpikesMissing_gaussian``).
    NaN with fewer than 20 spikes or when the fit fails.
    """
    from scipy.optimize import curve_fit
    from scipy.stats import norm

    a = np.abs(np.asarray(amplitudes, dtype=float))
    a = a[np.isfinite(a)]
    if len(a) < 20:
        return float("nan")
    q1, q99 = np.percentile(a, [1, 99])
    a = a[a <= q99 + 10 * (q99 - q1)]           # drop extreme outliers
    counts, edges = np.histogram(a, bins=n_bins)
    centres = 0.5 * (edges[:-1] + edges[1:])
    cut = float(a.min())

    def model(x, height, mu, sigma):
        y = height * np.exp(-((x - mu) ** 2) / (2 * sigma ** 2))
        y[x < cut] = 0
        return y

    mode = centres[int(np.argmax(counts))]
    try:
        (height, mu, sigma), _ = curve_fit(
            model, centres, counts, p0=[counts.max(), mode, np.std(a)],
            bounds=([0, -np.inf, 1e-9], [np.inf, np.inf, np.inf]), maxfev=5000)
    except (RuntimeError, ValueError):
        return float("nan")
    return float(100.0 * norm.cdf((cut - mu) / sigma))


def waveform_metrics(wave: np.ndarray, fs: float, t: QualityThresholds) -> dict:
    """Shape metrics of one unit's template on its peak channel."""
    from scipy.signal import find_peaks, peak_widths

    nan = float("nan")
    out = {k: nan for k in ("n_peaks", "n_troughs", "duration_us", "baseline_fraction",
                            "second_peak_to_trough", "main_peak_to_trough",
                            "trough_to_peak2", "peak1_to_peak2", "first_peak_width",
                            "trough_width")}
    w = np.asarray(wave, dtype=float)
    if w.size < 5 or not np.isfinite(w).all() or np.abs(w).max() == 0:
        return out
    scale = np.abs(w).max()
    prominence = t.peak_prominence * scale
    troughs, _ = find_peaks(-w, prominence=prominence)
    peaks, _ = find_peaks(w, prominence=prominence)
    if not len(troughs):
        troughs = np.array([int(np.argmin(w))])
    trough = int(troughs[np.argmax(-w[troughs])])
    before = peaks[peaks < trough]
    after = peaks[peaks > trough]
    # The peak around the trough, either side; the trough's edge where there is none.
    p1 = int(before[np.argmax(w[before])]) if len(before) else int(np.argmax(w[:trough + 1]))
    p2 = int(after[np.argmax(w[after])]) if len(after) else trough + int(np.argmax(w[trough:]))
    depth = -w[trough]
    peak1, peak2 = max(w[p1], 0.0), max(w[p2], 0.0)
    main_peak = max(peak1, peak2)
    out["n_peaks"] = float(len(peaks))
    out["n_troughs"] = float(len(troughs))
    # Trough to the larger peak, Bombcell's waveformDuration_peakTrough.
    other = p2 if peak2 >= peak1 else p1
    out["duration_us"] = abs(other - trough) / fs * 1e6
    base = w[:max(min(t.baseline_samples, trough), 1)]
    out["baseline_fraction"] = float(np.abs(base).max() / scale)
    out["second_peak_to_trough"] = float(peak2 / depth) if depth > 0 else nan
    out["main_peak_to_trough"] = float(main_peak / depth) if depth > 0 else nan
    out["trough_to_peak2"] = float(depth / peak2) if peak2 > 0 else float("inf")
    out["peak1_to_peak2"] = float(peak1 / peak2) if peak2 > 0 else float("inf")
    # Only a real peak before the trough has a width; the trough's edge has none.
    out["first_peak_width"] = (float(peak_widths(w, [p1], rel_height=0.5)[0][0])
                               if len(before) and peak1 > 0 else 0.0)
    out["trough_width"] = float(peak_widths(-w, [trough], rel_height=0.5)[0][0])
    return out


def spatial_decay(template: np.ndarray, peak: int, xy_um: np.ndarray,
                  n_nearest: int = 6) -> float:
    """Exponential decay constant (per µm) of the unit's amplitude with
    distance from its peak channel, over the *n_nearest* channels."""
    from scipy.optimize import curve_fit

    amp = np.abs(template).max(axis=0)
    d = np.hypot(*(xy_um - xy_um[peak]).T)
    near = np.argsort(d)[:n_nearest]
    x, y = d[near], amp[near] / max(amp[peak], 1e-12)
    try:
        (rate,), _ = curve_fit(lambda xx, r: np.exp(-r * xx), x, y, p0=[0.05],
                               bounds=(0, np.inf), maxfev=2000)
    except (RuntimeError, ValueError):
        return float("nan")
    return float(rate)


# ── all units ─────────────────────────────────────────────────────────────────


def compute_unit_quality(inputs: UnitQualityInputs,
                         thresholds: str | QualityThresholds | None = None):
    """Every unit's metrics, label and failed criteria, as a DataFrame.

    *thresholds* is a preset name (:data:`PRESETS`; MEA-NAP's ``"mea"`` by
    default) or a :class:`QualityThresholds`.
    """
    import pandas as pd

    t = thresholds_for(thresholds)
    rows = []
    templates = inputs.templates
    dense = False
    if inputs.channel_xy_um is not None and len(inputs.channel_xy_um) > 1:
        from scipy.spatial import cKDTree

        xy = np.asarray(inputs.channel_xy_um, dtype=float)
        nn = cKDTree(xy).query(xy, k=2)[0][:, 1]
        dense = float(np.median(nn)) <= DENSE_PROBE_UM
    for i, (uid, train) in enumerate(zip(inputs.unit_ids, inputs.spike_trains)):
        train = np.asarray(train, dtype=float)
        row = {"unit_id": str(uid), "n_spikes": len(train),
               "firing_rate": len(train) / inputs.duration_s if inputs.duration_s else np.nan,
               "presence_ratio": presence_ratio(train, inputs.duration_s, t.presence_bin_s),
               "rpv_contamination": (
                   hill_contamination(train, inputs.duration_s, t.refractory_s,
                                      t.censored_s)
                   if t.refractory_method == "hill" else
                   sliding_rp_contamination(train, inputs.duration_s,
                                            t.sliding_refractory_s, t.censored_s,
                                            t.sliding_confidence)),
               "rpv_status": (sliding_rp_status(train, inputs.duration_s,
                                                t.max_rpv_contamination,
                                                t.sliding_refractory_s, t.censored_s,
                                                t.sliding_confidence)
                              if t.refractory_method != "hill" else np.nan),
               "percent_missing": (percent_spikes_missing(inputs.amplitudes[i])
                                   if inputs.amplitudes is not None else np.nan),
               "peak_channel": -1, "amplitude": np.nan, "snr": np.nan,
               "spatial_decay": np.nan}
        if templates is not None:
            tmpl = np.asarray(templates[i], dtype=float)
            peak = int(np.argmax(np.abs(tmpl).max(axis=0)))
            wave = tmpl[:, peak]
            row["peak_channel"] = peak
            row["amplitude"] = float(wave.max() - wave.min())
            if inputs.noise_levels is not None and inputs.noise_levels[peak] > 0:
                row["snr"] = float(np.abs(wave).max() / inputs.noise_levels[peak])
            row.update(waveform_metrics(wave, inputs.fs, t))
            if dense:
                row["spatial_decay"] = spatial_decay(tmpl, peak, inputs.channel_xy_um)
        if inputs.labels is not None:
            row["sorter_label"] = str(inputs.labels[i])
        rows.append(row)
    df = pd.DataFrame(rows)
    label, fails, nonsomatic = classify_units(df, t, amplitude_in_uv=inputs.in_uv)
    df["label"], df["fails"], df["non_somatic"] = label, fails, nonsomatic
    return df


def _gt(series, value):
    """``series > value``, False where the metric could not be measured."""
    s = np.asarray(series, dtype=float)
    return np.where(np.isfinite(s), s > value, False)


def _lt(series, value):
    s = np.asarray(series, dtype=float)
    return np.where(np.isfinite(s), s < value, False)


def _refractory_fails(contamination, status, t: QualityThresholds) -> np.ndarray:
    """Too contaminated: Hill's estimate over the limit, or the sliding test
    confident that it is (status -1)."""
    if t.refractory_method == "hill":
        return _gt(contamination, t.max_rpv_contamination)
    return np.asarray(status, dtype=float) == -1


def _refractory_unconfirmed(status, t: QualityThresholds) -> np.ndarray:
    """The sliding test could not clear the unit, and uncertain units fail."""
    if t.refractory_method == "hill" or t.keep_uncertain_refractory:
        return np.zeros(len(np.asarray(status)), dtype=bool)
    return np.asarray(status, dtype=float) == 0


def classify_units(df, t: QualityThresholds | None = None, *, amplitude_in_uv: bool = False):
    """Bombcell's labels for *df*'s metrics: ``(label, fails, non_somatic)``.

    *fails* names every criterion a unit failed, ``;``-separated, noise
    criteria first: a unit labelled mua says why, and so does a noise unit.
    """
    t = thresholds_for(t)
    n = len(df)
    col = lambda name: df[name] if name in df else np.full(n, np.nan)  # noqa: E731
    noise_tests = [
        ("peaks", _gt(col("n_peaks"), t.max_n_peaks)),
        ("troughs", _gt(col("n_troughs"), t.max_n_troughs)),
        ("duration", _lt(col("duration_us"), t.min_duration_us)
         | _gt(col("duration_us"), t.max_duration_us)),
        ("baseline", _gt(col("baseline_fraction"), t.max_baseline_fraction)
         if t.test_baseline else np.zeros(n, dtype=bool)),
        ("second peak", _gt(col("second_peak_to_trough"), t.max_second_peak_to_trough)),
        ("spatial decay", _lt(col("spatial_decay"), t.min_spatial_decay)
         | _gt(col("spatial_decay"), t.max_spatial_decay)),
        ("noise-like", ~_lt(col("noise_fraction"), t.max_noise_fraction)
         & np.isfinite(np.asarray(col("noise_fraction"), dtype=float))),
    ]
    mua_tests = [
        ("refractory", _refractory_fails(col("rpv_contamination"), col("rpv_status"), t)),
        ("missing spikes", _gt(col("percent_missing"), t.max_percent_missing)),
        ("few spikes", _lt(col("n_spikes"), t.min_n_spikes)),
        ("presence", _lt(col("presence_ratio"), t.min_presence_ratio)),
        ("firing rate", _lt(col("firing_rate"), t.min_firing_rate)),
        ("refractory unconfirmed", _refractory_unconfirmed(col("rpv_status"), t)),
    ]
    if amplitude_in_uv:
        if t.min_amplitude_uv > 0:
            mua_tests.append(("amplitude", _lt(col("amplitude"), t.min_amplitude_uv)))
        mua_tests.append(("SNR", _lt(col("snr"), t.min_snr)))
    noise = np.zeros(n, dtype=bool)
    mua = np.zeros(n, dtype=bool)
    reasons = [[] for _ in range(n)]
    for name, failed in noise_tests:
        noise |= failed
        for i in np.flatnonzero(failed):
            reasons[i].append(name)
    for name, failed in mua_tests:
        mua |= failed
        for i in np.flatnonzero(failed):
            reasons[i].append(name)
    label = np.where(noise, "noise", np.where(mua, "mua", "good"))
    nonsomatic = (
        (_lt(col("trough_to_peak2"), t.min_trough_to_peak2_nonsomatic)
         & _lt(col("first_peak_width"), t.min_width_first_peak_nonsomatic)
         & _lt(col("trough_width"), t.min_width_main_trough_nonsomatic)
         & _gt(col("peak1_to_peak2"), t.max_peak1_to_peak2_nonsomatic))
        | _gt(col("main_peak_to_trough"), t.max_main_peak_to_trough_nonsomatic))
    return label, ["; ".join(r) for r in reasons], nonsomatic


# ── reading a sorting ─────────────────────────────────────────────────────────


def inputs_from_analyzer(path: str | Path) -> UnitQualityInputs:
    """Everything a saved SpikeInterface ``SortingAnalyzer`` holds for scoring.

    Templates, noise levels and spike amplitudes are used where the analyzer
    has them computed; it need not have its recording.
    """
    import spikeinterface.core as sic

    analyzer = sic.load(Path(path))
    sorting = analyzer.sorting
    fs = float(sorting.get_sampling_frequency())
    ids = list(sorting.get_unit_ids())
    trains = [np.sort(np.asarray(sorting.get_unit_spike_train(u, segment_index=0))) / fs
              for u in ids]
    templates = noise = amplitudes = None
    if analyzer.has_extension("templates"):
        templates = analyzer.get_extension("templates").get_templates(operator="average")
    if analyzer.has_extension("noise_levels"):
        noise = np.asarray(analyzer.get_extension("noise_levels").get_data(), dtype=float)
    if analyzer.has_extension("spike_amplitudes"):
        # One value per spike, in the order of the sorting's spike vector.
        flat = np.asarray(analyzer.get_extension("spike_amplitudes").get_data(), dtype=float)
        unit_index = sorting.to_spike_vector()["unit_index"]
        if len(flat) == len(unit_index):
            amplitudes = [flat[unit_index == k] for k in range(len(ids))]
    in_uv = bool(getattr(analyzer, "return_in_uV", getattr(analyzer, "return_scaled", False)))
    labels = sorting.get_property("quality")
    return UnitQualityInputs(
        unit_ids=[str(u) for u in ids], spike_trains=trains,
        duration_s=float(analyzer.get_total_duration()), fs=fs,
        amplitudes=amplitudes, templates=templates, in_uv=in_uv, noise_levels=noise,
        channel_xy_um=np.asarray(analyzer.get_channel_locations(), float)[:, :2],
        sorter=str(sorting.get_annotation("sorter_name") or "spikeinterface"),
        labels=None if labels is None else np.asarray(labels).astype(str))


# ── figure ────────────────────────────────────────────────────────────────────

#: The metrics drawn, with the threshold field(s) marking their pass range.
_FIGURE_METRICS = (
    ("n_peaks", "peaks", None, "max_n_peaks", False),
    ("n_troughs", "troughs", None, "max_n_troughs", False),
    ("duration_us", "trough-to-peak duration (µs)", "min_duration_us", "max_duration_us", False),
    ("baseline_fraction", "baseline / peak", None, "max_baseline_fraction", False),
    ("rpv_status", "refractory test", None, None, False),
    ("rpv_contamination", "refractory contamination", None, "max_rpv_contamination", False),
    ("percent_missing", "spikes missing (%)", None, "max_percent_missing", False),
    ("n_spikes", "spikes", "min_n_spikes", None, True),
    ("presence_ratio", "presence ratio", "min_presence_ratio", None, False),
    ("amplitude", "amplitude (µV)", "min_amplitude_uv", None, True),
    ("snr", "SNR", "min_snr", None, True),
    ("noise_fraction", "noise events / unit's large spikes", None, "max_noise_fraction", True),
)

#: A log axis cannot show 0, and "noise makes none" is the commonest value for
#: a clean unit; such units are drawn at this floor instead of being dropped.
_LOG_FLOOR = {"noise_fraction": 1e-3}


def plot_unit_quality(df, path: str | Path, *, title: str = "",
                      thresholds: str | QualityThresholds | None = None,
                      amplitude_in_uv: bool = False) -> Path:
    """One histogram per metric, the pass range shaded, the units coloured by
    the label they got; a count of units per label in the title."""
    from meanap.native.chart import Bars, Chart, Legend, LegendItem, Panel, Rule, rgba
    from meanap.native.chart_paint import save_chart

    t = thresholds_for(thresholds)
    preset = next((name for name, v in PRESETS.items() if v == t), "custom")
    colours = {"good": "#2a9d8f", "mua": "#e9a23b", "noise": "#9a9a9a"}
    panels = []
    sliding = "rpv_status" in df and np.isfinite(np.asarray(df["rpv_status"], float)).any()
    shown = [m for m in _FIGURE_METRICS
             if m[0] in df and np.isfinite(np.asarray(df[m[0]], float)).any()
             and (amplitude_in_uv or m[0] != "amplitude")
             # The sliding test's outcome, not its estimate: most units have none.
             and not (sliding and m[0] == "rpv_contamination")]
    cols = 5
    for k, (metric, label, lo_key, hi_key, logx) in enumerate(shown):
        values = np.asarray(df[metric], dtype=float)
        if metric in _LOG_FLOOR:
            values = np.where(np.isfinite(values), np.maximum(values, _LOG_FLOOR[metric]), values)
        ok = np.isfinite(values) & ((values > 0) if logx else True)
        if not ok.any():
            continue
        v = np.log10(values[ok]) if logx else values[ok]
        lo, hi = float(v.min()), float(v.max())
        categories = None
        if metric == "rpv_status":
            categories = [(-1, "contaminated"), (0, "unsure"), (1, "clean")]
            lo, hi = -1.0, 1.0
        rules = []
        for key in (lo_key, hi_key):
            if key is None or (metric == "baseline_fraction" and not t.test_baseline):
                continue
            at = float(getattr(t, key))
            if at <= 0 and (logx or key.startswith("min_amplitude")):
                continue            # a floor of zero is no floor
            rules.append(np.log10(at) if logx else at)
        # The axis spans the data and the thresholds, so a threshold is never off it.
        lo, hi = min([lo, *rules]), max([hi, *rules])
        if hi - lo < 1e-9:
            lo, hi = lo - 0.5, hi + 0.5
        pad = 0.04 * (hi - lo)
        edges = np.linspace(lo, hi, 26)
        if categories is not None:
            edges, pad = np.array([-1.5, -0.5, 0.5, 1.5]), 0.5
        centres, width = 0.5 * (edges[:-1] + edges[1:]), edges[1] - edges[0]
        marks = []
        bottom = np.zeros(len(centres))
        for name in LABELS:
            sel = np.asarray(df["label"])[ok] == name
            counts, _ = np.histogram(v[sel], bins=edges)
            if counts.any():
                marks.append(Bars(centres, counts.astype(float), width=width * 0.92,
                                  base=bottom.copy(), colour=rgba(colours[name], 0.9),
                                  key=name, hover=[f"{int(c)} {name} unit(s)" for c in counts]))
            bottom += counts
        marks += [Rule(at, axis="x", colour=rgba("#d62728"), width=1.0, dash="--")
                  for at in rules]
        ticks = None
        if categories is not None:
            ticks = categories
        elif logx:
            ticks = _log_ticks(lo - pad, hi + pad)
        panels.append(Panel(cell=(k // cols, k % cols), marks=marks, xlabel=label,
                            ylabel="units" if k % cols == 0 else "", xticks=ticks,
                            xlim=(lo - pad, hi + pad), ylim=(0, max(bottom.max(), 1) * 1.08),
                            title_size=9, label_size=9, tick_size=8, grid=""))
    counts = {name: int((np.asarray(df["label"]) == name).sum()) for name in LABELS}
    legend = Legend([LegendItem(f"{name} ({counts[name]})", rgba(colours[name]), kind="box",
                                key=name) for name in LABELS], loc="best", size=8)
    if panels:
        panels[0].legend = legend
    rows = (len(panels) + cols - 1) // cols
    head = title + ("\n" if title else "") + (
        f"{len(df)} units: {counts['good']} good, {counts['mua']} multi-unit, "
        f"{counts['noise']} noise ({preset} thresholds, after Bombcell; red: thresholds)")
    chart = Chart(panels, size=(13, 2.6 * rows + 0.6), grid=(rows, cols), title=head,
                  title_size=10)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_chart(chart, path)
    return path


def _log_ticks(lo: float, hi: float) -> list[tuple[float, str]]:
    """Ticks for a log10 axis from *lo* to *hi* (in log10 units): the powers of
    ten, plus 2× and 5× when fewer than two powers fall inside — so an axis
    spanning less than a decade (11–21 µV) is still labelled."""
    for mults in ((1,), (1, 2, 5), (1, 2, 3, 5, 7)):
        ticks = [(np.log10(m * 10.0 ** e), f"{m * 10.0 ** e:g}")
                 for e in range(int(np.floor(lo)) - 1, int(np.ceil(hi)) + 1) for m in mults]
        ticks = [t for t in ticks if lo <= t[0] <= hi]
        if len(ticks) >= 2:
            return ticks
    return ticks


def thresholds_table(t: QualityThresholds | None = None) -> dict:
    """The thresholds as a plain dict, for a params file beside the results."""
    t = t or QualityThresholds()
    return {f.name: getattr(t, f.name) for f in fields(t)}


# ── in the pipeline ───────────────────────────────────────────────────────────

#: Where step 1 writes each imported recording's unit table and figure.
UNIT_QUALITY_DIR = "1_SpikeDetection/1D_UnitQuality"
UNIT_QUALITY_CSV = "_unit_quality.csv"
UNIT_QUALITY_META = "_unit_quality.json"
FIGURE_NAME = "4_UnitQualityMetrics"


def inputs_from_imported(imp, analyzer_path: str | Path | None = None) -> UnitQualityInputs:
    """Scoring inputs for an :class:`~meanap.pipeline.sorted_import.ImportedSorting`.

    A SpikeInterface analyzer gives everything (amplitudes, µV templates on
    every channel, noise levels). Other formats give the spike times and, where
    the sorter kept one, the template on the peak electrode, in the sorter's
    own units (phy's are whitened, SpyKING CIRCUS's normalised): enough for the
    refractory, presence and waveform-shape criteria, not for amplitude or SNR.
    """
    if analyzer_path is not None:
        try:
            got = inputs_from_analyzer(analyzer_path)
        except Exception:            # a bare sorting folder, or an older analyzer
            got = None
        if got is not None and list(got.unit_ids) == [str(u) for u in imp.sorter_unit_ids]:
            return got
    templates = None
    if imp.templates is not None and len(imp.templates):
        templates = np.asarray(imp.templates, dtype=float)[:, :, None]
    return UnitQualityInputs(
        unit_ids=[str(u) for u in imp.sorter_unit_ids], spike_trains=list(imp.spike_trains),
        duration_s=float(imp.duration_s), fs=float(imp.fs), templates=templates,
        sorter=imp.sorter, labels=np.asarray(imp.labels).astype(str))


def run_unit_quality(rec_name: str, imp, output_root: Path, *, analyzer_path=None,
                     drop_labels=(), preset: str | None = None, raw_path=None,
                     log=print):
    """Step 1's unit quality for one imported recording: score, save, draw, log.

    Report only: which units become nodes is still the sorter's labels and
    ``sorted_drop_labels``; the table's ``kept`` column says which those were.
    With *raw_path* (a MaxWell recording the sorting was made from), each unit
    is also tested against its electrode's own noise
    (:mod:`meanap.pipeline.unit_noise`) and a noise-like unit is labelled
    noise. Never stops the run.
    """
    import json

    import pandas as pd  # noqa: F401  (DataFrame methods)

    try:
        inputs = inputs_from_imported(imp, analyzer_path)
        df = compute_unit_quality(inputs, preset)
    except Exception as exc:  # noqa: BLE001 — a check, not a step
        log(f"  ! [{rec_name}] unit quality metrics failed ({exc})")
        return None
    out_dir = Path(output_root) / UNIT_QUALITY_DIR
    if raw_path is not None:
        df = _add_noise_test(df, rec_name, imp, raw_path, preset, inputs.in_uv, log,
                             out_dir=out_dir)
    df.insert(1, "kept", [int(lab not in set(drop_labels)) for lab in imp.labels])
    # The peak electrode, as the array names it, so the map can place the unit.
    df.insert(2, "electrode", np.asarray(imp.electrodes.ids)[np.asarray(imp.peak_index, int)])
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"{rec_name}{UNIT_QUALITY_CSV}", index=False)
    name = preset or DEFAULT_PRESET
    (out_dir / f"{rec_name}{UNIT_QUALITY_META}").write_text(json.dumps(
        {"preset": name, "in_uv": bool(inputs.in_uv), "sorter": inputs.sorter,
         "thresholds": thresholds_table(thresholds_for(preset))}, indent=1, default=float))
    try:
        plot_unit_quality(df, out_dir / f"{rec_name}_{FIGURE_NAME}.png", title=rec_name,
                          thresholds=preset, amplitude_in_uv=inputs.in_uv)
    except Exception as exc:  # noqa: BLE001
        log(f"  ! [{rec_name}] unit quality figure failed ({exc})")
    if raw_path is not None:
        from meanap.pipeline.unit_noise import FIGURE_NAME as NOISE_FIGURE, draw_saved_unit_examples

        try:
            draw_saved_unit_examples(output_root, rec_name,
                                     out_dir / f"{rec_name}_{NOISE_FIGURE}.png")
        except Exception as exc:  # noqa: BLE001
            log(f"  ! [{rec_name}] unit-vs-noise example figure failed ({exc})")
    counts = df["label"].value_counts()
    log(f"  [{rec_name}] unit quality ({name} thresholds, after Bombcell): "
        f"{int(counts.get('good', 0))} good, {int(counts.get('mua', 0))} multi-unit, "
        f"{int(counts.get('noise', 0))} noise of {len(df)}")
    return df


def _add_noise_test(df, rec_name, imp, raw_path, preset, in_uv, log, out_dir=None):
    """*df* with the raw-voltage noise test's columns and the labels redone.

    With *out_dir*, also saves a few example units' raw spikes and rate curves
    there (:func:`meanap.pipeline.unit_noise.save_examples`) for the figure.
    """
    from meanap.pipeline.unit_noise import EXAMPLES_SUFFIX, maxwell_unit_noise, save_examples

    t = thresholds_for(preset)
    try:
        noise, examples = maxwell_unit_noise(
            raw_path, imp, examples=True,
            log=log.detail if hasattr(log, "detail") else log)
    except Exception as exc:  # noqa: BLE001 — a check, not a step
        log(f"  ! [{rec_name}] unit-vs-noise test failed ({exc})")
        return df
    if out_dir is not None and examples:
        save_examples(Path(out_dir) / f"{rec_name}{EXAMPLES_SUFFIX}", examples)
    for c in noise.columns:
        df[c] = noise[c].to_numpy()
    df["label"], df["fails"], df["non_somatic"] = classify_units(df, t, amplitude_in_uv=in_uv)
    nf = np.asarray(df["noise_fraction"], dtype=float)
    scored = np.isfinite(nf)
    log(f"  [{rec_name}] unit-vs-noise test on the raw voltage: "
        f"{int((nf[scored] >= t.max_noise_fraction).sum())} of "
        f"{int(scored.sum())} unit(s) cannot be told from their electrode's noise")
    return df


def draw_saved_unit_quality(root: Path, rec_name: str, out_path: Path) -> Path | None:
    """Redraw a recording's unit-quality figure from its saved table, or ``None``."""
    import json

    import pandas as pd

    base = Path(root) / UNIT_QUALITY_DIR
    csv_path = base / f"{rec_name}{UNIT_QUALITY_CSV}"
    if not csv_path.exists():
        return None
    meta_path = base / f"{rec_name}{UNIT_QUALITY_META}"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    df = pd.read_csv(csv_path, keep_default_na=True)
    df["fails"] = df["fails"].fillna("")
    preset = meta.get("preset", DEFAULT_PRESET)
    return plot_unit_quality(df, out_path, title=rec_name,
                             thresholds=preset if preset in PRESETS else None,
                             amplitude_in_uv=bool(meta.get("in_uv", False)))
