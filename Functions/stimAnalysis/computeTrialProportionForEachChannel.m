function proportions = computeTrialProportionForEachChannel(spikeTimes, allStimTimes, psth_window_s, baseline_window_s, numChannels, spikeMethod)
%computeTrialProportionForEachChannel Computes trial proportion metric for each channel.
%   For each channel, computes the proportion of trials where the post-stim
%   spike count exceeds the pre-stim spike count.

proportions = zeros(numChannels, 1);

for chIdx = 1:numChannels

    if isempty(spikeTimes{chIdx}) || isempty(spikeTimes{chIdx}.(spikeMethod))
        proportions(chIdx) = 0;
        continue;
    end

    channelSpikeTimes = spikeTimes{chIdx}.(spikeMethod);

    proportions(chIdx) = computeTrialProportion(channelSpikeTimes, allStimTimes, ...
        psth_window_s, baseline_window_s);
end

end
