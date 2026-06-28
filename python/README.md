# MEA-NAP Python

A Python implementation of MEA-NAP, living alongside the MATLAB codebase in this repository.

## Project structure

```
MEA-NAP/
├── pyproject.toml        # Python project config and dependencies
├── .python-version       # Pins Python 3.13
├── uv.lock               # Reproducible dependency lockfile
├── src/
│   └── meanap/
│       ├── params.py         # Params dataclass (mirrors MATLAB Params struct)
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
