---
key: thresholds
name: Threshold spike detection
tab: Spike detection
labels: Thresholds; Relative thresholds (MAD multiplier below median); Absolute thresholds (µV)
params: thresholds, abs_thresholds
image: sd_thresholds.png
related: spike_method, wavelets, refractory, bandpass
---
The threshold detector counts a spike wherever the filtered voltage dips below a line set a few noise levels under the trace's median. Each number you enter runs the detector once, at that many noise levels.

## What it does
For each electrode, MEA-NAP measures the noise of the bandpass-filtered trace with a robust estimate that large spikes barely affect: σ = median(|x − mean|) / 0.6745, a MAD-based standard deviation. The threshold is median − k × σ, where k is the multiplier. Every dip below the line is a spike; after it, the detector ignores the trace for one refractory period, then moves the spike to the bottom of its trough.

The picture shows one trace with the lines for 3, 4 and 5 × MAD. Lower lines catch smaller spikes, but at 3 × MAD noise crosses the line too.

## Choosing a value
Enter one or more multipliers separated by commas. The default is **4, 5**; 3 is permissive and 6 conservative. 4–5 is the usual range for MEA data. Running several costs little, and each is saved as its own result: `thr4`, `thr5`, or `thr4p5` for 4.5.

**Absolute thresholds (µV)** were meant to replace the relative ones with fixed voltages. Leave the field blank.

## How MEA-NAP uses it
Step 1 runs every multiplier on every electrode and saves each in the spike file. The noise level is measured once per electrode over the whole recording. Later steps use a threshold result only if **Spike method for analysis** names it.

## Things to watch for
- **The Python pipeline ignores Absolute thresholds.** The value is saved with your settings but never reaches the detector; only MATLAB MEA-NAP uses it.
- To analyse a threshold result, the multiplier here and the name under **Spike method for analysis** must agree: a threshold of 4.5 gives `thr4p5`. Whole numbers give `thr4`, `thr5`, which that list does not offer.
- Only downward crossings count. Upward-going spikes are not detected.
- The threshold scales with each electrode's own noise, so a noisy electrode gets a lower line (further from zero) than a quiet one.

## References
Quiroga RQ, Nadasdy Z, Ben-Shaul Y (2004). Unsupervised spike detection and sorting with wavelets and superparamagnetic clustering. *Neural Comput* 16(8):1661–1687.
