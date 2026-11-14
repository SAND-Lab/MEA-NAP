"""A small vocabulary for plots that are not one of the pipeline's fixed figures.

The step-5 statistics figures are many and varied — heatmaps, trajectories,
dot plots, bars — so rather than a painter per figure they are written in
these terms: a :class:`Chart` is panels on a grid, each panel holds marks,
and :class:`meanap.native.chart_paint.ChartPainter` draws any of them.

Everything here is plain data. Colours are ``(r, g, b, a)`` in 0–1 (build
them with :func:`rgba`); sizes of text and lines are in points, as matplotlib
gives them, so a figure keeps the proportions it was designed with; positions
are in data units unless a mark says otherwise.

Any mark can say what each of its parts is (``hover``), for a view to show
when it is pointed at, and which series it belongs to (``key``) — pointing at
or pinning one series fades the marks of every other series, in every panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "rgba", "Chart", "Panel", "Legend", "LegendItem", "ColourBar",
    "Line", "Band", "Points", "Bars", "ErrorBars", "Rule", "Span", "Text",
    "Cells", "Segments", "Polygon", "Labels",
]

#: The style's ink and its quieter grey, as ``(r, g, b, a)``.
INK = (0x22 / 255, 0x22 / 255, 0x22 / 255, 1.0)
MUTED = (0x8a / 255, 0x8a / 255, 0x8a / 255, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
NONE = (0.0, 0.0, 0.0, 0.0)


def rgba(colour, alpha: float | None = None) -> tuple[float, float, float, float]:
    """Any matplotlib colour (name, hex, tuple, "none") as ``(r, g, b, a)``."""
    from matplotlib import colors

    if colour is None or (isinstance(colour, str) and colour.lower() == "none"):
        return NONE
    r, g, b, a = colors.to_rgba(colour)
    return (float(r), float(g), float(b), float(a if alpha is None else alpha))


def _array(values) -> np.ndarray:
    return np.asarray(values, dtype=float).ravel()


def _texts(hover, n: int) -> list[str] | None:
    if hover is None:
        return None
    hover = list(hover)
    return hover if len(hover) == n else None


# ── marks ─────────────────────────────────────────────────────────────────────


@dataclass
class Line:
    """A polyline through points, optionally with a marker at each.

    NaN breaks the line, as in matplotlib.
    """

    x: np.ndarray
    y: np.ndarray
    colour: tuple = INK
    width: float = 1.25                 # points
    dash: str = "-"                     # "-", "--", ":"
    marker: str = ""                    # "", "o"
    marker_size: float = 5.0            # diameter, points
    #: Fill of the markers; ``None`` fills them with the line's colour.
    marker_fill: tuple | None = None
    marker_edge: tuple | None = None
    marker_edge_width: float = 0.0
    label: str = ""
    key: str | None = None
    hover: list[str] | None = None
    z: float = 2.0

    def __post_init__(self):
        self.x, self.y = _array(self.x), _array(self.y)
        self.hover = _texts(self.hover, len(self.x))


@dataclass
class Band:
    """The area between two curves over the same x (``fill_between``)."""

    x: np.ndarray
    low: np.ndarray
    high: np.ndarray
    colour: tuple = INK
    key: str | None = None
    #: Fill along y instead: ``x`` is then the y values and the band runs in x.
    vertical: bool = False
    edge: tuple | None = None
    edge_width: float = 0.0
    z: float = 1.0

    def __post_init__(self):
        self.x, self.low, self.high = _array(self.x), _array(self.low), _array(self.high)


@dataclass
class Points:
    """Scattered markers. Colours and sizes may be one for all or one per point."""

    x: np.ndarray
    y: np.ndarray
    fill: object = INK                  # (r,g,b,a) or a list of them
    edge: object = NONE
    edge_width: float = 0.0             # points
    size: object = 5.0                  # diameter in points, or a list
    marker: str = "o"                   # "o", "|", "_"
    label: str = ""
    key: object = None                  # a str for all, or a list of str
    hover: list[str] | None = None
    z: float = 3.0

    def __post_init__(self):
        self.x, self.y = _array(self.x), _array(self.y)
        self.hover = _texts(self.hover, len(self.x))

    def at(self, value, i: int):
        return value[i] if isinstance(value, list) else value

    def key_of(self, i: int):
        return self.key[i] if isinstance(self.key, list) else self.key


@dataclass
class Bars:
    """Bars from ``base`` to ``base + length`` at each position."""

    pos: np.ndarray
    length: np.ndarray
    width: float = 0.8                  # in data units across the bars
    base: object = 0.0
    colour: object = INK                # one, or a list
    horizontal: bool = False
    #: An outline, for bars stacked in colours close enough to run together.
    edge: tuple = NONE
    edge_width: float = 0.0             # points
    label: str = ""
    key: object = None
    hover: list[str] | None = None
    z: float = 2.0

    def __post_init__(self):
        self.pos, self.length = _array(self.pos), _array(self.length)
        self.base = _array(self.base) if np.ndim(self.base) else \
            np.full(len(self.pos), float(self.base))
        self.hover = _texts(self.hover, len(self.pos))


@dataclass
class ErrorBars:
    """Error bars: ``x ± xerr`` and/or ``y ± yerr``. An error may be one row
    (the same both ways) or two, below and above, as matplotlib takes them."""

    x: np.ndarray
    y: np.ndarray
    xerr: np.ndarray | None = None
    yerr: np.ndarray | None = None
    colour: tuple = MUTED
    width: float = 1.0
    cap: float = 0.0                    # cap length, points
    key: str | None = None
    z: float = 1.5

    def __post_init__(self):
        self.x, self.y = _array(self.x), _array(self.y)
        n = len(self.x)

        def shaped(err):
            if err is None:
                return None
            err = np.asarray(err, dtype=float)
            if err.ndim == 2 and err.shape == (2, n):
                return err
            return np.broadcast_to(err.ravel(), (n,)) if err.size in (1, n) else err.ravel()

        self.xerr, self.yerr = shaped(self.xerr), shaped(self.yerr)

    def ends(self, axis: str) -> tuple[np.ndarray, np.ndarray] | None:
        """The low and high end of each bar along *axis* ("x" or "y"), or ``None``."""
        centre, err = (self.x, self.xerr) if axis == "x" else (self.y, self.yerr)
        if err is None:
            return None
        below, above = (err[0], err[1]) if err.ndim == 2 else (err, err)
        return centre - below, centre + above


@dataclass
class Rule:
    """A horizontal (``axis="y"``) or vertical (``axis="x"``) line at ``value``.

    ``extent`` limits it to a stretch of the other axis, in data units.
    """

    value: float
    axis: str = "y"
    colour: tuple = MUTED
    width: float = 1.0
    dash: str = "-"
    extent: tuple | None = None
    key: str | None = None
    z: float = 0.5


@dataclass
class Span:
    """A shaded stretch ``low``–``high`` of one axis, across the whole panel."""

    low: float
    high: float
    axis: str = "y"
    colour: tuple = (0.6, 0.6, 0.6, 0.18)
    z: float = 0.2


@dataclass
class Text:
    """Text at a place. ``coords`` is "data", "axes" (0–1 of the panel), or
    "blend": x as a fraction of the panel and y in data units."""

    x: float
    y: float
    text: str
    colour: tuple = INK
    size: float = 8.0
    ha: str = "center"                  # left, center, right
    va: str = "center"                  # top, center, bottom
    bold: bool = False
    coords: str = "data"
    offset: tuple = (0.0, 0.0)          # points, x right and y up
    z: float = 4.0
    hover: str | None = None


@dataclass
class Cells:
    """A matrix drawn as coloured cells; row ``i`` at ``y = i``, column ``j`` at ``x = j``."""

    values: np.ndarray
    cmap: str = "RdBu_r"
    low: float = -1.0
    high: float = 1.0
    #: Text on each cell (``""`` for none), and its colour.
    text: list | None = None
    text_colour: list | None = None
    text_size: float = 7.0
    text_bold: bool = False
    #: Rows of strings, or a function of ``(row, column)`` giving the string —
    #: for a matrix too large to describe every cell up front.
    hover: object = None
    z: float = 1.0
    #: The outer edges of the first and last column (row) in data units, for a
    #: matrix over something other than its indices — time bins, say. ``None``
    #: puts cell ``k`` at ``k``.
    x: tuple | None = None
    y: tuple | None = None

    def __post_init__(self):
        self.values = np.asarray(self.values, dtype=float)

    def box(self) -> tuple[float, float, float, float]:
        """(x0, x1, y0, y1): the outer edges of the first and last column and row."""
        rows, cols = self.values.shape
        x0, x1 = self.x if self.x is not None else (-0.5, cols - 0.5)
        y0, y1 = self.y if self.y is not None else (-0.5, rows - 0.5)
        return float(x0), float(x1), float(y0), float(y1)

    def index(self, x: float, y: float) -> tuple[int, int] | None:
        """The (row, column) of the cell holding data point (x, y), if any."""
        rows, cols = self.values.shape
        x0, x1, y0, y1 = self.box()
        if x1 == x0 or y1 == y0:
            return None
        j = int(np.floor((x - x0) / (x1 - x0) * cols))
        i = int(np.floor((y - y0) / (y1 - y0) * rows))
        return (i, j) if 0 <= i < rows and 0 <= j < cols else None

    def centre(self, i: int, j: int) -> tuple[float, float]:
        rows, cols = self.values.shape
        x0, x1, y0, y1 = self.box()
        return x0 + (j + 0.5) * (x1 - x0) / cols, y0 + (i + 0.5) * (y1 - y0) / rows


@dataclass
class Segments:
    """Separate straight lines, each ``(x0, y0, x1, y1)``."""

    lines: np.ndarray
    colour: object = MUTED              # one, or a list
    width: float = 1.0
    dash: str = "-"
    key: object = None
    z: float = 1.0

    def __post_init__(self):
        self.lines = np.asarray(self.lines, dtype=float).reshape(-1, 4)


@dataclass
class Polygon:
    """A closed shape through points (a violin's body, say)."""

    x: np.ndarray
    y: np.ndarray
    fill: tuple = INK
    edge: tuple = NONE
    edge_width: float = 0.0
    dash: str = "-"
    key: str | None = None
    hover: str | None = None
    z: float = 1.0

    def __post_init__(self):
        self.x, self.y = _array(self.x), _array(self.y)


@dataclass
class Labels:
    """Short labels for points, nudged apart so none sits on another.

    Each label starts just above its point; labels that would overlap are
    pushed sideways, keeping the left-to-right order of their points, and off
    any point they cover. A label that ends up away from its point gets a
    thin leader to it. The nudging is done where the figure is drawn, at the
    size it is drawn, so it holds at any zoom.
    """

    x: np.ndarray
    y: np.ndarray
    texts: list[str]
    colours: list                       # one (r,g,b,a) per label
    size: float = 6.5
    bold: bool = True
    #: Radius of the points being labelled, in points.
    dot: float = 4.5
    keys: list | None = None
    z: float = 4.0

    def __post_init__(self):
        self.x, self.y = _array(self.x), _array(self.y)


# ── around the marks ──────────────────────────────────────────────────────────


@dataclass
class LegendItem:
    label: str
    colour: tuple = INK
    #: line, point, box, open (an unfilled point), tick (a short upright
    #: stroke), hline (a short thick bar)
    kind: str = "line"
    dash: str = "-"
    marker: bool = False                # a marker on a line swatch
    edge: tuple | None = None
    size: float = 5.0
    key: str | None = None


@dataclass
class Legend:
    items: list[LegendItem]
    title: str = ""
    #: Inside a panel: "upper left", "upper right", "lower left", "lower right",
    #: "center right"; "right" puts it outside, beside the panel. For the
    #: figure: "bottom" or "right".
    loc: str = "upper right"
    columns: int = 1
    size: float = 7.0
    swatch: float = 1.2                 # length of a line swatch, in font heights × 2


@dataclass
class ColourBar:
    cmap: str
    low: float
    high: float
    label: str = ""
    ticks: list | None = None
    #: Fraction of the panels' height it may span, centred on them (or from
    #: their top, with ``top``).
    shrink: float = 1.0
    top: bool = False
    #: Length to thickness (matplotlib's ``aspect``), and the share of the
    #: figure's width it may take (``fraction``): it is ``aspect × fraction``
    #: of the width long, unless that is taller than the panels.
    aspect: float = 20.0
    fraction: float = 0.15
    tick_size: float = 7.0


@dataclass
class Panel:
    """One plot area and everything in it.

    ``cell`` is ``(row, column)`` on the chart's grid, ``span`` how many rows
    and columns it covers.
    """

    cell: tuple[int, int] = (0, 0)
    span: tuple[int, int] = (1, 1)
    marks: list = field(default_factory=list)
    title: str = ""
    title_size: float = 9.0
    title_colour: tuple = INK
    xlabel: str = ""
    ylabel: str = ""
    label_size: float = 8.0
    xlim: tuple | None = None
    ylim: tuple | None = None
    #: ``[(value, label)]`` or ``[(value, label, colour)]``; ``None`` picks round
    #: numbers; ``[]`` shows none.
    xticks: list | None = None
    yticks: list | None = None
    tick_size: float = 7.0
    #: Whether the tick labels are written; the gridlines stay either way (a
    #: panel that shares an axis with its neighbour, as matplotlib's subplots).
    xlabels: bool = True
    ylabels: bool = True
    xtick_rotation: float = 0.0
    #: Gridlines along "y" (horizontal lines at the y ticks), "x", or "".
    grid: str = "y"
    ylog: bool = False
    #: The first row at the top: a matrix, or a ranked list.
    y_down: bool = False
    #: Equal scales on x and y.
    equal: bool = False
    legend: Legend | None = None
    #: A colour bar of the panel's own, beside it (matplotlib's
    #: ``fig.colorbar(im, ax=ax)``): ``fraction`` of the panel's width, ``aspect``
    #: long to thick, never taller than the panel.
    colour_bar: ColourBar | None = None
    #: No axes, ticks or grid: a key, or a cartoon, drawn in data units.
    bare: bool = False
    #: Whether a view may zoom and pan it along x and along y.
    zoom: tuple[bool, bool] = (True, True)
    #: Panels with the same name follow each other's x (or y) range.
    sharex: str | None = None
    sharey: str | None = None
    #: Text across the middle when the panel has no data.
    empty: str = ""
    #: Drawn over the panel in the same cell, with its y axis on the right
    #: (matplotlib's ``twinx``): a second quantity against the same x. It has
    #: no grid, x axis or title of its own; give both panels the same
    #: ``sharex`` so they move together.
    twin: bool = False
    #: A thin box around the plot area in this colour (``None``: none).
    frame: tuple | None = None


@dataclass
class Chart:
    panels: list[Panel]
    #: The size, in inches as matplotlib's ``figsize``.
    size: tuple[float, float] = (6.4, 4.8)
    grid: tuple[int, int] = (1, 1)
    #: Relative heights of the rows and widths of the columns.
    heights: list | None = None
    widths: list | None = None
    title: str = ""
    title_size: float = 11.0
    title_colour: tuple = INK
    legend: Legend | None = None
    colour_bar: ColourBar | None = None
    #: Small print at the foot of the figure; lines are wrapped to fit.
    note: str = ""
    note_size: float = 7.5
    note_align: str = "left"            # or "right"
    #: Space between panels, in points.
    gap: tuple[float, float] = (14.0, 14.0)
