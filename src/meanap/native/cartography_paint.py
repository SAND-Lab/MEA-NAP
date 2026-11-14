"""The node cartography scatter, drawn with ``QPainter``.

Every node by its participation coefficient and within-module degree z-score,
coloured by the role those two give it, with the boundaries between roles
drawn (the top panel of ``NodeCartography.m``) and the picture that explains
the roles underneath. Pointing at a node names it and its role.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPen

from meanap.native.axes import INK, Axes
from meanap.native.figure import GROUND, SELECTED, FigurePainter, paint_title
from meanap.native.output import figure_font
from meanap.native.scene import CartographyScene

__all__ = ["CartographyPainter"]

UNCLASSIFIED = (0.5, 0.5, 0.5)
RADIUS = 4.0
REACH = 8.0


class CartographyPainter(FigurePainter):
    """Draws the cartography scatter. What a view points at is a node's row."""

    standard_size = (640.0, 860.0)

    def __init__(self, scene: CartographyScene, size: tuple[float, float] | None = None):
        super().__init__(scene, size)
        self._diagram = QImage(scene.diagram) if scene.diagram else QImage()
        self._drawn = np.flatnonzero(np.isfinite(scene.pc) & np.isfinite(scene.z))
        self.axes: Axes | None = None
        self._layout(keep=False)

    def _layout(self, *, keep: bool) -> None:
        old = (self.axes.xlim, self.axes.ylim) if keep and self.axes is not None else None
        scene = self.scene
        width, height = self.size
        top, bottom = 84.0, 58.0
        # Under the plot: the picture of the roles, or failing that a key.
        below = height * 0.30
        self.axes = Axes(QRectF(84, top, width - 84 - 36, height - top - bottom - below),
                         scene.xlim, scene.ylim, xlabel="participation coefficient",
                         ylabel="within-module degree z-score", title="node cartography")
        self._below = QRectF(36, height - below + 6, width - 72, below - 22)
        if old is not None:
            self.axes.xlim, self.axes.ylim = old

    def resize(self, size: tuple[float, float]) -> None:
        super().resize(size)
        self._layout(keep=True)

    def all_axes(self) -> list[Axes]:
        return [self.axes]

    def panel_at(self, x: float, y: float):
        return ("scatter", self.axes) if self.axes.contains(x, y) else None

    def _pixels(self) -> np.ndarray:
        """Where each drawn node is, a row per entry of ``_drawn``."""
        scene = self.scene
        return np.column_stack([self.axes.x_pixel(scene.pc[self._drawn]),
                                self.axes.y_pixel(scene.z[self._drawn])])

    def under(self, x: float, y: float):
        if not len(self._drawn) or not self.axes.contains(x, y):
            return None
        at = self._pixels()
        distance = np.hypot(at[:, 0] - x, at[:, 1] - y)
        nearest = int(np.argmin(distance))
        return int(self._drawn[nearest]) if distance[nearest] <= REACH else None

    def _role(self, node: int) -> tuple[str, tuple]:
        return self.scene.roles.get(int(self.scene.role[node]), ("not classified", UNCLASSIFIED))

    def describe(self, what) -> str:
        scene = self.scene
        return (f"{scene.noun.capitalize()} {scene.names[what]}: {self._role(what)[0]}\n"
                f"participation coefficient {scene.pc[what]:.3g}, "
                f"within-module z-score {scene.z[what]:.3g}")

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        scene, axes = self.scene, self.axes
        width, height = self.size
        marked = self.marked
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        paint_title(painter, scene.title, width, top=6, height=30)

        painter.save()
        axes.clip(painter)
        hub, peripheral, connector, provincial, connector_hub = scene.boundaries
        (x0, x1), (y0, y1) = axes.home
        dashed = QPen(INK, 1, Qt.PenStyle.DashLine)
        painter.setPen(dashed)
        hub_y = float(axes.y_pixel(hub))
        lines = [QLineF(float(axes.x_pixel(x0)), hub_y, float(axes.x_pixel(x1)), hub_y)]
        # Below the hub line the two that divide the non-hubs; above it, the hubs.
        for at, low, high in ((peripheral, y0, hub), (connector, y0, hub),
                              (provincial, hub, y1), (connector_hub, hub, y1)):
            x = float(axes.x_pixel(at))
            lines.append(QLineF(x, float(axes.y_pixel(low)), x, float(axes.y_pixel(high))))
        painter.drawLines(lines)
        painter.setPen(Qt.PenStyle.NoPen)
        at = self._pixels()
        for (x, y), node in zip(at.tolist(), self._drawn.tolist()):
            painter.setBrush(QColor.fromRgbF(*self._role(node)[1]))
            painter.drawEllipse(QPointF(x, y), RADIUS, RADIUS)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if marked is not None and marked in self._drawn:
            x, y = at[int(np.flatnonzero(self._drawn == marked)[0])].tolist()
            painter.setPen(QPen(SELECTED, 2.5))
            painter.drawEllipse(QPointF(x, y), RADIUS + 3, RADIUS + 3)
        painter.restore()
        axes.paint_frame(painter)
        if self._diagram.isNull():
            self._paint_key(painter)
        else:
            self._paint_diagram(painter)
        painter.restore()

    def _paint_diagram(self, painter: QPainter) -> None:
        box, image = self._below, self._diagram
        scale = min(box.width() / image.width(), box.height() / image.height())
        w, h = image.width() * scale, image.height() * scale
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h),
                          image)
        painter.restore()

    def _paint_key(self, painter: QPainter) -> None:
        font = figure_font(12)
        painter.setFont(font)
        line = QFontMetricsF(font).height()
        box = self._below
        for row, (_role, (label, colour)) in enumerate(sorted(self.scene.roles.items())):
            y = box.top() + row * (line + 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor.fromRgbF(*colour))
            painter.drawEllipse(QPointF(box.left() + 60, y + line / 2), 6, 6)
            painter.setPen(INK)
            painter.drawText(QRectF(box.left() + 76, y, 300, line),
                             Qt.AlignmentFlag.AlignVCenter, label)
        painter.setBrush(Qt.BrushStyle.NoBrush)
