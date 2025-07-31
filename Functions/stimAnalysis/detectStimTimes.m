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

if strcmp(stimDetectionMethod, 'blanking')

    % IDEA: take the mode of the blanking times per electrode, and use
    % those as the stimulation times
    % NOTE: This is quite slow at the moment, not sure why...

    num_blanks_per_electrode = zeros(1, numChannels);
    electrode_blank_times = {};

    for channel_idx = 1:numChannels
        channelDat = rawData(:, channel_idx);
        
        % Minimum duration of a run (currently in samples)
        min_duration = round(Params.minBlankingDuration * Params.fs); % 25 works
        
        % Find where values change
        change_points = [1; diff(channelDat) ~= 0]; % [true (diff(channelDat) ~= 0)];
        
        % Assign group IDs to each run of constant value
        group_id = cumsum(change_points);
        
        % Count length of each run
        counts = accumarray(group_id(:), 1);
        
        % Find which groups meet the minimum duration
        valid_groups = find(counts >= min_duration);
        
        % Find start indices of each group
        [~, start_indices] = unique(group_id, 'first');
        
        % Select only those with valid length
        start_indices = start_indices(ismember(group_id(start_indices), valid_groups));

        num_blanks_per_electrode(channel_idx) = length(start_indices);
        electrode_blank_times{channel_idx} = start_indices / Params.fs;

    end
    
    blanks_count_mode = mode(num_blanks_per_electrode);
    electrodes_with_mode_count = find(num_blanks_per_electrode == blanks_count_mode);
    allStimTimesTemplate = median(horzcat(electrode_blank_times{electrodes_with_mode_count}), 2);

    if isempty(allStimTimesTemplate)
        fprintf('WARNING: NO BLANKING DETECTED')
    end

end


if strcmp(stimDetectionMethod, 'blanking')
    %{
    if strcmp(Params.stimProcessingMethod, 'filter')
        lowpass = Params.filterLowPass;
        highpass = Params.filterHighPass;
        wn = [lowpass highpass] / (Params.fs / 2);
        filterOrder = 3;
        [b, a] = butter(filterOrder, wn);
        % WIP: 
        filteredData = zeros(size(rawData));
        for channelIdx = 1:size(stimRawData.dat, 2)
            data = stimRawData.dat(:, channelIdx);
            trace = filtfilt(b, a, double(data));
            filteredData(:, channelIdx) = trace;
         end 
    else
    %}
        medianAbsDeviation = median(abs(rawData - mean(rawData, 1)), 1);
        medianZscore = abs(rawData - median(rawData, 1)) ./ medianAbsDeviation;
    % end 
end


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
    elseif strcmp(stimDetectionMethod, 'blanking')
        % First take the approximate stimulation time from the trace 
        % Then find the closest stimulation times according to the blanking
        % times
        stimThreshold = Params.stimDetectionVal;

        % TODO: this is not as good as the filtering approach... need to
        % have very long refractory period...
        approxElecStimTimes = find(medianZscore(:, channel_idx) > stimThreshold) / Params.fs;

        keepIdx = true(size(approxElecStimTimes)); % Logical mask for keeping elements
        lastValidIdx = 1; % Track last valid stim time
        
        for stimIdx = 2:length(approxElecStimTimes)
            if approxElecStimTimes(stimIdx) <= approxElecStimTimes(lastValidIdx) + stimRefPeriod
                keepIdx(stimIdx) = false; % Mark for removal
            else
                lastValidIdx = stimIdx; % Update last valid index
            end
        end
        approxElecStimTimes = approxElecStimTimes(keepIdx); % Keep only valid elements
        
        elecStimTimes = [];
        for stimIdx = 1:length(approxElecStimTimes)
            % NOTE: Here we assume that the blanking always occur before
            % the stimulation artifact, this resolves cases where two
            % blanking periods are equally close the the stimulation
            % artifact
            allStimTimesTemplateBeforeStim = allStimTimesTemplate(allStimTimesTemplate < approxElecStimTimes(stimIdx));
            [~, minIdx] = min(abs(approxElecStimTimes(stimIdx) - allStimTimesTemplateBeforeStim));
            if ~isempty(minIdx)
                elecStimTimes(stimIdx) = allStimTimesTemplateBeforeStim(minIdx);
            end 
        end

    elseif strcmp(stimDetectionMethod, 'longblank')

        channelDat = rawData(:, channel_idx);

        % Minimum duration of a run (currently in samples)
        min_duration = round(Params.minBlankingDuration * Params.fs); % 25 works
        
        % Find where values change
        change_points = [1; diff(channelDat) ~= 0]; % [true (diff(channelDat) ~= 0)];
        
        % Assign group IDs to each run of constant value
        group_id = cumsum(change_points);
        
        % Count length of each run
        counts = accumarray(group_id(:), 1);
        
        % Find which groups meet the minimum duration
        valid_groups = find(counts >= min_duration);
        
        % Find start indices of each group
        [~, start_indices] = unique(group_id, 'first');
        
        % Select only those with valid length
        start_indices = start_indices(ismember(group_id(start_indices), valid_groups));

        elecStimTimes = start_indices / Params.fs;


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
    
    if strcmp(stimDetectionMethod, 'blanking')
        stimStruct.allStimTimesTemplate = allStimTimesTemplate;
    end

    stimInfo{channel_idx} = stimStruct;

    
    
end

end

