# Importing spike-sorted data (+ light stimulation) — plan and status

Goal: let the Python MEA-NAP take **units sorted elsewhere** (SpyKING CIRCUS,
Kilosort/phy, anything SpikeInterface reads) as step-1 input, and analyse
**stimulus-triggered** activity and networks for event-driven stimulation
(light flashes) through MEA-Stim.

Test data: `local/test-spike-sorted-data/` — one
recording on a **MaxWell MaxOne** (legacy-layout `.raw.h5`, 941 routed
electrodes at 17.5 µm pitch, 20 kHz, 126.68 s), SpyKING CIRCUS output (306
merged templates), the collaborator's own `_spikes.mat` export, and a MATLAB
MEA-NAP run of that export (kept locally).

## What the test data told us

* The collaborator's `_spikes.mat` is the sorter's spikes, unchanged, except
  for a **truncation to 126 s** (≈0.5 % of spikes lost). Each unit sits at its
  template's peak electrode, looked up in the raw file's `settings/mapping`.
  We keep the full 126.68 s (decided 2026-10-20).
* Light stimulation is in the raw file's `bits` dataset (TTL word per change):
  bit value 32 toggles at 60 Hz (projector frame sync), `word == 0` blips
  (0.1–0.5 ms) mark **57 events** with alternating 2.0 s / 2.5 s spacing (120 /
  150 frames). This reads as a full-field flash with a transition at each
  marker.
* **No unit responds to the markers beyond chance**: for every window and every
  event subset tested, the number of units with p < 0.01 (against circularly
  shifted events) was 0–4, where about 3 are expected by chance. The population
  rate is flat at ~24 Hz across the markers. So this recording is a
  **no-response control**: it checks the plumbing and the false-positive rate.
  Showing that a real response is detected needs synthetic data with injected
  responses (below).

## Design

### Units in, unchanged steps 2–4 out
The `sort` spike source already makes units the nodes: `_spikes.npz` holds one
train per unit under method `sorted`, `channels` = each unit's parent electrode,
and `unit_*` arrays (`unit_id`, `unit_coords`, …). Step 3 forwards `unit_coords`
to the adjacency file, so step 4 draws units where they are. An import writes
**that same file**, so nothing downstream needs to know where the units came
from.

### `spike_source = "import"`
* `src/meanap/pipeline/sorted_import.py` — `ImportedSorting` (unit trains in
  s, sorter unit IDs, peak electrode ID + position (µm), fs, duration, labels,
  templates where available) and readers:
  * `read_spykingcircus` — `<base>.result[-merged].hdf5` +
    `<base>.templates[-merged].hdf5` (peak electrode = argmax |template|).
  * `read_phy` — a phy folder (`spike_times.npy`, `spike_clusters.npy`,
    `params.py`, `channel_map.npy`, `channel_positions.npy`, `templates.npy`,
    `cluster_group.tsv` / `cluster_KSLabel.tsv`). Covers Kilosort 1–4,
    SpyKING CIRCUS's phy export and SpikeInterface's `export_to_phy`.
  * `read_spikeinterface` — fallback for any format SpikeInterface reads
    (optional dependency, imported lazily).
* Recording metadata (fs, exact duration, electrode positions, TTLs) comes from
  the raw file when there is one. `src/meanap/pipeline/maxwell.py` reads MaxWell
  `.raw.h5` **metadata only**: the voltage is never loaded, since an import has
  no use for it, and it is 4.7 GB here.
* Matching to the spreadsheet: sorter outputs in `sorted_data_folder` are
  matched by recording name (`<name>.*result*.hdf5`, a phy folder named for the
  recording, or `<name>/<name>.GUI`).

### Node positions from the file (`channel_layout = "FromFile"`)
An HD-MEA has no fixed layout, because each recording routes its own electrodes.
The spike file therefore carries `electrode_ids` / `electrode_coords` (layout
units, largest extent scaled to 8 like the MCS/Axion layouts, y flipped so up
is up). Positions in µm are kept as `electrode_coords_um`. Plotters that look
coordinates up by channel ID take the recording's own table when the layout is
`FromFile`. *To verify*: MaxWell's y axis direction against MaxLab's display.

### Event-driven stimulation (MEA-Stim)
MEA-Stim's analysis core takes **patterns = lists of event times** plus a
per-node record of which nodes were stimulated. Light stimulation has no
stimulated node and no artifact, so:
* `src/meanap/stim/events.py` — `StimEvents` (times + condition label per
  event), readers: MaxWell TTL (`bits`), and a generic CSV
  (`time_s[,condition]`) for any platform; helpers to split conditions
  (by TTL value, alternation, or interval).
* `stimDetectionMethod = "events"`: `stim_info` for every node with no stim
  times (nothing is blanked or skipped), `stim_patterns` = event times per
  condition. `stim_activity_analysis`, PSTHs, shuffle test, reservoir matrices
  and figures run unchanged. Rows gain the unit ID for sorted runs.

### Stimulus-triggered network analysis
Full-field light drives many units at once, so a network built over the whole
recording mixes shared stimulus drive with interactions. New
`src/meanap/stim/evoked_network.py`:
* **Evoked vs baseline networks** — cut every train to the post-event windows
  `[a, b]` (evoked) and to pre-event windows of the same length (baseline),
  concatenate the windows, then run the existing STTC + probabilistic
  thresholding + network metrics on each. The output is per-condition
  adjacency matrices and metrics for evoked, baseline and evoked − baseline.
* **Noise-correlation network** — per condition, Pearson correlation of
  trial-by-trial spike counts after subtracting each unit's mean response,
  which removes shared stimulus drive. Significance comes from a trial shuffle
  done independently per unit.

### Verification
* Synthetic fixtures (small, fast): a SpyKING CIRCUS-shaped HDF5 set, a phy
  folder, and a MaxWell-shaped raw metadata file with TTL bits, using known
  trains in which a subset of units has an injected light response. Tests check
  exact round-trip of trains, positions and events, plus detection of the
  injected responders and nothing else.
* Real data: step 1 import gives exactly the sorter's spikes (full length);
  steps 2–4 compared against the MATLAB run (306 nodes, FRmean 23.69 Hz,
  density 0.0603 at 25 ms; differences expected from the extra 0.68 s and from
  thresholding RNG).

## Status (2026-10-20)
| Phase | What | State |
|---|---|---|
| A | readers + MaxWell metadata + `import` step 1 + FromFile layout | **done** |
| B | event-driven MEA-Stim (TTL/CSV events → patterns), unit-aware rows | **done** |
| C | evoked/baseline STTC networks + noise correlations | **done** |
| D | GUI: import source, sorted folder, event + network options | **done** |
| E | user docs: `docs/python/sorted-import.md` (+ links from index, spike-sorting, gui-guide, matlab-vs-python) | **done** |

Code: `pipeline/maxwell.py`, `pipeline/sorted_import.py`, `pipeline/import_step.py`,
`channel_layout.recording_layout` (FromFile), `stim/events.py`,
`stim/evoked_network.py`, the event branch of `pipeline/stim_step.py`. Params:
`spike_source="import"`, `sorted_data_*`, `stim_detection_method` ∈
{`maxwellTTL`, `eventsCSV`}, `stim_event_*`, `stim_network_*`. Versions: MEA-NAP
1.12.0, MEA-Stim 0.5.0.

Tests: `python/test_sorted_import.py` (12, synthetic MaxWell + SpyKING CIRCUS +
phy fixture in `sorted_import_fixture.py`, incl. end-to-end steps 1–4 + stim),
`python/test_evoked_network.py` (7), `python/test_gui_sorted_import_params.py`
(GUI round trip of every new field).

### Verified on the real recording
* Import = the sorter's spikes exactly (306 units, 919 154 spikes; identical to
  the collaborator's export up to its 126 s cut). TTL markers identical to theirs.
* Unit positions: peak electrode via the routed-row order. Checked
  independently against MaxLab's own online-detected spikes: 28 % coincide
  (±0.5 ms) with a unit on the *same* electrode vs 1 % with electrodes
  shuffled.
* Step 2 on identical input (first 126 s, burst min spikes 10 as the
  collaborator set): FR exact to 5e-14 on every unit. Single-unit burst
  metrics are close but not exact: MATLAB ran with `fs = 1000`, so its burst
  detection bins spikes at 1 ms (these units have ISIs down to 0.55 ms);
  emulating that binning closes most of the gap.
* Steps 3–4: every recording-level metric within RNG/duration noise of MATLAB
  (density 0.0597 vs 0.0603, PL 0.907 vs 0.918, SWw 0.685 vs 0.683).

### Findings to raise with the collaborator
* **SpyKING CIRCUS ran with a probe geometry that is not this array's.**
  Template supports span a median 1.2 mm (pitch 17.5 µm); under any plausible
  electrode ordering they look like a random draw. Peak electrodes are still
  right (above), but SC's neighbourhood-based steps (whitening, template
  fitting, merging) worked on wrong neighbours. Ask for the `.params` and
  `.prb` used.
* No unit responds to the flashes beyond chance (see top).
* Which TTL marker is ON is not in the file; conditions are labelled by
  alternation (first marker at 1.51 s, then 0.58 s to the next, then 2.0/2.5 s).

### Not done / next
* Stimulus networks run for event-driven methods only; electrical stimulation
  (stim electrodes, blanking) not wired yet.
* MATLAB side: no import path; MATLAB still needs the collaborator's
  `_spikes.mat` workaround.
* Reading MaxWell **voltage** needs MaxWell's HDF5 compression plugin (not
  installed); only metadata/TTLs are read, which is all an import needs.
* Newer MaxWell file layout (`recordings/rec0000/well000`): metadata reader
  written but unverified on a real file; its TTLs are not read.
* `channel_layout` list in the GUI still offers `Mea256`/`Custom`, which the
  Python pipeline does not support (pre-existing).
* The stim response metrics' baseline-AUC windows are capped to fit between
  events for event runs (MATLAB's 30 assume electrical-stim timescales).
