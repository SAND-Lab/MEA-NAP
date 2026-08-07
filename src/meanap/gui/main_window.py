"""MEA-NAP main application window."""

import json
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QLineEdit, QScrollArea, QSizePolicy, QTabWidget, QToolBar, QWidget,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QSettings, QSignalBlocker

from meanap.params import Params
from meanap.pipeline.bundle import BUNDLE_SUFFIX
from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.report import generate_report
from meanap.gui import theme
from meanap.gui.branding import logo_icon, logo_pixmap
from meanap.gui.modes import (
    DEFAULT_MODE, MODES, TAB_CATNAP, TAB_CONNECTIVITY, TAB_NETWORK, TAB_PATHS,
    TAB_PIPELINE, TAB_RECORDING, TAB_SPIKE, TAB_STIM, TAB_STIM_PREVIEW,
    apply_mode_to_params, mode_for_params,
)
from meanap.gui.pipeline_worker import PipelineWorker
from meanap.gui.viewer_session import ViewerSessions
from meanap.gui.panels.paths import PathsPanel
from meanap.gui.panels.recording import RecordingPanel
from meanap.gui.panels.spike_detection import SpikeDetectionPanel
from meanap.gui.panels.connectivity import ConnectivityPanel
from meanap.gui.panels.stim import StimPanel
from meanap.gui.panels.stim_preview import StimPreviewPanel
from meanap.gui.panels.pipeline import PipelinePanel
from meanap.gui.panels.catnap import CatNapPanel
from meanap.gui.panels.network_viewer import NetworkViewerPanel
from meanap.gui.tooltip import install_tooltip_style, wrap_tooltips
from meanap.gui.tutorial import TutorialOverlay, TutorialStep, tabbar_target


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    return area


class MainWindow(QMainWindow):
    def __init__(self, mode: str = DEFAULT_MODE) -> None:
        super().__init__()
        if mode not in MODES:
            raise ValueError(
                f"Unknown mode {mode!r} (expected one of: {', '.join(MODES)})"
            )
        self._mode = mode
        self._mode_combo: QComboBox | None = None
        self.setWindowTitle("MEA-NAP")
        # Also set in app.main() so dialogs inherit it; repeated here so the
        # window is branded however it was constructed (tests, embedding, …).
        self.setWindowIcon(logo_icon())
        self.resize(980, 780)

        self._params = Params()
        # Stamp the launch mode onto the defaults before anything reads them:
        # _load_params derives the mode from these flags, so leaving them unset
        # would snap a "--mode catnap" launch straight back to the ephys tabs.
        apply_mode_to_params(mode, self._params)
        self._last_output_root: Path | None = None
        self._last_bundle: Path | None = None
        self._current_theme = "dark"
        self._worker: PipelineWorker | None = None
        self._tutorial: TutorialOverlay | None = None
        self._viewers = ViewerSessions()

        # A bundle is a file people email each other, so dropping one on the
        # window is the obvious way to open it. Accepted at the window level;
        # see dragEnterEvent for why nothing else is claimed.
        self.setAcceptDrops(True)

        self._build_toolbar()
        self._build_tabs()
        self._load_params(self._params)
        # Wrap every tooltip in one pass, once the whole UI exists. Doing it
        # here rather than at each call site means a tooltip written anywhere
        # is formatted without its author having to remember — Qt otherwise
        # lays a long one out on a single line, wider than the screen.
        install_tooltip_style()
        wrap_tooltips(self)
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

        act_bundle = QAction("Open bundle…", self)
        act_bundle.setToolTip(
            "Open a .meanap run bundle — from an express run of your own, or "
            "one someone sent you — and draw any of its figures in the viewer. "
            "You can also drag the file onto this window."
        )
        act_bundle.triggered.connect(self._on_open_bundle)

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
        tb.addAction(act_bundle)
        tb.addSeparator()
        tb.addAction(self._act_theme)
        tb.addAction(act_tutorial)
        tb.addSeparator()

        # Mode selector: switching it re-tabs the window for that pipeline.
        tb.addWidget(QLabel("  Mode "))
        self._mode_combo = QComboBox()
        for key, mode in MODES.items():
            self._mode_combo.addItem(mode.label, key)
        self._mode_combo.setCurrentIndex(self._mode_combo.findData(self._mode))
        self._mode_combo.setToolTip(MODES[self._mode].blurb)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tb.addWidget(self._mode_combo)

        # Logo sits at the far right, past a stretch, so it reads as branding
        # rather than competing with the actions for the eye.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        pixmap = logo_pixmap(32, self.devicePixelRatioF())
        if pixmap is not None:
            logo = QLabel()
            logo.setPixmap(pixmap)
            logo.setContentsMargins(0, 0, 10, 0)
            logo.setToolTip("MEA-NAP — MEA Network Analysis Pipeline")
            tb.addWidget(logo)

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

        # Every tab is built once and kept alive here; the current mode decides
        # which of them are actually in the QTabWidget (see _apply_mode). Order
        # is the order they appear in, whichever subset is showing.
        self._tab_specs: list[tuple[str, QWidget, str]] = [
            (TAB_PATHS, _scrollable(self._paths_panel), "  Paths  "),
            (TAB_RECORDING, _scrollable(self._recording_panel), "  Recording  "),
            (TAB_SPIKE, _scrollable(self._spike_panel), "  Spike detection  "),
            (TAB_CONNECTIVITY, _scrollable(self._connectivity_panel), "  Connectivity  "),
            (TAB_STIM, _scrollable(self._stim_panel), "  Stimulation  "),
            (TAB_STIM_PREVIEW, self._stim_preview_panel, "  Stim Preview  "),
            (TAB_CATNAP, self._catnap_panel, "  CAT-NAP (2P)  "),
            (TAB_NETWORK, self._network_viewer_panel, "  Network Viewer  "),
            (TAB_PIPELINE, _scrollable(self._pipeline_panel), "  Pipeline  "),
        ]
        self._apply_mode(self._mode, sync_params=False)

        self._catnap_panel.log_message.connect(self._pipeline_panel.append_log)

        # The Paths "Raw data folder" and the CAT-NAP "Recordings folder" are
        # two views of one setting (Params.raw_data), and both panels write it
        # in _collect_params — so whichever saves last silently wins. Mirror
        # them instead. Without this, setting the folder on Paths and pressing
        # Run reports it missing, because the empty CAT-NAP field overwrites it.
        self._bind_mirrored(
            self._paths_panel.raw_data.line_edit, self._catnap_panel._folder_edit
        )

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

        # QTextEdit accepts drops even when read-only, and a child that accepts
        # a drag stops it reaching the window — so a bundle dropped on the
        # status log, the largest target on the Pipeline tab, would do nothing.
        self._pipeline_panel.log.setAcceptDrops(False)
        self._catnap_panel._log.setAcceptDrops(False)

        # A spreadsheet built from a scan describes the recordings the run is
        # about to read, so point the run at it rather than leaving the user to
        # copy the path across tabs.
        self._catnap_panel.spreadsheet_saved.connect(
            self._paths_panel.spreadsheet.set_value)

        # Secondary-style buttons in CAT-NAP panel
        self._catnap_panel._scan_btn.setObjectName("secondary")
        self._catnap_panel._denoise_btn.setObjectName("secondary")
        self._catnap_panel._make_sheet_btn.setObjectName("secondary")
        self._paths_panel.edit_spreadsheet_btn.setObjectName("secondary")

    @staticmethod
    def _bind_mirrored(first: QLineEdit, second: QLineEdit) -> None:
        """Keep two line edits showing the same text, in both directions."""

        def sync(source: QLineEdit, target: QLineEdit) -> None:
            def handler(text: str) -> None:
                if target.text() != text:
                    with QSignalBlocker(target):
                        target.setText(text)
            return handler

        first.textChanged.connect(sync(first, second))
        second.textChanged.connect(sync(second, first))
        second.setText(first.text())

    # ── Modes ─────────────────────────────────────────────────────────────────

    def _apply_mode(self, mode_key: str, *, sync_params: bool = True) -> None:
        """Show exactly the tabs *mode_key* needs, keeping the rest alive.

        QTabWidget has no "hide tab", so switching modes means rebuilding the
        tab strip. The pages themselves are never destroyed, so anything a user
        typed into a tab that is currently hidden is still there when the mode
        brings it back.
        """
        mode = MODES[mode_key]
        self._mode = mode_key

        keep = self._current_tab_key()
        self._tabs.blockSignals(True)
        while self._tabs.count():
            self._tabs.removeTab(0)
        # removeTab() leaves the page parented to the tab widget's stack but
        # does not hide it, so without this the hidden pages paint themselves
        # over the window as free-floating children.
        for _, widget, _ in self._tab_specs:
            widget.hide()
        for key, widget, label in self._tab_specs:
            if key in mode.tabs:
                self._tabs.addTab(widget, label)
        self._tabs.blockSignals(False)

        # Stay on the same tab across the switch when that tab still exists,
        # rather than dumping the user back on Paths every time.
        index = self._tab_index(keep) if keep else -1
        self._tabs.setCurrentIndex(index if index >= 0 else 0)

        if sync_params:
            # Read the panels back before touching the flags, so reloading the
            # two mode-flag panels can't overwrite edits with stale values, and
            # so a run started right after a switch does what the tabs show.
            params = self._collect_params()
            apply_mode_to_params(mode_key, params)
            self._params = params
            self._stim_panel.load(params)
            self._catnap_panel.load(params)

        if getattr(self, "_mode_combo", None) is not None:
            with QSignalBlocker(self._mode_combo):
                self._mode_combo.setCurrentIndex(self._mode_combo.findData(mode_key))
            self._mode_combo.setToolTip(mode.blurb)

    def _tab_index(self, key: str) -> int:
        """Current index of tab *key*, or -1 when this mode hides it."""
        for spec_key, widget, _ in self._tab_specs:
            if spec_key == key:
                return self._tabs.indexOf(widget)
        return -1

    def _current_tab_key(self) -> str | None:
        current = self._tabs.currentWidget()
        for key, widget, _ in self._tab_specs:
            if widget is current:
                return key
        return None

    def _on_mode_changed(self, index: int) -> None:
        key = self._mode_combo.itemData(index)
        if key and key != self._mode:
            self._apply_mode(key)

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
        # Picking a pipeline in the tutorial is the same choice as the Mode
        # selector, so make it one: switch first, then build the steps, whose
        # tab indices are resolved against the tabs this mode shows.
        if kind != self._mode:
            self._apply_mode(kind)

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
                "Choose the folder holding your recordings. No conversion needed: "
                "Multi Channel Systems .h5 and Axion .raw are read as they come off "
                "the recorder, alongside .mat files from the MATLAB converters.",
                self._tab_index(TAB_PATHS), lambda: paths.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX that lists each recording, "
                "its group and its age (DIV). This drives the whole batch. Name recordings "
                "without the file extension. An Axion .raw holds a whole plate, so name "
                "one row per well — 'Plate2_DIV75_A1' — exactly as the MATLAB converter "
                "would have named the file it wrote. No spreadsheet yet? “Edit…” "
                "builds one here and checks it as you type.",
                self._tab_index(TAB_PATHS), lambda: paths.spreadsheet),
            TutorialStep(
                "Spreadsheet range", "The cell range to read from the spreadsheet, "
                "e.g. A2:A100000 to read every row after the header.",
                self._tab_index(TAB_PATHS), lambda: paths.spreadsheet_range),
            TutorialStep(
                "Where results go", "Set the output folder and give this analysis run "
                "a name — a subfolder with that name will hold all results and plots.",
                self._tab_index(TAB_PATHS), lambda: paths.output_data_folder),
            TutorialStep(
                "Recording settings", "On the Recording tab, set the sampling frequency "
                "of your acquisition (Hz) so spike detection and downsampling are correct.",
                self._tab_index(TAB_RECORDING), lambda: rec.fs),
            TutorialStep(
                "Voltage units", "Set this to the units your recordings are in — µV for "
                "Multi Channel Systems, V for Axion. Getting it wrong scales every "
                "amplitude, so spike detection thresholds land in the wrong place.",
                self._tab_index(TAB_RECORDING), lambda: rec.potential_difference_unit),
            TutorialStep(
                "Channel layout", "Pick the MEA layout that matches your hardware: MCS60 "
                "for a 60-electrode MCS array, Axion64 for 6-well Axion plates, Axion16 "
                "for 24-well plates (16 electrodes per well). This maps channels to "
                "electrode positions.",
                self._tab_index(TAB_RECORDING), lambda: rec.channel_layout),
            TutorialStep(
                "Spike detection", "Step 1 detects spikes. Leave 'Detect spikes' ticked "
                "for a fresh run; untick it if you already have detected spike data.",
                self._tab_index(TAB_SPIKE), lambda: spike.detect_spikes),
            TutorialStep(
                "Detection thresholds", "These MAD multipliers set how far below the "
                "median a deflection must go to count as a spike. 3, 4, 5 is a good start.",
                self._tab_index(TAB_SPIKE), lambda: spike.thresholds),
            TutorialStep(
                "Connectivity lags", "Step 3 builds functional networks with the spike "
                "time tiling coefficient. These lag values (ms) set the coincidence window.",
                self._tab_index(TAB_CONNECTIVITY), lambda: conn.lag_vals),
            TutorialStep(
                "Choose the steps", "On the Pipeline tab, pick which steps to run "
                "(1–4). The default runs the whole pipeline end to end.",
                self._tab_index(TAB_PIPELINE), lambda: pipe.start_step),
            TutorialStep(
                "Try it first", "Not sure your setup works? 'Test pipeline' downloads a "
                "small example dataset and runs all four steps on it.",
                self._tab_index(TAB_PIPELINE), lambda: pipe.test_btn),
            TutorialStep(
                "Run the pipeline", "When your paths are filled in, press Run. Progress "
                "appears in the status log, and 'View report' opens the results in your browser.",
                self._tab_index(TAB_PIPELINE), lambda: pipe.run_btn),
        ]

    def _build_meastim_steps(self) -> list[TutorialStep]:
        paths = self._paths_panel
        stim = self._stim_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Raw data folder", "MEA-Stim reuses the same Paths tab. Choose the folder "
                "with your stimulation recordings — .mat, Multi Channel Systems .h5 or "
                "Axion .raw, no conversion needed.",
                self._tab_index(TAB_PATHS), lambda: paths.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX listing each recording, "
                "its group and DIV.",
                self._tab_index(TAB_PATHS), lambda: paths.spreadsheet),
            TutorialStep(
                "Where results go", "Set the output folder and a name for this run's "
                "results subfolder.",
                self._tab_index(TAB_PATHS), lambda: paths.output_data_folder),
            TutorialStep(
                "Turn on MEA-Stim", "On the Stimulation tab, tick this to run the "
                "stimulation analysis after spike detection.",
                self._tab_index(TAB_STIM), lambda: stim.stim_mode),
            TutorialStep(
                "Detection method", "Choose how stimulation artefacts are found. "
                "'longblank' and 'blanking' suit blanked recordings; the threshold "
                "methods detect by amplitude; 'axionStimEvents' reads an Axion CSV.",
                self._tab_index(TAB_STIM), lambda: stim.method),
            TutorialStep(
                "Analysis window", "Set the window around each stimulus (seconds) over "
                "which evoked responses are measured — e.g. −0.03 to 0.03 s.",
                self._tab_index(TAB_STIM), lambda: stim.win_start),
            TutorialStep(
                "Significance test", "Responses are tested against shuffled surrogates. "
                "More shuffles give a tighter p-value but take longer; 500 is a good default.",
                self._tab_index(TAB_STIM), lambda: stim.n_shuffles),
            TutorialStep(
                "Preview detection", "The Stim Preview tab lets you check the detected "
                "stimulus times on an example recording before running the full batch.",
                self._tab_index(TAB_STIM_PREVIEW),
                tabbar_target(self._tabs, self._tab_index(TAB_STIM_PREVIEW))),
            TutorialStep(
                "Run the pipeline", "On the Pipeline tab, press Run. Spike detection runs "
                "first, then the stimulation analysis and its plots.",
                self._tab_index(TAB_PIPELINE), lambda: pipe.run_btn),
        ]

    def _build_catnap_steps(self) -> list[TutorialStep]:
        cat = self._catnap_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Turn on CAT-NAP", "CAT-NAP analyses two-photon calcium imaging. On the "
                "CAT-NAP tab, tick this to analyse suite2p output instead of MEA data.",
                self._tab_index(TAB_CATNAP), lambda: cat._suite2p_mode),
            TutorialStep(
                "Recordings folder", "Point this at the folder holding all your "
                "recordings — not at a single recording's folder. Each sub-folder's "
                "name becomes that recording's name. A Dropbox folder share link "
                "works here too: it is scanned without downloading anything, and "
                "the run fetches one recording at a time.",
                self._tab_index(TAB_CATNAP), lambda: cat._folder_edit,
                diagram="my_experiment/       ← pick this\n"
                        "├── slice1_DIV14/    ← not this\n"
                        "│   └── suite2p/plane0/\n"
                        "├── slice2_DIV14/\n"
                        "│   └── suite2p/plane0/\n"
                        "└── slice3_DIV21/\n"
                        "    └── suite2p/plane0/"),
            TutorialStep(
                "Scan for recordings", "Press this to find every suite2p recording under "
                "that folder. Select one to preview its traces.",
                self._tab_index(TAB_CATNAP), lambda: cat._scan_btn),
            TutorialStep(
                "Build the spreadsheet", "This turns the recordings found above into "
                "the batch spreadsheet, with the names taken from the data rather "
                "than retyped, and the DIV read out of each name. Fill in the "
                "genotype/group column, save, and the Paths tab points at it.",
                self._tab_index(TAB_CATNAP), lambda: cat._make_sheet_btn),
            TutorialStep(
                "Denoising", "Optionally denoise the fluorescence traces before analysis. "
                "The threshold multiplier and peak windows control event extraction.",
                self._tab_index(TAB_CATNAP), lambda: cat._denoise_btn),
            TutorialStep(
                "Run the pipeline", "With CAT-NAP mode on and a folder selected, go to "
                "the Pipeline tab and press Run to analyse the imaging data.",
                self._tab_index(TAB_PIPELINE), lambda: pipe.run_btn),
        ]

    # ── Param sync ────────────────────────────────────────────────────────────

    def _load_params(self, params: Params) -> None:
        # A parameter file carries the pipeline it was written for, so follow
        # it — otherwise opening a CAT-NAP config would leave the window showing
        # ephys tabs while the run does 2P.
        wanted = mode_for_params(params)
        if wanted != self._mode:
            self._apply_mode(wanted, sync_params=False)

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

        self._tabs.setCurrentIndex(self._tab_index(TAB_PIPELINE))
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
        # Only step 1 reads the raw recordings; later steps work from the spike
        # files, so a resumed run doesn't need the raw data mounted at all.
        if not params.raw_data and params.start_analysis_step == 1:
            missing.append("Raw data folder (needed for step 1 — spike detection)")
        if not params.output_data_folder:
            missing.append("Output data folder")
        if not params.spreadsheet_file_name:
            missing.append("Spreadsheet file")
        if params.prior_analysis and not params.prior_analysis_path:
            missing.append("Previous analysis folder (required by 'Use prior analysis')")
        # Starting mid-pipeline needs the earlier steps' output from somewhere:
        # a prior analysis folder, an explicit spike-data folder, or an existing
        # output folder named on the Paths tab (continuing a run in place).
        if (
            params.start_analysis_step > 1
            and not params.prior_analysis
            and not params.spike_detected_data
            and not params.output_data_folder_name
        ):
            missing.append(
                f"'Use prior analysis' — starting at step {params.start_analysis_step} needs "
                "the earlier steps' output, but this run would create an empty output folder"
            )

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

        self._pipeline_panel.start_progress()

        worker = PipelineWorker(params, parent=self)
        worker.log_message.connect(self._pipeline_panel.append_log)
        worker.progress.connect(self._pipeline_panel.show_progress)
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
        self._pipeline_panel.finish_progress("Finished.")
        self._pipeline_panel.append_log(f"Done. Output folder: {output_root}")
        self._announce_bundle(output_root)
        self._reset_run_buttons()

    def _announce_bundle(self, output_root: Path) -> None:
        """Say where the express bundle went, as the last thing in the log.

        The runner already logs the path, but it does so before the timing
        lines, so on an express run the one file the user is meant to keep
        scrolls out of sight behind everything else. It also lands *beside* the
        output folder rather than inside it, which is exactly the place nobody
        looks — so repeat it at the end, framed, with the command that opens it.
        """
        if not (self._params is not None and self._params.express_mode):
            return
        bundle = output_root.with_suffix(BUNDLE_SUFFIX)
        if not bundle.is_file():
            return
        self._last_bundle = bundle
        size_mb = bundle.stat().st_size / 1e6
        rule = "─" * 68
        self._pipeline_panel.append_log(
            f"\n{rule}\n"
            f"  Express bundle ({size_mb:.1f} MB) — beside the output folder, not in it:\n"
            f"    {bundle}\n"
            f"  Draw any figure from it:  meanap-viewer \"{bundle}\"\n"
            f"{rule}"
        )

    def _on_pipeline_cancelled(self) -> None:
        self._pipeline_panel.finish_progress("Stopped.")
        self._pipeline_panel.append_log("Pipeline stopped.")
        self._reset_run_buttons()

    def _on_pipeline_failed(self, message: str) -> None:
        self._pipeline_panel.finish_progress("Failed.")
        self._pipeline_panel.append_log(f"ERROR: {message}")
        self._reset_run_buttons()
        QMessageBox.critical(self, "Pipeline error", message)

    def _candidate_output_root(self) -> Path | None:
        """The output folder View report should act on, run or no run.

        Falls back to the same folder :func:`run_pipeline` would have created
        from the current paths — including its dated default name, which the
        Paths tab leaves blank — so the button works in a fresh session
        pointed at yesterday's results.
        """
        if self._last_output_root is not None:
            return self._last_output_root
        params = self._collect_params()
        if not params.output_data_folder:
            return None
        from meanap.pipeline.runner import default_output_folder_name
        name = params.output_data_folder_name or default_output_folder_name()
        return Path(params.output_data_folder) / name

    def _on_view_report(self) -> None:
        """Open the run's results: the viewer for an express run, else the report.

        An express run leaves almost no figures on disk — that is the point of
        it — so building the static PNG report from that folder produces a page
        that looks like a failed run. The bundle beside it holds everything, and
        the viewer draws any figure from it on demand, so that is what "view the
        report" means for those runs.
        """
        output_root = self._candidate_output_root()

        bundle = self._last_bundle
        if bundle is None and output_root is not None:
            candidate = output_root.with_suffix(BUNDLE_SUFFIX)
            if candidate.is_file():
                bundle = candidate
        if bundle is not None and bundle.is_file():
            self._open_in_viewer(bundle)
            return

        if output_root is None or not output_root.is_dir():
            QMessageBox.warning(
                self, "No output folder found",
                "Run the pipeline first, or set the Output data folder / name "
                "(Paths tab) to an existing MEA-NAP output folder.\n\n"
                "To open an express run from another machine, use "
                "'Open bundle…' in the toolbar, or drag its .meanap file onto "
                "this window.",
            )
            return

        try:
            report_path = generate_report(output_root)
        except Exception as e:
            QMessageBox.critical(self, "Report generation failed", str(e))
            return

        self._pipeline_panel.append_log(f"Report generated: {report_path}")
        webbrowser.open(report_path.as_uri())

    # ── Bundles ───────────────────────────────────────────────────────────────

    def _on_open_bundle(self) -> None:
        start_dir = str(self._last_bundle.parent) if self._last_bundle else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a MEA-NAP run bundle", start_dir,
            f"MEA-NAP bundles (*{BUNDLE_SUFFIX})",
        )
        if path:
            self._open_in_viewer(Path(path))

    def _open_in_viewer(self, source: Path) -> bool:
        """Serve *source* in the local viewer and open a browser on it.

        Reading a bundle means extracting and parsing it, which is quick but
        not instant, so the wait is shown rather than looking like a click that
        did nothing. Returns whether it opened.
        """
        already = self._viewers.url_for(source)
        if already is None:
            self._pipeline_panel.append_log(f"Opening in the viewer: {source}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            url = self._viewers.open(source)
        except Exception as e:
            QMessageBox.critical(self, "Could not open the bundle", str(e))
            return False
        finally:
            QApplication.restoreOverrideCursor()

        if already is None:
            self._pipeline_panel.append_log(
                f"Viewer serving at {url} — it stays up until MEA-NAP closes."
            )
        webbrowser.open(url)
        return True

    @staticmethod
    def _dropped_bundles(event) -> list[Path]:
        """The ``.meanap`` files in a drag event, in the order they were dragged."""
        data = event.mimeData()
        if not data.hasUrls():
            return []
        paths = []
        for url in data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix == BUNDLE_SUFFIX and path.is_file():
                paths.append(path)
        return paths

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # Only claim the drag when we can act on it: refusing everything else
        # leaves the path fields free to accept a dragged file as text.
        if self._dropped_bundles(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._dropped_bundles(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        bundles = self._dropped_bundles(event)
        if not bundles:
            event.ignore()
            return
        event.acceptProposedAction()
        for bundle in bundles:
            self._open_in_viewer(bundle)

    def closeEvent(self, event) -> None:
        # A running QThread destroyed with its parent crashes Qt; ask the
        # pipeline to stop and give it a moment to reach a cancel checkpoint.
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(5000)
        # Each viewer holds a port and a temporary extraction directory; both
        # live as long as the process unless handed back here.
        self._viewers.close_all()
        super().closeEvent(event)
