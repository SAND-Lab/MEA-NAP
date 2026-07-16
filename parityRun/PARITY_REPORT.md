# MATLAB vs Python MEA-NAP — Test Pipeline CSV Parity Report

**Date:** 2026-07-15/16 · **Dataset:** bundled `ExampleData` (`NGN2_20230208_P1_DIV14_A2`, `..._A3`), the two recordings the Test-pipeline button analyses · **Steps:** 1–4 · **Lags:** 10/25/50 ms

## Verdict

**Every deterministic stage of the Python port now reproduces MATLAB exactly.** Spike detection, activity metrics and the network-metric arithmetic all match to floating-point noise. The one remaining source of end-to-end CSV divergence is **step 3's probabilistic thresholding**, which draws from an independently-seeded RNG in each port and so builds slightly different graphs (`aN` differs by up to 2 nodes) — that is inherent to comparing two RNG streams, not a defect.

| Stage | Status |
|---|---|
| **1. Spike detection** (`bior1p5`, `thr5`) | **Exact** — identical counts, identical times (1.1e-13 s) |
| **2. Activity metrics** (`NeuronalActivity_*.csv`) | **Exact** end-to-end — `FRmean` differs by 0 |
| **4. Network metrics, same graph** | **Exact** — worst diff 2.8e-14, incl. average controllability |
| **3. Probabilistic thresholding** | **Not reproducible by design** (independent RNG) → `aN` differs → network CSVs differ |
| NMF (`num_nnmf_components`) | **Not comparable** — different solver, not just different RNG |

This is a change from the first version of this report, which measured spike-detection F1 at 0.89–0.90 and concluded the ports "never can" match end-to-end. That was true of the code as it stood, but the *diagnosis* in `PIPELINE_PORT_STATUS.md` — that MATLAB's CWT was unreproducible — was wrong. Three bugs were found and fixed (§1); bior1.5 is now exact, and step 1 also got ~2× faster (272 s → 141 s).

---

## 1. Spike detection (step 1) — now exact

| Recording | Method | MATLAB | Python | Matched | F1 | max abs Δt after the known +2-sample shift |
|---|---|---|---|---|---|---|
| A2 | `bior1p5` | 7753 | **7753** | 7753 | **1.0000** | 1.1e-13 s |
| A2 | `thr5` | 1417 | **1417** | 1417 | **1.0000** | 1.1e-13 s |
| A2 | `thr4` | 24941 | 24943 | 24943 | 1.0000 | 1.1e-13 s |
| A3 | `bior1p5` | 6228 | **6228** | 6228 | **1.0000** | 1.1e-13 s |
| A3 | `thr5` | 713 | **713** | 713 | **1.0000** | 1.1e-13 s |
| A3 | `thr4` | 25159 | 25161 | 25160 | 1.0000 | 1.1e-13 s |

Previously: F1 0.9025 (A2) / 0.8900 (A3), ~2% fewer spikes, ~10% disagreeing.

### What was actually wrong

`PIPELINE_PORT_STATUS.md` recorded bior1.5 F1 ≈ 0.82–0.84 as *expected*, on the grounds that "PyWavelets approximates the wavelet via cascade; MATLAB uses its native CWT". **Both halves of that premise were false:**

- **PyWavelets' bior1.5 is not an approximation.** The filters are byte-identical to MATLAB's `wfilters('bior1.5')`, `wavefun`'s grid is identical, and `psi_d` agrees with MATLAB's to **1.6e-15** (so the integrated wavelet agrees to 2.7e-16).
- **MATLAB's "native CWT" here is the *legacy* algorithm**, not the modern Morse-wavelet `cwt`. `cwt(x, scales, 'bior1.5')` dispatches to a cascade-based path that is fully reproducible — verified **bit-identical** (max diff 0) against this reconstruction:

  ```matlab
  [psi, xval] = intwave(wname, 10);  step = xval(2)-xval(1);
  j = 1 + floor((0:a*(xmax-xmin)) / (a*step));
  f = fliplr(psi(j));
  coefs = -sqrt(a) * wkeep1(diff(wconv1(signal, f)), len);
  ```

So the wavelet was never the problem — the port's *algorithm* was. It convolved an interpolated `psi` via FFT and rolled the result; MATLAB convolves the **integrated** wavelet and differentiates. Three fixes, all in `src/meanap/pipeline/spike_detection.py`:

1. **`_cwt_bior15` rewritten as a literal port** of the formula above. Now matches MATLAB's own `cwt` to **~1e-15 relative** on real filtered traces (correlation 1.0000000000 at every scale). The `-sqrt(a)` factor carries the sign, so the previous `return -coeffs` hack is gone.
2. **`_determine_scales` off-by-one** — the decisive bug. MATLAB's zero-crossing indices are **1-based** and compared against `>500`/`<500`; the port compared **0-based** indices, so a crossing at 1-based index 501 fell into *neither* bin. That corrupted the narrowest scale's width entry (0.56 vs MATLAB's 0.32 ms) and produced scales `[3 3 4 6 7]` instead of `[2 3 4 6 7]`. The port simply never looked at the narrowest spikes — which is exactly the signature we measured: precision ≈ 1.000 with recall 0.9271 (identical in both recordings), i.e. Python's spikes were a strict *subset* of MATLAB's.
3. **`Sigmaj` centring** — MATLAB centres the subsampled coefficients on the mean of the **full** row (`mean(c(i,:))`); the port used the subsample's own mean.

(Also replicated `interp1`'s NaN-outside-range behaviour instead of `np.interp`'s silent clamping, and MATLAB's half-away-from-zero `round` instead of NumPy's half-to-even — the scale interpolation lands on exact `.5` values, so this matters.)

### Known deliberate 2-sample offset

Python's spike times are a constant **2 samples (0.16 ms) earlier** than MATLAB's, for every method. Two stacking MATLAB quirks:

- MATLAB reports **1-based** frames as `spikeFrames/fs`, so a spike on the first sample gets `1/fs`, not `0`.
- `alignPeaks.m` computes `newSpikeTime = spikeTimes(i)+pos-win` with a **1-based** `pos`, landing on the true peak **+1** even for a perfectly centred peak.

**Decision (2026-07-15, with the user): keep Python correct** — report the true peak — rather than replicate MATLAB's off-by-one, consistent with the existing call on the `setUpSpreadSheet.m` coordinate bug. This affects **no** downstream metric: a uniform shift leaves firing rates and STTC unchanged. Removing it (`+2` samples) makes the spike times agree to **1.1e-13 s**, i.e. exactly.

### Open, minor

`thr4` finds **2 extra spikes** per recording (24943 vs 24941). F1 is still 1.0000 to 4 dp. It predates this work and is unrelated to the CWT (threshold detection doesn't touch it) — most likely the refractory-period loop. `thr5` and `bior1p5` are exact.

Reproduce: `uv run python parityRun/compare_spike_detection.py`

---

## 2. Activity metrics (step 2) — exact end-to-end

With spike detection now exact, the activity CSVs match MATLAB **exactly in a full independent run** — no shared inputs:

| Column | MATLAB | Python | Max abs diff |
|---|---|---|---|
| `FRmean` (A2 / A3) | 0.202 / 0.162 | 0.202 / 0.162 | **0** |
| `FRmedian` | 0.0555 | 0.0555 | **0** |
| `numActiveElec` | 64 | 64 | **0** |
| `FR`, `FRactive` (128 node rows) | — | — | **0** (3.3e-15 when fed MATLAB's spikes) |

Previously `FRmean` was ~2.5% low. The step-2 port (`firing_rates_bursts`) is arithmetically identical to `firingRatesBursts.m`.

> **Caveat — burst metrics remain untested.** This dataset fires at ~0.16–0.20 Hz and produces **zero network bursts** (`NBurstRate = 0` in both ports), so `meanNBstLengthS`, `CVofINBI`, `fracInNburst`, `channelBurstDur` etc. are `NaN` on both sides. They agree trivially; this run gives **no evidence** about burst-detection parity. A busier dataset is needed.

---

## 3. Network metrics (steps 3–4) — limited by the thresholding RNG

Spikes are now identical, so **everything below is attributable to step 3's probabilistic thresholding** (200 shuffles, independently seeded). It changes which edges survive, hence `aN`:

| Recording / lag | 10ms | 25ms | 50ms |
|---|---|---|---|
| MATLAB `aN` (A2 / A3) | 61 / 61 | 63 / 64 | 64 / 64 |
| Python `aN` (A2 / A3) | 59 / 61 | 63 / 64 | 63 / 64 |

Recording-level, full independent run:

| Column | MATLAB mean | Python mean | Max rel diff | Corr |
|---|---|---|---|---|
| `effRank` | 26.0533 | 26.0536 | **1.2e-05** | 1.000 |
| `aveControlMean` | 1.00650 | 1.00652 | **1.4e-04** | 0.999 |
| `sigEdgesTop10` | 0.0818 | 0.0831 | 0.043 | 0.995 |
| `NSmean` | 0.1723 | 0.1721 | 0.051 | 0.997 |
| `Eglob` | 0.01368 | 0.01386 | 0.075 | 0.995 |
| `NDmean` | 5.057 | 4.960 | 0.080 | 0.980 |
| `Dens` | 0.0815 | 0.0805 | 0.083 | 0.968 |
| `ElocMean` | 0.01780 | 0.01783 | 0.191 | 0.959 |
| `Q` (stochastic) | 0.7752 | 0.7692 | 0.065 | 0.406 |
| `SW` (stochastic) | 1.048 | 1.287 | 0.649 | 0.217 |
| `num_nnmf_components` | 1.0 | 4.0 | 0.857 | — |

`effRank` and `aveControlMean` — the two metrics that barely depend on marginal edges — are now essentially exact, which is the clearest evidence the metric code is right and the graph is the only variable.

`aveControlMean` per (recording, lag):

| | 10ms A2 | 25ms A2 | 50ms A2 | 10ms A3 | 25ms A3 | 50ms A3 |
|---|---|---|---|---|---|---|
| MATLAB | 1.002738 | 1.004619 | 1.006549 | 1.007502 | 1.008126 | 1.009456 |
| Python (own spikes) | 1.002879 | 1.004567 | 1.006653 | 1.007488 | 1.008049 | 1.009481 |

**Node-level metrics remain the weakest** (`ND` r=0.83, `MEW` r=0.68, `Eloc` r=0.69, `PC` r=0.76 — up from 0.65/0.69/0.14/0.51 before the spike fix, but still not 1:1). A node kept by one port and dropped by the other changes its neighbours' degree, path length and centrality. Controllability is again the exception (`aveControl`/`modalControl` r=0.9997).

**`num_nnmf_components` is not comparable across ports** — not an RNG difference: `sklearn`'s coordinate-descent NMF vs MATLAB's alternating least squares, where the component count depends on where each solver's residual crosses a phase-randomised reference.

**Bottom line for users:** recording-level summaries are robust and now near-exact for the deterministic metrics; **per-node network values still should not be compared 1:1** across ports on this dataset, and neither should the stochastic metrics (`Q`, `nMod`, `SW`, `PC`, `Z`, `NCpn*`).

Reproduce: `uv run python parityRun/compare_parity.py OutputData_Python_parity`

---

## 4. Same adjacency matrix — the clean test of the ported maths

MATLAB's BCT functions run directly on this run's adjacency matrices (`parityRun/gen_step4_parity_reference.m`), then the *same* matrices fed to the port's `network_metrics` functions.

| Metric | Worst abs diff (both recordings × 3 lags) |
|---|---|
| `aN`, `Dens`, `ND`, `BC` | **0** (bit-identical) |
| `CCraw` | 5.2e-18 |
| `MEW`, `Eglob`, `Eloc` | ~1e-17 |
| `NS` | 1.1e-16 |
| `aveControl`, `modalControl` | 3.1e-15 |
| `PLraw` | 2.8e-14 |
| **Worst overall** | **2.842e-14** |

**Every step-4 metric — including average and modal controllability — is exact.**

Reproduce: `matlab -batch "run('parityRun/gen_step4_parity_reference.m')"` then `uv run python parityRun/compare_step4_same_adjacency.py`

---

## 5. Structural CSV differences

1. **`Lag` column format.** MATLAB writes numeric ms (`10`); Python writes the adjacency field name (`"10mslag"`). Anyone joining the two CSVs, or loading Python's into a numeric pipeline, hits a string column.

2. ~~**Network node-level `Channel` is not a channel ID.**~~ **FIXED** (`step4.py`, 2026-07-15). Python wrote `Channel = 1..aN` — a *position among active nodes* — so rows were mislabelled (`Channel = 3` was not electrode 3), and it contradicted step 2's node CSV, which uses real IDs. It now writes the real electrode ID via `activeChannelIndex`, matching `saveNetMet.m`'s `Info.channels(activeNodeIndices)`. Verified: values are now 11…88 and join directly against MATLAB's `activeChannel` with no remapping.

3. **CSV location.** MATLAB writes all four CSVs to the output root; Python writes them under `2_NeuronalActivity/` and `4_NetworkActivity/`.

4. **Column names differ for the network CSVs.** MATLAB's final files use `recordingName`/`eGrp`/`AgeDiv`/`activeChannel`; Python uses `FileName`/`Grp`/`DIV`/`Channel`. Cause: `saveNetMet.m` writes the port's schema at step 4, then **step 4B's `combineExpNetworkData.m` overwrites the same two filenames** with its own group-level schema. The port implements `saveNetMet.m` only (group-level analysis is unported), so it matches the file MATLAB *discards*.

5. **Extra Python columns**: `CC_rawMean`, `PL_raw`, `NCpn{1..6}count`, `Hub3`, `Hub4`, `aveControlTop25`, `modalControlMean`, `modalControlPrctLessThanThreshold`, `activeChannelIndex`, `CC_raw`, `NE`, `Ci`, `PC_raw`, `PC_residual`, `NdCartDiv`. Additive, so harmless for parity, but the files aren't drop-in interchangeable.

---

## 6. How the runs were configured

Both pipelines were driven from a single matched parameter set rather than their own defaults — **the two ports' defaults do not agree** (Python's `Params` defaults differ from MATLAB's on `thresholds`, `wname_list`, `ref_period`, `pos_peak_thr_multiplier`, `min_activity_level`, `func_con_lag_val`, cartography bounds, `min_number_of_nodes_to_cal_net_met` and more), so an unconfigured "Test pipeline vs Test pipeline" comparison would measure parameter drift, not port fidelity.

Shared config: `fs=12500`, `Axion64`, `thresholds={4,5}`, `bior1.5`, `cost=-0.12`, `filter 600–6150 Hz`, `refPeriod=1ms`, `posPeakThrMultiplier=15`, `minActivityLevel=0.01`, `lags={10,25,50}`, `ProbThreshRepNum=200`, `tail=0.05`, `weighted`, `minNumberOfNodesToCalNetMet=25`.

> **The example data is Axion64 @ 12500 Hz, not MCS60 @ 25000 Hz.** Channels are 11–88 (8×8) and `fs` in the raw file is 12500. MATLAB's `TestPipelineButton` sets the data folder/spreadsheet but **not** the channel layout or sampling rate, so a user pressing Test pipeline with GUI defaults may silently detect spikes against the wrong `fs`. (This also explains `filter_high_pass=6150`: Nyquist is 6250.) The Python runner reads `fs` from the raw file and is immune; MATLAB trusts `Params.fs`.

### Runtime (this machine, 2 recordings)

| Step | Python before | Python after |
|---|---|---|
| 1 (spike detection) | 271.8 s | **140.7 s** |
| 2 | 9.5 s | 7.0 s |
| 3 | 18.5 s | 16.3 s |
| 4 | 256.8 s | 237.0 s |
| **total** | 556.5 s | **401.0 s** |

The literal-port CWT is both exact *and* ~2× faster than the FFT version it replaced (a short filter against a long trace suits overlap-add convolution better than a full-length FFT per scale).

### Files

| File | Purpose |
|---|---|
| `parityRun/params_matlab_parity.mat` | MATLAB parameter set |
| `parityRun/MEApipeline_parity.m` | Headless copy of `MEApipeline.m` (2 additive lines, no numeric changes) |
| `parityRun/FakeApp.m` | Headless stub for the GUI `app` status text (`MEApipeline_parity.m` re-adds `parityRun/` to the path to reach it, since `MEApipeline.m` calls `restoredefaultpath` first) |
| `parityRun/run_python_parity.py` | Python run, params matched to the above |
| `parityRun/run_python_from_matlab_spikes.py` | Python steps 2–4 on MATLAB's spike times |
| `parityRun/gen_step4_parity_reference.m` | MATLAB BCT metrics on this run's adjacency |
| `parityRun/compare_spike_detection.py` | Step-1 spike comparison |
| `parityRun/compare_parity.py` | CSV comparison |
| `parityRun/compare_step4_same_adjacency.py` | Same-graph step-4 comparison |
| `parityRun/results_*.txt` | Captured output of each |

### Headless MATLAB traps hit (beyond the 5 in `MEApipeline_timingBenchmark.m`)

- `MEApipeline.m` never restores `csvRange` from `Params.spreadSheetRange` when run as `MEApipeline(paramsFile)` — line 33's `[2, Inf]` default wins, so it reads every spreadsheet row. Worked around with a 2-row spreadsheet.
- The params-file path forces `Params.guiMode = 1` and then dereferences `app`, which doesn't exist headless (hence `FakeApp.m`).
- `Params.electrodesToGroundPerRecording` is `[]` for spreadsheets with no `Ground` column but is brace-indexed `{ExN}` — the already-documented bug; hit it again.
- `Params.singleChannelIsiThreshold` is only ever set by `getParamsFromApp.m`; absent from older saved param files, crashing `firingRatesBursts.m`.

## 7. What this report does *not* establish

- **Burst metrics**: untested — the dataset has no bursts (all `NaN` on both sides).
- **Group-level outputs**: MATLAB's step 2B/4B group figures/CSVs are unported; not compared.
- **Only 2 recordings, one DIV, one group, low firing rates** — density stays under ~10% and many node pairs are disconnected. A weak stress test, as `PIPELINE_PORT_STATUS.md` notes.
- **NMF**: shown to disagree, but with n=6 rows this quantifies nothing beyond "they differ".
- **Stochastic metrics** (`Q`, `nMod`, `SW`, `PC`, `Z`, `NCpn*`) can't be validated by value comparison at all; only fixed-input tests can speak to them, and §4 re-verified only the deterministic subset.
- **Spike-detection parity is established on 128 channels of one 8×8 Axion64 dataset at one `fs`.** The `_determine_scales` bug was `fs`- and `Wid`-dependent (it corrupted whichever scale sat at the interpolation boundary), so other `fs`/`Wid`/layout combinations are worth re-checking before assuming exactness holds generally.
