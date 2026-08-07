# Express mode and run bundles

A finished MEA-NAP run is mostly pictures. On the bundled example dataset, a
full run writes **483 figures and 56 MB** — of which the numbers those figures
were drawn from are about **300 KB**. Every network figure is a pure function
of that data, so carrying the pictures around means carrying a redundant copy
roughly twenty times over.

**Express mode** skips the figures that can be rebuilt later and writes a single
`.meanap` bundle instead. A viewer redraws any figure on demand, in PNG or in
editable SVG.

```python
from meanap.params import Params
params = Params(..., express_mode=True)
```

Then browse the result:

```bash
uv run meanap-viewer path/to/OutputData….meanap
```

In the GUI it is the **Express mode** tick box on the Pipeline tab, and it
applies to **🧪 Test pipeline** runs too.

## Where the bundle goes

Beside the output folder, not inside it — the folder is named after the run and
the bundle takes the same name:

```
OutputData07Aug2026/            the output folder
OutputData07Aug2026.meanap      the bundle          ← one level up, alongside it
```

This is the single most common "express mode didn't produce anything" report:
the file is there, just not where the figures used to be. An express run ends
by naming it in the status log, in a framed block after the timing lines, with
the command that opens it.

## Opening a bundle from the GUI

Three routes, all equivalent to running `meanap-viewer` yourself:

- **🌐 View report** after an express run — the button notices the run was
  express and opens the bundle in the viewer instead of building a
  near-empty `report.html` from the handful of figures on disk;
- **Open bundle…** in the toolbar;
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

| | figures | output folder | bundle |
|---|---|---|---|
| Full | 483 | 56.4 MB | — |
| Express | 6 | 3.2 MB | **2.2 MB** |

**Size is the point: 25× smaller as a single file.** Time is a secondary
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
1_SpikeDetection/                          spike times + the checks kept as images
```

Cell-type information travels *inside* the bundle — marker matrix, the resolved
grouping, and the expression each group was built from. A recipient with no
spreadsheet still gets the marker rings and the by-cell-type comparisons.

## Which figures survive, and which don't

Express mode keeps only the quality-control figures that **cannot** be rebuilt,
because they depend on raw data far too large to carry:

- **spike-detection checks** (electrophysiology) — need the raw voltage;
- **2P trace figures** (CAT-NAP) — need the full fluorescence matrices.

Everything else is dropped and redrawn on demand. The viewer can currently
rebuild:

- the per-recording network figure set (4A) — all 11–12 figures, both pipelines;
- the per-recording activity figures (2A) — rasters, firing-rate and burst
  heatmaps, burst-detection detail;
- network metrics by group and age (4B);
- neuronal or two-photon activity by group and age (2B);
- CAT-NAP activity split by cell type, and cell-type subnetwork group
  comparisons.

```{warning}
One family is dropped and **cannot yet be rebuilt**, so an express run simply
does not have it: **`cell_type_subnetwork_per_rec`**, CAT-NAP's per-recording
cell-type subnetwork figures. This isn't fundamental — its inputs *are* in the
bundle, the reconstruction just isn't wired up — but until it is, re-run
without `express_mode` if you need those.

Every bundle records what it can and cannot rebuild in `manifest.json`
(`reconstructable` / `not_reconstructable`), so a viewer can say so rather than
leave you guessing.
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

A local web app: figure list on the left, the figure in the middle, and the
full Network Viewer control set on the right — node layout, colour map, edge
threshold and method, maximum edges drawn, node size and scaling, edge widths.
Changing any of them re-renders through the same Python that drew the original.

Defaults reproduce the pipeline's own figure exactly; the controls are opt-in
changes on top of it.

Each figure can be downloaded as **PNG, SVG or PDF**. SVG is real vector markup
with editable paths, so a figure can go straight into Illustrator or Inkscape
for a manuscript.

Comparison families are shown as a gallery of thumbnails. The styling controls
are hidden there rather than disabled — they apply to spatial network plots,
and nothing in a violin-plot gallery reads them.

```{note}
The gallery renders a whole family at once (the plotting routines emit a folder
per call and can't be asked for a single figure), so the first view of the
network family takes a few seconds; it is then cached and instant. Thumbnails
render at 96 dpi; downloads use the authored resolution.
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
| works on an express run | only the kept checks | fully |

`report.html` is the right artifact for someone who should not have to install
anything. The viewer is the right one when you want to change a figure and get
a publication-ready file out.
