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

| Type | Description | Connectivity measure |
|---|---|---|
| `peaks` | Detected calcium transient onset frames (from the denoising pipeline). | STTC over peak times |
| `denoised F` | Baseline-corrected, OASIS-deconvolved fluorescence. | binned correlation |
| `F` | Raw fluorescence as output by suite2p. | binned correlation |
| `spks` | Inferred spike probabilities from suite2p. | binned correlation |

The measure follows the activity type, and so does what the **Lag values (ms)**
field on the Connectivity tab means:

* `peaks` reads them as **STTC lags** — the coincidence window either side of a
  detected transient, thresholded against circular-shift surrogates.
* The other three read them as **correlation bin lengths** — traces are averaged
  into bins that long, and the Pearson correlation is taken between the binned
  series. There is no lag: the correlation is at zero lag by construction, and
  no probabilistic thresholding is applied.

Either way you get one adjacency matrix, and one full set of downstream metrics
and figures, per value in the field. The GUI relabels the field (and the group
box) to say "Bin length (ms)" when a correlation activity is selected.

:::{note}
Bins are built from whole frames, so a requested length is rounded to the
nearest frame count and the trailing partial bin is dropped. The run log records
what each bin became — `1000 ms bin → 33 frames (991.0 ms)`. A bin shorter than
one frame cannot be built and collapses to a single frame, which is the
un-binned, frame-resolution correlation; the log warns when this happens, since
two different requested bins can then produce identical results. At the other
end, a bin so long that fewer than two of them fit in the recording is shortened
to half the recording — there has to be more than one bin to correlate across —
and the log says so.

Averaging and summing within a bin give the same correlations (Pearson is
scale-invariant and every kept bin holds the same number of frames), so
"mean the fluorescence" and "sum the spikes" are the same operation here.
:::

Before bin lengths were settable, these three paths correlated the raw traces at
native frame resolution and filed the result under `adjM{round(1000/fs)}mslag` —
a name that read like an STTC lag but was really just the frame period. Old
parameter files still reproduce their old numbers, since ephys-scale lags round
to a single frame.

## Output naming: lags and bins

Because the number means a different thing in each measure, the **output folders
and figure captions say which**:

| | `peaks` (STTC) | `F` / `spks` / `denoised F` (correlation) |
|---|---|---|
| Per-recording folder | `4A_.../{rec}/1000mslag/` | `4A_.../{rec}/1000msbin/` |
| Group-comparison folder | `4B_.../Lag1000ms/` | `4B_.../Bin1000ms/` |
| Figure titles / report captions | "1000 ms STTC lag" | "1000 ms correlation bin" |

Identifiers that code reads back **deliberately keep their historical spelling**:
the `adjMs` dict keys stay `adjM1000mslag`, the CSV column stays `Lag`, and
figure filenames like `NodeCartography1000mslag.png` are unchanged. Those are
shared with the ephys pipeline, are the field names MATLAB writes, and are
recorded in every bundle already on disk — renaming them would buy a tidier
spelling at the cost of every existing result. Readers accept both spellings, so
a folder written either way still parses.

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
:class: important
OASIS is a compiled extension, so it is optional rather than default. Run this
from the `MEA-NAP` folder — the one holding `pyproject.toml`, which is where
you ran the original install:

```bash
cd /path/to/MEA-NAP
uv sync --extra oasis
```

Do this **before** your first run. Without it, step 2 falls back to
Savitzky-Golay smoothing, which produces a *different peak train* — and so
different adjacency matrices and different network metrics, not merely a
rougher version of the same ones. Since `Fdenoised.npy` records nothing about
how it was made, installing OASIS later will not recompute it; tick
**Redo denoising**.
:::

## What a run produces

Per recording, in
`4_NetworkActivity/4A_IndividualNetworkAnalysis/{group}/{recording}/{lag}mslag/`,
CAT-NAP draws the **same figure set as the electrophysiology pipeline** —
connectivity statistics, the five spatial network plots (plus their
batch-scaled and side-by-side combined variants), node cartography, the two
circular network plots, and graph-metrics-by-node. Node positions come from
suite2p cell centroids rather than an electrode grid; everything else is the
shared code path, so a 2P figure and an MEA figure of the same name mean the
same thing.

Per cell, `2_NeuronalActivity/2A_IndividualNeuronalAnalysis/{group}/{recording}/`
holds `unit_<roi>_2ptraces.png` — raw fluorescence, the raw trace scaled over
the denoised one, and the denoised trace with detected event onsets. Check
these first: if the event markers don't sit on real transients, retune the
denoising threshold before trusting anything downstream.

### The field of view beside the network

Each lag folder gets one extra figure, `12_MeanImageAndNetwork.png`: the imaged
field (suite2p's mean projection — `meanImgE` when present, else `meanImg`) on
the left, the network derived from it on the right, on identical axes so a
position on one panel is the same position on the other. It is the quickest way
to check the analysis is looking at real cells. Set
`twop_network_background = False` to skip it.

Side by side rather than overlaid: superimposing the two sounds better but
doesn't work in practice — a few hundred nodes plus a dense edge set cover the
image completely, so the thing you wanted to look at is exactly the thing that
gets hidden.

:::{admonition} How the image is aligned
:class: note
suite2p's `stat['med']` is `(row, column)`, but `suite2pToAdjm.m` stores it as
if it were `(x, y)`, and this port keeps that for exact parity with MATLAB's
saved coordinates. The plotted x axis is therefore the pixel *row* and the y
axis the pixel *column*, so the backdrop is transposed to match. Transposing
the picture rather than the coordinates puts each node on its own soma without
breaking parity. Verified on the example data: reading `med` as `(row, column)`
lands 78% of cells on above-median-brightness pixels, against 48% for the
swapped reading and 50% for random pixels.
:::

### Genetic identity on the network plots

When a recording has a cell-type spreadsheet, every spatial network plot draws
each node's **full genetic identity** as concentric marker rings: one ring per
spreadsheet column, at a radius fixed by that column's position, in that
marker's own dash pattern — bright where the cell is positive for the marker,
faint where it is negative. A cell that is negative for everything still shows
every slot, so "not positive" is distinguishable from "not measured".

Three things to note:

- Markers are distinguished by **line style, not colour**. Colour is already
  carrying the node metric on most of these figures, and overloading it makes
  both harder to read. Each ring is drawn white over a dark halo so the pattern
  stays legible at either end of the viridis colormap.
- The rings show the **raw markers**, not the groups you defined. Grouping
  (`Excitatory` vs `Inhibitory`) collapses information; the rings deliberately
  don't, so `NeuN+ PV+` and `NeuN+ SST+` cells stay distinguishable even when
  both were grouped as inhibitory.
- Rings are unfilled, so the node's interior still carries whatever metric that
  figure colours by (participation coefficient, betweenness, …).

MATLAB draws these rings too, but all solid white, so a marker is identifiable
only by which radius its ring sits at, and negative markers are not drawn at
all.

:::{admonition} Rings need room
:class: warning
With many markers, or a dense field of cells whose plotted nodes overlap, the
rings become hard to read however they're drawn. They work best on sparser
fields — the per-cell-type subnetwork figures are usually the clearest place to
read them.
:::

### Node cartography

Cartography roles depend on five boundaries in the participation-coefficient /
within-module-z-score plane. With `auto_set_cartography_boundaries` (the
default), CAT-NAP pools PC and Z over **every recording in the batch** and
places the boundaries where that dataset's nodes actually cluster, exactly as
MATLAB's `autoSetCartographyBoundaries` does — the fixed `Params` defaults are
tuned for MEA data and put almost every 2P cell in the peripheral-node role.

The pooled landscape those boundaries came from is saved to
`4B_GroupComparisons/7_DensityLandscape/`, and the resulting roles feed the
per-recording cartography figures and the `NCpn1`–`NCpn6` columns of
`NetworkActivity_RecordingLevel.csv`.

:::{admonition} Boundaries are a property of the batch, not the recording
:class: note
Because they are derived from the pooled data, adding or removing recordings
changes the boundaries and therefore every recording's roles. Role proportions
are comparable *within* a run, not across two runs over different recording
sets.
:::

## Batch comparisons across groups and ages

Once every recording has been analysed, CAT-NAP pools them and draws the same
half-violin comparison figures the electrophysiology pipeline produces, in the
same folders — so a 2P batch and an MEA batch have an identically-shaped output
tree.

**Calcium activity** — `2_NeuronalActivity/2B_GroupComparisons/`:

| Folder | Content |
|---|---|
| `3_RecordingsByGroup/HalfViolinPlots` | one recording-level metric per figure, subplot per experimental group, x-axis = age |
| `4_RecordingsByAge/HalfViolinPlots` | the same metrics, subplot per age, x-axis = experimental group |
| `1_NodeByGroup`, `2_NodeByAge` | the per-cell metrics, laid out the same way |

Recording-level metrics are the number of active cells, mean/median/IQR event
rate, mean inter-event interval, and mean event amplitude, duration and area.
Per-cell metrics are event rate (all cells and active-only), mean inter-event
interval, and mean amplitude, duration, area and total area. The rate metrics
are the calcium counterparts of the ephys firing-rate ones; amplitude, duration
and area have no ephys equivalent.

The same pooled numbers are written to
`2_NeuronalActivity/TwoPhotonActivity_RecordingLevel.csv` and
`TwoPhotonActivity_NodeLevel.csv`.

**Split by cell type.** When cell types are available, each per-cell metric is
drawn a second time with cell type as a *third* factor — paired half-violins at
every age, within every experimental group — in
`1_NodeByGroup/ByCellType/` and `2_NodeByAge/ByCellType/`. One figure answers
"do inhibitory cells fire faster, and does that differ by genotype?", rather
than requiring two files to be compared by eye.

**Composition** lands in `5_CellTypeComposition/` and
`CellTypeComposition.csv`: per recording and cell type, the number of cells,
their fraction of all cells, the number that cleared the activity threshold and
the fraction of that type which is active. Partly a result in its own right,
partly a confound check — if one group has systematically more inhibitory cells,
differences downstream may be compositional rather than functional.

Both are generic over whatever groups you defined; nothing assumes an
excitatory/inhibitory split. Because groups may overlap, these tables are long
format (one row per cell × group), so `nCells` need not sum to the recording's
cell count.

**Network metrics** — `4_NetworkActivity/4B_GroupComparisons/`, folders `1_`
through `6_`, one sub-folder per lag. These come from the shared step-4
comparison plotter, so they cover exactly the metrics the ephys pipeline
compares (density, efficiency, small-worldness, modularity, node degree,
participation coefficient, node cartography proportions, …).

:::{admonition} Metrics only separate if the spreadsheet says so
:class: note
Both the group and the age axes are read from the recording-list spreadsheet
(`Grp` and `DIV` columns). A batch that is all one group at one age still
produces every figure — each will just have a single panel with a single
distribution.
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

### The full figure set, per cell type

Alongside those five, each cell type gets its **own copy of the entire step-4A
figure set** in `cellTypeSubnetworks/<CellType>/` — the same renderer as the
whole network, pointed at that type's induced subgraph. So
`cellTypeSubnetworks/Inhibitory/2_MEA_NetworkPlot.png` can be read directly
against the whole-network `2_MEA_NetworkPlot.png` one folder up.

Cartography roles inside a subnetwork are classified against the
**whole-network** boundaries rather than the subgraph's own. The subgraph's
pooled PC/Z would place its boundaries somewhere else entirely, and then
"connector hub" would mean a different thing in each panel.

This multiplies the per-recording figure count by roughly the number of groups.
Set `twop_subnetwork_network_plots = False` to keep the analysis and the five
summary figures without it.

Batch CSVs land in `4_NetworkActivity/`:

| File | One row per |
|---|---|
| `Subnetwork_RecordingLevel.csv` | recording × lag × cell type — subgraph metrics (`Dens`, `Eglob`, `SW`, `Q`, plus `*_mean` collapses of the node metrics) |
| `Subnetwork_NodeLevel.csv` | recording × lag × node × cell type — whole-network node metrics plus `WithinGroupStrengthFrac` |
| `Subnetwork_EdgeMix.csv` | recording × lag × cell-type pair — `Density`, `MeanWeightNonzero`, `MeanWeightAll` |

`Subnetwork_NodeLevel.csv` is long format: a node positive for two markers
appears once per group, so each group's distribution is complete. Nodes in no
group appear once under `Unassigned`.

### Comparing cell types across groups and ages

Those same tables are also pooled across the batch and drawn as half-violin
comparisons, under
`4_NetworkActivity/4B_GroupComparisons/8_CellTypeSubnetworks/Lag{n}ms/`:

| Folder | Content |
|---|---|
| `RecordingsByGroup`, `RecordingsByAge` | induced-subgraph metrics (`Dens`, `Eglob`, `SW`, `Q`, …) |
| `NodeByGroup`, `NodeByAge` | whole-network node metrics split by cell type, plus `WithinGroupStrengthFrac` |

There is one file per (metric, cell type) — `Dens_Inhibitory_byGroup.png` next
to `Dens_Excitatory_byGroup.png` — each laid out exactly like the whole-network
comparison of the same metric. `Whole network` is itself one of the cell types,
so `Dens_Whole_network_byGroup.png` sits in the same folder as the reference to
read the others against.

:::{admonition} Subgraph metrics are size-dependent
:class: warning
A group of 4 SST+ cells and a group of 140 excitatory cells do not have
comparable densities or small-worldness, and these figures do not correct for
that. Read `aN` (in `Subnetwork_RecordingLevel.csv`) alongside them, and treat
a difference between cell types with very different node counts as
uninterpretable. Comparing *the same* cell type across experimental groups or
ages — which is what these figures are for — is not affected.
:::

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
example dataset if you want a worked example to inspect. For the complete
output tree — every figure, every CSV and a browsable `report.html` — use
`python/run_catnap_example.py` instead.

## Re-running from a previous run

```{tip}
A run made with {doc}`express-mode` keeps a single `.meanap` bundle — no output
folder — and that file is *also* a resume artifact: point **Use prior analysis**
straight at it.
```


Every run writes one `ExperimentMatFiles/<recording>_catnap.npz` per recording,
holding the adjacency matrices and activity statistics — the products of what
MATLAB calls step 2. To re-run the network analysis without rebuilding them,
set **Start at step** to 4 on the Run tab, tick **Use prior analysis**,
and point it at the earlier `OutputData…` folder. As in MATLAB, results still
go to a fresh output folder; the previous run is only ever read.

This skips loading the suite2p data, denoising, and the STTC / probabilistic
thresholding. It always recomputes the network metrics, the node-cartography
boundaries and every figure — that is what step 4 *is*, and it is what you are
usually re-running for (changed plotting options, a different cartography
setting, an edited cell-type spreadsheet, which is re-read each run rather than
frozen into the saved file).

How much time this saves depends on where your run spends it. Thresholding
scales with recordings × lags × `probThreshRepNum`, and denoising — by far the
most expensive stage — only runs when `Fdenoised.npy` is missing or
**Redo denoising** is ticked. On the single-recording, single-lag example
dataset with denoising already cached, a resume saves roughly 13% of a ~5.5 min
run; with denoising to redo, or a real multi-recording batch, the fraction is
far larger.

Two things to be aware of:

- **Step 4 is the only resumable point.** CAT-NAP has no step 1 or 3 —
  adjacency is built in step 2, as in MATLAB — so starting at 2 or 3 is the
  same as starting at 1, and **Stop at step** has no effect. The run log says
  so rather than silently ignoring the setting.
- **Resume the whole batch, not a subset.** The node-cartography boundaries are
  placed from participation-coefficient and within-module z-score values pooled
  across *every* recording in the run. Resuming with fewer recordings re-derives
  them from that subset, so the roles won't match the original run.

With `Random seed` set, a resumed run reproduces the original run's numbers
exactly (verified on the example dataset: all four CSVs byte-identical).
Without a seed, the stochastic stages differ between any two runs anyway —
resumed or not — as they do in MATLAB.

## Browsing the output

Every run's output folder can be turned into a single self-contained
`report.html` — a folder tree on the left, an image gallery on the right, with
a caption under each figure explaining what it shows. The GUI writes it
automatically at the end of a run; from a script:

```python
from meanap.pipeline.report import generate_report
generate_report("/path/to/OutputData…")
```

No server or internet access is needed — open the file directly in a browser.

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
