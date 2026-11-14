"""Draws any :class:`meanap.native.chart.Chart` with ``QPainter``.

The look is the step-5 one (``tim-modern``): no spines and no tick marks,
soft grey gridlines carrying the scale, near-black ink, small sans-serif
lettering. Sizes given in points are drawn at 96/72 pixels to the point.

The layout follows what ``tight_layout`` does: each column of the grid gets
the left margin its widest y tick labels and y label need, each row the top
margin its titles need and the bottom margin its x tick labels and x label
need, and the panels share what is left. Around them go, when the chart has
them, the figure's title, its legend, a colour bar and the small print.

For a view: pointing at a mark that says what it is (``hover``) describes it;
pointing at a legend entry, or clicking either, picks out that series in every
panel and fades the others. Panels zoom along the axes they allow, and panels
that share an axis move together.
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFontMetricsF, QLinearGradient, QPainter,
                         QPen, QPolygonF)

from meanap.native.axes import Axes, nice_ticks, tick_label
from meanap.native.chart import (Band, Bars, Cells, Chart, ErrorBars, Labels, Legend, Line,
                                 Panel, Points, Polygon, Rule, Segments, Span, Text)
from meanap.native.figure import GROUND, SELECTED, FigurePainter, colormap, colour_image
from meanap.native.output import figure_font

__all__ = ["ChartPainter", "PX"]

#: Pixels to the point.
PX = 96.0 / 72.0
INK = QColor("#222222")
MUTED = QColor("#8a8a8a")
GRID = QColor("#c8c8c8")
FADED = 0.18
REACH = 7.0
EDGE = 6.0                              # blank border round the figure
DASHES = {"--": [3.7, 1.6], ":": [1.0, 1.65], "-.": [6.4, 1.6, 1.0, 1.6]}
_ALIGN_H = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight}
_ALIGN_V = {"top": Qt.AlignmentFlag.AlignTop, "center": Qt.AlignmentFlag.AlignVCenter,
            "bottom": Qt.AlignmentFlag.AlignBottom,
            "baseline": Qt.AlignmentFlag.AlignBottom}


def qcolour(rgba, fade: float = 1.0) -> QColor:
    r, g, b = (float(c) for c in rgba[:3])
    a = float(rgba[3]) if len(rgba) > 3 else 1.0
    colour = QColor.fromRgbF(min(max(r, 0), 1), min(max(g, 0), 1), min(max(b, 0), 1))
    colour.setAlphaF(min(max(a * fade, 0.0), 1.0))
    return colour


def font(pt: float, bold: bool = False):
    return figure_font(pt * PX, bold=bold)


def _pen(colour: QColor, width_pt: float, dash: str = "-", cap=Qt.PenCapStyle.RoundCap) -> QPen:
    pen = QPen(colour, max(width_pt * PX, 0.01))
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dash in DASHES:
        pen.setDashPattern(DASHES[dash])
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


def text_size(text: str, pt: float, bold: bool = False) -> tuple[float, float]:
    """Width and height of *text* (lines split on newlines) at *pt* points."""
    metrics = QFontMetricsF(font(pt, bold))
    lines = str(text).split("\n")
    return (max(metrics.horizontalAdvance(line) for line in lines),
            metrics.height() * len(lines))


def wrap(text: str, pt: float, width: float) -> str:
    """*text* broken into lines no wider than *width* pixels, at the spaces."""
    metrics = QFontMetricsF(font(pt))
    out = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}" if line else word
            if line and metrics.horizontalAdvance(trial) > width:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    return "\n".join(out)


def draw_text(painter: QPainter, x: float, y: float, text: str, pt: float, colour: QColor,
              ha: str = "center", va: str = "center", *, bold: bool = False,
              rotation: float = 0.0) -> QRectF:
    """Text anchored at pixel (x, y); returns the box it covers (unrotated)."""
    w, h = text_size(text, pt, bold)
    left = x - (w / 2 if ha == "center" else w if ha == "right" else 0.0)
    top = y - (h / 2 if va == "center" else h if va in ("bottom", "baseline") else 0.0)
    painter.save()
    painter.setFont(font(pt, bold))
    painter.setPen(colour)
    flags = _ALIGN_H.get(ha, Qt.AlignmentFlag.AlignHCenter) | Qt.AlignmentFlag.AlignVCenter
    if rotation:
        painter.translate(x, y)
        painter.rotate(-rotation)
        painter.drawText(QRectF(left - x, top - y, w + 2, h), flags, text)
    else:
        painter.drawText(QRectF(left, top, w + 2, h), flags, text)
    painter.restore()
    return QRectF(left, top, w, h)


def _finite(values) -> np.ndarray:
    values = np.asarray(values, dtype=float).ravel()
    return values[np.isfinite(values)]


def _log(values):
    values = np.asarray(values, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(values > 0, np.log10(np.where(values > 0, values, 1.0)), np.nan)


_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


# ── ranges ────────────────────────────────────────────────────────────────────


def _extent(mark, axis: str) -> tuple[np.ndarray, bool]:
    """The values *mark* spans along *axis*, and whether its first is a hard edge.

    A hard edge (a bar's base) gets no margin, as matplotlib's sticky edges.
    """
    x = axis == "x"
    if isinstance(mark, (Line, Points)):
        return (mark.x if x else mark.y), False
    if isinstance(mark, Band):
        if mark.vertical:
            return (np.concatenate([mark.low, mark.high]) if x else mark.x), False
        return (mark.x if x else np.concatenate([mark.low, mark.high])), False
    if isinstance(mark, Bars):
        along = (not mark.horizontal) == x
        if along:
            return np.concatenate([mark.pos - mark.width / 2, mark.pos + mark.width / 2]), False
        return np.concatenate([mark.base, mark.base + mark.length]), True
    if isinstance(mark, ErrorBars):
        ends = mark.ends("x" if x else "y")
        if ends is None:
            return (mark.x if x else mark.y), False
        return np.concatenate(ends), False
    if isinstance(mark, Rule):
        if (mark.axis == "x") == x:
            return np.array([mark.value]), False
        return (np.asarray(mark.extent, float) if mark.extent else np.array([])), False
    if isinstance(mark, Cells):
        x0, x1, y0, y1 = mark.box()
        return np.array([x0, x1] if x else [y0, y1]), True
    if isinstance(mark, Segments):
        cols = [0, 2] if x else [1, 3]
        return mark.lines[:, cols].ravel(), False
    if isinstance(mark, Polygon):
        return (mark.x if x else mark.y), False
    return np.array([]), False


def auto_limits(panels: list[Panel], axis: str, log: bool = False) -> tuple[float, float]:
    """The range matplotlib's autoscale would give the marks of *panels*."""
    values, hard, exact = [], [], True
    for panel in panels:
        for mark in panel.marks:
            v, sticky = _extent(mark, axis)
            v = _log(v) if log else np.asarray(v, float)
            v = _finite(v)
            if not len(v):
                continue
            values.append(v)
            if sticky and not isinstance(mark, Cells):
                hard.append(float(v[: len(v) // 2].min()) if len(v) > 1 else float(v[0]))
            if not isinstance(mark, Cells):
                exact = False
    if not values:
        return (0.0, 1.0)
    allv = np.concatenate(values)
    low, high = float(allv.min()), float(allv.max())
    if exact:                           # a matrix fills its axes exactly
        return low, high
    if high <= low:
        pad = max(abs(low) * 0.05, 0.05)
        return low - pad, high + pad
    pad = (high - low) * 0.05
    new_low, new_high = low - pad, high + pad
    for edge in hard:
        if abs(edge - low) < 1e-12:
            new_low = low
        if abs(edge - high) < 1e-12:
            new_high = high
    return new_low, new_high


def _auto_ticks(low: float, high: float, length_px: float, log: bool, pt: float,
                axis: str = "y"):
    """``[(value, label)]`` for an axis with no ticks given."""
    if log:
        first, last = math.ceil(low - 1e-9), math.floor(high + 1e-9)
        step = max(1, int(math.ceil((last - first + 1) / max(length_px / (pt * PX * 3), 2))))
        return [(float(k), f"10{str(k).translate(_SUPERSCRIPT)}")
                for k in range(first, last + 1, step)]
    # matplotlib's "auto": room for a label every 2 (y) or 3 (x) font sizes.
    target = int(min(max(length_px / (pt * PX * (3 if axis == "x" else 2)), 2), 9))
    ticks, step = nice_ticks(low, high, target=target, steps=(1, 2, 2.5, 5, 10))
    return [(v, _label(v, step)) for v in ticks]


def _label(value: float, step: float) -> str:
    """*value* to as many decimals as *step* has (0.25 needs two)."""
    decimals = 0
    while decimals < 10 and abs(round(step, decimals) - step) > abs(step) * 1e-6:
        decimals += 1
    text = f"{value:.{decimals}f}"
    return "0" if float(text) == 0 else text


# ── the painter ───────────────────────────────────────────────────────────────


class _Follow:
    """What a view moves when it moves a panel that another shares one axis with."""

    def __init__(self, axes: Axes, x: bool, y: bool):
        object.__setattr__(self, "_axes", axes)
        object.__setattr__(self, "_x", x)
        object.__setattr__(self, "_y", y)

    def __getattr__(self, name):
        return getattr(self._axes, name)

    def __setattr__(self, name, value):
        if (name == "xlim" and self._x) or (name == "ylim" and self._y):
            setattr(self._axes, name, value)


class ChartPainter(FigurePainter):
    """Draws a :class:`Chart`.

    What a view points at is ``(panel, mark, item)`` — the item of a mark (a
    point, a bar, a cell as ``(row, column)``) — or ``("key", name)`` for a
    legend entry.
    """

    def __init__(self, scene: Chart, size: tuple[float, float] | None = None):
        self.axes: list[Axes] = []
        self._hits: list[tuple[QRectF, str]] = []
        self.scene = scene
        super().__init__(scene, size or self._standard(scene))
        self._layout(keep=False)

    # ── layout ───────────────────────────────────────────────────────────────

    def _standard(self, chart: Chart) -> tuple[float, float]:
        """The size to save at: the panels get what matplotlib's axes would
        within the figure size, and the lettering round them is added on."""
        w, h = chart.size[0] * 96.0, chart.size[1] * 96.0
        self.size = (w, h)
        margins = self._margins(chart, self._home(chart))
        extra_w = margins["outer_w"] + sum(margins["left"]) + sum(margins["right"])
        extra_h = margins["outer_h"] + sum(margins["top"]) + sum(margins["bottom"])
        size = (round(w * 0.8 + extra_w), round(h * 0.8 + extra_h))
        # Lettering that reaches past the figure's edge — a long title, a
        # label set beside the last bar — widens it, as a tight bounding box
        # does in matplotlib.
        self.size = size
        self._layout(keep=False)
        left, right = self._overflow()
        if left or right:
            self._pad_lr = (left, right)
            size = (size[0] + round(left + right), size[1])
        return size

    def _overflow(self) -> tuple[float, float]:
        """How far lettering reaches past the left and right edges, in pixels."""
        lows, highs = [], []
        for axes, panel in zip(self.axes, self.scene.panels):
            if panel.title:
                w = text_size(panel.title, panel.title_size)[0]
                lows.append(axes.rect.center().x() - w / 2)
                highs.append(axes.rect.center().x() + w / 2)
            for mark in panel.marks:
                if isinstance(mark, Text):
                    box = self._text_box(panel, axes, mark)
                    if np.isfinite(box.left()) and np.isfinite(box.right()):
                        lows.append(box.left())
                        highs.append(box.right())
            if not panel.bare and not panel.twin and panel.xlabels and not panel.xtick_rotation:
                # The labels of ticks at the ends of the axis are centred on
                # them, so half of each hangs past the plot area.
                xlow, xhigh = sorted(axes.xlim)
                for value, label, _ in self._ticks(panel, axes.xlim, "x", axes.rect.width()):
                    if xlow - 1e-9 <= value <= xhigh + 1e-9:
                        x, w = float(axes.x_pixel(value)), text_size(label, panel.tick_size)[0]
                        if np.isfinite(x):
                            lows.append(x - w / 2)
                            highs.append(x + w / 2)
        if self.scene.title:
            w = text_size(self.scene.title, self.scene.title_size)[0]
            lows.append(self.size[0] / 2 - w / 2)
            highs.append(self.size[0] / 2 + w / 2)
        legend = self.scene.legend
        if legend is not None and legend.loc == "bottom" and legend.items:
            # Centred under the panels, so a row of long verdicts can run past
            # both edges of a narrow figure.
            w = self._legend_size(legend)[0] + legend.size * PX
            lows.append(self.size[0] / 2 - w / 2)
            highs.append(self.size[0] / 2 + w / 2)
        left = max(0.0, EDGE - min(lows)) if lows else 0.0
        right = max(0.0, max(highs) + EDGE - self.size[0]) if highs else 0.0
        return left, right

    def _home(self, chart: Chart) -> list[tuple[tuple, tuple]]:
        """Each panel's home x and y range, with shared axes made one."""
        def auto(panel, axis):
            given = panel.xlim if axis == "x" else panel.ylim
            log = axis == "y" and panel.ylog
            if given is not None:
                low, high = (float(given[0]), float(given[1]))
                return (_log(low).item(), _log(high).item()) if log else (low, high)
            share = panel.sharex if axis == "x" else panel.sharey
            group = [p for p in chart.panels
                     if share and (p.sharex if axis == "x" else p.sharey) == share] or [panel]
            return auto_limits(group, axis, log)

        return [(auto(p, "x"), auto(p, "y")) for p in chart.panels]

    def _ticks(self, panel: Panel, lims, axis: str, length_px: float) -> list[tuple]:
        given = panel.xticks if axis == "x" else panel.yticks
        if panel.bare:
            return []
        if given is not None:
            out = []
            for tick in given:
                value = float(tick[0])
                if axis == "y" and panel.ylog:
                    value = float(_log(value))
                out.append((value, str(tick[1]), tick[2] if len(tick) > 2 else None))
            return out
        log = axis == "y" and panel.ylog
        return [(v, t, None) for v, t in _auto_ticks(min(lims), max(lims), length_px, log,
                                                     panel.tick_size, axis)]

    def _panel_needs(self, panel: Panel, home) -> dict:
        """Pixels of lettering a panel needs on each side of its plot area."""
        tick_pad, label_pad, title_pad = 4 * PX, 4 * PX, 8 * PX
        left = bottom = top = right = 0.0
        if panel.twin:
            yt = self._ticks(panel, home[1], "y", 300) if panel.ylabels else []
            if yt:
                right += max(text_size(t, panel.tick_size)[0] for _, t, _ in yt) + tick_pad
            if panel.ylabel:
                right += text_size(panel.ylabel, panel.label_size)[1] + label_pad
            return {"left": 0.0, "right": right, "top": 0.0, "bottom": 0.0}
        if not panel.bare:
            yt = self._ticks(panel, home[1], "y", 300) if panel.ylabels else []
            if yt:
                left += max(text_size(t, panel.tick_size)[0] for _, t, _ in yt) + tick_pad
            if panel.ylabel:
                left += text_size(panel.ylabel, panel.label_size)[1] + label_pad
            xt = self._ticks(panel, home[0], "x", 300) if panel.xlabels else []
            if xt:
                sizes = [text_size(t, panel.tick_size) for _, t, _ in xt]
                angle = math.radians(panel.xtick_rotation)
                tall = max(w * abs(math.sin(angle)) + h * abs(math.cos(angle)) for w, h in sizes)
                bottom += tall + tick_pad
                if panel.xtick_rotation:
                    # A slanted label hangs left of its tick.
                    widest = max(w * abs(math.cos(angle)) for w, _ in sizes)
                    first = xt[0][0]
                    span = (home[0][1] - home[0][0]) or 1.0
                    if (first - home[0][0]) / span < 0.25:
                        left = max(left, widest * 0.9)
            if panel.xlabel:
                bottom += text_size(panel.xlabel, panel.label_size)[1] + label_pad
        if panel.title:
            top += text_size(panel.title, panel.title_size)[1] + title_pad
        if panel.legend is not None and panel.legend.loc == "right":
            right += self._legend_size(panel.legend)[0] + 8
        if panel.colour_bar is not None:
            right += self._bar_width(panel.colour_bar)
        return {"left": left, "right": right, "top": top, "bottom": bottom}

    def _margins(self, chart: Chart, home) -> dict:
        rows, cols = chart.grid
        left, right = [0.0] * cols, [0.0] * cols
        top, bottom = [0.0] * rows, [0.0] * rows
        for panel, h in zip(chart.panels, home):
            need = self._panel_needs(panel, h)
            r, c = panel.cell
            r1, c1 = r + panel.span[0] - 1, c + panel.span[1] - 1
            left[c] = max(left[c], need["left"])
            right[min(c1, cols - 1)] = max(right[min(c1, cols - 1)], need["right"])
            top[r] = max(top[r], need["top"])
            bottom[min(r1, rows - 1)] = max(bottom[min(r1, rows - 1)], need["bottom"])
        gap_x, gap_y = chart.gap[0] * PX, chart.gap[1] * PX
        extra_l, extra_r = getattr(self, "_pad_lr", (0.0, 0.0))
        outer_l, outer_r, outer_t, outer_b = EDGE + extra_l, EDGE + extra_r, EDGE, EDGE
        if chart.title:
            outer_t += text_size(chart.title, chart.title_size)[1] + 6
        if chart.colour_bar is not None:
            outer_r += self._bar_width(chart.colour_bar)
        if chart.legend is not None:
            lw, lh = self._legend_size(chart.legend)
            if chart.legend.loc == "right":
                outer_r += lw + 12
            else:
                outer_b += lh + 8
        note_h = 0.0
        if chart.note:
            width = max(self.size[0] - 2 * EDGE, 100)
            note_h = text_size(wrap(chart.note, chart.note_size, width), chart.note_size)[1] + 6
            outer_b += note_h
        return {"left": left, "right": right, "top": top, "bottom": bottom,
                "gap": (gap_x, gap_y), "outer": (outer_l, outer_r, outer_t, outer_b),
                "outer_w": outer_l + outer_r + gap_x * (cols - 1),
                "outer_h": outer_t + outer_b + gap_y * (rows - 1), "note_h": note_h}

    def _layout(self, *, keep: bool) -> None:
        chart = self.scene
        old = [(a.xlim, a.ylim, a.zoomed) for a in self.axes] if keep else None
        home = self._home(chart)
        m = self._margins(chart, home)
        width, height = self.size
        rows, cols = chart.grid
        outer_l, outer_r, outer_t, outer_b = m["outer"]
        gap_x, gap_y = m["gap"]
        free_w = max(width - m["outer_w"] - sum(m["left"]) - sum(m["right"]), 20.0)
        free_h = max(height - m["outer_h"] - sum(m["top"]) - sum(m["bottom"]), 20.0)
        widths = np.asarray(chart.widths or [1.0] * cols, float)
        heights = np.asarray(chart.heights or [1.0] * rows, float)
        widths, heights = widths / widths.sum() * free_w, heights / heights.sum() * free_h
        xs, x = [], outer_l
        for c in range(cols):
            x += m["left"][c]
            xs.append((x, x + widths[c]))
            x += widths[c] + m["right"][c] + gap_x
        ys, y = [], outer_t
        for r in range(rows):
            y += m["top"][r]
            ys.append((y, y + heights[r]))
            y += heights[r] + m["bottom"][r] + gap_y
        self._panels_box = QRectF(outer_l, outer_t, x - gap_x - outer_l, y - gap_y - outer_t)
        self.axes = []
        for panel, (xlim, ylim) in zip(chart.panels, home):
            r, c = panel.cell
            r1 = min(r + panel.span[0] - 1, rows - 1)
            c1 = min(c + panel.span[1] - 1, cols - 1)
            rect = QRectF(QPointF(xs[c][0], ys[r][0]), QPointF(xs[c1][1], ys[r1][1]))
            if panel.equal and xlim[1] > xlim[0] and ylim[1] > ylim[0]:
                scale = min(rect.width() / (xlim[1] - xlim[0]),
                            rect.height() / (ylim[1] - ylim[0]))
                w, h = (xlim[1] - xlim[0]) * scale, (ylim[1] - ylim[0]) * scale
                rect = QRectF(rect.center().x() - w / 2, rect.top(), w, h)
            if xlim[1] == xlim[0]:
                xlim = (xlim[0] - 0.5, xlim[1] + 0.5)
            if ylim[1] == ylim[0]:
                ylim = (ylim[0] - 0.5, ylim[1] + 0.5)
            axes = Axes(rect, xlim, ylim, y_down=panel.y_down)
            self.axes.append(axes)
        if old is not None and len(old) == len(self.axes):
            for axes, (xlim, ylim, zoomed) in zip(self.axes, old):
                if zoomed:
                    axes.xlim, axes.ylim = xlim, ylim

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    # ── a view ───────────────────────────────────────────────────────────────

    def all_axes(self) -> list[Axes]:
        return list(self.axes)

    def panel_at(self, x: float, y: float):
        for index, (axes, panel) in enumerate(zip(self.axes, self.scene.panels)):
            if axes.contains(x, y) and not panel.bare:
                return str(index), axes
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        panel = self.scene.panels[int(key)]
        return bool(panel.zoom[0]), bool(panel.zoom[1])

    def linked(self, key: str) -> list:
        me = self.scene.panels[int(key)]
        out = []
        for index, (axes, panel) in enumerate(zip(self.axes, self.scene.panels)):
            if str(index) == key:
                continue
            x = bool(me.sharex) and panel.sharex == me.sharex
            y = bool(me.sharey) and panel.sharey == me.sharey
            if x or y:
                out.append(_Follow(axes, x, y))
        return out

    def _xy(self, panel: Panel, axes: Axes, x, y) -> tuple[np.ndarray, np.ndarray]:
        y = _log(y) if panel.ylog else np.asarray(y, float)
        return (np.asarray(axes.x_pixel(x), float), np.asarray(axes.y_pixel(y), float))

    def under(self, x: float, y: float):
        for rect, key in self._hits:
            if rect.contains(QPointF(x, y)):
                return ("key", key)
        # Panels can overlap (a twin over its base): the nearest mark of any of them.
        best, best_d = None, REACH
        for index, (axes, panel) in enumerate(zip(self.axes, self.scene.panels)):
            if not axes.contains(x, y):
                continue
            for m_index in range(len(panel.marks) - 1, -1, -1):
                mark = panel.marks[m_index]
                hit = self._hit(panel, axes, mark, x, y)
                if hit is None:
                    continue
                item, distance = hit
                if distance < best_d or (distance == 0 and best_d > 0):
                    best, best_d = (index, m_index, item), distance
        return best

    def _hit(self, panel, axes, mark, x, y):
        """The item of *mark* at pixel (x, y), and how far off it is."""
        if isinstance(mark, Points) and mark.hover:
            px, py = self._xy(panel, axes, mark.x, mark.y)
            d = np.hypot(px - x, py - y)
            if not len(d) or not np.isfinite(d).any():
                return None
            k = int(np.nanargmin(d))
            reach = max(mark.at(mark.size, k) * PX / 2 + 3, REACH)
            return (k, float(d[k])) if d[k] <= reach else None
        if isinstance(mark, Line) and mark.hover:
            px, py = self._xy(panel, axes, mark.x, mark.y)
            d = np.hypot(px - x, py - y)
            if not np.isfinite(d).any():
                return None
            k = int(np.nanargmin(d))
            return (k, float(d[k])) if d[k] <= REACH * 1.4 else None
        if isinstance(mark, Bars) and mark.hover:
            for k in range(len(mark.pos)):
                if self._bar_rect(panel, axes, mark, k).adjusted(-1, -1, 1, 1).contains(
                        QPointF(x, y)):
                    return (k, 0.0)
            return None
        if isinstance(mark, Cells) and mark.hover is not None:
            at = mark.index(*axes.to_data(x, y))
            if at is not None and _cell_text(mark, *at):
                return (at, 0.0)
            return None
        if isinstance(mark, Polygon) and mark.hover:
            px, py = self._xy(panel, axes, mark.x, mark.y)
            shape = QPolygonF([QPointF(a, b) for a, b in zip(px, py)])
            return (0, 0.0) if shape.containsPoint(QPointF(x, y), Qt.FillRule.OddEvenFill) \
                else None
        if isinstance(mark, Text) and mark.hover:
            rect = self._text_box(panel, axes, mark)
            return (0, 0.0) if rect.adjusted(-2, -2, 2, 2).contains(QPointF(x, y)) else None
        return None

    def describe(self, what) -> str:
        if what is None:
            return ""
        if what[0] == "key":
            return str(what[1])
        mark = self.scene.panels[what[0]].marks[what[1]]
        item = what[2]
        if isinstance(mark, Cells):
            return _cell_text(mark, item[0], item[1])
        if isinstance(mark, (Polygon, Text)):
            return str(mark.hover)
        return str(mark.hover[item]) if mark.hover else ""

    def _chosen(self) -> str | None:
        """The series picked out, if any."""
        marked = self.marked
        if marked is None:
            return None
        if marked[0] == "key":
            return marked[1]
        mark = self.scene.panels[marked[0]].marks[marked[1]]
        if isinstance(mark, Points):
            return mark.key_of(marked[2])
        if isinstance(mark, Bars):
            return mark.key[marked[2]] if isinstance(mark.key, list) else mark.key
        return getattr(mark, "key", None) if not isinstance(mark, Cells) else None

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        chart = self.scene
        width, height = self.size
        chosen = self._chosen()
        self._hits = []
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for index, (axes, panel) in enumerate(zip(self.axes, chart.panels)):
            self._paint_panel(painter, index, axes, panel, chosen)
            if panel.colour_bar is not None:
                self._paint_panel_bar(painter, panel.colour_bar, axes.rect)
        if chart.title:
            draw_text(painter, width / 2, EDGE, chart.title, chart.title_size,
                      qcolour(chart.title_colour), "center", "top")
        box = self._panels_box
        if chart.colour_bar is not None:
            self._paint_colour_bar(painter, chart.colour_bar, box)
        if chart.legend is not None:
            lw, lh = self._legend_size(chart.legend)
            if chart.legend.loc == "right":
                left = width - EDGE - lw - (self._bar_width(chart.colour_bar)
                                            if chart.colour_bar else 0)
                self._paint_legend(painter, chart.legend, left, box.center().y() - lh / 2,
                                   chosen)
            else:
                note_h = self._note_height()
                top = height - EDGE - note_h - lh
                self._paint_legend(painter, chart.legend, width / 2 - lw / 2, top, chosen)
        if chart.note:
            text = wrap(chart.note, chart.note_size, width - 2 * EDGE)
            right = chart.note_align == "right"
            draw_text(painter, box.right() if right else EDGE, height - EDGE, text,
                      chart.note_size, MUTED, "right" if right else "left", "bottom")
        painter.restore()

    def _note_height(self) -> float:
        chart = self.scene
        if not chart.note:
            return 0.0
        text = wrap(chart.note, chart.note_size, self.size[0] - 2 * EDGE)
        return text_size(text, chart.note_size)[1] + 6

    def _paint_panel(self, painter, index, axes, panel, chosen) -> None:
        r = axes.rect
        xt = self._ticks(panel, axes.xlim, "x", r.width())
        yt = self._ticks(panel, axes.ylim, "y", r.height())
        ylow, yhigh = sorted(axes.ylim)
        xlow, xhigh = sorted(axes.xlim)
        yt_in = [t for t in yt if ylow - 1e-9 <= t[0] <= yhigh + 1e-9]
        xt_in = [t for t in xt if xlow - 1e-9 <= t[0] <= xhigh + 1e-9]
        if not panel.bare and panel.grid and not panel.twin:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(_pen(GRID, 0.7, cap=Qt.PenCapStyle.FlatCap))
            if "y" in panel.grid:
                for value, _, _ in yt_in:
                    y = float(axes.y_pixel(value))
                    painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            if "x" in panel.grid:
                for value, _, _ in xt_in:
                    x = float(axes.x_pixel(value))
                    painter.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            painter.restore()
        painter.save()
        if not panel.bare:
            painter.setClipRect(r.adjusted(-1, -1, 1, 1))
        order = sorted(range(len(panel.marks)), key=lambda k: getattr(panel.marks[k], "z", 1))
        texts = []
        for k in order:
            mark = panel.marks[k]
            if isinstance(mark, Text):
                texts.append(mark)
                continue
            self._paint_mark(painter, panel, axes, mark, chosen)
        marked = self.marked
        if marked is not None and marked[0] == index:
            self._paint_marked(painter, panel, axes, panel.marks[marked[1]], marked[2])
        painter.restore()
        if panel.frame is not None:
            painter.save()
            painter.setPen(_pen(qcolour(panel.frame), 0.8, cap=Qt.PenCapStyle.FlatCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)
            painter.restore()
        for mark in texts:
            fade = self._fade(mark, chosen)
            rect = self._text_box(panel, axes, mark)
            draw_text(painter, rect.left(), rect.top(), mark.text, mark.size,
                      qcolour(mark.colour, fade), "left", "top", bold=mark.bold)
        if not panel.bare:
            self._paint_ticks(painter, panel, axes, xt_in if panel.xlabels else [],
                              yt_in if panel.ylabels else [])
        if panel.title:
            draw_text(painter, r.center().x(), r.top() - 8 * PX, panel.title, panel.title_size,
                      qcolour(panel.title_colour), "center", "bottom")
        if panel.empty:
            draw_text(painter, r.center().x(), r.center().y(), panel.empty, 8, MUTED)
        if panel.legend is not None:
            self._place_legend(painter, panel.legend, r, chosen)

    def _paint_ticks(self, painter, panel, axes, xt, yt) -> None:
        r = axes.rect
        pad = 4 * PX
        if panel.twin:
            widest = 0.0
            for value, label, colour in yt:
                box = draw_text(painter, r.right() + pad, float(axes.y_pixel(value)), label,
                                panel.tick_size, qcolour(colour) if colour else INK,
                                "left", "center")
                widest = max(widest, box.width())
            if panel.ylabel:
                painter.save()
                painter.translate(r.right() + (widest + pad if yt else 0) + 4 * PX,
                                  r.center().y())
                painter.rotate(90)
                draw_text(painter, 0, 0, panel.ylabel, panel.label_size, INK, "center",
                          "bottom")
                painter.restore()
            return
        widest = 0.0
        for value, label, colour in yt:
            y = float(axes.y_pixel(value))
            box = draw_text(painter, r.left() - pad, y, label, panel.tick_size,
                            qcolour(colour) if colour else INK, "right", "center")
            widest = max(widest, box.width())
        tallest = 0.0
        angle = panel.xtick_rotation
        for value, label, colour in xt:
            x = float(axes.x_pixel(value))
            ink = qcolour(colour) if colour else INK
            if angle:
                w, h = text_size(label, panel.tick_size)
                # The end of the label at the tick, slanting down to the left.
                painter.save()
                painter.translate(x, r.bottom() + pad)
                painter.rotate(-angle)
                draw_text(painter, 0, 0, label, panel.tick_size, ink, "right",
                          "top" if angle < 60 else "center")
                painter.restore()
                rad = math.radians(angle)
                tallest = max(tallest, w * abs(math.sin(rad)) + h * abs(math.cos(rad)))
            else:
                box = draw_text(painter, x, r.bottom() + pad, label, panel.tick_size, ink,
                                "center", "top")
                tallest = max(tallest, box.height())
        if panel.xlabel:
            top = r.bottom() + (tallest + pad if xt else 0) + 4 * PX
            draw_text(painter, r.center().x(), top, panel.xlabel, panel.label_size, INK,
                      "center", "top")
        if panel.ylabel:
            x = r.left() - (widest + pad if yt else 0) - 4 * PX
            painter.save()
            painter.translate(x, r.center().y())
            painter.rotate(-90)
            draw_text(painter, 0, 0, panel.ylabel, panel.label_size, INK, "center", "bottom")
            painter.restore()

    def _fade(self, mark, chosen, k: int | None = None) -> float:
        if chosen is None:
            return 1.0
        if isinstance(mark, Points) and k is not None:
            key = mark.key_of(k)
        elif isinstance(mark, (Bars, Segments)) and isinstance(mark.key, list):
            key = mark.key[k] if k is not None else None
        else:
            key = getattr(mark, "key", None)
        return 1.0 if key is None or key == chosen else FADED

    def _text_box(self, panel, axes, mark: Text) -> QRectF:
        r = axes.rect
        if mark.coords == "axes":
            x, y = r.left() + mark.x * r.width(), r.bottom() - mark.y * r.height()
        elif mark.coords == "blend":
            x = r.left() + mark.x * r.width()
            y = float(self._xy(panel, axes, [0.0], [mark.y])[1][0])
        else:
            px, py = self._xy(panel, axes, [mark.x], [mark.y])
            x, y = float(px[0]), float(py[0])
        x += mark.offset[0] * PX
        y -= mark.offset[1] * PX
        w, h = text_size(mark.text, mark.size, mark.bold)
        left = x - (w / 2 if mark.ha == "center" else w if mark.ha == "right" else 0.0)
        top = y - (h / 2 if mark.va == "center" else h if mark.va in ("bottom", "baseline")
                   else 0.0)
        return QRectF(left, top, w, h)

    def _bar_rect(self, panel, axes, mark: Bars, k: int) -> QRectF:
        pos, half = mark.pos[k], mark.width / 2
        base, end = mark.base[k], mark.base[k] + mark.length[k]
        if mark.horizontal:
            x0, x1 = (float(v) for v in axes.x_pixel([base, end]))
            y0, y1 = (float(v) for v in axes.y_pixel([pos - half, pos + half]))
        else:
            x0, x1 = (float(v) for v in axes.x_pixel([pos - half, pos + half]))
            ys = _log([base, end]) if panel.ylog else [base, end]
            y0, y1 = (float(v) for v in axes.y_pixel(ys))
        return QRectF(QPointF(min(x0, x1), min(y0, y1)), QPointF(max(x0, x1), max(y0, y1)))

    def _paint_mark(self, painter, panel, axes, mark, chosen) -> None:
        r = axes.rect
        if isinstance(mark, Span):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolour(mark.colour))
            if mark.axis == "y":
                ys = _log([mark.low, mark.high]) if panel.ylog else [mark.low, mark.high]
                a, b = (float(v) for v in axes.y_pixel(ys))
                painter.drawRect(QRectF(r.left(), min(a, b), r.width(), abs(b - a)))
            else:
                a, b = (float(v) for v in axes.x_pixel([mark.low, mark.high]))
                painter.drawRect(QRectF(min(a, b), r.top(), abs(b - a), r.height()))
            return
        if isinstance(mark, Rule):
            painter.setPen(_pen(qcolour(mark.colour, self._fade(mark, chosen)), mark.width,
                                mark.dash, cap=Qt.PenCapStyle.FlatCap))
            if mark.axis == "y":
                y = float(axes.y_pixel(_log(mark.value) if panel.ylog else mark.value))
                x0, x1 = ((float(v) for v in axes.x_pixel(mark.extent)) if mark.extent
                          else (r.left(), r.right()))
                painter.drawLine(QPointF(x0, y), QPointF(x1, y))
            else:
                x = float(axes.x_pixel(mark.value))
                if mark.extent:
                    ys = _log(mark.extent) if panel.ylog else mark.extent
                    y0, y1 = (float(v) for v in axes.y_pixel(ys))
                else:
                    y0, y1 = r.top(), r.bottom()
                painter.drawLine(QPointF(x, y0), QPointF(x, y1))
            return
        if isinstance(mark, Cells):
            self._paint_cells(painter, axes, mark)
            return
        if isinstance(mark, Band):
            fade = self._fade(mark, chosen)
            if mark.vertical:
                ys = np.asarray(axes.y_pixel(mark.x), float)
                lo, hi = (np.asarray(axes.x_pixel(v), float) for v in (mark.low, mark.high))
                pts = list(zip(lo, ys)) + list(zip(hi[::-1], ys[::-1]))
            else:
                xs = np.asarray(axes.x_pixel(mark.x), float)
                lo, hi = (self._xy(panel, axes, mark.x, v)[1] for v in (mark.low, mark.high))
                pts = list(zip(xs, lo)) + list(zip(xs[::-1], hi[::-1]))
            ok = np.isfinite(np.asarray(pts, float)).all(axis=1) if pts else []
            pts = [p for p, good in zip(pts, ok) if good]
            if len(pts) > 2:
                painter.setPen(_pen(qcolour(mark.edge, fade), mark.edge_width)
                               if mark.edge is not None and mark.edge_width else Qt.PenStyle.NoPen)
                painter.setBrush(qcolour(mark.colour, fade))
                painter.drawPolygon(QPolygonF([QPointF(a, b) for a, b in pts]))
            return
        if isinstance(mark, Polygon):
            fade = self._fade(mark, chosen)
            px, py = self._xy(panel, axes, mark.x, mark.y)
            painter.setPen(_pen(qcolour(mark.edge, fade), mark.edge_width, mark.dash)
                           if mark.edge_width else Qt.PenStyle.NoPen)
            painter.setBrush(qcolour(mark.fill, fade))
            painter.drawPolygon(QPolygonF([QPointF(a, b) for a, b in zip(px, py)
                                           if np.isfinite(a) and np.isfinite(b)]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            return
        if isinstance(mark, Segments):
            for k, (x0, y0, x1, y1) in enumerate(mark.lines):
                colour = mark.colour[k] if isinstance(mark.colour, list) else mark.colour
                (a, b), (c, d) = (self._xy(panel, axes, [x0, x1], [y0, y1]))
                if not np.isfinite([a, b, c, d]).all():
                    continue
                painter.setPen(_pen(qcolour(colour, self._fade(mark, chosen, k)), mark.width,
                                    mark.dash))
                painter.drawLine(QPointF(a, c), QPointF(b, d))
            return
        if isinstance(mark, ErrorBars):
            pen = _pen(qcolour(mark.colour, self._fade(mark, chosen)), mark.width,
                       cap=Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            cap = mark.cap * PX / 2
            y_ends, x_ends = mark.ends("y"), mark.ends("x")
            for k in range(len(mark.x)):
                x, y = mark.x[k], mark.y[k]
                if y_ends is not None and np.isfinite([y_ends[0][k], y_ends[1][k]]).all():
                    (px,), (y0, y1) = (np.atleast_1d(axes.x_pixel(x)),
                                       self._xy(panel, axes, [x, x], [y_ends[0][k],
                                                                       y_ends[1][k]])[1])
                    if np.isfinite([px, y0, y1]).all():
                        painter.drawLine(QPointF(px, y0), QPointF(px, y1))
                        if cap:
                            for yy in (y0, y1):
                                painter.drawLine(QPointF(px - cap, yy), QPointF(px + cap, yy))
                if x_ends is not None and np.isfinite([x_ends[0][k], x_ends[1][k]]).all():
                    xs, ys = self._xy(panel, axes, [x_ends[0][k], x_ends[1][k]], [y, y])
                    if np.isfinite(np.concatenate([xs, ys])).all():
                        painter.drawLine(QPointF(xs[0], ys[0]), QPointF(xs[1], ys[1]))
                        if cap:
                            for xx in xs:
                                painter.drawLine(QPointF(xx, ys[0] - cap),
                                                 QPointF(xx, ys[0] + cap))
            return
        if isinstance(mark, Bars):
            painter.setPen(Qt.PenStyle.NoPen)
            for k in range(len(mark.pos)):
                if not (np.isfinite(mark.length[k]) and np.isfinite(mark.pos[k])):
                    continue
                colour = mark.colour[k] if isinstance(mark.colour, list) else mark.colour
                fade = self._fade(mark, chosen, k)
                if mark.edge_width > 0 and mark.edge[3] > 0:
                    painter.setPen(_pen(qcolour(mark.edge, fade), mark.edge_width, "-"))
                painter.setBrush(qcolour(colour, fade))
                painter.drawRect(self._bar_rect(panel, axes, mark, k))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            return
        if isinstance(mark, Line):
            fade = self._fade(mark, chosen)
            px, py = self._xy(panel, axes, mark.x, mark.y)
            colour = qcolour(mark.colour, fade)
            ok = np.isfinite(px) & np.isfinite(py)
            if mark.width > 0 and len(px) > 1:
                painter.setPen(_pen(colour, mark.width, mark.dash))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                run: list[QPointF] = []
                for a, b, good in zip(px, py, ok):
                    if good:
                        run.append(QPointF(a, b))
                    else:
                        if len(run) > 1:
                            painter.drawPolyline(QPolygonF(run))
                        run = []
                if len(run) > 1:
                    painter.drawPolyline(QPolygonF(run))
            if mark.marker:
                fill = qcolour(mark.marker_fill, fade) if mark.marker_fill is not None else colour
                if mark.marker_edge is not None and mark.marker_edge_width:
                    painter.setPen(_pen(qcolour(mark.marker_edge, fade), mark.marker_edge_width))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                rad = mark.marker_size * PX / 2
                for a, b in zip(px[ok], py[ok]):
                    painter.drawEllipse(QPointF(a, b), rad, rad)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            return
        if isinstance(mark, Labels):
            self._paint_labels(painter, panel, axes, mark, chosen)
            return
        if isinstance(mark, Points):
            px, py = self._xy(panel, axes, mark.x, mark.y)
            for k in range(len(px)):
                if not (np.isfinite(px[k]) and np.isfinite(py[k])):
                    continue
                fade = self._fade(mark, chosen, k)
                fill = qcolour(mark.at(mark.fill, k), fade)
                edge = qcolour(mark.at(mark.edge, k), fade)
                size = float(mark.at(mark.size, k)) * PX
                if mark.marker in ("|", "_"):
                    painter.setPen(_pen(fill, max(mark.edge_width, 1.0),
                                        cap=Qt.PenCapStyle.FlatCap))
                    if mark.marker == "|":
                        painter.drawLine(QPointF(px[k], py[k] - size / 2),
                                         QPointF(px[k], py[k] + size / 2))
                    else:
                        painter.drawLine(QPointF(px[k] - size / 2, py[k]),
                                         QPointF(px[k] + size / 2, py[k]))
                    continue
                if mark.edge_width and edge.alphaF() > 0:
                    painter.setPen(_pen(edge, mark.edge_width))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill if fill.alphaF() > 0 else Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(px[k], py[k]), size / 2, size / 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_labels(self, painter, panel, axes, mark: Labels, chosen) -> None:
        px, py = self._xy(panel, axes, mark.x, mark.y)
        ok = np.isfinite(px) & np.isfinite(py)
        if not ok.any():
            return
        idx = np.flatnonzero(ok)
        texts = [mark.texts[i] for i in idx]
        w = np.array([text_size(t, mark.size, mark.bold)[0] + 3 for t in texts])
        h = np.full(len(texts), text_size("0", mark.size, mark.bold)[1] * 0.85)
        anchors = np.c_[px[idx], py[idx]]
        key = (tuple(anchors.round(2).ravel()), axes.rect.getRect())
        if getattr(mark, "_cache", (None,))[0] != key:
            mark._cache = (key, repel(anchors, w, h, mark.dot * PX, axes.rect))
        pos = mark._cache[1]
        for n, i in enumerate(idx):
            fade = 1.0 if chosen is None or mark.keys is None or mark.keys[i] == chosen \
                else FADED
            colour = qcolour(mark.colours[i], fade)
            (ax_, ay), (lx, ly) = anchors[n], pos[n]
            # Directly above its own point, a label needs no leader.
            beside = abs(lx - ax_) < w[n] / 2 and 0 < ay - ly < mark.dot * PX + h[0] + 2
            if not beside:
                ex = float(np.clip(ax_, lx - w[n] / 2, lx + w[n] / 2))
                ey = ly + h[n] / 2 if ly < ay else ly - h[n] / 2
                painter.setPen(_pen(qcolour(mark.colours[i], 0.6 * fade), 0.6))
                painter.drawLine(QPointF(ax_, ay), QPointF(ex, ey))
            draw_text(painter, lx, ly, texts[n], mark.size, colour, bold=mark.bold)

    def _paint_cells(self, painter, axes: Axes, mark: Cells) -> None:
        rows, cols = mark.values.shape
        if not rows or not cols:
            return
        image, pixels = colour_image(mark.values, mark.cmap, mark.low, mark.high,
                                     missing=(1.0, 1.0, 1.0, 0.0))
        bx0, bx1, by0, by1 = mark.box()
        x0, x1 = (float(v) for v in axes.x_pixel([bx0, bx1]))
        y0, y1 = (float(v) for v in axes.y_pixel([by0, by1]))
        if x0 > x1:                     # a reversed x axis: mirror the columns
            image = image.mirrored(True, False)
        target = QRectF(QPointF(min(x0, x1), min(y0, y1)), QPointF(max(x0, x1), max(y0, y1)))
        if y0 > y1:                     # row 0 at the bottom: flip the image
            image = image.mirrored(False, True)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, image)
        painter.restore()
        del pixels
        if mark.text is None:
            return
        for i in range(rows):
            for j in range(cols):
                text = mark.text[i][j]
                if not text:
                    continue
                colour = mark.text_colour[i][j] if mark.text_colour is not None else (0.13,) * 3
                cx, cy = mark.centre(i, j)
                x = float(axes.x_pixel(cx))
                y = float(axes.y_pixel(cy))
                draw_text(painter, x, y, text, mark.text_size, qcolour(colour if not
                          isinstance(colour, str) else _named(colour)), bold=mark.text_bold)

    def _paint_marked(self, painter, panel, axes, mark, item) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(SELECTED, 2.2))
        if isinstance(mark, (Points, Line)):
            px, py = self._xy(panel, axes, [mark.x[item]], [mark.y[item]])
            size = (float(mark.at(mark.size, item)) if isinstance(mark, Points)
                    else mark.marker_size) * PX / 2 + 4
            painter.drawEllipse(QPointF(px[0], py[0]), size, size)
        elif isinstance(mark, Bars):
            painter.drawRect(self._bar_rect(panel, axes, mark, item))
        elif isinstance(mark, Cells):
            i, j = item
            x0, x1 = (float(v) for v in axes.x_pixel([j - 0.5, j + 0.5]))
            y0, y1 = (float(v) for v in axes.y_pixel([i - 0.5, i + 0.5]))
            painter.drawRect(QRectF(QPointF(min(x0, x1), min(y0, y1)),
                                    QPointF(max(x0, x1), max(y0, y1))))
        elif isinstance(mark, Polygon):
            px, py = self._xy(panel, axes, mark.x, mark.y)
            painter.drawPolygon(QPolygonF([QPointF(a, b) for a, b in zip(px, py)]))
        elif isinstance(mark, Text):
            painter.drawRect(self._text_box(panel, axes, mark).adjusted(-2, -1, 2, 1))

    # ── legends and the colour bar ───────────────────────────────────────────

    def _legend_size(self, legend: Legend) -> tuple[float, float]:
        em = legend.size * PX
        line = text_size("Ag", legend.size)[1]
        handle = legend.swatch * em * 1.4
        cols = max(1, min(legend.columns, len(legend.items)))
        rows = math.ceil(len(legend.items) / cols) if legend.items else 0
        widths = [text_size(item.label, legend.size)[0] for item in legend.items] or [0.0]
        column_w = []
        for c in range(cols):
            mine = widths[c::cols]
            column_w.append(handle + 0.5 * em + (max(mine) if mine else 0.0))
        w = sum(column_w) + (cols - 1) * em
        h = rows * line + max(rows - 1, 0) * 0.3 * em
        if legend.title:
            tw, th = text_size(legend.title, legend.size)
            w, h = max(w, tw), h + th + 0.3 * em
        return w, h

    def _place_legend(self, painter, legend: Legend, r: QRectF, chosen) -> None:
        w, h = self._legend_size(legend)
        pad = 0.5 * legend.size * PX
        loc = legend.loc
        if loc == "best":
            loc = self._best_corner(r, w, h, pad)
        if loc == "right":
            left, top = r.right() + 8, r.center().y() - h / 2
        else:
            left = r.left() + pad if "left" in loc else r.right() - pad - w
            if loc.startswith("upper"):
                top = r.top() + pad
            elif loc.startswith("lower"):
                top = r.bottom() - pad - h
            else:
                top = r.center().y() - h / 2
            if loc == "center left":
                left = r.left() + pad
        self._paint_legend(painter, legend, left, top, chosen)

    def _best_corner(self, r: QRectF, w: float, h: float, pad: float) -> str:
        """The corner of panel *r* where a legend covers the fewest data points,
        as matplotlib's ``loc="best"`` chooses."""
        index = next(k for k, a in enumerate(self.axes) if a.rect == r)
        panel, axes = self.scene.panels[index], self.axes[index]
        xs, ys = [], []
        for mark in panel.marks:
            if isinstance(mark, (Line, Points)):
                px, py = self._xy(panel, axes, mark.x, mark.y)
                xs.append(px)
                ys.append(py)
            elif isinstance(mark, ErrorBars) and mark.yerr is not None:
                for end in mark.ends("y"):
                    px, py = self._xy(panel, axes, mark.x, end)
                    xs.append(px)
                    ys.append(py)
            elif isinstance(mark, Text) and mark.coords == "data":
                box = self._text_box(panel, axes, mark)
                xs.append(np.array([box.left(), box.right()]))
                ys.append(np.array([box.center().y()] * 2))
            elif isinstance(mark, Band) and not mark.vertical:
                for v in (mark.low, mark.high):
                    px, py = self._xy(panel, axes, mark.x, v)
                    xs.append(px)
                    ys.append(py)
        px = np.concatenate(xs) if xs else np.array([])
        py = np.concatenate(ys) if ys else np.array([])
        best, fewest = "upper right", None
        for loc in ("upper right", "upper left", "lower left", "lower right",
                    "center right", "center left"):
            left = r.left() + pad if "left" in loc else r.right() - pad - w
            top = (r.top() + pad if loc.startswith("upper") else
                   r.bottom() - pad - h if loc.startswith("lower") else r.center().y() - h / 2)
            inside = int(np.sum((px >= left) & (px <= left + w) & (py >= top) & (py <= top + h)))
            if fewest is None or inside < fewest:
                best, fewest = loc, inside
        return best

    def _paint_legend(self, painter, legend: Legend, left: float, top: float, chosen) -> None:
        em = legend.size * PX
        line = text_size("Ag", legend.size)[1]
        handle = legend.swatch * em * 1.4
        cols = max(1, min(legend.columns, len(legend.items)))
        widths = [text_size(item.label, legend.size)[0] for item in legend.items]
        column_w = [handle + 0.5 * em + max([widths[k] for k in range(len(widths))
                                             if k % cols == c] or [0.0]) for c in range(cols)]
        y0 = top
        if legend.title:
            tw, th = text_size(legend.title, legend.size)
            total = sum(column_w) + (cols - 1) * em
            draw_text(painter, left + max(total, tw) / 2, top, legend.title, legend.size, INK,
                      "center", "top")
            y0 += th + 0.3 * em
        for k, item in enumerate(legend.items):
            c, row = k % cols, k // cols
            x = left + sum(column_w[:c]) + c * em
            y = y0 + row * (line + 0.3 * em)
            mid = y + line / 2
            fade = 1.0 if chosen is None or item.key is None or item.key == chosen else FADED
            colour = qcolour(item.colour, fade)
            painter.save()
            if item.kind == "line":
                painter.setPen(_pen(colour, 1.5 if item.dash == "-" else 1.2, item.dash))
                painter.drawLine(QPointF(x, mid), QPointF(x + handle, mid))
                if item.marker:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(colour)
                    painter.drawEllipse(QPointF(x + handle / 2, mid), item.size * PX / 2,
                                        item.size * PX / 2)
            elif item.kind == "tick":
                painter.setPen(_pen(colour, 1.8, cap=Qt.PenCapStyle.FlatCap))
                half = min(item.size * PX, line) / 2
                painter.drawLine(QPointF(x + handle / 2, mid - half),
                                 QPointF(x + handle / 2, mid + half))
            elif item.kind == "hline":
                painter.setPen(_pen(colour, 2.5, cap=Qt.PenCapStyle.FlatCap))
                painter.drawLine(QPointF(x, mid), QPointF(x + handle, mid))
            elif item.kind in ("point", "open"):
                rad = item.size * PX / 2
                if item.kind == "open":
                    painter.setPen(_pen(colour, 1.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    edge = item.edge
                    painter.setPen(_pen(qcolour(edge, fade), 0.8) if edge is not None
                                   else Qt.PenStyle.NoPen)
                    painter.setBrush(colour)
                painter.drawEllipse(QPointF(x + handle / 2, mid), rad, rad)
            else:
                painter.setPen(_pen(qcolour(item.edge, fade), 0.8) if item.edge is not None
                               else Qt.PenStyle.NoPen)
                painter.setBrush(colour)
                side = min(line * 0.7, handle)
                painter.drawRect(QRectF(x + handle / 2 - side * 0.7, mid - side / 2,
                                        side * 1.4, side))
            painter.restore()
            box = draw_text(painter, x + handle + 0.5 * em, mid, item.label, legend.size,
                            qcolour((0.13, 0.13, 0.13, 1.0), fade if fade < 1 else 1.0),
                            "left", "center")
            if item.key is not None:
                self._hits.append((QRectF(x, y, box.right() - x, line), item.key))

    def _bar_width(self, bar) -> float:
        if bar is None:
            return 0.0
        labels = self._bar_ticks(bar)
        widest = max([text_size(t, bar.tick_size)[0] for _, t in labels] or [0.0])
        w = 12 * PX * 0.75 + 10 + 4 * PX + widest
        if bar.label:
            w += text_size(bar.label, 8)[1] + 6
        return w + 6

    def _bar_ticks(self, bar, length: float | None = None) -> list[tuple[float, str]]:
        if bar.ticks is not None:
            return [(float(t[0]), str(t[1])) if isinstance(t, (tuple, list))
                    else (float(t), tick_label(float(t), 0.1)) for t in bar.ticks]
        if length is None:
            length = getattr(self, "_bar_length", 300.0)
        ticks, step = nice_ticks(bar.low, bar.high,
                                 target=int(min(max(length / (bar.tick_size * PX * 3), 2), 9)))
        power = _bar_power(bar)
        return [(v, tick_label(v / 10.0 ** power, step / 10.0 ** power)) for v in ticks]

    def _paint_colour_bar(self, painter, bar, box: QRectF) -> None:
        width = self.size[0]
        left = width - EDGE - self._bar_width(bar) + 10
        # matplotlib takes ``fraction`` of the parent axes' width, not the figure's.
        plots = (max(a.rect.right() for a in self.axes) - min(a.rect.left() for a in self.axes)
                 if self.axes else box.width())
        h = min(box.height() * bar.shrink, bar.aspect * bar.fraction * plots)
        thick = min(h / bar.aspect, 12 * PX * 0.75) if bar.aspect else 12 * PX * 0.75
        self._bar_length = h
        top = box.top() if bar.top else box.top() + (box.height() - h) / 2
        self._draw_bar(painter, bar, QRectF(left, top, thick, h))

    def _paint_panel_bar(self, painter, bar, plot: QRectF) -> None:
        """A panel's own colour bar, just right of its plot area."""
        h = min(plot.height() * bar.shrink, bar.aspect * bar.fraction * plot.width())
        thick = min(h / bar.aspect, 12 * PX * 0.75) if bar.aspect else 12 * PX * 0.75
        top = plot.top() if bar.top else plot.center().y() - h / 2
        self._draw_bar(painter, bar, QRectF(plot.right() + 10, top, thick, h))

    def _draw_bar(self, painter, bar, rect: QRectF) -> None:
        table = colormap(bar.cmap)
        gradient = QLinearGradient(rect.bottomLeft(), rect.topLeft())
        for i in range(64):
            rr, gg, bb, _ = table(i / 63)
            gradient.setColorAt(i / 63, QColor.fromRgbF(rr, gg, bb))
        painter.fillRect(rect, QBrush(gradient))
        span = (bar.high - bar.low) or 1.0
        widest = 0.0
        for value, label in self._bar_ticks(bar, rect.height()):
            if not bar.low - 1e-9 <= value <= bar.high + 1e-9:
                continue
            y = rect.bottom() - (value - bar.low) / span * rect.height()
            box_t = draw_text(painter, rect.right() + 4 * PX, y, label, bar.tick_size, INK,
                              "left", "center")
            widest = max(widest, box_t.width())
        power = _bar_power(bar)
        if power and bar.ticks is None:
            # The scale the labels were divided by, above the bar, as matplotlib's offset text.
            draw_text(painter, rect.left(), rect.top() - 3, f"×1e{power}", bar.tick_size,
                      INK, "left", "bottom")
        if bar.label:
            painter.save()
            painter.translate(rect.right() + 4 * PX + widest + 4, rect.center().y())
            painter.rotate(-90)
            draw_text(painter, 0, 0, bar.label, 8, INK, "center", "top")
            painter.restore()


def _bar_power(bar) -> int:
    """The power of ten a colour bar's labels are written in, 0 for plain numbers:
    as matplotlib, beyond 1e-4 below or 1e4 above."""
    top = max(abs(bar.low), abs(bar.high))
    if not np.isfinite(top) or top == 0 or 1e-4 <= top < 1e4:
        return 0
    return int(math.floor(math.log10(top)))


def _cell_text(mark: Cells, i: int, j: int) -> str:
    if mark.hover is None:
        return ""
    if callable(mark.hover):
        return str(mark.hover(i, j) or "")
    return str(mark.hover[i][j] or "")


def repel(anchors: np.ndarray, w: np.ndarray, h: np.ndarray, dot: float,
          box: QRectF) -> np.ndarray:
    """Places for labels of size (*w*, *h*) near *anchors* (pixels, y down) that
    do not overlap each other or cover a point of radius *dot*.

    Each starts just above its point. Overlapping labels are pushed apart
    sideways, keeping the left-to-right order of their points, so a dense
    cluster becomes a row whose leaders fan out without crossing; labels are
    pushed off any point they cover, always on the side of their own point
    they already sit, so none bounces between two points.
    """
    n = len(anchors)
    up = np.c_[anchors[:, 0], -anchors[:, 1]]          # y up, as it was written
    pos = up + np.c_[np.zeros(n), dot + h / 2 + 1]
    lo = np.c_[box.left() + w / 2, -box.bottom() + h / 2]
    hi = np.c_[box.right() - w / 2, -box.top() - h / 2]
    rank = np.argsort(np.argsort(up[:, 0] + 1e-6 * np.arange(n)))
    for _ in range(400):
        moved = False
        for i in range(n):
            d = pos[i] - pos
            ox = (w[i] + w) / 2 - np.abs(d[:, 0])
            oy = (h[i] + h) / 2 - np.abs(d[:, 1])
            hit = (ox > 0.5) & (oy > 0.5)
            hit[i] = False
            for j in np.flatnonzero(hit):
                sign = 1.0 if rank[i] > rank[j] else -1.0
                pos[i, 0] += sign * ox[j] / 2
                pos[j, 0] -= sign * ox[j] / 2
                moved = True
            d = pos[i] - up
            ox = w[i] / 2 + dot - np.abs(d[:, 0])
            oy = h[i] / 2 + dot - np.abs(d[:, 1])
            side = 1.0 if pos[i, 1] >= up[i, 1] else -1.0
            for k in np.flatnonzero((ox > 0.5) & (oy > 0.5)):
                pos[i, 1] = up[k, 1] + side * (h[i] / 2 + dot + 0.5)
                moved = True
        pos = np.clip(pos, lo, np.maximum(hi, lo))
        if not moved:
            break
    return np.c_[pos[:, 0], -pos[:, 1]]


def _named(colour: str):
    from meanap.native.chart import rgba

    return rgba(colour)


def save_chart(chart: Chart, path):
    """Write *chart* to *path* (PNG, SVG or PDF), or hand it to a viewer."""
    from pathlib import Path

    from meanap.native import output

    painter = ChartPainter(chart)
    output.save(painter, path, capture=output.NativeFigure("chart", chart, painter))
    return Path(path)


__all__ += ["save_chart"]
