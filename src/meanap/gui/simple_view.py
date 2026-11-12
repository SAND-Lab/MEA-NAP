"""The simple view: one page that asks only for what a run needs.

The tabbed window shows every setting at once. This page shows one question at
a time instead: the pipeline's logo, then the recordings folder, then the
spreadsheet, and so on. When an answer checks out, a green tick appears beside
the field, the field fades into a one-line summary, and the next question comes
up. Every other setting keeps the value the tabbed window holds for it.

A second page, **View results** (:mod:`meanap.gui.simple_results`), opens a
finished run instead: a ``.meanap`` bundle or a results folder, in the viewers
the pipeline has.

The page owns no settings of its own. Each field is mirrored onto the matching
widget in the tabbed window, so ``MainWindow._collect_params`` reads the run's
settings from one place whichever view filled them in, and switching between
the two views never loses an edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QSignalBlocker, QSize, Qt, QTimer, QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMenu, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from meanap.gui.branding import logo_pixmap
from meanap.gui.modes import MODES
from meanap.params import is_remote_url
from meanap.gui.simple_results import ResultsPage, viewers_for
from meanap.gui.simple_settings import SETTINGS_QSS, Section, SectionDrawer, SettingsCard
from meanap.gui.settings_search import (
    SETTING, VIEW, Flash, SearchBox, SearchEntry, reveal_widget,
)
from meanap.gui.simple_checks import (
    Check, check_output_folder, check_recording_settings, check_recordings_folder,
    check_spreadsheet, describe_rates, recording_names,
)
from meanap.gui.run_clock import RunClock
from meanap.gui.panels.run import QUEUE, SHARED, THIS_RUN

__all__ = ["SimpleView", "StepCard"]

#: How long a new tick stays on a field before it fades into its summary, so
#: the person sees the check pass rather than the field vanishing.
TICK_HOLD_MS = 650
FADE_MS = 280
#: Wait this long after the last keystroke before checking a typed path.
DEBOUNCE_MS = 350

#: The "Run on" choices, in the Run tab's terms.
RUN_ON_CHOICES = (
    ("this_run", "This computer"),
    ("queue", "A queue of saved runs"),
    ("shared", "Several computers (shared folder)"),
)
DONE_OPACITY = 0.55
LOGO_HEIGHT = 84
COLUMN_WIDTH = 560

_OK = "#16a34a"
_WARN = "#d97706"
_ERROR = "#dc2626"
_MUTED = "#6b7280"
_INK = "#111827"
_LINE = "#e5e7eb"
_ACCENT = "#4f8ef7"

_QSS = f"""
#simpleView, #simpleColumn {{ background: #f7f8fa; }}
/* Set on this page only, so a bare type rule: the id rules below outrank it. */
QLabel {{ color: {_INK}; }}
#stepCard {{
    background: #ffffff;
    border: 1px solid {_LINE};
    border-radius: 14px;
}}
#stepCard[state="active"] {{ border: 1px solid #c7d7f8; }}
#stepDetails, #stepRow {{ background: transparent; }}
#stepTitle {{ font-size: 15px; font-weight: 600; }}
#stepHint, #simpleCaption {{ color: {_MUTED}; font-size: 12px; }}
#stepSummary {{ color: {_MUTED}; font-size: 13px; }}
#stepSummary[state="warn"] {{ color: {_WARN}; }}
#stepStatus {{ font-size: 12px; }}
#stepStatus[state="ok"] {{ color: {_OK}; }}
#stepStatus[state="warn"] {{ color: {_WARN}; }}
#stepStatus[state="error"] {{ color: {_ERROR}; }}
#stepBadge {{
    border-radius: 13px;
    font-weight: 600;
    font-size: 12px;
    color: {_MUTED};
    background: #eef0f3;
}}
#stepBadge[state="ok"] {{ color: #ffffff; background: {_OK}; }}
#stepBadge[state="warn"] {{ color: #ffffff; background: {_WARN}; }}
#stepBadge[state="active"] {{ color: #ffffff; background: {_ACCENT}; }}
#stepCard QLineEdit, #stepCard QComboBox, #stepCard QDoubleSpinBox {{
    min-height: 30px;
    border-radius: 8px;
}}
#linkButton {{
    border: none;
    background: transparent;
    color: {_MUTED};
    font-size: 12px;
    padding: 4px 6px;
}}
#linkButton:hover {{ color: {_ACCENT}; }}
#primaryLink {{
    border: none;
    background: transparent;
    color: {_ACCENT};
    font-size: 12px;
    font-weight: 600;
    padding: 4px 6px;
}}
#primaryLink:hover {{ text-decoration: underline; }}
#logoButton {{ border: none; background: transparent; }}
#runButton {{
    color: #ffffff;
    background: {_ACCENT};
    border: none;
    min-height: 44px;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
}}
#runButton:hover {{ background: #3a7de0; }}
#runButton:disabled {{ background: #b9cdf5; }}
#simpleProgress {{
    max-height: 6px;
    border: none;
    border-radius: 3px;
    background: #e8ebf0;
}}
#simpleProgress::chunk {{ border-radius: 3px; background: {_ACCENT}; }}
#runHeadline {{ font-size: 14px; font-weight: 600; }}
#runDetail {{ color: {_MUTED}; font-size: 12px; }}
#pageSwitch {{ background: #eceef2; border-radius: 10px; }}
#pageButton {{
    border: none;
    background: transparent;
    color: {_MUTED};
    font-size: 13px;
    padding: 6px 16px;
    min-width: 140px;
    border-radius: 8px;
}}
#pageButton:checked {{ background: #ffffff; color: {_INK}; font-weight: 600; }}
#pageButton:hover:!checked {{ color: {_INK}; }}
#dropZone {{
    background: #ffffff;
    border: 2px dashed #cdd5e1;
    border-radius: 14px;
}}
#dropZone[hover="true"] {{ border-color: {_ACCENT}; background: #f2f6fe; }}
#dropPrompt {{ color: {_MUTED}; font-size: 13px; }}
#sectionLabel {{
    color: {_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    margin-top: 6px;
}}
#viewerRow {{
    background: #ffffff;
    border: 1px solid {_LINE};
    border-radius: 12px;
}}
#viewerTitle {{ font-size: 13px; font-weight: 600; }}
#viewerRow[available="false"] QLabel {{ color: #b0b6c0; }}
#recentButton {{
    border: none;
    background: transparent;
    text-align: left;
    color: {_INK};
    font-size: 12px;
    padding: 5px 4px;
}}
#recentButton:hover {{ color: {_ACCENT}; }}
"""


def _repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _set_state(widget: QWidget, state: str) -> None:
    if widget.property("state") != state:
        widget.setProperty("state", state)
        _repolish(widget)


# ── Mirroring onto the tabbed window ─────────────────────────────────────────

def mirror_line(simple: QLineEdit, classic: QLineEdit) -> list:
    """Keep two line edits showing the same text, starting from *classic*.

    Returns the connections made on the classic widget, which outlives this
    page's fields and must be disconnected when they are rebuilt.
    """
    # Not signal-blocked: the classic field has mirrors of its own (the
    # recordings folder is also on the CAT-NAP tab), and blocking its signal
    # would leave those behind. The equality checks stop the pair looping.
    def to_classic(text: str) -> None:
        if classic.text() != text:
            classic.setText(text)

    def to_simple(text: str) -> None:
        if simple.text() != text:
            simple.setText(text)

    simple.setText(classic.text())
    simple.textChanged.connect(to_classic)
    classic.textChanged.connect(to_simple)
    return [(classic.textChanged, to_simple)]


def mirror_combo(simple: QComboBox, classic: QComboBox) -> list:
    """Give *simple* the classic combo's options and keep the choice in step."""
    simple.addItems([classic.itemText(i) for i in range(classic.count())])
    if simple.findText(classic.currentText()) < 0:
        simple.addItem(classic.currentText())
    simple.setCurrentText(classic.currentText())

    def to_classic(text: str) -> None:
        if classic.currentText() != text:
            classic.setCurrentText(text)

    def to_simple(text: str) -> None:
        if simple.findText(text) < 0:
            simple.addItem(text)
        if simple.currentText() != text:
            simple.setCurrentText(text)

    simple.currentTextChanged.connect(to_classic)
    classic.currentTextChanged.connect(to_simple)
    return [(classic.currentTextChanged, to_simple)]


def mirror_spin(simple: QDoubleSpinBox, classic: QDoubleSpinBox) -> list:
    """Copy the classic spin box's format and keep the value in step."""
    simple.setRange(classic.minimum(), classic.maximum())
    simple.setDecimals(classic.decimals())
    simple.setSuffix(classic.suffix())
    simple.setSingleStep(classic.singleStep())
    simple.setValue(classic.value())
    # setValue() only emits on a real change, so the pair cannot loop.
    simple.valueChanged.connect(classic.setValue)
    classic.valueChanged.connect(simple.setValue)
    return [(classic.valueChanged, simple.setValue)]


# ── One question ─────────────────────────────────────────────────────────────

class StepCard(QFrame):
    """One question on the page: a title, a field, and the result of checking it.

    It is either **active** (the field is open and being answered), **done**
    (folded to its title, a tick and a short summary, and faded back), or
    hidden because the questions before it are not answered yet. A done card
    can be clicked to open it again.
    """

    reopen_requested = pyqtSignal()

    def __init__(self, number: int, title: str, hint: str, body: QWidget,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepCard")
        self._number = number
        self.state = "hidden"
        self.check: Check | None = None

        self.badge = QLabel(str(number))
        self.badge.setObjectName("stepBadge")
        self.badge.setFixedSize(26, 26)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title)
        self.title.setObjectName("stepTitle")
        self.summary = QLabel()
        self.summary.setObjectName("stepSummary")
        self.summary.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Preferred)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self.badge)
        header.addWidget(self.title)
        header.addWidget(self.summary, 1)

        self.hint = QLabel(hint)
        self.hint.setObjectName("stepHint")
        self.hint.setWordWrap(True)
        self.body = body
        self.status = QLabel()
        self.status.setObjectName("stepStatus")
        self.status.setWordWrap(True)

        self._details = QWidget()
        self._details.setObjectName("stepDetails")
        details = QVBoxLayout(self._details)
        details.setContentsMargins(38, 0, 0, 0)
        details.setSpacing(10)
        details.addWidget(self.hint)
        details.addWidget(body)
        details.addWidget(self.status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._details)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._fold)
        self.hide()

    # The check ────────────────────────────────────────────────────────────

    def show_check(self, check: Check | None) -> None:
        """Put the result of checking the field under it and on the badge."""
        self.check = check
        self.status.setText("" if check is None else
                            ("✓  " if check.state == "ok" else "") + check.message)
        self.status.setVisible(bool(self.status.text()))
        _set_state(self.status, check.state if check else "none")
        self.summary.setText(check.summary if check else "")
        _set_state(self.summary, check.state if check else "none")
        self._paint_badge()

    def _paint_badge(self) -> None:
        check = self.check
        if check is not None and check.complete:
            self.badge.setText("✓" if check.state == "ok" else "!")
            _set_state(self.badge, check.state)
        else:
            self.badge.setText(str(self._number))
            _set_state(self.badge, "active" if self.state == "active" else "none")

    # States ───────────────────────────────────────────────────────────────

    def set_state(self, state: str, animate: bool = False) -> None:
        """Move to *state* ("hidden", "active" or "done"), fading if *animate*."""
        if state == self.state:
            return
        previous, self.state = self.state, state
        self._hold.stop()
        self._fade.stop()
        _set_state(self, state)
        self.setCursor(Qt.CursorShape.PointingHandCursor if state == "done"
                       else Qt.CursorShape.ArrowCursor)
        self.setToolTip("Click to change" if state == "done" else "")

        if state == "hidden":
            self.hide()
        elif state == "active":
            self._details.show()
            self.show()
            if animate and previous == "hidden":
                self._animate_opacity(0.0, 1.0)
            else:
                self._effect.setOpacity(1.0)
        elif state == "done":
            self.show()
            if animate and previous == "active":
                # Leave the tick on the open field for a moment before folding.
                self._effect.setOpacity(1.0)
                self._hold.start(TICK_HOLD_MS)
            else:
                self._details.hide()
                self._effect.setOpacity(DONE_OPACITY)
        self._paint_badge()

    def _fold(self) -> None:
        self._details.hide()
        self._animate_opacity(1.0, DONE_OPACITY)

    def _animate_opacity(self, start: float, end: float) -> None:
        self._fade.stop()
        self._fade.setStartValue(start)
        self._fade.setEndValue(end)
        self._fade.start()

    @property
    def settled(self) -> bool:
        """Whether no fade or fold is still under way."""
        return (not self._hold.isActive()
                and self._fade.state() != QPropertyAnimation.State.Running)

    def mousePressEvent(self, event) -> None:  # noqa: D102
        if self.state == "done":
            self.reopen_requested.emit()
        super().mousePressEvent(event)


@dataclass
class _Step:
    key: str
    card: StepCard
    #: The current answer's check, or ``None`` while the field is empty.
    check: Callable[[], Check | None]
    focus: QWidget | None = None
    #: For steps with sensible defaults: nothing to check, only to confirm.
    confirm: bool = False
    #: Child widgets whose edits should trigger a re-check.
    watch: list = field(default_factory=list)


# ── The page ─────────────────────────────────────────────────────────────────

class SimpleView(QWidget):
    """The one-page view. Built on top of the tabbed window's panels."""

    run_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    classic_requested = pyqtSignal()
    mode_requested = pyqtSignal(str)
    view_results_requested = pyqtSignal()
    show_log_requested = pyqtSignal()

    def __init__(self, data_panel, stim_panel, catnap_panel, mode: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("simpleView")
        self.setStyleSheet(_QSS + SETTINGS_QSS)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._data = data_panel
        self._stim = stim_panel
        self._catnap = catnap_panel
        self._mode = mode
        self._steps: list[_Step] = []
        #: The step the person clicked to change, if any.
        self._reopened: int | None = None
        self._reopened_check: Check | None = None
        #: Steps with defaults that have been confirmed in this mode.
        self._confirmed: set[str] = set()
        self._output_root: Path | None = None
        #: Connections from the tabbed window's widgets to this page's fields.
        self._links: list = []
        #: (folder, its raw files) → what they said about layout and rate.

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(lambda: self.evaluate(animate=True))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._build_top_bar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        holder.setObjectName("simpleColumn")
        centre = QHBoxLayout(holder)
        centre.addStretch(1)
        self._column = QWidget()
        self._column.setObjectName("simpleColumn")
        self._column.setFixedWidth(COLUMN_WIDTH)
        self._column_layout = QVBoxLayout(self._column)
        self._column_layout.setContentsMargins(0, 8, 0, 40)
        self._column_layout.setSpacing(12)
        centre.addWidget(self._column, 0, Qt.AlignmentFlag.AlignTop)
        centre.addStretch(1)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        self._build_header()
        self._build_page_switch()

        # The two pages are shown and hidden rather than stacked, so the
        # scroll area sizes to the page showing, not to the taller of the two.
        self.analyse_page = QWidget()
        self.analyse_page.setObjectName("stepRow")
        self._analyse_layout = QVBoxLayout(self.analyse_page)
        self._analyse_layout.setContentsMargins(0, 0, 0, 0)
        self._analyse_layout.setSpacing(12)
        self._steps_box = QVBoxLayout()
        self._steps_box.setSpacing(12)
        self._analyse_layout.addLayout(self._steps_box)
        # Always on the page, unlike the questions: it is how everything the
        # questions do not ask about is reached, before and after answering.
        #: Called for the areas the card lists; set by the window, which owns
        #: the tabs they come from. Without one the card stays empty.
        self.settings_provider = None
        self.settings_card = SettingsCard()
        self.settings_card.section_requested.connect(self.open_section)
        self._analyse_layout.addWidget(self.settings_card)
        self._build_run_area()
        self._column_layout.addWidget(self.analyse_page)

        self.results_page = ResultsPage(mode)
        self._column_layout.addWidget(self.results_page)
        self._column_layout.addStretch(1)

        self.drawer = SectionDrawer(self)
        self.drawer.closed.connect(self.refresh_settings)

        self.set_mode(mode)
        self.show_page("analyse")

    # ── Fixed parts ───────────────────────────────────────────────────────────

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 0)
        # Searches this page *and* the tabs: the window supplies the provider,
        # since only it knows the tabs. Without one, it searches this page.
        self.search_provider = None
        self.search_box = SearchBox(
            lambda: (self.search_provider or self.search_entries)(),
            placeholder="Search settings and viewers")
        self.search_box.setFixedWidth(340)
        self.search_box.install_shortcut(self)
        bar.addWidget(self.search_box)
        bar.addStretch(1)
        self.classic_button = QPushButton("Classic view")
        self.classic_button.setObjectName("linkButton")
        self.classic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.classic_button.setToolTip(
            "Every setting, on tabs. The fields here are the same settings, so "
            "nothing is lost by switching.")
        self.classic_button.clicked.connect(self.classic_requested)
        bar.addWidget(self.classic_button)
        return bar

    def _build_header(self) -> None:
        self.logo_button = QToolButton()
        self.logo_button.setObjectName("logoButton")
        self.logo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.logo_button.clicked.connect(self._show_mode_menu)

        self.mode_caption = QPushButton()
        self.mode_caption.setObjectName("linkButton")
        self.mode_caption.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_caption.setToolTip("Switch to another pipeline")
        self.mode_caption.clicked.connect(self._show_mode_menu)

        self._column_layout.addWidget(self.logo_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self._column_layout.addWidget(self.mode_caption, 0, Qt.AlignmentFlag.AlignHCenter)
        self._column_layout.addSpacing(12)

    def _show_mode_menu(self) -> None:
        menu = QMenu(self)
        for key, mode in MODES.items():
            action = menu.addAction(mode.label)
            action.setCheckable(True)
            action.setChecked(key == self._mode)
            action.setToolTip(mode.blurb)
            action.triggered.connect(lambda _=False, k=key: self.mode_requested.emit(k))
        menu.exec(self.mode_caption.mapToGlobal(self.mode_caption.rect().bottomLeft()))

    def _build_run_area(self) -> None:
        self.run_area = QWidget()
        self.run_area.setObjectName("stepRow")
        layout = QVBoxLayout(self.run_area)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Where the run happens: the Run tab's own switch (see attach_run_panel),
        # so this and the tab can never disagree about what Run starts.
        run_on = QHBoxLayout()
        run_on.setSpacing(8)
        run_on_label = QLabel("Run on")
        run_on_label.setObjectName("stepHint")
        self.run_on = QComboBox()
        for key, text in RUN_ON_CHOICES:
            self.run_on.addItem(text, key)
        self.run_on.setToolTip(
            "This computer: one run of these settings.\n"
            "A queue: several saved settings files, one after another.\n"
            "Several computers: these settings, with the recordings shared out "
            "through a folder they can all reach.")
        self.run_on.currentIndexChanged.connect(self._on_run_on_changed)
        self.run_on_setup = QPushButton("Set up…")
        self.run_on_setup.setObjectName("primaryLink")
        self.run_on_setup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_on_setup.clicked.connect(self.open_run_setup)
        self.run_on_setup.hide()
        run_on.addWidget(run_on_label)
        run_on.addWidget(self.run_on)
        run_on.addWidget(self.run_on_setup)
        run_on.addStretch(1)
        layout.addLayout(run_on)

        self.run_button = QPushButton()
        self.run_button.setObjectName("runButton")
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_button.clicked.connect(self.run_requested)
        layout.addWidget(self.run_button)

        self.run_headline = QLabel()
        self.run_headline.setObjectName("runHeadline")
        self.run_headline.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("simpleProgress")
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.run_detail = QLabel()
        self.run_detail.setObjectName("runDetail")
        self.run_detail.setWordWrap(True)
        layout.addWidget(self.run_headline)
        layout.addWidget(self.progress)
        layout.addWidget(self.run_detail)
        # Keeps elapsed time and time left moving between progress reports,
        # which can be minutes apart (see gui/run_clock.py).
        self.clock = RunClock(self)
        self.clock.ticked.connect(self._show_timing)
        self._run_detail_prefix = ""

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_requested)
        self.results_button = QPushButton("View results")
        self.results_button.setObjectName("primary")
        self.results_button.clicked.connect(self.view_results_requested)
        self.folder_button = QPushButton("Open folder")
        self.folder_button.clicked.connect(self._open_output_folder)
        self.log_button = QPushButton("Show log")
        self.log_button.setObjectName("linkButton")
        self.log_button.clicked.connect(self.show_log_requested)
        for button in (self.stop_button, self.results_button, self.folder_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.log_button)
        layout.addLayout(actions)

        self._analyse_layout.addWidget(self.run_area)
        self._show_run_state("idle")

    def _build_page_switch(self) -> None:
        switch = QFrame()
        switch.setObjectName("pageSwitch")
        row = QHBoxLayout(switch)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(0)
        self._page_buttons: dict[str, QPushButton] = {}
        for key, label in (("analyse", "Analyse recordings"), ("results", "View results")):
            button = QPushButton(label)
            button.setObjectName("pageButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            row.addWidget(button)
            self._page_buttons[key] = button
        self._column_layout.addWidget(switch, 0, Qt.AlignmentFlag.AlignHCenter)
        self._column_layout.addSpacing(6)

    def page(self) -> str:
        return "results" if self.results_page.isVisibleTo(self) else "analyse"

    def show_page(self, key: str) -> None:
        """Show **Analyse recordings** (``"analyse"``) or **View results** (``"results"``)."""
        self.analyse_page.setVisible(key == "analyse")
        self.results_page.setVisible(key == "results")
        for name, button in self._page_buttons.items():
            button.setChecked(name == key)
        if key == "results":
            self.results_page.refresh_recent()

    def show_results(self, source: str | Path) -> None:
        """Go to **View results** and open *source* in the results viewer."""
        self.show_page("results")
        self.results_page.set_source(source)

    # ── Steps per pipeline ────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        """Rebuild the questions for *mode*'s pipeline, keeping every answer."""
        # Confirmations carry over: a step with the same key asks about the
        # same settings in every pipeline that has it.
        self.close_section()
        self._mode = mode
        self._reopened = None
        for signal, slot in self._links:
            try:
                signal.disconnect(slot)
            except TypeError:  # already gone with its widget
                pass
        self._links = []
        for step in self._steps:
            step.card.setParent(None)
            step.card.deleteLater()
        self._steps = self._build_steps(mode)
        for index, step in enumerate(self._steps):
            self._steps_box.addWidget(step.card)
            step.card.reopen_requested.connect(lambda i=index: self._reopen(i))
            for widget in step.watch:
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(self.schedule_check)
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self.schedule_check)
                elif isinstance(widget, QDoubleSpinBox):
                    widget.valueChanged.connect(self.schedule_check)

        pixmap = logo_pixmap(LOGO_HEIGHT, self.devicePixelRatioF(), mode)
        if pixmap is not None:
            self.logo_button.setIcon(QIcon(pixmap))
            logical = pixmap.deviceIndependentSize().toSize()
            self.logo_button.setIconSize(logical)
        else:
            self.logo_button.setText(MODES[mode].label.split("·")[0].strip())
        self.logo_button.setToolTip(f"{MODES[mode].label}\n{MODES[mode].blurb}")
        self.mode_caption.setText(f"{MODES[mode].label}  ▾")
        self._refresh_run_button()
        self.results_page.set_mode(mode)
        self.refresh_settings()
        if self._run_state in ("done", "failed", "cancelled"):
            self._show_run_state("idle")
        self.evaluate(animate=False)

    def _build_steps(self, mode: str) -> list[_Step]:
        steps: list[_Step] = []

        def add(key, title, hint, body, check, focus=None, confirm=False, watch=()):
            card = StepCard(len(steps) + 1, title, hint, body)
            steps.append(_Step(key, card, check, focus, confirm, list(watch)))

        # Recordings
        folder = self._path_field(self._data.raw_data.line_edit, folder=True,
                                  placeholder="Choose a folder, or paste a Dropbox link")
        add("recordings",
            "Recordings" if mode != "catnap" else "Recordings (suite2p)",
            ("The folder holding one sub-folder per recording, each with "
             "suite2p/plane0 inside." if mode == "catnap" else
             "The folder with your recordings (.mat, .h5 or .raw files)."),
            folder, lambda: check_recordings_folder(self._folder_text(), mode),
            focus=folder.edit, watch=[folder.edit])

        # Spreadsheet
        sheet = self._path_field(self._data.spreadsheet.line_edit, folder=False,
                                 placeholder="Choose a .csv or .xlsx file",
                                 file_filter="Spreadsheets (*.csv *.xlsx *.xls)")
        make = QPushButton("Create or edit…")
        make.setObjectName("linkButton")
        make.setCursor(Qt.CursorShape.PointingHandCursor)
        make.setToolTip("Open the spreadsheet in a table editor, or start one from "
                        "the recordings folder.")
        make.clicked.connect(lambda: self._data.edit_spreadsheet(
            recording_names(self._folder_text(), mode) or None))
        self._sheet_button = make
        sheet_body = QWidget()
        sheet_body.setObjectName("stepRow")
        sheet_rows = QVBoxLayout(sheet_body)
        sheet_rows.setContentsMargins(0, 0, 0, 0)
        sheet_rows.setSpacing(2)
        sheet_rows.addWidget(sheet)
        sheet_rows.addWidget(make, 0, Qt.AlignmentFlag.AlignLeft)
        sheet_body.edit = sheet.edit  # a path step's body exposes its field
        add("spreadsheet", "Spreadsheet",
            "Lists each recording with its age (DIV) and group.",
            sheet_body,
            lambda: check_spreadsheet(self._data.spreadsheet.value, self._folder_text(),
                                      mode, self._data.spreadsheet_range.text()),
            focus=sheet.edit, watch=[sheet.edit])

        # What the data is, or how to read it
        if mode == "catnap":
            activity = QComboBox()
            self._links += mirror_combo(activity, self._catnap._activity_combo)
            body = self._form([("Activity measure", activity)])
            add("activity", "Activity measure",
                "Which suite2p signal the networks are built from.",
                body, lambda: self._confirmed_check("activity", activity.currentText()),
                focus=activity, confirm=True, watch=[activity])
        else:
            # The rate is shown, not asked for: every step reads each
            # recording's own, so there is nothing to set.
            layout = QComboBox()
            self._links += mirror_combo(layout, self._data.channel_layout)
            rate = QLabel()
            rate.setObjectName("stepHint")
            rate.setWordWrap(True)
            body = self._form([("Electrode layout", layout), ("Sampling rate", rate)])
            add("recording", "Recording settings",
                "Both are read from your recordings. Change the layout only if "
                "it's wrong.",
                body, lambda: self._recording_check(layout, rate),
                focus=layout, confirm=True, watch=[layout])

        if mode == "meastim":
            method = QComboBox()
            self._links += mirror_combo(method, self._stim.method)
            value = QDoubleSpinBox()
            self._links += mirror_spin(value, self._stim.detection_val)
            body = self._form([("Detection method", method), ("Detection value", value)])
            add("stimulation", "Stimulation",
                "How stimulation artefacts are found in the recordings.",
                body,
                lambda: self._confirmed_check("stimulation", method.currentText()),
                focus=method, confirm=True, watch=[method, value])

        # Output
        output = self._path_field(self._data.output_data_folder.line_edit, folder=True,
                                  placeholder="Choose where to save the results")
        add("output", "Results folder", "Where to save the results.",
            output, lambda: check_output_folder(self._data.output_data_folder.value),
            focus=output.edit, watch=[output.edit])
        return steps

    # ── Field builders ────────────────────────────────────────────────────────

    def _path_field(self, classic: QLineEdit, *, folder: bool, placeholder: str,
                    file_filter: str = "") -> QWidget:
        row = QWidget()
        row.setObjectName("stepRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        self._links += mirror_line(edit, classic)
        browse = QPushButton("Browse…")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)

        def pick() -> None:
            start = edit.text().strip()
            if folder:
                path = QFileDialog.getExistingDirectory(self, "Select folder", start)
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Select file", start,
                                                      file_filter)
            if path:
                edit.setText(path)
                self.evaluate(animate=True, commit=True)

        browse.clicked.connect(pick)
        edit.returnPressed.connect(lambda: self.evaluate(animate=True, commit=True))
        layout.addWidget(edit, 1)
        layout.addWidget(browse)
        row.edit = edit
        return row

    def _form(self, rows) -> QWidget:
        body = QWidget()
        body.setObjectName("stepRow")
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        for label, widget in rows:
            form.addRow(label, widget)
        done = QPushButton("Continue")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.setObjectName("primary")
        done.clicked.connect(self._confirm_current)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(done)
        form.addRow(actions)
        return body

    def _folder_text(self) -> str:
        return self._data.raw_data.value

    def _layout_guess(self):
        """What the recordings say about layout and rate (read by the Data tab)."""
        return self._data.layout_guess()

    def _recording_check(self, layout: QComboBox, rate: QLabel):
        guess = self._layout_guess()
        rates = describe_rates(guess.rates) if guess is not None else ""
        rate.setText(
            f"{rates}, read from the recordings" + (
                " (each is analysed at its own)" if len(set(guess.rates)) > 1 else "")
            if rates else "Read from each recording when the run starts")
        self._data.refresh_detection()
        return (check_recording_settings(guess, layout.currentText())
                or self._confirmed_check("recording", layout.currentText()))

    def _confirmed_check(self, key: str, summary: str) -> Check | None:
        """A settings step with defaults counts once Continue has been pressed."""
        return Check("ok", "", summary) if key in self._confirmed else None

    def _confirm_current(self) -> None:
        for step in self._steps:
            if step.card.state == "active" and step.confirm:
                self._confirmed.add(step.key)
        self.evaluate(animate=True, commit=True)

    def _reopen(self, index: int) -> None:
        if self._run_state == "running":
            return
        self._reopened = index
        self._reopened_check = self._steps[index].check()
        self.evaluate(animate=True)
        focus = self._steps[index].focus
        if focus is not None:
            focus.setFocus()

    # ── Search ────────────────────────────────────────────────────────────────

    def search_entries(self) -> list[SearchEntry]:
        """The questions, viewers and pages on this view, for the search."""
        here = "Simple view"
        entries: list[SearchEntry] = []
        for index, step in enumerate(self._steps):
            card = step.card
            if card.state == "hidden":
                continue  # not asked yet: earlier questions come first
            words = " ".join(label.text() for label in card.body.findChildren(QLabel))
            entries.append(SearchEntry(
                card.title.text(), f"{here} › Analyse recordings", SETTING, card,
                lambda i=index: self.go_to_step(i),
                f"{card.hint.text()} {words} {card.body.toolTip()}"))
        for viewer in viewers_for(self._mode):
            entries.append(SearchEntry(
                viewer.title, f"{here} › View results", VIEW, None,
                lambda k=viewer.key: self.go_to_viewer(k),
                f"{viewer.description} viewer results"))
        for key, title, words in (
                ("analyse", "Analyse recordings", "run steps start"),
                ("results", "View results", "results viewer bundle open report")):
            entries.append(SearchEntry(title, here, VIEW, None,
                                       lambda k=key: self.show_page(k), words))
        for key, mode in MODES.items():
            if key != self._mode:
                entries.append(SearchEntry(
                    f"Switch to {mode.label}", f"{here} › Pipeline", VIEW, None,
                    lambda k=key: self.mode_requested.emit(k),
                    f"mode pipeline {mode.blurb}"))
        for entry in entries:
            entry.rank = 0
        return entries

    def go_to_step(self, index: int) -> None:
        """Open question *index* (reopening it if answered) and mark it."""
        self.show_page("analyse")
        step = self._steps[index]
        if step.card.state == "done":
            self._reopen(index)
        elif step.focus is not None:
            step.focus.setFocus()
        self._mark(step.card)

    def go_to_viewer(self, key: str) -> None:
        """Show **View results** with *key*'s row marked."""
        self.show_page("results")
        row = self.results_page.viewer_row(key)
        if row is not None:
            self._mark(row)

    def _mark(self, widget: QWidget) -> None:
        def show() -> None:
            reveal_widget(widget)
            if widget.isVisible():
                Flash(widget)
        # Once the page has been laid out (and a reopened card unfolded).
        QTimer.singleShot(FADE_MS if isinstance(widget, StepCard) else 0, show)

    # ── Checking and moving on ────────────────────────────────────────────────

    def schedule_check(self) -> None:
        """Re-check after the person stops typing."""
        self._debounce.start()

    def evaluate(self, animate: bool = False, commit: bool = False) -> None:
        """Check every answer and show the questions that should be showing.

        Answered questions before the first unanswered one are folded, the
        first unanswered one is open, and everything after it stays hidden.

        A question the person reopened stays open, with the ones after it
        hidden, until its answer checks out and is either different from what
        it was or *commit*-ted (Browse, Enter or Continue).
        """
        if not self._steps:
            return
        checks = [step.check() for step in self._steps]
        first_open = next((i for i, c in enumerate(checks)
                           if c is None or not c.complete), len(checks))

        reopened = self._reopened
        if reopened is not None:
            check = checks[reopened]
            if check is not None and check.complete and (
                    commit or check != self._reopened_check):
                reopened = self._reopened = None

        newly_active: QWidget | None = None
        for i, (step, check) in enumerate(zip(self._steps, checks)):
            card = step.card
            card.show_check(check)
            if reopened is not None:
                state = ("active" if i == reopened else
                         "done" if i < first_open else "hidden")
            else:
                state = ("done" if i < first_open else
                         "active" if i == first_open else "hidden")
            if state == "active" and card.state != "active":
                newly_active = step.focus
            card.set_state(state, animate=animate)

        self._refresh_sheet_button()
        ready = first_open == len(self._steps) and reopened is None
        self._ready = ready
        self._show_settings_badge()
        self.run_area.setVisible(ready or self._run_state != "idle")
        self._refresh_run_button()
        # Only while the page is on screen: from behind the tabs, taking focus
        # would leave the classic window opening with a field focused.
        if newly_active is not None and self.analyse_page.isVisible():
            # After the previous card has had its moment, so focus does not
            # jump before the tick is seen.
            QTimer.singleShot(TICK_HOLD_MS if animate else 0, newly_active.setFocus)

    def _refresh_sheet_button(self) -> None:
        """Offer to build a spreadsheet when there is a folder of recordings and no sheet."""
        button = getattr(self, "_sheet_button", None)
        if button is None:
            return
        n = 0 if self._data.spreadsheet.value.strip() else len(
            recording_names(self._folder_text(), self._mode))
        if n:
            button.setText(f"Build one from the {n} recording{'s' if n != 1 else ''} "
                           "in this folder…")
            button.setObjectName("primaryLink")
        else:
            button.setText("Create or edit…")
            button.setObjectName("linkButton")
        _repolish(button)

    def showEvent(self, event) -> None:  # noqa: D102
        super().showEvent(event)
        self.evaluate(animate=False)
        self.refresh_settings()

    # ── Other settings ────────────────────────────────────────────────────────

    def refresh_settings(self) -> None:
        """Re-read the areas, their summaries and what has changed."""
        if self.settings_provider is None or self.drawer.is_open():
            return
        self.settings_card.set_areas(self.settings_provider())
        self._show_settings_badge()

    _ready = False

    def _show_settings_badge(self) -> None:
        """A tick once every question is answered: the run has all it needs.

        Before then, the card's number — the questions come first. Changed
        settings still get a tick: changed is a choice, not a problem.
        """
        badge = self.settings_card.badge
        badge.setText("✓" if self._ready else str(len(self._steps) + 1))
        _set_state(badge, "ok" if self._ready else "")

    def open_log(self, log_box: QWidget, log: QWidget | None = None) -> None:
        """Show the run's status log in the panel, live, without leaving the page."""
        self.close_section()
        self.drawer.open_section("Run", Section("Status log", log_box), fill=True,
                                 note="Updates as the run goes.")
        if log is not None and hasattr(log, "verticalScrollBar"):
            bar = log.verticalScrollBar()
            bar.setValue(bar.maximum())

    def open_section(self, area_key: str, index: int) -> None:
        """Show section *index* of *area_key* in the panel."""
        self.close_section()
        area = next((a for a in self.settings_card.areas() if a.key == area_key), None)
        if area is None or not 0 <= index < len(area.sections):
            return
        self.show_page("analyse")
        self.drawer.open_section(area.title, area.sections[index])

    def close_section(self) -> None:
        """Put the open section back on its tab, if one is open."""
        if self.drawer.is_open():
            self.drawer.close_section()

    def open_setting(self, widget: QWidget) -> bool:
        """Open the section holding *widget* in the panel; False if none does."""
        self.close_section()
        self.refresh_settings()
        for area in self.settings_card.areas():
            for index, section in enumerate(area.sections):
                if section.box is widget or section.box.isAncestorOf(widget):
                    self.settings_card.expand(area.key)
                    self.open_section(area.key, index)
                    return True
        return False

    # ── The run ───────────────────────────────────────────────────────────────

    _run_state = "idle"

    def _show_run_state(self, state: str, headline: str = "", detail: str = "") -> None:
        self._run_state = state
        running = state == "running"
        self.run_button.setVisible(state == "idle")
        self.run_headline.setVisible(state != "idle")
        self.run_headline.setText(headline)
        self.progress.setVisible(running)
        self.run_detail.setVisible(bool(detail))
        self.run_detail.setText(detail)
        self.stop_button.setVisible(running)
        self.results_button.setVisible(state == "done")
        self.folder_button.setVisible(state == "done")
        self.log_button.setVisible(state != "idle")
        for step in self._steps:
            step.card.setEnabled(not running)
        # Settings are read as the run starts; changing one now would change
        # nothing, so do not invite it.
        self.settings_card.setEnabled(not running)
        self.run_on.setEnabled(not running)
        self.run_on_setup.setEnabled(not running)

    # ── Where the run happens ─────────────────────────────────────────────────

    #: The Run tab's panel, once the window has attached it.
    run_panel = None

    def attach_run_panel(self, run_panel) -> None:
        """Follow, and drive, the Run tab's switch and its Run button."""
        self.run_panel = run_panel
        run_panel.run_label_changed.connect(self._sync_run_on)
        self._sync_run_on()

    def _run_on_key(self) -> str:
        return self.run_on.currentData() or THIS_RUN

    def _sync_run_on(self) -> None:
        if self.run_panel is None:
            return
        index = self.run_on.findData(self.run_panel.mode())
        if index >= 0 and index != self.run_on.currentIndex():
            blocker = QSignalBlocker(self.run_on)
            self.run_on.setCurrentIndex(index)
            del blocker
        self.run_on_setup.setVisible(self._run_on_key() != THIS_RUN)
        self._refresh_run_button()

    def _on_run_on_changed(self, _index: int) -> None:
        if self.run_panel is not None:
            self.run_panel.set_mode(self._run_on_key())  # relabels, then syncs back
        else:
            self._sync_run_on()
        if self._run_on_key() != THIS_RUN and self.isVisible():
            # Nothing to run yet until a queue or a shared run is set up.
            self.open_run_setup()

    def open_run_setup(self) -> None:
        """The queue's or the shared run's page, in the panel."""
        if self.run_panel is None:
            return
        key = self._run_on_key()
        if key == QUEUE:
            page, title = self.run_panel.queue, "Queue of saved runs"
            note = "Run starts them in order, one after another."
        elif key == SHARED:
            page, title = self.run_panel.shared, "Shared with other computers"
            note = "Run starts once the other computers have joined."
        else:
            return
        self.close_section()
        self.drawer.open_section("Run on", Section(title, page), fill=True, note=note)

    def _refresh_run_button(self) -> None:
        """Label and enable Run for what it would start.

        A single run is named after the pipeline. A queue or a shared run takes
        the Run tab's label and its say on whether there is anything to start
        (an empty queue, a shared run still waiting for its computers).
        """
        key = self._run_on_key()
        extra_ok = True
        if key == THIS_RUN or self.run_panel is None:
            self.run_button.setText(f"Run {MODES[self._mode].label.split('·')[0].strip()}")
            self.run_button.setToolTip("")
        else:
            classic = self.run_panel.run_btn
            self.run_button.setText(classic.text().replace("▶", "").strip())
            self.run_button.setToolTip(classic.toolTip())
            extra_ok = classic.isEnabled()
        self.run_button.setEnabled(self._ready and self._run_state != "running" and extra_ok)

    # ── The run ───────────────────────────────────────────────────────────────

    def track_run(self, worker) -> None:
        """Follow a run the window started, showing its progress on this page."""
        self._output_root = None
        self.progress.setValue(0)
        self._run_detail_prefix = ""
        self._show_run_state("running", "Starting…")
        self.clock.start()
        self.run_area.show()
        worker.progress.connect(self._on_progress)
        # A single or shared run finishes with its output folder; a queue, or a
        # helper's share, with (None, a summary).
        worker.finished_ok.connect(
            lambda result: self._on_finished(*result) if isinstance(result, tuple)
            else self._on_finished(result))
        worker.cancelled.connect(lambda: self._on_ended("cancelled", "Run stopped."))
        worker.failed.connect(lambda msg: self._on_ended(
            "failed", "The run failed.", msg.strip().splitlines()[-1] if msg.strip() else ""))

    def _on_progress(self, snapshot) -> None:
        self.progress.setValue(int(round(snapshot.fraction * 1000)))
        headline = f"{snapshot.percent}%  ·  {snapshot.phase}"
        self.run_headline.setText(headline)
        self._run_detail_prefix = snapshot.detail or ""
        self.clock.report(snapshot.elapsed_s, snapshot.eta_s)

    def _show_timing(self) -> None:
        if self._run_state != "running":
            return
        timing = self.clock.text()
        prefix = self._run_detail_prefix
        self.run_detail.setText(f"{prefix}  ·  {timing}" if prefix else timing)
        self.run_detail.show()

    def _on_finished(self, output_root, summary: str = "") -> None:
        """Done. *output_root* is the run's folder, or None for a queue's end,
        or for a helper's share of a shared run, which have no one folder."""
        self.clock.stop()
        self._output_root = Path(output_root) if output_root else None
        self._show_run_state("done", "✓  Finished",
                             str(self._output_root) if self._output_root else summary)
        self.results_button.setVisible(self._output_root is not None)
        self.folder_button.setVisible(self._output_root is not None)

    def _on_ended(self, state: str, headline: str, detail: str = "") -> None:
        self.clock.stop()
        self._show_run_state(state, headline, detail)
        # Back to a Run button after a moment, so trying again is one click.
        self.run_button.setVisible(True)
        self.run_button.setEnabled(True)

    def _open_output_folder(self) -> None:
        if self._output_root is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_root)))

    def sizeHint(self) -> QSize:  # noqa: D102
        return QSize(COLUMN_WIDTH + 80, 700)
