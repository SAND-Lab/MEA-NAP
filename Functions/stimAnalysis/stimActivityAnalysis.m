function stimActivityAnalysis(spikeData, Params, Info, figFolder, oneFigureHandle)
% Performs analysis of spike data relative to stimulation times 
% INPUT
% -------
% spikeData : struct 
% Params : struct 
% Info : struct 
% figFolder : path 
% oneFigureHandle : matlab figure object
    
    if strcmp(Params.stimDetectionMethod, 'longblank')
        % get all the blank durations 
        allBlankDurations = cellfun(@(s) s.blankDurations, spikeData.stimInfo, 'UniformOutput', false);
        allBlankDurations = [allBlankDurations{:}];
        Params.blankDurMode = mode(allBlankDurations(:));
    end

    
    %% Gather stimulation times
    allStimTimes = [];
    
    for channelIdx = 1:length(spikeData.stimInfo)
        
        allStimTimes = [allStimTimes, spikeData.stimInfo{channelIdx}.elecStimTimes];
    
    end

    %% Firing rate before and after stimulation 
    figName = '9_FR_before_after_stimulation';
    plotPrePostStimFR(spikeData, allStimTimes, Params, figFolder, figName, Info);

    % Do it for each pattern 
    for patternIdx = 1:length(spikeData.stimPatterns)
        figName = sprintf('9_FR_before_after_stimulation_pattern_%.f', patternIdx);
        plotPrePostStimFR(spikeData, spikeData.stimPatterns{patternIdx}, Params, figFolder, figName, Info);
    end


    %% Plot population raster align to stim times 
    % rasterWindow = [Params.preStimWindow(1), Params.postStimWindow(2)];
    Params.rasterBinWidth = 0.01; %  TODO: move this to the app

    [frAlignedToStim, rasterBins] = getFrAlignedToStim(spikeData, allStimTimes, Params);
    numChannels = size(frAlignedToStim, 1);

    figureHandle = figure;
    figName = '10_stimulation_raster_and_psth';
    ylabel_txt = 'Mean firing rate (spikes/s)';
    plotMetricAlignedToStim(frAlignedToStim, rasterBins, Info, Params, ...
    ylabel_txt, figFolder, figName, figureHandle)
    close(figureHandle);  % Close the figure after saving

    % Do it for each pattern
    for patternIdx = 1:length(spikeData.stimPatterns)
        figureHandle = figure;
        figName = sprintf('10_stimulation_raster_and_psth_pattern_%.f', patternIdx);
        [frAlignedToStim, rasterBins] = getFrAlignedToStim( ... 
            spikeData, spikeData.stimPatterns{patternIdx}, Params);
        plotMetricAlignedToStim(frAlignedToStim, rasterBins, Info, Params, ...
                ylabel_txt, figFolder, figName, figureHandle)
        close(figureHandle);  % Close the figure after saving
    end

    %% Look at spike amplitude aligned to stimulus
    % TODO: Loop throgh patterns
    numStimEvent = length(allStimTimes);
    spikeAmps = getSpikeAmp(spikeData.spikeWaveforms); 
    spikeData.spikeAmps = spikeAmps;
    
    rasterWindow = Params.stimAnalysisWindow;
    rasterBinWidth = Params.rasterBinWidth;   % originally 0.025 
    
    rasterBins = rasterWindow(1):rasterBinWidth:rasterWindow(2);
    numBins = length(rasterBins) - 1; 
    
    ampAlignedToStim = zeros(numChannels, numStimEvent, numBins) + nan;

    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
        channelSpikeAmps = spikeData.spikeAmps{channelIdx}.(Params.SpikesMethod);
           
         for stimEventIdx = 1:numStimEvent 
            stimTime = allStimTimes(stimEventIdx);
            
            for binIdx = 1:length(rasterBins)-1
                binStart = stimTime + rasterBins(binIdx);
                binEnd = stimTime + rasterBins(binIdx+1);
                spikeIdx = find((channelSpikeTimes >= binStart)  & (channelSpikeTimes < binEnd));
                meanAmps = mean(abs(channelSpikeAmps(spikeIdx)));
                ampAlignedToStim(channelIdx, stimEventIdx, binIdx) = meanAmps;
            end
    
            % ampAlignedToStim(channelIdx, stimEventIdx, :) = histcounts(channelSpikeTimes - stimTime, rasterBins) / rasterBinWidth;
    
         end 
    
        
    end
    
    figureHandle = figure;
    set(figureHandle, 'Position', [100, 100, 600, 500]);
    subplot(2, 1, 1)
    meanAmpalignedToStim = squeeze(nanmean(ampAlignedToStim, [1, 2]));
    plot(rasterBins(2:end), meanAmpalignedToStim)
    hold on 
    fill([0, Params.blankDurMode + Params.postStimWindowDur/1000, ...
          Params.blankDurMode + Params.postStimWindowDur/1000, 0], ...
          [0, 0, max(meanAmpalignedToStim), max(meanAmpalignedToStim)], [0.5, 0.5, 0.5], 'FaceAlpha', 0.3,'LineStyle','none')
    box off 
    set(gca, 'TickDir', 'out');
    ylabel('Mean absolute spike amplitude')
    title(Info.FN{1}, 'Interpreter', 'none');
    
    subplot(2, 1, 2)
    imagesc(rasterBins(2:end), 1:numChannels, squeeze(nanmean(ampAlignedToStim, 2)))
    box off
    ylabel('Channel')
    xlabel('Time from stimulation (s)')
    set(gca, 'TickDir', 'out');
    set(gcf, 'color', 'w');
    

    % save figure
    figName = '11_stimulation_amplitude_raster_and_psth';
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);
    close(figureHandle);  % Close the figure after saving

    %% Spike Latency / Time-to-first-spike 
    
    numPatterns = length(spikeData.stimPatterns);
    channelMeanSpikeLatency = zeros(numChannels, numPatterns) + nan;
   
    for patternIdx = 1:numPatterns
        stimTimesToAlign = spikeData.stimPatterns{patternIdx};
        % for each electrode
        for channelIdx= 1:numChannels
            channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
            spikeLatencies = getSpikeLatencyRelStim(stimTimesToAlign, channelSpikeTimes);
            channelMeanSpikeLatency(channelIdx, patternIdx) = nanmean(spikeLatencies);
        end
    end 
    % TODO: Make null distribution of spike latency

    % Make plots of spike latency
    vrange = [min(channelMeanSpikeLatency(:)) max(channelMeanSpikeLatency(:))];
    cmap = flip(viridis);
    for patternIdx = 1:length(spikeData.stimPatterns)
        oneFigureHandle = figure();
        nodeMetric = channelMeanSpikeLatency(:, patternIdx);
        cmapLabel = 'Mean spike latency (s)';
        oneFigureHandle = plotStimHeatmapWmetric(nodeMetric, vrange, cmap, cmapLabel, ...
            spikeData.stimInfo, patternIdx, oneFigureHandle);
        title(sprintf('Pattern %.f', patternIdx));
        figName = sprintf('spikeLatency_pattern_%.f_heatmap', patternIdx);
        figPath = fullfile(figFolder, figName);
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle)
        close(oneFigureHandle);  % Close the figure after saving
    end

    %% Plot heatmap of activity after stimulation 
    % stim_activity_window = [0.1, 0.3];  % seconds
    patternSpikeMatrixStore = {};
    stimActivityStore = {};

    % some parameter adjustments to look into smaller windows 
    % Params.stimRemoveSpikesWindow = [0, 0]
    % Params.rasterBinWidth = 0.001; % originally 0.01
    
    Params.stimDecodingTimeWindows = linspace(0, 0.01, 10);
    % Params.stimDecodingTimeWindows = [0, 0.002, 0.004, 0.006, 0.008, 0.01];

    for patternIdx = 1:length(spikeData.stimPatterns)
        stimTimesToAlign = spikeData.stimPatterns{patternIdx};
        [frAlignedToStim, rasterBins] = getFrAlignedToStim(spikeData, stimTimesToAlign, Params);
        
        numDecodingTimeBins = length(Params.stimDecodingTimeWindows)-1;
        numTrials = size(frAlignedToStim, 2);
        patternSpikeMatrix = zeros(numTrials, numChannels*numDecodingTimeBins);
        for window_idx = 1:numDecodingTimeBins
            subsetTimeIdx = find((rasterBins >= Params.stimDecodingTimeWindows(window_idx)) & ...
            (rasterBins <= Params.stimDecodingTimeWindows(window_idx+1))) - 1;
            patternSpikeMatrixAtWindow = mean(frAlignedToStim(:, :, subsetTimeIdx), 3); % mean across time
            start_idx = 1 + (window_idx - 1) * numChannels; 
            end_idx = start_idx + numChannels - 1;
            patternSpikeMatrix(:, start_idx:end_idx) = patternSpikeMatrixAtWindow';
        end

        % subsetTimeIdx = find((rasterBins >= Params.postStimWindow(1)) & ...
        %     (rasterBins <= Params.postStimWindow(2))) - 1;
        % patternSpikeMatrix = mean(frAlignedToStim(:, :, subsetTimeIdx), 3); % mean across time
        stimActivityStore{patternIdx} = patternSpikeMatrix; % for decoding 
        patternSpikeMatrix = squeeze(mean(patternSpikeMatrix, 1)); % mean across trials
       
        patternSpikeMatrixStore{patternIdx} = patternSpikeMatrix;
        
        % set stimulating electrode value to 0??? 

        % get spike matrix from alignment
        % electrodeHeatMaps(FN, spikeMatrix, channels, spikeFreqMax, Params, coords, figFolder, oneFigureHandle);
    end
    
    % get the max frequency to scale 
    spikeFreqMax = max(cellfun(@max, patternSpikeMatrixStore));
    spikeFreqMax = max([spikeFreqMax, 0.0001]);
    vrange = [0, spikeFreqMax];
    cmap = 'viridis';
    
    for patternIdx = 1:length(spikeData.stimPatterns)
        oneFigureHandle = figure();
        nodeMetric = patternSpikeMatrixStore{patternIdx};
        cmapLabel = 'Firing rate (spikes/s)';
        oneFigureHandle = plotStimHeatmapWmetric(nodeMetric, vrange, cmap, cmapLabel, ...
            spikeData.stimInfo, patternIdx, oneFigureHandle);
        title(sprintf('Pattern %.f', patternIdx));
        figName = sprintf('stimPattern_%.f_heatmap', patternIdx);
        figPath = fullfile(figFolder, figName);
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle)
         close(oneFigureHandle);  % Close the figure after saving
    end


    %% Plot trial by trial stimulation response 
    oneFigureHandle = figure;
    t = tiledlayout(1, length(stimActivityStore), ...
        'TileSpacing', 'compact', 'Padding', 'compact');

    all_activity = vertcat(stimActivityStore{:});
    min_activity = min(all_activity(:));
    max_activity = max(all_activity(:));
    
    if max_activity == 0 
        max_activity = 0.0001;
    end

    clim = [min_activity max_activity];
    for stimId = 1:length(stimActivityStore)
        
        ax = nexttile;
        imagesc(stimActivityStore{stimId}, clim)
        patternNumTrials = size(stimActivityStore{stimId}, 1);
        
        xlabel('Electrodes and time bins')
        ylabel('Trials')
        hTitle = title(['Stim pattern ' num2str(stimId)], '   ');  % add an empty line to create padding
        
        
        hold on
        for window_idx = 1:numDecodingTimeBins
            start_idx = 1 + (window_idx-1) * numChannels; 
            end_idx = start_idx + numChannels - 1;
            plot([start_idx, end_idx], [-0.5, -0.5], 'LineWidth', 3, 'Color', 'black');
            decodingStartMs = Params.stimDecodingTimeWindows(window_idx) * 1000;
            text(start_idx, -0.5, sprintf('%.f ms', decodingStartMs), 'VerticalAlignment', 'bottom');
            
            if window_idx == numDecodingTimeBins
                decodingEndMs = Params.stimDecodingTimeWindows(window_idx+1) * 1000;
                text(end_idx, -0.5, sprintf('%.f ms', decodingEndMs), ...
                    'VerticalAlignment', 'bottom', 'HorizontalAlignment','left');
            end
            
            hold on 
        end

        ylim([-1, patternNumTrials]);
        yticks([1, patternNumTrials])
        box(ax, 'off');
        set(ax, 'TickDir', 'out');  

    end 
    cb = colorbar(ax, 'eastoutside');
    cb.Layout.Tile = 'east';  % Put the colorbar outside the tile layout
    ylabel(cb, 'spikes/s', 'FontSize',12)
    set(gcf, 'color', 'w')
    
    figName = 'stimPattern_activity_per_trial';
    figPath = fullfile(figFolder, figName);
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle)
    close(oneFigureHandle);  % Close the figure after saving


    %% Do decoding of which pattern was stimulated
    numNodesToTry = 1:5:numChannels;
    numRepeatsPerNodeNumber = 10;
    decodingAccuracy = zeros(length(numNodesToTry), numRepeatsPerNodeNumber);

    % construct our X and y for decoding 
    % TODO: adjust which features to use (ie. include spike latency)
    X = vertcat(stimActivityStore{:});  % numTrials x numNodes
    
    % TEMP: Do some z-scoring 
    X = (X - mean(X, 1)) ./ std(X, 1);

    % Do some NaN imputation... 
    X(isnan(X)) = 0;

    y = []; 
    for patternIdx = 1:length(stimActivityStore)
        y = [y; repmat(patternIdx, size(stimActivityStore{patternIdx}, 1), 1)];
    end 
    
    numTrials = size(X, 1);
    % trialIdx = 1:numTrials;
    % propTrainTrials = 0.5;  % proportion of trials for training set
    % numTrainTrials = floor(propTrainTrials * numTrials);
    clf_num_kfold = 5;

    for numNodeIdx = 1:length(numNodesToTry)
        numNodesToUse = numNodesToTry(numNodeIdx);
        
        for repeatIdx = 1:numRepeatsPerNodeNumber
            
            % randomly get a subset of nodes (without replacement)
            nodeToUse = randsample(numChannels, numNodesToUse, false);
            featureIndices = [];
            for windowIdx = 1:numDecodingTimeBins
                startIdx = (windowIdx-1) * numChannels;
                featureIndices = [featureIndices; startIdx + nodeToUse];
            end

            % trialIdxShuffled = trialIdx(randperm(length(trialIdx));
            % train_idx = trialIdx(1:numTrainTrials);
            %test_idx = trialIdx((numTrainTrials+1):end);
            X_subset = X(:, featureIndices);

            if all(isnan(X_subset(:)))
                mean_model_loss = nan;
            else
                clf_model = fitcecoc(X_subset,y);  %multi-class model
                % clf_model = fitcsvm(X_subset,y);
                cross_val_model = crossval(clf_model, 'KFold', clf_num_kfold);
                mean_model_loss = mean(cross_val_model.kfoldLoss);
            end 
            decodingAccuracy(numNodeIdx, repeatIdx) = 1 - mean_model_loss;
        end

    end

    oneFigureHandle = figure;
    plot(numNodesToTry, mean(decodingAccuracy, 2));
    hold on 
    scatter(numNodesToTry, mean(decodingAccuracy, 2));
    ylim([0, 1])
    xlabel('Number of nodes used in classification')
    ylabel('Classification accuracy')
    set(gcf, 'color', 'w')
    figName = 'stimPattern_decoding';
    figPath = fullfile(figFolder, figName);
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle)
    close(oneFigureHandle);  % Close the figure after saving

% NEW SECTION: YUVAL

 %% ========================================================================
    %% SECTION: INDIVIDUAL ELECTRODE PSTH ANALYSIS
    %% ========================================================================
    % This section performs detailed peri-stimulus time histogram (PSTH) analysis
    % for individual electrodes across different stimulation patterns. 
    %
    % KEY COMPUTATIONAL STEPS:
    % 1. Parameter setup
    % 2. Artifact window calculation
    % 3. Channel exclusion 
    % 4. Stimulus time organization and data output organization
    % 5. Per-pattern, per-electrode PSTH computation
    % 6. Electrode selection and visualization
    % 7. Time-to-first-spike latency analysis
    % 8. Data export for reservoir computing analysis

    % -------------------------------------------------------------------------
    % STEP 1: ANALYSIS PARAMETER CONFIGURATION
    % -------------------------------------------------------------------------
    % Define temporal windows and binning parameters for PSTH analysis
    psth_window_s = Params.stimAnalysisWindow;      % Pre- to post-stim analysis window
    psth_bin_width_s = 0.001;            % Bin width for temporal resolution PSTH. NOTE: not currently functional but still passed as an argument
    num_baseline_psths = 30;             % Number of baseline windows for baseline distribution
    baseline_duration_s = psth_window_s(2) - 0;  % Baseline window duration matches post-stim duration

    % Configure smoothing method for PSTH computation
    psth_smoothing_method = 'gaussian';  % Options: 'ssvkernel' or 'gaussian'
    psth_gaussian_width_ms = 1;          % Gaussian kernel width in ms (only used if method is 'gaussian')

    % -------------------------------------------------------------------------
    % STEP 2: ARTIFACT WINDOW CALCULATION - ALIGNED WITH BATCHPROCESSSPIKESFROMSTIM
    % -------------------------------------------------------------------------
    % Extract actual artifact window data consistent with batchProcessSpikesFromStim logic
    % This ensures identical artifact exclusion methodology across preprocessing and analysis
    
    % Collect all blank start and end times from all channels (same as batchProcessSpikesFromStim)
    allBlankStartTimes = [];
    allBlankEndTimes = [];
    
    for channelIdx = 1:length(spikeData.stimInfo)
        channelStimInfo = spikeData.stimInfo{channelIdx};
        if isfield(channelStimInfo, 'blankStarts') && isfield(channelStimInfo, 'blankEnds')
            allBlankStartTimes = [allBlankStartTimes; channelStimInfo.blankStarts];
            allBlankEndTimes = [allBlankEndTimes; channelStimInfo.blankEnds];
        end
    end
    
    % Calculate artifact window ends exactly as in batchProcessSpikesFromStim
    allArtifactWindowEnd = allBlankEndTimes + Params.postStimWindowDur / 1000;
    
    % Calculate artifact window duration for consistent baseline exclusion
    % Use modal blank duration + postStimWindowDur (same total duration as batchProcessSpikesFromStim)
    artifact_duration_s = Params.blankDurMode + (Params.postStimWindowDur / 1000);
    
    % For metadata documentation, store representative artifact window
    % (using median values for documentation purposes)
    median_blank_start_s = median(allBlankStartTimes);
    median_artifact_end_s = median(allArtifactWindowEnd);
    artifact_window_s = [median_blank_start_s, median_artifact_end_s];
    artifact_window_ms = artifact_window_s * 1000;
    
    % -------------------------------------------------------------------------
    % STEP 3: CHANNEL IDENTIFICATION
    % -------------------------------------------------------------------------
    % Note: Global artifact removal and stimulated electrode spike removal is handled
    % by batchProcessSpikesFromStim() which runs before this analysis. However,
    % individual baseline calculations still apply artifact exclusion per baseline window
    % to maintain consistency with the stimulation response analysis methodology.
    
    % Identify stimulated channels for reference (though spikes already removed)
    stimulatedChannels = [];
    if isfield(spikeData, 'stimInfo')
        for channelIdx = 1:length(spikeData.stimInfo)
            if isfield(spikeData.stimInfo{channelIdx}, 'pattern') && ...
               ~isempty(spikeData.stimInfo{channelIdx}.pattern) && ...
               spikeData.stimInfo{channelIdx}.pattern > 0
                stimulatedChannels = [stimulatedChannels, channelIdx];
            end
        end
    end
    stimulatedChannels = unique(stimulatedChannels);  % Remove duplicates

    % -------------------------------------------------------------------------
    % INITIALIZE STIMULATION DATA COLLECTION STRUCTURE
    % -------------------------------------------------------------------------
    % Create structure to collect electrode response data for saving to experiment mat file
    stimData = struct();

    % -------------------------------------------------------------------------
    % STEP 3: STIMULUS TIME CONSOLIDATION
    % -------------------------------------------------------------------------
    % Create chronologically ordered list of all stimulation times across patterns
    allStimTimesConsolidated = [];
    stimPatternLabels = [];

    for patternIdx = 1:length(spikeData.stimPatterns)
        stimTimes = spikeData.stimPatterns{patternIdx};
        if ~isempty(stimTimes)
            stimTimes = stimTimes(:);  % Ensure column vector format
            allStimTimesConsolidated = [allStimTimesConsolidated; stimTimes];
            stimPatternLabels = [stimPatternLabels; repmat(patternIdx, length(stimTimes), 1)];
        end
    end

    % Sort chronologically while preserving pattern labels
    [allStimTimesConsolidated, sortIdx] = sort(allStimTimesConsolidated);
    stimPatternLabels = stimPatternLabels(sortIdx);

    % Initialize consolidated firing rate matrix for reservoir computing analysis
    % Dimensions: [numTrialsTotal x numChannels] where rows = stimulus trials, cols = recording channels
    numTrialsTotal = length(allStimTimesConsolidated);
    FiringRateMatrix = NaN(numTrialsTotal, numChannels);

    % Time window calculations
    poststim_duration_s = psth_window_s(2) - 0;  % Duration from stimulus to end of post-stim window
    baseline_window_s_dprime = [-poststim_duration_s, 0]; % Baseline window for d-prime calculation
    analysis_window_duration_s = psth_window_s(2) - psth_window_s(1); % Total analysis window duration
    
    % Note: Since batchProcessSpikesFromStim already removed artifact spikes,
    % we should use the full window duration for firing rate calculations
    effective_window_duration = analysis_window_duration_s; % Use full window since spikes already cleaned

    % Unit conversions (performed once to avoid repeated calculations)
    artifact_offset_s = artifact_window_s; % Convert artifact window to seconds (already in seconds)
    psth_window_ms = psth_window_s * 1000; % Convert PSTH window to milliseconds for plotting

    % Smoothing method flag (evaluated once)
    use_ssvkernel = strcmp(psth_smoothing_method, 'ssvkernel');

    % -------------------------------------------------------------------------
    % STEP 5: MAIN ANALYSIS LOOP - PER-PATTERN PSTH COMPUTATION
    % -------------------------------------------------------------------------
    % Process each stimulation pattern separately to compute electrode-specific responses

    % Loop through each stimulation pattern for individual PSTH analysis
    for patternIdx = 1:length(spikeData.stimPatterns)
        stimTimes = spikeData.stimPatterns{patternIdx};  % Extract stimulus times for current pattern

        if isempty(stimTimes)
            continue;  % Skip patterns with no stimulation events
        end

        % Create pattern-specific output directory for saving results
        patternFolderName = sprintf('Individual_PSTH_and_Raster_Pattern_%d', patternIdx);
        patternFigFolder = fullfile(figFolder, patternFolderName);
        if ~exist(patternFigFolder, 'dir')
            mkdir(patternFigFolder);
        end

        % Initialize data structures for this pattern's analysis
        electrodeLevelResponse_pattern_x = [];  % Stores quantitative metrics for each electrode
        valid_channel_count = 0;                % Counter for channels with valid data
        channel_metrics = [];                   % NOTE: currently not used
        temp_data = {};                         % Temporary storage for visualization data

        % =====================================================================
        % STEP 5.1: ELECTRODE-LEVEL RESPONSE COMPUTATION
        % =====================================================================
        % For each recording electrode, compute PSTH, baseline correction,
        % and statistical significance measures

        % Loop through each recording channel (electrode)
        for channelIdx = 1:numChannels
            % Skip analysis for stimulated channels
            if ismember(channelIdx, stimulatedChannels)
                continue; % Skip analysis for all stimulated channels
            end

            % ---------------------------------------------------------------
            % STEP 5.1a: SPIKE DATA EXTRACTION AND VALIDATION
            % ---------------------------------------------------------------
            % Extract and validate spike times for current channel
            if channelIdx > length(spikeData.spikeTimes) || ...
               isempty(spikeData.spikeTimes{channelIdx}) || ...
               ~isfield(spikeData.spikeTimes{channelIdx}, Params.SpikesMethod)
                continue;  % Skip channels with no spike data
            end

            all_spike_times_s = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
            if isempty(all_spike_times_s)
                continue;  % Skip channels with no detected spikes
            end

            % Note: Artifact removal already handled by batchProcessSpikesFromStim()
            % so we can use all_spike_times_s directly

            % ---------------------------------------------------------------
            % STEP 5.1b: RESPONSE PSTH COMPUTATION
            % ---------------------------------------------------------------
            % Calculate PSTH for the current channel
            if use_ssvkernel
                [response, resp_metrics] = calculate_psth_metrics(...
                    all_spike_times_s, stimTimes, psth_window_s, psth_bin_width_s, ...
                    'smoothing_method', 'ssvkernel');
            else
                [response, resp_metrics] = calculate_psth_metrics(...
                    all_spike_times_s, stimTimes, psth_window_s, psth_bin_width_s, ...
                    'smoothing_method', 'gaussian', 'gaussian_width_ms', psth_gaussian_width_ms);
            end

            if isempty(response.psth_samples)
                continue;  % Skip channels with no spikes in analysis window
            end

            % ---------------------------------------------------------------
            % STEP 5.1d: FIRING RATE MATRIX COMPUTATION (RESERVOIR COMPUTING)
            % ---------------------------------------------------------------
            % Calculate firing rates for consolidated matrix used in reservoir
            % computing analysis. This matrix contains all trials across all patterns.

            % Initialize arrays for firing rate calculations
            baseline_firing_rates_all_trials = [];
            poststim_firing_rates_all_trials = [];

            % Compute consolidated firing rate matrix (executed only once per channel)
            if patternIdx == 1  % Calculate consolidated matrix only during first pattern iteration
                for trialIdx = 1:numTrialsTotal
                    stimTime = allStimTimesConsolidated(trialIdx);

                    % Define analysis window for this trial (POST-ARTIFACT TO POST-STIM ONLY)
                    trial_window_start = stimTime + artifact_offset_s(2);  % Start AFTER artifact ends
                    trial_window_end = stimTime + psth_window_s(2);        % End of post-stim window

                    % Count spikes in post-artifact to post-stimulus window only
                    spikes_in_poststim_window = all_spike_times_s(...
                        all_spike_times_s >= trial_window_start & all_spike_times_s <= trial_window_end);

                    % Calculate window duration (post-artifact to post-stim only)
                    analysis_window_duration = trial_window_end - trial_window_start;

                    % Convert spike count to firing rate (Hz)
                    firing_rate_hz = length(spikes_in_poststim_window) / analysis_window_duration;
                    FiringRateMatrix(trialIdx, channelIdx) = firing_rate_hz;
                end
            end

            % ---------------------------------------------------------------
            % STEP 5.1e: D-PRIME CALCULATION
            % ---------------------------------------------------------------
            % Calculate trial-by-trial firing rates for baseline vs post-stimulus
            % periods to compute d-prime statistic for response significance

            % Calculate firing rates for each stimulus trial in current pattern
            for stimIdx = 1:length(stimTimes)
                stimTime = stimTimes(stimIdx);

                % Baseline period firing rate (pre-stimulus, same duration as post-stim)
                % Note: Using spikes already cleaned by batchProcessSpikesFromStim
                baseline_start = stimTime + baseline_window_s_dprime(1);
                baseline_end = stimTime + baseline_window_s_dprime(2);

                baseline_spikes = all_spike_times_s(...
                    all_spike_times_s >= baseline_start & all_spike_times_s < baseline_end);
                baseline_firing_rates_all_trials(stimIdx) = length(baseline_spikes) / effective_window_duration;

                % Post-stimulus period firing rate  
                poststim_start = stimTime + psth_window_s(1);
                poststim_end = stimTime + psth_window_s(2);

                poststim_spikes = all_spike_times_s(...
                    all_spike_times_s >= poststim_start & all_spike_times_s < poststim_end);
                poststim_firing_rates_all_trials(stimIdx) = length(poststim_spikes) / effective_window_duration;
            end

            % ---------------------------------------------------------------
            % STEP 5.1f: BASELINE PSTH COMPUTATION FOR BASELINE DISTRIBUTION
            % ---------------------------------------------------------------
            % Calculate multiple baseline PSTHs from pre-stimulus periods
            % Apply consistent artifact duration exclusion (same duration as batchProcessSpikesFromStim)

            baseline_aucs = zeros(num_baseline_psths, 1);
            all_baseline_psth_smooth = [];

            for i = 1:num_baseline_psths
                % Define baseline window moving backwards from pre-stimulus time
                % Each baseline window has the same duration as the post-stimulus window
                start_s = psth_window_s(1) - (i * baseline_duration_s);      % Start further back in time (before plotted pre-stimulus window)
                end_s = psth_window_s(1) - ((i-1) * baseline_duration_s);    
                current_baseline_window_s = [start_s, end_s];

                % Calculate baseline PSTH with artifact exclusion handled during smoothing
                if use_ssvkernel
                    [~, base_metrics] = calculate_psth_metrics(...
                        all_spike_times_s, stimTimes, current_baseline_window_s, psth_bin_width_s, ...
                        'smoothing_method', 'ssvkernel', 'artifact_exclusion_duration_s', artifact_duration_s);
                else
                    [~, base_metrics] = calculate_psth_metrics(...
                        all_spike_times_s, stimTimes, current_baseline_window_s, psth_bin_width_s, ...
                        'smoothing_method', 'gaussian', 'gaussian_width_ms', psth_gaussian_width_ms, ...
                        'artifact_exclusion_duration_s', artifact_duration_s);
                end
                baseline_aucs(i) = base_metrics.auc;

                % Store smoothed baseline PSTH for visualization
                if isempty(all_baseline_psth_smooth)
                    all_baseline_psth_smooth = zeros(num_baseline_psths, length(base_metrics.psth_smooth));
                end
                all_baseline_psth_smooth(i, :) = base_metrics.psth_smooth;
            end

            % ---------------------------------------------------------------
            % STEP 5.1g: RESPONSE METRICS 
            % ---------------------------------------------------------------
            % Compute baseline-corrected metrics and statistical significance measures

            % Baseline correction: subtract mean baseline AUC from response AUC
            mean_baseline_auc = mean(baseline_aucs);
            auc_corrected = resp_metrics.auc - mean_baseline_auc;
            mean_baseline_psth = mean(all_baseline_psth_smooth, 1);

            % Response decay analysis: find half-maximum time point
            [Rmax, Rmax_idx] = max(resp_metrics.psth_smooth);
            halfRmax = Rmax / 2;
            halfRmax_idx = find(resp_metrics.psth_smooth(Rmax_idx:end) <= halfRmax, 1, 'first');

            if ~isempty(halfRmax_idx)
                halfRmax_idx = halfRmax_idx + Rmax_idx - 1;
                halfRmax_time_s = resp_metrics.psth_smooth(halfRmax_idx);
                halfRmax_val = resp_metrics.psth_smooth(halfRmax_idx);
            else
                halfRmax_time_s = NaN;
                halfRmax_val = NaN;
            end

            % Statistical significance testing using d-prime
            % Calculate statistics from trial-by-trial firing rates
            baseline_mean_hz_dprime = mean(baseline_firing_rates_all_trials);
            baseline_std_hz_dprime = std(baseline_firing_rates_all_trials);
            poststim_mean_hz_dprime = mean(poststim_firing_rates_all_trials);
            poststim_std_hz_dprime = std(poststim_firing_rates_all_trials);

            % D-prime calculation
            % d' = (μ_post - μ_baseline) / √((σ²_post + σ²_baseline) / 2)
            if baseline_std_hz_dprime == 0 && poststim_std_hz_dprime == 0
                d_prime = abs(poststim_mean_hz_dprime - baseline_mean_hz_dprime);
            else
                pooled_variance = (baseline_std_hz_dprime^2 + poststim_std_hz_dprime^2) / 2;
                d_prime = (poststim_mean_hz_dprime - baseline_mean_hz_dprime) / sqrt(pooled_variance);
            end

            % Z-score calculation for standardized response magnitude
            % Z-score = (post-stim mean - baseline mean) / baseline std
            baseline_std_hz_safe = baseline_std_hz_dprime;
            if baseline_std_hz_safe == 0
                baseline_std_hz_safe = eps; % Avoid division by zero
            end
            zscore_response = (poststim_mean_hz_dprime - baseline_mean_hz_dprime) / baseline_std_hz_safe;

            % ---------------------------------------------------------------
            % STEP 5.1h: DATA ORGANIZATION AND STORAGE
            % ---------------------------------------------------------------
            % Store computed metrics and intermediate data for visualization and export

            valid_channel_count = valid_channel_count + 1;

            % Use channel name from stimInfo
            channel_id = spikeData.stimInfo{channelIdx}.channelName;

            % Store temporary data for calculations
            temp_data{valid_channel_count}.channelIdx = channelIdx;
            temp_data{valid_channel_count}.channel_id = channel_id;
            temp_data{valid_channel_count}.auc_corrected = auc_corrected;
            temp_data{valid_channel_count}.response = response;
            temp_data{valid_channel_count}.resp_metrics = resp_metrics;
            temp_data{valid_channel_count}.base_metrics = base_metrics;
            temp_data{valid_channel_count}.all_baseline_psth_smooth = all_baseline_psth_smooth;
            temp_data{valid_channel_count}.mean_baseline_auc = mean_baseline_auc;
            temp_data{valid_channel_count}.mean_baseline_psth = mean_baseline_psth;
            temp_data{valid_channel_count}.halfRmax_time_s = halfRmax_time_s;
            temp_data{valid_channel_count}.halfRmax_val = halfRmax_val;
            temp_data{valid_channel_count}.current_baseline_window_s = current_baseline_window_s;
            temp_data{valid_channel_count}.d_prime = d_prime;
            temp_data{valid_channel_count}.baseline_firing_rates_dprime = baseline_firing_rates_all_trials;
            temp_data{valid_channel_count}.poststim_firing_rates_dprime = poststim_firing_rates_all_trials;
            temp_data{valid_channel_count}.baseline_mean_hz_dprime = baseline_mean_hz_dprime;
            temp_data{valid_channel_count}.baseline_std_hz_safe = baseline_std_hz_safe;
            temp_data{valid_channel_count}.zscore_response = zscore_response;

            % Storing metrics for final output structure
            electrodeLevelResponse_pattern_x(valid_channel_count).channel_id = channel_id;
            electrodeLevelResponse_pattern_x(valid_channel_count).file_index = channelIdx;
            electrodeLevelResponse_pattern_x(valid_channel_count).pattern_id = patternIdx;
            electrodeLevelResponse_pattern_x(valid_channel_count).auc_response = resp_metrics.auc;
            electrodeLevelResponse_pattern_x(valid_channel_count).auc_baseline_mean = mean_baseline_auc;
            electrodeLevelResponse_pattern_x(valid_channel_count).auc_corrected = auc_corrected;
            electrodeLevelResponse_pattern_x(valid_channel_count).peak_firing_rate_hz = resp_metrics.peak_firing_rate;
            electrodeLevelResponse_pattern_x(valid_channel_count).peak_time_ms = resp_metrics.peak_time_s * 1000;
            electrodeLevelResponse_pattern_x(valid_channel_count).halfRmax_time_ms = halfRmax_time_s * 1000;
            electrodeLevelResponse_pattern_x(valid_channel_count).d_prime = d_prime;
            electrodeLevelResponse_pattern_x(valid_channel_count).zscore = zscore_response;
            electrodeLevelResponse_pattern_x(valid_channel_count).psth_window_s = psth_window_s;
        end % End of channel loop

        % =====================================================================
        % STEP 6: CHANNEL SELECTION AND VISUALIZATION
        % =====================================================================
        % Select top-responding channels (corrected AUC > 0.5)  for plotting.
        if ~isempty(temp_data)
            % Extract corrected AUC values for channel ranking
            auc_values = [electrodeLevelResponse_pattern_x.auc_corrected];

            % Identify channels with significant responses (corrected AUC > 0.5)
            high_auc_indices = find(auc_values > 0.5);

            % Rank channels by response strength and select top 5 for visualization
            [~, sort_indices] = sort(auc_values(high_auc_indices), 'descend');
            top_channels_for_plotting = high_auc_indices(sort_indices(1:min(5, length(sort_indices))));

            % ---------------------------------------------------------------
            % STEP 6.1: GENERATE PSTH PLOTS FOR TOP CHANNELS
            % ---------------------------------------------------------------
            % Create detailed PSTH plots with raster plots and statistical annotations
            % for the most responsive channels in the current pattern

            for plot_idx = 1:length(top_channels_for_plotting)
                channel_data_idx = top_channels_for_plotting(plot_idx);
                data = temp_data{channel_data_idx};

                % Create figure 
                fig = figure('Position', [100 100 1200 800], 'Visible', 'off');

                sgtitle(sprintf('Pattern %d | Channel %d | Corrected AUC: %.3f | d'' = %.2f', ...
                    patternIdx, data.channel_id, data.auc_corrected, data.d_prime), 'FontWeight', 'bold');

                % Calculate z-score transformations for standardized visualization
                baseline_mean_hz_dprime = data.baseline_mean_hz_dprime;
                baseline_std_hz_safe = data.baseline_std_hz_safe;

                % Calculate z-scores
                zscore_psth = (data.resp_metrics.psth_smooth - baseline_mean_hz_dprime) ./ baseline_std_hz_safe;
                zscore_baseline_psth = (data.mean_baseline_psth - baseline_mean_hz_dprime) ./ baseline_std_hz_safe;

                % Identify peak and half-maximum points in z-score space
                [zscore_peak_val, zscore_peak_idx] = max(zscore_psth);
                zscore_peak_time_ms = data.resp_metrics.time_vector_s(zscore_peak_idx) * 1000;

                % Calculate half-maximum decay time
                zscore_halfmax = zscore_peak_val / 2;
                zscore_halfmax_idx = find(zscore_psth(zscore_peak_idx:end) <= zscore_halfmax, 1, 'first');

                if ~isempty(zscore_halfmax_idx)
                    zscore_halfmax_idx = zscore_halfmax_idx + zscore_peak_idx - 1;
                    zscore_halfmax_time_ms = data.resp_metrics.time_vector_s(zscore_halfmax_idx) * 1000;
                    zscore_halfmax_val = zscore_psth(zscore_halfmax_idx);
                else
                    zscore_halfmax_time_ms = NaN;
                    zscore_halfmax_val = NaN;
                end

                % ---------------------------------------------------------------
                % SUBPLOT 1: SPIKE RASTER PLOT
                % ---------------------------------------------------------------
                % Display individual spike times for each stimulus trial
                ax1 = subplot(2, 1, 1); hold on;
                for trial_idx = 1:length(data.response.spikeTimes_byEvent)
                    trial_spikes_s = data.response.spikeTimes_byEvent{trial_idx};
                    if ~isempty(trial_spikes_s)
                        plot(trial_spikes_s * 1000, trial_idx * ones(size(trial_spikes_s)), ...
                            'r.', 'MarkerSize', 5);
                    end
                end
                hold off;
                set(gca, 'YDir', 'reverse');
                xlim(psth_window_ms);
                ylim([0 length(stimTimes)+1]);
                ylabel('Trial Number');
                xlabel('Time from stimulus (ms)');
                title('Spike Raster (Response)');
                grid on;

                % ---------------------------------------------------------------
                % SUBPLOT 2: PSTH COMPARISON PLOT
                % ---------------------------------------------------------------
                % Display response PSTH vs baseline PSTHs with statistical annotations
                ax2 = subplot(2, 1, 2); hold on;
                baseline_time_ms = (data.base_metrics.time_vector_s - data.current_baseline_window_s(1)) * 1000;

                % Plot individual baseline PSTHs 
                for i = 1:num_baseline_psths
                    zscore_individual_baseline = (data.all_baseline_psth_smooth(i, :) - baseline_mean_hz_dprime) ./ baseline_std_hz_safe;
                    plot(baseline_time_ms, zscore_individual_baseline, ...
                        'Color', [0.8 0.8 0.8], 'LineWidth', 0.5);
                end

                % Plot main traces
                p1_diag = plot(data.resp_metrics.time_vector_s*1000, zscore_psth, ...
                    'r-', 'LineWidth', 2, 'DisplayName', 'Response (Z-score)');
                p2_diag = plot(baseline_time_ms, zscore_baseline_psth, ...
                    'k-', 'LineWidth', 2, 'DisplayName', 'Mean Baseline (Z-score)');

                % Add Zmax markers
                plot(zscore_peak_time_ms, zscore_peak_val, ...
                    'bo', 'MarkerFaceColor', 'b', 'MarkerSize', 7, 'HandleVisibility', 'off');
                text(zscore_peak_time_ms, zscore_peak_val, ...
                    ' Z_{max}', ...
                    'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'left', ...
                    'Color', 'k', 'FontWeight', 'bold');

                % Add half-maximum decay marker 
                if ~isnan(zscore_halfmax_time_ms)
                    plot(zscore_halfmax_time_ms, zscore_halfmax_val, ...
                        'go', 'MarkerFaceColor', 'g', 'MarkerSize', 7, 'HandleVisibility', 'off');
                    text(zscore_halfmax_time_ms, zscore_halfmax_val, ...
                        ' Half Z_{max}', ...
                        'VerticalAlignment', 'top', 'HorizontalAlignment', 'left', ...
                        'Color', 'k', 'FontWeight', 'bold');
                end

                hold off;
                title('Diagnostic: Response vs. Baselines (Z-score)');
                ylabel('Z-score');
                xlabel('Time from stimulus (ms)');
                legend([p1_diag, p2_diag], 'Response', 'Mean Baseline', 'Location', 'Best');
                grid on;

                % Link axes for synchronized zooming
                linkaxes([ax1, ax2], 'x');
                xlim(psth_window_ms);

                % Save figure 
                figName = sprintf('Individual_PSTH_and_Raster_channel_%d', data.channel_id);
                figPath = fullfile(patternFigFolder, figName);
                pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, fig);

                close(fig);
            end % End of plotting loop
        end % End of plotting condition

        % =====================================================================
        % STEP 6.2: DATA COLLECTION FOR STIMULATION ANALYSIS
        % =====================================================================
        % Collect computed electrode-level response metrics for the current pattern
        % into the stimData structure for later saving to experiment mat file

        if ~isempty(electrodeLevelResponse_pattern_x)
            % Store pattern data in stimData structure
            patternFieldName = sprintf('electrodeLevelResponse_pattern_%d', patternIdx);
            stimData.(patternFieldName) = electrodeLevelResponse_pattern_x;
        end

    end % End of pattern loop

    %% ========================================================================
    %% STEP 7: TIME-TO-FIRST-SPIKE LATENCY ANALYSIS
    %% ========================================================================
    % Calculate time-to-first-spike latencies for all channels and stimulus trials

    % -------------------------------------------------------------------------
    % STEP 7.1: LATENCY MATRIX INITIALIZATION
    % -------------------------------------------------------------------------
    % Initialize matrix to store latency measurements across all trials and channels
    % Matrix dimensions: [numTrialsTotal x numChannels]
    % Values: Time-to-first-spike in milliseconds after stimulus onset
    % NaN indicates: no spike detected within search window OR stimulated channel (excluded)
    latencyMatrix = NaN(numTrialsTotal, numChannels);

    % Define latency search window: only post-stimulus, post-artifact times
    % Start search after artifact ends, search until end of post-stimulus window
    latency_search_start_s = artifact_offset_s(2);  % After artifact window ends
    latency_search_end_s = psth_window_s(2);        % End of post-stimulus window
    latency_search_window_s = [latency_search_start_s, latency_search_end_s];

    % -------------------------------------------------------------------------
    % STEP 7.2: LATENCY COMPUTATION ACROSS ALL CHANNELS AND TRIALS
    % -------------------------------------------------------------------------
    % Calculate first-spike latencies using the same artifact exclusion approach

    for channelIdx = 1:numChannels
        % Skip stimulated channels 
        if ismember(channelIdx, stimulatedChannels)
            continue; % Latency matrix already initialized with NaN for these channels
        end

        % Validate spike data availability for current channel
        if channelIdx > length(spikeData.spikeTimes) || ...
           isempty(spikeData.spikeTimes{channelIdx}) || ...
           ~isfield(spikeData.spikeTimes{channelIdx}, Params.SpikesMethod)
            continue;  % Skip channels with no spike data
        end

        all_spike_times_s = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
        if isempty(all_spike_times_s)
            continue;  % Skip channels with no detected spikes
        end

        % Process each stimulus trial across all patterns
        for trialIdx = 1:numTrialsTotal
            stimTime = allStimTimesConsolidated(trialIdx);

            % Define temporal search window for first-spike detection (post-artifact only)
            search_start = stimTime + latency_search_window_s(1);  % Start after artifact ends
            search_end = stimTime + latency_search_window_s(2);    % End of post-stimulus window

            % Find valid spikes (within post-stimulus, post-artifact search window only)
            valid_spikes = all_spike_times_s(...
                all_spike_times_s >= search_start & all_spike_times_s <= search_end);

            % Calculate latency to first valid spike (guaranteed to be positive)
            if ~isempty(valid_spikes)
                first_spike_time = min(valid_spikes);
                latency_s = first_spike_time - stimTime;
                latency_ms = latency_s * 1000;  % Convert to milliseconds

                % Double-check that latency is positive (should always be true with new search window)
                if latency_ms > 0
                    latencyMatrix(trialIdx, channelIdx) = latency_ms;
                end
            end
            % If no valid spikes found, latencyMatrix entry remains NaN
        end
    end

    % -------------------------------------------------------------------------
    % STEP 7.3: LATENCY ANALYSIS SUMMARY STATISTICS
    % -------------------------------------------------------------------------
    % Calculate descriptive statistics for latency analysis validation
    num_valid_latencies = sum(~isnan(latencyMatrix(:)));
    num_total_possible = numTrialsTotal * (numChannels - length(stimulatedChannels));
    detection_rate = num_valid_latencies / num_total_possible * 100;

    %% ========================================================================
    %% SECTION 8: CONSOLIDATED DATA EXPORT FOR RESERVOIR COMPUTING
    %% ========================================================================
    % Export consolidated matrices and metadata for downstream RC analysis

    % -------------------------------------------------------------------------
    % STEP 8.0: EXACT SPIKE TIMES MATRIX COMPUTATION
    % -------------------------------------------------------------------------
    % Create cell array containing exact spike times for each trial-electrode combination
    % Dimensions: [numTrialsTotal x numChannels] cell array
    % Each cell contains column vector of spike times in ms post-stimulation
    ExactSpikeTimes = cell(numTrialsTotal, numChannels);

    % Define analysis window for spike time extraction (same as firing rate analysis)
    spike_extraction_window_s = psth_window_s;

    for channelIdx = 1:numChannels
        % Skip stimulated channels (leave cells empty)
        if ismember(channelIdx, stimulatedChannels)
            continue; % ExactSpikeTimes already initialized as empty cells for these channels
        end

        % Validate spike data availability for current channel
        if channelIdx > length(spikeData.spikeTimes) || ...
           isempty(spikeData.spikeTimes{channelIdx}) || ...
           ~isfield(spikeData.spikeTimes{channelIdx}, Params.SpikesMethod)
            continue;  % Skip channels with no spike data
        end

        all_spike_times_s = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
        if isempty(all_spike_times_s)
            continue;  % Skip channels with no detected spikes
        end

        % Process each stimulus trial across all patterns
        for trialIdx = 1:numTrialsTotal
            stimTime = allStimTimesConsolidated(trialIdx);

            % Define analysis window for this trial (POST-ARTIFACT TO POST-STIM ONLY)
            trial_window_start = stimTime + artifact_offset_s(2);  % Start AFTER artifact ends
            trial_window_end = stimTime + psth_window_s(2);        % End of post-stim window

            % Find spikes in post-artifact to post-stimulus window only
            spikes_in_window = all_spike_times_s(...
                all_spike_times_s >= trial_window_start & all_spike_times_s <= trial_window_end);

            % Convert to milliseconds post-stimulation and store as column vector
            if ~isempty(spikes_in_window)
                spike_times_post_stim_ms = (spikes_in_window - stimTime) * 1000;
                ExactSpikeTimes{trialIdx, channelIdx} = spike_times_post_stim_ms(:); % Ensure column vector
            else
                ExactSpikeTimes{trialIdx, channelIdx} = []; % Empty array for no spikes
            end
        end
    end

    % -------------------------------------------------------------------------
    % STEP 8.1: FIRING RATE MATRIX METADATA PREPARATION
    % -------------------------------------------------------------------------
    % Create comprehensive metadata structure for the consolidated firing rate matrix
    FiringRateMatrix_info = struct();
    FiringRateMatrix_info.description = 'Consolidated firing rates (Hz) in post-artifact to post-stimulus window across all patterns';
    FiringRateMatrix_info.dimensions = sprintf('[%d trials x %d channels] - All stimulation times from all patterns in chronological order', numTrialsTotal, numChannels);
    FiringRateMatrix_info.analysis_window_s = [artifact_offset_s(2), psth_window_s(2)];  % Post-artifact to post-stim only
    FiringRateMatrix_info.artifact_window_ms = artifact_window_ms;
    FiringRateMatrix_info.stimulated_channels_excluded = stimulatedChannels;
    FiringRateMatrix_info.allStimTimesConsolidated = allStimTimesConsolidated;  % Column vector of all stim times chronologically
    FiringRateMatrix_info.stimPatternLabels = stimPatternLabels;  % Column vector indicating which pattern each trial belongs to
    FiringRateMatrix_info.numTrialsTotal = numTrialsTotal;
    FiringRateMatrix_info.note = 'Each row represents one stimulation trial, columns represent recording channels. Analysis window is POST-ARTIFACT TO POST-STIMULUS ONLY (excludes pre-stim and artifact periods). allStimTimesConsolidated and stimPatternLabels are column vectors with matching indices.';

    % -------------------------------------------------------------------------
    % STEP 8.2: LATENCY MATRIX METADATA PREPARATION
    % -------------------------------------------------------------------------
    % Create comprehensive metadata structure for the consolidated latency matrix
    latencyMatrix_info = struct();
    latencyMatrix_info.description = 'Time-to-first-spike latencies (ms) in post-artifact to post-stimulus window across all patterns';
    latencyMatrix_info.dimensions = sprintf('[%d trials x %d channels] - All stimulation times from all patterns in chronological order', numTrialsTotal, numChannels);
    latencyMatrix_info.search_window_s = latency_search_window_s;  % Post-artifact to post-stim only
    latencyMatrix_info.artifact_window_ms = artifact_window_ms;
    latencyMatrix_info.stimulated_channels_excluded = stimulatedChannels;
    latencyMatrix_info.allStimTimesConsolidated = allStimTimesConsolidated;  % Column vector of all stim times chronologically
    latencyMatrix_info.stimPatternLabels = stimPatternLabels;  % Column vector indicating which pattern each trial belongs to
    latencyMatrix_info.numTrialsTotal = numTrialsTotal;
    latencyMatrix_info.detection_rate_percent = detection_rate;
    latencyMatrix_info.mean_latency_ms = nanmean(latencyMatrix(:));
    latencyMatrix_info.median_latency_ms = nanmedian(latencyMatrix(:));
    latencyMatrix_info.note = 'Each row represents one stimulation trial, columns represent recording channels. Values are latency in ms to first spike after stimulus (POST-ARTIFACT TO POST-STIMULUS ONLY, excludes pre-stim period). NaN indicates no spike detected in search window or stimulated channel.';

    % -------------------------------------------------------------------------
    % STEP 8.3: EXACT SPIKE TIMES METADATA PREPARATION
    % -------------------------------------------------------------------------
    % Create comprehensive metadata structure for the exact spike times cell array
    ExactSpikeTimes_info = struct();
    ExactSpikeTimes_info.description = 'Exact spike times (ms) post-stimulation for each trial-electrode combination in post-artifact to post-stimulus window';
    ExactSpikeTimes_info.dimensions = sprintf('[%d trials x %d channels] cell array - All stimulation times from all patterns in chronological order', numTrialsTotal, numChannels);
    ExactSpikeTimes_info.analysis_window_s = [artifact_offset_s(2), psth_window_s(2)];  % Post-artifact to post-stim only
    ExactSpikeTimes_info.artifact_window_ms = artifact_window_ms;
    ExactSpikeTimes_info.stimulated_channels_excluded = stimulatedChannels;
    ExactSpikeTimes_info.allStimTimesConsolidated = allStimTimesConsolidated;  % Column vector of all stim times chronologically
    ExactSpikeTimes_info.stimPatternLabels = stimPatternLabels;  % Column vector indicating which pattern each trial belongs to
    ExactSpikeTimes_info.numTrialsTotal = numTrialsTotal;
    ExactSpikeTimes_info.time_units = 'milliseconds post-stimulation';
    ExactSpikeTimes_info.note = 'Each cell {trial, channel} contains column vector of spike times in ms post-stimulation. Analysis window is POST-ARTIFACT TO POST-STIMULUS ONLY (excludes pre-stim and artifact periods). Empty cells [] indicate no spikes detected or stimulated channels.';

    % -------------------------------------------------------------------------
    % STEP 8.4: CONSOLIDATED DATA EXPORT
    % -------------------------------------------------------------------------
    % Create output directory and save matrices with metadata for reservoir computing
    consolidatedFolder = fullfile(figFolder, 'Reservoir Computing Metrics');
    if ~exist(consolidatedFolder, 'dir')
        mkdir(consolidatedFolder);
    end

    % Export firing rate matrix 
    matrix_filename = fullfile(consolidatedFolder, 'FiringRateMatrix_consolidated.mat');
    save(matrix_filename, 'FiringRateMatrix', 'FiringRateMatrix_info');

    % Export latency matrix for 
    latency_filename = fullfile(consolidatedFolder, 'latencyMatrix_consolidated.mat');
    save(latency_filename, 'latencyMatrix', 'latencyMatrix_info');

    % Export exact spike times cell array
    spikeTimes_filename = fullfile(consolidatedFolder, 'ExactSpikeTimes_consolidated.mat');
    save(spikeTimes_filename, 'ExactSpikeTimes', 'ExactSpikeTimes_info');

    % Export exact spike times matrix
    exact_spike_times_filename = fullfile(consolidatedFolder, 'ExactSpikeTimes_consolidated.mat');
    save(exact_spike_times_filename, 'ExactSpikeTimes');

    %% ========================================================================
    %% SAVE STIMULATION DATA TO EXPERIMENT MAT FILE
    %% ========================================================================
    % Save the collected stimulation analysis data to the experiment mat file
    % for later aggregation into CSV files

    if ~isempty(stimData)
        % Construct path to experiment mat file
        experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, 'ExperimentMatFiles');
        experimentMatFname = strcat(char(Info.FN{1}),'_',Params.outputDataFolderName,'.mat');
        experimentMatFpath = fullfile(experimentMatFolderPath, experimentMatFname);

        % Save stimData to the experiment file (append to existing data)
        if exist(experimentMatFpath, 'file')
            save(experimentMatFpath, 'stimData', '-append');
            fprintf('Stimulation data saved to: %s\n', experimentMatFpath);
        else
            fprintf('Warning: Experiment mat file not found: %s\n', experimentMatFpath);
        end
    else
        fprintf('Warning: No stimulation data collected for %s\n', Info.FN{1});
    end

end