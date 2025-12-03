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


% --- TEMPLATE CALCULATION FOR 'longblank' METHOD ---

% This section is placed before the main channel loop for 'longblank' because

% it needs to process data from all channels to create the blank templates.

if strcmp(stimDetectionMethod, 'longblank')

    % --- Step 1: Pre-calculate blankStarts and blankEnds for all channels using the hardcoded blank length ---

    all_channels_blank_starts = cell(numChannels, 1);
    all_channels_blank_ends = cell(numChannels, 1);

    all_channels_non_stim_blank_starts = cell(numChannels, 1);
    all_channels_non_stim_blank_ends = cell(numChannels, 1);

    num_blanks_per_channel = zeros(numChannels, 1);

    nonStimBlankMinDur = 0.001;
    non_stim_min_dur = round(nonStimBlankMinDur * Params.fs);

    % Use hardcoded min_duration for blank detection
    % min_duration_hardcoded = 37; % This minimum value detects all blank
    min_duration = round(Params.minBlankingDuration * Params.fs);

    for channel_idx = 1:numChannels

        channelDat = rawData(:, channel_idx);



        change_points = [1; diff(channelDat) ~= 0];

        group_id = cumsum(change_points);

        counts = accumarray(group_id(:), 1);

        valid_groups = find(counts >= min_duration);

        [~, start_indices] = unique(group_id, 'first');

        [~, end_indices] = unique(group_id, 'last');

        start_indices_hardcoded = start_indices(ismember(group_id(start_indices), valid_groups));

        end_indices_hardcoded = end_indices(ismember(group_id(end_indices), valid_groups));

        blankStarts = start_indices_hardcoded / Params.fs;

        blankEnds = end_indices_hardcoded / Params.fs;
        
        % Get the non-stimulation blanks
        non_stim_groups = find((counts >= non_stim_min_dur) & (counts < min_duration));
        start_indices_non_stim = start_indices(ismember(group_id(start_indices), non_stim_groups));
        end_indices_non_stim = end_indices(ismember(group_id(end_indices), non_stim_groups));
        blankStartsNonstim = start_indices_non_stim / Params.fs;
        blankEndsNonstim = end_indices_non_stim / Params.fs;

        % Filter out long blanks

        if length(blankStarts) == length(blankEnds)

            blankDurations = blankEnds - blankStarts;

            validIdx = blankDurations <= 0.05;

            blankStarts = blankStarts(validIdx);

            blankEnds = blankEnds(validIdx);

        end

        all_channels_blank_starts{channel_idx} = blankStarts;
        all_channels_blank_ends{channel_idx} = blankEnds;

        all_channels_non_stim_blank_starts{channel_idx} = blankStartsNonstim;
        all_channels_non_stim_blank_ends{channel_idx} = blankEndsNonstim;

        num_blanks_per_channel(channel_idx) = length(blankStarts);

    end



    % --- Step 2: Find valid channels and consolidate their blank times ---

    mode_num_blanks = mode(num_blanks_per_channel);

    valid_channel_indices = find(num_blanks_per_channel == mode_num_blanks);

    consolidated_blank_starts = sort(vertcat(all_channels_blank_starts{valid_channel_indices}));

    consolidated_blank_ends = sort(vertcat(all_channels_blank_ends{valid_channel_indices}));



    % --- Step 3: Calculate the mode template for blank starts and ends ---

    allBlankStartsTemplate = [];

    allBlankEndsTemplate = [];

    
    if ~isempty(consolidated_blank_starts)

        % Create template for blank starts

        allBlankStartsTemplate = zeros(size(consolidated_blank_starts));

        for i = 1:length(consolidated_blank_starts)

            time = consolidated_blank_starts(i);

            window_times = consolidated_blank_starts(consolidated_blank_starts >= time - 1 & consolidated_blank_starts <= time + 1);

            allBlankStartsTemplate(i) = mode(window_times);

        end

        allBlankStartsTemplate = unique(allBlankStartsTemplate); % Keep unique template times

    end



    if ~isempty(consolidated_blank_ends)

        % Create template for blank ends

        allBlankEndsTemplate = zeros(size(consolidated_blank_ends));

        for i = 1:length(consolidated_blank_ends)

            time = consolidated_blank_ends(i);

            window_times = consolidated_blank_ends(consolidated_blank_ends >= time - 1 & consolidated_blank_ends <= time + 1);

            allBlankEndsTemplate(i) = mode(window_times);

        end

        allBlankEndsTemplate = unique(allBlankEndsTemplate); % Keep unique template times

    end

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
        
        % Retrieve the pre-calculated blank times for this channel
        blankStarts = all_channels_blank_starts{channel_idx};
        blankEnds = all_channels_blank_ends{channel_idx};

        nonStimBlankStarts = all_channels_non_stim_blank_starts{channel_idx};
        nonStimBlankEnds = all_channels_non_stim_blank_ends{channel_idx};
        % Calculate blank durations (seconds)
        if length(blankStarts) == length(blankEnds)
            blankDurations = blankEnds - blankStarts;
        else
            blankDurations = [];
        end


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

    if strcmp(stimDetectionMethod, 'longblank')
        stimStruct.blankStarts = blankStarts; % Start times (seconds) of hardcoded blanks 
        stimStruct.blankEnds   = blankEnds;   % End   times (seconds) of hardcoded blanks 
        stimStruct.nonStimBlankStarts = nonStimBlankStarts;
        stimStruct.nonStimBlankEnds = nonStimBlankEnds;
        stimStruct.blankDurations = blankDurations;
        % Add the new template variables to the output struct
        stimStruct.allBlankStartsTemplate = allBlankStartsTemplate;
        stimStruct.allBlankEndsTemplate = allBlankEndsTemplate;
    end

    stimInfo{channel_idx} = stimStruct;
    
    
    
end

end

