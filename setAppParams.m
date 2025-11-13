function app = setAppParams(app, Params)
%SETAPPPARAMS Load saved parameters and add them to GUI
% INPUTS 
% -------------------------
%  app : matlab app object 
%  Params : structure 
% OUTPUTS 
% ------------------------
%  app : matlab app object
%
% NOTES
% --------------------------- 
% Might be easier to store a lot of these into a table / cell array 
% of Parameter names and GUI names, to loop through these pairs
% Some of them may need an indicator (binary vector for example) for 
% special cases, eg. for dealing with vectors using strjoin()

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

if isfield(Params, 'minActivityLevel')
    % minimum activity level to be considered active node 
    app.MinactivitylevelspikessEditField.Value = Params.minActivityLevel;
end 

%% Burst detection settings 
if isfield(Params, 'singleChannelIsiThreshold')
    app.SinglechannelburstthresholdEditField.Value = Params.singleChannelIsiThreshold;
end

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
if isfield(Params, 'maxNodeSize')
    app.MaximumnodesizeEditField.Value = Params.maxNodeSize;
end

if isfield(Params, 'nodeScalingMethod')
    app.NodesizescalingDropDown.Value = Params.nodeScalingMethod;
end

if isfield(Params, 'nodeLayout')
    app.NodelayoutDropDown.Value = Params.nodeLayout;  
end

if isfield(Params, 'nodeScalingPower')
    app.NodescalingpowerEditField.Value = Params.nodeScalingPower;
end 

% Edge plotting settings 
if isfield(Params, 'networkPlotEdgeThresholdMethod')
    app.EdgethresholdmethodDropDown.Value = Params.networkPlotEdgeThresholdMethod;
end
if isfield(Params, 'networkPlotEdgeThresholdPercentile') 
    app.EdgeweightpercentileEditField.Value = Params.networkPlotEdgeThresholdPercentile;
end
if isfield(Params, 'networkPlotEdgeThreshold')
     app.MinedgeweightEditField.Value = Params.networkPlotEdgeThreshold; 
end
if isfield(Params, 'maxNumEdgesToPlot')
    app.MaximumedgesEditField.Value = Params.maxNumEdgesToPlot;
end
if isfield(Params, 'maxNumEdgesToPlot')
    app.EdgesubsamplingmethodDropDown.Value = Params.edgeSubsamplingMethod;
end 

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

if isfield(Params, 'removeNodesWithNoPeaks')
    app.RemovenodeswithnopeaksCheckBox.Value = Params.removeNodesWithNoPeaks;
end 

if isfield(Params, 'num2ptraces')
   app.CellstoplotperrecordingEditField.Value = Params.num2ptraces;
end 

%% Stimulation analysis 
if isfield(Params, 'stimulationMode')
     app.StimulationmodeCheckBox.Value = Params.stimulationMode;
end

if isfield(Params, 'automaticStimDetection')
     app.AutomaticstimdetectionCheckBox.Value = Params.automaticStimDetection;
end

if isfield(Params, 'stimDetectionMethod')
    app.StimdetectionmethodDropDown.Value = Params.stimDetectionMethod;
end

if isfield(Params, 'stimDetectionVal')
    app.DetectionthresholdmultiplierEditField.Value = Params.stimDetectionVal;
end 

if isfield(Params, 'stimRefractoryPeriod')
    app.StimrefractoryperiodsEditField.Value = Params.stimRefractoryPeriod;
end

if isfield(Params, 'stimDuration')
    app.StimdurationsEditField.Value = Params.stimDuration;
end

if isfield(Params, 'stimDurationForPlotting')
    app.StimdurationforplotssEditField.Value = Params.stimDurationForPlotting ;
end

% if isfield(Params, 'preStimWindow')
%     app.PrestimwindowsEditField.Value = string(['[', strjoin(cellstr(string(Params.preStimWindow)), ', '), ']']);
% end

% if isfield(Params, 'postStimWindow')
%     app.PoststimwindowsEditField.Value = string(['[', strjoin(cellstr(string(Params.postStimWindow)), ', '), ']']);
% end

% if isfield(Params, 'stimRemoveSpikesWindow')
%     app.StimignorespikeswindowsEditField.Value = string(['[', strjoin(cellstr(string(Params.stimRemoveSpikesWindow)), ', '), ']']);
% end



if isfield(Params, 'stimRawDataProcessing')
    app.StimdataprocessingDropDown.Value = Params.stimRawDataProcessing;
end

%% Pipeline settings 

app.TimeprocessesCheckBox.Value = Params.timeProcesses;
app.VerboseLevelDropDown.Value = Params.verboseLevel;

end

