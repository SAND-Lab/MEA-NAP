---
key: spatiotemporal
name: Spatial and temporal autocorrelation
tab: Connectivity
labels: Spatial && temporal autocorrelation; SA / TA metrics; TA bin for events; Spatiotemporal model; Model repetitions
params: compute_spatiotemporal, ta_bin_ms, spatiotemporal_null_model, spatiotemporal_null_reps
image: spatiotemporal.png
related: recording, prob_threshold, dimensionality
---
These metrics test whether graph metrics reflect more than how coupling falls off with distance (spatial autocorrelation, SA) and how smooth each node's activity is (temporal autocorrelation, TA), after Shinn et al. (2023). They are off by default.

## What it does

**SA / TA metrics** adds, per network:

- **SA_lambda, SA_inf**: an exponential fitted to the mean **unthresholded** STTC against distance, pinned to 1 at zero distance (the paper's fit).
- **SA_lambda_free, SA_amp, SA_inf_free**: the same fit with the starting value left free.
- **TA_regional, TA_global**: each node's lag-1 autocorrelation, and the mean over nodes.

Distance is in electrode pitches on MEA data and in imaging pixels on CAT-NAP.

In the picture (synthetic data on an Axion64 grid), no pair of separate electrodes has coupling near 1, so the pinned curve (red) can only fit by making λ very short. The free fit (blue) follows the data. On MEA and calcium data, read **SA_lambda_free** as the length scale.

**TA bin for events** (default 100 ms): spike trains and calcium events have no autocorrelation of their own, so TA is computed from their counts in bins this wide. CAT-NAP traces (F, spks, denoised F) are not affected; they use each lag's own bin.

**Spatiotemporal model** builds surrogate networks from SA and TA alone, matched to the data's density and edge weights. Its scores are written as `ST_*` columns (`STrho_*` for node rankings). **Model repetitions** (default 3) sets how many model networks are averaged for each data network.

## Choosing a value

Turn SA / TA on when you want to know whether a group difference in topology could come from simpler signal properties. Turn on the model only after that, and expect it to take several times as long as the network metrics: each repetition recomputes modularity and betweenness.

## How MEA-NAP uses it

Step 4 fits SA to the raw matrix that step 3 saves beside the thresholded one. It writes the batch summary of the model, with Lin's concordance per metric, to `4B_GroupComparisons/10_SpatiotemporalModel`.

## Things to watch for

- On spike data TA mostly tracks firing rate, and the pinned SA_lambda is often an artefact of the fit. Check each network's `13_SpatialTemporalAutocorrelation` figure first.
- SA needs electrode positions, so a layout without coordinates skips it. So does an adjacency file from before raw matrices were saved; re-run step 3.

## References

- Shinn M et al. (2023) Nature Neuroscience 26:867–878. doi:10.1038/s41593-023-01299-3
