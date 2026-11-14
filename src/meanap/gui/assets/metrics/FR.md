---
key: FR
name: Firing rate
also: FRactive, FRmean, FRmedian, FRiqr, FRstd, FRsem, numActiveElec
level: node
family: activity
related: ISI, bursts, networkbursts, events, ND, NS
---
How often each electrode fires (MEA) or each cell has a calcium event (CAT-NAP), averaged over the whole recording. The recording-level versions summarise the active nodes only.

## What it measures

**FR** is one value per node: the number of events divided by the recording length. **FRactive** is the same, with inactive nodes left blank. **numActiveElec** counts the active nodes. **FRmean**, **FRmedian**, **FRiqr** (interquartile range), **FRstd** and **FRsem** summarise FR across the active nodes of one recording.

## MEA versus CAT-NAP

The keys are shared, but the event is not:

- **MEA (electrophysiology):** a node is an electrode, or a unit in a spike-sorted run. FR is detected spikes per second (Hz).
- **CAT-NAP, `peaks` measure:** a node is a suite2p cell. FR is detected calcium events per second (Hz). Calcium rates are far lower than spike rates and the two cannot be compared.
- **CAT-NAP, `spks`, `F` or `denoised F`:** no events are counted. FR is the trace summed over all frames, divided by duration (a.u./s), which tracks the trace's mean level, not a rate. The active threshold is applied to this number too.

## Reading the values

Higher FR means more activity. FRmedian is less affected by a few very busy nodes than FRmean. A change in numActiveElec can drive changes in many network metrics, so check it first.

## How MEA-NAP calculates it

- **MEA:** `firing_rates_bursts` (`meanap.pipeline.firing_rates`) divides each electrode's spike count from step 1 (method `{{param:spikes_method}}`) by the recording duration in seconds. Grounded electrodes have their spikes removed first.
- **CAT-NAP:** `calc_twop_activity_stats` (`meanap.catnap.stats`) divides each cell's event count (or summed trace) by duration.
- A node is **active** when FR ≥ `{{param:min_activity_level}}`. FRmean, FRmedian, FRiqr, FRstd (n − 1) and FRsem use active nodes only and are rounded to 3 decimals.

## Things to watch for

- With no active nodes, the MEA summaries are 0 but the CAT-NAP ones are blank (NaN).
- If recordings were truncated (truncation on: `{{param:trunc_rec}}`, keeping `{{param:trunc_length}}` s), rates refer to the analysed part only.
- In a spike-sorted run, the FR heatmap adds up the units on each electrode.
- MEA FRiqr uses linear percentiles. CAT-NAP FRiqr uses MATLAB's quantile convention, so small samples can differ slightly.

## References

- Sit TPH et al. (2024). MEA-NAP: A flexible network analysis pipeline for neuronal 2D and 3D organoid multielectrode recordings. Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
