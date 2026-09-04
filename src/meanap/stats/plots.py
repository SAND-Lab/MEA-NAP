"""Figures for the statistics and machine-learning step.

Drawing rules, which are the ones the rest of the pipeline's figures follow:

* Groups and ages take their colours from
  :class:`~meanap.pipeline.palette.ColorScheme`, so a genotype is the same
  colour here as on every 4B comparison figure in the same output folder, and
  a run's ``group_colors``/``age_colors`` settings reach these plots too.
* Anything signed — an effect size, a correlation, a coefficient — gets a
  diverging map centred on zero with a neutral middle, so the sign is visible
  without reading the colourbar. Anything unsigned gets a single-hue sequential
  map. Never a rainbow for either.
* Spines off, ticks out, no gridlines competing with the data: MATLAB's
  ``aesthetics.m``, which every other figure in the folder is drawn with.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from meanap.pipeline.figure_output import savefig
from meanap.pipeline.palette import DEFAULT_SCHEME, GROUP_SCHEMES, ColorScheme
from meanap.stats.density_sweep import CONTROL_LEVELS, SWEEP_METRICS

__all__ = [
    "plot_confusion",
    "plot_correlation_grid",
    "plot_correlation_matrix",
    "plot_decoding_by_age",
    "plot_decoding_importance",
    "plot_decoding_scores",
    "plot_control_effects",
    "plot_density_context",
    "plot_genotype_effect_by_age",
    "plot_metric_values",
    "plot_density_sweep",
    "plot_selection_check",
    "plot_size_control",
    "plot_effect_heatmap",
    "plot_family_alone_vs_unique",
    "plot_family_contributions",
    "plot_lda_projection",
    "plot_measure_agreement",
    "plot_measure_concordance",
    "plot_measure_decoding",
    "plot_measure_differences",
    "plot_metric_trajectories",
    "plot_observed_vs_predicted",
    "plot_pca_variance",
    "plot_regression_scores",
    "plot_shapley_across_ages",
    "plot_shapley_by_age",
    "plot_topology_controlled",
    "plot_variance_decomposition",
]

#: Diverging map for signed quantities. Two hues either side of a neutral
#: midpoint; the reversed form puts red at the positive end, which is the
#: convention in the comparison figures already in the output folder.
DIVERGING = "RdBu_r"
#: Single-hue sequential map for unsigned magnitudes.
SEQUENTIAL = "viridis"
#: Ink for text and marks that carry no identity of their own.
INK = "#222222"
MUTED = "#8a8a8a"


def _bare(ax) -> None:
    """MATLAB ``aesthetics.m``: no top/right spines, ticks pointing out."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out")


def _save(fig, path: Path, *, dpi: int = 200) -> Path:
    savefig(fig, Path(path), default_dpi=dpi, bbox_inches="tight",
            facecolor="white")
    plt.close(fig)
    return Path(path)


def _group_colors(groups, scheme: ColorScheme) -> dict:
    """Colour per group, assigned in the batch's group order and never cycled.

    Keyed by group *name* rather than by position, so a figure that shows a
    subset of the groups keeps the same colour for each — a filter must not
    repaint the survivors.
    """
    return dict(zip(groups, scheme.groups(len(groups))))


def _age_colors(ages, scheme: ColorScheme) -> dict:
    return dict(zip(ages, scheme.ages(len(ages))))


#: Column names that read badly in a figure title. The tables keep the column
#: name; only the prose the reader sees is translated.
_TARGET_LABELS = {"Grp": "genotype", "eGrp": "genotype",
                  "DIV": "age (DIV)", "AgeDiv": "age (DIV)"}


def _target_label(target: str) -> str:
    return _TARGET_LABELS.get(target, target)


def _stars(p: float) -> str:
    if not np.isfinite(p):
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""


# ── comparisons ──────────────────────────────────────────────────────────────

def plot_effect_heatmap(
    table: pd.DataFrame, out_path: Path, *, family: str = "mixed-model",
    alpha: float = 0.05, title: str | None = None,
) -> Path | None:
    """Metrics × model terms, coloured by effect size, starred where significant.

    The one figure that shows a whole run's comparison results at once. Colour
    carries the *size and direction* of each effect and the stars carry
    significance, rather than the usual heatmap of p-values — a p-value map
    makes a huge effect in a small group look identical to a trivial effect in
    a large one.
    """
    from meanap.stats.comparisons import SIGNED_EFFECT_SIZES

    sub = table[table["Family"] == family]
    sub = sub[sub["EffectSizeName"].isin(SIGNED_EFFECT_SIZES)]
    if sub.empty:
        return None

    wide = sub.pivot_table(index="MetricLabel", columns="Term", values="EffectSize")
    pvals = sub.pivot_table(index="MetricLabel", columns="Term", values="PValueFDR")
    wide = wide.dropna(how="all").dropna(axis=1, how="all")
    if wide.empty:
        return None
    pvals = pvals.reindex(index=wide.index, columns=wide.columns)

    # Order metrics by their largest absolute effect, so the rows worth reading
    # are at the top rather than in alphabetical order.
    wide = wide.reindex(wide.abs().max(axis=1).sort_values(ascending=False).index)
    pvals = pvals.reindex(wide.index)

    limit = float(np.nanmax(np.abs(wide.to_numpy()))) or 1.0
    n_rows, n_cols = wide.shape
    fig, ax = plt.subplots(figsize=(max(4.5, 1.5 * n_cols + 2), max(3.0, 0.28 * n_rows + 1.2)))
    mesh = ax.imshow(wide.to_numpy(), cmap=DIVERGING, vmin=-limit, vmax=limit,
                     aspect="auto")

    # Stars sit *on* the cells, so their colour has to follow the cell's
    # lightness; a dark star on a saturated red cell is invisible, which is
    # exactly where the significant effects are.
    norm = matplotlib.colors.Normalize(vmin=-limit, vmax=limit)
    cmap = matplotlib.colormaps[DIVERGING]
    for i in range(n_rows):
        for j in range(n_cols):
            mark = _stars(pvals.iat[i, j])
            value = wide.iat[i, j]
            if not mark or not np.isfinite(value):
                continue
            r, g, b = cmap(norm(value))[:3]
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            ax.text(j, i, mark, ha="center", va="center", fontsize=9,
                    color="white" if luminance < 0.5 else INK, fontweight="bold")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(wide.columns, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(wide.index, fontsize=8)
    ax.set_title(title or f"Effect sizes — {family}", fontsize=11)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    cbar = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Effect size", fontsize=9)
    cbar.outline.set_visible(False)
    ax.text(1.0, -0.06, f"* FDR q < {alpha}   ** q < 0.01   *** q < 0.001",
            transform=ax.transAxes, ha="right", va="top", fontsize=7, color=MUTED)
    return _save(fig, out_path)


def plot_metric_trajectories(
    ds, metrics: list[str], out_path: Path, *, scheme: ColorScheme = DEFAULT_SCHEME,
    n_cols: int = 4, title: str | None = None,
) -> Path | None:
    """Mean ± SEM against age, one small multiple per metric, one line per group.

    Small multiples rather than one crowded axis: these metrics have no common
    unit, and putting two of them on one pair of axes would need a second
    y-scale, which is never the right answer.
    """
    metrics = [m for m in metrics if m in ds.table.columns]
    if not metrics:
        return None
    colors = _group_colors([str(g) for g in ds.groups], scheme)
    n_rows = int(np.ceil(len(metrics) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.1 * n_cols, 2.5 * n_rows),
                             squeeze=False)

    for idx, metric in enumerate(metrics):
        ax = axes[idx // n_cols][idx % n_cols]
        for grp in ds.groups:
            sub = ds.table[ds.table[ds.group_col] == grp]
            values = pd.to_numeric(sub[metric], errors="coerce")
            frame = pd.DataFrame({"age": sub[ds.age_col], "v": values}).dropna()
            if frame.empty:
                continue
            stat = frame.groupby("age")["v"].agg(["mean", "sem", "count"])
            stat = stat[stat["count"] >= 2]
            if stat.empty:
                continue
            colour = colors[str(grp)]
            ax.errorbar(stat.index, stat["mean"], yerr=stat["sem"], marker="o",
                        markersize=4, linewidth=2, capsize=0, color=colour,
                        label=str(grp))
            ax.fill_between(stat.index, stat["mean"] - stat["sem"],
                            stat["mean"] + stat["sem"], color=colour, alpha=0.15,
                            linewidth=0)
        ax.set_title(ds.label(metric), fontsize=9)
        ax.set_xlabel("Age (DIV)", fontsize=8)
        ax.tick_params(labelsize=8)
        _bare(ax)

    for idx in range(len(metrics), n_rows * n_cols):
        axes[idx // n_cols][idx % n_cols].axis("off")

    handles, labels = axes[0][0].get_legend_handles_labels()
    if len(labels) >= 2:
        fig.legend(handles, labels, loc="lower center", ncol=min(4, len(labels)),
                   frameon=False, fontsize=9,
                   bbox_to_anchor=(0.5, -0.02 if n_rows > 1 else -0.08))
    if title:
        fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    return _save(fig, out_path)


# ── correlation ──────────────────────────────────────────────────────────────

def _draw_corr(ax, corr: pd.DataFrame, *, labels, fontsize: float, title=None):
    mesh = ax.imshow(corr.to_numpy(), cmap=DIVERGING, vmin=-1, vmax=1, aspect="equal")
    n = len(corr.columns)
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, rotation=90, fontsize=fontsize)
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=fontsize)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title, fontsize=9)
    return mesh


def plot_correlation_matrix(res, out_path: Path, *, labeller=None) -> Path | None:
    """The whole feature set's correlation matrix, clustered.

    The effective dimensionality is printed on the figure because it is the
    number the matrix exists to convey: 50 metrics whose spectrum is worth ~5
    independent measurements is a fact about the analysis, not a detail.
    """
    corr = res.overall
    if corr.empty:
        return None
    labels = [labeller(c) if labeller else c for c in corr.columns]
    size = max(5.0, 0.22 * len(corr.columns) + 3.0)
    fig, ax = plt.subplots(figsize=(size, size))
    mesh = _draw_corr(ax, corr, labels=labels,
                      fontsize=7 if len(corr.columns) > 25 else 9)
    ax.set_title(f"Feature correlation ({res.method}), clustered", fontsize=11)
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Correlation", fontsize=9)
    cbar.outline.set_visible(False)
    ax.text(0.0, 1.02,
            f"{len(corr.columns)} metrics, effective dimensionality {res.effective_dim:.1f}",
            transform=ax.transAxes, fontsize=8, color=MUTED)
    return _save(fig, out_path)


def plot_correlation_grid(res, out_path: Path, *, labeller=None) -> Path | None:
    """One correlation matrix per group × age — the port of MATLAB's grid.

    Every panel uses the ordering clustered from the pooled matrix, so a block
    that tightens or loosens with age is visible as a change in one place
    rather than as a reshuffle.
    """
    if not res.per_cell:
        return None
    groups = sorted({g for g, _ in res.per_cell})
    ages = sorted({a for _, a in res.per_cell})
    labels = [labeller(c) if labeller else c for c in res.order]
    fontsize = 5 if len(res.order) > 25 else 7

    fig, axes = plt.subplots(len(groups), len(ages),
                             figsize=(3.2 * len(ages), 3.2 * len(groups)),
                             squeeze=False)
    mesh = None
    for i, grp in enumerate(groups):
        for j, age in enumerate(ages):
            ax = axes[i][j]
            cell = res.per_cell.get((grp, age))
            if cell is None:
                ax.axis("off")
                continue
            show = labels if (i == len(groups) - 1 or j == 0) else [""] * len(labels)
            mesh = _draw_corr(ax, cell, labels=show, fontsize=fontsize,
                              title=f"{grp}  DIV {age:g}")
            if j != 0:
                ax.set_yticklabels([""] * len(labels))
            if i != len(groups) - 1:
                ax.set_xticklabels([""] * len(labels))
    if mesh is not None:
        cbar = fig.colorbar(mesh, ax=axes, fraction=0.015, pad=0.01)
        cbar.set_label("Correlation", fontsize=9)
        cbar.outline.set_visible(False)
    return _save(fig, out_path)


def plot_pca_variance(res, out_path: Path) -> Path | None:
    """Scree plot with the cumulative curve — how many components it takes."""
    var = res.variance_explained
    if var.empty:
        return None
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    n = min(20, len(var))
    ax.bar(var["Component"][:n], var["VarianceExplained"][:n],
           color="#4c72b0", width=0.7)
    ax.set_xlabel("Principal component")
    ax.set_ylabel("Variance explained")
    _bare(ax)

    # The cumulative curve shares the y-axis (both are fractions of variance),
    # so this is one scale, not a dual axis.
    ax.plot(var["Component"][:n], var["CumulativeVariance"][:n], color=INK,
            marker="o", markersize=4, linewidth=2, label="Cumulative")
    ax.axhline(0.9, color=MUTED, linestyle=":", linewidth=1)
    ax.text(n, 0.905, "90%", ha="right", va="bottom", fontsize=8, color=MUTED)
    ax.legend(frameon=False, fontsize=9, loc="center right")
    ax.set_title("Feature-space dimensionality", fontsize=11)
    fig.tight_layout()
    return _save(fig, out_path)


# ── decoding ─────────────────────────────────────────────────────────────────

def plot_decoding_scores(res, out_path: Path) -> Path | None:
    """Per-model balanced accuracy over folds, against chance and the null.

    Each fold is drawn, not just the mean: with ~120 cultures the fold-to-fold
    spread is the honest measure of how much this accuracy can be trusted, and
    a bar chart of means hides it.
    """
    if res.scores.empty:
        return None
    order = (res.scores.groupby("Model")["BalancedAccuracy"].mean()
             .sort_values(ascending=False).index.tolist())
    fig, ax = plt.subplots(figsize=(max(4.5, 1.1 * len(order) + 1.5), 4.2))
    rng = np.random.default_rng(0)

    for i, name in enumerate(order):
        vals = res.scores.loc[res.scores["Model"] == name, "BalancedAccuracy"]
        ax.scatter(i + rng.normal(0, 0.06, len(vals)), vals, s=26, color="#4c72b0",
                   alpha=0.65, linewidths=0, zorder=3)
        ax.hlines(vals.mean(), i - 0.28, i + 0.28, color=INK, linewidth=2.5, zorder=4)
        if not res.null.empty:
            row = res.null[res.null["Model"] == name]
            if not row.empty and np.isfinite(row["Null95"].iloc[0]):
                ax.hlines(row["Null95"].iloc[0], i - 0.28, i + 0.28, color="#c44e52",
                          linewidth=1.5, linestyle="--", zorder=4)
                mark = _stars(row["PValue"].iloc[0])
                if mark:
                    ax.text(i, vals.max() + 0.02, mark, ha="center", fontsize=10,
                            color=INK, fontweight="bold")

    ax.axhline(res.chance, color=MUTED, linewidth=1.2, linestyle=":")
    ax.text(len(order) - 0.4, res.chance + 0.008, "chance", ha="right", fontsize=8,
            color=MUTED)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Balanced accuracy (held-out)")
    ax.set_ylim(0, 1)
    ax.set_title(
        f"Decoding {_target_label(res.target)} — {res.n_samples} recordings from "
        f"{res.n_groups} cultures", fontsize=11)
    if not res.null.empty:
        ax.plot([], [], color="#c44e52", linestyle="--", linewidth=1.5,
                label="95th centile of label-permutation null")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


def plot_confusion(res, out_path: Path, *, model: str | None = None) -> Path | None:
    """Row-normalised confusion matrix — recall per true class."""
    if not res.confusion:
        return None
    names = [model] if model else list(res.confusion)
    fig, axes = plt.subplots(1, len(names), figsize=(3.4 * len(names), 3.4),
                             squeeze=False)
    for ax, name in zip(axes[0], names):
        mat = res.confusion[name]
        # Normalised by row: with unequal class sizes the raw counts say more
        # about how many recordings each genotype has than about the decoder.
        norm = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0)
        mesh = ax.imshow(norm.to_numpy(), cmap=SEQUENTIAL, vmin=0, vmax=1)
        for i in range(len(mat)):
            for j in range(len(mat.columns)):
                value = norm.iat[i, j]
                ax.text(j, i, f"{value:.2f}\n({mat.iat[i, j]})", ha="center",
                        va="center", fontsize=7.5,
                        color="white" if value > 0.55 else INK)
        ax.set_xticks(range(len(mat.columns)))
        ax.set_xticklabels(mat.columns, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(mat.index)))
        ax.set_yticklabels(mat.index, fontsize=8)
        ax.set_xlabel("Predicted", fontsize=9)
        ax.set_ylabel("True", fontsize=9)
        ax.set_title(name, fontsize=10)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.colorbar(mesh, ax=axes, fraction=0.02, pad=0.02).outline.set_visible(False)
    return _save(fig, out_path)


def plot_decoding_importance(res, out_path: Path, *, top: int = 15) -> Path | None:
    """The most informative features per model, held-out permutation importance."""
    if res.importance.empty:
        return None
    models = list(res.importance["Model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(3.7 * len(models), 4.6),
                             squeeze=False, sharex=True)
    for ax, name in zip(axes[0], models):
        sub = res.importance[res.importance["Model"] == name].head(top).iloc[::-1]
        y = np.arange(len(sub))
        ax.barh(y, sub["Importance"], color="#4c72b0", height=0.7)
        ax.errorbar(sub["Importance"], y, xerr=sub["SD"].fillna(0), fmt="none",
                    ecolor=MUTED, elinewidth=1, capsize=0)
        ax.set_yticks(y)
        ax.set_yticklabels(sub["FeatureLabel"], fontsize=7.5)
        ax.axvline(0, color=MUTED, linewidth=1)
        ax.set_title(name, fontsize=10)
        ax.set_xlabel("Drop in balanced accuracy", fontsize=8.5)
        _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


def plot_lda_projection(proj: dict, out_path: Path, *,
                        scheme: ColorScheme = DEFAULT_SCHEME) -> Path | None:
    """Recordings on their discriminant axes — the ``doLDA`` figure.

    A *k*-class problem has only *k*-1 discriminant axes, so the two-group
    comparison that most of these studies actually are gets a single axis and
    no scatter to draw. That case is drawn as a strip of the recordings along
    that one axis, one row per group, rather than skipped — refusing to draw it
    would mean the commonest design got no discriminant figure at all.

    Labelled as in-sample, because it is: the axes were chosen to separate
    these very points, so the separation shown is an upper bound and the
    cross-validated number on the decoding figure is the real one.
    """
    if not proj or "coords" not in proj:
        return None
    coords = proj["coords"]
    target = proj["target"]
    if "LD1" not in coords.columns or coords.empty:
        return None
    levels = list(pd.unique(coords[target]))
    colors = _group_colors([str(g) for g in levels], scheme)
    explained = proj.get("explained", [])

    if "LD2" in coords.columns:
        fig, ax = plt.subplots(figsize=(5.4, 4.8))
        for level in levels:
            sub = coords[coords[target] == level]
            ax.scatter(sub["LD1"], sub["LD2"], s=30, alpha=0.75, linewidths=0.5,
                       edgecolors="white", color=colors[str(level)], label=str(level))
        # Share of the *between-class* separation carried by each axis; the two
        # add to 100% by construction (see lda_projection).
        ax.set_xlabel(f"LD1 ({explained[0] * 100:.0f}% of class separation)"
                      if len(explained) > 0 else "LD1")
        ax.set_ylabel(f"LD2 ({explained[1] * 100:.0f}%)" if len(explained) > 1 else "LD2")
    else:
        # One axis: the groups go on y, so the reader compares distributions
        # along the discriminant rather than reading a scatter with a
        # meaningless second dimension.
        fig, ax = plt.subplots(figsize=(6.0, max(2.4, 0.9 * len(levels) + 1.4)))
        rng = np.random.default_rng(0)
        for i, level in enumerate(levels):
            sub = coords[coords[target] == level]
            ax.scatter(sub["LD1"], i + rng.normal(0, 0.08, len(sub)), s=30,
                       alpha=0.7, linewidths=0.5, edgecolors="white",
                       color=colors[str(level)], label=str(level))
            ax.plot([sub["LD1"].mean()], [i], marker="|", markersize=18,
                    color=INK, markeredgewidth=2.5)
        ax.set_yticks(range(len(levels)))
        ax.set_yticklabels([str(x) for x in levels], fontsize=9)
        ax.set_ylim(-0.6, len(levels) - 0.4)
        ax.set_xlabel("LD1 — the only discriminant axis "
                      f"({len(levels)} groups give {len(levels) - 1})")

    ax.set_title(f"Linear discriminant projection — {_target_label(target)}",
                 fontsize=11)
    if "LD2" in coords.columns:
        ax.legend(frameon=False, fontsize=9)
    _bare(ax)
    # The caveat goes at the foot of the *figure*, with room reserved for it.
    # Hung off the axes it lands on the x-axis label as soon as the axes are
    # short, which the one-axis variant always is.
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.text(0.01, 0.015, "In-sample projection: fitted on all recordings, so "
             "the separation shown is optimistic.", fontsize=7.5, color=MUTED)
    return _save(fig, out_path)


def plot_decoding_by_age(by_age: pd.DataFrame, out_path: Path, *,
                         scheme: ColorScheme = DEFAULT_SCHEME) -> Path | None:
    """Decoding accuracy against age — when do the groups become separable?

    Takes the tidy per-age summary (one row per age × model, with
    ``BalancedAccuracy``/``SD``/``NFolds``/``Chance``) rather than the
    :class:`~meanap.stats.decoding.DecodingResults` objects it came from, so
    the figure can be redrawn from the CSV alone — which is what lets the
    viewer and the exporter rebuild it without re-running the decoders.
    """
    if by_age is None or by_age.empty:
        return None
    ages = sorted(by_age["DIV"].unique())
    models = sorted(by_age["Model"].unique())
    if not models or not ages:
        return None

    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    colors = _group_colors(models, scheme)
    for name in models:
        sub = by_age[by_age["Model"] == name].set_index("DIV").reindex(ages)
        # SD across folds, shown as the standard error of their mean: the
        # spread of the estimate, not of the folds.
        n_folds = sub["NFolds"] if "NFolds" in sub.columns else pd.Series(1, index=ages)
        err = (sub["SD"] / np.sqrt(n_folds.clip(lower=1))).fillna(0)
        ax.errorbar(ages, sub["BalancedAccuracy"], yerr=err, marker="o",
                    markersize=5, linewidth=2, capsize=0, color=colors[name],
                    label=name)
    chance = float(by_age["Chance"].iloc[0]) if "Chance" in by_age.columns else np.nan
    if np.isfinite(chance):
        ax.axhline(chance, color=MUTED, linestyle=":", linewidth=1.2)
        ax.text(ages[-1], chance + 0.01, "chance", ha="right", fontsize=8, color=MUTED)
    ax.set_xlabel("Age (DIV)")
    ax.set_ylabel("Balanced accuracy (held-out)")
    ax.set_ylim(0, 1)
    ax.set_title("Group separability across age", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


# ── regression ───────────────────────────────────────────────────────────────

def plot_regression_scores(res, out_path: Path) -> Path | None:
    """Per-model out-of-fold R², every fold drawn."""
    if res.scores.empty:
        return None
    order = (res.scores.groupby("Model")["R2"].mean()
             .sort_values(ascending=False).index.tolist())
    fig, ax = plt.subplots(figsize=(max(4.5, 1.1 * len(order) + 1.5), 4.0))
    rng = np.random.default_rng(0)
    for i, name in enumerate(order):
        vals = res.scores.loc[res.scores["Model"] == name, "R2"]
        ax.scatter(i + rng.normal(0, 0.06, len(vals)), vals, s=26, color="#4c72b0",
                   alpha=0.65, linewidths=0, zorder=3)
        ax.hlines(vals.mean(), i - 0.28, i + 0.28, color=INK, linewidth=2.5, zorder=4)
    ax.axhline(0, color=MUTED, linewidth=1.2, linestyle=":")
    ax.text(len(order) - 0.4, 0.012, "no better than the mean", ha="right",
            fontsize=8, color=MUTED)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("$R^2$ (held-out)")
    ax.set_title(
        f"Predicting {_target_label(res.target)} from network and activity features",
        fontsize=11)
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


def plot_variance_decomposition(res, out_path: Path, *, top: int = 20) -> Path | None:
    """Shapley share of R² per feature, with its marginal and unique bounds.

    The bar is the Shapley value — the share of explained variance that is
    genuinely attributable to the feature, and the column that sums to the
    model's R². The two markers bracket it: the open circle is what the feature
    explains *alone* (its ceiling) and the tick is what it explains that nothing
    else does (its floor). A tall bar with its ceiling far to the right and its
    floor at zero is a feature doing real work through a measurement it shares
    with others.
    """
    dec = res.decomposition
    if dec is None or dec.empty:
        return None
    sub = dec.head(top).iloc[::-1]
    y = np.arange(len(sub))
    fig, ax = plt.subplots(figsize=(7.2, max(3.4, 0.32 * len(sub) + 1.4)))

    ax.barh(y, sub["Shapley"], color="#4c72b0", height=0.62, zorder=3,
            label="Shapley share of $R^2$")
    ax.scatter(sub["Marginal"], y, s=34, facecolors="none", edgecolors=MUTED,
               linewidths=1.3, zorder=4, label="alone ($R^2$ of this feature only)")
    ax.scatter(sub["Unique"], y, marker="|", s=90, color="#c44e52", linewidths=1.8,
               zorder=5, label="unique (drop in $R^2$ if removed)")

    ax.set_yticks(y)
    ax.set_yticklabels(sub["FeatureLabel"], fontsize=8)
    ax.set_xlabel(f"Share of variance in {_target_label(res.target)}")
    ax.set_title(
        f"What explains {_target_label(res.target)}? Full-model $R^2$ = "
        f"{res.r2_full:.2f}, partitioned across {len(dec)} features", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


def plot_observed_vs_predicted(res, out_path: Path, *, model: str | None = None,
                               scheme: ColorScheme = DEFAULT_SCHEME) -> Path | None:
    """Out-of-fold predictions against the truth, for the best model."""
    if res.predictions is None or res.predictions.empty:
        return None
    if model is None:
        summary = res.summary()
        if summary.empty:
            return None
        model = summary["Model"].iloc[0]
    sub = res.predictions[res.predictions["Model"] == model].dropna(
        subset=["Predicted"])
    if sub.empty:
        return None

    fig, ax = plt.subplots(figsize=(4.8, 4.6))
    rng = np.random.default_rng(0)
    # Jitter the observed axis: ages are a handful of discrete values, so
    # without it every recording at one DIV lands on a single vertical line.
    jitter = rng.normal(0, 0.35, len(sub))
    ax.scatter(sub["Observed"] + jitter, sub["Predicted"], s=22, alpha=0.5,
               linewidths=0, color="#4c72b0")
    lo = float(min(sub["Observed"].min(), sub["Predicted"].min()))
    hi = float(max(sub["Observed"].max(), sub["Predicted"].max()))
    ax.plot([lo, hi], [lo, hi], color=INK, linewidth=1.2, linestyle="--")
    r2 = res.scores.loc[res.scores["Model"] == model, "R2"].mean()
    ax.set_xlabel(f"Observed {_target_label(res.target)}")
    ax.set_ylabel(f"Predicted {_target_label(res.target)} (held-out)")
    ax.set_title(f"{model}: $R^2$ = {r2:.2f}", fontsize=11)
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


# ── Shapley attribution of decoding, per age ─────────────────────────────────

#: Line colours for per-feature trajectories. Okabe-Ito, which stays
#: distinguishable under every common colour-vision deficiency, assigned in a
#: fixed order and never cycled — an extra feature folds into the summed
#: "other" line rather than reusing a hue that already means something.
#:
#: Okabe-Ito's yellow is the last entry rather than the seventh: it was
#: designed as a fill, and a 2px yellow line on white is barely visible to
#: anyone. Seven lines is the cap, so it is never reached in practice; it stays
#: in the tuple only so the list is the palette rather than a subset of it.
_OKABE_ITO = GROUP_SCHEMES["okabe-ito"]
_FEATURE_HUES = tuple(c for i, c in enumerate(_OKABE_ITO) if i != 6) + (_OKABE_ITO[6],)

#: How many features get their own line before the rest are summed.
_MAX_FEATURE_LINES = 7


def plot_shapley_by_age(res, out_path: Path) -> Path | None:
    """Each feature's share of genotype decodability, at each age.

    A heatmap rather than five bar charts: the question is how a feature's
    contribution *moves* across the row, and bars in separate panels make that
    a comparison of lengths in different places. Colour is diverging about
    zero because these shares can be negative — cross-validated accuracy is not
    monotone in the feature set, so a metric that is noise at one age genuinely
    costs the decoder there.

    Each column header carries that age's total, which its column sums to.
    """
    table = getattr(res, "table", None)
    if table is None or table.empty:
        return None
    wide = res.across_ages()
    if wide.empty:
        return None
    labels = dict(zip(table["Feature"], table["FeatureLabel"]))
    # Strongest contributors at the top; ranked by the mean over ages so a
    # feature that matters throughout outranks one that spikes once.
    wide = wide.reindex(wide.mean(axis=1).sort_values(ascending=False).index)

    limit = float(np.nanmax(np.abs(wide.to_numpy()))) or 1.0
    n_rows, n_cols = wide.shape
    fig, ax = plt.subplots(figsize=(max(4.5, 1.25 * n_cols + 3.2),
                                    max(3.0, 0.34 * n_rows + 1.8)))
    mesh = ax.imshow(wide.to_numpy(), cmap=DIVERGING, vmin=-limit, vmax=limit,
                     aspect="auto")

    for i in range(n_rows):
        for j in range(n_cols):
            value = wide.iat[i, j]
            if not np.isfinite(value):
                continue
            shade = abs(value) / limit
            ax.text(j, i, f"{value:+.02f}", ha="center", va="center", fontsize=7.5,
                    color="white" if shade > 0.6 else INK)

    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    heads = []
    for age in wide.columns:
        if totals is not None and age in totals.index:
            heads.append(f"DIV {age:g}\n{totals.loc[age, 'Total']:.2f} total")
        else:
            heads.append(f"DIV {age:g}")
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(heads, fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([labels.get(f, f) for f in wide.index], fontsize=8)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title("Which features carry the genotype signal, and when", fontsize=11)
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Shapley share of balanced accuracy above chance", fontsize=8)
    cbar.outline.set_visible(False)
    ax.text(0.0, -0.04 - 0.5 / max(n_rows, 1),
            "Each column sums to that age's decodability. Negative means the "
            "feature cost the decoder accuracy there.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    return _save(fig, out_path)


def plot_shapley_across_ages(res, out_path: Path, *, top: int = _MAX_FEATURE_LINES
                             ) -> Path | None:
    """How each feature's contribution to genotype decoding changes with age.

    Two panels on one shared age axis. The upper one is how much there was to
    decode at all — the total the lower panel partitions — because a feature's
    share falling can mean it stopped mattering *or* that nothing was
    decodable at that age, and those read identically in the lower panel alone.
    """
    table = getattr(res, "table", None)
    if table is None or table.empty:
        return None
    wide = res.across_ages()
    if wide.empty or wide.shape[1] < 2:
        return None
    labels = dict(zip(table["Feature"], table["FeatureLabel"]))
    ages = list(wide.columns)

    ranked = wide.abs().max(axis=1).sort_values(ascending=False).index.tolist()
    leading, rest = ranked[:top], ranked[top:]

    fig, (top_ax, ax) = plt.subplots(
        2, 1, figsize=(7.0, 6.4), sharex=True,
        gridspec_kw={"height_ratios": [1, 2.6], "hspace": 0.18})

    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    if totals is not None:
        present = [a for a in ages if a in totals.index]
        top_ax.plot(present, totals.loc[present, "Total"], marker="o",
                    markersize=5, linewidth=2, color=INK)
        top_ax.axhline(0, color=MUTED, linewidth=1, linestyle=":")
        top_ax.set_ylabel("Decodability\n(accuracy − chance)", fontsize=9)
        top_ax.set_title("Genotype decoding, and what carries it, across age",
                         fontsize=11)
    _bare(top_ax)

    for i, feature in enumerate(leading):
        ax.plot(ages, wide.loc[feature], marker="o", markersize=4.5, linewidth=2,
                color=_FEATURE_HUES[i], label=labels.get(feature, feature))
    if rest:
        # Summed, not dropped: the values are additive, so the remainder is a
        # meaningful line and keeping it means the panel still adds up to the
        # total drawn above it.
        ax.plot(ages, wide.loc[rest].sum(axis=0), marker="o", markersize=4,
                linewidth=1.6, linestyle="--", color=MUTED,
                label=f"other {len(rest)} features (summed)")

    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xlabel("Age (DIV)")
    ax.set_ylabel("Shapley share of decodability", fontsize=9)
    ax.set_xticks(ages)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper left",
              bbox_to_anchor=(0, -0.12))
    _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


# ── Feature families ─────────────────────────────────────────────────────────

#: One fixed hue per family, used in both family figures so the colour follows
#: the family and not its position in whichever panel it appears in.
_FAMILY_HUES = {
    "activity": _OKABE_ITO[0],    # blue
    "coupling": _OKABE_ITO[1],    # orange
    "topology": _OKABE_ITO[2],    # bluish green
    "other": (0.55, 0.55, 0.55),
}


def _family_colour(key: str):
    return _FAMILY_HUES.get(key, MUTED)


def plot_family_contributions(res, out_path: Path) -> Path | None:
    """What each family of features contributes to decoding, at each age.

    Grouped bars rather than stacked: these shares can be negative, and a
    stacked bar with a negative segment is unreadable. The black markers are
    each age's total, which its bars sum to.
    """
    table = getattr(res, "table", None)
    if table is None or table.empty:
        return None
    families = [f for f in res.families if f in set(table["Family"])]
    ages = sorted(table["DIV"].unique())
    if not families or not ages:
        return None

    wide = table.pivot_table(index="Family", columns="DIV", values="Shapley")
    labels = dict(zip(table["Family"], table["FamilyLabel"]))
    counts = table.groupby("Family")["NFeatures"].first()

    fig, ax = plt.subplots(figsize=(max(5.5, 1.5 * len(ages) + 2.5), 4.2))
    positions = np.arange(len(ages), dtype=float)
    width = 0.8 / len(families)
    for i, family in enumerate(families):
        offset = (i - (len(families) - 1) / 2) * width
        ax.bar(positions + offset, [wide.loc[family, a] for a in ages],
               width=width * 0.92, color=_family_colour(family),
               label=f"{labels.get(family, family)}  ({counts.get(family, 0)} metrics)")

    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    if totals is not None:
        present = [a for a in ages if a in totals.index]
        ax.plot([positions[ages.index(a)] for a in present],
                [totals.loc[a, "Total"] for a in present], marker="_",
                markersize=26, markeredgewidth=2.5, linestyle="none", color=INK,
                label="total decodability")

    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(positions)
    ax.set_xticklabels([f"DIV {a:g}" for a in ages])
    ax.set_ylabel("Shapley share of decodability")
    ax.set_title("What kind of feature carries the genotype difference", fontsize=11)
    ax.legend(frameon=False, fontsize=8.5, ncol=2, loc="upper right")
    _bare(ax)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.text(0.01, 0.015,
             "Bars at one age sum to that age's total. A family is one player, "
             "so metrics that duplicate each other inside it cost it nothing.",
             fontsize=7.5, color=MUTED)
    return _save(fig, out_path)


def plot_family_alone_vs_unique(res, out_path: Path) -> Path | None:
    """Whether each family carries signal of its own, or only a shared one.

    Per family and age, two numbers: what it achieves *alone*, and what is lost
    when it is removed from the full set (*unique*).

    This is the figure that answers the confound. A family whose ``alone`` is
    large while its ``unique`` sits at zero adds nothing the others do not
    already carry — for network topology, that would mean an apparent
    difference in organisation is what you would expect anyway from a culture
    that fires more and is more strongly correlated. A ``unique`` below zero
    means the family's metrics actively cost the decoder accuracy once the
    others are present.

    The two do not bracket the Shapley value, and the gap between them has a
    sign worth reading. ``alone`` above ``unique`` is the usual case: the
    family shares its signal with the others. ``unique`` above ``alone`` is
    complementarity — the family is worth *more* in company than by itself,
    because the classifier can only use it once the others are there.
    """
    table = getattr(res, "table", None)
    if table is None or table.empty:
        return None
    families = [f for f in res.families if f in set(table["Family"])]
    ages = sorted(table["DIV"].unique())
    if not families or len(ages) < 2:
        return None
    labels = dict(zip(table["Family"], table["FamilyLabel"]))

    fig, axes = plt.subplots(1, len(families), figsize=(3.5 * len(families), 4.0),
                             sharey=True, squeeze=False)
    for ax, family in zip(axes[0], families):
        sub = table[table["Family"] == family].set_index("DIV").reindex(ages)
        colour = _family_colour(family)
        ax.fill_between(ages, sub["Unique"], sub["Alone"], color=colour,
                        alpha=0.16, linewidth=0)
        ax.plot(ages, sub["Alone"], marker="o", markersize=5, linewidth=2,
                linestyle="--", color=colour)
        ax.plot(ages, sub["Unique"], marker="o", markersize=5, linewidth=2.4,
                color=colour)
        ax.axhline(0, color=INK, linewidth=1)
        ax.set_title(labels.get(family, family), fontsize=10)
        ax.set_xlabel("Age (DIV)", fontsize=9)
        ax.set_xticks(ages)
        _bare(ax)
    axes[0][0].set_ylabel("Balanced accuracy above chance")

    fig.suptitle("Does each family carry signal of its own?", fontsize=11)
    # The legend goes under the panels rather than inside the first one: the
    # upper-left corner is where the "alone" curve peaks in every family, so an
    # in-axes legend sits on the data it is describing.
    #
    # Its swatches are drawn in ink rather than lifted from the first panel:
    # they distinguish two *line styles*, and a blue swatch beside "alone"
    # reads as though the entry meant the Activity family. The handles are long
    # so the dash pattern is actually visible at legend size.
    from matplotlib.lines import Line2D

    proxies = [
        Line2D([], [], color=INK, linewidth=2, linestyle="--", marker="o",
               markersize=5, label="alone"),
        Line2D([], [], color=INK, linewidth=2.4, marker="o", markersize=5,
               label="unique"),
    ]
    fig.legend(handles=proxies, frameon=False, fontsize=9, ncol=2,
               handlelength=3.4, loc="lower center", bbox_to_anchor=(0.5, 0.055))
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    fig.text(0.01, 0.015,
             "Dashed: what the family achieves on its own. Solid: what is lost "
             "when it is removed from the full set. A solid line at zero means "
             "the family carries nothing the others do not. Solid above dashed "
             "is complementarity: worth more in company than alone.",
             fontsize=7.5, color=MUTED)
    return _save(fig, out_path)


# ── Density sweep ────────────────────────────────────────────────────────────

#: Axis labels for the swept metrics. Deliberately not the display names the
#: rest of the step uses: at a fixed binary density these are the *raw*
#: quantities, not the null-model-normalised ones the pipeline saves under the
#: same short names, and the axis should not claim otherwise.
_SWEEP_LABELS = {
    "CC": "Clustering coefficient",
    "PL": "Characteristic path length",
    "Eglob": "Global efficiency",
    "ElocMean": "Mean local efficiency",
    "BCmean": "Mean betweenness centrality",
    "Q": "Modularity (Q)",
    "nMod": "Number of modules",
    "lccFraction": "Largest component (fraction of nodes)",
}


def _sweep_panels(labelled, metrics, split_col, colours, n_cols, ylabel_of):
    """Shared body of the two sweep figures: one panel per metric, one line per level."""
    metrics = [m for m in metrics if m in labelled.columns]
    n_rows = int(np.ceil(len(metrics) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.2 * n_cols, 2.6 * n_rows),
                             squeeze=False, sharex=True)
    for idx, metric in enumerate(metrics):
        ax = axes[idx // n_cols][idx % n_cols]
        for level, colour in colours.items():
            sub = labelled[labelled[split_col] == level]
            if sub.empty:
                continue
            stat = sub.groupby("Density")[metric].agg(["mean", "sem", "count"])
            stat = stat[stat["count"] >= 2]
            if stat.empty:
                continue
            ax.plot(stat.index, stat["mean"], linewidth=2, color=colour,
                    label=str(level))
            ax.fill_between(stat.index, stat["mean"] - stat["sem"],
                            stat["mean"] + stat["sem"], color=colour, alpha=0.18,
                            linewidth=0)
        ax.set_title(ylabel_of(metric), fontsize=9)
        ax.set_xlabel("Imposed density", fontsize=8)
        ax.tick_params(labelsize=8)
        _bare(ax)
    for idx in range(len(metrics), n_rows * n_cols):
        axes[idx // n_cols][idx % n_cols].axis("off")
    return fig, axes, metrics


def plot_density_sweep(
    labelled: pd.DataFrame, out_path: Path, *, split: str, metrics,
    colours: dict, title: str, n_cols: int = 4,
) -> Path | None:
    """Each topology metric against imposed density, one line per group or age.

    The figure the sweep exists for: if two groups differ at their own
    densities but their curves lie on top of each other here, the difference
    was density, not organisation. Separated curves that stay separated across
    the range are a topology difference that survives the control.

    Read it against the ``lccFraction`` panel — where that is well below 1 the
    network is fragmented, and path length is being averaged over connected
    pairs only (see :mod:`meanap.stats.density_sweep`).
    """
    if labelled is None or labelled.empty:
        return None
    fig, axes, drawn = _sweep_panels(
        labelled, metrics, split, colours, n_cols, lambda m: _SWEEP_LABELS.get(m, m))
    if not drawn:
        plt.close(fig)
        return None

    handles, labels_ = axes[0][0].get_legend_handles_labels()
    if len(labels_) >= 2:
        fig.legend(handles, labels_, loc="lower center", ncol=min(5, len(labels_)),
                   frameon=False, fontsize=9, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, out_path)


def plot_density_context(
    observed: pd.DataFrame, labelled: pd.DataFrame, out_path: Path, *,
    densities, group_col: str, age_col: str, scheme: ColorScheme = DEFAULT_SCHEME,
) -> Path | None:
    """Where the sweep sits relative to the densities the recordings actually have.

    Two panels, and both are needed to read the other figures honestly. The
    left shows the observed density of every recording by age and group: if
    those differ, the unswept metrics were never comparable. The right shows
    what fraction of the network is connected at each imposed density — the
    sweep's own validity, since a metric measured on a third of the nodes is
    not measuring the network.
    """
    if observed is None or observed.empty:
        return None
    fig, (ax_obs, ax_lcc) = plt.subplots(1, 2, figsize=(10.5, 4.0))

    groups = list(pd.unique(observed[group_col].dropna())) if group_col in observed else []
    colours = _group_colors([str(g) for g in groups], scheme)
    ages = sorted(pd.unique(observed[age_col].dropna())) if age_col in observed else []
    rng = np.random.default_rng(0)
    for offset, group in enumerate(groups):
        sub = observed[observed[group_col] == group]
        jitter = (offset - (len(groups) - 1) / 2) * 0.9
        ax_obs.scatter(sub[age_col] + jitter + rng.normal(0, 0.25, len(sub)),
                       sub["ObservedDensity"], s=16, alpha=0.55, linewidths=0,
                       color=colours[str(group)], label=str(group))
        stat = sub.groupby(age_col)["ObservedDensity"].median()
        ax_obs.plot(stat.index + jitter, stat.values, color=colours[str(group)],
                    linewidth=2, marker="o", markersize=5)
    # The band the sweep imposes, against the densities that actually occur.
    ax_obs.axhspan(min(densities), max(densities), color="0.6", alpha=0.18,
                   linewidth=0)
    ax_obs.text(ax_obs.get_xlim()[0], max(densities), " swept range",
                va="bottom", ha="left", fontsize=8, color=MUTED)
    ax_obs.set_xlabel("Age (DIV)")
    ax_obs.set_ylabel("Observed density (step 4)")
    ax_obs.set_ylim(0, 1.02)
    ax_obs.set_xticks(ages)
    ax_obs.set_title("Densities the recordings actually have", fontsize=10)
    if groups:
        ax_obs.legend(frameon=False, fontsize=8.5, loc="lower right")
    _bare(ax_obs)

    if labelled is not None and not labelled.empty and "lccFraction" in labelled:
        for group in groups:
            sub = labelled[labelled[group_col] == group]
            if sub.empty:
                continue
            stat = sub.groupby("Density")["lccFraction"].mean()
            ax_lcc.plot(stat.index, stat.values, linewidth=2,
                        color=colours[str(group)], label=str(group))
        ax_lcc.axhline(1.0, color=MUTED, linestyle=":", linewidth=1)
        ax_lcc.set_ylim(0, 1.05)
    ax_lcc.set_xlabel("Imposed density")
    ax_lcc.set_ylabel("Largest component (fraction of nodes)")
    ax_lcc.set_title("How much of the network survives thresholding", fontsize=10)
    _bare(ax_lcc)

    fig.suptitle("Reading the density sweep", fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.text(0.01, 0.015,
             "Left: if the groups' observed densities differ, metrics compared "
             "at those densities were confounded. Right: where the largest "
             "component falls below 1 the network is fragmented and path "
             "length is averaged over connected pairs only — prefer global "
             "efficiency there.", fontsize=7.5, color=MUTED)
    return _save(fig, out_path)


def plot_topology_controlled(raw, controlled, out_path: Path) -> Path | None:
    """Topology's contribution before and after controlling density and size.

    The closing figure of the confound argument. The family decomposition is
    run twice — once with topology as the raw step-4 metrics, once with it
    represented only by the cost-integrated sweep features, activity and
    correlation strength left raw in both — and the two are drawn together.

    ``Unique`` is the panel that answers the question. If controlling the
    topology metrics lifts it off zero, the earlier null result was an artefact
    of measuring topology at each network's own density and size. If it stays
    at zero, topology is redundant with activity and coupling rather than
    merely mismeasured — which is a much stronger statement.
    """
    if raw is None or controlled is None:
        return None
    raw_t = raw.table[raw.table["Family"] == "topology"] if not raw.table.empty else None
    new_t = (controlled.table[controlled.table["Family"] == "topology"]
             if not controlled.table.empty else None)
    if raw_t is None or new_t is None or raw_t.empty or new_t.empty:
        return None

    ages = sorted(set(raw_t["DIV"]) & set(new_t["DIV"]))
    if not ages:
        return None
    measures = ("Shapley", "Alone", "Unique")
    titles = {
        "Shapley": "Share of decodability",
        "Alone": "What topology achieves alone",
        "Unique": "What only topology contributes",
    }
    colour_raw, colour_new = _OKABE_ITO[5], _OKABE_ITO[2]

    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.8), sharex=True)
    for ax, measure in zip(axes, measures):
        for frame, colour, label, style in (
            (raw_t, colour_raw, "as measured (step 4)", "--"),
            (new_t, colour_new, "density + size controlled", "-"),
        ):
            series = frame.set_index("DIV").reindex(ages)[measure]
            ax.plot(ages, series, marker="o", markersize=5, linewidth=2.2,
                    linestyle=style, color=colour, label=label)
        ax.axhline(0, color=INK, linewidth=1)
        ax.set_title(titles[measure], fontsize=10)
        ax.set_xlabel("Age (DIV)", fontsize=9)
        ax.set_xticks(ages)
        _bare(ax)
    axes[0].set_ylabel("Balanced accuracy above chance")

    handles, labels_ = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc="lower center", ncol=2, frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Does network topology carry genotype information of its own?",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.text(0.01, 0.015,
             "Topology measured on networks thresholded to a common density and "
             "subsampled to a common node count, against the same metrics as "
             "step 4 measured them. Activity and correlation strength are left "
             "uncontrolled in both — they are what topology is being tested "
             "against.", fontsize=7.5, color=MUTED)
    return _save(fig, out_path)


#: Marks a comparison the selection check flagged. One accent, used nowhere
#: else, so a flagged row reads as a warning rather than as another category.
FLAGGED = "#c1443c"


def plot_size_control(
    observed: pd.DataFrame, out_path: Path, *, n_nodes: int | None,
    group_col: str, age_col: str, scheme: ColorScheme = DEFAULT_SCHEME,
) -> Path | None:
    """The size half of the confound: what was subsampled to, and what it cost.

    The counterpart to :func:`plot_density_context`, which covers the density
    half. Left: how many connected nodes every recording actually had, against
    the common size they were all reduced to - the recordings below that line
    are the ones the sweep had to drop, since a network cannot be subsampled up.
    Right: what fraction of each group survived, which is the number to read
    before believing anything the sweep says. Smallness is not randomly
    distributed across groups, so an uneven bar chart means the size confound
    was traded for a selection one rather than removed.

    Returns ``None`` when size was not controlled, since then there is no target
    to draw and no recording was dropped for being too small.
    """
    if observed is None or observed.empty or n_nodes is None:
        return None
    if "NNodes" not in observed.columns:
        return None

    fig, (ax_size, ax_keep) = plt.subplots(1, 2, figsize=(10.5, 4.0))
    groups = (list(pd.unique(observed[group_col].dropna()))
              if group_col in observed.columns else [])
    colours = _group_colors([str(g) for g in groups], scheme)
    has_age = age_col in observed.columns and observed[age_col].notna().any()
    rng = np.random.default_rng(0)

    # Left: node counts, on a log axis because they span an order of magnitude
    # and the target would otherwise sit squashed against the bottom.
    if has_age:
        ages = sorted(pd.unique(observed[age_col].dropna()))
        for offset, group in enumerate(groups):
            sub = observed[observed[group_col] == group]
            jitter = (offset - (len(groups) - 1) / 2) * 0.9
            ax_size.scatter(sub[age_col] + jitter + rng.normal(0, 0.25, len(sub)),
                            sub["NNodes"], s=16, alpha=0.55, linewidths=0,
                            color=colours[str(group)], label=str(group))
            stat = sub.groupby(age_col)["NNodes"].median()
            ax_size.plot(stat.index + jitter, stat.values, color=colours[str(group)],
                         linewidth=2, marker="o", markersize=5)
        ax_size.set_xlabel(f"Age ({age_col})")
        ax_size.set_xticks(ages)
    else:
        for offset, group in enumerate(groups):
            sub = observed[observed[group_col] == group]
            ax_size.scatter(np.full(len(sub), offset) + rng.normal(0, 0.08, len(sub)),
                            sub["NNodes"], s=16, alpha=0.55, linewidths=0,
                            color=colours[str(group)], label=str(group))
        ax_size.set_xticks(range(len(groups)))
        ax_size.set_xticklabels([str(g) for g in groups], fontsize=8)

    ax_size.set_yscale("log")
    ax_size.axhline(n_nodes, color=INK, linestyle="--", linewidth=1.2)
    ax_size.axhspan(ax_size.get_ylim()[0], n_nodes, color=FLAGGED, alpha=0.10,
                    linewidth=0)
    ax_size.text(ax_size.get_xlim()[0], n_nodes, f" subsampled to {n_nodes}",
                 va="bottom", ha="left", fontsize=8, color=INK)
    ax_size.set_ylabel("Connected nodes per recording")
    ax_size.set_title("Sizes the recordings actually have", fontsize=10)
    if groups and has_age:
        # Lower right is the emptiest corner here: it is inside the band of
        # sizes too small to keep, where by definition few points sit.
        ax_size.legend(frameon=False, fontsize=8.5, loc="lower right")
    _bare(ax_size)

    # Right: retention. Recomputed here rather than read, so the figure needs
    # only the table it is already handed.
    if groups:
        kept = (observed.assign(_kept=observed["NNodes"] >= n_nodes)
                .groupby(group_col)["_kept"].agg(["mean", "sum", "size"]))
        kept = kept.reindex([g for g in groups if g in kept.index])
        positions = np.arange(len(kept))
        ax_keep.bar(positions, kept["mean"], width=0.62,
                    color=[colours[str(g)] for g in kept.index])
        for pos, (_, row) in zip(positions, kept.iterrows()):
            ax_keep.text(pos, row["mean"] + 0.02,
                         f"{row['mean']:.0%}\n{int(row['sum'])}/{int(row['size'])}",
                         ha="center", va="bottom", fontsize=8, color=INK)
        ax_keep.set_xticks(positions)
        ax_keep.set_xticklabels([str(g) for g in kept.index], fontsize=8.5)
        ax_keep.set_ylim(0, 1.18)
        spread = float(kept["mean"].max() - kept["mean"].min())
        # The same 20-point rule the runner warns on, drawn rather than logged.
        if spread > 0.2:
            ax_keep.set_title(
                f"Kept per group - {spread:.0%} spread, uneven", fontsize=10,
                color=FLAGGED)
        else:
            ax_keep.set_title("Kept per group", fontsize=10)
    ax_keep.set_ylabel("Fraction of recordings retained")
    _bare(ax_keep)

    fig.suptitle("Controlling for network size", fontsize=11)
    # Footnotes are wrapped by hand: the figure is saved with a tight bounding
    # box, so one long line silently widens the whole canvas.
    fig.tight_layout(rect=(0, 0.15, 1, 1))
    fig.text(0.01, 0.015,
             "Left: every recording below the dashed line was dropped — it "
             "cannot be subsampled up to the common size.\n"
             "Right: if the groups were not dropped evenly, the comparison is "
             "now between the largest networks of one group\n"
             "and typical ones of another, and the size confound has been "
             "traded rather than removed.",
             fontsize=7.5, color=MUTED, va="bottom", linespacing=1.5)
    return _save(fig, out_path)


def plot_selection_check(check, out_path: Path) -> Path | None:
    """Do the group differences survive a stricter size cut?

    One panel per group pair, one row per metric: an open marker at the gap over
    every swept recording, a filled one at the gap over only those clearing a
    higher node count, joined by a line. Since nothing is re-swept between the
    two - the same per-recording numbers are simply aggregated over fewer
    recordings - the movement is *selection* alone, with resolution held fixed.

    A long line means the difference is partly a statement about which
    recordings were big enough to keep. Those are drawn in the warning colour;
    they should not be quoted from a single subsample target.
    """
    if check is None or not getattr(check, "ran", False):
        return None
    table = check.table
    pairs = list(table.groupby(["GroupA", "GroupB"]).groups)
    if not pairs:
        return None

    # One shared metric order across panels, worst mover at the top, so a row
    # can be read straight across.
    order = (table.groupby("Metric")["Delta"].apply(lambda s: s.abs().max())
             .sort_values(ascending=True).index.tolist())

    fig, axes = plt.subplots(1, len(pairs), figsize=(3.6 * len(pairs) + 1.2, 4.2),
                             squeeze=False, sharex=True, sharey=True)
    for idx, (a, b) in enumerate(pairs):
        ax = axes[0][idx]
        sub = table[(table["GroupA"] == a) & (table["GroupB"] == b)]
        sub = sub.set_index("Metric").reindex(order).dropna(subset=["GapAll"])
        for row_idx, (metric, row) in enumerate(sub.iterrows()):
            colour = FLAGGED if bool(row["Flagged"]) else MUTED
            ax.plot([row["GapAll"], row["GapRestricted"]], [row_idx, row_idx],
                    color=colour, linewidth=2, alpha=0.85, zorder=1)
            ax.scatter(row["GapAll"], row_idx, s=34, facecolors="white",
                       edgecolors=colour, linewidths=1.4, zorder=2)
            ax.scatter(row["GapRestricted"], row_idx, s=34, color=colour,
                       linewidths=0, zorder=3)
        ax.axvline(0, color=INK, linewidth=0.9, linestyle=":")
        ax.set_yticks(range(len(sub)))
        ax.set_yticklabels(
            [_SWEEP_LABELS.get(m, m) for m in sub.index], fontsize=8)
        ax.set_xlabel("Standardised group difference", fontsize=8.5)
        ax.set_title(f"{a} vs {b}", fontsize=9.5)
        ax.tick_params(labelsize=8)
        _bare(ax)

    threshold = getattr(check, "threshold", None)
    cohort = ""
    if getattr(check, "n_restricted", 0) and getattr(check, "n_all", 0):
        cohort = f" ({check.n_restricted} of {check.n_all} recordings)"
    fig.suptitle("Do the group differences survive a stricter size cut?",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.18, 1, 1))
    fig.text(0.01, 0.015,
             "Open marker: every swept recording. Filled: only those with at "
             f"least {threshold} nodes{cohort}.\n"
             "Nothing is re-swept between the two, so the movement is the "
             "cohort changing, not the measurement —\n"
             "a long line in the warning colour means the difference is partly "
             "about which recordings were big enough to keep.",
             fontsize=7.5, color=MUTED, va="bottom", linespacing=1.5)
    return _save(fig, out_path)


#: One colour per level of control, darkening as more is controlled for, so the
#: direction of the reading is legible before the legend is.
_CONTROL_COLOURS = {
    "none": "#b7b7b7",
    "density": "#6f9fd0",
    "density+size": "#1f4e79",
}

_CONTROL_LABELS = {
    "none": "no control (step 4)",
    "density": "matched density",
    "density+size": "matched density + size",
}


def plot_control_effects(
    table: pd.DataFrame, out_path: Path, *, alpha: float = 0.05,
) -> Path | None:
    """Each metric's age and genotype effect, before and after the controls.

    The question the 5A heatmaps leave open: an effect measured at each
    network's own density and size may be a statement about density and size.
    Every metric appears once per level of control, joined by a line, so an
    effect that shrinks to nothing under the control is visible as a collapse
    toward zero and one that survives is visible as a flat run.

    Where all three levels are present the step from matched density to matched
    density *and* size is the node-subsampling effect on its own; with only two
    the density and size controls cannot be separated, and the caption says so.

    Filled markers survive FDR correction at *alpha*, open ones do not — a
    marker that empties out between conditions is an effect the control removed.
    """
    if table is None or table.empty:
        return None
    # Pooled rows only. The per-age contrasts also read "<a> vs <b> ...", and
    # matching on that alone would put every age in its own panel.
    if "Scope" in table.columns:
        table = table[table["Scope"] == "pooled"]
    terms = [t for t in pd.unique(table["Term"])
             if str(t) == "age" or (" vs " in str(t) and " at DIV " not in str(t))]
    terms = [t for t in terms if not str(t).startswith("age within")]
    if not terms:
        return None
    # Age first, then the genotype contrasts in a stable order.
    terms = ([t for t in terms if str(t) == "age"]
             + sorted(t for t in terms if str(t) != "age"))

    present = [c for c in CONTROL_LEVELS if c in set(table["Control"])]
    if not present:
        return None
    shown = table[table["Term"].isin(terms)]
    order = (shown.groupby("Metric")["EffectSize"]
             .apply(lambda s: s.abs().max())
             .sort_values(ascending=True).index.tolist())

    fig, axes = plt.subplots(1, len(terms), figsize=(3.5 * len(terms) + 1.3, 4.4),
                             squeeze=False, sharey=True)
    for idx, term in enumerate(terms):
        ax = axes[0][idx]
        sub = shown[shown["Term"] == term]
        for row_idx, metric in enumerate(order):
            points = (sub[sub["Metric"] == metric]
                      .set_index("Control").reindex(present).dropna(subset=["EffectSize"]))
            if points.empty:
                continue
            if len(points) > 1:
                ax.plot(points["EffectSize"], [row_idx] * len(points),
                        color=MUTED, linewidth=1.2, alpha=0.7, zorder=1)
            for control, point in points.iterrows():
                colour = _CONTROL_COLOURS.get(control, INK)
                significant = (pd.notna(point.get("PValueFDR"))
                               and float(point["PValueFDR"]) < alpha)
                ax.scatter(point["EffectSize"], row_idx, s=42, zorder=3,
                           color=colour if significant else "white",
                           edgecolors=colour, linewidths=1.5)
        ax.axvline(0, color=INK, linewidth=0.9, linestyle=":")
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([_SWEEP_LABELS.get(m, m) for m in order], fontsize=8)
        ax.set_title("Age" if str(term) == "age" else str(term), fontsize=9.5)
        ax.set_xlabel("Effect size", fontsize=8.5)
        ax.tick_params(labelsize=8)
        _bare(ax)

    handles = [plt.Line2D([], [], marker="o", linestyle="none",
                          markerfacecolor=_CONTROL_COLOURS.get(c, INK),
                          markeredgecolor=_CONTROL_COLOURS.get(c, INK),
                          markersize=7, label=_CONTROL_LABELS.get(c, c))
               for c in present]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.145))
    fig.suptitle("Age and genotype effects, before and after the controls",
                 fontsize=11)
    # Room for three footnote lines under the legend, which sits under the axes.
    fig.tight_layout(rect=(0, 0.23, 1, 1))

    isolated = "density" in present and "density+size" in present
    note = ("Matched density to matched density + size is the node-subsampling "
            "step on its own." if isolated else
            "Only one controlled condition was run, so the density and size "
            "controls cannot be told apart here.")
    fig.text(0.01, 0.015,
             "Filled markers survive FDR correction; open ones do not. An "
             "effect that collapses toward zero under control was a statement\n"
             "about how dense or how large the networks were, not about their "
             f"organisation.\n{note} Every condition is measured on the "
             "recordings all of them have, so a step is the control changing "
             "and not the cohort.",
             fontsize=7.5, color=MUTED, va="bottom", linespacing=1.5)
    return _save(fig, out_path)


def plot_genotype_effect_by_age(
    table: pd.DataFrame, out_path: Path, *, alpha: float = 0.05,
) -> Path | None:
    """Each genotype contrast at each age, before and after the controls.

    The pooled figure asks whether an effect survives control over the whole
    timecourse; this asks *when*. One row per metric, one column per genotype
    pair, age along the x axis, and one line per level of control. A raw line
    that climbs with age and a controlled line that does not is a difference
    that was tracking how dense and how large the networks became, not a
    genotype difference that grows.

    The statistic is Hedges' g from a Welch t-test at each age, which is not
    the mixed model's standardised beta — the two are never drawn together for
    that reason. Filled markers survive FDR correction at *alpha*.
    """
    if table is None or table.empty or "Scope" not in table.columns:
        return None
    per_age = table[table["Scope"] == "per-age"].dropna(subset=["Age"])
    if per_age.empty:
        return None

    contrasts = sorted(pd.unique(per_age["Contrast"].astype(str)))
    metrics = (per_age.groupby("Metric")["EffectSize"]
               .apply(lambda s: s.abs().max())
               .sort_values(ascending=False).index.tolist())
    present = [c for c in CONTROL_LEVELS if c in set(per_age["Control"])]
    if not contrasts or not metrics or not present:
        return None

    fig, axes = plt.subplots(
        len(metrics), len(contrasts), squeeze=False, sharex=True, sharey=True,
        figsize=(2.9 * len(contrasts) + 1.0, 1.75 * len(metrics) + 1.8))
    for r, metric in enumerate(metrics):
        for c, contrast in enumerate(contrasts):
            ax = axes[r][c]
            sub = per_age[(per_age["Metric"] == metric)
                          & (per_age["Contrast"].astype(str) == contrast)]
            for control in present:
                line = sub[sub["Control"] == control].sort_values("Age")
                if line.empty:
                    continue
                colour = _CONTROL_COLOURS.get(control, INK)
                ax.plot(line["Age"], line["EffectSize"], color=colour,
                        linewidth=1.8, zorder=2)
                significant = (line["PValueFDR"].notna()
                               & (line["PValueFDR"] < alpha))
                ax.scatter(line["Age"], line["EffectSize"], s=30, zorder=3,
                           color=[colour if ok else "white" for ok in significant],
                           edgecolors=colour, linewidths=1.4)
            ax.axhline(0, color=INK, linewidth=0.9, linestyle=":")
            if r == 0:
                ax.set_title(contrast, fontsize=9)
            if c == 0:
                ax.set_ylabel(_SWEEP_LABELS.get(metric, metric), fontsize=7.5)
            if r == len(metrics) - 1:
                ax.set_xlabel("Age (DIV)", fontsize=8.5)
            ax.tick_params(labelsize=7.5)
            _bare(ax)

    handles = [plt.Line2D([], [], color=_CONTROL_COLOURS.get(c, INK), marker="o",
                          markersize=6, linewidth=1.8,
                          label=_CONTROL_LABELS.get(c, c)) for c in present]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.045))
    fig.suptitle("Genotype differences at each age, before and after the controls",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.085, 1, 0.985))
    fig.text(0.01, 0.008,
             "Hedges' g at each age; filled markers survive FDR correction. "
             "Not the same statistic as the pooled figure, so read the shape "
             "across ages rather than against that one.\nEvery condition is "
             "measured on the recordings all of them have, so a step is the "
             "control changing and not the cohort.",
             fontsize=7.5, color=MUTED, va="bottom")
    return _save(fig, out_path)


def plot_metric_values(
    values: pd.DataFrame, out_path: Path, *,
    scheme: ColorScheme = DEFAULT_SCHEME,
) -> Path | None:
    """The metrics themselves per group and age, under each level of control.

    Effect sizes say how far apart two groups are in units of their own spread;
    they say nothing about what either group measured. This is the same
    trajectory figure the comparisons draw, repeated once per level of control,
    so a control that shifts every group together can be told from one that
    pulls them apart. Mean ± SEM.

    Rows share a y axis so a metric can be followed across conditions, but the
    conditions are not the same measurement — step 4 measures each network at
    its own density, the controlled columns are cost-integrated over the
    density grid — so a shift between columns is a change of definition as well
    as of control.
    """
    if values is None or values.empty:
        return None
    metrics = [m for m in SWEEP_METRICS if m in set(values["Metric"])]
    controls = [c for c in CONTROL_LEVELS if c in set(values["Control"])]
    if not metrics or not controls:
        return None
    groups = list(pd.unique(values["Group"].dropna()))
    colours = _group_colors([str(g) for g in groups], scheme)

    # Y axes are shared across the *controlled* columns only. Those measure the
    # same quantity the same way and differ just in how much is controlled, so a
    # common scale is what makes the subsampling step readable. The uncontrolled
    # column is a different measurement — step 4 on the weighted network at its
    # own density — and forcing it onto the same axis flattens it to a line
    # (raw nMod is ~2 against ~10-35 controlled).
    fig, axes = plt.subplots(
        len(metrics), len(controls), squeeze=False, sharex=True,
        figsize=(2.9 * len(controls) + 1.0, 1.75 * len(metrics) + 1.8))
    for r, metric in enumerate(metrics):
        for c, control in enumerate(controls):
            ax = axes[r][c]
            sub = values[(values["Metric"] == metric)
                         & (values["Control"] == control)]
            if sub.empty:
                ax.text(0.5, 0.5, "no step-4 equivalent", transform=ax.transAxes,
                        ha="center", va="center", fontsize=7.5, color=MUTED)
                # Only this panel's labels: the x axis is shared, so clearing
                # its ticks would strip them from every column.
                ax.tick_params(labelbottom=False)
                ax.set_yticks([])
            for group in groups:
                line = sub[sub["Group"] == group].sort_values("Age")
                if line.empty:
                    continue
                colour = colours[str(group)]
                ax.plot(line["Age"], line["Mean"], color=colour, linewidth=1.8,
                        marker="o", markersize=4, label=str(group))
                ax.fill_between(line["Age"], line["Mean"] - line["SEM"],
                                line["Mean"] + line["SEM"], color=colour,
                                alpha=0.18, linewidth=0)
            if r == 0:
                ax.set_title(_CONTROL_LABELS.get(control, control), fontsize=9)
            if c == 0:
                ax.set_ylabel(_SWEEP_LABELS.get(metric, metric), fontsize=7.5)
            if r == len(metrics) - 1:
                ax.set_xlabel("Age (DIV)", fontsize=8.5)
            ax.tick_params(labelsize=7.5)
            _bare(ax)

    # Put the controlled columns of each row on one scale, after autoscaling.
    controlled = [c for c, name in enumerate(controls) if name != "none"]
    if len(controlled) > 1:
        for r in range(len(metrics)):
            limits = [axes[r][c].get_ylim() for c in controlled
                      if axes[r][c].has_data()]
            if len(limits) < 2:
                continue
            low, high = min(l for l, _ in limits), max(h for _, h in limits)
            for c in controlled:
                axes[r][c].set_ylim(low, high)
            for c in controlled[1:]:
                axes[r][c].tick_params(labelleft=False)

    handles, labels_ = axes[0][0].get_legend_handles_labels()
    if not handles:
        for row in axes:
            for ax in row:
                handles, labels_ = ax.get_legend_handles_labels()
                if handles:
                    break
            if handles:
                break
    if handles:
        fig.legend(handles, labels_, loc="lower center", ncol=min(5, len(labels_)),
                   frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.045))
    fig.suptitle("The metrics themselves, under each level of control", fontsize=11)
    fig.tight_layout(rect=(0, 0.085, 1, 0.985))
    fig.text(0.01, 0.008,
             "Mean ± SEM. The controlled columns of a row share a y axis, so "
             "the subsampling step can be read directly; the uncontrolled "
             "column is\na different measurement of the same quantity and is "
             "scaled on its own. Every condition uses the recordings all of "
             "them have.",
             fontsize=7.5, color=MUTED, va="bottom")
    return _save(fig, out_path)


# ── measure of activity ──────────────────────────────────────────────────────
#
# Four figures answering one question in increasing order of consequence: do
# the measures rank recordings alike, do they give the same values, do they
# give the same conclusion, and which of them carries the most signal. See
# meanap.stats.measures for what each table means.

def _pair_label(a: str, b: str) -> str:
    return f"{a} vs {b}"


def plot_measure_agreement(result, out_path: Path) -> Path | None:
    """Metrics × measure pairs, coloured by how alike the two measures rank them.

    Spearman rho rather than the agreement coefficient beside it in the table:
    the ranking is the part that has to hold for a group comparison to survive
    a change of measure, and two measures on different scales — which an event
    network and a correlation network always are — would show as poor agreement
    on any statistic that also asks for the same *values*.

    Signed, and drawn on the diverging map for that reason: a metric that
    anti-correlates across measures is a much louder finding than one that
    merely fails to correlate, and a sequential map would hide the difference
    at the bottom of the scale.
    """
    table = getattr(result, "agreement", None)
    if table is None or table.empty:
        return None
    sub = table.copy()
    sub["Pair"] = [_pair_label(a, b) for a, b in zip(sub["MeasureA"], sub["MeasureB"])]
    wide = sub.pivot_table(index="MetricLabel", columns="Pair", values="Spearman")
    wide = wide.dropna(how="all").dropna(axis=1, how="all")
    if wide.empty:
        return None
    # Worst agreement at the top: those are the rows a reader has to act on.
    wide = wide.reindex(wide.abs().min(axis=1).sort_values().index)

    n_rows, n_cols = wide.shape
    fig, ax = plt.subplots(figsize=(max(4.0, 1.9 * n_cols + 2.4),
                                    max(3.0, 0.28 * n_rows + 1.4)))
    mesh = ax.imshow(wide.to_numpy(), cmap=DIVERGING, vmin=-1, vmax=1, aspect="auto")

    norm = matplotlib.colors.Normalize(vmin=-1, vmax=1)
    cmap = matplotlib.colormaps[DIVERGING]
    for i in range(n_rows):
        for j in range(n_cols):
            value = wide.iat[i, j]
            if not np.isfinite(value):
                continue
            r, g, b, _ = cmap(norm(value))
            ink = "white" if (0.299 * r + 0.587 * g + 0.114 * b) < 0.55 else INK
            ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                    fontsize=7, color=ink)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(wide.columns, rotation=20, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(wide.index, fontsize=7)
    ax.set_title("Do the measures rank recordings the same way?\n"
                 "Spearman rho between measures, over matched recordings",
                 fontsize=10)
    bar = fig.colorbar(mesh, ax=ax, fraction=0.035, pad=0.02)
    bar.set_label("Spearman rho", fontsize=8)
    bar.ax.tick_params(labelsize=7)
    return _save(fig, out_path)


def plot_measure_differences(result, out_path: Path, *, alpha: float = 0.05,
                             limit: int = 30) -> Path | None:
    """Paired standardised difference per metric, largest shift first.

    A dot per metric per measure pair, at ``g_av`` — the shift in the metric
    when the same recordings are measured the other way, in pooled standard
    deviations. Filled dots survived FDR correction; open dots did not.

    The zero line is the claim being tested: a metric sitting on it is one whose
    reported mean would not have changed had the other measure been used.
    """
    table = getattr(result, "differences", None)
    if table is None or table.empty:
        return None
    sub = table.dropna(subset=["HedgesG"]).copy()
    if sub.empty:
        return None
    sub["Pair"] = [_pair_label(a, b) for a, b in zip(sub["MeasureA"], sub["MeasureB"])]

    # Rank metrics by their largest shift under any pair, then keep the top
    # few: fifty rows of dots is a figure nobody reads, and the full table is
    # on disk beside it.
    order = (sub.groupby("MetricLabel")["HedgesG"].apply(lambda v: v.abs().max())
             .sort_values(ascending=False))
    keep = list(order.index[:limit])
    sub = sub[sub["MetricLabel"].isin(keep)]
    positions = {name: i for i, name in enumerate(reversed(keep))}

    pairs = list(pd.unique(sub["Pair"]))
    colours = dict(zip(pairs, plt.get_cmap("tab10").colors))
    offsets = np.linspace(-0.22, 0.22, len(pairs)) if len(pairs) > 1 else [0.0]

    fig, ax = plt.subplots(figsize=(6.4, max(3.0, 0.26 * len(keep) + 1.4)))
    ax.axvline(0.0, color=MUTED, lw=1.0, zorder=0)
    pcol = "PValueFDR" if "PValueFDR" in sub.columns else "PValue"
    for pair, offset in zip(pairs, offsets):
        block = sub[sub["Pair"] == pair]
        y = [positions[name] + offset for name in block["MetricLabel"]]
        sig = pd.to_numeric(block[pcol], errors="coerce") < alpha
        colour = colours[pair]
        ax.scatter(block["HedgesG"][sig], np.asarray(y)[sig.to_numpy()],
                   s=26, color=colour, label=pair, zorder=3)
        ax.scatter(block["HedgesG"][~sig], np.asarray(y)[~sig.to_numpy()],
                   s=26, facecolors="none", edgecolors=colour, zorder=3)

    ax.set_yticks(list(positions.values()))
    ax.set_yticklabels(list(positions.keys()), fontsize=7)
    ax.set_xlabel("paired difference between measures (Hedges' g$_{av}$)", fontsize=9)
    ax.set_title("How far do the values move when the measure changes?\n"
                 f"filled = significant after FDR correction (p < {alpha})",
                 fontsize=10)
    if len(pairs) > 1:
        ax.legend(fontsize=7, frameon=False, loc="best")
    _bare(ax)
    return _save(fig, out_path)


#: Colour per concordance verdict. Green for the two agreements, warm for the
#: two disagreements, so the figure reads before the legend does.
_VERDICT_COLORS = {
    "agree (both significant)": "#2f7d46",
    "agree (neither significant)": "#9dbfa6",
    "disagree (opposite signs)": "#a12a2a",
}
_VERDICT_DEFAULT = "#e08b2c"   # "disagree (only <measure>)", one per measure


def plot_measure_concordance(result, out_path: Path) -> Path | None:
    """Each metric's group/age effect under one measure against the other.

    The figure the whole comparison exists for. A point on the identity line is
    a conclusion that does not depend on how activity was measured; a point far
    off it, and especially one in an off-diagonal quadrant, is a conclusion that
    does. Colour carries the verdict — whether both measures called it
    significant, one did, or neither.

    Drawn per measure pair as its own panel so the axes can be read as "the
    effect I would have reported using this measure".
    """
    table = getattr(result, "concordance", None)
    if table is None or table.empty:
        return None
    sub = table.dropna(subset=["EffectA", "EffectB"]).copy()
    if sub.empty:
        return None

    pairs = sorted({(a, b) for a, b in zip(sub["MeasureA"], sub["MeasureB"])})
    n = len(pairs)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 4.2), squeeze=False)
    for ax, (a, b) in zip(axes[0], pairs):
        block = sub[(sub["MeasureA"] == a) & (sub["MeasureB"] == b)]
        limit = float(np.nanmax(np.abs(
            np.concatenate([block["EffectA"], block["EffectB"]])))) or 1.0
        limit *= 1.15
        ax.plot([-limit, limit], [-limit, limit], color=MUTED, lw=1.0, ls="--",
                zorder=0)
        ax.axhline(0, color=MUTED, lw=0.6, zorder=0)
        ax.axvline(0, color=MUTED, lw=0.6, zorder=0)
        for verdict, part in block.groupby("Verdict"):
            colour = _VERDICT_COLORS.get(str(verdict), _VERDICT_DEFAULT)
            ax.scatter(part["EffectA"], part["EffectB"], s=30, color=colour,
                       edgecolors="white", linewidths=0.4, label=str(verdict),
                       zorder=3)
        # Name only the points that disagree: labelling all fifty would bury
        # the four that matter.
        off = block[block["Verdict"].str.startswith("disagree")]
        for row in off.itertuples():
            ax.annotate(str(row.Metric), (row.EffectA, row.EffectB),
                        textcoords="offset points", xytext=(4, 3), fontsize=6,
                        color=INK)
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-limit, limit)
        ax.set_xlabel(f"effect under {a}", fontsize=9)
        ax.set_ylabel(f"effect under {b}", fontsize=9)
        ax.set_aspect("equal", adjustable="box")
        _bare(ax)

    handles, labels = axes[0][-1].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, fontsize=7, frameon=False,
                   loc="lower center", ncol=min(4, len(labels)),
                   bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Would the conclusion have been the same?\n"
                 "group and age effects, measured each way", fontsize=10)
    fig.tight_layout()
    return _save(fig, out_path)


def plot_measure_decoding(result, out_path: Path, *, scheme=None) -> Path | None:
    """Best decoding score per measure, against chance.

    Which measure carries the most information about the target — the practical
    counterpart of the concordance figure, and the one to read when the answer
    to "which measure should I use" has to be a single name.
    """
    table = getattr(result, "decoding", None)
    if table is None or table.empty:
        return None
    sub = table.dropna(subset=["BalancedAccuracy"]).sort_values(
        "BalancedAccuracy", ascending=True)
    if sub.empty:
        return None
    scheme = scheme or DEFAULT_SCHEME

    colours = scheme.groups(len(sub))
    fig, ax = plt.subplots(figsize=(5.6, max(2.4, 0.5 * len(sub) + 1.4)))
    y = np.arange(len(sub))
    errs = pd.to_numeric(sub["SD"], errors="coerce").fillna(0.0).to_numpy()
    ax.barh(y, sub["BalancedAccuracy"], xerr=errs, color=colours, height=0.6,
            error_kw={"ecolor": MUTED, "elinewidth": 1.0, "capsize": 3})
    chance = pd.to_numeric(sub["Chance"], errors="coerce").dropna()
    if len(chance):
        ax.axvline(float(chance.iloc[0]), color=INK, ls="--", lw=1.0,
                   label="chance")
        ax.legend(fontsize=7, frameon=False, loc="lower right")

    for i, row in enumerate(sub.itertuples()):
        mark = _stars(getattr(row, "PValue", np.nan))
        # Past the error bar, not past the bar: a wide interval would otherwise
        # run straight through the model's name.
        ax.text(float(row.BalancedAccuracy) + float(errs[i]) + 0.015, i,
                f"{row.Model}{(' ' + mark) if mark else ''}", va="center",
                fontsize=7, color=INK)

    ax.set_yticks(y)
    ax.set_yticklabels(sub["ActivityType"], fontsize=8)
    ax.set_xlabel("balanced accuracy (best model)", fontsize=9)
    # Room past 1.0 for the winning model's name, which sits at the bar's end.
    # Without it a measure that decodes perfectly has its label clipped, which
    # is exactly the row a reader looks at first.
    ax.set_xlim(0, 1.22)
    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    target = _target_label(str(sub["Target"].iloc[0])) if "Target" in sub else "target"
    ax.set_title(f"Which measure carries the most information about {target}?",
                 fontsize=10)
    _bare(ax)
    return _save(fig, out_path)
