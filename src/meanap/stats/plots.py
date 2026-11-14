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
import numpy as np
import pandas as pd

from meanap.native.chart import (Band, Bars, Cells, Chart, ColourBar, ErrorBars, Legend,
                                 LegendItem, Line, Panel, Points, Rule, Segments, Span,
                                 Text, rgba)
from meanap.native.chart_paint import save_chart
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
INK_RGBA = rgba(INK)
MUTED_RGBA = rgba(MUTED)
NONE_RGBA = rgba("none")


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


def _ink_for(value: float, cmap: str, low: float, high: float):
    """Ink that reads on a cell of *value*: white on dark colours, else the ink."""
    if not np.isfinite(value):
        return rgba(INK)
    span = (high - low) or 1.0
    r, g, b = matplotlib.colormaps[cmap](min(max((value - low) / span, 0.0), 1.0))[:3]
    return rgba("white") if 0.299 * r + 0.587 * g + 0.114 * b < 0.5 else rgba(INK)


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
    values = wide.to_numpy(float)
    # Stars sit *on* the cells, so their colour has to follow the cell's
    # lightness; a dark star on a saturated red cell is invisible, which is
    # exactly where the significant effects are.
    marks = [[_stars(pvals.iat[i, j]) if np.isfinite(values[i, j]) else ""
              for j in range(n_cols)] for i in range(n_rows)]
    inks = [[_ink_for(values[i, j], DIVERGING, -limit, limit) for j in range(n_cols)]
            for i in range(n_rows)]
    hover = [[(f"{wide.index[i]} · {wide.columns[j]}\n"
               f"effect size {values[i, j]:.3g}, FDR q = {pvals.iat[i, j]:.3g}")
              if np.isfinite(values[i, j]) else "" for j in range(n_cols)]
             for i in range(n_rows)]
    panel = Panel(
        marks=[Cells(values, DIVERGING, -limit, limit, text=marks, text_colour=inks,
                     text_size=9, text_bold=True, hover=hover)],
        title=title or f"Effect sizes — {family}", title_size=11,
        xticks=[(j, str(c)) for j, c in enumerate(wide.columns)], xtick_rotation=30,
        yticks=[(i, str(r)) for i, r in enumerate(wide.index)], tick_size=8,
        grid="", y_down=True)
    chart = Chart([panel], size=(max(4.5, 1.5 * n_cols + 2), max(3.0, 0.28 * n_rows + 1.2)),
                  colour_bar=ColourBar(DIVERGING, -limit, limit, "Effect size", fraction=0.03),
                  note=f"* FDR q < {alpha}   ** q < 0.01   *** q < 0.001", note_size=7,
                  note_align="right")
    return save_chart(chart, out_path)


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
    panels, seen = [], []
    for idx, metric in enumerate(metrics):
        marks = []
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
            colour, name = rgba(colors[str(grp)]), str(grp)
            ages = stat.index.to_numpy(float)
            mean, sem = stat["mean"].to_numpy(float), stat["sem"].to_numpy(float)
            marks += [
                Band(ages, mean - sem, mean + sem, rgba(colors[str(grp)], 0.15), key=name, z=1),
                ErrorBars(ages, mean, yerr=sem, colour=colour, width=2, key=name, z=2),
                Line(ages, mean, colour, width=2, marker="o", marker_size=4, key=name,
                     label=name, z=3,
                     hover=[f"{name}, DIV {a:g}: {m:.4g} ± {s:.3g} (SEM), n = {int(n)}"
                            for a, m, s, n in zip(ages, mean, sem, stat["count"])]),
            ]
            if idx == 0:
                seen.append((name, colour))
        panels.append(Panel(cell=(idx // n_cols, idx % n_cols), marks=marks,
                            title=ds.label(metric), xlabel="Age (DIV)", tick_size=8))
    legend = (Legend([LegendItem(n, c, marker=True, key=n) for n, c in seen], loc="bottom",
                     columns=min(4, len(seen)), size=9) if len(seen) >= 2 else None)
    chart = Chart(panels, size=(3.1 * n_cols, 2.5 * n_rows), grid=(n_rows, n_cols),
                  legend=legend, title=title or "")
    return save_chart(chart, out_path)


# ── correlation ──────────────────────────────────────────────────────────────

def _corr_panel(corr: pd.DataFrame, *, labels, fontsize: float, title: str = "",
                cell=(0, 0), show_x: bool = True, show_y: bool = True) -> Panel:
    n = len(corr.columns)
    values = corr.to_numpy(float)
    names = [str(c) for c in labels]
    hover = [[f"{names[i]} × {names[j]}\nr = {values[i, j]:.3f}" for j in range(n)]
             for i in range(n)]
    return Panel(cell=cell, marks=[Cells(values, DIVERGING, -1, 1, hover=hover)],
                 title=title, xticks=[(j, t) for j, t in enumerate(names)] if show_x else [],
                 yticks=[(i, t) for i, t in enumerate(names)] if show_y else [],
                 xtick_rotation=90, tick_size=fontsize, grid="", y_down=True, equal=True)


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
    panel = _corr_panel(corr, labels=labels, fontsize=7 if len(corr.columns) > 25 else 9,
                        title=f"Feature correlation ({res.method}), clustered")
    panel.title_size = 11
    panel.marks.append(Text(
        0.0, 1.0, f"{len(corr.columns)} metrics, effective dimensionality "
        f"{res.effective_dim:.1f}", MUTED_RGBA, size=8, ha="left", va="bottom",
        coords="axes", offset=(0, 3)))
    panel.title = panel.title + "\n "
    chart = Chart([panel], size=(size, size),
                  colour_bar=ColourBar(DIVERGING, -1, 1, "Correlation", fraction=0.035))
    return save_chart(chart, out_path)


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
    panels = []
    for i, grp in enumerate(groups):
        for j, age in enumerate(ages):
            cell = res.per_cell.get((grp, age))
            if cell is None:
                continue
            panels.append(_corr_panel(cell, labels=labels, fontsize=fontsize,
                                      title=f"{grp}  DIV {age:g}", cell=(i, j),
                                      show_x=i == len(groups) - 1, show_y=j == 0))
    chart = Chart(panels, size=(3.2 * len(ages), 3.2 * len(groups)),
                  grid=(len(groups), len(ages)), gap=(4, 8),
                  colour_bar=ColourBar(DIVERGING, -1, 1, "Correlation", fraction=0.015))
    return save_chart(chart, out_path)


def plot_pca_variance(res, out_path: Path) -> Path | None:
    """Scree plot with the cumulative curve — how many components it takes."""
    var = res.variance_explained
    if var.empty:
        return None
    n = min(20, len(var))
    comp = var["Component"][:n].to_numpy(float)
    each = var["VarianceExplained"][:n].to_numpy(float)
    cum = var["CumulativeVariance"][:n].to_numpy(float)
    # The cumulative curve shares the y-axis (both are fractions of variance),
    # so this is one scale, not a dual axis.
    panel = Panel(
        marks=[Bars(comp, each, width=0.7, colour=rgba("#4c72b0"),
                    hover=[f"PC {c:g}: {v:.1%} of the variance" for c, v in zip(comp, each)]),
               Line(comp, cum, INK_RGBA, width=2, marker="o", marker_size=4,
                    label="Cumulative", z=3,
                    hover=[f"PCs 1–{c:g}: {v:.1%} of the variance" for c, v in zip(comp, cum)]),
               Rule(0.9, colour=MUTED_RGBA, width=1, dash=":"),
               Text(n, 0.905, "90%", MUTED_RGBA, size=8, ha="right", va="bottom")],
        title="Feature-space dimensionality", title_size=11,
        xlabel="Principal component", ylabel="Variance explained",
        legend=Legend([LegendItem("Cumulative", INK_RGBA, marker=True)], loc="center right",
                      size=9))
    return save_chart(Chart([panel], size=(5.5, 3.6)), out_path)


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
    rng = np.random.default_rng(0)
    marks = []
    for i, name in enumerate(order):
        vals = res.scores.loc[res.scores["Model"] == name, "BalancedAccuracy"].to_numpy(float)
        marks.append(Points(i + rng.normal(0, 0.06, len(vals)), vals,
                            fill=rgba("#4c72b0", 0.65), size=float(np.sqrt(26)), key=name,
                            hover=[f"{name}, fold {k + 1}: {v:.3f}"
                                   for k, v in enumerate(vals)]))
        marks.append(Segments([[i - 0.28, vals.mean(), i + 0.28, vals.mean()]],
                              colour=INK_RGBA, width=2.5, key=name, z=4))
        if not res.null.empty:
            row = res.null[res.null["Model"] == name]
            if not row.empty and np.isfinite(row["Null95"].iloc[0]):
                level = float(row["Null95"].iloc[0])
                marks.append(Segments([[i - 0.28, level, i + 0.28, level]],
                                      colour=rgba("#c44e52"), width=1.5, dash="--", key=name,
                                      z=4))
                mark = _stars(row["PValue"].iloc[0])
                if mark:
                    marks.append(Text(i, vals.max() + 0.02, mark, INK_RGBA, size=10,
                                      va="bottom", bold=True))
    marks += [Rule(res.chance, colour=MUTED_RGBA, width=1.2, dash=":"),
              Text(len(order) - 0.4, res.chance + 0.008, "chance", MUTED_RGBA, size=8,
                   ha="right", va="bottom")]
    legend = (Legend([LegendItem("95th centile of label-permutation null", rgba("#c44e52"),
                                 dash="--")], loc="upper left", size=8)
              if not res.null.empty else None)
    panel = Panel(
        marks=marks, xticks=[(i, str(m)) for i, m in enumerate(order)], xtick_rotation=20,
        tick_size=9, ylabel="Balanced accuracy (held-out)", ylim=(0, 1),
        title_size=11, legend=legend, zoom=(False, True),
        title=(f"Decoding {_target_label(res.target)} — {res.n_samples} recordings from "
               f"{res.n_groups} cultures"))
    return save_chart(Chart([panel], size=(max(4.5, 1.1 * len(order) + 1.5), 4.2)), out_path)


def plot_confusion(res, out_path: Path, *, model: str | None = None) -> Path | None:
    """Row-normalised confusion matrix — recall per true class."""
    if not res.confusion:
        return None
    names = [model] if model else list(res.confusion)
    panels = []
    for k, name in enumerate(names):
        mat = res.confusion[name]
        # Normalised by row: with unequal class sizes the raw counts say more
        # about how many recordings each genotype has than about the decoder.
        norm = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0)
        values = norm.to_numpy(float)
        rows, cols = values.shape
        text = [[f"{values[i, j]:.2f}\n({mat.iat[i, j]})" for j in range(cols)]
                for i in range(rows)]
        ink = [[rgba("white") if values[i, j] > 0.55 else INK_RGBA for j in range(cols)]
               for i in range(rows)]
        hover = [[f"true {mat.index[i]}, predicted {mat.columns[j]}: {mat.iat[i, j]} "
                  f"({values[i, j]:.0%} of {mat.index[i]})" for j in range(cols)]
                 for i in range(rows)]
        panels.append(Panel(
            cell=(0, k), marks=[Cells(values, SEQUENTIAL, 0, 1, text=text, text_colour=ink,
                                      text_size=7.5, hover=hover)],
            xticks=[(j, str(c)) for j, c in enumerate(mat.columns)], xtick_rotation=30,
            yticks=[(i, str(r)) for i, r in enumerate(mat.index)], tick_size=8,
            xlabel="Predicted", ylabel="True", label_size=9, title=str(name),
            title_size=10, grid="", y_down=True, equal=True))
    chart = Chart(panels, size=(3.4 * len(names), 3.4), grid=(1, len(names)),
                  colour_bar=ColourBar(SEQUENTIAL, 0, 1, fraction=0.02))
    return save_chart(chart, out_path)


def plot_decoding_importance(res, out_path: Path, *, top: int = 15) -> Path | None:
    """The most informative features per model, held-out permutation importance."""
    if res.importance.empty:
        return None
    models = list(res.importance["Model"].unique())
    panels = []
    for k, name in enumerate(models):
        sub = res.importance[res.importance["Model"] == name].head(top).iloc[::-1]
        y = np.arange(len(sub), dtype=float)
        imp, sd = sub["Importance"].to_numpy(float), sub["SD"].fillna(0).to_numpy(float)
        labels = [str(t) for t in sub["FeatureLabel"]]
        panels.append(Panel(
            cell=(0, k),
            marks=[Bars(y, imp, width=0.7, colour=rgba("#4c72b0"), horizontal=True,
                        hover=[f"{t}: {v:.3f} ± {s:.3f}" for t, v, s in zip(labels, imp, sd)]),
                   ErrorBars(imp, y, xerr=sd, colour=MUTED_RGBA, width=1),
                   Rule(0, axis="x", colour=MUTED_RGBA, width=1)],
            yticks=[(v, t) for v, t in zip(y, labels)], tick_size=7.5,
            title=str(name), title_size=10, xlabel="Drop in balanced accuracy",
            label_size=8.5, sharex="importance", zoom=(True, False)))
    chart = Chart(panels, size=(3.7 * len(models), 4.6), grid=(1, len(models)))
    return save_chart(chart, out_path)


def _row_names(frame: pd.DataFrame, skip) -> list[str]:
    """What each row is, from the columns that are not values: "culture X, DIV 14"."""
    cols = [c for c in frame.columns if c not in skip]
    out = []
    for _, row in frame[cols].iterrows():
        out.append(", ".join(f"{c} {row[c]:g}" if isinstance(row[c], (int, float, np.number))
                             else f"{row[c]}" for c in cols))
    return out


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
    axes_cols = [c for c in coords.columns if str(c).startswith("LD")]
    size = float(np.sqrt(30))

    marks = []
    if "LD2" in coords.columns:
        for level in levels:
            sub = coords[coords[target] == level]
            names = _row_names(sub, set(axes_cols) | {target})
            marks.append(Points(
                sub["LD1"], sub["LD2"], fill=rgba(colors[str(level)], 0.75),
                edge=rgba("white"), edge_width=0.5, size=size, key=str(level),
                hover=[f"{level}: {n}\nLD1 {a:.2f}, LD2 {b:.2f}"
                       for n, a, b in zip(names, sub["LD1"], sub["LD2"])]))
        panel = Panel(
            marks=marks,
            # Share of the *between-class* separation carried by each axis; the
            # two add to 100% by construction (see lda_projection).
            xlabel=(f"LD1 ({explained[0] * 100:.0f}% of class separation)"
                    if len(explained) > 0 else "LD1"),
            ylabel=f"LD2 ({explained[1] * 100:.0f}%)" if len(explained) > 1 else "LD2",
            legend=Legend([LegendItem(str(v), rgba(colors[str(v)], 0.75), kind="point",
                                      size=size, key=str(v)) for v in levels],
                          loc="best", size=9))
        size_in = (5.4, 4.8)
    else:
        # One axis: the groups go on y, so the reader compares distributions
        # along the discriminant rather than reading a scatter with a
        # meaningless second dimension.
        rng = np.random.default_rng(0)
        for i, level in enumerate(levels):
            sub = coords[coords[target] == level]
            names = _row_names(sub, set(axes_cols) | {target})
            marks.append(Points(
                sub["LD1"], i + rng.normal(0, 0.08, len(sub)),
                fill=rgba(colors[str(level)], 0.7), edge=rgba("white"), edge_width=0.5,
                size=size, key=str(level),
                hover=[f"{level}: {n}\nLD1 {a:.2f}" for n, a in zip(names, sub["LD1"])]))
            mean = float(sub["LD1"].mean())
            marks.append(Points([mean], [i], fill=INK_RGBA, size=18, marker="|",
                                edge_width=2.5, key=str(level), z=4,
                                hover=[f"{level}: mean LD1 {mean:.2f}"]))
        panel = Panel(marks=marks, yticks=[(i, str(v)) for i, v in enumerate(levels)],
                      ylim=(-0.6, len(levels) - 0.4), zoom=(True, False),
                      xlabel=("LD1 — the only discriminant axis "
                              f"({len(levels)} groups give {len(levels) - 1})"))
        size_in = (6.0, max(2.4, 0.9 * len(levels) + 1.4))
    panel.title = f"Linear discriminant projection — {_target_label(target)}"
    panel.title_size = 11
    chart = Chart([panel], size=size_in,
                  note="In-sample projection: fitted on all recordings, so the separation "
                       "shown is optimistic.")
    return save_chart(chart, out_path)


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

    colors = _group_colors(models, scheme)
    marks, items = [], []
    x = np.asarray(ages, float)
    for name in models:
        sub = by_age[by_age["Model"] == name].set_index("DIV").reindex(ages)
        # SD across folds, shown as the standard error of their mean: the
        # spread of the estimate, not of the folds.
        n_folds = sub["NFolds"] if "NFolds" in sub.columns else pd.Series(1, index=ages)
        err = (sub["SD"] / np.sqrt(n_folds.clip(lower=1))).fillna(0).to_numpy(float)
        acc = sub["BalancedAccuracy"].to_numpy(float)
        colour = rgba(colors[name])
        marks += [ErrorBars(x, acc, yerr=err, colour=colour, width=2, key=name),
                  Line(x, acc, colour, width=2, marker="o", marker_size=5, key=name, z=3,
                       hover=[f"{name}, DIV {a:g}: {v:.3f} ± {e:.3f} (SEM)"
                              for a, v, e in zip(x, acc, err)])]
        items.append(LegendItem(name, colour, marker=True, key=name))
    chance = float(by_age["Chance"].iloc[0]) if "Chance" in by_age.columns else np.nan
    if np.isfinite(chance):
        marks += [Rule(chance, colour=MUTED_RGBA, width=1.2, dash=":"),
                  Text(ages[-1], chance + 0.01, "chance", MUTED_RGBA, size=8, ha="right",
                       va="bottom")]
    panel = Panel(marks=marks, xlabel="Age (DIV)", ylabel="Balanced accuracy (held-out)",
                  ylim=(0, 1), title="Group separability across age", title_size=11,
                  legend=Legend(items, loc="best", size=9))
    return save_chart(Chart([panel], size=(5.6, 3.8)), out_path)


# ── regression ───────────────────────────────────────────────────────────────

def plot_regression_scores(res, out_path: Path) -> Path | None:
    """Per-model out-of-fold R², every fold drawn."""
    if res.scores.empty:
        return None
    order = (res.scores.groupby("Model")["R2"].mean()
             .sort_values(ascending=False).index.tolist())
    rng = np.random.default_rng(0)
    marks = []
    for i, name in enumerate(order):
        vals = res.scores.loc[res.scores["Model"] == name, "R2"].to_numpy(float)
        marks.append(Points(i + rng.normal(0, 0.06, len(vals)), vals,
                            fill=rgba("#4c72b0", 0.65), size=float(np.sqrt(26)), key=name,
                            hover=[f"{name}, fold {k + 1}: R² = {v:.3f}"
                                   for k, v in enumerate(vals)]))
        marks.append(Segments([[i - 0.28, vals.mean(), i + 0.28, vals.mean()]],
                              colour=INK_RGBA, width=2.5, key=name, z=4))
    marks += [Rule(0, colour=MUTED_RGBA, width=1.2, dash=":"),
              Text(len(order) - 0.4, 0.012, "no better than the mean", MUTED_RGBA, size=8,
                   ha="right", va="bottom")]
    panel = Panel(
        marks=marks, xticks=[(i, str(m)) for i, m in enumerate(order)], xtick_rotation=20,
        tick_size=9, ylabel="R² (held-out)", zoom=(False, True), title_size=11,
        title=(f"Predicting {_target_label(res.target)} from network and activity "
               "features"))
    return save_chart(Chart([panel], size=(max(4.5, 1.1 * len(order) + 1.5), 4.0)), out_path)


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
    y = np.arange(len(sub), dtype=float)
    names = [str(t) for t in sub["FeatureLabel"]]
    shap, alone, unique = (sub[c].to_numpy(float) for c in ("Shapley", "Marginal", "Unique"))
    hover = [f"{n}\nShapley {s:.3f}, alone {a:.3f}, unique {u:.3f}"
             for n, s, a, u in zip(names, shap, alone, unique)]
    blue, red = rgba("#4c72b0"), rgba("#c44e52")
    panel = Panel(
        marks=[Bars(y, shap, width=0.62, colour=blue, horizontal=True, hover=hover, z=3),
               Points(alone, y, fill=NONE_RGBA, edge=MUTED_RGBA, edge_width=1.3,
                      size=float(np.sqrt(34)), z=4, hover=hover),
               Points(unique, y, fill=red, marker="|", size=float(np.sqrt(90)),
                      edge_width=1.8, z=5, hover=hover)],
        yticks=[(v, t) for v, t in zip(y, names)], tick_size=8, zoom=(True, False),
        xlabel=f"Share of variance in {_target_label(res.target)}", title_size=11,
        title=(f"What explains {_target_label(res.target)}? Full-model R² = "
               f"{res.r2_full:.2f}, partitioned across {len(dec)} features"),
        legend=Legend([LegendItem("Shapley share of R²", blue, kind="box"),
                       LegendItem("alone (R² of this feature only)", MUTED_RGBA, kind="open",
                                  size=float(np.sqrt(34))),
                       LegendItem("unique (drop in R² if removed)", red, kind="tick",
                                  size=float(np.sqrt(90)))],
                      loc="lower right", size=8))
    return save_chart(Chart([panel], size=(7.2, max(3.4, 0.32 * len(sub) + 1.4))), out_path)


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

    rng = np.random.default_rng(0)
    # Jitter the observed axis: ages are a handful of discrete values, so
    # without it every recording at one DIV lands on a single vertical line.
    jitter = rng.normal(0, 0.35, len(sub))
    observed = sub["Observed"].to_numpy(float)
    predicted = sub["Predicted"].to_numpy(float)
    names = _row_names(sub, {"Model", "Observed", "Predicted"})
    lo = float(min(observed.min(), predicted.min()))
    hi = float(max(observed.max(), predicted.max()))
    r2 = res.scores.loc[res.scores["Model"] == model, "R2"].mean()
    panel = Panel(
        marks=[Points(observed + jitter, predicted, fill=rgba("#4c72b0", 0.5),
                      size=float(np.sqrt(22)),
                      hover=[f"{n}\nobserved {o:g}, predicted {p:.3g}"
                             for n, o, p in zip(names, observed, predicted)]),
               Line([lo, hi], [lo, hi], INK_RGBA, width=1.2, dash="--")],
        xlabel=f"Observed {_target_label(res.target)}",
        ylabel=f"Predicted {_target_label(res.target)} (held-out)",
        title=f"{model}: R² = {r2:.2f}", title_size=11)
    return save_chart(Chart([panel], size=(4.8, 4.6)), out_path)


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
    values = wide.to_numpy(float)
    names = [labels.get(f, f) for f in wide.index]
    text = [[f"{values[i, j]:+.02f}" if np.isfinite(values[i, j]) else ""
             for j in range(n_cols)] for i in range(n_rows)]
    ink = [[rgba("white") if np.isfinite(values[i, j]) and abs(values[i, j]) / limit > 0.6
            else INK_RGBA for j in range(n_cols)] for i in range(n_rows)]
    hover = [[f"{names[i]}, DIV {wide.columns[j]:g}: {values[i, j]:+.3f}"
              if np.isfinite(values[i, j]) else "" for j in range(n_cols)]
             for i in range(n_rows)]

    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    heads = []
    for age in wide.columns:
        if totals is not None and age in totals.index:
            heads.append(f"DIV {age:g}\n{totals.loc[age, 'Total']:.2f} total")
        else:
            heads.append(f"DIV {age:g}")
    panel = Panel(
        marks=[Cells(values, DIVERGING, -limit, limit, text=text, text_colour=ink,
                     text_size=7.5, hover=hover)],
        xticks=[(j, h) for j, h in enumerate(heads)],
        yticks=[(i, str(n)) for i, n in enumerate(names)], tick_size=8, grid="",
        y_down=True, title="Which features carry the genotype signal, and when",
        title_size=11)
    chart = Chart([panel], size=(max(4.5, 1.25 * n_cols + 3.2), max(3.0, 0.34 * n_rows + 1.8)),
                  colour_bar=ColourBar(DIVERGING, -limit, limit,
                                       "Shapley share of balanced accuracy above chance",
                                       fraction=0.03),
                  note="Each column sums to that age's decodability. Negative means the "
                       "feature cost the decoder accuracy there.")
    return save_chart(chart, out_path)


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
    x = np.asarray(ages, float)

    ranked = wide.abs().max(axis=1).sort_values(ascending=False).index.tolist()
    leading, rest = ranked[:top], ranked[top:]

    upper = Panel(cell=(0, 0), xticks=[], sharex="age", zoom=(True, False),
                  ylabel="Decodability\n(accuracy − chance)", label_size=9)
    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    if totals is not None:
        present = [a for a in ages if a in totals.index]
        values = totals.loc[present, "Total"].to_numpy(float)
        upper.marks += [
            Line(np.asarray(present, float), values, INK_RGBA, width=2, marker="o",
                 marker_size=5, hover=[f"DIV {a:g}: {v:.3f} above chance"
                                       for a, v in zip(present, values)]),
            Rule(0, colour=MUTED_RGBA, width=1, dash=":")]
        upper.title = "Genotype decoding, and what carries it, across age"
        upper.title_size = 11

    marks, items = [], []
    for i, feature in enumerate(leading):
        name = str(labels.get(feature, feature))
        values = wide.loc[feature].to_numpy(float)
        colour = rgba(_FEATURE_HUES[i])
        marks.append(Line(x, values, colour, width=2, marker="o", marker_size=4.5, key=name,
                          hover=[f"{name}, DIV {a:g}: {v:+.3f}" for a, v in zip(x, values)]))
        items.append(LegendItem(name, colour, marker=True, key=name))
    if rest:
        # Summed, not dropped: the values are additive, so the remainder is a
        # meaningful line and keeping it means the panel still adds up to the
        # total drawn above it.
        name = f"other {len(rest)} features (summed)"
        values = wide.loc[rest].sum(axis=0).to_numpy(float)
        marks.append(Line(x, values, MUTED_RGBA, width=1.6, dash="--", marker="o",
                          marker_size=4, key=name,
                          hover=[f"{name}, DIV {a:g}: {v:+.3f}" for a, v in zip(x, values)]))
        items.append(LegendItem(name, MUTED_RGBA, dash="--", marker=True, key=name))
    marks.append(Rule(0, colour=MUTED_RGBA, width=1))
    lower = Panel(cell=(1, 0), marks=marks, xlabel="Age (DIV)",
                  ylabel="Shapley share of decodability", label_size=9,
                  xticks=[(a, f"{a:g}") for a in ages], sharex="age", zoom=(True, False))
    chart = Chart([upper, lower], size=(7.0, 6.4), grid=(2, 1), heights=[1, 2.6],
                  legend=Legend(items, loc="bottom", columns=2, size=8))
    return save_chart(chart, out_path)


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

    positions = np.arange(len(ages), dtype=float)
    width = 0.8 / len(families)
    marks, items = [], []
    for i, family in enumerate(families):
        offset = (i - (len(families) - 1) / 2) * width
        name = str(labels.get(family, family))
        values = np.asarray([wide.loc[family, a] for a in ages], float)
        colour = rgba(_family_colour(family))
        marks.append(Bars(positions + offset, values, width=width * 0.92, colour=colour,
                          key=name, hover=[f"{name}, DIV {a:g}: {v:+.3f}"
                                           for a, v in zip(ages, values)]))
        items.append(LegendItem(f"{name}  ({counts.get(family, 0)} metrics)", colour,
                                kind="box", key=name))

    totals = res.totals.set_index("DIV") if not res.totals.empty else None
    if totals is not None:
        present = [a for a in ages if a in totals.index]
        values = [float(totals.loc[a, "Total"]) for a in present]
        marks.append(Points([positions[ages.index(a)] for a in present], values,
                            fill=INK_RGBA, marker="_", size=26, edge_width=2.5, z=4,
                            hover=[f"DIV {a:g}: total {v:+.3f}"
                                   for a, v in zip(present, values)]))
        items.append(LegendItem("total decodability", INK_RGBA, kind="hline"))

    marks.append(Rule(0, colour=MUTED_RGBA, width=1))
    panel = Panel(marks=marks, xticks=[(p, f"DIV {a:g}") for p, a in zip(positions, ages)],
                  ylabel="Shapley share of decodability", zoom=(False, True), title_size=11,
                  title="What kind of feature carries the genotype difference",
                  legend=Legend(items, loc="upper right", columns=2, size=8.5))
    chart = Chart([panel], size=(max(5.5, 1.5 * len(ages) + 2.5), 4.2),
                  note="Bars at one age sum to that age's total. A family is one player, "
                       "so metrics that duplicate each other inside it cost it nothing.")
    return save_chart(chart, out_path)


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
    x = np.asarray(ages, float)

    panels = []
    for k, family in enumerate(families):
        sub = table[table["Family"] == family].set_index("DIV").reindex(ages)
        colour = rgba(_family_colour(family))
        name = str(labels.get(family, family))
        alone, unique = sub["Alone"].to_numpy(float), sub["Unique"].to_numpy(float)
        panels.append(Panel(
            cell=(0, k), title=name, title_size=10, xlabel="Age (DIV)", label_size=9,
            ylabel="Balanced accuracy above chance" if k == 0 else "",
            xticks=[(a, f"{a:g}") for a in ages], sharey="accuracy",
            ylabels=k == 0,
            marks=[Band(x, unique, alone, rgba(_family_colour(family), 0.16)),
                   Line(x, alone, colour, width=2, dash="--", marker="o", marker_size=5,
                        key="alone", hover=[f"{name}, DIV {a:g}: alone {v:+.3f}"
                                            for a, v in zip(x, alone)]),
                   Line(x, unique, colour, width=2.4, marker="o", marker_size=5,
                        key="unique", hover=[f"{name}, DIV {a:g}: unique {v:+.3f}"
                                             for a, v in zip(x, unique)]),
                   Rule(0, colour=INK_RGBA, width=1)]))
    # The legend goes under the panels rather than inside the first one: the
    # upper-left corner is where the "alone" curve peaks in every family, so an
    # in-axes legend sits on the data it is describing. Its swatches are in
    # ink: they distinguish two *line styles*, and a blue swatch beside "alone"
    # would read as though the entry meant the Activity family.
    legend = Legend([LegendItem("alone", INK_RGBA, dash="--", marker=True, key="alone"),
                     LegendItem("unique", INK_RGBA, marker=True, key="unique")],
                    loc="bottom", columns=2, size=9, swatch=3.4)
    chart = Chart(panels, size=(3.5 * len(families), 4.0), grid=(1, len(families)),
                  title="Does each family carry signal of its own?", legend=legend,
                  note="Dashed: what the family achieves on its own. Solid: what is lost "
                       "when it is removed from the full set. A solid line at zero means "
                       "the family carries nothing the others do not. Solid above dashed "
                       "is complementarity: worth more in company than alone.")
    return save_chart(chart, out_path)


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
    """Shared body of the two sweep figures: one panel per metric, one line per level.

    Returns the panels, the metrics drawn and the legend entries.
    """
    metrics = [m for m in metrics if m in labelled.columns]
    panels, items = [], {}
    for idx, metric in enumerate(metrics):
        marks = []
        for level, colour in colours.items():
            sub = labelled[labelled[split_col] == level]
            if sub.empty:
                continue
            stat = sub.groupby("Density")[metric].agg(["mean", "sem", "count"])
            stat = stat[stat["count"] >= 2]
            if stat.empty:
                continue
            name = str(level)
            x = stat.index.to_numpy(float)
            mean, sem = stat["mean"].to_numpy(float), stat["sem"].to_numpy(float)
            marks += [Band(x, mean - sem, mean + sem, rgba(colour, 0.18), key=name),
                      Line(x, mean, rgba(colour), width=2, key=name,
                           hover=[f"{name}, density {d:g}: {m:.4g} ± {s:.3g} (SEM)"
                                  for d, m, s in zip(x, mean, sem)])]
            if idx == 0:
                items[name] = LegendItem(name, rgba(colour), key=name)
        panels.append(Panel(cell=(idx // n_cols, idx % n_cols), marks=marks,
                            title=ylabel_of(metric), xlabel="Imposed density", tick_size=8,
                            sharex="density", zoom=(True, False)))
    return panels, metrics, list(items.values())


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
    panels, drawn, items = _sweep_panels(
        labelled, metrics, split, colours, n_cols, lambda m: _SWEEP_LABELS.get(m, m))
    if not drawn:
        return None
    n_rows = int(np.ceil(len(drawn) / n_cols))
    legend = (Legend(items, loc="bottom", columns=min(5, len(items)), size=9)
              if len(items) >= 2 else None)
    chart = Chart(panels, size=(3.2 * n_cols, 2.6 * n_rows), grid=(n_rows, n_cols),
                  title=title, legend=legend)
    return save_chart(chart, out_path)


def _by_age_scatter(observed, column, group_col, age_col, groups, colours, rng):
    """Every recording's *column* by age, groups side by side, with their medians."""
    marks = []
    for offset, group in enumerate(groups):
        sub = observed[observed[group_col] == group]
        jitter = (offset - (len(groups) - 1) / 2) * 0.9
        name, colour = str(group), colours[str(group)]
        ages = sub[age_col].to_numpy(float)
        values = sub[column].to_numpy(float)
        names = _row_names(sub, {column, group_col, age_col, "ObservedDensity", "NNodes"})
        marks.append(Points(ages + jitter + rng.normal(0, 0.25, len(sub)), values,
                            fill=rgba(colour, 0.55), size=4.0, key=name,
                            hover=[f"{name}, DIV {a:g}: {v:.4g}" + (f"\n{n}" if n else "")
                                   for a, v, n in zip(ages, values, names)]))
        stat = sub.groupby(age_col)[column].median()
        marks.append(Line(stat.index.to_numpy(float) + jitter, stat.to_numpy(float),
                          rgba(colour), width=2, marker="o", marker_size=5, key=name, z=4,
                          hover=[f"{name}, DIV {a:g}: median {v:.4g}"
                                 for a, v in zip(stat.index, stat.to_numpy(float))]))
    return marks


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
    groups = list(pd.unique(observed[group_col].dropna())) if group_col in observed else []
    colours = _group_colors([str(g) for g in groups], scheme)
    ages = sorted(pd.unique(observed[age_col].dropna())) if age_col in observed else []
    rng = np.random.default_rng(0)
    marks = (_by_age_scatter(observed, "ObservedDensity", group_col, age_col, groups,
                             colours, rng) if ages else [])
    # The band the sweep imposes, against the densities that actually occur.
    marks += [Span(min(densities), max(densities)),
              Text(0, max(densities), " swept range", MUTED_RGBA, size=8, ha="left",
                   va="bottom", coords="blend")]
    left = Panel(cell=(0, 0), marks=marks, xlabel="Age (DIV)",
                 ylabel="Observed density (step 4)", ylim=(0, 1.02),
                 xticks=[(a, f"{a:g}") for a in ages] or None,
                 title="Densities the recordings actually have", title_size=10,
                 legend=(Legend([LegendItem(str(g), rgba(colours[str(g)]), kind="point",
                                            key=str(g)) for g in groups],
                                loc="lower right", size=8.5) if groups else None))
    right = Panel(cell=(0, 1), xlabel="Imposed density",
                  ylabel="Largest component (fraction of nodes)",
                  title="How much of the network survives thresholding", title_size=10)
    if labelled is not None and not labelled.empty and "lccFraction" in labelled:
        for group in groups:
            sub = labelled[labelled[group_col] == group]
            if sub.empty:
                continue
            stat = sub.groupby("Density")["lccFraction"].mean()
            name = str(group)
            right.marks.append(Line(
                stat.index.to_numpy(float), stat.to_numpy(float), rgba(colours[name]),
                width=2, key=name, hover=[f"{name}, density {d:g}: {v:.2f} of the nodes"
                                          for d, v in zip(stat.index, stat.to_numpy(float))]))
        right.marks.append(Rule(1.0, colour=MUTED_RGBA, width=1, dash=":"))
        right.ylim = (0, 1.05)
    chart = Chart([left, right], size=(10.5, 4.0), grid=(1, 2),
                  title="Reading the density sweep",
                  note="Left: if the groups' observed densities differ, metrics compared "
                       "at those densities were confounded. Right: where the largest "
                       "component falls below 1 the network is fragmented and path "
                       "length is averaged over connected pairs only — prefer global "
                       "efficiency there.")
    return save_chart(chart, out_path)


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
    colour_raw, colour_new = rgba(_OKABE_ITO[5]), rgba(_OKABE_ITO[2])
    x = np.asarray(ages, float)
    series_of = (
        (raw_t, colour_raw, "as measured (step 4)", "--"),
        (new_t, colour_new, "density + size controlled", "-"),
    )
    panels = []
    for k, measure in enumerate(measures):
        marks = []
        for frame, colour, label, style in series_of:
            series = frame.set_index("DIV").reindex(ages)[measure].to_numpy(float)
            marks.append(Line(x, series, colour, width=2.2, dash=style, marker="o",
                              marker_size=5, key=label,
                              hover=[f"{label}, DIV {a:g}: {v:+.3f}"
                                     for a, v in zip(x, series)]))
        marks.append(Rule(0, colour=INK_RGBA, width=1))
        panels.append(Panel(cell=(0, k), marks=marks, title=titles[measure], title_size=10,
                            xlabel="Age (DIV)", label_size=9, sharex="age",
                            xticks=[(a, f"{a:g}") for a in ages],
                            ylabel="Balanced accuracy above chance" if k == 0 else ""))
    legend = Legend([LegendItem(label, colour, dash=style, marker=True, key=label)
                     for _, colour, label, style in series_of],
                    loc="bottom", columns=2, size=9)
    chart = Chart(panels, size=(11.0, 3.8), grid=(1, 3), legend=legend,
                  title="Does network topology carry genotype information of its own?",
                  note="Topology measured on networks thresholded to a common density and "
                       "subsampled to a common node count, against the same metrics as "
                       "step 4 measured them. Activity and correlation strength are left "
                       "uncontrolled in both — they are what topology is being tested "
                       "against.")
    return save_chart(chart, out_path)


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

    groups = (list(pd.unique(observed[group_col].dropna()))
              if group_col in observed.columns else [])
    colours = _group_colors([str(g) for g in groups], scheme)
    has_age = age_col in observed.columns and observed[age_col].notna().any()
    rng = np.random.default_rng(0)

    # Left: node counts, on a log axis because they span an order of magnitude
    # and the target would otherwise sit squashed against the bottom.
    left = Panel(cell=(0, 0), ylog=True, ylabel="Connected nodes per recording",
                 title="Sizes the recordings actually have", title_size=10)
    if has_age:
        ages = sorted(pd.unique(observed[age_col].dropna()))
        left.marks += _by_age_scatter(observed, "NNodes", group_col, age_col, groups,
                                      colours, rng)
        left.xlabel = f"Age ({age_col})"
        left.xticks = [(a, f"{a:g}") for a in ages]
        if groups:
            # Lower right is the emptiest corner here: it is inside the band of
            # sizes too small to keep, where by definition few points sit.
            left.legend = Legend([LegendItem(str(g), rgba(colours[str(g)]), kind="point",
                                             key=str(g)) for g in groups],
                                 loc="lower right", size=8.5)
    else:
        for offset, group in enumerate(groups):
            sub = observed[observed[group_col] == group]
            values = sub["NNodes"].to_numpy(float)
            left.marks.append(Points(
                np.full(len(sub), offset) + rng.normal(0, 0.08, len(sub)), values,
                fill=rgba(colours[str(group)], 0.55), size=4.0, key=str(group),
                hover=[f"{group}: {v:g} nodes" for v in values]))
        left.xticks = [(k, str(g)) for k, g in enumerate(groups)]
        left.tick_size = 8
    finite = observed["NNodes"].to_numpy(float)
    finite = finite[np.isfinite(finite) & (finite > 0)]
    floor = float(finite.min()) / 10 if len(finite) else n_nodes / 10
    left.marks += [Rule(n_nodes, colour=INK_RGBA, width=1.2, dash="--"),
                   Span(floor, n_nodes, colour=rgba(FLAGGED, 0.10)),
                   Text(0, n_nodes, f" subsampled to {n_nodes}", INK_RGBA, size=8, ha="left",
                        va="bottom", coords="blend")]

    # Right: retention. Recomputed here rather than read, so the figure needs
    # only the table it is already handed.
    right = Panel(cell=(0, 1), ylabel="Fraction of recordings retained", zoom=(False, True))
    if groups:
        kept = (observed.assign(_kept=observed["NNodes"] >= n_nodes)
                .groupby(group_col)["_kept"].agg(["mean", "sum", "size"]))
        kept = kept.reindex([g for g in groups if g in kept.index])
        positions = np.arange(len(kept), dtype=float)
        right.marks.append(Bars(
            positions, kept["mean"].to_numpy(float), width=0.62,
            colour=[rgba(colours[str(g)]) for g in kept.index],
            key=[str(g) for g in kept.index],
            hover=[f"{g}: kept {int(r['sum'])} of {int(r['size'])} ({r['mean']:.0%})"
                   for g, (_, r) in zip(kept.index, kept.iterrows())]))
        for pos, (_, row) in zip(positions, kept.iterrows()):
            right.marks.append(Text(
                pos, row["mean"] + 0.02,
                f"{row['mean']:.0%}\n{int(row['sum'])}/{int(row['size'])}",
                INK_RGBA, size=8, va="bottom"))
        right.xticks = [(p, str(g)) for p, g in zip(positions, kept.index)]
        right.tick_size = 8.5
        right.ylim = (0, 1.18)
        spread = float(kept["mean"].max() - kept["mean"].min())
        # The same 20-point rule the runner warns on, drawn rather than logged.
        if spread > 0.2:
            right.title = f"Kept per group - {spread:.0%} spread, uneven"
            right.title_colour = rgba(FLAGGED)
        else:
            right.title = "Kept per group"
        right.title_size = 10
    chart = Chart([left, right], size=(10.5, 4.0), grid=(1, 2),
                  title="Controlling for network size",
                  note="Left: every recording below the dashed line was dropped — it "
                       "cannot be subsampled up to the common size.\n"
                       "Right: if the groups were not dropped evenly, the comparison is "
                       "now between the largest networks of one group and typical ones "
                       "of another, and the size confound has been traded rather than "
                       "removed.")
    return save_chart(chart, out_path)


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
    panels = []
    for idx, (a, b) in enumerate(pairs):
        sub = table[(table["GroupA"] == a) & (table["GroupB"] == b)]
        sub = sub.set_index("Metric").reindex(order).dropna(subset=["GapAll"])
        rows = np.arange(len(sub), dtype=float)
        colours = [rgba(FLAGGED) if bool(r["Flagged"]) else MUTED_RGBA
                   for _, r in sub.iterrows()]
        names = [_SWEEP_LABELS.get(m, m) for m in sub.index]
        every, cut = sub["GapAll"].to_numpy(float), sub["GapRestricted"].to_numpy(float)
        hover = [f"{n}: {g:+.2f} over every recording, {r:+.2f} after the cut"
                 + (" (flagged)" if bool(f) else "")
                 for n, g, r, f in zip(names, every, cut, sub["Flagged"])]
        panels.append(Panel(
            cell=(0, idx),
            marks=[Segments(np.column_stack([every, rows, cut, rows]),
                            colour=[rgba(c, 0.85) for c in colours], width=2),
                   Points(every, rows, fill=rgba("white"), edge=colours, edge_width=1.4,
                          size=float(np.sqrt(34)), hover=hover),
                   Points(cut, rows, fill=colours, size=float(np.sqrt(34)), hover=hover),
                   Rule(0, axis="x", colour=INK_RGBA, width=0.9, dash=":")],
            yticks=[(r, n) for r, n in zip(rows, names)], tick_size=8, ylabels=idx == 0,
            xlabel="Standardised group difference", label_size=8.5,
            title=f"{a} vs {b}", title_size=9.5, sharex="gap", sharey="metric",
            zoom=(True, False)))

    threshold = getattr(check, "threshold", None)
    cohort = ""
    if getattr(check, "n_restricted", 0) and getattr(check, "n_all", 0):
        cohort = f" ({check.n_restricted} of {check.n_all} recordings)"
    chart = Chart(panels, size=(3.6 * len(pairs) + 1.2, 4.2), grid=(1, len(pairs)),
                  title="Do the group differences survive a stricter size cut?",
                  note="Open marker: every swept recording. Filled: only those with at "
                       f"least {threshold} nodes{cohort}. Nothing is re-swept between the "
                       "two, so the movement is the cohort changing, not the measurement — "
                       "a long line in the warning colour means the difference is partly "
                       "about which recordings were big enough to keep.")
    return save_chart(chart, out_path)


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

    panels = []
    for idx, term in enumerate(terms):
        sub = shown[shown["Term"] == term]
        marks = []
        for row_idx, metric in enumerate(order):
            points = (sub[sub["Metric"] == metric]
                      .set_index("Control").reindex(present).dropna(subset=["EffectSize"]))
            if points.empty:
                continue
            values = points["EffectSize"].to_numpy(float)
            if len(points) > 1:
                marks.append(Line(values, [row_idx] * len(points), rgba(MUTED, 0.7),
                                  width=1.2, z=1))
            for control, point in points.iterrows():
                colour = rgba(_CONTROL_COLOURS.get(control, INK))
                q = point.get("PValueFDR")
                significant = pd.notna(q) and float(q) < alpha
                label = _CONTROL_LABELS.get(control, control)
                marks.append(Points(
                    [point["EffectSize"]], [row_idx], fill=colour if significant else
                    rgba("white"), edge=colour, edge_width=1.5, size=float(np.sqrt(42)),
                    key=label, hover=[f"{_SWEEP_LABELS.get(metric, metric)}, {label}: "
                                      f"{float(point['EffectSize']):+.2f}"
                                      + (f", FDR q = {float(q):.3g}" if pd.notna(q) else "")]))
        marks.append(Rule(0, axis="x", colour=INK_RGBA, width=0.9, dash=":"))
        panels.append(Panel(
            cell=(0, idx), marks=marks,
            yticks=[(k, _SWEEP_LABELS.get(m, m)) for k, m in enumerate(order)], tick_size=8,
            ylabels=idx == 0, title="Age" if str(term) == "age" else str(term),
            title_size=9.5, xlabel="Effect size", label_size=8.5, sharey="metric",
            zoom=(True, False)))

    legend = Legend([LegendItem(_CONTROL_LABELS.get(c, c),
                                rgba(_CONTROL_COLOURS.get(c, INK)), kind="point", size=7,
                                key=_CONTROL_LABELS.get(c, c)) for c in present],
                    loc="bottom", columns=len(present), size=8.5)
    isolated = "density" in present and "density+size" in present
    note = ("Matched density to matched density + size is the node-subsampling "
            "step on its own." if isolated else
            "Only one controlled condition was run, so the density and size "
            "controls cannot be told apart here.")
    chart = Chart(panels, size=(3.5 * len(terms) + 1.3, 4.4), grid=(1, len(terms)),
                  title="Age and genotype effects, before and after the controls",
                  legend=legend,
                  note="Filled markers survive FDR correction; open ones do not. An "
                       "effect that collapses toward zero under control was a statement "
                       "about how dense or how large the networks were, not about their "
                       f"organisation. {note} Every condition is measured on the "
                       "recordings all of them have, so a step is the control changing "
                       "and not the cohort.")
    return save_chart(chart, out_path)


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

    panels = []
    last = len(metrics) - 1
    for r, metric in enumerate(metrics):
        for c, contrast in enumerate(contrasts):
            sub = per_age[(per_age["Metric"] == metric)
                          & (per_age["Contrast"].astype(str) == contrast)]
            marks = []
            for control in present:
                line = sub[sub["Control"] == control].sort_values("Age")
                if line.empty:
                    continue
                colour = rgba(_CONTROL_COLOURS.get(control, INK))
                label = _CONTROL_LABELS.get(control, control)
                ages = line["Age"].to_numpy(float)
                g = line["EffectSize"].to_numpy(float)
                q = line["PValueFDR"].to_numpy(float)
                significant = np.isfinite(q) & (q < alpha)
                marks += [
                    Line(ages, g, colour, width=1.8, key=label, z=2),
                    Points(ages, g, fill=[colour if ok else rgba("white")
                                          for ok in significant],
                           edge=colour, edge_width=1.4, size=float(np.sqrt(30)), key=label,
                           hover=[f"{contrast}, {label}, DIV {a:g}: g = {v:+.2f}"
                                  + (f", FDR q = {p:.3g}" if np.isfinite(p) else "")
                                  for a, v, p in zip(ages, g, q)])]
            marks.append(Rule(0, colour=INK_RGBA, width=0.9, dash=":"))
            panels.append(Panel(
                cell=(r, c), marks=marks, title=contrast if r == 0 else "",
                ylabel=_SWEEP_LABELS.get(metric, metric) if c == 0 else "", label_size=7.5,
                xlabel="Age (DIV)" if r == last else "", tick_size=7.5,
                xlabels=r == last, ylabels=c == 0, sharex="age", sharey="g"))
    legend = Legend([LegendItem(_CONTROL_LABELS.get(c, c), rgba(_CONTROL_COLOURS.get(c, INK)),
                                marker=True, key=_CONTROL_LABELS.get(c, c)) for c in present],
                    loc="bottom", columns=len(present), size=8.5)
    chart = Chart(panels, size=(2.9 * len(contrasts) + 1.0, 1.75 * len(metrics) + 1.8),
                  grid=(len(metrics), len(contrasts)), legend=legend, gap=(10, 8),
                  title="Genotype differences at each age, before and after the controls",
                  note="Hedges' g at each age; filled markers survive FDR correction. "
                       "Not the same statistic as the pooled figure, so read the shape "
                       "across ages rather than against that one. Every condition is "
                       "measured on the recordings all of them have, so a step is the "
                       "control changing and not the cohort.")
    return save_chart(chart, out_path)


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
    controlled = [c for c, name in enumerate(controls) if name != "none"]
    panels, items = [], {}
    last = len(metrics) - 1
    for r, metric in enumerate(metrics):
        for c, control in enumerate(controls):
            sub = values[(values["Metric"] == metric) & (values["Control"] == control)]
            marks = []
            for group in groups:
                line = sub[sub["Group"] == group].sort_values("Age")
                if line.empty:
                    continue
                name = str(group)
                colour = colours[name]
                ages = line["Age"].to_numpy(float)
                mean, sem = line["Mean"].to_numpy(float), line["SEM"].to_numpy(float)
                marks += [Band(ages, mean - sem, mean + sem, rgba(colour, 0.18), key=name),
                          Line(ages, mean, rgba(colour), width=1.8, marker="o", marker_size=4,
                               key=name, hover=[f"{name}, DIV {a:g}: {m:.4g} ± {s:.3g} (SEM)"
                                                for a, m, s in zip(ages, mean, sem)])]
                items.setdefault(name, LegendItem(name, rgba(colour), marker=True, key=name))
            shared = c in controlled and len(controlled) > 1
            panels.append(Panel(
                cell=(r, c), marks=marks,
                title=_CONTROL_LABELS.get(control, control) if r == 0 else "",
                ylabel=_SWEEP_LABELS.get(metric, metric) if c == 0 else "", label_size=7.5,
                xlabel="Age (DIV)" if r == last else "", tick_size=7.5,
                xlabels=r == last and not sub.empty,
                ylabels=not sub.empty and not (shared and c != controlled[0]),
                yticks=[] if sub.empty else None,
                empty="no step-4 equivalent" if sub.empty else "",
                sharex="age", sharey=f"row {r}" if shared else None))
    legend = (Legend(list(items.values()), loc="bottom", columns=min(5, len(items)), size=8.5)
              if items else None)
    chart = Chart(panels, size=(2.9 * len(controls) + 1.0, 1.75 * len(metrics) + 1.8),
                  grid=(len(metrics), len(controls)), legend=legend, gap=(10, 8),
                  title="The metrics themselves, under each level of control",
                  note="Mean ± SEM. The controlled columns of a row share a y axis, so "
                       "the subsampling step can be read directly; the uncontrolled "
                       "column is a different measurement of the same quantity and is "
                       "scaled on its own. Every condition uses the recordings all of "
                       "them have.")
    return save_chart(chart, out_path)


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
    values = wide.to_numpy(float)
    cmap = matplotlib.colormaps[DIVERGING]

    def ink(value):
        r, g, b, _ = cmap((value + 1) / 2)
        return rgba("white") if (0.299 * r + 0.587 * g + 0.114 * b) < 0.55 else INK_RGBA

    text = [[f"{values[i, j]:.2f}" if np.isfinite(values[i, j]) else ""
             for j in range(n_cols)] for i in range(n_rows)]
    inks = [[ink(values[i, j]) if np.isfinite(values[i, j]) else INK_RGBA
             for j in range(n_cols)] for i in range(n_rows)]
    hover = [[f"{wide.index[i]}, {wide.columns[j]}: rho = {values[i, j]:.3f}"
              if np.isfinite(values[i, j]) else "" for j in range(n_cols)]
             for i in range(n_rows)]
    panel = Panel(
        marks=[Cells(values, DIVERGING, -1, 1, text=text, text_colour=inks, text_size=7,
                     hover=hover)],
        xticks=[(j, str(c)) for j, c in enumerate(wide.columns)], xtick_rotation=20,
        yticks=[(i, str(r)) for i, r in enumerate(wide.index)], tick_size=7, grid="",
        y_down=True, title_size=10,
        title="Do the measures rank recordings the same way?\n"
              "Spearman rho between measures, over matched recordings")
    chart = Chart([panel], size=(max(4.0, 1.9 * n_cols + 2.4), max(3.0, 0.28 * n_rows + 1.4)),
                  colour_bar=ColourBar(DIVERGING, -1, 1, "Spearman rho", fraction=0.035))
    return save_chart(chart, out_path)


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
    colours = dict(zip(pairs, matplotlib.colormaps["tab10"].colors))
    offsets = np.linspace(-0.22, 0.22, len(pairs)) if len(pairs) > 1 else [0.0]

    marks = [Rule(0.0, axis="x", colour=MUTED_RGBA, width=1.0, z=0)]
    pcol = "PValueFDR" if "PValueFDR" in sub.columns else "PValue"
    for pair, offset in zip(pairs, offsets):
        block = sub[sub["Pair"] == pair]
        y = np.asarray([positions[name] + offset for name in block["MetricLabel"]], float)
        p = pd.to_numeric(block[pcol], errors="coerce").to_numpy(float)
        sig = p < alpha
        colour = rgba(colours[pair])
        g = block["HedgesG"].to_numpy(float)
        marks.append(Points(
            g, y, fill=[colour if ok else NONE_RGBA for ok in sig], edge=colour,
            edge_width=1.0, size=float(np.sqrt(26)), key=pair,
            hover=[f"{name}, {pair}: g = {v:+.2f}" + (f", q = {q:.3g}" if np.isfinite(q) else "")
                   for name, v, q in zip(block["MetricLabel"], g, p)]))
    panel = Panel(
        marks=marks, yticks=[(v, str(k)) for k, v in positions.items()], tick_size=7,
        xlabel="paired difference between measures (Hedges' g_av)", label_size=9,
        title="How far do the values move when the measure changes?\n"
              f"filled = significant after FDR correction (p < {alpha})", title_size=10,
        zoom=(True, False),
        legend=(Legend([LegendItem(p, rgba(colours[p]), kind="point", key=p) for p in pairs],
                       loc="best", size=7) if len(pairs) > 1 else None))
    return save_chart(Chart([panel], size=(6.4, max(3.0, 0.26 * len(keep) + 1.4))), out_path)


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
    panels, items = [], {}
    for k, (a, b) in enumerate(pairs):
        block = sub[(sub["MeasureA"] == a) & (sub["MeasureB"] == b)]
        limit = float(np.nanmax(np.abs(
            np.concatenate([block["EffectA"], block["EffectB"]])))) or 1.0
        limit *= 1.15
        marks = [Line([-limit, limit], [-limit, limit], MUTED_RGBA, width=1.0, dash="--", z=0),
                 Rule(0, colour=MUTED_RGBA, width=0.6, z=0),
                 Rule(0, axis="x", colour=MUTED_RGBA, width=0.6, z=0)]
        for verdict, part in block.groupby("Verdict"):
            colour = rgba(_VERDICT_COLORS.get(str(verdict), _VERDICT_DEFAULT))
            names = [str(m) for m in part["Metric"]]
            ea, eb = part["EffectA"].to_numpy(float), part["EffectB"].to_numpy(float)
            marks.append(Points(ea, eb, fill=colour, edge=rgba("white"), edge_width=0.4,
                                size=float(np.sqrt(30)), key=str(verdict),
                                hover=[f"{m}: {x:+.2f} under {a}, {y:+.2f} under {b}\n"
                                       f"{verdict}" for m, x, y in zip(names, ea, eb)]))
            items.setdefault(str(verdict), LegendItem(str(verdict), colour, kind="point",
                                                      key=str(verdict)))
        # Name only the points that disagree: labelling all fifty would bury
        # the four that matter.
        off = block[block["Verdict"].str.startswith("disagree")]
        for row in off.itertuples():
            marks.append(Text(row.EffectA, row.EffectB, str(row.Metric), INK_RGBA, size=6,
                              ha="left", va="bottom", offset=(4, 3)))
        panels.append(Panel(cell=(0, k), marks=marks, xlim=(-limit, limit),
                            ylim=(-limit, limit), xlabel=f"effect under {a}",
                            ylabel=f"effect under {b}", label_size=9, equal=True))
    legend = (Legend(list(items.values()), loc="bottom", columns=min(4, len(items)), size=7)
              if items else None)
    chart = Chart(panels, size=(4.2 * n, 4.2), grid=(1, n), legend=legend, title_size=10,
                  title="Would the conclusion have been the same?\n"
                        "group and age effects, measured each way")
    return save_chart(chart, out_path)


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

    colours = [rgba(c) for c in scheme.groups(len(sub))]
    y = np.arange(len(sub), dtype=float)
    errs = pd.to_numeric(sub["SD"], errors="coerce").fillna(0.0).to_numpy(float)
    acc = sub["BalancedAccuracy"].to_numpy(float)
    names = [str(t) for t in sub["ActivityType"]]
    marks = [Bars(y, acc, width=0.6, colour=colours, horizontal=True, key=names,
                  hover=[f"{t}: {v:.3f} ± {e:.3f} ({m})"
                         for t, v, e, m in zip(names, acc, errs, sub["Model"])]),
             # Over the bars, as matplotlib draws them: half of each interval
             # lies inside its bar.
             ErrorBars(acc, y, xerr=errs, colour=MUTED_RGBA, width=1.0, cap=6, z=3)]
    legend = None
    chance = pd.to_numeric(sub["Chance"], errors="coerce").dropna()
    if len(chance):
        marks.append(Rule(float(chance.iloc[0]), axis="x", colour=INK_RGBA, width=1.0,
                          dash="--", z=3))
        legend = Legend([LegendItem("chance", INK_RGBA, dash="--")], loc="lower right",
                        size=7)
    for i, row in enumerate(sub.itertuples()):
        mark = _stars(getattr(row, "PValue", np.nan))
        # Past the error bar, not past the bar: a wide interval would otherwise
        # run straight through the model's name.
        marks.append(Text(float(row.BalancedAccuracy) + float(errs[i]) + 0.015, i,
                          f"{row.Model}{(' ' + mark) if mark else ''}", INK_RGBA, size=7,
                          ha="left"))
    target = _target_label(str(sub["Target"].iloc[0])) if "Target" in sub else "target"
    panel = Panel(
        marks=marks, yticks=[(v, t) for v, t in zip(y, names)], tick_size=8,
        xlabel="balanced accuracy (best model)", label_size=9,
        # Room past 1.0 for the winning model's name, which sits at the bar's
        # end. Without it a measure that decodes perfectly has its label
        # clipped, which is exactly the row a reader looks at first.
        xlim=(0, 1.22), xticks=[(v, f"{v:.1f}") for v in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)],
        title=f"Which measure carries the most information about {target}?", title_size=10,
        zoom=(True, False), legend=legend)
    return save_chart(Chart([panel], size=(5.6, max(2.4, 0.5 * len(sub) + 1.4))), out_path)
