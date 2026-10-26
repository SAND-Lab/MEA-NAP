# Plot diff: aligning Python figures with MATLAB

Instructions for an agent that will change the Python port (`src/meanap/`) so its saved figures use the same filenames, titles and axis labels as the MATLAB pipeline (`matlab/`). The source of truth for both sides is [plot-inventory.md](plot-inventory.md). The inventory's line numbers drift, so find each call by searching for the filename or label text, and read the MATLAB source before you change anything.

## Ground rules

1. **MATLAB is the reference.** Where the inventory shows a difference, change Python to match MATLAB. Do not change MATLAB.
2. **Leave Python-only figures alone.** These have no MATLAB equivalent: sorting checks (`1_UnitsPerElectrode`, `2_UnitTemplates`, `3_UnitQuality`), `13_StimNetwork_*`, `12_MeanImageAndNetwork`, `cellTypeSubnetworks/*`, `CellTracking/*`, all of Step 5 (`5_StatsAndML/5A1…5G8`), `NodeCartographyProportionsBy*`, and the `fr_diff` and GUI saves.
3. **Skip MATLAB-only figures.** Do not port figures Python lacks (`11_stimulation_amplitude_raster_and_psth`, `stimPattern_activity_per_trial`, `stimPattern_decoding`, `8_adjM…NullModels`, `NodeCartographyProportions`, `nNMF`, `8_CombinedPlotsByDiv`). That is a separate task.
4. **Do not fix the shared known bugs.** The `2_SpikeFrequencies` 'Hz' label is wrong in both languages, and `ZandPC_scatter_with_kmeans_boundaries_` is overwritten for every lag. The task is parity, so leave both as they are.
5. **Check for downstream readers before renaming a file or folder.** Grep `src/`, `tests/`, `docs/` and the GUI for the old name. Anything that reads figures back, lists output folders, or asserts on a filename or label string must be updated in the same change.
6. **Check label dictionaries for other users.** `EPHYS_REC_METRICS`, `EPHYS_NODE_METRICS`, `NETMET_REC_METRICS` and `NETMET_NODE_METRICS` are also used by Step 5 and CAT-NAP plots. If you change a label there, confirm those figures still read sensibly. If a Python-only figure needs the old wording, add a separate display dict for it rather than keeping two meanings in one dict.
7. **Recording-name convention.** MATLAB's `FNt` is the recording name with `_` removed. Wherever the MATLAB title uses `FNt`, build the Python title from the name with `_` removed. File paths keep the real name.
8. **Do not commit** unless asked. Finish by updating the Python half of `plot-inventory.md` to match what you changed, then run the test suite and report failures verbatim.

## Priority 1: filenames and folders

### 1.1 Step 2A heatmap and raster numbering
MATLAB numbers `3_Raster` and then the heatmaps 4–8. Python numbers the heatmaps 3–7, so `3_` is used twice.

| Python now | Rename to (MATLAB) |
|---|---|
| `3_BurstRate_heatmap.png` | `4_BurstRate_heatmap.png` |
| `4_BurstDur_heatmap.png` | `5_BurstDur_heatmap.png` |
| `5_FractSpikesInBursts_heatmap.png` | `6_FractSpikesInBursts_heatmap.png` |
| `6_ISIwithinBurst_heatmap.png` | `7_ISIwithinBurst_heatmap.png` |
| `7_ISIoutsideBurst_heatmap.png` | `8_ISIoutsideBurst_heatmap.png` |

`1_FiringRateByElectrode`, `2_Heatmap`, `3_Raster` and `8_BurstDetectionInfo` already match. MATLAB also has `8_ISIoutsideBurst_heatmap` and `8_BurstDetectionInfo` sharing the prefix `8`. Reproduce that as is.

### 1.2 Step 2B filenames (`plot_half_violin_by_x` callers in `plotting_step2.py`)
MATLAB names files `<n>_<label>_<suffix>`, where `n` is the 1-based metric index and `label` is the display label. Python uses `<key>_<suffix>`.

| Section | Python now | MATLAB pattern |
|---|---|---|
| `3_RecordingsByGroup/HalfViolinPlots/` | `<key>_byGroup` | `<n>_<eMetl>_byGroup` |
| `4_RecordingsByAge/HalfViolinPlots/` | `<key>_byDIV` | `<n>_<eMetl>_byAge` |
| `1_NodeByGroup/` | `<key>_byGroup_node` | `<n>_<cMetl>_byGroup` |
| `2_NodeByAge/` | `<key>_byDIV_node` | `<n>_<cMetl>` (no suffix, as in `PlotEphysStats.m`) |

- `n` runs 1–15 for recording metrics and 1–8 for node metrics, in the order of the lists in the inventory.
- `eMetl` and `cMetl` are the MATLAB labels, which are also the y labels. See section 2.1.
- Confirm in `PlotEphysStats.m` whether any characters in the label are altered when it becomes a filename. If so, apply the same rule.
- The shared `plot_half_violin_by_x` helper serves 2B and 4B. Add the `n`-prefix, `_byAge` suffix and label-as-stem logic as parameters, not a fork.

### 1.3 Step 4B filenames and folders (`plotting_step4.py`)

| Item | Python now | MATLAB |
|---|---|---|
| Lag folder | `Lag<n>ms` | `<lag>mslag` |
| Recording-level by group | `<key>_byGroup.png` | `<n>_<label>_byGroup` |
| Recording-level by age | `<key>_byDIV.png` | `<n>_<label>_byAge` |
| Node by group | `<key>_byGroup_node.png` | `<n>_<label>_byGroup` |
| Node by age | `<key>_byDIV_node.png` | `<n>_<label>_byAge` |
| `5_GraphMetricsByLag` | `<key>.png` | `<n>_<label>` |

- Keep the `Bin<n>ms` folder for CAT-NAP correlation bins. MATLAB has no equivalent.
- `n` is the position in the label lists in section 2.2: 1–29 for network metrics in script mode, 1–7 for node metrics. The extra GUI-mode labels follow `netMetToCal`. Read that logic in MATLAB to number them.
- Apply the `PlotNetMet.m` filename rules to the label:
  - Strip backslashes, so `small worldness \sigma` becomes `small worldness sigma`.
  - Turn `>` into `greater than` and `<` into `less than`.
  - In the by-age sections, turn `/` into `div`.
- Keep `NodeCartography<lag>mslag.png`, `7_DensityLandscape/…`, and the Python-only `NodeCartographyProportionsBy*` as they are.

## Priority 2: axis labels and titles

### 2.1 Step 2B label lists
Change these in `EPHYS_REC_METRICS` and `EPHYS_NODE_METRICS`. All other recording-level labels already match.

| Key | Python now | MATLAB |
|---|---|---|
| channelAveBurstRate | 'Single-electrode burst rate (per min)' | 'Single-electrode burst rate (per minute)' |
| channelAveBurstDur | 'Single-electrode avg burst dur (ms)' | 'Single-electrode average burst duration (ms)' |
| channelAveISIwithinBurst | 'Single-electrode avg ISI within burst (ms)' | 'Single-electrode average ISI within burst (ms)' |
| channelAveISIoutsideBurst | 'Single-electrode avg ISI outside burst (ms)' | 'Single-electrode average ISI outside burst (ms)' |
| FR | 'mean_firing_rate_node' | 'mean firing rate node' |
| FRactive | 'mean_firing_rate_active_node' | 'mean firing rate active node' |

Also check the by-age panel title. MATLAB 2B uses 'Age\<DIV>' and Python uses 'Age \<div>'. Read `PlotEphysStats.m` to see whether the DIV value carries its own leading space, and match the rendered text. In 4B both use 'Age \<DIV>'.

### 2.2 Step 4B label lists
Replace the display labels with the MATLAB ones, keeping Python keys unchanged. Recording level (`NETMET_REC_METRICS`), in MATLAB order:

| n | Key | MATLAB label |
|---|---|---|
| 1 | aN | network size |
| 2 | Dens | density |
| 3 | CC | clustering coefficient |
| 4 | nMod | number of modules |
| 5 | Q | modularity score |
| 6 | PL | mean path length |
| 7 | Eglob | global efficiency |
| 8 | SW | small worldness \sigma |
| 9 | SWw | small worldness \omega |
| 10 | effRank | Effective rank |
| 11 | num_nnmf_components | Num NMF components |
| 12 | nComponentsRelNS | nNMF div network size |
| 13 | NDmean | Node degree mean |
| 14 | NDtop25 | Top 25% node degree |
| 15 | sigEdgesMean | Significant edge weight mean |
| 16 | sigEdgesTop10 | Top 10% edge weight mean |
| 17 | NSmean | Node strength mean |
| 18 | ElocMean | Local efficiency mean |
| 19 | PCmean | Participant coefficient (PC) mean |
| 20 | PCmeanTop10 | Top 10% PC |
| 21 | PCmeanBottom10 | Bottom 10% PC |
| 22 | percentZscoreGreaterThanZero | Percentage within-module z-score > 0 |
| 23 | percentZscoreLessThanZero | Percentage within-module z-score \< 0 |
| 24 | NCpn1 | NC1PeripheralNodes |
| 25 | NCpn2 | NC2NonhubConnectors |
| 26 | NCpn3 | NC3NonhubKinless |
| 27 | NCpn4 | NC4ProvincialHubs |
| 28 | NCpn5 | NC5ConnectorHubs |
| 29 | NCpn6 | NC6KinlessHubs |
| GUI | aveControlMean | Mean average controllability |
| GUI | modalControlMean | Mean modal controllability |

Node level (`NETMET_NODE_METRICS`):

| n | Key | MATLAB label |
|---|---|---|
| 1 | ND | node degree |
| 2 | MEW | edge weight |
| 3 | NS | node strength |
| 4 | Z | within-module degree z-score |
| 5 | Eloc | local efficiency |
| 6 | PC | participation coefficient |
| 7 | BC | betweenness centrality |
| GUI | aveControl | Average Controllability |
| GUI | modalControl | Modal Controllability |

Notes:
- MATLAB uses `\sigma` and `\omega` as TeX markup. In matplotlib, render these as `$\sigma$` and `$\omega$` so the visible text matches. In filenames they are stripped, as in 1.3.
- MATLAB has no top-5% betweenness entry in script mode. Leave the Python metrics with no MATLAB equivalent (such as `BCmean`) under their current labels and give them an `n` after the MATLAB ones.
- The labels 'Participant coefficient (PC) mean' (sic) and 'Percentage within-module z-score \< 0' come from MATLAB. Reproduce them as written.

### 2.3 Step 1 detection checks (`pipeline/plotting.py`)

| File | Item | Python now | MATLAB |
|---|---|---|---|
| `2_SpikeFrequencies` | title | `rec_name` | `FNt` (no underscores) |
| `1_ExampleTraces` | layout title | suptitle `rec_name` | `FNt` (no underscores) |
| `1_ExampleTraces` | tile titles | one line, 'Electrode \<ch> \| \<start> - \<end> s' | two lines, 'Electrode \<ch>' then '\<start> - \<end> s' |
| `3_Waveforms` | layout title | '\<rec>\nUnique spikes by method from electrode \<ch>' | `{FNt,' ',"Unique spikes by method from electrode <ch>"}` (a blank line between) |
| `3_Waveforms` | y label | 'Voltage ($\mu$V)' | 'Voltage [\muV]', so use 'Voltage [$\mu$V]' |

### 2.4 Step 2A (`pipeline/plotting_step2.py`)

| File | Item | Python now | MATLAB |
|---|---|---|---|
| `1_FiringRateByElectrode` | title | 'Firing Rate by Electrode' | `FNt` |
| `1_FiringRateByElectrode` | x label | none | 'age\<DIV>' |
| `1_FiringRateByElectrode` | y label | 'Mean firing rate per electrode (Hz)' | 'mean firing rate per electrode (Hz)' |
| `2_Heatmap` | titles | 'Firing Rate\nscaled to recording' / '…\nscaled to entire dataset' | '\<FNt> scaled to recording' / '\<FNt> scaled to entire dataset' |
| `2_Heatmap` | colorbar | 'Mean FR (Hz)' | 'mean firing rate (Hz)' |
| `3_Raster` | titles | 'raster scaled to recording' / 'raster scaled to entire data batch' | '\<FNt> raster scaled to recording' / '\<FNt> raster scaled to entire data batch' |
| `3_Raster` | x label | 'Time (s)' | 'Time (min)' |
| `4_BurstRate_heatmap` | titles / colorbar | 'Burst Rate\n…' / 'Burst Rate (bursts/min)' | '\<FNt> scaled to recording' (or '… entire dataset') / 'Mean burst rate (per minute)' |
| `5_BurstDur_heatmap` | titles / colorbar | 'Burst Duration\n…' / 'Duration (ms)' | same title form / 'Mean burst duration (ms)' |
| `6_FractSpikesInBursts_heatmap` | titles / colorbar | 'Fraction Spikes in Bursts\n…' / 'Fraction' | same title form / 'Fraction spikes in bursts' |
| `7_ISIwithinBurst_heatmap` | titles / colorbar | 'ISI Within Burst\n…' / 'ISI (ms)' | same title form / 'ISI within bursts (ms)' |
| `8_ISIoutsideBurst_heatmap` | titles / colorbar | 'ISI Outside Burst\n…' / 'ISI (ms)' | same title form / 'ISI outside bursts (ms)' |
| `8_BurstDetectionInfo` | titles | 'Raster (All spikes)'; 'Raster (Only network bursts)'; 'ISI Distribution' | 'Downsampled raster'; 'Raster with only bursts'; 'ISI Distribution: Within vs. Outside Bursts' |
| `8_BurstDetectionInfo` | y labels | 'Electrode' | 'Electrodes' |

Notes:
- **Raster x label.** `3_Raster` is plotted in seconds in Python and minutes in MATLAB. Convert the x data to minutes (divide by 60) and check that any tick or extent code still lines up. Do not relabel seconds as minutes.
- **Burst detection panels.** MATLAB also has 'Network mean activity' (x 'Time (s)', y 'z-scored mean') and 'Number of bursts as function of threshold' (x 'Burst detection z-score threshold', y 'Number of network bursts'). Python lacks both. Adding panels is out of scope, so only fix the labels on the panels Python has.
- **Heatmap titles.** The text before the line break goes away. The MATLAB title is the recording name plus the scaling phrase. The metric is already named by the colorbar.

### 2.5 Step 3 (`plotting_step3.py`)
Titles 'discarded (rep\<n>)' ×5 become 'discarded edges (rep\<n>)'. The x label 'Number of Repeats' and the other labels already match.

### 2.6 Step 4A (`plotting_step4.py`)

| Item | Python now | MATLAB |
|---|---|---|
| Network plot title (`2_`–`5_`, `10_`, `11_`, `6_circular`, `9_circular`) | '\<rec>  \<lag> ms lag' (two spaces) | '\<FNt> \<lag> ms lag' (one space, no underscores) |
| `*_scaled_*` network plot title | the same + ' (scaled to data batch)' | the same standard title, nothing appended |
| `1_adjM…ConnectivityStats` suptitle | '\<rec> \<lag> ms lag' | '\<FNt> \<lag> ms lag' |
| `7_adjM…GraphMetricsByNode` suptitle | '\<FNt> \<lag> ms lag' | already matches |
| `9_adjM…NodeCartography` title | '\<rec> \<lag> ms lag  —  node cartography' | suptitle '\<FNt> \<lag> ms lag'; the plot panel is titled 'node cartography' |
| Node-size text | 'node degree' / 'node strength' | 'Node degree:' / 'Node strength:' |
| `<n>_combined_MEA_NetworkPlot[_<Metric name>]` titles | '\<rec>  \<lag> ms lag\nscaled to recording' / '…\nscaled to entire data batch' | none |

Notes:
- **Combined plots.** The MATLAB combined plots have no titles because `copyobj` drops them. Remove the titles on the Python combined plots.
- **Scaled plots.** Keep the file name's `scaled_` prefix. Only the title text changes.
- **Size annotations.** Fix the 'node degree' and 'node strength' strings on the colour-mapped network plots. The colorbar labels ('Betweenness centrality', 'Participation coefficient', 'Local efficiency', 'Average controllability', 'Modal controllability') already match.
- **Cartography panel.** Where a figure carries both a suptitle and a panel title, MATLAB uses both. Mirror that.

### 2.7 Stimulation (`stim/plotting.py`)
Names and labels for files 9, 10, 12 and the pattern heatmaps already match. Only check that the `<rec>` titles use `Info.FN{1}`-style text, meaning the raw name with underscores as MATLAB does. Do not apply the no-underscore rule here, because MATLAB uses `Info.FN{1}` and not `FNt`.

## Out of scope (differences you should leave alone)

- **Step 5 naming.** MATLAB uses `5_Stats/1_sig_table…`, `…allclassifiers…` and `…FeatureCorrelation`. Python uses the `5A1…5G8` stems under `5_StatsAndML/`. These are different figure sets, not renames.
- **CAT-NAP rasters.** `3_ActivityRaster` and `4_ActivityRaster_zscored` use 'Cell', which MATLAB suite2p mode writes as 'Unit'. CAT-NAP is a separate design, so leave it.
- **File formats.** MATLAB writes each figure in every format listed in `Params.figExt` (default `.png` and `.svg`). Python writes `.png`. Do not add `.svg` unless asked.

## Checklist for the agent

1. Rename files and folders (sections 1.1–1.3), then grep for the old names across the repo and update every reader and test.
2. Update the label dicts (2.1, 2.2) and check Step 5 and CAT-NAP figures still read well (ground rule 6).
3. Fix titles and axis labels (2.3–2.6).
4. Run the plotting tests and a small end-to-end Python run. Open a few of the produced figures and compare them with the MATLAB column in the inventory.
5. Update the Python half of [plot-inventory.md](plot-inventory.md), including the "Prefix clash" entry under Known issues, which no longer applies after 1.1.
6. Report what changed, anything you could not match, and any test you had to edit.
