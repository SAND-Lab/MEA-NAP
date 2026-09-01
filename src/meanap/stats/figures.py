"""The catalogue of step-5 figures, and how to draw one from stored results.

Three places need to draw these figures: the step itself
(:mod:`meanap.stats.run`), the bundle exporter, and the viewer. Left to
themselves each would carry its own list of which figures exist and how each is
made, and the three lists would drift — the failure mode being a figure the
viewer silently never offers because nobody updated its copy. So the list lives
here once, as :func:`stats_figures`, and everything draws through
:func:`draw_stats_figure`.

**Figures are redrawn from the tables, not from the analyses.** Re-running the
decoders to look at a confusion matrix would take minutes; the CSVs the step
already writes hold everything the figures need, so :func:`load_results` reads
them back and the drawing is fast enough to do on demand. Two of the analyses
are recomputed rather than read — the correlation structure and the discriminant
projection — because both are deterministic, take well under a second, and
would otherwise need their own on-disk formats (a per-group-and-age stack of
matrices, and a set of eigenvalues) for no gain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from meanap.stats.comparisons import ComparisonResults
from meanap.stats.dataset import StatsDataset
from meanap.stats.decoding import DecodingResults
from meanap.stats.regression import RegressionResults

__all__ = [
    "FIGURE_GROUPS",
    "StatsFigure",
    "StatsResults",
    "draw_stats_figure",
    "load_results",
    "stats_figures",
]

#: Presentation order and display names for the four analyses. Also the prefix
#: each family's filenames carry (``5A_``…``5D_``), which is what makes an
#: output folder sort into reading order.
FIGURE_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("comparisons", "Group and age comparisons", "5A"),
    ("correlation", "Feature structure", "5B"),
    ("decoding", "Decoding", "5C"),
    ("regression", "Variance attribution", "5D"),
    ("density", "Topology at matched density", "5E"),
)


@dataclass(frozen=True)
class StatsFigure:
    """One drawable figure: how to name it, address it, and where it lands."""

    #: Stable address, unique within a lag. Used by the viewer as a request key.
    key: str
    label: str
    #: One of :data:`FIGURE_GROUPS`' keys.
    group: str
    #: Filename stem the pipeline writes, without extension.
    filename: str
    #: One sentence saying what the figure shows — the viewer's caption, and
    #: the HTML report's.
    caption: str = ""


@dataclass
class StatsResults:
    """Everything one lag's analyses produced, however it was obtained.

    Either computed fresh by :mod:`meanap.stats.run` or read back from a
    results folder by :func:`load_results`; the figures cannot tell the
    difference, which is the point.
    """

    dataset: StatsDataset
    lag: object = None
    comparisons: ComparisonResults | None = None
    correlation: object = None
    decoding: DecodingResults | None = None
    lda: dict | None = None
    by_age: pd.DataFrame | None = None
    #: Per-age Shapley attribution of decoding performance.
    shapley: object = None
    #: The same, with whole feature families as the players.
    families: object = None
    #: Topology swept across imposed densities, with group/age labels attached.
    sweep: object = None
    #: The family decomposition with topology measured under density and size
    #: control, for comparison against :attr:`families`.
    families_controlled: object = None
    regression: RegressionResults | None = None
    #: How many metrics the trajectory figure draws. Carried on the results
    #: rather than passed to every call, because the figure catalogue has to
    #: know whether that figure exists at all before anyone asks to draw it.
    n_trajectory_metrics: int = 12
    #: Where these came from, for a caption that has to be honest about it.
    source: str = "computed"


# ── the catalogue ────────────────────────────────────────────────────────────
#
# The prose lives here once and is read three ways: by ``stats_figures`` for the
# viewer's labels and captions, by ``report_patterns`` for the HTML report's,
# and by the figures themselves for their titles. A caption written twice is a
# caption that will eventually say two different things.

#: ``key -> (label, caption)`` for every figure with a fixed name.
_PROSE: dict[str, tuple[str, str]] = {
    "trajectories": (
        "Trajectories of the top metrics",
        "Mean ± SEM against age for the metrics with the strongest age or "
        "genotype effects — the data behind the top rows of the effect heatmap.",
    ),
    "correlation": (
        "Feature correlation matrix",
        "Every metric against every other, ordered by hierarchical clustering on "
        "correlation distance so blocks of redundant metrics are adjacent. The "
        "effective dimensionality printed on it is how many independent "
        "measurements the set is worth.",
    ),
    "correlation_by_group_age": (
        "Correlation by group and age",
        "The same matrix computed separately within each group and age, in the "
        "pooled ordering, so a block that tightens or loosens over development "
        "shows as a change in one place.",
    ),
    "dimensionality": (
        "Feature-space dimensionality",
        "Principal-component scree and cumulative curve: how many components it "
        "takes to account for the metric set.",
    ),
    "decoding_performance": (
        "Decoding performance",
        "Held-out balanced accuracy per classifier, one point per fold, against "
        "chance and the 95th centile of a label-permutation null. Whole cultures "
        "are held out, so a culture never appears in both training and test.",
    ),
    "decoding_confusion": (
        "Confusion matrices",
        "Row-normalised confusion per classifier — recall for each true class, "
        "with raw counts in brackets.",
    ),
    "decoding_importance": (
        "Decoding feature importance",
        "Held-out permutation importance: how much balanced accuracy each "
        "classifier loses when one feature is shuffled in the test fold.",
    ),
    "lda": (
        "Discriminant projection",
        "Recordings on their first two discriminant axes. Fitted on all the "
        "data, so the separation shown is optimistic — the held-out number is on "
        "the decoding-performance figure.",
    ),
    "decoding_by_age": (
        "Separability across age",
        "Genotype decoding accuracy computed separately at each age — when in "
        "development the groups become, or stop being, distinguishable.",
    ),
    "shapley_by_age": (
        "What carries the signal, by age",
        "Each feature's Shapley share of how far the decoder gets above chance, "
        "computed separately within every age. A column sums to that age's "
        "decodability, so it is a partition of what was there to be decoded; "
        "negative means the feature cost the decoder accuracy at that age. "
        "Redundant metrics are collapsed to one representative each first, "
        "by a rule that never looks at the labels.",
    ),
    "family_contributions": (
        "Activity vs correlation vs topology",
        "What kind of feature carries the genotype difference at each age: how "
        "much the cells fire, how strongly they are correlated, or how that "
        "correlation is arranged. Each family is one player in the "
        "decomposition, so metrics that duplicate each other inside a family "
        "cost it nothing, and the bars at one age sum to that age's "
        "decodability.",
    ),
    "family_alone_vs_unique": (
        "Does each family carry its own signal?",
        "Per family and age: what it achieves on its own, against what is lost "
        "when it is removed from the full set. A family with a large 'alone' "
        "and a 'unique' at zero adds nothing the others do not already carry — "
        "the test of whether an apparent difference in network organisation is "
        "more than a difference in firing and correlation. Where 'unique' "
        "exceeds 'alone' the families are complementary: that one is worth "
        "more in company than by itself.",
    ),
    "shapley_across_ages": (
        "What carries the signal, across age",
        "The same shares read along the age axis, over the total they "
        "partition. A share falling can mean the feature stopped mattering or "
        "that nothing was decodable at that age; the upper panel separates "
        "those two.",
    ),
    "regression_performance": (
        "Regression performance",
        "Held-out R² per model, one point per fold, with cultures held out whole.",
    ),
    "variance_decomposition": (
        "Variance decomposition",
        "Each feature's share of the explained variance. The bar is its Shapley "
        "value (the shares sum to the model's R²); the open circle is what it "
        "explains alone, and the tick what only it explains. A tall bar with a "
        "floor at zero is a feature working through a measurement it shares with "
        "others.",
    ),
    "sweep_by_group": (
        "Topology vs density, by group",
        "Each topology metric measured on networks thresholded to a common "
        "proportion of edges, from 2% to 40%, one line per group. Curves that "
        "lie on top of each other mean a difference seen at the recordings' own "
        "densities was density, not organisation; curves that stay apart across "
        "the range are a topology difference that survives the control. Binary "
        "at each density, so connection strength is removed too.",
    ),
    "sweep_by_age": (
        "Topology vs density, by age",
        "The same sweep split by age instead of group — how organisation "
        "changes over development once density is held fixed, rather than "
        "moving with it.",
    ),
    "topology_controlled": (
        "Does topology carry its own signal?",
        "The family decomposition run twice: once with network topology as "
        "step 4 measured it, once with topology represented only by metrics "
        "taken at matched connection density and matched node count. Activity "
        "and correlation strength stay uncontrolled in both, since they are "
        "what topology is being tested against. The 'unique' panel is the "
        "answer — if controlling topology does not lift it off zero, topology "
        "is redundant with activity and coupling rather than mismeasured.",
    ),
    "sweep_context": (
        "Reading the density sweep",
        "The densities the recordings actually have, against the range the "
        "sweep imposes, and how much of the network survives each threshold. "
        "Both are needed to read the sweep: differing observed densities are "
        "what makes it necessary, and a largest component well below 1 marks "
        "where path length stops being trustworthy.",
    ),
    "observed_vs_predicted": (
        "Observed vs predicted",
        "Out-of-fold predictions against the truth for the best model, jittered "
        "along the observed axis because ages are a handful of discrete values.",
    ),
}

#: ``key -> filename stem``. Separate from :data:`_PROSE` because the effect
#: heatmaps' stems carry their test family and so are built, not looked up.
#:
#: The digit after the step letter is what makes an output folder, and the HTML
#: report that lists it, read in the order the analysis is meant to be read.
#: Both sort by filename, and alphabetical order would otherwise open the
#: decoding section on the per-age breakdown and the comparisons section on
#: DIV 14 rather than on the model over all of them.
_FILENAMES: dict[str, str] = {
    "trajectories": "5A3_trajectories_top_metrics",
    "correlation": "5B1_feature_correlation",
    "correlation_by_group_age": "5B2_feature_correlation_by_group_age",
    "dimensionality": "5B3_feature_dimensionality",
    "decoding_performance": "5C1_decoding_performance",
    "decoding_confusion": "5C2_decoding_confusion",
    "decoding_importance": "5C3_decoding_feature_importance",
    "lda": "5C4_lda_projection",
    "decoding_by_age": "5C5_decoding_by_age",
    "shapley_by_age": "5C6_genotype_shapley_by_age",
    "shapley_across_ages": "5C7_genotype_shapley_across_ages",
    "family_contributions": "5C8_feature_family_contributions",
    "family_alone_vs_unique": "5C9_feature_family_alone_vs_unique",
    "regression_performance": "5D1_regression_performance",
    "variance_decomposition": "5D2_variance_decomposition",
    "observed_vs_predicted": "5D3_observed_vs_predicted",
    "sweep_by_group": "5E1_density_sweep_by_group",
    "sweep_by_age": "5E2_density_sweep_by_age",
    "sweep_context": "5E3_density_sweep_context",
    "topology_controlled": "5E4_topology_controlled",
}

#: Filename stems for the effect heatmaps: the pooled mixed model first, then
#: one per age.
_EFFECTS_POOLED_STEM = "5A1_effects_mixed-model"
_EFFECTS_PER_AGE_STEM = "5A2_effects_group-at-age-{age}"

#: Which analysis each figure belongs to, for grouping in a UI.
_GROUPS: dict[str, str] = {
    "trajectories": "comparisons",
    "correlation": "correlation",
    "correlation_by_group_age": "correlation",
    "dimensionality": "correlation",
    "decoding_performance": "decoding",
    "decoding_confusion": "decoding",
    "decoding_importance": "decoding",
    "lda": "decoding",
    "decoding_by_age": "decoding",
    "shapley_by_age": "decoding",
    "shapley_across_ages": "decoding",
    "family_contributions": "decoding",
    "family_alone_vs_unique": "decoding",
    "regression_performance": "regression",
    "variance_decomposition": "regression",
    "observed_vs_predicted": "regression",
    "sweep_by_group": "density",
    "sweep_by_age": "density",
    "sweep_context": "density",
    "topology_controlled": "density",
}

_EFFECTS_POOLED = (
    "Effect sizes — age and genotype",
    "Every metric against every term of the mixed model, coloured by effect size "
    "and starred where it survives FDR correction. Rows are ordered by their "
    "largest effect. The model carries a random intercept per culture, because "
    "a culture imaged at several ages contributes several rows.",
)

_EFFECTS_PER_AGE = (
    "Effect sizes — genotype at DIV {age:g}",
    "Genotype contrasts within one age, where each culture contributes a single "
    "recording and no mixed model is needed. Colour is the standardised "
    "difference, stars are FDR-corrected significance.",
)


def _fixed(key: str) -> StatsFigure:
    label, caption = _PROSE[key]
    return StatsFigure(key=key, label=label, group=_GROUPS[key],
                       filename=_FILENAMES[key], caption=caption)


def stats_figures(results: StatsResults) -> list[StatsFigure]:
    """Which figures *these* results can actually produce.

    Derived from the results rather than fixed, because two of the entries
    depend on the run: the effect heatmap exists once per test family (one
    pooled, one per age), and several figures are absent when their analysis
    was switched off or found nothing to draw.
    """
    out: list[StatsFigure] = []

    comp = results.comparisons
    if comp is not None and not comp.table.empty:
        families = [f for f in comp.table["Family"].dropna().unique()
                    if f == "mixed-model" or str(f).startswith("group-at-age")]
        # Pooled model first, then the per-age cross-sections in age order.
        families.sort(key=lambda f: (f != "mixed-model", _age_of(f)))
        for family in families:
            safe = str(family).replace(" ", "-")
            if family == "mixed-model":
                label, caption = _EFFECTS_POOLED
                stem = _EFFECTS_POOLED_STEM
            else:
                label = _EFFECTS_PER_AGE[0].format(age=_age_of(family))
                caption = _EFFECTS_PER_AGE[1]
                stem = _EFFECTS_PER_AGE_STEM.format(age=f"{_age_of(family):g}")
            out.append(StatsFigure(key=f"effects_{safe}", label=label,
                                   group="comparisons",
                                   filename=stem, caption=caption))
        if _trajectory_metrics(results):
            out.append(_fixed("trajectories"))

    if results.correlation is not None:
        out.append(_fixed("correlation"))
        if getattr(results.correlation, "per_cell", None):
            out.append(_fixed("correlation_by_group_age"))
        out.append(_fixed("dimensionality"))

    dec = results.decoding
    if dec is not None and not dec.scores.empty:
        out.append(_fixed("decoding_performance"))
        if dec.confusion:
            out.append(_fixed("decoding_confusion"))
        if not dec.importance.empty:
            out.append(_fixed("decoding_importance"))
    if results.lda:
        out.append(_fixed("lda"))
    if results.by_age is not None and not results.by_age.empty:
        out.append(_fixed("decoding_by_age"))
    shapley = results.shapley
    if shapley is not None and not shapley.table.empty:
        out.append(_fixed("shapley_by_age"))
        # The across-age view needs at least two ages to be a trajectory.
        if shapley.table["DIV"].nunique() > 1:
            out.append(_fixed("shapley_across_ages"))
    families = results.families
    if families is not None and not families.table.empty:
        out.append(_fixed("family_contributions"))
        if families.table["DIV"].nunique() > 1:
            out.append(_fixed("family_alone_vs_unique"))

    sweep = results.sweep
    if sweep is not None and not getattr(sweep, "labelled", pd.DataFrame()).empty:
        out.append(_fixed("sweep_by_group"))
        if sweep.labelled[sweep.age_col].nunique() > 1:
            out.append(_fixed("sweep_by_age"))
        if not sweep.observed.empty:
            out.append(_fixed("sweep_context"))
    if (results.families is not None and results.families_controlled is not None
            and not results.families_controlled.table.empty):
        out.append(_fixed("topology_controlled"))

    reg = results.regression
    if reg is not None and not reg.scores.empty:
        out.append(_fixed("regression_performance"))
        if reg.decomposition is not None and not reg.decomposition.empty:
            out.append(_fixed("variance_decomposition"))
        out.append(_fixed("observed_vs_predicted"))
    return out


def report_patterns() -> list[tuple[str, str, str]]:
    """``(filename regex, title, caption)`` for every figure the step can write.

    For the HTML report, which walks an output folder and has no results object
    to enumerate from — it sees only filenames. The regexes match a stem plus
    any image extension, since the step's ``fig_ext`` is configurable.
    """
    ext = r"\.(?:png|jpe?g|svg|pdf)$"
    out = [
        (rf"^{_EFFECTS_POOLED_STEM}{ext}", *_EFFECTS_POOLED),
        (r"^5A2_effects_group-at-age-(?P<age>[\d.]+)" + ext,
         "Effect sizes — genotype at DIV {age}", _EFFECTS_PER_AGE[1]),
    ]
    for key, stem in _FILENAMES.items():
        label, caption = _PROSE[key]
        out.append((rf"^{stem}{ext}", label, caption))
    return out


def _age_of(family) -> float:
    """The DIV a ``group-at-age-<n>`` family refers to; ``-1`` for the pooled one."""
    text = str(family)
    if not text.startswith("group-at-age-"):
        return -1.0
    try:
        return float(text.rsplit("-", 1)[1])
    except ValueError:
        return -1.0


def _trajectory_metrics(results: StatsResults, limit: int | None = None) -> list[str]:
    """Metrics for the trajectory figure: those with the strongest effects.

    Ranked by each metric's smallest FDR-corrected p-value across the mixed
    model's terms, which is the same ordering the effect heatmap's rows carry.
    """
    comp = results.comparisons
    if comp is None or comp.table.empty:
        return []
    rows = comp.table[(comp.table["Family"] == "mixed-model")
                      & comp.table["PValueFDR"].notna()]
    if rows.empty:
        return []
    ranked = rows.groupby("Metric")["PValueFDR"].min().sort_values().index.tolist()
    keep = limit if limit is not None else results.n_trajectory_metrics
    return [m for m in ranked if m in results.dataset.table.columns][:keep]


# ── drawing ──────────────────────────────────────────────────────────────────

def draw_stats_figure(
    results: StatsResults, key: str, out_path: Path | str, *, scheme=None,
) -> Path | None:
    """Draw one catalogued figure to *out_path*, or return ``None`` if it has no data.

    ``None`` rather than an exception for an empty figure: a metric that is
    all-missing, or an analysis that found nothing to plot, is an ordinary
    outcome and the caller's other figures should still be drawn.
    """
    from meanap.pipeline.palette import DEFAULT_SCHEME
    from meanap.stats import plots

    scheme = scheme or DEFAULT_SCHEME
    out_path = Path(out_path)
    ds = results.dataset

    if key.startswith("effects_"):
        family = key[len("effects_"):]
        # The figure wears the catalogue's own label rather than the test
        # family's internal name: "mixed-model" is what the code calls it, not
        # what a reader needs printed across the top of the plot.
        label = next((f.label for f in stats_figures(results) if f.key == key), None)
        return plots.plot_effect_heatmap(
            results.comparisons.table, out_path, family=family, title=label)
    if key == "trajectories":
        return plots.plot_metric_trajectories(
            ds, _trajectory_metrics(results), out_path, scheme=scheme,
            title="Metrics with the strongest age or group effects")
    if key == "correlation":
        return plots.plot_correlation_matrix(
            results.correlation, out_path, labeller=ds.label)
    if key == "correlation_by_group_age":
        return plots.plot_correlation_grid(
            results.correlation, out_path, labeller=ds.label)
    if key == "dimensionality":
        return plots.plot_pca_variance(results.correlation, out_path)
    if key == "decoding_performance":
        return plots.plot_decoding_scores(results.decoding, out_path)
    if key == "decoding_confusion":
        return plots.plot_confusion(results.decoding, out_path)
    if key == "decoding_importance":
        return plots.plot_decoding_importance(results.decoding, out_path)
    if key == "lda":
        return plots.plot_lda_projection(results.lda, out_path, scheme=scheme)
    if key == "decoding_by_age":
        return plots.plot_decoding_by_age(results.by_age, out_path, scheme=scheme)
    if key == "shapley_by_age":
        return plots.plot_shapley_by_age(results.shapley, out_path)
    if key == "shapley_across_ages":
        return plots.plot_shapley_across_ages(results.shapley, out_path)
    if key == "family_contributions":
        return plots.plot_family_contributions(results.families, out_path)
    if key == "family_alone_vs_unique":
        return plots.plot_family_alone_vs_unique(results.families, out_path)
    if key == "regression_performance":
        return plots.plot_regression_scores(results.regression, out_path)
    if key == "variance_decomposition":
        return plots.plot_variance_decomposition(results.regression, out_path)
    if key == "observed_vs_predicted":
        return plots.plot_observed_vs_predicted(
            results.regression, out_path, scheme=scheme)
    if key == "topology_controlled":
        return plots.plot_topology_controlled(
            results.families, results.families_controlled, out_path)
    if key in ("sweep_by_group", "sweep_by_age", "sweep_context"):
        sweep = results.sweep
        if key == "sweep_context":
            return plots.plot_density_context(
                sweep.observed, sweep.labelled, out_path,
                densities=sweep.densities, group_col=sweep.group_col,
                age_col=sweep.age_col, scheme=scheme)
        by_group = key == "sweep_by_group"
        column = sweep.group_col if by_group else sweep.age_col
        levels = (list(pd.unique(sweep.labelled[column].dropna())) if by_group
                  else sorted(pd.unique(sweep.labelled[column].dropna())))
        colours = dict(zip(
            levels,
            scheme.groups(len(levels)) if by_group else scheme.ages(len(levels))))
        return plots.plot_density_sweep(
            sweep.labelled, out_path, split=column, metrics=sweep.metrics,
            colours=colours,
            title=("Topology at matched density, by group" if by_group
                   else "Topology at matched density, by age"))
    raise ValueError(
        f"Unknown statistics figure {key!r}; expected one of "
        f"{[f.key for f in stats_figures(results)]}")


# ── reading results back ─────────────────────────────────────────────────────

def _read(folder: Path, name: str) -> pd.DataFrame | None:
    path = folder / name
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    return frame if not frame.empty else None


def load_results(folder: Path | str, dataset: StatsDataset, *, lag=None,
                 correlation_method: str = "spearman") -> StatsResults:
    """Rebuild a lag's :class:`StatsResults` from the CSVs the step wrote.

    *dataset* is the run's own metric table, which the figures that draw raw
    data (the trajectories) need and which the two recomputed analyses are
    derived from. A missing CSV simply leaves that analysis out, and
    :func:`stats_figures` then does not offer its figures — a results folder
    written with ``--only decoding`` yields a decoding-only catalogue.
    """
    folder = Path(folder)
    results = StatsResults(dataset=dataset, lag=lag, source="stored")

    comparisons = _read(folder, "comparisons.csv")
    if comparisons is not None:
        results.comparisons = ComparisonResults(table=comparisons)

    # Recomputed rather than read: deterministic, sub-second, and the only
    # alternative is inventing an on-disk format for a stack of matrices.
    if (folder / "feature_correlation.csv").exists():
        from meanap.stats.correlation import analyse_correlation

        results.correlation = analyse_correlation(
            dataset, method=correlation_method, lag=lag)

    scores = _read(folder, "decoding_scores.csv")
    if scores is not None:
        results.decoding = _load_decoding(folder, scores, dataset, lag)
    if (folder / "lda_projection.csv").exists():
        from meanap.stats.decoding import lda_projection

        results.lda = lda_projection(dataset) or None
    results.by_age = _read(folder, "decoding_by_age.csv")
    results.shapley = _load_shapley(folder)
    results.families = _load_families(folder)
    results.sweep = _load_sweep(folder, dataset)

    reg_scores = _read(folder, "regression_scores.csv")
    if reg_scores is not None:
        results.regression = _load_regression(folder, reg_scores, dataset, lag)
    return results


def _load_shapley(folder: Path):
    """Rebuild the per-age Shapley attribution from its two tables.

    Read rather than recomputed — unlike the correlation structure and the
    discriminant projection, this one costs a minute or two, which is well past
    what a viewer can do while someone waits for a figure.
    """
    from meanap.stats.decoding import ShapleyDecoding

    table = _read(folder, "genotype_shapley_by_age.csv")
    if table is None:
        return None
    totals = _read(folder, "genotype_shapley_totals.csv")
    clusters = _read(folder, "genotype_shapley_feature_clusters.csv")
    return ShapleyDecoding(
        table=table,
        totals=totals if totals is not None else pd.DataFrame(),
        clusters=clusters if clusters is not None else pd.DataFrame(),
        features=list(pd.unique(table["Feature"])),
    )


def _load_sweep(folder: Path, ds: StatsDataset):
    """Rebuild the density sweep from its CSVs.

    Read, never recomputed: the sweep is minutes of work over the adjacency
    matrices, which a results folder does not necessarily sit beside.
    """
    from meanap.stats.density_sweep import (
        SWEEP_METRICS, DensitySweep, attach_labels, cost_integrate,
    )

    curves = _read(folder, "density_sweep_curves.csv")
    if curves is None:
        return None
    observed = _read(folder, "density_sweep_observed.csv")
    integrated = _read(folder, "density_sweep_integrated.csv")
    metrics = tuple(m for m in SWEEP_METRICS if m in curves.columns)
    sweep = DensitySweep(
        curves=curves,
        integrated=integrated if integrated is not None
        else cost_integrate(curves, metrics=metrics),
        densities=tuple(sorted(curves["Density"].unique())),
        metrics=metrics,
        observed=observed if observed is not None else pd.DataFrame(),
        group_col=ds.group_col, age_col=ds.age_col,
    )
    sweep.labelled = attach_labels(curves, ds)
    if observed is not None and ds.group_col not in observed.columns:
        sweep.observed = attach_labels(observed, ds)
    return sweep


def _load_families(folder: Path, name: str = "feature_family_contributions.csv"):
    """Rebuild a per-family attribution from its tables."""
    from meanap.stats.decoding import FamilyShapley

    table = _read(folder, name)
    if table is None:
        return None
    totals = _read(folder, "feature_family_totals.csv")
    membership = _read(folder, "feature_family_membership.csv")
    # Presentation order comes from the file, which the step wrote in the
    # canonical order; a set would lose it and reshuffle every figure.
    families = list(dict.fromkeys(table["Family"]))
    return FamilyShapley(
        table=table,
        totals=totals if totals is not None else pd.DataFrame(),
        membership=membership if membership is not None else pd.DataFrame(),
        families=families,
    )


def _load_decoding(folder: Path, scores: pd.DataFrame, ds: StatsDataset,
                   lag) -> DecodingResults:
    from sklearn.metrics import confusion_matrix

    predictions = _read(folder, "decoding_predictions.csv")
    importance = _read(folder, "decoding_feature_importance.csv")
    null = _read(folder, "decoding_permutation_null.csv")
    summary = _read(folder, "decoding_summary.csv")

    classes: list[str] = []
    confusion: dict = {}
    if predictions is not None:
        classes = sorted(set(predictions["True"].astype(str)))
        for model in predictions["Model"].unique():
            sub = predictions[predictions["Model"] == model]
            mat = confusion_matrix(sub["True"].astype(str),
                                   sub["Predicted"].astype(str), labels=classes)
            confusion[str(model)] = pd.DataFrame(mat, index=classes, columns=classes)

    chance = float(summary["Chance"].iloc[0]) if (
        summary is not None and "Chance" in summary.columns) else (
        1.0 / len(classes) if classes else float("nan"))
    # The target is not written as a column of its own; it is whichever
    # identifying column the predicted labels came from.
    target = ds.group_col
    if classes and set(classes) <= {str(a) for a in ds.ages}:
        target = ds.age_col

    return DecodingResults(
        scores=scores,
        predictions=predictions if predictions is not None else pd.DataFrame(),
        confusion=confusion,
        importance=importance if importance is not None else pd.DataFrame(),
        null=null if null is not None else pd.DataFrame(),
        features=list(ds.metrics), target=target, classes=classes, chance=chance,
        # Per *recording*, not per row: the predictions table stacks one block
        # per model, so its length is the recording count times the number of
        # models and would put the wrong n on every figure title.
        n_samples=int(predictions[ds.name_col].nunique())
        if predictions is not None and ds.name_col in predictions.columns else 0,
        n_groups=int(predictions[ds.culture_col].nunique())
        if predictions is not None and ds.culture_col in predictions.columns else 0,
        lag=lag,
    )


def _load_regression(folder: Path, scores: pd.DataFrame, ds: StatsDataset,
                     lag) -> RegressionResults:
    predictions = _read(folder, "regression_predictions.csv")
    importance = _read(folder, "regression_feature_importance.csv")
    decomposition = _read(folder, "variance_decomposition.csv")
    coefficients = _read(folder, "regression_coefficients.csv")

    # The full model's R² is not stored separately because the Shapley column
    # already sums to it exactly — that identity is the decomposition's
    # defining property, and re-deriving it here is a cheap check on the file.
    r2_full = float(decomposition["Shapley"].sum()) if decomposition is not None \
        else float("nan")
    features = list(decomposition["Feature"]) if decomposition is not None else []
    target = ds.age_col
    if coefficients is not None and "Feature" in coefficients.columns:
        named = set(coefficients["Feature"])
        missing = [m for m in ds.metrics if m not in named and m in ds.table.columns]
        # A metric excluded from its own predictors is the regression target.
        if len(missing) == 1:
            target = missing[0]

    return RegressionResults(
        scores=scores,
        predictions=predictions if predictions is not None else pd.DataFrame(),
        importance=importance if importance is not None else pd.DataFrame(),
        decomposition=decomposition if decomposition is not None else pd.DataFrame(),
        coefficients=coefficients if coefficients is not None else pd.DataFrame(),
        target=target, features=features, r2_full=r2_full,
        n_samples=int(predictions[ds.name_col].nunique())
        if predictions is not None and ds.name_col in predictions.columns else 0,
        n_groups=int(predictions[ds.culture_col].nunique())
        if predictions is not None and ds.culture_col in predictions.columns else 0,
        lag=lag,
    )


def available_lags(stats_root: Path | str) -> list[str]:
    """Lag folder names inside a ``5_StatsAndML`` directory, in the run's order."""
    root = Path(stats_root)
    if not root.is_dir():
        return []
    names = [p.name for p in root.iterdir()
             if p.is_dir() and any(p.glob("*.csv"))]
    return sorted(names, key=_lag_sort_key)


def _lag_sort_key(name: str):
    digits = "".join(ch for ch in name if ch.isdigit())
    return (0, int(digits)) if digits else (1, 0)
