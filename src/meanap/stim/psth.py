"""PSTH computation + response metrics aligned to stimulation.

Port of ``calculate_psth_metrics.m``, ``WithinRanges.m``,
``getSpikeLatencyRelStim.m``, ``getStimArtifactDuration.m`` and
``getFrAlignedToStim.m``.

The **individual-electrode analysis** that produces
``StimActivity_NodeLevel.csv`` uses *gaussian* smoothing (fixed 1 ms width), so
that path is fully deterministic and reproduces MATLAB exactly. The adaptive
``ssvkernel`` path (used only for population-level plots) lives in
``ssvkernel.py`` and is wired in here via ``smoothing_method='ssvkernel'``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# np.trapz was removed in NumPy 2.0 in favour of np.trapezoid
_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


# ── artifact duration ─────────────────────────────────────────────────────────

def get_stim_artifact_duration(params: dict) -> float:
    """Duration (s) blanked after each stimulus (port of ``getStimArtifactDuration.m``).

    ``artifactDuration_s`` if precomputed, else ``blankDurMode + postStimWindowDur/1000``
    (``postStimWindowDur`` is in **ms**). Missing fields count as zero.
    """
    if params.get("artifactDuration_s"):
        return float(params["artifactDuration_s"])
    blank_dur = float(params.get("blankDurMode") or 0.0)
    ignore_dur = float(params.get("postStimWindowDur") or 0.0) / 1000.0
    return blank_dur + ignore_dur


# ── per-trial spike extraction (WithinRanges, inclusive both ends) ─────────────

def _spikes_by_event(
    all_spike_times_s: np.ndarray,
    stim_times_s: np.ndarray,
    window_s: tuple[float, float],
) -> list[np.ndarray]:
    """Spikes within ``[stim+w0, stim+w1]`` per trial, offset to stim onset.

    Reproduces ``WithinRanges(..., 'matrix')`` membership: inclusive on both
    ends. Windows here never overlap (trials are seconds apart, window is ±ms).
    """
    w0, w1 = window_s
    out = []
    for st in stim_times_s:
        lo, hi = st + w0, st + w1
        sel = all_spike_times_s[(all_spike_times_s >= lo) & (all_spike_times_s <= hi)]
        out.append(sel - st)
    return out


# ── PSTH metrics ──────────────────────────────────────────────────────────────

@dataclass
class PsthData:
    spike_times_by_event: list[np.ndarray]
    psth_samples: np.ndarray
    psth_histogram: np.ndarray


@dataclass
class PsthMetrics:
    time_vector_s: np.ndarray
    psth_smooth: np.ndarray
    kernel_bandwidth_s: np.ndarray
    auc: float
    peak_firing_rate: float
    peak_time_s: float


_L = 1000                 # smoothing grid points
_MIN_SPIKES_FOR_KDE = 5


def calculate_psth_metrics(
    all_spike_times_s: np.ndarray,
    stim_times_s: np.ndarray,
    window_s: tuple[float, float],
    bin_width_s: float,
    smoothing_method: str = "ssvkernel",
    gaussian_width_ms: float = 2.0,
    artifact_exclusion_duration_s: float = 0.0,
    auc_start_s: float = np.nan,
) -> tuple[PsthData, PsthMetrics]:
    """Port of ``calculate_psth_metrics.m``.

    Returns ``(psth_data, metrics)``. See the MATLAB docstring for semantics.
    ``auc_start_s`` (default NaN = full window) restricts AUC/peak to
    ``[auc_start_s, window_s[1]]`` after smoothing.
    """
    all_spike_times_s = np.asarray(all_spike_times_s, dtype=float).ravel()
    stim_times_s = np.asarray(stim_times_s, dtype=float).ravel()
    num_trials = stim_times_s.shape[0]

    spikes_by_event = _spikes_by_event(all_spike_times_s, stim_times_s, window_s)

    # artifact exclusion within each trial's window
    if artifact_exclusion_duration_s > 0:
        excl_start = window_s[0]
        excl_end = window_s[0] + artifact_exclusion_duration_s
        spikes_by_event = [
            s[(s < excl_start) | (s > excl_end)] for s in spikes_by_event
        ]

    psth_samples = (
        np.concatenate(spikes_by_event) if spikes_by_event else np.array([])
    )
    psth_samples = psth_samples[~np.isnan(psth_samples)] if psth_samples.size else psth_samples

    # raw histogram (kept for parity of psth_data; metrics use the smoothed PSTH)
    edges = np.arange(window_s[0], window_s[1] + bin_width_s / 2, bin_width_s)
    if psth_samples.size:
        b = _histc(psth_samples, edges)
        psth_histogram = b / (num_trials * bin_width_s)
    else:
        psth_histogram = np.zeros(edges.shape[0])

    psth_data = PsthData(spikes_by_event, psth_samples, psth_histogram)

    t_s = np.linspace(window_s[0], window_s[1], _L)

    if smoothing_method == "ssvkernel":
        from .ssvkernel import ssvkernel
        if psth_samples.size >= _MIN_SPIKES_FOR_KDE:
            yv_pdf, tv_s, optw = ssvkernel(psth_samples, t_s)
            yv = yv_pdf * (psth_samples.size / num_trials)
            metrics = PsthMetrics(tv_s, yv, optw, float(_trapz(yv, tv_s)),
                                  float(np.max(yv)), float(tv_s[int(np.argmax(yv))]))
        else:
            metrics = PsthMetrics(t_s, np.zeros(_L), np.zeros(_L), 0.0, 0.0, np.nan)
    elif smoothing_method == "gaussian":
        metrics = _gaussian_smooth(psth_samples, t_s, gaussian_width_ms, num_trials)
    else:
        raise ValueError(f"unknown smoothing_method {smoothing_method!r}")

    # post-stim restriction of AUC + peak
    if not np.isnan(auc_start_s) and metrics.auc != 0:
        tv = metrics.time_vector_s
        mask = tv >= auc_start_s
        metrics.auc = float(_trapz(metrics.psth_smooth[mask], tv[mask]))
        restricted = metrics.psth_smooth[mask]
        tv_r = tv[mask]
        idx = int(np.argmax(restricted))
        metrics.peak_firing_rate = float(restricted[idx])
        metrics.peak_time_s = float(tv_r[idx])

    return psth_data, metrics


def _gaussian_smooth(
    psth_samples: np.ndarray,
    t_s: np.ndarray,
    gaussian_width_ms: float,
    num_trials: int,
) -> PsthMetrics:
    """Fixed-bandwidth gaussian PSTH (literal port of the 'gaussian' branch)."""
    gaussian_width_s = gaussian_width_ms / 1000.0
    if psth_samples.size == 0:
        return PsthMetrics(t_s, np.zeros(_L),
                           np.full(_L, gaussian_width_s), 0.0, 0.0, np.nan)

    sigma_s = gaussian_width_s / (2 * np.sqrt(2 * np.log(2)))  # FWHM → sigma
    dt = t_s[1] - t_s[0]
    kernel_points = 5 * sigma_s / dt
    n_points = round(2 * kernel_points) + 1
    if n_points % 2 == 0:
        n_points += 1
    kernel_t = np.linspace(-5 * sigma_s, 5 * sigma_s, n_points)
    kernel = np.exp(-0.5 * (kernel_t / sigma_s) ** 2) / (sigma_s * np.sqrt(2 * np.pi))

    half = n_points // 2          # == floor(len/2)
    L = t_s.shape[0]
    yv = np.zeros(L)
    for spike in psth_samples:
        ci = int(np.argmin(np.abs(t_s - spike)))          # 0-based centre in t_s
        s0 = max(0, ci - half)
        e0 = min(L - 1, ci + half)
        ks = max(0, half - (ci - s0))
        ke = min(n_points - 1, half + (e0 - ci))
        yv[s0:e0 + 1] += kernel[ks:ke + 1]

    yv = yv / num_trials
    return PsthMetrics(t_s, yv, np.full(L, gaussian_width_s),
                       float(_trapz(yv, t_s)),
                       float(np.max(yv)), float(t_s[int(np.argmax(yv))]))


def _histc(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """MATLAB ``histc``: bin i = [edges[i], edges[i+1]); last bin = == edges[-1]."""
    out = np.zeros(edges.shape[0])
    idx = np.searchsorted(edges, x, side="right") - 1
    for k in idx:
        if 0 <= k < edges.shape[0] - 1:
            out[k] += 1
    out[-1] += np.sum(x == edges[-1])
    return out


# ── latency ───────────────────────────────────────────────────────────────────

def get_spike_latency_rel_stim(
    stim_times_s: np.ndarray,
    spike_times_s: np.ndarray,
    search_window_end_s: float,
) -> np.ndarray:
    """First-spike latency (ms) in ``(0, search_window_end_s]`` per stim.

    Port of ``getSpikeLatencyRelStim.m``. NaN where no spike in window.
    """
    stim_times_s = np.asarray(stim_times_s, dtype=float).ravel()
    spike_times_s = np.asarray(spike_times_s, dtype=float).ravel()
    out = np.empty(stim_times_s.shape[0])
    for i, st in enumerate(stim_times_s):
        rel = spike_times_s - st
        valid = rel[(rel > 0) & (rel <= search_window_end_s)]
        out[i] = np.min(valid) * 1000.0 if valid.size else np.nan
    return out


# ── population firing-rate tensor ──────────────────────────────────────────────

def get_fr_aligned_to_stim(
    spike_times_by_channel: list[np.ndarray],
    all_stim_times_s: np.ndarray,
    params: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Firing-rate tensor (n_channels × n_stim × n_bins) aligned to stim.

    Port of ``getFrAlignedToStim.m``. ``rasterBins`` spans ``stimAnalysisWindow``
    in ``rasterBinWidth`` steps; each bin holds ``histcounts / rasterBinWidth``.
    """
    window = params["stimAnalysisWindow"]
    bin_width = float(params["rasterBinWidth"])
    raster_bins = np.arange(window[0], window[1] + bin_width / 2, bin_width)
    n_bins = raster_bins.shape[0] - 1
    n_ch = len(spike_times_by_channel)
    n_stim = np.asarray(all_stim_times_s).shape[0]

    fr = np.full((n_ch, n_stim, n_bins), np.nan)
    for c in range(n_ch):
        sp = np.asarray(spike_times_by_channel[c], dtype=float).ravel()
        for e, st in enumerate(np.asarray(all_stim_times_s).ravel()):
            counts, _ = np.histogram(sp - st, bins=raster_bins)
            fr[c, e, :] = counts / bin_width
    return fr, raster_bins
