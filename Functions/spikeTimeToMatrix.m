function spike_matrix = spikeTimeToMatrix(spikeTimesStruct, start_time, end_time, sampling_rate)

 
channel_names = fieldnames(spikeTimesStruct);
bin_edges = start_time:1/sampling_rate:end_time;

num_bins = length(bin_edges) - 1; 
num_channels = length(channel_names);
spike_matrix = zeros(num_bins, num_channels);

for channel_idx = 1:numel(channel_names)
    channel_spike_times = spikeTimesStruct.(channel_names{channel_idx});
    spike_vector = histcounts(channel_spike_times, bin_edges);
    spike_matrix(:, channel_idx) = spike_vector;
end 


end 
