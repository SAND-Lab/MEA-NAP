# MEA-NAP Python Port — Status Handoff

Living status doc for the MATLAB → Python port of the MEA-NAP pipeline. Read this
first before making changes to `src/meanap/pipeline/` or the Pipeline/Test-pipeline
GUI wiring — it captures decisions and gotchas that aren't obvious from the code
alone.

## Where things stand

| Step | MATLAB source | Python status |
|---|---|---|
| 1. Spike detection | `Functions/WATERS-master/*`, `detectSpikes*.m` | **Done**, validated against MATLAB reference output, wired into the GUI (Run + Test pipeline) |
| 2. Neuronal activity (firing rates, burst detection) | `Functions/firingRatesBursts.m`, `Functions/singleChannelBurstDetection.m` | **Done**, validated against MATLAB reference output (100% parity on recording- and node-level fields), wired into `runner.py` |
| 3. Functional connectivity (STTC) | `Functions/generateAdjMs.m`, `Functions/STTCandThresholding/*` | **Core (STTC) done**, exact parity. Probabilistic thresholding ported but inherently non-bit-reproducible (see below) |
| 4. Network metrics | `Functions/ExtractNetMet.m`, `Functions/2019_03_03_BCT/*` | **Deterministic subset done** (ND, NS, MEW, Dens, CC, PL, Eglob, Eloc, BC, NE), 100% parity. **Modularity-dependent subset also done** (Ci/Q/nMod via Louvain + consensus clustering, raw + *normalized* PC, Z, node cartography 6-role classification, Hub3/Hub4, rich club RC) — 100% parity for everything downstream of a fixed Ci (and, for PC-normalization, a fixed PC_norm too); the stochastic pieces themselves (Ci, PC_norm's null-model randomization) aren't bit-reproducible, same situation as Step 3. Small-worldness (SW/SWw, the *saved* CC/PL) still NOT ported — see `network_metrics.py` docstring |

All four pipeline steps are wired into `runner.py` and reachable from the GUI
(`start`/`stop_analysis_step` now goes up to 4). Output folder structure (the
static tree `CreateOutputFolders.m` builds) is fully ported and used
automatically whenever the pipeline runs — diffed directly against
`OutputData03Mar2026/` (a real MATLAB run) and matches.

**MATLAB is available on this machine** (`/usr/local/bin/matlab`, licensed,
confirmed working). This was the key that unlocked exact-parity testing for
steps 3-4: MATLAB's own pipeline never persists the intermediate values
needed to isolate each step's arithmetic (e.g. the raw unthresholded STTC
matrix, or network metrics computed from a *fixed* adjacency matrix), so
`python/test_fixtures/gen_sttc_reference.m` and `gen_step4_reference.m` call
the relevant MATLAB/BCT functions directly to generate ground truth, saved
as `.npz` fixtures (see "How to verify changes" below to regenerate them).
Don't assume this MATLAB install will be present in every future environment
— treat the fixtures as the durable artifact, the `.m` scripts as how to
regenerate them if the underlying algorithms ever need re-validating.

## Key files

- `src/meanap/pipeline/io.py` — HDF5/v7.3 `.mat` I/O: `load_raw_recording`,
  `load_spike_times_mat`, `save_spike_times_npz`, `load_spike_times_npz`.
- `src/meanap/pipeline/spike_detection.py` — the ported detection algorithms
  (threshold + bior1.5 wavelet CWT). ~540 lines, see "Spike detection gotchas"
  below before touching this.
- `src/meanap/pipeline/output_folders.py` — `create_output_folders()`, a literal
  port of `CreateOutputFolders.m`'s folder list.
- `src/meanap/pipeline/spreadsheet.py` — `read_recording_csv()` /
  `parse_spreadsheet_range()`, port of `pipelineReadCSV.m`.
- `src/meanap/pipeline/example_data.py` — `download_example_data()`, port of
  `downloadExampleData.m` (Dropbox source only, not the Harvard Dataverse path).
- `src/meanap/pipeline/runner.py` — `run_pipeline(params, log)`, the new
  top-level orchestrator that MEApipeline.m corresponds to. Creates the output
  folders, reads the recording spreadsheet, then runs whichever steps fall in
  `[params.start_analysis_step, params.stop_analysis_step]`. **All four steps
  are implemented** (each guarded independently by `start <= N <= stop`, so
  e.g. `start=3, stop=4` correctly skips 1-2 and reads 1-2's saved outputs
  from disk instead — this was a latent bug for step 2 before this session,
  which ran whenever `stop >= 2` regardless of `start`).
- `src/meanap/pipeline/step2.py` — `_run_step2_neuronal_activity()`, called
  from `runner.py` when `stop_analysis_step >= 2`. Loads each recording's
  Step 1 `.npz` spike times (filtered to `params.spikes_method`), peeks the
  raw `.mat` file's HDF5 shape to get `duration_s`, calls
  `firing_rates_bursts()`, writes per-recording check plots, and dumps every
  recording's `ephys` dict to `2_NeuronalActivity/ephys_results.json`.
  (`step2_runner_snippet.py` alongside it is a stale draft of the same
  function — safe to delete, superseded by `step2.py`.)
- `src/meanap/pipeline/firing_rates.py` — `firing_rates_bursts()`, the port of
  `firingRatesBursts.m`: per-channel firing rates + active-electrode
  filtering, network burst stats (rate, mean length, ISI within/outside,
  CV of inter-burst interval, fraction of spikes in bursts), and single-channel
  burst stats. Returns the `ephys` dict with MATLAB-matching field names
  (`FRmean`, `NBurstRate`, `channelBurstDur`, etc.) — see
  `python/test_pipeline_step2.py` for the full field list.
- `src/meanap/pipeline/burst_detection.py` — `get_isin_threshold()` (Bakkum's
  automatic ISI_N threshold via histogram peak-finding), `burst_detect_isin()`
  (the core ISI_N burst assignment), `burst_detect_network()` (all-channel
  network bursts), `single_channel_burst_detection()` (per-channel bursts).
  Port of `singleChannelBurstDetection.m` + the network-burst half of
  `firingRatesBursts.m`. See "Burst detection gotchas" below.
- `src/meanap/pipeline/plotting_step2.py`, `parula.py` — Step 2 check plots
  (firing rate heatmap, raster, burst heatmaps); `parula.py` is a manual port
  of MATLAB's `parula` colormap (not in matplotlib) used by the heatmaps.
- `src/meanap/pipeline/sttc.py` — `get_sttc()`, the deterministic Spike Time
  Tiling Coefficient computation, port of `get_sttc.m` + `sttc_m.m`
  (Cutts & Eglen 2014). Vectorized with `np.searchsorted` rather than a
  literal two-pointer transliteration — see "STTC gotchas" below for why
  that's still exactly equivalent. **Bit-exact parity** (~1e-15 max diff,
  floating-point noise) confirmed against MATLAB's own `get_sttc.m` (called
  directly via `python/test_fixtures/gen_sttc_reference.m`) on both example
  recordings at 3 lag values.
- `src/meanap/pipeline/probabilistic_threshold.py` — `adjm_thr()` /
  `circular_shift_spikes()`, port of `adjM_thr_parallel.m`'s significance
  thresholding (circular-shift surrogates + upper-tail cutoff). **Not
  bit-reproducible against MATLAB** — see the module's own docstring and
  "STTC gotchas" below.
- `src/meanap/pipeline/step3.py` — `_run_step3_functional_connectivity()`.
  Loads each recording's Step 1 spike times, computes `adjm_thr()` per lag in
  `params.func_con_lag_val`, and saves both the thresholded
  (`adjM{lag}mslag`) and raw (`adjM{lag}mslag_raw`) matrices to
  `ExperimentMatFiles/<recording>_adjM.npz`.
- `src/meanap/pipeline/network_metrics.py` — deterministic BCT-equivalent
  functions (`find_node_deg_edge_weight`, `strengths_und`, `density_und`,
  `clustering_coef_wu`, `distance_wei`, `charpath`, `efficiency_wei_global`,
  `efficiency_wei_local`, `betweenness_wei`), hand-ported from
  `Functions/2019_03_03_BCT/*.m` (not via networkx — see "Network metrics
  gotchas" below for why), **plus** the modularity-dependent functions:
  `participation_coef` (raw, Guimera-Amaral, deterministic given Ci),
  `participation_coef_norm` (**this is what MATLAB actually saves as
  `NetMet.PC`** — see "Network metrics gotchas"; additionally stochastic,
  100 null-model randomizations via `null_models.py` on top of Ci),
  `module_degree_zscore`, `rich_club_wu`, `classify_node_cartography`
  (6-role classification from fixed `Params` thresholds),
  `hub_classification` (Hub3/Hub4). **Read this module's docstring** before
  adding more metrics; it explains exactly which `NetMet` fields are and
  aren't in scope and why.
- `src/meanap/pipeline/louvain.py` — `community_louvain()`, single-run
  Louvain modularity optimization, hand-ported from `community_louvain.m`
  line-by-line. Sanity-checked against known theoretical values (two
  disconnected triangles → Q=0.5 exactly), not against MATLAB directly
  (inherently stochastic — see the module's docstring). **Gotcha already
  found and fixed once**: module-label renumbering (`unique(Mb)`) happens
  exactly *once* per hierarchical level, after the local-moving phase fully
  converges — not after every single node-sweep. Getting this wrong doesn't
  crash, it just silently produces a worse/wrong partition.
- `src/meanap/pipeline/modularity.py` — `mod_consensus_cluster_iterate()`,
  port of the same-named `.m` file: runs `louvain.py` 50× per round, builds
  a consensus co-classification matrix, re-clusters on the thresholded
  consensus matrix, repeats until block-diagonal (stable). ~0.3s and 2 outer
  iterations on the real 64-node example data — fast enough that this isn't
  a performance concern the way Step 3's 200-shuffle thresholding is.
- `src/meanap/pipeline/null_models.py` — `randmio_und_signed()` (Maslov &
  Sneppen 2002 degree-preserving double-edge-swap rewiring, port of
  `randmio_und_signed.m`) and `null_model_und_sign()` (degree-exact,
  strength-approximate weighted randomization, port of
  `null_model_und_sign.m`'s `wei_freq<1` periodic-resort branch — the
  default in any modern MATLAB this codebase targets). Used by
  `participation_coef_norm` below. **Performance**: `rng.choice(n, size=4,
  replace=False)` profiled at >85% of `randmio_und_signed`'s runtime for
  realistic network sizes (array-setup overhead dominates for such a tiny
  sample) — replaced with a manual batched-candidate-and-filter approach
  for a ~3.5x speedup; see the inline comment if this ever needs revisiting.
  Validated via structural invariants only (`python/
  test_pipeline_null_models.py`) — exact degree preservation and total
  weight preservation are mathematical guarantees of the algorithm
  (verified empirically), strength preservation is approximate by design
  (MATLAB's own docs say so), and none of it is bit-reproducible against
  MATLAB (stochastic — different RNG stream).
- `src/meanap/pipeline/step4.py` — `_run_step4_network_metrics()` /
  `compute_network_metrics()`. Reproduces `ExtractNetMet.m`'s active-node
  subsetting (`nodeStrength != 0 & activityLevel >= minActivityLevel`) then
  calls the `network_metrics.py` functions on the subset, and (if `params`
  is passed) the modularity-dependent metrics too — Ci/Q/nMod,
  PC/Z/RC/NdCartDiv/NCpn1-6/Hub3/Hub4. Reads Step 3's thresholded adjacency
  matrices and Step 1's spike counts; writes `4_NetworkActivity/
  netmet_results.json` and, per recording/lag, check plots under
  `4A_IndividualNetworkAnalysis/<group>/<recording>/<lag>mslag/` (see
  `plotting_step4.py`). `compute_network_metrics()`'s result dict includes
  an `adjMsub` key (the active-node-subsetted adjacency matrix) purely so
  plots can be drawn — it's stripped out before the JSON dump, don't expect
  it to round-trip.
- `src/meanap/pipeline/plotting_step4.py` — two plots:
  - `plot_connectivity_stats()`, port of `plotConnectivityProperties.m`
    (adjacency-matrix heatmap + max/mean STTC bars + ND/NS/edge-weight
    histograms, laid out via `GridSpec` to mirror MATLAB's 6x6
    `tiledlayout`). Visually cross-checked against MATLAB's own
    `1_adjM10msConnectivityStats.png` from `OutputData24Dec2025` — same
    layout, same shapes; the specific bin heights/edges differ because that
    comparison used a *different* MATLAB run's stochastically-thresholded
    adjM (expected, see Step 3 notes), not a plotting bug.
  - `plot_spatial_network()`, port of the base `2_MEA_NetworkPlot.png` +
    `3_MEA_NetworkPlotNodedegree<Metric>.png` from `StandardisedNetworkPlot.m`
    — reuses `network_plot.py`'s `plot_network()` (built for the Network
    Viewer GUI tab, already a generic MEA renderer) rather than duplicating
    it. Needs electrode coordinates — see `channel_layout.py` below. Visually
    cross-checked against MATLAB's `2_MEA_NetworkPlot.png` from
    `OutputData24Dec2025`: node positions and overall edge topology (which
    nodes are hubs, the shape of the long diagonal high-weight edges) matches
    closely; exact edge set differs only because of Step 3's inherent
    stochastic thresholding (different MATLAB run).
  - Same `plot_spatial_network()` also produces
    `4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png`, colored by
    the *normalized* PC (`metrics["PC"]`, i.e. `participation_coef_norm`'s
    1st output — matches what MATLAB actually feeds this specific plot,
    traced through `PlotIndvNetMet.m` line 119).
  - `plot_node_cartography()`, port of the top (data) panel of
    `NodeCartography.m` — PC vs. Z scatter colored by the 6 cartography
    roles, with the 5 fixed `Params` boundary lines. Also colored by the
    normalized PC now (was raw PC in an earlier version of this port — see
    "Network metrics gotchas" for why that was a real bug, not just an
    approximation choice). The bottom panel in MATLAB (a static
    `NodeCartographyDiagram.jpg` explaining the roles) is not reproduced —
    nothing data-driven to check parity against. Visually cross-checked
    against MATLAB's `9_adjM10msNodeCartography.png` from
    `OutputData24Dec2025` — same legend/colors/boundary-line mechanics; the
    specific point positions differ only because Ci and the PC
    normalization are both stochastic (expected, documented).
  - Also produces `5_MEA_NetworkPlotNodestrengthLocalefficiency.png`
    (colored by `Eloc`). **Node size here is node strength (NS), not node
    degree** — the one plot in this family that sizes differently, confirmed
    from `PlotIndvNetMet.m` directly (`nodeSizeMetricsToPlot{end+1} =
    lagNetMet.NS` specifically for the Eloc entry, everything else uses
    `lagNetMet.ND`) rather than trusting the (wrong, "node degree") wording
    in `docs/meanap-outputs.rst`'s own Figure 5 caption — the *filename*
    MATLAB itself generates (`Nodestrength...`) was the tell. Finding this
    surfaced a real bug in `network_plot.py`'s `plot_network()`: its legend
    hardcoded the label "node degree:" and formatted values as 2-digit
    integers regardless of what `z` actually was, and applied a `max(z, 3)`
    floor intended to keep integer-ND legend divisions sane — which silently
    shrank every node to a sliver when `z` was node strength (typically
    < 1). Fixed by adding a `z_name` parameter that both relabels the legend
    and switches off the degree-specific floor/integer-formatting whenever
    `z_name != "node degree"` (or `z` doesn't look integer-valued). Defaults
    preserve the Network Viewer GUI's existing behavior exactly (it always
    sizes by ND). If you add another plot that sizes by anything other than
    ND, pass `z_name` — don't skip it even if the plot "looks fine" at a
    glance, since a too-small-node bug is easy to miss visually until you
    compare side-by-side against MATLAB's own legend.
  Saved per recording/lag: `1_adjM{lag}msConnectivityStats.png`,
  `2_MEA_NetworkPlot.png` (flat, no color metric — matches MATLAB's base
  variant), `3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png` (colored
  by BC), `4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png` (colored
  by normalized PC), `5_MEA_NetworkPlotNodestrengthLocalefficiency.png`
  (colored by Eloc, sized by NS), `6_circular_NetworkPlotNodedegreeModule.png`
  (circular layout, nodes colored by community assignment Ci from
  `mod_consensus_cluster_iterate`, sized by ND — see `plotting_step4.py`'s
  `plot_circular_module_network` and the notes in this doc's "⚠️ Network metrics
  gotchas" section for why Ci is stochastic), `9_adjM{lag}msNodeCartography.png`. Still
  not ported:
  null-model panels (small-worldness — see "Network metrics gotchas"),
  controllability plots (that metric family was never scoped at all — not
  mentioned in `ExtractNetMet.m`'s own docstring list of metrics), and the
  "scaled to whole dataset" / "combined" side-by-side variants of every network
  plot (need Step 4B-style cross-recording aggregation, which doesn't exist in
  this port).
- `src/meanap/pipeline/channel_layout.py` — `get_coords_from_layout()`, port
  of `getCoordsFromLayout.m`. Supports `MCS60old`, `MCS60`, `MCS59`
  (electrode-grid layouts that drop 1-4 grounded/corner channels via a
  specific hardcoded reordering — see the module for the transcribed
  `channelsOrdering` arrays), `Axion64`, `Axion16` (simpler row/col grid
  formulas, no channel dropping). **Exact parity confirmed against MATLAB**
  for all 5 layouts (`matlab -batch` calling `getCoordsFromLayout.m`
  directly — see `python/test_fixtures/gen_coords_reference.m` if that needs
  re-verifying). The example dataset uses `Axion64`
  (`Parameters_*.csv: channelLayout=Axion64`), which is why all 64 raw
  channels appear in every step 1-4 output with none dropped — MCS-layout
  corner/ground-channel dropping was never actually exercised against real
  pipeline data, only validated against MATLAB's lookup table in isolation.
  MATLAB's `'Custom'` layout (user-drawn random coordinates) isn't ported —
  raises `ValueError` if requested.
- `src/meanap/gui/main_window.py` — `_on_run` calls `run_pipeline` synchronously
  (no worker thread yet — see Limitations). `_on_test_pipeline` downloads the
  example dataset, points the Paths tab at it, forces `start/stop_analysis_step
  = 1`, then calls `_on_run`. This mirrors `runPipelineApp.m`'s
  `TestPipelineButton` handler, which also falls through into a full pipeline
  run using the example-data settings.
- `src/meanap/gui/panels/pipeline.py` — has both "Start at step" and "Stop at
  step" spin boxes now (kept mutually consistent — moving one past the other
  drags it along). `test_btn` ("🧪 Test pipeline") sits left of Run/Stop.
- `python/test_pipeline_step1.py` — standalone parity script; downloads example
  data via `meanap.pipeline.example_data`, runs step 1, and diffs spike times
  against the MATLAB reference in `OutputData03Mar2026/`.
- `python/test_pipeline_step2.py` — standalone parity script for step 2. Unlike
  the step 1 script, it feeds `firing_rates_bursts()` the **MATLAB reference
  spike times** (loaded straight from `OutputData03Mar2026`'s `_spikes.mat`,
  method `bior1p5`) rather than Python's own step 1 output — this isolates
  step 2 arithmetic from step 1's known ~82-84% wavelet-approximation gap.
  Diffs the resulting `ephys` dict against `NeuronalActivity_RecordingLevel.csv`
  and `NeuronalActivity_NodeLevel.csv` (MATLAB's own flattened summary CSVs,
  conveniently already keyed by the same field names as `ephys`). Currently
  **100% parity** (1052/1052 checks) on both example recordings.
- `python/test_pipeline_step3.py` — two-part test. (1) Exact parity of
  `get_sttc()` against the `python/test_fixtures/*_sttc_reference.npz`
  fixtures (generated via MATLAB directly, see "Key files" above) — currently
  **exact** (~1e-15 max diff). (2) Structural sanity checks on
  `adjm_thr()`'s thresholding (symmetric, zero diagonal, thresholding only
  removes edges) — NOT a MATLAB parity check, since the RNG isn't shared.
- `python/test_pipeline_step4.py` — feeds `network_metrics.py` the **actual
  MATLAB-thresholded adjacency matrices** from a real run
  (`OutputData03Mar2026/ExperimentMatFiles/*_OutputData03Mar2026.mat`,
  `adjMs.adjM{lag}mslag`) rather than Python's own Step 3 output, isolating
  Step 4's arithmetic from Step 3's stochasticity. Diffs against
  `python/test_fixtures/*_step4_reference.npz` (MATLAB's own BCT functions,
  called directly — see `gen_step4_reference.m`). Currently **100% parity**
  (60/60 checks) across both recordings × 3 lags × 10 metrics.
- `python/test_pipeline_cartography.py` — feeds `network_metrics.py`'s
  modularity-*dependent* functions (raw participation coefficient, z-score,
  rich club, cartography classification, hub classification) a **fixed,
  MATLAB-generated Ci** (`python/test_fixtures/*_cartography_reference.npz`,
  via `gen_cartography_reference.m`) — isolating "does the deterministic
  math match" from "does the same community assignment get found" (a
  different, inherently non-bit-reproducible question — see
  `modularity.py`'s docstring). Cartography classification and hub counting
  are additionally fed a **fixed, MATLAB-generated normalized PC**
  (`PCnorm` in the fixture) since that's what MATLAB's real pipeline
  actually feeds them, not the raw PC (see "Network metrics gotchas").
  Currently **100% parity** (42/42 checks).
- `python/test_pipeline_null_models.py` — structural tests (not MATLAB
  parity, since these are stochastic) for `null_models.py` and
  `participation_coef_norm`: exact degree preservation, exact/approximate
  weight and strength preservation, boundedness, no-NaN. Also a real-data
  timing smoke test (~15-35s for 100 iterations at real recording sizes).
- `python/test_fixtures/` — `.npz` ground-truth fixtures for steps 3-4 plus
  the `.m` scripts that generated them (`gen_sttc_reference.m`,
  `gen_step4_reference.m`, `gen_cartography_reference.m`) — re-run those
  directly in MATLAB if the fixtures ever need regenerating (e.g. after an
  algorithm change).

## HTML output report (`report.py`)

`src/meanap/pipeline/report.py`'s `generate_report(output_root)` walks a
completed (or partial) MEA-NAP output folder and writes a single
self-contained `report.html` at its root — a folder tree on the left, an
image gallery with captions on the right. No server, no external JS/CSS, no
new dependencies; opens directly over `file://`. Wired into the GUI as a
"🌐 View report" button next to Run/Stop on the Pipeline tab
(`main_window.py`'s `_on_view_report`) — regenerates the report from
whatever's on disk and opens it via `webbrowser.open()`.

- **Captions are sourced from `docs/meanap-outputs.rst`** (MEA-NAP's own
  Sphinx figure-legend reference) wherever it documents a figure, reworded to
  describe what *this Python port's* plot actually shows — MATLAB's originals
  often also render "scaled to whole dataset" and "combined" side-by-side
  variants this port doesn't produce. Six step-2 burst-heatmap figures
  (`3_BurstRate_heatmap.png` through `8_BurstDetectionInfo.png`) have **no
  MATLAB documentation anywhere in the repo** (confirmed via repo-wide
  search — `MEApipeline.m` only lists the filenames, and the MATLAB plotting
  functions' own docstrings are placeholder boilerplate); their captions in
  `report.py` are original, written to match the sibling group-comparison
  figures' documented semantics for the same metric.
- **Deep-linkable**: `report.html#4_NetworkActivity/.../10mslag` auto-expands
  the sidebar tree and selects that folder on load (`openHashPath()` in the
  embedded JS). Every folder node's `path` (relative to the output root) is
  baked into the JSON tree at generation time and both drives this and lets
  you verify a filename maps to the caption you expect by reading
  `_PLOT_PATTERNS`'/`FOLDER_DESCRIPTIONS`' regexes directly rather than
  reverse-engineering the JS.
- Data files (`.npz`/`.json`/`.csv`/`.mat`) are listed (with a short caption)
  rather than embedded as images — clicking one just opens/downloads it via
  the browser's normal `file://` handling.
- Verified by rendering with headless Chrome (`google-chrome --headless
  --screenshot`, available on this machine) and visually inspecting — no
  automated test script for this one, since there's no MATLAB ground truth
  to diff an HTML report against. If the tree/gallery structure changes,
  re-screenshot a few folders by hand rather than trusting it blind.

## Spike detection gotchas (don't re-discover these)

- **bior1.5 CWT sign**: PyWavelets' `wavefun()` gives the analysis wavelet with
  the *opposite* sign to MATLAB's Wavelet Toolbox CWT. `_cwt_bior15()` must
  return `-coeffs` at the end, or F1 collapses from 0.82 → 0.10.
- **Threshold naming**: MATLAB does `strcat('thr', num2str(t))`. The Python
  `_thr_name()` helper must special-case whole numbers (`thr4` not `thr4.0`) —
  getting this wrong silently produces F1 = 0.000 because saved/loaded keys
  never match.
- **Threshold sign convention** (fixed this session — was a live bug): the
  detection formula is `threshold = median − multiplier × MAD`, so `multiplier`
  must be **positive** to push the threshold below the median for
  negative-going spikes. `Params.thresholds` used to default to
  `[-3.5, -4.5, -5.5]` (copied from an assumption that never got exercised
  end-to-end); running step 1 with those values would have pushed the
  threshold the wrong way and detected near-nothing. Fixed default to
  `[3.0, 4.0, 5.0]`, matching MATLAB's own `Params.thresholds = {'3','4','5'}`
  convention. If you see thresholds go negative anywhere again, that's a bug.
- **HDF5 loading**: all `.mat` files here are v7.3 (HDF5), so `scipy.io.loadmat`
  can't read them — everything goes through `h5py`. Raw data is stored
  `(n_channels, n_samples)` and needs `.T`. Spike times are stored as a
  `(64, 1)` array of object references into per-channel Groups keyed by method
  name (`bior1p5`, `thr4`, `thr5`), values in **seconds**.
- **Parity numbers** (from `OutputData03Mar2026`, two example recordings):
  thr4/thr5 F1 = 1.000 (exact match), bior1.5 F1 ≈ 0.82–0.84 (PyWavelets
  approximates the wavelet via cascade; MATLAB uses its native CWT — expected,
  not a bug to chase further unless parity requirements tighten).

## Burst detection gotchas (don't re-discover these)

- **`array_fracInBursts` is not a median of per-channel fractions** (fixed
  this session — was a live bug). MATLAB computes it as
  `sum(total_num_sp_in_bst(bursting_electrodes)) / sum(sum(raster))` — total
  spikes-in-bursts summed across *only the bursting* electrodes, divided by
  total spikes across *all* electrodes (`singleChannelBurstDetection.m`
  line 152). `burst_detection.py`'s `single_channel_burst_detection()` used to
  compute `np.nanmedian(all_fracs_in_burst)` instead, which returns `NaN` when
  zero channels burst — MATLAB returns `0.0` there (0 spikes-in-bursts over a
  nonzero total). Fixed by accumulating `total_sp_in_bst_sum` /
  `total_all_spikes` directly instead of medianing per-channel ratios. The
  per-channel `all_fracsInBursts` (`channelFracSpikesInBursts` in `ephys`) was
  already correct — only the aggregate was wrong.
- **Weak test coverage for the actual burst-matching logic**: on both example
  recordings, firing rates are low enough (~0.16-0.20 Hz mean) that MATLAB
  itself detects **zero bursts**, network or single-channel, for either
  spike-detection method. `test_pipeline_step2.py` therefore only proves
  Python agrees with MATLAB that there are no bursts here — it does not
  exercise whether `burst_detect_isin()` / `get_isin_threshold()` produce the
  same burst boundaries as MATLAB when bursts *do* exist. If a future dataset
  with genuine bursting activity becomes available, re-run the parity test
  against it before trusting burst-timing outputs.

## STTC gotchas (don't re-discover these)

- **`_run_p` is vectorized via `searchsorted`, not a literal port of the
  two-pointer loop in `sttc_m.m`.** The MATLAB loop advances a monotonic
  pointer `j` into the second spike train and never backtracks; this is
  mathematically equivalent to "does the nearest spike in train 2 (by
  insertion point) fall within `dt`", since both trains are sorted ascending
  — so checking the immediate left/right neighbours via `np.searchsorted` per
  spike gives identical results without the pointer bookkeeping. Confirmed
  empirically to bit-exact match MATLAB's C-mex `sttc.c` output, not just
  argued from theory — if you ever suspect this equivalence breaks (e.g. for
  unusual/degenerate spike time inputs), regenerate
  `python/test_fixtures/*_sttc_reference.npz` and check before trusting a
  change here.
- **Probabilistic thresholding (`adjMci`) is fundamentally not
  bit-reproducible against MATLAB.** `adjM_thr_parallel.m` never seeds
  MATLAB's RNG, and even two MATLAB runs of the same recording can give
  different thresholded matrices (worse if the Parallel Computing Toolbox's
  `parfor` is active — each worker gets its own substream). Don't spend time
  trying to match `adjMci` bit-for-bit; the raw `adjM` (via `get_sttc`) is
  where exact parity lives, and it's what step 4 downstream should prefer
  once cross-step chaining matters more than matching MATLAB's specific
  thresholded output for a specific past run.
- **Performance**: `get_sttc()` on the full 64-channel example recording
  takes ~0.07s (vectorized). `adjm_thr()` with `rep_num=200` (MATLAB's
  default in the reference run) costs ~200x that per lag — budget for
  ~15-80s per (recording, lag) depending on activity level; `step3.py` does
  this for every recording × lag combination in `params.func_con_lag_val`,
  so a full run can take minutes, similar to step 1's wavelet CWT.

## Network metrics gotchas (don't re-discover these)

- **MATLAB's saved `NetMet.CC` / `NetMet.PL` are NOT the plain clustering
  coefficient / path length.** They come from `small_worldness_RL_wu.m`,
  which computes the real network's `C`/`PL` and then *normalizes* them
  against randomized (`randmio_und_v2`, 5000 iterations) and lattice
  (`latmio_und_v2`, 10000 iterations) null models: `CC = C/Cl`,
  `PL(saved) = PL/PLr`. Those null models involve randomized edge rewiring
  (stochastic, like step 3's thresholding) and are NOT ported. This module's
  `CC`/`PL` are the **raw, unnormalized** values (what `small_worldness_RL_wu`
  calls `C` and `PL` internally, before the null-model division) — useful and
  fully deterministic, but a different number than what MATLAB's `NetMet.CC`
  / `NetMet.PL` fields contain. Don't compare them directly without
  remembering this distinction.
- **Hand-ported from BCT, not networkx**, even though networkx is a project
  dependency. Tried & measured: BCT's weighted formulas (especially
  `clustering_coef_wu`'s Onnela geometric-mean triangle intensity, and
  `efficiency_wei`'s modified local efficiency) don't have exact networkx
  equivalents with matching normalization — porting the BCT `.m` source
  directly (available at `Functions/2019_03_03_BCT/`) and validating against
  real MATLAB output was more reliable than trying to reverse-engineer an
  equivalence. `distance_wei` (Dijkstra) and `betweenness_wei` (Brandes') are
  vectorized-per-source-node but otherwise structurally identical to their
  `.m` counterparts — see the inline comments in `network_metrics.py` if you
  need to verify the port line-by-line against the MATLAB source.
- **Ground truth requires a fixed adjacency matrix, which MATLAB's real
  pipeline never persists on its own** (only `Ephys`, `Info`, `Params`,
  `spikeTimes`, and the *thresholded* `adjMs` are saved to
  `ExperimentMatFiles/*.mat` — never a `NetMet` struct for the example
  dataset, since step 4 was never run on it). The fixtures instead take the
  real `adjMs.adjM{lag}mslag` matrices already sitting in
  `OutputData03Mar2026/ExperimentMatFiles/` and run MATLAB's own BCT
  functions on them directly, replicating `ExtractNetMet.m`'s active-node
  subsetting logic by hand in `gen_step4_reference.m`. If `step4.py`'s
  subsetting logic ever changes, that MATLAB script's subsetting logic needs
  to change in lockstep or the fixture stops being a valid ground truth.
- **`Q`/`Ci`/`nMod` (modularity), `PC` (raw + normalized)/`Z`, `RC`, node
  cartography (`NdCartDiv`/`NCpn1-6`), `Hub3`/`Hub4` are now ported** — see
  `louvain.py` (single-run Louvain), `modularity.py` (consensus clustering
  → Ci/Q/nMod), `null_models.py` (`randmio_und_signed`,
  `null_model_und_sign` — the randomization `participation_coef_norm` needs),
  and `network_metrics.py`'s `participation_coef`, `participation_coef_norm`,
  `module_degree_zscore`, `rich_club_wu`, `classify_node_cartography`,
  `hub_classification`. Everything downstream of a fixed Ci (or, for the
  normalized PC, a fixed Ci *and* a fixed PC_norm) has **100% parity**
  against MATLAB (`python/test_pipeline_cartography.py`); the stochastic
  pieces themselves (Ci, and separately the 100 randomizations inside
  `participation_coef_norm`) aren't bit-reproducible — same situation as
  Step 3's thresholding. `participation_coef_norm` costs ~15-35s per
  (recording, lag) at real data sizes (100 randomizations × Maslov-Sneppen
  rewiring) — see `null_models.py`'s "Performance" note above if this ever
  needs to be faster.
- **Found and fixed a real bug from an earlier session (not a MATLAB bug —
  this one was mine): node cartography classification and Hub3/Hub4 were
  wired to the *raw* PC instead of the *normalized* PC** in an earlier
  version of `step4.py` and the corresponding test fixture
  (`gen_cartography_reference.m`). Traced `ExtractNetMet.m` →
  `PlotIndvNetMet.m` line 119 to confirm MATLAB's real pipeline feeds
  cartography/hub classification the *normalized* PC (the same one that
  colors `4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png`), not the
  raw Guimera-Amaral formula. Both `step4.py` and the test fixture now use
  the normalized PC for these two — confirmed 100% parity re-holds
  (`python/test_pipeline_cartography.py`, 42/42). If a metric name in
  MEA-NAP's saved output has both a "PC"-like short name and a longer
  formula-named function producing a *different* number (raw vs. normalized,
  as here — or the `CC`/`PL`/`SW` situation above), always trace which one
  the *actual plotting/downstream code* consumes before assuming the obvious
  match.
- **`Cmcblty` (communicability) is correctly NOT ported** — it's not a gap.
  MATLAB's own code path that would compute it (`fcn_find_hubs_wu.m`, called
  from a block in `ExtractNetMet.m`) is commented out (wrapped in `%{ %}`)
  in the *current* MATLAB source. It's dead code upstream too.
- **`SW`/`SWw` (small-worldness) still NOT ported** — needs the
  `randmio_und_v2`/`latmio_und_v2` null models discussed above. Lower
  priority than everything else in this list since it was the most
  stochastic *and* most computationally expensive (10000/5000 rewiring
  iterations) piece to begin with.

## ⚠️ Electrode coordinate bug — found in MATLAB, not just the Python port

**`Functions/setUpSpreadSheet.m` has a real indexing bug** that misplaces
electrodes in every spatial plot (heatmaps, network plots) for layouts where
the raw recording's channel order differs from `getCoordsFromLayout.m`'s own
internal generation order — which is the case for `Axion64` (and likely the
MCS-family layouts too). This was found and confirmed while investigating a
user report that the step-4 network plots looked rotated relative to step
2's firing-rate heatmap.

**Root cause** (`setUpSpreadSheet.m`, ~line 68):

```matlab
[channels, coords] = getCoordsFromLayout(Params.channelLayoutPerRecording{nRecording});
recordingChannels = recordingChannelData.channels;   % raw file order, e.g. 11,12,13,...,88
subsetIndex = find(ismember(channels, recordingChannels));
Params.channels{nRecording} = recordingChannels;      % raw file order
Params.coords{nRecording} = coords(subsetIndex, :);   % getCoordsFromLayout's OWN order (11,21,31,...)
```

`find(ismember(channels, recordingChannels))` does **not** reorder `coords`
to align with `recordingChannels`— since every channel is present in both
arrays, it just returns `1:64` in `channels`'s own (unreordered) order. The
result: `Params.coords{n}[i]` and `Params.channels{n}[i]` are for two
*different* physical electrodes whenever the two source orderings differ.
Every spatial plot that reads `Params.coords{ExN}` (heatmaps, network plots,
node cartography — `electrodeHeatMaps.m`, `StandardisedNetworkPlot.m`, and
others all consume this same variable with no correction) inherits the
misplacement.

**`getCoordsFromLayout.m`'s Axion64 formula itself is correct** — confirmed
against Axion Biosystems' own AxIS Navigator software manual, which states
"[t]he electrode ID consists of two digits, the column and row" and that
column/row map to the x-/y-axis respectively. That matches
`channels(i) = colIdx*10 + rowIdx`, `coords(i,:) = [spacing(colIdx),
spacing(rowIdx)]` exactly. The bug is entirely in the reindexing step, not
the coordinate formula.

**Proof**: extracted the real `Params.coords{1}` from a genuine MATLAB run
(`OutputData24Dec2025/ExperimentMatFiles/*.mat`) and reproduced the exact
`find(ismember(...))` logic in Python — it reproduces MATLAB's actual saved
coordinates exactly. Cross-checked against MATLAB's own `Ephys.FR` (channel
23 = true max firing rate for that recording) against pixel-measured
positions in the real `2_Heatmap.png` — the bug's predicted (wrong) position
matches where the brightest dot actually renders; the semantically-correct
position does not.

**Decision (2026-07-02, discussed with the user)**: the Python port
(`channel_layout.py`, `plotting_step4.py`'s `plot_spatial_network`,
`plotting_step2.py`'s `plot_heatmap`) uses the **correct** electrode-to-
coordinate mapping, not a bug-for-bug replication of MATLAB's current output.
This means Python's spatial plots will *not* pixel-match MATLAB's current
Axion64 output, but *will* be internally self-consistent (heatmap and
network plots agree with each other) and consistent with Axion's documented
convention. `plotting_step2.py` previously had its own ad-hoc, undocumented
coordinate function (`get_coords_from_chs`, since removed) that turned out
to be the *exact transpose* of the correct mapping — likely someone's
attempt to compensate for a symptom of this same bug by eye, applied to only
one of the two plot types, which is what produced the apparent
heatmap-vs-network-plot rotation mismatch the user noticed. Both now go
through `channel_layout.py` consistently.

**Not fixed**: the user asked not to touch `setUpSpreadSheet.m` for now. If
this gets revisited, the fix is to properly reorder `coords` to match
`recordingChannels`, e.g. `[~, subsetIndex] = ismember(recordingChannels,
channels); Params.coords{nRecording} = coords(subsetIndex, :);` (note
`ismember`'s second output gives the actual per-element position, unlike
`find(ismember(...))` which only gives a same-order subset).

**Open question, follow-up needed**: the user mentioned their stimulation-
data pipeline runs in MATLAB look correctly oriented already. Stimulation
plotting functions (`electrodeHeatMaps.m` et al.) consume the *same*
`Params.coords{ExN}` — no separate code path was found (confirmed via
repo-wide `grep` for `stim.*coord`). The likely reconciliation: stim-data raw
files may happen to have their `channels` field stored in an order that
already coincides with `getCoordsFromLayout`'s internal generation order,
which would make the bug not manifest for those files by coincidence, not
because of different code. Worth checking directly against a real
stimulation dataset before trusting this hypothesis.

## Spreadsheet range convention

`Params.spreadsheet_range` is a string like `"A2:A100000"`. The parser
(`parse_spreadsheet_range`) extracts the two numbers and treats them as
1-indexed **file line numbers, header = line 1** — i.e. `"A2:A3"` reads the
first two data rows, matching MATLAB's `csvRange = [2, 3]` / `DataLines`
semantics exactly. Column letters are accepted but ignored (kept for
readability/familiarity, not functionally meaningful). Default is
`"A2:A100000"` — not `"A1:Z1000"`, which would include the header as a data
row.

## Batch scaling (scaled-to-whole-dataset plots)

MATLAB renders a "scaled to entire data batch" variant of several plots so
activity/metric levels are visually comparable *across* recordings, not just
within one. It does this with a **two-pass structure**: a first pass over all
recordings computes batch-wide maxima/bounds, a second pass plots each
recording against those shared scales. This port now mirrors that:

- **Step 2 raster** (`plotting_step2.py`'s `plot_raster`, port of
  `rasterPlot.m`): now a two-panel figure — top scaled to the recording's own
  `raster_plot_upper_percentile`, bottom scaled to `spike_freq_max`, the
  batch-wide max per-channel firing rate (MATLAB's `maxValStruct.FR`).
  `step2.py` computes `spike_freq_max` after its compute loop and threads it
  into a second plotting loop. (The old single-panel raster + avg-FR histogram
  was replaced — `rasterPlot.m` has no histogram panel.)
- **Step 2 electrode + burst heatmaps** (`plotting_step2.py`'s `plot_heatmap`,
  port of `electrodeHeatMaps.m` / `plotNodeHeatmap.m`): now a two-panel figure
  when a batch max is supplied — left scaled to the recording (99th-percentile
  color axis), right scaled to the entire dataset (color axis = that metric's
  batch-wide max). `step2.py` computes a `batch_max` dict over all six of
  MATLAB's `valsTogetMax` metrics (`FR`, `channelBurstRate`, `channelBurstDur`,
  `channelFracSpikesInBursts`, `channelISIwithinBurst`, `channeISIoutsideBurst`)
  in the same compute pass and threads it into the plotting loop. Covers
  `2_Heatmap.png` (FR) + the five burst heatmaps (`3_BurstRate` … `7_ISIoutside`).
  **Verified** on A2/A3: the right ("entire dataset") panels share the same
  color ceiling (~2.75 Hz FR) across both recordings while the left panels use
  each recording's own — A3 looks vividly active scaled to itself but correctly
  reads as much quieter than A2 on the shared batch scale. (MATLAB additionally
  log-scales the BurstDur and ISIoutsideBurst heatmaps via `useLogScale`; this
  port keeps them linear for now — see limitation note. Burst heatmaps are all
  ~zero on the example data anyway, since it has no detected bursts.)
- **Step 4 network plots** (`plotting_step4.py`'s `plot_spatial_network` →
  `network_plot.py`'s `plot_network`): each spatial plot now also writes a
  `_scaled` sibling **and a `_combined` side-by-side figure**
  (`plot_spatial_network_combined`, port of MATLAB's
  `N_combined_MEA_NetworkPlot` — individual scale left, batch scale right).
  `step4.py` was restructured into compute-then-plot: the
  compute loop collects `plot_jobs`, then `_batch_metric_bounds()` pools each
  node-level metric (ND/NS/BC/PC/Eloc) across **all recordings and all lags**
  (port of `findMinMaxNetMetTable.m`, which reads the whole NodeLevel.csv
  column), then `_plot_recording_lag()` draws both variants. The scaled variant
  passes three overrides into `plot_network`: `z_scale_override` (batch max of
  the size metric → node sizes comparable across recordings), `z2_bounds_override`
  (batch min/max of the color metric), and `edge_bounds_override` fixed to
  `(0.1, 1.0)` — MATLAB hardcodes `minMax.EW = [0.1, 1]`. These mirror MATLAB's
  `useMinMaxBoundsForPlots` / `Params.metricsMinMax` mechanism exactly.
  **Verified**: on the two example recordings (A2, A3), the `_scaled` plots
  share identical legend scales (node degree max 17, BC 0–0.263, fixed edge
  weights) while the individual plots differ (A2's own ND max is 14) — i.e. the
  batch scale is genuinely shared. Because the example data is low-connectivity
  (edges ~0.04–0.10, well under the fixed `[0.1, 1]` edge scale), the scaled
  variants' edges render faint — this is faithful to MATLAB, not a bug.
- **Not batch-scaled yet**: connectivity-stats / cartography (cartography has
  fixed [0,1]×Z axes in MATLAB anyway, so there's nothing to batch-scale). Also
  the **log-scaling** MATLAB applies to the BurstDur and ISIoutsideBurst
  heatmaps (`useLogScale = [0,1,0,0,1]` in `MEApipeline.m`) is not ported — the
  Python heatmaps are linear. Low priority: it's a cosmetic axis transform, and
  it can't be exercised/verified on the example data (no bursts → all-zero burst
  metrics). Add it to `plot_heatmap` (a `log_scale` flag transforming values +
  color axis to log10) if a bursting dataset makes it matter.

## Known limitations / next steps

_Last audited 2026-07-03 — if you fix or port something in this list, please
either delete the item or strike it through (like the coordinate-lookup one
below) rather than leaving it to silently go stale like the previous version
of this list did._

1. ~~**Pipeline runs synchronously on the Qt UI thread.**~~ **Done** — the
   pipeline now runs on a background `QThread` (`src/meanap/gui/pipeline_worker.py`,
   `PipelineWorker`). `run_pipeline` gained a `should_cancel: CancelCheck`
   parameter (see `src/meanap/pipeline/cancellation.py`) that it polls at every
   step boundary and once per recording (and per lag inside the expensive
   step-3/4 inner loops); when it returns `True` the run unwinds by raising
   `PipelineCancelled`, which the worker turns into a `cancelled` signal.
   The GUI's Stop button (`main_window.py`'s `_on_stop`) now calls
   `worker.request_cancel()` for a real cooperative cancel — it halts at the
   next checkpoint (i.e. after the in-flight recording/lag finishes, not
   mid-computation), not just resets the buttons. Log lines and the final
   outcome come back via Qt signals (`log_message`/`finished_ok`/`cancelled`/
   `failed`) delivered on the UI thread, so no more `QApplication.processEvents()`
   pumping. `closeEvent` requests cancel + `wait(5000)` so closing the window
   mid-run doesn't destroy a live `QThread`. **Granularity caveat**: because
   cancellation is cooperative (polled at loop boundaries), a click during a
   single long operation — one recording's wavelet CWT, or one lag's
   200-shuffle thresholding — won't take effect until that operation returns.
2. **Step 4 still missing**: small-worldness (`SW`/`SWw`, and the *saved*
   `NetMet.CC`/`NetMet.PL` which are normalized through the same null models),
   controllability (`aveControl`/`modalControl` — a metric family never
   scoped in this port at all), NMF/effective-rank (`num_nnmf_components`,
   `effRank` — likewise never scoped), spatial/temporal autocorrelation.
   Everything else in `ExtractNetMet.m`'s own docstring list of metrics is
   done with either exact or "deterministic given a fixed stochastic input"
   parity — see the "Where things stand" table and `network_metrics.py`'s
   docstring for the precise breakdown. `Cmcblty` (communicability) needs no
   work: MATLAB's own code path for it is commented out upstream.
3. **Step 4 plots**: 7 of MATLAB's `4A_IndividualNetworkAnalysis` plots are
   ported (connectivity stats, base/BC/PC/Eloc-colored network plots, circular
   module-colored network plot, node cartography — see `plotting_step4.py`).
   **Batch-scaled ("scaled to entire data batch") variants are now ported** for
   the four spatial network plots (2/3/4/5) plus the two controllability plots
   (10/11) — each writes a sibling `N_scaled_MEA_NetworkPlot….png` whose node
   size / node color / edge-weight scales come from batch-wide pooled bounds
   instead of the recording's own range (see the "Batch scaling" note below).
   **The `N_combined_MEA_NetworkPlot….png` side-by-side figure is now ported
   too** (`plot_spatial_network_combined` — left panel scaled to the recording,
   right panel scaled to the batch, each with its own inline legend/colorbar;
   rendered as one two-axis figure rather than MATLAB's `copyobj` merge of two
   separate figures). Still not ported: null-model panels (needs item 2's
   small-worldness).
4. **Step 3's probabilistic thresholding is not bit-reproducible against
   MATLAB by design** (see "STTC gotchas" above) — this is not a bug to fix,
   it's inherent to comparing two independently-seeded RNG streams. The
   deterministic STTC computation itself has exact parity. Same situation for
   Step 4's modularity (Ci) and the null-model randomization inside the
   normalized participation coefficient.
5. **No `Parameters_*.csv/.mat` or `channel_layout.png` generation.** MATLAB
   writes these as part of its run; Python writes `.npz`/`.json` outputs per
   step instead (see "Key files" above for exactly what each step writes) and
   the `ExperimentMatFiles/*_adjM.npz` per-recording adjacency file from step
   3, but nothing analogous to MATLAB's single combined
   `<recording>_<output>.mat` (`Info`/`Params`/`spikeTimes`/`Ephys`/`adjMs`
   all in one file).
6. **`wid_ms` / `n_scales` / `abs_thresholds` not exposed in the GUI or
   `Params`→`SpikeDetectionParams` wiring in `runner.py`.** The runner uses
   `SpikeDetectionParams`'s own defaults (`wid_ms=(0.4, 0.8)`, `n_scales=5`)
   rather than reading them from `Params`, because `Params` has no fields for
   them yet. `abs_thresholds` is stored in `Params` but never read by the
   runner — only relative thresholds are wired up.
7. **`filter_high_pass` default is 8000.0 Hz** in `Params`, whereas the
   parity-validated example run used 6150.0 Hz — both are legitimate,
   user-tunable values; just don't be surprised if the GUI-run parity looks
   slightly different from the `test_pipeline_step1.py` numbers.
8. **The example dataset barely exercises step 3/4 downstream logic.**
   Firing rates are low enough (~0.16-0.20 Hz mean) that density stays under
   ~10% and many node pairs are disconnected (`NE=0` for those nodes,
   `PL`/`Eglob` dominated by very sparse paths) — plausible and validated
   against MATLAB, but not a stress test. If a busier reference dataset shows
   up, it's worth re-running all the parity tests against it.
9. **No full group-level (Step 2B/4B `4_RecordingsByGroup`/`5_GraphMetricsByLag`/
   etc.) analysis in the port.** Most outputs are per-recording, per-lag. The
   one exception is **batch scaling** (see the "Batch scaling" section above):
   steps 2 and 4 now do a first cross-recording pass to compute batch-wide
   plot bounds, then a second plotting pass — but this only feeds the scaled
   plot variants, it does not produce MATLAB's group-comparison figures/CSVs.
10. ~~No electrode coordinate lookup table~~ **Done** — `channel_layout.py`
    ports `getCoordsFromLayout.m` (exact parity, all 5 layouts).
11. ~~No HTML/output browser~~ **Done** — `report.py`, wired into the GUI as
    "🌐 View report" on the Pipeline tab. See its own section above.

## How to verify changes

```bash
# Standalone parity checks against MATLAB reference (no GUI, no example-data path config needed)
uv run python python/test_pipeline_step1.py
uv run python python/test_pipeline_step2.py
uv run python python/test_pipeline_step3.py
uv run python python/test_pipeline_step4.py
uv run python python/test_pipeline_cartography.py
uv run python python/test_pipeline_null_models.py
uv run python python/test_pipeline_channel_layout.py

# Full runner smoke test (creates real output folder tree + runs all 4 steps)
uv run python -c "
from pathlib import Path
from meanap.params import Params
from meanap.pipeline.runner import run_pipeline

p = Params()
p.home_dir = str(Path.cwd())
p.raw_data = str(Path.cwd() / 'ExampleData')
p.spreadsheet_file_name = str(Path.cwd() / 'ExampleData' / 'exampleData.csv')
p.spreadsheet_range = 'A2:A3'
p.output_data_folder = '/tmp/some_test_dir'
p.output_data_folder_name = 'OutputDataTest'
p.start_analysis_step = 1
p.stop_analysis_step = 4
print(run_pipeline(p, log=print))
"

# GUI smoke test
uv run meanap-gui
# Paths tab: set "MEA-NAP folder" to the repo root, then Pipeline tab → 🧪 Test pipeline
```

Note: full spike detection on the two example recordings (64 channels each,
wavelet CWT) takes several minutes on a single core — it's CPU-bound, not
stuck. Step 3 with the default `prob_thresh_rep_num=200` adds another
minute-ish per lag value on top of that (see "STTC gotchas" above). Step 4's
normalized participation coefficient adds ~15-35s per (recording, lag) on
top of that too (100 degree-preserving randomizations — see `null_models.py`
"Performance" note) — a full 2-recording × 3-lag step 4 run alone takes
~2-4 minutes; don't assume a hang.

If MATLAB is available on the machine (`which matlab`), the step 3/4 fixtures
can be regenerated with:

```bash
matlab -batch "run('python/test_fixtures/gen_sttc_reference.m')"
matlab -batch "run('python/test_fixtures/gen_step4_reference.m')"
matlab -batch "run('python/test_fixtures/gen_cartography_reference.m')"
matlab -batch "run('python/test_fixtures/gen_coords_reference.m')"
# then convert the resulting .mat files to .npz — see the comment at the
# top of gen_sttc_reference.m for the exact conversion snippet.
```
