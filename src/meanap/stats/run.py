"""Running the whole step and writing ``5_StatsAndML/``.

The equivalent of the block at the end of ``MEApipeline.m`` that calls
``doStats``, ``featureCorrelation``, ``doLDA`` and ``doClassification`` in turn.

Everything is written twice over: once as a CSV, because the tables are the
result and someone will want them in a paper or a different plotting tool, and
once as a figure. Both go under one folder per lag, since every metric in a run
is computed per lag and mixing lags would mix several measurements of the same
recording.

Each of the four analyses is guarded. They are independent questions, and one
that fails — a mixed model that will not converge for any metric, a decoder
given a single genotype — should cost its own outputs and nothing else, the way
:mod:`meanap.pipeline.export` guards each figure family.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from meanap.pipeline.palette import DEFAULT_SCHEME, ColorScheme
from meanap.stats.comparisons import compare_metrics
from meanap.stats.correlation import analyse_correlation
from meanap.stats.dataset import StatsDataset, load_dataset
from meanap.stats.decoding import (
    decode, decode_per_age, decoding_shapley, family_of, family_shapley,
    lda_projection,
)
from meanap.stats.density_sweep import (
    COST_INT_SUFFIX, DEFAULT_DENSITIES, attach_labels, retention,
    run_density_sweep,
)
from meanap.stats.figures import StatsResults, draw_stats_figure, stats_figures
from meanap.stats.regression import regress

__all__ = ["StatsRunResult", "StatsSettings", "run_stats", "OUTPUT_DIRNAME"]

#: The folder written beside the pipeline's other numbered step folders.
OUTPUT_DIRNAME = "5_StatsAndML"


@dataclass
class StatsSettings:
    """What to run and how hard.

    The defaults are sized for a run of a few hundred recordings finishing in
    around a minute per lag. ``n_permutations`` is the one worth raising: at
    200 the smallest p-value the null can report is 1/201, which is a floor, not
    a measurement.
    """

    comparisons: bool = True
    correlation: bool = True
    decoding: bool = True
    regression: bool = True
    #: Re-measure topology on networks thresholded to a common density, across
    #: a range. Off by default: it is a robustness analysis rather than a
    #: headline one, it needs the per-recording adjacency matrices rather than
    #: the metric tables, and it is by far the slowest thing here — the work is
    #: multiplied by both the density grid and ``sweep_subsamples``, so on 378
    #: recordings across 16 cores it was ~15 minutes without subsampling and
    #: ~25 minutes with it.
    density_sweep: bool = False

    #: Restrict to these metrics; empty means every metric the run computed.
    metrics: tuple[str, ...] = ()
    #: Continuous target for the regression. Defaults to age.
    regression_target: str | None = None
    #: Classification target. ``None`` picks genotype, or age when a run has
    #: only one genotype — the rule ``doClassification`` uses.
    decoding_target: str | None = None

    correlation_method: str = "spearman"
    redundancy_threshold: float = 0.9

    models: tuple[str, ...] = ("logistic", "lda", "linearSVM", "rbfSVM",
                               "randomForest", "kNN")
    regression_models: tuple[str, ...] = ("ridge", "elasticNet", "randomForest",
                                          "gradientBoosting")
    n_splits: int = 5
    n_repeats: int = 5
    n_permutations: int = 200
    importance_repeats: int = 10
    n_orderings: int = 200
    per_age_decoding: bool = True

    #: Attribute the *decoding* of genotype across features, within each age,
    #: and report how those shares move with age. Off for a run with one age or
    #: one group, where neither question exists.
    shapley_by_age: bool = True
    #: Redundant metrics are collapsed to this many representatives before the
    #: decomposition. The cost is roughly linear in it and in
    #: ``shapley_orderings``; the default pair takes a minute or two on a
    #: five-age run.
    shapley_max_features: int = 15
    shapley_orderings: int = 100
    #: Also decompose decoding across whole *families* of features — activity,
    #: correlation strength, network topology — with each family as one player.
    #: Cheap next to the per-feature version: three families means eight
    #: subsets per age, so the Shapley values are exact rather than sampled.
    feature_families: bool = True
    #: Classifier the decomposition scores subsets with. Shrinkage LDA because
    #: it is fast, needs no tuning, and stays defined for a one-feature subset
    #: and for a subset wider than the ~40-90 recordings one age holds.
    shapley_model: str = "lda"

    #: Densities the sweep imposes. The default is Schroeter et al. (2015)'s
    #: grid, 2% to 40% in 2% steps.
    sweep_densities: tuple[float, ...] = DEFAULT_DENSITIES
    #: Consensus-Louvain repeats per density. Step 4 uses 50; the sweep pays it
    #: once per density and the curve smooths across them, so it defaults lower.
    sweep_modularity_reps: int = 20
    #: Reduce every network to this many randomly drawn nodes before
    #: thresholding, so size is controlled as well as density. ``"auto"`` picks
    #: a low percentile of the run's own node counts (see
    #: ``sweep_node_percentile``); ``None`` leaves size uncontrolled, which on
    #: real data is the larger of the two confounds. Recordings with fewer
    #: nodes are dropped — check the retention line in the log, because they
    #: are not a random sample.
    sweep_n_nodes: int | str | None = "auto"
    #: Percentile of observed node counts ``"auto"`` targets. Low on purpose:
    #: a higher target resolves topology better but drops more recordings, and
    #: it drops them unevenly across groups.
    sweep_node_percentile: float = 10.0
    #: Random draws averaged over per recording when subsampling.
    sweep_subsamples: int = 20

    seed: int = 0
    fig_ext: str = ".png"
    #: Trajectory figures are drawn for this many of the most strongly changing
    #: metrics; drawing all 50 makes a figure nobody reads.
    n_trajectory_metrics: int = 12


@dataclass
class StatsRunResult:
    """What the step produced, and what it could not."""

    dest: Path
    tables: list[Path] = field(default_factory=list)
    figures: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _write_table(frame: pd.DataFrame, path: Path, result: StatsRunResult) -> None:
    if frame is None or len(frame) == 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    result.tables.append(path)


def _note(result: StatsRunResult, figure: Path | None) -> None:
    if figure is not None:
        result.figures.append(Path(figure))


def run_stats(
    source: Path | str,
    *,
    dest: Path | str | None = None,
    settings: StatsSettings | None = None,
    scheme: ColorScheme | None = None,
    log=print,
    progress=None,
) -> StatsRunResult:
    """Run every enabled analysis over a run and write the results folder.

    *source* is an output folder or a ``.meanap`` bundle. *dest* defaults to
    ``<source>/5_StatsAndML`` for a folder, and to a sibling folder of that name
    for a bundle, since a bundle's own contents are read-only.
    """
    settings = settings or StatsSettings()
    scheme = scheme or DEFAULT_SCHEME
    source = Path(source)

    ds = load_dataset(source)
    if settings.metrics:
        ds = ds.with_metrics(list(settings.metrics))

    dest = Path(dest) if dest is not None else _default_dest(source)
    dest.mkdir(parents=True, exist_ok=True)
    result = StatsRunResult(dest=dest)

    # Four of the five analyses read the metric CSVs, which ``load_dataset``
    # has already pulled into memory. The density sweep reads the
    # per-recording adjacency matrices instead, so for a bundle it needs the
    # extraction kept alive rather than closed the moment the tables are out.
    sweep_bundle = None
    sweep_root = Path(source)
    if settings.density_sweep and not sweep_root.is_dir():
        from meanap.pipeline.bundle import open_bundle

        sweep_bundle = open_bundle(source)
        sweep_root = Path(sweep_bundle.root)

    design = ds.describe()
    result.summary["design"] = design
    log(f"{design['n_recordings']} recordings from {design['n_cultures']} cultures, "
        f"{design['n_metrics']} metrics, groups {design['groups']}, "
        f"ages {design['ages']}")
    if design["n_cultures"] == design["n_recordings"]:
        log("Note: every recording maps to its own culture — either the run is "
            "cross-sectional, or the recording names do not encode the culture "
            "in a way this can read. Repeated-measures handling is inert.")

    lags = ds.lags or [None]
    for lag in lags:
        sub = ds.for_lag(lag) if lag is not None else ds
        folder = dest / (_lag_dirname(lag) if lag is not None else "all")
        folder.mkdir(parents=True, exist_ok=True)
        log(f"— {folder.name}: {len(sub.table)} recordings")

        # The analyses fill this in; the figures are drawn from it afterwards,
        # through the same catalogue the exporter and the viewer draw through
        # (meanap.stats.figures). Drawing here instead would give this module
        # its own private list of which figures exist, and three lists that
        # must agree is two too many.
        computed = StatsResults(dataset=sub, lag=lag,
                                n_trajectory_metrics=settings.n_trajectory_metrics)
        for name, fn in (
            ("comparisons", _run_comparisons),
            ("correlation", _run_correlation),
            ("decoding", _run_decoding),
            ("regression", _run_regression),
            ("density_sweep", _run_density_sweep),
        ):
            if not getattr(settings, name):
                continue
            try:
                fn(sub, folder, settings, result, lag, log, progress, computed,
                   sweep_root)
            except Exception as exc:  # one analysis failing must not stop the rest
                result.skipped.append(f"{folder.name}/{name}: {exc}")
                log(f"  ! {name} failed: {exc}")
                log(traceback.format_exc(limit=3))

        _draw_all(computed, folder, settings, scheme, result, log)

    if sweep_bundle is not None:
        sweep_bundle.close()

    _write_summary(dest, result, settings)
    log(f"Wrote {len(result.tables)} table(s) and {len(result.figures)} figure(s) "
        f"to {dest}")
    return result


def _run_density_sweep(ds: StatsDataset, folder: Path, settings,
                       result, lag, log, progress, computed,
                       source_root: Path) -> None:
    """Topology re-measured at matched density — the confound control.

    Unlike the other four this reads the per-recording adjacency matrices, not
    the metric tables, so it needs the run's ``ExperimentMatFiles``. It also
    ignores *lag* subsetting and sweeps every lag at once, because the matrices
    are stored per recording with all lags in one file and opening each file
    once per lag would be the dominant cost on a multi-lag run.
    """
    log("  density sweep: topology at matched connection density")
    n_nodes = _resolve_target_nodes(source_root, settings, log)
    sweep = run_density_sweep(
        source_root, densities=settings.sweep_densities,
        modularity_reps=settings.sweep_modularity_reps,
        n_nodes=n_nodes, n_subsamples=settings.sweep_subsamples,
        seed=settings.seed, log=log, progress=progress)
    if sweep.curves.empty:
        result.skipped.append(f"{folder.name}/density_sweep: nothing swept")
        return

    sweep.labelled = attach_labels(sweep.curves, ds)
    sweep.observed = attach_labels(sweep.observed, ds)
    sweep.group_col, sweep.age_col = ds.group_col, ds.age_col
    # This lag's rows only, so the figures match the folder they land in.
    if lag is not None and "Lag" in sweep.labelled.columns:
        sweep.labelled = sweep.labelled[sweep.labelled["Lag"] == lag]
        sweep.observed = sweep.observed[sweep.observed["Lag"] == lag]
    computed.sweep = sweep

    kept = retention(sweep.observed, ds.group_col)
    _write_table(kept, folder / "density_sweep_retention.csv", result)
    _write_table(sweep.curves, folder / "density_sweep_curves.csv", result)
    _write_table(sweep.integrated, folder / "density_sweep_integrated.csv", result)
    _write_table(sweep.observed, folder / "density_sweep_observed.csv", result)

    fragmented = sweep.labelled.groupby("Density")["lccFraction"].mean()
    intact = fragmented[fragmented >= 0.95]
    result.summary.setdefault("density_sweep", {})[str(lag)] = {
        "n_recordings": int(sweep.curves["FileName"].nunique()),
        "densities": [float(d) for d in sweep.densities],
        "observed_density_median": float(sweep.observed["ObservedDensity"].median())
        if not sweep.observed.empty else None,
        # Below this the networks fragment and path length stops being
        # comparable — the number to quote when reading the curves.
        "density_where_network_intact": float(intact.index.min())
        if len(intact) else None,
        "n_skipped": len(sweep.skipped),
        "n_nodes": sweep.n_nodes,
        "n_subsamples": sweep.n_subsamples,
        # Not a footnote: uneven retention means the size confound was traded
        # for a selection one, and the comparison needs reading accordingly.
        "retention": (kept.set_index("Group")["Fraction"].round(3).to_dict()
                      if not kept.empty else None),
    }
    log(f"    swept {sweep.curves['FileName'].nunique()} recordings; observed "
        f"density median {sweep.observed['ObservedDensity'].median():.2f}"
        + (f", network intact from {intact.index.min():.0%}" if len(intact)
           else ", fragmented at every density"))
    _controlled_families(ds, sweep, folder, settings, result, lag, log, computed)

    if sweep.n_nodes is not None and not kept.empty:
        log(f"    subsampled to {sweep.n_nodes} nodes x{sweep.n_subsamples} draws; "
            "kept " + ", ".join(f"{r.Group} {r.Fraction:.0%}"
                                for r in kept.itertuples()))
        if kept["Fraction"].max() - kept["Fraction"].min() > 0.2:
            log("    ! retention differs by more than 20 points between groups — "
                "the size confound has been traded for a selection one")


def _controlled_families(ds: StatsDataset, sweep, folder: Path, settings,
                         result, lag, log, computed) -> None:
    """The family decomposition again, with topology measured under control.

    The question the sweep exists to answer is not just "do the curves
    separate" but "does topology carry anything about genotype once it is
    measured at matched density and size". That is the family decomposition
    with the topology family swapped for the cost-integrated sweep features —
    activity and correlation strength stay *raw*, because they are the
    confounders being tested against and controlling them away would defeat
    the comparison.

    Runs only when the family analysis ran too, since the point is the
    comparison against it.
    """
    if not settings.feature_families or computed.families is None:
        return
    if sweep.integrated is None or sweep.integrated.empty:
        return

    integrated = sweep.integrated.copy()
    if "Lag" in integrated.columns:
        integrated["Lag"] = integrated["Lag"].map(
            lambda k: k[len("adjM"):] if str(k).startswith("adjM") else k)
    controlled_cols = [c for c in integrated.columns
                       if c.endswith(COST_INT_SUFFIX)
                       and not c.startswith("lccFraction")]
    if not controlled_cols:
        return

    join_on = ["FileName", "Lag"] if "Lag" in ds.table.columns else ["FileName"]
    merged = ds.table.merge(integrated[join_on + controlled_cols], on=join_on,
                            how="inner")
    if len(merged) < 20:
        result.skipped.append(
            f"{folder.name}/controlled_families: only {len(merged)} recordings "
            "survive the sweep")
        return

    # Everything that is not topology, kept exactly as measured.
    others = [m for m in ds.metrics if family_of(m) in ("activity", "coupling")]
    subset = ds._with_table(merged).with_metrics(others + controlled_cols)
    fams = family_shapley(subset, target=settings.decoding_target,
                          n_splits=settings.n_splits,
                          model=settings.shapley_model, seed=settings.seed,
                          lag=lag)
    if fams.table.empty:
        return

    computed.families_controlled = fams
    _write_table(fams.table,
                 folder / "feature_family_contributions_controlled.csv", result)

    raw = computed.families.table
    raw_topo = raw[raw["Family"] == "topology"]["Unique"].mean()
    new_topo = fams.table[fams.table["Family"] == "topology"]["Unique"].mean()
    result.summary.setdefault("feature_families_controlled", {})[str(lag)] = {
        "n_recordings": int(len(merged)),
        "n_topology_features": len(controlled_cols),
        "topology_unique_raw": float(raw_topo),
        "topology_unique_controlled": float(new_topo),
        "mean_shapley": fams.table.groupby("FamilyLabel")["Shapley"].mean()
        .round(4).to_dict(),
    }
    log(f"    topology under control: unique contribution "
        f"{new_topo:+.3f} (raw topology was {raw_topo:+.3f}) "
        f"over {len(merged)} recordings")


def _resolve_target_nodes(source_root: Path, settings, log) -> int | None:
    """The common node count to subsample to, resolving ``"auto"``.

    ``"auto"`` reads the run's own node counts and takes a low percentile, so
    the target adapts to the dataset rather than being a number carried over
    from another one. Reading them means opening every adjacency file, which is
    cheap next to the sweep itself and avoids guessing.
    """
    target = settings.sweep_n_nodes
    if target is None:
        return None
    if isinstance(target, (int, np.integer)):
        return int(target) if int(target) > 0 else None
    if target != "auto":
        raise ValueError(
            f"sweep_n_nodes must be an int, None, or 'auto', not {target!r}")

    from meanap.stats.density_sweep import _adjacency_files, _clean, _matrices

    counts = []
    for _name, path in _adjacency_files(source_root):
        try:
            for raw in _matrices(Path(path)).values():
                w = _clean(raw)
                counts.append(int((w.sum(axis=1) > 0).sum()))
        except Exception:  # noqa: BLE001 - a bad file costs its own count
            continue
    if not counts:
        return None
    chosen = int(np.percentile(counts, settings.sweep_node_percentile))
    # Below this the metrics are measuring almost nothing; better to leave size
    # uncontrolled and say so than to compare 6-node graphs.
    if chosen < 15:
        log(f"    ! p{settings.sweep_node_percentile:g} of node counts is only "
            f"{chosen}; too small to subsample to, leaving size uncontrolled")
        return None
    log(f"    subsample target: {chosen} nodes "
        f"(p{settings.sweep_node_percentile:g} of {len(counts)} networks)")
    return chosen


def _draw_all(computed: StatsResults, folder: Path, settings, scheme,
              result: StatsRunResult, log) -> None:
    """Draw every figure the results support, guarded one at a time."""
    for figure in stats_figures(computed):
        path = folder / f"{figure.filename}{settings.fig_ext}"
        try:
            drawn = draw_stats_figure(computed, figure.key, path, scheme=scheme)
        except Exception as exc:  # a figure that cannot be drawn costs only itself
            result.skipped.append(f"{folder.name}/{figure.key}: {exc}")
            log(f"  ! figure {figure.key} failed: {exc}")
            continue
        _note(result, drawn)


def _default_dest(source: Path) -> Path:
    if source.is_dir():
        return source / OUTPUT_DIRNAME
    # A bundle: put the results beside it, named after it, so two bundles
    # analysed in one folder do not overwrite each other.
    return source.parent / f"{source.stem}_{OUTPUT_DIRNAME}"


def _lag_dirname(lag) -> str:
    return str(lag).replace("/", "-").replace(" ", "")


# ── the four analyses ────────────────────────────────────────────────────────

def _run_comparisons(ds: StatsDataset, folder: Path, settings,
                     result, lag, log, progress, computed,
                     source_root: Path) -> None:
    log("  comparisons: mixed models, per-age contrasts, paired age contrasts")
    res = compare_metrics(ds)
    computed.comparisons = res
    _write_table(res.table, folder / "comparisons.csv", result)

    significant = res.significant()
    _write_table(significant, folder / "comparisons_significant.csv", result)
    result.summary.setdefault("comparisons", {})[str(lag)] = {
        "n_tests": int(len(res.table)),
        "n_significant_fdr": int(len(significant)),
    }
    log(f"    {len(significant)} of {len(res.table)} tests significant at FDR q < 0.05")


def _run_correlation(ds: StatsDataset, folder: Path, settings,
                     result, lag, log, progress, computed,
                     source_root: Path) -> None:
    log("  correlation: feature structure and dimensionality")
    res = analyse_correlation(
        ds, method=settings.correlation_method,
        redundancy_threshold=settings.redundancy_threshold, lag=lag)
    computed.correlation = res

    _write_table(res.overall.reset_index().rename(columns={"index": "Feature"}),
                 folder / "feature_correlation.csv", result)
    _write_table(res.redundant, folder / "redundant_features.csv", result)
    _write_table(res.variance_explained, folder / "pca_variance.csv", result)
    _write_table(res.loadings.reset_index().rename(columns={"index": "Feature"}),
                 folder / "pca_loadings.csv", result)
    result.summary.setdefault("correlation", {})[str(lag)] = {
        "n_features": int(len(res.order)),
        "effective_dimensionality": float(res.effective_dim),
        "n_redundant_pairs": int(len(res.redundant)),
    }
    log(f"    {len(res.order)} metrics, effective dimensionality "
        f"{res.effective_dim:.1f}, {len(res.redundant)} redundant pairs "
        f"(|r| >= {settings.redundancy_threshold})")


def _run_decoding(ds: StatsDataset, folder: Path, settings,
                  result, lag, log, progress, computed,
                  source_root: Path) -> None:
    log("  decoding: culture-grouped cross-validation and label-permutation null")
    res = decode(
        ds, target=settings.decoding_target, models=settings.models,
        n_splits=settings.n_splits, n_repeats=settings.n_repeats,
        n_permutations=settings.n_permutations,
        importance_repeats=settings.importance_repeats, seed=settings.seed,
        lag=lag, progress=progress)

    if res.scores.empty:
        result.skipped.append(f"{folder.name}/decoding: not enough data to decode")
        log("    skipped: not enough data (one class, or too few cultures)")
        return

    computed.decoding = res
    _write_table(res.scores, folder / "decoding_scores.csv", result)
    _write_table(res.summary(), folder / "decoding_summary.csv", result)
    _write_table(res.predictions, folder / "decoding_predictions.csv", result)
    _write_table(res.importance, folder / "decoding_feature_importance.csv", result)
    _write_table(res.null, folder / "decoding_permutation_null.csv", result)

    best = res.summary().iloc[0]
    result.summary.setdefault("decoding", {})[str(lag)] = {
        "target": res.target, "chance": res.chance,
        "best_model": str(best["Model"]),
        "best_balanced_accuracy": float(best["BalancedAccuracy"]),
        "p_value": float(best["PValue"]) if "PValue" in best else None,
        "n_recordings": res.n_samples, "n_cultures": res.n_groups,
    }
    log(f"    best: {best['Model']} at {best['BalancedAccuracy']:.3f} balanced "
        f"accuracy (chance {res.chance:.3f})")

    proj = lda_projection(ds, target=settings.decoding_target)
    if proj:
        computed.lda = proj
        _write_table(proj["coords"], folder / "lda_projection.csv", result)
        _write_table(proj["loadings"].reset_index().rename(
            columns={"index": "Feature"}), folder / "lda_loadings.csv", result)

    if settings.per_age_decoding and len(ds.ages) > 1 and len(ds.groups) > 1:
        per_age = decode_per_age(
            ds, models=("logistic", "lda"), n_splits=settings.n_splits,
            n_repeats=settings.n_repeats, n_permutations=0,
            importance_repeats=0, seed=settings.seed)
        if per_age:
            rows = []
            for age, sub_res in per_age.items():
                frame = sub_res.summary()
                frame.insert(0, "DIV", age)
                rows.append(frame)
            computed.by_age = pd.concat(rows, ignore_index=True)
            _write_table(computed.by_age, folder / "decoding_by_age.csv", result)

    if (settings.shapley_by_age and len(ds.ages) > 1 and len(ds.groups) > 1):
        log("    attributing decoding across features, within each age")
        shapley = decoding_shapley(
            ds, target=settings.decoding_target,
            max_features=settings.shapley_max_features,
            n_orderings=settings.shapley_orderings,
            n_splits=settings.n_splits, model=settings.shapley_model,
            seed=settings.seed, lag=lag, progress=progress)
        if not shapley.table.empty:
            computed.shapley = shapley
            _write_table(shapley.table, folder / "genotype_shapley_by_age.csv",
                         result)
            _write_table(shapley.totals, folder / "genotype_shapley_totals.csv",
                         result)
            _write_table(shapley.clusters,
                         folder / "genotype_shapley_feature_clusters.csv", result)
            best = shapley.totals.loc[shapley.totals["Total"].idxmax()]
            leader = (shapley.table.groupby("FeatureLabel")["Shapley"].mean()
                      .sort_values(ascending=False))
            result.summary.setdefault("shapley_by_age", {})[str(lag)] = {
                "n_features": len(shapley.features),
                "most_decodable_age": float(best["DIV"]),
                "most_decodable_total": float(best["Total"]),
                "top_feature": str(leader.index[0]) if len(leader) else None,
                "top_feature_mean_share": float(leader.iloc[0]) if len(leader) else None,
            }
            log(f"      most decodable at DIV {best['DIV']:g} "
                f"({best['Total']:.2f} above chance); largest mean share: "
                f"{leader.index[0] if len(leader) else 'n/a'}")

    if (settings.feature_families and len(ds.ages) > 1 and len(ds.groups) > 1):
        log("    splitting that across activity / correlation / topology")
        fams = family_shapley(
            ds, target=settings.decoding_target, n_splits=settings.n_splits,
            model=settings.shapley_model, seed=settings.seed, lag=lag,
            progress=progress)
        if not fams.table.empty:
            computed.families = fams
            _write_table(fams.table,
                         folder / "feature_family_contributions.csv", result)
            _write_table(fams.totals, folder / "feature_family_totals.csv", result)
            _write_table(fams.membership,
                         folder / "feature_family_membership.csv", result)
            mean_share = (fams.table.groupby("FamilyLabel")["Shapley"].mean()
                          .sort_values(ascending=False))
            # The finding this analysis exists for: a family whose unique
            # contribution is ~0 is carrying nothing of its own.
            unique = fams.table.groupby("FamilyLabel")["Unique"].mean()
            result.summary.setdefault("feature_families", {})[str(lag)] = {
                "mean_shapley": {k: float(v) for k, v in mean_share.items()},
                "mean_unique": {k: float(v) for k, v in unique.items()},
                "n_features": fams.table.groupby("FamilyLabel")["NFeatures"]
                .first().to_dict(),
            }
            log("      mean share — " + ", ".join(
                f"{k}: {v:+.3f} (unique {unique[k]:+.3f})"
                for k, v in mean_share.items()))


def _run_regression(ds: StatsDataset, folder: Path, settings,
                    result, lag, log, progress, computed,
                    source_root: Path) -> None:
    target = settings.regression_target or ds.age_col
    log(f"  regression: predicting {target} and partitioning its variance")
    res = regress(
        ds, target=target, models=settings.regression_models,
        n_splits=settings.n_splits, n_repeats=settings.n_repeats,
        n_orderings=settings.n_orderings,
        importance_repeats=settings.importance_repeats, seed=settings.seed,
        lag=lag, progress=progress)

    if res.scores.empty:
        result.skipped.append(f"{folder.name}/regression: not enough data")
        log("    skipped: not enough data to regress")
        return

    computed.regression = res
    _write_table(res.scores, folder / "regression_scores.csv", result)
    _write_table(res.summary(), folder / "regression_summary.csv", result)
    _write_table(res.predictions, folder / "regression_predictions.csv", result)
    _write_table(res.importance, folder / "regression_feature_importance.csv", result)
    _write_table(res.decomposition, folder / "variance_decomposition.csv", result)
    _write_table(res.coefficients, folder / "regression_coefficients.csv", result)

    best = res.summary().iloc[0]
    top = res.decomposition.iloc[0] if len(res.decomposition) else None
    result.summary.setdefault("regression", {})[str(lag)] = {
        "target": res.target,
        "best_model": str(best["Model"]), "best_r2": float(best["R2"]),
        "r2_full_linear": float(res.r2_full),
        "top_feature": str(top["Feature"]) if top is not None else None,
        "top_feature_share": float(top["ShapleyShare"]) if top is not None else None,
    }
    log(f"    best: {best['Model']} at R2 = {best['R2']:.3f}; largest share of "
        f"variance: {top['FeatureLabel'] if top is not None else 'n/a'} "
        f"({top['ShapleyShare'] * 100:.0f}%)" if top is not None else "")


def _write_summary(dest: Path, result: StatsRunResult, settings: StatsSettings) -> None:
    """A machine-readable digest of the run, for the GUI and for later reading."""
    payload = {
        "settings": {k: (list(v) if isinstance(v, tuple) else v)
                     for k, v in vars(settings).items()},
        "results": result.summary,
        "tables": [str(p.relative_to(dest)) for p in result.tables],
        "figures": [str(p.relative_to(dest)) for p in result.figures],
        "skipped": result.skipped,
    }
    with open(dest / "stats_summary.json", "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
