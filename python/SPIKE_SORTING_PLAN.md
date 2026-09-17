# Spike sorting in MEA-NAP — Survey & Plan

Living plan for adding **spike sorting** (units, not electrodes, as the nodes
of the network) as an option in the Python MEA-NAP pipeline. Mirrors the style
of `CATNAP_PORT_PLAN.md` and `MEASTIM_PORT_PLAN.md`. Read this before touching
`src/meanap/pipeline/spike_sorting.py` (once it exists).

Written 2026-09-16. Feasibility run on `local/HP_rawData/HP_tc043_DIV21.mat`.

## 1. Why this is a different problem from Neuropixels sorting

MEA-NAP's supported hardware is **low-density**: MCS 60MEA (200 µm pitch,
30 µm electrodes), Axion 64/16 (350 µm pitch). At these pitches an
extracellular spike (~100 µm reach) is seen on **one electrode only**. So:

- There is **no spatial footprint** to cluster on. Sorting is per-electrode
  waveform clustering (amplitude / shape / PCA), exactly the "tetrode-era"
  problem that Wave_clus, Tridesclous, Offline Sorter etc. were built for.
- Drift correction, template spatial matching and multi-channel whitening —
  the things Kilosort4 / SpyKING CIRCUS 2 / DARTsort are optimised for —
  bring nothing here and can actively hurt (Kilosort's own docs: set
  `nblocks=0` for ≤64 ch or ≥50 µm spacing; reduce `nearest_chans`,
  `nearest_templates` to avoid numerical instability on sparse arrays).
- Multiple neurons per electrode are common in dense cultures (the SAMS paper,
  Axion plates, finds 1–4 units per electrode); overlapping spikes (bursts!)
  are the hard case, and a template-matching ("peeling") stage helps there.
- Realistic sorting yields for a 60MEA culture recording: roughly 1–3 units
  on active electrodes → ~50–150 units per recording rather than 60 nodes.
- Curation matters more than sorter choice: on low-density arrays, unit
  quality (SNR, ISI-violation rate, presence ratio) is what separates a
  believable node from noise, so **quality metrics + auto-curation** are
  part of the feature, not an afterthought.

The user's HD-MEA future (MaxWell / 3Brain, thousands of electrodes at
~17 µm pitch) is the opposite regime; there the dense-probe sorters apply and
RT-Sort / HerdingSpikes become relevant. Not in scope for this plan, but the
SpikeInterface layer chosen below makes it a config change, not a rewrite.

## 2. Survey of tools (September 2026)

### 2.1 The framework: SpikeInterface (use it)

[SpikeInterface](https://github.com/SpikeInterface/spikeinterface) 0.104.x
(Python; installs cleanly on **Python 3.13** with `uv`, verified) is the de
facto standard wrapper. It gives us, with one API:

- **Recording abstraction** — `NumpyRecording` wraps the `(n_samples, n_ch)`
  float array MEA-NAP already loads (`io.load_raw_recording`), so no new
  readers. Also has native MCS `.h5` and Axion readers if we ever want lazy
  loading. Electrode geometry attaches via `probeinterface.Probe`, which we
  can build from `channel_layout.get_coords_from_layout` (MCS60/59/Axion).
- **Lazy preprocessing** — bandpass, common median reference, whitening.
- **`run_sorter(name, …)`** — one call for ~20 sorters; the *internal*
  sorters need no extra install; external ones can run in Docker/Singularity.
- **`SortingAnalyzer`** — waveforms, templates, unit locations, spike
  amplitudes, **quality metrics** (SNR, ISI violations, presence ratio,
  amplitude cutoff, …), auto-merging (`auto_merge_units`), auto-curation
  rules, and export to Phy for manual curation.
- **`compare_sorter_to_ground_truth` / `compare_multiple_sorters`** — for
  validating one sorter against another or against MEA-NAP's threshold
  detection.

Cost: it is a heavy dependency tree (numpy/scipy/pandas which we have, plus
`probeinterface`, `neo`, `zarr`, `hdbscan`, `numba`, and `torch` for its
internal sorters). Plan: make it an **optional extra** (`meanap[sorting]`),
exactly like `oasis` for CAT-NAP.

### 2.2 Candidate sorters for low-density MEA

| Sorter | Runs via SI | Install | GPU | Fit for 60MEA / Axion | Notes |
|---|---|---|---|---|---|
| **MountainSort5** (scheme 2) | yes | `pip install mountainsort5` | no (CPU) | **good** — ISO-SPLIT clustering on per-channel PCA; radius params shrink to single-channel naturally | Fully automatic, no manual curation designed in. Fast. Python 3.13 OK. |
| **Tridesclous2** | yes (internal) | none | no | **good** — originally built for tetrodes / few channels; per-channel detection + HDBSCAN + template matching | Pure SpikeInterface components. |
| **SpyKING CIRCUS 2** | yes (internal) | none | no | ok — has OMP template matching (good for overlapping spikes in bursts); drift correction must be switched off | Default `apply_motion_correction=True` — must set False for MEAs. |
| **Lupin** (new, SI 0.104, Mar 2026) | yes (internal) | none | no | plausible — "best components on benchmarks"; untested on low-density | Newest; benchmark evidence is Neuropixels-centred. |
| **Kilosort4** | yes | `pip install kilosort` + torch | *designed* for GPU; runs on CPU (slow but 60 ch × 10 min is tractable) | marginal — needs `nblocks=0`, `nearest_chans`/`nearest_templates` ≤ n_ch, `dmin/dminx≈200`, `x_centers`; known issues on widely spaced 2D arrays ([Kilosort #644](https://github.com/MouseLand/Kilosort/issues/644)) | Best-known name, which matters for users; but it is the wrong tool for this geometry and its docs say so. Keep as an *opt-in* choice. |
| **Wave_clus** | yes (MATLAB or container) | MATLAB | no | **the classic single-electrode sorter**; SPC clustering on wavelet coefficients, strong on cultures | MATLAB — same licence issue we are moving away from; via `docker_image=True` it works without MATLAB. Good reference for validation. |
| **SAMS** (2025/26, Zhao lab) | no | MATLAB, Axion-specific | no | designed exactly for low-density culture MEAs (spectral clustering + dip test + DTW) | Reports 67–94 % accuracy vs 44–65 % for Plexon Offline Sorter. Not Python; a reference point, not a dependency. |
| HerdingSpikes2, RT-Sort, DARTsort | yes | varies | RT-Sort/DARTsort: GPU | **no** — need dense arrays (spatial location / axonal propagation across adjacent electrodes) | Relevant only if MEA-NAP gains HD-MEA support. |
| Plexon Offline Sorter, MCS Multi Channel Analyzer | no | commercial GUI | — | common in culture labs | Could accept their exported unit spike times as `spike_detected_data` input. |

Evidence base for the low-density claims:
- Kilosort4 parameter guidance for sparse / ≤64-ch probes:
  https://kilosort.readthedocs.io/en/latest/parameters.html
- Wave_clus vs Klusta/MountainSort/Kilosort/SpyKING CIRCUS on few-channel data
  (Chaure et al. 2018, J Neurophysiol): https://journals.physiology.org/doi/full/10.1152/jn.00339.2018
- SAMS for low-density culture MEAs (2026): https://pmc.ncbi.nlm.nih.gov/articles/PMC13083792/
- SpikeInterface sorters module: https://spikeinterface.readthedocs.io/en/latest/modules/sorters.html
- SpikeInterface internal sorters (Lupin, TDC2, SC2, simple): https://spikeinterface.readthedocs.io/en/latest/modules/sorters_internal.html
- Sorter comparison, brainstem large-scale (2024; KS3/IronClust least curation, MS5/SC most): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11601346/

### 2.3 Recommendation

Wrap **SpikeInterface** and expose a `sorter` choice. **Default:
Tridesclous2** — chosen by the synthetic ground-truth benchmark in §5.1,
which overturned the provisional MountainSort5 choice: TDC2 found more
neurons with *zero* false-positive or over-split units where MS5 left
several of each. MS5 stays as the faster alternative, SC2/Lupin as
built-in options, Kilosort4 opt-in for GPU owners.

## 3. Feasibility on `HP_tc043_DIV21` (60MEA200/30, 25 kHz, 600 s)

Machine: 16 CPU, 26 GB RAM, **no GPU**. Script:
`local/spikesort_test/feasibility.py` (venv in `local/spikesort_test/venv`).
Preprocessing: bandpass 300–6000 Hz, global median reference, saved to disk
(3.6 GB float32). Reference: MEA-NAP's own detection on the same file
(`HP_tc043_DIV21_spikes.npz`): thr4 121 548, thr5 60 518, bior1.5 172 534
spikes over 60 channels.

### 3.1 Sorter runs (CPU, 8 workers)

| Sorter | Wall time | Units | Electrodes with ≥1 unit | Units/electrode (max) | Spikes (all units) |
|---|---|---|---|---|---|
| MountainSort5 scheme 2 | 40 s | 43 | 36 | 1 on 30, 2 on 5, 3 on 1 | 96 052 |
| Tridesclous2 | 54 s | 49 | 48 | 1 on 47, 2 on 1 | 105 247 |
| SpyKING CIRCUS 2 | 338 s | 35 | 29 | 1 on 28, **7 on 1** | 133 758 |
| Lupin | 83 s | 51 | 45 | 1 on 42, 2 on 2, 5 on 1 | 71 526 |
| Kilosort4 (CPU) | not run yet | | | | |

SC2 is 6–8× slower than the others (OMP template matching over the full
recording) and puts 7 units on one electrode — an over-split to look at, or
a burst-overlap artefact. Lupin finds the fewest spikes (71 k, below thr5's
60 k + margin) for the most units. MS5 and TDC2 remain the sensible
defaults; SC2/Lupin stay available as alternatives.

Gotchas found:
- `spikeinterface[full]` pulls a **CUDA torch** (~5 GB) even on a GPU-less
  box, and *still* does not install `hdbscan` on Python 3.13 — SC2 and Lupin
  fail with `ModuleNotFoundError: hdbscan`. A minimal
  `spikeinterface + mountainsort5 + hdbscan` install is 293 MB, no torch, and
  registers all five CPU sorters. That is what the `[sorting]` extra should be.
- Loading the whole 60 × 15 M float64 `.mat` as float32 is 3.6 GB; the
  preprocessed copy on disk is another 3.6 GB. Do not put either on `/tmp`
  (14 GB RAM-backed tmpfs on this machine). Use the output folder.
- The preprocessed recording must be **saved to disk** before sorting; the
  internal sorters and MS5 read it in chunked parallel workers.

### 3.2 Agreement with MEA-NAP's threshold detection (MS5 / TDC2)

Per-electrode sum of unit spike counts vs. MEA-NAP's own detections on the
same file (Pearson r on log1p counts, 60 electrodes):

```
        thr4  thr5  bior  ms5  tdc2
thr4    1.00  0.97  0.91  0.91  0.82
thr5    0.97  1.00  0.97  0.91  0.91
bior    0.91  0.97  1.00  0.86  0.96
ms5     0.91  0.91  0.86  1.00  0.77
tdc2    0.82  0.91  0.96  0.77  1.00
```

Totals: thr4 121 548 · thr5 60 518 · bior1.5 172 534 · **MS5 96 052 · TDC2
105 247**. So the sorters recover roughly the thr4 spike population, and on
the busiest electrodes (e.g. 25, 67, 51, 57) 5–7 k spikes each, in line with
thr4. Nothing pathological: no electrode where a sorter finds zero and
thresholding finds thousands, or vice versa.

### 3.3 Where the sorters disagree, and what "good unit" should mean here

- **Unit-to-unit agreement between MS5 and TDC2 is moderate**: 20 / 43 MS5
  units match a TDC2 unit at > 50 % spike agreement (0.4 ms window). This is
  the known reality of single-electrode sorting — there is no spatial
  signature to disambiguate, so different clustering choices give different
  splits on the same electrode. Consequence for the design: (a) validate on
  synthetic ground truth before choosing the default, (b) surface unit QC
  prominently, (c) keep the per-electrode (unsorted) result as the baseline
  users can fall back to.
- **MS5 unit quality** (43 units): SNR 5.5–10.4 (median 6.6), presence ratio
  1.0 everywhere, firing rate 0.4–12.5 Hz. But the SpikeInterface default
  `isi_violations_ratio` (Hill's Poisson-normalised contamination) is 4–62
  for every unit — far above the usual 0.5 cutoff — because it assumes
  Poisson firing and cultured neurons burst. The **raw fraction of ISIs
  < 1.5 ms** is the honest number: 0.7–5 % for the 14 low-rate units,
  10–22 % for the high-rate (7–12 Hz) units, which are plausibly
  multi-unit clusters MS5 did not split. So MEA-NAP's curation should use
  `rp_violations` / a violation *fraction* threshold (and `sliding_rp_violation`),
  not `isi_violations_ratio`, and should label rather than delete: `good`
  (< 5 % violations) vs `mua`. High-rate electrodes carrying 2–3 real units
  that a sorter leaves merged still deserve to be a node — as `mua`.


## 4. Design

### 4.1 Where it sits in the pipeline

Step 1 today: raw → `detect_spikes_recording` → `{ch: {method: times}}` →
`_spikes.npz`. Steps 2–4 read `spike_times_{node}_{method}` and treat
`node` as an electrode index, with coordinates from `params.channel_layout`.

Spike sorting becomes a **Step 1 alternative** (`params.spike_source =
"detect" | "sort"`), not a Step 1.5, because both produce the same thing —
a set of spike trains that are the pipeline's nodes:

```
raw (n_samples, n_ch) ──detect──▶ one train per electrode ──▶ steps 2–4
                      ──sort────▶ one train per unit      ──▶ steps 2–4
```

The sorted output is written with the **same** `save_spike_times_npz` writer
using method name `sorted` (so `spikes_method="sorted"` selects it
downstream), plus unit metadata arrays:

```
spike_times_{unit_idx}_sorted     # seconds, one per unit
waveforms_{unit_idx}_sorted       # template ± samples, float32
unit_channel                      # (n_units,) 0-based index of the electrode the unit lives on
unit_channel_id                   # (n_units,) MCS/Axion channel ID
unit_coords                       # (n_units, 2) µm, electrode coords + small deterministic jitter
unit_quality_{snr,isi_violations_ratio,firing_rate,presence_ratio,amplitude_cutoff}
unit_label                        # 'good' | 'mua' | 'noise' from auto-curation
sorter_name, sorter_version, sorter_params (json string)
```

Downstream consequences (each small, but they are the real work):

- **Step 2** (`step2.py`, `firing_rates_bursts`): works unchanged on
  per-node trains. Per-electrode CSV columns become per-unit rows; add
  `unit_channel_id` so the electrode is still recoverable.
- **Step 3** (STTC): unchanged — pairwise on nodes.
- **Step 4** (network metrics & plots): already accepts `coords_all` (one
  row per node, added for CAT-NAP ROIs). Pass `unit_coords` instead of the
  layout lookup. Node cartography / heatmaps that index the 8×8 grid by
  electrode need the electrode-heatmap variants to aggregate units → electrode
  (sum of rates, max of degree) or be skipped in `sort` mode.
- **Grounded electrodes** (`ground_spike_times_dict`) must map to units via
  `unit_channel`.
- **Viewer / spike-check plots**: per-unit waveform overlay on the parent
  electrode's trace; a units-per-electrode summary figure.
- **MATLAB pipeline**: not ported. But the sorted file can also be written as
  a `_spikes.mat` with `spikeTimes{unit}.sorted` so MATLAB users can point
  `spikeDetectedData` at it — the "channels" would then be units; only
  `channel_layout`-based plots break. Document, do not fix.

### 4.2 Module layout

```
src/meanap/pipeline/spike_sorting.py     # build Recording+Probe, preprocess, run_sorter,
                                         # analyzer + quality metrics + auto-curation,
                                         # → SpikeSortingResult (same shape as SpikeDetectionResult + unit metadata)
src/meanap/pipeline/probes.py            # channel_layout → probeinterface.Probe (MCS60/59/old, Axion64/16)
src/meanap/params.py                     # spike_source, sorter_name, sorter_params, curation thresholds
src/meanap/gui/panels/spike_detection.py # "Spike source: detect / sort" + sorter dropdown + curation thresholds
python/test_spike_sorting.py             # synthetic ground truth (SI's generate_ground_truth_recording on a 60MEA probe)
```

`spikeinterface` is imported lazily inside `spike_sorting.py`; the GUI greys
out "sort" with an install hint when the extra is missing (same pattern as
OASIS in CAT-NAP).

### 4.3 Parameters (initial)

| Param | Default | Notes |
|---|---|---|
| `spike_source` | `detect` | `sort` enables this path |
| `sorter_name` | `mountainsort5` | also `tridesclous2`, `spykingcircus2`, `lupin`, `kilosort4` |
| `sorter_params` | `{}` | passthrough to `run_sorter`, merged over per-sorter MEA presets |
| `sort_freq_min/max` | 300 / 6000 Hz | preprocessing band (separate from detection's 600–8000) |
| `sort_common_reference` | `global_median` | or `none` |
| `curation_min_snr` | 4 | |
| `curation_max_rp_violation_frac` | 0.05 | fraction of ISIs < 1.5 ms; **not** SI's Poisson `isi_violations_ratio`, which is meaningless for bursting cultures (§3.3) |
| `curation_min_firing_rate` | 0.05 Hz | drops empty units |
| `curation_keep_labels` | `['good']` | or `['good','mua']` to include multi-unit nodes |
| `auto_merge` | True | SI `auto_merge_units` over-split fix |

Per-sorter MEA presets (baked in, user-overridable): MS5 `scheme=2,
scheme2_detect_channel_radius=50, snippet_mask_radius=100, filter=False`
(we prefilter); SC2/TDC2 `apply_motion_correction=False`; KS4 `nblocks=0,
nearest_chans=min(10,n_ch), nearest_templates=n_ch, dmin=dminx=pitch,
x_centers=n_cols`.

## 5. Validation

### 5.1 Synthetic ground truth → the default sorter (done)

`src/meanap/pipeline/sorting_benchmark.py` simulates a recording on the real
MCS60 geometry: 30 active electrodes with 1–3 neurons each (10–45 µm from
the electrode), peak amplitude log-uniform 15–120 µV, 5 µV noise, tonic
0.2–2 Hz firing plus network bursts every 1.5–4 s (2–8 spikes per neuron
per burst, 70 % participation), 2 ms refractory. Scored with
`compare_sorter_to_ground_truth` (0.4 ms match window).
`python/benchmark_spike_sorting.py`, 3 seeds × 120 s, 8 workers, run
2026-09-16 with the presets in `spike_sorting.py`:

| Sorter | Found (acc ≥ 0.5) / ~52 | Well (≥ 0.8) | FP units | Redundant | Accuracy | Precision | Recall | Time |
|---|---|---|---|---|---|---|---|---|
| **Tridesclous2** | **43.0** | **38.3** | **0.0** | **0.0** | **0.78** | 0.79 | 0.83 | 30 s |
| MountainSort5 sch. 2 | 38.3 | 26.7 | 4.0 | 5.7 | 0.64 | 0.73 | 0.66 | 19 s |

Per seed TDC2 led on every count (found 43/45/41 vs 38/36/41; well 39/41/35
vs 28/25/27). Verdict: **Tridesclous2 is the default.** Also learned:

- Curation changed nothing on synthetic data (no noise units; every unit
  `good`) — the floors are for real recordings, where the feasibility run
  showed high-rate units with 10–22 % refractory violations.
- `auto_merge_units` (presets `similarity_correlograms`, `x_contaminations`,
  `temporal_splits`, `feature_neighbors`) did not recover MS5's redundant
  units — the presets look for split *fragments* of one neuron, not two
  amplitude-clusters of one; so `sort_auto_merge` ships **off**.
- The smoke-level version (40 s, 16 electrodes) is in
  `python/test_spike_sorting.py` and must keep ≥ 60 % of neurons found and
  ≤ 15 % false positives.

### 5.2 Real data (`HP_tc043_DIV21`)

Steps 1–4 in `sort` mode: `local/spikesort_test/real/run_real.py` — the
numbers are in §5.3. The censor step (`sort_censor_ms`, 0.3 ms) was added
because of this run; see there.

### 5.3 Electrode-level vs unit-level network

Steps 1–4 in both modes on `HP_tc043_DIV21` (`local/spikesort_test/real/`,
`run_real.py`; comparison by `python/compare_sorted_vs_detected.py`,
2026-09-16, Tridesclous2 with the shipped presets, 5 min per mode of which
sorting is 2.5 min on 15 workers):

- **Node set**: 48 units on 48 electrodes (one per electrode; a second run
  before the censor step had one electrode with two). 6 404 duplicate spikes
  (< 0.3 ms apart, 2 % of the total) removed by the censor step — before it,
  the busiest unit had 652 intervals under 0.25 ms, an impossible number for
  one neuron.
- **Curation**: 8 `good`, 40 `mua`, 0 noise. Refractory violations scale
  with firing rate (0.5 % at 0.4 Hz → 30–40 % at 10 Hz). This is the
  culture, not the sorter: MEA-NAP's own thr4 detection on electrode 57
  (2 ms refractory enforced) has 47 % of ISIs under 3 ms — each busy
  electrode hears a population firing at hundreds of Hz in bursts, and no
  single-electrode sorter can separate that. The docs say so; the unit
  quality figure shows it.
- **Network** (detected → sorted): aN 59 → 48, density 0.94 → 1.00 (10 ms)
  and 0.90 → 1.00 (25 ms), Eglob 0.42 → 0.65 / 0.46 → 0.74, Q 0.50 → 0.49 /
  0.49 → 0.37, nMod 2 → 2. The sorter's 5×MAD detection floor drops the
  eleven quietest electrodes, and among the rest every pair is significantly
  correlated — this recording is one big network burst generator at both
  lags in both modes. So on this recording sorting changes the node set
  (fewer, cleaner nodes) more than the topology, which is the expected
  outcome for a dense culture on a 200 µm array.

### 5.4 Tridesclous2 vs bior1.5, spike by spike (2026-09-17)

On the 48 sorted electrodes of `HP_tc043_DIV21` (±0.5 ms match): 71 % of
TDC2 spikes coincide with a bior1.5 spike but only 43 % of bior1.5 spikes
with a TDC2 one; 68 % of thr5 spikes are in TDC2. Per-electrode counts
correlate r ≈ 0.96. The divergence is (a) small spikes below TDC2's 5 × MAD
floor, (b) burst-interior timing — thr4/thr5's refractory period removes
follow-on population spikes, TDC2 and bior1.5 keep them — and (c) bior1.5's
**double detections**: every bior1.5 pair closer than 0.5 ms is one trough
detected twice (5–6.5 % of spikes on busy electrodes), fixed by
`Params.wavelet_ref_period_ms` (default 0.5 ms; see `PIPELINE_PORT_STATUS.md`
"Spike detection gotchas" and `docs/python/matlab-vs-python.md`). Figures and
script: `local/spikesort_test/real/bior_doubles.{py,png}`. The spike-by-spike
comparison is reproducible on any pair of runs with
`python/compare_spike_trains.py` (it also showed TDC2's own unmatched spikes
sit at a median 3 σ — sub-threshold spikes the peeler recovered under larger
ones). User-facing summary: `docs/python/spike-sorting.md`, "How sorted units
compare with bior1.5 detection".

### 5.5 Wavelet candidates into TDC2, vs a lower threshold (2026-09-17)

Question: can bior1.5's sensitivity to small spikes be combined with TDC2's
clustering, and is that better than simply lowering TDC2's threshold?
Finding first: stock TDC2's `detect_threshold` only feeds the clustering; the
**peeler** re-detects with its own threshold, hard-wired at 5 σ, and the
peeler's spikes are the output. So "lower the threshold" needs the peeler's
threshold lowered too, which the sorter does not expose.
`pipeline/sorting_components.py` rebuilds TDC2's chain from its components
with the candidate source, the peeler threshold and the assignment mode
exposed (verified to reproduce stock TDC2 within one unit per seed).
`python/benchmark_hybrid_sorting.py`, ground truth with units 10–120 µV on
5 µV noise (a third under 25 µV), 3 seeds × 120 s, scored **after MEA-NAP
curation**:

| condition | found /~52 | well | FP nodes | recall | recall <25 µV |
|---|---|---|---|---|---|
| **TDC2 stock (5 σ/5 σ)** | **39.0** | 31.0 | 0.3 | 0.72 | **0.53** |
| thr 4 σ / peeler 4 σ | 37.0 | 31.7 | **52.7** | 0.71 | 0.51 |
| thr 3.5 σ / peeler 3.5 σ | 37.0 | 32.3 | 0 | 0.71 | 0.48 |
| bior1.5 → peeler 5 σ | 38.7 | 30.7 | 0 | 0.71 | 0.52 |
| bior1.5 → peeler 3.5 σ | 35.7 | 32.3 | 0 | 0.69 | 0.45 |
| bior1.5 → no peeler (wavelet decides spikes) | 32.7 | 25.7 | 2.7 | 0.61 | 0.30 |

Neither route finds more small neurons than stock. A lowered threshold makes
50–60 noise clusters; at 3.5 σ curation drops them all (SNR < 4), at 4 σ
they sit just above the floor and 53 survive as false nodes. Wavelet
candidates through the peeler are a wash (the peeler re-detects; the wavelet
only shaped the templates, no better). Wavelet candidates *without* the
peeler are the worst condition: the peeler is what recovers small and
overlapping spikes, by subtracting the large one and fitting the residual,
and no single-pass candidate list can replace that. Near the noise floor
bior1.5's shape criterion carries no more information than amplitude — it
returned 14 500 candidates for ~13 000 true spikes, the excess being 4–5 σ
noise. **Verdict: keep stock TDC2.** The missing sub-25 µV neurons are at
2–4 σ and not recoverable from per-electrode data.

### 5.6 The same conditions on `HP_tc043_DIV21` (no ground truth)

`local/spikesort_test/real/hybrid_real.py`, after MEA-NAP curation:

| condition | candidates | raw units / spikes | kept units (good/mua) | dropped | kept spikes | electrodes | median SNR | median RP viol. |
|---|---|---|---|---|---|---|---|---|
| **thr 5 / peeler 5 (stock)** | 101 635 | 49 / 108 k | 49 (12/37) | 0 | 101 k | 48 | 5.3 | 0.12 |
| thr 4 / peeler 4 | 185 053 | 61 / 193 k | 48 (13/35) | 13 | 159 k | 47 | **4.35** | 0.17 |
| thr 3.5 / peeler 3.5 | 368 741 | 63 / 395 k | 17 (2/15) | 46 | 111 k | **15** | 6.6 | 0.26 |
| bior1.5 → peeler 5 | 167 132 | 52 / 129 k | 52 (11/41) | 0 | 119 k | 48 | 5.35 | 0.135 |
| bior1.5 → peeler 3.5 | 167 132 | 51 / 245 k | 19 (0/19) | 32 | 106 k | 19 | 6.7 | 0.29 |
| bior1.5 → no peeler | 167 132 | 52 / 167 k | 19 (2/17) | 33 | 102 k | 16 | 5.9 | 0.38 |

Lowering the threshold: at 4 σ the kept spike count rises 57 % but the
median unit SNR falls to 4.35 — right on the curation floor — and refractory
violations rise; at 3.5 σ the candidates are mostly noise (369 k for a
recording with ~100 k real spikes), the templates are polluted, and curation
discards 46 of 63 units, leaving 15 electrodes. bior1.5 candidates through
the 5 σ peeler is the one variant that does no harm: 52 units on the same 48
electrodes, +18 % spikes, SNR and violations unchanged — presumably real
small spikes matched to templates the wavelet candidates let the clustering
form. Whether those spikes are real cannot be told here; on ground truth
(§5.5) the same condition found no more neurons and no more small-unit
recall than stock. Below the 5 σ peeler, wavelet candidates collapse the
recording as badly as a 3.5 σ threshold. **Verdict stands: stock TDC2.**
The component chain is kept (`pipeline/sorting_components.py`) for anyone
who wants to revisit this with a different candidate detector.

## 6. Implementation (done 2026-09-16)

- [x] `pipeline/probes.py` — `probeinterface.Probe` from every
      `channel_layout` at its real pitch (MCS 200 µm, Axion 350 µm; override
      `electrode_pitch_um`). Channels the layout cannot place are left off.
- [x] `pipeline/spike_sorting.py` — `build_recording` → `preprocess` (bandpass,
      global median reference, float32 to disk, **in-process**: a spawned
      worker would receive a pickled copy of the in-memory array) →
      `run_sorter_on` (presets per sorter, all spatial radii 0.4 × pitch,
      drift correction off) → `curate_sorting` (analyzer, SNR/rate/presence,
      refractory-violation *fraction*, labels, unit IDs `<electrode>-<rank>`,
      ring coordinates) → `SpikeSortingResult`. Workers are **spawned**, via
      SpikeInterface's global job kwargs so the sorters' internal stages
      comply; a fork copies the pipeline process (it complained at exit).
- [x] `io.py` — `save_spike_times_npz(units=…)` writes `unit_*` arrays;
      `SpikeFile.units` / `.sorted` read them back. `channels` = parent
      electrode per unit (repeats), method `sorted`.
- [x] `params.py` — `spike_source`, `sorter_name`, `sorter_params`,
      `sort_*`, `curation_*`, `keep_sorter_output`; `active_spike_method()`
      returns `sorted` in sort mode and steps 2/3/4, stim and render use it.
- [x] `runner.py` — `_sort_one_recording`: the `sort` branch of step 1,
      same output paths, sorting checks + `units.csv`; scratch under
      `1A_SpikeDetectedData/sorting/<rec>/`, removed unless kept.
- [x] `plotting_sorting.py` — three check figures + payload for the bundle.
- [x] Steps 2/3/4 — heatmaps pool units onto electrodes (rates sum, else
      mean); node CSVs gain `Unit`/`UnitLabel`; step 3 copies `unit_coords`
      into `_adjM.npz` as `coords`; step 4's plot phase passes them as
      `coords_all` (the CAT-NAP path). Renderer already reads `coords`.
- [x] Spike viewer — a sorted file lists `unit 25-1`… and draws each on its
      electrode's trace (`_trace_column`).
- [x] GUI — Spike source combo + sorter combo, folded "Spike sorting"
      section; greyed with an install hint without the extra.
- [x] `pyproject.toml` `[sorting]` extra; docs page
      `docs/python/spike-sorting.md`; install note.
- [x] Tests: `python/test_spike_sorting.py` (54 checks incl. steps 1–4 end
      to end on synthetic data); `python/benchmark_spike_sorting.py`.
- [x] Fixed along the way: `remote/source.py` local stream yielded inside
      `except BaseException`, so every step-1 run printed "generator ignored
      GeneratorExit" to stderr at the end of the batch; `parallel.spawn_usable`
      now says no for a script piped on stdin.

Not done / follow-ups:
- MATLAB pipeline: not touched. A sorted `.npz` cannot be read by MATLAB's
  `spikeDetectedData` path (it wants `_spikes.mat`); writing that is a small
  exporter if anyone asks.
- Bundle viewer re-rendering of the sorting check figures from their payload
  (`load_sorting_check_data` exists; the viewer's figure registry does not
  list them yet).
- Phy export (`si.export_to_phy`) behind `keep_sorter_output`.
