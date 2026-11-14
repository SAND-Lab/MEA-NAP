---
key: edges
name: Edges and edge weights (STTC)
also: EW
level: concept
family: network
image: EW.png
related: Dens, aN, MEW, NS, nullmodels
---
An edge is a functional connection: two electrodes whose spikes happen within a short time of each other more often than chance would predict. Its weight is their spike time tiling coefficient (STTC).

## What it measures

The **STTC** asks how often spikes on electrode A fall within ±Δt of a spike on electrode B (and B of A), corrected for how much of the recording each train covers anyway. So high firing rates alone do not produce high correlation, which matters when rates change over development. Long silent stretches do not count as "correlated".

Δt is the **lag**. Each lag in `{{param:func_con_lag_val}}` ms gives a separate network. Short lags (about 10–25 ms) favour tight, more direct coupling. Longer lags also pick up indirect coupling through neurons the electrodes cannot see.

## Reading the values

- STTC runs from −1 to 1. MEA-NAP sets negative values to 0, so edge weights (EW) run from 0 to 1.
- 1 means the two trains are always coincident within the lag, and values near 0 mean no more coincidence than chance.
- Weights tend to rise with longer lags.
- The network plots that are "scaled to the entire data batch" use a fixed edge-weight scale of 0.1 to 1.

## How MEA-NAP calculates it

1. `get_sttc` (`meanap.pipeline.sttc`) computes the STTC for every pair of channels at each lag (Cutts & Eglen 2014). Negative values and NaN are set to 0.
2. `adjm_thr` (`meanap.pipeline.probabilistic_threshold`) tests each edge against chance. It makes `{{param:prob_thresh_rep_num}}` surrogate datasets in which **each** channel's spike train is circularly shifted by its own random offset (spikes past the end wrap round to the start). This keeps each channel's firing pattern but breaks the timing between channels. The STTC is recomputed for each surrogate.
3. For each pair, the cutoff is the surrogate value at the (1 − `{{param:prob_thresh_tail}}`) quantile, so 95th percentile for a tail of 0.05. Edges whose real STTC is below the cutoff are set to 0. Surviving edges **keep their STTC value**, so the network is weighted.

Step 3 saves both the raw and the thresholded matrix. Step 4 uses the thresholded one.

**Other thresholding in MEA-NAP:**

- CAT-NAP correlation networks apply the same circular-shift test to Pearson correlations of the binned traces (`{{param:twop_corr_prob_thresh}}`).
- Stimulation networks use a trial-shuffle null (`{{param:stim_network_null}}`).
- The network-plot edge threshold (`{{param:network_plot_edge_threshold_method}}`) only controls which edges are **drawn**. It does not change any metric.

## Things to watch for

- The test is one-sided and done separately for every pair, with no correction for multiple comparisons. At a 0.05 tail, expect some false edges.
- Too few surrogates make the cutoff noisy. Turn on `{{param:prob_thresh_plot_checks}}` to see whether the threshold has stabilised.
- Surrogates are random. Set `{{param:random_seed}}` to reproduce the same edges.

## References

- Cutts CS, Eglen SJ (2014) Journal of Neuroscience 34:14288–14303. doi:10.1523/JNEUROSCI.2767-14.2014
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
