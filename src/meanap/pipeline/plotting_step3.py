"""Step 3 diagnostic plots — probabilistic-thresholding stability check.

Port of ``significance_distribution_plots.m`` (the figure ``adjM_thr_checkreps.m``
saves as ``<recording><lag>msLagProbThreshCheck.png`` under
``3_EdgeThresholdingCheck``). Shows how the significance threshold stabilises as
the number of circular-shift surrogate repetitions grows.

The figure is drawn from ``dist1`` — one threshold matrix per checkpoint, so
``n_checkpoints × n × n`` floats, tens of megabytes for a real recording, and
gone the moment step 3 returns. That is why a bundle could not rebuild this
one: the input is both enormous and not otherwise persisted.

Almost none of it is shown, though. Row 1 plots two summary curves; row 2 plots
twelve sampled edge trajectories; row 3 shows five matrices. So, as with the
step-1 checks, this is split into what the figure *displays*
(:class:`EdgeThresholdCheckData`, a few tens of kilobytes) and the drawing that
turns it into a picture — one function, used both by the run and by a viewer
rebuilding from a bundle, so the two cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from meanap.pipeline.figure_output import savefig

__all__ = [
    "EdgeThresholdCheckData",
    "EDGE_CHECK_SUFFIX",
    "compute_edge_threshold_check",
    "draw_edge_threshold_check",
    "plot_prob_thresh_check",
    "save_edge_threshold_check",
    "load_edge_threshold_check",
]

#: Written into ``ExperimentMatFiles`` beside the adjacency, one per recording,
#: with a group of arrays per lag.
EDGE_CHECK_SUFFIX = "_edgecheck.npz"

#: Sampled edge trajectories drawn in row 2.
N_TRAJECTORIES = 12

#: Discarded-edge heatmaps drawn in row 3.
N_MAPS = 5


def _upper_unique(mat: np.ndarray) -> np.ndarray:
    """Values of the strict upper triangle (unique off-diagonal edges).

    MATLAB keeps one triangular half via ``triu(rot90(ones))`` before averaging;
    the adjacency/threshold matrices are symmetric, so any unique half gives the
    same mean/variance. We use the strict upper triangle.
    """
    n = mat.shape[0]
    iu = np.triu_indices(n, k=1)
    return mat[iu]


@dataclass
class EdgeThresholdCheckData:
    """Everything the stability-check figure shows, and nothing else.

    Which twelve edges row 2 samples is decided when this is computed and then
    stored, so a rebuilt figure shows the same edges the run's own did rather
    than a fresh draw.
    """

    rep_val: np.ndarray        # (n_check,) repeat count at each checkpoint
    mean_thr: np.ndarray       # (n_check,) row 1, left axis
    std_thr: np.ndarray        # (n_check,) row 1, the band
    trajectories: np.ndarray   # (n_sample, n_check) row 2
    map_reps: np.ndarray       # (n_maps,) the repeat count each map is labelled with
    #: (n_maps, n, n) the discarded-edge matrices row 3 draws. Mostly zeros, so
    #: they compress to a fraction of their nominal size.
    maps: np.ndarray

    @property
    def n_checkpoints(self) -> int:
        return len(self.rep_val)


def compute_edge_threshold_check(
    dist1: list[np.ndarray],
    rep_val: np.ndarray,
    adj_m: np.ndarray,
    rng: np.random.Generator | None = None,
) -> EdgeThresholdCheckData | None:
    """Reduce the threshold snapshots to what the figure draws.

    ``dist1[i]`` is the per-edge threshold matrix after ``rep_val[i]`` surrogate
    repetitions and ``adj_m`` is the raw STTC matrix — the same inputs
    ``significance_distribution_plots.m`` takes. Returns ``None`` when there are
    no checkpoints, which is what the drawing used to treat as "nothing to do".
    """
    if rng is None:
        rng = np.random.default_rng()
    n_check = len(dist1)
    if n_check == 0:
        return None

    a = np.asarray(rep_val, dtype=float)

    # Row 1: mean threshold, and the std of each edge's trajectory *so far*.
    mean_thr = np.array([np.nanmean(_upper_unique(dist1[i])) for i in range(n_check)])
    std_thr = np.zeros(n_check)
    for i in range(n_check):
        stack = np.stack([_upper_unique(dist1[k]) for k in range(i + 1)], axis=0)
        std_thr[i] = np.sqrt(np.mean(np.var(stack, axis=0)))

    # Row 2: twelve sampled edges, drawn in the same order as before so the
    # colour ramp lands on the same trajectories.
    traj = np.stack([_upper_unique(d) for d in dist1], axis=1)  # (n_edges, n_check)
    n_edges = traj.shape[0]
    n_sample = min(N_TRAJECTORIES, n_edges)
    sel = (rng.integers(0, n_edges, size=n_sample) if n_edges > 0
           else np.array([], dtype=int))
    sampled = traj[sel] if len(sel) else np.zeros((0, n_check))

    # Row 3: the discarded-edge matrices themselves, at five checkpoints.
    n_maps = min(N_MAPS, n_check)
    idxs = np.round(np.linspace(0, n_check - 1, n_maps)).astype(int)
    n_nodes = adj_m.shape[0]
    maps = np.zeros((n_maps, n_nodes, n_nodes), dtype=np.float32)
    for q, pi in enumerate(idxs):
        mask = (dist1[pi] > adj_m) & (adj_m != 0)
        maps[q][mask] = adj_m[mask]

    return EdgeThresholdCheckData(
        rep_val=a,
        mean_thr=mean_thr,
        std_thr=std_thr,
        trajectories=np.asarray(sampled, dtype=np.float32),
        map_reps=a[idxs],
        maps=maps,
    )


def save_edge_threshold_check(
    path: Path | str, per_lag: dict[int, EdgeThresholdCheckData],
) -> Path:
    """Write one recording's checks — all lags — to a single ``.npz``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {"lags": np.asarray(sorted(per_lag),
                                                        dtype=np.int64)}
    for lag, data in per_lag.items():
        for field in ("rep_val", "mean_thr", "std_thr", "trajectories",
                      "map_reps", "maps"):
            arrays[f"{lag}ms_{field}"] = getattr(data, field)
    np.savez_compressed(path, **arrays)
    return path


def load_edge_threshold_check(
    path: Path | str, lag: int,
) -> EdgeThresholdCheckData | None:
    """Read back one lag's check data, or ``None`` if that lag isn't stored."""
    with np.load(path) as z:
        if f"{lag}ms_rep_val" not in z.files:
            return None
        return EdgeThresholdCheckData(
            **{field: z[f"{lag}ms_{field}"]
               for field in ("rep_val", "mean_thr", "std_thr", "trajectories",
                             "map_reps", "maps")}
        )


def stored_lags(path: Path | str) -> list[int]:
    """Which lags a check file holds."""
    with np.load(path) as z:
        return [int(v) for v in z["lags"]] if "lags" in z.files else []


def draw_edge_threshold_check(data: EdgeThresholdCheckData, out_path: Path) -> Path:
    """Draw the stability check figure.

    Layout (3 rows):
      1. Average threshold value (± std band, left axis) and coefficient of
         variation (right axis) vs. number of repeats.
      2. Threshold trajectories of 12 sampled edges vs. repeats.
      3. Five heatmaps of the edges that would be discarded at five repeat
         checkpoints.
    """
    a = np.asarray(data.rep_val, dtype=float)
    mean_thr, std_thr = data.mean_thr, data.std_thr
    c = (0.471, 0.674, 0.188)  # green (MATLAB "wild-type" colour)

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
    n_sample = len(data.trajectories)
    cmap = plt.cm.inferno
    for j, trajectory in enumerate(data.trajectories):
        ax2.plot(a, trajectory, "-", color=cmap(j / max(n_sample - 1, 1)), lw=1)
    ax2.set_xlim(0, a[-1])
    ax2.set_xlabel("Number of Repeats")
    ax2.set_ylabel("Threshold value")
    ax2.set_title("Raw Data Samples")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.tick_params(direction="out")

    # ── Row 3: discarded-edge heatmaps at 5 checkpoints ──────────────────────
    last_im = None
    for q, blank in enumerate(data.maps):
        ax = fig.add_subplot(gs[2, q])
        last_im = ax.imshow(blank, aspect="equal", origin="upper")
        ax.set_title(f"discarded (rep{int(data.map_reps[q]) - 1})", fontsize=8)
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

    savefig(fig, out_path, default_dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_prob_thresh_check(
    dist1: list[np.ndarray],
    rep_val: np.ndarray,
    adj_m: np.ndarray,
    out_path: Path,
    rng: np.random.Generator | None = None,
) -> None:
    """Compute and draw in one call — step 3's original entry point."""
    data = compute_edge_threshold_check(dist1, rep_val, adj_m, rng=rng)
    if data is not None:
        draw_edge_threshold_check(data, out_path)
