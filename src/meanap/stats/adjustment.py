"""Does an age or genotype effect survive holding X, Y, Z fixed? — no MATLAB counterpart.

The 5A comparisons say, per metric, whether it changes with age or differs by
genotype. They cannot say *why*. On the Mecp2 MEA timecourse network density
rises steeply with age (+1.4 SD, p < 1e-30), and so does firing rate, about a
hundredfold; more spikes give the STTC significance test more power, so more
edges pass. Whether density rises *beyond* what rate carries is a different
question, and the standard way to ask it is to put rate into the model:

    metric ~ age + genotype + rate + (1|culture)

and read the age coefficient now, which is the age effect at fixed rate. This
module does that for every metric under each of several *adjustment sets* —
named presets (:data:`PRESETS`) or any columns of the run's table — and
reports each effect beside the unadjusted one, with how much of it remains.

Three readings to keep straight, because the arithmetic is the same for all
three and only the causal story tells them apart:

**A mediator.** Age raises rate and rate raises density. Adjusting for rate
then gives the *direct* age effect, the part not passing through rate. A
collapse means "rate carries it", not "there is no age effect".

**A confounder.** Batch raises both rate and the metric, independently of age.
Adjusting removes a spurious part of the effect, which is what is usually
meant by "controlling for".

**A consequence.** If a stronger network *causes* more bursting, adjusting for
bursting conditions on an outcome and can hide a real effect or invent one.
Covariates measured from the network itself (``aN``, ``Dens``) are the
dangerous ones here.

Two guards the arithmetic does need. A covariate the design nearly determines
— rate on a timecourse where it climbs in lockstep with age — leaves too little
independent variation to separate the two, and "not significant after
adjustment" then means "cannot tell", not "no effect"; every set carries the R²
of its covariates on age and genotype (``CovariateR2``) for that reason. And a
metric is never adjusted for itself or for a near-copy of itself
(|Spearman ρ| ≥ :data:`NEAR_COPY`), which would explain it away trivially.

Every set is fitted on the same recordings — those with every covariate of
every set — so a step between sets is the adjustment changing and not the
cohort. The unadjusted row ("none") is therefore the 5A model refitted on that
cohort, and can differ slightly from 5A when a covariate is missing somewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from meanap.stats.comparisons import (
    RESULT_COLUMNS, _model_rows, fdr_correct,
)
from meanap.stats.dataset import StatsDataset

__all__ = [
    "PRESETS",
    "AdjustmentSet",
    "AdjustmentResults",
    "adjusted_effects",
    "resolve_sets",
]

#: ``name -> (label, roles)``. Each role is a tuple of candidate columns, the
#: first present in the run winning, so one preset reads an ephys run, a
#: calcium run and an imported table alike. A preset with a role nothing fills
#: is skipped, and the log says which.
PRESETS: dict[str, tuple[str, tuple[tuple[str, ...], ...]]] = {
    "rate": ("Firing rate", (("FRmean", "FRmedian", "median_FR"),)),
    "activity": ("Firing rate + active units",
                 (("FRmean", "FRmedian", "median_FR"),
                  ("numActiveElec", "N_active_Es"))),
    "size": ("Network size + density", (("aN", "netw_size"), ("Dens", "netw_density"))),
    "bursting": ("Network bursting", (("NBurstRate", "NetwBurst_per_min"),
                                      ("fracInNburst",))),
}

#: The adjustment sets run when nothing is chosen.
DEFAULT_SETS = ("rate", "activity")

#: A metric this close to a covariate (|Spearman ρ|) is not adjusted for it.
NEAR_COPY = 0.95

#: Above this R² on age and genotype, a covariate is flagged: what is left of
#: it once the design is known is too little to separate the two.
COLLINEAR_R2 = 0.8

#: The unadjusted level's name.
NONE = "none"


@dataclass(frozen=True)
class AdjustmentSet:
    """One set of covariates, as resolved against a run's columns."""

    name: str
    label: str
    columns: tuple[str, ...]


@dataclass
class AdjustmentResults:
    """The effects under every set, and what could not be run."""

    #: :data:`~meanap.stats.comparisons.RESULT_COLUMNS` plus ``Adjustment``,
    #: ``AdjustmentLabel``, ``Covariates``, ``CovariateR2`` and ``Retained``.
    table: pd.DataFrame
    sets: list[AdjustmentSet] = field(default_factory=list)
    #: ``"<set>: why"`` for every requested set that could not be resolved.
    skipped: list[str] = field(default_factory=list)


# ── resolving sets against a run ─────────────────────────────────────────────

def _usable(table: pd.DataFrame, column: str) -> bool:
    if column not in table.columns:
        return False
    values = table[column]
    if pd.api.types.is_numeric_dtype(values):
        values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return values.dropna().nunique() > 1


def resolve_sets(ds: StatsDataset, specs) -> tuple[list[AdjustmentSet], list[str]]:
    """Turn preset names and custom column lists into :class:`AdjustmentSet`.

    A spec is a preset name (``"rate"``) or columns joined by ``+``
    (``"FRmean+numActiveElec"``, or ``"Plate"`` for a batch column). Returns
    the sets that resolved, and a reason for each one that did not.
    """
    table = ds.table
    sets: list[AdjustmentSet] = []
    skipped: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for spec in specs or ():
        spec = str(spec).strip()
        if not spec or spec == NONE:
            continue
        if spec in PRESETS:
            label, roles = PRESETS[spec]
            columns, missing = [], []
            for candidates in roles:
                found = next((c for c in candidates if _usable(table, c)), None)
                (columns.append(found) if found else missing.append("/".join(candidates)))
            if missing:
                skipped.append(f"{spec}: this run has no {', '.join(missing)}")
                continue
        else:
            columns = [c.strip() for c in spec.split("+") if c.strip()]
            bad = [c for c in columns if not _usable(table, c)]
            if bad:
                skipped.append(f"{spec}: no usable column {', '.join(bad)}")
                continue
            label = " + ".join(ds.label(c) for c in columns)
        key = tuple(columns)
        if key in seen:
            continue
        seen.add(key)
        sets.append(AdjustmentSet(name=spec, label=label, columns=key))
    return sets, skipped


# ── the covariates ───────────────────────────────────────────────────────────

def _transform(values: pd.Series) -> pd.Series:
    """Numeric covariates are logged when positive and skewed, then z-scored.

    Rates span decades across development (0.05 to 6 Hz on the Mecp2
    timecourse), and a linear term in the raw rate would let the few busiest
    recordings decide the fit. A categorical covariate is passed through.
    """
    if not pd.api.types.is_numeric_dtype(values):
        return values.astype(str)
    x = pd.to_numeric(values, errors="coerce").astype(float)
    positive = x.dropna()
    if len(positive) and (positive > 0).all() and positive.skew() > 1:
        x = np.log(x)
    elif len(positive) and (positive >= 0).all() and positive.skew() > 1:
        floor = positive[positive > 0].min() / 2 if (positive > 0).any() else 1.0
        x = np.log(x.clip(lower=floor))
    sd = x.std(ddof=1)
    return (x - x.mean()) / (sd if sd > 0 else 1.0)


def _design_r2(table: pd.DataFrame, column: str, ds: StatsDataset) -> float:
    """R² of a numeric covariate on age and genotype: how much the design fixes."""
    import statsmodels.formula.api as smf

    d = table[[column, ds.age_col, ds.group_col]].dropna()
    if len(d) < 5 or not pd.api.types.is_numeric_dtype(d[column]):
        return np.nan
    terms = []
    if d[ds.age_col].nunique() > 1:
        terms.append("_age")
    if d[ds.group_col].nunique() > 1:
        terms.append("C(_grp)")
    if not terms:
        return 0.0
    d = d.assign(_c=d[column], _age=d[ds.age_col], _grp=d[ds.group_col].astype(str))
    try:
        return float(smf.ols("_c ~ " + " + ".join(terms), d).fit().rsquared)
    except Exception:
        return np.nan


def _near_copy(table: pd.DataFrame, metric: str, columns) -> str | None:
    """The covariate *metric* is, or nearly is; ``None`` if none."""
    for column in columns:
        if column == metric:
            return column
        a = pd.to_numeric(table[metric], errors="coerce")
        b = table[column]
        if not pd.api.types.is_numeric_dtype(b):
            continue
        both = pd.concat([a, pd.to_numeric(b, errors="coerce")], axis=1).dropna()
        if len(both) > 5 and abs(both.iloc[:, 0].corr(both.iloc[:, 1], method="spearman")) >= NEAR_COPY:
            return column
    return None


# ── the effects ──────────────────────────────────────────────────────────────

def adjusted_effects(
    ds: StatsDataset,
    specs=DEFAULT_SETS,
    *,
    metrics: list[str] | None = None,
    progress=None,
) -> AdjustmentResults:
    """Every metric's age and genotype effects, unadjusted and under each set.

    The model is the 5A mixed model (:func:`meanap.stats.comparisons._model_rows`)
    with the set's covariates added; effect sizes are on the same scales (SD
    change across the age range for age, standardised beta for a genotype
    contrast) and FDR is corrected within each (lag, set) — so the ``"none"``
    rows are exactly what 5A reports, on the common cohort.
    """
    sets, skipped = resolve_sets(ds, specs)
    names = [m for m in (metrics or ds.metrics) if m in ds.table.columns]
    if not sets:
        return AdjustmentResults(table=pd.DataFrame(), sets=[], skipped=skipped)

    every = sorted({c for s in sets for c in s.columns})
    # The common cohort: a recording missing any covariate is out of every set.
    table = ds.table.copy()
    keep = np.ones(len(table), dtype=bool)
    for column in every:
        values = table[column]
        if pd.api.types.is_numeric_dtype(values):
            values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
        keep &= values.notna().to_numpy()
    table = table[keep].reset_index(drop=True)

    transformed = {column: f"_cov_{i}" for i, column in enumerate(every)}
    lags = ds.lags or [None]
    rows: list[dict] = []
    set_info: dict[str, dict] = {}
    total = len(lags) * len(names) * (len(sets) + 1)
    done = 0
    for lag in lags:
        sub_table = table[table["Lag"] == lag] if lag is not None else table
        sub_table = sub_table.copy()
        for column, name in transformed.items():
            sub_table[name] = _transform(sub_table[column])
        sub = ds._with_table(sub_table.reset_index(drop=True))

        levels = [AdjustmentSet(name=NONE, label="Unadjusted", columns=())] + sets
        for level in levels:
            r2 = {c: _design_r2(sub_table, transformed[c], ds) for c in level.columns}
            finite = [v for v in r2.values() if np.isfinite(v)]
            set_info[(str(lag), level.name)] = dict(
                r2=max(finite) if finite else np.nan,
                covariates=", ".join(f"{c} (R² {r2[c]:.2f})" if np.isfinite(r2[c]) else c
                                     for c in level.columns))
            covariates = {transformed[c]: c for c in level.columns}
            for metric in names:
                start = len(rows)
                copy = _near_copy(sub_table, metric, level.columns)
                if copy is not None:
                    rows.append(dict(Lag=lag, Level=ds.level, Metric=metric,
                                     MetricLabel=ds.label(metric), Family="mixed-model",
                                     Test="LME", Term="age", PValue=np.nan,
                                     Note=f"not adjusted: the metric is (nearly) {copy}"))
                else:
                    _model_rows(sub, metric, lag, rows, {}, covariates)
                for row in rows[start:]:
                    row["Adjustment"] = level.name
                    row["AdjustmentLabel"] = level.label
                done += 1
                if progress is not None:
                    progress(done, total)

    out = pd.DataFrame(rows)
    for column in RESULT_COLUMNS:
        if column not in out.columns:
            out[column] = np.nan
    out["PValueFDR"] = np.nan
    for _, idx in out.groupby(["Lag", "Adjustment", "Family"], dropna=False).groups.items():
        out.loc[idx, "PValueFDR"] = fdr_correct(out.loc[idx, "PValue"])
    out["Covariates"] = [set_info[(str(l), a)]["covariates"]
                         for l, a in zip(out["Lag"], out["Adjustment"])]
    out["CovariateR2"] = [set_info[(str(l), a)]["r2"]
                          for l, a in zip(out["Lag"], out["Adjustment"])]

    # How much of each effect is left: the adjusted effect over the unadjusted.
    keys = ["Lag", "Metric", "Term"]
    base = (out[out["Adjustment"] == NONE][keys + ["EffectSize"]]
            .rename(columns={"EffectSize": "_base"}))
    out = out.merge(base, on=keys, how="left")
    signed = out["EffectSizeName"].isin(["SD change across age range", "standardised beta"]) \
        & (out["Family"] == "mixed-model")
    with np.errstate(divide="ignore", invalid="ignore"):
        out["Retained"] = np.where(signed & (out["_base"].abs() > 1e-12),
                                   out["EffectSize"] / out["_base"], np.nan)
    out = out.drop(columns="_base")

    order = {name: i for i, name in enumerate([NONE] + [s.name for s in sets])}
    out["_order"] = out["Adjustment"].map(order)
    out = (out.sort_values(["Lag", "Metric", "Term", "_order"], kind="stable")
           .drop(columns="_order").reset_index(drop=True))
    columns = RESULT_COLUMNS[:3] + ["Adjustment", "AdjustmentLabel", "Covariates",
                                    "CovariateR2"] + RESULT_COLUMNS[3:] + ["Retained"]
    return AdjustmentResults(table=out[columns], sets=sets, skipped=skipped)
