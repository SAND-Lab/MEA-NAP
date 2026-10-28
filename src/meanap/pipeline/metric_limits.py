"""The range each plotted metric can take *in principle*, for clipping KDEs.

A half-violin's density is evaluated a few bandwidths past the data on either
side, as MATLAB's ``ksdensity`` does, so it tails off smoothly rather than
being cut at the most extreme recording. A Gaussian kernel knows nothing about
the metric, though: left alone, a density violin pokes above 1 and a firing
rate's below 0. :func:`metric_limits` is where it must stop instead.

These are *not* the y-axis ranges of
:data:`~meanap.pipeline.plotting_step4.NETMET_BOUNDS` /
:data:`~meanap.pipeline.plotting_step2.EPHYS_BOUNDS`. Those are display
choices — average controllability is drawn on [1, 1.5], but nothing stops a
node exceeding 1.5 — and clipping a density at a display choice would draw a
cliff that isn't in the data. Every entry here is a hard limit of the metric's
definition. ``None`` on a side means unbounded there.

Edge weights (STTC, or Pearson correlation in CAT-NAP) are bounded by 1, and by
0 below because both pipelines zero negative weights before any graph metric is
computed (``step4.py``, ``network_metrics.py``).
"""

from __future__ import annotations

Limits = tuple[float | None, float | None]

_NONNEG: Limits = (0, None)
_UNIT: Limits = (0, 1)
_CORR: Limits = (-1, 1)

METRIC_LIMITS: dict[str, Limits] = {
    # ── Network, recording level (step 4) ────────────────────────────────────
    "aN": _NONNEG,
    "Dens": _UNIT,
    "CC": _NONNEG,                 # normalised by a random network: unbounded above
    "CC_rawMean": _UNIT,
    "nMod": _NONNEG,
    "Q": _UNIT,                    # the best partition scores >= 0 (one module scores 0)
    "PL": _NONNEG,
    "Eglob": _UNIT,
    "SW": _NONNEG,
    "SWw": _CORR,                  # omega lies in [-1, 1]
    "effRank": (1, None),
    "num_nnmf_components": _NONNEG,
    "nComponentsRelNS": _UNIT,
    "NDmean": _NONNEG,
    "NDtop25": _NONNEG,
    "sigEdgesMean": _UNIT,
    "sigEdgesTop10": _UNIT,
    "MEW_mean": _UNIT,
    "NSmean": _NONNEG,
    "ElocMean": _UNIT,
    "PCmean": _UNIT,
    "PCmeanTop10": _UNIT,
    "PCmeanBottom10": _UNIT,
    "percentZscoreGreaterThanZero": (0, 100),
    "percentZscoreLessThanZero": (0, 100),
    "NCpn1": _UNIT,
    "NCpn2": _UNIT,
    "NCpn3": _UNIT,
    "NCpn4": _UNIT,
    "NCpn5": _UNIT,
    "NCpn6": _UNIT,
    "aveControlMean": (1, None),   # trace of the Gramian includes the identity term
    "modalControlMean": _UNIT,
    "SA_lambda": _NONNEG,
    "SA_inf": _CORR,
    "TA_global": _CORR,
    # ── Network, node level ──────────────────────────────────────────────────
    "ND": _NONNEG,
    "NDnorm": _UNIT,               # degree / (active cells - 1)
    "NDnorm": _UNIT,               # degree / (active cells - 1)
    "MEW": _UNIT,
    "NS": _NONNEG,
    "Eloc": _UNIT,
    "BC": _UNIT,
    "PC": _UNIT,
    "NE": _UNIT,
    "CC_raw": _UNIT,
    "WithinGroupStrengthFrac": _UNIT,
    "aveControl": (1, None),
    "modalControl": _UNIT,
    "TA_regional": _CORR,
    # ── Spiking activity (step 2) ────────────────────────────────────────────
    "numActiveElec": _NONNEG,
    "FRmean": _NONNEG,
    "FRmedian": _NONNEG,
    "FRiqr": _NONNEG,
    "NBurstRate": _NONNEG,
    "meanNumChansInvolvedInNbursts": _NONNEG,
    "meanNBstLengthS": _NONNEG,
    "meanISIWithinNbursts_ms": _NONNEG,
    "meanISIoutsideNbursts_ms": _NONNEG,
    "CVofINBI": _NONNEG,
    "fracInNburst": _UNIT,
    "channelAveBurstRate": _NONNEG,
    "channelAveBurstDur": _NONNEG,
    "channelAveISIwithinBurst": _NONNEG,
    "channelAveISIoutsideBurst": _NONNEG,
    "channelAveFracSpikesInBursts": _UNIT,
    "FR": _NONNEG,
    "FRactive": _NONNEG,
    "channelBurstRate": _NONNEG,
    "channelWithinBurstFr": _NONNEG,
    "channelBurstDur": _NONNEG,
    "channelISIwithinBurst": _NONNEG,
    "channeISIoutsideBurst": _NONNEG,
    "channelFracSpikesInBursts": _UNIT,
    # ── Calcium-imaging activity (CAT-NAP) ───────────────────────────────────
    "ISImean": _NONNEG,
    "ISI": _NONNEG,
    "recPeakDurMean": _NONNEG,
    "unitPeakDurMean": _NONNEG,
    # Event heights/areas are left unbounded: not established to be >= 0 for
    # every trace. The FR family above is non-negative for peaks and spks only;
    # the CAT-NAP plotter drops its limits under the fluorescence measures
    # (see catnap.group_plots.plot_twop_group_comparisons).
    # ── Cell-type composition (CAT-NAP) ──────────────────────────────────────
    "nCells": _NONNEG,
    "fracOfCells": _UNIT,
    "nActiveCells": _NONNEG,
    "fracActive": _UNIT,
}


#: Metrics capped by how many nodes a network can have, and the cap's offset
#: from that count: a network of n nodes has at most n nodes and n modules, and
#: a node at most n − 1 neighbours — and, every weight being at most 1, at most
#: n − 1 strength.
_SIZE_CAPPED: dict[str, int] = {
    "aN": 0, "numActiveElec": 0, "nMod": 0,
    "ND": 1, "NDmean": 1, "NDtop25": 1,
    "NS": 1, "NSmean": 1,
}


def metric_limits(metric: str, max_nodes: int | None = None) -> Limits | None:
    """The theoretical ``(lo, hi)`` of *metric*, or ``None`` if unknown.

    ``max_nodes`` is the most nodes any network in the plot can have — the
    array's electrode count for a detected MEA run
    (:func:`~meanap.pipeline.channel_layout.fixed_electrode_count`), or one
    network's own size. It caps the size-dependent metrics, which are otherwise
    unbounded above.
    """
    limits = METRIC_LIMITS.get(metric)
    if limits is None or max_nodes is None or metric not in _SIZE_CAPPED:
        return limits
    return (limits[0], max_nodes - _SIZE_CAPPED[metric])
