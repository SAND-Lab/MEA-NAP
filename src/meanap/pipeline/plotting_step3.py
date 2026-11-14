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

import numpy as np

from meanap.pipeline.atomic import atomic_savez

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
    atomic_savez(path, compressed=True, **arrays)
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
         checkpoints, on one colour scale so they can be compared.
    """
    from matplotlib import colormaps

    from meanap.native.chart import (Band, Cells, Chart, ColourBar, Legend, LegendItem,
                                     Line, Panel, rgba)
    from meanap.native.chart_paint import save_chart

    a = np.asarray(data.rep_val, dtype=float)
    mean_thr = np.asarray(data.mean_thr, dtype=float)
    std_thr = np.asarray(data.std_thr, dtype=float)
    c = (0.471, 0.674, 0.188)  # green (MATLAB "wild-type" colour)
    with np.errstate(divide="ignore", invalid="ignore"):
        coeff_var = np.where(mean_thr != 0, std_thr / mean_thr, np.nan)
    reps = [f"after {int(n)} repeats" for n in a]
    text = dict(title_size=12, label_size=10, tick_size=8)
    xlim = (0.0, float(a[-1])) if len(a) and a[-1] > 0 else None

    threshold = Panel(
        cell=(0, 0), span=(1, N_MAPS), sharex="repeats", xlim=xlim, zoom=(True, False),
        marks=[Band(a, mean_thr - std_thr, mean_thr + std_thr, colour=rgba(c, 0.3),
                    key="threshold"),
               Line(a, mean_thr, colour=rgba(c), width=2, key="threshold",
                    hover=[f"{r}: threshold {m:.4g} ± {sd:.2g}"
                           for r, m, sd in zip(reps, mean_thr, std_thr)])],
        title="Change in threshold", xlabel="Number of Repeats",
        ylabel="Average threshold value", grid="",
        legend=Legend([LegendItem("average threshold ± SD", rgba(c), key="threshold"),
                       LegendItem("coefficient of variation", rgba("black"), key="cv")],
                      loc="best", size=8), **text)
    variation = Panel(
        cell=(0, 0), span=(1, N_MAPS), twin=True, sharex="repeats", xlim=xlim,
        zoom=(True, False),
        marks=[Line(a, coeff_var, colour=rgba("black"), width=1, key="cv",
                    hover=[f"{r}: coefficient of variation {v:.3g}"
                           for r, v in zip(reps, coeff_var)])],
        ylabel="Coefficient of Variance", **text)

    trajectories = np.asarray(data.trajectories, dtype=float)
    ramp = colormaps["inferno"]
    n_sample = len(trajectories)
    lines = [Line(a, t, colour=rgba(ramp(j / max(n_sample - 1, 1))), width=1,
                  key=f"edge {j + 1}",
                  hover=[f"sampled edge {j + 1}, {r}: threshold {v:.4g}"
                         for r, v in zip(reps, t)])
             for j, t in enumerate(trajectories)]
    samples = Panel(cell=(1, 0), span=(1, N_MAPS), sharex="repeats", xlim=xlim,
                    zoom=(True, False), marks=lines, title="Raw Data Samples",
                    xlabel="Number of Repeats", ylabel="Threshold value", grid="", **text)

    maps = [np.asarray(m, dtype=float) for m in data.maps]
    high = max([float(np.nanmax(m)) for m in maps if m.size] + [0.0]) or 1.0
    panels = [threshold, variation, samples]
    for q, blank in enumerate(maps):
        rep = int(data.map_reps[q]) - 1

        def hover(i, j, blank=blank, rep=rep):
            if i == j:
                return ""
            v = blank[i, j]
            return (f"electrodes {i + 1} ↔ {j + 1}\n"
                    + (f"discarded at rep {rep} (weight {v:.3g})" if v else "kept"))

        last = q == len(maps) - 1
        panels.append(Panel(
            cell=(2, q), marks=[Cells(blank, cmap="viridis", low=0.0, high=high, hover=hover)],
            title=f"discarded edges (rep{rep})", title_size=9, xlabel="Electrode",
            ylabel="Electrode" if q == 0 else "", label_size=9, tick_size=8,
            y_down=True, equal=True, grid="",
            colour_bar=ColourBar("viridis", 0.0, high, label="Edge weight", fraction=0.046)
            if last else None))
    chart = Chart(panels, size=(12, 8.5), grid=(3, N_MAPS), heights=[1, 1, 1.1])
    return save_chart(chart, out_path)


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
