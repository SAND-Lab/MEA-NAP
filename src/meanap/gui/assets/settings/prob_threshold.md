---
key: prob_threshold
name: Probabilistic thresholding
tab: Connectivity
labels: Probabilistic thresholding; Iterations; Surrogates; Jitter window; Tail percentile; Plot random checks; Number of checks to plot; Threshold correlations
params: prob_thresh_rep_num, prob_thresh_null, prob_thresh_jitter_lags, prob_thresh_tail, prob_thresh_plot_checks, prob_thresh_plot_checks_n, twop_corr_prob_thresh
image: prob_threshold.png
related: sttc, inclusion, adjacency
---
Probabilistic thresholding keeps an edge only if its STTC is higher than chance would give for those two spike trains.

## What it does

For each recording and each lag, MEA-NAP makes **Iterations** surrogate datasets (default 200) and computes the STTC again on every one. **Surrogates** chooses how they are made:

- **Circular shift** (the default, as in MATLAB): every channel's spike train is shifted in time by its own random offset, and spikes that run past the end wrap round to the start. This keeps each channel's own firing pattern but breaks all timing between channels, slow as well as fast.
- **Interval jitter**: time is cut into fixed windows **Jitter window** × the lag long, and each spike is moved to a random time inside its own window. Every channel keeps its spike count in every window, so its bursts and slow changes in rate stay in the surrogates. Only timing finer than the window is broken.

For each pair, the cut-off is the surrogate value at the 1 − **Tail percentile** quantile (default 0.05, so the 95th percentile). An edge whose real STTC falls below the cut-off is set to 0. Edges that pass keep their STTC as their weight.

## Choosing a value

- **Surrogates**: circular shift asks "do these two channels fire together more than chance?". Shared network bursts and a rise in firing over the recording both count. Interval jitter asks "is their timing tighter than their rate profiles explain?". It gives sparser networks, and their density is less tied to firing rate. Use circular shift to compare with earlier and MATLAB runs. Use jitter when you want edges to mean precise co-firing.
- **Jitter window**: 5 × lag by default (50 ms at a 10 ms lag). Close to 1, the surrogates keep the very coincidences the STTC counts, so few edges pass. Larger windows put less slow co-activation in the null and keep more edges.
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
- Under interval jitter, network bursts whose onsets are shared to within a few ms count partly as fine timing: a sharp, shared onset *is* timing finer than the window.
- Interval jitter is Python-only. MATLAB always uses circular shifts. CAT-NAP's correlation measures also always use circular shifts; its peaks (STTC) measure follows this setting.
- The Python pipeline ignores **Number of checks to plot**. With Plot random checks on, it draws a check for every recording and every lag, not for a random few as MATLAB does.
