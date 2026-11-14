"""The numbers of the figures that compare recordings, with no drawing in them.

* :class:`ComparisonScene` — half-violins of one metric, a panel per group (or
  per age), a violin per age (or group) in each (``plotHalfViolinByX.m``);
  optionally split again by a third factor such as cell type.
* :class:`LineScene` — mean ± SEM against something ordered (the STTC lag, the
  age), a line per series, a panel per group (``plotGraphMetricsByLag.m``,
  ``plotNetMetNodeCartography.m``).

Each point of a comparison carries the recording it came from, so a view can
say whose it is and mark that recording's other points.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from meanap.native.scene import violin_panel

__all__ = ["ComparisonViolin", "ComparisonPanel", "ComparisonScene", "comparison_scene",
           "LineSeries", "LinePanel", "LineScene", "rgb"]


def rgb(colour) -> tuple[float, float, float]:
    """Any matplotlib colour as ``(r, g, b)`` in 0–1."""
    from matplotlib import colors

    return tuple(float(c) for c in colors.to_rgb(colour))


@dataclass
class ComparisonViolin:
    """One half-violin at one x position."""

    pos: float
    label: str                          # "WT, age 14" — what this violin is
    colour: tuple
    mean_colour: tuple
    width: float                        # of the density and of the band of points, in x units
    gap: float                          # dead space either side of ``pos``
    values: np.ndarray                  # (M,) finite values
    recordings: list[str]               # (M,) the recording of each point
    points: list[str]                   # (M,) what each point is, for reading
    jitter: np.ndarray                  # (M,) 0–1 across the band of points
    curve_y: np.ndarray
    curve_x: np.ndarray                 # density scaled 0–1
    mean: float
    sem: float


@dataclass
class ComparisonPanel:
    title: str
    violins: list[ComparisonViolin]


@dataclass
class ComparisonScene:
    panels: list[ComparisonPanel]
    ticks: list[tuple[float, str]]      # x positions and their labels, the same in every panel
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    xlabel: str
    ylabel: str
    #: ``(title, [(name, (r, g, b))])`` when colour is a third factor.
    legend: tuple[str, list] | None = None
    #: Written across each panel when no recording has a value.
    empty: str | None = None
    #: Written under the figure when some recordings have no value.
    note: str = ""
    #: What a point is: "recording", or the node noun at node level.
    noun: str = "recording"


def comparison_scene(
    df, metric: str, ylabel: str, x_kind: str, *,
    group_order: list | None = None, div_order: list | None = None,
    kde_height: float = 0.3, series_col: str | None = None,
    series_order: list | None = None, series_colors: list | None = None,
    colors=None, ylim: tuple | None = None, age_title_sep: str = " ",
    kde_limits: tuple | None = None, node_noun: str = "node",
) -> ComparisonScene | None:
    """The numbers of ``plotHalfViolinByX.m``; see
    :func:`meanap.pipeline.plotting_step4.plot_half_violin_by_x` for the
    arguments. ``None`` when there is no panel to draw.

    The jitter of the points is drawn from a generator seeded with 0, in the
    order the old plotter drew it, so a figure is the same every time.
    """
    from meanap.pipeline.palette import DEFAULT_SCHEME
    from meanap.pipeline.plotting_step4 import _tick_label

    if df.empty:
        return None
    scheme = colors or DEFAULT_SCHEME
    has_col = metric in df.columns
    data = df.dropna(subset=[metric]) if has_col else df.iloc[0:0]
    is_empty = data.empty
    if "FileName" in df.columns:
        total = int(df["FileName"].nunique())
        with_values = int(data["FileName"].nunique()) if not is_empty else 0
    else:
        total, with_values = len(df), len(data)
    missing = max(0, total - with_values)

    groups = list(group_order) if group_order else sorted(df["Grp"].dropna().unique())

    def divkey(d):
        try:
            return float(str(d).replace("DIV", ""))
        except ValueError:
            return str(d)

    divs = list(div_order) if div_order else sorted(df["DIV"].dropna().unique(), key=divkey)
    if x_kind == "group":
        outer, outer_col, inner, inner_col = groups, "Grp", divs, "DIV"
        inner_colours = scheme.ages(len(divs))
        xlabel = "Age"
        titles = [str(g) for g in groups]

        def name(o, i):
            return f"{o}, age {_tick_label(i)}"
    elif x_kind == "DIV":
        outer, outer_col, inner, inner_col = divs, "DIV", groups, "Grp"
        inner_colours = scheme.groups(len(groups))
        xlabel = "Group"
        titles = [f"Age{age_title_sep}{_tick_label(d)}" for d in divs]

        def name(o, i):
            return f"{i}, age {_tick_label(o)}"
    else:
        raise ValueError(f"x_kind must be 'group' or 'DIV', got {x_kind!r}")
    if not outer or not inner:
        return None

    series: list = []
    if series_col is not None and series_col in df.columns:
        series = (list(series_order) if series_order
                  else sorted(df[series_col].dropna().unique().tolist()))
    gap = 0.1
    if series:
        series_colours = [rgb(c) for c in (series_colors or scheme.groups(len(series)))]
        # Split the unit-wide slot between the series, as the old plotter did.
        slot = 0.92 / len(series)
        offsets = [(s - (len(series) - 1) / 2.0) * slot for s in range(len(series))]
        kde_height, gap = 0.34 * slot, 0.12 * slot
        # Darkened: black would read as another series, and the series' own
        # colour vanishes against its density.
        mean_colours = [tuple(0.45 * c for c in colour) for colour in series_colours]

    point_col = "Channel" if "Channel" in df.columns else None
    rng = np.random.default_rng(0)
    panels = []
    for o_index, o in enumerate(outer):
        violins = []
        sub = data[data[outer_col].astype(str) == str(o)] if not is_empty else data
        for i_index, i in enumerate(inner):
            cell = sub[sub[inner_col].astype(str) == str(i)] if not is_empty else sub
            parts = ([(cell[cell[series_col].astype(str) == str(s)], s_index, s)
                      for s_index, s in enumerate(series)] if series else [(cell, None, None)])
            for frame, s_index, s in parts:
                if frame.empty:
                    continue
                values = frame[metric].to_numpy(float)
                panel = violin_panel(values, "", rng, limits=kde_limits, ylim=(0.0, 1.0))
                if panel is None:
                    continue
                files = frame["FileName"].astype(str).to_numpy()[panel.rows] \
                    if "FileName" in frame.columns else np.array([""] * len(panel.rows))
                if point_col is not None:
                    nodes = frame[point_col].to_numpy()[panel.rows]
                    points = [f"{f}, {node_noun} {_tick_label(n)}" for f, n in zip(files, nodes)]
                else:
                    points = [str(f) for f in files]
                if s_index is None:
                    pos, colour, mean_colour = float(i_index + 1), rgb(inner_colours[i_index]), \
                        (0.0, 0.0, 0.0)
                    label = name(o, i)
                else:
                    pos = float(i_index + 1) + offsets[s_index]
                    colour, mean_colour = series_colours[s_index], mean_colours[s_index]
                    label = f"{name(o, i)}, {s}"
                violins.append(ComparisonViolin(
                    pos=pos, label=label, colour=colour, mean_colour=mean_colour,
                    width=kde_height, gap=gap, values=panel.values,
                    recordings=[str(f) for f in files], points=points, jitter=panel.jitter,
                    curve_y=panel.curve_y, curve_x=panel.curve_x, mean=panel.mean,
                    sem=panel.sem))
        panels.append(ComparisonPanel(title=titles[o_index], violins=violins))

    things = "bursts detected" if "burst" in f"{metric} {ylabel}".lower() else "values"
    empty = note = None
    if is_empty:
        empty = f"No data\n{missing}/{total} recording(s)\nwith no {things}"
        span = (0.0, 1.0)
    else:
        if missing:
            note = f"Note: {missing}/{total} recording(s) had no {things} and are not shown"
        span = _span(panels)
        if ylim is not None:
            # Only the pinned ends move; one that would hide every point is
            # ignored, as before.
            low = span[0] if ylim[0] is None else float(ylim[0])
            high = span[1] if ylim[1] is None else float(ylim[1])
            if high > low:
                span = (low, high)
    n = len(inner)
    return ComparisonScene(
        panels=panels, ticks=[(float(k + 1), _tick_label(w)) for k, w in enumerate(inner)],
        xlim=(0.5, n + 0.5), ylim=span, xlabel=xlabel, ylabel=ylabel,
        legend=((series_col, [(str(s), c) for s, c in zip(series, series_colours)])
                if series else None),
        empty=empty, note=note or "",
        noun=node_noun if point_col is not None else "recording")


def _span(panels: list[ComparisonPanel]) -> tuple[float, float]:
    """The y range matplotlib's autoscale gave: everything drawn, plus 5% each side."""
    lows, highs = [], []
    for panel in panels:
        for v in panel.violins:
            lows += [float(v.curve_y.min()), float(v.values.min()), v.mean - v.sem]
            highs += [float(v.curve_y.max()), float(v.values.max()), v.mean + v.sem]
    if not lows:
        return 0.0, 1.0
    low, high = min(lows), max(highs)
    if high <= low:
        pad = max(abs(low) * 0.05, 0.05)
        return low - pad, high + pad
    pad = (high - low) * 0.05
    return low - pad, high + pad


@dataclass
class LineSeries:
    """Mean ± SEM at each x position; NaN where there is nothing."""

    label: str
    colour: tuple
    means: np.ndarray
    sems: np.ndarray
    counts: np.ndarray                  # recordings behind each mean


@dataclass
class LinePanel:
    title: str
    series: list[LineSeries]
    ylim: tuple[float, float] = (0.0, 1.0)


@dataclass
class LineScene:
    panels: list[LinePanel]
    ticks: list[str]                    # a label per x position, 1…n
    xlabel: str
    ylabel: str
    #: Heading over the key: "DIV", or "" when the labels say it all.
    legend_title: str = ""
    #: How an x position reads ("{} ms lag"), and what a series is ("DIV"),
    #: for reading a point.
    x_format: str = "{}"
    series_noun: str = ""


def line_panel(title: str, series: list[LineSeries]) -> LinePanel:
    """A panel, with the y range its bands need."""
    panel = LinePanel(title=title, series=series)
    panel.ylim = line_span([panel])
    return panel


def line_span(panels: list[LinePanel]) -> tuple[float, float]:
    lows, highs = [], []
    for panel in panels:
        for s in panel.series:
            ok = np.isfinite(s.means)
            if ok.any():
                lows.append(float(np.min(s.means[ok] - s.sems[ok])))
                highs.append(float(np.max(s.means[ok] + s.sems[ok])))
    if not lows:
        return 0.0, 1.0
    low, high = min(lows), max(highs)
    if high <= low:
        pad = max(abs(low) * 0.05, 0.05)
        return low - pad, high + pad
    pad = (high - low) * 0.05
    return low - pad, high + pad


def mean_sem(values) -> tuple[float, float, int]:
    """Mean, standard error and count of the finite *values*; NaN mean if none."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return float("nan"), 0.0, 0
    sem = float(np.std(values) / np.sqrt(len(values))) if len(values) > 1 else 0.0
    return float(np.mean(values)), sem, len(values)


__all__ += ["line_panel", "line_span", "mean_sem"]
