%% Advanced settings for batchInterface (only modify if you know what you are doing)

%% Output folder settings 
if any(isnan(Params.outputDataFolder)) || isempty(Params.outputDataFolder)
    Params.outputDataFolder = HomeDir;
end 
%% Spike detection settings
Params.threshold_calculation_window = [0, 1.0];  % which part of the recording to do spike detection, 0 = start of recording, 0.5 = midway, 1 = end of recording
% params.absThresholds = {''};  % add absolute thresholds here % TODO:
% double check this works, and allow for this to be empty so it does not have to be commented out 
% params.subsample_time = [1, 60];  % which part of the recording to subsample for spike detection (In seconds)
% if unspecified, then uses the entire recording
Params.run_detection_in_chunks = 0; % whether to run wavelet detection in chunks (0: no, 1:yes)
Params.chunk_length = 60;  % in seconds, will be ignored if run_detection_in_chunks = 0

Params.multiplier = 3.5; % multiplier to use extracting spikes for wavelet (not for detection)

% HSBSCAN is currently not used (and multiple_templates is not used to
% simplify things)
% adding HDBSCAN path (please specify your own path to HDBSCAN)
% currentScriptPath = matlab.desktop.editor.getActiveFilename;
% currFolder = fileparts(currentScriptPath);
% addpath(genpath([currFolder, filesep, 'HDBSCAN']));

% Uncomment this if you want to use custom threshold from a particular file
% params.custom_threshold_file = load(fullfile(dataPath, 'results', ...
% 'Organoid 180518 slice 7 old MEA 3D stim recording 3_L_-0.3_spikes_threshold_ref.mat'));

Params.custom_threshold_method_name = {'thr4p5'};
Params.remove_artifacts = 0;
Params.nScales = 5;
Params.wid = [0.4000 0.8000];
Params.grd = [];
Params.unit = 's';
Params.minPeakThrMultiplier = -5;
Params.maxPeakThrMultiplier = -100;
Params.posPeakThrMultiplier = 15;

% Refractory period (for spike detection and adapting template) (ms)
Params.refPeriod = 1; 
Params.getTemplateRefPeriod = 2;

Params.nSpikes = 10000;
Params.multiple_templates = 0; % whether to get multiple templates to adapt (1: yes, 0: no)
Params.multi_template_method = 'amplitudeAndWidthAndSymmetry';  % options are PCA, spikeWidthAndAmplitude, or amplitudeAndWidthAndSymmetry
 
% Filtering low and high pass frequencies 
Params.filterLowPass = 600;
Params.filterHighPass = 8000;

if Params.filterHighPass > Params.fs / 2
    fprintf(['WARNING: high pass frequency specified is above \n ', ...
        'nyquist frequency for given sampling rate, reducing it \n ' ...
        sprintf('to a frequency of %.f \n', Params.fs/2-100)])
    Params.filterHighPass = Params.fs/2-100;
end 

option = 'list';

%% Spike detection plots settings 

% Params.rasterPlotUpperPercentile determines the colorbar 
% y axis upper percentile (spikes/s) 
% 99 : prevent outliers dominating the plot, 100 : scale to the max (for
% low firing rate)
Params.rasterPlotUpperPercentile = 99;  

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
% set to 0 to disable plotting of KDE if there is only a single data point,
% and set to a positive number for a custom bandwidth, or set to 'auto', in
% which case the bandwidth will be determined automatically by ksdensity(),
% see HalfViolinPlot.m for more details

% Coordinates of each channel / node 
% Please specify coordinates such that 
% for x : 0 (left) to 1 (right)
% for y : 0 (bottom) to 1 (top)
% note that the coordinates will be multiplied by 8 for plotting purposes, 
% please do not remove that line

% Default mutichannel systems 8 x 8 layout
%
Params.includeChannelNumberInPlots = 0;  % whether to plot channel ID in heatmaps and node plots

[Params.channels,Params.coords] = getCoordsFromLayout(Params.channelLayout);

%% Plotting : colormap settings 
% Network plot colormap bounds 
Params.use_theoretical_bounds = 0;
Params.use_min_max_all_recording_bounds = 0;
Params.use_min_max_per_genotype_bounds = 0;

if Params.use_theoretical_bounds
    network_plot_cmap_bounds = struct();
    network_plot_cmap_bounds.CC = [0, 1];
    network_plot_cmap_bounds.PC = [0, 1];
    network_plot_cmap_bounds.Z = [-2, 2];
    network_plot_cmap_bounds.BC = [0, 1];
    network_plot_cmap_bounds.Eloc = [0, 1];
    network_plot_cmap_bounds.aveControl = [1, 1.5];
    network_plot_cmap_bounds.modalControl = [0.7, 1]; 
    Params.network_plot_cmap_bounds = network_plot_cmap_bounds;
else 
    het_node_level_vals = 0;
    if Params.use_min_max_all_recording_bounds
        
    elseif Params.use_min_max_per_genotype_bounds

    end 
end 

%% Plotting : ordering of groups for statistical summary plots 
% Params.customGrpOrder = {'WT', 'HE', 'KO'} ; % eg. {'WT', 'HE', 'KO'};  % leave as empty {} if to use default alphabetical order
Params.customGrpOrder = {} ; 

%% Plotting : stats summary settings 
Params.includeNotBoxPlots = 0;
Params.linePlotShadeMetric = 'sem';  % 'std' or 'sem'

%% Network analysis settings 
Params.netMetToCal = {'ND', 'EW', 'NS', 'aN', 'Dens', 'Ci', 'Q', 'nMod', 'Eglob', ...,
        'CC', 'PL' 'SW','SWw' 'Eloc', 'BC', 'PC' , 'PC_raw', 'Cmcblty', 'Z', ...
        'NE', 'effRank', 'num_nnmf_components', 'nComponentsRelNS', ...
        'aveControl', 'modalControl'};
% Other optional ones: SA_lambda, SA_inf, TA_regional, TA_global
 
Params.excludeEdgesBelowThreshold = 1;
Params.minNumberOfNodesToCalNetMet = 25;  % minimum number of nodes to calculate BC and other metrics
Params.networkLevelNetMetToPlot = ...
    {'aN','Dens','CC','nMod','Q','PL','Eglob', ...
    'SW','SWw', 'effRank', ...
    'num_nnmf_components', 'nComponentsRelNS', ...
    'NDmean', 'NDtop25', ...
    'sigEdgesMean', 'sigEdgesTop10', ...
    'NSmean', 'ElocMean', ... 
    'PCmean', 'PCmeanTop10', 'PCmeanBottom10', ...
    'percentZscoreGreaterThanZero', 'percentZscoreLessThanZero', ...
    };  % which network metric to plot at the network level 
Params.networkLevelNetMetLabels = {
    'network size', ... 
    'density','clustering coefficient', ...
    'number of modules', ... 
    'modularity score', ...
    'path length', ...
    'global efficiency', ...
    'small worldness \sigma', ... 
    'small worldness \omega', ...
    'Effective rank', ...
    'Num NMF components', 'nNMF div network size', ...
    'Node degree mean', 'Top 25% node degree', ...
    'Significant edge weight mean', 'Top 10% edge weight mean', ...
    'Node strength mean', 'Local efficiency mean', ... 
    'Participant coefficient (PC) mean', 'Top 10% PC', 'Bottom 10% PC', ... 
    'Percentage within-module z-score > 0', 'Percentage within-module z-score < 0', ...
    };
Params.networkLevelNetMetCustomBounds = struct();

% Set custom axis limits that matches with what can theoretically be
% obtained (This applies to the group comparison violin plots)
Params.networkLevelNetMetCustomBounds.('effRank') = [1, nan];
Params.networkLevelNetMetCustomBounds.('Dens') = [0, 1];  % density
Params.networkLevelNetMetCustomBounds.('num_nnmf_components') = [1, nan];
Params.networkLevelNetMetCustomBounds.('aveControl') = [1, 1.5];
Params.networkLevelNetMetCustomBounds.('modalControl') = [0.6, 1];
Params.networkLevelNetMetCustomBounds.('ND') = [0, length(Params.channels) -1];
Params.networkLevelNetMetCustomBounds.('Eloc') = [0, nan];
Params.networkLevelNetMetCustomBounds.('EW') = [0, nan];
Params.networkLevelNetMetCustomBounds.('NS') = [0, nan];
Params.networkLevelNetMetCustomBounds.('BC') = [0, 1];
Params.networkLevelNetMetCustomBounds.('CC') = [0, nan];
Params.networkLevelNetMetCustomBounds.('nMod') = [0, nan];
Params.networkLevelNetMetCustomBounds.('Q') = [0, nan];
Params.networkLevelNetMetCustomBounds.('PL') = [0, nan];
Params.networkLevelNetMetCustomBounds.('Eglob') = [0, 1];
Params.networkLevelNetMetCustomBounds.('effRank') = [1, length(Params.channels)];
Params.networkLevelNetMetCustomBounds.('nComponentsRelNS') = [0, 1];

Params.unitLevelNetMetToPlot = {'ND','MEW','NS','Z','Eloc','PC','BC', 'aveControl', 'modalControl'};
Params.unitLevelNetMetLabels = {'node degree','edge weight','node strength', ... 
    'within-module degree z-score', ... 
    'local efficiency','participation coefficient','betweeness centrality', ...
    'average controllability', 'modal controllability'}; 

Params.includeNMFcomponents = 0;  % whether to save extracted components and original downsampled data

% specify whether to include network plots scaled to all recordings 
Params.includeNetMetScaledPlots = 1;

%% Optional step : statistics and classification 
Params.pValThreshold = 0.01;  % p value threshold to consider effect as significant

%% Troubleshooting / Diagnostic settings 

Params.timeProcesses = 0; % whether to log how long each process took

