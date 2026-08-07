"""Tooltips that wrap, and look like the tutorial bubbles.

Qt lays a plain-text tooltip out on a single line however long it is. The
longest in this app rendered at 1468 px — most of a laptop screen, in a strip
one line tall, usually overlapping the very control it describes. Anything
worth explaining in a sentence was therefore unreadable.

Two changes fix it:

**Wrap by measured width, not character count.** A fixed character count guesses
wrong on a different font or display scale. :func:`wrap_to_width` asks the
actual font how wide each candidate line is, so the result is the requested
pixel width whatever the theme.

**Match the tutorial bubble**, which already solved "present a paragraph over a
dimmed UI": same dark panel, accent border, rounded corners, generous padding.
A tooltip and a tutorial step are the same kind of object — a short explanation
anchored to a control — and looking the same makes that legible.

Applied in bulk by :func:`wrap_tooltips`, so a tooltip written anywhere in the
GUI is formatted without its author having to remember to do it.
"""

from __future__ import annotations

import html

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QAction, QFontMetrics
from PyQt6.QtWidgets import QApplication, QToolTip, QWidget

from meanap.gui.tutorial import ACCENT

__all__ = ["TOOLTIP_QSS", "MAX_TOOLTIP_PX", "format_tooltip", "wrap_to_width",
           "set_tooltip", "wrap_tooltips", "install_tooltip_style"]

#: Target width for a wrapped tooltip. Narrower than the tutorial bubble's 560:
#: a tooltip appears unbidden next to the cursor, so it should occupy less of
#: the screen than something the reader deliberately opened.
MAX_TOOLTIP_PX = 380

#: Styled to match ``TutorialOverlay``'s bubble.
TOOLTIP_QSS = (
    "QToolTip {"
    "  background-color: #2d323b;"
    "  color: #f2f4f8;"
    f"  border: 1px solid {ACCENT};"
    "  border-radius: 6px;"
    "  padding: 6px 9px;"
    "  font-size: 12px;"
    "}"
)


def wrap_to_width(text: str, metrics: QFontMetrics, max_px: int) -> list[str]:
    """Split *text* into lines no wider than *max_px*, by measurement.

    Existing newlines are honoured as hard breaks, so a tooltip that was
    deliberately laid out keeps its shape. A single word wider than the limit is
    left over-long rather than broken mid-word — a hyphenated identifier is
    worse to read split than to read wide.
    """
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if metrics.horizontalAdvance(candidate) <= max_px:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def format_tooltip(text: str, widget: QObject | None = None,
                   max_px: int = MAX_TOOLTIP_PX) -> str:
    """Turn tooltip text into wrapped rich text.

    Returns the input untouched when it is already rich text — a caller that
    wrote markup meant it — or when it is short enough to need no help.
    """
    stripped = text.strip()
    if not stripped or stripped.startswith("<"):
        return text

    # A QAction has a tooltip but no font of its own; fall back to the
    # application's, which is what Qt draws its tooltip with anyway.
    font = getattr(widget, "font", None)
    font = font() if callable(font) else None
    if font is None:
        app = QApplication.instance()
        font = app.font() if app is not None else None
    if font is None:
        return text
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(stripped) <= max_px and "\n" not in stripped:
        return text

    lines = wrap_to_width(stripped, metrics, max_px)
    return "<div>" + "<br>".join(html.escape(line) for line in lines) + "</div>"


def set_tooltip(target: QObject, text: str, max_px: int = MAX_TOOLTIP_PX) -> None:
    """Set a tooltip, wrapped to a readable width."""
    target.setToolTip(format_tooltip(text, target, max_px))


def wrap_tooltips(root: QWidget, max_px: int = MAX_TOOLTIP_PX) -> int:
    """Wrap every tooltip already set on *root* and its children.

    Covers ``QAction`` as well as ``QWidget``: toolbar and menu tooltips live
    on actions, which are not widgets, and would otherwise be the only ones
    left unwrapped — exactly the long "what does this button do" text that
    needed wrapping most.

    Called once after a window is built, so tooltips written anywhere in the
    GUI are formatted without each author remembering to. Returns how many were
    changed.
    """
    changed = 0
    targets = [root, *root.findChildren(QWidget), *root.findChildren(QAction)]
    for target in targets:
        current = target.toolTip()
        if not current:
            continue
        formatted = format_tooltip(current, target, max_px)
        if formatted != current:
            target.setToolTip(formatted)
            changed += 1
    return changed


def install_tooltip_style(app: QApplication | None = None) -> None:
    """Append the tooltip styling to the application stylesheet.

    Appended rather than assigned: the app already carries a theme, and
    replacing its stylesheet to restyle tooltips would discard it.
    """
    app = app or QApplication.instance()
    if app is None:
        return
    existing = app.styleSheet() or ""
    if "QToolTip" in existing:
        return
    app.setStyleSheet(existing + "\n" + TOOLTIP_QSS)
    QToolTip.setFont(app.font())
