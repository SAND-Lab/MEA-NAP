# Network Viewer

The **Network Viewer** tab interactively explores the functional connectivity
network from a completed MEA-NAP run, including optional cell-type overlays.
It's the Python equivalent of MATLAB's `runMEANAPviewer.m`.

## Using the Network Viewer tab

When the tab first opens it shows a **built-in example network** so every
control is usable immediately — no file needed. To explore your own data:

1. Click **Browse…** and select a MEA-NAP output `.mat` file from the
   `ExperimentMatFiles/` subfolder of an output directory, e.g.
   `OutputData.../ExperimentMatFiles/<recording>_OutputData....mat`.
   (**Use example network** reloads the synthetic demo at any time.)
2. The network renders immediately. Recording metadata (name, DIV, group,
   active node count, edges shown) appears in the left panel.
3. Adjust **Network settings** to update the plot in real time:
   - **Lag** — which functional connectivity lag value to view (e.g. `1000
     ms`, `2500 ms`, `5000 ms`).
   - **Edge threshold by** / **Edge threshold** — how the minimum edge weight
     is chosen (see [Edge subsampling & thresholding](#edge-subsampling-thresholding)).
   - **Node size metric** — drive node size by any node-level metric present
     in the file (defaults to node degree, ND).
   - **Node color metric** — color nodes by any node-level metric (betweenness
     centrality, node strength, z-score, ...), or leave as **None** for flat
     cyan nodes.
4. (Optional) Click **Load cell types from file…** to overlay cell-type
   information — see below.

Node **color** uses the viridis colormap, with a colorbar legend on the right.

## Display controls

The **Display** group changes how the network is drawn — none of these alter
the underlying metrics, only the appearance:

- **Node layout** — where nodes are placed:
  - **Original (electrodes)** — the physical electrode coordinates (default).
  - **Circular**, **Spring (force)**, **Kamada-Kawai**, **Spectral**,
    **Shell** — positions derived from network topology (via networkx). These
    port MATLAB's `getNodeCoords.m` layout options and the `circular` plot
    type. Every derived layout is rescaled into the electrode bounding box so
    node, edge and legend sizing stay consistent.
- **Node size scale** — a multiplier applied to every node (MATLAB's
  `maxNodeSize`); increase it to enlarge all nodes at once.
- **Node scaling** — how the size metric maps onto node radius: **Linear**,
  **Log2**, **Log10**, **Square**, or **Cube** (port of MATLAB's
  `nodeScalingMethod` in `getNodeSize.m`).
- **Min edge width** / **Max edge width** — the line width (in points) of the
  weakest and strongest drawn edges. The viewer keeps max ≥ min automatically.

## Edge subsampling & thresholding

Dense networks can render as an unreadable hairball. Two independent controls
limit what's drawn (neither changes node degree or any other metric — they are
plotting-only, mirroring `PlotIndvNetMet.m`):

- **Max edges** (Display group) — draw only the strongest *N* edges by absolute
  weight, keeping the rest hidden (port of `limitEdgesForPlotting.m`,
  `HighToLow`). `0` (shown as *Unlimited*) draws every edge.
- **Edge threshold by** (Network settings) — how the threshold weight is chosen
  (port of `getEdgeThreshold.m`):
  - **Absolute value** — draw edges with weight ≥ the value you set (0–1).
  - **Percentile** — threshold at the Nth percentile of **all** adjacency
    entries, *including zeros* (MATLAB-faithful: on a sparse matrix a low
    percentile does nothing, so you typically need a high value).
  - **Percentile (nonzero edges)** — threshold at the Nth percentile of only
    the **actual** edge weights, so e.g. `80 %` keeps the strongest ~20 % of
    edges — the intuitive behaviour.

The **Edges shown** field updates live so you can see the effect of each control.

## Saving the plot

Click **Save plot…** (Display group) to export the current figure. Choose
**PNG** (raster, saved at **600 dpi** for publication-quality output) or
**SVG** (vector, resolution-independent). If you omit the extension it is
inferred from the selected file type. The export preserves the on-screen white
background and trims surrounding whitespace.

## Cell-type overlay

Cell types are rendered as concentric rings on each node, one line style per
type, mirroring the MATLAB viewer.

**Loading cell types:**

1. Prepare (or locate) a cell-type spreadsheet: each column is one cell type,
   each cell contains the 1-indexed channel number of a cell belonging to
   that type. Columns with no cells for a given type should be left blank.
   The `PutativeCellType_*.xlsx` files produced alongside MEA-NAP runs use
   this format.

   | NeuN+ | PV+ | SST+ |
   |---|---|---|
   | 68 | 25 | 110 |
   | 78 | 42 | 216 |
   | 117 | | |

2. In the **Cell types** group, click **Load cell types from file…** and
   select the `.xlsx` or `.csv` file.
3. A listbox appears with every cell type found — select one or more to
   filter the displayed network.

**Filtering by cell type:**

- Selecting one type shows only nodes of that type.
- Selecting multiple types shows only nodes belonging to **all** selected
  types (intersection — consistent with the MATLAB viewer).
- Deselecting everything returns to showing all active nodes.

The concentric-circle legend at the bottom of the plot identifies which ring
style corresponds to which cell type.

:::{admonition} Note on `.mat` cell-type data
:class: warning
MEA-NAP stores `Info.CellTypes` inside output `.mat` files as a MATLAB MCOS
table object, which `scipy.io` can't decode. When the viewer detects this, it
logs a message and prompts you to load the cell-type spreadsheet directly —
the same `.xlsx` file originally supplied to the MATLAB pipeline.
:::

## Using the network plotting API from Python

The plotting code underneath this tab is a standalone module,
`meanap.network_plot`, usable independently of the GUI. See the
[network-plotting notebook tutorial](notebooks/network-plotting-tutorial.ipynb)
for a runnable, end-to-end walkthrough with real output baked in, or the
[API reference](api/index.rst) for the full function/class list.
