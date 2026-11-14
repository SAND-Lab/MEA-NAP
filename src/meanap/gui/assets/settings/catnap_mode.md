---
key: catnap_mode
name: CAT-NAP mode and recordings folder
tab: CAT-NAP (calcium imaging)
labels: Pipeline mode; Analyse suite2p data (CAT-NAP); Suite2p recordings
params: suite2p_mode, raw_data
related: activity_type, peak_detection, cell_types
---
Switches the run from MEA recordings to suite2p calcium imaging output, and tells it where the recordings are.

## What it does

**Analyse suite2p data (CAT-NAP)** sets `suite2p_mode`. Switching the window to CAT-NAP mode ticks it. With it on, a run reads suite2p output instead of raw voltage. There is no spike detection: each cell that suite2p labels as a cell (`iscell`) becomes a node, placed at its ROI centroid. Its activity is the measure chosen under **Activity type**.

The **Suite2p recordings** folder is the same setting as the Data tab's raw data folder. Point it at the folder that holds all the recordings, one sub-folder each:

```
recordings/
└── MyRecording_DIV21/
    └── suite2p/plane0/  F.npy  spks.npy  iscell.npy  stat.npy  ops.npy
```

Each sub-folder's name is that recording's name and must match the batch spreadsheet. **Scan for suite2p folders** lists what it finds:

- ✓ means denoising outputs already exist; ○ means they will be made during the run.
- *Only show recordings in the spreadsheet* hides folders the spreadsheet does not list. It changes only the view, not the run.
- **Make spreadsheet from these…** writes a batch spreadsheet whose names match the folders. It fills in the DIV where the name gives it.

## Choosing a value

Leave the box ticked in CAT-NAP mode. Point the folder at the parent of the recordings, not at one recording. You can also paste a Dropbox folder share link: it is scanned without downloading anything, and the run fetches one recording at a time. The trace preview and the denoising button need a local folder.

## How MEA-NAP uses it

For each recording the run:

1. reads `ops.npy` for the frame rate;
2. denoises the traces and detects calcium events if the chosen measure needs them;
3. builds one adjacency matrix per lag or bin length on the Connectivity tab;
4. computes the activity statistics and network metrics, with the same figure set as the electrophysiology pipeline.

Each recording uses its own frame rate, so a batch may mix rates.

## Things to watch for

- Only ROIs with `iscell` = 1 are analysed. Re-curate in suite2p, not here.
- Fluorescence is used as suite2p's raw `F`; neuropil (`Fneu`) is not subtracted.
- For remote data, derived files (denoising outputs) go to `MEANAP-derived` in the output folder instead of beside the inputs.
