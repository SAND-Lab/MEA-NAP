function batchProcessSpikesFromStim(ExpName, Params)
    
    spikeDetectionFolder = fullfile(Params.outputDataFolder, ...
            Params.outputDataFolderName, '1_SpikeDetection', '1A_SpikeDetectedData');

    for expIdx = 1:length(ExpName)
        % temp hard-coded things 
        Params.removeSpikesFromStimElec = 1;
    
        % Load spike detected data 
        spikeDataFpath = fullfile(spikeDetectionFolder, [ExpName{expIdx} '_spikes.mat']);
        spikeData = load(spikeDataFpath);
        
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
        
        allArtifactWindowEnd = allBlankEndTimes + Params.postStimWindowDur / 1000;
        
        % Go through each of these window and remove spikes 
        for channelIdx = 1:length(spikeData.channels)
            channelSpikeMethods = fieldnames(spikeData.spikeTimes{channelIdx});
    
            for spikeMethodIdx = 1:length(channelSpikeMethods)
                spikeMethod = channelSpikeMethods{spikeMethodIdx};
                spikeMethodSpikeTimes = spikeData.spikeTimes{channelIdx}.(spikeMethod);
                spikeMethodAmps =  spikeData.spikeAmps{channelIdx}.(spikeMethod);
                removalIndices = [];
                for windowIdx = 1:length(allArtifactWindowEnd)
    
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

        % save the processed spike data
        save(spikeDataFpath, '-struct', 'spikeData');
    end


end