---
key: catnap_nmf
name: NMF components (CAT-NAP)
tab: CAT-NAP (calcium imaging)
labels: Compute NMF components
params: twop_nmf
related: activity_type, peak_detection
---
Whether a CAT-NAP run also counts how many recurring patterns of co-active cells the recording contains, using non-negative matrix factorisation (NMF).

## What it does

Ticked, each recording gets the NMF dimensionality metrics, `num_nnmf_components` and `nComponentsRelNS`, beside the effective rank (see the NMF metric card for what they mean). The calculation is the electrophysiology pipeline's `cal_nmf`:

1. bin each cell's events into counts, at the Connectivity tab's NMF downsampling frequency (default 10 Hz);
2. build a shuffled copy in which each cell's events are wrapped round a random cut point;
3. fit NMF at rank 1, 2, 3 … to both matrices, and stop at the first rank where the real data's reconstruction error is no longer smaller than the shuffled data's. That rank is the component count.

## Choosing a value

Off by default (`twop_nmf` = False). Effective rank, which also measures how many independent dimensions the activity has, is always computed. Turn NMF on only if you need the component count itself, for example to compare with an MEA analysis that reports it. It is markedly slower than effective rank, and NMF is much less established on calcium events than on spike trains.

## How MEA-NAP uses it

The input is a list of event times per cell, which depends on the **Activity type**:

- **peaks**: the detected event onsets.
- **F**, **denoised F** and **spks**: every frame where the trace is non-zero counts as an event. For `spks` that matches what the values mean. Raw `F` is non-zero in nearly every frame, so its "events" are almost every frame and carry little information. Use NMF with `peaks`.

The metrics go into the recording-level network table and step 5, like any other network metric. A failure is logged as a warning and leaves the rest of the recording's metrics intact.

## Things to watch for

- The ephys **NMF** switches on the Connectivity tab do not apply to CAT-NAP runs. This box is CAT-NAP's only switch.
- The component count is bounded by the number of cells that were active. Use `nComponentsRelNS`, which divides by that number, to compare recordings with different numbers of active cells.
