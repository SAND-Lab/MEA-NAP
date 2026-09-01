"""Step 5: statistical comparison, feature structure, and decoding.

The MATLAB pipeline's last analysis stage (``doStats``, ``featureCorrelation``,
``doLDA``, ``doClassification``, called from ``MEApipeline.m``) asks four
questions of a finished run's metric tables:

1. **Comparison** — does a metric differ by age or by genotype?
   (:mod:`meanap.stats.comparisons`)
2. **Structure** — which metrics measure the same thing?
   (:mod:`meanap.stats.correlation`)
3. **Decoding** — can genotype or age be read back out of the features?
   (:mod:`meanap.stats.decoding`)
4. **Attribution** — which features carry that information, and how much of a
   metric's variance does each explain? (:mod:`meanap.stats.regression`)

Question 4 has no MATLAB counterpart. The others do, and differ from it in one
substantive way, described in :mod:`meanap.stats.dataset`: recordings from the
same culture are treated as repeated measures throughout, both in the models
and in the cross-validation splits.

:func:`meanap.stats.run.run_stats` runs all four over a run's output folder or
bundle and writes ``5_StatsAndML/``.
"""

from meanap.stats.dataset import StatsDataset, load_dataset

__all__ = ["StatsDataset", "load_dataset"]
