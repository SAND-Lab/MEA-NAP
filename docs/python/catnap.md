# CAT-NAP (calcium imaging)

CAT-NAP is the calcium-imaging analysis pathway — the Python equivalent of
MATLAB's `suite2pToAdjm` / `denoiseSuite2pData` workflow. It's triggered from
the **CAT-NAP (2P)** tab by pointing at a folder that contains
[suite2p](https://github.com/MouseLand/suite2p) output, rather than raw MEA
`.mat` recordings.

## Expected folder structure

CAT-NAP scans your raw data folder for recordings whose directory contains a
`suite2p/plane0/` subfolder with at least a `stat.npy` file:

```text
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

## Using the CAT-NAP tab

1. Enter (or browse to) your raw data folder in **Suite2p recordings**.
2. Click **Scan for suite2p folders**. Discovered recordings appear in the
   list; a ✓ prefix means denoising outputs already exist for that recording.
3. Click a recording to load it — the info panel shows cell count, sampling
   rate, and duration.
4. (Optional) Adjust denoising settings and click **Run denoising on selected
   recording** to generate `Fdenoised.npy` and peak-detection outputs.
5. Use the **Trace preview** panel to inspect individual cell traces, switching
   between the activity types below.

## Activity types

| Type | Description |
|---|---|
| `peaks` | Detected calcium transient onset frames (from the denoising pipeline). |
| `denoised F` | Baseline-corrected, OASIS-deconvolved fluorescence. |
| `F` | Raw fluorescence as output by suite2p. |
| `spks` | Inferred spike probabilities from suite2p. |

## Denoising pipeline

Runs on raw fluorescence (`F.npy`) and writes outputs alongside the suite2p
files:

1. **Polynomial baseline** (`pybaselines.imodpoly`) — estimate and remove slow
   drift.
2. **OASIS deconvolution** — separate the calcium signal from noise (requires
   the optional install below; falls back to Savitzky-Golay smoothing
   otherwise, with a warning shown in the tab).
3. **Peak detection** (`scipy.signal.find_peaks`) — find calcium transient
   events.
4. Outputs saved: `Fdenoised.npy`, `timePoints.npy`, `peakStartFrames.npy`,
   `peakEndFrames.npy`, `peakHeights.npy`, `eventAreas.npy`.

:::{admonition} Installing OASIS
:class: note
OASIS deconvolution isn't on PyPI, so it isn't installed by default:

```bash
uv run pip install git+https://github.com/j-friedrich/OASIS.git
```
:::

## Using CAT-NAP from Python

The scanner, loader, and denoising pipeline are all usable without the GUI:

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

See the [API reference](api/index.rst) for the full `meanap.catnap` surface.
