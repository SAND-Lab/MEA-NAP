---
key: unitnoise
name: Units against their electrode's noise
also: 5_UnitNoiseExamples, noise_fraction, raw_snr
level: concept
family: activity
related: unitquality, signalquality
---
Could the electrode's noise alone have produced this unit's spikes, as large and as often? A sorter run on pure noise still returns units: it picks the moments the noise dipped furthest and groups them. This test, run on the raw voltage, is the one check that catches that.

## What it measures

On the unit's peak electrode, over the first 2 minutes:

1. The voltage is filtered to 300–6000 Hz, the band sorters use, and divided by its noise level, so sizes are in noise SDs.
2. Each spike's size is the largest dip (or rise, for a unit whose spikes point up) within ±0.5 ms of its time. The median is the unit's **raw SNR**.
3. A **phase-scrambled copy** of the same trace is made: the same noise level and frequency content, but nothing lined up in time, so no spikes. The test counts how often the copy dips at least as far as the unit's median spike.
4. **Noise fraction** = how often the noise reaches that size ÷ how often the unit's spikes do. 0 means noise never gets there; 1 means noise alone makes as many events that large as the unit has.

A unit with a noise fraction of 0.5 or more is **noise-like** and labelled noise.

The copy is searched for its *largest dips*, not looked at at random times, because the sorter chose its spike times for being dips. Compared with noise at random times, even a pure-noise unit would look clean.

## Reading the values

Three example units, one per column: the clearest (highest raw SNR), the one nearest the 0.5 cutoff, and a typical noise-like one.

- **Top: the spikes.** 60 of the unit's raw spikes (thin) and their mean (thick), in noise SDs. A real unit's spikes overlap tightly in a clear dip. A noise-like unit's are a fuzzy band that only just reaches below the noise.
- **Bottom: how often each size occurs.** The unit's curve: spikes per second at least as large as each size. The dashed curve: the same for the electrode's noise alone. The red line is the unit's median spike size. Where the dashed curve is near or above the unit's at the red line, noise could account for the unit. A real unit's curve stays far above the noise's.

A unit whose curve rises above the noise only at the largest sizes holds a few spikes too large for noise among many that are not.

## How MEA-NAP calculates it

In step 1, when a sorting is imported and the MaxWell `.raw.h5` it was made from is found (in the raw or sorted data folder, or beside the sorter output), `unit_noise_metrics` (`meanap.pipeline.unit_noise`) scores each unit. It runs when the signal-quality check is on (`{{param:signal_quality_check}}`) and needs MaxWell's decompression plugin. The columns are `raw_snr`, `raw_amp_uv`, `noise_rate_hz`, `unit_rate_hz`, `noise_fraction` and `noise_p` in the unit-quality table.

## Things to watch for

- On a single electrode the verdict tracks the unit's SNR: units below about 3–4 usually fail, units above 5 almost never do.
- The scrambled copy keeps the power of any real spikes on the electrode, so it errs towards calling a unit noise-like, never towards passing it.
- The raw file must be the recording that was sorted. A sort of another recording would be scored against the wrong voltage.
- A unit whose electrode is not in the raw file, or with fewer than 10 spikes in the window, is left blank.
