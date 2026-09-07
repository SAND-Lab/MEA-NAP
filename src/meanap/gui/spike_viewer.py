"""Look at the spikes and bursts before trusting them.

Spike detection is the one step whose output the rest of the pipeline cannot
sanity-check for you: every firing rate, every correlation and every network
metric downstream is computed from whatever came out of it, and a threshold set
one MAD too low turns noise into a well-connected network. The same is true a
level up — a network burst is only as real as the ISI\\ :sub:`N` threshold that
declared it.

This window is where you look. It loads a recording's raw traces and its
spikes — detected here, or read back from a finished run — and shows them
together three ways:

* **Traces** — the filtered voltage with every detected spike marked and the
  method's threshold drawn across it. The question "is that a spike?" is
  answered by looking at it, and nothing else in MEA-NAP lets you.
* **Waveforms** — the spikes overlaid on their mean, their amplitudes against
  the threshold that caught them, and the ISI histogram against the refractory
  period. Refractory violations are the cheapest lie-detector for a threshold
  set too low; the array map beside them says whether one channel is carrying
  the whole recording.
* **Bursts** — the array raster with network bursts shaded and one channel's
  own bursts below it, so single-channel and network detection are judged
  against the same spikes at the same time.

Detection parameters are editable here and re-run on the loaded recording — on
one channel while you are hunting for the right threshold, on all of them once
you have it. **Use these settings** hands them back to the Spike detection tab;
nothing here writes to disk, so a recording's detected files are exactly as the
pipeline left them however long you spend in this window.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QScrollBar, QSizePolicy, QSpinBox, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import (
    QBrush, QColor, QFontMetrics, QIcon, QLinearGradient, QPainter, QPen,
    QPixmap,
)
import pyqtgraph as pg
from matplotlib import colormaps
from matplotlib.lines import Line2D
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from pyqtgraph import exporters as pg_exporters
from scipy.signal import welch

from meanap.gui.advanced import AdvancedSection
from meanap.gui.widgets import pin_width, scrollable, show_auto_or_value
from meanap.params import Params
from meanap.pipeline.burst_detection import (
    burst_detect_network, single_channel_burst_detection,
)
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.io import (
    SpikeFile, find_raw_file, load_raw_recording, load_spike_file,
    save_spike_times_npz,
)
from meanap.pipeline.spike_detection import (
    SpikeDetectionParams, bandpass_filter, detect_spikes_recording,
    threshold_method_name,
)

__all__ = ["UNLABELLED_METHOD", "SpikeViewerWindow", "SweepPoint",
           "count_slopes", "knee_threshold", "noise_from_thresholds",
           "pack_bursts", "quality_summary", "refractory_violations",
           "sweep_points", "unpack_bursts"]

_LAYOUTS = ["MCS60", "MCS60old", "MCS59", "Axion64", "Axion16"]
_WAVELETS = ["bior1.5", "bior1.3", "db2", "mea"]
#: Points drawn for one window of a matplotlib trace — the Filtering tab's
#: before/after pair. Above this, a screen-width axes has more samples than
#: pixels and the extra ones cost redraw time to show nothing; but spikes are
#: ~1 ms events, so decimating too hard hides the very thing this window exists
#: to show, hence the peak-preserving :func:`_decimate` rather than strides.
#: (The Traces tab is pyqtgraph, which does the same thing for itself.)
_MAX_TRACE_POINTS = 8000
#: Spikes drawn in the array raster before it starts subsampling. A 60-channel
#: 10-minute recording can hold a million; the raster's job is showing where
#: the bursts are, and it does that identically from a tenth of them.
_MAX_RASTER_SPIKES = 120_000

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "#222222")
# Off for the traces, which carry millions of points; the items that want it
# ask for it themselves.
pg.setConfigOption("antialias", False)
_SPIKE_COLOR = "#d62728"
_RAW_COLOR = "#6e7f8f"
#: One colour per detection method, in the order the methods appear. These are
#: MATLAB's ``Params.spikeMethodColors`` (see ``runPipelineApp.m``), so a
#: method is the same colour here as in the pipeline's own spike-detection
#: check figures — the two are read side by side.
SPIKE_METHOD_COLORS = [
    "#0072bd", "#d95319", "#edb120", "#7e2f8e",
    "#77ac30", "#4dbeee", "#a2142f",
]


def method_color(index: int) -> str:
    """The colour for the *index*-th method, cycling if there are many."""
    return SPIKE_METHOD_COLORS[index % len(SPIKE_METHOD_COLORS)]
_BURST_COLOR = "#f2a900"
_TRACE_COLOR = "#2b3a4a"
#: How much of the recording "next spike" and "next burst" zoom to when the
#: whole thing is on screen — which it is when a recording is first opened. A
#: second holds a spike and enough either side to judge it; twenty seconds holds
#: a network burst and its neighbours. Capped at a quarter of the recording, so
#: that on a short one the button still visibly moves rather than asking for
#: more seconds than there are and leaving the view where it was.
#: Pixels the array map reserves for its caption and its colour scale.
_MAP_CAPTION_PX = 18
_MAP_SCALE_PX = 26
_MAP_MARGIN = 8.0
#: The firing rate a channel must reach to count as active in a sweep — the
#: pipeline's own ``min_activity_level`` default, so "active channels" here
#: means what it means in the results.
_MIN_ACTIVE_RATE = 0.01
_INSPECT_SPIKE_S = 1.0
_INSPECT_BURST_S = 20.0


def _inspect_window(preferred: float, duration: float) -> float:
    return max(min(preferred, duration / 4), 1e-3)


# ── Quality measures ──────────────────────────────────────────────────────────

def refractory_violations(spike_times: np.ndarray, ref_period_ms: float) -> tuple[int, float]:
    """How many consecutive spikes fall inside the refractory period.

    Returns ``(count, fraction)``. One neuron cannot fire twice inside its own
    refractory period, so on a single electrode a high fraction means the
    threshold is catching noise, catching one spike twice, or both — it is the
    cheapest evidence that a detection is too permissive. Fewer than two spikes
    is no evidence either way, and reports zero.
    """
    times = np.sort(np.asarray(spike_times, dtype=float).ravel())
    if times.size < 2:
        return 0, 0.0
    isis_ms = np.diff(times) * 1000.0
    count = int(np.count_nonzero(isis_ms < ref_period_ms))
    return count, count / isis_ms.size


def quality_summary(
    spike_times: np.ndarray,
    waveforms: np.ndarray | None,
    threshold: float,
    duration_s: float,
    ref_period_ms: float,
    noise_mad: float | None = None,
) -> str:
    """One line of numbers for the channel and method now on screen.

    Kept out of the window class so a test can check the numbers without a
    screen, and so the wording lives next to the definitions above it.
    """
    n = int(np.asarray(spike_times).size)
    rate = n / duration_s if duration_s > 0 else float("nan")
    parts = [f"{n} spikes", f"{rate:.2f} Hz"]

    violations, fraction = refractory_violations(spike_times, ref_period_ms)
    if n >= 2:
        parts.append(f"{fraction * 100:.1f}% ISIs < {ref_period_ms:g} ms "
                     f"({violations})")

    if waveforms is not None and getattr(waveforms, "size", 0):
        amplitudes = np.min(np.asarray(waveforms, dtype=float), axis=1)
        parts.append(f"median amplitude {np.median(amplitudes):.3g}")
        if noise_mad:
            parts.append(f"SNR {abs(np.median(amplitudes)) / noise_mad:.1f}")
    if threshold is not None and np.isfinite(threshold):
        parts.append(f"threshold {threshold:.3g}")
    return " · ".join(parts)


def _fit_title(head: str, summary: str, width: int = 74) -> str:
    """``head`` on its own line, then *summary* wrapped to *width* characters.

    A one-line title of channel, method and six numbers is wider than the axes
    under it at any figure size that fits a laptop, and matplotlib clips rather
    than wraps — so the last measure, whichever it happened to be, was the one
    nobody could read.
    """
    lines, current = [head], ""
    for part in summary.split(" · "):
        candidate = f"{current} · {part}" if current else part
        if len(candidate) > width and current:
            lines.append(current)
            current = part
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _noise_mad(trace: np.ndarray) -> float:
    """The MAD-based noise estimate spike detection thresholds against.

    ``median(|x|) / 0.6745`` is the robust standard deviation MEA-NAP's
    threshold methods use (see ``detect_spikes_threshold``); repeating it here
    means the SNR shown beside a threshold is measured against the same noise
    the threshold was set from.
    """
    trace = np.asarray(trace, dtype=float)
    if trace.size == 0:
        return float("nan")
    return float(np.median(np.abs(trace)) / 0.6745)


def _spectrum(trace: np.ndarray, fs: float,
              seconds: float = 60.0) -> tuple[np.ndarray, np.ndarray]:
    """Welch power spectral density over up to *seconds* of *trace*.

    A minute is far more than a spectrum needs and much less than a recording
    holds, which keeps this fast enough to recompute whenever a filter corner
    changes — the point of the plot is watching it move.
    """
    trace = np.asarray(trace, dtype=float).ravel()
    if trace.size < 16 or fs <= 0:
        return np.array([]), np.array([])
    trace = trace[: int(min(trace.size, seconds * fs))]
    nperseg = int(min(trace.size, max(256, 2 ** int(np.log2(fs / 2)))))
    freqs, psd = welch(trace, fs=fs, nperseg=nperseg)
    keep = freqs > 0
    return freqs[keep], psd[keep]


def _decimate(trace: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    """Indices and values that draw *trace* in about *target* points.

    Plain strided sampling is wrong here: a spike is a handful of samples, so
    taking every *k*-th one drops most spikes and shows a flat line where the
    detection found events. Instead each bin contributes its minimum and its
    maximum, in sample order — the envelope, which keeps every excursion the
    eye needs at a cost that does not grow with the window.
    """
    n = trace.size
    if n <= target:
        return np.arange(n), trace
    bins = max(1, target // 2)
    edges = np.linspace(0, n, bins + 1).astype(int)
    keep = []
    for start, stop in zip(edges[:-1], edges[1:]):
        if stop <= start:
            continue
        chunk = trace[start:stop]
        lo = start + int(np.argmin(chunk))
        hi = start + int(np.argmax(chunk))
        keep.extend((lo, hi) if lo <= hi else (hi, lo))
    idx = np.array(keep, dtype=int)
    return idx, trace[idx]


# ── Background workers ────────────────────────────────────────────────────────

class _Worker(QThread):
    """A thread that reports one result or one message, never a traceback.

    Every job in this window is "load or compute something big, then redraw" —
    same shape, same failure handling, so they share a base rather than
    repeating the try/except three times.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    #: ``(units_done, units_total)`` for a job that can count its own work.
    #: Jobs that cannot — reading a file is one call that returns when it
    #: returns — simply never emit it, and the window stays indeterminate.
    progress = pyqtSignal(int, int)

    def work(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def run(self) -> None:
        try:
            self.done.emit(self.work())
        except Exception as exc:   # noqa: BLE001 - reported to the user as text
            self.failed.emit(str(exc))


class _LoadRawWorker(_Worker):
    def __init__(self, source) -> None:
        super().__init__()
        self._source = source

    def work(self):
        dat, channels, fs = load_raw_recording(self._source)
        return dat.astype(np.float64, copy=False), channels, float(fs)


class _LoadSpikesWorker(_Worker):
    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def work(self) -> SpikeFile:
        return load_spike_file(self._path)


class _DetectWorker(_Worker):
    """Run detection over *ch_indices*, reported against the original indices.

    Slicing the columns and handing the slice to the pipeline's own
    :func:`detect_spikes_recording` is what makes one channel cheap to try:
    the detection a single channel gets here is byte-for-byte the one a full
    run would give it, so a threshold chosen in this window holds when the
    pipeline runs.
    """

    def __init__(self, dat, channels, fs: float,
                 params: SpikeDetectionParams, ch_indices: list[int]) -> None:
        super().__init__()
        self._dat, self._channels, self._fs = dat, channels, fs
        self._params, self._ch_indices = params, list(ch_indices)

    def work(self):
        subset = self._dat[:, self._ch_indices]
        result = detect_spikes_recording(
            subset, np.asarray(self._channels)[self._ch_indices], self._fs,
            self._params, progress=self.progress.emit,
        )
        times, waves, thresholds = {}, {}, {}
        for local, original in enumerate(self._ch_indices):
            times[original] = result.spike_times.get(local, {})
            waves[original] = result.spike_waveforms.get(local, {})
            thresholds[original] = result.thresholds.get(local, {})
        return times, waves, thresholds


class _SweepWorker(_Worker):
    """Detect at every threshold in a range, and summarise each.

    One call, not one per threshold: the filtering and the noise medians are
    per channel, so asking for thirteen thresholds together costs about what
    asking for one does — half a second on a ten-minute channel, a quarter of a
    minute on a whole array.
    """

    def __init__(self, dat, channels, fs: float, params: SpikeDetectionParams,
                 ch_indices: list[int], multipliers: list[float],
                 duration_s: float, ref_period_ms: float, min_rate: float) -> None:
        super().__init__()
        self._dat, self._channels, self._fs = dat, channels, fs
        self._params, self._ch_indices = params, list(ch_indices)
        self._multipliers = list(multipliers)
        self._duration_s, self._ref_period_ms = duration_s, ref_period_ms
        self._min_rate = min_rate

    def work(self):
        subset = self._dat[:, self._ch_indices]
        result = detect_spikes_recording(
            subset, np.asarray(self._channels)[self._ch_indices], self._fs,
            self._params, progress=self.progress.emit,
        )
        return sweep_points(result, self._multipliers, self._duration_s,
                            self._ref_period_ms, self._min_rate)


class _BurstWorker(_Worker):
    """Detect bursts once per spike method, and keep the results apart.

    Which spikes you feed a burst detector decides what it finds — a permissive
    threshold and a strict one on the same recording disagree about how many
    network bursts there are, and by a lot. So the results are held per method
    rather than pooled, and every method on screen is done in one go: burst
    detection costs hundredths of a second next to the detection that produced
    the spikes, so there is nothing to be saved by doing them one at a time.
    """

    def __init__(self, spikes_by_method: dict[str, dict[int, np.ndarray]],
                 n_channels: int, fs: float, duration_s: float,
                 settings: dict) -> None:
        super().__init__()
        self._by_method, self._n_channels = spikes_by_method, n_channels
        self._fs, self._duration_s, self._settings = fs, duration_s, settings

    def work(self):
        s = self._settings
        results = {}
        for index, (method, spikes) in enumerate(self._by_method.items(), start=1):
            _, burst_times, burst_channels, info = burst_detect_network(
                spikes, self._fs,
                min_spikes=s["network_min_spikes"],
                min_channels=s["network_min_channels"],
                isin_th_param=s["network_isi_threshold"],
            )
            single = single_channel_burst_detection(
                spikes, self._n_channels, self._fs,
                min_spikes=s["single_min_spikes"],
                isi_threshold=s["single_isi_threshold"],
                recording_duration_s=self._duration_s,
            )
            results[method] = (burst_times, burst_channels, info, single)
            self.progress.emit(index, len(self._by_method))
        return results


# ── Canvases ──────────────────────────────────────────────────────────────────

class _Canvas(FigureCanvasQTAgg):
    def __init__(self, figsize=(9, 6)) -> None:
        self._fig = Figure(figsize=figsize, tight_layout=True)
        self._fig.patch.set_facecolor("white")
        super().__init__(self._fig)

    def message(self, text: str) -> None:
        """Clear to a single sentence saying what is missing."""
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.text(0.5, 0.5, text, ha="center", va="center",
                transform=ax.transAxes, color="#888888", fontsize=11)
        ax.axis("off")
        self.draw()


class _TimeRectViewBox(pg.ViewBox):
    """A view box whose drag-rectangle zooms the time axis only.

    pyqtgraph's own rectangle zoom sets both axes from the box you drew, which
    on a voltage trace is wrong twice over: the useful vertical range is
    "whatever is in view" — which is why y is auto-ranged here — and a
    rectangle drawn to pick out a couple of spikes would clip the trace to
    however high the pointer happened to be. The width of the rectangle is the
    part that carries intent, so only the width is used.
    """

    def showAxRect(self, ax, **kwargs) -> None:
        self.setXRange(ax.left(), ax.right(), padding=0)
        self.enableAutoRange(axis="y")


class _PgView(QWidget):
    """A pyqtgraph page: a stack of linked plots, a placeholder, and an export.

    The two interactive views share these three things and nothing else, so the
    base is deliberately thin — everything about what is *on* the plots belongs
    to the view that draws them.
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self._graphics)
        self._placeholder = None

    def _plot(self, row: int, stretch: int = 1, view_box=None):
        plot = self._graphics.addPlot(row=row, col=0, viewBox=view_box)
        self._graphics.ci.layout.setRowStretchFactor(row, stretch)
        return plot

    def _say(self, plot, text: str) -> None:
        """Put *text* in the middle of *plot*, in place of any content."""
        plot.clear()
        label = pg.TextItem(text, color="#888888", anchor=(0.5, 0.5))
        plot.addItem(label)
        label.setPos(0.5, 0.5)
        plot.setTitle("")

    def export(self, path: str) -> None:
        """Write the current view to *path* (PNG, or SVG by extension)."""
        if path.lower().endswith(".svg"):
            exporter = pg_exporters.SVGExporter(self._graphics.scene())
        else:
            exporter = pg_exporters.ImageExporter(self._graphics.scene())
            exporter.parameters()["width"] = 1800
        exporter.export(path)


class _TraceView(_PgView):
    """The trace, its spikes, and where in the recording you are looking.

    This is the one view where the interaction *is* the work — you find a
    candidate spike by moving around until you are close enough to see its
    shape — so it is drawn with pyqtgraph rather than matplotlib. The whole
    channel goes to the plot once and pyqtgraph decimates per view (peak-
    preserving, so a spike never vanishes into a smoothed line); panning a
    ten-minute channel then costs nothing, where a re-render per mouse move
    could not keep up.

    Three rows, sharing one time axis:

    * the **trace**, with each selected method's spikes marked on the
      excursions they caught;
    * a **tick row** per method, because two methods that catch the same spike
      draw one marker on top of the other and a row each is how you see that
      they disagree at all;
    * the **overview**, the whole recording with a draggable region showing
      the stretch above. Zoom the trace and the region shrinks to match; drag
      the region and the trace follows. It is one window described twice, which
      is what makes "where am I" answerable at any zoom.
    """

    #: The visible time range changed — ``(start_s, end_s)``. Emitted for any
    #: cause: the wheel, a drag, the region, or :meth:`set_range` itself.
    range_changed = pyqtSignal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.trace = self._plot(0, stretch=6, view_box=_TimeRectViewBox())
        self.ticks = self._plot(1)
        self.overview = self._plot(2)
        self.ticks.setMaximumHeight(90)
        self.overview.setMaximumHeight(110)

        # Vertical panning is not a thing anyone wants on a voltage trace: the
        # useful y range is "whatever is in view", which auto-range gives for
        # free and a stray drag would only spoil.
        for plot in (self.trace, self.ticks):
            plot.setMouseEnabled(x=True, y=False)
        self.trace.enableAutoRange(axis="y")
        self.ticks.setXLink(self.trace)
        self.ticks.setYRange(-0.6, 0.6)
        self.ticks.hideAxis("bottom")
        self.trace.setLabel("left", "Voltage")
        # No axis label on the tick rows: each row is named already, and a
        # rotated "Methods" beside them collides with the longer names.
        self.overview.setLabel("bottom", "Whole recording (s)")
        self.overview.setMouseEnabled(x=False, y=False)
        self.overview.hideAxis("left")
        self.overview.setMenuEnabled(False)

        self._region = pg.LinearRegionItem(brush=(31, 119, 180, 45),
                                           hoverBrush=(31, 119, 180, 75))
        # Zoomed in far enough, the region is a fraction of a pixel wide and
        # the fill draws nothing at all. Its two edges are drawn solid instead,
        # so however narrow the window gets there is always a mark on the
        # overview saying where in the recording it is.
        for line in self._region.lines:
            line.setPen(pg.mkPen("#0d3b66", width=2))
            line.setHoverPen(pg.mkPen("#0d3b66", width=3))
        self._region.setZValue(10)
        self.overview.addItem(self._region)

        self._title = self.trace.setTitle("", size="10pt", color="#222222")
        self._syncing = False
        self._duration = 0.0
        self._time: np.ndarray | None = None
        self._filtered: np.ndarray | None = None
        self._fs = 1.0
        self._spike_items: list = []
        self._threshold_lines: list = []

        self._region.sigRegionChanged.connect(self._on_region)
        self.trace.sigXRangeChanged.connect(self._on_plot_range)
        self.message("Load a raw recording to see its traces.")

    # ── Content ───────────────────────────────────────────────────────────────

    def message(self, text: str) -> None:
        """Clear to a single sentence saying what is missing."""
        self.ticks.clear()
        self._spike_items.clear()
        self._threshold_lines.clear()
        self._filtered = None
        self._say(self.trace, text)

    def set_title(self, title: str) -> None:
        """Set the plot's title, which pyqtgraph renders as HTML.

        Escaped, because the quality summary says ``0.4% ISIs < 1 ms`` and an
        unescaped ``<`` opens a tag that swallows the rest of the line — the
        measures after it simply vanished.
        """
        markup = "<br>".join(html.escape(line) for line in title.splitlines())
        self.trace.setTitle(markup, size="9pt", color="#222222")

    def show_trace(self, time_axis, filtered, raw, fs: float, duration_s: float,
                   title: str) -> None:
        """Put one channel's trace on the plot. Cheap to call; drawn once."""
        self.trace.clear()
        self._spike_items.clear()
        self._threshold_lines.clear()
        self._time, self._filtered, self._fs = time_axis, filtered, fs
        self._duration = duration_s

        if raw is not None:
            self._curve(self.trace, time_axis, raw, _RAW_COLOR, width=1, alpha=140)
        self._curve(self.trace, time_axis, filtered, _TRACE_COLOR, width=1)
        self.trace.setTitle(title, size="9pt", color="#222222")
        self.trace.setLabel("bottom", "Time (s)")

        self.overview.clear()
        self.overview.addItem(self._region)
        # A whole-recording envelope, not every sample: the overview is a map,
        # and pyqtgraph would happily draw ten minutes of trace into 110 pixels
        # at a cost paid on every redraw for detail no one can see.
        self._curve(self.overview, time_axis, filtered, "#c9d2da", width=1,
                    downsample=max(1, int(filtered.size / 4000)))
        self.overview.setXRange(0, max(duration_s, 0.001), padding=0.01)

    def _curve(self, plot, x, y, color, width=1, alpha=255, downsample=None):
        pen = pg.mkPen(pg.mkColor(color), width=width)
        if alpha < 255:
            pen.setColor(pg.mkColor(*_rgb(color), alpha))
        item = plot.plot(x, y, pen=pen)
        if downsample is not None:
            item.setDownsampling(ds=downsample, auto=False, method="peak")
        else:
            item.setDownsampling(auto=True, method="peak")
        item.setClipToView(True)
        return item

    def show_spikes(self, methods: list[tuple[str, np.ndarray, str]], *,
                    solid: bool = False, offset: float = 0.0) -> None:
        """Mark *methods* — ``(name, times, colour)`` — on the trace and ticks.

        Separate from :meth:`show_trace` so toggling a method redraws the
        markers only, leaving the trace itself alone.

        *offset* stacks the methods vertically, each one further below the
        spike than the last. Without it, two methods that caught the same spike
        put their markers at exactly the same point and only the last drawn is
        visible — which is precisely the case worth seeing, since where methods
        agree and where they do not is the reason for showing several at once.
        Downwards, into the space under the trough, rather than up across the
        trace.

        *solid* fills the markers. Open ones stay legible where a dense channel
        would otherwise become a band; filled ones are easier to pick out when
        zoomed in on a handful of spikes. Which is better depends on the zoom,
        so it is a switch rather than a decision made here.
        """
        self._discard(self._spike_items)
        self.ticks.clear()

        for row, (name, times, colour) in enumerate(methods):
            times = np.asarray(times, dtype=float).ravel()
            y = -row  # newest method lowest, so the first is nearest the trace
            self.ticks.addItem(_tick_item(times, y - 0.35, y + 0.35, colour))
            if self._filtered is None or not times.size:
                continue
            # Rounded, not truncated. A spike time is a frame index that went
            # through a division by fs, so the round trip lands on 12344.9999
            # as often as 12345.0 — and one sample either side of a peak is a
            # completely different voltage, which put a scattering of markers
            # up in the noise band.
            frames = np.clip(np.rint(times * self._fs).astype(int), 0,
                             self._filtered.size - 1)
            # Every spike, at every zoom. An earlier version hid them once
            # there were too many to tell apart, which was the wrong trade:
            # what they were hiding was the trace, and the fix for that is the
            # z-order below, not making the marks come and go. Forty thousand
            # of these still pan at 55 fps, so there was never a cost to pay.
            scatter = pg.ScatterPlotItem(
                x=times, y=self._filtered[frames] - (row + 1) * offset,
                symbol="t", size=7,
                pen=pg.mkPen(*_rgb(colour), 200, width=1.2),
                brush=pg.mkBrush(*_rgb(colour), 170) if solid else None)
            # Behind the trace, so a channel dense enough for its markers to
            # merge into a band still has its trace drawn over the top of them.
            scatter.setZValue(-10)
            self.trace.addItem(scatter)
            self._spike_items.append(scatter)

        rows = max(len(methods), 1)
        self.ticks.setYRange(-rows + 0.4, 0.6)
        # The count belongs on the row rather than in a legend: the whole point
        # of stacking the methods is comparing them, and "how many did each
        # find" is the first half of that comparison.
        self._label_ticks([(-row, f"{name}  ({np.asarray(times).size})")
                           for row, (name, times, _) in enumerate(methods)])

    def show_thresholds(self, thresholds: list[tuple[float, str]]) -> None:
        self._discard(self._threshold_lines)
        for value, colour in thresholds:
            if value is None or not np.isfinite(value):
                continue
            line = pg.InfiniteLine(pos=value, angle=0,
                                   pen=pg.mkPen(*_rgb(colour), 120, width=1,
                                                style=Qt.PenStyle.DashLine))
            self.trace.addItem(line)
            self._threshold_lines.append(line)

    # ── Range, in both directions ─────────────────────────────────────────────

    def _label_ticks(self, labels: list[tuple[int, str]]) -> None:
        axis = self.ticks.getAxis("left")
        axis.setTicks([labels])
        # Measured, not guessed: an axis narrower than its label draws no label
        # at all rather than clipping it or widening itself.
        font = axis.style.get("tickFont") or self.font()
        metrics = QFontMetrics(font)
        needed = max((metrics.horizontalAdvance(text) for _, text in labels),
                     default=0)
        axis.setWidth(max(70, needed + 14))

    def _discard(self, items: list) -> None:
        """Take *items* off the trace, tolerating ones already gone.

        ``show_trace`` clears the whole plot when the channel changes, so by
        the time the markers are rebuilt the objects tracked here may no longer
        be in it — and ``PlotItem.removeItem`` on an absent item is a Qt
        warning at best.
        """
        for item in items:
            if item in self.trace.items:
                self.trace.removeItem(item)
        items.clear()

    def set_box_zoom(self, on: bool) -> None:
        """Left-drag draws a zoom rectangle (*on*) or pans (*off*)."""
        self.trace.vb.setMouseMode(pg.ViewBox.RectMode if on
                                   else pg.ViewBox.PanMode)

    def set_range(self, t0: float, t1: float) -> None:
        """Show ``[t0, t1]``, without reporting it back as a user action."""
        self._syncing = True
        try:
            self.trace.setXRange(t0, t1, padding=0)
            self._region.setRegion((t0, t1))
        finally:
            self._syncing = False

    def _on_region(self) -> None:
        if self._syncing:
            return
        t0, t1 = self._region.getRegion()
        self._syncing = True
        try:
            self.trace.setXRange(t0, t1, padding=0)
        finally:
            self._syncing = False
        self.range_changed.emit(float(t0), float(t1))

    def _on_plot_range(self, _item, view_range) -> None:
        t0, t1 = float(view_range[0]), float(view_range[1])
        if not self._syncing:
            self._syncing = True
            try:
                self._region.setRegion((t0, t1))
            finally:
                self._syncing = False
            self.range_changed.emit(t0, t1)

def _tick_item(times: np.ndarray, y0: float, y1: float, colour: str):
    """One drawable holding a vertical tick at every time in *times*.

    ``connect="pairs"`` makes a single item out of thousands of segments; an
    item per spike is what makes a raster of a busy recording unusable.
    """
    times = np.asarray(times, dtype=float).ravel()
    if not times.size:
        return pg.PlotDataItem(x=np.array([]), y=np.array([]))
    x = np.repeat(times, 2)
    y = np.tile(np.array([y0, y1]), times.size)
    return pg.PlotDataItem(x=x, y=y, connect="pairs",
                           pen=pg.mkPen(colour, width=1))


def _time_toolbar(*, on_zoom, on_step, on_jump, on_whole, on_save,
                  jump_label: str, jump_tip: str, box_zoom_tip: str,
                  noun: str) -> tuple[QWidget, QLabel, QPushButton]:
    """The row of time controls both plot tabs carry.

    Wheel-zoom and drag-pan are what anyone tries first and nothing on screen
    says they work, so the same moves are here as buttons — which is also the
    only way to make them with a trackpad that swallows the wheel. Shared
    between the traces and the bursts because the two are the same activity on
    the same axis, and a control that lived on one and not the other would read
    as the other one being unable to do it.

    Returns the bar, its window label, and the box-zoom toggle, for the caller
    to keep and update.
    """
    bar = QWidget()
    bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(bar)
    row.setContentsMargins(4, 2, 4, 0)

    def button(label: str, tip: str, slot) -> QPushButton:
        widget = QPushButton(label)
        widget.setToolTip(tip)
        widget.setFixedWidth(max(38, widget.sizeHint().width()))
        widget.clicked.connect(slot)
        row.addWidget(widget)
        return widget

    button("−", f"Show a longer stretch of the recording (or scroll down over "
                f"the {noun})", lambda: on_zoom(1.5))
    button("+", f"Close in on the window's centre (or scroll up over the "
                f"{noun})", lambda: on_zoom(1 / 1.5))

    box_zoom = QPushButton("⬚ Zoom to box")
    box_zoom.setCheckable(True)
    box_zoom.setToolTip(box_zoom_tip)
    box_zoom.setFixedWidth(box_zoom.sizeHint().width())
    row.addSpacing(8)
    row.addWidget(box_zoom)
    row.addSpacing(8)

    button("◀", f"Back one window (or drag the {noun}, or press ←)",
           lambda: on_step(-1))
    button("▶", f"Forward one window (or drag the {noun}, or press →)",
           lambda: on_step(1))
    row.addSpacing(8)
    jump = button(jump_label, jump_tip, on_jump)
    jump.setFixedWidth(jump.sizeHint().width())

    label = QLabel()
    label.setStyleSheet("color: gray;")
    row.addSpacing(12)
    row.addWidget(label)
    row.addStretch()

    whole = QPushButton("Whole recording")
    whole.setToolTip("Zoom back out to the entire recording.")
    whole.clicked.connect(on_whole)
    row.addWidget(whole)

    save = QPushButton("Save figure…")
    save.clicked.connect(on_save)
    row.addWidget(save)
    return bar, label, box_zoom


def _swatch(colour: str, size: int = 12) -> QIcon:
    """A small filled square, so the list says which colour a method draws in."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(colour))
    return QIcon(pixmap)


def _rgb(colour: str) -> tuple[int, int, int]:
    c = pg.mkColor(colour)
    return c.red(), c.green(), c.blue()


class _ArrayMap(QWidget):
    """The electrode grid, coloured by firing rate, clicked to pick a channel.

    A dropdown of channel numbers asks you to know which number is the one in
    the corner that looks dead, which nobody does. This is the same choice made
    the way the question actually arises — *that* electrode, the bright one, or
    the one next to a bright one — and because it is coloured by rate it doubles
    as the map of where the activity is.

    Painted directly rather than embedded as a figure. A matplotlib canvas here
    read as a picture pasted into the window: its own white ground against the
    panel's, its own margins, its own fonts. This one takes its background and
    its text colour from the widget palette, so it belongs to the form it sits
    in — and it costs nothing to repaint as the selection moves.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: Called with a channel index when an electrode is clicked.
        self.pick = None
        self._coords: np.ndarray | None = None
        self._rates: np.ndarray | None = None
        self._names: list[str] = []
        self._selected: int | None = None
        self._caption = ""
        self._unit = "Hz"
        self._message = "No electrode layout for these channels"
        self._geometry: tuple[np.ndarray, float] | None = None
        # Square, so the height is what decides how big the array is drawn.
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Content ───────────────────────────────────────────────────────────────

    def show_array(self, coords, rates, names: list[str], selected: int | None,
                   caption: str, unit: str = "Hz") -> None:
        self._coords = np.asarray(coords, float) if coords is not None else None
        self._rates = np.asarray(rates, float) if rates is not None else None
        self._unit = unit
        self._names = names
        self._selected = selected
        self._caption = caption
        self._geometry = None
        self.update()

    def message(self, text: str) -> None:
        self._coords = None
        self._message = text
        self.update()

    # ── Where the electrodes land ─────────────────────────────────────────────

    def _layout(self) -> tuple[np.ndarray, float] | None:
        """Electrode centres in widget pixels, and the radius to draw them at.

        Recomputed whenever the widget is resized, and cached in between: a
        repaint on every mouse move must not redo the arithmetic for sixty
        electrodes.
        """
        if self._coords is None or not len(self._coords):
            return None
        if self._geometry is not None:
            return self._geometry

        coords = self._coords
        finite = np.isfinite(coords).all(axis=1)
        if not finite.any():
            return None
        low = np.nanmin(coords[finite], axis=0)
        high = np.nanmax(coords[finite], axis=0)
        span = np.maximum(high - low, 1e-9)

        top = _MAP_CAPTION_PX if self._caption else 4
        side = _MAP_SCALE_PX
        usable = min(self.width() - 2 * _MAP_MARGIN,
                     self.height() - top - side - 2 * _MAP_MARGIN)
        usable = max(usable, 10.0)
        # Square, so the array keeps its aspect: an MEA stretched to the
        # panel's shape is a different array.
        left = (self.width() - usable) / 2
        span_max = float(max(span))
        centres = np.full((len(coords), 2), np.nan)
        centres[finite, 0] = left + (coords[finite, 0] - low[0]) / span_max * usable
        centres[finite, 1] = (top + _MAP_MARGIN
                              + (high[1] - coords[finite, 1]) / span_max * usable)
        # One electrode's share of the grid, less a gap.
        per_row = max(np.sqrt(len(coords)), 2.0)
        radius = max(usable / per_row * 0.36, 2.0)
        self._geometry = (centres, radius)
        return self._geometry

    def resizeEvent(self, event) -> None:
        self._geometry = None
        super().resizeEvent(event)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text_color = palette.windowText().color()

        layout = self._layout()
        if layout is None:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        centres, radius = layout
        if self._caption:
            faded = QColor(text_color)
            faded.setAlpha(170)
            painter.setPen(faded)
            font = painter.font()
            font.setPointSizeF(max(font.pointSizeF() - 1.0, 6.5))
            painter.setFont(font)
            painter.drawText(0, 0, self.width(), _MAP_CAPTION_PX,
                             Qt.AlignmentFlag.AlignCenter, self._caption)

        rates = self._rates if (self._rates is not None
                                and len(self._rates) == len(centres)) else None
        low, high = _rate_range(rates)
        outline = QColor(text_color)
        outline.setAlpha(90)
        for index, (x, y) in enumerate(centres):
            if not np.isfinite(x):
                continue
            value = rates[index] if rates is not None else np.nan
            painter.setBrush(QBrush(_viridis(value, low, high)))
            painter.setPen(QPen(outline, 0.8))
            painter.drawEllipse(QPointF(x, y), radius, radius)

        if self._selected is not None and self._selected < len(centres) \
                and np.isfinite(centres[self._selected, 0]):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(_SPIKE_COLOR), 2.2))
            painter.drawEllipse(QPointF(*centres[self._selected]),
                                radius + 3.0, radius + 3.0)

        if rates is not None and high > low:
            self._paint_scale(painter, low, high, text_color)

    def _paint_scale(self, painter: QPainter, low: float, high: float,
                     text_color: QColor) -> None:
        """A thin gradient with the two ends labelled, in place of a colorbar.

        A matplotlib colorbar took a fifth of the width and repeated the units
        three times. The range is two numbers; this is two numbers.
        """
        bar = QRectF(_MAP_MARGIN, self.height() - _MAP_SCALE_PX + 4,
                     self.width() - 2 * _MAP_MARGIN, 6.0)
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for stop in np.linspace(0, 1, 12):
            gradient.setColorAt(float(stop), _viridis(low + stop * (high - low),
                                                      low, high))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(bar, 3, 3)

        faded = QColor(text_color)
        faded.setAlpha(170)
        painter.setPen(faded)
        font = painter.font()
        font.setPointSizeF(max(font.pointSizeF() - 1.5, 6.0))
        painter.setFont(font)
        labels = QRectF(bar.left(), bar.bottom() + 1, bar.width(), 14)
        painter.drawText(labels, Qt.AlignmentFlag.AlignLeft,
                         f"{low:.2g} {self._unit}".strip())
        painter.drawText(labels, Qt.AlignmentFlag.AlignRight,
                         f"{high:.2g} {self._unit}".strip())

    # ── Picking ───────────────────────────────────────────────────────────────

    def _nearest(self, point) -> int | None:
        """The electrode under the pointer, or None if it is not near one."""
        layout = self._layout()
        if layout is None:
            return None
        centres, radius = layout
        distances = np.hypot(centres[:, 0] - point.x(), centres[:, 1] - point.y())
        if not np.isfinite(distances).any():
            return None
        index = int(np.nanargmin(distances))
        # A little beyond the electrode itself, so a near miss still counts and
        # a click on empty space does not select whichever was least far away.
        return index if distances[index] <= radius * 1.8 else None

    def mousePressEvent(self, event) -> None:
        index = self._nearest(event.position())
        if index is not None and self.pick is not None:
            self.pick(index)

    def mouseMoveEvent(self, event) -> None:
        index = self._nearest(event.position())
        if index is None:
            self.setToolTip("Click an electrode to look at that channel.")
            return
        rate = self._rates[index] if (self._rates is not None
                                      and index < len(self._rates)) else float("nan")
        name = self._names[index] if index < len(self._names) else str(index)
        self.setToolTip(f"Channel {name} — {rate:.2f} {self._unit}".strip())


def _rate_range(rates) -> tuple[float, float]:
    if rates is None or not len(rates) or not np.isfinite(rates).any():
        return 0.0, 1.0
    low, high = float(np.nanmin(rates)), float(np.nanmax(rates))
    return (low, high) if high > low else (low, low + 1.0)


def _viridis(value: float, low: float, high: float) -> QColor:
    """A value's colour on viridis — matplotlib's map, without its figure."""
    if not np.isfinite(value):
        return QColor(210, 214, 218)
    fraction = 0.0 if high <= low else (value - low) / (high - low)
    red, green, blue, _ = colormaps["viridis"](float(np.clip(fraction, 0, 1)))
    return QColor(int(red * 255), int(green * 255), int(blue * 255))


class _QualityCanvas(_Canvas):
    """Waveforms, amplitudes, ISIs and the array map, on one page.

    These four answer four different ways a detection goes wrong — the wrong
    shape, the wrong threshold, double-counted spikes, and one channel standing
    in for an array — and they are only conclusive together, which is why they
    share a figure rather than a tab each.

    Each of the first three draws every method ticked on the left, in that
    method's colour, because the question that follows "are these spikes?" is
    "then why does the other method disagree?". Two shapes of page come out of
    that, and they are deliberately different:

    * **one method** — its individual waveforms behind the mean, and the full
      set of numbers in the title. This is the view for judging a detection.
    * **several** — mean ± SD per method and no individuals, since a hundred
      grey traces from each of three methods is a grey rectangle. The numbers
      move into the legends, one line per method, because comparing them is
      the entire point.
    """

    def __init__(self) -> None:
        super().__init__(figsize=(9, 6))
        self.message("Detect spikes, or load a spike file, to check quality.")

    def render(self, methods: list[dict], fs: float, ref_period_ms: float,
               rates, coords, selected_index: int | None, head: str,
               summary: str, max_waveforms: int,
               map_label: str = "Firing rate (Hz)") -> None:
        """Draw *methods* — each ``{name, waveforms, times, threshold, color}``.

        ``rates``, ``coords``, ``selected_index`` and ``map_label`` describe
        the array map,
        which shows one method however many are ticked: it is a colour scale,
        and two of those on one set of electrodes cannot be read.
        """
        self._fig.clear()
        axes = self._fig.subplots(2, 2)
        ax_wave, ax_amp = axes[0]
        ax_isi, ax_map = axes[1]
        self._fig.suptitle(_fit_title(head, summary, width=96), fontsize=9)

        alone = len(methods) == 1
        self._draw_waveforms(ax_wave, methods, fs, max_waveforms, alone)
        self._draw_amplitudes(ax_amp, methods, alone)
        self._draw_isis(ax_isi, methods, ref_period_ms, alone)
        self._draw_array(ax_map, rates, coords, selected_index, map_label)
        self.draw()

    # ── The four panels ───────────────────────────────────────────────────────

    def _draw_waveforms(self, ax, methods: list[dict], fs: float,
                        max_waveforms: int, alone: bool) -> None:
        drawn = 0
        for method in methods:
            waveforms = np.asarray(method["waveforms"], dtype=float) \
                if method["waveforms"] is not None else np.zeros((0, 0))
            if waveforms.ndim != 2 or not waveforms.size:
                continue
            drawn += 1
            colour = method["color"]
            t_ms = (np.arange(waveforms.shape[1]) - waveforms.shape[1] // 2) / fs * 1000.0
            if alone:
                # The spread of the individual spikes is the evidence; the mean
                # alone hides a bimodal channel completely.
                step = max(1, waveforms.shape[0] // max_waveforms)
                ax.plot(t_ms, waveforms[::step].T, lw=0.4, color="#9aa7b4", alpha=0.5)
            mean = waveforms.mean(axis=0)
            sd = waveforms.std(axis=0)
            ax.fill_between(t_ms, mean - sd, mean + sd, color=colour, alpha=0.18, lw=0)
            ax.plot(t_ms, mean, lw=1.6, color=colour,
                    label=f"{method['name']} ({waveforms.shape[0]})")
        if not drawn:
            _nothing_here(ax, "No waveforms for this channel and these methods.\n"
                              "Detect here to compute them.")
            return
        ax.set_xlabel("Time from peak (ms)")
        ax.set_ylabel("Voltage")
        ax.set_title("Waveforms — mean ± SD"
                     + (" over the individual spikes" if alone else " per method"),
                     fontsize=9)
        if not alone:
            ax.legend(fontsize=7)

    def _draw_amplitudes(self, ax, methods: list[dict], alone: bool) -> None:
        drawn = 0
        for method in methods:
            waveforms = np.asarray(method["waveforms"], dtype=float) \
                if method["waveforms"] is not None else np.zeros((0, 0))
            if waveforms.ndim != 2 or not waveforms.size:
                continue
            drawn += 1
            amplitudes = waveforms.min(axis=1)
            # Outlined rather than filled once there is more than one: filled
            # bars hide whichever method was drawn first.
            ax.hist(amplitudes, bins=40, color=method["color"],
                    histtype="stepfilled" if alone else "step",
                    linewidth=1.4, alpha=1.0 if not alone else 0.85,
                    label=method["name"])
            threshold = method["threshold"]
            if threshold is not None and np.isfinite(threshold):
                ax.axvline(threshold, color=method["color"], ls="--", lw=1.1,
                           alpha=0.8)
        if not drawn:
            _nothing_here(ax, "No amplitudes for this channel and these methods.")
            return
        ax.set_xlabel("Spike amplitude")
        ax.set_ylabel("Count")
        # Two lines: on one, the sentence is wider than the axes and
        # matplotlib clips it rather than wrapping — so the part that says what
        # to look for was the part that went missing.
        ax.set_title("Amplitudes, each method's threshold dashed\n"
                     "a peak against the line means spikes are being cut off",
                     fontsize=8)
        if not alone:
            # Counts differ by more than an order of magnitude between a
            # permissive threshold and a strict one, so on a linear axis the
            # strict ones are a flat line along the bottom — which is the
            # comparison this panel exists for.
            ax.set_yscale("log")
            ax.legend(fontsize=7)

    def _draw_isis(self, ax, methods: list[dict], ref_period_ms: float,
                   alone: bool) -> None:
        pooled = [np.diff(np.sort(np.asarray(m["times"], float).ravel()))
                  for m in methods]
        positive = [isis[isis > 0] * 1000.0 for isis in pooled if isis.size]
        if not any(p.size for p in positive):
            _nothing_here(ax, "Fewer than two spikes.")
            ax.set_xlabel("Inter-spike interval (ms)")
            return
        low = min(p.min() for p in positive if p.size)
        high = max(p.max() for p in positive if p.size)
        bins = np.logspace(np.log10(max(low, 1e-3)), np.log10(high), 50)

        labels = []
        for method, isis_ms in zip(methods, positive):
            if not isis_ms.size:
                continue
            ax.hist(isis_ms, bins=bins, color=method["color"],
                    histtype="stepfilled" if alone else "step",
                    linewidth=1.4, alpha=0.85 if alone else 1.0)
            _, fraction = refractory_violations(np.asarray(method["times"], float),
                                                ref_period_ms)
            labels.append(f"{method['name']} — {fraction * 100:.1f}% below")
        ax.set_xscale("log")
        ax.axvline(ref_period_ms, color="#33404d", ls="--", lw=1.2)
        ax.set_xlabel("Inter-spike interval (ms)")
        ax.set_ylabel("Count")
        if alone:
            ax.set_title(f"ISIs — {labels[0].split('— ')[1]} the "
                         f"{ref_period_ms:g} ms refractory period", fontsize=8)
        else:
            ax.set_yscale("log")
            ax.set_title(f"ISIs, against the {ref_period_ms:g} ms refractory "
                         f"period", fontsize=8)
            ax.legend(labels, fontsize=7)

    def _draw_array(self, ax, rates, coords, selected_index: int | None,
                    label: str = "Firing rate (Hz)") -> None:
        rates = np.asarray(rates, dtype=float)
        if coords is not None and rates.size and len(coords) == rates.size:
            coords = np.asarray(coords, dtype=float)
            scatter = ax.scatter(coords[:, 0], coords[:, 1], c=rates, s=110,
                                 cmap="viridis", edgecolors="#33404d",
                                 linewidths=0.4)
            if selected_index is not None and selected_index < len(coords):
                ax.scatter(*coords[selected_index], s=210, facecolors="none",
                           edgecolors=_SPIKE_COLOR, linewidths=2.0)
            self._fig.colorbar(scatter, ax=ax, label=label)
            ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f"{label} across the array "
                         f"(ringed: the channel above)", fontsize=8)
        else:
            ax.bar(np.arange(rates.size), rates, color="#4a6b8a")
            ax.set_xlabel("Channel index")
            ax.set_ylabel(label)
            ax.set_title(f"{label} per channel", fontsize=8)


def _nothing_here(ax, text: str) -> None:
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes,
            color="#888888", fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])


class _SweepCanvas(_Canvas):
    """How a channel's detection changes as the threshold moves.

    Picking a threshold is the one decision in spike detection with no right
    answer written down anywhere, and it is normally made by trying one, looking
    at a trace, and trying another. This does the trying — every threshold at
    once, which costs barely more than one because the filtering and the noise
    medians are per channel rather than per threshold — and plots what changes.

    What to look for is the point where the two halves disagree. Counts falling
    away steeply mean noise is being excluded; counts flattening mean real
    spikes are starting to be lost. Amplitude and SNR climbing steadily while
    the count barely moves is the sign of a threshold already high enough.
    """

    def __init__(self) -> None:
        super().__init__(figsize=(9, 6))
        self.message("Run a sweep to see how the threshold changes what is found.")

    def render(self, points: list, scope: str, current: list[float],
               knee: float | None) -> None:
        if not points:
            self.message("The sweep found nothing to summarise.")
            return
        self._fig.clear()
        axes = self._fig.subplots(2, 2)
        ax_count, ax_slope = axes[0]
        ax_amplitude, ax_waves = axes[1]
        self._fig.suptitle(scope, fontsize=9, fontweight="bold")

        multipliers = np.array([p.multiplier for p in points])
        counts = np.array([p.n_spikes for p in points], dtype=float)
        rates = np.array([p.rate for p in points])
        amplitudes = np.array([p.median_amplitude for p in points])
        snr = np.array([p.snr for p in points])
        active = np.array([p.active_channels for p in points], dtype=float)

        def mark(ax) -> None:
            """The thresholds already set, and the bound, on every panel."""
            for value in current:
                ax.axvline(value, color=_SPIKE_COLOR, lw=1.1, alpha=0.7)
            if knee is not None:
                ax.axvline(knee, color="#4a6b8a", lw=1.1, ls="--", alpha=0.8)

        ax_count.semilogy(multipliers, np.maximum(counts, 0.5), "o-", lw=1.4,
                          ms=4, color=_TRACE_COLOR)
        ax_count.set_ylabel("Spikes found")
        ax_count.set_title("How many — steep means noise is being cut, flat "
                           "means spikes are", fontsize=8)
        if active.max() > 1:
            twin = ax_count.twinx()
            twin.plot(multipliers, active, "s--", lw=1.0, ms=3, color="#77ac30")
            twin.set_ylabel("Active channels", color="#77ac30", fontsize=8)
            twin.tick_params(axis="y", labelcolor="#77ac30", labelsize=7)
        mark(ax_count)

        slopes = count_slopes(points)
        if slopes.size:
            # Plotted at the midpoint of each step, because a slope belongs
            # between two thresholds rather than at one.
            midpoints = (multipliers[:-1] + multipliers[1:]) / 2
            ax_slope.plot(midpoints, -slopes, "o-", lw=1.4, ms=4,
                          color=_TRACE_COLOR)
            ax_slope.axhline(-0.5 * float(np.nanmin(slopes)), color="#4a6b8a",
                             lw=1.0, ls=":")
        ax_slope.set_ylabel("Decades of spikes lost per MAD")
        ax_slope.set_title("How fast the count is falling — steep is noise "
                           "being cut, shallow is spikes", fontsize=8)
        mark(ax_slope)

        ax_amplitude.plot(multipliers, np.abs(amplitudes), "o-", lw=1.4, ms=4,
                          color=_TRACE_COLOR)
        ax_amplitude.set_ylabel("Median amplitude")
        ax_amplitude.set_xlabel("Threshold (MAD multiplier)")
        # How far past the bar the median spike sits — SNR divided by the
        # multiplier. Plotting SNR itself here would draw the same curve twice:
        # on one channel the noise is a constant, so SNR is just the amplitude
        # in different units. This is the part that is not already on the left
        # axis. Near 1 means the median spike is only barely crossing, which is
        # what a threshold down in the noise looks like.
        clearance = np.divide(snr, multipliers, out=np.full_like(snr, np.nan),
                              where=multipliers != 0)
        twin = ax_amplitude.twinx()
        twin.plot(multipliers, clearance, "^--", lw=1.0, ms=4, color=_BURST_COLOR)
        twin.axhline(1.0, color=_BURST_COLOR, lw=0.8, ls=":", alpha=0.6)
        twin.set_ylabel("Median spike ÷ threshold", color=_BURST_COLOR, fontsize=8)
        twin.tick_params(axis="y", labelcolor=_BURST_COLOR, labelsize=7)
        ax_amplitude.set_title("What is being admitted: amplitude (left), and "
                               "how far it clears the threshold (right)",
                               fontsize=8)
        mark(ax_amplitude)

        shown = [p for p in points if np.size(p.mean_waveform)]
        if shown:
            low, high = multipliers.min(), multipliers.max()
            for point in shown:
                fraction = ((point.multiplier - low) / (high - low)) if high > low else 0.5
                ax_waves.plot(
                    np.arange(point.mean_waveform.size) - point.mean_waveform.size // 2,
                    point.mean_waveform, lw=1.2,
                    color=colormaps["viridis"](fraction),
                    label=f"{point.multiplier:g}")
            ax_waves.set_title("Mean spike at each threshold — dark is low, "
                               "bright is high", fontsize=8)
            ax_waves.set_xlabel("Samples from peak")
            ax_waves.set_ylabel("Voltage")
        else:
            _nothing_here(ax_waves, "No waveforms in this sweep.")

        # One key for the whole figure: the same two lines mean the same thing
        # on every panel, and four copies of it would be four times the ink.
        handles = []
        if current:
            handles.append(Line2D([], [], color=_SPIKE_COLOR, lw=1.1,
                                  label=f"set now: {', '.join(f'{c:g}' for c in current)}"))
        if knee is not None:
            handles.append(Line2D([], [], color="#4a6b8a", lw=1.1, ls="--",
                                  label=f"count stops falling steeply at {knee:g}"))
        if handles:
            self._fig.legend(handles=handles, loc="lower center", ncols=2,
                             fontsize=7, frameon=False)
            self._fig.subplots_adjust(bottom=0.14)
        self.draw()


class _FilterCanvas(_Canvas):
    """What the bandpass did: the same stretch before and after, and its spectrum.

    The filter is the step nobody looks at and everybody inherits — 600–8000 Hz
    because that is what MEA-NAP has always shipped. On a recording with drift,
    or mains hum, or a high-frequency artefact, the right corners are not the
    default ones, and the way to find that out is to see which parts of the
    signal the filter is throwing away.

    The traces answer "does it still look like my data"; the spectrum answers
    "what did it remove", which the traces cannot, because the removed part is
    the low-frequency swing that dominates the raw trace's own scale.
    """

    def __init__(self) -> None:
        super().__init__(figsize=(9, 5))
        self.message("Load a raw recording to see what the filter does to it.")

    def render(self, raw, filtered, fs: float, t0: float, t1: float,
               low: float, high: float, spike_times, title: str) -> None:
        self._fig.clear()
        gs = self._fig.add_gridspec(2, 2, width_ratios=[1.3, 1])
        ax_raw = self._fig.add_subplot(gs[0, 0])
        ax_filtered = self._fig.add_subplot(gs[1, 0], sharex=ax_raw)
        ax_psd = self._fig.add_subplot(gs[:, 1])
        self._fig.suptitle(title, fontsize=9, fontweight="bold")

        start = max(0, int(t0 * fs))
        stop = min(raw.size, int(t1 * fs))
        for ax, trace, colour, name in ((ax_raw, raw[start:stop], _RAW_COLOR, "Raw"),
                                        (ax_filtered, filtered[start:stop],
                                         _TRACE_COLOR, "Filtered")):
            idx, values = _decimate(trace, _MAX_TRACE_POINTS)
            ax.plot((start + idx) / fs, values, lw=0.6, color=colour)
            # Each on its own scale: sharing one would draw the filtered trace
            # as a flat line beside the raw swing it exists to remove.
            ax.set_ylabel(f"{name}\nvoltage", fontsize=8)
            ax.margins(y=0.08)
        in_window = np.asarray(spike_times, dtype=float)
        in_window = in_window[(in_window >= t0) & (in_window <= t1)]
        for at in in_window:
            ax_filtered.axvline(at, color=_SPIKE_COLOR, lw=0.5, alpha=0.5, zorder=0)
        ax_raw.set_xlim(t0, t1)
        ax_raw.set_title("The same stretch, before and after — spikes marked below",
                         fontsize=8)
        ax_filtered.set_xlabel("Time (s)")

        freqs, raw_psd = _spectrum(raw, fs)
        _, filtered_psd = _spectrum(filtered, fs)
        if freqs.size:
            ax_psd.loglog(freqs, raw_psd, lw=0.9, color=_RAW_COLOR, label="raw")
            ax_psd.loglog(freqs, filtered_psd, lw=0.9, color=_TRACE_COLOR,
                          label="filtered")
            ax_psd.axvspan(low, min(high, fs / 2), color="#4a6b8a", alpha=0.10,
                           lw=0, label=f"passband {low:g}–{high:g} Hz")
            for corner in (low, high):
                if 0 < corner < fs / 2:
                    ax_psd.axvline(corner, color="#4a6b8a", ls="--", lw=0.9)
            kept = float(np.trapezoid(filtered_psd, freqs) / np.trapezoid(raw_psd, freqs)) \
                if np.trapezoid(raw_psd, freqs) > 0 else float("nan")
            ax_psd.set_title(f"Power spectrum — the filter keeps {kept * 100:.1f}% "
                             f"of the signal's power", fontsize=8)
            ax_psd.legend(fontsize=7, loc="lower left")
            # The stopband rolls off past every float the eye can use, and
            # letting it set the axis squashes the passband — where the whole
            # comparison lives — into the top centimetre. Eight decades is more
            # than enough to see the corners bite.
            top = float(np.nanmax(raw_psd))
            if top > 0:
                ax_psd.set_ylim(top * 1e-8, top * 3)
        ax_psd.set_xlabel("Frequency (Hz)")
        ax_psd.set_ylabel("Power spectral density")
        self.draw()


class _BurstView(_PgView):
    """The array raster with network bursts on it, and one channel's own bursts.

    Both detections are judged against the same spikes on the same time axis,
    because the failure worth catching is the disagreement between them — a
    channel bursting through a stretch the network detector calls quiet, or a
    network burst no single channel contributes a burst to.

    Interactive for the same reason the trace is: a ten-minute raster shows you
    that there are two hundred bursts and nothing about what any one of them is
    made of. The three rows share an x-axis, so zooming into a burst on the
    array carries the population rate and the selected channel with it.
    """

    #: The visible time range changed — ``(start_s, end_s)``.
    range_changed = pyqtSignal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.raster = self._plot(0, stretch=5, view_box=_TimeRectViewBox())
        self.rate = self._plot(1, stretch=2)
        self.channel = self._plot(2, stretch=2)
        self.overview = self._plot(3, stretch=1)
        for plot in (self.rate, self.channel):
            plot.setXLink(self.raster)
        for plot in (self.raster, self.rate, self.channel):
            plot.setMouseEnabled(x=True, y=False)
        self.raster.setLabel("left", "Channel")
        self.rate.setLabel("left", "Array rate (Hz)")
        self.channel.hideAxis("left")
        self.raster.hideAxis("bottom")
        self.rate.hideAxis("bottom")
        self.channel.hideAxis("bottom")

        # The same overview the traces have, and for the same reason: zoomed
        # into one burst you can no longer see that there are two hundred more,
        # or where in the recording this one sits among them.
        self.overview.setMaximumHeight(74)
        self.overview.setMouseEnabled(x=False, y=False)
        self.overview.hideAxis("left")
        self.overview.setMenuEnabled(False)
        self.overview.setLabel("bottom", "Whole recording (s) — every burst; "
                                         "click or drag to move the window")
        # Fainter than the trace overview's: what lies under this one is the
        # bursts themselves, and they are the thing being navigated towards.
        self._region = pg.LinearRegionItem(brush=(31, 119, 180, 26),
                                           hoverBrush=(31, 119, 180, 55))
        for line in self._region.lines:
            line.setPen(pg.mkPen("#0d3b66", width=2))
            line.setHoverPen(pg.mkPen("#0d3b66", width=3))
        self._region.setZValue(10)
        self.overview.addItem(self._region)

        self._syncing = False
        self._duration = 0.0
        self._region.sigRegionChanged.connect(self._on_region)
        self.raster.sigXRangeChanged.connect(self._on_plot_range)
        self.message("Detect bursts to see them.")

    # ── Range, in both directions ─────────────────────────────────────────────

    def set_box_zoom(self, on: bool) -> None:
        self.raster.vb.setMouseMode(pg.ViewBox.RectMode if on
                                    else pg.ViewBox.PanMode)

    def set_range(self, t0: float, t1: float) -> None:
        self._syncing = True
        try:
            self.raster.setXRange(t0, t1, padding=0)
            self._region.setRegion((t0, t1))
        finally:
            self._syncing = False

    def _on_region(self) -> None:
        if self._syncing:
            return
        t0, t1 = self._region.getRegion()
        self._syncing = True
        try:
            self.raster.setXRange(t0, t1, padding=0)
        finally:
            self._syncing = False
        self.range_changed.emit(float(t0), float(t1))

    def _on_plot_range(self, _item, view_range) -> None:
        t0, t1 = float(view_range[0]), float(view_range[1])
        if not self._syncing:
            self._syncing = True
            try:
                self._region.setRegion((t0, t1))
            finally:
                self._syncing = False
            self.range_changed.emit(t0, t1)

    def message(self, text: str) -> None:
        self.rate.clear()
        self.channel.clear()
        self.overview.clear()
        self.overview.addItem(self._region)
        self._say(self.raster, text)

    def render(self, spikes_by_channel: dict[int, np.ndarray], fs: float,
               duration_s: float, network_burst_times, channel_index: int,
               channel_name: str, channel_bursts, bin_width_s: float,
               title: str, xlim: tuple[float, float] | None = None) -> None:
        for plot in (self.raster, self.rate, self.channel):
            plot.clear()

        order = sorted(spikes_by_channel)
        rows, pooled = [], []
        for row, ch in enumerate(order):
            times = np.asarray(spikes_by_channel[ch], dtype=float).ravel()
            if times.size:
                rows.append((row, times))
                pooled.append(times)

        total = sum(times.size for _, times in rows)
        if total > _MAX_RASTER_SPIKES:
            # Drawn to show where the bursts are, which a tenth of the spikes
            # shows identically — and a million ticks is a raster nobody can
            # pan. Seeded, so the same recording draws the same picture twice.
            keep = _MAX_RASTER_SPIKES / total
            rng = np.random.default_rng(0)
            rows = [(row, times[rng.random(times.size) < keep]) for row, times in rows]

        burst_times = np.asarray(network_burst_times, dtype=float)
        if burst_times.size:
            burst_times = burst_times.reshape(-1, 2) / fs
            # One item for every burst: a region item each is hundreds of
            # graphics objects, and it is the same picture.
            starts, stops = burst_times[:, 0], burst_times[:, 1]
            spans = pg.BarGraphItem(
                x0=starts, x1=np.maximum(stops, starts + 1e-4),
                y0=np.full(starts.size, -1.0),
                y1=np.full(starts.size, max(len(order), 1) + 1.0),
                brush=pg.mkBrush(*_rgb(_BURST_COLOR), 90), pen=None)
            spans.setZValue(-10)
            self.raster.addItem(spans)

        for row, times in rows:
            self.raster.addItem(_tick_item(times, row - 0.4, row + 0.4, _TRACE_COLOR))
        self.raster.setYRange(-1, max(len(order), 1))
        self.raster.setTitle(html.escape(title), size="9pt", color="#222222")

        if pooled:
            everything = np.concatenate(pooled)
            edges = np.arange(0, max(duration_s, bin_width_s) + bin_width_s,
                              bin_width_s)
            counts, _ = np.histogram(everything, bins=edges)
            self.rate.plot(edges[:-1], counts / bin_width_s,
                           pen=pg.mkPen("#4a6b8a", width=1))

        own = np.asarray(spikes_by_channel.get(channel_index, ()), dtype=float).ravel()
        starts = np.asarray(channel_bursts.get("T_start", ()), dtype=float).ravel()
        stops = np.asarray(channel_bursts.get("T_end", ()), dtype=float).ravel()
        if starts.size:
            own_spans = pg.BarGraphItem(
                x0=starts, x1=np.maximum(stops, starts + 1e-4),
                y0=np.zeros(starts.size), y1=np.ones(starts.size),
                brush=pg.mkBrush(*_rgb(_BURST_COLOR), 140), pen=None)
            own_spans.setZValue(-10)
            self.channel.addItem(own_spans)
        self.channel.addItem(_tick_item(own, 0.05, 0.95, _TRACE_COLOR))
        self.channel.setYRange(0, 1)
        self.channel.setTitle(
            html.escape(f"Channel {channel_name}: {own.size} spikes, "
                        f"{starts.size} single-channel burst(s)"),
            size="9pt", color="#222222")

        self._duration = max(duration_s, 1.0)
        self.overview.clear()
        self.overview.addItem(self._region)
        if burst_times.size:
            whole = pg.BarGraphItem(
                x0=burst_times[:, 0],
                x1=np.maximum(burst_times[:, 1], burst_times[:, 0] + 1e-4),
                y0=np.zeros(len(burst_times)), y1=np.ones(len(burst_times)),
                brush=pg.mkBrush(*_rgb(_BURST_COLOR), 200), pen=None)
            self.overview.addItem(whole)
        self.overview.setXRange(0, self._duration, padding=0.01)
        self.overview.setYRange(0, 1)
        self.raster.setXRange(*(xlim or (0, self._duration)), padding=0)


class SpikeViewerWindow(QDialog):
    """Inspect and re-run spike and burst detection on one recording.

    Non-modal on purpose: the point of opening it from the Spike detection tab
    is to try a threshold here and change the tab there, which a modal window
    would forbid. It owns no pipeline state — :meth:`apply_to` is the only way
    anything set here leaves the window, and only when asked for.
    """

    #: The user pressed **Use these settings**; the window's settings are ready
    #: for :meth:`apply_to`. Carries nothing, because the receiver holds the
    #: ``Params`` they belong in and this window does not.
    settings_accepted = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Spike and burst viewer")
        # A dialog gets a bare frame on most platforms; this is a workspace the
        # user will want beside the main window, minimised and resized.
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(1000, 640)

        self._dat: np.ndarray | None = None
        self._raw_channels: np.ndarray | None = None
        self._fs = 25000.0
        self._duration_s = 0.0
        self._spike_times: dict[int, dict[str, np.ndarray]] = {}
        self._waveforms: dict[int, dict[str, np.ndarray]] = {}
        self._spike_thresholds: dict[int, dict[str, float]] = {}
        #: Channel IDs the spikes are indexed against — the raw recording's when
        #: detection ran here, the spike file's when one was loaded. Kept apart
        #: from the raw channels so a mismatch between the two is detectable
        #: rather than silently plotting one channel's spikes on another's trace.
        self._spike_channels: np.ndarray | None = None
        #: Bandpassed traces, most-recently-used last. Bounded because a
        #: filtered channel is the same size as a raw one — keeping all 64 of a
        #: ten-minute recording would quietly hold four gigabytes.
        self._filtered: dict[int, np.ndarray] = {}
        #: Each cached channel's robust noise — see _channel_noise.
        self._noise: dict[int, float] = {}
        #: Seconds for every sample, built once per recording and shared by
        #: every channel's curve — 60 MB on a long recording, and the same 60
        #: MB whichever channel is on screen.
        self._time_axis: np.ndarray | None = None
        self._trace_signature: tuple | None = None
        #: Methods a detection has just produced that were not there before, to
        #: be ticked when the pickers are next rebuilt.
        self._newly_detected: set[str] = set()
        self._announce_new_methods = True
        #: Every method this window has seen, in first-seen order. Colours are
        #: assigned from it, so they survive a re-detection.
        self._method_order: list[str] = []
        self._coords: np.ndarray | None = None
        #: Burst results, keyed by the spike method they were detected from.
        self._bursts_by_method: dict[str, tuple] = {}
        self._workers: list[_Worker] = []
        #: True while one navigation is updating the widgets that describe it,
        #: so the scrollbar moving the spin box does not move the scrollbar.
        self._syncing = False
        self._started_at = time.monotonic()
        #: The Bursts tab's own time window, in seconds. Separate from the
        #: traces' — see _navigate_bursts.
        self._burst_start = 0.0
        self._burst_length = 0.0
        #: The last threshold sweep, and what it covered.
        self._sweep_result: list = []
        self._sweep_scope = ""

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_views())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 1000])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_status_bar(), 0)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 6, 0)

        column.addWidget(self._build_recording_box())
        column.addWidget(self._build_detection_box())
        column.addWidget(self._build_burst_box())
        column.addWidget(self._build_view_box())

        # The two things you do when you are done here, together at the bottom:
        # one keeps the work, the other keeps the settings that produced it.
        # Saving used to be a small button up among the detection controls,
        # where it read as part of setting a detection up rather than as the
        # step that commits it — and nothing said that bursts detected
        # afterwards were not in the file yet.
        self._save_btn = QPushButton("Save spikes and bursts…")
        self._save_btn.setObjectName("primary")
        self._save_btn.setEnabled(False)
        self._save_tooltip = (
            "Write everything detected here to a .npz file beside the "
            "recording: spikes, their waveforms, and the bursts for each spike "
            "method they were run on. Opening the same recording again picks it "
            "up automatically, so work worth minutes is not repeated — and the "
            "file is the one the pipeline reads, so a run can start from step 2 "
            "on it.")
        self._save_btn.setToolTip(self._save_tooltip)
        self._save_btn.clicked.connect(self._on_save_spikes)

        self._accept_btn = QPushButton("Use these settings")
        self._accept_btn.setObjectName("primary")
        self._accept_btn.setToolTip(
            "Copy the detection and burst settings in this window back to the "
            "Spike detection tab. Nothing on disk changes — the next run uses "
            "them, the files already detected are untouched.")
        self._accept_btn.clicked.connect(self.settings_accepted.emit)
        column.addStretch()

        area = scrollable(panel)
        # Wide enough that the settings column never needs a *horizontal*
        # scrollbar: a form that scrolls sideways hides the field labels, which
        # is the one part of it that has to stay readable.
        area.setMinimumWidth(panel.sizeHint().width() + 24)
        area.setMaximumWidth(460)

        # The two buttons sit *below* the scroll area rather than at the end of
        # it. At the end of a scrolling column they are below the fold on any
        # window short enough to scroll — which is every window, since the
        # settings above them are long — so the two things you press when you
        # are finished were the two things you had to go looking for.
        holder = QWidget()
        holder.setMaximumWidth(460)
        stack = QVBoxLayout(holder)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(6)
        stack.addWidget(area, 1)
        stack.addWidget(self._save_btn, 0)
        stack.addWidget(self._accept_btn, 0)
        return holder

    def _build_status_bar(self) -> QWidget:
        """The one line that says what the window is doing, always in view.

        It used to sit under the settings, inside the column that scrolls —
        which put it below the fold on any window short enough to need
        scrolling, so "Loading…" was invisible during exactly the minute it was
        there to explain. Across the bottom of the window it cannot scroll away.
        """
        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)

        self._status = QLabel("Open a raw recording, a detected spike file, or both.")
        self._status.setWordWrap(True)
        # Detection counts channels, so it gets a percentage and a time; reading
        # a recording is one h5py call that reports nothing until it returns, so
        # it gets a busy bar. A fake percentage on the second would be worse
        # than none — see _on_progress.
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(240)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)

        row.addWidget(self._status, 1)
        row.addWidget(self._progress, 0)
        return bar

    def _build_recording_box(self) -> QGroupBox:
        box = QGroupBox("Recording")
        form = QFormLayout(box)

        self._raw_path = QLineEdit()
        self._raw_path.setPlaceholderText("raw recording (.mat / .h5 / .raw)")
        self._raw_browse = QPushButton("Browse…")
        pin_width(self._raw_browse, 74)
        self._raw_browse.clicked.connect(self._on_browse_raw)
        form.addRow("Raw data", _row(self._raw_path, self._raw_browse))

        self._spikes_path = QLineEdit()
        self._spikes_path.setPlaceholderText("…_spikes.mat or .npz (optional)")
        self._spikes_browse = QPushButton("Browse…")
        pin_width(self._spikes_browse, 74)
        self._spikes_browse.clicked.connect(self._on_browse_spikes)
        self._spikes_path.setToolTip(
            "Spikes a run already detected. Leave empty and detect here "
            "instead — either way the traces come from the raw file above.")
        form.addRow("Detected spikes", _row(self._spikes_path, self._spikes_browse))

        self._layout_combo = QComboBox()
        self._layout_combo.addItems(_LAYOUTS)
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)
        form.addRow("Channel layout", self._layout_combo)

        self._channel_combo = QComboBox()
        self._channel_combo.currentIndexChanged.connect(self._refresh)
        form.addRow("Channel", self._channel_combo)

        self._array_map = _ArrayMap()
        self._array_map.pick = self._pick_channel
        form.addRow(self._array_map)

        # Which method the map is coloured by is a real question, not a detail:
        # a permissive threshold paints the whole array bright and a strict one
        # paints it dark, and the map is how a dead or a runaway electrode gets
        # noticed. Separate from the ticked methods, because the map shows one
        # at a time whatever is ticked for the trace.
        self._map_metric = QComboBox()
        self._map_metric.addItems(self.MAP_METRICS)
        self._map_metric.currentIndexChanged.connect(self._refresh)
        self._map_metric.setToolTip(
            "What the map's colours mean. Firing rate finds the dead and the "
            "runaway electrodes; SNR — the median spike depth over the noise "
            "it was detected against — finds the ones where the spikes are "
            "barely clearing the threshold. Note that SNR cannot come out "
            "below the threshold multiplier that produced it.")
        form.addRow("Colour by", self._map_metric)

        self._rate_method_combo = QComboBox()
        self._rate_method_combo.currentIndexChanged.connect(self._refresh)
        self._rate_method_combo.setToolTip(
            "Which method's spikes the colours are measured from — here and on "
            "the array map on the Waveforms tab. Defaults to the first ticked "
            "method.")
        form.addRow("Measured from", self._rate_method_combo)

        # Several at once, each in its own colour: the question a detected
        # recording actually raises is which method is right, and that is
        # answered by seeing where two of them disagree on the same trace —
        # not by switching between them and remembering.
        self._method_list = QListWidget()
        self._method_list.setMaximumHeight(96)
        self._method_list.itemChanged.connect(self._on_methods_changed)
        self._method_list.setToolTip(
            "Tick the methods to mark on the trace; each gets its own colour. "
            "A method that finds far more than the others on the same trace is "
            "the finding, not a display setting.\n\nThe waveform, array-map "
            "and burst views describe one method at a time — the first ticked.")
        form.addRow("Spike methods", self._method_list)
        return box

    def _build_detection_box(self) -> QGroupBox:
        box = QGroupBox("Spike detection")
        form = QFormLayout(box)

        self._thresholds = QLineEdit("3, 4, 5")
        self._thresholds.setToolTip(
            "Relative thresholds, as multiples of the median absolute "
            "deviation below the median. Detection runs each of them, so "
            "several can be compared on one trace.")
        form.addRow("Relative thresholds", self._thresholds)

        self._wavelets = QListWidget()
        self._wavelets.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._wavelets.setMaximumHeight(78)
        self._wavelets.addItems(_WAVELETS)
        self._wavelets.item(0).setSelected(True)
        form.addRow("Wavelets", self._wavelets)

        self._detect_channel_btn = QPushButton("Detect on this channel")
        self._detect_channel_btn.setToolTip(
            "Re-run detection on the channel shown, with the settings above. "
            "Seconds rather than minutes, so a threshold can be tried, looked "
            "at, and tried again.")
        self._detect_channel_btn.clicked.connect(lambda: self._detect(all_channels=False))
        self._detect_all_btn = QPushButton("Detect on all channels")
        self._detect_all_btn.setToolTip(
            "Detection over the whole array — what the array map and the burst "
            "detection below need. Minutes on a long recording.")
        self._detect_all_btn.clicked.connect(lambda: self._detect(all_channels=True))
        for button in (self._detect_channel_btn, self._detect_all_btn):
            button.setEnabled(False)
        form.addRow(self._detect_channel_btn)
        form.addRow(self._detect_all_btn)

        # Opening a recording and being shown an empty plot with a Detect
        # button under it makes the first thing you do every time into a chore.
        # A threshold pass is cheap — one filter per channel, shared by every
        # threshold in the box — so the window opens on spikes and the
        # question becomes whether they are the right ones. Wavelets are left
        # out on purpose: they are the slow part, and choosing them is a
        # decision, not a default.
        self._auto_detect = QCheckBox("Detect with the thresholds above on load")
        self._auto_detect.setChecked(True)
        self._auto_detect.setToolTip(
            "As soon as a recording is loaded, run threshold detection over "
            "every channel so there is something to look at. Turn off for very "
            "long recordings, or when you only want the spikes from a file.")
        form.addRow(self._auto_detect)

        advanced = AdvancedSection("Filter, refractory period and wavelet cost")
        self._filter_low = _spin(0, 20000, 0, 600, " Hz")
        self._filter_high = _spin(0, 50000, 0, 8000, " Hz")
        self._ref_period = _spin(0, 100, 1, 2.0, " ms")
        self._cost = _spin(-10, 10, 2, -0.12, step=0.01)
        advanced.form().addRow("Low-pass cutoff", self._filter_low)
        advanced.form().addRow("High-pass cutoff", self._filter_high)
        advanced.form().addRow("Refractory period", self._ref_period)
        advanced.form().addRow("Wavelet cost", self._cost)
        # The refractory period is what the ISI histogram is judged against, so
        # changing it has to redraw even though no detection has re-run.
        self._ref_period.valueChanged.connect(self._refresh)
        self._filter_low.valueChanged.connect(self._invalidate_filtered)
        self._filter_high.valueChanged.connect(self._invalidate_filtered)
        form.addRow(advanced)
        return box

    def _build_burst_box(self) -> QGroupBox:
        box = QGroupBox("Burst detection")
        form = QFormLayout(box)

        self._nb_min_spikes = _int_spin(1, 1000, 10)
        self._nb_min_channels = _int_spin(1, 1000, 3)
        self._nb_auto_isi = QCheckBox("Set ISIₙ threshold automatically")
        self._nb_auto_isi.setChecked(True)
        self._nb_isi = _spin(0.0001, 100, 4, 0.1, " s")
        self._nb_auto_isi.toggled.connect(lambda on: self._nb_isi.setEnabled(not on))
        self._nb_isi.setEnabled(False)
        form.addRow("Network: min spikes", self._nb_min_spikes)
        form.addRow("Network: min channels", self._nb_min_channels)
        form.addRow(self._nb_auto_isi)
        form.addRow("Network: ISIₙ threshold", self._nb_isi)

        self._sc_min_spikes = _int_spin(1, 1000, 5)
        self._sc_auto_isi = QCheckBox("Set channel ISI threshold automatically")
        self._sc_auto_isi.setChecked(True)
        self._sc_isi = _spin(0.0001, 100, 4, 0.1, " s")
        self._sc_auto_isi.toggled.connect(lambda on: self._sc_isi.setEnabled(not on))
        self._sc_isi.setEnabled(False)
        form.addRow("Channel: min spikes", self._sc_min_spikes)
        form.addRow(self._sc_auto_isi)
        form.addRow("Channel: ISI threshold", self._sc_isi)

        self._burst_btn = QPushButton("Detect bursts")
        self._burst_btn.setEnabled(False)
        self._burst_btn.setToolTip(
            "Runs both burst detectors over every channel's spikes — the ones "
            "loaded or detected above, whichever this window is holding.")
        self._burst_btn.clicked.connect(self._detect_bursts)
        form.addRow(self._burst_btn)
        return box

    def _build_view_box(self) -> QGroupBox:
        box = QGroupBox("View")
        form = QFormLayout(box)

        # The numbers behind the trace's own scrollbar and wheel: the way to
        # ask for exactly 1.5 seconds from 240, rather than approximately it.
        self._window_start = _spin(0, 1e6, 3, 0.0, " s")
        self._window_start.valueChanged.connect(self._on_window_typed)
        self._window_length = _spin(0.002, 3600, 3, 2.0, " s")
        self._window_length.valueChanged.connect(self._on_window_typed)

        form.addRow("Window start", self._window_start)
        form.addRow("Window length", self._window_length)

        self._solid_markers = QCheckBox("Fill the spike markers")
        self._solid_markers.setToolTip(
            "Filled markers are easier to pick out when zoomed in on a few "
            "spikes; open ones stay legible on a busy channel seen whole, "
            "where filled ones merge into a band. Neither is right at both "
            "zooms, so it is a switch.")
        self._solid_markers.toggled.connect(self._refresh)
        form.addRow(self._solid_markers)

        self._show_raw = QCheckBox("Show unfiltered trace behind")
        self._show_raw.setToolTip(
            "Draw the raw trace under the filtered one. The Filtering tab puts "
            "them side by side on their own scales, and adds the spectrum — "
            "this is for checking one against the other in place.")
        self._show_raw.toggled.connect(self._refresh)
        form.addRow(self._show_raw)

        # The Bursts tab navigates on its own, which is right most of the time
        # — but the one workflow that wants them joined is the important one:
        # find a burst on the array, then look at what the trace was doing
        # inside it.
        self._follow_trace = QCheckBox("Bursts follow the trace window")
        self._follow_trace.toggled.connect(self._on_follow_trace)
        self._follow_trace.setToolTip(
            "Keep the Bursts tab showing the same stretch as the Traces tab, "
            "so a burst found on the raster can be looked at as a trace "
            "without hunting for it again. Off, each tab keeps its own window.")
        form.addRow(self._follow_trace)

        self._max_waveforms = _int_spin(10, 5000, 200)
        self._max_waveforms.valueChanged.connect(self._refresh)
        self._raster_bin = _spin(0.001, 10, 3, 0.1, " s")
        self._raster_bin.valueChanged.connect(self._refresh)
        # Measured in noise, not volts, so one setting suits every recording
        # whatever its units and however loud it is.
        # Half a noise unit apart: enough to tell three methods' markers apart
        # under one spike, small enough that the stack does not stretch the
        # plot's vertical range much. The markers are part of what the y axis
        # fits, deliberately — excluding them would keep the trace's scale but
        # let the lowest method's marks fall off the bottom of the view, which
        # is the same disappearing act as before by another route.
        self._marker_offset = _spin(0.0, 10.0, 1, 0.5, step=0.5)
        self._marker_offset.setToolTip(
            "How far apart to stack the methods' markers under a spike, in "
            "multiples of the channel's noise. Zero puts them all on the spike "
            "itself, where whichever is drawn last hides the rest.")
        self._marker_offset.valueChanged.connect(self._refresh)

        advanced = AdvancedSection("Plot detail")
        advanced.form().addRow("Marker spacing (× noise)", self._marker_offset)
        advanced.form().addRow("Waveforms drawn", self._max_waveforms)
        advanced.form().addRow("Array rate bin width", self._raster_bin)
        form.addRow(advanced)
        return box

    def _build_views(self) -> QWidget:
        self._tabs = QTabWidget()
        self._trace_view = _TraceView()
        self._filter_canvas = _FilterCanvas()
        self._quality_canvas = _QualityCanvas()
        self._sweep_canvas = _SweepCanvas()
        self._burst_view = _BurstView()

        self._trace_view.range_changed.connect(self._on_view_range)

        trace_page = QWidget()
        trace_layout = QVBoxLayout(trace_page)
        trace_layout.setContentsMargins(0, 0, 0, 0)
        trace_layout.setSpacing(2)
        trace_layout.addWidget(self._build_trace_toolbar(), 0)
        trace_layout.addWidget(self._trace_view, 1)
        trace_layout.addWidget(self._build_trace_scrollbar(), 0)

        self._burst_view.range_changed.connect(self._on_burst_view_range)
        burst_page = QWidget()
        burst_layout = QVBoxLayout(burst_page)
        burst_layout.setContentsMargins(0, 0, 0, 0)
        burst_layout.setSpacing(2)
        burst_layout.addWidget(self._build_burst_toolbar(), 0)
        burst_layout.addWidget(self._burst_view, 1)
        burst_layout.addWidget(self._build_burst_scrollbar(), 0)

        self._tabs.addTab(trace_page, "  Traces  ")
        self._tabs.addTab(self._filter_canvas, "  Filtering  ")
        self._tabs.addTab(self._quality_canvas, "  Waveforms and quality  ")

        sweep_page = QWidget()
        sweep_layout = QVBoxLayout(sweep_page)
        sweep_layout.setContentsMargins(0, 0, 0, 0)
        sweep_layout.setSpacing(2)
        sweep_layout.addWidget(self._build_sweep_toolbar(), 0)
        sweep_layout.addWidget(self._sweep_canvas, 1)
        self._tabs.addTab(sweep_page, "  Threshold sweep  ")
        self._tabs.addTab(burst_page, "  Bursts  ")
        self._tabs.currentChanged.connect(self._refresh)
        return self._tabs

    def _build_trace_toolbar(self) -> QWidget:
        bar, self._window_label, self._box_zoom = _time_toolbar(
            on_zoom=self._zoom,
            on_step=self._step_window,
            on_jump=self._jump_to_next_spike,
            on_whole=lambda: self._navigate(0.0, max(self._duration_s, 0.01)),
            on_save=self._save_current_figure,
            jump_label="Next spike ▶|",
            jump_tip="Move to the first spike this window is not already "
                     "showing. On a sparse channel, scrolling to find one by "
                     "hand is most of the work.",
            box_zoom_tip="Drag a rectangle across the trace to zoom to the "
                         "stretch it covers. Only the width is used — the "
                         "vertical range always fits the trace. Turn off to go "
                         "back to dragging the trace to pan it.",
            noun="trace")
        self._box_zoom.toggled.connect(self._trace_view.set_box_zoom)
        return bar

    def _build_sweep_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 2, 4, 0)

        self._sweep_from = _spin(0.5, 50, 2, 2.0)
        self._sweep_to = _spin(0.5, 50, 2, 8.0)
        self._sweep_step = _spin(0.05, 5, 2, 0.5)
        for widget in (self._sweep_from, self._sweep_to, self._sweep_step):
            widget.setFixedWidth(74)
        row.addWidget(QLabel("From"))
        row.addWidget(self._sweep_from)
        row.addWidget(QLabel("to"))
        row.addWidget(self._sweep_to)
        row.addWidget(QLabel("in steps of"))
        row.addWidget(self._sweep_step)
        row.addSpacing(10)

        self._sweep_channel_btn = QPushButton("Sweep this channel")
        self._sweep_channel_btn.setObjectName("primary")
        self._sweep_channel_btn.setToolTip(
            "Detect at every threshold in the range on the channel shown, and "
            "plot what changes. About half a second on a ten-minute recording: "
            "all the thresholds share one filtering pass.")
        self._sweep_channel_btn.clicked.connect(lambda: self._sweep(all_channels=False))
        self._sweep_all_btn = QPushButton("Sweep every channel")
        self._sweep_all_btn.setToolTip(
            "The same over the whole array, which also shows how many channels "
            "stay active as the threshold rises. Tens of seconds.")
        self._sweep_all_btn.clicked.connect(lambda: self._sweep(all_channels=True))
        for button in (self._sweep_channel_btn, self._sweep_all_btn):
            button.setEnabled(False)
            pin_width(button, button.sizeHint().width())
            row.addWidget(button)

        row.addStretch()
        self._sweep_pick = _spin(0.5, 50, 2, 4.0)
        self._sweep_pick.setFixedWidth(74)
        use = QPushButton("Use this threshold")
        use.setToolTip(
            "Put this threshold in the detection settings on the left, "
            "replacing what is there. Nothing is re-detected until you ask.")
        use.clicked.connect(self._on_use_swept_threshold)
        row.addWidget(self._sweep_pick)
        row.addWidget(use)

        save = QPushButton("Save figure…")
        save.clicked.connect(self._save_current_figure)
        row.addWidget(save)
        return bar

    def _sweep_multipliers(self) -> list[float]:
        """The thresholds to try, low to high, inclusive of both ends."""
        low, high = self._sweep_from.value(), self._sweep_to.value()
        step = max(self._sweep_step.value(), 0.01)
        if high < low:
            low, high = high, low
        # Rounded because these become method names — "thr4p5" and not
        # "thr4p4999999999" — and because a sweep is read off its axis.
        count = int(round((high - low) / step)) + 1
        return [round(low + i * step, 4) for i in range(max(count, 1))]

    def _sweep(self, *, all_channels: bool) -> None:
        if self._dat is None:
            return
        multipliers = self._sweep_multipliers()
        if len(multipliers) < 2:
            self._status.setText("A sweep needs at least two thresholds.")
            return
        indices = list(range(self._dat.shape[1])) if all_channels \
            else [self._current_channel()]
        params = self._detection_params(thresholds_only=True)
        params.thresholds = multipliers
        self._sweep_scope = ("every channel" if all_channels
                             else f"channel {self._channel_name(indices[0])}")
        self._run(_SweepWorker(self._dat, self._raw_channels, self._fs, params,
                               indices, multipliers, self._duration_s,
                               self._ref_period.value(), _MIN_ACTIVE_RATE),
                  self._on_swept,
                  f"Sweeping {len(multipliers)} thresholds "
                  f"({multipliers[0]:g}–{multipliers[-1]:g} MAD) over "
                  f"{len(indices)} channel(s)…")

    def _on_swept(self, points) -> None:
        self._sweep_result = points
        self._tabs.setCurrentIndex(3)
        knee = knee_threshold(points)
        # Start the picker somewhere defensible rather than at whatever it was.
        if knee is not None:
            self._sweep_pick.setValue(knee)
        span = f"{points[0].n_spikes} spikes at {points[0].multiplier:g} MAD " \
               f"down to {points[-1].n_spikes} at {points[-1].multiplier:g}"
        self._finished(
            f"Swept {len(points)} thresholds over {self._sweep_scope}: {span}."
            + ("" if knee is None else
               f" The count stops falling steeply at {knee:g} MAD."))

    def _on_use_swept_threshold(self) -> None:
        value = self._sweep_pick.value()
        self._thresholds.setText(f"{value:g}")
        self._status.setText(
            f"Detection threshold set to {value:g} MAD. Detect on this channel "
            f"or on all of them to apply it.")

    def _draw_sweep(self) -> None:
        if self._dat is None:
            self._sweep_canvas.message(
                "Open a raw recording to sweep its thresholds.")
            return
        if not self._sweep_result:
            self._sweep_canvas.message(
                "Set a range above and press Sweep to see how the threshold "
                "changes what is detected.")
            return
        self._sweep_canvas.render(
            self._sweep_result, f"Threshold sweep · {self._sweep_scope}",
            _numbers(self._thresholds.text()),
            knee_threshold(self._sweep_result))

    def _build_burst_toolbar(self) -> QWidget:
        bar, self._burst_label, self._burst_box_zoom = _time_toolbar(
            on_zoom=self._zoom_bursts,
            on_step=self._step_bursts,
            on_jump=self._jump_to_next_burst,
            on_whole=lambda: self._navigate_bursts(0.0, max(self._duration_s, 0.01)),
            on_save=self._save_current_figure,
            jump_label="Next burst ▶|",
            jump_tip="Move to the first network burst this window is not "
                     "already showing. On a long recording, finding the next "
                     "one by dragging is most of the work.",
            box_zoom_tip="Drag a rectangle across the raster to zoom to the "
                         "stretch it covers. Only the width is used, so the "
                         "channels stay as they are.",
            noun="raster")
        self._burst_box_zoom.toggled.connect(self._burst_view.set_box_zoom)
        return bar

    def _build_burst_scrollbar(self) -> QWidget:
        self._burst_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._burst_scrollbar.setSizePolicy(QSizePolicy.Policy.Expanding,
                                            QSizePolicy.Policy.Fixed)
        self._burst_scrollbar.valueChanged.connect(self._on_burst_scrollbar)
        return self._burst_scrollbar

    def _build_trace_scrollbar(self) -> QWidget:
        """A scrollbar under the trace, in milliseconds of recording.

        The mouse moves are faster, but a scrollbar is the one control that
        says at a glance *where in the recording you are and how much of it you
        are seeing* — and it is what someone looks for first.
        """
        self._scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._scrollbar.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Fixed)
        self._scrollbar.valueChanged.connect(self._on_scrollbar)
        return self._scrollbar

    def _on_scrollbar(self, value: int) -> None:
        if self._syncing:
            return
        self._navigate(value / 1000.0, self._window_length.value())

    def _sync_scrollbar(self) -> None:
        """Point the scrollbar and the window label at the current view."""
        start, length = self._window_start.value(), self._window_length.value()
        self._syncing = True
        try:
            self._scrollbar.setRange(0, max(0, int((self._duration_s - length) * 1000)))
            self._scrollbar.setPageStep(max(1, int(length * 1000)))
            self._scrollbar.setSingleStep(max(1, int(length * 250)))
            self._scrollbar.setValue(int(start * 1000))
        finally:
            self._syncing = False
        # Decimals to suit the span: three of them are what tells one spike
        # from the next at 20 ms, and clutter at 600 s.
        places = 0 if length >= 100 else 1 if length >= 10 else 2 if length >= 1 else 3
        self._window_label.setText(
            f"{start:.{places}f}–{start + length:.{places}f} s "
            f"of {self._duration_s:.0f} s" if self._duration_s else "")

    def _navigate(self, start: float, length: float) -> None:
        """Move the trace window, from wherever the request came from.

        One route for the wheel, the drag, the buttons, the scrollbar and the
        spin boxes, so they cannot disagree — and one redraw at the end of it
        rather than one per widget that changes.

        It is also the only place the window is held inside the recording. A
        drag that runs off the end, or a zoom wider than the whole file, is a
        normal thing to do with a mouse and has to stop at the edge rather than
        leaving the view somewhere with no data in it.
        """
        start, length = self._clamp_window(start, length)
        self._set_window_widgets(start, length)
        self._trace_view.set_range(start, start + length)
        if self._follow_trace.isChecked():
            self._navigate_bursts(start, length)
        self._refresh()

    def _clamp_window(self, start: float, length: float) -> tuple[float, float]:
        duration = max(self._duration_s, 0.002)
        length = float(np.clip(length, 0.002, duration))
        return float(np.clip(start, 0.0, duration - length)), length

    def _set_window_widgets(self, start: float, length: float) -> None:
        self._syncing = True
        try:
            self._window_length.setValue(length)
            self._window_start.setValue(start)
        finally:
            self._syncing = False

    def _on_view_range(self, t0: float, t1: float) -> None:
        """The plot was panned or zoomed; catch the rest of the window up.

        Deliberately not routed through :meth:`_navigate`: that would set the
        plot's range back from the numbers it just reported, and a rounding
        difference between the two would fight the user's own drag.
        """
        start, length = self._clamp_window(t0, max(t1 - t0, 0.002))
        self._set_window_widgets(start, length)
        self._sync_scrollbar()
        if self._follow_trace.isChecked():
            self._navigate_bursts(start, length)

    def _on_burst_scrollbar(self, value: int) -> None:
        if self._syncing:
            return
        self._navigate_bursts(value / 1000.0, self._burst_length)

    def _sync_burst_scrollbar(self) -> None:
        start, length = self._burst_start, self._burst_length
        self._syncing = True
        try:
            self._burst_scrollbar.setRange(
                0, max(0, int((self._duration_s - length) * 1000)))
            self._burst_scrollbar.setPageStep(max(1, int(length * 1000)))
            self._burst_scrollbar.setSingleStep(max(1, int(length * 250)))
            self._burst_scrollbar.setValue(int(start * 1000))
        finally:
            self._syncing = False
        places = 0 if length >= 100 else 1 if length >= 10 else 2 if length >= 1 else 3
        self._burst_label.setText(
            f"{start:.{places}f}–{start + length:.{places}f} s "
            f"of {self._duration_s:.0f} s" if self._duration_s else "")

    def _navigate_bursts(self, start: float, length: float,
                         *, from_view: bool = False) -> None:
        """Move the burst window.

        The bursts keep a window of their own rather than sharing the traces':
        the two views answer different questions at different scales, and being
        dragged to a 20 ms slice of trace every time you looked at a raster
        would make the raster useless. **Follow the trace window** on the left
        joins them for anyone who wants them joined.
        """
        self._burst_start, self._burst_length = self._clamp_window(start, length)
        if not from_view:
            self._burst_view.set_range(self._burst_start,
                                       self._burst_start + self._burst_length)
        self._sync_burst_scrollbar()

    def _on_burst_view_range(self, t0: float, t1: float) -> None:
        self._navigate_bursts(t0, max(t1 - t0, 0.002), from_view=True)

    def _zoom_bursts(self, factor: float) -> None:
        centre = self._burst_start + self._burst_length / 2
        length = max(0.002, min(self._burst_length * factor,
                                max(self._duration_s, 0.002)))
        self._navigate_bursts(centre - length / 2, length)

    def _step_bursts(self, direction: int) -> None:
        self._navigate_bursts(self._burst_start + direction * self._burst_length,
                              self._burst_length)

    def _jump_to_next_burst(self) -> None:
        """Move to the first network burst the window is not already showing.

        Zooms in from the whole-recording view for the same reason the spike
        jump does: with everything on screen, "next" would always be "none".
        """
        shown = self._bursts_for_view()
        if shown is None:
            self._status.setText("No bursts detected yet.")
            return
        starts = np.asarray(shown[1][0], dtype=float).reshape(-1, 2)[:, 0]
        if starts.size == 0:
            self._status.setText("No network bursts to jump to.")
            return
        starts = starts / self._fs
        length = self._burst_length
        if length >= self._duration_s - 1e-6:
            length = _inspect_window(_INSPECT_BURST_S, self._duration_s)
            target = starts.min()
        else:
            after = starts[starts > self._burst_start + length]
            if after.size == 0:
                self._status.setText("No further network bursts.")
                return
            target = after.min()
        self._navigate_bursts(target - length / 4, length)

    def _zoom(self, factor: float) -> None:
        length = self._window_length.value()
        start = self._window_start.value()
        centre = start + length / 2
        new_length = max(0.002, min(length * factor, max(self._duration_s, 0.002)))
        self._navigate(centre - new_length / 2, new_length)

    def _save_current_figure(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the figure", "", "PNG image (*.png);;SVG image (*.svg);;"
            "PDF document (*.pdf)")
        if not path:
            return
        canvas = self._current_canvas()
        if isinstance(canvas, _PgView):
            canvas.export(path)
        else:
            canvas.figure.savefig(path, dpi=300, bbox_inches="tight")
        self._status.setText(f"Saved {Path(path).name}.")

    # ── Settings in and out ───────────────────────────────────────────────────

    def load_defaults(self, params: Params) -> None:
        """Start from the settings the main window is holding.

        Opening on the tab's own settings is what makes this a *check* of the
        run about to happen rather than a separate tool with its own defaults —
        what you see here is what that run would detect.
        """
        if params.thresholds:
            self._thresholds.setText(", ".join(_number(t) for t in params.thresholds))
        for i in range(self._wavelets.count()):
            item = self._wavelets.item(i)
            item.setSelected(item.text() in params.wname_list)
        cost = params.cost_list[0] if isinstance(params.cost_list, list) \
            else params.cost_list
        self._cost.setValue(float(cost))
        self._filter_low.setValue(params.filter_low_pass)
        self._filter_high.setValue(params.filter_high_pass)
        self._ref_period.setValue(params.ref_period)

        self._nb_min_spikes.setValue(int(params.min_spike_network_burst))
        self._nb_min_channels.setValue(int(params.min_channel_network_burst))
        show_auto_or_value(self._nb_auto_isi, self._nb_isi,
                           params.bakkum_network_burst_isi_n_threshold)
        self._sc_min_spikes.setValue(int(params.single_channel_burst_min_spike))
        show_auto_or_value(self._sc_auto_isi, self._sc_isi,
                           params.single_channel_isi_threshold)

        index = self._layout_combo.findText(params.channel_layout)
        if index >= 0:
            self._layout_combo.setCurrentIndex(index)
        self._default_raw_dir = str(params.raw_data or "")
        self._default_spike_dir = str(params.spike_detected_data
                                      or params.output_data_folder or "")

    def apply_to(self, params: Params) -> None:
        """Write this window's settings into *params*.

        Only the settings a run reads — nothing about which channel or window
        was on screen, which belong to looking rather than to running.
        """
        thresholds = _numbers(self._thresholds.text())
        if thresholds:
            params.thresholds = thresholds
        wavelets = [self._wavelets.item(i).text()
                    for i in range(self._wavelets.count())
                    if self._wavelets.item(i).isSelected()]
        if wavelets:
            params.wname_list = wavelets
        params.cost_list = self._cost.value()
        params.filter_low_pass = self._filter_low.value()
        params.filter_high_pass = self._filter_high.value()
        params.ref_period = self._ref_period.value()

        params.min_spike_network_burst = self._nb_min_spikes.value()
        params.min_channel_network_burst = self._nb_min_channels.value()
        params.bakkum_network_burst_isi_n_threshold = (
            "automatic" if self._nb_auto_isi.isChecked() else self._nb_isi.value())
        params.single_channel_burst_min_spike = self._sc_min_spikes.value()
        params.single_channel_isi_threshold = (
            "automatic" if self._sc_auto_isi.isChecked() else self._sc_isi.value())

    # ── Opening files ─────────────────────────────────────────────────────────

    def _on_browse_raw(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open raw recording", getattr(self, "_default_raw_dir", ""),
            "Raw recordings (*.mat *.h5 *.raw);;All files (*)")
        if path:
            self.open_raw(path)

    def open_raw(self, path: str | Path) -> None:
        """Load raw traces from *path*, in the background."""
        self._raw_path.setText(str(path))
        self._run(_LoadRawWorker(str(path)), self._on_raw_loaded,
                  f"Loading {_describe_file(path)} — reading the traces, "
                  f"this can take a while…")

    def _on_raw_loaded(self, payload) -> None:
        dat, channels, fs = payload
        self._dat, self._raw_channels, self._fs = dat, channels, float(fs)
        self._duration_s = dat.shape[0] / self._fs
        self._filtered.clear()
        self._noise.clear()
        self._time_axis = np.arange(dat.shape[0]) / self._fs
        self._trace_signature = None
        if self._spike_channels is None:
            self._spike_channels = channels
        self._window_start.setMaximum(max(self._duration_s, 1.0))
        # A recording opens on the whole of itself. Landing on the first two
        # seconds of ten minutes says nothing about whether the channel is any
        # good, and leaves the reader to discover the scroll bar before they
        # can find out — where the whole timeline shows the quiet stretches,
        # the bursts and the artefacts at a glance, and zooming in is then a
        # deliberate move towards something already visible.
        self._window_length.setMaximum(max(self._duration_s, 1.0))
        self._navigate(0.0, self._duration_s)
        self._refresh_channels()
        loaded = (f"{Path(self._raw_path.text()).name}: {dat.shape[1]} channels, "
                  f"{self._duration_s:.0f} s at {self._fs:.0f} Hz.")

        # Spikes saved from a previous visit are better than detecting again:
        # they are what was looked at last time, and they cost nothing to read.
        beside = self._suggested_spike_path()
        if not self._spike_times and beside.exists():
            self._finished(f"{loaded} Loading the spikes saved beside it.")
            self.open_spikes(beside)
            return

        if self._should_auto_detect():
            self._finished(loaded)
            self._detect(all_channels=True, thresholds_only=True, automatic=True)
        else:
            self._finished(loaded)

    def _should_auto_detect(self) -> bool:
        """Whether to detect on this recording without being asked.

        Not when the window already holds spikes: those came from a file the
        user chose, and replacing them with a fresh threshold pass would throw
        away the very thing they opened the window to look at.
        """
        return (self._auto_detect.isChecked() and not self._spike_times
                and bool(_numbers(self._thresholds.text())))

    def _on_browse_spikes(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open detected spikes", getattr(self, "_default_spike_dir", ""),
            "Detected spikes (*_spikes.mat *.npz *.mat);;All files (*)")
        if path:
            self.open_spikes(path)

    def open_spikes(self, path: str | Path) -> None:
        """Load a run's detected spikes from *path*, in the background."""
        self._spikes_path.setText(str(path))
        self._run(_LoadSpikesWorker(str(path)), self._on_spikes_loaded,
                  f"Reading {_describe_file(path)}…")

    def _on_spikes_loaded(self, spike_file: SpikeFile) -> None:
        self._spike_times = spike_file.spike_times
        self._waveforms = spike_file.waveforms
        self._spike_thresholds = spike_file.thresholds
        self._method_order = list(spike_file.methods)
        self._noise.clear()   # read off the thresholds this file brought
        self._spike_channels = spike_file.channels
        self._coords = spike_file.coords
        # A file that carries bursts arrives with them shown, rather than
        # asking for a detection that has already been done once.
        self._bursts_by_method = unpack_bursts(spike_file.bursts)
        if self._dat is None:
            # Without traces the sampling rate and duration can only come from
            # the file; with traces they came from the recording itself and are
            # not overwritten, since that is the data actually being plotted.
            self._fs = spike_file.fs
            self._duration_s = spike_file.duration_s or self._duration_s
        self._apply_file_params(spike_file.params)
        self._refresh_channels()

        if self._bursts_by_method and self._burst_length <= 0:
            self._navigate_bursts(0.0, max(self._duration_s, 0.01))

        n_spikes = sum(int(np.size(t)) for per in self._spike_times.values()
                       for t in per.values())
        bursts_note = "" if not self._bursts_by_method else (
            " Bursts came with it for "
            + ", ".join(f"{method} ({len(bursts[0])} network)"
                        for method, bursts in self._bursts_by_method.items()) + ".")
        self._finished(
            f"{spike_file.path.name}: {len(self._spike_times)} channels, "
            f"{n_spikes} spikes across {len(spike_file.methods)} method(s)."
            + bursts_note
            + ("" if self._dat is not None else
               " Open the raw recording to see the traces under them."))
        # Last, because it starts the longer job of the two and its "loading…"
        # has to be the message left on screen.
        self._maybe_find_raw(spike_file.path)

    def _apply_file_params(self, params: dict) -> None:
        """Adopt the detection settings the loaded file was made with.

        A file detected at 6150 Hz shown against controls saying 8000 would
        invite the reader to conclude something about a filter that was never
        applied, so the controls follow the file.
        """
        for key, widget in (("filterLowPass", self._filter_low),
                            ("filterHighPass", self._filter_high),
                            ("refPeriod", self._ref_period)):
            if key in params:
                widget.setValue(float(params[key]))
        if "minSpikeNetworkBurst" in params:
            self._nb_min_spikes.setValue(int(params["minSpikeNetworkBurst"]))
        if "minChannelNetworkBurst" in params:
            self._nb_min_channels.setValue(int(params["minChannelNetworkBurst"]))
        if "singleChannelBurstMinSpike" in params:
            self._sc_min_spikes.setValue(int(params["singleChannelBurstMinSpike"]))

    def _maybe_find_raw(self, spikes_path: Path) -> None:
        """Offer the raw recording that goes with a ``…_spikes.mat``.

        The pipeline names detected files after their recording, so the raw
        file is findable from the spike file plus the configured data folder —
        and a spike viewer with no traces in it is half a viewer.
        """
        if self._dat is not None:
            return
        stem = spikes_path.stem
        if stem.endswith("_spikes"):
            stem = stem[: -len("_spikes")]
        for folder in (getattr(self, "_default_raw_dir", ""), spikes_path.parent):
            if not folder:
                continue
            source = find_raw_file(folder, stem)
            if source is not None:
                self.open_raw(source.path if source.well is None else source)
                return

    # ── Detection ─────────────────────────────────────────────────────────────

    def _detection_params(self, *, thresholds_only: bool = False) -> SpikeDetectionParams:
        wavelets = [] if thresholds_only else [
            self._wavelets.item(i).text()
            for i in range(self._wavelets.count())
            if self._wavelets.item(i).isSelected()]
        return SpikeDetectionParams(
            fs=self._fs,
            thresholds=_numbers(self._thresholds.text()),
            wname_list=wavelets,
            cost_list=[self._cost.value()],
            filter_low_pass=self._filter_low.value(),
            filter_high_pass=self._filter_high.value(),
            ref_period_ms=self._ref_period.value(),
        )

    def _detect(self, *, all_channels: bool, thresholds_only: bool = False,
                automatic: bool = False) -> None:
        if self._dat is None:
            return
        params = self._detection_params(thresholds_only=thresholds_only)
        if not params.thresholds and not params.wname_list:
            self._status.setText("Choose at least one threshold or wavelet "
                                 "to detect with.")
            return
        indices = list(range(self._dat.shape[1])) if all_channels \
            else [self._current_channel()]
        # A detection the user clicked for should show what it found; the pass
        # that runs by itself when a recording opens should not tick three
        # methods over a trace nobody has looked at yet.
        self._announce_new_methods = not automatic
        methods = ", ".join(f"{t:g} MAD" for t in params.thresholds)
        if params.wname_list:
            methods = ", ".join(filter(None, (methods, ", ".join(params.wname_list))))
        self._run(_DetectWorker(self._dat, self._raw_channels, self._fs,
                                params, indices),
                  self._on_detected,
                  f"Detecting spikes on {len(indices)} channel(s) — {methods}…")

    def _on_detected(self, payload) -> None:
        times, waves, thresholds = payload
        before = set(self._methods())
        self._newly_detected = {name for per in times.values() for name in per
                                if name not in before} \
            if self._announce_new_methods else set()
        if not self._channels_agree():
            # Spikes loaded from a file are indexed against that file's channel
            # list. When it is the same list — the usual case, a run's own
            # output beside its own raw data — a channel detected here replaces
            # that channel and the rest of the file stands. When it is not, the
            # two are about different recordings, and keeping both would plot
            # one recording's spikes under the other's trace.
            self._spike_times, self._waveforms, self._spike_thresholds = {}, {}, {}
            self._method_order = []
        self._spike_channels = self._raw_channels
        # Merged per method, not per channel. ``dict.update`` would swap a
        # channel's whole method dict for the new one, so detecting bior1.5 on
        # a channel that already had thr4 and thr5 silently dropped both — the
        # rows for them then read "(0)", and which methods existed depended on
        # whichever channel happened to be first.
        for store, incoming in ((self._spike_times, times),
                                (self._waveforms, waves),
                                (self._spike_thresholds, thresholds)):
            for channel, per_method in incoming.items():
                store.setdefault(channel, {}).update(per_method)
        self._remember_methods(name for per in times.values() for name in per)
        # The noise is read off the thresholds, so a detection that produces new
        # ones invalidates it. Without this the value cached before detection —
        # measured off the trace, because there were no thresholds to read yet —
        # would be kept and quietly used instead of the detector's own.
        self._noise.clear()
        # Bursts describe the spikes they were found in; a fresh detection
        # makes them describe something that is no longer on screen.
        self._bursts_by_method = {}
        self._refresh_channels()
        detected = sum(int(np.size(t)) for per in times.values() for t in per.values())
        self._finished(f"Detected {detected} spikes on {len(times)} channel(s) "
                       f"across {len(self._methods())} method(s).")

    def _suggested_spike_path(self) -> Path:
        """Where a save would go by default: beside the recording it came from.

        Named the way the pipeline names its own, so the file it writes and the
        file this writes are interchangeable — and so opening the recording
        again finds it without being told where to look.
        """
        raw = Path(self._raw_path.text() or "spikes")
        return raw.with_name(f"{raw.stem}_spikes.npz")

    def _on_save_spikes(self) -> None:
        if not self._spike_times:
            self._status.setText("Nothing detected to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save detected spikes", str(self._suggested_spike_path()),
            "Detected spikes (*.npz)")
        if not path:
            return
        channels = self._spike_channels if self._spike_channels is not None \
            else self._raw_channels
        try:
            save_spike_times_npz(
                path, self._spike_times,
                np.asarray(channels if channels is not None else []),
                self._fs,
                params=self._saved_params(),
                duration_s=self._duration_s or None,
                # Saved with the detection, because a file of times alone
                # reopens with no waveform, no amplitude and no threshold to
                # draw — which is most of what this window is for.
                waveforms=self._waveforms,
                thresholds=self._spike_thresholds,
                # Burst detection too, when it has been run: it takes as long
                # as the spikes did and describes the same recording.
                bursts=pack_bursts(self._bursts_by_method) or None,
            )
        except Exception as exc:   # noqa: BLE001 - reported to the user
            self._status.setText(f"Could not save: {exc}")
            return
        self._spikes_path.setText(path)
        size = Path(path).stat().st_size
        held = (f", with bursts for {', '.join(self._bursts_by_method)}"
                if self._bursts_by_method else ", with no bursts run yet")
        self._status.setText(
            f"Saved {Path(path).name} ({size / 1e6:.1f} MB){held}. Opening "
            f"{Path(self._raw_path.text()).name} again will load it.")

    def _saved_params(self) -> dict:
        """The settings this detection was made with, written beside the file."""
        params = self._detection_params()
        return {
            "thresholds": params.thresholds,
            "wname_list": params.wname_list,
            "costList": params.cost_list,
            "filterLowPass": params.filter_low_pass,
            "filterHighPass": params.filter_high_pass,
            "refPeriod": params.ref_period_ms,
            "fs": self._fs,
            "duration": self._duration_s,
            "savedBy": "MEA-NAP spike and burst viewer",
            "minSpikeNetworkBurst": self._nb_min_spikes.value(),
            "minChannelNetworkBurst": self._nb_min_channels.value(),
            "bakkumNetworkBurstISInThreshold": (
                "automatic" if self._nb_auto_isi.isChecked()
                else self._nb_isi.value()),
            "singleChannelBurstMinSpike": self._sc_min_spikes.value(),
            "singleChannelISIThreshold": (
                "automatic" if self._sc_auto_isi.isChecked()
                else self._sc_isi.value()),
        }

    def _detect_bursts(self) -> None:
        # Every method on screen, not just the one the tab is showing: which
        # spikes you feed a burst detector decides what it finds, and doing
        # them together is what lets the saved file say which is which.
        methods = self._selected_methods() or [self._primary_method()]
        by_method = {name: self._spikes_for_method(name)
                     for name in methods if name}
        by_method = {name: spikes for name, spikes in by_method.items() if spikes}
        if not by_method:
            self._status.setText("No spikes to burst-detect yet.")
            return
        spikes = next(iter(by_method.values()))
        settings = {
            "network_min_spikes": self._nb_min_spikes.value(),
            "network_min_channels": self._nb_min_channels.value(),
            "network_isi_threshold": ("automatic" if self._nb_auto_isi.isChecked()
                                      else self._nb_isi.value()),
            "single_min_spikes": self._sc_min_spikes.value(),
            "single_isi_threshold": ("automatic" if self._sc_auto_isi.isChecked()
                                     else self._sc_isi.value()),
        }
        n_channels = max(max(s) for s in by_method.values()) + 1
        self._run(_BurstWorker(by_method, n_channels, self._fs, self._duration_s,
                               settings),
                  self._on_bursts,
                  f"Detecting bursts for {', '.join(by_method)}…")

    def _on_bursts(self, payload) -> None:
        self._bursts_by_method.update(payload)
        if self._burst_length <= 0:
            # Opens on the whole recording, like the traces: two hundred bursts
            # over ten minutes is the first thing worth seeing, and zooming into
            # one of them is the move after that.
            self._navigate_bursts(0.0, max(self._duration_s, 0.01))
        self._tabs.setCurrentIndex(4)
        # One line per method, because the disagreement between them is the
        # finding: the same recording gives two hundred network bursts on one
        # threshold's spikes and none on another's.
        summaries = []
        for method, (burst_times, _c, info, single) in payload.items():
            threshold = info.get("isin_th", float("nan"))
            summaries.append(
                f"{method}: {len(burst_times)} network burst(s) at an ISIₙ "
                f"threshold of {threshold * 1000:.0f} ms, "
                f"{len(single.get('bursting_units', ()))} channel(s) bursting")
        self._finished("  ·  ".join(summaries))

    # ── State the views read ──────────────────────────────────────────────────

    def _channels_agree(self) -> bool:
        """Whether loaded spikes and loaded traces describe the same electrodes.

        Compared by value, not identity: a run's spike file and the recording
        it was detected from list the same channels, and that is exactly the
        case where re-detecting one channel should leave the other 63 alone.
        """
        if self._spike_channels is None or self._raw_channels is None:
            return True
        return (len(self._spike_channels) == len(self._raw_channels)
                and bool(np.array_equal(np.asarray(self._spike_channels).ravel(),
                                        np.asarray(self._raw_channels).ravel())))

    def _methods(self) -> list[str]:
        """Methods present, in the order they first appeared in this window.

        Order is held in ``_method_order`` rather than read off the spike dict
        each time, because that dict's order follows whichever channels were
        detected most recently — and a method's colour is its position in this
        list. Re-detecting one channel would otherwise repaint the lot.
        """
        present = {name for per in self._spike_times.values() for name in per}
        return [name for name in self._method_order if name in present]

    def _remember_methods(self, names) -> None:
        for name in names:
            if name not in self._method_order:
                self._method_order.append(name)

    def _current_channel(self) -> int:
        """Index of the channel on screen, into the raw/spike channel arrays."""
        data = self._channel_combo.currentData()
        return int(data) if data is not None else 0

    def _pick_channel(self, index: int) -> None:
        """Show the channel at *index* — the map's half of the dropdown."""
        position = self._channel_combo.findData(index)
        if position >= 0:
            self._channel_combo.setCurrentIndex(position)

    def _selected_methods(self) -> list[str]:
        """Methods ticked for display, in the order the list holds them."""
        return [self._method_list.item(i).text()
                for i in range(self._method_list.count())
                if self._method_list.item(i).checkState() == Qt.CheckState.Checked]

    def _primary_method(self) -> str:
        """The one method the single-method views describe.

        The first ticked, falling back to the first that exists: a waveform
        average over three detection methods at once would be a picture of
        nothing, so those views pick one and their titles say which.
        """
        selected = self._selected_methods()
        if selected:
            return selected[0]
        methods = self._methods()
        return methods[0] if methods else ""

    def _rate_method(self) -> str:
        """The method whose firing rates colour the array map.

        Falls back to the first ticked one, which is what it starts on: the
        combo is a deliberate override, not another thing to set before the
        window says anything.
        """
        chosen = self._rate_method_combo.currentText()
        return chosen if chosen in self._methods() else self._primary_method()

    def _method_color(self, name: str) -> str:
        """A method's colour, fixed by its position in the recording's list.

        Keyed on the full list rather than the ticked subset, so a method does
        not change colour when a different one is ticked — which would make the
        two-method comparison this exists for unreadable.
        """
        methods = self._methods()
        return method_color(methods.index(name) if name in methods else 0)

    def _on_methods_changed(self) -> None:
        if not self._syncing:
            self._refresh()

    def _channel_name(self, index: int) -> str:
        channels = self._spike_channels if self._spike_channels is not None \
            else self._raw_channels
        if channels is not None and index < len(channels):
            return str(int(channels[index]))
        return str(index)

    def _times_for(self, index: int, method: str) -> np.ndarray:
        return np.asarray(self._spike_times.get(index, {}).get(method, ()), dtype=float)

    def _threshold_for(self, index: int, method: str) -> float:
        return self._spike_thresholds.get(index, {}).get(method, float("nan"))

    def _spikes_for_method(self, method: str) -> dict[int, np.ndarray]:
        """Every channel's spikes for *method*, as burst detection wants them."""
        return {index: self._times_for(index, method)
                for index in sorted(self._spike_times)
                if method in self._spike_times[index]}

    def _spikes_by_channel(self) -> dict[int, np.ndarray]:
        """The same, for whichever method the single-method views describe."""
        return self._spikes_for_method(self._primary_method())

    def _bursts_for_view(self) -> tuple[str, tuple] | None:
        """The bursts to draw, and which method they came from.

        The method being shown, when it has bursts. Otherwise anything the
        window holds — a file may carry bursts for a method that is not ticked,
        or from before results were kept per method, and showing them under a
        heading that says whose they are beats an empty tab.
        """
        method = self._primary_method()
        if method in self._bursts_by_method:
            return method, self._bursts_by_method[method]
        for name, bursts in self._bursts_by_method.items():
            return name, bursts
        return None

    #: How many filtered channels to keep. Enough that flicking between a few
    #: channels is instant, few enough that the cache cannot outgrow the
    #: recording it came from.
    FILTERED_CACHE = 6

    def _filtered_trace(self, index: int) -> np.ndarray | None:
        """The bandpassed trace for *index*, filtered once and kept.

        Filtering a ten-minute channel is a fifth of a second — nothing once,
        and very visible when it happens on every redraw of a window the user
        is stepping through.
        """
        if self._dat is None or index >= self._dat.shape[1]:
            return None
        if index in self._filtered:
            # Re-inserting moves it to the end, which is what makes this an LRU
            # rather than "evict whichever was loaded first".
            self._filtered[index] = self._filtered.pop(index)
        else:
            self._filtered[index] = bandpass_filter(
                self._dat[:, index].astype(float), self._fs,
                self._filter_low.value(), self._filter_high.value())
            while len(self._filtered) > self.FILTERED_CACHE:
                self._noise.pop(next(iter(self._filtered)), None)
                self._filtered.pop(next(iter(self._filtered)))
        return self._filtered[index]

    def _channel_noise(self, index: int) -> float:
        """The channel's noise: the one the detector actually thresholded against.

        Read back off the thresholds when the channel has any — that is the
        detector's own sigma, exactly, and it costs nothing. Only when there is
        none to read from (a wavelet-only detection, say) is it measured off
        the filtered trace, which is a median over the whole channel: 36 ms,
        wanted on every redraw for the SNR in the title and the marker spacing,
        so it is cached beside the trace it describes and dropped with it.

        One source for both, so the SNR over the trace and the SNR on the array
        map cannot quietly disagree. The two estimators differ in where they
        centre — on zero, or on the trace's mean — which is nothing on a
        bandpassed channel and not nothing in general.

        Note that this describes *the detection on screen*, not the filter
        settings on screen. Change the bandpass without re-detecting and this
        keeps reporting the noise the visible spikes were found against, which
        is the only thing consistent with the markers and thresholds beside it.
        Re-detecting moves them all together.
        """
        if index not in self._noise:
            recovered = self._channel_sigma(index)
            if np.isfinite(recovered):
                self._noise[index] = recovered
            else:
                trace = self._filtered_trace(index)
                self._noise[index] = (float("nan") if trace is None
                                      else _noise_mad(trace))
        return self._noise[index]

    def _invalidate_filtered(self) -> None:
        self._noise.clear()
        self._filtered.clear()
        self._trace_signature = None
        self._refresh()

    def _channel_count(self) -> int:
        if self._spike_channels is not None:
            return max(len(self._spike_channels), 1)
        return max(len(self._spike_times), 1)

    def _firing_rates(self) -> np.ndarray:
        method = self._rate_method()
        rates = np.zeros(self._channel_count())
        if self._duration_s <= 0:
            return rates
        for index in range(len(rates)):
            rates[index] = self._times_for(index, method).size / self._duration_s
        return rates

    def _channel_sigmas(self) -> np.ndarray:
        """Each channel's noise, without re-reading a byte of the recording.

        A threshold is ``median - multiplier * sigma``, so a channel detected at
        two or more thresholds has its noise written into the results already
        and it can be read straight back off them — exactly. With one threshold
        the median has to be taken as zero, which on a bandpassed trace it very
        nearly is. Only when neither is available does this fall back on
        measuring a filtered trace, and then only for channels already cached,
        because filtering sixty of them to colour a map is not a fair trade.
        """
        return np.array([self._channel_sigma(index)
                         for index in range(self._channel_count())])

    def _channel_sigma(self, index: int) -> float:
        """One channel's noise, read back off the thresholds it was detected at.

        NaN when there is nothing to read it from — a detection with no
        threshold methods in it, or a channel that was grounded.
        """
        per_method = self._spike_thresholds.get(index, {})
        pairs = [(float(name[3:].replace("p", ".")), value)
                 for name, value in per_method.items()
                 if name.startswith("thr") and np.isfinite(value)]
        if len(pairs) >= 2:
            return noise_from_thresholds(*zip(*pairs))[0]
        if len(pairs) == 1:
            multiplier, threshold = pairs[0]
            # One threshold fixes sigma only if the median is known, and on a
            # bandpassed trace it is zero to several decimal places.
            return abs(threshold) / multiplier if multiplier else float("nan")
        return float("nan")

    def _channel_amplitudes(self) -> np.ndarray:
        """Each channel's median spike depth for the method being shown."""
        method = self._rate_method()
        amplitudes = np.full(self._channel_count(), np.nan)
        for index in range(len(amplitudes)):
            waveforms = self._waveforms.get(index, {}).get(method)
            if waveforms is not None and np.size(waveforms):
                amplitudes[index] = float(np.median(
                    np.asarray(waveforms, dtype=float).min(axis=1)))
        return amplitudes

    def _channel_snr(self) -> np.ndarray:
        """Median spike depth over the noise it was detected against.

        The same ratio the trace title reports, per channel. Worth reading with
        one thing in mind: a threshold at 4 MAD accepts nothing shallower than
        4 sigma, so SNR cannot come out below the multiplier that produced it.
        It says how far past the bar the typical spike on a channel sits — not
        whether the bar was in the right place, which is what the sweep is for.
        """
        return np.abs(self._channel_amplitudes()) / self._channel_sigmas()

    #: What the array map can be coloured by: label → (values, unit).
    MAP_METRICS = ("Firing rate", "SNR", "Spike count", "Median amplitude")

    def _channel_values(self) -> tuple[np.ndarray, str]:
        """The values colouring the map, and their unit."""
        metric = self._map_metric.currentText()
        if metric == "SNR":
            return self._channel_snr(), "×σ"
        if metric == "Spike count":
            method = self._rate_method()
            return (np.array([float(self._times_for(i, method).size)
                              for i in range(self._channel_count())]), "")
        if metric == "Median amplitude":
            return np.abs(self._channel_amplitudes()), ""
        return self._firing_rates(), "Hz"

    def _layout_coords(self) -> np.ndarray | None:
        """Electrode positions for the array map, in the recording's order.

        The spike file's own coordinates win when it has them: they are the
        ones the run used, so a map drawn from them matches the run's figures
        even if the layout dropdown here says something else.
        """
        channels = self._spike_channels if self._spike_channels is not None \
            else self._raw_channels
        if channels is None:
            return None
        if self._coords is not None and len(self._coords) == len(channels):
            return self._coords
        try:
            ids, xy = get_coords_from_layout(self._layout_combo.currentText())
        except ValueError:
            return None
        by_id = {int(c): p for c, p in zip(ids, xy)}
        coords = np.array([by_id.get(int(c), (np.nan, np.nan)) for c in channels],
                          dtype=float)
        return None if np.isnan(coords).all() else coords

    def _on_layout_changed(self) -> None:
        # A layout only moves the array map; the file's own coordinates, when
        # it has them, still win — so dropping them here is what lets the
        # dropdown have any effect on a file that carried its own.
        self._coords = None
        self._refresh()

    # ── Redrawing ─────────────────────────────────────────────────────────────

    def _refresh_channels(self) -> None:
        """Rebuild the channel and method pickers, keeping the current picks."""
        channels = self._spike_channels if self._spike_channels is not None \
            else self._raw_channels
        if channels is None and self._dat is not None:
            channels = np.arange(self._dat.shape[1])

        self._syncing = True
        self._channel_combo.blockSignals(True)
        self._method_list.blockSignals(True)
        try:
            wanted_channel = self._channel_combo.currentData()
            self._channel_combo.clear()
            if channels is not None:
                for index, channel in enumerate(np.asarray(channels).ravel()):
                    self._channel_combo.addItem(str(int(channel)), index)
            restored = self._channel_combo.findData(wanted_channel)
            self._channel_combo.setCurrentIndex(max(restored, 0))

            # Which methods were ticked survives a re-detection: running again
            # with a new threshold and being shown a different method than the
            # one you were reading is a small theft of attention. A method that
            # was not there before is ticked too — asking for bior1.5 and being
            # shown no bior1.5 reads as a detection that found nothing.
            was_ticked = set(self._selected_methods()) | self._newly_detected
            self._newly_detected = set()
            first_run = self._method_list.count() == 0
            self._method_list.clear()
            for index, name in enumerate(self._methods()):
                item = QListWidgetItem(name)
                item.setIcon(_swatch(method_color(index)))
                # On the first detection nothing was ticked, so tick the first
                # method: opening onto an unmarked trace would look like the
                # detection had found nothing.
                ticked = name in was_ticked or (first_run and index == 0)
                item.setCheckState(Qt.CheckState.Checked if ticked
                                   else Qt.CheckState.Unchecked)
                self._method_list.addItem(item)
            if self._methods() and not self._selected_methods():
                self._method_list.item(0).setCheckState(Qt.CheckState.Checked)

            wanted_rate = self._rate_method_combo.currentText()
            self._rate_method_combo.blockSignals(True)
            self._rate_method_combo.clear()
            self._rate_method_combo.addItems(self._methods())
            restored = self._rate_method_combo.findText(wanted_rate)
            self._rate_method_combo.setCurrentIndex(max(restored, 0))
            self._rate_method_combo.blockSignals(False)
        finally:
            self._channel_combo.blockSignals(False)
            self._method_list.blockSignals(False)
            self._syncing = False

        self._update_busy()
        self._refresh()

    def _on_window_typed(self) -> None:
        if not self._syncing:
            self._refresh()

    def _refresh(self) -> None:
        """Redraw whichever view is showing. Cheap enough to call on any change."""
        self._sync_scrollbar()
        self._sync_burst_scrollbar()
        self._draw_array_map()
        index = self._tabs.currentIndex() if hasattr(self, "_tabs") else 0
        if index == 0:
            self._draw_traces()
        elif index == 1:
            self._draw_filtering()
        elif index == 2:
            self._draw_quality()
        elif index == 3:
            self._draw_sweep()
        else:
            self._draw_bursts()

    def _draw_array_map(self) -> None:
        channels = self._spike_channels if self._spike_channels is not None \
            else self._raw_channels
        if channels is None:
            self._array_map.message("Open a recording to see its electrodes")
            return
        names = [str(int(c)) for c in np.asarray(channels).ravel()]
        method = self._rate_method()
        values, unit = self._channel_values()
        self._array_map.show_array(
            self._layout_coords(), values, names, self._current_channel(),
            f"{self._map_metric.currentText()} · {method}" if method
            else "No spikes detected yet", unit)

    def _draw_traces(self) -> None:
        channel = self._current_channel()
        filtered = self._filtered_trace(channel)
        if filtered is None or self._time_axis is None:
            self._trace_view.message(
                "Open a raw recording to see its traces. "
                "Spikes alone can be checked on the Bursts tab.")
            return

        method = self._primary_method()
        noise = self._channel_noise(channel)
        summary = quality_summary(
            self._times_for(channel, method),
            self._waveforms.get(channel, {}).get(method),
            self._threshold_for(channel, method), self._duration_s,
            self._ref_period.value(), noise)
        head = (f"Channel {self._channel_name(channel)}"
                + (f" · {method}" if method else " · no spikes detected yet"))

        signature = (channel, self._show_raw.isChecked(),
                     self._filter_low.value(), self._filter_high.value())
        if signature != self._trace_signature:
            # The trace goes to the plot once and is then panned and zoomed
            # without touching it again; only a different channel, a different
            # filter, or the raw overlay coming and going is a reason to
            # rebuild it.
            self._trace_signature = signature
            self._trace_view.show_trace(
                self._time_axis, filtered,
                self._dat[:, channel].astype(float)
                if self._show_raw.isChecked() else None,
                self._fs, self._duration_s, "")
            self._trace_view.set_range(
                self._window_start.value(),
                self._window_start.value() + self._window_length.value())
        self._trace_view.set_title(_fit_title(head, summary, width=110))

        marked = [(name, self._times_for(channel, name), self._method_color(name))
                  for name in self._selected_methods()]
        self._trace_view.show_spikes(
            marked, solid=self._solid_markers.isChecked(),
            offset=self._marker_offset.value() * (noise if np.isfinite(noise) else 0.0))
        self._trace_view.show_thresholds(
            [(self._threshold_for(channel, name), self._method_color(name))
             for name, _, _ in marked])

    def _draw_filtering(self) -> None:
        channel = self._current_channel()
        filtered = self._filtered_trace(channel)
        if filtered is None or self._dat is None:
            self._filter_canvas.message(
                "Load a raw recording to see what the filter does to it.")
            return
        start = self._window_start.value()
        method = self._primary_method()
        self._filter_canvas.render(
            self._dat[:, channel].astype(float), filtered, self._fs,
            start, start + self._window_length.value(),
            self._filter_low.value(), self._filter_high.value(),
            self._times_for(channel, method),
            f"Channel {self._channel_name(channel)} · bandpass "
            f"{self._filter_low.value():g}–{self._filter_high.value():g} Hz")

    def _draw_quality(self) -> None:
        if not self._spike_times:
            self._quality_canvas.message(
                "No spikes yet. Detect here, or open a run's spike file.")
            return
        channel = self._current_channel()
        names = self._selected_methods() or [self._primary_method()]
        methods = [
            {"name": name,
             "waveforms": self._waveforms.get(channel, {}).get(name),
             "times": self._times_for(channel, name),
             "threshold": self._threshold_for(channel, name),
             "color": self._method_color(name)}
            for name in names if name
        ]
        if not methods:
            self._quality_canvas.message("Tick a spike method to check.")
            return

        head = f"Channel {self._channel_name(channel)} · {', '.join(names)}"
        if len(methods) == 1:
            # One method gets the full set of numbers; with several they would
            # describe only whichever happened to be first, so they move into
            # each panel's legend instead.
            noise = self._channel_noise(channel)
            summary = quality_summary(
                methods[0]["times"], methods[0]["waveforms"],
                methods[0]["threshold"], self._duration_s,
                self._ref_period.value(),
                noise if np.isfinite(noise) else None)
        else:
            summary = (f"{len(methods)} methods compared · the array map shows "
                       f"{self._map_metric.currentText().lower()} for "
                       f"{self._rate_method()}")

        values, unit = self._channel_values()
        self._quality_canvas.render(
            methods, self._fs, self._ref_period.value(), values,
            self._layout_coords(), channel, head, summary,
            self._max_waveforms.value(),
            f"{self._map_metric.currentText()}"
            + (f" ({unit})" if unit else "") + f" · {self._rate_method()}")

    def _draw_bursts(self) -> None:
        shown = self._bursts_for_view()
        if shown is None:
            self._burst_view.message(
                "Set the burst parameters and press Detect bursts."
                if self._spike_times else
                "No spikes yet. Detect here, or open a run's spike file.")
            return
        burst_method, (burst_times, _burst_channels, info, single) = shown
        channel = self._current_channel()
        threshold = info.get("isin_th", float("nan"))
        # Named after the method the *bursts* came from, which is not always the
        # one the rest of the window is describing — a file can carry bursts for
        # a method that is not ticked, and drawing them under the ticked one's
        # name would be a quiet lie about which spikes produced them.
        title = (f"{burst_method} spikes · network ISIₙ threshold "
                 f"{threshold * 1000:.0f} ms · "
                 f"{len(single.get('bursting_units', ()))} channel(s) bursting")
        self._burst_view.render(
            self._spikes_for_method(burst_method), self._fs,
            self._duration_s, burst_times, channel,
            self._channel_name(channel),
            single.get("burst_matrices", {}).get(channel, {}),
            self._raster_bin.value(), title,
            (self._burst_start, self._burst_start + self._burst_length))

    def _on_follow_trace(self, on: bool) -> None:
        if on:
            self._navigate_bursts(self._window_start.value(),
                                  self._window_length.value())
        self._refresh()

    # ── Moving the window ─────────────────────────────────────────────────────

    def _step_window(self, direction: int) -> None:
        length = self._window_length.value()
        self._navigate(self._window_start.value() + direction * length, length)

    def _jump_to_next_spike(self) -> None:
        """Move the window to the first spike it is not already showing.

        Measured from the end of the window rather than its start, so pressing
        this twice moves twice: from the start, a spike already on screen is
        "next" and the button would appear to do nothing.

        With the whole recording on screen — which is how one opens — every
        spike is already showing, and the honest answer to "next" would be
        "none", every time, on first use. So from there it zooms to the first
        one instead: that is plainly what the button is being asked for.
        """
        times = np.asarray(
            self._times_for(self._current_channel(), self._primary_method()),
            dtype=float)
        if times.size == 0:
            self._status.setText("No spikes on this channel to jump to.")
            return
        length = self._window_length.value()
        if length >= self._duration_s - 1e-6:
            length = _inspect_window(_INSPECT_SPIKE_S, self._duration_s)
            target = times.min()
        else:
            after = times[times > self._window_start.value() + length]
            if after.size == 0:
                self._status.setText("No further spikes on this channel.")
                return
            target = after.min()
        # Landed a little before the spike rather than on it, so the window
        # shows what led up to it — the part that says whether it is a spike.
        self._navigate(target - length / 4, length)

    # ── Plumbing ──────────────────────────────────────────────────────────────

    def _run(self, worker: _Worker, on_done, message: str) -> None:
        """Start *worker* saying *message*, and keep it alive until it finishes.

        A ``QThread`` that goes out of scope while running takes the process
        with it, so the window holds every worker it started and drops it on
        completion.
        """
        self._status.setText(message)
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._started_at = time.monotonic()
        if self._dat is None and not self._spike_times:
            # Nothing has ever been drawn, so the plot area is a blank the
            # message can have. Once there is something on it the status bar is
            # the place for this — wiping a plot to say "loading" would throw
            # away what the user is waiting to compare against.
            self._current_canvas().message(message)
        worker.done.connect(on_done)
        worker.failed.connect(self._on_failed)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(lambda: self._worker_finished(worker))
        self._workers.append(worker)
        self._update_busy()
        worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        """Show how far detection has got, and how much longer it will take.

        The estimate is elapsed-over-done extrapolated to the rest, which is
        honest for this job: channels are independent and cost about the same,
        so the rate measured over the first few is the rate for the remainder.
        It is deliberately vague in words — "about 40 s left" — because a
        second-by-second countdown claims a precision the extrapolation
        does not have.
        """
        if total <= 0:
            return
        self._progress.setRange(0, total)
        self._progress.setValue(done)
        self._progress.setTextVisible(True)
        elapsed = time.monotonic() - self._started_at
        # Nothing useful can be said from the first channel alone, and the
        # first is the slowest — it pays for whatever the run warms up.
        if done >= 2 and elapsed > 0:
            remaining = elapsed / done * (total - done)
            self._progress.setFormat(f"%p%  ·  about {_duration(remaining)} left")
        else:
            self._progress.setFormat("%p%")

    def _worker_finished(self, worker: _Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        self._update_busy()

    def _on_failed(self, message: str) -> None:
        self._finished(message)

    def _refresh_save_button(self) -> None:
        """Say what pressing Save would write, so it is never a guess.

        The wording is the only thing telling anyone that bursts detected after
        a save are not in the file yet — the commonest way to lose them is to
        save, then run bursts, then close.
        """
        bursts = len(self._bursts_by_method)
        self._save_btn.setText(
            "Save spikes and bursts…" if bursts else "Save spikes…")
        # Rebuilt from the stored base rather than appended to what is there:
        # re-detecting spikes clears the bursts, and a note left over from
        # before would promise to save something the window no longer holds.
        self._save_btn.setToolTip(
            self._save_tooltip if not bursts else
            self._save_tooltip
            + f"\n\nBursts are ready for {', '.join(self._bursts_by_method)} "
              f"and go in too.")

    def _update_busy(self) -> None:
        """Enable what can be started, given what is running.

        Busy means *any* job is running, not "the last one to report". Opening
        a run's spike file starts a second job — finding and loading the raw
        recording it names — and the first one finishing does not mean the
        window is free: a boolean set by whichever finished last hid the
        progress bar while the long half of the work was still going.
        """
        busy = bool(self._workers)
        self._progress.setVisible(busy)
        self._raw_browse.setEnabled(not busy)
        self._spikes_browse.setEnabled(not busy)
        self._detect_channel_btn.setEnabled(not busy and self._dat is not None)
        self._detect_all_btn.setEnabled(not busy and self._dat is not None)
        self._burst_btn.setEnabled(not busy and bool(self._spike_times))
        self._save_btn.setEnabled(not busy and bool(self._spike_times)
                                  and bool(self._raw_path.text()))
        self._sweep_channel_btn.setEnabled(not busy and self._dat is not None)
        self._sweep_all_btn.setEnabled(not busy and self._dat is not None)
        self._refresh_save_button()

    def _finished(self, message: str) -> None:
        """Report a job's result and redraw on it."""
        self._status.setText(message)
        self._update_busy()
        self._refresh()

    def _current_canvas(self) -> _Canvas:
        return (self._trace_view, self._filter_canvas, self._quality_canvas,
                self._sweep_canvas, self._burst_view)[self._tabs.currentIndex()]

    def closeEvent(self, event) -> None:
        """Let running work finish rather than tearing its thread down mid-read.

        Loading a multi-gigabyte recording is the common case here, and killing
        that thread from under h5py is how a close turns into a crash.
        """
        for worker in list(self._workers):
            worker.wait(2000)
        super().closeEvent(event)


# ── Threshold sweep ───────────────────────────────────────────────────────────

@dataclass
class SweepPoint:
    """What one threshold found, and how much of it looks like spikes."""

    multiplier: float
    #: The voltage that multiplier worked out to, averaged over the channels
    #: swept. Useful for reading the sweep against a trace.
    voltage: float
    n_spikes: int
    #: Mean per-channel firing rate, so sweeps of one channel and of a whole
    #: array are on the same scale.
    rate: float
    #: Fraction of intervals shorter than the refractory period.
    violations: float
    median_amplitude: float
    #: Median amplitude over the noise the threshold was measured against.
    snr: float
    active_channels: int
    mean_waveform: np.ndarray


def noise_from_thresholds(multipliers, thresholds) -> tuple[float, float]:
    """Recover ``(sigma, median)`` from the thresholds a sweep produced.

    A threshold is ``median - multiplier * sigma``, so a sweep's thresholds lie
    on a straight line in the multiplier and the two constants can be read
    straight back off it — exactly, not approximately. That is worth doing
    because it means the sweep knows the trace's noise without anyone measuring
    it a second time: the numbers are already in the results.
    """
    multipliers = np.asarray(multipliers, dtype=float)
    thresholds = np.asarray(thresholds, dtype=float)
    usable = np.isfinite(thresholds)
    if usable.sum() < 2:
        return float("nan"), float("nan")
    design = np.vstack([np.ones(usable.sum()), -multipliers[usable]]).T
    (median, sigma), *_ = np.linalg.lstsq(design, thresholds[usable], rcond=None)
    return float(sigma), float(median)


def sweep_points(result, multipliers, duration_s: float, ref_period_ms: float,
                 min_rate: float = 0.01) -> list[SweepPoint]:
    """Summarise a multi-threshold detection, one row per threshold.

    Reads a :class:`SpikeDetectionResult` that was asked for every threshold in
    *multipliers* at once — which costs barely more than asking for one, since
    the filtering and the noise medians are per channel, not per threshold.

    The measures are chosen to show the two things a sweep is looked at for.
    Counts and rates say *how much* a threshold admits; violations, amplitude
    and SNR say *what* it is admitting. A threshold low enough to be picking up
    noise shows it twice over — the count climbs away and the median amplitude
    collapses onto the threshold itself.
    """
    channels = sorted(result.spike_times)
    points: list[SweepPoint] = []
    sigmas = {
        channel: noise_from_thresholds(
            multipliers,
            [result.thresholds.get(channel, {}).get(
                threshold_method_name(m), float("nan")) for m in multipliers])[0]
        for channel in channels
    }
    mean_sigma = float(np.nanmean(list(sigmas.values()))) if sigmas else float("nan")

    for multiplier in multipliers:
        method = threshold_method_name(multiplier)
        times, amplitudes, waves, rates = [], [], [], []
        violations_num = violations_den = 0
        for channel in channels:
            spikes = np.asarray(
                result.spike_times.get(channel, {}).get(method, ()), dtype=float)
            rates.append(spikes.size / duration_s if duration_s > 0 else 0.0)
            if spikes.size:
                times.append(spikes)
            count, _ = refractory_violations(spikes, ref_period_ms)
            violations_num += count
            violations_den += max(spikes.size - 1, 0)
            waveforms = result.spike_waveforms.get(channel, {}).get(method)
            if waveforms is not None and np.size(waveforms):
                waveforms = np.asarray(waveforms, dtype=float)
                amplitudes.append(waveforms.min(axis=1))
                waves.append(waveforms.mean(axis=0))

        n_spikes = int(sum(t.size for t in times))
        median_amplitude = float(np.median(np.concatenate(amplitudes))) \
            if amplitudes else float("nan")
        thresholds = [result.thresholds.get(c, {}).get(method, np.nan)
                      for c in channels]
        points.append(SweepPoint(
            multiplier=float(multiplier),
            voltage=float(np.nanmean(thresholds)) if thresholds else float("nan"),
            n_spikes=n_spikes,
            rate=float(np.mean(rates)) if rates else 0.0,
            violations=(violations_num / violations_den) if violations_den else 0.0,
            median_amplitude=median_amplitude,
            snr=abs(median_amplitude) / mean_sigma
            if mean_sigma and np.isfinite(mean_sigma) else float("nan"),
            active_channels=int(sum(r >= min_rate for r in rates)),
            mean_waveform=np.mean(waves, axis=0) if waves else np.zeros(0),
        ))
    return points


def count_slopes(points: list[SweepPoint]) -> np.ndarray:
    """How steeply the spike count falls, in decades per MAD, between points.

    One shorter than *points*: entry *i* describes the step from ``points[i]``
    to ``points[i + 1]``.
    """
    if len(points) < 2:
        return np.zeros(0)
    multipliers = np.array([p.multiplier for p in points], dtype=float)
    counts = np.log10(np.maximum([p.n_spikes for p in points], 0.5))
    steps = np.diff(multipliers)
    return np.diff(counts) / np.where(steps == 0, np.nan, steps)


def knee_threshold(points: list[SweepPoint], shallow: float = 0.5) -> float | None:
    """Where the count stops falling steeply — the threshold worth arguing about.

    Raising the threshold through the noise takes the count down very fast,
    because the noise it is cutting into is a distribution with a steep tail.
    Once the noise is gone, what is left is spikes, and the count falls slowly.
    The elbow between the two is the useful reading of a sweep, and this finds
    it: the first threshold whose fall is less than *shallow* times the steepest
    fall anywhere in the sweep.

    Descriptive, not prescriptive. It says where the curve changes character,
    which is a fact about the data; whether that is the right threshold for an
    analysis is a judgement it cannot make.

    A refractory-violation criterion would be the obvious alternative and is not
    used, because MEA-NAP's threshold detector *enforces* a refractory period
    while detecting. Measuring violations of the same period against its own
    output returns nearly zero at every threshold — a number that looks like
    evidence and carries none.
    """
    slopes = count_slopes(points)
    if slopes.size == 0 or not np.isfinite(slopes).any():
        return None
    steepest = float(np.nanmin(slopes))
    if steepest >= 0:
        return None
    for index, slope in enumerate(slopes):
        if np.isfinite(slope) and slope > shallow * steepest:
            return points[index].multiplier
    return None


# ── Bursts, flattened for storage and back ────────────────────────────────────

#: Separates a method name from the field it labels in a saved burst file.
#: Two underscores because method names contain single ones (``thr4p5``).
_BURST_KEY = "__"
#: Where bursts from a file written before results were kept per method end up.
#: They are real results whose method was never recorded, so they are labelled
#: as such rather than silently attached to a method that may not have produced
#: them — or silently dropped.
UNLABELLED_METHOD = "(method not recorded)"


def pack_bursts(by_method: dict[str, tuple]) -> dict[str, np.ndarray]:
    """Lay burst detections out as flat arrays an ``npz`` can hold.

    Keyed by the spike method each was detected from, because that is what
    decides the answer: run the network detector on a permissive threshold's
    spikes and on a strict one's and you get different bursts from the same
    recording. A file that recorded only "the bursts" could not be reloaded
    onto the method it belonged to.

    Burst results are also ragged — a variable number of network bursts, and a
    variable number of single-channel bursts on each of a variable set of
    channels — so each channel's bursts go under their own key rather than into
    one array of arrays. What is kept is what the Bursts tab draws: where the
    network bursts are, which channels burst on their own and where, and the
    ISI-N threshold that produced them. The summary metrics are not kept,
    because the pipeline recomputes them from the spikes anyway and a stale
    copy in a file is worse than none.
    """
    packed: dict[str, np.ndarray] = {}
    for method, bursts in (by_method or {}).items():
        burst_times, _channels, info, single = bursts
        prefix = f"{method}{_BURST_KEY}"
        packed[f"{prefix}network_times"] = np.asarray(
            burst_times, dtype=float).reshape(-1, 2)
        packed[f"{prefix}isin_th"] = np.array(
            [float(info.get("isin_th", float("nan")))])
        packed[f"{prefix}bursting_units"] = np.asarray(
            single.get("bursting_units", []), dtype=int)
        for channel, matrix in (single.get("burst_matrices") or {}).items():
            starts = np.asarray(matrix.get("T_start", []), dtype=float)
            if not starts.size:
                continue
            packed[f"{prefix}ch{channel}_start"] = starts
            packed[f"{prefix}ch{channel}_end"] = np.asarray(
                matrix.get("T_end", []), dtype=float)
            packed[f"{prefix}ch{channel}_size"] = np.asarray(
                matrix.get("S", []), dtype=float)
    return packed


def unpack_bursts(packed: dict[str, np.ndarray]) -> dict[str, tuple]:
    """Rebuild what :func:`pack_bursts` stored, keyed by spike method.

    Empty when the file carried no bursts, which is what a spike file written
    before they were run — or by the pipeline — looks like. Keys written before
    burst results were kept per method have no method in them and come back
    under :data:`UNLABELLED_METHOD`.
    """
    grouped: dict[str, dict[str, np.ndarray]] = {}
    for key, value in (packed or {}).items():
        method, sep, field = key.partition(_BURST_KEY)
        if not sep:
            method, field = UNLABELLED_METHOD, key
        grouped.setdefault(method, {})[field] = value

    results: dict[str, tuple] = {}
    for method, fields in grouped.items():
        if "network_times" not in fields:
            continue
        matrices = {}
        for field in fields:
            if not (field.startswith("ch") and field.endswith("_start")):
                continue
            channel = int(field[2:-len("_start")])
            matrices[channel] = {
                "T_start": np.asarray(fields[field], dtype=float),
                "T_end": np.asarray(fields.get(f"ch{channel}_end", []), dtype=float),
                "S": np.asarray(fields.get(f"ch{channel}_size", []), dtype=float),
            }
        # The channel list each burst spanned is not stored: nothing draws it,
        # and it is the one part that would double the file.
        results[method] = (
            np.asarray(fields["network_times"], dtype=float).reshape(-1, 2),
            [],
            {"isin_th": float(np.asarray(
                fields.get("isin_th", [np.nan])).ravel()[0])},
            {"bursting_units": np.asarray(
                fields.get("bursting_units", []), dtype=int),
             "burst_matrices": matrices},
        )
    return results


# ── Small helpers ─────────────────────────────────────────────────────────────

def _row(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    return holder


def _spin(low, high, decimals, value, suffix="", step=None) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    if step is not None:
        spin.setSingleStep(step)
    return spin


def _int_spin(low, high, value) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    return spin


def _duration(seconds: float) -> str:
    """A rough spoken length: ``5 s``, ``40 s``, ``3 min``."""
    if seconds < 10:
        return f"{max(seconds, 1):.0f} s"
    if seconds < 90:
        return f"{round(seconds / 5) * 5:.0f} s"
    return f"{seconds / 60:.0f} min"


def _describe_file(path) -> str:
    """``name (1.4 GB)`` — a file's name and how much of it there is to read.

    Loading a recording is the longest wait in this window and reports no
    progress while it happens, so the size is the only thing that tells the
    difference between a slow file and a stuck one.
    """
    path = Path(getattr(path, "path", path))
    try:
        size = path.stat().st_size
    except OSError:
        return path.name
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{path.name} ({size:.0f} {unit})" if unit in ("bytes", "KB") \
                else f"{path.name} ({size:.1f} {unit})"
        size /= 1024
    return path.name


def _number(value: float) -> str:
    return f"{value:g}"


def _numbers(text: str) -> list[float]:
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out
