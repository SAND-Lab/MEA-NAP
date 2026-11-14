---
key: TA
name: Temporal autocorrelation
also: TA_regional, TA_global
level: node
family: spatiotemporal
related: SA, FR, ND, NS, Hub
---
How similar each node's activity is from one moment to the next. Shinn et al. (2023) found that in fMRI this smoothness predicts which nodes look like hubs.

## What it measures

- **TA_regional** (TA-Δ₁, per node): the correlation of a node's activity timeseries with itself shifted by one time bin, from −1 to 1.
- **TA_global** (per recording): the mean of TA_regional over the network's active nodes.

## Reading the values

Values near 1 mean activity changes slowly. Values near 0 mean each bin is unrelated to the previous one. Negative values mean busy bins tend to follow quiet ones.

## How MEA-NAP calculates it

Computed when the SA / TA metrics setting is on (this run: `{{param:compute_spatiotemporal}}`). `temporal_autocorrelation` (`meanap.pipeline.spatiotemporal`) needs a timeseries:

- **MEA spikes and CAT-NAP `peaks`:** `bin_event_times` counts events in bins of `{{param:ta_bin_ms}}` ms (a trailing partial bin is dropped). The same value applies to every lag.
- **CAT-NAP `F`, `spks`, `denoised F`:** the traces averaged into each lag's correlation bin, so TA is computed separately for each lag.

A node with no variation (silent, or a flat trace) gets NaN. `spatiotemporal_metrics` then keeps the network's active nodes and averages them for TA_global.

## Things to watch for

- On spike and event counts, TA mostly tracks firing rate. For sparse calcium events it is close to −p/(1 − p), where p = rate × bin width. Compare TA_global between groups only alongside FR.
- The diagnostic figure shows TA against degree with and without rate partialled out. Only the rate-adjusted correlation tells you something rate does not.
- TA depends on the bin width. Compare only runs that used the same `ta_bin_ms`.
- These metrics are not in the MATLAB pipeline.

## References

- Shinn M, Hu A, Turner L et al. (2023). Functional brain networks reflect spatial and temporal autocorrelation. Nature Neuroscience 26:867–878. doi:10.1038/s41593-023-01299-3
