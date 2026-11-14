"""A small drawing of an electrode layout, to check a custom one by eye.

A layout file is a list of numbers, and the mistakes it can hold — x and y
swapped, rows counted from the bottom, a channel typed twice over — are
invisible in it and obvious in a picture. The Data tab shows this beside the
layout file, drawn the way the run's spatial figures will place electrodes.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

__all__ = ["LayoutPreview", "choose_layout_item"]


class LayoutPreview(QWidget):
    """Electrodes as dots at their positions, each labelled with its channel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._channels = np.zeros(0, dtype=int)
        self._xy = np.zeros((0, 2))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(180)

    def sizeHint(self) -> QSize:
        return QSize(260, 200)

    def set_layout(self, channels, xy) -> None:
        """*xy* in the layout's drawing units (y up), as get_coords_from_layout gives."""
        self._channels = np.asarray(channels).ravel()
        self._xy = np.asarray(xy, dtype=float).reshape(-1, 2)
        self.update()

    def clear(self) -> None:
        self.set_layout([], np.zeros((0, 2)))

    def paintEvent(self, _event) -> None:
        if not len(self._xy):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = self._xy.min(axis=0), self._xy.max(axis=0)
        span = np.maximum(hi - lo, 1e-9)
        # Room round the edge for a dot and its label; keep the aspect ratio.
        pad = 18.0
        # (and a label's height more below, where the labels go)
        box = QRectF(pad, pad, max(self.width() - 2 * pad, 1),
                     max(self.height() - 2 * pad - 12, 1))
        scale = min(box.width() / span[0] if span[0] > 1e-6 else np.inf,
                    box.height() / span[1] if span[1] > 1e-6 else np.inf)
        if not np.isfinite(scale):
            scale = 1.0
        width, height = span * scale
        left = box.left() + (box.width() - width) / 2
        top = box.top() + (box.height() - height) / 2

        def at(x: float, y: float) -> QPointF:
            return QPointF(left + (x - lo[0]) * scale, top + (hi[1] - y) * scale)

        # Dots shrink as electrodes crowd, so a 256-electrode array stays legible.
        d = np.sqrt(box.width() * box.height() / max(len(self._xy), 1))
        radius = float(np.clip(d * 0.18, 2.0, 7.0))
        painter.setPen(QPen(QColor("#1d4ed8"), 1))
        painter.setBrush(QColor("#93c5fd"))
        points = [at(x, y) for x, y in self._xy]
        for p in points:
            painter.drawEllipse(p, radius, radius)
        if d >= 16:  # labels only where they fit
            font = QFont(self.font())
            font.setPointSizeF(max(6.5, min(8.5, d * 0.22)))
            painter.setFont(font)
            painter.setPen(QColor("#374151"))
            for p, ch in zip(points, self._channels):
                painter.drawText(QRectF(p.x() - 20, p.y() + radius, 40, 12),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 str(int(ch)))
        painter.end()


def choose_layout_item(combo, params) -> None:
    """Show the run's layout in a viewer's layout list; a custom one is added,
    carrying its table (``layout_of``) as the item's data."""
    from meanap.pipeline.channel_layout import layout_of

    layout = layout_of(params)
    if params.channel_layout == "Custom" and layout != "Custom":
        index = combo.findText("Custom")
        if index < 0:
            combo.addItem("Custom")
            index = combo.count() - 1
        combo.setItemData(index, layout)
        combo.setCurrentIndex(index)
        return
    index = combo.findText(params.channel_layout)
    if index >= 0:
        combo.setCurrentIndex(index)
