---
key: dimensionality
name: Dimensionality metrics (NMF and effective rank)
tab: Connectivity
labels: Network metrics; Network metrics  ·  NMF is switched on the CAT-NAP tab; NMF dimensionality; Effective rank; Stop NMF sweep below gain
params: compute_nmf, compute_eff_rank, nmf_plateau_gain
image: nmf_plateau.png
related: inclusion, spatiotemporal
---
Two measures of how many independent activity patterns a recording holds. Together they are most of what step 4 spends its time on, so you can switch them off.

## What it does

- **NMF dimensionality** (on by default) adds `num_nnmf_components`, `nComponentsRelNS` and the variance-explained-per-rank curve.
- **Effective rank** (on by default) adds `effRank`.

Both come from the binned spike trains of every channel, not from the network, so they have the same value in every lag folder. Every other step-4 metric is cheap and always computed.

**Stop NMF sweep below gain** (default 0.005) controls only the variance-explained curve. That curve fits one NMF per rank, up to the number of active channels. The sweep stops once variance explained passes 95%, or once the best value in the last 10 ranks beats the best before them by less than this gain. Ranks after the stop are left empty (NaN) in `nnmf_var_explained` and `nnmf_residuals`. 0 fits every rank, as MATLAB does. In the picture the sweep passes 95% at rank 51 and skips the last 9 ranks.

## Choosing a value

- Leave both on for a full analysis. NMF is the costly one: about 30 s for a 64-channel, 10-minute recording, against about 3 s for all the network metrics together.
- Switch NMF off for a quick first pass, or for spike-sorted data with hundreds of units. The NMF columns are then simply missing, and nothing else changes.
- Keep the gain at its default unless you need the whole curve, for example to compare with MATLAB. The highest ranks cost the most, so stopping early saves most of the NMF time on big arrays.

## How MEA-NAP uses it

Step 4 runs both once per recording. The number of NMF components is found by a separate search against shuffled data, so the gain does not change `num_nnmf_components` or `nComponentsRelNS`. The gain applies in CAT-NAP too.

## Things to watch for

- In CAT-NAP the group title says so: NMF is switched on the CAT-NAP tab (off by default) and effective rank is always computed, so the two checkboxes here are greyed out. The gain still applies.
- NMF uses random starts, so counts can differ by one between runs unless a seed is set.
