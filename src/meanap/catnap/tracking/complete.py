"""Attach the matches ROICaT declined, when position alone settles them.

ROICaT clusters on footprint similarity and is conservative about it. Audited
over the Mecp2 run (93 chains): for every tracked cell and every day it was
missing from, what sat at its expected position in that day's ROIs?

=====================================  ======  =====
at the expected position (<= 10 px)     slots  share
=====================================  ======  =====
an iscell ROI ROICaT left unmatched     2,089   24%
an iscell ROI in another cluster          682    8%
a non-iscell ROI                          274    3%
nothing -- suite2p extracted no ROI     5,857   66%
=====================================  ======  =====

The first row is what this module recovers. Whether those ROIs really are the
same cell was asked of the activity fingerprint (``validate.py``), which the
matcher never saw, with exactly the test the accepted matches got:

=====================================  ======  =========  ========  =====
                                            n  matched    nearest   AUC
=====================================  ======  =========  ========  =====
ROICaT's accepted matches               8,603  +0.539     +0.274    0.684
declined ROIs <= 10 px from the cell    1,747  +0.543     +0.267    0.675
=====================================  ======  =========  ========  =====

Candidates against the accepted pool: AUC 0.499. They are the same population.
The rule below is deliberately strict -- **exactly one** unmatched cell within
the radius, claimed by **exactly one** cluster -- because ambiguity is rare
(66 of 2,116 slots had two candidates; 32 ROIs were claimed twice) and the
strict rule loses almost nothing while never having to guess.

What it does not do: the 66% "nothing there" slots are suite2p's detection
(a cell with no transients that day is invisible to it), and no amount of
matching fixes that. Feeding non-iscell ROIs in has a 3% ceiling and a
documented cost (tracking yield 45% -> 6% unfiltered). Neither is attempted.

The second row is the other repair here, :func:`merge_split_clusters`: one cell
that ROICaT tracked as two clusters on disjoint days (DIV21-29 as one, DIV36-44
as another) because the mask changed across the gap. Where two clusters' days
are disjoint and their positions coincide, the fingerprint across the join
scored AUC 0.695 (163 pairs; median +0.626 against a nearest-neighbour null of
+0.350) -- again as strong as ROICaT's own matches. Merging does not add
matches so much as lengthen chains, which is what a longitudinal analysis
needs.

Rescued and merged members are recorded and flagged all the way through --
result JSON, CSVs, viewer -- so a downstream analysis can leave them out.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Within-cluster spread of member positions on the Mecp2 run is 4.5 px at the
#: 90th percentile and 9 px at the 99th, and the fingerprint AUC held out to
#: 10 px (0.701 within 4 px, 0.657 at 7-10 px). Beyond that a candidate is as
#: likely a neighbour as the cell.
COMPLETION_RADIUS_PX = 10.0


@dataclass
class Rescue:
    """One cluster member added by position."""

    cluster: int
    session: int
    roi: int
    dist_px: float


def complete_clusters(
    labels: list[np.ndarray],
    centroids: list[np.ndarray],
    *,
    radius_px: float = COMPLETION_RADIUS_PX,
) -> tuple[list[np.ndarray], list[Rescue]]:
    """Add unmatched ROIs to the cluster whose expected position they sit at.

    ``labels`` are ROICaT's per-session cluster labels (-1 = unmatched) and
    ``centroids`` the matching per-session ``(n, 2)`` positions, **all in one
    common frame** -- for a registered chain that is the staged frame, for a
    passed-through one the raw positions minus the solved offsets. A cluster's
    expected position is the mean of its members'. Returns new label arrays
    (the inputs are not modified) and the list of rescues.
    """
    labels = [np.asarray(l, dtype=int).copy() for l in labels]
    members: dict[int, dict[int, int]] = {}
    for s, lab in enumerate(labels):
        for i, c in enumerate(lab):
            if c >= 0:
                members.setdefault(int(c), {})[s] = i

    # first pass: every (cluster, day) slot with exactly one unmatched
    # candidate claims it; conflicts are resolved before anything is assigned
    claims: dict[tuple[int, int], list[tuple[int, float]]] = {}
    for cluster, by_session in members.items():
        if len(by_session) < 2:
            continue
        expected = np.mean([centroids[s][i] for s, i in by_session.items()], axis=0)
        for s in range(len(labels)):
            if s in by_session or not len(centroids[s]):
                continue
            dist = np.hypot(*(np.asarray(centroids[s], dtype=float) - expected).T)
            near = np.nonzero((dist <= radius_px) & (labels[s] < 0))[0]
            if near.size != 1:
                continue        # nothing there, or two cells and no way to choose
            roi = int(near[0])
            claims.setdefault((s, roi), []).append((cluster, float(dist[roi])))

    rescues = []
    for (s, roi), claimants in claims.items():
        if len(claimants) != 1:
            continue            # two clusters want the same cell: leave it
        cluster, dist = claimants[0]
        labels[s][roi] = cluster
        rescues.append(Rescue(cluster=cluster, session=s, roi=roi, dist_px=dist))
    rescues.sort(key=lambda r: (r.cluster, r.session))
    return labels, rescues


@dataclass
class Merge:
    """Two clusters on disjoint days at one position, made one."""

    cluster: int          # the label that survives (the smaller)
    absorbed: int         # the label folded into it
    dist_px: float        # between the two clusters' mean positions


def merge_split_clusters(
    labels: list[np.ndarray],
    centroids: list[np.ndarray],
    *,
    radius_px: float = COMPLETION_RADIUS_PX,
) -> tuple[list[np.ndarray], list[Merge]]:
    """Fold together clusters that are one cell tracked in two pieces.

    Two clusters qualify when their day sets are **disjoint** (a shared day
    means two cells side by side) and their mean positions, in the common
    frame, are within ``radius_px``. Each must be the other's **only** such
    partner; a cluster with two candidates is left alone rather than guessed
    at, and so are chains of three. The surviving label is the smaller one.
    Returns new label arrays (inputs untouched) and the merges made.
    """
    labels = [np.asarray(l, dtype=int).copy() for l in labels]
    members: dict[int, dict[int, int]] = {}
    for s, lab in enumerate(labels):
        for i, c in enumerate(lab):
            if c >= 0:
                members.setdefault(int(c), {})[s] = i
    tracked = sorted(c for c, by in members.items() if len(by) >= 2)
    if len(tracked) < 2:
        return labels, []
    centre = {c: np.mean([centroids[s][i] for s, i in members[c].items()], axis=0)
              for c in tracked}
    days = {c: set(members[c]) for c in tracked}

    partners: dict[int, list[tuple[int, float]]] = {c: [] for c in tracked}
    for a_i, a in enumerate(tracked):
        for b in tracked[a_i + 1:]:
            if days[a] & days[b]:
                continue
            d = float(np.hypot(*(centre[a] - centre[b])))
            if d <= radius_px:
                partners[a].append((b, d))
                partners[b].append((a, d))

    merges = []
    for a in tracked:
        if len(partners[a]) != 1:
            continue
        b, d = partners[a][0]
        if b < a or len(partners[b]) != 1:
            continue        # handled from the smaller label, or b is ambiguous
        for s, i in members[b].items():
            labels[s][i] = a
        merges.append(Merge(cluster=a, absorbed=b, dist_px=d))
    return labels, merges
