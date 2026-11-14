---
key: detection_control
name: Detection control
tab: Spike detection
labels: Detection control; Detect spikes; Spike source; Re-check previous spike data
params: detect_spikes, spike_source, run_spike_check_on_prev_spike_data
related: spike_sorting, sorted_import, thresholds, wavelets
---
These settings decide where step 1's spikes come from, and so what the **nodes** of every later network are: electrodes, or individual neurons (units).

## What it does
**Spike source** has three choices:

- **Detect spikes on each electrode** (default). One node per electrode. Its spikes are found by the threshold and wavelet detectors set further down this tab. This is what MEA-NAP has always done.
- **Sort spikes into units**. A spike sorter separates the neurons each electrode records by waveform shape, and each becomes its own node, so one electrode can give several nodes. Needs the optional sorting package (`pip install meanap[sorting]`); without it this choice is greyed out. Settings appear under **Spike sorting**.
- **Import units sorted elsewhere**. Reads units that SpyKING CIRCUS, Kilosort/phy or SpikeInterface already found, and makes each a node, as sorting would. No voltage data is loaded. Settings appear under **Importing sorted units**.

With sorting or import, the detector settings on this tab (thresholds, wavelets, filter, refractory periods, spike method) are not used.

**Detect spikes** and **Re-check previous spike data** come from MATLAB MEA-NAP. There, unticking Detect spikes skips detection and reuses spike files from an earlier run, and Re-check redraws the spike check figures from those files without detecting again.

## Choosing a value
Use detection unless you need networks of individual neurons rather than electrodes; sorting takes much longer than detection. Choose import when your lab already sorts its data.

## How MEA-NAP uses it
Step 1 runs the chosen source and writes one spike file per recording. Steps 2–4 read it the same way whichever source made it.

## Things to watch for
- **In the Python pipeline, Detect spikes and Re-check previous spike data have no effect.** Both are saved with your settings, but nothing in the Python pipeline reads them. Whether step 1 runs is set on the Run tab by the first step to run. To reuse earlier spike files, start from step 2, or point **Spike data folder** on the Data tab at them.
- After switching between detection and sorting/import, rerun step 1. Steps 2–4 look for the new source's spike trains in the existing spike file, and if they are not there every node has no spikes.
