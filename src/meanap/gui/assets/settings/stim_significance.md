---
key: stim_significance
name: Significance tests for stimulus responses
tab: Stimulation
labels: Number of shuffles; Alpha
params: stim_n_shuffles, stim_shuffle_alpha, stim_network_alpha
related: stim_windows, stim_networks
---
How MEA-Stim decides whether an electrode responded to a stimulus more often than chance, and the significance level shared by the network tests.

## What it does

Under *Shuffle significance test*, each electrode and condition gets a score: the fraction of trials in which the electrode fired more spikes in the response window than in the equally long baseline window before the stimulus (see *Response analysis windows*).

To build a null distribution, each electrode's whole spike train is shifted in time by a random amount, wrapping round the end of the recording, **Number of shuffles** times (default 500), and the score is recomputed each time. Shifting keeps the electrode's firing rate and pattern but breaks any alignment to the stimuli.

The electrode counts as responsive when its observed score is above the (1 − **Alpha**) percentile of its own null (one-tailed; default Alpha 0.05).

**Alpha** also appears under *Stimulus-triggered networks*, with the same default of 0.05. There it is the significance level for:

- network edges, where an edge needs p < Alpha;
- noise correlations;
- the trial-by-trial consistency and drift tests;
- the edges of the split-half networks. Their Mantel p-values are reported, not thresholded.

## Choosing a value

The defaults are the conventional ones. The percentile is estimated from the shuffles, so a stricter alpha needs more of them: around 1000 for Alpha 0.01, so that the threshold rests on 10 shuffles rather than 5. More shuffles take proportionally longer, and this test is most of the stimulation step's figure time.

## How MEA-NAP uses it

The test produces figure 12 for each condition:

- `12_shuffle_test_null_dist_pattern_<k>`: the observed scores against the null;
- `12_shuffle_test_sig_heatmap_pattern_<k>`: which electrodes are significant, on the array.

The random shifts are seeded from the run's random seed, so a rerun or a redraw from a bundle gives the same null.

## Things to watch for

- The result is per electrode and per condition, with no correction for testing many electrodes. Around 5 % of electrodes that do not respond will still pass at Alpha 0.05.
- The significance flag appears only in the figures, not in `StimActivity_NodeLevel.csv`.
- If the artifact window is as long as the response window or longer, the test cannot run.
