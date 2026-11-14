"""Any Qt-drawn figure, interactive.

The drawing is the figure's painter (:class:`meanap.native.figure.FigurePainter`)
— the object that writes the pipeline's file. This widget adds what a view
adds, the same for every figure:

* pointing at a mark describes it, in a tooltip and the read-out, and the
  painter marks whatever else in the figure it bears on;
* clicking keeps it marked; clicking it again, clicking empty space or Esc
  lets go;
* the wheel zooms the panel under the pointer, dragging moves it, a double
  click resets — along the axes the painter says that panel zooms on, with
  any panels it says are linked following.

What each of those means for a figure is the painter's to say; nothing here
knows which figure it is showing.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import QToolTip, QWidget

from meanap.native import output
from meanap.native.figure import FigurePainter

__all__ = ["FigureCanvas"]

WHEEL_STEP = 1.2
CLICK_SLOP = 4


class FigureCanvas(QWidget):
    """A figure's painter on screen: point, pin, zoom, export."""

    hovered = pyqtSignal(str)
    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.painter: FigurePainter | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 340)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._dragged = False
        self._grabbed = None            # (key, axes) of the panel being dragged

    def sizeHint(self) -> QSize:
        return QSize(1056, 634)

    # ── content ──────────────────────────────────────────────────────────────

    @property
    def scene(self):
        return None if self.painter is None else self.painter.scene

    def show_figure(self, figure, *, keep_view: bool = False) -> None:
        """Show a :class:`~meanap.native.output.NativeFigure`, laid out for this widget."""
        del keep_view                   # a new scene has new ranges: start whole
        self.painter = type(figure.painter)(figure.scene, (self.width(), self.height()))
        self.update()

    def reset_view(self) -> None:
        if self.painter is not None:
            self.painter.reset()
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self.painter is None:
            painter.fillRect(self.rect(), Qt.GlobalColor.white)
        else:
            self.painter.paint(painter)
        painter.end()

    def resizeEvent(self, event) -> None:
        if self.painter is not None:
            self.painter.resize((self.width(), self.height()))
        super().resizeEvent(event)

    # ── pointing and pinning ─────────────────────────────────────────────────

    @property
    def pinned(self):
        return None if self.painter is None else self.painter.pinned

    def point(self, what) -> None:
        """The pointer is over *what* (see ``FigurePainter.under``)."""
        figure = self.painter
        if figure is None or what == figure.hovered:
            return
        figure.hovered = what
        self.update()
        text = figure.describe(what) if what is not None else ""
        if not text:
            QToolTip.hideText()
            self.hovered.emit("")
            return
        QToolTip.showText(QCursor.pos(), text, self)
        self.hovered.emit(text.replace("\n", " · "))

    def pin(self, what) -> None:
        """Keep *what* marked while the pointer moves on, or let go."""
        figure = self.painter
        if figure is None:
            return
        if not figure.pinnable(what):
            what = None
        figure.pinned = what
        self.update()
        self.picked.emit("" if what is None else figure.describe(what).replace("\n", " · "))

    def click(self, what) -> None:
        """A click on *what*: pin it, or let go if it is pinned or nothing."""
        self.pin(None if what == self.pinned else what)

    # ── events ───────────────────────────────────────────────────────────────

    def _move(self, key: str, axes, act) -> None:
        """Apply *act* to a panel's axes and to the ones linked to it."""
        along_x, along_y = self.painter.zoomable(key)
        act(axes, along_x, along_y)
        for other in self.painter.linked(key):
            if along_x:
                other.xlim = axes.xlim
            if along_y:
                other.ylim = axes.ylim
        self.update()

    def mouseMoveEvent(self, event) -> None:
        figure, at = self.painter, event.position()
        if figure is None:
            return
        if self._press is not None:
            if (at - self._press).manhattanLength() > CLICK_SLOP:
                self._dragged = True
            if self._dragged and self._grabbed is not None:
                step = at - self._last
                self._move(*self._grabbed, lambda axes, x, y: axes.pan(
                    step.x(), step.y(), along_x=x, along_y=y))
            self._last = at
            return
        self.point(figure.under(at.x(), at.y()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.painter is not None:
            self._press = self._last = event.position()
            self._dragged = False
            panel = self.painter.panel_at(self._press.x(), self._press.y())
            self._grabbed = panel if panel and any(self.painter.zoomable(panel[0])) else None

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        dragged, self._press, self._grabbed = self._dragged, None, None
        if dragged or self.painter is None:
            return
        at = event.position()
        self.click(self.painter.under(at.x(), at.y()))

    def wheelEvent(self, event) -> None:
        figure = self.painter
        if figure is None or not event.angleDelta().y():
            return
        at = event.position()
        panel = figure.panel_at(at.x(), at.y())
        if panel is None or not any(figure.zoomable(panel[0])):
            return
        factor = WHEEL_STEP ** (event.angleDelta().y() / 120)
        self._move(*panel, lambda axes, x, y: axes.zoom(
            factor, at.x(), at.y(), along_x=x, along_y=y))

    def mouseDoubleClickEvent(self, _event) -> None:
        self.reset_view()

    def leaveEvent(self, _event) -> None:
        self.point(None)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.pinned is not None:
            self.pin(None)
            return
        super().keyPressEvent(event)

    # ── export ───────────────────────────────────────────────────────────────

    def preview(self) -> QPixmap:
        return QPixmap.fromImage(output.render_image(self._still()))

    def export(self, path: str, *, dpi: int = output.DEFAULT_DPI) -> None:
        """Write the figure as shown — these zooms, this pinned mark.

        ``.svg`` and ``.pdf`` are vector, except that a matrix or raster is an
        embedded picture, one pixel per cell.
        """
        output.save(self._still(), path, default_dpi=dpi)

    def _still(self) -> FigurePainter:
        """The painter, without the marks that only follow the pointer."""
        self.painter.hovered = None
        return self.painter
