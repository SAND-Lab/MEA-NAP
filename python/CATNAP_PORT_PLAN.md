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

---

## Reuse wins
- Denoising / peak detection (`catnap/denoising.py`) — done.
- STTC + probabilistic thresholding (`pipeline/probabilistic_threshold.py`) —
  the `peaks` adjacency path is the same machinery as ephys.
- Step-4 network metrics (`pipeline/step4.py`, `network_metrics.py`) — shared,
  already ported.
- Cell types from a spreadsheet — the network viewer already reads cell types
  from Excel/CSV rather than the MCOS `MatlabOpaque` table in the mat.
