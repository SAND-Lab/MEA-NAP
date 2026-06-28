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
from typing import TYPE_CHECKING

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
) -> None:
    """
    Run the full denoising pipeline on one suite2p/plane0 directory and
    save outputs as .npy files alongside the inputs.

    Outputs written:
      Fdenoised.npy, timePoints.npy,
      peakStartFrames.npy, peakEndFrames.npy,
      peakHeights.npy, eventAreas.npy
    """
    d = Path(suite2p_dir)
    out_path = d / "Fdenoised.npy"

    if out_path.exists() and not overwrite:
        return

    F = np.load(d / "F.npy")          # (n_rois, n_frames)
    ops = np.load(d / "ops.npy", allow_pickle=True).item()
    fs = float(ops["fs"])

    n_cells, n_frames = F.shape
    time_points = np.arange(n_frames) / fs

    frames_before = int(time_before_peak_s * fs)
    frames_after = int(time_after_peak_s * fs)
    width = int(fs * denoising_width_sec)
    wlen = int(fs * denoising_wlen_sec)

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
            distance=50,
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

    np.save(d / "Fdenoised.npy", F_denoised_out)
    np.save(d / "timePoints.npy", time_points)
    np.save(d / "peakStartFrames.npy", _to_matrix(peak_lists))
    np.save(d / "peakEndFrames.npy", _to_matrix(end_lists))
    np.save(d / "peakHeights.npy", _to_matrix(height_lists))
    np.save(d / "eventAreas.npy", _to_matrix(area_lists))


def oasis_available() -> bool:
    return _OASIS_AVAILABLE
