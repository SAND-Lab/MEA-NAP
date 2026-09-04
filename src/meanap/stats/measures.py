"""Does the measure of activity you chose change the answer you got?

A CAT-NAP recording has no single "activity". Detected calcium events, the
deconvolved trace, raw fluorescence and suite2p's spike estimate are four
different readings of the same field of view, and the pipeline builds a
different network from each: events give an STTC coincidence network, the three
continuous traces give a binned Pearson correlation network. Every number
downstream — event rate, density, modularity, small-worldness, and the genotype
effect measured on any of them — is conditional on that choice, and until a run
could analyse several measures at once (``Params.twop_activities``, see
:mod:`meanap.catnap.activities`) the choice was invisible in the output.

This module reads a multi-measure run back and asks three questions of it, in
increasing order of what is at stake:

1. **Do the values agree?** Per metric, per pair of measures: how strongly do
   the recordings rank the same way, how far apart are the values, and is one
   measure systematically higher (:func:`agreement_table`). A metric that
   correlates at rho = 0.95 across measures is measuring one thing; one at
   rho = 0.1 is measuring two.

2. **Do the values differ?** The same recordings measured two ways are paired
   observations, so the difference is tested within recording — a Wilcoxon
   signed-rank test and a paired standardised effect size
   (:func:`difference_table`). This is the question "would my reported mean
   have been different", and for most metrics the answer is yes and large,
   which is *expected* and not by itself a problem.

3. **Does the conclusion differ?** The question that actually matters. The
   run's own group and age comparisons are re-read within each measure and put
   side by side (:func:`effect_table`, :func:`concordance_table`): same sign?
   both significant? And the decoders trained per measure are compared on
   accuracy (:func:`decoding_table`), which says which measure carries more of
   the signal being looked for. A genotype effect that is significant under
   ``peaks`` and absent under ``denoised F`` is a finding about the analysis,
   not about the biology, and it should be visible before publication rather
   than after.

Nothing here recomputes a model. The per-measure comparisons and decoders are
already fitted by :mod:`meanap.stats.run`, once per measure, because each
measure is analysed as a dataset in its own right; this module is handed those
results and lines them up. That keeps the cost of the whole comparison down to
a few correlations, and — more importantly — guarantees the effect it reports
for a measure is the identical number that measure's own ``5A`` table reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd

from meanap.stats.comparisons import SIGNED_EFFECT_SIZES, fdr_correct
from meanap.stats.dataset import StatsDataset

__all__ = [
    "MeasureComparison",
    "agreement_table",
    "compare_measures",
    "concordance_table",
    "decoding_table",
    "difference_table",
    "effect_table",
]

#: Terms from the run's own comparison table that a conclusion can hinge on.
#: The omnibus group test and the age slope are the two headline effects every
#: MEA-NAP run reports; the pairwise genotype contrasts come along because a
#: two-group study reads those and not the omnibus.
_CONCLUSION_FAMILY = "mixed-model"

#: Below this, a metric's two measures are not ranking the recordings alike and
#: anything either of them says about a group difference is a statement about
#: that measure rather than about the network. Chosen as the conventional floor
#: for "good" agreement rather than derived from anything; the number is
#: reported beside every rho so a reader can apply their own.
AGREEMENT_FLOOR = 0.5


@dataclass
class MeasureComparison:
    """Everything the measure comparison produced for one lag."""

    lag: object = None
    #: Measures compared, in the order the run analysed them (primary first).
    activities: list[str] = field(default_factory=list)
    #: Unordered pairs, as ``(A, B)`` with A earlier in *activities* than B.
    pairs: list[tuple[str, str]] = field(default_factory=list)
    agreement: pd.DataFrame = field(default_factory=pd.DataFrame)
    differences: pd.DataFrame = field(default_factory=pd.DataFrame)
    effects: pd.DataFrame = field(default_factory=pd.DataFrame)
    concordance: pd.DataFrame = field(default_factory=pd.DataFrame)
    decoding: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Headline counts, for the log line and ``summary.json``.
    summary: dict = field(default_factory=dict)
    #: Metric display names, so figures drawn from this need no dataset.
    labels: dict = field(default_factory=dict)

    @property
    def ran(self) -> bool:
        return bool(self.pairs) and not self.agreement.empty


# ── the paired frame every table is built from ───────────────────────────────

def _paired(ds: StatsDataset, metric: str) -> pd.DataFrame:
    """``metric`` per recording per measure, one column per measure.

    Recordings are the pairing unit: the same field of view measured two ways
    is one observation seen twice, not two observations. Rows where either
    measure is missing or non-finite are dropped, so every statistic below is
    computed on exactly the recordings both measures could describe — a metric
    that is undefined for a recording under one measure must not contribute a
    half-pair to the comparison.
    """
    cols = [ds.name_col, ds.activity_col, metric]
    frame = ds.table[cols].copy()
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    wide = frame.pivot_table(index=ds.name_col, columns=ds.activity_col,
                             values=metric, aggfunc="first")
    return wide


def _pair_values(wide: pd.DataFrame, a: str, b: str):
    """The finite, matched values of two measures — ``(x, y)`` or two empties."""
    if a not in wide.columns or b not in wide.columns:
        return np.empty(0), np.empty(0)
    both = wide[[a, b]].dropna()
    return both[a].to_numpy(float), both[b].to_numpy(float)


def _pairs_of(activities: list[str]) -> list[tuple[str, str]]:
    return list(combinations(activities, 2))


# ── 1. do the values agree? ──────────────────────────────────────────────────

def _concordance_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Lin's concordance correlation coefficient.

    Preferred over a plain Pearson r as the single agreement number because r
    is blind to exactly the failure worth catching here: two measures can
    correlate at 0.99 while one is three times the other, and r would call that
    perfect agreement. CCC multiplies r by a bias term that only reaches 1 when
    the values also lie on the identity line.
    """
    if len(x) < 3:
        return float("nan")
    vx, vy = x.var(ddof=0), y.var(ddof=0)
    if vx <= 0 or vy <= 0:
        return float("nan")
    cov = float(np.cov(x, y, ddof=0)[0, 1])
    denom = vx + vy + (x.mean() - y.mean()) ** 2
    return float(2 * cov / denom) if denom > 0 else float("nan")


def agreement_table(ds: StatsDataset, metrics: list[str],
                    pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """How closely two measures agree about each metric, over matched recordings.

    Reports both a *ranking* statistic (Spearman rho: do the recordings come out
    in the same order?) and an *agreement* one (CCC, and the Bland-Altman bias
    and limits: are the values actually the same?). They answer different
    questions and a metric can pass one and fail the other — which is the
    common case, since a correlation network and an event network are on
    different scales by construction.
    """
    from scipy import stats as sps

    rows: list[dict] = []
    for metric in metrics:
        wide = _paired(ds, metric)
        for a, b in pairs:
            x, y = _pair_values(wide, a, b)
            row = {"Lag": None, "Metric": metric, "MetricLabel": ds.label(metric),
                   "MeasureA": a, "MeasureB": b, "N": int(len(x))}
            if len(x) < 3 or np.allclose(x, x[0]) or np.allclose(y, y[0]):
                # Two or fewer paired recordings, or a metric that is constant
                # under one measure: every statistic below would be either
                # undefined or a coin flip dressed up as a correlation.
                rows.append({**row, "Spearman": np.nan, "Pearson": np.nan,
                             "CCC": np.nan, "MeanA": float(np.mean(x)) if len(x) else np.nan,
                             "MeanB": float(np.mean(y)) if len(y) else np.nan,
                             "Bias": np.nan, "LoALower": np.nan, "LoAUpper": np.nan,
                             "Note": "too few matched recordings, or constant"})
                continue
            diff = y - x
            sd_diff = float(np.std(diff, ddof=1))
            rows.append({
                **row,
                "Spearman": float(sps.spearmanr(x, y).statistic),
                "Pearson": float(sps.pearsonr(x, y).statistic),
                "CCC": _concordance_correlation(x, y),
                "MeanA": float(np.mean(x)), "MeanB": float(np.mean(y)),
                "SDA": float(np.std(x, ddof=1)), "SDB": float(np.std(y, ddof=1)),
                # Bland-Altman: the mean difference and the interval 95% of
                # differences fall in. Quoted in the metric's own units, since
                # "how far apart" is not a question a correlation answers.
                "Bias": float(np.mean(diff)),
                "LoALower": float(np.mean(diff) - 1.96 * sd_diff),
                "LoAUpper": float(np.mean(diff) + 1.96 * sd_diff),
                "Note": "",
            })
    return pd.DataFrame(rows)


# ── 2. do the values differ? ─────────────────────────────────────────────────

def _paired_hedges_g(x: np.ndarray, y: np.ndarray) -> float:
    """Standardised mean difference for paired data, Cumming's ``g_av``.

    Standardised by the *pooled* SD of the two conditions rather than the SD of
    the differences. The difference-SD version (``g_z``) inflates without limit
    as the two measures correlate, which they do here by construction — the
    same recordings measured twice — so it would report an enormous effect for
    a shift that is small on the metric's own scale. ``g_av`` stays comparable
    to the between-group effect sizes the rest of the step reports.
    """
    n = len(x)
    if n < 2:
        return float("nan")
    sd = np.sqrt((np.var(x, ddof=1) + np.var(y, ddof=1)) / 2.0)
    if not np.isfinite(sd) or sd <= 0:
        return float("nan")
    d = float(np.mean(y - x) / sd)
    # Hedges' small-sample correction, on the paired degrees of freedom.
    j = 1.0 - 3.0 / (4.0 * (n - 1) - 1) if n > 2 else 1.0
    return d * j


def difference_table(ds: StatsDataset, metrics: list[str],
                     pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """Within-recording differences between measures, tested and sized.

    FDR-corrected across metrics *within* each pair of measures: the family of
    tests a reader scans is "which of my metrics moved when I changed measure",
    and correcting across pairs as well would penalise a three-measure run for
    asking the same question three times.
    """
    from scipy import stats as sps

    rows: list[dict] = []
    for metric in metrics:
        wide = _paired(ds, metric)
        for a, b in pairs:
            x, y = _pair_values(wide, a, b)
            diff = y - x
            row = {"Lag": None, "Metric": metric, "MetricLabel": ds.label(metric),
                   "MeasureA": a, "MeasureB": b, "N": int(len(x))}
            if len(x) < 5 or np.allclose(diff, 0):
                rows.append({**row, "Statistic": np.nan, "PValue": np.nan,
                             "HedgesG": np.nan, "MedianDiff": float(np.median(diff))
                             if len(diff) else np.nan, "PercentChange": np.nan,
                             "Note": "too few matched recordings, or identical"})
                continue
            try:
                test = sps.wilcoxon(x, y)
                stat, pval = float(test.statistic), float(test.pvalue)
            except ValueError as exc:  # all-zero differences, or too few
                stat, pval = np.nan, np.nan
                row["Note"] = str(exc)
            median_a = float(np.median(x))
            rows.append({
                **row,
                "Statistic": stat, "PValue": pval,
                "HedgesG": _paired_hedges_g(x, y),
                "MedianDiff": float(np.median(diff)),
                # Relative change is the readable one for rates and counts and
                # meaningless for a metric that crosses zero, so it is left
                # blank there rather than reported as a huge number.
                "PercentChange": (float(np.median(diff) / median_a * 100.0)
                                  if abs(median_a) > 1e-12 else np.nan),
                "Note": row.get("Note", ""),
            })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["PValueFDR"] = np.nan
    for _, idx in table.groupby(["MeasureA", "MeasureB"], dropna=False).groups.items():
        table.loc[idx, "PValueFDR"] = fdr_correct(table.loc[idx, "PValue"])
    return table


# ── 3. does the conclusion differ? ───────────────────────────────────────────

def effect_table(comparisons: dict, metrics: list[str] | None = None) -> pd.DataFrame:
    """Each measure's own group and age effects, stacked into one table.

    *comparisons* is ``{measure: ComparisonResults}`` — the results
    :mod:`meanap.stats.run` already fitted for each measure separately. Only the
    pooled mixed-model family is kept: the per-age cross-sections multiply the
    rows by the number of ages without changing the question being asked here.
    """
    frames = []
    for activity, results in comparisons.items():
        table = getattr(results, "table", None)
        if table is None or table.empty:
            continue
        sub = table[table["Family"] == _CONCLUSION_FAMILY].copy()
        if metrics is not None:
            sub = sub[sub["Metric"].isin(metrics)]
        if sub.empty:
            continue
        sub.insert(0, "ActivityType", activity)
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def concordance_table(effects: pd.DataFrame, pairs: list[tuple[str, str]],
                      *, alpha: float = 0.05) -> pd.DataFrame:
    """Whether two measures reach the same conclusion about each metric.

    One row per (metric, term, pair of measures) carrying both effect sizes,
    both p-values, and a plain-language ``Verdict``:

    ``agree (both significant)``
        The same effect, in the same direction, found under both measures.
        The only verdict that lets a result be quoted without naming the
        measure it came from.
    ``agree (neither significant)``
        Nothing found either way — concordant, but only as an absence.
    ``disagree (only <measure>)``
        Significant under one measure and not the other. Whichever measure was
        reported, the other one would have told a different story.
    ``disagree (opposite signs)``
        Significant under both, pointing opposite ways. The worst case, and the
        one worth checking the raw traces over.

    Significance is read off the FDR-corrected p-value, because that is what the
    ``5A`` tables and figures report; a verdict that disagreed with the figure
    beside it would be worse than no verdict.
    """
    if effects.empty:
        return pd.DataFrame()

    pcol = "PValueFDR" if "PValueFDR" in effects.columns else "PValue"
    rows: list[dict] = []
    keys = ["Metric", "Term"]
    for (metric, term), block in effects.groupby(keys, dropna=False):
        by_measure = block.set_index("ActivityType")
        label = str(block["MetricLabel"].iloc[0]) if "MetricLabel" in block else metric
        for a, b in pairs:
            if a not in by_measure.index or b not in by_measure.index:
                continue
            ra, rb = by_measure.loc[a], by_measure.loc[b]
            # A metric can appear twice under one measure only if the run's own
            # table did, which it does not; guard anyway so a duplicated row
            # cannot turn a Series into a DataFrame and crash the whole step.
            if isinstance(ra, pd.DataFrame):
                ra = ra.iloc[0]
            if isinstance(rb, pd.DataFrame):
                rb = rb.iloc[0]
            ea, eb = _effect_of(ra), _effect_of(rb)
            pa, pb = float(ra.get(pcol, np.nan)), float(rb.get(pcol, np.nan))
            sig_a, sig_b = pa < alpha, pb < alpha
            # Some terms are unsigned by construction — the omnibus group test
            # reports a chi-square, which has no direction. Two measures that
            # both find such an effect agree about it; calling that "opposite
            # signs" because neither had a sign to compare would invent a
            # disagreement out of the test's own arithmetic.
            directional = bool(np.isfinite(ea) and np.isfinite(eb))
            same_sign = bool(np.sign(ea) == np.sign(eb)) if directional else None
            if sig_a and sig_b:
                verdict = ("disagree (opposite signs)" if same_sign is False
                           else "agree (both significant)")
            elif sig_a or sig_b:
                verdict = f"disagree (only {a if sig_a else b})"
            else:
                verdict = "agree (neither significant)"
            rows.append({
                "Lag": ra.get("Lag"), "Metric": metric, "MetricLabel": label,
                "Term": term, "MeasureA": a, "MeasureB": b,
                "EffectA": ea, "EffectB": eb, "PValueA": pa, "PValueB": pb,
                "SignificantA": bool(sig_a), "SignificantB": bool(sig_b),
                "Directional": directional, "SameSign": same_sign,
                "Verdict": verdict,
                "EffectSizeName": ra.get("EffectSizeName", ""),
            })
    return pd.DataFrame(rows)


def _effect_of(row) -> float:
    """A row's signed effect size, or ``nan`` when the term has none.

    Not every row in the comparison table carries a direction. The omnibus group
    test reports a chi-square and the age x group interaction reports a
    degrees-of-freedom count; both are real results, and reading either as an
    effect size would put a metric on the concordance scatter at a position that
    means nothing. ``nan`` is the honest answer, and the verdict logic then
    judges those terms on significance alone.
    """
    if str(row.get("EffectSizeName", "")) not in SIGNED_EFFECT_SIZES:
        return float("nan")
    for key in ("EffectSize", "Estimate"):
        value = row.get(key, np.nan)
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            return value
    return float("nan")


def decoding_table(decoding: dict) -> pd.DataFrame:
    """Best decoding score per measure — which measure carries the signal.

    *decoding* is ``{measure: DecodingResults}``. The best model rather than the
    mean over models: the question is how much the features of this measure can
    be made to say about the target, and averaging in a model that happened to
    suit one measure's feature geometry answers a different one. The winning
    model's name is reported alongside so a reader can see when the measures
    were not won by the same one.
    """
    rows: list[dict] = []
    for activity, results in decoding.items():
        summary = getattr(results, "summary", None)
        table = summary() if callable(summary) else None
        if table is None or table.empty:
            continue
        best = table.sort_values("BalancedAccuracy", ascending=False).iloc[0]
        rows.append({
            "ActivityType": activity,
            "Target": getattr(results, "target", ""),
            "Model": best.get("Model", ""),
            "BalancedAccuracy": float(best.get("BalancedAccuracy", np.nan)),
            "SD": float(best.get("SD", np.nan)),
            "Chance": float(getattr(results, "chance", np.nan)),
            "PValue": float(best.get("PValue", np.nan)),
            "NRecordings": int(getattr(results, "n_samples", 0)),
            "NFeatures": len(getattr(results, "features", []) or []),
        })
    return pd.DataFrame(rows)


# ── putting it together ──────────────────────────────────────────────────────

def compare_measures(
    ds: StatsDataset,
    *,
    comparisons: dict | None = None,
    decoding: dict | None = None,
    metrics: list[str] | None = None,
    lag=None,
    alpha: float = 0.05,
) -> MeasureComparison:
    """Compare every measure of activity in *ds* against every other.

    *ds* holds one lag's rows for all measures. *comparisons* and *decoding*
    are the per-measure results the run already fitted, keyed by measure; both
    are optional, and without them the two value-level tables are still
    produced — which is the whole analysis for a run whose comparisons were
    switched off.

    Returns an empty :class:`MeasureComparison` (``ran`` False) when the run
    used one measure. That is not a failure: it is what every ephys run and
    every ordinary CAT-NAP run looks like, and the caller skips the outputs.
    """
    activities = ds.activities
    result = MeasureComparison(lag=lag, activities=list(activities))
    if len(activities) < 2:
        return result

    names = [m for m in (metrics or ds.metrics) if m in ds.table.columns]
    pairs = _pairs_of(list(activities))
    result.pairs = pairs
    result.labels = {m: ds.label(m) for m in names}

    result.agreement = agreement_table(ds, names, pairs)
    result.differences = difference_table(ds, names, pairs)
    for frame in (result.agreement, result.differences):
        if not frame.empty:
            frame["Lag"] = lag

    result.effects = effect_table(comparisons or {}, names)
    result.concordance = concordance_table(result.effects, pairs, alpha=alpha)
    result.decoding = decoding_table(decoding or {})
    result.summary = _summarise(result, alpha=alpha)
    return result


def _summarise(result: MeasureComparison, *, alpha: float) -> dict:
    """The handful of numbers worth putting in a log line and ``summary.json``."""
    out: dict = {
        "activities": list(result.activities),
        "n_pairs": len(result.pairs),
    }
    agree = result.agreement
    if not agree.empty:
        rho = pd.to_numeric(agree["Spearman"], errors="coerce")
        out["n_metrics"] = int(agree["Metric"].nunique())
        out["median_spearman"] = float(rho.median()) if rho.notna().any() else None
        out["n_poorly_agreeing"] = int((rho.abs() < AGREEMENT_FLOOR).sum())
        weak = agree.loc[rho.abs() < AGREEMENT_FLOOR, "Metric"]
        out["poorly_agreeing_metrics"] = sorted(set(weak.astype(str)))[:20]
    diffs = result.differences
    if not diffs.empty and "PValueFDR" in diffs:
        out["n_metrics_shifted"] = int((diffs["PValueFDR"] < alpha).sum())
        out["n_comparisons"] = int(len(diffs))
    conc = result.concordance
    if not conc.empty:
        counts = conc["Verdict"].value_counts()
        out["verdicts"] = {str(k): int(v) for k, v in counts.items()}
        disagreeing = conc[conc["Verdict"].str.startswith("disagree")]
        out["n_conclusions_disagreeing"] = int(len(disagreeing))
        out["conclusions_disagreeing"] = sorted(
            {f"{r.Metric} ({r.Term})" for r in disagreeing.itertuples()})[:20]
    dec = result.decoding
    if not dec.empty:
        best = dec.sort_values("BalancedAccuracy", ascending=False).iloc[0]
        out["best_decoding_measure"] = str(best["ActivityType"])
        out["best_decoding_accuracy"] = float(best["BalancedAccuracy"])
    return out


def summary_lines(result: MeasureComparison) -> list[str]:
    """The comparison in prose, for the run log.

    Written as sentences rather than a table because this is the part of the
    step a reader most needs to *notice*: a run whose conclusions move with the
    measure should say so where it cannot be scrolled past.
    """
    s = result.summary
    if not result.ran:
        return []
    lines = [f"  measures compared: {', '.join(result.activities)}"]
    if s.get("median_spearman") is not None:
        lines.append(
            f"  metric agreement across measures: median Spearman rho = "
            f"{s['median_spearman']:.2f} over {s.get('n_metrics', 0)} metrics; "
            f"{s.get('n_poorly_agreeing', 0)} comparison(s) below "
            f"rho = {AGREEMENT_FLOOR}")
    if "n_metrics_shifted" in s:
        lines.append(
            f"  values shifted with the measure in {s['n_metrics_shifted']} of "
            f"{s.get('n_comparisons', 0)} metric x measure-pair comparisons "
            "(paired Wilcoxon, FDR-corrected)")
    if "n_conclusions_disagreeing" in s:
        n = s["n_conclusions_disagreeing"]
        total = sum(s.get("verdicts", {}).values())
        lines.append(
            f"  group/age conclusions: {total - n} of {total} agree across "
            f"measures, {n} do not")
        for name in s.get("conclusions_disagreeing", [])[:5]:
            lines.append(f"    disagrees: {name}")
        if n > 5:
            lines.append(f"    …and {n - 5} more (see measure_concordance.csv)")
    if "best_decoding_measure" in s:
        lines.append(
            f"  best decoding: {s['best_decoding_measure']} at "
            f"{s['best_decoding_accuracy']:.2f} balanced accuracy")
    return lines
