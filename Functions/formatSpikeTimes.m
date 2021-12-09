function [spikeMatrix,spikeTimes,Params,Info] = formatSpikeTimes(File,Params,Info)

% this function loads in the spike detection result and creates a
% spike matrix and spike times structure for the chosen spike detection
% method and chosen length of recording
%
% INPUTS
%   File:
%   Params: here we will use Params.SpikesCostParam, Params.SpikesMethod,
%            Params.TruncRec and Params.TruncLength
%
% OUTPUTS 
%

%% load spike detection result

try
    load(strcat(char(File),'_spikes.mat'),'spikeTimes','spikeDetectionResult','channels')
    % remove empty channels
    spikeTimes = spikeTimes(~cellfun(@isempty, spikeTimes));
catch
    load(strcat(char(File),'.mat'),'spikeTimes','spikeDetectionResult','channels')
    % remove empty channels
    spikeTimes = spikeTimes(~cellfun(@isempty, spikeTimes));
end

Info.channels = channels;

%% merge spikes if using multiple spike detection methods

if strcmp(Params.SpikesMethod,'merged')
    for uu = 1:length(spikeTimes)
        [spike_times{uu}.merged,~, ~] = mergeSpikes(spikeTimes{uu}, 'all');
    end
    clear spikeTimes
    spikeTimes = spike_times;
end

%% format full length or truncated recording

if Params.TruncRec == 0
    Info.duration_s = floor(spikeDetectionResult.params.duration);
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

Params.fs = spikeDetectionResult.params.fs;

%% create spike matrix

spikeMatrix = SpikeTimesToMatrix(spikeTimes,spikeDetectionResult,Params.SpikesMethod,Info);
while  floor(length(spikeMatrix)/Params.fs)~=Info.duration_s
    n2del = Params.fs*(length(spikeMatrix)/Params.fs - floor(length(spikeMatrix)/Params.fs));
    spikeMatrix=spikeMatrix(1:length(spikeMatrix)-(n2del),:);
end

% make into sparse matrix to reduce size of variable
spikeMatrix = sparse(spikeMatrix);

end