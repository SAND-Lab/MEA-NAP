# CAT-NAP (calcium imaging) port plan

CAT-NAP is the calcium-imaging analysis pathway — the Python equivalent of
MATLAB's `suite2pToAdjm.m` → `MEApipeline.m (Params.suite2pMode == 1)` workflow.
It takes [suite2p](https://github.com/MouseLand/suite2p) output (per-cell
fluorescence) instead of raw MEA `.mat` recordings, denoises it, extracts
calcium transients ("peaks"), builds a functional-connectivity adjacency matrix,
and then reuses the **same** network-metrics machinery as the electrophysiology
(ephys) side.

This document tracks the port. For the ephys pipeline status see
`python/PIPELINE_PORT_STATUS.md`.

---

## Already ported (standalone denoising + preview tool)

A complete, GUI-wired **denoising + trace-preview** tool. It can denoise a
suite2p recording and inspect traces, but is **not yet connected** to the
network-analysis pipeline.

| Piece | File | Mirrors MATLAB |
|---|---|---|
| Folder scanner | `src/meanap/catnap/scanner.py` | `appCheckSuite2pData.m` |
| Suite2p loader (`Suite2pData`) | `src/meanap/catnap/loader.py` | the NPY reads in `suite2pToAdjm.m` |
| Denoising + peak detection | `src/meanap/catnap/denoising.py` | `denoiseSuite2pData.py` |
| GUI panel | `src/meanap/gui/panels/catnap.py` | the CAT-NAP (2P) tab |
| User docs | `docs/python/catnap.md` | — |
| Params | `src/meanap/params.py` (twop_* fields) | `getParamsFromApp.m` |

---

## The gap

Everything in `suite2pToAdjm.m` *after* denoising, plus the `suite2pMode == 1`
branches in `MEApipeline.m`, is unported. When suite2p mode is on, MATLAB:

- **replaces step 1** (spike detection) and **step 3** (connectivity) with
  `suite2pToAdjm` → produces `adjMs`, `coords`, `channels`, `activityProperties`;
- **swaps step-2 stats** for `calTwopActivityStats.m`;
- builds the activity matrix for rasters via `get2pActivityMatrix.m`;
- maps cell types via `getCellTypeMatrix.m` (from `Info.CellTypes`);
- feeds the **shared, already-ported step-4** network metrics.

---

## Parity dataset (ground truth)

`local/example2pdataWCellTypes/` is a complete CAT-NAP run. `local/` is
gitignored, so tests must **skip gracefully** when it is absent.

| Component | Path (under `local/example2pdataWCellTypes/`) |
|---|---|
| suite2p inputs (+ precomputed denoising) | `OPME…/suite2p/plane0/` |
| Cell types | `OPME…/PutativeCellType_…_PositiveOnly.csv` (cols: NeuN+/Mecp2+/PV+/SST+/GAD+) |
| Metadata (1 rec, HET, DIV21) | `Metadata_…SingleTest…csv` |
| Full `expData` mat (v7, scipy-readable) | `OutputData22May2026/ExperimentMatFiles/*.mat` |
| Step-4 `NetMet` mat (v7, scipy-readable) | `OutputData22May2026-step-4/ExperimentMatFiles/*.mat` |

**Run config** (`Params` in the mat): `suite2pMode=1`, `twopActivity='peaks'`,
`FuncConLagval=[1000, 2500, 5000]` ms, `fs=33.3` Hz, `duration=600.6` s,
`removeNodesWithNoPeaks=1`, `ProbThreshRepNum=200`, `ProbThreshTail=0.05`,
`minActivityLevel=0.01`. After iscell + no-peaks filtering: **253 nodes**,
up to 59 peaks/cell.

**Confirmed parity targets** (verified field names):

- Full `expData` mat: `adjMs.adjM{1000,2500,5000}mslag` (253×253), `coords`
  (253×2), `channels`, `F`/`denoisedF`/`spks` (20000×253), `spikeTimes`
  (cell array of structs with `.peak`, in **seconds**), `activityProperties`
  (`cellsWithPeaks, peakDurationFrames, peakHeights, eventAreas`),
  `activityStats` (`FR, FRactive, FRmean/std/sem/median/iqr, numActiveElec,
  ISImean, ISI, unitHeightMean, unitPeakDurMean, unitEventAreaMean,
  unitEventAreaSum, recHeightMean, recPeakDurMean, recEventAreaMean`).
- Step-4 mat: `NetMet` per lag (shared step 4, already ported).

> ⚠️ The `peaks` → adjM path uses probabilistic thresholding (RNG via circular
> shifts), so — exactly like the ephys STTC parity — `adjMs` match only **within
> the prob-threshold tolerance**, not bit-exact. `activityStats`, `coords`,
> `activityProperties`, and `spikeTimes` are **deterministic → exact parity**.

---

## Phases

### Phase 0 — Test scaffolding ✅ (this change)
- `python/test_pipeline_catnap.py`: standalone script (matching the other
  `test_pipeline_*.py`), skips when the local dataset is absent, loads both
  ground-truth mats, and asserts the parity targets exist / have expected
  shapes. Per-phase numeric assertions are filled in as each phase lands.

### Phase 1 — `params.suite2p_mode` + runner guard ✅ (this change)
- `Params.suite2p_mode: bool` added.
- `run_pipeline` raises `NotImplementedError` when it is set (fails loudly
  instead of running ephys steps on 2P data).
- CAT-NAP GUI panel exposes a "Analyse suite2p data (CAT-NAP)" checkbox, wired
  through `load()`/`save()`.

### Phase 3 — `catnap/stats.py` ✅
Ported `calTwopActivityStats` (`calc_twop_activity_stats`) + `getCellTypeMatrix`
(`get_cell_type_matrix`). `calc_twop_activity_stats` has **exact parity** on all
17 `activityStats` fields (verified in `test_pipeline_catnap.py`, incl. the
subtle ones: N−1 std, MATLAB `iqr` via numpy `method="hazen"`, round-half-away
scalars). `get_cell_type_matrix` logic verified against the PositiveOnly CSV
(no MATLAB output to compare — `Info.CellTypes` is an opaque MCOS table).
`get2pActivityMatrix` deferred to Phase 5 (only consumed by the raster plot).

### Phase 2 — `catnap/adjacency.py` ✅
Ported `suite2pToAdjm.m` (`suite2p_to_adjm`): iscell filter → `channels`/`coords`
(stat centroids, normalized 0→8 over the full XYloc range) → `removeNodesWithNoPeaks`
subset → `activityProperties` → adjacency (`corr` for F/spks/denoised F;
`peaks` reuses `probabilistic_threshold.adjm_thr`/STTC per lag). Verified in
`test_pipeline_catnap.py`: coords, channels, activityProperties, cellsWithPeaks,
and spikeTimes (all 253 units) **exact**; the RNG-thresholded `adjMs` checked via
the deterministic invariant "every surviving (nonzero) edge equals raw STTC" —
exact on all ~46k/40k/24k surviving edges at the three lags.

**Bug found & fixed** (`pipeline/sttc.py`): the vectorized `_run_p` used
`np.searchsorted`, which silently assumes sorted spike trains. suite2p/denoising
peak times can be **unsorted**, and MATLAB's `sttc_m.m run_P` is an
order-dependent monotonic two-pointer that never sorts — so the vectorized
version gave wrong STTC for unsorted trains (up to ~0.33 off). Replaced with a
faithful numba-jitted port of the literal loop (pure-Python fallback). Ephys STTC
exact parity preserved (max|diff|≈1e-16); full pipeline test suite still green.

### Phase 4 — Runner integration ✅
`catnap/pipeline.py::run_catnap_pipeline` orchestrates the suite2p path; `run_pipeline`
branches to it when `suite2p_mode` (replacing the Phase 1 `NotImplementedError`),
returning before the ephys steps. Per recording: `load_suite2p` → denoise if needed
(skipped when `Fdenoised.npy` cached) → `suite2p_to_adjm` → `calc_twop_activity_stats`
→ **shared** `step4.compute_network_metrics` per lag → save `netmet_results.json`,
`NetworkActivity_{Recording,Node}Level.csv`, and `TwoPhotonActivity_RecordingLevel.csv`.
Verified two ways: (1) NetMet parity — feeding MATLAB's stored (step-4-mat) adjMs
into `compute_network_metrics` reproduces `NetMet` **exactly** on all deterministic
fields (aN, Dens, Eglob, ND, NS, MEW, Eloc, BC, + scalar summaries) across the 3
lags (36/36 in `test_pipeline_catnap.py`); (2) end-to-end smoke run on the local
dataset completes and writes correct outputs (TwoPhoton stats match Phase 3;
NodeLevel = 175 active nodes). **112/112 total test checks pass.**

Network-plot generation (needs suite2p `coords` instead of an MEA channel
layout) is deferred to Phase 5.

### Phase 5 — Run-time plots ◑ (mostly done)
- **`plot2ptraces`** ✅ → `catnap/plotting.py::plot_2p_traces`: per-unit 3-panel
  figure (raw F / min-max-scaled F over denoised / denoised + event-start
  markers), saved to `2_NeuronalActivity/2A_IndividualNeuronalAnalysis/{grp}/{fn}/
  unit_<roi>_2ptraces.png`. Visually verified faithful to the MATLAB layout.
  (Deviation: takes the first N labelled ROIs, not `randsample`, for
  reproducibility.)
- **Spatial network plot** ✅ (wiring) → reuses `step4.plot_spatial_network` via
  a new `coords_override` path (`plotting_step4._prepare_network_plot_data`),
  feeding suite2p cell centroids instead of an MEA channel layout. Renders the
  `2_MEA_NetworkPlot.png` per lag. **Known gap:** node-size scaling is tuned for
  ~60 MEA electrodes, so 175 dense 2P cells overlap; MATLAB's
  `minNodeSize`/`maxNodeSize`/`nodeScaling*` params aren't ported for the dense
  2P case — a cosmetic refinement, metrics/coords are correct.
- **Raster** (`get2pActivityMatrix` → `rasterPlot`) — not yet ported.

Both `plot_2p_traces` and the network plot are wired into `run_catnap_pipeline`
(`_plot_recording`), guarded so a plotting failure never aborts the run.

### Phase 7 — Batch group × age comparison figures ✅

The per-recording figures were in place but nothing pooled the batch, so a
CAT-NAP run produced none of the `2B_`/`4B_GroupComparisons` output the ephys
path (and MATLAB's own suite2p branch, via `PlotEphysStats`/`PlotNetMet`) does.
`catnap/group_plots.py` + `pipeline.py::_plot_group_comparisons` add it:

| Family | Output | Source |
|---|---|---|
| Two-photon activity | `2_NeuronalActivity/2B_GroupComparisons/{1_NodeByGroup, 2_NodeByAge, 3_RecordingsByGroup, 4_RecordingsByAge}` | new `plot_twop_group_comparisons` |
| Network metrics | `4_NetworkActivity/4B_GroupComparisons/1_`…`6_` | **shared** `plot_step4_group_comparisons`, called unchanged |
| Cell-type subnetworks | `4_NetworkActivity/4B_GroupComparisons/8_CellTypeSubnetworks/Lag{n}ms/` | new `plot_subnetwork_group_comparisons` |

Every figure goes through the shared `plot_half_violin_by_x`
(`plotHalfViolinByX.m`), so CAT-NAP and ephys comparison plots are visually and
structurally identical. The network family needed no new code at all — CAT-NAP's
per-recording results dict already has the ephys shape.

Two-photon metrics: recording level = active-cell count, mean/median/IQR event
rate, mean inter-event interval, mean event amplitude/duration/area; node level
= event rate (all + active-only), inter-event interval, amplitude, duration,
area, total area. Rates parallel the ephys firing-rate comparisons; amplitude /
duration / area have no ephys counterpart.

Subnetwork comparisons emit one figure per (metric, cell type) rather than
crowding a third dimension into the half-violin layout, whose two axes are
already spent on group and age; `Whole network` is one of the cell types, so the
reference panel sits in the same folder. `SUBNET_GRAPH_METRICS` /
`SUBNET_NODE_METRICS` in `group_plots.py` are now the single source of truth for
which subnetwork metrics *both* the per-recording and the batch figures cover.

**Also fixed here.** The per-unit two-photon stats (`FR`, `ISI`,
`unitHeightMean`, `unitPeakDurMean`, `unitEventAreaMean`, `unitEventAreaSum`)
were computed and then dropped — `_save_catnap_results` kept only scalars, so
nothing per-cell reached disk. They now go to
`2_NeuronalActivity/TwoPhotonActivity_NodeLevel.csv`, keyed by the real suite2p
ROI id, which is also what the node-level figures plot.

### Phase 8 — Node cartography + the rest of the shared 4A figure set ✅

**The bug.** Cartography roles depend on five boundaries in the PC/Z plane.
MATLAB's `autoSetCartographyBoundaries` places them from the batch's *pooled*
PC/Z; the ephys path ports this as `step4._apply_cartography_boundaries`, run as
a reduce barrier between per-recording compute and per-recording plotting.
CAT-NAP never called it, so its `NCpn1-6` came from the fixed `Params` defaults
— the same pile-into-role-1 problem that was already fixed for ephys.

**The fix** required restructuring `run_catnap_pipeline` into the same three
phases the ephys step 4 uses, because roles are re-derived *after* every
recording is computed and everything that displays a role must come after that:

1. compute (adjacency, activity stats, network metrics per lag);
2. reduce (`_apply_cartography_boundaries` over the pooled batch, plus
   `_batch_metric_bounds` for the `_scaled` plot ranges);
3. plot (per-recording figures, subnetwork analysis, batch comparisons).

Phase 1 keeps only a small `_RecordingState` (adjacency matrices, coords,
channels, spike counts, duration, suite2p path) — the fluorescence matrices are
hundreds of MB per recording, so phase 3 re-reads them from disk for the trace
figures instead of holding a batch's worth in memory.

**Figure set.** `_plot_recording_lag` gained a `coords_all` parameter and
`plot_spatial_network_combined` a `coords_override`, so CAT-NAP now draws the
*entire* shared 4A set — connectivity stats, five spatial network plots plus
their `_scaled` and `combined` variants, node cartography, both circular plots,
graph-metrics-by-node — from suite2p centroids, with nothing duplicated from the
ephys path. Previously it drew only the base `2_MEA_NetworkPlot.png`.

**HTML report.** `report.py` had no descriptions for any CAT-NAP output and two
stale folder captions claiming group comparisons were unimplemented. Added
captions for the trace figures, the five cell-type subnetwork figures, the
pooled cartography landscape, the comparison sub-folders, generic
`*_byGroup`/`*_byDIV` half-violins (which covers the ephys side too, previously
undescribed), and all seven CAT-NAP/network CSVs.

Tests: `python/test_catnap_cartography.py` (24/24) — the barrier re-classifies
nodes and records one shared boundary set differing from the Params defaults
(on a synthetic *modular* graph, since a uniform random graph would pass
vacuously); the phase ordering is pinned by driving `run_catnap_pipeline` with
stubbed I/O and asserting no recording is plotted before all are computed and
that each carries the pooled boundaries when it is; and the whole 4A set renders
from a coordinate array with no channel layout involved.

Example run: `python/run_catnap_example.py` writes a complete output tree plus
`report.html`.

### Phase 9 — Cell-type information in the activity and network figures ✅

Cell types were confined to the `cellTypeSubnetworks` figures; every other
figure was type-blind. Three additions, all driven by the *same*
`CellTypeGroups` the subnetwork analysis already uses (resolved once per
recording in phase 1, so nothing reads the spreadsheet twice):

**1. Genetic-identity rings on every spatial network plot.** `plot_network`
already implemented MATLAB's concentric rings but nothing in the pipeline ever
passed `cell_type_matrix` — only the Network Viewer did. Now threaded through
`_plot_recording_lag` → `plot_spatial_network` → `plot_network`, and the
rendering is reworked: each marker keeps a fixed radius *and* its own colour,
negative markers are drawn faintly in the same hue instead of omitted, and the
rings are unfilled so the metric colormap stays visible underneath. MATLAB draws
all rings white and omits negatives, so a marker was identifiable only by
radius. Rings show the **raw markers**, not the user's groups — grouping
collapses information the rings deliberately keep.

**2. Activity split by cell type (2B).** `plot_half_violin_by_x` gained an
optional `series_col`: at each x position it draws one violin per series value,
with colour switching from the (redundant) x position to the series, plus a
legend. Omitting it reproduces the two-factor plot exactly — verified by
counting rendered violins. CAT-NAP uses it for per-cell activity metrics in
`1_NodeByGroup/ByCellType/` and `2_NodeByAge/ByCellType/`.

**3. Cell-type composition (2B).** Per recording × cell type: `nCells`,
`fracOfCells`, `nActiveCells`, `fracActive` → `5_CellTypeComposition/` +
`CellTypeComposition.csv`. Active membership is read off `FRactive`'s NaN
pattern, which is already the authoritative record of what the network analysis
kept. Generic over user-defined groups — nothing assumes E/I.

**4. The whole 4A figure set per subnetwork.** `_plot_recording_lag` gained
`sub_dir`, so each cell type gets its own copy of all 23 figures in
`cellTypeSubnetworks/<CellType>/`, readable directly against the whole-network
version. Subnetwork cartography is re-classified against the **whole-network**
boundaries — the subgraph's own pooled PC/Z would put the boundaries elsewhere
and "connector hub" would then mean something different in each panel. Gated by
`Params.twop_subnetwork_network_plots` since it multiplies the figure count by
roughly the number of groups.

### Phase 10 — Mean-image backdrop, linestyle rings, violin layout ✅

**Mean projection behind the network.** `plot_network` gained a `background`
`(image, extent)` param; the loader reads `ops['meanImgE']` (suite2p's
contrast-enhanced projection, falling back to `meanImg`), and
`_mean_image_background` maps it into the node coordinate frame using the
`coord_norm` now returned by `suite2p_to_adjm`. Gated by
`Params.twop_network_background`.

The alignment is the subtle part. `stat['med']` is `(row, col)` but
`suite2pToAdjm.m` stores it as `(x, y)`, so the plotted x axis is the pixel row
and the y axis the pixel column; the **image is transposed** to match, which
puts nodes on their somata without touching `coords` and therefore without
breaking the MATLAB coordinate parity test. Verified numerically on the example
data: `med` read as `(row, col)` lands 78% of cells on above-median-brightness
pixels vs 48% swapped and 50% for random pixels — an independent confirmation of
the ypix/xpix finding.

**Rings by line style, not colour.** Colour was already carrying the node
metric, so overloading it made both harder to read. Each marker now has a fixed
dash pattern (`_cell_type_styles`), drawn white over a dark halo so it stays
legible at both ends of viridis; negatives keep the same pattern at low alpha.

**Half-violin layout fix.** With a series dimension the violins overlapped —
one series' scatter dots landed on the next series' KDE fill, because
`_half_violin` hard-coded a 0.1 gap that is right for one violin per x position
but too wide when several share a slot. `gap` is now a parameter, and the series
path sizes `width`/`gap` so `2*(width + gap)` stays inside one slot. The mean
marker and SEM bar also take the series colour (darkened 55%) instead of black:
once colour is what distinguishes the series, a black marker reads as a separate
one. Non-series plots keep black, preserving the MATLAB look.

Tests: `python/test_catnap_cell_type_plots.py` (38/38) — ring counts checked
against the membership matrix rather than by eye (solid rings = positives, faint
= negatives, every node showing every slot); long-format tagging with
overlapping membership; composition consistency; and violin counts proving the
series dimension adds panels without changing the no-series output.

Tests: `python/test_catnap_group_plots.py` (49/49) — pooled-frame correctness,
folder/filename layout for all three families, degenerate batches (single
recording, empty batch, all-NaN metric, unsafe cell-type names like
`NeuN+ & ~GAD+`), and a runner save+plot tail driven with the exact structures
`run_catnap_pipeline` holds, so signature drift is caught without a full
multi-minute run.

---

### Phase 6 — Cell-type subnetworks ✅ (feature extension, no MATLAB counterpart)

MATLAB only uses `Info.CellTypes` cosmetically (concentric rings around nodes in
`StandardisedNetworkPlot.m`). This phase turns it into an analysis — the first
CAT-NAP capability that goes **beyond** the MATLAB pipeline rather than porting
it, so there is no parity ground truth; `python/test_catnap_subnetwork.py`
checks correctness/self-consistency instead (45/45).

| Piece | File |
|---|---|
| Group resolution, expressions, subgraph metrics, edge mixing, node split | `src/meanap/catnap/subnetwork.py` |
| Figures (spatial, per-group panels, metric comparisons, mixing heatmaps) | `src/meanap/catnap/subnetwork_plotting.py` |
| Runner wiring + 3 batch CSVs | `src/meanap/catnap/pipeline.py` (`_run_subnetwork_analysis`) |
| Params (`twop_subnetwork_analysis` / `_groups` / `twop_cell_type_file`) | `src/meanap/params.py` |
| GUI group editor (grid of groups × markers) | `src/meanap/gui/panels/cell_type_groups.py` |
| GUI wiring (file picker, mode combo, live validation) | `src/meanap/gui/panels/catnap.py` |
| Tests / demo run | `python/test_catnap_subnetwork.py`, `python/test_gui_cell_type_groups.py`, `python/run_catnap_subnetwork_demo.py` |
| User docs | `docs/python/catnap.md` § Cell-type subnetworks |

Two complementary comparisons, both requested and both shipped:

1. **Induced subgraphs** — restrict `adjM` to one cell type's nodes and re-run
   the *shared* `step4.compute_network_metrics`. Comparable across groups but
   size-dependent, so every figure annotates `aN`.
2. **Split whole-network node metrics** — leave the graph intact, label nodes
   by type, compare ND/NS/PC/BC/Eloc distributions. Long format (one row per
   node × group) because marker membership legitimately overlaps.

Plus **edge mixing**: a group × group density / mean-weight matrix and a
per-node `WithinGroupStrengthFrac`.

Groups come from the recording folder's cell-type spreadsheet (MATLAB's
`rawData/<FN>/*.csv` rule, extended to xlsx). Default is one group per marker
column; `twop_subnetwork_groups="E/I"` derives excitatory/inhibitory from the
inhibitory markers present; a dict takes boolean expressions
(`"NeuN+ & ~GAD+ & ~PV+"`, `&` binding tighter than `|`).

**GUI.** The CAT-NAP tab edits those expressions through a grid — rows are
groups, columns are the spreadsheet's markers, each cell is include / exclude /
irrelevant, plus a per-row any-of vs all-of match. Unlimited groups via **Add
group** (two rows by default only because E/I is the common case).
`build_group_expression` / `parse_group_expression_terms` in `subnetwork.py`
round-trip the grid ↔ expression mapping exactly, including both shipped
presets; anything the grid cannot represent (nested parens, mixed operators, a
marker absent from the loaded file) makes `set_groups` return `False` and the
panel falls back to a free-text mode, so a hand-written expression is never
silently dropped. Group sizes are counted live from the spreadsheet as an upper
bound on what a run will see.

> ⚠️ **Two upstream hangs fixed in `pipeline/null_models.py`.** Small
> subnetworks (`SST+` has 4 cells in the example data) reach graph shapes MEA
> arrays never produce, and both BCT-derived rewiring routines spin forever
> there — faithfully ported from MATLAB, which has the same bug:
> - `randmio_und_signed` (via `participation_coef_norm`) draws 4 distinct nodes
>   in a bare `while 1` → never terminates for `n < 4`. Now returns the input
>   unchanged when `n < 4`.
> - `_valid_quad_stream` (via `latmio_und_v2` / `randmio_und_v2`) searches for
>   two edges with 4 distinct endpoints in a bare `while 1` → never terminates
>   on a triangle, a star, or any degenerate component. Now bounded by a
>   k²-scaled draw budget, after which the caller stops rewiring.
>
> Both only change behaviour where MATLAB would hang; ephys parity is
> unaffected (null-model, small-worldness and step-4 suites still green).

## Reuse wins
- Denoising / peak detection (`catnap/denoising.py`) — done.
- STTC + probabilistic thresholding (`pipeline/probabilistic_threshold.py`) —
  the `peaks` adjacency path is the same machinery as ephys.
- Step-4 network metrics (`pipeline/step4.py`, `network_metrics.py`) — shared,
  already ported.
- Cell types from a spreadsheet — the network viewer already reads cell types
  from Excel/CSV rather than the MCOS `MatlabOpaque` table in the mat.
