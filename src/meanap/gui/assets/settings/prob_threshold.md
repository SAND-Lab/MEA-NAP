---
key: prob_threshold
name: Probabilistic thresholding
tab: Connectivity
labels: Probabilistic thresholding; Iterations; Tail percentile; Plot random checks; Number of checks to plot; Threshold correlations
params: prob_thresh_rep_num, prob_thresh_tail, prob_thresh_plot_checks, prob_thresh_plot_checks_n, twop_corr_prob_thresh
image: prob_threshold.png
related: sttc, inclusion, adjacency
---
Probabilistic thresholding keeps an edge only if its STTC is higher than chance would give for those two spike trains.

## What it does

For each recording and each lag, MEA-NAP makes **Iterations** surrogate datasets (default 200). In each surrogate, **every** channel's spike train is shifted in time by its own random offset, and spikes that run past the end wrap round to the start. This keeps each channel's own firing pattern but breaks the timing between channels. The STTC is computed again on every surrogate.

For each pair, the cut-off is the surrogate value at the 1 − **Tail percentile** quantile (default 0.05, so the 95th percentile). An edge whose real STTC falls below the cut-off is set to 0. Edges that pass keep their STTC as their weight.

## Choosing a value

- **Iterations**: 200 is a good default. Use 500–1000 for a smaller tail, so the cut-off is not set by just a few surrogates (at a tail of 0.01 and 200 iterations, the cut-off is the third-highest surrogate). This is the slowest part of a run: step 3 takes about as long as the number of iterations.
- **Tail percentile**: lower it (for example to 0.01) for sparser networks with fewer chance edges. Raise it for denser ones.
- **Plot random checks** saves a figure to `3_EdgeThresholdingCheck`. It shows how the cut-offs settle as iterations accumulate, so you can see whether you ran enough.
- **Threshold correlations** appears only for CAT-NAP trace measures. It applies the same test to binned Pearson correlations. Off keeps the whole correlation matrix, negative edges included, as before CAT-NAP 1.9.0.

## How MEA-NAP uses it

Step 3 saves both matrices. Step 4 calculates every network metric from the thresholded one, and the spatial autocorrelation from the raw one.

## Things to watch for

- Every pair is tested on its own, with no correction for multiple comparisons, so expect about tail × pairs edges to pass by chance.
- The test is one-sided, so negative correlations never survive.
- Surrogates are random. Set a fixed seed on the Run tab to get the same edges every time.
- The Python pipeline ignores **Number of checks to plot**. With Plot random checks on, it draws a check for every recording and every lag, not for a random few as MATLAB does.
