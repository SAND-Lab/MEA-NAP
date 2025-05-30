function [spikeMatrix,spikeTimes,Params,Info] = formatSpikeTimes(File, Params, Info, spikeDataFolder, expMatData)
% this function loads in the spike detection result and creates a
% spike matrix and spike times structure for the chosen spike detection
% method and chosen length of recording

% Parameters
% -----------
% File : character
%    name of the recording, excluding file extensions
% Params : structure
%    here we will use Params.SpikesCostParam, Params.SpikesMethod,
%    Params.TruncRec and Params.TruncLength
% Info : structure
% spikeDataFolder : path to directory 
%     absolute path to the folder containing the spike detected files
% Returns 
% -------
% spikeMatrix : matrix 
% spikeTimes : struct 
% Params : struct 
% Info : struct 
%   Info.channels : vector 
%       list of electrode names
%    


%% load spike detection result

fileName = strcat(char(File),'_spikes.mat');
fileFullPath = fullfile(spikeDataFolder, fileName);
if isfile(fileFullPath)
    load(fileFullPath, 'spikeTimes', 'spikeDetectionResult', 'channels')
    if isfield(spikeDetectionResult, 'params')
        duration_s = floor(spikeDetectionResult.params.duration);
        fs = spikeDetectionResult.params.fs;
    else 
        duration_s = floor(spikeDetectionResult.Params.duration);
        fs = spikeDetectionResult.Params.fs;
    end
    
else 
   spikeTimes = expMatData.spikeTimes; 
   channels = expMatData.Info.channels;
   duration_s = expMatData.Info.duration_s;
   fs = expMatData.Params.fs;
end

spikeTimes = spikeTimes(~cellfun(@isempty, spikeTimes));

Info.channels = channels;

%% merge spikes if using multiple spike detection methods

if strcmp(Params.SpikesMethod,'merged') || strcmp(Params.SpikesMethod,'mergedAll')
    for uu = 1:length(spikeTimes)
        [spike_times{uu}.('mergedAll'),~, ~] = mergeSpikes(spikeTimes{uu}, 'all');
    end
    clear spikeTimes
    spikeTimes = spike_times;
elseif strcmp(Params.SpikesMethod,'mergedWavelet')
    for uu = 1:length(spikeTimes)
            [spike_times{uu}.('mergedWavelet'),~, ~] = mergeSpikes(spikeTimes{uu}, 'wavelets');
    end
    clear spikeTimes
    spikeTimes = spike_times;
end

%% format full length or truncated recording

if Params.TruncRec == 0
    Info.duration_s = duration_s;
end

% truncate spike times
if Params.TruncRec == 1
    for uu = 1:length(spikeTimes)
        temp_spike_times = double(spikeTimes{1,uu}.(Params.SpikesMethod));
        temp_spike_times(temp_spike_times>Params.TruncLength) = [];
        spikeTimes{1,uu}.(Params.SpikesMethod) = [];
        spikeTimes{1,uu}.(Params.SpikesMethod) = temp_spike_times;
        clear temp_spike_times
    end
    if spikeDetectionResult.params.duration < Params.TruncLength
        Info.duration_s = spikeDetectionResult.params.duration;
    else
        Info.duration_s = Params.TruncLength;
    end
end

Params.fs = fs;

%% create spike matrix

spikeMatrix = SpikeTimesToMatrix(spikeTimes,fs,Params.SpikesMethod,Info);

% duration_s_rounded = floor(length(spikeMatrix)/Params.fs);
% numSamplesToGet = floor(duration_s_rounded * Params.fs); 
% spikeMatrix = spikeMatrix(numSamplesToGet, :);

% this while loop looks like it can be improved !!!
% 2024-11-07 : Actually I think this is unnecessary with some adjustement
% downstream
%{
while  floor(length(spikeMatrix)/Params.fs)~=Info.duration_s
    n2del = Params.fs*(length(spikeMatrix)/Params.fs - floor(length(spikeMatrix)/Params.fs));
    spikeMatrix=spikeMatrix(1:length(spikeMatrix)-(n2del),:);
end
%}

% make into sparse matrix to reduce size of variable
spikeMatrix = sparse(spikeMatrix);

end