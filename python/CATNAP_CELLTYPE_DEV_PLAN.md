# CAT-NAP: cell-type comparisons across development

Goal: compare basic (event rate, amplitude, …) and network (ND, NS, PC, Z, …)
metrics **between cell types, across development**. This includes following
tracked cells through it. Everything here must work for any CAT-NAP run:

* any marker panel;
* any group expressions (`twop_subnetwork_groups`);
* any experimental groups and lags;
* any activity measures, with one row per `ActivityType` in multi-measure runs.

Yin's dataset is the test case, not the target.

## What existed before this work (2026-10-07)

| Output | Cell type shown as |
|---|---|
| `2_NeuronalActivity/2B…/{1_NodeByGroup,2_NodeByAge}/ByCellType` | a series within each panel (good) |
| `2B…/5_CellTypeComposition` | a series within each panel |
| `4_NetworkActivity/4B…/8_CellTypeSubnetworks` | **one file per cell type**, never side by side |
| per-recording `cellTypeSubnetworks/*.png` | one recording, so no development axis |
| tracking viewer | colour and filter only, no metric plots |

The gaps:

* Every "by age" plot pools cells across recordings, so cells are treated as
  independent samples (pseudoreplication).
* None of them use tracking.
* The `final` cell-type calls (recommendation + manual override) never reach
  the pipeline figures.

## Order: A → C → D → B

### A. Tracked-cell metric table *(foundation)*
`meanap.catnap.tracking.development` → `CellTracking/TrackedCellMetrics.csv`.

One row per (tracked cell, day, lag[, ActivityType]). Each row carries:

* `celltype_<marker>` = the final call;
* every `TwoPhotonActivity_NodeLevel` column;
* every `NetworkActivity_NodeLevel` column for that lag (NaN when the cell was
  inactive that day).

Design points:

* **Network metrics are the pipeline's own whole-network node metrics**, not
  the tracking module's subgraph measures. That way trajectories and the
  cross-sectional plots describe the same numbers.
* **The core is a pure function over payloads plus frames.** A folder wrapper
  writes the CSV, and the viewer can build the same table from a bundle.
* **Matching a recording to its pipeline `FileName`:**
  1. exact name;
  2. otherwise the same set of name tokens, ignoring order, the `YYYYMMDD`
     date and the DIV, plus the same DIV.

  Runs that tracked from raw folder names need the fallback. Yin's raw names
  carry the imaging date and put the tokens in a different order from the
  spreadsheet names.
* **Matching a day's cells to pipeline `Channel`s:**
  1. `sessions[k].roi + 1` when the payload stores it;
  2. otherwise the recording's pipeline channel list, when its length equals
     the session's cell count (CAT-NAP channels are the iscell ROIs in order).

  Verified on Yin: route 2 agrees with route 1 in 104/104 sessions where both
  exist.
* **Ages:** `DIV` is the pipeline's age, which may be binned by the master
  sheet. `DIVrecorded` is the day the tracking saw.
* **When it is rebuilt:**
  * at the end of a tracking run in the pipeline;
  * by `annotate_tracking_dir`;
  * by every override save;
  * on demand: `python -m meanap.catnap.tracking.development <run>`.

### C. Longitudinal figures → `CellTracking/DevelopmentByCellType/`
* **Trajectories:** metric against age, a thin line per tracked cell plus the
  mean ± CI per cell type, faceted by group.
* **Change per cell between consecutive days**, by cell type (paired).
* **Cartography role transitions**, by cell type.
* **Cell types** are defined by a marker's +/− (default) or by the run's
  group expressions, evaluated on the final calls. Unknown stays unknown and
  is excluded, never counted as negative.
* **Stats table:** `metric ~ age × type × group + (1 | chain/cell)`, reported
  alongside a within-chain-only comparison. Genotype can be confounded with
  prep.

### D. Viewer: "Development by cell type" view in the tracking tab
* Pick the metric, cell-type definition, group, minimum days tracked and lag.
* Plots are drawn live from table A, so a saved override shows up at once.

### B. Cross-sectional pipeline fixes
* Network node metrics by cell type as a series in each panel, mirroring
  `plot_activity_by_cell_type`.
* Recording-level means per cell type, so n = recordings.
* Use the `final` calls when tracking ran.
* Re-render the existing runs from their CSVs.

## Phase C as built (`tracking/development_plots.py`)
* **Entry points:** `python -m meanap.catnap.tracking.development_plots <run>`,
  or automatically at the end of a pipeline tracking run. Express mode keeps
  the tables and skips the figures.
* **Outputs:**
  `CellTracking/DevelopmentByCellType/[<ActivityType>/]<definition>/`
  * `Activity/{1_Trajectories,2_ChangePerCell}/<metric>.png`
  * `Network/<Lag>/{1_Trajectories,2_ChangePerCell}/<metric>.png` and
    `3_RoleTransitions.png`
  * `CellSlopes.csv`, `Stats_MixedModel.csv` and `Stats_WithinChain.csv` at
    the top of the folder.
* **Definitions:** one per marker (`M+` vs `M-`), plus the run's
  `twop_subnetwork_groups` (a dict, or `E/I`). These are evaluated in Kleene
  logic on the final calls. A type needs at least 5 tracked cells.
* **Mixed model:** `metric ~ age(weeks) * type [* group]`, with a random
  intercept **and age slope** per chain plus a cell intercept within each
  chain.
  * Without the per-chain slope the model is badly anticonservative. On Yin,
    Mecp2 × age for ND came out at p = 8e-7 with intercepts only and
    p = 0.59 with slopes; the within-chain test agrees with the latter. A
    test guards this.
  * The optimisers are tried in turn (lbfgs, then bfgs, then powell); all
    588 Yin rows converge.
  * Only groups that contain every type are fitted, and the `note` column
    names the rest. For example, Mecp2 in a WT/KO run.
* **Within-chain:** the per-chain difference in level and in slope between
  types, tested with Wilcoxon signed-rank across chains. Needs at least 5
  chains.
* **FDR:** `q` is the Benjamini–Hochberg adjusted p. It is computed within one
  question (definition × block × lag × term, plus the comparison, measure and
  group for the within-chain test) across metrics. On Yin, PV+ > PV− in event
  amplitude and area survives in both tests.
* **`NDnorm`** (ND / (active cells − 1)) was added to table A. Raw ND moves
  with network size, which shows up as whole chains of identical slopes.
* **Cost on Yin:** 172 figures plus 84 model fits take about 1m40s. Fits run
  through `parallel.map_recordings` with BLAS pinned to one thread.
  Unpinned, the same run cost 95 CPU-minutes.

## Phase D as built (viewer → Cell tracking → "Development by cell type")
* **`/api/trackingdevelopment`:** with no parameters it returns the
  cell-days, the metrics, and every definition's member rows. The members
  come from `development_plots.memberships`, the same function the figures
  use. With `?metric=&lag=&measure=` it returns that metric's values aligned
  to the cell-days, plus its rows from the saved stats tables.
* **Live decisions:** the final calls are re-applied on every visit (sidecar
  for bundles), so a decision saved in the cells view shows on return.
  `statsStale` flags when decisions are newer than the saved stats, which
  are not recomputed in the viewer.
* **Controls:** the split, metric, lag, measure, minimum days tracked, and
  whether to include days added by position.
* **Panels:**
  * per-group trajectories, with means of chain means and a t CI over chains;
  * change per cell, where clicking a chain ring opens that chain's network;
  * the stats tables, with q < 0.05 in bold.
* **Defaults and links:** the view opens on the split whose smallest type is
  largest. Links may carry `?tab=tracking&view=development&def=…&metric=…`.
* **Palette:** `TYPE_COLOURS` slots 4–6 were re-stepped so the palette passes
  the validator on the dark background too.
* **Not yet exercised in a live browser:** hover tooltips and the
  click-through. The layout was checked in headless-Chrome screenshots, in
  light and dark.

## Status
- [x] A
- [x] C
- [x] D
- [ ] B
