function allSpikeTimes = combineAllChannelSpikeTimes(spikeTimes, method)
%COMBINEALLCHANNELSPIKETIMES Summary of this function goes here
%   Detailed explanation goes here

allSpikeTimes = [];

for channelIdx = 1:length(spikeTimes)
    allSpikeTimes = [allSpikeTimes; spikeTimes{channelIdx}.(method)];
end

allSpikeTimes = sort(allSpikeTimes);

end