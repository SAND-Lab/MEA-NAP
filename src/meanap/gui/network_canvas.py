"""The spatial network plot, interactive.

The drawing is :class:`meanap.native.network_paint.NetworkPainter` — the same
object, and the same ``paint`` call, that writes the pipeline's file. This
widget only adds what a view adds: wheel zoom, drag to pan, pointing at a node
to read it, clicking one to keep its connections and fade the rest, and
optionally the nodes' names. Exporting writes the figure as it is shown.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import QCheckBox, QToolTip, QVBoxLayout, QWidget

from meanap.native import output
from meanap.native.network_paint import (
    MANY_EDGES, MAX_LABELS, SMOOTH_ALWAYS, NetworkPainter,
)
from meanap.native.scene import NetworkScene

__all__ = ["NetworkCanvas", "GROUND", "INK", "SELECTED"]

GROUND = QColor("#ffffff")
INK = QColor("#16181d")
SELECTED = "#d62728"
#: One wheel notch zooms by this factor.
WHEEL_STEP = 1.2
#: How long the view must rest before it is drawn at full quality again.
REST_MS = 180
#: A press that moves less than this many pixels is a click, not a drag.
CLICK_SLOP = 4


class _Surface(QWidget):
    """The painted area: the figure and nothing else."""

    def __init__(self, canvas: "NetworkCanvas") -> None:
        super().__init__(canvas)
        self._canvas = canvas
        self.setMouseTracking(True)
        self.setMinimumSize(420, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._dragged = False

    def sizeHint(self) -> QSize:
        return QSize(960, 760)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        figure = self._canvas.painter
        if figure is None:
            painter.fillRect(self.rect(), GROUND)
        else:
            figure.paint(painter)
        painter.end()

    def resizeEvent(self, event) -> None:
        if self._canvas.painter is not None:
            self._canvas.painter.resize((self.width(), self.height()))
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        figure = self._canvas.painter
        if figure is None or not event.angleDelta().y():
            return
        at = event.position()
        figure.zoom(WHEEL_STEP ** (event.angleDelta().y() / 120), at.x(), at.y())
        self._canvas._moved()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = self._last = event.position()
            self._dragged = False

    def mouseMoveEvent(self, event) -> None:
        figure, at = self._canvas.painter, event.position()
        if figure is None:
            return
        if self._press is not None:
            if (at - self._press).manhattanLength() > CLICK_SLOP:
                self._dragged = True
            if self._dragged:
                step = at - self._last
                figure.pan(step.x(), step.y())
                self._canvas._moved()
            self._last = at
            return
        self._canvas._point(figure.node_at(at.x(), at.y()))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        dragged, self._press = self._dragged, None
        figure = self._canvas.painter
        if dragged or figure is None:
            return
        at = event.position()
        self._canvas.click(figure.node_at(at.x(), at.y()))

    def mouseDoubleClickEvent(self, _event) -> None:
        self._canvas.reset_view()

    def leaveEvent(self, _event) -> None:
        self._canvas._point(None)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._canvas.selected is not None:
            self._canvas.select(None)
            return
        super().keyPressEvent(event)


class NetworkCanvas(QWidget):
    """A network scene on screen: zoom, pan, point, select, export."""

    hovered = pyqtSignal(str)
    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.painter: NetworkPainter | None = None
        self.surface = _Surface(self)
        #: What export() writes: the painted area, without the controls.
        self.card = self.surface
        self.names = QCheckBox("Show names")
        self.names.toggled.connect(self._on_names)
        self._rest = QTimer(self)
        self._rest.setSingleShot(True)
        self._rest.setInterval(REST_MS)
        self._rest.timeout.connect(self._settle)
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 6, 8, 0)
        box.addWidget(self.surface, 1)
        box.addWidget(self.names)       # a control, so outside the figure

    # ── content ──────────────────────────────────────────────────────────────

    @property
    def scene(self) -> NetworkScene | None:
        """The network on show (of a pair of panels, the one they share)."""
        return None if self.painter is None else self.painter.network

    def show_scene(self, scene: NetworkScene, *, keep_view: bool = False) -> None:
        """Show one network. *keep_view* keeps the zoom and selection — a restyle."""
        self._show(NetworkPainter(scene, (self.surface.width(), self.surface.height())),
                   keep_view)

    def show_figure(self, figure, *, keep_view: bool = False) -> None:
        """Show a :class:`~meanap.native.output.NativeFigure` drawn by a network
        painter — one network, or a pair of panels — laid out for this widget."""
        self._show(type(figure.painter)(figure.scene, (self.surface.width(),
                                                        self.surface.height())), keep_view)

    def _show(self, figure, keep_view: bool) -> None:
        old, scene = self.painter, figure.network
        figure.names = self.names.isChecked()
        if keep_view and old is not None and type(old) is type(figure):
            figure.centre, figure.scale, figure.fitted = old.centre, old.scale, old.fitted
            if old.selected is not None and old.selected < len(scene.xy):
                figure.select(old.selected)
        self.painter = figure
        self.names.setEnabled(len(scene.xy) <= MAX_LABELS)
        self.surface.update()

    def reset_view(self) -> None:
        if self.painter is not None:
            self.painter.fit()
            self.surface.update()

    def _on_names(self, on: bool) -> None:
        if self.painter is not None:
            self.painter.names = on
            self.surface.update()

    def _moved(self) -> None:
        """The view changed: draw quickly now, properly once it rests."""
        figure = self.painter
        if len(figure.network.edge_nodes) > SMOOTH_ALWAYS or figure.thin_count > MANY_EDGES:
            figure.moving = True
            self._rest.start()
        self.surface.update()

    def _settle(self) -> None:
        self._rest.stop()
        if self.painter is not None and self.painter.moving:
            self.painter.moving = False
            self.surface.update()

    # ── pointing and selecting ───────────────────────────────────────────────

    @property
    def selected(self) -> int | None:
        return None if self.painter is None else self.painter.selected

    def neighbours(self, node: int) -> np.ndarray:
        return self.painter.network.neighbours(node)

    def _point(self, node: int | None) -> None:
        figure = self.painter
        if figure is None or node == figure.hovered:
            return
        figure.hovered = node
        self.surface.update()
        if node is None:
            QToolTip.hideText()
            self.hovered.emit("")
            return
        text = figure.describe(node)
        QToolTip.showText(QCursor.pos(), text, self.surface)
        self.hovered.emit(text.replace("\n", " · "))

    def click(self, node: int | None) -> None:
        """A click on *node*, or on empty space: select, or let go."""
        if node is None or node == self.selected:
            if self.selected is not None:
                self.select(None)
        else:
            self.select(node)

    def select(self, node: int | None) -> None:
        """Select one node — its connections stay, the rest fades — or none."""
        figure = self.painter
        if figure is None:
            return
        figure.select(node)
        self.surface.update()
        if node is None:
            self.picked.emit("")
            return
        count = len(figure.network.neighbours(node))
        self.picked.emit(figure.describe(node).replace("\n", " · ")
                         + f" · {count} connection{'' if count == 1 else 's'} shown")

    # ── export ───────────────────────────────────────────────────────────────

    def preview(self) -> QPixmap:
        """The figure as it would be exported now."""
        self._settle()
        return QPixmap.fromImage(output.render_image(self._still()))

    def export(self, path: str, *, dpi: int = output.DEFAULT_DPI) -> None:
        """Write the figure as shown — this zoom, this selection, these names.

        ``.svg`` and ``.pdf`` are vector; anything else is an image at *dpi*.
        """
        self._settle()
        output.save(self._still(), path, default_dpi=dpi)

    def _still(self) -> NetworkPainter:
        """The painter, without the marks that only follow the pointer."""
        figure = self.painter
        figure.hovered = None
        return figure
