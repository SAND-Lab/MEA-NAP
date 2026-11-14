---
key: cell_types
name: Cell types and subnetworks
tab: CAT-NAP (calcium imaging)
labels: Cell types: subnetworks and comparisons; Analyse cell-type subnetworks; Cell-type file; Grouping
params: twop_subnetwork_analysis, twop_cell_type_file, twop_subnetwork_groups, twop_celltype_comparison_groups
related: catnap_mode, cell_tracking
---
Uses a cell-type spreadsheet, for example from post-hoc immunostaining, to split each network by cell type and to compare cell types across groups and ages.

## What it does

The spreadsheet has one column per marker (`NeuN+`, `PV+`, `GAD+` …). Each column lists the 0-indexed suite2p ROI ids that are positive for that marker.

**Cell-type file** says where to find it:

- empty (the default): look in the recordings folder, either for `<recording>.csv` or for a single `.csv`/`.xlsx` inside the recording's own folder;
- a file: used for every recording;
- a folder: searched the same way as the recordings folder.

When there are both, CSV is preferred to Excel.

**Grouping** turns the markers into groups:

- *One subnetwork per marker*: each column is a group.
- *Excitatory vs inhibitory*: Inhibitory is any of `GAD+`, `PV+`, `SST+`, `VIP+`, `GABA+` that the sheet has. Excitatory is `NeuN+` and none of those, or just none of those if there is no `NeuN+`. With no inhibitory marker, it falls back to one group per marker.
- *Custom groups*: the grid. Each marker is *include*, *exclude* or —, and the included markers combine as any of or all of.
- *Custom groups (expressions)*: free text such as `Inhibitory = GAD+ | PV+ | SST+`, using `&`, `|`, `~` and parentheses.

Groups may overlap. A group that matches no cell is dropped.

## Choosing a value

Check the status line under the editor, which shows how many labelled cells each group captures. Size-dependent metrics (density, efficiency, small-worldness) differ between a 20-cell and a 200-cell subgraph for that reason alone, so read them with the node counts.

## How MEA-NAP uses it

With **Analyse cell-type subnetworks** ticked, for every recording and lag MEA-NAP:

- re-runs the step-4 metrics on each group's induced subgraph (its own cells and the edges among them);
- splits the whole-network node metrics by group;
- measures within- and between-type edge mixing;
- draws a full step-4A figure set per group.

Results go to `Subnetwork_*.csv`, and to `cellTypeSubnetworks/` and `8_CellTypeSubnetworks/` in the output folders.

The cell-type comparison figures across groups and development run whether or not the box is ticked, except in express mode. They use the *Multi-ID comparison splits* if any are given, and otherwise this grouping.

## Things to watch for

- ROI ids are suite2p's 0-based indices over **all** ROIs, not positions among the iscell cells.
- In the comparison splits, a cell with an unknown call for a marker is excluded, not treated as negative.
