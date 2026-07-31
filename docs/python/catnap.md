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

## Cell-type subnetworks

If a recording folder contains a putative-cell-type spreadsheet, CAT-NAP can
split the network by cell type and analyse each type separately — for example
comparing the excitatory and inhibitory subnetworks.

### The spreadsheet

MEA-NAP looks for a single `.csv` (or `.xlsx`) inside the recording folder,
alongside `suite2p/` — the same rule the MATLAB pipeline uses:

```
raw_data/
└── MyRecording_DIV21/
    ├── PutativeCellType_MyRecording_DIV21.csv
    └── suite2p/plane0/…
```

One column per marker; each column lists the **0-indexed suite2p ROI ids**
positive for that marker, padded with blanks to the longest column:

| NeuN+ | Mecp2+ | PV+ | GAD+ |
|---|---|---|---|
| 68 | 53 | 26 | 7 |
| 78 | 97 | 267 | 8 |
| 117 | 270 | | 9 |

### Defining subnetworks in the GUI

The **Cell-type subnetworks** box on the CAT-NAP tab does all of this without
writing expressions.

1. Tick **Analyse cell-type subnetworks**.
2. Leave **Cell-type file** blank to auto-detect a spreadsheet in each
   recording's folder, or browse to a specific one. Markers load automatically
   after a scan or when you select a recording; **Load markers** forces it.
3. Pick a **Grouping**:
   - *One subnetwork per marker* — no further setup.
   - *Excitatory vs inhibitory* — derived from the inhibitory markers present.
   - *Custom groups* — the grid below.
   - *Custom groups (expressions)* — free text, for shapes the grid can't express.

In the grid, each row is a subnetwork and each column a marker. Set every cell
to **include**, **exclude**, or **—** (irrelevant), and use **Match** to say
whether the *included* markers combine as "any of" (OR) or "all of" (AND);
excluded markers must always be absent. **Add group** appends as many
subnetworks as you want — the two starting rows are just a convenience for the
excitatory/inhibitory case, not a limit.

The **Expression** column shows exactly what each row compiles to, and the line
underneath reports how many labelled cells each group would capture, so an empty
or over-broad group is obvious before you run anything.

### Defining subnetworks in code

Set `twop_subnetwork_analysis = True`, then choose how the columns become
groups with `twop_subnetwork_groups`:

| Value | Meaning |
|---|---|
| `None` (default) | one subnetwork per spreadsheet column |
| `"E/I"` | excitatory vs inhibitory, derived from whichever inhibitory markers (`GAD+`, `PV+`, `SST+`, `VIP+`, `GABA+`) are present |
| a dict | your own named boolean combinations |

```python
from meanap.params import Params

params = Params(
    suite2p_mode=True,
    twop_subnetwork_analysis=True,
    twop_subnetwork_groups={
        "Excitatory": "NeuN+ & ~GAD+ & ~PV+ & ~SST+",
        "Inhibitory": "GAD+ | PV+ | SST+",
        "Mecp2 positive": "Mecp2+",
    },
)
```

Expressions support `&` (and), `|` (or), `~` or `!` (not) and parentheses, with
`&` binding tighter than `|` as in Python. Groups may overlap — a cell can be
both `NeuN+` and `Mecp2+` — and any group that ends up empty is dropped, so a
spec written for a rich marker panel still runs on a sparser recording.

### What comes out

Two complementary comparisons are produced for every recording and lag.

**Induced subgraphs** keep only one cell type's nodes and the edges *among*
them, then re-run the full step-4 metric suite on that subgraph. This answers
"is the inhibitory network denser / more efficient / more small-world than the
excitatory one?". Note these metrics are size-dependent, so read them alongside
each group's node count (the figures annotate it).

**Split whole-network metrics** leave the graph intact and just label each node
with its cell type, then compare the node-level distributions. This answers "are
inhibitory cells more hub-like *within the whole network*?" — usually the more
interesting question, and not the same as the first.

Figures land in
`4_NetworkActivity/4A_IndividualNetworkAnalysis/{group}/{recording}/{lag}mslag/cellTypeSubnetworks/`:

| File | Content |
|---|---|
| `1_CellTypeNetwork.png` | whole network, nodes coloured by cell type, within-type edges highlighted over pale between-type ones |
| `2_SubnetworkGraphs.png` | one panel per cell type showing just its induced subgraph, on shared axes |
| `3_NodeMetricsByCellType.png` | half-violin distributions of whole-network node metrics, split by cell type |
| `4_SubnetworkMetrics.png` | graph-level metrics of each induced subgraph, versus the whole network |
| `5_EdgeMixing.png` | cell type × cell type edge-density and mean-weight heatmaps |

2P peak/STTC networks are often more than 80% dense, so the two graph figures
draw only the strongest 3000 edges per group and say so in the panel caption.
Metrics are always computed on the complete graph.

Batch CSVs land in `4_NetworkActivity/`:

| File | One row per |
|---|---|
| `Subnetwork_RecordingLevel.csv` | recording × lag × cell type — subgraph metrics (`Dens`, `Eglob`, `SW`, `Q`, plus `*_mean` collapses of the node metrics) |
| `Subnetwork_NodeLevel.csv` | recording × lag × node × cell type — whole-network node metrics plus `WithinGroupStrengthFrac` |
| `Subnetwork_EdgeMix.csv` | recording × lag × cell-type pair — `Density`, `MeanWeightNonzero`, `MeanWeightAll` |

`Subnetwork_NodeLevel.csv` is long format: a node positive for two markers
appears once per group, so each group's distribution is complete. Nodes in no
group appear once under `Unassigned`.

### Using it directly

```python
from meanap.catnap import subnetwork as sn

table = sn.load_cell_type_table("PutativeCellType_MyRecording.csv")
groups = sn.resolve_groups(table, channels, "E/I")
print(groups.counts())          # {'Excitatory': 142, 'Inhibitory': 61}

results = sn.compute_subnetwork_metrics(adjM, spike_counts, duration_s,
                                        groups, params)
mix = sn.compute_edge_mix(adjM, groups)
nodes = sn.split_node_metrics(full_metrics, groups, channels, adj_m=adjM)
```

`python/run_catnap_subnetwork_demo.py` runs the whole thing end-to-end on the
example dataset if you want a worked example to inspect.

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
