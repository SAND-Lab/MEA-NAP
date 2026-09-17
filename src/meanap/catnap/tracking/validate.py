"""Is a matched pair really the same cell? Ask its activity.

ROICaT matches on ROI footprint and position, so a spatial control cannot
distinguish "the same cell" from "a different cell in the same place". This
validates matches with signals the matcher never saw, after UnitMatch (van
Beest, Bimbard et al.), which validates waveform-based matches with functional
fingerprints.

**The null is what makes this work.** Matched cells are co-located by
construction, so "matched pairs agree" proves nothing on its own. The comparison
here is against each partner's **nearest spatial neighbour** -- a different
cell, in essentially the same place. Against a random null everything looks
good; against the spatial null:

=============================  ==================
measure                        AUC vs neighbour
=============================  ==================
event rate                     0.53
inter-event interval           0.54
decay time                     0.57
population coupling            0.57
**functional fingerprint**     **0.68**
=============================  ==================

Two conclusions follow, and both are load-bearing:

* The fingerprint is a **quality descriptor, not a filter**. At a 10% false
  positive rate only 22-31% of matches survive and usable chains fall from 67 to
  ~13, while the false-match bound only improves to ~33-45%. AUC 0.68 is not
  enough to accept or reject an individual match.
* The **match rate is not a per-match quality score** -- fingerprint AUC is flat
  across match-rate bins. A well-tracked chain is not reliably a well-matched one.

Neuropil: subtract ``F - neucoeff * Fneu`` because it is correct and yields more
usable cells, **not** because it changes the answer (AUC 0.681 against 0.678
uncorrected). Neighbouring cells are correlated because they share real local
network activity, not neuropil bleed -- a proxy that regressed out nearby cells
collapsed the null to +0.003 and was misread as evidence about neuropil until
the real subtraction failed to reproduce it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: suite2p's convention for neuropil correction.
NEUCOEFF = 0.7

#: A fingerprint needs enough other tracked cells to correlate against.
MIN_REFERENCE_CELLS = 6


@dataclass
class SessionActivity:
    """One recording's activity, reduced to what validation needs."""

    corr: np.ndarray          # (n, n) cell-by-cell correlation
    pop_coupling: np.ndarray  # (n,)
    centroids: np.ndarray     # (n, 2), for the spatial null
    event_rate: np.ndarray | None = None
    median_iei: np.ndarray | None = None


def correct_neuropil(F: np.ndarray, Fneu: np.ndarray, *, neucoeff: float = NEUCOEFF
                     ) -> np.ndarray:
    return F - neucoeff * Fneu


def _zscore_rows(F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Z-scored traces, and a mask of the rows that were usable.

    Degenerate rows are excluded rather than normalised. A flat or non-finite
    trace otherwise poisons everything downstream: ``nan`` defeats magnitude
    guards (``nan < 1e-9`` is False), and one bad row turns the whole of
    ``Fz @ Fz.T`` into NaN. In the Mecp2 set 2.85% of cells did this and
    silently cost 51.7% of all cells.
    """
    F = np.asarray(F, dtype=float)
    ok = np.isfinite(F).all(axis=1) & (F.std(axis=1) > 1e-9)
    Fz = np.zeros_like(F)
    if ok.any():
        good = F[ok]
        Fz[ok] = (good - good.mean(1, keepdims=True)) / good.std(1, keepdims=True)
    return Fz, ok


def reduce_session(F: np.ndarray, centroids: np.ndarray) -> SessionActivity:
    """Correlation matrix and population coupling from corrected traces."""
    Fz, ok = _zscore_rows(F)
    n, n_frames = Fz.shape
    corr = np.full((n, n), np.nan)
    if ok.any():
        sub = Fz[ok]
        corr_ok = (sub @ sub.T) / n_frames
        idx = np.nonzero(ok)[0]
        corr[np.ix_(idx, idx)] = corr_ok

    total = Fz[ok].sum(0)
    n_ok = int(ok.sum())
    pop = np.full(n, np.nan)
    for i in range(n):
        if not ok[i] or n_ok < 2:
            continue
        other = (total - Fz[i]) / (n_ok - 1)
        if other.std() > 1e-9:
            pop[i] = float(np.corrcoef(Fz[i], other)[0, 1])
    return SessionActivity(corr=corr.astype(np.float32),
                           pop_coupling=pop.astype(np.float32),
                           centroids=np.asarray(centroids, dtype=float))


def event_metrics(peak_start_frames: np.ndarray, n_frames: int, fs: float
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Event rate (per minute) and median inter-event interval (seconds)."""
    duration_min = n_frames / fs / 60.0
    rate = np.zeros(len(peak_start_frames))
    iei = np.full(len(peak_start_frames), np.nan)
    for i, row in enumerate(peak_start_frames):
        starts = np.asarray(row, dtype=float)
        starts = starts[np.isfinite(starts)]
        rate[i] = len(starts) / duration_min if duration_min > 0 else 0.0
        if len(starts) >= 3:
            iei[i] = float(np.median(np.diff(np.sort(starts))) / fs)
    return rate, iei


def nearest_other(centroids: np.ndarray, j: int) -> int:
    """Index of the cell closest to ``j`` -- the spatial null's stand-in."""
    d = np.linalg.norm(centroids - centroids[j], axis=1)
    d[j] = np.inf
    return int(np.argmin(d))


def fingerprints(
    a: SessionActivity,
    b: SessionActivity,
    index_a: dict[int, int],
    index_b: dict[int, int],
) -> list[dict]:
    """Fingerprint correlation for each matched cluster, and its spatial null.

    A cell's fingerprint is its correlation to every *other* tracked cell in the
    same session. Comparing that vector across days asks whether the cell sits
    in the same place in the network, which the matcher never looked at.
    """
    shared = sorted(set(index_a) & set(index_b))
    if len(shared) < MIN_REFERENCE_CELLS:
        return []

    out = []
    for cluster in shared:
        i, j = index_a[cluster], index_b[cluster]
        others = [c for c in shared if c != cluster]
        fa = np.array([a.corr[i, index_a[c]] for c in others], dtype=float)
        if not np.all(np.isfinite(fa)) or fa.std() < 1e-9:
            continue
        neighbour = nearest_other(b.centroids, j)
        row = {"cluster": int(cluster)}
        for kind, jj in (("matched", j), ("nearest", neighbour)):
            fb = np.array([b.corr[jj, index_b[c]] for c in others], dtype=float)
            if not np.all(np.isfinite(fb)) or fb.std() < 1e-9:
                continue
            r = float(np.corrcoef(fa, fb)[0, 1])
            if np.isfinite(r):
                row[kind] = r
        # only usable if both survived: otherwise the two distributions would
        # describe different sets of cells and the AUC would be meaningless
        if "matched" in row and "nearest" in row:
            out.append(row)
    return out


def auc_vs_null(matched: np.ndarray, null: np.ndarray) -> float:
    """P(a matched pair looks more like the same cell than a null pair).

    Oriented so >0.5 always favours the match. 0.5 is no information.
    """
    from scipy.stats import mannwhitneyu

    matched = np.asarray(matched, dtype=float)
    null = np.asarray(null, dtype=float)
    matched = matched[np.isfinite(matched)]
    null = null[np.isfinite(null)]
    if not matched.size or not null.size:
        return float("nan")
    return float(mannwhitneyu(matched, null).statistic / (matched.size * null.size))
