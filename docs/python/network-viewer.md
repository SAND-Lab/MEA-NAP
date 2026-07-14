# Network Viewer

The **Network Viewer** tab interactively explores the functional connectivity
network from a completed MEA-NAP run, including optional cell-type overlays.
It's the Python equivalent of MATLAB's `runMEANAPviewer.m`.

## Using the Network Viewer tab

1. Click **Browse…** and select a MEA-NAP output `.mat` file from the
   `ExperimentMatFiles/` subfolder of an output directory, e.g.
   `OutputData.../ExperimentMatFiles/<recording>_OutputData....mat`.
2. The network renders immediately. Recording metadata (name, DIV, group,
   active node count) appears in the left panel.
3. Adjust settings to update the plot in real time:
   - **Lag** — which functional connectivity lag value to view (e.g. `1000
     ms`, `2500 ms`, `5000 ms`).
   - **Edge threshold** — minimum correlation weight required to draw an edge.
   - **Node color metric** — color nodes by any node-level metric present in
     the file (betweenness centrality, node strength, z-score, ...), or leave
     as **None** for flat cyan nodes.
4. (Optional) Click **Load cell types from file…** to overlay cell-type
   information — see below.

Node **size** is always proportional to node degree (ND). Node **color** uses
the viridis colormap, with a colorbar legend on the right.

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
