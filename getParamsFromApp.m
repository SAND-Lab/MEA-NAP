function  Params = getParamsFromApp(app)
%UNTITLED2 Summary of this function goes here
%   Detailed explanation goes here

Params.HomeDir = app.HomeDirectoryEditField.Value;
Params.outputDataFolder = app.OutputDataFolderEditField.Value;
Params.rawData = app.RawDataFolderEditField.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.spikeDetectedData = app.SpikeDataFolderEditField.Value;
Params.spreadSheetFileName = app.SpreadsheetfilenameEditField.Value;

Params.fs = app.SamplingFrequencyEditField.Value;
Params.dSampF = app.DownSampleFrequencyEditField.Value;
Params.potentialDifferenceUnit = app.PotentialDifferenceUnitEditField.Value;
Params.channelLayout = app.ChannelLayoutDropDown.Value;
thresholdsArray = str2num(app.ThresholdsEditField.Value);
Params.thresholds = cellstr(string(thresholdsArray));
Params.wnameList = cellstr(app.WaveletsListBox.Value); %  {'bior1.5'}; % wavelet methods to use {'bior1.5', 'mea'}; 
Params.costList = str2double(app.WaveletCostEditField.Value);
Params.SpikesMethod = app.SpikeMethodforAnalysisEditField.Value;  % wavelet methods, eg. 'bior1p5', or 'mergedAll', or 'mergedWavelet'

% Functional connectivity inference settings
Params.FuncConLagval = str2num(app.LagvaluesEditField.Value); % set the different lag values (in ms), default to [10, 15, 25]
Params.TruncRec = app.TruncateRecordingCheckBox.Value; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = app.TruncationlengthsecEditField.Value; % length of truncated recordings (in seconds)
Params.adjMtype = lower(app.AdjacencymatrixtypeButtonGroup.SelectedObject.Text); % 'weighted'; % 'weighted' or 'binary'

% Connectivity matrix thresholding settings
Params.ProbThreshRepNum = app.ProbthresholdingrepeatsEditField.Value; % probabilistic thresholding number of repeats 
Params.ProbThreshTail = app.ProbthresholdingtailEditField.Value; % probabilistic thresholding percentile threshold 
Params.ProbThreshPlotChecks = app.PlotprobthresholdingchecksCheckBox.Value; % randomly sample recordings to plot probabilistic thresholding check, 1 = yes, 0 = no
Params.ProbThreshPlotChecksN = app.ProbthresholdingnumchecksEditField.Value; % number of random checks to plot

% Node cartography settings 
Params.autoSetCartographyBoudariesPerLag = app.AutomaticallysetnodecartographyboundariesperlagCheckBox.Value;  % whether to fit separate boundaries per lag value
Params.cartographyLagVal = str2num(app.NodecartographylagvaluesEditField.Value); % lag value (ms) to use to calculate PC-Z distribution (only applies if Params.autoSetCartographyBoudariesPerLag = 0)
Params.autoSetCartographyBoundaries = app.AutomaticallysetnodecartographyboundariesCheckBox.Value;  % whether to automatically determine bounds for hubs or use custom ones


% use previously analysed data?
Params.priorAnalysis = app.UsePreviousAnalysisCheckBox.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.priorAnalysisDate = app.PreviousAnalysisDateEditField.Value;

Params.startAnalysisStep = app.StartAnalysisStepEditField.Value;
Params.optionalStepsToRun = app.OptionalStepstoRunListBox.Value;

% run spike detection?
Params.detectSpikes = app.DetectSpikesCheckBox.Value;
Params.runSpikeCheckOnPrevSpikeData = app.RunspikecheckonpreviousspikedataCheckBox.Value;

% show one figure 
Params.showOneFig = app.DisplayonlyonefigureCheckBox.Value;
figExts = app.FigureformatsListBox.Value;
for figExtIndex = 1:length(figExts)
    figExts{figExtIndex} = ['.' figExts{figExtIndex}];
end 
Params.figExt = figExts;
Params.fullSVG = app.DonotcompressSVGCheckBox.Value;

%%%%%%%%%%%%%%%%%%%%%%%%% ADVANCED SETTINGS %%%%%%%%%%%%%%%%%%%%
Params.run_detection_in_chunks = app.RundetectioninchunksCheckBox.Value; % whether to run wavelet detection in chunks (0: no, 1:yes)
Params.chunk_length = app.ChunklengthsecEditField.Value;  % in seconds, will be ignored if run_detection_in_chunks = 0
Params.multiplier = app.WaveletmultiplierEditField.Value; % multiplier to use extracting spikes for wavelet (not for detection)

Params.custom_threshold_method_name = {'thr4p5'};
Params.remove_artifacts = app.RemoveartifactsCheckBox.Value;
Params.nScales = app.WaveletnScalesEditField.Value;
waveletWid = app.WaveletwidEditField.Value;  % TODO: convert this to array
Params.wid = str2num(waveletWid);  
Params.grd = [];
Params.unit = app.TimeUnitEditField.Value;
Params.minPeakThrMultiplier = app.MinimumspikepeakmultiplierEditField.Value;
Params.maxPeakThrMultiplier = app.MaximumspikepeakmultiplierEditField.Value;
Params.posPeakThrMultiplier = app.MaximumpositivepeakmultiplierEditField.Value;

% Refractory period (for spike detection and adapting template) (ms)
Params.refPeriod = app.SpikerefractoryperiodmsEditField.Value;
Params.getTemplateRefPeriod = app.TemplaterefractoryperiodmsEditField.Value;

Params.nSpikes = app.MaxNSpikestomaketemplateEditField.Value;
Params.multiple_templates = app.AdaptmultipletemplatesCheckBox.Value; % whether to get multiple templates to adapt (1: yes, 0: no)
Params.multi_template_method = app.MultipletemplatemethodDropDown.Value;  % options are PCA, spikeWidthAndAmplitude, or amplitudeAndWidthAndSymmetry
 
% Filtering low and high pass frequencies 
Params.filterLowPass = app.LowpassfilterHzEditField.Value;
Params.filterHighPass = app.HighpassfilterHzEditField.Value;

%% Raster plot 
Params.rasterPlotUpperPercentile = app.RasterMapUpperPercentileEditField.Value;

%% Burst detection settings 
Params.networkBurstDetectionMethod = app.BurstDetectionMethodDropDown.Value; % supported methods: 'Bakkum', 'Manuel', 'LogISI', 'nno'
Params.minSpikeNetworkBurst = app.MinspikepernetworkburstEditField.Value;
Params.minChannelNetworkBurst = app.MinchannelpernetworkburstEditField.Value;
Params.bakkumNetworkBurstISInThreshold = app.BakkumNetworkBurstThresholdEditField.Value; % either 'automatic' or a number in seconds

Params.singleChannelBurstDetectionMethod = app.SingleChanenlBurstDetectionDropDown.Value; % supported methods: 'Bakkum'
Params.singleChannelBurstMinSpike = app.MinspikeperchannelburstEditField.Value;

%% Dimensionality calculation settings 
Params.effRankCalMethod = app.effRankCalculationMethodDropDown.Value;
Params.NMFdownsampleFreq = app.NMFDownsamplingFrequencyHzEditField.Value;   % how mucn to downsample the spike matrix to (Hz) before doing non-negative matrix factorisation

%% Node cartography settings 
Params.hubBoundaryWMdDeg = app.hubBoundaryWMdDegEditField.Value; % boundary that separates hub and non-hubs (default 2.5)
Params.periPartCoef = app.periPartCoefEditField.Value; % boundary that separates peripheral node and none-hub connector (default: 0.625)
Params.proHubpartCoef = app.proHubpartCoefEditField.Value; % boundary that separates provincial hub and connector hub (default: 0.3)
Params.nonHubconnectorPartCoef = app.nonHubconnectorPartCoefEditField.Value; % boundary that separates non-hub connector and non-hub kinless node (default: 0.8)
Params.connectorHubPartCoef = app.connectorHubPartCoefEditField.Value;  % boundary that separates connector hub and kinless hub (default 0.75)

%% Plotting settings

% colors to use for each group in group comparison plots
% this should be an nGroup x 3 matrix where nGroup is the number of groups
% you have, and each row is a RGB value (scaled from 0 to 1) denoting the
% color
Params.groupColors = app.colorUITable.Data(:, 1:end);

Params.minNodeSize = app.MinimumnodesizeEditField.Value;  % minimum node size in network plots
Params.kdeHeight = app.KDEHeightEditField.Value;  % height of the KDE curve, only affects plotting and not the kernel density estimate itself
Params.kdeWidthForOnePoint = app.KDEwidthforonepointEditField.Value;  % bandwidth for KDE (in half violin plots) if there is only a single data point 
Params.includeChannelNumberInPlots = app.IncludechannelnumberinplotsCheckBox.Value;  % whether to plot channel ID in heatmaps and node plots

%% Pipeline settings 
Params.timeProcesses = app.TimeprocessesCheckBox.Value;
Params.verboseLevel = app.VerboseLevelDropDown.Value;

%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
Params.showAdvancedSetting = app.ShowAdvancedSettingsCheckBox.Value; 

end