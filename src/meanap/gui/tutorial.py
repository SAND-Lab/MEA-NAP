"""Guided coach-mark tutorial for the MEA-NAP GUI.

The tutorial dims the whole window and highlights one real tab/field at a
time, walking the user through every required setting for the pipeline they
pick (MEA-NAP, MEA-Stim or CAT-NAP) and landing them on the Run tab
ready to run. The dimming scrim is purely visual: the highlighted field stays
fully interactive so users fill in real values as they go.

``TutorialOverlay`` is generic — it consumes a list of :class:`TutorialStep`.
The step lists themselves live in ``main_window`` where the panel widgets are
in scope (see ``MainWindow._build_*_steps``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QRegion
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from meanap.gui.branding import logo_pixmap

ACCENT = "#4f8ef7"

# Bubble border width, in px. Kept as a constant because _size_bubble must
# subtract it when working out how wide the wrapped text really gets.
BUBBLE_BORDER = 1

# A step's target is resolved lazily (after the tab switch) and may be a live
# widget, a global-coordinate QRect (e.g. a tab-bar tab), or None (centred).
TargetT = Callable[[], Union[QWidget, QRect, None]]


@dataclass
class TutorialStep:
    """One coach-mark: switch to *tab_index*, highlight *target*, show text.

    ``diagram`` is optional pre-formatted text — a folder tree, say — shown in a
    monospace block under the body. Keep its lines short: unlike the body it
    does not wrap, so a long line widens the whole bubble.
    """

    title: str
    body: str
    tab_index: Optional[int] = None
    target: Optional[TargetT] = None
    diagram: Optional[str] = None


def tabbar_target(tabs: QTabWidget, index: int) -> TargetT:
    """A target that highlights tab *index* in the tab bar."""

    def resolve() -> QRect:
        bar = tabs.tabBar()
        r = bar.tabRect(index)
        return QRect(bar.mapToGlobal(r.topLeft()), r.size())

    return resolve


class TutorialOverlay(QWidget):
    """Full-window dimming overlay that steps through a list of coach-marks."""

    pipeline_chosen = pyqtSignal(str)  # "meanap" | "meastim" | "catnap"
    finished = pyqtSignal()

    def __init__(self, host: QMainWindow, tabs: QTabWidget) -> None:
        super().__init__(host)
        self._host = host
        self._tabs = tabs
        self._steps: list[TutorialStep] = []
        self._index = 0
        self._mode = "idle"  # "chooser" | "steps"
        self._highlight = QRect()
        self._busy = False

        # Interaction is controlled with a mask (see _update_mask): the
        # highlighted field is a real hole so clicks reach it, the bubble stays
        # solid so its buttons work, and the dimmed scrim blocks everything
        # else. WA_TransparentForMouseEvents is NOT used — it would make Qt skip
        # the overlay *and its children*, leaving the bubble buttons dead.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._bubble = QFrame(self)
        self._body_label: QLabel | None = None
        self._bubble.setObjectName("tutorialBubble")
        self._bubble.setStyleSheet(
            "#tutorialBubble {"
            "  background-color: #2d323b;"
            f"  border: {BUBBLE_BORDER}px solid {ACCENT};"
            "  border-radius: 10px;"
            "}"
            "#tutorialBubble QLabel { color: #f2f4f8; background: transparent; }"
            "#tutorialBubble QLabel#tutTitle { font-size: 14px; font-weight: 700; }"
            "#tutorialBubble QLabel#tutBody  { font-size: 12px; }"
            "#tutorialBubble QLabel#tutDiagram {"
            "  font-family: 'DejaVu Sans Mono', Menlo, Consolas, monospace;"
            "  font-size: 11px; color: #c9d3e0;"
            "  background: rgba(255, 255, 255, 0.06);"
            "  border-radius: 5px; padding: 8px 10px;"
            "}"
            "#tutorialBubble QLabel#tutCount { color: #9aa4b2; font-size: 11px; }"
            "#tutorialBubble QPushButton {"
            "  padding: 6px 14px; border-radius: 6px; font-weight: 600;"
            "  color: #f2f4f8; background-color: #3a414c; border: none;"
            "}"
            "#tutorialBubble QPushButton:hover { background-color: #464e5b; }"
            f"#tutorialBubble QPushButton#tutPrimary {{ background-color: {ACCENT}; color: white; }}"
            "#tutorialBubble QPushButton#tutPrimary:hover { background-color: #3a7de0; }"
            "#tutorialBubble QPushButton#tutLink {"
            "  background: transparent; color: #9aa4b2; font-weight: 500; padding: 6px 6px;"
            "}"
            "#tutorialBubble QPushButton#tutLink:hover { color: #f2f4f8; }"
        )

        host.installEventFilter(self)
        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Show the pipeline chooser and begin the tutorial."""
        self._mode = "chooser"
        self._highlight = QRect()
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        self._render_chooser()
        self.update()

    def set_steps(self, steps: list[TutorialStep]) -> None:
        self._steps = steps

    def begin_steps(self) -> None:
        self._mode = "steps"
        self._index = 0
        self._show_step()

    # ── Chooser screen ────────────────────────────────────────────────────────

    def _render_chooser(self) -> None:
        self._clear_bubble()
        lay = QVBoxLayout(self._bubble)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)

        logo_pix = logo_pixmap(96, self.devicePixelRatioF())
        if logo_pix is not None:
            logo = QLabel()
            logo.setPixmap(logo_pix)
            logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(logo)
            lay.addSpacing(2)

        title = QLabel("Welcome to MEA-NAP")
        title.setObjectName("tutTitle")
        subtitle = QLabel("Which analysis would you like to run? "
                          "The tutorial will guide you through the settings it needs.")
        subtitle.setObjectName("tutBody")
        subtitle.setWordWrap(True)
        self._body_label = subtitle   # so the intro screen is measured the same way
        lay.addWidget(title)
        lay.addWidget(subtitle)
        lay.addSpacing(4)

        for kind, heading, blurb in (
            ("meanap", "MEA-NAP  ·  Main pipeline",
             "Spike detection → activity → connectivity → network analysis for MEA recordings."),
            ("meastim", "MEA-Stim  ·  Stimulation pipeline",
             "Detect electrical-stimulation artefacts and analyse evoked responses."),
            ("catnap", "CAT-NAP  ·  Imaging pipeline",
             "Analyse two-photon calcium imaging processed with suite2p."),
        ):
            btn = QPushButton(f"{heading}\n{blurb}")
            btn.setObjectName("tutPrimary" if kind == "meanap" else "")
            btn.setStyleSheet("text-align: left; padding: 10px 14px;")
            btn.clicked.connect(lambda _=False, k=kind: self._choose(k))
            lay.addWidget(btn)

        skip = QPushButton("Skip the tour")
        skip.setObjectName("tutLink")
        skip.clicked.connect(self._finish)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(skip)
        lay.addLayout(row)

        self._finalize_bubble(560)

    def _choose(self, kind: str) -> None:
        self.pipeline_chosen.emit(kind)

    # ── Step screens ──────────────────────────────────────────────────────────

    def _show_step(self) -> None:
        if not (0 <= self._index < len(self._steps)):
            self._finish()
            return
        step = self._steps[self._index]

        self._busy = True
        if step.tab_index is not None:
            self._tabs.setCurrentIndex(step.tab_index)
        QApplication.processEvents()

        # Scroll the target into view inside a scrollable tab, then settle.
        target_widget = None
        if step.target is not None:
            resolved = step.target()
            if isinstance(resolved, QWidget):
                target_widget = resolved
        if target_widget is not None:
            self._reveal(target_widget)
            QApplication.processEvents()
        self._busy = False

        self._highlight = self._resolve_highlight(step)
        self._update_mask()  # cut the hole now; the bubble is added once shown
        self._render_step(step)
        self.raise_()
        self.update()

    def _render_step(self, step: TutorialStep) -> None:
        self._clear_bubble()
        lay = QVBoxLayout(self._bubble)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(8)

        title = QLabel(step.title)
        title.setObjectName("tutTitle")
        body = QLabel(step.body)
        body.setObjectName("tutBody")
        body.setWordWrap(True)
        self._body_label = body   # _size_bubble measures this to avoid clipping
        lay.addWidget(title)
        lay.addWidget(body)

        if step.diagram:
            diagram = QLabel(step.diagram)
            diagram.setObjectName("tutDiagram")
            diagram.setTextFormat(Qt.TextFormat.PlainText)
            lay.addWidget(diagram)

        footer = QHBoxLayout()
        count = QLabel(f"{self._index + 1} / {len(self._steps)}")
        count.setObjectName("tutCount")
        footer.addWidget(count)
        footer.addStretch()

        skip = QPushButton("Exit")
        skip.setObjectName("tutLink")
        skip.clicked.connect(self._finish)
        footer.addWidget(skip)

        if self._index > 0:
            back = QPushButton("Back")
            back.clicked.connect(self._back)
            footer.addWidget(back)

        is_last = self._index == len(self._steps) - 1
        nxt = QPushButton("Finish" if is_last else "Next")
        nxt.setObjectName("tutPrimary")
        nxt.clicked.connect(self._finish if is_last else self._next)
        footer.addWidget(nxt)

        lay.addLayout(footer)

        self._finalize_bubble(380)

    def _next(self) -> None:
        self._index += 1
        self._show_step()

    def _back(self) -> None:
        self._index -= 1
        self._show_step()

    def _finish(self) -> None:
        self.hide()
        self._mode = "idle"
        self.finished.emit()

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _reveal(self, w: QWidget) -> None:
        self._unfold(w)
        # The scroll area is not always the tab page itself — a tab can scroll
        # just one of its columns (the CAT-NAP settings do). Walk out from the
        # target to whichever one actually holds it.
        parent = w.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(w, 60, 60)
                return
            parent = parent.parentWidget()

    @staticmethod
    def _unfold(w: QWidget) -> None:
        """Open any collapsed advanced section this target is inside.

        A step pointing at a folded-away setting would cut its hole around
        nothing. Opening the section is also the honest thing to show: the
        tutorial is where someone finds out these settings exist, and where
        they live.
        """
        from meanap.gui.advanced import AdvancedSection

        parent = w
        while parent is not None:
            if isinstance(parent, AdvancedSection):
                parent.set_expanded(True)
            parent = parent.parentWidget()

    def _resolve_highlight(self, step: TutorialStep) -> QRect:
        if step.target is None:
            return QRect()
        t = step.target()
        if t is None:
            return QRect()
        if isinstance(t, QRect):
            g = t
        else:
            if not t.isVisible():
                return QRect()
            g = QRect(t.mapToGlobal(QPoint(0, 0)), t.size())
        return QRect(self.mapFromGlobal(g.topLeft()), g.size())

    def _position_bubble(self) -> None:
        margin = 16
        bw = self._bubble.width()
        bh = self._bubble.height()
        W, H = self.width(), self.height()

        if self._highlight.isNull():
            x = (W - bw) // 2
            y = (H - bh) // 2
        else:
            h = self._highlight
            # Prefer below the highlight, else above, else centred vertically.
            if h.bottom() + 12 + bh + margin <= H:
                y = h.bottom() + 12
            elif h.top() - 12 - bh >= margin:
                y = h.top() - 12 - bh
            else:
                y = (H - bh) // 2
            x = h.left()
            x = max(margin, min(x, W - bw - margin))
            y = max(margin, min(y, H - bh - margin))
        self._bubble.move(x, y)

    def _reposition(self) -> None:
        """Recompute geometry after a resize while a screen is showing."""
        if not self.isVisible():
            return
        self.setGeometry(self._host.rect())
        if self._mode == "steps" and 0 <= self._index < len(self._steps):
            self._highlight = self._resolve_highlight(self._steps[self._index])
        self._position_bubble()
        self._update_mask()
        self.update()

    def _update_mask(self) -> None:
        """Cut a real hole for the highlighted field so clicks reach it, while
        keeping the bubble and scrim solid. Without this the opaque overlay
        would swallow every click."""
        region = QRegion(self.rect())
        if not self._highlight.isNull():
            region = region.subtracted(QRegion(self._highlight))
        if self._bubble.isVisible():
            region = region.united(QRegion(self._bubble.geometry()))
        self.setMask(region)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scrim = QColor(0, 0, 0, 150)
        W, H = self.width(), self.height()

        if self._highlight.isNull():
            p.fillRect(0, 0, W, H, scrim)
            return

        h = self._highlight.adjusted(-6, -6, 6, 6)
        hx = max(0, h.x())
        hy = max(0, h.y())
        hr = min(W, h.x() + h.width())
        hb = min(H, h.y() + h.height())

        # Four bands around the hole (leaves the target fully visible).
        p.fillRect(0, 0, W, hy, scrim)                 # top
        p.fillRect(0, hb, W, H - hb, scrim)            # bottom
        p.fillRect(0, hy, hx, hb - hy, scrim)          # left
        p.fillRect(hr, hy, W - hr, hb - hy, scrim)     # right

        pen = QPen(QColor(ACCENT))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(h, 6, 6)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _finalize_bubble(self, max_width: int) -> None:
        # The stylesheet fonts only take effect after the widget is polished on
        # the next event-loop tick, so the content size isn't known yet. Hide
        # the bubble now and size + place it once, deferred.
        self._bubble.setMaximumWidth(max_width)
        self._bubble.hide()
        QTimer.singleShot(0, self._apply_bubble_geometry)

    def _apply_bubble_geometry(self) -> None:
        if self._mode == "idle":
            return
        lay = self._bubble.layout()
        if lay is not None:
            lay.activate()
        self._size_bubble()
        self._position_bubble()
        self._bubble.show()
        self._bubble.raise_()
        self._update_mask()
        self.update()

    def _size_bubble(self) -> None:
        """Size the bubble to its wrapped text.

        ``adjustSize()`` alone is not enough: the body is a word-wrapping
        QLabel, so its height depends on the width it ends up at, but
        ``sizeHint()`` reports the height the text *would* need at its own
        preferred (unwrapped) width. For a long step that yields a box wide
        enough but too short, clipping the first and last lines. So settle the
        width first, then ask the layout how tall it needs to be at exactly
        that width.
        """
        hint = self._bubble.sizeHint()
        width = min(hint.width(), self._bubble.maximumWidth())
        lay = self._bubble.layout()
        if lay is None:
            self._bubble.resize(width, hint.height())
            return

        height = lay.heightForWidth(width) if lay.hasHeightForWidth() else hint.height()

        # heightForWidth answers for the *contents*, but the stylesheet border
        # sits outside them, so the frame needs those pixels on top — otherwise
        # the last line of the body is cropped by exactly the border width.
        height += 2 * BUBBLE_BORDER

        # The same border also narrows the contents, so a wrapping label can
        # need one more line than the layout assumed when it computed the
        # height above. Add back what that costs. Measuring the labels' live
        # geometry instead would be simpler but is wrong on the first render,
        # when children have no geometry yet and a wrapped label claims it
        # needs many lines in ~50px.
        margins = lay.contentsMargins()
        assumed = max(1, width - margins.left() - margins.right())
        actual = max(1, assumed - 2 * BUBBLE_BORDER)
        for i in range(lay.count()):
            widget = lay.itemAt(i).widget()
            if widget is not None and widget.hasHeightForWidth():
                height += max(0, widget.heightForWidth(actual) - widget.heightForWidth(assumed))

        self._bubble.resize(width, height)
        lay.activate()

    def _clear_bubble(self) -> None:
        # Dropped here rather than left dangling: _drain_layout deletes the
        # label, and touching a deleted QLabel raises.
        self._body_label = None
        old = self._bubble.layout()
        if old is not None:
            self._drain_layout(old)
            # Reparent the stale (now empty) layout so a fresh one installs.
            QWidget().setLayout(old)

    def _drain_layout(self, layout) -> None:
        """Remove and destroy every widget/sub-layout in *layout*.

        ``setParent(None)`` is essential: ``deleteLater`` alone defers the
        destruction to the next event loop, leaving stale widgets painted on
        the bubble in the meantime.
        """
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            sub = item.layout()
            if sub is not None:
                self._drain_layout(sub)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._host and event.type() == QEvent.Type.Resize and not self._busy:
            self._reposition()
        return super().eventFilter(obj, event)
