"""MEA-NAP main application window."""

import json
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QScrollArea,
    QTabWidget, QToolBar, QWidget,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QSettings

from meanap.params import Params
from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.report import generate_report
from meanap.gui import theme
from meanap.gui.pipeline_worker import PipelineWorker
from meanap.gui.panels.paths import PathsPanel
from meanap.gui.panels.recording import RecordingPanel
from meanap.gui.panels.spike_detection import SpikeDetectionPanel
from meanap.gui.panels.connectivity import ConnectivityPanel
from meanap.gui.panels.stim import StimPanel
from meanap.gui.panels.stim_preview import StimPreviewPanel
from meanap.gui.panels.pipeline import PipelinePanel
from meanap.gui.panels.catnap import CatNapPanel
from meanap.gui.panels.network_viewer import NetworkViewerPanel
from meanap.gui.tutorial import TutorialOverlay, TutorialStep, tabbar_target


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
        self._last_output_root: Path | None = None
        self._current_theme = "dark"
        self._worker: PipelineWorker | None = None
        self._tutorial: TutorialOverlay | None = None

        self._build_toolbar()
        self._build_tabs()
        self._load_params(self._params)
        self._maybe_show_tutorial_on_first_launch()

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

        act_tutorial = QAction("?  Tutorial", self)
        act_tutorial.setToolTip("Launch the guided tutorial")
        act_tutorial.triggered.connect(self._start_tutorial)

        tb.addAction(act_new)
        tb.addSeparator()
        tb.addAction(act_open)
        tb.addAction(act_save)
        tb.addSeparator()
        tb.addAction(self._act_theme)
        tb.addAction(act_tutorial)

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        self._paths_panel = PathsPanel()
        self._recording_panel = RecordingPanel()
        self._spike_panel = SpikeDetectionPanel()
        self._connectivity_panel = ConnectivityPanel()
        self._stim_panel = StimPanel()
        self._stim_preview_panel = StimPreviewPanel()
        self._catnap_panel = CatNapPanel()
        self._pipeline_panel = PipelinePanel()
        self._network_viewer_panel = NetworkViewerPanel()

        self._tab_paths = self._tabs.addTab(_scrollable(self._paths_panel), "  Paths  ")
        self._tab_recording = self._tabs.addTab(_scrollable(self._recording_panel), "  Recording  ")
        self._tab_spike = self._tabs.addTab(_scrollable(self._spike_panel), "  Spike detection  ")
        self._tab_connectivity = self._tabs.addTab(_scrollable(self._connectivity_panel), "  Connectivity  ")
        self._tab_stim = self._tabs.addTab(_scrollable(self._stim_panel), "  Stimulation  ")
        self._tab_stim_preview = self._tabs.addTab(self._stim_preview_panel, "  Stim Preview  ")
        self._tab_catnap = self._tabs.addTab(self._catnap_panel, "  CAT-NAP (2P)  ")
        self._tab_network = self._tabs.addTab(self._network_viewer_panel, "  Network Viewer  ")
        self._pipeline_tab_index = self._tabs.addTab(_scrollable(self._pipeline_panel), "  Pipeline  ")

        self._catnap_panel.log_message.connect(self._pipeline_panel.append_log)

        # Mark Run / Stop with object names so QSS can style them distinctly
        self._pipeline_panel.run_btn.setObjectName("primary")
        self._pipeline_panel.stop_btn.setObjectName("danger")
        self._pipeline_panel.test_btn.setObjectName("secondary")
        self._pipeline_panel.view_report_btn.setObjectName("secondary")
        self._pipeline_panel.run_btn.clicked.connect(self._on_run)
        self._pipeline_panel.stop_btn.clicked.connect(self._on_stop)
        self._pipeline_panel.test_btn.clicked.connect(self._on_test_pipeline)
        self._pipeline_panel.view_report_btn.clicked.connect(self._on_view_report)

        # Mark log widget so the monospace QSS rule applies
        self._pipeline_panel.log.setObjectName("log")
        self._catnap_panel._log.setObjectName("log")

        # Secondary-style buttons in CAT-NAP panel
        self._catnap_panel._scan_btn.setObjectName("secondary")
        self._catnap_panel._denoise_btn.setObjectName("secondary")

    # ── Tutorial ──────────────────────────────────────────────────────────────

    def _maybe_show_tutorial_on_first_launch(self) -> None:
        settings = QSettings("SAND Lab", "MEA-NAP")
        if not settings.value("tutorial/seen", False, type=bool):
            self._start_tutorial()

    def _start_tutorial(self) -> None:
        if self._tutorial is None:
            self._tutorial = TutorialOverlay(self, self._tabs)
            self._tutorial.pipeline_chosen.connect(self._on_pipeline_chosen)
            self._tutorial.finished.connect(self._on_tutorial_finished)
        self._tutorial.start()

    def _on_pipeline_chosen(self, kind: str) -> None:
        builders = {
            "meanap": self._build_meanap_steps,
            "meastim": self._build_meastim_steps,
            "catnap": self._build_catnap_steps,
        }
        steps = builders[kind]()
        assert self._tutorial is not None
        self._tutorial.set_steps(steps)
        self._tutorial.begin_steps()

    def _on_tutorial_finished(self) -> None:
        QSettings("SAND Lab", "MEA-NAP").setValue("tutorial/seen", True)

    def _build_meanap_steps(self) -> list[TutorialStep]:
        paths = self._paths_panel
        rec = self._recording_panel
        spike = self._spike_panel
        conn = self._connectivity_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Raw data folder", "The MEA-NAP pipeline starts on the Paths tab. "
                "First, choose the folder holding your recordings "
                "(.mat files, one per recording).",
                self._tab_paths, lambda: paths.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX that lists each recording, "
                "its group and its age (DIV). This drives the whole batch.",
                self._tab_paths, lambda: paths.spreadsheet),
            TutorialStep(
                "Spreadsheet range", "The cell range to read from the spreadsheet, "
                "e.g. A2:A100000 to read every row after the header.",
                self._tab_paths, lambda: paths.spreadsheet_range),
            TutorialStep(
                "Where results go", "Set the output folder and give this analysis run "
                "a name — a subfolder with that name will hold all results and plots.",
                self._tab_paths, lambda: paths.output_data_folder),
            TutorialStep(
                "Recording settings", "On the Recording tab, set the sampling frequency "
                "of your acquisition (Hz) so spike detection and downsampling are correct.",
                self._tab_recording, lambda: rec.fs),
            TutorialStep(
                "Channel layout", "Pick the MEA layout that matches your hardware "
                "(MCS60, Axion64, …). This maps channels to electrode positions.",
                self._tab_recording, lambda: rec.channel_layout),
            TutorialStep(
                "Spike detection", "Step 1 detects spikes. Leave 'Detect spikes' ticked "
                "for a fresh run; untick it if you already have detected spike data.",
                self._tab_spike, lambda: spike.detect_spikes),
            TutorialStep(
                "Detection thresholds", "These MAD multipliers set how far below the "
                "median a deflection must go to count as a spike. 3, 4, 5 is a good start.",
                self._tab_spike, lambda: spike.thresholds),
            TutorialStep(
                "Connectivity lags", "Step 3 builds functional networks with the spike "
                "time tiling coefficient. These lag values (ms) set the coincidence window.",
                self._tab_connectivity, lambda: conn.lag_vals),
            TutorialStep(
                "Choose the steps", "On the Pipeline tab, pick which steps to run "
                "(1–4). The default runs the whole pipeline end to end.",
                self._pipeline_tab_index, lambda: pipe.start_step),
            TutorialStep(
                "Try it first", "Not sure your setup works? 'Test pipeline' downloads a "
                "small example dataset and runs all four steps on it.",
                self._pipeline_tab_index, lambda: pipe.test_btn),
            TutorialStep(
                "Run the pipeline", "When your paths are filled in, press Run. Progress "
                "appears in the status log, and 'View report' opens the results in your browser.",
                self._pipeline_tab_index, lambda: pipe.run_btn),
        ]

    def _build_meastim_steps(self) -> list[TutorialStep]:
        paths = self._paths_panel
        stim = self._stim_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Raw data folder", "MEA-Stim reuses the same Paths tab. Start by choosing "
                "the folder with your stimulation recordings.",
                self._tab_paths, lambda: paths.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX listing each recording, "
                "its group and DIV.",
                self._tab_paths, lambda: paths.spreadsheet),
            TutorialStep(
                "Where results go", "Set the output folder and a name for this run's "
                "results subfolder.",
                self._tab_paths, lambda: paths.output_data_folder),
            TutorialStep(
                "Turn on MEA-Stim", "On the Stimulation tab, tick this to run the "
                "stimulation analysis after spike detection.",
                self._tab_stim, lambda: stim.stim_mode),
            TutorialStep(
                "Detection method", "Choose how stimulation artefacts are found. "
                "'longblank' and 'blanking' suit blanked recordings; the threshold "
                "methods detect by amplitude; 'axionStimEvents' reads an Axion CSV.",
                self._tab_stim, lambda: stim.method),
            TutorialStep(
                "Analysis window", "Set the window around each stimulus (seconds) over "
                "which evoked responses are measured — e.g. −0.03 to 0.03 s.",
                self._tab_stim, lambda: stim.win_start),
            TutorialStep(
                "Significance test", "Responses are tested against shuffled surrogates. "
                "More shuffles give a tighter p-value but take longer; 500 is a good default.",
                self._tab_stim, lambda: stim.n_shuffles),
            TutorialStep(
                "Preview detection", "The Stim Preview tab lets you check the detected "
                "stimulus times on an example recording before running the full batch.",
                self._tab_stim_preview, tabbar_target(self._tabs, self._tab_stim_preview)),
            TutorialStep(
                "Run the pipeline", "On the Pipeline tab, press Run. Spike detection runs "
                "first, then the stimulation analysis and its plots.",
                self._pipeline_tab_index, lambda: pipe.run_btn),
        ]

    def _build_catnap_steps(self) -> list[TutorialStep]:
        cat = self._catnap_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Turn on CAT-NAP", "CAT-NAP analyses two-photon calcium imaging. On the "
                "CAT-NAP tab, tick this to analyse suite2p output instead of MEA data.",
                self._tab_catnap, lambda: cat._suite2p_mode),
            TutorialStep(
                "suite2p folder", "Point this to the parent folder containing your "
                "suite2p output (the plane0 folders live beneath it).",
                self._tab_catnap, lambda: cat._folder_edit),
            TutorialStep(
                "Scan for recordings", "Press this to find every suite2p recording under "
                "that folder. Select one to preview its traces.",
                self._tab_catnap, lambda: cat._scan_btn),
            TutorialStep(
                "Denoising", "Optionally denoise the fluorescence traces before analysis. "
                "The threshold multiplier and peak windows control event extraction.",
                self._tab_catnap, lambda: cat._denoise_btn),
            TutorialStep(
                "Run the pipeline", "With CAT-NAP mode on and a folder selected, go to "
                "the Pipeline tab and press Run to analyse the imaging data.",
                self._pipeline_tab_index, lambda: pipe.run_btn),
        ]

    # ── Param sync ────────────────────────────────────────────────────────────

    def _load_params(self, params: Params) -> None:
        self._paths_panel.load(params)
        self._recording_panel.load(params)
        self._spike_panel.load(params)
        self._connectivity_panel.load(params)
        self._stim_panel.load(params)
        self._stim_preview_panel.load_defaults(params)  # preview-only: no save/collect
        self._catnap_panel.load(params)
        self._pipeline_panel.load(params)

    def _collect_params(self) -> Params:
        params = Params()
        self._paths_panel.save(params)
        self._recording_panel.save(params)
        self._spike_panel.save(params)
        self._connectivity_panel.save(params)
        self._stim_panel.save(params)
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

    def _on_test_pipeline(self) -> None:
        # The test run needs somewhere to put the example data and its output.
        # Default the output folder to ~/MEA-NAP when it hasn't been set.
        out_folder = self._paths_panel.output_data_folder.value
        if not out_folder:
            out_folder = str(Path.home() / "MEA-NAP")
            self._paths_panel.output_data_folder.set_value(out_folder)

        self._tabs.setCurrentIndex(self._pipeline_tab_index)
        self._pipeline_panel.append_log("Downloading example data for pipeline test…")
        QApplication.processEvents()

        def log(message: str) -> None:
            self._pipeline_panel.append_log(message)
            QApplication.processEvents()

        try:
            example_dir = download_example_data(Path(out_folder), log=log)
        except Exception as e:
            QMessageBox.critical(self, "Download failed", str(e))
            return

        # Point the paths panel at the example dataset, mirroring the MATLAB
        # TestPipelineButton behaviour (downloadExampleData + settings override).
        self._paths_panel.raw_data.set_value(str(example_dir))
        self._paths_panel.spreadsheet.set_value(str(example_dir / "exampleData.csv"))
        self._paths_panel.spreadsheet_range.setText("A2:A3")
        try:
            from meanap.pipeline.spreadsheet import read_recording_csv
            recordings = read_recording_csv(example_dir / "exampleData.csv", "A2:A3")
            # Preserve order of first appearance
            unique_grps = list(dict.fromkeys(r.group for r in recordings))
            self._paths_panel.custom_grp_order.setText(",".join(unique_grps))
        except Exception as e:
            log(f"Warning: could not parse custom group order from exampleData.csv: {e}")

        # The test run verifies that the full pipeline (steps 1-4) works.
        self._pipeline_panel.start_step.setValue(1)
        self._pipeline_panel.stop_step.setValue(4)

        self._pipeline_panel.append_log("Example data ready — running full pipeline (steps 1-4).")
        self._on_run()

    def _on_run(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # a run is already in progress

        params = self._collect_params()
        self._params = params

        missing = []
        if not params.raw_data and not params.prior_analysis:
            missing.append("Raw data folder")
        if not params.output_data_folder:
            missing.append("Output data folder")
        if not params.spreadsheet_file_name:
            missing.append("Spreadsheet file")

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
            f"Starting MEA-NAP: steps {params.start_analysis_step}-{params.stop_analysis_step}…"
        )

        worker = PipelineWorker(params, parent=self)
        worker.log_message.connect(self._pipeline_panel.append_log)
        worker.finished_ok.connect(self._on_pipeline_finished)
        worker.cancelled.connect(self._on_pipeline_cancelled)
        worker.failed.connect(self._on_pipeline_failed)
        self._worker = worker
        worker.start()

    def _on_stop(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._pipeline_panel.append_log(
                "Stop requested — finishing the current recording, then halting…"
            )
            self._pipeline_panel.stop_btn.setEnabled(False)
            self._worker.request_cancel()
        else:
            self._pipeline_panel.stop_btn.setEnabled(False)

    def _reset_run_buttons(self) -> None:
        self._pipeline_panel.run_btn.setEnabled(True)
        self._pipeline_panel.stop_btn.setEnabled(False)
        self._worker = None

    def _on_pipeline_finished(self, output_root: Path) -> None:
        self._last_output_root = output_root
        self._pipeline_panel.append_log(f"Done. Output folder: {output_root}")
        self._reset_run_buttons()

    def _on_pipeline_cancelled(self) -> None:
        self._pipeline_panel.append_log("Pipeline stopped.")
        self._reset_run_buttons()

    def _on_pipeline_failed(self, message: str) -> None:
        self._pipeline_panel.append_log(f"ERROR: {message}")
        self._reset_run_buttons()
        QMessageBox.critical(self, "Pipeline error", message)

    def _on_view_report(self) -> None:
        output_root = self._last_output_root
        if output_root is None:
            params = self._collect_params()
            if params.output_data_folder and params.output_data_folder_name:
                output_root = Path(params.output_data_folder) / params.output_data_folder_name

        if output_root is None or not output_root.is_dir():
            QMessageBox.warning(
                self, "No output folder found",
                "Run the pipeline first, or set the Output data folder / name "
                "(Paths tab) to an existing MEA-NAP output folder.",
            )
            return

        try:
            report_path = generate_report(output_root)
        except Exception as e:
            QMessageBox.critical(self, "Report generation failed", str(e))
            return

        self._pipeline_panel.append_log(f"Report generated: {report_path}")
        webbrowser.open(report_path.as_uri())

    def closeEvent(self, event) -> None:
        # A running QThread destroyed with its parent crashes Qt; ask the
        # pipeline to stop and give it a moment to reach a cancel checkpoint.
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(5000)
        super().closeEvent(event)
