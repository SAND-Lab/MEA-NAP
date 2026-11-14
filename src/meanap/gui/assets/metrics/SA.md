---
key: SA
name: Spatial autocorrelation
also: SA_lambda, SA_inf, SA_lambda_free, SA_amp, SA_inf_free
level: recording
family: spatiotemporal
related: TA, CC, PL, Q, nullmodels
---
How functional coupling between nodes falls off with the distance between them. Shinn et al. (2023) showed that this, rather than wiring, can explain many graph metrics.

## What it measures

A curve is fitted to mean coupling against distance:

- **SA_lambda** (SA-λ): the distance over which coupling decays, as in the paper.
- **SA_inf** (SA-∞): the floor that long-range coupling settles to.
- **SA_lambda_free**, **SA_amp**, **SA_inf_free**: the same from a free-start fit. SA_amp is how far above the floor coupling starts for the closest pairs.

Units: electrode pitches on MEA (nearest neighbour = 1), imaging pixels on CAT-NAP.

## Reading the values

A larger λ means coupling reaches further. A higher floor means distant nodes are still coupled. On MEA and calcium data, read **SA_lambda_free** as the length scale and SA_amp as neighbour coupling strength.

## How MEA-NAP calculates it

`spatiotemporal_metrics` (`meanap.pipeline.spatiotemporal`), computed when the SA / TA metrics setting is on (this run: `{{param:compute_spatiotemporal}}`):

1. Takes the **unthresholded** coupling matrix (STTC, or correlation on CAT-NAP trace measures) for the network's active nodes.
2. Averages coupling over all node pairs in 20 equal-width distance bins.
3. `spatial_autocorrelation` fits corr(d) = (1 − SA-∞)·exp(−d/SA-λ) + SA-∞, which starts at 1 at zero distance.
4. `spatial_autocorrelation_nugget` fits corr(d) = SA_amp·exp(−d/λ) + SA_inf_free, with SA_amp ≥ 0 and SA_amp + SA_inf_free ≤ 1.

## Things to watch for

- Electrodes, however close, record different cells, so coupling rarely starts near 1. The pinned fit then shortens SA_lambda, mixing coupling strength with reach.
- The free fit is NaN when there is no spatial structure (SA_amp = 0), when decay ends before the nearest pair, or when coupling is still falling across the whole array.
- Everything is NaN with fewer than three distance bins, as on small 4×4 wells.
- Compare CAT-NAP values only between recordings imaged at the same zoom.
- These metrics are not in the MATLAB pipeline.

## References

- Shinn M, Hu A, Turner L et al. (2023). Functional brain networks reflect spatial and temporal autocorrelation. Nature Neuroscience 26:867–878. doi:10.1038/s41593-023-01299-3
