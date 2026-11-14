"""MEA-NAP main application window."""

import dataclasses
import json
import webbrowser
from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QLabel, QMainWindow, QWidgetAction,
    QMessageBox, QPushButton,
    QLineEdit, QStackedWidget, QTabWidget, QToolBar, QToolButton, QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QObject, QRect, Qt, QSettings, QSignalBlocker, QSize, QTimer, pyqtSignal

from meanap.params import STATS_STEP, Params
from meanap.pipeline.bundle import BUNDLE_SUFFIX
from meanap.pipeline.pack import default_bundle_dest, unbundlable_reason
from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.report import generate_report
from meanap.gui.branding import CORNER_LOGO_HEIGHT, logo_icon, logo_pixmap
from meanap.gui.dialogs import ask_yes_no
from meanap.gui import advanced
from meanap.gui.modes import (
    DEFAULT_MODE, MODES, TAB_CATNAP, TAB_CONNECTIVITY, TAB_DATA, TAB_RESULTS,
    TAB_RUN, TAB_SPIKE, TAB_STATS, TAB_STIM,
    TAB_STIM_PREVIEW,
    apply_mode_to_params, default_params, mode_for_params,
)
from meanap.gui.bundle_worker import BundleWorker
from meanap.gui.pipeline_worker import (
    PipelineWorker, QueueWorker, SharedHelperWorker, SharedMainWorker,
)
from meanap.gui.stats_worker import StatsWorker
from meanap.gui.viewer_session import ViewerSessions
from meanap.gui.widgets import scrollable
from meanap.gui.panels.data import (
    CATNAP_DATA_LABEL, DataPanel, RAW_DATA_LABEL,
)
from meanap.gui.panels.spike_detection import SpikeDetectionPanel
from meanap.gui.panels.connectivity import ConnectivityPanel
from meanap.gui.panels.stim import StimPanel
from meanap.gui.panels.stim_preview import StimPreviewPanel
from meanap.gui.panels.run import QUEUE, SHARED, THIS_RUN, RunPanel
from meanap.gui.panels.catnap import CatNapPanel
from meanap.gui.panels.results import ResultsPanel
from meanap.gui.panels.stats import StatsPanel
from meanap.gui.simple_view import SimpleView
from meanap.gui.settings_search import (
    FEATURE, SETTING, VIEW, Flash, SearchBox, SearchEntry, index_tabs, reveal_widget,
)
from meanap.gui.tooltip import install_tooltip_style, wrap_tooltips
from meanap.gui.tutorial import TutorialOverlay, TutorialStep, tabbar_target
from meanap.frozen import is_frozen
from meanap.gui.versions_dialog import (
    AppVersionDialog, Background, VersionsDialog, dev_builds_wanted, status_summary,
)
from meanap.gui.combo import install_combo_popup_fit
from meanap.gui.wheel import install_wheel_guard


#: QSettings key remembering whether the window was last in the simple view.
SIMPLE_VIEW_KEY = "gui/simple_view"


def load_simple_view_preference() -> bool:
    """Whether to open in the simple view. The classic view is the default."""
    value = QSettings("SAND Lab", "MEA-NAP").value(SIMPLE_VIEW_KEY, False)
    # QSettings hands back the string "false" on some platforms.
    return value if isinstance(value, bool) else str(value).lower() == "true"


def save_simple_view_preference(simple: bool) -> None:
    QSettings("SAND Lab", "MEA-NAP").setValue(SIMPLE_VIEW_KEY, bool(simple))


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


class _QueueFeed(QObject):
    """A queue's progress as the simple view follows a single run's.

    The queue reports ``(index, label, Progress)`` per run; the page wants one
    bar for the whole queue, so the fraction becomes the queue's and the phase
    says which run is going. It finishes with a summary, not a folder.
    """

    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, worker, total: int, parent=None) -> None:
        super().__init__(parent)
        total = max(total, 1)

        def forward(index: int, label: str, snap) -> None:
            self.progress.emit(dataclasses.replace(
                snap, fraction=(index + snap.fraction) / total,
                phase=f"Run {index + 1} of {total}  ·  {snap.phase}",
                detail=f"{label}  ·  {snap.detail}" if snap.detail else label))

        worker.progress.connect(forward)
        worker.finished_all.connect(lambda summary: self.finished_ok.emit((None, summary)))
        worker.failed.connect(self.failed)


class _HelperFeed(QObject):
    """A helper computer's share of a shared run, as the simple view follows it."""

    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, worker, parent=None) -> None:
        super().__init__(parent)
        worker.progress.connect(self.progress)
        worker.finished_ok.connect(lambda status: self.finished_ok.emit(
            (None, "Your share is done. The main computer pools the results."
             if status == "done" else "Stopped.")))
        worker.cancelled.connect(self.cancelled)
        worker.failed.connect(self.failed)


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
        self._bundle_worker: BundleWorker | None = None
        #: True once the user has picked a run for the Stats tab by hand, after
        #: which this session's own run no longer overrides their choice.
        self._stats_source_chosen = False
        self._worker: PipelineWorker | None = None
        self._queue_worker: QueueWorker | None = None
        self._shared_worker: SharedMainWorker | SharedHelperWorker | None = None
        self._tutorial: TutorialOverlay | None = None
        self._viewers = ViewerSessions()
        #: The spike and burst viewer, built the first time it is asked for and
        #: kept afterwards so it holds on to whatever recording it loaded.
        self._spike_viewer = None
        #: The firing-rate change viewer, built on first use and reopened rather
        #: than rebuilt; it unloads its run when closed.
        self._fr_diff_viewer = None
        #: Panels the simple view opens in windows of their own (see _panel_window).
        self._panel_windows: dict[str, QWidget] = {}
        #: The machine report, built on first use and kept so a benchmark
        #: already run is still on screen when it is reopened.
        self._system_report = None
        #: The versions dialog, kept like the system report; and the last
        #: result of checking GitHub, which the version button reflects.
        self._versions_dialog = None
        self._update_status = None

        # A bundle is a file people email each other, so dropping one on the
        # window is the obvious way to open it. Accepted at the window level;
        # see dragEnterEvent for why nothing else is claimed.
        self.setAcceptDrops(True)

        self._build_toolbar()
        self._build_tabs()
        # On the status bar, not the toolbar: the toolbar is already as wide as
        # the default window, and an extra action pushes "This computer" into
        # the overflow chevron. The simple view has its own way back, in its
        # top corner.
        simple_btn = QPushButton("✦  Simple view")
        simple_btn.setFlat(True)
        simple_btn.setObjectName("simpleViewButton")
        simple_btn.setToolTip(
            "One page that asks only for what a run needs, one question at a "
            "time. Every setting on these tabs is kept.")
        simple_btn.clicked.connect(lambda: self._set_simple_view(True))
        self.statusBar().addPermanentWidget(simple_btn)
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
        # A scroll over a spin box or combo box belongs to the page it is on,
        # not to the field the pointer happened to cross — see gui/wheel.py.
        install_wheel_guard()
        # A combo box opens its popup at the width of the box, which is set by
        # the form around it — too narrow for the options once the popup's own
        # check column is taken out of it. See gui/combo.py.
        install_combo_popup_fit()
        # Qt hands focus to the first widget that will take it, so the window
        # opened with a settings field focused that nobody had clicked — and a
        # focused field is one the wheel is allowed to change. The tab strip
        # takes it instead, where the arrow keys move between tabs.
        self._tabs.setFocus(Qt.FocusReason.OtherFocusReason)
        self._set_simple_view(load_simple_view_preference(), remember=False)
        # The tutorial walks the tabs, which the simple view does not show.
        if not self.is_simple_view():
            self._maybe_show_tutorial_on_first_launch()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        # "Reset to defaults", not "New": there is no document to be new, and
        # the one thing the button does is discard the settings on screen.
        act_new = QAction("Reset to defaults", self)
        act_new.setToolTip(
            "Put every setting on every tab back to its default for the "
            "current pipeline. Parameters you saved to a file are untouched."
        )
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

        # In the toolbar rather than on a tab: it is about the computer, not
        # about the analysis, and it is wanted in every mode — most often when
        # a run is slower than someone expected and nobody can say why.
        act_system = QAction("🖥  This computer", self)
        act_system.setToolTip(
            "What this computer is, how much of it a run will use, and how "
            "fast it is — for choosing which machine runs a batch, and for "
            "working out why one of them is slow.")
        act_system.triggered.connect(self._on_show_system_report)

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
        # A button, because it is also the way in to choosing another version
        # and to updating this one — and the place a new version announces
        # itself, which is why the check colours it rather than popping up.
        self._version_label = QToolButton()
        self._version_label.setAutoRaise(True)
        self._version_label.clicked.connect(self._on_show_versions)
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
        tb.addAction(act_system)
        tb.addSeparator()


    def _add_logo(self) -> None:
        """Branding in the tab strip's right-hand corner, not on the toolbar.

        It used to sit at the far end of the toolbar past an expanding spacer,
        which meant it competed for width with the actions: at the default
        window size the spacer took what was left and pushed Tutorial — and
        before that the Mode selector — into the overflow chevron. There is
        always room beside five tabs, and nothing there to be pushed out.
        """
        # The search field shares the corner. The toolbar has no room for it —
        # it is already as wide as the default window on some platforms — and
        # the tab strip has a third of its width spare in every mode.
        corner = QWidget()
        corner.setObjectName("tabCorner")
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self._search_box = SearchBox(self._search_entries)
        self._search_box.setMinimumWidth(190)
        self._search_box.setMaximumWidth(280)
        self._search_box.install_shortcut(self._tabs)
        row.addWidget(self._search_box, 0, Qt.AlignmentFlag.AlignVCenter)
        self._tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        if logo_pixmap(CORNER_LOGO_HEIGHT, self.devicePixelRatioF(), self._mode) is None:
            row.addSpacing(8)
            return
        self._logo_label = _LogoLabel()
        self._logo_label.setContentsMargins(0, 0, 10, 0)
        row.addWidget(self._logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
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

    def _setting_help_area(self) -> QRect:
        """Where a setting's card goes: over the tab below its strip, or in
        the simple view beside the drawer that holds the setting."""
        views = self._views.rect()
        if self._views.currentWidget() is self._tabs:
            return views.adjusted(0, self._tabs.tabBar().height(), 0, 0)
        simple = getattr(self, "_simple_view", None)
        drawer = getattr(simple, "drawer", None)
        if drawer is not None and drawer.is_open():
            panel = drawer.panel.geometry()
            left = drawer.mapTo(self._views, panel.topLeft()).x()
            return QRect(views.left(), views.top(), max(left - views.left(), 320),
                         views.height())
        return views

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        # The tabs and the simple view share the window: one is shown at a time.
        self._views = QStackedWidget()
        self._views.addWidget(self._tabs)
        self.setCentralWidget(self._views)
        self._add_logo()

        self._data_panel = DataPanel()
        self._spike_panel = SpikeDetectionPanel()
        self._spike_panel.open_viewer_requested.connect(self._on_open_spike_viewer)
        self._connectivity_panel = ConnectivityPanel()
        self._stim_panel = StimPanel()
        self._stim_preview_panel = StimPreviewPanel()
        self._catnap_panel = CatNapPanel()
        self._catnap_panel.open_tracking_viewer_requested.connect(
            self._on_open_tracking_viewer)
        self._run_panel = RunPanel()
        # The Run tab holds both pages; these name them for the code that only
        # cares about one — loading parameters, or the queue's list.
        self._pipeline_panel = self._run_panel.settings
        self._queue_panel = self._run_panel.queue
        self._shared_panel = self._run_panel.shared
        # A shared run is created from the settings on the other tabs, read
        # when the wizard opens rather than cached.
        self._shared_panel.params_source = self._collect_params
        self._shared_panel.helper_ready.connect(self._on_shared_helper_ready)
        self._shared_panel.finish_now_requested.connect(self._on_shared_finish_now)
        self._results_panel = ResultsPanel()
        self._results_panel.view_report_requested.connect(self._on_view_report)
        self._results_panel.make_bundle_requested.connect(self._on_make_bundle)
        self._results_panel.open_bundle_requested.connect(self._on_open_bundle)
        self._results_panel.open_fr_diff_requested.connect(self._on_open_fr_diff_viewer)
        self._network_viewer_panel = self._results_panel.viewer
        self._stats_panel = StatsPanel()
        self._stats_panel.run_requested.connect(self._on_run_stats)
        self._stats_panel.open_folder_requested.connect(self._on_open_stats_folder)
        self._stats_panel.choose_source_requested.connect(self._on_choose_stats_source)

        # Every tab is built once and kept alive here; the current mode decides
        # which of them are actually in the QTabWidget (see _apply_mode). Order
        # is the order they appear in, whichever subset is showing.
        self._tab_specs: list[tuple[str, QWidget, str]] = [
            (TAB_DATA, scrollable(self._data_panel), "  Data  "),
            (TAB_SPIKE, scrollable(self._spike_panel), "  Spike detection  "),
            # CAT-NAP before Connectivity: in calcium imaging mode this tab is where the
            # recordings are found and prepared, so it comes before the
            # settings that act on them — the same place Spike detection holds
            # in the ephys modes.
            (TAB_CATNAP, self._catnap_panel, "  CAT-NAP (calcium imaging)  "),
            (TAB_CONNECTIVITY, scrollable(self._connectivity_panel), "  Connectivity  "),
            (TAB_STIM, scrollable(self._stim_panel), "  Stimulation  "),
            (TAB_STIM_PREVIEW, self._stim_preview_panel, "  Stim Preview  "),
            (TAB_RUN, self._run_panel, "  Run  "),
            (TAB_RESULTS, self._results_panel, "  Results  "),
            # Last, because it acts on a run that has already finished — it is
            # the only tab whose input is another tab's output.
            # "&&" because Qt reads a single "&" in a tab label as the marker
            # for a keyboard mnemonic and swallows it.
            (TAB_STATS, scrollable(self._stats_panel), "  Stats && ML  "),
        ]
        from meanap.gui.setting_help import SettingHelp

        # ⓘ on the settings that have a card saying what they do.
        self._setting_help = SettingHelp(self._tabs, self._views, self._setting_help_area)
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
        # Likewise Params.min_activity_level, on both the Spike detection and
        # Connectivity tabs. CAT-NAP hides the former, so an edit made on
        # Connectivity has to reach it or the two would disagree on a switch.
        self._bind_mirrored_spin(
            self._connectivity_panel.min_activity_level,
            self._spike_panel.min_activity_level,
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

        # Built last: its fields mirror the panels above, which must exist.
        self._simple_view = SimpleView(
            self._data_panel, self._stim_panel, self._catnap_panel, self._mode)
        # A setting's card goes with the drawer that showed the setting.
        self._simple_view.drawer.closed.connect(self._setting_help.card.close_card)
        # Whatever the Run tab's switch says: one run, a queue, or a shared run.
        self._simple_view.run_requested.connect(self._on_run_clicked)
        self._simple_view.attach_run_panel(self._run_panel)
        self._simple_view.stop_requested.connect(self._on_stop)
        self._simple_view.classic_requested.connect(
            lambda: self._set_simple_view(False))
        self._simple_view.mode_requested.connect(self._on_mode_requested)
        self._simple_view.view_results_requested.connect(self._on_simple_view_results)
        self._simple_view.show_log_requested.connect(self._on_show_run_log)
        self._simple_view.versions_requested.connect(self._on_show_versions)
        self._refresh_version_label()
        self._simple_view.search_provider = self._search_entries
        self._simple_view.settings_provider = self._settings_areas
        # Express mode is the simple view's default (see _apply_simple_defaults)
        # until someone decides otherwise — by ticking or unticking it, or by
        # loading settings that say. clicked, not toggled: only a person clicks.
        self._express_chosen = False
        self._pipeline_panel.express_mode.clicked.connect(
            lambda _on: setattr(self, "_express_chosen", True))
        results = self._simple_view.results_page
        results.open_requested.connect(self._on_results_page_open)
        results.spike_viewer_requested.connect(self._on_open_spike_viewer)
        results.fr_diff_requested.connect(self._on_results_page_fr_diff)
        results.network_viewer_requested.connect(self._on_results_page_network)
        results.native_viewer_requested.connect(self._on_results_page_native)
        results.stim_preview_requested.connect(self._on_results_page_stim_preview)
        self._views.addWidget(self._simple_view)

    # ── Simple and classic views ──────────────────────────────────────────────

    def is_simple_view(self) -> bool:
        return self._views.currentWidget() is self._simple_view

    def _set_simple_view(self, simple: bool, remember: bool = True) -> None:
        """Show the one-page view or the tabs. Both edit the same settings."""
        if not simple:
            # The panel holds a section borrowed from a tab; the tab needs it.
            self._simple_view.close_section()
        else:
            self._apply_simple_defaults()
        self._views.setCurrentWidget(self._simple_view if simple else self._tabs)
        self._setting_help.card.close_card()
        # The simple view has no use for the toolbar or status bar, and leaving
        # them would undo most of what makes it simple.
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(not simple)
        self.statusBar().setVisible(not simple)
        # The tutorial walks the tabs, so it has nothing to point at here. Set
        # aside, not finished: the classic view still offers it next start.
        if simple and self._tutorial is not None and self._tutorial.isVisible():
            self._tutorial.hide()
        if remember:
            save_simple_view_preference(simple)

    # ── Search ────────────────────────────────────────────────────────────────

    def _search_entries(self) -> list[SearchEntry]:
        """Everything the search can find, from whichever view is showing.

        Built afresh each time the field is used, from the window as it is:
        the current mode's tabs, and only the rows those tabs are showing.
        """
        entries: list[SearchEntry] = []
        if self.is_simple_view():
            # A section open in the panel is away from its tab, where the
            # index looks for it.
            self._simple_view.close_section()
            entries += self._simple_view.search_entries()
        for entry in index_tabs(self._tabs):
            entry.activate = lambda e=entry: self._go_to_setting(e)
            entries.append(entry)
        entries += self._window_features()
        return entries

    def _window_features(self) -> list[SearchEntry]:
        """The toolbar's actions and the switches that are not on any tab."""
        out: list[SearchEntry] = []
        for toolbar in self.findChildren(QToolBar):
            for action in toolbar.actions():
                # Widget actions (the mode selector, the version button) have
                # no text of their own; they are listed by hand below.
                title = action.text().strip(" ?🖥⚙").strip()
                if title and not isinstance(action, QWidgetAction):
                    out.append(SearchEntry(
                        title, "Toolbar", FEATURE, toolbar.widgetForAction(action),
                        lambda a=action: self._run_toolbar_action(a), action.toolTip()))
        simple = self.is_simple_view()
        out.append(SearchEntry(
            "Versions and updates", "Under the logo" if simple else "Toolbar", FEATURE,
            self._simple_view.version_button if simple else self._version_label,
            # The dialog is a window of its own, so neither view need change.
            self._on_show_versions,
            "version update upgrade which version release"))
        out.append(SearchEntry(
            "Pipeline mode", "Toolbar", SETTING, self._mode_combo,
            lambda: self._run_classic(lambda: self._flash(self._mode_combo)),
            "mode MEA-NAP MEA-Stim CAT-NAP pipeline switch calcium stimulation"))
        if self.is_simple_view():
            out.append(SearchEntry(
                "Classic view", "Every setting, on tabs", VIEW, None,
                lambda: self._set_simple_view(False), "tabs all settings classic"))
        else:
            out.append(SearchEntry(
                "Simple view", "One page, one question at a time", VIEW, None,
                lambda: self._set_simple_view(True), "simple one page beginner easy"))
        return out

    #: Settings tabs the simple view's card lists, with the sections on each
    #: that are not settings (run controls, logs, progress) left out.
    _SETTINGS_AREAS = {
        TAB_DATA: ("Recordings and output", frozenset()),
        TAB_SPIKE: ("Spike detection", frozenset()),
        TAB_CATNAP: ("Calcium imaging", frozenset({"Log", "Trace preview", "Suite2p recordings"})),
        TAB_CONNECTIVITY: ("Connectivity and networks", frozenset()),
        TAB_STIM: ("Stimulation", frozenset()),
        TAB_RUN: ("Pipeline steps and output", frozenset({
            "Runs", "Step overview", "Start", "Progress", "Status log", "This shared run"})),
    }

    def _settings_areas(self) -> list:
        """The simple view's card: one area per settings tab this mode shows."""
        from meanap.gui.simple_settings import Area, changed_fields, settings_sections, summarise

        panels = {
            TAB_DATA: self._data_panel, TAB_SPIKE: self._spike_panel,
            TAB_CATNAP: self._catnap_panel, TAB_CONNECTIVITY: self._connectivity_panel,
            TAB_STIM: self._stim_panel, TAB_RUN: self._pipeline_panel,
        }
        params = self._collect_params()
        defaults = default_params(self._mode)
        defaults.express_mode = True  # the simple view's own default
        areas = []
        for key, page, _label in self._tab_specs:
            if key not in self._SETTINGS_AREAS or self._tabs.indexOf(page) < 0:
                continue
            title, exclude = self._SETTINGS_AREAS[key]
            sections = settings_sections(page, exclude)
            if sections:
                areas.append(Area(key, title, sections, summarise(key, params),
                                  changed_fields(panels[key], defaults)))
        return areas

    def _run_classic(self, then) -> None:
        """Do *then* in the classic view, switching to it first if need be."""
        if self.is_simple_view():
            self._set_simple_view(False, remember=False)
        then()

    def _run_toolbar_action(self, action) -> None:
        def run() -> None:
            if action.isCheckable():
                action.toggle()
            else:
                action.trigger()
        self._run_classic(run)

    def _go_to_setting(self, entry: SearchEntry) -> None:
        """Show *entry*'s tab, open whatever folds it away, and mark it."""
        target = entry.target
        if target is None:
            return
        # From the simple view, open the section in its panel rather than
        # leaving the page — if the setting is in a section the card offers.
        if self.is_simple_view() and self._simple_view.open_setting(target):
            if isinstance(target, (QLineEdit, QAbstractSpinBox, QComboBox)) and target.isEnabled():
                target.setFocus(Qt.FocusReason.OtherFocusReason)
            self._flash(target)
            return
        if self.is_simple_view():
            # A detour, not a change of preference: the simple view is still
            # what this person opens to.
            self._set_simple_view(False, remember=False)
        page = getattr(entry, "page", None)
        if page is not None and self._tabs.indexOf(page) >= 0:
            self._tabs.setCurrentWidget(page)
        # The Run tab's pipeline settings are on the "This run" page; picking
        # the page by its radio button keeps the radio and the page in step.
        if self._pipeline_panel.isAncestorOf(target):
            self._run_panel.set_mode(THIS_RUN)
        reveal_widget(target)
        if isinstance(target, (QLineEdit, QAbstractSpinBox, QComboBox)) and target.isEnabled():
            target.setFocus(Qt.FocusReason.OtherFocusReason)
        self._flash(target)

    def _flash(self, target: QWidget) -> None:
        # After the unfolding and scrolling have been laid out, or the outline
        # lands where the widget was rather than where it is.
        def show() -> None:
            reveal_widget(target)
            if target.isVisible():
                Flash(target)
        QTimer.singleShot(0, show)

    def _apply_simple_defaults(self) -> None:
        """Defaults the simple view has that the tabs do not: express mode on.

        Its figures are the quick ones, which is what a first look at a run
        needs. Left alone once someone has chosen either way.
        """
        if not self._express_chosen:
            self._pipeline_panel.express_mode.setChecked(True)
        self._simple_view.refresh_settings()

    def _on_mode_requested(self, key: str) -> None:
        """Switch pipeline from the simple view, through the same path as the combo."""
        if key != self._mode:
            self._apply_mode(key)

    def _on_show_run_log(self) -> None:
        """The Run tab's status log — in the simple view's panel when it is showing."""
        if self.is_simple_view():
            self._simple_view.open_log(self._run_panel.log.parentWidget(), self._run_panel.log)
            return
        self._tabs.setCurrentIndex(self._tab_index(TAB_RUN))

    # ── Opening finished runs ────────────────────────────────────────────────

    def open_results(self, paths: list) -> None:
        """Show runs handed to MEA-NAP from outside: double-clicked, or sent by
        a second copy of MEA-NAP that was started with them.

        The window goes to the simple view's **View results** page, whichever
        view was showing, because that is where the run's viewers are; the
        choice of view is not remembered, so the next ordinary start opens the
        view the person picked.
        """
        from meanap.gui.simple_results import is_results_source

        sources = [Path(p) for p in paths if is_results_source(Path(p))]
        if not sources:
            return
        self._set_simple_view(True, remember=False)
        # The page and the results window hold one run at a time: the last.
        self._simple_view.show_results(sources[-1])
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_results_page_open(self, path: str, query: str) -> None:
        """The page's "Open in browser instead": the web viewer, for what only it has."""
        source = Path(path)
        if self._open_in_browser(source, query=query):
            self._simple_view.results_page.note_opened(
                path, self._viewers.url_for(source))

    def _on_results_page_fr_diff(self, path: str) -> None:
        from meanap.gui.fr_diff_viewer import FrDiffViewerWindow

        if self._fr_diff_viewer is None:
            self._fr_diff_viewer = FrDiffViewerWindow(self)
        self._fr_diff_viewer.set_source(Path(path), chosen=True)
        self._fr_diff_viewer.show()
        self._fr_diff_viewer.raise_()
        self._fr_diff_viewer.activateWindow()

    def _panel_window(self, key: str, title: str, make):
        """A separate window holding a panel the tabs also show, made once.

        The simple view has no tabs, so its network viewer and stimulation
        preview open in windows of their own. Each is its own copy of the
        panel, independent of the one on the tab, and is reopened rather than
        rebuilt, keeping whatever it had loaded.
        """
        window = self._panel_windows.get(key)
        if window is None:
            window = QWidget(self, Qt.WindowType.Window)
            window.setWindowTitle(title)
            layout = QVBoxLayout(window)
            layout.setContentsMargins(6, 6, 6, 6)
            window.panel = make()
            layout.addWidget(window.panel)
            window.resize(1200, 800)
            self._panel_windows[key] = window
        window.show()
        window.raise_()
        window.activateWindow()
        return window.panel

    def _on_results_page_network(self, path: str) -> None:
        from meanap.gui.panels.network_viewer import NetworkViewerPanel

        panel = self._panel_window("network", "MEA-NAP · Network viewer", NetworkViewerPanel)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            panel.load_run(path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self._panel_windows["network"],
                                "Could not open the run's networks", str(e))
            return
        QApplication.restoreOverrideCursor()

    def _on_results_page_native(self, path: str, query: str = "") -> None:
        if self._open_in_viewer(Path(path), query=query):
            self._simple_view.results_page.note_opened(path, None)

    def _on_results_page_stim_preview(self) -> None:
        panel = self._panel_window("stim_preview", "MEA-Stim · Stimulation preview",
                                   StimPreviewPanel)
        params = self._collect_params()
        panel.load_defaults(params)
        panel.start_dir = params.raw_data or ""

    def _on_simple_view_results(self) -> None:
        """The simple view's **View results** after a run: that run, on its page."""
        root = self._last_output_root or self._candidate_output_root()
        bundle = self._last_bundle
        if bundle is None and root is not None:
            candidate = Path(root).with_suffix(BUNDLE_SUFFIX)
            bundle = candidate if candidate.is_file() else None
        source = bundle if bundle is not None and Path(bundle).is_file() else root
        if source is None or not Path(source).exists():
            self._on_view_report()  # explains what is missing
            return
        self._simple_view.show_results(source)

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

    @staticmethod
    def _bind_mirrored_spin(first: QDoubleSpinBox,
                            second: QDoubleSpinBox) -> None:
        """Keep two spin boxes showing the same value, in both directions."""
        # setValue() emits only on a real change, so the pair cannot loop.
        first.valueChanged.connect(second.setValue)
        second.valueChanged.connect(first.setValue)
        second.setValue(first.value())

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
        self._results_panel.set_stim_tools_visible(mode_key == "meastim")

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
        # A panel may have relabelled itself for the mode ("events/s").
        help_ = getattr(self, "_setting_help", None)
        if help_ is not None:
            help_.attach()
        simple = getattr(self, "_simple_view", None)
        if simple is not None:
            simple.set_mode(mode_key)
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

        status = self._update_status
        fresh = status is not None and status.update_available
        text = f"v{pipeline_version(self._mode)}"
        label.setText(text + ("  ⬆ update" if fresh else ""))
        simple = getattr(self, "_simple_view", None)
        label.setStyleSheet("" if fresh else "color: palette(mid);")
        every = all_versions()
        from meanap.version import build_label

        build = build_label()
        tip = ((f"Build: {build}\n\n" if build else "")
               + "Versions in this install:\n"
               + "\n".join(f"  {PIPELINE_NAMES[k]} {every[k]}" for k in PIPELINE_NAMES)
               + "\n\nThe running pipeline's version is written into every run's "
                 "params.json and bundle manifest.")
        if status is not None:
            tip += "\n\n" + status_summary(status)
        tip += ("\n\nClick to update MEA-NAP"
                + ("." if is_frozen() else " or choose another version."))
        label.setToolTip(tip)
        if simple is not None:
            newer = getattr(status, "newer_version", None) if fresh else None
            simple.set_version(text, (
                f"{text}  ·  {newer} available ⬆" if newer
                else f"{text}  ·  update available ⬆" if fresh else ""), tip)

    # ── This computer's speed, for time estimates ─────────────────────────────

    #: How long after the window opens the one-off speed check starts: past
    #: start-up, so the window is responsive first.
    SPEED_CHECK_DELAY_MS = 5000

    def start_speed_check(self, delay_ms: int | None = None) -> bool:
        """Benchmark this computer once, in the background, if it never has been.

        The benchmark (:mod:`meanap.shared.benchmark`) lets a first run's time
        estimate know how this computer compares at spike detection and at
        network work, and put a number on step 1 before it starts. Called by
        ``app.main`` only, like the update check, so a test's window never
        starts one. Returns whether one was scheduled.
        """
        from meanap.pipeline.step_times import for_this_computer

        times = for_this_computer()
        if times is None or times.benchmark is not None:
            return False
        QTimer.singleShot(self.SPEED_CHECK_DELAY_MS if delay_ms is None else delay_ms,
                          self._begin_speed_check)
        return True

    def _begin_speed_check(self) -> None:
        # A run already going would slow the benchmark and be slowed by it;
        # this run will be timed anyway, and the check waits for next time.
        if self._busy():
            return
        from meanap.gui.speed_check import SpeedCheck

        self._speed_check = SpeedCheck(self)
        self._speed_check.finished_check.connect(self._on_speed_checked)
        self.statusBar().showMessage(
            "Timing this computer once, for run time estimates (about 15 s)…", 20000)
        self._speed_check.start()

    def _on_speed_checked(self, result) -> None:
        # Timed alongside a run, it measured a busy computer: not kept.
        if result is None or self._busy():
            self.statusBar().clearMessage()
            return
        from meanap.shared.benchmark import remember_benchmark

        remember_benchmark(result)
        self.statusBar().showMessage(
            "This computer's speed is noted; run time estimates will use it.", 8000)

    # ── Versions and updates ──────────────────────────────────────────────────

    def start_update_check(self) -> None:
        """Ask GitHub, in the background, whether this copy is current.

        Called by ``app.main`` rather than from ``__init__``, so that a window
        built by a test or embedded somewhere never reaches for the network.
        Failures are quiet: offline is normal, and the version button simply
        stays as it was.
        """
        from meanap import updates

        if is_frozen():
            include_dev = dev_builds_wanted()
            job = Background(lambda: updates.check_app(include_dev=include_dev), self)
        else:
            job = Background(updates.check, self)
        job.done.connect(self._on_update_status)
        job.start()
        self._update_job = job

    def report_app_update(self) -> None:
        """Say how the update the app installed before this start went."""
        if not is_frozen():
            return
        from meanap import app_update

        outcome = app_update.take_outcome()
        if outcome is None:
            return
        if outcome.ok:
            self.statusBar().showMessage(outcome.message, 15000)
        else:
            QMessageBox.warning(self, "MEA-NAP update", outcome.message)

    def _on_update_status(self, status) -> None:
        self._update_status = status
        self._refresh_version_label()
        if self._versions_dialog is not None:
            self._versions_dialog.set_status(status)

    def _on_show_versions(self) -> None:
        if self._versions_dialog is None and is_frozen():
            self._versions_dialog = AppVersionDialog(
                self, is_busy=self._busy, on_quit=self.close)
            self._versions_dialog.status_changed.connect(self._on_update_status)
            if self._update_status is not None:
                self._versions_dialog.set_status(self._update_status)
            else:
                self._versions_dialog.refresh()
        if self._versions_dialog is None:
            self._versions_dialog = VersionsDialog(
                self,
                checkout=(self._update_status.checkout
                          if self._update_status is not None else None),
                is_busy=self._busy,
                restart_args=lambda: ("--mode", self._mode),
                on_restart=self.close,
            )
            self._versions_dialog.status_changed.connect(self._on_update_status)
            if self._update_status is not None:
                self._versions_dialog.set_status(self._update_status)
            else:
                self._versions_dialog.refresh()
        self._versions_dialog.show()
        self._versions_dialog.raise_()
        self._versions_dialog.activateWindow()

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
        self._tutorial.start(self._mode)

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
                "opens the run's figures — an HTML gallery of every figure, or the "
                "results viewer if it was an express run — and the network viewer below explores "
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
                "Turn on CAT-NAP", "CAT-NAP analyses calcium imaging. On the "
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
        # ephys tabs while the run does calcium imaging.
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
        if hasattr(self, "_simple_view"):
            self._simple_view.refresh_settings()

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
        if ask_yes_no(self, "Reset to defaults",
                      "Reset all parameters to defaults?"):
            # Defaults for the pipeline on screen, not for MEA-NAP: resetting
            # in CAT-NAP should not quietly drop you back into the ephys tabs
            # with ephys-scaled lags.
            params = default_params(self._mode)
            self._params = params
            self._express_chosen = False
            self._load_params(self._params)
            if self.is_simple_view():
                self._apply_simple_defaults()

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
            self._express_chosen = True  # the file says, either way
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
        # The layout comes from the files rather than from whatever the window
        # last held: the example is an Axion 8×8 well, and run as MCS60 its
        # networks were drawn upside down with the corner electrodes dropped.
        from meanap.pipeline.recording_probe import detect_layout, probe_folder
        guess = detect_layout(probe_folder(example_dir))
        if guess.layout:
            self._data_panel.channel_layout.setCurrentText(guess.layout)
            if len(set(guess.rates)) == 1:
                self._data_panel.fs.setValue(guess.rates[0])
            # Each format's loader returns its own unit: volts for Axion, µV
            # for MCS. Only the plots' scale depends on it.
            unit = "V" if guess.layout.startswith("Axion") else "uV"
            self._data_panel.potential_difference_unit.setCurrentText(unit)
            log(f"Electrode layout: {guess.layout}. {guess.reason}")
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
        mode = self._run_panel.mode()
        if mode == QUEUE:
            self._on_run_queue()
        elif mode == SHARED:
            self._on_run_shared()
        else:
            self._on_run()

    def _busy(self) -> bool:
        return ((self._worker is not None and self._worker.isRunning())
                or (self._queue_worker is not None
                    and self._queue_worker.isRunning())
                or (self._shared_worker is not None
                    and self._shared_worker.isRunning()))

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
        self._simple_view.track_run(worker)
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
        # Not "Use <name>": QMessageBox sizes itself to its text and then
        # squeezes the buttons into that, which cut a dated name down to its
        # middle ("…putData12Nov…") and hid the _v2 that is the whole point.
        # The name is in bold just above, where it has room.
        use_new = box.addButton("Save as new folder", QMessageBox.ButtonRole.AcceptRole)
        # The third option is the one a stopped run actually wants: fill in the
        # recordings that never finished rather than redo the ones that did.
        continue_it = box.addButton("Continue it",
                                    QMessageBox.ButtonRole.ActionRole)
        overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(use_new)
        for button in box.buttons():
            button.setMinimumWidth(button.sizeHint().width())
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
        self._simple_view.track_run(_QueueFeed(worker, len(paths), self))
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

    # ── Shared runs ───────────────────────────────────────────────────────────

    def _on_run_shared(self) -> None:
        """Start (or resume) a shared run as the main computer."""
        from meanap.shared.workspace import DONE as SHARED_DONE

        if self._busy():
            return
        panel = self._shared_panel
        ws = panel.workspace
        if ws is None or panel.role != "main":
            return
        try:
            run = ws.read()
            if run.status == SHARED_DONE:
                return
            if not run.started:
                assignment = panel.assignment()
                if any(n < 0 for n in map(len, assignment.values())) or \
                        len(assignment.get(run.main, [])) < 0:
                    raise ValueError("The recording counts do not add up.")
                empty = [m for m, recs in assignment.items() if not recs]
                if empty:
                    self._run_panel.append_log(
                        f"Note: {', '.join(empty)} will get no recordings with this split.")
                ws.start(assignment)
                self._run_panel.append_log(
                    "Shared run started: " + "; ".join(
                        f"{m}: {len(recs)}" for m, recs in assignment.items()))
            else:
                self._run_panel.append_log("Resuming the shared run.")
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Could not start the shared run", str(e))
            return

        self._params = panel.params
        self._run_panel.set_running(True)
        self._run_panel.start_progress()
        worker = SharedMainWorker(
            ws, panel.machine_name, panel.output_folder, panel.output_name,
            parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.progress.connect(self._run_panel.show_progress)
        worker.finished_ok.connect(self._on_shared_main_finished)
        worker.cancelled.connect(self._on_shared_cancelled)
        worker.failed.connect(self._on_shared_failed)
        # Same signals as a single run's worker: the pooled output is the run.
        self._simple_view.track_run(worker)
        self._shared_worker = worker
        worker.start()
        panel.refresh()

    def _on_shared_helper_ready(self, ws, name: str, raw_data) -> None:
        """This computer joined as a helper: wait for the start, do the share."""
        if self._busy():
            QMessageBox.information(
                self, "Something is already running",
                "Stop the current run before joining a shared one.")
            return
        self._run_panel.set_mode(SHARED)
        self._run_panel.set_running(True)
        self._run_panel.start_progress()
        self._run_panel.progress_label.setText("Waiting for the main computer to start…")
        worker = SharedHelperWorker(ws, name, raw_data, parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.progress.connect(self._run_panel.show_progress)
        worker.finished_ok.connect(self._on_shared_helper_finished)
        worker.cancelled.connect(self._on_shared_cancelled)
        worker.failed.connect(self._on_shared_failed)
        self._simple_view.track_run(_HelperFeed(worker, self))
        self._shared_worker = worker
        worker.start()

    def _on_shared_finish_now(self) -> None:
        worker = self._shared_worker
        if isinstance(worker, SharedMainWorker) and worker.isRunning():
            self._run_panel.append_log(
                "Finishing now — whatever the other computers have not done "
                "will be analysed here.")
            worker.request_finish_now()

    def _on_shared_main_finished(self, output_root: Path) -> None:
        self._shared_worker = None
        self._shared_panel.mark_finished(f"Finished. Pooled results: {output_root}")
        self._on_pipeline_finished(output_root)

    def _on_shared_helper_finished(self, status: str) -> None:
        self._shared_worker = None
        done = status == "done"
        self._shared_panel.mark_finished(
            "This computer's share is done — the main computer collects it."
            if done else f"This computer's part ended: {status}.")
        self._run_panel.finish_progress("Your share is done." if done else "Stopped.")
        self._reset_run_buttons()

    def _on_shared_cancelled(self) -> None:
        self._shared_worker = None
        self._run_panel.finish_progress("Stopped.")
        self._run_panel.append_log("Shared run stopped on this computer.")
        self._reset_run_buttons()
        self._shared_panel.refresh()

    def _on_shared_failed(self, message: str) -> None:
        self._shared_worker = None
        self._run_panel.finish_progress("Failed.")
        self._run_panel.append_log(f"ERROR: {message}")
        self._reset_run_buttons()
        self._shared_panel.refresh()
        QMessageBox.critical(self, "Shared run error", message)

    def _on_stop(self) -> None:
        """Stop whichever of the three is running — again, one button for all."""
        if self._shared_worker is not None and self._shared_worker.isRunning():
            panel = self._shared_panel
            if isinstance(self._shared_worker, SharedMainWorker):
                # The main computer stopping ends the run for everyone: the
                # helpers watch the shared folder and stop at their next
                # recording. The parts they wrote stay, so a later Start
                # resumes rather than restarts.
                from meanap.shared.workspace import CANCELLED as SHARED_CANCELLED
                try:
                    if panel.workspace is not None:
                        panel.workspace.set_status(SHARED_CANCELLED)
                except (ValueError, OSError):
                    pass
                self._run_panel.append_log(
                    "Stop requested — the helpers will stop after their current "
                    "recording too.")
            else:
                self._run_panel.append_log(
                    "Stop requested — finishing the current recording, then halting. "
                    "The main computer will see this computer stopped.")
            self._run_panel.stop_btn.setEnabled(False)
            self._shared_worker.request_cancel()
        elif self._queue_worker is not None and self._queue_worker.isRunning():
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
        # The CAT-NAP panel's cell-viewer button reads this to find the run's
        # CellTracking folder; without it the button can never enable.
        self._catnap_panel.set_output_root(output_root)
        self._run_panel.finish_progress("Finished.")
        self._run_panel.append_log(f"Done. Output folder: {output_root}")
        self._announce_bundle(output_root)
        self._reset_run_buttons()
        self._refresh_results_target()
        # A display only: a failure redrawing it must not stop the hand-off to
        # step 5 (an uncaught error in a Qt slot aborts the app).
        try:
            self._refresh_fr_diff_source()
        except Exception as e:
            self._run_panel.append_log(f"Warning: could not refresh the ΔFR viewer: {e}")
        if self._start_optional_stats(output_root):
            return
        # The log is what someone is looking at when a run ends, and the thing
        # to do next is now on a different tab.
        self._run_panel.append_log(
            "Open the results on the Results tab, or explore the networks there.")

    def _start_optional_stats(self, output_root: Path) -> bool:
        """Carry on into step 5, if the run asked for it. Did it start?

        The settings are the Stats tab's own — ticking the box on the Run tab
        means "and then do what that tab is set up to do", rather than adding
        a second, quietly different set of statistics settings to keep in step.
        """
        if self._params is None or STATS_STEP not in self._params.optional_steps_to_run:
            return False
        if self._stats_worker is not None and self._stats_worker.isRunning():
            self._run_panel.append_log(
                "Statistics are already running from the Stats && ML tab — "
                "leaving them to finish rather than starting a second pass.")
            return False

        # Point the tab at the run that just finished before reading its
        # settings: the density sweep is only offered for a source that has
        # the adjacency matrices, so the settings depend on the source.
        self._stats_panel.set_source(output_root)
        self._stats_panel.clear_log()
        self._stats_panel.set_result(None)
        self._stats_panel.set_running(True)

        rule = "─" * 68
        self._run_panel.append_log(
            f"\n{rule}\n  Optional step: statistics and machine learning\n{rule}")

        worker = StatsWorker(output_root, None, self._stats_panel.settings(),
                             parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.log_message.connect(self._stats_panel.append_log)
        worker.finished_ok.connect(self._on_optional_stats_finished)
        worker.failed.connect(self._on_optional_stats_failed)
        worker.finished.connect(lambda: self._stats_panel.set_running(False))
        self._stats_worker = worker
        worker.start()
        return True

    def _on_optional_stats_finished(self, result) -> None:
        self._on_stats_finished(result)
        self._run_panel.append_log(
            f"Statistics done — {len(result.tables)} table(s), "
            f"{len(result.figures)} figure(s) in {result.dest}")
        self._run_panel.append_log(
            "Open the results on the Results tab, or the statistics on the "
            "Stats && ML tab.")

    def _on_optional_stats_failed(self, message: str) -> None:
        # Only the statistics failed; the run itself finished and its output is
        # on disk, so this must not be reported as a failed run.
        self._stats_panel.append_log(f"ERROR: {message}")
        self._run_panel.append_log(
            f"ERROR: the statistics step failed: {message}\n"
            "The run itself finished — its output folder is complete, and the "
            "Stats && ML tab can retry against it.")

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

    def _on_make_bundle(self) -> None:
        """Pack this run's output folder into one shareable ``.meanap`` file.

        A bundle used to be something you asked for before the run, by ticking
        Express mode. A full run that turned out to be worth sending therefore
        had no way to become one — the data was all there on disk, and the only
        route to the file was to run the analysis again. This is that route
        without the run.
        """
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            return

        output_root = self._candidate_output_root()
        if output_root is None or not output_root.is_dir():
            # The reason this button exists is a run finished weeks ago that
            # now needs sending, and the session that wants to send it has no
            # run in it and no reason to have set the Data tab. So ask, the
            # way Open bundle… asks — a dead button here would refuse exactly
            # the case it was added for.
            chosen = QFileDialog.getExistingDirectory(
                self, "Make bundle, step 1 of 2: choose the output folder to pack",
                str(output_root.parent) if output_root is not None else "",
            )
            if not chosen:
                return
            output_root = Path(chosen)

        # Checked before asking where to save: finding out afterwards that
        # there was never going to be a bundle spends a dialog for nothing.
        reason = unbundlable_reason(output_root)
        if reason is not None:
            QMessageBox.warning(self, "Nothing to pack in that folder", reason)
            return

        # Two file dialogs back to back read as one that did not take: the
        # folder dialog closes and a second, different-looking one opens with
        # no word on whether the folder was accepted. Say it was, and what
        # comes next — this also names the folder when it was the run's own
        # and no dialog was shown at all.
        if not self._confirm_bundle_source(output_root):
            return

        # A save dialog rather than a silent write: it offers the default name,
        # lets the bundle be put somewhere else entirely, and asks before
        # overwriting — which matters here, because the file being overwritten
        # may be an express run whose folder is long gone.
        path, _ = QFileDialog.getSaveFileName(
            self, "Make bundle, step 2 of 2: save the .meanap file as",
            str(default_bundle_dest(output_root)),
            f"MEA-NAP bundles (*{BUNDLE_SUFFIX})",
        )
        if not path:
            return
        dest = Path(path)
        if dest.suffix != BUNDLE_SUFFIX:
            # Typing a name without the extension is normal; a bundle without it
            # is not opened by the file dialog that looks for one.
            dest = dest.with_name(dest.name + BUNDLE_SUFFIX)

        self._results_panel.set_bundling(True)
        worker = BundleWorker(output_root, dest, parent=self)
        worker.log_message.connect(self._run_panel.append_log)
        worker.finished_ok.connect(self._on_bundle_finished)
        worker.failed.connect(self._on_bundle_failed)
        worker.finished.connect(lambda: self._results_panel.set_bundling(False))
        self._bundle_worker = worker
        worker.start()

    def _confirm_bundle_source(self, output_root: Path) -> bool:
        """Confirm the folder to pack, and say a save dialog comes next."""
        box = QMessageBox(
            QMessageBox.Icon.Information, "Output folder selected",
            f"✓ Ready to pack <b>{output_root.name}</b><br>"
            f"<span style='color: gray;'>{output_root.parent}</span><br><br>"
            f"Next, choose where to save the bundle, a single "
            f"<b>{BUNDLE_SUFFIX}</b> file. It is suggested beside the folder; "
            f"the folder itself is not changed.",
            QMessageBox.StandardButton.Cancel, self,
        )
        box.setTextFormat(Qt.TextFormat.RichText)
        next_btn = box.addButton("Choose where to save…", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(next_btn)
        box.exec()
        return box.clickedButton() is next_btn

    def _on_bundle_finished(self, result) -> None:
        """Say what was written, and offer to open it.

        Deliberately does *not* make the new bundle this session's bundle: for
        a full run the output folder still holds every figure, and View report
        should go on meaning the HTML report rather than quietly switching to
        the viewer because a file was packed. If the bundle took the default
        name beside the folder, :meth:`_refresh_results_target` finds it anyway
        and the label says so.
        """
        for warning in result.warnings:
            self._run_panel.append_log(f"  ! {warning}")
        self._refresh_results_target()

        box = QMessageBox(
            QMessageBox.Icon.Information, "Bundle written",
            f"{result.dest.name} — {result.size_mb:.1f} MB, "
            f"{result.recordings} recording"
            f"{'' if result.recordings == 1 else 's'}.\n\n{result.dest}\n\n"
            "The output folder is unchanged.",
            QMessageBox.StandardButton.Close, self,
        )
        open_btn = box.addButton("Open in viewer",
                                 QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_in_viewer(result.dest)

    def _on_bundle_failed(self, message: str) -> None:
        self._run_panel.append_log(f"ERROR: could not pack the bundle: {message}")
        QMessageBox.critical(self, "Could not pack the bundle", message)

    # ── The spike and burst viewer ────────────────────────────────────────────

    def _on_show_system_report(self) -> None:
        """Open the machine report, reusing the window if it is already up."""
        from meanap.gui.system_report import SystemReportDialog

        if self._system_report is None:
            self._system_report = SystemReportDialog(self)
        else:
            # Free memory moves while the window sits open, and the worker
            # counts move with it, so a reopen re-reads rather than showing
            # what was true the first time.
            self._system_report._on_refresh()
        self._system_report.show()
        self._system_report.raise_()
        self._system_report.activateWindow()

    def _on_open_spike_viewer(self) -> None:
        """Open the viewer on the settings this window currently holds.

        One window, reopened rather than replaced: a viewer holds a loaded
        recording, and a second click while one is open means "show me that
        again", not "load those gigabytes a second time".
        """
        from meanap.gui.spike_viewer import SpikeViewerWindow

        if self._spike_viewer is None:
            self._spike_viewer = SpikeViewerWindow(self)
            self._spike_viewer.settings_accepted.connect(
                self._on_spike_viewer_settings)
            self._spike_viewer.load_defaults(self._collect_params())
        self._spike_viewer.show()
        self._spike_viewer.raise_()
        self._spike_viewer.activateWindow()

    def _on_open_fr_diff_viewer(self) -> None:
        """Open the firing-rate change viewer on this session's run.

        One window, reopened rather than replaced, like the spike viewer. It
        unloads its run when closed, so it opens afresh: this session's
        run, read now, with the lab's parameters.
        """
        from meanap.gui.fr_diff_viewer import FrDiffViewerWindow

        if self._fr_diff_viewer is None:
            self._fr_diff_viewer = FrDiffViewerWindow(self)
        self._refresh_fr_diff_source(opening=True)
        self._fr_diff_viewer.show()
        self._fr_diff_viewer.raise_()
        self._fr_diff_viewer.activateWindow()

    def _refresh_fr_diff_source(self, *, opening: bool = False) -> None:
        """Point an open viewer at this session's run, unless it chose its own.

        The same rule as the Stats tab: the bundle an express run left, else
        the run's folder, else the folder the settings name. A closed viewer
        is left empty — it reads the run when next opened (``opening``).
        """
        viewer = self._fr_diff_viewer
        if (viewer is None or (not opening and not viewer.isVisible())
                or viewer.source_chosen()):
            return
        bundle = self._last_bundle
        root = self._candidate_output_root()
        source = bundle if bundle is not None else root
        viewer.set_source(Path(source) if source is not None and Path(source).exists()
                          else None)

    def _on_open_tracking_viewer(self, chain: str) -> None:
        """Open the last run's folder in the results viewer, on *chain*'s cells."""
        from urllib.parse import urlencode

        root = self._last_output_root
        if root is None:
            QMessageBox.information(
                self, "No run to view", "Run the pipeline with cell tracking "
                "enabled first, or open a bundle that carries tracking results.")
            return
        self._open_in_viewer(Path(root), query=urlencode(
            {"tab": "tracking", "chain": chain}))

    def _on_spike_viewer_settings(self) -> None:
        """Take the viewer's detection and burst settings onto the tabs."""
        if self._spike_viewer is None:
            return
        params = self._collect_params()
        self._spike_viewer.apply_to(params)
        self._spike_panel.load(params)
        self._tabs.setCurrentIndex(max(self._tab_index(TAB_SPIKE), 0))
        self.statusBar().showMessage(
            "Spike and burst settings updated from the viewer.", 5000)

    def _on_open_bundle(self) -> None:
        start_dir = str(self._last_bundle.parent) if self._last_bundle else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a MEA-NAP run bundle", start_dir,
            f"MEA-NAP bundles (*{BUNDLE_SUFFIX})",
        )
        if path:
            self._open_in_viewer(Path(path))

    def _open_in_viewer(self, source: Path, *, query: str = "") -> bool:
        """Open *source* in the results viewer, in a window of this app.

        ``query`` is the web viewer's way of saying where to land:
        ``tab=tracking`` (with ``chain=…``) opens on the cell-tracking page.
        Returns whether it opened; a run that cannot be read is reported.
        """
        from urllib.parse import parse_qs

        from meanap.gui.results_viewer import ResultsViewer

        panel = self._panel_window("results_native", "MEA-NAP · Results", ResultsViewer)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            panel.load_run(source)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self._panel_windows["results_native"],
                                "Could not open the run", f"{source}\n\n{e}")
            return False
        QApplication.restoreOverrideCursor()
        wanted = parse_qs(query)
        if wanted.get("tab") == ["tracking"]:
            panel.show_tracking()
            chain = (wanted.get("chain") or [None])[0]
            if chain:
                try:
                    panel.tracking.show_chain(chain)
                except KeyError:        # not in this run: its first chain, then
                    pass
        return True

    def _open_in_browser(self, source: Path, *, query: str = "") -> bool:
        """Serve *source* in the local viewer and open a browser on it.

        Reading a bundle means extracting and parsing it, which is quick but
        not instant, so the wait is shown rather than looking like a click that
        did nothing. ``query`` is appended to the URL, so a caller can land the
        browser on a particular tab. Returns whether it opened.
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
        webbrowser.open(url + ("?" + query if query else ""))
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
        if self.is_simple_view():
            self.open_results(bundles)
            return
        # One results window, so of several the last is the one shown.
        self._open_in_viewer(bundles[-1])

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
        # Likewise for packing, which is one zip write with no checkpoints in
        # it. Waiting also means the bundle is either finished or removed by
        # its own verification, never left half-written by a closing window.
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            self._bundle_worker.wait(30000)
        # The speed check is 10-20 s with no checkpoints; its result is
        # dropped, and it is tried again next time.
        speed = getattr(self, "_speed_check", None)
        if speed is not None and speed.isRunning():
            speed.discard = True
            speed.wait(30000)
        # Each viewer holds a port and a temporary extraction directory; both
        # live as long as the process unless handed back here.
        self._viewers.close_all()
        network = self._panel_windows.get("network")
        if network is not None:
            network.panel.close_run()  # removes an extracted bundle
        native = self._panel_windows.get("results_native")
        if native is not None:
            native.panel.close_run()  # removes an extracted bundle
        for window in self._panel_windows.values():
            window.close()
        # The spike viewer is a child window with its own threads, and a child
        # left open keeps the process alive after the main window has gone.
        if self._spike_viewer is not None:
            self._spike_viewer.close()
        if self._system_report is not None:
            self._system_report.close()
        super().closeEvent(event)
