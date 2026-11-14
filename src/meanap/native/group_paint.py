"""The figures that compare recordings, drawn with ``QPainter``.

* :class:`ComparisonPainter` — half-violins of one metric across groups and
  ages. Pointing at a point says which recording (and node) it is and its
  value; pointing at a violin gives its count, mean and standard error.
  Clicking a point marks every point of that recording, in every panel — at
  node level, all of that recording's nodes. The panels share their y axis
  and zoom along it together.
* :class:`LinePainter` — mean ± SEM lines, a panel per group. Pointing at a
  marker reads it; clicking a series (an age, a role) keeps it drawn in full
  in every panel and fades the rest.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen, QPolygonF

from meanap.native.axes import INK, Axes
from meanap.native.figure import GROUND, SELECTED, FigurePainter, paint_dots
from meanap.native.group_scene import ComparisonScene, LineScene
from meanap.native.output import figure_font

__all__ = ["ComparisonPainter", "LinePainter"]

POINT_R = 3.2
MEAN_R = 7.0
REACH = 7.0
MUTED = QColor("#666666")
FADED = 0.2


def _colour(rgb, alpha: float = 1.0) -> QColor:
    colour = QColor.fromRgbF(*(float(c) for c in rgb[:3]))
    colour.setAlphaF(alpha)
    return colour


def _key_width(title: str, names) -> float:
    """Room a key needs: its swatch, then its longest name or heading."""
    metrics = QFontMetricsF(figure_font(12))
    widest = max([metrics.horizontalAdvance(str(n)) for n in names] + [
        metrics.horizontalAdvance(title) - 32 if title else 0.0])
    return 22 + 32 + widest + 16


def _paint_key(painter: QPainter, left: float, top: float, title: str,
               items: list[tuple[str, tuple]], *, swatch: str = "box",
               chosen: str | None = None) -> None:
    """A key: an optional heading, then a swatch and a name per row."""
    font = figure_font(12)
    painter.save()
    painter.setFont(font)
    line = QFontMetricsF(font).height()
    y = top
    if title:
        painter.setPen(INK)
        painter.drawText(QRectF(left, y, 220, line), Qt.AlignmentFlag.AlignVCenter, title)
        y += line + 4
    for name, colour in items:
        alpha = 1.0 if chosen in (None, name) else FADED * 1.5
        if swatch == "line":
            painter.setPen(QPen(_colour(colour, alpha), 3.5))
            painter.drawLine(QPointF(left, y + line / 2), QPointF(left + 24, y + line / 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_colour(colour, alpha))
            painter.drawRect(QRectF(left + 4, y + line / 2 - 7, 14, 14))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(INK)
        painter.drawText(QRectF(left + 32, y, 260, line), Qt.AlignmentFlag.AlignVCenter, name)
        y += line + 6
    painter.restore()


# ── half-violins ──────────────────────────────────────────────────────────────


class ComparisonPainter(FigurePainter):
    """Draws a comparison: a panel of half-violins per group or per age.

    What a view points at is ``("point", panel, violin, k)`` or
    ``("violin", panel, violin)``.
    """

    PANEL_W, HEIGHT = 288.0, 520.0
    LEFT, KEY_W = 96.0, 190.0

    def __init__(self, scene: ComparisonScene, size: tuple[float, float] | None = None):
        n_series = len(scene.legend[1]) if scene.legend else 0
        each = self.PANEL_W * max(1.0, n_series * 0.6)
        self._key_w = (max(self.KEY_W, _key_width(scene.legend[0],
                                                  [n for n, _ in scene.legend[1]]))
                       if scene.legend else 24.0)
        standard = (self.LEFT + each * max(len(scene.panels), 1) + self._key_w, self.HEIGHT)
        super().__init__(scene, size or standard)
        self.axes: list[Axes] = []
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = self.axes[0].ylim if keep and self.axes else None
        scene = self.scene
        width, height = self.size
        count = max(len(scene.panels), 1)
        each = (width - self.LEFT - self._key_w) / count
        bottom = 64.0 + (22.0 if scene.note else 0.0)
        self.axes = []
        for index, panel in enumerate(scene.panels):
            rect = QRectF(self.LEFT + index * each + (0 if index == 0 else 18), 46,
                          each - (18 if index else 0) - 14, height - 46 - bottom)
            axes = Axes(rect, scene.xlim, scene.ylim, xlabel=scene.xlabel,
                        ylabel=scene.ylabel if index == 0 else "", title=panel.title,
                        y_ticks=index == 0)
            axes.x_tick_values = list(scene.ticks)
            self.axes.append(axes)
        if old is not None:
            for axes in self.axes:
                axes.ylim = old

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
        return [axes for index, axes in enumerate(self.axes) if str(index) != key]

    # ── where things are ─────────────────────────────────────────────────────

    def _points(self, axes: Axes, violin) -> np.ndarray:
        x = violin.pos - (violin.width + violin.gap) + violin.jitter * violin.width
        return np.column_stack([axes.x_pixel(x), axes.y_pixel(violin.values)])

    def under(self, x: float, y: float):
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        index = int(panel[0])
        axes = panel[1]
        best, best_d = None, REACH
        for v_index, violin in enumerate(self.scene.panels[index].violins):
            at = self._points(axes, violin)
            distance = np.hypot(at[:, 0] - x, at[:, 1] - y)
            k = int(np.argmin(distance))
            if distance[k] <= best_d:
                best, best_d = ("point", index, v_index, k), float(distance[k])
        if best is not None:
            return best
        data_x, data_y = axes.to_data(x, y)
        for v_index, violin in enumerate(self.scene.panels[index].violins):
            left = violin.pos - violin.width - violin.gap
            right = violin.pos + violin.gap + violin.width
            low = min(float(violin.curve_y.min()), violin.mean - violin.sem)
            high = max(float(violin.curve_y.max()), violin.mean + violin.sem)
            if left <= data_x <= right and low <= data_y <= high:
                return ("violin", index, v_index)
        return None

    def describe(self, what) -> str:
        scene = self.scene
        violin = scene.panels[what[1]].violins[what[2]]
        if what[0] == "point":
            k = what[3]
            return f"{violin.points[k]}\n{scene.ylabel}: {violin.values[k]:.4g}"
        n = len(violin.values)
        things = "recordings" if scene.noun == "recording" else f"{scene.noun}s"
        return (f"{violin.label}: {n} {things if n != 1 else things[:-1]}\n"
                f"mean {violin.mean:.4g} ± {violin.sem:.3g} (SEM)")

    def info_at(self, x: float, y: float) -> str | None:
        """The metric: the title band, or the y axis's label and ticks."""
        if self.axes:
            rect = self.axes[0].rect
            if x < rect.left() and rect.top() <= y <= rect.bottom():
                return "title"
        return super().info_at(x, y)

    def recording_of(self, what) -> str | None:
        if what is None or what[0] != "point":
            return None
        return self.scene.panels[what[1]].violins[what[2]].recordings[what[3]] or None

    def _marked_recording(self) -> str | None:
        return self.recording_of(self.marked)

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        marked = self.marked
        recording = self._marked_recording()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for index, (axes, panel) in enumerate(zip(self.axes, scene.panels)):
            painter.save()
            axes.clip(painter)
            for v_index, violin in enumerate(panel.violins):
                lit = (marked is not None and marked[0] == "violin"
                       and marked[1:] == (index, v_index))
                self._paint_violin(painter, axes, violin, lit)
            if recording is not None:
                self._paint_recording(painter, axes, panel, recording,
                                      marked if marked[1] == index else None)
            painter.restore()
            axes.paint_frame(painter)
            if scene.empty:
                painter.setPen(MUTED)
                painter.setFont(figure_font(13))
                painter.drawText(axes.rect, Qt.AlignmentFlag.AlignCenter, scene.empty)
        if scene.legend:
            title, items = scene.legend
            _paint_key(painter, self.axes[-1].rect.right() + 22, self.axes[-1].rect.top(),
                       title, items)
        if scene.note:
            painter.setPen(MUTED)
            painter.setFont(figure_font(11))
            painter.drawText(QRectF(0, height - 24, width, 20), Qt.AlignmentFlag.AlignCenter,
                             scene.note)
        painter.restore()

    def _paint_violin(self, painter: QPainter, axes: Axes, violin, lit: bool) -> None:
        colour = _colour(violin.colour)
        # The density, to the right of the centre line.
        base = violin.pos + violin.gap
        xs = axes.x_pixel(base + violin.curve_x * violin.width)
        ys = axes.y_pixel(violin.curve_y)
        x0 = float(axes.x_pixel(base))
        if len(ys) > 1:
            shape = QPolygonF([QPointF(x0, float(ys[0]))]
                              + [QPointF(float(a), float(b)) for a, b in zip(xs, ys)]
                              + [QPointF(x0, float(ys[-1]))])
            painter.setPen(QPen(colour, 1))
            painter.setBrush(colour)
            painter.drawPolygon(shape)
        else:
            painter.setPen(QPen(colour, 2))
            painter.drawLine(QPointF(x0, float(ys[0])), QPointF(float(xs[0]), float(ys[0])))
        # The points, to the left.
        paint_dots(painter, self._points(axes, violin), POINT_R, colour)
        # The mean and its standard error, on the line.
        mean_colour = _colour(violin.mean_colour)
        x = float(axes.x_pixel(violin.pos))
        top, bottom = (float(axes.y_pixel(violin.mean + s)) for s in (violin.sem, -violin.sem))
        pen = QPen(mean_colour, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        painter.setPen(QPen(GROUND, 1.1))
        painter.setBrush(mean_colour)
        y = float(axes.y_pixel(violin.mean))
        painter.drawEllipse(QPointF(x, y), MEAN_R, MEAN_R)
        if lit:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(SELECTED, 2.5))
            painter.drawEllipse(QPointF(x, y), MEAN_R + 3, MEAN_R + 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_recording(self, painter: QPainter, axes: Axes, panel, recording: str,
                         exact) -> None:
        """Ring every point of *recording*, and the one pointed at more boldly."""
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(SELECTED, 1.6))
        for violin in panel.violins:
            mine = np.flatnonzero(np.asarray(violin.recordings) == recording)
            if not len(mine):
                continue
            at = self._points(axes, violin)[mine]
            for x, y in at.tolist():
                painter.drawEllipse(QPointF(x, y), POINT_R + 2, POINT_R + 2)
        if exact is not None:
            violin = panel.violins[exact[2]]
            x, y = self._points(axes, violin)[exact[3]].tolist()
            painter.setPen(QPen(SELECTED, 2.6))
            painter.drawEllipse(QPointF(x, y), POINT_R + 4, POINT_R + 4)


# ── lines ─────────────────────────────────────────────────────────────────────


class LinePainter(FigurePainter):
    """Draws mean ± SEM lines, a panel per group, stacked.

    What a view points at is ``(panel, series, x index)``; a pinned series —
    one age, say — stays drawn in full in every panel.
    """

    WIDTH, PANEL_H = 940.0, 300.0
    LEFT, KEY_W = 100.0, 230.0

    def __init__(self, scene: LineScene, size: tuple[float, float] | None = None):
        names = [s.label for p in scene.panels for s in p.series]
        self._key_w = max(160.0, _key_width(scene.legend_title, names) if names else 0.0)
        standard = (self.WIDTH - self.KEY_W + self._key_w,
                    max(self.PANEL_H * len(scene.panels), self.PANEL_H) + 20)
        super().__init__(scene, size or standard)
        self.axes: list[Axes] = []
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = [axes.ylim for axes in self.axes] if keep and self.axes else None
        scene = self.scene
        width, height = self.size
        count = max(len(scene.panels), 1)
        each = (height - 10) / count
        n = len(scene.ticks)
        self.axes = []
        for index, panel in enumerate(scene.panels):
            rect = QRectF(self.LEFT, index * each + 40, width - self.LEFT - self._key_w,
                          each - 40 - 58)
            axes = Axes(rect, (0.5, n + 0.5), panel.ylim, xlabel=scene.xlabel,
                        ylabel=scene.ylabel, title=panel.title)
            axes.x_tick_values = [(float(k + 1), t) for k, t in enumerate(scene.ticks)]
            self.axes.append(axes)
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

    def under(self, x: float, y: float):
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        index, axes = int(panel[0]), panel[1]
        column = int(round(axes.to_data(x, y)[0])) - 1
        if not 0 <= column < len(self.scene.ticks):
            return None
        best, best_d = None, REACH * 1.5
        for s_index, series in enumerate(self.scene.panels[index].series):
            mean = series.means[column]
            if not np.isfinite(mean):
                continue
            distance = float(np.hypot(float(axes.x_pixel(column + 1)) - x,
                                      float(axes.y_pixel(mean)) - y))
            if distance <= best_d:
                best, best_d = (index, s_index, column), distance
        return best

    def describe(self, what) -> str:
        scene = self.scene
        index, s_index, column = what
        panel = scene.panels[index]
        series = panel.series[s_index]
        n = int(series.counts[column])
        x = scene.ticks[column]
        at = scene.x_format.format(x)
        name = f"{scene.series_noun} {series.label}".strip() if scene.series_noun else series.label
        return (f"{panel.title}, {name}, {at}\n"
                f"{series.means[column]:.4g} ± {series.sems[column]:.3g} (SEM), "
                f"n = {n}")

    def _chosen(self) -> str | None:
        marked = self.marked
        if marked is None:
            return None
        return self.scene.panels[marked[0]].series[marked[1]].label

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        chosen = self._chosen()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for index, (axes, panel) in enumerate(zip(self.axes, scene.panels)):
            painter.save()
            axes.clip(painter)
            order = sorted(range(len(panel.series)),
                           key=lambda s: panel.series[s].label == chosen)
            for s_index in order:
                series = panel.series[s_index]
                alpha = 1.0 if chosen in (None, series.label) else FADED
                self._paint_series(painter, axes, series, alpha)
            marked = self.marked
            if marked is not None and marked[0] == index:
                series = panel.series[marked[1]]
                x = float(axes.x_pixel(marked[2] + 1))
                y = float(axes.y_pixel(series.means[marked[2]]))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(SELECTED, 2.5))
                painter.drawEllipse(QPointF(x, y), 8, 8)
            painter.restore()
            axes.paint_frame(painter)
            items = [(s.label, s.colour) for s in panel.series]
            if items:
                font = QFontMetricsF(figure_font(12))
                rows = len(items) + (1 if scene.legend_title else 0)
                top = axes.rect.center().y() - rows * (font.height() + 6) / 2
                _paint_key(painter, axes.rect.right() + 20, top, scene.legend_title, items,
                           swatch="line", chosen=chosen)
        painter.restore()

    def _paint_series(self, painter: QPainter, axes: Axes, series, alpha: float) -> None:
        ok = np.flatnonzero(np.isfinite(series.means))
        if not len(ok):
            return
        xs = np.asarray(axes.x_pixel(ok + 1.0), dtype=float)
        top = np.asarray(axes.y_pixel(series.means[ok] + series.sems[ok]), dtype=float)
        bottom = np.asarray(axes.y_pixel(series.means[ok] - series.sems[ok]), dtype=float)
        middle = np.asarray(axes.y_pixel(series.means[ok]), dtype=float)
        # The band, then the line over it, then the markers: matplotlib's order.
        # A gap where an age has no value breaks the line and the band, as
        # NaN does in matplotlib.
        runs = np.split(np.arange(len(ok)), np.flatnonzero(np.diff(ok) > 1) + 1)
        band = _colour(series.colour, 0.3 * alpha)
        line = _colour(series.colour, alpha)
        for run in runs:
            if len(run) > 1:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(band)
                painter.drawPolygon(QPolygonF(
                    [QPointF(xs[i], top[i]) for i in run]
                    + [QPointF(xs[i], bottom[i]) for i in run[::-1]]))
                pen = QPen(line, 4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF([QPointF(xs[i], middle[i]) for i in run]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(line)
        for x, y in zip(xs.tolist(), middle.tolist()):
            painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
