function batchProcessSpikesFromStim(ExpName, Params)
    
    % temp hard-coded things 
    Params.removeSpikesFromStimElec = 1;

    % Load spike detected data 
    spikeData = load('/home/timsit/MEA-NAP/testStimDetection/OutputData13Nov2025/1_SpikeDetection/1A_SpikeDetectedData/R241118CT9A_DIV197_stimLR_spikes.mat');
    
    allBlankStartTimes = [];
    allBlankEndTimes = [];

    % Loop through each channel to find stimulation times 
    for channelIdx = 1:length(spikeData.channels)
        
        channelStimInfo = spikeData.stimInfo{channelIdx};

        % OPTIONAL: Remove spikes from stimulation electrodes
        if Params.removeSpikesFromStimElec
            if length(channelStimInfo.elecStimTimes) > 0
                channelSpikeMethods = fieldnames(spikeData.spikeTimes{channelIdx});
                for spikeMethodIdx = 1:length(channelSpikeMethods)
                    spikeMethod = channelSpikeMethods{spikeMethodIdx};
                    spikeData.spikeTimes{channelIdx}.(spikeMethod) = [];
                    spikeData.spikeAmps{channelIdx}.(spikeMethod) = [];
                end
            end
            
        end
        allBlankStartTimes = [allBlankStartTimes; channelStimInfo.blankStarts];
        allBlankEndTimes = [allBlankEndTimes; channelStimInfo.blankEnds];

    end
    
    % NOTE: str2num() is temporary
    allArtifactWindowEnd = allBlankEndTimes + str2num(Params.postStimWindowDur) / 1000;
    
    % Go through each of these window and remove spikes 
    for channelIdx = 1:length(spikeData.channels)
        channelSpikeMethods = fieldnames(spikeData.spikeTimes{channelIdx});

        for spikeMethodIdx = 1:length(channelSpikeMethods)
            spikeMethod = channelSpikeMethods{spikeMethodIdx};
            spikeMethodSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
            spikeMethodAmps =  spikeData.spikeAmps{channelIdx}.(spikeMethod);
            removalIndices = [];
            for windowIdx = 1:length(batchProcessSpikesFromStim)

                winStart = allBlankStartTimes(windowIdx);
                winEnd = allArtifactWindowEnd(windowIdx);
                  
                removalIndices = [removalIndices; ...
                    find((spikeMethodSpikeTimes >= winStart) & ...
                    (spikeMethodSpikeTimes <= winEnd))];
            end
            
            spikeMethodSpikeTimes(removalIndices) = [];
            spikeMethodAmps(removalIndices) = [];
            
            % re-assign the spike data 
            spikeData.spikeTimes{channelIdx}.(spikeMethod) = spikeMethodSpikeTimes;
            spikeData.spikeAmps{channelIdx}.(spikeMethod) = spikeMethodAmps;
        end
    
    
    end


end