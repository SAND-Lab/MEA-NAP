"""
Denoising pipeline for suite2p fluorescence traces.

Ported from Functions/twoPhoton/denoiseSuite2pData.py.

Requires:
  - pybaselines  (baseline estimation)
  - scipy        (signal processing, peak detection)
  - oasis        (OASIS deconvolution — optional; install from
                  https://github.com/j-friedrich/OASIS if needed)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import integrate, signal
from pybaselines.polynomial import imodpoly
from tqdm.auto import tqdm

try:
    from oasis.functions import deconvolve as oasis_deconvolve
    _OASIS_AVAILABLE = True
except ImportError:
    _OASIS_AVAILABLE = False


def _poly_baseline(trace: np.ndarray) -> np.ndarray:
    baseline, _ = imodpoly(trace, poly_order=3, num_std=0.7)
    return baseline


def _get_denoised_intensity(
    raw: np.ndarray,
    denoising_threshold: float = 1.3,
    frames_before_peak: int = 20,
    frames_after_peak: int = 41,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (delta_F, rel_intensity_filtered).
    Mirrors get_denoised_intensity() in the original Python script.
    """
    base = _poly_baseline(raw)
    F_denoised = base.copy()

    cond1 = (raw - base) <= 0
    cond2 = (raw - (base + denoising_threshold * abs(np.min(raw - base)))) > 0

    F_denoised = np.where(cond1, base, F_denoised)
    F_denoised = np.where(cond2, raw, F_denoised)

    preserved = base.copy()
    mismatch = np.where(F_denoised != base)[0]
    for idx in mismatch:
        s = max(0, idx - frames_before_peak)
        e = min(len(raw), idx + frames_after_peak)
        preserved[s:e] = raw[s:e]

    F_denoised = np.where(preserved != F_denoised, preserved, F_denoised)

    delta_F = F_denoised - base
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(base != 0, delta_F / base, 0.0)

    # zero out values below 0.05
    rel_filtered = np.where(rel < 0.05, 0.0, rel)
    preserved_rel = np.zeros_like(rel)
    mismatch2 = np.where(rel_filtered != preserved_rel)[0]
    for idx in mismatch2:
        s = max(0, idx - frames_before_peak)
        e = min(len(raw), idx + 51)
        preserved_rel[s:e] = rel[s:e]

    rel_filtered = np.where(preserved_rel != rel_filtered, preserved_rel, rel_filtered)
    return delta_F, rel_filtered


def _deconvolve_trace(rel_intensity: np.ndarray) -> np.ndarray:
    """
    Run OASIS deconvolution and return the denoised calcium trace (b + c).
    Falls back to Savitzky-Golay smoothing if OASIS is not installed.
    """
    if _OASIS_AVAILABLE:
        c, _s, b, _g, _lam = oasis_deconvolve(rel_intensity)
        return b + c
    else:
        # Savitzky-Golay as a reasonable fallback
        win = min(51, len(rel_intensity) // 4 * 2 + 1)  # must be odd
        if win < 5:
            return rel_intensity.copy()
        return signal.savgol_filter(rel_intensity, win, 3)


def process_suite2p_folder(
    suite2p_dir: str | Path,
    overwrite: bool = False,
    denoising_threshold: float = 1.3,
    time_before_peak_s: float = 1.0,
    time_after_peak_s: float = 2.05,
    denoising_width_sec: float = 1.13,
    denoising_wlen_sec: float = 12.0,
    min_event_interval_s: float | None = None,
    derived_root: str | Path | None = None,
    recording: str | None = None,
) -> Path:
    """
    Run the full denoising pipeline on one suite2p/plane0 directory.

    Outputs written:
      Fdenoised.npy, timePoints.npy,
      peakStartFrames.npy, peakEndFrames.npy,
      peakHeights.npy, eventAreas.npy

    They land beside the suite2p inputs by default — the historical behaviour —
    or under ``derived_root`` when one is given, which is what makes the raw
    data usable read-only or remote (see :mod:`meanap.catnap.derived`).
    Returns the directory written to.
    """
    from meanap.catnap.derived import resolve_read, resolve_write_dir

    d = Path(suite2p_dir)
    out_dir = resolve_write_dir(d, derived_root, recording) if recording else d
    out_path = out_dir / "Fdenoised.npy"

    # Honour outputs found anywhere we would read them from, not just where we
    # would write them: a dataset shipped with denoising already done must not
    # be redone just because a derived root is now configured.
    existing = (resolve_read(d, derived_root, recording, "Fdenoised.npy")
                if recording else (out_path if out_path.exists() else None))
    if existing is not None and not overwrite:
        return existing.parent

    F = np.load(d / "F.npy")          # (n_rois, n_frames)
    ops = np.load(d / "ops.npy", allow_pickle=True).item()
    fs = float(ops["fs"])

    n_cells, n_frames = F.shape
    time_points = np.arange(n_frames) / fs

    frames_before = int(time_before_peak_s * fs)
    frames_after = int(time_after_peak_s * fs)
    width = int(fs * denoising_width_sec)
    wlen = int(fs * denoising_wlen_sec)
    # 50 frames is the original script's hard-coded value. It is a *frame*
    # count, so the refractory period it imposes depends on the acquisition
    # rate; giving the interval in seconds makes it rate-independent. Default
    # stays on frames so existing runs (and the MATLAB parity test) are
    # unchanged — see Params.twop_min_event_interval.
    distance = 50 if min_event_interval_s is None else max(1, int(fs * min_event_interval_s))

    F_denoised_out = np.full_like(F, np.nan)
    max_peaks = 1  # will grow
    peak_lists: list[np.ndarray] = []
    end_lists: list[np.ndarray] = []
    height_lists: list[np.ndarray] = []
    area_lists: list[np.ndarray] = []

    for cell_id in tqdm(range(n_cells), desc="Denoising cells"):
        raw = F[cell_id]

        if np.all(np.diff(raw) == 0):
            rel = raw - np.mean(raw)
        else:
            _delta, rel = _get_denoised_intensity(
                raw,
                denoising_threshold=denoising_threshold,
                frames_before_peak=frames_before,
                frames_after_peak=frames_after,
            )

        denoised = _deconvolve_trace(rel)

        peaks, props = signal.find_peaks(
            denoised,
            height=0.0015,
            width=width,
            distance=distance,
            prominence=0.0015,
            rel_height=0.95,
            wlen=wlen,
        )

        starts = np.array([int(props["left_ips"][i]) for i in range(len(peaks))], dtype=float)
        ends = np.array([int(props["right_ips"][i]) for i in range(len(peaks))], dtype=float)
        heights = np.array([props["peak_heights"][i] for i in range(len(peaks))], dtype=float)
        areas = np.array(
            [integrate.trapezoid(denoised[int(s):int(e)]) for s, e in zip(starts, ends)],
            dtype=float,
        )

        peak_lists.append(starts)
        end_lists.append(ends)
        height_lists.append(heights)
        area_lists.append(areas)
        F_denoised_out[cell_id] = denoised
        max_peaks = max(max_peaks, len(starts))

    def _to_matrix(lists: list[np.ndarray]) -> np.ndarray:
        mat = np.full((n_cells, max_peaks), np.nan)
        for i, arr in enumerate(lists):
            mat[i, : len(arr)] = arr
        return mat

    np.save(out_dir / "Fdenoised.npy", F_denoised_out)
    np.save(out_dir / "timePoints.npy", time_points)
    np.save(out_dir / "peakStartFrames.npy", _to_matrix(peak_lists))
    np.save(out_dir / "peakEndFrames.npy", _to_matrix(end_lists))
    np.save(out_dir / "peakHeights.npy", _to_matrix(height_lists))
    np.save(out_dir / "eventAreas.npy", _to_matrix(area_lists))
    return out_dir


def oasis_available() -> bool:
    return _OASIS_AVAILABLE
