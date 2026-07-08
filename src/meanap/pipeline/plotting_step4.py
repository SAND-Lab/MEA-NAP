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

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from meanap.network_plot import plot_network
from meanap.params import Params
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.network_metrics import classify_node_cartography


def plot_connectivity_stats(
    adj_m: np.ndarray,
    nd: np.ndarray,
    ns: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    exclude_edges_below_threshold: bool = True,
) -> None:
    """Port of ``plotConnectivityProperties.m``'s single saved figure.

    Layout mirrors the MATLAB 6x6 ``tiledlayout``: adjacency matrix heatmap
    (top-left block) + max/mean STTC bars (bottom-left) + ND/NS/edge-weight
    histograms (right column).
    """
    if exclude_edges_below_threshold:
        edge_weights = adj_m[adj_m > 0]
    else:
        edge_weights = adj_m.ravel()

    mean_sttc = float(np.nanmean(edge_weights)) if edge_weights.size else 0.0
    max_sttc = float(np.max(edge_weights)) if edge_weights.size else 0.0
    max_sttc = max(max_sttc, 0.001)
    max_adj_m = max(float(np.max(adj_m)) if adj_m.size else 0.0, 0.0001)
    ylim_bar = (0, max_adj_m + 0.15 * max_adj_m)

    fig = plt.figure(figsize=(11, 6))
    gs = fig.add_gridspec(6, 6)
    fig.suptitle(f"{recording_name} {lag_ms} ms lag")

    ax_adj = fig.add_subplot(gs[0:3, 0:2])
    im = ax_adj.imshow(adj_m, aspect="auto")
    ax_adj.set_xlabel("nodes")
    ax_adj.set_ylabel("nodes")
    ax_adj.set_title("adjacency matrix")
    cbar = fig.colorbar(im, ax=ax_adj)
    cbar.set_label("correlation coefficient")

    ax_max = fig.add_subplot(gs[3:6, 0])
    ax_max.bar([0], [max_sttc], color="#1f77b4")
    ax_max.set_ylim(*ylim_bar)
    ax_max.set_title("max corr. value")
    ax_max.set_xticks([])

    ax_mean = fig.add_subplot(gs[3:6, 1])
    ax_mean.bar([0], [mean_sttc], color="#1f77b4")
    ax_mean.set_ylim(*ylim_bar)
    ax_mean.set_title("mean corr. value")
    ax_mean.set_xticks([])

    ax_nd = fig.add_subplot(gs[0:2, 3:6])
    ax_nd.hist(nd, bins=50, color="#4FC3E8")
    ax_nd.set_xlabel("node degree")
    ax_nd.set_ylabel("frequency")

    ax_ns = fig.add_subplot(gs[2:4, 3:6])
    ax_ns.hist(ns, bins=50, color="#4FC3E8")
    ax_ns.set_xlabel("node strength")
    ax_ns.set_ylabel("frequency")

    ax_ew = fig.add_subplot(gs[4:6, 3:6])
    ax_ew.hist(edge_weights, bins=50, color="#4FC3E8")
    ax_ew.set_xlabel("edge weight")
    ax_ew.set_ylabel("frequency")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


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
    prepared = _prepare_network_plot_data(
        adj_m_sub, channels_active, channel_layout, z, z2,
    )
    if prepared is None:
        return
    sub, coords, z_sub, z2_sub = prepared

    scaled = z_scale_override is not None
    title_suffix = " (scaled to data batch)" if scaled else ""
    fig, ax = plt.subplots(figsize=(8, 8))
    plot_network(
        ax, sub, coords, edge_thresh, z_sub, z2_sub, z2_name,
        title=f"{recording_name}  {lag_ms} ms lag{title_suffix}", z_name=z_name,
        z_scale_override=z_scale_override,
        z2_bounds_override=z2_bounds_override,
        edge_bounds_override=edge_bounds_override,
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _prepare_network_plot_data(
    adj_m_sub: np.ndarray,
    channels_active: np.ndarray,
    channel_layout: str,
    z: np.ndarray,
    z2: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None] | None:
    """Map active channels to layout coordinates and subset the adjacency
    matrix / per-node metrics to the channels that have a coordinate.

    Returns ``(sub_adj, coords, z_sub, z2_sub)`` or ``None`` if no active
    channel has a coordinate (e.g. an all-grounded layout). Shared by
    ``plot_spatial_network`` and ``plot_spatial_network_combined`` so both
    subset identically.
    """
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
    return sub, coords, z_sub, z2_sub


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
) -> None:
    """Side-by-side "combined" network plot, port of the
    ``N_combined_MEA_NetworkPlot`` figure from ``PlotIndvNetMet.m``.

    Left panel is scaled to this recording's own range; right panel is scaled
    to the whole data batch (via the ``*_override`` bounds). Same two-scale
    comparison MATLAB builds by ``copyobj``-ing its individual and scaled
    figures into one two-subplot figure — here we just render
    ``plot_network`` onto two axes of a single wide figure, each with its own
    inline legend/colorbar.
    """
    prepared = _prepare_network_plot_data(
        adj_m_sub, channels_active, channel_layout, z, z2,
    )
    if prepared is None:
        return
    sub, coords, z_sub, z2_sub = prepared

    fig, (ax_ind, ax_batch) = plt.subplots(1, 2, figsize=(16, 8))
    plot_network(
        ax_ind, sub, coords, edge_thresh, z_sub, z2_sub, z2_name,
        title=f"{recording_name}  {lag_ms} ms lag\nscaled to recording",
        z_name=z_name,
    )
    plot_network(
        ax_batch, sub, coords, edge_thresh, z_sub, z2_sub, z2_name,
        title=f"{recording_name}  {lag_ms} ms lag\nscaled to entire data batch",
        z_name=z_name,
        z_scale_override=z_scale_override,
        z2_bounds_override=z2_bounds_override,
        edge_bounds_override=edge_bounds_override,
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# Role colors, matching NodeCartography.m's c1..c6 exactly.
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


def plot_node_cartography(
    pc: np.ndarray, z: np.ndarray, params: Params,
    lag_ms: float, recording_name: str, out_path: Path,
) -> None:
    """Node cartography scatter, port of the top panel of ``NodeCartography.m``
    (participation coefficient vs. within-module degree z-score, colored by
    role, with the 5 fixed decision-boundary lines from ``Params``).

    The bottom panel in MATLAB's version is a static reference diagram image
    (``NodeCartographyDiagram.jpg``) explaining the 6 roles — not
    reproduced here since it's not derived from any data.
    """
    hub_boundary = params.hub_boundary_wm_d_deg
    peri = params.peri_part_coef
    non_hub_connector = params.non_hub_connector_part_coef
    pro_hub = params.pro_hub_part_coef
    connector_hub = params.connector_hub_part_coef

    nd_cart_div, _ = classify_node_cartography(
        pc, z, hub_boundary, peri, non_hub_connector, pro_hub, connector_hub,
    )

    if len(pc) == 0 or np.all(np.isnan(pc)):
        part_coef_range = (0.0, 1.0)
    else:
        part_coef_range = (float(np.nanmin(pc)), float(np.nanmax(pc)))
        if part_coef_range[0] == part_coef_range[1]:
            part_coef_range = (0.0, 1.0)

    if len(z) == 0 or np.all(np.isnan(z)):
        wm_deg_range = (-2.0, 4.0)
    else:
        lo = np.nanmin(z) * (1.1 if np.nanmin(z) < 0 else 0.9)
        hi = np.nanmax(z) * (1.1 if np.nanmax(z) > 0 else 0.9)
        wm_deg_range = (float(lo), float(hi))
        if wm_deg_range[0] == wm_deg_range[1]:
            wm_deg_range = (-2.0, 4.0)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(part_coef_range, [hub_boundary, hub_boundary], "--k", linewidth=1)
    ax.plot([peri, peri], [wm_deg_range[0], hub_boundary], "--k", linewidth=1)
    ax.plot([non_hub_connector, non_hub_connector], [wm_deg_range[0], hub_boundary], "--k", linewidth=1)
    ax.plot([pro_hub, pro_hub], [hub_boundary, wm_deg_range[1]], "--k", linewidth=1)
    ax.plot([connector_hub, connector_hub], [hub_boundary, wm_deg_range[1]], "--k", linewidth=1)

    for role in range(1, 7):
        mask = nd_cart_div == role
        if np.any(mask):
            ax.scatter(
                pc[mask], z[mask], s=18, color=_CARTOGRAPHY_COLORS[role],
                label=_CARTOGRAPHY_LABELS[role], edgecolors="none",
            )

    ax.set_xlim(*part_coef_range)
    ax.set_ylim(*wm_deg_range)
    ax.set_xlabel("participation coefficient")
    ax.set_ylabel("within-module degree z-score")
    ax.set_title(f"{recording_name} {lag_ms} ms lag  —  node cartography")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8, frameon=False)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


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
    n = adj_m_sub.shape[0]
    if n == 0:
        return

    plasma = _plasma_256()

    # ── Node positions (unit circle) ──────────────────────────────────────────
    t = np.linspace(-np.pi, np.pi, n + 1)  # N+1 angles; node i uses t[i]
    node_x = np.cos(t[:n])
    node_y = np.sin(t[:n])

    # ── Edge geometry ─────────────────────────────────────────────────────────
    max_ew = 2.0
    min_ew = 0.001
    light_c = np.array([0.8, 0.8, 0.8])

    adj_tril = np.tril(adj_m_sub, -1)
    flat_order = np.argsort(adj_tril.ravel())          # ascending → weak first
    rows_ord, cols_ord = np.unravel_index(flat_order, adj_tril.shape)

    pos_vals = adj_m_sub[adj_m_sub > 0]
    edge_max = float(adj_m_sub.max()) if adj_m_sub.max() > 0 else 1.0
    edge_min = float(pos_vals.min()) if pos_vals.size else edge_max
    edge_range = edge_max - edge_min if edge_max != edge_min else max(edge_max, 1e-6)

    edge_xs: list[np.ndarray] = []
    edge_ys: list[np.ndarray] = []
    edge_lws: list[float] = []
    edge_cols: list[np.ndarray] = []

    for ea, eb in zip(rows_ord, cols_ord):
        w = adj_m_sub[ea, eb]
        if w < edge_thresh or ea == eb or np.isnan(w) or w <= 0:
            continue
        xc, yc = _arc_points(t[ea], t[eb])
        frac = (w - edge_min) / edge_range
        lw = min_ew + (max_ew - min_ew) * frac
        col = np.clip(np.ones(3) - light_c * frac, 0.0, 1.0)
        edge_xs.append(xc)
        edge_ys.append(yc)
        edge_lws.append(max(lw, min_ew))
        edge_cols.append(col)

    # ── Node colours by module ────────────────────────────────────────────────
    ci_arr = np.asarray(ci, dtype=float)
    unique_modules = np.unique(ci_arr[~np.isnan(ci_arr)])
    unique_modules = unique_modules[unique_modules > 0]
    ci_min = float(unique_modules.min()) if unique_modules.size else 1.0
    ci_max = float(unique_modules.max()) if unique_modules.size else 1.0
    if ci_max == ci_min:
        ci_max = ci_min + 1.0

    def _module_color(m: float) -> np.ndarray:
        frac = (m - ci_min) / (ci_max - ci_min)
        idx = max(int(np.ceil(len(plasma) * frac)) - 1, 0)
        return plasma[min(idx, len(plasma) - 1)]

    # ── Node sizing ───────────────────────────────────────────────────────────
    max_z = float(np.nanmax(nd)) if np.any(nd > 0) else 1.0
    spacing = np.sqrt(
        (np.cos(t[0]) - np.cos(t[1])) ** 2 + (np.sin(t[0]) - np.sin(t[1])) ** 2
    )
    node_scale_f = max_z / spacing if spacing > 0 else max_z
    min_node_size_px = 0.02

    # ── Figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(9.6, 7.3))
    ax = fig.add_axes([0.04, 0.05, 0.60, 0.88])
    ax.set_aspect("equal")
    ax.axis("off")

    title_str = recording_name.replace("_", "") + f"  {lag_ms} ms lag"
    ax.set_title(title_str, fontweight="bold", fontsize=11)

    # Draw edges (weakest drawn first so strongest appear on top)
    for xc, yc, lw, col in zip(edge_xs, edge_ys, edge_lws, edge_cols):
        ax.plot(xc, yc, linewidth=lw, color=col, solid_capstyle="round")

    # Draw nodes
    for i in range(n):
        if nd[i] <= 0:
            continue
        node_size = max(min_node_size_px, nd[i] / node_scale_f)
        m = ci_arr[i]
        node_color = _module_color(m) if (not np.isnan(m) and m > 0) else plasma[0]
        circ = plt.Circle(
            (node_x[i], node_y[i]), node_size / 2,
            facecolor=node_color, edgecolor="white", linewidth=0.1, zorder=3,
        )
        ax.add_patch(circ)

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)

    # ── Legend (right panel) ──────────────────────────────────────────────────
    # The legend uses a separate axes with xlim/ylim = (0,1).  Circles are
    # rendered as scatter points (display-space, always round) rather than
    # matplotlib Patch objects (which would appear oval in a non-square axes).
    ax_leg = fig.add_axes([0.67, 0.02, 0.31, 0.96])
    ax_leg.set_xlim(0, 1)
    ax_leg.set_ylim(0, 1)
    ax_leg.axis("off")

    # Convert a data-space radius in ax_leg's y-direction to a scatter marker
    # size (points²).  This lets us keep legend geometry in data coordinates
    # while still producing round dots.
    #   - ax_leg height in inches = fig height × axes_height_frac
    #   - data height = ylim_max - ylim_min = 1
    #   - 1 data unit = (fig_h_in × axes_frac) × 72 pt/in display points
    fig_h_in, ax_frac_h = fig.get_size_inches()[1], 0.96
    pts_per_data_unit = fig_h_in * ax_frac_h * fig.dpi / 72  # px-per-unit → pt-per-unit with dpi correction
    pts_per_data_unit = fig_h_in * ax_frac_h * 72  # display-pts per data unit

    def _r_to_s(r_data: float) -> float:
        """Convert a circle radius in ax_leg data coords to scatter s (pt²)."""
        diameter_pts = r_data * 2 * pts_per_data_unit
        return max((diameter_pts / 2) ** 2 * np.pi, 4.0)

    # -- Node degree legend --
    nd_fracs = [1 / 3, 2 / 3, 1.0]
    nd_vals = [max_z * f for f in nd_fracs]
    if int(round(nd_vals[0])) >= 1:
        nd_labels = [f"{int(round(v)):02d}" for v in nd_vals]
    else:
        nd_labels = [f"{v:.4f}" for v in nd_vals]

    ax_leg.text(0.05, 0.97, "Node degree:", fontsize=9, va="top")

    # Node-degree circle sizes in ax_leg data coords
    sizes_norm = [max(v / node_scale_f, min_node_size_px) for v in nd_vals]
    # Cap so they fit in the legend panel (max radius = 0.10 data units)
    sizes_norm = [min(s, 0.20) for s in sizes_norm]

    # Stack circles from top, with a small gap between each
    gap = 0.06
    y_pos = []
    cur_y = 0.90
    for s in sizes_norm:
        cur_y -= s / 2
        y_pos.append(cur_y)
        cur_y -= s / 2 + gap

    leg_x_circle = 0.22
    leg_x_text = 0.40
    for si, yi, label in zip(sizes_norm, y_pos, nd_labels):
        ax_leg.scatter(
            [leg_x_circle], [yi],
            s=_r_to_s(si / 2),
            facecolors="white", edgecolors="black", linewidths=0.8, zorder=3,
        )
        ax_leg.text(leg_x_text, yi, label, va="center", fontsize=8)

    # -- Edge weight legend --
    ew_top = cur_y - 0.02
    ax_leg.text(0.05, ew_top, "edge weight:", fontsize=9, va="top")

    ew_triplet = [
        edge_max - (2 / 3) * edge_range,
        edge_max - (1 / 3) * edge_range,
        edge_max,
    ]
    line_x = [0.05, 0.45]
    ew_y_start = ew_top - 0.08
    ew_y_gap = 0.075

    for k, ew_val in enumerate(ew_triplet):
        frac = (ew_val - edge_min) / edge_range if edge_range > 0 else 1.0
        lw = max(min_ew + (max_ew - min_ew) * frac, 0.3) * 1.5
        col = np.clip(np.ones(3) - light_c * frac, 0, 1)
        ew_y = ew_y_start - k * ew_y_gap
        ax_leg.plot(line_x, [ew_y, ew_y],
                    linewidth=lw, color=col, solid_capstyle="round")
        ax_leg.text(0.50, ew_y, str(round(ew_val, 4)), va="center", fontsize=8)

    # -- Module swatches --
    mod_label_y = ew_y - ew_y_gap - 0.02
    ax_leg.text(0.05, mod_label_y, "Module", fontsize=9, va="top")

    swatch_y = mod_label_y - 0.10
    n_mods = len(unique_modules)
    # Swatch radius: fit n_mods non-overlapping circles across x in [0.05, 0.95]
    x_span = 0.90
    max_swatch_r = x_span / max(n_mods * 2.4, 1)
    swatch_r = min(0.07, max_swatch_r)
    swatch_xs = (
        np.linspace(0.05 + swatch_r, 0.95 - swatch_r, n_mods)
        if n_mods > 1
        else np.array([0.45])
    )

    for mod_val, sx in zip(unique_modules, swatch_xs):
        col = _module_color(mod_val)
        ax_leg.scatter(
            [sx], [swatch_y],
            s=_r_to_s(swatch_r),
            facecolors=[col], edgecolors="white", linewidths=0.1, zorder=3,
        )
        ax_leg.text(
            sx, swatch_y, str(int(mod_val)),
            ha="center", va="center", fontsize=6, color="white", zorder=4,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_circular_cartography_network(
    adj_m_sub: np.ndarray,
    nd_cart_div: np.ndarray,
    lag_ms: float,
    recording_name: str,
    out_path: Path,
    edge_thresh: float = 0.0,
) -> None:
    """Circular network plot with nodes colored by cartography role.

    Port of ``StandardisedNetworkPlotNodeCartography.m`` with
    ``plotType='circular'``.
    """
    n = adj_m_sub.shape[0]
    if n == 0:
        return

    # ── Node positions (unit circle) ──────────────────────────────────────────
    t = np.linspace(-np.pi, np.pi, n + 1)
    node_x = np.cos(t[:n])
    node_y = np.sin(t[:n])

    # ── Edge geometry ─────────────────────────────────────────────────────────
    max_ew = 2.0
    min_ew = 0.001
    light_c = np.array([0.8, 0.8, 0.8])

    adj_tril = np.tril(adj_m_sub, -1)
    flat_order = np.argsort(adj_tril.ravel())
    rows_ord, cols_ord = np.unravel_index(flat_order, adj_tril.shape)

    pos_vals = adj_m_sub[adj_m_sub > 0]
    edge_max = float(adj_m_sub.max()) if adj_m_sub.max() > 0 else 1.0
    edge_min = float(pos_vals.min()) if pos_vals.size else edge_max
    edge_range = edge_max - edge_min if edge_max != edge_min else max(edge_max, 1e-6)

    edge_xs: list[np.ndarray] = []
    edge_ys: list[np.ndarray] = []
    edge_lws: list[float] = []
    edge_cols: list[np.ndarray] = []

    for ea, eb in zip(rows_ord, cols_ord):
        w = adj_m_sub[ea, eb]
        if w < edge_thresh or ea == eb or np.isnan(w) or w <= 0:
            continue
        xc, yc = _arc_points(t[ea], t[eb])
        frac = (w - edge_min) / edge_range
        lw = max(min_ew + (max_ew - min_ew) * frac, min_ew)
        col = np.clip(np.ones(3) - light_c * frac, 0.0, 1.0)
        edge_xs.append(xc)
        edge_ys.append(yc)
        edge_lws.append(max(lw, min_ew))
        edge_cols.append(col)

    # ── Node sizes ────────────────────────────────────────────────────────────
    if n > 1:
        spacing = np.sqrt(
            (np.cos(t[0]) - np.cos(t[1])) ** 2 + (np.sin(t[0]) - np.sin(t[1])) ** 2
        )
    else:
        spacing = 0.1
    node_size = (2.0 / 3.0) * spacing

    # ── Figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(9.6, 7.3))
    ax = fig.add_axes([0.04, 0.05, 0.60, 0.88])
    ax.set_aspect("equal")
    ax.axis("off")

    title_str = recording_name.replace("_", "") + f"  {lag_ms} ms lag"
    ax.set_title(title_str, fontweight="bold", fontsize=11)

    # Draw edges
    for xc, yc, lw, col in zip(edge_xs, edge_ys, edge_lws, edge_cols):
        ax.plot(xc, yc, linewidth=lw, color=col, solid_capstyle="round")

    # Draw nodes
    for i in range(n):
        role = nd_cart_div[i]
        node_color = _CARTOGRAPHY_COLORS.get(role, (0.5, 0.5, 0.5))
        circ = plt.Circle(
            (node_x[i], node_y[i]), node_size / 2,
            facecolor=node_color, edgecolor="white", linewidth=0.1, zorder=3,
        )
        ax.add_patch(circ)

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)

    # ── Legend (right panel) ──────────────────────────────────────────────────
    ax_leg = fig.add_axes([0.67, 0.02, 0.31, 0.96])
    ax_leg.set_xlim(0, 1)
    ax_leg.set_ylim(0, 1)
    ax_leg.axis("off")

    def _r_to_s(r_data: float) -> float:
        ax_h_inches = 7.3 * 0.96
        y_range = 1.0
        r_inches = (r_data / y_range) * ax_h_inches
        r_points = r_inches * 72.0
        return (r_points * 2) ** 2

    # Draw cartography swatches vertically
    swatch_r = 0.045
    current_y = 0.90
    for role in range(1, 7):
        col = _CARTOGRAPHY_COLORS[role]
        label = _CARTOGRAPHY_LABELS[role]
        ax_leg.scatter(
            [0.1], [current_y],
            s=_r_to_s(swatch_r),
            facecolors=[col], edgecolors="white", linewidths=0.1, zorder=3,
        )
        ax_leg.text(0.2, current_y, label, va="center", fontsize=9)
        current_y -= 0.09

    current_y -= 0.03
    ax_leg.text(0.05, current_y, "edge weight:", va="center", fontsize=9)
    current_y -= 0.08

    ew_triplet = [
        edge_max - (2 / 3) * edge_range,
        edge_max - (1 / 3) * edge_range,
        edge_max,
    ]
    line_x = [0.1, 0.35]

    for ew_val in ew_triplet:
        frac = (ew_val - edge_min) / edge_range if edge_range > 0 else 1.0
        lw = max(min_ew + (max_ew - min_ew) * frac, 0.3) * 1.5
        col = np.clip(np.ones(3) - light_c * frac, 0, 1)
        ax_leg.plot(line_x, [current_y, current_y],
                    linewidth=lw, color=col, solid_capstyle="round")
        ax_leg.text(0.40, current_y, str(round(ew_val, 4)), va="center", fontsize=9)
        current_y -= 0.08

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── Half-violin helper ────────────────────────────────────────────────────────

def _half_violin(
    ax: "plt.Axes",
    data: np.ndarray,
    pos: float = 1.0,
    colour: tuple = (0.3, 0.3, 0.3),
    width: float = 1.0,
    rng: np.random.Generator | None = None,
) -> None:
    """Draw a half-violin plot on *ax*, mirroring ``HalfViolinPlot.m``.

    Port of ``HalfViolinPlot.m`` (author RCFeord, edited Tim Sit):
    - Right half: KDE curve filled rightward from ``pos``
    - Left half: jittered scatter dots at ``pos - width … pos``
    - Mean dot (large black) + SEM bar at ``pos``

    Uses scipy Gaussian KDE with Silverman's rule (MATLAB ``ksdensity``
    default) and a minimum bandwidth of 10% of the data range, matching
    the ``min_bandwidth`` guard in ``HalfViolinPlot.m``.
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
        xi = np.linspace(data.min(), data.max(), 256)
        f = kde(xi)
    else:
        # Single unique value or zero variance — tiny spike
        xi = np.array([data.mean()])
        f = np.array([1.0])

    # Scale width: widthFactor = width / max(f)  (MATLAB line 69)
    width_factor = width / max(f.max(), 1e-12)
    # KDE fills to the RIGHT of pos (MATLAB: fill(f*widthFactor + pos + 0.1, xi, colour))
    kde_x = f * width_factor + pos + 0.1
    ax.fill_betweenx(xi, pos + 0.1, kde_x, color=colour, linewidth=1,
                     edgecolor=colour)

    # ── Jittered scatter ─────────────────────────────────────────────────────
    jitter = rng.random(len(data)) * width
    drops_x = jitter + pos - (width + 0.1)  # MATLAB line 77
    ax.scatter(drops_x, data, s=20, color=colour, zorder=3)

    # ── Mean dot + SEM bar ───────────────────────────────────────────────────
    mean_val = float(np.mean(data))
    sem_val = float(np.std(data) / np.sqrt(len(data))) if len(data) > 1 else 0.0
    ax.scatter([pos], [mean_val], s=100, color="black", zorder=4)
    ax.plot([pos, pos], [mean_val - sem_val, mean_val + sem_val],
            color="black", linewidth=3, zorder=4)


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
) -> None:
    """Half-violin panel for all node-level graph metrics.

    Port of ``electrodeSpecificMetrics.m``.  Layout mirrors MATLAB's 4×7
    ``tiledlayout``:
    - **Row 0**: schematic PNG icons (ND / EW / NS / WMZ / Eloc / PC / BC)
      loaded from ``images_dir`` (defaults to ``Images/`` at the repo root
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
        the function looks for ``Images/`` three levels above this file
        (i.e. the MEA-NAP repo root).
    rng : optional seeded RNG (for reproducible jitter in tests)
    """
    if rng is None:
        rng = np.random.default_rng()

    # ── Resolve schematic images directory ───────────────────────────────────
    if images_dir is None:
        # Repo root = three levels above src/meanap/pipeline/
        images_dir = Path(__file__).parent.parent.parent.parent / "Images"

    SCHEMATICS = [
        ("ND.png",   "node degree"),
        ("EW.png",   "edge weight"),
        ("NS.png",   "node strength"),
        ("WMZ.png",  "within-module\ndegree z-score"),
        ("Eloc.png", "local efficiency"),
        ("PC.png",   "participation\ncoefficient"),
        ("BC.png",   "betweenness\ncentrality"),
    ]

    # ── Metric slots (in column order, matching MATLAB) ───────────────────────
    # Each entry: (data_array, y_label, y_lim_fn)
    def _ylim_nd(d):
        mx = max(float(np.nanmax(d)), 1.0)
        return (0, mx * 1.2)

    def _ylim_mew(d):
        mx = max(float(np.nanmax(d)), 0.1)
        return (0, mx * 1.2)

    def _ylim_ns(d):
        mx = max(float(np.nanmax(d)), 0.1)
        return (0, mx * 1.2)

    def _ylim_z(d):
        lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
        if lo == hi:
            return (0, hi + 0.1)
        return (lo - abs(lo) * 0.2, hi + abs(hi) * 0.2)

    def _ylim_eloc(d):
        mx = float(np.nanmax(d))
        if len(np.unique(d[np.isfinite(d)])) == 1:
            return None  # let matplotlib decide
        return (0, mx * 1.2)

    def _ylim_pc(d):
        mx = min(float(np.nanmax(d)) * 1.2, 1.0)
        return (0, mx)

    def _ylim_bc(d):
        lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
        if lo == hi:
            return (0, hi + 0.1)
        return (0, hi * 1.2)

    def _is_plottable(arr):
        if arr is None:
            return False
        a = np.asarray(arr, dtype=float)
        a = a[np.isfinite(a)]
        return len(a) > 1

    metrics = [
        (nd,   "node degree",                  _ylim_nd,   True),
        (mew,  "mean edge weight",              _ylim_mew,  True),
        (ns,   "node strength",                 _ylim_ns,   True),
        (z,    "within-module degree z-score",  _ylim_z,    _is_plottable(z)),
        (eloc, "local efficiency",              _ylim_eloc,
            _is_plottable(eloc) and float(np.nanmax(eloc)) > 0),
        (pc,   "participation coefficient",     _ylim_pc,   _is_plottable(pc)),
        (bc,   "betweenness centrality",        _ylim_bc,   _is_plottable(bc)),
    ]

    # ── Figure ────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(18.7, 7.3))   # ~1400×550 pt at 75 dpi (MATLAB p=[100 100 1400 550])
    gs = fig.add_gridspec(4, 7, hspace=0.05, wspace=0.35)

    title_str = recording_name.replace("_", "") + f" {lag_ms} ms lag"
    fig.suptitle(title_str, fontsize=11)

    # ── Row 0: schematic images ───────────────────────────────────────────────
    for col, (fname, label) in enumerate(SCHEMATICS):
        ax_img = fig.add_subplot(gs[0, col])
        ax_img.axis("off")
        img_path = images_dir / fname
        if img_path.exists():
            import matplotlib.image as mpimg
            img = mpimg.imread(str(img_path))
            ax_img.imshow(img, aspect="equal")
        else:
            # Fallback: just show the label as text
            ax_img.text(0.5, 0.5, label, ha="center", va="center",
                        fontsize=8, transform=ax_img.transAxes)

    # ── Rows 1–3: half-violin plots ───────────────────────────────────────────
    grey = (0.3, 0.3, 0.3)

    for col, (data, ylabel, ylim_fn, do_plot) in enumerate(metrics):
        ax = fig.add_subplot(gs[1:4, col])
        ax.tick_params(direction="out")
        ax.set_xticks([])
        ax.set_ylabel(ylabel, fontsize=8)

        # Match MATLAB `aesthetics`: minimal spines
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)

        if do_plot and data is not None:
            arr = np.asarray(data, dtype=float)
            _half_violin(ax, arr, pos=1.0, colour=grey, width=1.0, rng=rng)

            ylim = ylim_fn(arr[np.isfinite(arr)])
            if ylim is not None:
                ax.set_ylim(*ylim)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

import pandas as pd
import seaborn as sns

NETMET_REC_METRICS = {
    "aN": "Active Nodes",
    "Dens": "Density",
    "CC": "Clustering Coefficient",
    "nMod": "Number of Modules",
    "Q": "Modularity (Q)",
    "PL": "Path Length",
    "Eglob": "Global Efficiency",
    "SW": "Small-worldness (SW)",
    "SWw": "Small-worldness (SWw)",
    "effRank": "Effective Rank",
    "num_nnmf_components": "Num NNMF Components",
    "nComponentsRelNS": "NNMF Components / NS",
    "NDmean": "Mean Node Degree",
    "NDtop25": "Top 25% Node Degree",
    "sigEdgesMean": "Mean Significant Edges",
    "sigEdgesTop10": "Top 10% Significant Edges",
    "NSmean": "Mean Node Strength",
    "ElocMean": "Mean Local Efficiency",
    "PCmean": "Mean Participation Coefficient",
    "PCmeanTop10": "Top 10% Participation Coefficient",
    "PCmeanBottom10": "Bottom 10% Participation Coefficient",
    "percentZscoreGreaterThanZero": "Percent Z > 0",
    "percentZscoreLessThanZero": "Percent Z < 0",
    "NCpn1": "Node Cartography R1 (%)",
    "NCpn2": "Node Cartography R2 (%)",
    "NCpn3": "Node Cartography R3 (%)",
    "NCpn4": "Node Cartography R4 (%)",
    "NCpn5": "Node Cartography R5 (%)",
    "NCpn6": "Node Cartography R6 (%)",
    "aveControlMean": "Mean Average Controllability",
    "modalControlMean": "Mean Modal Controllability"
}

NETMET_NODE_METRICS = {
    "ND": "Node Degree",
    "MEW": "Mean Edge Weight",
    "NS": "Node Strength",
    "Z": "Within-Module Degree Z-Score",
    "Eloc": "Local Efficiency",
    "PC": "Participation Coefficient",
    "BC": "Betweenness Centrality",
    "aveControl": "Average Controllability",
    "modalControl": "Modal Controllability"
}

def _plot_violin(df: pd.DataFrame, metric: str, group_col: str, out_path: Path, ylabel: str) -> None:
    if df.empty or metric not in df.columns or df[metric].dropna().empty:
        return
        
    df_plot = df.dropna(subset=[metric])
    if df_plot.empty:
        return
        
    fig, ax = plt.subplots(figsize=(max(4, len(df_plot[group_col].unique()) * 1.5), 6))
    
    sns.violinplot(
        data=df_plot, x=group_col, y=metric,
        ax=ax, color="lightgray", inner=None, linewidth=1
    )
    sns.stripplot(
        data=df_plot, x=group_col, y=metric,
        ax=ax, color="black", size=4, jitter=True, alpha=0.6
    )
    
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.set_title(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

def plot_step4_group_comparisons(
    recordings: list,
    all_results: dict,
    out_dir: Path,
    custom_grp_order: list[str] | None = None
) -> None:
    """Generate group comparison plots for step 4."""
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
                
    if not rec_rows:
        return
        
    df_rec = pd.DataFrame(rec_rows)
    df_node = pd.DataFrame(node_rows)
    
    if custom_grp_order:
        df_rec["Grp"] = pd.Categorical(df_rec["Grp"], categories=custom_grp_order, ordered=True)
        df_node["Grp"] = pd.Categorical(df_node["Grp"], categories=custom_grp_order, ordered=True)
    
    # 3_RecordingsByGroup and 1_NodeByGroup
    grp_dir = out_dir / "4B_GroupComparisons" / "3_RecordingsByGroup" / "HalfViolinPlots"
    node_grp_dir = out_dir / "4B_GroupComparisons" / "1_NodeByGroup"
    
    # Loop over lags
    for lag in df_rec["Lag"].unique():
        # Handle "10mslag" vs "10ms"
        lag_str = lag.replace("lag", "") if isinstance(lag, str) else lag
        lag_grp_dir = grp_dir / f"Lag{lag_str}ms" if "ms" not in str(lag_str) else grp_dir / f"Lag{lag_str}"
        lag_grp_dir.mkdir(parents=True, exist_ok=True)
        
        df_rec_lag = df_rec[df_rec["Lag"] == lag]
        for k, name in NETMET_REC_METRICS.items():
            _plot_violin(df_rec_lag, k, "Grp", lag_grp_dir / f"{k}_byGroup.png", name)
            
        lag_node_grp_dir = node_grp_dir / f"Lag{lag_str}ms" if "ms" not in str(lag_str) else node_grp_dir / f"Lag{lag_str}"
        lag_node_grp_dir.mkdir(parents=True, exist_ok=True)
        
        df_node_lag = df_node[df_node["Lag"] == lag]
        for k, name in NETMET_NODE_METRICS.items():
            _plot_violin(df_node_lag, k, "Grp", lag_node_grp_dir / f"{k}_byGroup_node.png", name)
        
    # 4_RecordingsByAge and 2_NodeByAge
    age_dir = out_dir / "4B_GroupComparisons" / "4_RecordingsByAge" / "HalfViolinPlots"
    node_age_dir = out_dir / "4B_GroupComparisons" / "2_NodeByAge"
    
    for lag in df_rec["Lag"].unique():
        lag_str = lag.replace("lag", "") if isinstance(lag, str) else lag
        
        lag_age_dir = age_dir / f"Lag{lag_str}ms" if "ms" not in str(lag_str) else age_dir / f"Lag{lag_str}"
        lag_age_dir.mkdir(parents=True, exist_ok=True)
        
        df_rec_lag = df_rec[df_rec["Lag"] == lag]
        for k, name in NETMET_REC_METRICS.items():
            _plot_violin(df_rec_lag, k, "DIV", lag_age_dir / f"{k}_byDIV.png", name)
            
        lag_node_age_dir = node_age_dir / f"Lag{lag_str}ms" if "ms" not in str(lag_str) else node_age_dir / f"Lag{lag_str}"
        lag_node_age_dir.mkdir(parents=True, exist_ok=True)
        
        df_node_lag = df_node[df_node["Lag"] == lag]
        for k, name in NETMET_NODE_METRICS.items():
            _plot_violin(df_node_lag, k, "DIV", lag_node_age_dir / f"{k}_byDIV_node.png", name)
