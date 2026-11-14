"""Half-violins, drawn with ``QPainter``.

One panel per metric, side by side (``HalfViolinPlot.m``): the density to the
right of the centre line, the nodes as points to the left, and the mean with
its standard error on the line. Used for "Firing rate by electrode" (one
panel) and "Graph metrics by node" (one per node-level metric, each under a
picture explaining it).

Every panel is over the same nodes, so pointing at a point marks that node in
all of them and reads out its value for every metric.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from meanap.native.axes import INK, Axes
from meanap.native.figure import GROUND, SELECTED, FigurePainter, paint_title
from meanap.native.output import figure_font
from meanap.native.scene import ViolinScene

__all__ = ["ViolinPainter"]

POINT_R = 3.0
MEAN_R = 6.5
#: A point is "pointed at" from this many pixels away.
REACH = 7.0


class ViolinPainter(FigurePainter):
    """Draws a row of half-violins. What a view points at is a node's row."""

    #: Width of one panel, its height, and the room above for the pictures.
    PANEL_W, HEIGHT, LONE = 196.0, 600.0, (520.0, 620.0)

    def __init__(self, scene: ViolinScene, size: tuple[float, float] | None = None):
        count = max(len(scene.panels), 1)
        standard = self.LONE if count == 1 else (self.PANEL_W * count + 40, self.HEIGHT)
        super().__init__(scene, size or standard)
        self._icons = [self._load(panel.icon) for panel in scene.panels]
        self.axes: list[Axes] = []
        self._layout(keep=False)

    @staticmethod
    def _load(path: str | None) -> QImage | None:
        if not path:
            return None
        image = QImage(path)
        return None if image.isNull() else image

    def _layout(self, *, keep: bool) -> None:
        old = [axes.ylim for axes in self.axes] if keep else None
        scene = self.scene
        width, height = self.size
        count = max(len(scene.panels), 1)
        has_icons = any(icon is not None for icon in self._icons) or count > 1
        self._icon_h = min(height * 0.22, 130.0) if has_icons else 0.0
        top = 50.0 + self._icon_h + (14 if has_icons else 0)
        bottom = height - (58.0 if any(p.xlabel for p in scene.panels) else 26.0)
        each = (width - 24) / count
        reach = scene.width + scene.gap
        self.axes = []
        for index, panel in enumerate(scene.panels):
            left = 12 + index * each + 78
            rect = QRectF(left, top, each - 78 - 14, bottom - top)
            self.axes.append(Axes(rect, (-reach * 1.08, reach * 1.08), panel.ylim,
                                  xlabel=panel.xlabel, ylabel=panel.label,
                                  x_ticks=False, x_spine=scene.x_spine))
        if old is not None and len(old) == len(self.axes):
            for axes, ylim in zip(self.axes, old):
                axes.ylim = ylim

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    # ── for a view ───────────────────────────────────────────────────────────

    def all_axes(self) -> list[Axes]:
        return list(self.axes)

    def panel_at(self, x: float, y: float):
        for index, axes in enumerate(self.axes):
            if axes.contains(x, y):
                return str(index), axes
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        return False, True              # the violin's width means nothing to zoom

    def _points(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        """Pixel positions of panel *index*'s points."""
        scene, panel, axes = self.scene, self.scene.panels[index], self.axes[index]
        x = panel.jitter * scene.width - (scene.width + scene.gap)
        return np.asarray(axes.x_pixel(x)), np.asarray(axes.y_pixel(panel.values))

    def under(self, x: float, y: float):
        panel = self.panel_at(x, y)
        if panel is None:
            return None
        index = int(panel[0])
        px, py = self._points(index)
        if not len(px):
            return None
        distance = np.hypot(px - x, py - y)
        nearest = int(np.argmin(distance))
        return int(self.scene.panels[index].rows[nearest]) if distance[nearest] <= REACH else None

    def describe(self, what) -> str:
        scene = self.scene
        name = scene.names[what] if what < len(scene.names) else str(what + 1)
        lines = [f"{scene.noun.capitalize()} {name}"]
        for panel in scene.panels:
            at = np.flatnonzero(panel.rows == what)
            if len(at):
                lines.append(f"{panel.label}: {panel.values[at[0]]:.4g}")
        return "\n".join(lines)

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        scene = self.scene
        width, height = self.size
        marked = self.marked
        colour = QColor.fromRgbF(*(float(c) for c in scene.colour[:3]))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, scene.title, width, size=14 if len(scene.panels) == 1 else 15)
        for index, (panel, axes) in enumerate(zip(scene.panels, self.axes)):
            self._paint_icon(painter, index, axes)
            if not len(panel.values):          # a metric that was not computed
                axes.paint_frame(painter)
                continue
            painter.save()
            axes.clip(painter)
            # The density, filled from the centre line outward.
            base = float(axes.x_pixel(scene.gap))
            xs = np.asarray(axes.x_pixel(scene.gap + panel.curve_x * scene.width))
            ys = np.asarray(axes.y_pixel(panel.curve_y))
            if len(ys) > 1:
                outline = [QPointF(base, float(ys[0]))]
                outline += [QPointF(float(x), float(y)) for x, y in zip(xs, ys)]
                outline.append(QPointF(base, float(ys[-1])))
                painter.setPen(QPen(colour, 1))
                painter.setBrush(colour)
                painter.drawPolygon(QPolygonF(outline))
            else:
                painter.setPen(QPen(colour, 2))
                painter.drawLine(QPointF(base, float(ys[0])), QPointF(float(xs[0]), float(ys[0])))
            px, py = self._points(index)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            for x, y in zip(px.tolist(), py.tolist()):
                painter.drawEllipse(QPointF(x, y), POINT_R, POINT_R)
            # Mean, with its standard error.
            centre = float(axes.x_pixel(0.0))
            pen = QPen(INK, 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(centre, float(axes.y_pixel(panel.mean - panel.sem))),
                             QPointF(centre, float(axes.y_pixel(panel.mean + panel.sem))))
            painter.setPen(QPen(GROUND, 1))
            painter.setBrush(INK)
            painter.drawEllipse(QPointF(centre, float(axes.y_pixel(panel.mean))), MEAN_R, MEAN_R)
            if marked is not None:
                at = np.flatnonzero(panel.rows == marked)
                if len(at):
                    painter.setPen(QPen(SELECTED, 2.2))
                    painter.setBrush(SELECTED)
                    painter.drawEllipse(QPointF(float(px[at[0]]), float(py[at[0]])),
                                        POINT_R + 1.5, POINT_R + 1.5)
            painter.restore()
            axes.paint_frame(painter)
        painter.restore()

    def _paint_icon(self, painter: QPainter, index: int, axes: Axes) -> None:
        if not self._icon_h:
            return
        image, panel = self._icons[index], self.scene.panels[index]
        box = QRectF(axes.rect.left() - 60, 46, axes.rect.width() + 60, self._icon_h)
        if image is None:
            if panel.icon is not None:      # the picture is missing: say what it was
                painter.setPen(INK)
                painter.setFont(figure_font(11))
                painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter
                                          | Qt.TextFlag.TextWordWrap), panel.label)
            return
        scale = min(box.width() / image.width(), box.height() / image.height())
        w, h = image.width() * scale, image.height() * scale
        painter.drawImage(QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h), image)
