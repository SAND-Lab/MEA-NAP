# Express mode and run bundles

A finished MEA-NAP run is mostly pictures. On the bundled example dataset, a
full run writes **483 figures and 56 MB** — of which the numbers those figures
were drawn from are about **300 KB**. Every network figure is a pure function
of that data, so carrying the pictures around means carrying a redundant copy
roughly twenty times over.

**Express mode** skips the figures that can be rebuilt later and keeps a single
`.meanap` bundle — *only* the bundle. A viewer redraws any figure on demand, in
PNG or in editable SVG, and can draw the whole output folder back out when you
need to hand results to someone who has no MEA-NAP.

```python
from meanap.params import Params
params = Params(..., express_mode=True)
```

Then browse the result:

```bash
uv run meanap-viewer path/to/OutputData….meanap
```

In the GUI it is the **Express mode** tick box on the Run tab, and it
applies to **🧪 Test pipeline** runs too.

## Where the bundle goes

Where the output folder would have been, named after the run:

```
OutputData07Aug2026.meanap      the bundle — and, for an express run, all of it
```

The output folder is **removed** once the bundle has been written, because
keeping both is keeping two copies of the same run and the folder is the larger
one. `run_pipeline` returns the bundle's path for such a run.

Removal happens only after the bundle has been opened and its manifest read
back: "the file exists" is not the same as "the file is good", and this deletes
results. A bundle that cannot be written, or will not reopen, leaves the folder
where it is and the log says which.

This is the single most common "express mode didn't produce anything" report:
the file is there, just not where the figures used to be. An express run ends
by naming it in the status log, in a framed block after the timing lines, with
the command that opens it.

To get a folder back, see [Exporting a full output
folder](#exporting-a-full-output-folder).

## Opening a bundle from the GUI

Three routes, all equivalent to running `meanap-viewer` yourself:

- **🌐 View report** after an express run — the button notices the run was
  express and opens the bundle in the viewer instead of building a
  near-empty `report.html` from the handful of figures on disk;
- **📦 Open bundle…** on the Results tab;
- **drag the `.meanap` file onto the window**.

Each bundle gets its own viewer; they all shut down when MEA-NAP closes. See
[Opening a bundle](gui-guide.md#opening-a-bundle).

## What it costs and what it saves

Measured on the same dataset and settings as the MATLAB-vs-Python comparison
(`ExampleData/`, two `NGN2_20230208_P1_DIV14` recordings, `Axion64`, lags
`[10, 25, 50]` ms, 200 thresholding shuffles), both modes run back to back on
one machine:

| Step | Full | Express |
|---|---|---|
| 1. Spike detection | 69.8s | 69.9s |
| 2. Neuronal activity | 7.7s | 0.0s |
| 3. Functional connectivity | 14.6s | 14.6s |
| 4. Network activity | 159.0s | 113.4s |
| **Total** | **251.1s** | **198.0s** |

| | figures on disk | output folder | bundle |
|---|---|---|---|
| Full | 483 | 56.4 MB | — |
| Express | 0 | none | **2.2 MB** |

**Size is the point: 25× smaller, as one file and nothing else.** Time is a secondary
benefit and a bounded one — steps 1 and 3 draw almost nothing, so their 84s can
never be saved, and step 4 keeps 113s of genuine computation (null models, NMF,
modularity) once its plotting is removed. Expect **around 20%**, and less on
datasets where spike detection dominates.

```{note}
A small single-recording dataset will suggest a much larger saving (~36% on a
16-channel recording). That is an artefact of the figure count barely shrinking
while the compute does — don't generalise from it.
```

## Express mode never changes the numbers

An express run and a full run of the same data with the same
`random_seed` write **byte-identical** CSVs at both the recording and node
level, for steps 2 and 4. Express mode changes what is *drawn*, never what is
*computed*. This is asserted in `python/test_bundle_render.py`, not assumed.

Likewise, figures redrawn from a bundle are **pixel-identical** to the ones the
pipeline would have written — the renderer calls the same plotting functions
the pipeline calls, with state reassembled from the bundle, so the two cannot
drift. All 66 per-recording network figures of the run above were verified this
way.

## What is in a bundle

A `.meanap` file is a zip whose entries mirror an output folder, so you can
open it with any zip tool and find plain CSVs inside.

```
manifest.json                              what this run is, and what can be redrawn
params.json                                every setting the run used
ExperimentMatFiles/<rec>_adjM.npz          adjacency matrices (ephys)
ExperimentMatFiles/<rec>_catnap.npz        adjacency, coordinates, cell types (CAT-NAP)
ExperimentMatFiles/<rec>_background.npz    mean projection (CAT-NAP, optional)
4_NetworkActivity/netmet_results.json      every network metric
4_NetworkActivity/*.csv                    recording- and node-level tables
2_NeuronalActivity/*.csv, ephys_results.json
1_SpikeDetection/1A_SpikeDetectedData/     spike times + the check-figure payload
```

Two of those entries are worth a word. `<rec>_step1checks.npz` (~100 KB) holds
what the spike-detection check figures *display* — the ±30 ms trace windows,
one channel's waveforms, the binned frequency curve — rather than the raw
voltage they were cut from. `<rec>_edgecheck.npz` (~10 KB) does the same for the
thresholding-stability figure, whose input is tens of megabytes of threshold
snapshots that vanish when step 3 returns.

Cell-type information travels *inside* the bundle — marker matrix, the resolved
grouping, and the expression each group was built from. A recipient with no
spreadsheet still gets the marker rings and the by-cell-type comparisons.

## Which figures survive, and which don't

**Every figure a full run writes can be drawn from a bundle.** Verified rather
than asserted: `python/test_check_figures_bundle.py` renders everything a bundle
offers and compares the set against a full run's output folder, by full relative
path — 335 of 335 on the test fixture, nothing missing and nothing extra.

The viewer rebuilds:

- the per-recording network figure set (4A), both pipelines — including the
  **batch-scaled** and **side-by-side** versions, reached through the *Scaling*
  toggle rather than as separate entries;
- the per-recording activity figures (2A) — rasters, firing-rate and burst
  heatmaps, burst-detection detail;
- the step-1 **spike-detection checks** — example traces, spike frequency,
  waveforms;
- the step-3 **edge-thresholding stability check**, per lag;
- network metrics by group and age (4B), and activity by group and age (2B),
  including the cell-type composition set;
- CAT-NAP's per-recording cell-type subnetwork figures, and the whole 4A set
  repeated per subnetwork.

One family still travels as pictures rather than as data: the **2P trace
figures** (CAT-NAP), which need the full fluorescence matrices. They are packed
into the bundle as images, and only produced at all when `num_2p_traces > 0`.

```{note}
Every bundle records what it can and cannot rebuild in `manifest.json`
(`reconstructable` / `not_reconstructable`). `not_reconstructable` is now empty
for a bundle written by this version; it is kept as a field because it is part
of the format, and because a bundle written by an *older* version may carry
families this one would rebuild — those bundles keep their figures as images
and say so, rather than claiming a payload they do not have.
```

The per-subnetwork 4A repeat is the one family that *recomputes* rather than
reassembles — the subnetwork metrics are not stored, only their summary rows —
so it reproduces the run's own figures exactly for a seeded run, and closely but
not identically with `random_seed=None`.

## Exporting a full output folder

A bundle is the right artifact for the person who ran the analysis. It is the
wrong one for the person they send it to who has no MEA-NAP: to them it is a zip
of arrays.

**Export output folder**, in the viewer's top bar, unpacks that trade. It draws
every figure the bundle can produce into the same folder layout the pipeline
itself writes, copies the data files across, and finishes with the
self-contained `report.html` browser — a folder anyone can open with nothing
installed.

```bash
uv run meanap-viewer Run.meanap      # then press "Export output folder"
```

Or from Python:

```python
from meanap.pipeline.export import export_output_folder

result = export_output_folder("Run.meanap")          # → Run/ beside the bundle
print(result.figures, result.report, result.skipped)
```

The export lands beside the bundle under its own name (`Run.meanap` → `Run/`),
stepping to `Run_v2` only if a folder is already there. On the test fixture it
is 335 figures in about 40 seconds; the figures are byte-identical to the ones a
full run would have written, because the same plotting functions draw both.

The button is hidden when the viewer was opened on an output folder rather than
a bundle — there is nothing to unpack, it is already a folder.

```{note}
Each figure is guarded independently. One that cannot be drawn is recorded in
`result.skipped` and costs its own figure, not the other several hundred.
```

## A bundle is also a resume artifact

Point `prior_analysis_path` at a `.meanap` file and the pipeline resumes from
it, exactly as it would from an output folder:

```python
params = Params(
    prior_analysis=True,
    prior_analysis_path="path/to/Run.meanap",
    start_analysis_step=4,
)
```

This works with the raw data absent entirely — the bundle carries the adjacency
matrices and, for electrophysiology, the spike times. So the file you email to
a collaborator is also the file they can re-run step 4 from, with different
network settings, and reproduce your metrics exactly.

```{note}
Spike files are small for a 64-channel recording (~0.3 MB each) but scale with
channel count and firing rate. On a large batch they may dominate the bundle.
```

See {doc}`catnap` for the CAT-NAP-specific resume notes, including why you
should resume the *whole* batch rather than a subset, and {doc}`remote-data` for
running against data that never lands on your disk — the two compose: stream the
inputs, ship a small bundle back.

## The viewer

```bash
uv run meanap-viewer path/to/Run.meanap        # or an output folder
uv run meanap-viewer Run.meanap --port 9000 --no-browser
```

(Or open it from the GUI — [above](#opening-a-bundle-from-the-gui).)

A local web app in three tabs, one per kind of question a run answers.

Every figure can be downloaded as **PNG, SVG or PDF**. SVG is real vector markup
with editable paths, so a figure can go straight into Illustrator or Inkscape
for a manuscript.

CAT-NAP's peak-detection traces are the one exception, and only for the format:
they are PNGs packed into the bundle rather than redrawn on request, so the
vector buttons are hidden for them. **Download PNG** saves the file, same as
anywhere else. (Before v1.3.1 it opened the image in a tab instead — that route
was the only one that never read the download flag.)

### Recordings

One figure at a time, with the full Network Viewer control set on the right —
node layout, colour map, edge threshold and method, maximum edges drawn, node
size and scaling, edge widths. Changing any of them re-renders through the same
Python that drew the original.

**Every control opens on the value the run itself used**, not on a generic
default, so the panel doubles as a record of how these figures were drawn.
Changes are opt-in on top of that, and **Reset** returns to it. This matters
most for **Node size**, which CAT-NAP runs leave on `Auto` — nodes sized from
how densely the cells are packed, which a two-photon field of a few hundred
cells needs and an MEA's sixty electrodes do not. Switch it to `Manual` to set
a multiplier by hand; the scale box beside it is greyed while `Auto` is on,
because nothing reads it then.

:::{note}
Before v1.3.0 the controls opened on library defaults instead. Since a request
carries only the controls you changed, changing *any* of them — a colour map,
say — also silently reset node sizing to `1.0`, which redrew a CAT-NAP network
with nodes the size of the field. Figures exported from an older viewer after
touching a control may show that; re-render them to get the run's own sizing
back.
:::

The left column lists everything a recording has, grouped by the question each
set answers: **network figures** at the selected lag, **activity figures**,
**spike detection** checks, **edge thresholding** checks, and CAT-NAP's
**cell-type subnetworks**. A set the run did not produce says so rather than
disappearing.

**Scaling** appears above the styling controls for the spatial network plots,
which the pipeline draws three ways:

| | what it shows |
|---|---|
| **Individual** | this recording's own range — the default, and the plain filename |
| **Batch-scaled** | one scale across every recording, so panels are directly comparable |
| **Side by side** | both, in one figure |

It is a toggle rather than three more buttons per figure because the three are
the same plot at different scales. It hides itself for figures that have only
one — the batch-scaled versions need a pooled bound for the figure's size
metric, which a single-recording bundle may not have.

All three take the styling controls, and all three are drawn with the run's own
node sizing and cell-type rings. (Before v1.4.0 the side-by-side figure took
neither: it ignored every control, and was drawn at `node_size_scale = 1.0`
while the two single figures beside it used the run's — so on a CAT-NAP run the
figure meant to compare two scalings matched neither of them. Re-render or
re-run to correct an affected figure; only the side-by-side one was wrong.)

### Parameters

Every setting the run used, grouped as `Params` groups them, opening on the ones
that differ from the defaults. The left column filters to a section; a toggle
expands to all ~140 fields. Remote share links are shown as a placeholder, since
a bundle is a thing people send each other.

The tab is absent for a bundle that carries no `params.json`.

### Comparisons

The 2B and 4B half-violin sets — network metrics and neuronal activity by group
and age. These are the run's bulk: on a three-lag run the 4B set alone is **274
small multiples**. Rather than show them all, the tab selects the one you want
by the address each figure actually has:

| Facet | Choices |
|---|---|
| **Lag** | the run's STTC lags (hidden for 2B activity, which has none) |
| **Level** | recording — one point per recording; node — one per node |
| **Split** | by group (panel per group, age on x), by age (panel per age, group on x), or both stacked |
| **Metric** | the metric list on the left, which follows the level |

Each figure is drawn on demand and is **byte-identical** to the one the
pipeline writes to `4B_GroupComparisons/…`; the folder and the viewer are two
routes to the same picture. On the example dataset that is 0.2 s for the figure
you asked for, against 36 s to draw all 274.

"Both" shows the two splits stacked for one metric. The download buttons are
hidden there — one button cannot mean two figures — so pick a single split to
export.

#### Colours

The same panel sets the palettes, which apply to the comparison figures and the
across-lag ones alike. The two axes are different kinds of variable and get
different kinds of palette:

| | what it is | presets |
|---|---|---|
| **Ages** | ordered, so a sequential colormap | `viridis` (default), `viridis_r`, `plasma`, `plasma_r`, `cividis`, `magma`, `inferno`, `grey` |
| **Groups** | unordered, so a categorical list | `meanap` (default, MATLAB's `groupColors`), `okabe-ito`, `tab10`, `grey` |

`okabe-ito` is worth knowing about: eight hues that stay distinguishable under
all common colour-vision deficiencies. A genotype comparison printed in a paper
will be read by someone who cannot separate the default red and green.

Either can be overridden with your own colours — hex codes or names, comma
separated, in group order or youngest age first. A short list cycles rather
than failing, and a colour that isn't one is refused with a message naming it.

```
Custom group colours:  #e63946, #1d3557
Custom age colours:    crimson, #abc, tab:blue
```

The defaults reproduce the pipeline's own figures exactly, so an untouched
panel still gives you byte-identical output.

The same settings exist as `Params` fields, so a full run can be given them up
front rather than restyled afterwards:

```python
Params(
    group_color_scheme="okabe-ito",
    age_color_scheme="cividis",
    group_colors=["#e63946", "#1d3557"],   # overrides the scheme
)
```

### Across lags

The two sets whose subject is the lag itself, and which therefore answer a
different question from anything sliced at one lag:

- **Graph metrics by lag** — one figure per recording-level metric, each
  metric's mean ± SEM against STTC lag, one line per DIV;
- **Node cartography by lag** — the six role proportions against DIV, one
  figure per lag.

This tab is absent on a single-lag run: a curve through one point says nothing.

### Galleries

A few CAT-NAP sets — activity by cell type, cell-type subnetworks — have no
per-figure address, so they stay galleries of thumbnails, listed under the
Comparisons tab and clearly separated from the faceted sets. The styling
controls are hidden outside the Recordings tab rather than disabled: they apply
to spatial network plots, and no violin or line plot reads them.

```{note}
A gallery renders its whole family at once (those plotting routines emit a
folder per call and can't be asked for a single figure), so the first view takes
a few seconds; it is then cached and instant. Thumbnails render at 96 dpi;
downloads use the authored resolution.
```

The viewer binds to `127.0.0.1` by default. A bundle is unpublished data and
nothing here authenticates anyone — only bind elsewhere on a machine where that
is deliberate.

## Relationship to `report.html`

{doc}`output-report` describes a different thing, and both are useful:

| | `report.html` | the viewer |
|---|---|---|
| needs Python running | no | yes |
| figures | whatever is on disk | rendered on demand |
| restyling | no | yes |
| vector export | no | yes |
| works on an express run | after an export | directly |

`report.html` is the right artifact for someone who should not have to install
anything. The viewer is the right one when you want to change a figure and get
a publication-ready file out — and it is how you *produce* the former from an
express run: **Export output folder** writes the figures and the `report.html`
together, which is the pair you send onward.
