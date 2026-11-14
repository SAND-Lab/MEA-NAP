"""Step 4 check plots: ``plotConnectivityProperties.m``,
``StandardisedNetworkPlot.m`` (base + betweenness-centrality-colored
variants), ``NodeCartography.m``,
``StandardisedNetworkPlotNodeColourMap.m`` (circular/module variant),
``electrodeSpecificMetrics.m`` (half-violin panel of all node metrics), and
``StandardisedNetworkPlotNodeCartography.m`` (circular/cartography variant).

Not ported: null-model panels (small-worldness — stochastic, see
``network_metrics.py``'s docstring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meanap.network_plot import NetworkStyle

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from meanap.pipeline.figure_output import savefig

from meanap.params import Params
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.network_metrics import classify_node_cartography


def _std_title(recording_name: str, lag_ms) -> str:
    """MATLAB's standard 4A title, ``"<FNt> <lag> ms lag"``.

    ``FNt`` is the recording name with its underscores removed, which is how
    MATLAB titles every per-recording network figure.
    """
    return f"{recording_name.replace('_', '')} {lag_ms} ms lag"


def plot_connectivity_stats(
    adj_m: np.ndarray,
    nd: np.ndarray,
    ns: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    exclude_edges_below_threshold: bool = True,
    node_names: list | None = None,
    node_noun: str = "node",
) -> None:
    """Port of ``plotConnectivityProperties.m``'s single saved figure.

    ``node_names`` and ``node_noun`` name the rows of ``adj_m`` for an
    interactive view; they change nothing that is drawn.

    Drawn by Qt, not matplotlib: the file written here is the figure the viewer
    shows and exports (see :mod:`meanap.native`).
    """
    from meanap.native import output
    from meanap.native.connectivity_paint import ConnectivityPainter
    from meanap.native.scene import connectivity_scene

    scene = connectivity_scene(
        adj_m, nd, ns, title=_std_title(recording_name, lag_ms),
        exclude_edges_below_threshold=exclude_edges_below_threshold,
        names=node_names, noun=node_noun)
    painter = ConnectivityPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("connectivity", scene, painter))


def plot_spatial_network(
    adj_m_sub: np.ndarray,
    channels_active: np.ndarray,
    channel_layout: str,
    z: np.ndarray,
    z2: np.ndarray | None,
    z2_name: str,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    edge_thresh: float = 0.0,
    z_name: str = "node degree",
    z_scale_override: float | None = None,
    z2_bounds_override: tuple[float, float] | None = None,
    edge_bounds_override: tuple[float, float] | None = None,
    coords_override: np.ndarray | None = None,
    cell_types: tuple[np.ndarray, list[str]] | None = None,
    background: tuple | None = None,
    node_size_scale: float | str = 1.0,
    style: "NetworkStyle | None" = None,
) -> None:
    """Spatial network plot, port of the base ``2_MEA_NetworkPlot.png`` from
    ``StandardisedNetworkPlot.m`` (reuses ``network_plot.py``'s
    ``plot_network``, built for the Network Viewer GUI tab, since it's
    already a generic MEA-plot renderer).

    Electrode coordinates come from ``channel_layout.get_coords_from_layout``.
    Active channels without a coordinate entry (e.g. grounded corner
    electrodes on MCS-family layouts) are silently dropped from the plot —
    they still contribute to the underlying metrics, just not this figure.

    ``z_name`` matters, not just cosmetically: it also tells
    ``plot_network`` whether ``z`` is degree-like (small integers) or a
    continuous metric like node strength — sizing a continuous metric with
    the integer-degree scaling logic renders every node far too small. Pass
    e.g. ``"node strength"`` whenever ``z`` isn't literally node degree (see
    ``network_plot.py``'s ``plot_network`` docstring).
    """
    ct_matrix, ct_names = cell_types if cell_types else (None, None)
    prepared = _prepare_network_plot_data(
        adj_m_sub, channels_active, channel_layout, z, z2, coords_override, ct_matrix,
    )
    if prepared is None:
        return
    sub, coords, z_sub, z2_sub, ct_matrix = prepared

    # ``style`` carries the Network Viewer control set (edge subsampling and
    # threshold, layout, node scaling, edge widths, colormap). Left as None the
    # pipeline's long-standing styling applies unchanged — see
    # NetworkStyle.pipeline_default, which the renderer relies on for parity.
    from meanap.network_plot import NetworkStyle

    if style is None:
        # No restyling: keep the caller's edge_thresh and coordinates exactly.
        style = NetworkStyle.pipeline_default(node_size_scale)
    else:
        sub, coords, edge_thresh = style.prepare(sub, coords)

    # Drawn by Qt, not matplotlib: the file written here, the figure the
    # viewer shows and what it exports are the same drawing (meanap.native).
    # MATLAB titles the batch-scaled variant exactly like the plain one; only
    # the file name ("<n>_scaled_…") tells them apart.
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter
    from meanap.native.scene import network_scene

    names, noun = _node_names(channels_active, channel_layout, coords_override)
    scene = network_scene(
        sub, coords, edge_thresh, z_sub, z2_sub, z2_name,
        title=_std_title(recording_name, lag_ms), z_name=z_name,
        names=names, noun=noun,
        z_scale_override=z_scale_override,
        z2_bounds_override=z2_bounds_override,
        edge_bounds_override=edge_bounds_override,
        cell_type_matrix=ct_matrix, cell_type_names=ct_names,
        background=background,
        node_size_scale=style.node_size_scale,
        node_scaling_method=style.node_scaling_method,
        node_scaling_power=style.node_scaling_power,
        min_node_size=style.min_node_size,
        min_ew=style.min_edge_width, max_ew=style.max_edge_width,
        colormap=style.colormap,
    )
    painter = NetworkPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("network", scene, painter))


def plot_network_beside_field(
    adj_m_sub: np.ndarray,
    channels_active: np.ndarray,
    channel_layout: str,
    z: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    background: tuple,
    edge_thresh: float = 0.0,
    z_name: str = "node degree",
    coords_override: np.ndarray | None = None,
    node_size_scale: float | str = 1.0,
) -> None:
    """The imaged field beside the network derived from it.

    Left: the raw field of view (CAT-NAP passes suite2p's mean projection).
    Right: the network, drawn exactly as the standalone spatial plot draws it.

    Deliberately *not* an overlay. Superimposing the two hides the image
    entirely once there are a few hundred nodes and a dense edge set — the
    thing you wanted to look at is the thing that gets covered. Side by side,
    on identical axes, you can still check node-by-node that the analysis sits
    on real cells, which is the only question this figure exists to answer.
    """
    prepared = _prepare_network_plot_data(
        adj_m_sub, channels_active, channel_layout, z, None, coords_override,
    )
    if prepared is None:
        return
    sub, coords, z_sub, _z2, _ct = prepared

    import dataclasses

    from meanap.native import output
    from meanap.native.network_paint import NetworkPairPainter
    from meanap.native.scene import NetworkPairScene, network_scene

    names, noun = _node_names(channels_active, channel_layout, coords_override)
    network = network_scene(
        sub, coords, edge_thresh, z_sub, None, "None",
        title=_std_title(recording_name, lag_ms), z_name=z_name, names=names, noun=noun,
        node_size_scale=node_size_scale)
    # The same scene with the image behind it and nothing drawn on top: the
    # two panels are then the same view of the same coordinates.
    field = dataclasses.replace(network, background=background, title="Imaged field of view")
    scene = NetworkPairScene(left=field, right=network, left_is_field=True)
    painter = NetworkPairPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("field", scene, painter))


def _node_names(channels_active, channel_layout: str,
                coords_override: np.ndarray | None) -> tuple[list, str]:
    """The name of each node a spatial plot draws, by row, and what one is called.

    Uses the same rule as :func:`_prepare_network_plot_data` for which channels
    survive, so the names line up with the rows that were drawn.
    """
    if coords_override is not None:
        return list(np.asarray(channels_active).tolist()), "cell"
    layout_channels, _ = get_coords_from_layout(channel_layout)
    known = set(layout_channels.tolist())
    return [int(ch) for ch in channels_active if int(ch) in known], "electrode"


def _prepare_network_plot_data(
    adj_m_sub: np.ndarray,
    channels_active: np.ndarray,
    channel_layout: str,
    z: np.ndarray,
    z2: np.ndarray | None,
    coords_override: np.ndarray | None = None,
    ct_matrix: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None] | None:
    """Map active channels to coordinates and subset the adjacency matrix /
    per-node metrics to the channels that have one.

    ``ct_matrix`` (an ``(n_active, n_markers)`` membership matrix) is subset by
    the same index as everything else, so cell-type rings cannot drift out of
    alignment with the nodes they belong to when a channel is dropped.

    ``coords_override`` (an ``(n_active, 2)`` array aligned with
    ``channels_active``) supplies coordinates directly instead of the MEA
    ``channel_layout`` lookup — used by the CAT-NAP path, whose node positions
    come from suite2p cell centroids rather than an electrode grid. In that
    case every active node has a coordinate, so nothing is dropped.

    Returns ``(sub_adj, coords, z_sub, z2_sub, ct_sub)`` or ``None`` if no
    active channel has a coordinate (e.g. an all-grounded layout). Shared by
    ``plot_spatial_network`` and ``plot_spatial_network_combined`` so both
    subset identically.
    """
    if coords_override is not None:
        return adj_m_sub, np.asarray(coords_override, dtype=float), z, z2, ct_matrix

    layout_channels, layout_coords = get_coords_from_layout(channel_layout)
    coord_by_channel = dict(zip(layout_channels.tolist(), map(tuple, layout_coords)))

    has_coord = np.array([int(ch) in coord_by_channel for ch in channels_active])
    if not np.any(has_coord):
        return None
    idx = np.nonzero(has_coord)[0]

    sub = adj_m_sub[np.ix_(idx, idx)]
    coords = np.array([coord_by_channel[int(channels_active[i])] for i in idx])
    z_sub = z[idx]
    z2_sub = z2[idx] if z2 is not None else None
    ct_sub = np.asarray(ct_matrix)[idx] if ct_matrix is not None else None
    return sub, coords, z_sub, z2_sub, ct_sub


def plot_spatial_network_combined(
    adj_m_sub: np.ndarray,
    channels_active: np.ndarray,
    channel_layout: str,
    z: np.ndarray,
    z2: np.ndarray | None,
    z2_name: str,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    z_scale_override: float,
    z2_bounds_override: tuple[float, float] | None,
    edge_bounds_override: tuple[float, float] | None,
    edge_thresh: float = 0.0,
    z_name: str = "node degree",
    coords_override: np.ndarray | None = None,
    cell_types: tuple[np.ndarray, list[str]] | None = None,
    node_size_scale: float | str = 1.0,
    style: "NetworkStyle | None" = None,
) -> None:
    """Side-by-side "combined" network plot, port of the
    ``N_combined_MEA_NetworkPlot`` figure from ``PlotIndvNetMet.m``.

    Left panel is scaled to this recording's own range; right panel is scaled
    to the whole data batch (via the ``*_override`` bounds). Same two-scale
    comparison MATLAB builds by ``copyobj``-ing its individual and scaled
    figures into one two-subplot figure — here we just render
    ``plot_network`` onto two axes of a single wide figure, each with its own
    inline legend/colorbar.

    ``coords_override`` behaves as in :func:`plot_spatial_network` — suite2p
    cell centroids for the CAT-NAP path instead of an electrode-grid lookup.

    ``cell_types``, ``node_size_scale`` and ``style`` mean exactly what they do
    in :func:`plot_spatial_network`, and are applied identically to both
    panels. The point of this figure is that the two panels differ *only* in
    what they are scaled to, so any styling that reached one and not the other
    would make it lie; and the panels have to be drawn the way the single
    figures beside them were, or the comparison is between a network and a
    differently-drawn network.
    """
    ct_matrix, ct_names = cell_types if cell_types else (None, None)
    prepared = _prepare_network_plot_data(
        adj_m_sub, channels_active, channel_layout, z, z2, coords_override,
        ct_matrix,
    )
    if prepared is None:
        return
    sub, coords, z_sub, z2_sub, ct_matrix = prepared

    from meanap.network_plot import NetworkStyle

    if style is None:
        style = NetworkStyle.pipeline_default(node_size_scale)
    else:
        sub, coords, edge_thresh = style.prepare(sub, coords)

    styling = dict(
        cell_type_matrix=ct_matrix, cell_type_names=ct_names,
        node_size_scale=style.node_size_scale,
        node_scaling_method=style.node_scaling_method,
        node_scaling_power=style.node_scaling_power,
        min_node_size=style.min_node_size,
        min_ew=style.min_edge_width, max_ew=style.max_edge_width,
        colormap=style.colormap,
    )

    # No titles: MATLAB builds this figure with copyobj, which drops them.
    from meanap.native import output
    from meanap.native.network_paint import NetworkPairPainter
    from meanap.native.scene import NetworkPairScene, network_scene

    names, noun = _node_names(channels_active, channel_layout, coords_override)
    title = _std_title(recording_name, lag_ms)
    own = network_scene(
        sub, coords, edge_thresh, z_sub, z2_sub, z2_name, z_name=z_name,
        title=f"{title} — scaled to recording", names=names, noun=noun, **styling)
    batch = network_scene(
        sub, coords, edge_thresh, z_sub, z2_sub, z2_name, z_name=z_name,
        title=f"{title} — scaled to entire dataset", names=names, noun=noun,
        z_scale_override=z_scale_override,
        z2_bounds_override=z2_bounds_override,
        edge_bounds_override=edge_bounds_override,
        **styling)
    scene = NetworkPairScene(left=own, right=batch)
    painter = NetworkPairPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("network", scene, painter))


_CARTOGRAPHY_COLORS = {
    1: (0.8, 0.902, 0.310),    # Peripheral node — light green
    2: (0.580, 0.706, 0.278),  # Non-hub connector — medium green
    3: (0.369, 0.435, 0.122),  # Non-hub kinless node — dark green
    4: (0.2, 0.729, 0.949),    # Provincial hub — light blue
    5: (0.078, 0.424, 0.835),  # Connector hub — medium blue
    6: (0.016, 0.235, 0.498),  # Kinless hub — dark blue
}
_CARTOGRAPHY_LABELS = {
    1: "Peripheral node", 2: "Non-hub connector", 3: "Non-hub kinless node",
    4: "Provincial hub", 5: "Connector hub", 6: "Kinless hub",
}


def _matlab_images_dir() -> Path:
    """MATLAB's ``Images`` folder: in the repo, or bundled inside the desktop app."""
    from meanap.frozen import bundle_dir

    bundled = bundle_dir()
    if bundled is not None:
        return bundled / "matlab" / "Images"
    return Path(__file__).resolve().parents[3] / "matlab" / "Images"


def _cartography_diagram_path() -> str | None:
    """The picture of the six roles (legend and schematic), or ``None`` if missing.

    ``NodeCartography.m`` shows ``NodeCartographyDiagram.jpg`` under its
    scatter; without it the plot draws a plain key instead.
    """
    for p in (Path(__file__).resolve().parent / "assets" / "NodeCartographyDiagram.jpg",
              _matlab_images_dir() / "NodeCartographyDiagram.jpg"):
        if p.exists():
            return str(p)
    return None


def plot_node_cartography(
    pc: np.ndarray, z: np.ndarray, params: Params,
    lag_ms: float, recording_name: str, out_path: Path,
    boundaries: tuple | None = None,
    nd_cart_div: np.ndarray | None = None,
    names: list | None = None,
    noun: str = "electrode",
) -> None:
    """Node cartography scatter, port of the top panel of ``NodeCartography.m``
    (participation coefficient vs. within-module degree z-score, colored by
    role, with the 5 decision-boundary lines).

    ``boundaries`` — ``(hub, peri, non_hub_connector, pro_hub, connector_hub)`` —
    overrides the fixed ``Params`` thresholds; with MATLAB's default
    ``autoSetCartographyBoundaries``/``boundarySelectionMethod='kmeans'`` these
    are the data-driven k-means boundaries. ``nd_cart_div`` supplies the
    pre-computed per-node roles so the scatter colours match the CSVs / circular
    cartography plot exactly. Both fall back to fixed thresholds / re-derivation
    when omitted (i.e. when auto boundary selection is off).

    The bottom panel is MATLAB's static reference picture of the six roles
    (``NodeCartographyDiagram.jpg``), which doubles as the key. *names* and
    *noun* say what each node is, for whoever points at one.
    """
    if boundaries is not None:
        hub_boundary, peri, non_hub_connector, pro_hub, connector_hub = boundaries
    else:
        hub_boundary = params.hub_boundary_wm_d_deg
        peri = params.peri_part_coef
        non_hub_connector = params.non_hub_connector_part_coef
        pro_hub = params.pro_hub_part_coef
        connector_hub = params.connector_hub_part_coef

    if nd_cart_div is None:
        nd_cart_div, _ = classify_node_cartography(
            pc, z, hub_boundary, peri, non_hub_connector, pro_hub, connector_hub,
        )
    else:
        nd_cart_div = np.asarray(nd_cart_div)

    from meanap.native import output
    from meanap.native.cartography_paint import CartographyPainter
    from meanap.native.scene import cartography_scene

    scene = cartography_scene(
        pc, z, nd_cart_div,
        (hub_boundary, peri, non_hub_connector, pro_hub, connector_hub),
        title=_std_title(recording_name, lag_ms),
        roles={r: (_CARTOGRAPHY_LABELS[r], _CARTOGRAPHY_COLORS[r]) for r in range(1, 7)},
        names=names, noun=noun, diagram=_cartography_diagram_path())
    painter = CartographyPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("cartography", scene, painter))


# ── Plasma colormap helper ────────────────────────────────────────────────────

def _plasma_256() -> np.ndarray:
    """Return the 256×3 plasma colormap array (RGB, float 0-1)."""
    import matplotlib
    cmap = matplotlib.colormaps["plasma"].resampled(256)
    return cmap(np.linspace(0, 1, 256))[:, :3]


# ── Circular-arc geometry ─────────────────────────────────────────────────────

def _arc_points(
    t_a: float, t_b: float, n_pts: int = 100
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the circular-arc chord between two points on the unit circle.

    Direct Python translation of the Möbius-inversion geometry used in
    ``StandardisedNetworkPlotNodeColourMap.m`` (lines 162-239) for the
    'circular' plot type.  Given angles ``t_a`` and ``t_b``, the unique
    circle that is orthogonal to the unit circle and passes through both
    ``(cos t_a, sin t_a)`` and ``(cos t_b, sin t_b)`` is computed; the
    arc is always drawn inside the unit disk.

    A tiny epsilon nudge is applied when a coordinate component rounds to
    zero (matches MATLAB's own 0.001 nudge to avoid division-by-zero).

    Returns
    -------
    x, y : arrays of length ``n_pts``
    """
    eps = 0.001

    def _nudge(val: float, prev_val: float) -> float:
        if round(val, 3) == 0.0:
            return eps if prev_val > 0 else -eps
        return val

    u = np.array([np.cos(t_a), np.sin(t_a)])
    v = np.array([np.cos(t_b), np.sin(t_b)])

    u[0] = _nudge(u[0], np.cos(t_a - 0.01))
    u[1] = _nudge(u[1], np.sin(t_a - 0.01))
    v[0] = _nudge(v[0], np.cos(t_b - 0.01))
    v[1] = _nudge(v[1], np.sin(t_b - 0.01))

    # Degenerate case: shared coordinate magnitude → nudge (MATLAB L218-223)
    if round(abs(u[0]), 4) == round(abs(v[0]), 4):
        u[0] += 0.0001
    if round(abs(u[1]), 4) == round(abs(v[1]), 4):
        u[1] += 0.0001

    # Centre (x0, y0) and radius r of the orthogonal arc circle (MATLAB L225-227)
    denom = u[0] * v[1] - u[1] * v[0]
    if abs(denom) < 1e-12:
        return np.array([u[0], v[0]]), np.array([u[1], v[1]])

    x0 = -(u[1] - v[1]) / denom
    y0 = (u[0] - v[0]) / denom
    r = np.sqrt(max(x0 ** 2 + y0 ** 2 - 1.0, 0.0))

    theta_a = np.arctan2(u[1] - y0, u[0] - x0)
    theta_b = np.arctan2(v[1] - y0, v[0] - x0)

    # Arc stays inside unit disk (MATLAB L231-237)
    if u[0] >= 0 and v[0] >= 0:
        theta = np.concatenate([
            np.linspace(max(theta_a, theta_b), np.pi, n_pts // 2),
            np.linspace(-np.pi, min(theta_a, theta_b), n_pts // 2),
        ])
    else:
        theta = np.linspace(theta_a, theta_b, n_pts)

    return r * np.cos(theta) + x0, r * np.sin(theta) + y0


# ── Public plot function ──────────────────────────────────────────────────────

def plot_circular_module_network(
    adj_m_sub: np.ndarray,
    ci: np.ndarray,
    nd: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    edge_thresh: float = 0.0,
    names: list | None = None,
    noun: str = "node",
) -> None:
    """Circular network plot with nodes colored by module (Ci) and sized by
    node degree (ND).

    Port of ``StandardisedNetworkPlotNodeColourMap.m`` with
    ``plotType='circular'`` and ``z2name='Module'``.  Nodes are arranged
    at equal angles around a unit circle in index order
    (``t = linspace(-pi, pi, N+1)``), exactly as MATLAB does.  Edges are
    circular-arc chords drawn weakest-first so stronger edges appear on
    top.  The legend shows three node-degree reference circles, three
    edge-weight line samples, and coloured module swatches with integer
    labels — matching MATLAB's legend layout.

    Parameters
    ----------
    adj_m_sub : (N, N) active-node adjacency matrix
    ci        : (N,) integer module assignments (1-indexed, from
                ``mod_consensus_cluster_iterate``)
    nd        : (N,) node degree for each active node
    lag_ms    : lag in milliseconds (display only)
    recording_name : recording filename (display only)
    out_path  : full path for the saved PNG
    edge_thresh : minimum edge weight to draw (default 0 = all edges)
    """
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter
    from meanap.native.scene import circular_scene

    n = adj_m_sub.shape[0]
    if n == 0:
        return
    plasma = _plasma_256()
    nd = np.asarray(nd, dtype=float)
    modules = np.asarray(ci, dtype=float)
    present = np.unique(modules[~np.isnan(modules)])
    present = present[present > 0]
    low = float(present.min()) if present.size else 1.0
    high = float(present.max()) if present.size else 1.0
    if high == low:
        high = low + 1.0

    def module_colour(module: float) -> np.ndarray:
        frac = (module - low) / (high - low)
        index = max(int(np.ceil(len(plasma) * frac)) - 1, 0)
        return plasma[min(index, len(plasma) - 1)]

    # The busiest node is as wide as the gap between neighbours on the circle.
    t = np.linspace(-np.pi, np.pi, n + 1)
    spacing = float(np.hypot(np.cos(t[0]) - np.cos(t[1]), np.sin(t[0]) - np.sin(t[1])))
    top = float(np.nanmax(nd)) if np.any(nd > 0) else 1.0
    scale = top / spacing if spacing > 0 else top
    diameter = np.where(nd > 0, np.maximum(0.02, np.nan_to_num(nd) / scale), 0.0)
    samples = [top * f for f in (1 / 3, 2 / 3, 1.0)]
    whole = int(round(samples[0])) >= 1
    size_items = [(f"{int(round(v))}" if whole else f"{v:.4f}", max(v / scale, 0.02))
                  for v in samples]
    colour = np.array([module_colour(m) if (not np.isnan(m) and m > 0) else plasma[0]
                       for m in modules])
    text = [f"node degree: {nd[i]:.4g}"
            + (f"\nmodule: {int(modules[i])}" if not np.isnan(modules[i]) else "")
            for i in range(n)]
    scene = circular_scene(
        adj_m_sub, colour, diameter, text, title=_std_title(recording_name, lag_ms),
        edge_thresh=edge_thresh, size_name="node degree", size_items=size_items,
        category_key={"name": "module",
                      "items": [(str(int(m)), tuple(module_colour(m))) for m in present]},
        names=names, noun=noun)
    painter = NetworkPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("circular", scene, painter))


def plot_circular_cartography_network(
    adj_m_sub: np.ndarray,
    nd_cart_div: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    edge_thresh: float = 0.0,
    names: list | None = None,
    noun: str = "node",
) -> None:
    """Circular network plot with nodes colored by cartography role.

    Port of ``StandardisedNetworkPlotNodeCartography.m`` with
    ``plotType='circular'``.
    """
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter
    from meanap.native.scene import circular_scene

    n = adj_m_sub.shape[0]
    if n == 0:
        return
    # Every node the same size: two thirds of the gap between neighbours.
    t = np.linspace(-np.pi, np.pi, n + 1)
    spacing = (float(np.hypot(np.cos(t[0]) - np.cos(t[1]), np.sin(t[0]) - np.sin(t[1])))
               if n > 1 else 0.1)
    roles = np.asarray(nd_cart_div)
    colour = np.array([_CARTOGRAPHY_COLORS.get(_role(r), (0.5, 0.5, 0.5)) for r in roles])
    text = [f"role: {_CARTOGRAPHY_LABELS.get(_role(r), 'not classified')}" for r in roles]
    scene = circular_scene(
        adj_m_sub, colour, np.full(n, (2.0 / 3.0) * spacing), text,
        title=_std_title(recording_name, lag_ms), edge_thresh=edge_thresh,
        category_key={"name": "cartography role",
                      "items": [(_CARTOGRAPHY_LABELS[r], _CARTOGRAPHY_COLORS[r])
                                for r in range(1, 7)]},
        names=names, noun=noun)
    painter = NetworkPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("circular", scene, painter))


def _role(value):
    """A cartography role as the integer the colour and label tables are keyed by."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _half_violin(
    ax: "plt.Axes",
    data: np.ndarray,
    pos: float = 1.0,
    colour: tuple = (0.3, 0.3, 0.3),
    width: float = 1.0,
    rng: np.random.Generator | None = None,
    gap: float = 0.1,
    mean_colour: tuple | str = "black",
    limits: tuple[float | None, float | None] | None = None,
) -> None:
    """Draw a half-violin plot on *ax*, mirroring ``HalfViolinPlot.m``.

    Port of ``HalfViolinPlot.m`` (author RCFeord, edited Tim Sit):
    - Right half: KDE curve filled rightward from ``pos``
    - Left half: jittered scatter dots at ``pos - width … pos``
    - Mean dot (large black) + SEM bar at ``pos``

    Uses scipy Gaussian KDE with Silverman's rule (MATLAB ``ksdensity``
    default) and a minimum bandwidth of 10% of the data range, matching
    the ``min_bandwidth`` guard in ``HalfViolinPlot.m``.

    The drawing spans ``pos ± (width + gap)``. ``gap`` is the dead space either
    side of ``pos``; MATLAB hard-codes 0.1, which is right for one violin per x
    position but too wide once several are packed into the same slot — hence
    the parameter. ``mean_colour`` defaults to black, as MATLAB draws it; pass a
    colour when the violins at one position are distinguished *by* colour, so
    the mean marker doesn't read as belonging to a different series.

    The density is evaluated over the data range widened by three bandwidths
    each side — MATLAB ``ksdensity``'s default grid — so it tails off rather
    than stopping dead at the most extreme value. ``limits`` is the metric's
    theoretical ``(lo, hi)`` (:func:`~meanap.pipeline.metric_limits.metric_limits`;
    ``None`` on a side for unbounded): the tails are cut there, so a correlation
    violin never runs past 1. MATLAB has no such cut. A limit the data itself
    crosses is not a limit, and is ignored rather than allowed to hide data.
    """
    from scipy.stats import gaussian_kde

    if rng is None:
        rng = np.random.default_rng()

    data = np.asarray(data, dtype=float)
    data = data[np.isfinite(data)]
    if len(data) == 0:
        return

    # ── KDE ──────────────────────────────────────────────────────────────────
    if len(data) > 1 and np.std(data) > 1e-8:
        kde = gaussian_kde(data, bw_method="silverman")
        min_bw = (data.max() - data.min()) * 0.1
        # Enforce minimum bandwidth (same guard as MATLAB line 47-48)
        if kde.factor * np.std(data) < min_bw:
            kde = gaussian_kde(data, bw_method=min_bw / np.std(data))
        bw = float(np.sqrt(kde.covariance[0, 0]))
        lo, hi = data.min() - 3 * bw, data.max() + 3 * bw
        if limits is not None:
            if limits[0] is not None:
                lo = max(lo, min(limits[0], data.min()))
            if limits[1] is not None:
                hi = min(hi, max(limits[1], data.max()))
        xi = np.linspace(lo, hi, 256)
        f = kde(xi)
    else:
        # Single unique value or zero variance — tiny spike
        xi = np.array([data.mean()])
        f = np.array([1.0])

    # Scale width: widthFactor = width / max(f)  (MATLAB line 69)
    width_factor = width / max(f.max(), 1e-12)
    # KDE fills to the RIGHT of pos (MATLAB: fill(f*widthFactor + pos + 0.1, xi, colour))
    kde_x = f * width_factor + pos + gap
    ax.fill_betweenx(xi, pos + gap, kde_x, color=colour, linewidth=1,
                     edgecolor=colour)

    # ── Jittered scatter ─────────────────────────────────────────────────────
    jitter = rng.random(len(data)) * width
    drops_x = jitter + pos - (width + gap)  # MATLAB line 77
    ax.scatter(drops_x, data, s=20, color=colour, zorder=3)

    # ── Mean dot + SEM bar ───────────────────────────────────────────────────
    mean_val = float(np.mean(data))
    sem_val = float(np.std(data) / np.sqrt(len(data))) if len(data) > 1 else 0.0
    ax.scatter([pos], [mean_val], s=100, color=mean_colour, zorder=4,
               edgecolors="white", linewidths=0.8)
    ax.plot([pos, pos], [mean_val - sem_val, mean_val + sem_val],
            color=mean_colour, linewidth=3, zorder=4,
            solid_capstyle="round")


# ── Group-comparison half-violin (port of plotHalfViolinByX.m) ────────────────

# MATLAB default group palette (AdvancedSettings.m Params.groupColors)
_GROUP_COLORS = [
    (0.996, 0.670, 0.318),
    (0.780, 0.114, 0.114),
    (0.459, 0.000, 0.376),
    (0.027, 0.306, 0.659),
    (0.5, 0.5, 0.5),
]


def _div_colors(n: int, colors=None) -> list:
    """Per-DIV colours. Default ``flipud(viridis(n))`` (plotHalfViolinByX.m:16).

    ``flipud`` puts the bright (yellow) end at the first DIV. *colors* is a
    :class:`~meanap.pipeline.palette.ColorScheme`; omitting it keeps the
    historical palette exactly.
    """
    from meanap.pipeline.palette import DEFAULT_SCHEME

    return (colors or DEFAULT_SCHEME).ages(n)


def _group_colors(n: int, colors=None) -> list:
    """Per-group colours, by default cycling MATLAB's ``groupColors``."""
    from meanap.pipeline.palette import DEFAULT_SCHEME

    return (colors or DEFAULT_SCHEME).groups(n)


def _tick_label(v) -> str:
    """Tidy axis-tick text: render whole-number DIVs as ints ("14" not "14.0")."""
    s = str(v)
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s


def plot_half_violin_by_x(
    df: "pd.DataFrame",
    metric: str,
    metric_label: str,
    x_kind: str,
    out_path: Path,
    group_order: list | None = None,
    div_order: list | None = None,
    kde_height: float = 0.3,
    series_col: str | None = None,
    series_order: list | None = None,
    series_colors: list | None = None,
    colors=None,
    ylim: tuple[float | None, float | None] | None = None,
    age_title_sep: str = " ",
    kde_limits: tuple[float | None, float | None] | None | str = "auto",
    max_nodes: int | None = None,
    node_noun: str = "node",
) -> None:
    """Group-comparison half-violin plot, port of ``plotHalfViolinByX.m``.

    ``colors`` is a :class:`~meanap.pipeline.palette.ColorScheme` choosing the
    age and group palettes; omitting it keeps the pipeline's historical ones.

    ``x_kind='group'``  → one subplot per group, x-axis = DIVs (viridis-coloured),
    title = group name, xlabel "Age".
    ``x_kind='DIV'``    → one subplot per DIV, x-axis = groups (group-coloured),
    title = "Age <div>", xlabel "Group".

    Each cell is drawn with :func:`_half_violin` (KDE right-fill + jittered
    scatter left + black mean dot + SEM bar), matching ``HalfViolinPlot.m``.
    Requires ``df`` to carry ``Grp`` and ``DIV`` columns plus ``metric``.

    When the metric has no finite values (e.g. a burst metric on a recording
    with no bursts), the plot is still written — empty axes with the usual
    titles/labels plus a centred note stating how many recordings had no data —
    so it pairs with MATLAB's placeholder output and tells the reader why it's
    blank.

    ``series_col`` adds a **third** factor: at every x position one violin is
    drawn per distinct value of that column, side by side, and colour switches
    from encoding the x position (where it is redundant with the axis anyway) to
    encoding the series, with a legend. CAT-NAP uses this to split each metric
    by cell type, so "excitatory vs inhibitory, per genotype, per age" is one
    figure rather than one file per cell type. Omitting it reproduces the
    original two-factor plot exactly.

    ``ylim`` pins the y-axis to the metric's feasible range — ``(0, 1)`` for a
    density, say — as MATLAB's ``networkLevelNetMetCustomBounds`` does. A
    ``None`` on either side leaves that end to the data, so ``(0, None)`` is
    "from zero, up to whatever this batch reaches". The axes share y, so this
    is one range for every panel. See :func:`netmet_bounds`.

    ``age_title_sep`` goes between "Age" and the DIV in the by-age panel
    titles. ``plotHalfViolinByX.m`` (step 4B) writes "Age 14";
    ``PlotEphysStats.m`` (step 2B) writes "Age14", so step 2 passes ``""``.

    ``kde_limits`` is where the violins' density tails are cut — see
    :func:`_half_violin`. ``"auto"`` looks *metric* up in
    :func:`~meanap.pipeline.metric_limits.metric_limits`; ``None`` cuts nowhere.
    It is deliberately separate from ``ylim``, which may be a display choice.
    ``max_nodes`` (the array's electrode count, when fixed) caps network size,
    degree and strength in that lookup.

    The file name is the caller's; :func:`comparison_figure_stem` builds the
    MATLAB one. *node_noun* is what a point is called at node level, for
    whoever points at one in the viewer.
    """
    from meanap.native import output
    from meanap.native.group_paint import ComparisonPainter
    from meanap.native.group_scene import comparison_scene

    if df.empty:
        return
    if isinstance(kde_limits, str):
        from meanap.pipeline.metric_limits import metric_limits
        kde_limits = metric_limits(metric, max_nodes)
    scene = comparison_scene(
        df, metric, netmet_axis_label(metric, metric_label), x_kind,
        group_order=group_order, div_order=div_order, kde_height=kde_height,
        series_col=series_col, series_order=series_order, series_colors=series_colors,
        colors=colors, ylim=ylim, age_title_sep=age_title_sep, kde_limits=kde_limits,
        node_noun=node_noun)
    if scene is None:
        return
    painter = ComparisonPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("comparison", scene, painter))


def _timescale_group_folder(value, timescale: str = "lag") -> str:
    """``('1000mslag', 'bin')`` → ``'Bin1000ms'``; the CAT-NAP group folders' naming.

    Used by the Python-only CAT-NAP comparison sets (cell-type subnetworks,
    cell tracking). The 4B folders MATLAB also writes use
    :func:`comparison_timescale_folder` instead.

    Accepts the value with or without a unit or suffix, which is what lets it
    read a ``Lag`` column written by any version.
    """
    return f"{timescale.capitalize()}{_lag_num(value)}ms"


def comparison_timescale_folder(value, timescale: str = "lag") -> str:
    """The per-lag sub-folder of the 4B comparison sets.

    ``'<lag>mslag'`` as ``PlotNetMet.m`` names it. A CAT-NAP correlation run
    (``timescale="bin"``) has no MATLAB counterpart and keeps ``'Bin<n>ms'``.
    """
    if timescale == "bin":
        return _timescale_group_folder(value, timescale)
    return f"{_lag_num(value)}mslag"


def comparison_figure_stem(n: int, label: str, suffix: str = "",
                           by_age: bool = False) -> str:
    """MATLAB's file stem for one group-comparison figure: ``<n>_<label>[_<suffix>]``.

    *n* is the metric's 1-based position in its list and *label* its display
    label, as in ``PlotEphysStats.m`` and ``PlotNetMet.m``. The label is
    cleaned the way ``PlotNetMet.m`` cleans it: TeX backslashes (here also the
    ``$`` of their matplotlib form) are dropped, ``>`` and ``<`` are spelled
    out, and in the by-age sections ``/`` becomes ``div``. None of these
    characters occur in the step-2 labels, so the same rule serves both steps.
    """
    name = label.replace("$", "").replace("\\", "")
    if by_age:
        name = name.replace("/", "div")
    name = name.replace(">", "greater than").replace("<", "less than")
    return f"{n}_{name}_{suffix}" if suffix else f"{n}_{name}"


def metric_number(metrics: dict, key: str) -> int:
    """1-based position of *key* in a metric dict, MATLAB's ``n``."""
    return list(metrics).index(key) + 1


def _lag_num(lag) -> int:
    """Extract the numeric lag (ms) from a lag key like ``'10mslag'`` or ``10``."""
    import re
    m = re.search(r"\d+", str(lag))
    return int(m.group()) if m else 0


# Node-cartography proportion colours/labels (plotNetMetNodeCartography.m c1-c6)
_NC_PROP_COLORS = [
    (0.800, 0.902, 0.310),  # peripheral nodes
    (0.580, 0.706, 0.278),  # non-hub connectors
    (0.369, 0.435, 0.122),  # non-hub kinless nodes
    (0.200, 0.729, 0.949),  # provincial hubs
    (0.078, 0.424, 0.835),  # connector hubs
    (0.016, 0.235, 0.498),  # kinless hubs
]
_NC_PROP_LABELS = [
    "proportion peripheral nodes",
    "proportion non-hub connectors",
    "proportion non-hub kinless nodes",
    "proportion provincial hubs",
    "proportion connector hubs",
    "proportion kinless hubs",
]


def _node_cartography_proportion_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """Pool node-cartography role counts by group, age, and lag.

    ``NCpn*`` is a proportion for one recording. Averaging it gives every
    recording equal weight; a stacked composition plot should instead pool
    nodes first. This mirrors the R workflow's ``count / sum(count)``.
    """
    import pandas as pd

    count_cols = [f"NCpn{i}count" for i in range(1, 7)]
    if df.empty or not all(col in df.columns for col in count_cols):
        return pd.DataFrame()
    long = df.melt(id_vars=["Grp", "DIV", "Lag"], value_vars=count_cols,
                   var_name="Role", value_name="Count")
    long["Count"] = pd.to_numeric(long["Count"], errors="coerce").fillna(0.0)
    long["Role"] = long["Role"].str.extract(r"NCpn(\d+)count")[0].astype(int)
    pooled = long.groupby(["Grp", "DIV", "Lag", "Role"], observed=True,
                          as_index=False)["Count"].sum()
    totals = pooled.groupby(["Grp", "DIV", "Lag"], observed=True)["Count"].transform("sum")
    pooled["Proportion"] = np.divide(
        pooled["Count"], totals, out=np.zeros(len(pooled), dtype=float), where=totals > 0,
    )
    return pooled


#: matplotlib's default lettering, which these figures were designed with.
_MPL_TEXT = dict(title_size=12, label_size=10, tick_size=9)


def _role_stack(cells: list, pooled: "pd.DataFrame", where: str) -> list:
    """The six role bars stacked at positions ``0..len(cells)-1``.

    *cells* are ``(label, rows)`` pairs: the pooled rows of one bar. Each role
    is one series, so pointing at it in the legend picks it out in every bar.
    """
    from meanap.native.chart import Bars, rgba

    bottom = np.zeros(len(cells), dtype=float)
    marks = []
    for role, (colour, label) in enumerate(zip(_NC_PROP_COLORS, _NC_PROP_LABELS), start=1):
        name = label.replace("proportion ", "")
        values, hover = [], []
        for cell, rows in cells:
            mine = rows[rows["Role"] == role]
            total = float(rows["Count"].sum())
            value = float(mine["Proportion"].sum())
            values.append(value)
            hover.append(f"{name}: {100 * value:.1f}% "
                         f"({int(mine['Count'].sum())} of {int(total)} nodes)\n{cell}{where}")
        values = np.asarray(values)
        marks.append(Bars(np.arange(len(cells)), values, width=0.8, base=bottom.copy(),
                          colour=rgba(colour), edge=rgba("white"), edge_width=0.5,
                          key=name, hover=hover))
        bottom += values
    return marks


def _role_legend():
    from meanap.native.chart import Legend, LegendItem, rgba

    names = [label.replace("proportion ", "") for label in _NC_PROP_LABELS]
    # Top of the stack first, as the eye meets the bars.
    return Legend([LegendItem(n, rgba(c), kind="box", key=n)
                   for n, c in reversed(list(zip(names, _NC_PROP_COLORS)))],
                  title="Node role", loc="right", size=8.5)


def plot_node_cartography_proportions(
    df: "pd.DataFrame", out_dir: Path, group_order: list | None = None,
    only: int | None = None, fmt: str = "png",
) -> list[Path]:
    """Draw R-style 100%-stacked cartography-role bars, one figure per lag.

    Each panel is one spreadsheet group (such as a cell type or genotype), with
    DIV on the x-axis. Unlike the existing line chart, the bars pool all nodes
    in each group/DIV/lag cell before calculating the six role proportions.
    """
    from meanap.native.chart import Chart, Panel
    from meanap.native.chart_paint import save_chart

    pooled = _node_cartography_proportion_frame(df)
    if pooled.empty:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = list(group_order) if group_order else sorted(pooled["Grp"].dropna().unique())

    def _divkey(d):
        try:
            return float(str(d).replace("DIV", ""))
        except ValueError:
            return str(d)

    ticks = [(v, f"{v:.1f}") for v in np.arange(0, 1.01, 0.2)]
    written: list[Path] = []
    for lag in sorted(pooled["Lag"].unique(), key=_lag_num):
        if only is not None and _lag_num(lag) != only:
            continue
        ldf = pooled[pooled["Lag"] == lag]
        divs = sorted(ldf["DIV"].dropna().unique(), key=_divkey)
        if not divs:
            continue
        panels = []
        for row, group in enumerate(groups):
            gdf = ldf[ldf["Grp"].astype(str) == str(group)]
            cells = [(f"age {_tick_label(div)}", gdf[gdf["DIV"].astype(str) == str(div)])
                     for div in divs]
            last = row == len(groups) - 1
            panels.append(Panel(
                cell=(row, 0), marks=_role_stack(cells, pooled, f", {group}"),
                title=str(group), ylabel="Proportion of nodes", ylim=(0, 1), yticks=ticks,
                xticks=[(k, _tick_label(div)) for k, div in enumerate(divs)],
                xlabels=last, xlabel="Age" if last else "", xlim=(-0.6, len(divs) - 0.4),
                grid="", zoom=(True, False), sharex="age", **_MPL_TEXT))
        chart = Chart(panels, size=(8.0, max(3.0, 3.0 * len(groups))),
                      grid=(len(groups), 1), legend=_role_legend())
        dest = out_dir / f"NodeCartographyProportionsByGenotype{_lag_num(lag)}mslag.{fmt}"
        written.append(save_chart(chart, dest))
    return written


def plot_node_cartography_proportions_by_age(
    df: "pd.DataFrame", out_dir: Path, group_order: list | None = None,
    only: int | None = None, fmt: str = "png",
) -> list[Path]:
    """Draw R-style role-composition bars faceted by age, one figure per lag.

    This is the complementary view to :func:`plot_node_cartography_proportions`:
    each panel is one DIV, groups are on the x-axis, and each bar is a 100%
    stack of the six node-cartography roles. It corresponds to the R workflow's
    second proportion plot (``facet_wrap(~ AgeDiv)``).
    """
    from meanap.native.chart import Chart, Panel
    from meanap.native.chart_paint import save_chart

    pooled = _node_cartography_proportion_frame(df)
    if pooled.empty:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = list(group_order) if group_order else sorted(pooled["Grp"].dropna().unique())

    def _divkey(d):
        try:
            return float(str(d).replace("DIV", ""))
        except ValueError:
            return str(d)

    ticks = [(v, f"{v:.1f}") for v in np.arange(0, 1.01, 0.2)]
    written: list[Path] = []
    for lag in sorted(pooled["Lag"].unique(), key=_lag_num):
        if only is not None and _lag_num(lag) != only:
            continue
        ldf = pooled[pooled["Lag"] == lag]
        divs = sorted(ldf["DIV"].dropna().unique(), key=_divkey)
        if not divs:
            continue
        panels = []
        for col, div in enumerate(divs):
            ddf = ldf[ldf["DIV"].astype(str) == str(div)]
            cells = [(str(group), ddf[ddf["Grp"].astype(str) == str(group)])
                     for group in groups]
            panels.append(Panel(
                cell=(0, col), marks=_role_stack(cells, pooled, f", age {_tick_label(div)}"),
                title=f"DIV {_tick_label(div)}", ylim=(0, 1), yticks=ticks,
                ylabel="Proportion of nodes" if col == 0 else "", ylabels=col == 0,
                xticks=[(k, str(group)) for k, group in enumerate(groups)],
                xtick_rotation=45, xlim=(-0.6, len(groups) - 0.4),
                grid="", zoom=(False, False), **_MPL_TEXT))
        chart = Chart(panels, size=(max(8.0, 3.2 * len(divs)), 5.5),
                      grid=(1, len(divs)), legend=_role_legend())
        dest = out_dir / f"NodeCartographyProportionsByAge{_lag_num(lag)}mslag.{fmt}"
        written.append(save_chart(chart, dest))
    return written


def plot_node_cartography_by_lag(
    df: "pd.DataFrame",
    out_dir: Path,
    group_order: list | None = None,
    only: int | None = None,
    fmt: str = "png",
) -> list[Path]:
    """Node-cartography role proportions vs DIV, port of ``plotNetMetNodeCartography.m``.

    One figure per STTC lag (``NodeCartography<lag>mslag.<fmt>``): a vertical
    stack of subplots (one per group), each overlaying the six role proportions
    (``NCpn1``-``NCpn6``) as lines vs DIV with mean ± SEM bands and a role
    legend. Requires ``df`` with ``Grp``/``DIV``/``Lag`` columns plus
    ``NCpn1``-``NCpn6``.

    ``only`` restricts the run to a single lag (in ms), for a viewer redrawing
    one figure. Returns the files written.
    """
    if df.empty:
        return []
    metrics = [f"NCpn{i}" for i in range(1, 7)]
    if not all(m in df.columns for m in metrics):
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    groups = list(group_order) if group_order else sorted(df["Grp"].dropna().unique())
    lags = sorted(df["Lag"].unique(), key=_lag_num)

    def _divkey(d):
        try:
            return float(str(d).replace("DIV", ""))
        except ValueError:
            return str(d)
    divs = sorted(df["DIV"].dropna().unique(), key=_divkey)

    from meanap.native import output
    from meanap.native.group_paint import LinePainter
    from meanap.native.group_scene import LineScene, LineSeries, line_panel, line_span, mean_sem

    for lag in lags:
        if only is not None and _lag_num(lag) != only:
            continue
        ldf = df[df["Lag"] == lag]
        panels = []
        for g in groups:
            gdf = ldf[ldf["Grp"].astype(str) == str(g)]
            series = []
            for mi, metric in enumerate(metrics):
                stats = [mean_sem(gdf[gdf["DIV"].astype(str) == str(d)][metric])
                         for d in divs]
                series.append(LineSeries(
                    label=_NC_PROP_LABELS[mi], colour=_NC_PROP_COLORS[mi],
                    means=np.array([m for m, _, _ in stats]),
                    sems=np.array([e for _, e, _ in stats]),
                    counts=np.array([c for _, _, c in stats])))
            panels.append(line_panel(str(g), series))
        # One y range for every group, as before (sharey).
        shared = line_span(panels)
        for panel in panels:
            panel.ylim = shared
        scene = LineScene(panels=panels, ticks=[_tick_label(d) for d in divs],
                          xlabel="Age", ylabel="node cartography",
                          x_format="age {}")
        dest = out_dir / f"NodeCartography{_lag_num(lag)}mslag.{fmt}"
        painter = LinePainter(scene)
        output.save(painter, dest, capture=output.NativeFigure("lines", scene, painter))
        written.append(dest)
    return written


def plot_density_landscape(
    pc: np.ndarray,
    z: np.ndarray,
    boundaries: tuple,
    out_path: Path,
) -> Path | None:
    """Pooled PC-vs-Z scatter with the k-means cartography boundaries drawn.

    Port of ``TrialLandscapeDensity.m``'s ``ZandPC_scatter_with_kmeans_boundaries``
    plot: every node's participation coefficient vs within-module z-score (open
    circles) with the horizontal z boundary, the two hub PC boundaries (above the
    z line) and the two non-hub PC boundaries (below it).
    """
    from meanap.native.chart import (Chart, Legend, LegendItem, Panel, Points, Rule,
                                     Segments, rgba)
    from meanap.native.chart_paint import save_chart

    pc = np.asarray(pc, dtype=float)
    z = np.asarray(z, dtype=float)
    mask = np.isfinite(pc) & np.isfinite(z)
    pc, z = pc[mask], z[mask]
    if pc.size == 0:
        return None
    z_boundary, peri, non_hub_connector, pro_hub, connector_hub = boundaries
    zmax = float(np.max(np.abs(z))) if z.size else 4.0

    grey = rgba("0.5")
    lines = [  # (x, from z, to z, colour, what it separates)
        (pro_hub, z_boundary, zmax, "#D95319", "provincial | connector hubs"),
        (connector_hub, z_boundary, zmax, "#EDB120", "connector | kinless hubs"),
        (peri, -zmax, z_boundary, "#7E2F8E", "peripheral | non-hub connectors"),
        (non_hub_connector, -zmax, z_boundary, "#77AC30", "non-hub connectors | kinless"),
    ]
    marks = [
        Points(pc, z, fill=rgba("none"), edge=rgba("#0072BD"), edge_width=1.0,
               size=float(np.sqrt(30)), key="nodes",
               hover=[f"PC {a:.3f}, Z {b:.2f}" for a, b in zip(pc, z)]),
        Rule(z_boundary, colour=grey, width=1.0, key="hub", z=3),
    ]
    items = [LegendItem(f"hub boundary, Z = {z_boundary:.2f}", grey, key="hub")]
    for x, low, high, colour, what in lines:
        marks.append(Segments([[x, low, x, high]], colour=rgba(colour), width=1.5, key=what,
                              z=3))
        items.append(LegendItem(f"{what}, PC = {x:.2f}", rgba(colour), key=what))
    panel = Panel(marks=marks, xlabel="Participation Coefficient (PC)",
                  ylabel="Within-module Z-score (Z)", grid="",
                  legend=Legend(items, loc="right", size=8), **_MPL_TEXT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return save_chart(Chart([panel], size=(9, 5)), out_path)


def plot_graph_metrics_by_lag(
    df: "pd.DataFrame",
    out_dir: Path,
    group_order: list | None = None,
    only: str | None = None,
    fmt: str = "png",
    colors=None,
    timescale: str = "lag",
) -> list[Path]:
    """Network metric vs. connectivity timescale, port of ``plotGraphMetricsByLag.m``.

    One figure per recording-level metric: a vertical stack of subplots (one per
    group), each plotting mean ± SEM across recordings as a function of the
    timescale the adjacency was built at,
    with one line per DIV (viridis-coloured, DIV1 = yellow end) and a DIV legend.

    ``timescale`` is ``"lag"`` (an STTC coincidence window) or ``"bin"`` (a
    CAT-NAP correlation bin), and only decides how the x axis is labelled — see
    :mod:`meanap.timescale`.
    Requires ``df`` with ``Grp``/``DIV``/``Lag`` columns plus the metric columns.
    Files are named ``<n>_<label>.<fmt>`` as MATLAB names them (see
    :func:`comparison_figure_stem`).

    ``only`` restricts the run to a single metric, for a viewer redrawing the
    one figure it is showing rather than all 31. Returns the files written.
    """
    if df.empty:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    groups = list(group_order) if group_order else sorted(df["Grp"].dropna().unique())
    lags = sorted(df["Lag"].unique(), key=_lag_num)
    lag_nums = [_lag_num(l) for l in lags]

    def _divkey(d):
        try:
            return float(str(d).replace("DIV", ""))
        except ValueError:
            return str(d)
    divs = sorted(df["DIV"].dropna().unique(), key=_divkey)
    div_colors = _div_colors(len(divs), colors)

    from meanap.native import output
    from meanap.native.group_paint import LinePainter
    from meanap.native.group_scene import LineScene, LineSeries, line_panel, mean_sem

    for n, (metric, label) in enumerate(NETMET_REC_METRICS.items(), start=1):
        if metric not in df.columns or (only is not None and metric != only):
            continue
        panels = []
        for g in groups:
            gdf = df[df["Grp"].astype(str) == str(g)]
            series = []
            for di, d in enumerate(divs):
                ddf = gdf[gdf["DIV"].astype(str) == str(d)]
                stats = [mean_sem(ddf[ddf["Lag"] == lag][metric]) for lag in lags]
                means = np.array([m for m, _, _ in stats])
                if np.all(np.isnan(means)):
                    continue
                series.append(LineSeries(
                    label=_tick_label(d), colour=tuple(div_colors[di]), means=means,
                    sems=np.array([e for _, e, _ in stats]),
                    counts=np.array([c for _, _, c in stats])))
            panels.append(line_panel(str(g), series))
        if not any(p.series for p in panels):
            continue
        scene = LineScene(
            panels=panels, ticks=[str(v) for v in lag_nums],
            xlabel="STTC lag (ms)" if timescale == "lag" else "Correlation bin (ms)",
            ylabel=netmet_axis_label(metric, label), legend_title="DIV",
            x_format="{} ms lag" if timescale == "lag" else "{} ms bins",
            series_noun="DIV")
        dest = out_dir / f"{comparison_figure_stem(n, label)}.{fmt}"
        painter = LinePainter(scene)
        output.save(painter, dest, capture=output.NativeFigure("lines", scene, painter))
        written.append(dest)
    return written


# ── Public plot function ──────────────────────────────────────────────────────

def plot_graph_metrics_by_node(
    nd: np.ndarray,
    mew: np.ndarray,
    ns: np.ndarray,
    z: np.ndarray | None,
    eloc: np.ndarray | None,
    pc: np.ndarray | None,
    bc: np.ndarray | None,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    images_dir: Path | None = None,
    rng: np.random.Generator | None = None,
    names: list | None = None,
    noun: str = "node",
) -> None:
    """Half-violin panel for all node-level graph metrics.

    Drawn by Qt (:mod:`meanap.native`). ``names`` and ``noun`` name the nodes
    for whoever points at one; they change nothing that is drawn.

    Port of ``electrodeSpecificMetrics.m``.  Layout mirrors MATLAB's 4×7
    ``tiledlayout``:

    - **Row 0**: schematic PNG icons (ND / EW / NS / WMZ / Eloc / PC / BC)
      loaded from ``images_dir`` (defaults to ``matlab/Images/`` in the repo
      relative to the package install).  Missing images are silently skipped.
    - **Rows 1–3**: half-violin plots (KDE + jitter + mean±SEM) for each metric.

    Parameters
    ----------
    nd, mew, ns : node degree, mean edge weight, node strength (always plotted)
    z    : within-module degree z-score (skipped if None / all-NaN)
    eloc : local efficiency (skipped if None / all-NaN / all-zero)
    pc   : participation coefficient (skipped if None / all-NaN)
    bc   : betweenness centrality (skipped if None / all-NaN)
    lag_ms : lag in milliseconds (title only)
    recording_name : recording filename (title only)
    out_path : where to save the PNG
    images_dir : directory containing ND.png, EW.png … BC.png; if None,
        the function looks for ``matlab/Images/`` three levels above this file
        (i.e. the MEA-NAP repo root).
    rng : optional seeded RNG (for reproducible jitter in tests)
    """
    from meanap.native import output
    from meanap.native.scene import ViolinScene, empty_violin_panel, violin_panel
    from meanap.native.violin_paint import ViolinPainter
    from meanap.pipeline.metric_limits import metric_limits

    if rng is None:
        rng = np.random.default_rng()
    if images_dir is None:
        images_dir = _matlab_images_dir()

    def top_of(d, floor):
        return (0, max(float(np.nanmax(d)), floor) * 1.2)

    def spread(d):
        lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
        return (0, hi + 0.1) if lo == hi else (lo - abs(lo) * 0.2, hi + abs(hi) * 0.2)

    def eloc_range(d):
        if len(np.unique(d)) == 1:
            return None                 # no spread: let the panel choose
        return (0, float(np.nanmax(d)) * 1.2)

    def from_zero(d):
        lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
        return (0, hi + 0.1) if lo == hi else (0, hi * 1.2)

    def plottable(values) -> bool:
        if values is None:
            return False
        finite = np.asarray(values, dtype=float)
        return int(np.isfinite(finite).sum()) > 1

    # (values, y label, limits key, picture, y range, drawn?) — in MATLAB's order.
    panels_spec = [
        (nd, "node degree", "ND", "ND.png", lambda d: top_of(d, 1.0), True),
        (mew, "mean edge weight", "MEW", "EW.png", lambda d: top_of(d, 0.1), True),
        (ns, "node strength", "NS", "NS.png", lambda d: top_of(d, 0.1), True),
        (z, "within-module degree z-score", "Z", "WMZ.png", spread, plottable(z)),
        (eloc, "local efficiency", "Eloc", "Eloc.png", eloc_range,
         plottable(eloc) and float(np.nanmax(eloc)) > 0),
        (pc, "participation coefficient", "PC", "PC.png",
         lambda d: (0, min(float(np.nanmax(d)) * 1.2, 1.0)), plottable(pc)),
        (bc, "betweenness centrality", "BC", "BC.png", from_zero, plottable(bc)),
    ]
    panels = []
    for data, label, key, picture, y_range, drawn in panels_spec:
        icon = str(images_dir / picture)
        panel = None
        if drawn and data is not None:
            values = np.asarray(data, dtype=float)
            finite = values[np.isfinite(values)]
            ylim = y_range(finite) if finite.size else None
            if ylim is not None and ylim[1] <= ylim[0]:
                ylim = None
            panel = violin_panel(values, label, rng, ylim=ylim, icon=icon,
                                 limits=metric_limits(key, max_nodes=len(values)))
        panels.append(panel or empty_violin_panel(label, icon=icon))

    count = len(np.asarray(nd).ravel())
    scene = ViolinScene(
        title=_std_title(recording_name, lag_ms), panels=panels,
        names=[str(i + 1) for i in range(count)] if names is None else [str(n) for n in names],
        noun=noun, colour=(0.3, 0.3, 0.3), width=1.0)
    painter = ViolinPainter(scene)
    output.save(painter, out_path, capture=output.NativeFigure("violin", scene, painter))


import pandas as pd

#: Recording-level network metrics and their labels, in MATLAB's order and
#: wording (``networkLevelNetMetLabels`` in ``AdvancedSettings.m``; the last two
#: from the GUI's ``NetMetLabelDict``). The label is the y label and, through
#: :func:`comparison_figure_stem`, the file name; the position is the file's
#: ``<n>``. MATLAB's TeX ``\sigma``/``\omega`` are written in matplotlib's form.
NETMET_REC_METRICS = {
    "aN": "network size",
    "Dens": "density",
    "CC": "clustering coefficient",
    "nMod": "number of modules",
    "Q": "modularity score",
    "PL": "mean path length",
    "Eglob": "global efficiency",
    "SW": r"small worldness $\sigma$",
    "SWw": r"small worldness $\omega$",
    "effRank": "Effective rank",
    "num_nnmf_components": "Num NMF components",
    "nComponentsRelNS": "nNMF div network size",
    "NDmean": "Node degree mean",
    "NDtop25": "Top 25% node degree",
    "sigEdgesMean": "Significant edge weight mean",
    "sigEdgesTop10": "Top 10% edge weight mean",
    "NSmean": "Node strength mean",
    "ElocMean": "Local efficiency mean",
    "PCmean": "Participant coefficient (PC) mean",  # sic, as MATLAB
    "PCmeanTop10": "Top 10% PC",
    "PCmeanBottom10": "Bottom 10% PC",
    "percentZscoreGreaterThanZero": "Percentage within-module z-score > 0",
    "percentZscoreLessThanZero": "Percentage within-module z-score < 0",
    "NCpn1": "NC1PeripheralNodes",
    "NCpn2": "NC2NonhubConnectors",
    "NCpn3": "NC3NonhubKinless",
    "NCpn4": "NC4ProvincialHubs",
    "NCpn5": "NC5ConnectorHubs",
    "NCpn6": "NC6KinlessHubs",
    "aveControlMean": "Mean average controllability",
    "modalControlMean": "Mean modal controllability",
    # Python only (spatiotemporal.py). Appended, so the MATLAB metrics above
    # keep their figure numbers.
    "SA_lambda": "spatial autocorrelation length",
    "SA_inf": "spatial autocorrelation floor",
    "TA_global": "mean temporal autocorrelation",
    "SA_lambda_free": "spatial autocorrelation length (free start)",
    "SA_amp": "spatial autocorrelation amplitude",
    "SA_inf_free": "spatial autocorrelation floor (free start)",
}

#: Node-level network metrics, as ``unitLevelNetMetLabels`` (the last two from
#: the GUI's ``NetMetLabelDict``).
NETMET_NODE_METRICS = {
    "ND": "node degree",
    "MEW": "edge weight",
    "NS": "node strength",
    "Z": "within-module degree z-score",
    "Eloc": "local efficiency",
    "PC": "participation coefficient",
    "BC": "betweenness centrality",
    "aveControl": "Average Controllability",
    "modalControl": "Modal Controllability",
    "TA_regional": "temporal autocorrelation",
}

#: Axis wording where it differs from the file-name label above. ``CC`` and
#: ``PL`` are the null-model-normalised values (``C/C_lattice`` and
#: ``PL/PL_random``), but their labels must stay MATLAB's because they name the
#: figure files.
_NETMET_AXIS_LABELS = {
    "CC": "clustering coefficient (normalised)",
    "PL": "mean path length (normalised)",
}


def netmet_axis_label(metric: str, label: str) -> str:
    """The text to show for *metric*; *label* remains what names its file."""
    return _NETMET_AXIS_LABELS.get(metric, label)


#: Display names for the Python-only figures that label network metrics —
#: step 5 and CAT-NAP cell tracking. Kept apart from the MATLAB labels above,
#: which are file names as much as labels, so those figures keep their
#: readable wording without one dict carrying two meanings.
NETMET_REC_DISPLAY_LABELS = {
    "aN": "Active Nodes",
    "Dens": "Density",
    "CC": "Clustering Coefficient (normalised)",
    "nMod": "Number of Modules",
    "Q": "Modularity (Q)",
    "PL": "Path Length (normalised)",
    "Eglob": "Global Efficiency",
    "SW": "Small-worldness (SW)",
    "SWw": "Small-worldness (SWw)",
    "effRank": "Effective Rank",
    "num_nnmf_components": "Num NNMF Components",
    "nComponentsRelNS": "NNMF Components / NS",
    "NDmean": "Mean Node Degree",
    "NDtop25": "Top 25% Node Degree",
    "sigEdgesMean": "Mean Significant Edge Weight",
    "sigEdgesTop10": "Top 10% Significant Edge Weight",
    "NSmean": "Mean Node Strength",
    "ElocMean": "Mean Local Efficiency",
    "PCmean": "Mean Participation Coefficient",
    "PCmeanTop10": "Top 10% Participation Coefficient",
    "PCmeanBottom10": "Bottom 10% Participation Coefficient",
    "percentZscoreGreaterThanZero": "Percent Z > 0",
    "percentZscoreLessThanZero": "Percent Z < 0",
    # Stored as a fraction of the active nodes (``pop_num_nc[i] / a_n``), so
    # "proportion", not "%": the axis runs 0-1.
    "NCpn1": "Proportion Peripheral Nodes (R1)",
    "NCpn2": "Proportion Non-hub Connectors (R2)",
    "NCpn3": "Proportion Non-hub Kinless Nodes (R3)",
    "NCpn4": "Proportion Provincial Hubs (R4)",
    "NCpn5": "Proportion Connector Hubs (R5)",
    "NCpn6": "Proportion Kinless Hubs (R6)",
    "aveControlMean": "Mean Average Controllability",
    "modalControlMean": "Mean Modal Controllability",
    # Shinn et al. (2023). SA-λ is in electrode pitches on an MEA and in
    # imaging pixels on CAT-NAP — the units each pipeline's positions are in.
    "SA_lambda": "Spatial Autocorrelation Length (SA-λ)",
    "SA_inf": "Spatial Autocorrelation Floor (SA-∞)",
    "TA_global": "Mean Temporal Autocorrelation (TA-Δ₁)",
    "SA_lambda_free": "Spatial Autocorrelation Length, Free Start",
    "SA_amp": "Spatial Autocorrelation Amplitude",
    "SA_inf_free": "Spatial Autocorrelation Floor, Free Start",
}

NETMET_NODE_DISPLAY_LABELS = {
    "ND": "Node Degree",
    "MEW": "Mean Edge Weight",
    "NS": "Node Strength",
    "Z": "Within-Module Degree Z-Score",
    "Eloc": "Local Efficiency",
    "PC": "Participation Coefficient",
    "BC": "Betweenness Centrality",
    "aveControl": "Average Controllability",
    "modalControl": "Modal Controllability",
    "TA_regional": "Temporal Autocorrelation (TA-Δ₁)",
}

# ── Feasible y-axis ranges for the comparison violins ────────────────────────
#
# Port of ``Params.networkLevelNetMetCustomBounds`` (getParamsFromApp.m), which
# ``plotHalfViolinByX.m`` applies to every half-violin so that a bounded metric
# is drawn on the range it *can* take rather than the range this batch happened
# to fill — density on [0, 1], a participation coefficient on [0, 1]. ``None``
# on a side is MATLAB's ``nan``: let the data decide.
#
# Beyond MATLAB's table: the cartography role proportions and the two z-score
# percentages, which are fractions and percentages by construction. And two
# repairs — MATLAB keys the edge-weight bound as ``EW`` while the metric is
# ``MEW``, so it never fired there; and node degree is capped by the largest
# network in the batch (see :func:`netmet_bounds`) rather than the electrode
# layout, which a CAT-NAP run of cells does not have.
NETMET_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    # Recording level
    "Dens": (0, 1),
    "effRank": (1, None),
    "num_nnmf_components": (1, None),
    "nComponentsRelNS": (0, 1),
    "NDmean": (0, None),
    "NDtop25": (0, None),
    "sigEdgesMean": (0, None),
    "sigEdgesTop10": (0, None),
    "NSmean": (0, None),
    "ElocMean": (0, 1),
    "PCmean": (0, 1),
    "PCmeanTop10": (0, 1),
    "PCmeanBottom10": (0, 1),
    "CC": (0, None),
    "nMod": (0, None),
    "Q": (0, None),
    "PL": (0, None),
    "Eglob": (0, 1),
    "percentZscoreGreaterThanZero": (0, 100),
    "percentZscoreLessThanZero": (0, 100),
    "NCpn1": (0, 1),
    "NCpn2": (0, 1),
    "NCpn3": (0, 1),
    "NCpn4": (0, 1),
    "NCpn5": (0, 1),
    "NCpn6": (0, 1),
    "SA_lambda": (0, None),
    "SA_inf": (-1, 1),
    "TA_global": (-1, 1),
    "SA_lambda_free": (0, None),
    "SA_amp": (0, None),
    "SA_inf_free": (-1, 1),
    # Node level
    "ND": (0, None),
    "MEW": (0, 1),
    "NS": (0, None),
    "Eloc": (0, 1),
    "TA_regional": (-1, 1),
    "BC": (0, 1),
    "PC": (0, 1),
    "aveControl": (1, 1.5),
    "modalControl": (0.6, 1),
}


def netmet_bounds(metric: str, n_nodes: int | None = None) -> tuple[float | None, float | None] | None:
    """The y-range *metric*'s comparison violins are drawn on, or ``None``.

    ``n_nodes`` is the node count of the largest network in the batch — from
    :func:`batch_node_count` — and caps node degree at ``n_nodes - 1``, the most
    neighbours any node there could have. Without it the cap is left to the data.
    """
    bounds = NETMET_BOUNDS.get(metric)
    if bounds is None:
        return None
    if metric == "ND" and n_nodes is not None and n_nodes > 1:
        return (bounds[0], n_nodes - 1)
    return bounds


def batch_node_count(df_node: "pd.DataFrame") -> int | None:
    """The node count of the largest network in a node-level frame, or ``None``."""
    if df_node is None or df_node.empty or "Channel" not in df_node.columns:
        return None
    n = df_node["Channel"].max()
    return int(n) if np.isfinite(n) else None

def netmet_comparison_frames(
    recordings: list,
    all_results: dict,
    custom_grp_order: list[str] | None = None,
) -> tuple["pd.DataFrame", "pd.DataFrame"]:
    """The recording- and node-level tables every 4B comparison plot is drawn from.

    One row per (recording, lag) at the recording level, and per
    (recording, lag, channel) at the node level, carrying ``FileName``/``Grp``/
    ``DIV``/``Lag`` plus whichever of :data:`NETMET_REC_METRICS` /
    :data:`NETMET_NODE_METRICS` the results hold.

    Separated from :func:`plot_step4_group_comparisons` so a caller can draw
    *one* comparison figure — the viewer redraws a single metric at a single lag
    on demand, and rebuilding these frames is the only part of that work it
    cannot skip. Both callers share this function, so a figure drawn one at a
    time cannot drift from the same figure drawn as part of the folder.

    Returns empty frames when nothing matched, rather than raising.
    """
    rec_rows = []
    node_rows = []

    for rec in recordings:
        if rec.filename not in all_results:
            continue

        rec_results = all_results[rec.filename]
        for lag, metrics in rec_results.items():
            base = {"FileName": rec.filename, "Grp": rec.group, "DIV": str(rec.div), "Lag": lag}

            # Recording-level
            rec_row = dict(base)
            for k in NETMET_REC_METRICS:
                if k in metrics:
                    val = metrics[k]
                    if isinstance(val, (list, np.ndarray)) and np.size(val) <= 1:
                        val = val[0] if np.size(val) == 1 else val
                    if not isinstance(val, (list, np.ndarray)):
                        rec_row[k] = val
            # Counts support pooled cartography-composition bars; they are not
            # regular metrics and intentionally stay out of the violin plots.
            for i in range(1, 7):
                key = f"NCpn{i}count"
                if key in metrics and np.isscalar(metrics[key]):
                    rec_row[key] = metrics[key]
            rec_rows.append(rec_row)

            # Node-level
            # Determine number of nodes from one of the arrays (e.g. ND)
            node_metrics = {k: v for k, v in metrics.items() if k in NETMET_NODE_METRICS and isinstance(v, (list, np.ndarray)) and len(v) > 1}
            if node_metrics:
                num_nodes = len(next(iter(node_metrics.values())))
                for ch in range(num_nodes):
                    node_row = dict(base)
                    node_row["Channel"] = ch + 1
                    for k, v_arr in node_metrics.items():
                        if len(v_arr) == num_nodes:
                            node_row[k] = v_arr[ch]
                    node_rows.append(node_row)

    df_rec = pd.DataFrame(rec_rows)
    df_node = pd.DataFrame(node_rows)
    _apply_group_order(df_rec, df_node, custom_grp_order)
    return df_rec, df_node


def _apply_group_order(df_rec, df_node, custom_grp_order: list[str] | None) -> None:
    """Make ``Grp`` an ordered categorical in place, so plots honour the order.

    The ``Grp in columns`` guard matters for the node frame: a batch whose
    recordings all have a single node produces no node rows at all, and a
    column assignment on that empty frame is a ``KeyError`` rather than a
    no-op.
    """
    if not custom_grp_order:
        return
    for df in (df_rec, df_node):
        if "Grp" in df.columns:
            df["Grp"] = pd.Categorical(df["Grp"], categories=custom_grp_order, ordered=True)


def plot_step4_group_comparisons(
    recordings: list,
    all_results: dict,
    out_dir: Path,
    custom_grp_order: list[str] | None = None,
    fmt: str = "png",
    colors=None,
    timescale: str = "lag",
    n_electrodes: int | None = None,
) -> None:
    """Generate group comparison plots for step 4.

    ``n_electrodes`` is the array's electrode count when it is fixed
    (:func:`~meanap.pipeline.channel_layout.fixed_electrode_count`); it caps
    the violins of network size, degree and strength.

    ``colors`` is a :class:`~meanap.pipeline.palette.ColorScheme` for the age
    and group palettes; omitting it keeps the historical ones.

    ``timescale`` names what the ``Lag`` column holds, and so what the per-lag
    folders are called: ``"lag"`` (STTC) or ``"bin"`` (a CAT-NAP correlation
    run — see :mod:`meanap.timescale`). It defaults to ``"lag"`` because that
    is what every ephys run is.
    """
    df_rec, df_node = netmet_comparison_frames(recordings, all_results, custom_grp_order)
    if df_rec.empty:
        return
    n_nodes = batch_node_count(df_node)

    # 3_RecordingsByGroup and 1_NodeByGroup
    grp_dir = out_dir / "4B_GroupComparisons" / "3_RecordingsByGroup" / "HalfViolinPlots"
    node_grp_dir = out_dir / "4B_GroupComparisons" / "1_NodeByGroup"
    
    # Loop over lags. File names follow PlotNetMet.m: "<n>_<label>_byGroup"
    # and "<n>_<label>_byAge", recording and node level alike.
    for lag in df_rec["Lag"].unique():
        lag_grp_dir = grp_dir / comparison_timescale_folder(lag, timescale)
        lag_grp_dir.mkdir(parents=True, exist_ok=True)

        df_rec_lag = df_rec[df_rec["Lag"] == lag]
        for n, (k, name) in enumerate(NETMET_REC_METRICS.items(), start=1):
            plot_half_violin_by_x(df_rec_lag, k, name, "group",
                                  lag_grp_dir / f"{comparison_figure_stem(n, name, 'byGroup')}.{fmt}",
                                  group_order=custom_grp_order, colors=colors,
                                  ylim=netmet_bounds(k, n_nodes),
                                  max_nodes=n_electrodes)

        lag_node_grp_dir = node_grp_dir / comparison_timescale_folder(lag, timescale)
        lag_node_grp_dir.mkdir(parents=True, exist_ok=True)

        df_node_lag = df_node[df_node["Lag"] == lag]
        for n, (k, name) in enumerate(NETMET_NODE_METRICS.items(), start=1):
            plot_half_violin_by_x(df_node_lag, k, name, "group",
                                  lag_node_grp_dir / f"{comparison_figure_stem(n, name, 'byGroup')}.{fmt}",
                                  group_order=custom_grp_order, colors=colors,
                                  ylim=netmet_bounds(k, n_nodes),
                                  max_nodes=n_electrodes)

    # 4_RecordingsByAge and 2_NodeByAge
    age_dir = out_dir / "4B_GroupComparisons" / "4_RecordingsByAge" / "HalfViolinPlots"
    node_age_dir = out_dir / "4B_GroupComparisons" / "2_NodeByAge"

    for lag in df_rec["Lag"].unique():

        lag_age_dir = age_dir / comparison_timescale_folder(lag, timescale)
        lag_age_dir.mkdir(parents=True, exist_ok=True)

        df_rec_lag = df_rec[df_rec["Lag"] == lag]
        for n, (k, name) in enumerate(NETMET_REC_METRICS.items(), start=1):
            stem = comparison_figure_stem(n, name, "byAge", by_age=True)
            plot_half_violin_by_x(df_rec_lag, k, name, "DIV",
                                  lag_age_dir / f"{stem}.{fmt}",
                                  group_order=custom_grp_order, colors=colors,
                                  ylim=netmet_bounds(k, n_nodes),
                                  max_nodes=n_electrodes)

        lag_node_age_dir = node_age_dir / comparison_timescale_folder(lag, timescale)
        lag_node_age_dir.mkdir(parents=True, exist_ok=True)

        df_node_lag = df_node[df_node["Lag"] == lag]
        for n, (k, name) in enumerate(NETMET_NODE_METRICS.items(), start=1):
            # PlotNetMet.m does not apply the "/" → "div" rule at node level.
            plot_half_violin_by_x(df_node_lag, k, name, "DIV",
                                  lag_node_age_dir / f"{comparison_figure_stem(n, name, 'byAge')}.{fmt}",
                                  group_order=custom_grp_order, colors=colors,
                                  ylim=netmet_bounds(k, n_nodes),
                                  max_nodes=n_electrodes)

    # 5_GraphMetricsByLag — network metric vs. timescale, one figure per metric
    gmbl_dir = out_dir / "4B_GroupComparisons" / "5_GraphMetricsByLag"
    plot_graph_metrics_by_lag(df_rec, gmbl_dir, group_order=custom_grp_order,
                              fmt=fmt, colors=colors, timescale=timescale)

    # 6_NodeCartographyByLag — role proportions vs DIV, one figure per lag
    ncbl_dir = out_dir / "4B_GroupComparisons" / "6_NodeCartographyByLag"
    plot_node_cartography_by_lag(df_rec, ncbl_dir, group_order=custom_grp_order, fmt=fmt)
    plot_node_cartography_proportions(df_rec, ncbl_dir, group_order=custom_grp_order, fmt=fmt)
    plot_node_cartography_proportions_by_age(
        df_rec, ncbl_dir, group_order=custom_grp_order, fmt=fmt)


#: Display names for the raw metrics the spatiotemporal model is scored on —
#: ``CC_rawMean``/``PL_raw`` are not in :data:`NETMET_REC_METRICS`, whose
#: ``CC``/``PL`` are the null-normalised versions.
_ST_MODEL_LABELS = {
    "NDtop25": "Top 25% Node Degree",
    "CC_rawMean": "Clustering Coefficient (raw)",
    "PL_raw": "Path Length (raw)",
    "Eglob": "Global Efficiency",
    "ElocMean": "Mean Local Efficiency",
    "Q": "Modularity (Q)",
}


def plot_spatiotemporal_model(all_results: dict, lag_key: str, out_path: Path) -> bool:
    """Data against the spatiotemporal model, one panel per graph metric.

    One point per recording at lag *lag_key*. On the diagonal, the metric is
    what SA and TA alone predict; the panel title carries Lin's concordance
    (the paper's measure). Returns ``False``, drawing nothing, when no recording
    at this lag has model values.
    """
    from meanap.pipeline.spatiotemporal import MODEL_REC_METRICS, lins_concordance

    per_lag = [rec[lag_key] for rec in all_results.values() if lag_key in rec]
    panels = []
    for k in MODEL_REC_METRICS:
        pairs = [(m.get(k, np.nan), m[f"ST_{k}"]) for m in per_lag if f"ST_{k}" in m]
        if pairs:
            data, model = (np.asarray(v, dtype=float) for v in zip(*pairs))
            panels.append((k, data, model))
    if not panels:
        return False

    ink, muted, mark = "#222222", "#8a8a8a", "#3b6ea8"
    ncol = 3
    nrow = int(np.ceil(len(panels) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.4 * ncol, 3.3 * nrow), squeeze=False)
    for ax in axes.ravel()[len(panels):]:
        ax.set_visible(False)
    for ax, (k, data, model) in zip(axes.ravel(), panels):
        ok = np.isfinite(data) & np.isfinite(model)
        if ok.any():
            lo = float(min(data[ok].min(), model[ok].min()))
            hi = float(max(data[ok].max(), model[ok].max()))
            pad = (hi - lo) * 0.08 or 0.05 * (abs(hi) or 1.0)
            lims = (lo - pad, hi + pad)
            ax.plot(lims, lims, color=muted, lw=1, ls="--", zorder=1)
            ax.set_xlim(lims)
            ax.set_ylim(lims)
        ax.scatter(data[ok], model[ok], s=36, color=mark, edgecolor="white",
                   linewidth=1.0, zorder=2)
        ccc = lins_concordance(data, model)
        ccc_txt = "n/a" if not np.isfinite(ccc) else f"{ccc:.2f}"
        ax.set_title(f"{_ST_MODEL_LABELS.get(k, k)}\nLin's concordance {ccc_txt}"
                     f"  (n={int(ok.sum())})", fontsize=9, color=ink)
        ax.set_xlabel("Data", fontsize=8, color=ink)
        ax.set_ylabel("Spatiotemporal model", fontsize=8, color=ink)
        ax.tick_params(labelsize=7, colors=ink)
        ax.set_aspect("equal", adjustable="box")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    lag_ms = str(lag_key).replace("mslag", "")
    fig.suptitle(f"How much of each metric spatial + temporal autocorrelation "
                 f"predict — lag {lag_ms} ms", fontsize=10, color=ink)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    savefig(fig, out_path, default_dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


def _partial_spearman(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    """Spearman ρ between *x* and *y* with *z* partialled out (rank residuals)."""
    from scipy.stats import rankdata

    rx, ry, rz = (rankdata(v) for v in (x, y, z))
    design = np.column_stack([np.ones_like(rz), rz])
    ex = rx - design @ np.linalg.lstsq(design, rx, rcond=None)[0]
    ey = ry - design @ np.linalg.lstsq(design, ry, rcond=None)[0]
    den = np.sqrt(np.dot(ex, ex) * np.dot(ey, ey))
    return float(np.dot(ex, ey) / den) if den > 0 else float("nan")


def plot_spatiotemporal_diagnostic(
    raw_sub: np.ndarray,
    dist_sub: np.ndarray,
    coords: np.ndarray | None,
    metrics: dict,
    rate: np.ndarray,
    out_path: Path,
    *,
    title: str = "",
    dist_unit: str = "electrode pitches",
    rate_label: str = "Firing rate (Hz)",
    n_bins: int = 20,
) -> bool:
    """One network's SA/TA statistics against the data they summarise.

    Four panels, all over the network's active nodes:

    1. mean unthresholded coupling per distance bin, with the paper's pinned
       curve (``SA_lambda``/``SA_inf``) and the free-start one
       (``SA_lambda_free``/``SA_amp``/``SA_inf_free``) drawn over it;
    2. ``TA_regional`` at each node's position;
    3. TA against degree — the paper's "TA predicts the hubs" — with Spearman ρ,
       and ρ again with rate partialled out;
    4. TA against rate. On binned event counts TA is close to a function of
       rate alone (sparse events in short bins give ≈ −p/(1−p), p = rate × bin),
       so panel 3 means little unless its partial ρ survives.

    *raw_sub*, *dist_sub*, *coords* and *rate* are already restricted to the
    active nodes, in ``metrics["TA_regional"]`` order. Returns ``False``,
    drawing nothing, when the network has no SA/TA metrics.
    """
    from scipy.stats import spearmanr

    from meanap.pipeline.spatiotemporal import _binned_correlation_profile

    ta = np.asarray(metrics.get("TA_regional", []), dtype=float)
    if "SA_lambda" not in metrics or ta.size == 0:
        return False
    deg = np.asarray(metrics.get("ND", np.full(ta.size, np.nan)), dtype=float)
    rate = np.asarray(rate, dtype=float)

    ink, muted, mark = "#222222", "#8a8a8a", "#3b6ea8"
    pinned_c, free_c = "#3b6ea8", "#c0504d"
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))

    # 1. Coupling against distance.
    ax = axes[0]
    d, y = _binned_correlation_profile(np.asarray(raw_sub, float), np.asarray(dist_sub, float), n_bins)
    ax.plot(d, y, "o", color=ink, ms=4, label="Mean coupling per distance bin")
    lam, inf = metrics.get("SA_lambda", np.nan), metrics.get("SA_inf", np.nan)
    lam_f, amp, inf_f = (metrics.get(k, np.nan) for k in ("SA_lambda_free", "SA_amp", "SA_inf_free"))
    note = ""
    if d.size:
        x = np.linspace(0, d.max(), 300)
        if np.isfinite(lam) and np.isfinite(inf):
            ax.plot(x, (1 - inf) * np.exp(-x / lam) + inf, color=pinned_c, lw=1.5,
                    label=f"Pinned: SA-λ {lam:.3g}, SA-∞ {inf:.2f}")
            if np.exp(-d.min() / lam) < 0.1:
                note = ("Pinned curve has decayed before the nearest pair:\n"
                        "SA-λ is not a length scale here.")
        if np.isfinite(lam_f) and np.isfinite(amp) and np.isfinite(inf_f):
            xf = x[x > 0]
            ax.plot(xf, amp * np.exp(-xf / lam_f) + inf_f, color=free_c, lw=1.5,
                    label=f"Free start: λ {lam_f:.3g}, amp {amp:.2f}, ∞ {inf_f:.2f}")
        elif np.isfinite(inf_f):
            ax.axhline(inf_f, color=free_c, lw=1, ls="--",
                       label=f"Free start: no λ (level {inf_f:.2f})")
        else:
            ax.plot([], [], color=free_c, lw=1.5,
                    label="Free start: not identifiable (still falling at the edge)")
        lo = min(0.0, float(np.nanmin(y)))
        ax.set_ylim(lo - 0.02, 1.02)
    if note:
        ax.text(0.98, 0.5, note, transform=ax.transAxes, ha="right", va="center",
                fontsize=7, color=pinned_c)
    ax.set_xlabel(f"Distance ({dist_unit})", fontsize=8, color=ink)
    ax.set_ylabel("Unthresholded coupling", fontsize=8, color=ink)
    ax.set_title("Spatial autocorrelation", fontsize=9, color=ink)
    ax.legend(fontsize=6.5, frameon=False, loc="upper right")

    # 2. TA map.
    ax = axes[1]
    if coords is not None and len(coords) == ta.size:
        c = np.asarray(coords, dtype=float)
        sc = ax.scatter(c[:, 0], c[:, 1], c=ta, s=28, cmap="viridis", edgecolor="none")
        fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04).set_label("TA-Δ₁", fontsize=8)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        ax.set_axis_off()
    ax.set_title(f"Temporal autocorrelation (mean {np.nanmean(ta):.2f})", fontsize=9, color=ink)

    # 3–4. TA against degree and rate.
    def stats(xv: np.ndarray, partial: np.ndarray | None) -> str:
        ok = np.isfinite(xv) & np.isfinite(ta)
        if partial is not None:
            ok &= np.isfinite(partial)
        if ok.sum() < 5 or np.ptp(xv[ok]) == 0 or np.ptp(ta[ok]) == 0:
            return "too few varying nodes for ρ"
        txt = f"Spearman ρ = {spearmanr(xv[ok], ta[ok])[0]:.2f}"
        if partial is not None and np.ptp(partial[ok]) > 0:
            txt += f";  given rate: {_partial_spearman(ta[ok], xv[ok], partial[ok]):.2f}"
        return txt

    for ax, xv, xlabel, partial in ((axes[2], deg, "Node degree", rate),
                                    (axes[3], rate, rate_label, None)):
        ok = np.isfinite(xv) & np.isfinite(ta)
        ax.scatter(xv[ok], ta[ok], s=14, color=mark, edgecolor="white", linewidth=0.5)
        ax.set_xlabel(xlabel, fontsize=8, color=ink)
        ax.set_ylabel("TA-Δ₁", fontsize=8, color=ink)
        ax.set_title(stats(xv, partial), fontsize=9, color=ink)

    for ax in axes:
        ax.tick_params(labelsize=7, colors=ink)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    if title:
        fig.suptitle(title, fontsize=10, color=ink)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    savefig(fig, out_path, default_dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


#: Where the spatiotemporal-model comparison lands, under ``4_NetworkActivity``.
ST_MODEL_DIR = Path("4B_GroupComparisons") / "10_SpatiotemporalModel"
ST_MODEL_CSV = "SpatiotemporalModel_Concordance.csv"


def write_spatiotemporal_model_outputs(
    all_results: dict, net_dir: Path, *, draw: bool, log,
) -> None:
    """The batch-level model comparison: a CSV always, figures unless *draw* is off.

    Shared by the ephys step 4 and CAT-NAP, which hold their results in the
    same ``{recording: {lag_key: metrics}}`` shape. Does nothing when no
    recording carries model values (the model was off).
    """
    from meanap.pipeline.spatiotemporal import concordance_table

    table = concordance_table(all_results)
    if table.empty:
        return
    out_dir = Path(net_dir) / ST_MODEL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / ST_MODEL_CSV, index=False)
    log(f"  spatiotemporal model: concordance → {(out_dir / ST_MODEL_CSV).relative_to(Path(net_dir).parent)}")
    if not draw:
        return
    for lag_key in table["Lag"].unique():
        plot_spatiotemporal_model(
            all_results, lag_key, out_dir / f"SpatiotemporalModel_{lag_key}.png")
