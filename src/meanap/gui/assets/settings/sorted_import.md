---
key: sorted_import
name: Importing sorted units
tab: Spike detection
labels: Importing sorted units; Sorted data folder; Format; Leave out labels
params: sorted_data_folder, sorted_data_format, sorted_drop_labels
related: detection_control, spike_sorting
---
When **Spike source** is "Import units sorted elsewhere", MEA-NAP reads units another spike sorter has already found and makes each one a node, exactly as its own sorting would. These settings say where that output is and which units to leave out.

## What it does
**Sorted data folder** is where each recording's sorter output lives. MEA-NAP searches it (including subfolders) by recording name:

- **SpyKING CIRCUS**: a file `<recording>….result-merged.hdf5` (preferred, as it is the curated one) or `….result.hdf5`, with its templates file beside it.
- **phy / Kilosort**: a folder holding `spike_times.npy` whose own name, or a parent folder's, is the recording's (for example `<recording>_kilosort4`).
- **SpikeInterface folder**: a folder named for the recording containing a saved analyzer or sorting.

Leave it empty to search the raw data folder.

**Format** (default Automatic) tries SpyKING CIRCUS, then phy, then SpikeInterface for each recording. Choose one to stop a recording matching the wrong kind of output.

**Leave out labels** (default `noise`) is a comma-separated list of curation labels whose units are dropped. `noise` is what phy and Kilosort call a cluster that is not a neuron. Units labelled good, mua, or not curated at all ("unsorted") are kept. Clear the field to keep every unit.

## Choosing a value
Point the folder at your sorter output, keep Automatic and `noise`. Add `mua` to keep only well-isolated single neurons.

## How MEA-NAP uses it
Step 1 reads each recording's units and writes the same spike file as in-pipeline sorting, with each unit placed at its peak electrode. No voltage is loaded. If a MaxWell raw file is found beside the data, it supplies the sampling rate, exact duration, electrode positions and TTL events; otherwise the duration comes from the sorter's own copy of the data where there is one (phy's `.dat`), and failing that from the last spike, which makes firing rates slightly too high. Recordings with no matching output are skipped with a message in the log.

## Things to watch for
- The detector settings on this tab are not used.
- For an array with no fixed layout (MaxWell), set the channel layout to FromFile on the Data tab.
- Matching is by name: a recording called `plate` is not given the output of `plate_A1` when both are in the batch.
- Labels are matched exactly, so `Noise` and `noise` are different.
