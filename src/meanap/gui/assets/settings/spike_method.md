---
key: spike_method
name: Spike method for analysis
tab: Spike detection
labels: Spike method for analysis
params: spikes_method
image: sd_spike_method.png
related: wavelets, thresholds
---
Step 1 can detect spikes several ways at once. This setting picks the one result that every later step (firing rates, bursts, networks) is built from. The default is **bior1p5**.

## What it does
Each detector saves its own spike times in the recording's spike file, named after the method: `bior1p5` for the bior1.5 wavelet, `thr4` for a threshold of 4 × MAD, `thr4p5` for 4.5 × MAD, and so on (a point in the number becomes `p`). The picture shows one stretch of trace detected three ways: the methods agree on the large spikes and disagree on the small ones, so the choice changes firing rates and, through them, the networks.

The list offers exactly the methods step 1 will detect with the **Wavelet methods** and **Relative thresholds** as they are set, and changes as you change them.

## Choosing a value
- **bior1p5**: the default and MEA-NAP's main method; finds smaller spikes than a threshold does.
- **A threshold method** (`thrN`): simple and easy to explain; use it when you need to match an analysis that used thresholds.

To compare methods, detect several in one step 1, look at the spike check figures, then choose here and run again from step 2. Detection is not repeated.

## How MEA-NAP uses it
Steps 2, 3 and 4 (and stimulation analysis) read only this method's spike times from the spike file. The others stay in the file, so you can change this setting and rerun from step 2 without detecting again. When **Spike source** is sorting or import, this setting is ignored and the sorted units are used.

## Things to watch for
- A method marked **"not detected by these settings"** is one the current wavelets and thresholds will not produce. That is fine when you start from step 2 with spike files from an earlier run that did detect it. If a recording's spike file does not have it, the run stops there with a message naming the methods the file does have, rather than giving every electrode zero spikes.
- MATLAB's `mergedAll` and `mergedWavelet` (pooling several methods into one train) are not made by the Python pipeline.
