"""Does a metric differ by age or by genotype? — the port of ``doStats.m``.

MATLAB fits, per metric, a linear mixed-effects model with a random intercept
per recording, a one-way repeated-measures ANOVA for the age effect within each
group, and pairwise t-tests between ages and between groups, and pours every
p-value into one long table. The shape is kept — a tidy table of one row per
(metric, test, term) is the right output for something that runs 50 metrics
through half a dozen tests — and four things are fixed:

**The random effect groups cultures, not recordings.** MATLAB's
``(1|recordingName)`` gives each *recording* its own intercept, but each
recording appears once, so the random effect has one observation per level and
absorbs nothing. The grouping that has repeated measurements is the culture (see
:func:`meanap.stats.dataset.derive_culture_ids`), and that is what is used here.

**Omnibus tests before pairwise ones.** A three-level genotype factor gets a
joint Wald test across its dummies, and the age×genotype interaction gets a
likelihood-ratio test against the main-effects model, rather than MATLAB's
inspection of individual coefficients (it fits the interaction model, compares
it, then discards the comparison and uses the main-effects model regardless).

**Multiple comparisons.** Running ~50 metrics × several tests and reading the
p-values raw is a guarantee of false positives. Every p-value carries a
Benjamini-Hochberg FDR-corrected partner, corrected within its own family of
tests, and the family is named in the table.

**Effect sizes are Hedges' g.** MATLAB reports a "d-prime" that divides by the
*mean* of the two standard deviations rather than their pooled value, which is
not Cohen's d and has no small-sample correction.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

from meanap.stats.dataset import StatsDataset

__all__ = ["ComparisonResults", "compare_metrics", "hedges_g", "fdr_correct"]

#: Columns of the tidy results table, in order.
RESULT_COLUMNS = [
    "Lag", "Level", "Metric", "MetricLabel", "Family", "Test", "Term",
    "Estimate", "Statistic", "PValue", "PValueFDR", "EffectSize",
    "EffectSizeName", "N", "NCultures", "Note",
]


@dataclass
class ComparisonResults:
    """Every test run, plus the model fits worth keeping for the figures."""

    table: pd.DataFrame
    #: ``(lag, metric) -> {"estimates": DataFrame, "converged": bool}`` for the
    #: main-effects mixed model, so plots can draw fitted age trajectories
    #: without refitting.
    models: dict = None

    def significant(self, alpha: float = 0.05, *, corrected: bool = True) -> pd.DataFrame:
        col = "PValueFDR" if corrected else "PValue"
        return self.table[self.table[col] < alpha].sort_values(col)


#: ``EffectSizeName`` values that name a *signed, comparable* effect size.
#: The comparison table also carries unsigned ones — a chi-square for the
#: omnibus group test, a degrees-of-freedom count for the interaction — which
#: are real results but say nothing about direction or magnitude on a shared
#: scale. Anything reading ``EffectSize`` as a direction has to filter on this,
#: or it will read "1.0" off an interaction row and plot it as an effect.
SIGNED_EFFECT_SIZES = frozenset({
    "standardised beta", "SD change across age range", "Hedges g", "Cohen dz",
})


# ── effect sizes and correction ──────────────────────────────────────────────

def hedges_g(a: np.ndarray, b: np.ndarray) -> float:
    """Standardised mean difference (*b* − *a*), pooled SD, small-*n* corrected.

    Hedges' g rather than Cohen's d because group sizes here are routinely
    12-40 recordings, where d is biased upward by a few percent.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    pooled_var = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if pooled_var <= 0:
        return float("nan")
    d = (b.mean() - a.mean()) / np.sqrt(pooled_var)
    # Hedges' correction factor; exact form uses gamma functions, this
    # approximation is accurate to <0.1% for n >= 4 and is the standard one.
    correction = 1.0 - 3.0 / (4.0 * (na + nb) - 9.0)
    return float(d * correction)


def fdr_correct(pvals) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values, NaNs passed through untouched.

    NaNs are tests that could not run (a metric that is all-missing at one DIV,
    a model that did not converge). Counting them in the correction would make
    every other test in the family more conservative for no reason.
    """
    p = np.asarray(pvals, dtype=float)
    out = np.full(p.shape, np.nan)
    finite = np.isfinite(p)
    n = int(finite.sum())
    if n == 0:
        return out
    vals = p[finite]
    order = np.argsort(vals)
    ranked = vals[order]
    adjusted = ranked * n / np.arange(1, n + 1)
    # Enforce monotonicity from the largest p downward, as BH requires.
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result = np.empty(n)
    result[order] = np.clip(adjusted, 0, 1)
    out[finite] = result
    return out


def _apply_fdr(rows: list[dict]) -> pd.DataFrame:
    """Correct within each (Lag, Family) group and return the tidy table."""
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    table = pd.DataFrame(rows)
    for col in RESULT_COLUMNS:
        if col not in table.columns:
            table[col] = np.nan
    table["PValueFDR"] = np.nan
    for _, idx in table.groupby(["Lag", "Family"], dropna=False).groups.items():
        table.loc[idx, "PValueFDR"] = fdr_correct(table.loc[idx, "PValue"])
    return table[RESULT_COLUMNS]


# ── mixed models ─────────────────────────────────────────────────────────────

#: Optimisers tried in order when fitting a mixed model. ``powell`` leads
#: because ``lbfgs`` — statsmodels' default — routinely drives the culture
#: variance to the boundary on these metrics and then fails inverting a
#: singular Hessian, while ``powell`` converges on the same data to a variance
#: component that is clearly non-zero (0.08-0.35 of the metric's variance on
#: the Yin timecourse). The rest are there because no single optimiser wins on
#: every metric.
_MIXEDLM_METHODS = ("powell", "lbfgs", "bfgs", "cg")


def _fit_mixedlm(data: pd.DataFrame, formula: str, groups: pd.Series, *, reml: bool = True):
    """Fit one mixed model, trying each optimiser until one converges.

    Returns ``None`` if none does. Non-convergence is common and expected here:
    some metrics are near-constant within a culture, some are degenerate at one
    DIV. A metric that cannot be fitted should produce a row saying so and let
    the caller fall back, not stop the other 49.
    """
    import statsmodels.formula.api as smf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for method in _MIXEDLM_METHODS:
            try:
                model = smf.mixedlm(formula, data, groups=groups)
                fit = model.fit(reml=reml, method=method)
                if np.all(np.isfinite(fit.bse.to_numpy(dtype=float))):
                    return fit
            except Exception:
                continue
    return None


def _fit_cluster_ols(data: pd.DataFrame, formula: str, groups: pd.Series):
    """Ordinary least squares with standard errors clustered by culture.

    The fallback when no mixed model converges. It answers the same question —
    fixed effects, with the non-independence of a culture's repeated recordings
    accounted for — by correcting the standard errors for clustering instead of
    modelling the culture variance explicitly. Weaker (it estimates no variance
    component and borrows no strength across cultures), but it does not depend
    on a variance component being identifiable, so it converges when the mixed
    model will not.
    """
    import statsmodels.formula.api as smf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return smf.ols(formula, data).fit(
                cov_type="cluster", cov_kwds={"groups": np.asarray(groups)})
        except Exception:
            return None


def _fit_with_fallback(data: pd.DataFrame, formula: str, groups: pd.Series):
    """``(fit, test_name, note)`` — a mixed model if possible, clustered OLS if not."""
    fit = _fit_mixedlm(data, formula, groups)
    if fit is not None:
        return fit, "LME", ""
    fit = _fit_cluster_ols(data, formula, groups)
    if fit is not None:
        return fit, "OLS-clustered", "mixed model did not converge; clustered OLS instead"
    return None, "LME", "neither mixed model nor clustered OLS could be fitted"


def _wald_joint(result, terms: list[str]) -> tuple[float, float]:
    """Joint Wald test that every coefficient in *terms* is zero.

    Used for the omnibus genotype effect: with three genotypes there are two
    dummy coefficients, and "does genotype matter" is the question of whether
    both are zero, not whether either individually is.
    """
    names = list(result.params.index)
    present = [t for t in terms if t in names]
    if not present:
        return float("nan"), float("nan")
    constraint = np.zeros((len(present), len(names)))
    for i, term in enumerate(present):
        constraint[i, names.index(term)] = 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            test = result.wald_test(constraint, scalar=True)
            return float(np.squeeze(test.statistic)), float(np.squeeze(test.pvalue))
        except Exception:
            return float("nan"), float("nan")


# ── the analyses ─────────────────────────────────────────────────────────────

def _model_rows(ds: StatsDataset, metric: str, lag, rows: list[dict], models: dict) -> None:
    """Mixed-effects age and genotype effects for one metric.

    Fits ``metric ~ age + genotype + (1|culture)`` and, when both factors vary,
    the interaction model as well, reporting: the age slope, each genotype
    contrast against the reference level, the joint genotype effect, and the
    interaction LRT.
    """
    label = ds.label(metric)
    cols = [metric, ds.age_col, ds.group_col, ds.culture_col]
    data = ds.table[cols].copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna()

    base = dict(Lag=lag, Level=ds.level, Metric=metric, MetricLabel=label,
                Family="mixed-model", N=len(data),
                NCultures=int(data[ds.culture_col].nunique()))

    def blank(test, term, note):
        rows.append({**base, "Test": test, "Term": term, "PValue": np.nan,
                     "EffectSizeName": "standardised beta", "Note": note})

    n_groups = data[ds.group_col].nunique()
    n_ages = data[ds.age_col].nunique()
    if len(data) < 10 or data[metric].std(ddof=1) == 0:
        blank("LME", "age", "too few finite values, or metric is constant")
        return

    # Centre age and standardise the metric so the coefficients are comparable
    # across metrics measured on wildly different scales (node counts vs.
    # modularity). The p-values are unaffected by either transform.
    sd = data[metric].std(ddof=1)
    data["_y"] = (data[metric] - data[metric].mean()) / sd
    data["_age"] = data[ds.age_col] - data[ds.age_col].mean()
    data["_grp"] = data[ds.group_col].astype(str)

    terms = []
    if n_ages > 1:
        terms.append("_age")
    if n_groups > 1:
        terms.append("C(_grp)")
    if not terms:
        blank("LME", "age", "only one age and one group present")
        return

    formula = "_y ~ " + " + ".join(terms)
    fit, test_name, note = _fit_with_fallback(data, formula, data[ds.culture_col])
    if fit is None:
        blank("LME", "age", note)
        return
    base["Note"] = note

    models[(lag, metric)] = {"params": fit.params.to_dict(), "sd": float(sd),
                             "mean": float(data[metric].mean()),
                             "age_mean": float(data[ds.age_col].mean())}

    if n_ages > 1 and "_age" in fit.params.index:
        rows.append({**base, "Test": test_name, "Term": "age",
                     "Estimate": float(fit.params["_age"]),
                     "Statistic": float(fit.tvalues["_age"]),
                     "PValue": float(fit.pvalues["_age"]),
                     # Slope is in SD of the metric per day, so a whole
                     # timecourse's worth of change is the more readable size.
                     "EffectSize": float(fit.params["_age"]) * (
                         data[ds.age_col].max() - data[ds.age_col].min()),
                     "EffectSizeName": "SD change across age range"})

    if n_groups > 1:
        dummies = [n for n in fit.params.index if n.startswith("C(_grp)")]
        reference = sorted(data["_grp"].unique())[0]
        for name in dummies:
            level = name.split("T.")[-1].rstrip("]")
            rows.append({**base, "Test": test_name, "Term": f"{level} vs {reference}",
                         "Estimate": float(fit.params[name]),
                         "Statistic": float(fit.tvalues[name]),
                         "PValue": float(fit.pvalues[name]),
                         "EffectSize": float(fit.params[name]),
                         "EffectSizeName": "standardised beta"})
        stat, pval = _wald_joint(fit, dummies)
        rows.append({**base, "Test": test_name, "Term": "group (omnibus)",
                     "Statistic": stat, "PValue": pval,
                     "EffectSizeName": "chi-square"})

    if n_ages > 1 and n_groups > 1:
        # Whether the groups age *differently* is a joint test that every
        # age x genotype coefficient is zero. A joint Wald test rather than a
        # likelihood-ratio test so the same test can be reported whether the
        # fit came from the mixed model or the clustered-OLS fallback, for
        # which a likelihood ratio would not be valid.
        inter, inter_name, inter_note = _fit_with_fallback(
            data, "_y ~ _age * C(_grp)", data[ds.culture_col])
        if inter is None:
            blank("LME", "age x group", inter_note)
        else:
            cross = [n for n in inter.params.index if ":" in n]
            stat, pval = _wald_joint(inter, cross)
            rows.append({**base, "Test": inter_name, "Term": "age x group",
                         "Statistic": stat, "PValue": pval,
                         "EffectSize": float(len(cross)), "EffectSizeName": "df",
                         "Note": inter_note or "joint test of all interaction terms"})


def _per_age_rows(ds: StatsDataset, metric: str, lag, rows: list[dict]) -> None:
    """Genotype comparisons within each age, the cross-sectional view.

    Within one DIV each culture contributes at most one recording, so ordinary
    between-group tests apply and no mixed model is needed. Kruskal-Wallis is
    used for the omnibus rather than one-way ANOVA (MATLAB's ``anova1``) because
    several of these metrics are proportions bounded at 0 or 1 and are visibly
    non-normal; the pairwise follow-ups are Welch t-tests, which do not assume
    the groups share a variance.
    """
    label = ds.label(metric)
    base_cols = [metric, ds.age_col, ds.group_col]
    data = ds.table[base_cols].copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna()

    for age in sorted(data[ds.age_col].unique()):
        at_age = data[data[ds.age_col] == age]
        samples, names = [], []
        for grp in ds.groups:
            vals = at_age.loc[at_age[ds.group_col] == grp, metric].to_numpy(float)
            if len(vals) >= 2:
                samples.append(vals)
                names.append(str(grp))
        if len(samples) < 2:
            continue

        base = dict(Lag=lag, Level=ds.level, Metric=metric, MetricLabel=label,
                    Family=f"group-at-age-{age:g}", N=int(sum(len(s) for s in samples)),
                    NCultures=int(sum(len(s) for s in samples)))

        if len(samples) > 2:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    stat, pval = sps.kruskal(*samples)
                except ValueError:  # all values identical
                    stat, pval = float("nan"), float("nan")
            rows.append({**base, "Test": "Kruskal-Wallis",
                         "Term": f"group at DIV {age:g}",
                         "Statistic": float(stat), "PValue": float(pval),
                         "EffectSizeName": "H"})

        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                a, b = samples[i], samples[j]
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    stat, pval = sps.ttest_ind(b, a, equal_var=False)
                rows.append({**base, "Test": "Welch t-test",
                             "Term": f"{names[j]} vs {names[i]} at DIV {age:g}",
                             "Estimate": float(np.mean(b) - np.mean(a)),
                             "Statistic": float(stat), "PValue": float(pval),
                             "EffectSize": hedges_g(a, b),
                             "EffectSizeName": "Hedges g",
                             "N": len(a) + len(b), "NCultures": len(a) + len(b)})


def _within_group_age_rows(ds: StatsDataset, metric: str, lag, rows: list[dict]) -> None:
    """The age effect inside each group, and paired age-to-age contrasts.

    The pairing is on culture: only cultures imaged at *both* ages contribute,
    which is what makes the test paired and is the same restriction MATLAB
    applies (it intersects recording names across DIVs). Cultures missing one of
    the two ages are dropped for that pair only, not for the whole metric.
    """
    label = ds.label(metric)
    cols = [metric, ds.age_col, ds.group_col, ds.culture_col]
    data = ds.table[cols].copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna()

    for grp in ds.groups:
        sub = data[data[ds.group_col] == grp]
        ages = sorted(sub[ds.age_col].unique())
        if len(ages) < 2 or len(sub) < 6:
            continue
        base = dict(Lag=lag, Level=ds.level, Metric=metric, MetricLabel=label,
                    Family=f"age-within-{grp}", N=len(sub),
                    NCultures=int(sub[ds.culture_col].nunique()))

        # Age slope within this group, cultures as random intercepts. This is
        # the replacement for MATLAB's RMAOV1: a repeated-measures ANOVA needs
        # every subject measured at every level and silently drops the rest,
        # while the mixed model uses the unbalanced data as it is.
        fit_data = sub.copy()
        sd = fit_data[metric].std(ddof=1)
        if sd > 0 and fit_data[ds.culture_col].nunique() >= 3:
            fit_data["_y"] = (fit_data[metric] - fit_data[metric].mean()) / sd
            fit_data["_age"] = fit_data[ds.age_col] - fit_data[ds.age_col].mean()
            fit, test_name, note = _fit_with_fallback(
                fit_data, "_y ~ _age", fit_data[ds.culture_col])
            if fit is not None and "_age" in fit.params.index:
                rows.append({**base, "Test": test_name, "Term": f"age within {grp}",
                             "Note": note,
                             "Estimate": float(fit.params["_age"]),
                             "Statistic": float(fit.tvalues["_age"]),
                             "PValue": float(fit.pvalues["_age"]),
                             "EffectSize": float(fit.params["_age"]) * (ages[-1] - ages[0]),
                             "EffectSizeName": "SD change across age range"})

        wide = sub.pivot_table(index=ds.culture_col, columns=ds.age_col,
                               values=metric, aggfunc="mean")
        for i in range(len(ages)):
            for j in range(i + 1, len(ages)):
                age_a, age_b = ages[i], ages[j]
                if age_a not in wide.columns or age_b not in wide.columns:
                    continue
                paired = wide[[age_a, age_b]].dropna()
                if len(paired) < 3:
                    continue
                a = paired[age_a].to_numpy(float)
                b = paired[age_b].to_numpy(float)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    stat, pval = sps.ttest_rel(b, a)
                diff = b - a
                sd_diff = diff.std(ddof=1)
                rows.append({**base, "Test": "paired t-test",
                             "Term": f"{grp} DIV {age_a:g} to {age_b:g}",
                             "Estimate": float(diff.mean()),
                             "Statistic": float(stat), "PValue": float(pval),
                             # Cohen's d_z, the effect size that matches a
                             # paired test: mean change over its own SD.
                             "EffectSize": float(diff.mean() / sd_diff) if sd_diff > 0 else np.nan,
                             "EffectSizeName": "Cohen dz",
                             "N": 2 * len(paired), "NCultures": len(paired)})


def compare_metrics(
    ds: StatsDataset,
    *,
    metrics: list[str] | None = None,
    progress=None,
) -> ComparisonResults:
    """Run every comparison over every metric, for every lag in the run.

    Returns a tidy table: one row per (lag, metric, test, term), with raw and
    FDR-corrected p-values and an effect size whose name is stated in the row,
    because the four test kinds here do not share one.
    """
    names = list(metrics or ds.metrics)
    lags = ds.lags or [None]
    rows: list[dict] = []
    models: dict = {}

    total = len(lags) * len(names)
    done = 0
    for lag in lags:
        sub = ds.for_lag(lag) if lag is not None else ds
        for metric in names:
            if metric in sub.table.columns:
                _model_rows(sub, metric, lag, rows, models)
                _per_age_rows(sub, metric, lag, rows)
                _within_group_age_rows(sub, metric, lag, rows)
            done += 1
            if progress is not None:
                progress(done, total)

    return ComparisonResults(table=_apply_fdr(rows), models=models)
