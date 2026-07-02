"""Network viewer panel: load a MEA-NAP output .mat file and plot the network."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from meanap.network_plot import (
    MatData, build_cell_type_matrix, filter_by_cell_types,
    load_cell_type_file, plot_network,
)


# ── Background workers ────────────────────────────────────────────────────────

class _LoadMatWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            data = MatData(self._path)
            self.finished.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Embedded matplotlib canvas ────────────────────────────────────────────────

class _NetworkCanvas(FigureCanvasQTAgg):
    def __init__(self) -> None:
        self._fig = Figure(figsize=(7, 6), tight_layout=True)
        self._fig.patch.set_facecolor("white")
        super().__init__(self._fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._draw_placeholder()

    def _draw_placeholder(self) -> None:
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.set_facecolor("white")
        ax.text(0.5, 0.5, "Select a .mat file to display the network",
                ha="center", va="center", transform=ax.transAxes,
                color="#888888", fontsize=11)
        ax.axis("off")
        self.draw()

    def render(
        self,
        adjM: np.ndarray,
        coords: np.ndarray,
        edge_thresh: float,
        z: np.ndarray,
        z2: np.ndarray | None,
        z2_name: str,
        cell_type_matrix: np.ndarray | None,
        cell_type_names: list[str] | None,
        min_node_size: float,
        title: str,
    ) -> None:
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        self._fig.patch.set_facecolor("white")
        plot_network(
            ax, adjM, coords, edge_thresh, z, z2, z2_name,
            cell_type_matrix, cell_type_names, min_node_size, title,
        )
        self.draw()


# ── Main panel ────────────────────────────────────────────────────────────────

class NetworkViewerPanel(QWidget):
    """Interactive MEA network viewer with optional cell-type overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._mat_data: MatData | None = None
        self._cell_type_matrix: np.ndarray | None = None
        self._cell_type_names: list[str] | None = None
        self._load_worker: _LoadMatWorker | None = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([300, 700])

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        # File selection
        file_box = QGroupBox("Recording")
        file_layout = QVBoxLayout(file_box)

        path_row = QHBoxLayout()
        self._mat_path = QLineEdit()
        self._mat_path.setPlaceholderText("No file selected…")
        self._mat_path.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._on_browse_mat)
        path_row.addWidget(self._mat_path)
        path_row.addWidget(browse_btn)

        info_form = QFormLayout()
        self._info_fn = QLabel("—")
        self._info_div = QLabel("—")
        self._info_grp = QLabel("—")
        self._info_nodes = QLabel("—")
        info_form.addRow("Recording:", self._info_fn)
        info_form.addRow("DIV:", self._info_div)
        info_form.addRow("Group:", self._info_grp)
        info_form.addRow("Active nodes:", self._info_nodes)

        file_layout.addLayout(path_row)
        file_layout.addLayout(info_form)

        # Network settings
        net_box = QGroupBox("Network settings")
        net_form = QFormLayout(net_box)

        self._lag_combo = QComboBox()
        self._lag_combo.setEnabled(False)
        self._lag_combo.currentIndexChanged.connect(self._on_settings_changed)

        self._edge_thresh = QDoubleSpinBox()
        self._edge_thresh.setRange(0.0, 1.0)
        self._edge_thresh.setSingleStep(0.05)
        self._edge_thresh.setDecimals(3)
        self._edge_thresh.setValue(0.0)
        self._edge_thresh.setEnabled(False)
        self._edge_thresh.valueChanged.connect(self._on_settings_changed)

        self._node_color_metric = QComboBox()
        self._node_color_metric.addItem("None")
        self._node_color_metric.setEnabled(False)
        self._node_color_metric.currentIndexChanged.connect(self._on_settings_changed)

        net_form.addRow("Lag", self._lag_combo)
        net_form.addRow("Edge threshold", self._edge_thresh)
        net_form.addRow("Node color metric", self._node_color_metric)

        # Cell types
        ct_box = QGroupBox("Cell types")
        ct_layout = QVBoxLayout(ct_box)

        ct_btn_row = QHBoxLayout()
        self._load_ct_btn = QPushButton("Load cell types from file…")
        self._load_ct_btn.setEnabled(False)
        self._load_ct_btn.clicked.connect(self._on_load_cell_types)
        self._clear_ct_btn = QPushButton("Clear")
        self._clear_ct_btn.setFixedWidth(52)
        self._clear_ct_btn.setEnabled(False)
        self._clear_ct_btn.clicked.connect(self._on_clear_cell_types)
        ct_btn_row.addWidget(self._load_ct_btn)
        ct_btn_row.addWidget(self._clear_ct_btn)

        self._ct_hint = QLabel("Load an Excel/CSV file with one column\nper cell type and channel numbers as values.")
        self._ct_hint.setWordWrap(True)
        self._ct_hint.setStyleSheet("color: #888888; font-size: 10px;")

        self._ct_list = QListWidget()
        self._ct_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._ct_list.setMaximumHeight(180)
        self._ct_list.setVisible(False)
        self._ct_list.itemSelectionChanged.connect(self._on_cell_type_selection_changed)

        self._ct_note = QLabel("")
        self._ct_note.setWordWrap(True)
        self._ct_note.setStyleSheet("font-size: 10px;")
        self._ct_note.setVisible(False)

        ct_layout.addLayout(ct_btn_row)
        ct_layout.addWidget(self._ct_hint)
        ct_layout.addWidget(self._ct_list)
        ct_layout.addWidget(self._ct_note)

        # Log
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(90)
        self._log.setObjectName("log")
        log_layout.addWidget(self._log)

        layout.addWidget(file_box)
        layout.addWidget(net_box)
        layout.addWidget(ct_box)
        layout.addWidget(log_box)
        layout.addStretch()
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        self._canvas = _NetworkCanvas()
        layout.addWidget(self._canvas)
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_browse_mat(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MEA-NAP output .mat file", "",
            "MATLAB files (*.mat)",
        )
        if not path:
            return
        self._mat_path.setText(path)
        self._log_msg(f"Loading {Path(path).name}…")
        self._load_worker = _LoadMatWorker(path)
        self._load_worker.finished.connect(self._on_mat_loaded)
        self._load_worker.error.connect(lambda e: self._log_msg(f"Error: {e}"))
        self._load_worker.start()

    def _on_mat_loaded(self, data: MatData) -> None:
        self._mat_data = data
        info = data.info

        self._info_fn.setText(str(info.get("FN", "—")))
        self._info_div.setText(str(info.get("DIV", "—")))
        self._info_grp.setText(str(info.get("Grp", "—")))

        # Populate lag dropdown
        self._lag_combo.blockSignals(True)
        self._lag_combo.clear()
        for key in data.lag_keys:
            self._lag_combo.addItem(f"{data.lag_ms(key)} ms", userData=key)
        self._lag_combo.blockSignals(False)

        # Populate node color metric dropdown (node SIZE is always ND)
        self._node_color_metric.blockSignals(True)
        self._node_color_metric.clear()
        self._node_color_metric.addItem("None")
        metrics = data.available_node_metrics
        self._node_color_metric.addItems(sorted(metrics))
        self._node_color_metric.blockSignals(False)

        # Enable controls
        self._lag_combo.setEnabled(True)
        self._edge_thresh.setEnabled(True)
        self._node_color_metric.setEnabled(True)
        self._load_ct_btn.setEnabled(True)

        # Notify about embedded cell types
        if data.has_readable_cell_types:
            self._log_msg("Cell type data found in .mat file.")
        else:
            ct_raw = data.info.get("CellTypes")
            if ct_raw is not None:
                self._log_msg(
                    "Info.CellTypes found but is a MATLAB table (MCOS) — "
                    "use 'Load cell types from file…' to load from Excel/CSV."
                )

        self._refresh_plot()

    def _on_settings_changed(self) -> None:
        if self._mat_data is not None:
            self._refresh_plot()

    def _on_load_cell_types(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load cell type file", "",
            "Spreadsheets (*.xlsx *.xls *.csv)",
        )
        if not path:
            return
        try:
            df = load_cell_type_file(path)
            if self._mat_data is None:
                self._log_msg("Load a .mat file first.")
                return

            mat, names = build_cell_type_matrix(df, self._mat_data.channels)
            self._cell_type_matrix = mat
            self._cell_type_names = names

            self._log_msg(
                f"Loaded {len(names)} cell type(s) from {Path(path).name}: "
                + ", ".join(names)
            )
            self._populate_ct_list(names)
            self._clear_ct_btn.setEnabled(True)
            self._refresh_plot()
        except Exception as exc:
            self._log_msg(f"Cell type load error: {exc}")

    def _populate_ct_list(self, names: list[str]) -> None:
        self._ct_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            self._ct_list.addItem(item)
        self._ct_hint.setVisible(False)
        self._ct_list.setVisible(True)
        self._ct_note.setText(
            "Select cell types to filter shown nodes (intersection). "
            "Deselect all to show every active node."
        )
        self._ct_note.setVisible(True)

    def _on_clear_cell_types(self) -> None:
        self._cell_type_matrix = None
        self._cell_type_names = None
        self._ct_list.clear()
        self._ct_list.setVisible(False)
        self._ct_note.setVisible(False)
        self._ct_hint.setVisible(True)
        self._clear_ct_btn.setEnabled(False)
        self._log_msg("Cell type data cleared.")
        self._refresh_plot()

    def _on_cell_type_selection_changed(self) -> None:
        self._refresh_plot()

    # ── Plot refresh ──────────────────────────────────────────────────────────

    def _refresh_plot(self) -> None:
        data = self._mat_data
        if data is None or not data.lag_keys:
            return

        lag_key = self._lag_combo.currentData()
        if not lag_key:
            return

        edge_thresh = self._edge_thresh.value()
        color_metric = self._node_color_metric.currentText()

        adjM_full = data.get_adjM(lag_key)
        active_idx = data.get_active_indices(lag_key)

        # Node SIZE is always ND (node degree)
        z = data.get_metric(lag_key, "ND")
        if z is None:
            self._log_msg("ND metric not found in file.")
            return

        # Node COLOR is the user-selected metric (or None for flat cyan)
        z2 = data.get_metric(lag_key, color_metric) if color_metric != "None" else None

        # Build active cell-type matrix (rows correspond to active_idx)
        ct_matrix_active = None
        ct_names = self._cell_type_names

        if self._cell_type_matrix is not None and ct_names is not None:
            ct_matrix_active = self._cell_type_matrix[active_idx, :]

            selected = [item.text() for item in self._ct_list.selectedItems()]
            if selected:
                filtered_idx, ct_matrix_active = filter_by_cell_types(
                    np.arange(len(active_idx)),
                    ct_matrix_active,
                    ct_names,
                    selected,
                )
                active_idx = active_idx[filtered_idx]
                z = z[filtered_idx]
                if z2 is not None:
                    z2 = z2[filtered_idx]

        self._info_nodes.setText(str(len(active_idx)))

        adjM_sub = adjM_full[np.ix_(active_idx, active_idx)]
        coords_sub = data.coords[active_idx]
        min_node_size = float(data.params.get("minNodeSize", 0.01))

        fn = data.info.get("FN", "")
        title = f"{fn}  —  {data.lag_ms(lag_key)} ms lag"

        self._canvas.render(
            adjM_sub, coords_sub, edge_thresh, z, z2, color_metric,
            ct_matrix_active, ct_names,
            min_node_size, title,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, text: str) -> None:
        self._log.append(text)
