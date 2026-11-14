---
key: recording
name: Recording properties
tab: Data
labels: Recording; Sampling frequency; Channel layout; Downsample frequency; Potential difference unit
params: fs, channel_layout, d_samp_f, potential_difference_unit
image: channel_layouts.png
related: data_input, spatiotemporal
---
Which electrode grid the recordings came from, and how a few figures read their samples. The layout and rate are read from the files when possible.

## What it does

- **Sampling frequency** is for information only. Every step reads each recording's own rate from its file, so a batch can mix rates.
- **Channel layout** maps each channel ID to a position on the array (pictured above). It is used for spatial plots and SA distances. **FromFile** reads each recording's own electrode positions from an import of sorted units, for arrays with no fixed grid such as MaxWell HD-MEAs.
- **Downsample frequency** (default 1000) is read by just one figure: the spike-count-over-time curve in the step-1 spike-detection checks. It is the number of **samples** per bin, not a rate in Hz.
- **Potential difference unit** (default uV) tells the step-1 check figures how to convert traces to µV. V multiplies by 10⁶ and mV by 10³. Detection itself uses the raw values.

## Choosing a value

- **Channel layout**: when you choose a local raw data folder, the GUI reads the files and fills in the layout. A 60-channel MCS file gives MCS60 and 59 channels gives MCS59. An Axion plate gives Axion64 (6-well) or Axion16 (24-well).
- **Downsample frequency**: set it to the sampling rate, as MATLAB's default does, to get one bin per second. The check figure assumes this when it labels its axes in seconds and Hz.
- **Potential difference unit**: V for Axion data, either `.raw` or converted `.mat`, which is in volts. uV for MCS data, either `.h5` or converted `.mat`.

## How MEA-NAP uses it

Step 2 uses the layout to place electrodes in the heatmaps and network plots. Step 4 uses it for the SA distances, which it converts to electrode pitches. Pitch is 200 µm on MCS arrays and 350 µm on Axion arrays.

## Things to watch for

- **Mea256** and **Custom** are offered in the list but have no coordinates in the Python pipeline. Anything that needs electrode positions reports "Unsupported channel layout". MCS59, MCS60old and Axion16 work fine, though the list does not show them. Type the name, or let detection fill it in.
- With the default Downsample frequency at 25 kHz, each bin is 40 ms. The check curve then covers only the first 1/25 of the recording, and its "Hz" axis shows spikes per 40 ms.
