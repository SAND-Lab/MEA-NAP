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
QTabBar::tab {{
    padding: 7px 18px;
    font-weight: 500;
    font-size: 12px;
    min-width: 90px;
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


def apply(app: QApplication, theme: str = "auto") -> None:
    """Apply qdarktheme + custom overrides to *app*."""
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


def toggle(current: str) -> str:
    """Return the next theme name."""
    return "light" if current == "dark" else "dark"


def reapply(theme: str) -> None:
    """Re-apply qdarktheme after a toggle (call without recreating QApplication)."""
    qdarktheme.setup_theme(
        theme,
        corner_shape="rounded",
        custom_colors={"primary": ACCENT},
        additional_qss=_EXTRA_QSS,
    )
