"""``meanap-stats`` — run the statistics and machine-learning step from a shell.

The step reads a finished run, so it is useful on its own: a run analysed
months ago, or one someone sent as a bundle, can be put through it without
re-running the pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meanap.stats.run import StatsSettings, run_stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meanap-stats",
        description="Statistical comparison, feature structure, decoding and "
                    "variance attribution for a finished MEA-NAP / CAT-NAP run.")
    parser.add_argument("source", type=Path,
                        help="Run output folder or .meanap bundle")
    parser.add_argument("-o", "--out", type=Path, default=None,
                        help="Where to write the results "
                             "(default: <source>/5_StatsAndML)")

    which = parser.add_argument_group("which analyses")
    which.add_argument("--only", nargs="+", default=None,
                       choices=["comparisons", "correlation", "decoding", "regression"],
                       help="Run only these (default: all four)")
    which.add_argument("--metrics", nargs="+", default=None,
                       help="Restrict to these metric columns")
    which.add_argument("--density-sweep", action="store_true",
                       help="Also re-measure topology on networks thresholded "
                            "to a common density (2-40%%) and subsampled to a "
                            "common node count, to separate organisation from "
                            "connection density and network size. Needs the "
                            "run's ExperimentMatFiles. Slow: tens of minutes "
                            "on a few hundred recordings, since it is "
                            "multiplied by both the density grid and "
                            "--sweep-subsamples.")

    targets = parser.add_argument_group("targets")
    targets.add_argument("--decode", dest="decoding_target", default=None,
                         help="Column to classify (default: genotype, or age "
                              "when the run has one genotype)")
    targets.add_argument("--regress", dest="regression_target", default=None,
                         help="Continuous column to predict (default: age). "
                              "Naming a metric asks what explains that metric.")

    effort = parser.add_argument_group("effort")
    effort.add_argument("--splits", type=int, default=5, help="Cross-validation folds")
    effort.add_argument("--repeats", type=int, default=5,
                        help="Times the cross-validation is repeated")
    effort.add_argument("--permutations", type=int, default=200,
                        help="Label permutations for the decoding null (0 to skip)")
    effort.add_argument("--orderings", type=int, default=200,
                        help="Random orderings for the Shapley variance decomposition")
    effort.add_argument("--shapley-orderings", type=int, default=100,
                        help="Random orderings for the per-age decoding "
                             "attribution (0 to skip it)")
    effort.add_argument("--sweep-nodes", default="auto",
                        help="Common node count the density sweep subsamples "
                             "every network to, so size is controlled as well "
                             "as density. 'auto' picks a low percentile of the "
                             "run's own counts; 0 leaves size uncontrolled. "
                             "Give two counts ('22,50') to sweep at both and "
                             "split the difference into a selection and a "
                             "resolution term — that doubles the sweep's "
                             "cost. The selection half alone is free and is "
                             "always reported.")
    effort.add_argument("--sweep-subsamples", type=int, default=20,
                        help="Random node draws averaged per recording")
    effort.add_argument("--sweep-density-only", action="store_true",
                        help="Also sweep with subsampling off, so the density "
                             "control and the size control can be told apart "
                             "in control_effects.csv and on 5E7. Costs a "
                             "second sweep; without it a change under control "
                             "cannot be attributed to subsampling.")
    effort.add_argument("--shapley-features", type=int, default=15,
                        help="How many representative metrics the per-age "
                             "decoding attribution runs over")
    effort.add_argument("--seed", type=int, default=0)
    effort.add_argument("--quick", action="store_true",
                        help="Small numbers everywhere, for a first look")

    style = parser.add_argument_group("output")
    style.add_argument("--corr-method", default="spearman",
                       choices=["spearman", "pearson", "kendall"])
    style.add_argument("--fig-ext", default=".png")
    return parser


def _sweep_nodes(value):
    """``--sweep-nodes`` as ``(target, second target or None)``.

    The target is ``"auto"``, an int, or ``None`` for uncontrolled. A comma
    gives a second, larger target, which turns the sweep into the three-
    condition design that separates selection from resolution; the smaller of
    the two is always the one the ordinary outputs are measured at.
    """
    if value is None or str(value).lower() in ("auto", ""):
        return "auto", None

    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if len(parts) > 2:
        raise SystemExit("--sweep-nodes takes at most two node counts")

    def one(text):
        if text.lower() == "auto":
            return "auto"
        try:
            count = int(text)
        except (TypeError, ValueError):
            raise SystemExit("--sweep-nodes must be 'auto', 0, or a node count, "
                             f"not {text!r}") from None
        return count if count > 0 else None

    if len(parts) == 1:
        return one(parts[0]), None

    low, high = one(parts[0]), one(parts[1])
    if not isinstance(high, int):
        raise SystemExit("the second --sweep-nodes count must be a node count")
    if isinstance(low, int) and low >= high:
        # Order is the whole point: C is the low target read over the high
        # target's cohort, so a reversed pair would decompose nothing.
        low, high = high, low
        if low == high:
            raise SystemExit("--sweep-nodes needs two different node counts")
    return low, high


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    enabled = set(args.only) if args.only else {
        "comparisons", "correlation", "decoding", "regression"}
    settings = StatsSettings(
        comparisons="comparisons" in enabled,
        correlation="correlation" in enabled,
        decoding="decoding" in enabled,
        regression="regression" in enabled,
        density_sweep=args.density_sweep,
        sweep_n_nodes=_sweep_nodes(args.sweep_nodes)[0],
        sweep_n_nodes_high=_sweep_nodes(args.sweep_nodes)[1],
        sweep_subsamples=args.sweep_subsamples,
        sweep_density_only=args.sweep_density_only,
        metrics=tuple(args.metrics or ()),
        decoding_target=args.decoding_target,
        regression_target=args.regression_target,
        correlation_method=args.corr_method,
        n_splits=args.splits, n_repeats=args.repeats,
        n_permutations=args.permutations, n_orderings=args.orderings,
        shapley_by_age=args.shapley_orderings > 0,
        shapley_orderings=max(1, args.shapley_orderings),
        shapley_max_features=args.shapley_features,
        seed=args.seed, fig_ext=args.fig_ext,
    )
    if args.quick:
        settings.n_repeats = 1
        settings.n_permutations = 0
        settings.n_orderings = 40
        settings.importance_repeats = 3
        settings.per_age_decoding = False
        settings.shapley_orderings = 20
        settings.shapley_max_features = 10

    try:
        result = run_stats(args.source, dest=args.out, settings=settings)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.skipped:
        print("\nSkipped:")
        for item in result.skipped:
            print(f"  - {item}")
    print(f"\nResults in {result.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
