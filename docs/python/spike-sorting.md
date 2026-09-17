# Spike sorting: neurons as nodes

By default MEA-NAP's nodes are electrodes. Step 1 finds the spikes on each
electrode and everything after — firing rates, bursts, the STTC adjacency
matrix, the network metrics — treats that electrode's pooled activity as one
node. On a dense culture an electrode often hears two or three neurons, and
their spikes are then one train.

**Spike sorting** separates those neurons by their waveforms, and MEA-NAP can
make each one a node. Switch **Spike source** on the Spike detection tab
from *Detect spikes on each electrode* to *Sort spikes into units*, or in
Python:

```python
from meanap.params import Params
params = Params(..., spike_source="sort")
```

Everything else is unchanged: steps 2–4 run on the units exactly as they run
on electrodes, the CSVs gain a `Unit` column beside `Channel`, and the
network plots draw each unit beside its electrode. Needs the `sorting` extra
— see [Installation](installation.md#optional-spike-sorting).

## What it does

1. **Preprocess.** Bandpass 300–6000 Hz and subtract the median across
   electrodes at every sample (the noise the whole dish picks up). The band
   is separate from the detectors' because sorters work on waveform shape.
2. **Sort.** The recording is handed to a sorter through
   [SpikeInterface](https://spikeinterface.readthedocs.io), with the MEA's
   real electrode geometry attached. The default sorter is **Tridesclous2**;
   see [Choosing a sorter](#choosing-a-sorter).
3. **Measure and curate.** Two spikes of one unit closer than 0.3 ms are one
   spike counted twice (a matcher resolving a burst can do that) and the
   second is dropped. Then every unit the sorter returns gets a template,
   SNR, firing rate and refractory-violation fraction, and a label:

   | Label | Meaning |
   |---|---|
   | `good` | SNR ≥ 4, firing ≥ 0.05 Hz, fewer than 5 % of intervals inside 1.5 ms |
   | `mua` | real activity, but the refractory violations say more than one neuron |
   | `noise` | below the SNR or firing-rate floor — dropped |

   By default `good` and `mua` units become nodes. Dropping `mua` keeps only
   well-isolated neurons, at the cost of losing the busiest electrodes from
   the network; the choice is **Keep units labelled** on the tab.
4. **Number the nodes.** Units are named `<electrode>-<rank>` — `25-1` is the
   largest-amplitude unit on electrode 25, `25-2` the next — so IDs are stable
   across reruns and readable in every CSV.

## Reading the output

`1_SpikeDetection/1A_SpikeDetectedData/<recording>_spikes.npz` holds one
train per unit under the method `sorted`, and `channels` lists each unit's
parent electrode — repeated where an electrode gave several units. This is
what lets electrode grounding, the electrode heatmaps (units are pooled onto
their electrode there: rates add, everything else averages) and the
node-level CSVs work without knowing the nodes are units. The `unit_*` arrays
carry the IDs, coordinates, quality metrics and labels.

`1B_SpikeDetectionChecks/<group>/<recording>/` replaces the detection check
figures with three of its own:

- **1_UnitsPerElectrode** — the MEA grid coloured by how many units each
  electrode became. The picture of what sorting changed about the node set.
- **2_UnitTemplates** — one panel per electrode, its units' templates
  overlaid (dashed for `mua`). This is where to judge whether two units on an
  electrode are really two neurons.
- **3_UnitQuality** — every returned unit against the curation floors, so the
  labels can be read off the plot.

and `units.csv`, one row per unit the sorter returned, kept or not.

The spike viewer opens a sorted file too: each unit is listed as
`unit 25-1`, drawn on its electrode's trace.

## Why this is different from Neuropixels sorting

MEA-NAP's arrays are low-density — 200 µm between electrodes on an MCS
60MEA, 350 µm on Axion plates. An extracellular spike reaches about 100 µm,
so it is seen on **one electrode**. There is no spatial footprint to sort on;
each electrode is sorted on its own waveforms, the way tetrode-era sorters
did it. MEA-NAP's presets therefore keep every sorter's spatial radius
inside one electrode's reach and switch off drift correction, which needs a
footprint to track. The trade-off is inherent: two neurons on one electrode
with similar waveforms cannot be separated by any sorter, and that is what
the `mua` label is for.

One consequence worth knowing: SpikeInterface's default contamination
metric, `isi_violations_ratio`, assumes Poisson firing and reads as 10–60 for
every unit in a bursting culture. MEA-NAP curates on the plain fraction of
intervals inside the refractory period instead.

## Choosing a sorter

There is no ground truth in a culture recording, and on a single electrode
two sorters can split the same spikes differently with nothing to say which
is right. So the default was chosen on a **synthetic recording with known
neurons** on the real MCS60 geometry — 1–3 neurons per electrode, 15–120 µV,
firing in network bursts — scored with SpikeInterface's ground-truth
comparison (`python/benchmark_spike_sorting.py`, three seeds, 120 s each):

| Sorter | Neurons found (of ~52) | Well detected | False-positive units | Over-split units | Accuracy | Time |
|---|---|---|---|---|---|---|
| **Tridesclous2** (default) | 43.0 | 38.3 | 0 | 0 | 0.78 | 30 s |
| MountainSort5 | 38.3 | 26.7 | 4.0 | 5.7 | 0.64 | 19 s |

Tridesclous2 was built for few-channel data and it shows: every node it
returned was a neuron. MountainSort5 is the faster alternative when that
matters. SpyKING CIRCUS 2 and Lupin run too but are tuned for dense probes
(on the real test recording SC2 was 8× slower and stacked seven units on one
electrode); Kilosort4 needs a GPU to be worth it and its own documentation
advises against arrays this sparse. Any sorter SpikeInterface can run can be
named in `sorter_name`, with `sorter_params` passed straight through.

Auto-merge (SpikeInterface's `auto_merge_units`) is available but off: on the
benchmark it did not recover MountainSort5's over-splits and Tridesclous2 had
none.

## How sorted units compare with bior1.5 detection

Measured on one dense hippocampal culture (`HP_tc043_DIV21`, MCS 60MEA, DIV
21, 10 min), so treat the numbers as one data point and rerun the recipe
below on your own recordings before generalising.

| | bior1.5 (detected) | Tridesclous2 (sorted) |
|---|---|---|
| Spikes | 167 k on 60 electrodes | 102 k on 48 electrodes |
| Quiet electrodes | all kept | 12 dropped — 7–74 spikes each, too few to build a template |
| Agreement (±0.5 ms) | 43 % of bior1.5 spikes have a TDC2 spike | 71 % of TDC2 spikes have a bior1.5 spike |
| What the other lacks | small (median 4.7 σ, half under 5 σ) and burst-interior (two-thirds within 3 ms of the previous spike) | sub-threshold spikes (median 3 σ) the peeler recovered under bigger ones |
| Refractory violations, busiest electrode | 48 % of ISIs < 1.5 ms | 27 % |
| STTC matrices at 10 ms, 48 shared electrodes | r = 0.91 between them; mean STTC 0.54 | mean STTC 0.65 |

So on this recording the two agree on the network's structure (r ≈ 0.9,
the same as thr5 vs either) but not on the spike population: bior1.5 is the
more *sensitive* detector — anything spike-shaped above ~4 σ — and TDC2 the
more *selective*, keeping only events it can attribute to a learned template.
The sorter's trains are more strongly correlated overall because they
concentrate in the network bursts. Neither is "right"; the choice is how
much low-amplitude activity you want counted. Feeding bior1.5's detections
into TDC2, or lowering TDC2's threshold, does not recover more small neurons
on ground truth — see `python/SPIKE_SORTING_PLAN.md` §5.5 for why.

To repeat this on a recording of yours, run it once in each mode and
compare the two spike files (and, for network-level effects, the two runs):

```bash
uv run python python/compare_spike_trains.py \
    OutputData_detected/1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz \
    OutputData_sorted/1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz \
    --method-a bior1p5 --raw /path/to/<rec>.mat
uv run python python/compare_sorted_vs_detected.py OutputData_detected OutputData_sorted --out compare.png
```

The first prints spike totals, ISI structure, agreement, what the unmatched
spikes look like and the STTC correlation; the second draws units per
electrode, same- vs other-electrode STTC, and the recording-level network
metrics of both runs side by side.

## When to use it

Sorting changes the node set, so it changes every network metric; that is
the point, and it is also why it is not the default. Use it when the
question is about neurons — how many an electrode carries, whether two units
on one electrode belong to different modules — and compare against the
detected run of the same recordings before trusting a difference in a
group-level metric. The unit-quality figure and `units.csv` are the record
of what the sorter did; a run whose `mua` units outnumber its `good` ones is
telling you the culture is too dense for single-electrode sorting to
separate.
