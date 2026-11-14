"""Writing a Qt-drawn figure to a file, from wherever the pipeline is running.

A figure is anything with a ``size`` — its width and height in logical pixels,
96 to the inch — and a ``paint(painter)`` method that draws it into that box.
:func:`save` writes one as PNG, SVG or PDF by the path's suffix.

The pipeline plots from three places: the main thread of a command-line run,
a background thread of the application, and spawned worker processes. Only
``QPainter`` on an image or a vector device is used here — no widgets — which
Qt allows on any thread. A process that has no Qt application yet gets one on
the ``offscreen`` platform, so no display is needed.

Text is set in DejaVu Sans, loaded from the file matplotlib ships, so a figure
is the same whatever fonts the computer has and however the run was started.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

__all__ = ["NativeFigure", "ensure_app", "figure_font", "save", "render_image",
           "DEFAULT_DPI", "LOGICAL_DPI"]

#: Logical pixels per inch: a figure's sizes are in these.
LOGICAL_DPI = 96
#: Resolution of a saved PNG — from the pipeline or exported from the viewer —
#: unless the run overrides it (the web viewer's thumbnails do).
DEFAULT_DPI = 300

_lock = threading.Lock()
_app = None
_family: str | None = None


@dataclass
class NativeFigure:
    """A scene and the painter that draws it: what a native plotter "saves".

    When the viewer intercepts a save (see
    :func:`meanap.pipeline.figure_output.capture_figures`) this is what it is
    handed, so it can show the scene live instead of a picture of it.
    """

    kind: str                # "network", …
    scene: object
    painter: object          # has .size and .paint(QPainter)


def ensure_app():
    """A Qt application for this process, creating a display-less one if needed."""
    global _app
    from PyQt6.QtCore import QCoreApplication

    with _lock:
        existing = QCoreApplication.instance()
        if existing is not None:
            return existing
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        _app = QApplication(["meanap"])
        return _app


def figure_font(pixel_size: float, *, bold: bool = False):
    """The font figures are lettered in, at *pixel_size* logical pixels."""
    global _family
    from PyQt6.QtGui import QFont, QFontDatabase

    ensure_app()
    with _lock:
        if _family is None:
            import matplotlib

            folder = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
            family = ""
            for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
                found = QFontDatabase.addApplicationFont(str(folder / name))
                families = QFontDatabase.applicationFontFamilies(found) if found >= 0 else []
                family = family or (families[0] if families else "")
            _family = family or "DejaVu Sans"
    font = QFont(_family)
    font.setPixelSize(max(int(round(pixel_size)), 1))
    font.setBold(bold)
    return font


def render_image(figure, scale: float = 1.0):
    """*figure* as a ``QImage``, *scale* device pixels to the logical pixel."""
    from PyQt6.QtGui import QColor, QImage, QPainter

    ensure_app()
    width, height = figure.size
    image = QImage(max(int(round(width * scale)), 1), max(int(round(height * scale)), 1),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    try:
        painter.scale(scale, scale)
        figure.paint(painter)
    finally:
        painter.end()
    return image


def save(figure, path: Path | str, *, default_dpi: int = DEFAULT_DPI,
         capture: NativeFigure | None = None) -> None:
    """Write *figure* to *path*: ``.svg`` and ``.pdf`` as vector, else an image.

    The resolution of an image is the run's override
    (:func:`meanap.pipeline.figure_output.figure_dpi`) if one is active, else
    *default_dpi*. If the viewer is intercepting saves, *capture* is handed to
    it and nothing is written.
    """
    from meanap.pipeline import figure_output

    if capture is not None and figure_output.capture_native(capture, Path(path)):
        return
    ensure_app()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = figure.size
    suffix = path.suffix.lower()
    if suffix == ".svg":
        from PyQt6.QtCore import QRect, QSize
        from PyQt6.QtGui import QPainter
        from PyQt6.QtSvg import QSvgGenerator

        device = QSvgGenerator()
        device.setFileName(str(path))
        device.setSize(QSize(int(width), int(height)))
        device.setViewBox(QRect(0, 0, int(width), int(height)))
        device.setResolution(LOGICAL_DPI)
        painter = QPainter(device)
        try:
            painter.fillRect(0, 0, int(width), int(height), _white())
            figure.paint(painter)
        finally:
            painter.end()
    elif suffix == ".pdf":
        from PyQt6.QtCore import QMarginsF, QSizeF
        from PyQt6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

        device = QPdfWriter(str(path))
        device.setPageSize(QPageSize(QSizeF(width / LOGICAL_DPI, height / LOGICAL_DPI),
                                     QPageSize.Unit.Inch))
        device.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Inch)
        device.setResolution(LOGICAL_DPI)
        painter = QPainter(device)
        try:
            figure.paint(painter)
        finally:
            painter.end()
    else:
        dpi = figure_output.current_dpi() or default_dpi
        image = render_image(figure, dpi / LOGICAL_DPI)
        image.setDotsPerMeterX(int(round(dpi / 0.0254)))
        image.setDotsPerMeterY(int(round(dpi / 0.0254)))
        if not image.save(str(path)):
            raise OSError(f"Could not write {path}")


def _white():
    from PyQt6.QtGui import QColor

    return QColor("#ffffff")
