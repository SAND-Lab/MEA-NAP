function batchDetectSpikes(dataPath, savePath, option, files, Params, MEANAPapp)
% Performs spike detection 
% Runs spike detection through recordings, cost parameters, electrodes, and wavelets.
% 
% Parameters:
% -----------
% dataPath : str or character
%     path to the folder containing data to be analyzed
% savePath : str or character
%     path to the folder where spike detection
%             output will be saved
% option : 
%     pass either path to files ('path') or list of files ('list');
% files : cell array 
% 
% params: structure
%     [optional] argument to pass structure containing parameters;
%       otherwise, run setParams() first to set parameters
%       nSpikes : number of spikes use to make the custom threshold
%       template
% 
% Returns
% -------
% Author:
%   Jeremy Chabros, University of Cambridge, 2020
%   email: jjc80@cam.ac.uk
%   github.com/jeremi-chabros/CWT
% Edited by Tim Sit
% Improvements to make 
% set params to Params to be consistent with the rest of the pipeline 
% TODO: Please address the median definition


arguments
    dataPath;
    savePath;
    option;
    files;
    Params;
    MEANAPapp; 
end


% Check if specified folder exists 
if iscell(dataPath)
    for dataPathIdx = 1:length(dataPath)
        if ~exist(dataPath{dataPathIdx}, 'dir')
            error(sprintf('Specified dataPath does not exist: %s', dataPath{dataPathIdx}))
        end 
        addpath(dataPath{dataPathIdx});
    end
else 
    if ~exist(dataPath, 'dir')
        error(sprintf('Specified dataPath does not exist: %s', dataPath))
    end 
    addpath(dataPath);
end

if ~exist('MEANAPapp', 'var')
    MEANAPapp = struct();
end 

multiplier = Params.multiplier;
nSpikes = Params.nSpikes;
nScales = Params.nScales;
wid = Params.wid;
grd = Params.grd;
costList = Params.costList;
wnameList = Params.wnameList;
minPeakThrMultiplier = Params.minPeakThrMultiplier;
maxPeakThrMultiplier = Params.maxPeakThrMultiplier;
posPeakThrMultiplier = Params.posPeakThrMultiplier;
unit = Params.unit;

% Setting some defaults
if ~isfield(Params, 'multiple_templates')
    Params.multiple_templates = 0;
end 

if ~isfield(Params, 'multi_template_method')
    Params.multi_template_method = 'PCA';
end 

if ~isfield(Params, 'run_detection_in_chunks')
    Params.run_detection_in_chunks = 1;
end 

if ~isfield(Params, 'chunk_length')
    Params.chunk_length = 60;
end 

if ~isfield(Params, 'threshold_calculation_window')
    threshold_calculation_window = [0, 1];
else
    threshold_calculation_window = Params.threshold_calculation_window;
end 

if ~isfield(Params, 'plot_folder')
    plot_folder = ''; % won't save plot
else 
    plot_folder = Params.plot_folder;
end 


%% Spike Detection part
% Get files
% Modify the '*string*.mat' wildcard to include a subset of recordings

if exist('option', 'var') && strcmp(option, 'list')
    files = files;
else
    if iscell(dataPath)
        for dataPathIdx = 1:length(dataPath)
            filesInFolder = dir(fullfile(dataPath{dataPathIdx}, '*.mat'));
            if dataPathIdx == 1
                files = filesInFolder;
            else 
                files = [files; filesInFolder];
            end 
        end
    else
        files = dir(fullfile(dataPath, '*.mat'));
    end
end

Params.numFilesForSpikeDetection = length(files);

thresholds = Params.thresholds;
thrList = strcat( 'thr', thresholds);
thrList = strrep(thrList, '.', 'p');

% 2021-06-07: adding absolute thresholds 
if isfield(Params, 'absThresholds')
    absThrList = {};
    for absIdx = 1:length(Params.absThresholds)
        absThreshold = Params.absThresholds(absIdx);
        absThresholdStr = strcat('absthr', num2str(absThreshold));
        absThresholdStr = strrep(absThresholdStr, '.', 'p');
        absThrList = [absThrList absThresholdStr];
    end
    
    wnameList = horzcat(wnameList, absThrList);
end 

wnameList = horzcat(wnameList, thrList);

% Remove special 'None' specifier (for no wavelet spike detection)
wnameList = wnameList(~strcmp(wnameList, 'None'));

% check if custom threshold file is provided
if isfield(Params, 'custom_threshold_file')
    % params.custom_threshold_file.thresholds;
    custom_threshold_method_name = Params.custom_threshold_method_name;
    for n_custom_threshold_method = 1:length(custom_threshold_method_name)
        custom_name = strcat('customAbs', custom_threshold_method_name{n_custom_threshold_method});
        wnameList = vertcat(wnameList, {custom_name});
    end 
    customAbsThrPerChannel = Params.custom_threshold_file.thresholds;
else
    customAbsThrPerChannel = nan;
    custom_threshold_method_name = nan;
end 

progressbar('File', 'Electrode');

for recording = 1:numel(files)
    
    progressbar((recording-1)/numel(files), []);
    
    if exist('option', 'var') && strcmp(option, 'list')
        fileName = files{recording};
    else
        fileName = files(recording).name;
    end

    % Set which electrodes to ground 
    if isfield(Params, 'electrodesToGroundPerRecording')
        if ~isempty(Params.('electrodesToGroundPerRecording'))
            groundElectrodeStr = Params.('electrodesToGroundPerRecording'){recording}; 
            if isstr(groundElectrodeStr)
                groundElectrodeCell = strsplit(groundElectrodeStr,',');
                groundElectrodeVec = str2double(groundElectrodeCell);
            else
                groundElectrodeVec = groundElectrodeStr;
            end 
            grd = groundElectrodeVec;

            if (Params.electrodesToGroundPerRecordingUseName == 1) && all(~isnan(grd))
                % Convert from the channel name we want to ground, to the
                % index within Params.channels
                new_grd = zeros(length(grd), 1) + nan;
                for grd_idx = 1:length(grd)
                    new_idx = find(Params.channels{recording} == grd(grd_idx));
                    if ~isempty(new_idx)
                        new_grd(grd_idx) = new_idx;
                    else
                        fprintf(sprintf('WARNING: you specified to ground electrode %.f, but it does not exist, skipping... \n', groundElectrodeVec(grd_idx)))
                    end 
                end 
                grd = new_grd(~isnan(new_grd));
            end 

        end 
    end 
    
    % Load data
    if Params.guiMode == 1
        MEANAPapp.MEANAPStatusTextArea.Value = [MEANAPapp.MEANAPStatusTextArea.Value; ...
                    'Loading ' fileName ' ...'];
    else 
        disp(['Loading ' fileName ' ...']);
    end
    
    file = load(fileName);
    
    data = file.dat;
    channels = file.channels;
    num_channels = length(channels);  
    fs = file.fs;
    ttx = contains(fileName, 'TTX');
    Params.duration = length(data)/fs;
    
    % Truncate the data if specified
    if isfield(Params, 'subsample_time')
        if ~isempty(Params.subsample_time)
            if Params.subsample_time(1) <= 1
                start_frame = 1;
            else
                start_frame = Params.subsample_time(1) * fs;
            end
            end_frame = Params.subsample_time(2) * fs;
        end
        data = data(start_frame:end_frame, :);
        Params.duration = length(data)/fs;
    end
    
    for L = costList
        saveName = [savePath fileName(1:end-4) '_L_' num2str(L) '_spikes.mat'];
        if ~exist(saveName, 'file')
            Params.L = L;
            
            if Params.timeProcesses == 1
                tic
            end
            
            if Params.guiMode == 1
               MEANAPapp.MEANAPStatusTextArea.Value = [MEANAPapp.MEANAPStatusTextArea.Value; ...
                    'Detecting spikes...'];
            else 
                disp('Detecting spikes...');
            end 
            % disp(['L = ' num2str(L)]);
            
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
                            Params.multiple_templates, Params.multi_template_method, ...
                            channelInfo, plot_folder, Params.run_detection_in_chunks, ...
                            Params.chunk_length, threshold_calculation_window, ...
                            customAbsThr, Params.filterLowPass, Params.filterHighPass, ...
                            Params.remove_artifacts, Params.refPeriod, Params.getTemplateRefPeriod);
                        
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
                m = median(trace); % Note: filtered trace is already zero-mean
                absThreshold = m - multiplier*s;
                
                variance(channel) = var(trace);
                
            end
            
            if Params.timeProcesses == 1
                toc
            end 
            
            % Save results
            save_suffix = ['_' strrep(num2str(L), '.', 'p')];
            Params.save_suffix = save_suffix;
            Params.fs = fs;
            Params.variance = variance;
            Params.mad = mad;
            Params.absThreshold = absThreshold;
            
            spikeDetectionResult = struct();
            % spikeDetectionResult.method = 'CWT';
            spikeDetectionResult.params = Params;
            
            saveName = fullfile(savePath,  strcat(fileName, '_spikes.mat'));
            % disp(['Saving results to: ' saveName]);
            
            % Get coordinates for particular recording 
            coords = Params.coords{recording};
            
            % Calculate spike amplitudes
            spikeAmps = getSpikeAmp(spikeWaveforms);
            
            varsList = {'spikeTimes', 'channels', 'spikeDetectionResult', ...
                'spikeWaveforms', 'spikeAmps', 'thresholds', 'coords'};
            save(saveName, varsList{:}, '-v7.3');
        end
    end
end
progressbar(1);
end
