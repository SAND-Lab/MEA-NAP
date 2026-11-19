# Quickstart

This walks through the fastest path from a fresh install to a browsable set
of results: no data preparation of your own required, using the small example
dataset bundled with MEA-NAP.

```{admonition} Before you start
:class: tip
Complete [Installation](installation.md) first (`uv sync`), so `uv run
meanap-gui` launches the desktop app.
```

## 1. Launch the GUI

```bash
uv run meanap-gui
```

MEA-NAP opens in the [simple view](gui-guide.md#simple-view): one page that
asks only for what a run needs, one question at a time. (Using the desktop
app? Open it the way you open any other app.)

## 2. Run it on the example data

Under the first question, **Recordings**, click **Or try it on the example
data**. This:

1. Downloads the example dataset (two Axion recordings, about 1.8 GB) into
   `MEA-NAP/ExampleData` in your home folder, unless it is already there.
2. Fills in the questions: the recordings folder, its spreadsheet, and the
   electrode layout, read from the recordings themselves.

Each answer gets a green tick and folds into a one-line summary. Press
**Run MEA-NAP**. The page shows the run's progress and how long is left,
and **Show log** opens the status log beside it. On a typical laptop the
run takes a few minutes; functional connectivity thresholding (step 3) and
the network-metrics null models (step 4) are the slowest parts, by design.
See [MATLAB vs. Python](matlab-vs-python.md) if you're curious why.

```{admonition} Prefer the tabs?
:class: note
**Classic view**, at the top right, switches to one tab per part of the
pipeline. There, **🧪 Test pipeline** on the **Pipeline** tab downloads the
same data and runs all four steps in one go. To see it work as fast as
possible, set **Start at step** / **Stop at step** to `1`–`2` on the Run tab
first: spike detection and firing-rate analysis alone finish in well under a
minute.
```

## 3. Browse the results

When the run finishes, click **View results**. The results viewer opens on
the run: every figure, which you can zoom and move, point at a node or a
point to read its value, and compare across recordings and DIVs. The
**View results** page also lists the other viewers (spikes and bursts,
networks) and the runs you opened recently, and takes a `.meanap` file
dropped onto it.

The simple view runs in [express mode](express-mode.md): instead of writing
every figure as a PNG, it saves the whole run as one `.meanap` file beside the
results folder, and the viewer draws any figure from it on demand. To share a
run, send that file; anyone with MEA-NAP opens it by double-clicking it or
dropping it on **View results**. For a folder of figures with a
self-contained `report.html` that opens in any browser, see
[Exporting a full output folder](express-mode.md#exporting-a-full-output-folder),
or untick **Express mode** under **Other settings › Pipeline steps and
output** before the run.

## 4. Where to go next

::::{grid} 2
:gutter: 2

:::{grid-item-card} Explore every GUI tab
:link: gui-guide
:link-type: doc
Field-by-field reference for Data, Spike detection, Connectivity, CAT-NAP,
Run, and Results.
:::

:::{grid-item-card} Script against the Python API directly
:link: notebooks/network-plotting-tutorial
:link-type: doc
Skip the GUI entirely and drive `meanap.network_plot` from a notebook or
script.
:::

:::{grid-item-card} Run on your own recordings
:link: /setting-up-meanap
:link-type: doc
The MATLAB "preparing your data" guide (spreadsheet format) applies equally to
the Python port — except that the Python port also reads Multi Channel Systems
`.h5` files directly, so you can skip the `.mat` conversion step.
:::

:::{grid-item-card} Check what's implemented
:link: matlab-vs-python
:link-type: doc
Read this before trusting the Python port's numbers for a publication figure.
:::

::::
