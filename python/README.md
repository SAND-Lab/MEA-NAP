# MEA-NAP Python

A Python implementation of MEA-NAP, living alongside the MATLAB codebase in this repository.

> **Working on the pipeline port (spike detection, output folders, Run/Test pipeline wiring)?**
> Read [`PIPELINE_PORT_STATUS.md`](PIPELINE_PORT_STATUS.md) first — it tracks what's ported,
> what isn't, and non-obvious gotchas (sign conventions, HDF5 quirks, parity numbers) that are
> easy to re-break or re-discover from scratch.

## Project structure

```
MEA-NAP/
├── pyproject.toml        # Python project config and dependencies
├── .python-version       # Pins Python 3.13
├── uv.lock               # Reproducible dependency lockfile
├── src/
│   └── meanap/
│       ├── params.py         # Params dataclass (mirrors MATLAB Params struct)
│       ├── network_plot.py   # Network plotting logic (MatData loader, plot_network)
│       ├── pipeline/          # MATLAB pipeline port — steps 1-4. Read
│       │                      # python/PIPELINE_PORT_STATUS.md before touching this.
│       │   ├── runner.py             # run_pipeline() — top-level orchestrator (MEApipeline.m equivalent)
│       │   ├── output_folders.py     # Output folder tree (CreateOutputFolders.m port)
│       │   ├── spreadsheet.py        # Recording CSV/spreadsheet parsing
│       │   ├── example_data.py       # Downloads the example dataset (downloadExampleData.m port)
│       │   ├── io.py                 # Raw recording I/O: MCS .h5, Axion .raw, .mat v7/v7.3
│       │   ├── axion_raw.py         # Axion .raw reader (AxionFileLoader port)
│       │   ├── spike_detection.py    # Step 1: threshold + bior1.5 wavelet CWT
│       │   ├── plotting.py           # Step 1 check plots
│       │   ├── firing_rates.py       # Step 2: firing rates
│       │   ├── burst_detection.py    # Step 2: network + single-channel bursts
│       │   ├── plotting_step2.py     # Step 2 check plots
│       │   ├── parula.py             # MATLAB parula colormap (not in matplotlib)
│       │   ├── sttc.py               # Step 3: Spike Time Tiling Coefficient
│       │   ├── probabilistic_threshold.py  # Step 3: significance thresholding
│       │   ├── network_metrics.py    # Step 4: BCT-equivalent network metrics
│       │   ├── louvain.py            # Step 4: Louvain community detection
│       │   ├── modularity.py         # Step 4: consensus clustering (→ Ci/Q/nMod)
│       │   ├── null_models.py        # Step 4: degree-preserving randomization
│       │   ├── channel_layout.py     # Electrode ID → spatial coordinate lookup
│       │   ├── plotting_step4.py     # Step 4 check plots
│       │   └── report.py             # Self-contained HTML output viewer — see below
│       ├── catnap/           # CAT-NAP: calcium imaging pipeline (suite2p)
│       │   ├── scanner.py    # Discover suite2p recordings in a folder
│       │   ├── loader.py     # Load suite2p .npy files into Python
│       │   └── denoising.py  # Baseline correction, peak detection, denoising
│       └── gui/
│           ├── app.py            # Entry point (meanap-gui command)
│           ├── main_window.py    # Main QMainWindow
│           └── panels/
│               ├── paths.py          # File/folder paths tab
│               ├── recording.py      # Sampling rate and hardware tab
│               ├── spike_detection.py
│               ├── connectivity.py   # STTC and thresholding tab
│               ├── catnap.py         # CAT-NAP (2P) tab
│               ├── network_viewer.py # Network Viewer tab
│               └── pipeline.py       # Run controls, status log, View report button
└── python/               # Scripts, notebooks, and pipeline docs (this directory)
    ├── README.md
    ├── PIPELINE_PORT_STATUS.md   # Living status doc for the pipeline port — read first
    ├── test_pipeline_step1.py    # Parity tests, one per step (run directly with uv run)
    ├── test_pipeline_step2.py
    ├── test_pipeline_step3.py
    ├── test_pipeline_step4.py
    ├── test_pipeline_cartography.py
    ├── test_pipeline_null_models.py
    ├── test_pipeline_channel_layout.py
    ├── test_fixtures/            # MATLAB-generated ground-truth .npz fixtures + .m generator scripts
    ├── compile_plots.py
    └── feature-schematic.ipynb
```

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then from the repo root:

```bash
uv sync
```

This creates a `.venv/` and installs all dependencies. No manual environment activation needed — prefix commands with `uv run`.

## GUI (`meanap-gui`)

Launch the graphical interface from the repo root:

```bash
uv run meanap-gui                  # MEA-NAP (ephys), the default
uv run meanap-gui --mode meastim   # + stimulation analysis
uv run meanap-gui --mode catnap    # two-photon imaging (suite2p)
```

The GUI is a tabbed desktop application (PyQt6) that mirrors the MATLAB App Designer interface. `--mode` picks which of the three pipelines to start in, and the window shows only that pipeline's tabs; the **Mode** selector in the toolbar switches at any time without losing what you have entered. See [Modes](../docs/python/gui-guide.md#modes).

Each tab corresponds to a section of the pipeline:

| Tab | Description |
|---|---|
| **Paths** | Set all input/output folder and file paths, with Browse buttons |
| **Recording** | Sampling frequency, downsample rate, channel layout, potential unit |
| **Raw formats** | No conversion needed — point the raw data folder at MCS `.h5`, Axion `.raw`, or `.mat` files; see [Raw data formats](../docs/python/gui-guide.md#raw-data-formats) |
| **Spike detection** | Thresholds, wavelet methods, bandpass filter, template settings |
| **Connectivity** | STTC lag values, adjacency matrix type, probabilistic thresholding |
| **CAT-NAP (2P)** | Suite2p pipeline — see below |
| **Network Viewer** | Interactive network plot from a MEA-NAP output `.mat` file — see below |
| **Pipeline** | Step selection (1-4), run/test/stop controls, status log, and a "🌐 View report" button that generates and opens an HTML output browser — see "Output report" below |

### Parameters

Parameters are stored as a `Params` dataclass (`src/meanap/params.py`). Every panel exposes `load(params)` and `save(params)` methods so parameters round-trip cleanly to and from the dataclass.

Parameters can be saved and reloaded as JSON using the toolbar:

- **New** — reset everything to defaults
- **Open params…** — load a previously saved JSON file
- **Save params…** — write current settings to JSON

### Running the pipeline

Set the required paths (MEA-NAP folder, raw data folder, output folder), configure the desired tabs, then go to the **Pipeline** tab and click **Run pipeline**. The GUI validates that required paths are filled in before starting. Click **🧪 Test pipeline** instead to download the bundled example dataset and run against that, as a setup sanity check.

The pipeline mirrors MATLAB's 4 steps — spike detection, neuronal activity (firing rates/bursts), functional connectivity (STTC), and network metrics — writing the same output folder structure MATLAB's `CreateOutputFolders.m` builds. **Not every step or metric is fully ported yet**; see [`PIPELINE_PORT_STATUS.md`](PIPELINE_PORT_STATUS.md) for exactly what's done, what's approximate, and what's still missing before relying on this for real analysis.

### Not overwriting an earlier run

The output folder defaults to today's date, so two runs in a day both want
`OutputData07Aug2026`. Rather than replacing the first one, the second writes to
`OutputData07Aug2026_v2` and says so; the GUI asks first, offering the new name,
**Continue it**, **Overwrite**, or **Cancel**. Past `_v99` it falls back to a
`_HHMMSS` stamp. **Continue it** is the one an interrupted run wants — see
[Continuing an interrupted run](#continuing-an-interrupted-run).

The `.meanap` bundle counts on its own — an express run's folder is often
deleted once the bundle is in hand, and it would otherwise be the one artefact
left to overwrite. An empty tree from a crashed run does not count.

Resuming *into* a folder (start at step > 1 with a named output folder and no
prior-analysis path) is left alone: that run reads what it then rewrites. To
replace a run deliberately, delete it or set
`Params(overwrite_existing_output=True)` — which is still reported in the log,
never silent.

### Continuing an interrupted run

A batch cut off at recording 5 of 10 — Ctrl-C, a cluster wall clock, a closed
laptop — can pick up at 6 rather than starting again:

```python
Params(..., output_data_folder_name="OutputData09Aug2026", continue_interrupted=True)
```

In the GUI it is the **Continue it** button on the dialog that appears when a
run would land on an existing folder. A continued run writes into that same
folder and skips any recording whose result for the step is already there:

| Step | Skipped when present | Cost avoided |
|---|---|---|
| 1 — spike detection | `<rec>_spikes.npz` | ~52s/recording |
| 3 — connectivity | `<rec>_adjM.npz` | ~21s/recording |
| 4 — network metrics | that recording's entry in `netmet_results.json` | ~99s/recording |
| CAT-NAP phase 1 | `<rec>_catnap.npz` | the STTC + thresholding half |

Step 4 has no per-recording file, so `netmet_results.json` is itself the
checkpoint: it is rewritten atomically after each recording finishes, from the
parent process. An interrupted run therefore leaves a valid results file holding
everything that completed, rather than nothing at all.

Two things make this safe rather than merely convenient. **Writes are atomic** —
every artefact goes to a temporary name and is `os.replace`d into position — so
a file existing means it is whole; anything unreadable is deleted and redone.
And **step 4 loads the finished recordings back in** rather than only skipping
them, because its cartography boundaries are pooled across the whole batch: a
continued run that saw only what it recomputed would place them somewhere the
original never would. `python/test_continue_interrupted.py` checks the result is
identical to a run that was never interrupted, figures included.

### Changing which recordings a run covers

The same mechanism handles a batch that changes after the fact. In each case the
result is what you would have got by analysing that set from the start — the
pooled statistics, the batch-scaled axes and the cartography boundaries are all
redone over whatever the spreadsheet now names.

**Adding a recording.** Put it in the spreadsheet and continue: only the new one
is computed.

```python
Params(..., output_data_folder_name="OutputData09Aug2026", continue_interrupted=True)
```

**Removing one.** Take it out of the spreadsheet and continue. It drops out of
every CSV and pooled statistic on its own, but its *figures* do not delete
themselves — they would keep appearing in the output folder and the report as
though they were part of the analysis. So a continued run names them:

```
1 recording(s) in this folder are no longer in the spreadsheet: rec2
  Their 23 figure(s) are still on disk and will appear in the output folder and
  report, though they are excluded from every CSV and pooled statistic.
  Set Params.prune_removed_recordings = True to delete them.
```

With `prune_removed_recordings=True` the figures go. The recording's *data* is
kept either way — that is what makes putting it back cheap.

**Combining separate runs.** Name more than one previous analysis and give a
spreadsheet listing recordings from all of them; nothing is recomputed.

```python
Params(
    prior_analysis=True,
    prior_analysis_path="path/to/RunA",
    prior_analysis_paths=["path/to/RunB"],   # searched after the first
    start_analysis_step=4,
)
```

Each folder may equally be a `.meanap` bundle.

### Progress and time estimates

A run shows a progress bar on the Pipeline tab with the phase, the recording
being worked on, elapsed time and an estimate of the time left. A remote run
gets a second, slimmer bar for the download.

The bar is weighted, not a count of recordings: on the reference benchmark a
recording costs 3.2s in step 2 and 98.7s in step 4, so equal weighting would
park the bar at half way with the slowest step still entirely ahead. The
estimate is *calibrated rather than predicted* — the weights only fix the
relative size of each phase, and the rate is measured from this run on this
machine, so it adapts within the first completed recording. Until then it says
"estimating" rather than quoting a number from someone else's hardware. Expect
it to be within ~10-20% and to wobble when a parallel phase finishes several
recordings at once.

Transfers are deliberately *not* counted as pipeline progress: downloads
overlap compute (the next recording is fetched while this one is analysed), so
adding them would double-count. A slow link instead shows up as a higher
measured cost per unit of work, which the estimate already tracks.

To consume the same data outside the GUI, pass a callback:

```python
from meanap.pipeline.runner import run_pipeline
run_pipeline(params, progress=lambda p: print(p.describe()))
# 37% · Step 4 · Network metrics · rec_A3 (2/4) · 6m 20s elapsed · ~10m 41s left
```

### Output report

After a run (or against any existing MEA-NAP output folder), click **🌐 View report** on the Pipeline tab to generate `report.html` in that output folder and open it in your browser. It's a self-contained page (no server, works offline) with a folder-tree sidebar and a captioned image gallery for every plot the pipeline produced — captions are adapted from MEA-NAP's own figure-legend documentation (`docs/meanap-outputs.rst`) wherever one exists. You can also generate it directly from Python:

```python
from meanap.pipeline.report import generate_report
generate_report("/path/to/OutputData...")  # writes report.html there, returns its path
```

The same report is deep-linkable — `report.html#4_NetworkActivity/4A_IndividualNetworkAnalysis/<group>/<recording>/<lag>mslag` auto-navigates the sidebar to that folder on load, useful for sharing a link to a specific plot.

## Express mode & run bundles

`Params(express_mode=True)` skips every figure that can be rebuilt from the
run's own data and keeps **only** the shareable `.meanap` bundle — the output
folder is removed once the bundle has been written *and read back*, since
keeping both is keeping two copies of the same run. `run_pipeline` returns the
bundle path for such a run. If the bundle cannot be written or does not reopen,
the folder is kept and the log says why.

To turn a bundle back into an ordinary folder — to send results to someone
without MEA-NAP — open it in the viewer and press **Export output folder**, or
call `meanap.pipeline.export.export_output_folder(bundle)`. It draws every
figure into the layout the pipeline itself writes and adds the self-contained
`report.html`, so the recipient needs nothing installed. On the example dataset
that is 335 figures in about 40 seconds, and the exported figures are
byte-identical to the ones a full run would have written.

The saving is the point: a full run of the example dataset writes 483 figures
and 56 MB; the express bundle is 2.2 MB.

```bash
uv run meanap-viewer path/to/OutputData….meanap
```

The viewer redraws any figure on demand with the full Network Viewer control
set, and exports PNG, **SVG** or PDF. A bundle also works as a resume artifact:
point `prior_analysis_path` at it to re-run step 4 without the raw data.

One figure family can't be rebuilt yet and is simply absent from an express run
— CAT-NAP's per-recording cell-type subnetwork figures. See
`docs/python/express-mode.md`.

The step-1 spike-detection checks (example traces, spike frequency, waveforms)
*are* rebuildable, despite being drawn from raw voltage: almost none of that
voltage is visible in them — the trace panels clip to a ±30 ms window, the
waveform panel uses one channel, the frequency panel needs only spike times. So
step 1 saves the slices they show (`<rec>_step1checks.npz`, ~100 KB) and the
bundle carries that instead of ~1.3 MB of PNG per recording. On the two-recording
example dataset that took the bundle from 5.1 MB to 0.69 MB. The figure a run
writes and the figure the viewer rebuilds come out of the same drawing function,
so they are byte-identical.

The step-3 edge-thresholding checks work the same way, and were worse off
before: their folder was already on the never-pack list *and* the family was
declared unreconstructable, so a bundle dropped them with no way to get them
back. Step 3 now reduces the threshold snapshots — tens of megabytes that
vanished when the step returned — to the ~10 KB per recording the figure
actually shows.

Bundling an output folder written before either change keeps its PNGs instead,
and says so in the manifest rather than claiming a family it cannot rebuild.

The CAT-NAP per-recording cell-type subnetwork figures needed no payload at
all: the adjacency, coordinates, resolved groups and the three subnetwork CSVs
were already in the bundle, and only the wiring was missing. One change was
needed to make them reproducible — the jittered points in
`3_NodeMetricsByCellType` now come from their own RNG stream rather than from
whatever state the metrics left the shared one in, so a viewer can land on the
same offsets.

**Every PNG a full run writes can now be produced from its bundle** — verified
by rendering everything a bundle offers and comparing the set against a full
run's output folder (0 unaccounted). Two routes were missing and were added:

- the **batch-scaled** and **side-by-side** versions of the spatial network
  plots. These were always reachable by naming their stems, but nothing
  advertised them. The viewer now shows a *Scaling* toggle — individual /
  batch-scaled / side by side — for whichever network figure is selected, and
  hides it for figures that have only one. The naming rule lives once, in
  `step4.variant_stem`, so the renderer cannot drift from what the pipeline
  writes.
- the four **cell-type composition** figures. `composition_frame` omits its
  "active cells" columns unless given `active_by_rec`, and the render path
  wasn't passing it — so the figures that read those columns were silently never
  drawn. The helper that computes it moved from the CAT-NAP pipeline into
  `group_plots`, where both callers can reach it.

## Remote data

`raw_data` accepts a **Dropbox folder share link** instead of a path. Recordings
are fetched one at a time and dropped once analysed, so a batch can exceed local
disk — a real 13-recording folder streams through **0.72 GB** of working space.
The cache and denoising outputs default under `output_data_folder`; nothing else
needs configuring.

```bash
uv run meanap-preflight '<share link>'          # check first; seconds, no transfer
uv run meanap-preflight '<link>' --write-spreadsheet fixed.csv
```

In the GUI, the same link works in **Raw data folder** and in the CAT-NAP tab's
**Scan for suite2p folders**, which lists what is behind the link without
transferring anything. The batch spreadsheet is still a local file; build it
from the scan (see below) or with `--write-spreadsheet` above.

A remote run pre-flights automatically and refuses to start if recordings are
missing, since a silently-shortened batch still produces results. Share links
are redacted from bundled `params.json`. Works for both analysis paths — a
suite2p folder per recording for CAT-NAP, one raw file for electrophysiology.
See `docs/python/remote-data.md`.

## CAT-NAP (2P)

CAT-NAP is the calcium imaging analysis pathway, triggered by loading a folder that contains suite2p output. It is the Python equivalent of the MATLAB `suite2pToAdjm` / `denoiseSuite2pData` workflow.

### Expected folder structure

CAT-NAP looks for recordings inside your raw data folder where each recording directory contains a `suite2p/plane0/` subdirectory with at least a `stat.npy` file:

```
raw_data/
├── recording_A/
│   └── suite2p/
│       └── plane0/
│           ├── F.npy
│           ├── spks.npy
│           ├── iscell.npy
│           ├── stat.npy
│           └── ops.npy
└── recording_B/
    └── suite2p/
        └── plane0/
            └── ...
```

### Using the CAT-NAP tab

1. Enter (or browse to) your raw data folder in the **Suite2p recordings** section — or paste a **Dropbox folder share link**, which is scanned without downloading anything.
2. Click **Scan for suite2p folders**. All discovered recordings appear in the list; a ✓ prefix means denoising outputs already exist.
3. Click **Make spreadsheet from these…** to turn the scan into the batch spreadsheet, with names taken from the data rather than retyped and DIV read out of each name. Fill in the genotype column (or **Fill from another sheet…** to copy DIV and genotype from an existing spreadsheet, matched by name even when the folders carry a trailing word the sheet doesn't). Saving points the Paths tab at it.
4. Click a recording to load it. The info panel shows cell count, sampling rate, and duration. Recordings behind a share link have nothing local to preview or denoise here — the pipeline run fetches them one at a time.
5. (Optional) Adjust denoising settings and click **Run denoising on selected recording** to generate `Fdenoised.npy` and peak detection outputs.
6. Use the **Trace preview** panel on the right to inspect individual cell traces, switching between activity types.

### Activity types

| Type | Description |
|---|---|
| `peaks` | Detected calcium transient onset frames (from denoising pipeline) |
| `denoised F` | Baseline-corrected, OASIS-deconvolved fluorescence |
| `F` | Raw fluorescence as output by suite2p |
| `spks` | Inferred spike probabilities from suite2p |

### Denoising pipeline

The denoising runs on raw fluorescence (`F.npy`) and produces outputs saved alongside the suite2p files:

1. **Polynomial baseline** (`pybaselines.imodpoly`) — estimate and remove slow drift
2. **OASIS deconvolution** — separate calcium signal from noise (requires optional install; see below)
3. **Peak detection** (`scipy.signal.find_peaks`) — find calcium transient events
4. Outputs saved: `Fdenoised.npy`, `timePoints.npy`, `peakStartFrames.npy`, `peakEndFrames.npy`, `peakHeights.npy`, `eventAreas.npy`

#### OASIS (optional)

OASIS deconvolution is not available on PyPI. If it is not installed, the pipeline falls back to Savitzky-Golay smoothing, which is noted with a warning in the CAT-NAP tab. To install OASIS:

```bash
pip install git+https://github.com/j-friedrich/OASIS.git
```

### Using CAT-NAP from Python

```python
from meanap.catnap.scanner import find_suite2p_recordings
from meanap.catnap.loader import load_suite2p
from meanap.catnap.denoising import process_suite2p_folder

# Discover all suite2p recordings under a folder
recordings = find_suite2p_recordings("/path/to/raw_data")
for rec in recordings:
    print(rec.name, rec.suite2p_dir, rec.has_denoised)

# Load one recording
data = load_suite2p(recordings[0].suite2p_dir)
print(data.n_cells, data.fs, data.duration_s)
print(data.F_cells.shape)    # (n_cells, n_frames)
print(data.xy_cells.shape)   # (n_cells, 2)

# Run denoising (writes output .npy files next to the inputs)
process_suite2p_folder(
    recordings[0].suite2p_dir,
    overwrite=False,
    denoising_threshold=1.3,
    time_before_peak_s=1.0,
    time_after_peak_s=2.05,
)

# Reload to get denoised data
data = load_suite2p(recordings[0].suite2p_dir)
print(data.F_denoised_cells.shape)   # (n_cells, n_frames)
print(data.peak_start_frames.shape)  # (n_rois, max_peaks), NaN-padded
```

## Network Viewer

The Network Viewer tab lets you interactively explore the functional connectivity network from a completed MEA-NAP run, including optional cell-type overlays. It mirrors the functionality of the MATLAB `runMEANAPviewer.m` viewer.

### Using the Network Viewer tab

1. Click **Browse…** and select a MEA-NAP output `.mat` file from the `ExperimentMatFiles/` subfolder of an output directory (e.g. `OutputData.../ExperimentMatFiles/<recording>_OutputData....mat`).
2. The network renders immediately. Recording metadata (name, DIV, group, active node count) appears in the left panel.
3. Adjust settings to update the plot in real time:
   - **Lag** — choose between the available functional connectivity lag values (e.g. 1000 ms, 2500 ms, 5000 ms)
   - **Edge threshold** — minimum correlation weight required to draw an edge
   - **Node color metric** — colour nodes by any node-level metric in the file (betweenness centrality, node strength, z-score, etc.), or leave as **None** for flat cyan nodes
4. (Optional) Click **Load cell types from file…** to overlay cell-type information — see below.

Node **size** is always proportional to node degree (ND). Node **color** is driven by the selected metric using the viridis colormap, with a colorbar legend shown on the right.

### Cell-type overlay

Cell-type information is displayed as concentric rings on each node, with a distinct line style per cell type, mirroring the MATLAB viewer.

**Loading cell types:**

1. Prepare (or locate) a cell-type spreadsheet. Each column represents one cell type; each cell contains the channel number (1-indexed) of a cell belonging to that type. Columns with no cells for that type should be left empty/NaN. The `PutativeCellType_*.xlsx` files produced alongside MEA-NAP runs use this format.

   Example layout:

   | NeuN+ | PV+ | SST+ |
   |---|---|---|
   | 68 | 25 | 110 |
   | 78 | 42 | 216 |
   | 117 | | |

2. In the **Cell types** group, click **Load cell types from file…** and select the `.xlsx` or `.csv` file.
3. A listbox appears listing all cell types found in the file. Select one or more to filter the displayed network.

**Filtering by cell type:**

- Selecting one type shows only nodes belonging to that type.
- Selecting multiple types shows only nodes that belong to **all** selected types (intersection, consistent with the MATLAB viewer).
- Deselecting everything (no types highlighted) returns to showing all active nodes.

The concentric circle legend at the bottom of the plot identifies which ring style corresponds to each cell type.

> **Note on `.mat` cell-type data:** MEA-NAP stores `Info.CellTypes` inside output `.mat` files as a MATLAB MCOS table object. Python's `scipy.io` cannot decode this format. When the viewer detects this it logs a message and prompts you to load the cell-type spreadsheet directly — the same `.xlsx` file that was originally supplied to the MATLAB pipeline.

### Using the network plotting API from Python

The underlying plotting code is available independently of the GUI:

```python
import numpy as np
from meanap.network_plot import (
    MatData,
    load_cell_type_file,
    build_cell_type_matrix,
    filter_by_cell_types,
    plot_network,
)
import matplotlib.pyplot as plt

# Load a MEA-NAP output .mat file
data = MatData("path/to/ExperimentMatFiles/recording_OutputData.mat")

print(data.lag_keys)          # ['adjM1000mslag', 'adjM2500mslag', ...]
print(data.available_node_metrics)  # ['ND', 'NS', 'BC', 'Z', ...]

lag = data.lag_keys[0]        # e.g. 'adjM1000mslag'
active_idx = data.get_active_indices(lag)   # 0-based indices into full electrode array
adjM = data.get_adjM(lag)[np.ix_(active_idx, active_idx)]
coords = data.coords[active_idx]
z = data.get_metric(lag, "ND")       # node degree — drives node size
z2 = data.get_metric(lag, "BC")      # betweenness centrality — drives node color

# (Optional) load cell types from an Excel file
df = load_cell_type_file("path/to/PutativeCellType.xlsx")
ct_matrix, ct_names = build_cell_type_matrix(df, data.channels)
ct_active = ct_matrix[active_idx, :]

# Filter to nodes that are both NeuN+ and PV+
row_idx, ct_sub = filter_by_cell_types(
    np.arange(len(active_idx)), ct_active, ct_names, ["NeuN+", "PV+"]
)
adjM_sub = adjM[np.ix_(row_idx, row_idx)]
coords_sub = coords[row_idx]
z_sub = z[row_idx]
z2_sub = z2[row_idx]

# Plot
fig, ax = plt.subplots(figsize=(10, 8))
plot_network(
    ax, adjM_sub, coords_sub,
    edge_thresh=0.1,
    z=z_sub,               # node size (ND)
    z2=z2_sub,             # node color (BC); pass None for flat cyan
    z2_name="BC",
    cell_type_matrix=ct_sub,
    cell_type_names=ct_names,
    title="NeuN+ ∩ PV+ — 1000 ms lag",
)
plt.show()
```

## Adding dependencies

```bash
uv add <package>          # runtime dependency
uv add --dev <package>    # dev-only (pytest, ruff, etc.)
```

Both commands update `pyproject.toml` and `uv.lock` automatically.

## Core dependencies

| Package | Purpose |
|---|---|
| numpy, scipy | Numerical computing, signal processing, peak detection |
| matplotlib | Plotting and embedded trace previews |
| pandas | Data management |
| networkx | Graph theory metrics |
| h5py | Reading HDF5 / `.mat` (v7.3+) files |
| pyqt6 | Desktop GUI framework |
| pybaselines | Polynomial baseline correction for denoising |
| tqdm | Progress bars during batch denoising |
| sciplotlib | Publication-quality plot styles |
| natsort, Pillow | Utilities used in existing scripts |

## Development

Run tests:

```bash
uv run pytest
```

Lint and format:

```bash
uv run ruff check src/
uv run ruff format src/
```

## Running scripts

```bash
uv run python python/compile_plots.py
uv run jupyter notebook python/feature-schematic.ipynb
```
