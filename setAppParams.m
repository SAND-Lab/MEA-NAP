function app = setAppParams(app, Params)
%SETAPPPARAMS Load saved parameterse and add them to GUI
%   Detailed explanation goes here


app.MEANAPFolderEditField.Value = Params.HomeDir;
app.OutputDataFolderEditField.Value = Params.outputDataFolder;
app.RawDataFolderEditField.Value = Params.rawData;

app.PreviousAnalysisFolderEditField.Value = Params.priorAnalysisPath;
app.UsePreviousAnalysisCheckBox.Value = Params.priorAnalysis;
app.PreviousAnalysisDateEditField.Value = Params.priorAnalysisDate;

app.SpikeDataFolderEditField.Value = Params.spikeDetectedData;
app.SpreadsheetFilenameEditField.Value = Params.spreadSheetFileName;
app.StartAnalysisStepEditField.Value = Params.startAnalysisStep;

% Spike Detection 
app.DetectSpikesCheckBox.Value = Params.detectSpikes;
app.RunspikecheckonpreviousspikedataCheckBox.Value = Params.runSpikeCheckOnPrevSpikeData;

%% Connectivity settings 
app.STTCLagmsEditField.Value = num2str(Params.FuncConLagval);

%% Network analysis settings 
app.NetworkmetricstocalculateListBox.Value = Params.netMetToCal;

%% Plotting settings

% colors to use for each group in group comparison plots
% this should be an nGroup x 3 matrix where nGroup is the number of groups
% you have, and each row is a RGB value (scaled from 0 to 1) denoting the
% color
app.colorUITable.Data(:, 1:end) = Params.groupColors;

app.MinimumnodesizeEditField.Value = Params.minNodeSize;  % minimum node size in network plots
app.KDEHeightEditField.Value = Params.kdeHeight;  % height of the KDE curve, only affects plotting and not the kernel density estimate itself
app.KDEwidthforonepointEditField.Value = Params.kdeWidthForOnePoint;  % bandwidth for KDE (in half violin plots) if there is only a single data point 
app.IncludechannelnumberinplotsCheckBox.Value = Params.includeChannelNumberInPlots;  % whether to plot channel ID in heatmaps and node plots

% show one figure 
app.DisplayonlyonefigureCheckBox.Value = Params.showOneFig;

for ext_i = 1:length(Params.figExt)
    figExtWithoutDot{ext_i} = Params.figExt{ext_i}(2:end);
end
app.FigureformatsListBox.Value = figExtWithoutDot;
% for figExtIndex = 1:length(figExts)
%     figExts{figExtIndex} = ['.' figExts{figExtIndex}];
% end 
app.DonotcompressSVGCheckBox.Value = Params.fullSVG ;

%% Dimensionality Analysis
% app.IncludeNMFcomponentsCheckBox.Value = Params.includeNMFcomponents;

%% Pipeline settings 

app.TimeprocessesCheckBox.Value = Params.timeProcesses;
app.VerboseLevelDropDown.Value = Params.verboseLevel;

%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
app.ShowAdvancedSettingsCheckBox.Value = Params.showAdvancedSetting;


end

