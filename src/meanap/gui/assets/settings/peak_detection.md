---
key: peak_detection
name: Denoising and calcium event detection
tab: CAT-NAP (calcium imaging)
labels: Denoising settings; Threshold multiplier; Time before peak; Time after peak; Min interval between events; Redo if already exists; Exclude cells with no peaks; Trace figures to save per recording
params: twop_denoising_threshold, twop_denoising_time_before_peak, twop_denoising_time_after_peak, twop_min_event_interval, twop_redo_denoising, remove_nodes_with_no_peaks, num_2p_traces
image: peak_detection.png
related: activity_type, catnap_mode
---
How CAT-NAP turns each cell's raw fluorescence into a denoised trace and a list of calcium events. The events are what the `peaks` measure, event rates and event sizes are built from.

## What it does

For every ROI in `F.npy`, MEA-NAP:

1. Fits a slow polynomial baseline.
2. Keeps the raw trace only where it rises above the threshold: baseline + **Threshold multiplier** (default 1.3) × the cell's deepest dip below baseline. Each such stretch is widened by **Time before peak** (1.0 s) and **Time after peak** (2.05 s). Everything else is set to the baseline.
3. Converts the result to ΔF/F and denoises it with OASIS. The reconstructed calcium trace is the *denoised F*.
4. Finds events on that trace with `scipy.signal.find_peaks`: height and prominence at least 0.0015, width at least 1.13 s, and peaks at least **Min interval between events** apart.

The event's onset (where the trace has risen 5 % of the way to its peak) is its time.

## Choosing a value

- **Threshold multiplier**: the threshold scales with each cell's own noise. Raise it if events appear on noise; lower it if clear transients are missed (the small transient near 63 s in the picture falls below it).
- **Min interval between events**: 0, shown as "50 frames (default)", keeps the original 50-frame spacing. That is 3.3 s at 15 Hz and 1.5 s at 33 Hz. Set a value in seconds so a batch with mixed frame rates is treated alike.
- **Time before / after peak**: set by the indicator's rise and decay. Change them only for a much faster or slower indicator.

## How MEA-NAP uses it

The outputs (`Fdenoised.npy`, `peakStartFrames.npy`, and so on) are saved and reused. **Redo if already exists** recomputes them; without it, changed settings have no effect on recordings already denoised.

**Exclude cells with no peaks** drops cells with no detected event from the network, under every measure.

**Trace figures to save per recording** (default 3) draws the raw and denoised traces with event onsets for the first N cells, in `2_NeuronalActivity/2A_IndividualNeuronalAnalysis/`. They are the only record of what detection did, and a bundle cannot rebuild them. 0 turns them off.

## Things to watch for

- Neuropil is not subtracted before denoising.
- Without OASIS installed, a Savitzky–Golay filter is used instead. It gives different events. Tick Redo after installing OASIS.
- With **Activity type** `F` alone, **Exclude cells with no peaks** stops the recording with an error: no events are detected for `F`.

## References

- Friedrich J, Zhou P, Paninski L (2017). Fast online deconvolution of calcium imaging data. PLoS Computational Biology 13:e1005423.
