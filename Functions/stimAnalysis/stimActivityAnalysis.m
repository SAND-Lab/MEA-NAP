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
        allBlankDuations = cellfun(@(s) s.blankDurations, spikeData.stimInfo, 'UniformOutput', false);
        allBlankDuations = [allBlankDuations{:}];
        Params.blankDurMode = mode(allBlankDuations(:));
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
    
     % Do it for each pattern 
    for patternIdx = 1:length(spikeData.stimPatterns)
        figureHandle = figure;
        figName = sprintf('10_stimulation_raster_and_psth_pattern_%.f', patternIdx);
        [frAlignedToStim, rasterBins] = getFrAlignedToStim( ... 
            spikeData, spikeData.stimPatterns{patternIdx}, Params);
        plotMetricAlignedToStim(frAlignedToStim, rasterBins, Info, Params, ...
                ylabel_txt, figFolder, figName, figureHandle)
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
            patternSpikeMatrix(:, start_idx:end_idx) = patternSpikeMatrixAtWindow;
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



end