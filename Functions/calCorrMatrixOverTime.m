function corrMatrixOverT = calCorrMatrixOverTime(spikeMatrix, time_window, step_size, fs)
% Function to calculate the correlation matrix over some sliding window 

recording_duration = size(spikeMatrix, 1) / fs;
t_starts = 0:step_size:(recording_duration - time_window);
t_ends = time_window:step_size:recording_duration;

num_window = length(t_starts);
num_nodes = size(spikeMatrix, 2);
corrMatrixOverT = zeros(num_nodes, num_nodes, num_window);

for n_t_start = 1:length(t_starts)
    
    t_start = t_starts(n_t_start);
    t_end = t_ends(n_t_start);
    t_start_frame = t_start * fs + 1;
    t_end_frame = t_end * fs;
    subset_spike_matrix = spikeMatrix(t_start_frame:t_end_frame, :);
    corrMatrixOverT(:, :, n_t_start) = corr(subset_spike_matrix);
    

end 


end 