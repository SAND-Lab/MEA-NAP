"""Step-1 spike-detection check figures, and the small payload they draw from.

These three figures are the only quality-control record of what spike detection
actually did, and they are the ones a bundle could not rebuild: they are drawn
from the raw voltage, which is gigabytes and deliberately never travels.

But almost none of that voltage is *visible*. The example-trace panels plot the
whole filtered trace and then set the x-limits to a ±30 ms window around one
spike; the waveform panel draws snippets from a single channel; the frequency
panel needs nothing but spike times. So the figures are separated here into
what they *show* — :class:`SpikeCheckData`, tens of kilobytes — and the drawing
that turns it into pictures. Step 1 saves the payload alongside the spike times;
a bundle carries it instead of the PNGs, which cost roughly twenty times more.

Compute and draw are split rather than duplicated so the two cannot drift: the
figure the pipeline writes and the figure a viewer rebuilds come out of the same
function, from the same numbers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from meanap.params import Params
from meanap.pipeline.parallel import compute_threads
from meanap.pipeline.rng import make_rng
from meanap.pipeline.spike_detection import SpikeDetectionResult, bandpass_filter
from meanap.pipeline.atomic import atomic_savez

__all__ = [
    "SpikeCheckData",
    "SPIKE_CHECK_FIGURES",
    "CHECKS_SUFFIX",
    "compute_spike_check_data",
    "draw_spike_check_figures",
    "plot_spike_detection_checks",
    "save_spike_check_data",
    "load_spike_check_data",
]

#: The three figures, by the base filename each is written under.
SPIKE_CHECK_FIGURES = ("1_ExampleTraces", "2_SpikeFrequencies", "3_Waveforms")

#: Written beside ``<rec>_spikes.npz``. In *1A* (data) rather than *1B*
#: (figures) so a bundle can drop the whole figure folder and keep this.
CHECKS_SUFFIX = "_step1checks.npz"

#: How many example-trace panels the figure has (a 5×2 grid, last one blank).
N_TRACE_PANELS = 9

#: Half-width of the example-trace window, in seconds.
TRACE_WINDOW_S = 30 / 1000

#: Cap on waveforms drawn per method — and therefore on waveforms stored. The
#: panel draws a grey cloud whose density stops reading above this anyway.
MAX_WAVEFORMS = 1000


@dataclass
class SpikeCheckData:
    """Everything the step-1 check figures draw, and nothing else.

    Voltages are stored already filtered and already scaled to µV, because that
    is what is plotted. A bundle therefore cannot re-filter them under different
    bandpass settings — deliberately: these figures are a record of what this
    run did, not a workbench for trying other settings on.
    """

    rec_name: str
    fs: float
    methods: list[str]

    # ── 2_SpikeFrequencies ───────────────────────────────────────────────────
    #: (n_methods, n_bins) — channel-mean spikes per bin, already reduced.
    freq_curves: np.ndarray
    duration_s: float

    # ── 1_ExampleTraces ──────────────────────────────────────────────────────
    trace_channels: np.ndarray          # (n_panels,) channel index per panel
    trace_windows: np.ndarray           # (n_panels, win) filtered µV
    trace_starts: np.ndarray            # (n_panels,) first frame of each window
    #: (n_panels, 2) the frame range each panel *shows*. One sample narrower at
    #: each end than the stored window: the original drew the whole trace and
    #: clipped it, so a segment entered the axes from off-screen at each edge.
    #: Keeping that overhang is what makes a rebuilt panel pixel-identical.
    trace_views: np.ndarray
    #: Std of each panel's *whole* trace, not of its window — the y-limits are
    #: scaled to the recording's noise, and a 60 ms slice would not give that.
    trace_stds: np.ndarray
    #: ``[panel][method] -> frames``, absolute, already clipped to the window.
    trace_spike_frames: list[list[np.ndarray]]

    # ── 3_Waveforms ──────────────────────────────────────────────────────────
    wave_channel: int
    wave_std: float
    waveforms: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def n_panels(self) -> int:
        return len(self.trace_channels)


# ── Compute ───────────────────────────────────────────────────────────────────

def compute_spike_check_data(
    dat: np.ndarray,
    result: SpikeDetectionResult,
    params: Params,
    rec_name: str,
) -> SpikeCheckData:
    """Reduce a recording to just what its three check figures show.

    The random choices — which channels appear as example traces, which spike
    each window centres on — are made here and then *stored*, so a rebuilt
    figure shows the same panels as the one the run wrote rather than a fresh
    draw from the same seed.
    """
    rng = make_rng(params.random_seed, "step1-plots", rec_name)

    fs = result.fs
    n_samples, n_channels = dat.shape
    scale_factor = _scale_factor(params)
    active_channels = list(result.spike_times.keys())
    # A recording where detection found nothing on any channel has no methods
    # to name either. Handled rather than left to raise from next(iter(...)):
    # step 1 now always builds this, so a dead recording would take the run
    # down instead of just producing an empty check figure.
    methods = (sorted(next(iter(result.spike_times.values())).keys())
               if active_channels else [])

    freq_curves = _frequency_curves(result, methods, params, n_samples, n_channels)

    # Filtering is the expensive part, so each channel is filtered once and
    # reused for both its window and (if it is the last one) its waveforms.
    def filtered(ch: int) -> np.ndarray:
        return bandpass_filter(dat[:, ch].astype(float), fs,
                               params.filter_low_pass,
                               params.filter_high_pass) * scale_factor

    window_frames = int(round(TRACE_WINDOW_S * fs))
    channels: list[int] = []
    windows: list[np.ndarray] = []
    starts: list[int] = []
    views: list[tuple[int, int]] = []
    stds: list[float] = []
    frames_per_panel: list[list[np.ndarray]] = []

    last_channel = active_channels[0] if active_channels else 0

    # Every draw depends on spike times only, never on a filtered trace, so
    # they are all made first, in the order they always were, and the
    # channels are then filtered on threads (filtfilt releases the GIL).
    panels: list[tuple[int, int, int, int, int]] = []
    for _ in range(N_TRACE_PANELS if active_channels else 0):
        ch = int(rng.choice(active_channels))
        times_s = result.spike_times[ch].get(methods[0], np.array([]))
        centre = (int(round(rng.choice(times_s) * fs)) if len(times_s)
                  else n_samples // 2)
        start_f = max(0, centre - window_frames)
        end_f = min(n_samples, centre + window_frames)
        # One sample of overhang each side — see SpikeCheckData.trace_views.
        cut_from = max(0, start_f - 1)
        cut_to = min(n_samples, end_f + 1)
        panels.append((ch, start_f, end_f, cut_from, cut_to))

    def summarise(ch: int) -> tuple[float, list[np.ndarray]]:
        """The trace's std and its window for every panel showing it."""
        trace = filtered(ch)
        return float(np.std(trace)), [
            trace[cut_from:cut_to].astype(np.float32)
            for c, _, _, cut_from, cut_to in panels if c == ch]

    unique_channels = list(dict.fromkeys(p[0] for p in panels))
    with ThreadPoolExecutor(max_workers=max(1, min(len(unique_channels),
                                                   compute_threads()))) as pool:
        summaries = dict(zip(unique_channels,
                             pool.map(summarise, unique_channels)))
    next_window = {ch: iter(summaries[ch][1]) for ch in unique_channels}

    for ch, start_f, end_f, cut_from, _ in panels:
        last_channel = ch
        channels.append(ch)
        windows.append(next(next_window[ch]))
        starts.append(cut_from)
        views.append((start_f, end_f))
        stds.append(summaries[ch][0])
        frames_per_panel.append([
            _frames_in_window(result.spike_times[ch].get(m, np.array([])),
                              fs, start_f, end_f)
            for m in methods
        ])

    waveforms = {}
    for method in methods:
        waves = result.spike_waveforms.get(last_channel, {}).get(
            method, np.zeros((0, 0)))
        if waves.shape[0] > MAX_WAVEFORMS:
            waves = waves[np.linspace(0, waves.shape[0] - 1,
                                      MAX_WAVEFORMS).astype(int)]
        # MATLAB scales the trace by 1e6 and then scales the snippets cut from
        # it by 1e6 again. The double scaling is preserved so these panels match
        # the MATLAB reference; applying it here keeps the stored waveforms in
        # the units the drawing expects.
        waveforms[method] = np.asarray(waves, dtype=np.float32) * scale_factor

    return SpikeCheckData(
        rec_name=rec_name,
        fs=float(fs),
        methods=methods,
        freq_curves=freq_curves,
        duration_s=n_samples / fs,
        trace_channels=np.asarray(channels, dtype=np.int32),
        trace_windows=(np.stack(windows) if windows
                       else np.zeros((0, 0), dtype=np.float32)),
        trace_starts=np.asarray(starts, dtype=np.int64),
        trace_views=(np.asarray(views, dtype=np.int64) if views
                     else np.zeros((0, 2), dtype=np.int64)),
        trace_stds=np.asarray(stds, dtype=np.float64),
        trace_spike_frames=frames_per_panel,
        wave_channel=int(last_channel),
        # The waveform channel is the last panel's, whose std is already known.
        wave_std=stds[-1] if stds else 0.0,
        waveforms=waveforms,
    )


def _scale_factor(params: Params) -> float:
    if params.potential_difference_unit == "V":
        return 1e6
    if params.potential_difference_unit == "mV":
        return 1e3
    return 1.0


def _frames_in_window(times_s, fs: float, start_f: int, end_f: int) -> np.ndarray:
    frames = np.round(np.asarray(times_s) * fs).astype(np.int64)
    return frames[(frames >= start_f) & (frames <= end_f)]


def _frequency_curves(
    result: SpikeDetectionResult, methods: list[str], params: Params,
    n_samples: int, n_channels: int,
) -> np.ndarray:
    """Channel-mean spike count per ``d_samp_f`` bin, one row per method.

    Reduced here rather than at draw time: the curve is a few hundred floats,
    while rebuilding it needs a full-length spike vector per channel.
    """
    d_samp_f = int(params.d_samp_f)
    n_bins = int(np.ceil(n_samples / d_samp_f))
    active_channels = list(result.spike_times.keys())
    curves = np.zeros((len(methods), n_bins))

    for i, method in enumerate(methods):
        spk_matrix = np.zeros((n_channels, n_bins))
        for ch_idx in active_channels:
            times_s = result.spike_times[ch_idx].get(method, np.array([]))
            frames = np.round(times_s * result.fs).astype(int)
            frames = frames[frames < n_samples]

            # Spikes per bin, each sample counted once however many spikes
            # land on it: what marking a full-length 0/1 vector and summing it
            # per bin gave, without building millions of samples per channel
            # per method. The modulo keeps that indexing's wrap-around for a
            # negative frame.
            occupied = np.unique(frames % n_samples)
            spk_matrix[ch_idx, :] = np.bincount(occupied // d_samp_f,
                                                minlength=n_bins)

        if active_channels:
            curves[i] = np.mean(spk_matrix[active_channels, :], axis=0)
    return curves


# ── Persistence ───────────────────────────────────────────────────────────────

def save_spike_check_data(path: Path | str, data: SpikeCheckData) -> Path:
    """Write the payload as an ``.npz``.

    Ragged pieces — the per-panel, per-method spike frames — are flattened with
    an offset index rather than saved as an object array, so the file loads
    without ``allow_pickle``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    flat: list[np.ndarray] = []
    offsets = [0]
    for panel in data.trace_spike_frames:
        for frames in panel:
            flat.append(np.asarray(frames, dtype=np.int64))
            offsets.append(offsets[-1] + len(frames))

    arrays = {
        "rec_name": np.array([data.rec_name]),
        "fs": np.array([data.fs]),
        "methods": np.array(data.methods),
        "freq_curves": data.freq_curves,
        "duration_s": np.array([data.duration_s]),
        "trace_channels": data.trace_channels,
        "trace_windows": data.trace_windows,
        "trace_starts": data.trace_starts,
        "trace_views": data.trace_views,
        "trace_stds": data.trace_stds,
        "spike_frames_flat": (np.concatenate(flat) if flat
                              else np.zeros(0, dtype=np.int64)),
        "spike_frames_offsets": np.asarray(offsets, dtype=np.int64),
        "wave_channel": np.array([data.wave_channel]),
        "wave_std": np.array([data.wave_std]),
    }
    for method, waves in data.waveforms.items():
        arrays[f"waveforms_{method}"] = waves

    atomic_savez(path, compressed=True, **arrays)
    return path


def load_spike_check_data(path: Path | str) -> SpikeCheckData:
    """Read back what :func:`save_spike_check_data` wrote."""
    with np.load(path) as z:
        methods = [str(m) for m in z["methods"]]
        offsets = z["spike_frames_offsets"]
        flat = z["spike_frames_flat"]

        n_panels = len(z["trace_channels"])
        frames_per_panel: list[list[np.ndarray]] = []
        k = 0
        for _ in range(n_panels):
            panel = []
            for _ in methods:
                panel.append(flat[offsets[k]:offsets[k + 1]])
                k += 1
            frames_per_panel.append(panel)

        return SpikeCheckData(
            rec_name=str(z["rec_name"][0]),
            fs=float(z["fs"][0]),
            methods=methods,
            freq_curves=z["freq_curves"],
            duration_s=float(z["duration_s"][0]),
            trace_channels=z["trace_channels"],
            trace_windows=z["trace_windows"],
            trace_starts=z["trace_starts"],
            trace_views=z["trace_views"],
            trace_stds=z["trace_stds"],
            trace_spike_frames=frames_per_panel,
            wave_channel=int(z["wave_channel"][0]),
            wave_std=float(z["wave_std"][0]),
            waveforms={m: z[f"waveforms_{m}"] for m in methods
                       if f"waveforms_{m}" in z.files},
        )


# ── Draw ──────────────────────────────────────────────────────────────────────

def draw_spike_check_figures(
    data: SpikeCheckData,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    only: str | None = None,
) -> list[Path]:
    """Draw the check figures from *data*, returning the paths written.

    ``fmt`` and ``only`` are the two hooks the bundle viewer needs — one figure
    per request, optionally as vector — and default to the pipeline's behaviour.
    """
    from meanap.native import output
    from meanap.native.spike_check_paint import (
        FrequenciesPainter, TracesPainter, WaveformsPainter,
    )

    out_dir = Path(out_dir)
    written: list[Path] = []
    # Drawn by Qt (meanap.native): the file is the figure the viewer shows.
    figures = [("2_SpikeFrequencies", FrequenciesPainter, True),
               ("1_ExampleTraces", TracesPainter, bool(data.n_panels)),
               ("3_Waveforms", WaveformsPainter, bool(data.n_panels))]
    for name, painter_type, available in figures:
        if not available or (only is not None and Path(only).stem != name):
            continue
        path = out_dir / f"{name}.{fmt}"
        painter = painter_type(data)
        output.save(painter, path, capture=output.NativeFigure("spike_check", data, painter))
        written.append(path)
    return written


def plot_spike_detection_checks(
    dat: np.ndarray,
    result: SpikeDetectionResult,
    params: Params,
    rec_name: str,
    out_dir: Path,
) -> None:
    """Compute and draw in one call — the pipeline's original entry point."""
    draw_spike_check_figures(
        compute_spike_check_data(dat, result, params, rec_name), out_dir)
