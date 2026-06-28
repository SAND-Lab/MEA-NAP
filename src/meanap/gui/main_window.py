"""MEA-NAP main application window."""

import json

from PyQt6.QtWidgets import (
    QFileDialog, QMainWindow, QMessageBox, QScrollArea,
    QTabWidget, QToolBar, QWidget,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from meanap.params import Params
from meanap.gui import theme
from meanap.gui.panels.paths import PathsPanel
from meanap.gui.panels.recording import RecordingPanel
from meanap.gui.panels.spike_detection import SpikeDetectionPanel
from meanap.gui.panels.connectivity import ConnectivityPanel
from meanap.gui.panels.pipeline import PipelinePanel
from meanap.gui.panels.catnap import CatNapPanel


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    return area


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MEA-NAP")
        self.resize(980, 780)

        self._params = Params()
        self._current_theme = "dark"

        self._build_toolbar()
        self._build_tabs()
        self._load_params(self._params)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        act_new = QAction("New", self)
        act_new.setToolTip("Reset all parameters to defaults")
        act_new.triggered.connect(self._on_new)

        act_open = QAction("Open params…", self)
        act_open.setToolTip("Load parameters from a JSON file")
        act_open.triggered.connect(self._on_open)

        act_save = QAction("Save params…", self)
        act_save.setToolTip("Save current parameters to a JSON file")
        act_save.triggered.connect(self._on_save)

        self._act_theme = QAction("☀  Light", self)
        self._act_theme.setToolTip("Toggle light / dark theme")
        self._act_theme.triggered.connect(self._on_toggle_theme)

        tb.addAction(act_new)
        tb.addSeparator()
        tb.addAction(act_open)
        tb.addAction(act_save)
        tb.addSeparator()
        tb.addAction(self._act_theme)

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        self._paths_panel = PathsPanel()
        self._recording_panel = RecordingPanel()
        self._spike_panel = SpikeDetectionPanel()
        self._connectivity_panel = ConnectivityPanel()
        self._catnap_panel = CatNapPanel()
        self._pipeline_panel = PipelinePanel()

        self._tabs.addTab(_scrollable(self._paths_panel), "  Paths  ")
        self._tabs.addTab(_scrollable(self._recording_panel), "  Recording  ")
        self._tabs.addTab(_scrollable(self._spike_panel), "  Spike detection  ")
        self._tabs.addTab(_scrollable(self._connectivity_panel), "  Connectivity  ")
        self._tabs.addTab(self._catnap_panel, "  CAT-NAP (2P)  ")
        self._tabs.addTab(_scrollable(self._pipeline_panel), "  Pipeline  ")

        self._catnap_panel.log_message.connect(self._pipeline_panel.append_log)

        # Mark Run / Stop with object names so QSS can style them distinctly
        self._pipeline_panel.run_btn.setObjectName("primary")
        self._pipeline_panel.stop_btn.setObjectName("danger")
        self._pipeline_panel.run_btn.clicked.connect(self._on_run)
        self._pipeline_panel.stop_btn.clicked.connect(self._on_stop)

        # Mark log widget so the monospace QSS rule applies
        self._pipeline_panel.log.setObjectName("log")
        self._catnap_panel._log.setObjectName("log")

        # Secondary-style buttons in CAT-NAP panel
        self._catnap_panel._scan_btn.setObjectName("secondary")
        self._catnap_panel._denoise_btn.setObjectName("secondary")

    # ── Param sync ────────────────────────────────────────────────────────────

    def _load_params(self, params: Params) -> None:
        self._paths_panel.load(params)
        self._recording_panel.load(params)
        self._spike_panel.load(params)
        self._connectivity_panel.load(params)
        self._catnap_panel.load(params)
        self._pipeline_panel.load(params)

    def _collect_params(self) -> Params:
        params = Params()
        self._paths_panel.save(params)
        self._recording_panel.save(params)
        self._spike_panel.save(params)
        self._connectivity_panel.save(params)
        self._catnap_panel.save(params)
        self._pipeline_panel.save(params)
        return params

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_toggle_theme(self) -> None:
        self._current_theme = theme.toggle(self._current_theme)
        theme.reapply(self._current_theme)
        self._act_theme.setText("☀  Light" if self._current_theme == "dark" else "🌙  Dark")

    def _on_new(self) -> None:
        if QMessageBox.question(
            self, "New parameters",
            "Reset all parameters to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._params = Params()
            self._load_params(self._params)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open parameters", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            params = Params(**{k: v for k, v in data.items() if hasattr(Params, k)})
            self._params = params
            self._load_params(self._params)
            self._pipeline_panel.append_log(f"Loaded parameters from {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error loading parameters", str(e))

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save parameters", "meanap_params.json", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            import dataclasses
            params = self._collect_params()
            with open(path, "w") as f:
                json.dump(dataclasses.asdict(params), f, indent=2)
            self._pipeline_panel.append_log(f"Saved parameters to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error saving parameters", str(e))

    # ── Pipeline run / stop ───────────────────────────────────────────────────

    def _on_run(self) -> None:
        params = self._collect_params()
        self._params = params

        missing = []
        if not params.home_dir:
            missing.append("MEA-NAP folder")
        if not params.raw_data and not params.prior_analysis:
            missing.append("Raw data folder")
        if not params.output_data_folder:
            missing.append("Output data folder")

        if missing:
            QMessageBox.warning(
                self, "Missing paths",
                "Please fill in the following required paths before running:\n\n• "
                + "\n• ".join(missing),
            )
            self._tabs.setCurrentIndex(0)
            return

        self._pipeline_panel.run_btn.setEnabled(False)
        self._pipeline_panel.stop_btn.setEnabled(True)
        self._pipeline_panel.append_log(
            f"Starting MEA-NAP from step {params.start_analysis_step}…"
        )
        # TODO: launch pipeline worker thread here

    def _on_stop(self) -> None:
        self._pipeline_panel.append_log("Stop requested.")
        self._pipeline_panel.run_btn.setEnabled(True)
        self._pipeline_panel.stop_btn.setEnabled(False)
        # TODO: signal worker thread to stop
