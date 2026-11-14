---
key: spike_sorting
name: Spike sorting
tab: Spike detection
labels: Spike sorting; Sorter; Bandpass for sorting; Common reference; Electrode pitch; Auto-merge split units; Drop duplicate spikes within; Curation: min SNR; Curation: refractory period; Curation: max refractory violations; Curation: min firing rate; Keep units labelled; Keep sorter output
params: sorter_name, sort_freq_min, sort_freq_max, sort_common_reference, electrode_pitch_um, sort_auto_merge, sort_censor_ms, curation_min_snr, curation_refractory_ms, curation_max_rp_violation_frac, curation_min_firing_rate, curation_keep_labels, keep_sorter_output
image: sd_spike_sorting.png
related: detection_control, sorted_import
---
When **Spike source** is "Sort spikes into units", a spike sorter separates the neurons each electrode records by the shape of their spikes, and each neuron (unit) becomes a node. These settings run the sorter and decide which of its units to keep.

## What it does
**Sorter** (default tridesclous2): built for few-channel data, it recovered the most neurons on MEA-NAP's synthetic test data, with no false or duplicated units. mountainsort5 is faster; the others are tuned for dense probes, and kilosort4 needs a GPU.

**Bandpass for sorting** (default 300–6000 Hz) is the band the sorter sees, separate from the detectors' filter: sorters group spikes by shape, and this band keeps more of it. **Common reference** (default global median) subtracts, at every sample, the median across all electrodes, removing noise the whole dish picks up. **Electrode pitch** (default "layout default": 200 µm for MCS 60, 350 µm for Axion) sets the sorter's neighbourhoods; set it only for a custom array.

**Auto-merge split units** (default off) joins units that look like one neuron split in two. **Drop duplicate spikes within** (default 0.3 ms) removes a unit's second spike when two come closer than this.

Each unit is then labelled (picture):

- **noise** if its peak is below **min SNR** (default 4 × the noise) or it fires below **min firing rate** (default 0.05 Hz);
- otherwise **multi-unit** if more than **max refractory violations** (default 5 %) of its inter-spike intervals are shorter than the **refractory period** (default 1.5 ms), meaning it holds spikes of more than one neuron;
- otherwise **good**.

**Keep units labelled** picks which labels become nodes (default good and multi-unit). **Keep sorter output** (default off) keeps the sorter's folder and filtered copy of the recording for Phy.

## Choosing a value
Start with the defaults. Untick multi-unit to keep only single neurons; this drops the busiest electrodes' pooled activity from the network.

## How MEA-NAP uses it
Step 1 sorts each recording and saves the kept units under the method name "sorted"; steps 2–4 use them in place of electrodes. Units on one electrode are drawn on a small ring around it.

## Things to watch for
- Sorting is much slower than detection and needs `pip install meanap[sorting]`.
- Switch Common reference off if most electrodes fire together so strongly that the median itself contains spikes.
- Keep sorter output stores a copy as large as the recording.
