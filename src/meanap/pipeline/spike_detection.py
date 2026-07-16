"""MEA spike detection algorithms — Python port of MATLAB WATERS.

Implements threshold-based and wavelet CWT-based detection, matching the
behaviour of the MATLAB ``detectSpikesCWT`` / ``detectSpikesThreshold`` /
``detectSpikesWavelet`` functions in ``Functions/WATERS-master/``.

Both the threshold and the wavelet CWT paths are exact ports.

``_cwt_bior15`` reproduces MATLAB's legacy ``cwt(x, scales, 'bior1.5')``
algorithm literally (integrated wavelet, convolve, differentiate) rather than
approximating it, and agrees with MATLAB's own ``cwt`` to ~1e-15 relative on
real traces. PyWavelets' bior1.5 is *not* an approximation of MATLAB's: the
filters are identical and ``wavefun`` agrees to 1.6e-15 — see
``_get_bior15_intwave``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
import pywt
from scipy.signal import butter, filtfilt, find_peaks, oaconvolve

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

_BIOR15_INTWAVE_CACHE: tuple[np.ndarray, np.ndarray] | None = None


def _get_bior15_intwave() -> tuple[np.ndarray, np.ndarray]:
    """Return ``(int_psi, x)`` — the *integrated* bior1.5 decomposition wavelet.

    Port of MATLAB's ``intwave('bior1.5', 10)``, which is what its legacy
    ``cwt(x, scales, wname)`` convolves with: ``cumsum(psi_d) * step`` over
    ``wavefun``'s level-10 grid, where ``psi_d`` is the *decomposition* wavelet
    (``intwave.m`` takes ``wavefun``'s 2nd output for biorthogonal wavelets).

    PyWavelets' bior1.5 is not an approximation of MATLAB's — the two agree
    exactly: identical filters, identical ``wavefun`` grid, and ``psi_d`` equal
    to MATLAB's to 1.6e-15 (hence ``int_psi`` to 2.7e-16). ``level=10`` matters:
    it is ``intwave``'s default precision, and MATLAB's ``cwt`` relies on it.
    """
    global _BIOR15_INTWAVE_CACHE
    if _BIOR15_INTWAVE_CACHE is None:
        wav = pywt.Wavelet("bior1.5")
        _, psi_d, _, _, x = wav.wavefun(level=10)
        step = x[1] - x[0]
        _BIOR15_INTWAVE_CACHE = (np.cumsum(psi_d) * step, x)
    return _BIOR15_INTWAVE_CACHE


def _wkeep1_centre(x: np.ndarray, length: int) -> np.ndarray:
    """Port of MATLAB ``wkeep1(x, length)`` (central extraction, side=0)."""
    sx = len(x)
    if length >= sx:
        return x
    d = (sx - length) / 2.0
    return x[int(np.floor(d)):sx - int(np.ceil(d))]


def _cwt_bior15(signal: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """Compute CWT of ``signal`` at each scale using the bior1.5 wavelet.

    Literal port of MATLAB's legacy ``cwt(signal, scales, 'bior1.5')``, whose
    algorithm is (verified bit-identical against R2024b's ``cwt``)::

        [psi, xval] = intwave(wname, 10);  step = xval(2)-xval(1);
        j = 1 + floor((0:a*(xmax-xmin)) / (a*step));
        f = fliplr(psi(j));
        coefs = -sqrt(a) * wkeep1(diff(wconv1(signal, f)), len);

    i.e. convolve with the *reversed, integrated* wavelet sampled by index
    flooring, then differentiate — not a direct convolution with an
    interpolated ``psi``. The ``-sqrt(a)`` factor carries the sign, so the
    result needs no extra negation.

    Returns
    -------
    c : (n_scales, n_samples) array of CWT coefficients
    """
    int_psi, x = _get_bior15_intwave()
    step = x[1] - x[0]
    x_span = x[-1] - x[0]
    n = len(signal)
    sig = np.asarray(signal, dtype=float)

    coeffs = np.zeros((len(scales), n), dtype=float)
    for i, scale in enumerate(scales):
        a = float(scale)
        # MATLAB `0:a*(xmax-xmin)` -> 0,1,...,floor(a*span); the +1/-1 offsets
        # between the two index expressions are MATLAB's 1-based indexing.
        k = np.arange(0, np.floor(a * x_span) + 1)
        j = np.floor(k / (a * step)).astype(np.intp)
        if j.size == 1:
            j = np.zeros(2, dtype=np.intp)
        f = int_psi[j][::-1]
        # oaconvolve == MATLAB's conv(x, f, 'full') to float rounding, but is
        # O(n log m) rather than O(n*m) for these long traces / short filters.
        conv_full = oaconvolve(sig, f, mode="full")
        coeffs[i, :] = -np.sqrt(a) * _wkeep1_centre(np.diff(conv_full), n)

    return coeffs


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
            # MATLAB's IndZeroCross are 1-BASED indices and the >500 / <500
            # comparisons are against those, so use the same convention: a
            # crossing at 1-based index 501 belongs to IndMax, whereas testing
            # the 0-based index against 500 drops it from *both* bins. That
            # off-by-one silently corrupted the narrowest scale's width entry.
            zero_cross = np.where(ind_der == -1)[0] + 1
            max_cross = zero_cross[zero_cross > 500]
            min_cross = zero_cross[zero_cross < 500]
            if len(max_cross) == 0 or len(min_cross) == 0:
                continue
            width_table[i] = (max_cross.min() + 1 - min_cross.max()) * dt

        # MATLAB: WidthTable + [1:length(Scales)]*Eps
        Eps = 1e-15
        width_table = width_table + np.arange(1, len(scales_test) + 1) * Eps

        # Target widths
        width_target = np.linspace(wid_ms[0], wid_ms[1], ns)

        # MATLAB: Scale = round(interp1(WidthTable, Scales, Width, 'linear')).
        # interp1 returns NaN outside WidthTable's range; np.interp would
        # silently clamp, so ask for NaN and surface it instead of guessing.
        interp = np.interp(width_target, width_table, scales_test,
                           left=np.nan, right=np.nan)
        if np.isnan(interp).any():
            bad = width_target[np.isnan(interp)]
            raise ValueError(
                f"Wid {wid_ms} is not achievable at fs={fs_hz} Hz with {wname!r}: "
                f"target width(s) {bad} ms fall outside the wavelet's range "
                f"[{width_table.min():.3g}, {width_table.max():.3g}] ms"
            )
        # MATLAB's round() is half-away-from-zero; np.round is half-to-even.
        return np.floor(interp + 0.5).astype(int)
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
        # Take independent samples for MAD (W(i) apart).
        # MATLAB: median(abs(c(i,1:round(W(i)):end) - mean(c(i,:))))/0.6745 —
        # the subsampled coefficients are centred on the mean of the FULL row,
        # not on their own mean.
        stride = max(1, int(round(w_i)))
        c_sub = c[i, ::stride]
        Sigmaj = np.median(np.abs(c_sub - c[i, :].mean())) / 0.6745
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
    waveform_width: int = 25,
) -> tuple[np.ndarray, np.ndarray]:
    """Align spike frames to the negative peak within ±win frames.

    Port of MATLAB's ``alignPeaks()``, with one **deliberate** difference: this
    returns the true peak, MATLAB's returns the true peak + 1.

    MATLAB computes ``newSpikeTime = spikeTimes(i) + pos - win`` where ``pos``
    is a *1-based* index into the window, so a perfectly centred peak
    (``pos == win+1``) still shifts the spike by +1. MATLAB then reports the
    frame as ``spikeFrames/fs``, and those frames are 1-based too. Net effect:
    MATLAB's spike times sit 2 samples after the actual negative peak, and this
    port's sit exactly on it — so Python's times run a constant 2 samples
    (0.16 ms at 12.5 kHz) earlier than MATLAB's.

    That is intentional (decided 2026-07-15; same reasoning as the
    ``setUpSpreadSheet.m`` coordinate bug — the port does not replicate MATLAB
    off-by-ones). It changes no downstream metric, since a uniform shift leaves
    firing rates and STTC untouched. Add 2 samples to compare spike times with
    MATLAB's directly. See python/PIPELINE_PORT_STATUS.md.

    ``win`` is only the peak-search window; ``waveform_width`` is the *half*
    width of the extracted waveform (MATLAB ``alignPeaks.m``'s hard-coded
    ``waveform_width = 25``), so waveforms are ``2*waveform_width+1 = 51``
    samples wide — matching MATLAB's time scale rather than the coarse
    ``2*win+1`` window. Waveforms are used only for the ``3_Waveforms`` check
    plot, so this doesn't touch spike times/counts (and hence parity).

    Returns
    -------
    aligned_frames : 1-D int array
    waveforms : (n_spikes, 2*waveform_width+1) array of spike waveforms
    """
    wave_len = 2 * waveform_width + 1
    if len(spike_frames) == 0:
        return np.array([], dtype=int), np.zeros((0, wave_len))

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
        # Extract waveform over ±waveform_width around the peak, padding at the
        # recording edges so the peak stays centred and every waveform is the
        # same length (MATLAB drops edge spikes instead; they don't occur in the
        # validated data, so padding keeps spike counts identical either way).
        wlo = max(0, peak_frame - waveform_width)
        whi = min(n, peak_frame + waveform_width + 1)
        wave = trace[wlo:whi]
        left_pad = max(0, waveform_width - peak_frame)
        right_pad = max(0, wave_len - len(wave) - left_pad)
        if left_pad or right_pad:
            wave = np.pad(wave, (left_pad, right_pad))
        waves.append(wave)

    if not aligned:
        return np.array([], dtype=int), np.zeros((0, wave_len))

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
        _get_bior15_intwave()

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
