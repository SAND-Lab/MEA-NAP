"""The connectivity-statistics figure, drawn with ``QPainter``.

Six panels in the arrangement of MATLAB's ``plotConnectivityProperties``: the
adjacency matrix with its colour bar, the largest and the mean edge weight as
bars beneath it, and histograms of node degree, node strength and edge weight
down the right.

The pipeline paints it once to write the file. An interactive view paints the
same object after setting what it is pointing at, which links the panels: a
matrix cell marks its value on the edge-weight histogram and its row node's
degree and strength on the other two; a histogram bar is lit.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen

from meanap.native.axes import INK, Axes
from meanap.native.figure import (
    GROUND, SELECTED, FigurePainter, colour_image, paint_colour_bar, paint_title,
)
from meanap.native.output import figure_font
from meanap.native.scene import ConnectivityScene

__all__ = ["ConnectivityPainter", "STANDARD_SIZE"]

#: The figure the pipeline saves, in logical pixels (11 × 6.6 inches).
STANDARD_SIZE = (1056, 634)
BAR = QColor("#1f77b4")
HIST = QColor("#4FC3E8")
HIST_LIT = QColor("#1787ad")
BINS = 50
COLORMAP = "viridis"
#: A bar's members are listed by name up to this many, then only counted.
MAX_NAMED = 8

_HISTOGRAMS = (("nd", "node degree", True), ("ns", "node strength", True),
               ("edge_weights", "edge weight", False))
_SUMMARIES = (("max_value", "max corr. value"), ("mean_value", "mean corr. value"))


class _Histogram:
    def __init__(self, key: str, label: str, of_nodes: bool, values: np.ndarray) -> None:
        self.key, self.label, self.of_nodes = key, label, of_nodes
        values = np.asarray(values, dtype=float).ravel()
        #: Which of the scene's values each kept value is, for naming members.
        self.rows = np.flatnonzero(np.isfinite(values))
        self.values = values[self.rows]
        if self.values.size:
            self.counts, self.edges = np.histogram(self.values, bins=BINS)
        else:
            self.counts, self.edges = np.zeros(0, dtype=int), np.array([0.0, 1.0])
        self.axes: Axes | None = None

    def bin_at(self, x: float) -> int | None:
        if not self.counts.size or not self.edges[0] <= x <= self.edges[-1]:
            return None
        return int(np.clip(np.searchsorted(self.edges, x, side="right") - 1,
                           0, len(self.counts) - 1))

    def members(self, index: int) -> np.ndarray:
        """Rows of the values in bar *index* (the last bar includes its top edge)."""
        low, high = self.edges[index], self.edges[index + 1]
        last = index == len(self.counts) - 1
        inside = (self.values >= low) & ((self.values <= high) if last else (self.values < high))
        return self.rows[inside]


class ConnectivityPainter(FigurePainter):
    """Draws one connectivity-statistics scene.

    What a view points at is ``("cell", i, j)``, ``("bar", key, index)`` or
    ``("summary", key)``.
    """

    standard_size = STANDARD_SIZE

    def __init__(self, scene: ConnectivityScene, size: tuple[float, float] | None = None):
        super().__init__(scene, size)
        finite = scene.adj[np.isfinite(scene.adj)]
        low, high = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        self.levels = (low, high if high > low else low + 1e-6)
        self.histograms = {key: _Histogram(key, label, of_nodes, getattr(scene, key))
                           for key, label, of_nodes in _HISTOGRAMS}
        self._image, self._pixels = colour_image(scene.adj, COLORMAP, *self.levels)
        self._layout(keep=False)

    # ── layout ───────────────────────────────────────────────────────────────

    def resize(self, size: tuple[float, float]) -> None:
        self.size = (float(size[0]), float(size[1]))
        self._layout(keep=True)

    def zoomable(self, key: str) -> tuple[bool, bool]:
        # The matrix both ways, a histogram along its values, a summary not at all.
        if key in self.summaries:
            return False, False
        return True, key == "matrix"

    def pinnable(self, what) -> bool:
        return what is not None and what[0] != "summary"

    def all_axes(self) -> list[Axes]:
        return [self.matrix, *self.summaries.values(),
                *(h.axes for h in self.histograms.values())]

    def _layout(self, *, keep: bool) -> None:
        """Place the panels. *keep* carries each panel's zoom over a resize."""
        old = ({"matrix": (self.matrix.xlim, self.matrix.ylim),
                **{k: (h.axes.xlim, h.axes.ylim) for k, h in self.histograms.items()}}
               if keep else {})
        scene = self.scene
        width, height = self.size
        top, bottom = 78.0, height - 52.0
        split = width * 0.46
        rows, cols = scene.adj.shape if scene.adj.ndim == 2 else (1, 1)

        matrix_h = (bottom - top) * 0.50
        matrix_rect = QRectF(64, top, split - 64 - 118, matrix_h)
        self.matrix = Axes(matrix_rect, (0, max(cols, 1)), (0, max(rows, 1)),
                           xlabel="nodes", ylabel="nodes", title="adjacency matrix",
                           y_down=True)
        self.colour_bar = QRectF(matrix_rect.right() + 14, top, 16, matrix_h)

        bar_top = matrix_rect.bottom() + 86
        bar_w = (split - 64 - 40) / 2 - 30
        self.summaries = {}
        for i, (key, title) in enumerate(_SUMMARIES):
            rect = QRectF(64 + i * (bar_w + 60), bar_top, bar_w, bottom - bar_top)
            self.summaries[key] = Axes(rect, (-0.6, 0.6), scene.bar_ylim, title=title,
                                       x_ticks=False)

        left = split + 70
        gap = 58.0
        panel_h = (bottom - top + 24 - 2 * gap) / 3
        for i, (key, label, _) in enumerate(_HISTOGRAMS):
            hist = self.histograms[key]
            rect = QRectF(left, top - 24 + i * (panel_h + gap), width - left - 24, panel_h)
            low, high = float(hist.edges[0]), float(hist.edges[-1])
            pad = (high - low) * 0.02 or 0.5
            peak = float(hist.counts.max()) if hist.counts.size else 1.0
            hist.axes = Axes(rect, (low - pad, high + pad), (0, max(peak, 1.0) * 1.06),
                             xlabel=label, ylabel="frequency")
        if keep:
            self.matrix.xlim, self.matrix.ylim = old["matrix"]
            for key, hist in self.histograms.items():
                hist.axes.xlim, hist.axes.ylim = old[key]

    # ── pointing ─────────────────────────────────────────────────────────────

    def name(self, row: int) -> str:
        names = self.scene.names
        return names[row] if row < len(names) else str(row + 1)

    def panel_at(self, x: float, y: float) -> tuple[str, Axes] | None:
        """Which panel pixel (x, y) is in: its key and its axes."""
        if self.matrix.contains(x, y):
            return "matrix", self.matrix
        for key, hist in self.histograms.items():
            if hist.axes.contains(x, y):
                return key, hist.axes
        for key, axes in self.summaries.items():
            if axes.contains(x, y):
                return key, axes
        return None

    def under(self, x: float, y: float) -> tuple | None:
        """What is at pixel (x, y): a matrix cell, a histogram bar, a summary."""
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        key, axes = panel
        at = axes.to_data(x, y)
        if key == "matrix":
            i, j = int(np.floor(at[1])), int(np.floor(at[0]))
            rows, cols = self.scene.adj.shape
            return ("cell", i, j) if 0 <= i < rows and 0 <= j < cols else None
        if key in self.histograms:
            hist = self.histograms[key]
            index = hist.bin_at(at[0])
            return ("bar", key, index) if index is not None and hist.counts[index] else None
        return ("summary", key)

    def describe(self, what: tuple) -> str:
        scene, noun = self.scene, self.scene.noun
        if what[0] == "cell":
            _, i, j = what
            value = float(scene.adj[i, j])
            pair = f"{noun.capitalize()} {self.name(i)} × {noun} {self.name(j)}"
            return f"{pair}\ncorrelation: {value:.4g}" + ("" if value else " (no edge)")
        if what[0] == "bar":
            _, key, index = what
            hist = self.histograms[key]
            low, high, count = hist.edges[index], hist.edges[index + 1], int(hist.counts[index])
            thing = noun if hist.of_nodes else "edge"
            text = (f"{hist.label.capitalize()} {low:.4g} to {high:.4g}\n"
                    f"{count} {thing}{'' if count == 1 else 's'}")
            if hist.of_nodes and count <= MAX_NAMED:
                text += ": " + ", ".join(self.name(int(m)) for m in hist.members(index))
            return text
        return f"{dict(_SUMMARIES)[what[1]]}: {float(getattr(scene, what[1])):.4g}"

    def marks(self) -> tuple[tuple | None, dict[str, float], tuple | None]:
        """What to mark: the matrix cell, a value per histogram, and the lit bar."""
        what = self.marked
        if what is None or what[0] == "summary":
            return None, {}, None
        if what[0] == "bar":
            return None, {}, what
        _, i, j = what
        scene, values = self.scene, {}
        weight = float(scene.adj[i, j])
        edges = self.histograms["edge_weights"]
        # The cell's value where it is one of the values counted, and the row
        # node's degree and strength.
        if edges.values.size and edges.edges[0] <= weight <= edges.edges[-1]:
            values["edge_weights"] = weight
        for key in ("nd", "ns"):
            column = getattr(scene, key)
            if i < len(column) and np.isfinite(column[i]):
                values[key] = float(column[i])
        return what, values, None

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        width, height = self.size
        cell, values, bar = self.marks()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, self.scene.title, width)
        self._paint_matrix(painter, cell)
        paint_colour_bar(painter, self.colour_bar, COLORMAP, *self.levels,
                         label="correlation coefficient")
        for key, axes in self.summaries.items():
            self._paint_summary(painter, axes, float(getattr(self.scene, key)))
        for key, hist in self.histograms.items():
            lit = bar[2] if bar is not None and bar[1] == key else None
            self._paint_histogram(painter, hist, lit, values.get(key))
        painter.restore()

    def _paint_matrix(self, painter: QPainter, cell) -> None:
        axes = self.matrix
        (x0, x1), (y0, y1) = axes.xlim, axes.ylim
        painter.save()
        axes.clip(painter)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(axes.rect, self._image, QRectF(x0, y0, x1 - x0, y1 - y0))
        if cell is not None:
            _, i, j = cell
            left, right = float(axes.x_pixel(j)), float(axes.x_pixel(j + 1))
            top, bottom = float(axes.y_pixel(i)), float(axes.y_pixel(i + 1))
            painter.setPen(QPen(SELECTED, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Never smaller than a mark that can be seen.
            grow = max(0.0, (5 - (right - left)) / 2)
            painter.drawRect(QRectF(left - grow, top - grow, right - left + 2 * grow,
                                    bottom - top + 2 * grow))
        painter.restore()
        axes.paint_frame(painter)

    def _paint_summary(self, painter: QPainter, axes: Axes, value: float) -> None:
        painter.save()
        axes.clip(painter)
        left, right = float(axes.x_pixel(-0.4)), float(axes.x_pixel(0.4))
        top, base = float(axes.y_pixel(value)), float(axes.y_pixel(0))
        painter.fillRect(QRectF(left, top, right - left, base - top), BAR)
        painter.setPen(INK)
        font = figure_font(11)
        painter.setFont(font)
        line = QFontMetricsF(font).height()
        painter.drawText(QRectF(left - 30, top - line - 2, right - left + 60, line),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                         f"{value:.3g}")
        painter.restore()
        axes.paint_frame(painter)

    def _paint_histogram(self, painter: QPainter, hist: _Histogram, lit: int | None,
                         mark: float | None) -> None:
        axes = hist.axes
        painter.save()
        axes.clip(painter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        base = float(axes.y_pixel(0))
        lefts, rights = axes.x_pixel(hist.edges[:-1]), axes.x_pixel(hist.edges[1:])
        tops = axes.y_pixel(hist.counts) if hist.counts.size else []
        for index, (left, right, top) in enumerate(zip(np.atleast_1d(lefts).tolist(),
                                                       np.atleast_1d(rights).tolist(),
                                                       np.atleast_1d(tops).tolist())):
            if hist.counts[index]:
                gap = 0.5 if right - left > 3 else 0.0
                painter.fillRect(QRectF(left + gap, top, right - left - 2 * gap, base - top),
                                 HIST_LIT if index == lit else HIST)
        if mark is not None:
            x = float(axes.x_pixel(mark))
            painter.setPen(QPen(SELECTED, 2))
            painter.drawLine(QPointF(x, axes.rect.top()), QPointF(x, axes.rect.bottom()))
        painter.restore()
        axes.paint_frame(painter)
