"""A spatial network plot as data: what is drawn, before anything draws it.

:func:`network_scene` takes what ``plot_network`` takes — an adjacency matrix,
node positions, a metric for node size and optionally one for node colour — and
applies the same rules (MATLAB's ``StandardisedNetworkPlot``: node size from the
metric through ``getNodeSize``, edge width and grey from the weight, three
sample values each for the size and edge legends). It returns positions, sizes
and colours; nothing here knows about pixels.

Three deliberate differences from what ``plot_network`` draws:

* the weakest edge is a light grey, not white (see :func:`edge_shade`);

* an edge is a pair of nodes with a weight above zero, once. ``plot_network``
  draws every ordered pair at or above the threshold, so with no threshold it
  also draws the unconnected pairs, as white hairlines;
* only edges between two nodes that are drawn are kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["NetworkScene", "network_scene", "DEFAULT_NODE_COLOUR", "edge_shade",
           "ConnectivityScene", "connectivity_scene", "HeatmapScene", "heatmap_scene",
           "RasterScene", "raster_scene", "ViolinPanel", "ViolinScene", "violin_panel",
           "empty_violin_panel", "chord_arcs", "circular_scene", "NetworkPairScene",
           "BurstScene", "burst_scene", "CartographyScene", "cartography_scene"]

DEFAULT_NODE_COLOUR = (0.020, 0.729, 0.859)
#: Edge shade, 0 black – 1 white: the strongest edge and the weakest. MATLAB
#: runs the weakest to white, which on a white ground is an edge not drawn —
#: every edge of a recording whose weights sit below a batch-wide scale. An
#: edge that is drawn should be seen; hiding weak edges is the edge threshold's
#: job (``network_plot_edge_threshold`` and its kin), not the colour's.
EDGE_DARKEST, EDGE_FAINTEST = 0.2, 0.86


def edge_shade(position) -> np.ndarray:
    """Grey for an edge at *position* (0 weakest – 1 strongest) on the scale."""
    t = np.clip(np.asarray(position, dtype=float), 0.0, 1.0)
    return EDGE_FAINTEST - (EDGE_FAINTEST - EDGE_DARKEST) * t


@dataclass
class NetworkScene:
    """One network, as drawable data. Lengths are in the units of ``xy``."""

    title: str
    xy: np.ndarray                      # (N, 2) centres of the nodes drawn
    diameter: np.ndarray                # (N,)
    colour: np.ndarray                  # (N, 4) RGBA, 0–1
    #: (N,) row of each node in the arrays the scene was computed from.
    index: np.ndarray
    names: list[str]
    #: One description per node: "node degree: 5\nbetweenness centrality: 0.2".
    text: list[str]
    noun: str
    #: (N,) the colour metric per node (NaN where it has none), or ``None``.
    value: np.ndarray | None
    edge_nodes: np.ndarray              # (E, 2) rows of ``xy``
    edge_weight: np.ndarray             # (E,)
    edge_width: np.ndarray              # (E,) points
    edge_grey: np.ndarray               # (E,) 0 black – 1 white
    size_name: str
    size_items: list[tuple[str, float]]             # (label, diameter)
    edge_items: list[tuple[str, float, float]]      # (label, width, grey)
    #: ``{"name", "min", "max", "colormap"}`` when nodes are coloured by a metric.
    colour_key: dict | None
    extent: tuple[float, float, float, float]       # x0, x1, y0, y1 of all nodes
    #: (N, K) 0/1 marker membership, with its names and dash patterns, or empty.
    cell_types: np.ndarray | None = None
    cell_type_names: list[str] = field(default_factory=list)
    cell_type_styles: list = field(default_factory=list)
    #: The multiplier node sizes were scaled by; ring line widths follow it.
    node_size_scale: float = 1.0
    #: ``(image, (x0, x1, y0, y1))`` drawn beneath the network, or ``None``.
    background: tuple | None = None
    #: (E, P, 2) each edge as a curve of P points, for a circular layout;
    #: ``None`` for straight edges.
    edge_arcs: np.ndarray | None = None
    #: ``{"name", "items": [(label, (r, g, b))]}`` when node colour is a
    #: category — a module, a cartography role — rather than a metric.
    category_key: dict | None = None
    #: Points that are not nodes, drawn over the network at a fixed size:
    #: ``{"xy": (x, y), "shape": "star" | "cross", "colour": "#rrggbb",
    #: "size": points, "text": what pointing at it says}``.
    markers: list = field(default_factory=list)

    @property
    def segments(self) -> np.ndarray:
        """(E, 2, 2) the two end points of each edge."""
        return self.xy[self.edge_nodes] if len(self.edge_nodes) else np.zeros((0, 2, 2))

    def neighbours(self, node: int) -> np.ndarray:
        """The nodes joined to *node* by an edge."""
        touching = (self.edge_nodes == node).any(axis=1)
        return np.setdiff1d(np.unique(self.edge_nodes[touching]), [node])


def network_scene(
    adj: np.ndarray,
    coords: np.ndarray,
    edge_thresh: float,
    z: np.ndarray,
    z2: np.ndarray | None = None,
    z2_name: str = "None",
    *,
    title: str = "",
    z_name: str = "node degree",
    names: list | None = None,
    noun: str = "node",
    cell_type_matrix: np.ndarray | None = None,
    cell_type_names: list[str] | None = None,
    cell_type_styles: list | None = None,
    background: tuple | None = None,
    min_node_size: float = 0.01,
    z_scale_override: float | None = None,
    z2_bounds_override: tuple[float, float] | None = None,
    edge_bounds_override: tuple[float, float] | None = None,
    min_ew: float = 0.001,
    max_ew: float = 4.0,
    node_size_scale: float | str = 1.0,
    node_scaling_method: str = "Linear",
    node_scaling_power: float = 1.0,
    colormap: str = "viridis",
) -> NetworkScene:
    """Lay a network out for drawing. Parameters are ``plot_network``'s.

    ``names`` are the nodes' names by row (electrode or cell numbers) and
    ``noun`` what one is called; both are only for reading the plot.
    """
    import matplotlib

    from meanap.network_plot import (
        _cell_type_styles, _get_node_size, auto_node_size_scale,
    )

    adj = np.asarray(adj, dtype=float)
    coords = np.asarray(coords, dtype=float).reshape(-1, 2)
    z = np.asarray(z, dtype=float)
    n = len(adj)
    if isinstance(node_size_scale, str):
        node_size_scale = auto_node_size_scale(coords) if node_size_scale == "auto" else 1.0

    # ── node size ────────────────────────────────────────────────────────────
    z_max = float(np.nanmax(z)) if np.any(~np.isnan(z)) else 0.0
    looks_like_degree = (z_name.lower() == "node degree"
                         or np.allclose(z, np.round(z), equal_nan=True))
    if z_scale_override is not None:
        scale = max(float(z_scale_override), 1e-9)
    else:
        scale = max(z_max, 3.0) if looks_like_degree else max(z_max, 1e-9)

    def size_of(value: float) -> float:
        return _get_node_size(value, scale, min_node_size, method=node_scaling_method,
                              power=node_scaling_power, size_mult=node_size_scale)

    drawn = np.flatnonzero(~np.isnan(z) & (np.nan_to_num(z) > 0))
    diameter = np.array([size_of(float(z[i])) for i in drawn], dtype=float)

    # ── node colour ──────────────────────────────────────────────────────────
    coloured = z2 is not None and z2_name != "None" and not np.all(np.isnan(z2))
    colour = np.tile(np.array([*DEFAULT_NODE_COLOUR, 1.0]), (len(drawn), 1))
    colour_key, value = None, None
    if coloured:
        z2 = np.asarray(z2, dtype=float)
        if z2_bounds_override is not None:
            low, high = (float(v) for v in z2_bounds_override)
        else:
            low, high = float(np.nanmin(z2)), float(np.nanmax(z2))
        value = z2[drawn]
        span = high - low
        # As matplotlib's Normalize: a flat range maps everything to the bottom.
        t = np.zeros(len(drawn)) if span <= 0 else (value - low) / span
        colour = np.asarray(matplotlib.colormaps[colormap](np.nan_to_num(t)), dtype=float)
        colour[np.isnan(value)] = (0.5, 0.5, 0.5, 1.0)
        colour_key = {"name": z2_name, "min": low, "max": high, "colormap": colormap}

    # ── edges ────────────────────────────────────────────────────────────────
    if edge_bounds_override is not None:
        weakest, strongest = (float(v) for v in edge_bounds_override)
    else:
        positive = adj[adj > 0]
        if positive.size:
            weakest, strongest = float(positive.min()), float(positive.max())
        else:
            weakest = strongest = 1.0
    edge_range = strongest - weakest
    if edge_range == 0:
        edge_range = strongest - min_ew
        weakest = min_ew

    def edge_style(weights):
        t = np.clip((np.asarray(weights, dtype=float) - weakest) / edge_range, 0.0, 1.0)
        return min_ew + (max_ew - min_ew) * t, edge_shade(t)

    row = np.full(n, -1)
    row[drawn] = np.arange(len(drawn))
    # One edge per pair: the stronger direction, should the two differ.
    pair = np.fmax(adj, adj.T)
    a, b = np.triu_indices(n, k=1)
    w = pair[a, b]
    keep = (w > 0) & (w >= edge_thresh) & (row[a] >= 0) & (row[b] >= 0)
    a, b, w = a[keep], b[keep], w[keep]
    order = np.argsort(w, kind="stable")            # weakest first: drawn underneath
    a, b, w = a[order], b[order], w[order]
    edge_width, edge_grey = edge_style(w)

    # ── legends ──────────────────────────────────────────────────────────────
    samples = [scale * d / 3 for d in (1, 2, 3)]
    if looks_like_degree:
        samples = [round(v) for v in samples]
        size_items = [(f"{int(v):02d}", float(size_of(v))) for v in samples]
    else:
        size_items = [(f"{v:.4f}", float(size_of(v))) for v in samples]
    edge_items = []
    for fraction in (1 / 3, 2 / 3, 1.0):
        weight = weakest + (strongest - weakest) * fraction
        width, grey = edge_style(weight)
        edge_items.append((f"{weight:.3f}", float(width), float(grey)))

    text = []
    for k, i in enumerate(drawn):
        line = f"{z_name}: {float(z[i]):.4g}"
        if coloured and not np.isnan(value[k]):
            line += f"\n{z2_name}: {float(value[k]):.4g}"
        text.append(line)

    has_types = (cell_type_matrix is not None and cell_type_names is not None
                 and np.asarray(cell_type_matrix).ndim == 2
                 and np.asarray(cell_type_matrix).shape[1] > 0)
    types = np.asarray(cell_type_matrix)[drawn] if has_types else None
    if has_types and cell_type_styles is None:
        cell_type_styles = _cell_type_styles(types.shape[1])

    return NetworkScene(
        title=title, xy=coords[drawn], diameter=diameter, colour=colour, index=drawn,
        names=[str(i) if names is None else str(names[i]) for i in drawn],
        text=text, noun=noun, value=value,
        edge_nodes=np.column_stack([row[a], row[b]]).astype(int).reshape(-1, 2),
        edge_weight=w, edge_width=edge_width, edge_grey=edge_grey,
        size_name=z_name, size_items=size_items, edge_items=edge_items,
        colour_key=colour_key,
        extent=(float(coords[:, 0].min()), float(coords[:, 0].max()),
                float(coords[:, 1].min()), float(coords[:, 1].max())) if n else (0, 1, 0, 1),
        cell_types=types, cell_type_names=list(cell_type_names) if has_types else [],
        cell_type_styles=list(cell_type_styles) if has_types else [],
        node_size_scale=float(node_size_scale), background=background)


@dataclass
class ConnectivityScene:
    """The connectivity-statistics figure as data.

    The adjacency matrix, its largest and mean edge weight, and what the three
    histograms bin: node degree, node strength and edge weight.
    """

    title: str
    adj: np.ndarray                     # (N, N)
    nd: np.ndarray                      # (N,) node degree
    ns: np.ndarray                      # (N,) node strength
    edge_weights: np.ndarray            # the weights the third histogram bins
    max_value: float
    mean_value: float
    #: y range shared by the two summary bars.
    bar_ylim: tuple[float, float]
    names: list[str]
    noun: str = "node"


def connectivity_scene(adj: np.ndarray, nd: np.ndarray, ns: np.ndarray, *, title: str = "",
                       exclude_edges_below_threshold: bool = True,
                       names: list | None = None, noun: str = "node") -> ConnectivityScene:
    """Port of ``plotConnectivityProperties.m``'s numbers, without its drawing."""
    adj = np.asarray(adj, dtype=float)
    weights = adj[adj > 0] if exclude_edges_below_threshold else adj.ravel()
    mean = float(np.nanmean(weights)) if weights.size else 0.0
    largest = max(float(np.max(weights)) if weights.size else 0.0, 0.001)
    top = max(float(np.max(adj)) if adj.size else 0.0, 0.0001)
    count = len(adj)
    return ConnectivityScene(
        title=title, adj=adj, nd=np.asarray(nd, dtype=float).ravel(),
        ns=np.asarray(ns, dtype=float).ravel(), edge_weights=np.asarray(weights, dtype=float),
        max_value=largest, mean_value=mean, bar_ylim=(0.0, top * 1.15),
        names=[str(i + 1) for i in range(count)] if names is None else [str(n) for n in names],
        noun=noun)


@dataclass
class HeatmapScene:
    """One value per electrode, placed where the electrode is.

    One panel per colour scale: this recording's own, and — when the run has a
    batch maximum — the whole data set's, so levels compare across recordings.
    """

    xy: np.ndarray                      # (N, 2)
    values: np.ndarray                  # (N,) NaN where there is none (grounded, silent)
    names: list[str]
    #: ``(title, low, high)`` of each panel's colour scale.
    panels: list[tuple[str, float, float]]
    label: str                          # what the colour is: "mean firing rate (Hz)"
    cmap: object = "viridis"
    noun: str = "electrode"
    #: Marker diameter, in the units of ``xy``.
    diameter: float = 1.0


def heatmap_scene(metric, chs, title: str, label: str, *, cmap="viridis",
                  channel_layout: str = "Axion64", batch_max: float | None = None,
                  aggregate: str = "mean", layout=None,
                  grounded: set[int] | None = None) -> HeatmapScene | None:
    """Port of ``electrodeHeatMaps.m`` / ``plotNodeHeatmap.m``, without the drawing.

    The arguments are ``plot_heatmap``'s. ``None`` when there is nothing to
    place: no values, or no channel the layout knows.
    """
    from scipy.spatial import cKDTree

    from meanap.pipeline.channel_layout import get_coords_from_layout

    metric = np.asarray(metric, dtype=float)
    if len(metric) == 0:
        return None
    layout_channels, layout_coords = (layout if layout is not None
                                      else get_coords_from_layout(channel_layout))
    where = dict(zip(np.asarray(layout_channels).tolist(), map(tuple, layout_coords)))
    chs = np.asarray(chs).ravel()
    if len(np.unique(chs)) < len(chs):
        # Several units on an electrode — a spike-sorted run — pool into one value.
        electrodes = np.unique(chs)
        pooled = np.full(len(electrodes), np.nan)
        for i, electrode in enumerate(electrodes):
            values = metric[chs == electrode]
            values = values[np.isfinite(values)]
            if len(values):
                pooled[i] = values.sum() if aggregate == "sum" else values.mean()
        chs, metric = electrodes, pooled
    keep = np.array([int(c) in where for c in chs])
    if not np.any(keep):
        return None
    xy = np.array([where[int(c)] for c in chs[keep]], dtype=float)
    metric = metric[keep]
    if grounded:
        # Grounding empties a spike train; left in, it would read as a silent
        # electrode and set the bottom of the scale.
        metric = np.where(np.isin(chs[keep].astype(int), list(grounded)), np.nan, metric)
    valid = metric[~np.isnan(metric)]
    low, high = (float(valid.min()), float(np.percentile(valid, 99))) if valid.size else (0.0, 1.0)
    if low == high:
        high = low + 1e-5
    panels = [(title, low, high)]
    if batch_max is not None:
        top = float(batch_max)
        if top <= low or np.isnan(top):
            top = low + 1e-5
        panels = [(f"{title} scaled to recording", low, high),
                  (f"{title} scaled to entire dataset", low, top)]
    unique = np.unique(xy, axis=0)
    spacing = (float(np.median(cKDTree(unique).query(unique, k=2)[0][:, 1]))
               if len(unique) > 1 else 1.0)
    return HeatmapScene(xy=xy, values=metric, names=[str(int(c)) for c in chs[keep]],
                        panels=panels, label=label, cmap=cmap, diameter=0.82 * spacing)


@dataclass
class RasterScene:
    """Activity through time, a row per electrode or cell, on one or two colour scales.

    For an ephys recording a cell is the spike count in one second; a calcium
    recording fills ``counts`` with its own measure and says so in ``label``.
    """

    counts: np.ndarray                  # (rows, bins) the value in each time bin
    duration_s: float
    #: ``(title, high)`` of each panel; every scale starts at zero.
    panels: list[tuple[str, float]]
    names: list[str]
    noun: str = "electrode"
    cmap: object = "viridis"
    #: Seconds a column covers, and the unit the time axis is read in.
    bin_s: float = 1.0
    time_unit: str = "min"
    #: What a cell's value is: the colour bar's label, and the unit after a value.
    label: str = "Firing Rate (Hz)"
    unit: str = "Hz"
    #: The scale runs from ``-high`` to ``high`` rather than from zero.
    symmetric: bool = False


def raster_scene(spike_times: dict, duration_s: float, *, title: str = "",
                 spike_freq_max: float | None = None, upper_percentile: float = 99.0,
                 names: list | None = None, cmap="viridis",
                 noun: str = "electrode") -> RasterScene:
    """Port of ``rasterPlot.m``'s numbers. The arguments are ``plot_raster``'s.

    Bins are one second wide, so a cell is a count per second (Hz). The top
    panel's scale ends at the *upper_percentile* of this recording's counts,
    the bottom's at *spike_freq_max* — the batch-wide maximum, which makes
    recordings comparable — or at the same percentile when there is none.
    """
    rows = len(spike_times)
    bins = max(1, int(np.ceil(duration_s)))
    counts = np.zeros((rows, bins))
    for channel, times in spike_times.items():
        if len(times) > 0:
            counts[channel, :] = np.histogram(times, bins=bins, range=(0, bins))[0]
    own = max(1.0, float(np.percentile(counts, upper_percentile)))
    batch = max(1.0, float(spike_freq_max)) if spike_freq_max is not None else own
    return RasterScene(
        counts=counts, duration_s=float(duration_s),
        panels=[(f"{title} raster scaled to recording", own),
                (f"{title} raster scaled to entire data batch", batch)],
        names=[str(i + 1) for i in range(rows)] if names is None else [str(n) for n in names],
        noun=noun, cmap=cmap)


@dataclass
class ViolinPanel:
    """One half-violin: a density to the right, the points to the left, the mean."""

    label: str                          # the y axis: "node degree"
    values: np.ndarray                  # (M,) the finite values
    #: (M,) which node each value belongs to, as a row of the scene's ``names``.
    rows: np.ndarray
    #: (M,) where each point sits across the violin, 0–1 of its width.
    jitter: np.ndarray
    #: The density curve: values along the axis, and density scaled 0–1.
    curve_y: np.ndarray
    curve_x: np.ndarray
    mean: float
    sem: float
    ylim: tuple[float, float]
    #: A picture explaining the metric, shown above the panel, or ``None``.
    icon: str | None = None
    xlabel: str = ""


@dataclass
class ViolinScene:
    """Half-violins side by side, one per metric, over the same nodes."""

    title: str
    panels: list[ViolinPanel]
    names: list[str]
    noun: str = "node"
    colour: tuple = (0.3, 0.3, 0.3)
    #: Width of the density and of the band of points, in units where the
    #: panel is one unit either side of the mean marker.
    width: float = 1.0
    gap: float = 0.1
    #: Draw the x axis line (a lone violin has one; a row of them does not).
    x_spine: bool = False


def violin_panel(data, label: str, rng: np.random.Generator, *,
                 limits: tuple | None = None, ylim: tuple | None = None,
                 icon: str | None = None, xlabel: str = "") -> ViolinPanel | None:
    """The numbers of one half-violin: port of ``HalfViolinPlot.m``.

    Gaussian KDE with Silverman's rule and a minimum bandwidth of a tenth of
    the data range, evaluated three bandwidths past the data each side and cut
    at *limits* — the metric's theoretical range — unless the data crosses
    them. ``None`` when there is nothing finite to draw.
    """
    from scipy.stats import gaussian_kde

    data = np.asarray(data, dtype=float).ravel()
    rows = np.flatnonzero(np.isfinite(data))
    values = data[rows]
    if not len(values):
        return None
    if len(values) > 1 and np.std(values) > 1e-8:
        kde = gaussian_kde(values, bw_method="silverman")
        floor = (values.max() - values.min()) * 0.1
        if kde.factor * np.std(values) < floor:
            kde = gaussian_kde(values, bw_method=floor / np.std(values))
        bandwidth = float(np.sqrt(kde.covariance[0, 0]))
        low, high = values.min() - 3 * bandwidth, values.max() + 3 * bandwidth
        if limits is not None:
            if limits[0] is not None:
                low = max(low, min(limits[0], values.min()))
            if limits[1] is not None:
                high = min(high, max(limits[1], values.max()))
        curve_y = np.linspace(low, high, 256)
        density = kde(curve_y)
    else:
        # A single value, or no spread: a spike.
        curve_y, density = np.array([values.mean()]), np.array([1.0])
    # Drawn in the same order as HalfViolinPlot.m draws: jitter after the KDE.
    jitter = rng.random(len(values))
    if ylim is None:
        low, high = float(values.min()), float(values.max())
        pad = (high - low) * 0.1 or max(abs(high) * 0.1, 0.05)
        ylim = (low - pad, high + pad)
    return ViolinPanel(
        label=label, values=values, rows=rows, jitter=jitter, curve_y=curve_y,
        curve_x=density / max(float(density.max()), 1e-12), mean=float(values.mean()),
        sem=float(np.std(values) / np.sqrt(len(values))) if len(values) > 1 else 0.0,
        ylim=(float(ylim[0]), float(ylim[1])), icon=icon, xlabel=xlabel)


def empty_violin_panel(label: str, *, icon: str | None = None) -> ViolinPanel:
    """A panel with its axis and picture but nothing in it: a metric not computed."""
    none = np.zeros(0)
    return ViolinPanel(label=label, values=none, rows=none.astype(int), jitter=none,
                       curve_y=none, curve_x=none, mean=float("nan"), sem=0.0,
                       ylim=(0.0, 1.0), icon=icon)


def chord_arcs(angle_a, angle_b, points: int = 33) -> np.ndarray:
    """(E, points, 2) curved chords between nodes on the unit circle.

    Each is the arc, inside the disc, of the circle through the two nodes that
    meets the unit circle at right angles — the geometry of MATLAB's circular
    network plot. For nodes ``u`` and ``v`` that circle is centred at
    ``(u + v) / (1 + u·v)``; opposite nodes are joined by a straight line.
    """
    a = np.asarray(angle_a, dtype=float)
    b = np.asarray(angle_b, dtype=float)
    u = np.column_stack([np.cos(a), np.sin(a)])
    v = np.column_stack([np.cos(b), np.sin(b)])
    dot = (u * v).sum(axis=1)
    straight = dot < -1 + 1e-9
    centre = (u + v) / np.where(straight, 1.0, 1 + dot)[:, None]
    radius = np.sqrt(np.maximum((centre ** 2).sum(axis=1) - 1.0, 0.0))
    start = np.arctan2(u[:, 1] - centre[:, 1], u[:, 0] - centre[:, 0])
    end = np.arctan2(v[:, 1] - centre[:, 1], v[:, 0] - centre[:, 0])
    # The short way round: that is the part of the circle inside the disc.
    sweep = (end - start + np.pi) % (2 * np.pi) - np.pi
    t = np.linspace(0.0, 1.0, points)
    theta = start[:, None] + sweep[:, None] * t[None, :]
    arcs = np.stack([centre[:, 0:1] + radius[:, None] * np.cos(theta),
                     centre[:, 1:2] + radius[:, None] * np.sin(theta)], axis=2)
    if straight.any():
        arcs[straight] = (u[straight, None, :] * (1 - t)[None, :, None]
                          + v[straight, None, :] * t[None, :, None])
    return arcs


def circular_scene(adj: np.ndarray, colour: np.ndarray, diameter: np.ndarray,
                   text: list[str], *, title: str = "", edge_thresh: float = 0.0,
                   size_name: str = "", size_items: list | None = None,
                   category_key: dict | None = None, names: list | None = None,
                   noun: str = "node", min_ew: float = 0.001,
                   max_ew: float = 2.0) -> NetworkScene:
    """A network with its nodes evenly round a circle, in row order.

    Port of the ``plotType='circular'`` branch of MATLAB's network plots:
    node ``i`` of ``N`` sits at angle ``-π + 2πi/N``, edges are curved chords,
    weakest drawn first. *colour* (N, 3) and *diameter* (N,) are the caller's —
    by module and degree, or by cartography role — and a node with a diameter
    of zero is not drawn.
    """
    adj = np.asarray(adj, dtype=float)
    n = len(adj)
    angle = np.linspace(-np.pi, np.pi, n + 1)[:n]
    diameter = np.asarray(diameter, dtype=float)
    drawn = np.flatnonzero(diameter > 0)
    row = np.full(n, -1)
    row[drawn] = np.arange(len(drawn))

    positive = adj[adj > 0]
    strongest = float(adj.max()) if n and adj.max() > 0 else 1.0
    weakest = float(positive.min()) if positive.size else strongest
    span = strongest - weakest if strongest != weakest else max(strongest, 1e-6)

    def edge_style(weights):
        t = (np.asarray(weights, dtype=float) - weakest) / span
        return np.maximum(min_ew + (max_ew - min_ew) * t, min_ew), edge_shade(t)

    pair = np.fmax(adj, adj.T)
    a, b = np.triu_indices(n, k=1)
    w = pair[a, b]
    keep = (w > 0) & (w >= edge_thresh) & (row[a] >= 0) & (row[b] >= 0)
    a, b, w = a[keep], b[keep], w[keep]
    order = np.argsort(w, kind="stable")
    a, b, w = a[order], b[order], w[order]
    width, grey = edge_style(w)
    edge_items = []
    for fraction in (1 / 3, 2 / 3, 1.0):
        weight = strongest - (1 - fraction) * span
        item_width, item_grey = edge_style(weight)
        edge_items.append((f"{round(weight, 4)}", float(item_width), float(item_grey)))

    colour = np.asarray(colour, dtype=float)[drawn, :3]
    return NetworkScene(
        title=title, xy=np.column_stack([np.cos(angle), np.sin(angle)])[drawn],
        diameter=diameter[drawn], colour=np.column_stack([colour, np.ones(len(drawn))]),
        index=drawn, names=[str(i + 1) if names is None else str(names[i]) for i in drawn],
        text=[text[i] for i in drawn], noun=noun, value=None,
        edge_nodes=np.column_stack([row[a], row[b]]).astype(int).reshape(-1, 2),
        edge_weight=w, edge_width=width, edge_grey=grey,
        size_name=size_name, size_items=list(size_items or []), edge_items=edge_items,
        colour_key=None, extent=(-1.0, 1.0, -1.0, 1.0),
        edge_arcs=chord_arcs(angle[a], angle[b]) if len(a) else np.zeros((0, 33, 2)),
        category_key=category_key)


@dataclass
class NetworkPairScene:
    """Two views of one network side by side, sharing their zoom.

    Either the same network on two scales — this recording's own, and the
    whole data set's — or, with *left_is_field*, the imaged field of view
    beside the network drawn from it.
    """

    left: NetworkScene
    right: NetworkScene
    #: The left panel shows only ``left.background``: no nodes, edges or legend.
    left_is_field: bool = False


@dataclass
class BurstScene:
    """What burst detection made of a recording: all spikes, those in bursts, and ISIs."""

    full: np.ndarray                    # (channels, bins) spikes in each bin
    bursts: np.ndarray                  # the same, counting only spikes inside a burst
    duration_s: float
    bin_s: float
    names: list[str]
    noun: str = "electrode"
    cmap: object = "viridis"
    #: Edges of the inter-spike-interval bins, in seconds, evenly spaced in
    #: log; ``None`` when the recording has too few spikes for a histogram.
    isi_edges: np.ndarray | None = None
    #: Density of intervals outside bursts and within them, per bin.
    isi_outside: np.ndarray | None = None
    isi_within: np.ndarray | None = None
    n_outside: int = 0
    n_within: int = 0


def _inside(times: np.ndarray, spans: np.ndarray) -> np.ndarray:
    """Which of *times* fall inside any of the ``(start, end)`` *spans*."""
    times = np.asarray(times, dtype=float)
    if spans.size == 0 or times.size == 0:
        return np.zeros(times.shape, dtype=bool)
    order = np.argsort(spans[:, 0])
    starts = spans[order, 0]
    # The latest end among the spans starting at or before each one, so spans
    # that overlap are still handled.
    ends = np.maximum.accumulate(spans[order, 1])
    at = np.searchsorted(starts, times, side="right") - 1
    return (at >= 0) & (times <= ends[np.clip(at, 0, None)])


def burst_scene(spike_times: dict, burst_times, duration_s: float, *,
                names: list | None = None, noun: str = "electrode",
                cmap="viridis", bin_s: float = 0.1, isi_bins: int = 100) -> BurstScene:
    """The numbers behind the burst-detection figure.

    *spike_times* maps a channel's row to its spike times in seconds;
    *burst_times* is ``(start, end)`` of each network burst, in seconds. An
    interval between consecutive spikes of the whole array counts as within a
    burst when its midpoint is inside one.
    """
    rows = len(spike_times)
    bins = max(1, int(np.ceil(duration_s / bin_s)))
    spans = np.asarray(burst_times, dtype=float).reshape(-1, 2)
    full = np.zeros((rows, bins))
    bursts = np.zeros((rows, bins))
    everything = []
    for channel, times in spike_times.items():
        times = np.asarray(times, dtype=float)
        if times.size == 0:
            continue
        everything.append(times)
        full[channel] = np.histogram(times, bins=bins, range=(0, duration_s))[0]
        bursts[channel] = np.histogram(times[_inside(times, spans)], bins=bins,
                                       range=(0, duration_s))[0]
    scene = BurstScene(
        full=full, bursts=bursts, duration_s=float(duration_s), bin_s=float(bin_s),
        names=[str(i + 1) for i in range(rows)] if names is None else [str(n) for n in names],
        noun=noun, cmap=cmap)
    if not everything:
        return scene
    pooled = np.sort(np.concatenate(everything))
    isi = np.diff(pooled)
    if isi.size == 0:
        return scene
    low, high = max(1e-5, float(isi.min())), float(isi.max())
    if not high > low:
        return scene
    within = _inside(pooled[:-1] + isi / 2.0, spans)
    edges = np.logspace(np.log10(low), np.log10(high), isi_bins)
    scene.isi_edges = edges
    scene.n_within, scene.n_outside = int(within.sum()), int((~within).sum())
    for name, values in (("isi_within", isi[within]), ("isi_outside", isi[~within])):
        if values.size:
            with np.errstate(invalid="ignore", divide="ignore"):
                density = np.histogram(values, bins=edges, density=True)[0]
            setattr(scene, name, np.nan_to_num(density))
    return scene


@dataclass
class CartographyScene:
    """Each node by participation coefficient and within-module degree z-score."""

    title: str
    pc: np.ndarray                      # (N,) participation coefficient
    z: np.ndarray                       # (N,) within-module degree z-score
    role: np.ndarray                    # (N,) 1–6, or 0 where a node has none
    names: list[str]
    #: ``(hub, peripheral, non-hub connector, provincial hub, connector hub)``:
    #: the z-score that makes a hub, then the participation coefficients that
    #: divide the roles below it and above it.
    boundaries: tuple[float, float, float, float, float]
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    #: ``{role: (label, (r, g, b))}``.
    roles: dict = field(default_factory=dict)
    noun: str = "electrode"
    #: A picture explaining the roles, shown under the plot, or ``None``.
    diagram: str | None = None


def cartography_scene(pc, z, role, boundaries, *, title: str = "", roles: dict,
                      names: list | None = None, noun: str = "electrode",
                      diagram: str | None = None) -> CartographyScene:
    """Port of the top panel of ``NodeCartography.m``'s numbers."""
    pc = np.asarray(pc, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    xlim, ylim = (0.0, 1.0), (-2.0, 4.0)
    if pc.size and not np.all(np.isnan(pc)):
        low, high = float(np.nanmin(pc)), float(np.nanmax(pc))
        if high > low:
            # A little room, so a node at either end is drawn whole.
            pad = (high - low) * 0.04
            xlim = (low - pad, high + pad)
    if z.size and not np.all(np.isnan(z)):
        low, high = float(np.nanmin(z)), float(np.nanmax(z))
        low *= 1.1 if low < 0 else 0.9
        high *= 1.1 if high > 0 else 0.9
        if high > low:
            ylim = (low, high)
    shown = np.zeros(pc.size, dtype=int)
    given = np.asarray(role, dtype=float).ravel()[:pc.size]
    ok = np.isfinite(given)
    shown[:given.size][ok] = given[ok].astype(int)
    return CartographyScene(
        title=title, pc=pc, z=z, role=shown,
        names=([str(i + 1) for i in range(pc.size)] if names is None
               else [str(n) for n in names]),
        boundaries=tuple(float(b) for b in boundaries), xlim=xlim, ylim=ylim,
        roles=dict(roles), noun=noun, diagram=diagram)
