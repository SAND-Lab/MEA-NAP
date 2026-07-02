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
│               └── pipeline.py       # Run controls and status log tab
└── python/               # Scripts and notebooks (this directory)
    ├── README.md
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
uv run meanap-gui
```

The GUI is a tabbed desktop application (PyQt6) that mirrors the MATLAB App Designer interface. Each tab corresponds to a section of the pipeline:

| Tab | Description |
|---|---|
| **Paths** | Set all input/output folder and file paths, with Browse buttons |
| **Recording** | Sampling frequency, downsample rate, channel layout, potential unit |
| **Spike detection** | Thresholds, wavelet methods, bandpass filter, template settings |
| **Connectivity** | STTC lag values, adjacency matrix type, probabilistic thresholding |
| **CAT-NAP (2P)** | Suite2p pipeline — see below |
| **Network Viewer** | Interactive network plot from a MEA-NAP output `.mat` file — see below |
| **Pipeline** | Step selection, run/stop controls, status log |

### Parameters

Parameters are stored as a `Params` dataclass (`src/meanap/params.py`). Every panel exposes `load(params)` and `save(params)` methods so parameters round-trip cleanly to and from the dataclass.

Parameters can be saved and reloaded as JSON using the toolbar:

- **New** — reset everything to defaults
- **Open params…** — load a previously saved JSON file
- **Save params…** — write current settings to JSON

### Running the pipeline

Set the required paths (MEA-NAP folder, raw data folder, output folder), configure the desired tabs, then go to the **Pipeline** tab and click **Run pipeline**. The GUI validates that required paths are filled in before starting.

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

1. Enter (or browse to) your raw data folder in the **Suite2p recordings** section.
2. Click **Scan for suite2p folders**. All discovered recordings appear in the list; a ✓ prefix means denoising outputs already exist.
3. Click a recording to load it. The info panel shows cell count, sampling rate, and duration.
4. (Optional) Adjust denoising settings and click **Run denoising on selected recording** to generate `Fdenoised.npy` and peak detection outputs.
5. Use the **Trace preview** panel on the right to inspect individual cell traces, switching between activity types.

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
