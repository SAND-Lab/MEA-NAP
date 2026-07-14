# MEA-NAP Python Port — Status Handoff

Living status doc for the MATLAB → Python port of the MEA-NAP pipeline. Read this
first before making changes to `src/meanap/pipeline/` or the Pipeline/Test-pipeline
GUI wiring — it captures decisions and gotchas that aren't obvious from the code
alone.

## Where things stand

| Step | MATLAB source | Python status |
|---|---|---|
| 1. Spike detection | `Functions/WATERS-master/*`, `detectSpikes*.m` | **Done**, validated against MATLAB reference output, wired into the GUI (Run + Test pipeline) |
| 2. Neuronal activity (firing rates, burst detection) | `Functions/firingRatesBursts.m`, `Functions/singleChannelBurstDetection.m` | **Done**, validated against MATLAB reference output (100% parity on recording- and node-level fields), wired into `runner.py`. **CSV export now done too** (`NeuronalActivity_RecordingLevel.csv`/`NeuronalActivity_NodeLevel.csv`, port of `saveEphysStats.m`) — a 2026-07-08 audit found the `ephys` dict itself was complete but was only ever written to `ephys_results.json`, never flattened into the two CSVs MATLAB's own pipeline produces. |
| 3. Functional connectivity (STTC) | `Functions/generateAdjMs.m`, `Functions/STTCandThresholding/*` | **Core (STTC) done**, exact parity. Probabilistic thresholding ported but inherently non-bit-reproducible (see below) |
| 4. Network metrics | `Functions/ExtractNetMet.m`, `Functions/2019_03_03_BCT/*` | **Deterministic subset done** (ND, NS, MEW, Dens, CC_raw, PL_raw, Eglob, Eloc, BC, NE), 100% parity. **Modularity-dependent subset also done** (Ci/Q/nMod via Louvain + consensus clustering, raw + *normalized* PC, Z, node cartography 6-role classification, Hub3/Hub4, rich club RC) — 100% parity for everything downstream of a fixed Ci (and, for PC-normalization, a fixed PC_norm too); the stochastic pieces themselves (Ci, PC_norm's null-model randomization) aren't bit-reproducible, same situation as Step 3. **Controllability (`aveControl`/`modalControl`) also done.** **Small-worldness also done** — `SW`/`SWw` and the *saved*, null-model-normalized `CC`/`PL` (formula assembly has exact parity against MATLAB given the same `A`/`R`/`L`, see `test_pipeline_small_worldness.py`; the null models themselves, `randmio_und_v2`/`latmio_und_v2`, aren't bit-reproducible, same situation as everywhere else in this table) — see `network_metrics.py`. **`effRank` done** (`network_metrics.effective_rank`, port of `calEffRank.m`). **NMF (`num_nnmf_components`/`nComponentsRelNS`/`nnmf_residuals`/`nnmf_var_explained`) also done** — see `nmf.py`; not just RNG-different from MATLAB but *algorithm*-different (`sklearn` NMF solvers vs. MATLAB's `nnmf`), so treat this one as looser-than-usual parity. **Record-level summary-stat scalars now done too** (`NDmean`, `NDtop25`, `NSmean`, `sigEdgesMean`, `sigEdgesTop10`, `PCmean`, `PCmeanTop10`, `PCmeanBottom10`, `percentZscoreGreaterThanZero`, `percentZscoreLessThanZero`) — a 2026-07-08 audit against MATLAB's full default `netMetToCal` list (see "Auditing for silently-missing metrics" below) found these were in `plotting_step4.py`'s display-name dict (implying they were intended) but never actually computed anywhere in the port. |

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
  Also `parse_ground_electrodes()`/`ground_spike_times_dict()`, port of
  `groundSpikeTimes.m` — zeroes out spike times for channels listed in a
  recording's optional 4th spreadsheet column (`Ground`, comma-separated
  channel IDs — `RecordingInfo.ground` was already parsed from this column,
  but nothing consumed it until the 2026-07-08 audit found it unwired).
  Called independently in `step2.py`/`step3.py`/`step4.py` right after each
  loads its own spike times — MATLAB instead grounds once (in Step 2's
  `formatSpikeTimes.m`) and lets the grounded spike times propagate through
  its single chained `.mat` file; this port's steps each load spike times
  fresh from Step 1's raw output, so grounding has to be reapplied at each
  load site to reach the same outcome. Only matters for spreadsheets that
  actually have a populated `Ground` column — the bundled example dataset's
  `exampleData.csv` doesn't, so this is a no-op for the Test Pipeline button
  and wasn't (and can't be, without a fixture that has grounded channels)
  validated against a real end-to-end run; validated instead via a direct
  unit test of `ground_spike_times_dict()` (matches by channel ID against
  the `channels` array, zeroes the matched channels' spike-time arrays,
  leaves everything else untouched).
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
  Also implements `Params.time_processes` (port of `MEApipeline.m`'s
  `Params.timeProcesses` — the field and its GUI checkbox already existed in
  `params.py`/`pipeline.py`, but nothing actually timed anything until this
  session, same "wired but never built" pattern as several other findings
  in this doc). When set, times each step with `time.perf_counter()`, logs
  `"Step N duration (seconds): X"` per step in MATLAB's own format plus a
  `"Total pipeline duration (seconds): X"` line MATLAB has no equivalent of,
  and writes `step_durations.json` into the output folder (MATLAB has no
  single chained output file for this port to append timings to, so this is
  the durable, programmatically-readable record instead of scraping the
  log) — built for a MATLAB-vs-Python speed comparison on the Test Pipeline
  dataset.
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
  `hub_classification` (Hub3/Hub4), `average_controllability`/
  `modal_controllability` (Bassett Lab `ave_control.m`/`modal_control.m`),
  `effective_rank`, and `small_worldness_rl_wu` (port of
  `small_worldness_RL_wu.m` — deterministic given a real network plus two
  null models built from it; see `null_models.py` for those). **Read this
  module's docstring** before adding more metrics; it explains exactly which
  `NetMet` fields are and aren't in scope and why.
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
  Also `randmio_und_v2()`/`latmio_und_v2()` (ports of the same-named `.m`
  files in `Functions/CC_PL_SW/`) — a *different* edge-swap algorithm
  (picks two existing edges by index rather than four random node indices)
  used to build the random/lattice-like null models that
  `network_metrics.small_worldness_rl_wu` normalizes small-worldness
  against. `latmio_und_v2` additionally takes a "distance" matrix (MEA-NAP
  passes `squareform(pdist(adjM))` — Euclidean distance between each node's
  *connectivity profile*, not spatial electrode distance) that biases which
  swaps count as more lattice-like. Both batch their random draws the same
  way `randmio_und_signed` does, for the same performance reason. At
  realistic recording sizes (n≤64) and MATLAB's own iteration counts
  (10000 for the lattice model, 5000 for the random model), both run in well
  under a second — sparse active-node subnetworks mean few edges to rewire
  per attempt. Validated via the same structural-invariants approach, plus
  (unlike the signed variants above) an *exact* MATLAB parity check on the
  deterministic formula that consumes their output — see
  `small_worldness_rl_wu` below.
- `src/meanap/pipeline/nmf.py` — `cal_nmf()`, port of `calNMF.m`
  (`num_nnmf_components`/`nComponentsRelNS`/`nnmf_residuals`/
  `nnmf_var_explained`). **Read this module's docstring before touching
  it** — of everything in this port, this is the one place where even the
  *algorithm* differs from MATLAB (`sklearn.decomposition.NMF`'s coordinate-
  descent solver standing in for MATLAB's built-in `nnmf`, which defaults to
  Alternating Least Squares), so `num_nnmf_components` itself — not just the
  underlying factor matrices — can legitimately differ between the two.
  Also deliberately diverges from `calNMF.m`'s literal implementation for
  tractability: bins spike times directly into the target-downsampled-
  resolution bins instead of building MATLAB's huge intermediate matrix at
  native sampling rate first — mathematically identical whenever MATLAB's
  own `downSampleSum` wouldn't have errored (see the module docstring for
  the exact-divisibility condition this relies on). **Performance**: the
  `nnmf_residuals`/`nnmf_var_explained` sweep (one NNMF fit per rank from 1
  to the active-electrode count) is unconditional — always runs regardless
  of `Params.includeNMFcomponents` — and is the dominant cost, ~55s for a
  real 64-channel/600s recording on this environment's CPU. Computed once
  per recording (not once per lag).
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
  **Field-naming gotcha**: this module computes clustering coefficient and
  path length *twice*, for two genuinely different quantities that happen to
  share MATLAB's `CC`/`PL` names in `ExtractNetMet.m`'s docstring — the raw,
  unnormalized values (`CC_raw` per-node array + `CC_rawMean` scalar,
  `PL_raw` scalar; independently useful/testable, but NOT what MATLAB
  saves), and the null-model-normalized scalars from `small_worldness_rl_wu`
  (`CC`/`PL` — what MATLAB actually saves into `NetMet.CC`/`NetMet.PL`,
  alongside the new `SW`/`SWw`). The small-worldness block additionally
  uses MATLAB's own oddball gate, `aN > minNumberOfNodesToCalNetMet`
  (strictly greater — every other block in `ExtractNetMet.m` uses `>=`),
  faithfully replicated rather than "fixed", since the goal is matching
  MATLAB's actual behavior.
  Also computes the record-level summary-stat scalars `NDmean`/`NDtop25`/
  `NSmean`/`sigEdgesMean`/`sigEdgesTop10` (from ND/NS/the raw adjacency
  values) and, inside the modularity block, `PCmean`/`PCmeanTop10`/
  `PCmeanBottom10`/`percentZscoreGreaterThanZero`/
  `percentZscoreLessThanZero` (from the normalized PC/Z) — added in the
  2026-07-08 audit (see "Auditing for silently-missing metrics" below),
  these were previously computed nowhere despite being in
  `plotting_step4.py`'s display-name dict and MATLAB's default
  `netMetToCal`.
  `_run_step4_network_metrics()` additionally calls `nmf.cal_nmf()` once per
  recording (lag-independent, matching `ExtractNetMet.m`'s `if e == 1`
  gate) and merges its result into every lag's metrics dict via
  `metrics.update(nmf_result)`. The NMF result's rank-indexed arrays
  (`nnmf_residuals`, `nnmf_var_explained`, `randResidualPerComponent`, and
  the optional factor matrices) are NOT node-indexed — `_NMF_NON_NODE_KEYS`
  explicitly excludes them from the CSV-export loop's generic "any array
  with size>1 gets spread across `NetworkActivity_NodeLevel.csv` rows by
  channel index" logic, since their length can coincidentally match the
  active-node count and would otherwise get silently mis-attributed to
  channels.
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
  gotchas" section for why Ci is stochastic), `9_adjM{lag}msNodeCartography.png`,
  `10_MEA_NetworkPlotNodedegreeAveragecontrollability.png`,
  `11_MEA_NetworkPlotNodedegreeModalcontrollability.png` (controllability plots,
  including their batch-scaled variants — see "Batch scaling" below). Still
  not ported: null-model panels (small-worldness — see "Network metrics
  gotchas").
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
- `src/meanap/gui/main_window.py` — `_on_run` runs the pipeline on a background
  `QThread` (see item 1 under "Known limitations" for the cancellation
  mechanism). `_on_test_pipeline` downloads the example dataset, points the
  Paths tab at it, sets `start_step=1, stop_step=4`, then calls `_on_run` —
  i.e. it runs the full 4-step pipeline. This mirrors `runPipelineApp.m`'s
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
- `python/test_pipeline_small_worldness.py` — three-part test for
  `small_worldness_rl_wu` + `randmio_und_v2`/`latmio_und_v2`. (1) **Exact**
  MATLAB parity for the deterministic formula assembly: feeds MATLAB's own
  `A`/`R`/`L` (`python/test_fixtures/small_worldness_reference.npz`, via
  `gen_small_worldness_reference.m`) into `small_worldness_rl_wu` and diffs
  `SW`/`SWw`/`CC`/`PL` against MATLAB's own `small_worldness_RL_wu.m` output
  on the same inputs. Unlike the other `gen_*_reference.m` scripts, this one
  doesn't need a real MATLAB pipeline run's saved adjacency matrices — it
  builds a small fixed-seed random network directly, since the point is
  isolating formula correctness, not re-deriving a specific recording's
  numbers. (2) Structural invariants on Python's own `randmio_und_v2`/
  `latmio_und_v2` (exact degree/weight preservation, symmetry) — NOT a
  MATLAB parity check, same rationale as `test_pipeline_null_models.py`.
  (3) An end-to-end smoke test chaining Python's own null models into
  `small_worldness_rl_wu`. All three currently pass.
- `python/test_pipeline_nmf.py` — structural/sanity tests for `nmf.py`
  (NOT a MATLAB parity check — impossible here even in principle, since the
  underlying NNMF solver is a different algorithm, not just a different RNG
  stream, see `nmf.py`'s docstring). Checks: spike-count preservation
  through `randomise_spike_train`/`_bin_spike_times`; on a synthetic
  low-rank-plus-noise recording, `num_nnmf_components` lands in a sane
  range, `nnmf_var_explained` is bounded in [0, 1] and approaches ~1 at full
  rank, `nnmf_residuals` roughly decreases with rank; `include_nmf_
  components=True` returns non-negative factor matrices. All currently pass.
- `python/test_fixtures/` — `.npz` ground-truth fixtures for steps 3-4 plus
  the `.m` scripts that generated them (`gen_sttc_reference.m`,
  `gen_step4_reference.m`, `gen_cartography_reference.m`,
  `gen_small_worldness_reference.m`) — re-run those directly in MATLAB if
  the fixtures ever need regenerating (e.g. after an algorithm change).

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
- **Auto-set cartography boundaries (`TrialLandscapeDensity.m`) is now
  ported** — `network_metrics.trial_landscape_density` +
  `step4._apply_cartography_boundaries` (Phase B reducer, gated on
  `params.auto_set_cartography_boundaries`, per-lag by default to match
  `MEApipeline.m`). Before this, `step4.py` classified nodes with the *fixed*
  default boundaries (`peri_part_coef=0.625` …); against real data almost
  every node's normalized PC sits below 0.625, so ~62-95% of nodes piled into
  cartography role 1 (`NCpn1`) and roles 2-6 were near-empty — a systematic,
  non-RNG divergence from MATLAB's `NCpn1-6` CSV columns (found via end-to-end
  CSV verification vs `OutputData24Dec2025`). The port pools PC/Z across
  recordings and re-derives all five boundaries by optimal 1-D k-means
  (`_optimal_1d_split_boundaries`, a deterministic O(k·n²) DP — MATLAB's
  `kmeans` is random-seeded and *not* itself bit-reproducible, so exact
  boundary parity is unavailable, same class as Step 3). Validated against
  MATLAB's stored per-lag boundaries (several match to ~1e-16 where MATLAB's
  kmeans also hit the optimum) and by `test_pipeline_landscape.py` (48 checks,
  incl. a regression guard that data-driven boundaries un-pile role 1 across
  all 6 fixture recordings/lags). **Deliberate divergence from MATLAB**:
  `TrialLandscapeDensity.m` line 61 reloads `ExpName{1}` every loop iteration,
  so MATLAB actually pools only the *first* recording's PC/Z (duplicated) — an
  upstream bug. The port pools *all* recordings (the documented intent); this
  is the largest remaining source of NCpn1-3 difference vs MATLAB and is
  expected/bounded, not a defect.
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

_Last audited 2026-07-08 — if you fix or port something in this list, please
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
2. ~~**Controllability not ported.**~~ **Done** — `average_controllability()`/
   `modal_controllability()` (ports of the Bassett Lab `ave_control.m`/
   `modal_control.m`) are in `network_metrics.py`, computed in `step4.py`
   (`aveControl`/`modalControl` + mean/top-25%/threshold summary stats), and
   plotted as `10_…Averagecontrollability.png` / `11_…Modalcontrollability.png`
   (see item 3 below).
   ~~**Small-worldness not ported.**~~ **Done** — `small_worldness_rl_wu()`
   (port of `small_worldness_RL_wu.m`) is in `network_metrics.py`, fed by two
   new null-model rewiring functions in `null_models.py`
   (`randmio_und_v2`/`latmio_und_v2`, ports of the same-named `.m` files in
   `Functions/CC_PL_SW/` — distinct from `randmio_und_signed`/
   `null_model_und_sign` above, which serve `participation_coef_norm`
   instead). Wired into `step4.py`'s `compute_network_metrics` as `SW`/`SWw`/
   `CC`/`PL` (the last two are what MATLAB actually saves into
   `NetMet.CC`/`NetMet.PL` — the *raw*, unnormalized values this module
   already computed are now under `CC_raw`/`PL_raw`/`CC_rawMean` instead, to
   avoid colliding with the real field names; see `network_metrics.py`'s
   docstring for why both are kept). MATLAB's own gate for this block is
   `aN > minNumberOfNodesToCalNetMet` (strictly greater — unlike every other
   block's `aN >= ...`), faithfully replicated in `step4.py`, not a typo.
   Formula-assembly parity against MATLAB (fixed `A`/`R`/`L`) is exact — see
   `python/test_pipeline_small_worldness.py` and
   `python/test_fixtures/gen_small_worldness_reference.m`. The null models
   themselves aren't bit-reproducible against MATLAB (independent RNG
   streams), validated instead via structural invariants (exact degree/
   weight preservation), same situation as `null_models.py`'s other
   functions.
   ~~**NMF-based `num_nnmf_components` not ported.**~~ **Done** —
   `nmf.py`'s `cal_nmf()`, port of `calNMF.m`. Unlike everything else in
   this port, this one is not just RNG-stream-different from MATLAB but
   *algorithm*-different: MATLAB's `nnmf` defaults to Alternating Least
   Squares, `nmf.py` uses `sklearn.decomposition.NMF` (coordinate descent,
   the closest available equivalent) — different solvers can converge to
   different local optima and even pick a different
   `num_nnmf_components`, since that value depends on exactly where each
   solver's residual crosses a phase-randomized reference's. Also computes
   the (mathematically identical, see `nmf.py`'s docstring) downsampled
   spike matrix directly at the target resolution rather than materializing
   MATLAB's huge intermediate native-`fs` matrix first. **Performance**:
   `nnmf_residuals`/`nnmf_var_explained` are unconditional (saved regardless
   of `Params.includeNMFcomponents`) and require one NNMF fit per rank
   1..(active-electrode count), which is the dominant cost — ~55s for a real
   64-channel/600s recording (measured on this environment's CPU),
   independent of lag count since it's computed once per recording, not
   once per lag.
   ~~**Spatial/temporal autocorrelation not ported.**~~ Still true, and
   staying that way for now: `SA_lambda`/`SA_inf`/`TA_regional`/`TA_global`
   aren't in MATLAB's own default `netMetToCal` list either
   (`AdvancedSettings.m` calls them out as "other optional ones"), and
   `ExtractNetMet.m`'s own temporal-autocorrelation code path is an explicit
   `% TODO` stub — there's no complete MATLAB reference behavior to port yet.
   Everything else in `ExtractNetMet.m`'s own docstring list of metrics is
   done with either exact or "deterministic given a fixed stochastic input"
   parity — see the "Where things stand" table and `network_metrics.py`'s
   docstring for the precise breakdown. `Cmcblty` (communicability) needs no
   work: MATLAB's own code path for it is commented out upstream.
3. **Step 4 plots**: 9 of MATLAB's `4A_IndividualNetworkAnalysis` plots are
   ported (connectivity stats, base/BC/PC/Eloc-colored network plots, circular
   module-colored network plot, node cartography, average/modal controllability
   — see `plotting_step4.py`).
   **Batch-scaled ("scaled to entire data batch") variants are now ported** for
   the four spatial network plots (2/3/4/5) plus the two controllability plots
   (10/11) — each writes a sibling `N_scaled_MEA_NetworkPlot….png` whose node
   size / node color / edge-weight scales come from batch-wide pooled bounds
   instead of the recording's own range (see the "Batch scaling" note below).
   **The `N_combined_MEA_NetworkPlot….png` side-by-side figure is now ported
   too** (`plot_spatial_network_combined` — left panel scaled to the recording,
   right panel scaled to the batch, each with its own inline legend/colorbar;
   rendered as one two-axis figure rather than MATLAB's `copyobj` merge of two
   separate figures). Still not ported: the null-model-iterations panel
   (`plotNullModelIterations.m` — a diagnostic plot of the `met`/`met2`
   convergence traces `latmio_und_v2`/`randmio_und_v2` collect every 1000
   rewiring iterations; item 2's null-model *calculation* is done, this is
   purely the unported diagnostic plot on top of it).
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

## Auditing for silently-missing metrics

A real gap in this port (found 2026-07-08, now fixed) went undetected for a
while because it wasn't a crash or a wrong number — it was fields that were
simply never computed, with no test asserting they existed. Controllability
and small-worldness were caught because someone happened to remember seeing
plots for them; the record-level summary-stat scalars (`NDmean`, `NDtop25`,
`NSmean`, `sigEdgesMean`, `sigEdgesTop10`, `PCmean`, `PCmeanTop10`,
`PCmeanBottom10`, `percentZscoreGreaterThanZero`,
`percentZscoreLessThanZero`) were only found by deliberately auditing
against MATLAB's ground truth for "what should exist" rather than trusting
this doc's own "still missing" list (which had gone stale — it only tracked
things someone had *noticed* were missing).

**The audit that found them**: `Functions/ExtractNetMet.m`'s docstring
(lines 26-50) lists every `NetMet` field name, and `AdvancedSettings.m`'s
`Params.netMetToCal`/`Params.networkLevelNetMetToPlot`/
`Params.unitLevelNetMetToPlot` defaults are the authoritative list of what a
default pipeline run actually produces. Cross-referencing that full list
against `grep -n '"X"\]\|result\["X"\]' src/meanap/pipeline/step4.py
network_metrics.py` for every field name is the reliable check — checking
this doc's own "known limitations" prose against the code is not, since
prose gets stale in exactly the way that just happened. A second useful
signal: `plotting_step4.py`'s `NETMET_REC_METRICS`/`NETMET_NODE_METRICS`
display-name dicts were built ahead of the metrics they label (i.e. someone
added the label anticipating the field, then the field itself never got
written) — grepping for display-dict keys with no corresponding
`result["X"] = ...` in `step4.py` catches exactly this pattern. If you're
auditing again later, also grep `ExtractNetMet.m` for every distinct
function call (`grep -oE '[a-zA-Z_][a-zA-Z0-9_]*\(' Functions/
ExtractNetMet.m | sort -u`) and check each one has a Python equivalent
somewhere in `network_metrics.py`/`nmf.py`/`null_models.py` — that's how
`randmio_und_v2`/`latmio_und_v2`/`calNMF`/`calEffRank` were confirmed to be
the *only* remaining unaccounted-for function calls at the time of this
audit (excluding MATLAB builtins, the `checkIfRecomputeMetric`/
`prevNetMet` incremental-caching machinery Python doesn't replicate, the
commented-out `fcn_find_hubs_wu` block, and binary-adjacency-matrix-only
functions like `betweenness_bin`/`distance_bin`, since this port only
supports `Params.adjMtype == 'weighted'`).

**Extended to Steps 1-3 the same day.** Same methodology, different
authoritative lists: `firingRatesBursts.m`'s own field-by-field assignments
to `Ephys.*` (there's no `netMetToCal`-equivalent list for Step 2 — the
closest thing is `saveEphysStats.m`'s hardcoded `NetMetricsE`/`NetMetricsC`
cell arrays, which turned out to be the more useful reference since they're
also *the CSV column whitelist*) and `batchDetectSpikes.m`'s `varsList`
(what actually gets saved to each recording's `_spikes.mat`). Found two more
real gaps, both now fixed:

1. **Step 2 had no CSV export at all** — `firing_rates_bursts()`'s `ephys`
   dict was complete and correct (already validated at 100% parity), but
   `step2.py` only ever wrote it to `ephys_results.json`; the
   `NeuronalActivity_RecordingLevel.csv`/`NeuronalActivity_NodeLevel.csv`
   files MATLAB's `saveEphysStats.m` produces (called unconditionally in
   `MEApipeline.m`, not gated behind an optional flag) never got written by
   the Python port. Fixed — see `_save_ephys_stats_csv()` in `step2.py`.
2. **Electrode grounding was parsed but never applied** —
   `RecordingInfo.ground` (the spreadsheet's optional 4th `Ground` column)
   was already being read by `read_recording_csv()`, but nothing consumed
   it anywhere in the pipeline. Fixed — see `spreadsheet.py`'s
   `parse_ground_electrodes()`/`ground_spike_times_dict()` note above. This
   one's a good example of why grepping call sites matters more than
   grepping field/parameter *existence*: `Params.ground`-equivalent fields
   existing in `params.py`/`RecordingInfo` proved nothing about whether
   they were wired to anything.

Also checked and confirmed **not** gaps (dead code in MATLAB itself, so
correctly unported): `Ephys.channelHasBurst` (computed by
`firingRatesBursts.m` but not in `saveEphysStats.m`'s CSV whitelist, same
"computed but never surfaced" pattern as Step 4's `BCmeantop5`);
`spikeAmps`/`getSpikeAmp.m` (only consumed by the stimulation-analysis code
path, `Params.stimulationMode == 1`, out of this port's scope);
`Params.ProbThreshPlotChecks`'s diagnostic replicate-stability plot
(`adjM_thr_checkreps.m` — optional, off by default, and `Params
.prob_thresh_plot_checks` already exists in `params.py` unwired to match
that same off-by-default state, not silently dropped).

## MATLAB vs Python speed comparison (2026-07-09)

Full steps-1-4 run on the Test Pipeline dataset (`ExampleData/`, recordings
`NGN2_20230208_P1_DIV14_A2`/`_A3`, `Axion64` layout, `ProbThreshRepNum=200`,
lags `[10, 25, 50]`ms), timed via MATLAB's `Params.timeProcesses` and the
Python port's newly-implemented equivalent (`Params.time_processes`, see
`runner.py`'s entry above), both run alone (no concurrent load) on the same
machine:

| Step | MATLAB | Python | Ratio |
|---|---|---|---|
| 1. Spike detection | 580s | 568.8s | Python ~2% faster |
| 2. Neuronal activity | 53s | 6.2s | **Python ~8.5x faster** |
| 3. Functional connectivity | 15s | 80.2s | **Python ~5.3x slower** |
| 4. Network activity | 283s | 511.7s | **Python ~1.8x slower** |
| **Total** | **931s (~15.5 min)** | **1166.9s (~19.5 min)** | **Python ~25% slower overall** |

Not a uniform "Python is slower" story — it's faster than MATLAB at the two
purely-numerical steps, slower specifically where MATLAB parallelizes:

- **Step 3**: MATLAB's log shows it spinning up an 8-worker parallel pool for
  the 200-shuffle probabilistic thresholding; `adjm_thr()` (this port) runs
  single-threaded. Likely the dominant cause of the 5.3x gap — not yet
  investigated further (e.g. whether MATLAB is also using a compiled/mex
  STTC core on top of the parallelism).
- **Step 4**: NMF alone costs ~55s per recording (~110s of the 511.7s total,
  measured earlier this session on real data) — sklearn's coordinate-descent
  solver run serially for every rank from 1 to the active-electrode count,
  see `nmf.py`'s docstring. MATLAB likely also parallelizes some of its BCT
  calls here (unconfirmed). The other ~400s is the rest of step 4's compute
  + plotting, not yet broken down further.
- **Step 2**: Python's vectorized numpy firing-rate/burst computation is
  dramatically faster than MATLAB's implementation, which does per-channel
  LOESS regression fitting for the burst ISI threshold (`getISInTh.m` →
  `fLOESS.m` — also the source of the "Matrix is close to singular" warnings
  MATLAB prints throughout Step 2 on this low-firing-rate dataset).

**Obvious next lever if closing the gap matters**: parallelize steps 3/4
(e.g. `multiprocessing`/`joblib` across recordings or lags) — that's where
essentially all of the total deficit lives.

### Optimization pass — 3.3x faster end-to-end (2026-07-09)

A follow-up performance pass took the full run from 1166.9s to **350.0s** —
Python is now **~2.66x faster than MATLAB** (931s), not 25% slower. Same
machine, same config (2 recordings, `[10, 25, 50]`ms, `ProbThreshRepNum=200`):

| Step | Before | After | Speedup | What changed |
|---|---|---|---|---|
| 1. Spike detection | 568.8s | 103.6s | **5.5x** | Channel-level threading (`detect_spikes_recording(max_workers=)`): per-channel wavelet CWT + bandpass release the GIL, so threads parallelize over one shared ~3.8 GB `dat` array with no extra RAM. Bit-identical output. |
| 2. Neuronal activity | 6.2s | 6.4s | — | Unchanged (already fast). |
| 3. Functional connectivity | 80.2s | 42.7s | **1.9x** | Recording-level process map. |
| 4. Network activity | 511.7s | 197.3s | **2.6x** | numba-JIT `randmio_und_signed` (~28x on the PC-norm null models); collection-based plotting (~5x plot phase, single-threaded); recording-level process map. |
| **Total** | **1166.9s** | **350.0s** | **3.3x** | |

Key pieces (all default-on, with serial fallbacks; see
`src/meanap/pipeline/parallel.py`):

- **RAM/CPU-aware worker sizing.** Step 1 is RAM-bound (~3.8 GB/recording) →
  *threads over channels* on one shared array (no per-worker copy). Steps 3/4
  are CPU-bound/low-RAM → *processes over recordings*. Counts auto-size to
  physical cores and free RAM (`psutil`) with headroom; override via
  `params.spike_detection_channel_workers` / `params.recording_workers`
  (`None` = auto). Per-worker BLAS threads pinned to avoid oversubscription.
- **numba** is now a dependency (forces `numpy<2.5`); `randmio_und_signed` has
  an `@njit` core + pure-Python fallback (runs without numba, just slower).
  All step-3/4 parity fixtures pass under numpy 2.4.6.
- **Plotting** (`network_plot.py`): edges were individual `ax.plot()` Line2D
  artists and nodes individual `add_patch` circles (hundreds per figure ×
  ~380 figures) → one `LineCollection` + `PatchCollection(match_original=True)`.
  Cut the plot phase ~5x *and* removed a `get_text_width_height_descent`
  layout pathology (458s→1.1s in profile — the per-edge artists were making
  `tight_layout`/bbox re-measure text catastrophically). Output pixel-validated
  unchanged.
- **Step 4** restructured into A (parallel compute) → B (serial batch-bounds
  reduce) → C (parallel plot). Deterministic metrics bit-identical
  serial-vs-parallel. Phase B is also where the cross-recording node-cartography
  boundary clustering runs (`_apply_cartography_boundaries` →
  `network_metrics.trial_landscape_density`, port of `TrialLandscapeDensity.m`'s
  default `kmeans` branch — see the node-cartography note below).

Caveats: measured on a shared 16-core box where step-4 *process*-parallelism
scales poorly (memory-bandwidth/BLAS contention → only ~1.1-1.4x across
recordings), so most of step 4's win is the numba + plotting changes, which are
single-threaded and portable. On a dedicated ~8-core machine the recording map
should contribute more. Remaining portable candidates: numba
`randmio_und_v2`/`latmio_und_v2` (small-worldness, same `@njit` pattern);
cutting NMF's fit count (`init="nndsvda"` was tried — ~8% *slower* since the
per-rank sweep pays NNDSVD's SVD-init cost on every fit, reverted).

**How this was measured** — headless (`Params.guiMode=0`) execution of
MATLAB MEA-NAP is not a well-trodden path; getting a clean end-to-end run
required finding and working around 5 bugs/config traps that the
interactive GUI (`runPipelineApp.m`/`getParamsFromApp.m`) silently avoids.
See `MEApipeline_timingBenchmark.m`'s header comment (repo root, not part of
the Python port — a throwaway benchmarking copy of `MEApipeline.m`) for the
full list and exact fixes; briefly:
1. `batchDetectSpikes()` called with 5 args in `MEApipeline.m`'s non-GUI
   branch, but its `arguments` block requires 6.
2. `Params.electrodesToGroundPerRecording` is left as a non-cell `[]` by
   `setUpSpreadSheet.m` when there's no spreadsheet `Ground` column, but
   Step 2/3/4 unconditionally brace-index it.
3. `AdvancedSettings.m`'s default `Params.netMetToCal` includes `'PC_raw'`,
   whose computation is dead code — crashes Step 4's eval-assignment loop.
4. Several `Params` fields (`minActivityLevel`, `nodeScalingMethod`,
   `networkPlotEdgeThresholdMethod`, etc.) are only ever set by the GUI, with
   no `AdvancedSettings.m` fallback — silently undefined in headless runs.
5. `Params.nodeLayout='Original'` (not `'MEA'`) is `StandardisedNetworkPlot
   .m`'s actual sentinel for "use real electrode coordinates"; several other
   plotting/scaling params (`nodeScalingMethod='Linear'` not `'degree'`,
   `maxNodeSize=1` not `0.06`, `networkPlotEdgeThresholdMethod='Absolute
   Value'` not `'percentile'`, etc.) also don't match the Python port's
   same-sounding defaults — the two ports' vocabularies/scales for these
   particular fields diverged. The values finally used were extracted from
   `Parameters_OutputData26Jun2025.csv`, a completed **GUI-driven** MATLAB
   run on this exact dataset — i.e. "what MEA-NAP actually computes in
   practice," not a guess.

Items 1-4 are genuine MATLAB-side bugs (would affect anyone scripting
MEA-NAP outside the GUI, e.g. for HPC batch jobs); item 5 is this
benchmark's own config error, not a MATLAB bug — noted here so a future
re-run doesn't have to rediscover it.

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
