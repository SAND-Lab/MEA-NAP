"""Every other setting, from the simple view.

The simple view asks only for what a run cannot do without. Everything else
lives on the classic tabs, and this module is how the simple view reaches it
without leaving the page:

* :class:`SettingsCard` — a card above **Run**, always on the page, with one
  row per settings tab: a summary of its key values and how many of its
  settings differ from the pipeline's defaults. A row unfolds into the tab's
  sections.
* :class:`SectionDrawer` — choosing a section slides in a panel holding it.

The panel does not hold copies of the settings. It *borrows* the section's
group box from its tab (:class:`Loan`) and puts it back when it closes. The
tabs are hidden while the simple view is showing, so nothing is missing from
them while it is away, and there is one widget per setting — no mirroring to
keep in step, and nothing for :meth:`MainWindow._collect_params` to miss. It
also means a setting added to a tab is in the panel without anyone adding it.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import (
    QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from meanap.gui.settings_search import _plain, _reachable

__all__ = [
    "STEP_FIELDS", "Change", "Section", "Area", "changed_fields",
    "settings_sections", "summarise", "Loan", "SettingsCard", "SectionDrawer",
    "SETTINGS_QSS",
]

#: Settings the simple view's own questions ask for, or fills in from the
#: recordings. Not counted as "changed": answering a question is not changing
#: a default, and every run changes these.
STEP_FIELDS = frozenset({
    "raw_data", "spreadsheet_file_name", "output_data_folder",
    "output_data_folder_name", "channel_layout", "fs", "d_samp_f",
    "potential_difference_unit", "stim_detection_method", "stim_detection_val",
    "twop_activity", "twop_activities",
})

#: How wide the panel is, at most, and the share of the page it may take.
DRAWER_WIDTH = 620
DRAWER_SHARE = 0.62
SLIDE_MS = 180

_MUTED = "#6b7280"
_LINE = "#e5e7eb"
_ACCENT = "#4f8ef7"
_CHANGED = "#b45309"

SETTINGS_QSS = f"""
#areaRow {{
    background: transparent;
    border: none;
    border-radius: 8px;
}}
#areaRow:hover {{ background: #f3f5f8; }}
#areaTitle {{ font-size: 13px; font-weight: 600; }}
#areaSummary {{ color: {_MUTED}; font-size: 12px; }}
#areaArrow {{ color: {_MUTED}; font-size: 11px; }}
#areaChanged {{
    color: #ffffff;
    background: {_CHANGED};
    border-radius: 9px;
    font-size: 11px;
    font-weight: 600;
    padding: 0 6px;
}}
#sectionLink {{
    border: none;
    background: transparent;
    text-align: left;
    color: {_ACCENT};
    font-size: 12px;
    padding: 4px 8px;
}}
#sectionLink:hover {{ text-decoration: underline; }}
#settingsDrawer {{
    background: #ffffff;
    border-left: 1px solid {_LINE};
}}
#drawerArea {{ color: {_MUTED}; font-size: 12px; }}
#drawerTitle {{ font-size: 16px; font-weight: 600; }}
#drawerHolder {{ background: #ffffff; }}
"""


# ── What changed, and the summary line ─────────────────────────────────────────

@dataclass
class Change:
    """One setting whose value is not the pipeline's default."""

    name: str
    default: Any
    value: Any

    def describe(self) -> str:
        return f"{self.name.replace('_', ' ')}: {_fmt(self.default)} → {_fmt(self.value)}"


def _fmt(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_fmt(v) for v in value) + "]" if value else "none"
    if isinstance(value, float):
        return f"{value:g}"
    if value in ("", None):
        return "none"
    return str(value)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, tuple):
        a = list(a)
    if isinstance(b, tuple):
        b = list(b)
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def changed_fields(panel, defaults) -> list[Change]:
    """The settings *panel* holds that differ from *defaults*.

    Every panel's ``save`` writes only its own settings, so saving it over a
    copy of the defaults and comparing tells exactly which of its settings
    were changed — without a table saying which widget is which setting.
    """
    saved = copy.deepcopy(defaults)
    panel.save(saved)
    out = []
    for f in dataclasses.fields(defaults):
        if f.name in STEP_FIELDS:
            continue
        before, after = getattr(defaults, f.name), getattr(saved, f.name)
        if not _same(before, after):
            out.append(Change(f.name, before, after))
    return out


def _nums(values, unit: str = "") -> str:
    return ", ".join(f"{v:g}" for v in values) + unit


def summarise(key: str, p) -> str:
    """The two or three values of an area most worth seeing without opening it."""
    from meanap.gui.modes import (
        TAB_CATNAP, TAB_CONNECTIVITY, TAB_DATA, TAB_RUN, TAB_SPIKE, TAB_STIM,
    )

    if key == TAB_DATA:
        parts = [(f"{'First' if p.trunc_keep == 'first' else 'Last'} "
                  f"{p.trunc_length:g} s of each recording")
                 if p.trunc_rec else "Whole recordings"]
        if p.custom_grp_order:
            parts.append("groups " + ", ".join(p.custom_grp_order))
        return " · ".join(parts)
    if key == TAB_SPIKE:
        if p.spike_source == "sort":
            return f"Spike sorting with {p.sorter_name}"
        if p.spike_source == "import":
            return "Imported sorted units"
        parts = [", ".join(p.wname_list) or "no wavelets"]
        if p.thresholds:
            parts.append(f"thresholds {_nums(p.thresholds)}")
        parts.append(f"active from {p.min_activity_level:g} Hz")
        return " · ".join(parts)
    if key == TAB_CONNECTIVITY:
        parts = [f"lags {_nums(p.func_con_lag_val, ' ms')}", f"{p.adj_m_type} networks"]
        if p.compute_spatiotemporal:
            parts.append("autocorrelation")
        return " · ".join(parts)
    if key == TAB_STIM:
        lo, hi = (list(p.stim_analysis_window) + [0, 0])[:2]
        return (f"responses {lo * 1000:g} to {hi * 1000:g} ms · "
                f"{p.stim_n_shuffles} shuffles")
    if key == TAB_CATNAP:
        return (f"denoising threshold {p.twop_denoising_threshold:g} · "
                f"cell tracking {'on' if p.track_cells else 'off'}")
    if key == TAB_RUN:
        parts = [f"steps {p.start_analysis_step}–{p.stop_analysis_step}",
                 "figures " + (", ".join(e.lstrip(".") for e in p.fig_ext) or "none")]
        if p.express_mode:
            parts.append("express mode")
        return " · ".join(parts)
    return ""


# ── Sections ───────────────────────────────────────────────────────────────────

@dataclass
class Section:
    title: str
    box: QGroupBox


@dataclass
class Area:
    """One settings tab as the card shows it."""

    key: str
    title: str
    sections: list[Section]
    summary: str = ""
    changed: list[Change] = field(default_factory=list)


def _has_inputs(box: QWidget) -> bool:
    for kind in (QLineEdit, QAbstractSpinBox, QComboBox, QAbstractItemView):
        for w in box.findChildren(kind):
            if not (isinstance(w, QLineEdit) and w.isReadOnly()):
                return True
    return any(b.isCheckable() for b in box.findChildren(QAbstractButton))


def settings_sections(page: QWidget, exclude: frozenset[str] = frozenset()) -> list[Section]:
    """The group boxes on *page* that hold settings, outermost only, in order.

    A box the mode hides, or one with nothing to set in it (a log, a progress
    bar), is not a section. Nor is one :class:`Loan` could not put back.
    """
    out = []
    for box in _in_layout_order(page):
        if not isinstance(box, QGroupBox):
            continue
        title = _plain(box.title())
        if not title or title in exclude or not _reachable(box, page):
            continue
        parent = box.parentWidget()
        nested = False
        while parent is not None and parent is not page:
            if isinstance(parent, QGroupBox):
                nested = True
                break
            parent = parent.parentWidget()
        if nested or not _has_inputs(box) or not Loan.possible(box):
            continue
        out.append(Section(title, box))
    return out


def _in_layout_order(widget: QWidget):
    """*widget* and everything laid out inside it, in the order it is laid out.

    The order the tab shows things in, top to bottom and column by column —
    which neither creation order nor on-screen position gives reliably: a tab
    never shown has no positions yet.
    """
    yield widget
    if isinstance(widget, QSplitter):
        for i in range(widget.count()):
            yield from _in_layout_order(widget.widget(i))
        return
    if isinstance(widget, QScrollArea):
        if widget.widget() is not None:
            yield from _in_layout_order(widget.widget())
        return
    if widget.layout() is not None:
        yield from _layout_items(widget.layout())


def _layout_items(layout):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            yield from _in_layout_order(item.widget())
        elif item.layout() is not None:
            yield from _layout_items(item.layout())


# ── Borrowing a box from its tab ───────────────────────────────────────────────

class Loan:
    """Take a widget out of its place, and put it back exactly there.

    A placeholder holds the widget's place in the layout (or splitter) while it
    is away, so it goes back into the same row of the same layout, with the
    same stretch, whatever kind of layout that is.
    """

    def __init__(self, widget: QWidget) -> None:
        self.widget = widget
        self._placeholder = QWidget()
        self._placeholder.setObjectName("loanPlaceholder")
        parent = widget.parentWidget()
        self._splitter: QSplitter | None = None
        self._layout = None
        if isinstance(parent, QSplitter):
            self._splitter = parent
            self._sizes = parent.sizes()
            parent.replaceWidget(parent.indexOf(widget), self._placeholder)
        else:
            self._layout = parent.layout()
            self._layout.replaceWidget(widget, self._placeholder)
        self._placeholder.hide()
        # The panel's heading names the section; the box's own title would
        # say it a second time, directly below.
        self._title = widget.title() if isinstance(widget, QGroupBox) else None
        if self._title is not None:
            widget.setTitle("")

    @staticmethod
    def possible(widget: QWidget) -> bool:
        parent = widget.parentWidget()
        if isinstance(parent, QSplitter):
            return parent.indexOf(widget) >= 0
        layout = parent.layout() if parent is not None else None
        return layout is not None and _in_layout(layout, widget)

    def give_back(self) -> None:
        if sip.isdeleted(self.widget) or sip.isdeleted(self._placeholder):
            return
        if self._splitter is not None:
            self._splitter.replaceWidget(self._splitter.indexOf(self._placeholder), self.widget)
            self._splitter.setSizes(self._sizes)
        else:
            self._layout.replaceWidget(self._placeholder, self.widget)
        if self._title is not None:
            self.widget.setTitle(self._title)
        self.widget.show()
        self._placeholder.deleteLater()


def _in_layout(layout, widget: QWidget) -> bool:
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return True
        if item.layout() is not None and _in_layout(item.layout(), widget):
            return True
    return False


# ── The card ───────────────────────────────────────────────────────────────────

class _AreaRow(QPushButton):
    """A clickable row: arrow, area name, its summary, and a changed count."""

    def __init__(self, area: Area, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("areaRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)
        self.arrow = QLabel("▸")
        self.arrow.setObjectName("areaArrow")
        self.arrow.setFixedWidth(10)
        self.title = QLabel(area.title)
        self.title.setObjectName("areaTitle")
        self.summary = QLabel(area.summary)
        self.summary.setObjectName("areaSummary")
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.changed = QLabel(str(len(area.changed)))
        self.changed.setObjectName("areaChanged")
        self.changed.setFixedHeight(18)
        self.changed.setVisible(bool(area.changed))
        for label in (self.arrow, self.title, self.summary, self.changed):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.arrow)
        row.addWidget(self.title)
        row.addWidget(self.summary, 1)
        row.addWidget(self.changed)
        tip = [area.summary] if area.summary else []
        if area.changed:
            tip.append(f"{len(area.changed)} changed from the defaults:")
            tip += [f"  {c.describe()}" for c in area.changed]
        else:
            tip.append("All at their defaults.")
        self.setToolTip("\n".join(tip))
        self.toggled.connect(lambda on: self.arrow.setText("▾" if on else "▸"))

    def sizeHint(self):  # noqa: D102, N802
        return self.layout().sizeHint()


class SettingsCard(QFrame):
    """One card listing every settings tab, unfolding into its sections."""

    #: (area key, section index) — a section to open in the panel.
    section_requested = pyqtSignal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepCard")
        self.setProperty("state", "active")
        self._areas: list[Area] = []
        self._expanded: set[str] = set()
        self.rows: dict[str, _AreaRow] = {}
        self.links: dict[str, list[QPushButton]] = {}

        self.badge = QLabel("⚙")
        self.badge.setObjectName("stepBadge")
        self.badge.setFixedSize(26, 26)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Other settings")
        self.title.setObjectName("stepTitle")
        self.summary = QLabel()
        self.summary.setObjectName("stepSummary")
        self.summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self.badge)
        header.addWidget(self.title)
        header.addWidget(self.summary, 1)

        self.hint = QLabel(
            "Everything else a run uses, at the pipeline's defaults unless you "
            "change it. Open an area, then a section, to see its settings.")
        self.hint.setObjectName("stepHint")
        self.hint.setWordWrap(True)

        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(0)
        details = QVBoxLayout()
        details.setContentsMargins(38, 0, 0, 0)
        details.setSpacing(8)
        details.addWidget(self.hint)
        details.addLayout(self._rows_box)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addLayout(details)

    def areas(self) -> list[Area]:
        return list(self._areas)

    def total_changed(self) -> int:
        return sum(len(a.changed) for a in self._areas)

    def set_areas(self, areas: list[Area]) -> None:
        """Show *areas*, keeping whichever were unfolded."""
        self._areas = areas
        while self._rows_box.count():
            item = self._rows_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.rows.clear()
        self.links.clear()
        for area in areas:
            row = _AreaRow(area)
            sections = QWidget()
            sections.setObjectName("stepDetails")
            column = QVBoxLayout(sections)
            column.setContentsMargins(28, 0, 0, 6)
            column.setSpacing(0)
            links = []
            for index, section in enumerate(area.sections):
                link = QPushButton(f"{section.title}  ›")
                link.setObjectName("sectionLink")
                link.setCursor(Qt.CursorShape.PointingHandCursor)
                link.clicked.connect(
                    lambda _=False, k=area.key, i=index: self.section_requested.emit(k, i))
                column.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
                links.append(link)
            sections.setVisible(area.key in self._expanded)
            row.setChecked(area.key in self._expanded)
            row.toggled.connect(
                lambda on, k=area.key, s=sections: self._set_expanded(k, s, on))
            self._rows_box.addWidget(row)
            self._rows_box.addWidget(sections)
            self.rows[area.key] = row
            self.links[area.key] = links
        n = self.total_changed()
        self.summary.setText("All at defaults" if n == 0 else
                             f"{n} changed from the defaults")

    def _set_expanded(self, key: str, sections: QWidget, on: bool) -> None:
        sections.setVisible(on)
        (self._expanded.add if on else self._expanded.discard)(key)

    def expand(self, key: str) -> None:
        row = self.rows.get(key)
        if row is not None:
            row.setChecked(True)


# ── The panel ──────────────────────────────────────────────────────────────────

class SectionDrawer(QWidget):
    """A panel sliding in from the right over its parent, holding one section.

    Covers the whole parent with a dimmed backdrop; clicking the backdrop,
    pressing Escape or **Done** closes it, and closing gives the section back
    to its tab.
    """

    closed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("drawerBackdrop")
        self._loan: Loan | None = None
        self._dim = 0.0

        self.panel = QFrame(self)
        self.panel.setObjectName("settingsDrawer")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QVBoxLayout(self.panel)
        column.setContentsMargins(24, 18, 16, 16)
        column.setSpacing(10)

        top = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.area_label = QLabel()
        self.area_label.setObjectName("drawerArea")
        self.title_label = QLabel()
        self.title_label.setObjectName("drawerTitle")
        self.title_label.setWordWrap(True)
        heading.addWidget(self.area_label)
        heading.addWidget(self.title_label)
        close = QPushButton("✕")
        close.setObjectName("linkButton")
        close.setToolTip("Close (Esc)")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(lambda: self.close_section())
        top.addLayout(heading, 1)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._holder = QWidget()
        self._holder.setObjectName("drawerHolder")
        self._holder_layout = QVBoxLayout(self._holder)
        self._holder_layout.setContentsMargins(0, 0, 8, 0)
        self._holder_layout.addStretch(1)
        self.scroll.setWidget(self._holder)
        column.addWidget(self.scroll, 1)

        bottom = QHBoxLayout()
        note = QLabel("Changes are kept as you make them.")
        note.setObjectName("stepHint")
        self.done_button = QPushButton("Done")
        self.done_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_button.clicked.connect(lambda: self.close_section())
        bottom.addWidget(note, 1)
        bottom.addWidget(self.done_button)
        column.addLayout(bottom)

        self._slide = QPropertyAnimation(self.panel, b"geometry", self)
        self._slide.setDuration(SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        parent.installEventFilter(self)
        self.hide()

    # ── Opening and closing ──

    def section(self) -> QWidget | None:
        return self._loan.widget if self._loan is not None else None

    def is_open(self) -> bool:
        return self._loan is not None

    def open_section(self, area_title: str, section: Section) -> None:
        self.close_section(emit=False)
        self.area_label.setText(area_title)
        self.title_label.setText(section.title)
        self._loan = Loan(section.box)
        self._holder_layout.insertWidget(0, section.box)
        section.box.show()
        self.scroll.verticalScrollBar().setValue(0)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        final = self._panel_rect()
        self._slide.stop()
        self._slide.setStartValue(final.translated(final.width(), 0))
        self._slide.setEndValue(final)
        self._slide.start()
        self._dim = 1.0
        self.update()
        self.done_button.setFocus()

    def close_section(self, emit: bool = True) -> None:
        if self._loan is None:
            return
        self._slide.stop()
        box = self._loan.widget
        if not sip.isdeleted(box):
            self._holder_layout.removeWidget(box)
        self._loan.give_back()
        self._loan = None
        self.hide()
        if emit:
            self.closed.emit()

    # ── Geometry and painting ──

    def _panel_rect(self) -> QRect:
        r = self.rect()
        width = min(DRAWER_WIDTH, max(int(r.width() * DRAWER_SHARE), min(r.width(), 420)))
        return QRect(r.width() - width, 0, width, r.height())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize \
                and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._slide.stop()
            self.panel.setGeometry(self._panel_rect())
        return False

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(17, 24, 39, int(70 * self._dim)))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Here rather than a shortcut, so a field that uses Escape itself (an
        # open combo box) keeps it, and anything it does not use closes this.
        if event.key() == Qt.Key.Key_Escape:
            self.close_section()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.close_section()
            return
        super().mousePressEvent(event)
