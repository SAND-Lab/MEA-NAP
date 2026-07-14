"""MEA spike detection algorithms — Python port of MATLAB WATERS.

Implements threshold-based and wavelet CWT-based detection, matching the
behaviour of the MATLAB ``detectSpikesCWT`` / ``detectSpikesThreshold`` /
``detectSpikesWavelet`` functions in ``Functions/WATERS-master/``.

Key differences from MATLAB
----------------------------
- Wavelet CWT uses a custom FFT-based implementation with the bior1.5 wavelet
  function obtained via PyWavelets' cascade algorithm.  Results should be
  highly similar but not bitwise identical to MATLAB's Wavelet Toolbox CWT.
- Threshold detection is an exact port and should give near-identical results.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
import pywt
from scipy.signal import butter, filtfilt, find_peaks

from meanap.pipeline.parallel import suggest_thread_count


# ── Bandpass filter ───────────────────────────────────────────────────────────

def bandpass_filter(trace: np.ndarray, fs: float, low: float = 600.0, high: float = 8000.0) -> np.ndarray:
    """3rd-order Butterworth bandpass filter, matching MATLAB's filtfilt."""
    wn = np.array([low, high]) / (fs / 2.0)
    wn = np.clip(wn, 1e-6, 1 - 1e-6)
    b, a = butter(3, wn, btype="bandpass")
    return filtfilt(b, a, trace.astype(float))


# ── Threshold detection ───────────────────────────────────────────────────────

def _apply_refractory(spike_frames: np.ndarray, ref_frames: int) -> np.ndarray:
    """Remove spikes that occur within ``ref_frames`` of a previous spike."""
    if len(spike_frames) == 0:
        return spike_frames
    kept = [spike_frames[0]]
    for f in spike_frames[1:]:
        if f - kept[-1] > ref_frames:
            kept.append(f)
    return np.array(kept, dtype=int)


def detect_spikes_threshold(
    trace: np.ndarray,
    multiplier: float,
    ref_period_ms: float,
    fs: float,
    filter_flag: bool = False,
    absolute_threshold: float | None = None,
    threshold_window: tuple[float, float] = (0.0, 1.0),
) -> tuple[np.ndarray, float]:
    """Threshold-based spike detection.

    Exact Python port of ``detectSpikesThreshold.m``.

    Parameters
    ----------
    trace : 1-D array — voltage trace (already filtered if ``filter_flag=False``)
    multiplier : threshold = median - multiplier * MAD / 0.6745
    ref_period_ms : refractory period in milliseconds
    fs : sampling frequency in Hz
    filter_flag : if True apply bandpass filter first
    absolute_threshold : if given, use this instead of the MAD threshold
    threshold_window : (start, end) as fractions of recording [0, 1]

    Returns
    -------
    spike_frames : 1-D int array of spike frame indices (0-based)
    threshold : the threshold value used
    """
    if filter_flag:
        trace = bandpass_filter(trace, fs)

    n = len(trace)
    if absolute_threshold is not None:
        threshold = float(absolute_threshold)
    else:
        t0 = int(round(n * threshold_window[0]))
        t1 = int(round(n * threshold_window[1]))
        subset = trace[t0:t1]
        s = np.median(np.abs(trace - np.mean(subset))) / 0.6745
        m = np.median(subset)
        threshold = m - multiplier * s

    # Threshold crossings (signal goes below threshold)
    spike_train = (trace < threshold).astype(float)

    # Apply refractory period
    ref_frames = int(round(ref_period_ms * 1e-3 * fs))
    spike_frames_raw = np.where(spike_train == 1)[0]

    if len(spike_frames_raw) == 0:
        return np.array([], dtype=int), threshold

    # Refractory: from each spike, zero-out the next ref_frames samples
    # (exact MATLAB loop logic)
    result = []
    i = 0
    while i < len(spike_frames_raw):
        f = spike_frames_raw[i]
        result.append(f)
        # Skip all frames within refractory window
        ref_end = f + ref_frames
        while i + 1 < len(spike_frames_raw) and spike_frames_raw[i + 1] <= ref_end:
            i += 1
        i += 1

    return np.array(result, dtype=int), threshold


# ── Wavelet CWT implementation ────────────────────────────────────────────────

_BIOR15_WAVEFN_CACHE: tuple[np.ndarray, np.ndarray] | None = None


def _get_bior15_wavefn() -> tuple[np.ndarray, np.ndarray]:
    """Return (psi, x) for the bior1.5 analysis (decomposition) wavelet (cached)."""
    global _BIOR15_WAVEFN_CACHE
    if _BIOR15_WAVEFN_CACHE is None:
        wav = pywt.Wavelet("bior1.5")
        phi_d, psi_d, phi_r, psi_r, x = wav.wavefun(level=8)
        x = x - x[0]
        _BIOR15_WAVEFN_CACHE = (psi_d, x)
    return _BIOR15_WAVEFN_CACHE


def _cwt_bior15(signal: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """Compute CWT of ``signal`` at each scale using bior1.5 wavelet.

    Replicates MATLAB ``cwt(signal, scales, 'bior1.5')`` via FFT convolution
    with the cascade-approximated wavelet function.

    Returns
    -------
    c : (n_scales, n_samples) array of CWT coefficients
    """
    psi_d, x = _get_bior15_wavefn()
    x_range = x[-1]
    n = len(signal)

    # Pad to next power-of-2 for faster FFT
    n_fft = int(2 ** np.ceil(np.log2(n)))
    sig_rfft = np.fft.rfft(signal.astype(float), n=n_fft)

    coeffs = np.zeros((len(scales), n), dtype=float)

    for i, scale in enumerate(scales):
        n_wvl = max(3, int(round(x_range * scale)))
        t_fine = np.linspace(0, x_range, n_wvl)
        psi_at_scale = np.interp(t_fine, x, psi_d) / np.sqrt(float(scale))

        psi_padded = np.zeros(n_fft)
        n_put = min(len(psi_at_scale), n_fft)
        psi_padded[:n_put] = psi_at_scale[:n_put]

        psi_rfft = np.fft.rfft(psi_padded)
        conv_full = np.fft.irfft(sig_rfft * psi_rfft, n=n_fft)
        shift = n_wvl // 2
        coeffs[i, :] = np.roll(conv_full[:n], -shift)

    # Negate: PyWavelets' bior1.5 psi_d has opposite sign to MATLAB's analysis wavelet.
    # After negation, negative voltage spikes (MEA action potentials) produce positive
    # CWT coefficients, matching MATLAB's convention (which keeps ct>0, zeros ct<0).
    return -coeffs


def _determine_scales(
    wname: str,
    wid_ms: tuple[float, float],
    fs_hz: float,
    ns: int,
) -> np.ndarray:
    """Determine CWT scales matching MATLAB's ``determine_scales()``.

    Returns integer scales for the desired spike-width range ``wid_ms``.
    """
    fs_khz = fs_hz / 1000.0
    dt = 1.0 / fs_khz           # ms per sample (of the actual signal)
    ScaleMax = int(4 * fs_khz)   # MATLAB: ScaleMax = 4*SFr
    scales_test = np.arange(2, ScaleMax + 1, dtype=float)

    # Test signal: 1000-sample Dirac at index 499 (MATLAB: index 500, 1-based)
    test_signal = np.zeros(1000)
    test_signal[499] = 1.0

    if wname in ("bior1.5", "bior1p5"):
        c = _cwt_bior15(test_signal, scales_test)

        width_table = np.zeros(len(scales_test))
        for i in range(len(scales_test)):
            ind_pos = (c[i, :] > 0).astype(int)
            ind_der = np.diff(ind_pos)
            zero_cross = np.where(ind_der == -1)[0]
            max_cross = zero_cross[zero_cross > 500]
            min_cross = zero_cross[zero_cross < 500]
            if len(max_cross) == 0 or len(min_cross) == 0:
                continue
            width_table[i] = (max_cross.min() + 1 - min_cross.max()) * dt

        Eps = 1e-15
        width_table = width_table + np.arange(len(scales_test)) * Eps

        # Target widths
        width_target = np.linspace(wid_ms[0], wid_ms[1], ns)

        # Find rows where width_table is positive and roughly monotone
        valid = width_table > 0
        if valid.sum() < 2:
            # Fallback: linearly spaced scales
            return np.linspace(int(ScaleMax * wid_ms[0] / wid_ms[1]),
                               ScaleMax, ns, dtype=int)

        wt_valid = width_table[valid]
        sc_valid = scales_test[valid]

        # Sort by width for interpolation (handles non-monotone regions)
        sort_idx = np.argsort(wt_valid)
        wt_sorted = wt_valid[sort_idx]
        sc_sorted = sc_valid[sort_idx]

        # Remove duplicates (keep first occurrence)
        _, unique_idx = np.unique(wt_sorted, return_index=True)
        wt_sorted = wt_sorted[unique_idx]
        sc_sorted = sc_sorted[unique_idx]

        Scale = np.round(np.interp(width_target, wt_sorted, sc_sorted)).astype(int)
        Scale = np.clip(Scale, 2, ScaleMax)
        return Scale
    else:
        raise ValueError(f"Unsupported wavelet for scale determination: {wname!r}")


# ── Wavelet spike detection ───────────────────────────────────────────────────

def _parse_spike_index(index: np.ndarray, fs_hz: float, wid_ms: tuple[float, float]) -> np.ndarray:
    """Convert binary spike-indicator vector to spike frame indices.

    Port of MATLAB's ``parse()`` inside ``detectSpikesWavelet.m``.
    Merges events closer than mean(Wid) and removes events closer than 0.1 ms.
    """
    Refract = max(1, round(0.1 * fs_hz / 1000.0))  # 0.1 ms refractory in frames
    Merge = max(1, round(np.mean(wid_ms) * fs_hz / 1000.0))  # merge window in frames

    index = index.copy()
    index[0] = 0
    index[-1] = 0

    ind_ones = np.where(index == 1)[0]
    if len(ind_ones) == 0:
        return np.array([], dtype=int)

    temp = np.diff(index)
    lead_t = np.where(temp == 1)[0]
    lag_t = np.where(temp == -1)[0]
    n_sp = len(lead_t)

    tE = []
    for i in range(n_sp):
        tE.append(int(np.ceil(np.mean([lead_t[i], lag_t[i]]))))

    tE = list(tE)
    i = 0
    while i < len(tE) - 1:
        diff = tE[i + 1] - tE[i]
        if Refract < diff <= Merge:
            del tE[i + 1]  # discard too-close spike
        elif diff <= Merge:
            tE[i] = int(np.ceil(np.mean([tE[i], tE[i + 1]])))
            del tE[i + 1]
        else:
            i += 1

    return np.array(tE, dtype=int)


def detect_spikes_wavelet(
    signal: np.ndarray,
    fs_hz: float,
    wid_ms: tuple[float, float] = (0.4, 0.8),
    ns: int = 5,
    option: str = "l",
    L: float = -0.12,
    wname: str = "bior1.5",
) -> np.ndarray:
    """Wavelet CWT spike detection.

    Port of MATLAB ``detectSpikesWavelet()``.  Signal should already be
    filtered (bandpass).

    Parameters
    ----------
    signal : 1-D array — filtered voltage trace (zero-mean)
    fs_hz : sampling frequency in Hz
    wid_ms : (min, max) expected spike width in milliseconds
    ns : number of CWT scales
    option : 'l' (liberal) or 'c' (conservative)
    L : Bayesian cost factor (typically -0.12)
    wname : wavelet name ('bior1.5' supported)

    Returns
    -------
    spike_frames : 1-D int array of spike frame indices (0-based)
    """
    signal = signal - signal.mean()
    Nt = len(signal)

    W = _determine_scales(wname, wid_ms, fs_hz, ns)

    c = _cwt_bior15(signal, W.astype(float))

    Lmax = 36.7368
    L_scaled = L * Lmax

    Io = np.zeros(Nt, dtype=bool)
    ct = np.zeros((ns, Nt), dtype=float)

    for i in range(ns):
        w_i = W[i]
        # Take independent samples for MAD (W(i) apart)
        stride = max(1, int(round(w_i)))
        c_sub = c[i, ::stride]
        Sigmaj = np.median(np.abs(c_sub - c_sub.mean())) / 0.6745
        if Sigmaj == 0:
            continue
        Thj = Sigmaj * np.sqrt(2 * np.log(Nt))     # hard threshold

        index = np.where(np.abs(c[i, :]) > Thj)[0]

        if len(index) == 0:
            if option == "c":
                pass  # do nothing
            else:  # "l"
                Mj = Thj
                PS = 1.0 / Nt
                PN = 1.0 - PS
                DTh = Mj / 2 + Sigmaj**2 / Mj * (L_scaled + np.log(PN / PS))
                DTh = abs(DTh) * (DTh >= 0)
                ind = np.where(np.abs(c[i, :]) > DTh)[0]
                if len(ind) > 0:
                    ct[i, ind] = c[i, ind]
        else:
            Mj = np.mean(np.abs(c[i, index]))
            PS = len(index) / Nt
            PN = 1.0 - PS
            DTh = Mj / 2 + Sigmaj**2 / Mj * (L_scaled + np.log(PN / PS))
            DTh = abs(DTh) * (DTh >= 0)
            ind = np.where(np.abs(c[i, :]) > DTh)[0]
            if len(ind) > 0:
                ct[i, ind] = c[i, ind]

        # Delete negative coefficients (MATLAB: ct(ct<0)=0)
        ct[i, ct[i, :] < 0] = 0
        Index_i = ct[i, :] != 0
        Io = Io | Index_i

    return _parse_spike_index(Io.astype(int), fs_hz, wid_ms)


# ── Peak alignment ────────────────────────────────────────────────────────────

def align_peaks(
    spike_frames: np.ndarray,
    trace: np.ndarray,
    win: int = 10,
    min_peak_thr_mult: float = -5.0,
    max_peak_thr_mult: float = -100.0,
    pos_peak_thr_mult: float = 15.0,
    remove_artifacts: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Align spike frames to the negative peak within ±win frames.

    Approximate port of MATLAB's ``alignPeaks()``.

    Returns
    -------
    aligned_frames : 1-D int array
    waveforms : (n_spikes, 2*win+1) array of spike waveforms
    """
    if len(spike_frames) == 0:
        return np.array([], dtype=int), np.zeros((0, 2 * win + 1))

    n = len(trace)
    aligned = []
    waves = []

    s = np.median(np.abs(trace - np.mean(trace))) / 0.6745
    thr_min = min_peak_thr_mult * s
    thr_max = max_peak_thr_mult * s
    thr_pos = pos_peak_thr_mult * s

    for f in spike_frames:
        lo = max(0, f - win)
        hi = min(n, f + win + 1)
        segment = trace[lo:hi]
        peak_offset = int(np.argmin(segment))
        peak_frame = lo + peak_offset
        peak_val = trace[peak_frame]

        if remove_artifacts:
            if peak_val > thr_min or peak_val < thr_max:
                continue
            pos_peak = trace[lo:hi].max()
            if pos_peak > thr_pos:
                continue

        aligned.append(peak_frame)
        # Extract waveform
        wlo = max(0, peak_frame - win)
        whi = min(n, peak_frame + win + 1)
        wave = trace[wlo:whi]
        if len(wave) < 2 * win + 1:
            wave = np.pad(wave, (0, 2 * win + 1 - len(wave)))
        waves.append(wave)

    if not aligned:
        return np.array([], dtype=int), np.zeros((0, 2 * win + 1))

    return np.array(aligned, dtype=int), np.vstack(waves)


# ── High-level detector ───────────────────────────────────────────────────────

@dataclass
class SpikeDetectionParams:
    """Parameters matching the MATLAB Params struct for spike detection."""
    fs: float = 12500.0
    thresholds: list[float] = field(default_factory=lambda: [4.0, 5.0])
    wname_list: list[str] = field(default_factory=lambda: ["bior1.5"])
    cost_list: list[float] = field(default_factory=lambda: [-0.12])
    spikes_method: str = "bior1p5"
    wid_ms: tuple[float, float] = (0.4, 0.8)
    n_scales: int = 5
    filter_low_pass: float = 600.0
    filter_high_pass: float = 6150.0
    ref_period_ms: float = 1.0
    n_spikes: int = 10000
    min_peak_thr_mult: float = -5.0
    max_peak_thr_mult: float = -100.0
    pos_peak_thr_mult: float = 15.0
    remove_artifacts: bool = False
    unit: str = "s"   # 's', 'ms', or 'frames'
    grd: list[int] = field(default_factory=list)  # grounded channels (0-based)


class SpikeDetectionResult(NamedTuple):
    """Results for a single recording."""
    spike_times: dict[int, dict[str, np.ndarray]]  # ch_idx → {method: times}
    spike_waveforms: dict[int, dict[str, np.ndarray]]  # ch_idx → {method: (n_sp, n_pts)}
    thresholds: dict[int, dict[str, float]]           # ch_idx → {method: threshold}
    channels: np.ndarray
    fs: float


def detect_spikes_recording(
    dat: np.ndarray,
    channels: np.ndarray,
    fs: float,
    params: SpikeDetectionParams | None = None,
    max_workers: int | None = None,
) -> SpikeDetectionResult:
    """Run spike detection on all channels of a single recording.

    Parameters
    ----------
    dat : (n_samples, n_channels) array
    channels : (n_channels,) channel ID array
    fs : sampling frequency in Hz
    params : detection parameters (defaults match the example data MATLAB run)

    Returns
    -------
    SpikeDetectionResult
    """
    if params is None:
        params = SpikeDetectionParams(fs=fs)

    n_channels = len(channels)
    spike_times: dict[int, dict[str, np.ndarray]] = {}
    spike_waveforms: dict[int, dict[str, np.ndarray]] = {}
    thresholds_out: dict[int, dict[str, float]] = {}

    # Build full method list: wavelets + thresholds (as in MATLAB)
    # Threshold names match MATLAB: integer threshold → "thr4", fractional → "thr4p5"
    def _thr_name(t: float) -> str:
        return f"thr{int(t)}" if t == int(t) else f"thr{t}".replace(".", "p")

    wname_list = [w for w in params.wname_list if w != "None"]
    thr_list = [_thr_name(t) for t in params.thresholds]
    all_methods = wname_list + thr_list

    # Pre-cache wavelet function before the channel loop so it's not recomputed
    if any(not w.startswith("thr") for w in all_methods):
        _get_bior15_wavefn()

    # Per-channel work is independent and dominated by GIL-releasing
    # scipy.filtfilt + numpy.fft, so it threads cleanly over the (single,
    # shared) ~3.8 GB `dat` array without duplicating it — the RAM-safe way
    # to parallelize Step 1 (see pipeline/parallel.py). Column slices of a
    # NumPy array are read-only-shared across threads; each channel writes
    # only its own result dict entry, so no locking is needed.
    def _process_channel(ch_idx: int):
        if ch_idx in params.grd:
            return None

        raw_trace = dat[:, ch_idx].astype(float)
        filtered = bandpass_filter(raw_trace, fs, params.filter_low_pass, params.filter_high_pass)

        spike_struct: dict[str, np.ndarray] = {}
        wave_struct: dict[str, np.ndarray] = {}
        thr_struct: dict[str, float] = {}

        for wname in all_methods:
            valid_name = wname.replace(".", "p")

            if wname.startswith("thr"):
                # Threshold method
                mult_str = wname[3:].replace("p", ".")
                mult = float(mult_str)
                frames, thr = detect_spikes_threshold(
                    filtered, mult, params.ref_period_ms, fs,
                    filter_flag=False,
                )
                thr_struct[valid_name] = thr

            else:
                # Wavelet method
                actual_wname = wname.replace("p", ".")
                frames = detect_spikes_wavelet(
                    filtered, fs,
                    wid_ms=params.wid_ms,
                    ns=params.n_scales,
                    option="l",
                    L=params.cost_list[0],
                    wname=actual_wname,
                )
                thr_struct[valid_name] = float("nan")

            aligned_frames, waveforms = align_peaks(
                frames, filtered, win=10,
                min_peak_thr_mult=params.min_peak_thr_mult,
                max_peak_thr_mult=params.max_peak_thr_mult,
                pos_peak_thr_mult=params.pos_peak_thr_mult,
                remove_artifacts=params.remove_artifacts,
            )

            # Convert frames to the requested unit
            if params.unit == "s":
                times = aligned_frames / fs
            elif params.unit == "ms":
                times = aligned_frames / (fs / 1000.0)
            else:
                times = aligned_frames.astype(float)

            spike_struct[valid_name] = times
            wave_struct[valid_name] = waveforms

        return ch_idx, spike_struct, wave_struct, thr_struct

    n_threads = suggest_thread_count(n_channels, max_workers=max_workers)
    if n_threads <= 1:
        results = (_process_channel(ch) for ch in range(n_channels))
    else:
        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            results = pool.map(_process_channel, range(n_channels))

    for res in results:
        if res is None:
            continue
        ch_idx, spike_struct, wave_struct, thr_struct = res
        spike_times[ch_idx] = spike_struct
        spike_waveforms[ch_idx] = wave_struct
        thresholds_out[ch_idx] = thr_struct

    return SpikeDetectionResult(
        spike_times=spike_times,
        spike_waveforms=spike_waveforms,
        thresholds=thresholds_out,
        channels=channels,
        fs=fs,
    )
