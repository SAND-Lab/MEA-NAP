"""Pictures for the Stimulation (MEA-Stim) and CAT-NAP tabs' settings cards.

Every picture that shows a detection runs MEA-NAP's own code on small
synthetic data: ``meanap.stim.detection.detect_stim_times`` (``longblank``)
and the artifact window of ``meanap.stim.cleaning.artifact_windows`` for the
stimulation pictures, and ``meanap.catnap.denoising`` (baseline, threshold,
OASIS, ``find_peaks``) for the calcium ones. Seeds are fixed, so reruns give
the same files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from meanap.catnap.denoising import (
    _deconvolve_trace, _get_denoised_intensity, _poly_baseline, process_suite2p_folder,
)
from meanap.stim.cleaning import artifact_windows
from meanap.stim.detection import detect_stim_times

try:
    from . import style
except ImportError:  # run as a script
    import style

FS_MEA = 25000.0       # Params.fs default
FS_2P = 15.0           # a typical suite2p frame rate
STIM_TIMES = (0.6, 3.6, 6.6, 9.6)   # s, one pulse every 3 s


# ── Stimulation: synthetic blanked recording ──────────────────────────────────

def blanked_recording(seed: int = 3):
    """Two electrodes at 25 kHz: the stimulating one holds a 5 ms blank at
    each pulse, the recording one a 1.2 ms blank followed by the amplifier's
    recovery step and a couple of evoked spikes. Returns (raw µV, onsets)."""
    rng = np.random.default_rng(seed)
    n = int(10.5 * FS_MEA)
    raw = rng.normal(0, 5.0, (n, 2))
    t = np.arange(n) / FS_MEA
    for st in STIM_TIMES:
        i = int(st * FS_MEA)
        raw[i:i + int(0.005 * FS_MEA), 0] = raw[i, 0]          # long blank
        j = i + int(0.0012 * FS_MEA)
        raw[i:j, 1] = raw[i, 1]                                 # short blank
        after = t[j:j + int(0.004 * FS_MEA)] - t[j]
        raw[j:j + after.size, 1] += 70 * np.exp(-after / 0.0004)  # recovery step
        for lat in rng.uniform(0.004, 0.012, 2):                # evoked spikes
            k = i + int(lat * FS_MEA)
            w = np.arange(-10, 25)
            raw[k + w, 1] += -45 * np.exp(-(w / 4.0) ** 2) + 12 * np.exp(-((w - 10) / 7.0) ** 2)
    return raw


def stim_params(**over) -> dict:
    p = {"stimDetectionMethod": "longblank", "stimRefractoryPeriod": 2.9,
         "stimDuration": 0.00012, "fs": FS_MEA, "minBlankingDuration": 0.004,
         "stimDetectionVal": 150.0, "postStimWindowDur": 0.5}
    p.update(over)
    return p


def stim_detection_figure() -> Path:
    raw = blanked_recording()
    params = stim_params()
    info = detect_stim_times(raw, params, np.array([12, 13]), np.zeros((2, 2)))
    found = info[0].elec_stim_times
    starts, ends, _own = artifact_windows(info, params)

    fig, (top, zoom) = style.figure(style.TALL, nrows=2,
                                    gridspec_kw={"height_ratios": [1, 1.6], "hspace": 0.75})
    # Whole stretch: detected onsets and the refractory period after each.
    step = 50
    t = np.arange(raw.shape[0]) / FS_MEA
    top.plot(t[::step], raw[::step, 0], color=style.MUTED, lw=0.5)
    for st in found:
        top.axvspan(st, st + params["stimRefractoryPeriod"], color=style.SOFT, lw=0)
        top.plot(st, 24, "v", color=style.ACCENT, ms=5)
    top.text(found[0] + 0.1, -22, "refractory period 2.9 s", color=style.ACCENT,
             fontsize=7.5, va="center")
    top.set_xlim(0, 10.5)
    top.set_ylim(-28, 32)
    top.set_yticks([])
    top.set_xlabel("time (s)")
    top.set_title("stimulating electrode: one onset per pulse", loc="left")

    # One pulse, both electrodes.
    st = found[1]
    i0, i1 = int((st - 0.003) * FS_MEA), int((st + 0.014) * FS_MEA)
    tz = (t[i0:i1] - st) * 1000
    zoom.plot(tz, raw[i0:i1, 0] + 110, color=style.MUTED, lw=0.7)
    zoom.plot(tz, raw[i0:i1, 1], color=style.INK, lw=0.7)
    zoom.axvspan(0, 5, ymin=0.62, ymax=0.98, color=style.SOFT, lw=0)
    zoom.text(5.4, 110, "blank ≥ Min blanking\nduration (4 ms) → pulse",
              fontsize=7.5, va="center", color=style.ACCENT)
    a0 = (starts[1] - st) * 1000
    a1 = (ends[1] - st) * 1000
    zoom.axvspan(a0, a1, ymin=0.02, ymax=0.55, color=style.ACCENT_2, alpha=0.18, lw=0)
    zoom.annotate("short blank + 0.5 ms ignore:\nspikes here are dropped",
                  xy=(a1, -40), xytext=(4.0, -75), fontsize=7.5, color=style.ACCENT_2,
                  arrowprops={"arrowstyle": "-", "color": style.ACCENT_2, "lw": 0.7})
    zoom.axvline(0, color=style.ACCENT, lw=0.8, ls="--")
    zoom.text(-2.8, 150, "stimulating", fontsize=7.5, color=style.MUTED)
    zoom.text(-2.8, 30, "recording", fontsize=7.5, color=style.INK)
    zoom.set_xlim(-3, 14)
    zoom.set_ylim(-95, 170)
    zoom.set_yticks([])
    zoom.set_xlabel("time from detected onset (ms)")
    return style.save(fig, "stim_detection")


def stim_windows_figure() -> Path:
    """The response windows around one pulse, at their defaults."""
    fig, ax1 = style.figure(style.WIDE)
    artifact = 1.2 + 0.5   # ms: blank (measured) + post-stim ignore duration
    rng = np.random.default_rng(5)
    t = np.linspace(-30, 30, 601)
    rate = 4 + 40 * np.exp(-((t - 8) / 3.5) ** 2) * (t > artifact)
    rate = rate + rng.normal(0, 0.8, t.size)
    rate[(t >= 0) & (t <= artifact)] = 0
    ax1.plot(t, rate, color=style.INK, lw=0.9)
    ax1.axvspan(0, artifact, color=style.ACCENT_2, alpha=0.25, lw=0)
    ax1.axvspan(artifact, 30, ymin=0, ymax=0.08, color=style.ACCENT_3, lw=0)
    ax1.axvspan(-(30 - artifact), 0, ymin=0, ymax=0.08, color=style.MUTED, alpha=0.6, lw=0)
    ax1.text(16, 30, "response:\nartifact end → 30 ms", fontsize=7.5, color=style.ACCENT_3)
    ax1.text(-29, 30, "baseline: equally\nlong, before pulse", fontsize=7.5, color=style.MUTED)
    ax1.annotate("blank + ignore", xy=(artifact / 2, 50), xytext=(-4, 50), fontsize=7.5,
                 color=style.ACCENT_2, ha="right", va="center",
                 arrowprops={"arrowstyle": "-", "color": style.ACCENT_2, "lw": 0.7})
    ax1.set_xlim(-30, 30)
    ax1.set_ylim(0, 58)
    ax1.set_xlabel("time from pulse (ms): analysis window −30 to 30 ms")
    ax1.set_ylabel("rate (Hz)")
    return style.save(fig, "stim_windows")


def stim_networks_figure() -> Path:
    """The three network epochs around each stimulus, at their defaults."""
    fig, ax2 = style.figure((4.6, 1.7))
    rows = [("baseline", -0.5, 0.0, style.MUTED),
            ("evoked", 0.0, 0.5, style.ACCENT),
            ("post", 0.5, 1.0, style.ACCENT_4)]
    for y, (name, a, b, colour) in enumerate(rows):
        ax2.barh(2 - y, b - a, left=a, height=0.6, color=colour, alpha=0.85)
        ax2.text(a - 0.03, 2 - y, f"{name}  {a:g} to {b:g} s".replace("-", "−"),
                 ha="right", va="center", fontsize=7.5, color=colour)
    ax2.axvline(0, ymin=0.4, color=style.INK, lw=0.8, ls="--")
    ax2.set_xlim(-1.05, 1.1)
    ax2.set_ylim(-0.6, 2.6)
    ax2.set_yticks([])
    ax2.spines["left"].set_visible(False)
    ax2.set_xlabel("time from stimulus (s)")
    return style.save(fig, "stim_networks")


# ── CAT-NAP: one synthetic cell ───────────────────────────────────────────────

def synthetic_cell(seed: int = 7, seconds: float = 180.0):
    """Raw suite2p-style F for one cell at 15 Hz: a slow drift, shot noise and
    calcium transients (fast rise, ~1.2 s decay), one of them small."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS_2P)
    t = np.arange(n) / FS_2P
    spikes = np.zeros(n)
    for onset, k in ((12, 6), (31, 3), (47, 9), (63, 0.5), (66.5, 4), (88, 7),
                     (104, 2), (121, 5), (140, 8), (162, 4)):
        i = int(onset * FS_2P)
        spikes[i:i + 3] += k / 3
    kernel_t = np.arange(int(8 * FS_2P)) / FS_2P
    kernel = (1 - np.exp(-kernel_t / 0.15)) * np.exp(-kernel_t / 1.2)
    calcium = np.convolve(spikes, kernel)[:n]
    F = 400 + 25 * np.sin(2 * np.pi * t / 200) + 28 * calcium + rng.normal(0, 7, n)
    return t, F


def run_denoising(F: np.ndarray):
    """Run the pipeline's own ``process_suite2p_folder`` on one cell."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        np.save(d / "F.npy", F[None, :])
        np.save(d / "ops.npy", np.array({"fs": FS_2P}, dtype=object), allow_pickle=True)
        process_suite2p_folder(d, overwrite=True)
        denoised = np.load(d / "Fdenoised.npy")[0]
        starts = np.load(d / "peakStartFrames.npy")[0]
        ends = np.load(d / "peakEndFrames.npy")[0]
    starts = starts[~np.isnan(starts)].astype(int)
    ends = ends[~np.isnan(ends)].astype(int)
    return denoised, starts, ends


def activity_type_figure() -> Path:
    t, F = synthetic_cell()
    denoised, starts, _ends = run_denoising(F)
    # suite2p's spks is its own OASIS deconvolution; this stands in for it with
    # OASIS's spike estimate on the same cell's ΔF/F.
    from oasis.functions import deconvolve
    base = _poly_baseline(F)
    _c, spks, _b, _g, _lam = deconvolve((F - base) / base)

    show = (t >= 5) & (t <= 125)
    fig, axes = style.figure(style.TALL, nrows=4, sharex=True,
                             gridspec_kw={"hspace": 0.35})
    traces = [("F", F, style.MUTED), ("denoised F", denoised, style.ACCENT),
              ("spks", spks, style.ACCENT_3)]
    for ax, (name, y, colour) in zip(axes, traces):
        ax.plot(t[show], y[show], color=colour, lw=0.8)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.text(0.0, 0.98, name, transform=ax.transAxes, fontsize=8, va="top",
                color=colour, fontweight="bold")
    peaks_ax = axes[3]
    ev = t[starts]
    ev = ev[(ev >= 5) & (ev <= 125)]
    peaks_ax.vlines(ev, 0, 1, color=style.ACCENT_2, lw=1.4)
    peaks_ax.set_ylim(-0.1, 1.3)
    peaks_ax.set_yticks([])
    peaks_ax.spines["left"].set_visible(False)
    peaks_ax.text(0.0, 1.0, "peaks (event onsets)", transform=peaks_ax.transAxes,
                  fontsize=8, va="top", color=style.ACCENT_2, fontweight="bold")
    peaks_ax.set_xlim(5, 125)
    peaks_ax.set_xlabel("time (s)")
    return style.save(fig, "activity_type")


def peak_detection_figure() -> Path:
    t, F = synthetic_cell()
    threshold, before_s, after_s = 1.3, 1.0, 2.05
    base = _poly_baseline(F)
    level = base + threshold * abs(np.min(F - base))
    _delta, rel = _get_denoised_intensity(
        F, threshold, int(before_s * FS_2P), int(after_s * FS_2P))
    denoised, starts, ends = run_denoising(F)
    assert np.allclose(denoised, _deconvolve_trace(rel), equal_nan=True)

    lo, hi = 40, 100
    show = (t >= lo) & (t <= hi)
    fig, (ax1, ax2) = style.figure(style.TALL, nrows=2, sharex=True,
                                   gridspec_kw={"hspace": 0.3})
    ax1.plot(t[show], F[show], color=style.MUTED, lw=0.7)
    ax1.plot(t[show], base[show], color=style.INK, lw=0.9, ls="--")
    ax1.plot(t[show], level[show], color=style.ACCENT_2, lw=1.0)
    # The stretches step 1 of the denoising keeps: every sample above the
    # threshold, widened by the time before and after the peak.
    above = np.flatnonzero(F - level > 0)
    kept = np.zeros(F.size, bool)
    for i in above:
        kept[max(0, i - int(before_s * FS_2P)):i + int(after_s * FS_2P)] = True
    edges = np.flatnonzero(np.diff(np.r_[0, kept.astype(int), 0]))
    for a, b in zip(edges[::2], edges[1::2]):
        ax1.axvspan(t[a], t[b - 1], color=style.SOFT, lw=0, zorder=0)
    y_lo, y_hi = F[show].min(), F[show].max()
    ax1.set_ylim(y_lo - 0.35 * (y_hi - y_lo), y_hi + 0.05 * (y_hi - y_lo))
    i_lab = np.searchsorted(t, 78)
    ax1.text(78, level[i_lab] + 4, "threshold:\n1.3 × deepest dip",
             color=style.ACCENT_2, fontsize=7.5, ha="center", va="bottom")
    ax1.annotate("baseline", xy=(78, base[i_lab]), xytext=(78, y_lo - 0.27 * (y_hi - y_lo)),
                 color=style.INK, fontsize=7.5, ha="center", va="center",
                 arrowprops={"arrowstyle": "-", "color": style.INK, "lw": 0.6})
    ax1.text(52.5, y_hi, "kept: 1 s before, 2.05 s after",
             color=style.ACCENT, fontsize=7.5, va="top")
    ax1.set_yticks([])
    ax1.set_ylabel("raw F")

    ax2.plot(t[show], denoised[show], color=style.ACCENT, lw=0.9)
    for s, e in zip(starts, ends):
        if lo <= t[s] <= hi:
            ax2.axvspan(t[s], t[e], color=style.ACCENT_2, alpha=0.12, lw=0)
            ax2.plot(t[s], 0, "^", color=style.ACCENT_2, ms=5, clip_on=False)
    ax2.text(70, denoised[show].max(), "event = onset ▲ to end",
             color=style.ACCENT_2, fontsize=7.5, va="top")
    ax2.set_yticks([])
    ax2.set_ylabel("denoised F")
    ax2.set_xlim(lo, hi)
    ax2.set_xlabel("time (s)")
    return style.save(fig, "peak_detection")


def main() -> list[Path]:
    return [stim_detection_figure(), stim_windows_figure(), stim_networks_figure(),
            activity_type_figure(), peak_detection_figure()]


if __name__ == "__main__":
    for p in main():
        print(p)
