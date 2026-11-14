"""What a figure's marks *are*, kept beside the axes that drew them.

A saved figure is pixels; a figure shown live still has its artists, but an
artist knows where it is, not what it stands for. A plotter that knows — this
circle is electrode 34, its degree is 5 — records it here, and an interactive
view reads it back to answer "what am I pointing at?".

Purely additive: nothing here draws, so attaching it cannot change a figure,
and a plotter that attaches nothing still gets the viewer's generic read-out of
scatter points and line vertices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["HoverPoints", "attach", "points", "relabel", "set_legend", "legend"]

_ATTR = "_meanap_hover"
_LEGEND = "_meanap_legend"


@dataclass
class HoverPoints:
    """One set of marks on one axes."""

    #: (N, 2) positions, in the axes' data coordinates.
    xy: np.ndarray
    #: One line of description per mark.
    text: list[str]
    #: (N,) radius in data units — pointing anywhere inside a mark counts —
    #: or ``None`` for marks with no data-space extent.
    radius: np.ndarray | None = None
    #: (N,) row of each mark in the arrays the plotter was given, so a caller
    #: that knows names for those rows can add them (see :func:`relabel`).
    index: np.ndarray | None = None
    #: What one mark is called: "electrode", "cell", "recording".
    noun: str = "point"
    names: list[str] = field(default_factory=list)


def attach(ax, xy, text, *, radius=None, index=None, noun: str = "point") -> None:
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    if not len(xy):
        return
    existing = getattr(ax, _ATTR, None) or []
    existing.append(HoverPoints(
        xy, list(text),
        None if radius is None else np.asarray(radius, dtype=float),
        None if index is None else np.asarray(index, dtype=int), noun))
    setattr(ax, _ATTR, existing)


def points(ax) -> list[HoverPoints]:
    return getattr(ax, _ATTR, None) or []


def relabel(ax, names, noun: str) -> None:
    """Name the marks on *ax* from *names*, indexed by each mark's row."""
    for group in points(ax):
        if group.index is None:
            continue
        group.noun = noun
        group.names = [str(names[i]) for i in group.index]


def set_legend(ax, spec: dict) -> None:
    """Record what the legend drawn on *ax* says, as data.

    A plotter draws its legend into the figure, sized for print. A view that
    builds its own legend from native widgets needs the content, not the
    artists: which values the sample marks stand for and how large they are.
    """
    setattr(ax, _LEGEND, spec)


def legend(ax) -> dict | None:
    return getattr(ax, _LEGEND, None)

