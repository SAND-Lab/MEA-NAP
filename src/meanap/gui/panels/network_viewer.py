"""Network viewer panel: load a MEA-NAP output .mat file and plot the network."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QSpinBox, QSplitter, QTextEdit, QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from meanap.network_plot import (
    EDGE_THRESHOLD_METHODS, LAYOUT_OPTIONS, MatData, build_cell_type_matrix,
    compute_node_coords, count_edges_shown, filter_by_cell_types,
    get_edge_threshold, limit_edges_for_plotting, load_cell_type_file,
    make_example_network, plot_network,
)

# Node-size scaling methods exposed in the UI — mirror MATLAB's nodeScalingMethod
# options (see getNodeSize.m). The value is passed straight to plot_network.
NODE_SCALING_METHODS = ["Linear", "Log2", "Log10", "Square", "Cube"]


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
        *,
        z_name: str = "node degree",
        min_ew: float = 0.001,
        max_ew: float = 4.0,
        node_size_scale: float = 1.0,
        node_scaling_method: str = "Linear",
    ) -> None:
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        self._fig.patch.set_facecolor("white")
        plot_network(
            ax, adjM, coords, edge_thresh, z, z2, z2_name,
            cell_type_matrix, cell_type_names, min_node_size, title,
            z_name=z_name,
            min_ew=min_ew, max_ew=max_ew,
            node_size_scale=node_size_scale,
            node_scaling_method=node_scaling_method,
        )
        self.draw()

    def save_figure(self, path: str, dpi: int = 600) -> None:
        """Save the current figure to *path* (format inferred from extension).

        ``dpi`` only affects raster formats (PNG); SVG is resolution-independent.
        The white facecolor is preserved so the export matches the on-screen plot.
        """
        self._fig.savefig(
            path, dpi=dpi, facecolor=self._fig.get_facecolor(), bbox_inches="tight",
        )


# ── Main panel ────────────────────────────────────────────────────────────────

class NetworkViewerPanel(QWidget):
    """Interactive MEA network viewer with optional cell-type overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._mat_data: MatData | None = None
        self._cell_type_matrix: np.ndarray | None = None
        self._cell_type_names: list[str] | None = None
        self._load_worker: _LoadMatWorker | None = None

        # Data source: "example" uses a built-in synthetic network so the
        # display controls are usable immediately; "mat" uses a loaded file.
        self._source = "example"
        self._example: dict | None = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([320, 700])

        # Start on the example network so every control does something on launch.
        self._load_example_network()

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

        example_btn = QPushButton("Use example network")
        example_btn.setToolTip(
            "Load a built-in synthetic network to experiment with the display "
            "controls without needing a MEA-NAP output file."
        )
        example_btn.clicked.connect(self._load_example_network)

        info_form = QFormLayout()
        self._info_fn = QLabel("—")
        self._info_div = QLabel("—")
        self._info_grp = QLabel("—")
        self._info_nodes = QLabel("—")
        self._info_edges = QLabel("—")
        info_form.addRow("Recording:", self._info_fn)
        info_form.addRow("DIV:", self._info_div)
        info_form.addRow("Group:", self._info_grp)
        info_form.addRow("Active nodes:", self._info_nodes)
        info_form.addRow("Edges shown:", self._info_edges)

        file_layout.addLayout(path_row)
        file_layout.addWidget(example_btn)
        file_layout.addLayout(info_form)

        # Network settings
        net_box = QGroupBox("Network settings")
        net_form = QFormLayout(net_box)

        self._lag_combo = QComboBox()
        self._lag_combo.setEnabled(False)
        self._lag_combo.currentIndexChanged.connect(self._on_settings_changed)

        self._edge_thresh_method = QComboBox()
        self._edge_thresh_method.addItems(EDGE_THRESHOLD_METHODS)
        self._edge_thresh_method.currentIndexChanged.connect(self._on_edge_thresh_method_changed)

        # One spinbox whose meaning depends on the method: a weight (0–1) for
        # "Absolute value", or a percentile (0–100 %) for "Percentile".
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

        self._node_size_metric = QComboBox()
        self._node_size_metric.addItem("node degree")
        self._node_size_metric.currentIndexChanged.connect(self._on_settings_changed)

        net_form.addRow("Lag", self._lag_combo)
        net_form.addRow("Edge threshold by", self._edge_thresh_method)
        net_form.addRow("Edge threshold", self._edge_thresh)
        net_form.addRow("Node size metric", self._node_size_metric)
        net_form.addRow("Node color metric", self._node_color_metric)

        # ── Display settings (live-updating visual controls) ───────────────────
        disp_box = QGroupBox("Display")
        disp_form = QFormLayout(disp_box)

        self._layout_combo = QComboBox()
        self._layout_combo.addItems(LAYOUT_OPTIONS)
        self._layout_combo.currentIndexChanged.connect(self._on_settings_changed)

        # Max edges to draw — keeps the strongest N by |weight| (HighToLow),
        # a plotting-only subsample so dense networks stay readable. 0 = unlimited.
        self._max_edges = QSpinBox()
        self._max_edges.setRange(0, 100000)
        self._max_edges.setSingleStep(25)
        self._max_edges.setSpecialValueText("Unlimited")
        self._max_edges.setValue(0)
        self._max_edges.valueChanged.connect(self._on_settings_changed)

        self._node_scale = QDoubleSpinBox()
        self._node_scale.setRange(0.1, 8.0)
        self._node_scale.setSingleStep(0.1)
        self._node_scale.setValue(1.0)
        self._node_scale.valueChanged.connect(self._on_settings_changed)

        self._node_scaling_method = QComboBox()
        self._node_scaling_method.addItems(NODE_SCALING_METHODS)
        self._node_scaling_method.currentIndexChanged.connect(self._on_settings_changed)

        self._min_ew = QDoubleSpinBox()
        self._min_ew.setRange(0.0, 5.0)
        self._min_ew.setSingleStep(0.1)
        self._min_ew.setDecimals(3)
        self._min_ew.setValue(0.001)
        self._min_ew.valueChanged.connect(self._on_edge_width_changed)

        self._max_ew = QDoubleSpinBox()
        self._max_ew.setRange(0.1, 15.0)
        self._max_ew.setSingleStep(0.5)
        self._max_ew.setDecimals(2)
        self._max_ew.setValue(4.0)
        self._max_ew.valueChanged.connect(self._on_edge_width_changed)

        disp_form.addRow("Node layout", self._layout_combo)
        disp_form.addRow("Max edges", self._max_edges)
        disp_form.addRow("Node size scale", self._node_scale)
        disp_form.addRow("Node scaling", self._node_scaling_method)
        disp_form.addRow("Min edge width", self._min_ew)
        disp_form.addRow("Max edge width", self._max_ew)

        self._save_btn = QPushButton("Save plot…")
        self._save_btn.setToolTip("Save the current network plot as a PNG (600 dpi) or SVG file.")
        self._save_btn.clicked.connect(self._on_save_plot)
        disp_form.addRow(self._save_btn)

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
        layout.addWidget(disp_box)
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
        self._source = "mat"
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

        metrics = sorted(data.available_node_metrics)

        # Node SIZE metric — default to node degree (ND) if present, as in MATLAB
        self._node_size_metric.blockSignals(True)
        self._node_size_metric.clear()
        self._node_size_metric.addItems(metrics)
        if "ND" in metrics:
            self._node_size_metric.setCurrentText("ND")
        self._node_size_metric.blockSignals(False)

        # Node COLOR metric (or None for flat cyan)
        self._node_color_metric.blockSignals(True)
        self._node_color_metric.clear()
        self._node_color_metric.addItem("None")
        self._node_color_metric.addItems(metrics)
        self._node_color_metric.blockSignals(False)

        # Enable controls
        self._lag_combo.setEnabled(True)
        self._edge_thresh.setEnabled(True)
        self._node_size_metric.setEnabled(True)
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
        self._refresh_plot()

    def _on_edge_thresh_method_changed(self) -> None:
        """Reconfigure the threshold spinbox to match the selected method."""
        self._edge_thresh.blockSignals(True)
        if self._edge_thresh_method.currentText().startswith("Percentile"):
            self._edge_thresh.setRange(0.0, 100.0)
            self._edge_thresh.setDecimals(1)
            self._edge_thresh.setSingleStep(5.0)
            self._edge_thresh.setSuffix(" %")
            self._edge_thresh.setValue(90.0)
        else:  # Absolute value
            self._edge_thresh.setRange(0.0, 1.0)
            self._edge_thresh.setDecimals(3)
            self._edge_thresh.setSingleStep(0.05)
            self._edge_thresh.setSuffix("")
            self._edge_thresh.setValue(0.0)
        self._edge_thresh.blockSignals(False)
        self._refresh_plot()

    def _on_edge_width_changed(self, _value: float) -> None:
        # Keep max ≥ min so edge widths never invert; then re-render.
        if self._max_ew.value() < self._min_ew.value():
            blocker = self._max_ew if self.sender() is self._min_ew else self._min_ew
            blocker.blockSignals(True)
            if self.sender() is self._min_ew:
                self._max_ew.setValue(self._min_ew.value())
            else:
                self._min_ew.setValue(self._max_ew.value())
            blocker.blockSignals(False)
        self._refresh_plot()

    def _on_save_plot(self) -> None:
        # Suggest a filename from the current recording / example.
        base_name = self._info_fn.text() if self._source == "mat" else "example_network"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in base_name).strip("_")
        default = f"{safe or 'network'}.png"

        path, selected = QFileDialog.getSaveFileName(
            self, "Save network plot", default,
            "PNG image (*.png);;SVG image (*.svg)",
        )
        if not path:
            return

        # Ensure the extension matches the chosen filter if the user omitted one.
        ext = Path(path).suffix.lower()
        if ext not in (".png", ".svg"):
            ext = ".svg" if "svg" in selected.lower() else ".png"
            path = str(Path(path).with_suffix(ext))

        try:
            self._canvas.save_figure(path, dpi=600)
            self._log_msg(f"Saved plot to {path}"
                          + (" (600 dpi)" if ext == ".png" else ""))
        except Exception as exc:
            self._log_msg(f"Save error: {exc}")

    # ── Example network ─────────────────────────────────────────────────────────

    def _load_example_network(self) -> None:
        """Generate the built-in synthetic network and make it the active source."""
        adjM, coords = make_example_network()
        binar = (adjM > 0)
        node_degree = binar.sum(axis=1).astype(float)
        node_strength = adjM.sum(axis=1).astype(float)

        self._example = {
            "adjM": adjM,
            "coords": coords,
            "metrics": {
                "node degree": node_degree,
                "node strength": node_strength,
            },
            "ct_matrix": None,
            "ct_names": None,
            "min_node_size": 0.01,
            "title": "Example synthetic network",
        }
        self._source = "example"
        self._mat_data = None
        self._mat_path.clear()

        self._info_fn.setText("Example network")
        self._info_div.setText("—")
        self._info_grp.setText("—")

        # Lag is meaningless for the example; disable it.
        self._lag_combo.blockSignals(True)
        self._lag_combo.clear()
        self._lag_combo.blockSignals(False)
        self._lag_combo.setEnabled(False)

        metric_names = list(self._example["metrics"].keys())
        self._node_size_metric.blockSignals(True)
        self._node_size_metric.clear()
        self._node_size_metric.addItems(metric_names)
        self._node_size_metric.blockSignals(False)

        self._node_color_metric.blockSignals(True)
        self._node_color_metric.clear()
        self._node_color_metric.addItem("None")
        self._node_color_metric.addItems(metric_names)
        self._node_color_metric.blockSignals(False)

        self._edge_thresh.setEnabled(True)
        self._node_size_metric.setEnabled(True)
        self._node_color_metric.setEnabled(True)
        # Cell types require channel numbers from a real recording.
        self._load_ct_btn.setEnabled(False)
        if self._cell_type_matrix is not None:
            self._on_clear_cell_types()

        self._log_msg("Loaded built-in example network — adjust the Display controls to explore.")
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
        """Build the current network (example or loaded file), apply the display
        controls, and render. Shared by both data sources."""
        if self._source == "mat":
            base = self._mat_base()
        else:
            base = self._example_base()
        if base is None:
            return

        metrics = base["metrics"]

        # Node SIZE metric (falls back to node degree if the selection is gone)
        size_name = self._node_size_metric.currentText()
        z = metrics.get(size_name)
        if z is None:
            size_name = "ND" if "ND" in metrics else next(iter(metrics), None)
            z = metrics.get(size_name) if size_name else None
        if z is None:
            self._log_msg("No node-size metric available for this network.")
            return
        z_name = "node degree" if size_name == "ND" else size_name

        # Node COLOR metric (or None for flat cyan)
        color_metric = self._node_color_metric.currentText()
        z2 = metrics.get(color_metric) if color_metric != "None" else None

        # Edge subsampling (plotting-only): cap to the strongest N edges, then
        # derive the threshold on that limited matrix — mirrors PlotIndvNetMet.m.
        max_edges = self._max_edges.value() or None
        adjM = limit_edges_for_plotting(base["adjM"], max_edges)

        method = self._edge_thresh_method.currentText()
        thresh_val = self._edge_thresh.value()
        is_percentile = method.startswith("Percentile")
        edge_thresh = get_edge_threshold(
            adjM,
            method=method,
            threshold=0.0 if is_percentile else thresh_val,
            percentile=thresh_val if is_percentile else 90.0,
        )

        # Node layout (electrode coords, or derived from the limited topology)
        coords = compute_node_coords(
            adjM, base["coords"], self._layout_combo.currentText()
        )

        self._info_nodes.setText(str(len(adjM)))
        self._info_edges.setText(str(count_edges_shown(adjM, edge_thresh)))

        self._canvas.render(
            adjM, coords, edge_thresh,
            z, z2, color_metric,
            base["ct_matrix"], base["ct_names"],
            base["min_node_size"], base["title"],
            z_name=z_name,
            min_ew=self._min_ew.value(),
            max_ew=self._max_ew.value(),
            node_size_scale=self._node_scale.value(),
            node_scaling_method=self._node_scaling_method.currentText(),
        )

    def _example_base(self) -> dict | None:
        return self._example

    def _mat_base(self) -> dict | None:
        data = self._mat_data
        if data is None or not data.lag_keys:
            return None
        lag_key = self._lag_combo.currentData()
        if not lag_key:
            return None

        adjM_full = data.get_adjM(lag_key)
        active_idx = data.get_active_indices(lag_key)

        # All node-level metrics for this lag, aligned to active_idx order.
        metrics = {
            name: data.get_metric(lag_key, name)
            for name in data.available_node_metrics
        }
        metrics = {k: v for k, v in metrics.items() if v is not None}

        # Cell-type overlay / intersection filter (rows correspond to active_idx)
        ct_matrix_active = None
        ct_names = self._cell_type_names
        keep = np.arange(len(active_idx))

        if self._cell_type_matrix is not None and ct_names is not None:
            ct_matrix_active = self._cell_type_matrix[active_idx, :]
            selected = [item.text() for item in self._ct_list.selectedItems()]
            if selected:
                keep, ct_matrix_active = filter_by_cell_types(
                    keep, ct_matrix_active, ct_names, selected,
                )

        active_idx = active_idx[keep]
        metrics = {name: arr[keep] for name, arr in metrics.items()}

        adjM_sub = adjM_full[np.ix_(active_idx, active_idx)]
        coords_sub = data.coords[active_idx]

        fn = data.info.get("FN", "")
        return {
            "adjM": adjM_sub,
            "coords": coords_sub,
            "metrics": metrics,
            "ct_matrix": ct_matrix_active,
            "ct_names": ct_names,
            "min_node_size": float(data.params.get("minNodeSize", 0.01)),
            "title": f"{fn}  —  {data.lag_ms(lag_key)} ms lag",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, text: str) -> None:
        self._log.append(text)
