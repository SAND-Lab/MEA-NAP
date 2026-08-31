"""MEA-NAP main application window."""

import json
import webbrowser
from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QLineEdit, QScrollArea, QTabWidget, QToolBar, QWidget,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QSettings, QSignalBlocker, QSize

from meanap.params import Params
from meanap.pipeline.bundle import BUNDLE_SUFFIX
from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.report import generate_report
from meanap.gui.branding import CORNER_LOGO_HEIGHT, logo_icon, logo_pixmap
from meanap.gui.dialogs import ask_yes_no
from meanap.gui import advanced
from meanap.gui.modes import (
    DEFAULT_MODE, MODES, TAB_CATNAP, TAB_CONNECTIVITY, TAB_DATA, TAB_RESULTS,
    TAB_RUN, TAB_SPIKE, TAB_STATS, TAB_STIM,
    TAB_STIM_PREVIEW,
    apply_mode_to_params, mode_for_params,
)
from meanap.gui.pipeline_worker import PipelineWorker, QueueWorker
from meanap.gui.stats_worker import StatsWorker
from meanap.gui.viewer_session import ViewerSessions
from meanap.gui.panels.data import (
    CATNAP_DATA_LABEL, DataPanel, RAW_DATA_LABEL,
)
from meanap.gui.panels.spike_detection import SpikeDetectionPanel
from meanap.gui.panels.connectivity import ConnectivityPanel
from meanap.gui.panels.stim import StimPanel
from meanap.gui.panels.stim_preview import StimPreviewPanel
from meanap.gui.panels.run import QUEUE, RunPanel
from meanap.gui.panels.catnap import CatNapPanel
from meanap.gui.panels.results import ResultsPanel
from meanap.gui.panels.stats import StatsPanel
from meanap.gui.tooltip import install_tooltip_style, wrap_tooltips
from meanap.gui.tutorial import TutorialOverlay, TutorialStep, tabbar_target


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    return area


class _LogoLabel(QLabel):
    """A logo whose artwork does not become a floor for the whole window.

    A QLabel reports its pixmap as its minimum size, and in the tab strip's
    corner that minimum propagates all the way up to the window — so a taller
    logo would raise the smallest height the window can be resized to, which
    is the thing test_gui_window_resize exists to protect. The corner is laid
    out from ``sizeHint``, left alone here, so the logo still draws full size.
    """

    def minimumSizeHint(self) -> QSize:  # noqa: D102
        return QSize(0, 0)


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
        # Wide enough for both header rows to lay out in full. The toolbar
        # sets the floor — below it Qt folds trailing actions into an overflow
        # chevron, a reasonable thing for Tutorial but not for the Mode
        # selector, hence Mode leading the toolbar rather than ending it. The
        # binding constraint is MEA-Stim's tab strip, which is seven tabs plus
        # the logo beside them and needs ~1120; the margin over that is for
        # fonts wider than the one measured here.
        self.resize(1200, 800)

        self._params = Params()
        # Stamp the launch mode onto the defaults before anything reads them:
        # _load_params derives the mode from these flags, so leaving them unset
        # would snap a "--mode catnap" launch straight back to the ephys tabs.
        apply_mode_to_params(mode, self._params)
        # ...including the settings that are shared between pipelines but want
        # a different value in each. __init__ ends by loading these into the
        # panels, so this is what a "--mode catnap" launch actually starts on.
        self._params.func_con_lag_val = list(MODES[mode].default_lags)
        self._last_output_root: Path | None = None
        self._last_bundle: Path | None = None
        self._stats_worker: StatsWorker | None = None
        #: True once the user has picked a run for the Stats tab by hand, after
        #: which this session's own run no longer overrides their choice.
        self._stats_source_chosen = False
        self._worker: PipelineWorker | None = None
        self._queue_worker: QueueWorker | None = None
        self._tutorial: TutorialOverlay | None = None
        self._viewers = ViewerSessions()

        # A bundle is a file people email each other, so dropping one on the
        # window is the obvious way to open it. Accepted at the window level;
        # see dragEnterEvent for why nothing else is claimed.
        self.setAcceptDrops(True)

        self._build_toolbar()
        self._build_tabs()
        # After the tabs exist, so there is something to expand. Blocked so
        # restoring the preference does not immediately re-save it.
        self._act_advanced.blockSignals(True)
        self._act_advanced.setChecked(advanced.load_preference())
        self._act_advanced.blockSignals(False)
        advanced.set_all_expanded(self, self._act_advanced.isChecked())
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

        act_tutorial = QAction("?  Tutorial", self)
        act_tutorial.setToolTip("Launch the guided tutorial")
        act_tutorial.triggered.connect(self._start_tutorial)

        # One switch for every folded section in the window, for someone who
        # would rather see all of it than open sections one at a time. It only
        # changes what is shown: see meanap.gui.advanced.
        self._act_advanced = QAction("⚙  Advanced", self)
        self._act_advanced.setCheckable(True)
        self._act_advanced.setToolTip(
            "Show the less-used settings on every tab at once. They are saved "
            "and used either way — this only changes what is on screen."
        )
        self._act_advanced.toggled.connect(self._on_toggle_advanced)

        # Mode selector first, and deliberately so. It decides which pipeline
        # the window is for, which is a bigger choice than anything after it —
        # and a toolbar that overflows drops its *trailing* items, so the last
        # thing to go should not be the first thing you set. (It used to sit at
        # the far end, and a narrow window hid it behind the overflow chevron.)
        tb.addWidget(QLabel("  Mode "))
        self._mode_combo = QComboBox()
        for key, mode in MODES.items():
            self._mode_combo.addItem(mode.label, key)
        self._mode_combo.setCurrentIndex(self._mode_combo.findData(self._mode))
        self._mode_combo.setToolTip(MODES[self._mode].blurb)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tb.addWidget(self._mode_combo)

        # Beside the selector rather than in an About box: the three pipelines
        # are versioned separately, so "which version" is only answerable once
        # you know which mode, and putting them together makes that obvious.
        self._version_label = QLabel()
        self._version_label.setContentsMargins(8, 0, 0, 0)
        self._version_label.setStyleSheet("color: palette(mid);")
        tb.addWidget(self._version_label)
        self._refresh_version_label()
        tb.addSeparator()

        tb.addAction(act_new)
        tb.addSeparator()
        tb.addAction(act_open)
        tb.addAction(act_save)
        tb.addSeparator()
        tb.addAction(self._act_advanced)
        tb.addAction(act_tutorial)
        tb.addSeparator()


    def _add_logo(self) -> None:
        """Branding in the tab strip's right-hand corner, not on the toolbar.

        It used to sit at the far end of the toolbar past an expanding spacer,
        which meant it competed for width with the actions: at the default
        window size the spacer took what was left and pushed Tutorial — and
        before that the Mode selector — into the overflow chevron. There is
        always room beside five tabs, and nothing there to be pushed out.
        """
        if logo_pixmap(CORNER_LOGO_HEIGHT, self.devicePixelRatioF(), self._mode) is None:
            return
        self._logo_label = _LogoLabel()
        self._logo_label.setContentsMargins(0, 0, 10, 0)
        self._tabs.setCornerWidget(self._logo_label, Qt.Corner.TopRightCorner)
        self._refresh_logo()

    def _refresh_logo(self) -> None:
        """Show the running mode's artwork, falling back to MEA-NAP's.

        The window icon deliberately does *not* follow: it identifies the
        application in the taskbar and to the window manager, where a logo that
        changed under the user would read as a different program.
        """
        label = getattr(self, "_logo_label", None)
        if label is None:
            return
        from meanap.gui.branding import available_logos

        pixmap = logo_pixmap(CORNER_LOGO_HEIGHT, self.devicePixelRatioF(), self._mode)
        if pixmap is not None:
            label.setPixmap(pixmap)
        mode = MODES[self._mode]
        own = self._mode in available_logos()
        label.setToolTip(
            f"{mode.label}\n{mode.blurb}" if own
            else "MEA-NAP — MEA Network Analysis Pipeline")

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)
        self._add_logo()

        self._data_panel = DataPanel()
        self._spike_panel = SpikeDetectionPanel()
        self._connectivity_panel = ConnectivityPanel()
        self._stim_panel = StimPanel()
        self._stim_preview_panel = StimPreviewPanel()
        self._catnap_panel = CatNapPanel()
        self._run_panel = RunPanel()
        # The Run tab holds both pages; these name them for the code that only
        # cares about one — loading parameters, or the queue's list.
        self._pipeline_panel = self._run_panel.settings
        self._queue_panel = self._run_panel.queue
        self._results_panel = ResultsPanel()
        self._results_panel.view_report_requested.connect(self._on_view_report)
        self._results_panel.open_bundle_requested.connect(self._on_open_bundle)
        self._network_viewer_panel = self._results_panel.viewer
        self._stats_panel = StatsPanel()
        self._stats_panel.run_requested.connect(self._on_run_stats)
        self._stats_panel.open_folder_requested.connect(self._on_open_stats_folder)
        self._stats_panel.choose_source_requested.connect(self._on_choose_stats_source)

        # Every tab is built once and kept alive here; the current mode decides
        # which of them are actually in the QTabWidget (see _apply_mode). Order
        # is the order they appear in, whichever subset is showing.
        self._tab_specs: list[tuple[str, QWidget, str]] = [
            (TAB_DATA, _scrollable(self._data_panel), "  Data  "),
            (TAB_SPIKE, _scrollable(self._spike_panel), "  Spike detection  "),
            # CAT-NAP before Connectivity: in 2P mode this tab is where the
            # recordings are found and prepared, so it comes before the
            # settings that act on them — the same place Spike detection holds
            # in the ephys modes.
            (TAB_CATNAP, self._catnap_panel, "  CAT-NAP (2P)  "),
            (TAB_CONNECTIVITY, _scrollable(self._connectivity_panel), "  Connectivity  "),
            (TAB_STIM, _scrollable(self._stim_panel), "  Stimulation  "),
            (TAB_STIM_PREVIEW, self._stim_preview_panel, "  Stim Preview  "),
            (TAB_RUN, self._run_panel, "  Run  "),
            (TAB_RESULTS, self._results_panel, "  Results  "),
            # Last, because it acts on a run that has already finished — it is
            # the only tab whose input is another tab's output.
            # "&&" because Qt reads a single "&" in a tab label as the marker
            # for a keyboard mnemonic and swallows it.
            (TAB_STATS, _scrollable(self._stats_panel), "  Stats && ML  "),
        ]
        self._apply_mode(self._mode, sync_params=False)

        self._catnap_panel.log_message.connect(self._run_panel.append_log)
        # The activity type decides whether the Connectivity tab's timescale
        # field means STTC lags or correlation bins, and the two tabs are never
        # visible at once — so the label has to follow the selector rather than
        # wait for the user to notice.
        self._catnap_panel._activity_combo.currentTextChanged.connect(
            lambda _text: self._refresh_timescale_label())
        # What "View report" would open depends on the output paths, which live
        # on another tab, so it is recomputed on the way in rather than cached.
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._queue_panel.changed.connect(self._run_panel.refresh)

        # The Data tab's recordings folder and the CAT-NAP tab's are
        # two views of one setting (Params.raw_data), and both panels write it
        # in _collect_params — so whichever saves last silently wins. Mirror
        # them instead. Without this, setting the folder on Data and pressing
        # Run reports it missing, because the empty CAT-NAP field overwrites it.
        self._bind_mirrored(
            self._data_panel.raw_data.line_edit, self._catnap_panel._folder_edit
        )

        # Mark Run / Stop with object names so QSS can style them distinctly
        self._run_panel.run_btn.setObjectName("primary")
        self._run_panel.stop_btn.setObjectName("danger")
        self._run_panel.test_btn.setObjectName("secondary")
        self._run_panel.run_btn.clicked.connect(self._on_run_clicked)
        self._run_panel.stop_btn.clicked.connect(self._on_stop)
        self._run_panel.test_btn.clicked.connect(self._on_test_pipeline)

        # Mark log widget so the monospace QSS rule applies
        self._run_panel.log.setObjectName("log")
        self._catnap_panel._log.setObjectName("log")

        # QTextEdit accepts drops even when read-only, and a child that accepts
        # a drag stops it reaching the window — so a bundle dropped on the
        # status log, the largest target on the Run tab, would do nothing.
        self._run_panel.log.setAcceptDrops(False)
        self._catnap_panel._log.setAcceptDrops(False)

        # The scan can hide folders the batch spreadsheet leaves out, which
        # means reading the Data tab's spreadsheet as it stands when the scan
        # finishes — not as it was when the panels were built.
        self._catnap_panel.spreadsheet_source = lambda: (
            self._data_panel.spreadsheet.value,
            self._data_panel.spreadsheet_range.text(),
        )

        # A spreadsheet built from a scan describes the recordings the run is
        # about to read, so point the run at it rather than leaving the user to
        # copy the path across tabs.
        self._catnap_panel.spreadsheet_saved.connect(
            self._data_panel.spreadsheet.set_value)

        # Secondary-style buttons in CAT-NAP panel
        self._catnap_panel._scan_btn.setObjectName("secondary")
        self._catnap_panel._denoise_btn.setObjectName("secondary")
        self._catnap_panel._make_sheet_btn.setObjectName("secondary")
        self._data_panel.edit_spreadsheet_btn.setObjectName("secondary")

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

    def _on_toggle_advanced(self, show: bool) -> None:
        n = advanced.set_all_expanded(self, show)
        advanced.save_preference(show)
        self.statusBar().showMessage(
            f"{'Showing' if show else 'Hiding'} advanced settings "
            f"in {n} section(s).", 4000)

    # ── Modes ─────────────────────────────────────────────────────────────────

    def _apply_mode(self, mode_key: str, *, sync_params: bool = True) -> None:
        """Show exactly the tabs *mode_key* needs, keeping the rest alive.

        QTabWidget has no "hide tab", so switching modes means rebuilding the
        tab strip. The pages themselves are never destroyed, so anything a user
        typed into a tab that is currently hidden is still there when the mode
        brings it back.

        A few settings are shared between the pipelines but want different
        values in each, so the outgoing mode is kept long enough to re-tune
        them — without overwriting anything the user set themselves.
        """
        mode = MODES[mode_key]
        previous = self._mode
        self._mode = mode_key
        # The Data tab is shown in every mode but does not mean the same thing
        # in each — CAT-NAP has no electrodes and no sampling rate to set.
        self._data_panel.set_mode(mode_key)

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
        # rather than dumping the user back on Data every time.
        index = self._tab_index(keep) if keep else -1
        self._tabs.setCurrentIndex(index if index >= 0 else 0)

        # Before _collect_params(), so a run started right after a switch uses
        # the lags the tab now shows.
        new_lags = self._connectivity_panel.retune_lags_for_mode(previous, mode_key)

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
        self._refresh_version_label()
        self._refresh_logo()
        self._refresh_timescale_label()
        if new_lags is not None:
            # Say it out loud: the lags drive every network in the run, and a
            # field changing itself behind your back is worse than no change.
            self.statusBar().showMessage(
                f"Lag values set to {', '.join(str(v) for v in new_lags)} ms "
                f"for {mode.label.split('·')[0].strip()}.", 6000)

    def _refresh_timescale_label(self) -> None:
        """Point the Connectivity tab at whichever measure this run will use."""
        from meanap.timescale import timescale_kind

        params = Params()
        apply_mode_to_params(self._mode, params)
        params.twop_activity = self._catnap_panel._activity_combo.currentText()
        self._connectivity_panel.set_timescale(timescale_kind(params))
        # The dimensionality switches on that tab are the ephys step 4's; say
        # so when the run about to start is a CAT-NAP one.
        self._connectivity_panel.set_pipeline(self._mode)

    def _refresh_version_label(self) -> None:
        """Show the running mode's version, and all three in the tooltip."""
        label = getattr(self, "_version_label", None)
        if label is None:
            return
        from meanap.version import PIPELINE_NAMES, all_versions, pipeline_version

        label.setText(f"v{pipeline_version(self._mode)}")
        every = all_versions()
        label.setToolTip(
            "Versions in this install:\n"
            + "\n".join(f"  {PIPELINE_NAMES[k]} {every[k]}" for k in PIPELINE_NAMES)
            + "\n\nThe running pipeline's version is written into every run's "
              "params.json and bundle manifest.")

    def _tab_index(self, key: str) -> int:
        """Current index of tab *key*, or -1 when this mode hides it."""
        for spec_key, widget, _ in self._tab_specs:
            if spec_key == key:
                return self._tabs.indexOf(widget)
        return -1

    def _on_tab_changed(self, _index: int) -> None:
        key = self._current_tab_key()
        if key == TAB_RESULTS:
            self._refresh_results_target()
        elif key == TAB_STATS:
            self._refresh_stats_target()

    def _refresh_results_target(self) -> None:
        root = self._candidate_output_root()
        bundle = self._last_bundle
        if bundle is None and root is not None:
            candidate = root.with_suffix(BUNDLE_SUFFIX)
            bundle = candidate if candidate.is_file() else None
        self._results_panel.set_target(root, bundle)

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
        data = self._data_panel
        spike = self._spike_panel
        conn = self._connectivity_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Raw data folder", "The MEA-NAP pipeline starts on the Data tab. "
                "Choose the folder holding your recordings. No conversion needed: "
                "Multi Channel Systems .h5 and Axion .raw are read as they come off "
                "the recorder, alongside .mat files from the MATLAB converters.",
                self._tab_index(TAB_DATA), lambda: data.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX that lists each recording, "
                "its group and its age (DIV). This drives the whole batch. Name recordings "
                "without the file extension. An Axion .raw holds a whole plate, so name "
                "one row per well — 'Plate2_DIV75_A1' — exactly as the MATLAB converter "
                "would have named the file it wrote. No spreadsheet yet? “Edit…” "
                "builds one here and checks it as you type.",
                self._tab_index(TAB_DATA), lambda: data.spreadsheet),
            TutorialStep(
                "Spreadsheet range", "The cell range to read from the spreadsheet, "
                "e.g. A2:A100000 to read every row after the header.",
                self._tab_index(TAB_DATA), lambda: data.spreadsheet_range),
            TutorialStep(
                "Where results go", "Set the output folder and give this analysis run "
                "a name — a subfolder with that name will hold all results and plots.",
                self._tab_index(TAB_DATA), lambda: data.output_data_folder),
            TutorialStep(
                "Recording settings", "Further down the Data tab, set the sampling frequency "
                "of your acquisition (Hz) so spike detection and downsampling are correct.",
                self._tab_index(TAB_DATA), lambda: data.fs),
            TutorialStep(
                "Voltage units", "Set this to the units your recordings are in — µV for "
                "Multi Channel Systems, V for Axion. Getting it wrong scales every "
                "amplitude, so spike detection thresholds land in the wrong place.",
                self._tab_index(TAB_DATA), lambda: data.potential_difference_unit),
            TutorialStep(
                "Channel layout", "Pick the MEA layout that matches your hardware: MCS60 "
                "for a 60-electrode MCS array, Axion64 for 6-well Axion plates, Axion16 "
                "for 24-well plates (16 electrodes per well). This maps channels to "
                "electrode positions.",
                self._tab_index(TAB_DATA), lambda: data.channel_layout),
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
                "Choose the steps", "On the Run tab, pick which steps to run "
                "(1–4). The default runs the whole pipeline end to end.",
                self._tab_index(TAB_RUN), lambda: pipe.start_step),
            TutorialStep(
                "Try it first", "Not sure your setup works? 'Test pipeline' downloads a "
                "small example dataset and runs all four steps on it.",
                self._tab_index(TAB_RUN), lambda: self._run_panel.test_btn),
            TutorialStep(
                "Run the pipeline", "When your paths are filled in, press Run. Progress, "
                "a time estimate and the status log all appear below it.",
                self._tab_index(TAB_RUN), lambda: self._run_panel.run_btn),
            TutorialStep(
                "Look at what came out", "The Results tab is the last stop. 'View report' "
                "opens the run in your browser — an HTML gallery of every figure, or the "
                "viewer if it was an express run — and the network viewer below explores "
                "any recording's connectivity interactively.",
                self._tab_index(TAB_RESULTS),
                lambda: self._results_panel.view_report_btn),
        ]

    def _build_meastim_steps(self) -> list[TutorialStep]:
        data = self._data_panel
        stim = self._stim_panel
        pipe = self._pipeline_panel
        return [
            TutorialStep(
                "Raw data folder", "MEA-Stim reuses the same Data tab. Choose the folder "
                "with your stimulation recordings — .mat, Multi Channel Systems .h5 or "
                "Axion .raw, no conversion needed.",
                self._tab_index(TAB_DATA), lambda: data.raw_data),
            TutorialStep(
                "Recording spreadsheet", "Select the CSV/XLSX listing each recording, "
                "its group and DIV.",
                self._tab_index(TAB_DATA), lambda: data.spreadsheet),
            TutorialStep(
                "Where results go", "Set the output folder and a name for this run's "
                "results subfolder.",
                self._tab_index(TAB_DATA), lambda: data.output_data_folder),
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
                "Run the pipeline", "On the Run tab, press Run. Spike detection runs "
                "first, then the stimulation analysis and its plots.",
                self._tab_index(TAB_RUN), lambda: self._run_panel.run_btn),
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
                "genotype/group column, save, and the Data tab points at it.",
                self._tab_index(TAB_CATNAP), lambda: cat._make_sheet_btn),
            TutorialStep(
                "Denoising", "Optionally denoise the fluorescence traces before analysis. "
                "The threshold multiplier and peak windows control event extraction.",
                self._tab_index(TAB_CATNAP), lambda: cat._denoise_btn),
            TutorialStep(
                "Run the pipeline", "With CAT-NAP mode on and a folder selected, go to "
                "the Run tab and press Run to analyse the imaging data.",
                self._tab_index(TAB_RUN), lambda: self._run_panel.run_btn),
        ]

    # ── Param sync ────────────────────────────────────────────────────────────

    def _load_params(self, params: Params) -> None:
        # A parameter file carries the pipeline it was written for, so follow
        # it — otherwise opening a CAT-NAP config would leave the window showing
        # ephys tabs while the run does 2P.
        wanted = mode_for_params(params)
        if wanted != self._mode:
            self._apply_mode(wanted, sync_params=False)

        self._data_panel.load(params)
        self._spike_panel.load(params)
        self._connectivity_panel.load(params)
        self._stim_panel.load(params)
        self._stim_preview_panel.load_defaults(params)  # preview-only: no save/collect
        self._catnap_panel.load(params)
        self._pipeline_panel.load(params)
        self._refresh_timescale_label()

    def _collect_params(self) -> Params:
        params = Params()
        self._data_panel.save(params)
        self._spike_panel.save(params)
        self._connectivity_panel.save(params)
        self._stim_panel.save(params)
        self._catnap_panel.save(params)
        self._pipeline_panel.save(params)
        return params

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_new(self) -> None:
        # ask_yes_no rather than QMessageBox.question: the latter lets the
        # platform decide which end Yes goes on, which moves it on a Mac.
        if ask_yes_no(self, "New parameters",
                      "Reset all parameters to defaults?"):
            # Defaults for the pipeline on screen, not for MEA-NAP: resetting
            # in CAT-NAP should not quietly drop you back into the ephys tabs
            # with ephys-scaled lags.
            params = Params()
            apply_mode_to_params(self._mode, params)
            params.func_con_lag_val = list(MODES[self._mode].default_lags)
            self._params = params
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
            self._run_panel.append_log(f"Loaded parameters from {path}")
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
            self._run_panel.append_log(f"Saved parameters to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error saving parameters", str(e))

    # ── Pipeline run / stop ───────────────────────────────────────────────────

    def _on_test_pipeline(self) -> None:
        # The test run needs somewhere to put the example data and its output.
        # Default the output folder to ~/MEA-NAP when it hasn't been set.
        out_folder = self._data_panel.output_data_folder.value
        if not out_folder:
            out_folder = str(Path.home() / "MEA-NAP")
            self._data_panel.output_data_folder.set_value(out_folder)

        self._tabs.setCurrentIndex(self._tab_index(TAB_RUN))
        self._run_panel.append_log("Downloading example data for pipeline test…")
        QApplication.processEvents()

        def log(message: str) -> None:
            self._run_panel.append_log(message)
            QApplication.processEvents()

        try:
            example_dir = download_example_data(Path(out_folder), log=log)
        except Exception as e:
            QMessageBox.critical(self, "Download failed", str(e))
            return

        # Point the paths panel at the example dataset, mirroring the MATLAB
        # TestPipelineButton behaviour (downloadExampleData + settings override).
        self._data_panel.raw_data.set_value(str(example_dir))
        self._data_panel.spreadsheet.set_value(str(example_dir / "exampleData.csv"))
        self._data_panel.spreadsheet_range.setText("A2:A3")
        try:
            from meanap.pipeline.spreadsheet import read_recording_csv
            recordings = read_recording_csv(example_dir / "exampleData.csv", "A2:A3")
            # Preserve order of first appearance
            unique_grps = list(dict.fromkeys(r.group for r in recordings))
            self._data_panel.custom_grp_order.setText(",".join(unique_grps))
        except Exception as e:
            log(f"Warning: could not parse custom group order from exampleData.csv: {e}")

        # The test run verifies that the full pipeline (steps 1-4) works.
        self._pipeline_panel.start_step.setValue(1)
        self._pipeline_panel.stop_step.setValue(4)

        self._run_panel.append_log("Example data ready — running full pipeline (steps 1-4).")
        self._on_run()

    def _on_run_clicked(self) -> None:
        """One button, so what it starts is whatever the Run tab's switch says.

        Nothing here has to refuse an overlapping run: the button is disabled
        while anything is going, so there is no second run to refuse.
        """
        if self._busy():
            return
        if self._run_panel.mode() == QUEUE:
            self._on_run_queue()
        else:
            self._on_run()

    def _busy(self) -> bool:
        return ((self._worker is not None and self._worker.isRunning())
                or (self._queue_worker is not None
                    and self._queue_worker.isRunning()))

    def _on_run(self) -> None:
        if self._busy():
            return

        params = self._collect_params()
        self._params = params

        missing = []
        # Only step 1 reads the raw recordings; later steps work from the spike
        # files, so a resumed run doesn't need the raw data mounted at all.
        # Named as the Data tab names it in this mode — see DataPanel.set_mode.
        if not params.raw_data and params.start_analysis_step == 1:
            missing.append(
                f"{CATNAP_DATA_LABEL} (needed to find the suite2p recordings)"
                if self._mode == "catnap" else
                f"{RAW_DATA_LABEL} (needed for step 1 — spike detection)")
        if not params.output_data_folder:
            missing.append("Output data folder")
        if not params.spreadsheet_file_name:
            missing.append("Spreadsheet file")
        if params.prior_analysis and not params.prior_analysis_path:
            missing.append("Previous analysis folder (required by 'Use prior analysis')")
        # Starting mid-pipeline needs the earlier steps' output from somewhere:
        # a prior analysis folder, an explicit spike-data folder, or an existing
        # output folder named on the Data tab (continuing a run in place).
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

        self._run_panel.append_log(
            f"Starting MEA-NAP: steps {params.start_analysis_step}-{params.stop_analysis_step}…"
        )

        params = self._confirm_output_folder(params)
        if params is None:
            # Called off at the overwrite prompt. Buttons are set *after* this
            # rather than before, so the tab cannot be left with Run greyed out
            # and nothing running.
            self._run_panel.append_log("Run cancelled.")
            return

        self._run_panel.set_running(True)
        self._run_panel.start_progress()

        worker = PipelineWorker(params, parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.progress.connect(self._run_panel.show_progress)
        worker.finished_ok.connect(self._on_pipeline_finished)
        worker.cancelled.connect(self._on_pipeline_cancelled)
        worker.failed.connect(self._on_pipeline_failed)
        self._worker = worker
        worker.start()

    def _confirm_output_folder(self, params: Params) -> Params | None:
        """Ask before a run lands on an existing one. ``None`` = don't run.

        The default folder name is today's date, so the second run of a day
        collides with the first without the user having done anything wrong —
        which is exactly when a silent overwrite is least expected and most
        expensive. ``run_pipeline`` would move aside on its own; asking here
        lets the choice be an informed one, and puts the name that will actually
        be used on the Data tab where it can be seen.
        """
        from meanap.pipeline.output_folders import (
            next_free_output_name, output_name_taken,
        )
        from meanap.pipeline.runner import (
            default_output_folder_name, resumes_in_place,
        )

        if resumes_in_place(params) or params.continue_interrupted:
            return params   # the run is going to read what is in there

        name = params.output_data_folder_name or default_output_folder_name()
        parent = Path(params.output_data_folder or ".")
        if not output_name_taken(parent, name):
            return params

        fresh = next_free_output_name(parent, name)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("That run already exists")
        # Qt auto-detects rich text on the main label but not the informative
        # one, so say which it is rather than leaving markup showing.
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"<b>{name}</b> already holds a run's results.")
        box.setInformativeText(
            "Running now would overwrite it — its figures, its CSVs and its "
            f"bundle.<br><br>Save this run as <b>{fresh}</b> instead, or "
            "continue the existing one where it stopped?"
        )
        use_new = box.addButton(f"Use {fresh}", QMessageBox.ButtonRole.AcceptRole)
        # The third option is the one a stopped run actually wants: fill in the
        # recordings that never finished rather than redo the ones that did.
        continue_it = box.addButton("Continue it",
                                    QMessageBox.ButtonRole.ActionRole)
        overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(use_new)
        box.exec()

        clicked = box.clickedButton()
        if clicked is use_new:
            # Onto the Data tab too: the name a run wrote to should be visible
            # afterwards, not something the user has to reconstruct from a log.
            self._data_panel.output_data_folder_name.setText(fresh)
            params.output_data_folder_name = fresh
            self._run_panel.append_log(f"Saving this run as {fresh}.")
            return params
        if clicked is continue_it:
            self._run_panel.append_log(
                f"Continuing {name} — recordings already finished are skipped.")
            # A copy, for the same reason as below: continuing is a decision
            # about this run, not a setting to carry into every future one.
            return replace(params, continue_interrupted=True)
        if clicked is overwrite:
            self._run_panel.append_log(f"Overwriting the existing run in {name}.")
            # A copy, so "overwrite this once" cannot be saved into a parameter
            # file and quietly overwrite every run that later loads it.
            return replace(params, overwrite_existing_output=True)
        return None

    def _on_run_queue(self) -> None:
        """Start the queued runs."""
        if self._busy():
            return
        paths = self._queue_panel.paths()
        if not paths:
            return

        self._queue_panel.start()
        self._run_panel.set_running(True)
        self._run_panel.start_progress()
        self._run_panel.append_log(f"Starting {len(paths)} queued run(s)…")

        worker = QueueWorker(paths, parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.progress.connect(
            lambda i, label, snap, n=len(paths):
                self._run_panel.show_queue_progress(i, n, label, snap))
        worker.run_finished.connect(self._queue_panel.mark)
        worker.finished_all.connect(self._on_queue_finished)
        worker.failed.connect(self._on_queue_failed)
        self._queue_worker = worker
        worker.start()

    def _on_queue_finished(self, summary: str) -> None:
        self._queue_worker = None
        self._run_panel.set_running(False)
        self._run_panel.finish_progress(summary)

    def _on_queue_failed(self, message: str) -> None:
        self._queue_worker = None
        self._run_panel.set_running(False)
        self._run_panel.finish_progress("The queue could not start.")
        self._run_panel.append_log(f"ERROR: {message}")
        QMessageBox.critical(self, "Queue error", message)

    def _on_stop(self) -> None:
        """Stop whichever of the two is running — again, one button for both."""
        if self._queue_worker is not None and self._queue_worker.isRunning():
            self._run_panel.append_log(
                "Stop requested — finishing the current run, then halting. "
                "Runs after it will not be started.")
            self._run_panel.stop_btn.setEnabled(False)
            self._queue_worker.request_cancel()
        elif self._worker is not None and self._worker.isRunning():
            self._run_panel.append_log(
                "Stop requested — finishing the current recording, then halting…"
            )
            self._run_panel.stop_btn.setEnabled(False)
            self._worker.request_cancel()
        else:
            self._run_panel.stop_btn.setEnabled(False)

    def _reset_run_buttons(self) -> None:
        self._worker = None
        self._run_panel.set_running(False)

    def _on_pipeline_finished(self, output_root: Path) -> None:
        self._last_output_root = output_root
        self._run_panel.finish_progress("Finished.")
        self._run_panel.append_log(f"Done. Output folder: {output_root}")
        self._announce_bundle(output_root)
        self._reset_run_buttons()
        # The log is what someone is looking at when a run ends, and the thing
        # to do next is now on a different tab.
        self._run_panel.append_log(
            "Open the results on the Results tab, or explore the networks there.")
        self._refresh_results_target()

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
        self._run_panel.append_log(
            f"\n{rule}\n"
            f"  Express bundle ({size_mb:.1f} MB) — beside the output folder, not in it:\n"
            f"    {bundle}\n"
            f"  Draw any figure from it:  meanap-viewer \"{bundle}\"\n"
            f"{rule}"
        )

    def _on_pipeline_cancelled(self) -> None:
        self._run_panel.finish_progress("Stopped.")
        self._run_panel.append_log("Pipeline stopped.")
        self._reset_run_buttons()

    def _on_pipeline_failed(self, message: str) -> None:
        self._run_panel.finish_progress("Failed.")
        self._run_panel.append_log(f"ERROR: {message}")
        self._reset_run_buttons()
        QMessageBox.critical(self, "Pipeline error", message)

    # ── Stats & ML ────────────────────────────────────────────────────────────

    def _refresh_stats_target(self) -> None:
        """Point the Stats tab at whatever this session's run produced.

        A user-chosen source wins: having picked a run explicitly, they should
        not find the tab silently switched back on the next visit.
        """
        if self._stats_source_chosen:
            return
        bundle = self._last_bundle
        root = self._last_output_root or self._candidate_output_root()
        source = bundle if bundle is not None else root
        if source is not None and Path(source).exists():
            self._stats_panel.set_source(Path(source))
        else:
            self._stats_panel.set_source(None)

    def _on_choose_stats_source(self) -> None:
        source = self._stats_panel.choose_source_dialog()
        if source is None:
            return
        self._stats_source_chosen = True
        self._stats_panel.set_source(source)
        self._stats_panel.set_result(None)

    def _on_run_stats(self) -> None:
        source = self._stats_panel.source()
        if source is None:
            return
        if self._stats_worker is not None and self._stats_worker.isRunning():
            return

        self._stats_panel.clear_log()
        self._stats_panel.set_running(True)
        self._stats_panel.set_result(None)

        worker = StatsWorker(source, None, self._stats_panel.settings(), parent=self)
        worker.log_message.connect(self._stats_panel.append_log)
        worker.finished_ok.connect(self._on_stats_finished)
        worker.failed.connect(self._on_stats_failed)
        worker.finished.connect(lambda: self._stats_panel.set_running(False))
        self._stats_worker = worker
        worker.start()

    def _on_stats_finished(self, result) -> None:
        self._stats_panel.set_result(result.dest)
        self._stats_panel.append_log(
            f"\nDone — {len(result.tables)} table(s), {len(result.figures)} "
            f"figure(s) in {result.dest}")
        if result.skipped:
            self._stats_panel.append_log("Skipped:")
            for item in result.skipped:
                self._stats_panel.append_log(f"  - {item}")

    def _on_stats_failed(self, message: str) -> None:
        self._stats_panel.append_log(f"ERROR: {message}")
        QMessageBox.critical(self, "Statistics error", message)

    def _on_open_stats_folder(self) -> None:
        folder = self._stats_panel.result_folder()
        if folder is not None and folder.exists():
            webbrowser.open(folder.as_uri())

    def _candidate_output_root(self) -> Path | None:
        """The output folder View report should act on, run or no run.

        Falls back to the same folder :func:`run_pipeline` would have created
        from the current paths — including its dated default name, which the
        Data tab leaves blank — so the button works in a fresh session
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
                "(Data tab) to an existing MEA-NAP output folder.\n\n"
                "To open an express run from another machine, use "
                "'Open bundle…' above, or drag its .meanap file onto "
                "this window.",
            )
            return

        try:
            report_path = generate_report(output_root)
        except Exception as e:
            QMessageBox.critical(self, "Report generation failed", str(e))
            return

        self._run_panel.append_log(f"Report generated: {report_path}")
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
            self._run_panel.append_log(f"Opening in the viewer: {source}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            url = self._viewers.open(source)
        except Exception as e:
            QMessageBox.critical(self, "Could not open the bundle", str(e))
            return False
        finally:
            QApplication.restoreOverrideCursor()

        if already is None:
            self._run_panel.append_log(
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
        # The stats step has no cancellation checkpoints — it is a sequence of
        # model fits, none individually long — so this waits it out rather than
        # asking it to stop.
        if self._stats_worker is not None and self._stats_worker.isRunning():
            self._stats_worker.wait(10000)
        # Each viewer holds a port and a temporary extraction directory; both
        # live as long as the process unless handed back here.
        self._viewers.close_all()
        super().closeEvent(event)
