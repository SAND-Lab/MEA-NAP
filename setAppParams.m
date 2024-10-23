function app = setAppParams(app, Params)
%SETAPPPARAMS Load saved parameters and add them to GUI
% INPUTS 
% -------------------------
%  app : matlab app object 
%  Params : structure 
% OUTPUTS 
% ------------------------
%  app : matlab app object

app.MEANAPFolderEditField.Value = Params.HomeDir;
app.MEADataFolderEditField.Value = Params.rawData;
app.OutputDataFolderEditField.Value = Params.outputDataFolder;
app.SpreadsheetFilenameEditField.Value = Params.spreadSheetFileName;
app.SpreadsheetRangeEditField.Value = Params.spreadSheetRange;
app.StartAnalysisStepEditField.Value = Params.startAnalysisStep;
app.OptionalStepstoRunListBox.Value = Params.optionalStepsToRun;

app.UsePreviousAnalysisCheckBox.Value = Params.priorAnalysis;
app.PreviousAnalysisFolderEditField.Value = Params.priorAnalysisPath;
app.SpikeDataFolderEditField.Value = Params.spikeDetectedData;

%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
app.ShowAdvancedSettingsCheckBox.Value = Params.showAdvancedSetting;

%% Spike detection settings

app.DetectSpikesCheckBox.Value = Params.detectSpikes;
app.SamplingFrequencyEditField.Value = Params.fs;
app.DownSampleFrequencyEditField.Value = Params.dSampF;
app.PotentialDifferenceUnitEditField.Value = Params.potentialDifferenceUnit;
app.ChannelLayoutDropDown.Value = Params.channelLayout;
app.ThresholdsEditField.Value = string(['[', strjoin(Params.thresholds, ', '), ']']);
app.SpikeMethodforAnalysisEditField.Value = Params.SpikesMethod;
app.WaveletsListBox.Value = Params.wnameList;
app.WaveletCostEditField.Value = num2str(Params.costList);
app.SpikeMethodforAnalysisEditField.Value = Params.SpikesMethod;
app.RunspikecheckonpreviousspikedataCheckBox.Value = Params.runSpikeCheckOnPrevSpikeData;

%% Connectivity settings 

app.STTCLagmsEditField.Value = ['[', strjoin(cellstr(string(Params.FuncConLagval)), ', '), ']'];
app.AdjacencymatrixtypeButtonGroup.SelectedObject.Text = [upper(Params.adjMtype(1)), Params.adjMtype(2:end)];
app.TruncateRecordingCheckBox.Value = Params.TruncRec; 
app.TruncationlengthsecEditField.Value = Params.TruncLength;

app.ProbthresholdingiterationsEditField.Value = Params.ProbThreshRepNum;
app.ProbthresholdingtailEditField.Value = Params.ProbThreshTail;
app.PlotprobthresholdingchecksCheckBox.Value = Params.ProbThreshPlotChecks;
app.ProbthresholdingnumchecksEditField.Value = Params.ProbThreshPlotChecksN;

app.AutomaticallysetnodecartographyboundariesperlagCheckBox.Value = Params.autoSetCartographyBoudariesPerLag;
app.AutomaticallysetnodecartographyboundariesCheckBox.Value = Params.autoSetCartographyBoundaries;
app.NodecartographylagvaluesEditField.Value = ['[', strjoin(cellstr(string(Params.cartographyLagVal)), ', '), ']'];

app.NetworkmetricstocalculateListBox.Value = Params.netMetToCal;

%% Plotting settings

% colors to use for each group in group comparison plots
% this should be an nGroup x 3 matrix where nGroup is the number of groups
% you have, and each row is a RGB value (scaled from 0 to 1) denoting the
% color
for ext_i = 1:length(Params.figExt)
    figExtWithoutDot{ext_i} = Params.figExt{ext_i}(2:end);
end
app.FigureformatsListBox.Value = figExtWithoutDot;

app.DonotcompressSVGCheckBox.Value = Params.fullSVG; 
app.DisplayonlyonefigureCheckBox.Value = Params.showOneFig;

app.RasterMapUpperPercentileEditField.Value = Params.rasterPlotUpperPercentile;
app.IncludeNotBoxPlotsCheckBox.Value = Params.includeNotBoxPlots;
app.IncludechannelnumberinplotsCheckBox.Value = Params.includeChannelNumberInPlots;
app.UsetheoreticalboundsCheckBox.Value = Params.use_theoretical_bounds;
app.UseminmaxallrecordingboundsCheckBox.Value = Params.use_min_max_all_recording_bounds;
app.UseminmaxpergroupboundsCheckBox.Value = Params.use_min_max_per_genotype_bounds;

app.colorUITable.Data(:, 2:end) = Params.groupColors;

app.MinimumnodesizeEditField.Value = Params.minNodeSize;  % minimum node size in network plots
app.KDEHeightEditField.Value = Params.kdeHeight;  % height of the KDE curve, only affects plotting and not the kernel density estimate itself
app.KDEwidthforonepointEditField.Value = Params.kdeWidthForOnePoint;  % bandwidth for KDE (in half violin plots) if there is only a single data point 
app.IncludechannelnumberinplotsCheckBox.Value = Params.includeChannelNumberInPlots;  % whether to plot channel ID in heatmaps and node plots

app.CustomGroupOrderEditField.Value = strjoin(Params.customGrpOrder, ',');


%% Dimensionality Analysis
% app.IncludeNMFcomponentsCheckBox.Value = Params.includeNMFcomponents;

%% Suite2p settings 
if isfield(Params, 'twopActivity')
    app.ActivityDropDown.Value = Params.twopActivity;
end 

%% Pipeline settings 

app.TimeprocessesCheckBox.Value = Params.timeProcesses;
app.VerboseLevelDropDown.Value = Params.verboseLevel;

end

