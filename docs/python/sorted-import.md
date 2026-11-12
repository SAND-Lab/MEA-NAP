# Importing spike-sorted data

If your recordings have already been spike sorted (by SpyKING CIRCUS,
Kilosort, or anything else SpikeInterface can read), MEA-NAP can start from
those units. It does not detect spikes again. Each unit becomes a node, as with
[built-in sorting](spike-sorting.md), and steps 2–4 run on the units as they
would on electrodes.

The import was built for **high-density arrays** such as MaxWell MaxOne and
MaxTwo. Those arrays have no fixed electrode layout, because each recording
routes its own set of electrodes, so MEA-NAP takes each recording's electrode
positions from the data instead of from a layout file. On a MaxWell recording
the import also reads the **TTL events** from the raw file, so light
stimulation (or any other event-driven stimulus) can go straight into
MEA-Stim's stimulus-triggered analysis. See
[Light and other event-driven stimulation](#light-and-other-event-driven-stimulation).

:::{note}
The import is in the Python pipeline only. The MATLAB pipeline still needs the
units exported to a `_spikes.mat` file by hand.
:::

## What can be imported

| Format | What MEA-NAP reads | Sampling rate, duration and electrode positions |
|---|---|---|
| **SpyKING CIRCUS** | `<name>.result-merged.hdf5` (or `<name>.result.hdf5`) and the `.templates` file beside it | SpyKING CIRCUS does not store these, so a **MaxWell raw file is required** |
| **phy / Kilosort** (Kilosort 1–4, SpyKING CIRCUS's phy export, SpikeInterface's `export_to_phy`) | a folder holding `spike_times.npy`, `spike_clusters.npy` (or `spike_templates.npy`), `templates.npy`, `params.py`, `channel_map.npy`, `channel_positions.npy` and the curation `.tsv` files | from `params.py` and `channel_positions.npy`; a MaxWell raw file, if present, overrides them with the real electrode IDs and exact duration |
| **SpikeInterface** | a saved `SortingAnalyzer` (with a `templates` extension), or a saved sorting | from the analyzer; needs the `sorting` extra (see [Installation](installation.md#optional-spike-sorting)) |

MEA-NAP only reads the **metadata and TTL bits** from a MaxWell `.raw.h5`:
sampling rate, exact recording length, which electrodes were routed and where
they sit, and the TTL word. The voltage is never loaded, so it does not matter
that MaxWell compresses it with a plugin MEA-NAP does not have. Both the
classic MaxOne layout (`data_store/data0000`) and the newer
`recordings/rec0000/well000` layout are read for metadata. TTL events are read
from the classic layout only for now.

Each unit is placed on its **peak electrode**, the electrode where its
template is largest. Units are named `<electrode>-<rank>`, as with built-in
sorting: `19708-1` is the largest unit on electrode 19708. The sorter's own
cluster number is kept in the spike file.

## Laying out the data

Put the sorter output where MEA-NAP can find it by **recording name**. The
recording name is what you put in the batch spreadsheet's *Recording
filename* column: the raw file's name without `.raw.h5`. A SpyKING CIRCUS
folder for one MaxOne recording looks like this:

```text
sorted_data/
├── Trace_20240101_12_00_00_well1.raw.h5                     ← MaxWell raw (metadata + TTLs)
├── Trace_20240101_12_00_00_well1.raw.result-merged.hdf5     ← spikes
├── Trace_20240101_12_00_00_well1.raw.templates-merged.hdf5  ← templates (peak electrode)
└── … (.clusters, .overlap, .basis: not needed)
```

and the batch spreadsheet:

```text
Recording filename,DIV,Group
Trace_20240101_12_00_00_well1,42,Control
```

How each recording's output is found (the search includes subfolders):

* **SpyKING CIRCUS**: `<name>.<anything>.result-merged.hdf5`. Only the merged
  result is used when both are present, because that is the one you curated.
  If there is no merged result, `<name>.<anything>.result.hdf5` is used.
* **phy / Kilosort**: any folder holding `spike_times.npy` whose own name, or
  a parent folder's name, is the recording name or the recording name followed
  by `_`, `-` or `.` and a suffix, e.g.
  `<name>_kilosort4/`, `<name>/sorter_output/` or SpyKING CIRCUS's
  `<name>/<name>.GUI/`. A folder that matches a longer recording name in the
  same batch belongs to that recording, so `plate` does not take
  `plate_A1_kilosort4/`.
* **SpikeInterface**: a folder named for the recording that holds
  `spikeinterface_info.json`.
* **MaxWell raw file**: `<name>.raw.h5` or `<name>.h5`, in the raw data folder
  or in the sorted data folder.

The sorter output and the raw files can share one folder, as above, or sit in
different folders. If they are in different folders, set the **sorted data
folder** separately.

## Walkthrough: GUI

1. **Data tab**
   * **Raw data folder**: the folder with the MaxWell `.raw.h5` files. With
     phy/Kilosort output and no raw file, use the folder with the sorter
     output.
   * **Spreadsheet**: the batch file above.
   * **Channel layout**: `FromFile`. Every spatial plot (electrode heatmaps,
     network plots) then uses the electrodes each recording actually routed.
     Use `MCS60` or `Axion64` only if the sorted data came from those arrays.
2. **Spike detection tab**
   * **Spike source**: *Import units sorted elsewhere (SpyKING CIRCUS,
     Kilosort/phy…)*. The detector settings below it no longer apply.
   * Open the **Importing sorted units** section:

     | Field | What to put |
     |---|---|
     | **Sorted data folder** | Where the sorter output is. Leave empty if it is in the raw data folder. |
     | **Format** | *Automatic* tries SpyKING CIRCUS, then phy, then SpikeInterface for each recording. Pick one only if a folder holds more than one kind. |
     | **Leave out labels** | Curation labels whose units are dropped. The default is `noise`, which is the label phy and Kilosort give clusters that are not neurons. Add `mua` to keep only well-isolated units. Clear the field to keep every unit. SpyKING CIRCUS's own output has no labels, so every unit is kept there. |

3. **Connectivity tab**: choose the STTC lags as usual. Sorted units are more
   numerous than electrodes (several hundred is common), and steps 3–4
   scale with the number of node pairs, so start with **one lag**.
4. **Run tab**: run steps 1–4. Step 1 takes seconds, because it reads files
   and detects nothing. The run log has one line per recording, e.g.

   ```text
   [Trace_…_well1] importing spykingcircus output (Trace_….raw.result-merged.hdf5)…
   [Trace_…_well1] 306 unit(s) from spykingcircus, 306 kept as nodes on 305 electrode(s)
   ```

   With **Verbose** logging the log also gives the raw-file metadata:
   electrodes routed, sampling rate, duration.

If a recording is skipped, the log says why. The usual reasons are that no
sorter output matched the recording name, or that SpyKING CIRCUS output was
found without a raw file to give it a sampling rate.

## Walkthrough: Python

The same run as a script:

```python
from meanap.params import Params
from meanap.pipeline.runner import run_pipeline

params = Params(
    raw_data="sorted_data",                  # MaxWell .raw.h5 (+ the sorter output, here)
    spreadsheet_file_name="batch.csv",
    spreadsheet_range="2:100",
    output_data_folder="runs",
    output_data_folder_name="SortedRun",
    spike_source="import",
    sorted_data_folder="",                    # "" = look in raw_data
    sorted_data_format="auto",                # auto | spykingcircus | phy | spikeinterface
    sorted_drop_labels=["noise"],
    channel_layout="FromFile",
    func_con_lag_val=[25],
)
run_pipeline(params)
```

To use only the readers, for example to look at a sorting before a run:

```python
from meanap.pipeline.maxwell import read_maxwell_meta
from meanap.pipeline.sorted_import import (
    ElectrodeTable, find_sorted_output, read_sorted_output)

meta = read_maxwell_meta("sorted_data/<name>.raw.h5")
fmt, path = find_sorted_output("sorted_data", "<name>")
units = read_sorted_output(fmt, path, electrodes=ElectrodeTable.from_maxwell(meta),
                           fs=meta.fs, duration_s=meta.duration_s)
units.n_units, units.spike_trains[0][:5], units.sorter_unit_ids[:5], units.labels[:5]
```

## What the import writes

Step 1 writes the same `1_SpikeDetection/1A_SpikeDetectedData/<name>_spikes.npz`
that [built-in sorting](spike-sorting.md#reading-the-output) writes, so
nothing downstream needs to know where the units came from:

* one spike train per unit under the method `sorted`, in seconds, over the
  **full recording**. The length comes from the raw file's frame count, so the
  last spike does not cut it short;
* `channels`: each unit's peak electrode (MaxWell electrode IDs, not routing
  channels);
* `unit_*` arrays: the unit IDs, the sorter's cluster numbers, labels and
  coordinates (units sharing an electrode are spread on a small ring around
  it, as in a sorted run);
* `electrode_ids`, `electrode_coords` and `electrode_coords_um`: every routed
  electrode and its position, which the `FromFile` layout reads. In
  `electrode_coords` the largest extent is scaled to 8, as in the MCS and
  Axion layouts, with y pointing up. `electrode_coords_um` has the positions
  in µm, as the array reports them.

and a `<name>_spikes_params.txt` that records which file each recording was
imported from.

## Light and other event-driven stimulation

MEA-Stim was written for **electrical** stimulation. It finds stimulus times
from the artifact in the voltage, blanks them, and knows which electrode
stimulated. Light needs none of that: the stimulus times come from a
**marker** recorded alongside the data, no electrode is stimulated, and
nothing has to be blanked. Two new **Detection method** options handle this:

| Method | Where the event times come from |
|---|---|
| `maxwellTTL` | the TTL word stored in the MaxWell raw file (`bits`) |
| `eventsCSV` | `<name>_events.csv` (or `<name>_stim_events.csv` / `<name>.events.csv`): a `time_s` column in seconds from the start of the recording, plus an optional `condition` column. This works for any platform. |

Each **condition** is analysed as a stimulation pattern, so the PSTHs,
rasters, response metrics, shuffle test and latency heatmaps of
electrical-stimulation runs are produced per condition.

### Walkthrough

Switch the GUI to **MEA-Stim** mode (or launch with `meanap-gui --mode
meastim`; see [Modes](gui-guide.md#modes)). Set up the Data, Spike detection
and Connectivity tabs as above, then go to the **Stimulation** tab:

1. Tick **Enable** (*Run stimulation analysis*) and set **Detection
   method** to `maxwellTTL` or `eventsCSV`. The *Stimulus events (light, TTL,
   event log)* box replaces the voltage-detection box.
2. **Events folder**: where the events CSV, or the MaxWell raw file, is.
   Leave it empty to use the raw data folder.
3. **TTL rule** (MaxWell only): which TTL changes count as stimuli.
   * `auto` (default) picks the bit that changes **least often**. A projector
     typically toggles one bit every frame (60 Hz) as a frame sync, and the
     stimulus marker is the rare one. The run log (Verbose) lists every bit's
     changes and says which one it picked, so check it on your first run.
   * `rise:<bit>` / `fall:<bit>`: a given bit going high or low, with the bit
     given by its index (0–15), e.g. `fall:7` for the bit worth 128. The
     Verbose log lists the bits as `bit 7 (value 128)`.
   * `value:<word>`: every change *to* that TTL word, e.g. `value:0`.

   Markers closer together than **Merge events closer than** (under the
   box's *Advanced settings*, default 0.05 s) count as one event.
4. **Conditions**:
   * *All events one condition*: every event is a repeat of the same stimulus.
   * *Alternate labels (e.g. ON, OFF)*: the events take the **Condition
     labels** in turn, e.g. `ON, OFF` for a full-field flash with a marker at
     each transition.

   A TTL marker does not say which transition is ON, so take this from the
   stimulus protocol. If the protocol is not to hand, label them `A, B`.
5. **Analysis window start / end**: the PSTH window around each event. The
   default (−30 ms to +30 ms) is set for electrical stimulation. For light,
   use something like **−0.5 s to 1.0 s**, and set **Post-stim ignore
   duration** (under *Advanced settings*) to 0, since there is no artifact
   to skip.

In Python, the same settings are:

```python
params = Params(
    ...,                                       # import settings as above
    stimulation_mode=True,
    stim_detection_method="maxwellTTL",        # or "eventsCSV"
    stim_events_folder="",                     # "" = raw data folder
    stim_event_ttl_rule="auto",
    stim_event_min_interval=0.05,
    stim_event_condition_mode="alternate",     # or "single"
    stim_event_condition_labels=["ON", "OFF"],
    stim_analysis_window=[-0.5, 1.0],
    post_stim_window_dur=0.0,
)
```

The stimulation analysis runs right after step 1, so a run that stops at
step 1 (`stop_analysis_step=1`) still produces it.

### Outputs

* `StimActivity_NodeLevel.csv` (output root): one row per unit and condition,
  with the MATLAB MEA-Stim columns (AUC, baseline-corrected AUC, peak rate and
  time, d′, z-score, latency) plus `condition` and `unit_id`.
* `2_NeuronalActivity/2A_IndividualNeuronalAnalysis/<group>/<name>/`:
  * `stim_events.csv`: the events actually used, with their condition and
    pattern number. Compare it with your stimulus log;
  * the MEA-Stim figures, one per condition (`pattern_1`, `pattern_2`, … in
    the order of the condition labels): `9_FR_before_after_stimulation`,
    `10_stimulation_raster_and_psth`, `12_shuffle_test_*`,
    `stimPattern_*_heatmap`, `spikeLatency_*_heatmap`, and per-unit PSTHs in
    `Individual_PSTH_and_Raster_Pattern_*`.
* `ExperimentMatFiles/<name>_stimFigures.npz`: what those figures are drawn
  from, so a `.meanap` bundle's viewer can redraw them (under *Stimulation*
  on the Recordings tab) without the raw recording.

Baseline windows for the response metrics are capped so that they fit between
one event and the one before it. MEA-Stim's default of 30 baseline windows
assumes events seconds apart and stimulus windows of milliseconds.

## Stimulus-triggered networks

A full-field flash drives many units at once. A network built over the whole
recording, as step 3 builds it, then counts units as connected simply because
they all respond to the light. Open **Stimulus-triggered networks** on the
Stimulation tab (on by default, `stim_network=True`) to separate the two:

* **Evoked vs baseline networks.** Per condition and STTC lag, every unit's
  train is cut to the window after each event (**Evoked window start / end**,
  default 0–0.5 s), and the STTC network is built from those windows. The
  same is done for equally long windows **before** each event (baseline). Comparing the two shows how the stimulus reshapes
  functional connectivity. Events whose evoked window would overlap the next
  event's baseline are left out, and the log says how many.
* **Post-stimulus network.** A third epoch, after the evoked window: by
  default as long as the evoked window and starting where it ends (evoked
  2–50 ms gives post 50–98 ms), so all three epochs are equally long; STTC
  depends on window length. Untick *Post-stimulus window: as long as the
  evoked one* to set it (`stim_network_post_window`, seconds after the event).
  It answers whether a network the stimulus sets up outlasts it. Events whose
  post window would reach the next event's baseline are left out of all three
  networks, so every epoch uses the same trials.
* **Figure 16, `16_StimNetworkGraph_<lag>mslag`**: the three networks drawn on
  the array, one row per stimulation pattern and one column per epoch
  (pre-stimulus, during, post-stimulus). Edges are the significant STTC edges;
  node size (degree) and edge width (STTC) are on scales shared by every
  panel, so they compare across epochs and patterns. The row's stimulating
  electrodes are starred; they are left out of the networks.
* **STTC** sets how a pair's STTC is computed from the windows
  (`stim_network_sttc`):
  * *Within each trial, averaged over trials* (default, `trial_mean`): STTC
    in each trial's window alone, averaged over the trials in which both
    units fired. A pair needs 5 such trials; with fewer its STTC is
    undefined, it is never an edge, and it is left out of means and
    split-half comparisons. STTC's correction for firing rate then holds
    trial by trial, so slow shared activity states (the culture busier on
    some trials than others) no longer pass for edges, and no coincidence
    spans two trials. Needs the trial-shuffle test.
  * *Over all trial windows joined end to end* (`pooled`, the only method
    before MEA-NAP 1.19.0): one STTC over the joined train. Shared slow
    states make these networks dense in every epoch (see the note below).

  `StimNetwork_RecordingLevel.csv` gives `sttc_mode`, `nPairs`,
  `nDefinedPairs` and `fracSigOfDefined` (significant edges / defined pairs),
  and Figure 16's panels give the edges out of the defined pairs.
* **Edge test** decides which edges are significant:
  * *Trial shuffle* (default): the surrogate pairs one unit's trial *i* with
    another unit's trial *j*. This keeps each unit's response to the stimulus
    and breaks only same-trial timing, so an edge survives only if the pair is
    coupled **beyond the shared stimulus drive** (the shift-predictor idea).
  * *Circular shift*: shifts each train within the joined windows, as step 3
    does. This measures total co-activity, stimulus-locked co-firing
    included.

  Set **Surrogates** (default 200) and **Alpha** (default 0.05). The p-value
  is the permutation p, (1 + #surrogates ≥ observed) / (1 + surrogates).
* **Noise correlations.** Per condition, the Pearson correlation of
  trial-by-trial spike counts in the evoked window, tested against a trial
  shuffle done independently for each unit. This is the classic measure of
  shared variability that the stimulus does not explain.

Outputs:

* `StimNetwork_RecordingLevel.csv`: one row per recording × condition ×
  epoch (`evoked`, `baseline`, `noise_corr`) × lag. It holds the step-4
  network metrics (density, degree, strength, clustering, path length,
  small-worldness, modularity, cartography, …), plus `meanSTTC`,
  `meanSTTCminusNull`, `nSigEdges`, the number of trials, and the
  noise-correlation summaries (`meanNoiseCorr`, `fracSigNoiseCorr`,
  `fracSigPositive`).
* `StimNetwork_NodeLevel.csv`: the same per unit.
* `ExperimentMatFiles/<name>_stimNetwork.npz`: per condition, the evoked and
  baseline STTC matrices, their thresholded versions and null means
  (`<condition>__<epoch>__<lag>ms__sttc` / `__sttc_thr` / `__null_mean`), and
  the noise-correlation matrix and its p-values (`<condition>__noise_r` /
  `__noise_p`), with the node IDs, for your own analysis.
* `13_StimNetwork_<condition>_<lag>mslag.png` in the recording's figure
  folder: the significant baseline and evoked STTC matrices, the raw
  evoked − baseline STTC difference, and the noise-correlation matrix.

:::{dropdown} How do I know the edge test is calibrated?
On data with no stimulus coupling, about `alpha` of all pairs should come out
significant in **both** epochs, and about `alpha` of noise correlations.
The synthetic test fixture (`python/sorted_import_fixture.py`), in which
known units respond to ON or OFF events, checks the other direction: those
units, and only those, are detected. A clear rise in the evoked epoch over baseline is the
signal to look for. A baseline well above `alpha` means something other than
the stimulus is driving the units together.
:::

### Electrical stimulation

The same analysis runs on electrical stimulation detected from the raw
voltage (`longblank` and the other detection methods). Each stimulation
pattern is one condition, named by its electrodes (see
[Stimulation conditions](#stimulation-conditions)). Two things differ from
event-driven stimulation:

* **The evoked window starts after the artifact.** Cleaning removes every
  spike from the blanked period plus the post-stimulus ignore window
  (`post_stim_window_dur`), so a window starting at 0 would count that
  stretch as silence. The start moves to the end of the artifact (about
  2 ms on MCS60 data with `longblank`), and the log says so. For a sequence
  of pulses, it moves to the end of the *last* pulse's artifact. The baseline
  window keeps the same length.
* **Spike detection drops the artifact.** The amplifier coming out of its
  blank steps the voltage, and the bandpass filter turns the step into
  something spike-shaped: on the MCS60 test data every electrode gets one
  detection 1.0–1.5 ms after every stimulus, with every method. With the
  stimulation mode on, step 1 finds the stimuli and drops detections in the
  same windows cleaning removes (on a stimulating electrode, its own longer
  blank), so they stay out of the step-1 waveform checks and steps 2–4 too.
  *Spike detection drops detections in the stimulation blank*
  (`stim_drop_artifact_spikes`, on by default) on the Stimulation tab turns
  this off. Event-driven stimulation is left alone.
* **Stimulating electrodes are left out.** Cleaning empties their spike
  trains, so they would sit in the networks as silent nodes. They are NaN in
  the saved matrices and flagged `stim_electrode = True` in the node-level
  CSVs.

The detected stimulus times are written to `stim_events.csv` in the
recording's figure folder.

### Stimulation conditions

A condition is one kind of stimulus, and the analyses and group figures
compare conditions. How electrical stimulation is split into conditions:

* **By electrode (default).** As in MATLAB: electrodes whose pulse times
  agree within the pattern threshold are one pattern. This suits sets of
  electrodes stimulated together, alternating between sets or not.
* **By sequence** (**Group pulses into sequences** under Detection,
  `stim_group_sequences=True`). Needed for **temporal patterns**, such as a
  left-to-right sweep alternating with a right-to-left one. Grouped by
  electrode, a sweep with 10 ms between pulses becomes one pattern per
  electrode, and each of those mixes both directions. Grouped by sequence,
  pulses on any electrodes that follow each other within **Sequence gap**
  (`stim_sequence_gap`, default 50 ms) are one stimulus. Stimuli with the
  same electrodes in the same order, and the same delays to within 1 ms, are
  one condition. The gap must be longer than the delays within a sequence and
  shorter than the time between stimuli. A sequence seen fewer than 3 times
  (usually a pulse the detection missed) is left out, and the log says so.
  The patterns then drive every MEA-Stim output, including
  `StimActivity_NodeLevel.csv` and the PSTH figures. MATLAB has no
  counterpart.

Conditions are **named by their electrodes**: `12+13` for electrodes pulsed
together, `12>13>14` for a sequence, with the delays added when one order
was run at several speeds (`12>13>14 (5/10 ms)`). Recordings that stimulate
the same electrodes therefore share condition names, and the group figures
line them up with no labelling. The response metrics' first window still
starts at the first pulse, so a sequence's later pulses fall inside it.

To give conditions meaningful names, or to match **different** electrodes
across recordings (each culture's hub, say), add a `StimConditions` column
to the spreadsheet. It goes after the Genotype column (after Ground, if you
use one), and is found by its header:

| StimConditions | Meaning |
|---|---|
| `hub` | The recording's one condition is called `hub` |
| `A=12+13; B=45+46` | Two sets of electrodes pulsed together |
| `LtoR=12>13>14; RtoL=14>13>12` | Two sequences, told apart by their order |

Unlisted conditions keep their electrode names. A label for electrodes that
were not stimulated is logged, and a single label on a recording with
several conditions stops the run with a message saying which conditions to
name. `stim_events.csv` beside the figures lists every stimulus with its
condition, electrodes and last-pulse delay.

### Is the response the same on every trial?

**Trial-by-trial consistency and drift** (on by default,
`stim_trial_consistency=True`) asks whether the response changes over the
recording, by adaptation, potentiation or electrode drift. Per condition:

* **Per node:** the evoked − baseline spike count on every trial, and its
  Spearman ρ with trial number.
* **Population:** the same count summed over nodes, and its trend.
* **Latency:** each node's first spike after the window start, as the median
  and interquartile range over nodes on every trial.
* **Response pattern:** the correlation, over nodes, of every pair of trials'
  evoked counts. If the pattern drifts, trials close together are more alike
  than trials far apart. The slope of similarity against trial separation
  (over the first half of the separations) is compared with 1000 random trial
  orders. The same is done for the baseline window as a control: drift there
  is the recording changing, not the response.

Output: `14_StimConsistency_<condition>.png`,
`StimConsistency_RecordingLevel.csv` (`popResponseRho`/`P`,
`fracNodesDrifting`, `similarityLagSlope`/`P`,
`baselineSimilarityLagSlope`/`P`, `latencyRho`/`P`, …) and
`StimConsistency_NodeLevel.csv` (`meanResponse`, `driftRho`, `driftP`).
The per-trial count matrices are in the `.npz` (`<condition>__trial_evoked`,
`__trial_baseline`).

### Split-half networks

A network is only worth interpreting if a different set of trials gives the
same one. **Split-half networks** (on by default, `stim_split_half=True`)
build the evoked and baseline networks from half the trials, split two ways:

* **Odd vs even trials.** Both halves span the whole recording, so their
  agreement measures **reliability**.
* **First vs second half.** Agreement clearly lower than odd vs even means
  the network **changed** over the recording, not just that it is noisy.

Agreement is the correlation of edge weights between the two halves, for raw
STTC and for STTC above the trial-shuffle null. Edges are not independent
(each node is in n − 1 of them), so the p-value is a **Mantel test**: the node
labels of one half are permuted 1000 times. Only nodes active in both halves
are compared, since a silent node's zero edges would agree with each other
and inflate r. The overlap of significant edges is reported as a Jaccard
index next to its chance level, and noise correlations get the same split.

Output: `15_StimNetworkSplitHalf_<condition>_<lag>mslag.png`, with the two
halves' matrices drawn above and below the diagonal of one image and
scatter plots of edge weights, and `StimNetworkSplitHalf_RecordingLevel.csv`
(`r_sttc`, `mantel_p_sttc`, `r_excess`, `mantel_p_excess`, `jaccardSigEdges`,
`jaccardChance`, `r_noise_corr`, …). The half-trial matrices are in the
`.npz` (`<condition>__<epoch>__<lag>ms__<split>_A__sttc` and `_B`).

### Group comparisons by condition

With **Group comparisons by condition** on (default, `stim_group_plots=True`),
the stimulus networks get step 4B's half violins: one panel per group with
DIV on the x-axis, or one panel per DIV with group on the x-axis, and one
folder per lag. Each cell then has one violin per stimulation condition. Every
point is one recording × condition. They are written to
`StimNetwork_GroupComparisons/`:

* `1_ChangeByGroup`, `2_ChangeByAge`: every step-4 network metric (plus mean
  STTC, mean STTC above the null and the number of significant edges) as
  **evoked − baseline**, one violin per condition. The difference is taken
  within each recording, which keeps the pairing that separate baseline and
  evoked violins would hide.
* `3_EpochsByGroup/<condition>`, `4_EpochsByAge/<condition>`: the raw
  metric, **baseline and evoked** side by side. Use it to see whether a
  difference in the change comes from the evoked network or from a baseline
  that already differs between groups.
* `5_ResponseByGroup`, `6_ResponseByAge`: summaries with no epoch, one violin
  per condition. Split-half agreement (per lag), mean and significant noise
  correlations, the population response and its trend over trials, the
  fraction of drifting nodes, and first-spike latency.

Files are numbered as in step 4B. Conditions are matched across recordings
by name, so label them in the spreadsheet when different electrodes play the
same role.

:::{dropdown} Why are my pooled networks almost fully connected, in baseline too?
In a culture whose activity comes in slow waves or network bursts, the
biggest difference between trials is whether the culture is active at
that moment. The trial shuffle breaks that shared state, so every pair that
fires together during active periods passes as an edge, before the stimulus
as much as after it. Noise correlations come out high for the same reason.
Panel B of the consistency figure shows this: evoked and baseline counts rise
and fall together over trials. On the MCS60 test recordings (60 stimuli 5 s
apart), half or more of all pairs were significant in both epochs, with a
0.5 s window and with a 50 ms one. A shorter window aimed at the direct
response (first-spike latency is in the consistency figure) brings the
networks closer to the stimulus, but it does not remove the shared state.
Averaging STTC within trials (the default) does: on the same recordings
baseline and post-stimulus networks keep 0–17 % of defined pairs, and the
evoked ones 48–95 % (lags 10–25 ms).
:::

## Limitations

* MATLAB pipeline: no import path yet.
* MaxWell **voltage** is not read, so the spike viewer and the waveform
  figures of built-in sorting are not available for imported units.
* The newer MaxWell file layout: metadata only; TTL events are not read yet.
  Use `eventsCSV` for those files.
* SpyKING CIRCUS output can't be imported without its raw file, since
  neither the sampling rate nor the electrode positions are in its output.
  For non-MaxWell recordings, export to phy from SpyKING CIRCUS
  (`spyking-circus <file> -m converting`) and import the phy folder.
* Check that the sorter was given the array's real geometry. Each unit's
  position comes from its own template, so the units are placed correctly
  either way. But a sorter that worked with the wrong neighbouring
  electrodes will have whitened, fitted and merged templates against the
  wrong electrodes.
