"""Step 3 diagnostic plots — probabilistic-thresholding stability check.

Port of ``significance_distribution_plots.m`` (the figure ``adjM_thr_checkreps.m``
saves as ``<recording><lag>msLagProbThreshCheck.png`` under
``3_EdgeThresholdingCheck``). Shows how the significance threshold stabilises as
the number of circular-shift surrogate repetitions grows.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _upper_unique(mat: np.ndarray) -> np.ndarray:
    """Values of the strict upper triangle (unique off-diagonal edges).

    MATLAB keeps one triangular half via ``triu(rot90(ones))`` before averaging;
    the adjacency/threshold matrices are symmetric, so any unique half gives the
    same mean/variance. We use the strict upper triangle.
    """
    n = mat.shape[0]
    iu = np.triu_indices(n, k=1)
    return mat[iu]


def plot_prob_thresh_check(
    dist1: list[np.ndarray],
    rep_val: np.ndarray,
    adj_m: np.ndarray,
    out_path: Path,
    rng: np.random.Generator | None = None,
) -> None:
    """Draw the probabilistic-thresholding stability check figure.

    Parameters mirror ``significance_distribution_plots.m``:
    ``dist1[i]`` is the per-edge threshold matrix after ``rep_val[i]`` surrogate
    repetitions, ``adj_m`` is the raw STTC matrix.

    Layout (3 rows):
      1. Average threshold value (± std band, left axis) and coefficient of
         variation (right axis) vs. number of repeats.
      2. Threshold trajectories of 12 randomly-sampled edges vs. repeats.
      3. Five heatmaps of the edges that would be discarded at five repeat
         checkpoints.
    """
    if rng is None:
        rng = np.random.default_rng()
    n_check = len(dist1)
    if n_check == 0:
        return

    a = np.asarray(rep_val, dtype=float)
    c = (0.471, 0.674, 0.188)  # green (MATLAB "wild-type" colour)

    # ── Row 1: mean threshold ± std, and coefficient of variation ────────────
    mean_thr = np.array([np.nanmean(_upper_unique(dist1[i])) for i in range(n_check)])
    # Per-checkpoint std: std across repeats for each edge, averaged (as variance)
    std_thr = np.zeros(n_check)
    for i in range(n_check):
        # variance across the threshold trajectory up to checkpoint i, per edge
        stack = np.stack([_upper_unique(dist1[k]) for k in range(i + 1)], axis=0)
        var_per_edge = np.var(stack, axis=0)
        std_thr[i] = np.sqrt(np.mean(var_per_edge))
    with np.errstate(divide="ignore", invalid="ignore"):
        coeff_var = np.where(mean_thr != 0, std_thr / mean_thr, np.nan)

    fig = plt.figure(figsize=(12, 8.5))
    gs = fig.add_gridspec(3, 5, height_ratios=[1, 1, 1.1], hspace=0.45, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, :])
    ax1.fill_between(a, mean_thr - std_thr, mean_thr + std_thr, color=c, alpha=0.3,
                     edgecolor="none")
    ax1.plot(a, mean_thr, "-", color=c, lw=2)
    ax1.set_xlabel("Number of Repeats")
    ax1.set_ylabel("Average threshold value", color=(0, 0.4, 0))
    ax1.set_xlim(0, a[-1])
    ax1.set_title("Change in threshold")
    ax1.spines["top"].set_visible(False)
    ax1.tick_params(direction="out")
    ax1b = ax1.twinx()
    ax1b.plot(a, coeff_var, "-", color="k", lw=1)
    ax1b.set_ylabel("Coefficient of Variance")
    ax1b.spines["top"].set_visible(False)
    ax1b.tick_params(direction="out")

    # ── Row 2: threshold trajectories of 12 random edges ─────────────────────
    ax2 = fig.add_subplot(gs[1, :])
    traj = np.stack([_upper_unique(d) for d in dist1], axis=1)  # (n_edges, n_check)
    n_edges = traj.shape[0]
    n_sample = min(12, n_edges)
    sel = rng.integers(0, n_edges, size=n_sample) if n_edges > 0 else np.array([], dtype=int)
    cmap = plt.cm.inferno
    for j, e in enumerate(sel):
        ax2.plot(a, traj[e], "-", color=cmap(j / max(n_sample - 1, 1)), lw=1)
    ax2.set_xlim(0, a[-1])
    ax2.set_xlabel("Number of Repeats")
    ax2.set_ylabel("Threshold value")
    ax2.set_title("Raw Data Samples")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.tick_params(direction="out")

    # ── Row 3: discarded-edge heatmaps at 5 checkpoints ──────────────────────
    n_maps = min(5, n_check)
    idxs = np.round(np.linspace(0, n_check - 1, n_maps)).astype(int)
    n_nodes = adj_m.shape[0]
    last_im = None
    for q, pi in enumerate(idxs):
        ax = fig.add_subplot(gs[2, q])
        use = dist1[pi]
        blank = np.zeros((n_nodes, n_nodes))
        mask = (use > adj_m) & (adj_m != 0)
        blank[mask] = adj_m[mask]
        last_im = ax.imshow(blank, aspect="equal", origin="upper")
        ax.set_title(f"discarded (rep{int(a[pi]) - 1})", fontsize=8)
        ax.set_xlabel("Electrode", fontsize=8)
        if q == 0:
            ax.set_ylabel("Electrode", fontsize=8)
        ax.tick_params(direction="out", labelsize=7)
    if last_im is not None:
        cbar = fig.colorbar(last_im, ax=fig.axes[-1], fraction=0.046, pad=0.04)
        cbar.set_label("Edge weight", fontsize=8)

    for ax in fig.axes:
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontsize(8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
