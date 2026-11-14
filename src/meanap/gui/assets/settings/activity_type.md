---
key: activity_type
name: Measure of calcium activity
tab: CAT-NAP (calcium imaging)
labels: Trace preview; Activity type; Also analyse
params: twop_activity, twop_activities
image: activity_type.png
related: peak_detection, catnap_mode, catnap_nmf
---
Which reading of each cell's calcium signal the network and activity statistics are built from. The choice changes the kind of network, not just its numbers.

## What it does

**Activity type** (default `peaks`) picks the measure:

- **peaks**: the onsets of the calcium events found by peak detection (see *Denoising settings*). The network is an STTC coincidence network, and the Connectivity tab's **Lag values** are STTC lags in ms.
- **denoised F**: the OASIS reconstruction of each cell's thresholded ΔF/F. It is still a fluorescence trace with calcium kinetics, not a spike train.
- **F**: suite2p's raw fluorescence, uncorrected.
- **spks**: suite2p's own deconvolved spike estimate.

For the last three the network is a Pearson correlation between binned traces at zero lag. The Lag values become bin lengths in ms, and edges are kept if they beat circular-shift surrogates.

The picture shows one synthetic cell in all four forms. Its `spks` row is an OASIS estimate standing in for suite2p's.

**Also analyse** adds more measures to the same run. Each ticked measure gets a full pass of its own: adjacency, metrics and figures, written under `ByActivityType/`. Every CAT-NAP table gains an `ActivityType` column, and step 5 compares the measures: how far each metric moves, and whether group and age differences survive the change. The traces are loaded and denoised only once.

## Choosing a value

`peaks` is the default. It is the only measure with an event rate, event sizes and an STTC network comparable to the MEA pipeline. Correlation networks on continuous traces are usually denser, because they also pick up slow co-fluctuation, not only coincident events. Tick one or two other measures under **Also analyse** if your conclusion should not depend on the choice.

## How MEA-NAP uses it

The primary measure's results keep the top-level output folders and file names. `peaks`, `denoised F` and `spks` all trigger denoising, because they need its outputs. `F` alone does not. Under the other measures the step-2 statistics are a reduced set (see the metric cards).

## Things to watch for

- Changing the measure changes what the lag values mean: 1000 ms is a coincidence window for `peaks` but a bin length for the others.
- `F` and `denoised F` inherit any neuropil contamination, because `Fneu` is not subtracted.
- The trace preview on this tab shows the selected recording under the chosen measure. **Cells to preview** affects only the screen.
