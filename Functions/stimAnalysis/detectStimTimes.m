function stimInfo = detectStimTimes(rawData, Params, channelNames, coords)
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


numChannels = size(rawData, 2);
stimInfo = cell(numChannels, 1);

% Do electrical stimulation detection (and assign stimulation duration)
for channel_idx = 1:numChannels
    traceMean = mean(rawData(:, channel_idx));
    traceStd = std(rawData(:, channel_idx));
    

    if strcmp(stimDetectionMethod, 'absPosThreshold')
        stimThreshold = Params.stimDetectionVal;
        elecStimTimes = find(rawData(:, channel_idx) > stimThreshold) / Params.fs;
    elseif strcmp(stimDetectionMethod, 'absNegThreshold')
        stimThreshold = Params.stimDetectionVal;
        elecStimTimes = find(rawData(:, channel_idx) < stimThreshold) / Params.fs;
    elseif strcmp(stimDetectionMethod, 'stdNeg')
        stimThreshold = traceMean - traceStd * Params.stimDetectionVal;
        elecStimTimes = find(rawData(:, channel_idx) < stimThreshold) / Params.fs;
    else 
        error('No valid stimulus detection specified')
    end 
    
    % Remove stim within refractory period of each other 
    % V1 : Slow 
    %{
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
    %}

    % V2: Faster
    %
    keepIdx = true(size(elecStimTimes)); % Logical mask for keeping elements
    lastValidIdx = 1; % Track last valid stim time
    
    for stimIdx = 2:length(elecStimTimes)
        if elecStimTimes(stimIdx) <= elecStimTimes(lastValidIdx) + stimRefPeriod
            keepIdx(stimIdx) = false; % Mark for removal
        else
            lastValidIdx = stimIdx; % Update last valid index
        end
    end
    elecStimTimes = elecStimTimes(keepIdx); % Keep only valid elements
    %}

    stimStruct = struct();
    stimStruct.elecStimTimes = elecStimTimes; 
    stimStruct.elecStimDur = repmat(stimDur, length(elecStimTimes), 1);
    stimStruct.channelName = channelNames(channel_idx);
    stimStruct.coords = coords(channel_idx, :);
    stimInfo{channel_idx} = stimStruct;
    
end

end

