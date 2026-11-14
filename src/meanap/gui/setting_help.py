"""What a run setting does, a click away: ⓘ marks on the settings tabs.

Each card in ``gui/assets/settings`` names the tab it is for and the labels
it explains — the row labels and group titles exactly as the tab shows them
(``meanap.metric_info``). :class:`SettingHelp` finds those labels on the
tabs, marks each with an ⓘ, and opens the card over the tab when one is
clicked.

The labels are matched as text rather than registered by the panels, so
the cards can be written and corrected without touching the panels; a test
checks every card's labels still exist, so a renamed label is caught.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QStyle, QStyleOptionGroupBox, QTabWidget, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.metric_card import MetricCard
from meanap.gui.settings_search import _plain
from meanap.metric_info import SETTINGS_DIR, MetricInfo, all_metrics

__all__ = ["SettingHelp", "MARK", "MARK_NAME", "LABEL", "settings_cards", "cards_by_label", "card_text",
           "card_tabs"]

#: The mark a label with a card carries.
MARK = "ⓘ"
_ACCENT = "#2563eb"
_KEY = "settingHelpKey"
#: The object name of an ⓘ link.
MARK_NAME = "settingHelpMark"
#: The label text a marked widget stands for (its own text, for a section's mark).
LABEL = "settingHelpLabel"


def card_text(text: str) -> str:
    """A label as a card writes it, as :func:`_plain` reads the GUI's: a card
    may write "&" or Qt's "&&" for an ampersand."""
    return " ".join(text.replace("&&", "&").split()).rstrip(":").strip()


def card_tabs(card: MetricInfo) -> list[str]:
    """The tabs a card is for: ``tab``, and any in ``also_tabs`` (";")."""
    tabs = [card.meta.get("tab", "")] + card.meta.get("also_tabs", "").split(";")
    return [card_text(t) for t in tabs if t.strip()]


def settings_cards() -> dict[str, MetricInfo]:
    return all_metrics(SETTINGS_DIR)


def cards_by_label() -> dict[tuple[str, str], str]:
    """``(tab, label) → card key`` for every label a card explains."""
    out: dict[tuple[str, str], str] = {}
    for key, card in settings_cards().items():
        for tab in card_tabs(card):
            for label in card.labels:
                out.setdefault((tab, card_text(label)), key)
    return out


class SettingHelp(QObject):
    """Marks the labels on *tabs* that have a card, and shows the card.

    Call :meth:`attach` after the tabs are built and again whenever a panel
    may have relabelled itself (a mode switch): it is idempotent.
    """

    def __init__(self, tabs: QTabWidget, host: QWidget | None = None, area=None) -> None:
        """*host* is the widget the card is laid over (the tabs, by default);
        *area*, a ``() -> QRect`` in *host*'s coordinates, where on it."""
        super().__init__(tabs)
        self.tabs = tabs
        self.host = host or tabs
        self.card = MetricCard(self.host, SETTINGS_DIR)
        # A setting's picture is a diagram with words on it: the full width.
        self.card.image_width = None
        # Below the tab strip, over the page, unless told otherwise.
        self.card.area = area or (
            lambda: tabs.rect().adjusted(0, tabs.tabBar().height(), 0, 0))
        tabs.currentChanged.connect(lambda _i: self.card.close_card())
        self.host.installEventFilter(self)
        #: Label widgets marked, by card key (for tests and for finding them).
        self.marked: dict[str, list[QWidget]] = {}

    # ── marking ──────────────────────────────────────────────────────────────
    #
    # The labels and titles themselves are left as they are: panels relabel
    # them as modes change, and code reads them back. The ⓘ is a small link
    # of its own, a child of the label or box it explains, kept beside the
    # text (see eventFilter).

    def attach(self) -> int:
        """Mark every label on the tabs that has a card; returns how many."""
        index = cards_by_label()
        self.marked = {}
        for i in range(self.tabs.count()):
            page, tab = self.tabs.widget(i), _plain(self.tabs.tabText(i))
            for form in page.findChildren(QFormLayout):
                for row in range(form.rowCount()):
                    item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                    label = item.widget() if item is not None else None
                    if isinstance(label, QLabel):
                        key = index.get((tab, _plain(label.text()))) \
                            or label.property(_KEY)
                        if key is not None:
                            self._mark(label, key, _plain(label.text()))
            for group in page.findChildren(QGroupBox):
                key = index.get((tab, _plain(group.title()))) or group.property(_KEY)
                if key is not None:
                    self._mark(group, key, _plain(group.title()))
            for section in page.findChildren(AdvancedSection):
                key = index.get((tab, _plain(section._title)))
                if key is not None:
                    self._mark_section(section, key)
        return sum(len(v) for v in self.marked.values())

    def _new_mark(self, parent: QWidget, key: str, label: str) -> QLabel:
        mark = getattr(parent, "_help_mark", None)
        if mark is None:
            mark = QLabel(parent)
            mark.setObjectName(MARK_NAME)
            mark.setTextFormat(Qt.TextFormat.RichText)
            mark.linkActivated.connect(self._on_link)
            parent._help_mark = mark
        mark.setText(f'<a href="setting:{key}" style="color:{_ACCENT}; '
                     f'text-decoration:none;">{MARK}</a>')
        mark.setToolTip(f"What “{label}” does.")
        mark.adjustSize()
        parent.setProperty(_KEY, key)
        parent.setProperty(LABEL, label)
        self.marked.setdefault(key, []).append(parent)
        return mark

    def _mark(self, widget: QWidget, key: str, label: str) -> None:
        """A row label or a box: the mark floats just after its text."""
        fresh = getattr(widget, "_help_mark", None) is None
        mark = self._new_mark(widget, key, label)
        if fresh:
            if isinstance(widget, QLabel):
                # Room for the mark after the text, so a form column that
                # fits the label fits it too.
                margins = widget.contentsMargins()
                widget.setContentsMargins(margins.left(), margins.top(),
                                          margins.right() + mark.width() + 4,
                                          margins.bottom())
            widget.installEventFilter(self)
        self._place_mark(widget)
        mark.show()

    def _mark_section(self, section: AdvancedSection, key: str) -> None:
        """A folding section's header toggles it, so its ⓘ sits beside it."""
        fresh = getattr(section, "_help_mark", None) is None
        mark = self._new_mark(section, key, _plain(section._title))
        if fresh:
            layout = section.layout()
            layout.removeWidget(section.header)
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(section.header)
            row.addWidget(mark)
            row.addStretch(1)
            layout.insertLayout(0, row)

    def _place_mark(self, widget: QWidget) -> None:
        mark = getattr(widget, "_help_mark", None)
        if mark is None:
            return
        if isinstance(widget, QGroupBox):
            text = widget.title()
            rect = self._title_rect(widget)
            at = QPoint(rect.right() + 4, rect.center().y() - mark.height() // 2)
        else:
            text = widget.text()
            metrics = widget.fontMetrics()
            margins = widget.contentsMargins()
            room = widget.width() - margins.right()
            width = metrics.horizontalAdvance(_plain(text))
            if widget.alignment() & Qt.AlignmentFlag.AlignRight:
                left = room - width
            else:
                left = margins.left()
            at = QPoint(min(left + width + 4, widget.width() - mark.width()),
                        (widget.height() - mark.height()) // 2)
        # A box lent to the simple view's drawer gives up its title for the
        # drawer's heading; its mark goes with it.
        mark.setVisible(bool(_plain(text)))
        if mark.pos() != at:
            mark.move(at)

    # ── opening ──────────────────────────────────────────────────────────────

    def _on_link(self, link: str) -> None:
        if link.startswith("setting:"):
            self.open(link.split(":", 1)[1])

    def open(self, key: str) -> bool:
        """Show card *key* over the tabs (a second click on its mark closes it)."""
        if self.card.current == key:
            self.card.close_card()
            return True
        return self.card.show_metric(key)

    @staticmethod
    def _title_rect(group: QGroupBox):
        option = QStyleOptionGroupBox()
        group.initStyleOption(option)
        return group.style().subControlRect(
            QStyle.ComplexControl.CC_GroupBox, option,
            QStyle.SubControl.SC_GroupBoxLabel, group)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.host:
            if event.type() == QEvent.Type.Resize and self.card.isVisible():
                self.card.place()
            return False
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Paint,
                            QEvent.Type.FontChange):
            self._place_mark(watched)
        return False
