"""Find a setting or a feature by name, from either view.

The index is not a hand-kept list. It is read off the panels as they stand —
every labelled row, check box, group and button on the tabs the current mode
shows — so a setting added to a panel is searchable without anyone remembering
to register it, and one a mode hides is not offered.

The pieces:

* :func:`index_tabs` walks a :class:`QTabWidget` into :class:`SearchEntry` rows.
* :func:`search` ranks entries against a query.
* :class:`SearchBox` is the field and its drop-down list of matches.
* :func:`reveal_widget` / :class:`Flash` bring a widget into view and mark it.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from PyQt6 import sip
from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QAbstractButton, QCheckBox, QFormLayout, QFrame, QGroupBox, QLabel,
    QLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
    QScrollArea, QStackedWidget, QStyle, QStyledItemDelegate, QTabWidget,
    QStyleOptionViewItem, QWidget,
)

__all__ = [
    "SearchEntry", "index_tabs", "search", "SearchBox", "reveal_widget",
    "Flash", "MAX_RESULTS",
]

#: Rows shown in the drop-down; more than this and the list stops being a glance.
MAX_RESULTS = 12

#: Kinds, in the order a tie is broken.
SETTING, VIEW, FEATURE, SECTION = "Setting", "View", "Feature", "Section"
_KIND_ORDER = {SETTING: 0, VIEW: 1, FEATURE: 2, SECTION: 3}

#: Words people use for a setting that the setting's label does not.
#: Each key also matches any of its values, so "sampling rate" finds
#: "Sampling frequency" and "fs" finds it too.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "rate": ("frequency", "fs", "hz"),
    "frequency": ("rate", "fs", "hz"),
    "fs": ("sampling frequency", "sampling rate"),
    "hz": ("frequency", "rate"),
    "folder": ("directory", "path"),
    "directory": ("folder", "path"),
    "dir": ("folder", "directory"),
    "sheet": ("spreadsheet",),
    "excel": ("spreadsheet",),
    "csv": ("spreadsheet",),
    "genotype": ("group",),
    "group": ("genotype",),
    "electrode": ("channel", "layout"),
    "channel": ("electrode",),
    "graph": ("network",),
    "network": ("graph", "connectivity"),
    "correlation": ("sttc", "connectivity"),
    "sttc": ("correlation", "tiling"),
    "lag": ("timescale", "window"),
    "plot": ("figure",),
    "figure": ("plot",),
    "image": ("figure", "plot"),
    "statistics": ("stats",),
    "machine learning": ("ml",),
    "calcium": ("catnap", "cat-nap", "suite2p"),
    "stim": ("stimulation",),
    "stimulus": ("stimulation", "stim"),
    "spike": ("detection",),
    "threshold": ("multiplier", "cutoff"),
    "parallel": ("workers", "cores"),
    "cpu": ("workers", "cores", "computer"),
}


@dataclass
class SearchEntry:
    """One thing the search can find."""

    title: str
    #: Where it lives, for the reader: "Spike detection › Advanced settings".
    where: str
    kind: str = SETTING
    #: The widget to bring into view, if there is one.
    target: QWidget | None = None
    #: What choosing it does. Set by whoever builds the entry; the box only calls it.
    activate: Callable[[], None] | None = None
    #: Extra text the query may match (tooltips, the setting's other names).
    keywords: str = ""
    #: Breaks ties between equally good matches, lower first — the view on
    #: screen ranks its own entries ahead of the ones that would leave it.
    rank: int = 1
    _hay: str = field(default="", repr=False)

    def haystack(self) -> str:
        if not self._hay:
            self._hay = _norm(" ".join((self.title, self.where, self.keywords)))
        return self._hay


# ── Reading the panels ─────────────────────────────────────────────────────────

_TAGS = re.compile(r"<[^>]+>")
_LEADING_SYMBOLS = re.compile(r"^[^\w(\"'“]+")


def _plain(text: str) -> str:
    """A label's text as a reader sees it: no markup, mnemonic or trailing colon."""
    text = html.unescape(_TAGS.sub("", text or ""))
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(text.split()).rstrip(":").strip()


def _norm(text: str) -> str:
    return " ".join(_plain(text).lower().replace("-", " ").replace("_", " ").split())


def _reachable(widget: QWidget, page: QWidget) -> bool:
    """Whether *widget* can be brought on screen by revealing it.

    Hidden is fine when the thing hiding it is a folded advanced section or an
    unselected page of a stack — revealing opens those. Hidden for any other
    reason (a row the mode has switched off, a box that only appears while
    running) means it is not on offer, so it is not found.
    """
    from meanap.gui.advanced import AdvancedSection

    w: QWidget | None = widget
    while w is not None and w is not page:
        if w.isHidden():
            parent = w.parentWidget()
            folded = isinstance(parent, AdvancedSection) and w is parent._body
            if not (folded or isinstance(parent, QStackedWidget)):
                return False
        w = w.parentWidget()
    return w is page


def _first_widget(item) -> QWidget | None:
    if item is None:
        return None
    if item.widget() is not None:
        return item.widget()
    layout: QLayout | None = item.layout()
    if layout is None:
        return None
    for i in range(layout.count()):
        found = _first_widget(layout.itemAt(i))
        if found is not None:
            return found
    return None


def _breadcrumb(widget: QWidget, page: QWidget, tab: str) -> str:
    """Tab, then the groups and folded sections between it and *widget*, outermost first."""
    from meanap.gui.advanced import AdvancedSection

    parts: list[str] = []
    w = widget.parentWidget()
    while w is not None and w is not page:
        if isinstance(w, QGroupBox) and _plain(w.title()):
            parts.append(_plain(w.title()))
        elif isinstance(w, AdvancedSection):
            parts.append(_plain(w._title))
        w = w.parentWidget()
    return " › ".join([tab, *reversed(parts)])


def _tooltip(*widgets: QWidget | None) -> str:
    return " ".join(_plain(w.toolTip()) for w in widgets if w is not None and w.toolTip())


def index_tabs(tabs: QTabWidget) -> list[SearchEntry]:
    """Every setting, group and button on the tabs *tabs* is showing.

    Entries carry their tab page as ``target``'s owner through
    :attr:`SearchEntry.where`; they have no ``activate`` — the window decides
    what choosing one does (switching tab, unfolding, scrolling).
    """
    entries: list[SearchEntry] = []
    for index in range(tabs.count()):
        page = tabs.widget(index)
        tab = _plain(tabs.tabText(index))
        seen: set[int] = set()

        def add(title: str, target: QWidget, kind: str, keywords: str = "") -> None:
            # Without the emoji some buttons lead with ("📦  Make bundle…").
            title = _LEADING_SYMBOLS.sub("", _plain(title))
            if not title or len(title) > 80 or id(target) in seen:
                return
            if not _reachable(target, page):
                return
            seen.add(id(target))
            entry = SearchEntry(title, _breadcrumb(target, page, tab), kind,
                                target, None, keywords)
            entry.page = page  # type: ignore[attr-defined]
            entries.append(entry)

        for form in page.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                label = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                label_w = label.widget() if label is not None else None
                field_w = _first_widget(form.itemAt(row, QFormLayout.ItemRole.FieldRole))
                if not isinstance(label_w, QLabel) or field_w is None:
                    continue
                add(label_w.text(), field_w, SETTING, _tooltip(label_w, field_w))
                seen.add(id(label_w))
        for box in page.findChildren(QAbstractButton):
            if isinstance(box, (QCheckBox, QRadioButton)):
                add(box.text(), box, SETTING, _tooltip(box))
            elif isinstance(box, QPushButton) and not box.isCheckable():
                add(box.text(), box, FEATURE, _tooltip(box))
        for group in page.findChildren(QGroupBox):
            add(group.title(), group, SECTION, _tooltip(group))
    return entries


# ── Ranking ────────────────────────────────────────────────────────────────────

def _alternatives(token: str) -> tuple[str, ...]:
    return (token, *SYNONYMS.get(token, ()))


def _has(text: str, needle: str) -> bool:
    """Whether *needle* starts a word of *text* (both normalised).

    Word starts, not anywhere: "fs" should find "fs", not "offset", and
    "rate" should not find "separate".
    """
    start = 0
    while True:
        at = text.find(needle, start)
        if at < 0:
            return False
        if at == 0 or not text[at - 1].isalnum():
            return True
        start = at + 1


def _all(text: str, tokens: list[str], synonyms: bool = True) -> bool:
    return all(any(_has(text, alt) for alt in (_alternatives(t) if synonyms else (t,)))
               for t in tokens)


def _score(entry: SearchEntry, query: str, tokens: list[str]) -> int | None:
    """Lower is better; ``None`` when *entry* does not match at all."""
    if not _all(entry.haystack(), tokens):
        return None
    title = _norm(entry.title)
    if title == query:
        return 0
    if title.startswith(query):
        return 1
    if _has(title, query):
        return 2
    if _all(title, tokens, synonyms=False):
        return 3
    if _all(title, tokens):
        return 4
    if _all(f"{title} {_norm(entry.where)}", tokens):
        return 5
    return 6  # matched only on a tooltip or keyword


def search(entries: Iterable[SearchEntry], query: str,
           limit: int = MAX_RESULTS) -> list[SearchEntry]:
    """The entries matching every word of *query*, best first."""
    query = _norm(query)
    if not query:
        return []
    tokens = query.split()
    scored = []
    for order, entry in enumerate(entries):
        score = _score(entry, query, tokens)
        if score is not None:
            scored.append((score, entry.rank, _KIND_ORDER.get(entry.kind, 9),
                           len(entry.title), order, entry))
    scored.sort(key=lambda s: s[:5])
    # Two widgets with one name in one place (a mirrored field) read as a
    # duplicate, and only the first can be meant.
    out: list[SearchEntry] = []
    names: set[tuple[str, str]] = set()
    for *_, entry in scored:
        key = (_norm(entry.title), entry.where)
        if key in names:
            continue
        names.add(key)
        out.append(entry)
        if len(out) >= limit:
            break
    return out


# ── Bringing a widget into view ────────────────────────────────────────────────

def reveal_widget(widget: QWidget) -> None:
    """Unfold, unstack and scroll whatever stands between *widget* and the screen."""
    from meanap.gui.advanced import AdvancedSection

    w: QWidget | None = widget
    while w is not None:
        parent = w.parentWidget()
        if isinstance(w, AdvancedSection):
            w.set_expanded(True)
        if isinstance(parent, QStackedWidget) and parent.currentWidget() is not w:
            parent.setCurrentWidget(w)
        w = parent
    # Scroll every enclosing area, innermost first: a scrolled column inside a
    # scrolled tab needs both.
    w = widget.parentWidget()
    while w is not None:
        if isinstance(w, QScrollArea):
            w.ensureWidgetVisible(widget, 60, 60)
        w = w.parentWidget()


class Flash(QWidget):
    """A rounded outline drawn over a widget for a moment, then gone.

    A child of the window rather than a style change on the widget, so it works
    on any widget and leaves nothing behind on the widget's own stylesheet.
    """

    DURATION_MS = 1600

    def __init__(self, target: QWidget) -> None:
        window = target.window()
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._target = target
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._place()
        self.show()
        self.raise_()
        self._timer.start()

    def _place(self) -> None:
        top_left = self._target.mapTo(self.parentWidget(), self._target.rect().topLeft())
        rect = QRect(top_left, self._target.size()).adjusted(-5, -4, 5, 4)
        self.setGeometry(rect)

    def _tick(self) -> None:
        self._ticks += 1
        # Gone with its target: a tab or view switched away mid-flash would
        # otherwise leave an outline over whatever is there now.
        if (sip.isdeleted(self._target) or not self._target.isVisible()
                or self._ticks * self._timer.interval() >= self.DURATION_MS):
            self._timer.stop()
            self.deleteLater()
            return
        self._place()
        self.update()

    def opacity(self) -> float:
        done = self._ticks * self._timer.interval() / self.DURATION_MS
        return 1.0 if done < 0.6 else max(0.0, (1.0 - done) / 0.4)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = QColor("#f59e0b")
        colour.setAlphaF(self.opacity())
        pen = painter.pen()
        pen.setColor(colour)
        pen.setWidth(3)
        painter.setPen(pen)
        fill = QColor("#f59e0b")
        fill.setAlphaF(0.12 * self.opacity())
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)


# ── The field ──────────────────────────────────────────────────────────────────

class _Delegate(QStyledItemDelegate):
    """Title, then where it lives in grey on the same line."""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: D102
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        title = opt.text
        where = index.data(Qt.ItemDataRole.UserRole + 1) or ""
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        rect = opt.rect.adjusted(10, 0, -10, 0)
        painter.save()
        painter.setFont(opt.font)
        main = opt.palette.color(QPalette.ColorRole.HighlightedText if selected
                                 else QPalette.ColorRole.Text)
        painter.setPen(main)
        metrics = painter.fontMetrics()
        title_w = min(metrics.horizontalAdvance(title) + 2, int(rect.width() * 0.6))
        painter.drawText(rect.adjusted(0, 0, -(rect.width() - title_w), 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         metrics.elidedText(title, Qt.TextElideMode.ElideRight, title_w))
        grey = QColor(main)
        grey.setAlphaF(0.55)
        painter.setPen(grey)
        rest = rect.adjusted(title_w + 14, 0, 0, 0)
        painter.drawText(rest, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                         metrics.elidedText(where, Qt.TextElideMode.ElideLeft, rest.width()))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: D102, N802
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), option.fontMetrics.height() + 12))


class SearchBox(QLineEdit):
    """A search field with its matches in a list just below it.

    *provider* is called each time the field is used, so the entries always
    describe the window as it is now — after a mode switch, a run that added a
    button, a section unfolded. The list is a child of the window, not a popup
    window: it never takes focus from the field, so typing carries on while it
    is open, and there is no window-manager behaviour to differ by platform.
    """

    #: Emitted with the chosen entry, after its ``activate`` (if any) has run.
    chosen = pyqtSignal(object)

    def __init__(self, provider: Callable[[], list[SearchEntry]],
                 placeholder: str = "Search settings",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._entries: list[SearchEntry] | None = None
        self._matches: list[SearchEntry] = []
        self.setObjectName("settingsSearch")
        self.setClearButtonEnabled(True)
        shortcut = QKeySequence(QKeySequence.StandardKey.Find).toString(
            QKeySequence.SequenceFormat.NativeText)
        self.setPlaceholderText(f"🔍  {placeholder}" + (f"   {shortcut}" if shortcut else ""))
        self.setToolTip(
            "Type part of a setting's name, or something it does — "
            "\"sampling\", \"threshold\", \"bundle\". Choosing one takes you to it.")
        self.setMinimumWidth(240)

        self._list = QListWidget()
        self._list.setObjectName("settingsSearchResults")
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setItemDelegate(_Delegate(self._list))
        self._list.setFrameShape(QFrame.Shape.StyledPanel)
        self._list.setStyleSheet(
            "#settingsSearchResults { border: 1px solid palette(mid); "
            "border-radius: 6px; background: palette(base); }")
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(lambda item: self._choose(self._list.row(item)))
        self._list.hide()
        self._empty = QListWidgetItem()

        self.textEdited.connect(self._refresh)
        self.textChanged.connect(lambda text: None if text else self.hide_results())

    # ── Showing matches ──

    def entries(self) -> list[SearchEntry]:
        """The index, built when the field is first used since it was last left."""
        if self._entries is None:
            self._entries = self._provider()
        return self._entries

    def matches(self) -> list[SearchEntry]:
        return list(self._matches)

    def results_visible(self) -> bool:
        return self._list.isVisible()

    def _refresh(self, text: str | None = None) -> None:
        text = self.text() if text is None else text
        self._matches = search(self.entries(), text)
        self._list.clear()
        if not text.strip():
            self.hide_results()
            return
        if not self._matches:
            item = QListWidgetItem("Nothing called that")
            item.setData(Qt.ItemDataRole.UserRole + 1, "try another word")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        for entry in self._matches:
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole + 1, f"{entry.where}")
            item.setToolTip(f"{entry.kind} · {entry.where}")
            self._list.addItem(item)
        if self._matches:
            self._list.setCurrentRow(0)
        self._show_results()

    def _show_results(self) -> None:
        window = self.window()
        if self._list.parentWidget() is not window:
            self._list.setParent(window)
        row_h = self._list.sizeHintForRow(0) if self._list.count() else 24
        height = row_h * self._list.count() + 6
        width = max(self.width(), 460)
        top_left = self.mapTo(window, self.rect().bottomLeft())
        x = min(top_left.x(), max(0, window.width() - width - 8))
        self._list.setGeometry(x, top_left.y() + 2, width, height)
        self._list.show()
        self._list.raise_()

    def hide_results(self) -> None:
        # The list belongs to the window, which can be torn down first.
        if not sip.isdeleted(self._list):
            self._list.hide()

    # ── Choosing ──

    def _choose(self, row: int) -> None:
        if not 0 <= row < len(self._matches):
            return
        entry = self._matches[row]
        self.hide_results()
        self.clear()
        self._entries = None
        if entry.activate is not None:
            entry.activate()
        self.chosen.emit(entry)

    def choose_text(self, text: str) -> SearchEntry | None:
        """Type *text* and take the first match — for tests, and for Return."""
        self.setText(text)
        self._refresh(text)
        if not self._matches:
            return None
        entry = self._matches[0]
        self._choose(0)
        return entry

    def keyPressEvent(self, event) -> None:  # noqa: D102, N802
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._matches:
            if not self._list.isVisible():
                self._show_results()
            step = 1 if key == Qt.Key.Key_Down else -1
            row = (self._list.currentRow() + step) % len(self._matches)
            self._list.setCurrentRow(row)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._matches:
                self._choose(max(0, self._list.currentRow()))
            return
        if key == Qt.Key.Key_Escape:
            if self._list.isVisible():
                self.hide_results()
            else:
                self.clear()
                self.clearFocus()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: D102, N802
        # The window may have changed since the field was last used.
        self._entries = None
        super().focusInEvent(event)
        if self.text().strip():
            self._refresh()

    def focusOutEvent(self, event) -> None:  # noqa: D102, N802
        super().focusOutEvent(event)
        # Clicking a row takes no focus (the list refuses it), so this only
        # fires when the person has gone somewhere else entirely.
        self.hide_results()

    def install_shortcut(self, host: QWidget) -> QShortcut:
        """Ctrl+F (⌘F) on *host* puts the cursor here."""
        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), host)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.focus_search)
        return shortcut

    def focus_search(self) -> None:
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.selectAll()
