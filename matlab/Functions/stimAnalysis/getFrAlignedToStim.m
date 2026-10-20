function [frAlignedToStim, rasterBins] = getFrAlignedToStim(spikeData, allStimTimes, Params)
%GETFRALIGNEDTOSTIM Summary of this function goes here
%   Detailed explanation goes here
% Returns 
% -------
% frAlignedToStim : matrix 
%     double of shape (numChannel, numTrials, numTimeBins)
    
    numChannels = length(spikeData.stimInfo);

    rasterWindow = Params.stimAnalysisWindow;
    rasterBinWidth = Params.rasterBinWidth; % 0.01;   % originally 0.025 

    rasterBins = rasterWindow(1):rasterBinWidth:rasterWindow(2);
    numBins = length(rasterBins) - 1; 
    
    numStimEvent = length(allStimTimes);
    frAlignedToStim = zeros(numChannels, numStimEvent, numBins) + nan;
    
    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeData.spikeTimes{channelIdx}.(Params.SpikesMethod);
        
         for stimEventIdx = 1:numStimEvent 
            stimTime = allStimTimes(stimEventIdx);
            
            frAlignedToStim(channelIdx, stimEventIdx, :) = histcounts(channelSpikeTimes - stimTime, rasterBins) / rasterBinWidth;
    
         end 
    
        
    end
end

