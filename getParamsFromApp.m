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

% use previously analysed data?
Params.priorAnalysis = app.UsePreviousAnalysisCheckBox.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.priorAnalysisDate = app.PreviousAnalysisDateEditField.Value;

Params.startAnalysisStep = app.StartAnalysisStepEditField.Value;

% run spike detection?
Params.detectSpikes = app.DetectSpikesCheckBox.Value;

%%%%%%%%%%%%%%%%%%%%%%%%% ADVANCED SETTINGS %%%%%%%%%%%%%%%%%%%%
Params.run_detection_in_chunks = app.RundetectioninchunksCheckBox.Value; % whether to run wavelet detection in chunks (0: no, 1:yes)
Params.chunk_length = app.ChunklengthsecEditField.Value;  % in seconds, will be ignored if run_detection_in_chunks = 0
Params.multiplier = app.WaveletmultiplierEditField.Value; % multiplier to use extracting spikes for wavelet (not for detection)

Params.custom_threshold_method_name = {'thr4p5'};
Params.remove_artifacts = app.RemoveartifactsCheckBox.Value;
Params.nScales = app.WaveletnScalesEditField.Value;
waveletWid = app.WaveletwidEditField.Value;  % TODO: convert this to array
Params.wid = [0.4000 0.8000];  
Params.grd = [];
Params.unit = app.TimeUnitEditField.Value;
Params.minPeakThrMultiplier = app.MinimumspikepeakmultiplierEditField.Value;
Params.maxPeakThrMultiplier = app.MaximumspikepeakmultiplierEditField.Value;
Params.posPeakThrMultiplier = app.MaximumpositivepeakmultiplierEditField.Value;

% Refractory period (for spike detection and adapting template) (ms)
Params.refPeriod = app.SpikerefractoryperiodmsEditField.Value;
Params.getTemplateRefPeriod = app.TemplaterefractoryperiodmsEditField.Value;

Params.nSpikes = app.MaxNSpikestomaketemplateEditField.Value;
Params.multiple_templates = 0; % whether to get multiple templates to adapt (1: yes, 0: no)
Params.multi_template_method = 'amplitudeAndWidthAndSymmetry';  % options are PCA, spikeWidthAndAmplitude, or amplitudeAndWidthAndSymmetry
 
% Filtering low and high pass frequencies 
Params.filterLowPass = app.LowpassfilterHzEditField.Value;
Params.filterHighPass = app.HighpassfilterHzEditField.Value;

%% Raster plot 
Params.rasterPlotUpperPercentile = app.RasterMapUpperPercentileEditField.Value;

%% Burst detection settings 
Params.networkBurstDetectionMethod = 'Bakkum'; % supported methods: 'Bakkum', 'Manuel', 'LogISI', 'nno'
Params.minSpikeNetworkBurst = 10;
Params.minChannelNetworkBurst = 3;
Params.bakkumNetworkBurstISInThreshold = 'automatic'; % either 'automatic' or a number in seconds

Params.singleChannelBurstDetectionMethod = 'Bakkum'; % supported methods: 'Bakkum'
Params.singleChannelBurstMinSpike = 10;

%% Dimensionality calculation settings 
Params.effRankCalMethod = 'covariance';
Params.NMFdownsampleFreq = 10;   % how mucn to downsample the spike matrix to (Hz) before doing non-negative matrix factorisation

%% Node cartography settings 
Params.hubBoundaryWMdDeg = 0.25; % boundary that separates hub and non-hubs (default 2.5)
Params.periPartCoef = 0.525; % boundary that separates peripheral node and none-hub connector (default: 0.625)
Params.proHubpartCoef = 0.45; % boundary that separates provincial hub and connector hub (default: 0.3)
Params.nonHubconnectorPartCoef = 0.8; % boundary that separates non-hub connector and non-hub kinless node (default: 0.8)
Params.connectorHubPartCoef = 0.75;  % boundary that separates connector hub and kinless hub (default 0.75)

%% Plotting settings

% colors to use for each group in group comparison plots
% this should be an nGroup x 3 matrix where nGroup is the number of groups
% you have, and each row is a RGB value (scaled from 0 to 1) denoting the
% color
Params.groupColors = [ ...
   0.996, 0.670, 0.318; ...
   0.780, 0.114, 0.114; ... 
   0.459, 0.000, 0.376; ...  
   0.027, 0.306, 0.659; ...
   0.5, 0.5, 0.5; ...
];

Params.minNodeSize = 0.1;  % minimum node size in network plots
Params.kdeHeight = 0.3;  % height of the KDE curve, only affects plotting and not the kernel density estimate itself
Params.kdeWidthForOnePoint = 0;  % bandwidth for KDE (in half violin plots) if there is only a single data point 
Params.includeChannelNumberInPlots = 0;  % whether to plot channel ID in heatmaps and node plots

%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
Params.showAdvancedSetting = app.ShowAdvancedSettingsCheckBox.Value; 

end