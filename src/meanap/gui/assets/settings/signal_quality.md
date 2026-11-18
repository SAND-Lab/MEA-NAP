---
key: signal_quality
name: Signal quality check
tab: Spike detection
labels: Signal quality check; Check for spikes first; Seconds checked
params: signal_quality_check, signal_quality_seconds
related: thresholds, bandpass, spike_sorting
---
Before detecting spikes, MEA-NAP checks whether the recording contains any. A detector or a spike sorter always finds *something*: lower the threshold enough and noise crosses it tens of times a second. This check uses only the voltage and tells you when that is all that is there.

## What it does
Spikes are brief, large and rare, so a trace that holds them has more large deflections than noise of the same power. For each electrode, MEA-NAP filters the trace with the bandpass above and makes a copy with its Fourier phases scrambled. The copy has exactly the electrode's own noise (its level, its colour, any line noise), but no spikes. MEA-NAP then counts the deflections beyond 4, 5 and 6 noise SDs in both. An electrode **shows spikes** when it has significantly more deflections beyond 5 SD than its scrambled copy, by at least 0.1 per second.

**Check for spikes first** (default on). Runs the check in step 1, before detection. Detection runs either way.

**Seconds checked** (default 60 s). How much of each recording is read, starting 5 s in. A minute is enough to see whether spikes exist. The check costs a few seconds on a 60-electrode array and about a minute on a 1,000-electrode one.

## Choosing a value
Keep it on. It reads at most a minute per recording, and the warning matters most on data you have not looked at yet. Turn it off only on a batch you already know is good, if step 1's time matters. A longer window helps only with very sparse activity, a few spikes per electrode per minute.

## What you get
`1_SpikeDetection/1C_SignalQuality/` holds the following:
- **`<recording>_signal_quality.png`**: 250 ms of the electrode with the clearest spikes beside its scrambled copy, events beyond −5 SD marked, how often each size of deflection occurs in the recording against its own noise, and the excess on every electrode, ranked.
- **`<recording>_signal_quality.csv`**: one row per electrode.
- **`signal_quality_summary.csv`**: one row per recording.

The run log says how many electrodes show spikes and marks with `!` any recording where none does.

## Things to watch for
- A recording where no electrode shows spikes is noise as far as threshold detection or sorting can tell. Spikes or units found in it, and the networks built from them, describe noise.
- The check sees spikes larger than about 5 noise SDs. Smaller ones may exist, but no threshold method can tell them from noise.
- Large artifacts count too. A count that is mostly positive deflections (see the `pos_` and `neg_` columns) is a warning sign.
