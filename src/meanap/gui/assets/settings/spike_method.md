---
key: spike_method
name: Spike method for analysis
tab: Spike detection
labels: Spike method for analysis
params: spikes_method
image: sd_spike_method.png
related: wavelets, thresholds
---
Step 1 can detect spikes several ways at once. This setting picks the one result that every later step — firing rates, bursts, networks — is built from. The default is **bior1p5**.

## What it does
Each detector saves its own spike times in the recording's spike file, named after the method: `bior1p5` for the bior1.5 wavelet, `thr4` for a threshold of 4 × MAD, `thr4p5` for 4.5 × MAD, and so on (a point in the number becomes `p`). The picture shows one stretch of trace detected three ways: the methods agree on the large spikes and disagree on the small ones, so the choice changes firing rates and, through them, the networks.

`mergedAll` and `mergedWavelet` are MATLAB options that pool the spike times of all methods, or of all wavelets, into one train.

## Choosing a value
- **bior1p5** — the default and MEA-NAP's main method; finds smaller spikes than a threshold does.
- **A threshold method** (`thrN`) — simple and easy to explain; use it when you need to match an analysis that used thresholds.

Whichever you choose, it must be one that step 1 actually produced: a wavelet you selected under **Wavelet methods**, or a multiplier you listed under **Relative thresholds**.

## How MEA-NAP uses it
Steps 2, 3 and 4 (and stimulation analysis) read only this method's spike times from the spike file. The others stay in the file, so you can change this setting and rerun from step 2 without detecting again. When **Spike source** is sorting or import, this setting is ignored and the sorted units are used.

## Things to watch for
- **A method that is not in the spike file gives empty electrodes, without an error.** Every electrode then has zero spikes. Check the step-2 log line "method=…" and the firing rates.
- **The list does not match what the Python pipeline produces.** Whole-number thresholds are saved as `thr4`, `thr5`, never `thr5p0`, and `thr4`/`thr5` (the default thresholds) are not in the list. `mergedAll` and `mergedWavelet` are never produced by the Python pipeline, and `bior1p3` only if bior1.3 could run, which it cannot. In practice, use `bior1p5`, or `thr4p5`/`thr3p5` with matching thresholds.
- A method loaded from saved settings that is not in the list (such as `thr4`) is not shown; the list keeps its previous choice (`bior1p5` in a fresh window), and that is what the next run uses.
