function stimActivityAnalysis(spikeData, Params, Info, figFolder, oneFigureHandle)
    % Performs analysis of spike data relative to stimulation times 
    % INPUT
    % -------
    % spikeData : struct 
    % Params : struct 
    % Info : struct 
    % figFolder : path 
    % oneFigureHandle : matlab figure object
    

    %% Gather stimulation times
    allStimTimes = [];
    
    for channelIdx = 1:length(spikeData.stimInfo)
        
        allStimTimes = [allStimTimes, spikeData.stimInfo{channelIdx}.elecStimTimes];
    
    end

    %% Firing rate before and after stimulation 

    numStimEvent = length(allStimTimes);

    preStimWindow = Params.preStimWindow; 
    postStimWindow = Params.postStimWindow;
    spikeMethod = Params.SpikesMethod;
    
    preStimWindowDur = preStimWindow(2) - preStimWindow(1);
    postStimWindowDur = postStimWindow(2) - postStimWindow(1);
    
    preStimFR = zeros(length(channelIdx), 1) + nan;
    postStimFR = zeros(length(channelIdx), 1) + nan;
    
    numChannels = length(spikeData.stimInfo);
    
    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
        
        numSpikesPreStim = zeros(numStimEvent, 1) + nan;
        numSpikesPostStim = zeros(numStimEvent, 1) + nan;
    
        for stimEventIdx = 1:numStimEvent 
            stimTime = allStimTimes(stimEventIdx);
    
            numSpikesPreStim(stimEventIdx) = length(find(...
                (channelSpikeTimes >= stimTime + preStimWindow(1)) & ...
                (channelSpikeTimes <= stimTime + preStimWindow(2)) ...
                )); 
    
            numSpikesPostStim(stimEventIdx) = length(find(...
                (channelSpikeTimes >= stimTime + postStimWindow(1)) & ...
                (channelSpikeTimes <= stimTime + postStimWindow(2)) ...
                )); 
        end 
    
        preStimFR(channelIdx) = mean(numSpikesPreStim) / preStimWindowDur;
        postStimFR(channelIdx) = mean(numSpikesPostStim) / postStimWindowDur;
    end 

    prePostVals = [preStimFR, postStimFR];
    prePostMin = min(prePostVals); 
    prePostMax = max(prePostVals);
    unityVals = linspace(prePostMin, prePostMax, 100);
    
    
    figureHandle = figure;
    set(figureHandle, 'Position', [100, 100, 400, 400]);
    scatter(preStimFR, postStimFR);
    hold on 
    plot(unityVals, unityVals, 'LineStyle', '--')
    xlabel('Pre-stim firing rate (spikes/s)')
    ylabel('Post-stim firing rate (spikes/s)')
    set(gcf, 'color', 'w')
    set(gca, 'TickDir', 'out');
    title(Info.FN{1}, 'Interpreter', 'none');

    % save figure
    
    figName = '9_FR_before_after_stimulation';
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);

    %% Plot population raster align to stim times 
    rasterWindow = [Params.preStimWindow(1), Params.postStimWindow(2)];
    rasterBinWidth = 0.01;   % originally 0.025 

    rasterBins = rasterWindow(1):rasterBinWidth:rasterWindow(2);
    numBins = length(rasterBins) - 1; 
    
    frAlignedToStim = zeros(numChannels, numStimEvent, numBins) + nan;
    
    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
        
        % Process spike times to remove spikes near stimulus time 
        
        for stimTimeIdx = 1:length(allStimTimes)
            stimTime = allStimTimes(stimTimeIdx);
            channelSpikeTimes(channelSpikeTimes >=  stimTime + Params.stimRemoveSpikesWindow(1) & ...
                              channelSpikeTimes <=  stimTime + Params.stimRemoveSpikesWindow(2)...
                ) = [];
        end  
         
    
         for stimEventIdx = 1:numStimEvent 
            stimTime = allStimTimes(stimEventIdx);
            
            frAlignedToStim(channelIdx, stimEventIdx, :) = histcounts(channelSpikeTimes - stimTime, rasterBins) / rasterBinWidth;
    
         end 
    
        
    end

    figureHandle = figure;
    set(figureHandle, 'Position', [100, 100, 600, 500]);
    subplot(2, 1, 1)
    meanFRalignedToStim = squeeze(mean(frAlignedToStim, [1, 2]));
    plot(rasterBins(2:end), meanFRalignedToStim)
    hold on 
    fill([Params.stimRemoveSpikesWindow(1), Params.stimRemoveSpikesWindow(2), ...
          Params.stimRemoveSpikesWindow(2), Params.stimRemoveSpikesWindow(1)], ...
         [0, 0, max(meanFRalignedToStim), max(meanFRalignedToStim)], [0.5, 0.5, 0.5], 'FaceAlpha', 0.3,'LineStyle','none')
    box off 
    set(gca, 'TickDir', 'out');
    ylabel('Mean firing rate (spikes/s)')
    title(Info.FN{1}, 'Interpreter', 'none');
    
    subplot(2, 1, 2)
    imagesc(rasterBins(2:end), 1:numChannels, squeeze(mean(frAlignedToStim, 2)))
    box off
    ylabel('Channel')
    xlabel('Time from stimulation (s)')
    set(gca, 'TickDir', 'out');
    set(gcf, 'color', 'w')
    

    % save figure
    figName = '10_stimulation_raster_and_psth';
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);

    %% Look at spike amplitude aligned to stimulus 
    spikeAmps = getSpikeAmp(spikeData.spikeWaveforms); 
    spikeData.spikeAmps = spikeAmps;
    
    rasterWindow = [Params.preStimWindow(1), Params.postStimWindow(2)];
    rasterBinWidth = 0.01;   % originally 0.025 
    
    rasterBins = rasterWindow(1):rasterBinWidth:rasterWindow(2);
    numBins = length(rasterBins) - 1; 
    
    ampAlignedToStim = zeros(numChannels, numStimEvent, numBins) + nan;

    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
        channelSpikeAmps = spikeData.spikeAmps{channelIdx}.(spikeMethod);
        
        % Process spike times to remove spikes near stimulus time 
        
        for stimTimeIdx = 1:length(allStimTimes)
            stimTime = allStimTimes(stimTimeIdx);
            removeIndex = find((channelSpikeTimes >=  stimTime + Params.stimRemoveSpikesWindow(1)) & ...
                               (channelSpikeTimes <=  stimTime + Params.stimRemoveSpikesWindow(2)));
            channelSpikeTimes(removeIndex) = [];
            channelSpikeAmps(removeIndex) = [];
        end  
         
    
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
    fill([Params.stimRemoveSpikesWindow(1), Params.stimRemoveSpikesWindow(2), ...
          Params.stimRemoveSpikesWindow(2), Params.stimRemoveSpikesWindow(1)], ...
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
    set(gcf, 'color', 'w')
    

    % save figure
    figName = '11_stimulation_amplitude_raster_and_psth';
    pipelineSaveFig(fullfile(figFolder, figName), Params.figExt, Params.fullSVG, gcf);

    %% Spike Latency / Time-to-first-spike 
    channelMeanSpikeLatency = zeros(numChannels, 1) + nan;
    % for each electrode
    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeTimesStimRemoved{channelIdx}.(Params.SpikesMethod);
        spikeLatencies = getSpikeLatencyRelStim(allStimTimes, channelSpikeTimes);
        channelMeanSpikeLatency(channelIdx) = nanmean(spikeLatencies);
    end
    
end