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

A tabbed desktop window opens. Each tab configures one part of the pipeline —
see the [GUI guide](gui-guide.md) for what every field does. For this
quickstart you don't need to touch any of them.

## 2. Run the test pipeline

Go to the **Pipeline** tab and click **🧪 Test pipeline**.

This single button:

1. Downloads the bundled example dataset (two short recordings) if it isn't
   already cached locally.
2. Points the **Paths** tab at it automatically.
3. Runs all four pipeline steps — spike detection, neuronal activity,
   functional connectivity, and network metrics — end to end.

Progress streams into the **Status log** at the bottom of the Pipeline tab.
On a typical laptop this takes a few minutes; functional connectivity
thresholding (step 3) and the network-metrics null models (step 4) are the
slowest parts, by design — see [MATLAB vs. Python](matlab-vs-python.md) if
you're curious why.

```{admonition} Just want to see it work as fast as possible?
:class: note
Set **Start at step** / **Stop at step** to `1`–`2` on the Pipeline tab before
clicking **Test pipeline** — spike detection and firing-rate analysis alone
finish in well under a minute, and already produce plots worth looking at.
```

## 3. Browse the results

Once the run finishes, click **🌐 View report**. This generates `report.html`
inside the output folder and opens it in your default browser — no server, no
extra install, works entirely offline.

You'll see:

- A **folder tree** on the left, matching the same output structure MATLAB's
  pipeline produces (`1_SpikeDetection`, `2_NeuronalActivity`, ...).
- A **captioned image gallery** on the right for whichever folder is
  selected — every plot the pipeline produced, with a plain-language caption.

See [Output report](output-report.md) for more on how this viewer works,
including deep links you can share to a specific plot.

## 4. Where to go next

::::{grid} 2
:gutter: 2

:::{grid-item-card} Explore every GUI tab
:link: gui-guide
:link-type: doc
Field-by-field reference for Paths, Recording, Spike detection, Connectivity,
CAT-NAP, Network Viewer, and Pipeline.
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
The MATLAB "preparing your data" guide (spreadsheet format, `.mat` conversion)
applies equally to the Python port.
:::

:::{grid-item-card} Check what's implemented
:link: matlab-vs-python
:link-type: doc
Read this before trusting the Python port's numbers for a publication figure.
:::

::::
