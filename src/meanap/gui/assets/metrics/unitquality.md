---
key: unitquality
name: Unit quality
also: 4_UnitQualityMetrics
level: concept
family: activity
related: unitnoise, signalquality, FR
---
Whether each unit a spike sorter returned looks like one neuron, a mix of neurons, or not a spike at all. A sorter always returns units, so MEA-NAP scores every imported unit on the same criteria, after Bombcell (Fabre et al. 2023), and labels it **good**, **mua** (multi-unit activity) or **noise**.

## What it measures

Most criteria are read off the unit's **template**: its average spike, on the electrode where it is largest. A spike recorded outside a neuron is a sharp downward dip (the **trough**, about 0.2–0.5 ms wide) followed by a slower, smaller upward bump (the **peak**), and often a small bump just before the dip.

- **Peaks / troughs**: how many separate bumps and dips the template has, counting only those at least 20 % of its largest value. A spike has one trough and at most two peaks. A template that wiggles up and down several times is an average of noise or an artifact, not a spike.
- **Trough-to-peak duration**: time from the trough to the larger peak. Spikes take 0.1–1.15 ms. Much shorter is an electrical artifact; much longer is a slow wave, not a spike.
- **Baseline / peak**: how large the template is before the spike, relative to the spike. A spike's baseline is flat. (Not tested under the **mea** preset: an MEA spike rises gently before its trough.)
- **Refractory test**: a neuron cannot fire twice within about 1–2 ms. Pairs of spikes closer than that mean a second neuron is mixed in. The test asks, for refractory periods of 1–10 ms, whether the unit is confidently under 10 % contamination (**clean**), confidently over it (**contaminated**), or has too few spikes to tell (**unsure**).
- **Spikes missing**: the spread of the unit's spike sizes is roughly bell-shaped. If the detection threshold cut off its small end, the missing share is estimated from the fitted bell.
- **Spikes**: how many spikes the unit has. Too few to judge is mua.
- **Presence ratio**: the share of 60 s stretches in which the unit fires. A unit that is there for only part of the recording may have drifted or been split.
- **Amplitude**: the template's size in µV, trough to peak.
- **SNR**: the template's largest value over the electrode's noise level. Below 5 the spike is hard to tell apart from noise.
- **Noise events / unit's large spikes**: from the raw voltage, when the recording was found. See the card on units against their electrode's noise.

## Reading the values

One histogram per criterion, every unit in one, stacked by the label it got (good, mua, noise). The red lines are the thresholds; a unit outside them fails that criterion. The title counts the labels. A histogram is only drawn for a criterion the import could measure: Phy or Kilosort templates are not in µV, so those units have no amplitude or SNR.

A unit is labelled in order. Failing any **shape** criterion (peaks, troughs, duration, baseline, noise-like) makes it **noise**: not a spike. Otherwise failing any of the rest makes it **mua**: a spike, but not one cleanly isolated neuron. Everything else is **good**.

## How MEA-NAP calculates it

In step 1, after importing a sorting, `run_unit_quality` (`meanap.pipeline.unit_quality`) scores every unit from the spike times, templates, noise levels and spike amplitudes the sorting provides. The table is `<recording>_unit_quality.csv` in `1_SpikeDetection/1D_UnitQuality`, with the criteria each unit failed. It is an independent implementation of Bombcell's published criteria, with an **mea** preset (the default) that drops the baseline test, lowers the spike floor from 300 to 50, adds a 0.05 Hz floor, drops the 40 µV floor and lets "unsure" refractory units pass.

## Things to watch for

- A good label is not proof of one neuron. On a sparse array a unit is seen on one electrode, so nothing separates two neurons with similar spikes. On a few minutes of recording most good units are "unsure" on the refractory test.
- A sorter run on noise can pass most of these criteria: it enforces a refractory gap, and an average of noise dips is a dip. Only the raw-voltage test catches that.
- The labels are a report. Which units become network nodes is still set by the sorter's labels and *Leave out labels*.
