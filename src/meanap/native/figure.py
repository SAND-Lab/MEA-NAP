"""What every Qt-drawn figure offers, so one widget can show any of them.

A painter draws a scene into a box of logical pixels (``size``, ``paint``).
That is all the pipeline needs to write a file. An interactive view needs a
little more, and asks for it through the methods here: what is under the
pointer, how to describe it, which panel the wheel should zoom and along which
axes. A painter overrides only what its figure has; the defaults describe a
figure that is simply looked at.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QImage, QLinearGradient, QPainter, QPen

from meanap.native.axes import INK, Axes, nice_ticks, tick_label
from meanap.native.output import figure_font

__all__ = ["FigurePainter", "MatrixImage", "colormap", "colour_image", "paint_colour_bar",
           "paint_dots",
           "paint_title", "GROUND", "SELECTED"]

GROUND = QColor("#ffffff")
SELECTED = QColor("#d62728")


class FigurePainter:
    """Base of the painters. ``scene`` is the data; ``size`` the box, in pixels."""

    #: The size the pipeline saves this figure at.
    standard_size: tuple[float, float] = (960.0, 640.0)

    def __init__(self, scene, size: tuple[float, float] | None = None) -> None:
        self.scene = scene
        self.size = tuple(float(v) for v in (size or self.standard_size))
        #: What an interactive view points at, and what it has clicked.
        self.hovered = None
        self.pinned = None

    # ── for a file ───────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        raise NotImplementedError

    # ── for a view ───────────────────────────────────────────────────────────

    def resize(self, size: tuple[float, float]) -> None:
        """Lay the figure out again for a box of *size*, keeping any zoom."""
        self.size = (float(size[0]), float(size[1]))

    def reset(self) -> None:
        """Undo zooming and panning."""
        for axes in self.all_axes():
            axes.reset()

    def all_axes(self) -> list[Axes]:
        return []

    def panel_at(self, x: float, y: float) -> tuple[str, Axes] | None:
        """The panel pixel (x, y) is in: a key for it, and its axes."""
        return None

    def zoomable(self, key: str) -> tuple[bool, bool]:
        """Whether panel *key* zooms and pans along x, and along y."""
        return True, True

    def linked(self, key: str) -> list[Axes]:
        """Axes that follow panel *key*'s x range (and y, if it zooms in y)."""
        return []

    def under(self, x: float, y: float):
        """What is at pixel (x, y), as a value ``describe`` understands."""
        return None

    def describe(self, what) -> str:
        """One or two lines about *what*, for a tooltip and the read-out."""
        return ""

    def recording_of(self, what) -> str | None:
        """The recording *what* stands for, on a figure whose marks are
        recordings — so a view can offer that recording's own figures."""
        return None

    #: How far down the figure's title reaches, for :meth:`info_at`.
    info_band: float = 36.0

    def info_at(self, x: float, y: float) -> str | None:
        """What part of the figure pixel (x, y) is on, for a card explaining
        it: "title" over the title (by default the top ``info_band`` pixels),
        else None. A painter with a legend may name its parts too ("size",
        "colour", "edges"; see :func:`meanap.metric_info.metrics_for`)."""
        return "title" if 0 <= y <= self.info_band else None

    def pinnable(self, what) -> bool:
        """Whether a click on *what* keeps it marked."""
        return what is not None

    @property
    def marked(self):
        """What to mark now: the pinned thing, else the one pointed at."""
        return self.pinned if self.pinned is not None else self.hovered


# ── pieces painters share ─────────────────────────────────────────────────────


def colormap(cmap):
    """A matplotlib colour map, by name or as given. Only its table is used."""
    import matplotlib

    return matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap


def colour_image(values: np.ndarray, cmap, low: float, high: float,
                 missing=(0.83, 0.83, 0.83, 1.0)) -> tuple[QImage, np.ndarray]:
    """*values* as an image, one pixel per cell, and the pixels it borrows.

    Keep the returned array alive as long as the image: ``QImage`` does not
    copy it.
    """
    values = np.asarray(values, dtype=float)
    span = high - low if high > low else 1.0
    rgba = np.asarray(colormap(cmap)(np.clip((np.nan_to_num(values, nan=low) - low) / span,
                                             0, 1)), dtype=float)
    rgba[~np.isfinite(values)] = missing
    pixels = np.ascontiguousarray((rgba * 255).astype(np.uint8))
    rows, cols = values.shape
    return QImage(pixels.data, cols, rows, cols * 4, QImage.Format.Format_RGBA8888), pixels


def _device_scale(painter: QPainter) -> float:
    """Device pixels to the logical pixel, for what *painter* is drawing on."""
    from PyQt6.QtGui import QPaintEngine

    engine = painter.paintEngine()
    if engine is not None and engine.type() in (QPaintEngine.Type.SVG, QPaintEngine.Type.Pdf):
        return 3.0                      # a vector file: as fine as a 300 dpi image
    transform = painter.combinedTransform()
    ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
    return max(float(np.hypot(transform.m11(), transform.m12())) * ratio, 1e-6)


def paint_dots(painter: QPainter, xy, radius: float, colour: QColor) -> None:
    """Filled dots of *radius* at each pixel of *xy* (``(N, 2)``), no outline.

    Into an image, a dot is drawn once and stamped at every point: drawing
    tens of thousands of antialiased circles one by one takes a second or
    more, stamping them a few milliseconds. A file that keeps shapes (SVG,
    PDF) gets real circles. Stamps land on whole device pixels, a shift of
    at most half a pixel.
    """
    from PyQt6.QtGui import QPaintEngine, QTransform

    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    if not len(xy):
        return
    engine = painter.paintEngine()
    transform = painter.combinedTransform()
    vector = engine is not None and engine.type() in (QPaintEngine.Type.SVG,
                                                      QPaintEngine.Type.Pdf)
    plain = transform.type().value <= QTransform.TransformationType.TxScale.value and \
        abs(transform.m11() - transform.m22()) < 1e-9
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    if vector or not plain or len(xy) < 64:
        for x, y in xy.tolist():
            painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.restore()
        return
    scale = transform.m11()
    side = int(np.ceil(2 * radius * scale)) + 2
    stamp = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    stamp.fill(0)
    inked = QPainter(stamp)
    inked.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    inked.setPen(Qt.PenStyle.NoPen)
    inked.setBrush(colour)
    inked.drawEllipse(QPointF(side / 2, side / 2), radius * scale, radius * scale)
    inked.end()
    at = np.rint(xy * scale + [transform.dx(), transform.dy()] - side / 2).astype(int)
    painter.resetTransform()
    for x, y in at.tolist():
        painter.drawImage(x, y, stamp)
    painter.restore()


class MatrixImage:
    """A matrix as colours, drawn so that no cell is skipped.

    Drawn one image pixel to the cell, a matrix with more cells than the
    screen has pixels loses most of them — which ones is an accident of
    rounding, and a lone spike can vanish. So when several cells share a
    pixel they are first pooled into one: their mean, or with ``pool="max"``
    their largest, which keeps a single event visible at any zoom.
    """

    def __init__(self, values: np.ndarray, cmap, low: float, high: float,
                 pool: str = "mean") -> None:
        self.values = np.asarray(values, dtype=float)
        self.cmap, self.low, self.high, self.pool = cmap, low, high, pool
        self._key: tuple[int, int] | None = None
        self._image = self._pixels = None

    def pooled(self, ky: int, kx: int) -> np.ndarray:
        """The matrix with *ky* rows and *kx* columns pooled into each cell."""
        values = self.values
        if ky <= 1 and kx <= 1:
            return values
        import warnings

        rows, cols = values.shape
        tall, wide = -(-rows // ky), -(-cols // kx)
        padded = np.full((tall * ky, wide * kx), np.nan)
        padded[:rows, :cols] = values
        blocks = padded.reshape(tall, ky, wide, kx)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)     # a block of only NaN
            return (np.nanmax if self.pool == "max" else np.nanmean)(blocks, axis=(1, 3))

    def paint(self, painter: QPainter, target: QRectF, source: QRectF) -> None:
        """Draw the cells in *source* (x in columns, y in rows) to fill *target*."""
        scale = _device_scale(painter)
        kx = max(int(source.width() / max(target.width() * scale, 1.0)), 1)
        ky = max(int(source.height() / max(target.height() * scale, 1.0)), 1)
        if (ky, kx) != self._key:
            self._image, self._pixels = colour_image(self.pooled(ky, kx), self.cmap,
                                                     self.low, self.high)
            self._key = (ky, kx)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, self._image,
                          QRectF(source.x() / kx, source.y() / ky,
                                 source.width() / kx, source.height() / ky))
        painter.restore()


def paint_title(painter: QPainter, text: str, width: float, *, top: float = 4,
                height: float = 32, size: int = 15) -> None:
    painter.save()
    painter.setPen(INK)
    painter.setFont(figure_font(size))
    painter.drawText(QRectF(12, top, width - 24, height), Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()


def paint_colour_bar(painter: QPainter, bar: QRectF, cmap, low: float, high: float,
                     label: str = "", mark: float | None = None) -> None:
    """A vertical colour bar with ticks to its right, a label, and a marked value."""
    table = colormap(cmap)
    gradient = QLinearGradient(bar.bottomLeft(), bar.topLeft())
    for i in range(32):
        r, g, b, _ = table(i / 31)
        gradient.setColorAt(i / 31, QColor.fromRgbF(r, g, b))
    painter.save()
    painter.fillRect(bar, gradient)
    font = figure_font(11)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    line, widest = metrics.height(), 0.0
    span = high - low if high > low else 1.0
    ticks, step = nice_ticks(low, high, target=max(int(bar.height() // 45), 2))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(QPen(INK, 1))
    for value in ticks:
        y = bar.bottom() - (value - low) / span * bar.height()
        text = tick_label(value, step)
        widest = max(widest, metrics.horizontalAdvance(text))
        painter.drawLine(QPointF(bar.right(), y), QPointF(bar.right() + 4, y))
        painter.drawText(QRectF(bar.right() + 7, y - line / 2, 90, line),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
    if mark is not None and np.isfinite(mark):
        y = bar.bottom() - float(np.clip((mark - low) / span, 0, 1)) * bar.height()
        painter.setPen(QPen(INK, 2))
        painter.drawLine(QPointF(bar.left() - 4, y), QPointF(bar.right() + 4, y))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if label:
        painter.setPen(INK)
        painter.setFont(figure_font(12))
        painter.translate(bar.right() + 7 + widest + 8, bar.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-bar.height() / 2 - 60, 0, bar.height() + 120, line + 4),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
    painter.restore()
