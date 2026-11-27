"""The per-cell tracking page, in Qt.

The web page (:mod:`meanap.catnap.tracking.viewer`) ships data, not pictures —
mean images, ROI masks, centroids, footprints, traces and metric comparisons as
arrays in one payload per chain — and draws them in the browser. This draws the
same payload with pyqtgraph, so the two cannot disagree about what a chain
holds.

What it shows: the chain list (searchable), every day's field of view side by
side with pan and zoom shared between days, tracked ROIs in their cell's colour
or by cell type, and the cell list worst-first. For the selected cell: a table
of its days — the suite2p ROI number and position where it was found, and where
it *should* be on the days it was not (:mod:`meanap.catnap.tracking.review`),
drawn on those days' images as a dashed ring — its immunostain labels with the
call to make for each marker, and its footprint and trace on each day with
each metric's standing against the null.

The cell list filters to the cells missing on a given day, and to cell-type
conflicts: labels that change across days, and those nobody has settled.
Decisions are saved through the run's service, to the same file the web page
writes (beside a bundle, since a bundle is read-only).

Not carried over yet: the null/matched distribution strips and the overview,
network and development views.
"""

from __future__ import annotations

import base64
import time

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGraphicsPixmapItem, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QToolTip, QVBoxLayout, QWidget,
)

from meanap.catnap.tracking.review import (
    Expected, expected_positions, final_call, is_flip, missing_sessions, nearest_roi,
    needs_decision, recommended_call, roi_number, session_rows,
)
from meanap.catnap.tracking.viewer import cluster_colour

__all__ = ["TrackingView"]

SELECTED = "#ffd400"
#: Half-width, in full-frame pixels, of the view "Zoom to cell" gives.
CELL_WINDOW_PX = 110
#: Cell-type colours on the dark field of view: the web page's dark theme.
CALL_COLOURS = {"+": "#fbbf24", "-": "#60a5fa", "~": "#c084fc", None: "#6b747d"}
#: A label on one day, as the page writes it.
STATE = {1: "+", -1: "−", 0: "?"}
#: What a marker's call reads as in the list and the tables.
CALL_TEXT = {"+": "+", "-": "−", None: ""}
#: The decisions a person can make, as the override store spells them; ``None``
#: clears the decision and goes back to the recommendation.
DECISIONS = (("+", "+ positive"), ("-", "− negative"), ("?", "can't tell"))


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


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    return label


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(26)
    return table


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
        # untracked ROIs answer a hover too: on a day a cell was missed, one of
        # them can be the cell suite2p found but the matcher did not join
        self.others = pg.ScatterPlotItem(
            x=self.cx[~tracked], y=self.cy[~tracked], size=5, pxMode=True,
            brush=pg.mkBrush(170, 170, 170, 150), pen=None,
            data=np.flatnonzero(~tracked), hoverable=True,
            hoverPen=pg.mkPen(SELECTED, width=1.5), hoverSize=8, tip=None)
        self.others.setZValue(2)
        self.rows = np.flatnonzero(tracked)
        self.cells = pg.ScatterPlotItem(
            x=self.cx[tracked], y=self.cy[tracked], size=9, pxMode=True,
            pen=pg.mkPen("k", width=0.8), data=self.cluster[tracked],
            hoverable=True, hoverPen=pg.mkPen(SELECTED, width=2), tip=None)
        self.cells.setZValue(3)
        self.ring = pg.ScatterPlotItem(size=26, pxMode=True, brush=pg.mkBrush(None),
                                       pen=pg.mkPen(SELECTED, width=2.5), tip=None)
        self.ring.setZValue(4)
        # where the cell should be on a day it was not found
        self.expected = pg.ScatterPlotItem(
            size=30, pxMode=True, brush=pg.mkBrush(None),
            pen=pg.mkPen(SELECTED, width=2, style=Qt.PenStyle.DashLine), tip=None)
        self.expected.setZValue(4)
        self.note = pg.TextItem("", color=SELECTED, anchor=(0, 1))
        self.note.setZValue(5)
        for item in (self.others, self.cells, self.ring, self.expected):
            plot.addItem(item)
        plot.addItem(self.note, ignoreBounds=True)

    def colour_cells(self, brushes: list) -> None:
        self.cells.setBrush(brushes)


class TrackingView(QWidget):
    """Chains, their fields of view across days, and one cell in detail."""

    hovered = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = None
        self._payload: dict | None = None
        self._days: list[_Day] = []
        self._cell: dict | None = None
        self._expected: dict[int, dict[int, Expected]] = {}
        #: Rows of the cell table, as indices into the payload's cells.
        self._shown: list[int] = []
        self.timings: dict[str, float] = {}

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter, e.g. pup4A")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_chains)
        # which fields of view carry immunostain labels: most do not, and the
        # cell-type review is only possible on those that do
        self.labels_filter = QComboBox()
        self.labels_filter.setToolTip(
            "Only the fields of view with immunostaining labels, or with one "
            "marker. The Cell type filter and calls only appear on these.")
        self.labels_filter.currentIndexChanged.connect(
            lambda _i: self._filter_chains(self.search.text()))
        self.chains = QListWidget()
        self.chains.currentItemChanged.connect(lambda *_: self._on_chain())
        # Names differ at both ends (prep at the start, genotype at the end):
        # shorten the middle rather than scroll sideways.
        self.chains.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chains.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        left, left_box = _card()
        left_box.addWidget(_heading("Fields of view"))
        left_box.addWidget(self.search)
        left_box.addWidget(self.labels_filter)
        left_box.addWidget(self.chains, 1)
        left.setMinimumWidth(270)

        self.background = QComboBox()
        self.background.addItem("Mean image", "mean")
        self.background.addItem("ROI footprints", "masks")
        self.background.addItem("Both", "both")
        self.background.currentIndexChanged.connect(lambda _i: self._layers())
        self.colour_by = QComboBox()
        self.colour_by.setToolTip(
            "Colour tracked ROIs by their cell, or by a marker's call for that cell "
            "(amber +, blue −, violet changes across days and undecided, grey unlabelled).")
        self.colour_by.currentIndexChanged.connect(lambda _i: self._colour())
        self.untracked = QCheckBox("Show untracked ROIs")
        self.untracked.setChecked(True)
        self.untracked.toggled.connect(lambda _on: self._layers())
        zoom = QPushButton("Zoom to cell")
        zoom.setObjectName("ghost")
        zoom.clicked.connect(self.zoom_to_cell)
        reset = QPushButton("Whole field")
        reset.setObjectName("ghost")
        reset.clicked.connect(self.reset_view)
        self.status = _muted()
        self.chain_title = QLabel("")
        self.chain_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.chain_title)
        bar.addSpacing(12)
        bar.addWidget(_muted("Background"))
        bar.addWidget(self.background)
        self._colour_label = _muted("Colour")
        bar.addWidget(self._colour_label)
        bar.addWidget(self.colour_by)
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

        # ── the cell list and its filters ────────────────────────────────────
        self.missing_filter = QComboBox()
        self.missing_filter.setToolTip(
            "Only the cells suite2p did not find on some day. Their expected "
            "position on that day is drawn as a dashed ring.")
        self.missing_filter.currentIndexChanged.connect(lambda _i: self._fill_cells())
        self.type_filter = QComboBox()
        self.type_filter.setToolTip(
            "Cell-type conflicts: a label that changes across days means the "
            "match or a label is wrong. 'Needs a decision' is a change that the "
            "recommendation leaves tied and nobody has settled.")
        self.type_filter.currentIndexChanged.connect(lambda _i: self._fill_cells())
        self.shown_count = _muted()
        filters = QGridLayout()
        filters.setHorizontalSpacing(8)
        filters.addWidget(_muted("Missing"), 0, 0)
        filters.addWidget(self.missing_filter, 0, 1)
        self._type_label = _muted("Cell type")
        filters.addWidget(self._type_label, 1, 0)
        filters.addWidget(self.type_filter, 1, 1)
        filters.setColumnStretch(1, 1)

        self.cells = _table(["Cell"])
        self.cells.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cells.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.cells.setAlternatingRowColors(False)
        self.cells.itemSelectionChanged.connect(self._on_cell_row)

        # ── one cell ─────────────────────────────────────────────────────────
        self.days = _table(["DIV", "suite2p ROI", "x", "y", ""])
        self.days.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.days.setWordWrap(False)
        self.decisions = QWidget()
        self._decisions_box = QHBoxLayout(self.decisions)
        self._decisions_box.setContentsMargins(0, 0, 0, 0)
        self._decisions_box.setSpacing(10)
        self.decision_note = _muted()
        self.decision_note.setWordWrap(True)
        self.copy = QPushButton("Copy")
        self.copy.setObjectName("ghost")
        self.copy.setToolTip("Copy this cell's days — ROI numbers, positions and "
                             "labels — as tab-separated text, ready to paste.")
        self.copy.clicked.connect(self.copy_cell)

        self._detail = pg.GraphicsLayoutWidget()
        self._detail.setBackground("w")
        self._detail.setFrameShape(QFrame.Shape.NoFrame)
        self.metrics = _table([])
        self.metrics.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        cell_side, cell_box = _card()
        cell_box.addWidget(_heading("Tracked cells, least convincing first"))
        cell_box.addLayout(filters)
        cell_box.addWidget(self.shown_count)
        cell_box.addWidget(self.cells, 1)
        detail_side, detail_box = _card()
        self.cell_title = QLabel("")
        self.cell_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        title_row = QHBoxLayout()
        title_row.addWidget(self.cell_title, 1)
        title_row.addWidget(self.copy)
        detail_box.addLayout(title_row)
        detail_box.addWidget(self.days)
        detail_box.addWidget(self.decisions)
        detail_box.addWidget(self.decision_note)
        detail_box.addWidget(self._detail, 3)
        detail_box.addWidget(self.metrics, 2)
        lower = QSplitter()
        lower.setHandleWidth(10)
        lower.addWidget(cell_side)
        lower.addWidget(detail_side)
        lower.setStretchFactor(1, 1)
        lower.setSizes([420, 680])

        upper, upper_box = _card()
        upper_box.addLayout(bar)
        upper_box.addWidget(self.subtitle)
        upper_box.addWidget(self._fov, 1)
        right = QSplitter(Qt.Orientation.Vertical)
        right.setHandleWidth(10)
        right.addWidget(upper)
        right.addWidget(lower)
        right.setSizes([420, 480])

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
        counts: dict[str, int] = {}
        labelled = 0
        for chain in listing["chains"]:
            days = ", ".join(str(d) for d in chain.get("divs", []))
            sep = chain.get("separability")
            detail = " · ".join(v for v in (
                chain.get("genotype"), f"DIV {days}" if days else "",
                f"{chain.get('networkCells', 0)} cells",
                f"separability {sep:.2f}" if sep is not None else "") if v)
            markers = list((chain.get("cellTypes") or {}).get("markers") or [])
            text = f"{chain['chain']}\n{detail}"
            if markers:
                text += "\nCell types: " + ", ".join(markers)
                labelled += 1
                for m in markers:
                    counts[m] = counts.get(m, 0) + 1
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, chain["chain"])
            item.setData(Qt.ItemDataRole.UserRole + 1, markers)
            self.chains.addItem(item)
        self.labels_filter.blockSignals(True)
        self.labels_filter.clear()
        self.labels_filter.addItem(f"All fields of view ({len(listing['chains'])})", None)
        if labelled:
            self.labels_filter.addItem(f"With cell types ({labelled})", "")
            for m in sorted(counts):
                self.labels_filter.addItem(f"With {m} ({counts[m]})", m)
        self.labels_filter.blockSignals(False)
        self.labels_filter.setVisible(bool(labelled))
        self._filter_chains(self.search.text())
        if self.chains.count():
            self.chains.setCurrentRow(0)
        return True

    def close_run(self) -> None:
        self._service = None
        self._payload = None

    def show_chain(self, key: str) -> None:
        for row in range(self.chains.count()):
            if self.chains.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.chains.item(row).setHidden(False)
                self.chains.setCurrentRow(row)
                return
        raise KeyError(key)

    def _filter_chains(self, text: str) -> None:
        words = text.lower().split()
        # None: every chain; "": any marker; otherwise that marker
        want = self.labels_filter.currentData()
        for row in range(self.chains.count()):
            item = self.chains.item(row)
            name = item.text().lower()
            markers = item.data(Qt.ItemDataRole.UserRole + 1) or []
            labels_ok = want is None or (bool(markers) if want == "" else want in markers)
            item.setHidden(not (labels_ok and all(w in name for w in words)))
        # the page must not go on showing a chain the list no longer has
        current = self.chains.currentItem()
        if current is not None and current.isHidden():
            visible = [r for r in range(self.chains.count())
                       if not self.chains.item(r).isHidden()]
            if visible:
                self.chains.setCurrentRow(visible[0])

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

    @property
    def markers(self) -> list[str]:
        return list((self._payload or {}).get("markers") or [])

    @property
    def overrides(self) -> dict:
        if self._payload is None:
            return {}
        return self._payload.setdefault("overrides", {})

    def _show(self, payload: dict) -> None:
        self._payload = payload
        self._cell = None
        self._expected = expected_positions(payload)
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
                lambda _item, points, _ev, k=column: self._on_roi_hover(points, k, True))
            day.others.sigHovered.connect(
                lambda _item, points, _ev, k=column: self._on_roi_hover(points, k, False))
            if first is None:
                first = plot
            else:
                plot.setXLink(first)
                plot.setYLink(first)
            self._days.append(day)
        self._layers()
        self.reset_view()

        self._build_filters()
        self.colour_by.blockSignals(True)
        self.colour_by.clear()
        self.colour_by.addItem("Cell", None)
        for marker in self.markers:
            self.colour_by.addItem(marker, marker)
        self.colour_by.setVisible(bool(self.markers))
        self._colour_label.setVisible(bool(self.markers))
        self.colour_by.blockSignals(False)
        self._colour()
        self._fill_cells()

    def _layers(self) -> None:
        mode, others = self.background.currentData(), self.untracked.isChecked()
        for day in self._days:
            day.layers["mean"].setVisible(mode in ("mean", "both"))
            day.layers["tracked"].setVisible(mode in ("masks", "both"))
            day.layers["other"].setVisible(mode in ("masks", "both") and others)
            day.others.setVisible(others)

    def _colour(self) -> None:
        """Tracked ROIs in their cell's colour, or by one marker's call."""
        if self._payload is None:
            return
        marker = self.colour_by.currentData()
        calls = {}
        if marker:
            for cell in self._payload["cells"]:
                call = final_call(cell, marker, self.overrides)
                if call is None and is_flip(cell, marker):
                    call = "~"
                calls[int(cell["cluster"])] = call
        for day in self._days:
            tracked = day.cluster[day.rows]
            if marker:
                day.colour_cells([pg.mkBrush(CALL_COLOURS[calls.get(int(c))])
                                  for c in tracked])
            else:
                day.colour_cells([pg.mkBrush(*cluster_colour(int(c))) for c in tracked])
        ring = "#ffffff" if marker else SELECTED
        for day in self._days:
            day.ring.setPen(pg.mkPen(ring, width=2.5))

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
        for e in self._expected.get(int(self._cell["cluster"]), {}).values():
            ys.append(e.y)
            xs.append(e.x)
        x, y = float(np.mean(xs)), float(np.mean(ys))
        # Wide enough to hold the cell on every day, however far it drifted.
        half = max(CELL_WINDOW_PX, float(np.ptp(xs)) / 2 + 40, float(np.ptp(ys)) / 2 + 40)
        self._days[0].plot.setRange(xRange=(x - half, x + half),
                                    yRange=(y - half, y + half), padding=0)

    def _follow(self, cell: dict) -> None:
        """Zoomed in, pan to a newly selected cell that is out of view.

        Whole-field views are left alone; a zoomed view keeps its zoom, so
        stepping through a list of cells stays at the scale chosen for them.
        """
        if not self._days or self._payload is None:
            return
        (x0, x1), (y0, y1) = self._days[0].plot.viewRange()
        frame = float(self._payload.get("frame", 1.0))
        if x1 - x0 >= frame * 0.98:
            return
        x = float(np.mean([p[2] for p in cell["positions"]]))
        y = float(np.mean([p[1] for p in cell["positions"]]))
        if x0 <= x <= x1 and y0 <= y <= y1:
            return
        hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
        self._days[0].plot.setRange(xRange=(x - hw, x + hw), yRange=(y - hh, y + hh),
                                    padding=0)

    # ── the cell list ────────────────────────────────────────────────────────

    def _build_filters(self) -> None:
        cells = self._payload["cells"]
        sessions = self._payload["sessions"]
        n = len(sessions)
        missing = [set(missing_sessions(c, n)) for c in cells]
        self.missing_filter.blockSignals(True)
        self.missing_filter.clear()
        self.missing_filter.addItem(f"All tracked cells ({len(cells)})", None)
        self.missing_filter.addItem(
            f"Missing on any day ({sum(1 for m in missing if m)})", "any")
        for k, session in enumerate(sessions):
            count = sum(1 for m in missing if k in m)
            self.missing_filter.addItem(f"Missing on DIV {session['div']} ({count})", k)
        self.missing_filter.blockSignals(False)

        markers, overrides = self.markers, self.overrides
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("Any", None)
        if markers:
            self.type_filter.addItem(
                f"Needs a decision ({sum(needs_decision(c, markers, overrides) for c in cells)})",
                "review")
            self.type_filter.addItem(
                "Label changes, any marker "
                f"({sum(any(is_flip(c, m) for m in markers) for c in cells)})",
                "flip:")
            for m in markers:
                flips = sum(is_flip(c, m) for c in cells)
                pos = sum(final_call(c, m, overrides) == "+" for c in cells)
                neg = sum(final_call(c, m, overrides) == "-" for c in cells)
                self.type_filter.addItem(f"{m} changes across days ({flips})", f"flip:{m}")
                self.type_filter.addItem(f"{m} + ({pos})", f"+:{m}")
                self.type_filter.addItem(f"{m} − ({neg})", f"-:{m}")
        self.type_filter.blockSignals(False)
        for widget in (self.type_filter, self._type_label):
            widget.setVisible(bool(markers))

    def _keep(self, cell: dict) -> bool:
        n = len(self._payload["sessions"])
        want = self.missing_filter.currentData()
        if want is not None:
            missing = missing_sessions(cell, n)
            if (want == "any" and not missing) or (want != "any" and want not in missing):
                return False
        kind = self.type_filter.currentData()
        if kind is None:
            return True
        # "review", "flip:" (any marker), "flip:<marker>", "+:<marker>", "-:<marker>"
        what, _, marker = kind.partition(":")
        markers, overrides = self.markers, self.overrides
        if what == "review":
            return needs_decision(cell, markers, overrides)
        if what == "flip":
            return is_flip(cell, marker) if marker else any(is_flip(cell, m) for m in markers)
        return final_call(cell, marker, overrides) == what

    def _cell_columns(self) -> list[str]:
        return ["Cell", "Found on", "Missing on", *self.markers, "r"]

    def _call_text(self, cell: dict, marker: str) -> str:
        call = final_call(cell, marker, self.overrides)
        decided = marker in (self.overrides.get(str(int(cell["cluster"]))) or {})
        if call is not None:
            text = CALL_TEXT[call]
        elif decided:
            text = "?"
        else:
            text = "±" if is_flip(cell, marker) else ""
        return text + (" ✎" if decided else "")

    def _fill_cells(self, keep_cluster: int | None = None) -> None:
        """Rebuild the list from the filters; keep *keep_cluster* selected."""
        if self._payload is None:
            return
        cells = self._payload["cells"]
        sessions = self._payload["sessions"]
        current = keep_cluster if keep_cluster is not None else (
            int(self._cell["cluster"]) if self._cell else None)
        self._shown = [i for i, c in enumerate(cells) if self._keep(c)]
        columns = self._cell_columns()
        self.cells.blockSignals(True)
        self.cells.clear()
        self.cells.setColumnCount(len(columns))
        self.cells.setHorizontalHeaderLabels(columns)
        self.cells.setRowCount(len(self._shown))
        for row, index in enumerate(self._shown):
            cell = cells[index]
            r = cell.get("fingerprint")
            missing = missing_sessions(cell, len(sessions))
            values = [str(cell["cluster"]),
                      ", ".join(str(d) for d in cell["divs"]),
                      ", ".join(str(sessions[k]["div"]) for k in missing),
                      *(self._call_text(cell, m) for m in self.markers),
                      "" if r is None else f"{r:.2f}"]
            for column, text in enumerate(values):
                entry = QTableWidgetItem(text)
                if column == 0:
                    entry.setForeground(QColor(*cluster_colour(int(cell["cluster"]))))
                elif 3 <= column < 3 + len(self.markers):
                    marker = self.markers[column - 3]
                    call = final_call(cell, marker, self.overrides)
                    if call is None and is_flip(cell, marker):
                        call = "~"
                    if call is not None:
                        entry.setForeground(QColor(CALL_COLOURS[call]))
                    if is_flip(cell, marker):
                        font = entry.font()
                        font.setBold(True)
                        entry.setFont(font)
                    entry.setToolTip(self._marker_tip(cell, marker))
                self.cells.setItem(row, column, entry)
        header = self.cells.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(columns) - 1, QHeaderView.ResizeMode.Stretch)
        self.cells.blockSignals(False)
        self.shown_count.setText(f"{len(self._shown)} of {len(cells)} cells"
                                 + ("" if not self.markers else
                                    " · bold: label changes across days · ± undecided · ✎ decided by hand"))
        rows = [cells[i]["cluster"] for i in self._shown]
        if current is not None and current in rows:
            self.cells.selectRow(rows.index(current))
        elif self._shown:
            self.cells.selectRow(0)
        else:
            self._show_cell(None)

    def _marker_tip(self, cell: dict, marker: str) -> str:
        rec = (cell.get("typeRec") or {}).get(marker) or {}
        labels = (cell.get("types") or {}).get(marker) or []
        days = ", ".join(f"DIV {d} {STATE.get(int(v), '?')}"
                         for d, v in zip(cell["divs"], labels))
        why = rec.get("reason")
        decided = (self.overrides.get(str(int(cell["cluster"]))) or {}).get(marker)
        return (f"{marker}: {days or 'no labels'}"
                + (f"\nrecommended {CALL_TEXT.get(rec.get('call'), '') or 'nothing (tie)'}"
                   f" — {why}" if rec else "")
                + (f"\ndecided by hand: {decided}" if decided else ""))

    # ── one cell ─────────────────────────────────────────────────────────────

    @property
    def cell(self) -> dict | None:
        return self._cell

    def select_cluster(self, cluster: int) -> None:
        cells = self._payload["cells"]
        rows = [int(cells[i]["cluster"]) for i in self._shown]
        if int(cluster) not in rows:
            # filtered out: show everything rather than ignore the click
            self.missing_filter.blockSignals(True)
            self.type_filter.blockSignals(True)
            self.missing_filter.setCurrentIndex(0)
            self.type_filter.setCurrentIndex(0)
            self.missing_filter.blockSignals(False)
            self.type_filter.blockSignals(False)
            self._fill_cells(keep_cluster=int(cluster))
            return
        self.cells.selectRow(rows.index(int(cluster)))

    def _on_cell_row(self) -> None:
        rows = self.cells.selectionModel().selectedRows()
        cells = self._payload["cells"] if self._payload else []
        if rows and rows[0].row() < len(self._shown):
            self._show_cell(cells[self._shown[rows[0].row()]])
        else:
            self._show_cell(None)

    def _on_roi_click(self, _item, points, _event) -> None:
        if len(points):
            self.select_cluster(int(points[0].data()))

    def _on_roi_hover(self, points, k: int, tracked: bool) -> None:
        if not len(points):
            QToolTip.hideText()
            self.hovered.emit("")
            return
        session = self._payload["sessions"][k]
        if tracked:
            cluster = int(points[0].data())
            row = session_rows(session).get(cluster)
            text = (f"Cell {cluster} on DIV {session['div']}"
                    + (f" · suite2p ROI {roi_number(session, row)}" if row is not None else ""))
        else:
            row = int(points[0].data())
            text = f"Untracked suite2p ROI {roi_number(session, row)} on DIV {session['div']}"
        pos = points[0].pos()
        text += f" · x {pos.x():.0f}, y {pos.y():.0f}"
        QToolTip.showText(QCursor.pos(), text, self)
        self.hovered.emit(text)

    def day_rows(self, cell: dict) -> list[dict]:
        """The selected cell, one row per day: what was found, or where to look."""
        sessions = self._payload["sessions"]
        here = {int(s): (y, x) for s, y, x in cell["positions"]}
        expected = self._expected.get(int(cell["cluster"]), {})
        labels = cell.get("types") or {}
        out = []
        for k, session in enumerate(sessions):
            div = session["div"]
            # "note" is the short form for the table; "detail" says it in full
            row = {"div": div, "session": k, "found": k in here, "roi": None,
                   "x": None, "y": None, "note": "", "detail": "", "nearest": "",
                   "labels": {m: "" for m in self.markers}}
            if k in here:
                row["y"], row["x"] = here[k]
                position = cell["divs"].index(div)
                for m in self.markers:
                    values = labels.get(m) or []
                    row["labels"][m] = (STATE.get(int(values[position]), "?")
                                        if position < len(values) else "")
                srow = session_rows(session).get(int(cell["cluster"]))
                row["roi"] = None if srow is None else roi_number(session, srow)
                if div in (cell.get("rescuedDivs") or []):
                    row["note"] = "added by position"
                    row["detail"] = ("Added by position: the matcher left this ROI "
                                     "unmatched, and it was the only unmatched ROI "
                                     "within 10 px of where the cell should be.")
                elif div in (cell.get("mergedDivs") or []):
                    row["note"] = "joined"
                    row["detail"] = ("Joined: the matcher tracked this cell as a second "
                                     "cell on these days, at the same position.")
            elif k in expected:
                e = expected[k]
                row["y"], row["x"] = e.y, e.x
                row["note"] = ("expected here" + (f", ±{e.spread_px:.0f} px"
                                                  if e.n_days > 1 else ""))
                row["detail"] = (
                    "Not found on this day. x, y is where it should be, in this "
                    "day's own suite2p pixels: its position on each day it was found "
                    "on, moved by how far the field drifted to this day (the median "
                    "shift of the cells tracked on both). "
                    + (f"{e.n_days} days give estimates within {e.spread_px:.0f} px "
                       "of each other." if e.n_days > 1 else "One day gives the estimate."))
                near = nearest_roi(session, e.y, e.x)
                if near is not None:
                    nrow, dist = near
                    owner = int(session["cluster"][nrow])
                    whose = "untracked" if owner < 0 else f"cell {owner}"
                    row["nearest"] = f"{roi_number(session, nrow)} ({whose}, {dist:.0f} px)"
            else:
                row["note"] = "no estimate"
                row["detail"] = ("Not found, and this day shares too few tracked cells "
                                 "with the days this cell was found on to say how far "
                                 "the field moved.")
            out.append(row)
        return out

    def _show_cell(self, cell: dict | None) -> None:
        self._cell = cell
        where = {int(s): (x, y) for s, y, x in cell["positions"]} if cell else {}
        expected = self._expected.get(int(cell["cluster"]), {}) if cell else {}
        for index, day in enumerate(self._days):
            session = day.session
            if index in where:
                x, y = where[index]
                day.ring.setData(x=[x], y=[y])
                day.expected.setData(x=[], y=[])
                srow = session_rows(session).get(int(cell["cluster"]))
                day.note.setText("" if srow is None else f" ROI {roi_number(session, srow)}")
                day.note.setPos(x + 6, y - 6)
            elif index in expected:
                e = expected[index]
                day.ring.setData(x=[], y=[])
                day.expected.setData(x=[e.x], y=[e.y])
                day.note.setText(" expected here")
                day.note.setPos(e.x + 8, e.y - 8)
            else:
                day.ring.setData(x=[], y=[])
                day.expected.setData(x=[], y=[])
                day.note.setText("")
        if cell is not None:
            self._follow(cell)
        self._detail.clear()
        self.metrics.setRowCount(0)
        self.days.setRowCount(0)
        self._clear_decisions()
        if cell is None:
            self.cell_title.setText("")
            self.copy.setEnabled(False)
            return
        self.copy.setEnabled(True)
        days = cell["divs"]
        missing = missing_sessions(cell, len(self._payload["sessions"]))
        self.cell_title.setText(
            f"Cell {cell['cluster']}  ·  found on {len(days)} of "
            f"{len(self._payload['sessions'])} days"
            + (f", missing on DIV {', '.join(str(self._payload['sessions'][k]['div']) for k in missing)}"
               if missing else ""))
        self._fill_days(cell)
        self._fill_decisions(cell)

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

    def _fill_days(self, cell: dict) -> None:
        columns = ["DIV", "suite2p ROI", "x", "y", *self.markers, "nearest ROI", ""]
        self.days.setColumnCount(len(columns))
        self.days.setHorizontalHeaderLabels(columns)
        rows = self.day_rows(cell)
        self.days.setRowCount(len(rows))
        muted = QColor("#8a8f98")
        for r, row in enumerate(rows):
            values = [f"DIV {row['div']}",
                      "—" if row["roi"] is None else str(row["roi"]),
                      "" if row["x"] is None else f"{row['x']:.0f}",
                      "" if row["y"] is None else f"{row['y']:.0f}",
                      *(row["labels"][m] for m in self.markers), row["nearest"],
                      row["note"]]
            for c, text in enumerate(values):
                entry = QTableWidgetItem(text)
                if row["detail"]:
                    entry.setToolTip(row["detail"])
                if not row["found"]:
                    entry.setForeground(QColor(SELECTED) if c in (2, 3) else muted)
                self.days.setItem(r, c, entry)
        header = self.days.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(columns) - 1, QHeaderView.ResizeMode.Stretch)
        # every day in view at once: there are only ever a handful
        self.days.setFixedHeight(self.days.horizontalHeader().height()
                                 + 26 * len(rows) + 4)

    def _clear_decisions(self) -> None:
        while self._decisions_box.count():
            item = self._decisions_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # detached now, deleted later: the old choices must not linger
                # as children until the event loop runs
                widget.setParent(None)
                widget.deleteLater()
        self.decision_note.setText("")
        self.decisions.setVisible(False)
        self.decision_note.setVisible(False)

    def _fill_decisions(self, cell: dict) -> None:
        """One choice per marker: keep the recommendation, or decide."""
        if not self.markers or not cell.get("types"):
            return
        decided = self.overrides.get(str(int(cell["cluster"]))) or {}
        self._decisions_box.addWidget(_muted("Call"))
        for marker in self.markers:
            rec = recommended_call(cell, marker)
            choice = QComboBox()
            choice.setObjectName(f"decision_{marker}")
            choice.addItem(f"{marker}: recommended ({CALL_TEXT.get(rec) or 'tie'})", None)
            for value, text in DECISIONS:
                choice.addItem(f"{marker}: {text}", value)
            current = decided.get(marker)
            choice.setCurrentIndex(max(0, choice.findData(current)) if current else 0)
            choice.setToolTip(self._marker_tip(cell, marker))
            if is_flip(cell, marker):
                choice.setStyleSheet(f"QComboBox {{ border: 1.5px solid {CALL_COLOURS['~']}; }}")
            choice.currentIndexChanged.connect(
                lambda _i, m=marker, box=choice: self.decide(m, box.currentData()))
            self._decisions_box.addWidget(choice)
        self._decisions_box.addStretch(1)
        self.decisions.setVisible(True)
        flips = [m for m in self.markers if is_flip(cell, m)]
        self.decision_note.setText(
            ("Labels change across days for " + ", ".join(flips)
             + ": either a match or a label is wrong. " if flips else "")
            + "A call made here is saved with the run and used for its cell-type results.")
        self.decision_note.setVisible(True)

    def decide(self, marker: str, value: str | None) -> None:
        """Record a decision for the selected cell (``None`` clears it)."""
        if self._cell is None or self._service is None:
            return
        cluster = int(self._cell["cluster"])
        try:
            saved = self._service.set_tracking_override({
                "chain": self._payload.get("chainKey"), "cluster": cluster,
                "marker": marker, "value": value})
        except Exception as e:  # noqa: BLE001 — shown, not swallowed
            self.status.setText(f"Could not save the decision: {e}")
            return
        self._payload["overrides"] = saved.get("overrides", {})
        self.status.setText(f"Saved to {saved.get('file', 'the run')}")
        self._build_filters_keeping()
        self._colour()
        self._fill_cells(keep_cluster=cluster)

    def _build_filters_keeping(self) -> None:
        """Recount the filters without losing what is selected in them."""
        missing, kind = self.missing_filter.currentData(), self.type_filter.currentData()
        self._build_filters()
        for box, want in ((self.missing_filter, missing), (self.type_filter, kind)):
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(want)))
            box.blockSignals(False)

    def cell_text(self, cell: dict | None = None) -> str:
        """The cell's days as tab-separated text, header first."""
        cell = cell or self._cell
        if cell is None:
            return ""
        chain = self._payload.get("chainKey", "")
        recordings = [s.get("recording", "") for s in self._payload["sessions"]]
        lines = ["\t".join(["chain", "cell", "DIV", "recording", "suite2p ROI", "x", "y",
                            *self.markers, "nearest ROI", "note"])]
        for row in self.day_rows(cell):
            lines.append("\t".join([
                chain, str(cell["cluster"]), str(row["div"]), recordings[row["session"]],
                "" if row["roi"] is None else str(row["roi"]),
                "" if row["x"] is None else f"{row['x']:.0f}",
                "" if row["y"] is None else f"{row['y']:.0f}",
                *(row["labels"][m] for m in self.markers), row["nearest"],
                row["note"] if row["found"] else ("not found: " + row["note"])]))
        return "\n".join(lines)

    def copy_cell(self) -> None:
        text = self.cell_text()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.status.setText("Copied this cell's days")
