---
key: data_input
name: Input folders
tab: Data
labels: Input; Raw data folder; Recordings folder (suite2p); Spike data folder
params: raw_data, spike_detected_data
related: spreadsheet, truncation, output
---
Where the recordings are. In CAT-NAP mode, also where suite2p output is. Optionally, where spikes detected outside MEA-NAP are.

## What it does

**Raw data folder** is the folder that holds every recording in the batch. MEA-NAP looks in it for a file named exactly as the spreadsheet row, with no extension, trying `.mat`, `.h5` and `.raw` in that order. Multi Channel Systems `.h5` and Axion `.raw` files are read as they come off the recorder, with no conversion. For an Axion plate, name each well in the spreadsheet (`Plate2_DIV75_A1`) and MEA-NAP will read that well out of `Plate2_DIV75.raw`.

In CAT-NAP mode the same box is called **Recordings folder (suite2p)**. It is the folder above the recordings, not one recording's own folder. Each sub-folder's name becomes the recording's name, and each sub-folder holds `suite2p/plane0`.

**Spike data folder** holds spike files made outside this run, named `<recording>_spikes.npz`. Leave it empty unless you have them.

## Choosing a value

- Choosing a local folder also lets the Data tab read the channel layout and sampling rate from the files.
- Either folder can be a Dropbox folder share link. Recordings are then downloaded one at a time and deleted after analysis, so a batch can be bigger than your disk. Where the downloads go is set under Output.
- To use a spike data folder, set **Start at step** to 2 on the Run tab. If step 1 runs, the spikes it detects are written to this run's output folder, and MEA-NAP always looks there first.

## How MEA-NAP uses it

Step 1 reads the raw traces. Steps 2–4 read the spike files: first from this run's output folder, then from the spike data folder, then from any prior analysis. When a spike file does not record the recording's length, steps 2–4 open the raw file to get it, so keep the raw folder set even when you are working from spikes.

## Things to watch for

- A spreadsheet name that matches no file does not stop the run. That recording is skipped and the log says so. Check the log for `SKIP` lines.
- The name has to match exactly. The only near-miss allowed is a folder name with extra words at the end.
