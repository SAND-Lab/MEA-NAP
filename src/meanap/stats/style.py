"""The look of the step-5 figures: sciplotlib's ``tim-modern`` style.

Frameless — no spines and no tick marks, with soft horizontal gridlines
carrying the y-scale — soft near-black ink, a sans-serif face at 7-9 pt, and
flat, edgeless markers.

The settings are copied here rather than loaded from sciplotlib because the
stylesheet is newer than the sciplotlib release MEA-NAP depends on. Only the
parts that say how a figure *looks* are taken: figure sizes, resolution and
layout stay with each figure and with :mod:`meanap.pipeline.figure_output`.
"""

from __future__ import annotations

from contextlib import contextmanager

import matplotlib.pyplot as plt
from cycler import cycler

__all__ = ["STATS_STYLE", "stats_style"]

#: ``tim-modern.mplstyle`` (sciplotlib 0.0.9), less figure size, dpi and layout.
STATS_STYLE = {
    "lines.linewidth": 1.25,
    "lines.markersize": 5,
    "lines.markeredgewidth": 0,
    "lines.solid_capstyle": "round",
    "lines.dash_capstyle": "round",
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "TeX Gyre Heros", "DejaVu Sans"],
    "font.size": 8,
    "text.color": "#222222",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "axes.facecolor": "white",
    "axes.edgecolor": "#222222",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.grid.which": "major",
    "axes.titlesize": 9,
    "axes.titleweight": "normal",
    "axes.titlepad": 8,
    "axes.labelsize": 8,
    "axes.labelcolor": "#222222",
    "axes.labelpad": 4,
    "axes.spines.left": False,
    "axes.spines.bottom": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.axisbelow": True,
    "axes.prop_cycle": cycler(color=["#2a78d6", "#1baf7a", "#eda100", "#008300",
                                     "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]),
    "xtick.color": "#222222",
    "ytick.color": "#222222",
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "xtick.major.size": 0,
    "ytick.major.size": 0,
    "xtick.minor.size": 0,
    "ytick.minor.size": 0,
    "xtick.major.width": 0,
    "ytick.major.width": 0,
    "xtick.major.pad": 4,
    "ytick.major.pad": 4,
    "legend.frameon": False,
    "legend.fontsize": 7,
    "legend.handlelength": 1.2,
    "legend.handletextpad": 0.5,
    "legend.labelspacing": 0.3,
    "legend.borderpad": 0.3,
    "legend.columnspacing": 1.0,
    "grid.color": "#c8c8c8",
    "grid.linestyle": "-",
    "grid.linewidth": 0.7,
    "grid.alpha": 1.0,
    "figure.facecolor": "white",
    "figure.edgecolor": "white",
    "savefig.facecolor": "white",
    "scatter.marker": "o",
    "scatter.edgecolors": "none",
}


@contextmanager
def stats_style():
    """Draw the figures made inside this block in the step-5 style."""
    with plt.style.context(STATS_STYLE):
        yield
