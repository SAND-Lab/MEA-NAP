"""How much of a target does each feature explain? — no MATLAB counterpart.

``doClassification`` ranks features by how much a classifier gets worse without
them, which answers "is this feature useful to this model" but not "how much of
the variance does this feature account for". The second question is the one
usually being asked of a metric table, and it is harder, because these features
are heavily correlated — the effective dimensionality of the ~50 recording-level
metrics on the Yin timecourse is about 5 (see :mod:`meanap.stats.correlation`).
Under that much collinearity a regression coefficient, and a single-model
importance, are close to arbitrary: swap two features that correlate at 0.99 and
the credit moves wholly from one to the other.

So this module reports three numbers per feature, which together say something a
single number cannot:

``Marginal``
    R² of that feature alone. What it explains ignoring every other feature —
    its ceiling.
``Unique``
    The drop in R² from removing it from the full model. What *only* it
    explains — its floor, and near zero for any feature with a near-duplicate.
``Shapley``
    Its average marginal contribution over feature orderings — the LMG
    decomposition. This is the number to quote: unlike the other two it is
    never negative, and the Shapley values sum exactly to the full model's R²,
    so each is a genuine share of explained variance.

A feature with high ``Marginal`` and near-zero ``Unique`` is not unimportant; it
is redundant, and its ``Shapley`` value shows the share it splits with its
duplicates. Reading ``Unique`` alone is the standard way to wrongly conclude
that none of a set of correlated predictors matters.

The predictive numbers (``r2_cv``, permutation importance) are separately
cross-validated with cultures held out whole, exactly as in
:mod:`meanap.stats.decoding`; the decomposition itself is in-sample, which is
what a variance decomposition is.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from meanap.stats.dataset import StatsDataset

__all__ = [
    "RegressionResults",
    "REGRESSION_MODELS",
    "regress",
    "variance_decomposition",
]

#: Regressors offered, in presentation order. Ridge first because it is the one
#: whose coefficients are reported: with collinear features OLS coefficients
#: have enormous variance, and ridge is the standard remedy. The forest is there
#: because a monotone-but-not-linear relation to age (most of these metrics
#: saturate) is exactly what a linear model underestimates.
REGRESSION_MODELS = ("ridge", "elasticNet", "randomForest", "gradientBoosting")


def build_regressors(names=REGRESSION_MODELS, *, seed: int = 0) -> dict:
    """Named scikit-learn regression pipelines, each standardising its inputs."""
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import ElasticNetCV, RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    factories = {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-3, 4, 40)),
        "elasticNet": lambda: ElasticNetCV(
            l1_ratio=[0.1, 0.5, 0.9, 1.0], max_iter=20000, random_state=seed),
        "randomForest": lambda: RandomForestRegressor(
            n_estimators=500, random_state=seed, n_jobs=-1),
        "gradientBoosting": lambda: GradientBoostingRegressor(random_state=seed),
    }
    return {
        name: Pipeline([("scale", StandardScaler()), ("model", factories[name]())])
        for name in names if name in factories
    }


@dataclass
class RegressionResults:
    """Cross-validated prediction of a continuous target, plus attribution."""

    #: One row per (model, repeat, fold): out-of-fold R² and RMSE.
    scores: pd.DataFrame
    #: One row per (model, recording): observed and out-of-fold predicted value.
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: One row per (model, feature): held-out permutation importance, as the
    #: drop in R² when that feature is shuffled.
    importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: One row per feature: Marginal / Unique / Shapley shares of R².
    decomposition: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Standardised ridge coefficients, in SD of target per SD of feature.
    coefficients: pd.DataFrame = field(default_factory=pd.DataFrame)
    target: str = ""
    features: list[str] = field(default_factory=list)
    #: In-sample R² of the full linear model — the total the Shapley values
    #: partition.
    r2_full: float = float("nan")
    n_samples: int = 0
    n_groups: int = 0
    lag: object = None

    def summary(self) -> pd.DataFrame:
        """Mean and SD of out-of-fold R² per model, best first."""
        if self.scores.empty:
            return pd.DataFrame()
        out = (self.scores.groupby("Model")[["R2", "RMSE"]]
               .agg(["mean", "std"]).reset_index())
        out.columns = ["Model", "R2", "R2_SD", "RMSE", "RMSE_SD"]
        return out.sort_values("R2", ascending=False).reset_index(drop=True)


# ── variance decomposition ───────────────────────────────────────────────────

def _r2(X: np.ndarray, y: np.ndarray) -> float:
    """In-sample R² of the least-squares fit of *y* on *X* (with intercept).

    ``lstsq`` rather than a normal-equations solve because these design
    matrices are routinely rank-deficient — two features correlating at 0.9999
    make the Gram matrix singular — and ``lstsq``'s minimum-norm solution is
    defined anyway. The R² of a rank-deficient fit is still well-defined even
    though its coefficients are not, and R² is all this needs.
    """
    if X.size == 0 or X.shape[1] == 0:
        return 0.0
    design = np.column_stack([np.ones(len(y)), X])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    total = float(((y - y.mean()) ** 2).sum())
    if total <= 0:
        return 0.0
    return float(1.0 - (resid ** 2).sum() / total)


def variance_decomposition(
    X: np.ndarray, y: np.ndarray, feature_names: list[str], *,
    n_orderings: int = 200, seed: int = 0, progress=None,
) -> tuple[pd.DataFrame, float]:
    """Marginal, unique, and Shapley (LMG) shares of R² for each feature.

    The Shapley value of feature *j* is its average increase in R² over all
    orderings in which the features could be entered. There are ``p!`` of them,
    so it is estimated from *n_orderings* random ones — the standard Monte
    Carlo LMG estimator. Its error falls as ``1/sqrt(n_orderings)`` and 200 is
    ample for ranking 50 features; raise it if two features need separating.

    Returns the per-feature table and the full model's R², which the Shapley
    column sums to (up to Monte Carlo error).
    """
    n, p = X.shape
    rng = np.random.default_rng(seed)
    r2_full = _r2(X, y)

    marginal = np.array([_r2(X[:, [j]], y) for j in range(p)])
    unique = np.array([
        r2_full - _r2(X[:, [k for k in range(p) if k != j]], y) for j in range(p)
    ])

    shapley = np.zeros(p)
    for i in range(n_orderings):
        order = rng.permutation(p)
        previous = 0.0
        for position in range(p):
            current = _r2(X[:, order[:position + 1]], y)
            shapley[order[position]] += current - previous
            previous = current
        if progress is not None:
            progress(i + 1, n_orderings)
    shapley /= n_orderings

    table = pd.DataFrame({
        "Feature": feature_names,
        "Marginal": marginal,
        "Unique": np.clip(unique, 0.0, None),
        "Shapley": shapley,
        "ShapleyShare": shapley / r2_full if r2_full > 0 else np.nan,
    })
    return table.sort_values("Shapley", ascending=False).reset_index(drop=True), r2_full


# ── the run ──────────────────────────────────────────────────────────────────

def _grouped_splits(groups, *, n_splits: int, n_repeats: int, seed: int):
    """Repeated k-fold splits that keep each culture wholly in one fold."""
    from sklearn.model_selection import GroupKFold

    groups = np.asarray(groups)
    usable = int(min(n_splits, len(np.unique(groups))))
    if usable < 2:
        return
    for repeat in range(n_repeats):
        splitter = GroupKFold(n_splits=usable, shuffle=True, random_state=seed + repeat)
        for fold, (train, test) in enumerate(
                splitter.split(np.zeros(len(groups)), groups=groups)):
            yield repeat, fold, train, test


def regress(
    ds: StatsDataset,
    *,
    target: str | None = None,
    models=REGRESSION_MODELS,
    metrics: list[str] | None = None,
    n_splits: int = 5,
    n_repeats: int = 5,
    n_orderings: int = 200,
    importance_repeats: int = 10,
    seed: int = 0,
    lag=None,
    progress=None,
) -> RegressionResults:
    """Predict a continuous *target* from the features and attribute its variance.

    *target* defaults to age. It may also be any metric column, which turns this
    into "what explains this metric" — the way to ask, say, which activity
    features account for a network metric. A metric used as the target is
    excluded from its own predictors.
    """
    from sklearn.base import clone
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import mean_squared_error, r2_score

    target = target or ds.age_col
    names = list(metrics or ds.metrics)
    if target in names:
        names.remove(target)

    # The target has to survive the same row filtering as the features, so it
    # rides along as a feature column and is split off afterwards.
    X_all, feature_names, meta = ds.feature_matrix(metrics=names + [target])
    if target not in feature_names:
        # Dropped as constant or all-missing: nothing to predict.
        return RegressionResults(scores=pd.DataFrame(), target=target)
    target_idx = feature_names.index(target)
    y = X_all[:, target_idx]
    X = np.delete(X_all, target_idx, axis=1)
    feature_names = [f for i, f in enumerate(feature_names) if i != target_idx]
    groups = meta[ds.culture_col].astype(str).to_numpy()

    if X.shape[0] < 20 or X.shape[1] < 2 or np.std(y) == 0:
        return RegressionResults(scores=pd.DataFrame(), target=target,
                                 features=feature_names, n_samples=X.shape[0])

    splits = list(_grouped_splits(groups, n_splits=n_splits, n_repeats=n_repeats,
                                  seed=seed))
    built = build_regressors(models, seed=seed)

    score_rows, importance_rows, pred_rows = [], [], []
    oof = {name: np.full(len(y), np.nan) for name in built}
    total = len(built) * len(splits)
    done = 0
    for name, template in built.items():
        for repeat, fold, train, test in splits:
            model = clone(template)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(X[train], y[train])
                pred = model.predict(X[test])
            score_rows.append({
                "Model": name, "Repeat": repeat, "Fold": fold,
                "R2": float(r2_score(y[test], pred)),
                "RMSE": float(np.sqrt(mean_squared_error(y[test], pred))),
                "NTrain": len(train), "NTest": len(test),
            })
            if repeat == 0:
                oof[name][test] = pred
                if importance_repeats:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        imp = permutation_importance(
                            model, X[test], y[test], scoring="r2",
                            n_repeats=importance_repeats, random_state=seed + fold,
                            n_jobs=-1)
                    importance_rows.extend(
                        {"Model": name, "Feature": f, "Drop": float(v)}
                        for f, v in zip(feature_names, imp.importances_mean))
            done += 1
            if progress is not None:
                progress(done, total)

    for name, preds in oof.items():
        pred_rows.append(pd.DataFrame({
            "Model": name, ds.name_col: meta[ds.name_col].to_numpy(),
            ds.culture_col: groups, "Observed": y, "Predicted": preds,
        }))

    importance = pd.DataFrame(importance_rows)
    if not importance.empty:
        importance = (importance.groupby(["Model", "Feature"])["Drop"]
                      .agg(["mean", "std"]).reset_index()
                      .rename(columns={"mean": "Importance", "std": "SD"}))
        importance["FeatureLabel"] = importance["Feature"].map(ds.label)
        importance = importance.sort_values(
            ["Model", "Importance"], ascending=[True, False]).reset_index(drop=True)

    decomposition, r2_full = variance_decomposition(
        X, y, feature_names, n_orderings=n_orderings, seed=seed)
    decomposition["FeatureLabel"] = decomposition["Feature"].map(ds.label)

    return RegressionResults(
        scores=pd.DataFrame(score_rows),
        predictions=pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame(),
        importance=importance, decomposition=decomposition,
        coefficients=_ridge_coefficients(X, y, feature_names, ds),
        target=target, features=feature_names, r2_full=r2_full,
        n_samples=X.shape[0], n_groups=len(set(groups)), lag=lag,
    )


def _ridge_coefficients(X, y, feature_names, ds: StatsDataset) -> pd.DataFrame:
    """Standardised ridge coefficients of the full model.

    Reported alongside the decomposition because a share of variance has no
    sign: the decomposition says a feature explains 12% of the age variance,
    and only the coefficient says whether it goes up or down with age.
    """
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    ys = (y - y.mean()) / (y.std() if y.std() > 0 else 1.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ridge = RidgeCV(alphas=np.logspace(-3, 4, 40)).fit(Xs, ys)
    out = pd.DataFrame({
        "Feature": feature_names,
        "FeatureLabel": [ds.label(f) for f in feature_names],
        "Coefficient": ridge.coef_,
        "Alpha": float(ridge.alpha_),
    })
    return out.reindex(
        out["Coefficient"].abs().sort_values(ascending=False).index).reset_index(drop=True)
