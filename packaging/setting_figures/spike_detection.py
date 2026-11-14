"""Pictures for the Spike detection tab's settings cards.

Every picture runs MEA-NAP's own code on a small synthetic recording: the
bandpass filter, threshold and wavelet detectors from
``meanap.pipeline.spike_detection``, the burst detectors from
``meanap.pipeline.burst_detection`` and the sorting curation rule from
``meanap.pipeline.spike_sorting``. Seeds are fixed, so reruns give the same
files.
"""

from __future__ import annotations

import numpy as np
import pywt
from scipy.signal import butter, freqz

from meanap.pipeline.burst_detection import (
    burst_detect_isin, burst_detect_network, get_isin_threshold,
)
from meanap.pipeline.spike_detection import (
    WAVELETS, _MATLAB_SIGN, SpikeDetectionParams, _get_bior15_intwave, adapt_wavelet,
    align_peaks, bandpass_filter,
    detect_spikes_recording, detect_spikes_threshold, trace_noise,
)

try:
    from . import style
except ImportError:  # run as a script
    import style

FS = 25000.0  # Params.fs default


# ── Synthetic data ────────────────────────────────────────────────────────────

def spike_shape(fs: float = FS, amp: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """A typical extracellular spike: a sharp trough and a slower rebound.
    Returns (t_ms, waveform), trough at t = 0, trough value -amp."""
    t = np.arange(-1.0, 2.0, 1000.0 / fs)
    w = (-np.exp(-(t / 0.13) ** 2)
         + 0.32 * np.exp(-((t - 0.45) / 0.28) ** 2))
    return t, amp * w / -w.min()


def synthetic_trace(seconds: float = 2.0, rate: float = 12.0, seed: int = 1,
                    fs: float = FS, noise_uv: float = 5.0,
                    amps=(-15.0, -90.0), lfp_uv: float = 60.0):
    """Raw voltage (µV): noise + a slow field potential + spikes.
    Returns (raw, true_spike_frames, true_amplitudes)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    raw = rng.normal(0, noise_uv, n)
    t = np.arange(n) / fs
    raw += lfp_uv * np.sin(2 * np.pi * 3 * t) + 0.3 * lfp_uv * np.sin(2 * np.pi * 11 * t + 1)
    n_sp = rng.poisson(rate * seconds)
    frames = np.sort(rng.integers(int(0.01 * fs), n - int(0.01 * fs), n_sp))
    keep = np.r_[True, np.diff(frames) > int(0.003 * fs)]
    frames = frames[keep]
    amps_out = rng.uniform(amps[1], amps[0], len(frames))
    _, w = spike_shape(fs, 1.0)
    i0 = int(round(1.0 * fs / 1000))
    for f, a in zip(frames, amps_out):
        seg = slice(f - i0, f - i0 + len(w))
        raw[seg] += -a * w
    return raw, frames, amps_out


# ── Wavelets ──────────────────────────────────────────────────────────────────

def mea_wavelet(waveform: np.ndarray) -> np.ndarray:
    """The 'mea' wavelet the pipeline builds from a median spike
    (``adapt_wavelet``: MATLAB's adaptWavelet.m + pat2cwav), as the wavelet
    itself rather than its integral."""
    int_psi, x = adapt_wavelet(waveform)
    return np.diff(np.r_[0.0, int_psi]) / (x[1] - x[0])


def run_detector(raw: np.ndarray, *, thresholds=(), wavelets=(), cost=-0.12,
                 ref_ms: float = 2.0) -> dict[str, np.ndarray]:
    """Step 1 as the pipeline runs it on one channel (filter, detect, align,
    refractory), via ``detect_spikes_recording``. Returns {method: frames}."""
    p = SpikeDetectionParams(fs=FS, thresholds=list(thresholds), wname_list=list(wavelets),
                             cost_list=[cost], filter_low_pass=600.0,
                             filter_high_pass=8000.0, ref_period_ms=ref_ms,
                             wavelet_ref_period_ms=0.5, pos_peak_thr_mult=40.0)
    res = detect_spikes_recording(raw[:, None], np.array([1]), FS, p, max_workers=1)
    return {m: np.round(t * FS).astype(int) for m, t in res.spike_times[0].items()}


def _main_lobes(x, psi):
    """x of the wavelet's largest positive and negative lobes."""
    return x[np.argmax(psi)], x[np.argmin(psi)]


def draw_wavelets():
    names = list(WAVELETS)
    notes = {"bior1.5": "the default", "bior1.3": "shorter, plainer",
             "db2": "lopsided", "sym2": "db2 turned round",
             "haar": "a square step", "mea": "built from each\nelectrode's spikes"}
    fig, axes = style.figure((4.6, 3.5), nrows=2, ncols=3, sharey=True)
    axes = axes.ravel()
    t_sp, sp = spike_shape(FS, 1.0)
    for ax, name in zip(axes, names):
        if name == "mea":
            # The median spike get_template takes, put through adapt_wavelet.
            keep = (t_sp >= -0.6) & (t_sp <= 1.2)
            psi = mea_wavelet(sp[keep])
            x = np.linspace(-0.6, 1.2, len(psi))
            # adapt_wavelet smooths with a causal filter, which delays the
            # shape; line the troughs up so the two can be compared.
            sx = t_sp + x[np.argmin(psi)]
        else:
            out = pywt.Wavelet(name).wavefun(level=8)
            # Biorthogonal: the decomposition wavelet is what the CWT uses.
            # MATLAB draws sym2 the other way up from PyWavelets; so does
            # the pipeline.
            psi, x = out[1] * _MATLAB_SIGN.get(name, 1.0), out[-1]
            # Spike stretched so its trough spans the wavelet's two main
            # lobes, centred between them: the scale the detector would pick.
            hi, lo = _main_lobes(x, psi)
            k = abs(lo - hi) / 0.3
            sx = (hi + lo) / 2 + t_sp * k
        psi = psi / np.max(np.abs(psi))
        ax.plot(sx, sp, color=style.MUTED, lw=1.0, alpha=0.6)
        ax.plot(x, psi, color=style.ACCENT, lw=1.4)
        ax.axhline(0, color=style.MUTED, lw=0.5, alpha=0.5)
        ax.set_xlim(x[0], x[-1])
        ax.set_title(name, fontsize=9, color=style.INK)
        ax.text(0.5, -0.04, notes[name], transform=ax.transAxes, ha="center",
                va="top", fontsize=7, color=style.MUTED)
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ("bottom", "left"):
            ax.spines[side].set_visible(False)
        ax.set_ylim(-1.15, 1.15)
    axes[0].plot([], [], color=style.ACCENT, label="wavelet")
    axes[0].plot([], [], color=style.MUTED, alpha=0.6, label="a typical spike")
    fig.legend(loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.08))
    fig.subplots_adjust(wspace=0.1, hspace=0.55)
    return style.save(fig, "sd_wavelets")


def draw_wavelet_cost():
    raw, frames, _ = synthetic_trace(seconds=6.0, rate=15, seed=3, amps=(-12.0, -60.0))
    costs = np.round(np.arange(-0.40, 0.201, 0.04), 2)
    found, hits = [], []
    tol = int(0.001 * FS)
    for c in costs:
        det = run_detector(raw, wavelets=["bior1.5"], cost=float(c))["bior1p5"]
        found.append(len(det))
        hits.append(sum(np.any(np.abs(det - f) <= tol) for f in frames))
    fig, ax = style.figure((4.6, 2.3))
    ax.plot(costs, found, "o-", color=style.ACCENT, ms=3.5, label="spikes detected")
    ax.plot(costs, hits, "s-", color=style.ACCENT_3, ms=3, label="of which real spikes")
    ax.axhline(len(frames), color=style.MUTED, ls="--", lw=0.9,
               label=f"spikes in the recording ({len(frames)})")
    ax.set_ylim(0, max(found) * 1.1)
    ax.axvline(-0.12, color=style.ACCENT_2, lw=0.9, ls=":")
    ax.text(-0.115, max(found), "default −0.12", color=style.ACCENT_2,
            fontsize=7.5, va="top", ha="left")
    ax.set_xlabel("Wavelet cost")
    ax.set_ylabel("count")
    ax.text(0.01, 1.02, "← more spikes", transform=ax.transAxes, fontsize=7.5,
            color=style.MUTED, va="bottom")
    ax.text(0.99, 1.02, "fewer spikes →", transform=ax.transAxes, fontsize=7.5,
            color=style.MUTED, va="bottom", ha="right")
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.85))
    return style.save(fig, "sd_wavelet_cost")


# ── Thresholds ────────────────────────────────────────────────────────────────

def draw_thresholds():
    raw, frames, _ = synthetic_trace(seconds=0.4, rate=40, seed=7, amps=(-14.0, -70.0))
    filt = bandpass_filter(raw, FS, 600, 8000)
    t = np.arange(len(filt)) / FS * 1000
    noise = trace_noise(filt)
    found = run_detector(raw, thresholds=[3.0, 4.0, 5.0])
    fig, ax = style.figure((4.6, 2.5))
    ax.plot(t, filt, color=style.INK, lw=0.5)
    colours = {3: style.ACCENT_4, 4: style.ACCENT, 5: style.ACCENT_2}
    top = filt.max() + 8
    for k, (mult, col) in enumerate(colours.items()):
        thr = noise[1] - mult * noise[0]   # what detect_spikes_threshold uses
        det = found[f"thr{mult}"]
        ax.axhline(thr, color=col, lw=0.9, ls="--")
        y = top + 9 * (2 - k)
        ax.plot(t[det], np.full(len(det), y), "|", color=col, ms=5, mew=1.2)
        ax.text(t[-1] * 1.01, y, f"{mult}× MAD: {len(det)}", color=col,
                fontsize=7.5, va="center")
    ax.text(t[-1] * 1.01, top + 27, f"true: {len(frames)}", color=style.MUTED,
            fontsize=7.5, va="center")
    ax.set_xlim(0, t[-1])
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("filtered voltage (µV)")
    return style.save(fig, "sd_thresholds")


# ── Bandpass ──────────────────────────────────────────────────────────────────

def draw_bandpass():
    fig, (ax1, ax2) = style.figure((4.6, 3.3), nrows=2, ncols=1,
                                   gridspec_kw={"height_ratios": [1.1, 1]})
    low, high = 600.0, 8000.0
    b, a = butter(3, np.array([low, high]) / (FS / 2), btype="bandpass")
    w, h = freqz(b, a, worN=4096, fs=FS)
    gain = np.abs(h) ** 2  # filtfilt runs the filter twice
    ax1.semilogx(w[1:], gain[1:], color=style.ACCENT, lw=1.5)
    ax1.axvspan(low, high, color=style.SOFT, alpha=0.7, lw=0)
    for f, lab in ((low, "Low-pass cutoff\n600 Hz"), (high, "High-pass cutoff\n8000 Hz")):
        ax1.axvline(f, color=style.ACCENT_2, lw=0.9, ls="--")
        ax1.text(f, 1.08, lab, ha="center", va="bottom", fontsize=7.5, color=style.ACCENT_2)
    ax1.text(110, 0.45, "field potentials\nremoved", fontsize=7.5, color=style.MUTED, ha="center")
    ax1.text(2200, 0.45, "spikes\nkept", fontsize=7.5, color=style.INK, ha="center")
    ax1.set_xlim(30, FS / 2)
    ax1.set_ylim(0, 1.05)
    ax1.set_xlabel("frequency (Hz)", labelpad=1)
    ax1.set_ylabel("gain")

    raw, _, _ = synthetic_trace(seconds=0.25, rate=30, seed=11, amps=(-30.0, -70.0))
    filt = bandpass_filter(raw, FS, low, high)
    t = np.arange(len(raw)) / FS * 1000
    ax2.plot(t, raw - raw.mean() + 90, color=style.MUTED, lw=0.5)
    ax2.plot(t, filt, color=style.INK, lw=0.5)
    ax2.text(t[-1] * 1.01, 90, "raw", fontsize=7.5, color=style.MUTED, va="center")
    ax2.text(t[-1] * 1.01, 0, "filtered", fontsize=7.5, color=style.INK, va="center")
    ax2.set_xlim(0, t[-1])
    ax2.set_yticks([])
    ax2.spines["left"].set_visible(False)
    ax2.set_xlabel("time (ms)")
    fig.subplots_adjust(hspace=0.55)
    return style.save(fig, "sd_bandpass")


# ── Refractory periods ────────────────────────────────────────────────────────

def draw_refractory():
    """Two real spikes 1 ms apart (a burst): the threshold detector's 2 ms
    period keeps one, the wavelet detectors' 0.5 ms keeps both."""
    rng = np.random.default_rng(5)
    n = int(0.012 * FS)
    trace = rng.normal(0, 3.0, n)
    _, w = spike_shape(FS, 1.0)
    i0 = int(round(1.0 * FS / 1000))
    spikes = [int(0.004 * FS), int(0.005 * FS)]
    for f, a in zip(spikes, (60, 45)):
        trace[f - i0:f - i0 + len(w)] += a * w
    t = np.arange(n) / FS * 1000
    noise = trace_noise(trace)
    det2, thr = detect_spikes_threshold(trace, 4.0, 2.0, FS, noise=noise)
    det2, _ = align_peaks(det2, trace)
    det05, _ = detect_spikes_threshold(trace, 4.0, 0.5, FS, noise=noise)
    det05, _ = align_peaks(det05, trace)

    fig, ax = style.figure((4.6, 2.3))
    ax.plot(t, trace, color=style.INK, lw=0.9)
    ax.axhline(thr, color=style.MUTED, lw=0.8, ls="--")
    top = trace.max() + 8
    for y, det, col, lab in ((top + 14, det05, style.ACCENT_3, "0.5 ms (wavelet default)"),
                             (top, det2, style.ACCENT_2, "2 ms (threshold default)")):
        ax.plot(t[det], np.full(len(det), y), "v", color=col, ms=6)
        for f in det:
            ref = 0.5 if col == style.ACCENT_3 else 2.0
            ax.add_patch(__import__("matplotlib").patches.Rectangle(
                (t[f], y - 3), ref, 6, color=col, alpha=0.25, lw=0))
        ax.text(t[-1], y, f"{lab}: {len(det)} spike{'s' if len(det) != 1 else ''}",
                fontsize=7.5, color=col, ha="right", va="center")
    ax.set_xlim(t[0], t[-1])
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("µV")
    ax.text(t[spikes[1]] + 0.15, trace.min() - 2, "second spike,\n1 ms later",
            fontsize=7.5, color=style.MUTED, va="top")
    ax.set_ylim(trace.min() - 22, top + 22)
    return style.save(fig, "sd_refractory")


# ── Spike method ──────────────────────────────────────────────────────────────

def draw_spike_method():
    raw, frames, _ = synthetic_trace(seconds=1.0, rate=25, seed=21, amps=(-12.0, -60.0))
    found = run_detector(raw, thresholds=[4.0, 5.0], wavelets=["bior1.5"])
    rows = [("in the data", frames)] + [(m, found[m]) for m in ("bior1p5", "thr4", "thr5")]
    fig, ax = style.figure((4.6, 1.9))
    for i, (name, d) in enumerate(rows):
        y = len(rows) - 1 - i
        col = style.MUTED if i == 0 else style.PALETTE[i - 1]
        ax.plot(d / FS, np.full(len(d), y), "|", color=col, ms=9, mew=1.1)
        ax.text(1.01, y, f"{len(d)}", fontsize=7.5, color=col, va="center",
                transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("time (s)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.text(1.01, len(rows) - 0.4, "spikes", fontsize=7, color=style.MUTED,
            transform=ax.get_yaxis_transform(), va="bottom")
    return style.save(fig, "sd_spike_method")


# ── Active electrodes ─────────────────────────────────────────────────────────

def draw_active_electrodes():
    rng = np.random.default_rng(2)
    rates = np.sort(np.concatenate([10 ** rng.uniform(-1.3, 1.0, 22),
                                    10 ** rng.uniform(-3.2, -2.2, 5),
                                    np.zeros(3)]))[::-1]
    fig, ax = style.figure((4.6, 2.2))
    floor = 0.01
    shown = np.where(rates > 0, rates, 2e-4)
    cols = [style.ACCENT if r >= floor else style.MUTED for r in rates]
    ax.bar(np.arange(len(rates)), shown, color=cols, width=0.8, bottom=1e-4)
    ax.set_yscale("log")
    ax.set_ylim(1e-4, 30)
    ax.axhline(floor, color=style.ACCENT_2, lw=1, ls="--")
    ax.text(len(rates) - 0.5, floor * 1.3, "Min activity level 0.01",
            color=style.ACCENT_2, fontsize=7.5, ha="right", va="bottom")
    n_act = int(np.sum(rates >= floor))
    ax.text(n_act / 2, 15, f"active ({n_act})", color=style.ACCENT, fontsize=7.5, ha="center")
    ax.text(n_act + (len(rates) - n_act) / 2 - 0.5, 0.2, f"left out\n({len(rates) - n_act})",
            color=style.MUTED, fontsize=7.5, ha="center")
    ax.set_xticks([])
    ax.set_xlabel("electrodes, busiest first")
    ax.set_ylabel("firing rate (spikes/s)")
    return style.save(fig, "sd_active_electrodes")


# ── Bursts ────────────────────────────────────────────────────────────────────

def bursty_train(seed: int, seconds: float = 20.0, bg_rate: float = 1.0,
                 burst_times=None, burst_rate: float = 120.0,
                 burst_len: float = 0.15) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = list(rng.uniform(0, seconds, rng.poisson(bg_rate * seconds)))
    for b in burst_times if burst_times is not None else []:
        n = rng.poisson(burst_rate * burst_len)
        t.extend(b + rng.uniform(0, burst_len, n))
    return np.sort(np.round(np.asarray(t) * FS) / FS)


def draw_bursts():
    seconds = 20.0
    rng = np.random.default_rng(4)
    bursts = np.sort(rng.uniform(1, seconds - 1, 7))
    train = bursty_train(8, seconds, 1.5, bursts, burst_rate=110, burst_len=0.25)
    n = 5
    th = get_isin_threshold(train, n=n)
    info, _ = burst_detect_isin(train, n, th)

    fig, (ax1, ax2) = style.figure((4.6, 3.0), nrows=2, ncols=1,
                                   gridspec_kw={"height_ratios": [0.7, 1]})
    for s, e in zip(info["T_start"], info["T_end"]):
        ax1.axvspan(s, e, color=style.ACCENT_4, alpha=0.35, lw=0)
    ax1.plot(train, np.zeros(len(train)), "|", color=style.INK, ms=12, mew=0.6)
    ax1.set_xlim(0, seconds)
    ax1.set_yticks([])
    ax1.spines["left"].set_visible(False)
    ax1.set_xlabel("time (s)", labelpad=1)
    ax1.set_title(f"one electrode: {len(info['T_start'])} bursts found", fontsize=8.5,
                  loc="left", color=style.INK)

    isin = train[n - 1:] - train[:-(n - 1)]
    steps = 10 ** np.arange(-5, 1.55, 0.05)
    ax2.hist(isin, bins=steps, color=style.ACCENT, alpha=0.8)
    ax2.set_xscale("log")
    ax2.axvline(th, color=style.ACCENT_2, ls="--", lw=1)
    ax2.text(th, ax2.get_ylim()[1] * 0.95,
             f" automatic\n threshold\n {th * 1000:.0f} ms" + (" (cap)" if th >= 0.1 else ""),
             color=style.ACCENT_2, fontsize=7.5, va="top")
    ax2.set_xlim(1e-3, 10)
    ax2.set_xlabel(f"time spanned by {n} consecutive spikes (ISI$_N$, s)")
    ax2.set_ylabel("count")
    ax2.text(0.02, 0.95, "inside\nbursts", transform=ax2.transAxes, fontsize=7.5,
             color=style.MUTED, va="top")
    ax2.text(0.98, 0.95, "between\nbursts", transform=ax2.transAxes, fontsize=7.5,
             color=style.MUTED, va="top", ha="right")
    fig.subplots_adjust(hspace=0.75)
    return style.save(fig, "sd_bursts")


def draw_network_bursts():
    seconds = 10.0
    rng = np.random.default_rng(12)
    events = np.sort(rng.uniform(0.5, seconds - 0.5, 5))
    n_ch = 12
    trains = {}
    for ch in range(n_ch):
        # Each event recruits most, not all, electrodes.
        joined = events[rng.random(len(events)) < 0.8]
        trains[ch] = bursty_train(100 + ch, seconds, 0.8, joined + rng.uniform(0, 0.03),
                                  burst_rate=120, burst_len=0.2)
    # One local event on two electrodes only: fewer than min channels. Every
    # electrode with *any* spike inside a burst's span counts towards min
    # channels, so put it where the other electrodes are quiet.
    local = (2, 3)
    others = np.concatenate([trains[c] for c in range(n_ch) if c not in local])
    at = next(x for x in np.arange(5.0, 9.0, 0.05)
              if not np.any(np.abs(others - (x + 0.04)) < 0.15))
    for ch in local:
        extra = bursty_train(300 + ch, 0.0, 0.0, [at], burst_rate=150, burst_len=0.08)
        trains[ch] = np.sort(np.concatenate([trains[ch], extra]))
    _, times, chans, info = burst_detect_network(trains, FS, min_spikes=10,
                                                 min_channels=3, merge_gap_ms=20.0)
    fig, ax = style.figure((4.6, 2.5))
    for s, e in times / FS:
        ax.axvspan(s, e, color=style.ACCENT_4, alpha=0.35, lw=0)
    for ch, t in trains.items():
        ax.plot(t, np.full(len(t), ch), "|", color=style.INK, ms=5, mew=0.6)
    ax.annotate("2 electrodes only:\nnot a network burst", xy=(at + 0.05, 3.4),
                xytext=(at - 0.8, 6.3), fontsize=7.5, color=style.MUTED,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"),
                arrowprops=dict(arrowstyle="-", color=style.MUTED, lw=0.7))
    ax.set_xlim(0, seconds)
    ax.set_ylim(-0.8, n_ch - 0.2)
    ax.set_yticks([])
    ax.set_ylabel("electrodes")
    ax.set_xlabel("time (s)")
    ax.set_title(f"{len(times)} network bursts (shaded); ISI$_N$ threshold "
                 f"{info['isin_th'] * 1000:.0f} ms", fontsize=8.5, loc="left")
    return style.save(fig, "sd_network_bursts")


# ── Sorting curation ──────────────────────────────────────────────────────────

def draw_curation():
    from meanap.pipeline.spike_sorting import label_unit

    class P:  # the curation fields label_unit reads, at their defaults
        curation_min_snr = 4.0
        curation_min_firing_rate = 0.05
        curation_max_rp_violation_frac = 0.05

    rng = np.random.default_rng(9)
    snr = np.concatenate([rng.uniform(5, 18, 18), rng.uniform(5, 14, 7), rng.uniform(1.5, 4, 7)])
    rp = np.concatenate([rng.uniform(0, 0.04, 18), rng.uniform(0.06, 0.17, 7),
                         rng.uniform(0, 0.2, 7)])
    labels = [label_unit(s, r, 1.0, P) for s, r in zip(snr, rp)]
    colour = {"good": style.ACCENT_3, "mua": style.ACCENT_4, "noise": style.MUTED}
    name = {"good": "good", "mua": "multi-unit", "noise": "noise (dropped)"}
    fig, ax = style.figure((4.6, 2.4))
    for lab in ("good", "mua", "noise"):
        m = np.array([u == lab for u in labels])
        ax.scatter(snr[m], rp[m] * 100, s=16, color=colour[lab], label=name[lab],
                   edgecolor="white", lw=0.4)
    ax.axvline(4.0, color=style.INK, lw=0.8, ls="--")
    ax.axhline(5.0, color=style.INK, lw=0.8, ls="--", xmin=(4.0 - 0) / 20)
    ax.text(4.2, 30, "min SNR 4", fontsize=7.5)
    ax.text(19.8, 5.6, "max refractory violations 5 %", fontsize=7.5, ha="right")
    ax.set_xlim(0, 20)
    ax.set_ylim(-1, 32)
    ax.set_xlabel("unit SNR (template peak / noise)")
    ax.set_ylabel("ISIs < 1.5 ms (%)")
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.02, 1.04))
    return style.save(fig, "sd_spike_sorting")


def main():
    _get_bior15_intwave()
    return [
        draw_wavelets(),
        draw_wavelet_cost(),
        draw_thresholds(),
        draw_bandpass(),
        draw_refractory(),
        draw_spike_method(),
        draw_active_electrodes(),
        draw_bursts(),
        draw_network_bursts(),
        draw_curation(),
    ]


if __name__ == "__main__":
    for p in main():
        print(p)
