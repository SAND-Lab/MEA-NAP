# Plot inventory

This page lists every figure that MEA-NAP saves to disk, for both the MATLAB pipeline (`matlab/`) and the Python package (`src/meanap/`). Each entry gives the saved filename (or filename pattern), the source line that saves it, and the figure's titles and axis labels. Use it to find which code made a figure in your output folder, or to check what a figure will be labelled before you run the pipeline.

**Notation**

- `<OUT>` is the output root folder.
- `<G>/<R>` is the group / recording.
- `<FNt>` is the recording name with `_` removed.
- `<lag>` is the STTC lag. In MATLAB this is `Params.FuncConLagval` (default 10/25/50).
- "std" in a title column means the standard title `"<FNt> <lag> ms lag"`, used on per-recording network figures.
- "—" means no title or label is set.
- Multi-panel figures are written as `panel: title / xlabel / ylabel`.

**Extensions**

- MATLAB writes each `pipelineSaveFig` figure once per entry in `Params.figExt` (default `.png` + `.svg`).
- Python writes `.png`. Step 5 uses `StatsSettings.fig_ext` (default `.png`).

**Folder shorthand**

- **2A** = `<OUT>/2_NeuronalActivity/2A_IndividualNeuronalAnalysis/<G>/<R>/`
- **2B** = `<OUT>/2_NeuronalActivity/2B_GroupComparisons/`
- **4A** = `<OUT>/4_NetworkActivity/4A_IndividualNetworkAnalysis/<G>/<R>/<lag>mslag/`
- **4B** = `<OUT>/4_NetworkActivity/4B_GroupComparisons/`

Source line numbers were correct when this page was written and will drift as the code changes.

## MATLAB (`matlab/`)

### Step 0/1: Layout, spike detection, stimulation detection
| Saved file | Source | Title | X label | Y label | Other |
|---|---|---|---|---|---|
| `<OUT>/channel_layout` | plotElectrodeLayout.m:83 | p1 'Provided electrode layout (channel index)'; p2 'Provided electrode layout (channel ID)' | 'X coordinates' | 'Y coordinates' | |
| `1_SpikeDetection/1B_SpikeDetectionChecks/<G>/<R>/2_SpikeFrequencies` | plotSpikeDetectionChecks.m:149 | `{FNt,' '}` | 'Time (minutes)' | 'Spiking frequency (Hz)' | legend: methods |
| `.../1B_SpikeDetectionChecks/<G>/<R>/1_ExampleTraces` | :240 | layout `{FNt,' '}`; tiles `{"Electrode <ch>", "<start> - <end> s"}` | — | 'Amplitude (\muV)' | legend 'Filtered voltage trace' + methods |
| `.../1B_SpikeDetectionChecks/<G>/<R>/3_Waveforms` | :320 | layout `{FNt,' ',"Unique spikes by method from electrode <ch>"}`; tiles `<method>` | — | 'Voltage [\muV]' | |
| `1_SpikeDetection/1C_StimDetectionChecks/<G>/<R>/1_StimsDetected` | stimAnalysis/plotStimDetectionChecks.m:10 | — | 'Time (s)' | (hidden; text 'Electrode ID', 'Channel Index') | |
| `.../1C_StimDetectionChecks/<G>/<R>/2_StimsHeatmap` | :17 | — | — | — | axes off |
| `.../1C_StimDetectionChecks/<G>/<R>/3_NoStimsElectrode_<id>` and `3_StimsElectrode_<id>` | :54 / :68 | p1 'Electrode \<name> (Channel \<idx>)' | p1 'Time'; p2 'Time (s)' | p1 'Filtered signal'; p2 'Stim Pulses Detected' | |
| `<OUT>/1_SpikeDetection/1C_prePostTTXcomparison<rec>_detected_w_<wavelet>.png` (no folder separator, which is a bug) | find_best_spike_result.m:389 | sgtitle 'Recording: \<rec>'; one panel 'Simultaneous spikes ratio: \<x>%' | 'Cost parameter' / 'Time(seconds)' / 'Number of spikes in time bin' / 'Spike min peak' | 'Spike counts' / 'Spike ratio' / 'Spikes' / 'Number of time bins' / 'Spike count' | PNG only |
| `<plot_folder>/<rec>_channel_<ch>.png` | WATERS-master/getTemplate.m:207 | 'Clusters: \<n>' | 'Feature 1'; 'Time bins' | 'Feature 2'; 'Voltage' | `Params.plot_folder` is never set, so this never runs |

### Step 2A: Per-recording neuronal activity (folder 2A)
| Saved file | Source | Title | X label | Y label | Colorbar / other |
|---|---|---|---|---|---|
| `1_FiringRateByElectrode` | firingRateElectrodeDistribution.m:56 | `{FNt,' '}` | 'age\<DIV>' | 'mean firing rate per electrode (Hz)'; suite2p: 'mean activity rate per unit (\<twopActivity>)' | |
| `2_Heatmap` | electrodeHeatMaps.m:238 | '\<FNt> scaled to recording' / '\<FNt> scaled to entire dataset' | — | — | 'mean firing rate (Hz)' |
| `3_Raster` | rasterPlot.m:139 | '\<FNt> raster scaled to recording' / '\<FNt> raster scaled to entire data batch' | 'Time (min)' | 'Electrode' (suite2p 'Unit') | 'Firing Rate (Hz)' (suite2p 'Activity') |
| `4_BurstRate_heatmap` | plotting/plotNodeHeatmap.m:229 | '\<FNt> scaled to recording' / '\<FNt> scaled to entire dataset' | — | — | 'Mean burst rate (per minute)' |
| `5_BurstDur_heatmap` | same | same | — | — | 'Mean burst duration (ms)' |
| `6_FractSpikesInBursts_heatmap` | same | same | — | — | 'Fraction spikes in bursts' |
| `7_ISIwithinBurst_heatmap` | same | same | — | — | 'ISI within bursts (ms)' |
| `8_ISIoutsideBurst_heatmap` | same | same | — | — | 'ISI outside bursts (ms)' |
| `8_BurstDetectionInfo` | plotting/plotNetworkBursts.m:116 | 'Downsampled raster'; 'Raster with only bursts'; 'Network mean activity'; 'ISI Distribution: Within vs. Outside Bursts'; 'Number of bursts as function of threshold' | 'Time (s)' ×3; 'Inter-Spike Interval (s)'; 'Burst detection z-score threshold' | 'Electrodes' ×2; 'z-scored mean'; 'Probability'; 'Number of network bursts' | `close(F1)` at :124 is an undefined-variable bug |
| `unit_<cell>_2ptraces` | twoPhoton/plot2ptraces.m:98 | '\<fileName> cell \<idx>' | p3 'Time (s)' | 'Fluorescence'; 'Arbitrary units' ×2 | |
| `9_FR_before_after_stimulation[_pattern_<p>]` | stimAnalysis/plotPrePostStimFR.m:75 | `Info.FN{1}` | 'Pre-stim firing rate (spikes/s)' | 'Post-stim firing rate (spikes/s)' | |
| `10_stimulation_raster_and_psth[_pattern_<p>]` | stimAnalysis/plotMetricAlignedToStim.m:45 | top `Info.FN{1}` | bottom 'Time from stimulation (ms)' | 'Mean firing rate (spikes/s)'; 'Channel' | 'Firing rate (spikes/s)' |
| `11_stimulation_amplitude_raster_and_psth` | stimActivityAnalysis.m:154 | top `Info.FN{1}` | 'Time from stimulation (ms)' | 'Mean absolute spike amplitude'; 'Channel' | 'Mean absolute spike amplitude' |
| `spikeLatency_pattern_<p>_heatmap` | stimActivityAnalysis.m:190 | 'Pattern \<p>' | — | — | 'Median spike latency (ms)' |
| `stimPattern_<p>_heatmap` | :251 | 'Pattern \<p>' | — | — | 'Firing rate (spikes/s)' |
| `stimPattern_activity_per_trial` | :311 | 'Stim pattern \<id>' per tile | 'Electrodes and time bins' | 'Trials' | 'spikes/s' |
| `stimPattern_decoding` | :382 | — | 'Number of nodes used in classification' | 'Classification accuracy' | |
| `12_shuffle_test_null_dist_pattern_<p>` | stimAnalysis/plotStimShuffleResults.m:75 | 'Null trial proportion distribution – pattern \<p>  \|  \<FN>'; 'Observed vs null – pattern \<p>' | 'Shuffle (sorted)'; 'Channel Index' | 'Channel Index'; 'Proportion of trials (post > pre)' | |
| `12_shuffle_test_sig_heatmap_pattern_<p>` | :107 | 'Significant electrodes – pattern \<p>' | — | — | legend Significant / Not significant / Stimulated electrode |
| `Individual_PSTH_and_Raster_Pattern_<p>/Individual_PSTH_and_Raster_electrode_<id>` | stimActivityAnalysis.m:907 | sgtitle 'Pattern \<p> \| Electrode \<id> \| Corrected AUC: \<x> \| d' = \<x>'; 'Spike Raster (Response)'; 'Diagnostic: Response vs. Baselines (Z-score)' | 'Time from stimulus (ms)' | 'Trial Number'; 'Z-score' | |

### Step 2B: Group comparisons, PlotEphysStats.m (folder 2B, one figure per metric)
| Saved file pattern | Source | Panel title | X label | Y label |
|---|---|---|---|---|
| `3_RecordingsByGroup/HalfViolinPlots/<n>_<eMetl>_byGroup` | :419 | `<group>` | 'Age' | `<eMetl>` |
| `4_RecordingsByAge/HalfViolinPlots/<n>_<eMetl>_byAge` | :645 | 'Age\<DIV>' | 'Group' | `<eMetl>` |
| `3_RecordingsByGroup/NotBoxPlots/<n>_<eMetl>_byGroup` and `4_RecordingsByAge/NotBoxPlots/<n>_<eMetl>` (only with `includeNotBoxPlots`) | :308 / :531 | same | same | same |
| `1_NodeByGroup/<n>_<cMetl>_byGroup` | :731 | `<group>` | 'Age' | `<cMetl>` |
| `2_NodeByAge/<n>_<cMetl>` | :812 | 'Age\<DIV>' | 'Group' | `<cMetl>` |

Recording-level `eMetl` labels, which are both the filename stem and the y label, n = 1–15:
1. 'number of active electrodes'
2. 'mean firing rate (Hz)'
3. 'median firing rate (Hz)'
4. 'network burst rate (per minute)'
5. 'mean number of channels involved in network bursts'
6. 'mean network burst length (s)'
7. 'mean ISI within network burst (ms)'
8. 'mean ISI outside network bursts (ms)'
9. 'coefficient of variation of inter network burst intervals'
10. 'fraction of bursts in network bursts'
11. 'Single-electrode burst rate (per minute)'
12. 'Single-electrode average burst duration (ms)'
13. 'Single-electrode average ISI within burst (ms)'
14. 'Single-electrode average ISI outside burst (ms)'
15. 'Mean fraction of spikes in bursts per electrode'

Node-level `cMetl` labels, n = 1–8:
1. 'mean firing rate node'
2. 'mean firing rate active node'
3. 'Unit burst rate (per minute)'
4. 'Unit within-burst firing rate (Hz)'
5. 'Unit burst duration (ms)'
6. 'Unit ISI within burst (ms)'
7. 'Unit ISI outside burst (ms)'
8. 'Unit fraction of spikes in bursts'

suite2p mode uses its own label lists:
- Recording level: 'number of active units', 'mean firing rate (Hz)', 'median firing rate (Hz)', 'mean peak height', 'mean peak duration (s)', 'mean event area'.
- Node level: 'mean firing rate node', 'peak height', 'peak duration', 'event area', 'event area (sum)'.

### Step 3: Edge thresholding check
| Saved file | Source | Titles | X label | Y label | Colorbar |
|---|---|---|---|---|---|
| `<OUT>/3_EdgeThresholdingCheck/<FN><lag>msLagProbThreshCheck` | generateAdjMs.m:47 (also twoPhoton/suite2pToAdjm.m:180) | 'Change in threshold'; 'Raw Data Samples'; 'discarded edges (rep\<n>)' ×5 | 'Number of Repeats' ×2; 'Electrode' | 'Average threshold value' + right axis 'Coefficient of Variance'; 'Threshold value'; 'Electrode' | 'Edge weight' |

### Step 4A: Per-recording network analysis (folder 4A)
All titled `"<FNt> <lag> ms lag"` unless noted. Network plots have axes off.

| Saved file | Source | Title / panels | X label | Y label | Colorbar / legend |
|---|---|---|---|---|---|
| `1_adjM<lag>msConnectivityStats` | plotConnectivityProperties.m:105 | 'adjacency matrix'; 'max corr. value'; 'mean corr. value' | 'nodes'; 'node degree'; 'node strength'; 'edge weight' | 'nodes'; 'frequency' ×3 | 'correlation coefficient' |
| `2_MEA_NetworkPlot`, `2_scaled_MEA_NetworkPlot` | StandardisedNetworkPlot.m:574 | std | — | — | text 'node degree:', 'edge weight:' |
| `3_MEA_NetworkPlotNodedegreeBetweennesscentrality` (+`3_scaled_…`) | StandardisedNetworkPlotNodeColourMap.m:726 | std | — | — | size 'Node degree:'; cbar 'Betweenness centrality' |
| `4_MEA_NetworkPlotNodedegreeParticipationcoefficient` (+scaled) | same | std | — | — | 'Node degree:'; 'Participation coefficient' |
| `5_MEA_NetworkPlotNodestrengthLocalefficiency` (+scaled) | same | std | — | — | 'Node strength:'; 'Local efficiency' |
| `10_MEA_NetworkPlotNodedegreeAveragecontrollability` (+scaled) | same | std | — | — | 'Node degree:'; 'Average controllability' |
| `11_MEA_NetworkPlotNodedegreeModalcontrollability` (+scaled) | same | std | — | — | 'Node degree:'; 'Modal controllability' |
| `6_circular_NetworkPlotNodedegreeModule` | same, called from PlotIndvNetMet.m:392 | std | — | — | 'Node degree:', 'edge weight:', 'Module' |
| `2_combined_MEA_NetworkPlot`, `<n>_combined_MEA_NetworkPlot_<Metric name>` (spaces kept; n = 3/4/5/10/11) | PlotIndvNetMet.m:343 | none (copyobj drops titles) | — | — | colorbars as above |
| `7_adjM<lag>msGraphMetricsByNode` | electrodeSpecificMetrics.m:186 | std | — | 'node degree', 'mean edge weight', 'node strength', 'within-module degree z-score', 'local efficiency', 'participation coefficient', 'betweenness centrality' | |
| `8_adjM<lag>msNullModels` | plotNullModelIterations.m:54 | std; 'lattice null model'; 'random null model' | 'iterations/10' | 'small world coefficient' | |
| `9_adjM<lag>msNodeCartography` | NodeCartography.m:207 | std; 'node cartography' | 'participation coefficient' | 'within-module degree z-score' | |
| `9_circular_NetworkPlotNodeCartography[_modules]`, `9_MEA_NetworkPlotNodeCartography_modules` | StandardisedNetworkPlotNodeCartography.m:388 | std | — | — | role legend: 'peripheral node', 'non-hub connector', 'non-hub kinless node', 'provincial hub', 'connector hub', 'kinless hub', 'edge weight:' |
| `../NodeCartographyProportions` (recording folder, not the lag folder) | plotNodeCartographyProportions.m:126 | `<FNt>` | 'Participation coefficient'; 'STTC lag (ms)' | 'Within-module degree z-score'; 'proportion of nodes' | |
| `../nNMF` (recording folder) | plotNMF.m:154 | 'Original activity'; 'NMF component \<k>' | 'Time (s)'; 'Number of NMF components' | 'Electrode'; 'Variance explained'; 'Mean sq. root residual' | |

### Step 4B: Group comparisons (folder 4B)
| Saved file pattern | Source | Panel title | X label | Y label |
|---|---|---|---|---|
| `5_GraphMetricsByLag/<n>_<label>.<ext>` | PlotNetMet.m:138 | `<group>` | 'STTC lag (ms)' | `<label>` (legend title 'DIV') |
| `3_RecordingsByGroup/HalfViolinPlots/<lag>mslag/<n>_<label>_byGroup` | :284 | `<group>` | 'Age' | `<label>` |
| `4_RecordingsByAge/HalfViolinPlots/<lag>mslag/<n>_<label>_byAge` | :419 | 'Age \<DIV>' | 'Group' | `<label>` |
| `1_NodeByGroup/<lag>mslag/<n>_<label>_byGroup` | :467 | `<group>` | 'Age' | node `<label>` |
| `2_NodeByAge/<lag>mslag/<n>_<label>_byAge` | :517 | 'Age \<DIV>' | 'Group' | node `<label>` |
| `…/NotBoxPlots/…` variants (with `includeNotBoxPlots`) | :236 / :366 | same | same | same |
| `6_NodeCartographyByLag/NodeCartography<lag>mslag` | plotNetMetNodeCartography.m:123 | `<group>` | 'Age' | 'node cartography' |
| `7_DensityLandscape/ZandPC_scatter_with_kmeans_boundaries_` (overwritten for each lag) | TrialLandscapeDensity.m:200 | — | 'Participation Coefficient (PC)' | 'Within-module Z-score (Z)' |
| `8_CombinedPlotsByDiv/<G>/<rec>/<lag>mslag/<n>_scaled_MEA_NetworkPlot…` (under `OutputData<Date>`) | combinePlots.m:77 | — (image tiles) | — | — |

PlotNetMet.m filename handling:
- Backslashes are stripped from the label.
- `>` becomes 'greater than' and `<` becomes 'less than'.
- In the by-age sections, '/' becomes 'div'.

Network `<label>` list (script mode, `AdvancedSettings.m`, n = 1–29):
1. 'network size'
2. 'density'
3. 'clustering coefficient'
4. 'number of modules'
5. 'modularity score'
6. 'mean path length'
7. 'global efficiency'
8. 'small worldness \sigma'
9. 'small worldness \omega'
10. 'Effective rank'
11. 'Num NMF components'
12. 'nNMF div network size'
13. 'Node degree mean'
14. 'Top 25% node degree'
15. 'Significant edge weight mean'
16. 'Top 10% edge weight mean'
17. 'Node strength mean'
18. 'Local efficiency mean'
19. 'Participant coefficient (PC) mean'
20. 'Top 10% PC'
21. 'Bottom 10% PC'
22. 'Percentage within-module z-score > 0'
23. 'Percentage within-module z-score \< 0'
24. 'NC1PeripheralNodes'
25. 'NC2NonhubConnectors'
26. 'NC3NonhubKinless'
27. 'NC4ProvincialHubs'
28. 'NC5ConnectorHubs'
29. 'NC6KinlessHubs'

GUI mode adds 'Mean average controllability', 'Mean modal controllability' and 'Top 5% betweenness centrality mean'. In GUI mode the numbering follows `netMetToCal`.

Node `<label>` list, n = 1–7:
1. 'node degree'
2. 'edge weight'
3. 'node strength'
4. 'within-module degree z-score'
5. 'local efficiency'
6. 'participation coefficient'
7. 'betweenness centrality'

GUI mode adds 'Average Controllability' and 'Modal Controllability'.

### Step 5: Stats and classification (`<stats>/5_Stats[/<lag>msLag]`)
| Saved file | Source | Title | X label | Y label | Other |
|---|---|---|---|---|---|
| `5_Stats/1_sig_table_<lag>ms_lag` | plotStats.m:219 | — | (metric names as ticks) | (test names as ticks) | colorbar 'D prime' |
| `<lag>msLag/1_allclassifiersConfusionMatrix` | doClassification.m:269 | 'linearSVM' / 'kNN' / 'decisionTree' / 'LDA' | default confusionchart | default | |
| `<lag>msLag/2_allclassifiersMisclassificationRatePerKFold` | :238 | — | 'Classifier' | 'Misclassification rate' | |
| `<lag>msLag/3_classificationFeatureImportanceViaLeaveOneOut` | :189 | — | 'Features' | 'Leave one out loss - original loss (Higher is better)' | |
| `<lag>msLag/allRegressorMSEPerKFold` (single group only) | :413 | — | 'Regression models' | 'Mean squared error' | |
| `<lag>msLag/allRegressorActualVsPredicted` (single group only) | :460 | 'svmRegressor' / 'regressionTree' / 'ridgeRegression' / 'fforwardNN' | 'Observed' | 'Predicted' | |
| `<lag>msLag/4_nodeLevelFeatureCorrelation` | featureCorrelation.m:76 | '\<group> \<DIV>' per panel | (metric names) | (metric names) | colorbar 'Correlation' |
| `<lag>msLag/5_recordingLevelFeatureCorrelation` | :155 | same | same | same | same |

### Not reached in a normal run
These functions save figures but are dead code or lack a caller:
- **plotNetworkWideMetrics.m:173** `NetworkWideMetrics`
  - Title `<FNt>`; xlabel 'STTC lag (ms)'.
  - ylabels: 'edge weight (mean)', 'edge weight (max)', 'density', 'number of modules', 'modularity score', 'mean clustering coefficient (norm)', 'characteritics path length (norm)', 'global efficiency', 'small world coefficent \sigma', 'small world coefficent \omega' (typos are in the source).
- **PlotNetMetOrganoid.m** (not runnable): `<eMet>.png` with x 'STTC lag (ms)' and then 'DIV', y `<eMetl>`; `NodeCartography.fig` with x 'DIV', y 'node cartography'.
- **StandardisedNetworkPlotNodeColourMap2.m:293** `<FN>_<grid|circular>_NetworkPlot<z2name>`: colorbar `z2name`.
- **TrialLandscapeDensity.m:325** `ZandPCLandscape_sigma_<s>_`: 'sigma=\<s>[,bandwidth=\<bw>]', x 'PC', y 'Z'.
- **findBasinsOfAttraction.m:41/75/112** `ZandPCLandscape_WaterShed[Group1|Group2]_sigma_<s>_`: x 'Participation Coefficient (PC)', y 'Within-module Z-score (Z)'.
- **sensitivityAnalysis/testSensitivity.m** (standalone script, writes `.svg` + `.png` to the current folder). Shared y label 'Proportion of succesful detection':

| File | sgtitle | x label |
|---|---|---|
| `numModulesSensitivity` | 'Number of modules' | 'Edge replacement probability' |
| `smallWorldOmegaSensitivity` | — | 'Small-worldness coefficient (\omega)' |
| `top10meanPCSensitivity` | — | 'Participation coefficient (top 10%)' |
| `networkDensitySensitivity` | 'Network density' | 'Edge replacement probability' |
| `meanEdgeWeightSensitivity` | 'Mean edge weight (top 10%)' | 'Edge replacement probability' |

- **runMEANAPviewer.m** (GUI viewer) saves `1_MEA_NetworkPlot` and `1_MEA_NetworkPlotND<z2name>` with the title 'temp 1000 ms lag'.

---

## Python (`src/meanap/`)

### Step 1: Detection and sorting checks (`<OUT>/1_SpikeDetection/1B_SpikeDetectionChecks/<G>/<R>/`)
| Saved file | Source | Title | X label | Y label | Other |
|---|---|---|---|---|---|
| `1_ExampleTraces.png` | pipeline/plotting.py:442 | suptitle `rec_name`; panels 'Electrode \<ch> \| \<start> - \<end> s' | — | 'Amplitude ($\mu$V)' | |
| `2_SpikeFrequencies.png` | :403 | `rec_name` | 'Time (minutes)' | 'Spiking frequency (Hz)' | |
| `3_Waveforms.png` | :510 | suptitle '\<rec>\nUnique spikes by method from electrode \<ch>'; panels `<method>` | — | 'Voltage ($\mu$V)' | |
| `1_UnitsPerElectrode.png` | pipeline/plotting_sorting.py:251 | '\<rec>\n\<n> unit(s) on \<n> of \<N> electrodes (\<sorter> \<ver>)' | — | — | colorbar 'units kept on electrode' |
| `2_UnitTemplates.png` | :289 | suptitle '\<rec> — unit templates on each electrode (solid: good, dashed: multi-unit; ±\<amp> µV)' | — | — | |
| `3_UnitQuality.png` | :328 | 'Where each unit fell against the curation floors'; 'Firing rate by label'; suptitle '\<rec> — \<n> unit(s) from \<sorter>' | 'ISIs shorter than the refractory period (%)' | 'SNR'; 'firing rate (Hz)' | |

### Step 2A: Per recording (folder 2A)
| Saved file | Source | Title | X label | Y label | Colorbar |
|---|---|---|---|---|---|
| `1_FiringRateByElectrode.png` | pipeline/plotting_step2.py:46 | 'Firing Rate by Electrode' | — | 'Mean firing rate per electrode (Hz)' | |
| `2_Heatmap.png` | :181 | 'Firing Rate\nscaled to recording' / '…\nscaled to entire dataset' | — | — | 'Mean FR (Hz)' |
| `3_BurstRate_heatmap.png` | same | 'Burst Rate\n…' | — | — | 'Burst Rate (bursts/min)' |
| `4_BurstDur_heatmap.png` | same | 'Burst Duration\n…' | — | — | 'Duration (ms)' |
| `5_FractSpikesInBursts_heatmap.png` | same | 'Fraction Spikes in Bursts\n…' | — | — | 'Fraction' |
| `6_ISIwithinBurst_heatmap.png` | same | 'ISI Within Burst\n…' | — | — | 'ISI (ms)' |
| `7_ISIoutsideBurst_heatmap.png` | same | 'ISI Outside Burst\n…' | — | — | 'ISI (ms)' |
| `3_Raster.png` | :233 | 'raster scaled to recording' / 'raster scaled to entire data batch' | 'Time (s)' | 'Electrode' | 'Firing Rate (Hz)' |
| `8_BurstDetectionInfo.png` | :318 | 'Raster (All spikes)'; 'Raster (Only network bursts)'; 'ISI Distribution' | 'Time (s)'; 'Inter-Spike Interval (s)' | 'Electrode'; 'Probability' | |
| `3_ActivityRaster.png`, `4_ActivityRaster_zscored.png` (CAT-NAP) | catnap/rasters.py:214 | '\<rec> — \<activity>[ (z-scored per cell)]' | 'Time (s)' | 'Cell' | 'z-score (per cell)' / 'Events / s' / 'Deconvolved activity (a.u.)' / 'Denoised fluorescence (a.u.)' / 'Fluorescence (a.u.)' |
| `unit_<roi>_2ptraces.png` (CAT-NAP) | catnap/plotting.py:95 | '\<rec>  cell \<roi>' | 'Time (s)' | 'Fluorescence'; 'Arbitrary units' ×2 | |
| `9_FR_before_after_stimulation[_pattern_<k>].png` | stim/plotting.py:378 | `<rec>` | 'Pre-stim firing rate (spikes/s)' | 'Post-stim firing rate (spikes/s)' | |
| `10_stimulation_raster_and_psth[_pattern_<k>].png` | :440 | `<rec>` | 'Time from stimulation (ms)' | 'Mean firing rate (spikes/s)'; 'Channel' | 'Firing rate (spikes/s)' |
| `spikeLatency_pattern_<k>_heatmap.png` | :186 | 'Pattern \<k>' | — | — | 'Median spike latency (ms)' |
| `stimPattern_<k>_heatmap.png` | :186 | 'Pattern \<k>' | — | — | 'Firing rate (spikes/s)' |
| `12_shuffle_test_null_dist_pattern_<k>.png` | :503 | 'Null trial proportion distribution – pattern \<k>  \|  \<fn>'; 'Observed vs null – pattern \<k>' | 'Shuffle (sorted)'; 'Channel Index' | 'Channel Index'; 'Proportion of trials (post > pre)' | |
| `12_shuffle_test_sig_heatmap_pattern_<k>.png` | :186 | 'Significant electrodes – pattern \<k>' | — | — | |
| `Individual_PSTH_and_Raster_Pattern_<k>/Individual_PSTH_and_Raster_electrode_<id>.png` | :698 | suptitle "Pattern \<k> \| Electrode \<id> \| Corrected AUC: \<x> \| d' = \<x>"; 'Spike Raster (Response)'; 'Diagnostic: Response vs. Baselines (Z-score)' | 'Time from stimulus (ms)' | 'Trial Number'; 'Z-score' | |
| `13_StimNetwork_<cond>_<lag>mslag.png` | pipeline/stim_step.py:468 | suptitle '\<rec> — \<cond>, lag \<lag> ms\n\<null> null, \<n> trials'; 'Baseline \<w0>–\<w1> s (significant STTC)', 'Evoked \<w0>–\<w1> s (significant STTC)', 'Evoked − baseline (raw STTC)', 'Noise correlation (\<n> trials)' | 'Node' | 'Node' | |

### Step 2B: Group comparisons (folder 2B), plotting_step2 → `plot_half_violin_by_x` (plotting_step4.py:1337)
| Saved file pattern | Panel title | X label | Y label |
|---|---|---|---|
| `3_RecordingsByGroup/HalfViolinPlots/<key>_byGroup.png` | `<group>` | 'Age' | label |
| `4_RecordingsByAge/HalfViolinPlots/<key>_byDIV.png` | 'Age \<div>' | 'Group' | label |
| `1_NodeByGroup/<key>_byGroup_node.png` | `<group>` | 'Age' | label |
| `2_NodeByAge/<key>_byDIV_node.png` | 'Age \<div>' | 'Group' | label |

The key/label pairs differ slightly from MATLAB.

Recording level (`EPHYS_REC_METRICS`):

| Key | Label |
|---|---|
| numActiveElec | 'number of active electrodes' |
| FRmean | 'mean firing rate (Hz)' |
| FRmedian | 'median firing rate (Hz)' |
| NBurstRate | 'network burst rate (per minute)' |
| meanNumChansInvolvedInNbursts | 'mean number of channels involved in network bursts' |
| meanNBstLengthS | 'mean network burst length (s)' |
| meanISIWithinNbursts_ms | 'mean ISI within network burst (ms)' |
| meanISIoutsideNbursts_ms | 'mean ISI outside network bursts (ms)' |
| CVofINBI | 'coefficient of variation of inter network burst intervals' |
| fracInNburst | 'fraction of bursts in network bursts' |
| channelAveBurstRate | 'Single-electrode burst rate (per min)' |
| channelAveBurstDur | 'Single-electrode avg burst dur (ms)' |
| channelAveISIwithinBurst | 'Single-electrode avg ISI within burst (ms)' |
| channelAveISIoutsideBurst | 'Single-electrode avg ISI outside burst (ms)' |
| channelAveFracSpikesInBursts | 'Mean fraction of spikes in bursts per electrode' |

Node level (`EPHYS_NODE_METRICS`):

| Key | Label |
|---|---|
| FR | 'mean_firing_rate_node' (raw identifier) |
| FRactive | 'mean_firing_rate_active_node' (raw identifier) |
| channelBurstRate | 'Unit burst rate (per minute)' |
| channelWithinBurstFr | 'Unit within-burst firing rate (Hz)' |
| channelBurstDur | 'Unit burst duration (ms)' |
| channelISIwithinBurst | 'Unit ISI within burst (ms)' |
| channeISIoutsideBurst | 'Unit ISI outside burst (ms)' |
| channelFracSpikesInBursts | 'Unit fraction of spikes in bursts' |

### Step 3
| Saved file | Source | Titles | X label | Y label | Colorbar |
|---|---|---|---|---|---|
| `<OUT>/3_EdgeThresholdingCheck/<rec><lag>msLagProbThreshCheck.png` | pipeline/plotting_step3.py:250 | 'Change in threshold'; 'Raw Data Samples'; 'discarded (rep\<n>)' ×5 | 'Number of Repeats'; 'Electrode' | 'Average threshold value' + twin 'Coefficient of Variance'; 'Threshold value'; 'Electrode' | 'Edge weight' |

### Step 4A: Per recording and lag (folder 4A; `<lag>msbin` for CAT-NAP correlation)
| Saved file | Source (plotting_step4.py) | Title | X label | Y label | Colorbar / legend |
|---|---|---|---|---|---|
| `1_adjM<lag>msConnectivityStats.png` | :102 | suptitle '\<rec> \<lag> ms lag'; 'adjacency matrix', 'max corr. value', 'mean corr. value' | 'nodes'; 'node degree'; 'node strength'; 'edge weight' | 'nodes'; 'frequency' | 'correlation coefficient' |
| `2_MEA_NetworkPlot.png` | :184 | '\<rec>  \<lag> ms lag' (scaled: + ' (scaled to data batch)') | — | — | text 'node degree:', 'edge weight:' |
| `3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png` | :184 | same | — | — | 'Betweenness centrality' / size 'node degree' |
| `4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png` | :184 | same | — | — | 'Participation coefficient' / 'node degree' |
| `5_MEA_NetworkPlotNodestrengthLocalefficiency.png` | :184 | same | — | — | 'Local efficiency' / 'node strength' |
| `10_MEA_NetworkPlotNodedegreeAveragecontrollability.png` | :184 | same | — | — | 'Average controllability' / 'node degree' |
| `11_MEA_NetworkPlotNodedegreeModalcontrollability.png` | :184 | same | — | — | 'Modal controllability' / 'node degree' |
| `*_scaled_MEA_NetworkPlot*.png` (the 6 above) | :184 | + ' (scaled to data batch)' | — | — | same |
| `<n>_combined_MEA_NetworkPlot[_<Metric name>].png` | :381 | '\<rec>  \<lag> ms lag\nscaled to recording' / '…\nscaled to entire data batch' | — | — | |
| `6_circular_NetworkPlotNodedegreeModule.png` | :864 | '\<FNt>  \<lag> ms lag' | — | — | 'Node degree:', 'edge weight:', 'Module' |
| `7_adjM<lag>msGraphMetricsByNode.png` | :1910 | suptitle '\<FNt> \<lag> ms lag' | — | 'node degree', 'mean edge weight', 'node strength', 'within-module degree z-score', 'local efficiency', 'participation coefficient', 'betweenness centrality' | |
| `9_adjM<lag>msNodeCartography.png` | :532 | '\<rec> \<lag> ms lag  —  node cartography' | 'participation coefficient' | 'within-module degree z-score' | |
| `9_circular_NetworkPlotNodeCartography.png` | :1013 | '\<FNt>  \<lag> ms lag' | — | — | 6 role names, 'edge weight:' |
| `12_MeanImageAndNetwork.png` (CAT-NAP) | :247 | '\<rec>\nimaged field of view' / '\<rec>  \<lag> ms lag\nnetwork' | — | — | |
| `cellTypeSubnetworks/1_CellTypeNetwork.png` (CAT-NAP) | catnap/subnetwork_plotting.py:233 | '\<rec>  \<lag> ms lag\n\<label>: \<n> edges · …' | — | — | legend '\<type> (n=\<n>)', 'between-type edge' |
| `cellTypeSubnetworks/2_SubnetworkGraphs.png` | :294 | suptitle '\<rec>  \<lag> ms lag'; panels '\<name>\n\<n> cells · \<edges> · density \<d>' | — | — | |
| `cellTypeSubnetworks/3_NodeMetricsByCellType.png` | :351 | suptitle '… — whole-network node metrics by cell type' | '\<group>\n(n=…)' ticks | raw keys ND, NS, MEW, Eloc, BC, PC, Z, NE, CC_raw, WithinGroupStrengthFrac | |
| `cellTypeSubnetworks/4_SubnetworkMetrics.png` | :418 | suptitle '… — metrics of each cell-type subnetwork' | — | raw keys Dens, NDmean, NSmean, MEW_mean, Eglob, ElocMean, CC_rawMean, SW, SWw, Q, nMod | |
| `cellTypeSubnetworks/5_EdgeMixing.png` | :472 | suptitle '… — connectivity within/between cell types'; 'edge density', 'mean weight (edges present)' | — | — | |

### Step 4B: Group comparisons (folder 4B; `<L>` = `Lag<n>ms` or `Bin<n>ms`)
| Saved file pattern | Source (plotting_step4.py) | Panel title | X label | Y label |
|---|---|---|---|---|
| `3_RecordingsByGroup/HalfViolinPlots/<L>/<key>_byGroup.png` | :1337 | `<group>` | 'Age' | label |
| `4_RecordingsByAge/HalfViolinPlots/<L>/<key>_byDIV.png` | :1337 | 'Age \<div>' | 'Group' | label |
| `1_NodeByGroup/<L>/<key>_byGroup_node.png`, `2_NodeByAge/<L>/<key>_byDIV_node.png` | :1337 | same | same | node label |
| `5_GraphMetricsByLag/<key>.png` | :1748 | `<group>` | 'STTC lag (ms)' or 'Correlation bin (ms)' | label (legend title 'DIV') |
| `6_NodeCartographyByLag/NodeCartography<lag>mslag.png` | :1599 | `<group>` | 'Age' | 'node cartography' |
| `6_NodeCartographyByLag/NodeCartographyProportionsByGenotype<lag>mslag.png` | :1453 | `<group>` | 'Age' (bottom) | 'Proportion of nodes' |
| `6_NodeCartographyByLag/NodeCartographyProportionsByAge<lag>mslag.png` | :1511 | 'DIV \<div>' | — | 'Proportion of nodes' |
| `7_DensityLandscape/ZandPC_scatter_with_kmeans_boundaries_.png` | :1642 | — | 'Participation Coefficient (PC)' | 'Within-module Z-score (Z)' |

Recording-level labels (`NETMET_REC_METRICS`):

| Key | Label |
|---|---|
| aN | 'Active Nodes' |
| Dens | 'Density' |
| CC | 'Clustering Coefficient' |
| nMod | 'Number of Modules' |
| Q | 'Modularity (Q)' |
| PL | 'Path Length' |
| Eglob | 'Global Efficiency' |
| SW | 'Small-worldness (SW)' |
| SWw | 'Small-worldness (SWw)' |
| effRank | 'Effective Rank' |
| num_nnmf_components | 'Num NNMF Components' |
| nComponentsRelNS | 'NNMF Components / NS' |
| NDmean | 'Mean Node Degree' |
| NDtop25 | 'Top 25% Node Degree' |
| sigEdgesMean | 'Mean Significant Edge Weight' |
| sigEdgesTop10 | 'Top 10% Significant Edge Weight' |
| NSmean | 'Mean Node Strength' |
| ElocMean | 'Mean Local Efficiency' |
| PCmean | 'Mean Participation Coefficient' |
| PCmeanTop10 | 'Top 10% Participation Coefficient' |
| PCmeanBottom10 | 'Bottom 10% Participation Coefficient' |
| percentZscoreGreaterThanZero | 'Percent Z > 0' |
| percentZscoreLessThanZero | 'Percent Z \< 0' |
| NCpn1 | 'Proportion Peripheral Nodes (R1)' |
| NCpn2 | 'Proportion Non-hub Connectors (R2)' |
| NCpn3 | 'Proportion Non-hub Kinless Nodes (R3)' |
| NCpn4 | 'Proportion Provincial Hubs (R4)' |
| NCpn5 | 'Proportion Connector Hubs (R5)' |
| NCpn6 | 'Proportion Kinless Hubs (R6)' |
| aveControlMean | 'Mean Average Controllability' |
| modalControlMean | 'Mean Modal Controllability' |

Node-level labels (`NETMET_NODE_METRICS`):

| Key | Label |
|---|---|
| ND | 'Node Degree' |
| MEW | 'Mean Edge Weight' |
| NS | 'Node Strength' |
| Z | 'Within-Module Degree Z-Score' |
| Eloc | 'Local Efficiency' |
| PC | 'Participation Coefficient' |
| BC | 'Betweenness Centrality' |
| aveControl | 'Average Controllability' |
| modalControl | 'Modal Controllability' |

### CAT-NAP cell tracking (`<OUT>/CellTracking/DevelopmentByCellType/[<measure>/]<definition>/…`)
| Saved file | Source (catnap/tracking/development_plots.py) | Title | X label | Y label |
|---|---|---|---|---|
| `Activity\|Network/<L>/1_Trajectories/<metric>.png` | :521 | suptitle '\<label> — tracked cells by \<definition>'; panels `<group>` | 'Age (DIV)' | `<label>` |
| `…/2_ChangePerCell/<metric>.png` | :568 | same | — | 'Change in \<label>\nper week' |
| `Network/<L>/3_RoleTransitions.png` | :613 | suptitle 'Cartography role transitions — by \<definition>'; panels '\<type> · \<group>  (\<n> transitions)' | 'role on the next tracked day' | 'role on one day' |

### Step 5: Stats and ML (`<OUT>/5_StatsAndML/<lag|all>/<stem><fig_ext>`; 5F goes in `MeasureComparison/<lag>/`)
| Stem | Source (stats/plots.py) | Title (suptitle when marked "sup") | X label | Y label / colorbar |
|---|---|---|---|---|
| `5A1_effects_mixed-model` | :206 | 'Effect sizes — age and genotype' | — | cbar 'Effect size' |
| `5A2_effects_group-at-age-<age>` | :206 | 'Effect sizes — genotype at DIV \<age>' | — | cbar 'Effect size' |
| `5A3_trajectories_top_metrics` | :262 | sup 'Metrics with the strongest age or group effects'; panels = metric label | 'Age (DIV)' | — |
| `5B1_feature_correlation` | :304 | 'Feature correlation (\<method>), clustered' | — | cbar 'Correlation' |
| `5B2_feature_correlation_by_group_age` | :343 | '\<group>  DIV \<age>' | — | cbar 'Correlation' |
| `5B3_feature_dimensionality` | :368 | 'Feature-space dimensionality' | 'Principal component' | 'Variance explained' |
| `5C1_decoding_performance` | :418 | 'Decoding \<target> — \<n> recordings from \<g> cultures' | — | 'Balanced accuracy (held-out)' |
| `5C2_decoding_confusion` | :451 | model name | 'Predicted' | 'True' |
| `5C3_decoding_feature_importance` | :474 | model name | 'Drop in balanced accuracy' | — |
| `5C4_lda_projection` | :542 | 'Linear discriminant projection — \<target>' | 'LD1 (\<p>% of class separation)' | 'LD2 (\<p>%)' |
| `5C5_decoding_by_age` | :584 | 'Group separability across age' | 'Age (DIV)' | 'Balanced accuracy (held-out)' |
| `5C6_genotype_shapley_by_age` | :767 | 'Which features carry the genotype signal, and when' | 'DIV \<a>\n\<t> total' ticks | cbar 'Shapley share of balanced accuracy above chance' |
| `5C7_genotype_shapley_across_ages` | :825 | 'Genotype decoding, and what carries it, across age' | 'Age (DIV)' | 'Decodability\n(accuracy − chance)'; 'Shapley share of decodability' |
| `5C8_feature_family_contributions` | :892 | 'What kind of feature carries the genotype difference' | 'DIV \<a>' ticks | 'Shapley share of decodability' |
| `5C9_feature_family_alone_vs_unique` | :968 | sup 'Does each family carry signal of its own?' | 'Age (DIV)' | 'Balanced accuracy above chance' |
| `5D1_regression_performance` | :613 | 'Predicting \<target> from network and activity features' | — | '$R^2$ (held-out)' |
| `5D2_variance_decomposition` | :650 | 'What explains \<target>? Full-model $R^2$ = \<r2>, partitioned across \<n> features' | 'Share of variance in \<target>' | — |
| `5D3_observed_vs_predicted` | :684 | '\<model>: $R^2$ = \<r2>' | 'Observed \<target>' | 'Predicted \<target> (held-out)' |
| `5E1_density_sweep_by_group` | :1048 | sup 'Topology at matched density, by group'; panels from `_SWEEP_LABELS` | 'Imposed density' | — |
| `5E2_density_sweep_by_age` | :1048 | sup 'Topology at matched density, by age'; panels from `_SWEEP_LABELS` | 'Imposed density' | — |
| `5E3_density_sweep_context` | :1118 | sup 'Reading the density sweep'; 'Densities the recordings actually have'; 'How much of the network survives thresholding' | 'Age (DIV)'; 'Imposed density' | 'Observed density (step 4)'; 'Largest component (fraction of nodes)' |
| `5E4_topology_controlled` | :1182 | sup 'Does network topology carry genotype information of its own?'; 'Share of decodability', 'What topology achieves alone', 'What only topology contributes' | 'Age (DIV)' | 'Balanced accuracy above chance' |
| `5E5_size_control` | :1297 | sup 'Controlling for network size'; 'Sizes the recordings actually have'; 'Kept per group' | 'Age (\<col>)' | 'Connected nodes per recording'; 'Fraction of recordings retained' |
| `5E6_selection_check` | :1363 | sup 'Do the group differences survive a stricter size cut?'; '\<a> vs \<b>' | 'Standardised group difference' | — |
| `5E7_control_effects` | :1475 | sup 'Age and genotype effects, before and after the controls' | 'Effect size' | — |
| `5E8_genotype_effect_by_age` | :1553 | sup 'Genotype differences at each age, before and after the controls' | 'Age (DIV)' | `_SWEEP_LABELS` |
| `5E9_metric_values_by_control` | :1658 | sup 'The metrics themselves, under each level of control'; 'no control (step 4)', 'matched density', 'matched density + size' | 'Age (DIV)' | `_SWEEP_LABELS` |
| `5F1_measure_agreement` | :1725 | 'Do the measures rank recordings the same way?\nSpearman rho between measures, over matched recordings' | — | cbar 'Spearman rho' |
| `5F2_measure_differences` | :1782 | 'How far do the values move when the measure changes?\nfilled = significant after FDR correction (p \< \<alpha>)' | "paired difference between measures (Hedges' g$_{av}$)" | — |
| `5F3_measure_concordance` | :1853 | sup 'Would the conclusion have been the same?\ngroup and age effects, measured each way' | 'effect under \<a>' | 'effect under \<b>' |
| `5F4_measure_decoding` | :1904 | 'Which measure carries the most information about \<target>?' | 'balanced accuracy (best model)' | — |

`_SWEEP_LABELS`:

| Key | Label |
|---|---|
| CC | 'Clustering coefficient' |
| PL | 'Characteristic path length' |
| Eglob | 'Global efficiency' |
| ElocMean | 'Mean local efficiency' |
| BCmean | 'Mean betweenness centrality' |
| Q | 'Modularity (Q)' |
| nMod | 'Number of modules' |
| lccFraction | 'Largest component (fraction of nodes)' |

Cell-type mosaic figures (stats/celltype_plots.py). `<v>` is 'All labelled cells' or 'Tracked cells':

| Stem | Source | Title / suptitle | X label | Y label / colorbar |
|---|---|---|---|---|
| `5G1_celltype_inventory` | :174 | sup 'Cell-type labels by culture and age  ·  dot area: labelled cells, colour: % positive (blue = all -, red = all +)'; panels `<marker>` | 'DIV' | cbar '% of cells positive' |
| `5G2_mosaic_cell_autonomy` | :323 | sup 'On the diagonal the difference travels with the cell (cell-autonomous); on the horizontal axis it belongs to the network'; panels `<v>` | 'Genotype: \<neg> vs \<pos> (SD)' | 'Cell-autonomous: \<mosN> vs \<mosP> (SD)' |
| `5G3_mosaic_contrasts` | :473 | sup 'Mosaic contrasts per feature  ·  stars: FDR-corrected'; panels `<v>` | — | cbar 'difference (SD; per week for the last column)' |
| `5G4_mosaic_within_recording` | :522 | sup 'Within-recording differences (\<v>)  ·  one dot per recording, coloured by culture; black: mean ± 95% CI'; panels = feature label | 'DIV' | '\<mosN> - \<mosP> (SD)' |
| `5G5_mosaic_ko_scores` | :586 | '\<v>  ·  \<neg> vs \<pos> held-out AUC \<x>'; 'per recording: \<x>% higher in \<mosN>\nmodel gap … Wilcoxon p=…' | — | '\<neg>-likeness (log-odds)'; 'recording mean (log-odds)' |
| `5G6_mosaic_cell_autonomy_by_age` | :629 | 'Cell-autonomous difference by age (\<v>)' | 'DIV (mosaic cultures)' | cbar '\<mosN> - \<mosP> (SD)' |
| `5G7_mosaic_decoding` | :686 | '\<mosN> vs \<mosP> from within-recording features\nticks: 95th percentile of the within-recording label-shuffle null'; 'Permutation importance, pooled (\<v>)' | 'drop in balanced accuracy when shuffled' | 'Balanced accuracy (held-out cultures)' |
| `5G8_mosaic_trajectories` | :737 | sup 'Trajectories by cell class (\<v>)  ·  mean ± SEM across cultures'; panels = feature label | 'DIV' | 'culture mean (SD)' |

### User-triggered GUI saves (filename chosen by the user)
- **stim/fr_diff_plot.py:372**: default name `fr_diff_<sel|all>[_log2].png`; formats png, svg or pdf.
  - Panel title: the slice, shown only when there is more than one panel.
  - xlabel 'Channel'.
  - ylabel 'Firing rate difference from baseline (%)', or 'Firing rate change from baseline\n(log₂ stim / \<baseline>)'.
- **gui/panels/network_viewer.py:113**: default name `<recording>.png`.
- **gui/spike_viewer.py:2795**: saves the current tab.

### Python code that never runs
- `_plot_violin` in plotting_step2 and plotting_step4.
- `stim/plotting.plot_stim_detection_checks`, which would write `1_StimsDetected`, `2_StimsHeatmap` and `3_[No]StimsElectrode_<id>` with the same labels as MATLAB.
- `catnap/tracking/network.plot_tracked_network`: suptitle '\<n> cells tracked through every day', panels 'DIV\<div>\n\<n> edges ≥ \<thr>'.

### Known issues
- **Undefined `F1`:**
  - MATLAB `plotting/plotNetworkBursts.m:124`: `close(F1)` with `F1` undefined.
  - `doClassification.m:189`: `F1` is undefined when `showOneFig==0`.
  - `electrodeSpecificMetrics.m:25`: `close all` deletes `F1` before it is saved.
- **Bad save path:** `find_best_spike_result.m:389` is missing a path separator.
- **Overwritten every lag:** `ZandPC_scatter_with_kmeans_boundaries_` in both MATLAB and Python.
- **Wrong axis label:** `2_SpikeFrequencies` is labelled 'Hz' in both MATLAB and Python, but it plots raw spikes per bin.
- **Prefix clash:** Python step 2A has both `3_Raster.png` and `3_BurstRate_heatmap.png`.
