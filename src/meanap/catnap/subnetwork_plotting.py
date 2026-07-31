"""Figures for the CAT-NAP cell-type subnetwork analysis.

Two families, matching the two questions the analysis answers:

*Graphs* — where the subnetworks sit in the field of view.
  - :func:`plot_subnetwork_spatial` — the whole network, nodes coloured by cell
    type and edges coloured by whether they stay within a type or cross between
    types.
  - :func:`plot_subnetwork_panels` — the same coordinates repeated per group,
    each panel showing only that group's induced subgraph.

*Comparisons* — how the subnetworks differ.
  - :func:`plot_node_metrics_by_group` — half-violin distributions of
    whole-network node metrics, split by cell type.
  - :func:`plot_subnetwork_metric_bars` — recording-level metrics recomputed on
    each induced subgraph.
  - :func:`plot_edge_mix_matrix` — group × group density / mean-weight heatmaps.

Node coordinates are suite2p cell centroids (``res.coords``), so these render
in imaging space; the ``y`` axis is inverted to match the image convention used
by the other CAT-NAP figures.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from meanap.catnap.subnetwork import CellTypeGroups, WHOLE_NETWORK
from meanap.pipeline.plotting_step4 import _half_violin

# Qualitative palette for cell-type groups — distinguishable in print and for
# the common forms of colour-vision deficiency (Okabe–Ito, reordered so the
# first two entries read as a clear pair for an excitatory/inhibitory split).
# Okabe–Ito's yellow is meant for filled areas; as the hairline strokes these
# graphs are made of it washes out on white, so it sits last and is darkened.
_TYPE_COLORS = [
    (0.000, 0.447, 0.698),   # blue
    (0.835, 0.369, 0.000),   # vermillion
    (0.000, 0.620, 0.451),   # bluish green
    (0.800, 0.475, 0.655),   # reddish purple
    (0.337, 0.706, 0.913),   # sky blue
    (0.902, 0.624, 0.000),   # orange
    (0.690, 0.640, 0.090),   # darkened yellow
]
_UNASSIGNED_COLOR = (0.65, 0.65, 0.65)
_WHOLE_COLOR = (0.35, 0.35, 0.35)


def group_colors(names: list[str]) -> dict[str, tuple]:
    """Stable colour per group name, with fixed colours for the two
    pseudo-groups (:data:`WHOLE_NETWORK`, ``"Unassigned"``)."""
    colors: dict[str, tuple] = {}
    i = 0
    for name in names:
        if name == WHOLE_NETWORK:
            colors[name] = _WHOLE_COLOR
        elif name == "Unassigned":
            colors[name] = _UNASSIGNED_COLOR
        else:
            colors[name] = _TYPE_COLORS[i % len(_TYPE_COLORS)]
            i += 1
    return colors


# Above this many drawn edges a spatial plot is an unreadable hairball, so only
# the strongest EDGE_DISPLAY_LIMIT are rendered — always annotated on the
# figure, never silently. Metrics are computed on the full graph regardless.
# 2P peak/STTC networks routinely exceed 80% density, so this bites often.
EDGE_DISPLAY_LIMIT = 3000


def _edge_segments(
    adj: np.ndarray,
    coords: np.ndarray,
    keep: np.ndarray | None = None,
    limit: int | None = EDGE_DISPLAY_LIMIT,
) -> tuple[list, np.ndarray, int]:
    """Line segments + weights for above-zero upper-triangle edges.

    ``keep`` is an optional ``(n, n)`` boolean mask selecting which edges to
    include (e.g. only within-group ones). ``limit`` keeps only the strongest
    that many edges.

    Returns ``(segments, weights, n_total)`` — ``n_total`` being the edge count
    *before* the limit, so callers can report what was dropped.
    """
    iu = np.triu_indices(adj.shape[0], k=1)
    weights = adj[iu]
    sel = weights > 0
    if keep is not None:
        sel &= keep[iu]
    rows, cols, weights = iu[0][sel], iu[1][sel], weights[sel]
    n_total = int(weights.size)

    if limit is not None and n_total > limit:
        strongest = np.argpartition(weights, n_total - limit)[n_total - limit:]
        rows, cols, weights = rows[strongest], cols[strongest], weights[strongest]

    segments = [
        [(coords[r, 0], coords[r, 1]), (coords[c, 0], coords[c, 1])]
        for r, c in zip(rows, cols)
    ]
    return segments, weights, n_total


def _draw_edges(ax, segments, weights, color, w_max: float, alpha=1.0, zorder=1,
                crowding_n: int | None = None):
    """Draw edges as a single LineCollection, width scaled by weight.

    One collection rather than per-edge ``plot`` calls: a dense 2P network has
    tens of thousands of edges, and the per-artist overhead dominates otherwise.
    Line width and opacity both taper as the collection grows, so a dense graph
    reads as a texture instead of a solid block.

    ``crowding_n`` overrides the edge count that tapering is derived from. Pass
    the figure's *total* edge count when several groups share one axes,
    otherwise a small group is drawn bold against a faded large one and reads
    as the dominant structure when it is the opposite.
    """
    from matplotlib.collections import LineCollection

    if not segments:
        return
    n = crowding_n if crowding_n is not None else len(segments)
    max_width = 2.5 if n < 500 else (1.2 if n < 2000 else 0.6)
    crowding = min(1.0, 400 / max(n, 1)) ** 0.35
    widths = 0.15 + max_width * (np.asarray(weights) / max(w_max, 1e-12))
    ax.add_collection(LineCollection(
        segments, linewidths=widths, colors=[color],
        alpha=alpha * max(crowding, 0.12), zorder=zorder,
    ))


def _edge_caption(n_drawn: int, n_total: int) -> str:
    """Edge-count text, stating the display cap whenever it applied."""
    if n_drawn < n_total:
        return f"{n_total} edges (strongest {n_drawn} drawn)"
    return f"{n_total} edges"


def _style_spatial_axes(ax, coords: np.ndarray) -> None:
    pad = 0.05 * max(np.ptp(coords[:, 0]), np.ptp(coords[:, 1]), 1e-9)
    ax.set_xlim(coords[:, 0].min() - pad, coords[:, 0].max() + pad)
    ax.set_ylim(coords[:, 1].max() + pad, coords[:, 1].min() - pad)  # image convention
    ax.set_aspect("equal")
    ax.axis("off")


def plot_subnetwork_spatial(
    adj_m: np.ndarray,
    coords: np.ndarray,
    groups: CellTypeGroups,
    out_path: Path,
    title: str = "",
    node_size: float = 22.0,
) -> None:
    """Whole network with nodes coloured by cell type and edges by mixing.

    Between-group edges are drawn first in pale grey so the within-group
    structure — the thing the subnetwork analysis is about — sits on top.
    Nodes belonging to more than one group get a second, smaller ring in the
    other group's colour (the same convention MATLAB's
    ``StandardisedNetworkPlot.m`` uses for cell types).
    """
    adj = np.asarray(adj_m, dtype=float).copy()
    np.fill_diagonal(adj, 0.0)
    coords = np.asarray(coords, dtype=float)
    colors = group_colors(groups.names)
    w_max = float(adj.max()) if adj.size else 1.0

    fig, ax = plt.subplots(figsize=(9, 9))
    fig.patch.set_facecolor("white")

    within_any = np.zeros(adj.shape, dtype=bool)
    for i in range(groups.n_groups):
        m = groups.masks[:, i]
        within_any |= np.outer(m, m)

    # Collect every group's edges before drawing any, so all collections can
    # share one crowding scale (see _draw_edges).
    layers = [((0.75, 0.75, 0.75), 0.45, 1,
               "between-type", _edge_segments(adj, coords, keep=~within_any))]
    for i, name in enumerate(groups.names):
        m = groups.masks[:, i]
        layers.append((colors[name], 0.85, 2, name,
                       _edge_segments(adj, coords, keep=np.outer(m, m))))
    total_drawn = sum(len(segs) for *_, (segs, _, _) in layers)

    captions = []
    for color, alpha, zorder, label, (segs, wts, n_edges) in layers:
        _draw_edges(ax, segs, wts, color, w_max, alpha=alpha, zorder=zorder,
                    crowding_n=total_drawn)
        captions.append(f"{label}: {_edge_caption(len(segs), n_edges)}")

    assigned = groups.masks.any(axis=1) if groups.n_groups else np.zeros(len(coords), bool)
    ax.scatter(coords[~assigned, 0], coords[~assigned, 1], s=node_size * 0.5,
               c=[_UNASSIGNED_COLOR], edgecolors="none", zorder=3)

    # Concentric rings (large first) let a node in several groups show all of
    # them — MATLAB's StandardisedNetworkPlot.m convention. When memberships
    # are disjoint no rings are needed, and shrinking later groups would just
    # make them read as less important, so keep every node the same size.
    overlapping = groups.n_groups > 1 and bool((groups.masks.sum(axis=1) > 1).any())
    sizes = (np.linspace(1.0, 0.45, groups.n_groups) * node_size if overlapping
             else np.full(max(groups.n_groups, 1), node_size))
    for i, name in enumerate(groups.names):
        m = groups.masks[:, i]
        ax.scatter(coords[m, 0], coords[m, 1], s=sizes[i], c=[colors[name]],
                   edgecolors="white", linewidths=0.3, zorder=4 + i)

    handles = [plt.Line2D([], [], marker="o", linestyle="", color=colors[n],
                          markersize=7, label=f"{n} (n={int(groups.masks[:, i].sum())})")
               for i, n in enumerate(groups.names)]
    if (~assigned).any():
        handles.append(plt.Line2D([], [], marker="o", linestyle="", color=_UNASSIGNED_COLOR,
                                  markersize=5, label=f"Unassigned (n={int((~assigned).sum())})"))
    handles.append(plt.Line2D([], [], color=(0.75, 0.75, 0.75), lw=1.5, label="between-type edge"))
    ax.legend(handles=handles, loc="upper right", fontsize=8, frameon=False)

    _style_spatial_axes(ax, coords)
    ax.set_title("\n".join([title] + ["  ·  ".join(captions)]) if title
                 else "  ·  ".join(captions), fontsize=10)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_subnetwork_panels(
    adj_m: np.ndarray,
    coords: np.ndarray,
    groups: CellTypeGroups,
    out_path: Path,
    title: str = "",
    node_size: float = 20.0,
) -> None:
    """One panel per group showing only that group's induced subgraph.

    Every panel shares the whole recording's axis limits and edge-width scale,
    so the panels are directly comparable to each other and to the leading
    whole-network reference panel. Non-member cells stay visible as faint grey
    dots to keep the spatial context.
    """
    adj = np.asarray(adj_m, dtype=float).copy()
    np.fill_diagonal(adj, 0.0)
    coords = np.asarray(coords, dtype=float)
    colors = group_colors(groups.names)
    w_max = float(adj.max()) if adj.size else 1.0

    panels = [WHOLE_NETWORK] + list(groups.names)
    n_cols = min(3, len(panels))
    n_rows = int(np.ceil(len(panels) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5.2 * n_cols, 5.2 * n_rows),
                             squeeze=False)
    fig.patch.set_facecolor("white")

    for ax, name in zip(axes.ravel(), panels):
        if name == WHOLE_NETWORK:
            mask = np.ones(adj.shape[0], dtype=bool)
            color = _WHOLE_COLOR
        else:
            mask = groups.masks[:, groups.names.index(name)]
            color = colors[name]

        ax.scatter(coords[:, 0], coords[:, 1], s=node_size * 0.35,
                   c=[(0.87, 0.87, 0.87)], edgecolors="none", zorder=1)
        segs, wts, n_edges = _edge_segments(adj, coords, keep=np.outer(mask, mask))
        _draw_edges(ax, segs, wts, color, w_max, alpha=0.8, zorder=2)
        ax.scatter(coords[mask, 0], coords[mask, 1], s=node_size, c=[color],
                   edgecolors="white", linewidths=0.3, zorder=3)

        n_nodes = int(mask.sum())
        possible = n_nodes * (n_nodes - 1) / 2
        dens = n_edges / possible if possible else np.nan
        ax.set_title(f"{name}\n{n_nodes} cells · {_edge_caption(len(segs), n_edges)}"
                     f" · density {dens:.3f}", fontsize=10)
        _style_spatial_axes(ax, coords)

    for ax in axes.ravel()[len(panels):]:
        ax.axis("off")

    if title:
        fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_node_metrics_by_group(
    node_df: pd.DataFrame,
    metrics: list[str],
    out_path: Path,
    title: str = "",
    rng: np.random.Generator | None = None,
) -> None:
    """Half-violin distributions of whole-network node metrics, split by group.

    These are metrics of each cell's role in the **whole** network — the
    subnetworks are used only to label the cells, not to rebuild the graph. So
    a higher participation coefficient for inhibitory cells here means they
    connect across more modules of the full network, which is a different (and
    usually more interesting) claim than the induced-subgraph comparison in
    :func:`plot_subnetwork_metric_bars`.

    Uses the same ``HalfViolinPlot.m`` renderer as the rest of the pipeline:
    KDE on the right, jittered points on the left, mean ± SEM in black.
    """
    if node_df.empty:
        return
    metrics = [m for m in metrics if m in node_df.columns]
    if not metrics:
        return

    order = [g for g in node_df["Group"].unique() if g != "Unassigned"]
    order += [g for g in node_df["Group"].unique() if g == "Unassigned"]
    colors = group_colors(order)

    n_cols = min(3, len(metrics))
    n_rows = int(np.ceil(len(metrics) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.0 * n_cols, 3.4 * n_rows),
                             squeeze=False)
    fig.patch.set_facecolor("white")

    for ax, metric in zip(axes.ravel(), metrics):
        for pos, grp in enumerate(order, start=1):
            values = node_df.loc[node_df["Group"] == grp, metric].to_numpy(dtype=float)
            _half_violin(ax, values, pos=pos, colour=colors[grp], width=0.3, rng=rng)
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels([f"{g}\n(n={int((node_df['Group'] == g).sum())})" for g in order],
                           fontsize=8)
        ax.set_xlim(0.4, len(order) + 0.8)
        ax.set_ylabel(metric, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)

    for ax in axes.ravel()[len(metrics):]:
        ax.axis("off")

    if title:
        fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_subnetwork_metric_bars(
    summary: pd.DataFrame,
    metrics: list[str],
    out_path: Path,
    title: str = "",
) -> None:
    """Recording-level metrics recomputed on each group's induced subgraph.

    Unlike :func:`plot_node_metrics_by_group`, these describe the subnetwork as
    a graph in its own right (its density, global efficiency, small-worldness,
    …). The :data:`WHOLE_NETWORK` bar is the whole-network reference.

    Density-like metrics are strongly size-dependent, so each bar is annotated
    with the number of active nodes the metric was computed over — a
    difference between two groups of very different size should be read with
    that in mind.
    """
    if summary.empty:
        return
    metrics = [m for m in metrics if m in summary.columns
               and summary[m].notna().any()]
    if not metrics:
        return

    order = list(summary["Group"])
    colors = group_colors(order)
    n_cols = min(3, len(metrics))
    n_rows = int(np.ceil(len(metrics) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.0 * n_cols, 3.4 * n_rows),
                             squeeze=False)
    fig.patch.set_facecolor("white")

    for ax, metric in zip(axes.ravel(), metrics):
        values = summary[metric].to_numpy(dtype=float)
        bars = ax.bar(range(len(order)), values,
                      color=[colors[g] for g in order], width=0.65)
        finite = values[np.isfinite(values)]
        span = (max(finite.max(), 0.0) - min(finite.min(), 0.0)) if finite.size else 1.0
        offset = 0.02 * max(span, 1e-9)
        for bar, value, a_n in zip(bars, values, summary["aN"]):
            if not np.isfinite(value):
                continue
            # Sit outside the bar on whichever side it grows — an all-negative
            # metric (SWw is routinely negative) would otherwise print the
            # label inside the bar, in low-contrast grey on the bar colour.
            above = value >= 0
            ax.text(bar.get_x() + bar.get_width() / 2,
                    value + (offset if above else -offset), f"n={int(a_n)}",
                    ha="center", va="bottom" if above else "top",
                    fontsize=7, color="0.3")
        ax.margins(y=0.12)
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(order, fontsize=8, rotation=20, ha="right")
        ax.set_ylabel(metric, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)

    for ax in axes.ravel()[len(metrics):]:
        ax.axis("off")

    if title:
        fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_edge_mix_matrix(
    edge_mix: pd.DataFrame,
    groups: CellTypeGroups,
    out_path: Path,
    title: str = "",
) -> None:
    """Group × group heatmaps of edge density and mean edge weight.

    The diagonal is within-type connectivity, the off-diagonal between-type.
    A diagonal that dominates means cell types wire preferentially among
    themselves — assortative mixing by type.
    """
    if edge_mix.empty or groups.n_groups == 0:
        return

    names = groups.names
    n = len(names)
    fields = [("Density", "edge density"), ("MeanWeightNonzero", "mean weight (edges present)")]

    fig, axes = plt.subplots(1, len(fields), figsize=(5.6 * len(fields), 5.0), squeeze=False)
    fig.patch.set_facecolor("white")

    for ax, (field, label) in zip(axes.ravel(), fields):
        mat = np.full((n, n), np.nan)
        for _, row in edge_mix.iterrows():
            if row["GroupA"] not in names or row["GroupB"] not in names:
                continue
            i, j = names.index(row["GroupA"]), names.index(row["GroupB"])
            mat[i, j] = mat[j, i] = row[field]

        im = ax.imshow(mat, cmap="viridis")
        ax.set_xticks(range(n), names, fontsize=9, rotation=25, ha="right")
        ax.set_yticks(range(n), names, fontsize=9)
        for i in range(n):
            for j in range(n):
                if not np.isfinite(mat[i, j]):
                    continue
                # Contrast against the cell's actual colour, not against the
                # data mean — viridis is dark at the low end and bright at the
                # high end regardless of what the numbers happen to be.
                dark_cell = float(im.norm(mat[i, j])) < 0.6
                ax.text(j, i, f"{mat[i, j]:.3g}", ha="center", va="center", fontsize=9,
                        color="white" if dark_cell else "black")
        ax.set_title(label, fontsize=10)
        fig.colorbar(im, ax=ax, fraction=0.046)

    if title:
        fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
