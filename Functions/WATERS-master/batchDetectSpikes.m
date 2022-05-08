function batchDetectSpikes(dataPath, savePath, option, files, params)
%{
Master script for spike detection using CWT method. 
Runs spike detection through recordings, cost parameters, electrodes, and wavelets.

Parameters:
-----------
dataPath : str or character
    path (ending with '/') to the folder containing data to be analyzed
savePath : str or character
    path (ending with '/') to the folder where spike detection
            output will be saved
option: 
    pass either path to files ('path') or list of files ('list');

params: structure
    [optional] argument to pass structure containing parameters;
      otherwise, run setParams() first to set parameters
      nSpikes : number of spikes use to make the custom threshold
      template

Returns
-------


% Author:
%   Jeremy Chabros, University of Cambridge, 2020
%   email: jjc80@cam.ac.uk
%   github.com/jeremi-chabros/CWT
% Edited by Tim SIt
%}

arguments
    dataPath;
    savePath;
    option;
    files;
    params;
end

if ~endsWith(dataPath, filesep)
    dataPath = [dataPath filesep];
end

% Check if specified folder exists 
if ~exist(dataPath, 'dir')
    error(sprintf('Specified dataPath does not exist: %s', dataPath))
end 


addpath(dataPath);


%   Load parameters
if ~exist('params', 'var')
    load('params.mat');
end

multiplier = params.multiplier;
nSpikes = params.nSpikes;
nScales = params.nScales;
wid = params.wid;
grd = params.grd;
costList = params.costList;
wnameList = params.wnameList;
minPeakThrMultiplier = params.minPeakThrMultiplier;
maxPeakThrMultiplier = params.maxPeakThrMultiplier;
posPeakThrMultiplier = params.posPeakThrMultiplier;
unit = params.unit;

% Setting some defaults
if ~isfield(params, 'multiple_templates')
    params.multiple_templates = 0;
end 

if ~isfield(params, 'multi_template_method')
    params.multi_template_method = 'PCA';
end 

if ~isfield(params, 'run_detection_in_chunks')
    params.run_detection_in_chunks = 1;
end 

if ~isfield(params, 'chunk_length')
    params.chunk_length = 60;
end 

if ~isfield(params, 'threshold_calculation_window')
    threshold_calculation_window = [0, 1];
else
    threshold_calculation_window = params.threshold_calculation_window;
end 

if ~isfield(params, 'plot_folder')
    plot_folder = ''; % won't save plot
else 
    plot_folder = params.plot_folder;
end 


%%
% Get files
% Modify the '*string*.mat' wildcard to include a subset of recordings

if exist('option', 'var') && strcmp(option, 'list')
    files = files;
else
    files = dir([dataPath '*.mat']);
end
thresholds = params.thresholds;
thrList = strcat( 'thr', thresholds);
thrList = strrep(thrList, '.', 'p')';


% 2021-06-07: adding absolute thresholds 
if isfield(params, 'absThresholds')
    absThresholds = params.absThresholds;
    absThrList = strcat('absthr', absThresholds);
    absThrList = strrep(absThrList, '.', 'p')';
    
end 

% TODO: work in progress
% if isfield(params, 'absThresholds')
%     wnameList = horzcat(wnameList, absThrList);
% end 

% Note that this adds a new dimensions, you should get Nx2 cell array
% 2021-06-09: TS: but why not just do vertcat???
% wnameList = horzcat(wnameList, thrList);
wnameList = vertcat(wnameList, thrList);

% check if custom threshold file is provided
if isfield(params, 'custom_threshold_file')
    % params.custom_threshold_file.thresholds;
    custom_threshold_method_name = params.custom_threshold_method_name;
    for n_custom_threshold_method = 1:length(custom_threshold_method_name)
        custom_name = strcat('customAbs', custom_threshold_method_name{n_custom_threshold_method});
        wnameList = vertcat(wnameList, {custom_name});
    end 
    customAbsThrPerChannel = params.custom_threshold_file.thresholds;
else
    customAbsThrPerChannel = nan;
    custom_threshold_method_name = nan;
end 

% wnameList = vertcat(wnameList, {'customAbsThr'});


progressbar('File', 'Electrode');

for recording = 1:numel(files)
    
    progressbar((recording-1)/numel(files), []);
    
    if exist('option', 'var') && strcmp(option, 'list')
        fileName = files{recording};
    else
        fileName = files(recording).name;
    end

    % Set which electrodes to ground 
    if isfield(params, 'electrodesToGroundPerRecording')
        if ~isempty(params.('electrodesToGroundPerRecording'))
            groundElectrodeStr = params.('electrodesToGroundPerRecording'){recording}; 
            groundElectrodeCell = strsplit(groundElectrodeStr,', ');
            groundElectrodeVec = str2double(groundElectrodeCell);
            grd = groundElectrodeVec;
        end 
    end 
    
    % Load data
    disp(['Loading ' fileName ' ...']);
    file = load(fileName);
    disp(['File loaded']);
    
    data = file.dat;
    channels = file.channels;
    num_channels = length(channels);  
    fs = file.fs;
    ttx = contains(fileName, 'TTX');
    params.duration = length(data)/fs;
    
    % Truncate the data if specified
    if isfield(params, 'subsample_time')
        if ~isempty(params.subsample_time)
            if params.subsample_time(1) <= 1
                start_frame = 1;
            else
                start_frame = params.subsample_time(1) * fs;
            end
            end_frame = params.subsample_time(2) * fs;
        end
        data = data(start_frame:end_frame, :);
        params.duration = length(data)/fs;
    end
    
    for L = costList
        saveName = [savePath fileName(1:end-4) '_L_' num2str(L) '_spikes.mat'];
        if ~exist(saveName, 'file')
            params.L = L;
            tic
            disp('Detecting spikes...');
            disp(['L = ' num2str(L)]);
            
            % Pre-allocate vectors for storing spike features
            spikeTimes = cell(1,num_channels);
            spikeWaveforms = cell(1,num_channels);
            mad = zeros(1,num_channels);
            variance = zeros(1,num_channels);
            absThreshold = zeros(1, num_channels);

            numChannelsInData = size(data, 2);
            if numChannelsInData ~= length(channels) 
                fprintf(['MAJOR WARNING: the provided list of channels has a different length than the number of channels in the data, ' ...
                    'Please check that the data has been processed correctly. For now I will just run spike detection up to the number of' ...
                    'available channels, assuming that the ordering of channels is still okay \n'])
                channels = channels(1:numChannelsInData);
            end 
            
            % Run spike detection
            for channel = 1:length(channels)
                
                progressbar([], [(channel-1)/length(channels)]);
                
                spikeStruct = struct();
                waveStruct = struct();
                thresholdStruct = struct();

                trace = data(:, channel);
                
                for wname = 1:numel(wnameList)
                    
                    wname = char(wnameList{wname});
                    valid_wname = strrep(wname, '.', 'p');
                    actual_wname = strrep(wname, 'p', '.');
                    
                    spikeWaves = [];
                    spikeFrames = [];
                    if ~(ismember(channel, grd))
                        channelInfo.channel = channel;
                        channelInfo.fileName = fileName;
                        
                        
                        if contains(wname, 'customAbs')
                            customAbsThr = customAbsThrPerChannel{channel}.(erase(wname, 'customAbs'));
                        else
                            customAbsThr = nan;
                        end 
                        
                        
                        [spikeFrames, spikeWaves, ~, threshold] = ...
                            detectSpikesCWT(trace,fs,wid,actual_wname,L,nScales, ...
                            multiplier,nSpikes,ttx, minPeakThrMultiplier, ...
                            maxPeakThrMultiplier, posPeakThrMultiplier, ...
                            params.multiple_templates, params.multi_template_method, ...
                            channelInfo, plot_folder, params.run_detection_in_chunks, ...
                            params.chunk_length, threshold_calculation_window, ...
                            customAbsThr, params.filterLowPass, params.filterHighPass, ...
                            params.remove_artifacts, params.refPeriod, params.getTemplateRefPeriod);
                        
                        thresholdStruct.(valid_wname) = threshold;
                        
                        if iscell(spikeFrames)
                            
                            for cell_idx = 1:length(spikeFrames)
                                custom_spike_frames = spikeFrames{cell_idx};
                                custom_spike_wave = spikeWaves{cell_idx};
                                valid_wname_w_idx = strcat(valid_wname, num2str(cell_idx));
                                switch unit
                                    case 'ms'
                                        spikeStruct.(valid_wname_w_idx) = custom_spike_frames/(fs/1000);
                                    case 's'
                                        spikeStruct.(valid_wname_w_idx) = custom_spike_frames/fs;
                                    case 'frames'
                                        spikeStruct.(valid_wname_w_idx) = custom_spike_frames;
                                end
                                waveStruct.(valid_wname_w_idx) = custom_spike_wave;
                            end 
                            
                        else
                            switch unit
                                case 'ms'
                                    spikeStruct.(valid_wname) = spikeFrames/(fs/1000);
                                case 's'
                                    spikeStruct.(valid_wname) = spikeFrames/fs;
                                case 'frames'
                                    spikeStruct.(valid_wname) = spikeFrames;
                            end
                            waveStruct.(valid_wname) = spikeWaves;
                        end 
                    else
                        waveStruct.(valid_wname) = [];
                        spikeStruct.(valid_wname) = [];
                        thresholdStruct.(valid_wname) = [];
                    end
                end
                
                thresholds{channel} = thresholdStruct;
                spikeTimes{channel} = spikeStruct;
                spikeWaveforms{channel} = waveStruct;
                
                % 2021-06-08 I think this is not actually the mad...
                % mad(channel) = median(trace) - median(abs(trace - mean(trace))) / 0.6745;
                
                % also taking the median of the mean is a  bit weird... 
                % I think mean of mean or mean of median is more
                % sensible...
                s = median(abs(trace - mean(trace))) / 0.6745;
                mad(channel) = s;
                % s = median(abs(trace-mean(trace)))/0.6745;     % Faster than mad(X,1);
                m = median(trace);                % Note: filtered trace is already zero-mean
                absThreshold = m - multiplier*s;
                
                variance(channel) = var(trace);
                
            end
            
            toc
            
          
            % Save results
            save_suffix = ['_' strrep(num2str(L), '.', 'p')];
            params.save_suffix = save_suffix;
            params.fs = fs;
            params.variance = variance;
            params.mad = mad;
            params.absThreshold = absThreshold;
            
            spikeDetectionResult = struct();
            spikeDetectionResult.method = 'CWT';
            spikeDetectionResult.params = params;
            
            saveName = [savePath fileName '_spikes.mat'];
            disp(['Saving results to: ' saveName]);
            
            varsList = {'spikeTimes', 'channels', 'spikeDetectionResult', ...
                'spikeWaveforms', 'thresholds'};
            save(saveName, varsList{:}, '-v7.3');
        end
    end
end
progressbar(1);
end