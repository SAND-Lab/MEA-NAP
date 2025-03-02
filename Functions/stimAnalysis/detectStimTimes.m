function stimInfo = detectStimTimes(filteredData, Params, channelNames, coords)
% Detects electrical sitmulation time from filtered voltage trace
% Parameters
% ----------
% filteredData : matrix
% matrix of shape (numTimeSamples, numChannels)
% Params : struct 
% structure with the following required fields 
%      stimDetectionMethod : str 
%           method of detecting electrical stimulation
% channelNames : vector 
% vector (or cell) of channel names, usually integer values
% Output
% ------
% stimInfo : cell 
% cell where each entry is a structure 
% is structure has the following fields
%      elecStimTimes : vector of electrical stimulation onset times (seconds)
%      elecStimDur : vector of electrical stimulation duration (seconds)

% Set parameters 
stimDetectionMethod = Params.stimDetectionMethod;
stimRefPeriod = Params.stimRefractoryPeriod; 
stimDur = Params.stimDuration;


numChannels = size(filteredData, 2);
stimInfo = cell(numChannels, 1);

% Do electrical stimulation detection (and assign stimulation duration)
for channel_idx = 1:numChannels
    traceMean = mean(filteredData(:, channel_idx));
    traceStd = std(filteredData(:, channel_idx));
    

    if strcmp(stimDetectionMethod, 'absPosThreshold')
        stimThreshold = Params.stimDetectionVal;
        elecStimTimes = find(filteredData(:, channel_idx) > stimThreshold) / Params.fs;
    elseif strcmp(stimDetectionMethod, 'absNegThreshold')
        stimThreshold = Params.stimDetectionVal;
        elecStimTimes = find(filteredData(:, channel_idx) < stimThreshold) / Params.fs;
    elseif strcmp(stimDetectionMethod, 'stdNeg')
        stimThreshold = traceMean - traceStd * Params.stimDetectionVal;
        elecStimTimes = find(filteredData(:, channel_idx) < stimThreshold) / Params.fs;
    else 
        error('No valid stimulus detection specified')
    end 

    for stimIdx = 1:length(elecStimTimes)
        
        stimTime = elecStimTimes(stimIdx);

        if ~isnan(stimTime)
            removeIndex = find( ...
                 (elecStimTimes > stimTime) & ...
                 (elecStimTimes <= stimTime + stimRefPeriod) ...
                );
            elecStimTimes(removeIndex) = nan;
        end

    end
    elecStimTimes = elecStimTimes(~isnan(elecStimTimes));

    
    stimStruct = struct();
    stimStruct.elecStimTimes = elecStimTimes; 
    stimStruct.elecStimDur = repmat(stimDur, length(elecStimTimes), 1);
    stimStruct.channelName = channelNames(channel_idx);
    stimStruct.coords = coords(channel_idx, :);
    stimInfo{channel_idx} = stimStruct;
    
end

end

