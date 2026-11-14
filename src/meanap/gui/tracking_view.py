"""The per-cell tracking page, in Qt (prototype).

The web page (:mod:`meanap.catnap.tracking.viewer`) ships data, not pictures —
mean images, ROI masks, centroids, footprints, traces and metric comparisons as
arrays in one payload per chain — and draws them in the browser. This draws the
same payload with pyqtgraph, so the two cannot disagree about what a chain
holds.

Carried over: the chain list, every day's field of view side by side with pan
and zoom shared between days, tracked ROIs in their cell's colour, the cell
list worst-first, and for the selected cell its footprint and trace on each day
and each metric's standing against the null.

Not carried over yet: the null/matched distribution strips, cell-type colouring
and editing, and the overview, network and development views.
"""

from __future__ import annotations

import base64
import time

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGraphicsPixmapItem, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QToolTip, QVBoxLayout, QWidget,
)

from meanap.catnap.tracking.viewer import cluster_colour

__all__ = ["TrackingView"]

SELECTED = "#ffd400"
#: Half-width, in full-frame pixels, of the view "Zoom to cell" gives.
CELL_WINDOW_PX = 110


def _f32(text: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(text), dtype=np.float32) if text else np.zeros(0)


def _pixmap(png: str) -> QPixmap:
    image = QImage.fromData(base64.b64decode(png)) if png else QImage()
    return QPixmap.fromImage(image)


# The object names below are the results viewer's (its style sheet is what
# styles this page): "card", "cardTitle", "muted", "ghost".


def _heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("cardTitle")
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    box = QVBoxLayout(card)
    box.setContentsMargins(12, 12, 12, 12)
    box.setSpacing(8)
    return card, box


class _Day:
    """One day's field of view: its layers, in a view box linked to the others."""

    def __init__(self, plot: pg.PlotItem, session: dict, frame: float) -> None:
        self.plot, self.session = plot, session
        self.cx, self.cy = _f32(session["cx"]), _f32(session["cy"])
        self.cluster = np.asarray(session["cluster"], dtype=int)
        self.layers: dict[str, QGraphicsPixmapItem] = {}
        for key, name in (("mean", "meanPng"), ("tracked", "masksTrackedPng"),
                          ("other", "masksOtherPng")):
            pixmap = _pixmap(session.get(name, ""))
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            if not pixmap.isNull():
                item.setScale(frame / pixmap.width())
            item.setZValue(0 if key == "mean" else 1)
            plot.addItem(item, ignoreBounds=True)
            self.layers[key] = item
        tracked = self.cluster >= 0
        self.others = pg.ScatterPlotItem(
            x=self.cx[~tracked], y=self.cy[~tracked], size=5, pxMode=True,
            brush=pg.mkBrush(170, 170, 170, 150), pen=None, tip=None)
        self.others.setZValue(2)
        self.rows = np.flatnonzero(tracked)
        self.cells = pg.ScatterPlotItem(
            x=self.cx[tracked], y=self.cy[tracked], size=9, pxMode=True,
            brush=[pg.mkBrush(*cluster_colour(int(c))) for c in self.cluster[tracked]],
            pen=pg.mkPen("k", width=0.8), data=self.cluster[tracked],
            hoverable=True, hoverPen=pg.mkPen(SELECTED, width=2), tip=None)
        self.cells.setZValue(3)
        self.ring = pg.ScatterPlotItem(size=26, pxMode=True, brush=pg.mkBrush(None),
                                       pen=pg.mkPen(SELECTED, width=2.5), tip=None)
        self.ring.setZValue(4)
        for item in (self.others, self.cells, self.ring):
            plot.addItem(item)


class TrackingView(QWidget):
    """Chains, their fields of view across days, and one cell in detail."""

    hovered = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = None
        self._payload: dict | None = None
        self._days: list[_Day] = []
        self._cell: dict | None = None
        self.timings: dict[str, float] = {}

        self.chains = QListWidget()
        self.chains.currentItemChanged.connect(lambda *_: self._on_chain())
        # Names differ at both ends (prep at the start, genotype at the end):
        # shorten the middle rather than scroll sideways.
        self.chains.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chains.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        left, left_box = _card()
        left_box.addWidget(_heading("Fields of view"))
        left_box.addWidget(self.chains, 1)
        left.setMinimumWidth(270)

        self.background = QComboBox()
        self.background.addItem("Mean image", "mean")
        self.background.addItem("ROI footprints", "masks")
        self.background.addItem("Both", "both")
        self.background.currentIndexChanged.connect(lambda _i: self._layers())
        self.untracked = QCheckBox("Show untracked ROIs")
        self.untracked.setChecked(True)
        self.untracked.toggled.connect(lambda _on: self._layers())
        zoom = QPushButton("Zoom to cell")
        zoom.setObjectName("ghost")
        zoom.clicked.connect(self.zoom_to_cell)
        reset = QPushButton("Whole field")
        reset.setObjectName("ghost")
        reset.clicked.connect(self.reset_view)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.chain_title = QLabel("")
        self.chain_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        background_label = QLabel("Background")
        background_label.setObjectName("muted")
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.chain_title)
        bar.addSpacing(12)
        bar.addWidget(background_label)
        bar.addWidget(self.background)
        bar.addWidget(self.untracked)
        bar.addStretch(1)
        bar.addWidget(self.status)
        bar.addWidget(zoom)
        bar.addWidget(reset)

        self.subtitle = QLabel("")
        self.subtitle.setWordWrap(True)
        self.subtitle.setTextFormat(Qt.TextFormat.RichText)
        self.subtitle.setObjectName("muted")
        self._fov = pg.GraphicsLayoutWidget()
        self._fov.setBackground("#111418")
        self._fov.setFrameShape(QFrame.Shape.NoFrame)

        self.cells = QTableWidget(0, 4)
        self.cells.setHorizontalHeaderLabels(["Cell", "Days", "Fingerprint r", "vs null"])
        self.cells.verticalHeader().hide()
        self.cells.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cells.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.cells.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cells.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cells.setShowGrid(False)
        self.cells.setAlternatingRowColors(False)
        self.cells.verticalHeader().setDefaultSectionSize(28)
        self.cells.itemSelectionChanged.connect(self._on_cell_row)

        self._detail = pg.GraphicsLayoutWidget()
        self._detail.setBackground("w")
        self._detail.setFrameShape(QFrame.Shape.NoFrame)
        self.metrics = QTableWidget(0, 0)
        self.metrics.verticalHeader().hide()
        self.metrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metrics.setShowGrid(False)
        self.metrics.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.metrics.verticalHeader().setDefaultSectionSize(28)
        self.metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        cell_side, cell_box = _card()
        cell_box.addWidget(_heading("Tracked cells, least convincing first"))
        cell_box.addWidget(self.cells, 1)
        detail_side, detail_box = _card()
        self.cell_title = QLabel("")
        self.cell_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        detail_box.addWidget(self.cell_title)
        detail_box.addWidget(self._detail, 3)
        detail_box.addWidget(self.metrics, 2)
        lower = QSplitter()
        lower.setHandleWidth(10)
        lower.addWidget(cell_side)
        lower.addWidget(detail_side)
        lower.setStretchFactor(1, 1)
        lower.setSizes([380, 720])

        upper, upper_box = _card()
        upper_box.addLayout(bar)
        upper_box.addWidget(self.subtitle)
        upper_box.addWidget(self._fov, 1)
        right = QSplitter(Qt.Orientation.Vertical)
        right.setHandleWidth(10)
        right.addWidget(upper)
        right.addWidget(lower)
        right.setSizes([440, 380])

        splitter = QSplitter()
        splitter.setHandleWidth(10)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1060])
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(splitter)

    # ── the run ──────────────────────────────────────────────────────────────

    def load(self, service) -> bool:
        """List *service*'s chains. ``False`` if the run has no tracking."""
        self._service = service
        self.chains.clear()
        listing = service.tracking()
        if not listing.get("available"):
            return False
        for chain in listing["chains"]:
            days = ", ".join(str(d) for d in chain.get("divs", []))
            sep = chain.get("separability")
            detail = " · ".join(v for v in (
                chain.get("genotype"), f"DIV {days}" if days else "",
                f"{chain.get('networkCells', 0)} cells",
                f"separability {sep:.2f}" if sep is not None else "") if v)
            item = QListWidgetItem(f"{chain['chain']}\n{detail}")
            item.setData(Qt.ItemDataRole.UserRole, chain["chain"])
            self.chains.addItem(item)
        if self.chains.count():
            self.chains.setCurrentRow(0)
        return True

    def close_run(self) -> None:
        self._service = None
        self._payload = None

    def show_chain(self, key: str) -> None:
        for row in range(self.chains.count()):
            if self.chains.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.chains.setCurrentRow(row)
                return
        raise KeyError(key)

    def _on_chain(self) -> None:
        item = self.chains.currentItem()
        if item is None or self._service is None:
            return
        started = time.perf_counter()
        payload = self._service.tracking_payload(item.data(Qt.ItemDataRole.UserRole))
        read = time.perf_counter() - started
        started = time.perf_counter()
        self._show(payload)
        shown = time.perf_counter() - started
        self.timings = {"read": read, "show": shown}
        self.status.setText(f"Opened in {read + shown:.2f} s "
                            f"({read:.2f} s reading, {shown:.2f} s drawing)")

    def _show(self, payload: dict) -> None:
        self._payload = payload
        self._cell = None
        self.chain_title.setText(str(payload.get("chainKey", "")))
        self.subtitle.setText(payload.get("subtitle", ""))
        frame = float(payload.get("frame", 1.0))

        self._fov.clear()
        self._days = []
        first = None
        for column, session in enumerate(payload["sessions"]):
            plot = self._fov.addPlot(row=0, col=column)
            plot.setTitle(f"DIV {session['div']}", color="#e5e7eb")
            plot.hideAxis("left")
            plot.hideAxis("bottom")
            plot.setMenuEnabled(False)
            plot.hideButtons()
            plot.setAspectLocked(True)
            plot.invertY(True)
            day = _Day(plot, session, frame)
            day.cells.sigClicked.connect(self._on_roi_click)
            day.cells.sigHovered.connect(
                lambda _item, points, _ev, div=session["div"]: self._on_roi_hover(points, div))
            if first is None:
                first = plot
            else:
                plot.setXLink(first)
                plot.setYLink(first)
            self._days.append(day)
        self._layers()
        self.reset_view()

        cells = payload["cells"]
        self.cells.blockSignals(True)
        self.cells.setRowCount(len(cells))
        for row, cell in enumerate(cells):
            r, pct = cell.get("fingerprint"), cell.get("percentile")
            values = (str(cell["cluster"]), ", ".join(str(d) for d in cell["divs"]),
                      "" if r is None else f"{r:.2f}",
                      "" if pct is None else f"{pct:.0f}th percentile")
            for column, text in enumerate(values):
                entry = QTableWidgetItem(text)
                if column == 0:
                    entry.setForeground(QColor(*cluster_colour(int(cell["cluster"]))))
                self.cells.setItem(row, column, entry)
        self.cells.blockSignals(False)
        if cells:
            self.cells.selectRow(0)
        else:
            self._show_cell(None)

    def _layers(self) -> None:
        mode, others = self.background.currentData(), self.untracked.isChecked()
        for day in self._days:
            day.layers["mean"].setVisible(mode in ("mean", "both"))
            day.layers["tracked"].setVisible(mode in ("masks", "both"))
            day.layers["other"].setVisible(mode in ("masks", "both") and others)
            day.others.setVisible(others)

    def reset_view(self) -> None:
        if self._payload is None or not self._days:
            return
        frame = float(self._payload.get("frame", 1.0))
        self._days[0].plot.setRange(xRange=(0, frame), yRange=(0, frame), padding=0)

    def zoom_to_cell(self) -> None:
        """Bring the selected cell to the middle of every day's view."""
        if self._cell is None or not self._days:
            return
        ys = [p[1] for p in self._cell["positions"]]
        xs = [p[2] for p in self._cell["positions"]]
        x, y = float(np.mean(xs)), float(np.mean(ys))
        # Wide enough to hold the cell on every day, however far it drifted.
        half = max(CELL_WINDOW_PX, float(np.ptp(xs)) / 2 + 40, float(np.ptp(ys)) / 2 + 40)
        self._days[0].plot.setRange(xRange=(x - half, x + half),
                                    yRange=(y - half, y + half), padding=0)

    # ── one cell ─────────────────────────────────────────────────────────────

    @property
    def cell(self) -> dict | None:
        return self._cell

    def select_cluster(self, cluster: int) -> None:
        for row, cell in enumerate(self._payload["cells"]):
            if int(cell["cluster"]) == int(cluster):
                self.cells.selectRow(row)
                return

    def _on_cell_row(self) -> None:
        rows = self.cells.selectionModel().selectedRows()
        cells = self._payload["cells"] if self._payload else []
        self._show_cell(cells[rows[0].row()] if rows and rows[0].row() < len(cells) else None)

    def _on_roi_click(self, _item, points, _event) -> None:
        if len(points):
            self.select_cluster(int(points[0].data()))

    def _on_roi_hover(self, points, div) -> None:
        if not len(points):
            QToolTip.hideText()
            self.hovered.emit("")
            return
        text = f"Cell {int(points[0].data())} on DIV {div}"
        QToolTip.showText(QCursor.pos(), text, self)
        self.hovered.emit(text)

    def _show_cell(self, cell: dict | None) -> None:
        self._cell = cell
        where = {int(s): (x, y) for s, y, x in cell["positions"]} if cell else {}
        for index, day in enumerate(self._days):
            if index in where:
                day.ring.setData(x=[where[index][0]], y=[where[index][1]])
            else:
                day.ring.setData(x=[], y=[])
        self._detail.clear()
        self.metrics.setRowCount(0)
        if cell is None:
            self.cell_title.setText("")
            return
        days = cell["divs"]
        notes = []
        if cell.get("rescuedDivs"):
            notes.append("position-completed on DIV "
                         + ", ".join(str(d) for d in cell["rescuedDivs"]))
        if cell.get("mergedDivs"):
            notes.append("merged on DIV " + ", ".join(str(d) for d in cell["mergedDivs"]))
        self.cell_title.setText(f"Cell {cell['cluster']}"
                                + (f"  ({'; '.join(notes)})" if notes else ""))

        colour = cluster_colour(int(cell["cluster"]))
        first = None
        for row, div in enumerate(days):
            crop = cell["crops"][row] if row < len(cell["crops"]) else None
            foot = self._detail.addViewBox(row=row, col=0, lockAspect=True, invertY=True,
                                           enableMouse=False)
            foot.setFixedWidth(90)
            if crop:
                pixels = _f32(crop["d"]).reshape(int(crop["h"]), int(crop["w"]))
                image = pg.ImageItem(pixels, axisOrder="row-major")
                image.setColorMap(pg.colormap.get("inferno"))
                foot.addItem(image)
                foot.autoRange(padding=0.05)
            trace = _f32(cell["traces"][row]) if row < len(cell["traces"]) else np.zeros(0)
            plot = self._detail.addPlot(row=row, col=1)
            plot.setMenuEnabled(False)
            plot.hideButtons()
            plot.setMouseEnabled(x=True, y=False)
            for name in ("left", "bottom"):
                axis = plot.getAxis(name)
                axis.setPen("#16181d")
                axis.setTextPen("#16181d")
                axis.enableAutoSIPrefix(False)
            plot.getAxis("left").setLabel(f"DIV {div}", color="#16181d")
            plot.getAxis("left").setWidth(64)
            # The payload holds each trace decimated to a fixed number of
            # points, so the axis is the fraction of the recording, not seconds.
            plot.plot(np.linspace(0, 1, len(trace)), trace,
                      pen=pg.mkPen(QColor(*colour), width=1.2), antialias=True)
            if row < len(days) - 1:
                plot.getAxis("bottom").setStyle(showValues=False)
            else:
                plot.getAxis("bottom").setLabel("fraction of the recording", color="#16181d")
            if first is None:
                first = plot
            else:
                plot.setXLink(first)

        # Per-day activity, then each cross-day measure against the null.
        per_day = cell.get("metrics") or []
        comparisons = cell.get("comparisons") or []
        self.metrics.setColumnCount(4)
        self.metrics.setHorizontalHeaderLabels(["Measure", "Value", "vs null", "vs matched"])
        rows: list[tuple[str, str, str, str]] = []
        for div, values in zip(days, per_day):
            rows.append((f"DIV {div}: events / min, interval (s), population coupling",
                         " · ".join("–" if values.get(k) is None else f"{values[k]:.3g}"
                                    for k in ("rate", "iei", "pop")), "", ""))
        for item in comparisons:
            value, pct, matched = item.get("value"), item.get("pct"), item.get("matchedPct")
            rows.append((item.get("label", item.get("key", "")),
                         "–" if value is None else f"{value:.3g}",
                         "" if pct is None else f"{pct:.0f}th percentile",
                         "" if matched is None else f"{matched:.0f}th percentile"))
        self.metrics.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, text in enumerate(values):
                self.metrics.setItem(r, c, QTableWidgetItem(text))
