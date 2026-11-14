"""Shared look for the settings-card illustrations.

Each module beside this one draws the pictures for one tab's cards and is run
by ``make_setting_figures.py``. Pictures go to
``src/meanap/gui/assets/settings`` and are shown about 460 px wide in a card,
so they are drawn small, with large-enough text, and saved at 2x.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "src" / "meanap" / "gui" / "assets" / "settings"

#: Card-width figure, in inches at 100 dpi (saved at 200 dpi).
WIDE = (4.6, 2.4)
TALL = (4.6, 3.4)

INK = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_2 = "#dc2626"
ACCENT_3 = "#059669"
ACCENT_4 = "#d97706"
SOFT = "#dbeafe"
PALETTE = [ACCENT, ACCENT_2, ACCENT_3, ACCENT_4, "#7c3aed"]


def setup() -> None:
    plt.rcParams.update({
        "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
        "savefig.pad_inches": 0.04, "lines.linewidth": 1.2,
    })


def figure(size=WIDE, **kwargs):
    setup()
    return plt.subplots(figsize=size, **kwargs)


def save(fig, name: str) -> Path:
    """Write *fig* as ``<name>.png`` in the assets folder and close it."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path
