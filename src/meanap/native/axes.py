"""A pair of axes for ``QPainter`` figures: limits, ticks, labels, zoom.

The network plot has no axes; most other figures do. This is the small shared
piece they need: a rectangle of the figure that shows a range of x and y, knows
how to turn data into pixels and back, draws its own spines, ticks and labels,
and can be zoomed and panned by an interactive view.
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen

from meanap.native.output import figure_font

__all__ = ["Axes", "nice_ticks", "tick_label", "INK"]

INK = QColor("#16181d")
TICK_PX = 4
TICK_FONT = 11
LABEL_FONT = 12
TITLE_FONT = 13


def nice_ticks(low: float, high: float, target: int = 5,
               steps=(1, 2, 5, 10)) -> tuple[list[float], float]:
    """Round tick values covering [low, high], and the step between them."""
    low, high = (low, high) if low <= high else (high, low)
    span = high - low
    if not math.isfinite(span) or span <= 0:
        return [low], 1.0
    raw = span / max(target, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in steps if m * magnitude >= raw)
    first = math.ceil(low / step - 1e-9)
    last = math.floor(high / step + 1e-9)
    return [k * step for k in range(first, last + 1)], step


def tick_label(value: float, step: float) -> str:
    """*value* written to the precision *step* calls for, without trailing noise."""
    decimals = max(0, -math.floor(math.log10(step) + 1e-9)) if step > 0 else 0
    text = f"{value:.{min(decimals, 10)}f}"
    return "0" if float(text) == 0 else text


class Axes:
    """One plot area. ``rect`` is where the data is drawn; labels go outside it."""

    def __init__(self, rect: QRectF, xlim: tuple[float, float], ylim: tuple[float, float],
                 *, xlabel: str = "", ylabel: str = "", title: str = "",
                 y_down: bool = False, x_ticks: bool = True, y_ticks: bool = True,
                 x_spine: bool = True) -> None:
        self.rect = QRectF(rect)
        self.xlim, self.ylim = tuple(map(float, xlim)), tuple(map(float, ylim))
        self.home = (self.xlim, self.ylim)
        self.xlabel, self.ylabel, self.title = xlabel, ylabel, title
        #: y increases downward: a matrix, whose first row is at the top.
        self.y_down = y_down
        self.x_ticks, self.y_ticks = x_ticks, y_ticks
        self.x_spine = x_spine
        self.title_size = TITLE_FONT
        #: ``[(position, label)]`` to use instead of round numbers on the x axis
        #: — minutes on an axis counted in seconds, say.
        self.x_tick_values: list[tuple[float, str]] | None = None

    # ── data ↔ pixels ────────────────────────────────────────────────────────

    def x_pixel(self, x):
        (x0, x1), r = self.xlim, self.rect
        return r.left() + (np.asarray(x, dtype=float) - x0) / (x1 - x0) * r.width()

    def y_pixel(self, y):
        (y0, y1), r = self.ylim, self.rect
        t = (np.asarray(y, dtype=float) - y0) / (y1 - y0)
        return r.top() + t * r.height() if self.y_down else r.bottom() - t * r.height()

    def to_data(self, x: float, y: float) -> tuple[float, float]:
        (x0, x1), (y0, y1), r = self.xlim, self.ylim, self.rect
        tx = (x - r.left()) / r.width()
        ty = (y - r.top()) / r.height() if self.y_down else (r.bottom() - y) / r.height()
        return x0 + tx * (x1 - x0), y0 + ty * (y1 - y0)

    def contains(self, x: float, y: float) -> bool:
        return self.rect.contains(QPointF(x, y))

    # ── view ─────────────────────────────────────────────────────────────────

    @property
    def zoomed(self) -> bool:
        return (self.xlim, self.ylim) != self.home

    def reset(self) -> None:
        self.xlim, self.ylim = self.home

    def zoom(self, factor: float, x: float, y: float, *, along_x: bool = True,
             along_y: bool = True) -> None:
        """Magnify about pixel (x, y); never out past the home range."""
        at = self.to_data(x, y)
        for axis, on, centre in (("xlim", along_x, at[0]), ("ylim", along_y, at[1])):
            if not on:
                continue
            low, high = getattr(self, axis)
            home = self.home[0 if axis == "xlim" else 1]
            low = centre + (low - centre) / factor
            high = centre + (high - centre) / factor
            if high - low >= home[1] - home[0]:
                low, high = home
            setattr(self, axis, self._within(low, high, home))

    def pan(self, dx: float, dy: float, *, along_x: bool = True, along_y: bool = True) -> None:
        r = self.rect
        if along_x:
            low, high = self.xlim
            shift = -dx / r.width() * (high - low)
            self.xlim = self._within(low + shift, high + shift, self.home[0])
        if along_y:
            low, high = self.ylim
            shift = (-dy if self.y_down else dy) / r.height() * (high - low)
            self.ylim = self._within(low + shift, high + shift, self.home[1])

    @staticmethod
    def _within(low: float, high: float, home: tuple[float, float]) -> tuple[float, float]:
        """Slide [low, high] back inside *home*, keeping its width."""
        if low < home[0]:
            low, high = home[0], home[0] + (high - low)
        if high > home[1]:
            low, high = home[1] - (high - low), home[1]
        return max(low, home[0]), min(high, home[1])

    # ── drawing ──────────────────────────────────────────────────────────────

    def transform(self):
        """Data coordinates to pixels, as a transform to set on a painter.

        With it, shapes prepared once in data coordinates are drawn at any
        zoom; pens must be cosmetic to keep their width in pixels.
        """
        from PyQt6.QtGui import QTransform

        (x0, x1), (y0, y1), r = self.xlim, self.ylim, self.rect
        sx = r.width() / (x1 - x0)
        sy = r.height() / (y1 - y0)
        if self.y_down:
            return QTransform(sx, 0, 0, sy, r.left() - x0 * sx, r.top() - y0 * sy)
        return QTransform(sx, 0, 0, -sy, r.left() - x0 * sx, r.bottom() + y0 * sy)

    def clip(self, painter: QPainter) -> None:
        painter.setClipRect(self.rect)

    def paint_frame(self, painter: QPainter) -> None:
        """Spines on the left and bottom, ticks, tick labels, labels, title."""
        r = self.rect
        painter.save()
        painter.setClipping(False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(INK, 1))
        if self.x_spine:
            painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.drawLine(r.topLeft(), r.bottomLeft())
        font = figure_font(TICK_FONT)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        line = metrics.height()
        left_room = 0.0
        if self.x_ticks:
            if self.x_tick_values is not None:
                low, high = sorted(self.xlim)
                shown = [(v, text) for v, text in self.x_tick_values if low <= v <= high]
                # Thin them out when zoomed out far enough to crowd.
                keep = max(int(np.ceil(len(shown) * 34 / max(r.width(), 1))), 1)
                labelled = shown[keep - 1::keep] if keep > 1 else shown
            else:
                ticks, step = nice_ticks(*self.xlim, target=max(int(r.width() // 70), 2))
                labelled = [(value, tick_label(value, step)) for value in ticks]
            for value, text in labelled:
                x = float(self.x_pixel(value))
                painter.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + TICK_PX))
                painter.drawText(QRectF(x - 40, r.bottom() + TICK_PX + 1, 80, line),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 text)
        if self.y_ticks:
            ticks, step = nice_ticks(*self.ylim, target=max(int(r.height() // 30), 3))
            for value in ticks:
                y = float(self.y_pixel(value))
                text = tick_label(value, step)
                left_room = max(left_room, metrics.horizontalAdvance(text))
                painter.drawLine(QPointF(r.left() - TICK_PX, y), QPointF(r.left(), y))
                painter.drawText(QRectF(r.left() - TICK_PX - 3 - 80, y - line / 2, 80, line),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(figure_font(LABEL_FONT))
        if self.xlabel:
            top = r.bottom() + TICK_PX + (line + 3 if self.x_ticks else 2)
            painter.drawText(QRectF(r.left(), top, r.width(), line + 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             self.xlabel)
        if self.ylabel:
            painter.save()
            painter.translate(r.left() - TICK_PX - left_room - 14, r.center().y())
            painter.rotate(-90)
            painter.drawText(QRectF(-r.height() / 2, -line - 2, r.height(), line + 2),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                             self.ylabel)
            painter.restore()
        if self.title:
            font = figure_font(self.title_size)
            painter.setFont(font)
            rows = self.title.count("\n") + 1
            tall = QFontMetricsF(font).height() * rows
            painter.drawText(QRectF(r.left() - 40, r.top() - tall - 8, r.width() + 80, tall + 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                             self.title)
        painter.restore()
