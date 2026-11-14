"""The per-recording activity figures, drawn with ``QPainter``.

* :class:`HeatmapPainter` — one value per electrode as a coloured disc where
  the electrode is (``electrodeHeatMaps.m``): firing rate, burst rate, burst
  duration and the rest of that family. Pointing at an electrode names it and
  gives its value, on every panel and both colour bars at once.
* :class:`RasterPainter` — activity through time, a row per electrode or cell
  (``rasterPlot.m``; CAT-NAP's activity rasters), on one colour scale or on
  this recording's and the batch's. Panels zoom and pan together; pointing at
  a cell gives the electrode, the time and the value.
* :class:`BurstPainter` — what burst detection made of a recording: every
  spike, the spikes inside bursts, and how the inter-spike intervals within
  bursts differ from those outside.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen, QPolygonF

from meanap.native.axes import INK, Axes
from meanap.native.figure import (
    GROUND, SELECTED, FigurePainter, MatrixImage, colormap, paint_colour_bar,
)
from meanap.native.output import figure_font
from meanap.native.scene import BurstScene, HeatmapScene, RasterScene

__all__ = ["HeatmapPainter", "RasterPainter", "BurstPainter"]

NO_VALUE = QColor("#d3d3d3")


class HeatmapPainter(FigurePainter):
    """Draws an electrode heatmap: one panel per colour scale, side by side.

    What a view points at is the row of an electrode in the scene.
    """

    PANEL = (600.0, 520.0)

    def __init__(self, scene: HeatmapScene, size: tuple[float, float] | None = None):
        count = max(len(scene.panels), 1)
        super().__init__(scene, size or (self.PANEL[0] * count, self.PANEL[1]))
        table = colormap(scene.cmap)
        #: Whether any electrode has a value, and so whether there is a colour bar.
        self.has_scale = bool(np.isfinite(scene.values).any())
        self._colours = []
        for _title, low, high in scene.panels:
            span = high - low if high > low else 1.0
            t = np.clip((np.nan_to_num(scene.values, nan=low) - low) / span, 0, 1)
            self._colours.append(np.asarray(table(t), dtype=float))

    # ── geometry ─────────────────────────────────────────────────────────────

    def _panel(self, index: int) -> tuple[QRectF, QRectF, float, tuple[float, float]]:
        """Panel *index*: its plot area, its colour bar, pixels per unit, data centre."""
        scene = self.scene
        width, height = self.size
        each = width / max(len(scene.panels), 1)
        area = QRectF(index * each + 24, 58, each - 24 - 128, height - 58 - 26)
        pad = scene.diameter * 0.75
        x0, x1 = float(scene.xy[:, 0].min()) - pad, float(scene.xy[:, 0].max()) + pad
        y0, y1 = float(scene.xy[:, 1].min()) - pad, float(scene.xy[:, 1].max()) + pad
        scale = min(area.width() / max(x1 - x0, 1e-9), area.height() / max(y1 - y0, 1e-9))
        used_h = (y1 - y0) * scale
        used_w = (x1 - x0) * scale
        plot = QRectF(area.center().x() - used_w / 2, area.center().y() - used_h / 2,
                      used_w, used_h)
        bar = QRectF(plot.right() + 18, plot.top() + used_h * 0.08, 16, used_h * 0.84)
        return plot, bar, scale, ((x0 + x1) / 2, (y0 + y1) / 2)

    def _pixels(self, index: int) -> np.ndarray:
        plot, _bar, scale, (cx, cy) = self._panel(index)
        xy = self.scene.xy
        return np.column_stack([plot.center().x() + (xy[:, 0] - cx) * scale,
                                plot.center().y() - (xy[:, 1] - cy) * scale])

    def under(self, x: float, y: float):
        scene = self.scene
        for index in range(len(scene.panels)):
            _plot, _bar, scale, _centre = self._panel(index)
            at = self._pixels(index)
            distance = np.hypot(at[:, 0] - x, at[:, 1] - y)
            nearest = int(np.argmin(distance))
            if distance[nearest] <= max(scene.diameter * scale / 2, 4.0):
                return nearest
        return None

    def describe(self, what) -> str:
        scene = self.scene
        value = float(scene.values[what])
        said = "no value" if np.isnan(value) else f"{value:.4g}"
        return f"{scene.noun.capitalize()} {scene.names[what]}\n{scene.label}: {said}"

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        marked = self.marked
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        each = width / max(len(scene.panels), 1)
        for index, (title, low, high) in enumerate(scene.panels):
            plot, bar, scale, _centre = self._panel(index)
            painter.setPen(INK)
            painter.setFont(figure_font(14))
            painter.drawText(QRectF(index * each + 8, 10, each - 16, 36),
                             Qt.AlignmentFlag.AlignCenter, title)
            radius = scene.diameter * scale / 2
            outline = QPen(GROUND, 1) if radius >= 5 else Qt.PenStyle.NoPen
            for (x, y), value, colour in zip(self._pixels(index).tolist(),
                                             scene.values.tolist(), self._colours[index]):
                painter.setPen(outline)
                painter.setBrush(NO_VALUE if np.isnan(value)
                                 else QColor.fromRgbF(*(float(c) for c in colour[:3])))
                painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            mark = None
            if marked is not None:
                x, y = self._pixels(index)[marked].tolist()
                painter.setPen(QPen(SELECTED, 2.5))
                painter.drawEllipse(QPointF(x, y), radius + 3, radius + 3)
                mark = float(scene.values[marked])
            # No electrode has a value — no bursts were detected, say — so there
            # is no scale to show.
            if self.has_scale:
                paint_colour_bar(painter, bar, scene.cmap, low, high, label=scene.label,
                                 mark=mark)
        painter.restore()


def _clock(seconds: float, bin_s: float = 1.0) -> str:
    """A time into the recording, as precisely as its bins are wide."""
    minutes, rest = divmod(float(seconds), 60.0)
    if bin_s >= 1.0:
        return f"{int(minutes)} min {int(round(rest)):02d} s"
    return f"{int(minutes)} min {rest:04.1f} s"


def _mark_cell(painter: QPainter, axes: Axes, row: int, x0: float, x1: float) -> None:
    """Mark the cell of *row* spanning *x0*–*x1* on the time axis, and its row faintly."""
    top, base = float(axes.y_pixel(row)), float(axes.y_pixel(row + 1))
    left, right = float(axes.x_pixel(x0)), float(axes.x_pixel(x1))
    painter.setPen(QPen(SELECTED, 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setOpacity(0.55)
    painter.drawRect(QRectF(axes.rect.left(), top, axes.rect.width(), max(base - top, 2.0)))
    painter.setOpacity(1.0)
    painter.setPen(QPen(SELECTED, 2))
    grow_x = max(0.0, (5 - (right - left)) / 2)
    grow_y = max(0.0, (5 - (base - top)) / 2)
    painter.drawRect(QRectF(left - grow_x, top - grow_y, right - left + 2 * grow_x,
                            base - top + 2 * grow_y))


class RasterPainter(FigurePainter):
    """Draws a raster: one panel per colour scale, stacked, sharing their axes.

    What a view points at is ``(row, bin)``.
    """

    standard_size = (1000.0, 800.0)
    #: The size with a single panel.
    SINGLE = (1000.0, 460.0)

    def __init__(self, scene: RasterScene, size: tuple[float, float] | None = None):
        super().__init__(scene, size or (self.standard_size if len(scene.panels) > 1
                                         else self.SINGLE))
        self._images = [MatrixImage(scene.counts, scene.cmap,
                                    -high if scene.symmetric else 0.0, high)
                        for _title, high in scene.panels]
        #: Seconds to one unit of the time axis.
        self._per = 60.0 if scene.time_unit == "min" else 1.0
        self.axes: list[Axes] = []
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = (self.axes[0].xlim, self.axes[0].ylim) if keep and self.axes else None
        scene = self.scene
        width, height = self.size
        rows = scene.counts.shape[0]
        count = max(len(scene.panels), 1)
        top, gap, bottom = 46.0, 96.0, 58.0
        panel_h = (height - top - bottom - gap * (count - 1)) / count
        self.axes, self.bars = [], []
        for index, (title, _high) in enumerate(scene.panels):
            rect = QRectF(72, top + index * (panel_h + gap), width - 72 - 132, panel_h)
            self.axes.append(Axes(rect, (0.0, scene.duration_s / self._per), (0.0, float(rows)),
                                  xlabel=f"Time ({scene.time_unit})",
                                  ylabel=scene.noun.capitalize(),
                                  title=title, y_down=True))
            self.bars.append(QRectF(rect.right() + 14, rect.top(), 16, panel_h))
        if old is not None:
            for axes in self.axes:
                axes.xlim, axes.ylim = old

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

    def linked(self, key: str) -> list[Axes]:
        return [axes for index, axes in enumerate(self.axes) if str(index) != key]

    def under(self, x: float, y: float):
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        time, row = panel[1].to_data(x, y)
        row, column = int(np.floor(row)), int(np.floor(time * self._per / self.scene.bin_s))
        rows, columns = self.scene.counts.shape
        return (row, column) if 0 <= row < rows and 0 <= column < columns else None

    def describe(self, what) -> str:
        scene = self.scene
        row, column = what
        name = scene.names[row] if row < len(scene.names) else str(row + 1)
        value = float(scene.counts[row, column])
        said = "no value" if np.isnan(value) else f"{value:.4g} {scene.unit}".rstrip()
        return (f"{scene.noun.capitalize()} {name} at "
                f"{_clock(column * scene.bin_s, scene.bin_s)}\n{said}")

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        marked = self.marked
        each = scene.bin_s / self._per          # a column, on the time axis
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for axes, bar, image, (_title, high) in zip(
                self.axes, self.bars, self._images, scene.panels):
            (t0, t1), (r0, r1) = axes.xlim, axes.ylim
            painter.save()
            axes.clip(painter)
            image.paint(painter, axes.rect, QRectF(t0 / each, r0, (t1 - t0) / each, r1 - r0))
            mark = None
            if marked is not None:
                row, column = marked
                _mark_cell(painter, axes, row, column * each, (column + 1) * each)
                mark = float(scene.counts[row, column])
            painter.restore()
            axes.paint_frame(painter)
            paint_colour_bar(painter, bar, scene.cmap, -high if scene.symmetric else 0.0,
                             high, label=scene.label, mark=mark)
        painter.restore()


OUTSIDE, WITHIN = QColor("#1f77b4"), QColor("#d62728")


def _interval(seconds: float) -> str:
    """An inter-spike interval, in the unit it reads best in."""
    return f"{seconds * 1000:.3g} ms" if seconds < 1.0 else f"{seconds:.3g} s"


def _plain(value: float) -> str:
    """A tick value without an exponent: 0.00001, not 1e-05."""
    return f"{value:.8f}".rstrip("0").rstrip(".") if value < 1 else f"{value:g}"


class BurstPainter(FigurePainter):
    """Draws the burst-detection figure: two rasters and the ISI distributions.

    What a view points at is ``("raster", panel, row, bin)`` or ``("isi", bin)``.
    The rasters zoom and pan together; the distribution is only read.
    """

    standard_size = (1000.0, 1000.0)
    TITLES = ("Downsampled raster", "Raster with only bursts")

    def __init__(self, scene: BurstScene, size: tuple[float, float] | None = None):
        super().__init__(scene, size)
        self._highs = [max(float(m.max()) if m.size else 0.0, 1.0)
                       for m in (scene.full, scene.bursts)]
        # The largest count of the bins sharing a pixel, so that a single
        # spike stays visible with the whole recording in view.
        self._images = [MatrixImage(m, scene.cmap, 0.0, high, pool="max")
                        for m, high in zip((scene.full, scene.bursts), self._highs)]
        self.axes: list[Axes] = []
        self.isi: Axes | None = None
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = (self.axes[0].xlim, self.axes[0].ylim) if keep and self.axes else None
        scene = self.scene
        width, height = self.size
        rows = scene.full.shape[0]
        top, gap, bottom = 46.0, 84.0, 58.0
        panel_h = (height - top - bottom - gap * 2) / 3
        self.axes, self.bars = [], []
        for index, title in enumerate(self.TITLES):
            rect = QRectF(72, top + index * (panel_h + gap), width - 72 - 132, panel_h)
            self.axes.append(Axes(rect, (0.0, scene.duration_s), (0.0, float(rows)),
                                  xlabel="Time (s)", ylabel=scene.noun.capitalize(),
                                  title=title, y_down=True))
            self.bars.append(QRectF(rect.right() + 14, rect.top(), 16, panel_h))
        if old is not None:
            for axes in self.axes:
                axes.xlim, axes.ylim = old
        rect = QRectF(72, top + 2 * (panel_h + gap), width - 72 - 132, panel_h)
        edges = scene.isi_edges
        if edges is None:
            xlim, peak = (-3.0, 1.0), 1.0
        else:
            xlim = (float(np.log10(edges[0])), float(np.log10(edges[-1])))
            peak = max([float(d.max()) for d in (scene.isi_outside, scene.isi_within)
                        if d is not None] or [1.0]) * 1.08 or 1.0
        # The axis is the logarithm of the interval, lettered with the interval.
        self.isi = Axes(rect, xlim, (0.0, peak), xlabel="Inter-spike interval (s)",
                        ylabel="Probability density",
                        title="ISI distribution: within vs. outside bursts")
        decades = range(int(np.ceil(xlim[0] - 1e-9)), int(np.floor(xlim[1] + 1e-9)) + 1)
        ticks = [(float(k), _plain(10.0 ** k)) for k in decades]
        if len(ticks) < 2:
            ticks = [(float(np.log10(m * 10.0 ** k)), _plain(m * 10.0 ** k))
                     for k in range(int(np.floor(xlim[0])), int(np.ceil(xlim[1])) + 1)
                     for m in (1, 2, 5)]
        self.isi.x_tick_values = ticks

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    def all_axes(self) -> list[Axes]:
        return list(self.axes)

    def panel_at(self, x: float, y: float):
        for index, axes in enumerate(self.axes):
            if axes.contains(x, y):
                return str(index), axes
        if self.isi.contains(x, y):
            return "isi", self.isi
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        return (False, False) if key == "isi" else (True, True)

    def linked(self, key: str) -> list[Axes]:
        if key == "isi":
            return []
        return [axes for index, axes in enumerate(self.axes) if str(index) != key]

    def under(self, x: float, y: float):
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        key, axes = panel
        scene = self.scene
        if key == "isi":
            if scene.isi_edges is None:
                return None
            at = int(np.searchsorted(np.log10(scene.isi_edges), axes.to_data(x, y)[0]) - 1)
            return ("isi", at) if 0 <= at < len(scene.isi_edges) - 1 else None
        time, row = axes.to_data(x, y)
        row, column = int(np.floor(row)), int(np.floor(time / scene.bin_s))
        rows, columns = scene.full.shape
        if 0 <= row < rows and 0 <= column < columns:
            return ("raster", int(key), row, column)
        return None

    def describe(self, what) -> str:
        scene = self.scene
        if what[0] == "isi":
            at = what[1]
            low, high = scene.isi_edges[at], scene.isi_edges[at + 1]
            parts = [f"{label}: {density[at]:.3g}" if density is not None
                     else f"{label}: none"
                     for label, density in (("outside bursts", scene.isi_outside),
                                            ("within bursts", scene.isi_within))]
            return f"Intervals of {_interval(low)} to {_interval(high)}\n" + "; ".join(parts)
        _kind, panel, row, column = what
        name = scene.names[row] if row < len(scene.names) else str(row + 1)
        count = int((scene.bursts if panel else scene.full)[row, column])
        spikes = "1 spike" if count == 1 else f"{count} spikes"
        where = " inside bursts" if panel else ""
        return (f"{scene.noun.capitalize()} {name} at "
                f"{_clock(column * scene.bin_s, scene.bin_s)}\n"
                f"{spikes}{where} in {scene.bin_s:g} s")

    # ── painting ─────────────────────────────────────────────────────────────

    def _steps(self, density: np.ndarray) -> QPolygonF:
        """The outline of a histogram, as matplotlib's ``histtype="step"`` draws it."""
        axes = self.isi
        xs = np.asarray(axes.x_pixel(np.log10(self.scene.isi_edges)), dtype=float)
        ys = np.asarray(axes.y_pixel(density), dtype=float)
        base = float(axes.y_pixel(0.0))
        points = [QPointF(float(xs[0]), base)]
        for i, y in enumerate(ys.tolist()):
            points += [QPointF(float(xs[i]), y), QPointF(float(xs[i + 1]), y)]
        points.append(QPointF(float(xs[-1]), base))
        return QPolygonF(points)

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        marked = self.marked
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for index, (axes, bar, image, high) in enumerate(
                zip(self.axes, self.bars, self._images, self._highs)):
            (t0, t1), (r0, r1) = axes.xlim, axes.ylim
            painter.save()
            axes.clip(painter)
            image.paint(painter, axes.rect,
                        QRectF(t0 / scene.bin_s, r0, (t1 - t0) / scene.bin_s, r1 - r0))
            mark = None
            if marked is not None and marked[0] == "raster":
                _kind, _panel, row, column = marked
                _mark_cell(painter, axes, row, column * scene.bin_s,
                           (column + 1) * scene.bin_s)
                mark = float((scene.bursts if index else scene.full)[row, column])
            painter.restore()
            axes.paint_frame(painter)
            paint_colour_bar(painter, bar, scene.cmap, 0.0, high,
                             label=f"Spikes per {scene.bin_s:g} s", mark=mark)
        self._paint_isi(painter, marked)
        painter.restore()

    def _paint_isi(self, painter: QPainter, marked) -> None:
        scene, axes = self.scene, self.isi
        font = figure_font(12)
        painter.setFont(font)
        if scene.isi_edges is None:
            axes.paint_frame(painter)
            painter.setPen(INK)
            painter.drawText(axes.rect, Qt.AlignmentFlag.AlignCenter,
                             "Too few spikes for a distribution")
            return
        painter.save()
        axes.clip(painter)
        if marked is not None and marked[0] == "isi":
            edges = np.log10(scene.isi_edges[marked[1]:marked[1] + 2])
            left, right = (float(v) for v in axes.x_pixel(edges))
            band = QColor(SELECTED)
            band.setAlphaF(0.18)
            painter.fillRect(QRectF(left, axes.rect.top(), max(right - left, 1.5),
                                    axes.rect.height()), band)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for colour, density in ((OUTSIDE, scene.isi_outside), (WITHIN, scene.isi_within)):
            if density is not None:
                painter.setPen(QPen(colour, 1.6))
                painter.drawPolyline(self._steps(density))
        painter.restore()
        axes.paint_frame(painter)
        # The key, to the right of the panel where the rasters have their colour bars.
        line = QFontMetricsF(font).height()
        left, top = axes.rect.right() + 14, axes.rect.top() + 4
        for row, (colour, label, count) in enumerate((
                (OUTSIDE, "Outside bursts", scene.n_outside),
                (WITHIN, "Within bursts", scene.n_within))):
            y = top + row * (line + 8)
            painter.setPen(QPen(colour, 2.2))
            painter.drawLine(QPointF(left, y + line / 2), QPointF(left + 18, y + line / 2))
            painter.setPen(INK)
            painter.drawText(QRectF(left + 24, y, 110, line),
                             Qt.AlignmentFlag.AlignVCenter, label)
