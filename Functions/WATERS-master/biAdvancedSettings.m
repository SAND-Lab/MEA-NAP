%% Advanced settings for batchInterface (only modify if you know what you are doing)
load params
FNames = fieldnames(params);
for i = 1:length(FNames)
    VN = char(FNames{i});
    eval(['Params.' VN '= params.' VN ';']);
end
clear params

%% Spike detection settings
Params.plotDetectionResults = 0;
Params.threshold_calculation_window = [0, 1.0];  % which part of the recording to do spike detection, 0 = start of recording, 0.5 = midway, 1 = end of recording
% params.absThresholds = {''};  % add absolute thresholds here % TODO:
% double check this works, and allow for this to be empty so it does not have to be commented out 
% params.subsample_time = [1, 60];  % which part of the recording to subsample for spike detection (In seconds)
% if unspecified, then uses the entire recording
Params.run_detection_in_chunks = 0; % whether to run wavelet detection in chunks (0: no, 1:yes)
Params.chunk_length = 60;  % in seconds, will be ignored if run_detection_in_chunks = 0

Params.multiplier = 3; % multiplier to use extracting spikes for wavelet (not for detection)

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

%% Network analysis settings 
Params.minNumberOfNodesToCalNetMet = 25;  % minimum number of nodes to calculate BC and other metrics

%% Node cartography settings 
Params.hubBoundaryWMdDeg = 2.5; % boundary that separates hub and non-hubs (default 2.5)
Params.periPartCoef = 0.625; % boundary that separates peripheral node and none-hub connector (default: 0.625)
Params.proHubpartCoef = 0.3; % boundary that separates provincial hub and connector hub (default: 0.3)
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
channels = [21 31 41 51 61 71 12 22 32 42 52 62 72 82 13 23 33 43 53 63 ... 
            73 83 14 24 34 44 54 64 74 84 15 25 35 45 55 65 75 85 16 26 ...
            36 46 56 66 76 86 17 27 37 47 57 67 77 87 28 38 48 58 68 78];
if size(channels, 1) == 1
    channels = channels';
end 
Params.coords(:,1) = floor(channels/10);
Params.coords(:,2) = channels - Params.coords(:,1)*10;
Params.coords = Params.coords ./ 8; % convert to 0 - 1 system
%}

% Random coordinates
%{
x_min = 0;
x_max = 1;
y_min = 0;
y_max = 1;
num_nodes = 64;

rand_x_coord = (x_max - x_min) .* rand(num_nodes,1) + x_min;
rand_y_coord = (y_max - y_min) .* rand(num_nodes, 1) + y_min; 
Params.coords = [rand_x_coord, rand_y_coord];


Params.coords  = Params.coords * 8;
%}

Params.coords  = Params.coords * 8;  % Do not remove this line after specifying coordinate positions in (0 - 1 format)
num_channels = size(Params.coords, 1);
figure;
subplot(1, 2, 1)
title('Provided electrode layout (channel index)')
for n_channel = 1:num_channels
    txt_to_plot = sprintf('%.f', n_channel);
    text(Params.coords(n_channel, 1), Params.coords(n_channel, 2), txt_to_plot)
end 
xlabel('X coordinates')
ylabel('Y coordinates')
xlim([min(Params.coords(:, 1)) - 1, max(Params.coords(:, 1) + 1)])
ylim([min(Params.coords(:, 2)) - 1, max(Params.coords(:, 2) + 1)])

subplot(1, 2, 2)
title('Provided electrode layout (channel ID)')
for n_channel = 1:num_channels
    txt_to_plot = sprintf('%.f', channels(n_channel));
    text(Params.coords(n_channel, 1), Params.coords(n_channel, 2), txt_to_plot)
end 
xlabel('X coordinates')
ylabel('Y coordinates')
xlim([min(Params.coords(:, 1)) - 1, max(Params.coords(:, 1) + 1)])
ylim([min(Params.coords(:, 2)) - 1, max(Params.coords(:, 2) + 1)])

set(gcf, 'color', 'w')

