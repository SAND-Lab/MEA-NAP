function  Params = getParamsFromApp(app)
%getParamsFromApp Sets the parameters from GUI input
%   INPUT 
%   app : app object 
%   OUTPUT
%   Params : struct

Params.HomeDir = app.MEANAPFolderEditField.Value;
Params.outputDataFolder = app.OutputDataFolderEditField.Value;
Params.rawData = app.RawDataFolderEditField.Value;
Params.priorAnalysisPath = app.PreviousAnalysisFolderEditField.Value;
Params.spikeDetectedData = app.SpikeDataFolderEditField.Value;
Params.spreadSheetFileName = app.SpreadsheetFilenameEditField.Value;
Params.spreadSheetRange = app.SpreadsheetRangeEditField.Value;

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
Params.FuncConLagval = str2num(app.STTCLagmsEditField.Value); % set the different lag values (in ms), default to [10, 15, 25]
Params.TruncRec = app.TruncateRecordingCheckBox.Value; % truncate recording? 1 = yes, 0 = no
Params.TruncLength = app.TruncationlengthsecEditField.Value; % length of truncated recordings (in seconds)
Params.adjMtype = lower(app.AdjacencymatrixtypeButtonGroup.SelectedObject.Text); % 'weighted'; % 'weighted' or 'binary'

% Connectivity matrix thresholding settings
Params.ProbThreshRepNum = app.ProbthresholdingiterationsEditField.Value; % probabilistic thresholding number of repeats 
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

% Spike detected data location 
Params.spikeDetectedData = app.SpikeDataFolderEditField.Value;

% show one figure 
Params.showOneFig = app.DisplayonlyonefigureCheckBox.Value;
figExts = app.FigureformatsListBox.Value;
for figExtIndex = 1:length(figExts)
    figExts{figExtIndex} = ['.' figExts{figExtIndex}];
end 
Params.figExt = figExts;
Params.fullSVG = app.DonotcompressSVGCheckBox.Value;

% Colormap settings
Params.use_theoretical_bounds = app.UsetheoreticalboundsCheckBox.Value; 
Params.use_min_max_all_recording_bounds = app.UseminmaxallrecordingboundsCheckBox.Value;
Params.use_min_max_per_genotype_bounds = app.UseminmaxpergroupboundsCheckBox.Value;

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

if Params.filterHighPass > Params.fs / 2
    fprintf(['WARNING: high pass frequency specified is above \n ', ...
        'nyquist frequency for given sampling rate, reducing it \n ' ...
        sprintf('to a frequency of %.f \n', Params.fs/2-100)])
    Params.filterHighPass = Params.fs/2-100;
end 
%% Which network metrics to calculate and plot 
Params.netMetToCal = app.NetworkmetricstocalculateListBox.Value;

%% Network analysis 
Params.excludeEdgesBelowThreshold = app.ExcludeedgesbelowthresholdCheckBox.Value; 
Params.minNumberOfNodesToCalNetMet = app.MinimumnumberofnodesEditField.Value;

Params.NetMetLabelDict = {
    'aN',  'network size', 'network'; ...  
    'Dens', 'density', 'network'; ...
    'CC', 'clustering coefficient', 'network'; ...
    'nMod', 'number of modules', 'network'; ...
    'Q', 'modularity score', 'network'; ...
    'PL', 'mean path length', 'network'; ...
    'Eglob', 'global efficiency', 'network'; ...
    'SW', 'small worldness \sigma', 'network'; ...
    'SWw', 'small worldness \omega', 'network'; ...
    'effRank', 'Effective rank', 'network'; ...
    'num_nnmf_components', 'Num NMF components', 'network'; ...
    'nComponentsRelNS', 'nNMF div network size', 'network'; ...
    'NDmean', 'Node degree mean', 'network'; ...
    'NDtop25', 'Top 25% node degree', 'network'; ...
    'sigEdgesMean', 'Significant edge weight mean', 'network'; ...  
    'sigEdgesTop10', 'Top 10% edge weight mean', 'network'; ... 
    'NSmean', 'Node strength mean', 'network'; ... 
    'ElocMean', 'Local efficiency mean', 'network'; ... 
    'PCmean', 'Participant coefficient (PC) mean', 'network'; ... 
    'PCmeanTop10', 'Top 10% PC', 'network'; ... 
    'PCmeanBottom10', 'Bottom 10% PC', 'network'; ...
    'percentZscoreGreaterThanZero',  'Percentage within-module z-score > 0', 'network'; ...
    'percentZscoreLessThanZero', 'Percentage within-module z-score < 0', 'network'; ...
    'NCpn1', 'NC1PeripheralNodes', 'network'; ... 
    'NCpn2', 'NC2NonhubConnectors', 'network'; ... 
    'NCpn3', 'NC3NonhubKinless', 'network'; ... 
    'NCpn4', 'NC4ProvincialHubs', 'network'; ...
    'NCpn5', 'NC5ConnectorHubs', 'network'; ... 
    'NCpn6', 'NC6KinlessHubs', 'network'; ... 
    'aveControlMean', 'Mean average controllability', 'network'; ... 
    'modalControlMean', 'Mean modal controllability', 'network'; ... 
    'aveControl', 'Average Controllability', 'node'; ...
    'modalControl', 'Modal Controllability', 'node'; ...
    'ND', 'node degree', 'node'; ...
    'MEW','edge weight', 'node'; ...
    'NS', 'node strength', 'node'; ...
    'Z',  'within-module degree z-score', 'node'; ...
    'Eloc', 'local efficiency', 'node'; ...
    'PC', 'participation coefficient', 'node'; ...
    'BC', 'betweenness centrality', 'node'; ...
};

networkMetricIndices = find(strcmp({Params.NetMetLabelDict{:, 3}}, 'network'));
nodeMetricsIndices = find(strcmp({Params.NetMetLabelDict{:, 3}}, 'node'));

Params.networkLevelNetMetToPlot = intersect(Params.netMetToCal, {Params.NetMetLabelDict{networkMetricIndices, :}});
Params.unitLevelNetMetToPlot = intersect(Params.netMetToCal, {Params.NetMetLabelDict{nodeMetricsIndices, :}});

Params.networkLevelNetMetLabels = {};
Params.unitLevelNetMetLabels = {};

for netMetIdx = 1:length(Params.networkLevelNetMetToPlot)
    netMetName = Params.networkLevelNetMetToPlot{netMetIdx};
    labelNameIdx = find(strcmp({Params.NetMetLabelDict{:, 1}}, netMetName));
    labelName = Params.NetMetLabelDict{labelNameIdx, 2};
    Params.networkLevelNetMetLabels{end+1} = labelName;
end

for netMetIdx = 1:length(Params.unitLevelNetMetToPlot)
    netMetName = Params.unitLevelNetMetToPlot{netMetIdx};
    labelNameIdx = find(strcmp({Params.NetMetLabelDict{:, 1}}, netMetName));
    labelName = Params.NetMetLabelDict{labelNameIdx, 2};
    Params.unitLevelNetMetLabels{end+1} = labelName;
end

Params.networkLevelNetMetCustomBounds = struct();

% add all relevant folders to path
cd(Params.HomeDir)
addpath(genpath('Functions'))
addpath('Images')
[Params.channels, Params.coords] = getCoordsFromLayout(Params.channelLayout);

% Set custom axis limits that matches with what can theoretically be
% obtained (This applies to the group comparison violin plots)
Params.networkLevelNetMetCustomBounds.('effRank') = [1, nan];
Params.networkLevelNetMetCustomBounds.('Dens') = [0, 1];  % density
Params.networkLevelNetMetCustomBounds.('num_nnmf_components') = [1, nan];
Params.networkLevelNetMetCustomBounds.('aveControl') = [1, 1.5];
Params.networkLevelNetMetCustomBounds.('modalControl') = [0.6, 1];
Params.networkLevelNetMetCustomBounds.('ND') = [0, (length(Params.channels) - 1)];
Params.networkLevelNetMetCustomBounds.('Eloc') = [0, 1];
Params.networkLevelNetMetCustomBounds.('EW') = [0, 1];
Params.networkLevelNetMetCustomBounds.('NS') = [0, nan];
Params.networkLevelNetMetCustomBounds.('BC') = [0, 1];
Params.networkLevelNetMetCustomBounds.('PC') = [0, 1];
Params.networkLevelNetMetCustomBounds.('CC') = [0, nan];
Params.networkLevelNetMetCustomBounds.('nMod') = [0, nan];
Params.networkLevelNetMetCustomBounds.('Q') = [0, nan];
Params.networkLevelNetMetCustomBounds.('PL') = [0, nan];
Params.networkLevelNetMetCustomBounds.('Eglob') = [0, 1];
Params.networkLevelNetMetCustomBounds.('effRank') = [1, length(Params.channels)];
Params.networkLevelNetMetCustomBounds.('nComponentsRelNS') = [0, 1];
Params.networkLevelNetMetCustomBounds.('NDmean') = [0, nan];
Params.networkLevelNetMetCustomBounds.('NDtop25') = [0, nan];
Params.networkLevelNetMetCustomBounds.('sigEdgesMean') = [0, nan];
Params.networkLevelNetMetCustomBounds.('sigEdgesTop10') = [0, nan];
Params.networkLevelNetMetCustomBounds.('NSmean') = [0, nan];
Params.networkLevelNetMetCustomBounds.('ElocMean') = [0, 1];
Params.networkLevelNetMetCustomBounds.('PCmean') = [0, 1];
Params.networkLevelNetMetCustomBounds.('PCmeanTop10') = [0, 1];
Params.networkLevelNetMetCustomBounds.('PCmeanBottom10') = [0, 1];

Params.lagIndependentMets = {'effRank', 'num_nnmf_components', 'nComponentsRelNS'};

% Params.unitLevelNetMetToPlot = {'ND','MEW','NS','Z','Eloc','PC','BC'};
% 'aveControl', 'modalControl'
% Params.unitLevelNetMetLabels = {'node degree','edge weight','node strength', ... 
%     'within-module degree z-score', ... 
%     'local efficiency','participation coefficient','betweenness centrality'};

%% Colormap settings 

% Network plot colormap bounds 
Params.use_custom_bounds = 0;  % Default value: 0
Params.use_min_max_all_recording_bounds = 0;
Params.use_min_max_per_genotype_bounds = 0;

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
Params.effRankDownsampleFreq = 10; 
Params.NMFdownsampleFreq = app.NMFDownsamplingFrequencyHzEditField.Value;   % how much to downsample the spike matrix to (Hz) before doing non-negative matrix factorisation
Params.includeNMFcomponents = app.IncludeNMFcomponentsCheckBox.Value;


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
Params.groupColors = app.colorUITable.Data(:, 2:end);

Params.minNodeSize = app.MinimumnodesizeEditField.Value;  % minimum node size in network plots
Params.kdeHeight = app.KDEHeightEditField.Value;  % height of the KDE curve, only affects plotting and not the kernel density estimate itself
Params.kdeWidthForOnePoint = app.KDEwidthforonepointEditField.Value;  % bandwidth for KDE (in half violin plots) if there is only a single data point 
Params.includeChannelNumberInPlots = app.IncludechannelnumberinplotsCheckBox.Value;  % whether to plot channel ID in heatmaps and node plots

Params.includeNotBoxPlots = app.IncludeNotBoxPlotsCheckBox.Value;

Params.linePlotShadeMetric = 'sem';  % 'std' or 'sem'

%% Pipeline settings 
Params.timeProcesses = app.TimeprocessesCheckBox.Value;
Params.verboseLevel = app.VerboseLevelDropDown.Value;

%%%%%%%%%%%%%%%%%%%%%%%%%% GUI SPECIFIC SETTINGS %%%%%%%%%%%%%%%%%%%%%%%
Params.showAdvancedSetting = app.ShowAdvancedSettingsCheckBox.Value; 

end