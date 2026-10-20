function spikeMatrix = spikeTimesToSpikeMatrix(spikeTimes, duration, fs)

start_time = 0;
end_time = duration;
bin_edges = start_time:1/fs:end_time;

numUnits = length(spikeTimes);
num_bins = length(bin_edges) - 1;
spikeMatrix = zeros(num_bins, numUnits);

for unit = 1:numUnits
    channel_spike_times = spikeTimes{unit};
    spike_vector = histcounts(channel_spike_times, bin_edges);
    spikeMatrix(:, unit) = spike_vector;
end 


end 