"""Orders for a raster's rows: which electrode (or cell) goes on which line.

A raster in recording order puts electrode 12 next to electrode 13 because of
their numbers. Sorted, rows that fire alike sit together, and structure the
numbering hides (a group of electrodes bursting together, a slow wave across
the array) shows as blocks and diagonals.

- ``"Recording order"``: the rows as recorded; the pipeline's figures.
- ``"Firing rate"``: busiest first.
- ``"Correlation"``: hierarchical clustering of the rows' activity
  (correlation distance, average linkage), with the leaves ordered so that
  neighbouring rows are as alike as possible (Bar-Joseph et al. 2001).
- ``"Rastermap"``: Rastermap's embedding (Stringer et al. 2024, *Nature
  Neuroscience*), when the ``rastermap`` package is installed. It sorts rows so
  that ones active in sequence sit in sequence, not only ones active together.

Rows with no activity at all go last, in recording order: no measure of
likeness means anything for them.
"""

from __future__ import annotations

import numpy as np

__all__ = ["RASTER_ORDERS", "available_orders", "order_rows", "order_description"]

RASTER_ORDERS = ("Recording order", "Firing rate", "Correlation", "Rastermap")


def rastermap_available() -> bool:
    try:
        import rastermap  # noqa: F401
    except ImportError:
        return False
    return True


def available_orders() -> list[str]:
    """The orders this installation can compute."""
    return [o for o in RASTER_ORDERS if o != "Rastermap" or rastermap_available()]


def order_description(order: str) -> str:
    """What the rows are sorted by, for the axis label; ``""`` unsorted."""
    return {"Firing rate": "sorted by firing rate",
            "Correlation": "sorted by correlation clustering",
            "Rastermap": "sorted by Rastermap"}.get(order, "")


def order_rows(counts: np.ndarray, order: str = "Recording order") -> np.ndarray:
    """A permutation of ``range(len(counts))``: the row drawn on each line.

    *counts* is the raster's ``(rows, bins)`` matrix.
    """
    counts = np.asarray(counts, dtype=float)
    n = len(counts)
    every = np.arange(n)
    if order == "Recording order" or n < 3:
        return every
    if order not in RASTER_ORDERS:
        raise ValueError(f"Unknown raster order {order!r}: one of {list(RASTER_ORDERS)}")
    total = np.nansum(counts, axis=1)
    varies = np.nanstd(counts, axis=1) > 0
    if order == "Firing rate":
        return np.argsort(-total, kind="stable")
    active, silent = every[varies], every[~varies]
    if len(active) < 3:
        return np.concatenate([active[np.argsort(-total[active], kind="stable")], silent])
    if order == "Correlation":
        ranked = _correlation_order(counts[active])
    else:
        ranked = _rastermap_order(counts[active])
    return np.concatenate([active[ranked], silent])


def _correlation_order(x: np.ndarray) -> np.ndarray:
    from scipy.cluster.hierarchy import leaves_list, linkage, optimal_leaf_ordering
    from scipy.spatial.distance import pdist

    distance = np.nan_to_num(pdist(x, metric="correlation"), nan=1.0)
    distance = np.clip(distance, 0.0, 2.0)
    tree = linkage(distance, method="average")
    return leaves_list(optimal_leaf_ordering(tree, distance))


def _rastermap_order(x: np.ndarray) -> np.ndarray:
    if not rastermap_available():
        raise ValueError("Sorting by Rastermap needs the rastermap package "
                         "(pip install rastermap)")
    from rastermap import Rastermap

    rows, bins = x.shape
    kwargs = dict(n_PCs=max(2, min(200, rows - 1, bins - 1)),
                  n_clusters=max(2, min(100, rows // 2)), locality=0.75, time_lag_window=5)
    try:
        model = Rastermap(**kwargs)
    except TypeError:            # an older release without some of these
        model = Rastermap(n_PCs=kwargs["n_PCs"], n_clusters=kwargs["n_clusters"])
    model.fit(x.astype(np.float32))
    return np.asarray(model.isort, dtype=int)
