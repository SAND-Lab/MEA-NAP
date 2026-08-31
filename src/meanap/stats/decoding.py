"""Can genotype or age be read back out of the features? — ports ``doClassification.m``
and ``doLDA.m``.

MATLAB fits five classifiers, cross-validates each, shuffles each feature in
turn to rank importance, and shuffles the labels 200 times to get a null. The
structure is kept. What changes is who is allowed to be in which fold.

**Culture-grouped cross-validation.** MATLAB calls ``crossval(..., 'KFold', 2)``
on a table where the same culture contributes a row at every DIV. A model that
has seen a culture at DIV 21 and is then tested on the same culture at DIV 28 is
being asked to recognise a culture it has already met, and it is very good at
that — the reported accuracy measures culture identity as much as genotype.
Every split here is a :class:`~sklearn.model_selection.StratifiedGroupKFold` on
culture, so a culture is wholly in train or wholly in test.

**A null that respects the grouping too.** Permuting labels row-wise would break
the culture-to-label link that the real data has (a culture has one genotype at
every age), making the null easier than the real problem and the p-value
optimistic. :func:`permutation_null` permutes labels *between cultures*,
carrying the label to all of that culture's recordings.

**Importance measured out of fold.** MATLAB re-fits on shuffled features and
compares training-fold losses. Here it is the standard held-out permutation
importance: shuffle one feature in the *test* fold of an already-fitted model
and measure the drop in balanced accuracy, which is what the feature is worth
to a model that has to generalise.

Balanced accuracy throughout, not the misclassification rate MATLAB reports:
these genotype groups are unequal (Yin's timecourse is 44/40/37 cultures but
132/159/87 recordings), and plain accuracy rewards a model for always guessing
the biggest class.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from meanap.stats.dataset import StatsDataset

__all__ = [
    "DecodingResults",
    "MODEL_NAMES",
    "build_models",
    "decode",
    "decode_per_age",
    "lda_projection",
    "permutation_null",
]

#: The classifiers offered, in the order figures should present them. The set
#: mirrors MATLAB's (``linearSVM``/``kNN``/``decisionTree``/``fforwardNN``/
#: ``LDA``) with two substitutions: logistic regression in place of the single
#: decision tree, because one unpruned tree on 50 correlated features is mostly
#: noise, and a random forest in place of the feed-forward net, because a net
#: on ~120 cultures has nothing to learn from that a forest does not.
MODEL_NAMES = ("logistic", "lda", "linearSVM", "rbfSVM", "randomForest", "kNN")


def build_models(names=MODEL_NAMES, *, seed: int = 0) -> dict:
    """Named scikit-learn pipelines, each standardising its inputs first.

    Standardisation is inside the pipeline rather than applied to the whole
    matrix up front, so the scaler is fitted on training folds only. Scaling on
    the full dataset would leak each test fold's mean and variance into its own
    training — a small leak next to the culture one, but free to avoid.
    """
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    factories = {
        "logistic": lambda: LogisticRegression(
            max_iter=5000, C=1.0, class_weight="balanced"),
        # 'lsqr' with shrinkage is the well-conditioned counterpart of MATLAB's
        # 'pseudoLinear' discrimType: both exist to cope with a within-class
        # covariance that is singular, which it is whenever features outnumber
        # the cultures in a class.
        "lda": lambda: LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"),
        "linearSVM": lambda: SVC(kernel="linear", C=1.0, class_weight="balanced"),
        "rbfSVM": lambda: SVC(kernel="rbf", C=1.0, gamma="scale",
                              class_weight="balanced"),
        "randomForest": lambda: RandomForestClassifier(
            n_estimators=500, random_state=seed, class_weight="balanced_subsample",
            n_jobs=-1),
        "kNN": lambda: KNeighborsClassifier(n_neighbors=5),
    }
    return {
        name: Pipeline([("scale", StandardScaler()), ("model", factories[name]())])
        for name in names if name in factories
    }


@dataclass
class DecodingResults:
    """Everything one decoding run produced."""

    #: One row per (model, repeat, fold): balanced accuracy and accuracy.
    scores: pd.DataFrame
    #: One row per (model, recording): true label and out-of-fold prediction.
    predictions: pd.DataFrame
    #: ``model -> DataFrame`` confusion matrix (rows true, columns predicted).
    confusion: dict = field(default_factory=dict)
    #: One row per (model, feature): mean drop in balanced accuracy when that
    #: feature is permuted in held-out data.
    importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: One row per model: observed score, null distribution summary, p-value.
    null: pd.DataFrame = field(default_factory=pd.DataFrame)
    features: list[str] = field(default_factory=list)
    target: str = "Grp"
    classes: list[str] = field(default_factory=list)
    chance: float = float("nan")
    n_samples: int = 0
    n_groups: int = 0
    lag: object = None

    def summary(self) -> pd.DataFrame:
        """Mean and SD of balanced accuracy per model, best first."""
        if self.scores.empty:
            return pd.DataFrame()
        out = (self.scores.groupby("Model")["BalancedAccuracy"]
               .agg(["mean", "std", "count"]).reset_index()
               .rename(columns={"mean": "BalancedAccuracy",
                                "std": "SD", "count": "NFolds"}))
        out["Chance"] = self.chance
        if not self.null.empty:
            out = out.merge(self.null[["Model", "PValue"]], on="Model", how="left")
        return out.sort_values("BalancedAccuracy", ascending=False).reset_index(drop=True)


# ── splitting ────────────────────────────────────────────────────────────────

def _splits(y, groups, *, n_splits: int, n_repeats: int, seed: int):
    """Repeated culture-grouped stratified k-fold splits.

    scikit-learn has no ``RepeatedStratifiedGroupKFold``, so the repeats are
    made by re-shuffling. *n_splits* is reduced when a class has fewer cultures
    than folds, since a fold with no example of a class scores it as zero and
    drags the mean down for a reason that has nothing to do with the features.
    """
    from sklearn.model_selection import StratifiedGroupKFold

    y = np.asarray(y)
    groups = np.asarray(groups)
    per_class = pd.Series(y).groupby(pd.Series(groups)).first().value_counts()
    usable = int(min(n_splits, per_class.min())) if len(per_class) else 0
    if usable < 2:
        return
    for repeat in range(n_repeats):
        splitter = StratifiedGroupKFold(
            n_splits=usable, shuffle=True, random_state=seed + repeat)
        for fold, (train, test) in enumerate(splitter.split(np.zeros(len(y)), y, groups)):
            yield repeat, fold, train, test


class _single_threaded:
    """Temporarily set every estimator's ``n_jobs`` to 1.

    Only the random forest has one, but a forest asking for every core from
    inside each of *n* parallel permutation workers oversubscribes the machine
    badly enough to run slower than no parallelism at all.
    """

    def __init__(self, built: dict):
        self._built = built
        self._saved: list = []

    def __enter__(self):
        for pipe in self._built.values():
            est = pipe.named_steps.get("model")
            # Only estimators that were *given* an ``n_jobs`` — leaving it at
            # its default means the estimator either does not parallelise or,
            # as with ``LogisticRegression`` since scikit-learn 1.8, ignores
            # the parameter and warns when it is set.
            if est is not None and getattr(est, "n_jobs", None) is not None:
                self._saved.append((est, est.n_jobs))
                est.n_jobs = 1
        return self

    def __exit__(self, *exc):
        for est, value in self._saved:
            est.n_jobs = value
        return False


def _chance_level(y) -> float:
    """Balanced accuracy of a classifier that ignores its input.

    Always ``1/n_classes``: a constant prediction is right for one class and
    wrong for the rest, and balanced accuracy averages the per-class recalls.
    This is the honest baseline, unlike the majority-class rate MATLAB draws.
    """
    n = len(np.unique(y))
    return 1.0 / n if n else float("nan")


# ── the run ──────────────────────────────────────────────────────────────────

def decode(
    ds: StatsDataset,
    *,
    target: str | None = None,
    models=MODEL_NAMES,
    metrics: list[str] | None = None,
    n_splits: int = 5,
    n_repeats: int = 5,
    n_permutations: int = 200,
    importance_repeats: int = 10,
    seed: int = 0,
    n_jobs: int = -1,
    lag=None,
    progress=None,
) -> DecodingResults:
    """Decode *target* from the features, with culture-grouped cross-validation.

    *target* defaults to genotype, or to age when the run has only one genotype
    — the same rule MATLAB uses. Set *n_permutations* to 0 to skip the null,
    which is the bulk of the runtime.
    """
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix

    if target is None:
        target = ds.age_col if len(ds.groups) < 2 else ds.group_col

    X, feature_names, meta = ds.feature_matrix(metrics=metrics)
    y = meta[target].astype(str).to_numpy()
    groups = meta[ds.culture_col].astype(str).to_numpy()
    classes = sorted(set(y))

    empty = DecodingResults(
        scores=pd.DataFrame(), predictions=pd.DataFrame(), features=feature_names,
        target=target, classes=classes, chance=_chance_level(y),
        n_samples=len(y), n_groups=len(set(groups)), lag=lag)
    if len(classes) < 2 or X.shape[0] < 10:
        return empty

    splits = list(_splits(y, groups, n_splits=n_splits, n_repeats=n_repeats, seed=seed))
    if not splits:
        return empty

    built = build_models(models, seed=seed)
    score_rows, pred_rows, importance_rows = [], [], []
    # Out-of-fold predictions from the first repeat only: with repeats every
    # sample is predicted several times, and a confusion matrix wants one
    # prediction per sample.
    oof = {name: np.full(len(y), None, dtype=object) for name in built}

    total = len(built) * len(splits)
    done = 0
    for name, template in built.items():
        for repeat, fold, train, test in splits:
            model = clone(template)
            model.fit(X[train], y[train])
            pred = model.predict(X[test])
            bal = balanced_accuracy_score(y[test], pred)
            score_rows.append({
                "Model": name, "Repeat": repeat, "Fold": fold,
                "BalancedAccuracy": float(bal),
                "Accuracy": float(accuracy_score(y[test], pred)),
                "NTrain": len(train), "NTest": len(test),
            })
            if repeat == 0:
                oof[name][test] = pred
            if importance_repeats and repeat == 0:
                importance_rows.extend(_fold_importance(
                    name, model, X, y, test, feature_names, bal,
                    n_repeats=importance_repeats, seed=seed + fold))
            done += 1
            if progress is not None:
                progress(done, total)

    for name, preds in oof.items():
        have = preds != None  # noqa: E711 — object array, `is not None` won't vectorise
        pred_rows.append(pd.DataFrame({
            "Model": name,
            ds.name_col: meta[ds.name_col].to_numpy()[have],
            ds.culture_col: groups[have],
            "True": y[have],
            "Predicted": preds[have].astype(str),
        }))

    predictions = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    confusion = {}
    for name in built:
        sub = predictions[predictions["Model"] == name] if not predictions.empty else None
        if sub is None or sub.empty:
            continue
        mat = confusion_matrix(sub["True"], sub["Predicted"], labels=classes)
        confusion[name] = pd.DataFrame(mat, index=classes, columns=classes)

    importance = pd.DataFrame(importance_rows)
    if not importance.empty:
        importance = (importance.groupby(["Model", "Feature"])["Drop"]
                      .agg(["mean", "std"]).reset_index()
                      .rename(columns={"mean": "Importance", "std": "SD"}))
        importance["FeatureLabel"] = importance["Feature"].map(ds.label)
        importance = importance.sort_values(
            ["Model", "Importance"], ascending=[True, False]).reset_index(drop=True)

    scores = pd.DataFrame(score_rows)
    null = pd.DataFrame()
    if n_permutations:
        null = permutation_null(
            X, y, groups, built, scores, n_splits=n_splits, seed=seed,
            n_permutations=n_permutations, n_jobs=n_jobs, progress=progress)

    return DecodingResults(
        scores=scores, predictions=predictions, confusion=confusion,
        importance=importance, null=null, features=feature_names, target=target,
        classes=classes, chance=_chance_level(y), n_samples=len(y),
        n_groups=len(set(groups)), lag=lag,
    )


def _fold_importance(name, model, X, y, test, feature_names, baseline, *,
                     n_repeats: int, seed: int) -> list[dict]:
    """Permutation importance of each feature on one held-out fold.

    scikit-learn's own routine rather than a hand-rolled loop: it is the same
    computation (shuffle column *j* of the test fold, re-score, average the
    drop) but parallelised over features, which matters because the forest has
    to re-predict once per feature per repeat.
    """
    from sklearn.inspection import permutation_importance

    result = permutation_importance(
        model, X[test], y[test], scoring="balanced_accuracy",
        n_repeats=n_repeats, random_state=seed, n_jobs=-1)
    return [
        {"Model": name, "Feature": feature, "Drop": float(mean)}
        for feature, mean in zip(feature_names, result.importances_mean)
    ]


def permutation_null(
    X, y, groups, built: dict, observed: pd.DataFrame, *,
    n_splits: int, n_permutations: int, seed: int, n_jobs: int = -1, progress=None,
) -> pd.DataFrame:
    """Label-permutation null, permuting labels between cultures.

    Each culture keeps one label across all its recordings, as in the real data;
    what is destroyed is only the link between a culture's label and its
    features. A row-wise shuffle would additionally destroy the within-culture
    label consistency, and so would not be a null for *this* problem.

    The p-value is ``(1 + #{null >= observed}) / (1 + n)`` — the add-one form,
    which cannot return 0 and correctly reports that *n* permutations can only
    bound a p-value from below.
    """
    from sklearn.base import clone
    from sklearn.metrics import balanced_accuracy_score

    y = np.asarray(y)
    groups = np.asarray(groups)

    unique_cultures = np.unique(groups)
    culture_label = pd.Series(y, index=groups).groupby(level=0).first()
    culture_label = culture_label.reindex(unique_cultures).to_numpy()

    # One split scheme, reused across permutations: the null is about the
    # labels, and re-drawing folds each time would fold split variability into
    # it and widen it for the wrong reason.
    def one_permutation(i: int) -> dict:
        local = np.random.default_rng(seed + 1000 + i)
        shuffled = culture_label[local.permutation(len(culture_label))]
        mapping = dict(zip(unique_cultures, shuffled))
        y_perm = np.array([mapping[g] for g in groups])
        splits = list(_splits(y_perm, groups, n_splits=n_splits, n_repeats=1,
                              seed=seed + i))
        if not splits:
            return {}
        out = {}
        for name, template in built.items():
            fold_scores = []
            for _, _, train, test in splits:
                model = clone(template)
                model.fit(X[train], y_perm[train])
                fold_scores.append(balanced_accuracy_score(
                    y_perm[test], model.predict(X[test])))
            out[name] = float(np.mean(fold_scores))
        return out

    # Permutations are independent and there are hundreds of them, so this is
    # where parallelism pays. The models inside are asked for one thread each
    # (``n_jobs`` on the forest would otherwise oversubscribe every core from
    # inside every worker).
    from joblib import Parallel, delayed

    with _single_threaded(built):
        results = Parallel(n_jobs=n_jobs, prefer="processes")(
            delayed(one_permutation)(i) for i in range(n_permutations))

    rows = []
    null_scores = {name: [] for name in built}
    for res in results:
        for name, value in res.items():
            null_scores[name].append(value)
    if progress is not None:
        progress(n_permutations, n_permutations)

    for name, values in null_scores.items():
        arr = np.asarray(values, dtype=float)
        obs = float(observed.loc[observed["Model"] == name,
                                 "BalancedAccuracy"].mean())
        if arr.size == 0:
            rows.append({"Model": name, "Observed": obs, "NullMean": np.nan,
                         "NullSD": np.nan, "Null95": np.nan, "PValue": np.nan,
                         "NPermutations": 0})
            continue
        rows.append({
            "Model": name, "Observed": obs,
            "NullMean": float(arr.mean()), "NullSD": float(arr.std(ddof=1)),
            "Null95": float(np.percentile(arr, 95)),
            "PValue": float((1 + np.sum(arr >= obs)) / (1 + arr.size)),
            "NPermutations": int(arr.size),
        })
    return pd.DataFrame(rows)


def decode_per_age(ds: StatsDataset, *, models=("logistic", "lda"), **kwargs) -> dict:
    """Decode genotype separately at each age.

    The cross-sectional counterpart of :func:`decode`, and the question
    ``doLDA``'s ``genotypePerDIV`` mode asks: at DIV 14 the genotypes may be
    indistinguishable and by DIV 42 separable, which a decoder pooled over ages
    cannot show. Within one age a culture contributes one recording, so the
    grouped splits reduce to ordinary stratified ones.
    """
    out = {}
    for age in ds.ages:
        sub = ds._with_table(
            ds.table[ds.table[ds.age_col] == age].reset_index(drop=True))
        if sub.table[ds.group_col].nunique() < 2 or len(sub.table) < 15:
            continue
        out[float(age)] = decode(sub, target=ds.group_col, models=models, **kwargs)
    return out


def lda_projection(ds: StatsDataset, *, target: str | None = None,
                   metrics: list[str] | None = None) -> dict:
    """Project the recordings onto their discriminant axes — ports ``doLDA.m``.

    MATLAB solves the generalised eigenproblem on the between- and within-class
    scatter by hand; ``LinearDiscriminantAnalysis(solver="eigen")`` is the same
    decomposition, and its ``explained_variance_ratio_`` says how much of the
    between-class separation each axis carries — a number ``doLDA`` computes
    (``lambda``) and then discards.

    This is a *descriptive* projection fitted on all the data, so its apparent
    separation is not an out-of-sample result; :func:`decode` is where the
    honest number comes from. Shrinkage keeps it defined when the within-class
    covariance is singular, which it is whenever features outnumber recordings
    in a class.
    """
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.preprocessing import StandardScaler

    target = target or (ds.age_col if len(ds.groups) < 2 else ds.group_col)
    X, names, meta = ds.feature_matrix(metrics=metrics)
    y = meta[target].astype(str).to_numpy()
    if len(np.unique(y)) < 2 or X.shape[0] < 5:
        return {}

    Xs = StandardScaler().fit_transform(X)
    lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto")
    coords = lda.fit_transform(Xs, y)
    n_axes = coords.shape[1]

    # scikit-learn returns only the retained axes' ratios but normalises them
    # over *every* eigenvalue of the generalised problem — one per feature —
    # and the between-class scatter has rank n_classes-1, so the rest are
    # numerical noise that nonetheless dominates the denominator. On the Yin
    # run that reports two axes at 5.4% and 5.4%, which reads as "the
    # discriminant axes explain nothing" when what it means is "5% of a sum
    # that is 90% junk". Renormalising over the retained axes gives the
    # quantity actually being asked for: how the between-class separation
    # splits between the discriminant axes (there, 50/50).
    raw = np.asarray(lda.explained_variance_ratio_[:n_axes], dtype=float)
    total = float(raw.sum())
    explained = raw / total if total > 0 else raw

    return {
        "coords": pd.DataFrame(
            coords, columns=[f"LD{i + 1}" for i in range(n_axes)]).assign(
                **{target: y, ds.culture_col: meta[ds.culture_col].to_numpy(),
                   ds.age_col: meta[ds.age_col].to_numpy()}),
        "loadings": pd.DataFrame(
            lda.scalings_[:, :n_axes], index=names,
            columns=[f"LD{i + 1}" for i in range(n_axes)]),
        "explained": explained,
        #: The unnormalised ratios, kept because they are what scikit-learn
        #: reported and someone comparing against it will look for them.
        "explained_raw": raw,
        "target": target,
        "features": names,
    }


# ── Shapley attribution of decoding performance ──────────────────────────────
#
# The counterpart of `regression.variance_decomposition`, for a categorical
# target. There the quantity partitioned is R²; here it is how far a decoder
# gets above chance, and the question is which features carry the genotype
# signal at each age and whether that changes as the culture matures.
#
# Two differences from the regression version are worth knowing.
#
# **Shapley values here can be negative.** Nested least-squares R² can only
# rise as features are added, so the regression decomposition's shares are
# non-negative by construction. Cross-validated accuracy has no such guarantee
# — a feature that is noise in this sample makes the classifier worse — so a
# negative share is a real result meaning "this metric cost the decoder
# accuracy", not an error.
#
# **The features are de-duplicated first, and de-duplicated once.** With 50
# metrics whose effective dimensionality is about five, a Shapley value split
# between two columns that correlate at 0.99 is arbitrary. Redundant metrics
# are collapsed to one representative each *before* the decomposition, using a
# rule that never looks at the labels (see `select_representatives`), so this
# adds no selection bias to the totals. The selection is made once on the
# pooled data and reused at every age — with a different feature set per age
# the trajectories would not be comparable, which is the whole point of
# looking across ages.

__all__ += ["ShapleyDecoding", "decoding_shapley", "select_representatives"]


@dataclass
class ShapleyDecoding:
    """Per-age Shapley attribution of decoding performance across features."""

    #: One row per (age, feature): its Shapley share of the decodability at
    #: that age, and that age's total.
    table: pd.DataFrame
    #: One row per age: cross-validated balanced accuracy, chance, the total
    #: the Shapley values sum to, and how many recordings it was measured on.
    totals: pd.DataFrame
    #: One row per original metric: which representative stands for it, and how
    #: strongly. Metrics that are their own representative appear too.
    clusters: pd.DataFrame = field(default_factory=pd.DataFrame)
    features: list[str] = field(default_factory=list)
    target: str = "Grp"
    model: str = "lda"
    n_orderings: int = 0
    lag: object = None

    def across_ages(self) -> pd.DataFrame:
        """Features as rows, ages as columns — the shape both figures read."""
        if self.table.empty:
            return pd.DataFrame()
        return self.table.pivot_table(index="Feature", columns="DIV",
                                      values="Shapley")


def select_representatives(
    frame: pd.DataFrame, metrics: list[str], *, max_features: int = 15,
    method: str = "spearman",
) -> tuple[list[str], pd.DataFrame]:
    """Collapse correlated metrics to one representative each.

    Hierarchical clustering on ``1 - |r|``, cut to at most *max_features*
    clusters, with the most central member of each cluster — the one whose
    absolute correlations to the rest of its cluster are largest — standing for
    it. A metric and its negative image cluster together, since for "am I
    measuring one thing twice" the sign is irrelevant.

    **This never looks at the labels.** That matters: screening features by how
    well they separate the groups and then reporting how well those features
    separate the groups is circular, and would inflate every total this
    produces. Redundancy is a property of the feature set alone, so removing it
    is free of that.

    Returns ``(representatives, membership)`` where *membership* has one row per
    input metric naming its representative.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    from meanap.stats.correlation import correlation_matrix

    corr = correlation_matrix(frame, metrics, method=method)
    keep = [c for c in corr.columns if corr[c].notna().sum() > 1]
    corr = corr.loc[keep, keep]
    names = list(corr.columns)
    if not names:
        return [], pd.DataFrame(columns=["Feature", "Representative", "R"])
    if len(names) <= max_features:
        return names, pd.DataFrame({"Feature": names, "Representative": names,
                                    "R": 1.0})

    dist = 1.0 - corr.abs().to_numpy(dtype=float)
    dist = np.nan_to_num(dist, nan=1.0)
    dist = (dist + dist.T) / 2.0
    np.fill_diagonal(dist, 0.0)
    labels = fcluster(linkage(squareform(dist, checks=False), method="average"),
                      t=max_features, criterion="maxclust")

    rows, representatives = [], []
    for cluster in sorted(set(labels)):
        members = [n for n, lab in zip(names, labels) if lab == cluster]
        if len(members) == 1:
            rep = members[0]
        else:
            block = corr.loc[members, members].abs()
            rep = block.sum(axis=1).idxmax()
        representatives.append(rep)
        for member in members:
            rows.append({"Feature": member, "Representative": rep,
                         "R": float(corr.loc[member, rep])})
    # Keep the input ordering, so the representative list is stable and reads
    # in the order the pipeline computes the metrics.
    representatives = [n for n in names if n in set(representatives)]
    return representatives, pd.DataFrame(rows)


def _subset_scorer(X, y, groups, *, n_splits: int, model: str, seed: int):
    """A cached ``value(S)`` — cross-validated balanced accuracy above chance.

    ``value(∅)`` is zero by definition: a classifier given nothing predicts one
    class and scores exactly chance under balanced accuracy. Fitting that case
    would be both wasteful and, for some estimators, an error.

    One fixed set of folds is used for every subset. Re-drawing them per subset
    would add split noise to each marginal contribution, and the differences
    between nested subsets are what the whole decomposition is made of.
    """
    from sklearn.base import clone
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedGroupKFold

    template = build_models((model,), seed=seed)[model]
    chance = _chance_level(y)
    per_class = pd.Series(y).groupby(pd.Series(groups)).first().value_counts()
    usable = int(min(n_splits, per_class.min())) if len(per_class) else 0
    if usable < 2:
        return None, chance
    splits = list(StratifiedGroupKFold(
        n_splits=usable, shuffle=True, random_state=seed).split(
            np.zeros(len(y)), y, groups))

    cache: dict[frozenset, float] = {frozenset(): 0.0}

    def value(columns) -> float:
        key = frozenset(columns)
        hit = cache.get(key)
        if hit is not None:
            return hit
        cols = list(key)
        scores = []
        for train, test in splits:
            model_ = clone(template)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model_.fit(X[np.ix_(train, cols)], y[train])
                pred = model_.predict(X[np.ix_(test, cols)])
            scores.append(balanced_accuracy_score(y[test], pred))
        cache[key] = float(np.mean(scores)) - chance
        return cache[key]

    return value, chance


def _shapley_for_age(X, y, groups, feature_names, *, n_orderings: int,
                     n_splits: int, model: str, seed: int):
    """Monte Carlo Shapley values of *value* over the feature set.

    Each random ordering is walked once, adding each feature's marginal
    contribution to the running prefix. Subset scores are cached, so the small
    prefixes — which every ordering shares — are paid for once.
    """
    value, chance = _subset_scorer(X, y, groups, n_splits=n_splits, model=model,
                                   seed=seed)
    if value is None:
        return None, chance, float("nan")

    p = len(feature_names)
    rng = np.random.default_rng(seed)
    shapley = np.zeros(p)
    for _ in range(n_orderings):
        order = rng.permutation(p)
        prefix: list[int] = []
        previous = 0.0
        for column in order:
            prefix.append(int(column))
            current = value(prefix)
            shapley[column] += current - previous
            previous = current
    shapley /= n_orderings
    return shapley, chance, value(range(p))


def decoding_shapley(
    ds: StatsDataset,
    *,
    target: str | None = None,
    metrics: list[str] | None = None,
    max_features: int = 15,
    n_orderings: int = 100,
    n_splits: int = 5,
    model: str = "lda",
    seed: int = 0,
    lag=None,
    progress=None,
) -> ShapleyDecoding:
    """How much each feature contributes to decoding *target*, at each age.

    Runs the decomposition separately within every age, over one feature set
    chosen once on the pooled data. The values at one age sum to that age's
    decodability — its cross-validated balanced accuracy minus chance — so a
    column can be read as a partition of what was there to be decoded, and the
    totals can be compared across ages.

    Within an age each culture contributes a single recording, so the folds are
    ordinary stratified ones; they are still grouped by culture, which costs
    nothing and keeps the guarantee if a dataset ever breaks that assumption.
    """
    target = target or ds.group_col
    names = list(metrics or ds.metrics)

    representatives, membership = select_representatives(
        ds.table, names, max_features=max_features)
    if not representatives:
        return ShapleyDecoding(table=pd.DataFrame(), totals=pd.DataFrame(),
                               target=target, model=model, lag=lag)
    if not membership.empty:
        membership = membership.copy()
        membership["FeatureLabel"] = membership["Feature"].map(ds.label)
        membership["RepresentativeLabel"] = membership["Representative"].map(ds.label)

    rows, totals = [], []
    ages = ds.ages
    for index, age in enumerate(ages):
        at_age = ds.table[ds.table[ds.age_col] == age]
        sub = ds._with_table(at_age.reset_index(drop=True))
        X, feature_names, meta = sub.feature_matrix(metrics=representatives)
        y = meta[target].astype(str).to_numpy()
        groups = meta[ds.culture_col].astype(str).to_numpy()
        if len(set(y)) < 2 or X.shape[0] < 10 or X.shape[1] < 2:
            continue

        shapley, chance, total = _shapley_for_age(
            X, y, groups, feature_names, n_orderings=n_orderings,
            n_splits=n_splits, model=model, seed=seed)
        if progress is not None:
            progress(index + 1, len(ages))
        if shapley is None:
            continue

        for name, value in zip(feature_names, shapley):
            rows.append({
                "DIV": float(age), "Feature": name,
                "FeatureLabel": ds.label(name), "Shapley": float(value),
                "Share": float(value / total) if total else np.nan,
                "Total": float(total), "Chance": float(chance),
                "N": int(X.shape[0]),
            })
        totals.append({
            "DIV": float(age), "BalancedAccuracy": float(total + chance),
            "Chance": float(chance), "Total": float(total),
            "N": int(X.shape[0]), "NFeatures": len(feature_names),
            "NCultures": int(len(set(groups))),
        })

    return ShapleyDecoding(
        table=pd.DataFrame(rows), totals=pd.DataFrame(totals),
        clusters=membership, features=representatives, target=target,
        model=model, n_orderings=n_orderings, lag=lag,
    )


# ── Contributions of whole feature families ──────────────────────────────────
#
# The per-feature attribution above answers "which metric carries the signal".
# It cannot answer the question that usually follows: is an apparent difference
# in network *organisation* real, or is it what you would expect anyway from a
# culture that simply fires more and is more strongly correlated? Density and
# global efficiency correlate at 0.98 on the Yin run, so no per-feature ranking
# can separate those two readings.
#
# Treating a whole family as one player does separate them. Three families:
#
#   activity   how much the cells fire, independent of any pairwise measure
#   coupling   how much correlation there is — density, degree, strength, the
#              significant-edge counts. "Global correlation", not topology.
#   topology   the graph-theoretic metrics: efficiency, clustering, path
#              length, modularity, cartography, controllability
#
# Two things make this view stronger than the per-feature one:
#
# **Collinearity inside a family stops mattering.** Thirteen metrics that are
# all density in disguise are one player, so no credit is split arbitrarily
# between them — which is why this needs none of the redundancy reduction
# `decoding_shapley` does.
#
# **Collinearity *between* families is exactly what the Shapley value is for.**
# The part of the signal that density and global efficiency share is split
# between coupling and topology in proportion to how often each is the one that
# adds it, over all orders of entry.
#
# `alone` and `unique` are reported beside it, and their gap is the finding:
# a family with a large `alone` and a near-zero `unique` carries nothing the
# other families do not already carry.

__all__ += ["FEATURE_FAMILIES", "FAMILY_LABELS", "FamilyShapley",
            "family_shapley", "family_of"]

#: Presentation order and display names for the three families.
FAMILY_LABELS: dict[str, str] = {
    "activity": "Activity",
    "coupling": "Correlation strength",
    "topology": "Network topology",
    "other": "Unclassified",
}

#: Which family each metric belongs to. Explicit rather than pattern-matched,
#: because the boundaries are judgement calls that deserve to be readable and
#: arguable — the two most arguable are noted below. Anything absent lands in
#: ``other``, which becomes a family of its own rather than being silently
#: dropped or silently folded into one of the three.
FEATURE_FAMILIES: dict[str, str] = {
    # ── Activity: properties of the traces, computed before any pairwise
    # measure exists. ``aN``/``numActiveElec`` are here because how many cells
    # are active is a fact about firing, not about the graph — even though the
    # graph is then built on them.
    "FRmean": "activity", "FRstd": "activity", "FRsem": "activity",
    "FRmedian": "activity", "FRiqr": "activity", "FR": "activity",
    "FRactive": "activity", "ISImean": "activity", "ISI": "activity",
    "numActiveElec": "activity", "aN": "activity",
    "recHeightMean": "activity", "recPeakDurMean": "activity",
    "recEventAreaMean": "activity", "unitHeightMean": "activity",
    "unitPeakDurMean": "activity", "unitEventAreaMean": "activity",
    "unitEventAreaSum": "activity",
    # Dimensionality of the population activity. Arguable: both are computed
    # from the activity matrix rather than from the adjacency matrix, which is
    # why they sit here rather than under coupling.
    "effRank": "activity", "num_nnmf_components": "activity",
    "nComponentsRelNS": "activity", "nnmf_residuals": "activity",
    "nnmf_var_explained": "activity",

    # ── Coupling: how much correlation there is, with no reference to how it
    # is arranged. Every one of these rises monotonically with the mean
    # pairwise correlation.
    "Dens": "coupling", "NDmean": "coupling", "NDtop25": "coupling",
    "NSmean": "coupling", "ND": "coupling", "NS": "coupling",
    "MEW": "coupling", "MEW_mean": "coupling",
    "sigEdgesMean": "coupling", "sigEdgesTop10": "coupling",

    # ── Topology: what the graph looks like once you have it.
    "CC": "topology", "CC_raw": "topology", "CC_rawMean": "topology",
    "PL": "topology", "PL_raw": "topology",
    "Eglob": "topology", "Eloc": "topology", "ElocMean": "topology",
    "SW": "topology", "SWw": "topology",
    "Q": "topology", "nMod": "topology", "Ci": "topology",
    "PC": "topology", "PC_raw": "topology", "PC_residual": "topology",
    "PCmean": "topology", "PCmeanTop10": "topology",
    "PCmeanBottom10": "topology",
    "Z": "topology", "NdCartDiv": "topology",
    "percentZscoreGreaterThanZero": "topology",
    "percentZscoreLessThanZero": "topology",
    "BC": "topology", "NE": "topology",
    "Hub3": "topology", "Hub4": "topology",
    "aveControl": "topology", "aveControlMean": "topology",
    "aveControlTop25": "topology", "modalControl": "topology",
    "modalControlMean": "topology",
    "modalControlPrctLessThanThreshold": "topology",
}
# Cost-integrated topology: the same metrics measured at matched density and
# integrated over the range (see meanap.stats.density_sweep). They are topology
# by construction — the density and strength they would otherwise be confounded
# with have been thresholded away — which is what makes them worth having in the
# taxonomy at all.
for _swept in ("CC", "PL", "Eglob", "ElocMean", "BCmean", "Q", "nMod"):
    FEATURE_FAMILIES[f"{_swept}_costInt"] = "topology"
del _swept
# ``lccFraction_costInt`` is deliberately absent: how fragmented a network is
# under thresholding is a property of its weight distribution, not of its
# topology, and grouping it with the topology metrics would smuggle the
# confound back in.

# The six node-cartography roles, as proportions and as counts.
for _role in range(1, 7):
    FEATURE_FAMILIES[f"NCpn{_role}"] = "topology"
    FEATURE_FAMILIES[f"NCpn{_role}count"] = "topology"
del _role


def family_of(metric: str, overrides: dict | None = None) -> str:
    """The family *metric* belongs to, or ``"other"`` if it is not classified."""
    if overrides and metric in overrides:
        return overrides[metric]
    return FEATURE_FAMILIES.get(metric, "other")


@dataclass
class FamilyShapley:
    """Per-age contribution of each feature family to decoding performance."""

    #: One row per (age, family): its Shapley share, what it achieves alone,
    #: and what only it contributes.
    table: pd.DataFrame
    #: One row per age: the decodability the families partition.
    totals: pd.DataFrame
    #: One row per metric: which family it was placed in.
    membership: pd.DataFrame = field(default_factory=pd.DataFrame)
    families: list[str] = field(default_factory=list)
    target: str = "Grp"
    model: str = "lda"
    lag: object = None

    def across_ages(self, column: str = "Shapley") -> pd.DataFrame:
        """Families as rows, ages as columns."""
        if self.table.empty:
            return pd.DataFrame()
        return self.table.pivot_table(index="Family", columns="DIV", values=column)


def _exact_shapley(value, n_players: int) -> np.ndarray:
    """Shapley values by enumeration — exact, and cheap for a handful of players.

    With three or four families there are only 8 or 16 subsets, so there is no
    reason to sample orderings as the per-feature decomposition must. Every
    subset is scored once and the weighted marginal contributions are summed in
    closed form.
    """
    from itertools import combinations
    from math import factorial

    players = range(n_players)
    shapley = np.zeros(n_players)
    for i in players:
        others = [p for p in players if p != i]
        for size in range(len(others) + 1):
            weight = factorial(size) * factorial(n_players - size - 1) / factorial(n_players)
            for subset in combinations(others, size):
                shapley[i] += weight * (value(tuple(sorted(subset + (i,))))
                                        - value(tuple(sorted(subset))))
    return shapley


def family_shapley(
    ds: StatsDataset,
    *,
    target: str | None = None,
    metrics: list[str] | None = None,
    family_overrides: dict | None = None,
    n_splits: int = 5,
    model: str = "lda",
    seed: int = 0,
    lag=None,
    progress=None,
) -> FamilyShapley:
    """How much each feature family contributes to decoding *target*, per age.

    The families are the players, so their Shapley values sum to that age's
    decodability exactly as the per-feature ones do. Alongside each, ``Alone``
    is what the family achieves on its own and ``Unique`` is what is lost by
    removing it from the full set — together they bracket the Shapley value and
    say whether a family is carrying its own signal or sharing one.
    """
    target = target or ds.group_col
    names = list(metrics or ds.metrics)

    membership = pd.DataFrame({
        "Feature": names,
        "FeatureLabel": [ds.label(n) for n in names],
        "Family": [family_of(n, family_overrides) for n in names],
    })
    membership["FamilyLabel"] = membership["Family"].map(
        lambda f: FAMILY_LABELS.get(f, f))

    present = [f for f in FAMILY_LABELS if f in set(membership["Family"])]
    if len(present) < 2:
        return FamilyShapley(table=pd.DataFrame(), totals=pd.DataFrame(),
                             membership=membership, target=target, model=model,
                             lag=lag)

    rows, totals = [], []
    ages = ds.ages
    for index, age in enumerate(ages):
        at_age = ds.table[ds.table[ds.age_col] == age]
        sub = ds._with_table(at_age.reset_index(drop=True))
        X, feature_names, meta = sub.feature_matrix(metrics=names)
        y = meta[target].astype(str).to_numpy()
        groups = meta[ds.culture_col].astype(str).to_numpy()
        if len(set(y)) < 2 or X.shape[0] < 10:
            continue

        # Column indices per family, for the features that survived this age's
        # row filtering — a family whose metrics are all missing here drops out
        # rather than being scored as an empty set.
        by_family = {}
        for family in present:
            columns = [i for i, name in enumerate(feature_names)
                       if family_of(name, family_overrides) == family]
            if columns:
                by_family[family] = columns
        if len(by_family) < 2:
            continue
        keys = list(by_family)

        scorer, chance = _subset_scorer(X, y, groups, n_splits=n_splits,
                                        model=model, seed=seed)
        if progress is not None:
            progress(index + 1, len(ages))
        if scorer is None:
            continue

        def value(players, _scorer=scorer, _by=by_family, _keys=keys) -> float:
            columns: list[int] = []
            for player in players:
                columns.extend(_by[_keys[player]])
            return _scorer(columns)

        shapley = _exact_shapley(value, len(keys))
        everything = tuple(range(len(keys)))
        total = value(everything)

        for position, family in enumerate(keys):
            without = tuple(p for p in everything if p != position)
            rows.append({
                "DIV": float(age), "Family": family,
                "FamilyLabel": FAMILY_LABELS.get(family, family),
                "Shapley": float(shapley[position]),
                "Alone": float(value((position,))),
                "Unique": float(total - value(without)),
                "Share": float(shapley[position] / total) if total else np.nan,
                "Total": float(total), "Chance": float(chance),
                "NFeatures": len(by_family[family]), "N": int(X.shape[0]),
            })
        totals.append({
            "DIV": float(age), "BalancedAccuracy": float(total + chance),
            "Chance": float(chance), "Total": float(total),
            "N": int(X.shape[0]), "NCultures": int(len(set(groups))),
        })

    return FamilyShapley(
        table=pd.DataFrame(rows), totals=pd.DataFrame(totals),
        membership=membership, families=present, target=target, model=model,
        lag=lag,
    )
