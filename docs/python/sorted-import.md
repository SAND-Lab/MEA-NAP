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
data_for_tim/
├── Trace_20240920_15_34_23_6L_6weekSOHU_inf_OS_fullfield.raw.h5                     ← MaxWell raw (metadata + TTLs)
├── Trace_20240920_15_34_23_6L_6weekSOHU_inf_OS_fullfield.raw.result-merged.hdf5     ← spikes
├── Trace_20240920_15_34_23_6L_6weekSOHU_inf_OS_fullfield.raw.templates-merged.hdf5  ← templates (peak electrode)
└── … (.clusters, .overlap, .basis: not needed)
```

and the batch spreadsheet:

```text
Recording filename,DIV,Group
Trace_20240920_15_34_23_6L_6weekSOHU_inf_OS_fullfield,42,SOHU
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
   numerous than electrodes (306 on the example recording), and steps 3–4
   scale with the number of node pairs, so start with **one lag**.
4. **Run tab**: run steps 1–4. Step 1 takes seconds, because it reads files
   and detects nothing. The run log has one line per recording, e.g.

   ```text
   [Trace_…_fullfield] importing spykingcircus output (Trace_….raw.result-merged.hdf5)…
   [Trace_…_fullfield] 306 unit(s) from spykingcircus, 306 kept as nodes on 305 electrode(s)
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
    raw_data="data_for_tim",                  # MaxWell .raw.h5 (+ the sorter output, here)
    spreadsheet_file_name="batch.csv",
    spreadsheet_range="2:100",
    output_data_folder="runs",
    output_data_folder_name="RetinalOrganoid",
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

meta = read_maxwell_meta("data_for_tim/<name>.raw.h5")
fmt, path = find_sorted_output("data_for_tim", "<name>")
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
  default 0–0.5 s). The windows are joined end to end, and the STTC network is
  built on that. The same is done for equally long windows **before** each
  event (baseline). Comparing the two shows how the stimulus reshapes
  functional connectivity. Events whose evoked window would overlap the next
  event's baseline are left out, and the log says how many.
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
significant in **both** epochs. On the example recording below (306 units,
46 665 pairs), 4.9–5.3 % did at α = 0.05, and 5.0 % of noise correlations
were significant. A clear rise in the evoked epoch over baseline is the
signal to look for. A baseline well above `alpha` means something other than
the stimulus is driving the units together.
:::

Stimulus-triggered networks are built for event-driven methods only.
Electrical stimulation would also need the stimulating electrodes and blanked
periods taken out of the windows, and that is not wired up yet.

## Worked example: a retinal organoid on a MaxOne

The recording the import was developed on is a 6-week human retinal organoid
on a MaxWell MaxOne: 941 routed electrodes at 17.5 µm pitch, 20 kHz,
126.68 s, sorted with SpyKING CIRCUS into 306 units, with full-field light
flashes marked in the TTL bits. What a run gave:

* **Import**: identical to the collaborator's own export for MATLAB, unit for
  unit and spike for spike, except that the import keeps the last 0.68 s
  their export cut off. The peak electrodes were checked against MaxLab's
  online spike detection: 28 % of its spikes fall within ±0.5 ms of a spike
  from a unit on the same electrode, against 1 % with electrodes shuffled.
* **Steps 2–4 vs MATLAB on the same units**: firing rates identical to
  5 × 10⁻¹⁴. Network metrics agree within the thresholding's randomness
  (density 0.0597 vs 0.0603, path length 0.907 vs 0.918).
* **TTL**: bit 5 toggles at 60 Hz (projector frame sync). `auto` picks the
  rare marker, bit 7 falling (`fall:7`), 57 times, alternating 2.0 s and
  2.5 s apart. The run log reports the result as `57 event(s) … TTL auto → fall:7;
  condition(s) A (29), B (28)`, and 4 events too close to a neighbour are left
  out of the networks.
* **Light responses**: none beyond chance. No unit had |z| > 3, and evoked
  networks, baseline networks and noise correlations all sat at the 5 %
  false-positive level. For this recording that is the expected result: it
  shows that the analysis does not report responses that are not there. The
  synthetic test fixture (`python/sorted_import_fixture.py`), in which known
  units respond to ON or OFF events, checks the other direction: those units,
  and only those, are detected.

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
