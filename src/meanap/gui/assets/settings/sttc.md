---
key: sttc
name: Spike time tiling coefficient (STTC)
tab: Connectivity
labels: Spike time tiling coefficient (STTC); Lag values (ms)
params: func_con_lag_val
image: sttc.png
related: prob_threshold, inclusion, truncation
---
The lag Δt is the coincidence window: how close in time two spikes must be to count as correlated. Each lag you list gives its own network and its own set of network metrics.

## What it does

For each pair of electrodes, the STTC (Cutts & Eglen 2014) asks what fraction of A's spikes fall within ±Δt of one of B's spikes, and B's of A's. It then corrects each fraction for how much of the recording the other train's ±Δt tiles cover anyway. Because of that correction, a high firing rate alone does not give a high STTC, and long silent stretches are not counted as correlation. The picture shows a lag of 25 ms. Blue spikes have a partner in the other train and grey ones do not. The STTC printed above it was computed by MEA-NAP's own function.

## Choosing a value

The default is **10, 15, 25** ms for MEA-NAP and **1000, 2500, 5000** ms for CAT-NAP, where calcium signals are about a hundred times slower.

- **Short lags** (about 10–25 ms) pick up tight, near-synchronous coupling, the kind most likely to reflect direct connections.
- **Longer lags** (about 50–150 ms) also pick up coupling that goes through neurons the electrodes do not see, and the slower co-activation inside network bursts.
- STTC rises with the lag, so networks become denser at longer lags. Compare recordings at the same lag, never across lags.
- Each extra lag adds a full set of step-3 surrogates and step-4 metrics, so the run time grows in proportion to the number of lags.

## How MEA-NAP uses it

Step 3 computes the STTC for every pair at each lag, setting negative values to 0. Each matrix is then tested against surrogates (see Probabilistic thresholding). Step 4 computes every network metric once per lag and writes the results into per-lag folders. The cartography lags are a separate setting.

## Things to watch for

- Changing mode between MEA-NAP and CAT-NAP swaps the lags for the other mode's defaults, but only if you had not edited them.
- In CAT-NAP, with a trace measure (F, spks, denoised F), this box becomes **Correlation binning / Bin length (ms)**. The values are then bin widths for a Pearson correlation, not STTC lags.
- Lags are whole milliseconds, separated by commas.

## References

- Cutts CS, Eglen SJ (2014) Journal of Neuroscience 34:14288–14303. doi:10.1523/JNEUROSCI.2767-14.2014
