"""MEA-NAP logo assets for the GUI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "mea-nap-logo.png"


def logo_pixmap(height: int, device_pixel_ratio: float = 1.0) -> QPixmap | None:
    """The MEA-NAP logo scaled to *height* pixels, or ``None`` if unavailable.

    Rendered at ``device_pixel_ratio`` times the requested size and tagged as
    such, so the artwork stays sharp on HiDPI screens while still laying out as
    ``height`` logical pixels. Returns ``None`` rather than raising if the asset
    is missing — a missing logo should never stop the GUI from opening.
    """
    if not LOGO_PATH.exists():
        return None
    source = QPixmap(str(LOGO_PATH))
    if source.isNull():
        return None

    ratio = max(1.0, float(device_pixel_ratio))
    scaled = source.scaledToHeight(
        int(round(height * ratio)),
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(ratio)
    return scaled


def logo_icon() -> QIcon:
    """The logo as a window/taskbar icon (empty QIcon if the asset is missing)."""
    return QIcon(str(LOGO_PATH)) if LOGO_PATH.exists() else QIcon()
