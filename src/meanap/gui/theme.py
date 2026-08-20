"""Theme helpers for the MEA-NAP GUI."""

from __future__ import annotations

import qdarktheme
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

# Accent colour used throughout the UI
ACCENT = "#4f8ef7"

# Extra QSS layered on top of qdarktheme
_EXTRA_QSS = f"""
/* ── Toolbar ─────────────────────────────────────────────────────────────── */
QToolBar {{
    spacing: 6px;
    padding: 4px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}}
QToolBar QToolButton {{
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 500;
}}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
/* Drawn as one segmented control — a joined bar divided into sections — so the
   tabs read as things you press rather than as words with an underline.
   qdarktheme styles QTabBar::tab:top and QTabBar::tab:selected:enabled, so
   these must match that specificity to win; a plain QTabBar::tab:selected is
   silently outranked and only some of its properties land.

   Height is load-bearing. padding + margin together set the tab height, which
   is also the height Qt hands the corner widget — so it is what the logo
   beside the tabs has to live in, and 13 + 13 is what clears
   branding.CORNER_LOGO_HEIGHT. The margin is the part that does not get
   painted, which is how the bar sits as a band inside a tall strip rather
   than filling it. test_gui_toolbar fails if this stops adding up. */
QTabBar::tab {{
    font-weight: 500;
    font-size: 12px;
    min-width: 90px;
}}
QTabBar::tab:top {{
    padding: 13px 14px;
    margin: 13px 0 13px 0;
    background-color: rgba(0, 0, 0, 0.035);
    border: 1px solid rgba(0, 0, 0, 0.18);
    border-left-width: 0;
    border-radius: 0;
}}
/* Only the outer ends are rounded, so the sections read as one control. */
QTabBar::tab:top:first {{
    border-left-width: 1px;
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}}
QTabBar::tab:top:last {{
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}}
QTabBar::tab:top:only-one {{
    border-left-width: 1px;
    border-radius: 8px;
}}
QTabBar::tab:top:hover {{
    background-color: rgba(0, 0, 0, 0.075);
}}
QTabBar::tab:selected:enabled {{
    background-color: #ffffff;
    color: {ACCENT};
    font-weight: 600;
}}

/* ── GroupBox ────────────────────────────────────────────────────────────── */
QGroupBox {{
    font-weight: 600;
    font-size: 12px;
    margin-top: 14px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    letter-spacing: 0.3px;
}}

/* ── Primary action button (Run pipeline) ────────────────────────────────── */
QPushButton#primary {{
    background-color: {ACCENT};
    color: white;
    font-weight: 700;
    font-size: 13px;
    border-radius: 8px;
    padding: 8px 20px;
    border: none;
}}
QPushButton#primary:hover {{
    background-color: #3a7de0;
}}
QPushButton#primary:disabled {{
    background-color: rgba(79, 142, 247, 0.35);
    color: rgba(255, 255, 255, 0.4);
}}

/* ── Destructive / stop button ───────────────────────────────────────────── */
QPushButton#danger {{
    background-color: #e05c5c;
    color: white;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 20px;
    border: none;
}}
QPushButton#danger:hover {{
    background-color: #c94b4b;
}}
QPushButton#danger:disabled {{
    background-color: rgba(224, 92, 92, 0.35);
    color: rgba(255, 255, 255, 0.4);
}}

/* ── Scan / denoise buttons ──────────────────────────────────────────────── */
QPushButton#secondary {{
    font-weight: 600;
    border-radius: 6px;
    padding: 5px 14px;
}}

/* ── Status log ─────────────────────────────────────────────────────────── */
QTextEdit#log {{
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    font-size: 11px;
    border-radius: 6px;
}}

/* ── Info labels in CAT-NAP panel ───────────────────────────────────────── */
QLabel#info-value {{
    font-weight: 600;
}}

/* ── Splitter handle ─────────────────────────────────────────────────────── */
QSplitter::handle {{
    width: 2px;
    background: rgba(128, 128, 128, 0.2);
}}
"""


def apply(app: QApplication, theme: str = "light") -> None:
    """Apply qdarktheme + custom overrides to *app*.

    Light, and only light. A dark variant existed behind a toolbar toggle, but
    the figures the window is mostly showing are drawn on white, so half the
    screen stayed light whichever way it was set. The parameter is kept so a
    dark build is a one-line change rather than a revert.
    """
    qdarktheme.enable_hi_dpi()
    qdarktheme.setup_theme(
        theme,
        corner_shape="rounded",
        custom_colors={"primary": ACCENT},
        additional_qss=_EXTRA_QSS,
    )

    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
