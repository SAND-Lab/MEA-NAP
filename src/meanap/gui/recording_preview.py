"""A small card previewing one recording, raised over a cross-recording figure.

Pointing at a recording's point on a comparison shows that recording's own
figure here (its raster, say); clicking the card opens the recording. The card
is a child widget of the viewer, not a window of its own, so it never takes
focus away from the figure under it.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

__all__ = ["RecordingPreview", "PREVIEW_W"]

#: The picture's width on screen, in logical pixels.
PREVIEW_W = 380
PREVIEW_H = 230


class RecordingPreview(QFrame):
    """Title, picture, and a line saying what a click does."""

    opened = pyqtSignal(str)
    entered = pyqtSignal()
    left = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("recordingPreview")
        self.setStyleSheet(
            "#recordingPreview { background: #ffffff; border: 1px solid #c7d7f8;"
            " border-radius: 10px; }"
            "#recordingPreview QLabel { border: none; background: transparent; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(Qt.GlobalColor.gray)
        self.setGraphicsEffect(shadow)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name = ""
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 12px; font-weight: 700; color: #111827;")
        self.detail = QLabel()
        self.detail.setStyleSheet("font-size: 11px; color: #6b7280;")
        self.picture = QLabel()
        self.picture.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.hint = QLabel()
        self.hint.setStyleSheet("font-size: 11px; color: #1d4ed8; font-weight: 600;")
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(4)
        for widget in (self.title, self.detail, self.picture, self.hint):
            box.addWidget(widget)
        self.hide()

    def show_for(self, name: str, detail: str, figure: str, image: QImage | None,
                 *, move: bool = True) -> None:
        """Preview *name*'s *figure*; *image* None means it is still being drawn."""
        self.name = name
        self.title.setText(name)
        self.detail.setText(" · ".join(t for t in (detail, figure) if t))
        self.hint.setText(f"Click to open this recording's {figure.lower()}  ›")
        self.set_image(image, failed="")
        self.adjustSize()
        if move or not self.isVisible():
            self._place()
        self.show()
        self.raise_()

    def set_image(self, image: QImage | None, *, failed: str = "") -> None:
        if image is None:
            self.picture.setPixmap(QPixmap())
            self.picture.setText(failed or "Drawing…")
            return
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(max(image.width() / PREVIEW_W, 1.0))
        if pixmap.deviceIndependentSize().height() > PREVIEW_H:
            pixmap.setDevicePixelRatio(image.height() / PREVIEW_H)
        self.picture.setText("")
        self.picture.setPixmap(pixmap)

    def _place(self) -> None:
        """Beside the pointer, kept inside the viewer."""
        parent = self.parentWidget()
        at = parent.mapFromGlobal(QCursor.pos())
        size = self.sizeHint()
        bounds = QRect(QPoint(0, 0), parent.size()).adjusted(8, 8, -8, -8)
        x, y = at.x() + 22, at.y() + 18
        if x + size.width() > bounds.right():
            x = at.x() - 22 - size.width()      # to the pointer's left instead
        if y + size.height() > bounds.bottom():
            y = bounds.bottom() - size.height()
        self.move(max(x, bounds.left()), max(y, bounds.top()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.name:
            self.opened.emit(self.name)

    def enterEvent(self, _event) -> None:
        self.entered.emit()

    def leaveEvent(self, _event) -> None:
        self.left.emit()
