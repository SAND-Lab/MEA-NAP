"""The results viewer, inside the app (prototype: per-recording figures).

The web viewer shows each figure as a picture the server drew. This shows the
figure itself: the same pipeline drawing code runs, but its matplotlib figure
is handed over live (:mod:`meanap.viewer.live`) and hosted on a Qt canvas. So
the drawing is what the pipeline would have saved, and on top of that it can be
zoomed and panned, and its marks can be pointed at — which electrode a node is,
the value under the cursor on a heat map.

Three parts:

* :class:`FigureView` — one figure, fitted to the space it has at the shape the
  pipeline gave it, with wheel zoom, drag pan and the hover read-out.
* :class:`StylePanel` — the Network Viewer control set, built from the same
  schema the web page builds its form from (:mod:`meanap.viewer.controls`).
* :class:`ResultsViewer` — recordings and figures on the left, the figure in
  the middle, styling on the right.

Drawing happens off the GUI thread and the newest request wins, so dragging a
spin box does not queue a redraw per step.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import (
    QObject, QPointF, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QFontInfo, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QStackedWidget, QToolTip, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from meanap.viewer.live import Live, live_figure

__all__ = ["FigureView", "StylePanel", "ResultsViewer"]

#: How close, in pixels, the cursor must be to a mark with no size of its own.
HOVER_PIXELS = 9.0
#: One wheel notch zooms by this factor.
ZOOM_STEP = 1.2
#: Text is never shown smaller than this many screen pixels. The pipeline sizes
#: text for a printed page (7-point legends on an 8-inch figure), which lands
#: under 9 px in a window; the saved file keeps the pipeline's sizes.
MIN_TEXT_PX = 11.5
#: The canvas is never asked to be larger than this on its long side, which is
#: what bounds how far a whole figure can be magnified.
MAX_CANVAS_PX = 6000
#: Wait this long after the last control change before redrawing.
RESTYLE_DELAY_MS = 120
#: How long a recording's preview card stays after the pointer leaves its
#: point — time to move onto the card and click it.
PREVIEW_GRACE_MS = 700


# ── the figure ────────────────────────────────────────────────────────────────


class _Ring(QWidget):
    """A ring over the hovered mark, painted by Qt so matplotlib is not redrawn."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._at: QPointF | None = None
        self._radius = 0.0

    def mark(self, at: QPointF | None, radius: float = 0.0) -> None:
        if at == self._at and radius == self._radius:
            return
        self._at, self._radius = at, radius
        self.update()

    def paintEvent(self, _event) -> None:
        if self._at is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for colour, width in ((QColor(255, 255, 255, 230), 4.0),
                              (QColor(214, 39, 40), 2.0)):
            painter.setPen(QPen(colour, width))
            painter.drawEllipse(self._at, self._radius, self._radius)


class FigureView(QWidget):
    """One matplotlib figure, live.

    The figure keeps the size in inches the pipeline drew it at and its
    resolution is set from the space available, so text, line widths and
    spacing stay in the proportions of the saved file however the window is
    sized. A figure the pipeline saves cropped (``bbox_inches="tight"``) is
    shown cropped the same way, by placing the canvas so that only the crop is
    inside this widget.
    """

    #: (description) of the mark under the cursor, or "" when there is none.
    hovered = pyqtSignal(str)
    #: (description) of a mark that was clicked.
    picked = pyqtSignal(str)
    #: Seconds the canvas took to paint the figure the first time.
    painted = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self._canvas = None
        self._figure = None
        self._image: QLabel | None = None
        self._pixmap: QPixmap | None = None
        self._size_in = (1.0, 1.0)
        self._crop = (0.0, 0.0, 1.0, 1.0)       # inches, matplotlib's origin
        self._home: list = []
        self._pan_axes = None
        self._pressed_at = None
        #: Magnification of the whole figure, and where its canvas then sits.
        self._zoom = 1.0
        self._origin: tuple[float, float] | None = None
        self._dragging_from = None
        #: (text artist, the pipeline's size, the pipeline's font) for each text.
        self._texts: list = []
        self._ring = _Ring(self)
        self._message = QLabel("", self)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #6b7280;")
        self.setStyleSheet("FigureView { background: white; }")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    # ── what is shown ────────────────────────────────────────────────────────

    @property
    def figure(self):
        return self._figure

    def show_message(self, text: str) -> None:
        self._clear()
        self._message.setText(text)
        self._message.setGeometry(self.rect())
        self._message.show()

    def show_live(self, live: Live) -> None:
        """Take ownership of *live* and show it."""
        self._clear()
        self._message.hide()
        if live.figure is None:
            self._show_image(live.image)
            return
        # Imported here so the module can be imported without a Qt backend
        # having been chosen for matplotlib (the pipeline uses Agg).
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

        fig = live.figure
        self._figure = fig
        width, height = (float(v) for v in fig.get_size_inches())
        self._size_in = (width, height)
        self._crop = (0.0, 0.0, width, height)
        # How the pipeline would have saved it, for save() to do the same.
        self._save_kwargs = ({"bbox_inches": "tight", "pad_inches": live.pad_inches}
                             if live.tight else {})
        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setParent(self)
        if live.tight:
            try:
                box = fig.get_tightbbox().padded(live.pad_inches)
                self._crop = (max(box.x0, 0.0), max(box.y0, 0.0),
                              min(box.x1, width), min(box.y1, height))
            except Exception:
                pass                    # an uncroppable figure is shown whole
        self._home = [(ax, ax.get_xlim(), ax.get_ylim()) for ax in fig.axes]
        self._zoom, self._origin = 1.0, None
        self._adopt_text()
        self._canvas.mpl_connect("scroll_event", self._on_scroll)
        self._canvas.mpl_connect("button_press_event", self._on_press)
        self._canvas.mpl_connect("button_release_event", self._on_release)
        self._canvas.mpl_connect("motion_notify_event", self._on_motion)
        self._canvas.mpl_connect("figure_leave_event", lambda _e: self._point_at(None))
        self._fit()
        self._canvas.show()
        self._ring.raise_()
        self._time_first_paint()

    def _adopt_text(self) -> None:
        """Note every text's own size and font, and give it the window's font.

        A figure in matplotlib's default face beside widgets in the system's
        reads as a pasted-in picture. Only done when matplotlib can find the
        application's font; :meth:`save` puts the pipeline's back.
        """
        from matplotlib import font_manager
        from matplotlib.text import Text
        from PyQt6.QtWidgets import QApplication

        # The font Qt actually resolved, which is not always the one asked for.
        family = QFontInfo(QApplication.font()).family()
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except Exception:
            family = None
        self._texts = []
        for text in self._figure.findobj(Text):
            if not text.get_text():
                continue
            self._texts.append((text, text.get_fontsize(), text.get_fontfamily()))
            if family:
                # The pipeline's face stays as the fallback, for the glyphs the
                # window's font lacks (a true minus sign, in some).
                text.set_fontfamily([family, *text.get_fontfamily()])

    def _size_text(self, scale: float) -> None:
        """Hold every text at or above :data:`MIN_TEXT_PX` at *scale* px/inch."""
        floor = MIN_TEXT_PX * 72 / scale
        for text, size, _family in self._texts:
            wanted = max(size, floor)
            if abs(text.get_fontsize() - wanted) > 1e-6:
                text.set_fontsize(wanted)

    def save(self, path: str, dpi: int = 300) -> None:
        """Save what is shown, with the pipeline's own text sizes and fonts."""
        shown = [(t, t.get_fontsize(), t.get_fontfamily()) for t, _, _ in self._texts]
        for text, size, family in self._texts:
            text.set_fontsize(size)
            text.set_fontfamily(family)
        try:
            self._figure.savefig(path, dpi=dpi, **getattr(self, "_save_kwargs", {}))
        finally:
            for text, size, family in shown:
                text.set_fontsize(size)
                text.set_fontfamily(family)
            self._canvas.draw_idle()

    def _time_first_paint(self) -> None:
        import time

        started = time.perf_counter()
        self._canvas.draw()
        self.painted.emit(time.perf_counter() - started)

    def _show_image(self, path: Path | None) -> None:
        self._pixmap = QPixmap(str(path)) if path else QPixmap()
        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.show()
        self._fit()
        self.painted.emit(0.0)

    def _clear(self) -> None:
        self._ring.mark(None)
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas.deleteLater()
            self._canvas = None
        if self._figure is not None:
            self._figure.clear()        # drop the artists now, not at GC
            self._figure = None
        if self._image is not None:
            self._image.setParent(None)
            self._image.deleteLater()
            self._image = None
        self._home = []
        self._texts = []
        self._pan_axes = None
        self._dragging_from = None

    # ── fitting ──────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._message.setGeometry(self.rect())
        self._fit()

    def _fit(self) -> None:
        width, height = self.width(), self.height()
        self._ring.setGeometry(self.rect())
        if self._image is not None and self._pixmap is not None:
            self._image.setGeometry(self.rect())
            if not self._pixmap.isNull():
                self._image.setPixmap(self._pixmap.scaled(
                    self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            return
        if self._canvas is None or width < 2 or height < 2:
            return
        x0, y0, x1, y1 = self._crop
        crop_w, crop_h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        fitted = min(width / crop_w, height / crop_h)     # widget px per inch
        full_w, full_h = self._size_in
        limit = MAX_CANVAS_PX / (max(full_w, full_h) * fitted
                                 * self._canvas.device_pixel_ratio)
        self._zoom = float(min(max(self._zoom, 1.0), max(limit, 1.0)))
        scale = fitted * self._zoom
        self._size_text(scale)
        # The canvas derives its size in inches from its pixels and the dpi, so
        # setting the dpi first is what keeps the inches — and with them the
        # proportions of everything drawn — as the pipeline had them.
        self._figure._original_dpi = scale
        self._figure._set_dpi(scale * self._canvas.device_pixel_ratio, forward=False)
        if self._zoom <= 1.0 or self._origin is None:
            left = (width - crop_w * scale) / 2 - x0 * scale
            top = (height - crop_h * scale) / 2 - (full_h - y1) * scale
            self._origin = None
        else:
            left, top = self._origin
        self._canvas.setGeometry(round(left), round(top),
                                 max(round(full_w * scale), 1),
                                 max(round(full_h * scale), 1))

    # ── zoom and pan ─────────────────────────────────────────────────────────

    def reset_view(self) -> None:
        self._zoom, self._origin = 1.0, None
        self._fit()
        for ax, xlim, ylim in self._home:
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
        if self._canvas is not None:
            self._canvas.draw_idle()

    @staticmethod
    def _is_picture(ax) -> bool:
        """Whether *ax* has no axes to speak of — a network plot, a diagram.

        Such a plot has its legend and labels inside the drawing, so zooming
        its data range would slide them out of view and leave the text as it
        was. It is magnified whole instead, like a page. A plot with real axes
        zooms its range, and its ticks follow.
        """
        return ax is None or not ax.axison

    def _magnify(self, factor: float, about: QPointF) -> None:
        before = self._zoom
        left, top = self._canvas.x(), self._canvas.y()
        self._zoom = max(before * factor, 1.0)
        self._origin = (about.x() - (about.x() - left) * self._zoom / before,
                        about.y() - (about.y() - top) * self._zoom / before)
        self._fit()
        if self._zoom != before:
            # _fit may have capped the zoom; place for the zoom actually used.
            self._origin = (about.x() - (about.x() - left) * self._zoom / before,
                            about.y() - (about.y() - top) * self._zoom / before)
            self._fit()
        self._ring.mark(None)

    def _on_scroll(self, event) -> None:
        ax = event.inaxes
        if self._is_picture(ax):
            self._magnify(ZOOM_STEP if event.button == "up" else 1 / ZOOM_STEP,
                          self._to_widget((event.x, event.y)))
            return
        if event.xdata is None or not ax.can_zoom():
            return
        factor = 1 / ZOOM_STEP if event.button == "up" else ZOOM_STEP
        # Zoom about the cursor, in display space so log axes behave.
        to_data = ax.transData.inverted()
        (dx0, dy0), (dx1, dy1) = ax.transData.transform(
            np.column_stack([ax.get_xlim(), ax.get_ylim()]))
        cx, cy = event.x, event.y
        corners = np.array([[cx + (dx0 - cx) * factor, cy + (dy0 - cy) * factor],
                            [cx + (dx1 - cx) * factor, cy + (dy1 - cy) * factor]])
        (nx0, ny0), (nx1, ny1) = to_data.transform(corners)
        ax.set_xlim(nx0, nx1)
        ax.set_ylim(ny0, ny1)
        self._ring.mark(None)
        self._canvas.draw_idle()

    def _on_press(self, event) -> None:
        if event.dblclick:
            self.reset_view()
            return
        if event.button != 1:
            return
        self._pressed_at = (event.x, event.y)
        if self._is_picture(event.inaxes):
            if self._zoom > 1.0:
                self._dragging_from = (QCursor.pos(), self._canvas.x(), self._canvas.y())
            return
        if event.inaxes.can_pan():
            self._pan_axes = event.inaxes
            self._pan_axes.start_pan(event.x, event.y, 1)

    def _on_release(self, event) -> None:
        self._dragging_from = None
        if self._pan_axes is not None:
            self._pan_axes.end_pan()
            self._pan_axes = None
        pressed, self._pressed_at = self._pressed_at, None
        if pressed is None:
            return
        if abs(event.x - pressed[0]) + abs(event.y - pressed[1]) < 4:
            found = self._mark_under(event)
            if found is not None:
                self.picked.emit(found[0].replace("\n", " · "))

    def _on_motion(self, event) -> None:
        if self._dragging_from is not None:
            # In screen coordinates: the canvas moves under the cursor, so its
            # own event positions cannot measure the drag.
            start, left, top = self._dragging_from
            moved = QCursor.pos() - start
            self._origin = (left + moved.x(), top + moved.y())
            self._canvas.move(round(self._origin[0]), round(self._origin[1]))
            self._ring.mark(None)
            return
        if self._pan_axes is not None:
            self._pan_axes.drag_pan(1, None, event.x, event.y)
            self._ring.mark(None)
            self._canvas.draw_idle()
            return
        self._point_at(event)

    # ── what is under the cursor ─────────────────────────────────────────────

    def _point_at(self, event) -> None:
        found = self._mark_under(event) if event is not None else None
        if found is None:
            self._ring.mark(None)
            QToolTip.hideText()
            self.hovered.emit("")
            return
        text, centre, radius = found
        if centre is not None:
            self._ring.mark(self._to_widget(centre), radius)
        else:
            self._ring.mark(None)
        QToolTip.showText(QCursor.pos(), text, self)
        self.hovered.emit(text.replace("\n", " · "))

    def _to_widget(self, display_xy) -> QPointF:
        """Matplotlib display pixels (origin bottom-left) to this widget's."""
        ratio = self._canvas.device_pixel_ratio
        x = display_xy[0] / ratio + self._canvas.x()
        y = self._canvas.height() - display_xy[1] / ratio + self._canvas.y()
        return QPointF(x, y)

    def _mark_under(self, event):
        """``(text, display centre or None, ring radius in widget px)`` or ``None``."""
        ax = event.inaxes
        if ax is None:
            return None
        from meanap.pipeline import hover

        ratio = self._canvas.device_pixel_ratio
        cursor = np.array([event.x, event.y], dtype=float)
        reach = HOVER_PIXELS * ratio

        # 1. Marks a plotter described: nodes that know which electrode they are.
        best = None
        for group in hover.points(ax):
            shown = ax.transData.transform(group.xy)
            distance = np.hypot(*(shown - cursor).T)
            if group.radius is not None:
                edge = ax.transData.transform(
                    group.xy + np.column_stack([group.radius, np.zeros(len(group.xy))]))
                size = np.abs(edge[:, 0] - shown[:, 0])
            else:
                size = np.zeros(len(shown))
            inside = distance - np.maximum(size, reach)
            i = int(np.argmin(inside))
            if inside[i] <= 0 and (best is None or distance[i] < best[0]):
                name = (f"{group.noun.capitalize()} {group.names[i]}"
                        if group.names else group.noun.capitalize())
                best = (distance[i], f"{name}\n{group.text[i]}", shown[i],
                        max(size[i], 5 * ratio) / ratio + 3)
        if best is not None:
            return best[1], best[2], best[3]

        # 2. Any scatter point or line vertex: its coordinates, named by the axes.
        from matplotlib.collections import PathCollection

        candidates = []
        for artist in ax.collections:
            if isinstance(artist, PathCollection) and artist.get_visible():
                offsets = np.asarray(artist.get_offsets(), dtype=float)
                if offsets.size:
                    candidates.append((offsets, artist.get_offset_transform()))
        for line in ax.lines:
            if line.get_visible():
                xy = np.asarray(line.get_xydata(), dtype=float)
                if 0 < len(xy) <= 20000:
                    candidates.append((xy, line.get_transform()))
        nearest = None
        for xy, transform in candidates:
            ok = np.isfinite(xy).all(axis=1)
            if not ok.any():
                continue
            try:
                shown = transform.transform(xy[ok])
            except Exception:
                continue
            distance = np.hypot(*(shown - cursor).T)
            i = int(np.argmin(distance))
            if distance[i] <= reach and (nearest is None or distance[i] < nearest[0]):
                nearest = (distance[i], xy[ok][i], shown[i])
        if nearest is not None:
            _, (x, y), shown = nearest
            return (f"{ax.get_xlabel() or 'x'}: {ax.format_xdata(x).strip()}\n"
                    f"{ax.get_ylabel() or 'y'}: {ax.format_ydata(y).strip()}",
                    shown, 7.0)

        # 3. A heat map: the value of the cell under the cursor.
        for artist in list(ax.images) + [c for c in ax.collections
                                         if hasattr(c, "get_cursor_data")]:
            if not artist.get_visible():
                continue
            try:
                value = artist.get_cursor_data(event)
            except Exception:
                continue
            if value is None or np.ma.is_masked(value) or np.ndim(value) != 0:
                continue
            return (f"value: {float(value):.4g}\n"
                    f"x: {ax.format_xdata(event.xdata).strip()}, "
                    f"y: {ax.format_ydata(event.ydata).strip()}", None, 0.0)
        return None


# ── styling controls ──────────────────────────────────────────────────────────


class StylePanel(QWidget):
    """The Network Viewer controls, built from the viewer's control schema."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._widgets: dict[str, QWidget] = {}
        self._defaults: dict[str, object] = {}

    def set_schema(self, schema: list[dict]) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._widgets.clear()
        self._defaults.clear()
        for control in schema:
            key, default = control["key"], control["default"]
            if control["kind"] == "select":
                widget = QComboBox()
                widget.addItems([str(o) for o in control["options"]])
                widget.setCurrentText(str(default))
                widget.currentTextChanged.connect(lambda _t: self.changed.emit())
            elif control["kind"] == "number":
                whole = isinstance(default, int) and not isinstance(default, bool)
                widget = QSpinBox() if whole else QDoubleSpinBox()
                low = control["min"] if control["min"] is not None else 0
                high = control["max"] if control["max"] is not None else 1e6
                if whole:
                    widget.setRange(int(low), int(high))
                    widget.setSingleStep(int(control["step"] or 1))
                    widget.setValue(int(default))
                else:
                    step = float(control["step"] or 0.1)
                    widget.setDecimals(max(2, len(f"{step:.6f}".rstrip("0").split(".")[1])))
                    widget.setRange(float(low), float(high))
                    widget.setSingleStep(step)
                    widget.setValue(float(default))
                widget.setKeyboardTracking(False)
                widget.valueChanged.connect(lambda _v: self.changed.emit())
            else:
                continue                 # colour lists: not in this prototype
            widget.setToolTip(control.get("help") or "")
            label = QLabel(control["label"])
            label.setToolTip(control.get("help") or "")
            self._form.addRow(label, widget)
            self._widgets[key] = widget
            self._defaults[key] = default
        reset = QPushButton("Reset to the run's styling")
        reset.clicked.connect(self.reset)
        self._form.addRow(reset)

    def reset(self) -> None:
        for key, widget in self._widgets.items():
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(str(self._defaults[key]))
            else:
                widget.setValue(self._defaults[key])
            widget.blockSignals(False)
        self.changed.emit()

    def query(self) -> dict[str, list[str]]:
        """The controls as the query string the web page would send."""
        out = {}
        for key, widget in self._widgets.items():
            value = (widget.currentText() if isinstance(widget, QComboBox)
                     else widget.value())
            out[key] = [str(value)]
        return out


# ── drawing off the GUI thread ────────────────────────────────────────────────


class _Signals(QObject):
    done = pyqtSignal(int, object)      # generation, Live
    failed = pyqtSignal(int, str)


class _Draw(QRunnable):
    def __init__(self, generation: int, service, request: dict, signals: _Signals):
        super().__init__()
        self._generation, self._service = generation, service
        self._request, self._signals = request, signals

    def run(self) -> None:
        try:
            live = live_figure(self._service, **self._request)
        except Exception as e:           # shown to the user, not raised in a pool
            self._signals.failed.emit(self._generation, str(e))
            return
        self._signals.done.emit(self._generation, live)


class _DrawMany(QRunnable):
    """The same figure for several recordings: ``[(title, Live or message, current)]``.

    A recording that cannot draw it (no such lag, no such check) gets the
    reason in its place rather than failing the rest.
    """

    def __init__(self, generation: int, service, cells: list[tuple[str, dict, bool]],
                 signals: _Signals):
        super().__init__()
        self._generation, self._service = generation, service
        self._cells, self._signals = cells, signals

    def run(self) -> None:
        drawn = []
        for title, request, current in self._cells:
            try:
                drawn.append((title, live_figure(self._service, **request), current))
            except Exception as e:       # one recording's gap, not the montage's
                drawn.append((title, str(e) or "Not available.", current))
        self._signals.done.emit(self._generation, drawn)


class _PreviewSignals(QObject):
    done = pyqtSignal(object, object)       # key, QImage
    failed = pyqtSignal(object, str)


class _Preview(QRunnable):
    """One recording's figure as a small picture, for the hover card."""

    def __init__(self, key: tuple, service, request: dict, width: int,
                 signals: _PreviewSignals):
        super().__init__()
        self._key, self._service, self._request = key, service, request
        self._width, self._signals = width, signals

    def run(self) -> None:
        from meanap.native import output
        from meanap.native.output import NativeFigure

        try:
            live = live_figure(self._service, **self._request)
            if isinstance(live.figure, NativeFigure):
                painter = live.figure.painter
                image = output.render_image(painter, 2 * self._width / painter.size[0])
            else:
                from meanap.gui.div_montage import _picture

                image = _picture(live)
                if hasattr(live.figure, "clear"):
                    live.figure.clear()
            if image is None:
                raise ValueError("Nothing to preview.")
        except Exception as e:           # shown on the card, not raised in a pool
            self._signals.failed.emit(self._key, str(e) or "Could not draw this.")
            return
        self._signals.done.emit(self._key, image)


#: The headings stim figures fold under, by the start of their name.
_STIM_HEADINGS = (
    ("9_", "Responses"), ("10_", "Responses"), ("stimPattern_", "Responses"),
    ("spikeLatency_", "Responses"), ("12_", "Shuffle test"),
    ("Individual_PSTH", "Single electrodes"),
    ("13_", "Stimulus networks"), ("14_", "Stimulus networks"), ("15_", "Stimulus networks"),
    ("16_", "Stimulus networks"),
)


def _stim_heading(name: str) -> str:
    return next((heading for start, heading in _STIM_HEADINGS if name.startswith(start)),
                "Other")


# ── the viewer ────────────────────────────────────────────────────────────────

_REQUEST_ROLE = Qt.ItemDataRole.UserRole
_VARIANTS_ROLE = Qt.ItemDataRole.UserRole + 1
#: A heading's own name; its text also carries the open/closed mark.
_NAME_ROLE = Qt.ItemDataRole.UserRole + 2
#: A recording list item's index into the manifest's recordings.
_RECORDING_ROLE = Qt.ItemDataRole.UserRole + 3
_OPEN, _SHUT = "▾  ", "▸  "


def _cultures(recordings: list[dict]) -> dict[int, list[int]]:
    """For each recording that shares its culture with recordings at other
    DIVs, all of them (itself included), youngest first.

    The culture is the name with its DIV and date tokens dropped — the same
    rule the statistics use for repeated measures
    (:func:`meanap.stats.dataset.derive_culture_ids`), so the viewer and the
    statistics agree on which recordings are one culture. A culture recorded
    at a single DIV is left out: there is nothing to compare across.
    """
    import re

    import pandas as pd

    from meanap.stats.dataset import derive_culture_ids

    if not recordings:
        return {}
    # A DIV token with a note after it (``..._DIV16 David Oluigbo``, as folders
    # exported with their owner's name are) is still a DIV token.
    names = [re.sub(r"(?i)(_DIV[_-]?\d+\.?\d*)\s.*$", r"\1", r["name"]) for r in recordings]
    ids = derive_culture_ids(pd.Series(names)).tolist()
    members: dict[str, list[int]] = {}
    for index, culture in enumerate(ids):
        members.setdefault(culture, []).append(index)
    out = {}
    for group in members.values():
        divs = {recordings[i].get("div") for i in group}
        if len(group) > 1 and len(divs) > 1:
            group = sorted(group, key=lambda i: (
                float(recordings[i]["div"]) if recordings[i].get("div") is not None
                else float("inf"), recordings[i]["name"]))
            for index in group:
                out[index] = group
    return out

_VARIANT_LABELS = {"plain": "This recording's scale", "scaled": "Whole batch's scale",
                   "combined": "Both, side by side"}

#: The two ways of looking at a run, and the page for tracked cells.
RECORDING, GROUP, TRACKING = "recording", "group", "tracking"

_INK, _MUTED, _LINE, _ACCENT = "#111827", "#6b7280", "#e5e7eb", "#4f8ef7"
#: The simple view's look: a pale ground, white rounded cards, one accent.
_QSS = f"""
#resultsViewer, #resultsPage {{ background: #f7f8fa; }}
#resultsViewer QLabel {{ color: {_INK}; }}
#card {{ background: #ffffff; border: 1px solid {_LINE}; border-radius: 12px; }}
#resultsViewer QLabel#cardTitle {{
    color: {_MUTED}; font-size: 11px; font-weight: 600; padding: 2px 4px;
}}
#resultsViewer QLabel#muted {{ color: {_MUTED}; font-size: 12px; }}
#resultsViewer QLabel#selection {{ color: {_INK}; font-size: 12px; font-weight: 600; }}
#scopeBar {{ background: #eceef2; border-radius: 10px; }}
#scopeButton {{
    border: 1px solid transparent; background: transparent; color: {_MUTED};
    font-size: 13px; font-weight: 600; padding: 6px 16px; border-radius: 8px;
}}
#scopeButton:hover {{ color: {_INK}; }}
#scopeButton:checked {{ background: #ffffff; color: {_INK}; border: 1px solid {_LINE}; }}
#resultsViewer QListWidget, #resultsViewer QTreeWidget {{
    border: none; background: transparent; outline: 0; font-size: 13px; color: {_INK};
}}
#resultsViewer QListWidget::item, #resultsViewer QTreeWidget::item {{
    padding: 5px 8px; border-radius: 7px; color: {_INK};
}}
#resultsViewer QListWidget::item:hover, #resultsViewer QTreeWidget::item:hover {{
    background: #f1f4f9;
}}
#resultsViewer QListWidget::item:selected, #resultsViewer QTreeWidget::item:selected {{
    background: #e8f0fe; color: #1d4ed8;
}}
#resultsViewer QTreeWidget {{ show-decoration-selected: 0; }}
#resultsViewer QTreeWidget::branch, #resultsViewer QTreeWidget::branch:selected {{
    background: transparent; border-image: none; image: none;
}}
#resultsViewer QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
#resultsViewer QScrollBar::handle:vertical {{
    background: #d5d9e0; border-radius: 3px; min-height: 28px;
}}
#resultsViewer QScrollBar::handle:vertical:hover {{ background: #b9c0cb; }}
#resultsViewer QScrollBar::add-line:vertical, #resultsViewer QScrollBar::sub-line:vertical {{
    height: 0px;
}}
#resultsViewer QScrollBar::add-page:vertical, #resultsViewer QScrollBar::sub-page:vertical {{
    background: transparent;
}}
#resultsViewer QComboBox::drop-down {{ border: none; width: 20px; }}
#resultsViewer QLineEdit {{
    min-height: 26px; border: 1px solid {_LINE}; border-radius: 8px;
    padding: 0px 8px; background: #ffffff; color: {_INK};
}}
#resultsViewer QLineEdit:focus {{ border: 1px solid #c7d7f8; }}
#primary {{
    color: #ffffff; background: {_ACCENT}; border: none; border-radius: 8px;
    padding: 6px 14px; font-weight: 600;
}}
#primary:hover {{ background: #3a7de0; }}
#ghost {{
    color: #374151; background: #ffffff; border: 1px solid {_LINE};
    border-radius: 8px; padding: 6px 12px;
}}
#ghost:hover {{ border: 1px solid #c7d7f8; }}
#ghost:checked {{ background: #e8f0fe; color: #1d4ed8; border: 1px solid #c7d7f8; }}
#resultsViewer QComboBox {{
    min-height: 28px; border: 1px solid {_LINE}; border-radius: 8px;
    padding: 0px 8px; background: #ffffff; color: {_INK};
}}
#resultsViewer QComboBox:disabled {{ color: #9ca3af; background: #f3f4f6; }}
#resultsViewer QComboBox QAbstractItemView {{
    background: #ffffff; color: {_INK};
    selection-background-color: #e8f0fe; selection-color: #1d4ed8;
}}
#resultsViewer QTableWidget {{
    border: none; background: #ffffff; font-size: 12px; color: {_INK};
    selection-background-color: #e8f0fe; selection-color: #1d4ed8; outline: 0;
}}
#resultsViewer QTableWidget::item {{ padding: 3px 6px; border-bottom: 1px solid #f1f3f6; }}
#resultsViewer QHeaderView::section {{
    background: #ffffff; color: {_MUTED}; border: none;
    border-bottom: 1px solid {_LINE}; padding: 5px 6px; font-size: 11px; font-weight: 600;
}}
#resultsViewer QCheckBox {{ color: {_INK}; }}
#resultsViewer QSplitter::handle {{ background: transparent; }}
#resultsViewer QScrollArea {{ border: none; background: transparent; }}
"""


def _card(*, margins: int = 12) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    box = QVBoxLayout(card)
    box.setContentsMargins(margins, margins, margins, margins)
    box.setSpacing(8)
    return card, box


def _card_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("cardTitle")
    return label


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    return label


class ResultsViewer(QWidget):
    """A run's figures, drawn live: one recording at a time, or across them."""

    HINT = "Scroll to zoom, drag to move, point at a mark to read it."

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsViewer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(_QSS)
        self._service = None
        self._manifest: dict = {}
        self._scope = RECORDING
        self._generation = 0
        self._drawing = False
        self._queued = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)      # one figure at a time; newest wins
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_drawn)
        self._signals.failed.connect(self._on_failed)
        self._restyle = QTimer(self)
        self._restyle.setSingleShot(True)
        self._restyle.setInterval(RESTYLE_DELAY_MS)
        self._restyle.timeout.connect(self._draw)
        self._drew_in = 0.0
        self._native_key = None
        self._styleable = False
        self._tracking_listed = False
        #: What was open in each scope, to come back to.
        self._remembered: dict[str, tuple] = {}
        self._tree_scope = RECORDING

        # ── which view of the run ────────────────────────────────────────────
        self._scope_buttons: dict[str, QPushButton] = {}
        scope_bar = QFrame()
        scope_bar.setObjectName("scopeBar")
        scope_row = QHBoxLayout(scope_bar)
        scope_row.setContentsMargins(3, 3, 3, 3)
        scope_row.setSpacing(2)
        group = QButtonGroup(self)
        for key, text, tip in (
            (RECORDING, "One recording", "Figures of a single recording."),
            (GROUP, "Across recordings",
             "Figures that compare recordings: by group, by age, across lags, statistics."),
            (TRACKING, "Cell tracking", "Cells followed across days."),
        ):
            button = QPushButton(text)
            button.setObjectName("scopeButton")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _on, k=key: self.set_scope(k))
            group.addButton(button)
            scope_row.addWidget(button)
            self._scope_buttons[key] = button
        self._scope_buttons[RECORDING].setChecked(True)
        self.run_name = _muted()
        header = QHBoxLayout()
        header.addWidget(scope_bar)
        header.addStretch(1)
        header.addWidget(self.run_name)

        # ── left: what to look at ────────────────────────────────────────────
        self.recordings = QListWidget()
        self.recordings.currentItemChanged.connect(lambda *_: self._on_recording(0))
        # Which recordings are listed, and how: by name, group (genotype) and
        # DIV, optionally under headings.
        self.rec_search = QLineEdit()
        self.rec_search.setPlaceholderText("Filter by name…")
        self.rec_search.setClearButtonEnabled(True)
        self.rec_search.textChanged.connect(lambda _t: self._fill_recordings())
        self.rec_group = QComboBox()
        self.rec_group.setToolTip("Show one group (genotype, condition) only.")
        self.rec_div = QComboBox()
        self.rec_div.setToolTip("Show one age only.")
        self.rec_by = QComboBox()
        self.rec_by.setToolTip("List the recordings under a heading per group, per DIV, or both.")
        for key, text in ((None, "No headings"), ("group", "Under group"),
                          ("div", "Under DIV"), ("group_div", "Under group, DIV")):
            self.rec_by.addItem(text, key)
        for combo in (self.rec_group, self.rec_div, self.rec_by):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(4)
            combo.currentIndexChanged.connect(lambda _i: self._fill_recordings())
        self.rec_by.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        filter_row.addWidget(self.rec_search, 1)
        filter_row.addWidget(self.rec_by)
        choose_row = QHBoxLayout()
        choose_row.setSpacing(4)
        for combo in (self.rec_group, self.rec_div):
            choose_row.addWidget(combo, 1)
        self.rec_count = _muted()
        rec_title = QHBoxLayout()
        rec_title.addWidget(_card_title("Recording"))
        rec_title.addStretch(1)
        rec_title.addWidget(self.rec_count)
        self._recordings_card, rec_box = _card()
        rec_box.addLayout(rec_title)
        rec_box.addLayout(filter_row)
        rec_box.addLayout(choose_row)
        rec_box.addWidget(self.recordings, 1)
        # Long names are shortened in the middle, where they differ least.
        self.recordings.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.recordings.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recordings.setWordWrap(False)
        #: Each recording's culture: the manifest indices of the recordings of
        #: it (itself included), youngest first. See ``derive_culture_ids``.
        self._siblings: dict[int, list[int]] = {}

        self.figures = QTreeWidget()
        self.figures.setHeaderHidden(True)
        self.figures.setIndentation(14)
        self.figures.setAnimated(True)
        self.figures.setExpandsOnDoubleClick(False)
        self.figures.currentItemChanged.connect(lambda *_: self._on_figure())
        self.figures.itemClicked.connect(self._on_tree_click)
        # The style sheet takes over the tree's own disclosure arrows, so each
        # heading carries its mark in its text.
        self.figures.setRootIsDecorated(False)
        self.figures.itemExpanded.connect(lambda item: self._mark(item, True))
        self.figures.itemCollapsed.connect(lambda item: self._mark(item, False))
        self.lag = QComboBox()
        self.lag.currentIndexChanged.connect(lambda _i: self._fill_figures())
        self._lag_label = _muted("Lag")
        lag_row = QHBoxLayout()
        lag_row.addWidget(_card_title("Figures"))
        lag_row.addStretch(1)
        lag_row.addWidget(self._lag_label)
        lag_row.addWidget(self.lag)
        fig_card, fig_box = _card()
        fig_box.addLayout(lag_row)
        fig_box.addWidget(self.figures, 1)

        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self._recordings_card)
        left.addWidget(fig_card)
        left.setStretchFactor(1, 1)
        left.setSizes([380, 480])
        left.setMinimumWidth(270)

        # ── middle: the figure ───────────────────────────────────────────────
        self.view = FigureView()
        self.view.hovered.connect(self._on_hover)
        self.view.picked.connect(self._on_picked)
        self.view.painted.connect(self._on_painted)
        from meanap.gui.figure_canvas import FigureCanvas
        from meanap.gui.network_canvas import NetworkCanvas

        # The network plot has controls of its own; every other Qt-drawn
        # figure is shown by the one generic canvas.
        self.native = NetworkCanvas()
        self.canvas = FigureCanvas()
        from meanap.gui.div_montage import DivMontage

        self.montage = DivMontage()
        for canvas in (self.native, self.canvas, self.montage):
            canvas.hovered.connect(self._on_hover)
            canvas.picked.connect(self._on_picked)
        self.canvas.recording.connect(self._on_point_recording)
        self._stack = QStackedWidget()
        for widget in (self.view, self.native, self.canvas, self.montage):
            self._stack.addWidget(widget)

        # The same figure at every DIV this culture was recorded at.
        self.across_divs = QPushButton("Across DIVs")
        self.across_divs.setObjectName("ghost")
        self.across_divs.setCheckable(True)
        self.across_divs.toggled.connect(lambda _on: self._draw())
        self.across_divs.hide()

        self.variant = QComboBox()
        self.variant.currentIndexChanged.connect(lambda _i: self._draw())
        self.variant.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._variant_label = _muted("Scale")
        self.split = QComboBox()
        self.split.currentIndexChanged.connect(lambda _i: self._draw())
        self.split.setToolTip("Whether the panels of a comparison are groups or ages.")
        self._split_label = _muted("Panels")
        self.figure_title = QLabel("")
        self.figure_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.status = _muted()
        # The timing is a note; it gives way before the controls do.
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Styling restyles spatial network plots and nothing else, and is not
        # what most visits are for: offered only on those plots, and closed
        # until asked for.
        self.style_button = QPushButton("Styling")
        self.style_button.setObjectName("ghost")
        self.style_button.setCheckable(True)
        self.style_button.setToolTip(
            "Node sizes, edge thresholds, layout and colour map for this network plot.")
        self.style_button.toggled.connect(lambda _on: self._place_styling())
        self.style_button.hide()
        reset = QPushButton("Reset view")
        reset.setObjectName("ghost")
        reset.setToolTip("Undo zooming and panning. Double-clicking the figure does the same.")
        reset.clicked.connect(lambda: self._stack.currentWidget().reset_view())
        save = QPushButton("Save figure…")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.figure_title)
        bar.addWidget(self.status, 1)
        for widget in (self._variant_label, self.variant, self._split_label, self.split,
                       self.across_divs, self.style_button, reset, save):
            bar.addWidget(widget)
        self.readout = _muted(self.HINT)
        # While something is selected its description is the longer text; the
        # hint gives way to it rather than the other way round.
        self.readout.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.selection = QLabel("")
        self.selection.setObjectName("selection")
        foot = QHBoxLayout()
        foot.addWidget(self.readout, 1)
        foot.addWidget(self.selection)
        middle, middle_box = _card()
        middle_box.addLayout(bar)
        middle_box.addWidget(self._stack, 1)
        middle_box.addLayout(foot)

        # ── right: styling, when asked for ───────────────────────────────────
        self.style_panel = StylePanel()
        self.style_panel.changed.connect(self._restyle.start)
        self._style_scroll = QScrollArea()
        self._style_scroll.setWidgetResizable(True)
        self._style_scroll.setWidget(self.style_panel)
        self._right, right_box = _card()
        right_box.addWidget(_card_title("Network styling"))
        right_box.addWidget(self._style_scroll, 1)
        self._right.setMinimumWidth(280)
        self._right.hide()

        splitter = self._splitter = QSplitter()
        splitter.setHandleWidth(10)
        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(self._right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 760, 290])

        from meanap.gui.tracking_view import TrackingView

        self.tracking = TrackingView()
        self.tracking.hovered.connect(self._on_hover)
        self._pages = QStackedWidget()
        self._pages.addWidget(splitter)
        self._pages.addWidget(self.tracking)

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)
        box.addLayout(header)
        box.addWidget(self._pages, 1)

        # ── the card previewing a recording pointed at across recordings ─────
        from meanap.gui.recording_preview import PREVIEW_W, RecordingPreview

        self._preview_w = PREVIEW_W
        self.preview = RecordingPreview(self)
        self.preview.opened.connect(self._open_preview)
        self.preview.entered.connect(lambda: self._preview_hide.stop())
        self.preview.left.connect(lambda: self._preview_hide.start())
        self._preview_hide = QTimer(self)
        self._preview_hide.setSingleShot(True)
        self._preview_hide.setInterval(PREVIEW_GRACE_MS)
        self._preview_hide.timeout.connect(self._hide_preview_if_idle)
        self._preview_signals = _PreviewSignals(self)
        self._preview_signals.done.connect(self._on_preview)
        self._preview_signals.failed.connect(self._on_preview_failed)
        #: Pictures already drawn, by (recording, kind, name, lag).
        self._preview_cache: dict[tuple, object] = {}
        self._preview_busy = False
        self._preview_wanted: tuple | None = None
        #: The recording pointed at, and the one pinned, on the figure shown.
        self._hover_recording: str | None = None
        self._pinned_recording: str | None = None

    # ── the run ──────────────────────────────────────────────────────────────

    def load_run(self, source: str | Path) -> None:
        """Open a bundle or results folder. Raises ``ValueError`` if unreadable."""
        from meanap.viewer.server import ViewerService

        service = ViewerService(source)
        self.close_run()
        self._service = service
        self._manifest = service.manifest()
        self._remembered = {}
        self._tracking_listed = False
        self.run_name.setText(Path(str(source)).name)
        self.style_panel.blockSignals(True)
        self.style_panel.set_schema(self._manifest["controls"])
        self.style_panel.blockSignals(False)
        self._scope_buttons[GROUP].setVisible(self._has_group_figures())
        self._scope_buttons[TRACKING].setVisible(bool(service.tracking().get("available")))
        recs = self._manifest["recordings"]
        self._siblings = _cultures(recs)
        self._preview_cache = {}
        for combo, values, every in (
                (self.rec_group, sorted({str(r.get("group") or "") for r in recs} - {""}),
                 "All groups"),
                (self.rec_div, [f"{d:g}" for d in sorted({float(r["div"]) for r in recs
                                                         if r.get("div") is not None})],
                 "All DIVs")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(every, None)
            for value in values:
                combo.addItem(value if combo is self.rec_group else f"DIV {value}", value)
            combo.setVisible(len(values) > 1)
            combo.blockSignals(False)
        self.rec_search.blockSignals(True)
        self.rec_search.clear()
        self.rec_search.blockSignals(False)
        self._scope = RECORDING
        self._scope_buttons[RECORDING].setChecked(True)
        self._pages.setCurrentIndex(0)
        self._recordings_card.show()
        self._fill_recordings(select=0)
        if not recs:
            self.view.show_message("This run has no recordings to show.")

    def close_run(self) -> None:
        self._generation += 1            # anything still drawing is now stale
        self._pool.waitForDone(5000)
        self._stack.setCurrentWidget(self.view)
        self.view.show_message("")
        self._native_key = None
        self._dismiss_preview()
        self.montage.clear()
        self.tracking.close_run()
        if self._service is not None:
            self._service.close()
            self._service = None

    def _has_group_figures(self) -> bool:
        m = self._manifest
        return bool(m.get("comparisons") or m.get("lag_series") or m.get("stats"))

    # ── one recording, across recordings, tracked cells ──────────────────────

    @property
    def scope(self) -> str:
        return self._scope

    def set_scope(self, scope: str) -> None:
        """Turn to one recording's figures, the cross-recording ones, or tracking."""
        if self._service is None or not self._scope_buttons[scope].isVisibleTo(self):
            scope = self._scope
        self._scope_buttons[scope].setChecked(True)
        if scope == self._scope:
            return
        self._remember()
        self._scope = scope
        self._dismiss_preview()
        self._place_across()
        if scope == TRACKING:
            self._pages.setCurrentWidget(self.tracking)
            # Listing the chains opens the first one, which is megabytes to
            # read: not until the page is asked for.
            if not self._tracking_listed:
                self._tracking_listed = True
                self.tracking.load(self._service)
            return
        self._pages.setCurrentIndex(0)
        self._recordings_card.setVisible(scope == RECORDING)
        self._fill_lags()
        self._fill_figures()

    def show_tracking(self) -> None:
        """Turn to the cell-tracking page, if this run has one."""
        self.set_scope(TRACKING)

    def _recording_index(self) -> int | None:
        item = self.recordings.currentItem()
        index = item.data(_RECORDING_ROLE) if item is not None else None
        return index if isinstance(index, int) else None

    def _recording(self) -> dict | None:
        index = self._recording_index()
        recs = self._manifest.get("recordings", [])
        return recs[index] if index is not None and 0 <= index < len(recs) else None

    def _on_recording(self, _row: int) -> None:
        if self._recording() is None:
            return
        self._fill_lags()
        self._fill_figures()

    @staticmethod
    def _div_text(rec: dict) -> str | None:
        return f"DIV {float(rec['div']):g}" if rec.get("div") is not None else None

    def _listed(self) -> list[int]:
        """The manifest indices the filters let through, in the order listed."""
        recs = self._manifest.get("recordings", [])
        text = self.rec_search.text().strip().lower()
        group, div = self.rec_group.currentData(), self.rec_div.currentData()
        keep = [i for i, rec in enumerate(recs)
                if (not text or text in rec["name"].lower())
                and (group is None or str(rec.get("group") or "") == group)
                and (div is None or (rec.get("div") is not None
                                     and f"{float(rec['div']):g}" == div))]
        by = self.rec_by.currentData()
        if by is None:
            return keep
        order = {g: k for k, g in enumerate(self._group_order())}

        def key(i):
            rec = recs[i]
            g = order.get(str(rec.get("group") or ""), len(order))
            d = float(rec["div"]) if rec.get("div") is not None else float("inf")
            return (g, d) if by in ("group", "group_div") else (d, g)
        return sorted(keep, key=key)

    def _group_order(self) -> list[str]:
        """Groups in the run's own order (its custom one, if it set one)."""
        recs = self._manifest.get("recordings", [])
        present = []
        for rec in recs:
            g = str(rec.get("group") or "")
            if g not in present:
                present.append(g)
        custom = []
        if self._service is not None:
            custom = [str(g) for g in (getattr(self._service.ctx.params,
                                               "custom_grp_order", None) or [])]
        return [g for g in custom if g in present] + sorted(g for g in present
                                                            if g not in custom)

    def _heading_of(self, rec: dict) -> str | None:
        by = self.rec_by.currentData()
        group = str(rec.get("group") or "") or "No group"
        div = self._div_text(rec) or "No DIV"
        return {None: None, "group": group, "div": div,
                "group_div": f"{group} · {div}"}[by]

    def _fill_recordings(self, select: int | None = None, *, notify: bool = True) -> None:
        """List the recordings the filters let through, keeping the one chosen.

        Choosing a different one redraws, unless *notify* is False.
        """
        recs = self._manifest.get("recordings", [])
        wanted = self._recording_index() if select is None else select
        listed = self._listed()
        self.recordings.blockSignals(True)
        self.recordings.clear()
        heading, chosen = None, None
        for index in listed:
            rec = recs[index]
            this = self._heading_of(rec)
            if this is not None and this != heading:
                heading = this
                head = QListWidgetItem(this)
                head.setFlags(Qt.ItemFlag.NoItemFlags)       # a heading, not a recording
                font = head.font()
                font.setBold(True)
                head.setFont(font)
                head.setForeground(QColor(_MUTED))
                self.recordings.addItem(head)
            detail = [v for v in (rec.get("group"), self._div_text(rec)) if v]
            others = [recs[j] for j in self._siblings.get(index, []) if j != index]
            if others:
                detail.append("also " + ", ".join(self._div_text(r) or "?" for r in others))
            item = QListWidgetItem(rec["name"] + ("\n" + " · ".join(map(str, detail))
                                                  if detail else ""))
            item.setData(_RECORDING_ROLE, index)
            if others:
                item.setToolTip(
                    "This culture was also recorded at "
                    + ", ".join(self._div_text(r) or "?" for r in others)
                    + ". Turn on “Across DIVs” to see a figure at every age at once.")
            self.recordings.addItem(item)
            if index == wanted:
                chosen = item
        self.recordings.blockSignals(False)
        self.rec_count.setText(f"{len(listed)} of {len(recs)}" if len(listed) != len(recs)
                               else f"{len(recs)}")
        if chosen is None:
            # The chosen recording is filtered out: the first one left instead.
            chosen = next((self.recordings.item(i) for i in range(self.recordings.count())
                           if self.recordings.item(i).data(_RECORDING_ROLE) is not None), None)
        if chosen is not None:
            changed = chosen.data(_RECORDING_ROLE) != wanted or select is not None
            self.recordings.blockSignals(not (changed and notify))
            self.recordings.setCurrentItem(chosen)
            self.recordings.blockSignals(False)
            self.recordings.scrollToItem(chosen)

    def select_recording(self, name: str, *, notify: bool = True) -> bool:
        """Choose the recording called *name*, clearing filters that hide it."""
        names = [r["name"] for r in self._manifest.get("recordings", [])]
        if name not in names:
            return False
        index = names.index(name)
        if index not in self._listed():
            for widget in (self.rec_search, self.rec_group, self.rec_div):
                widget.blockSignals(True)
            self.rec_search.clear()
            self.rec_group.setCurrentIndex(0)
            self.rec_div.setCurrentIndex(0)
            for widget in (self.rec_search, self.rec_group, self.rec_div):
                widget.blockSignals(False)
        self._fill_recordings(select=index, notify=notify)
        return True

    def _fill_lags(self) -> None:
        """The lags the current scope has figures for, keeping the one chosen."""
        if self._scope == RECORDING:
            rec = self._recording()
            lags = list(rec["lags"]) if rec else []
        else:
            lags = sorted({lag for family in self._manifest.get("comparisons", [])
                           for lag in family.get("lags", [])})
        wanted = self.lag.currentData()
        self.lag.blockSignals(True)
        self.lag.clear()
        for lag in lags:
            self.lag.addItem(f"{lag} ms", lag)
        if wanted in lags:
            self.lag.setCurrentIndex(lags.index(wanted))
        self.lag.blockSignals(False)
        for widget in (self.lag, self._lag_label):
            widget.setVisible(bool(lags))

    # ── the figure tree ──────────────────────────────────────────────────────

    def _branch(self, parent, text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [_SHUT + text])
        item.setData(0, _NAME_ROLE, text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)        # opens and closes; not a figure
        if isinstance(parent, QTreeWidget):
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        return item

    @staticmethod
    def _name(item: QTreeWidgetItem) -> str:
        return item.data(0, _NAME_ROLE) or item.text(0)

    def _mark(self, item: QTreeWidgetItem, opened: bool) -> None:
        name = item.data(0, _NAME_ROLE)
        if name:
            item.setText(0, (_OPEN if opened else _SHUT) + name)

    def _leaf(self, parent, text: str, request: dict, variants=None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, _REQUEST_ROLE, request)
        item.setData(0, _VARIANTS_ROLE, list(variants or ["plain"]))
        return item

    def _recording_tree(self) -> None:
        """The spike detection checks first — whether the spikes everything else
        is built on can be trusted — then activity, then network properties."""
        rec, lag = self._recording(), self.lag.currentData()
        if rec is None:
            return
        if rec.get("spike_checks"):
            branch = self._branch(self.figures, "Spike detection checks")
            for figure in rec["spike_checks"]:
                self._leaf(branch, figure["label"],
                           {"kind": "spike_check", "name": figure["name"]})
        if rec.get("sorting_checks"):
            branch = self._branch(self.figures, "Spike sorting checks")
            for figure in rec["sorting_checks"]:
                self._leaf(branch, figure["label"],
                           {"kind": "sorting_check", "name": figure["name"]})
        if rec.get("stim_checks"):
            branch = self._branch(self.figures, "Stimulus detection checks")
            for figure in rec["stim_checks"]:
                self._leaf(branch, figure["label"],
                           {"kind": "stim_check", "name": figure["name"]})
        if rec.get("activity"):
            branch = self._branch(self.figures, "Activity")
            for figure in rec["activity"]:
                self._leaf(branch, figure["label"], {"kind": "activity", "name": figure["name"]})
        network = rec["figures"].get(str(lag), []) if lag is not None else []
        if network:
            branch = self._branch(self.figures, "Network")
            groups: dict[str, QTreeWidgetItem] = {}
            for figure in network:
                parent, label = branch, figure["label"]
                # "Network — node degree" and its kin fold under one heading.
                for prefix, heading in (("Network — ", "Spatial network"),
                                        ("Circular — ", "Circular layout")):
                    if label.startswith(prefix):
                        if heading not in groups:
                            groups[heading] = self._branch(branch, heading)
                        parent = groups[heading]
                        label = label[len(prefix):]
                        label = label[:1].upper() + label[1:]
                self._leaf(parent, label, {"kind": "network", "name": figure["name"]},
                           figure.get("variants"))
        if lag is not None and lag in rec.get("edge_checks", []):
            # Only when the run kept the thresholding snapshots, at this lag.
            branch = next((self.figures.topLevelItem(i)
                           for i in range(self.figures.topLevelItemCount())
                           if self._name(self.figures.topLevelItem(i)) == "Network"), None) \
                or self._branch(self.figures, "Network")
            self._leaf(branch, "Edge threshold check",
                       {"kind": "edge_check", "name": "ProbThreshCheck"})
        if rec.get("stim"):
            # MEA-Stim: what the stimulus did, then the networks it evoked.
            branch = self._branch(self.figures, "Stimulation")
            groups: dict[str, QTreeWidgetItem] = {}
            for figure in rec["stim"]:
                heading = _stim_heading(figure["name"])
                if heading not in groups:
                    groups[heading] = self._branch(branch, heading)
                self._leaf(groups[heading], figure["label"],
                           {"kind": "stim", "name": figure["name"]})

    def _group_tree(self) -> None:
        """The same order across recordings: activity, network, then statistics."""
        m, lag = self._manifest, self.lag.currentData()
        families = list(m.get("comparisons", []))
        # Activity before network, whatever order the run lists them in.
        families.sort(key=lambda f: (0 if "activity" in f["key"] else
                                     1 if f["key"] == "network" else 2))
        for family in families:
            title = ("Activity" if "activity" in family["key"] else
                     "Network" if family["key"] == "network" else family["label"])
            branch = self._branch(self.figures, title)
            for level in family.get("levels", []):
                sub = self._branch(branch, level["label"])
                for metric in level.get("metrics", []):
                    self._leaf(sub, metric["label"], {
                        "kind": "comparison", "family": family["key"],
                        "level": level["key"], "metric": metric["name"],
                        "splits": family.get("splits", []), "lagged": bool(family.get("lags"))})
            if family["key"] == "network":
                for series in m.get("lag_series", []):
                    sub = self._branch(branch, series["label"])
                    for option in series.get("options", []):
                        self._leaf(sub, option["label"], {
                            "kind": "lag_series", "series": series["key"], "key": option["key"]})
        if not any(f["key"] == "network" for f in families):
            for series in m.get("lag_series", []):
                sub = self._branch(self.figures, series["label"])
                for option in series.get("options", []):
                    self._leaf(sub, option["label"], {
                        "kind": "lag_series", "series": series["key"], "key": option["key"]})
        stats = m.get("stats", [])
        if stats:
            entry = next((s for s in stats if lag is not None
                          and str(s["lag"]).startswith(f"{lag}ms")), stats[0])
            branch = self._branch(self.figures, "Statistics")
            for group in entry.get("groups", []):
                sub = self._branch(branch, group["label"])
                for figure in group.get("figures", []):
                    self._leaf(sub, figure["label"], {
                        "kind": "stats", "lag": entry["lag"], "key": figure["key"]})

    @staticmethod
    def _identity(request: dict | None) -> tuple | None:
        """What a figure is, apart from which recording or lag it is drawn for."""
        if not request:
            return None
        if "name" in request:
            return (request["kind"], str(request["name"]).split("ms")[-1])
        return tuple(str(request.get(k)) for k in ("kind", "family", "level", "metric",
                                                   "series", "key"))

    def _leaves(self) -> list[QTreeWidgetItem]:
        found, stack = [], [self.figures.topLevelItem(i)
                            for i in range(self.figures.topLevelItemCount())]
        while stack:
            item = stack.pop(0)
            if item.data(0, _REQUEST_ROLE):
                found.append(item)
            stack[0:0] = [item.child(i) for i in range(item.childCount())]
        return found

    def figure_labels(self) -> list[str]:
        """Every figure on offer, as "Branch / … / figure"."""
        labels = []
        for item in self._leaves():
            parts, at = [], item
            while at is not None:
                parts.insert(0, self._name(at))
                at = at.parent()
            labels.append(" / ".join(parts))
        return labels

    def select_figure(self, label: str) -> bool:
        """Open the figure whose path ends with *label*. ``False`` if there is none."""
        for item, path in zip(self._leaves(), self.figure_labels()):
            if path == label or path.endswith(" / " + label):
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.figures.setCurrentItem(item)
                self.figures.scrollToItem(item)
                return True
        return False

    def _remember(self) -> None:
        item = self.figures.currentItem()
        request = item.data(0, _REQUEST_ROLE) if item is not None else None
        # Filed under the scope the tree was built for, which during a change
        # of scope is not yet the scope being turned to.
        if request:
            self._remembered[self._tree_scope] = self._identity(request)

    def _fill_figures(self) -> None:
        if self._service is None or self._scope == TRACKING:
            return
        self._remember()
        keep = self._remembered.get(self._scope)
        # Which branches are open is the reader's arrangement: keep it.
        closed = ({self._name(item) for item in self._branches() if not item.isExpanded()}
                  if self._tree_scope == self._scope else set())
        self.figures.blockSignals(True)
        self.figures.clear()
        self._tree_scope = self._scope
        if self._scope == RECORDING:
            self._recording_tree()
        else:
            self._group_tree()
        first_open = True
        for item in self._branches():
            top = item.parent() is None
            # Top-level branches start open; inside them, only the first does,
            # so a long run of metrics is not all unrolled at once.
            item.setExpanded(self._name(item) not in closed
                             and (top or first_open or self._scope == RECORDING))
            if not top:
                first_open = False
        leaves = self._leaves()
        select = next((i for i in leaves if self._identity(i.data(0, _REQUEST_ROLE)) == keep),
                      leaves[0] if leaves else None)
        self.figures.blockSignals(False)
        for item in self._branches():           # opened while signals were held
            self._mark(item, item.isExpanded())
        if select is None:
            self._stack.setCurrentWidget(self.view)
            self.view.show_message("Nothing to draw here.")
            self.figure_title.setText("")
            return
        parent = select.parent()
        while parent is not None:
            parent.setExpanded(True)
            self._mark(parent, True)
            parent = parent.parent()
        self.figures.setCurrentItem(select)
        self.figures.scrollToItem(select, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._on_figure()

    def _branches(self) -> list[QTreeWidgetItem]:
        found, stack = [], [self.figures.topLevelItem(i)
                            for i in range(self.figures.topLevelItemCount())]
        while stack:
            item = stack.pop(0)
            if item.childCount():
                found.append(item)
                stack[0:0] = [item.child(i) for i in range(item.childCount())]
        return found

    def _on_tree_click(self, item: QTreeWidgetItem, _column: int) -> None:
        # A heading is not a figure: clicking anywhere on it folds or unfolds.
        if not item.data(0, _REQUEST_ROLE):
            item.setExpanded(not item.isExpanded())

    def _on_figure(self) -> None:
        item = self.figures.currentItem()
        request = item.data(0, _REQUEST_ROLE) if item is not None else None
        if not request:
            return
        self.figure_title.setText(item.text(0))
        variants = item.data(0, _VARIANTS_ROLE) or ["plain"]
        self._fill_combo(self.variant, [(v, _VARIANT_LABELS.get(v, v)) for v in variants])
        for widget in (self.variant, self._variant_label):
            widget.setVisible(len(variants) > 1)
        splits = [(s["key"], s["label"]) for s in request.get("splits", [])]
        self._fill_combo(self.split, splits)
        for widget in (self.split, self._split_label):
            widget.setVisible(len(splits) > 1)
        self._place_across()
        self._draw()

    @staticmethod
    def _fill_combo(combo: QComboBox, choices: list[tuple]) -> None:
        wanted = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for key, label in choices:
            combo.addItem(label, key)
        keys = [key for key, _ in choices]
        if wanted in keys:
            combo.setCurrentIndex(keys.index(wanted))
        combo.blockSignals(False)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _request(self) -> dict | None:
        item = self.figures.currentItem()
        chosen = item.data(0, _REQUEST_ROLE) if item is not None else None
        if self._service is None or not chosen:
            return None
        kind = chosen["kind"]
        if kind in ("network", "activity", "spike_check", "sorting_check", "edge_check", "stim",
                    "stim_check"):
            rec = self._recording()
            if rec is None:
                return None
            request = {"kind": kind, "recording": rec["name"], "name": chosen["name"]}
            if kind == "edge_check":
                request["lag"] = self.lag.currentData()
            if kind == "network":
                from meanap.viewer.controls import parse_overrides

                request["lag"] = self.lag.currentData()
                request["variant"] = self.variant.currentData() or "plain"
                request["overrides"] = parse_overrides(
                    self.style_panel.query(), self._service.run_style())
            return request
        if kind == "comparison":
            return {"kind": kind, "family": chosen["family"], "level": chosen["level"],
                    "metric": chosen["metric"],
                    "split": self.split.currentData() or "group",
                    "lag": self.lag.currentData() if chosen.get("lagged") else None}
        if kind == "lag_series":
            return {"kind": kind, "series": chosen["series"], "key": chosen["key"]}
        return {"kind": kind, "lag": chosen["lag"], "key": chosen["key"]}

    def _draw(self) -> None:
        """Draw what is selected. A request made while drawing waits its turn."""
        if self._drawing:
            self._queued = True
            return
        try:
            request = self._request()
        except ValueError as e:
            self.view.show_message(str(e))
            return
        if request is None:
            return
        self._generation += 1
        self._drawing = True
        self._dismiss_preview()
        if self._across():
            recs, index = self._manifest["recordings"], self._recording_index()
            cells = [(" · ".join(t for t in (self._div_text(recs[j]), recs[j]["name"]) if t),
                      {**request, "recording": recs[j]["name"]}, j == index)
                     for j in self._siblings[index]]
            self.status.setText(f"Drawing {len(cells)} recordings…")
            self._pool.start(_DrawMany(self._generation, self._service, cells, self._signals))
            return
        self.status.setText("Drawing…")
        self._pool.start(_Draw(self._generation, self._service, request, self._signals))

    def _across(self) -> bool:
        """Whether the figure is to be drawn at every DIV of this culture."""
        return (self._scope == RECORDING and self.across_divs.isChecked()
                and self._recording_index() in self._siblings)

    def _place_across(self) -> None:
        """Offer "Across DIVs" on a recording whose culture has others."""
        index = self._recording_index()
        others = self._siblings.get(index, []) if self._scope == RECORDING else []
        self.across_divs.setVisible(bool(others))
        if others:
            recs = self._manifest["recordings"]
            self.across_divs.setText(f"Across DIVs ({len(others)})")
            self.across_divs.setToolTip(
                "This culture was recorded at "
                + ", ".join(self._div_text(recs[j]) or "?" for j in others)
                + ": show this figure for each, side by side.")

    def _finish(self) -> None:
        self._drawing = False
        if self._queued:
            self._queued = False
            self._draw()

    def _on_drawn(self, generation: int, live) -> None:
        if isinstance(live, list):           # across DIVs: [(title, Live or message, current)]
            if generation == self._generation:
                self._drew_in = sum(got.seconds for _t, got, _c in live
                                    if isinstance(got, Live))
                self.selection.setText("")
                self._show_many(live)
            self._finish()
            return
        if generation == self._generation:
            self._drew_in = live.seconds
            self.selection.setText("")
            self._show(live)
        elif hasattr(live.figure, "clear"):
            live.figure.clear()
        self._finish()

    def _show_many(self, cells: list) -> None:
        import time

        item = self.figures.currentItem()
        request = item.data(0, _REQUEST_ROLE) if item is not None else {}
        self._styleable = (request or {}).get("kind") == "network"
        self._place_styling()
        self._native_key = None
        started = time.perf_counter()
        self.montage.link_nodes = self._manifest.get("mode") != "catnap"
        self.montage.show_cells(cells)
        self.view.show_message("")
        self._stack.setCurrentWidget(self.montage)
        self.montage.repaint()
        self._on_painted(time.perf_counter() - started)

    def _place_styling(self) -> None:
        """Offer the styling panel on network plots only; show it when asked."""
        self.style_button.setVisible(self._styleable)
        show = self._styleable and self.style_button.isChecked()
        if show and not self._right.isVisible():
            # A hidden splitter pane comes back at whatever is left over, which
            # is nothing; give it its width out of the figure's.
            left, middle, _ = self._splitter.sizes()
            self._right.show()
            self._splitter.setSizes([left, max(middle - 300, 300), 300])
        self._right.setVisible(show)
        try:
            changed = bool((self._request() or {}).get("overrides"))
        except ValueError:
            changed = True
        self.style_button.setText("Styling (changed)" if changed else "Styling")

    def _show(self, live: Live) -> None:
        """Put *live* on screen."""
        from meanap.native.output import NativeFigure
        from meanap.pipeline import hover

        # A figure the pipeline draws with Qt arrives as its scene and is shown
        # by the painter that writes its file. One matplotlib still draws
        # arrives as the figure, and is shown as that.
        if isinstance(live.figure, NativeFigure):
            import time

            # Networks, spatial or circular, share a canvas; only the spatial
            # ones have styling to offer.
            network = hasattr(live.figure.painter, "node_at")
            canvas = self.native if network else self.canvas
            self._styleable = live.figure.kind == "network"
            self._place_styling()
            item = self.figures.currentItem()
            key = (self.recordings.currentRow(), self._identity(item.data(0, _REQUEST_ROLE)),
                   self.lag.currentData(), self.variant.currentData())
            started = time.perf_counter()
            # Restyling the figure that is already up keeps its zoom.
            canvas.show_figure(live.figure, keep_view=key == self._native_key)
            self._native_key = key
            self.view.show_message("")
            self._stack.setCurrentWidget(canvas)
            canvas.repaint()
            self._on_painted(time.perf_counter() - started)
            return

        # A spatial network plot is one plot_network drew, which says so.
        self._styleable = live.figure is not None and any(
            hover.legend(ax) is not None for ax in live.figure.axes)
        self._place_styling()
        self._native_key = None
        self._stack.setCurrentWidget(self.view)
        self.view.show_live(live)

    def _on_failed(self, generation: int, message: str) -> None:
        if generation == self._generation:
            self.status.setText("")
            self._styleable = False
            self._place_styling()
            self._stack.setCurrentWidget(self.view)
            self.view.show_message(message)
        self._finish()

    def _on_painted(self, seconds: float) -> None:
        self.status.setText(f"Drawn in {self._drew_in + seconds:.2f} s")
        self.status.setToolTip(f"{self._drew_in:.2f} s to make the figure, "
                               f"{seconds:.2f} s to put it on screen.")

    def _on_picked(self, text: str) -> None:
        self.selection.setText("Selected: " + text if text else "")

    def _on_hover(self, text: str) -> None:
        self.readout.setText(text or self.HINT)

    # ── previewing a recording pointed at across recordings ──────────────────

    def _preview_request(self, name: str) -> tuple[dict, str] | None:
        """Which of *name*'s own figures to preview, and what it is called.

        An activity comparison previews the raster; a network one, the
        spatial network at the comparison's lag. Each falls back on the other
        when the recording does not have it (a CAT-NAP run from before rasters
        were stored has none).
        """
        recs = {r["name"]: r for r in self._manifest.get("recordings", [])}
        rec = recs.get(name)
        item = self.figures.currentItem()
        shown = item.data(0, _REQUEST_ROLE) if item is not None else None
        if rec is None or not shown:
            return None
        lag = self.lag.currentData()
        if lag is None and rec.get("lags"):
            lag = rec["lags"][0]
        network = rec["figures"].get(str(lag), []) if lag is not None else []
        spatial = next((f for f in network if f["label"].startswith("Network — ")),
                       network[0] if network else None)
        raster = next((f for f in rec.get("activity", []) if "aster" in f["name"]), None)
        found = []
        if raster is not None:
            found.append(({"kind": "activity", "recording": name, "name": raster["name"]},
                          raster["label"]))
        if spatial is not None:
            found.append(({"kind": "network", "recording": name, "name": spatial["name"],
                           "lag": lag}, "Network"))
        if shown.get("family") == "network" or shown.get("kind") != "comparison":
            found.reverse()
        return found[0] if found else None

    def _on_point_recording(self, name: str, pinned: bool) -> None:
        if pinned:
            self._pinned_recording = name or None
        else:
            self._hover_recording = name or None
        target = self._hover_recording or self._pinned_recording
        if target is None:
            self._preview_hide.start()
            return
        self._preview_hide.stop()
        # A pinned card stays where it is while the pointer wanders off it.
        self._show_preview(target, move=self._hover_recording is not None)

    def _show_preview(self, name: str, *, move: bool = True) -> None:
        found = self._preview_request(name)
        if found is None or self._service is None:
            self.preview.hide()
            return
        request, label = found
        key = (name, request["kind"], request["name"], request.get("lag"))
        rec = next(r for r in self._manifest["recordings"] if r["name"] == name)
        detail = " · ".join(str(v) for v in (rec.get("group"), self._div_text(rec)) if v)
        self.preview.show_for(name, detail, label, self._preview_cache.get(key), move=move)
        self.preview.setProperty("request", (request, label))
        if key not in self._preview_cache:
            self._preview_wanted = (key, request)
            self._next_preview()

    def _next_preview(self) -> None:
        """Draw the latest picture asked for, one at a time, behind any figure."""
        if self._preview_busy or self._preview_wanted is None:
            return
        key, request = self._preview_wanted
        self._preview_wanted = None
        if key in self._preview_cache:
            return
        self._preview_busy = True
        self._pool.start(_Preview(key, self._service, request, self._preview_w,
                                  self._preview_signals))

    def _on_preview(self, key: tuple, image) -> None:
        self._preview_busy = False
        self._preview_cache[key] = image
        if self.preview.isVisible() and self.preview.name == key[0]:
            self.preview.set_image(image)
        self._next_preview()

    def _on_preview_failed(self, key: tuple, message: str) -> None:
        self._preview_busy = False
        if self.preview.isVisible() and self.preview.name == key[0]:
            self.preview.set_image(None, failed=message)
        self._next_preview()

    def _hide_preview_if_idle(self) -> None:
        if self.preview.underMouse() or self._pinned_recording or self._hover_recording:
            return
        self.preview.hide()

    def _dismiss_preview(self) -> None:
        """A new figure: no recording is pointed at any more."""
        self._hover_recording = self._pinned_recording = None
        self._preview_wanted = None
        self._preview_hide.stop()
        self.preview.hide()

    def _open_preview(self, name: str) -> None:
        """Open the recording on the card at the figure it previews."""
        found = self._preview_request(name)
        self._dismiss_preview()
        if found is None:
            return
        request, _label = found
        self._remember()
        self._remembered[RECORDING] = self._identity(request)
        self.select_recording(name, notify=False)
        if self._scope == RECORDING:
            self._on_recording(0)
        else:
            self.set_scope(RECORDING)

    def _save(self) -> None:
        shown, item = self._stack.currentWidget(), self.figures.currentItem()
        request = item.data(0, _REQUEST_ROLE) if item is not None else None
        if not request or (shown is self.view and self.view.figure is None):
            return
        name = str(request.get("name") or request.get("metric") or request.get("key"))
        if shown is self.montage:
            name += "_acrossDIVs"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save figure", name + ".png",
            "PNG image, 300 dpi (*.png);;SVG, editable (*.svg);;PDF, editable (*.pdf)")
        if not path:
            return
        if shown is self.view:
            # A matplotlib figure: as shown, at the pipeline's text sizes.
            self.view.save(path)
        else:
            # A Qt-drawn figure: what is on screen is what is written.
            shown.export(path)

    def closeEvent(self, event) -> None:
        self.close_run()
        super().closeEvent(event)

