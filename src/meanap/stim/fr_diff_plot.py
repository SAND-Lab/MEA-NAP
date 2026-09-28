"""The firing-rate-change figure: one panel per slice, change per channel.

Port of the lab viewer ``fr_diff_viewer.html`` to matplotlib, so the pipeline's
saved figure and the GUI's interactive view are drawn by the same code. Each
panel plots the change from baseline (y) against channel (x), one colour per
stimulation pattern, with the dots jittered sideways so a channel's patterns do
not overprint.

Works on a bare :class:`~matplotlib.figure.Figure` and never touches pyplot,
so the GUI can draw straight onto its canvas. :func:`draw_fr_diff` returns what
it drew, point by point, for the GUI's hover read-out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from .fr_diff import Diff, FrDiffResult, Panel, multi_run, panel_title

__all__ = [
    "PALETTE", "SAVE_DPI", "MEASURES", "DrawnPoints", "stim_colors", "default_columns",
    "figure_size", "draw_fr_diff", "save_fr_diff_figure", "y_label",
]

#: Pattern colours, in pattern order (the lab scripts' categorical palette).
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
           "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
EXCLUDED_COLOR = "#e34948"     # excluded channel numbers on the x axis, nothing else
GRID_COLOR = "#e4e3df"
INK_COLOR = "#52514e"
TITLE_COLOR = "#0b0b0b"
ZERO_LINE_COLOR = "#bdbcb8"    # the 0 reference line inside each panel
SAVE_DPI = 300

MEASURES = ("pct", "log2")

# Panel geometry in inches, from the viewer's pixels at 100 px/in. Rows have a
# fixed height rather than sharing the figure's, so a tall grid keeps readable
# panels and scrolls instead of squeezing every row onto one screen.
ROW_H = 3.0
ROW_GAP = 0.64                 # room beneath a row for its tick labels
SINGLE_H = 4.6
MARGIN_T = 0.64                # the legend, and the top row's panel titles
MARGIN_B = 0.56
MARGIN_L = 0.88
MARGIN_R = 0.2
CAPTION_H = 0.3

JITTER = 0.18                  # half-width of the sideways jitter, in channel slots


@dataclass
class DrawnPoints:
    """One scatter the figure drew, and the readings behind its points, in order."""

    collection: object         # matplotlib PathCollection
    panel: Panel
    diffs: list[Diff]
    silent: bool               # drawn at the panel's foot: 0 Hz under stim, log2 view


def stim_colors(result: FrDiffResult) -> dict[str, str]:
    return {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(result.config.stims)}


def default_columns(n_panels: int) -> int:
    """Columns for a grid of ``n_panels`` on a wide window, as the viewer lays them out."""
    return 1 if n_panels <= 1 else (2 if n_panels <= 6 else 3)


def figure_size(n_panels: int, ncols: int, width: float, caption: bool = False
                ) -> tuple[float, float]:
    """(width, height) in inches for ``n_panels`` laid out in ``ncols`` columns."""
    if n_panels <= 1:
        height = SINGLE_H
    else:
        rows = math.ceil(n_panels / ncols)
        height = MARGIN_T + rows * ROW_H + (rows - 1) * ROW_GAP + MARGIN_B
    return width, height + (CAPTION_H if caption else 0.0)


def y_label(measure: str, baseline: str) -> str:
    # Two lines for log2: on one it is taller than a grid row and runs into
    # the label of the panel beneath.
    if measure == "log2":
        return f"Firing rate change from baseline\n(log₂ stim / {baseline})"
    return "Firing rate difference from baseline (%)"


def _y(d: Diff, log: bool) -> float | None:
    return d.log2 if log else d.pct


def _y_range(values: list[float], log: bool, floor: bool) -> tuple[float, float]:
    """The panel's y limits: 0 always inside, padded, with a band below for -inf."""
    if values:
        lo, hi = min(0.0, min(values)), max(0.0, max(values))
    else:
        lo, hi = (-1.0, 1.0) if log else (-100.0, 100.0)
    pad = 0.08 * ((hi - lo) or 1.0)
    return lo - pad * (2.5 if floor else 1.0), hi + pad


def _ticks(channels: list[int], excluded: set[int], budget: int) -> list[int]:
    """The channels that keep a tick label.

    Ticks thin out so the labels stay readable, but an excluded channel always
    keeps its tick: its red number is the only thing marking it, since it has
    no point to plot. The excluded ticks go in first and a regular tick yields
    to one it would collide with, so a red number is never overprinted.
    """
    step = max(1, math.ceil(len(channels) / budget))
    keep = set(excluded)
    clearance = max(1, step // 2) if step > 1 else 0
    excluded_at = [j for j, c in enumerate(channels) if c in excluded]
    for j, c in enumerate(channels):
        if c in keep or j % step:
            continue
        if any(abs(g - j) <= clearance for g in excluded_at):
            continue
        keep.add(c)
    return [c for c in channels if c in keep]


def _style(ax) -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID_COLOR)
    ax.tick_params(colors=INK_COLOR, which="both")
    ax.yaxis.grid(True, color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)


def draw_fr_diff(
    fig: Figure,
    result: FrDiffResult,
    *,
    measure: str = "pct",
    same_y: bool = True,
    selected: str | None = None,
    hidden: frozenset[str] | set[str] = frozenset(),
    ncols: int | None = None,
    caption: bool = False,
) -> list[DrawnPoints]:
    """Draw ``result`` onto ``fig``, clearing it first.

    ``selected`` is a panel id (``R250929/CT1A``) to show on its own, or None
    for the grid of every slice. ``hidden`` names patterns left undrawn; the y
    axes are still scaled to them, so hiding a pattern never rescales the view.
    ``ncols`` defaults to :func:`default_columns`. ``caption`` adds a line at
    the foot explaining the red channel numbers and the triangles, for a figure
    saved without the GUI around it to say so.

    The figure's size is the caller's: :func:`figure_size` gives the one the
    layout is designed for.
    """
    if measure not in MEASURES:
        raise ValueError(f"measure must be one of {MEASURES}, not {measure!r}")
    fig.clear()
    fig.patch.set_facecolor("white")
    log = measure == "log2"
    panels = [p for p in result.panels if selected in (None, p.id)]
    n = len(panels)
    if not n:
        fig.text(0.5, 0.5, "No slice has a baseline and its stimulation patterns to "
                 "compare.", ha="center", va="center", color=INK_COLOR)
        return []

    single = n == 1
    ncols = 1 if single else max(1, min(ncols or default_columns(n), n))
    nrows = math.ceil(n / ncols)
    width, height = fig.get_size_inches()
    cap = CAPTION_H if caption else 0.0
    top = 1 - MARGIN_T / height
    bottom = (MARGIN_B + cap) / height
    col_gap = 0.07 if ncols <= 2 else 0.05            # fraction of the width, as the viewer
    panel_w = (1 - col_gap * (ncols - 1)) / ncols
    grid = fig.add_gridspec(
        nrows, ncols, left=MARGIN_L / width, right=1 - MARGIN_R / width,
        top=top, bottom=bottom,
        hspace=0.0 if single else ROW_GAP / ROW_H, wspace=col_gap / panel_w)

    colors = stim_colors(result)
    multi = multi_run(result.panels)
    all_points = [d for p in panels for d in p.diffs]
    finite = lambda ds: [v for v in (_y(d, log) for d in ds) if v is not None]  # noqa: E731
    any_silent = lambda ds: log and any(d.log2 is None for d in ds)            # noqa: E731
    shared = _y_range(finite(all_points), log, any_silent(all_points)) if same_y else None
    fmt = FuncFormatter(lambda v, _: f"{v:g}" if log else f"{v:g}%")
    tick_size = 10 if single else 9
    budget = 10**9 if single else (16 if ncols <= 2 else 10)

    drawn: list[DrawnPoints] = []
    shown_stims: set[str] = set()
    silent_shown = False
    excluded_shown = False
    for i, panel in enumerate(panels):
        row, col = divmod(i, ncols)
        ax = fig.add_subplot(grid[row, col])
        _style(ax)
        channels = panel.channels
        pos = {c: j for j, c in enumerate(channels)}
        lo, hi = shared or _y_range(finite(panel.diffs), log, any_silent(panel.diffs))
        floor_y = lo + 0.04 * (hi - lo)
        ax.axhline(0, color=ZERO_LINE_COLOR, linewidth=1, zorder=1)

        # Re-seeded per panel so a slice's dots land in the same places in the
        # grid and in the single-slice view; drawn for every point in both
        # measures so a dot keeps its x when the measure is switched.
        rng = np.random.default_rng(0)
        for token in result.config.stims:
            pts = [d for d in panel.diffs if d.stim == token]
            if not pts:
                continue
            jitter = rng.uniform(-JITTER, JITTER, len(pts))
            if token in hidden:
                continue
            shown_stims.add(token)
            x = np.array([pos[d.channel] for d in pts]) + jitter
            on_axis = [k for k, d in enumerate(pts) if _y(d, log) is not None]
            silent = [k for k, d in enumerate(pts) if _y(d, log) is None]
            if on_axis:
                sc = ax.scatter(x[on_axis], [_y(pts[k], log) for k in on_axis], s=22,
                                color=colors[token], alpha=0.8, linewidths=0, zorder=3)
                drawn.append(DrawnPoints(sc, panel, [pts[k] for k in on_axis], False))
            if silent:
                silent_shown = True
                sc = ax.scatter(x[silent], [floor_y] * len(silent), s=30, marker="v",
                                color=colors[token], alpha=0.8, linewidths=0, zorder=3)
                drawn.append(DrawnPoints(sc, panel, [pts[k] for k in silent], True))

        excluded = set(panel.unplotted)
        excluded_shown |= bool(excluded)
        shown = _ticks(channels, excluded, budget)
        ax.set_xticks([pos[c] for c in shown])
        ax.set_xticklabels([str(c) for c in shown], fontsize=tick_size,
                           rotation=90 if len(shown) > 24 else 0)
        for label, c in zip(ax.get_xticklabels(), shown):
            if c in excluded:
                label.set_color(EXCLUDED_COLOR)
        ax.set_xlim(-0.7, len(channels) - 0.3)
        ax.set_ylim(lo, hi)
        ax.yaxis.set_major_formatter(fmt)
        ax.tick_params(axis="y", labelsize=tick_size)

        if i + ncols >= n:
            ax.set_xlabel("Channel", fontsize=11, color=INK_COLOR)
        if col == 0:
            ax.set_ylabel(y_label(measure, result.config.baseline), fontsize=11,
                          color=INK_COLOR)
        # With one panel the slice is already named wherever it was chosen, so
        # a title on top of it is noise.
        if not single:
            ax.set_title(panel_title(panel, multi), loc="left", fontsize=12,
                         color=TITLE_COLOR, pad=6)

    handles = [Line2D([], [], linestyle="", marker="o", markersize=6, alpha=0.8,
                      markerfacecolor=colors[t], markeredgewidth=0,
                      label=result.config.label(t))
               for t in result.config.stims if t in shown_stims]
    if handles:
        fig.legend(handles=handles, loc="lower center", ncols=len(handles),
                   bbox_to_anchor=(0.5, top + 0.12 / height), frameon=False, fontsize=11,
                   handletextpad=0.3, columnspacing=1.4)

    if caption:
        parts = []
        if excluded_shown:
            parts.append("Channel numbers in red were excluded (grounded, stimulating, "
                         "or 0 Hz at baseline).")
        if silent_shown:
            parts.append("▼ at a panel's foot: 0 Hz under that pattern "
                         "(log₂ = −∞).")
        if parts:
            fig.text(MARGIN_L / width, 0.12 / height, "   ".join(parts), fontsize=9,
                     color=INK_COLOR, ha="left", va="bottom")
    return drawn


def save_fr_diff_figure(result: FrDiffResult, out_path: Path | str, *,
                        measure: str = "pct", dpi: int = SAVE_DPI) -> Path:
    """Save every slice's panel, grid-laid, to ``out_path`` (a .png/.svg/.pdf)."""
    n = len(result.panels)
    ncols = default_columns(n)
    fig = Figure(figsize=figure_size(n, ncols, 6.5 if ncols == 1 else 5.5 * ncols + 1.2,
                                     caption=True))
    draw_fr_diff(fig, result, measure=measure, ncols=ncols, caption=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor="white")
    return out_path
