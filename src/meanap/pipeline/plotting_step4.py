"""Step 4 check plots, port of ``plotConnectivityProperties.m``.

Only the connectivity-stats plot is ported (adjacency matrix + max/mean STTC
+ node degree / node strength / edge weight distributions) — it's the one
built entirely from metrics already in `network_metrics.py`. The other
`4A_IndividualNetworkAnalysis` plots MATLAB produces (spatial network plots,
node cartography, null-model panels, controllability) either need electrode
coordinates (not yet ported — see ``python/PIPELINE_PORT_STATUS.md``) or
depend on network metrics that are out of scope (modularity, participation
coefficient, hub classification).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from meanap.network_plot import plot_network
from meanap.pipeline.channel_layout import get_coords_from_layout


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
) -> None:
    """Spatial network plot, port of the base ``2_MEA_NetworkPlot.png`` from
    ``StandardisedNetworkPlot.m`` (reuses ``network_plot.py``'s
    ``plot_network``, built for the Network Viewer GUI tab, since it's
    already a generic MEA-plot renderer).

    Electrode coordinates come from ``channel_layout.get_coords_from_layout``.
    Active channels without a coordinate entry (e.g. grounded corner
    electrodes on MCS-family layouts) are silently dropped from the plot —
    they still contribute to the underlying metrics, just not this figure.
    """
    layout_channels, layout_coords = get_coords_from_layout(channel_layout)
    coord_by_channel = dict(zip(layout_channels.tolist(), map(tuple, layout_coords)))

    has_coord = np.array([int(ch) in coord_by_channel for ch in channels_active])
    if not np.any(has_coord):
        return
    idx = np.nonzero(has_coord)[0]

    sub = adj_m_sub[np.ix_(idx, idx)]
    coords = np.array([coord_by_channel[int(channels_active[i])] for i in idx])
    z_sub = z[idx]
    z2_sub = z2[idx] if z2 is not None else None

    fig, ax = plt.subplots(figsize=(8, 8))
    plot_network(
        ax, sub, coords, edge_thresh, z_sub, z2_sub, z2_name,
        title=f"{recording_name}  {lag_ms} ms lag",
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
