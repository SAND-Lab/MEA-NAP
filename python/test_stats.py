"""Test the statistics and machine-learning step (``src/meanap/stats``).

Run from the repo root::

    uv run python python/test_stats.py

There is no MATLAB ground truth to compare against: ``doStats``/``doLDA``/
``doClassification`` were never finished, and where they were, this port
deliberately differs (culture-grouped cross-validation instead of leaky splits,
Hedges' g instead of MATLAB's "d-prime", joint omnibus tests instead of
coefficient-by-coefficient inspection). So these are property checks against
data whose answer is known by construction.

Section A builds a synthetic timecourse with a planted age effect, a planted
genotype effect, and a deliberately duplicated feature, then asserts that each
analysis finds what was planted and nothing else:

  - culture IDs collapse the DIV and date tokens, and do not collapse names
    the heuristic does not understand;
  - a metric with a planted age slope is significant, a pure-noise metric is
    not, and FDR correction is monotone in the raw p-values;
  - the duplicated feature shows up as a redundant pair, and effective
    dimensionality is far below the feature count;
  - decoding beats chance on a separable target and *does not* beat it on a
    label that carries no signal — the check that would fail if the splits
    leaked cultures;
  - the Shapley shares sum to the full model's R², and a feature with a real
    but shared contribution gets a positive share while its "unique" variance
    is ~0.

Section B runs the real Yin timecourse bundle end to end and **skips
gracefully** when the gitignored ``local/`` folder is absent.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

warnings.simplefilter("ignore")

from meanap.stats.comparisons import compare_metrics, fdr_correct, hedges_g  # noqa: E402
from meanap.stats.correlation import analyse_correlation  # noqa: E402
from meanap.stats.dataset import StatsDataset, derive_culture_ids, metric_labels  # noqa: E402
from meanap.stats.decoding import (  # noqa: E402
    FAMILY_LABELS, FEATURE_FAMILIES, decode, decoding_shapley, family_of,
    family_shapley, select_representatives,
)
from meanap.stats.regression import regress, variance_decomposition  # noqa: E402

Check = tuple[str, bool, str]

BUNDLE = REPO_ROOT / "local" / "YinThesisRun.meanap"


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── Synthetic fixture ────────────────────────────────────────────────────────

N_CULTURES = 60
AGES = (14.0, 21.0, 28.0, 35.0)
GROUPS = ("WT", "KO")


def _synthetic() -> StatsDataset:
    """A timecourse with a planted age effect, group effect, and duplicate.

    Every culture is measured at every age, so the repeated-measures structure
    is real and a leaky cross-validation would be visibly rewarded by it.

    ``ageMetric``  rises with age, no group difference.
    ``groupMetric`` differs by group, flat in age.
    ``noiseMetric`` is pure noise — nothing should ever find it significant.
    ``ageMetricCopy`` is ``ageMetric`` plus a whisker of noise, so it is a
      near-duplicate that the correlation and decomposition checks look for.
    ``cultureMetric`` is constant within a culture and random between them: it
      identifies the culture and carries no group signal at all, which is what
      makes it the leakage tripwire.
    """
    rng = np.random.default_rng(7)
    rows = []
    for culture_idx in range(N_CULTURES):
        group = GROUPS[culture_idx % len(GROUPS)]
        offset = rng.normal(0, 0.4)              # the culture's random intercept
        identity = rng.normal(0, 1.0)            # its fingerprint
        for age in AGES:
            age_value = 0.08 * age + offset + rng.normal(0, 0.3)
            rows.append({
                "FileName": f"CULT{culture_idx:03d}_20240101_DIV{int(age)}",
                "Culture": f"CULT{culture_idx:03d}",
                "Grp": group,
                "DIV": age,
                "ageMetric": age_value,
                "ageMetricCopy": age_value + rng.normal(0, 0.01),
                "groupMetric": (1.4 if group == "KO" else 0.0)
                               + offset + rng.normal(0, 0.6),
                "noiseMetric": rng.normal(0, 1.0),
                "cultureMetric": identity + rng.normal(0, 0.05),
            })
    table = pd.DataFrame(rows)
    metrics = ["ageMetric", "ageMetricCopy", "groupMetric", "noiseMetric",
               "cultureMetric"]
    return StatsDataset(table=table, metrics=metrics, labels=metric_labels())


# ── Section A ────────────────────────────────────────────────────────────────

def _culture_checks() -> list[Check]:
    checks: list[Check] = []

    names = pd.Series([
        "OPME240607_6_20240719_P1_pup1B_WT_MOI50000_DIV42",
        "OPME240607_6_20240711_P1_pup1B_WT_MOI50000_DIV34",
        "OPME240607_6_20240707_P1_pup3B_WT_MOI50000_DIV30",
    ])
    ids = derive_culture_ids(names)
    checks.append((
        "date and DIV tokens collapse two timepoints of one culture",
        ids.iloc[0] == ids.iloc[1] and ids.iloc[0] != ids.iloc[2],
        f"{list(ids)}"))

    mea = pd.Series(["MPT200114_2A_DIV21", "MPT200114_2A_DIV28",
                     "MPT200114_3B_DIV21"])
    mea_ids = derive_culture_ids(mea)
    checks.append((
        "MEA names (no date token) collapse on DIV alone",
        mea_ids.iloc[0] == mea_ids.iloc[1] and mea_ids.iloc[0] != mea_ids.iloc[2],
        f"{list(mea_ids)}"))

    opaque = pd.Series(["alpha", "beta", "gamma"])
    checks.append((
        "names the heuristic cannot parse are left one-per-culture",
        derive_culture_ids(opaque).nunique() == 3, ""))

    return checks


def _fdr_checks() -> list[Check]:
    checks: list[Check] = []

    p = np.array([0.001, 0.01, 0.03, 0.5, np.nan])
    adjusted = fdr_correct(p)
    checks.append((
        "FDR is monotone in the raw p-values",
        bool(np.all(np.diff(adjusted[:4]) >= -1e-12)), f"{adjusted}"))
    checks.append((
        "FDR never shrinks a p-value or exceeds 1",
        bool(np.all(adjusted[:4] >= p[:4] - 1e-12) and np.all(adjusted[:4] <= 1)),
        f"{adjusted}"))
    checks.append((
        "NaN p-values pass through and are excluded from the count",
        bool(np.isnan(adjusted[4])), ""))

    # Hedges' g of a known standardised difference: two unit-variance samples
    # one SD apart should come back at ~1, slightly shrunk by the correction.
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 400)
    b = rng.normal(1, 1, 400)
    g = hedges_g(a, b)
    checks.append((
        "Hedges' g recovers a planted 1-SD difference",
        0.85 < g < 1.15, f"g = {g:.3f}"))
    checks.append((
        "Hedges' g is signed by direction",
        hedges_g(b, a) < 0, ""))
    return checks


def _comparison_checks() -> list[Check]:
    ds = _synthetic()
    res = compare_metrics(ds)
    table = res.table
    checks: list[Check] = []

    def p_for(metric, term, family="mixed-model"):
        row = table[(table["Metric"] == metric) & (table["Term"] == term)
                    & (table["Family"] == family)]
        return float(row["PValueFDR"].iloc[0]) if len(row) else float("nan")

    checks.append((
        "planted age effect is found on ageMetric",
        p_for("ageMetric", "age") < 0.001, f"q = {p_for('ageMetric', 'age'):.2g}"))
    checks.append((
        "no age effect is invented on groupMetric",
        not (p_for("groupMetric", "age") < 0.05),
        f"q = {p_for('groupMetric', 'age'):.2g}"))
    checks.append((
        "planted group effect is found on groupMetric",
        p_for("groupMetric", "group (omnibus)") < 0.01,
        f"q = {p_for('groupMetric', 'group (omnibus)'):.2g}"))
    checks.append((
        "no group effect is invented on ageMetric",
        not (p_for("ageMetric", "group (omnibus)") < 0.05),
        f"q = {p_for('ageMetric', 'group (omnibus)'):.2g}"))
    checks.append((
        "pure noise metric survives no test at FDR q < 0.05",
        not (table[(table["Metric"] == "noiseMetric")]["PValueFDR"] < 0.05).any(),
        ""))
    checks.append((
        "the age effect's sign is positive, as planted",
        float(table[(table["Metric"] == "ageMetric")
                    & (table["Term"] == "age")]["Estimate"].iloc[0]) > 0, ""))
    checks.append((
        "every reported p-value has an FDR partner",
        bool(table["PValue"].notna().eq(table["PValueFDR"].notna()).all()), ""))

    families = set(table["Family"].dropna())
    checks.append((
        "all three test families ran",
        "mixed-model" in families
        and any(f.startswith("group-at-age") for f in families)
        and any(f.startswith("age-within") for f in families),
        f"{sorted(families)[:4]}"))
    return checks


def _correlation_checks() -> list[Check]:
    ds = _synthetic()
    res = analyse_correlation(ds, redundancy_threshold=0.9)
    checks: list[Check] = []

    pairs = {frozenset((a, b)) for a, b in
             zip(res.redundant["FeatureA"], res.redundant["FeatureB"])}
    checks.append((
        "the planted duplicate is reported as a redundant pair",
        frozenset(("ageMetric", "ageMetricCopy")) in pairs,
        f"{[sorted(p) for p in pairs]}"))
    checks.append((
        "noiseMetric is in no redundant pair",
        not any("noiseMetric" in p for p in pairs), ""))
    checks.append((
        "effective dimensionality is below the feature count",
        1.0 <= res.effective_dim < len(ds.metrics),
        f"{res.effective_dim:.2f} of {len(ds.metrics)}"))
    checks.append((
        "the duplicated pair are neighbours in the clustered order",
        abs(res.order.index("ageMetric") - res.order.index("ageMetricCopy")) == 1,
        f"{res.order}"))
    checks.append((
        "PCA variance is a valid, ordered decomposition",
        bool(np.all(np.diff(res.variance_explained["VarianceExplained"]) <= 1e-9)
             and abs(res.variance_explained["CumulativeVariance"].iloc[-1] - 1) < 1e-6),
        ""))
    return checks


def _decoding_checks() -> list[Check]:
    ds = _synthetic()
    checks: list[Check] = []

    res = decode(ds, target="Grp", models=("logistic", "lda"), n_repeats=2,
                 n_permutations=30, importance_repeats=3, seed=1)
    best = res.summary()["BalancedAccuracy"].max()
    checks.append((
        "genotype is decoded above chance from the planted group effect",
        best > 0.65, f"balanced accuracy {best:.3f} vs chance {res.chance:.3f}"))
    checks.append((
        "the permutation null sits at chance, not at the observed value",
        bool((res.null["NullMean"] - res.chance).abs().max() < 0.08),
        f"{res.null['NullMean'].tolist()}"))
    checks.append((
        "the null yields a small p-value for a real effect",
        bool(res.null["PValue"].min() < 0.05), f"{res.null['PValue'].tolist()}"))
    checks.append((
        "groupMetric is ranked the most important feature",
        res.importance.sort_values("Importance", ascending=False)["Feature"].iloc[0]
        == "groupMetric", ""))

    # The leakage tripwire. `cultureMetric` identifies the culture perfectly
    # and carries no group signal; a decoder given only it must fail, and does
    # fail only because whole cultures are held out. With row-wise folds it
    # would score near-perfectly by memorising each culture's fingerprint from
    # its other timepoints.
    only_identity = ds.with_metrics(["cultureMetric"])
    leak = decode(only_identity, target="Grp", models=("logistic",), n_repeats=2,
                  n_permutations=0, importance_repeats=0, seed=1)
    leaked_score = float(leak.scores["BalancedAccuracy"].mean())
    checks.append((
        "a culture-identity feature does NOT decode genotype (splits do not leak)",
        leaked_score < 0.60, f"balanced accuracy {leaked_score:.3f}"))

    checks.append((
        "out-of-fold predictions cover every recording exactly once",
        len(res.predictions[res.predictions["Model"] == "logistic"]) == len(ds.table),
        ""))
    return checks


def _regression_checks() -> list[Check]:
    ds = _synthetic()
    checks: list[Check] = []

    res = regress(ds, target="DIV", models=("ridge", "randomForest"), n_repeats=2,
                  n_orderings=60, importance_repeats=3, seed=1)
    dec = res.decomposition
    checks.append((
        "Shapley shares sum to the full model's R²",
        abs(dec["Shapley"].sum() - res.r2_full) < 1e-6,
        f"{dec['Shapley'].sum():.6f} vs {res.r2_full:.6f}"))
    checks.append((
        "Shapley shares are all non-negative",
        bool((dec["Shapley"] >= -1e-9).all()), ""))
    checks.append((
        "age is predicted above the mean-only baseline",
        res.summary()["R2"].max() > 0.3, f"R² = {res.summary()['R2'].max():.3f}"))

    by_feature = dec.set_index("Feature")
    checks.append((
        "the two age-carrying features take the largest shares",
        set(dec["Feature"].head(2)) == {"ageMetric", "ageMetricCopy"},
        f"{dec['Feature'].tolist()}"))
    checks.append((
        "a duplicated feature has a real Shapley share but ~no unique variance",
        by_feature.loc["ageMetric", "Shapley"] > 0.05
        and by_feature.loc["ageMetric", "Unique"] < 0.02,
        f"Shapley {by_feature.loc['ageMetric', 'Shapley']:.3f}, "
        f"unique {by_feature.loc['ageMetric', 'Unique']:.4f}"))
    checks.append((
        "a duplicated feature's marginal R² far exceeds its unique R²",
        by_feature.loc["ageMetric", "Marginal"]
        > 10 * max(by_feature.loc["ageMetric", "Unique"], 1e-6), ""))
    checks.append((
        "the noise feature takes a negligible share",
        by_feature.loc["noiseMetric", "Shapley"]
        < by_feature.loc["ageMetric", "Shapley"] / 5,
        f"{by_feature.loc['noiseMetric', 'Shapley']:.4f}"))

    # An orthogonal design is the case where the decomposition has an exactly
    # known answer: with uncorrelated predictors each Shapley value must equal
    # that predictor's own marginal R².
    rng = np.random.default_rng(3)
    X = rng.normal(size=(400, 3))
    X -= X.mean(axis=0)
    Q, _ = np.linalg.qr(X)                       # exactly orthogonal columns
    y = 2.0 * Q[:, 0] + 1.0 * Q[:, 1] + rng.normal(0, 0.1, 400)
    table, r2 = variance_decomposition(Q, y, ["a", "b", "c"], n_orderings=50, seed=0)
    ordered = table.set_index("Feature")
    checks.append((
        "with orthogonal predictors, Shapley equals marginal R² exactly",
        bool((ordered["Shapley"] - ordered["Marginal"]).abs().max() < 1e-9),
        f"{(ordered['Shapley'] - ordered['Marginal']).abs().max():.2e}"))
    checks.append((
        "with orthogonal predictors, Shapley equals unique R² too",
        bool((ordered["Shapley"] - ordered["Unique"]).abs().max() < 1e-9), ""))
    return checks


def _shapley_synthetic() -> StatsDataset:
    """A timecourse where *which* feature separates the groups changes with age.

    ``earlyMetric`` separates the genotypes at DIV 14 and not later;
    ``lateMetric`` does the reverse; ``alwaysNoise`` never does. That is the
    pattern the per-age attribution exists to find, so it is the one to plant.
    Every culture appears once per age, as in the real data.
    """
    rng = np.random.default_rng(19)
    ages = (14.0, 21.0, 28.0, 35.0)
    rows = []
    for culture in range(70):
        group = "KO" if culture % 2 else "WT"
        sign = 1.0 if group == "KO" else -1.0
        for age in ages:
            early = 1.0 if age == ages[0] else 0.0
            late = (age - ages[0]) / (ages[-1] - ages[0])
            rows.append({
                "FileName": f"C{culture:03d}_20240101_DIV{int(age)}",
                "Culture": f"C{culture:03d}", "Grp": group, "DIV": age,
                "earlyMetric": sign * 2.2 * early + rng.normal(0, 1.0),
                "lateMetric": sign * 2.2 * late + rng.normal(0, 1.0),
                "alwaysNoise": rng.normal(0, 1.0),
                "noiseTwin": rng.normal(0, 1.0),
            })
    table = pd.DataFrame(rows)
    # A near-duplicate of the noise column, so representative selection has
    # something to collapse.
    table["alwaysNoiseCopy"] = table["alwaysNoise"] + rng.normal(0, 0.01, len(table))
    metrics = ["earlyMetric", "lateMetric", "alwaysNoise", "noiseTwin",
               "alwaysNoiseCopy"]
    return StatsDataset(table=table, metrics=metrics, labels=metric_labels())


def _shapley_checks() -> list[Check]:
    checks: list[Check] = []
    ds = _shapley_synthetic()

    reps, membership = select_representatives(ds.table, ds.metrics, max_features=4)
    checks.append((
        "representative selection respects the feature cap",
        len(reps) <= 4, f"{reps}"))
    pair = membership[membership["Feature"].isin(["alwaysNoise", "alwaysNoiseCopy"])]
    checks.append((
        "a near-duplicate is collapsed onto the same representative",
        pair["Representative"].nunique() == 1, str(pair.to_dict("records"))))
    checks.append((
        "every input metric is accounted for by some representative",
        set(membership["Feature"]) == set(ds.metrics),
        str(set(ds.metrics) - set(membership["Feature"]))))

    res = decoding_shapley(ds, max_features=4, n_orderings=30, seed=1)
    checks.append((
        "one row per (age, feature), for every age",
        set(res.table["DIV"]) == set(ds.ages)
        and res.table.groupby("DIV").size().nunique() == 1,
        f"{sorted(set(res.table['DIV']))}"))

    # The defining property: the shares at an age partition that age's
    # decodability exactly.
    sums = res.table.groupby("DIV")["Shapley"].sum()
    totals = res.totals.set_index("DIV")["Total"]
    checks.append((
        "the shares at each age sum to that age's decodability",
        bool((sums - totals).abs().max() < 1e-9),
        f"max deviation {float((sums - totals).abs().max()):.2e}"))
    checks.append((
        "decodability is measured against chance, not raw accuracy",
        bool(((res.totals["BalancedAccuracy"] - res.totals["Chance"])
              - res.totals["Total"]).abs().max() < 1e-12), ""))

    wide = res.across_ages()
    checks.append((
        "the same feature set is used at every age, so ages are comparable",
        not wide.isna().any().any(), str(wide.isna().sum().to_dict())))

    ages = sorted(wide.columns)
    early = wide.loc["earlyMetric"]
    late = wide.loc["lateMetric"]
    checks.append((
        "the planted early-only feature peaks at the youngest age",
        early.idxmax() == ages[0], f"peaks at {early.idxmax()}"))
    checks.append((
        "the planted late-growing feature gains share with age",
        late[ages[-1]] > late[ages[0]],
        f"{late[ages[0]]:.3f} at {ages[0]:g} to {late[ages[-1]]:.3f} at {ages[-1]:g}"))
    # Which feature *leads* is the robust claim; which age a feature peaks at
    # is not. A Shapley value here is a marginal contribution to accuracy, and
    # accuracy saturates — once the decoder is near ceiling on a feature, its
    # share stops growing however much stronger the underlying effect gets. So
    # the planted crossover is what to assert, not the position of a maximum.
    checks.append((
        "the two planted features cross over: early leads young, late leads old",
        early[ages[0]] > late[ages[0]] and late[ages[-1]] > early[ages[-1]],
        f"at {ages[0]:g}: early {early[ages[0]]:.3f} vs late {late[ages[0]]:.3f}; "
        f"at {ages[-1]:g}: early {early[ages[-1]]:.3f} vs late {late[ages[-1]]:.3f}"))
    noise_rows = [f for f in wide.index if "oise" in f or "win" in f]
    checks.append((
        "noise features take smaller shares than the planted ones",
        wide.loc[noise_rows].abs().max().max()
        < max(early.max(), late.max()),
        f"noise max {wide.loc[noise_rows].abs().max().max():.3f}"))
    return checks


def _family_checks() -> list[Check]:
    """The three feature families, as players in the same decomposition."""
    checks: list[Check] = []

    known = set(FAMILY_LABELS)
    assigned = set(FEATURE_FAMILIES.values())
    checks.append((
        "every taxonomy entry names a declared family",
        assigned <= known, str(sorted(assigned - known))))
    checks.append((
        "an unknown metric falls into 'other' rather than being guessed at",
        family_of("someMetricNobodyHasWrittenYet") == "other", ""))
    checks.append((
        "an override wins over the built-in taxonomy",
        family_of("Dens", {"Dens": "topology"}) == "topology", ""))

    # A dataset where the answer is known by construction: the group difference
    # lives *only* in the activity family, and the coupling and topology
    # columns are noise. Their unique contributions must be ~0.
    rng = np.random.default_rng(23)
    rows = []
    for culture in range(60):
        group = "KO" if culture % 2 else "WT"
        sign = 1.0 if group == "KO" else -1.0
        for div in (14.0, 21.0, 28.0):
            rows.append({
                "FileName": f"F{culture:03d}_20240101_DIV{int(div)}",
                "Culture": f"F{culture:03d}", "Grp": group, "DIV": div,
                "FRmean": sign * 1.8 + rng.normal(0, 1.0),
                "ISImean": sign * 1.6 + rng.normal(0, 1.0),
                "Dens": rng.normal(0, 1.0),
                "NDmean": rng.normal(0, 1.0),
                "Eglob": rng.normal(0, 1.0),
                "Q": rng.normal(0, 1.0),
            })
    ds = StatsDataset(table=pd.DataFrame(rows), labels=metric_labels(),
                      metrics=["FRmean", "ISImean", "Dens", "NDmean", "Eglob", "Q"])
    res = family_shapley(ds, seed=3)

    placed = res.membership.set_index("Feature")["Family"].to_dict()
    checks.append((
        "metrics are placed in the families they belong to",
        placed["FRmean"] == "activity" and placed["Dens"] == "coupling"
        and placed["Eglob"] == "topology", str(placed)))

    sums = res.table.groupby("DIV")["Shapley"].sum()
    totals = res.totals.set_index("DIV")["Total"]
    checks.append((
        "the families' shares sum to each age's decodability",
        bool((sums - totals).abs().max() < 1e-9),
        f"max deviation {float((sums - totals).abs().max()):.2e}"))

    by_family = res.table.groupby("Family")
    mean_shapley = by_family["Shapley"].mean()
    checks.append((
        "the family the signal was planted in takes the largest share",
        mean_shapley.idxmax() == "activity", str(mean_shapley.round(3).to_dict())))
    mean_unique = by_family["Unique"].mean()
    checks.append((
        "and it is the only family with a unique contribution",
        mean_unique["activity"] > 0.05
        and max(mean_unique["coupling"], mean_unique["topology"]) < 0.03,
        str(mean_unique.round(3).to_dict())))
    checks.append((
        "a noise family's 'alone' is near chance",
        res.table[res.table["Family"] == "topology"]["Alone"].max() < 0.15,
        str(res.table[res.table["Family"] == "topology"]["Alone"].round(3).tolist())))

    # Note what is *not* asserted: that Shapley sits between `Unique` and
    # `Alone`. That bracket holds for a submodular game, and cross-validated
    # accuracy is not one — families can be complementary, and on this fixture
    # activity's `Unique` exceeds its `Alone` at DIV 28 because the classifier
    # uses it better once the other families are present. Asserting the bracket
    # would be asserting an assumption rather than a property.
    mean_alone = by_family["Alone"].mean()
    checks.append((
        "the planted family also leads on the standalone measure",
        mean_alone.idxmax() == "activity", str(mean_alone.round(3).to_dict())))

    # Exactness: with three players the decomposition enumerates all 8 subsets,
    # so re-running must give bit-identical numbers rather than Monte Carlo
    # noise. This is the property that distinguishes it from decoding_shapley.
    again = family_shapley(ds, seed=3)
    checks.append((
        "the decomposition is exact, so it reproduces exactly",
        bool((again.table["Shapley"].to_numpy()
              == res.table["Shapley"].to_numpy()).all()), ""))
    return checks


def _shapley_degenerate_checks() -> list[Check]:
    """One age, or one group, means the question does not exist."""
    checks: list[Check] = []
    ds = _shapley_synthetic()

    one_age = ds._with_table(ds.table[ds.table["DIV"] == 14.0].reset_index(drop=True))
    try:
        res = decoding_shapley(one_age, max_features=3, n_orderings=5)
        ok = len(set(res.table["DIV"])) <= 1
        detail = ""
    except Exception as exc:
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    checks.append(("a single age still decomposes, and says so", ok, detail))

    one_group = ds._with_table(ds.table[ds.table["Grp"] == "WT"].reset_index(drop=True))
    try:
        res = decoding_shapley(one_group, max_features=3, n_orderings=5)
        ok, detail = res.table.empty, "produced rows for a single-class target"
    except Exception as exc:
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    checks.append(("a single group produces nothing rather than an error",
                   ok, detail))
    return checks


def _degenerate_checks() -> list[Check]:
    """Inputs that have no answer must return an empty result, not raise."""
    checks: list[Check] = []
    ds = _synthetic()

    one_group = ds._with_table(ds.table[ds.table["Grp"] == "WT"].reset_index(drop=True))
    try:
        res = decode(one_group, target="Grp", models=("logistic",), n_repeats=1,
                     n_permutations=0, importance_repeats=0)
        ok, detail = res.scores.empty, ""
    except Exception as exc:
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    checks.append(("decoding a single-class target returns empty, not an error",
                   ok, detail))

    tiny = ds._with_table(ds.table.head(4).reset_index(drop=True))
    try:
        res = compare_metrics(tiny)
        ok, detail = res.table["PValue"].isna().all(), "some tests claimed to run"
    except Exception as exc:
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    checks.append(("too few rows produces NaN results with a stated reason",
                   ok, detail))

    constant = ds.table.copy()
    constant["ageMetric"] = 1.0
    try:
        compare_metrics(ds._with_table(constant))
        regress(ds._with_table(constant), target="DIV", models=("ridge",),
                n_repeats=1, n_orderings=10, importance_repeats=0)
        ok, detail = True, ""
    except Exception as exc:
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    checks.append(("a zero-variance metric does not break either analysis",
                   ok, detail))
    return checks


# ── Section B ────────────────────────────────────────────────────────────────

def _bundle_checks() -> list[Check]:
    """The real Yin timecourse, end to end through the runner."""
    from meanap.stats.dataset import load_dataset
    from meanap.stats.run import StatsSettings, run_stats

    checks: list[Check] = []
    ds = load_dataset(BUNDLE)
    design = ds.describe()
    checks.append((
        "network and activity tables merge into one feature table",
        design["n_metrics"] > 40 and "FRmean" in ds.metrics and "Dens" in ds.metrics,
        f"{design['n_metrics']} metrics"))
    checks.append((
        "recordings collapse to fewer cultures",
        0 < design["n_cultures"] < design["n_recordings"],
        f"{design['n_recordings']} recordings, {design['n_cultures']} cultures"))
    checks.append((
        "the run's custom group order is honoured",
        ds.groups[0] == "Wildtype", f"{ds.groups}"))

    with tempfile.TemporaryDirectory() as tmp:
        # Everything turned down: this section checks that the runner writes
        # what it says it writes on real data, not that any number is precise.
        # The two attribution analyses are the expensive ones and default to
        # settings meant for a real run, so they are shrunk here too — without
        # that, this one check costs more than the rest of the file together.
        settings = StatsSettings(
            n_repeats=1, n_permutations=0, n_orderings=30, importance_repeats=2,
            per_age_decoding=False, shapley_orderings=15,
            shapley_max_features=8)
        result = run_stats(BUNDLE, dest=Path(tmp), settings=settings,
                           log=lambda _m: None)
        checks.append((
            "the runner writes tables and figures without skipping an analysis",
            len(result.tables) > 10 and len(result.figures) > 8
            and not result.skipped,
            f"{len(result.tables)} tables, {len(result.figures)} figures, "
            f"skipped {result.skipped}"))
        checks.append((
            "a summary JSON describes all four analyses",
            (Path(tmp) / "stats_summary.json").exists()
            and set(result.summary) >= {"design", "comparisons", "correlation",
                                        "decoding", "regression"},
            f"{sorted(result.summary)}"))
        lag_folder = Path(tmp) / "1000mslag"
        checks.append((
            "results are grouped by lag",
            lag_folder.is_dir() and (lag_folder / "comparisons.csv").exists(), ""))

        decoding = result.summary.get("decoding", {}).get("1000mslag", {})
        checks.append((
            "genotype decodes above chance on the real data",
            decoding.get("best_balanced_accuracy", 0) > decoding.get("chance", 1),
            f"{decoding.get('best_balanced_accuracy')} vs "
            f"{decoding.get('chance')}"))

        regression = result.summary.get("regression", {}).get("1000mslag", {})
        checks.append((
            "age is predicted above the mean-only baseline on the real data",
            regression.get("best_r2", -1) > 0.2, f"R² = {regression.get('best_r2')}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("Statistics and machine-learning step")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A1 — culture identity:", _culture_checks),
        ("Section A2 — multiple comparisons and effect sizes:", _fdr_checks),
        ("Section A3 — planted age and group effects:", _comparison_checks),
        ("Section A4 — feature correlation structure:", _correlation_checks),
        ("Section A5 — decoding, including the leakage tripwire:", _decoding_checks),
        ("Section A6 — regression and variance decomposition:", _regression_checks),
        ("Section A7 — per-age decoding attribution:", _shapley_checks),
        ("Section A8 — feature families as players:", _family_checks),
        ("Section A8b — degenerate inputs:", _degenerate_checks),
        ("Section A9 — degenerate inputs to the attribution:",
         _shapley_degenerate_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    if BUNDLE.exists():
        p, n = _report("Section B — real Yin timecourse bundle:", _bundle_checks())
        total_pass += p
        total += n
    else:
        print(f"\nSection B — SKIPPED (bundle not found at {BUNDLE})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
