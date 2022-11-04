%% Advanced settings for batchInterface (only modify if you know what you are doing)

%% Output folder settings 
Params.outputDataFolder = nan;  % specify the main folder to save output data to 
if isnan(Params.outputDataFolder)
    Params.outputDataFolder = HomeDir;
end 
%% Spike detection settings
Params.plotDetectionResults = 0;
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
Params.refPeriod = 0.2; 
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

%% Network analysis settings 
Params.netMetToCal = {'ND', 'EW', 'NS', 'aN', 'Dens', 'Ci', 'Q', 'nMod', 'Eglob', ...,
        'CC', 'PL' 'SW','SWw' 'Eloc', 'BC', 'PC' , 'PC_raw', 'Cmcblty', 'Z', ...
        'Hub4','Hub3', 'NE', 'effRank', 'num_nnmf_components', 'nComponentsRelNS', ...
        'aveControl', 'modalControl'};
Params.excludeEdgesBelowThreshold = 1;
Params.minNumberOfNodesToCalNetMet = 25;  % minimum number of nodes to calculate BC and other metrics
Params.networkLevelNetMetToPlot = {'aN','Dens','CC','nMod','Q','PL','Eglob', ...
    'SW','SWw','Hub3','Hub4', 'effRank', ...
    'num_nnmf_components', 'nComponentsRelNS'};  % which network metric to plot at the network level 
Params.networkLevelNetMetLabels = {
    'network size', ... 
    'density','clustering coefficient', ...
    'number of modules', ... 
    'modularity score', ...
    'path length', ...
    'global efficiency', ...
    'small worldness \sigma', ... 
    'small worldness \omega', ...
    'hub nodes 2','hub nodes 1', 'Effective rank', ...
    'Num NMF components', 'nNMF div network size'};
Params.networkLevelNetMetCustomBounds = struct();
Params.networkLevelNetMetCustomBounds.('effRank') = [1, nan];
Params.networkLevelNetMetCustomBounds.('aveControl') = [1, 1.5];

Params.unitLevelNetMetToPlot = {'ND','MEW','NS','Z','Eloc','PC','BC', 'aveControl', 'modalControl'};
Params.unitLevelNetMetLabels = {'node degree','edge weight','node strength', ... 
    'within-module degree z-score', ... 
    'local efficiency','participation coefficient','betweeness centrality', 'average controllability', 'modal controllability'}; 

Params.includeNMFcomponents = 0;  % whether to save extracted components and original downsampled data

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


% Coordinates of each channel / node 
% Please specify coordinates such that 
% for x : 0 (left) to 1 (right)
% for y : 0 (bottom) to 1 (top)
% note that the coordinates will be multiplied by 8 for plotting purposes, 
% please do not remove that line

% Default mutichannel systems 8 x 8 layout
%
Params.includeChannelNumberInPlots = 1;  % whether to plot channel ID in heatmaps and node plots


if strcmp(Params.channelLayout, 'MCS60old')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [21 31 41 51 61 71 12 22 32 42 52 62 72 82 13 23 33 43 53 63 ... 
    73 83 14 24 34 44 54 64 74 84 15 25 35 45 55 65 75 85 16 26 ...
    36 46 56 66 76 86 17 27 37 47 57 67 77 87 28 38 48 58 68 78];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);

elseif strcmp(Params.channelLayout, 'MCS60')

     channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);
    Params.reorderingIdx = reorderingIdx;

elseif strcmp(Params.channelLayout, 'MCS59')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);

    inclusionIndex = find(channelsOrdering ~= 82);
    Params.channels = channels(inclusionIndex);
    Params.coords = Params.coords(inclusionIndex, :);
    Params.reorderingIdx = reorderingIdx; % (inclusionIndex)


elseif strcmp(Params.channelLayout, 'Axion64')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];
    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(0, 1, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);
    
    Params.channels = channels; 


elseif strcmp(Params.channelLayout, 'Custom')

    x_min = 0;
    x_max = 1;
    y_min = 0;
    y_max = 1;
    num_nodes = 64;
    
    rand_x_coord = (x_max - x_min) .* rand(num_nodes,1) + x_min;
    rand_y_coord = (y_max - y_min) .* rand(num_nodes, 1) + y_min; 
    Params.coords = [rand_x_coord, rand_y_coord];

    Params.coords  = Params.coords * 8;

end 

Params.coords  = Params.coords * 8;  % Do not remove this line after specifying coordinate positions in (0 - 1 format)

