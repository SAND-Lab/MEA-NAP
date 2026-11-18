---
key: recording
name: Recording properties
tab: Data
labels: Recording; Sampling frequency; Channel layout; Layout file; Downsample frequency; Potential difference unit
params: fs, channel_layout, custom_layout_file, d_samp_f, potential_difference_unit
image: channel_layouts.png
related: data_input, spatiotemporal
---
Which electrode grid the recordings came from, and how a few figures read their samples. The layout and rate are read from the files when possible.

## What it does

- **Sampling frequency** is for information only. Every step reads each recording's own rate from its file, so a batch can mix rates.
- **Channel layout** maps each channel ID to a position on the array (pictured above). It is used for spatial plots and SA distances. **Custom** reads the positions from a layout file you give (below). **FromFile** reads each recording's own electrode positions from an import of sorted units, for arrays with no fixed grid such as MaxWell HD-MEAs.
- **Layout file** (Custom only) is a `.csv` or `.xlsx` table with one row per electrode: its channel ID, then x and y in µm, with y counted down from the top of the array. Columns named channel (or electrode or id), x and y are found by name, in any order; without names the first three columns are used. The Data tab draws the file as it reads it, so a swapped x and y, or rows counted from the bottom, shows before the run. The table is saved with the settings, so a settings file still works on a computer without the layout file.
- **Downsample frequency** (default 1000) is read by just one figure: the spike-count-over-time curve in the step-1 spike-detection checks. It is the number of **samples** per bin, not a rate in Hz.
- **Potential difference unit** (default uV) tells the step-1 check figures how to convert traces to µV. V multiplies by 10⁶ and mV by 10³. Detection itself uses the raw values.

## Choosing a value

- **Channel layout**: when you choose a local raw data folder, the GUI reads the files and fills in the layout. A 60- or 59-channel MCS file gives MCS60 (59 channels is the same array with its ground electrode left out). An Axion plate gives Axion64 (6-well) or Axion16 (24-well).
- **Downsample frequency**: set it to the sampling rate, as MATLAB's default does, to get one bin per second. The check figure assumes this when it labels its axes in seconds and Hz.
- **Potential difference unit**: V for Axion data, either `.raw` or converted `.mat`, which is in volts. uV for MCS data, either `.h5` or converted `.mat`.

## How MEA-NAP uses it

Step 2 uses the layout to place electrodes in the heatmaps and network plots. Step 4 uses it for the SA distances, which it converts to electrode pitches. Pitch is 200 µm on MCS arrays and 350 µm on Axion arrays. For a custom layout it is the median distance from each electrode to its nearest neighbour.

## Things to watch for

- With **Custom**, a channel in the recordings that is not in the layout file is left out of the spatial plots. Step 1's log names each one.
- The layout is never detected as Custom: a folder's detected layout does not replace a Custom choice.
- MCS59 and MCS60old are no longer offered. Settings files that name them still load and run.
- With the default Downsample frequency at 25 kHz, each bin is 40 ms. The check curve then covers only the first 1/25 of the recording, and its "Hz" axis shows spikes per 40 ms.
