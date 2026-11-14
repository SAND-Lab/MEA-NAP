---
key: output
name: Output and working folders
tab: Data
labels: Output; Output data folder; Output folder name; Cache folder; Cache size limit; Derived data folder
params: output_data_folder, output_data_folder_name, cache_dir, cache_budget_gb, derived_data_folder
related: data_input, spreadsheet
---
Where the results go, and where a run that streams its data from a share link keeps its working files.

## What it does

Each run writes to **Output data folder / Output folder name**. Leave the name empty to get `OutputData<date>`, for example `OutputData14Nov2026`. A run never silently overwrites an earlier one. If the name is already taken by a folder, or by a `.meanap` bundle beside it, the run writes to `…_v2` and says so. The exception is a run set to continue an existing one.

The three settings under **Remote data (streamed runs)** matter mainly when the raw data folder is a Dropbox link:

- **Cache folder** holds downloaded recordings until they have been analysed. It defaults to `<output data folder>/MEANAP-cache`. That is the parent of the dated run folders, so successive runs share one cache.
- **Cache size limit** caps the cache. **Automatic** (the default) uses a quarter of the free space on the cache's disk, up to 50 GB. If a recording will not fit, the run stops with an error rather than filling the disk.
- **Derived data folder** is where CAT-NAP keeps files it computes from suite2p output, such as denoising results, so that a later run can reuse them. If you leave it empty, local suite2p data gets these files written beside it, and streamed data gets `<output data folder>/MEANAP-derived`.

## Choosing a value

- For streamed runs, point the cache at a fast local disk with room for at least the largest recording. Raise the limit if the run reports that the cache is full.
- The derived folder can grow to gigabytes, far more than the run's own results. Move it to a large disk if needed, but keep it between runs: deleting it means denoising runs again.

## How MEA-NAP uses it

Every step writes into the run folder: the numbered figure folders, `ExperimentMatFiles`, the CSVs, the report and the `.meanap` bundle. The cache and derived folders sit outside the run folder, so they survive after the run ends.

## Things to watch for

- The derived folder is read only by CAT-NAP. Ephys runs never use it.
- The cache empties itself as recordings are analysed. The derived folder does not, so delete it yourself once you are finished with a dataset.
