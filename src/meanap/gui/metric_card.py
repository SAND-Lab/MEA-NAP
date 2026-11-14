"""A card laid over a figure, saying what the metric it shows means.

Opened from the results viewer by clicking a figure's title or a legend
heading, or its ⓘ button. The text is the metric's card
(:mod:`meanap.metric_info`) with the run's own settings filled in; related
metrics are links, and Back returns along the way followed.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)

from meanap.metric_info import METRICS_DIR, MetricInfo, lookup, render_markdown

__all__ = ["MetricCard", "CARD_W", "card_markdown"]

#: The card's width, at most; it never covers more than most of the figure.
CARD_W = 520
#: A metric's picture, at most this wide: an illustration, not the subject.
IMAGE_W = 300

_LEVELS = {"node": "Per node", "recording": "Per recording", "concept": "Background"}
_FAMILIES = {"network": "network", "activity": "activity", "catnap": "calcium imaging",
             "spatiotemporal": "spatiotemporal"}


def card_markdown(card: MetricInfo, params=None, directory: Path = METRICS_DIR) -> str:
    """The Markdown the card shows: summary, picture, sections, related links."""
    text = render_markdown(card, params)
    summary, _, rest = text.partition("\n## ")
    parts = [summary.strip()]
    if card.image and (directory / card.image).is_file():
        parts.append(f"![{card.name}]({card.image})")
    if rest:
        parts.append("## " + rest.strip())
    related = [lookup(k, directory) for k in card.related]
    links = [f"[{c.name}](metric:{c.key})" for c in related if c is not None and c != card]
    if links:
        parts.append("## Related\n\n" + " · ".join(links))
    if card.also:
        parts.append("*Also explains:* " + ", ".join(f"`{k}`" for k in card.also))
    fields = [f.strip() for f in card.meta.get("params", "").split(",") if f.strip()]
    if fields:
        parts.append("*In a params file:* " + ", ".join(f"`{f}`" for f in fields))
    return "\n\n".join(parts)


class MetricCard(QFrame):
    """The overlay. :meth:`show_metric` opens it; × or Esc closes it."""

    closed = pyqtSignal()

    def __init__(self, parent: QWidget, directory: Path = METRICS_DIR) -> None:
        super().__init__(parent)
        #: Where the cards are: the metrics, or the settings (``SETTINGS_DIR``).
        self.directory = Path(directory)
        self.setObjectName("metricCard")
        self.setStyleSheet(
            "#metricCard { background: #ffffff; border: 1px solid #d1d5db;"
            " border-radius: 10px; }"
            "#metricCard QTextBrowser { border: none; background: transparent; }"
            "#metricCard QScrollBar:vertical { background: transparent; width: 10px;"
            " margin: 2px; border: none; }"
            "#metricCard QScrollBar::handle:vertical { background: #d5d9e0;"
            " border-radius: 3px; min-height: 28px; }"
            "#metricCard QScrollBar::handle:vertical:hover { background: #b9c0cb; }"
            "#metricCard QScrollBar::add-line:vertical, #metricCard QScrollBar::sub-line:vertical"
            " { height: 0px; }"
            "#metricCard QScrollBar::add-page:vertical, #metricCard QScrollBar::sub-page:vertical"
            " { background: transparent; }"
            "#metricChip { color: #4b5563; background: #eef2ff; border-radius: 8px;"
            " padding: 2px 8px; font-size: 11px; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        from PyQt6.QtGui import QColor

        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        self._params = None
        #: Where to lay the card, if not over the whole parent: () -> QRect.
        self.area = None
        #: The widest a picture is drawn (None: the text's width).
        self.image_width: int | None = IMAGE_W
        #: The cards shown, oldest first; the last is on screen.
        self.history: list[str] = []

        self.back = QPushButton("‹ Back")
        self.back.setObjectName("ghost")
        self.back.clicked.connect(self.go_back)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.title.setWordWrap(True)
        self.chip = QLabel()
        self.chip.setObjectName("metricChip")
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("ghost")
        self.close_button.setToolTip("Close (Esc)")
        self.close_button.setFixedWidth(34)
        self.close_button.clicked.connect(self.close_card)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setSearchPaths([str(self.directory)])
        self.text.anchorClicked.connect(self._on_link)
        # Pictures fit the text's width, which is known only once laid out.
        self.text.viewport().installEventFilter(self)
        self._fitted_width = -1

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self.back)
        head.addWidget(self.title, 1)
        head.addWidget(self.close_button)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 12, 12)
        box.setSpacing(6)
        box.addLayout(head)
        chip_row = QHBoxLayout()
        chip_row.addWidget(self.chip)
        chip_row.addStretch(1)
        box.addLayout(chip_row)
        box.addWidget(self.text, 1)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.close_card)
        self.hide()

    # ── content ──────────────────────────────────────────────────────────────

    def set_params(self, params) -> None:
        """The run's settings, for the text's ``{{param:…}}`` placeholders."""
        self._params = params

    def show_metric(self, key: str, *, fresh: bool = True) -> bool:
        """Show *key*'s card. *fresh* starts a new history; following a link
        does not. Returns False if there is no card for it."""
        card = lookup(key, self.directory)
        if card is None:
            return False
        if fresh:
            self.history = []
        if not self.history or self.history[-1] != card.key:
            self.history.append(card.key)
        self._fill(card)
        self.place()
        self.show()
        self.raise_()
        self.text.setFocus()
        return True

    @property
    def current(self) -> str | None:
        return self.history[-1] if self.history and self.isVisible() else None

    def _fill(self, card: MetricInfo) -> None:
        self.title.setText(card.name)
        if card.meta.get("tab"):                # a setting: where it is
            chip = f"{card.meta['tab']} tab"
        else:
            chip = " · ".join(t for t in (_LEVELS.get(card.level, ""),
                                           _FAMILIES.get(card.family, card.family)) if t)
        self.chip.setText(chip)
        self.chip.setVisible(bool(chip))
        self.text.setMarkdown(card_markdown(card, self._params, self.directory))
        self._fit_images()
        self.text.verticalScrollBar().setValue(0)
        self.back.setVisible(len(self.history) > 1)

    def _fit_images(self) -> None:
        """Pictures at most ``IMAGE_W`` wide (and never wider than the text),
        headings sized for a card rather than a page."""
        from PyQt6.QtGui import (
            QImage, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat,
            QTextImageFormat,
        )

        document = self.text.document()
        self._fitted_width = self.text.viewport().width()
        width = max(self.text.viewport().width() - 24, 120)
        if self.image_width is not None:
            width = min(width, self.image_width)
        block = document.begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if level:
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                heading = QTextCharFormat()
                # Markdown headings are sized by adjustment, not by points.
                heading.setProperty(QTextFormat.Property.FontSizeAdjustment,
                                    1 if level <= 2 else 0)
                cursor.mergeCharFormat(heading)
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                fmt = fragment.charFormat()
                if fmt.isImageFormat():
                    image = fmt.toImageFormat()
                    name = image.name()
                    if name.startswith("scaled/"):          # fitted before: the file
                        name = name.split("/", 2)[2]
                    picture = QImage(str(self.directory / name))
                    if not picture.isNull():
                        # Scaled here, smoothly, at the screen's pixel density:
                        # the document's own scaling skips pixels, and text in
                        # a picture drawn at 2x turns to noise.
                        w = min(width, picture.width())
                        h = picture.height() * w / picture.width()
                        ratio = self.devicePixelRatioF() or 1.0
                        fitted = picture.scaled(
                            max(int(w * ratio), 1), max(int(h * ratio), 1),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        fitted.setDevicePixelRatio(ratio)
                        url = f"scaled/{int(w)}/{name}"
                        document.addResource(QTextDocument.ResourceType.ImageResource.value,
                                             QUrl(url), fitted)
                        scaled = QTextImageFormat(image)
                        scaled.setName(url)
                        scaled.setWidth(w)
                        scaled.setHeight(h)
                        cursor = QTextCursor(document)
                        cursor.setPosition(fragment.position())
                        cursor.setPosition(fragment.position() + fragment.length(),
                                           QTextCursor.MoveMode.KeepAnchor)
                        cursor.setCharFormat(scaled)
                it += 1
            block = block.next()

    def eventFilter(self, watched, event) -> bool:
        from PyQt6.QtCore import QEvent

        if watched is self.text.viewport() and event.type() == QEvent.Type.Resize \
                and self.text.viewport().width() != self._fitted_width:
            self._fit_images()
        return super().eventFilter(watched, event)

    # ── moving about ─────────────────────────────────────────────────────────

    def _on_link(self, url: QUrl) -> None:
        if url.scheme() == "metric":
            self.show_metric(url.path() or url.toString().split(":", 1)[-1], fresh=False)
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)

    def go_back(self) -> None:
        if len(self.history) > 1:
            self.history.pop()
            card = lookup(self.history[-1], self.directory)
            if card is not None:
                self._fill(card)

    def close_card(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    # ── placing ──────────────────────────────────────────────────────────────

    def place(self, area: QRect | None = None) -> None:
        """Over the right of *area* (the parent's rectangle, by default)."""
        if area is None:
            area = self.area() if self.area is not None else self.parentWidget().rect()
        width = min(CARD_W, max(area.width() - 40, 280))
        self.setGeometry(area.right() - width - 12, area.top() + 12, width,
                         max(area.height() - 24, 200))
        self._fit_images()
