function spikeAmps = getSpikeAmp(spikeWaveforms)
%GETSPIKEAMP Get spike amplitude from spikeData
%   Detailed explanation goes here

numChannels = length(spikeWaveforms);
spikeAmps = cell(1, numChannels);

for channelIdx = 1:length(spikeWaveforms)
    spikeAmps{channelIdx} = struct();
    spikeDmethods = fieldnames(spikeWaveforms{channelIdx});
    for spikeDmethodIdx = 1:length(spikeDmethods)
        spikeMethodName = spikeDmethods{spikeDmethodIdx};
        spikeAmps{channelIdx}.(spikeMethodName) = min(spikeWaveforms{channelIdx}.(spikeMethodName), [], 2);
    end
end


end

