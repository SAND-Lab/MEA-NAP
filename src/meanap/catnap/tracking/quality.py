"""How good is a match, and how good is a chain?

Inspired by Bombcell's per-unit quality metrics, with one important difference
established by measurement rather than assumed.

**There is no useful composite score.** Combining the fingerprint with activity
agreement (event rate, inter-event interval, population coupling) was tested
against the nearest-neighbour null, cross-validated by chain over 17392
comparisons:

===================================  =====
fingerprint alone                    0.681
weighted combination of all four     0.685
equal-weighted combination           0.644
===================================  =====

The fitted weights were fingerprint 0.70 against 0.06-0.12 for the rest: the
other measures are close to redundant with it, and weighting them equally makes
the score *worse* than its best component. So the fingerprint is the score, and
the other metrics earn their place as **context for reading a match**, not as
terms in a sum.

**Spatial agreement is deliberately excluded from the score.** Footprint overlap
and centroid distance would separate matched from null beautifully, and it would
mean nothing: ROICaT matched on exactly those, and the null is by construction a
*different* cell. They are reported as description, never as evidence.

Chain quality is likewise a small vector rather than one number, because its
parts fail independently: a chain can register perfectly and match nothing, or
match plenty of cells that do not survive validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Metrics shown per cell. ``higher_is_better`` says which tail favours a match;
#: ``independent`` says whether the matcher already used it -- only independent
#: metrics are evidence that a match is real.
METRIC_SPECS: tuple[dict, ...] = (
    {"key": "fingerprint", "label": "functional fingerprint",
     "higher_is_better": True, "independent": True,
     "note": "correlation to every other tracked cell, compared across days"},
    {"key": "d_event_rate", "label": "|Δ event rate|",
     "higher_is_better": False, "independent": True,
     "note": "events per minute, absolute difference"},
    {"key": "d_iei", "label": "|Δ inter-event interval|",
     "higher_is_better": False, "independent": True,
     "note": "median interval, absolute difference"},
    {"key": "d_pop_coupling", "label": "|Δ population coupling|",
     "higher_is_better": False, "independent": True,
     "note": "correlation with the rest of the population"},
    {"key": "footprint_iou", "label": "footprint overlap",
     "higher_is_better": True, "independent": False,
     "note": "IoU: shared pixels ÷ pixels in either mask, after registration — "
             "the matcher used this, so it is description rather than evidence"},
    {"key": "centroid_shift", "label": "centroid shift",
     "higher_is_better": False, "independent": False,
     "note": "px after registration — the matcher used this, so it is "
             "description rather than evidence"},
)

#: A cell scoring below this against the null is worth looking at by eye. It is
#: a *prompt*, not a rejection: at AUC 0.68 no threshold can decide a match
#: (rejecting at a 10% false-positive rate discards ~75% of matches and still
#: leaves a third of survivors possibly wrong).
REVIEW_PERCENTILE = 50.0


@dataclass
class MetricComparison:
    """One metric for one cell, placed against the null and the matched pool."""

    key: str
    label: str
    value: float
    percentile: float            # vs the null: 100 = better than every null pair
    matched_percentile: float    # vs other matched cells
    higher_is_better: bool
    independent: bool
    note: str = ""


@dataclass
class ChainQuality:
    """A chain's quality as a vector -- its parts fail independently."""

    chain: str
    #: Fingerprint AUC against the spatial null. The separability of the
    #: matches, and the only part that is evidence they are real.
    separability: float = float("nan")
    #: Median fraction of the smaller session's cells that were matched.
    coverage: float = float("nan")
    #: Fraction of tracked cells that appear on every day of the chain.
    persistence: float = float("nan")
    #: Residual field-of-view offset after registration, in px.
    residual_shift_px: float = float("nan")
    n_cells: int = 0
    n_fingerprints: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (f"{self.chain}: separability {self.separability:.2f}, "
                f"coverage {self.coverage:.2f}, persistence {self.persistence:.2f}, "
                f"residual {self.residual_shift_px:.0f} px")


def footprint_overlap(roi_a, roi_b, offset_a=(0, 0), offset_b=(0, 0)) -> float:
    """Intersection over union of two ROI masks, after registration.

    A tight overlap and a marginal one both count as "matched", and the match
    rate cannot tell them apart; this can. It is **not evidence** — ROICaT
    matched on exactly this, so against a spatial null it separates at AUC
    0.997, which says only that the matcher did what it was asked.

    Measured on real matches: median 0.448, and no matched pair has zero
    overlap, so a value near zero is worth looking at by eye.
    """
    def pixels(roi, offset):
        ypix = np.asarray(roi["ypix"]) - int(offset[0])
        xpix = np.asarray(roi["xpix"]) - int(offset[1])
        return set(zip(ypix.tolist(), xpix.tolist()))

    a = pixels(roi_a, offset_a)
    b = pixels(roi_b, offset_b)
    if not a or not b:
        return float("nan")
    union = len(a | b)
    return len(a & b) / union if union else float("nan")


def percentile_of(value: float, pool: np.ndarray, *, higher_is_better: bool) -> float:
    """Where ``value`` sits in ``pool``, oriented so 100 always means "better"."""
    pool = np.asarray(pool, dtype=float)
    pool = pool[np.isfinite(pool)]
    if not pool.size or not np.isfinite(value):
        return float("nan")
    below = float((pool < value).mean() * 100.0)
    return below if higher_is_better else 100.0 - below


def compare_metrics(values: dict[str, float], null_pool: dict[str, np.ndarray],
                    matched_pool: dict[str, np.ndarray]) -> list[MetricComparison]:
    """Place one cell's metrics against the null and the matched population."""
    out = []
    for spec in METRIC_SPECS:
        key = spec["key"]
        if key not in values:
            continue
        out.append(MetricComparison(
            key=key,
            label=spec["label"],
            value=float(values[key]),
            percentile=percentile_of(values[key], null_pool.get(key, np.array([])),
                                     higher_is_better=spec["higher_is_better"]),
            matched_percentile=percentile_of(
                values[key], matched_pool.get(key, np.array([])),
                higher_is_better=spec["higher_is_better"]),
            higher_is_better=spec["higher_is_better"],
            independent=spec["independent"],
            note=spec["note"]))
    return out


def chain_quality(chain: str, *, fingerprint_auc: float, pair_rates: list[float],
                  cluster_spans: list[int], n_sessions: int,
                  residual_shift_px: float, n_fingerprints: int = 0) -> ChainQuality:
    """Assemble a chain's quality vector and flag what a reader should know."""
    spans = np.asarray(cluster_spans, dtype=float)
    q = ChainQuality(
        chain=chain,
        separability=float(fingerprint_auc),
        coverage=float(np.median(pair_rates)) if pair_rates else float("nan"),
        persistence=float((spans >= n_sessions).mean()) if spans.size else float("nan"),
        residual_shift_px=float(residual_shift_px),
        n_cells=int(spans.size),
        n_fingerprints=int(n_fingerprints),
    )
    if np.isfinite(q.separability) and q.separability < 0.55:
        q.warnings.append(
            "matches barely separate from a co-located different cell; treat "
            "per-cell claims as unsupported")
    if q.n_fingerprints < 50:
        q.warnings.append(
            f"only {q.n_fingerprints} fingerprints — separability is noisy here")
    if np.isfinite(q.residual_shift_px) and q.residual_shift_px > 16:
        q.warnings.append(
            f"{q.residual_shift_px:.0f} px of field-of-view offset remains; the "
            "sessions may not share a field")
    return q
