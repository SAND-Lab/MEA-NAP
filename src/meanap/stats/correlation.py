"""Which metrics measure the same thing? — the port of ``featureCorrelation.m``.

MATLAB draws a grid of correlation heatmaps, one per group x DIV, and stops
there. The heatmaps are kept, and three things are added, because the question
a correlation matrix is usually being asked is not "what is r for this pair"
but "how many independent things am I actually measuring, and which of my 50
columns are duplicates of each other":

* **Spearman by default.** Several of these metrics are proportions bounded at
  0 and 1 (the node-cartography percentages), several are counts, and small-
  worldness has heavy tails. Pearson r on those measures the outliers.
* **A clustered ordering.** Correlation matrices in metric-file order show
  nothing; ordered by hierarchical clustering on correlation distance, blocks
  of redundant metrics become visible, and the ordering is reused across every
  group x age panel so the panels can be compared.
* **Effective dimensionality.** The participation ratio of the correlation
  matrix's eigenvalue spectrum — roughly, how many uncorrelated metrics this
  set of metrics is worth. It is the number to quote when asked whether it is
  fair to run 50 tests, and it is the thing the redundancy blocks imply.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from meanap.stats.dataset import StatsDataset

__all__ = [
    "CorrelationResults",
    "analyse_correlation",
    "correlation_matrix",
    "cluster_order",
    "effective_dimensionality",
    "redundant_pairs",
]


@dataclass
class CorrelationResults:
    """Correlation structure overall and split by group and age."""

    #: Correlation matrix over all recordings, features in clustered order.
    overall: pd.DataFrame
    #: ``(group, age) -> DataFrame`` in the same feature order as *overall*.
    per_cell: dict = field(default_factory=dict)
    #: Feature order used everywhere, from clustering *overall*.
    order: list[str] = field(default_factory=list)
    #: Long table of feature pairs above the redundancy threshold.
    redundant: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: PCA of the standardised feature matrix.
    variance_explained: pd.DataFrame = field(default_factory=pd.DataFrame)
    loadings: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Participation ratio of the correlation eigenvalue spectrum.
    effective_dim: float = float("nan")
    method: str = "spearman"
    lag: object = None


def correlation_matrix(
    frame: pd.DataFrame, metrics: list[str], *, method: str = "spearman",
    min_pairs: int = 5,
) -> pd.DataFrame:
    """Pairwise correlations, computed on each pair's own complete rows.

    Pairwise rather than listwise deletion: dropping every recording that is
    missing any of 50 metrics can cost most of the dataset to save a column
    nobody asked about. Pairs with fewer than *min_pairs* observations are NaN
    rather than a correlation computed from three points.
    """
    cols = [m for m in metrics if m in frame.columns]
    data = frame[cols].apply(pd.to_numeric, errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan)
    corr = data.corr(method=method, min_periods=min_pairs)
    return corr


def cluster_order(corr: pd.DataFrame) -> list[str]:
    """Feature order from average-linkage clustering on correlation distance.

    Distance is ``1 - |r|``, so a metric and its negative image (path length and
    global efficiency, say) cluster together — they are the same measurement
    with a sign, and for the question "am I measuring one thing twice" they
    should sit in one block.
    """
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import squareform

    names = list(corr.columns)
    if len(names) < 3:
        return names
    dist = 1.0 - corr.abs().to_numpy(dtype=float)
    dist = np.nan_to_num(dist, nan=1.0)
    dist = (dist + dist.T) / 2.0
    np.fill_diagonal(dist, 0.0)
    try:
        link = linkage(squareform(dist, checks=False), method="average")
        return [names[i] for i in leaves_list(link)]
    except (ValueError, MemoryError):
        return names


def effective_dimensionality(corr: pd.DataFrame) -> float:
    """Participation ratio ``(sum lambda)^2 / sum lambda^2`` of the spectrum.

    Equals the number of features when they are mutually uncorrelated, and 1
    when they are all the same measurement. Between those, it is the count of
    genuinely independent measurements the feature set contains.
    """
    mat = corr.to_numpy(dtype=float)
    mat = np.nan_to_num(mat, nan=0.0)
    np.fill_diagonal(mat, 1.0)
    eig = np.linalg.eigvalsh((mat + mat.T) / 2.0)
    eig = eig[eig > 0]
    if eig.size == 0:
        return float("nan")
    return float(eig.sum() ** 2 / (eig ** 2).sum())


def redundant_pairs(corr: pd.DataFrame, threshold: float = 0.9) -> pd.DataFrame:
    """Feature pairs correlated above *threshold* in absolute value.

    The practical output of this whole module: these are the columns that carry
    one piece of information between them, and a decoder given all of them will
    split that information's importance arbitrarily across the pair.
    """
    rows = []
    names = list(corr.columns)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r) and abs(r) >= threshold:
                rows.append({"FeatureA": a, "FeatureB": b, "r": float(r)})
    out = pd.DataFrame(rows, columns=["FeatureA", "FeatureB", "r"])
    if not out.empty:
        out = out.reindex(out["r"].abs().sort_values(ascending=False).index)
    return out.reset_index(drop=True)


def _pca(ds: StatsDataset, metrics: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Explained-variance table and component loadings of the feature matrix."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    X, names, _ = ds.feature_matrix(metrics=metrics)
    if X.shape[0] < 3 or X.shape[1] < 2:
        return pd.DataFrame(), pd.DataFrame()
    Xs = StandardScaler().fit_transform(X)
    pca = PCA().fit(Xs)
    ratio = pca.explained_variance_ratio_
    var = pd.DataFrame({
        "Component": np.arange(1, len(ratio) + 1),
        "VarianceExplained": ratio,
        "CumulativeVariance": np.cumsum(ratio),
    })
    loadings = pd.DataFrame(
        pca.components_[:min(10, len(ratio))].T,
        index=names,
        columns=[f"PC{i + 1}" for i in range(min(10, len(ratio)))],
    )
    return var, loadings


def analyse_correlation(
    ds: StatsDataset,
    *,
    metrics: list[str] | None = None,
    method: str = "spearman",
    redundancy_threshold: float = 0.9,
    lag=None,
) -> CorrelationResults:
    """Correlation structure of *ds*'s features, overall and per group x age."""
    names = list(metrics or ds.metrics)
    overall = correlation_matrix(ds.table, names, method=method)
    # Metrics that correlate with nothing (all-NaN row) carry no structure and
    # would only widen every heatmap; drop them from the ordering.
    keep = [c for c in overall.columns if overall[c].notna().sum() > 1]
    overall = overall.loc[keep, keep]
    order = cluster_order(overall)
    overall = overall.loc[order, order]

    per_cell: dict = {}
    for grp in ds.groups:
        for age in ds.ages:
            mask = ((ds.table[ds.group_col] == grp)
                    & (ds.table[ds.age_col] == age))
            sub = ds.table[mask]
            if len(sub) < 5:
                continue
            cell = correlation_matrix(sub, order, method=method)
            per_cell[(str(grp), float(age))] = cell.reindex(index=order, columns=order)

    var, loadings = _pca(ds, order)
    return CorrelationResults(
        overall=overall, per_cell=per_cell, order=order,
        redundant=redundant_pairs(overall, redundancy_threshold),
        variance_explained=var, loadings=loadings,
        effective_dim=effective_dimensionality(overall),
        method=method, lag=lag,
    )
