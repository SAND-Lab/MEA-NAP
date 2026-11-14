"""One figure for each DIV a culture was recorded at, side by side.

The results viewer's "Across DIVs" view. Each cell is the same figure drawn
for one of the culture's recordings, on the same canvas the viewer would show
it on alone, so each can still be pointed at, zoomed and panned. Network cells
are linked: selecting an electrode in one selects it in all of them (not
imaged cells, which are numbered afresh in each session).

Saving writes the cells as one figure, through the painters that draw them,
so ``.svg`` and ``.pdf`` stay vector.
"""

from __future__ import annotations

import io
import math

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from meanap.native import output

__all__ = ["DivMontage", "Montage"]

#: Never more than this many figures in a row.
MAX_COLUMNS = 3
#: A cell is never shorter than this; past it the montage scrolls.
MIN_CELL_H = 300
#: Room for a cell's title in a saved montage.
TITLE_H = 30.0


def _picture(live) -> QImage | None:
    """A figure that is not drawn by a native painter, as a picture."""
    if live.image is not None:
        image = QImage(str(live.image))
        return None if image.isNull() else image
    figure = live.figure
    if figure is not None and hasattr(figure, "savefig"):
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=110,
                       bbox_inches="tight" if live.tight else None,
                       pad_inches=live.pad_inches)
        return QImage.fromData(buffer.getvalue())
    return None


class _PictureCell(QLabel):
    """A picture, scaled to fit, standing in for a figure with no painter."""

    def __init__(self, image: QImage) -> None:
        super().__init__()
        self._image = image
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 160)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def resizeEvent(self, event) -> None:
        self.setPixmap(QPixmap.fromImage(self._image).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        super().resizeEvent(event)

    def reset_view(self) -> None:
        pass


class Montage:
    """Several figures as one, for saving: anything with ``size`` and
    ``paint(QPainter)``, or a ``QImage``, each under its title."""

    def __init__(self, cells: list[tuple[str, object]], columns: int) -> None:
        self.cells = cells
        self.columns = max(1, columns)
        sizes = [self._size(item) for _title, item in cells]
        self.cell_w = max((w for w, _ in sizes), default=1.0)
        self.cell_h = max((h for _, h in sizes), default=1.0) + TITLE_H
        rows = math.ceil(len(cells) / self.columns) if cells else 1
        self.size = (self.cell_w * min(self.columns, max(len(cells), 1)), self.cell_h * rows)

    @staticmethod
    def _size(item) -> tuple[float, float]:
        if isinstance(item, QImage):
            return float(item.width()), float(item.height())
        return float(item.size[0]), float(item.size[1])

    def paint(self, painter: QPainter) -> None:
        painter.setFont(output.figure_font(15, bold=True))
        for index, (title, item) in enumerate(self.cells):
            row, column = divmod(index, self.columns)
            x, y = column * self.cell_w, row * self.cell_h
            painter.save()
            painter.translate(x, y)
            painter.setPen(QColor("#111111"))
            # A long name is shortened in the middle rather than run into the
            # next cell's.
            title = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, int(self.cell_w - 16))
            painter.drawText(QRectF(8, 0, self.cell_w - 16, TITLE_H),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
            painter.translate(0, TITLE_H)
            w, h = self._size(item)
            painter.setClipRect(QRectF(0, 0, w, h))
            if isinstance(item, QImage):
                painter.drawImage(QRectF(0, 0, w, h), item)
            else:
                item.paint(painter)
            painter.restore()
            painter.setFont(output.figure_font(15, bold=True))


class DivMontage(QWidget):
    """The cells, in a grid that scrolls when there are many."""

    hovered = pyqtSignal(str)
    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cells: list[tuple[str, QWidget]] = []
        self._columns = 1
        #: Whether selecting a node selects the same-named node in the other
        #: cells: right for electrodes, which are the same at every DIV, not
        #: for imaged cells, whose numbers are each session's own.
        self.link_nodes = True
        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._inner)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self._scroll)

    @property
    def canvases(self) -> list[QWidget]:
        return [widget for _title, widget in self._cells]

    def clear(self) -> None:
        self._cells = []
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def show_cells(self, cells: list[tuple[str, object, bool]]) -> None:
        """Show *cells*: ``(title, Live or message, is this the recording chosen)``."""
        from meanap.gui.figure_canvas import FigureCanvas
        from meanap.gui.network_canvas import NetworkCanvas
        from meanap.native.output import NativeFigure

        self.clear()
        self._columns = min(len(cells), MAX_COLUMNS) or 1
        rows = math.ceil(len(cells) / self._columns) if cells else 1
        for index, (title, got, current) in enumerate(cells):
            frame = QFrame()
            frame.setObjectName("montageCell")
            frame.setStyleSheet(
                "#montageCell { border: 1px solid %s; border-radius: 10px; background: #ffffff; }"
                % ("#9dbcf5" if current else "#e5e7eb"))
            box = QVBoxLayout(frame)
            box.setContentsMargins(6, 4, 6, 6)
            box.setSpacing(2)
            label = QLabel(title)
            label.setToolTip(title)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setStyleSheet("font-size: 12px; font-weight: %s; color: %s; border: none;"
                                % ("700" if current else "600",
                                   "#1d4ed8" if current else "#111827"))
            box.addWidget(label)
            if isinstance(got, str):
                widget = QLabel(got)
                widget.setWordWrap(True)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                widget.setStyleSheet("color: #6b7280; font-size: 12px; border: none;")
                widget.reset_view = lambda: None
            elif isinstance(got.figure, NativeFigure):
                network = hasattr(got.figure.painter, "node_at")
                widget = NetworkCanvas() if network else FigureCanvas()
                widget.setMinimumSize(240, 200)
                if network:
                    widget.surface.setMinimumSize(220, 180)
                if network and self.link_nodes:
                    widget.node_selected.connect(
                        lambda name, w=widget: self._follow(w, name))
                widget.hovered.connect(self.hovered)
                widget.picked.connect(self.picked)
                widget.show_figure(got.figure)
            else:
                image = _picture(got)
                if image is None:
                    widget = QLabel("Could not show this figure here.")
                    widget.reset_view = lambda: None
                else:
                    widget = _PictureCell(image)
            box.addWidget(widget, 1)
            self._grid.addWidget(frame, *divmod(index, self._columns))
            self._cells.append((title, widget))
        for row in range(rows):
            self._grid.setRowMinimumHeight(row, MIN_CELL_H)
            self._grid.setRowStretch(row, 1)
        for column in range(self._columns):
            self._grid.setColumnStretch(column, 1)

    def _follow(self, source: QWidget, name) -> None:
        """An electrode selected in one network: select it in the others."""
        from meanap.gui.network_canvas import NetworkCanvas

        for widget in self.canvases:
            if widget is not source and isinstance(widget, NetworkCanvas):
                widget.select_name(name)

    def reset_view(self) -> None:
        for widget in self.canvases:
            widget.reset_view()

    def _still_cells(self) -> list[tuple[str, object]]:
        cells = []
        for title, widget in self._cells:
            if hasattr(widget, "_still") and getattr(widget, "painter", None) is not None:
                if hasattr(widget, "_settle"):
                    widget._settle()
                cells.append((title, widget._still()))
            elif isinstance(widget, _PictureCell):
                cells.append((title, widget._image))
        return cells

    def export(self, path: str, *, dpi: int = output.DEFAULT_DPI) -> None:
        """Write the cells as shown, as one figure."""
        output.save(Montage(self._still_cells(), self._columns), path, default_dpi=dpi)
