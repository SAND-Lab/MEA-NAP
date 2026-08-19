"""Settings that most runs never touch, folded away until asked for.

``Params`` has 140 fields. Roughly half are reachable from the window, and a
run's outcome usually turns on a dozen of them — the data, the sampling rate,
the lags, which steps to run. The rest are real settings that real analyses
occasionally need, and showing them all at once means the dozen that matter are
buried among the hundred that do not.

So each tab keeps its everyday settings in the open and puts the rest in one of
these: a header you can click, collapsed by default, with the number of settings
inside it so nothing is hidden *silently*. A toggle in the toolbar opens every
section at once, for someone who would rather see the lot.

**Advanced does not mean dangerous.** Nothing here is disabled, and nothing
behaves differently for being folded away — a collapsed section's widgets hold
and save their values exactly as an open one's do. The distinction is only how
often a setting is worth looking at.

The window finds these by type rather than by a registry (see
:func:`set_all_expanded`), so a tab that grows one later is picked up with no
wiring.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout, QToolButton, QVBoxLayout, QWidget,
)

__all__ = ["AdvancedSection", "set_all_expanded", "load_preference",
           "save_preference", "SETTINGS_KEY"]

#: Where the toolbar toggle's state is remembered between sessions.
SETTINGS_KEY = "gui/show_advanced"


class AdvancedSection(QWidget):
    """A collapsible group of less-used settings.

    Add rows to :meth:`form`, exactly as you would to a tab's own
    :class:`QFormLayout`::

        advanced = AdvancedSection()
        advanced.form().addRow("Tail percentile", self.tail)
    """

    toggled = pyqtSignal(bool)

    def __init__(self, title: str = "Advanced settings",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(2)

        self.header = QToolButton()
        self.header.setCheckable(True)
        self.header.setChecked(False)
        self.header.setArrowType(Qt.ArrowType.RightArrow)
        self.header.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(
            "QToolButton { border: none; font-weight: 600; padding: 2px 0; }")
        self.header.setToolTip(
            "Settings most runs leave alone. They are saved and used whether "
            "this is open or closed — folding them away only keeps the "
            "everyday settings easy to find."
        )
        self.header.toggled.connect(self._on_toggled)

        self._body = QWidget()
        self._form = QFormLayout(self._body)
        self._form.setContentsMargins(14, 4, 0, 0)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._body.setVisible(False)

        layout.addWidget(self.header)
        layout.addWidget(self._body)
        # The header carries a count of what it holds, but rows are added after
        # construction, so counting now would always say zero. Once round the
        # event loop is after the panel is fully built and does not wait for the
        # tab to be shown — a hidden tab's headers are still correct the moment
        # it appears. Parented to self so it dies with the widget rather than
        # firing into a deleted one.
        self._label_timer = QTimer(self)
        self._label_timer.setSingleShot(True)
        self._label_timer.timeout.connect(self._relabel)
        self._label_timer.start(0)
        self._relabel()

    # ── Contents ──────────────────────────────────────────────────────────────

    def form(self) -> QFormLayout:
        """The layout to add rows to."""
        return self._form

    def count(self) -> int:
        """How many settings are in here — not counting rows a mode hid.

        A panel may take a row out for the running pipeline (see
        ``DataPanel.set_mode``), and a header promising three settings that
        opens onto two is a small lie the count exists to avoid.
        """
        return sum(1 for row in range(self._form.rowCount())
                   if self._form.isRowVisible(row))

    def refresh_label(self) -> None:
        """Re-read the count, for a caller that just showed or hid a row."""
        self._relabel()

    # ── Open and closed ───────────────────────────────────────────────────────

    def is_expanded(self) -> bool:
        return self.header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        if self.header.isChecked() != expanded:
            self.header.setChecked(expanded)

    def showEvent(self, event) -> None:
        """Relabel on display, for rows added after the timer above ran."""
        super().showEvent(event)
        self._relabel()

    def _on_toggled(self, expanded: bool) -> None:
        self.header.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._body.setVisible(expanded)
        self._relabel()
        self.toggled.emit(expanded)

    def _relabel(self) -> None:
        # The count is what stops this reading as "there is nothing here": a
        # closed section that says how much it holds is an invitation, a bare
        # one is a dead end.
        n = self.count()
        self.header.setText(self._title if self.is_expanded() or not n
                            else f"{self._title}  ({n})")


def set_all_expanded(root: QWidget, expanded: bool) -> int:
    """Open or close every section under *root*. Returns how many it found.

    By type rather than through a registry: a panel that grows a section later
    is picked up without anyone remembering to register it, and nothing has to
    be unregistered when a panel is destroyed.
    """
    sections = root.findChildren(AdvancedSection)
    for section in sections:
        section.set_expanded(expanded)
    return len(sections)


def load_preference() -> bool:
    """Whether advanced settings were showing when the window last closed."""
    value = QSettings("SAND Lab", "MEA-NAP").value(SETTINGS_KEY, False)
    # QSettings hands back the string "false" on some platforms.
    return value if isinstance(value, bool) else str(value).lower() == "true"


def save_preference(expanded: bool) -> None:
    QSettings("SAND Lab", "MEA-NAP").setValue(SETTINGS_KEY, bool(expanded))
