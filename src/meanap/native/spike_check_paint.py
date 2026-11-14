"""The step-1 spike-detection check figures, drawn with ``QPainter``.

Three figures from one :class:`~meanap.pipeline.plotting.SpikeCheckData`:

* :class:`FrequenciesPainter` — spiking frequency over the recording, a curve
  per detection method. Pointing at a curve reads its value; clicking a method
  keeps it and fades the others.
* :class:`TracesPainter` — short filtered traces from a few electrodes, with
  each method's detected spikes marked above. Pointing at a marker says which
  method found a spike there and when; each panel zooms in time.
* :class:`WaveformsPainter` — the spikes each method found on one electrode,
  overlaid, with their mean.

A method is the same colour in all three.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen, QPolygonF

from meanap.native.axes import INK, Axes
from meanap.native.figure import GROUND, SELECTED, FigurePainter, paint_title
from meanap.native.output import figure_font

__all__ = ["FrequenciesPainter", "TracesPainter", "WaveformsPainter", "method_colour",
           "method_label"]

#: matplotlib's "tab10", which these figures have always used for the methods.
_TAB10 = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")
FADED = 0.18
REACH = 8.0


def method_colour(index: int) -> QColor:
    return QColor(_TAB10[index % len(_TAB10)])


def method_label(method: str) -> str:
    """A method as written for people: ``thr4p5`` is "thr4.5"."""
    return method.replace("p", ".")


def _paint_methods(painter: QPainter, methods: list[str], left: float, top: float,
                   chosen: int | None = None, marker: str = "line") -> None:
    """A legend of the detection methods, one per row."""
    font = figure_font(12)
    painter.save()
    painter.setFont(font)
    line = QFontMetricsF(font).height()
    for index, method in enumerate(methods):
        y = top + index * (line + 6)
        colour = method_colour(index)
        colour.setAlphaF(1.0 if chosen in (None, index) else FADED * 2)
        if marker == "line":
            painter.setPen(QPen(colour, 2.5))
            painter.drawLine(QPointF(left, y + line / 2), QPointF(left + 26, y + line / 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawPolygon(_triangle(left + 13, y + line / 2, 5.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(INK)
        painter.drawText(QRectF(left + 36, y, 220, line), Qt.AlignmentFlag.AlignVCenter,
                         method_label(method))
    painter.restore()


def _triangle(x: float, y: float, r: float) -> QPolygonF:
    """A marker pointing down at (x, y)."""
    return QPolygonF([QPointF(x - r, y - r), QPointF(x + r, y - r), QPointF(x, y + r * 0.9)])


class FrequenciesPainter(FigurePainter):
    """Spiking frequency through the recording, by method.

    What a view points at is ``(method index, bin)``; a pinned method stays
    drawn in full while the others fade.
    """

    standard_size = (1152.0, 576.0)

    def __init__(self, scene, size: tuple[float, float] | None = None):
        super().__init__(scene, size)
        self.axes: Axes | None = None
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = (self.axes.xlim, self.axes.ylim) if keep and self.axes is not None else None
        data = self.scene
        width, height = self.size
        curves = np.asarray(data.freq_curves, dtype=float)
        finite = curves[np.isfinite(curves)] if curves.size else np.zeros(0)
        top = float(finite.max()) * 1.06 if finite.size and finite.max() > 0 else 1.0
        duration = max(float(data.duration_s), 1.0)
        self.axes = Axes(QRectF(78, 56, width - 78 - 190, height - 56 - 62),
                         (0.0, duration), (0.0, top),
                         xlabel="Time (minutes)", ylabel="Spiking frequency (Hz)")
        # The axis counts seconds; it is read in minutes.
        self.axes.x_tick_values = [(60.0 * k, str(k))
                                   for k in range(1, int(np.ceil(duration / 60.0)) + 1)]
        if old is not None:
            self.axes.xlim, self.axes.ylim = old

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    def all_axes(self) -> list[Axes]:
        return [self.axes]

    def panel_at(self, x: float, y: float):
        return ("curves", self.axes) if self.axes.contains(x, y) else None

    def under(self, x: float, y: float):
        curves = np.asarray(self.scene.freq_curves, dtype=float)
        if not curves.size or not self.axes.contains(x, y):
            return None
        seconds, _ = self.axes.to_data(x, y)
        column = int(np.clip(round(seconds) - 1, 0, curves.shape[1] - 1))
        at = np.asarray(self.axes.y_pixel(curves[:, column]), dtype=float)
        nearest = int(np.nanargmin(np.abs(at - y)))
        return (nearest, column) if abs(at[nearest] - y) <= REACH else None

    def describe(self, what) -> str:
        method, column = what
        second = column + 1
        value = float(self.scene.freq_curves[method, column])
        return (f"{method_label(self.scene.methods[method])}\n"
                f"{second // 60} min {second % 60:02d} s: {value:.4g} Hz")

    def paint(self, painter: QPainter) -> None:
        data, axes = self.scene, self.axes
        width, height = self.size
        chosen = None if self.marked is None else self.marked[0]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, data.rec_name.replace("_", ""), width)
        curves = np.asarray(data.freq_curves, dtype=float)
        painter.save()
        axes.clip(painter)
        seconds = np.arange(1, curves.shape[1] + 1) if curves.size else np.zeros(0)
        xs = np.asarray(axes.x_pixel(seconds), dtype=float)
        order = [i for i in range(len(data.methods)) if i != chosen]
        for index in order + ([chosen] if chosen is not None else []):
            colour = method_colour(index)
            colour.setAlphaF(1.0 if chosen in (None, index) else FADED)
            ys = np.asarray(axes.y_pixel(curves[index]), dtype=float)
            pen = QPen(colour, 2.0)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in zip(xs.tolist(), ys.tolist())
                                            if np.isfinite(y)]))
        if self.marked is not None:
            method, column = self.marked
            painter.setPen(QPen(GROUND, 1.5))
            painter.setBrush(method_colour(method))
            painter.drawEllipse(QPointF(float(xs[column]),
                                        float(axes.y_pixel(curves[method, column]))), 5, 5)
        painter.restore()
        axes.paint_frame(painter)
        _paint_methods(painter, list(data.methods), axes.rect.right() + 22, axes.rect.top() + 4,
                       chosen)
        painter.restore()


class TracesPainter(FigurePainter):
    """Example filtered traces with each method's spikes marked.

    What a view points at is ``(panel, method index, frame)`` — one marker.
    """

    standard_size = (1344.0, 860.0)
    COLUMNS = 2

    def __init__(self, scene, size: tuple[float, float] | None = None):
        super().__init__(scene, size)
        self.axes: list[Axes] = []
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = [(a.xlim, a.ylim) for a in self.axes] if keep else None
        data = self.scene
        width, height = self.size
        # One slot more than there are panels, for the legend.
        rows = max(int(np.ceil((data.n_panels + 1) / self.COLUMNS)), 1)
        top, bottom, gap_x, gap_y = 44.0, 14.0, 26.0, 16.0
        cell_w = (width - 16 - gap_x * (self.COLUMNS - 1)) / self.COLUMNS
        cell_h = (height - top - bottom - gap_y * (rows - 1)) / rows
        self.axes = []
        self._cells = []
        for index in range(rows * self.COLUMNS):
            row, column = divmod(index, self.COLUMNS)
            cell = QRectF(8 + column * (cell_w + gap_x), top + row * (cell_h + gap_y),
                          cell_w, cell_h)
            self._cells.append(cell)
            if index >= data.n_panels:
                continue
            start, end = (float(v) for v in data.trace_views[index])
            std = float(data.trace_stds[index]) or 1.0
            axes = Axes(QRectF(cell.left() + 76, cell.top() + 40, cell.width() - 86,
                               cell.height() - 46),
                        (start, end), (-6 * std, 5 * std), ylabel="Amplitude (µV)",
                        title=(f"Electrode {int(data.trace_channels[index])}\n"
                               f"{start / data.fs:.3f} - {end / data.fs:.3f} s"),
                        x_ticks=False, x_spine=False)
            axes.title_size = 11
            self.axes.append(axes)
        if old is not None and len(old) == len(self.axes):
            for axes, (xlim, ylim) in zip(self.axes, old):
                axes.xlim, axes.ylim = xlim, ylim

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    def all_axes(self) -> list[Axes]:
        return list(self.axes)

    def panel_at(self, x: float, y: float):
        for index, axes in enumerate(self.axes):
            if axes.contains(x, y):
                return str(index), axes
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        return True, False              # in time; the voltage range is the noise level's

    def _marker_y(self, panel: int, method: int) -> float:
        std = float(self.scene.trace_stds[panel]) or 1.0
        return 5 * std - (method + 1) * (0.5 * std)

    def under(self, x: float, y: float):
        found = self.panel_at(x, y)
        if found is None:
            return None
        panel, axes = int(found[0]), found[1]
        best = None
        for method, frames in enumerate(self.scene.trace_spike_frames[panel]):
            frames = np.asarray(frames, dtype=float)
            if not len(frames):
                continue
            px = np.asarray(axes.x_pixel(frames), dtype=float)
            py = float(axes.y_pixel(self._marker_y(panel, method)))
            distance = np.hypot(px - x, py - y)
            nearest = int(np.argmin(distance))
            if distance[nearest] <= REACH and (best is None or distance[nearest] < best[0]):
                best = (float(distance[nearest]), (panel, method, int(frames[nearest])))
        return None if best is None else best[1]

    def describe(self, what) -> str:
        panel, method, frame = what
        data = self.scene
        return (f"{method_label(data.methods[method])}: spike at {frame / data.fs:.4f} s\n"
                f"electrode {int(data.trace_channels[panel])}")

    def paint(self, painter: QPainter) -> None:
        data = self.scene
        width, height = self.size
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, data.rec_name.replace("_", ""), width)
        marked = self.marked
        for index, axes in enumerate(self.axes):
            window = np.asarray(data.trace_windows[index], dtype=float)
            first = int(data.trace_starts[index])
            painter.save()
            axes.clip(painter)
            xs = np.asarray(axes.x_pixel(np.arange(first, first + len(window))), dtype=float)
            ys = np.asarray(axes.y_pixel(window), dtype=float)
            painter.setPen(QPen(INK, 0.8))
            painter.drawPolyline(QPolygonF([QPointF(x, y)
                                            for x, y in zip(xs.tolist(), ys.tolist())]))
            painter.setPen(Qt.PenStyle.NoPen)
            for method, frames in enumerate(data.trace_spike_frames[index]):
                frames = np.asarray(frames, dtype=float)
                if not len(frames):
                    continue
                y = float(axes.y_pixel(self._marker_y(index, method)))
                painter.setBrush(method_colour(method))
                for x in np.asarray(axes.x_pixel(frames), dtype=float).tolist():
                    painter.drawPolygon(_triangle(x, y, 4.0))
            if marked is not None and marked[0] == index:
                _panel, method, frame = marked
                x = float(axes.x_pixel(frame))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                # The moment it marks, down through the trace.
                painter.setPen(QPen(SELECTED, 1))
                painter.drawLine(QPointF(x, axes.rect.top()), QPointF(x, axes.rect.bottom()))
                painter.setPen(QPen(SELECTED, 2))
                painter.drawEllipse(QPointF(x, float(axes.y_pixel(self._marker_y(index, method)))),
                                    7, 7)
            painter.restore()
            axes.paint_frame(painter)
        # The methods, in the slot the grid leaves empty.
        if data.n_panels < len(self._cells):
            cell = self._cells[data.n_panels]
            painter.setPen(INK)
            painter.setFont(figure_font(12, bold=True))
            painter.drawText(QRectF(cell.left() + 76, cell.top() + 14, 300, 20),
                             Qt.AlignmentFlag.AlignVCenter, "Spikes detected by")
            _paint_methods(painter, list(data.methods), cell.left() + 76, cell.top() + 40,
                           marker="triangle")
        painter.restore()


class WaveformsPainter(FigurePainter):
    """Each method's spikes on one electrode, overlaid, with their mean.

    What a view points at is a method index.
    """

    PANEL_W, HEIGHT = 300.0, 640.0

    def __init__(self, scene, size: tuple[float, float] | None = None):
        columns = max(int(np.ceil(len(scene.methods) / 2)), 1)
        super().__init__(scene, size or (max(self.PANEL_W * columns + 16, 640.0), self.HEIGHT))
        self._columns = columns
        self._length = next((w.shape[1] for w in (scene.waveforms.get(m, np.zeros((0, 0)))
                                                  for m in scene.methods) if w.shape[0]), 0)
        # Every waveform as line pieces in data coordinates, made once.
        self._clouds: list[list[QLineF]] = []
        self._means: list[np.ndarray | None] = []
        for method in scene.methods:
            waves = np.asarray(scene.waveforms.get(method, np.zeros((0, 0))), dtype=float)
            if not waves.shape[0]:
                self._clouds.append([])
                self._means.append(None)
                continue
            x = np.arange(waves.shape[1], dtype=float)
            pieces = np.stack([np.broadcast_to(x[:-1], waves[:, :-1].shape), waves[:, :-1],
                               np.broadcast_to(x[1:], waves[:, 1:].shape), waves[:, 1:]], axis=2)
            pieces = pieces.reshape(-1, 4)
            pieces = pieces[np.isfinite(pieces).all(axis=1)]
            self._clouds.append([QLineF(a, b, c, d) for a, b, c, d in pieces.tolist()])
            self._means.append(np.nanmean(waves, axis=0))
        self.axes: list[Axes] = []
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = [a.ylim for a in self.axes] if keep else None
        data = self.scene
        width, height = self.size
        low, high = -6 * float(data.wave_std), 5 * float(data.wave_std)
        if low == high:
            low, high = -1.0, 1.0
        top, bottom, gap = 96.0, 20.0, 34.0
        cell_w = (width - 16) / self._columns
        cell_h = (height - top - bottom - gap) / 2
        self.axes = []
        for index, method in enumerate(data.methods):
            row, column = divmod(index, self._columns)
            rect = QRectF(8 + column * cell_w + 74, top + row * (cell_h + gap) + 22,
                          cell_w - 88, cell_h - 22)
            self.axes.append(Axes(rect, (0.0, float(max(self._length - 1, 1))), (low, high),
                                  ylabel="Voltage [µV]", title=method_label(method),
                                  x_ticks=False, x_spine=False))
        if old is not None and len(old) == len(self.axes):
            for axes, ylim in zip(self.axes, old):
                axes.ylim = ylim

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    def all_axes(self) -> list[Axes]:
        return list(self.axes)

    def panel_at(self, x: float, y: float):
        for index, axes in enumerate(self.axes):
            if axes.contains(x, y):
                return str(index), axes
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        return False, True

    def linked(self, key: str) -> list[Axes]:
        # One voltage scale across the methods is what makes them comparable.
        return [axes for index, axes in enumerate(self.axes) if str(index) != key]

    def under(self, x: float, y: float):
        found = self.panel_at(x, y)
        return None if found is None else int(found[0])

    def describe(self, what) -> str:
        data = self.scene
        method = data.methods[what]
        count = int(np.asarray(data.waveforms.get(method, np.zeros((0, 0)))).shape[0])
        return (f"{method_label(method)}\n{count} spike{'' if count == 1 else 's'} "
                f"shown from electrode {data.wave_channel}")

    def pinnable(self, what) -> bool:
        return False                    # nothing here to keep marked

    def _scale_bar(self) -> float | None:
        """A round duration, in ms, no longer than 60% of the window."""
        data = self.scene
        if not self._length or data.fs <= 0:
            return None
        window_ms = self._length / data.fs * 1000.0
        return next((c for c in (2.0, 1.0, 0.5, 0.2, 0.1) if c <= window_ms * 0.6), None)

    def paint(self, painter: QPainter) -> None:
        data = self.scene
        width, height = self.size
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, data.rec_name.replace("_", ""), width)
        paint_title(painter, f"Unique spikes by method from electrode {data.wave_channel}",
                    width, top=38, size=13)
        bar_ms = self._scale_bar()
        cloud = QPen(QColor(120, 120, 120, 70), 0.6)
        cloud.setCosmetic(True)
        for index, axes in enumerate(self.axes):
            painter.save()
            axes.clip(painter)
            if self._clouds[index]:
                painter.save()
                painter.setTransform(axes.transform(), True)
                painter.setPen(cloud)
                painter.drawLines(self._clouds[index])
                painter.restore()
                mean = self._means[index]
                xs = np.asarray(axes.x_pixel(np.arange(len(mean))), dtype=float)
                ys = np.asarray(axes.y_pixel(mean), dtype=float)
                painter.setPen(QPen(INK, 2.0))
                painter.drawPolyline(QPolygonF([QPointF(x, y)
                                                for x, y in zip(xs.tolist(), ys.tolist())]))
            if bar_ms is not None:
                low, high = axes.ylim
                x0 = float(axes.x_pixel(self._length * 0.05))
                x1 = float(axes.x_pixel(self._length * 0.05 + bar_ms / 1000.0 * data.fs))
                y = float(axes.y_pixel(low + 0.09 * (high - low)))
                pen = QPen(INK, 2.5)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(x0, y), QPointF(x1, y))
                painter.setFont(figure_font(11))
                label = f"{bar_ms:g} ms" if bar_ms >= 1 else f"{bar_ms * 1000:g} µs"
                painter.drawText(QRectF(x0 - 40, y + 3, x1 - x0 + 80, 16),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
            painter.restore()
            axes.paint_frame(painter)
        painter.restore()
