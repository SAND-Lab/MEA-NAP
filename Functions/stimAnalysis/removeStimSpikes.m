function spikeTimesStimRemoved = removeStimSpikes(allStimTimes, spikeTimes, Params)
%REMOVESTIMSPIKES Remove spike times around the stimulation time
% INPUTS
% ----------
% allStimTimes : vector 
%    vector of size (numStimTimes, 1)
%    stimulation times in seconds 
% spikeTimes : cell 
%     cell of size (1, numChannels)
%     each cell entry is a structure, whose fields are the spike 
%     detection methods, and within each field are the detected spike times
%     in seconds 
% Params : struct 
%     Parameter structure
%     Here we only need Params.stimRemoveSpikesWindow, which is a 
%     vector with two entries, being the window in which you want to remove
%     the spikes around the stimulation time, eg. [-0.02, 0.03] will remove
%     spikes before 20 ms and after 30 ms centered on the stimulation times
% 
% OUTPUT 
% ------
% spikeTimesStimRemoved : cell 
%     same format as spikeTimes, with some spikes removed


spikeMethods = fieldnames(spikeTimes{1});
numChannels = length(spikeTimes);
spikeTimesStimRemoved = cell(1, numChannels);

for methodIdx = 1:length(spikeMethods)

    spikeMethod = spikeMethods{methodIdx};

    for channelIdx= 1:numChannels
        channelSpikeTimes = spikeTimes{channelIdx}.(spikeMethod);
        
        % Process spike times to remove spikes near stimulus time 
        
        for stimTimeIdx = 1:length(allStimTimes)
            stimTime = allStimTimes(stimTimeIdx);
            channelSpikeTimes(channelSpikeTimes >=  stimTime + Params.stimRemoveSpikesWindow(1) & ...
                              channelSpikeTimes <=  stimTime + Params.stimRemoveSpikesWindow(2)...
                ) = [];
        end  
        
        spikeTimesStimRemoved{channelIdx}.(spikeMethod) = channelSpikeTimes;

    end


end

end

